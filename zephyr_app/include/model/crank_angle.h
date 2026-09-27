/**
 * @file crank_angle.h
 * @brief Crank angle, angular velocity, revolutions and rest from the
 *        accelerometer (docs/06, Ângulo e cadência)
 *
 * The accelerometer is fixed to the crank arm. Its two in-plane axes read
 * the gravity vector turning once per revolution plus the terms of the
 * motion:
 *
 *     a_t = sign * (-g sin(theta)) + alpha r      tangential
 *     a_r = g cos(theta) + omega^2 r               radial, outward
 *
 * with theta measured from the arm pointing up, r the distance of the
 * sensor from the axle and omega the angular velocity.
 *
 * Two estimates, each from the axis that is clean for it:
 *
 *   - the angular velocity comes from the zero crossings of a_t, which
 *     happen at the top and at the bottom of the stroke whatever the
 *     centripetal term does to a_r: half a turn between two crossings,
 *     with the crossing instant interpolated between the two samples
 *     around it (100 Hz alone would give ±3 % at 90 rpm);
 *   - the angle comes from atan2 of the two axes with the centripetal
 *     term removed using that angular velocity.
 *
 * A crossing tells top from bottom by the sign of the corrected radial
 * axis, and forward from backward by which way a_t crossed. A revolution
 * event fires at the bottom, going forward. Angles in radians, 0 = arm
 * up, growing in the pedalling direction.
 */

#ifndef CRANK_ANGLE_H
#define CRANK_ANGLE_H

#include <stdbool.h>
#include <stdint.h>

#include "model/pm_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/** Tuning of the estimator; crank_cfg_default() fills the docs/06 values */
struct crank_cfg {
    float radius_m;         /**< sensor distance from the axle, m */
    float tangential_sign;  /**< +1 or -1: which way the tangential axis points */
    float omega_max;        /**< above this the sample is discarded, rad/s (25: 240 rpm) */
    float cross_hyst;       /**< a_t must pass ± this to arm a crossing, m/s^2 (0,5) */
    uint32_t no_cross_ms;   /**< no crossing for this long: omega is zero (2000) */
    float still_g_tol;      /**< |a| within g ± this fraction counts as still (0,10) */
    float still_omega;      /**< and omega below this, rad/s (0,3) */
    uint32_t still_ms;      /**< for this long, ms (2000) */
};

/** Estimator state; opaque to the callers, sized here for static allocation */
struct crank_state {
    struct crank_cfg cfg;
    float theta;            /**< last angle, [0, 2pi) */
    float omega;            /**< angular velocity from the crossings, signed, rad/s */
    uint32_t last_ms;       /**< time of the last accepted sample */
    float last_u;           /**< its tangential axis, in the canonical sign */
    float last_ar;          /**< its radial axis */
    bool have_last;
    /* crossings of the tangential axis */
    bool armed_pos;         /**< u went below -hyst: a rise through 0 is a crossing */
    bool armed_neg;         /**< u went above +hyst: a fall through 0 is a crossing */
    bool have_cross;
    uint32_t cross_ms;      /**< sample before the last crossing */
    float cross_frac_ms;    /**< and how far after it the crossing was, ms */
    uint32_t rev_count;     /**< revolutions since init */
    /* rest */
    uint32_t still_since_ms;
    bool still_candidate;
    bool stationary;
};

/** What one sample yields */
struct crank_out {
    float angle_rad;        /**< [0, 2pi), 0 = arm up */
    float omega_rad_s;      /**< signed (negative = backpedalling) */
    float dtheta_rad;       /**< angle travelled since the previous valid sample */
    bool revolution;        /**< the arm passed the bottom, forward */
    bool stationary;        /**< the crank is at rest (docs/06 rule) */
    bool valid;             /**< the sample was used (false: first sample, dt 0, a jump) */
};

/**
 * @brief The docs/06 configuration: r 50 mm, +1, 25 rad/s, 0,5 m/s^2, 2 s, 10 %, 0,3 rad/s, 2 s
 */
struct crank_cfg crank_cfg_default(void);

/**
 * @brief Start from rest, with @p cfg (NULL: the default)
 */
void crank_init(struct crank_state *st, const struct crank_cfg *cfg);

/**
 * @brief Feed one accelerometer sample
 *
 * @param st State
 * @param a_t Tangential acceleration, m/s^2
 * @param a_r Radial acceleration (outward positive), m/s^2
 * @param a_l Lateral acceleration, m/s^2 (only for |a|)
 * @param uptime_ms Time of the sample
 * @param out Result
 */
void crank_update(struct crank_state *st, float a_t, float a_r, float a_l, uint32_t uptime_ms,
                  struct crank_out *out);

/**
 * @brief Cadence of an angular velocity, rpm (absolute value)
 */
float crank_cadence_rpm(float omega_rad_s);

/**
 * @brief Wrap an angle to [0, 2pi)
 */
float crank_wrap_2pi(float angle);

#ifdef __cplusplus
}
#endif

#endif /* CRANK_ANGLE_H */
