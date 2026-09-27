/**
 * @file ble_cps.h
 * @brief The Cycling Power Service of the pod, server side (docs/05)
 *
 * The GATT table with the Measurement, the Feature, the Sensor Location,
 * the Control Point and the Vector. The bytes come from model/cps_encode.c;
 * this file only owns the attributes, the subscriptions and the one
 * outstanding indication of the control point. A control point request
 * reaches the radio service through the callback, in the Bluetooth receive
 * thread: it decides, and answers with ble_cps_respond().
 */

#ifndef RF_BLE_CPS_H
#define RF_BLE_CPS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "app/app_events.h"
#include "model/cps_encode.h"

#ifdef __cplusplus
extern "C" {
#endif

/** A request of the control point, already decoded */
typedef void (*ble_cps_cp_cb_t)(const struct cps_cp_req *req);

/** @brief Keep the callback of the control point; the table is static */
void ble_cps_init(ble_cps_cp_cb_t cb);

/** @brief The Sensor Location value (CPS_LOC_LEFT_CRANK or RIGHT) */
void ble_cps_set_location(uint8_t location);

/** @brief The content mask set by the control point */
uint16_t ble_cps_mask(void);
void ble_cps_set_mask(uint16_t mask);

/** @brief Notify a measurement to every subscriber; -ENOTCONN when nobody listens */
int ble_cps_notify_measurement(const struct app_power *p);

/** @brief Notify the vector of a revolution; -ENOTCONN when nobody listens */
int ble_cps_notify_vector(const struct app_vector *v);

/** @brief Indicate a control point response (one at a time) */
int ble_cps_respond(uint8_t req_opcode, uint8_t result, const uint8_t *param, size_t param_len);

#ifdef __cplusplus
}
#endif

#endif /* RF_BLE_CPS_H */
