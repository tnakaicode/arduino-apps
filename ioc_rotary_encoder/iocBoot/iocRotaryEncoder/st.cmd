#!/bin/bash
# Startup script for Rotary Encoder Dual Stepper IOC

# Get environment paths
. ./envPaths

# Set IOC name and prefix
epicsEnvSet("IOCNAME", "IOC-RotaryEncoder")
epicsEnvSet("P", "RE:")
epicsEnvSet("R", "ch0:")

# Serial port for Arduino communication
epicsEnvSet("SERIAL_PORT", "/dev/ttyUSB0")
epicsEnvSet("BAUD_RATE", "115200")

# Register all record types
cd "${TOP}/dbd"
dbLoadDatabase "RotaryEncoder.dbd"
RotaryEncoder_registerRecordDeviceSupport

cd "${APPDIR}"

# Load the database
dbLoadRecords "${TOP}/db/RotaryEncoder.db", "P=${P}, R=${R}"

# IOC initialization
iocInit

# Start sequence
seq "rotaryEncoder", "P=${P}, R=${R}"

# Dbl - list all records
dbl

# Leave caShell running
caShell
