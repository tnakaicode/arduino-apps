#!/usr/bin/env python3
"""
Serial Monitor for Rotary Encoder Dual Stepper
Simple tool to verify Arduino is sending data correctly
"""

import serial
import time
import argparse
import sys
from datetime import datetime


def monitor_serial(port='/dev/ttyUSB0', baudrate=115200, log_file=None):
    """Monitor and display serial data"""
    
    try:
        ser = serial.Serial(port, baudrate, timeout=1)
        print(f"Connected to {port} at {baudrate} baud")
        print("Press Ctrl+C to exit\n")
        
        line_count = 0
        log_handle = None
        
        if log_file:
            log_handle = open(log_file, 'w')
            log_handle.write(f"Serial Monitor - {datetime.now()}\n")
            log_handle.write(f"Port: {port}, Baud: {baudrate}\n")
            log_handle.write("="*80 + "\n")
        
        while True:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                
                if line:
                    timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                    output = f"[{timestamp}] {line}"
                    print(output)
                    
                    if log_handle:
                        log_handle.write(output + '\n')
                        log_handle.flush()
                    
                    line_count += 1
                    
                    # Parse and display formatted output
                    try:
                        pairs = line.split(',')
                        for pair in pairs:
                            if ':' in pair:
                                key, value = pair.split(':')
                                print(f"  {key.strip():>6s}: {value.strip():>10s}")
                    except:
                        pass
                    
                    print()
            
            time.sleep(0.01)
    
    except serial.SerialException as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    
    except KeyboardInterrupt:
        print("\n\nStopped monitoring")
        if log_handle:
            log_handle.write("\n" + "="*80 + "\n")
            log_handle.write(f"Total lines: {line_count}\n")
            log_handle.close()
            print(f"Data saved to {log_file}")
        return 0
    
    finally:
        if ser.is_open:
            ser.close()


def main():
    parser = argparse.ArgumentParser(
        description='Serial Monitor for Rotary Encoder Dual Stepper'
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
        '--log', '-l',
        help='Log file (optional)'
    )
    
    args = parser.parse_args()
    
    return monitor_serial(args.port, args.baud, args.log)


if __name__ == '__main__':
    sys.exit(main())
