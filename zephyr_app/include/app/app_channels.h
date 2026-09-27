/**
 * @file app_channels.h
 * @brief zbus channels of the application (docs/04, Eventos)
 *
 * The channels carry copies: whoever publishes does not wait for whoever
 * reads. Each service adds its own listener to the channels it needs with
 * ZBUS_CHAN_ADD_OBS() in its own file, so the channel list stays free of
 * who listens.
 */

#ifndef APP_CHANNELS_H
#define APP_CHANNELS_H

#include <zephyr/zbus/zbus.h>

#include "app/app_events.h"

ZBUS_CHAN_DECLARE(chan_torque,          /* struct app_torque: sample -> compute */
                  chan_temp,            /* struct app_temp: sample -> compute */
                  chan_excitation,      /* struct app_excitation: sample -> compute */
                  chan_crank,           /* struct app_crank: motion -> compute */
                  chan_motion_state,    /* struct app_motion_state: motion -> power, radio */
                  chan_power,           /* struct app_power: compute -> radio, usb */
                  chan_vector,          /* struct app_vector: compute -> radio */
                  chan_cmd,             /* struct app_cmd_msg: app_cmd -> compute, power */
                  chan_cmd_result,      /* struct app_cmd_result: compute, power -> radio, usb */
                  chan_system_state,    /* struct app_system_state: power -> all */
                  chan_battery,         /* struct app_battery: power -> radio, usb */
                  chan_vbus,            /* struct app_vbus: usb -> power */
                  chan_health,          /* struct app_health: compute -> radio */
                  chan_settings,        /* struct app_settings_msg: app -> all */
                  chan_dfu);            /* struct app_dfu: radio -> power, usb */

/**
 * @brief Publish a message, logging a failure
 *
 * Every channel is published without waiting long: a service never blocks
 * on another one. A failure means the channel is being read at that
 * instant, which the next sample covers.
 */
int app_publish(const struct zbus_channel *chan, const void *msg);

/**
 * @brief Publish a command result
 */
void app_cmd_reply(uint8_t id, uint8_t source, uint8_t err, int32_t value, const char *text);

#endif /* APP_CHANNELS_H */
