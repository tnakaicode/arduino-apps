#include "Arduino_LED_Matrix.h"

ArduinoLEDMatrix matrix;

// LEDの点灯状態を保持するバッファ（12行分）
uint8_t frame[12] = {0};
int byteCount = 0;

void setup() {
  Serial.begin(115200); // 高速通信
  matrix.begin();
}

void loop() {
  // LabVIEWから12バイト（全行分）のデータが届いたらLEDを更新
  while (Serial.available() > 0) {
    frame[byteCount] = Serial.read();
    byteCount++;

    if (byteCount >= 12) {
      matrix.renderFrame(frame); // LEDマトリクスを表示更新
      byteCount = 0;             // カウンタをリセット
    }
  }
}

//  & "C:\Program Files\Arduino CLI\arduino-cli.exe" core install arduino:renesas_uno
// Get-Content R4.cpp | & "C:\Program Files\Arduino CLI\arduino-cli.exe" compile --fqbn arduino:renesas_uno:unor4wifi --build-path ./build -
// & "C:\Program Files\Arduino CLI\arduino-cli.exe" upload -p COM5 --fqbn arduino:renesas_uno:unor4wifi --input-dir ./build
