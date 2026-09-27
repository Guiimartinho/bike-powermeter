/**
 * @file ble_cfg.c
 * @brief The configuration service of the project over GATT (docs/05)
 */

#include <errno.h>
#include <string.h>

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#include "app/app_cmd.h"
#include "app/pm_store.h"
#include "model/pm_cmd.h"
#include "model/pm_wire.h"
#include "rf/ble_cfg.h"

LOG_MODULE_REGISTER(ble_cfg, CONFIG_LOG_DEFAULT_LEVEL);

/* UUIDs of the project: 7d1f0001-4c8e-4a3b-9e2f-5b6a7c8d9e01 and the next four */
#define UUID_CFG_BASE(n) BT_UUID_128_ENCODE(0x7d1f0000U + (n), 0x4c8e, 0x4a3b, 0x9e2f, 0x5b6a7c8d9e01ULL)

static const struct bt_uuid_128 uuid_svc = BT_UUID_INIT_128(UUID_CFG_BASE(1));
static const struct bt_uuid_128 uuid_cmd = BT_UUID_INIT_128(UUID_CFG_BASE(2));
static const struct bt_uuid_128 uuid_rsp = BT_UUID_INIT_128(UUID_CFG_BASE(3));
static const struct bt_uuid_128 uuid_cfg = BT_UUID_INIT_128(UUID_CFG_BASE(4));
static const struct bt_uuid_128 uuid_sta = BT_UUID_INIT_128(UUID_CFG_BASE(5));

static bool rsp_on;
static bool sta_on;
static struct pm_line line;

static void rsp_ccc(const struct bt_gatt_attr *attr, uint16_t value)
{
    ARG_UNUSED(attr);
    rsp_on = (value == BT_GATT_CCC_NOTIFY);
}

static void sta_ccc(const struct bt_gatt_attr *attr, uint16_t value)
{
    ARG_UNUSED(attr);
    sta_on = (value == BT_GATT_CCC_NOTIFY);
}

/** A write of the command: the bytes of a line; a write without a terminator ends the line */
static ssize_t write_cmd(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *buf,
                         uint16_t len, uint16_t offset, uint8_t flags)
{
    const char *p = buf;
    bool ended = false;

    ARG_UNUSED(conn);
    ARG_UNUSED(attr);
    ARG_UNUSED(flags);
    if (offset != 0U) {
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
    }
    for (uint16_t i = 0U; i < len; i++) {
        ended = (p[i] == '\r') || (p[i] == '\n');
        if (pm_line_feed(&line, p[i])) {
            app_cmd_handle(line.buf, strlen(line.buf), APP_SRC_BLE_CFG);
        }
    }
    if (!ended && (len > 0U) && pm_line_feed(&line, '\n')) {
        app_cmd_handle(line.buf, strlen(line.buf), APP_SRC_BLE_CFG);
    }
    return len;
}

static ssize_t read_cfg(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf,
                        uint16_t len, uint16_t offset)
{
    struct pm_settings s;
    uint8_t blob[PM_SETTINGS_WIRE_LEN];

    pm_store_get(&s);
    (void)pm_settings_serialize(&s, blob, sizeof(blob));
    return bt_gatt_attr_read(conn, attr, buf, len, offset, blob, sizeof(blob));
}

static ssize_t write_cfg(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *buf,
                         uint16_t len, uint16_t offset, uint8_t flags)
{
    struct pm_settings s;

    ARG_UNUSED(conn);
    ARG_UNUSED(attr);
    ARG_UNUSED(flags);
    if (offset != 0U) {
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
    }
    if (len != PM_SETTINGS_WIRE_LEN) {
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
    }
    if (pm_settings_deserialize(buf, len, &s) != PM_OK) {
        return BT_GATT_ERR(BT_ATT_ERR_VALUE_NOT_ALLOWED);
    }
    if (pm_store_set(&s, true) != PM_OK) {
        return BT_GATT_ERR(BT_ATT_ERR_VALUE_NOT_ALLOWED);
    }
    return len;
}

BT_GATT_SERVICE_DEFINE(cfg_svc,
    BT_GATT_PRIMARY_SERVICE(&uuid_svc),
    BT_GATT_CHARACTERISTIC(&uuid_cmd.uuid, BT_GATT_CHRC_WRITE | BT_GATT_CHRC_WRITE_WITHOUT_RESP,
                           BT_GATT_PERM_WRITE, NULL, write_cmd, NULL),
    BT_GATT_CHARACTERISTIC(&uuid_rsp.uuid, BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_NONE, NULL, NULL,
                           NULL),
    BT_GATT_CCC(rsp_ccc, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
    BT_GATT_CHARACTERISTIC(&uuid_cfg.uuid, BT_GATT_CHRC_READ | BT_GATT_CHRC_WRITE,
                           BT_GATT_PERM_READ | BT_GATT_PERM_WRITE, read_cfg, write_cfg, NULL),
    BT_GATT_CHARACTERISTIC(&uuid_sta.uuid, BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_NONE, NULL, NULL,
                           NULL),
    BT_GATT_CCC(sta_ccc, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
);

#define ATTR_RSP    3
#define ATTR_STA    8

void ble_cfg_init(void)
{
    pm_line_reset(&line);
}

int ble_cfg_send_line(const char *text)
{
    size_t n = strlen(text);

    if (!rsp_on) {
        return -ENOTCONN;
    }
    if (n > 244U) {
        n = 244U;
    }
    return bt_gatt_notify(NULL, &cfg_svc.attrs[ATTR_RSP], text, (uint16_t)n);
}

int ble_cfg_notify_status(const struct app_health *h, uint8_t soc_pct, uint8_t state)
{
    uint8_t buf[BLE_CFG_STATUS_LEN];
    size_t at;
    float t = h->temp_c * 100.0f;
    int16_t t100 = (int16_t)((t > 32767.0f) ? 32767.0f : (t < -32768.0f) ? -32768.0f : t);

    if (!sta_on) {
        return -ENOTCONN;
    }
    at = pm_put_u16(buf, 0U, h->flags);
    at = pm_put_u16(buf, at, (uint16_t)t100);
    at = pm_put_u32(buf, at, (uint32_t)h->code);
    at = pm_put_u32(buf, at, (uint32_t)h->zero);
    at = pm_put_u16(buf, at, h->ref_mv);
    at = pm_put_u8(buf, at, soc_pct);
    (void)pm_put_u8(buf, at, state);
    return bt_gatt_notify(NULL, &cfg_svc.attrs[ATTR_STA], buf, sizeof(buf));
}
