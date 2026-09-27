/**
 * @file crank_angle.c
 * @brief Crank angle, angular velocity, revolutions and rest (docs/06)
 */

#include <math.h>
#include <string.h>

#include "model/crank_angle.h"

struct crank_cfg crank_cfg_default(void)
{
    struct crank_cfg cfg = {
        .radius_m = 0.050f,
        .tangential_sign = 1.0f,
        .omega_max = 25.0f,
        .cross_hyst = 0.5f,
        .no_cross_ms = 2000U,
        .still_g_tol = 0.10f,
        .still_omega = 0.3f,
        .still_ms = 2000U,
    };

    return cfg;
}

void crank_init(struct crank_state *st, const struct crank_cfg *cfg)
{
    (void)memset(st, 0, sizeof(*st));
    st->cfg = (cfg != NULL) ? *cfg : crank_cfg_default();
}

float crank_wrap_2pi(float angle)
{
    float a = fmodf(angle, PM_TWO_PI);

    if (a < 0.0f) {
        a += PM_TWO_PI;
    }
    return a;
}

float crank_cadence_rpm(float omega_rad_s)
{
    return fabsf(omega_rad_s) * 60.0f / PM_TWO_PI;
}

/** The shortest way round between two angles of [0, 2pi) */
static float wrap_pi(float d)
{
    if (d > PM_PI) {
        d -= PM_TWO_PI;
    } else if (d < -PM_PI) {
        d += PM_TWO_PI;
    } else {
        /* already the short way */
    }
    return d;
}

/** The angle of a sample, with the centripetal term of @p omega removed */
static float angle_of(const struct crank_state *st, float u, float a_r, float omega)
{
    float radial = a_r - (omega * omega * st->cfg.radius_m);

    return crank_wrap_2pi(atan2f(-u, radial));
}

/** The rest rule of docs/06: |a| around g and omega small, for still_ms */
static bool update_rest(struct crank_state *st, float a_t, float a_r, float a_l, uint32_t now_ms)
{
    float mag = sqrtf((a_t * a_t) + (a_r * a_r) + (a_l * a_l));
    float lo = PM_GRAVITY * (1.0f - st->cfg.still_g_tol);
    float hi = PM_GRAVITY * (1.0f + st->cfg.still_g_tol);
    bool quiet = (mag >= lo) && (mag <= hi) && (fabsf(st->omega) < st->cfg.still_omega);

    if (!quiet) {
        st->still_candidate = false;
        st->stationary = false;
        return false;
    }
    if (!st->still_candidate) {
        st->still_candidate = true;
        st->still_since_ms = now_ms;
    }
    if ((now_ms - st->still_since_ms) >= st->cfg.still_ms) {
        st->stationary = true;
    }
    return st->stationary;
}

/** The first sample, or a sample on the same tick as the last: only the angle */
static void restart(struct crank_state *st, float u, float a_r, uint32_t now_ms, float theta)
{
    st->theta = theta;
    st->last_ms = now_ms;
    st->last_u = u;
    st->last_ar = a_r;
    st->have_last = true;
    st->armed_pos = (u < -st->cfg.cross_hyst);
    st->armed_neg = (u > st->cfg.cross_hyst);
}

/**
 * A crossing of the tangential axis between the last sample and this one:
 * half a turn since the previous crossing.
 *
 * @param rising u went from below 0 to 0 or above
 * @param u This sample's tangential axis
 * @param a_r This sample's radial axis
 * @param dt_ms Time since the last sample
 * @param[out] omega_changed The angular velocity was re-estimated
 * @return true when this crossing is the bottom passed forward
 */
static bool handle_crossing(struct crank_state *st, bool rising, float u, float a_r,
                            uint32_t dt_ms, bool *omega_changed)
{
    float span = u - st->last_u;
    float frac_ms = (span != 0.0f) ? ((float)dt_ms * (-st->last_u) / span) : 0.0f;
    bool bottom;
    bool forward;

    *omega_changed = false;
    if (st->have_cross) {
        float half_ms = (float)(st->last_ms - st->cross_ms) + frac_ms - st->cross_frac_ms;
        float t_min_ms = PM_PI / st->cfg.omega_max * 1000.0f;

        if (half_ms < t_min_ms) {
            /* two crossings closer than the fastest crank allows: noise */
            return false;
        }
        st->omega = PM_PI / (half_ms / 1000.0f);
        *omega_changed = true;
    }
    st->have_cross = true;
    st->cross_ms = st->last_ms;
    st->cross_frac_ms = frac_ms;

    /* top or bottom by the corrected radial axis, forward by the way it crossed */
    bottom = (a_r - (st->omega * st->omega * st->cfg.radius_m)) < 0.0f;
    forward = (rising == bottom);
    if (!forward) {
        st->omega = -st->omega;
    }
    if (forward && bottom) {
        st->rev_count++;
        return true;
    }
    return false;
}

void crank_update(struct crank_state *st, float a_t, float a_r, float a_l, uint32_t uptime_ms,
                  struct crank_out *out)
{
    float u = st->cfg.tangential_sign * a_t;
    float theta;
    float prev_theta;
    float dtheta;
    uint32_t dt_ms;

    (void)memset(out, 0, sizeof(*out));

    if (!st->have_last || (uptime_ms == st->last_ms)) {
        theta = angle_of(st, u, a_r, st->omega);
        restart(st, u, a_r, uptime_ms, theta);
        out->angle_rad = theta;
        out->omega_rad_s = st->omega;
        out->stationary = update_rest(st, a_t, a_r, a_l, uptime_ms);
        return;
    }

    /* no crossing for a while: the crank stopped turning, forget the last one */
    if (st->have_cross && ((uptime_ms - st->cross_ms) > st->cfg.no_cross_ms)) {
        st->have_cross = false;
        st->omega = 0.0f;
    }

    dt_ms = uptime_ms - st->last_ms;
    theta = angle_of(st, u, a_r, st->omega);
    prev_theta = st->theta;
    dtheta = wrap_pi(theta - prev_theta);
    if ((fabsf(dtheta) * 1000.0f / (float)dt_ms) > st->cfg.omega_max) {
        /* a jump, not a crank: the sample is discarded whole */
        out->angle_rad = st->theta;
        out->omega_rad_s = st->omega;
        out->stationary = update_rest(st, a_t, a_r, a_l, uptime_ms);
        return;
    }

    /* crossings of the tangential axis, armed beyond ± hyst against noise */
    if ((st->armed_pos && (u >= 0.0f)) || (st->armed_neg && (u < 0.0f))) {
        bool rising = st->armed_pos;
        bool changed;

        st->armed_pos = false;
        st->armed_neg = false;
        out->revolution = handle_crossing(st, rising, u, a_r, dt_ms, &changed);
        if (changed) {
            /* both angles with the new angular velocity, so dtheta is consistent */
            theta = angle_of(st, u, a_r, st->omega);
            prev_theta = angle_of(st, st->last_u, st->last_ar, st->omega);
            dtheta = wrap_pi(theta - prev_theta);
        }
    }
    if (u < -st->cfg.cross_hyst) {
        st->armed_pos = true;
    } else if (u > st->cfg.cross_hyst) {
        st->armed_neg = true;
    } else {
        /* between the thresholds: keep what was armed */
    }

    st->theta = theta;
    st->last_ms = uptime_ms;
    st->last_u = u;
    st->last_ar = a_r;
    out->valid = true;
    out->angle_rad = theta;
    out->omega_rad_s = st->omega;
    out->dtheta_rad = dtheta;
    out->stationary = update_rest(st, a_t, a_r, a_l, uptime_ms);
}
