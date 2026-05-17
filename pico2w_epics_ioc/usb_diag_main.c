#include <stdio.h>
#include "pico/stdlib.h"

int main(void) {
    stdio_init_all();
    sleep_ms(1200);

    while (true) {
        puts("USB_DIAG_ALIVE");
        sleep_ms(1000);
    }
}
