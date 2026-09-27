/*
 * Tests of model/bridge_calc.c against docs/06 (Da ponte ao torque):
 *   tau = s(T) (c - c0(T)), c0(T) = c0 + k1 dT + k2 dT^2, s(T) = s (1 + k3 dT).
 * A slope of 1000 µN·m per count makes 1 mN·m per count, which keeps the
 * expected values readable.
 */

#include <math.h>

#include "model/bridge_calc.h"
#include "unity.h"

static struct bridge_cal cal;

void setUp(void)
{
    cal.zero_code = 1000;
    cal.slope_unm = 1000.0f;
    cal.t0_c = 25.0f;
    cal.k1 = 0.0f;
    cal.k2 = 0.0f;
    cal.k3 = 0.0f;
    cal.temp_calibrated = false;
}

void tearDown(void)
{
}

/* ---------------------------------------------------------------- filter */

static void test_median3_needs_three_samples_then_returns_the_middle_one(void)
{
    struct bridge_filter f;
    int32_t out = 0;

    bridge_filter_reset(&f);
    TEST_ASSERT_FALSE(bridge_filter_median3(&f, 10, &out));
    TEST_ASSERT_FALSE(bridge_filter_median3(&f, 30, &out));
    TEST_ASSERT_TRUE(bridge_filter_median3(&f, 20, &out));
    TEST_ASSERT_EQUAL_INT32(20, out);
}

static void test_median3_removes_a_single_spike_in_every_position(void)
{
    struct bridge_filter f;
    int32_t out = 0;

    bridge_filter_reset(&f);
    (void)bridge_filter_median3(&f, 100, &out);
    (void)bridge_filter_median3(&f, 101, &out);
    /* spike as the newest sample */
    TEST_ASSERT_TRUE(bridge_filter_median3(&f, 90000, &out));
    TEST_ASSERT_EQUAL_INT32(101, out);
    /* the spike is now the oldest; the two new ones win */
    TEST_ASSERT_TRUE(bridge_filter_median3(&f, 102, &out));
    TEST_ASSERT_EQUAL_INT32(102, out);
    TEST_ASSERT_TRUE(bridge_filter_median3(&f, 103, &out));
    TEST_ASSERT_EQUAL_INT32(103, out);
    /* a negative spike replaces the oldest slot */
    TEST_ASSERT_TRUE(bridge_filter_median3(&f, -90000, &out));
    TEST_ASSERT_EQUAL_INT32(102, out);
    TEST_ASSERT_TRUE(bridge_filter_median3(&f, 104, &out));
    TEST_ASSERT_EQUAL_INT32(103, out);
}

static void test_median3_with_equal_samples_returns_that_value(void)
{
    struct bridge_filter f;
    int32_t out = 0;

    bridge_filter_reset(&f);
    (void)bridge_filter_median3(&f, 7, &out);
    (void)bridge_filter_median3(&f, 7, &out);
    TEST_ASSERT_TRUE(bridge_filter_median3(&f, 7, &out));
    TEST_ASSERT_EQUAL_INT32(7, out);
    /* reset forgets everything */
    bridge_filter_reset(&f);
    TEST_ASSERT_FALSE(bridge_filter_median3(&f, 1, &out));
}

/* ------------------------------------------------------------ zero, slope */

static void test_zero_and_slope_without_temperature_model_are_the_constants(void)
{
    TEST_ASSERT_FLOAT_WITHIN(0.001f, 1000.0f, bridge_zero_at(&cal, -10.0f));
    TEST_ASSERT_FLOAT_WITHIN(0.001f, 1000.0f, bridge_zero_at(&cal, 60.0f));
    TEST_ASSERT_FLOAT_WITHIN(0.001f, 1000.0f, bridge_slope_at(&cal, 60.0f));
}

static void test_zero_follows_the_second_order_model(void)
{
    cal.k1 = 2.0f;      /* counts per degC */
    cal.k2 = 0.1f;      /* counts per degC^2 */
    /* dT = 10: 1000 + 20 + 10 = 1030 */
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 1030.0f, bridge_zero_at(&cal, 35.0f));
    /* dT = -20: 1000 - 40 + 40 = 1000 */
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 1000.0f, bridge_zero_at(&cal, 5.0f));
}

static void test_slope_follows_the_first_order_model(void)
{
    cal.k3 = -0.001f;   /* -0,1 % per degC */
    /* dT = 20: 1000 (1 - 0,02) = 980 */
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 980.0f, bridge_slope_at(&cal, 45.0f));
}

/* ---------------------------------------------------------------- torque */

static void test_torque_is_slope_times_code_minus_zero(void)
{
    /* 1000 µN·m per count: 1 mN·m per count */
    TEST_ASSERT_EQUAL_INT32(0, bridge_torque_mnm(&cal, 1000, 25.0f));
    TEST_ASSERT_EQUAL_INT32(500, bridge_torque_mnm(&cal, 1500, 25.0f));
    TEST_ASSERT_EQUAL_INT32(-500, bridge_torque_mnm(&cal, 500, 25.0f));
    /* 21,2 N·m at 200 W and 90 rpm: 21200 counts above zero */
    TEST_ASSERT_EQUAL_INT32(21200, bridge_torque_mnm(&cal, 22200, 25.0f));
}

static void test_torque_uses_the_temperature_corrected_zero_and_slope(void)
{
    cal.k1 = 1.0f;
    cal.k3 = 0.01f;
    /* at 35 degC: zero 1010, slope 1100 -> (1510 - 1010) * 1,1 = 550 */
    TEST_ASSERT_EQUAL_INT32(550, bridge_torque_mnm(&cal, 1510, 35.0f));
}

static void test_torque_rounds_to_the_nearest_mnm(void)
{
    cal.slope_unm = 1500.0f;    /* 1,5 mN·m per count */
    TEST_ASSERT_EQUAL_INT32(2, bridge_torque_mnm(&cal, 1001, 25.0f));     /* 1,5 -> 2 */
    TEST_ASSERT_EQUAL_INT32(3, bridge_torque_mnm(&cal, 1002, 25.0f));     /* 3,0 */
    TEST_ASSERT_EQUAL_INT32(-2, bridge_torque_mnm(&cal, 999, 25.0f));     /* -1,5 -> -2 */
}

static void test_torque_saturates_at_both_ends(void)
{
    cal.slope_unm = 1000000.0f;   /* 1 N·m per count */
    TEST_ASSERT_EQUAL_INT32(BRIDGE_TORQUE_MAX_MNM, bridge_torque_mnm(&cal, 8000000, 25.0f));
    TEST_ASSERT_EQUAL_INT32(-BRIDGE_TORQUE_MAX_MNM, bridge_torque_mnm(&cal, -8000000, 25.0f));
}

/* ----------------------------------------------------------------- range */

static void test_code_in_range_is_within_80_percent_of_full_scale(void)
{
    const int32_t limit = (int32_t)(PM_ADC_FULL_SCALE * 80L / 100L);   /* 6710886 */

    TEST_ASSERT_TRUE(bridge_code_in_range(0));
    TEST_ASSERT_TRUE(bridge_code_in_range(limit - 1));
    TEST_ASSERT_TRUE(bridge_code_in_range(-(limit - 1)));
    TEST_ASSERT_FALSE(bridge_code_in_range(limit));
    TEST_ASSERT_FALSE(bridge_code_in_range(-limit));
    TEST_ASSERT_FALSE(bridge_code_in_range(PM_ADC_FULL_SCALE - 1));
}

/* --------------------------------------------------------------- validity */

static void test_cal_valid_accepts_the_default_constants(void)
{
    TEST_ASSERT_TRUE(bridge_cal_valid(&cal));
}

static void test_cal_valid_rejects_a_slope_that_is_not_positive_or_not_finite(void)
{
    cal.slope_unm = 0.0f;
    TEST_ASSERT_FALSE(bridge_cal_valid(&cal));
    cal.slope_unm = -1.0f;
    TEST_ASSERT_FALSE(bridge_cal_valid(&cal));
    cal.slope_unm = INFINITY;
    TEST_ASSERT_FALSE(bridge_cal_valid(&cal));
    cal.slope_unm = NAN;
    TEST_ASSERT_FALSE(bridge_cal_valid(&cal));
}

static void test_cal_valid_rejects_a_zero_out_of_range(void)
{
    cal.zero_code = 7000000;
    TEST_ASSERT_FALSE(bridge_cal_valid(&cal));
}

static void test_cal_valid_rejects_non_finite_coefficients(void)
{
    cal.k1 = NAN;
    TEST_ASSERT_FALSE(bridge_cal_valid(&cal));
    cal.k1 = 0.0f;
    cal.k2 = INFINITY;
    TEST_ASSERT_FALSE(bridge_cal_valid(&cal));
    cal.k2 = 0.0f;
    cal.k3 = NAN;
    TEST_ASSERT_FALSE(bridge_cal_valid(&cal));
}

static void test_cal_valid_rejects_an_implausible_reference_temperature(void)
{
    cal.t0_c = -41.0f;
    TEST_ASSERT_FALSE(bridge_cal_valid(&cal));
    cal.t0_c = 86.0f;
    TEST_ASSERT_FALSE(bridge_cal_valid(&cal));
    cal.t0_c = NAN;
    TEST_ASSERT_FALSE(bridge_cal_valid(&cal));
    cal.t0_c = 85.0f;
    TEST_ASSERT_TRUE(bridge_cal_valid(&cal));
}

/* ------------------------------------------------------------- pm_types */

static void test_ms_to_1024_rounds_and_wraps_like_the_protocols(void)
{
    TEST_ASSERT_EQUAL_UINT16(0, pm_ms_to_1024(0));
    TEST_ASSERT_EQUAL_UINT16(1024, pm_ms_to_1024(1000));
    TEST_ASSERT_EQUAL_UINT16(1, pm_ms_to_1024(1));          /* 1,024 -> 1 */
    TEST_ASSERT_EQUAL_UINT16(2, pm_ms_to_1024(2));          /* 2,048 -> 2 */
    TEST_ASSERT_EQUAL_UINT16(0, pm_ms_to_1024(64000));      /* wraps at 64 s */
    TEST_ASSERT_EQUAL_UINT16(1024, pm_ms_to_1024(65000));
}

static void test_clamp_i32_keeps_the_range(void)
{
    TEST_ASSERT_EQUAL_INT32(INT32_MAX, pm_clamp_i32((int64_t)INT32_MAX + 5));
    TEST_ASSERT_EQUAL_INT32(INT32_MIN, pm_clamp_i32((int64_t)INT32_MIN - 5));
    TEST_ASSERT_EQUAL_INT32(-7, pm_clamp_i32(-7));
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_median3_needs_three_samples_then_returns_the_middle_one);
    RUN_TEST(test_median3_removes_a_single_spike_in_every_position);
    RUN_TEST(test_median3_with_equal_samples_returns_that_value);
    RUN_TEST(test_zero_and_slope_without_temperature_model_are_the_constants);
    RUN_TEST(test_zero_follows_the_second_order_model);
    RUN_TEST(test_slope_follows_the_first_order_model);
    RUN_TEST(test_torque_is_slope_times_code_minus_zero);
    RUN_TEST(test_torque_uses_the_temperature_corrected_zero_and_slope);
    RUN_TEST(test_torque_rounds_to_the_nearest_mnm);
    RUN_TEST(test_torque_saturates_at_both_ends);
    RUN_TEST(test_code_in_range_is_within_80_percent_of_full_scale);
    RUN_TEST(test_cal_valid_accepts_the_default_constants);
    RUN_TEST(test_cal_valid_rejects_a_slope_that_is_not_positive_or_not_finite);
    RUN_TEST(test_cal_valid_rejects_a_zero_out_of_range);
    RUN_TEST(test_cal_valid_rejects_non_finite_coefficients);
    RUN_TEST(test_cal_valid_rejects_an_implausible_reference_temperature);
    RUN_TEST(test_ms_to_1024_rounds_and_wraps_like_the_protocols);
    RUN_TEST(test_clamp_i32_keeps_the_range);
    return UNITY_END();
}
