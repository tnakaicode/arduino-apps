
#include <WiFiS3.h>
#include <Arduino.h>
#include "wifi_config.h"  // WiFi設定（SSID, パスワード, 静的IP）

// #pragma once
// 
// --- WiFi設定（このファイルを編集してください）---
// const char *ssid     = "ssid"; // WiFiのSSID
// const char *password = "password";        // WiFiのパスワード
// --- 静的IPアドレス設定 ---
// IPAddress WIFI_LOCAL_IP(192, 168, 3, 123); // ArduinoのIPアドレス
// IPAddress WIFI_GATEWAY (192, 168, 3,   1); // ルーターのIPアドレス
// IPAddress WIFI_SUBNET  (255, 255, 255, 0); // サブネットマスク
// IPAddress WIFI_DNS     (192, 168, 3,   1); // DNS（通常はゲートウェイと同じ）

// arduino-cli compile --fqbn arduino:renesas_uno:unor4wifi .
// arduino-cli upload --fqbn arduino:renesas_uno:unor4wifi --port COM5 .

// --- 関数プロトタイプ宣言 ---
void print_network_info();
String get_all_pin_status();
void send_all_pin_status();
String get_http_path(const String &req);
String get_query_value(const String &path, const String &key);
void apply_pin_command(const String &path);
void send_web_page(WiFiClient &client);
void send_http_redirect(WiFiClient &client, const String &location);

// --- WiFi状態 ---
int status = WL_IDLE_STATUS;          // WiFiの状態格納
WiFiServer server(80);
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

  // --- WiFi静的IP設定（wifi_config.hから読み込み）---
  WiFi.config(WIFI_LOCAL_IP, WIFI_DNS, WIFI_GATEWAY, WIFI_SUBNET);
  WiFi.begin(ssid, password);

  // WiFiモジュールの確認
  if (WiFi.status() == WL_NO_MODULE)
  { // WiFiモジュールがない場合の処理
    Serial.println("Communication with WiFi module failed!");
    // don't continue
    while (true)
      ;
  }

  String fv = WiFi.firmwareVersion(); // WiFiモジュールのファームバージョンの取得
  if (fv < WIFI_FIRMWARE_LATEST_VERSION)
  { // ファームバージョンの確認（古い場合はアップデートを促すメッセージ)
    Serial.println("Please upgrade the firmware");
  }

  // WiFi接続
  Serial.print("Attempting to connect to WPA SSID: ");
  Serial.println(ssid); // WiFi接続に使うSSIDをシリアルモニタに表示

  int wifi_retry = 0;
  while (WiFi.status() != WL_CONNECTED && wifi_retry < 10)
  {
    delay(500);
    wifi_retry++;
  }
  if (WiFi.status() == WL_CONNECTED)
  {
    Serial.println("WiFi Connected");
  }
  else
  {
    Serial.println("WiFi Connect Failed");
  }
  server.begin();
  Serial.println("BOOT");
}

void loop()
{
  // --- Webサーバー応答 ---
  WiFiClient client = server.available();
  if (client)
  {
    String req = client.readStringUntil('\r');
    client.flush();
    if (req.startsWith("GET "))
    {
      String path = get_http_path(req);
      if (path.startsWith("/cmd?"))
      {
        apply_pin_command(path);
        send_http_redirect(client, "/");
      }
      else
      {
        send_web_page(client);
      }
    }
    delay(1);
    client.stop();
  }

  // --- 既存のシリアルコマンド処理 ---
  if (Serial.available())
  {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.length() == 0)
    {
      // 何も入力がなければ無視
      return;
    }
    if (cmd.equalsIgnoreCase("PING"))
    {
      Serial.println("PONG");
    }
    else if (cmd.equalsIgnoreCase("WIFISTATUS"))
    {
      int st = WiFi.status();
      String msg = "WiFi.status(): ";
      switch (st)
      {
      case WL_NO_SHIELD:
        msg += "NO_SHIELD";
        break;
      case WL_IDLE_STATUS:
        msg += "IDLE";
        break;
      case WL_NO_SSID_AVAIL:
        msg += "NO_SSID_AVAIL";
        break;
      case WL_SCAN_COMPLETED:
        msg += "SCAN_COMPLETED";
        break;
      case WL_CONNECTED:
        msg += "CONNECTED";
        break;
      case WL_CONNECT_FAILED:
        msg += "CONNECT_FAILED";
        break;
      case WL_CONNECTION_LOST:
        msg += "CONNECTION_LOST";
        break;
      case WL_DISCONNECTED:
        msg += "DISCONNECTED";
        break;
      default:
        msg += String(st);
        break;
      }
      Serial.println(msg);
    }
    else if (cmd == "READ")
    {
      send_all_pin_status();
      Serial.println("OK");
    }
    else if (cmd == "NETINFO")
    {
      print_network_info();
    }
    else if (cmd.equalsIgnoreCase("IP"))
    {
      Serial.print("IP: ");
      Serial.println(WiFi.localIP());
      Serial.println("OK");
    }
    else if (cmd.equalsIgnoreCase("WIFICONNECT"))
    {
      Serial.println("Trying WiFi connection...");
      WiFi.begin(ssid, password);
      int retry = 0;
      while (WiFi.status() != WL_CONNECTED && retry < 10) {
        delay(500);
        retry++;
      }
      if (WiFi.status() == WL_CONNECTED) {
        Serial.println("WiFi Connected");
      } else {
        Serial.println("WiFi Connect Failed");
      }
      print_network_info();
    }
    else if (cmd.startsWith("SETMODE"))
    {
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
          else
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
      Serial.println("OK");
    }
    else if (cmd.startsWith("SETVAL"))
    {
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
      Serial.println("OK");
    }
    else
    {
      Serial.println("NG");
    }
  }

  // 500msごとに状態送信
  static unsigned long lastSend = 0;
  if (millis() - lastSend > 500)
  {
    send_all_pin_status();
    lastSend = millis();
  }
}

// --- シリアルでネットワーク情報を出力する関数 ---
void print_network_info()
{
  Serial.println("--- Network Info ---");
  // WiFi接続状態
  int st = WiFi.status();
  String stmsg = "Status: ";
  switch (st) {
    case WL_NO_SHIELD: stmsg += "NO_SHIELD"; break;
    case WL_IDLE_STATUS: stmsg += "IDLE"; break;
    case WL_NO_SSID_AVAIL: stmsg += "NO_SSID_AVAIL"; break;
    case WL_SCAN_COMPLETED: stmsg += "SCAN_COMPLETED"; break;
    case WL_CONNECTED: stmsg += "CONNECTED"; break;
    case WL_CONNECT_FAILED: stmsg += "CONNECT_FAILED"; break;
    case WL_CONNECTION_LOST: stmsg += "CONNECTION_LOST"; break;
    case WL_DISCONNECTED: stmsg += "DISCONNECTED"; break;
    default: stmsg += String(st); break;
  }
  Serial.println(stmsg);
  Serial.print("SSID: ");
  Serial.println(WiFi.SSID());
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());
  Serial.print("Gateway: ");
  Serial.println(WiFi.gatewayIP());
  Serial.print("Subnet: ");
  Serial.println(WiFi.subnetMask());
  // WiFiS3: DNSはWiFi.dnsServerIP()が無い場合があるので省略または独自管理
  // MACアドレス取得はバッファを使う
  Serial.print("DNS: (fixed)");
  Serial.println();
  uint8_t mac[6];
  WiFi.macAddress(mac);
  Serial.print("MAC: ");
  for (int i = 0; i < 6; i++)
  {
    if (i > 0)
      Serial.print(":");
    if (mac[i] < 16)
      Serial.print("0");
    Serial.print(mac[i], HEX);
  }
  Serial.println();
  Serial.println("--------------------");
  Serial.println("OK");
}
// --- Web用: ピン状態をテキストで返す関数 ---
String get_all_pin_status()
{
  String result = "";
  for (int i = 2; i <= 13; i++)
  {
    result += "D" + String(i) + ": " + digital_modes[i] + ", " + String(digitalRead(i)) + "\n";
  }
  for (int i = 0; i < 6; i++)
  {
    result += "A" + String(i) + ": " + analog_modes[i] + ", " + String(analogRead(i)) + "\n";
  }
  return result;
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

String get_http_path(const String &req)
{
  int first_space = req.indexOf(' ');
  if (first_space < 0)
  {
    return "/";
  }
  int second_space = req.indexOf(' ', first_space + 1);
  if (second_space < 0)
  {
    return "/";
  }
  return req.substring(first_space + 1, second_space);
}

String get_query_value(const String &path, const String &key)
{
  int qidx = path.indexOf('?');
  if (qidx < 0)
  {
    return "";
  }
  String query = path.substring(qidx + 1);
  String pat = key + "=";
  int kidx = query.indexOf(pat);
  if (kidx < 0)
  {
    return "";
  }
  int start = kidx + pat.length();
  int end = query.indexOf('&', start);
  if (end < 0)
  {
    end = query.length();
  }
  return query.substring(start, end);
}

void apply_pin_command(const String &path)
{
  String op = get_query_value(path, "op");
  String pin_str = get_query_value(path, "pin");
  String val = get_query_value(path, "v");

  if (pin_str.startsWith("D"))
  {
    int pin = pin_str.substring(1).toInt();
    if (pin < 2 || pin > 13)
    {
      return;
    }

    if (op == "mode")
    {
      if (val == "OUTPUT")
      {
        pinMode(pin, OUTPUT);
        digital_modes[pin] = "OUTPUT";
      }
      else if (val == "INPUT_PULLUP")
      {
        pinMode(pin, INPUT_PULLUP);
        digital_modes[pin] = "INPUT_PULLUP";
      }
      else
      {
        pinMode(pin, INPUT);
        digital_modes[pin] = "INPUT";
      }
    }
    else if (op == "write")
    {
      if (digital_modes[pin] == "OUTPUT")
      {
        int dval = val.toInt() != 0 ? HIGH : LOW;
        digitalWrite(pin, dval);
        digital_values[pin] = dval;
      }
    }
    return;
  }

  if (pin_str.startsWith("A"))
  {
    int idx = pin_str.substring(1).toInt();
    if (idx < 0 || idx > 5)
    {
      return;
    }

    if (op == "mode")
    {
      if (val == "OUTPUT")
      {
        analog_modes[idx] = "OUTPUT";
      }
      else
      {
        analog_modes[idx] = "INPUT";
      }
    }
    else if (op == "pwm")
    {
      if (analog_modes[idx] == "OUTPUT")
      {
        int pwm = val.toInt();
        if (pwm < 0)
          pwm = 0;
        if (pwm > 255)
          pwm = 255;
        analogWrite(idx + A0, pwm);
        analog_pwm_values[idx] = pwm;
      }
    }
  }
}

void send_http_redirect(WiFiClient &client, const String &location)
{
  client.println("HTTP/1.1 302 Found");
  client.print("Location: ");
  client.println(location);
  client.println("Connection: close");
  client.println();
}

void send_web_page(WiFiClient &client)
{
  String html = "<!doctype html><html><head><meta charset='utf-8'>";
  html += "<meta name='viewport' content='width=device-width,initial-scale=1'>";
  html += "<meta http-equiv='refresh' content='2'>";
  html += "<title>UNO R4 WiFi Pin Control</title>";
  html += "<style>body{font-family:Arial,sans-serif;margin:12px;}table{border-collapse:collapse;width:100%;max-width:960px;}th,td{border:1px solid #ccc;padding:6px;font-size:13px;}a{margin-right:6px;white-space:nowrap;}h2,h3{margin:8px 0;}small{color:#555;}</style>";
  html += "</head><body>";
  html += "<h2>UNO R4 WiFi Pin Control</h2>";
  html += "<small>IP: ";
  html += WiFi.localIP().toString();
  html += " | SSID: ";
  html += WiFi.SSID();
  html += "</small>";

  html += "<h3>Digital Pins (D2-D13)</h3><table><tr><th>Pin</th><th>Mode</th><th>Value</th><th>Mode Cmd</th><th>Value Cmd</th></tr>";
  for (int pin = 2; pin <= 13; pin++)
  {
    html += "<tr><td>D" + String(pin) + "</td>";
    html += "<td>" + digital_modes[pin] + "</td>";
    html += "<td>";
    if (digital_modes[pin] == "OUTPUT")
    {
      html += String(digital_values[pin]);
    }
    else
    {
      html += String(digitalRead(pin));
    }
    html += "</td><td>";
    html += "<a href='/cmd?op=mode&pin=D" + String(pin) + "&v=INPUT'>INPUT</a>";
    html += "<a href='/cmd?op=mode&pin=D" + String(pin) + "&v=INPUT_PULLUP'>PULLUP</a>";
    html += "<a href='/cmd?op=mode&pin=D" + String(pin) + "&v=OUTPUT'>OUTPUT</a>";
    html += "</td><td>";
    html += "<a href='/cmd?op=write&pin=D" + String(pin) + "&v=1'>HIGH</a>";
    html += "<a href='/cmd?op=write&pin=D" + String(pin) + "&v=0'>LOW</a>";
    html += "</td></tr>";
  }
  html += "</table>";

  html += "<h3>Analog Pins (A0-A5)</h3><table><tr><th>Pin</th><th>Mode</th><th>Value</th><th>Mode Cmd</th><th>PWM Cmd</th></tr>";
  for (int i = 0; i < 6; i++)
  {
    html += "<tr><td>A" + String(i) + "</td>";
    html += "<td>" + analog_modes[i] + "</td>";
    html += "<td>";
    if (analog_modes[i] == "OUTPUT")
    {
      html += String(analog_pwm_values[i]);
    }
    else
    {
      html += String(analogRead(i));
    }
    html += "</td><td>";
    html += "<a href='/cmd?op=mode&pin=A" + String(i) + "&v=INPUT'>INPUT</a>";
    html += "<a href='/cmd?op=mode&pin=A" + String(i) + "&v=OUTPUT'>OUTPUT</a>";
    html += "</td><td>";
    html += "<a href='/cmd?op=pwm&pin=A" + String(i) + "&v=0'>0</a>";
    html += "<a href='/cmd?op=pwm&pin=A" + String(i) + "&v=128'>128</a>";
    html += "<a href='/cmd?op=pwm&pin=A" + String(i) + "&v=255'>255</a>";
    html += "</td></tr>";
  }
  html += "</table></body></html>";

  client.println("HTTP/1.1 200 OK");
  client.println("Content-Type: text/html");
  client.println("Connection: close");
  client.println();
  client.println(html);
}