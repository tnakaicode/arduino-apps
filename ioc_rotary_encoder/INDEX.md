# EPICS IOC for Rotary Encoder - File Index

## Documentation Files

### Start Here
- **[QUICKSTART.md](QUICKSTART.md)** ⭐
  - 5-minute quick start guide
  - Installation steps
  - How to run the IOC
  - Basic troubleshooting

### Comprehensive Guides
- **[OVERVIEW.md](OVERVIEW.md)**
  - System architecture overview
  - Complete PV reference
  - Integration examples
  - Performance characteristics

- **[README.md](README.md)**
  - Detailed documentation
  - Directory structure
  - PV descriptions
  - Build instructions
  - Monitoring examples

- **[SETUP.md](SETUP.md)**
  - Detailed setup instructions
  - Architecture diagrams
  - Serial protocol documentation
  - Python serial monitor script
  - Archiver integration guide

## Source Code Files

### Python IOC (RECOMMENDED ⭐)
- **[RotaryEncoderApp/src/rotary_encoder_ioc.py](RotaryEncoderApp/src/rotary_encoder_ioc.py)**
  - Main Python IOC application
  - Reads Arduino serial data
  - Updates EPICS PVs
  - 10Hz update rate
  - Easy to install and run

### Arduino Firmware
- **[RotaryEncoderApp/src/rotary_encoder_dual_stepper_epics.ino](RotaryEncoderApp/src/rotary_encoder_dual_stepper_epics.ino)**
  - Modified Arduino sketch for EPICS output
  - Outputs: `ENC1:value,ENC2:value,MTR1:value,MTR2:value,SYNC:value`
  - 115200 baud serial output
  - **Upload this to your Arduino board**

### Diagnostic Tools
- **[RotaryEncoderApp/src/serial_monitor.py](RotaryEncoderApp/src/serial_monitor.py)**
  - Serial port monitor/debugger
  - Verifies Arduino is working
  - Logs serial data to file
  - Usage: `python3 serial_monitor.py --port /dev/ttyUSB0`

### EPICS IOC Components (C++)
- **[RotaryEncoderApp/src/RotaryEncoderMain.cpp](RotaryEncoderApp/src/RotaryEncoderMain.cpp)**
  - Traditional EPICS IOC main program
  - For full EPICS installations
  - Optional - use Python version instead

- **[RotaryEncoderApp/Db/RotaryEncoder.db](RotaryEncoderApp/Db/RotaryEncoder.db)**
  - EPICS database file
  - Defines all PV records
  - Specifies PV types, ranges, units
  - Editable for customization

- **[RotaryEncoderApp/Db/RotaryEncoder.dbd](RotaryEncoderApp/Db/RotaryEncoder.dbd)**
  - Database definition file
  - Registers device support
  - For full EPICS builds

## Configuration Files

### Startup Scripts
- **[iocBoot/iocRotaryEncoder/st.cmd](iocBoot/iocRotaryEncoder/st.cmd)**
  - EPICS startup command script
  - Sets environment variables
  - Loads database records
  - For full EPICS IOC only

- **[iocBoot/iocRotaryEncoder/envPaths](iocBoot/iocRotaryEncoder/envPaths)**
  - EPICS environment paths
  - Sets EPICS_BASE, TOP paths
  - For full EPICS IOC only

### System Configuration
- **[rotary-encoder-ioc.service](rotary-encoder-ioc.service)**
  - Systemd service file
  - Automatic startup on boot
  - Daemon mode operation
  - Install to `/etc/systemd/system/`

### Build Configuration
- **[configure/CONFIG](configure/CONFIG)**
  - Build system configuration
  - Compiler settings
  - EPICS paths
  - For full EPICS builds only

- **[RotaryEncoderApp/src/Makefile](RotaryEncoderApp/src/Makefile)**
  - Makefile for C++ IOC
  - For full EPICS builds only

- **[RotaryEncoderApp/Db/Makefile](RotaryEncoderApp/Db/Makefile)**
  - Makefile for database files
  - For full EPICS builds only

- **[Makefile](Makefile)**
  - Top-level Makefile
  - For full EPICS builds only

## File Organization Summary

```
ioc_rotary_encoder/
│
├─ Documentation (Start here!)
│  ├─ QUICKSTART.md ⭐ (5-minute setup)
│  ├─ OVERVIEW.md (architecture & overview)
│  ├─ SETUP.md (detailed setup)
│  ├─ README.md (full reference)
│  └─ INDEX.md (this file)
│
├─ Python IOC (RECOMMENDED) ⭐
│  └─ RotaryEncoderApp/src/rotary_encoder_ioc.py
│
├─ Arduino Firmware
│  └─ RotaryEncoderApp/src/rotary_encoder_dual_stepper_epics.ino
│
├─ Tools
│  └─ RotaryEncoderApp/src/serial_monitor.py
│
├─ EPICS Components (Optional)
│  ├─ RotaryEncoderApp/
│  │  ├─ src/ (RotaryEncoderMain.cpp, Makefile)
│  │  └─ Db/ (RotaryEncoder.db, RotaryEncoder.dbd, Makefile)
│  ├─ iocBoot/ (st.cmd, envPaths, Makefile)
│  └─ configure/ (CONFIG)
│
└─ System Files
   ├─ rotary-encoder-ioc.service
   └─ Makefile
```

## Quick Reference

### Recommended Workflow

1. **📖 Read Documentation**
   ```
   QUICKSTART.md → OVERVIEW.md → README.md
   ```

2. **🔧 Setup Hardware**
   - Upload `rotary_encoder_dual_stepper_epics.ino` to Arduino
   - Connect USB serial cable
   - Verify with: `python3 RotaryEncoderApp/src/serial_monitor.py`

3. **▶️ Start IOC**
   ```bash
   python3 RotaryEncoderApp/src/rotary_encoder_ioc.py --port /dev/ttyUSB0
   ```

4. **📊 Monitor PVs**
   ```bash
   camonitor RE:ch0:ENC1:POSITION RE:ch0:MTR1:POSITION
   ```

5. **🚀 Deploy (Optional)**
   ```bash
   sudo cp rotary-encoder-ioc.service /etc/systemd/system/
   sudo systemctl enable rotary-encoder-ioc
   sudo systemctl start rotary-encoder-ioc
   ```

## Key PVs Reference

| PV | Description | Units |
|----|-------------|-------|
| `RE:ch0:ENC1:POSITION` | Encoder 1 position | clicks |
| `RE:ch0:ENC2:POSITION` | Encoder 2 position | clicks |
| `RE:ch0:MTR1:POSITION` | Motor 1 position | steps |
| `RE:ch0:MTR2:POSITION` | Motor 2 position | steps |
| `RE:ch0:SYNC:MODE` | Sync mode | 0/1 |
| `RE:ch0:STATUS` | IOC status | string |

## Dependencies

### Minimal Setup (Python IOC)
- Python 3.6+
- pyserial (for serial communication)
- pyepics (for EPICS integration)

### Full Setup (EPICS IOC)
- EPICS base
- GCC/G++
- Make
- All minimal dependencies

## File Statistics

| Category | Count |
|----------|-------|
| Documentation | 5 |
| Python files | 3 |
| Arduino sketches | 1 |
| EPICS components | 5 |
| Configuration | 5 |
| **Total** | **19 files** |

## Generated Directory Structure

```
ioc_rotary_encoder/
├── RotaryEncoderApp/
│   ├── Db/
│   │   ├── Makefile
│   │   ├── RotaryEncoder.db
│   │   └── RotaryEncoder.dbd
│   └── src/
│       ├── Makefile
│       ├── RotaryEncoderMain.cpp
│       ├── rotary_encoder_dual_stepper_epics.ino
│       ├── rotary_encoder_ioc.py
│       └── serial_monitor.py
├── configure/
│   └── CONFIG
├── iocBoot/
│   └── iocRotaryEncoder/
│       ├── Makefile
│       ├── envPaths
│       └── st.cmd
├── INDEX.md (this file)
├── Makefile
├── OVERVIEW.md
├── QUICKSTART.md
├── README.md
├── SETUP.md
└── rotary-encoder-ioc.service
```

## Version History

- **v1.0** (2026-05-11)
  - Initial EPICS IOC creation
  - Python IOC implementation
  - Complete documentation
  - Arduino firmware update
  - Systemd service support

## Contact & Support

For issues or questions:
1. Check QUICKSTART.md for common issues
2. Review logs: `tail -f rotary_encoder_ioc.log`
3. Test serial: `python3 RotaryEncoderApp/src/serial_monitor.py`
4. Check EPICS tools: `caget RE:ch0:*`

---

**Last Updated**: 2026-05-11  
**Status**: Production Ready ✓
