/**
 * @file app_cmd.c
 * @brief What the device does with a command line (docs/05)
 */

#include <stdio.h>
#include <string.h>

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#include "app/app_channels.h"
#include "app/app_cmd.h"
#include "app/pm_store.h"
#include "app_types.h"
#include "model/pm_cmd.h"

LOG_MODULE_REGISTER(app_cmd, CONFIG_LOG_DEFAULT_LEVEL);

static void reply(uint8_t id, uint8_t source, pm_err_t err, const char *text)
{
    app_cmd_reply(id, source, (uint8_t)err, 0, text);
}

/** $CFG,GET: one key, or every key one answer at a time */
static void cfg_get(const struct pm_cmd *cmd, uint8_t source)
{
    struct pm_settings s;
    char text[APP_CMD_TEXT_LEN];
    char value[32];

    pm_store_get(&s);
    if (cmd->key[0] != '\0') {
        if (pm_settings_get_text(&s, cmd->key, value, sizeof(value)) == 0U) {
            reply(PM_CMD_CFG_GET, source, PM_EINVAL, NULL);
            return;
        }
        (void)snprintf(text, sizeof(text), "%s=%s", cmd->key, value);
        reply(PM_CMD_CFG_GET, source, PM_OK, text);
        return;
    }
    for (size_t i = 0U; pm_settings_key(i) != NULL; i++) {
        const char *key = pm_settings_key(i);

        if (pm_settings_get_text(&s, key, value, sizeof(value)) > 0U) {
            (void)snprintf(text, sizeof(text), "%s=%s", key, value);
            reply(PM_CMD_CFG_GET, source, PM_OK, text);
        }
    }
}

static void cfg_set(const struct pm_cmd *cmd, uint8_t source)
{
    struct pm_settings s;
    pm_err_t err;

    pm_store_get(&s);
    err = pm_settings_set_text(&s, cmd->key, cmd->value);
    if (err == PM_OK) {
        err = pm_store_set(&s, false);
    }
    reply(PM_CMD_CFG_SET, source, err, (err == PM_OK) ? cmd->key : NULL);
}

static void info(uint8_t source)
{
    char text[APP_CMD_TEXT_LEN];

    (void)snprintf(text, sizeof(text), "%s,%s,%s", APP_NAME, APP_VERSION_STR,
                   pm_store_loaded() ? "stored" : "defaults");
    reply(PM_CMD_INFO, source, PM_OK, text);
}

void app_cmd_send(enum pm_cmd_id id, uint8_t source)
{
    struct app_cmd_msg msg = {
        .id = (uint8_t)id,
        .source = source,
    };

    msg.cmd.id = id;
    (void)app_publish(&chan_cmd, &msg);
}

void app_cmd_handle(const char *line, size_t len, uint8_t source)
{
    struct pm_cmd cmd;
    pm_err_t err = pm_cmd_parse(line, len, &cmd);

    if (err != PM_OK) {
        reply(PM_CMD_NONE, source, err, NULL);
        return;
    }

    switch (cmd.id) {
    case PM_CMD_CFG_GET:
        cfg_get(&cmd, source);
        break;
    case PM_CMD_CFG_SET:
        cfg_set(&cmd, source);
        break;
    case PM_CMD_CFG_SAVE:
        reply(PM_CMD_CFG_SAVE, source, pm_store_save(), NULL);
        break;
    case PM_CMD_INFO:
        info(source);
        break;
    case PM_CMD_LOG:
        /* the log already goes to the console; the serial has nothing more */
        reply(PM_CMD_LOG, source, PM_OK, NULL);
        break;
    default: {
        /* a service does it and answers */
        struct app_cmd_msg msg = {
            .id = (uint8_t)cmd.id,
            .source = source,
            .cmd = cmd,
        };

        (void)app_publish(&chan_cmd, &msg);
        break;
    }
    }
}

pm_err_t app_cmd_set_crank_half_mm(uint16_t half_mm)
{
    struct pm_settings s;

    pm_store_get(&s);
    s.crank_length_half_mm = half_mm;
    return pm_store_set(&s, true);
}
