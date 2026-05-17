/**
 * pv_database.c - PV データベース実装
 */

#include "pv_database.h"
#include <string.h>
#include <stdio.h>
#include "hardware/adc.h"
#include "pico/time.h"

#define MAX_PV_COUNT 8

static pv_entry_t      s_db[MAX_PV_COUNT];
static int             s_count = 0;
static SemaphoreHandle_t s_mutex = NULL;

/* ---- 内部ヘルパー ---- */
static void add_pv(const char *name, uint16_t type, uint16_t count, bool writable)
{
    if (s_count >= MAX_PV_COUNT) return;
    pv_entry_t *e = &s_db[s_count++];
    strncpy(e->name, name, MAX_PV_NAME - 1);
    e->name[MAX_PV_NAME - 1] = '\0';
    e->dbr_type   = type;
    e->dbr_count  = count;
    e->writable   = writable;
    memset(&e->value, 0, sizeof(e->value));
}

/* ---- 公開 API ---- */

void pvdb_init(void)
{
    s_mutex = xSemaphoreCreateMutex();
    configASSERT(s_mutex != NULL);

    s_count = 0;

    /* PV 登録 (インデックス順に注意) */
    add_pv("PICO:LED",    DBR_ENUM,  1, true);   /* idx 0 */
    add_pv("PICO:UPTIME", DBR_LONG,  1, false);  /* idx 1 */
    add_pv("PICO:TEMP",   DBR_FLOAT, 1, false);  /* idx 2 */

    /* RP2350 内部温度センサ ADC 初期化 */
    adc_init();
    adc_set_temp_sensor_enabled(true);
}

int pvdb_find(const char *name)
{
    for (int i = 0; i < s_count; i++) {
        if (strcmp(s_db[i].name, name) == 0) return i;
    }
    return -1;
}

bool pvdb_get(int idx, pv_value_t *out, uint16_t *type, uint16_t *count)
{
    if (idx < 0 || idx >= s_count) return false;

    xSemaphoreTake(s_mutex, portMAX_DELAY);

    /* PICO:UPTIME: 呼び出し時に更新 */
    if (idx == 1) {
        s_db[1].value.lval =
            (int32_t)(to_ms_since_boot(get_absolute_time()) / 1000);
    }

    /* PICO:TEMP: RP2350 内部温度センサを読む */
    if (idx == 2) {
        adc_select_input(4);                       /* ch4 = 内部温度センサ */
        uint16_t raw = adc_read();
        float voltage = (float)raw * 3.3f / 4096.0f;
        s_db[2].value.fval = 27.0f - (voltage - 0.706f) / 0.001721f;
    }

    *out   = s_db[idx].value;
    *type  = s_db[idx].dbr_type;
    *count = s_db[idx].dbr_count;

    xSemaphoreGive(s_mutex);
    return true;
}

bool pvdb_put(int idx, const pv_value_t *val)
{
    if (idx < 0 || idx >= s_count) return false;
    if (!s_db[idx].writable)       return false;

    xSemaphoreTake(s_mutex, portMAX_DELAY);
    s_db[idx].value = *val;
    xSemaphoreGive(s_mutex);
    return true;
}

const pv_entry_t *pvdb_entry(int idx)
{
    if (idx < 0 || idx >= s_count) return NULL;
    return &s_db[idx];
}

int pvdb_count(void)         { return s_count; }
SemaphoreHandle_t pvdb_mutex(void) { return s_mutex; }
