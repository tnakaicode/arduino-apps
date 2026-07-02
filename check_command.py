import serial
import time

ser = serial.Serial("COM9", 115200, timeout=1)
time.sleep(1.5)


def send_cmd(cmd_text):
    full_cmd = cmd_text.encode("utf-8") + b"\r\n"
    ser.write(full_cmd)
    print(f"送信: {cmd_text}")
    time.sleep(0.1)


# 1. CH1の波形を「矩形波(Square)」にする
send_cmd(":w22=1.")

# 2. CH1の周波数を「1.5kHz (150000)」にする
send_cmd(":w23=200000.")

# 3. CH1の出力を「ON」にする
send_cmd(":w20=0.")

ser.close()
print("制御完了")
