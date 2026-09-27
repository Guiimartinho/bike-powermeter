/**
 * @file cps_encode.h
 * @brief The bytes of the Cycling Power Service, built and read field by
 *        field (docs/05, BLE Cycling Power)
 *
 * The service (0x1818) sends the measurement in one notification with a
 * bitfield in front saying which optional fields follow, answers the
 * control point with a response code, and can stream the torques of a
 * revolution in the vector characteristic. Everything is little-endian;
 * the widths and the order below are those of Cycling Power Service 1.1
 * (bluetooth.com, with erratum 23224), and the host tests check the bytes
 * against the tables of the specification.
 *
 * The counterpart of this module in the bike computer is its
 * `model/cps_parse.c`, which walks the same fields the other way: the two
 * projects are the first bench of each other.
 */

#ifndef CPS_ENCODE_H
#define CPS_ENCODE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "model/pm_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Flags of the Cycling Power Measurement (0x2A63), in wire order */
#define CPS_MEAS_BALANCE            0x0001U
#define CPS_MEAS_BALANCE_LEFT       0x0002U /**< the balance refers to the left leg */
#define CPS_MEAS_TORQUE             0x0004U
#define CPS_MEAS_TORQUE_CRANK       0x0008U /**< the torque is measured at the crank */
#define CPS_MEAS_WHEEL_REV          0x0010U
#define CPS_MEAS_CRANK_REV          0x0020U
#define CPS_MEAS_EXTREME_FORCE      0x0040U
#define CPS_MEAS_EXTREME_TORQUE     0x0080U
#define CPS_MEAS_EXTREME_ANGLES     0x0100U
#define CPS_MEAS_TOP_DEAD_SPOT      0x0200U
#define CPS_MEAS_BOTTOM_DEAD_SPOT   0x0400U
#define CPS_MEAS_ENERGY             0x0800U
#define CPS_MEAS_OFFSET_NEEDED      0x1000U

/* Bits of the Cycling Power Feature (0x2A65) */
#define CPS_FEAT_BALANCE            (1UL << 0)
#define CPS_FEAT_TORQUE             (1UL << 1)
#define CPS_FEAT_WHEEL_REV          (1UL << 2)
#define CPS_FEAT_CRANK_REV          (1UL << 3)
#define CPS_FEAT_EXTREME_MAG        (1UL << 4)
#define CPS_FEAT_EXTREME_ANGLES     (1UL << 5)
#define CPS_FEAT_DEAD_SPOTS         (1UL << 6)
#define CPS_FEAT_ENERGY             (1UL << 7)
#define CPS_FEAT_OFFSET_INDICATOR   (1UL << 8)
#define CPS_FEAT_OFFSET_COMP        (1UL << 9)
#define CPS_FEAT_CONTENT_MASK       (1UL << 10)
#define CPS_FEAT_MULTI_LOCATION     (1UL << 11)
#define CPS_FEAT_CRANK_LENGTH       (1UL << 12)
#define CPS_FEAT_CHAIN_LENGTH       (1UL << 13)
#define CPS_FEAT_CHAIN_WEIGHT       (1UL << 14)
#define CPS_FEAT_SPAN_LENGTH        (1UL << 15)
#define CPS_FEAT_TORQUE_BASED       (1UL << 16) /**< sensor measurement context: torque */
#define CPS_FEAT_DIRECTION          (1UL << 17)
#define CPS_FEAT_FACTORY_DATE       (1UL << 18)
#define CPS_FEAT_ENHANCED_OFFSET    (1UL << 19)
/** Bits 20 and 21: 1 = not for use in a distributed system, 2 = can be used in one */
#define CPS_FEAT_DIST_NOT_FOR_USE   (1UL << 20)
#define CPS_FEAT_DIST_CAN_BE_USED   (2UL << 20)

/** What this meter declares: one crank, torque based, offset and crank length by the control point */
#define CPS_METER_FEATURES                                                                   \
    (CPS_FEAT_BALANCE | CPS_FEAT_TORQUE | CPS_FEAT_CRANK_REV | CPS_FEAT_ENERGY |             \
     CPS_FEAT_OFFSET_INDICATOR | CPS_FEAT_OFFSET_COMP | CPS_FEAT_CONTENT_MASK |              \
     CPS_FEAT_CRANK_LENGTH | CPS_FEAT_TORQUE_BASED | CPS_FEAT_FACTORY_DATE |                 \
     CPS_FEAT_DIST_NOT_FOR_USE)

/* Sensor Location (0x2A5D) values used here */
#define CPS_LOC_OTHER               0U
#define CPS_LOC_LEFT_CRANK          5U
#define CPS_LOC_RIGHT_CRANK         6U
#define CPS_LOC_LEFT_PEDAL          7U
#define CPS_LOC_RIGHT_PEDAL         8U
#define CPS_LOC_REAR_HUB            13U
#define CPS_LOC_SPIDER              15U

/* Cycling Power Control Point (0x2A66) opcodes */
#define CPS_CP_SET_CUMULATIVE       0x01U
#define CPS_CP_UPDATE_LOCATION      0x02U
#define CPS_CP_REQ_LOCATIONS        0x03U
#define CPS_CP_SET_CRANK_LENGTH     0x04U
#define CPS_CP_REQ_CRANK_LENGTH     0x05U
#define CPS_CP_SET_CHAIN_LENGTH     0x06U
#define CPS_CP_REQ_CHAIN_LENGTH     0x07U
#define CPS_CP_SET_CHAIN_WEIGHT     0x08U
#define CPS_CP_REQ_CHAIN_WEIGHT     0x09U
#define CPS_CP_SET_SPAN_LENGTH      0x0AU
#define CPS_CP_REQ_SPAN_LENGTH      0x0BU
#define CPS_CP_START_OFFSET_COMP    0x0CU
#define CPS_CP_MASK_CONTENT         0x0DU
#define CPS_CP_REQ_SAMPLING_RATE    0x0EU
#define CPS_CP_REQ_FACTORY_DATE     0x0FU
#define CPS_CP_START_ENHANCED_OFFSET 0x10U
#define CPS_CP_RESPONSE             0x20U

/* Control point result codes */
#define CPS_CP_SUCCESS              0x01U
#define CPS_CP_NOT_SUPPORTED        0x02U
#define CPS_CP_INVALID_PARAM        0x03U
#define CPS_CP_FAILED               0x04U

/* Content mask of opcode 0x0D: a set bit turns the field off */
#define CPS_MASK_BALANCE            0x0001U
#define CPS_MASK_TORQUE             0x0002U
#define CPS_MASK_WHEEL_REV          0x0004U
#define CPS_MASK_CRANK_REV          0x0008U
#define CPS_MASK_EXTREME_MAG        0x0010U
#define CPS_MASK_EXTREME_ANGLES     0x0020U
#define CPS_MASK_TOP_DEAD_SPOT      0x0040U
#define CPS_MASK_BOTTOM_DEAD_SPOT   0x0080U
#define CPS_MASK_ENERGY             0x0100U
/** Bits above the defined ones are reserved: a mask with them set is an invalid parameter */
#define CPS_MASK_VALID              0x01FFU

/* Cycling Power Vector (0x2A64) flags */
#define CPS_VEC_CRANK_REV           0x01U
#define CPS_VEC_FIRST_ANGLE         0x02U
#define CPS_VEC_FORCE_ARRAY         0x04U
#define CPS_VEC_TORQUE_ARRAY        0x08U
#define CPS_VEC_DIR_UNKNOWN         0x00U
#define CPS_VEC_DIR_TANGENTIAL      0x10U
#define CPS_VEC_DIR_RADIAL          0x20U
#define CPS_VEC_DIR_LATERAL         0x30U

/** Longest measurement this meter sends: flags, power, balance, torque, crank, energy */
#define CPS_MEAS_MAX_LEN            13U
/** Longest control point response: code, opcode, result and a 7-byte date */
#define CPS_CP_RESP_MAX_LEN         10U

/** One measurement, with the optional fields this meter may include */
struct cps_meas {
    int16_t power_w;
    bool has_balance;
    uint8_t balance_half_pct;   /**< 1/2 %, of the left leg when balance_left */
    bool balance_left;          /**< false: reference unknown */
    bool has_torque;
    uint16_t torque_1_32;       /**< accumulated torque, 1/32 N·m */
    bool has_crank;
    uint16_t crank_revs;
    uint16_t crank_time_1024;
    bool has_energy;
    uint16_t energy_kj;
    bool offset_needed;
};

/** A control point request, decoded */
struct cps_cp_req {
    uint8_t opcode;
    uint32_t value;             /**< the parameter of a set request, or 0 */
};

/** A date-time of the profile (7 bytes) */
struct cps_date {
    uint16_t year;
    uint8_t month;
    uint8_t day;
    uint8_t hours;
    uint8_t minutes;
    uint8_t seconds;
};

/** Header of a vector notification */
struct cps_vector_hdr {
    bool has_crank;
    uint16_t crank_revs;
    uint16_t crank_time_1024;
    bool has_first_angle;
    uint16_t first_angle_deg;   /**< angle of the first value, degrees, 0 = arm up */
    bool torque_array;          /**< values are 1/32 N·m (else newtons) */
    uint8_t direction;          /**< CPS_VEC_DIR_* */
};

/**
 * @brief Encode a Cycling Power Measurement
 *
 * @param m Values; the has_* pick the optional fields
 * @param mask Content mask set by the control point (CPS_MASK_*): masked fields are left out
 * @param buf Output
 * @param len Room in @p buf
 * @return Bytes written, 0 when @p buf is too small
 */
size_t cps_encode_measurement(const struct cps_meas *m, uint16_t mask, uint8_t *buf, size_t len);

/**
 * @brief Encode the Cycling Power Feature (4 bytes)
 * @return 4, or 0 when @p buf is too small
 */
size_t cps_encode_feature(uint32_t features, uint8_t *buf, size_t len);

/**
 * @brief Decode a control point request
 *
 * @return PM_OK with the opcode and its parameter; PM_EINVAL when the length
 *         does not match the opcode (an unknown opcode with no parameter is
 *         returned as PM_OK, for the handler to answer "not supported")
 */
pm_err_t cps_cp_decode(const uint8_t *buf, size_t len, struct cps_cp_req *req);

/**
 * @brief Encode a control point response: 0x20, the request opcode, the result, the parameter
 * @return Bytes written, 0 when @p buf is too small
 */
size_t cps_cp_encode_response(uint8_t req_opcode, uint8_t result, const uint8_t *param,
                              size_t param_len, uint8_t *buf, size_t len);

/**
 * @brief Response with a 16-bit parameter (crank length, offset, mask)
 */
size_t cps_cp_encode_u16(uint8_t req_opcode, uint8_t result, uint16_t value, uint8_t *buf,
                         size_t len);

/**
 * @brief Response to Request Factory Calibration Date
 */
size_t cps_cp_encode_date(uint8_t result, const struct cps_date *d, uint8_t *buf, size_t len);

/**
 * @brief Encode a vector notification with as many values as fit
 *
 * @param h Header
 * @param values The values, in the order of the revolution
 * @param n How many there are
 * @param buf Output
 * @param len Room in @p buf (the MTU minus the ATT overhead)
 * @param[out] used How many values went in
 * @return Bytes written, 0 when not even the header fits
 */
size_t cps_encode_vector(const struct cps_vector_hdr *h, const int16_t *values, size_t n,
                         uint8_t *buf, size_t len, size_t *used);

/**
 * @brief Check a content mask against the fields the meter has
 */
bool cps_mask_valid(uint16_t mask);

#ifdef __cplusplus
}
#endif

#endif /* CPS_ENCODE_H */
