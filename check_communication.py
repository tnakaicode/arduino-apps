import serial
import time

COM_PORT = "COM9"
# 主要なボーレートを順に試す
BAUD_RATES = [9600, 115200, 57600, 38400]

for baud in BAUD_RATES:
    print(f"--- 接続テスト中: {COM_PORT} ({baud} bps) ---")
    try:
        # ポートを開く（タイムアウト2秒）
        ser = serial.Serial(COM_PORT, baud, timeout=2.0)
        time.sleep(2)  # 接続後の機器安定待ち

        # 受信バッファをクリア
        ser.reset_input_buffer()

        # 1. 標準的な識別コマンドを送ってみる
        print("-> 送信: *IDN?\\n")
        ser.write(b"*IDN?\n")

        # 2. 応答を読み込む
        response = ser.readline()

        if response:
            print(f"<- 受信(Raw): {response}")
            try:
                print(f"<- 受信(Text): {response.decode('utf-8').strip()}")
            except UnicodeDecodeError:
                print(f"<- 受信(Hex): {response.hex().upper()}")

            ser.close()
            break
        else:
            print(".. 応答がありません（タイムアウト）")

        ser.close()

    except Exception as e:
        print(f"エラーが発生しました: {e}")
