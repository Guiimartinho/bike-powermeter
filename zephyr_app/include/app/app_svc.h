/**
 * @file app_svc.h
 * @brief Threads of the services, their watchdog channels and inboxes
 *
 * docs/04, Serviços: one thread per service, each with its own 4 s channel
 * on the task watchdog. A service sleeps on its inbox, a k_msgq that zbus
 * listeners fill with copies of the messages it needs, so no event is lost
 * and no buffer is allocated after boot. The wait has a timeout below the
 * watchdog limit, which also gives each service its periodic work.
 *
 * Priorities: a lower number wins. The sample service is above everything
 * because a lost bridge sample shifts the integral of the revolution.
 */

#ifndef APP_SVC_H
#define APP_SVC_H

#include <zephyr/kernel.h>

/* Priorities (docs/04, Serviços) */
#define APP_PRIO_SAMPLE     4
#define APP_PRIO_MOTION     5
#define APP_PRIO_COMPUTE    5
#define APP_PRIO_RADIO      6
#define APP_PRIO_USB        8
#define APP_PRIO_POWER      9

/** Task watchdog timeout of every thread */
#define APP_WDT_TIMEOUT_MS  4000U

/** Longest wait of a service before it feeds its watchdog channel again */
#define APP_SVC_TICK_MS     1000U

/**
 * @brief Give the calling thread its task watchdog channel
 * @param name Thread name, printed when the channel expires
 * @return Channel id, or a negative error code (the thread runs unwatched)
 */
int app_wdt_add(const char *name);

/**
 * @brief Feed a channel from app_wdt_add(); a negative id does nothing
 */
void app_wdt_feed(int channel);

/**
 * @brief Start the task watchdog over the hardware watchdog (alias watchdog0)
 *
 * Call once from main() before the services start.
 */
void app_wdt_init(void);

/**
 * @brief Feed the nRF WDT if it survived a soft reset
 *
 * Only pin, power-on, brownout and watchdog resets stop the nRF WDT: after
 * sys_reboot() it keeps counting, and the boot feeds it until the services
 * add their channels.
 */
void app_wdt_feed_if_running(void);

/**
 * @brief Wait for the next message of a service inbox
 *
 * Feeds the watchdog channel before waiting.
 *
 * @param q Inbox
 * @param msg Buffer of the inbox item size
 * @param wdt_channel Watchdog channel of the calling thread
 * @param timeout_ms Longest wait, capped to APP_SVC_TICK_MS
 * @return 0 with a message, -EAGAIN on timeout
 */
int app_inbox_get(struct k_msgq *q, void *msg, int wdt_channel, uint32_t timeout_ms);

/**
 * @brief Put a message in an inbox from a zbus listener
 *
 * Never waits: a full inbox drops the message and counts the drop.
 */
void app_inbox_put(struct k_msgq *q, const void *msg, const char *svc);

#endif /* APP_SVC_H */
