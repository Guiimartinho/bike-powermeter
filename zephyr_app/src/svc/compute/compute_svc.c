/**
 * @file compute_svc.c
 * @brief Compute service: torque and angle into power, calibrations, health
 *
 * docs/04 (Serviços, compute). The thread pairs each bridge sample with
 * the angular velocity of the last accelerometer sample (the two flows are
 * stamped with the same clock), integrates torque over angle with
 * model/rev_power.c, closes the revolution at the bottom event of
 * model/crank_angle.c and publishes chan_power; once a second it publishes
 * the status (zero power after 3 s without a revolution) and chan_health
 * from model/health.c.
 *
 * The calibrations of docs/06 run here on request ($ZERO, $SLOPE, $TEMP,
 * the control point, the ANT+ page), on the same bridge samples, and the
 * result goes to the settings in force and to chan_cmd_result. The auto
 * zero revises the zero while the crank rests, within the configured step.
 */

#include <math.h>
#include <stdio.h>
#include <string.h>

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/zbus/zbus.h>

#include "app/app_channels.h"
#include "app/app_services.h"
#include "app/app_svc.h"
#include "app/pm_store.h"
#include "model/bridge_calc.h"
#include "model/calib.h"
#include "model/health.h"
#include "model/pm_fsm.h"
#include "model/rev_power.h"

LOG_MODULE_REGISTER(compute_svc, CONFIG_LOG_DEFAULT_LEVEL);

/*
 * Measured with CONFIG_STACK_USAGE (2026-09-27): compute_thread 336 B with
 * the calibrations inlined, the answers print floats (about 500 B in
 * picolibc) and the publish chain: about 1,4 KB
 */
#define COMPUTE_STACK_SIZE  3072
/* 175 torque and 100 crank messages a second: a few milliseconds of both */
#define COMPUTE_INBOX_LEN   48

/** Samples averaged for one slope point */
#define SLOPE_POINT_SAMPLES 32U
/** The auto zero is tried again this long after one was taken */
#define AUTO_ZERO_PERIOD_MS 30000U

struct compute_msg {
    const struct zbus_channel *chan;
    union {
        struct app_torque torque;
        struct app_crank crank;
        struct app_temp temp;
        struct app_excitation exc;
        struct app_cmd_msg cmd;
        struct app_settings_msg settings;
        struct app_system_state sys;
    } u;
};

K_MSGQ_DEFINE(compute_inbox, sizeof(struct compute_msg), COMPUTE_INBOX_LEN, 4);

static void compute_listener(const struct zbus_channel *chan)
{
    struct compute_msg msg = { .chan = chan };

    if (chan == &chan_cmd) {
        const struct app_cmd_msg *c = zbus_chan_const_msg(chan);

        switch (c->id) {
        case PM_CMD_ZERO:
        case PM_CMD_SLOPE_POINT:
        case PM_CMD_SLOPE_END:
        case PM_CMD_TEMP_BEGIN:
        case PM_CMD_TEMP_POINT:
        case PM_CMD_TEMP_END:
            break;
        default:
            return;
        }
    }
    if (zbus_chan_msg_size(chan) > sizeof(msg.u)) {
        return;
    }
    (void)memcpy(&msg.u, zbus_chan_const_msg(chan), zbus_chan_msg_size(chan));
    app_inbox_put(&compute_inbox, &msg, "compute");
}

ZBUS_LISTENER_DEFINE(compute_lis, compute_listener);
ZBUS_CHAN_ADD_OBS(chan_torque, compute_lis, 3);
ZBUS_CHAN_ADD_OBS(chan_crank, compute_lis, 3);
ZBUS_CHAN_ADD_OBS(chan_temp, compute_lis, 3);
ZBUS_CHAN_ADD_OBS(chan_excitation, compute_lis, 3);
ZBUS_CHAN_ADD_OBS(chan_cmd, compute_lis, 3);
ZBUS_CHAN_ADD_OBS(chan_settings, compute_lis, 3);
ZBUS_CHAN_ADD_OBS(chan_system_state, compute_lis, 3);

/* ---- state ------------------------------------------------------------ */

static struct pm_settings settings;
static struct rev_power rp;
static struct health hl;
static enum pm_sysstate state = PM_ST_BOOT;

/* the last accelerometer sample */
static float omega;
static float angle;
static bool stationary = true;
static uint32_t last_torque_ms;
static bool have_torque;

/* the last bridge sample and temperature, for the status */
static int32_t last_code;
static float temp_c = 25.0f;
static uint16_t ref_mv;

/* the torque profile of the revolution in progress, by angle bin */
static int32_t bin_sum[APP_VECTOR_POINTS];
static uint16_t bin_n[APP_VECTOR_POINTS];

/* a collection of samples for a zero (manual, auto, temperature point) */
enum collect_kind {
    COLLECT_NONE = 0,
    COLLECT_ZERO,
    COLLECT_AUTO_ZERO,
    COLLECT_TEMP_POINT,
    COLLECT_SLOPE_POINT
};

static struct {
    enum collect_kind kind;
    uint8_t source;
    struct calib_zero zero;
    int64_t sum;
    uint16_t n;
    uint32_t mass_g;
    uint16_t length_mm;
    bool descending;
} collect;

static struct calib_slope slope;
static struct calib_temp tcurve;
static bool tcurve_open;
static uint32_t next_auto_zero;

static void take_settings(const struct pm_settings *s)
{
    struct rev_power_cfg cfg = rev_power_cfg_default();

    settings = *s;
    cfg.single_side = true;
    rev_power_init(&rp, &cfg);
    health_calibrated(&hl, pm_settings_calibrated(s));
}

/* ---- power per revolution --------------------------------------------- */

static void reset_bins(void)
{
    (void)memset(bin_sum, 0, sizeof(bin_sum));
    (void)memset(bin_n, 0, sizeof(bin_n));
}

static void publish_power(const struct rev_power_out *out, bool revolution)
{
    struct app_power p = {
        .uptime_ms = k_uptime_get_32(),
        .power_w = out->power_w,
        .cadence_rpm = (uint8_t)((out->cadence_rpm > 254.0f) ? 254.0f : (out->cadence_rpm + 0.5f)),
        .te_pct = out->te_pct,
        .ps_pct = out->ps_pct,
        .balance_pct = out->balance_pct,
        .torque_acc_1_32 = out->torque_acc_1_32,
        .rev_count = out->rev_count,
        .last_event_1024 = out->last_event_1024,
        .energy_kj = out->energy_kj,
        .health_flags = health_flags(&hl),
        .revolution = revolution,
        .measuring = health_can_measure(&hl),
    };

    (void)app_publish(&chan_power, &p);
}

static void publish_vector(const struct rev_power_out *out)
{
    struct app_vector v = {
        .rev_count = out->rev_count,
        .last_event_1024 = out->last_event_1024,
        .first_angle_deg = 0U,
    };

    for (size_t i = 0U; i < APP_VECTOR_POINTS; i++) {
        int32_t mean = (bin_n[i] > 0U) ? (bin_sum[i] / (int32_t)bin_n[i]) : 0;
        /* mN.m to 1/32 N.m */
        int32_t t32 = (mean * 32) / 1000;

        v.torque_1_32[i] = (int16_t)pm_clamp_i32((t32 > INT16_MAX) ? INT16_MAX :
                                                   (t32 < INT16_MIN) ? INT16_MIN : t32);
    }
    (void)app_publish(&chan_vector, &v);
}

static void on_torque(const struct app_torque *t)
{
    uint32_t dt_ms;

    last_code = t->code;
    health_bridge(&hl, t->code, t->excitation_on, t->uptime_ms);
    if (collect.kind != COLLECT_NONE) {
        /* a calibration takes the samples; nothing is measured meanwhile */
        if ((collect.kind == COLLECT_SLOPE_POINT)) {
            collect.sum += t->code;
            collect.n++;
        } else {
            calib_zero_add(&collect.zero, t->code);
        }
        return;
    }
    if (!have_torque) {
        have_torque = true;
        last_torque_ms = t->uptime_ms;
        return;
    }
    dt_ms = t->uptime_ms - last_torque_ms;
    last_torque_ms = t->uptime_ms;
    if (!t->calibrated || !health_can_measure(&hl) || stationary || (omega <= 0.0f)) {
        return;
    }

    float dtheta = omega * (float)dt_ms / 1000.0f;
    size_t bin = (size_t)(angle / PM_TWO_PI * (float)APP_VECTOR_POINTS) % APP_VECTOR_POINTS;

    rev_power_feed(&rp, t->torque_mnm, dtheta, dt_ms, omega);
    bin_sum[bin] += t->torque_mnm;
    bin_n[bin]++;
}

static void on_crank(const struct app_crank *c)
{
    health_imu(&hl, c->mag_g, c->uptime_ms);
    if (!c->valid) {
        return;
    }
    omega = c->omega_rad_s;
    angle = c->angle_rad;
    stationary = c->stationary;
    if (c->revolution && (collect.kind == COLLECT_NONE)) {
        struct rev_power_out out;

        if (rev_power_close(&rp, c->uptime_ms, &out) == PM_OK) {
            publish_power(&out, true);
            publish_vector(&out);
        }
        reset_bins();
    }
}

/* ---- calibrations ------------------------------------------------------ */

static void reply(uint8_t id, uint8_t source, pm_err_t err, int32_t value, const char *text)
{
    app_cmd_reply(id, source, (uint8_t)err, value, text);
}

static void start_collect(enum collect_kind kind, uint8_t source)
{
    collect.kind = kind;
    collect.source = source;
    collect.sum = 0;
    collect.n = 0U;
    calib_zero_reset(&collect.zero);
}

static void save_settings(bool persist)
{
    if (pm_store_set(&settings, persist) != PM_OK) {
        LOG_ERR("settings refused after calibration");
    }
}

static void finish_zero(void)
{
    int32_t zero = 0;
    float sd = 0.0f;
    pm_err_t err = calib_zero_result(&collect.zero, &zero, &sd);
    char text[APP_CMD_TEXT_LEN];

    if (err == PM_ENOTREADY) {
        return;
    }
    if (collect.kind == COLLECT_AUTO_ZERO) {
        if ((err == PM_OK) &&
            calib_zero_accept_auto(settings.cal.zero_code, zero, settings.auto_zero_max_step)) {
            settings.cal.zero_code = zero;
            save_settings(false);
            LOG_INF("auto zero %ld (sd %.1f)", (long)zero, (double)sd);
        }
        health_zero(&hl, zero, settings.cal.zero_code, settings.auto_zero_max_step);
        collect.kind = COLLECT_NONE;
        return;
    }
    if (collect.kind == COLLECT_TEMP_POINT) {
        if (err == PM_OK) {
            /* the zero at this temperature; the slope stays the one in force
             * (its own temperature coefficient needs a mass at each point) */
            err = calib_temp_add(&tcurve, temp_c, (float)zero, settings.cal.slope_unm);
        }
        (void)snprintf(text, sizeof(text), "%ld,%.2f,%u", (long)zero, (double)temp_c,
                       (unsigned int)tcurve.n);
        reply(PM_CMD_TEMP_POINT, collect.source, err, zero, (err == PM_OK) ? text : NULL);
        collect.kind = COLLECT_NONE;
        return;
    }
    /* the manual zero */
    if (err == PM_OK) {
        settings.cal.zero_code = zero;
        save_settings(true);
        health_zero(&hl, zero, zero, settings.auto_zero_max_step);
    }
    (void)snprintf(text, sizeof(text), "%ld,%.1f", (long)zero, (double)sd);
    reply(PM_CMD_ZERO, collect.source, err, zero, (err == PM_OK) ? text : NULL);
    collect.kind = COLLECT_NONE;
}

static void finish_slope_point(void)
{
    int32_t code;
    int32_t torque;
    pm_err_t err;
    char text[APP_CMD_TEXT_LEN];

    if (collect.n < SLOPE_POINT_SAMPLES) {
        return;
    }
    code = (int32_t)(collect.sum / collect.n);
    torque = calib_torque_from_mass_mnm(collect.mass_g, collect.length_mm, 0.0f);
    err = calib_slope_add(&slope, code, settings.cal.zero_code, torque, collect.descending);
    (void)snprintf(text, sizeof(text), "%ld,%ld,%u", (long)code, (long)torque,
                   (unsigned int)slope.n);
    reply(PM_CMD_SLOPE_POINT, collect.source, err, code, (err == PM_OK) ? text : NULL);
    collect.kind = COLLECT_NONE;
}

static void slope_end(uint8_t source)
{
    struct calib_slope_result r;
    pm_err_t err = calib_slope_fit(&slope, &r);
    char text[APP_CMD_TEXT_LEN];

    if (err == PM_OK) {
        settings.cal.slope_unm = r.slope_unm;
        save_settings(true);
        health_calibrated(&hl, pm_settings_calibrated(&settings));
        (void)snprintf(text, sizeof(text), "%.3f,%.2f,%.2f,%u", (double)r.slope_unm,
                       (double)r.residual_pct, (double)r.hysteresis_pct, (unsigned int)r.points);
    }
    calib_slope_reset(&slope);
    reply(PM_CMD_SLOPE_END, source, err, 0, (err == PM_OK) ? text : NULL);
}

static void temp_end(uint8_t source)
{
    struct bridge_cal cal = settings.cal;
    pm_err_t err = tcurve_open ? calib_temp_fit(&tcurve, &cal) : PM_ESTATE;
    char text[APP_CMD_TEXT_LEN];

    if (err == PM_OK) {
        settings.cal = cal;
        save_settings(true);
        (void)snprintf(text, sizeof(text), "%.2f,%.4g,%.4g,%.4g", (double)cal.t0_c,
                       (double)cal.k1, (double)cal.k2, (double)cal.k3);
    }
    tcurve_open = false;
    reply(PM_CMD_TEMP_END, source, err, 0, (err == PM_OK) ? text : NULL);
}

static void on_cmd(const struct app_cmd_msg *m)
{
    if (collect.kind != COLLECT_NONE) {
        reply(m->id, m->source, PM_ESTATE, 0, NULL);
        return;
    }
    switch (m->id) {
    case PM_CMD_ZERO:
        if (!stationary || !pm_fsm_measuring(state)) {
            reply(m->id, m->source, PM_ESTATE, 0, NULL);
            return;
        }
        start_collect(COLLECT_ZERO, m->source);
        break;
    case PM_CMD_SLOPE_POINT:
        if (!pm_fsm_measuring(state)) {
            reply(m->id, m->source, PM_ESTATE, 0, NULL);
            return;
        }
        start_collect(COLLECT_SLOPE_POINT, m->source);
        collect.mass_g = m->cmd.mass_g;
        collect.length_mm = m->cmd.length_mm;
        collect.descending = m->cmd.descending;
        break;
    case PM_CMD_SLOPE_END:
        slope_end(m->source);
        break;
    case PM_CMD_TEMP_BEGIN:
        calib_temp_reset(&tcurve);
        tcurve_open = true;
        reply(m->id, m->source, PM_OK, 0, NULL);
        break;
    case PM_CMD_TEMP_POINT:
        if (!tcurve_open || !stationary || !pm_fsm_measuring(state)) {
            reply(m->id, m->source, PM_ESTATE, 0, NULL);
            return;
        }
        start_collect(COLLECT_TEMP_POINT, m->source);
        break;
    case PM_CMD_TEMP_END:
        temp_end(m->source);
        break;
    default:
        break;
    }
}

/* ---- once a second ----------------------------------------------------- */

static void status(uint32_t now)
{
    struct rev_power_out out;
    struct app_health h = {
        .flags = health_flags(&hl),
        .temp_c = temp_c,
        .code = last_code,
        .zero = settings.cal.zero_code,
        .ref_mv = ref_mv,
    };

    health_tick(&hl, now);
    rev_power_status(&rp, now, &out);
    publish_power(&out, false);
    (void)app_publish(&chan_health, &h);

    /* the auto zero, while the crank rests and the bridge samples come */
    if (settings.auto_zero && stationary && (collect.kind == COLLECT_NONE) &&
        pm_settings_calibrated(&settings) && ((int32_t)(now - next_auto_zero) >= 0)) {
        next_auto_zero = now + AUTO_ZERO_PERIOD_MS;
        start_collect(COLLECT_AUTO_ZERO, APP_SRC_LOCAL);
    }
    if ((collect.kind == COLLECT_AUTO_ZERO) && !stationary) {
        collect.kind = COLLECT_NONE;
    }
}

static void compute_thread(void *p1, void *p2, void *p3)
{
    struct compute_msg msg;
    struct pm_settings s;
    uint32_t next_status = k_uptime_get_32() + CONFIG_PM_STATUS_PERIOD_MS;

    ARG_UNUSED(p1);
    ARG_UNUSED(p2);
    ARG_UNUSED(p3);

    pm_store_get(&s);
    health_init(&hl, NULL);
    take_settings(&s);
    calib_slope_reset(&slope);
    calib_temp_reset(&tcurve);
    reset_bins();

    int wdt = app_wdt_add("compute");

    for (;;) {
        uint32_t now = k_uptime_get_32();
        uint32_t wait = ((int32_t)(next_status - now) > 0) ? (next_status - now) : 0U;

        if (app_inbox_get(&compute_inbox, &msg, wdt, wait) == 0) {
            if (msg.chan == &chan_torque) {
                on_torque(&msg.u.torque);
                if (collect.kind == COLLECT_SLOPE_POINT) {
                    finish_slope_point();
                } else if (collect.kind != COLLECT_NONE) {
                    finish_zero();
                } else {
                    /* measuring */
                }
            } else if (msg.chan == &chan_crank) {
                on_crank(&msg.u.crank);
            } else if (msg.chan == &chan_temp) {
                if (msg.u.temp.valid) {
                    temp_c = msg.u.temp.temp_c;
                    health_temperature(&hl, temp_c);
                }
            } else if (msg.chan == &chan_excitation) {
                if (msg.u.exc.valid) {
                    ref_mv = msg.u.exc.ref_mv;
                    health_excitation(&hl, ref_mv);
                }
            } else if (msg.chan == &chan_cmd) {
                on_cmd(&msg.u.cmd);
            } else if (msg.chan == &chan_settings) {
                take_settings(&msg.u.settings.s);
            } else if (msg.chan == &chan_system_state) {
                state = (enum pm_sysstate)msg.u.sys.state;
                if (!pm_fsm_measuring(state) && (collect.kind != COLLECT_NONE) &&
                    (collect.kind != COLLECT_AUTO_ZERO)) {
                    reply(PM_CMD_ZERO, collect.source, PM_ESTATE, 0, NULL);
                    collect.kind = COLLECT_NONE;
                }
                if (collect.kind == COLLECT_AUTO_ZERO) {
                    collect.kind = COLLECT_NONE;
                }
            } else {
                /* nothing else reaches this inbox */
            }
        }
        now = k_uptime_get_32();
        if ((int32_t)(now - next_status) >= 0) {
            next_status = now + CONFIG_PM_STATUS_PERIOD_MS;
            status(now);
        }
    }
}

K_THREAD_DEFINE(compute_tid, COMPUTE_STACK_SIZE, compute_thread, NULL, NULL, NULL,
                APP_PRIO_COMPUTE, 0, SYS_FOREVER_MS);

void compute_svc_start(void)
{
    k_thread_name_set(compute_tid, "compute");
    k_thread_start(compute_tid);
}
