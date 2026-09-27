/**
 * @file dfu.h
 * @brief Firmware update over Bluetooth (mcumgr SMP)
 *
 * mcumgr does the transfer and MCUboot does the swap; what is here is the
 * part that belongs to this device: confirm the image that is running so
 * MCUboot stops reverting it, publish how the upload goes on chan_dfu, and
 * refuse an upload while the crank turns or with the battery below 30 %
 * (docs/04, Atualização). Without CONFIG_MCUMGR every function does nothing.
 */

#ifndef RF_DFU_H
#define RF_DFU_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/** Battery needed to accept an update, percent */
#define DFU_MIN_SOC_PCT     30U

/** @brief Register the mcumgr callbacks and confirm the running image */
int rf_dfu_init(void);

/** @brief What the device is doing, for the refusal rule */
void rf_dfu_set_conditions(bool moving, uint8_t soc_pct, bool vbus);

/** @brief Whether an update is being received or waits for the reset */
bool rf_dfu_busy(void);

#ifdef __cplusplus
}
#endif

#endif /* RF_DFU_H */
