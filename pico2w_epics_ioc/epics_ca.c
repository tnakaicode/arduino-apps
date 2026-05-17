/**
 * epics_ca.c - EPICS Channel Access プロトコル実装
 *
 * 動作概要:
 *  1. ca_udp_task  … UDP 5064 でブロードキャストの PV サーチを受信し
 *                    自分が持つ PV なら CA_PROTO_SEARCH 応答を返す。
 *  2. ca_tcp_listener_task … TCP 5064 でクライアント接続を待ち受け、
 *                    接続ごとに ca_tcp_client_task を生成する。
 *  3. ca_tcp_client_task … チャンネル作成・読み書き・サブスクライブを処理。
 */

#include "epics_ca.h"
#include "pv_database.h"

#include <string.h>
#include <stdio.h>

#include "FreeRTOS.h"
#include "task.h"
#include "lwip/sockets.h"
#include "lwip/inet.h"
#include "pico/cyw43_arch.h"

/* ============================================================
 * 内部定数
 * ============================================================ */
#define CA_PORT          5064
#define MAX_TCP_CLIENTS  4
#define TCP_BUF_SIZE     1024
#define MAX_CLIENT_CHANS 16   /* 1 TCP 接続あたりの最大チャンネル数 */

/* ============================================================
 * ユーティリティ
 * ============================================================ */

/** 指定バイト数を必ず受信するまでリトライする */
static int recv_all(int sock, void *buf, int len)
{
    uint8_t *ptr = (uint8_t *)buf;
    int remaining = len;
    while (remaining > 0) {
        int n = recv(sock, ptr, remaining, 0);
        if (n <= 0) return n;
        ptr      += n;
        remaining -= n;
    }
    return len;
}

/** ペイロードサイズを 8 バイト境界に切り上げる */
static uint16_t align8(uint16_t size)
{
    return (uint16_t)((size + 7u) & ~7u);
}

/**
 * PV 値をビッグエンディアンのバイト列にシリアライズする。
 * @return シリアライズしたバイト数 (失敗時 0)
 */
static int serialize_pv(int pv_idx, void *buf, uint16_t req_type, uint16_t req_count)
{
    pv_value_t val;
    uint16_t native_type, native_count;

    if (!pvdb_get(pv_idx, &val, &native_type, &native_count)) return 0;
    if (req_count == 0) req_count = native_count;

    switch (req_type) {
        case DBR_FLOAT: {
            float f = (native_type == DBR_LONG)  ? (float)val.lval
                    : (native_type == DBR_FLOAT) ? val.fval
                    : 0.0f;
            uint32_t tmp;
            memcpy(&tmp, &f, 4);
            tmp = htonl(tmp);              /* float もビッグエンディアンに変換 */
            memcpy(buf, &tmp, 4);
            return 4;
        }
        case DBR_ENUM: {
            uint16_t e = htons((uint16_t)val.en);
            memcpy(buf, &e, 2);
            return 2;
        }
        case DBR_LONG: {
            uint32_t l = htonl((uint32_t)val.lval);
            memcpy(buf, &l, 4);
            return 4;
        }
        case DBR_SHORT: {
            uint16_t s = htons((uint16_t)val.sh);
            memcpy(buf, &s, 2);
            return 2;
        }
        default:
            return 0;
    }
}

/* ============================================================
 * TCP クライアント処理タスク
 * ============================================================ */
static void ca_tcp_client_task(void *arg)
{
    int client_fd = (int)(uintptr_t)arg;

    /* chan_pv[cid] = pv_index  (クライアント指定 CID をキーに PV を管理) */
    int chan_pv[MAX_CLIENT_CHANS];
    memset(chan_pv, -1, sizeof(chan_pv));

    /* --- グリーティング: CA_PROTO_VERSION を送る --- */
    {
        ca_hdr_t greet = {0};
        greet.command    = htons(CA_PROTO_VERSION);
        greet.data_count = htons(CA_MINOR_PROTOCOL_REVISION);
        send(client_fd, &greet, sizeof(greet), 0);
    }

    uint8_t buf[TCP_BUF_SIZE];

    while (1) {
        /* --- ヘッダ受信 --- */
        if (recv_all(client_fd, buf, sizeof(ca_hdr_t)) <= 0) break;

        ca_hdr_t *req  = (ca_hdr_t *)buf;
        uint16_t cmd   = ntohs(req->command);
        uint16_t plen  = ntohs(req->payload_size);
        uint16_t dtype = ntohs(req->data_type);
        uint16_t dcnt  = ntohs(req->data_count);
        uint32_t p1    = ntohl(req->parameter1);
        uint32_t p2    = ntohl(req->parameter2);

        /* --- ペイロード受信 --- */
        if (plen > 0 && plen <= (uint16_t)(TCP_BUF_SIZE - sizeof(ca_hdr_t))) {
            if (recv_all(client_fd, buf + sizeof(ca_hdr_t), plen) <= 0) break;
        }

        switch (cmd) {

        /* ---- バージョン交換 (無視) ---- */
        case CA_PROTO_VERSION:
            break;

        /* ---- チャンネル作成 ---- */
        case CA_PROTO_CREATE_CHAN: {
            uint32_t cid = p1;
            char *pvname = (char *)(buf + sizeof(ca_hdr_t));
            if (plen < (uint16_t)(TCP_BUF_SIZE - sizeof(ca_hdr_t)))
                pvname[plen] = '\0';

            int pv_idx = pvdb_find(pvname);
            ca_hdr_t rsp = {0};

            if (pv_idx < 0) {
                /* PV が見つからない */
                rsp.command    = htons(CA_PROTO_CREATE_CHAN_FAIL);
                rsp.parameter1 = htonl(cid);
                send(client_fd, &rsp, sizeof(rsp), 0);
                printf("CA TCP: PV '%s' not found\n", pvname);
                break;
            }

            /* CID → PV インデックスを登録 */
            if (cid < MAX_CLIENT_CHANS) chan_pv[cid] = pv_idx;

            const pv_entry_t *pv = pvdb_entry(pv_idx);

            /* アクセス権通知 */
            rsp.command    = htons(CA_PROTO_ACCESS_RIGHTS);
            rsp.parameter1 = htonl(cid);
            rsp.parameter2 = htonl(pv->writable ? 3u : 1u); /* 1=R / 3=R+W */
            send(client_fd, &rsp, sizeof(rsp), 0);

            /* チャンネル作成成功 */
            memset(&rsp, 0, sizeof(rsp));
            rsp.command    = htons(CA_PROTO_CREATE_CHAN);
            rsp.data_type  = htons(pv->dbr_type);
            rsp.data_count = htons(pv->dbr_count);
            rsp.parameter1 = htonl(cid); /* SID = CID (簡略化) */
            rsp.parameter2 = htonl(cid); /* CID そのまま返す */
            send(client_fd, &rsp, sizeof(rsp), 0);

            printf("CA TCP: Channel '%s' created (cid=%u)\n", pvname, (unsigned)cid);
            break;
        }

        /* ---- 読み取り (caget) ---- */
        case CA_PROTO_READ_NOTIFY: {
            uint32_t sid  = p1;
            uint32_t ioid = p2;
            int pv_idx = (sid < MAX_CLIENT_CHANS) ? chan_pv[sid] : -1;

            uint8_t data[64] = {0};
            uint16_t data_sz = 0;

            if (pv_idx >= 0) {
                data_sz = (uint16_t)serialize_pv(pv_idx, data, dtype,
                                                 (dcnt > 0) ? dcnt : 1u);
            }

            uint16_t payload_sz = align8(data_sz);
            ca_hdr_t rsp = {0};
            rsp.command      = htons(CA_PROTO_READ_NOTIFY);
            rsp.payload_size = htons(payload_sz);
            rsp.data_type    = htons(dtype);
            rsp.data_count   = htons((dcnt > 0) ? dcnt : 1u);
            rsp.parameter1   = htonl(1u);   /* ECA_NORMAL */
            rsp.parameter2   = htonl(ioid);

            uint8_t out[sizeof(ca_hdr_t) + 64] = {0};
            memcpy(out, &rsp, sizeof(ca_hdr_t));
            memcpy(out + sizeof(ca_hdr_t), data, data_sz);
            send(client_fd, out, sizeof(ca_hdr_t) + payload_sz, 0);
            break;
        }

        /* ---- サブスクライブ (camonitor) ---- */
        case CA_PROTO_EVENT_ADD: {
            uint32_t sid   = p1;
            uint32_t subid = p2;
            int pv_idx = (sid < MAX_CLIENT_CHANS) ? chan_pv[sid] : -1;

            uint8_t data[64] = {0};
            uint16_t data_sz = 0;

            if (pv_idx >= 0) {
                data_sz = (uint16_t)serialize_pv(pv_idx, data, dtype,
                                                 (dcnt > 0) ? dcnt : 1u);
            }

            uint16_t payload_sz = align8(data_sz);
            ca_hdr_t rsp = {0};
            rsp.command      = htons(CA_PROTO_EVENT_ADD);
            rsp.payload_size = htons(payload_sz);
            rsp.data_type    = htons(dtype);
            rsp.data_count   = htons((dcnt > 0) ? dcnt : 1u);
            rsp.parameter1   = htonl(1u);   /* ECA_NORMAL */
            rsp.parameter2   = htonl(subid);

            uint8_t out[sizeof(ca_hdr_t) + 64] = {0};
            memcpy(out, &rsp, sizeof(ca_hdr_t));
            memcpy(out + sizeof(ca_hdr_t), data, data_sz);
            send(client_fd, out, sizeof(ca_hdr_t) + payload_sz, 0);

            /* 注意: 定期的な更新送信は未実装。
             *       実装するには subscription リストを管理し、
             *       値変化検知タスクから各クライアントへ通知する必要がある。 */
            break;
        }

        /* ---- 書き込み (caput, 確認なし) ---- */
        case CA_PROTO_WRITE: {
            uint32_t sid = p1;
            int pv_idx = (sid < MAX_CLIENT_CHANS) ? chan_pv[sid] : -1;
            if (pv_idx < 0) break;

            void *payload = buf + sizeof(ca_hdr_t);
            pv_value_t new_val = {0};

            /* ビッグエンディアン → ネイティブ変換してから格納 */
            switch (dtype) {
                case DBR_ENUM: {
                    uint16_t v; memcpy(&v, payload, 2);
                    new_val.en = (int16_t)ntohs(v);
                    break;
                }
                case DBR_LONG: {
                    uint32_t v; memcpy(&v, payload, 4);
                    new_val.lval = (int32_t)ntohl(v);
                    break;
                }
                case DBR_FLOAT: {
                    uint32_t v; memcpy(&v, payload, 4);
                    v = ntohl(v);
                    memcpy(&new_val.fval, &v, 4);
                    break;
                }
                default: break;
            }

            pvdb_put(pv_idx, &new_val);

            /* PICO:LED (idx 0) の場合はオンボード LED に反映 */
            if (pv_idx == 0) {
                cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, new_val.en != 0);
                printf("CA TCP: PICO:LED = %d\n", (int)new_val.en);
            }
            break;
        }

        /* ---- 書き込み確認付き (caput -c) ---- */
        case CA_PROTO_WRITE_NOTIFY: {
            /* 書き込みを実行してから CA_PROTO_WRITE_NOTIFY で応答 */
            uint32_t sid  = p1;
            uint32_t ioid = p2;
            int pv_idx = (sid < MAX_CLIENT_CHANS) ? chan_pv[sid] : -1;

            if (pv_idx >= 0) {
                void *payload = buf + sizeof(ca_hdr_t);
                pv_value_t new_val = {0};
                switch (dtype) {
                    case DBR_ENUM: {
                        uint16_t v; memcpy(&v, payload, 2);
                        new_val.en = (int16_t)ntohs(v);
                        break;
                    }
                    case DBR_LONG: {
                        uint32_t v; memcpy(&v, payload, 4);
                        new_val.lval = (int32_t)ntohl(v);
                        break;
                    }
                    case DBR_FLOAT: {
                        uint32_t v; memcpy(&v, payload, 4);
                        v = ntohl(v);
                        memcpy(&new_val.fval, &v, 4);
                        break;
                    }
                    default: break;
                }
                pvdb_put(pv_idx, &new_val);
                if (pv_idx == 0) {
                    cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, new_val.en != 0);
                }
            }

            ca_hdr_t rsp = {0};
            rsp.command    = htons(CA_PROTO_WRITE_NOTIFY);
            rsp.data_type  = htons(dtype);
            rsp.data_count = htons((dcnt > 0) ? dcnt : 1u);
            rsp.parameter1 = htonl(1u);   /* ECA_NORMAL */
            rsp.parameter2 = htonl(ioid);
            send(client_fd, &rsp, sizeof(rsp), 0);
            break;
        }

        default:
            printf("CA TCP: Unknown command %u (ignored)\n", (unsigned)cmd);
            break;
        }
    }

    printf("CA TCP: Client disconnected\n");
    close(client_fd);
    vTaskDelete(NULL);
}

/* ============================================================
 * TCP リスナータスク
 * ============================================================ */
void ca_tcp_listener_task(void *params)
{
    (void)params;

    int server_fd = socket(AF_INET, SOCK_STREAM, 0);
    configASSERT(server_fd >= 0);

    int opt = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in addr = {0};
    addr.sin_family      = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port        = htons(CA_PORT);
    bind(server_fd, (struct sockaddr *)&addr, sizeof(addr));
    listen(server_fd, MAX_TCP_CLIENTS);

    printf("EPICS CA TCP: Listening on port %d\n", CA_PORT);

    while (1) {
        struct sockaddr_in cli_addr;
        socklen_t cli_len = sizeof(cli_addr);
        int client_fd = accept(server_fd, (struct sockaddr *)&cli_addr, &cli_len);
        if (client_fd < 0) {
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        }

        printf("CA TCP: New client from %s\n", inet_ntoa(cli_addr.sin_addr));

        /* クライアントごとにタスクを生成 (スタック 3 KB) */
        BaseType_t ret = xTaskCreate(ca_tcp_client_task, "CA_Client",
                                     768,   /* words (= 3072 bytes) */
                                     (void *)(uintptr_t)client_fd,
                                     configMAX_PRIORITIES - 2, NULL);
        if (ret != pdPASS) {
            printf("CA TCP: Failed to create client task\n");
            close(client_fd);
        }
    }
}

/* ============================================================
 * UDP サーチリスナータスク
 * ============================================================ */
void ca_udp_task(void *params)
{
    (void)params;

    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    configASSERT(sock >= 0);

    int bcast = 1;
    setsockopt(sock, SOL_SOCKET, SO_BROADCAST, &bcast, sizeof(bcast));

    struct sockaddr_in addr = {0};
    addr.sin_family      = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port        = htons(CA_PORT);
    bind(sock, (struct sockaddr *)&addr, sizeof(addr));

    printf("EPICS CA UDP: Listening on port %d\n", CA_PORT);

    uint8_t buf[512];

    while (1) {
        struct sockaddr_in cli_addr;
        socklen_t cli_len = sizeof(cli_addr);
        int n = recvfrom(sock, buf, sizeof(buf) - 1, 0,
                         (struct sockaddr *)&cli_addr, &cli_len);

        if (n < (int)sizeof(ca_hdr_t)) {
            vTaskDelay(pdMS_TO_TICKS(5));
            continue;
        }

        ca_hdr_t *hdr  = (ca_hdr_t *)buf;
        uint16_t cmd   = ntohs(hdr->command);
        uint16_t plen  = ntohs(hdr->payload_size);
        uint16_t dtype = ntohs(hdr->data_type);
        uint32_t p2    = ntohl(hdr->parameter2); /* search_id (CID) */

        /* CA_PROTO_SEARCH のみ処理 */
        if (cmd != CA_PROTO_SEARCH) continue;
        /* dtype == 0xFFFF は "返信不要" フラグ (ルータ中継パケットなど) */
        if (dtype == 0xFFFF) continue;

        /* PV 名はヘッダ直後のペイロード */
        if ((int)(sizeof(ca_hdr_t) + plen) > n) continue;
        char *pvname = (char *)(buf + sizeof(ca_hdr_t));
        pvname[plen] = '\0';  /* 念のためヌル終端を保証 */

        int pv_idx = pvdb_find(pvname);
        if (pv_idx < 0) continue; /* このIOCが持たない PV */

        printf("CA UDP: Search '%s' -> found! Reply to %s\n",
               pvname, inet_ntoa(cli_addr.sin_addr));

        /* ---- CA_PROTO_SEARCH 応答を構築 ---- */
        /*
         * ヘッダ (16 B) + ペイロード (8 B):
         *   [0-3]  server IPv4 (0xFFFFFFFF = use socket address)
         *   [4-5]  reserved = 0
         *   [6-7]  CA minor protocol version
         */
        struct {
            ca_hdr_t hdr;
            uint32_t server_ip;
            uint16_t reserved;
            uint16_t minor_ver;
        } __attribute__((packed)) reply = {0};

        reply.hdr.command      = htons(CA_PROTO_SEARCH);
        reply.hdr.payload_size = htons(8);
        reply.hdr.data_type    = htons(CA_PORT);      /* TCP ポート番号 */
        reply.hdr.data_count   = htons(0xFFFF);       /* 応答マーカー */
        reply.hdr.parameter1   = htonl(0xFFFFFFFF);   /* use my IP */
        reply.hdr.parameter2   = htonl(p2);           /* 検索 ID をそのまま返す */
        reply.server_ip        = htonl(0xFFFFFFFF);
        reply.minor_ver        = htons(CA_MINOR_PROTOCOL_REVISION);

        sendto(sock, &reply, sizeof(reply), 0,
               (struct sockaddr *)&cli_addr, cli_len);
    }
}
