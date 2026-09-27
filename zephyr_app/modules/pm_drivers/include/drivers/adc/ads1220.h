/**
 * @file ads1220.h
 * @brief TI ADS1220 bridge converter (ti,ads1220): the calls of the sample
 *        service (docs/04, Drivers)
 *
 * The converter runs the bridge in continuous conversion at the configured
 * rate; DRDY falls at each result and the callback below runs in the GPIO
 * interrupt, where it may only signal a thread. The thread reads the code
 * with ads1220_read(). Between rides the sample service powers the device
 * down (400 nA) and reads the reference monitor before each burst.
 *
 * Commands, registers and timing from SBAS501D (revision May 2026).
 * Not tested on a converter yet.
 */

#ifndef DRIVERS_ADC_ADS1220_H
#define DRIVERS_ADC_ADS1220_H

#include <stdbool.h>
#include <stdint.h>

#include <zephyr/device.h>

#ifdef __cplusplus
extern "C" {
#endif

/** What the monitor of the multiplexer measures (CONFIG0 MUX 1100b and 1101b) */
enum ads1220_monitor {
    ADS1220_MON_REF = 0,    /**< (VREFPx - VREFNx) / 4 */
    ADS1220_MON_AVDD        /**< (AVDD - AVSS) / 4 */
};

/** Called from the DRDY interrupt: signal a thread and return */
typedef void (*ads1220_drdy_cb_t)(const struct device *dev, void *user);

/** @brief RESET, then the configuration of the devicetree */
int ads1220_reset(const struct device *dev);

/**
 * @brief Continuous conversions at the configured rate, from START/SYNC
 *
 * The first result comes 210 tCLK plus one conversion later; DRDY falls at
 * each one.
 */
int ads1220_start_continuous(const struct device *dev);

/**
 * @brief One conversion at the configured rate
 *
 * DRDY falls when it is done; the device then waits in its low-power state.
 */
int ads1220_start_single(const struct device *dev);

/** @brief POWERDOWN: everything off after the current conversion, registers kept */
int ads1220_powerdown(const struct device *dev);

/**
 * @brief Read the last result, 24-bit two's complement sign-extended
 *
 * Call after DRDY fell (or after a single conversion): the bytes are read
 * directly, without RDATA, with DIN low.
 */
int ads1220_read(const struct device *dev, int32_t *code);

/**
 * @brief Measure a monitor voltage with one conversion, then restore the input
 *
 * The device uses the internal 2,048 V reference and gain 1 for the
 * monitor (8.3.11): the code is (V / 4) / 2,048 V of the full scale.
 * Blocks for one conversion at the configured rate (up to 60 ms at 20 SPS).
 *
 * @param[out] mv The voltage in millivolts
 */
int ads1220_read_monitor(const struct device *dev, enum ads1220_monitor what, uint16_t *mv);

/**
 * @brief Install the DRDY callback (NULL removes it) and enable the interrupt
 */
int ads1220_drdy_callback_set(const struct device *dev, ads1220_drdy_cb_t cb, void *user);

/** @brief Whether DRDY is low right now */
bool ads1220_data_ready(const struct device *dev);

/** @brief The data rate the device is configured for, SPS */
uint16_t ads1220_data_rate(const struct device *dev);

#ifdef __cplusplus
}
#endif

#endif /* DRIVERS_ADC_ADS1220_H */
