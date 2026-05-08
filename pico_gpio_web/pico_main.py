# Raspberry Pi Pico - MicroPython
# シリアルで周波数コマンドを受け取り、GP15をON/OFFする
# コマンド: "FREQ:10.5\n" → 10.5Hzで点滅
#           "STOP\n"       → 停止

import machine
import utime

PIN_NUM = 15  # 制御するGPIOピン番号 (GP15)

pin = machine.Pin(PIN_NUM, machine.Pin.OUT)
pin.off()

freq_hz = 0.0  # 0 = 停止
running = False


def set_frequency(hz):
    global freq_hz, running
    freq_hz = hz
    running = hz > 0
    if not running:
        pin.off()


def toggle_loop():
    last_toggle = utime.ticks_us()
    state = False
    while True:
        # シリアルにデータがあれば読む
        if utime.ticks_diff(utime.ticks_ms(), 0) >= 0:  # always true, just yield
            pass

        line = None
        # ノンブロッキング読み込み
        import sys
        import select
        r, _, _ = select.select([sys.stdin], [], [], 0)
        if r:
            line = sys.stdin.readline().strip()

        if line:
            if line.startswith("FREQ:"):
                try:
                    hz = float(line[5:])
                    if hz < 0:
                        hz = 0
                    set_frequency(hz)
                    print(f"OK FREQ:{hz}")
                except ValueError:
                    print("ERR invalid frequency")
            elif line == "STOP":
                set_frequency(0)
                print("OK STOP")
            elif line == "STATUS":
                print(f"STATUS FREQ:{freq_hz} PIN:{pin.value()}")

        # GPIO制御
        if running and freq_hz > 0:
            half_period_us = int(500000 / freq_hz)  # 半周期 (マイクロ秒)
            now = utime.ticks_us()
            if utime.ticks_diff(now, last_toggle) >= half_period_us:
                state = not state
                pin.value(state)
                last_toggle = now
        else:
            state = False
            pin.off()


print("Pico GPIO Web Controller ready. GP15 output.")
print("Commands: FREQ:<hz> | STOP | STATUS")
toggle_loop()
