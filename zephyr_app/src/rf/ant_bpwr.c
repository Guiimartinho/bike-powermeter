/**
 * @file ant_bpwr.c
 * @brief ANT+ Bicycle Power, sensor side, on the sdk-ant add-on (docs/05)
 *
 * The add-on's profile encodes the pages at each transmission from the
 * fields of its profile structure; this file keeps those fields current.
 * Page 16 carries the instantaneous power, the accumulated power and the
 * event count; page 18 the crank torque: the crank ticks, the accumulated
 * crank period in 1/2048 s and the accumulated torque in 1/32 N.m; the
 * cadence goes with both. A calibration request (page 1, manual zero)
 * becomes a $ZERO from APP_SRC_ANT, and the result closes the handshake
 * with ant_bpwr_calib_response().
 */

#include <string.h>

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#include <ant_key_manager.h>
#include <ant_parameters.h>
#include <ant_profiles/bpwr/ant_bpwr.h>

#include "app/app_cmd.h"
#include "app_types.h"
#include "rf/ant_bpwr.h"

/* not ant_bpwr: that is the log module of the add-on's profile */
LOG_MODULE_REGISTER(rf_ant, CONFIG_LOG_DEFAULT_LEVEL);

/* ANT+ network 0, channel 0, transmission type 5 (independent, no shared address) */
#define ANT_NETWORK_NUMBER  0U
#define ANT_CHANNEL_NUMBER  0U
#define ANT_TRANS_TYPE      5U

static void bpwr_evt_handler(ant_bpwr_profile_t *p_profile, ant_bpwr_evt_t event);
static void bpwr_calib_handler(ant_bpwr_profile_t *p_profile, ant_bpwr_page1_data_t *p_page1);

static ant_channel_config_t channel_cfg;
BPWR_SENS_PROFILE_CONFIG_DEF(pm, TORQUE_CRANK, bpwr_calib_handler, bpwr_evt_handler);

static ant_bpwr_profile_t bpwr;
static bool open_channel;
static uint16_t last_rev_count;
static uint16_t last_event_1024;
static bool have_last;

static void bpwr_evt_handler(ant_bpwr_profile_t *p_profile, ant_bpwr_evt_t event)
{
    ARG_UNUSED(p_profile);
    ARG_UNUSED(event);
    /* the fields are kept current by rf_ant_update(); nothing to do per page */
}

/** A calibration page from the display, in the ANT event context: signal only */
/* the signature is the ant_bpwr_calib_handler_t typedef of the add-on: no const */
/* cppcheck-suppress constParameterCallback */
static void bpwr_calib_handler(ant_bpwr_profile_t *p_profile, ant_bpwr_page1_data_t *p_page1)
{
    ARG_UNUSED(p_profile);
    switch (p_page1->calibration_id) {
    case ANT_BPWR_CALIB_ID_MANUAL:
        app_cmd_send(PM_CMD_ZERO, APP_SRC_ANT);
        break;
    case ANT_BPWR_CALIB_ID_AUTO:
        /* auto zero is the firmware's own; the request is acknowledged as is */
        bpwr.BPWR_PROFILE_calibration_id = ANT_BPWR_CALIB_ID_MANUAL_SUCCESS;
        bpwr.BPWR_PROFILE_auto_zero_status = p_page1->auto_zero_status;
        ant_bpwr_calib_response(&bpwr);
        break;
    default:
        bpwr.BPWR_PROFILE_calibration_id = ANT_BPWR_CALIB_ID_FAILED;
        ant_bpwr_calib_response(&bpwr);
        break;
    }
}

static void ant_evt_handler(ant_evt_t *p_ant_evt)
{
    ant_bpwr_sens_evt_handler(p_ant_evt, &bpwr);
}

int rf_ant_start(uint16_t device_number, uint32_t serial)
{
    int err = ant_init();

    if (err != 0) {
        LOG_ERR("ant_init failed: %d", err);
        return err;
    }
    err = ant_cb_register(&ant_evt_handler);
    if (err != 0) {
        LOG_ERR("ant_cb_register failed: %d", err);
        return err;
    }
    err = ant_plus_key_set(ANT_NETWORK_NUMBER);
    if (err != 0) {
        LOG_ERR("ant_plus_key_set failed: %d", err);
        return err;
    }

    channel_cfg.channel_number = ANT_CHANNEL_NUMBER;
    channel_cfg.channel_type = BPWR_SENS_CHANNEL_TYPE;
    channel_cfg.ext_assign = BPWR_EXT_ASSIGN;
    channel_cfg.rf_freq = BPWR_ANTPLUS_RF_FREQ;
    channel_cfg.transmission_type = ANT_TRANS_TYPE;
    channel_cfg.device_type = BPWR_DEVICE_TYPE;
    channel_cfg.device_number = device_number;
    channel_cfg.channel_period = BPWR_MSG_PERIOD;
    channel_cfg.network_number = ANT_NETWORK_NUMBER;

    err = ant_bpwr_sens_init(&bpwr, &channel_cfg, BPWR_SENS_PROFILE_CONFIG(pm));
    if (err != 0) {
        LOG_ERR("ant_bpwr_sens_init failed: %d", err);
        return err;
    }
    bpwr.page_80 = ANT_COMMON_page80(CONFIG_PM_HW_REVISION, CONFIG_PM_ANT_MANUFACTURER_ID,
                                     CONFIG_PM_MODEL_NUMBER);
    bpwr.page_81 = ANT_COMMON_page81(APP_VERSION_MAJOR, APP_VERSION_MINOR, serial);
    bpwr.BPWR_PROFILE_auto_zero_status = ANT_BPWR_AUTO_ZERO_ON;
    /* one crank only: the pedal power byte says "not used" */
    bpwr.page_16.pedal_power.byte = 0xFFU;

    err = ant_bpwr_sens_open(&bpwr);
    if (err != 0) {
        LOG_ERR("ant_bpwr_sens_open failed: %d", err);
        return err;
    }
    open_channel = true;
    LOG_INF("ANT+ power sensor %u on channel %u", (unsigned int)device_number,
            ANT_CHANNEL_NUMBER);
    return 0;
}

void rf_ant_update(const struct app_power *p)
{
    if (!open_channel) {
        return;
    }
    bpwr.BPWR_PROFILE_instantaneous_cadence = p->cadence_rpm;
    bpwr.BPWR_PROFILE_instantaneous_power = p->power_w;
    if (!p->revolution) {
        return;
    }
    /* one event per revolution: the accumulators roll as the profile wants */
    bpwr.BPWR_PROFILE_power_update_event_count++;
    bpwr.BPWR_PROFILE_accumulated_power += p->power_w;
    bpwr.BPWR_PROFILE_crank_update_event_count++;
    bpwr.BPWR_PROFILE_crank_tick = (uint8_t)(p->rev_count & 0xFFU);
    if (have_last) {
        uint16_t revs = (uint16_t)(p->rev_count - last_rev_count);
        uint16_t dt_1024 = (uint16_t)(p->last_event_1024 - last_event_1024);

        ARG_UNUSED(revs);
        /* 1/1024 s to 1/2048 s */
        bpwr.BPWR_PROFILE_crank_period += (uint16_t)(dt_1024 * 2U);
    }
    bpwr.BPWR_PROFILE_crank_accumulated_torque = p->torque_acc_1_32;
    last_rev_count = p->rev_count;
    last_event_1024 = p->last_event_1024;
    have_last = true;
}

void rf_ant_calib_result(bool ok, int16_t value)
{
    if (!open_channel) {
        return;
    }
    bpwr.BPWR_PROFILE_calibration_id = ok ? ANT_BPWR_CALIB_ID_MANUAL_SUCCESS
                                          : ANT_BPWR_CALIB_ID_FAILED;
    bpwr.BPWR_PROFILE_general_calib_data = value;
    ant_bpwr_calib_response(&bpwr);
}
