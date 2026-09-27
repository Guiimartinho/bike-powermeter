/**
 * @file ant_bpwr.h
 * @brief ANT+ Bicycle Power, sensor side, on the sdk-ant add-on (docs/05)
 *
 * Built only with CONFIG_ANT (tools/fw/fw.sh with ANT=1). The profile
 * ant_bpwr of the add-on carries the pages (1, 16, 18, 80, 81) and the
 * calibration handshake; this file feeds it from chan_power and turns a
 * calibration request into the zero of the compute service. The channel
 * parameters of the profile come from the add-on's header, never from
 * this repository.
 */

#ifndef RF_ANT_BPWR_H
#define RF_ANT_BPWR_H

#include <stdbool.h>
#include <stdint.h>

#include "app/app_events.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Start the ANT stack, the network key and the sensor channel
 *
 * Call before bt_enable(), as the sdk-ant samples with both radios do.
 *
 * @param device_number The ANT device number (1 to 65535)
 * @param serial The serial number of page 81
 */
int rf_ant_start(uint16_t device_number, uint32_t serial);

/** @brief Feed the pages from a power message */
void rf_ant_update(const struct app_power *p);

/** @brief The zero asked by the display finished */
void rf_ant_calib_result(bool ok, int16_t value);

#ifdef __cplusplus
}
#endif

#endif /* RF_ANT_BPWR_H */
