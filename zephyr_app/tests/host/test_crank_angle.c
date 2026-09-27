/*
 * Tests of model/crank_angle.c against docs/06 (Ângulo e cadência).
 *
 * The samples are synthesised from the same equations the module inverts:
 *   a_t = -sign g sin(theta) + alpha r,  a_r = g cos(theta) + omega^2 r,
 * so a constant cadence must come back as that cadence, with one
 * revolution event each time the arm passes the bottom.
 */

#include <math.h>

#include "model/crank_angle.h"
#include "unity.h"

#define DT_MS       10U     /* 100 Hz */
#define G           PM_GRAVITY

static struct crank_state st;

void setUp(void)
{
    crank_init(&st, NULL);
}

void tearDown(void)
{
}

/* Feed n samples of a constant angular velocity starting at theta0; returns revolutions */
static uint32_t run_constant(float omega, float theta0, uint32_t n, uint32_t *t_ms, float sign,
                             struct crank_out *last)
{
    uint32_t revs = 0U;
    float r = st.cfg.radius_m;

    for (uint32_t i = 0U; i < n; i++) {
        float theta = theta0 + (omega * (float)(*t_ms) / 1000.0f);
        float a_t = -sign * G * sinf(theta);
        float a_r = (G * cosf(theta)) + (omega * omega * r);

        crank_update(&st, a_t, a_r, 0.0f, *t_ms, last);
        if (last->revolution) {
            revs++;
        }
        *t_ms += DT_MS;
    }
    return revs;
}

/* ------------------------------------------------------------ defaults */

static void test_default_configuration_is_the_one_of_docs_06(void)
{
    struct crank_cfg c = crank_cfg_default();

    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.050f, c.radius_m);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 1.0f, c.tangential_sign);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 25.0f, c.omega_max);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.10f, c.still_g_tol);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.3f, c.still_omega);
    TEST_ASSERT_EQUAL_UINT32(2000U, c.still_ms);
}

static void test_init_with_a_configuration_keeps_it(void)
{
    struct crank_cfg c = crank_cfg_default();

    c.radius_m = 0.070f;
    crank_init(&st, &c);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.070f, st.cfg.radius_m);
    TEST_ASSERT_EQUAL_UINT32(0U, st.rev_count);
}

/* --------------------------------------------------------------- helpers */

static void test_wrap_2pi_brings_any_angle_into_the_turn(void)
{
    TEST_ASSERT_FLOAT_WITHIN(1e-5f, 0.0f, crank_wrap_2pi(0.0f));
    TEST_ASSERT_FLOAT_WITHIN(1e-5f, 1.0f, crank_wrap_2pi(1.0f + PM_TWO_PI));
    TEST_ASSERT_FLOAT_WITHIN(1e-5f, PM_TWO_PI - 1.0f, crank_wrap_2pi(-1.0f));
    TEST_ASSERT_FLOAT_WITHIN(1e-5f, 0.0f, crank_wrap_2pi(PM_TWO_PI));
}

static void test_cadence_is_absolute_rpm(void)
{
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 90.0f, crank_cadence_rpm(9.42478f));
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 90.0f, crank_cadence_rpm(-9.42478f));
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 0.0f, crank_cadence_rpm(0.0f));
}

/* ---------------------------------------------------------- first sample */

static void test_first_sample_gives_the_angle_and_nothing_else(void)
{
    struct crank_out out;

    /* arm horizontal, forward: theta = pi/2 -> a_t = -g, a_r = 0 */
    crank_update(&st, -G, 0.0f, 0.0f, 100U, &out);
    TEST_ASSERT_FALSE(out.valid);
    TEST_ASSERT_FALSE(out.revolution);
    TEST_ASSERT_FLOAT_WITHIN(1e-4f, PM_PI / 2.0f, out.angle_rad);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, out.omega_rad_s);
}

static void test_two_samples_on_the_same_tick_do_not_divide_by_zero(void)
{
    struct crank_out out;

    crank_update(&st, 0.0f, G, 0.0f, 100U, &out);
    crank_update(&st, -G, 0.0f, 0.0f, 100U, &out);
    TEST_ASSERT_FALSE(out.valid);
    TEST_ASSERT_FLOAT_WITHIN(1e-4f, PM_PI / 2.0f, out.angle_rad);
}

/* ------------------------------------------------------- constant cadence */

static void test_constant_90_rpm_is_recovered_within_two_percent(void)
{
    uint32_t t = 0U;
    struct crank_out out;
    float omega = 90.0f * PM_TWO_PI / 60.0f;

    (void)run_constant(omega, 0.0f, 200U, &t, 1.0f, &out);   /* 2 s */
    TEST_ASSERT_TRUE(out.valid);
    TEST_ASSERT_FLOAT_WITHIN(0.02f * omega, omega, out.omega_rad_s);
    TEST_ASSERT_FLOAT_WITHIN(2.0f, 90.0f, crank_cadence_rpm(out.omega_rad_s));
    TEST_ASSERT_FALSE(out.stationary);
}

static void test_ten_seconds_at_90_rpm_give_fifteen_revolutions(void)
{
    uint32_t t = 0U;
    struct crank_out out;
    float omega = 90.0f * PM_TWO_PI / 60.0f;
    uint32_t revs = run_constant(omega, 0.0f, 1000U, &t, 1.0f, &out);

    /* the arm starts up and passes the bottom 15 times in 10 s */
    TEST_ASSERT_EQUAL_UINT32(15U, revs);
    TEST_ASSERT_EQUAL_UINT32(15U, st.rev_count);
}

static void test_revolution_fires_when_the_arm_passes_the_bottom(void)
{
    uint32_t t = 0U;
    struct crank_out out;
    float omega = 60.0f * PM_TWO_PI / 60.0f;   /* 1 rev/s: bottom at 0,5 s */

    (void)run_constant(omega, 0.0f, 49U, &t, 1.0f, &out);    /* up to 0,48 s */
    TEST_ASSERT_EQUAL_UINT32(0U, st.rev_count);
    (void)run_constant(omega, 0.0f, 3U, &t, 1.0f, &out);     /* 0,49 to 0,51 s */
    TEST_ASSERT_EQUAL_UINT32(1U, st.rev_count);
}

static void test_the_centripetal_term_does_not_bias_the_angle_at_120_rpm(void)
{
    uint32_t t = 0U;
    struct crank_out out;
    float omega = 120.0f * PM_TWO_PI / 60.0f;     /* omega^2 r = 7,9 m/s^2 */

    (void)run_constant(omega, 0.3f, 300U, &t, 1.0f, &out);   /* 3 s */
    float theta_true = crank_wrap_2pi(0.3f + (omega * (float)(t - DT_MS) / 1000.0f));
    float err = fabsf(out.angle_rad - theta_true);

    if (err > PM_PI) {
        err = PM_TWO_PI - err;
    }
    TEST_ASSERT_FLOAT_WITHIN(0.1f, 0.0f, err);
    TEST_ASSERT_FLOAT_WITHIN(0.02f * omega, omega, out.omega_rad_s);
}

static void test_a_mirrored_tangential_axis_is_configured_not_guessed(void)
{
    struct crank_cfg c = crank_cfg_default();
    uint32_t t = 0U;
    struct crank_out out;
    float omega = 90.0f * PM_TWO_PI / 60.0f;

    c.tangential_sign = -1.0f;
    crank_init(&st, &c);
    (void)run_constant(omega, 0.0f, 200U, &t, -1.0f, &out);
    TEST_ASSERT_FLOAT_WITHIN(0.02f * omega, omega, out.omega_rad_s);
}

/* ------------------------------------------------------------ backpedal */

static void test_backpedalling_gives_negative_omega_and_no_revolution(void)
{
    uint32_t t = 0U;
    struct crank_out out;
    float omega = -60.0f * PM_TWO_PI / 60.0f;
    uint32_t revs = run_constant(omega, 0.0f, 300U, &t, 1.0f, &out);

    TEST_ASSERT_EQUAL_UINT32(0U, revs);
    TEST_ASSERT_TRUE(out.omega_rad_s < 0.0f);
    TEST_ASSERT_FLOAT_WITHIN(0.02f * 6.2832f, -6.2832f, out.omega_rad_s);
}

/* ------------------------------------------------------------------ rest */

static void test_rest_is_declared_after_two_seconds_still_and_not_before(void)
{
    struct crank_out out;
    uint32_t t = 0U;

    for (uint32_t i = 0U; i < 190U; i++) {   /* 1,9 s */
        crank_update(&st, 0.0f, G, 0.0f, t, &out);
        t += DT_MS;
    }
    TEST_ASSERT_FALSE(out.stationary);
    for (uint32_t i = 0U; i < 20U; i++) {    /* 2,1 s */
        crank_update(&st, 0.0f, G, 0.0f, t, &out);
        t += DT_MS;
    }
    TEST_ASSERT_TRUE(out.stationary);
}

static void test_a_shake_cancels_the_rest_candidate(void)
{
    struct crank_out out;
    uint32_t t = 0U;

    for (uint32_t i = 0U; i < 150U; i++) {
        crank_update(&st, 0.0f, G, 0.0f, t, &out);
        t += DT_MS;
    }
    /* |a| far from g: a bump */
    crank_update(&st, 0.0f, 2.0f * G, 0.0f, t, &out);
    t += DT_MS;
    TEST_ASSERT_FALSE(out.stationary);
    for (uint32_t i = 0U; i < 150U; i++) {
        crank_update(&st, 0.0f, G, 0.0f, t, &out);
        t += DT_MS;
    }
    /* only 1,5 s since the bump */
    TEST_ASSERT_FALSE(out.stationary);
}

static void test_pedalling_is_never_rest_even_with_the_magnitude_at_g(void)
{
    uint32_t t = 0U;
    struct crank_out out;
    float omega = 30.0f * PM_TWO_PI / 60.0f;

    /* 30 rpm with r = 0: |a| = g exactly, but omega = 3,1 rad/s */
    st.cfg.radius_m = 0.0f;
    (void)run_constant(omega, 0.0f, 400U, &t, 1.0f, &out);
    TEST_ASSERT_FALSE(out.stationary);
}

/* ---------------------------------------------------------------- spikes */

static void test_an_impossible_jump_is_discarded_and_the_angle_kept(void)
{
    uint32_t t = 0U;
    struct crank_out out;
    float omega = 60.0f * PM_TWO_PI / 60.0f;

    /* 1,5 s: crossings at 0,5 s (bottom) and 1,0 s (top) give omega */
    (void)run_constant(omega, 0.0f, 150U, &t, 1.0f, &out);
    float angle_before = out.angle_rad;
    uint32_t revs_before = st.rev_count;

    TEST_ASSERT_EQUAL_UINT32(1U, revs_before);
    TEST_ASSERT_FLOAT_WITHIN(0.02f * omega, omega, out.omega_rad_s);

    /* half a turn in 10 ms would be 314 rad/s */
    float theta = angle_before + PM_PI;

    crank_update(&st, -G * sinf(theta), G * cosf(theta), 0.0f, t, &out);
    TEST_ASSERT_FALSE(out.valid);
    TEST_ASSERT_FALSE(out.revolution);
    TEST_ASSERT_FLOAT_WITHIN(1e-5f, angle_before, out.angle_rad);
    TEST_ASSERT_EQUAL_UINT32(revs_before, st.rev_count);
    TEST_ASSERT_FLOAT_WITHIN(0.02f * omega, omega, out.omega_rad_s);

    /* the true signal resumes 20 ms after the last good sample: the bottom
     * at 1,5 s is still caught, interpolated between 1,49 and 1,51 s */
    t += DT_MS;
    (void)run_constant(omega, 0.0f, 1U, &t, 1.0f, &out);
    TEST_ASSERT_TRUE(out.valid);
    TEST_ASSERT_TRUE(out.revolution);
    TEST_ASSERT_EQUAL_UINT32(2U, st.rev_count);
    TEST_ASSERT_FLOAT_WITHIN(0.02f * omega, omega, out.omega_rad_s);
    TEST_ASSERT_FLOAT_WITHIN(0.02f, 2.0f * omega * 0.010f, out.dtheta_rad);
}

static void test_two_crossings_closer_than_the_fastest_crank_are_noise(void)
{
    uint32_t t = 0U;
    struct crank_out out;
    float omega = 60.0f * PM_TWO_PI / 60.0f;

    /* 1,52 s: the bottom at 1,5 s was just passed, omega is known */
    (void)run_constant(omega, 0.0f, 152U, &t, 1.0f, &out);
    TEST_ASSERT_EQUAL_UINT32(2U, st.rev_count);
    TEST_ASSERT_FLOAT_WITHIN(0.02f * omega, omega, out.omega_rad_s);

    /* a_t flips beyond the hysteresis both ways within 20 ms, near the
     * bottom (a_r = -g): a crossing 20 ms after the last one is impossible */
    crank_update(&st, 1.0f, -G, 0.0f, t, &out);
    t += DT_MS;
    crank_update(&st, -1.0f, -G, 0.0f, t, &out);
    TEST_ASSERT_TRUE(out.valid);
    TEST_ASSERT_FALSE(out.revolution);
    TEST_ASSERT_EQUAL_UINT32(2U, st.rev_count);
    TEST_ASSERT_FLOAT_WITHIN(0.02f * omega, omega, out.omega_rad_s);
}

static void test_no_crossing_for_two_seconds_means_the_crank_stopped(void)
{
    uint32_t t = 0U;
    struct crank_out out;
    float omega = 60.0f * PM_TWO_PI / 60.0f;

    (void)run_constant(omega, 0.0f, 152U, &t, 1.0f, &out);
    TEST_ASSERT_FLOAT_WITHIN(0.02f * omega, omega, out.omega_rad_s);

    /* the arm is held at 45 degrees: no crossing, |a| = g */
    for (uint32_t i = 0U; i < 190U; i++) {   /* to 3,41 s: 1,9 s after the bottom */
        crank_update(&st, -G * 0.70711f, G * 0.70711f, 0.0f, t, &out);
        t += DT_MS;
    }
    TEST_ASSERT_TRUE(out.omega_rad_s > 0.0f);
    for (uint32_t i = 0U; i < 20U; i++) {    /* to 3,61 s */
        crank_update(&st, -G * 0.70711f, G * 0.70711f, 0.0f, t, &out);
        t += DT_MS;
    }
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, out.omega_rad_s);
    TEST_ASSERT_FALSE(st.have_cross);
    TEST_ASSERT_FALSE(out.stationary);   /* only 0,1 s with omega 0 */

    /* pedalling resumes: the estimate starts afresh from two new crossings */
    (void)run_constant(omega, 0.0f, 130U, &t, 1.0f, &out);   /* 3,61 to 4,9 s */
    TEST_ASSERT_FLOAT_WITHIN(0.02f * omega, omega, out.omega_rad_s);
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_default_configuration_is_the_one_of_docs_06);
    RUN_TEST(test_init_with_a_configuration_keeps_it);
    RUN_TEST(test_wrap_2pi_brings_any_angle_into_the_turn);
    RUN_TEST(test_cadence_is_absolute_rpm);
    RUN_TEST(test_first_sample_gives_the_angle_and_nothing_else);
    RUN_TEST(test_two_samples_on_the_same_tick_do_not_divide_by_zero);
    RUN_TEST(test_constant_90_rpm_is_recovered_within_two_percent);
    RUN_TEST(test_ten_seconds_at_90_rpm_give_fifteen_revolutions);
    RUN_TEST(test_revolution_fires_when_the_arm_passes_the_bottom);
    RUN_TEST(test_the_centripetal_term_does_not_bias_the_angle_at_120_rpm);
    RUN_TEST(test_a_mirrored_tangential_axis_is_configured_not_guessed);
    RUN_TEST(test_backpedalling_gives_negative_omega_and_no_revolution);
    RUN_TEST(test_rest_is_declared_after_two_seconds_still_and_not_before);
    RUN_TEST(test_a_shake_cancels_the_rest_candidate);
    RUN_TEST(test_pedalling_is_never_rest_even_with_the_magnitude_at_g);
    RUN_TEST(test_an_impossible_jump_is_discarded_and_the_angle_kept);
    RUN_TEST(test_two_crossings_closer_than_the_fastest_crank_are_noise);
    RUN_TEST(test_no_crossing_for_two_seconds_means_the_crank_stopped);
    return UNITY_END();
}
