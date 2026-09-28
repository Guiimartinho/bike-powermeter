/**
 * @file main.c
 * @brief Boot of the bike power meter (docs/04)
 *
 * main() prepares what the services share (task watchdog, settings) and
 * starts the service threads in the order of docs/04: power first, then
 * sample, motion, compute, radio and the USB serial. Then it tells the
 * system machine that the boot is over and returns; the services run on
 * their own.
 */

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#include "app/app_services.h"
#include "app/app_svc.h"
#include "app/pm_store.h"
#include "app_types.h"

LOG_MODULE_REGISTER(main, CONFIG_LOG_DEFAULT_LEVEL);

int main(void)
{
    LOG_INF("%s %s", APP_NAME, APP_VERSION_STR);

    /* a watchdog that survived a soft reset keeps counting */
    app_wdt_feed_if_running();

    pm_store_init();

    app_wdt_feed_if_running();
    app_wdt_init();

    power_svc_start();
    sample_svc_start();
    motion_svc_start();
    compute_svc_start();
    radio_svc_start();
#if defined(CONFIG_USB_DEVICE_STACK_NEXT)
    usb_svc_start();
#else
    serial_svc_start();
#endif

    power_svc_ready();
    LOG_INF("services started");
    return 0;
}
