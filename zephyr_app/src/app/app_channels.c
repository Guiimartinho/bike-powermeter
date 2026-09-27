/**
 * @file app_channels.c
 * @brief Definition of the zbus channels (docs/04, Eventos)
 */

#include <string.h>

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/zbus/zbus.h>

#include "app/app_channels.h"

LOG_MODULE_REGISTER(app_chan, CONFIG_LOG_DEFAULT_LEVEL);

/*
 * Publishers wait at most this long for a channel another thread is
 * publishing on: the listeners only copy the message into a queue.
 */
#define APP_PUB_TIMEOUT     K_MSEC(20)

ZBUS_CHAN_DEFINE(chan_torque, struct app_torque, NULL, NULL, ZBUS_OBSERVERS_EMPTY,
                 ZBUS_MSG_INIT(0));
ZBUS_CHAN_DEFINE(chan_temp, struct app_temp, NULL, NULL, ZBUS_OBSERVERS_EMPTY, ZBUS_MSG_INIT(0));
ZBUS_CHAN_DEFINE(chan_excitation, struct app_excitation, NULL, NULL, ZBUS_OBSERVERS_EMPTY,
                 ZBUS_MSG_INIT(0));
ZBUS_CHAN_DEFINE(chan_crank, struct app_crank, NULL, NULL, ZBUS_OBSERVERS_EMPTY, ZBUS_MSG_INIT(0));
ZBUS_CHAN_DEFINE(chan_motion_state, struct app_motion_state, NULL, NULL, ZBUS_OBSERVERS_EMPTY,
                 ZBUS_MSG_INIT(0));
ZBUS_CHAN_DEFINE(chan_power, struct app_power, NULL, NULL, ZBUS_OBSERVERS_EMPTY, ZBUS_MSG_INIT(0));
ZBUS_CHAN_DEFINE(chan_vector, struct app_vector, NULL, NULL, ZBUS_OBSERVERS_EMPTY,
                 ZBUS_MSG_INIT(0));
ZBUS_CHAN_DEFINE(chan_cmd, struct app_cmd_msg, NULL, NULL, ZBUS_OBSERVERS_EMPTY, ZBUS_MSG_INIT(0));
ZBUS_CHAN_DEFINE(chan_cmd_result, struct app_cmd_result, NULL, NULL, ZBUS_OBSERVERS_EMPTY,
                 ZBUS_MSG_INIT(0));
ZBUS_CHAN_DEFINE(chan_system_state, struct app_system_state, NULL, NULL, ZBUS_OBSERVERS_EMPTY,
                 ZBUS_MSG_INIT(0));
ZBUS_CHAN_DEFINE(chan_battery, struct app_battery, NULL, NULL, ZBUS_OBSERVERS_EMPTY,
                 ZBUS_MSG_INIT(0));
ZBUS_CHAN_DEFINE(chan_vbus, struct app_vbus, NULL, NULL, ZBUS_OBSERVERS_EMPTY, ZBUS_MSG_INIT(0));
ZBUS_CHAN_DEFINE(chan_health, struct app_health, NULL, NULL, ZBUS_OBSERVERS_EMPTY,
                 ZBUS_MSG_INIT(0));
ZBUS_CHAN_DEFINE(chan_settings, struct app_settings_msg, NULL, NULL, ZBUS_OBSERVERS_EMPTY,
                 ZBUS_MSG_INIT(0));
ZBUS_CHAN_DEFINE(chan_dfu, struct app_dfu, NULL, NULL, ZBUS_OBSERVERS_EMPTY, ZBUS_MSG_INIT(0));

int app_publish(const struct zbus_channel *chan, const void *msg)
{
    int err = zbus_chan_pub(chan, msg, APP_PUB_TIMEOUT);

    if (err != 0) {
        LOG_WRN("publish on %s failed: %d", zbus_chan_name(chan), err);
    }
    return err;
}

void app_cmd_reply(uint8_t id, uint8_t source, uint8_t err, int32_t value, const char *text)
{
    struct app_cmd_result r = {
        .id = id,
        .source = source,
        .err = err,
        .value = value,
    };

    if (text != NULL) {
        (void)strncpy(r.text, text, sizeof(r.text) - 1U);
    }
    (void)app_publish(&chan_cmd_result, &r);
}
