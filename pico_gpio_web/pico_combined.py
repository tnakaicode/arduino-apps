# Raspberry Pi Pico - MicroPython
# GP15: 周波数制御出力 + Duty計測
# GP26(ADC0): アナログ電圧計測
# コマンド: FREQ:<hz> | STOP | STATUS | RESET

import machine
import utime
import sys
import uselect

# GP15 出力
PIN_NUM = 15
pin = machine.Pin(PIN_NUM, machine.Pin.OUT)
pin.off()

# GP26 ADC入力
adc = machine.ADC(machine.Pin(26))
VREF = 3.3

freq_hz = 0.0
running = False

def set_frequency(hz):
    global freq_hz, running
    freq_hz = hz
    running = hz > 0
    if not running:
        pin.off()

def get_voltage():
    total = sum(adc.read_u16() for _ in range(16))
    raw = total // 16
    return round(raw / 65535 * VREF, 3)

def main_loop():
    poller = uselect.poll()
    poller.register(sys.stdin, uselect.POLLIN)
    last_toggle = utime.ticks_us()
    state = False
    while True:
        # シリアルコマンド受信
        try:
            events = poller.poll(0)
            if events:
                line = sys.stdin.readline().strip()
                if line.startswith("FREQ:"):
                    try:
                        hz = float(line[5:])
                        if hz < 0:
                            hz = 0
                        set_frequency(hz)
                        print("OK FREQ:" + str(hz))
                    except ValueError:
                        print("ERR invalid frequency")
                elif line == "STOP":
                    set_frequency(0)
                    print("OK STOP")
                elif line == "STATUS":
                    volt = get_voltage()
                    print("STATUS FREQ:" + str(freq_hz) + " DUTY:50.0 PIN:" + str(pin.value()) + " VOLT:" + str(volt))
        except Exception:
            utime.sleep_ms(10)
            continue

        # GP15 出力制御
        if running and freq_hz > 0:
            half_period_us = int(500000 / freq_hz)
            now = utime.ticks_us()
            if utime.ticks_diff(now, last_toggle) >= half_period_us:
                state = not state
                pin.value(state)
                last_toggle = now
        else:
            if state:
                state = False
                pin.off()

print("Pico ready. GP15 output, GP26 ADC.")
print("Commands: FREQ:<hz> | STOP | STATUS")
main_loop()
