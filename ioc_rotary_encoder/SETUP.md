# EPICS IOC Setup Guide

This document explains how to set up and use the EPICS IOC for the Rotary Encoder Dual Stepper system.

## Quick Start

### 1. Prerequisites
- EPICS base installed
- Arduino firmware programmed with `rotary_encoder_dual_stepper.ino`
- Python serial communication module

### 2. Build the IOC

```bash
cd /home/rpi/arduino-apps/ioc_rotary_encoder
make
```

### 3. Run the IOC

```bash
cd iocBoot/iocRotaryEncoder
./st.cmd
```

## Architecture

```
┌─────────────────────────────────────┐
│  Arduino (Rotary Encoder Sketch)   │
│  - Encoder1, Encoder2              │
│  - Motor1, Motor2 positions        │
│  - Serial output @ 115200 baud    │
└──────────────┬──────────────────────┘
               │ (USB Serial)
┌──────────────▼──────────────────────┐
│  Serial Reader (Python/C++)        │
│  - Parse serial data               │
│  - Update EPICS PVs                │
└──────────────┬──────────────────────┘
               │ (CA Protocol)
┌──────────────▼──────────────────────┐
│  EPICS IOC                          │
│  - RE:ch0:ENC1:POSITION            │
│  - RE:ch0:ENC2:POSITION            │
│  - RE:ch0:MTR1:POSITION            │
│  - RE:ch0:MTR2:POSITION            │
│  - RE:ch0:SYNC:MODE                │
└─────────────────────────────────────┘
         │ (CA Clients)
┌────────▼────────────────────────────┐
│  Clients (camonitor, CSS, etc)     │
└─────────────────────────────────────┘
```

## PV Naming Convention

- **Prefix**: `RE:ch0:` (Rotary Encoder, Channel 0)
- **Subsystem**: `ENC1`, `ENC2` (Encoders), `MTR1`, `MTR2` (Motors)
- **Suffix**: `:POSITION`, `:FREQ`, `:SYNC`

## Serial Data Format

The Arduino sends data in CSV format:

```
ENC1:120,ENC2:-45,MTR1:2400,MTR2:1500,SYNC:0
```

### Parsing Rules
- Split by `,` to get key-value pairs
- Split by `:` to extract key and value
- Update corresponding EPICS PV

## Python Serial Monitor

You can use this Python script to verify serial communication:

```python
import serial
import time

port = "/dev/ttyUSB0"
baudrate = 115200

try:
    ser = serial.Serial(port, baudrate, timeout=1)
    print(f"Connected to {port} at {baudrate} baud")
    
    while True:
        if ser.in_waiting > 0:
            line = ser.readline().decode('utf-8').strip()
            print(f"[{time.strftime('%H:%M:%S')}] {line}")
            
except KeyboardInterrupt:
    print("Interrupted")
except Exception as e:
    print(f"Error: {e}")
finally:
    if 'ser' in locals() and ser.is_open:
        ser.close()
```

## Testing the IOC

### 1. Check if IOC is running
```bash
caget RE:ch0:STATUS
```

### 2. Monitor encoder position
```bash
camonitor RE:ch0:ENC1:POSITION
```

### 3. Monitor motor position
```bash
camonitor RE:ch0:MTR1:POSITION RE:ch0:MTR2:POSITION
```

### 4. Get all PV values
```bash
caget RE:ch0:*
```

## Customization

### Change Serial Port
Edit `iocBoot/iocRotaryEncoder/st.cmd`:
```bash
epicsEnvSet("SERIAL_PORT", "/dev/ttyUSB1")
```

### Change PV Prefix
Edit `st.cmd`:
```bash
epicsEnvSet("P", "MYPREFIX:")
```

### Add New PVs
Edit `RotaryEncoderApp/Db/RotaryEncoder.db` and add new records.

## Integrating with EPICS Archiver

Create an `ArchiveInfo.xml` file:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<engineconfig>
    <group name="rotary_encoder">
        <channel name="RE:ch0:ENC1:POSITION" />
        <channel name="RE:ch0:ENC2:POSITION" />
        <channel name="RE:ch0:MTR1:POSITION" />
        <channel name="RE:ch0:MTR2:POSITION" />
        <channel name="RE:ch0:SYNC:MODE" />
    </group>
</engineconfig>
```

## Next Steps

1. **Program Arduino** with `rotary_encoder_dual_stepper.ino`
2. **Verify Serial Connection**: `screen /dev/ttyUSB0 115200`
3. **Build IOC**: `make` in ioc_rotary_encoder directory
4. **Start IOC**: Run startup script
5. **Monitor PVs**: Use `camonitor` or CSS/PyEpics

## Troubleshooting Checklist

- [ ] Arduino is programmed and connected
- [ ] Serial port is correct in st.cmd
- [ ] EPICS base is installed
- [ ] IOC builds without errors
- [ ] IOC starts without errors
- [ ] `caget RE:ch0:STATUS` returns a value
- [ ] Serial data is being received (check with screen/minicom)
