#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <termios.h>
#include <unistd.h>

#include <string>
#include <sstream>

#include "dbAccess.h"
#include "epicsExit.h"
#include "epicsExport.h"
#include "epicsMutex.h"
#include "epicsThread.h"
#include "epicsTime.h"
#include "epicsTypes.h"
#include "errlog.h"
#include "iocsh.h"

namespace {

const char *kPersistentStateFile = "rotary_state.dat";

struct PersistentState {
    long mtr1Set;
    long mtr2Set;
    long rpm1Set;
    long rpm2Set;
};

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

    epicsInt32 v = static_cast<epicsInt32>(value);
    long nRequest = 1;
    if (dbPutField(&addr, DBR_LONG, &v, nRequest) != 0) {
        errlogPrintf("rotarySerial: dbPutField failed: %s\n", pvName.c_str());
        return false;
    }

    return true;
}

bool getLongPV(const std::string& pvName, long *value)
{
    DBADDR addr;
    if (dbNameToAddr(pvName.c_str(), &addr) != 0) {
        errlogPrintf("rotarySerial: PV not found: %s\n", pvName.c_str());
        return false;
    }

    dbScanLock(addr.precord);
    epicsInt32 v = *static_cast<epicsInt32 *>(addr.pfield);
    dbScanUnlock(addr.precord);
    *value = static_cast<long>(v);

    return true;
}

bool writeSerialLine(int fd, const std::string& line)
{
    const char *ptr = line.c_str();
    size_t remaining = line.size();
    while (remaining > 0) {
        ssize_t n = write(fd, ptr, remaining);
        if (n < 0) {
            if (errno == EINTR) {
                continue;
            }
            return false;
        }
        ptr += n;
        remaining -= static_cast<size_t>(n);
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

bool loadPersistentState(PersistentState *state)
{
    FILE *fp = fopen(kPersistentStateFile, "r");
    if (!fp) {
        return false;
    }

    long m1 = 0;
    long m2 = 0;
    long r1 = 0;
    long r2 = 0;
    int n = fscanf(fp, "%ld %ld %ld %ld", &m1, &m2, &r1, &r2);
    fclose(fp);
    if (n != 4) {
        return false;
    }

    state->mtr1Set = m1;
    state->mtr2Set = m2;
    state->rpm1Set = r1;
    state->rpm2Set = r2;
    return true;
}

void savePersistentState(const PersistentState& state)
{
    const char *tmpFile = "rotary_state.dat.tmp";
    FILE *fp = fopen(tmpFile, "w");
    if (!fp) {
        errlogPrintf("rotarySerial: failed to open persistent state tmp file\n");
        return;
    }

    fprintf(fp, "%ld %ld %ld %ld\n",
        state.mtr1Set, state.mtr2Set, state.rpm1Set, state.rpm2Set);
    fclose(fp);

    if (rename(tmpFile, kPersistentStateFile) != 0) {
        errlogPrintf("rotarySerial: failed to rename persistent state file: %s\n", strerror(errno));
    }
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
    const std::string mtr1SetPv = cfg->pvPrefix + "MTR1:SETPOINT";
    const std::string mtr2SetPv = cfg->pvPrefix + "MTR2:SETPOINT";
    const std::string mtr1RpmSetPv = cfg->pvPrefix + "MTR1:RPM_SET";
    const std::string mtr2RpmSetPv = cfg->pvPrefix + "MTR2:RPM_SET";
    const std::string mtr1RpmFbPv = cfg->pvPrefix + "MTR1:RPM_FB";
    const std::string mtr2RpmFbPv = cfg->pvPrefix + "MTR2:RPM_FB";
    const std::string connectedPv = cfg->pvPrefix + "ARDUINO:CONNECTED";
    const std::string linesPerSecPv = cfg->pvPrefix + "ARDUINO:LINES_PER_SEC";
    const std::string parseOkPv = cfg->pvPrefix + "ARDUINO:PARSE_OK";
    const std::string parseErrPv = cfg->pvPrefix + "ARDUINO:PARSE_ERR";
    const std::string reconnectsPv = cfg->pvPrefix + "ARDUINO:RECONNECTS";
    const std::string lastRxMsPv = cfg->pvPrefix + "ARDUINO:LAST_RX_MS";
    const std::string loopHzPv = cfg->pvPrefix + "ARDUINO:LOOP_HZ";
    const std::string loopMsPv = cfg->pvPrefix + "ARDUINO:LOOP_MS";
    const std::string loopUsPv = cfg->pvPrefix + "ARDUINO:LOOP_US";
    const std::string lightRawPv = cfg->pvPrefix + "ARDUINO:LIGHT_RAW";
    const std::string uptimeMsPv = cfg->pvPrefix + "ARDUINO:UPTIME_MS";

    const speed_t baud = parseBaud(cfg->baudRate.c_str());
    const char *port = cfg->serialPort.c_str();

    long parseOk = 0;
    long parseErr = 0;
    long reconnects = 0;
    long linesWindow = 0;
    long lastCmdMtr1 = 0;
    long lastCmdMtr2 = 0;
    long lastCmdRpm1 = 0;
    long lastCmdRpm2 = 0;
    PersistentState persisted = {0, 0, 0, 0};
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
    putLongPV(lightRawPv, 0);
    putLongPV(uptimeMsPv, 0);
    putLongPV(mtr1RpmFbPv, 0);
    putLongPV(mtr2RpmFbPv, 0);

    if (loadPersistentState(&persisted)) {
        putLongPV(mtr1SetPv, persisted.mtr1Set);
        putLongPV(mtr2SetPv, persisted.mtr2Set);
        putLongPV(mtr1RpmSetPv, persisted.rpm1Set);
        putLongPV(mtr2RpmSetPv, persisted.rpm2Set);
        errlogPrintf("rotarySerial: restored state M1=%ld M2=%ld R1=%ld R2=%ld\n",
            persisted.mtr1Set, persisted.mtr2Set, persisted.rpm1Set, persisted.rpm2Set);
    }

    getLongPV(mtr1SetPv, &lastCmdMtr1);
    getLongPV(mtr2SetPv, &lastCmdMtr2);
    getLongPV(mtr1RpmSetPv, &lastCmdRpm1);
    getLongPV(mtr2RpmSetPv, &lastCmdRpm2);

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

        {
            std::ostringstream cmd1;
            cmd1 << "SET:MTR1:" << lastCmdMtr1 << "\n";
            if (writeSerialLine(fd, cmd1.str())) {
                errlogPrintf("rotarySerial: sent %s", cmd1.str().c_str());
            }

            std::ostringstream cmd2;
            cmd2 << "SET:MTR2:" << lastCmdMtr2 << "\n";
            if (writeSerialLine(fd, cmd2.str())) {
                errlogPrintf("rotarySerial: sent %s", cmd2.str().c_str());
            }

            std::ostringstream cmd3;
            cmd3 << "SET:RPM1:" << lastCmdRpm1 << "\n";
            if (writeSerialLine(fd, cmd3.str())) {
                errlogPrintf("rotarySerial: sent %s", cmd3.str().c_str());
            }

            std::ostringstream cmd4;
            cmd4 << "SET:RPM2:" << lastCmdRpm2 << "\n";
            if (writeSerialLine(fd, cmd4.str())) {
                errlogPrintf("rotarySerial: sent %s", cmd4.str().c_str());
            }
        }

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

            long mtr1Set = lastCmdMtr1;
            long mtr2Set = lastCmdMtr2;
            if (getLongPV(mtr1SetPv, &mtr1Set) && mtr1Set != lastCmdMtr1) {
                std::ostringstream cmd;
                cmd << "SET:MTR1:" << mtr1Set << "\n";
                if (writeSerialLine(fd, cmd.str())) {
                    lastCmdMtr1 = mtr1Set;
                    persisted.mtr1Set = lastCmdMtr1;
                    persisted.mtr2Set = lastCmdMtr2;
                    persisted.rpm1Set = lastCmdRpm1;
                    persisted.rpm2Set = lastCmdRpm2;
                    savePersistentState(persisted);
                    errlogPrintf("rotarySerial: sent %s", cmd.str().c_str());
                }
            }
            if (getLongPV(mtr2SetPv, &mtr2Set) && mtr2Set != lastCmdMtr2) {
                std::ostringstream cmd;
                cmd << "SET:MTR2:" << mtr2Set << "\n";
                if (writeSerialLine(fd, cmd.str())) {
                    lastCmdMtr2 = mtr2Set;
                    persisted.mtr1Set = lastCmdMtr1;
                    persisted.mtr2Set = lastCmdMtr2;
                    persisted.rpm1Set = lastCmdRpm1;
                    persisted.rpm2Set = lastCmdRpm2;
                    savePersistentState(persisted);
                    errlogPrintf("rotarySerial: sent %s", cmd.str().c_str());
                }
            }

            long rpm1Set = lastCmdRpm1;
            long rpm2Set = lastCmdRpm2;
            if (getLongPV(mtr1RpmSetPv, &rpm1Set) && rpm1Set != lastCmdRpm1) {
                std::ostringstream cmd;
                cmd << "SET:RPM1:" << rpm1Set << "\n";
                if (writeSerialLine(fd, cmd.str())) {
                    lastCmdRpm1 = rpm1Set;
                    persisted.mtr1Set = lastCmdMtr1;
                    persisted.mtr2Set = lastCmdMtr2;
                    persisted.rpm1Set = lastCmdRpm1;
                    persisted.rpm2Set = lastCmdRpm2;
                    savePersistentState(persisted);
                    errlogPrintf("rotarySerial: sent %s", cmd.str().c_str());
                }
            }
            if (getLongPV(mtr2RpmSetPv, &rpm2Set) && rpm2Set != lastCmdRpm2) {
                std::ostringstream cmd;
                cmd << "SET:RPM2:" << rpm2Set << "\n";
                if (writeSerialLine(fd, cmd.str())) {
                    lastCmdRpm2 = rpm2Set;
                    persisted.mtr1Set = lastCmdMtr1;
                    persisted.mtr2Set = lastCmdMtr2;
                    persisted.rpm1Set = lastCmdRpm1;
                    persisted.rpm2Set = lastCmdRpm2;
                    savePersistentState(persisted);
                    errlogPrintf("rotarySerial: sent %s", cmd.str().c_str());
                }
            }

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
                long lightRaw = 0;
                if (extractTaggedLong(line, ",LIGHT_RAW:", &lightRaw)) {
                    putLongPV(lightRawPv, lightRaw);
                }
                if (extractTaggedLong(line, ",UPTIME_MS:", &uptimeMs)) {
                    putLongPV(uptimeMsPv, uptimeMs);
                }
                long rpm1Fb = 0;
                long rpm2Fb = 0;
                if (extractTaggedLong(line, ",RPM1:", &rpm1Fb)) {
                    putLongPV(mtr1RpmFbPv, rpm1Fb);
                }
                if (extractTaggedLong(line, ",RPM2:", &rpm2Fb)) {
                    putLongPV(mtr2RpmFbPv, rpm2Fb);
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
