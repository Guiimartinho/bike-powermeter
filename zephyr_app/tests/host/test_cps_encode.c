/*
 * Tests of model/cps_encode.c against Cycling Power Service 1.1: the flags
 * and the order of the measurement fields, the feature bits, the control
 * point requests and responses, the vector, the content mask.
 */

#include <string.h>

#include "model/cps_encode.h"
#include "unity.h"

void setUp(void)
{
}

void tearDown(void)
{
}

/* ----------------------------------------------------------- measurement */

static void test_power_alone_is_four_bytes_with_no_flag(void)
{
    struct cps_meas m = { .power_w = 250 };
    uint8_t buf[CPS_MEAS_MAX_LEN];
    uint8_t want[] = { 0x00, 0x00, 0xFA, 0x00 };

    TEST_ASSERT_EQUAL_size_t(4U, cps_encode_measurement(&m, 0U, buf, sizeof(buf)));
    TEST_ASSERT_EQUAL_UINT8_ARRAY(want, buf, sizeof(want));
}

static void test_negative_power_is_a_signed_int16(void)
{
    struct cps_meas m = { .power_w = -1 };
    uint8_t buf[CPS_MEAS_MAX_LEN];

    TEST_ASSERT_EQUAL_size_t(4U, cps_encode_measurement(&m, 0U, buf, sizeof(buf)));
    TEST_ASSERT_EQUAL_UINT8(0xFF, buf[2]);
    TEST_ASSERT_EQUAL_UINT8(0xFF, buf[3]);
}

static void test_every_field_of_the_meter_in_wire_order(void)
{
    struct cps_meas m = {
        .power_w = 400,
        .has_balance = true, .balance_half_pct = 100U, .balance_left = false,
        .has_torque = true, .torque_1_32 = 0x1234U,
        .has_crank = true, .crank_revs = 0x0102U, .crank_time_1024 = 0xABCDU,
        .has_energy = true, .energy_kj = 0x0007U,
        .offset_needed = true,
    };
    uint8_t buf[CPS_MEAS_MAX_LEN];
    /* flags: balance (bit 0), torque (bit 2) at the crank (bit 3), crank rev
     * (bit 5), energy (bit 11), offset needed (bit 12) = 0x182D */
    uint8_t want[] = { 0x2D, 0x18, 0x90, 0x01, 0x64, 0x34, 0x12, 0x02, 0x01, 0xCD, 0xAB,
                       0x07, 0x00 };

    TEST_ASSERT_EQUAL_size_t(13U, cps_encode_measurement(&m, 0U, buf, sizeof(buf)));
    TEST_ASSERT_EQUAL_UINT8_ARRAY(want, buf, sizeof(want));
}

static void test_balance_reference_flag_follows_the_left_leg(void)
{
    struct cps_meas m = { .power_w = 1, .has_balance = true, .balance_half_pct = 100U,
                          .balance_left = true };
    uint8_t buf[CPS_MEAS_MAX_LEN];

    TEST_ASSERT_EQUAL_size_t(5U, cps_encode_measurement(&m, 0U, buf, sizeof(buf)));
    TEST_ASSERT_EQUAL_UINT8(0x03, buf[0]);
}

static void test_the_content_mask_drops_fields_and_their_flags(void)
{
    struct cps_meas m = {
        .power_w = 400,
        .has_balance = true, .balance_half_pct = 100U,
        .has_torque = true, .torque_1_32 = 5U,
        .has_crank = true, .crank_revs = 1U, .crank_time_1024 = 2U,
        .has_energy = true, .energy_kj = 3U,
    };
    uint8_t buf[CPS_MEAS_MAX_LEN];

    /* torque and energy off: flags balance + crank = 0x0021 */
    TEST_ASSERT_EQUAL_size_t(9U, cps_encode_measurement(&m, CPS_MASK_TORQUE | CPS_MASK_ENERGY,
                                                        buf, sizeof(buf)));
    TEST_ASSERT_EQUAL_UINT8(0x21, buf[0]);
    TEST_ASSERT_EQUAL_UINT8(0x00, buf[1]);
    TEST_ASSERT_EQUAL_UINT8(100U, buf[4]);
    TEST_ASSERT_EQUAL_UINT8(1U, buf[5]);   /* crank revs right after the balance */

    /* everything off: only the power */
    TEST_ASSERT_EQUAL_size_t(4U, cps_encode_measurement(&m, CPS_MASK_VALID, buf, sizeof(buf)));
    TEST_ASSERT_EQUAL_UINT8(0x00, buf[0]);
}

static void test_a_short_buffer_gives_zero(void)
{
    struct cps_meas m = { .power_w = 1, .has_crank = true };
    uint8_t buf[CPS_MEAS_MAX_LEN];

    TEST_ASSERT_EQUAL_size_t(0U, cps_encode_measurement(&m, 0U, buf, 7U));
    TEST_ASSERT_EQUAL_size_t(8U, cps_encode_measurement(&m, 0U, buf, 8U));
}

/* --------------------------------------------------------------- feature */

static void test_feature_is_four_little_endian_bytes(void)
{
    uint8_t buf[4];
    uint8_t want[] = { 0x8B, 0x17, 0x15, 0x00 };

    /* the meter's features: bits 0,1,3,7 = 0x8B; 8,9,10,12 = 0x17; 16,18,20 = 0x15 */
    TEST_ASSERT_EQUAL_size_t(4U, cps_encode_feature(CPS_METER_FEATURES, buf, sizeof(buf)));
    TEST_ASSERT_EQUAL_UINT8_ARRAY(want, buf, 4U);
    TEST_ASSERT_EQUAL_size_t(0U, cps_encode_feature(CPS_METER_FEATURES, buf, 3U));
}

static void test_meter_features_are_a_crank_torque_meter_not_a_distributed_one(void)
{
    TEST_ASSERT_TRUE((CPS_METER_FEATURES & CPS_FEAT_TORQUE_BASED) != 0U);
    TEST_ASSERT_TRUE((CPS_METER_FEATURES & CPS_FEAT_WHEEL_REV) == 0U);
    TEST_ASSERT_TRUE((CPS_METER_FEATURES & CPS_FEAT_ENHANCED_OFFSET) == 0U);
    TEST_ASSERT_EQUAL_UINT32(CPS_FEAT_DIST_NOT_FOR_USE, CPS_METER_FEATURES & (3UL << 20));
}

/* --------------------------------------------------------- control point */

static void test_set_crank_length_carries_a_uint16_in_half_millimetres(void)
{
    uint8_t req[] = { CPS_CP_SET_CRANK_LENGTH, 0x59, 0x01 };   /* 345 = 172,5 mm */
    struct cps_cp_req r;

    TEST_ASSERT_EQUAL(PM_OK, cps_cp_decode(req, sizeof(req), &r));
    TEST_ASSERT_EQUAL_UINT8(CPS_CP_SET_CRANK_LENGTH, r.opcode);
    TEST_ASSERT_EQUAL_UINT32(345U, r.value);
}

static void test_set_cumulative_value_carries_a_uint32(void)
{
    uint8_t req[] = { CPS_CP_SET_CUMULATIVE, 0x78, 0x56, 0x34, 0x12 };
    struct cps_cp_req r;

    TEST_ASSERT_EQUAL(PM_OK, cps_cp_decode(req, sizeof(req), &r));
    TEST_ASSERT_EQUAL_UINT32(0x12345678U, r.value);
}

static void test_update_location_carries_a_uint8(void)
{
    uint8_t req[] = { CPS_CP_UPDATE_LOCATION, CPS_LOC_RIGHT_CRANK };
    struct cps_cp_req r;

    TEST_ASSERT_EQUAL(PM_OK, cps_cp_decode(req, sizeof(req), &r));
    TEST_ASSERT_EQUAL_UINT32(6U, r.value);
}

static void test_requests_without_parameter_are_one_byte(void)
{
    uint8_t ops[] = { CPS_CP_REQ_LOCATIONS, CPS_CP_REQ_CRANK_LENGTH, CPS_CP_REQ_CHAIN_LENGTH,
                      CPS_CP_REQ_CHAIN_WEIGHT, CPS_CP_REQ_SPAN_LENGTH, CPS_CP_START_OFFSET_COMP,
                      CPS_CP_REQ_SAMPLING_RATE, CPS_CP_REQ_FACTORY_DATE,
                      CPS_CP_START_ENHANCED_OFFSET };
    struct cps_cp_req r;

    for (size_t i = 0U; i < sizeof(ops); i++) {
        uint8_t req[2] = { ops[i], 0x00 };

        TEST_ASSERT_EQUAL(PM_OK, cps_cp_decode(req, 1U, &r));
        TEST_ASSERT_EQUAL_UINT8(ops[i], r.opcode);
        TEST_ASSERT_EQUAL_UINT32(0U, r.value);
        /* a parameter that should not be there is an invalid request */
        TEST_ASSERT_EQUAL(PM_EINVAL, cps_cp_decode(req, 2U, &r));
    }
}

static void test_wrong_lengths_and_empty_requests_are_invalid(void)
{
    uint8_t req[] = { CPS_CP_SET_CRANK_LENGTH, 0x59 };
    struct cps_cp_req r;

    TEST_ASSERT_EQUAL(PM_EINVAL, cps_cp_decode(req, 2U, &r));     /* one byte short */
    TEST_ASSERT_EQUAL(PM_EINVAL, cps_cp_decode(req, 0U, &r));
    TEST_ASSERT_EQUAL_UINT8(0U, r.opcode);
}

static void test_unknown_opcode_decodes_for_a_not_supported_answer(void)
{
    uint8_t req[] = { 0x7F, 0x01, 0x02 };
    struct cps_cp_req r;

    TEST_ASSERT_EQUAL(PM_OK, cps_cp_decode(req, sizeof(req), &r));
    TEST_ASSERT_EQUAL_UINT8(0x7F, r.opcode);
    TEST_ASSERT_EQUAL_UINT32(0U, r.value);
}

static void test_response_is_code_opcode_result_then_parameter(void)
{
    uint8_t buf[CPS_CP_RESP_MAX_LEN];
    uint8_t want[] = { 0x20, CPS_CP_REQ_CRANK_LENGTH, CPS_CP_SUCCESS, 0x59, 0x01 };

    TEST_ASSERT_EQUAL_size_t(5U, cps_cp_encode_u16(CPS_CP_REQ_CRANK_LENGTH, CPS_CP_SUCCESS, 345U,
                                                   buf, sizeof(buf)));
    TEST_ASSERT_EQUAL_UINT8_ARRAY(want, buf, sizeof(want));

    /* no parameter */
    TEST_ASSERT_EQUAL_size_t(3U, cps_cp_encode_response(CPS_CP_SET_CHAIN_LENGTH,
                                                        CPS_CP_NOT_SUPPORTED, NULL, 0U, buf,
                                                        sizeof(buf)));
    TEST_ASSERT_EQUAL_UINT8(0x20, buf[0]);
    TEST_ASSERT_EQUAL_UINT8(CPS_CP_SET_CHAIN_LENGTH, buf[1]);
    TEST_ASSERT_EQUAL_UINT8(CPS_CP_NOT_SUPPORTED, buf[2]);

    /* the offset of the compensation is a signed 16-bit value */
    TEST_ASSERT_EQUAL_size_t(5U, cps_cp_encode_u16(CPS_CP_START_OFFSET_COMP, CPS_CP_SUCCESS,
                                                   (uint16_t)(int16_t)-2, buf, sizeof(buf)));
    TEST_ASSERT_EQUAL_UINT8(0xFE, buf[3]);
    TEST_ASSERT_EQUAL_UINT8(0xFF, buf[4]);

    TEST_ASSERT_EQUAL_size_t(0U, cps_cp_encode_u16(CPS_CP_START_OFFSET_COMP, CPS_CP_SUCCESS, 0U,
                                                   buf, 4U));
}

static void test_factory_date_is_seven_bytes(void)
{
    struct cps_date d = { .year = 2026U, .month = 9U, .day = 27U, .hours = 14U, .minutes = 5U,
                          .seconds = 59U };
    uint8_t buf[CPS_CP_RESP_MAX_LEN];
    uint8_t want[] = { 0x20, CPS_CP_REQ_FACTORY_DATE, CPS_CP_SUCCESS, 0xEA, 0x07, 9, 27, 14, 5,
                       59 };

    TEST_ASSERT_EQUAL_size_t(10U, cps_cp_encode_date(CPS_CP_SUCCESS, &d, buf, sizeof(buf)));
    TEST_ASSERT_EQUAL_UINT8_ARRAY(want, buf, sizeof(want));
    TEST_ASSERT_EQUAL_size_t(0U, cps_cp_encode_date(CPS_CP_SUCCESS, &d, buf, 9U));
}

static void test_content_mask_with_reserved_bits_is_invalid(void)
{
    TEST_ASSERT_TRUE(cps_mask_valid(0U));
    TEST_ASSERT_TRUE(cps_mask_valid(CPS_MASK_VALID));
    TEST_ASSERT_FALSE(cps_mask_valid(0x0200U));
    TEST_ASSERT_FALSE(cps_mask_valid(0xFFFFU));
}

/* ---------------------------------------------------------------- vector */

static void test_vector_header_then_as_many_torques_as_fit(void)
{
    struct cps_vector_hdr h = {
        .has_crank = true, .crank_revs = 0x0102U, .crank_time_1024 = 0x0304U,
        .has_first_angle = true, .first_angle_deg = 180U,
        .torque_array = true, .direction = CPS_VEC_DIR_TANGENTIAL,
    };
    int16_t values[20];
    uint8_t buf[20];    /* header 7 + 6 values of 2 bytes, 1 byte left over */
    size_t used = 0U;

    for (int16_t i = 0; i < 20; i++) {
        values[i] = (int16_t)(i - 3);
    }
    /* flags: crank (1) + angle (2) + torque array (8) + tangential (0x10) = 0x1B */
    TEST_ASSERT_EQUAL_size_t(19U, cps_encode_vector(&h, values, 20U, buf, sizeof(buf), &used));
    TEST_ASSERT_EQUAL_size_t(6U, used);
    TEST_ASSERT_EQUAL_UINT8(0x1B, buf[0]);
    TEST_ASSERT_EQUAL_UINT8(0x02, buf[1]);
    TEST_ASSERT_EQUAL_UINT8(0x01, buf[2]);
    TEST_ASSERT_EQUAL_UINT8(0x04, buf[3]);
    TEST_ASSERT_EQUAL_UINT8(0x03, buf[4]);
    TEST_ASSERT_EQUAL_UINT8(0xB4, buf[5]);   /* 180 */
    TEST_ASSERT_EQUAL_UINT8(0x00, buf[6]);
    TEST_ASSERT_EQUAL_UINT8(0xFD, buf[7]);   /* -3 */
    TEST_ASSERT_EQUAL_UINT8(0xFF, buf[8]);
    TEST_ASSERT_EQUAL_UINT8(0x02, buf[17]);  /* the sixth value, 2 */
    TEST_ASSERT_EQUAL_UINT8(0x00, buf[18]);
}

static void test_vector_without_crank_or_angle_is_flags_and_forces(void)
{
    struct cps_vector_hdr h = { .torque_array = false, .direction = CPS_VEC_DIR_UNKNOWN };
    int16_t values[] = { 100, 200 };
    uint8_t buf[8];
    size_t used = 0U;

    TEST_ASSERT_EQUAL_size_t(5U, cps_encode_vector(&h, values, 2U, buf, sizeof(buf), &used));
    TEST_ASSERT_EQUAL_size_t(2U, used);
    TEST_ASSERT_EQUAL_UINT8(CPS_VEC_FORCE_ARRAY, buf[0]);
    TEST_ASSERT_EQUAL_UINT8(0x64, buf[1]);
    TEST_ASSERT_EQUAL_UINT8(0xC8, buf[3]);
}

static void test_vector_with_no_room_for_a_value_clears_the_array_flag(void)
{
    struct cps_vector_hdr h = { .has_crank = true, .torque_array = true };
    int16_t values[] = { 1 };
    uint8_t buf[8];
    size_t used = 9U;

    TEST_ASSERT_EQUAL_size_t(5U, cps_encode_vector(&h, values, 1U, buf, 6U, &used));
    TEST_ASSERT_EQUAL_size_t(0U, used);
    TEST_ASSERT_EQUAL_UINT8(CPS_VEC_CRANK_REV, buf[0]);
    /* not even the header */
    TEST_ASSERT_EQUAL_size_t(0U, cps_encode_vector(&h, values, 1U, buf, 4U, &used));
    /* no values at all: no array flag, no error */
    TEST_ASSERT_EQUAL_size_t(5U, cps_encode_vector(&h, values, 0U, buf, sizeof(buf), &used));
    TEST_ASSERT_EQUAL_UINT8(CPS_VEC_CRANK_REV, buf[0]);
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_power_alone_is_four_bytes_with_no_flag);
    RUN_TEST(test_negative_power_is_a_signed_int16);
    RUN_TEST(test_every_field_of_the_meter_in_wire_order);
    RUN_TEST(test_balance_reference_flag_follows_the_left_leg);
    RUN_TEST(test_the_content_mask_drops_fields_and_their_flags);
    RUN_TEST(test_a_short_buffer_gives_zero);
    RUN_TEST(test_feature_is_four_little_endian_bytes);
    RUN_TEST(test_meter_features_are_a_crank_torque_meter_not_a_distributed_one);
    RUN_TEST(test_set_crank_length_carries_a_uint16_in_half_millimetres);
    RUN_TEST(test_set_cumulative_value_carries_a_uint32);
    RUN_TEST(test_update_location_carries_a_uint8);
    RUN_TEST(test_requests_without_parameter_are_one_byte);
    RUN_TEST(test_wrong_lengths_and_empty_requests_are_invalid);
    RUN_TEST(test_unknown_opcode_decodes_for_a_not_supported_answer);
    RUN_TEST(test_response_is_code_opcode_result_then_parameter);
    RUN_TEST(test_factory_date_is_seven_bytes);
    RUN_TEST(test_content_mask_with_reserved_bits_is_invalid);
    RUN_TEST(test_vector_header_then_as_many_torques_as_fit);
    RUN_TEST(test_vector_without_crank_or_angle_is_flags_and_forces);
    RUN_TEST(test_vector_with_no_room_for_a_value_clears_the_array_flag);
    return UNITY_END();
}
