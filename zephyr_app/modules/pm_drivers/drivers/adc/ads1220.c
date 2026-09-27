/**
 * @file ads1220.c
 * @brief TI ADS1220 bridge converter (ti,ads1220)
 *
 * SPI mode 1 (CPOL 0, CPHA 1), MSB first, the only mode the device speaks
 * (SBAS501D 8.5.1). Commands from table 8-7, registers from tables 8-8 to
 * 8-13. Nothing here has run against a converter.
 */

#define DT_DRV_COMPAT ti_ads1220

#include <errno.h>
#include <string.h>

#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/spi.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#include <drivers/adc/ads1220.h>

LOG_MODULE_REGISTER(ads1220, CONFIG_PM_ADC_ADS1220_LOG_LEVEL);

/* Commands (table 8-7) */
#define CMD_RESET           0x06U
#define CMD_START_SYNC      0x08U
#define CMD_POWERDOWN       0x02U
#define CMD_RDATA           0x10U
#define CMD_RREG(rr, nn)    (0x20U | ((rr) << 2) | (nn))
#define CMD_WREG(rr, nn)    (0x40U | ((rr) << 2) | (nn))

/* CONFIG0 (table 8-10) */
#define CFG0_MUX_SHIFT      4
#define CFG0_GAIN_SHIFT     1
#define CFG0_PGA_BYPASS     0x01U
#define MUX_MON_REF         0x0CU
#define MUX_MON_AVDD        0x0DU
/* CONFIG1 (table 8-11) */
#define CFG1_DR_SHIFT       5
#define CFG1_MODE_NORMAL    (0x0U << 3)
#define CFG1_CM_CONTINUOUS  0x04U
/* CONFIG2 (table 8-13) */
#define CFG2_VREF_SHIFT     6
#define CFG2_PSW            0x08U
/* CONFIG3: DRDY on its own pin only (DRDYM 0) */
#define CFG3_DEFAULT        0x00U

/** After RESET: 50 us plus 32 tCLK at 4,096 MHz (8.5.3.1) */
#define RESET_WAIT_US       100U
/** Longest conversion, at 20 SPS, with margin */
#define MONITOR_TIMEOUT_MS  120U
/** Internal reference used by the monitor, mV (8.3.11) */
#define VREF_INTERNAL_MV    2048U

struct ads1220_config {
    struct spi_dt_spec spi;
    struct gpio_dt_spec drdy;
    uint8_t gain_code;
    uint8_t dr_code;
    uint16_t data_rate;
    uint8_t mux;
    uint8_t vref_code;
    bool pga_bypass;
    bool psw;
};

struct ads1220_data {
    const struct device *dev;
    struct gpio_callback drdy_cb;
    ads1220_drdy_cb_t cb;
    void *user;
    uint8_t cfg[4];
    bool continuous;
};

static int spi_write_bytes(const struct device *dev, const uint8_t *tx, size_t n)
{
    const struct ads1220_config *cfg = dev->config;
    const struct spi_buf buf = { .buf = (void *)tx, .len = n };
    const struct spi_buf_set set = { .buffers = &buf, .count = 1U };

    return spi_write_dt(&cfg->spi, &set);
}

static int send_command(const struct device *dev, uint8_t cmd)
{
    return spi_write_bytes(dev, &cmd, 1U);
}

static int write_config(const struct device *dev)
{
    const struct ads1220_data *data = dev->data;
    uint8_t tx[5] = { CMD_WREG(0U, 3U), data->cfg[0], data->cfg[1], data->cfg[2], data->cfg[3] };

    return spi_write_bytes(dev, tx, sizeof(tx));
}

static int read_config(const struct device *dev, uint8_t out[4])
{
    const struct ads1220_config *cfg = dev->config;
    uint8_t tx[5] = { CMD_RREG(0U, 3U), 0U, 0U, 0U, 0U };
    uint8_t rx[5] = { 0U };
    const struct spi_buf txb = { .buf = tx, .len = sizeof(tx) };
    const struct spi_buf rxb = { .buf = rx, .len = sizeof(rx) };
    const struct spi_buf_set txs = { .buffers = &txb, .count = 1U };
    const struct spi_buf_set rxs = { .buffers = &rxb, .count = 1U };
    int err = spi_transceive_dt(&cfg->spi, &txs, &rxs);

    if (err == 0) {
        (void)memcpy(out, &rx[1], 4U);
    }
    return err;
}

/** The configuration of the devicetree, with the given multiplexer and mode */
static void build_config(const struct device *dev, uint8_t mux, bool continuous)
{
    const struct ads1220_config *cfg = dev->config;
    struct ads1220_data *data = dev->data;

    data->cfg[0] = (uint8_t)((mux << CFG0_MUX_SHIFT) | (cfg->gain_code << CFG0_GAIN_SHIFT) |
                             (cfg->pga_bypass ? CFG0_PGA_BYPASS : 0U));
    data->cfg[1] = (uint8_t)((cfg->dr_code << CFG1_DR_SHIFT) | CFG1_MODE_NORMAL |
                             (continuous ? CFG1_CM_CONTINUOUS : 0U));
    data->cfg[2] = (uint8_t)((cfg->vref_code << CFG2_VREF_SHIFT) | (cfg->psw ? CFG2_PSW : 0U));
    data->cfg[3] = CFG3_DEFAULT;
    data->continuous = continuous;
}

int ads1220_reset(const struct device *dev)
{
    const struct ads1220_config *cfg = dev->config;
    uint8_t back[4];
    int err = send_command(dev, CMD_RESET);

    if (err != 0) {
        return err;
    }
    k_busy_wait(RESET_WAIT_US);
    build_config(dev, cfg->mux, false);
    err = write_config(dev);
    if (err != 0) {
        return err;
    }
    /* a write starts a single conversion: read the registers back to check the link */
    err = read_config(dev, back);
    if (err != 0) {
        return err;
    }
    if (memcmp(back, ((struct ads1220_data *)dev->data)->cfg, 4U) != 0) {
        LOG_ERR("configuration read back differs: %02x %02x %02x %02x", back[0], back[1],
                back[2], back[3]);
        return -EIO;
    }
    return 0;
}

int ads1220_start_continuous(const struct device *dev)
{
    const struct ads1220_data *data = dev->data;

    if (!data->continuous) {
        const struct ads1220_config *cfg = dev->config;
        int err;

        build_config(dev, cfg->mux, true);
        err = write_config(dev);
        if (err != 0) {
            return err;
        }
    }
    return send_command(dev, CMD_START_SYNC);
}

int ads1220_start_single(const struct device *dev)
{
    const struct ads1220_data *data = dev->data;

    if (data->continuous) {
        const struct ads1220_config *cfg = dev->config;

        build_config(dev, cfg->mux, false);
        /* the write itself starts a conversion */
        return write_config(dev);
    }
    return send_command(dev, CMD_START_SYNC);
}

int ads1220_powerdown(const struct device *dev)
{
    return send_command(dev, CMD_POWERDOWN);
}

int ads1220_read(const struct device *dev, int32_t *code)
{
    const struct ads1220_config *cfg = dev->config;
    uint8_t tx[3] = { 0U, 0U, 0U };
    uint8_t rx[3] = { 0U };
    const struct spi_buf txb = { .buf = tx, .len = sizeof(tx) };
    const struct spi_buf rxb = { .buf = rx, .len = sizeof(rx) };
    const struct spi_buf_set txs = { .buffers = &txb, .count = 1U };
    const struct spi_buf_set rxs = { .buffers = &rxb, .count = 1U };
    int err = spi_transceive_dt(&cfg->spi, &txs, &rxs);

    if (err != 0) {
        return err;
    }

    uint32_t raw = ((uint32_t)rx[0] << 16) | ((uint32_t)rx[1] << 8) | (uint32_t)rx[2];

    if ((raw & 0x800000U) != 0U) {
        raw |= 0xFF000000U;
    }
    *code = (int32_t)raw;
    return 0;
}

bool ads1220_data_ready(const struct device *dev)
{
    const struct ads1220_config *cfg = dev->config;

    return gpio_pin_get_dt(&cfg->drdy) == 1;
}

int ads1220_read_monitor(const struct device *dev, enum ads1220_monitor what, uint16_t *mv)
{
    const struct ads1220_config *cfg = dev->config;
    const struct ads1220_data *data = dev->data;
    bool was_continuous = data->continuous;
    uint8_t mux = (what == ADS1220_MON_REF) ? MUX_MON_REF : MUX_MON_AVDD;
    int32_t code = 0;
    int err;
    uint32_t waited = 0U;

    build_config(dev, mux, false);
    err = write_config(dev);           /* starts one conversion of the monitor */
    if (err != 0) {
        return err;
    }
    while (!ads1220_data_ready(dev)) {
        if (waited >= MONITOR_TIMEOUT_MS) {
            err = -ETIMEDOUT;
            break;
        }
        k_msleep(1);
        waited++;
    }
    if (err == 0) {
        err = ads1220_read(dev, &code);
    }
    /* back to the bridge input; a write starts a single conversion that is ignored */
    build_config(dev, cfg->mux, was_continuous);
    (void)write_config(dev);
    if (err != 0) {
        return err;
    }
    if (code < 0) {
        code = 0;
    }
    /* code / 2^23 * 2,048 V is V / 4 (gain 1, internal reference) */
    *mv = (uint16_t)(((int64_t)code * 4LL * VREF_INTERNAL_MV) / 8388608LL);
    return 0;
}

static void drdy_isr(const struct device *port, struct gpio_callback *cb, uint32_t pins)
{
    struct ads1220_data *data = CONTAINER_OF(cb, struct ads1220_data, drdy_cb);

    ARG_UNUSED(port);
    ARG_UNUSED(pins);
    if (data->cb != NULL) {
        data->cb(data->dev, data->user);
    }
}

int ads1220_drdy_callback_set(const struct device *dev, ads1220_drdy_cb_t cb, void *user)
{
    const struct ads1220_config *cfg = dev->config;
    struct ads1220_data *data = dev->data;

    data->cb = cb;
    data->user = user;
    return gpio_pin_interrupt_configure_dt(&cfg->drdy, (cb != NULL) ? GPIO_INT_EDGE_TO_ACTIVE
                                                                     : GPIO_INT_DISABLE);
}

uint16_t ads1220_data_rate(const struct device *dev)
{
    const struct ads1220_config *cfg = dev->config;

    return cfg->data_rate;
}

static int ads1220_init(const struct device *dev)
{
    const struct ads1220_config *cfg = dev->config;
    struct ads1220_data *data = dev->data;
    int err;

    data->dev = dev;
    if (!spi_is_ready_dt(&cfg->spi)) {
        LOG_ERR("SPI not ready");
        return -ENODEV;
    }
    if (!gpio_is_ready_dt(&cfg->drdy)) {
        LOG_ERR("DRDY gpio not ready");
        return -ENODEV;
    }
    err = gpio_pin_configure_dt(&cfg->drdy, GPIO_INPUT);
    if (err != 0) {
        return err;
    }
    gpio_init_callback(&data->drdy_cb, drdy_isr, BIT(cfg->drdy.pin));
    err = gpio_add_callback(cfg->drdy.port, &data->drdy_cb);
    if (err != 0) {
        return err;
    }
    err = ads1220_reset(dev);
    if (err != 0) {
        LOG_ERR("no converter: %d", err);
        return err;
    }
    /* nothing to convert until the sample service asks */
    (void)ads1220_powerdown(dev);
    LOG_INF("ADS1220 ready: gain %u, %u SPS", 1U << cfg->gain_code, cfg->data_rate);
    return 0;
}

/* Gain 1..128 to GAIN[2:0]: log2 */
#define GAIN_CODE(g) ((g) == 1 ? 0 : (g) == 2 ? 1 : (g) == 4 ? 2 : (g) == 8 ? 3 : \
                      (g) == 16 ? 4 : (g) == 32 ? 5 : (g) == 64 ? 6 : 7)
/* Data rate to DR[2:0] in normal mode (table 8-12) */
#define DR_CODE(r) ((r) == 20 ? 0 : (r) == 45 ? 1 : (r) == 90 ? 2 : (r) == 175 ? 3 : \
                    (r) == 330 ? 4 : (r) == 600 ? 5 : 6)
#define VREF_CODE(s) (DT_ENUM_IDX(s, vref))

#define ADS1220_DEFINE(inst)                                                                 \
    static struct ads1220_data ads1220_data_##inst;                                          \
    static const struct ads1220_config ads1220_config_##inst = {                             \
        .spi = SPI_DT_SPEC_INST_GET(inst, SPI_OP_MODE_MASTER | SPI_WORD_SET(8) |             \
                                              SPI_TRANSFER_MSB | SPI_MODE_CPHA),             \
        .drdy = GPIO_DT_SPEC_INST_GET(inst, drdy_gpios),                                     \
        .gain_code = GAIN_CODE(DT_INST_PROP(inst, gain)),                                    \
        .dr_code = DR_CODE(DT_INST_PROP(inst, data_rate)),                                   \
        .data_rate = DT_INST_PROP(inst, data_rate),                                          \
        .mux = DT_INST_PROP(inst, mux),                                                      \
        .vref_code = VREF_CODE(DT_DRV_INST(inst)),                                           \
        .pga_bypass = DT_INST_PROP(inst, pga_bypass),                                        \
        .psw = DT_INST_PROP(inst, low_side_switch),                                          \
    };                                                                                       \
    DEVICE_DT_INST_DEFINE(inst, ads1220_init, NULL, &ads1220_data_##inst,                    \
                          &ads1220_config_##inst, POST_KERNEL,                               \
                          CONFIG_PM_ADC_ADS1220_INIT_PRIORITY, NULL);

DT_INST_FOREACH_STATUS_OKAY(ADS1220_DEFINE)
