/**
 * @file ble_cps.c
 * @brief The Cycling Power Service of the pod, server side (docs/05)
 */

#include <errno.h>
#include <string.h>

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#include "model/health.h"
#include "rf/ble_cps.h"

LOG_MODULE_REGISTER(ble_cps, CONFIG_LOG_DEFAULT_LEVEL);

/** The Control Point wants its CCC configured before any write (CPS 1.1, 3.4.2) */
#define CPS_ERR_CCC_NOT_CONFIGURED  0x80U

static ble_cps_cp_cb_t cp_cb;
static uint8_t location = CPS_LOC_LEFT_CRANK;
static uint16_t content_mask;
static bool meas_on;
static bool vec_on;
static bool cp_on;
static bool cp_busy;
static struct bt_gatt_indicate_params ind;
static uint8_t ind_buf[CPS_CP_RESP_MAX_LEN];

static void meas_ccc(const struct bt_gatt_attr *attr, uint16_t value)
{
    ARG_UNUSED(attr);
    meas_on = (value == BT_GATT_CCC_NOTIFY);
}

static void vec_ccc(const struct bt_gatt_attr *attr, uint16_t value)
{
    ARG_UNUSED(attr);
    vec_on = (value == BT_GATT_CCC_NOTIFY);
}

static void cp_ccc(const struct bt_gatt_attr *attr, uint16_t value)
{
    ARG_UNUSED(attr);
    cp_on = (value == BT_GATT_CCC_INDICATE);
}

static ssize_t read_feature(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf,
                            uint16_t len, uint16_t offset)
{
    uint8_t v[4];

    (void)cps_encode_feature(CPS_METER_FEATURES, v, sizeof(v));
    return bt_gatt_attr_read(conn, attr, buf, len, offset, v, sizeof(v));
}

static ssize_t read_location(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf,
                             uint16_t len, uint16_t offset)
{
    return bt_gatt_attr_read(conn, attr, buf, len, offset, &location, sizeof(location));
}

static ssize_t write_cp(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *buf,
                        uint16_t len, uint16_t offset, uint8_t flags)
{
    struct cps_cp_req req;

    ARG_UNUSED(conn);
    ARG_UNUSED(attr);
    ARG_UNUSED(flags);
    if (!cp_on) {
        return BT_GATT_ERR(CPS_ERR_CCC_NOT_CONFIGURED);
    }
    if (offset != 0U) {
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
    }
    if (cp_busy) {
        return BT_GATT_ERR(BT_ATT_ERR_PROCEDURE_IN_PROGRESS);
    }
    if (cps_cp_decode(buf, len, &req) != PM_OK) {
        /* a length that does not fit the opcode: invalid parameter, by indication */
        (void)ble_cps_respond(req.opcode, CPS_CP_INVALID_PARAM, NULL, 0U);
        return len;
    }
    if (cp_cb != NULL) {
        cp_cb(&req);
    } else {
        (void)ble_cps_respond(req.opcode, CPS_CP_NOT_SUPPORTED, NULL, 0U);
    }
    return len;
}

BT_GATT_SERVICE_DEFINE(cps_svc,
    BT_GATT_PRIMARY_SERVICE(BT_UUID_CPS),
    BT_GATT_CHARACTERISTIC(BT_UUID_GATT_CPS_CPM, BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_NONE, NULL,
                           NULL, NULL),
    BT_GATT_CCC(meas_ccc, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
    BT_GATT_CHARACTERISTIC(BT_UUID_GATT_CPS_CPF, BT_GATT_CHRC_READ, BT_GATT_PERM_READ,
                           read_feature, NULL, NULL),
    BT_GATT_CHARACTERISTIC(BT_UUID_SENSOR_LOCATION, BT_GATT_CHRC_READ, BT_GATT_PERM_READ,
                           read_location, NULL, NULL),
    BT_GATT_CHARACTERISTIC(BT_UUID_GATT_CPS_CPCP, BT_GATT_CHRC_WRITE | BT_GATT_CHRC_INDICATE,
                           BT_GATT_PERM_WRITE, NULL, write_cp, NULL),
    BT_GATT_CCC(cp_ccc, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
    BT_GATT_CHARACTERISTIC(BT_UUID_GATT_CPS_CPV, BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_NONE, NULL,
                           NULL, NULL),
    BT_GATT_CCC(vec_ccc, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
);

/* attribute indexes in the table above */
#define ATTR_MEAS   1
#define ATTR_CP     8
#define ATTR_VEC    11

void ble_cps_init(ble_cps_cp_cb_t cb)
{
    cp_cb = cb;
}

void ble_cps_set_location(uint8_t loc)
{
    location = loc;
}

uint16_t ble_cps_mask(void)
{
    return content_mask;
}

void ble_cps_set_mask(uint16_t mask)
{
    content_mask = mask;
}

int ble_cps_notify_measurement(const struct app_power *p)
{
    uint8_t buf[CPS_MEAS_MAX_LEN];
    struct cps_meas m = {
        .power_w = (int16_t)((p->power_w > INT16_MAX) ? INT16_MAX : p->power_w),
        .has_balance = true,
        .balance_half_pct = (uint8_t)(p->balance_pct * 2U),
        .balance_left = false,
        .has_torque = true,
        .torque_1_32 = p->torque_acc_1_32,
        .has_crank = true,
        .crank_revs = p->rev_count,
        .crank_time_1024 = p->last_event_1024,
        .has_energy = true,
        .energy_kj = p->energy_kj,
        .offset_needed = (p->health_flags & HEALTH_ZERO_DRIFT) != 0U,
    };
    size_t n;

    if (!meas_on) {
        return -ENOTCONN;
    }
    n = cps_encode_measurement(&m, content_mask, buf, sizeof(buf));
    if (n == 0U) {
        return -EINVAL;
    }
    return bt_gatt_notify(NULL, &cps_svc.attrs[ATTR_MEAS], buf, (uint16_t)n);
}

int ble_cps_notify_vector(const struct app_vector *v)
{
    uint8_t buf[1U + 4U + 2U + (2U * APP_VECTOR_POINTS)];
    struct cps_vector_hdr h = {
        .has_crank = true,
        .crank_revs = v->rev_count,
        .crank_time_1024 = v->last_event_1024,
        .has_first_angle = true,
        .first_angle_deg = v->first_angle_deg,
        .torque_array = true,
        .direction = CPS_VEC_DIR_TANGENTIAL,
    };
    size_t used = 0U;
    size_t n;

    if (!vec_on) {
        return -ENOTCONN;
    }
    n = cps_encode_vector(&h, v->torque_1_32, APP_VECTOR_POINTS, buf, sizeof(buf), &used);
    if (n == 0U) {
        return -EINVAL;
    }
    return bt_gatt_notify(NULL, &cps_svc.attrs[ATTR_VEC], buf, (uint16_t)n);
}

static void ind_done(struct bt_conn *conn, struct bt_gatt_indicate_params *params, uint8_t err)
{
    ARG_UNUSED(conn);
    ARG_UNUSED(params);
    if (err != 0U) {
        LOG_WRN("control point indication failed: %u", err);
    }
}

static void ind_destroy(struct bt_gatt_indicate_params *params)
{
    ARG_UNUSED(params);
    cp_busy = false;
}

int ble_cps_respond(uint8_t req_opcode, uint8_t result, const uint8_t *param, size_t param_len)
{
    size_t n;
    int err;

    if (!cp_on) {
        return -ENOTCONN;
    }
    if (cp_busy) {
        return -EBUSY;
    }
    n = cps_cp_encode_response(req_opcode, result, param, param_len, ind_buf, sizeof(ind_buf));
    if (n == 0U) {
        return -EINVAL;
    }
    (void)memset(&ind, 0, sizeof(ind));
    ind.attr = &cps_svc.attrs[ATTR_CP];
    ind.func = ind_done;
    ind.destroy = ind_destroy;
    ind.data = ind_buf;
    ind.len = (uint16_t)n;
    cp_busy = true;
    err = bt_gatt_indicate(NULL, &ind);
    if (err != 0) {
        cp_busy = false;
    }
    return err;
}
