import time
import epics

# 対象のPV名
PV_NAME = "RE:ch0:MTR1:SETPOINT"

print(f"--- PV制御ループを開始します ({PV_NAME}) ---")
print("終了するには Ctrl + C を押してください。\n")

try:
    while True:
        # -500 を書き込み
        print(f"[{time.strftime('%X')}] caput {PV_NAME} -500")
        epics.caput(PV_NAME, -500)
        time.sleep(10)

        # +500 を書き込み
        print(f"[{time.strftime('%X')}] caput {PV_NAME} 500")
        epics.caput(PV_NAME, 500)
        time.sleep(10)

except KeyboardInterrupt:
    print("\nユーザーによってプログラムが停止されました。")
