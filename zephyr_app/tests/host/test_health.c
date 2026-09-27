/*
 * Tests of model/health.c against docs/06 (Saúde do sensor): every rule,
 * its threshold, its timing, and which flags stop the measurement.
 */

#include "model/health.h"
#include "unity.h"

static struct health h;

void setUp(void)
{
    health_init(&h, NULL);
}

void tearDown(void)
{
}

static void test_init_flags_only_the_missing_calibration(void)
{
    TEST_ASSERT_EQUAL_HEX16(HEALTH_NOT_CALIBRATED, health_flags(&h));
    TEST_ASSERT_FALSE(health_can_measure(&h));
    health_calibrated(&h, true);
    TEST_ASSERT_EQUAL_HEX16(0U, health_flags(&h));
    TEST_ASSERT_TRUE(health_can_measure(&h));
    health_calibrated(&h, false);
    TEST_ASSERT_FALSE(health_can_measure(&h));
}

static void test_default_configuration_is_the_one_of_docs_06(void)
{
    struct health_cfg c = health_cfg_default();

    TEST_ASSERT_EQUAL_UINT16(3000U, c.excitation_nominal_mv);
    TEST_ASSERT_EQUAL_UINT8(10U, c.excitation_tol_pct);
    TEST_ASSERT_EQUAL_UINT32(2000U, c.stuck_ms);
    TEST_ASSERT_EQUAL_UINT32(500U, c.imu_stale_ms);
    TEST_ASSERT_EQUAL_UINT32(1000U, c.imu_range_ms);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.5f, c.imu_min_g);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 6.0f, c.imu_max_g);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, -20.0f, c.temp_min_c);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 70.0f, c.temp_max_c);
}

static void test_init_with_a_configuration_keeps_it(void)
{
    struct health_cfg c = health_cfg_default();

    c.stuck_ms = 100U;
    health_init(&h, &c);
    TEST_ASSERT_EQUAL_UINT32(100U, h.cfg.stuck_ms);
}

/* ---------------------------------------------------------------- bridge */

static void test_a_code_at_80_percent_of_full_scale_is_an_open_bridge(void)
{
    health_calibrated(&h, true);
    health_bridge(&h, 6710885, true, 0U);
    TEST_ASSERT_EQUAL_HEX16(0U, health_flags(&h));
    health_bridge(&h, 6710886, true, 10U);
    TEST_ASSERT_EQUAL_HEX16(HEALTH_BRIDGE_OPEN, health_flags(&h));
    TEST_ASSERT_FALSE(health_can_measure(&h));
    health_bridge(&h, -6710886, true, 20U);
    TEST_ASSERT_EQUAL_HEX16(HEALTH_BRIDGE_OPEN, health_flags(&h));
    health_bridge(&h, -6710885, true, 30U);
    TEST_ASSERT_EQUAL_HEX16(0U, health_flags(&h));
}

static void test_the_same_code_for_two_seconds_is_a_stuck_bridge(void)
{
    health_calibrated(&h, true);
    for (uint32_t t = 0U; t < 2000U; t += 100U) {
        health_bridge(&h, 1000, true, t);
        TEST_ASSERT_EQUAL_HEX16(0U, health_flags(&h));
    }
    health_bridge(&h, 1000, true, 2000U);
    TEST_ASSERT_EQUAL_HEX16(HEALTH_BRIDGE_STUCK, health_flags(&h));
    TEST_ASSERT_FALSE(health_can_measure(&h));
    /* one different code clears it and restarts the clock */
    health_bridge(&h, 1001, true, 2100U);
    TEST_ASSERT_EQUAL_HEX16(0U, health_flags(&h));
    health_bridge(&h, 1001, true, 4000U);
    TEST_ASSERT_EQUAL_HEX16(0U, health_flags(&h));
    health_bridge(&h, 1001, true, 4100U);
    TEST_ASSERT_EQUAL_HEX16(HEALTH_BRIDGE_STUCK, health_flags(&h));
}

static void test_without_excitation_the_bridge_is_not_judged(void)
{
    health_calibrated(&h, true);
    health_bridge(&h, 1000, true, 0U);
    health_bridge(&h, 8000000, false, 100U);    /* off: nothing */
    TEST_ASSERT_EQUAL_HEX16(0U, health_flags(&h));
    /* the stuck clock restarted with the excitation */
    health_bridge(&h, 1000, true, 1900U);
    health_bridge(&h, 1000, true, 3800U);
    TEST_ASSERT_EQUAL_HEX16(0U, health_flags(&h));
    health_bridge(&h, 1000, true, 3900U);
    TEST_ASSERT_EQUAL_HEX16(HEALTH_BRIDGE_STUCK, health_flags(&h));
}

static void test_excitation_outside_ten_percent_of_nominal(void)
{
    health_calibrated(&h, true);
    health_excitation(&h, 2700U);
    TEST_ASSERT_EQUAL_HEX16(0U, health_flags(&h));
    health_excitation(&h, 2699U);
    TEST_ASSERT_EQUAL_HEX16(HEALTH_EXCITATION, health_flags(&h));
    TEST_ASSERT_FALSE(health_can_measure(&h));
    health_excitation(&h, 3300U);
    TEST_ASSERT_EQUAL_HEX16(0U, health_flags(&h));
    health_excitation(&h, 3301U);
    TEST_ASSERT_EQUAL_HEX16(HEALTH_EXCITATION, health_flags(&h));
    health_excitation(&h, 0U);
    TEST_ASSERT_EQUAL_HEX16(HEALTH_EXCITATION, health_flags(&h));
}

/* ----------------------------------------------------------------- imu */

static void test_accelerometer_silence_of_500_ms_is_stale(void)
{
    health_calibrated(&h, true);
    health_tick(&h, 10000U);        /* never seen: not judged */
    TEST_ASSERT_EQUAL_HEX16(0U, health_flags(&h));
    health_imu(&h, 1.0f, 10000U);
    health_tick(&h, 10499U);
    TEST_ASSERT_EQUAL_HEX16(0U, health_flags(&h));
    health_tick(&h, 10500U);
    TEST_ASSERT_EQUAL_HEX16(HEALTH_IMU_STALE, health_flags(&h));
    TEST_ASSERT_FALSE(health_can_measure(&h));
    health_imu(&h, 1.0f, 10600U);
    TEST_ASSERT_EQUAL_HEX16(0U, health_flags(&h));
    TEST_ASSERT_TRUE(health_can_measure(&h));
}

static void test_accelerometer_out_of_range_for_a_second_is_a_warning(void)
{
    health_calibrated(&h, true);
    health_imu(&h, 0.4f, 0U);
    health_imu(&h, 0.4f, 999U);
    TEST_ASSERT_EQUAL_HEX16(0U, health_flags(&h));
    health_imu(&h, 0.4f, 1000U);
    TEST_ASSERT_EQUAL_HEX16(HEALTH_IMU_RANGE, health_flags(&h));
    TEST_ASSERT_TRUE(health_can_measure(&h));    /* a warning, not a stop */
    health_imu(&h, 1.0f, 1100U);
    TEST_ASSERT_EQUAL_HEX16(0U, health_flags(&h));
    /* above 6 g, and the clock restarts at the first bad sample */
    health_imu(&h, 6.1f, 2000U);
    health_imu(&h, 6.1f, 2999U);
    TEST_ASSERT_EQUAL_HEX16(0U, health_flags(&h));
    health_imu(&h, 6.1f, 3000U);
    TEST_ASSERT_EQUAL_HEX16(HEALTH_IMU_RANGE, health_flags(&h));
    /* a good sample in between restarts the count */
    health_imu(&h, 1.0f, 3100U);
    health_imu(&h, 0.1f, 3200U);
    health_imu(&h, 0.1f, 4100U);
    TEST_ASSERT_EQUAL_HEX16(0U, health_flags(&h));
    health_imu(&h, 0.1f, 4200U);
    TEST_ASSERT_EQUAL_HEX16(HEALTH_IMU_RANGE, health_flags(&h));
}

/* ------------------------------------------------------- temperature, zero */

static void test_temperature_outside_minus_20_to_70(void)
{
    health_calibrated(&h, true);
    health_temperature(&h, -20.0f);
    TEST_ASSERT_EQUAL_HEX16(0U, health_flags(&h));
    health_temperature(&h, -20.1f);
    TEST_ASSERT_EQUAL_HEX16(HEALTH_TEMP_RANGE, health_flags(&h));
    TEST_ASSERT_TRUE(health_can_measure(&h));
    health_temperature(&h, 70.0f);
    TEST_ASSERT_EQUAL_HEX16(0U, health_flags(&h));
    health_temperature(&h, 70.1f);
    TEST_ASSERT_EQUAL_HEX16(HEALTH_TEMP_RANGE, health_flags(&h));
}

static void test_zero_drift_beyond_the_step_asks_for_a_recalibration(void)
{
    health_calibrated(&h, true);
    health_zero(&h, 1000, 1000, 100);
    TEST_ASSERT_EQUAL_HEX16(0U, health_flags(&h));
    health_zero(&h, 1100, 1000, 100);
    TEST_ASSERT_EQUAL_HEX16(0U, health_flags(&h));
    health_zero(&h, 1101, 1000, 100);
    TEST_ASSERT_EQUAL_HEX16(HEALTH_ZERO_DRIFT, health_flags(&h));
    health_zero(&h, 899, 1000, 100);
    TEST_ASSERT_EQUAL_HEX16(HEALTH_ZERO_DRIFT, health_flags(&h));
    TEST_ASSERT_TRUE(health_can_measure(&h));
    /* a step of 0 disables the rule; extreme values do not overflow */
    health_zero(&h, 2000000000, -2000000000, 0);
    TEST_ASSERT_EQUAL_HEX16(0U, health_flags(&h));
    health_zero(&h, 2000000000, -2000000000, INT32_MAX);
    TEST_ASSERT_EQUAL_HEX16(HEALTH_ZERO_DRIFT, health_flags(&h));
}

static void test_flags_accumulate_independently(void)
{
    health_bridge(&h, 7000000, true, 0U);
    health_excitation(&h, 100U);
    health_temperature(&h, 80.0f);
    TEST_ASSERT_EQUAL_HEX16(HEALTH_NOT_CALIBRATED | HEALTH_BRIDGE_OPEN | HEALTH_EXCITATION |
                            HEALTH_TEMP_RANGE, health_flags(&h));
    health_temperature(&h, 20.0f);
    TEST_ASSERT_EQUAL_HEX16(HEALTH_NOT_CALIBRATED | HEALTH_BRIDGE_OPEN | HEALTH_EXCITATION,
                            health_flags(&h));
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_init_flags_only_the_missing_calibration);
    RUN_TEST(test_default_configuration_is_the_one_of_docs_06);
    RUN_TEST(test_init_with_a_configuration_keeps_it);
    RUN_TEST(test_a_code_at_80_percent_of_full_scale_is_an_open_bridge);
    RUN_TEST(test_the_same_code_for_two_seconds_is_a_stuck_bridge);
    RUN_TEST(test_without_excitation_the_bridge_is_not_judged);
    RUN_TEST(test_excitation_outside_ten_percent_of_nominal);
    RUN_TEST(test_accelerometer_silence_of_500_ms_is_stale);
    RUN_TEST(test_accelerometer_out_of_range_for_a_second_is_a_warning);
    RUN_TEST(test_temperature_outside_minus_20_to_70);
    RUN_TEST(test_zero_drift_beyond_the_step_asks_for_a_recalibration);
    RUN_TEST(test_flags_accumulate_independently);
    return UNITY_END();
}
