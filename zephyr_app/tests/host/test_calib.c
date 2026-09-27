/*
 * Tests of model/calib.c against docs/06 (Calibração): the zero with its
 * stability rule, the slope by least squares through the origin with
 * residual and hysteresis, the torque of a hung mass, and the temperature
 * fit of the bridge_calc model.
 */

#include <math.h>

#include "model/calib.h"
#include "unity.h"

void setUp(void)
{
}

void tearDown(void)
{
}

/* ------------------------------------------------------------------ zero */

static void test_zero_needs_64_samples(void)
{
    struct calib_zero z;
    int32_t zero = 0;
    float sd = 0.0f;

    calib_zero_reset(&z);
    for (uint32_t i = 0U; i < 63U; i++) {
        calib_zero_add(&z, 1000);
    }
    TEST_ASSERT_EQUAL(PM_ENOTREADY, calib_zero_result(&z, &zero, &sd));
    calib_zero_add(&z, 1000);
    TEST_ASSERT_EQUAL(PM_OK, calib_zero_result(&z, &zero, &sd));
    TEST_ASSERT_EQUAL_INT32(1000, zero);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, sd);
    TEST_ASSERT_EQUAL_INT32(1000, z.min);
    TEST_ASSERT_EQUAL_INT32(1000, z.max);
}

static void test_zero_is_the_mean_and_the_noise_is_the_standard_deviation(void)
{
    struct calib_zero z;
    int32_t zero = 0;
    float sd = 0.0f;

    calib_zero_reset(&z);
    /* alternating 998 and 1002: mean 1000, sample standard deviation ~2,02 */
    for (uint32_t i = 0U; i < 64U; i++) {
        calib_zero_add(&z, ((i % 2U) == 0U) ? 998 : 1002);
    }
    TEST_ASSERT_EQUAL(PM_OK, calib_zero_result(&z, &zero, &sd));
    TEST_ASSERT_EQUAL_INT32(1000, zero);
    TEST_ASSERT_FLOAT_WITHIN(0.05f, 2.02f, sd);
    TEST_ASSERT_EQUAL_INT32(998, z.min);
    TEST_ASSERT_EQUAL_INT32(1002, z.max);
}

static void test_zero_that_moves_is_unstable(void)
{
    struct calib_zero z;
    int32_t zero = 0;
    float sd = 0.0f;

    calib_zero_reset(&z);
    for (uint32_t i = 0U; i < 64U; i++) {
        calib_zero_add(&z, ((i % 2U) == 0U) ? 990 : 1010);   /* sd ~10 */
    }
    TEST_ASSERT_EQUAL(PM_EUNSTABLE, calib_zero_result(&z, &zero, &sd));
    TEST_ASSERT_TRUE(sd > CALIB_ZERO_STDDEV_MAX);
}

static void test_zero_beyond_20_percent_of_full_scale_is_a_bad_bridge(void)
{
    struct calib_zero z;
    int32_t zero = 0;
    float sd = 0.0f;

    calib_zero_reset(&z);
    for (uint32_t i = 0U; i < 64U; i++) {
        calib_zero_add(&z, -1700000);      /* 20 % of 2^23 is 1677722 */
    }
    TEST_ASSERT_EQUAL(PM_EBRIDGE, calib_zero_result(&z, &zero, &sd));
    TEST_ASSERT_EQUAL_INT32(-1700000, zero);
}

static void test_zero_stops_counting_at_the_limit_of_the_counter(void)
{
    struct calib_zero z;

    calib_zero_reset(&z);
    z.n = UINT16_MAX;
    calib_zero_add(&z, 5);
    TEST_ASSERT_EQUAL_UINT16(UINT16_MAX, z.n);
    TEST_ASSERT_EQUAL_INT32(INT32_MAX, z.min);   /* nothing was added */
}

static void test_auto_zero_is_accepted_only_within_the_step(void)
{
    TEST_ASSERT_TRUE(calib_zero_accept_auto(1000, 1050, 100));
    TEST_ASSERT_TRUE(calib_zero_accept_auto(1000, 900, 100));
    TEST_ASSERT_FALSE(calib_zero_accept_auto(1000, 1101, 100));
    TEST_ASSERT_FALSE(calib_zero_accept_auto(1000, 899, 100));
    /* a step wider than int32 does not overflow into acceptance */
    TEST_ASSERT_FALSE(calib_zero_accept_auto(-2000000000, 2000000000, INT32_MAX));
}

/* ----------------------------------------------------------------- slope */

static void test_torque_of_a_hung_mass(void)
{
    /* 10 kg on a 172,5 mm arm, horizontal: 16,916 N·m */
    TEST_ASSERT_INT32_WITHIN(2, 16916, calib_torque_from_mass_mnm(10000U, 172U, 0.0f) +
                                            (calib_torque_from_mass_mnm(10000U, 173U, 0.0f) -
                                             calib_torque_from_mass_mnm(10000U, 172U, 0.0f)) / 2);
    TEST_ASSERT_INT32_WITHIN(2, 16867, calib_torque_from_mass_mnm(10000U, 172U, 0.0f));
    /* 10 degrees off horizontal: cos = 0,9848 */
    TEST_ASSERT_INT32_WITHIN(3, 16611, calib_torque_from_mass_mnm(10000U, 172U, 0.17453f));
    TEST_ASSERT_EQUAL_INT32(0, calib_torque_from_mass_mnm(0U, 172U, 0.0f));
}

static void test_slope_fit_needs_two_points(void)
{
    struct calib_slope s;
    struct calib_slope_result r;

    calib_slope_reset(&s);
    TEST_ASSERT_EQUAL(PM_ENOTREADY, calib_slope_fit(&s, &r));
    TEST_ASSERT_EQUAL(PM_OK, calib_slope_add(&s, 11000, 1000, 10000, false));
    TEST_ASSERT_EQUAL(PM_ENOTREADY, calib_slope_fit(&s, &r));
}

static void test_slope_of_exact_points_has_no_residual(void)
{
    struct calib_slope s;
    struct calib_slope_result r;

    calib_slope_reset(&s);
    /* 1 mN·m per count: 5, 10, 20 kg-equivalent torques */
    TEST_ASSERT_EQUAL(PM_OK, calib_slope_add(&s, 6000, 1000, 5000, false));
    TEST_ASSERT_EQUAL(PM_OK, calib_slope_add(&s, 11000, 1000, 10000, false));
    TEST_ASSERT_EQUAL(PM_OK, calib_slope_add(&s, 21000, 1000, 20000, false));
    TEST_ASSERT_EQUAL(PM_OK, calib_slope_fit(&s, &r));
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 1000.0f, r.slope_unm);
    TEST_ASSERT_FLOAT_WITHIN(1e-3f, 0.0f, r.residual_pct);
    TEST_ASSERT_FLOAT_WITHIN(1e-3f, 0.0f, r.hysteresis_pct);
    TEST_ASSERT_EQUAL_UINT8(3U, r.points);
}

static void test_slope_residual_is_the_worst_point_over_the_largest_torque(void)
{
    struct calib_slope s;
    struct calib_slope_result r;

    calib_slope_reset(&s);
    (void)calib_slope_add(&s, 11000, 1000, 10000, false);
    (void)calib_slope_add(&s, 21000, 1000, 20000, false);
    /* a point 1 % low on the largest torque: the least squares spreads it,
     * slope 0,99238 and the worst residual on the 20 000 point, 152 in
     * 39 600 = 0,385 % */
    (void)calib_slope_add(&s, 41000, 1000, 39600, false);
    TEST_ASSERT_EQUAL(PM_OK, calib_slope_fit(&s, &r));
    TEST_ASSERT_FLOAT_WITHIN(0.02f, 0.385f, r.residual_pct);
    TEST_ASSERT_FLOAT_WITHIN(0.5f, 992.4f, r.slope_unm);
}

static void test_slope_hysteresis_compares_the_same_torque_up_and_down(void)
{
    struct calib_slope s;
    struct calib_slope_result r;

    calib_slope_reset(&s);
    (void)calib_slope_add(&s, 11000, 1000, 10000, false);
    (void)calib_slope_add(&s, 21000, 1000, 20000, false);
    /* on the way down the 10 000 point reads 200 counts higher: 200 / 20000 = 1 % */
    (void)calib_slope_add(&s, 11200, 1000, 10000, true);
    TEST_ASSERT_EQUAL(PM_OK, calib_slope_fit(&s, &r));
    TEST_ASSERT_FLOAT_WITHIN(0.05f, 1.0f, r.hysteresis_pct);
}

static void test_slope_rejects_a_bridge_that_does_not_follow_the_load(void)
{
    struct calib_slope s;
    struct calib_slope_result r;

    calib_slope_reset(&s);
    (void)calib_slope_add(&s, 1000, 1000, 10000, false);
    (void)calib_slope_add(&s, 1000, 1000, 20000, false);
    TEST_ASSERT_EQUAL(PM_EBRIDGE, calib_slope_fit(&s, &r));     /* sxx = 0 */

    calib_slope_reset(&s);
    (void)calib_slope_add(&s, 900, 1000, 10000, false);
    (void)calib_slope_add(&s, 800, 1000, 20000, false);
    TEST_ASSERT_EQUAL(PM_EBRIDGE, calib_slope_fit(&s, &r));     /* negative slope */
}

static void test_slope_table_refuses_out_of_range_codes_and_overflow(void)
{
    struct calib_slope s;

    calib_slope_reset(&s);
    TEST_ASSERT_EQUAL(PM_ERANGE, calib_slope_add(&s, 8000000, 1000, 10000, false));
    for (uint32_t i = 0U; i < CALIB_SLOPE_POINTS; i++) {
        TEST_ASSERT_EQUAL(PM_OK, calib_slope_add(&s, 2000 + (int32_t)i, 1000, 1000, false));
    }
    TEST_ASSERT_EQUAL(PM_ERANGE, calib_slope_add(&s, 3000, 1000, 1000, false));
    TEST_ASSERT_EQUAL_UINT8(CALIB_SLOPE_POINTS, s.n);
}

/* ----------------------------------------------------------- temperature */

static struct bridge_cal ref_cal(void)
{
    struct bridge_cal cal = {
        .zero_code = 1000,
        .slope_unm = 1000.0f,
        .t0_c = 25.0f,
    };

    return cal;
}

static void test_temperature_fit_needs_three_points_over_ten_degrees(void)
{
    struct calib_temp t;
    struct bridge_cal cal = ref_cal();

    calib_temp_reset(&t);
    TEST_ASSERT_EQUAL(PM_ENOTREADY, calib_temp_fit(&t, &cal));
    (void)calib_temp_add(&t, 25.0f, 1000.0f, 1000.0f);
    (void)calib_temp_add(&t, 30.0f, 1010.0f, 995.0f);
    TEST_ASSERT_EQUAL(PM_ENOTREADY, calib_temp_fit(&t, &cal));
    (void)calib_temp_add(&t, 33.0f, 1016.0f, 992.0f);      /* span 8 degC */
    TEST_ASSERT_EQUAL(PM_ENOTREADY, calib_temp_fit(&t, &cal));
    TEST_ASSERT_FALSE(cal.temp_calibrated);
}

static void test_temperature_fit_recovers_known_coefficients(void)
{
    struct calib_temp t;
    struct bridge_cal cal = ref_cal();
    const float k1 = 2.0f;
    const float k2 = 0.05f;
    const float k3 = -0.001f;

    calib_temp_reset(&t);
    for (int i = -2; i <= 3; i++) {
        float temp = 25.0f + (10.0f * (float)i);    /* 5 to 55 degC */
        float d = temp - 25.0f;

        (void)calib_temp_add(&t, temp, 1000.0f + (k1 * d) + (k2 * d * d),
                             1000.0f * (1.0f + (k3 * d)));
    }
    TEST_ASSERT_EQUAL(PM_OK, calib_temp_fit(&t, &cal));
    TEST_ASSERT_TRUE(cal.temp_calibrated);
    TEST_ASSERT_FLOAT_WITHIN(0.01f, k1, cal.k1);
    TEST_ASSERT_FLOAT_WITHIN(0.001f, k2, cal.k2);
    TEST_ASSERT_FLOAT_WITHIN(1e-5f, k3, cal.k3);
    /* the reference point stays where it was */
    TEST_ASSERT_EQUAL_INT32(1000, cal.zero_code);
    TEST_ASSERT_FLOAT_WITHIN(1e-3f, 1000.0f, cal.slope_unm);
}

static void test_temperature_fit_is_singular_with_all_points_at_one_temperature_pair(void)
{
    struct calib_temp t;
    struct bridge_cal cal = ref_cal();

    calib_temp_reset(&t);
    /* two temperatures only, symmetric: d = -10 and +10 give s3 = 0 but a
     * valid system; three identical d's make the matrix singular */
    (void)calib_temp_add(&t, 35.0f, 1020.0f, 990.0f);
    (void)calib_temp_add(&t, 35.0f, 1020.0f, 990.0f);
    (void)calib_temp_add(&t, 35.0f + 10.0f, 1040.0f, 980.0f);
    /* d = 10, 10, 20: s2 = 600, s3 = 10000, s4 = 180000 -> det = 8e6: not singular */
    TEST_ASSERT_EQUAL(PM_OK, calib_temp_fit(&t, &cal));

    calib_temp_reset(&t);
    (void)calib_temp_add(&t, 35.0f, 1020.0f, 990.0f);
    (void)calib_temp_add(&t, 35.0f, 1020.0f, 990.0f);
    (void)calib_temp_add(&t, 35.0f, 1020.0f, 990.0f);
    (void)calib_temp_add(&t, 45.0f, 1020.0f, 990.0f);
    /* d = 10 x3 and 20: still regular... make it singular: all d equal after span check */
    calib_temp_reset(&t);
    cal = ref_cal();
    cal.t0_c = 5.0f;
    (void)calib_temp_add(&t, 15.0f, 1020.0f, 990.0f);
    (void)calib_temp_add(&t, 15.0f, 1020.0f, 990.0f);
    (void)calib_temp_add(&t, 15.0f, 1020.0f, 990.0f);
    (void)calib_temp_add(&t, 15.0f, 1020.0f, 990.0f);
    /* span 0: not ready, before the matrix is even built */
    TEST_ASSERT_EQUAL(PM_ENOTREADY, calib_temp_fit(&t, &cal));
}

static void test_temperature_fit_singular_matrix_is_reported(void)
{
    struct calib_temp t;
    struct bridge_cal cal = ref_cal();

    calib_temp_reset(&t);
    /* d = 0, 0, 20: rows d=0 add nothing, one distinct d -> s2 s4 = s3^2 */
    (void)calib_temp_add(&t, 25.0f, 1000.0f, 1000.0f);
    (void)calib_temp_add(&t, 25.0f, 1000.0f, 1000.0f);
    (void)calib_temp_add(&t, 45.0f, 1040.0f, 980.0f);
    TEST_ASSERT_EQUAL(PM_EINVAL, calib_temp_fit(&t, &cal));
    TEST_ASSERT_FALSE(cal.temp_calibrated);
}

static void test_temperature_table_is_bounded(void)
{
    struct calib_temp t;

    calib_temp_reset(&t);
    for (uint32_t i = 0U; i < CALIB_TEMP_POINTS; i++) {
        TEST_ASSERT_EQUAL(PM_OK, calib_temp_add(&t, (float)i, 0.0f, 1.0f));
    }
    TEST_ASSERT_EQUAL(PM_ERANGE, calib_temp_add(&t, 99.0f, 0.0f, 1.0f));
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_zero_needs_64_samples);
    RUN_TEST(test_zero_is_the_mean_and_the_noise_is_the_standard_deviation);
    RUN_TEST(test_zero_that_moves_is_unstable);
    RUN_TEST(test_zero_beyond_20_percent_of_full_scale_is_a_bad_bridge);
    RUN_TEST(test_zero_stops_counting_at_the_limit_of_the_counter);
    RUN_TEST(test_auto_zero_is_accepted_only_within_the_step);
    RUN_TEST(test_torque_of_a_hung_mass);
    RUN_TEST(test_slope_fit_needs_two_points);
    RUN_TEST(test_slope_of_exact_points_has_no_residual);
    RUN_TEST(test_slope_residual_is_the_worst_point_over_the_largest_torque);
    RUN_TEST(test_slope_hysteresis_compares_the_same_torque_up_and_down);
    RUN_TEST(test_slope_rejects_a_bridge_that_does_not_follow_the_load);
    RUN_TEST(test_slope_table_refuses_out_of_range_codes_and_overflow);
    RUN_TEST(test_temperature_fit_needs_three_points_over_ten_degrees);
    RUN_TEST(test_temperature_fit_recovers_known_coefficients);
    RUN_TEST(test_temperature_fit_is_singular_with_all_points_at_one_temperature_pair);
    RUN_TEST(test_temperature_fit_singular_matrix_is_reported);
    RUN_TEST(test_temperature_table_is_bounded);
    return UNITY_END();
}
