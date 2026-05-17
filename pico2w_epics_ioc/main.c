#include <stdio.h>
#include "pico/stdlib.h"
#include "pico/cyw43_arch.h"
#include "FreeRTOS.h"
#include "task.h"
#include "lwip/sockets.h"

#define WIFI_SSID "あなたのWi-FiのSSID"
#define WIFI_PASSWORD "Wi-Fiのパスワード"
#define EPICS_PORT 5064

// EPICS IOCとしての通信処理を行うタスク
void epics_ioc_task(__unused void *params) {
    int server_fd;
    struct sockaddr_in server_addr, client_addr;
    char buffer[512];

    // UDPソケットの作成（EPICS Channel Accessのサーチは主にUDP 5064番）
    server_fd = socket(AF_INET, SOCK_DGRAM, 0);
    
    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = INADDR_ANY;
    server_addr.sin_port = htons(EPICS_PORT);

    bind(server_fd, (struct sockaddr *)&server_addr, sizeof(server_addr));
    printf("EPICS IOC Task: Listening on UDP port %d...\n", EPICS_PORT);

    while (1) {
        socklen_t client_len = sizeof(client_addr);
        // ホストPCのcagetなどからの検索要求（CA_PROTO_SEARCH）を待つ
        int len = recvfrom(server_fd, buffer, sizeof(buffer), 0, 
                           (struct sockaddr *)&client_addr, &client_len);
        
        if (len > 0) {
            // 💡 ここにEPICSプロトコルの解析と応答ロジックを実装します。
            // 受信パケットのヘッダを解析し、探しているPV名（例: "PICO:LED"）が
            // 一致した場合に「そのPVはここにあります」という応答（CA_PROTO_SEARCH_REPLY）を
            // `sendto` でホストPCに送り返します。
            printf("Received EPICS Search Packet! Size: %d\n", len);
        }
        vTaskDelay(pdMS_TO_TICKS(10)); // タスクを一時譲って他の処理（Wi-Fi維持など）に回す
    }
}

int main() {
    stdio_init_all();
    
    // Wi-Fiチップの初期化（FreeRTOSモード）
    if (cyw43_arch_init()) {
        printf("Wi-Fi Init Failed\n");
        return -1;
    }
    cyw43_arch_enable_sta_mode();

    printf("Connecting to Wi-Fi...\n");
    if (cyw43_arch_wifi_connect_timeout_ms(WIFI_SSID, WIFI_PASSWORD, CYW43_AUTH_WPA2_AES_PSK, 30000)) {
        printf("Connect Failed\n");
        return -1;
    }
    printf("Connected! IP: %s\n", ip4addr_ntoa(netif_ip4_addr(netif_default)));

    // FreeRTOSのタスクとしてEPICS IOCを生成
    xTaskCreate(epics_ioc_task, "EPICS_IOC_Task", 4096, NULL, configMAX_PRIORITIES - 1, NULL);

    // OS（スケジューラ）の起動（ここからマルチタスクが始まる）
    vTaskStartScheduler();

    while(1); // ここには到達しない
}
