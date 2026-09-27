/**
 * @file ble_cfg.h
 * @brief The configuration service of the project over GATT (docs/05)
 *
 * Four characteristics under a 128-bit UUID of the project: the command
 * (write), the response (notify), the configuration blob (read, write) and
 * the status (notify). The commands are the lines of model/pm_cmd.c, the
 * same ones the serial port takes; the blob is the one of
 * model/pm_settings.c. The bike computer speaks this service to pair, to
 * set the crank length and to ask for the zero.
 */

#ifndef RF_BLE_CFG_H
#define RF_BLE_CFG_H

#include <stdint.h>

#include "app/app_events.h"

#ifdef __cplusplus
extern "C" {
#endif

/** Size of the status notification */
#define BLE_CFG_STATUS_LEN  16U

/** @brief Nothing to do at start: the table is static; kept for symmetry */
void ble_cfg_init(void);

/** @brief Notify one answer line; -ENOTCONN when nobody listens */
int ble_cfg_send_line(const char *text);

/**
 * @brief Notify the status (docs/05, Serviço de configuração)
 *
 * flags u16, temperature in 1/100 degC i16, code i32, zero i32, reference
 * mV u16, battery percent u8, system state u8: 16 bytes, little-endian.
 */
int ble_cfg_notify_status(const struct app_health *h, uint8_t soc_pct, uint8_t state);

#ifdef __cplusplus
}
#endif

#endif /* RF_BLE_CFG_H */
