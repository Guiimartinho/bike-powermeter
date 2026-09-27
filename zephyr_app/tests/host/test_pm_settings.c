/*
 * Tests of model/pm_settings.c: the defaults, every limit, the 60-byte blob
 * with its version and CRC, and the text keys of $CFG.
 */

#include <math.h>
#include <string.h>

#include "model/pm_settings.h"
#include "model/pm_wire.h"
#include "unity.h"

static struct pm_settings s;

void setUp(void)
{
    pm_settings_defaults(&s);
}

void tearDown(void)
{
}

/* -------------------------------------------------------------- defaults */

static void test_defaults_are_valid_and_not_calibrated(void)
{
    TEST_ASSERT_EQUAL(PM_OK, pm_settings_validate(&s));
    TEST_ASSERT_FALSE(pm_settings_calibrated(&s));
    TEST_ASSERT_EQUAL_UINT16(345U, s.crank_length_half_mm);
    TEST_ASSERT_EQUAL_UINT16(50U, s.sensor_radius_mm);
    TEST_ASSERT_EQUAL_UINT8(PM_SIDE_LEFT, s.side);
    TEST_ASSERT_EQUAL_INT8(1, s.tangential_sign);
    TEST_ASSERT_EQUAL_UINT16(175U, s.sample_rate_sps);
    TEST_ASSERT_TRUE(s.auto_zero);
    TEST_ASSERT_EQUAL_INT32(41943, s.auto_zero_max_step);
    TEST_ASSERT_EQUAL_UINT16(0U, s.ant_device_number);
    TEST_ASSERT_EQUAL_STRING("PM", s.name);
}

static void test_a_slope_makes_it_calibrated(void)
{
    s.cal.slope_unm = 1000.0f;
    TEST_ASSERT_EQUAL(PM_OK, pm_settings_validate(&s));
    TEST_ASSERT_TRUE(pm_settings_calibrated(&s));
}

/* ---------------------------------------------------------------- limits */

static void test_every_limit_is_enforced(void)
{
    s.crank_length_half_mm = PM_CRANK_MIN_HALF_MM - 1U;
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_validate(&s));
    s.crank_length_half_mm = PM_CRANK_MAX_HALF_MM + 1U;
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_validate(&s));
    s.crank_length_half_mm = PM_CRANK_MAX_HALF_MM;
    TEST_ASSERT_EQUAL(PM_OK, pm_settings_validate(&s));

    s.sensor_radius_mm = PM_RADIUS_MIN_MM - 1U;
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_validate(&s));
    s.sensor_radius_mm = PM_RADIUS_MAX_MM + 1U;
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_validate(&s));
    s.sensor_radius_mm = PM_RADIUS_MIN_MM;
    TEST_ASSERT_EQUAL(PM_OK, pm_settings_validate(&s));

    s.side = 7U;
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_validate(&s));
    s.side = PM_SIDE_RIGHT;
    TEST_ASSERT_EQUAL(PM_OK, pm_settings_validate(&s));

    s.tangential_sign = 0;
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_validate(&s));
    s.tangential_sign = -1;
    TEST_ASSERT_EQUAL(PM_OK, pm_settings_validate(&s));

    s.sample_rate_sps = 100U;
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_validate(&s));
    s.sample_rate_sps = 1000U;
    TEST_ASSERT_EQUAL(PM_OK, pm_settings_validate(&s));

    s.auto_zero_max_step = -1;
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_validate(&s));
    s.auto_zero_max_step = PM_AUTO_ZERO_STEP_MAX + 1;
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_validate(&s));
    s.auto_zero_max_step = 0;
    TEST_ASSERT_EQUAL(PM_OK, pm_settings_validate(&s));
}

static void test_calibration_limits(void)
{
    s.cal.slope_unm = -1.0f;
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_validate(&s));
    s.cal.slope_unm = NAN;
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_validate(&s));
    s.cal.slope_unm = 1000.0f;
    s.cal.t0_c = 100.0f;    /* bridge_cal_valid refuses it once there is a slope */
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_validate(&s));
    s.cal.t0_c = 25.0f;
    s.cal.zero_code = 8000000;
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_validate(&s));
    s.cal.zero_code = 0;
    s.cal.k2 = INFINITY;
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_validate(&s));
    s.cal.k2 = 0.0f;
    TEST_ASSERT_EQUAL(PM_OK, pm_settings_validate(&s));
    /* without a slope the other fields are still checked */
    s.cal.slope_unm = 0.0f;
    s.cal.t0_c = NAN;
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_validate(&s));
}

static void test_date_and_name_limits(void)
{
    s.cal_year = 2019U;
    s.cal_month = 1U;
    s.cal_day = 1U;
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_validate(&s));
    s.cal_year = 2026U;
    s.cal_month = 13U;
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_validate(&s));
    s.cal_month = 12U;
    s.cal_day = 0U;
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_validate(&s));
    s.cal_day = 31U;
    TEST_ASSERT_EQUAL(PM_OK, pm_settings_validate(&s));

    s.name[0] = '\0';
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_validate(&s));
    (void)strcpy(s.name, "PM,1");
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_validate(&s));
    (void)strcpy(s.name, "PM\x01");
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_validate(&s));
    (void)memset(s.name, 'A', sizeof(s.name));    /* no terminator */
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_validate(&s));
    (void)strcpy(s.name, "PM-CRANK-1");
    TEST_ASSERT_EQUAL(PM_OK, pm_settings_validate(&s));
}

/* ------------------------------------------------------------------ blob */

static void test_crc16_ccitt_false_check_value(void)
{
    /* the check value of CRC-16/CCITT-FALSE for "123456789" is 0x29B1 */
    TEST_ASSERT_EQUAL_HEX16(0x29B1, pm_crc16((const uint8_t *)"123456789", 9U));
    TEST_ASSERT_EQUAL_HEX16(0xFFFF, pm_crc16((const uint8_t *)"", 0U));
}

static void test_blob_is_sixty_bytes_with_version_first_and_crc_last(void)
{
    uint8_t buf[PM_SETTINGS_WIRE_LEN];

    s.cal.zero_code = -2;
    s.cal.slope_unm = 1.5f;
    s.ant_device_number = 0xBEEFU;
    s.cal_year = 2026U;
    s.cal_month = 9U;
    s.cal_day = 27U;
    TEST_ASSERT_EQUAL_size_t(60U, pm_settings_serialize(&s, buf, sizeof(buf)));
    TEST_ASSERT_EQUAL_UINT8(1U, buf[0]);
    TEST_ASSERT_EQUAL_UINT8(0U, buf[1]);
    TEST_ASSERT_EQUAL_UINT8(0x59, buf[2]);      /* 345 */
    TEST_ASSERT_EQUAL_UINT8(0x01, buf[3]);
    TEST_ASSERT_EQUAL_UINT8(50U, buf[4]);
    TEST_ASSERT_EQUAL_UINT8(PM_SIDE_LEFT, buf[6]);
    TEST_ASSERT_EQUAL_UINT8(0x01, buf[7]);
    TEST_ASSERT_EQUAL_UINT8(0xFE, buf[8]);      /* -2 */
    TEST_ASSERT_EQUAL_UINT8(0xFF, buf[11]);
    TEST_ASSERT_EQUAL_UINT8(0x00, buf[12]);     /* 1,5f = 0x3FC00000 */
    TEST_ASSERT_EQUAL_UINT8(0xC0, buf[14]);
    TEST_ASSERT_EQUAL_UINT8(0x3F, buf[15]);
    TEST_ASSERT_EQUAL_UINT8(0xAF, buf[33]);     /* 175 */
    TEST_ASSERT_EQUAL_UINT8(0x00, buf[34]);
    TEST_ASSERT_EQUAL_UINT8(0x01, buf[35]);     /* auto zero */
    TEST_ASSERT_EQUAL_UINT8(0xEF, buf[40]);     /* ANT number */
    TEST_ASSERT_EQUAL_UINT8(0xBE, buf[41]);
    TEST_ASSERT_EQUAL_UINT8(0xEA, buf[42]);     /* 2026 */
    TEST_ASSERT_EQUAL_UINT8(0x07, buf[43]);
    TEST_ASSERT_EQUAL_UINT8(9U, buf[44]);
    TEST_ASSERT_EQUAL_UINT8(27U, buf[45]);
    TEST_ASSERT_EQUAL_UINT8('P', buf[46]);
    TEST_ASSERT_EQUAL_UINT8('M', buf[47]);
    TEST_ASSERT_EQUAL_UINT8(0U, buf[48]);
    TEST_ASSERT_EQUAL_HEX16(pm_crc16(buf, 58U), (uint16_t)(buf[58] | (buf[59] << 8)));
    TEST_ASSERT_EQUAL_size_t(0U, pm_settings_serialize(&s, buf, 59U));
}

static void test_blob_round_trip_keeps_every_field(void)
{
    uint8_t buf[PM_SETTINGS_WIRE_LEN];
    struct pm_settings r;

    s.crank_length_half_mm = 350U;
    s.sensor_radius_mm = 65U;
    s.side = PM_SIDE_RIGHT;
    s.tangential_sign = -1;
    s.cal.zero_code = -123456;
    s.cal.slope_unm = 987.654f;
    s.cal.t0_c = 21.5f;
    s.cal.k1 = -1.5f;
    s.cal.k2 = 0.02f;
    s.cal.k3 = 1e-4f;
    s.cal.temp_calibrated = true;
    s.sample_rate_sps = 330U;
    s.auto_zero = false;
    s.auto_zero_max_step = 12345;
    s.ant_device_number = 4242U;
    s.cal_year = 2027U;
    s.cal_month = 1U;
    s.cal_day = 2U;
    (void)strcpy(s.name, "PM-ABCD");
    TEST_ASSERT_EQUAL(PM_OK, pm_settings_validate(&s));
    TEST_ASSERT_EQUAL_size_t(60U, pm_settings_serialize(&s, buf, sizeof(buf)));
    (void)memset(&r, 0xAA, sizeof(r));
    TEST_ASSERT_EQUAL(PM_OK, pm_settings_deserialize(buf, sizeof(buf), &r));
    TEST_ASSERT_EQUAL_MEMORY(&s, &r, sizeof(s));
}

static void test_blob_with_bad_length_version_crc_or_values_is_refused(void)
{
    uint8_t buf[PM_SETTINGS_WIRE_LEN];
    struct pm_settings r;

    pm_settings_defaults(&r);
    (void)pm_settings_serialize(&s, buf, sizeof(buf));

    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_deserialize(buf, 59U, &r));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_deserialize(buf, 61U, &r));

    buf[10] ^= 0x01U;    /* a flipped bit: the CRC catches it */
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_deserialize(buf, sizeof(buf), &r));
    buf[10] ^= 0x01U;

    buf[0] = 2U;         /* another version, CRC fixed */
    (void)pm_put_u16(buf, 58U, pm_crc16(buf, 58U));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_deserialize(buf, sizeof(buf), &r));
    buf[0] = 1U;

    buf[6] = 9U;         /* an impossible side, CRC fixed */
    (void)pm_put_u16(buf, 58U, pm_crc16(buf, 58U));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_deserialize(buf, sizeof(buf), &r));
    /* the target was not touched */
    TEST_ASSERT_EQUAL_UINT8(PM_SIDE_LEFT, r.side);

    buf[6] = PM_SIDE_LEFT;
    (void)pm_put_u16(buf, 58U, pm_crc16(buf, 58U));
    TEST_ASSERT_EQUAL(PM_OK, pm_settings_deserialize(buf, sizeof(buf), &r));
}

static void test_blob_name_without_terminator_is_cut(void)
{
    uint8_t buf[PM_SETTINGS_WIRE_LEN];
    struct pm_settings r;

    (void)pm_settings_serialize(&s, buf, sizeof(buf));
    (void)memset(&buf[46], 'Z', PM_SETTINGS_NAME_LEN);
    (void)pm_put_u16(buf, 58U, pm_crc16(buf, 58U));
    TEST_ASSERT_EQUAL(PM_OK, pm_settings_deserialize(buf, sizeof(buf), &r));
    TEST_ASSERT_EQUAL_size_t(PM_SETTINGS_NAME_LEN - 1U, strlen(r.name));
}

/* ------------------------------------------------------------------ text */

static void test_keys_are_listed_in_order_and_end_with_null(void)
{
    TEST_ASSERT_EQUAL_STRING("crank", pm_settings_key(0U));
    TEST_ASSERT_EQUAL_STRING("name", pm_settings_key(16U));
    TEST_ASSERT_NULL(pm_settings_key(17U));
}

static void test_set_and_get_each_key_as_text(void)
{
    char buf[32];

    TEST_ASSERT_EQUAL(PM_OK, pm_settings_set_text(&s, "crank", "170"));
    TEST_ASSERT_EQUAL_UINT16(340U, s.crank_length_half_mm);
    TEST_ASSERT_EQUAL(PM_OK, pm_settings_set_text(&s, "crank", "172.5"));
    TEST_ASSERT_EQUAL_UINT16(345U, s.crank_length_half_mm);
    TEST_ASSERT_TRUE(pm_settings_get_text(&s, "crank", buf, sizeof(buf)) > 0U);
    TEST_ASSERT_EQUAL_STRING("172.5", buf);

    TEST_ASSERT_EQUAL(PM_OK, pm_settings_set_text(&s, "radius", "60"));
    TEST_ASSERT_EQUAL_UINT16(60U, s.sensor_radius_mm);
    (void)pm_settings_get_text(&s, "radius", buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING("60", buf);

    TEST_ASSERT_EQUAL(PM_OK, pm_settings_set_text(&s, "side", "R"));
    TEST_ASSERT_EQUAL_UINT8(PM_SIDE_RIGHT, s.side);
    (void)pm_settings_get_text(&s, "side", buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING("R", buf);
    TEST_ASSERT_EQUAL(PM_OK, pm_settings_set_text(&s, "side", "L"));
    (void)pm_settings_get_text(&s, "side", buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING("L", buf);

    TEST_ASSERT_EQUAL(PM_OK, pm_settings_set_text(&s, "sign", "-1"));
    TEST_ASSERT_EQUAL_INT8(-1, s.tangential_sign);
    (void)pm_settings_get_text(&s, "sign", buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING("-1", buf);

    TEST_ASSERT_EQUAL(PM_OK, pm_settings_set_text(&s, "zero", "-4096"));
    TEST_ASSERT_EQUAL_INT32(-4096, s.cal.zero_code);
    (void)pm_settings_get_text(&s, "zero", buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING("-4096", buf);

    TEST_ASSERT_EQUAL(PM_OK, pm_settings_set_text(&s, "slope", "1234.5"));
    TEST_ASSERT_FLOAT_WITHIN(1e-3f, 1234.5f, s.cal.slope_unm);
    (void)pm_settings_get_text(&s, "slope", buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING("1234.5", buf);

    TEST_ASSERT_EQUAL(PM_OK, pm_settings_set_text(&s, "t0", "22.25"));
    TEST_ASSERT_EQUAL(PM_OK, pm_settings_set_text(&s, "k1", "-2.5"));
    TEST_ASSERT_EQUAL(PM_OK, pm_settings_set_text(&s, "k2", "0.01"));
    TEST_ASSERT_EQUAL(PM_OK, pm_settings_set_text(&s, "k3", "1e-4"));
    TEST_ASSERT_EQUAL(PM_OK, pm_settings_set_text(&s, "tempcal", "1"));
    TEST_ASSERT_TRUE(s.cal.temp_calibrated);
    TEST_ASSERT_FLOAT_WITHIN(1e-4f, 22.25f, s.cal.t0_c);
    TEST_ASSERT_FLOAT_WITHIN(1e-4f, -2.5f, s.cal.k1);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.01f, s.cal.k2);
    TEST_ASSERT_FLOAT_WITHIN(1e-8f, 1e-4f, s.cal.k3);
    (void)pm_settings_get_text(&s, "t0", buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING("22.25", buf);
    (void)pm_settings_get_text(&s, "k1", buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING("-2.5", buf);
    (void)pm_settings_get_text(&s, "k2", buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING("0.01", buf);
    (void)pm_settings_get_text(&s, "k3", buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING("0.0001", buf);
    (void)pm_settings_get_text(&s, "tempcal", buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING("1", buf);

    TEST_ASSERT_EQUAL(PM_OK, pm_settings_set_text(&s, "rate", "330"));
    TEST_ASSERT_EQUAL_UINT16(330U, s.sample_rate_sps);
    (void)pm_settings_get_text(&s, "rate", buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING("330", buf);

    TEST_ASSERT_EQUAL(PM_OK, pm_settings_set_text(&s, "autozero", "0"));
    TEST_ASSERT_FALSE(s.auto_zero);
    (void)pm_settings_get_text(&s, "autozero", buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING("0", buf);

    TEST_ASSERT_EQUAL(PM_OK, pm_settings_set_text(&s, "azstep", "1000"));
    TEST_ASSERT_EQUAL_INT32(1000, s.auto_zero_max_step);
    (void)pm_settings_get_text(&s, "azstep", buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING("1000", buf);

    TEST_ASSERT_EQUAL(PM_OK, pm_settings_set_text(&s, "ant", "65535"));
    TEST_ASSERT_EQUAL_UINT16(65535U, s.ant_device_number);
    (void)pm_settings_get_text(&s, "ant", buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING("65535", buf);

    (void)pm_settings_get_text(&s, "caldate", buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING("0", buf);
    TEST_ASSERT_EQUAL(PM_OK, pm_settings_set_text(&s, "caldate", "2026-09-27"));
    TEST_ASSERT_EQUAL_UINT16(2026U, s.cal_year);
    TEST_ASSERT_EQUAL_UINT8(9U, s.cal_month);
    TEST_ASSERT_EQUAL_UINT8(27U, s.cal_day);
    (void)pm_settings_get_text(&s, "caldate", buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING("2026-09-27", buf);
    TEST_ASSERT_EQUAL(PM_OK, pm_settings_set_text(&s, "caldate", "0"));
    TEST_ASSERT_EQUAL_UINT16(0U, s.cal_year);

    TEST_ASSERT_EQUAL(PM_OK, pm_settings_set_text(&s, "name", "PM-1234"));
    TEST_ASSERT_EQUAL_STRING("PM-1234", s.name);
    (void)pm_settings_get_text(&s, "name", buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING("PM-1234", buf);

    TEST_ASSERT_EQUAL(PM_OK, pm_settings_validate(&s));
}

static void test_bad_text_values_change_nothing(void)
{
    struct pm_settings before = s;

    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "crank", "172.3"));   /* not a half */
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "crank", "abc"));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "crank", ""));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "crank", "99"));      /* below 100 mm */
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "crank", "-172.5"));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "radius", "60x"));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "radius", "70000"));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "side", "X"));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "sign", "2"));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "zero", "9999999999"));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "zero", "8000000"));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "slope", "nan"));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "slope", "-1"));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "t0", "warm"));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "k1", "1,5"));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "k2", ""));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "k3", "inf"));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "tempcal", "2"));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "rate", "100"));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "rate", "70000"));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "autozero", "yes"));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "azstep", "-5"));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "azstep", "99999999999"));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "ant", "65536"));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "caldate", "2026-13-01"));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "caldate", "2026/09/27"));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "caldate", "2026-09"));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "caldate", "2026-09-27x"));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "caldate", "x026-09-27"));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "caldate", "99999-09-27"));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "name", "PM-12345678901"));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "name", ""));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "colour", "red"));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, NULL, "1"));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_settings_set_text(&s, "crank", NULL));
    TEST_ASSERT_EQUAL_MEMORY(&before, &s, sizeof(s));
}

static void test_get_text_refuses_unknown_keys_and_short_buffers(void)
{
    char buf[4];

    TEST_ASSERT_EQUAL_size_t(0U, pm_settings_get_text(&s, "colour", buf, sizeof(buf)));
    TEST_ASSERT_EQUAL_size_t(0U, pm_settings_get_text(&s, "crank", buf, sizeof(buf)));
    TEST_ASSERT_EQUAL_STRING("", buf);
    TEST_ASSERT_EQUAL_size_t(0U, pm_settings_get_text(&s, "crank", buf, 0U));
    TEST_ASSERT_EQUAL_size_t(0U, pm_settings_get_text(&s, NULL, buf, sizeof(buf)));
    TEST_ASSERT_EQUAL_size_t(0U, pm_settings_get_text(&s, "crank", NULL, 4U));
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_defaults_are_valid_and_not_calibrated);
    RUN_TEST(test_a_slope_makes_it_calibrated);
    RUN_TEST(test_every_limit_is_enforced);
    RUN_TEST(test_calibration_limits);
    RUN_TEST(test_date_and_name_limits);
    RUN_TEST(test_crc16_ccitt_false_check_value);
    RUN_TEST(test_blob_is_sixty_bytes_with_version_first_and_crc_last);
    RUN_TEST(test_blob_round_trip_keeps_every_field);
    RUN_TEST(test_blob_with_bad_length_version_crc_or_values_is_refused);
    RUN_TEST(test_blob_name_without_terminator_is_cut);
    RUN_TEST(test_keys_are_listed_in_order_and_end_with_null);
    RUN_TEST(test_set_and_get_each_key_as_text);
    RUN_TEST(test_bad_text_values_change_nothing);
    RUN_TEST(test_get_text_refuses_unknown_keys_and_short_buffers);
    return UNITY_END();
}
