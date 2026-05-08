"""
Picoのプログラムを停止してファイルを書き込むスクリプト
使い方: python pico_upload.py <送るファイル> <Pico側のパス>
例:     python pico_upload.py pico_gpio_web/pico_main.py /main.py
"""
import sys
import time
import serial

PORT = "/dev/ttyACM1"
BAUD = 115200


def enter_raw_repl(ser):
    """Ctrl+C → Ctrl+A でRAW REPLに入る"""
    # Ctrl+C を連打して実行中プログラムを止める
    for _ in range(10):
        ser.write(b"\r\x03")
        time.sleep(0.1)
    time.sleep(0.5)
    ser.read(ser.in_waiting)  # バッファクリア

    # Ctrl+A でRAW REPLへ
    ser.write(b"\x01")
    time.sleep(0.5)
    resp = ser.read(ser.in_waiting).decode(errors="replace")
    print(f"[RAW REPL応答] {repr(resp)}")
    return "raw REPL" in resp or ">" in resp


def upload_file(ser, local_path, remote_path):
    """RAW REPLモードでファイルを書き込む"""
    with open(local_path, "rb") as f:
        data = f.read()

    # チャンク分割して書き込む（大きいファイル対応）
    chunk_size = 128
    chunks = [data[i:i+chunk_size] for i in range(0, len(data), chunk_size)]

    # ファイルオープン
    cmd = f"f=open('{remote_path}','wb')\r\n"
    ser.write(cmd.encode())
    ser.write(b"\x04")
    time.sleep(1)
    ser.read(ser.in_waiting)

    # チャンクごとに書き込み
    for i, chunk in enumerate(chunks):
        cmd = f"f.write({chunk!r})\r\n"
        ser.write(cmd.encode())
        ser.write(b"\x04")
        time.sleep(0.5)
        ser.read(ser.in_waiting)
        print(f"  書き込み中... {i+1}/{len(chunks)}", end="\r")

    # ファイルクローズ
    ser.write(b"f.close()\r\n")
    ser.write(b"\x04")
    time.sleep(0.5)
    resp = ser.read(ser.in_waiting).decode(errors="replace")
    print(f"\n[完了応答] {repr(resp)}")

    # 通常モードに戻る (Ctrl+B)
    ser.write(b"\x02")
    time.sleep(0.3)
    return True


if __name__ == "__main__":
    local = sys.argv[1] if len(sys.argv) > 1 else "pico_gpio_web/pico_main.py"
    remote = sys.argv[2] if len(sys.argv) > 2 else "/main.py"

    print(f"接続: {PORT}")
    ser = serial.Serial(PORT, BAUD, timeout=2)
    time.sleep(0.5)

    print("RAW REPLに移行中...")
    if not enter_raw_repl(ser):
        print("警告: RAW REPLの確認ができませんでしたが続行します")

    print(f"書き込み中: {local} → {remote}")
    ok = upload_file(ser, local, remote)
    ser.close()

    if ok:
        print("完了！USBを抜き差しするか、リセットしてください。")
    else:
        print("失敗。BOOTSELボタンを使ってください。")
