# Raspberry Pi Pico W - MicroPython
# WiFi接続 + Webサーバー + GP15 GPIO制御 + GP26 ADC計測

import network
import socket
import machine
import utime
import gc

# === WiFi設定（config.txtから読み込み） ===
try:
    with open('/config.txt', 'r') as f:
        WIFI_SSID = f.readline().strip()
        WIFI_PASS = f.readline().strip()
except:
    WIFI_SSID = "default_ssid"
    WIFI_PASS = "default_pass"

# === GPIO設定 ===
PIN_NUM = 15
pin = machine.Pin(PIN_NUM, machine.Pin.OUT)
pin.off()
led = machine.Pin("LED", machine.Pin.OUT)  # Pico W内蔵LED

adc = machine.ADC(machine.Pin(26))
VREF = 3.3

# === 状態変数 ===
freq_hz = 0.0
running = False
timer = machine.Timer()

def toggle_cb(t):
    pin.toggle()

def set_frequency(hz):
    global freq_hz, running
    freq_hz = hz
    if hz > 0:
        period_ms = int(500.0 / hz)
        if period_ms < 1:
            period_ms = 1
        timer.init(period=period_ms, mode=machine.Timer.PERIODIC, callback=toggle_cb)
        running = True
    else:
        timer.deinit()
        pin.off()
        running = False

def get_voltage():
    total = sum(adc.read_u16() for _ in range(16))
    return round((total // 16) / 65535 * VREF, 3)

# === WiFi接続 ===
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.ifconfig(('192.168.3.100', '255.255.255.0', '192.168.3.1', '192.168.3.1'))
    wlan.connect(WIFI_SSID, WIFI_PASS)
    print("WiFi接続中...")
    for _ in range(20):
        if wlan.isconnected():
            ip = wlan.ifconfig()[0]
            print("接続完了 IP:", ip)
            led.on()
            return ip
        led.toggle()
        utime.sleep(0.5)
    print("WiFi接続失敗")
    led.off()
    return None

# === HTML ===
HTML = """\
HTTP/1.0 200 OK
Content-Type: text/html

<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pico W GPIO</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:sans-serif;background:#1a1a2e;color:#eee;display:flex;justify-content:center;align-items:center;min-height:100vh}
.card{background:#16213e;border-radius:16px;padding:32px;width:360px;box-shadow:0 8px 32px rgba(0,0,0,.4)}
h1{font-size:1.3rem;color:#e94560;text-align:center;margin-bottom:24px}
.disp{text-align:center;font-size:2.5rem;font-weight:bold;background:#e94560;border-radius:10px;padding:12px;margin-bottom:20px}
.disp span{font-size:.9rem}
input[type=range]{width:100%;accent-color:#e94560;margin-bottom:8px}
.labels{display:flex;justify-content:space-between;font-size:.75rem;color:#888;margin-bottom:16px}
.row{display:flex;gap:8px;margin-bottom:16px}
.row input{flex:1;padding:8px;border:1px solid #e94560;background:#0f3460;color:#fff;border-radius:8px;font-size:1rem}
.row button,.btn{padding:10px 14px;background:#e94560;border:none;border-radius:8px;color:#fff;font-size:1rem;cursor:pointer}
.btns{display:flex;gap:8px}
.go{flex:1;padding:12px;border:none;border-radius:10px;font-size:1rem;cursor:pointer;background:#4caf50;color:#fff}
.st{flex:1;padding:12px;border:none;border-radius:10px;font-size:1rem;cursor:pointer;background:#f44336;color:#fff}
.info{margin-top:16px;text-align:center;font-size:.8rem;color:#aaa}
.volt{margin-top:8px;text-align:center;font-size:.85rem;color:#4fc3f7}
</style>
</head>
<body>
<div class="card">
<h1>Pico W GPIO Controller</h1>
<div class="disp" id="d">0.0 <span>Hz</span></div>
<input type="range" id="sl" min="0.1" max="100" step="0.1" value="1" oninput="upd(this.value)">
<div class="labels"><span>0.1Hz</span><span>50Hz</span><span>100Hz</span></div>
<div class="row">
  <input type="number" id="fi" min="0.1" max="10000" step="0.1" value="1">
  <button onclick="applyInput()">SET</button>
</div>
<div class="btns">
  <button class="go" onclick="go()">&#9654; START</button>
  <button class="st" onclick="stp()">&#9632; STOP</button>
</div>
<div class="info" id="inf">---</div>
<div class="volt" id="vlt"></div>
</div>
<script>
let tgt=1.0;
function upd(v){tgt=parseFloat(v);document.getElementById('d').innerHTML=tgt.toFixed(1)+' <span>Hz</span>';document.getElementById('fi').value=tgt.toFixed(1);}
function applyInput(){let v=parseFloat(document.getElementById('fi').value);if(!isNaN(v)&&v>0){tgt=v;document.getElementById('sl').value=Math.min(v,100);upd(tgt);}}
async function go(){let r=await fetch('/set?freq='+tgt);let t=await r.text();document.getElementById('inf').textContent=t;}
async function stp(){let r=await fetch('/stop');let t=await r.text();document.getElementById('inf').textContent=t;document.getElementById('d').innerHTML='0.0 <span>Hz</span>';}
setInterval(async()=>{try{let r=await fetch('/status');let d=await r.json();
  document.getElementById('inf').textContent=d.freq>0?'動作中 '+d.freq+' Hz':'停止中';
  document.getElementById('vlt').textContent='GP26: '+d.volt+' V';}catch(e){}},2000);
</script>
</body>
</html>"""

def parse_query(path):
    if '?' in path:
        _, q = path.split('?', 1)
        params = {}
        for kv in q.split('&'):
            if '=' in kv:
                k, v = kv.split('=', 1)
                params[k] = v
        return params
    return {}

def handle(conn):
    try:
        req = conn.recv(512).decode('utf-8', 'ignore')
        first = req.split('\r\n')[0] if req else ''
        parts = first.split(' ')
        path = parts[1] if len(parts) > 1 else '/'

        if path == '/' or path.startswith('/?'):
            conn.send(HTML)

        elif path.startswith('/set'):
            params = parse_query(path)
            hz = float(params.get('freq', '1'))
            hz = max(0.1, min(hz, 10000.0))
            set_frequency(hz)
            conn.send('HTTP/1.0 200 OK\r\nContent-Type: text/plain\r\n\r\nOK FREQ:' + str(hz))

        elif path == '/stop':
            set_frequency(0)
            conn.send('HTTP/1.0 200 OK\r\nContent-Type: text/plain\r\n\r\nOK STOP')

        elif path == '/status':
            volt = get_voltage()
            body = '{{"freq":{},"volt":{},"pin":{}}}'.format(freq_hz, volt, pin.value())
            conn.send('HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n' + body)

        elif path == '/upload' and req.startswith('POST'):
            # POSTボディを取得
            if '\r\n\r\n' in req:
                body = req.split('\r\n\r\n', 1)[1]
            else:
                body = ''
            # Content-Lengthで追加受信
            cl = 0
            for line in req.split('\r\n'):
                if line.lower().startswith('content-length:'):
                    cl = int(line.split(':', 1)[1].strip())
            while len(body.encode('utf-8', 'ignore')) < cl:
                chunk = conn.recv(512)
                if not chunk:
                    break
                body += chunk.decode('utf-8', 'ignore')
            with open('/main.py', 'w') as f:
                f.write(body)
            conn.send('HTTP/1.0 200 OK\r\nContent-Type: text/plain\r\n\r\nOK UPLOADED. Rebooting...')
            conn.close()
            utime.sleep(1)
            machine.reset()

        else:
            conn.send('HTTP/1.0 404 Not Found\r\n\r\nNot Found')
    except Exception as e:
        print("handle error:", e)
    finally:
        conn.close()

# === メイン ===
ip = connect_wifi()
if ip:
    addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr)
    s.listen(2)
    print("サーバー起動: http://" + ip)
    while True:
        gc.collect()
        try:
            conn, _ = s.accept()
            handle(conn)
        except Exception as e:
            print("server error:", e)
else:
    print("WiFi失敗。オフラインで起動します。")
    while True:
        pin.toggle()
        utime.sleep_ms(500)


# 
# curl -X POST http://192.168.3.100/upload \
#   -H "Content-Type: text/plain" \
#   --data-binary @pico_gpio_web/picow_main.py
#   