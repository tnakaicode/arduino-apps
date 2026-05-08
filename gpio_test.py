#!/usr/bin/env python3
import RPi.GPIO as GPIO
import sys

GPIO.setmode(GPIO.BCM)

if len(sys.argv) > 2:
    try:
        pin = int(sys.argv[1])
        cmd = sys.argv[2].upper()
        
        GPIO.setup(pin, GPIO.OUT)
        
        if cmd == 'ON':
            GPIO.output(pin, GPIO.HIGH)
            print(f"GPIO {pin}: ON")
        elif cmd == 'OFF':
            GPIO.output(pin, GPIO.LOW)
            print(f"GPIO {pin}: OFF")
        elif cmd == 'TOGGLE':
            state = GPIO.input(pin)
            GPIO.output(pin, not state)
            print(f"GPIO {pin}: {'ON' if not state else 'OFF'}")
        elif cmd == 'STATUS':
            state = GPIO.input(pin)
            print(f"GPIO {pin}: {'ON' if state else 'OFF'}")
        else:
            print(f"Unknown command: {cmd}")
    except ValueError:
        print("Error: GPIO number must be an integer")
else:
    print("Usage: python3 gpio_test.py <GPIO_NUM> [ON|OFF|TOGGLE|STATUS]")
    print("Examples:")
    print("  python3 gpio_test.py 26 ON")
    print("  python3 gpio_test.py 26 OFF")
    print("  python3 gpio_test.py 26 TOGGLE")
    print("  python3 gpio_test.py 26 STATUS")

GPIO.cleanup()
