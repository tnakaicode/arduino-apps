#!/usr/bin/env python3
"""
Serial Reader for Rotary Encoder Dual Stepper
Reads Arduino serial data and publishes to EPICS PVs
"""

import serial
import time
import threading
import logging
from datetime import datetime
from pathlib import Path

try:
    from epics import PV
    EPICS_AVAILABLE = True
except ImportError:
    EPICS_AVAILABLE = False
    print("Warning: pyepics not installed. Install with: pip install pyepics")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('rotary_encoder_ioc.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class RotaryEncoderIOC:
    def __init__(self, port='/dev/ttyUSB0', baudrate=115200, pv_prefix='RE:ch0:'):
        self.port = port
        self.baudrate = baudrate
        self.pv_prefix = pv_prefix
        self.running = False
        self.ser = None
        
        # Initialize PVs
        self.pvs = {
            'ENC1_POS': PV(f'{pv_prefix}ENC1:POSITION') if EPICS_AVAILABLE else None,
            'ENC2_POS': PV(f'{pv_prefix}ENC2:POSITION') if EPICS_AVAILABLE else None,
            'MTR1_POS': PV(f'{pv_prefix}MTR1:POSITION') if EPICS_AVAILABLE else None,
            'MTR2_POS': PV(f'{pv_prefix}MTR2:POSITION') if EPICS_AVAILABLE else None,
            'ENC1_FREQ': PV(f'{pv_prefix}ENC1:FREQ') if EPICS_AVAILABLE else None,
            'ENC2_FREQ': PV(f'{pv_prefix}ENC2:FREQ') if EPICS_AVAILABLE else None,
            'SYNC_MODE': PV(f'{pv_prefix}SYNC:MODE') if EPICS_AVAILABLE else None,
            'STATUS': PV(f'{pv_prefix}STATUS') if EPICS_AVAILABLE else None,
            'UPTIME': PV(f'{pv_prefix}UPTIME') if EPICS_AVAILABLE else None,
        }
        
        self.start_time = time.time()
        self.last_data = {}
        self.data_lock = threading.Lock()
        
    def connect(self):
        """Connect to Arduino via serial port"""
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            logger.info(f"Connected to {self.port} at {self.baudrate} baud")
            return True
        except serial.SerialException as e:
            logger.error(f"Failed to connect to {self.port}: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from serial port"""
        if self.ser and self.ser.is_open:
            self.ser.close()
            logger.info(f"Disconnected from {self.port}")
    
    def parse_serial_data(self, line):
        """
        Parse Arduino serial output format:
        ENC1:120,ENC2:-45,MTR1:2400,MTR2:1500,SYNC:0
        """
        try:
            data = {}
            pairs = line.strip().split(',')
            
            for pair in pairs:
                if ':' in pair:
                    key, value = pair.split(':')
                    try:
                        data[key.strip()] = int(value.strip())
                    except ValueError:
                        data[key.strip()] = value.strip()
            
            return data
        except Exception as e:
            logger.error(f"Error parsing serial data: {e}")
            return {}
    
    def update_pvs(self, data):
        """Update EPICS PVs with parsed data"""
        if not EPICS_AVAILABLE:
            logger.debug(f"Data: {data}")
            return
        
        mapping = {
            'ENC1': ('ENC1_POS', int),
            'ENC2': ('ENC2_POS', int),
            'MTR1': ('MTR1_POS', int),
            'MTR2': ('MTR2_POS', int),
            'SYNC': ('SYNC_MODE', int),
        }
        
        with self.data_lock:
            for key, (pv_key, dtype) in mapping.items():
                if key in data and pv_key in self.pvs:
                    try:
                        self.pvs[pv_key].put(dtype(data[key]))
                    except Exception as e:
                        logger.error(f"Error updating {pv_key}: {e}")
        
        # Update status and uptime
        if self.pvs['STATUS']:
            self.pvs['STATUS'].put('Running')
        
        if self.pvs['UPTIME']:
            uptime = time.time() - self.start_time
            self.pvs['UPTIME'].put(int(uptime))
    
    def read_serial_loop(self):
        """Main serial reading loop"""
        logger.info("Starting serial read loop")
        self.running = True
        
        while self.running:
            try:
                if self.ser and self.ser.in_waiting > 0:
                    line = self.ser.readline().decode('utf-8', errors='ignore')
                    
                    if line.strip():
                        logger.debug(f"Received: {line.strip()}")
                        data = self.parse_serial_data(line)
                        
                        if data:
                            self.last_data = data
                            self.update_pvs(data)
                
                time.sleep(0.01)  # 10ms polling
                
            except Exception as e:
                logger.error(f"Error in serial read loop: {e}")
                time.sleep(1)  # Retry after 1 second
    
    def start(self):
        """Start the IOC"""
        if not self.connect():
            logger.error("Failed to start IOC")
            return False
        
        # Start serial reading in background thread
        self.read_thread = threading.Thread(target=self.read_serial_loop, daemon=True)
        self.read_thread.start()
        
        logger.info("Rotary Encoder IOC started")
        logger.info(f"PV Prefix: {self.pv_prefix}")
        logger.info("Waiting for serial data...")
        
        if EPICS_AVAILABLE:
            logger.info("EPICS integration enabled")
        else:
            logger.info("EPICS integration disabled (pyepics not installed)")
        
        return True
    
    def stop(self):
        """Stop the IOC"""
        logger.info("Stopping Rotary Encoder IOC")
        self.running = False
        self.disconnect()
    
    def print_status(self):
        """Print current status"""
        with self.data_lock:
            uptime = time.time() - self.start_time
            logger.info("="*50)
            logger.info(f"Rotary Encoder IOC Status")
            logger.info(f"Port: {self.port} @ {self.baudrate} baud")
            logger.info(f"Uptime: {uptime:.1f}s")
            logger.info(f"Last data: {self.last_data}")
            
            if EPICS_AVAILABLE:
                for key, pv in self.pvs.items():
                    if pv:
                        try:
                            value = pv.get()
                            logger.info(f"{key}: {value}")
                        except:
                            pass
            logger.info("="*50)


def main():
    import argparse
    import signal
    
    parser = argparse.ArgumentParser(
        description='EPICS IOC for Rotary Encoder Dual Stepper'
    )
    parser.add_argument(
        '--port', '-p',
        default='/dev/ttyUSB0',
        help='Serial port (default: /dev/ttyUSB0)'
    )
    parser.add_argument(
        '--baud', '-b',
        type=int,
        default=115200,
        help='Baud rate (default: 115200)'
    )
    parser.add_argument(
        '--prefix',
        default='RE:ch0:',
        help='EPICS PV prefix (default: RE:ch0:)'
    )
    
    args = parser.parse_args()
    
    # Create IOC instance
    ioc = RotaryEncoderIOC(
        port=args.port,
        baudrate=args.baud,
        pv_prefix=args.prefix
    )
    
    # Setup signal handlers
    def signal_handler(sig, frame):
        logger.info("Received interrupt signal")
        ioc.stop()
        exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start IOC
    if not ioc.start():
        exit(1)
    
    # Print status periodically
    try:
        while True:
            time.sleep(10)
            ioc.print_status()
    except KeyboardInterrupt:
        ioc.stop()
        logger.info("IOC stopped")


if __name__ == '__main__':
    main()
