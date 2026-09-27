/**
 * @file pm_fsm.h
 * @brief The state machine of the system (docs/04, Máquina do sistema)
 *
 * Plain C, so that every transition and every refusal is a host test. The
 * power service runs it: it feeds the events and the clock, and turns the
 * state into actions (excitation, converter, accelerometer mode,
 * advertising interval). Nothing here touches hardware.
 */

#ifndef PM_FSM_H
#define PM_FSM_H

#include <stdbool.h>
#include <stdint.h>

#include "model/pm_types.h"

#ifdef __cplusplus
extern "C" {
#endif

enum pm_state {
    PM_ST_BOOT = 0,     /**< services starting */
    PM_ST_IDLE,         /**< awake, crank still */
    PM_ST_ACTIVE,       /**< pedalling, or still for less than idle_after_ms */
    PM_ST_SLEEP,        /**< converter off, accelerometer on its wake interrupt */
    PM_ST_CALIBRATING,  /**< a calibration runs; the crank must stay still */
    PM_ST_DFU,          /**< the update is accepted; the device reboots from it */
    PM_ST_LOW_BATTERY,  /**< battery critical: nothing measured until it charges */
    PM_ST_COUNT
};

enum pm_event {
    PM_EV_READY = 0,        /**< all services started */
    PM_EV_MOTION,           /**< the crank turns (motion service) */
    PM_EV_STILL,            /**< the crank stopped (motion service) */
    PM_EV_WAKE,             /**< the accelerometer's wake interrupt, in sleep */
    PM_EV_CAL_REQUEST,      /**< a calibration command */
    PM_EV_CAL_DONE,         /**< the calibration ended, well or badly */
    PM_EV_DFU_REQUEST,      /**< an update was requested */
    PM_EV_BATTERY_CRITICAL, /**< the fuel gauge says critical */
    PM_EV_CHARGING,         /**< a charger is connected and charging */
    PM_EV_COUNT
};

struct pm_fsm_cfg {
    uint32_t idle_after_ms;     /**< still for this long in Active: Idle (30 s) */
    uint32_t sleep_after_ms;    /**< still for this long: Sleep (10 min) */
    uint32_t cal_timeout_ms;    /**< a calibration that does not end: back (60 s) */
    uint8_t dfu_min_soc_pct;    /**< battery needed to accept an update (30) */
};

struct pm_fsm {
    struct pm_fsm_cfg cfg;
    enum pm_state state;
    bool moving;
    uint32_t still_since_ms;
    uint32_t cal_since_ms;
    uint8_t soc_pct;
};

struct pm_fsm_cfg pm_fsm_cfg_default(void);

/** Boot, with the crank taken as still since @p now_ms and the battery unknown (100) */
void pm_fsm_init(struct pm_fsm *f, const struct pm_fsm_cfg *cfg, uint32_t now_ms);

/** The battery level the DFU guard uses */
void pm_fsm_set_soc(struct pm_fsm *f, uint8_t soc_pct);

/**
 * @brief Feed an event
 * @return PM_OK when the event was taken (with or without a change of state),
 *         PM_ESTATE when the state refuses it, PM_EINVAL for an unknown event
 */
pm_err_t pm_fsm_event(struct pm_fsm *f, enum pm_event ev, uint32_t now_ms);

/** Time passes: the timers of Active, Idle and Calibrating */
void pm_fsm_tick(struct pm_fsm *f, uint32_t now_ms);

enum pm_state pm_fsm_state(const struct pm_fsm *f);

/** Whether the converter and the accelerometer sample at full rate in this state */
bool pm_fsm_measuring(enum pm_state s);

const char *pm_fsm_state_name(enum pm_state s);

#ifdef __cplusplus
}
#endif

#endif /* PM_FSM_H */
