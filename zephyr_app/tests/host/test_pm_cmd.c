/*
 * Tests of model/pm_cmd.c against the command list of docs/05: every
 * command with its arguments, the refusals, the answers, and the line
 * assembler.
 */

#include <string.h>

#include "model/pm_cmd.h"
#include "unity.h"

static struct pm_cmd c;

void setUp(void)
{
    (void)memset(&c, 0xAA, sizeof(c));
}

void tearDown(void)
{
}

static pm_err_t parse(const char *line)
{
    return pm_cmd_parse(line, strlen(line), &c);
}

/* -------------------------------------------------------------- commands */

static void test_plain_commands_with_and_without_terminators(void)
{
    TEST_ASSERT_EQUAL(PM_OK, parse("$ZERO"));
    TEST_ASSERT_EQUAL(PM_CMD_ZERO, c.id);
    TEST_ASSERT_EQUAL(PM_OK, parse("$ZERO\r\n"));
    TEST_ASSERT_EQUAL(PM_CMD_ZERO, c.id);
    TEST_ASSERT_EQUAL(PM_OK, parse("$zero\n"));
    TEST_ASSERT_EQUAL(PM_CMD_ZERO, c.id);
    TEST_ASSERT_EQUAL(PM_OK, parse("$DFU"));
    TEST_ASSERT_EQUAL(PM_CMD_DFU, c.id);
    TEST_ASSERT_EQUAL(PM_OK, parse("$SLEEP"));
    TEST_ASSERT_EQUAL(PM_CMD_SLEEP, c.id);
    TEST_ASSERT_EQUAL(PM_OK, parse("$INFO"));
    TEST_ASSERT_EQUAL(PM_CMD_INFO, c.id);
    TEST_ASSERT_EQUAL(PM_OK, parse("$LOG"));
    TEST_ASSERT_EQUAL(PM_CMD_LOG, c.id);
    /* a plain command takes no argument */
    TEST_ASSERT_EQUAL(PM_EINVAL, parse("$ZERO,1"));
    TEST_ASSERT_EQUAL(PM_CMD_NONE, c.id);
}

static void test_slope_point_takes_mass_length_and_an_optional_down(void)
{
    TEST_ASSERT_EQUAL(PM_OK, parse("$SLOPE,10000,172"));
    TEST_ASSERT_EQUAL(PM_CMD_SLOPE_POINT, c.id);
    TEST_ASSERT_EQUAL_UINT32(10000U, c.mass_g);
    TEST_ASSERT_EQUAL_UINT16(172U, c.length_mm);
    TEST_ASSERT_FALSE(c.descending);

    TEST_ASSERT_EQUAL(PM_OK, parse("$SLOPE,5000,170,DOWN"));
    TEST_ASSERT_TRUE(c.descending);
    TEST_ASSERT_EQUAL(PM_OK, parse("$slope,5000,170,down"));
    TEST_ASSERT_TRUE(c.descending);

    TEST_ASSERT_EQUAL(PM_OK, parse("$SLOPE,END"));
    TEST_ASSERT_EQUAL(PM_CMD_SLOPE_END, c.id);

    TEST_ASSERT_EQUAL(PM_EINVAL, parse("$SLOPE"));
    TEST_ASSERT_EQUAL(PM_EINVAL, parse("$SLOPE,10000"));
    TEST_ASSERT_EQUAL(PM_EINVAL, parse("$SLOPE,10000,172,UP"));
    TEST_ASSERT_EQUAL(PM_EINVAL, parse("$SLOPE,10000,172,DOWN,1"));
    TEST_ASSERT_EQUAL(PM_EINVAL, parse("$SLOPE,-1,172"));
    TEST_ASSERT_EQUAL(PM_EINVAL, parse("$SLOPE,10kg,172"));
    TEST_ASSERT_EQUAL(PM_EINVAL, parse("$SLOPE,200001,172"));    /* 200 kg */
    TEST_ASSERT_EQUAL(PM_EINVAL, parse("$SLOPE,10000,1001"));
    TEST_ASSERT_EQUAL(PM_EINVAL, parse("$SLOPE,,172"));
}

static void test_temperature_curve_commands(void)
{
    TEST_ASSERT_EQUAL(PM_OK, parse("$TEMP,BEGIN"));
    TEST_ASSERT_EQUAL(PM_CMD_TEMP_BEGIN, c.id);
    TEST_ASSERT_EQUAL(PM_OK, parse("$TEMP,POINT"));
    TEST_ASSERT_EQUAL(PM_CMD_TEMP_POINT, c.id);
    TEST_ASSERT_EQUAL(PM_OK, parse("$TEMP,END"));
    TEST_ASSERT_EQUAL(PM_CMD_TEMP_END, c.id);
    TEST_ASSERT_EQUAL(PM_EINVAL, parse("$TEMP"));
    TEST_ASSERT_EQUAL(PM_EINVAL, parse("$TEMP,NOW"));
    TEST_ASSERT_EQUAL(PM_EINVAL, parse("$TEMP,POINT,1"));
}

static void test_configuration_commands(void)
{
    TEST_ASSERT_EQUAL(PM_OK, parse("$CFG,GET"));
    TEST_ASSERT_EQUAL(PM_CMD_CFG_GET, c.id);
    TEST_ASSERT_EQUAL_STRING("", c.key);

    TEST_ASSERT_EQUAL(PM_OK, parse("$CFG,GET,crank"));
    TEST_ASSERT_EQUAL(PM_CMD_CFG_GET, c.id);
    TEST_ASSERT_EQUAL_STRING("crank", c.key);

    TEST_ASSERT_EQUAL(PM_OK, parse("$CFG,SET,crank,172.5"));
    TEST_ASSERT_EQUAL(PM_CMD_CFG_SET, c.id);
    TEST_ASSERT_EQUAL_STRING("crank", c.key);
    TEST_ASSERT_EQUAL_STRING("172.5", c.value);

    TEST_ASSERT_EQUAL(PM_OK, parse("$CFG,SET,name,"));       /* an empty value is for the settings to judge */
    TEST_ASSERT_EQUAL_STRING("", c.value);

    TEST_ASSERT_EQUAL(PM_OK, parse("$CFG,SAVE"));
    TEST_ASSERT_EQUAL(PM_CMD_CFG_SAVE, c.id);

    TEST_ASSERT_EQUAL(PM_EINVAL, parse("$CFG"));
    TEST_ASSERT_EQUAL(PM_EINVAL, parse("$CFG,GET,crank,1"));
    TEST_ASSERT_EQUAL(PM_EINVAL, parse("$CFG,SET"));
    TEST_ASSERT_EQUAL(PM_EINVAL, parse("$CFG,SET,crank"));
    TEST_ASSERT_EQUAL(PM_EINVAL, parse("$CFG,SET,,1"));
    TEST_ASSERT_EQUAL(PM_EINVAL, parse("$CFG,SAVE,1"));
    TEST_ASSERT_EQUAL(PM_EINVAL, parse("$CFG,DROP"));
    TEST_ASSERT_EQUAL(PM_EINVAL, parse("$CFG,GET,a-key-that-is-too-long"));
    TEST_ASSERT_EQUAL(PM_EINVAL, parse("$CFG,SET,a-key-that-is-too-long,1"));
    TEST_ASSERT_EQUAL(PM_EINVAL, parse("$CFG,SET,name,a-value-that-is-far-too-long-for-it"));
}

static void test_lines_that_are_not_commands(void)
{
    TEST_ASSERT_EQUAL(PM_EINVAL, parse(""));
    TEST_ASSERT_EQUAL(PM_EINVAL, parse("$"));
    TEST_ASSERT_EQUAL(PM_EINVAL, parse("\r\n"));
    TEST_ASSERT_EQUAL(PM_EINVAL, parse("ZERO"));
    TEST_ASSERT_EQUAL(PM_EINVAL, parse("$FLY"));
    TEST_ASSERT_EQUAL(PM_EINVAL, parse("$ZER"));
    TEST_ASSERT_EQUAL(PM_EINVAL, parse("$ZEROS"));
    TEST_ASSERT_EQUAL(PM_EINVAL, parse("$CFG,SET,a,b,c,d"));      /* six fields */
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_cmd_parse(NULL, 5U, &c));
    TEST_ASSERT_EQUAL(PM_EINVAL, pm_cmd_parse("$ZERO", PM_CMD_LINE_MAX, &c));
    TEST_ASSERT_EQUAL(PM_CMD_NONE, c.id);
}

/* --------------------------------------------------------------- answers */

static void test_ack_and_nak_lines(void)
{
    char buf[32];

    TEST_ASSERT_EQUAL_size_t(6U, pm_cmd_ack(buf, sizeof(buf), NULL));
    TEST_ASSERT_EQUAL_STRING("$ACK\r\n", buf);
    TEST_ASSERT_EQUAL_size_t(6U, pm_cmd_ack(buf, sizeof(buf), ""));
    TEST_ASSERT_EQUAL_STRING("$ACK\r\n", buf);
    TEST_ASSERT_EQUAL_size_t(18U, pm_cmd_ack(buf, sizeof(buf), "crank=172.5"));
    TEST_ASSERT_EQUAL_STRING("$ACK,crank=172.5\r\n", buf);
    TEST_ASSERT_EQUAL_size_t(0U, pm_cmd_ack(buf, 6U, NULL));
    TEST_ASSERT_EQUAL_STRING("", buf);
    TEST_ASSERT_EQUAL_size_t(0U, pm_cmd_ack(buf, 0U, NULL));

    TEST_ASSERT_EQUAL_size_t(15U, pm_cmd_nak(buf, sizeof(buf), PM_EINVAL));
    TEST_ASSERT_EQUAL_STRING("$NAK,1,EINVAL\r\n", buf);
    TEST_ASSERT_EQUAL_size_t(15U, pm_cmd_nak(buf, sizeof(buf), PM_ESTATE));
    TEST_ASSERT_EQUAL_STRING("$NAK,6,ESTATE\r\n", buf);
    TEST_ASSERT_EQUAL_size_t(0U, pm_cmd_nak(buf, 10U, PM_EINVAL));
    TEST_ASSERT_EQUAL_STRING("", buf);
    TEST_ASSERT_EQUAL_size_t(0U, pm_cmd_nak(buf, 0U, PM_EINVAL));
}

static void test_error_names(void)
{
    TEST_ASSERT_EQUAL_STRING("OK", pm_err_name(PM_OK));
    TEST_ASSERT_EQUAL_STRING("ENOTREADY", pm_err_name(PM_ENOTREADY));
    TEST_ASSERT_EQUAL_STRING("ERANGE", pm_err_name(PM_ERANGE));
    TEST_ASSERT_EQUAL_STRING("EUNSTABLE", pm_err_name(PM_EUNSTABLE));
    TEST_ASSERT_EQUAL_STRING("EBRIDGE", pm_err_name(PM_EBRIDGE));
    TEST_ASSERT_EQUAL_STRING("E?", pm_err_name((pm_err_t)99));
}

/* ------------------------------------------------------------------ lines */

static void feed(struct pm_line *l, const char *text, size_t *ready)
{
    for (size_t i = 0U; text[i] != '\0'; i++) {
        if (pm_line_feed(l, text[i])) {
            (*ready)++;
        }
    }
}

static void test_line_assembler_returns_each_terminated_line_once(void)
{
    struct pm_line l;
    size_t ready = 0U;

    pm_line_reset(&l);
    feed(&l, "$ZER", &ready);
    TEST_ASSERT_EQUAL_size_t(0U, ready);
    TEST_ASSERT_FALSE(pm_line_feed(&l, 'O'));
    TEST_ASSERT_TRUE(pm_line_feed(&l, '\n'));
    TEST_ASSERT_EQUAL_STRING("$ZERO", l.buf);
    /* the terminator does not return the same line twice */
    TEST_ASSERT_FALSE(pm_line_feed(&l, '\n'));
}

static void test_line_assembler_handles_crlf_empty_lines_and_overflow(void)
{
    struct pm_line l;
    size_t ready = 0U;

    pm_line_reset(&l);
    feed(&l, "$ZERO\r", &ready);
    TEST_ASSERT_EQUAL_size_t(1U, ready);
    TEST_ASSERT_EQUAL_STRING("$ZERO", l.buf);
    feed(&l, "\n", &ready);             /* the LF of the CR LF: no empty line */
    TEST_ASSERT_EQUAL_size_t(1U, ready);
    feed(&l, "\r\n\r\n", &ready);
    TEST_ASSERT_EQUAL_size_t(1U, ready);
    feed(&l, "$INFO\n", &ready);
    TEST_ASSERT_EQUAL_size_t(2U, ready);
    TEST_ASSERT_EQUAL_STRING("$INFO", l.buf);

    /* 63 characters fit, the 64th overflows and the line is dropped whole */
    for (size_t i = 0U; i < (PM_CMD_LINE_MAX - 1U); i++) {
        TEST_ASSERT_FALSE(pm_line_feed(&l, 'x'));
    }
    TEST_ASSERT_FALSE(l.overflow);
    TEST_ASSERT_FALSE(pm_line_feed(&l, 'x'));
    TEST_ASSERT_TRUE(l.overflow);
    TEST_ASSERT_FALSE(pm_line_feed(&l, 'y'));       /* swallowed */
    TEST_ASSERT_FALSE(pm_line_feed(&l, '\n'));      /* the end of the bad line */
    TEST_ASSERT_FALSE(l.overflow);
    feed(&l, "$LOG\n", &ready);                     /* the next one is fine */
    TEST_ASSERT_EQUAL_size_t(3U, ready);
    TEST_ASSERT_EQUAL_STRING("$LOG", l.buf);
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_plain_commands_with_and_without_terminators);
    RUN_TEST(test_slope_point_takes_mass_length_and_an_optional_down);
    RUN_TEST(test_temperature_curve_commands);
    RUN_TEST(test_configuration_commands);
    RUN_TEST(test_lines_that_are_not_commands);
    RUN_TEST(test_ack_and_nak_lines);
    RUN_TEST(test_error_names);
    RUN_TEST(test_line_assembler_returns_each_terminated_line_once);
    RUN_TEST(test_line_assembler_handles_crlf_empty_lines_and_overflow);
    return UNITY_END();
}
