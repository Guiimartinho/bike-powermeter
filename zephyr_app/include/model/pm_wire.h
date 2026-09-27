/**
 * @file pm_wire.h
 * @brief Little-endian byte helpers shared by the modules that build or
 *        read wire formats (CPS bytes, the settings blob)
 */

#ifndef PM_WIRE_H
#define PM_WIRE_H

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#ifdef __cplusplus
extern "C" {
#endif

static inline size_t pm_put_u8(uint8_t *buf, size_t at, uint8_t v)
{
    buf[at] = v;
    return at + 1U;
}

static inline size_t pm_put_u16(uint8_t *buf, size_t at, uint16_t v)
{
    buf[at] = (uint8_t)(v & 0xFFU);
    buf[at + 1U] = (uint8_t)(v >> 8);
    return at + 2U;
}

static inline size_t pm_put_u32(uint8_t *buf, size_t at, uint32_t v)
{
    at = pm_put_u16(buf, at, (uint16_t)(v & 0xFFFFU));
    return pm_put_u16(buf, at, (uint16_t)(v >> 16));
}

/** A float travels as its IEEE 754 bits, little-endian */
static inline size_t pm_put_f32(uint8_t *buf, size_t at, float v)
{
    uint32_t bits;

    (void)memcpy(&bits, &v, sizeof(bits));
    return pm_put_u32(buf, at, bits);
}

static inline uint16_t pm_get_u16(const uint8_t *buf, size_t at)
{
    return (uint16_t)((uint16_t)buf[at] | ((uint16_t)buf[at + 1U] << 8));
}

static inline uint32_t pm_get_u32(const uint8_t *buf, size_t at)
{
    return (uint32_t)pm_get_u16(buf, at) | ((uint32_t)pm_get_u16(buf, at + 2U) << 16);
}

static inline float pm_get_f32(const uint8_t *buf, size_t at)
{
    uint32_t bits = pm_get_u32(buf, at);
    float v;

    (void)memcpy(&v, &bits, sizeof(v));
    return v;
}

#ifdef __cplusplus
}
#endif

#endif /* PM_WIRE_H */
