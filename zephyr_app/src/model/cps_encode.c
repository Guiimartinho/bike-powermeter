/**
 * @file cps_encode.c
 * @brief The bytes of the Cycling Power Service (docs/05)
 */

#include <string.h>

#include "model/cps_encode.h"
#include "model/pm_wire.h"

size_t cps_encode_measurement(const struct cps_meas *m, uint16_t mask, uint8_t *buf, size_t len)
{
    uint16_t flags = 0U;
    size_t need = 2U + 2U;      /* flags and instantaneous power */
    bool balance = m->has_balance && ((mask & CPS_MASK_BALANCE) == 0U);
    bool torque = m->has_torque && ((mask & CPS_MASK_TORQUE) == 0U);
    bool crank = m->has_crank && ((mask & CPS_MASK_CRANK_REV) == 0U);
    bool energy = m->has_energy && ((mask & CPS_MASK_ENERGY) == 0U);
    size_t at;

    if (balance) {
        flags |= CPS_MEAS_BALANCE;
        if (m->balance_left) {
            flags |= CPS_MEAS_BALANCE_LEFT;
        }
        need += 1U;
    }
    if (torque) {
        /* the torque of a crank meter is always measured at the crank */
        flags |= CPS_MEAS_TORQUE | CPS_MEAS_TORQUE_CRANK;
        need += 2U;
    }
    if (crank) {
        flags |= CPS_MEAS_CRANK_REV;
        need += 4U;
    }
    if (energy) {
        flags |= CPS_MEAS_ENERGY;
        need += 2U;
    }
    if (m->offset_needed) {
        flags |= CPS_MEAS_OFFSET_NEEDED;
    }
    if (len < need) {
        return 0U;
    }

    at = pm_put_u16(buf, 0U, flags);
    at = pm_put_u16(buf, at, (uint16_t)m->power_w);
    if (balance) {
        at = pm_put_u8(buf, at, m->balance_half_pct);
    }
    if (torque) {
        at = pm_put_u16(buf, at, m->torque_1_32);
    }
    if (crank) {
        at = pm_put_u16(buf, at, m->crank_revs);
        at = pm_put_u16(buf, at, m->crank_time_1024);
    }
    if (energy) {
        at = pm_put_u16(buf, at, m->energy_kj);
    }
    return at;
}

size_t cps_encode_feature(uint32_t features, uint8_t *buf, size_t len)
{
    if (len < 4U) {
        return 0U;
    }
    return pm_put_u32(buf, 0U, features);
}

/** Parameter length of each request opcode; 0xFF for an opcode the profile does not define */
static uint8_t cp_param_len(uint8_t opcode)
{
    switch (opcode) {
    case CPS_CP_SET_CUMULATIVE:
        return 4U;
    case CPS_CP_UPDATE_LOCATION:
        return 1U;
    case CPS_CP_SET_CRANK_LENGTH:
    case CPS_CP_SET_CHAIN_LENGTH:
    case CPS_CP_SET_CHAIN_WEIGHT:
    case CPS_CP_SET_SPAN_LENGTH:
    case CPS_CP_MASK_CONTENT:
        return 2U;
    case CPS_CP_REQ_LOCATIONS:
    case CPS_CP_REQ_CRANK_LENGTH:
    case CPS_CP_REQ_CHAIN_LENGTH:
    case CPS_CP_REQ_CHAIN_WEIGHT:
    case CPS_CP_REQ_SPAN_LENGTH:
    case CPS_CP_START_OFFSET_COMP:
    case CPS_CP_REQ_SAMPLING_RATE:
    case CPS_CP_REQ_FACTORY_DATE:
    case CPS_CP_START_ENHANCED_OFFSET:
        return 0U;
    default:
        return 0xFFU;
    }
}

pm_err_t cps_cp_decode(const uint8_t *buf, size_t len, struct cps_cp_req *req)
{
    uint8_t plen;

    req->opcode = 0U;
    req->value = 0U;
    if (len < 1U) {
        return PM_EINVAL;
    }
    req->opcode = buf[0];
    plen = cp_param_len(buf[0]);
    if (plen == 0xFFU) {
        /* unknown opcode: the handler answers "not supported" */
        return PM_OK;
    }
    if (len != (size_t)plen + 1U) {
        return PM_EINVAL;
    }
    switch (plen) {
    case 1U:
        req->value = buf[1];
        break;
    case 2U:
        req->value = pm_get_u16(buf, 1U);
        break;
    case 4U:
        req->value = pm_get_u32(buf, 1U);
        break;
    default:
        break;
    }
    return PM_OK;
}

size_t cps_cp_encode_response(uint8_t req_opcode, uint8_t result, const uint8_t *param,
                              size_t param_len, uint8_t *buf, size_t len)
{
    size_t at;

    if (len < (3U + param_len)) {
        return 0U;
    }
    at = pm_put_u8(buf, 0U, CPS_CP_RESPONSE);
    at = pm_put_u8(buf, at, req_opcode);
    at = pm_put_u8(buf, at, result);
    if (param_len > 0U) {
        (void)memcpy(&buf[at], param, param_len);
        at += param_len;
    }
    return at;
}

size_t cps_cp_encode_u16(uint8_t req_opcode, uint8_t result, uint16_t value, uint8_t *buf,
                         size_t len)
{
    uint8_t p[2];

    (void)pm_put_u16(p, 0U, value);
    return cps_cp_encode_response(req_opcode, result, p, sizeof(p), buf, len);
}

size_t cps_cp_encode_date(uint8_t result, const struct cps_date *d, uint8_t *buf, size_t len)
{
    uint8_t p[7];
    size_t at = pm_put_u16(p, 0U, d->year);

    at = pm_put_u8(p, at, d->month);
    at = pm_put_u8(p, at, d->day);
    at = pm_put_u8(p, at, d->hours);
    at = pm_put_u8(p, at, d->minutes);
    (void)pm_put_u8(p, at, d->seconds);
    return cps_cp_encode_response(CPS_CP_REQ_FACTORY_DATE, result, p, sizeof(p), buf, len);
}

size_t cps_encode_vector(const struct cps_vector_hdr *h, const int16_t *values, size_t n,
                         uint8_t *buf, size_t len, size_t *used)
{
    uint8_t flags = h->direction & 0x30U;
    size_t need = 1U;
    size_t at;
    size_t room;

    *used = 0U;
    if (h->has_crank) {
        flags |= CPS_VEC_CRANK_REV;
        need += 4U;
    }
    if (h->has_first_angle) {
        flags |= CPS_VEC_FIRST_ANGLE;
        need += 2U;
    }
    if (n > 0U) {
        flags |= h->torque_array ? CPS_VEC_TORQUE_ARRAY : CPS_VEC_FORCE_ARRAY;
    }
    if (len < need) {
        return 0U;
    }

    at = pm_put_u8(buf, 0U, flags);
    if (h->has_crank) {
        at = pm_put_u16(buf, at, h->crank_revs);
        at = pm_put_u16(buf, at, h->crank_time_1024);
    }
    if (h->has_first_angle) {
        at = pm_put_u16(buf, at, h->first_angle_deg);
    }
    room = (len - at) / 2U;
    if (room > n) {
        room = n;
    }
    for (size_t i = 0U; i < room; i++) {
        at = pm_put_u16(buf, at, (uint16_t)values[i]);
    }
    *used = room;
    if ((n > 0U) && (room == 0U)) {
        /* the array flag says values follow: without room for one, say none */
        buf[0] = (uint8_t)(flags & (uint8_t)~(CPS_VEC_TORQUE_ARRAY | CPS_VEC_FORCE_ARRAY));
    }
    return at;
}

bool cps_mask_valid(uint16_t mask)
{
    return (mask & (uint16_t)~CPS_MASK_VALID) == 0U;
}
