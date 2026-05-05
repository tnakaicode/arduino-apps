import asyncio
import contextlib
import os
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from aiohttp import web

from PIL import Image, ImageDraw, ImageFont

# pkill -f rpi_camera/camera_remote_web.py || true
# ss -lntp | grep ':5000' || true

HOST = '0.0.0.0'
WEB_PORT = 5000
CAMERA_PORT = '/dev/video0'
AUTO_CONNECT = True

TARGET_FPS = 30.0
TIMELAPSE_INTERVAL_SEC = 2.0
TIMELAPSE_VIDEO_FPS = 30.0


HTML_PAGE = """<!doctype html>
<html lang=\"ja\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>カメラ遠隔モニター</title>
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
      max-width: 1280px;
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
    .status {
      display: grid;
      gap: 8px;
      margin-bottom: 10px;
    }
    .status div {
      display: flex;
      justify-content: space-between;
      border-bottom: 1px dashed #334155;
      padding-bottom: 4px;
      font-size: 0.95rem;
    }
    .tag {
      color: var(--accent);
      font-weight: 700;
    }
    .controls {
      display: flex;
      flex-direction: column;
      gap: 10px;
      margin-top: 12px;
    }
    .row2 {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    .row3 {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 10px;
    }
    @media (max-width: 900px) {
      .row2, .row3 {
        grid-template-columns: 1fr;
      }
    }
    button, input, select {
      width: 100%;
      border: 1px solid #475569;
      background: #0b1220;
      color: var(--text);
      padding: 10px;
      border-radius: 10px;
      font-size: 0.95rem;
      box-sizing: border-box;
    }
    button {
      cursor: pointer;
      transition: transform 120ms ease, border-color 120ms ease;
    }
    button:hover {
      transform: translateY(-1px);
      border-color: var(--accent);
    }
    .ok { border-color: var(--accent2); }
    .danger { border-color: var(--danger); }
    .muted {
      color: var(--muted);
      font-size: 0.86rem;
      margin-top: 10px;
      line-height: 1.5;
      word-break: break-all;
    }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <h1>カメラ遠隔モニター（ブラウザ）</h1>
    <div class=\"grid\">
      <div class=\"card\">
        <img id=\"stream\" src=\"/stream.mjpg\" alt=\"camera stream\" />
      </div>
      <div class=\"card\">
        <div class=\"status\">
          <div><span>カメラ</span><span id=\"cam\" class=\"tag\">-</span></div>
          <div><span>ポート</span><span id=\"camport\" class=\"tag\">-</span></div>
          <div><span>録画</span><span id=\"rec\" class=\"tag\">-</span></div>
          <div><span>タイムラプス</span><span id=\"tl\" class=\"tag\">-</span></div>
          <div><span>FPS</span><span id=\"fps\" class=\"tag\">-</span></div>
          <div><span>解像度</span><span id=\"res\" class=\"tag\">-</span></div>
        </div>

        <div class=\"controls\">
          <input id=\"device\" readonly />
          <div class=\"row2\">
            <button id=\"connect\" class=\"ok\">接続</button>
            <button id=\"disconnect\" class=\"danger\">切断</button>
          </div>

          <input id=\"overlay\" placeholder=\"オーバーレイ文字列（日本語可）\" />

          <div class=\"row2\">
            <button id=\"recordStart\" class=\"ok\">録画開始</button>
            <button id=\"recordStop\" class=\"danger\">録画停止</button>
          </div>

          <div class=\"row2\">
            <button id=\"tlStart\" class=\"ok\">TL開始</button>
            <button id=\"tlStop\" class=\"danger\">TL停止</button>
          </div>

          <div class=\"row2\">
            <button id=\"save\">画像保存</button>
            <button id=\"downloadLatest\" class=\"ok\">最新録画DL</button>
          </div>

          <select id=\"fileSelect\"></select>
          <div class=\"row2\">
            <button id=\"refreshFiles\">一覧更新</button>
            <button id=\"downloadSelected\" class=\"ok\">選択DL</button>
          </div>
        </div>

        <div id=\"savedir\" class=\"muted\">保存先: -</div>
        <div id=\"downloadInfo\" class=\"muted\">ダウンロード対象: -</div>
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

    async function refreshStatus() {
      try {
        const s = await j('/api/status');
        document.getElementById('cam').textContent = s.connected ? '接続中' : '未接続';
        document.getElementById('camport').textContent = s.camera_port || '-';
        document.getElementById('device').value = s.camera_port || '-';
        document.getElementById('rec').textContent = s.recording ? 'ON' : 'OFF';
        document.getElementById('tl').textContent = s.timelapse_active ? 'ON' : 'OFF';
        document.getElementById('fps').textContent = s.fps.toFixed(1);
        document.getElementById('res').textContent = s.resolution || '-';
        document.getElementById('savedir').textContent = '保存先: ' + (s.output_dir || '-');
      } catch (_) {}
    }

    async function refreshFiles() {
      try {
        const data = await j('/api/files');
        const sel = document.getElementById('fileSelect');
        sel.innerHTML = '';
        const files = data.files || [];
        if (files.length === 0) {
          const o = document.createElement('option');
          o.value = '';
          o.textContent = 'ダウンロード可能な録画ファイルなし';
          sel.appendChild(o);
          document.getElementById('downloadInfo').textContent = 'ダウンロード対象: -';
          return;
        }
        for (const f of files) {
          const o = document.createElement('option');
          o.value = f.name;
          o.textContent = `${f.name} (${Math.round(f.size / 1024)} KB)`;
          sel.appendChild(o);
        }
        document.getElementById('downloadInfo').textContent = 'ダウンロード対象: ' + files[0].name;
      } catch (e) {
        document.getElementById('downloadInfo').textContent = 'ダウンロード対象: 取得失敗';
      }
    }

    document.getElementById('connect').onclick = async () => {
      await j('/api/connect', { method: 'POST' });
      await refreshStatus();
    };

    document.getElementById('disconnect').onclick = async () => {
      await j('/api/disconnect', { method: 'POST' });
      await refreshStatus();
    };

    document.getElementById('save').onclick = async () => {
      await j('/api/save-image', { method: 'POST' });
      await refreshStatus();
      await refreshFiles();
    };

    document.getElementById('recordStart').onclick = async () => {
      await j('/api/start-recording', { method: 'POST' });
      await refreshStatus();
    };

    document.getElementById('recordStop').onclick = async () => {
      await j('/api/stop-recording', { method: 'POST' });
      await refreshStatus();
      await refreshFiles();
    };

    document.getElementById('tlStart').onclick = async () => {
      await j('/api/timelapse/start', { method: 'POST' });
      await refreshStatus();
    };

    document.getElementById('tlStop').onclick = async () => {
      await j('/api/timelapse/stop', { method: 'POST' });
      await refreshStatus();
      await refreshFiles();
    };

    document.getElementById('refreshFiles').onclick = async () => {
      await refreshFiles();
    };

    document.getElementById('downloadLatest').onclick = async () => {
      const data = await j('/api/files');
      const files = data.files || [];
      if (files.length === 0) {
        return;
      }
      window.location.href = `/download/${encodeURIComponent(files[0].name)}`;
    };

    document.getElementById('downloadSelected').onclick = async () => {
      const name = document.getElementById('fileSelect').value;
      if (!name) {
        return;
      }
      window.location.href = `/download/${encodeURIComponent(name)}`;
    };

    document.getElementById('fileSelect').onchange = (e) => {
      const v = e.target.value || '-';
      document.getElementById('downloadInfo').textContent = 'ダウンロード対象: ' + v;
    };

    document.getElementById('overlay').onchange = async (e) => {
      await j('/api/overlay-text', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: e.target.value || '' })
      });
    };

    refreshStatus();
    refreshFiles();
    setInterval(refreshStatus, 1000);
  </script>
</body>
</html>
"""


def create_temp_output_dir(base_dir):
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_dir = os.path.join(base_dir, f'temp_{stamp}')
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


class CameraRemoteServer:
    def __init__(self, host, port, camera_port, out_dir=None):
        self.host = host
        self.port = port
        self.camera_port = camera_port
        base_dir = os.path.dirname(__file__)
        self.out_dir = out_dir or create_temp_output_dir(base_dir)
        os.makedirs(self.out_dir, exist_ok=True)

        self.cap = None
        self.overlay_text = ''
        self.connected = False

        self.frame_lock = threading.Lock()
        self.latest_frame = None

        self.recording = False
        self.video_writer = None
        self.writer_lock = threading.Lock()

        self.timelapse_active = False
        self.timelapse_last_capture_ts = 0.0
        self.timelapse_frames = []
        self.timelapse_lock = threading.Lock()

        self.target_fps = TARGET_FPS
        self._fps = 0.0
        self._fps_ema = TARGET_FPS
        self._prev_frame_ts = None

        self._pil_font = self._load_japanese_font()

        self.stop_event = threading.Event()
        self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.capture_thread.start()

    def _load_japanese_font(self):
        if ImageFont is None:
            return None

        # Try system font discovery first for better portability.
        try:
            out = subprocess.check_output(
                ['fc-list', ':lang=ja', 'file'],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            for line in out.splitlines():
                path = line.strip().split(':')[0]
                if path and os.path.exists(path):
                    try:
                        return ImageFont.truetype(path, 28)
                    except Exception:
                        continue
        except Exception:
            pass

        font_candidates = [
            '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',
            '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
            '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
            '/usr/share/fonts/truetype/fonts-japanese-gothic.ttf',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        ]
        for path in font_candidates:
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, 28)
                except Exception:
                    continue
        return None

    def _has_non_ascii(self, text):
        try:
            text.encode('ascii')
            return False
        except UnicodeEncodeError:
            return True

    def _list_devices(self):
        return [{'index': 0, 'label': self.camera_port}]

    def connect_camera(self):
        self.disconnect_camera()
        cap = cv2.VideoCapture(self.camera_port, cv2.CAP_V4L2)
        if not cap.isOpened():
            cap.release()
            raise RuntimeError(f'failed to open camera port={self.camera_port}')

        cap.set(cv2.CAP_PROP_FPS, self.target_fps)
        self.cap = cap
        self.connected = True

    def disconnect_camera(self):
        self.stop_recording()
        self.stop_timelapse(save=False)
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self.connected = False
        with self.frame_lock:
            self.latest_frame = None

    def _now_stamp(self):
        return datetime.now().strftime('%Y%m%d_%H%M%S')

    def _draw_text(self, frame, text, x, y, color=(0, 255, 255)):
        # ASCII text is more reliable with cv2 on embedded environments.
        use_pillow = self._has_non_ascii(text)
        if (not use_pillow) or self._pil_font is None or Image is None or ImageDraw is None:
            cv2.putText(
                frame,
                text,
                (x, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                color,
                2,
                cv2.LINE_AA,
            )
            return frame

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        draw = ImageDraw.Draw(pil_img)
        try:
            draw.text((x, y - 24), text, font=self._pil_font, fill=(color[2], color[1], color[0]))
            out = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            return out
        except Exception:
            cv2.putText(
                frame,
                text,
                (x, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                color,
                2,
                cv2.LINE_AA,
            )
            return frame

    def _overlay(self, frame):
        out = frame.copy()
        stamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # RECを一番下にするため、通常情報を先に並べる
        lines = [stamp, f'FPS: {self._fps:.1f}']
        if self.overlay_text:
            lines.append(self.overlay_text)
        if self.recording:
            lines.append('REC')
        if self.timelapse_active:
          with self.timelapse_lock:
            tl_count = len(self.timelapse_frames)
          lines.append(f'TL ON ({tl_count})')

        y = 36
        for text in lines:
            out = self._draw_text(out, text, 12, y)
            y += 34
        return out

    def _capture_loop(self):
        interval = 1.0 / max(self.target_fps, 1.0)
        while not self.stop_event.is_set():
            loop_start = time.perf_counter()

            if self.cap is None:
                time.sleep(0.05)
                continue

            ok, frame = self.cap.read()
            if not ok or frame is None:
                time.sleep(0.02)
                continue

            now = time.perf_counter()
            if self._prev_frame_ts is not None:
                dt = max(now - self._prev_frame_ts, 1e-6)
                inst_fps = min(120.0, 1.0 / dt)
                self._fps_ema = (self._fps_ema * 0.85) + (inst_fps * 0.15)
                self._fps = min(self._fps_ema, self.target_fps * 1.2)
            self._prev_frame_ts = now

            draw = self._overlay(frame)
            with self.frame_lock:
                self.latest_frame = draw

            with self.writer_lock:
              if self.recording and self.video_writer is not None:
                self.video_writer.write(draw)

            if self.timelapse_active:
                if now - self.timelapse_last_capture_ts >= TIMELAPSE_INTERVAL_SEC:
                    with self.timelapse_lock:
                        self.timelapse_frames.append(draw.copy())
                    self.timelapse_last_capture_ts = now

            elapsed = time.perf_counter() - loop_start
            sleep_s = interval - elapsed
            if sleep_s > 0:
                time.sleep(sleep_s)

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
        writer = cv2.VideoWriter(path, fourcc, max(10.0, self.target_fps), (w, h))
        if not writer.isOpened():
            raise RuntimeError('failed to start recorder')

        with self.writer_lock:
            self.video_writer = writer
            self.recording = True
        return path

    def stop_recording(self):
        writer = None
        with self.writer_lock:
            writer = self.video_writer
            self.video_writer = None
            self.recording = False
        if writer is not None:
            writer.release()

    def start_timelapse(self):
        if self.timelapse_active:
            return None
        with self.timelapse_lock:
            self.timelapse_frames = []
        self.timelapse_last_capture_ts = 0.0
        self.timelapse_active = True
        return {'ok': True}

    def stop_timelapse(self, save=True):
        with self.timelapse_lock:
            has_frames = bool(self.timelapse_frames)
        if not self.timelapse_active and not has_frames:
            return None

        self.timelapse_active = False

        with self.timelapse_lock:
            frames = list(self.timelapse_frames)
            self.timelapse_frames = []

        if not save or not frames:
            return None

        h, w = frames[0].shape[:2]
        path = os.path.join(self.out_dir, f'timelapse_{self._now_stamp()}.mp4')
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(path, fourcc, TIMELAPSE_VIDEO_FPS, (w, h))
        if not writer.isOpened():
            raise RuntimeError('failed to start timelapse writer')

        for frame in frames:
            writer.write(frame)
        writer.release()
        return path

    def status(self):
        resolution = None
        with self.frame_lock:
            if self.latest_frame is not None:
                h, w = self.latest_frame.shape[:2]
                resolution = f'{w}x{h}'

        return {
            'connected': self.connected,
            'recording': self.recording,
            'timelapse_active': self.timelapse_active,
            'fps': float(self._fps),
            'resolution': resolution,
            'camera_port': self.camera_port,
            'output_dir': self.out_dir,
            'timelapse_interval_sec': TIMELAPSE_INTERVAL_SEC,
        }

    def list_downloadable_files(self):
        p = Path(self.out_dir)
        if not p.exists():
            return []

        files = []
        for item in p.iterdir():
            if not item.is_file():
                continue
            if item.suffix.lower() not in {'.mp4', '.png'}:
                continue
            stat = item.stat()
            files.append(
                {
                    'name': item.name,
                    'size': stat.st_size,
                    'mtime': stat.st_mtime,
                }
            )
        files.sort(key=lambda x: x['mtime'], reverse=True)
        return files

    async def index(self, request):
        return web.Response(text=HTML_PAGE, content_type='text/html')

    async def api_status(self, request):
        return web.json_response(self.status())

    async def api_devices(self, request):
        return web.json_response({'devices': self._list_devices(), 'camera_port': self.camera_port})

    async def api_connect(self, request):
        self.connect_camera()
        return web.json_response({'ok': True, 'camera_port': self.camera_port})

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

    async def api_timelapse_start(self, request):
        self.start_timelapse()
        return web.json_response({'ok': True, 'interval_sec': TIMELAPSE_INTERVAL_SEC})

    async def api_timelapse_stop(self, request):
        path = self.stop_timelapse(save=True)
        return web.json_response({'ok': True, 'path': path})

    async def api_files(self, request):
        return web.json_response({'files': self.list_downloadable_files()})

    async def download_file(self, request):
        name = request.match_info.get('name', '')
        safe_name = os.path.basename(name)
        if not safe_name:
            raise web.HTTPBadRequest(text='invalid file name')

        path = os.path.abspath(os.path.join(self.out_dir, safe_name))
        out_dir_abs = os.path.abspath(self.out_dir)
        if not path.startswith(out_dir_abs + os.sep):
            raise web.HTTPForbidden(text='forbidden path')
        if not os.path.isfile(path):
            raise web.HTTPNotFound(text='file not found')

        return web.FileResponse(
            path,
            headers={'Content-Disposition': f'attachment; filename="{safe_name}"'},
        )

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
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        img = self._draw_text(img, 'カメラ未接続', 140, 240, color=(0, 0, 255))
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
        app.router.add_post('/api/timelapse/start', self.api_timelapse_start)
        app.router.add_post('/api/timelapse/stop', self.api_timelapse_stop)
        app.router.add_get('/api/files', self.api_files)
        app.router.add_get('/download/{name}', self.download_file)

        async def on_shutdown(_app):
            self.stop_event.set()
            self.stop_recording()
            self.stop_timelapse(save=False)
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
