import asyncio
import contextlib
import glob
import os
import threading
import time
from datetime import datetime

import cv2
from aiohttp import web


HOST = '0.0.0.0'
WEB_PORT = 5000
CAMERA_PORT = '/dev/video0'
AUTO_CONNECT = True


HTML_PAGE = """<!doctype html>
<html lang=\"ja\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Camera Remote</title>
  <style>
    :root {
      --bg: #0f172a;
      --card: #111827;
      --card2: #1f2937;
      --accent: #0ea5e9;
      --accent2: #22c55e;
      --text: #e5e7eb;
      --muted: #9ca3af;
      --danger: #ef4444;
    }
    body {
      margin: 0;
      font-family: "Noto Sans JP", "Hiragino Sans", sans-serif;
      color: var(--text);
      background: radial-gradient(circle at 20% 0%, #1e293b, #0b1023 60%);
      min-height: 100vh;
    }
    .wrap {
      max-width: 1200px;
      margin: 0 auto;
      padding: 20px;
    }
    h1 {
      margin: 0 0 14px;
      font-size: 1.4rem;
      letter-spacing: 0.02em;
    }
    .grid {
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 16px;
    }
    @media (max-width: 900px) {
      .grid {
        grid-template-columns: 1fr;
      }
    }
    .card {
      background: linear-gradient(160deg, var(--card), var(--card2));
      border: 1px solid #334155;
      border-radius: 14px;
      padding: 14px;
      box-shadow: 0 8px 30px rgba(0, 0, 0, 0.25);
    }
    #stream {
      width: 100%;
      border-radius: 10px;
      background: #000;
      aspect-ratio: 16/9;
      object-fit: contain;
    }
    .controls {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      margin-top: 12px;
    }
    .wide {
      grid-column: 1 / -1;
    }
    button, select, input {
      width: 100%;
      border: 1px solid #475569;
      background: #0b1220;
      color: var(--text);
      padding: 10px;
      border-radius: 10px;
      font-size: 0.95rem;
    }
    button {
      cursor: pointer;
      transition: transform 120ms ease, border-color 120ms ease;
    }
    button:hover {
      transform: translateY(-1px);
      border-color: var(--accent);
    }
    .ok {
      border-color: var(--accent2);
    }
    .danger {
      border-color: var(--danger);
    }
    .muted {
      color: var(--muted);
      font-size: 0.88rem;
      margin-top: 10px;
      line-height: 1.5;
    }
    .status {
      display: grid;
      gap: 8px;
      margin-bottom: 10px;
    }
    .status div {
      display: flex;
      justify-content: space-between;
      font-size: 0.95rem;
      border-bottom: 1px dashed #334155;
      padding-bottom: 4px;
    }
    .tag {
      color: var(--accent);
      font-weight: 700;
    }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <h1>Camera Remote (Browser View)</h1>
    <div class=\"grid\">
      <div class=\"card\">
        <img id=\"stream\" src=\"/stream.mjpg\" alt=\"camera stream\" />
      </div>
      <div class=\"card\">
        <div class=\"status\">
          <div><span>Camera</span><span id=\"cam\" class=\"tag\">-</span></div>
          <div><span>Recording</span><span id=\"rec\" class=\"tag\">-</span></div>
          <div><span>FPS</span><span id=\"fps\" class=\"tag\">-</span></div>
          <div><span>Resolution</span><span id=\"res\" class=\"tag\">-</span></div>
        </div>
        <div class=\"controls\">
          <select id=\"device\" class=\"wide\"></select>
          <button id=\"connect\" class=\"ok\">Connect</button>
          <button id=\"disconnect\" class=\"danger\">Disconnect</button>
          <input id=\"overlay\" class=\"wide\" placeholder=\"オーバーレイ文字列\" />
          <button id=\"save\">Save Image</button>
          <button id=\"recordStart\" class=\"ok\">Start Rec</button>
          <button id=\"recordStop\" class=\"danger\">Stop Rec</button>
        </div>
        <div class=\"muted\">同じネットワーク内の別PCから http://RaspberryPiのIP:5000 でアクセスできます。</div>
      </div>
    </div>
  </div>

  <script>
    async function j(url, opt) {
      const r = await fetch(url, opt || {});
      if (!r.ok) {
        const t = await r.text();
        throw new Error(t || r.statusText);
      }
      return r.json();
    }

    async function refreshDevices() {
      const data = await j('/api/devices');
      const sel = document.getElementById('device');
      sel.innerHTML = '';
      for (const d of data.devices) {
        const o = document.createElement('option');
        o.value = d.index;
        o.textContent = d.label;
        sel.appendChild(o);
      }
      if (typeof data.current_index === 'number') {
        sel.value = String(data.current_index);
      }
    }

    async function refreshStatus() {
      try {
        const s = await j('/api/status');
        document.getElementById('cam').textContent = s.connected ? 'connected' : 'disconnected';
        document.getElementById('rec').textContent = s.recording ? 'on' : 'off';
        document.getElementById('fps').textContent = s.fps.toFixed(1);
        document.getElementById('res').textContent = s.resolution || '-';
      } catch (_) {}
    }

    document.getElementById('connect').onclick = async () => {
      const idx = Number(document.getElementById('device').value || 0);
      await j('/api/connect', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({index: idx})
      });
      await refreshStatus();
    };

    document.getElementById('disconnect').onclick = async () => {
      await j('/api/disconnect', {method: 'POST'});
      await refreshStatus();
    };

    document.getElementById('save').onclick = async () => {
      await j('/api/save-image', {method: 'POST'});
      await refreshStatus();
    };

    document.getElementById('recordStart').onclick = async () => {
      await j('/api/start-recording', {method: 'POST'});
      await refreshStatus();
    };

    document.getElementById('recordStop').onclick = async () => {
      await j('/api/stop-recording', {method: 'POST'});
      await refreshStatus();
    };

    document.getElementById('overlay').onchange = async (e) => {
      await j('/api/overlay-text', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({text: e.target.value || ''})
      });
    };

    refreshDevices().catch(console.error);
    refreshStatus();
    setInterval(refreshStatus, 1000);
  </script>
</body>
</html>
"""


class CameraRemoteServer:
  def __init__(self, host="0.0.0.0", port=5000, camera_port='/dev/video0', out_dir=None):
    self.host = host
    self.port = port
    self.camera_port = camera_port
    self.out_dir = out_dir or os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(self.out_dir, exist_ok=True)

    self.cap = None
    self.device_index = 0
    self.overlay_text = ""

    self.frame_lock = threading.Lock()
    self.latest_frame = None

    self.connected = False
    self.recording = False
    self.video_writer = None

    self._frame_counter = 0
    self._fps = 0.0
    self._fps_last_tick = time.time()

    self.stop_event = threading.Event()
    self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
    self.capture_thread.start()

  def _list_devices(self):
        return [{'index': 0, 'label': self.camera_port}]

  def connect_camera(self, index=0):
        self.disconnect_camera()
        cap = cv2.VideoCapture(self.camera_port, cv2.CAP_V4L2)
        if not cap.isOpened():
            cap.release()
            raise RuntimeError(f'failed to open camera port={self.camera_port}')

        self.cap = cap
        self.device_index = 0
        self.connected = True

  def disconnect_camera(self):
        self.stop_recording()
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self.connected = False
        with self.frame_lock:
            self.latest_frame = None

  def _now_stamp(self):
        return datetime.now().strftime('%Y%m%d_%H%M%S')

  def _overlay(self, frame):
        out = frame.copy()
        stamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        lines = [stamp, f'FPS: {self._fps:.1f}']
        if self.recording:
            lines.append('REC')
        if self.overlay_text:
            lines.append(self.overlay_text)

        y = 28
        for text in lines:
            cv2.putText(
                out,
                text,
                (12, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )
            y += 28
        return out

  def _capture_loop(self):
        while not self.stop_event.is_set():
            if self.cap is None:
                time.sleep(0.05)
                continue

            ok, frame = self.cap.read()
            if not ok or frame is None:
                time.sleep(0.02)
                continue

            draw = self._overlay(frame)
            with self.frame_lock:
                self.latest_frame = draw

            if self.recording and self.video_writer is not None:
                self.video_writer.write(draw)

            self._frame_counter += 1
            now = time.time()
            elapsed = now - self._fps_last_tick
            if elapsed >= 1.0:
                self._fps = self._frame_counter / max(elapsed, 1e-6)
                self._frame_counter = 0
                self._fps_last_tick = now

  def save_image(self):
        with self.frame_lock:
            frame = None if self.latest_frame is None else self.latest_frame.copy()
        if frame is None:
            raise RuntimeError('no frame available')

        path = os.path.join(self.out_dir, f'camera_{self._now_stamp()}.png')
        if not cv2.imwrite(path, frame):
            raise RuntimeError('failed to save image')
        return path

  def start_recording(self):
        if self.recording:
            return None

        with self.frame_lock:
            frame = None if self.latest_frame is None else self.latest_frame.copy()
        if frame is None:
            raise RuntimeError('no frame available')

        h, w = frame.shape[:2]
        path = os.path.join(self.out_dir, f'camera_{self._now_stamp()}.mp4')
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(path, fourcc, max(10.0, self._fps or 30.0), (w, h))
        if not writer.isOpened():
            raise RuntimeError('failed to start recorder')

        self.video_writer = writer
        self.recording = True
        return path

  def stop_recording(self):
        if self.video_writer is not None:
            self.video_writer.release()
            self.video_writer = None
        self.recording = False

  def status(self):
        resolution = None
        with self.frame_lock:
            if self.latest_frame is not None:
                h, w = self.latest_frame.shape[:2]
                resolution = f'{w}x{h}'

        return {
            'connected': self.connected,
            'recording': self.recording,
            'fps': float(self._fps),
            'resolution': resolution,
            'current_index': self.device_index,
          'camera_port': self.camera_port,
            'output_dir': self.out_dir,
        }

  async def index(self, request):
        return web.Response(text=HTML_PAGE, content_type='text/html')

  async def api_status(self, request):
        return web.json_response(self.status())

  async def api_devices(self, request):
        return web.json_response({'devices': self._list_devices(), 'current_index': self.device_index})

  async def api_connect(self, request):
        data = await request.json()
        index = int(data.get('index', 0))
        self.connect_camera(index)
        return web.json_response({'ok': True, 'index': index})

  async def api_disconnect(self, request):
        self.disconnect_camera()
        return web.json_response({'ok': True})

  async def api_save_image(self, request):
        path = self.save_image()
        return web.json_response({'ok': True, 'path': path})

  async def api_start_recording(self, request):
        path = self.start_recording()
        return web.json_response({'ok': True, 'path': path})

  async def api_stop_recording(self, request):
        self.stop_recording()
        return web.json_response({'ok': True})

  async def api_overlay_text(self, request):
        data = await request.json()
        self.overlay_text = str(data.get('text', '')).strip()
        return web.json_response({'ok': True, 'text': self.overlay_text})

  async def stream(self, request):
        response = web.StreamResponse(
            status=200,
            headers={
                'Content-Type': 'multipart/x-mixed-replace; boundary=frame',
                'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
                'Pragma': 'no-cache',
            },
        )
        await response.prepare(request)

        try:
            while True:
                with self.frame_lock:
                    frame = None if self.latest_frame is None else self.latest_frame.copy()

                if frame is None:
                    frame = self._blank_frame()

                ok, encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if not ok:
                    await asyncio.sleep(0.05)
                    continue

                await response.write(b'--frame\r\n')
                await response.write(b'Content-Type: image/jpeg\r\n\r\n')
                await response.write(encoded.tobytes())
                await response.write(b'\r\n')
                await asyncio.sleep(0.03)
        except (asyncio.CancelledError, ConnectionResetError, RuntimeError):
            pass
        finally:
            with contextlib.suppress(Exception):
                await response.write_eof()

        return response

  def _blank_frame(self):
        img = cv2.UMat(480, 640, cv2.CV_8UC3).get()
        cv2.putText(
            img,
            'Camera not connected',
            (120, 240),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )
        return img

  def make_app(self):
        app = web.Application()
        app.router.add_get('/', self.index)
        app.router.add_get('/stream.mjpg', self.stream)

        app.router.add_get('/api/status', self.api_status)
        app.router.add_get('/api/devices', self.api_devices)
        app.router.add_post('/api/connect', self.api_connect)
        app.router.add_post('/api/disconnect', self.api_disconnect)
        app.router.add_post('/api/save-image', self.api_save_image)
        app.router.add_post('/api/start-recording', self.api_start_recording)
        app.router.add_post('/api/stop-recording', self.api_stop_recording)
        app.router.add_post('/api/overlay-text', self.api_overlay_text)

        async def on_shutdown(_app):
            self.stop_event.set()
            self.stop_recording()
            self.disconnect_camera()

        app.on_shutdown.append(on_shutdown)
        return app


def main():
    server = CameraRemoteServer(host=HOST, port=WEB_PORT, camera_port=CAMERA_PORT)

    if AUTO_CONNECT:
        try:
            server.connect_camera()
            print(f'[Camera] connected to port={CAMERA_PORT}')
        except Exception as exc:
            print(f'[Camera] auto connect failed: {exc}')

    print(f'[Web] open: http://{HOST}:{WEB_PORT}')
    web.run_app(server.make_app(), host=HOST, port=WEB_PORT)


if __name__ == '__main__':
    main()
