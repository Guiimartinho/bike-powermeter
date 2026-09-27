/**
 * @file sample_svc.c
 * @brief Sample service: the bridge, its excitation and its temperature
 *
 * docs/04 (Serviços, sample). The thread owns the ADS1220 of the alias
 * bridge-adc, the TPS22916 of the alias bridge-excitation and the TMP117
 * of the alias temp0. In Active and Calibrating it runs the converter in
 * continuous conversion at the configured rate: the DRDY interrupt only
 * drops a message in the inbox, the thread reads the code over SPI, filters
 * it (median of three, docs/06) and publishes chan_torque with the torque
 * of the calibration in force. In Idle it powers the converter down and
 * takes a short burst every CONFIG_PM_IDLE_BURST_PERIOD_MS, with the
 * reference monitor first, for the auto zero and the health rules. In the
 * other states everything is off.
 *
 * The excitation is on whenever the converter converts: the digital filter
 * of the ADS1220 integrates over the whole conversion (SBAS501D 8.3.6), so
 * there is no shorter window than the conversion itself.
 */

#include <string.h>

#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/zbus/zbus.h>

#include <drivers/adc/ads1220.h>

#include "app/app_channels.h"
#include "app/app_services.h"
#include "app/app_svc.h"
#include "app/pm_store.h"
#include "model/bridge_calc.h"
#include "model/pm_fsm.h"

LOG_MODULE_REGISTER(sample_svc, CONFIG_LOG_DEFAULT_LEVEL);

/*
 * Measured with CONFIG_STACK_USAGE (2026-09-27): sample_thread 184 B with
 * the burst inlined, the SPI read, the I2C fetch of the temperature and the
 * publish chain: about 0,9 KB
 */
#define SAMPLE_STACK_SIZE   2048
/* the DRDY messages of a few milliseconds plus the settings and the states */
#define SAMPLE_INBOX_LEN    32

/** The excitation settles in well under this (TPS22916 on, RC input filter) */
#define EXCITATION_SETTLE_MS    3U
/** Samples of an idle burst */
#define IDLE_BURST_SAMPLES      8U
/** The bridge temperature is read this often while active */
#define TEMP_PERIOD_MS          1000U

#define ADC_NODE    DT_ALIAS(bridge_adc)
#define EXC_NODE    DT_ALIAS(bridge_excitation)
#define TEMP_NODE   DT_ALIAS(temp0)

#if DT_NODE_HAS_STATUS_OKAY(ADC_NODE)
static const struct device *const adc = DEVICE_DT_GET(ADC_NODE);
#else
static const struct device *const adc = NULL;
#endif
#if DT_NODE_HAS_STATUS_OKAY(EXC_NODE)
static const struct gpio_dt_spec exc = GPIO_DT_SPEC_GET(EXC_NODE, gpios);
#else
static const struct gpio_dt_spec exc = { .port = NULL };
#endif
#if DT_NODE_HAS_STATUS_OKAY(TEMP_NODE)
static const struct device *const temp_dev = DEVICE_DT_GET(TEMP_NODE);
#else
static const struct device *const temp_dev = NULL;
#endif

enum sample_msg_kind {
    MSG_DRDY = 0,
    MSG_ZBUS
};

struct sample_msg {
    uint8_t kind;
    const struct zbus_channel *chan;
    union {
        struct app_system_state sys;
        struct app_settings_msg settings;
    } u;
};

K_MSGQ_DEFINE(sample_inbox, sizeof(struct sample_msg), SAMPLE_INBOX_LEN, 4);

static void sample_listener(const struct zbus_channel *chan)
{
    struct sample_msg msg = { .kind = MSG_ZBUS, .chan = chan };

    if (zbus_chan_msg_size(chan) > sizeof(msg.u)) {
        return;
    }
    (void)memcpy(&msg.u, zbus_chan_const_msg(chan), zbus_chan_msg_size(chan));
    app_inbox_put(&sample_inbox, &msg, "sample");
}

ZBUS_LISTENER_DEFINE(sample_lis, sample_listener);
ZBUS_CHAN_ADD_OBS(chan_system_state, sample_lis, 3);
ZBUS_CHAN_ADD_OBS(chan_settings, sample_lis, 3);

/** From the DRDY interrupt: a message, nothing else */
static void drdy_isr(const struct device *dev, void *user)
{
    struct sample_msg msg = { .kind = MSG_DRDY };

    ARG_UNUSED(dev);
    ARG_UNUSED(user);
    (void)k_msgq_put(&sample_inbox, &msg, K_NO_WAIT);
}

static struct bridge_cal cal;
static bool calibrated;
static struct bridge_filter filter;
static float temp_c = 25.0f;
static bool temp_valid;
static bool continuous;
static bool exc_on;

static void excitation(bool on)
{
    if (exc.port != NULL) {
        (void)gpio_pin_set_dt(&exc, on ? 1 : 0);
    }
    exc_on = on;
}

static void take_settings(const struct pm_settings *s)
{
    cal = s->cal;
    calibrated = bridge_cal_valid(&cal);
}

static void read_temperature(void)
{
    struct sensor_value v;
    struct app_temp t = { .uptime_ms = k_uptime_get_32() };

    if ((temp_dev != NULL) && (sensor_sample_fetch(temp_dev) == 0) &&
        (sensor_channel_get(temp_dev, SENSOR_CHAN_AMBIENT_TEMP, &v) == 0)) {
        temp_c = sensor_value_to_float(&v);
        temp_valid = true;
    } else {
        temp_valid = false;
    }
    t.temp_c = temp_c;
    t.valid = temp_valid;
    (void)app_publish(&chan_temp, &t);
}

static void read_monitor(void)
{
    struct app_excitation e = { .uptime_ms = k_uptime_get_32() };
    uint16_t mv = 0U;

    e.valid = (adc != NULL) && (ads1220_read_monitor(adc, ADS1220_MON_REF, &mv) == 0);
    e.ref_mv = mv;
    (void)app_publish(&chan_excitation, &e);
}

static void publish_code(int32_t code)
{
    int32_t filtered;
    struct app_torque t = {
        .uptime_ms = k_uptime_get_32(),
        .excitation_on = exc_on,
        .calibrated = calibrated,
    };

    if (!bridge_filter_median3(&filter, code, &filtered)) {
        return;
    }
    t.code = filtered;
    t.torque_mnm = calibrated ? bridge_torque_mnm(&cal, filtered, temp_c) : 0;
    (void)app_publish(&chan_torque, &t);
}

static void start_continuous(void)
{
    if ((adc == NULL) || continuous) {
        return;
    }
    excitation(true);
    k_msleep(EXCITATION_SETTLE_MS);
    read_monitor();
    bridge_filter_reset(&filter);
    (void)k_msgq_purge(&sample_inbox);
    if (ads1220_drdy_callback_set(adc, drdy_isr, NULL) != 0) {
        LOG_ERR("DRDY interrupt failed");
    }
    if (ads1220_start_continuous(adc) != 0) {
        LOG_ERR("converter did not start");
    }
    continuous = true;
    LOG_INF("bridge sampling at %u SPS", ads1220_data_rate(adc));
}

static void stop_all(void)
{
    if (adc != NULL) {
        (void)ads1220_drdy_callback_set(adc, NULL, NULL);
        (void)ads1220_powerdown(adc);
    }
    excitation(false);
    continuous = false;
}

/** A short burst of single conversions with the excitation on (Idle) */
static void idle_burst(void)
{
    if (adc == NULL) {
        return;
    }
    excitation(true);
    k_msleep(EXCITATION_SETTLE_MS);
    read_monitor();
    bridge_filter_reset(&filter);
    for (uint32_t i = 0U; i < IDLE_BURST_SAMPLES; i++) {
        int32_t code;
        uint32_t waited = 0U;

        if (ads1220_start_single(adc) != 0) {
            break;
        }
        /* one conversion at the configured rate: 6 ms at 175 SPS, 50 ms at 20 */
        while (!ads1220_data_ready(adc) && (waited < 100U)) {
            k_msleep(1);
            waited++;
        }
        if (!ads1220_data_ready(adc) || (ads1220_read(adc, &code) != 0)) {
            break;
        }
        publish_code(code);
    }
    (void)ads1220_powerdown(adc);
    excitation(false);
    read_temperature();
}

static void sample_thread(void *p1, void *p2, void *p3)
{
    struct sample_msg msg;
    struct pm_settings s;
    enum pm_sysstate state = PM_ST_BOOT;
    uint32_t next_temp = k_uptime_get_32();
    uint32_t next_burst = k_uptime_get_32();

    ARG_UNUSED(p1);
    ARG_UNUSED(p2);
    ARG_UNUSED(p3);

    pm_store_get(&s);
    take_settings(&s);
    bridge_filter_reset(&filter);
    if (exc.port != NULL) {
        (void)gpio_pin_configure_dt(&exc, GPIO_OUTPUT_INACTIVE);
    }
    if ((adc == NULL) || !device_is_ready(adc)) {
        LOG_ERR("no bridge converter");
    }
    if ((temp_dev != NULL) && !device_is_ready(temp_dev)) {
        LOG_WRN("temperature sensor not ready");
    }

    int wdt = app_wdt_add("sample");

    for (;;) {
        uint32_t wait = continuous ? 50U : APP_SVC_TICK_MS;

        if (app_inbox_get(&sample_inbox, &msg, wdt, wait) != 0) {
            if (continuous) {
                LOG_WRN("no DRDY for 50 ms: restarting the converter");
                stop_all();
                start_continuous();
            }
        } else if (msg.kind == MSG_DRDY) {
            int32_t code;

            if (continuous && (ads1220_read(adc, &code) == 0)) {
                publish_code(code);
            }
        } else if (msg.chan == &chan_settings) {
            take_settings(&msg.u.settings.s);
        } else if (msg.chan == &chan_system_state) {
            state = (enum pm_sysstate)msg.u.sys.state;
            if (pm_fsm_measuring(state)) {
                start_continuous();
            } else {
                stop_all();
                next_burst = k_uptime_get_32();
            }
        } else {
            /* nothing else reaches this inbox */
        }

        uint32_t now = k_uptime_get_32();

        if (continuous && ((int32_t)(now - next_temp) >= 0)) {
            next_temp = now + TEMP_PERIOD_MS;
            read_temperature();
        }
        if ((state == PM_ST_IDLE) && ((int32_t)(now - next_burst) >= 0)) {
            next_burst = now + CONFIG_PM_IDLE_BURST_PERIOD_MS;
            idle_burst();
        }
    }
}

K_THREAD_DEFINE(sample_tid, SAMPLE_STACK_SIZE, sample_thread, NULL, NULL, NULL, APP_PRIO_SAMPLE,
                0, SYS_FOREVER_MS);

void sample_svc_start(void)
{
    k_thread_name_set(sample_tid, "sample");
    k_thread_start(sample_tid);
}
