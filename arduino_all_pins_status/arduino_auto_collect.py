import serial
import time

SERIAL_PORT = "COM3"  # 実際のポートに合わせて変更
BAUD_RATE = 9600

ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
time.sleep(2)  # Arduinoリセット待ち
print("シリアル接続が確立されました")

try:
    while True:
        line = ser.readline().decode("utf-8").strip()
        if line:
            try:
                digital_part, analog_part = line.split(';')
                digital_values = digital_part.replace('D:', '').split(',')
                analog_values = analog_part.replace('A:', '').split(',')
                digital_values = [int(x) for x in digital_values]
                analog_values = [int(x) for x in analog_values]
                print(f"Digital Pins (2-13): {digital_values}")
                print(f"Analog Pins (A0-A5): {analog_values}")
            except Exception as e:
                print(f"受信データのパースに失敗: {line} ({e})")
        else:
            print("データ未受信")
        time.sleep(1)
except KeyboardInterrupt:
    print("終了します")
finally:
    ser.close()
