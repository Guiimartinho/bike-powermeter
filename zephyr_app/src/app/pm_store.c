/**
 * @file pm_store.c
 * @brief The configuration in force and its persistence (docs/05)
 */

#include <string.h>

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#if defined(CONFIG_SETTINGS)
#include <zephyr/settings/settings.h>
#endif

#include "app/app_channels.h"
#include "app/pm_store.h"

LOG_MODULE_REGISTER(pm_store, CONFIG_LOG_DEFAULT_LEVEL);

#define STORE_KEY       "pm"
#define STORE_BLOB      "blob"

static struct pm_settings current;
static K_MUTEX_DEFINE(lock);
static bool loaded;

#if defined(CONFIG_SETTINGS)

static int store_set(const char *name, size_t len, settings_read_cb read_cb, void *cb_arg)
{
    const char *next;
    uint8_t blob[PM_SETTINGS_WIRE_LEN];
    struct pm_settings s;

    if (!settings_name_steq(name, STORE_BLOB, &next) || (next != NULL)) {
        return -ENOENT;
    }
    if (len != sizeof(blob)) {
        LOG_WRN("stored blob of %u bytes ignored", (unsigned int)len);
        return -EINVAL;
    }
    if (read_cb(cb_arg, blob, sizeof(blob)) != (ssize_t)sizeof(blob)) {
        return -EIO;
    }
    if (pm_settings_deserialize(blob, sizeof(blob), &s) != PM_OK) {
        LOG_WRN("stored blob refused: defaults in use");
        return -EINVAL;
    }
    (void)k_mutex_lock(&lock, K_FOREVER);
    current = s;
    loaded = true;
    (void)k_mutex_unlock(&lock);
    return 0;
}

SETTINGS_STATIC_HANDLER_DEFINE(pm_store, STORE_KEY, NULL, store_set, NULL, NULL);

#endif /* CONFIG_SETTINGS */

void pm_store_init(void)
{
    pm_settings_defaults(&current);
    loaded = false;
#if defined(CONFIG_SETTINGS)
    if (settings_subsys_init() != 0) {
        LOG_ERR("settings subsystem failed");
    } else if (settings_load_subtree(STORE_KEY) != 0) {
        LOG_WRN("settings not loaded");
    } else {
        /* loaded says whether a valid blob came in */
    }
#endif
    LOG_INF("settings %s", loaded ? "loaded" : "at their defaults");
}

void pm_store_get(struct pm_settings *out)
{
    (void)k_mutex_lock(&lock, K_FOREVER);
    *out = current;
    (void)k_mutex_unlock(&lock);
}

pm_err_t pm_store_save(void)
{
#if defined(CONFIG_SETTINGS)
    uint8_t blob[PM_SETTINGS_WIRE_LEN];
    size_t n;

    (void)k_mutex_lock(&lock, K_FOREVER);
    n = pm_settings_serialize(&current, blob, sizeof(blob));
    (void)k_mutex_unlock(&lock);
    if (n != sizeof(blob)) {
        return PM_EINVAL;
    }
    if (settings_save_one(STORE_KEY "/" STORE_BLOB, blob, sizeof(blob)) != 0) {
        LOG_ERR("settings not saved");
        return PM_ERANGE;
    }
    LOG_INF("settings saved");
#endif
    return PM_OK;
}

pm_err_t pm_store_set(const struct pm_settings *s, bool save)
{
    struct app_settings_msg msg;

    if (pm_settings_validate(s) != PM_OK) {
        return PM_EINVAL;
    }
    (void)k_mutex_lock(&lock, K_FOREVER);
    current = *s;
    msg.s = current;
    (void)k_mutex_unlock(&lock);
    (void)app_publish(&chan_settings, &msg);
    if (save) {
        return pm_store_save();
    }
    return PM_OK;
}

bool pm_store_loaded(void)
{
    return loaded;
}
