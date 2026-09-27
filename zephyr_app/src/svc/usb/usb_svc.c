/**
 * @file usb_svc.c
 * @brief USB service: the serial of the commands, and whether the cable is in
 *
 * docs/04 (Serviços, usb) and docs/05 (Porta serial). With the cable in the
 * magnetic connector the pod is a serial port on the PC (CDC ACM) that
 * takes the same command lines as the configuration service and answers
 * them the same way; the bench of docs/06 needs no radio. The interrupt of
 * the port only moves the bytes into a ring; this thread assembles the
 * lines and hands them to app_cmd.
 *
 * The USB stack also says when VBUS comes and goes, which is how the
 * power service learns the cable is in (the nPM1100 has no pin for it).
 */

#include <string.h>

#include <zephyr/device.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/ring_buffer.h>
/*
 * usbd_msg.h, which usbd.h pulls in, has a static inline that compares an
 * enum with zero (`type >= 0`, NCS v3.3.0); with the -Wextra of this
 * firmware that is a warning of the SDK, not of the project.
 */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wtype-limits"
#include <zephyr/usb/usbd.h>
#pragma GCC diagnostic pop
#include <zephyr/zbus/zbus.h>

#include "app/app_channels.h"
#include "app/app_cmd.h"
#include "app/app_services.h"
#include "app/app_svc.h"
#include "app_types.h"
#include "model/pm_cmd.h"

LOG_MODULE_REGISTER(usb_svc, CONFIG_LOG_DEFAULT_LEVEL);

/*
 * Measured with CONFIG_STACK_USAGE (2026-09-27): usb_thread 184 B, then
 * app_cmd_handle 248 and pm_cmd_parse 360, and the $CFG answers print a
 * float (about 500 B in picolibc): about 1,8 KB with the publish chain
 */
#define USB_STACK_SIZE      3072
#define USB_INBOX_LEN       8

/*
 * Identifiers of the device. 0x1209 is the vendor of open hardware
 * (pid.codes) and 0x0001 the number they keep for tests: a product number
 * of our own has to be asked for there before any of this is sold.
 */
#define USB_VID             0x1209
#define USB_PID             0x0001

struct usb_msg {
    const struct zbus_channel *chan;
    union {
        struct app_cmd_result result;
    } u;
};

K_MSGQ_DEFINE(usb_inbox, sizeof(struct usb_msg), USB_INBOX_LEN, 4);

static void usb_listener(const struct zbus_channel *chan)
{
    struct usb_msg msg = { .chan = chan };

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
    app_inbox_put(&usb_inbox, &msg, "usb");
}

ZBUS_LISTENER_DEFINE(usb_lis, usb_listener);
ZBUS_CHAN_ADD_OBS(chan_cmd_result, usb_lis, 3);

USBD_DEVICE_DEFINE(pm_usbd, DEVICE_DT_GET(DT_NODELABEL(usbhs)), USB_VID, USB_PID);

USBD_DESC_LANG_DEFINE(usb_lang);
USBD_DESC_MANUFACTURER_DEFINE(usb_mfr, APP_NAME);
USBD_DESC_PRODUCT_DEFINE(usb_product, "Bike power meter");
USBD_DESC_SERIAL_NUMBER_DEFINE(usb_sn);

USBD_DESC_CONFIG_DEFINE(usb_fs_desc, "Serial");
USBD_DESC_CONFIG_DEFINE(usb_hs_desc, "Serial");
USBD_CONFIGURATION_DEFINE(usb_fs_config, USB_SCD_SELF_POWERED, 100, &usb_fs_desc);
USBD_CONFIGURATION_DEFINE(usb_hs_config, USB_SCD_SELF_POWERED, 100, &usb_hs_desc);

static const struct device *const cdc_dev = DEVICE_DT_GET(DT_NODELABEL(cdc_acm_uart0));

/* two lines of 64 bytes */
RING_BUF_DECLARE(cdc_rx, 128);

static struct pm_line line;
static bool usb_ready;

/* ---- the serial of the commands ------------------------------------------ */

/** The interrupt only moves the bytes out of the controller */
static void cdc_irq(const struct device *dev, void *user_data)
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
        (void)ring_buf_put(&cdc_rx, buf, (uint32_t)n);
    }
}

static void cdc_process(void)
{
    uint8_t buf[16];
    uint32_t n;

    while ((n = ring_buf_get(&cdc_rx, buf, sizeof(buf))) > 0U) {
        for (uint32_t i = 0U; i < n; i++) {
            if (pm_line_feed(&line, (char)buf[i])) {
                app_cmd_handle(line.buf, strlen(line.buf), APP_SRC_USB);
            }
        }
    }
}

static void cdc_send(const char *text)
{
    if (!device_is_ready(cdc_dev)) {
        return;
    }
    for (const char *p = text; *p != '\0'; p++) {
        uart_poll_out(cdc_dev, (unsigned char)*p);
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
    cdc_send(out);
}

/* ---- the device ---------------------------------------------------------- */

static void usbd_msg(struct usbd_context *const ctx, const struct usbd_msg *msg)
{
    struct app_vbus v;

    ARG_UNUSED(ctx);
    switch (msg->type) {
    case USBD_MSG_VBUS_READY:
        v.present = true;
        (void)app_publish(&chan_vbus, &v);
        break;
    case USBD_MSG_VBUS_REMOVED:
        v.present = false;
        (void)app_publish(&chan_vbus, &v);
        break;
    default:
        break;
    }
}

static int usb_setup(void)
{
    int err = usbd_add_descriptor(&pm_usbd, &usb_lang);

    if (err == 0) {
        err = usbd_add_descriptor(&pm_usbd, &usb_mfr);
    }
    if (err == 0) {
        err = usbd_add_descriptor(&pm_usbd, &usb_product);
    }
    if (err == 0) {
        err = usbd_add_descriptor(&pm_usbd, &usb_sn);
    }
    if (err == 0) {
        err = usbd_add_configuration(&pm_usbd, USBD_SPEED_FS, &usb_fs_config);
    }
    if (err == 0) {
        err = usbd_add_configuration(&pm_usbd, USBD_SPEED_HS, &usb_hs_config);
    }
    if (err == 0) {
        err = usbd_register_all_classes(&pm_usbd, USBD_SPEED_FS, 1U, NULL);
    }
    if (err == 0) {
        err = usbd_register_all_classes(&pm_usbd, USBD_SPEED_HS, 1U, NULL);
    }
    if (err != 0) {
        LOG_ERR("cannot describe the device: %d", err);
        return err;
    }
    usbd_device_set_code_triple(&pm_usbd, USBD_SPEED_FS, USB_BCC_MISCELLANEOUS, 0x02, 0x01);
    usbd_device_set_code_triple(&pm_usbd, USBD_SPEED_HS, USB_BCC_MISCELLANEOUS, 0x02, 0x01);
    err = usbd_msg_register_cb(&pm_usbd, usbd_msg);
    if (err == 0) {
        err = usbd_init(&pm_usbd);
    }
    if (err == 0) {
        err = usbd_enable(&pm_usbd);
    }
    if (err != 0) {
        LOG_ERR("cannot start the USB: %d", err);
        return err;
    }
    usb_ready = true;
    LOG_INF("USB serial ready");
    return 0;
}

static void usb_thread(void *p1, void *p2, void *p3)
{
    struct usb_msg msg;

    ARG_UNUSED(p1);
    ARG_UNUSED(p2);
    ARG_UNUSED(p3);

    pm_line_reset(&line);
    if (device_is_ready(cdc_dev)) {
        (void)uart_irq_callback_user_data_set(cdc_dev, cdc_irq, NULL);
        uart_irq_rx_enable(cdc_dev);
    } else {
        LOG_ERR("no USB serial");
    }
    (void)usb_setup();

    int wdt = app_wdt_add("usb");

    for (;;) {
        if (app_inbox_get(&usb_inbox, &msg, wdt, 100U) != 0) {
            cdc_process();
            continue;
        }
        cdc_process();
        if (msg.chan == &chan_cmd_result) {
            send_result(&msg.u.result);
        } else {
            /* nothing else reaches this inbox */
        }
    }
}

K_THREAD_DEFINE(usb_tid, USB_STACK_SIZE, usb_thread, NULL, NULL, NULL, APP_PRIO_USB, 0,
                SYS_FOREVER_MS);

void usb_svc_start(void)
{
    k_thread_name_set(usb_tid, "usb");
    k_thread_start(usb_tid);
}
