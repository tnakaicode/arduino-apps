#include <stdio.h>

#include "pico/stdlib.h"

#include "FreeRTOS.h"
#include "task.h"

static void alive_task(void *params) {
    (void)params;
    while (1) {
        puts("FREERTOS_USB_ALIVE");
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

int main(void) {
    stdio_init_all();
    sleep_ms(1500);
    puts("FREERTOS_USB_BOOT");

    if (xTaskCreate(alive_task, "ALIVE", 512, NULL, 1, NULL) != pdPASS) {
        puts("ERR: xTaskCreate failed");
        while (1) {
            sleep_ms(1000);
        }
    }

    vTaskStartScheduler();

    while (1) {
        tight_loop_contents();
    }
}
