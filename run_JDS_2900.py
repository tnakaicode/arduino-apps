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
        """両チャンネルの出力を個別に指定する (マニュアル正しい仕様)
        :w20=CH1_ON,CH2_ON. (1=ON, 0=OFF)
        """
        c1 = 1 if ch1_on else 0
        c2 = 1 if ch2_on else 0
        return self._send(f":w20={c1},{c2}.")

    def set_waveform(self, channel: int, wave_type: int):
        """波形を設定 (CH1: :w21, CH2: :w22)"""
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
        offset_val = int((offset_v + 10.0) * 100)
        return self._send(f":w{cmd_num}={offset_val}.")

    # --- 読み出し(状態取得)コマンド群 ---
    def get_device_info(self):
        return self._send(":r00=0.")

    def get_output_status(self):
        """出力ON/OFF状態を取得 (:r20=0.) -> 戻り値: 例 :R20=1,0."""
        res = self._send(":r20=0.")
        if res.upper().startswith(":R20="):
            cleaned = res.upper().replace(":R20=", "").replace(".", "")
            return cleaned.split(",")  # ['1', '0'] のような配列を返す
        return None


# ==========================================
# 2. PyQt5 メインウィンドウ
# ==========================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JUNTEK JDS-2900 Controller")
        self.setGeometry(100, 100, 900, 500)

        self.dev = JDS2900Driver()
        self.ch1_active = False
        self.ch2_active = False

        self.init_ui()

        # モニタ用タイマー（出力ON/OFF状態のみを安全に同期）
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self.update_monitor)

        self.set_controls_enabled(False)
        self.refresh_com_ports()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # 接続バー
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

        # コントロール
        ctrl_layout = QHBoxLayout()

        self.ch1_box = QGroupBox("Channel 1 (CH1) 制御")
        ch1_grid = QGridLayout(self.ch1_box)
        self.setup_channel_ui(ch1_grid, channel=1)
        ctrl_layout.addWidget(self.ch1_box)

        self.ch2_box = QGroupBox("Channel 2 (CH2) 制御")
        ch2_grid = QGridLayout(self.ch2_box)
        self.setup_channel_ui(ch2_grid, channel=2)
        ctrl_layout.addWidget(self.ch2_box)

        main_layout.addLayout(ctrl_layout)

        # ボトム（モニタ表示 ＆ ログ）
        bottom_layout = QHBoxLayout()

        monitor_box = QGroupBox("リアルタイム出力モニタ")
        monitor_layout = QGridLayout(monitor_box)
        self.lbl_mon_ch1_out = QLabel("CH1 出力: --")
        self.lbl_mon_ch2_out = QLabel("CH2 出力: --")
        self.lbl_mon_ch1_out.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.lbl_mon_ch2_out.setStyleSheet("font-size: 14px; font-weight: bold;")
        monitor_layout.addWidget(self.lbl_mon_ch1_out, 0, 0)
        monitor_layout.addWidget(self.lbl_mon_ch2_out, 0, 1)
        bottom_layout.addWidget(monitor_box, 40)

        log_box = QGroupBox("通信ログ")
        log_layout = QVBoxLayout(log_box)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        bottom_layout.addWidget(log_box, 60)

        main_layout.addLayout(bottom_layout)

    def setup_channel_ui(self, grid, channel):
        grid.addWidget(QLabel("波形型:"), 0, 0)
        wave_combo = QComboBox()
        wave_combo.addItems(["正弦波 (Sine)", "矩形波 (Square)", "三角波 (Triangle)"])
        wave_combo.currentIndexChanged.connect(
            lambda idx, ch=channel: self.send_waveform(ch, idx)
        )
        grid.addWidget(wave_combo, 0, 1)
        if channel == 1:
            self.ch1_wave = wave_combo
        else:
            self.ch2_wave = wave_combo

        grid.addWidget(QLabel("周波数 (Hz):"), 1, 0)
        freq_spin = QDoubleSpinBox()
        freq_spin.setRange(0.01, 15000000.0)
        freq_spin.setValue(1000.0)
        freq_spin.setDecimals(2)
        freq_spin.valueChanged.connect(
            lambda val, ch=channel: self.send_frequency(ch, val)
        )
        grid.addWidget(freq_spin, 1, 1)
        if channel == 1:
            self.ch1_freq = freq_spin
        else:
            self.ch2_freq = freq_spin

        grid.addWidget(QLabel("振幅 (Vpp):"), 2, 0)
        amp_spin = QDoubleSpinBox()
        amp_spin.setRange(0.001, 20.0)
        amp_spin.setValue(5.0)
        amp_spin.valueChanged.connect(
            lambda val, ch=channel: self.send_amplitude(ch, val)
        )
        grid.addWidget(amp_spin, 2, 1)
        if channel == 1:
            self.ch1_amp = amp_spin
        else:
            self.ch2_amp = amp_spin

        btn_out = QPushButton(f"CH{channel} Output: OFF")
        btn_out.setStyleSheet("background-color: #ffcccc;")
        btn_out.clicked.connect(lambda: self.toggle_output(channel))
        grid.addWidget(btn_out, 3, 0, 1, 2)
        if channel == 1:
            self.btn_ch1_out = btn_out
        else:
            self.btn_ch2_out = btn_out

    # --- 独立したコマンド送信処理 (シグナル競合防止) ---
    def send_waveform(self, ch, idx):
        if self.dev.is_connected():
            self.dev.set_waveform(ch, idx)

    def send_frequency(self, ch, val):
        if self.dev.is_connected():
            self.dev.set_frequency(ch, val)

    def send_amplitude(self, ch, val):
        if self.dev.is_connected():
            self.dev.set_amplitude(ch, val)

    def refresh_com_ports(self):
        self.combo_port.clear()
        ports = serial.tools.list_ports.comports()
        for p in ports:
            self.combo_port.addItem(p.device)
        if self.combo_port.count() == 0:
            self.combo_port.addItem("COM9")

    def toggle_connection(self):
        if not self.dev.is_connected():
            target_port = self.combo_port.currentText()
            if self.dev.connect(target_port):
                self.log(f"JDS-2900 ({target_port}) に接続しました。")
                info = self.dev.get_device_info()
                self.log(f"デバイス応答: {info}")
                self.btn_connect.setText("切断")
                self.btn_connect.setStyleSheet("background-color: #ffcdd2;")
                self.set_controls_enabled(True)
                self.monitor_timer.start(1000)
        else:
            self.disconnect_device()

    def disconnect_device(self):
        self.monitor_timer.stop()
        self.dev.disconnect()
        self.log("デバイスを切断しました。")
        self.btn_connect.setText("接続")
        self.btn_connect.setStyleSheet("background-color: #e1f5fe;")
        self.set_controls_enabled(False)
        self.lbl_mon_ch1_out.setText("CH1 出力: --")
        self.lbl_mon_ch2_out.setText("CH2 出力: --")

    def set_controls_enabled(self, enabled: bool):
        self.ch1_box.setEnabled(enabled)
        self.ch2_box.setEnabled(enabled)

    def toggle_output(self, channel):
        if channel == 1:
            self.ch1_active = not self.ch1_active
        else:
            self.ch2_active = not self.ch2_active
        self.dev.set_output(self.ch1_active, self.ch2_active)
        self.update_output_button_styles()

    def update_output_button_styles(self):
        # GUI部品のイベント発火を防ぐため、一時的にシグナルをブロック
        self.btn_ch1_out.blockSignals(True)
        self.btn_ch2_out.blockSignals(True)

        if self.ch1_active:
            self.btn_ch1_out.setText("CH1 Output: ON")
            self.btn_ch1_out.setStyleSheet("background-color: #ccffcc;")
            self.lbl_mon_ch1_out.setText("CH1 出力: ON")
        else:
            self.btn_ch1_out.setText("CH1 Output: OFF")
            self.btn_ch1_out.setStyleSheet("background-color: #ffcccc;")
            self.lbl_mon_ch1_out.setText("CH1 出力: OFF")

        if self.ch2_active:
            self.btn_ch2_out.setText("CH2 Output: ON")
            self.btn_ch2_out.setStyleSheet("background-color: #ccffcc;")
            self.lbl_mon_ch2_out.setText("CH2 出力: ON")
        else:
            self.btn_ch2_out.setText("CH2 Output: OFF")
            self.btn_ch2_out.setStyleSheet("background-color: #ffcccc;")
            self.lbl_mon_ch2_out.setText("CH2 出力: OFF")

        self.btn_ch1_out.blockSignals(False)
        self.btn_ch2_out.blockSignals(False)

    def update_monitor(self):
        """定期的に機器から出力状態のみを安全に同期"""
        status_data = self.dev.get_output_status()
        if status_data and len(status_data) >= 2:
            try:
                # 機器から返ってきた独立したON/OFF状態（'1' または '0'）を取得
                ch1_status_hardware = status_data[0] == "1"
                ch2_status_hardware = status_data[1] == "1"

                # 現在の内部状態と異なる場合のみ更新（無駄な書き込みループを防ぐ）
                if (self.ch1_active != ch1_status_hardware) or (
                    self.ch2_active != ch2_status_hardware
                ):
                    self.ch1_active = ch1_status_hardware
                    self.ch2_active = ch2_status_hardware
                    self.update_output_button_styles()
            except Exception:
                pass

    def log(self, message):
        self.log_text.append(f"[{time.strftime('%H:%M:%S')}] {message}")

    def closeEvent(self, event):
        self.disconnect_device()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
