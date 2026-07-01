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