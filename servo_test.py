import lgpio
import time

GPIO1 = 20
GPIO2 = 21
CHIP = 4  # Raspberry Pi 5 は gpiochip4

def set_angle(h, gpio, angle):
    """0〜180度をパルス幅（500〜2500μs）に変換してサーボ制御"""
    angle = max(0, min(180, angle))  # 0〜180度にクランプ
    pulse_us = int(500 + (angle / 180.0) * 2000)
    lgpio.tx_servo(h, gpio, pulse_us)

h = lgpio.gpiochip_open(CHIP)
lgpio.gpio_claim_output(h, GPIO1)
lgpio.gpio_claim_output(h, GPIO2)

try:
    print("サーボ初期化中 (GPIO 20, 21)...")

    print("1. まずは中央（90度）へ")
    set_angle(h, GPIO1, 0)
    set_angle(h, GPIO2, 0)
    time.sleep(2)

    print("2. 中央から±5度で小さく振ります")
    set_angle(h, GPIO1, 5)
    time.sleep(1)
    set_angle(h, GPIO2, 5)
    time.sleep(1)

    set_angle(h, GPIO1, 10)
    time.sleep(1)
    set_angle(h, GPIO2, 10)
    time.sleep(1)

    print("3. 中央に戻して終了します")
    set_angle(h, GPIO1, 0)
    set_angle(h, GPIO2, 0)
    time.sleep(1)

except KeyboardInterrupt:
    print("\n中断されました")

finally:
    lgpio.tx_servo(h, GPIO1, 0)
    lgpio.tx_servo(h, GPIO2, 0)
    lgpio.gpiochip_close(h)
    print("プログラムを終了しました。")