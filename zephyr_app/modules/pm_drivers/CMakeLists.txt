# SPDX-License-Identifier: CC-BY-NC-4.0

zephyr_include_directories(include)

add_subdirectory_ifdef(CONFIG_PM_ADC_ADS1220 drivers/adc)
add_subdirectory_ifdef(CONFIG_PM_SENSOR_BMA400 drivers/sensor)
