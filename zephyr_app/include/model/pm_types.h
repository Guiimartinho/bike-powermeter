/**
 * @file pm_types.h
 * @brief Units, limits and error codes shared by the model modules
 *
 * The model is plain C: no Zephyr types, so the same code runs on the
 * board and in the host tests. Physical quantities travel as integers in
 * the units the radio protocols use where one exists (1/32 N·m, 1/1024 s,
 * 1/2 mm), and as float where the maths needs it (angles, slopes).
 */

#ifndef PM_TYPES_H
#define PM_TYPES_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/** Result of a model call */
typedef enum {
    PM_OK = 0,          /**< done */
    PM_EINVAL,          /**< an argument is out of its range */
    PM_ENOTREADY,       /**< not enough data yet */
    PM_ERANGE,          /**< a value left the range the hardware can deliver */
    PM_EUNSTABLE,       /**< the data moved while it had to stand still */
    PM_EBRIDGE,         /**< the bridge looks open, shorted or saturated */
    PM_ESTATE           /**< the call does not fit the current state */
} pm_err_t;

/** Positive full scale of the 24-bit converter, in counts (2^23) */
#define PM_ADC_FULL_SCALE       8388608L

/** A code beyond this fraction of the full scale is not a bridge under load */
#define PM_ADC_RANGE_PCT        80U

/** Gravity, m/s^2 */
#define PM_GRAVITY              9.80665f

/** Two pi, as float */
#define PM_TWO_PI               6.28318530718f

/** Pi, as float */
#define PM_PI                   3.14159265359f

/**
 * @brief Milliseconds of uptime to the 1/1024 s clock of the protocols
 *
 * Both protocols carry event times as uint16 in 1/1024 s, wrapping every
 * 64 s; the receiver handles the wrap. Rounded to the nearest tick.
 */
static inline uint16_t pm_ms_to_1024(uint32_t ms)
{
    return (uint16_t)((((uint64_t)ms * 1024ULL) + 500ULL) / 1000ULL);
}

/**
 * @brief Clamp a 64-bit value to int32
 */
static inline int32_t pm_clamp_i32(int64_t v)
{
    if (v > INT32_MAX) {
        return INT32_MAX;
    }
    if (v < INT32_MIN) {
        return INT32_MIN;
    }
    return (int32_t)v;
}

#ifdef __cplusplus
}
#endif

#endif /* PM_TYPES_H */
