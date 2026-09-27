/**
 * @file calib.h
 * @brief The three calibrations: zero, slope and temperature (docs/06, Calibração)
 *
 * Zero: the code of the unloaded bridge, accepted only when it stands
 * still. Slope: known masses hung from the pedal with the arm horizontal,
 * a least-squares line through the origin, with the residual and the
 * hysteresis reported. Temperature: zero and slope repeated at several
 * temperatures, fitted to the model of bridge_calc.h.
 */

#ifndef CALIB_H
#define CALIB_H

#include <stdbool.h>
#include <stdint.h>

#include "model/bridge_calc.h"
#include "model/pm_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ---------------------------------------------------------------- zero */

/** Samples the zero needs (docs/06: 64) */
#define CALIB_ZERO_SAMPLES      64U
/** Largest standard deviation of a zero that stands still, counts */
#define CALIB_ZERO_STDDEV_MAX   4.0f
/** A zero beyond this fraction of full scale is a bad bridge, percent */
#define CALIB_ZERO_RANGE_PCT    20U

struct calib_zero {
    uint16_t n;
    float mean;             /**< running mean (Welford) */
    float m2;               /**< running sum of squares of differences */
    int32_t min;
    int32_t max;
};

void calib_zero_reset(struct calib_zero *z);
void calib_zero_add(struct calib_zero *z, int32_t code);

/**
 * @brief The zero, once enough samples are in
 *
 * @return PM_ENOTREADY before CALIB_ZERO_SAMPLES; PM_EBRIDGE when the mean
 *         is beyond ±20 % of full scale; PM_EUNSTABLE when the standard
 *         deviation exceeds CALIB_ZERO_STDDEV_MAX; PM_OK otherwise
 */
pm_err_t calib_zero_result(const struct calib_zero *z, int32_t *zero_code, float *stddev);

/**
 * @brief Whether a new automatic zero may replace the one in use
 *
 * @param current The zero in use
 * @param candidate The zero just measured
 * @param max_step_counts Largest change accepted at once
 */
bool calib_zero_accept_auto(int32_t current, int32_t candidate, int32_t max_step_counts);

/* --------------------------------------------------------------- slope */

/** Points of a slope calibration (3 to 5 masses, up and down) */
#define CALIB_SLOPE_POINTS      10U

struct calib_slope_pt {
    float dcode;            /**< code minus zero, counts */
    float torque_mnm;
    bool descending;        /**< taken while removing the masses */
};

struct calib_slope {
    struct calib_slope_pt pt[CALIB_SLOPE_POINTS];
    uint8_t n;
};

struct calib_slope_result {
    float slope_unm;        /**< µN·m per count */
    float residual_pct;     /**< largest residual over the largest torque */
    float hysteresis_pct;   /**< largest up/down difference over the largest code */
    uint8_t points;
};

void calib_slope_reset(struct calib_slope *s);

/**
 * @brief Add a point: the code read with the mass on, the zero, the torque
 *
 * @return PM_ERANGE when the table is full or the code is not in range
 */
pm_err_t calib_slope_add(struct calib_slope *s, int32_t code, int32_t zero_code,
                         int32_t torque_mnm, bool descending);

/**
 * @brief Least squares through the origin
 *
 * @return PM_ENOTREADY with fewer than 2 points; PM_EBRIDGE when the codes
 *         do not move with the torque (slope not positive)
 */
pm_err_t calib_slope_fit(const struct calib_slope *s, struct calib_slope_result *r);

/**
 * @brief Torque of a mass hung from the pedal, mN·m
 *
 * tau = m g L cos(phi): @p mass_g the mass, @p length_mm the crank length,
 * @p phi_rad the deviation of the arm from the horizontal.
 */
int32_t calib_torque_from_mass_mnm(uint32_t mass_g, uint16_t length_mm, float phi_rad);

/* --------------------------------------------------------- temperature */

#define CALIB_TEMP_POINTS       8U
/** Smallest temperature span that gives a curve worth keeping, °C */
#define CALIB_TEMP_SPAN_MIN     10.0f

struct calib_temp_pt {
    float temp_c;
    float zero_code;
    float slope_unm;
};

struct calib_temp {
    struct calib_temp_pt pt[CALIB_TEMP_POINTS];
    uint8_t n;
};

void calib_temp_reset(struct calib_temp *t);

/**
 * @return PM_ERANGE when the table is full
 */
pm_err_t calib_temp_add(struct calib_temp *t, float temp_c, float zero_code, float slope_unm);

/**
 * @brief Fit k1, k2 and k3 of the model around the point (t0_c, zero_code, slope_unm)
 *
 * Updates @p cal in place and sets temp_calibrated. The reference point
 * is cal->t0_c, cal->zero_code and cal->slope_unm as they stand.
 *
 * @return PM_ENOTREADY with fewer than 3 points or a span below
 *         CALIB_TEMP_SPAN_MIN; PM_EINVAL when the fit is singular
 */
pm_err_t calib_temp_fit(const struct calib_temp *t, struct bridge_cal *cal);

#ifdef __cplusplus
}
#endif

#endif /* CALIB_H */
