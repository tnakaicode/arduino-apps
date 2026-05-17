#ifndef FREERTOS_CONFIG_H
#define FREERTOS_CONFIG_H

#include <stdint.h>

/* ============================================================
 * 基本スケジューラ設定
 * ============================================================ */
#define configUSE_PREEMPTION                    1
#define configUSE_PORT_OPTIMISED_TASK_SELECTION 0
#define configUSE_TICKLESS_IDLE                 0
#define configCPU_CLOCK_HZ                      150000000UL  /* Pico 2 (RP2350) は 150 MHz */
#define configTICK_RATE_HZ                      1000
#define configMAX_PRIORITIES                    8
#define configMINIMAL_STACK_SIZE                256          /* 最低スタック (words): lwIP は 128 では不足 */
#define configTOTAL_HEAP_SIZE                   (256 * 1024) /* 520 KB RAM のうち 256 KB を OS に割り当て */
#define configMAX_TASK_NAME_LEN                 16
#define configUSE_16_BIT_TICKS                  0
#define configIDLE_SHOULD_YIELD                 1

/* ============================================================
 * メモリ管理
 * ============================================================ */
#define configSUPPORT_DYNAMIC_ALLOCATION        1
#define configSUPPORT_STATIC_ALLOCATION         0

/* ============================================================
 * タスク間通信・同期機構
 * ============================================================ */
#define configUSE_MUTEXES                       1
#define configUSE_RECURSIVE_MUTEXES             1
#define configUSE_COUNTING_SEMAPHORES           1
#define configUSE_TASK_NOTIFICATIONS            1
#define configTASK_NOTIFICATION_ARRAY_ENTRIES   3
#define configQUEUE_REGISTRY_SIZE               8

/* ============================================================
 * ソフトウェアタイマー (lwIP の内部タイマーが使用)
 * ============================================================ */
#define configUSE_TIMERS                        1
#define configTIMER_TASK_PRIORITY               (configMAX_PRIORITIES - 1)
#define configTIMER_QUEUE_LENGTH                16
#define configTIMER_TASK_STACK_DEPTH            512

/* ============================================================
 * フック関数 (使用しない場合は 0)
 * ============================================================ */
#define configUSE_IDLE_HOOK                     0
#define configUSE_TICK_HOOK                     0
#define configUSE_MALLOC_FAILED_HOOK            0
#define configUSE_DAEMON_TASK_STARTUP_HOOK      0
#define configCHECK_FOR_STACK_OVERFLOW          0

/* ============================================================
 * デバッグ・統計
 * ============================================================ */
#define configGENERATE_RUN_TIME_STATS           0
#define configUSE_TRACE_FACILITY                0
#define configUSE_STATS_FORMATTING_FUNCTIONS    0

/* ============================================================
 * Cortex-M33 (RP2350) 割り込み優先度設定
 * RP2350 は NVIC 4 ビット優先度 (0〜15) を使用
 * ============================================================ */
#define configPRIO_BITS                         4
#define configLIBRARY_LOWEST_INTERRUPT_PRIORITY          0xF
#define configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY     5
#define configKERNEL_INTERRUPT_PRIORITY \
    (configLIBRARY_LOWEST_INTERRUPT_PRIORITY << (8 - configPRIO_BITS))
#define configMAX_SYSCALL_INTERRUPT_PRIORITY \
    (configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY << (8 - configPRIO_BITS))

/* ============================================================
 * INCLUDE マクロ (API の有効化)
 * ============================================================ */
#define INCLUDE_vTaskPrioritySet                1
#define INCLUDE_uxTaskPriorityGet               1
#define INCLUDE_vTaskDelete                     1
#define INCLUDE_vTaskSuspend                    1
#define INCLUDE_xResumeFromISR                  1
#define INCLUDE_vTaskDelayUntil                 1
#define INCLUDE_vTaskDelay                      1
#define INCLUDE_xTaskGetSchedulerState          1
#define INCLUDE_xTaskGetCurrentTaskHandle       1
#define INCLUDE_uxTaskGetStackHighWaterMark     0
#define INCLUDE_xTaskGetIdleTaskHandle          0
#define INCLUDE_eTaskGetState                   0

#define INCLUDE_xSemaphoreGetMutexHolder        1
#define INCLUDE_xTimerPendFunctionCall          1

/* ============================================================
 * アサート
 * ============================================================ */

// Cortex-M33 (RP2350) FPU/MPU/TrustZone defines (required by portmacrocommon.h)
#define configENABLE_FPU        1
#define configENABLE_MPU        0
#define configENABLE_TRUSTZONE  0

#define configASSERT(x) \
    do { if ((x) == 0) { portDISABLE_INTERRUPTS(); for (;;); } } while (0)

#endif /* FREERTOS_CONFIG_H */
