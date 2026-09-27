/**
 * @file bma400.c
 * @brief Bosch BMA400 accelerometer on SPI (bosch,bma400)
 *
 * SPI mode 0 (CPOL 0, CPHA 0), MSB first; a read carries the address with
 * bit 7 set, then one dummy byte, then the data (datasheet 6.2); the very
 * first SPI packet after power-up switches the device from I2C to SPI and
 * is ignored, so the chip id is read twice. Registers from the register
 * map of BST-BMA400-DS000-14 revision 2.3. Nothing here has run against a
 * sensor.
 */

#define DT_DRV_COMPAT bosch_bma400

#include <errno.h>
#include <string.h>

#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/drivers/spi.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#include <drivers/sensor/bma400.h>

LOG_MODULE_REGISTER(bma400, CONFIG_PM_SENSOR_BMA400_LOG_LEVEL);

/* Registers */
#define REG_CHIPID          0x00U
#define REG_STATUS          0x03U
#define REG_ACC_X_LSB       0x04U
#define REG_INT_STAT0       0x0EU
#define REG_ACC_CONFIG0     0x19U
#define REG_ACC_CONFIG1     0x1AU
#define REG_ACC_CONFIG2     0x1BU
#define REG_INT_CONFIG0     0x1FU
#define REG_INT_CONFIG1     0x20U
#define REG_INT1_MAP        0x21U
#define REG_INT12_IO_CTRL   0x24U
#define REG_AUTOWAKEUP_1    0x2DU
#define REG_WKUP_INT_CONFIG0 0x2FU
#define REG_WKUP_INT_CONFIG1 0x30U
#define REG_CMD             0x7EU

#define CHIP_ID             0x90U
#define CMD_SOFTRESET       0xB6U
#define SPI_READ            0x80U

/* ACC_CONFIG0 */
#define CFG0_POWER_MASK     0x03U
/* ACC_CONFIG1 */
#define CFG1_RANGE_SHIFT    6
#define CFG1_OSR_SHIFT      4
/* ACC_CONFIG2: data_src_reg 0 = acc_filt1 (variable ODR) */
#define CFG2_FILT1          0x00U
/* INT_CONFIG0 */
#define INT0_DRDY_EN        0x80U
/* INT1_MAP */
#define MAP1_DRDY           0x80U
#define MAP1_WKUP           0x01U
/* INT12_IO_CTRL: int1 active high, push-pull */
#define IO_INT1_HIGH        0x02U
/* AUTOWAKEUP_1 */
#define AWK1_WKUP_INT       0x02U
/* WKUP_INT_CONFIG0 */
#define WKUP_XYZ_EN         0xE0U
#define WKUP_SAMPLES_SHIFT  2
#define WKUP_REFU_ONETIME   0x01U
/* STATUS */
#define STATUS_DRDY         0x80U

/** After a soft reset and after leaving sleep mode (datasheet, example 1) */
#define WAKE_WAIT_US        1500U
#define RESET_WAIT_MS       2U

struct bma400_config {
    struct spi_dt_spec spi;
    struct gpio_dt_spec int1;
    uint8_t range_g;
    uint8_t range_code;
    uint8_t odr_code;
    uint8_t osr;
};

struct bma400_data {
    const struct device *dev;
    int16_t raw[3];
    uint8_t range_g;
    struct gpio_callback int1_cb;
    sensor_trigger_handler_t drdy_handler;
    const struct sensor_trigger *drdy_trig;
    sensor_trigger_handler_t wake_handler;
    const struct sensor_trigger *wake_trig;
    struct k_sem sem;
    K_KERNEL_STACK_MEMBER(stack, CONFIG_PM_SENSOR_BMA400_THREAD_STACK_SIZE);
    struct k_thread thread;
};

static int reg_read(const struct device *dev, uint8_t reg, uint8_t *buf, size_t n)
{
    const struct bma400_config *cfg = dev->config;
    uint8_t hdr[2] = { (uint8_t)(reg | SPI_READ), 0U };
    const struct spi_buf tx[1] = { { .buf = hdr, .len = sizeof(hdr) } };
    const struct spi_buf rx[2] = { { .buf = NULL, .len = sizeof(hdr) }, { .buf = buf, .len = n } };
    const struct spi_buf_set txs = { .buffers = tx, .count = 1U };
    const struct spi_buf_set rxs = { .buffers = rx, .count = 2U };

    return spi_transceive_dt(&cfg->spi, &txs, &rxs);
}

static int reg_write(const struct device *dev, uint8_t reg, uint8_t val)
{
    const struct bma400_config *cfg = dev->config;
    uint8_t tx[2] = { reg, val };
    const struct spi_buf buf = { .buf = tx, .len = sizeof(tx) };
    const struct spi_buf_set set = { .buffers = &buf, .count = 1U };

    return spi_write_dt(&cfg->spi, &set);
}

static int set_power_mode(const struct device *dev, enum bma400_power_mode mode)
{
    const struct bma400_config *cfg = dev->config;
    uint8_t v = (uint8_t)((cfg->osr << 5) | ((uint8_t)mode & CFG0_POWER_MASK));
    int err = reg_write(dev, REG_ACC_CONFIG0, v);

    if (err == 0) {
        k_busy_wait(WAKE_WAIT_US);
    }
    return err;
}

static int bma400_sample_fetch(const struct device *dev, enum sensor_channel chan)
{
    struct bma400_data *data = dev->data;
    uint8_t buf[6];
    int err;

    if ((chan != SENSOR_CHAN_ALL) && (chan != SENSOR_CHAN_ACCEL_XYZ) &&
        (chan != SENSOR_CHAN_ACCEL_X) && (chan != SENSOR_CHAN_ACCEL_Y) &&
        (chan != SENSOR_CHAN_ACCEL_Z)) {
        return -ENOTSUP;
    }
    err = reg_read(dev, REG_ACC_X_LSB, buf, sizeof(buf));
    if (err != 0) {
        return err;
    }
    for (size_t i = 0U; i < 3U; i++) {
        int32_t v = (int32_t)buf[2U * i] + (256 * (int32_t)(buf[(2U * i) + 1U] & 0x0FU));

        if (v > 2047) {
            v -= 4096;
        }
        data->raw[i] = (int16_t)v;
    }
    return 0;
}

/** 12 bits over ± range: one LSB is range / 2048 g */
static void to_value(const struct bma400_data *data, int16_t raw, struct sensor_value *val)
{
    int64_t um_s2 = ((int64_t)raw * (int64_t)data->range_g * 9806650LL) / 2048LL;

    val->val1 = (int32_t)(um_s2 / 1000000LL);
    val->val2 = (int32_t)(um_s2 % 1000000LL);
}

static int bma400_channel_get(const struct device *dev, enum sensor_channel chan,
                              struct sensor_value *val)
{
    const struct bma400_data *data = dev->data;

    switch (chan) {
    case SENSOR_CHAN_ACCEL_X:
        to_value(data, data->raw[0], val);
        break;
    case SENSOR_CHAN_ACCEL_Y:
        to_value(data, data->raw[1], val);
        break;
    case SENSOR_CHAN_ACCEL_Z:
        to_value(data, data->raw[2], val);
        break;
    case SENSOR_CHAN_ACCEL_XYZ:
        to_value(data, data->raw[0], &val[0]);
        to_value(data, data->raw[1], &val[1]);
        to_value(data, data->raw[2], &val[2]);
        break;
    default:
        return -ENOTSUP;
    }
    return 0;
}

static uint8_t odr_code_of(int32_t hz)
{
    switch (hz) {
    case 12:
        return 0x05U;
    case 25:
        return 0x06U;
    case 50:
        return 0x07U;
    case 100:
        return 0x08U;
    case 200:
        return 0x09U;
    case 400:
        return 0x0AU;
    case 800:
        return 0x0BU;
    default:
        return 0U;
    }
}

static int write_config1(const struct device *dev, uint8_t range_code, uint8_t odr_code)
{
    const struct bma400_config *cfg = dev->config;

    return reg_write(dev, REG_ACC_CONFIG1,
                     (uint8_t)((range_code << CFG1_RANGE_SHIFT) | (cfg->osr << CFG1_OSR_SHIFT) |
                               odr_code));
}

/** The wake-up interrupt of the low power mode, or off with threshold 0 */
static int configure_wakeup(const struct device *dev, int32_t thresh_mg, int32_t samples)
{
    struct bma400_data *data = dev->data;
    int err;

    if (thresh_mg <= 0) {
        err = reg_write(dev, REG_AUTOWAKEUP_1, 0U);
        return err;
    }
    if ((samples < 1) || (samples > 8)) {
        return -EINVAL;
    }
    /* one LSB of the threshold is 2^(2+range_code) / 256 g (datasheet, WKUP_INT_CONFIG1) */
    int32_t lsb_mg = (1000 * (4 << ((data->range_g == 2U) ? 0 : (data->range_g == 4U) ? 1 :
                                    (data->range_g == 8U) ? 2 : 3))) / 256;
    int32_t code = (thresh_mg + (lsb_mg / 2)) / lsb_mg;

    if (code > 255) {
        code = 255;
    }
    if (code < 1) {
        code = 1;
    }
    err = reg_write(dev, REG_WKUP_INT_CONFIG1, (uint8_t)code);
    if (err == 0) {
        err = reg_write(dev, REG_WKUP_INT_CONFIG0,
                        (uint8_t)(WKUP_XYZ_EN | ((uint8_t)(samples - 1) << WKUP_SAMPLES_SHIFT) |
                                  WKUP_REFU_ONETIME));
    }
    if (err == 0) {
        err = reg_write(dev, REG_AUTOWAKEUP_1, AWK1_WKUP_INT);
    }
    return err;
}

static int bma400_attr_set(const struct device *dev, enum sensor_channel chan,
                           enum sensor_attribute attr, const struct sensor_value *val)
{
    const struct bma400_config *cfg = dev->config;
    struct bma400_data *data = dev->data;

    if ((chan != SENSOR_CHAN_ACCEL_XYZ) && (chan != SENSOR_CHAN_ALL)) {
        return -ENOTSUP;
    }
    switch ((int)attr) {
    case SENSOR_ATTR_SAMPLING_FREQUENCY: {
        uint8_t code = odr_code_of(val->val1);
        uint8_t range_code = (data->range_g == 2U) ? 0U : (data->range_g == 4U) ? 1U :
                             (data->range_g == 8U) ? 2U : 3U;

        if (code == 0U) {
            return -EINVAL;
        }
        return write_config1(dev, range_code, code);
    }
    case SENSOR_ATTR_FULL_SCALE: {
        uint8_t range_code;

        switch (val->val1) {
        case 2:
            range_code = 0U;
            break;
        case 4:
            range_code = 1U;
            break;
        case 8:
            range_code = 2U;
            break;
        case 16:
            range_code = 3U;
            break;
        default:
            return -EINVAL;
        }
        data->range_g = (uint8_t)val->val1;
        return write_config1(dev, range_code, cfg->odr_code);
    }
    case BMA400_ATTR_POWER_MODE:
        if ((val->val1 < 0) || (val->val1 > (int32_t)BMA400_MODE_NORMAL)) {
            return -EINVAL;
        }
        return set_power_mode(dev, (enum bma400_power_mode)val->val1);
    case BMA400_ATTR_WAKEUP:
        return configure_wakeup(dev, val->val1, val->val2);
    default:
        return -ENOTSUP;
    }
}

static void int1_isr(const struct device *port, struct gpio_callback *cb, uint32_t pins)
{
    struct bma400_data *data = CONTAINER_OF(cb, struct bma400_data, int1_cb);

    ARG_UNUSED(port);
    ARG_UNUSED(pins);
    k_sem_give(&data->sem);
}

/** The trigger thread: the interrupt gave the semaphore, this calls the handlers */
static void bma400_thread(void *p1, void *p2, void *p3)
{
    struct bma400_data *data = p1;

    ARG_UNUSED(p2);
    ARG_UNUSED(p3);
    for (;;) {
        k_sem_take(&data->sem, K_FOREVER);
        if (data->wake_handler != NULL) {
            uint8_t st = 0U;

            if ((reg_read(data->dev, REG_INT_STAT0, &st, 1U) == 0) && ((st & MAP1_WKUP) != 0U)) {
                data->wake_handler(data->dev, data->wake_trig);
                continue;
            }
        }
        if (data->drdy_handler != NULL) {
            data->drdy_handler(data->dev, data->drdy_trig);
        }
    }
}

static int update_int1_map(const struct device *dev)
{
    struct bma400_data *data = dev->data;
    uint8_t map = 0U;
    int err;

    if (data->drdy_handler != NULL) {
        map |= MAP1_DRDY;
    }
    if (data->wake_handler != NULL) {
        map |= MAP1_WKUP;
    }
    err = reg_write(dev, REG_INT1_MAP, map);
    if (err == 0) {
        err = reg_write(dev, REG_INT_CONFIG0, (data->drdy_handler != NULL) ? INT0_DRDY_EN : 0U);
    }
    return err;
}

static int bma400_trigger_set(const struct device *dev, const struct sensor_trigger *trig,
                              sensor_trigger_handler_t handler)
{
    const struct bma400_config *cfg = dev->config;
    struct bma400_data *data = dev->data;
    int err;

    switch ((int)trig->type) {
    case SENSOR_TRIG_DATA_READY:
        data->drdy_handler = handler;
        data->drdy_trig = trig;
        break;
    case BMA400_TRIG_WAKEUP:
        data->wake_handler = handler;
        data->wake_trig = trig;
        break;
    default:
        return -ENOTSUP;
    }
    err = update_int1_map(dev);
    if (err != 0) {
        return err;
    }
    bool any = (data->drdy_handler != NULL) || (data->wake_handler != NULL);

    return gpio_pin_interrupt_configure_dt(&cfg->int1,
                                           any ? GPIO_INT_EDGE_TO_ACTIVE : GPIO_INT_DISABLE);
}

static int bma400_init(const struct device *dev)
{
    const struct bma400_config *cfg = dev->config;
    struct bma400_data *data = dev->data;
    uint8_t id = 0U;
    int err;

    data->dev = dev;
    data->range_g = cfg->range_g;
    if (!spi_is_ready_dt(&cfg->spi)) {
        LOG_ERR("SPI not ready");
        return -ENODEV;
    }
    if (!gpio_is_ready_dt(&cfg->int1)) {
        LOG_ERR("INT1 gpio not ready");
        return -ENODEV;
    }
    /* the first packet switches the interface to SPI and is ignored */
    (void)reg_read(dev, REG_CHIPID, &id, 1U);
    err = reg_read(dev, REG_CHIPID, &id, 1U);
    if (err != 0) {
        return err;
    }
    if (id != CHIP_ID) {
        LOG_ERR("chip id 0x%02x, expected 0x%02x", id, CHIP_ID);
        return -ENODEV;
    }
    err = reg_write(dev, REG_CMD, CMD_SOFTRESET);
    if (err != 0) {
        return err;
    }
    k_msleep(RESET_WAIT_MS);
    /* back to SPI after the reset, and the id again */
    (void)reg_read(dev, REG_CHIPID, &id, 1U);
    err = reg_read(dev, REG_CHIPID, &id, 1U);
    if ((err != 0) || (id != CHIP_ID)) {
        LOG_ERR("no sensor after reset");
        return -EIO;
    }
    err = set_power_mode(dev, BMA400_MODE_NORMAL);
    if (err == 0) {
        err = write_config1(dev, cfg->range_code, cfg->odr_code);
    }
    if (err == 0) {
        err = reg_write(dev, REG_ACC_CONFIG2, CFG2_FILT1);
    }
    if (err == 0) {
        err = reg_write(dev, REG_INT12_IO_CTRL, IO_INT1_HIGH);
    }
    if (err == 0) {
        err = reg_write(dev, REG_INT_CONFIG1, 0U);    /* non-latched */
    }
    if (err != 0) {
        return err;
    }

    err = gpio_pin_configure_dt(&cfg->int1, GPIO_INPUT);
    if (err != 0) {
        return err;
    }
    gpio_init_callback(&data->int1_cb, int1_isr, BIT(cfg->int1.pin));
    err = gpio_add_callback(cfg->int1.port, &data->int1_cb);
    if (err != 0) {
        return err;
    }
    k_sem_init(&data->sem, 0, 1);
    (void)k_thread_create(&data->thread, data->stack,
                          K_KERNEL_STACK_SIZEOF(data->stack), bma400_thread, data, NULL, NULL,
                          K_PRIO_COOP(CONFIG_PM_SENSOR_BMA400_THREAD_PRIORITY), 0, K_NO_WAIT);
    (void)k_thread_name_set(&data->thread, "bma400");
    LOG_INF("BMA400 ready: %u g, odr code 0x%02x", cfg->range_g, cfg->odr_code);
    return 0;
}

static DEVICE_API(sensor, bma400_api) = {
    .sample_fetch = bma400_sample_fetch,
    .channel_get = bma400_channel_get,
    .attr_set = bma400_attr_set,
    .trigger_set = bma400_trigger_set,
};

#define RANGE_CODE(g) ((g) == 2 ? 0 : (g) == 4 ? 1 : (g) == 8 ? 2 : 3)
#define ODR_CODE(hz) ((hz) == 12 ? 0x05 : (hz) == 25 ? 0x06 : (hz) == 50 ? 0x07 :         \
                      (hz) == 100 ? 0x08 : (hz) == 200 ? 0x09 : (hz) == 400 ? 0x0A : 0x0B)

#define BMA400_DEFINE(inst)                                                                  \
    static struct bma400_data bma400_data_##inst;                                            \
    static const struct bma400_config bma400_config_##inst = {                               \
        .spi = SPI_DT_SPEC_INST_GET(inst, SPI_OP_MODE_MASTER | SPI_WORD_SET(8) |             \
                                              SPI_TRANSFER_MSB),                             \
        .int1 = GPIO_DT_SPEC_INST_GET(inst, int1_gpios),                                     \
        .range_g = DT_INST_PROP(inst, range),                                                \
        .range_code = RANGE_CODE(DT_INST_PROP(inst, range)),                                 \
        .odr_code = ODR_CODE(DT_INST_PROP(inst, odr)),                                       \
        .osr = DT_INST_PROP(inst, osr),                                                      \
    };                                                                                       \
    SENSOR_DEVICE_DT_INST_DEFINE(inst, bma400_init, NULL, &bma400_data_##inst,               \
                                 &bma400_config_##inst, POST_KERNEL,                         \
                                 CONFIG_SENSOR_INIT_PRIORITY, &bma400_api);

DT_INST_FOREACH_STATUS_OKAY(BMA400_DEFINE)
