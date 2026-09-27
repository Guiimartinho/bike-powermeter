/**
 * @file pm_cmd.c
 * @brief The text commands of the configuration service (docs/05)
 */

#include <ctype.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "model/pm_cmd.h"

#define MAX_FIELDS      5U

static const char *const err_names[] = {
    "OK", "EINVAL", "ENOTREADY", "ERANGE", "EUNSTABLE", "EBRIDGE", "ESTATE",
};

const char *pm_err_name(pm_err_t err)
{
    size_t i = (size_t)err;

    return (i < (sizeof(err_names) / sizeof(err_names[0]))) ? err_names[i] : "E?";
}

/** Case-insensitive equality of a field with a keyword */
static bool field_is(const char *field, const char *word)
{
    size_t i = 0U;

    while ((field[i] != '\0') && (word[i] != '\0')) {
        if (toupper((unsigned char)field[i]) != (int)word[i]) {
            return false;
        }
        i++;
    }
    return (field[i] == '\0') && (word[i] == '\0');
}

static bool parse_ulong(const char *text, unsigned long max, unsigned long *out)
{
    char *end = NULL;

    if ((text[0] == '\0') || !isdigit((unsigned char)text[0])) {
        return false;
    }
    errno = 0;
    *out = strtoul(text, &end, 10);
    return (errno == 0) && (end != NULL) && (*end == '\0') && (*out <= max);
}

static bool copy_field(char *dst, size_t dst_len, const char *src)
{
    size_t n = strlen(src);

    if (n >= dst_len) {
        return false;
    }
    (void)memcpy(dst, src, n + 1U);
    return true;
}

static pm_err_t parse_slope(char fields[][PM_CMD_LINE_MAX], size_t nf, struct pm_cmd *cmd)
{
    unsigned long mass;
    unsigned long length;

    if ((nf == 2U) && field_is(fields[1], "END")) {
        cmd->id = PM_CMD_SLOPE_END;
        return PM_OK;
    }
    if ((nf != 3U) && (nf != 4U)) {
        return PM_EINVAL;
    }
    if (!parse_ulong(fields[1], 200000UL, &mass) || !parse_ulong(fields[2], 1000UL, &length)) {
        return PM_EINVAL;
    }
    if (nf == 4U) {
        if (!field_is(fields[3], "DOWN")) {
            return PM_EINVAL;
        }
        cmd->descending = true;
    }
    cmd->id = PM_CMD_SLOPE_POINT;
    cmd->mass_g = (uint32_t)mass;
    cmd->length_mm = (uint16_t)length;
    return PM_OK;
}

static pm_err_t parse_temp(char fields[][PM_CMD_LINE_MAX], size_t nf, struct pm_cmd *cmd)
{
    if (nf != 2U) {
        return PM_EINVAL;
    }
    if (field_is(fields[1], "BEGIN")) {
        cmd->id = PM_CMD_TEMP_BEGIN;
    } else if (field_is(fields[1], "POINT")) {
        cmd->id = PM_CMD_TEMP_POINT;
    } else if (field_is(fields[1], "END")) {
        cmd->id = PM_CMD_TEMP_END;
    } else {
        return PM_EINVAL;
    }
    return PM_OK;
}

static pm_err_t parse_cfg(char fields[][PM_CMD_LINE_MAX], size_t nf, struct pm_cmd *cmd)
{
    if (nf < 2U) {
        return PM_EINVAL;
    }
    if (field_is(fields[1], "GET")) {
        if (nf > 3U) {
            return PM_EINVAL;
        }
        if ((nf == 3U) && !copy_field(cmd->key, sizeof(cmd->key), fields[2])) {
            return PM_EINVAL;
        }
        cmd->id = PM_CMD_CFG_GET;
        return PM_OK;
    }
    if (field_is(fields[1], "SET")) {
        if ((nf != 4U) || (fields[2][0] == '\0')) {
            return PM_EINVAL;
        }
        if (!copy_field(cmd->key, sizeof(cmd->key), fields[2]) ||
            !copy_field(cmd->value, sizeof(cmd->value), fields[3])) {
            return PM_EINVAL;
        }
        cmd->id = PM_CMD_CFG_SET;
        return PM_OK;
    }
    if (field_is(fields[1], "SAVE") && (nf == 2U)) {
        cmd->id = PM_CMD_CFG_SAVE;
        return PM_OK;
    }
    return PM_EINVAL;
}

pm_err_t pm_cmd_parse(const char *line, size_t len, struct pm_cmd *cmd)
{
    char fields[MAX_FIELDS][PM_CMD_LINE_MAX];
    size_t nf = 0U;
    size_t at = 0U;
    static const struct {
        const char *name;
        enum pm_cmd_id id;
    } plain[] = {
        { "ZERO", PM_CMD_ZERO }, { "DFU", PM_CMD_DFU }, { "SLEEP", PM_CMD_SLEEP },
        { "SHIP", PM_CMD_SHIP }, { "INFO", PM_CMD_INFO }, { "LOG", PM_CMD_LOG },
    };

    (void)memset(cmd, 0, sizeof(*cmd));
    if ((line == NULL) || (len == 0U) || (len >= PM_CMD_LINE_MAX)) {
        return PM_EINVAL;
    }
    /* the terminator, if it came along */
    while ((len > 0U) && ((line[len - 1U] == '\r') || (line[len - 1U] == '\n'))) {
        len--;
    }
    if ((len < 2U) || (line[0] != '$')) {
        return PM_EINVAL;
    }

    /* split at the commas; an empty field is kept (it is an error later) */
    fields[0][0] = '\0';
    for (size_t i = 1U; i <= len; i++) {
        if ((i == len) || (line[i] == ',')) {
            fields[nf][at] = '\0';
            nf++;
            at = 0U;
            if (i < len) {
                if (nf >= MAX_FIELDS) {
                    return PM_EINVAL;
                }
                fields[nf][0] = '\0';
            }
        } else {
            fields[nf][at] = line[i];
            at++;
        }
    }

    for (size_t i = 0U; i < (sizeof(plain) / sizeof(plain[0])); i++) {
        if (field_is(fields[0], plain[i].name)) {
            if (nf != 1U) {
                return PM_EINVAL;
            }
            cmd->id = plain[i].id;
            return PM_OK;
        }
    }
    if (field_is(fields[0], "SLOPE")) {
        return parse_slope(fields, nf, cmd);
    }
    if (field_is(fields[0], "TEMP")) {
        return parse_temp(fields, nf, cmd);
    }
    if (field_is(fields[0], "CFG")) {
        return parse_cfg(fields, nf, cmd);
    }
    return PM_EINVAL;
}

size_t pm_cmd_ack(char *buf, size_t len, const char *payload)
{
    int n;

    if ((payload != NULL) && (payload[0] != '\0')) {
        n = snprintf(buf, len, "$ACK,%s\r\n", payload);
    } else {
        n = snprintf(buf, len, "$ACK\r\n");
    }
    if ((n < 0) || ((size_t)n >= len)) {
        if (len > 0U) {
            buf[0] = '\0';
        }
        return 0U;
    }
    return (size_t)n;
}

size_t pm_cmd_nak(char *buf, size_t len, pm_err_t err)
{
    int n = snprintf(buf, len, "$NAK,%d,%s\r\n", (int)err, pm_err_name(err));

    if ((n < 0) || ((size_t)n >= len)) {
        if (len > 0U) {
            buf[0] = '\0';
        }
        return 0U;
    }
    return (size_t)n;
}

void pm_line_reset(struct pm_line *l)
{
    l->n = 0U;
    l->overflow = false;
    l->buf[0] = '\0';
}

bool pm_line_feed(struct pm_line *l, char c)
{
    if ((c == '\r') || (c == '\n')) {
        bool ready = (l->n > 0U) && !l->overflow;

        l->buf[l->n] = '\0';
        l->n = 0U;
        l->overflow = false;
        return ready;
    }
    if (l->overflow) {
        return false;
    }
    if (l->n >= (PM_CMD_LINE_MAX - 1U)) {
        l->overflow = true;
        l->n = 0U;
        return false;
    }
    l->buf[l->n] = c;
    l->n++;
    return false;
}
