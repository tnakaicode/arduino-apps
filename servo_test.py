import time
from gpiozero import AngularServo

# MG996Rのパルス幅（0.5ms〜2.5ms）
MIN_PW = 0.0005
MAX_PW = 0.0025

print("サーボ初期化中 (GPIO 20, 21)...")
# pin_factoryの指定を削除（ラズパイ5標準のlgpioが自動適用されます）
servo1 = AngularServo(20, min_angle=0, max_angle=180, min_pulse_width=MIN_PW, max_pulse_width=MAX_PW)
servo2 = AngularServo(21, min_angle=0, max_angle=180, min_pulse_width=MIN_PW, max_pulse_width=MAX_PW)

try:
    print("1. まずは中央（90度）へ")
    servo1.angle = 90
    servo2.angle = 90
    time.sleep(2)

    print("2. 交互に左右に振ります")
    servo1.angle = 0
    time.sleep(1)
    servo2.angle = 180
    time.sleep(2)

    servo1.angle = 180
    time.sleep(1)
    servo2.angle = 0
    time.sleep(2)

    print("3. 中央に戻して終了します")
    servo1.angle = 90
    servo2.angle = 90
    time.sleep(1)

except KeyboardInterrupt:
    print("\n中断されました")

finally:
    # サーボをフリー状態にする
    servo1.detach()
    servo2.detach()
    print("プログラムを終了しました。")