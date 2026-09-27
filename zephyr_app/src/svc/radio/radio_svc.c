/**
 * @file radio_svc.c
 * @brief Radio service: Bluetooth (and ANT+) up, the data into the air
 *
 * docs/04 (Serviços, radio). The thread brings up ANT (with ANT=1) before
 * Bluetooth, as the sdk-ant samples with both radios do, advertises the
 * Cycling Power Service, and turns the messages of its inbox into the air:
 * chan_power into the CPS measurement, the ANT+ pages and the status;
 * chan_vector into the CPS vector; chan_battery into the Battery Service;
 * chan_cmd_result into the configuration service's answers, the control
 * point's indication or the ANT+ calibration response, by the source of
 * the command. The GATT callbacks run in the Bluetooth receive thread:
 * they decode, publish and return.
 *
 * In Sleep the advertising slows to one packet every 2 s.
 */

#include <errno.h>
#include <stdio.h>
#include <string.h>

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gap.h>
#include <zephyr/bluetooth/services/bas.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/settings/settings.h>
#include <zephyr/zbus/zbus.h>

#include "app/app_channels.h"
#include "app/app_cmd.h"
#include "app/app_services.h"
#include "app/app_svc.h"
#include "app/pm_store.h"
#include "model/pm_cmd.h"
#include "model/pm_fsm.h"
#include "rf/ble_cfg.h"
#include "rf/ble_cps.h"
#include "rf/dfu.h"
#if defined(CONFIG_ANT)
#include "rf/ant_bpwr.h"
#endif

LOG_MODULE_REGISTER(radio_svc, CONFIG_LOG_DEFAULT_LEVEL);

/*
 * Measured with CONFIG_STACK_USAGE (2026-09-27): radio_thread 264 B, then
 * bt_enable() and the settings load of the bonds (about 1,5 KB), the
 * notifications and the answers: about 2 KB
 */
#define RADIO_STACK_SIZE    3072
#define RADIO_INBOX_LEN     16

/** Advertising: 100 to 150 ms awake, 2 s in Sleep (units of 0,625 ms) */
#define ADV_FAST_MIN        160U
#define ADV_FAST_MAX        240U
#define ADV_SLOW            3200U

struct radio_msg {
    const struct zbus_channel *chan;
    union {
        struct app_power power;
        struct app_vector vector;
        struct app_battery battery;
        struct app_health health;
        struct app_cmd_result result;
        struct app_system_state sys;
        struct app_motion_state motion;
        struct app_settings_msg settings;
    } u;
};

K_MSGQ_DEFINE(radio_inbox, sizeof(struct radio_msg), RADIO_INBOX_LEN, 4);

static void radio_listener(const struct zbus_channel *chan)
{
    struct radio_msg msg = { .chan = chan };

    if (chan == &chan_cmd_result) {
        const struct app_cmd_result *r = zbus_chan_const_msg(chan);

        if (r->source == APP_SRC_USB) {
            return;
        }
    }
    if (zbus_chan_msg_size(chan) > sizeof(msg.u)) {
        return;
    }
    (void)memcpy(&msg.u, zbus_chan_const_msg(chan), zbus_chan_msg_size(chan));
    app_inbox_put(&radio_inbox, &msg, "radio");
}

ZBUS_LISTENER_DEFINE(radio_lis, radio_listener);
ZBUS_CHAN_ADD_OBS(chan_power, radio_lis, 3);
ZBUS_CHAN_ADD_OBS(chan_vector, radio_lis, 3);
ZBUS_CHAN_ADD_OBS(chan_battery, radio_lis, 3);
ZBUS_CHAN_ADD_OBS(chan_health, radio_lis, 3);
ZBUS_CHAN_ADD_OBS(chan_cmd_result, radio_lis, 3);
ZBUS_CHAN_ADD_OBS(chan_system_state, radio_lis, 3);
ZBUS_CHAN_ADD_OBS(chan_motion_state, radio_lis, 3);
ZBUS_CHAN_ADD_OBS(chan_settings, radio_lis, 3);

/* ---- advertising --------------------------------------------------------- */

static const struct bt_data ad[] = {
    BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
    BT_DATA_BYTES(BT_DATA_UUID16_ALL, BT_UUID_16_ENCODE(BT_UUID_CPS_VAL),
                  BT_UUID_16_ENCODE(BT_UUID_BAS_VAL)),
    BT_DATA_BYTES(BT_DATA_GAP_APPEARANCE, 0x84, 0x04),
};

static char dev_name[CONFIG_BT_DEVICE_NAME_MAX + 1];
static bool advertising;
static bool slow_adv;
static atomic_t adv_needed;

static int adv_start(bool slow)
{
    struct bt_le_adv_param param = *BT_LE_ADV_PARAM(BT_LE_ADV_OPT_CONN,
                                                    slow ? ADV_SLOW : ADV_FAST_MIN,
                                                    slow ? ADV_SLOW : ADV_FAST_MAX, NULL);
    const struct bt_data sd[] = {
        BT_DATA(BT_DATA_NAME_COMPLETE, dev_name, strlen(dev_name)),
    };
    int err;

    if (advertising) {
        (void)bt_le_adv_stop();
        advertising = false;
    }
    err = bt_le_adv_start(&param, ad, ARRAY_SIZE(ad), sd, ARRAY_SIZE(sd));
    if (err == 0) {
        advertising = true;
        slow_adv = slow;
    } else if (err != -EALREADY) {
        LOG_WRN("advertising did not start: %d", err);
    } else {
        advertising = true;
    }
    return err;
}

static void connected(struct bt_conn *conn, uint8_t err)
{
    ARG_UNUSED(conn);
    if (err != 0U) {
        LOG_WRN("connection failed: %u", err);
        atomic_set(&adv_needed, 1);
        return;
    }
    LOG_INF("connected");
    advertising = false;
}

static void disconnected(struct bt_conn *conn, uint8_t reason)
{
    ARG_UNUSED(conn);
    LOG_INF("disconnected: %u", reason);
    atomic_set(&adv_needed, 1);
}

BT_CONN_CB_DEFINE(conn_cbs) = {
    .connected = connected,
    .disconnected = disconnected,
};

/** "PM-XXXX" from the configured name and the last two bytes of the address */
static void build_name(const struct pm_settings *s)
{
    bt_addr_le_t addrs[CONFIG_BT_ID_MAX];
    size_t count = ARRAY_SIZE(addrs);

    bt_id_get(addrs, &count);
    if ((strcmp(s->name, "PM") == 0) && (count > 0U)) {
        (void)snprintf(dev_name, sizeof(dev_name), "PM-%02X%02X", addrs[0].a.val[1],
                       addrs[0].a.val[0]);
    } else {
        (void)snprintf(dev_name, sizeof(dev_name), "%s", s->name);
    }
    (void)bt_set_name(dev_name);
}

/* ---- the control point, in the Bluetooth receive thread ------------------- */

static bool cp_zero_pending;

static void cp_request(const struct cps_cp_req *req)
{
    struct pm_settings s;

    switch (req->opcode) {
    case CPS_CP_SET_CRANK_LENGTH: {
        pm_err_t err = app_cmd_set_crank_half_mm((uint16_t)req->value);

        (void)ble_cps_respond(req->opcode,
                              (err == PM_OK) ? CPS_CP_SUCCESS : CPS_CP_INVALID_PARAM, NULL, 0U);
        break;
    }
    case CPS_CP_REQ_CRANK_LENGTH: {
        uint8_t p[2];

        pm_store_get(&s);
        p[0] = (uint8_t)(s.crank_length_half_mm & 0xFFU);
        p[1] = (uint8_t)(s.crank_length_half_mm >> 8);
        (void)ble_cps_respond(req->opcode, CPS_CP_SUCCESS, p, sizeof(p));
        break;
    }
    case CPS_CP_REQ_LOCATIONS: {
        const uint8_t locs[2] = { CPS_LOC_LEFT_CRANK, CPS_LOC_RIGHT_CRANK };

        (void)ble_cps_respond(req->opcode, CPS_CP_SUCCESS, locs, sizeof(locs));
        break;
    }
    case CPS_CP_UPDATE_LOCATION:
        if ((req->value == CPS_LOC_LEFT_CRANK) || (req->value == CPS_LOC_RIGHT_CRANK)) {
            pm_store_get(&s);
            s.side = (uint8_t)req->value;
            if (pm_store_set(&s, true) == PM_OK) {
                ble_cps_set_location(s.side);
                (void)ble_cps_respond(req->opcode, CPS_CP_SUCCESS, NULL, 0U);
                break;
            }
        }
        (void)ble_cps_respond(req->opcode, CPS_CP_INVALID_PARAM, NULL, 0U);
        break;
    case CPS_CP_START_OFFSET_COMP:
        /* answered when the zero of the compute service comes back */
        cp_zero_pending = true;
        app_cmd_send(PM_CMD_ZERO, APP_SRC_CPS);
        break;
    case CPS_CP_MASK_CONTENT:
        if (cps_mask_valid((uint16_t)req->value)) {
            ble_cps_set_mask((uint16_t)req->value);
            (void)ble_cps_respond(req->opcode, CPS_CP_SUCCESS, NULL, 0U);
        } else {
            (void)ble_cps_respond(req->opcode, CPS_CP_INVALID_PARAM, NULL, 0U);
        }
        break;
    case CPS_CP_REQ_SAMPLING_RATE: {
        /* one measurement per revolution and one a second: 1 Hz nominal */
        const uint8_t hz = 1U;

        (void)ble_cps_respond(req->opcode, CPS_CP_SUCCESS, &hz, 1U);
        break;
    }
    case CPS_CP_REQ_FACTORY_DATE: {
        uint8_t buf[CPS_CP_RESP_MAX_LEN];
        struct cps_date d;

        pm_store_get(&s);
        (void)memset(&d, 0, sizeof(d));
        d.year = s.cal_year;
        d.month = s.cal_month;
        d.day = s.cal_day;
        /* cps_cp_encode_date writes the whole response; reuse its parameter part */
        if (cps_cp_encode_date(CPS_CP_SUCCESS, &d, buf, sizeof(buf)) == CPS_CP_RESP_MAX_LEN) {
            (void)ble_cps_respond(req->opcode, CPS_CP_SUCCESS, &buf[3], 7U);
        }
        break;
    }
    default:
        (void)ble_cps_respond(req->opcode, CPS_CP_NOT_SUPPORTED, NULL, 0U);
        break;
    }
}

/* ---- the answers ----------------------------------------------------------- */

static void on_result(const struct app_cmd_result *r)
{
    char out[80];

    switch (r->source) {
    case APP_SRC_BLE_CFG:
        if (r->err == (uint8_t)PM_OK) {
            (void)pm_cmd_ack(out, sizeof(out), r->text);
        } else {
            (void)pm_cmd_nak(out, sizeof(out), (pm_err_t)r->err);
        }
        (void)ble_cfg_send_line(out);
        break;
    case APP_SRC_CPS:
        if ((r->id == PM_CMD_ZERO) && cp_zero_pending) {
            cp_zero_pending = false;
            if (r->err == (uint8_t)PM_OK) {
                int32_t v = r->value;
                uint8_t p[2];

                /* the offset in the raw units of the converter, clamped to int16 */
                if (v > INT16_MAX) {
                    v = INT16_MAX;
                } else if (v < INT16_MIN) {
                    v = INT16_MIN;
                } else {
                    /* fits */
                }
                p[0] = (uint8_t)((uint16_t)v & 0xFFU);
                p[1] = (uint8_t)((uint16_t)v >> 8);
                (void)ble_cps_respond(CPS_CP_START_OFFSET_COMP, CPS_CP_SUCCESS, p, sizeof(p));
            } else {
                (void)ble_cps_respond(CPS_CP_START_OFFSET_COMP, CPS_CP_FAILED, NULL, 0U);
            }
        }
        break;
#if defined(CONFIG_ANT)
    case APP_SRC_ANT:
        if (r->id == PM_CMD_ZERO) {
            int32_t v = r->value;

            if (v > INT16_MAX) {
                v = INT16_MAX;
            } else if (v < INT16_MIN) {
                v = INT16_MIN;
            } else {
                /* fits */
            }
            rf_ant_calib_result(r->err == (uint8_t)PM_OK, (int16_t)v);
        }
        break;
#endif
    default:
        break;
    }
}

/* ---- thread ----------------------------------------------------------------- */

static void radio_start(void)
{
    struct pm_settings s;
    int err;

    pm_store_get(&s);
#if defined(CONFIG_ANT)
    {
        bt_addr_le_t addrs[CONFIG_BT_ID_MAX];
        size_t count = 0U;
        uint16_t number = s.ant_device_number;
        uint32_t serial = 0U;

        /* ANT before bt_enable(); the address is not known yet: a fixed serial */
        ARG_UNUSED(addrs);
        ARG_UNUSED(count);
        if (number == 0U) {
            number = 1U;
        }
        err = rf_ant_start(number, serial);
        if (err != 0) {
            LOG_ERR("ANT start failed: %d", err);
        }
    }
#endif
    err = bt_enable(NULL);
    if (err != 0) {
        LOG_ERR("Bluetooth start failed: %d", err);
        return;
    }
#if defined(CONFIG_BT_SETTINGS)
    (void)settings_load_subtree("bt");
#endif
    build_name(&s);
    ble_cfg_init();
    ble_cps_init(cp_request);
    ble_cps_set_location(s.side);
    if (rf_dfu_init() != 0) {
        LOG_ERR("DFU start failed");
    }
    (void)adv_start(false);
    LOG_INF("Bluetooth up as %s", dev_name);
}

static void radio_thread(void *p1, void *p2, void *p3)
{
    struct radio_msg msg;
    uint8_t soc = 100U;
    bool vbus = false;
    bool moving = false;
    uint8_t state = PM_ST_BOOT;
    int16_t last_soc = -1;
    struct app_health health = { 0 };

    ARG_UNUSED(p1);
    ARG_UNUSED(p2);
    ARG_UNUSED(p3);

    radio_start();

    int wdt = app_wdt_add("radio");

    for (;;) {
        if (atomic_cas(&adv_needed, 1, 0)) {
            (void)adv_start(slow_adv);
        }
        if (app_inbox_get(&radio_inbox, &msg, wdt, APP_SVC_TICK_MS) != 0) {
            continue;
        }
        if (msg.chan == &chan_power) {
            (void)ble_cps_notify_measurement(&msg.u.power);
#if defined(CONFIG_ANT)
            rf_ant_update(&msg.u.power);
#endif
        } else if (msg.chan == &chan_vector) {
            (void)ble_cps_notify_vector(&msg.u.vector);
        } else if (msg.chan == &chan_battery) {
            soc = msg.u.battery.gauge ? msg.u.battery.soc_pct : 100U;
            vbus = msg.u.battery.vbus;
            if (msg.u.battery.gauge && ((int16_t)soc != last_soc)) {
                last_soc = (int16_t)soc;
                (void)bt_bas_set_battery_level(soc);
            }
            rf_dfu_set_conditions(moving, soc, vbus);
        } else if (msg.chan == &chan_health) {
            health = msg.u.health;
            (void)ble_cfg_notify_status(&health, soc, state);
        } else if (msg.chan == &chan_cmd_result) {
            on_result(&msg.u.result);
        } else if (msg.chan == &chan_system_state) {
            state = msg.u.sys.state;
            if (advertising || (state == PM_ST_SLEEP)) {
                (void)adv_start(state == PM_ST_SLEEP);
            }
        } else if (msg.chan == &chan_motion_state) {
            moving = msg.u.motion.moving;
            rf_dfu_set_conditions(moving, soc, vbus);
        } else if (msg.chan == &chan_settings) {
            ble_cps_set_location(msg.u.settings.s.side);
        } else {
            /* nothing else reaches this inbox */
        }
    }
}

K_THREAD_DEFINE(radio_tid, RADIO_STACK_SIZE, radio_thread, NULL, NULL, NULL, APP_PRIO_RADIO, 0,
                SYS_FOREVER_MS);

void radio_svc_start(void)
{
    k_thread_name_set(radio_tid, "radio");
    k_thread_start(radio_tid);
}
