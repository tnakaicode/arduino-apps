#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <termios.h>
#include <unistd.h>

#include <string>

#include "dbAccess.h"
#include "epicsExit.h"
#include "epicsExport.h"
#include "epicsMutex.h"
#include "epicsThread.h"
#include "errlog.h"
#include "iocsh.h"

namespace {

epicsMutex serialReaderMutex;
epicsThreadId serialThreadId = 0;
bool serialThreadRunning = false;
bool serialThreadStop = false;

struct SerialThreadConfig {
    std::string pvPrefix;
    std::string serialPort;
    std::string baudRate;
};

speed_t parseBaud(const char *baudText)
{
    long baud = strtol(baudText, NULL, 10);
    switch (baud) {
        case 9600:
            return B9600;
        case 19200:
            return B19200;
        case 38400:
            return B38400;
        case 57600:
            return B57600;
        case 115200:
        default:
            return B115200;
    }
}

bool configureSerialPort(int fd, speed_t baud)
{
    struct termios tio;
    if (tcgetattr(fd, &tio) != 0) {
        return false;
    }

    cfsetispeed(&tio, baud);
    cfsetospeed(&tio, baud);

    tio.c_cflag |= (CLOCAL | CREAD);
    tio.c_cflag &= ~PARENB;
    tio.c_cflag &= ~CSTOPB;
    tio.c_cflag &= ~CSIZE;
    tio.c_cflag |= CS8;

    tio.c_lflag &= ~(ICANON | ECHO | ECHOE | ISIG);
    tio.c_iflag &= ~(IXON | IXOFF | IXANY | IGNBRK | BRKINT | PARMRK | ISTRIP | INLCR | IGNCR | ICRNL);
    tio.c_oflag &= ~OPOST;

    tio.c_cc[VMIN] = 1;
    tio.c_cc[VTIME] = 0;

    if (tcsetattr(fd, TCSANOW, &tio) != 0) {
        return false;
    }

    tcflush(fd, TCIOFLUSH);
    return true;
}

bool putLongPV(const std::string& pvName, long value)
{
    DBADDR addr;
    if (dbNameToAddr(pvName.c_str(), &addr) != 0) {
        errlogPrintf("rotarySerial: PV not found: %s\n", pvName.c_str());
        return false;
    }

    long nRequest = 1;
    if (dbPutField(&addr, DBR_LONG, &value, nRequest) != 0) {
        errlogPrintf("rotarySerial: dbPutField failed: %s\n", pvName.c_str());
        return false;
    }

    return true;
}

bool isStopRequested()
{
    epicsGuard<epicsMutex> guard(serialReaderMutex);
    return serialThreadStop;
}

void serialReaderThread(void *arg)
{
    SerialThreadConfig *cfg = static_cast<SerialThreadConfig *>(arg);
    const std::string enc1Pv = cfg->pvPrefix + "ENC1:POSITION";
    const std::string enc2Pv = cfg->pvPrefix + "ENC2:POSITION";
    const std::string mtr1Pv = cfg->pvPrefix + "MTR1:POSITION";
    const std::string mtr2Pv = cfg->pvPrefix + "MTR2:POSITION";
    const std::string syncPv = cfg->pvPrefix + "SYNC:MODE";

    const speed_t baud = parseBaud(cfg->baudRate.c_str());
    const char *port = cfg->serialPort.c_str();

    errlogPrintf("rotarySerial: thread started prefix=%s port=%s baud=%s\n",
        cfg->pvPrefix.c_str(), cfg->serialPort.c_str(), cfg->baudRate.c_str());

    while (!isStopRequested()) {
        int fd = open(port, O_RDWR | O_NOCTTY);
        if (fd < 0) {
            errlogPrintf("rotarySerial: open failed (%s): %s\n", port, strerror(errno));
            epicsThreadSleep(1.0);
            continue;
        }

        if (!configureSerialPort(fd, baud)) {
            errlogPrintf("rotarySerial: configure failed (%s): %s\n", port, strerror(errno));
            close(fd);
            epicsThreadSleep(1.0);
            continue;
        }

        errlogPrintf("rotarySerial: serial open/configured (%s)\n", port);

        std::string line;
        line.reserve(128);

        while (!isStopRequested()) {
            char ch = 0;
            ssize_t n = read(fd, &ch, 1);
            if (n <= 0) {
                errlogPrintf("rotarySerial: read ended (%s): %s\n", port, strerror(errno));
                break;
            }

            if (ch == '\r') {
                continue;
            }

            if (ch != '\n') {
                if (line.size() < 256) {
                    line.push_back(ch);
                }
                continue;
            }

            if (line.empty()) {
                continue;
            }

            long enc1 = 0;
            long enc2 = 0;
            long mtr1 = 0;
            long mtr2 = 0;
            long sync = 0;

            if (sscanf(line.c_str(), "ENC1:%ld,ENC2:%ld,MTR1:%ld,MTR2:%ld,SYNC:%ld", &enc1, &enc2, &mtr1, &mtr2, &sync) == 5) {
                putLongPV(enc1Pv, enc1);
                putLongPV(enc2Pv, enc2);
                putLongPV(mtr1Pv, mtr1);
                putLongPV(mtr2Pv, mtr2);
                putLongPV(syncPv, sync);
            }

            line.clear();
        }

        close(fd);
        if (!isStopRequested()) {
            epicsThreadSleep(0.5);
        }
    }

    {
        epicsGuard<epicsMutex> guard(serialReaderMutex);
        serialThreadRunning = false;
        serialThreadId = 0;
    }

    delete cfg;
    errlogPrintf("rotarySerial: thread stopped\n");
}

void stopSerialReader(void *)
{
    epicsGuard<epicsMutex> guard(serialReaderMutex);
    serialThreadStop = true;
}

void rotaryStartSerialReader(const iocshArgBuf *args)
{
    const char *pvPrefix = args[0].sval ? args[0].sval : "RE:ch0:";
    const char *serialPort = args[1].sval ? args[1].sval : "/dev/ttyACM0";
    const char *baudRate = args[2].sval ? args[2].sval : "115200";

    epicsGuard<epicsMutex> guard(serialReaderMutex);

    if (serialThreadRunning) {
        errlogPrintf("rotaryStartSerialReader: serial reader thread already running\n");
        return;
    }

    SerialThreadConfig *cfg = new SerialThreadConfig;
    cfg->pvPrefix = pvPrefix;
    cfg->serialPort = serialPort;
    cfg->baudRate = baudRate;

    serialThreadStop = false;
    serialThreadId = epicsThreadCreate(
        "rotarySerialReader",
        epicsThreadPriorityMedium,
        epicsThreadGetStackSize(epicsThreadStackMedium),
        serialReaderThread,
        cfg);

    if (!serialThreadId) {
        delete cfg;
        serialThreadStop = true;
        serialThreadRunning = false;
        errlogPrintf("rotaryStartSerialReader: failed to create serial reader thread\n");
        return;
    }

    serialThreadRunning = true;
    errlogPrintf("rotaryStartSerialReader: started serial reader thread prefix=%s port=%s baud=%s\n",
        pvPrefix, serialPort, baudRate);
}

static const iocshArg startArg0 = {"pvPrefix", iocshArgString};
static const iocshArg startArg1 = {"serialPort", iocshArgString};
static const iocshArg startArg2 = {"baudRate", iocshArgString};
static const iocshArg * const startArgs[] = {&startArg0, &startArg1, &startArg2};
static const iocshFuncDef startDef = {"rotaryStartSerialReader", 3, startArgs};

void rotarySerialRegistrar(void)
{
    iocshRegister(&startDef, rotaryStartSerialReader);
    epicsAtExit(stopSerialReader, NULL);
}

} // namespace

epicsExportRegistrar(rotarySerialRegistrar);
