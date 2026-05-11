/* RotaryEncoderMain.cpp - Main IOC application for Rotary Encoder Dual Stepper */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "iocsh.h"
#include "epicsThread.h"
#include "epicsExit.h"
#include "epicsVersion.h"
#include "errlog.h"

extern "C" {
    int RotaryEncoder_registerRecordDeviceSupport(void);
}

int main(int argc, char *argv[])
{
    if (argc < 2)
    {
        fprintf(stderr, "Usage: %s st.cmd\n", argv[0]);
        fprintf(stderr, "  st.cmd = startup script\n");
        epicsThreadSleep(.2);
        exit(1);
    }

    iocshPrepare();

    if (iocshLoad(argv[1], NULL) == 0)
    {
        iocshCmd("iocInit()");
        iocshLoop(); /* This function never returns */
    }
    else
    {
        exit(1);
    }

    return 0;
}
