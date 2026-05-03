import serial
import time

# シリアルポートとボーレートを適宜変更してください
SERIAL_PORT = "COM3"  # 例: Windowsの場合 'COM3', Mac/Linuxの場合 '/dev/ttyACM0' など
BAUD_RATE = 9600

# シリアル接続を開始
ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
time.sleep(2)  # Arduinoのリセット待ち
print("シリアル接続が確立されました")

try:
    while True:
        ser.write(b"READ\n")  # Arduinoに全ピン状態要求
        line = ser.readline().decode("utf-8").strip()
        if line:
            # データ例: D:1,1,0,1,1,1,1,1,1,1,1,1;A:123,456,789,321,654,987
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

"""
# Arduino側スケッチ例
void setup() {
  Serial.begin(9600);
  for (int i = 2; i <= 13; i++) pinMode(i, INPUT_PULLUP); // デジタルピン
}

void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    if (cmd == "READ") {
      String result = "D:";
      for (int i = 2; i <= 13; i++) {
        result += digitalRead(i);
        if (i < 13) result += ",";
      }
      result += ";A:";
      for (int i = 0; i < 6; i++) {
        result += analogRead(i);
        if (i < 5) result += ",";
      }
      Serial.println(result);
    }
  }
  delay(10);
}
"""
