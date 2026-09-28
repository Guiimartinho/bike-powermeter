/**
 * @file app_services.h
 * @brief Start of each service thread, in the order main() calls them
 *
 * The threads are defined statically and start stopped; main() starts them
 * once the settings and the watchdog are ready.
 */

#ifndef APP_SERVICES_H
#define APP_SERVICES_H

void power_svc_start(void);
void sample_svc_start(void);
void motion_svc_start(void);
void compute_svc_start(void);
void radio_svc_start(void);
/* The serial port of the commands: USB on a target that has one, a plain
 * UART on the pod (the nRF54L15 has no USB). Only one of the two is
 * built, and CMakeLists.txt picks by CONFIG_USB_DEVICE_STACK_NEXT. */
void usb_svc_start(void);
void serial_svc_start(void);

/** Tell the system machine that every service started (Boot -> Idle) */
void power_svc_ready(void);

#endif /* APP_SERVICES_H */
