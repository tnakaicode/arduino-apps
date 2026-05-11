// Modified rotary_encoder_dual_stepper.ino with EPICS serial output
// This version outputs data in a format suitable for EPICS PV updates
// Format: ENC1:value,ENC2:value,MTR1:value,MTR2:value,SYNC:value

#include <AccelStepper.h>

// =========================
// Rotary encoder #1 pins  (motor1 操作 / SW: syncモード切替)
// Encoder module terminals: GND, +, SW, DT, CLK
// GND -> GND, + -> 5V
// =========================
const int ENC1_SW_PIN  = 2;  // white
const int ENC1_DT_PIN  = 3;  // gray
const int ENC1_CLK_PIN = 12; // magenta

// =========================
// Rotary encoder #2 pins  (motor2 操作 / SW: 位置リセット)
// =========================
const int ENC2_SW_PIN  = A0; // 14
const int ENC2_DT_PIN  = A1; // 15
const int ENC2_CLK_PIN = A2; // 16

// =========================
// Bipolar stepper motor #1 pins
// Coil1: Blue=A+, Black=A-
// Coil2: Red=B+,  Yellow=B-
// =========================
const int M1_A_PLUS = 8;   // Blue
const int M1_A_MINUS = 9;  // Black
const int M1_B_PLUS = 10;  // Red
const int M1_B_MINUS = 11; // Yellow

// =========================
// Bipolar stepper motor #2 pins
// Coil1: Blue=A+, Black=A-
// Coil2: Red=B+,  Yellow=B-
// =========================
const int M2_A_PLUS = 4;  // Blue
const int M2_A_MINUS = 5; // Black
const int M2_B_PLUS = 6;  // Red
const int M2_B_MINUS = 7; // Yellow

AccelStepper motor1(AccelStepper::FULL4WIRE, M1_A_PLUS, M1_A_MINUS, M1_B_PLUS, M1_B_MINUS);
AccelStepper motor2(AccelStepper::FULL4WIRE, M2_A_PLUS, M2_A_MINUS, M2_B_PLUS, M2_B_MINUS);

// 1ノッチで動かすステップ数
const long STEP_PER_CLICK = 20;

// 目標位置
long target1 = 0;
long target2 = 0;

// Encoder positions (for EPICS PVs)
int enc1_position = 0;
int enc2_position = 0;

// ENC1 SW: syncモード
// false: enc1はmotor1のみ / true: enc1がmotor1+2を同期駆動
bool syncMode = false;

// Encoder1 state
int lastClk1State = HIGH;
int lastSw1State  = HIGH;
unsigned long lastSw1ChangeMs = 0;

// Encoder2 state
int lastClk2State = HIGH;
int lastSw2State  = HIGH;
unsigned long lastSw2ChangeMs = 0;

const unsigned long SW_DEBOUNCE_MS = 30;

// EPICS output timing
unsigned long lastEpicsUpdate = 0;
const unsigned long EPICS_UPDATE_INTERVAL = 100; // 100ms = 10Hz

void setup()
{
    pinMode(ENC1_SW_PIN,  INPUT_PULLUP);
    pinMode(ENC1_DT_PIN,  INPUT_PULLUP);
    pinMode(ENC1_CLK_PIN, INPUT_PULLUP);
    pinMode(ENC2_SW_PIN,  INPUT_PULLUP);
    pinMode(ENC2_DT_PIN,  INPUT_PULLUP);
    pinMode(ENC2_CLK_PIN, INPUT_PULLUP);

    motor1.setMaxSpeed(900);
    motor1.setAcceleration(1200);
    motor2.setMaxSpeed(900);
    motor2.setAcceleration(1200);

    Serial.begin(115200);
    Serial.println("# Dual bipolar stepper + dual rotary encoder start");
    Serial.println("# ENC1: motor1 (SW: syncモード切替)");
    Serial.println("# ENC2: motor2 (SW: 位置リセット)");
    Serial.println("# EPICS PV Format: ENC1:value,ENC2:value,MTR1:value,MTR2:value,SYNC:value");
}

// --- Encoder1: motor1 操作（syncMode時はmotor2も追従） ---
void handleEncoder1()
{
    int clkState = digitalRead(ENC1_CLK_PIN);

    if (lastClk1State == HIGH && clkState == LOW)
    {
        int dtState = digitalRead(ENC1_DT_PIN);
        long delta = (dtState != clkState) ? STEP_PER_CLICK : -STEP_PER_CLICK;

        target1 += delta;
        motor1.moveTo(target1);
        enc1_position += (delta > 0) ? 1 : -1;  // Increment/decrement by click, not steps

        if (syncMode)
        {
            target2 += delta;
            motor2.moveTo(target2);
            enc2_position += (delta > 0) ? 1 : -1;
        }
    }

    lastClk1State = clkState;
}

// --- Encoder2: motor2 操作、またはSW: リセット ---
void handleEncoder2()
{
    int clkState = digitalRead(ENC2_CLK_PIN);

    if (lastClk2State == HIGH && clkState == LOW)
    {
        int dtState = digitalRead(ENC2_DT_PIN);
        long delta = (dtState != clkState) ? STEP_PER_CLICK : -STEP_PER_CLICK;

        target2 += delta;
        motor2.moveTo(target2);
        enc2_position += (delta > 0) ? 1 : -1;
    }

    lastClk2State = clkState;
}

// --- SW1: Toggle sync mode ---
void handleSw1()
{
    int swState = digitalRead(ENC1_SW_PIN);

    if (lastSw1State == HIGH && swState == LOW)
    {
        lastSw1ChangeMs = millis();
    }
    else if (lastSw1State == LOW && swState == HIGH)
    {
        unsigned long pressDurationMs = millis() - lastSw1ChangeMs;

        if (pressDurationMs >= SW_DEBOUNCE_MS && pressDurationMs < 3000)
        {
            syncMode = !syncMode;
        }
    }

    lastSw1State = swState;
}

// --- SW2: Reset motor positions ---
void handleSw2()
{
    int swState = digitalRead(ENC2_SW_PIN);

    if (lastSw2State == HIGH && swState == LOW)
    {
        lastSw2ChangeMs = millis();
    }
    else if (lastSw2State == LOW && swState == HIGH)
    {
        unsigned long pressDurationMs = millis() - lastSw2ChangeMs;

        if (pressDurationMs >= SW_DEBOUNCE_MS && pressDurationMs < 3000)
        {
            // Reset target positions
            target1 = 0;
            target2 = 0;
            motor1.setCurrentPosition(0);
            motor2.setCurrentPosition(0);
        }
    }

    lastSw2State = swState;
}

// --- Output EPICS format data ---
void outputEpicsData()
{
    unsigned long now = millis();
    
    // Output at regular intervals for EPICS
    if (now - lastEpicsUpdate >= EPICS_UPDATE_INTERVAL)
    {
        lastEpicsUpdate = now;
        
        // Format: ENC1:value,ENC2:value,MTR1:value,MTR2:value,SYNC:value
        Serial.print("ENC1:");
        Serial.print(enc1_position);
        Serial.print(",ENC2:");
        Serial.print(enc2_position);
        Serial.print(",MTR1:");
        Serial.print(motor1.currentPosition());
        Serial.print(",MTR2:");
        Serial.print(motor2.currentPosition());
        Serial.print(",SYNC:");
        Serial.println(syncMode ? 1 : 0);
    }
}

void loop()
{
    // Handle encoder/button inputs
    handleEncoder1();
    handleEncoder2();
    handleSw1();
    handleSw2();

    // Run motors
    motor1.run();
    motor2.run();

    // Output EPICS data
    outputEpicsData();
}
