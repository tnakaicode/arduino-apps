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

#  cd /home/rpi/arduino-apps && pgrep -af "rpi_camera/camera_remote_web.py" || true && ss -lntp | grep ':5000' || true
#  cd /home/rpi/arduino-apps && nohup python rpi_camera/camera_remote_web.py > rpi_camera/camera_remote_web.nohup.log 2>&1 < /dev/null & echo $! && sleep 1 && pgrep -af "rpi_camera/camera_remote_web.py" && ss -lntp | grep ':5000' || true
#  cd /home/rpi/arduino-apps && pkill -f rpi_camera/camera_remote_web.py || true && nohup python rpi_camera/camera_remote_web.py > rpi_camera/camera_remote_web.nohup.log 2>&1 < /dev/null & echo $! && sleep 1 && pgrep -af "rpi_camera/camera_remote_web.py" && ss -lntp | grep ':5000' || true

# systemctl --user stop camera-remote-web.service
# systemctl --user start camera-remote-web.service
# 
# 
# lsof -i :5000
#
# rpi@rpi5:~ $ ps -fp 5623
# UID          PID    PPID  C STIME TTY          TIME CMD
# rpi         5623     883 36 May12 ?        8-16:24:07 /home/rpi/arduino-apps/venv/bin/python /home/rpi/arduino-apps/rpi_camera/camera_remote_web.py
# rpi@rpi5:~ $ 
# rpi@rpi5:~ $ 
# rpi@rpi5:~ $ ps -fp 883
# UID          PID    PPID  C STIME TTY          TIME CMD
# rpi          883       1  0 May12 ?        00:00:00 /lib/systemd/systemd --user
# rpi@rpi5:~ $ systemctl status 883 2>/dev/null
# 

HOST = '0.0.0.0'
WEB_PORT = 5000
CAMERA_PORT = '/dev/video1'
AUTO_CONNECT = True

TARGET_FPS = 30.0
TIMELAPSE_INTERVAL_SEC = 1.0
TIMELAPSE_VIDEO_FPS = 30.0
CAPTURE_WIDTH = 1024
CAPTURE_HEIGHT = 768
CAPTURE_FORMATS = ['MJPG']
CAPTURE_EXPOSURE = 120  # exposure_time_absolute; choose a visible brightness while keeping 30 FPS
CAPTURE_DYNAMIC_FRAMERATE = True

# MJPG is preferred for 30 FPS capture on this UVC camera. YUYV is raw and usually heavier/slower.
LASER_SAT_MIN = 150
LASER_VAL_MIN = 200
LASER_MAX_AREA = 150
LASER_CONTRAST_MIN = 30
LASER_TARGET_N = 1
LASER_MIN_HITS = 4


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
          <div><span>レーザー</span><span id=\"laser\" class=\"tag\">-</span></div>
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
            <button id=\"laserStart\" class=\"ok\">レーザーON</button>
            <button id=\"laserStop\" class=\"danger\">レーザーOFF</button>
          </div>

          <details id=\"laserDetails\" style=\"margin-top:2px\">
            <summary style=\"cursor:pointer;font-size:0.88rem;color:var(--muted)\">レーザー検出パラメータ ▶</summary>
            <div style=\"display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:6px\">
              <label style=\"font-size:0.82rem;color:var(--muted)\">S min<input id=\"lpSatMin\" type=\"number\" min=\"0\" max=\"255\" style=\"padding:5px;font-size:0.88rem\" /></label>
              <label style=\"font-size:0.82rem;color:var(--muted)\">V min<input id=\"lpValMin\" type=\"number\" min=\"0\" max=\"255\" style=\"padding:5px;font-size:0.88rem\" /></label>
              <label style=\"font-size:0.82rem;color:var(--muted)\">Max area<input id=\"lpMaxArea\" type=\"number\" min=\"1\" style=\"padding:5px;font-size:0.88rem\" /></label>
              <label style=\"font-size:0.82rem;color:var(--muted)\">Contrast<input id=\"lpContrast\" type=\"number\" min=\"0\" style=\"padding:5px;font-size:0.88rem\" /></label>
              <label style=\"font-size:0.82rem;color:var(--muted)\">Targets<input id=\"lpTargetN\" type=\"number\" min=\"1\" max=\"10\" style=\"padding:5px;font-size:0.88rem\" /></label>
              <label style=\"font-size:0.82rem;color:var(--muted)\">Min hits<input id=\"lpMinHits\" type=\"number\" min=\"1\" style=\"padding:5px;font-size:0.88rem\" /></label>
            </div>
            <button id=\"laserParamsApply\" class=\"ok\" style=\"margin-top:6px\">パラメータ適用</button>
          </details>

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
        document.getElementById('laser').textContent = s.laser_enabled ? 'ON' : 'OFF';
        if (s.laser_params && !document.getElementById('laserDetails').open) {
          const p = s.laser_params;
          document.getElementById('lpSatMin').value = p.sat_min;
          document.getElementById('lpValMin').value = p.val_min;
          document.getElementById('lpMaxArea').value = p.max_area;
          document.getElementById('lpContrast').value = p.contrast_min;
          document.getElementById('lpTargetN').value = p.target_n;
          document.getElementById('lpMinHits').value = p.min_hits;
        }
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

    document.getElementById('laserStart').onclick = async () => {
      await j('/api/laser/start', { method: 'POST' });
      await refreshStatus();
    };

    document.getElementById('laserStop').onclick = async () => {
      await j('/api/laser/stop', { method: 'POST' });
      await refreshStatus();
    };

    document.getElementById('laserParamsApply').onclick = async () => {
      await j('/api/laser/params', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sat_min:      parseInt(document.getElementById('lpSatMin').value) || 0,
          val_min:      parseInt(document.getElementById('lpValMin').value) || 0,
          max_area:     parseInt(document.getElementById('lpMaxArea').value) || 1,
          contrast_min: parseInt(document.getElementById('lpContrast').value) || 0,
          target_n:     parseInt(document.getElementById('lpTargetN').value) || 1,
          min_hits:     parseInt(document.getElementById('lpMinHits').value) || 1,
        })
      });
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


# ---------------------------------------------------------------------------
# Laser spot detection helpers (adapted from camera_laser.py)
# ---------------------------------------------------------------------------

def _detect_red_lasers(
    frame,
    sat_min=150,
    val_min=200,
    min_area=4.0,
    max_area_abs=80.0,
    max_targets=3,
    contrast_min=30,
):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    b, g, r = cv2.split(frame)
    value_channel = hsv[:, :, 2]

    lower1 = np.array([0, sat_min, val_min], dtype=np.uint8)
    upper1 = np.array([12, 255, 255], dtype=np.uint8)
    lower2 = np.array([168, sat_min, val_min], dtype=np.uint8)
    upper2 = np.array([179, 255, 255], dtype=np.uint8)
    mask = cv2.bitwise_or(
        cv2.inRange(hsv, lower1, upper1), cv2.inRange(hsv, lower2, upper2)
    )

    r16 = r.astype(np.int16)
    dom_map = r16 - np.maximum(g, b).astype(np.int16)
    white_hot = cv2.bitwise_and(
        cv2.threshold(value_channel, int(val_min), 255, cv2.THRESH_BINARY)[1],
        cv2.inRange(dom_map, 10, 255),
    )
    mask = cv2.bitwise_or(mask, white_hot)

    kernel = np.ones((3, 3), np.uint8)
    clean = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    dom_req = int(sat_min) // 8
    candidates = []

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area_abs:
            continue

        (x, y), radius = cv2.minEnclosingCircle(cnt)
        cx, cy = int(x), int(y)

        y0 = max(0, cy - 3)
        y1 = min(frame.shape[0], cy + 4)
        x0 = max(0, cx - 3)
        x1 = min(frame.shape[1], cx + 4)
        local_peak = int(value_channel[y0:y1, x0:x1].max()) if y1 > y0 and x1 > x0 else 0
        if local_peak < int(val_min):
            continue

        r_surround = 15
        sy0 = max(0, cy - r_surround)
        sy1 = min(value_channel.shape[0], cy + r_surround + 1)
        sx0 = max(0, cx - r_surround)
        sx1 = min(value_channel.shape[1], cx + r_surround + 1)
        surround_patch = value_channel[sy0:sy1, sx0:sx1].astype(np.float32)
        icy = cy - sy0
        icx = cx - sx0
        hs, ws = surround_patch.shape
        yy, xx = np.ogrid[:hs, :ws]
        d2 = (yy - icy) ** 2 + (xx - icx) ** 2
        outer_vals = surround_patch[d2 >= 25]
        if outer_vals.size == 0:
            continue
        mean_surround = float(outer_vals.mean())
        if local_peak - mean_surround < contrast_min:
            continue

        patch_r = r[y0:y1, x0:x1]
        patch_g = g[y0:y1, x0:x1]
        patch_b = b[y0:y1, x0:x1]
        if patch_r.size == 0:
            continue
        dom = float(np.mean(patch_r.astype(np.float32) - np.maximum(patch_g, patch_b)))
        if local_peak < 255 and dom < dom_req:
            continue

        score = local_peak + (dom * 2.0) - (area * 0.2)
        candidates.append((score, cx, cy, float(radius), float(area), local_peak))

    candidates.sort(key=lambda c: c[0], reverse=True)
    return candidates[: max(1, int(max_targets))]


def _update_laser_tracks(
    tracks,
    detections,
    next_track_id,
    max_miss=3,
    max_dist=40.0,
    ema_alpha=0.45,
    min_hits=4,
    max_new_tracks=5,
):
    updated = []
    used_track_idx = set()
    used_det_idx = set()

    confirmed = [t for t in tracks if t['hits'] >= min_hits]
    tentative = [t for t in tracks if t['hits'] < min_hits]
    ordered = confirmed + tentative

    pairs = []
    for ti, tr in enumerate(ordered):
        for di, det in enumerate(detections):
            dist = float(np.hypot(tr['x'] - det['x'], tr['y'] - det['y']))
            pairs.append((dist, ti, di))
    pairs.sort(key=lambda p: p[0])

    for dist, ti, di in pairs:
        if dist > max_dist:
            continue
        if ti in used_track_idx or di in used_det_idx:
            continue
        tr = ordered[ti]
        det = detections[di]
        tr['x'] = (ema_alpha * det['x']) + ((1.0 - ema_alpha) * tr['x'])
        tr['y'] = (ema_alpha * det['y']) + ((1.0 - ema_alpha) * tr['y'])
        tr['radius'] = (ema_alpha * det['radius']) + ((1.0 - ema_alpha) * tr['radius'])
        tr['area'] = det['area']
        tr['peak'] = det['peak']
        tr['score'] = det['score']
        tr['miss'] = 0
        tr['hits'] = tr['hits'] + 1
        tr['fresh'] = True
        updated.append(tr)
        used_track_idx.add(ti)
        used_det_idx.add(di)

    for ti, tr in enumerate(ordered):
        if ti in used_track_idx:
            continue
        tr['miss'] += 1
        tr['fresh'] = False
        if tr['miss'] <= max_miss:
            updated.append(tr)

    tentative_count = sum(1 for t in updated if t['hits'] < min_hits)
    for di, det in enumerate(detections):
        if di in used_det_idx:
            continue
        if tentative_count >= max_new_tracks:
            break
        updated.append({
            'id': next_track_id,
            'x': float(det['x']),
            'y': float(det['y']),
            'radius': float(det['radius']),
            'area': float(det['area']),
            'peak': int(det['peak']),
            'score': float(det['score']),
            'miss': 0,
            'hits': 1,
            'fresh': True,
        })
        next_track_id += 1
        tentative_count += 1

    updated.sort(key=lambda t: (t['hits'] >= min_hits, t['score']), reverse=True)
    return updated, next_track_id


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

        self.laser_enabled = False
        self.laser_sat_min = LASER_SAT_MIN
        self.laser_val_min = LASER_VAL_MIN
        self.laser_max_area = LASER_MAX_AREA
        self.laser_contrast_min = LASER_CONTRAST_MIN
        self.laser_target_n = LASER_TARGET_N
        self.laser_min_hits = LASER_MIN_HITS
        self._laser_tracks = []
        self._laser_next_track_id = 1
        self._laser_lock = threading.Lock()

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

    def _fourcc_to_str(self, code):
        try:
            v = int(code)
        except Exception:
            return '????'
        return ''.join(chr((v >> (8 * i)) & 0xFF) for i in range(4))

    def _ensure_v4l2_dynamic_framerate(self):
        if not CAPTURE_DYNAMIC_FRAMERATE:
            return

        try:
            subprocess.run(
                [
                    'v4l2-ctl',
                    '-d',
                    str(self.camera_port),
                    '--set-ctrl=auto_exposure=1',
                    f'--set-ctrl=exposure_time_absolute={CAPTURE_EXPOSURE}',
                    '--set-ctrl=exposure_dynamic_framerate=1',
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f'[Camera] enabled V4L2 dynamic framerate exposure={CAPTURE_EXPOSURE}')
        except FileNotFoundError:
            print('[Camera] v4l2-ctl not installed; dynamic framerate disabled')
        except Exception as exc:
            print(f'[Camera] V4L2 dynamic framerate setup failed: {exc}')

    def _configure_camera(self, cap):
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)
        if CAPTURE_EXPOSURE > 0:
            cap.set(cv2.CAP_PROP_EXPOSURE, CAPTURE_EXPOSURE)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_HEIGHT)

        for fmt in CAPTURE_FORMATS:
            fourcc = cv2.VideoWriter_fourcc(*fmt)
            cap.set(cv2.CAP_PROP_FOURCC, fourcc)
            cap.set(cv2.CAP_PROP_FPS, self.target_fps)

            actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            actual_fps = cap.get(cv2.CAP_PROP_FPS)
            actual_fmt = self._fourcc_to_str(cap.get(cv2.CAP_PROP_FOURCC))
            actual_auto = cap.get(cv2.CAP_PROP_AUTO_EXPOSURE)
            actual_expo = cap.get(cv2.CAP_PROP_EXPOSURE)

            print(
                f'[Camera] trying format={fmt} target={CAPTURE_WIDTH}x{CAPTURE_HEIGHT}@{self.target_fps}, '
                f'actual={actual_w}x{actual_h}@{actual_fps:.1f} fmt={actual_fmt} '
                f'auto_exposure={actual_auto} exposure={actual_expo}'
            )

            if actual_w == CAPTURE_WIDTH and actual_h == CAPTURE_HEIGHT and actual_fps >= 28.0:
                print(f'[Camera] successful capture mode: {fmt}')
                return

        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = cap.get(cv2.CAP_PROP_FPS)
        actual_fmt = self._fourcc_to_str(cap.get(cv2.CAP_PROP_FOURCC))
        print(
            f'[Camera] fallback capture mode: actual={actual_w}x{actual_h}@{actual_fps:.1f} fmt={actual_fmt}'
        )

    def _probe_camera_fps(self, cap, frames=10):
        timestamps = []
        for _ in range(frames):
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            timestamps.append(time.perf_counter())
        if len(timestamps) < 2:
            return 0.0
        intervals = [timestamps[i] - timestamps[i - 1] for i in range(1, len(timestamps))]
        avg = sum(intervals) / len(intervals)
        return 1.0 / avg if avg > 0 else 0.0

    def _has_non_ascii(self, text):
        try:
            text.encode('ascii')
            return False
        except UnicodeEncodeError:
            return True

    def _list_devices(self):
        devices = []
        for p in sorted(Path('/dev').glob('video*')):
            devices.append({'label': str(p)})
        if not devices:
            devices.append({'label': self.camera_port})
        return devices

    def _camera_open_candidates(self):
        candidates = [(self.camera_port, cv2.CAP_V4L2), (self.camera_port, None)]

        # Fallback: try all available /dev/video* nodes when configured path is unavailable.
        extra_paths = sorted(Path('/dev').glob('video*'))
        for p in extra_paths:
            sp = str(p)
            if sp == self.camera_port:
                continue
            candidates.extend([(sp, cv2.CAP_V4L2), (sp, None)])

        # Final fallback: if source is /dev/videoN, try index N directly.
        if isinstance(self.camera_port, str) and self.camera_port.startswith('/dev/video'):
            suffix = self.camera_port[len('/dev/video'):]
            if suffix.isdigit():
                idx = int(suffix)
                candidates.extend([(idx, cv2.CAP_V4L2), (idx, None)])

        deduped = []
        seen = set()
        for source, backend in candidates:
            key = (str(source), backend)
            if key in seen:
                continue
            seen.add(key)
            deduped.append((source, backend))
        return deduped

    def connect_camera(self):
        self.disconnect_camera()
        cap = None
        errors = []
        for source, backend in self._camera_open_candidates():
            if backend is None:
                trial = cv2.VideoCapture(source)
            else:
                trial = cv2.VideoCapture(source, backend)

            if trial.isOpened():
                cap = trial
                break

            errors.append(f'source={source} backend={backend}')
            trial.release()

        if cap is None:
            details = ', '.join(errors)
            raise RuntimeError(
                f'failed to open camera port={self.camera_port}; tried: {details}'
            )

        self._ensure_v4l2_dynamic_framerate()
        self._configure_camera(cap)
        actual_fps = self._probe_camera_fps(cap, frames=8)
        print(f'[Camera] measured capture fps={actual_fps:.1f}')

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
        if self.laser_enabled:
            lines.append('LASER ON')

        y = 36
        for text in lines:
            out = self._draw_text(out, text, 12, y)
            y += 34

        if self.laser_enabled:
            with self._laser_lock:
                laser_tracks = list(self._laser_tracks)
            confirmed = [t for t in laser_tracks if t['hits'] >= self.laser_min_hits]
            draw_tracks = confirmed[:self.laser_target_n]
            for idx, tr in enumerate(draw_tracks, start=1):
                cx = int(round(tr['x']))
                cy = int(round(tr['y']))
                color = (0, 255, 255) if tr['fresh'] else (130, 130, 130)
                cv2.circle(out, (cx, cy), max(5, int(tr['radius']) + 6), color, 2)
                cv2.drawMarker(
                    out, (cx, cy), color,
                    markerType=cv2.MARKER_CROSS, markerSize=20, thickness=2,
                )
                cv2.putText(
                    out, f'T{idx}({cx},{cy})', (cx + 8, cy - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2, cv2.LINE_AA,
                )

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

            if self.laser_enabled:
                raw = _detect_red_lasers(
                    frame,
                    sat_min=self.laser_sat_min,
                    val_min=self.laser_val_min,
                    max_area_abs=float(self.laser_max_area),
                    max_targets=self.laser_target_n * 3,
                    contrast_min=self.laser_contrast_min,
                )
                dets = [
                    {
                        'score': float(t[0]),
                        'x': int(t[1]),
                        'y': int(t[2]),
                        'radius': float(t[3]),
                        'area': float(t[4]),
                        'peak': int(t[5]),
                    }
                    for t in raw
                ]
                with self._laser_lock:
                    self._laser_tracks, self._laser_next_track_id = _update_laser_tracks(
                        self._laser_tracks, dets, self._laser_next_track_id
                    )

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

    def update_laser_params(self, params: dict):
        if 'sat_min' in params:
            self.laser_sat_min = int(max(0, min(255, params['sat_min'])))
        if 'val_min' in params:
            self.laser_val_min = int(max(0, min(255, params['val_min'])))
        if 'max_area' in params:
            self.laser_max_area = int(max(1, params['max_area']))
        if 'contrast_min' in params:
            self.laser_contrast_min = int(max(0, params['contrast_min']))
        if 'target_n' in params:
            self.laser_target_n = int(max(1, min(10, params['target_n'])))
        if 'min_hits' in params:
            self.laser_min_hits = int(max(1, params['min_hits']))

    def start_laser(self):
        with self._laser_lock:
            self._laser_tracks = []
            self._laser_next_track_id = 1
        self.laser_enabled = True

    def stop_laser(self):
        self.laser_enabled = False
        with self._laser_lock:
            self._laser_tracks = []
            self._laser_next_track_id = 1

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
            'laser_enabled': self.laser_enabled,
            'laser_params': {
                'sat_min': self.laser_sat_min,
                'val_min': self.laser_val_min,
                'max_area': self.laser_max_area,
                'contrast_min': self.laser_contrast_min,
                'target_n': self.laser_target_n,
                'min_hits': self.laser_min_hits,
            },
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
        try:
            self.connect_camera()
            return web.json_response({'ok': True, 'camera_port': self.camera_port})
        except Exception as exc:
            return web.json_response(
                {'ok': False, 'error': str(exc), 'camera_port': self.camera_port},
                status=400,
            )

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

    async def api_laser_start(self, request):
        self.start_laser()
        return web.json_response({'ok': True})

    async def api_laser_stop(self, request):
        self.stop_laser()
        return web.json_response({'ok': True})

    async def api_laser_params(self, request):
        data = await request.json()
        self.update_laser_params(data)
        return web.json_response({'ok': True, 'laser_params': {
            'sat_min': self.laser_sat_min,
            'val_min': self.laser_val_min,
            'max_area': self.laser_max_area,
            'contrast_min': self.laser_contrast_min,
            'target_n': self.laser_target_n,
            'min_hits': self.laser_min_hits,
        }})

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
        app.router.add_post('/api/laser/start', self.api_laser_start)
        app.router.add_post('/api/laser/stop', self.api_laser_stop)
        app.router.add_post('/api/laser/params', self.api_laser_params)
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
