#include "Arduino_LED_Matrix.h"

ArduinoLEDMatrix matrix;

// 1. 最新の loadFrame が要求する「32ビット×3個（計12バイト）」の型に変更
uint32_t frame[3] = {0};
int byteCount = 0;

void setup() {
  Serial.begin(115200); // 高速通信
  matrix.begin();
}

void loop() {
  // LabVIEWから12バイト（全行分）のデータが届いたらLEDを更新
  while (Serial.available() > 0) {
    // 2. 32ビット配列のメモリに対して、1バイトずつ受信データを詰め込む
    ((uint8_t*)frame)[byteCount] = Serial.read();
    byteCount++;

    if (byteCount >= 12) {
      matrix.loadFrame(frame); // ★最新仕様の loadFrame に32ビット配列を渡す
      byteCount = 0;           // カウンタをリセット
    }
  }
}

// & "C:\Program Files\Arduino CLI\arduino-cli.exe" core install arduino:renesas_uno
// & "C:\Program Files\Arduino CLI\arduino-cli.exe" compile --fqbn arduino:renesas_uno:unor4wifi --build-path ./build R4Project.ino
// & "C:\Program Files\Arduino CLI\arduino-cli.exe" upload -p COM5 --fqbn arduino:renesas_uno:unor4wifi --input-dir ./build
