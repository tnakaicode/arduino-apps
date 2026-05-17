cmake_minimum_required(VERSION 3.13)

# ★ set(PICO_BOARD ...) は pico_sdk_init() より前に宣言しなければなりません
#    後ろに置くと CYW43 (Wi-Fi) 関連ライブラリが含まれなくなります
set(PICO_BOARD pico2_w)

# Force USB CDC stdio on this project, regardless of prior CMake cache values.
set(PICO_STDIO_USB ON CACHE BOOL "Enable USB stdio" FORCE)
set(PICO_STDIO_UART OFF CACHE BOOL "Disable UART stdio" FORCE)

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

find_package(Python3 REQUIRED COMPONENTS Interpreter)

pico_sdk_init()

add_executable(pico2w_epics_ioc
    main.c
    epics_ca.c
    pv_database.c
)

add_executable(pico2w_usb_diag
    usb_diag_main.c
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

target_link_libraries(pico2w_usb_diag
    pico_stdlib
)

# インクルードパスの設定（FreeRTOSConfig.h, lwipopts.h などをここから読む）
target_include_directories(pico2w_epics_ioc PRIVATE ${CMAKE_CURRENT_LIST_DIR})
target_include_directories(pico2w_usb_diag PRIVATE ${CMAKE_CURRENT_LIST_DIR})

pico_enable_stdio_usb(pico2w_epics_ioc 1)
pico_enable_stdio_usb(pico2w_usb_diag 1)
pico_enable_stdio_uart(pico2w_usb_diag 0)

# NOTE:
# picotool uf2 conversion can crash on some Windows environments.
# Generate HEX/BIN/UF2 via objcopy + local converter script instead.
add_custom_command(TARGET pico2w_epics_ioc POST_BUILD
    COMMAND ${CMAKE_OBJCOPY} -Oihex $<TARGET_FILE:pico2w_epics_ioc> ${CMAKE_CURRENT_BINARY_DIR}/pico2w_epics_ioc.hex
    COMMAND ${CMAKE_OBJCOPY} -Obinary $<TARGET_FILE:pico2w_epics_ioc> ${CMAKE_CURRENT_BINARY_DIR}/pico2w_epics_ioc.bin
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_LIST_DIR}/tools/bin_to_uf2.py
            ${CMAKE_CURRENT_BINARY_DIR}/pico2w_epics_ioc.bin
            ${CMAKE_CURRENT_BINARY_DIR}/pico2w_epics_ioc.uf2
    COMMENT "Generating HEX/BIN/UF2 artifacts without picotool"
)

add_custom_command(TARGET pico2w_usb_diag POST_BUILD
    COMMAND ${CMAKE_OBJCOPY} -Oihex $<TARGET_FILE:pico2w_usb_diag> ${CMAKE_CURRENT_BINARY_DIR}/pico2w_usb_diag.hex
    COMMAND ${CMAKE_OBJCOPY} -Obinary $<TARGET_FILE:pico2w_usb_diag> ${CMAKE_CURRENT_BINARY_DIR}/pico2w_usb_diag.bin
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_LIST_DIR}/tools/bin_to_uf2.py
            ${CMAKE_CURRENT_BINARY_DIR}/pico2w_usb_diag.bin
            ${CMAKE_CURRENT_BINARY_DIR}/pico2w_usb_diag.uf2
    COMMENT "Generating USB diagnostic HEX/BIN/UF2 artifacts"
)
