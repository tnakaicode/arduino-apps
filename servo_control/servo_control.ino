#include <Servo.h>
Servo myServo;

// ユーザー角度 (-90〜+90) を write 用角度 (0〜180) に変換
void servoWrite(int angle) {
    myServo.write(90 + angle);
}

void setup()
{
    myServo.attach(9); // 黄線をPin9に接続
}
void loop()
{
    servoWrite(-90); // -90度（左端）
    delay(1000);

    servoWrite(0);   // 0度（中央）
    delay(1000);

    servoWrite(90);  // +90度（右端）
    delay(1000);
}

// arduino-cli compile --fqbn arduino:avr:uno .
// arduino-cli upload -p COM4 --fqbn arduino:avr:uno .
