#!/usr/bin/env python3
"""
Serial Reader for Rotary Encoder Dual Stepper
Reads Arduino serial data and publishes to EPICS via CAServer
No external dependencies - uses EPICS base only
"""

import serial
import time
import threading
import logging
from datetime import datetime

try:
    from pcaspy import SimpleServer, pvdb
    PCASPY_AVAILABLE = True
except ImportError:
    PCASPY_AVAILABLE = False
    print("Note: pcaspy not installed. Install with: pip install pcaspy")
    print("Continuing with data collection mode...")

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
        
        # Current PV values (in-memory)
        self.pv_values = {
            'ENC1_POS': 0,
            'ENC2_POS': 0,
            'MTR1_POS': 0,
            'MTR2_POS': 0,
            'SYNC_MODE': 0,
            'STATUS': 'Starting',
            'UPTIME': 0,
        }
        
        # Initialize CA server if available
        if PCASPY_AVAILABLE:
            self._setup_ca_server(pv_prefix)
        
        self.start_time = time.time()
        self.last_data = {}
        self.data_lock = threading.Lock()
        self.server = None
    
    def _setup_ca_server(self, pv_prefix):
        """Setup EPICS CA Server with PV database"""
        try:
            # Define PV database
            pvdb.clear()
            
            pvdb[f'{pv_prefix}ENC1:POSITION'] = {
                'type': 'int',
                'value': 0,
            }
            pvdb[f'{pv_prefix}ENC2:POSITION'] = {
                'type': 'int',
                'value': 0,
            }
            pvdb[f'{pv_prefix}MTR1:POSITION'] = {
                'type': 'long',
                'value': 0,
            }
            pvdb[f'{pv_prefix}MTR2:POSITION'] = {
                'type': 'long',
                'value': 0,
            }
            pvdb[f'{pv_prefix}SYNC:MODE'] = {
                'type': 'int',
                'value': 0,
            }
            pvdb[f'{pv_prefix}STATUS'] = {
                'type': 'string',
                'value': 'Starting',
            }
            pvdb[f'{pv_prefix}UPTIME'] = {
                'type': 'float',
                'value': 0,
            }
            
            # Create server
            self.server = SimpleServer()
            logger.info("EPICS CA Server initialized")
            
        except Exception as e:
            logger.error(f"Failed to setup CA server: {e}")
            self.server = None
        
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
        Ignore debug output and invalid lines
        """
        try:
            line = line.strip()
            
            # Skip empty lines and debug output
            if not line or not line.startswith('ENC'):
                return {}
            
            data = {}
            pairs = line.split(',')
            
            for pair in pairs:
                if ':' not in pair:
                    continue
                    
                key, value = pair.split(':', 1)
                key = key.strip()
                value = value.strip()
                
                # Only process known keys
                if key in ['ENC1', 'ENC2', 'MTR1', 'MTR2', 'SYNC']:
                    try:
                        data[key] = int(value)
                    except ValueError:
                        logger.debug(f"Invalid value for {key}: {value}")
                        continue
            
            return data
        except Exception as e:
            logger.debug(f"Error parsing serial data: {e}")
            return {}
    
    def update_pvs(self, data):
        """Update EPICS PVs with parsed data"""
        mapping = {
            'ENC1': ('ENC1_POS', int),
            'ENC2': ('ENC2_POS', int),
            'MTR1': ('MTR1_POS', int),
            'MTR2': ('MTR2_POS', int),
            'SYNC': ('SYNC_MODE', int),
        }
        
        with self.data_lock:
            # Update in-memory values
            for key, (pv_key, dtype) in mapping.items():
                if key in data:
                    self.pv_values[pv_key] = dtype(data[key])
            
            # Update CA Server if available
            if PCASPY_AVAILABLE and self.server:
                pv_prefix = self.pv_prefix
                try:
                    if 'ENC1' in data:
                        self.server[f'{pv_prefix}ENC1:POSITION'] = data['ENC1']
                    if 'ENC2' in data:
                        self.server[f'{pv_prefix}ENC2:POSITION'] = data['ENC2']
                    if 'MTR1' in data:
                        self.server[f'{pv_prefix}MTR1:POSITION'] = data['MTR1']
                    if 'MTR2' in data:
                        self.server[f'{pv_prefix}MTR2:POSITION'] = data['MTR2']
                    if 'SYNC' in data:
                        self.server[f'{pv_prefix}SYNC:MODE'] = data['SYNC']
                except Exception as e:
                    logger.debug(f"Error updating CA server: {e}")
            
            logger.debug(f"PV Values: {self.pv_values}")
    
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
        logger.info(f"Serial Port: {self.port} @ {self.baudrate} baud")
        logger.info("Waiting for serial data...")
        
        if PCASPY_AVAILABLE and self.server:
            logger.info("EPICS CA Server enabled")
            # Start CA server in background
            self.server_thread = threading.Thread(target=self.server.process, daemon=True)
            self.server_thread.start()
        else:
            logger.info("EPICS CA Server not available (install pcaspy for full EPICS support)")
        
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
            logger.info("PV Values:")
            for key, value in self.pv_values.items():
                logger.info(f"  {key}: {value}")
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
