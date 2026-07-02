import serial
import time

COM_PORT = 'COM9'
BAUD_RATE = 115200  # JDSシリーズの標準速度

print(f"--- JDS-2900 デバイス詳細取得テスト ({BAUD_RATE} bps) ---")

try:
    # ポートを開く
    ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=2.0)
    time.sleep(1.5)  # 接続後の安定待ち
    
    ser.reset_input_buffer()
    
    # JDSシリーズの「機器情報読み出し」コマンド
    # 末尾にキャリッジリターン(\r)とラインフィード(\n)が必要です
    cmd = b":r00=0.\r\n"
    
    print(f"-> 送信コマンド: {cmd}")
    ser.write(cmd)
    
    # 応答の読み込み
    response = ser.readline()
    
    if response:
        print(f"<- 受信(Raw): {response}")
        try:
            print(f"<- 受信(Text): {response.decode('utf-8').strip()}")
        except UnicodeDecodeError:
            print(f"<- 受信(Hex): {response.hex().upper()}")
    else:
        print(".. 応答がありません（タイムアウト）。本体のボーレート設定が115200になっているか確認してください。")
        
    ser.close()

except Exception as e:
    print(f"エラー: {e}")