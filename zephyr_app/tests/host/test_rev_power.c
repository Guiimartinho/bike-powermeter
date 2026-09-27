/*
 * Tests of model/rev_power.c against docs/06 (Potência por volta):
 *   P = (1/T) sum tau_i dtheta_i, one side doubled, TE = (W+ + W-)/W+,
 *   PS = P_mean / P_peak, accumulators in 1/32 N·m, kJ and 1/1024 s.
 */

#include <math.h>

#include "model/rev_power.h"
#include "unity.h"

static struct rev_power rp;

void setUp(void)
{
    rev_power_init(&rp, NULL);
}

void tearDown(void)
{
}

/* A revolution of n samples with a constant torque, at omega rad/s */
/* Timestamps are integers on the board: the sum of the dt's is exact */
static uint32_t stamp(float t_s)
{
    return (uint32_t)lroundf(t_s * 1000.0f);
}

static void feed_constant(int32_t torque_mnm, float omega, uint32_t n)
{
    float dt_s = (PM_TWO_PI / omega) / (float)n;
    float dtheta = PM_TWO_PI / (float)n;

    for (uint32_t i = 0U; i < n; i++) {
        uint32_t dt_ms = stamp(dt_s * (float)(i + 1U)) - stamp(dt_s * (float)i);

        rev_power_feed(&rp, torque_mnm, dtheta, dt_ms, omega);
    }
}

/* A revolution with tau = peak * max(sin(theta), 0) plus a negative floor */
static void feed_sine(float peak_nm, float floor_nm, float omega, uint32_t n)
{
    float dt_s = (PM_TWO_PI / omega) / (float)n;
    float dtheta = PM_TWO_PI / (float)n;

    for (uint32_t i = 0U; i < n; i++) {
        float theta = dtheta * (float)i;
        float tau = floor_nm + (peak_nm * fmaxf(sinf(theta), 0.0f));
        uint32_t dt_ms = stamp(dt_s * (float)(i + 1U)) - stamp(dt_s * (float)i);

        rev_power_feed(&rp, (int32_t)lroundf(tau * 1000.0f), dtheta, dt_ms, omega);
    }
}

static void test_default_configuration(void)
{
    struct rev_power_cfg c = rev_power_cfg_default();

    TEST_ASSERT_TRUE(c.single_side);
    TEST_ASSERT_EQUAL_UINT8(50U, c.balance_pct);
    TEST_ASSERT_EQUAL_UINT32(3000U, c.zero_after_ms);
}

static void test_constant_torque_at_90_rpm_gives_tau_times_omega_doubled(void)
{
    struct rev_power_out out;
    float omega = 9.42478f;     /* 90 rpm */

    /* 21,2 N·m x 9,42 rad/s = 200 W on one side: 400 W reported */
    feed_constant(21200, omega, 87U);
    TEST_ASSERT_EQUAL(PM_OK, rev_power_close(&rp, 667U, &out));
    TEST_ASSERT_UINT16_WITHIN(3U, 400U, out.power_w);
    TEST_ASSERT_FLOAT_WITHIN(1.0f, 90.0f, out.cadence_rpm);
    TEST_ASSERT_EQUAL_UINT8(100U, out.te_pct);      /* no negative work */
    TEST_ASSERT_EQUAL_UINT8(100U, out.ps_pct);      /* flat torque: mean = peak */
    TEST_ASSERT_EQUAL_UINT8(50U, out.balance_pct);
    TEST_ASSERT_EQUAL_UINT16(1U, out.rev_count);
    TEST_ASSERT_EQUAL_UINT16(pm_ms_to_1024(667U), out.last_event_1024);
    /* mean torque 21,2 N·m -> 678,4 in 1/32 N·m */
    TEST_ASSERT_UINT16_WITHIN(2U, 678U, out.torque_acc_1_32);
}

static void test_two_sides_are_not_doubled(void)
{
    struct rev_power_cfg c = rev_power_cfg_default();
    struct rev_power_out out;

    c.single_side = false;
    rev_power_init(&rp, &c);
    feed_constant(21200, 9.42478f, 87U);
    TEST_ASSERT_EQUAL(PM_OK, rev_power_close(&rp, 667U, &out));
    TEST_ASSERT_UINT16_WITHIN(2U, 200U, out.power_w);
}

static void test_a_sine_stroke_has_the_expected_effectiveness_and_smoothness(void)
{
    struct rev_power_out out;
    float omega = 6.28318f;     /* 60 rpm, T = 1 s */

    /* peak 40 N·m on the down stroke, -5 N·m dragging on the up stroke */
    feed_sine(40.0f, -5.0f, omega, 100U);
    TEST_ASSERT_EQUAL(PM_OK, rev_power_close(&rp, 1000U, &out));

    /*
     * Work of the positive half: integral of (40 sin - 5) over 0..pi where
     * positive = 80 - 5 pi = 64,3 J; negative half: -5 pi = -15,7 J.
     * TE = (64,3 - 15,7) / 64,3 = 76 %. Power one side = 48,6 W, doubled 97 W.
     * Peak power = 35 N·m x 6,28 = 220 W; PS = 48,6 / 220 = 22 %.
     */
    TEST_ASSERT_UINT8_WITHIN(2U, 76U, out.te_pct);
    TEST_ASSERT_UINT8_WITHIN(2U, 22U, out.ps_pct);
    TEST_ASSERT_UINT16_WITHIN(3U, 97U, out.power_w);
}

static void test_negative_work_over_a_whole_revolution_reports_zero_power(void)
{
    struct rev_power_out out;

    feed_constant(-5000, 6.28318f, 50U);
    TEST_ASSERT_EQUAL(PM_OK, rev_power_close(&rp, 1000U, &out));
    TEST_ASSERT_EQUAL_UINT16(0U, out.power_w);
    TEST_ASSERT_EQUAL_UINT8(0U, out.te_pct);       /* no positive work */
    TEST_ASSERT_EQUAL_UINT8(0U, out.ps_pct);       /* no positive peak */
    TEST_ASSERT_EQUAL_UINT16(0U, out.torque_acc_1_32);  /* negative mean not accumulated */
}

static void test_more_negative_than_positive_work_gives_zero_effectiveness(void)
{
    struct rev_power_out out;

    /* +5 N·m over the first half turn (15,7 J), -20 N·m over the second (-62,8 J) */
    for (uint32_t i = 0U; i < 50U; i++) {
        rev_power_feed(&rp, 5000, PM_PI / 50.0f, 10U, 6.28318f);
    }
    for (uint32_t i = 0U; i < 50U; i++) {
        rev_power_feed(&rp, -20000, PM_PI / 50.0f, 10U, 6.28318f);
    }
    TEST_ASSERT_EQUAL(PM_OK, rev_power_close(&rp, 1000U, &out));
    TEST_ASSERT_EQUAL_UINT16(0U, out.power_w);
    TEST_ASSERT_EQUAL_UINT8(0U, out.te_pct);   /* (15,7 - 62,8) / 15,7 < 0 */
    TEST_ASSERT_EQUAL_UINT8(0U, out.ps_pct);   /* mean power < 0 against a positive peak */
}

static void test_too_few_samples_discard_the_revolution(void)
{
    struct rev_power_out out;

    feed_constant(20000, 6.28318f, 3U);
    TEST_ASSERT_EQUAL(PM_EINVAL, rev_power_close(&rp, 1000U, &out));
    TEST_ASSERT_EQUAL_UINT16(0U, rp.rev_count);
    TEST_ASSERT_EQUAL_UINT16(0U, rp.samples);
}

static void test_a_revolution_too_short_or_too_long_is_discarded(void)
{
    struct rev_power_out out;

    /* 10 samples of 5 ms: 50 ms, below 100 ms */
    for (uint32_t i = 0U; i < 10U; i++) {
        rev_power_feed(&rp, 20000, 0.628f, 5U, 100.0f);
    }
    TEST_ASSERT_EQUAL(PM_EINVAL, rev_power_close(&rp, 100U, &out));

    /* 10 samples of 700 ms: 7 s, above 6 s */
    for (uint32_t i = 0U; i < 10U; i++) {
        rev_power_feed(&rp, 20000, 0.628f, 700U, 0.9f);
    }
    TEST_ASSERT_EQUAL(PM_EINVAL, rev_power_close(&rp, 8000U, &out));
    TEST_ASSERT_EQUAL_UINT16(0U, rp.rev_count);
}

static void test_accumulators_carry_over_revolutions_and_wrap(void)
{
    struct rev_power_out out;
    float omega = 9.42478f;

    for (uint32_t i = 0U; i < 3U; i++) {
        feed_constant(21200, omega, 87U);
        TEST_ASSERT_EQUAL(PM_OK, rev_power_close(&rp, 667U * (i + 1U), &out));
    }
    TEST_ASSERT_EQUAL_UINT16(3U, out.rev_count);
    TEST_ASSERT_UINT16_WITHIN(4U, 2035U, out.torque_acc_1_32);   /* 3 x 678,4 */
    /* 400 W x 0,667 s x 3 = 800 J: still 0 kJ */
    TEST_ASSERT_EQUAL_UINT16(0U, out.energy_kj);

    /* force the wrap of the revolution counter and of the energy */
    rp.rev_count = 65535U;
    rp.energy_j = 65535.0f * 1000.0f + 900.0f;
    feed_constant(21200, omega, 87U);
    TEST_ASSERT_EQUAL(PM_OK, rev_power_close(&rp, 5000U, &out));
    TEST_ASSERT_EQUAL_UINT16(0U, out.rev_count);
    TEST_ASSERT_EQUAL_UINT16(0U, out.energy_kj);   /* 65535,9 + 0,27 kJ wraps to 0 */
}

static void test_power_saturates_at_the_uint16_of_the_characteristic(void)
{
    struct rev_power_out out;

    /* 5000 N·m at 9,42 rad/s doubled: far beyond 65535 W */
    feed_constant(5000000, 9.42478f, 87U);
    TEST_ASSERT_EQUAL(PM_OK, rev_power_close(&rp, 667U, &out));
    TEST_ASSERT_EQUAL_UINT16(65535U, out.power_w);
}

static void test_status_reports_the_last_revolution_then_zero_after_the_timeout(void)
{
    struct rev_power_out out;

    rev_power_status(&rp, 0U, &out);
    TEST_ASSERT_EQUAL_UINT16(0U, out.power_w);
    TEST_ASSERT_EQUAL_UINT8(50U, out.balance_pct);

    feed_constant(21200, 9.42478f, 87U);
    TEST_ASSERT_EQUAL(PM_OK, rev_power_close(&rp, 1000U, &out));
    rev_power_status(&rp, 2500U, &out);
    TEST_ASSERT_UINT16_WITHIN(3U, 400U, out.power_w);
    TEST_ASSERT_FLOAT_WITHIN(1.0f, 90.0f, out.cadence_rpm);

    rev_power_status(&rp, 4001U, &out);
    TEST_ASSERT_EQUAL_UINT16(0U, out.power_w);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, out.cadence_rpm);
    TEST_ASSERT_EQUAL_UINT8(0U, out.te_pct);
    TEST_ASSERT_EQUAL_UINT8(0U, out.ps_pct);
    /* the accumulators stay */
    TEST_ASSERT_EQUAL_UINT16(1U, out.rev_count);
    TEST_ASSERT_UINT16_WITHIN(2U, 678U, out.torque_acc_1_32);
}

static void test_sample_counter_does_not_overflow(void)
{
    rp.samples = UINT16_MAX;
    rev_power_feed(&rp, 1000, 0.01f, 10U, 1.0f);
    TEST_ASSERT_EQUAL_UINT16(UINT16_MAX, rp.samples);
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_default_configuration);
    RUN_TEST(test_constant_torque_at_90_rpm_gives_tau_times_omega_doubled);
    RUN_TEST(test_two_sides_are_not_doubled);
    RUN_TEST(test_a_sine_stroke_has_the_expected_effectiveness_and_smoothness);
    RUN_TEST(test_negative_work_over_a_whole_revolution_reports_zero_power);
    RUN_TEST(test_more_negative_than_positive_work_gives_zero_effectiveness);
    RUN_TEST(test_too_few_samples_discard_the_revolution);
    RUN_TEST(test_a_revolution_too_short_or_too_long_is_discarded);
    RUN_TEST(test_accumulators_carry_over_revolutions_and_wrap);
    RUN_TEST(test_power_saturates_at_the_uint16_of_the_characteristic);
    RUN_TEST(test_status_reports_the_last_revolution_then_zero_after_the_timeout);
    RUN_TEST(test_sample_counter_does_not_overflow);
    return UNITY_END();
}
