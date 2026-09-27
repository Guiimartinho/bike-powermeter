/**
 * @file pm_settings.c
 * @brief The configuration of the meter (docs/05)
 */

#include <ctype.h>
#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "model/pm_settings.h"
#include "model/pm_wire.h"

/** The ADS1220 data rates of the normal mode, SPS (datasheet SBAS501D, table 18) */
static const uint16_t rates_sps[] = { 20U, 45U, 90U, 175U, 330U, 600U, 1000U };

/** The text keys, in the order $CFG,GET prints them */
static const char *const keys[] = {
    "crank", "radius", "side", "sign", "zero", "slope", "t0", "k1", "k2", "k3", "tempcal",
    "rate", "autozero", "azstep", "ant", "caldate", "name",
};

void pm_settings_defaults(struct pm_settings *s)
{
    (void)memset(s, 0, sizeof(*s));
    s->crank_length_half_mm = 345U;     /* 172,5 mm */
    s->sensor_radius_mm = 50U;
    s->side = PM_SIDE_LEFT;
    s->tangential_sign = 1;
    s->cal.zero_code = 0;
    s->cal.slope_unm = 0.0f;
    s->cal.t0_c = 25.0f;
    s->sample_rate_sps = 175U;
    s->auto_zero = true;
    s->auto_zero_max_step = (int32_t)(PM_ADC_FULL_SCALE / 200L);   /* 0,5 % */
    (void)strncpy(s->name, "PM", sizeof(s->name) - 1U);
}

static bool rate_valid(uint16_t sps)
{
    for (size_t i = 0U; i < (sizeof(rates_sps) / sizeof(rates_sps[0])); i++) {
        if (rates_sps[i] == sps) {
            return true;
        }
    }
    return false;
}

static bool name_valid(const char *name)
{
    size_t n = 0U;

    while ((n < PM_SETTINGS_NAME_LEN) && (name[n] != '\0')) {
        if (!isprint((unsigned char)name[n]) || (name[n] == ',')) {
            return false;
        }
        n++;
    }
    return (n > 0U) && (n < PM_SETTINGS_NAME_LEN);
}

static bool date_valid(uint16_t y, uint8_t m, uint8_t d)
{
    if ((y == 0U) && (m == 0U) && (d == 0U)) {
        return true;
    }
    return (y >= 2020U) && (y <= 2100U) && (m >= 1U) && (m <= 12U) && (d >= 1U) && (d <= 31U);
}

pm_err_t pm_settings_validate(const struct pm_settings *s)
{
    if ((s->crank_length_half_mm < PM_CRANK_MIN_HALF_MM) ||
        (s->crank_length_half_mm > PM_CRANK_MAX_HALF_MM)) {
        return PM_EINVAL;
    }
    if ((s->sensor_radius_mm < PM_RADIUS_MIN_MM) || (s->sensor_radius_mm > PM_RADIUS_MAX_MM)) {
        return PM_EINVAL;
    }
    if ((s->side != PM_SIDE_LEFT) && (s->side != PM_SIDE_RIGHT)) {
        return PM_EINVAL;
    }
    if ((s->tangential_sign != 1) && (s->tangential_sign != -1)) {
        return PM_EINVAL;
    }
    /* the calibration may be absent (slope 0), never broken */
    if (!isfinite(s->cal.slope_unm) || (s->cal.slope_unm < 0.0f)) {
        return PM_EINVAL;
    }
    if ((s->cal.slope_unm > 0.0f) && !bridge_cal_valid(&s->cal)) {
        return PM_EINVAL;
    }
    if (!bridge_code_in_range(s->cal.zero_code)) {
        return PM_EINVAL;
    }
    if (!isfinite(s->cal.t0_c) || !isfinite(s->cal.k1) || !isfinite(s->cal.k2) ||
        !isfinite(s->cal.k3)) {
        return PM_EINVAL;
    }
    if (!rate_valid(s->sample_rate_sps)) {
        return PM_EINVAL;
    }
    if ((s->auto_zero_max_step < 0) || (s->auto_zero_max_step > PM_AUTO_ZERO_STEP_MAX)) {
        return PM_EINVAL;
    }
    if (!date_valid(s->cal_year, s->cal_month, s->cal_day)) {
        return PM_EINVAL;
    }
    if (!name_valid(s->name)) {
        return PM_EINVAL;
    }
    return PM_OK;
}

bool pm_settings_calibrated(const struct pm_settings *s)
{
    return bridge_cal_valid(&s->cal);
}

uint16_t pm_crc16(const uint8_t *data, size_t len)
{
    uint16_t crc = 0xFFFFU;

    for (size_t i = 0U; i < len; i++) {
        crc ^= (uint16_t)((uint16_t)data[i] << 8);
        for (uint8_t b = 0U; b < 8U; b++) {
            crc = ((crc & 0x8000U) != 0U) ? (uint16_t)((crc << 1) ^ 0x1021U)
                                           : (uint16_t)(crc << 1);
        }
    }
    return crc;
}

size_t pm_settings_serialize(const struct pm_settings *s, uint8_t *buf, size_t len)
{
    size_t at;

    if (len < PM_SETTINGS_WIRE_LEN) {
        return 0U;
    }
    at = pm_put_u16(buf, 0U, PM_SETTINGS_VERSION);
    at = pm_put_u16(buf, at, s->crank_length_half_mm);
    at = pm_put_u16(buf, at, s->sensor_radius_mm);
    at = pm_put_u8(buf, at, s->side);
    at = pm_put_u8(buf, at, (uint8_t)s->tangential_sign);
    at = pm_put_u32(buf, at, (uint32_t)s->cal.zero_code);
    at = pm_put_f32(buf, at, s->cal.slope_unm);
    at = pm_put_f32(buf, at, s->cal.t0_c);
    at = pm_put_f32(buf, at, s->cal.k1);
    at = pm_put_f32(buf, at, s->cal.k2);
    at = pm_put_f32(buf, at, s->cal.k3);
    at = pm_put_u8(buf, at, s->cal.temp_calibrated ? 1U : 0U);
    at = pm_put_u16(buf, at, s->sample_rate_sps);
    at = pm_put_u8(buf, at, s->auto_zero ? 1U : 0U);
    at = pm_put_u32(buf, at, (uint32_t)s->auto_zero_max_step);
    at = pm_put_u16(buf, at, s->ant_device_number);
    at = pm_put_u16(buf, at, s->cal_year);
    at = pm_put_u8(buf, at, s->cal_month);
    at = pm_put_u8(buf, at, s->cal_day);
    (void)memset(&buf[at], 0, PM_SETTINGS_NAME_LEN);
    (void)strncpy((char *)&buf[at], s->name, PM_SETTINGS_NAME_LEN - 1U);
    at += PM_SETTINGS_NAME_LEN;
    at = pm_put_u16(buf, at, pm_crc16(buf, at));
    return at;
}

pm_err_t pm_settings_deserialize(const uint8_t *buf, size_t len, struct pm_settings *s)
{
    size_t at = 0U;
    struct pm_settings t;

    if (len != PM_SETTINGS_WIRE_LEN) {
        return PM_EINVAL;
    }
    if (pm_get_u16(buf, PM_SETTINGS_WIRE_LEN - 2U) != pm_crc16(buf, PM_SETTINGS_WIRE_LEN - 2U)) {
        return PM_EINVAL;
    }
    if (pm_get_u16(buf, 0U) != PM_SETTINGS_VERSION) {
        return PM_EINVAL;
    }
    (void)memset(&t, 0, sizeof(t));
    at = 2U;
    t.crank_length_half_mm = pm_get_u16(buf, at);
    at += 2U;
    t.sensor_radius_mm = pm_get_u16(buf, at);
    at += 2U;
    t.side = buf[at];
    at += 1U;
    t.tangential_sign = (int8_t)buf[at];
    at += 1U;
    t.cal.zero_code = (int32_t)pm_get_u32(buf, at);
    at += 4U;
    t.cal.slope_unm = pm_get_f32(buf, at);
    at += 4U;
    t.cal.t0_c = pm_get_f32(buf, at);
    at += 4U;
    t.cal.k1 = pm_get_f32(buf, at);
    at += 4U;
    t.cal.k2 = pm_get_f32(buf, at);
    at += 4U;
    t.cal.k3 = pm_get_f32(buf, at);
    at += 4U;
    t.cal.temp_calibrated = (buf[at] != 0U);
    at += 1U;
    t.sample_rate_sps = pm_get_u16(buf, at);
    at += 2U;
    t.auto_zero = (buf[at] != 0U);
    at += 1U;
    t.auto_zero_max_step = (int32_t)pm_get_u32(buf, at);
    at += 4U;
    t.ant_device_number = pm_get_u16(buf, at);
    at += 2U;
    t.cal_year = pm_get_u16(buf, at);
    at += 2U;
    t.cal_month = buf[at];
    at += 1U;
    t.cal_day = buf[at];
    at += 1U;
    (void)memcpy(t.name, &buf[at], PM_SETTINGS_NAME_LEN);
    t.name[PM_SETTINGS_NAME_LEN - 1U] = '\0';
    if (pm_settings_validate(&t) != PM_OK) {
        return PM_EINVAL;
    }
    *s = t;
    return PM_OK;
}

const char *pm_settings_key(size_t i)
{
    return (i < (sizeof(keys) / sizeof(keys[0]))) ? keys[i] : NULL;
}

static bool key_is(const char *key, const char *name)
{
    return strcmp(key, name) == 0;
}

/** A whole decimal integer, nothing else in the string; 64 bits so the int32 limits are real tests */
static bool parse_long(const char *text, long long *out)
{
    char *end = NULL;

    errno = 0;
    if (*text == '\0') {
        return false;
    }
    *out = strtoll(text, &end, 10);
    return (errno == 0) && (end != NULL) && (*end == '\0');
}

static bool parse_float(const char *text, float *out)
{
    char *end = NULL;

    if ((text == NULL) || (*text == '\0')) {
        return false;
    }
    *out = strtof(text, &end);
    return (end != NULL) && (*end == '\0') && isfinite(*out);
}

/** "172.5" or "172" to half millimetres, exact only with .0 or .5 */
static bool parse_half_mm(const char *text, uint16_t *out)
{
    float mm;
    float half;

    if (!parse_float(text, &mm)) {
        return false;
    }
    half = mm * 2.0f;
    if ((half < 0.0f) || (half > 65535.0f) || (fabsf(half - roundf(half)) > 1e-3f)) {
        return false;
    }
    *out = (uint16_t)roundf(half);
    return true;
}

/** "YYYY-MM-DD", or "0" to clear */
static bool parse_date(const char *text, uint16_t *y, uint8_t *m, uint8_t *d)
{
    unsigned long part[3];
    size_t at = 0U;

    if (key_is(text, "0")) {
        *y = 0U;
        *m = 0U;
        *d = 0U;
        return true;
    }
    for (size_t i = 0U; i < 3U; i++) {
        char *end = NULL;

        if (!isdigit((unsigned char)text[at])) {
            return false;
        }
        part[i] = strtoul(&text[at], &end, 10);
        at = (size_t)(end - text);
        if (i < 2U) {
            if (text[at] != '-') {
                return false;
            }
            at++;
        }
    }
    if ((text[at] != '\0') || (part[0] > 65535UL) || (part[1] > 255UL) || (part[2] > 255UL)) {
        return false;
    }
    *y = (uint16_t)part[0];
    *m = (uint8_t)part[1];
    *d = (uint8_t)part[2];
    return true;
}

pm_err_t pm_settings_set_text(struct pm_settings *s, const char *key, const char *value)
{
    struct pm_settings t = *s;
    long long l = 0;
    float f = 0.0f;
    bool ok;

    if ((key == NULL) || (value == NULL)) {
        return PM_EINVAL;
    }
    if (key_is(key, "crank")) {
        ok = parse_half_mm(value, &t.crank_length_half_mm);
    } else if (key_is(key, "radius")) {
        ok = parse_long(value, &l) && (l >= 0) && (l <= 65535);
        t.sensor_radius_mm = (uint16_t)l;
    } else if (key_is(key, "side")) {
        ok = true;
        if (key_is(value, "L")) {
            t.side = PM_SIDE_LEFT;
        } else if (key_is(value, "R")) {
            t.side = PM_SIDE_RIGHT;
        } else {
            ok = false;
        }
    } else if (key_is(key, "sign")) {
        ok = parse_long(value, &l) && ((l == 1) || (l == -1));
        t.tangential_sign = (int8_t)l;
    } else if (key_is(key, "zero")) {
        ok = parse_long(value, &l) && (l >= INT32_MIN) && (l <= INT32_MAX);
        t.cal.zero_code = (int32_t)l;
    } else if (key_is(key, "slope")) {
        ok = parse_float(value, &f);
        t.cal.slope_unm = f;
    } else if (key_is(key, "t0")) {
        ok = parse_float(value, &f);
        t.cal.t0_c = f;
    } else if (key_is(key, "k1")) {
        ok = parse_float(value, &f);
        t.cal.k1 = f;
    } else if (key_is(key, "k2")) {
        ok = parse_float(value, &f);
        t.cal.k2 = f;
    } else if (key_is(key, "k3")) {
        ok = parse_float(value, &f);
        t.cal.k3 = f;
    } else if (key_is(key, "tempcal")) {
        ok = parse_long(value, &l) && ((l == 0) || (l == 1));
        t.cal.temp_calibrated = (l == 1);
    } else if (key_is(key, "rate")) {
        ok = parse_long(value, &l) && (l >= 0) && (l <= 65535);
        t.sample_rate_sps = (uint16_t)l;
    } else if (key_is(key, "autozero")) {
        ok = parse_long(value, &l) && ((l == 0) || (l == 1));
        t.auto_zero = (l == 1);
    } else if (key_is(key, "azstep")) {
        ok = parse_long(value, &l) && (l >= 0) && (l <= INT32_MAX);
        t.auto_zero_max_step = (int32_t)l;
    } else if (key_is(key, "ant")) {
        ok = parse_long(value, &l) && (l >= 0) && (l <= 65535);
        t.ant_device_number = (uint16_t)l;
    } else if (key_is(key, "caldate")) {
        ok = parse_date(value, &t.cal_year, &t.cal_month, &t.cal_day);
    } else if (key_is(key, "name")) {
        ok = strlen(value) < PM_SETTINGS_NAME_LEN;
        if (ok) {
            (void)memset(t.name, 0, sizeof(t.name));
            (void)strncpy(t.name, value, sizeof(t.name) - 1U);
        }
    } else {
        return PM_EINVAL;
    }
    if (!ok || (pm_settings_validate(&t) != PM_OK)) {
        return PM_EINVAL;
    }
    *s = t;
    return PM_OK;
}

size_t pm_settings_get_text(const struct pm_settings *s, const char *key, char *buf, size_t len)
{
    int n;

    if ((key == NULL) || (buf == NULL) || (len == 0U)) {
        return 0U;
    }
    if (key_is(key, "crank")) {
        n = snprintf(buf, len, "%u.%u", (unsigned int)(s->crank_length_half_mm / 2U),
                     (unsigned int)((s->crank_length_half_mm % 2U) * 5U));
    } else if (key_is(key, "radius")) {
        n = snprintf(buf, len, "%u", (unsigned int)s->sensor_radius_mm);
    } else if (key_is(key, "side")) {
        n = snprintf(buf, len, "%s", (s->side == PM_SIDE_LEFT) ? "L" : "R");
    } else if (key_is(key, "sign")) {
        n = snprintf(buf, len, "%d", (int)s->tangential_sign);
    } else if (key_is(key, "zero")) {
        n = snprintf(buf, len, "%ld", (long)s->cal.zero_code);
    } else if (key_is(key, "slope")) {
        n = snprintf(buf, len, "%.6g", (double)s->cal.slope_unm);
    } else if (key_is(key, "t0")) {
        n = snprintf(buf, len, "%.6g", (double)s->cal.t0_c);
    } else if (key_is(key, "k1")) {
        n = snprintf(buf, len, "%.6g", (double)s->cal.k1);
    } else if (key_is(key, "k2")) {
        n = snprintf(buf, len, "%.6g", (double)s->cal.k2);
    } else if (key_is(key, "k3")) {
        n = snprintf(buf, len, "%.6g", (double)s->cal.k3);
    } else if (key_is(key, "tempcal")) {
        n = snprintf(buf, len, "%d", s->cal.temp_calibrated ? 1 : 0);
    } else if (key_is(key, "rate")) {
        n = snprintf(buf, len, "%u", (unsigned int)s->sample_rate_sps);
    } else if (key_is(key, "autozero")) {
        n = snprintf(buf, len, "%d", s->auto_zero ? 1 : 0);
    } else if (key_is(key, "azstep")) {
        n = snprintf(buf, len, "%ld", (long)s->auto_zero_max_step);
    } else if (key_is(key, "ant")) {
        n = snprintf(buf, len, "%u", (unsigned int)s->ant_device_number);
    } else if (key_is(key, "caldate")) {
        if (s->cal_year == 0U) {
            n = snprintf(buf, len, "0");
        } else {
            n = snprintf(buf, len, "%04u-%02u-%02u", (unsigned int)s->cal_year,
                         (unsigned int)s->cal_month, (unsigned int)s->cal_day);
        }
    } else if (key_is(key, "name")) {
        n = snprintf(buf, len, "%s", s->name);
    } else {
        return 0U;
    }
    if ((n < 0) || ((size_t)n >= len)) {
        buf[0] = '\0';
        return 0U;
    }
    return (size_t)n;
}
