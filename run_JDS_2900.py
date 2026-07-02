import sys
import serial
import serial.tools.list_ports
import time
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QComboBox,
    QDoubleSpinBox,
    QTextEdit,
)
from PyQt5.QtCore import QTimer


# ==========================================
# 1. JDS-2900 シリアル制御クラス (Driver)
# ==========================================
class JDS2900Driver:
    def __init__(self, port="COM9", baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None

    def connect(self, port=None):
        if port:
            self.port = port
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=0.5)
            time.sleep(1.0)  # 接続安定待ち
            return True
        except Exception as e:
            print(f"接続エラー: {e}")
            return False

    def disconnect(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            self.ser = None

    def is_connected(self):
        return self.ser is not None and self.ser.is_open

    def _send(self, cmd: str) -> str:
        """コマンドを送信し、応答を一行受け取る"""
        if not self.is_connected():
            return ""
        try:
            full_cmd = f"{cmd}\r\n".encode("utf-8")
            self.ser.write(full_cmd)
            res = self.ser.readline().decode("utf-8").strip()
            return res
        except Exception as e:
            print(f"通信エラー: {e}")
            return ""

    # --- 書き込み(制御)コマンド群 ---
    def set_output(self, ch1_on: bool, ch2_on: bool):
        """両チャンネルの出力を設定 (:w20=CH1,CH2.)"""
        val1 = "1" if ch1_on else "0"
        val2 = "1" if ch2_on else "0"
        return self._send(f":w20={val1},{val2}.")

    def set_waveform(self, channel: int, wave_type: int):
        """波形を設定 (CH1: :w21, CH2: :w22) 0:Sine, 1:Square, 2:Triangle"""
        cmd_num = 21 if channel == 1 else 22
        return self._send(f":w{cmd_num}={wave_type}.")

    def set_frequency(self, channel: int, freq_hz: float):
        """周波数を設定 (CH1: :w23, CH2: :w24)"""
        cmd_num = 23 if channel == 1 else 24
        freq_val = int(freq_hz * 100)  # 0.01Hz単位
        return self._send(f":w{cmd_num}={freq_val},0.")

    def set_amplitude(self, channel: int, amp_v: float):
        """振幅を設定 (CH1: :w25, CH2: :w26)"""
        cmd_num = 25 if channel == 1 else 26
        amp_val = int(amp_v * 1000)  # mV単位
        return self._send(f":w{cmd_num}={amp_val}.")

    def set_offset(self, channel: int, offset_v: float):
        """DCオフセットを設定 (CH1: :w27, CH2: :w28)"""
        cmd_num = 27 if channel == 1 else 28
        # JDSシリーズのオフセットは通常「(設定値 + 10) * 100」または「設定値 * 100 + 1000」等の固有バイアスがあります
        offset_val = int((offset_v + 10.0) * 100)
        return self._send(f":w{cmd_num}={offset_val}.")

    # --- 読み出し(状態取得)コマンド群 ---
    def get_device_info(self):
        """デバイスの基本情報を取得"""
        return self._send(":r00=0.")

    def get_channel_status(self):
        """現在の全ステータスを一括取得"""
        res = self._send(":r20=0.")
        if res.startswith(":r20="):
            # ":r20=" と末尾の "." を除外してカンマで分割
            data = res.replace(":r20=", "").replace(".", "").split(",")
            return data
        return None


# ==========================================
# 2. PyQt5 メインウィンドウ ＆ 状態モニタ UI
# ==========================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JUNTEK JDS-2900 Advanced Controller")
        self.setGeometry(100, 100, 900, 550)

        # ドライバ初期化
        self.dev = JDS2900Driver()

        # 各チャンネルの出力状態フラグ
        self.ch1_active = False
        self.ch2_active = False

        self.init_ui()

        # タイマーによる周期的な状態モニタ（1秒周期）
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self.update_monitor)

        # 初期状態でコントロールUIを無効化（接続後に有効化）
        self.set_controls_enabled(False)
        self.refresh_com_ports()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # ーー 接続管理トップバー ーー
        conn_layout = QHBoxLayout()
        conn_layout.addWidget(QLabel("COMポート:"))
        self.combo_port = QComboBox()
        conn_layout.addWidget(self.combo_port)

        self.btn_refresh = QPushButton("更新")
        self.btn_refresh.clicked.connect(self.refresh_com_ports)
        conn_layout.addWidget(self.btn_refresh)

        self.btn_connect = QPushButton("接続")
        self.btn_connect.setStyleSheet("background-color: #e1f5fe;")
        self.btn_connect.clicked.connect(self.toggle_connection)
        conn_layout.addWidget(self.btn_connect)

        main_layout.addLayout(conn_layout)

        # ーー メインコントロールエリア（左右分割） ーー
        ctrl_layout = QHBoxLayout()

        # ーー チャンネル1制御ボックス ーー
        self.ch1_box = QGroupBox("Channel 1 (CH1) 制御")
        ch1_grid = QGridLayout(self.ch1_box)
        self.setup_channel_ui(ch1_grid, channel=1)
        ctrl_layout.addWidget(self.ch1_box)

        # ーー チャンネル2制御ボックス ーー
        self.ch2_box = QGroupBox("Channel 2 (CH2) 制御")
        ch2_grid = QGridLayout(self.ch2_box)
        self.setup_channel_ui(ch2_grid, channel=2)
        ctrl_layout.addWidget(self.ch2_box)

        main_layout.addLayout(ctrl_layout)

        # ーー ボトムエリア（リアルタイム状態モニタ ＆ ログ） ーー
        bottom_layout = QHBoxLayout()

        # 状態表示モニタパネル
        monitor_box = QGroupBox("リアルタイム状態モニタ (機器同期表示)")
        monitor_layout = QGridLayout(monitor_box)

        self.lbl_mon_ch1_title = QLabel("<b>【CH1 ステータス】</b>")
        self.lbl_mon_ch1_out = QLabel("出力: --")
        self.lbl_mon_ch1_wave = QLabel("波形: --")
        self.lbl_mon_ch1_freq = QLabel("周波数: -- Hz")
        self.lbl_mon_ch1_amp = QLabel("振幅: -- V")

        self.lbl_mon_ch2_title = QLabel("<b>【CH2 ステータス】</b>")
        self.lbl_mon_ch2_out = QLabel("出力: --")
        self.lbl_mon_ch2_wave = QLabel("波形: --")
        self.lbl_mon_ch2_freq = QLabel("周波数: -- Hz")
        self.lbl_mon_ch2_amp = QLabel("振幅: -- V")

        monitor_layout.addWidget(self.lbl_mon_ch1_title, 0, 0)
        monitor_layout.addWidget(self.lbl_mon_ch1_out, 1, 0)
        monitor_layout.addWidget(self.lbl_mon_ch1_wave, 2, 0)
        monitor_layout.addWidget(self.lbl_mon_ch1_freq, 3, 0)
        monitor_layout.addWidget(self.lbl_mon_ch1_amp, 4, 0)

        monitor_layout.addWidget(self.lbl_mon_ch2_title, 0, 1)
        monitor_layout.addWidget(self.lbl_mon_ch2_out, 1, 1)
        monitor_layout.addWidget(self.lbl_mon_ch2_wave, 2, 1)
        monitor_layout.addWidget(self.lbl_mon_ch2_freq, 3, 1)
        monitor_layout.addWidget(self.lbl_mon_ch2_amp, 4, 1)

        bottom_layout.addWidget(monitor_box, 50)

        # ログビュー
        log_box = QGroupBox("通信ログ")
        log_layout = QVBoxLayout(log_box)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        bottom_layout.addWidget(log_box, 50)

        main_layout.addLayout(bottom_layout)

    def setup_channel_ui(self, grid, channel):
        """CH1/CH2共通のコントロールUI組み立て"""
        # 波形選択
        grid.addWidget(QLabel("波形型:"), 0, 0)
        wave_combo = QComboBox()
        wave_combo.addItems(["正弦波 (Sine)", "矩形波 (Square)", "三角波 (Triangle)"])
        wave_combo.currentIndexChanged.connect(
            lambda idx: self.dev.set_waveform(channel, idx)
        )
        grid.addWidget(wave_combo, 0, 1)
        if channel == 1:
            self.ch1_wave = wave_combo
        else:
            self.ch2_wave = wave_combo

        # 周波数
        grid.addWidget(QLabel("周波数 (Hz):"), 1, 0)
        freq_spin = QDoubleSpinBox()
        freq_spin.setRange(0.01, 15000000.0)
        freq_spin.setValue(1000.0)
        freq_spin.setDecimals(2)
        freq_spin.setSingleStep(100.0)
        freq_spin.valueChanged.connect(lambda val: self.dev.set_frequency(channel, val))
        grid.addWidget(freq_spin, 1, 1)
        if channel == 1:
            self.ch1_freq = freq_spin
        else:
            self.ch2_freq = freq_spin

        # 振幅
        grid.addWidget(QLabel("振幅 (Vpp):"), 2, 0)
        amp_spin = QDoubleSpinBox()
        amp_spin.setRange(0.001, 20.0)
        amp_spin.setValue(5.0)
        amp_spin.setSingleStep(0.1)
        amp_spin.valueChanged.connect(lambda val: self.dev.set_amplitude(channel, val))
        grid.addWidget(amp_spin, 2, 1)
        if channel == 1:
            self.ch1_amp = amp_spin
        else:
            self.ch2_amp = amp_spin

        # オフセット
        grid.addWidget(QLabel("オフセット (V):"), 3, 0)
        offset_spin = QDoubleSpinBox()
        offset_spin.setRange(-10.0, 10.0)
        offset_spin.setValue(0.0)
        offset_spin.setSingleStep(0.1)
        offset_spin.valueChanged.connect(lambda val: self.dev.set_offset(channel, val))
        grid.addWidget(offset_spin, 3, 1)
        if channel == 1:
            self.ch1_offset = offset_spin
        else:
            self.ch2_offset = offset_spin

        # 個別出力ボタン
        btn_out = QPushButton(f"CH{channel} Output: OFF")
        btn_out.setStyleSheet("background-color: #ffcccc;")
        btn_out.clicked.connect(lambda: self.toggle_output(channel))
        grid.addWidget(btn_out, 4, 0, 1, 2)
        if channel == 1:
            self.btn_ch1_out = btn_out
        else:
            self.btn_ch2_out = btn_out

    def refresh_com_ports(self):
        """PCに接続されているCOMポートを検出してリストを更新"""
        self.combo_port.clear()
        ports = serial.tools.list_ports.comports()
        for p in ports:
            self.combo_port.addItem(p.device)
        # 候補がない場合のフォールバック
        if self.combo_port.count() == 0:
            self.combo_port.addItem("COM9")

    def toggle_connection(self):
        """手動接続・切断処理"""
        if not self.dev.is_connected():
            # 接続処理
            target_port = self.combo_port.currentText()
            if self.dev.connect(target_port):
                self.log(f"JDS-2900 ({target_port}) に接続しました。")
                info = self.dev.get_device_info()
                self.log(f"デバイス応答: {info}")

                self.btn_connect.setText("切断")
                self.btn_connect.setStyleSheet("background-color: #ffcdd2;")
                self.combo_port.setEnabled(False)
                self.btn_refresh.setEnabled(False)
                self.set_controls_enabled(True)

                # モニタタイマースタート
                self.monitor_timer.start(1000)
            else:
                self.log(f"ポート {target_port} への接続に失敗しました。")
        else:
            # 切断処理
            self.disconnect_device()

    def disconnect_device(self):
        self.monitor_timer.stop()
        self.dev.disconnect()
        self.log("デバイスを切断しました。")
        self.btn_connect.setText("接続")
        self.btn_connect.setStyleSheet("background-color: #e1f5fe;")
        self.combo_port.setEnabled(True)
        self.btn_refresh.setEnabled(True)
        self.set_controls_enabled(False)
        self.clear_monitor_labels()

    def set_controls_enabled(self, enabled: bool):
        """接続状態に応じて操作パネルをロック/解除"""
        self.ch1_box.setEnabled(enabled)
        self.ch2_box.setEnabled(enabled)

    def toggle_output(self, channel):
        """各チャンネルの独立ON/OFF制御"""
        if channel == 1:
            self.ch1_active = not self.ch1_active
        else:
            self.ch2_active = not self.ch2_active

        self.dev.set_output(self.ch1_active, self.ch2_active)
        self.update_output_button_styles()

    def update_output_button_styles(self):
        # CH1ボタン更新
        if self.ch1_active:
            self.btn_ch1_out.setText("CH1 Output: ON")
            self.btn_ch1_out.setStyleSheet("background-color: #ccffcc;")
        else:
            self.btn_ch1_out.setText("CH1 Output: OFF")
            self.btn_ch1_out.setStyleSheet("background-color: #ffcccc;")

        # CH2ボタン更新
        if self.ch2_active:
            self.btn_ch2_out.setText("CH2 Output: ON")
            self.btn_ch2_out.setStyleSheet("background-color: #ccffcc;")
        else:
            self.btn_ch2_out.setText("CH2 Output: OFF")
            self.btn_ch2_out.setStyleSheet("background-color: #ffcccc;")

    def update_monitor(self):
        """定期的に機器から状態文字列を読み込んでパースし、インジケータを更新"""
        status_data = self.dev.get_channel_status()

        # JDSシリーズの :r20= 応答パース
        # 正しいインデックス構造: [0]:CH1出力, [1]:CH2出力, [2]:CH1周波数, [3]:CH2周波数, [4]:CH1波形, [5]:CH2波形, [6]:CH1振幅, [7]:CH2振幅 ...
        if status_data and len(status_data) >= 8:
            try:
                # 1. 出力状態の同期
                ch1_out = "ON" if status_data[0] == "1" else "OFF"
                ch2_out = "ON" if status_data[1] == "1" else "OFF"
                self.ch1_active = status_data[0] == "1"
                self.ch2_active = status_data[1] == "1"
                self.update_output_button_styles()

                # 2. 周波数パース (0.01Hz単位を元に戻す)
                ch1_freq = float(status_data[2]) / 100.0
                ch2_freq = float(status_data[3]) / 100.0

                # 3. 波形パース
                wave_names = ["正弦波 (Sine)", "矩形波 (Square)", "三角波 (Triangle)"]
                ch1_w_idx = int(status_data[4])
                ch2_w_idx = int(status_data[5])
                ch1_wave = (
                    wave_names[ch1_w_idx] if ch1_w_idx < len(wave_names) else "その他"
                )
                wave_names[ch2_w_idx] if ch2_w_idx < len(wave_names) else "その他"
                ch2_wave = (
                    wave_names[ch2_w_idx] if ch2_w_idx < len(wave_names) else "その他"
                )

                # 4. 振幅パース (mV単位をVに戻す)
                ch1_amp = float(status_data[6]) / 1000.0
                ch2_amp = float(status_data[7]) / 1000.0

                # GUIラベルへの割り当て
                self.lbl_mon_ch1_out.setText(f"出力: {ch1_out}")
                self.lbl_mon_ch1_wave.setText(f"波形: {ch1_wave}")
                self.lbl_mon_ch1_freq.setText(f"周波数: {ch1_freq:,.2f} Hz")
                self.lbl_mon_ch1_amp.setText(f"振幅: {ch1_amp:.3f} V")

                self.lbl_mon_ch2_out.setText(f"出力: {ch2_out}")
                self.lbl_mon_ch2_wave.setText(f"波形: {ch2_wave}")
                self.lbl_mon_ch2_freq.setText(f"周波数: {ch2_freq:,.2f} Hz")
                self.lbl_mon_ch2_amp.setText(f"振幅: {ch2_amp:.3f} V")

            except Exception as e:
                # パースエラー時はログを出さずにスキップ
                pass

    def clear_monitor_labels(self):
        for lbl in [
            self.lbl_mon_ch1_out,
            self.lbl_mon_ch1_wave,
            self.lbl_mon_ch1_freq,
            self.lbl_mon_ch1_amp,
            self.lbl_mon_ch2_out,
            self.lbl_mon_ch2_wave,
            self.lbl_mon_ch2_freq,
            self.lbl_mon_ch2_amp,
        ]:
            lbl.setText("--")

    def log(self, message):
        self.log_text.append(f"[{time.strftime('%H:%M:%S')}] {message}")

    def closeEvent(self, event):
        """ウィンドウを閉じた時の終了処理"""
        self.disconnect_device()
        event.accept()


# ==========================================
# 3. エントリーポイント
# ==========================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
