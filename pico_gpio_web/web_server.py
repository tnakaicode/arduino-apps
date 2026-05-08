#!/usr/bin/env python3
"""
RPi5 上で動く Flask Web サーバー
ブラウザから周波数を指示 → シリアル経由で Pico の GP15 を ON/OFF 制御
起動: python3 web_server.py
アクセス: http://<RPiのIP>:5000
"""

import threading
import time
from flask import Flask, jsonify, render_template_string, request
import serial

SERIAL_PORT = "/dev/ttyACM1"
BAUD_RATE = 115200

app = Flask(__name__)
ser = None
ser_lock = threading.Lock()
current_freq = 0.0

HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Pico GPIO Controller</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Segoe UI', sans-serif; background: #1a1a2e; color: #eee; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
    .card { background: #16213e; border-radius: 16px; padding: 40px; width: 380px; box-shadow: 0 8px 32px rgba(0,0,0,0.4); }
    h1 { font-size: 1.4rem; margin-bottom: 8px; color: #e94560; text-align: center; }
    .subtitle { text-align: center; color: #aaa; font-size: 0.85rem; margin-bottom: 32px; }
    .freq-display { text-align: center; font-size: 3rem; font-weight: bold; color: #0f3460; background: #e94560; border-radius: 12px; padding: 16px; margin-bottom: 24px; letter-spacing: 2px; }
    .freq-display span { font-size: 1rem; color: #ffd; }
    input[type=range] { width: 100%; accent-color: #e94560; margin-bottom: 12px; cursor: pointer; }
    .range-labels { display: flex; justify-content: space-between; font-size: 0.75rem; color: #888; margin-bottom: 24px; }
    .input-row { display: flex; gap: 10px; margin-bottom: 24px; }
    .input-row input[type=number] { flex: 1; padding: 10px; border: 1px solid #e94560; background: #0f3460; color: #fff; border-radius: 8px; font-size: 1rem; }
    .input-row button { padding: 10px 18px; background: #e94560; border: none; border-radius: 8px; color: white; font-size: 1rem; cursor: pointer; }
    .input-row button:hover { background: #c73652; }
    .btn-row { display: flex; gap: 10px; }
    .btn { flex: 1; padding: 14px; border: none; border-radius: 10px; font-size: 1rem; cursor: pointer; transition: 0.2s; }
    .btn-start { background: #4caf50; color: white; }
    .btn-start:hover { background: #388e3c; }
    .btn-stop  { background: #f44336; color: white; }
    .btn-stop:hover  { background: #c62828; }
    .status { margin-top: 20px; text-align: center; font-size: 0.85rem; color: #aaa; }
    .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: #555; margin-right: 6px; }
    .dot.on { background: #4caf50; box-shadow: 0 0 8px #4caf50; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Pico GPIO Controller</h1>
    <p class="subtitle">GP15 ON/OFF &nbsp;|&nbsp; /dev/ttyACM1</p>

    <div class="freq-display" id="freqDisplay">0.0 <span>Hz</span></div>

    <input type="range" id="slider" min="0.1" max="50" step="0.1" value="1.0"
           oninput="updateFromSlider(this.value)">
    <div class="range-labels"><span>0.1 Hz</span><span>10 Hz</span><span>50 Hz</span></div>

    <div class="input-row">
      <input type="number" id="freqInput" min="0.1" max="1000" step="0.1" value="1.0" placeholder="周波数 (Hz)">
      <button onclick="applyInput()">SET</button>
    </div>

    <div class="btn-row">
      <button class="btn btn-start" onclick="sendFreq()">▶ START</button>
      <button class="btn btn-stop"  onclick="sendStop()">■ STOP</button>
    </div>

    <div class="status"><span class="dot" id="statusDot"></span><span id="statusText">---</span></div>
    <div class="status" id="measureText" style="margin-top:6px; color:#4fc3f7;"></div>
  </div>

  <script>
    let targetFreq = 1.0;

    function updateFromSlider(v) {
      targetFreq = parseFloat(v);
      document.getElementById('freqDisplay').innerHTML = targetFreq.toFixed(1) + ' <span>Hz</span>';
      document.getElementById('freqInput').value = targetFreq.toFixed(1);
    }

    function applyInput() {
      const v = parseFloat(document.getElementById('freqInput').value);
      if (isNaN(v) || v <= 0) return;
      targetFreq = v;
      document.getElementById('slider').value = Math.min(v, 50);
      document.getElementById('freqDisplay').innerHTML = targetFreq.toFixed(1) + ' <span>Hz</span>';
    }

    async function sendFreq() {
      const res = await fetch('/set', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({freq: targetFreq})
      });
      const data = await res.json();
      updateStatus(data);
    }

    async function sendStop() {
      const res = await fetch('/stop', {method: 'POST'});
      const data = await res.json();
      document.getElementById('freqDisplay').innerHTML = '0.0 <span>Hz</span>';
      updateStatus(data);
    }

    function updateStatus(data) {
      const dot = document.getElementById('statusDot');
      const txt = document.getElementById('statusText');
      if (data.ok) {
        dot.className = 'dot on';
        txt.textContent = data.message || 'OK';
      } else {
        dot.className = 'dot';
        txt.textContent = data.error || 'Error';
      }
    }

    // 定期的にステータス更新
    setInterval(async () => {
      try {
        const res = await fetch('/status');
        const data = await res.json();
        if (data.freq > 0) {
          document.getElementById('statusDot').className = 'dot on';
          document.getElementById('statusText').textContent = `実行中 ${data.freq} Hz`;
        } else {
          document.getElementById('statusDot').className = 'dot';
          document.getElementById('statusText').textContent = '停止中';
        }
        document.getElementById('measureText').textContent =
          `GP15: DUTY ${data.duty}%  |  GP26: ${data.volt} V`;
      } catch(e) {}
    }, 2000);
  </script>
</body>
</html>
"""


def open_serial():
    global ser
    try:
        # HUPCLを無効化（ポートopen/close時にDTRがトグルしてPicoがリセットされるのを防ぐ）
        import subprocess
        subprocess.run(["stty", "-F", SERIAL_PORT, "-hupcl"], check=False)
        ser = serial.Serial()
        ser.port = SERIAL_PORT
        ser.baudrate = BAUD_RATE
        ser.timeout = 1
        ser.dsrdtr = False
        ser.rtscts = False
        ser.open()
        ser.dtr = False
        ser.rts = False
        time.sleep(0.3)
        ser.reset_input_buffer()
        print(f"[Serial] Connected: {SERIAL_PORT}")
    except Exception as e:
        print(f"[Serial] Failed to open {SERIAL_PORT}: {e}")
        ser = None


def send_command(cmd: str) -> str:
    global ser
    if ser is None or not ser.is_open:
        open_serial()
    if ser is None:
        return "ERROR: serial not available"
    with ser_lock:
        ser.write((cmd + "\n").encode())
        time.sleep(0.05)
        resp = ser.readline().decode(errors="replace").strip()
    return resp


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/set", methods=["POST"])
def set_freq():
    global current_freq
    data = request.get_json(force=True)
    hz = float(data.get("freq", 1.0))
    hz = max(0.1, min(hz, 1000.0))
    resp = send_command(f"FREQ:{hz:.2f}")
    current_freq = hz
    return jsonify(ok=True, message=f"FREQ {hz:.2f} Hz → {resp}")


@app.route("/stop", methods=["POST"])
def stop():
    global current_freq
    resp = send_command("STOP")
    current_freq = 0.0
    return jsonify(ok=True, message=f"STOP → {resp}")


@app.route("/status")
def status():
    resp = send_command("STATUS")
    # STATUS FREQ:10.0 DUTY:50.0 PIN:1 VOLT:1.234 を解析
    freq = current_freq
    duty = 0.0
    volt = 0.0
    try:
        for part in resp.split():
            if part.startswith("FREQ:"):
                freq = float(part[5:])
            elif part.startswith("DUTY:"):
                duty = float(part[5:])
            elif part.startswith("VOLT:"):
                volt = float(part[5:])
    except Exception:
        pass
    return jsonify(freq=freq, duty=duty, volt=volt, raw=resp)


if __name__ == "__main__":
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)  # アクセスログを抑制
    open_serial()
    print("Web server starting on http://0.0.0.0:8080")
    app.run(host="0.0.0.0", port=8080, debug=False)
