/**
 * @file dfu.c
 * @brief Firmware update over Bluetooth (mcumgr SMP)
 */

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#if defined(CONFIG_MCUMGR)
#include <zephyr/dfu/mcuboot.h>
#include <zephyr/mgmt/mcumgr/mgmt/callbacks.h>
#include <zephyr/mgmt/mcumgr/grp/img_mgmt/img_mgmt.h>
#include <zephyr/mgmt/mcumgr/grp/img_mgmt/img_mgmt_callbacks.h>
#endif

#include "app/app_channels.h"
#include "rf/dfu.h"

LOG_MODULE_REGISTER(rf_dfu, CONFIG_LOG_DEFAULT_LEVEL);

#if defined(CONFIG_MCUMGR)

static bool moving;
static uint8_t soc_pct = 100U;
static bool vbus;
static uint8_t phase = APP_DFU_IDLE;
static uint8_t published_pct = UINT8_MAX;

static void publish(uint8_t percent)
{
    struct app_dfu msg = { .phase = phase, .percent = percent };

    published_pct = percent;
    (void)app_publish(&chan_dfu, &msg);
}

static bool allowed(void)
{
    return !moving && (vbus || (soc_pct >= DFU_MIN_SOC_PCT));
}

/* the signature is the mgmt_cb typedef of Zephyr: `data` cannot be const */
static enum mgmt_cb_return dfu_callback(uint32_t event, enum mgmt_cb_return prev_status,
                                        int32_t *rc, uint16_t *group, bool *abort_more,
                                        /* cppcheck-suppress constParameterCallback */
                                        void *data, size_t data_size)
{
    ARG_UNUSED(prev_status);
    ARG_UNUSED(group);
    ARG_UNUSED(abort_more);

    switch (event) {
    case MGMT_EVT_OP_IMG_MGMT_DFU_CHUNK: {
        const struct img_mgmt_upload_check *check = data;

        if ((check == NULL) || (data_size < sizeof(*check)) || (check->req == NULL)) {
            break;
        }
        if (!allowed()) {
            LOG_WRN("update refused: moving %d, battery %u%%", (int)moving, soc_pct);
            phase = APP_DFU_REFUSED;
            publish(0U);
            *rc = MGMT_ERR_EACCESSDENIED;
            return MGMT_CB_ERROR_RC;
        }

        size_t off = check->req->off;
        size_t size = check->req->size;
        uint8_t pct = ((size == 0U) || (size == SIZE_MAX) || (off == SIZE_MAX))
                          ? 0U : (uint8_t)((100U * off) / size);

        phase = APP_DFU_RECEIVING;
        if (pct != published_pct) {
            publish(pct);
        }
        break;
    }
    case MGMT_EVT_OP_IMG_MGMT_DFU_STARTED:
        LOG_INF("update started");
        phase = APP_DFU_RECEIVING;
        publish(0U);
        break;
    case MGMT_EVT_OP_IMG_MGMT_DFU_PENDING:
        LOG_INF("update image in place");
        phase = APP_DFU_PENDING;
        publish(100U);
        break;
    case MGMT_EVT_OP_IMG_MGMT_DFU_STOPPED:
        if (phase != APP_DFU_PENDING) {
            LOG_WRN("update stopped");
            phase = APP_DFU_IDLE;
            publish(0U);
        }
        break;
    default:
        break;
    }
    return MGMT_CB_OK;
}

static struct mgmt_callback dfu_cb = {
    .callback = dfu_callback,
    .event_id = (MGMT_EVT_OP_IMG_MGMT_DFU_CHUNK | MGMT_EVT_OP_IMG_MGMT_DFU_STARTED |
                 MGMT_EVT_OP_IMG_MGMT_DFU_PENDING | MGMT_EVT_OP_IMG_MGMT_DFU_STOPPED),
};

int rf_dfu_init(void)
{
    mgmt_callback_register(&dfu_cb);

    /*
     * MCUboot boots a new image once and takes it back at the next reset
     * unless it is confirmed. Getting this far means the services are up
     * and the radio answers, so the image works: keep it.
     */
    if (!boot_is_img_confirmed()) {
        int err = boot_write_img_confirmed();

        if (err != 0) {
            LOG_ERR("cannot confirm the running image: %d", err);
            return err;
        }
        LOG_INF("running image confirmed");
    }
    return 0;
}

void rf_dfu_set_conditions(bool now_moving, uint8_t soc, bool cable)
{
    moving = now_moving;
    soc_pct = soc;
    vbus = cable;
}

bool rf_dfu_busy(void)
{
    return (phase == APP_DFU_RECEIVING) || (phase == APP_DFU_PENDING);
}

#else /* CONFIG_MCUMGR */

int rf_dfu_init(void)
{
    return 0;
}

void rf_dfu_set_conditions(bool now_moving, uint8_t soc, bool cable)
{
    ARG_UNUSED(now_moving);
    ARG_UNUSED(soc);
    ARG_UNUSED(cable);
}

bool rf_dfu_busy(void)
{
    return false;
}

#endif /* CONFIG_MCUMGR */
