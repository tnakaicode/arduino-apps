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

    # --- マニュアルに準拠した正しい一括送信型コマンド群 ---
    def set_output(self, ch1_on: bool, ch2_on: bool):
        """:w20=CH1状態,CH2状態. (1=ON, 0=OFF)"""
        c1 = 1 if ch1_on else 0
        c2 = 1 if ch2_on else 0
        return self._send(f":w20={c1},{c2}.")

    def set_waveforms(self, ch1_wave: int, ch2_wave: int):
        """:w21=CH1波形,CH2波形."""
        return self._send(f":w21={ch1_wave},{ch2_wave}.")

    def set_frequency(self, channel: int, freq_hz: float):
        """周波数のみコマンド番号が完全に独立しています (CH1=23, CH2=24)"""
        cmd_num = 23 if channel == 1 else 24
        freq_val = int(freq_hz * 100)  # 0.01Hz単位
        return self._send(f":w{cmd_num}={freq_val},0.")

    def set_amplitudes(self, ch1_amp_v: float, ch2_amp_v: float):
        """:w25=CH1振幅,CH2振幅. (単位: mV)"""
        a1 = int(ch1_amp_v * 1000)
        a2 = int(ch2_amp_v * 1000)
        return self._send(f":w25={a1},{a2}.")

    def set_offsets(self, ch1_offset_v: float, ch2_offset_v: float):
        """:w26=CH1オフセット,CH2オフセット."""
        o1 = int((ch1_offset_v + 10.0) * 100)
        o2 = int((ch2_offset_v + 10.0) * 100)
        return self._send(f":w26={o1},{o2}.")

    def get_device_info(self):
        return self._send(":r00=0.")


# ==========================================
# 2. PyQt5 メインウィンドウ
# ==========================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JUNTEK JDS-2900 Independent Controller")
        self.setGeometry(100, 100, 850, 450)

        self.dev = JDS2900Driver()

        # 相手側の既存の値を壊さずにペア送信するため、現在のGUI設定値を完全にキャッシュ
        self.cache = {
            "ch1_on": False,
            "ch2_on": False,
            "ch1_wave": 0,
            "ch2_wave": 0,
            "ch1_amp": 5.0,
            "ch2_amp": 5.0,
            "ch1_offset": 0.0,
            "ch2_offset": 0.0,
        }

        self.init_ui()
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

        # コントロールパネル（左右独立構造）
        ctrl_layout = QHBoxLayout()

        # CH1 グループ
        self.ch1_box = QGroupBox("Channel 1 (CH1) 制御")
        ch1_grid = QGridLayout(self.ch1_box)
        self.setup_channel_ui(ch1_grid, channel=1)
        ctrl_layout.addWidget(self.ch1_box)

        # CH2 グループ
        self.ch2_box = QGroupBox("Channel 2 (CH2) 制御")
        ch2_grid = QGridLayout(self.ch2_box)
        self.setup_channel_ui(ch2_grid, channel=2)
        ctrl_layout.addWidget(self.ch2_box)

        main_layout.addLayout(ctrl_layout)

        # 通信ログエリア
        log_box = QGroupBox("通信ログ")
        log_layout = QVBoxLayout(log_box)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        main_layout.addWidget(log_box)

    def setup_channel_ui(self, grid, channel):
        # 波形
        grid.addWidget(QLabel("波形型:"), 0, 0)
        wave_combo = QComboBox()
        wave_combo.addItems(["正弦波 (Sine)", "矩形波 (Square)", "三角波 (Triangle)"])
        wave_combo.currentIndexChanged.connect(
            lambda idx, ch=channel: self.on_waveform_changed(ch, idx)
        )
        grid.addWidget(wave_combo, 0, 1)

        # 周波数
        grid.addWidget(QLabel("周波数 (Hz):"), 1, 0)
        freq_spin = QDoubleSpinBox()
        freq_spin.setRange(0.01, 15000000.0)
        freq_spin.setValue(1000.0)
        freq_spin.setDecimals(2)
        freq_spin.setSingleStep(100.0)
        freq_spin.valueChanged.connect(
            lambda val, ch=channel: self.on_frequency_changed(ch, val)
        )
        grid.addWidget(freq_spin, 1, 1)

        # 振幅
        grid.addWidget(QLabel("振幅 (Vpp):"), 2, 0)
        amp_spin = QDoubleSpinBox()
        amp_spin.setRange(0.001, 20.0)
        amp_spin.setValue(5.0)
        amp_spin.setSingleStep(0.1)
        amp_spin.valueChanged.connect(
            lambda val, ch=channel: self.on_amplitude_changed(ch, val)
        )
        grid.addWidget(amp_spin, 2, 1)

        # オフセット
        grid.addWidget(QLabel("オフセット (V):"), 3, 0)
        offset_spin = QDoubleSpinBox()
        offset_spin.setRange(-10.0, 10.0)
        offset_spin.setValue(0.0)
        offset_spin.setSingleStep(0.1)
        offset_spin.valueChanged.connect(
            lambda val, ch=channel: self.on_offset_changed(ch, val)
        )
        grid.addWidget(offset_spin, 3, 1)

        # 出力ボタン
        btn_out = QPushButton(f"CH{channel} Output: OFF")
        btn_out.setStyleSheet("background-color: #ffcccc;")
        btn_out.clicked.connect(lambda: self.on_output_toggled(channel))
        grid.addWidget(btn_out, 4, 0, 1, 2)

        if channel == 1:
            self.btn_ch1_out = btn_out
        else:
            self.btn_ch2_out = btn_out

    # --- キャッシュの値を合成して、相手側の設定を壊さずに送信するロジック ---
    def on_waveform_changed(self, ch, idx):
        self.cache[f"ch{ch}_wave"] = idx
        if self.dev.is_connected():
            res = self.dev.set_waveforms(self.cache["ch1_wave"], self.cache["ch2_wave"])
            self.log(f"波形設定変更 (応答: {res})")

    def on_frequency_changed(self, ch, val):
        if self.dev.is_connected():
            res = self.dev.set_frequency(ch, val)  # 周波数のみ単独コマンド
            self.log(f"CH{ch} 周波数設定変更 -> {val} Hz (応答: {res})")

    def on_amplitude_changed(self, ch, val):
        self.cache[f"ch{ch}_amp"] = val
        if self.dev.is_connected():
            res = self.dev.set_amplitudes(self.cache["ch1_amp"], self.cache["ch2_amp"])
            self.log(f"振幅設定変更 (応答: {res})")

    def on_offset_changed(self, ch, val):
        self.cache[f"ch{ch}_offset"] = val
        if self.dev.is_connected():
            res = self.dev.set_offsets(
                self.cache["ch1_offset"], self.cache["ch2_offset"]
            )
            self.log(f"オフセット設定変更 (応答: {res})")

    def on_output_toggled(self, ch):
        self.cache[f"ch{ch}_on"] = not self.cache[f"ch{ch}_on"]
        if self.dev.is_connected():
            res = self.dev.set_output(self.cache["ch1_on"], self.cache["ch2_on"])
            self.log(f"CH{ch} 出力状態切り替え (応答: {res})")
        self.update_output_button_styles()

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
                self.combo_port.setEnabled(False)
                self.btn_refresh.setEnabled(False)
                self.set_controls_enabled(True)
            else:
                self.log(f"ポート {target_port} への接続に失敗しました。")
        else:
            self.disconnect_device()

    def disconnect_device(self):
        self.dev.disconnect()
        self.log("デバイスを切断しました。")
        self.btn_connect.setText("接続")
        self.btn_connect.setStyleSheet("background-color: #e1f5fe;")
        self.combo_port.setEnabled(True)
        self.btn_refresh.setEnabled(True)
        self.set_controls_enabled(False)

        # 状態リセット
        self.cache["ch1_on"] = False
        self.cache["ch2_on"] = False
        self.update_output_button_styles()

    def set_controls_enabled(self, enabled: bool):
        self.ch1_box.setEnabled(enabled)
        self.ch2_box.setEnabled(enabled)

    def update_output_button_styles(self):
        # CH1
        if self.cache["ch1_on"]:
            self.btn_ch1_out.setText("CH1 Output: ON")
            self.btn_ch1_out.setStyleSheet("background-color: #ccffcc;")
        else:
            self.btn_ch1_out.setText("CH1 Output: OFF")
            self.btn_ch1_out.setStyleSheet("background-color: #ffcccc;")
        # CH2
        if self.cache["ch2_on"]:
            self.btn_ch2_out.setText("CH2 Output: ON")
            self.btn_ch2_out.setStyleSheet("background-color: #ccffcc;")
        else:
            self.btn_ch2_out.setText("CH2 Output: OFF")
            self.btn_ch2_out.setStyleSheet("background-color: #ffcccc;")

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
