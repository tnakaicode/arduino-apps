#!/usr/bin/env python3
import RPi.GPIO as GPIO
import subprocess
import re
import sys
import os

GPIO.setmode(GPIO.BCM)


def parse_reserved_pins_from_env():
    raw = os.getenv("GPIO_RESERVED", "").strip()
    if not raw:
        return set()
    pins = set()
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            pins.add(int(item))
        except ValueError:
            pass
    return pins


RESERVED_PINS = parse_reserved_pins_from_env()


def get_gpioinfo_consumer(pin: int):
    try:
        out = subprocess.check_output(["gpioinfo", "gpiochip0"], text=True)
    except Exception:
        return None

    pat = re.compile(r"line\s+%d:\s+\"[^\"]*\"\s+(\"[^\"]*\"|unused)\s+" % pin)
    for line in out.splitlines():
        m = pat.search(line)
        if m:
            consumer = m.group(1)
            if consumer == "unused":
                return "unused"
            return consumer.strip('"')
    return None


def get_pinctrl_mode(pin: int):
    try:
        out = subprocess.check_output(["pinctrl", "get", str(pin)], text=True)
    except Exception:
        return None

    # Example: "14: a4    pn | hi // GPIO14 = TXD0"
    m = re.search(r"^\s*%d:\s+(\S+)" % pin, out)
    if m:
        return m.group(1)
    return None


def is_pin_in_use(pin: int):
    if pin in RESERVED_PINS:
        return True, "reserved"

    consumer = get_gpioinfo_consumer(pin)
    if consumer and consumer != "unused":
        return True, f"consumer={consumer}"

    mode = get_pinctrl_mode(pin)
    if mode and mode.startswith("a"):
        return True, f"alt={mode}"

    return False, ""


def usage():
    print("Usage: python3 gpio_test.py <GPIO_NUM> [ON|OFF|TOGGLE|STATUS]")
    print("Reserved GPIOs: env GPIO_RESERVED=5,6,7")
    print("Examples:")
    print("  python3 gpio_test.py 26 ON")
    print("  python3 gpio_test.py 26 OFF")
    print("  python3 gpio_test.py 26 TOGGLE")
    print("  python3 gpio_test.py 26 STATUS")

if len(sys.argv) > 2:
    try:
        pin = int(sys.argv[1])
        cmd = sys.argv[2].upper()

        if pin < 0 or pin > 27:
            print("Error: GPIO number must be in 0..27")
            sys.exit(1)

        in_use, reason = is_pin_in_use(pin)
        if in_use:
            print(f"GPIO {pin}: IN USE ({reason})")
            sys.exit(2)

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
            sys.exit(1)
    except ValueError:
        print("Error: GPIO number must be an integer")
        sys.exit(1)
else:
    usage()

GPIO.cleanup()

# pinctrl get 0-27
# gpioinfo gpiochip0 | sed -n '1,40p'
