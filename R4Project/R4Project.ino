#include "Arduino_LED_Matrix.h"

ArduinoLEDMatrix matrix;

uint32_t frame[3] = {0};
int byteCount = 0;

void setup() {
  Serial.begin(115200);
  matrix.begin();
}

void loop() {
  while (Serial.available() > 0) {
    ((uint8_t*)frame)[byteCount] = Serial.read();
    byteCount++;

    if (byteCount >= 12) {
      matrix.loadFrame(frame); 
      
      // ★追加：受信した12バイトのデータをそのままLabVIEWに送り返す
      Serial.write((uint8_t*)frame, 12); 
      
      byteCount = 0;
    }
  }
}

// & "C:\Program Files\Arduino CLI\arduino-cli.exe" core install arduino:renesas_uno
// & "C:\Program Files\Arduino CLI\arduino-cli.exe" compile --fqbn arduino:renesas_uno:unor4wifi --build-path ./build R4Project.ino
// & "C:\Program Files\Arduino CLI\arduino-cli.exe" upload -p COM5 --fqbn arduino:renesas_uno:unor4wifi --input-dir ./build
