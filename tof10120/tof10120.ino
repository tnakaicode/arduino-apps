#include <Wire.h>

// TOF10120 配線（I2C）
// 黒 → GND
// 赤 → 3.3V または 5V
// 黄 → SDA (Arduino A4)
// 白 → SCL (Arduino A5)
// 青 → 未使用（GPIO/ENABLE）
// 緑 → 未使用（INT）

const uint8_t TOF10120_ADDR = 0x52;  // 7bitアドレス (0xa4 >> 1)

void i2cScan() {
    Serial.println("=== I2C Scan ===");
    uint8_t found = 0;
    for (uint8_t addr = 1; addr < 127; addr++) {
        Wire.beginTransmission(addr);
        uint8_t err = Wire.endTransmission();
        if (err == 0) {
            Serial.print("Found: 0x");
            Serial.println(addr, HEX);
            found++;
        }
    }
    if (found == 0) Serial.println("No devices found. Check wiring/pull-ups.");
    Serial.println("================");
}

uint16_t readDistance() {
    Wire.beginTransmission(TOF10120_ADDR);
    Wire.write(0x00);
    Wire.endTransmission(false);  // Repeated Start
    Wire.requestFrom(TOF10120_ADDR, (uint8_t)2);
    if (Wire.available() >= 2) {
        uint8_t high = Wire.read();
        uint8_t low  = Wire.read();
        return ((uint16_t)high << 8) | low;
    }
    return 0xFFFF;
}

void setup() {
    Serial.begin(9600);
    Wire.begin();
    delay(500);
    i2cScan();
}

void loop() {
    uint16_t dist = readDistance();
    if (dist == 0xFFFF) {
        Serial.println(dist);
    } else {
        Serial.print("Distance: ");
        Serial.print(dist);
        Serial.println(" mm");
    }
    delay(500);
}

// コンパイル: arduino-cli compile --fqbn arduino:avr:uno .
// 書き込み:   arduino-cli upload -p COM4 --fqbn arduino:avr:uno .
// シリアル監視: arduino-cli monitor -p COM4 --config baudrate=9600
