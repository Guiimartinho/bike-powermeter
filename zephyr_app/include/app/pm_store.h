/**
 * @file pm_store.h
 * @brief The configuration in force: one copy, a lock, the settings
 *        subsystem behind it, and a channel that says it changed
 *
 * Every service works on a copy taken with pm_store_get(); whoever changes
 * a field goes through pm_store_set(), which validates, keeps the copy,
 * publishes chan_settings and, when asked, writes the blob to the settings
 * subsystem (ZMS on the nRF54L). The blob is the one of model/pm_settings.
 */

#ifndef PM_STORE_H
#define PM_STORE_H

#include <stdbool.h>

#include "model/pm_settings.h"
#include "model/pm_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Load the settings, or the defaults when there is nothing valid
 *
 * Called once by main() before the services start.
 */
void pm_store_init(void);

/** @brief Copy of the configuration in force */
void pm_store_get(struct pm_settings *out);

/**
 * @brief Replace the configuration in force
 *
 * @param s The new one, validated here
 * @param save Also write it to the settings subsystem
 * @return PM_OK; PM_EINVAL when it fails validation (nothing changes)
 */
pm_err_t pm_store_set(const struct pm_settings *s, bool save);

/** @brief Write the configuration in force to the settings subsystem */
pm_err_t pm_store_save(void);

/** @brief Whether the copy in force came from the storage (false: defaults) */
bool pm_store_loaded(void);

#ifdef __cplusplus
}
#endif

#endif /* PM_STORE_H */
