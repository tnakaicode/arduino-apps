"""
Arduino Uno ボード情報まとめ
----------------------------------------
【デジタルピン（D0～D13）】
- D0: RX（シリアル受信専用、通常は使用しない）
- D1: TX（シリアル送信専用、通常は使用しない）
- D2～D13: 通常のデジタル入出力（DI: Digital Input／DO: Digital Output）として使用可能
    - DI（デジタル入力）: 外部信号のHIGH/LOWを読み取る
    - DO（デジタル出力）: ピンからHIGH（5V）/LOW（0V）を出力する
- OUTPUT時はピンに直接5V/0Vが出力される（内部に電流制限抵抗なし）
- INPUT_PULLUPで内部プルアップ抵抗（約20～50kΩ）を有効化可能
- 1ピンあたり最大20mA、全ピン合計で100mA程度まで推奨

【アナログピン（A0～A5）】
- アナログ入力（0～5V, 10bit ADC, 0～1023）
- 一部ピンはアナログ出力（PWM, analogWrite）にも利用可能

【注意点】
- DOピンで外部回路を駆動する場合は必ず外付け抵抗を入れる（LED等は220Ω～1kΩ推奨）
- DIピンにも電流制限抵抗は内蔵されていない（必要に応じて外付け）
- D0/D1はシリアル通信専用なので、通常の入出力には使わない
- PWM出力は高速なON/OFFの平均電圧であり、真のアナログ出力ではない
- AIピンでPWM出力を測定する場合はローパスフィルタ（RC回路）を挟むと平均電圧が安定

【電気的仕様】
- 動作電圧: 5V
- HIGHレベル: 4.5V以上（出力時は約5V）
- LOWレベル: 0.8V以下
- 入力インピーダンス: 数MΩ以上（INPUT時）
----------------------------------------
"""

import sys
import serial
import time
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLabel,
    QGridLayout,
    QPushButton,
    QLineEdit,
    QComboBox,
    QHBoxLayout,
)
from PyQt5.QtCore import QTimer
from functools import partial
import serial.tools.list_ports

BAUD_RATE = 9600


class ArduinoMonitor(QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Arduino Pin Monitor")
        self.resize(500, 350)
        self.ser = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_pins)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # --- COMポート選択UI ---
        com_layout = QHBoxLayout()
        self.combobox = QComboBox()
        self.refresh_button = QPushButton("再スキャン")
        self.connect_button = QPushButton("接続")
        self.disconnect_button = QPushButton("切断")
        self.disconnect_button.setEnabled(False)
        com_layout.addWidget(QLabel("COMポート:"))
        com_layout.addWidget(self.combobox)
        com_layout.addWidget(self.refresh_button)
        com_layout.addWidget(self.connect_button)
        com_layout.addWidget(self.disconnect_button)
        layout.addLayout(com_layout)

        self.refresh_button.clicked.connect(self.refresh_ports)
        self.connect_button.clicked.connect(self.connect_serial)
        self.disconnect_button.clicked.connect(self.disconnect_serial)
        self.refresh_ports()

        # Digitalピン用タイトル
        digital_title = QLabel("Digital Pins (D0-D13)")
        digital_title.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(digital_title)
        self.digital_grid = QGridLayout()
        self.digital_labels = []
        self.digital_value_labels = []  # 読み値
        self.digital_set_edits = []  # 出力時の値
        self.digital_mode_buttons = []  # INPUT/OUTPUT切替
        self.digital_pullup_buttons = []  # INPUT/INPUT_PULLUP切替
        self.digital_modes = ["INPUT"] * 14
        self.digital_pullups = [False] * 14
        for i in range(14):
            label = QLabel(f"D{i}")
            value_label = QLabel("?")
            set_edit = QLineEdit()
            set_edit.setFixedWidth(40)
            set_edit.setText("0")  # デフォルト値を0に
            set_edit.setReadOnly(True)
            set_edit.editingFinished.connect(partial(self.send_output_value, i))
            btn_mode = QPushButton("INPUT")
            btn_mode.setCheckable(True)
            btn_mode.setChecked(True)
            btn_mode.clicked.connect(lambda checked, idx=i: self.toggle_mode(idx))
            btn_pullup = QPushButton("PULLUP:OFF")
            btn_pullup.setCheckable(True)
            btn_pullup.setChecked(False)
            btn_pullup.clicked.connect(lambda checked, idx=i: self.toggle_pullup(idx))
            self.digital_labels.append(label)
            self.digital_value_labels.append(value_label)
            self.digital_set_edits.append(set_edit)
            self.digital_mode_buttons.append(btn_mode)
            self.digital_pullup_buttons.append(btn_pullup)
            self.digital_grid.addWidget(label, i, 0)
            self.digital_grid.addWidget(value_label, i, 1)
            self.digital_grid.addWidget(set_edit, i, 2)
            self.digital_grid.addWidget(btn_mode, i, 3)
            self.digital_grid.addWidget(btn_pullup, i, 4)
        layout.addLayout(self.digital_grid)

        # Analogピン用タイトル
        analog_title = QLabel("Analog Pins (A0-A5)")
        analog_title.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(analog_title)
        self.analog_grid = QGridLayout()
        self.analog_labels = []
        self.analog_value_edits = []  # 読み値
        self.analog_set_edits = []  # 出力時の値
        self.analog_mode_buttons = []
        self.analog_modes = ["INPUT"] * 6
        for i in range(6):
            label = QLabel(f"A{i}")
            value_edit = QLineEdit()
            value_edit.setReadOnly(True)
            value_edit.setText("?")
            set_edit = QLineEdit()
            set_edit.setFixedWidth(50)
            set_edit.setText("")
            set_edit.setReadOnly(True)
            set_edit.editingFinished.connect(partial(self.send_analog_output_value, i))
            btn = QPushButton("INPUT")
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.clicked.connect(lambda checked, idx=i: self.toggle_analog_mode(idx))
            self.analog_labels.append(label)
            self.analog_value_edits.append(value_edit)
            self.analog_set_edits.append(set_edit)
            self.analog_mode_buttons.append(btn)
            self.analog_grid.addWidget(label, i, 0)
            self.analog_grid.addWidget(value_edit, i, 1)
            self.analog_grid.addWidget(set_edit, i, 2)
            self.analog_grid.addWidget(btn, i, 3)
        layout.addLayout(self.analog_grid)
        self.setLayout(layout)

    def refresh_ports(self):
        self.combobox.clear()
        ports = list(serial.tools.list_ports.comports())
        for port in ports:
            # 表示例: COM3 (Arduino Uno)
            desc = f"{port.device} ({port.description})"
            self.combobox.addItem(desc, port.device)
        if ports:
            self.connect_button.setEnabled(True)
        else:
            self.connect_button.setEnabled(False)

    def connect_serial(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
        port = self.combobox.currentData()
        if not port:
            return
        try:
            self.ser = serial.Serial(port, BAUD_RATE, timeout=1)
            time.sleep(2)
            self.connect_button.setEnabled(False)
            self.disconnect_button.setEnabled(True)
            self.combobox.setEnabled(False)
            self.refresh_button.setEnabled(False)
            self.timer.start(100)
            print(f"[INFO] Connected to {port}")
        except Exception as e:
            print(f"[ERROR] 接続失敗: {e}")
            self.ser = None

    def disconnect_serial(self):
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None
        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)
        self.combobox.setEnabled(True)
        self.refresh_button.setEnabled(True)
        self.timer.stop()
        print("[INFO] 切断しました")

    def send_command(self, cmd):
        print(f"[SEND] {cmd.strip()}")
        if self.ser and self.ser.is_open:
            self.ser.write(cmd.encode("utf-8"))

    def send_analog_output_value(self, idx):
        # OUTPUTモード時のみ値を送信
        if self.analog_modes[idx] == "OUTPUT":
            val = self.analog_set_edits[idx].text().strip()
            try:
                pwm = int(val)
                if 0 <= pwm <= 255:
                    cmd = f"SETVAL,A{idx},PWM,{pwm}\n"
                    self.send_command(cmd)
            except Exception:
                pass

    def toggle_analog_mode(self, idx):
        # 現在のモードを切り替え
        if self.analog_modes[idx] == "INPUT":
            self.analog_modes[idx] = "OUTPUT"
            self.analog_mode_buttons[idx].setText("OUTPUT")
            self.analog_mode_buttons[idx].setChecked(False)
            self.analog_set_edits[idx].setReadOnly(False)
            cmd = f"SETMODE,A{idx},OUTPUT\n"
            self.send_command(cmd)
            # Editの値をすぐ送信
            val = self.analog_set_edits[idx].text().strip()
            try:
                pwm = int(val)
                if 0 <= pwm <= 255:
                    setval_cmd = f"SETVAL,A{idx},PWM,{pwm}\n"
                    self.send_command(setval_cmd)
            except Exception:
                pass
        else:
            self.analog_modes[idx] = "INPUT"
            self.analog_mode_buttons[idx].setText("INPUT")
            self.analog_mode_buttons[idx].setChecked(True)
            self.analog_set_edits[idx].setReadOnly(True)
            cmd = f"SETMODE,A{idx},INPUT\n"
            self.send_command(cmd)

    def send_output_value(self, idx):
        # OUTPUTモード時のみ値を送信
        if self.digital_modes[idx] == "OUTPUT":
            val = self.digital_set_edits[idx].text().strip()
            if val in ("0", "1"):
                cmd = f"SETVAL,D{idx},{val}\n"
                self.send_command(cmd)
        # Arduino側でコマンドを受信しdigitalWriteする処理が必要

    def toggle_mode(self, idx):
        # INPUT/OUTPUTのみ切替
        if self.digital_modes[idx] == "INPUT":
            self.digital_modes[idx] = "OUTPUT"
            self.digital_mode_buttons[idx].setText("OUTPUT")
            self.digital_mode_buttons[idx].setChecked(False)
            self.digital_set_edits[idx].setReadOnly(False)
            cmd = f"SETMODE,D{idx},OUTPUT\n"
            self.send_command(cmd)
            val = self.digital_set_edits[idx].text().strip()
            if val in ("0", "1"):
                setval_cmd = f"SETVAL,D{idx},{val}\n"
                self.send_command(setval_cmd)
        else:
            self.digital_modes[idx] = "INPUT"
            self.digital_mode_buttons[idx].setText("INPUT")
            self.digital_mode_buttons[idx].setChecked(True)
            self.digital_set_edits[idx].setReadOnly(True)
            # PULLUP状態に応じてコマンド送信
            if self.digital_pullups[idx]:
                cmd = f"SETMODE,D{idx},INPUT_PULLUP\n"
            else:
                cmd = f"SETMODE,D{idx},INPUT\n"
            self.send_command(cmd)

    def toggle_pullup(self, idx):
        # INPUTモード時のみPULLUP切替
        if self.digital_modes[idx] != "INPUT":
            return
        self.digital_pullups[idx] = not self.digital_pullups[idx]
        if self.digital_pullups[idx]:
            self.digital_pullup_buttons[idx].setText("PULLUP:ON")
            cmd = f"SETMODE,D{idx},INPUT_PULLUP\n"
        else:
            self.digital_pullup_buttons[idx].setText("PULLUP:OFF")
            cmd = f"SETMODE,D{idx},INPUT\n"
        self.send_command(cmd)

    def update_pins(self):
        # Arduino側が自動送信する場合、READコマンドは送らず受信のみ
        if not self.ser or not self.ser.is_open:
            return
        try:
            line = self.ser.readline()
            try:
                line = line.decode("utf-8", errors="replace").strip()
            except Exception:
                # デコードエラー時は無視して再接続を試みる
                self.try_reconnect()
                return
            if not line:
                return
            # 例: DI/O:INPUT,1;...;AI/O:123,456,789,...
            parts = line.split(";AI/O:")
            if len(parts) != 2:
                return
            dio_part = parts[0].replace("DI/O:", "")
            aio_part = parts[1]
            digital_items = dio_part.split(";")
            # digital_items: ["INPUT,1", ...] 14個
            for i in range(14):
                if i >= 2:
                    try:
                        mode_val = digital_items[i].split(",")
                        val = mode_val[1] if len(mode_val) > 1 else "?"
                        self.digital_value_labels[i].setText(val)
                    except Exception:
                        self.digital_value_labels[i].setText("?")
                else:
                    self.digital_value_labels[i].setText("?")
            analog_values = aio_part.split(",")
            for i, val in enumerate(analog_values):
                try:
                    v = int(val)
                    voltage = v * 5.0 / 1023
                    self.analog_value_edits[i].setText(f"{voltage:.2f} V")
                except Exception:
                    self.analog_value_edits[i].setText(val)
        except (serial.SerialException, OSError):
            self.try_reconnect()
        except Exception:
            pass

    def try_reconnect(self):
        if not self.ser:
            return
        try:
            self.ser.close()
        except Exception:
            pass
        # 再接続を試みる
        for _ in range(3):
            try:
                self.ser.open() if not self.ser.is_open else None
                return
            except Exception:
                time.sleep(1)
        # 3回失敗したら何もしない（次回timerで再度試行）

    def closeEvent(self, event):
        try:
            if self.ser:
                self.ser.close()
        except Exception:
            pass
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = ArduinoMonitor()
    win.show()
    sys.exit(app.exec_())
