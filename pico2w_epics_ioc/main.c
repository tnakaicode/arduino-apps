/**
 * main.c - Pico 2W C firmware (EPICS + HTTP + GPIO/ADC)
 *
 * このファームは以下を同時に提供する:
 *  - EPICS CA (UDP/TCP 5064)
 *  - Web API (/set, /stop, /status)
 *  - GP15 周波数出力
 *  - GP26(ADC0) 電圧監視
 */

#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdbool.h>

#ifndef SAFE_COM_BRINGUP
#define SAFE_COM_BRINGUP 0
#endif

#ifndef EPICS_MINIMAL_MODE
#define EPICS_MINIMAL_MODE 1
#endif

#include "pico/stdlib.h"
#if !SAFE_COM_BRINGUP
#include "pico/cyw43_arch.h"

#include "lwip/netif.h"
#include "lwip/ip4_addr.h"
#define LWIP_PROVIDE_ERRNO 1
#include "lwip/sockets.h"
#undef poll
#endif

#include "FreeRTOS.h"
#include "task.h"

#if !SAFE_COM_BRINGUP
#include "epics_ca.h"
#include "pv_database.h"
#include "wifi_config.h"
#endif

#define GP15_PIN 15
#define HTTP_PORT 80
#define NETWORK_DEFER_MS 5000

#define GPIO_TASK_STACK_WORDS   768
#define NETMGR_TASK_STACK_WORDS 4096
#define HTTP_TASK_STACK_WORDS   3072
#define CA_TASK_STACK_WORDS     3072
#define NETBOOT_TASK_STACK_WORDS 768
#define HEARTBEAT_TASK_STACK_WORDS 512

/* 固定IP要件: 192.168.3.100 */
#define STATIC_IP   "192.168.3.100"
#define STATIC_MASK "255.255.255.0"
#define STATIC_GW   "192.168.3.1"

static volatile bool g_network_ready = false;
static volatile bool g_cyw43_ready = false;
static volatile bool g_network_tasks_started = false;

typedef struct {
    const char *name;
    uint32_t auth;
} wifi_auth_try_t;

#if !SAFE_COM_BRINGUP
static const char *k_html_response =
    "HTTP/1.0 200 OK\r\n"
    "Content-Type: text/html\r\n\r\n"
    "<!doctype html><html><head><meta charset='utf-8'>"
    "<meta name='viewport' content='width=device-width,initial-scale=1'>"
    "<title>Pico2W C Controller</title></head><body>"
    "<h3>Pico2W C Controller</h3>"
    "<p>API: /set?freq=10.0, /stop, /status</p>"
    "</body></html>";

static bool wait_for_netif_ready(uint32_t timeout_ms)
{
    const TickType_t deadline = xTaskGetTickCount() + pdMS_TO_TICKS(timeout_ms);

    while (xTaskGetTickCount() < deadline) {
        if (netif_default && netif_is_up(netif_default) && netif_is_link_up(netif_default)) {
            return true;
        }
        vTaskDelay(pdMS_TO_TICKS(100));
    }
    return false;
}

static bool set_static_ip(void)
{
    ip4_addr_t ip, mask, gw;

    if (!ip4addr_aton(STATIC_IP, &ip)) return false;
    if (!ip4addr_aton(STATIC_MASK, &mask)) return false;
    if (!ip4addr_aton(STATIC_GW, &gw)) return false;
    if (!netif_default) return false;

    netif_set_addr(netif_default, &ip, &mask, &gw);
    return true;
}

static bool connect_wifi_with_fallback(void)
{
#if EPICS_MINIMAL_MODE
    static const wifi_auth_try_t k_auth_tries[] = {
        {"WPA2_AES_PSK", CYW43_AUTH_WPA2_AES_PSK},
    };
#else
    static const wifi_auth_try_t k_auth_tries[] = {
        {"WPA2_AES_PSK", CYW43_AUTH_WPA2_AES_PSK},
        {"WPA2_MIXED_PSK", CYW43_AUTH_WPA2_MIXED_PSK},
        {"WPA_TKIP_PSK", CYW43_AUTH_WPA_TKIP_PSK},
    };
#endif

    for (size_t i = 0; i < sizeof(k_auth_tries) / sizeof(k_auth_tries[0]); ++i) {
        int rc;

        printf("[INFO] Wi-Fi auth try: %s\n", k_auth_tries[i].name);
        rc = cyw43_arch_wifi_connect_timeout_ms(
            WIFI_SSID,
            WIFI_PASSWORD,
            k_auth_tries[i].auth,
            4000);
        if (rc == 0) {
            return true;
        }

        printf("[WARN] Wi-Fi auth %s failed rc=%d\n", k_auth_tries[i].name, rc);
    }

    return false;
}

static float query_freq_set(void)
{
    pv_value_t v;
    uint16_t t, c;
    if (!pvdb_get(PV_IDX_FREQ_SET, &v, &t, &c)) return 0.0f;
    return v.fval;
}

static int query_run(void)
{
    pv_value_t v;
    uint16_t t, c;
    if (!pvdb_get(PV_IDX_RUN, &v, &t, &c)) return 0;
    return (v.en != 0);
}

static int query_led(void)
{
    pv_value_t v;
    uint16_t t, c;
    if (!pvdb_get(PV_IDX_LED, &v, &t, &c)) return 0;
    return (v.en != 0);
}

static void set_freq_and_run(float freq_hz, int run)
{
    pv_value_t v = {0};

    if (freq_hz < 0.1f) freq_hz = 0.1f;
    if (freq_hz > 10000.0f) freq_hz = 10000.0f;

    v.fval = freq_hz;
    pvdb_put(PV_IDX_FREQ_SET, &v);

    memset(&v, 0, sizeof(v));
    v.en = run ? 1 : 0;
    pvdb_put(PV_IDX_RUN, &v);
}

static void stop_output(void)
{
    pv_value_t v = {0};
    v.fval = 0.0f;
    pvdb_put(PV_IDX_FREQ_SET, &v);
    memset(&v, 0, sizeof(v));
    v.en = 0;
    pvdb_put(PV_IDX_RUN, &v);
}

static void gpio_control_task(void *params)
{
    (void)params;

    gpio_init(GP15_PIN);
    gpio_set_dir(GP15_PIN, GPIO_OUT);
    gpio_put(GP15_PIN, 0);

    bool state = false;
    uint64_t next_toggle_us = time_us_64();

    while (1) {
        float freq = query_freq_set();
        int run = query_run();

        if (g_cyw43_ready) {
            cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, query_led());
        }

        if (run && freq > 0.0f) {
            uint32_t half_period_us = (uint32_t)(500000.0f / freq);
            if (half_period_us < 100) half_period_us = 100;

            uint64_t now = time_us_64();
            if (now >= next_toggle_us) {
                state = !state;
                gpio_put(GP15_PIN, state);
                next_toggle_us = now + half_period_us;
            }
        } else {
            state = false;
            gpio_put(GP15_PIN, 0);
            next_toggle_us = time_us_64() + 1000;
        }

        pv_value_t pin_val = {0};
        pin_val.en = gpio_get(GP15_PIN) ? 1 : 0;
        pvdb_update(PV_IDX_PIN, &pin_val);

        vTaskDelay(pdMS_TO_TICKS(1));
    }
}

static void send_text(int fd, const char *s)
{
    if (!s) return;
    send(fd, s, (int)strlen(s), 0);
}

static float parse_freq(const char *path)
{
    const char *p = strstr(path, "freq=");
    if (!p) return 1.0f;
    return (float)atof(p + 5);
}

static void http_server_task(void *params)
{
    (void)params;

    int server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd < 0) {
        printf("[ERR] HTTP socket create failed\n");
        vTaskDelete(NULL);
    }

    int opt = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in addr = {0};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(HTTP_PORT);
    addr.sin_addr.s_addr = htonl(INADDR_ANY);

    if (bind(server_fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        printf("[ERR] HTTP bind failed\n");
        close(server_fd);
        vTaskDelete(NULL);
    }

    if (listen(server_fd, 2) < 0) {
        printf("[ERR] HTTP listen failed\n");
        close(server_fd);
        vTaskDelete(NULL);
    }

    printf("[INFO] HTTP server ready: http://%s\n", STATIC_IP);

    char req[512];
    while (1) {
        int cfd = accept(server_fd, NULL, NULL);
        if (cfd < 0) {
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        }

        int n = recv(cfd, req, sizeof(req) - 1, 0);
        if (n <= 0) {
            close(cfd);
            continue;
        }
        req[n] = '\0';

        char method[8] = {0};
        char path[200] = {0};
        sscanf(req, "%7s %199s", method, path);

        if (strcmp(path, "/") == 0 || strncmp(path, "/?", 2) == 0) {
            send_text(cfd, k_html_response);
        } else if (strncmp(path, "/set", 4) == 0) {
            float hz = parse_freq(path);
            set_freq_and_run(hz, 1);
            char out[96];
            snprintf(out, sizeof(out),
                     "HTTP/1.0 200 OK\r\nContent-Type: text/plain\r\n\r\nOK FREQ:%.3f", hz);
            send_text(cfd, out);
        } else if (strcmp(path, "/stop") == 0) {
            stop_output();
            send_text(cfd, "HTTP/1.0 200 OK\r\nContent-Type: text/plain\r\n\r\nOK STOP");
        } else if (strcmp(path, "/status") == 0) {
            pv_value_t vf = {0}, vv = {0}, vp = {0};
            uint16_t t, c;
            pvdb_get(PV_IDX_FREQ_SET, &vf, &t, &c);
            pvdb_get(PV_IDX_VOLT, &vv, &t, &c);
            pvdb_get(PV_IDX_PIN, &vp, &t, &c);

            char body[160];
            snprintf(body, sizeof(body),
                     "{\"freq\":%.3f,\"volt\":%.3f,\"pin\":%d}",
                     vf.fval, vv.fval, (int)vp.en);

            char hdr[96];
            snprintf(hdr, sizeof(hdr),
                     "HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n");
            send_text(cfd, hdr);
            send_text(cfd, body);
        } else {
            send_text(cfd, "HTTP/1.0 404 Not Found\r\n\r\nNot Found");
        }

        close(cfd);
    }
}

static void network_manager_task(void *params)
{
    (void)params;

    while (1) {
        if (!g_cyw43_ready) {
            if (cyw43_arch_init()) {
                printf("[WARN] Wi-Fi init failed; retry in 1s\n");
                vTaskDelay(pdMS_TO_TICKS(1000));
                continue;
            }

            g_cyw43_ready = true;
            cyw43_arch_enable_sta_mode();
            printf("[INFO] Wi-Fi driver ready\n");
        }

        if (!g_network_ready) {
            printf("[INFO] Connecting Wi-Fi: %s\n", WIFI_SSID);
            if (!connect_wifi_with_fallback()) {
                printf("[WARN] Wi-Fi connect failed; retry in 1s\n");
                vTaskDelay(pdMS_TO_TICKS(1000));
                continue;
            }

            if (!wait_for_netif_ready(5000)) {
                printf("[WARN] netif not ready; retry in 1s\n");
                vTaskDelay(pdMS_TO_TICKS(1000));
                continue;
            }

            if (!set_static_ip()) {
                printf("[WARN] static IP apply failed; retry in 1s\n");
                vTaskDelay(pdMS_TO_TICKS(1000));
                continue;
            }

            g_network_ready = true;
            printf("[INFO] Connected. Fixed IP: %s\n", STATIC_IP);
        }

        if (!g_network_tasks_started) {
#if !EPICS_MINIMAL_MODE
            if (xTaskCreate(http_server_task, "HTTP", HTTP_TASK_STACK_WORDS, NULL, 2, NULL) != pdPASS) {
                printf("[ERR] xTaskCreate HTTP failed\n");
            }
#else
            printf("[INFO] EPICS minimal mode: HTTP disabled\n");
#endif
            if (xTaskCreate(ca_udp_task, "CA_UDP", CA_TASK_STACK_WORDS, NULL, configMAX_PRIORITIES - 1, NULL) != pdPASS) {
                printf("[ERR] xTaskCreate CA_UDP failed\n");
            }
            if (xTaskCreate(ca_tcp_listener_task, "CA_TCP", CA_TASK_STACK_WORDS, NULL, configMAX_PRIORITIES - 1, NULL) != pdPASS) {
                printf("[ERR] xTaskCreate CA_TCP failed\n");
            }

            g_network_tasks_started = true;
            printf("[INFO] Network tasks started\n");
        }

        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

static void delayed_network_boot_task(void *params)
{
    (void)params;

    printf("[INFO] Network boot deferred %d ms for USB stability\n", NETWORK_DEFER_MS);
    vTaskDelay(pdMS_TO_TICKS(NETWORK_DEFER_MS));

    if (xTaskCreate(network_manager_task, "NET_MGR", NETMGR_TASK_STACK_WORDS, NULL, 3, NULL) != pdPASS) {
        printf("[ERR] xTaskCreate NET_MGR failed\n");
    } else {
        printf("[INFO] NET_MGR task started\n");
    }

    vTaskDelete(NULL);
}
#endif

static void heartbeat_task(void *params)
{
    (void)params;

    while (1) {
        printf("[HB] alive, net=%d cyw43=%d\n", g_network_ready ? 1 : 0, g_cyw43_ready ? 1 : 0);
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

int main(void)
{
    stdio_init_all();
    setvbuf(stdout, NULL, _IONBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);

    printf("[INFO] Booting pico2w_epics_ioc...\n");
    printf("[INFO] Starting RTOS tasks...\n");

#if SAFE_COM_BRINGUP
    printf("[INFO] SAFE_COM_BRINGUP active (network disabled)\n");

    if (xTaskCreate(heartbeat_task, "HEARTBEAT", HEARTBEAT_TASK_STACK_WORDS, NULL, 1, NULL) != pdPASS) {
        printf("[ERR] xTaskCreate HEARTBEAT failed\n");
    }

    vTaskStartScheduler();

    while (1) {
        tight_loop_contents();
    }
    return 0;
#endif

#if !SAFE_COM_BRINGUP
    pvdb_init();
    printf("[INFO] PV database initialized (%d PVs)\n", pvdb_count());

#if !EPICS_MINIMAL_MODE
    if (xTaskCreate(gpio_control_task, "GPIO_CTRL", GPIO_TASK_STACK_WORDS, NULL, 2, NULL) != pdPASS) {
        printf("[ERR] xTaskCreate GPIO_CTRL failed\n");
    }
#else
    printf("[INFO] EPICS minimal mode: GPIO task disabled\n");
#endif
    if (xTaskCreate(heartbeat_task, "HEARTBEAT", HEARTBEAT_TASK_STACK_WORDS, NULL, 1, NULL) != pdPASS) {
        printf("[ERR] xTaskCreate HEARTBEAT failed\n");
    }
    if (xTaskCreate(delayed_network_boot_task, "NET_BOOT", NETBOOT_TASK_STACK_WORDS, NULL, 3, NULL) != pdPASS) {
        printf("[ERR] xTaskCreate NET_BOOT failed\n");
    }
#endif

    vTaskStartScheduler();

    while (1) {
        tight_loop_contents();
    }
    return 0;
}

