#include <Stepper.h>

// 28BYJ-48: ギア比1/64、1回転 = 2048ステップ（ハーフステップ）
const int STEPS_PER_REV = 2048;

// Stepper(ステップ数, IN1, IN3, IN2, IN4) ← この順序が重要
Stepper myStepper(STEPS_PER_REV, 8, 10, 9, 11);

void setup()
{
    myStepper.setSpeed(10); // 10 RPM（最大15RPM程度）
}

void loop()
{
    myStepper.setSpeed(10); // 10 RPM（最大15RPM程度）
    myStepper.step(2048);  // 1回転（正転）
    delay(500);
    myStepper.step(1024);  // 1回転（正転）
    delay(500);
    myStepper.setSpeed(12); // 10 RPM（最大15RPM程度）
    myStepper.step(-3072); // 1回転（逆転）
    delay(1000);
}

// コンパイル: arduino-cli compile --fqbn arduino:avr:uno .
// 書き込み:   arduino-cli upload -p COM4 --fqbn arduino:avr:uno .
