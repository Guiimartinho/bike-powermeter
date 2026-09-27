/**
 * @file bridge_calc.h
 * @brief From the converter code to torque (docs/06, Da ponte ao torque)
 *
 * The bridge is read ratiometrically, so the code is proportional to the
 * strain and independent of the excitation voltage. Torque is
 *
 *     tau = s(T) * (c - c0(T))
 *
 * with c the 24-bit code, c0 the zero, s the slope in µN·m per count and T
 * the bridge temperature. The zero and the slope carry the temperature
 * model of docs/06 (Temperatura):
 *
 *     c0(T) = c0 + k1 (T - T0) + k2 (T - T0)^2
 *     s(T)  = s [1 + k3 (T - T0)]
 *
 * Before the temperature procedure the k's are zero and the model says so.
 */

#ifndef BRIDGE_CALC_H
#define BRIDGE_CALC_H

#include <stdbool.h>
#include <stdint.h>

#include "model/pm_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/** Largest torque the model reports, mN·m (5000 N·m: far above any pedal) */
#define BRIDGE_TORQUE_MAX_MNM   5000000L

/** Calibration constants of one bridge */
struct bridge_cal {
    int32_t zero_code;      /**< c0 at T0, counts */
    float slope_unm;        /**< s at T0, µN·m per count; positive */
    float t0_c;             /**< temperature of the slope calibration, °C */
    float k1;               /**< counts per °C */
    float k2;               /**< counts per °C² */
    float k3;               /**< 1/°C on the slope */
    bool temp_calibrated;   /**< the k's come from the temperature procedure */
};

/** Median-of-three filter against single-sample spikes (docs/06, Amostragem) */
struct bridge_filter {
    int32_t buf[3];
    uint8_t n;              /**< samples held, up to 3 */
    uint8_t idx;            /**< next slot */
};

/**
 * @brief Forget every sample of the filter
 */
void bridge_filter_reset(struct bridge_filter *f);

/**
 * @brief Push a code and get the median of the last three
 *
 * @return true when three samples are held and @p out is the median
 */
bool bridge_filter_median3(struct bridge_filter *f, int32_t code, int32_t *out);

/**
 * @brief Zero at a temperature, counts (float: the k's are fractional)
 */
float bridge_zero_at(const struct bridge_cal *cal, float temp_c);

/**
 * @brief Slope at a temperature, µN·m per count
 */
float bridge_slope_at(const struct bridge_cal *cal, float temp_c);

/**
 * @brief Torque from a code, mN·m, saturated at ±BRIDGE_TORQUE_MAX_MNM
 */
int32_t bridge_torque_mnm(const struct bridge_cal *cal, int32_t code, float temp_c);

/**
 * @brief A code a loaded bridge can produce: within ±80 % of full scale
 */
bool bridge_code_in_range(int32_t code);

/**
 * @brief The constants make sense: positive finite slope, zero in range,
 *        finite k's, plausible T0
 */
bool bridge_cal_valid(const struct bridge_cal *cal);

#ifdef __cplusplus
}
#endif

#endif /* BRIDGE_CALC_H */
