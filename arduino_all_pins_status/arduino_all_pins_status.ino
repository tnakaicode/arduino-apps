

#include <Arduino.h>
// デジタルピンのモード管理
String digital_modes[14]; // D0-D13
int digital_values[14];   // D0-D13

// アナログピンのモード・値管理
String analog_modes[6];   // A0-A5: "INPUT" or "OUTPUT"
int analog_pwm_values[6]; // PWM値(0-255)

void setup()
{
  // --- Reset直後にLED点滅（5秒間）---
  pinMode(13, OUTPUT);
  for (int i = 0; i < 10; ++i)
  {
    digitalWrite(13, HIGH);
    delay(250);
    digitalWrite(13, LOW);
    delay(250);
  }
  // --- 通常初期化 ---
  analog_modes[0] = "INPUT";
  analog_pwm_values[0] = 0;
  analog_modes[1] = "INPUT";
  analog_pwm_values[1] = 0;
  analog_modes[2] = "INPUT";
  analog_pwm_values[2] = 0;
  analog_modes[3] = "INPUT";
  analog_pwm_values[3] = 0;
  analog_modes[4] = "INPUT";
  analog_pwm_values[4] = 0;
  analog_modes[5] = "INPUT";
  analog_pwm_values[5] = 0;
  Serial.begin(9600);
  // D0, D1はUNUSED
  digital_modes[0] = "UNUSED";
  digital_values[0] = 0;
  digital_modes[1] = "UNUSED";
  digital_values[1] = 0;
  // D2-D13 INPUT_PULLUP
  pinMode(2, INPUT_PULLUP);
  digital_modes[2] = "INPUT";
  digital_values[2] = 0;
  pinMode(3, INPUT_PULLUP);
  digital_modes[3] = "INPUT";
  digital_values[3] = 0;
  pinMode(4, INPUT_PULLUP);
  digital_modes[4] = "INPUT";
  digital_values[4] = 0;
  pinMode(5, INPUT_PULLUP);
  digital_modes[5] = "INPUT";
  digital_values[5] = 0;
  pinMode(6, INPUT_PULLUP);
  digital_modes[6] = "INPUT";
  digital_values[6] = 0;
  pinMode(7, INPUT_PULLUP);
  digital_modes[7] = "INPUT";
  digital_values[7] = 0;
  pinMode(8, INPUT_PULLUP);
  digital_modes[8] = "INPUT";
  digital_values[8] = 0;
  pinMode(9, INPUT_PULLUP);
  digital_modes[9] = "INPUT";
  digital_values[9] = 0;
  pinMode(10, INPUT_PULLUP);
  digital_modes[10] = "INPUT";
  digital_values[10] = 0;
  pinMode(11, INPUT_PULLUP);
  digital_modes[11] = "INPUT";
  digital_values[11] = 0;
  pinMode(12, INPUT_PULLUP);
  digital_modes[12] = "INPUT";
  digital_values[12] = 0;
  pinMode(13, INPUT_PULLUP);
  digital_modes[13] = "INPUT";
  digital_values[13] = 0;
}

void loop()
{
  if (Serial.available())
  {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd == "READ")
    {
      send_all_pin_status();
    }
    else if (cmd.startsWith("SETMODE"))
    {
      // 例: SETMODE,D3,OUTPUT または SETMODE,A0,OUTPUT
      int d_idx = cmd.indexOf(",");
      int d2_idx = cmd.indexOf(",", d_idx + 1);
      String pin_str = cmd.substring(d_idx + 1, d2_idx);
      String mode = cmd.substring(d2_idx + 1);
      if (pin_str.startsWith("D"))
      {
        int pin = pin_str.substring(1).toInt();
        if (pin >= 2 && pin <= 13)
        {
          if (mode == "OUTPUT")
          {
            pinMode(pin, OUTPUT);
            digital_modes[pin] = "OUTPUT";
          }
          else if (mode == "INPUT_PULLUP")
          {
            pinMode(pin, INPUT_PULLUP);
            digital_modes[pin] = "INPUT_PULLUP";
          }
          else // "INPUT"
          {
            pinMode(pin, INPUT);
            digital_modes[pin] = "INPUT";
          }
        }
      }
      else if (pin_str.startsWith("A"))
      {
        int idx = pin_str.substring(1).toInt();
        if (idx >= 0 && idx < 6)
        {
          analog_modes[idx] = mode;
        }
      }
    }
    else if (cmd.startsWith("SETVAL"))
    {
      // 例: SETVAL,D3,1 または SETVAL,A0,PWM,128
      int d_idx = cmd.indexOf(",");
      int d2_idx = cmd.indexOf(",", d_idx + 1);
      String pin_str = cmd.substring(d_idx + 1, d2_idx);
      String rest = cmd.substring(d2_idx + 1);
      if (pin_str.startsWith("D"))
      {
        int pin = pin_str.substring(1).toInt();
        int val = rest.toInt();
        if (pin >= 2 && pin <= 13 && digital_modes[pin] == "OUTPUT")
        {
          digitalWrite(pin, val);
          digital_values[pin] = val;
        }
      }
      else if (pin_str.startsWith("A"))
      {
        int idx = pin_str.substring(1).toInt();
        if (idx >= 0 && idx < 6 && analog_modes[idx] == "OUTPUT")
        {
          int cidx = rest.indexOf(",");
          if (cidx > 0)
          {
            String typ = rest.substring(0, cidx);
            String sval = rest.substring(cidx + 1);
            if (typ == "PWM")
            {
              int pwm = sval.toInt();
              if (pwm >= 0 && pwm <= 255)
              {
                analogWrite(idx + A0, pwm);
                analog_pwm_values[idx] = pwm;
              }
            }
          }
        }
      }
    }
  }
  // 500msごとに状態送信
  static unsigned long lastSend = 0;
  if (millis() - lastSend > 10)
  {
    send_all_pin_status();
    lastSend = millis();
  }
}

void send_all_pin_status()
{
  String result = "DI/O:";
  // D0, D1
  result += "UNUSED,?;";
  result += "UNUSED,?;";
  // D2-D13
  result += (digital_modes[2] == "OUTPUT" ? digital_modes[2] + "," + String(digital_values[2]) : digital_modes[2] + "," + String(digitalRead(2))) + ";";
  result += (digital_modes[3] == "OUTPUT" ? digital_modes[3] + "," + String(digital_values[3]) : digital_modes[3] + "," + String(digitalRead(3))) + ";";
  result += (digital_modes[4] == "OUTPUT" ? digital_modes[4] + "," + String(digital_values[4]) : digital_modes[4] + "," + String(digitalRead(4))) + ";";
  result += (digital_modes[5] == "OUTPUT" ? digital_modes[5] + "," + String(digital_values[5]) : digital_modes[5] + "," + String(digitalRead(5))) + ";";
  result += (digital_modes[6] == "OUTPUT" ? digital_modes[6] + "," + String(digital_values[6]) : digital_modes[6] + "," + String(digitalRead(6))) + ";";
  result += (digital_modes[7] == "OUTPUT" ? digital_modes[7] + "," + String(digital_values[7]) : digital_modes[7] + "," + String(digitalRead(7))) + ";";
  result += (digital_modes[8] == "OUTPUT" ? digital_modes[8] + "," + String(digital_values[8]) : digital_modes[8] + "," + String(digitalRead(8))) + ";";
  result += (digital_modes[9] == "OUTPUT" ? digital_modes[9] + "," + String(digital_values[9]) : digital_modes[9] + "," + String(digitalRead(9))) + ";";
  result += (digital_modes[10] == "OUTPUT" ? digital_modes[10] + "," + String(digital_values[10]) : digital_modes[10] + "," + String(digitalRead(10))) + ";";
  result += (digital_modes[11] == "OUTPUT" ? digital_modes[11] + "," + String(digital_values[11]) : digital_modes[11] + "," + String(digitalRead(11))) + ";";
  result += (digital_modes[12] == "OUTPUT" ? digital_modes[12] + "," + String(digital_values[12]) : digital_modes[12] + "," + String(digitalRead(12))) + ";";
  result += (digital_modes[13] == "OUTPUT" ? digital_modes[13] + "," + String(digital_values[13]) : digital_modes[13] + "," + String(digitalRead(13)));
  result += ";AI/O:";
  for (int i = 0; i < 6; i++)
  {
    if (analog_modes[i] == "OUTPUT")
    {
      result += String(analog_pwm_values[i]);
    }
    else
    {
      result += String(analogRead(i));
    }
    if (i < 5)
      result += ",";
  }
  Serial.println(result);
}