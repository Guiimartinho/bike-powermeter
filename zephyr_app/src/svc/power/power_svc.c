/**
 * @file power_svc.c
 * @brief Power service: the system machine, the battery, the ways out
 *
 * docs/04 (Serviços, power). The thread runs the machine of
 * model/pm_fsm.c on the events of its inbox (the crank moving or still,
 * the cable, the commands, the update) and its timers, and publishes the
 * state on chan_system_state; every service applies its own actions to
 * the state. Every 10 s it reads the MAX17048 of the alias fuel-gauge0 by
 * the Zephyr fuel gauge API and the CHG and ERR pins of the nPM1100
 * (aliases charger-status and charger-error) and publishes chan_battery.
 *
 * $SLEEP puts the SoC in System OFF with the accelerometer's INT1 as the
 * wake source (the motion service armed its wake-up interrupt on the Sleep
 * state); $SHIP raises SHPACT of the nPM1100 (alias ship-activate) for
 * 300 ms with the cable out, which cuts the battery until the cable comes
 * (docs/02, Pinos do módulo).
 */

#include <string.h>

#include <zephyr/device.h>
#include <zephyr/drivers/fuel_gauge.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/logging/log_ctrl.h>
#include <zephyr/sys/poweroff.h>
#include <zephyr/zbus/zbus.h>

#include "app/app_channels.h"
#include "app/app_services.h"
#include "app/app_svc.h"
#include "model/pm_fsm.h"

LOG_MODULE_REGISTER(power_svc, CONFIG_LOG_DEFAULT_LEVEL);

/*
 * Measured with CONFIG_STACK_USAGE (2026-09-27): power_thread 112 B, the
 * fuel gauge read over I2C, the publish chain and the LOG_PANIC flush of
 * the power-off (about 0,75 KB): about 1,5 KB
 */
#define POWER_STACK_SIZE    3072
#define POWER_INBOX_LEN     16

#define GAUGE_PERIOD_MS     10000U
#define CRITICAL_SOC_PCT    2U
/** SHPACT must be high for at least 200 ms (nPM1100 PS v1.5, tactiveToShip) */
#define SHIP_PULSE_MS       300U
/** The services see the Sleep state before the SoC goes off */
#define SLEEP_SETTLE_MS     300U

#define GAUGE_NODE  DT_ALIAS(fuel_gauge0)
#define CHG_NODE    DT_ALIAS(charger_status)
#define ERR_NODE    DT_ALIAS(charger_error)
#define SHIP_NODE   DT_ALIAS(ship_activate)

#if DT_NODE_HAS_STATUS_OKAY(GAUGE_NODE)
static const struct device *const gauge = DEVICE_DT_GET(GAUGE_NODE);
#else
static const struct device *const gauge = NULL;
#endif
#if DT_NODE_HAS_STATUS_OKAY(CHG_NODE)
static const struct gpio_dt_spec chg = GPIO_DT_SPEC_GET(CHG_NODE, gpios);
#else
static const struct gpio_dt_spec chg = { .port = NULL };
#endif
#if DT_NODE_HAS_STATUS_OKAY(ERR_NODE)
static const struct gpio_dt_spec chg_err = GPIO_DT_SPEC_GET(ERR_NODE, gpios);
#else
static const struct gpio_dt_spec chg_err = { .port = NULL };
#endif
#if DT_NODE_HAS_STATUS_OKAY(SHIP_NODE)
static const struct gpio_dt_spec ship = GPIO_DT_SPEC_GET(SHIP_NODE, gpios);
#else
static const struct gpio_dt_spec ship = { .port = NULL };
#endif

struct power_msg {
    const struct zbus_channel *chan;
    union {
        struct app_motion_state motion;
        struct app_cmd_msg cmd;
        struct app_vbus vbus;
        struct app_dfu dfu;
    } u;
};

K_MSGQ_DEFINE(power_inbox, sizeof(struct power_msg), POWER_INBOX_LEN, 4);

static void power_listener(const struct zbus_channel *chan)
{
    struct power_msg msg = { .chan = chan };

    if (chan == &chan_cmd) {
        const struct app_cmd_msg *c = zbus_chan_const_msg(chan);

        if ((c->id != PM_CMD_SLEEP) && (c->id != PM_CMD_SHIP) && (c->id != PM_CMD_DFU) &&
            (c->id != PM_CMD_ZERO) && (c->id != PM_CMD_SLOPE_POINT) &&
            (c->id != PM_CMD_TEMP_POINT)) {
            return;
        }
    }
    if (zbus_chan_msg_size(chan) > sizeof(msg.u)) {
        return;
    }
    (void)memcpy(&msg.u, zbus_chan_const_msg(chan), zbus_chan_msg_size(chan));
    app_inbox_put(&power_inbox, &msg, "power");
}

ZBUS_LISTENER_DEFINE(power_lis, power_listener);
ZBUS_CHAN_ADD_OBS(chan_motion_state, power_lis, 3);
ZBUS_CHAN_ADD_OBS(chan_cmd, power_lis, 3);
ZBUS_CHAN_ADD_OBS(chan_vbus, power_lis, 3);
ZBUS_CHAN_ADD_OBS(chan_dfu, power_lis, 3);

static struct pm_fsm fsm;
static struct app_battery battery = { .soc_pct = 100U, .gauge = false };
static K_SEM_DEFINE(ready_sem, 0, 1);

static void publish_state(void)
{
    struct app_system_state s = { .state = (uint8_t)pm_fsm_state(&fsm) };

    LOG_INF("state %s", pm_fsm_state_name(pm_fsm_state(&fsm)));
    (void)app_publish(&chan_system_state, &s);
}

/** Feed the machine; publish when the state changed */
static pm_err_t event(enum pm_event ev)
{
    enum pm_sysstate before = pm_fsm_state(&fsm);
    pm_err_t err = pm_fsm_event(&fsm, ev, k_uptime_get_32());

    if (pm_fsm_state(&fsm) != before) {
        publish_state();
    }
    return err;
}

static void read_battery(void)
{
    union fuel_gauge_prop_val v;
    struct app_battery b = battery;

    b.gauge = false;
    if ((gauge != NULL) && device_is_ready(gauge)) {
        if (fuel_gauge_get_prop(gauge, FUEL_GAUGE_RELATIVE_STATE_OF_CHARGE, &v) == 0) {
            b.soc_pct = v.relative_state_of_charge;
            b.gauge = true;
        }
        if (fuel_gauge_get_prop(gauge, FUEL_GAUGE_VOLTAGE, &v) == 0) {
            b.mv = (uint16_t)(v.voltage / 1000);
        }
    }
    b.charging = (chg.port != NULL) && (gpio_pin_get_dt(&chg) == 1);
    b.fault = (chg_err.port != NULL) && (gpio_pin_get_dt(&chg_err) == 1);
    battery = b;
    (void)app_publish(&chan_battery, &b);

    pm_fsm_set_soc(&fsm, b.gauge ? b.soc_pct : 100U);
    if (b.charging || b.vbus) {
        (void)event(PM_EV_CHARGING);
    } else if (b.gauge && (b.soc_pct <= CRITICAL_SOC_PCT)) {
        (void)event(PM_EV_BATTERY_CRITICAL);
    } else {
        /* nothing to tell the machine */
    }
}

static void go_to_sleep(void)
{
    LOG_INF("System OFF; the crank wakes the pod");
    LOG_PANIC();
    k_msleep(SLEEP_SETTLE_MS);
    sys_poweroff();
}

static void go_to_ship(void)
{
    if (ship.port == NULL) {
        return;
    }
    LOG_INF("ship mode: SHPACT for %u ms", SHIP_PULSE_MS);
    LOG_PANIC();
    (void)gpio_pin_set_dt(&ship, 1);
    k_msleep(SHIP_PULSE_MS);
    (void)gpio_pin_set_dt(&ship, 0);
}

static void on_cmd(const struct app_cmd_msg *c)
{
    pm_err_t err;

    switch (c->id) {
    case PM_CMD_SLEEP:
        /* the answer goes first; the motion service arms the wake-up on the state */
        err = event(PM_EV_SLEEP_REQUEST);
        app_cmd_reply(c->id, c->source, (uint8_t)err, 0, NULL);
        if (err == PM_OK) {
            go_to_sleep();
        }
        break;
    case PM_CMD_SHIP:
        err = (battery.vbus || battery.charging || (ship.port == NULL)) ? PM_ESTATE : PM_OK;
        app_cmd_reply(c->id, c->source, (uint8_t)err, 0, NULL);
        if (err == PM_OK) {
            go_to_ship();
        }
        break;
    case PM_CMD_DFU:
        err = event(PM_EV_DFU_REQUEST);
        app_cmd_reply(c->id, c->source, (uint8_t)err, 0, NULL);
        break;
    case PM_CMD_ZERO:
    case PM_CMD_SLOPE_POINT:
    case PM_CMD_TEMP_POINT:
        /* the machine goes to Calibrating; the compute service answers */
        (void)event(PM_EV_CAL_REQUEST);
        break;
    default:
        break;
    }
}

static void power_thread(void *p1, void *p2, void *p3)
{
    struct power_msg msg;
    uint32_t next_gauge = k_uptime_get_32();
    uint32_t next_tick = k_uptime_get_32();

    ARG_UNUSED(p1);
    ARG_UNUSED(p2);
    ARG_UNUSED(p3);

    pm_fsm_init(&fsm, NULL, k_uptime_get_32());
    if (chg.port != NULL) {
        (void)gpio_pin_configure_dt(&chg, GPIO_INPUT);
    }
    if (chg_err.port != NULL) {
        (void)gpio_pin_configure_dt(&chg_err, GPIO_INPUT);
    }
    if (ship.port != NULL) {
        (void)gpio_pin_configure_dt(&ship, GPIO_OUTPUT_INACTIVE);
    }

    int wdt = app_wdt_add("power");

    /* main() says when every service started */
    while (k_sem_take(&ready_sem, K_MSEC(APP_SVC_TICK_MS)) != 0) {
        app_wdt_feed(wdt);
    }
    (void)event(PM_EV_READY);

    for (;;) {
        if (app_inbox_get(&power_inbox, &msg, wdt, APP_SVC_TICK_MS) == 0) {
            if (msg.chan == &chan_motion_state) {
                if (msg.u.motion.moving) {
                    if (pm_fsm_state(&fsm) == PM_ST_SLEEP) {
                        (void)event(PM_EV_WAKE);
                    }
                    (void)event(PM_EV_MOTION);
                } else {
                    (void)event(PM_EV_STILL);
                }
            } else if (msg.chan == &chan_cmd) {
                on_cmd(&msg.u.cmd);
            } else if (msg.chan == &chan_vbus) {
                battery.vbus = msg.u.vbus.present;
                read_battery();
            } else if (msg.chan == &chan_dfu) {
                if (msg.u.dfu.phase == APP_DFU_RECEIVING) {
                    (void)event(PM_EV_DFU_REQUEST);
                }
            } else {
                /* nothing else reaches this inbox */
            }
        }

        uint32_t now = k_uptime_get_32();

        if ((int32_t)(now - next_tick) >= 0) {
            enum pm_sysstate before = pm_fsm_state(&fsm);

            next_tick = now + APP_SVC_TICK_MS;
            pm_fsm_tick(&fsm, now);
            if (pm_fsm_state(&fsm) != before) {
                publish_state();
                if (pm_fsm_state(&fsm) == PM_ST_IDLE) {
                    /* a calibration that timed out: whoever waited is told by compute */
                }
            }
        }
        if ((int32_t)(now - next_gauge) >= 0) {
            next_gauge = now + GAUGE_PERIOD_MS;
            read_battery();
        }
    }
}

K_THREAD_DEFINE(power_tid, POWER_STACK_SIZE, power_thread, NULL, NULL, NULL, APP_PRIO_POWER, 0,
                SYS_FOREVER_MS);

void power_svc_start(void)
{
    k_thread_name_set(power_tid, "power");
    k_thread_start(power_tid);
}

void power_svc_ready(void)
{
    k_sem_give(&ready_sem);
}
