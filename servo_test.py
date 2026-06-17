import lgpio
import time

GPIO1 = 12  # ハードウェアPWM対応ピン (物理ピン32)
GPIO2 = 13  # ハードウェアPWM対応ピン (物理ピン33)
CHIP = 4  # Raspberry Pi 5 は gpiochip4

def set_angle(h, gpio, angle, hold=0.5):
    """0〜180度をパルス幅（500〜2500μs）に変換してサーボ制御。到達後にPWMを停止して揺れを防ぐ"""
    angle = max(0, min(180, angle))  # 0〜180度にクランプ
    pulse_us = int(500 + (angle / 180.0) * 2000)
    lgpio.tx_servo(h, gpio, pulse_us)
    time.sleep(hold)            # サーボが目標角度に到達するまで待つ
    lgpio.tx_servo(h, gpio, 0)  # PWM停止（ギアで位置保持、揺れなくなる）

h = lgpio.gpiochip_open(CHIP)
lgpio.gpio_claim_output(h, GPIO1)
lgpio.gpio_claim_output(h, GPIO2)

try:
    print("サーボ初期化中 (GPIO 20, 21)...")

    print("1. まずは中央（180度）へ")
    set_angle(h, GPIO1, 180)
    set_angle(h, GPIO2, 180)

    print("2. 中央から±5度で小さく振ります")
    set_angle(h, GPIO1, 180-5)
    set_angle(h, GPIO2, 180-5)

    set_angle(h, GPIO1, 180-10)
    set_angle(h, GPIO2, 180-10)

    print("3. 中央に戻して終了します")
    set_angle(h, GPIO1, 180)
    set_angle(h, GPIO2, 180)

except KeyboardInterrupt:
    print("\n中断されました")

finally:
    lgpio.gpiochip_close(h)
    print("プログラムを終了しました。")
