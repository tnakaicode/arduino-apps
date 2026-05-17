/**
 * main.c - Pico 2W EPICS IOC エントリポイント
 *
 * 起動シーケンス:
 *   1. Wi-Fi 接続 (CYW43 + FreeRTOS 統合モード)
 *   2. PV データベース初期化
 *   3. FreeRTOS タスク生成
 *      - LED 点滅タスク (動作確認用)
 *      - EPICS CA UDP タスク (PV サーチ応答, ポート 5064)
 *      - EPICS CA TCP タスク (チャンネル読み書き, ポート 5064)
 *   4. FreeRTOS スケジューラ起動
 *
 * 対応 PV:
 *   PICO:LED    … DBR_ENUM  0=消灯 / 1=点灯  (caput で制御)
 *   PICO:UPTIME … DBR_LONG  起動後経過秒数   (caget / camonitor)
 *   PICO:TEMP   … DBR_FLOAT RP2350 内部温度  (caget / camonitor)
 *
 * 必要環境変数 (CMake ビルド前に設定):
 *   PICO_SDK_PATH       … pico-sdk のルートパス
 *   FREERTOS_KERNEL_PATH… FreeRTOS-Kernel のルートパス
 */

#include <stdio.h>
#include <string.h>

#include "pico/stdlib.h"
#include "pico/cyw43_arch.h"
#include "lwip/netif.h"

#include "FreeRTOS.h"
#include "task.h"

#include "epics_ca.h"
#include "pv_database.h"
#include "wifi_config.h"   /* WIFI_SSID / WIFI_PASSWORD */

/* ============================================================
 * LED 点滅タスク (Wi-Fi 接続後の動作確認)
 * ============================================================ */
static void led_blink_task(void *params)
{
    (void)params;
    bool led = false;
    while (1) {
        led = !led;
        cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, led);
        vTaskDelay(pdMS_TO_TICKS(500));
    }
}

/* ============================================================
 * エントリポイント
 * ============================================================ */
int main(void)
{
    stdio_init_all();

    /* Wi-Fi チップの初期化 (FreeRTOS 統合モード) */
    if (cyw43_arch_init()) {
        printf("[ERR] Wi-Fi init failed\n");
        return -1;
    }
    cyw43_arch_enable_sta_mode();

    printf("[INFO] Connecting to Wi-Fi: %s\n", WIFI_SSID);
    if (cyw43_arch_wifi_connect_timeout_ms(
            WIFI_SSID, WIFI_PASSWORD,
            CYW43_AUTH_WPA2_AES_PSK, 30000)) {
        printf("[ERR] Wi-Fi connect failed\n");
        return -1;
    }
    printf("[INFO] Connected! IP: %s\n",
           ip4addr_ntoa(netif_ip4_addr(netif_default)));

    /* PV データベース初期化 */
    pvdb_init();
    printf("[INFO] PV database initialized (%d PVs)\n", pvdb_count());

    /* FreeRTOS タスク生成 */
    xTaskCreate(led_blink_task,       "LED",        256,  NULL,
                1, NULL);
    xTaskCreate(ca_udp_task,          "CA_UDP",     512,  NULL,
                configMAX_PRIORITIES - 1, NULL);
    xTaskCreate(ca_tcp_listener_task, "CA_TCP",     512,  NULL,
                configMAX_PRIORITIES - 1, NULL);

    /* FreeRTOS スケジューラ起動 (ここから先には戻らない) */
    vTaskStartScheduler();

    /* 到達しない */
    while (1);
    return 0;
}

