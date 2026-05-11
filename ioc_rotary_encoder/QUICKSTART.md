# Quick Start Guide - EPICS IOC for Rotary Encoder Dual Stepper

## Installation

### 1. Install Dependencies

```bash
# Install EPICS client libraries
sudo apt-get update
sudo apt-get install -y epics-dev epics-clients

# Install Python dependencies
pip install pyserial pyepics
```

### 2. Verify Arduino Setup

Connect your Arduino with the `rotary_encoder_dual_stepper.ino` firmware:

```bash
ls -la /dev/ttyUSB*
```

You should see a device like `/dev/ttyUSB0`.

### 3. Test Serial Communication

Run the serial monitor to verify the Arduino is working:

```bash
cd /home/rpi/arduino-apps/ioc_rotary_encoder
chmod +x RotaryEncoderApp/src/serial_monitor.py
./RotaryEncoderApp/src/serial_monitor.py --port /dev/ttyUSB0 --log test.log
```

You should see output like:
```
[12:34:56.789] ENC1:120,ENC2:-45,MTR1:2400,MTR2:1500,SYNC:0
  ENC1:    120
  ENC2:    -45
  MTR1:   2400
  MTR2:   1500
  SYNC:      0
```

Press Ctrl+C to stop. Check `test.log` for the full session.

## Running the IOC

### Option 1: Manual Start (Recommended for Testing)

```bash
cd /home/rpi/arduino-apps/ioc_rotary_encoder
python3 RotaryEncoderApp/src/rotary_encoder_ioc.py --port /dev/ttyUSB0 --prefix RE:ch0:
```

You should see:
```
INFO - Connected to /dev/ttyUSB0 at 115200 baud
INFO - Rotary Encoder IOC started
INFO - PV Prefix: RE:ch0:
INFO - EPICS integration enabled
INFO - Waiting for serial data...
```

### Option 2: Systemd Service (Recommended for Production)

Install the service:

```bash
sudo cp rotary-encoder-ioc.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable rotary-encoder-ioc
sudo systemctl start rotary-encoder-ioc
```

Check status:
```bash
sudo systemctl status rotary-encoder-ioc
journalctl -u rotary-encoder-ioc -f
```

## Monitoring PVs

### Method 1: Command Line (EPICS Tools)

```bash
# List all available PVs
caget RE:ch0:*

# Monitor encoder position in real-time
camonitor RE:ch0:ENC1:POSITION

# Watch multiple PVs
camonitor RE:ch0:ENC1:POSITION RE:ch0:MTR1:POSITION

# Get a single value
caget RE:ch0:MTR1:POSITION
```

### Method 2: Python (PyEpics)

```python
from epics import PV

# Create PV objects
enc1_pv = PV('RE:ch0:ENC1:POSITION')
mtr1_pv = PV('RE:ch0:MTR1:POSITION')

# Read values
print(f"Encoder 1: {enc1_pv.get()}")
print(f"Motor 1: {mtr1_pv.get()}")

# Monitor changes
def callback(char_value, **kw):
    print(f"Encoder 1 changed to: {char_value}")

enc1_pv.add_callback(callback)
```

### Method 3: Web Dashboard

Install CSS (Control System Studio) or use Web-based EPICS clients.

## Available PVs

| PV Name | Description | Type | Units |
|---------|-------------|------|-------|
| `RE:ch0:ENC1:POSITION` | Encoder 1 position | Long | clicks |
| `RE:ch0:ENC2:POSITION` | Encoder 2 position | Long | clicks |
| `RE:ch0:MTR1:POSITION` | Motor 1 current position | Long | steps |
| `RE:ch0:MTR2:POSITION` | Motor 2 current position | Long | steps |
| `RE:ch0:ENC1:FREQ` | Encoder 1 frequency | Float | Hz |
| `RE:ch0:ENC2:FREQ` | Encoder 2 frequency | Float | Hz |
| `RE:ch0:SYNC:MODE` | Sync mode (0=Motor1 only, 1=Dual) | Binary | - |
| `RE:ch0:STATUS` | IOC status message | String | - |
| `RE:ch0:UPTIME` | IOC uptime | Float | seconds |

## Troubleshooting

### Serial port not found
```bash
# Check device
ls -la /dev/ttyUSB*

# Check permissions
sudo usermod -a -G dialout $USER
# Need to logout and login for changes to take effect
```

### No data in PVs
```bash
# Check if IOC is running
systemctl status rotary-encoder-ioc

# View logs
journalctl -u rotary-encoder-ioc -n 50

# Test serial directly
./RotaryEncoderApp/src/serial_monitor.py
```

### EPICS tools not found
```bash
# Install EPICS clients
sudo apt-get install epics-clients

# Or set EPICS path
export PATH="/opt/epics/base/bin/linux-x86_64:$PATH"
export LD_LIBRARY_PATH="/opt/epics/base/lib/linux-x86_64:$LD_LIBRARY_PATH"
```

### pyepics not installed
```bash
pip install pyepics

# Or with sudo if system-wide
sudo pip install pyepics
```

## Customization

### Change Serial Port

Edit systemd service or command line:

```bash
# Command line
python3 RotaryEncoderApp/src/rotary_encoder_ioc.py --port /dev/ttyUSB1

# Systemd service: edit /etc/systemd/system/rotary-encoder-ioc.service
# Change: ExecStart=/usr/bin/python3 ... --port /dev/ttyUSB1
```

### Change PV Prefix

```bash
# Command line
python3 RotaryEncoderApp/src/rotary_encoder_ioc.py --prefix MY:

# This creates PVs like MY:ENC1:POSITION, MY:MTR1:POSITION, etc.
```

### Modify PV Records

Edit `RotaryEncoderApp/Db/RotaryEncoder.db` to add/modify PV definitions:

```db
record(longin, "$(P)$(R)CUSTOM:PV")
{
    field(DESC, "Custom PV Description")
    field(DTYP, "Raw Soft Channel")
    field(SCAN, "I/O Intr")
}
```

## Next Steps

1. **Archive Data**: Set up EPICS archiver to save PV history
2. **Create OPI Screens**: Design control system displays with CSS
3. **Add Alarms**: Configure alarm limits and notifications
4. **Control Motors**: Implement motor control PVs to command positions
5. **Data Logging**: Export PV data for analysis

## Support

- EPICS Documentation: https://epics-controls.org/
- PyEpics: https://pyepics.github.io/
- Arduino AccelStepper: http://www.airspayce.com/mikem/arduino/AccelStepper/

## Log Location

- Service logs: `journalctl -u rotary-encoder-ioc`
- Application logs: `/home/rpi/arduino-apps/ioc_rotary_encoder/rotary_encoder_ioc.log`
