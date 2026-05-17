/**
 * epics_ca.h - EPICS Channel Access プロトコル定義
 *
 * 実装している CA コマンド:
 *   UDP: CA_PROTO_SEARCH (PV 検索への応答)
 *   TCP: VERSION / CREATE_CHAN / READ_NOTIFY / EVENT_ADD / WRITE
 */

#ifndef EPICS_CA_H
#define EPICS_CA_H

#include <stdint.h>

/* ============================================================
 * CA コマンド番号
 * ============================================================ */
#define CA_PROTO_VERSION        0   /* バージョン交換 */
#define CA_PROTO_EVENT_ADD      1   /* サブスクライブ (camonitor) */
#define CA_PROTO_EVENT_CANCEL   2   /* サブスクライブ解除 */
#define CA_PROTO_WRITE          4   /* 書き込み (確認なし) */
#define CA_PROTO_SEARCH         6   /* PV 検索 (UDP) */
#define CA_PROTO_NOT_FOUND      14  /* PV 不在応答 */
#define CA_PROTO_READ_NOTIFY    15  /* 読み取り (caget) */
#define CA_PROTO_CREATE_CHAN    18  /* チャンネル作成 (TCP 接続後) */
#define CA_PROTO_WRITE_NOTIFY  19  /* 書き込み (確認あり) */
#define CA_PROTO_ACCESS_RIGHTS  22  /* アクセス権通知 */
#define CA_PROTO_CREATE_CHAN_FAIL 26 /* チャンネル作成失敗 */
#define CA_PROTO_SERVER_DISCONN  27 /* サーバ側切断通知 */

/* CA プロトコルマイナーバージョン */
#define CA_MINOR_PROTOCOL_REVISION  13

/* ============================================================
 * CA ヘッダー構造体 (16 バイト固定, ビッグエンディアン)
 * ============================================================ */
typedef struct {
    uint16_t command;       /* CA コマンド番号 */
    uint16_t payload_size;  /* ペイロードサイズ [バイト] */
    uint16_t data_type;     /* DBR 型 or ポート番号 */
    uint16_t data_count;    /* 要素数 */
    uint32_t parameter1;    /* 第1パラメータ (SID / CID / ステータス等) */
    uint32_t parameter2;    /* 第2パラメータ (IOID / subid / CID 等) */
} __attribute__((packed)) ca_hdr_t;

/* ============================================================
 * FreeRTOS タスクのエントリポイント
 * ============================================================ */

/** UDP ポート 5064: PV サーチ要求に応答するタスク */
void ca_udp_task(void *params);

/** TCP ポート 5064: クライアント接続を受け付けるリスナータスク */
void ca_tcp_listener_task(void *params);

#endif /* EPICS_CA_H */
