#include <AccelStepper.h>
#include <MultiStepper.h>

// Coil1: Blue=A+, Black=A-
// Coil2: Red=B+,  Yellow=B-
const int PIN_A_PLUS  = 8;   // Blue
const int PIN_A_MINUS = 9;   // Black
const int PIN_B_PLUS  = 10;  // Red
const int PIN_B_MINUS = 11;  // Yellow

// Motor1: 
// Coil1=Blue(A+)/Black(A-) 40Ohm, 
// Coil2=Red(B+)/White(B-) 40Ohm
const int M1_A_PLUS  = 8;   // Blue
const int M1_A_MINUS = 9;   // Black
const int M1_B_PLUS  = 10;  // Red
const int M1_B_MINUS = 11;  // White

// Motor2: 
// Coil1=Green(A+)/Orange(A-) 40Ohm, 
// Coil2=Magenta(B+)/Yellow(B-) 40Ohm
const int M2_A_PLUS  = 4;   // Green
const int M2_A_MINUS = 5;   // Orange
const int M2_B_PLUS  = 6;   // Magenta
const int M2_B_MINUS = 7;   // Yellow

AccelStepper motor1(AccelStepper::FULL4WIRE, M1_A_PLUS, M1_A_MINUS, M1_B_PLUS, M1_B_MINUS);
AccelStepper motor2(AccelStepper::FULL4WIRE, M2_A_PLUS, M2_A_MINUS, M2_B_PLUS, M2_B_MINUS);
MultiStepper motors;

// 1回転のステップ数
const int STEPS_PER_REV = 200;

void setup()
{
    motor1.setMaxSpeed(500);
    motor2.setMaxSpeed(500);
    motors.addStepper(motor1);
    motors.addStepper(motor2);
}

void loop()
{
    long pos1[2] = {1 * STEPS_PER_REV, 1 * STEPS_PER_REV};
    motors.moveTo(pos1);
    motors.runSpeedToPosition();  // 同時に目標位置まで移動
    delay(1000);

    long pos2[2] = {0, 0};
    motors.moveTo(pos2);
    motors.runSpeedToPosition();
    delay(500);
}

// ライブラリインストール: arduino-cli lib install "AccelStepper"
// コンパイル: arduino-cli compile --fqbn arduino:avr:uno .
// 書き込み:   arduino-cli upload -p COM4 --fqbn arduino:avr:uno .
