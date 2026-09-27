/**
 * @file motion_svc.c
 * @brief Motion service: the crank angle, its velocity, the revolutions
 *
 * docs/04 (Serviços, motion). The BMA400 of the alias imu0 raises INT1 at
 * each sample; the driver's trigger thread calls the handler below, which
 * only gives a semaphore, and this thread reads the three axes by the
 * sensor API, runs the estimator of model/crank_angle.c and publishes
 * chan_crank at every sample and chan_motion_state when the crank starts
 * or stops turning.
 *
 * Axes: which axis of the package is radial (along the arm, outward
 * positive) and which is tangential is a fact of the board on the arm, set
 * by CONFIG_PM_IMU_AXIS_RADIAL and CONFIG_PM_IMU_AXIS_TANGENTIAL and to be
 * confirmed on the pod; the sign of the tangential axis is the setting
 * tangential_sign of docs/05, so a pod on the right arm needs no other
 * build.
 *
 * In Sleep the sensor goes to its low power mode with the wake-up
 * interrupt, which is also what wakes the SoC from System OFF ($SLEEP).
 */

#include <math.h>
#include <string.h>

#include <zephyr/device.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/zbus/zbus.h>

#include <drivers/sensor/bma400.h>

#include "app/app_channels.h"
#include "app/app_services.h"
#include "app/app_svc.h"
#include "app/pm_store.h"
#include "model/crank_angle.h"
#include "model/pm_fsm.h"
#include "model/pm_types.h"

LOG_MODULE_REGISTER(motion_svc, CONFIG_LOG_DEFAULT_LEVEL);

/*
 * Measured with CONFIG_STACK_USAGE (2026-09-27): motion_thread 248 B with
 * one_sample inlined, crank_update 64, the SPI fetch of the sensor and the
 * publish chain: about 1,2 KB with the exception frame
 */
#define MOTION_STACK_SIZE   2560
#define MOTION_INBOX_LEN    8

/** Wake-up interrupt of the low power mode: 250 mg over 3 samples */
#define WAKE_THRESH_MG      250
#define WAKE_SAMPLES        3

#define IMU_NODE    DT_ALIAS(imu0)

#if DT_NODE_HAS_STATUS_OKAY(IMU_NODE)
static const struct device *const imu = DEVICE_DT_GET(IMU_NODE);
#else
static const struct device *const imu = NULL;
#endif

struct motion_msg {
    const struct zbus_channel *chan;
    union {
        struct app_system_state sys;
        struct app_settings_msg settings;
    } u;
};

K_MSGQ_DEFINE(motion_inbox, sizeof(struct motion_msg), MOTION_INBOX_LEN, 4);

static void motion_listener(const struct zbus_channel *chan)
{
    struct motion_msg msg = { .chan = chan };

    if (zbus_chan_msg_size(chan) > sizeof(msg.u)) {
        return;
    }
    (void)memcpy(&msg.u, zbus_chan_const_msg(chan), zbus_chan_msg_size(chan));
    app_inbox_put(&motion_inbox, &msg, "motion");
}

ZBUS_LISTENER_DEFINE(motion_lis, motion_listener);
ZBUS_CHAN_ADD_OBS(chan_system_state, motion_lis, 3);
ZBUS_CHAN_ADD_OBS(chan_settings, motion_lis, 3);

static K_SEM_DEFINE(sample_sem, 0, 1);
static K_SEM_DEFINE(wake_sem, 0, 1);

/** In the trigger thread of the driver: signal and return */
static void drdy_handler(const struct device *dev, const struct sensor_trigger *trig)
{
    ARG_UNUSED(dev);
    ARG_UNUSED(trig);
    k_sem_give(&sample_sem);
}

static void wake_handler(const struct device *dev, const struct sensor_trigger *trig)
{
    ARG_UNUSED(dev);
    ARG_UNUSED(trig);
    k_sem_give(&wake_sem);
}

static const struct sensor_trigger drdy_trig = {
    .type = SENSOR_TRIG_DATA_READY,
    .chan = SENSOR_CHAN_ACCEL_XYZ,
};
static const struct sensor_trigger wake_trig = {
    .type = BMA400_TRIG_WAKEUP,
    .chan = SENSOR_CHAN_ACCEL_XYZ,
};

static struct crank_state crank;
static bool moving;
static bool sampling;

static void take_settings(const struct pm_settings *s)
{
    struct crank_cfg cfg = crank_cfg_default();

    cfg.radius_m = (float)s->sensor_radius_mm / 1000.0f;
    cfg.tangential_sign = (float)s->tangential_sign;
    crank_init(&crank, &cfg);
}

static int set_mode(enum bma400_power_mode mode)
{
    struct sensor_value v = { .val1 = (int32_t)mode };

    return sensor_attr_set(imu, SENSOR_CHAN_ACCEL_XYZ, (enum sensor_attribute)BMA400_ATTR_POWER_MODE,
                           &v);
}

static void sampling_on(void)
{
    if ((imu == NULL) || sampling) {
        return;
    }
    (void)set_mode(BMA400_MODE_NORMAL);
    (void)sensor_trigger_set(imu, &wake_trig, NULL);
    if (sensor_trigger_set(imu, &drdy_trig, drdy_handler) != 0) {
        LOG_ERR("data-ready trigger failed");
    }
    sampling = true;
}

static void sampling_off(bool wake_on_motion)
{
    struct sensor_value w = { .val1 = wake_on_motion ? WAKE_THRESH_MG : 0, .val2 = WAKE_SAMPLES };

    if (imu == NULL) {
        return;
    }
    (void)sensor_trigger_set(imu, &drdy_trig, NULL);
    sampling = false;
    if (wake_on_motion) {
        (void)sensor_attr_set(imu, SENSOR_CHAN_ACCEL_XYZ, (enum sensor_attribute)BMA400_ATTR_WAKEUP,
                              &w);
        (void)sensor_trigger_set(imu, &wake_trig, wake_handler);
        (void)set_mode(BMA400_MODE_LOW_POWER);
    } else {
        (void)sensor_trigger_set(imu, &wake_trig, NULL);
        (void)set_mode(BMA400_MODE_SLEEP);
    }
}

static void publish_motion(bool now_moving)
{
    struct app_motion_state m = { .uptime_ms = k_uptime_get_32(), .moving = now_moving };

    moving = now_moving;
    (void)app_publish(&chan_motion_state, &m);
}

static void one_sample(void)
{
    struct sensor_value a[3];
    float axes[3];
    struct crank_out out;
    struct app_crank c;

    if ((sensor_sample_fetch_chan(imu, SENSOR_CHAN_ACCEL_XYZ) != 0) ||
        (sensor_channel_get(imu, SENSOR_CHAN_ACCEL_XYZ, a) != 0)) {
        return;
    }
    for (size_t i = 0U; i < 3U; i++) {
        axes[i] = sensor_value_to_float(&a[i]);
    }

    float a_r = (float)CONFIG_PM_IMU_RADIAL_SIGN * axes[CONFIG_PM_IMU_AXIS_RADIAL];
    float a_t = axes[CONFIG_PM_IMU_AXIS_TANGENTIAL];
    float a_l = axes[3 - CONFIG_PM_IMU_AXIS_RADIAL - CONFIG_PM_IMU_AXIS_TANGENTIAL];
    uint32_t now = k_uptime_get_32();

    crank_update(&crank, a_t, a_r, a_l, now, &out);
    c.uptime_ms = now;
    c.angle_rad = out.angle_rad;
    c.omega_rad_s = out.omega_rad_s;
    c.dtheta_rad = out.dtheta_rad;
    c.mag_g = sqrtf((axes[0] * axes[0]) + (axes[1] * axes[1]) + (axes[2] * axes[2])) / PM_GRAVITY;
    c.revolution = out.revolution;
    c.stationary = out.stationary;
    c.valid = out.valid;
    (void)app_publish(&chan_crank, &c);

    bool now_moving = (out.omega_rad_s != 0.0f);

    if (now_moving != moving) {
        publish_motion(now_moving);
    }
}

static void motion_thread(void *p1, void *p2, void *p3)
{
    struct motion_msg msg;
    struct pm_settings s;

    ARG_UNUSED(p1);
    ARG_UNUSED(p2);
    ARG_UNUSED(p3);

    pm_store_get(&s);
    take_settings(&s);
    if ((imu == NULL) || !device_is_ready(imu)) {
        LOG_ERR("no accelerometer");
    }

    int wdt = app_wdt_add("motion");

    for (;;) {
        /* the sample semaphore first: 100 Hz must not wait for the inbox */
        if (sampling && (k_sem_take(&sample_sem, K_MSEC(20)) == 0)) {
            one_sample();
            app_wdt_feed(wdt);
            if (k_msgq_get(&motion_inbox, &msg, K_NO_WAIT) != 0) {
                continue;
            }
        } else if (k_sem_take(&wake_sem, K_NO_WAIT) == 0) {
            /* the crank moved in Sleep: the power service brings the pod back */
            publish_motion(true);
            continue;
        } else if (app_inbox_get(&motion_inbox, &msg, wdt, sampling ? 20U : APP_SVC_TICK_MS) != 0) {
            continue;
        } else {
            /* a message came in */
        }

        if (msg.chan == &chan_settings) {
            take_settings(&msg.u.settings.s);
        } else if (msg.chan == &chan_system_state) {
            enum pm_sysstate st = (enum pm_sysstate)msg.u.sys.state;

            if ((st == PM_ST_IDLE) || pm_fsm_measuring(st)) {
                sampling_on();
            } else if (st == PM_ST_SLEEP) {
                sampling_off(true);
                if (moving) {
                    publish_motion(false);
                }
            } else {
                sampling_off(false);
            }
        } else {
            /* nothing else reaches this inbox */
        }
    }
}

K_THREAD_DEFINE(motion_tid, MOTION_STACK_SIZE, motion_thread, NULL, NULL, NULL, APP_PRIO_MOTION,
                0, SYS_FOREVER_MS);

void motion_svc_start(void)
{
    k_thread_name_set(motion_tid, "motion");
    k_thread_start(motion_tid);
}
