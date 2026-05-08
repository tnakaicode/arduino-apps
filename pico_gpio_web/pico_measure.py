# Raspberry Pi Pico - MicroPython
# GP15の電圧変動を検出して周波数・Duty比を計算
# GP26(ADC0)でアナログ電圧計測
# コマンド: STATUS → FREQ, DUTY, PIN, VOLT の状態返答
#           RESET  → 計測値リセット

import machine
import utime
import sys
import uselect

PIN_NUM = 15
pin = machine.Pin(PIN_NUM, machine.Pin.IN, machine.Pin.PULL_DOWN)

# GP26 ADC（アナログ電圧計測）
adc = machine.ADC(machine.Pin(26))
VREF = 3.3

def get_voltage():
    # 16回平均でノイズ低減
    total = sum(adc.read_u16() for _ in range(16))
    raw = total // 16
    return round(raw / 65535 * VREF, 3)

# 計測値（IRQハンドラと共有）
_rise_time = 0
_prev_rise = 0
_period_us = 0
_high_us = 0
_last_edge_us = 0

def on_edge(p):
    global _rise_time, _prev_rise, _period_us, _high_us, _last_edge_us
    now = utime.ticks_us()
    _last_edge_us = now
    if p.value() == 1:  # 立ち上がり
        if _prev_rise > 0:
            _period_us = utime.ticks_diff(now, _prev_rise)
        _prev_rise = now
        _rise_time = now
    else:               # 立ち下がり
        if _rise_time > 0:
            _high_us = utime.ticks_diff(now, _rise_time)

pin.irq(trigger=machine.Pin.IRQ_RISING | machine.Pin.IRQ_FALLING, handler=on_edge)

def get_freq():
    if _period_us <= 0:
        return 0.0
    # 最後のエッジから1秒以上経過していたら0
    if utime.ticks_diff(utime.ticks_us(), _last_edge_us) > 1000000:
        return 0.0
    return round(1000000.0 / _period_us, 2)

def get_duty():
    if _period_us <= 0:
        return 0.0
    return round(_high_us / _period_us * 100.0, 1)

def reset_measure():
    global _rise_time, _prev_rise, _period_us, _high_us, _last_edge_us
    _rise_time = 0
    _prev_rise = 0
    _period_us = 0
    _high_us = 0
    _last_edge_us = 0

def main_loop():
    poller = uselect.poll()
    poller.register(sys.stdin, uselect.POLLIN)
    while True:
        try:
            events = poller.poll(0)
            if events:
                line = sys.stdin.readline().strip()
                if line == "STATUS":
                    freq = get_freq()
                    duty = get_duty()
                    volt = get_voltage()
                    print("STATUS FREQ:" + str(freq) + " DUTY:" + str(duty) + " PIN:" + str(pin.value()) + " VOLT:" + str(volt))
                elif line == "RESET":
                    reset_measure()
                    print("OK RESET")
        except Exception:
            utime.sleep_ms(10)
            continue

        utime.sleep_ms(1)

print("Pico Measure ready. GP15 input, GP26 ADC.")
print("Commands: STATUS | RESET")
main_loop()
