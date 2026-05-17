/**
 * pv_database.h - EPICS PV (Process Variable) データベース
 *
 * このモジュールはマイコン上に「PVのレジスタ」を持ちます。
 * - PICO:LED    … DBR_ENUM  (0=消灯 / 1=点灯) 書き込み可能
 * - PICO:UPTIME … DBR_LONG  (起動後の経過秒数)  読み取り専用
 * - PICO:TEMP   … DBR_FLOAT (RP2350 内部温度 [℃]) 読み取り専用
 */

#ifndef PV_DATABASE_H
#define PV_DATABASE_H

#include <stdint.h>
#include <stdbool.h>
#include "FreeRTOS.h"
#include "semphr.h"

/* ============================================================
 * DBR 型番号 (Channel Access プロトコルと同じ値)
 * ============================================================ */
#define DBR_STRING   0
#define DBR_SHORT    1
#define DBR_FLOAT    2
#define DBR_ENUM     3
#define DBR_CHAR     4
#define DBR_LONG     5
#define DBR_DOUBLE   6

/* ============================================================
 * PV 値を保持する union (ネイティブエンディアン)
 * ============================================================ */
typedef union {
    char    str[40];   /* DBR_STRING */
    int16_t sh;        /* DBR_SHORT  */
    float   fval;      /* DBR_FLOAT  */
    int16_t en;        /* DBR_ENUM   */
    int8_t  ch;        /* DBR_CHAR   */
    int32_t lval;      /* DBR_LONG   */
    double  dval;      /* DBR_DOUBLE */
} pv_value_t;

/* ============================================================
 * PV エントリ構造体
 * ============================================================ */
#define MAX_PV_NAME 64

typedef struct {
    char      name[MAX_PV_NAME];
    uint16_t  dbr_type;   /* このPVのネイティブ型 */
    uint16_t  dbr_count;  /* 要素数 (通常 1) */
    pv_value_t value;     /* 現在値 (ネイティブエンディアン) */
    bool      writable;
} pv_entry_t;

/* PV index constants (pvdb_init の登録順と一致させること) */
enum {
    PV_IDX_LED = 0,
    PV_IDX_UPTIME,
    PV_IDX_TEMP,
    PV_IDX_FREQ_SET,
    PV_IDX_RUN,
    PV_IDX_PIN,
    PV_IDX_VOLT,
};

/* ============================================================
 * API
 * ============================================================ */

/** PV データベースを初期化する (起動時に一度だけ呼ぶ) */
void pvdb_init(void);

/** PV 名でエントリを検索。見つかればインデックス、なければ -1 */
int pvdb_find(const char *name);

/**
 * PV の現在値を取得する。
 * PICO:UPTIME / PICO:TEMP は呼び出し時に自動更新される。
 * @param idx     pvdb_find() が返したインデックス
 * @param out     取得した値をコピーする先 (ネイティブエンディアン)
 * @param type    PV のネイティブ DBR 型
 * @param count   PV の要素数
 * @return        成功なら true
 */
bool pvdb_get(int idx, pv_value_t *out, uint16_t *type, uint16_t *count);

/**
 * PV の値を書き込む (ネイティブエンディアンで渡す)。
 * writable = false の PV への書き込みは無視される。
 */
bool pvdb_put(int idx, const pv_value_t *val);

/** 内部更新用 API (writable 属性を無視して値を更新する) */
bool pvdb_update(int idx, const pv_value_t *val);

/** エントリへの const ポインタを返す (読み取り専用参照) */
const pv_entry_t *pvdb_entry(int idx);

/** 登録されている PV 数を返す */
int pvdb_count(void);

/** データベース全体を保護する mutex (直接ロックが必要な場合) */
SemaphoreHandle_t pvdb_mutex(void);

#endif /* PV_DATABASE_H */
