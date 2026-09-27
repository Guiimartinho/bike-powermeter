/**
 * @file app_cmd.h
 * @brief What the device does with a command line (docs/05)
 *
 * The lines come from the configuration service over BLE and from the USB
 * serial, and both do the same with them: the configuration ones are
 * answered here at once, the ones that need a service ($ZERO, $SLOPE,
 * $TEMP, $DFU, $SLEEP, $SHIP) go out on chan_cmd and are answered on
 * chan_cmd_result by whoever did them. Everything publishes, so it runs in
 * whichever thread read the characters and never waits for anyone.
 */

#ifndef APP_CMD_H
#define APP_CMD_H

#include <stddef.h>
#include <stdint.h>

#include "app/app_events.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Act on one line
 *
 * @param line The text, with or without its terminator
 * @param len Its length
 * @param source Where it came from, for the answer
 */
void app_cmd_handle(const char *line, size_t len, uint8_t source);

/**
 * @brief Send a command of the firmware itself (the control point, ANT+, auto zero)
 */
void app_cmd_send(enum pm_cmd_id id, uint8_t source);

/**
 * @brief Set the crank length from the control point (0,5 mm units)
 * @return PM_OK, or PM_EINVAL when it is out of range
 */
pm_err_t app_cmd_set_crank_half_mm(uint16_t half_mm);

#ifdef __cplusplus
}
#endif

#endif /* APP_CMD_H */
