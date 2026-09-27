/**
 * @file rev_power.h
 * @brief Power per revolution, and the accumulators of the protocols
 *        (docs/06, Potência por volta)
 *
 * Each sample brings a torque and the angle travelled since the previous
 * one; the work of the revolution is the sum of torque times angle, and
 * the power is that work over the period. Torque effectiveness and pedal
 * smoothness come from the same sums. The accumulators wrap as the radio
 * characteristics do (uint16), and the receiver handles the wrap.
 */

#ifndef REV_POWER_H
#define REV_POWER_H

#include <stdbool.h>
#include <stdint.h>

#include "model/pm_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/** Fewer samples than this do not make a revolution (a glitch of the angle) */
#define REV_MIN_SAMPLES         4U
/** Shortest and longest revolution accepted, ms (600 rpm and 10 rpm) */
#define REV_MIN_PERIOD_MS       100U
#define REV_MAX_PERIOD_MS       6000U

struct rev_power_cfg {
    bool single_side;       /**< one crank measured: power is doubled */
    uint8_t balance_pct;    /**< pedal power balance declared (50 with one side) */
    uint32_t zero_after_ms; /**< no revolution for this long: 0 W, 0 rpm (3000) */
};

/** Result of a closed revolution, in the units of the radio */
struct rev_power_out {
    uint16_t power_w;           /**< instantaneous power of the revolution */
    float cadence_rpm;
    uint8_t te_pct;             /**< torque effectiveness, 0 to 100 */
    uint8_t ps_pct;             /**< pedal smoothness, 0 to 100 */
    uint8_t balance_pct;
    uint16_t torque_acc_1_32;   /**< accumulated torque, 1/32 N·m, wraps */
    uint16_t rev_count;         /**< cumulative crank revolutions, wraps */
    uint16_t last_event_1024;   /**< time of the last revolution, 1/1024 s, wraps */
    uint16_t energy_kj;         /**< accumulated energy, kJ, wraps */
};

struct rev_power {
    struct rev_power_cfg cfg;
    /* the revolution in progress */
    float work_j;
    float work_pos_j;
    float work_neg_j;
    float peak_w;
    float period_s;
    uint16_t samples;
    /* accumulators */
    float torque_acc_nm;        /**< running sum of the mean torque of each revolution */
    float energy_j;
    uint16_t rev_count;
    uint16_t last_event_1024;
    uint32_t last_rev_ms;
    bool have_rev;
    struct rev_power_out last;
};

/**
 * @brief Default configuration: one side, balance 50 %, zero after 3 s
 */
struct rev_power_cfg rev_power_cfg_default(void);

void rev_power_init(struct rev_power *rp, const struct rev_power_cfg *cfg);

/**
 * @brief Add a sample to the revolution in progress
 *
 * @param torque_mnm Torque at the sample, mN·m
 * @param dtheta_rad Angle travelled since the previous sample, rad
 * @param dt_ms Time since the previous sample, ms
 * @param omega_rad_s Angular velocity at the sample, rad/s (for the peak power)
 */
void rev_power_feed(struct rev_power *rp, int32_t torque_mnm, float dtheta_rad, uint32_t dt_ms,
                    float omega_rad_s);

/**
 * @brief Close the revolution at the bottom of the stroke
 *
 * @param uptime_ms Time of the revolution event
 * @param out Filled on PM_OK
 * @return PM_OK, or PM_EINVAL when the revolution is discarded (too few
 *         samples, too short or too long); the sums restart either way
 */
pm_err_t rev_power_close(struct rev_power *rp, uint32_t uptime_ms, struct rev_power_out *out);

/**
 * @brief The values to report now (the 1 Hz notification)
 *
 * The last revolution, or zeros once no revolution closed for
 * cfg.zero_after_ms; the accumulators always carry on.
 */
void rev_power_status(const struct rev_power *rp, uint32_t now_ms, struct rev_power_out *out);

#ifdef __cplusplus
}
#endif

#endif /* REV_POWER_H */
