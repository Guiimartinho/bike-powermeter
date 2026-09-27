/**
 * @file app_events.h
 * @brief Messages of the zbus channels (docs/04, Eventos)
 *
 * Plain C types, without Zephyr driver types, so the model and its host
 * tests can use them. Each service publishes on its channels and never
 * calls another service: the only calls go down to Zephyr and to the model.
 */

#ifndef APP_EVENTS_H
#define APP_EVENTS_H

#include <stdbool.h>
#include <stdint.h>

#include "model/pm_cmd.h"
#include "model/pm_settings.h"

#ifdef __cplusplus
extern "C" {
#endif

/** Services with a thread and a watchdog channel */
enum app_svc_id {
    APP_SVC_SAMPLE = 0,
    APP_SVC_MOTION,
    APP_SVC_COMPUTE,
    APP_SVC_RADIO,
    APP_SVC_POWER,
    APP_SVC_USB,
    APP_SVC_COUNT
};

/** Channel torque: one bridge sample, 175 Hz while active (sample -> compute) */
struct app_torque {
    uint32_t uptime_ms;
    int32_t code;               /**< converter code after the median of three */
    int32_t torque_mnm;         /**< with the calibration in force; 0 when not calibrated */
    bool excitation_on;
    bool calibrated;
};

/** Channel temp: the bridge temperature, 1 Hz (sample -> compute) */
struct app_temp {
    uint32_t uptime_ms;
    float temp_c;
    bool valid;
};

/** Channel excitation: the reference monitor of the converter, mV (sample -> compute) */
struct app_excitation {
    uint32_t uptime_ms;
    uint16_t ref_mv;
    bool valid;
};

/** Channel crank: one accelerometer sample through the estimator (motion -> compute) */
struct app_crank {
    uint32_t uptime_ms;
    float angle_rad;
    float omega_rad_s;
    float dtheta_rad;
    float mag_g;                /**< |a| in g, for the health rule */
    bool revolution;
    bool stationary;
    bool valid;
};

/** Channel motion_state: whether the crank turns (motion -> power, radio) */
struct app_motion_state {
    uint32_t uptime_ms;
    bool moving;
};

/** Channel power: the result of a revolution, or the 1 Hz status (compute -> radio, usb) */
struct app_power {
    uint32_t uptime_ms;
    uint16_t power_w;
    uint8_t cadence_rpm;        /**< 0 to 254; the ANT+ page uses 255 for invalid */
    uint8_t te_pct;
    uint8_t ps_pct;
    uint8_t balance_pct;
    uint16_t torque_acc_1_32;
    uint16_t rev_count;
    uint16_t last_event_1024;
    uint16_t energy_kj;
    uint16_t health_flags;
    bool revolution;            /**< this message closes a revolution */
    bool measuring;             /**< no fatal health flag */
};

/** Points of the torque profile of a revolution sent in the CPS vector */
#define APP_VECTOR_POINTS       16U

/** Channel vector: the torque profile of the last revolution (compute -> radio) */
struct app_vector {
    uint16_t rev_count;
    uint16_t last_event_1024;
    uint16_t first_angle_deg;
    int16_t torque_1_32[APP_VECTOR_POINTS];
};

/** Where a command came from, so the answer goes back the same way */
enum app_cmd_source {
    APP_SRC_BLE_CFG = 0,        /**< the configuration service */
    APP_SRC_USB,                /**< the serial port */
    APP_SRC_CPS,                /**< the control point of the Cycling Power Service */
    APP_SRC_ANT,                /**< the calibration page of ANT+ */
    APP_SRC_LOCAL               /**< the firmware itself (auto zero, power) */
};

/** Channel cmd: a command for the services (app_cmd -> compute, power) */
struct app_cmd_msg {
    uint8_t id;                 /**< enum pm_cmd_id */
    uint8_t source;             /**< enum app_cmd_source */
    struct pm_cmd cmd;          /**< the arguments */
};

/** Longest text of an answer, without the $ACK prefix */
#define APP_CMD_TEXT_LEN        48U

/** Channel cmd_result: the outcome of a command (compute, power -> radio, usb) */
struct app_cmd_result {
    uint8_t id;                 /**< enum pm_cmd_id */
    uint8_t source;             /**< enum app_cmd_source */
    uint8_t err;                /**< pm_err_t */
    int32_t value;              /**< the zero of an offset compensation, or 0 */
    char text[APP_CMD_TEXT_LEN];/**< payload of the $ACK, empty for none */
};

/** Channel system_state: the machine of docs/04 (power -> all) */
struct app_system_state {
    uint8_t state;              /**< enum pm_sysstate */
};

/** Channel battery: the fuel gauge and the charger pins (power -> radio, usb) */
struct app_battery {
    uint8_t soc_pct;
    uint16_t mv;
    bool charging;              /**< CHG low */
    bool fault;                 /**< ERR low */
    bool vbus;                  /**< the cable is in */
    bool gauge;                 /**< the gauge answered */
};

/** Channel vbus: the cable is in or out (usb -> power) */
struct app_vbus {
    bool present;
};

/** Channel health: the flags of docs/06 and what they were judged on (compute -> radio) */
struct app_health {
    uint16_t flags;
    float temp_c;
    int32_t code;
    int32_t zero;
    uint16_t ref_mv;
};

/** Channel settings: the configuration in force changed (app -> all) */
struct app_settings_msg {
    struct pm_settings s;
};

/** Channel dfu: how the update goes (radio -> power, usb) */
enum app_dfu_phase {
    APP_DFU_IDLE = 0,
    APP_DFU_RECEIVING,
    APP_DFU_PENDING,            /**< the image is in place: reboot to apply */
    APP_DFU_REFUSED
};

struct app_dfu {
    uint8_t phase;              /**< enum app_dfu_phase */
    uint8_t percent;
};

#ifdef __cplusplus
}
#endif

#endif /* APP_EVENTS_H */
