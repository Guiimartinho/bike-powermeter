/*
 * Tests of model/pm_fsm.c against the state diagram of docs/04: every
 * transition, every refusal, and the three timers.
 */

#include "model/pm_fsm.h"
#include "unity.h"

static struct pm_fsm f;

void setUp(void)
{
    pm_fsm_init(&f, NULL, 0U);
}

void tearDown(void)
{
}

static void ready(void)
{
    TEST_ASSERT_EQUAL(PM_OK, pm_fsm_event(&f, PM_EV_READY, 100U));
}

static void pedal(uint32_t now)
{
    TEST_ASSERT_EQUAL(PM_OK, pm_fsm_event(&f, PM_EV_MOTION, now));
    TEST_ASSERT_EQUAL(PM_ST_ACTIVE, pm_fsm_state(&f));
}

/* ------------------------------------------------------------- boot, idle */

static void test_boot_waits_for_ready_and_refuses_the_rest(void)
{
    struct pm_fsm_cfg c = pm_fsm_cfg_default();

    TEST_ASSERT_EQUAL_UINT32(30000U, c.idle_after_ms);
    TEST_ASSERT_EQUAL_UINT32(600000U, c.sleep_after_ms);
    TEST_ASSERT_EQUAL_UINT32(60000U, c.cal_timeout_ms);
    TEST_ASSERT_EQUAL_UINT8(30U, c.dfu_min_soc_pct);

    TEST_ASSERT_EQUAL(PM_ST_BOOT, pm_fsm_state(&f));
    TEST_ASSERT_EQUAL(PM_ESTATE, pm_fsm_event(&f, PM_EV_MOTION, 10U));
    TEST_ASSERT_EQUAL(PM_ESTATE, pm_fsm_event(&f, PM_EV_STILL, 10U));
    TEST_ASSERT_EQUAL(PM_ESTATE, pm_fsm_event(&f, PM_EV_WAKE, 10U));
    TEST_ASSERT_EQUAL(PM_ESTATE, pm_fsm_event(&f, PM_EV_CAL_REQUEST, 10U));
    TEST_ASSERT_EQUAL(PM_ESTATE, pm_fsm_event(&f, PM_EV_CAL_DONE, 10U));
    TEST_ASSERT_EQUAL(PM_ESTATE, pm_fsm_event(&f, PM_EV_DFU_REQUEST, 10U));
    TEST_ASSERT_EQUAL(PM_ESTATE, pm_fsm_event(&f, PM_EV_BATTERY_CRITICAL, 10U));
    TEST_ASSERT_EQUAL(PM_OK, pm_fsm_event(&f, PM_EV_CHARGING, 10U));   /* harmless anywhere */
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_fsm_event(&f, PM_EV_COUNT, 10U));
    TEST_ASSERT_EQUAL(PM_ST_BOOT, pm_fsm_state(&f));
    pm_fsm_tick(&f, 1000000U);      /* no timer runs in boot */
    TEST_ASSERT_EQUAL(PM_ST_BOOT, pm_fsm_state(&f));

    ready();
    TEST_ASSERT_EQUAL(PM_ST_IDLE, pm_fsm_state(&f));
    TEST_ASSERT_EQUAL(PM_ESTATE, pm_fsm_event(&f, PM_EV_READY, 200U));
}

static void test_init_with_a_configuration_keeps_it(void)
{
    struct pm_fsm_cfg c = pm_fsm_cfg_default();

    c.idle_after_ms = 5U;
    pm_fsm_init(&f, &c, 7U);
    TEST_ASSERT_EQUAL_UINT32(5U, f.cfg.idle_after_ms);
    TEST_ASSERT_EQUAL_UINT32(7U, f.still_since_ms);
    TEST_ASSERT_EQUAL_UINT8(100U, f.soc_pct);
}

static void test_state_names(void)
{
    TEST_ASSERT_EQUAL_STRING("boot", pm_fsm_state_name(PM_ST_BOOT));
    TEST_ASSERT_EQUAL_STRING("low-battery", pm_fsm_state_name(PM_ST_LOW_BATTERY));
    TEST_ASSERT_EQUAL_STRING("?", pm_fsm_state_name(PM_ST_COUNT));
}

/* --------------------------------------------------------- active, timers */

static void test_motion_makes_active_and_thirty_seconds_still_make_idle(void)
{
    ready();
    pedal(1000U);
    TEST_ASSERT_TRUE(pm_fsm_measuring(pm_fsm_state(&f)));
    pedal(2000U);                   /* more motion: nothing changes */
    TEST_ASSERT_EQUAL(PM_OK, pm_fsm_event(&f, PM_EV_STILL, 5000U));
    TEST_ASSERT_EQUAL(PM_ST_ACTIVE, pm_fsm_state(&f));
    TEST_ASSERT_EQUAL(PM_OK, pm_fsm_event(&f, PM_EV_STILL, 6000U));  /* still again: clock kept */
    pm_fsm_tick(&f, 34999U);
    TEST_ASSERT_EQUAL(PM_ST_ACTIVE, pm_fsm_state(&f));
    pm_fsm_tick(&f, 35000U);
    TEST_ASSERT_EQUAL(PM_ST_IDLE, pm_fsm_state(&f));
    TEST_ASSERT_FALSE(pm_fsm_measuring(pm_fsm_state(&f)));
    /* motion in between resets the clock */
    pedal(40000U);
    TEST_ASSERT_EQUAL(PM_OK, pm_fsm_event(&f, PM_EV_STILL, 50000U));
    pm_fsm_tick(&f, 79999U);
    TEST_ASSERT_EQUAL(PM_ST_ACTIVE, pm_fsm_state(&f));
    pm_fsm_tick(&f, 80000U);
    TEST_ASSERT_EQUAL(PM_ST_IDLE, pm_fsm_state(&f));
    /* a tick while moving never leaves active */
    pedal(90000U);
    pm_fsm_tick(&f, 900000U);
    TEST_ASSERT_EQUAL(PM_ST_ACTIVE, pm_fsm_state(&f));
}

static void test_ten_minutes_still_make_sleep_and_wake_or_motion_leave_it(void)
{
    ready();                        /* idle since 100 ms */
    pm_fsm_tick(&f, 600099U);
    TEST_ASSERT_EQUAL(PM_ST_IDLE, pm_fsm_state(&f));
    pm_fsm_tick(&f, 600100U);
    TEST_ASSERT_EQUAL(PM_ST_SLEEP, pm_fsm_state(&f));
    TEST_ASSERT_EQUAL(PM_ESTATE, pm_fsm_event(&f, PM_EV_STILL, 600200U));
    TEST_ASSERT_EQUAL(PM_ESTATE, pm_fsm_event(&f, PM_EV_CAL_REQUEST, 600200U));
    TEST_ASSERT_EQUAL(PM_ESTATE, pm_fsm_event(&f, PM_EV_CAL_DONE, 600200U));
    pm_fsm_tick(&f, 9000000U);
    TEST_ASSERT_EQUAL(PM_ST_SLEEP, pm_fsm_state(&f));

    TEST_ASSERT_EQUAL(PM_OK, pm_fsm_event(&f, PM_EV_WAKE, 700000U));
    TEST_ASSERT_EQUAL(PM_ST_IDLE, pm_fsm_state(&f));
    TEST_ASSERT_EQUAL(PM_ESTATE, pm_fsm_event(&f, PM_EV_WAKE, 700001U));
    /* the sleep clock restarted at the wake */
    pm_fsm_tick(&f, 1299999U);
    TEST_ASSERT_EQUAL(PM_ST_IDLE, pm_fsm_state(&f));
    pm_fsm_tick(&f, 1300000U);
    TEST_ASSERT_EQUAL(PM_ST_SLEEP, pm_fsm_state(&f));

    pedal(1300500U);                /* pedalling straight out of sleep */
}

static void test_the_pedalling_clock_carries_from_active_to_idle_to_sleep(void)
{
    ready();
    pedal(1000U);
    TEST_ASSERT_EQUAL(PM_OK, pm_fsm_event(&f, PM_EV_STILL, 2000U));
    pm_fsm_tick(&f, 32000U);
    TEST_ASSERT_EQUAL(PM_ST_IDLE, pm_fsm_state(&f));
    /* 10 min after the crank stopped, not after idle began */
    pm_fsm_tick(&f, 601999U);
    TEST_ASSERT_EQUAL(PM_ST_IDLE, pm_fsm_state(&f));
    pm_fsm_tick(&f, 602000U);
    TEST_ASSERT_EQUAL(PM_ST_SLEEP, pm_fsm_state(&f));
}

/* ----------------------------------------------------------- calibrating */

static void test_calibration_needs_a_still_crank_and_ends_or_times_out(void)
{
    ready();
    pedal(1000U);
    TEST_ASSERT_EQUAL(PM_ESTATE, pm_fsm_event(&f, PM_EV_CAL_REQUEST, 2000U));   /* moving */
    TEST_ASSERT_EQUAL(PM_OK, pm_fsm_event(&f, PM_EV_STILL, 3000U));
    TEST_ASSERT_EQUAL(PM_OK, pm_fsm_event(&f, PM_EV_CAL_REQUEST, 4000U));
    TEST_ASSERT_EQUAL(PM_ST_CALIBRATING, pm_fsm_state(&f));
    TEST_ASSERT_TRUE(pm_fsm_measuring(PM_ST_CALIBRATING));
    TEST_ASSERT_EQUAL(PM_ESTATE, pm_fsm_event(&f, PM_EV_CAL_REQUEST, 4100U));  /* twice */
    TEST_ASSERT_EQUAL(PM_ESTATE, pm_fsm_event(&f, PM_EV_DFU_REQUEST, 4100U));
    TEST_ASSERT_EQUAL(PM_OK, pm_fsm_event(&f, PM_EV_STILL, 4200U));            /* stays */
    TEST_ASSERT_EQUAL(PM_ST_CALIBRATING, pm_fsm_state(&f));
    TEST_ASSERT_EQUAL(PM_OK, pm_fsm_event(&f, PM_EV_CAL_DONE, 10000U));
    TEST_ASSERT_EQUAL(PM_ST_IDLE, pm_fsm_state(&f));
    TEST_ASSERT_EQUAL(PM_ESTATE, pm_fsm_event(&f, PM_EV_CAL_DONE, 10001U));

    /* from idle, and the timeout brings it back to idle with a fresh clock */
    TEST_ASSERT_EQUAL(PM_OK, pm_fsm_event(&f, PM_EV_CAL_REQUEST, 20000U));
    pm_fsm_tick(&f, 79999U);
    TEST_ASSERT_EQUAL(PM_ST_CALIBRATING, pm_fsm_state(&f));
    pm_fsm_tick(&f, 80000U);
    TEST_ASSERT_EQUAL(PM_ST_IDLE, pm_fsm_state(&f));
    pm_fsm_tick(&f, 679999U);
    TEST_ASSERT_EQUAL(PM_ST_IDLE, pm_fsm_state(&f));
    pm_fsm_tick(&f, 680000U);
    TEST_ASSERT_EQUAL(PM_ST_SLEEP, pm_fsm_state(&f));
}

static void test_motion_voids_a_calibration(void)
{
    ready();
    TEST_ASSERT_EQUAL(PM_OK, pm_fsm_event(&f, PM_EV_CAL_REQUEST, 1000U));
    pedal(2000U);
    TEST_ASSERT_EQUAL(PM_ST_ACTIVE, pm_fsm_state(&f));
}

/* ------------------------------------------------------------------- dfu */

static void test_dfu_needs_a_still_crank_and_thirty_percent_of_battery(void)
{
    ready();
    pm_fsm_set_soc(&f, 29U);
    TEST_ASSERT_EQUAL(PM_ESTATE, pm_fsm_event(&f, PM_EV_DFU_REQUEST, 1000U));
    pm_fsm_set_soc(&f, 30U);
    pedal(2000U);
    TEST_ASSERT_EQUAL(PM_ESTATE, pm_fsm_event(&f, PM_EV_DFU_REQUEST, 3000U));    /* moving */
    TEST_ASSERT_EQUAL(PM_OK, pm_fsm_event(&f, PM_EV_STILL, 4000U));
    TEST_ASSERT_EQUAL(PM_OK, pm_fsm_event(&f, PM_EV_DFU_REQUEST, 5000U));        /* active, still */
    TEST_ASSERT_EQUAL(PM_ST_DFU, pm_fsm_state(&f));
    /* terminal: nothing moves it, no timer either */
    TEST_ASSERT_EQUAL(PM_ESTATE, pm_fsm_event(&f, PM_EV_MOTION, 6000U));
    TEST_ASSERT_EQUAL(PM_ESTATE, pm_fsm_event(&f, PM_EV_STILL, 6000U));
    TEST_ASSERT_EQUAL(PM_ESTATE, pm_fsm_event(&f, PM_EV_BATTERY_CRITICAL, 6000U));
    TEST_ASSERT_EQUAL(PM_ESTATE, pm_fsm_event(&f, PM_EV_DFU_REQUEST, 6000U));
    pm_fsm_tick(&f, 9000000U);
    TEST_ASSERT_EQUAL(PM_ST_DFU, pm_fsm_state(&f));
}

static void test_dfu_from_sleep_and_the_soc_is_capped(void)
{
    ready();
    pm_fsm_set_soc(&f, 250U);
    TEST_ASSERT_EQUAL_UINT8(100U, f.soc_pct);
    pm_fsm_tick(&f, 700000U);
    TEST_ASSERT_EQUAL(PM_ST_SLEEP, pm_fsm_state(&f));
    TEST_ASSERT_EQUAL(PM_OK, pm_fsm_event(&f, PM_EV_DFU_REQUEST, 700001U));
    TEST_ASSERT_EQUAL(PM_ST_DFU, pm_fsm_state(&f));
}

/* ----------------------------------------------------------- low battery */

static void test_battery_critical_stops_everything_until_it_charges(void)
{
    ready();
    pedal(1000U);
    TEST_ASSERT_EQUAL(PM_OK, pm_fsm_event(&f, PM_EV_BATTERY_CRITICAL, 2000U));
    TEST_ASSERT_EQUAL(PM_ST_LOW_BATTERY, pm_fsm_state(&f));
    TEST_ASSERT_FALSE(f.moving);
    TEST_ASSERT_EQUAL(PM_OK, pm_fsm_event(&f, PM_EV_BATTERY_CRITICAL, 2100U));   /* again: fine */
    TEST_ASSERT_EQUAL(PM_ESTATE, pm_fsm_event(&f, PM_EV_MOTION, 3000U));
    TEST_ASSERT_EQUAL(PM_OK, pm_fsm_event(&f, PM_EV_STILL, 3000U));
    TEST_ASSERT_EQUAL(PM_ESTATE, pm_fsm_event(&f, PM_EV_CAL_REQUEST, 3000U));
    TEST_ASSERT_EQUAL(PM_ESTATE, pm_fsm_event(&f, PM_EV_DFU_REQUEST, 3000U));
    TEST_ASSERT_EQUAL(PM_ESTATE, pm_fsm_event(&f, PM_EV_WAKE, 3000U));
    pm_fsm_tick(&f, 9000000U);
    TEST_ASSERT_EQUAL(PM_ST_LOW_BATTERY, pm_fsm_state(&f));
    TEST_ASSERT_EQUAL(PM_OK, pm_fsm_event(&f, PM_EV_CHARGING, 9000100U));
    TEST_ASSERT_EQUAL(PM_ST_IDLE, pm_fsm_state(&f));
    /* the sleep clock starts at the charge, not at the old stop */
    pm_fsm_tick(&f, 9600099U);
    TEST_ASSERT_EQUAL(PM_ST_IDLE, pm_fsm_state(&f));
    pm_fsm_tick(&f, 9600100U);
    TEST_ASSERT_EQUAL(PM_ST_SLEEP, pm_fsm_state(&f));
}

static void test_battery_critical_from_idle_sleep_and_calibrating(void)
{
    ready();
    TEST_ASSERT_EQUAL(PM_OK, pm_fsm_event(&f, PM_EV_BATTERY_CRITICAL, 1000U));
    TEST_ASSERT_EQUAL(PM_ST_LOW_BATTERY, pm_fsm_state(&f));

    pm_fsm_init(&f, NULL, 0U);
    ready();
    pm_fsm_tick(&f, 700000U);
    TEST_ASSERT_EQUAL(PM_ST_SLEEP, pm_fsm_state(&f));
    TEST_ASSERT_EQUAL(PM_OK, pm_fsm_event(&f, PM_EV_BATTERY_CRITICAL, 700001U));
    TEST_ASSERT_EQUAL(PM_ST_LOW_BATTERY, pm_fsm_state(&f));

    pm_fsm_init(&f, NULL, 0U);
    ready();
    TEST_ASSERT_EQUAL(PM_OK, pm_fsm_event(&f, PM_EV_CAL_REQUEST, 1000U));
    TEST_ASSERT_EQUAL(PM_OK, pm_fsm_event(&f, PM_EV_BATTERY_CRITICAL, 2000U));
    TEST_ASSERT_EQUAL(PM_ST_LOW_BATTERY, pm_fsm_state(&f));
    /* charging elsewhere changes nothing */
    TEST_ASSERT_EQUAL(PM_OK, pm_fsm_event(&f, PM_EV_CHARGING, 3000U));
    TEST_ASSERT_EQUAL(PM_ST_IDLE, pm_fsm_state(&f));
    TEST_ASSERT_EQUAL(PM_OK, pm_fsm_event(&f, PM_EV_CHARGING, 4000U));
    TEST_ASSERT_EQUAL(PM_ST_IDLE, pm_fsm_state(&f));
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_boot_waits_for_ready_and_refuses_the_rest);
    RUN_TEST(test_init_with_a_configuration_keeps_it);
    RUN_TEST(test_state_names);
    RUN_TEST(test_motion_makes_active_and_thirty_seconds_still_make_idle);
    RUN_TEST(test_ten_minutes_still_make_sleep_and_wake_or_motion_leave_it);
    RUN_TEST(test_the_pedalling_clock_carries_from_active_to_idle_to_sleep);
    RUN_TEST(test_calibration_needs_a_still_crank_and_ends_or_times_out);
    RUN_TEST(test_motion_voids_a_calibration);
    RUN_TEST(test_dfu_needs_a_still_crank_and_thirty_percent_of_battery);
    RUN_TEST(test_dfu_from_sleep_and_the_soc_is_capped);
    RUN_TEST(test_battery_critical_stops_everything_until_it_charges);
    RUN_TEST(test_battery_critical_from_idle_sleep_and_calibrating);
    return UNITY_END();
}
