/**
 * @file bridge_calc.c
 * @brief From the converter code to torque (docs/06, Da ponte ao torque)
 */

#include <math.h>

#include "model/bridge_calc.h"

void bridge_filter_reset(struct bridge_filter *f)
{
    f->n = 0U;
    f->idx = 0U;
    f->buf[0] = 0;
    f->buf[1] = 0;
    f->buf[2] = 0;
}

bool bridge_filter_median3(struct bridge_filter *f, int32_t code, int32_t *out)
{
    f->buf[f->idx] = code;
    f->idx = (uint8_t)((f->idx + 1U) % 3U);
    if (f->n < 3U) {
        f->n++;
    }
    if (f->n < 3U) {
        return false;
    }

    int32_t a = f->buf[0];
    int32_t b = f->buf[1];
    int32_t c = f->buf[2];

    /* the median is the one that is neither the minimum nor the maximum */
    if ((a >= b) == (a <= c)) {
        *out = a;
    } else if ((b >= a) == (b <= c)) {
        *out = b;
    } else {
        *out = c;
    }
    return true;
}

float bridge_zero_at(const struct bridge_cal *cal, float temp_c)
{
    float dt = temp_c - cal->t0_c;

    return (float)cal->zero_code + (cal->k1 * dt) + (cal->k2 * dt * dt);
}

float bridge_slope_at(const struct bridge_cal *cal, float temp_c)
{
    float dt = temp_c - cal->t0_c;

    return cal->slope_unm * (1.0f + (cal->k3 * dt));
}

int32_t bridge_torque_mnm(const struct bridge_cal *cal, int32_t code, float temp_c)
{
    float delta = (float)code - bridge_zero_at(cal, temp_c);
    /* µN·m to mN·m */
    float tau = delta * bridge_slope_at(cal, temp_c) / 1000.0f;

    if (tau > (float)BRIDGE_TORQUE_MAX_MNM) {
        return BRIDGE_TORQUE_MAX_MNM;
    }
    if (tau < -(float)BRIDGE_TORQUE_MAX_MNM) {
        return -BRIDGE_TORQUE_MAX_MNM;
    }
    return (int32_t)lroundf(tau);
}

bool bridge_code_in_range(int32_t code)
{
    const int32_t limit = (int32_t)((PM_ADC_FULL_SCALE * (long)PM_ADC_RANGE_PCT) / 100L);

    return (code > -limit) && (code < limit);
}

bool bridge_cal_valid(const struct bridge_cal *cal)
{
    if (!(cal->slope_unm > 0.0f) || !isfinite(cal->slope_unm)) {
        return false;
    }
    if (!bridge_code_in_range(cal->zero_code)) {
        return false;
    }
    if (!isfinite(cal->k1) || !isfinite(cal->k2) || !isfinite(cal->k3)) {
        return false;
    }
    if (!isfinite(cal->t0_c) || (cal->t0_c < -40.0f) || (cal->t0_c > 85.0f)) {
        return false;
    }
    return true;
}
