/**
 * @file pm_fsm.c
 * @brief The state machine of the system (docs/04)
 */

#include <string.h>

#include "model/pm_fsm.h"

static const char *const names[PM_ST_COUNT] = {
    "boot", "idle", "active", "sleep", "calibrating", "dfu", "low-battery",
};

struct pm_fsm_cfg pm_fsm_cfg_default(void)
{
    struct pm_fsm_cfg cfg = {
        .idle_after_ms = 30000U,
        .sleep_after_ms = 600000U,
        .cal_timeout_ms = 60000U,
        .dfu_min_soc_pct = 30U,
    };

    return cfg;
}

void pm_fsm_init(struct pm_fsm *f, const struct pm_fsm_cfg *cfg, uint32_t now_ms)
{
    (void)memset(f, 0, sizeof(*f));
    f->cfg = (cfg != NULL) ? *cfg : pm_fsm_cfg_default();
    f->state = PM_ST_BOOT;
    f->still_since_ms = now_ms;
    f->soc_pct = 100U;
}

void pm_fsm_set_soc(struct pm_fsm *f, uint8_t soc_pct)
{
    f->soc_pct = (soc_pct > 100U) ? 100U : soc_pct;
}

static void go_still(struct pm_fsm *f, uint32_t now_ms)
{
    if (f->moving) {
        f->moving = false;
        f->still_since_ms = now_ms;
    }
}

static pm_err_t on_motion(struct pm_fsm *f)
{
    switch (f->state) {
    case PM_ST_IDLE:
    case PM_ST_SLEEP:
    case PM_ST_ACTIVE:
        f->moving = true;
        f->state = PM_ST_ACTIVE;
        return PM_OK;
    case PM_ST_CALIBRATING:
        /* the crank moved under a calibration: it is void */
        f->moving = true;
        f->state = PM_ST_ACTIVE;
        return PM_OK;
    default:
        return PM_ESTATE;
    }
}

static pm_err_t on_still(struct pm_fsm *f, uint32_t now_ms)
{
    switch (f->state) {
    case PM_ST_ACTIVE:
    case PM_ST_IDLE:
    case PM_ST_CALIBRATING:
    case PM_ST_LOW_BATTERY:
        go_still(f, now_ms);
        return PM_OK;
    default:
        return PM_ESTATE;
    }
}

static pm_err_t on_cal_request(struct pm_fsm *f, uint32_t now_ms)
{
    if ((f->state != PM_ST_ACTIVE) && (f->state != PM_ST_IDLE)) {
        return PM_ESTATE;
    }
    if (f->moving) {
        return PM_ESTATE;
    }
    f->state = PM_ST_CALIBRATING;
    f->cal_since_ms = now_ms;
    return PM_OK;
}

static pm_err_t on_dfu_request(struct pm_fsm *f)
{
    switch (f->state) {
    case PM_ST_ACTIVE:
    case PM_ST_IDLE:
    case PM_ST_SLEEP:
        if (f->moving || (f->soc_pct < f->cfg.dfu_min_soc_pct)) {
            return PM_ESTATE;
        }
        f->state = PM_ST_DFU;
        return PM_OK;
    default:
        return PM_ESTATE;
    }
}

static pm_err_t on_battery_critical(struct pm_fsm *f, uint32_t now_ms)
{
    switch (f->state) {
    case PM_ST_ACTIVE:
    case PM_ST_IDLE:
    case PM_ST_SLEEP:
    case PM_ST_CALIBRATING:
        go_still(f, now_ms);
        f->state = PM_ST_LOW_BATTERY;
        return PM_OK;
    case PM_ST_LOW_BATTERY:
        return PM_OK;
    default:
        return PM_ESTATE;
    }
}

pm_err_t pm_fsm_event(struct pm_fsm *f, enum pm_event ev, uint32_t now_ms)
{
    switch (ev) {
    case PM_EV_READY:
        if (f->state != PM_ST_BOOT) {
            return PM_ESTATE;
        }
        f->state = PM_ST_IDLE;
        f->still_since_ms = now_ms;
        return PM_OK;
    case PM_EV_MOTION:
        return on_motion(f);
    case PM_EV_STILL:
        return on_still(f, now_ms);
    case PM_EV_WAKE:
        if (f->state != PM_ST_SLEEP) {
            return PM_ESTATE;
        }
        f->state = PM_ST_IDLE;
        f->still_since_ms = now_ms;
        return PM_OK;
    case PM_EV_CAL_REQUEST:
        return on_cal_request(f, now_ms);
    case PM_EV_CAL_DONE:
        if (f->state != PM_ST_CALIBRATING) {
            return PM_ESTATE;
        }
        f->state = PM_ST_IDLE;
        f->still_since_ms = now_ms;
        return PM_OK;
    case PM_EV_DFU_REQUEST:
        return on_dfu_request(f);
    case PM_EV_BATTERY_CRITICAL:
        return on_battery_critical(f, now_ms);
    case PM_EV_CHARGING:
        if (f->state == PM_ST_LOW_BATTERY) {
            f->state = PM_ST_IDLE;
            f->still_since_ms = now_ms;
        }
        return PM_OK;
    default:
        return PM_EINVAL;
    }
}

void pm_fsm_tick(struct pm_fsm *f, uint32_t now_ms)
{
    uint32_t still_ms = now_ms - f->still_since_ms;

    switch (f->state) {
    case PM_ST_ACTIVE:
        if (!f->moving && (still_ms >= f->cfg.idle_after_ms)) {
            f->state = PM_ST_IDLE;
        }
        break;
    case PM_ST_IDLE:
        if (!f->moving && (still_ms >= f->cfg.sleep_after_ms)) {
            f->state = PM_ST_SLEEP;
        }
        break;
    case PM_ST_CALIBRATING:
        if ((now_ms - f->cal_since_ms) >= f->cfg.cal_timeout_ms) {
            f->state = PM_ST_IDLE;
            f->still_since_ms = now_ms;
        }
        break;
    default:
        break;
    }
}

enum pm_sysstate pm_fsm_state(const struct pm_fsm *f)
{
    return f->state;
}

bool pm_fsm_measuring(enum pm_sysstate s)
{
    return (s == PM_ST_ACTIVE) || (s == PM_ST_CALIBRATING);
}

const char *pm_fsm_state_name(enum pm_sysstate s)
{
    return (s < PM_ST_COUNT) ? names[s] : "?";
}
