cmake_minimum_required(VERSION 3.13)

# Pico SDKの初期化（インストール時の環境変数を利用）
include($ENV{PICO_SDK_PATH}/pico_sdk_init.cmake)

project(pico2w_epics_ioc C CXX ASM)
pico_sdk_init()

add_executable(pico2w_epics_ioc main.c)

# Pico 2 W (RP2350) ＆ Wi-Fiを有効化
set(PICO_BOARD pico2_w)

# 必要なライブラリのリンク (FreeRTOSとlwIP)
target_link_libraries(pico2w_epics_ioc 
    pico_stdlib
    pico_cyw43_arch_lwip_sys_freertos # FreeRTOS上で動くlwIP(Wi-Fi)スタック
    hardware_gpio
)

# 各種設定ファイルのパスを通す
target_include_directories(pico2w_epics_ioc PRIVATE ${CMAKE_CURRENT_LIST_DIR})

pico_enable_stdio_usb(pico2w_epics_ioc 1)
pico_add_extra_outputs(pico2w_epics_ioc)
