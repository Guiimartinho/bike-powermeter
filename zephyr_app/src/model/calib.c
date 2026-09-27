/**
 * @file calib.c
 * @brief Zero, slope and temperature calibrations (docs/06)
 */

#include <math.h>
#include <string.h>

#include "model/calib.h"

/* ---------------------------------------------------------------- zero */

void calib_zero_reset(struct calib_zero *z)
{
    (void)memset(z, 0, sizeof(*z));
    z->min = INT32_MAX;
    z->max = INT32_MIN;
}

void calib_zero_add(struct calib_zero *z, int32_t code)
{
    if (z->n == UINT16_MAX) {
        return;
    }
    z->n++;

    /* Welford's running mean and variance */
    float x = (float)code;
    float delta = x - z->mean;

    z->mean += delta / (float)z->n;
    z->m2 += delta * (x - z->mean);

    if (code < z->min) {
        z->min = code;
    }
    if (code > z->max) {
        z->max = code;
    }
}

pm_err_t calib_zero_result(const struct calib_zero *z, int32_t *zero_code, float *stddev)
{
    if (z->n < CALIB_ZERO_SAMPLES) {
        return PM_ENOTREADY;
    }

    float sd = sqrtf(z->m2 / (float)(z->n - 1U));
    const float limit = (float)PM_ADC_FULL_SCALE * ((float)CALIB_ZERO_RANGE_PCT / 100.0f);

    *stddev = sd;
    *zero_code = (int32_t)lroundf(z->mean);
    if (fabsf(z->mean) > limit) {
        return PM_EBRIDGE;
    }
    if (sd > CALIB_ZERO_STDDEV_MAX) {
        return PM_EUNSTABLE;
    }
    return PM_OK;
}

bool calib_zero_accept_auto(int32_t current, int32_t candidate, int32_t max_step_counts)
{
    int64_t step = (int64_t)candidate - (int64_t)current;

    if (step < 0) {
        step = -step;
    }
    return step <= (int64_t)max_step_counts;
}

/* --------------------------------------------------------------- slope */

void calib_slope_reset(struct calib_slope *s)
{
    (void)memset(s, 0, sizeof(*s));
}

pm_err_t calib_slope_add(struct calib_slope *s, int32_t code, int32_t zero_code,
                         int32_t torque_mnm, bool descending)
{
    if (s->n >= CALIB_SLOPE_POINTS) {
        return PM_ERANGE;
    }
    if (!bridge_code_in_range(code)) {
        return PM_ERANGE;
    }
    s->pt[s->n].dcode = (float)code - (float)zero_code;
    s->pt[s->n].torque_mnm = (float)torque_mnm;
    s->pt[s->n].descending = descending;
    s->n++;
    return PM_OK;
}

pm_err_t calib_slope_fit(const struct calib_slope *s, struct calib_slope_result *r)
{
    if (s->n < 2U) {
        return PM_ENOTREADY;
    }

    /* least squares through the origin: slope = sum(tau dc) / sum(dc^2) */
    float sxy = 0.0f;
    float sxx = 0.0f;
    float tau_max = 0.0f;
    float dc_max = 0.0f;

    for (uint8_t i = 0U; i < s->n; i++) {
        sxy += s->pt[i].torque_mnm * s->pt[i].dcode;
        sxx += s->pt[i].dcode * s->pt[i].dcode;
        if (fabsf(s->pt[i].torque_mnm) > tau_max) {
            tau_max = fabsf(s->pt[i].torque_mnm);
        }
        if (fabsf(s->pt[i].dcode) > dc_max) {
            dc_max = fabsf(s->pt[i].dcode);
        }
    }
    if (!(sxx > 0.0f) || !(sxy > 0.0f)) {
        return PM_EBRIDGE;
    }

    float slope_mnm = sxy / sxx;          /* mN·m per count */
    float worst = 0.0f;

    for (uint8_t i = 0U; i < s->n; i++) {
        float res = fabsf(s->pt[i].torque_mnm - (slope_mnm * s->pt[i].dcode));

        if (res > worst) {
            worst = res;
        }
    }

    /* hysteresis: the same torque read on the way up and on the way down */
    float hyst = 0.0f;

    for (uint8_t i = 0U; i < s->n; i++) {
        for (uint8_t j = 0U; j < s->n; j++) {
            if (s->pt[i].descending || !s->pt[j].descending) {
                continue;
            }
            float tol = 0.01f * fmaxf(fabsf(s->pt[i].torque_mnm), 1.0f);

            if (fabsf(s->pt[i].torque_mnm - s->pt[j].torque_mnm) <= tol) {
                float d = fabsf(s->pt[i].dcode - s->pt[j].dcode);

                if (d > hyst) {
                    hyst = d;
                }
            }
        }
    }

    r->slope_unm = slope_mnm * 1000.0f;
    r->residual_pct = (tau_max > 0.0f) ? (worst / tau_max * 100.0f) : 0.0f;
    r->hysteresis_pct = (dc_max > 0.0f) ? (hyst / dc_max * 100.0f) : 0.0f;
    r->points = s->n;
    return PM_OK;
}

int32_t calib_torque_from_mass_mnm(uint32_t mass_g, uint16_t length_mm, float phi_rad)
{
    /* m [kg] g [m/s^2] L [m] cos(phi) -> N·m; times 1000 -> mN·m */
    float tau = ((float)mass_g / 1000.0f) * PM_GRAVITY * ((float)length_mm / 1000.0f) *
                cosf(phi_rad) * 1000.0f;

    return pm_clamp_i32((int64_t)lroundf(tau));
}

/* --------------------------------------------------------- temperature */

void calib_temp_reset(struct calib_temp *t)
{
    (void)memset(t, 0, sizeof(*t));
}

pm_err_t calib_temp_add(struct calib_temp *t, float temp_c, float zero_code, float slope_unm)
{
    if (t->n >= CALIB_TEMP_POINTS) {
        return PM_ERANGE;
    }
    t->pt[t->n].temp_c = temp_c;
    t->pt[t->n].zero_code = zero_code;
    t->pt[t->n].slope_unm = slope_unm;
    t->n++;
    return PM_OK;
}

pm_err_t calib_temp_fit(const struct calib_temp *t, struct bridge_cal *cal)
{
    if (t->n < 3U) {
        return PM_ENOTREADY;
    }

    float tmin = t->pt[0].temp_c;
    float tmax = tmin;

    for (uint8_t i = 1U; i < t->n; i++) {
        tmin = fminf(tmin, t->pt[i].temp_c);
        tmax = fmaxf(tmax, t->pt[i].temp_c);
    }
    if ((tmax - tmin) < CALIB_TEMP_SPAN_MIN) {
        return PM_ENOTREADY;
    }

    /*
     * zero - c0 = k1 d + k2 d^2 (no intercept: the model passes through the
     * reference point). Normal equations of the two unknowns:
     *   [S2 S3] [k1]   [Sy1]
     *   [S3 S4] [k2] = [Sy2]
     */
    float s2 = 0.0f;
    float s3 = 0.0f;
    float s4 = 0.0f;
    float sy1 = 0.0f;
    float sy2 = 0.0f;
    float ss = 0.0f;        /* for k3: sum d^2 */
    float sr = 0.0f;        /* sum d (s/s0 - 1) */

    for (uint8_t i = 0U; i < t->n; i++) {
        float d = t->pt[i].temp_c - cal->t0_c;
        float y = t->pt[i].zero_code - (float)cal->zero_code;
        float rel = (t->pt[i].slope_unm / cal->slope_unm) - 1.0f;

        s2 += d * d;
        s3 += d * d * d;
        s4 += d * d * d * d;
        sy1 += d * y;
        sy2 += d * d * y;
        ss += d * d;
        sr += d * rel;
    }

    float det = (s2 * s4) - (s3 * s3);

    if (!(fabsf(det) > 1e-6f) || !(ss > 0.0f)) {
        return PM_EINVAL;
    }

    cal->k1 = ((sy1 * s4) - (sy2 * s3)) / det;
    cal->k2 = ((s2 * sy2) - (s3 * sy1)) / det;
    cal->k3 = sr / ss;
    cal->temp_calibrated = true;
    return PM_OK;
}
