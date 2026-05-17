cmake_minimum_required(VERSION 3.13)

# ★ set(PICO_BOARD ...) は pico_sdk_init() より前に宣言しなければなりません
#    後ろに置くと CYW43 (Wi-Fi) 関連ライブラリが含まれなくなります
set(PICO_BOARD pico2_w)

# Pico SDK の初期化
include($ENV{PICO_SDK_PATH}/pico_sdk_init.cmake)

# FreeRTOS-Kernel のインポート
# 環境変数 FREERTOS_KERNEL_PATH に FreeRTOS-Kernel リポジトリのルートを設定してください
# 例: set(ENV{FREERTOS_KERNEL_PATH} "C:/FreeRTOS-Kernel")
# RP2350 (Cortex-M33 Non-Secure) 用ポートを使用します
include($ENV{FREERTOS_KERNEL_PATH}/portable/ThirdParty/GCC/RP2350_ARM_NTZ/FreeRTOS_Kernel_import.cmake)

project(pico2w_epics_ioc C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

add_executable(pico2w_epics_ioc
    main.c
    epics_ca.c
    pv_database.c
)

# 必要なライブラリのリンク
target_link_libraries(pico2w_epics_ioc
    pico_stdlib
    pico_cyw43_arch_lwip_sys_freertos  # FreeRTOS 上で動く lwIP (Wi-Fi) スタック
    FreeRTOS-Kernel                    # FreeRTOS カーネル本体
    FreeRTOS-Kernel-Heap4              # ヒープアロケータ (Heap4 = 分割・結合対応)
    hardware_gpio
    hardware_adc                       # 内部温度センサ読み取り用
)

# インクルードパスの設定（FreeRTOSConfig.h, lwipopts.h などをここから読む）
target_include_directories(pico2w_epics_ioc PRIVATE ${CMAKE_CURRENT_LIST_DIR})

pico_enable_stdio_usb(pico2w_epics_ioc 1)
pico_add_extra_outputs(pico2w_epics_ioc)
