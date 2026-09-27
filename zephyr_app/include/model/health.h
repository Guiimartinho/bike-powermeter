/**
 * @file health.h
 * @brief The health flags of the sensor chain (docs/06, Saúde do sensor)
 *
 * Every rule is fed with what it watches and keeps its own timing; the
 * flags are read whenever a status is sent. Flags that stop the
 * measurement (a bridge that is not a bridge, an excitation that is not
 * there, an accelerometer that is silent, a meter never calibrated) are
 * told apart from the warnings by HEALTH_FATAL_MASK.
 */

#ifndef HEALTH_H
#define HEALTH_H

#include <stdbool.h>
#include <stdint.h>

#include "model/pm_types.h"

#ifdef __cplusplus
extern "C" {
#endif

#define HEALTH_BRIDGE_OPEN      0x0001U /**< code beyond ±80 % of the full scale with the excitation on */
#define HEALTH_BRIDGE_STUCK     0x0002U /**< the same code for stuck_ms with the excitation on */
#define HEALTH_EXCITATION       0x0004U /**< reference outside nominal ± tolerance */
#define HEALTH_IMU_STALE        0x0008U /**< no accelerometer sample for imu_stale_ms */
#define HEALTH_IMU_RANGE        0x0010U /**< |a| outside imu_min_g..imu_max_g for imu_range_ms */
#define HEALTH_TEMP_RANGE       0x0020U /**< bridge temperature outside temp_min..temp_max */
#define HEALTH_ZERO_DRIFT       0x0040U /**< the zero moved beyond the auto zero step since calibration */
#define HEALTH_NOT_CALIBRATED   0x0080U /**< no slope: torque cannot be reported */

/** The flags under which no power is reported */
#define HEALTH_FATAL_MASK                                                                    \
    (HEALTH_BRIDGE_OPEN | HEALTH_BRIDGE_STUCK | HEALTH_EXCITATION | HEALTH_IMU_STALE |       \
     HEALTH_NOT_CALIBRATED)

struct health_cfg {
    uint16_t excitation_nominal_mv; /**< 3000 */
    uint8_t excitation_tol_pct;     /**< 10 */
    uint32_t stuck_ms;              /**< 2000 */
    uint32_t imu_stale_ms;          /**< 500 */
    uint32_t imu_range_ms;          /**< 1000 */
    float imu_min_g;                /**< 0,5 */
    float imu_max_g;                /**< 6 */
    float temp_min_c;               /**< -20 */
    float temp_max_c;               /**< 70 */
};

struct health {
    struct health_cfg cfg;
    uint16_t flags;
    /* bridge */
    bool have_code;
    int32_t last_code;
    uint32_t code_since_ms;
    /* accelerometer */
    bool have_imu;
    uint32_t last_imu_ms;
    bool imu_bad;
    uint32_t imu_bad_since_ms;
};

/** The docs/06 configuration */
struct health_cfg health_cfg_default(void);

/** Start with every flag clear except HEALTH_NOT_CALIBRATED */
void health_init(struct health *h, const struct health_cfg *cfg);

/** A code of the converter, with the state of the excitation switch */
void health_bridge(struct health *h, int32_t code, bool excitation_on, uint32_t now_ms);

/** The reference voltage read by the converter's monitor, mV */
void health_excitation(struct health *h, uint16_t ref_mv);

/** An accelerometer sample: the magnitude of the vector, in g */
void health_imu(struct health *h, float mag_g, uint32_t now_ms);

/** The bridge temperature, °C */
void health_temperature(struct health *h, float temp_c);

/** The zero in use against the one of the calibration; max_step 0 disables the rule */
void health_zero(struct health *h, int32_t zero_now, int32_t zero_cal, int32_t max_step);

/** Whether the slope is known */
void health_calibrated(struct health *h, bool calibrated);

/** Time passes: the accelerometer silence is judged here */
void health_tick(struct health *h, uint32_t now_ms);

uint16_t health_flags(const struct health *h);

/** No fatal flag */
bool health_can_measure(const struct health *h);

#ifdef __cplusplus
}
#endif

#endif /* HEALTH_H */
