/**
 * @file pm_cmd.h
 * @brief The text commands of the configuration service and of the serial
 *        port (docs/05, Serviço de configuração)
 *
 * One line, `$NAME,arg,...`, ended by CR, LF or both; the answer is
 * `$ACK[,payload]` or `$NAK,code,name`. The same lines come over the BLE
 * configuration characteristic and over the USB serial port, so the bike
 * computer and a terminal drive the meter the same way.
 */

#ifndef PM_CMD_H
#define PM_CMD_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "model/pm_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/** Longest line accepted, with its terminator */
#define PM_CMD_LINE_MAX     64U
#define PM_CMD_KEY_LEN      16U
#define PM_CMD_VALUE_LEN    32U

enum pm_cmd_id {
    PM_CMD_NONE = 0,
    PM_CMD_ZERO,            /**< $ZERO */
    PM_CMD_SLOPE_POINT,     /**< $SLOPE,m_g,L_mm[,DOWN] */
    PM_CMD_SLOPE_END,       /**< $SLOPE,END */
    PM_CMD_TEMP_BEGIN,      /**< $TEMP,BEGIN */
    PM_CMD_TEMP_POINT,      /**< $TEMP,POINT */
    PM_CMD_TEMP_END,        /**< $TEMP,END */
    PM_CMD_CFG_GET,         /**< $CFG,GET[,key] */
    PM_CMD_CFG_SET,         /**< $CFG,SET,key,value */
    PM_CMD_CFG_SAVE,        /**< $CFG,SAVE */
    PM_CMD_DFU,             /**< $DFU */
    PM_CMD_SLEEP,           /**< $SLEEP */
    PM_CMD_INFO,            /**< $INFO */
    PM_CMD_LOG,             /**< $LOG */
    PM_CMD_COUNT
};

struct pm_cmd {
    enum pm_cmd_id id;
    uint32_t mass_g;                /**< of $SLOPE */
    uint16_t length_mm;             /**< of $SLOPE */
    bool descending;                /**< of $SLOPE: the point is on the way down */
    char key[PM_CMD_KEY_LEN];       /**< of $CFG; empty for $CFG,GET without a key */
    char value[PM_CMD_VALUE_LEN];   /**< of $CFG,SET */
};

/** Assembles lines from a stream of bytes */
struct pm_line {
    char buf[PM_CMD_LINE_MAX];
    size_t n;
    bool overflow;
};

/**
 * @brief Parse one command line
 * @param line The text, with or without its CR or LF
 * @param len Its length
 * @return PM_OK; PM_EINVAL for anything that is not a command of docs/05
 */
pm_err_t pm_cmd_parse(const char *line, size_t len, struct pm_cmd *cmd);

/**
 * @brief Write "$ACK" or "$ACK,payload", with CR LF
 * @return Characters written, 0 when @p buf is too small
 */
size_t pm_cmd_ack(char *buf, size_t len, const char *payload);

/**
 * @brief Write "$NAK,code,name", with CR LF
 */
size_t pm_cmd_nak(char *buf, size_t len, pm_err_t err);

/** The short name of an error code ("EINVAL") */
const char *pm_err_name(pm_err_t err);

void pm_line_reset(struct pm_line *l);

/**
 * @brief Feed one byte
 * @return true when a whole line is in @p l->buf (terminated, without CR or LF);
 *         an overlong line is dropped up to its end and never returned
 */
bool pm_line_feed(struct pm_line *l, char c);

#ifdef __cplusplus
}
#endif

#endif /* PM_CMD_H */
