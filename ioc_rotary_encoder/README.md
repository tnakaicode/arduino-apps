# EPICS IOC for Rotary Encoder Dual Stepper System

This directory contains the EPICS Input/Output Controller (IOC) for controlling and monitoring the Rotary Encoder Dual Stepper motor system.

## Directory Structure

```
ioc_rotary_encoder/
├── RotaryEncoderApp/         # EPICS application
│   ├── src/                   # Source code and Makefile
│   │   ├── RotaryEncoderMain.cpp
│   │   └── Makefile
│   └── Db/                    # Database files
│       ├── RotaryEncoder.db   # PV record definitions
│       └── Makefile
├── iocBoot/                   # Boot scripts
│   └── iocRotaryEncoder/
│       ├── st.cmd             # Startup command script
│       ├── envPaths            # Environment paths
│       └── Makefile
└── configure/                 # Build configuration
    └── CONFIG
```

## Process Variables (PVs)

The IOC exposes the following PVs (prefix: `RE:ch0:`):

### Encoder Positions
- `RE:ch0:ENC1:POSITION` - Encoder 1 position (clicks)
- `RE:ch0:ENC2:POSITION` - Encoder 2 position (clicks)

### Motor Positions
- `RE:ch0:MTR1:POSITION` - Motor 1 current position (steps)
- `RE:ch0:MTR2:POSITION` - Motor 2 current position (steps)

### Encoder Frequencies
- `RE:ch0:ENC1:FREQ` - Encoder 1 frequency (Hz)
- `RE:ch0:ENC2:FREQ` - Encoder 2 frequency (Hz)

### System Status
- `RE:ch0:SYNC:MODE` - Synchronization mode status (Motor1 Only / Motor1+Motor2 Sync)
- `RE:ch0:STATUS` - IOC status message
- `RE:ch0:UPTIME` - IOC uptime (seconds)

## Building the IOC

### Prerequisites
- EPICS base installed at `/opt/epics/base`
- GNU build tools (make, gcc, g++)
- Arduino serial communication library

### Build Steps

```bash
cd /home/rpi/arduino-apps/ioc_rotary_encoder
make
```

## Running the IOC

### Using the startup script
```bash
cd ./iocBoot/iocRotaryEncoder
./st.cmd
```

### Starting manually
```bash
cd ./iocBoot/iocRotaryEncoder
source ./envPaths
RotaryEncoder st.cmd
```

## Arduino Firmware Communication

The IOC communicates with the Arduino running `rotary_encoder_dual_stepper.ino` via serial port (default: `/dev/ttyUSB0` at 115200 baud).

### Serial Protocol

The Arduino sends position updates in the format:
```
ENC1:<pos>,ENC2:<pos>,MTR1:<pos>,MTR2:<pos>,SYNC:<mode>
```

Example:
```
ENC1:120,ENC2:-45,MTR1:2400,MTR2:1500,SYNC:0
```

## Hardware Requirements

- Arduino Uno/Mega with dual rotary encoders and stepper motors
- USB-to-Serial adapter (for communication with IOC)
- Proper power supply for stepper motors

## Configuration

Edit the following files to customize:

- **Serial Port**: Edit `iocBoot/iocRotaryEncoder/st.cmd` line with `SERIAL_PORT`
- **PV Prefix**: Edit `st.cmd` to change `epicsEnvSet("P", "RE:")` 
- **PV Records**: Edit `RotaryEncoderApp/Db/RotaryEncoder.db` to add/modify PVs

## Monitoring PVs with EPICS Tools

```bash
# List all IOC PVs
caget RE:ch0:*

# Monitor encoder 1 position
camonitor RE:ch0:ENC1:POSITION

# Read motor 1 position
caget RE:ch0:MTR1:POSITION

# Watch all updates
camonitor RE:ch0:ENC1:POSITION RE:ch0:ENC2:POSITION RE:ch0:MTR1:POSITION RE:ch0:MTR2:POSITION
```

## Troubleshooting

### Serial port not found
- Check device connection: `ls -la /dev/ttyUSB*`
- Verify Arduino is programmed with the stepper sketch
- Check baud rate matches (115200)

### PVs not updating
- Verify IOC is running: `caget RE:ch0:STATUS`
- Check serial communication: `screen /dev/ttyUSB0 115200`
- Verify Arduino firmware is sending data

### EPICS not installed
- Install EPICS base: [EPICS Wiki](https://epics.anl.gov/)
- Update path in `configure/CONFIG`

## References

- [EPICS Documentation](https://epics-controls.org/)
- [EPICS Database Reference](https://epics.anl.gov/base/R3-15/8-docs/DBD.html)
- [Arduino AccelStepper Library](http://www.airspayce.com/mikem/arduino/AccelStepper/)

```bash
mkdir -p /home/rpi/.config/systemd/user
cat > /home/rpi/.config/systemd/user/rotary-ioc.service <<'EOF'
[Unit]
Description=Rotary Encoder EPICS IOC
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/rpi/arduino-apps/ioc_rotary_encoder/iocBoot/iocRotaryEncoder
ExecStart=/bin/bash -lc 'exec ./st.cmd'
Restart=always
RestartSec=2
StandardOutput=append:/home/rpi/arduino-apps/ioc_rotary_encoder/iocBoot/iocRotaryEncoder/ioc.log
StandardError=append:/home/rpi/arduino-apps/ioc_rotary_encoder/iocBoot/iocRotaryEncoder/ioc.log

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable rotary-ioc.service
systemctl --user restart rotary-ioc.service
systemctl --user status rotary-ioc.service --no-pager -n 20


loginctl show-user rpi -p Linger



systemctl --user is-enabled rotary-ioc.service; systemctl --user is-active rotary-ioc.service

systemctl --user status rotary-ioc.service
```
