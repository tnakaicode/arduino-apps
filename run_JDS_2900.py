import sys
import serial
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
from PyQt5.QtCore import QTimer, pyqtSignal, QObject


# ==========================================
# 1. JDS-2900 シリアル制御クラス (Driver)
# ==========================================
class JDS2900Driver:
    def __init__(self, port="COM9", baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None

    def connect(self):
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

    def _send(self, cmd: str) -> str:
        """コマンドを送信し、応答を一行受け取る"""
        if not self.ser or not self.ser.is_open:
            return ""
        try:
            full_cmd = f"{cmd}\r\n".encode("utf-8")
            self.ser.write(full_cmd)
            # JDSシリーズの応答（通常は :r... または ok）を取得
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
        """波形を設定 (:w21=波形(CH1), :w22=波形(CH2)) 0:Sine, 1:Square, 2:Triangle"""
        cmd_num = 21 if channel == 1 else 22
        return self._send(f":w{cmd_num}={wave_type}.")

    def set_frequency(self, channel: int, freq_hz: float):
        """周波数を設定 (:w23=周波数,単位(CH1), :w24=周波数,単位(CH2))"""
        cmd_num = 23 if channel == 1 else 24
        # プロトコル仕様: 周波数は100倍(0.01Hzステップ用等)して、単位指定(0はHz)
        freq_val = int(freq_hz * 100)
        return self._send(f":w{cmd_num}={freq_val},0.")

    def set_amplitude(self, channel: int, amp_v: float):
        """振幅を設定 (:w25=振幅(CH1), :w26=振幅(CH2)) 単位は1000倍(mV表記相当)"""
        cmd_num = 25 if channel == 1 else 26
        amp_val = int(amp_v * 1000)
        return self._send(f":w{cmd_num}={amp_val}.")

    def set_offset(self, channel: int, offset_v: float):
        """DCオフセットを設定 (:w27=オフセット(CH1), :w28=オフセット(CH2))"""
        cmd_num = 27 if channel == 1 else 28
        # オフセットはオフセット値に1000を足して100倍する等の内部仕様があるため、
        # 機種固有のスケールに合わせて調整してください(基本はそのまま100倍等)
        offset_val = int((offset_v + 10.0) * 100)  # オフセット計算(仮)
        return self._send(f":w{cmd_num}={offset_val}.")

    # --- 読み出し(状態取得)コマンド群 ---
    def get_device_info(self):
        """デバイスの基本情報を取得"""
        return self._send(":r00=0.")

    def get_channel_status(self):
        """現在の全ステータスを一括取得
        JDSシリーズは :r20=0. などで現在のパラメータ群をカンマ区切りで一括返却します
        """
        res = self._send(":r20=0.")
        # 返ってきた文字列（例: :r20=1,0,100000,0,...）をパースする
        if res.startswith(":r20="):
            data = res.replace(":r20=", "").replace(".", "").split(",")
            return data
        return None


# ==========================================
# 2. PyQt6 メインウィンドウ ＆ 状態モニタ UI
# ==========================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JUNTEK JDS-2900 Controller")
        self.setGeometry(100, 100, 700, 450)

        # ドライバ初期化
        self.dev = JDS2900Driver(port="COM9", baudrate=115200)

        # 内部状態保持フラグ
        self.ch1_active = False
        self.ch2_active = False

        self.init_ui()

        # タイマーによる周期的な状態モニタ（1秒周期）
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self.update_monitor)

        # 自動接続試行
        if self.dev.connect():
            self.log("JDS-2900 に接続しました。(COM9)")
            info = self.dev.get_device_info()
            self.log(f"デバイス情報: {info}")
            self.monitor_timer.start(1000)  # 1000msごとに状態更新
        else:
            self.log("接続に失敗しました。COMポートを確認してください。")

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # 左側：制御＆モニタパネル
        left_panel = QVBoxLayout()

        # ーー チャンネル1制御 ーー
        ch1_box = QGroupBox("Channel 1 制御")
        ch1_grid = QGridLayout(ch1_box)

        ch1_grid.addWidget(QLabel("波形:"), 0, 0)
        self.ch1_wave = QComboBox()
        self.ch1_wave.addItems(
            ["正弦波 (Sine)", "矩形波 (Square)", "三角波 (Triangle)"]
        )
        self.ch1_wave.currentIndexChanged.connect(
            lambda: self.dev.set_waveform(1, self.ch1_wave.currentIndex())
        )
        ch1_grid.addWidget(self.ch1_wave, 0, 1)

        ch1_grid.addWidget(QLabel("周波数 (Hz):"), 1, 0)
        self.ch1_freq = QDoubleSpinBox()
        self.ch1_freq.setRange(0.01, 15000000.0)
        self.ch1_freq.setValue(1000.0)
        self.ch1_freq.setDecimals(2)
        ch1_grid.addWidget(self.ch1_freq, 1, 1)
        self.ch1_freq.valueChanged.connect(
            lambda: self.dev.set_frequency(1, self.ch1_freq.value())
        )

        ch1_grid.addWidget(QLabel("振幅 (Vpp):"), 2, 0)
        self.ch1_amp = QDoubleSpinBox()
        self.ch1_amp.setRange(0.001, 20.0)
        self.ch1_amp.setValue(5.0)
        ch1_grid.addWidget(self.ch1_amp, 2, 1)
        self.ch1_amp.valueChanged.connect(
            lambda: self.dev.set_amplitude(1, self.ch1_amp.value())
        )

        self.btn_ch1_out = QPushButton("CH1 Output: OFF")
        self.btn_ch1_out.setStyleSheet("background-color: #ffcccc;")
        self.btn_ch1_out.clicked.connect(self.toggle_ch1)
        ch1_grid.addWidget(self.btn_ch1_out, 3, 0, 1, 2)

        left_panel.addWidget(ch1_box)

        # ーー 状態表示モニタ ーー
        monitor_box = QGroupBox("リアルタイム状態モニタ")
        monitor_layout = QGridLayout(monitor_box)
        self.lbl_mon_ch1 = QLabel("CH1: -- Hz / -- V")
        self.lbl_mon_ch2 = QLabel("CH2: -- Hz / -- V")
        monitor_layout.addWidget(self.lbl_mon_ch1, 0, 0)
        monitor_layout.addWidget(self.lbl_mon_ch2, 1, 0)
        left_panel.addWidget(monitor_box)

        # 右側：シリアルログ表示
        right_panel = QVBoxLayout()
        right_panel.addWidget(QLabel("通信・履歴ログ:"))
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        right_panel.addWidget(self.log_text)

        main_layout.addLayout(left_panel, 60)
        main_layout.addLayout(right_panel, 40)

    def toggle_ch1(self):
        self.ch1_active = not self.ch1_active
        self.dev.set_output(self.ch1_active, self.ch2_active)
        if self.ch1_active:
            self.btn_ch1_out.setText("CH1 Output: ON")
            self.btn_ch1_out.setStyleSheet("background-color: #ccffcc;")
        else:
            self.btn_ch1_out.setText("CH1 Output: OFF")
            self.btn_ch1_out.setStyleSheet("background-color: #ffcccc;")

    def update_monitor(self):
        """定期的に機器からデータを取得してGUIのモニタテキストを更新"""
        status_data = self.dev.get_channel_status()
        if status_data and len(status_data) >= 4:
            try:
                # パース例（JDSのプロトコル配置に準拠して適宜調整してください）
                ch1_on_str = "ON" if status_data[0] == "1" else "OFF"
                ch2_on_str = "ON" if status_data[1] == "1" else "OFF"

                # 周波数は100で割って元に戻す
                raw_freq = float(status_data[2]) / 100.0

                self.lbl_mon_ch1.setText(
                    f"CH1 Status: [{ch1_on_str}]  現在の周波数: {raw_freq:.2f} Hz"
                )
                self.lbl_mon_ch2.setText(f"CH2 Status: [{ch2_on_str}]")
            except Exception as e:
                pass

    def log(self, message):
        self.log_text.append(f"[{time.strftime('%H:%M:%S')}] {message}")

    def closeEvent(self, event):
        self.monitor_timer.stop()
        self.dev.disconnect()
        event.accept()


# ==========================================
# 3. エントリーポイント
# ==========================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
