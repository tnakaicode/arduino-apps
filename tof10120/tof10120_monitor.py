import sys
import serial
import serial.tools.list_ports
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget,
                             QVBoxLayout, QHBoxLayout, QLabel,
                             QComboBox, QPushButton, QLCDNumber)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QFont


class SerialReader(QThread):
    data_received = pyqtSignal(int)
    error_occurred = pyqtSignal(str)

    def __init__(self, port, baudrate=9600):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self._running = False

    def run(self):
        try:
            with serial.Serial(self.port, self.baudrate, timeout=1) as ser:
                self._running = True
                while self._running:
                    line = ser.readline().decode("utf-8", errors="ignore").strip()
                    # フォーマット: "Distance: 123 mm"
                    if line.startswith("Distance:"):
                        parts = line.split()
                        if len(parts) >= 2:
                            try:
                                dist = int(parts[1])
                                self.data_received.emit(dist)
                            except ValueError:
                                pass
        except serial.SerialException as e:
            self.error_occurred.emit(str(e))

    def stop(self):
        self._running = False
        self.wait()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TOF10120 Distance Monitor")
        self.reader = None
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # ポート選択
        port_layout = QHBoxLayout()
        port_layout.addWidget(QLabel("Port:"))
        self.port_combo = QComboBox()
        self._refresh_ports()
        port_layout.addWidget(self.port_combo)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._refresh_ports)
        port_layout.addWidget(self.refresh_btn)
        layout.addLayout(port_layout)

        # 開始/停止
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("Start")
        self.start_btn.clicked.connect(self._start)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self._stop)
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        layout.addLayout(btn_layout)

        # 距離表示（LCD）
        self.lcd = QLCDNumber(6)
        self.lcd.setSegmentStyle(QLCDNumber.Flat)
        self.lcd.setMinimumHeight(100)
        layout.addWidget(self.lcd)

        unit_label = QLabel("mm")
        unit_label.setAlignment(Qt.AlignCenter)
        unit_label.setFont(QFont("Arial", 16))
        layout.addWidget(unit_label)

        # ステータス
        self.status_label = QLabel("Disconnected")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

    def _refresh_ports(self):
        self.port_combo.clear()
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_combo.addItems(ports)

    def _start(self):
        port = self.port_combo.currentText()
        if not port:
            return
        self.reader = SerialReader(port)
        self.reader.data_received.connect(self._update_display)
        self.reader.error_occurred.connect(self._on_error)
        self.reader.start()
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_label.setText(f"Connected: {port}")

    def _stop(self):
        if self.reader:
            self.reader.stop()
            self.reader = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("Disconnected")

    def _update_display(self, dist):
        self.lcd.display(dist)

    def _on_error(self, msg):
        self.status_label.setText(f"Error: {msg}")
        self._stop()

    def closeEvent(self, event):
        self._stop()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.resize(400, 300)
    win.show()
    sys.exit(app.exec_())
