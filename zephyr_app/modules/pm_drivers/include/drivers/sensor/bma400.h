/**
 * @file bma400.h
 * @brief Bosch BMA400 accelerometer (bosch,bma400): what the sensor API
 *        does not cover
 *
 * The motion service reads the three axes by the Zephyr sensor API with a
 * data-ready trigger on INT1, at the rate and range of the devicetree.
 * Below are the attributes of this device that the API has no name for:
 * the power mode of ACC_CONFIG0 and the wake-up interrupt of the low
 * power mode, which is what brings the pod out of Sleep and out of
 * System OFF. Register map from BST-BMA400-DS000-14 revision 2.3.
 * Not tested on a sensor yet.
 */

#ifndef DRIVERS_SENSOR_BMA400_H
#define DRIVERS_SENSOR_BMA400_H

#include <zephyr/drivers/sensor.h>

#ifdef __cplusplus
extern "C" {
#endif

/** ACC_CONFIG0 power_mode_conf */
enum bma400_power_mode {
    BMA400_MODE_SLEEP = 0,      /**< 160 nA, no data */
    BMA400_MODE_LOW_POWER = 1,  /**< 25 Hz, 850 nA, the wake-up interrupt */
    BMA400_MODE_NORMAL = 2      /**< the data rate of the devicetree */
};

/** Attributes of this device, after the sensor API ones */
enum bma400_attribute {
    /** enum bma400_power_mode in val1 */
    BMA400_ATTR_POWER_MODE = SENSOR_ATTR_PRIV_START,
    /**
     * Wake-up interrupt on INT1: threshold in milli-g in val1 (0 turns it
     * off), samples that must exceed it (1 to 8) in val2. The device goes
     * to low power mode and returns to normal mode by itself when the
     * interrupt fires (AUTOWAKEUP_1 wkup_int).
     */
    BMA400_ATTR_WAKEUP,
};

/** Trigger of the wake-up interrupt, on top of SENSOR_TRIG_DATA_READY */
#define BMA400_TRIG_WAKEUP  SENSOR_TRIG_MOTION

#ifdef __cplusplus
}
#endif

#endif /* DRIVERS_SENSOR_BMA400_H */
