#include <Wire.h>

// I2C スキャナー
// A4=SDA, A5=SCL に接続して実行
// シリアルモニタで検出されたアドレスを確認する

void setup() {
    Serial.begin(9600);
    Wire.begin();
    Serial.println("I2C Scanner start...");

    int found = 0;
    for (uint8_t addr = 1; addr < 127; addr++) {
        Wire.beginTransmission(addr);
        uint8_t err = Wire.endTransmission();
        if (err == 0) {
            Serial.print("Found device at 0x");
            Serial.println(addr, HEX);
            found++;
        }
    }
    if (found == 0) {
        Serial.println("No I2C devices found.");
        Serial.println("Check: SDA=A4, SCL=A5, pull-up 4.7kOhm to 3.3V/5V");
    }
}

void loop() {}

// コンパイル: arduino-cli compile --fqbn arduino:avr:uno .
// 書き込み:   arduino-cli upload -p COM4 --fqbn arduino:avr:uno .
// 監視:       arduino-cli monitor -p COM4 --config baudrate=9600
