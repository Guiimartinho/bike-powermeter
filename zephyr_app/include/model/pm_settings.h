/**
 * @file pm_settings.h
 * @brief The configuration of the meter: limits, defaults, the versioned
 *        blob it is stored and sent as, and the text keys of the
 *        configuration commands (docs/05, Serviço de configuração)
 *
 * The blob is explicit, field by field, little-endian, with the version in
 * front and a CRC-16 at the end: the same bytes go to the settings
 * subsystem of Zephyr and to the configuration characteristic, and the
 * host tests fix them byte by byte. A blob of another version is refused;
 * a migration is written when a version 2 exists.
 */

#ifndef PM_SETTINGS_H
#define PM_SETTINGS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "model/bridge_calc.h"
#include "model/pm_types.h"

#ifdef __cplusplus
extern "C" {
#endif

#define PM_SETTINGS_VERSION         1U
/** Name of the meter, with its terminator ("PM-" and up to 8 characters) */
#define PM_SETTINGS_NAME_LEN        12U
/** Size of the blob of this version */
#define PM_SETTINGS_WIRE_LEN        60U

/* Limits (docs/02, Requisitos) */
#define PM_CRANK_MIN_HALF_MM        200U    /**< 100 mm */
#define PM_CRANK_MAX_HALF_MM        500U    /**< 250 mm */
#define PM_RADIUS_MIN_MM            10U
#define PM_RADIUS_MAX_MM            200U
#define PM_AUTO_ZERO_STEP_MAX       1677721L /**< 20 % of the full scale */

/** The side, as the CPS sensor location */
#define PM_SIDE_LEFT                5U
#define PM_SIDE_RIGHT               6U

struct pm_settings {
    uint16_t crank_length_half_mm;  /**< 0,5 mm, as the CPS carries it */
    uint16_t sensor_radius_mm;      /**< accelerometer to axle */
    uint8_t side;                   /**< PM_SIDE_LEFT or PM_SIDE_RIGHT */
    int8_t tangential_sign;         /**< +1 or -1 */
    struct bridge_cal cal;          /**< slope 0: not calibrated */
    uint16_t sample_rate_sps;       /**< ADS1220 normal mode: 20, 45, 90, 175, 330, 600, 1000 */
    bool auto_zero;                 /**< revise the zero while the crank rests */
    int32_t auto_zero_max_step;     /**< largest auto zero accepted, counts */
    uint16_t ant_device_number;     /**< 0: derived from the radio address at boot */
    uint16_t cal_year;              /**< factory calibration date, 0 0 0 when unset */
    uint8_t cal_month;
    uint8_t cal_day;
    char name[PM_SETTINGS_NAME_LEN];
};

/**
 * @brief The factory defaults: 172,5 mm, 50 mm, left, +1, no calibration, 175 SPS,
 *        auto zero of 0,5 % of the full scale, no ANT number, "PM"
 */
void pm_settings_defaults(struct pm_settings *s);

/**
 * @brief Check every field against its limits
 * @return PM_OK, or PM_EINVAL naming nothing (the command layer reports the key)
 */
pm_err_t pm_settings_validate(const struct pm_settings *s);

/**
 * @brief The bridge has a slope: torque can be reported
 */
bool pm_settings_calibrated(const struct pm_settings *s);

/**
 * @brief Write the blob
 * @return PM_SETTINGS_WIRE_LEN, or 0 when @p buf is too small
 */
size_t pm_settings_serialize(const struct pm_settings *s, uint8_t *buf, size_t len);

/**
 * @brief Read a blob
 * @return PM_OK; PM_EINVAL on a wrong length, version or CRC, or on values out of range
 */
pm_err_t pm_settings_deserialize(const uint8_t *buf, size_t len, struct pm_settings *s);

/**
 * @brief CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF), the one of the blob
 */
uint16_t pm_crc16(const uint8_t *data, size_t len);

/**
 * @brief The i-th text key, or NULL past the last one
 */
const char *pm_settings_key(size_t i);

/**
 * @brief Set one field from its text value, as $CFG,SET does
 * @return PM_OK; PM_EINVAL for an unknown key or a value out of range (nothing changes)
 */
pm_err_t pm_settings_set_text(struct pm_settings *s, const char *key, const char *value);

/**
 * @brief Print one field as text, as $CFG,GET does
 * @return Characters written (without the terminator), 0 for an unknown key or a short buffer
 */
size_t pm_settings_get_text(const struct pm_settings *s, const char *key, char *buf, size_t len);

#ifdef __cplusplus
}
#endif

#endif /* PM_SETTINGS_H */
