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
    print("X1201 GPIOs: env GPIO_X1201=5,6,7,8,14,15,16")
    print("Examples:")
    print("  python3 gpio_test.py 26 ON")
    print("  python3 gpio_test.py 26 OFF")
    print("  python3 gpio_test.py 26 TOGGLE")
    print("  python3 gpio_test.py 26 STATUS")
    print("pinctrl get 0-27")
    print("gpioinfo gpiochip0 | sed -n '1,40p'")

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

# rpi@rpi5:~/arduino-apps $ pinctrl get 0-27
#  0: ip    pu | hi // ID_SDA/GPIO0 = input
#  1: ip    pu | hi // ID_SCL/GPIO1 = input
#  2: a3    pu | hi // GPIO2 = SDA1
#  3: a3    pu | hi // GPIO3 = SCL1
#  4: ip    pn | lo // GPIO4 = input
#  5: no    pu | -- // GPIO5 = none
#  6: ip    pu | hi // GPIO6 = input
#  7: op dh pu | hi // GPIO7 = output
#  8: op dh pu | hi // GPIO8 = output
#  9: a0    pn | lo // GPIO9 = SPI0_MISO
# 10: a0    pn | lo // GPIO10 = SPI0_MOSI
# 11: a0    pn | lo // GPIO11 = SPI0_SCLK
# 12: no    pd | -- // GPIO12 = none
# 13: no    pd | -- // GPIO13 = none
# 14: a4    pn | hi // GPIO14 = TXD0
# 15: a4    pu | hi // GPIO15 = RXD0
# 16: no    pd | -- // GPIO16 = none
# 17: no    pd | -- // GPIO17 = none
# 18: no    pd | -- // GPIO18 = none
# 19: no    pd | -- // GPIO19 = none
# 20: no    pd | -- // GPIO20 = none
# 21: no    pd | -- // GPIO21 = none
# 22: no    pd | -- // GPIO22 = none
# 23: no    pd | -- // GPIO23 = none
# 24: no    pd | -- // GPIO24 = none
# 25: no    pd | -- // GPIO25 = none
# 26: no    pd | -- // GPIO26 = none
# 27: no    pd | -- // GPIO27 = none
# rpi@rpi5:~/arduino-apps $ 
# rpi@rpi5:~/arduino-apps $ gpioinfo gpiochip0 | sed -n '1,40p'
# gpiochip0 - 54 lines:
#         line   0:     "ID_SDA"       unused   input  active-high 
#         line   1:     "ID_SCL"       unused   input  active-high 
#         line   2:      "GPIO2"       unused   input  active-high 
#         line   3:      "GPIO3"       unused   input  active-high 
#         line   4:      "GPIO4"  "onewire@0"  output  active-high [used open-drain]
#         line   5:      "GPIO5"       unused   input  active-high 
#         line   6:      "GPIO6"       unused   input  active-high 
#         line   7:      "GPIO7"   "spi0 CS1"  output   active-low [used]
#         line   8:      "GPIO8"   "spi0 CS0"  output   active-low [used]
#         line   9:      "GPIO9"       unused   input  active-high 
#         line  10:     "GPIO10"       unused   input  active-high 
#         line  11:     "GPIO11"       unused   input  active-high 
#         line  12:     "GPIO12"       unused   input  active-high 
#         line  13:     "GPIO13"       unused   input  active-high 
#         line  14:     "GPIO14"       unused   input  active-high 
#         line  15:     "GPIO15"       unused   input  active-high 
#         line  16:     "GPIO16"       unused   input  active-high 
#         line  17:     "GPIO17"       unused   input  active-high 
#         line  18:     "GPIO18"       unused   input  active-high 
#         line  19:     "GPIO19"       unused   input  active-high 
#         line  20:     "GPIO20"       unused   input  active-high 
#         line  21:     "GPIO21"       unused   input  active-high 
#         line  22:     "GPIO22"       unused   input  active-high 
#         line  23:     "GPIO23"       unused   input  active-high 
#         line  24:     "GPIO24"       unused   input  active-high 
#         line  25:     "GPIO25"       unused   input  active-high 
#         line  26:     "GPIO26"       unused   input  active-high 
#         line  27:     "GPIO27"       unused   input  active-high 
#         line  28: "PCIE_RP1_WAKE" unused input active-high 
#         line  29:   "FAN_TACH"       unused   input  active-high 
#         line  30:   "HOST_SDA"       unused   input  active-high 
#         line  31:   "HOST_SCL"       unused   input  active-high 
#         line  32:  "ETH_RST_N"  "phy-reset"  output   active-low [used]
#         line  33:          "-"       unused   input  active-high 
#         line  34: "CD0_IO0_MICCLK" "cam0_reg" output active-high [used]
#         line  35: "CD0_IO0_MICDAT0" unused input active-high 
#         line  36: "RP1_PCIE_CLKREQ_N" unused input active-high 
#         line  37:          "-"       unused   input  active-high 
#         line  38:    "CD0_SDA"       unused   input  active-high 
# rpi@rpi5:~/arduino-apps $ 
# rpi@rpi5:~/arduino-apps $ gpioinfo 
# gpiochip0 - 54 lines:
#         line   0:     "ID_SDA"       unused   input  active-high 
#         line   1:     "ID_SCL"       unused   input  active-high 
#         line   2:      "GPIO2"       unused   input  active-high 
#         line   3:      "GPIO3"       unused   input  active-high 
#         line   4:      "GPIO4"  "onewire@0"  output  active-high [used open-drain]
#         line   5:      "GPIO5"       unused   input  active-high 
#         line   6:      "GPIO6"       unused   input  active-high 
#         line   7:      "GPIO7"   "spi0 CS1"  output   active-low [used]
#         line   8:      "GPIO8"   "spi0 CS0"  output   active-low [used]
#         line   9:      "GPIO9"       unused   input  active-high 
#         line  10:     "GPIO10"       unused   input  active-high 
#         line  11:     "GPIO11"       unused   input  active-high 
#         line  12:     "GPIO12"       unused   input  active-high 
#         line  13:     "GPIO13"       unused   input  active-high 
#         line  14:     "GPIO14"       unused   input  active-high 
#         line  15:     "GPIO15"       unused   input  active-high 
#         line  16:     "GPIO16"       unused   input  active-high 
#         line  17:     "GPIO17"       unused   input  active-high 
#         line  18:     "GPIO18"       unused   input  active-high 
#         line  19:     "GPIO19"       unused   input  active-high 
#         line  20:     "GPIO20"       unused   input  active-high 
#         line  21:     "GPIO21"       unused   input  active-high 
#         line  22:     "GPIO22"       unused   input  active-high 
#         line  23:     "GPIO23"       unused   input  active-high 
#         line  24:     "GPIO24"       unused   input  active-high 
#         line  25:     "GPIO25"       unused   input  active-high 
#         line  26:     "GPIO26"       unused   input  active-high 
#         line  27:     "GPIO27"       unused   input  active-high 
#         line  28: "PCIE_RP1_WAKE" unused input active-high 
#         line  29:   "FAN_TACH"       unused   input  active-high 
#         line  30:   "HOST_SDA"       unused   input  active-high 
#         line  31:   "HOST_SCL"       unused   input  active-high 
#         line  32:  "ETH_RST_N"  "phy-reset"  output   active-low [used]
#         line  33:          "-"       unused   input  active-high 
#         line  34: "CD0_IO0_MICCLK" "cam0_reg" output active-high [used]
#         line  35: "CD0_IO0_MICDAT0" unused input active-high 
#         line  36: "RP1_PCIE_CLKREQ_N" unused input active-high 
#         line  37:          "-"       unused   input  active-high 
#         line  38:    "CD0_SDA"       unused   input  active-high 
#         line  39:    "CD0_SCL"       unused   input  active-high 
#         line  40:    "CD1_SDA"       unused   input  active-high 
#         line  41:    "CD1_SCL"       unused   input  active-high 
#         line  42: "USB_VBUS_EN" unused output active-high 
#         line  43:   "USB_OC_N"       unused   input  active-high 
#         line  44: "RP1_STAT_LED" "PWR" output active-low [used]
#         line  45:    "FAN_PWM"       unused  output  active-high 
#         line  46: "CD1_IO0_MICCLK" "cam1_reg" output active-high [used]
#         line  47:  "2712_WAKE"       unused   input  active-high 
#         line  48: "CD1_IO1_MICDAT1" unused input active-high 
#         line  49: "EN_MAX_USB_CUR" unused output active-high 
#         line  50:          "-"       unused   input  active-high 
#         line  51:          "-"       unused   input  active-high 
#         line  52:          "-"       unused   input  active-high 
#         line  53:          "-"       unused   input  active-high 
# gpiochip10 - 32 lines:
#         line   0:          "-"       unused   input  active-high 
#         line   1: "2712_BOOT_CS_N" "spi10 CS0" output active-low [used]
#         line   2: "2712_BOOT_MISO" unused input active-high 
#         line   3: "2712_BOOT_MOSI" unused input active-high 
#         line   4: "2712_BOOT_SCLK" unused input active-high 
#         line   5:          "-"       unused   input  active-high 
#         line   6:          "-"       unused   input  active-high 
#         line   7:          "-"       unused   input  active-high 
#         line   8:          "-"       unused   input  active-high 
#         line   9:          "-"       unused   input  active-high 
#         line  10:          "-"       unused   input  active-high 
#         line  11:          "-"       unused   input  active-high 
#         line  12:          "-"       unused   input  active-high 
#         line  13:          "-"       unused   input  active-high 
#         line  14:   "PCIE_SDA"       unused   input  active-high 
#         line  15:   "PCIE_SCL"       unused   input  active-high 
#         line  16:          "-"       unused   input  active-high 
#         line  17:          "-"       unused   input  active-high 
#         line  18:          "-"       unused   input  active-high 
#         line  19:          "-"       unused   input  active-high 
#         line  20:   "PWR_GPIO" "pwr_button"   input   active-low [used]
#         line  21: "2712_G21_FS" unused input active-high 
#         line  22:          "-"       unused   input  active-high 
#         line  23:          "-"       unused   input  active-high 
#         line  24:     "BT_RTS"       unused   input  active-high 
#         line  25:     "BT_CTS"       unused   input  active-high 
#         line  26:     "BT_TXD"       unused   input  active-high 
#         line  27:     "BT_RXD"       unused   input  active-high 
#         line  28:      "WL_ON"  "wl-on-reg"  output  active-high [used]
#         line  29:      "BT_ON"   "shutdown"  output  active-high [used]
#         line  30: "WIFI_SDIO_CLK" unused input active-high 
#         line  31: "WIFI_SDIO_CMD" unused input active-high 
# gpiochip11 - 15 lines:
#         line   0:    "RP1_SDA"       unused   input  active-high 
#         line   1:    "RP1_SCL"       unused   input  active-high 
#         line   2:    "RP1_RUN" "RP1 RUN pin" output active-high [used]
#         line   3: "SD_IOVDD_SEL" "vdd-sd-io" output active-high [used]
#         line   4:  "SD_PWR_ON" "sd-vcc-reg"  output  active-high [used]
#         line   5:  "SD_CDET_N"         "cd"   input   active-low [used]
#         line   6:   "SD_FLG_N"       unused   input  active-high 
#         line   7:          "-"       unused   input  active-high 
#         line   8:  "2712_WAKE"       unused   input  active-high 
#         line   9: "2712_STAT_LED" "ACT" output active-low [used]
#         line  10:          "-"       unused   input  active-high 
#         line  11:          "-"       unused   input  active-high 
#         line  12:   "PMIC_INT"       unused   input  active-high 
#         line  13: "UART_TX_FS"       unused   input  active-high 
#         line  14: "UART_RX_FS"       unused   input  active-high 
# gpiochip12 - 6 lines:
#         line   0:  "HDMI0_SCL"       unused   input  active-high 
#         line   1:  "HDMI0_SDA"       unused   input  active-high 
#         line   2:  "HDMI1_SCL"       unused   input  active-high 
#         line   3:  "HDMI1_SDA"       unused   input  active-high 
#         line   4:   "PMIC_SCL"       unused   input  active-high 
#         line   5:   "PMIC_SDA"       unused   input  active-high 
# gpiochip13 - 4 lines:
#         line   0: "WIFI_SDIO_D0" unused input active-high 
#         line   1: "WIFI_SDIO_D1" unused input active-high 
#         line   2: "WIFI_SDIO_D2" unused input active-high 
#         line   3: "WIFI_SDIO_D3" unused input active-high 
# gpiochip0 - 54 lines:
#         line   0:     "ID_SDA"       unused   input  active-high 
#         line   1:     "ID_SCL"       unused   input  active-high 
#         line   2:      "GPIO2"       unused   input  active-high 
#         line   3:      "GPIO3"       unused   input  active-high 
#         line   4:      "GPIO4"  "onewire@0"  output  active-high [used open-drain]
#         line   5:      "GPIO5"       unused   input  active-high 
#         line   6:      "GPIO6"       unused   input  active-high 
#         line   7:      "GPIO7"   "spi0 CS1"  output   active-low [used]
#         line   8:      "GPIO8"   "spi0 CS0"  output   active-low [used]
#         line   9:      "GPIO9"       unused   input  active-high 
#         line  10:     "GPIO10"       unused   input  active-high 
#         line  11:     "GPIO11"       unused   input  active-high 
#         line  12:     "GPIO12"       unused   input  active-high 
#         line  13:     "GPIO13"       unused   input  active-high 
#         line  14:     "GPIO14"       unused   input  active-high 
#         line  15:     "GPIO15"       unused   input  active-high 
#         line  16:     "GPIO16"       unused   input  active-high 
#         line  17:     "GPIO17"       unused   input  active-high 
#         line  18:     "GPIO18"       unused   input  active-high 
#         line  19:     "GPIO19"       unused   input  active-high 
#         line  20:     "GPIO20"       unused   input  active-high 
#         line  21:     "GPIO21"       unused   input  active-high 
#         line  22:     "GPIO22"       unused   input  active-high 
#         line  23:     "GPIO23"       unused   input  active-high 
#         line  24:     "GPIO24"       unused   input  active-high 
#         line  25:     "GPIO25"       unused   input  active-high 
#         line  26:     "GPIO26"       unused   input  active-high 
#         line  27:     "GPIO27"       unused   input  active-high 
#         line  28: "PCIE_RP1_WAKE" unused input active-high 
#         line  29:   "FAN_TACH"       unused   input  active-high 
#         line  30:   "HOST_SDA"       unused   input  active-high 
#         line  31:   "HOST_SCL"       unused   input  active-high 
#         line  32:  "ETH_RST_N"  "phy-reset"  output   active-low [used]
#         line  33:          "-"       unused   input  active-high 
#         line  34: "CD0_IO0_MICCLK" "cam0_reg" output active-high [used]
#         line  35: "CD0_IO0_MICDAT0" unused input active-high 
#         line  36: "RP1_PCIE_CLKREQ_N" unused input active-high 
#         line  37:          "-"       unused   input  active-high 
#         line  38:    "CD0_SDA"       unused   input  active-high 
#         line  39:    "CD0_SCL"       unused   input  active-high 
#         line  40:    "CD1_SDA"       unused   input  active-high 
#         line  41:    "CD1_SCL"       unused   input  active-high 
#         line  42: "USB_VBUS_EN" unused output active-high 
#         line  43:   "USB_OC_N"       unused   input  active-high 
#         line  44: "RP1_STAT_LED" "PWR" output active-low [used]
#         line  45:    "FAN_PWM"       unused  output  active-high 
#         line  46: "CD1_IO0_MICCLK" "cam1_reg" output active-high [used]
#         line  47:  "2712_WAKE"       unused   input  active-high 
#         line  48: "CD1_IO1_MICDAT1" unused input active-high 
#         line  49: "EN_MAX_USB_CUR" unused output active-high 
#         line  50:          "-"       unused   input  active-high 
#         line  51:          "-"       unused   input  active-high 
#         line  52:          "-"       unused   input  active-high 
#         line  53:          "-"       unused   input  active-high 
# rpi@rpi5:~/arduino-apps $ 
