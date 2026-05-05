import numpy as np
import matplotlib.pyplot as plt
import sys
import os
import time
import json
import collections
import cv2
from PIL import Image, ImageDraw, ImageFont
import av
import traceback
import threading
import socket
import asyncio
import serial.tools.list_ports
import serial
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.contrib.media import MediaRelay
from pygrabber.dshow_graph import FilterGraph

from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QObject
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QLabel,
    QWidget,
    QVBoxLayout,
    QPushButton,
    QComboBox,
    QHBoxLayout,
    QGroupBox,
    QFileDialog,
    QMessageBox,
    QSpinBox,
    QGridLayout,
    QCheckBox,
    QLineEdit,
)

from base import plot2d, create_tempnum
from base_qtApp import MainWindow
from arduino_control_group import ArduinoControlGroup


class CameraVideoTrack(VideoStreamTrack):
    # --- WebRTC integration ---
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.stopped = True
        self.blank = np.zeros((480, 640, 3), dtype=np.uint8)
        self.frame = None
        self._lock = threading.Lock()
        # trackを親のactive_webrtc_tracksに登録
        if hasattr(parent, "active_webrtc_tracks"):
            parent.active_webrtc_tracks.add(self)

    def __del__(self):
        # trackを親のactive_webrtc_tracksから削除
        if hasattr(self, "parent") and hasattr(self.parent, "active_webrtc_tracks"):
            self.parent.active_webrtc_tracks.discard(self)

    async def recv(self):
        # print(f"[WebRTC] recv called. stopped={self.stopped}, frame={'set' if self.frame is not None else 'None'}")
        pts, time_base = await self.next_timestamp()
        with self._lock:
            if self.stopped or self.frame is None:
                img = self.blank.copy()
                cv2.putText(
                    img,
                    "Camera Stopped",
                    (100, 240),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.2,
                    (0, 0, 255),
                    3,
                )
            else:
                img = self.frame.copy()
        try:
            frame = av.VideoFrame.from_ndarray(img, format="bgr24")
            frame = frame.reformat(format="yuv420p")
            frame.pts = pts
            frame.time_base = time_base
            # print(f"[WebRTC] Frame sent. shape={img.shape}")
            return frame
        except Exception as e:
            blank_frame = av.VideoFrame.from_ndarray(self.blank, format="bgr24")
            blank_frame = blank_frame.reformat(format="yuv420p")
            blank_frame.pts = pts
            blank_frame.time_base = time_base
            # print(f"[WebRTC] Exception in recv: {e}")
            return blank_frame

    def update_frame(self, frame):
        with self._lock:
            self.frame = frame.copy()
            self.stopped = False

    def stop_camera(self):
        with self._lock:
            self.stopped = True
            self.frame = None


class CameraWidget(QWidget, plot2d):
    auto_record_triggered = pyqtSignal()

    def __init__(self):
        print(f"[CameraWidget.__init__] thread: {threading.current_thread().name}")
        plot2d.__init__(self)
        QWidget.__init__(self)

        # --- 必須属性 ---
        self.cap = None
        self.is_recording = False
        self.video_writer = None
        self.record_seconds = 0
        self._fps_frame_count = 0
        self.fps_history = []
        self.fps_history_len = 120
        self.fps_options = [30, 60, 90, 120]
        self.selected_fps = self.fps_options[2]
        self.pre_record_seconds = 30
        self.pre_record_buffer = collections.deque(
            maxlen=self.selected_fps * self.pre_record_seconds
        )
        self.auto_record_seconds = 30
        self.active_webrtc_tracks = set()

        # --- タイムラプス関連の属性を追加 ---
        self.timelapse_active = False
        self.timelapse_interval_seconds = 1  # デフォルト1秒間隔
        self.timelapse_duration_minutes = 60  # デフォルト60分間
        self.timelapse_buffer = []
        self.timelapse_start_time = None
        self.timelapse_total_frames = 0  # 総フレーム数（分割保存後も継続）
        self.timelapse_part_number = 1  # 分割保存のパート番号
        self._timelapse_timer = QTimer()
        self._timelapse_timer.setSingleShot(False)
        self._timelapse_timer.timeout.connect(self._capture_timelapse_frame)
        self._timelapse_stop_timer = QTimer()
        self._timelapse_stop_timer.setSingleShot(True)
        self._timelapse_stop_timer.timeout.connect(self._stop_timelapse_recording)

        # --- Arduino AI値・DI/O値キャッシュを早期初期化 ---
        self._arduino1_ai_cache = ["?"] * 6
        self._arduino2_ai_cache = ["?"] * 6
        self._arduino1_dio_cache = ["?"] * 14
        self._arduino2_dio_cache = ["?"] * 14

        # --- オーバーレイサイズの初期化 ---
        self._overlay_width = 200
        self._overlay_max_h = 20

        # WebRTC
        self.shared_webrtc_track = CameraVideoTrack(self)
        self._ai_overlay_img = None
        self._ai_overlay_text = None
        self._ai_overlay_which = 0
        self._camera_thread_stop = threading.Event()
        self._frame_lock = threading.Lock()  # フレーム共有用ロック
        self._serial_lock = threading.Lock()  # シリアル共有用ロック
        self._serial_status = None
        self._serial_arr = None
        self._serial_event = threading.Event()

        # --- QTimerでメインスレッドからUI更新 ---
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)

        # --- シグナル: 自動録画トリガ ---
        self.auto_record_triggered.connect(self._handle_auto_record_trigger)

        # --- 自動録画用QTimerを1回だけ生成 ---
        self._auto_record_timer = QTimer()
        self._auto_record_timer.setSingleShot(True)
        self._auto_record_timer.timeout.connect(self._stop_auto_recording)

        # --- カメラ接続・映像処理・WebRTC配信・Serial監視を分離 ---
        self._camera_thread = threading.Thread(
            target=self._camera_capture_thread, daemon=True
        )
        self._camera_thread.start()

        self.last_frame = None  # 最新フレームを格納
        
        self._frame_process_thread = threading.Thread(
            target=self._frame_process_loop, daemon=True
        )
        self._frame_process_thread.start()

        self.setWindowTitle("UVC Camera (PyQt)")
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setSizePolicy(QLabel().sizePolicy())
        self.image_label.setMinimumSize(320, 240)
        self.image_label.setMaximumSize(1280, 800)
        self.save_button = QPushButton("Save Image")
        self.save_button.clicked.connect(self.save_image)
        self.record_button = QPushButton("Start Recording")
        self.stop_button = QPushButton("Stop Recording")
        self.record_button.clicked.connect(self.start_recording)
        self.stop_button.clicked.connect(self.stop_recording)
        self.record_time_label = QLabel("録画時間: 00:00")
        self.fps_label = QLabel("FPS: 0.0")
        self.resolution_label = QLabel("解像度: N/A")
        self._fps_timer = QTimer()
        self._fps_timer.timeout.connect(self.update_fps)
        self.record_timer = QTimer()
        self.record_timer.timeout.connect(self.update_record_time)

        # --- 左右反転チェックボックス ---
        self.flip_checkbox = QCheckBox("左右反転")
        self.flip_checkbox.setChecked(False)
        # --- UI widgets (must be created before layout) ---
        self.device_combo = QComboBox()
        self.device_list = self.get_camera_devices()
        self.device_combo.addItems(self.device_list)
        self.device_combo.currentIndexChanged.connect(self.update_resolution_label)
        self.current_device_index = 0
        # カメラポート再スキャンボタン
        self.rescan_button = QPushButton("Rescan Ports")
        self.rescan_button.clicked.connect(self.rescan_camera_ports)
        # --- FPS履歴とグラフ ---
        self.fps_combo = QComboBox()
        self.fps_combo.addItems([str(fps) + " FPS" for fps in self.fps_options])
        self.fps_combo.setCurrentIndex(0)
        self.fps_combo.setToolTip("Disconnect before changing FPS")
        self.fps_combo.currentIndexChanged.connect(self.on_fps_changed)

        # プリトリガ秒数スピンボックス
        self.pre_record_spin = QSpinBox()
        self.pre_record_spin.setRange(1, 60)
        self.pre_record_spin.setValue(self.pre_record_seconds)
        self.pre_record_spin.setSuffix(" 秒プリトリガ")
        self.pre_record_spin.valueChanged.connect(self.on_pre_record_seconds_changed)

        # 異常時自動録画時間スピンボックス
        self.auto_record_spin = QSpinBox()
        self.auto_record_spin.setRange(1, 60)
        self.auto_record_spin.setValue(self.auto_record_seconds)
        self.auto_record_spin.setSuffix(" 秒自動録画")
        self.auto_record_spin.setToolTip("異常時の自動録画時間")
        self.auto_record_spin.valueChanged.connect(self.on_auto_record_seconds_changed)

        # 手動自動録画トリガーボタン
        self.manual_auto_record_button = QPushButton("自動録画トリガー")
        self.manual_auto_record_button.setToolTip("手動で自動録画を開始")
        self.manual_auto_record_button.clicked.connect(
            self.trigger_auto_record_manually
        )

        # --- タイムラプス関連のUI要素を追加 ---
        self.timelapse_interval_spin = QSpinBox()
        self.timelapse_interval_spin.setRange(1, 300)  # 1秒〜5分
        self.timelapse_interval_spin.setValue(self.timelapse_interval_seconds)
        self.timelapse_interval_spin.setSuffix(" 秒間隔")
        self.timelapse_interval_spin.setToolTip("タイムラプス撮影間隔")
        self.timelapse_interval_spin.valueChanged.connect(
            self.on_timelapse_interval_changed
        )

        self.timelapse_duration_spin = QSpinBox()
        self.timelapse_duration_spin.setRange(0, 1440)  # 0分（無制限）〜24時間
        self.timelapse_duration_spin.setValue(self.timelapse_duration_minutes)
        self.timelapse_duration_spin.setSuffix(" 分継続")
        self.timelapse_duration_spin.setToolTip("タイムラプス撮影継続時間 (0=無制限)")
        self.timelapse_duration_spin.valueChanged.connect(
            self.on_timelapse_duration_changed
        )

        self.timelapse_start_button = QPushButton("タイムラプス開始")
        self.timelapse_start_button.setToolTip(
            "指定した間隔でフレームを記録し、最後に動画として保存"
        )
        self.timelapse_start_button.clicked.connect(self.start_timelapse)

        self.timelapse_stop_button = QPushButton("タイムラプス停止")
        self.timelapse_stop_button.setEnabled(False)
        self.timelapse_stop_button.clicked.connect(self.stop_timelapse)

        self.timelapse_status_label = QLabel("タイムラプス: 停止中")

        self.connect_button = QPushButton("Connect")
        self.disconnect_button = QPushButton("Disconnect")
        self.connect_button.clicked.connect(self.connect_camera)
        self.disconnect_button.clicked.connect(self.disconnect_camera)
        self.device_combo.currentIndexChanged.connect(self.change_camera)

        # --- 2つのArduino Control+Pinsを作成（レイアウト直前に作成し、COMリストを確実に初期化） ---
        self.arduino1 = ArduinoControlGroup(self, "Arduino Control 1")
        self.arduino2 = ArduinoControlGroup(self, "Arduino Control 2")

        # --- Arduino コールバック設定 ---
        self.arduino1.set_ai_update_callback(
            lambda idx, val: self._update_ai_cache(1, idx, val)
        )
        self.arduino2.set_ai_update_callback(
            lambda idx, val: self._update_ai_cache(2, idx, val)
        )
        if hasattr(self.arduino1, "set_dio_update_callback"):
            self.arduino1.set_dio_update_callback(
                lambda idx, val: self._update_dio_cache(1, idx, val)
            )
        if hasattr(self.arduino2, "set_dio_update_callback"):
            self.arduino2.set_dio_update_callback(
                lambda idx, val: self._update_dio_cache(2, idx, val)
            )

        # --- QLineEdit for overlay text ---
        self.overlay_text_edit = QLineEdit()
        self.overlay_text_edit.setPlaceholderText(
            "ここにテキストを入力 (映像上部に表示)"
        )
        self.overlay_text_edit.textChanged.connect(
            lambda _: setattr(self, "_overlay_text_cache", None)
        )

        # --- オーバーレイ最大幅を初期化時に計算して固定 ---
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.7
        thickness = 1
        margin = 10
        ai1_texts = [f"A{i}: 0.00 V" for i in range(6)]
        ai2_texts = [f"A{i}: 0.00 V" for i in range(6)]
        max_w1, max_w2, max_h = 0, 0, 0
        for ai1, ai2 in zip(ai1_texts, ai2_texts):
            ((w1, h1), _) = cv2.getTextSize(ai1, font, font_scale, thickness)
            ((w2, h2), _) = cv2.getTextSize(ai2, font, font_scale, thickness)
            max_w1 = max(max_w1, w1)
            max_w2 = max(max_w2, w2)
            max_h = max(max_h, h1, h2)
        self._overlay_width = max_w1 + max_w2 + margin * 4
        self._overlay_max_h = max_h

        # Layout: [LeftGroup][Arduino Control + Arduino Pins][Video]
        main_layout = QHBoxLayout()
        self.arduino1.refresh_ports()
        self.arduino2.refresh_ports()

        # Left group (settings)
        left_main_layout = QVBoxLayout()
        left_top_group = QGroupBox()
        left_top_layout = QVBoxLayout()
        left_top_layout.addWidget(QLabel("Camera Control"))
        left_top_layout.addWidget(self.rescan_button)
        left_top_layout.addWidget(self.device_combo)
        left_top_layout.addWidget(self.fps_combo)
        left_top_layout.addWidget(self.connect_button)
        left_top_layout.addWidget(self.disconnect_button)
        left_top_layout.addWidget(self.fps_label)
        left_top_layout.addWidget(self.resolution_label)
        left_top_layout.addWidget(self.flip_checkbox)
        left_top_group.setLayout(left_top_layout)
        left_bottom_group = QGroupBox("Actions")
        left_bottom_layout = QVBoxLayout()
        left_bottom_layout.addWidget(self.save_button)
        left_bottom_layout.addWidget(self.pre_record_spin)
        left_bottom_layout.addWidget(self.auto_record_spin)
        left_bottom_layout.addWidget(self.manual_auto_record_button)
        left_bottom_layout.addWidget(self.record_button)
        left_bottom_layout.addWidget(self.stop_button)
        left_bottom_layout.addWidget(self.record_time_label)

        # タイムラプス関連のUIを追加
        timelapse_group = QGroupBox("タイムラプス")
        timelapse_layout = QVBoxLayout()
        timelapse_layout.addWidget(self.timelapse_interval_spin)
        timelapse_layout.addWidget(self.timelapse_duration_spin)
        timelapse_layout.addWidget(self.timelapse_start_button)
        timelapse_layout.addWidget(self.timelapse_stop_button)
        timelapse_layout.addWidget(self.timelapse_status_label)
        timelapse_group.setLayout(timelapse_layout)

        left_bottom_layout.addWidget(timelapse_group)
        left_bottom_layout.addStretch(1)
        left_bottom_group.setLayout(left_bottom_layout)
        left_main_layout.addWidget(left_top_group)
        left_main_layout.addWidget(left_bottom_group)
        left_main_layout.addStretch(1)
        left_group = QGroupBox("LeftGroup")
        left_group.setLayout(left_main_layout)
        left_group.setFixedWidth(180)
        main_layout.addWidget(left_group)

        # Arduino Control + Arduino Pins (横並び, 2つ)
        arduino_side_layout = QHBoxLayout()
        self.arduino1.setFixedWidth(180)
        self.arduino2.setFixedWidth(180)
        arduino_side_layout.addWidget(self.arduino1)
        arduino_side_layout.addWidget(self.arduino2)
        arduino_side_layout.addStretch(1)
        arduino_side_group = QGroupBox()
        arduino_side_group.setLayout(arduino_side_layout)
        arduino_side_group.setFixedWidth(370)
        main_layout.addWidget(arduino_side_group)

        # Center group (video)
        center_group = QGroupBox("RightGroup")
        center_layout = QVBoxLayout()
        center_layout.addWidget(self.overlay_text_edit)
        center_layout.addWidget(self.image_label)
        center_group.setLayout(center_layout)
        main_layout.addWidget(center_group)

        self.setLayout(main_layout)
        self.setMinimumWidth(1250)  # Serial通信パラメータUI追加に対応
        self.setMinimumHeight(400)
        self.disconnect_button.setEnabled(False)

        # --- WebRTCサーバーを一度だけ起動 ---
        self.webrtc_server_thread = threading.Thread(
            target=self._start_webrtc_server, daemon=True
        )
        self.webrtc_server_thread.start()

    def _start_webrtc_server(self):
        # remote_status_server.pyのWebサーバ機能を移植
        relay = MediaRelay()
        pcs = set()
        parent = self

        # WebRTCサーバーを起動し、/offerでaiortc映像転送を実装
        async def index(request):
            return web.Response(text=self._get_webrtc_html(), content_type="text/html")

        async def index(request):
            # --- 解説 ---
            # main-flexの中で、video部分とinfo_panel部分を同じflex row内に並べることで、
            # シリアル状態表示（info_panel）が映像の右隣に表示されるように修正します。
            content = """<!DOCTYPE html>
<html>
<head>
  <meta charset=\"utf-8\">
  <title>WebRTC Camera Client</title>
  <style>
    #main-flex {
      display: flex;
      flex-direction: row;
      align-items: flex-start;
      gap: 32px;
      margin-top: 10px;
    }
    .video-container {
      /* no width/flex, just let content size naturally */
    }
    #video {
      width: 100%;
      max-width: 100%;
      height: auto;
      display: block;
      background: #222;
    }
    #info_panel {
      min-width: 220px;
      max-width: 340px;
      display: flex;
      flex-direction: column;
      gap: 18px;
    }
    #status_big {
      color: #d00;
      font-size: 2.2em;
      font-weight: bold;
      margin-bottom: 8px;
    }
    #camera_conn_status {
      color: #0066cc;
      font-size: 1.3em;
      font-weight: bold;
      margin-bottom: 8px;
    }
    #controls { margin: 10px 0; }
    button { margin-right: 8px; }
    #status { color: #333; font-size: 1.1em; margin-top: 10px; }
  </style>
</head>
<body>
  <h2>WebRTC Camera Stream</h2>
  <div id=\"status\">接続中...</div>
  <div id=\"main-flex\">
    <div class=\"video-container\">
      <video id=\"video\" autoplay playsinline muted></video>
      <div id=\"controls\">
        <button id=\"photoBtn\">写真保存</button>
        <button id=\"recBtn\">動画保存開始</button>
        <button id=\"stopRecBtn\" disabled>動画保存停止</button>
        <span id=\"recording-status\" style=\"margin-left: 10px; color: #ff0000; font-weight: bold;\"></span>
      </div>
    </div>
    <div id=\"info_panel\" style=\"margin-left: 24px;\">
      <div id=\"camera_conn_status\"></div>
      <div id=\"status_big\"></div>
      <div id=\"lamp_row\"></div>
      <div id=\"arr_info\"></div>
      <span id=\"camera_status\" style=\"display:none\"></span>
    </div>
  </div>
  <script src=\"webrtc_client.js\"></script>
</body>
</html>
"""
            return web.Response(content_type="text/html", text=content)

        async def offer(request):
            print("[offer] HTTP POST /offer 到達")
            params = await request.json()
            pc = RTCPeerConnection()
            pcs.add(pc)
            pc.addTransceiver("video", direction="sendonly")
            pc.addTrack(relay.subscribe(parent.shared_webrtc_track))

            async def cleanup_pc():
                if pc in pcs:
                    pcs.remove(pc)
                await pc.close()

            def on_connection_state_change():
                print(f"[WebRTC] connectionState: {pc.connectionState}")
                if pc.connectionState in ("closed", "failed", "disconnected"):
                    asyncio.ensure_future(cleanup_pc())

            pc.onconnectionstatechange = on_connection_state_change

            def on_ice_connection_state_change():
                print(f"[WebRTC] iceConnectionState: {pc.iceConnectionState}")

            pc.oniceconnectionstatechange = on_ice_connection_state_change

            offer_obj = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
            await pc.setRemoteDescription(offer_obj)
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            print("[offer] 応答返却")
            return web.json_response(
                {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
            )

        async def status_api(request):
            # serial_monitorが存在しない場合のデフォルト値を設定
            arr_info = []
            serial_status = "未接続"

            # serial_monitorが存在する場合のみ値を取得
            if hasattr(parent, "serial_monitor") and parent.serial_monitor:
                try:
                    arr_info = parent.serial_monitor.get_status_info()
                    serial_status = parent.serial_monitor.get_status()
                    # 「状態取得中」は送らず、データ未取得時は「未接続」扱いにする
                    if serial_status not in ("正常", "異常"):
                        serial_status = "未接続"
                except Exception as e:
                    print(f"[WebRTC] serial_monitor error: {e}")
                    arr_info = []
                    serial_status = "未接続"

            # カメラ接続状態をcap.isOpened()で判定
            cam_status = "異常"
            if hasattr(parent, "cap") and parent.cap is not None:
                try:
                    if parent.cap.isOpened():
                        cam_status = "正常"
                except Exception:
                    pass
            # remote_status_server.py互換
            return web.json_response(
                {"status": serial_status, "camera": cam_status, "arr": arr_info}
            )

        # /webrtc_client.jsエンドポイント: 最新のclient.jsを返す
        async def client_js(request):
            js_path = os.path.join(
                os.path.dirname(__file__), "static", "webrtc_client.js"
            )
            if not os.path.exists(js_path):
                return web.Response(status=404, text="webrtc_client.js not found")
            with open(js_path, "r", encoding="utf-8") as f:
                js_code = f.read()
            return web.Response(content_type="application/javascript", text=js_code)

        # キャッシュ制御ミドルウェア
        @web.middleware
        async def js_cache_control_middleware(request, handler):
            response = await handler(request)
            if request.path == "/webrtc_client.js":
                response.headers["Cache-Control"] = "no-store"
            return response

        async def on_shutdown(app):
            coros = [pc.close() for pc in pcs]
            await asyncio.gather(*coros)
            pcs.clear()

        app = web.Application(middlewares=[js_cache_control_middleware])
        app.on_shutdown.append(on_shutdown)
        app.router.add_get("/", index)
        app.router.add_post("/offer", offer)
        app.router.add_get("/status", status_api)
        app.router.add_get("/webrtc_client.js", client_js)
        # staticファイルルート追加（必要なら）
        static_dir = os.path.join(os.path.dirname(__file__), "static")
        if os.path.isdir(static_dir):
            app.router.add_static("/static/", static_dir)

        # 既に使われているポートを避けるため、5000〜5010で空きを探す
        port = 5000
        for p in range(5000, 5011):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("0.0.0.0", p))
                    port = p
                    break
                except OSError:
                    continue

        async def run_async():
            try:
                runner = web.AppRunner(app)
                await runner.setup()
                site = web.TCPSite(runner, host="0.0.0.0", port=port)
                print(f"[WebRTC] サーバー起動中: port={port}")
                await site.start()
                print(f"[WebRTC] サーバー起動完了: http://localhost:{port}")
                print(f"[WebRTC] アクセス可能URL: http://0.0.0.0:{port}")
                while True:
                    await asyncio.sleep(3600)
            except Exception as e:
                print(f"[WebRTC] サーバー起動失敗: {e}")
                import traceback

                traceback.print_exc()

        def start_loop():
            try:
                # 新しいイベントループを作成して実行
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(run_async())
            except Exception as e:
                print(f"[WebRTC] asyncio.run失敗: {e}")
                import traceback

                traceback.print_exc()
            finally:
                try:
                    loop.close()
                except:
                    pass

        start_loop()

    def _update_dio_cache(self, which, idx, val):
        changed = False
        if which == 1:
            if self._arduino1_dio_cache[idx] != val:
                self._arduino1_dio_cache[idx] = val
                changed = True
        elif which == 2:
            if self._arduino2_dio_cache[idx] != val:
                self._arduino2_dio_cache[idx] = val
                changed = True
        if changed:
            self._ai_overlay_img = None

    def _update_ai_cache(self, which, idx, val):
        changed = False
        if which == 1:
            if self._arduino1_ai_cache[idx] != val:
                self._arduino1_ai_cache[idx] = val
                changed = True
        elif which == 2:
            if self._arduino2_ai_cache[idx] != val:
                self._arduino2_ai_cache[idx] = val
                changed = True
        if changed:
            self._ai_overlay_img = None

    def reset_arduino_ai_cache(self, which):
        if which == 1:
            self._arduino1_ai_cache = ["?"] * 6
            self._arduino1_dio_cache = ["?"] * 14
        elif which == 2:
            self._arduino2_ai_cache = ["?"] * 6
            self._arduino2_dio_cache = ["?"] * 14
        self._ai_overlay_img = None

    def add_overlays_to_frame(self, frame):
        """
        カメラ映像に対して、Arduino値・DI/O値・時刻・録画時間などのオーバーレイを追加し、必要に応じてFrameサイズを拡張して返す。
        """
        try:
            return self._add_overlays_to_frame_internal(frame)
        except Exception as e:
            print(f"[add_overlays_to_frame] エラーをキャッチ: {e}")
            import traceback
            traceback.print_exc()
            # エラー時は元のフレームを返す
            return frame.copy()
    
    def _add_overlays_to_frame_internal(self, frame):
        """
        オーバーレイ処理の実装（エラー処理は呼び出し元で行う）
        """
        orig_h, orig_w = frame.shape[:2]

        # オーバーレイ幅・高さが初期化されていない場合のデフォルト値
        if not hasattr(self, "_overlay_width") or self._overlay_width is None:
            self._overlay_width = 200  # デフォルト値
        if not hasattr(self, "_overlay_max_h") or self._overlay_max_h is None:
            self._overlay_max_h = 20  # デフォルト値

        overlay_width = self._overlay_width
        max_h = self._overlay_max_h

        # 数値が有効かチェック
        if not isinstance(overlay_width, (int, float)) or overlay_width <= 0:
            overlay_width = 200
        if not isinstance(max_h, (int, float)) or max_h <= 0:
            max_h = 20

        # Arduino キャッシュが初期化されていない場合のデフォルト値
        if not hasattr(self, "_arduino1_ai_cache") or self._arduino1_ai_cache is None:
            self._arduino1_ai_cache = ["?"] * 6
        if not hasattr(self, "_arduino2_ai_cache") or self._arduino2_ai_cache is None:
            self._arduino2_ai_cache = ["?"] * 6
        if not hasattr(self, "_arduino1_dio_cache") or self._arduino1_dio_cache is None:
            self._arduino1_dio_cache = ["?"] * 14
        if not hasattr(self, "_arduino2_dio_cache") or self._arduino2_dio_cache is None:
            self._arduino2_dio_cache = ["?"] * 14

        # --- キャッシュからAI値・DI/O値テキスト取得 ---
        ai1_texts = [f"A{i}: {v}" for i, v in enumerate(self._arduino1_ai_cache)]
        ai2_texts = [f"A{i}: {v}" for i, v in enumerate(self._arduino2_ai_cache)]
        dio1_texts = [
            f"D{str(i).zfill(2)}: {v}" for i, v in enumerate(self._arduino1_dio_cache)
        ]
        dio2_texts = [
            f"D{str(i).zfill(2)}: {v}" for i, v in enumerate(self._arduino2_dio_cache)
        ]
        ai_overlay_text = tuple(ai1_texts + ai2_texts + dio1_texts + dio2_texts)
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.7
        thickness = 1
        color1 = (0, 255, 255)
        color2 = (0, 180, 255)
        margin = 10
        new_w = int(orig_w + overlay_width)
        # --- オーバーレイ画像キャッシュを利用 ---
        need_redraw = (
            self._ai_overlay_img is None
            or self._ai_overlay_text != ai_overlay_text
            or (
                self._ai_overlay_img is not None
                and (
                    self._ai_overlay_img.shape[0]
                    != (max_h + 8) * (len(ai1_texts) + len(dio1_texts)) + 30
                    or self._ai_overlay_img.shape[1] != overlay_width
                )
            )
        )
        if need_redraw:
            n_lines = len(ai1_texts) + len(dio1_texts)
            overlay_h = int((max_h + 8) * n_lines + 30)
            overlay_width = int(overlay_width)
            # サイズが有効な範囲内かチェック
            if overlay_h <= 0:
                overlay_h = 100
            if overlay_width <= 0:
                overlay_width = 200
            overlay_img = np.zeros((overlay_h, overlay_width, 3), dtype=np.uint8)
            # AI値
            for idx, (ai1, ai2) in enumerate(zip(ai1_texts, ai2_texts)):
                y = int(30 + idx * (max_h + 8))
                x1 = int(margin)
                x2 = int(margin + (overlay_width // 2))
                cv2.putText(
                    overlay_img,
                    ai1,
                    (x1, y),
                    font,
                    font_scale,
                    color1,
                    thickness,
                    cv2.LINE_AA,
                )
                cv2.putText(
                    overlay_img,
                    ai2,
                    (x2, y),
                    font,
                    font_scale,
                    color2,
                    thickness,
                    cv2.LINE_AA,
                )
            # DI/O値
            for idx, (dio1, dio2) in enumerate(zip(dio1_texts, dio2_texts)):
                y = int(30 + (len(ai1_texts) + idx) * (max_h + 8))
                x1 = int(margin)
                x2 = int(margin + (overlay_width // 2))
                cv2.putText(
                    overlay_img,
                    dio1,
                    (x1, y),
                    font,
                    font_scale,
                    (0, 255, 180),
                    thickness,
                    cv2.LINE_AA,
                )
                cv2.putText(
                    overlay_img,
                    dio2,
                    (x2, y),
                    font,
                    font_scale,
                    (0, 180, 180),
                    thickness,
                    cv2.LINE_AA,
                )
            self._ai_overlay_img = overlay_img
            self._ai_overlay_text = ai_overlay_text
        # --- フレームとオーバーレイを合成 ---
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        if hasattr(self, "fps_history") and len(self.fps_history) > 0:
            fps_disp = f"FPS: {self.fps_history[-1]:.1f}"
        else:
            fps_disp = "FPS: 0.0"
        if self.is_recording:
            m, s = divmod(self.record_seconds, 60)
            rec_time_str = f"REC {m:02d}:{s:02d}"
        else:
            rec_time_str = "REC"

        # タイムラプス情報を追加
        if hasattr(self, "timelapse_active") and self.timelapse_active:
            elapsed_seconds = time.time() - self.timelapse_start_time
            elapsed_minutes = int(elapsed_seconds // 60)
            elapsed_secs = int(elapsed_seconds % 60)
            tl_str = f"TL #{self.timelapse_total_frames + 1} | {elapsed_minutes:02d}:{elapsed_secs:02d}"
            text_items = [now_str, fps_disp, rec_time_str, tl_str]
        else:
            text_items = [now_str, fps_disp, rec_time_str]

        overlay_text = "   ".join(text_items)
        text_size, _ = cv2.getTextSize(overlay_text, font, font_scale, thickness)
        text_h = int(text_size[1] + 20)

        # _ai_overlay_imgがNoneでないことを確認
        if self._ai_overlay_img is not None:
            overlay_h = int(self._ai_overlay_img.shape[0])
        else:
            overlay_h = 100  # デフォルト値

        base_h = int(max(orig_h, overlay_h))
        need_extra = base_h < orig_h + text_h
        total_h = int(base_h if not need_extra else orig_h + text_h)
        new_img = np.zeros((total_h, new_w, 3), dtype=np.uint8)
        new_img[:orig_h, :orig_w] = frame

        # _ai_overlay_imgがNoneでない場合のみ配置
        if self._ai_overlay_img is not None:
            new_img[:overlay_h, orig_w:] = self._ai_overlay_img

        text_x = int(margin)
        if need_extra:
            text_y = int(orig_h + text_h - 10)
        else:
            text_y = int(base_h - 10)
        cv2.putText(
            new_img,
            overlay_text,
            (text_x, text_y),
            font,
            font_scale,
            (255, 255, 255),
            thickness,
            cv2.LINE_AA,
        )
        # --- QLineEditのTextは映像にかぶせず、上部に新しい帯を作って表示 ---
        overlay_user_text = (
            self.overlay_text_edit.text().strip()
            if hasattr(self, "overlay_text_edit")
            else ""
        )
        pad_x, pad_y = 16, 10
        # --- テキスト帯のキャッシュを利用して再描画を抑制 ---
        if not hasattr(self, "_user_text_band_cache"):
            self._user_text_band_cache = None
            self._user_text_band_text = None
            self._user_text_band_h = None
            self._user_text_band_w = None
        band_w = new_img.shape[1]
        # テキストまたは画像幅が変わったら再描画
        need_redraw_band = (
            self._user_text_band_cache is None
            or self._user_text_band_text != overlay_user_text
            or self._user_text_band_w != band_w
        )
        if need_redraw_band:
            # フォント選択
            font_candidates = [
                ("C:/Windows/Fonts/meiryo.ttc", 28),
                ("C:/Windows/Fonts/msgothic.ttc", 28),
                ("C:/Windows/Fonts/msmincho.ttc", 28),
                ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28),
                ("DejaVuSans.ttf", 28),
            ]
            pil_font = None
            for font_path, font_size in font_candidates:
                try:
                    pil_font = ImageFont.truetype(font_path, font_size)
                    break
                except Exception:
                    continue
            if pil_font is None:
                pil_font = ImageFont.load_default()
            sample_text = overlay_user_text if overlay_user_text else "あA"
            bbox = pil_font.getbbox(sample_text)
            user_text_w = bbox[2] - bbox[0]
            user_text_h = bbox[3] - bbox[1]
            box_h = user_text_h + pad_y * 2
            band_img = np.zeros((box_h, band_w, 3), dtype=np.uint8)
            band_img[:, :] = (0, 0, 0)
            if overlay_user_text:
                pil_img = Image.fromarray(band_img.copy())
                draw = ImageDraw.Draw(pil_img)
                text_x = pad_x
                text_y = pad_y - 2
                draw.text(
                    (text_x, text_y),
                    overlay_user_text,
                    font=pil_font,
                    fill=(255, 255, 255),
                )
                band_img = np.array(pil_img)
            self._user_text_band_cache = band_img
            self._user_text_band_text = overlay_user_text
            self._user_text_band_h = box_h
            self._user_text_band_w = band_w
        else:
            band_img = self._user_text_band_cache
            box_h = self._user_text_band_h
        # 新しい帯＋既存画像分の高さでnew_imgを拡張
        expanded_img = np.zeros(
            (new_img.shape[0] + box_h, new_img.shape[1], 3), dtype=np.uint8
        )
        expanded_img[:box_h, :] = band_img
        expanded_img[box_h:, :] = new_img
        new_img = expanded_img
        return new_img

    def _camera_capture_thread(self):
        # カメラからフレーム取得のみ担当
        fail_count = 0
        max_fail = 30
        last_warn = False
        while not getattr(self, "_camera_thread_stop", threading.Event()).is_set():
            if self.cap:
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    fail_count += 1
                    if not last_warn:
                        print("[WARN] Camera grab/read failed. Retrying...")
                        last_warn = True
                    if fail_count >= max_fail:
                        print(
                            "[WARN] Too many camera grab failures. Reopening camera..."
                        )
                        try:
                            self.cap.release()
                        except Exception:
                            pass
                        try:
                            self.cap = cv2.VideoCapture(self.current_device_index)
                        except Exception as e:
                            print(f"[ERROR] Camera reopen failed: {e}")
                        fail_count = 0
                        time.sleep(0.5)
                    else:
                        time.sleep(0.05)
                    continue
                else:
                    fail_count = 0
                    last_warn = False
                # フレームを共有バッファに格納
                with self._frame_lock:
                    self._raw_frame = frame.copy()
            else:
                with self._frame_lock:
                    self._raw_frame = None
                time.sleep(0.05)

    def _frame_process_loop(self):
        # 映像処理・WebRTC配信・録画・バッファ保存
        while not getattr(self, "_camera_thread_stop", threading.Event()).is_set():
            with self._frame_lock:
                frame = getattr(self, "_raw_frame", None)
            if frame is not None:
                # 左右反転（Qtオブジェクトの存在確認）
                try:
                    if (
                        hasattr(self, "flip_checkbox")
                        and self.flip_checkbox
                        and self.flip_checkbox.isChecked()
                    ):
                        frame = cv2.flip(frame, 1)
                except (RuntimeError, AttributeError):
                    # Qtオブジェクトが削除済みの場合はスキップ
                    pass

                # オーバーレイ追加（失敗した場合は元のフレームを使用）
                try:
                    new_img = self.add_overlays_to_frame(frame)
                except Exception as overlay_error:
                    import traceback
                    print(f"[frame_process_loop] Overlay error: {overlay_error}")
                    print(traceback.format_exc())
                    new_img = frame.copy()  # フォールバック

                self.last_frame = new_img.copy()
                
                # WebRTC配信
                for track in list(self.active_webrtc_tracks):
                    track.update_frame(new_img)
                # --- プリトリガバッファ保存（録画していない時のみ） ---
                if not self.is_recording:
                    self.pre_record_buffer.append((time.time(), new_img.copy()))
                # --- 録画バッファに保存（録画中のみ） ---
                if self.is_recording:
                    self._recording_buffer.append((time.time(), new_img.copy()))
                    self._frame_count += 1
                self._fps_frame_count += 1
            time.sleep(0.01)

    def trigger_auto_record_manually(self):
        """手動で自動録画をトリガーする"""
        if not getattr(self, "_auto_recording", False):
            print("[AutoRecord] 手動トリガー: 自動録画開始 (emit signal)")
            self.auto_record_triggered.emit()
        else:
            print("[AutoRecord] 手動トリガー: 既に自動録画中のためスキップ")

    def _handle_auto_record_trigger(self):
        if not hasattr(self, "last_frame"):
            print("[DEBUG] auto_record: no last_frame attribute")
            return
        if self.last_frame is None:
            print("[DEBUG] auto_record: last_frame is None (no camera image yet)")
            return
        if self.is_recording:
            print("[DEBUG] auto_record: already recording, skip auto-record trigger")
            return
        self._auto_recording = True
        self._recording_mode = "auto"
        self._recording_buffer = []
        print("[DEBUG] auto_record: start_recording(auto_filename=True) with buffer")
        self.start_recording(auto_filename=True)
        duration_ms = getattr(self, "auto_record_seconds", 5) * 1000
        print(f"[DEBUG] about to call _auto_record_timer.start({duration_ms})")
        self._auto_record_timer.start(duration_ms)
        print(
            f"[DEBUG] _auto_record_timer.isActive()={self._auto_record_timer.isActive()}"
        )

    def on_auto_record_seconds_changed(self, val):
        self.auto_record_seconds = val

    def on_timelapse_interval_changed(self, val):
        """タイムラプス間隔の変更"""
        self.timelapse_interval_seconds = val

    def on_timelapse_duration_changed(self, val):
        """タイムラプス継続時間の変更"""
        self.timelapse_duration_minutes = val

    def start_timelapse(self):
        """タイムラプス録画開始"""
        if not hasattr(self, "last_frame") or self.last_frame is None:
            QMessageBox.warning(self, "警告", "カメラが接続されていません")
            return

        if self.timelapse_active:
            print("[Timelapse] 既にタイムラプス録画中")
            return

        # バッファ初期化: 既存のフレームをクリアして新規撮影開始
        self.timelapse_active = True
        self.timelapse_buffer = []  # 空のリストで初期化
        self.timelapse_start_time = time.time()
        self.timelapse_total_frames = 0  # 総フレーム数リセット
        self.timelapse_part_number = 1  # パート番号リセット
        self.timelapse_file_num = (
            self._get_timelapse_file_number()
        )  # ファイル番号を取得して固定

        # UI更新
        self.timelapse_start_button.setEnabled(False)
        self.timelapse_stop_button.setEnabled(True)
        self.timelapse_status_label.setText("タイムラプス: 録画中")

        # タイマー設定
        interval_ms = self.timelapse_interval_seconds * 1000
        self._timelapse_timer.start(interval_ms)

        # 継続時間後に自動停止（0分の場合は無制限モード）
        if self.timelapse_duration_minutes > 0:
            duration_ms = self.timelapse_duration_minutes * 60 * 1000
            self._timelapse_stop_timer.start(duration_ms)
            print(
                f"[Timelapse] 開始: {self.timelapse_interval_seconds}秒間隔, {self.timelapse_duration_minutes}分継続"
            )
        else:
            # 無制限モード: 自動停止タイマーを起動しない
            print(
                f"[Timelapse] 開始: {self.timelapse_interval_seconds}秒間隔, 無制限モード"
            )

    def stop_timelapse(self):
        """タイムラプス録画停止"""
        if not self.timelapse_active:
            return

        self.timelapse_active = False

        # タイマー停止
        self._timelapse_timer.stop()
        self._timelapse_stop_timer.stop()

        # UI更新
        self.timelapse_start_button.setEnabled(True)
        self.timelapse_stop_button.setEnabled(False)
        self.timelapse_status_label.setText("タイムラプス: 停止中")

        # 動画ファイル作成
        self._write_timelapse_video()

        print("[Timelapse] 停止")

    def _stop_timelapse_recording(self):
        """タイムラプス録画の自動停止（継続時間経過）"""
        print("[Timelapse] 継続時間経過により自動停止")
        self.stop_timelapse()

    def _capture_timelapse_frame(self):
        """タイムラプス用フレーム取得（TL情報はadd_overlaysで追加済み）"""
        if (
            not self.timelapse_active
            or not hasattr(self, "last_frame")
            or self.last_frame is None
        ):
            return

        # 現在時刻とフレームをバッファに保存（TL情報は既にadd_overlays_to_frame()で追加済み）
        timestamp = time.time()
        frame = self.last_frame.copy()

        # フレームが有効か確認
        if frame is None or len(frame.shape) != 3:
            print(
                f"[Timelapse] 警告: 無効なフレーム shape={frame.shape if frame is not None else 'None'}"
            )
            return

        self.timelapse_buffer.append((timestamp, frame))
        self.timelapse_total_frames += 1  # 総フレーム数を増加

        # ステータス更新
        frames_count = len(self.timelapse_buffer)
        elapsed_minutes = (timestamp - self.timelapse_start_time) / 60

        # 無制限モードの場合は残り時間を表示しない
        if self.timelapse_duration_minutes > 0:
            remaining_minutes = max(
                0, self.timelapse_duration_minutes - elapsed_minutes
            )
            status_text = f"タイムラプス: {self.timelapse_total_frames}フレーム (残り{remaining_minutes:.1f}分)"
        else:
            status_text = f"タイムラプス: {self.timelapse_total_frames}フレーム (経過{elapsed_minutes:.1f}分)"

        self.timelapse_status_label.setText(status_text)

        print(f"[Timelapse] フレーム取得: {self.timelapse_total_frames}枚目")

        # 10000フレーム到達時に自動保存
        if frames_count >= 100:
            print(
                f"[Timelapse] 10000フレーム到達 - Part {self.timelapse_part_number} を自動保存"
            )
            self._save_timelapse_part()

    def _save_timelapse_part(self):
        """タイムラプスの一部を保存（バッファをクリアしてタイムラプスは継続）"""
        if not self.timelapse_buffer:
            print("[Timelapse] バッファが空のため保存をスキップ")
            return

        # 開始時に取得したファイル番号を使用
        video_filename = self._get_timelapse_filename(self.timelapse_file_num)

        print(f"[Timelapse] Part {self.timelapse_part_number} を自動保存")

        if self._write_timelapse_frames(video_filename, 30.0, self.timelapse_buffer):
            print(f"[Timelapse] Part {self.timelapse_part_number} 保存完了")
            print(f"[Timelapse] 総フレーム数: {self.timelapse_total_frames}")
        else:
            print(f"[Timelapse] Part {self.timelapse_part_number} 保存失敗")

        # バッファをクリアして次のパートへ
        self.timelapse_buffer = []
        self.timelapse_part_number += 1
        print(
            f"[Timelapse] Part {self.timelapse_part_number} 開始（総フレーム数: {self.timelapse_total_frames}）"
        )

    def _get_timelapse_file_number(self):
        """タイムラプスの連番を取得（既存ファイルの最大番号+1）"""
        import glob

        os.makedirs(self.tmpdir, exist_ok=True)
        pattern = os.path.join(self.tmpdir, "timelapse_*.mp4")
        existing_files = glob.glob(pattern)

        if not existing_files:
            return 1

        # ファイル名から番号を抽出（timelapse_003.mp4 → 3, timelapse_003_part2.mp4 → 3）
        max_num = 0
        for filepath in existing_files:
            filename = os.path.basename(filepath)
            try:
                # "timelapse_" の後の数字部分を抽出
                num_str = filename.split("_")[1].split(".")[0].split("_")[0]
                num = int(num_str)
                max_num = max(max_num, num)
            except (IndexError, ValueError):
                continue

        return max_num + 1

    def _get_timelapse_filename(self, file_num, extension=".mp4"):
        """タイムラプスのファイル名を生成（分割保存時は常に_partXを付与）"""
        filename = f"timelapse_{file_num:03d}_part{self.timelapse_part_number}{extension}"
        return os.path.join(self.tmpdir, filename)

    def _write_timelapse_frames(self, video_filename, fps, frames):
        """タイムラプスフレームを動画ファイルに書き出し（mp4形式固定）"""
        if not frames:
            print("[Timelapse] フレームが空です")
            return False

        height, width, ch = frames[0][1].shape
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")

        print(f"[Timelapse] 書き出し開始: {video_filename}")
        print(f"[Timelapse] フレーム数: {len(frames)}, 出力FPS: {fps}")

        writer = cv2.VideoWriter(video_filename, fourcc, fps, (width, height))

        if not writer.isOpened():
            print("[Timelapse] エラー: VideoWriterの初期化に失敗")
            return False

        # フレーム書き込み
        for i, (timestamp, frame) in enumerate(frames):
            writer.write(frame)
            if (i + 1) % 1000 == 0:
                print(f"[Timelapse] 書き出し進捗: {i + 1}/{len(frames)}")

        writer.release()

        # 統計情報を計算
        video_duration = len(frames) / fps
        if len(frames) > 1:
            actual_duration = (frames[-1][0] - frames[0][0]) / 60
        else:
            actual_duration = 0

        print(f"[Timelapse] 書き出し完了: {video_filename}")
        print(
            f"[Timelapse] 実撮影時間: {actual_duration:.1f}分 → 動画時間: {video_duration:.1f}秒"
        )

        return True

    def _write_timelapse_video(self):
        """タイムラプス動画ファイル書き出し（最終パートまたは停止時）"""
        if not self.timelapse_buffer:
            print("[Timelapse] バッファが空のため書き出しをスキップ")
            return

        # 最終パートの保存（開始時に取得したファイル番号を使用）
        if self.timelapse_part_number > 1:
            print(f"[Timelapse] 最終パート (Part {self.timelapse_part_number}) を保存")

        video_filename = self._get_timelapse_filename(self.timelapse_file_num)

        if self._write_timelapse_frames(video_filename, 30.0, self.timelapse_buffer):
            print(f"[Timelapse] 総フレーム数: {self.timelapse_total_frames}")
            if self.timelapse_part_number > 1:
                print(
                    f"[Timelapse] 全{self.timelapse_part_number}パートの保存が完了しました"
                )
        else:
            print("[Timelapse] 最終パート保存失敗")

        # バッファをクリア
        self.timelapse_buffer = []

    def _stop_auto_recording(self):
        print(
            f"[DEBUG] _stop_auto_recording called, _auto_recording={getattr(self, '_auto_recording', False)}"
        )
        if getattr(self, "_auto_recording", False):
            print("[AutoRecord] 自動録画タイマー経過: 自動録画停止")
            self._auto_recording = False
            # Ensure stop_recording is called in main thread
            QTimer.singleShot(0, self.stop_recording)

    def start_recording(self, auto_filename=False):
        print(
            f"[DEBUG] start_recording called, is_recording={self.is_recording}, auto_filename={auto_filename}"
        )
        if not hasattr(self, "last_frame"):
            print("[DEBUG] start_recording: no last_frame attribute")
            return
        if self.last_frame is None:
            print("[DEBUG] start_recording: last_frame is None (no camera image yet)")
            return
        if self.is_recording:
            print("[DEBUG] start_recording: already recording, skip")
            return
        # --- バッファ方式で録画開始 ---
        self._recording_buffer = []
        if getattr(self, "_auto_recording", False):
            self._recording_mode = "auto"
        else:
            self._recording_mode = "manual"
        # プリトリガバッファを録画バッファに移す
        self._recording_buffer.extend(list(self.pre_record_buffer))
        self.is_recording = True
        self.record_seconds = 0
        self.record_time_label.setText("録画時間: 00:00")
        self._frame_count = 0
        self._last_fps = 0.0
        self.record_timer.start(1000)
        self.record_button.setEnabled(False)
        self.stop_button.setEnabled(True)

    def rescan_camera_ports(self):
        self.device_list = self.get_camera_devices()
        self.device_combo.clear()
        self.device_combo.addItems(self.device_list)
        self.current_device_index = 0

    def update_resolution_label(self):
        idx = self.device_combo.currentIndex()
        self.current_device_index = idx
        if idx < 0 or idx >= len(self.device_list):
            self.resolution_label.setText("")
            return
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()
            self.resolution_label.setText(f"解像度: {width} x {height}")
        else:
            self.resolution_label.setText("解像度: N/A")

    def update_fps(self):
        # FPS履歴・ラベル更新はウィンドウ可視時のみ
        if self.isVisible():
            fps = self._fps_frame_count
            self.fps_label.setText(f"FPS: {fps:.1f}")
            self.fps_history.append(fps)
            if len(self.fps_history) > self.fps_history_len:
                self.fps_history = self.fps_history[-self.fps_history_len :]
        self._fps_frame_count = 0

    def on_fps_changed(self, idx):
        # Only allow changing FPS when disconnected
        if self.cap is not None:
            QMessageBox.warning(
                self, "Warning", "Disconnect the camera before changing FPS."
            )
            self.fps_combo.blockSignals(True)
            # revert to previous selection
            self.fps_combo.setCurrentIndex(self.fps_options.index(self.selected_fps))
            self.fps_combo.blockSignals(False)
            return
        self.selected_fps = self.fps_options[idx]
        # FPS変更時にバッファサイズも更新
        self.pre_record_buffer = collections.deque(
            maxlen=self.selected_fps * self.pre_record_seconds
        )

    def on_pre_record_seconds_changed(self, val):
        self.pre_record_seconds = val
        self.pre_record_buffer = collections.deque(
            maxlen=self.selected_fps * self.pre_record_seconds
        )
        self.pre_record_buffer.clear()

    def update_record_time(self):
        self.record_seconds += 1
        m, s = divmod(self.record_seconds, 60)
        self.record_time_label.setText(f"録画時間: {m:02d}:{s:02d}")
        # Update FPS
        self._last_fps = self._frame_count
        self.fps_label.setText(f"FPS: {self._last_fps:.1f}")
        self._frame_count = 0

    def stop_recording(self):
        print(f"[DEBUG] stop_recording called, is_recording={self.is_recording}")
        if self.is_recording:
            self.is_recording = False
            # バッファ書き出し
            self._write_recording_buffer()
        else:
            print("[DEBUG] stop_recording: not recording")
        self.record_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.record_timer.stop()
        self.record_time_label.setText("録画時間: 00:00")
        self.fps_label.setText("FPS: 0.0")
        self._auto_recording = False  # 自動録画フラグも必ずリセット
        self._recording_mode = None
        # Stop auto_record_timer if running
        if hasattr(self, "_auto_record_timer") and self._auto_record_timer.isActive():
            print("[DEBUG] stop_recording: stopping _auto_record_timer")
            self._auto_record_timer.stop()
        # プリトリガバッファもクリア
        self.pre_record_buffer.clear()

    def _write_recording_buffer(self):
        # 録画バッファの内容を動画ファイルに書き出し
        if not self._recording_buffer:
            print("[Record] バッファが空です")
            return
        all_frames = self._recording_buffer
        # FPS計算（MPEG4標準の制限を考慮して60FPS上限）
        if len(all_frames) > 1:
            duration = all_frames[-1][0] - all_frames[0][0]
            calculated_fps = len(all_frames) / max(duration, 1e-3)
            fps_for_record = min(60.0, self.selected_fps, max(10.0, calculated_fps))
        else:
            fps_for_record = min(60.0, self.selected_fps)
        video_filename = create_tempnum("camera", self.tmpdir, ".mp4")
        print(
            f"[Record] 書き出し: {video_filename}, frames={len(all_frames)}, fps={fps_for_record:.2f}"
        )
        height, width, ch = all_frames[0][1].shape
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(
            video_filename, fourcc, fps_for_record, (width, height)
        )
        for _, frame in all_frames:
            writer.write(frame)
        writer.release()
        self._recording_buffer = []
        print("[Record] 書き出し完了")

    def save_image(self):
        # Use plot2d's create_tempnum to generate a unique filename
        if hasattr(self, "last_frame") and self.last_frame is not None:
            # create_tempnum(basename, prefix, ext)
            # Use current directory, prefix 'camera_', ext '.png'
            filename = create_tempnum("camera", self.tmpdir, ".png")
            cv2.imwrite(filename, self.last_frame)
            # QMessageBox.information(self, "Saved", f"Saved image: {filename}")

    def connect_camera(self):
        idx = self.device_combo.currentIndex()
        self.current_device_index = idx
        self.init_camera(idx)
        self.connect_button.setEnabled(False)
        self.disconnect_button.setEnabled(True)
        self._fps_frame_count = 0
        self.fps_label.setText("FPS: 0.0")
        self._fps_timer.start(1000)

    def disconnect_camera(self):
        if self.cap:
            self.cap.release()
            self.cap = None
        self.timer.stop()
        self.image_label.clear()
        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)
        self._fps_timer.stop()
        self.fps_label.setText("FPS: 0.0")
        self._ai_overlay_img = None

    def toggle_virtual_camera(self):
        pass

    def get_camera_devices(self):
        graph = FilterGraph()
        return graph.get_input_devices()

    def init_camera(self, index):
        if hasattr(self, "cap") and self.cap:
            self.cap.release()
        self.cap = cv2.VideoCapture(index)
        if self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_FPS, self.selected_fps)
            # Get actual resolution from camera
            width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            print(f"[Camera] Connected: Resolution = {width} x {height}")
            # Try to set timer interval based on FPS (ms)
            interval = int(1000 / self.selected_fps)
            self.timer.start(interval)
            self.image_label.setText("")
        else:
            self.timer.stop()
            self.image_label.setText("カメラが見つかりません")

    def change_camera(self, idx):
        self.current_device_index = idx
        # Do not auto-connect on change, only connect when button is pressed
        pass

    def update_frame(self):
        # メインスレッドでのみUI更新
        if self.last_frame is not None:
            rgb_image = cv2.cvtColor(self.last_frame, cv2.COLOR_BGR2RGB)
            h2, w2, ch = rgb_image.shape
            bytes_per_line = ch * w2
            rgb_copy = np.ascontiguousarray(rgb_image)
            qt_image = QImage(
                rgb_copy.data, w2, h2, bytes_per_line, QImage.Format_RGB888
            )
            qt_image = qt_image.copy()  # QImageのバッファを独立させる
            pixmap = QPixmap.fromImage(qt_image)
            max_w, max_h = 800, 600  # UI上の最大表示サイズ
            scaled_pixmap = pixmap.scaled(
                max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.image_label.setPixmap(scaled_pixmap)
        else:
            self.image_label.clear()


class App(MainWindow):

    def __init__(self, *args):

        # Don't create a new QApplication,
        # it would unhook the Events set by Traits on the existing QApplication.
        # Simply use the '.instance()' method to retrieve the existing one.
        self.app = QApplication.instance()
        if not self.app:  # create QApplication if it doesnt exist
            self.app = QApplication(sys.argv)
        MainWindow.__init__(self)
        plt.close("all")
        self.set_canvas(CameraWidget(), "UVC Camera (PyQt)")
        self.set_settingfile("./temp_setting/" + self.canva.rootname + ".ini")

        self.add_menu("File")
        self.add_function_to_menu("File", self.openAct)
        self.add_function_to_menu("File", self.exitAct)
        self.add_function_to_menu("File", self.get_settigfile)
        self.add_function_to_menu("File", self.plot_close)
        self.add_function_to_menu("File", self.canva.open_tempdir)
        self.add_function_to_menu("File", self.canva.open_newtempdir)
        plt.close("all")

    def plot_close(self):
        plt.close("all")

    def start_app(self):
        self.show()
        self.raise_()
        sys.exit(self.app.exec_())


if __name__ == "__main__":
    obj = App()
    obj.start_app()
