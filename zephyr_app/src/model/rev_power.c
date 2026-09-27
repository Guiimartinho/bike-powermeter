/**
 * @file rev_power.c
 * @brief Power per revolution and the accumulators (docs/06)
 */

#include <math.h>
#include <string.h>

#include "model/rev_power.h"

struct rev_power_cfg rev_power_cfg_default(void)
{
    struct rev_power_cfg cfg = {
        .single_side = true,
        .balance_pct = 50U,
        .zero_after_ms = 3000U,
    };

    return cfg;
}

void rev_power_init(struct rev_power *rp, const struct rev_power_cfg *cfg)
{
    (void)memset(rp, 0, sizeof(*rp));
    rp->cfg = (cfg != NULL) ? *cfg : rev_power_cfg_default();
    rp->last.balance_pct = rp->cfg.balance_pct;
}

static void restart_revolution(struct rev_power *rp)
{
    rp->work_j = 0.0f;
    rp->work_pos_j = 0.0f;
    rp->work_neg_j = 0.0f;
    rp->peak_w = 0.0f;
    rp->period_s = 0.0f;
    rp->samples = 0U;
}

void rev_power_feed(struct rev_power *rp, int32_t torque_mnm, float dtheta_rad, uint32_t dt_ms,
                    float omega_rad_s)
{
    float tau = (float)torque_mnm / 1000.0f;
    float work = tau * dtheta_rad;

    rp->work_j += work;
    if (work >= 0.0f) {
        rp->work_pos_j += work;
    } else {
        rp->work_neg_j += work;
    }

    float p = tau * omega_rad_s;

    if (p > rp->peak_w) {
        rp->peak_w = p;
    }
    rp->period_s += (float)dt_ms / 1000.0f;
    if (rp->samples < UINT16_MAX) {
        rp->samples++;
    }
}

static uint8_t pct_u8(float ratio)
{
    if (!(ratio > 0.0f)) {
        return 0U;
    }
    if (ratio >= 1.0f) {
        return 100U;
    }
    return (uint8_t)lroundf(ratio * 100.0f);
}

pm_err_t rev_power_close(struct rev_power *rp, uint32_t uptime_ms, struct rev_power_out *out)
{
    uint32_t period_ms = (uint32_t)lroundf(rp->period_s * 1000.0f);
    bool ok = (rp->samples >= REV_MIN_SAMPLES) && (period_ms >= REV_MIN_PERIOD_MS) &&
              (period_ms <= REV_MAX_PERIOD_MS);

    if (!ok) {
        restart_revolution(rp);
        return PM_EINVAL;
    }

    float power = rp->work_j / rp->period_s;

    if (rp->cfg.single_side) {
        power *= 2.0f;
    }
    if (power < 0.0f) {
        power = 0.0f;
    }
    if (power > 65535.0f) {
        power = 65535.0f;
    }

    /* the mean torque of the revolution: work over one turn */
    float mean_torque = rp->work_j / PM_TWO_PI;

    if (mean_torque > 0.0f) {
        rp->torque_acc_nm += mean_torque;
    }
    rp->energy_j += power * rp->period_s;
    rp->rev_count++;
    rp->last_event_1024 = pm_ms_to_1024(uptime_ms);
    rp->last_rev_ms = uptime_ms;
    rp->have_rev = true;

    struct rev_power_out o = {
        .power_w = (uint16_t)lroundf(power),
        .cadence_rpm = 60.0f / rp->period_s,
        .te_pct = (rp->work_pos_j > 0.0f)
                      ? pct_u8((rp->work_pos_j + rp->work_neg_j) / rp->work_pos_j)
                      : 0U,
        .ps_pct = (rp->peak_w > 0.0f) ? pct_u8((rp->work_j / rp->period_s) / rp->peak_w) : 0U,
        .balance_pct = rp->cfg.balance_pct,
        .torque_acc_1_32 = (uint16_t)((uint32_t)lroundf(rp->torque_acc_nm * 32.0f) & 0xFFFFU),
        .rev_count = rp->rev_count,
        .last_event_1024 = rp->last_event_1024,
        .energy_kj = (uint16_t)((uint32_t)(rp->energy_j / 1000.0f) & 0xFFFFU),
    };

    rp->last = o;
    *out = o;
    restart_revolution(rp);
    return PM_OK;
}

void rev_power_status(const struct rev_power *rp, uint32_t now_ms, struct rev_power_out *out)
{
    *out = rp->last;
    if (!rp->have_rev || ((now_ms - rp->last_rev_ms) > rp->cfg.zero_after_ms)) {
        out->power_w = 0U;
        out->cadence_rpm = 0.0f;
        out->te_pct = 0U;
        out->ps_pct = 0U;
    }
}
