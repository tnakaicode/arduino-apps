import serial


def get_pico_status():
    """
    Raspberry Pi PicoがCOM4に接続されている場合の全Pin状態取得用関数。
    シリアルから1行受信し、全Pinの状態をパースして表示します。
    Pico側で全Pinの状態をカンマ区切りやJSON等でprintしている必要があります。
    """
    try:
        ser = serial.Serial("COM4", 115200, timeout=2)
        print("[Pico] Waiting for data on COM4...")
        line = ser.readline().decode("utf-8").strip()
        print(f"[Pico] Raw Received: {line}")
        # 例: "D0:1,D1:0,D2:1,A0:512,A1:256" のような形式を想定
        pin_states = {}
        for item in line.split(","):
            if ":" in item:
                k, v = item.split(":", 1)
                pin_states[k.strip()] = v.strip()
        print("[Pico] Pin States:")
        for pin, val in pin_states.items():
            print(f"  {pin}: {val}")
        ser.close()
        return pin_states
    except Exception as e:
        print(f"[Pico] Error: {e}")
        return None


if __name__ == "__main__":
    states = get_pico_status()
    if states:
        print(states["D0"])  # D0ピンの値を取得
