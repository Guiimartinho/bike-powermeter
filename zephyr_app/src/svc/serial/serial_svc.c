/**
 * @file serial_svc.c
 * @brief Serial service: the port of the commands, and whether the cable is in
 *
 * docs/04 (Serviços) and docs/05 (Porta serial). The same job the USB
 * service does on the DK, over a plain UART, because the pod's SoC has no
 * USB: `usbhs` does not exist on the nRF54L15
 * (hardware_powermeter/09-modulo-de-radio.md). The port leaves the pod on
 * uart20, through the two contacts of the magnetic connector that used to
 * carry D+ and D-, so the calibration bench of docs/06 still needs no radio,
 * and MCUboot's serial recovery rides the same pair.
 *
 * The interrupt only moves bytes into a ring; this thread assembles the
 * lines and hands them to app_cmd, exactly as the USB one does.
 *
 * Whether the cable is in is a GPIO here and not a stack event. The nPM1100
 * has no pin that reports it, and without a USB stack there is nothing else
 * to ask, so the board divides VBUS 1 M / 470 k into `vbus-sense`: 5,0 V of
 * the cable become 1,60, a solid high on a 3,0 V input, and the divider
 * leaks 3,4 uA only while the cable is in. The pin is read on both edges and
 * on start-up, because the cable may already be there when the pod boots.
 */

#include <string.h>

#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/ring_buffer.h>
#include <zephyr/zbus/zbus.h>

#include "app/app_channels.h"
#include "app/app_cmd.h"
#include "app/app_services.h"
#include "app/app_svc.h"
#include "app_types.h"
#include "model/pm_cmd.h"

LOG_MODULE_REGISTER(serial_svc, CONFIG_LOG_DEFAULT_LEVEL);

/*
 * The same chain the USB service measured with CONFIG_STACK_USAGE
 * (2026-09-27): the thread itself, then app_cmd_handle at 248 B and
 * pm_cmd_parse at 360, and a $CFG answer prints a float (about 500 B in
 * picolibc). This one carries no USB stack, so it is the smaller of the two,
 * and it keeps the same size until it is measured on a board.
 */
#define SERIAL_STACK_SIZE   3072
#define SERIAL_INBOX_LEN    8

struct serial_msg {
    const struct zbus_channel *chan;
    union {
        struct app_cmd_result result;
    } u;
};

K_MSGQ_DEFINE(serial_inbox, sizeof(struct serial_msg), SERIAL_INBOX_LEN, 4);

static void serial_listener(const struct zbus_channel *chan)
{
    struct serial_msg msg = { .chan = chan };

    if (chan == &chan_cmd_result) {
        const struct app_cmd_result *r = zbus_chan_const_msg(chan);

        if (r->source != APP_SRC_USB) {
            return;
        }
    }
    if (zbus_chan_msg_size(chan) > sizeof(msg.u)) {
        return;
    }
    (void)memcpy(&msg.u, zbus_chan_const_msg(chan), zbus_chan_msg_size(chan));
    app_inbox_put(&serial_inbox, &msg, "serial");
}

ZBUS_LISTENER_DEFINE(serial_lis, serial_listener);
ZBUS_CHAN_ADD_OBS(chan_cmd_result, serial_lis, 3);

static const struct device *const port = DEVICE_DT_GET(DT_CHOSEN(zephyr_console));

#if DT_NODE_HAS_STATUS(DT_ALIAS(vbus_sense), okay)
static const struct gpio_dt_spec vbus = GPIO_DT_SPEC_GET(DT_ALIAS(vbus_sense), gpios);
static struct gpio_callback vbus_cb;
#endif

/* two lines of 64 bytes */
RING_BUF_DECLARE(serial_rx, 128);

static struct pm_line line;

/* ---- the serial of the commands ------------------------------------------ */

/** The interrupt only moves the bytes out of the controller */
static void serial_irq(const struct device *dev, void *user_data)
{
    uint8_t buf[16];

    ARG_UNUSED(user_data);
    if (!uart_irq_update(dev)) {
        return;
    }
    while (uart_irq_rx_ready(dev)) {
        int n = uart_fifo_read(dev, buf, sizeof(buf));

        if (n <= 0) {
            break;
        }
        (void)ring_buf_put(&serial_rx, buf, (uint32_t)n);
    }
}

static void serial_process(void)
{
    uint8_t buf[16];
    uint32_t n;

    while ((n = ring_buf_get(&serial_rx, buf, sizeof(buf))) > 0U) {
        for (uint32_t i = 0U; i < n; i++) {
            if (pm_line_feed(&line, (char)buf[i])) {
                app_cmd_handle(line.buf, strlen(line.buf), APP_SRC_USB);
            }
        }
    }
}

static void serial_send(const char *text)
{
    if (!device_is_ready(port)) {
        return;
    }
    for (const char *p = text; *p != '\0'; p++) {
        uart_poll_out(port, (unsigned char)*p);
    }
}

static void send_result(const struct app_cmd_result *r)
{
    char out[80];

    if (r->err == (uint8_t)PM_OK) {
        (void)pm_cmd_ack(out, sizeof(out), r->text);
    } else {
        (void)pm_cmd_nak(out, sizeof(out), (pm_err_t)r->err);
    }
    serial_send(out);
}

/* ---- the cable ----------------------------------------------------------- */

#if DT_NODE_HAS_STATUS(DT_ALIAS(vbus_sense), okay)
/** The ISR only publishes a bool: no work here, by the rule of docs/04 */
static void vbus_changed(const struct device *dev, struct gpio_callback *cb, uint32_t pins)
{
    struct app_vbus v;

    ARG_UNUSED(dev);
    ARG_UNUSED(cb);
    ARG_UNUSED(pins);
    v.present = gpio_pin_get_dt(&vbus) == 1;
    (void)app_publish(&chan_vbus, &v);
}

static void vbus_setup(void)
{
    struct app_vbus v;

    if (!gpio_is_ready_dt(&vbus)) {
        LOG_ERR("no VBUS sense pin");
        return;
    }
    if (gpio_pin_configure_dt(&vbus, GPIO_INPUT) != 0) {
        LOG_ERR("cannot read the VBUS sense pin");
        return;
    }
    if (gpio_pin_interrupt_configure_dt(&vbus, GPIO_INT_EDGE_BOTH) == 0) {
        gpio_init_callback(&vbus_cb, vbus_changed, BIT(vbus.pin));
        (void)gpio_add_callback_dt(&vbus, &vbus_cb);
    }
    /* the cable may already be in when the pod boots */
    v.present = gpio_pin_get_dt(&vbus) == 1;
    (void)app_publish(&chan_vbus, &v);
}
#else
static void vbus_setup(void)
{
    LOG_WRN("no vbus-sense alias: the pod cannot tell that the cable is in");
}
#endif

/* ---- the thread ---------------------------------------------------------- */

static void serial_thread(void *p1, void *p2, void *p3)
{
    struct serial_msg msg;

    ARG_UNUSED(p1);
    ARG_UNUSED(p2);
    ARG_UNUSED(p3);

    pm_line_reset(&line);
    if (device_is_ready(port)) {
        (void)uart_irq_callback_user_data_set(port, serial_irq, NULL);
        uart_irq_rx_enable(port);
        LOG_INF("serial commands ready");
    } else {
        LOG_ERR("no serial port");
    }
    vbus_setup();

    int wdt = app_wdt_add("serial");

    for (;;) {
        if (app_inbox_get(&serial_inbox, &msg, wdt, 100U) != 0) {
            serial_process();
            continue;
        }
        serial_process();
        if (msg.chan == &chan_cmd_result) {
            send_result(&msg.u.result);
        } else {
            /* nothing else reaches this inbox */
        }
    }
}

K_THREAD_DEFINE(serial_tid, SERIAL_STACK_SIZE, serial_thread, NULL, NULL, NULL,
                APP_PRIO_USB, 0, SYS_FOREVER_MS);

void serial_svc_start(void)
{
    k_thread_name_set(serial_tid, "serial");
    k_thread_start(serial_tid);
}
