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
#include "epicsTime.h"
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

bool putBoolPV(const std::string& pvName, bool value)
{
    DBADDR addr;
    if (dbNameToAddr(pvName.c_str(), &addr) != 0) {
        errlogPrintf("rotarySerial: PV not found: %s\n", pvName.c_str());
        return false;
    }

    short v = value ? 1 : 0;
    long nRequest = 1;
    if (dbPutField(&addr, DBR_SHORT, &v, nRequest) != 0) {
        errlogPrintf("rotarySerial: dbPutField failed: %s\n", pvName.c_str());
        return false;
    }

    return true;
}

bool extractTaggedLong(const std::string& line, const char *tag, long *out)
{
    const char *start = strstr(line.c_str(), tag);
    if (!start) {
        return false;
    }

    start += strlen(tag);
    char *endPtr = NULL;
    long v = strtol(start, &endPtr, 10);
    if (endPtr == start) {
        return false;
    }

    *out = v;
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
    const std::string connectedPv = cfg->pvPrefix + "ARDUINO:CONNECTED";
    const std::string linesPerSecPv = cfg->pvPrefix + "ARDUINO:LINES_PER_SEC";
    const std::string parseOkPv = cfg->pvPrefix + "ARDUINO:PARSE_OK";
    const std::string parseErrPv = cfg->pvPrefix + "ARDUINO:PARSE_ERR";
    const std::string reconnectsPv = cfg->pvPrefix + "ARDUINO:RECONNECTS";
    const std::string lastRxMsPv = cfg->pvPrefix + "ARDUINO:LAST_RX_MS";
    const std::string loopHzPv = cfg->pvPrefix + "ARDUINO:LOOP_HZ";
    const std::string loopMsPv = cfg->pvPrefix + "ARDUINO:LOOP_MS";
    const std::string loopUsPv = cfg->pvPrefix + "ARDUINO:LOOP_US";
    const std::string uptimeMsPv = cfg->pvPrefix + "ARDUINO:UPTIME_MS";

    const speed_t baud = parseBaud(cfg->baudRate.c_str());
    const char *port = cfg->serialPort.c_str();

    long parseOk = 0;
    long parseErr = 0;
    long reconnects = 0;
    long linesWindow = 0;
    epicsTimeStamp lastRateUpdate;
    epicsTimeStamp lastRxTime;
    epicsTimeGetCurrent(&lastRateUpdate);
    lastRxTime = lastRateUpdate;

    putBoolPV(connectedPv, false);
    putLongPV(linesPerSecPv, 0);
    putLongPV(parseOkPv, 0);
    putLongPV(parseErrPv, 0);
    putLongPV(reconnectsPv, 0);
    putLongPV(lastRxMsPv, 0);
    putLongPV(loopHzPv, 0);
    putLongPV(loopMsPv, 0);
    putLongPV(loopUsPv, 0);
    putLongPV(uptimeMsPv, 0);

    errlogPrintf("rotarySerial: thread started prefix=%s port=%s baud=%s\n",
        cfg->pvPrefix.c_str(), cfg->serialPort.c_str(), cfg->baudRate.c_str());

    while (!isStopRequested()) {
        int fd = open(port, O_RDWR | O_NOCTTY);
        if (fd < 0) {
            putBoolPV(connectedPv, false);
            putLongPV(linesPerSecPv, 0);
            errlogPrintf("rotarySerial: open failed (%s): %s\n", port, strerror(errno));
            epicsThreadSleep(1.0);
            continue;
        }

        if (!configureSerialPort(fd, baud)) {
            putBoolPV(connectedPv, false);
            putLongPV(linesPerSecPv, 0);
            errlogPrintf("rotarySerial: configure failed (%s): %s\n", port, strerror(errno));
            close(fd);
            epicsThreadSleep(1.0);
            continue;
        }

        reconnects++;
        putLongPV(reconnectsPv, reconnects);
        putBoolPV(connectedPv, true);
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

            if (line.rfind("ENC1:", 0) != 0) {
                line.clear();
                continue;
            }

            epicsTimeStamp now;
            epicsTimeGetCurrent(&now);
            long rxMs = static_cast<long>(epicsTimeDiffInSeconds(&now, &lastRxTime) * 1000.0);
            if (rxMs < 0) {
                rxMs = 0;
            }
            lastRxTime = now;
            linesWindow++;

            long enc1 = 0;
            long enc2 = 0;
            long mtr1 = 0;
            long mtr2 = 0;
            long sync = 0;

            if (sscanf(line.c_str(), "ENC1:%ld,ENC2:%ld,MTR1:%ld,MTR2:%ld,SYNC:%ld", &enc1, &enc2, &mtr1, &mtr2, &sync) == 5) {
                parseOk++;
                putLongPV(enc1Pv, enc1);
                putLongPV(enc2Pv, enc2);
                putLongPV(mtr1Pv, mtr1);
                putLongPV(mtr2Pv, mtr2);
                putLongPV(syncPv, sync);
                putLongPV(parseOkPv, parseOk);

                long loopHz = 0;
                long loopMs = 0;
                long loopUs = 0;
                long uptimeMs = 0;
                if (extractTaggedLong(line, ",LOOP_HZ:", &loopHz)) {
                    putLongPV(loopHzPv, loopHz);
                }
                if (extractTaggedLong(line, ",LOOP_MS:", &loopMs)) {
                    putLongPV(loopMsPv, loopMs);
                }
                if (extractTaggedLong(line, ",LOOP_US:", &loopUs)) {
                    putLongPV(loopUsPv, loopUs);
                }
                if (extractTaggedLong(line, ",UPTIME_MS:", &uptimeMs)) {
                    putLongPV(uptimeMsPv, uptimeMs);
                }
            } else {
                parseErr++;
                putLongPV(parseErrPv, parseErr);
            }

            putLongPV(lastRxMsPv, rxMs);

            double rateDt = epicsTimeDiffInSeconds(&now, &lastRateUpdate);
            if (rateDt >= 1.0) {
                long rate = static_cast<long>((static_cast<double>(linesWindow) / rateDt) + 0.5);
                putLongPV(linesPerSecPv, rate);
                linesWindow = 0;
                lastRateUpdate = now;
            }

            line.clear();
        }

        putBoolPV(connectedPv, false);
        putLongPV(linesPerSecPv, 0);
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
