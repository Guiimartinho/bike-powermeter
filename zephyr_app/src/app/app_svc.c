/**
 * @file app_svc.c
 * @brief Watchdog channels and inboxes of the service threads
 */

#include <errno.h>

#include <zephyr/device.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/logging/log_ctrl.h>
#include <zephyr/sys/reboot.h>
#include <zephyr/task_wdt/task_wdt.h>

#include "app/app_svc.h"

LOG_MODULE_REGISTER(app_svc, CONFIG_LOG_DEFAULT_LEVEL);

/*
 * The hardware watchdog behind the task watchdog: watchdog0 of the board
 * (wdt31 on the nRF54LM20). DT_REG_ADDR gives the address the CPU sees.
 */
#if defined(CONFIG_SOC_FAMILY_NORDIC_NRF) && DT_NODE_HAS_STATUS(DT_ALIAS(watchdog0), okay)
#include <hal/nrf_wdt.h>
#define HW_WDT_REGS ((NRF_WDT_Type *)DT_REG_ADDR(DT_ALIAS(watchdog0)))
#endif

/** Messages dropped by full inboxes, for the log */
static atomic_t inbox_drops;

void app_wdt_feed_if_running(void)
{
#if defined(HW_WDT_REGS)
    if (nrf_wdt_started_check(HW_WDT_REGS)) {
        for (uint32_t rr = 0U; rr < NRF_WDT_CHANNEL_NUMBER; rr++) {
            if (nrf_wdt_reload_request_enable_check(HW_WDT_REGS, (nrf_wdt_rr_register_t)rr)) {
                nrf_wdt_reload_request_set(HW_WDT_REGS, (nrf_wdt_rr_register_t)rr);
            }
        }
    }
#endif
}

/**
 * Task watchdog expiry: a thread stopped feeding its channel. Runs in the
 * system timer interrupt: flush the log so the name reaches the console,
 * then reboot.
 */
static void wdt_expired(int channel_id, void *user_data)
{
    LOG_ERR("Task watchdog: %s stalled (channel %d), rebooting", (const char *)user_data,
            channel_id);
    LOG_PANIC();
    sys_reboot(SYS_REBOOT_COLD);
}

void app_wdt_init(void)
{
    const struct device *hw_wdt = DEVICE_DT_GET_OR_NULL(DT_ALIAS(watchdog0));

    if ((hw_wdt != NULL) && !device_is_ready(hw_wdt)) {
        hw_wdt = NULL;
    }
    if (task_wdt_init(hw_wdt) != 0) {
        LOG_ERR("Task watchdog init failed");
    }
    if (hw_wdt == NULL) {
        LOG_WRN("No hardware watchdog behind the task watchdog");
    }
}

int app_wdt_add(const char *name)
{
    int channel = task_wdt_add(APP_WDT_TIMEOUT_MS, wdt_expired, (void *)name);

    if (channel < 0) {
        LOG_ERR("Task watchdog channel for %s failed: %d", name, channel);
    }
    return channel;
}

void app_wdt_feed(int channel)
{
    if (channel >= 0) {
        (void)task_wdt_feed(channel);
    }
}

int app_inbox_get(struct k_msgq *q, void *msg, int wdt_channel, uint32_t timeout_ms)
{
    uint32_t wait = (timeout_ms < APP_SVC_TICK_MS) ? timeout_ms : APP_SVC_TICK_MS;

    app_wdt_feed(wdt_channel);
    if (k_msgq_get(q, msg, K_MSEC(wait)) != 0) {
        return -EAGAIN;
    }
    return 0;
}

void app_inbox_put(struct k_msgq *q, const void *msg, const char *svc)
{
    if (k_msgq_put(q, msg, K_NO_WAIT) != 0) {
        atomic_val_t n = atomic_inc(&inbox_drops);

        /* one line for the first drop and then every 100, not a flood */
        if ((n % 100) == 0) {
            LOG_WRN("inbox of %s full: %ld messages dropped", svc, (long)(n + 1));
        }
    }
}
