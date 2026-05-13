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

const bool DEBUG_SERIAL = false;

const long SERIAL_CMD_MAX_ABS = 200000;
const long SERIAL_RPM_MAX_ABS = 300;
const float MOTOR_STEPS_PER_REV = 200.0f;
const float DEFAULT_MAX_SPEED_STEPS_PER_SEC = 900.0f;

// 1ノッチで動かすステップ数
const long STEP_PER_CLICK = 20;

// 目標位置
long target1 = 0;
long target2 = 0;
long rpmCmd1 = 0;
long rpmCmd2 = 0;

// Encoder click counts (for EPICS PVs)
int enc1_clicks = 0;
int enc2_clicks = 0;

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
const unsigned long EPICS_UPDATE_INTERVAL = 10; // 10ms = 100Hz

// Arduino runtime stats
unsigned long lastLoopTickMs = 0;
unsigned long loopPeriodMs = 0;
unsigned long lastLoopTickUs = 0;
unsigned long loopPeriodUs = 0;
unsigned long loopRateWindowStartMs = 0;
unsigned long loopRateWindowCount = 0;
long loopRateHz = 0;

String serialCmdBuf;

long clampTarget(long value)
{
    if (value > SERIAL_CMD_MAX_ABS)
    {
        return SERIAL_CMD_MAX_ABS;
    }
    if (value < -SERIAL_CMD_MAX_ABS)
    {
        return -SERIAL_CMD_MAX_ABS;
    }
    return value;
}

long clampRpm(long value)
{
    if (value > SERIAL_RPM_MAX_ABS)
    {
        return SERIAL_RPM_MAX_ABS;
    }
    if (value < -SERIAL_RPM_MAX_ABS)
    {
        return -SERIAL_RPM_MAX_ABS;
    }
    return value;
}

float rpmToStepsPerSec(long rpm)
{
    long absRpm = (rpm < 0) ? -rpm : rpm;
    return ((float)absRpm * MOTOR_STEPS_PER_REV) / 60.0f;
}

void applyMotorTarget(int motorIndex, long value)
{
    long clamped = clampTarget(value);
    if (motorIndex == 1)
    {
        target1 = clamped;
        motor1.moveTo(target1);
    }
    else if (motorIndex == 2)
    {
        target2 = clamped;
        motor2.moveTo(target2);
    }
}

void applyMotorRpm(int motorIndex, long rpm)
{
    long clamped = clampRpm(rpm);
    float sps = rpmToStepsPerSec(clamped);
    if (sps <= 0.0f)
    {
        sps = DEFAULT_MAX_SPEED_STEPS_PER_SEC;
    }
    if (motorIndex == 1)
    {
        rpmCmd1 = clamped;
        motor1.setMaxSpeed(sps);
    }
    else if (motorIndex == 2)
    {
        rpmCmd2 = clamped;
        motor2.setMaxSpeed(sps);
    }
}

void handleSerialCommand(const String& cmd)
{
    if (cmd.length() == 0)
    {
        return;
    }

    const char *prefix1 = "SET:MTR1:";
    const char *prefix2 = "SET:MTR2:";
    const char *rpmPrefix1 = "SET:RPM1:";
    const char *rpmPrefix2 = "SET:RPM2:";

    if (cmd.startsWith(prefix1))
    {
        long value = cmd.substring(strlen(prefix1)).toInt();
        applyMotorTarget(1, value);
        return;
    }

    if (cmd.startsWith(prefix2))
    {
        long value = cmd.substring(strlen(prefix2)).toInt();
        applyMotorTarget(2, value);
        return;
    }

    if (cmd.startsWith(rpmPrefix1))
    {
        long value = cmd.substring(strlen(rpmPrefix1)).toInt();
        applyMotorRpm(1, value);
        return;
    }

    if (cmd.startsWith(rpmPrefix2))
    {
        long value = cmd.substring(strlen(rpmPrefix2)).toInt();
        applyMotorRpm(2, value);
        return;
    }

}

void pollSerialCommands()
{
    while (Serial.available() > 0)
    {
        char ch = (char)Serial.read();
        if (ch == '\r')
        {
            continue;
        }
        if (ch == '\n')
        {
            handleSerialCommand(serialCmdBuf);
            serialCmdBuf = "";
            continue;
        }

        if (serialCmdBuf.length() < 80)
        {
            serialCmdBuf += ch;
        }
    }
}

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
    if (DEBUG_SERIAL)
    {
        Serial.println("Dual bipolar stepper + dual rotary encoder start");
        Serial.println("ENC1: motor1 (SW: sync mode toggle)");
        Serial.println("ENC2: motor2 (SW: reset)");
    }
}

// --- Encoder1: monitor only (no motor control) ---
void handleEncoder1()
{
    int clkState = digitalRead(ENC1_CLK_PIN);

    if (lastClk1State == HIGH && clkState == LOW)
    {
        int dtState = digitalRead(ENC1_DT_PIN);
        long delta = (dtState != clkState) ? 1 : -1;
        enc1_clicks += (delta > 0) ? 1 : -1;

        if (DEBUG_SERIAL)
        {
            Serial.print("ENC1 delta=");
            Serial.print(delta);
            Serial.println();
        }
    }

    lastClk1State = clkState;
}

// --- Encoder2: monitor only (no motor control) ---
void handleEncoder2()
{
    int clkState = digitalRead(ENC2_CLK_PIN);

    if (lastClk2State == HIGH && clkState == LOW)
    {
        int dtState = digitalRead(ENC2_DT_PIN);
        long delta = (dtState != clkState) ? 1 : -1;
        enc2_clicks += (delta > 0) ? 1 : -1;

        if (DEBUG_SERIAL)
        {
            Serial.print("ENC2 delta=");
            Serial.print(delta);
            Serial.println();
        }
    }

    lastClk2State = clkState;
}

// --- SW1: syncモード切り替え ---
void handleSwitch1()
{
    int swState = digitalRead(ENC1_SW_PIN);
    unsigned long now = millis();

    if (swState != lastSw1State)
    {
        lastSw1ChangeMs = now;
        lastSw1State = swState;
    }

    if ((now - lastSw1ChangeMs) > SW_DEBOUNCE_MS && swState == LOW)
    {
        syncMode = !syncMode;
        if (DEBUG_SERIAL)
        {
            Serial.print("syncMode=");
            Serial.println(syncMode ? "ON" : "OFF");
        }

        while (digitalRead(ENC1_SW_PIN) == LOW)
        {
            motor1.run();
            motor2.run();
        }
    }
}

// --- SW2: monitor reset (encoder counters only) ---
void handleSwitch2()
{
    int swState = digitalRead(ENC2_SW_PIN);
    unsigned long now = millis();

    if (swState != lastSw2State)
    {
        lastSw2ChangeMs = now;
        lastSw2State = swState;
    }

    if ((now - lastSw2ChangeMs) > SW_DEBOUNCE_MS && swState == LOW)
    {
        enc1_clicks = 0;
        enc2_clicks = 0;
        if (DEBUG_SERIAL)
        {
            Serial.println("RESET: enc1=0 enc2=0");
        }

        while (digitalRead(ENC2_SW_PIN) == LOW)
        {
            motor1.run();
            motor2.run();
        }
    }
}

void loop()
{
    unsigned long nowMs = millis();
    unsigned long nowUs = micros();
    
    if (lastLoopTickMs > 0)
    {
        loopPeriodMs = nowMs - lastLoopTickMs;
    }
    lastLoopTickMs = nowMs;
    
    if (lastLoopTickUs > 0)
    {
        loopPeriodUs = nowUs - lastLoopTickUs;
    }
    lastLoopTickUs = nowUs;

    if (loopRateWindowStartMs == 0)
    {
        loopRateWindowStartMs = nowMs;
    }
    loopRateWindowCount++;

    unsigned long rateDtMs = nowMs - loopRateWindowStartMs;
    if (rateDtMs >= 1000)
    {
        loopRateHz = (long)((1000.0 * (double)loopRateWindowCount / (double)rateDtMs) + 0.5);
        loopRateWindowCount = 0;
        loopRateWindowStartMs = nowMs;
    }

    pollSerialCommands();

    handleEncoder1();
    handleEncoder2();
    handleSwitch1();
    handleSwitch2();

    // 常に位置制御: 目標値変更時に移動を開始し、RPM設定は最大速度として反映
    motor1.run();
    motor2.run();
    
    // EPICS形式でデータ出力
    outputEpicsData();
}

// --- Output EPICS format data ---
void outputEpicsData()
{
    unsigned long now = millis();
    
    // Output at regular intervals for EPICS
    if (now - lastEpicsUpdate >= EPICS_UPDATE_INTERVAL)
    {
        lastEpicsUpdate = now;
        
        // Format:
        // ENC1:value,ENC2:value,MTR1:value,MTR2:value,SYNC:value,RPM1:value,RPM2:value,LOOP_HZ:value,LOOP_MS:value,LOOP_US:value,UPTIME_MS:value
        Serial.print("ENC1:");
        Serial.print(enc1_clicks);
        Serial.print(",ENC2:");
        Serial.print(enc2_clicks);
        Serial.print(",MTR1:");
        Serial.print(motor1.currentPosition());
        Serial.print(",MTR2:");
        Serial.print(motor2.currentPosition());
        Serial.print(",SYNC:");
        Serial.print(syncMode ? 1 : 0);
        Serial.print(",RPM1:");
        Serial.print(rpmCmd1);
        Serial.print(",RPM2:");
        Serial.print(rpmCmd2);
        Serial.print(",LOOP_HZ:");
        Serial.print(loopRateHz);
        Serial.print(",LOOP_MS:");
        Serial.print(loopPeriodMs);
        Serial.print(",LOOP_US:");
        Serial.print(loopPeriodUs);
        Serial.print(",UPTIME_MS:");
        Serial.println(now);
    }
}

// ライブラリインストール: arduino-cli lib install "AccelStepper"
// コンパイル例: arduino-cli compile --fqbn arduino:avr:uno .
// 書き込み例:   arduino-cli upload -p COM4 --fqbn arduino:avr:uno .
// シリアル監視: arduino-cli monitor -p COM4 --config baudrate=115200
// arduino-cli monitor -p /dev/ttyACM0 --config baudrate=115200
