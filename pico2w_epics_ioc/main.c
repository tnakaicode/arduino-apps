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

#include "pico/stdlib.h"
#include "pico/cyw43_arch.h"

#include "lwip/netif.h"
#include "lwip/ip4_addr.h"
#define LWIP_PROVIDE_ERRNO 1
#include "lwip/sockets.h"
#undef poll

#include "FreeRTOS.h"
#include "task.h"

#include "epics_ca.h"
#include "pv_database.h"
#include "wifi_config.h"

#define GP15_PIN 15
#define HTTP_PORT 80

/* 固定IP要件: 192.168.3.100 */
#define STATIC_IP   "192.168.3.100"
#define STATIC_MASK "255.255.255.0"
#define STATIC_GW   "192.168.3.1"
#define STATIC_DNS  "192.168.3.1"

static const char *k_html_response =
    "HTTP/1.0 200 OK\r\n"
    "Content-Type: text/html\r\n\r\n"
    "<!doctype html><html><head><meta charset='utf-8'>"
    "<meta name='viewport' content='width=device-width,initial-scale=1'>"
    "<title>Pico2W C Controller</title></head><body>"
    "<h3>Pico2W C Controller</h3>"
    "<p>API: /set?freq=10.0, /stop, /status</p>"
    "</body></html>";

static void set_static_ip(void)
{
    ip4_addr_t ip, mask, gw;

    if (!ip4addr_aton(STATIC_IP, &ip)) return;
    if (!ip4addr_aton(STATIC_MASK, &mask)) return;
    if (!ip4addr_aton(STATIC_GW, &gw)) return;
    netif_set_addr(netif_default, &ip, &mask, &gw);
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

        cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, query_led());

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
    configASSERT(server_fd >= 0);

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

int main(void)
{
    stdio_init_all();

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

    set_static_ip();
    printf("[INFO] Connected. Fixed IP: %s\n", STATIC_IP);

    pvdb_init();
    printf("[INFO] PV database initialized (%d PVs)\n", pvdb_count());

    xTaskCreate(gpio_control_task,   "GPIO_CTRL",  512, NULL, 2, NULL);
    xTaskCreate(http_server_task,    "HTTP",      1024, NULL, 2, NULL);
    xTaskCreate(ca_udp_task,         "CA_UDP",     768, NULL, configMAX_PRIORITIES - 1, NULL);
    xTaskCreate(ca_tcp_listener_task,"CA_TCP",     768, NULL, configMAX_PRIORITIES - 1, NULL);

    vTaskStartScheduler();

    while (1) {}
    return 0;
}

