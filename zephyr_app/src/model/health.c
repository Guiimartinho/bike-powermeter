/**
 * @file health.c
 * @brief The health flags of the sensor chain (docs/06)
 */

#include <string.h>

#include "model/health.h"

struct health_cfg health_cfg_default(void)
{
    struct health_cfg cfg = {
        .excitation_nominal_mv = 3000U,
        .excitation_tol_pct = 10U,
        .stuck_ms = 2000U,
        .imu_stale_ms = 500U,
        .imu_range_ms = 1000U,
        .imu_min_g = 0.5f,
        .imu_max_g = 6.0f,
        .temp_min_c = -20.0f,
        .temp_max_c = 70.0f,
    };

    return cfg;
}

void health_init(struct health *h, const struct health_cfg *cfg)
{
    (void)memset(h, 0, sizeof(*h));
    h->cfg = (cfg != NULL) ? *cfg : health_cfg_default();
    h->flags = HEALTH_NOT_CALIBRATED;
}

static void set_flag(struct health *h, uint16_t flag, bool on)
{
    if (on) {
        h->flags |= flag;
    } else {
        h->flags &= (uint16_t)~flag;
    }
}

void health_bridge(struct health *h, int32_t code, bool excitation_on, uint32_t now_ms)
{
    const int32_t limit = (int32_t)((PM_ADC_FULL_SCALE * (long)PM_ADC_RANGE_PCT) / 100L);

    if (!excitation_on) {
        /* nothing to judge without excitation; the stuck timer restarts */
        h->have_code = false;
        return;
    }
    set_flag(h, HEALTH_BRIDGE_OPEN, (code <= -limit) || (code >= limit));

    if (!h->have_code || (code != h->last_code)) {
        h->have_code = true;
        h->last_code = code;
        h->code_since_ms = now_ms;
        set_flag(h, HEALTH_BRIDGE_STUCK, false);
        return;
    }
    if ((now_ms - h->code_since_ms) >= h->cfg.stuck_ms) {
        set_flag(h, HEALTH_BRIDGE_STUCK, true);
    }
}

void health_excitation(struct health *h, uint16_t ref_mv)
{
    uint32_t tol = ((uint32_t)h->cfg.excitation_nominal_mv * h->cfg.excitation_tol_pct) / 100U;
    uint32_t lo = (uint32_t)h->cfg.excitation_nominal_mv - tol;
    uint32_t hi = (uint32_t)h->cfg.excitation_nominal_mv + tol;

    set_flag(h, HEALTH_EXCITATION, (ref_mv < lo) || (ref_mv > hi));
}

void health_imu(struct health *h, float mag_g, uint32_t now_ms)
{
    bool bad = (mag_g < h->cfg.imu_min_g) || (mag_g > h->cfg.imu_max_g);

    h->have_imu = true;
    h->last_imu_ms = now_ms;
    set_flag(h, HEALTH_IMU_STALE, false);

    if (!bad) {
        h->imu_bad = false;
        set_flag(h, HEALTH_IMU_RANGE, false);
        return;
    }
    if (!h->imu_bad) {
        h->imu_bad = true;
        h->imu_bad_since_ms = now_ms;
    }
    if ((now_ms - h->imu_bad_since_ms) >= h->cfg.imu_range_ms) {
        set_flag(h, HEALTH_IMU_RANGE, true);
    }
}

void health_temperature(struct health *h, float temp_c)
{
    set_flag(h, HEALTH_TEMP_RANGE, (temp_c < h->cfg.temp_min_c) || (temp_c > h->cfg.temp_max_c));
}

void health_zero(struct health *h, int32_t zero_now, int32_t zero_cal, int32_t max_step)
{
    int64_t step = (int64_t)zero_now - (int64_t)zero_cal;

    if (max_step <= 0) {
        set_flag(h, HEALTH_ZERO_DRIFT, false);
        return;
    }
    if (step < 0) {
        step = -step;
    }
    set_flag(h, HEALTH_ZERO_DRIFT, step > (int64_t)max_step);
}

void health_calibrated(struct health *h, bool calibrated)
{
    set_flag(h, HEALTH_NOT_CALIBRATED, !calibrated);
}

void health_tick(struct health *h, uint32_t now_ms)
{
    if (h->have_imu && ((now_ms - h->last_imu_ms) >= h->cfg.imu_stale_ms)) {
        set_flag(h, HEALTH_IMU_STALE, true);
    }
}

uint16_t health_flags(const struct health *h)
{
    return h->flags;
}

bool health_can_measure(const struct health *h)
{
    return (h->flags & HEALTH_FATAL_MASK) == 0U;
}
