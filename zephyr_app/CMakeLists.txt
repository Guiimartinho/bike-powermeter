# SPDX-License-Identifier: CC-BY-NC-4.0
# Bike power meter: the firmware of the crank pod (docs/04-arquitetura-firmware.md)

cmake_minimum_required(VERSION 3.20.0)

# Board: chosen with west build -b (tools/fw/fw.sh defaults to the nRF54LM20 DK).
# Zephyr adds boards/<board>.overlay by name, so each target keeps its pins in
# its own overlay. BOARD_ROOT lets the board of the project live in boards/.
set(BOARD_ROOT ${CMAKE_CURRENT_SOURCE_DIR})

# Drivers of our own, as a Zephyr module inside the application: the ADS1220
# bridge converter and the BMA400 accelerometer (modules/pm_drivers, docs/04)
list(APPEND EXTRA_ZEPHYR_MODULES ${CMAKE_CURRENT_SOURCE_DIR}/modules/pm_drivers)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})

project(bike_powermeter VERSION 0.1.0 LANGUAGES C)

target_compile_options(app PRIVATE
    -Wall
    -Wextra
    -Werror=implicit-function-declaration
    -Werror=return-type
    -Wno-unused-parameter
    -ffunction-sections
    -fdata-sections
)

target_include_directories(app PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

# =============================================================================
# Application: boot, zbus channels, service framework, settings, commands
# =============================================================================
target_sources(app PRIVATE
    src/app/main.c
    src/app/app_channels.c
    src/app/app_svc.c
    src/app/app_cmd.c
    src/app/pm_store.c
)

# =============================================================================
# Services, one thread each (docs/04, Serviços)
# =============================================================================
target_sources(app PRIVATE
    src/svc/sample/sample_svc.c
    src/svc/motion/motion_svc.c
    src/svc/compute/compute_svc.c
    src/svc/radio/radio_svc.c
    src/svc/power/power_svc.c
)

# =============================================================================
# Model: plain C, the same files the host tests compile (docs/04, Modelo)
# =============================================================================
target_sources(app PRIVATE
    src/model/bridge_calc.c
    src/model/calib.c
    src/model/cps_encode.c
    src/model/crank_angle.c
    src/model/health.c
    src/model/pm_cmd.c
    src/model/pm_fsm.c
    src/model/pm_settings.c
    src/model/rev_power.c
)

# =============================================================================
# Radio: the Cycling Power Service, the configuration service, the update
# =============================================================================
target_sources_ifdef(CONFIG_BT app PRIVATE
    src/rf/ble_cps.c
    src/rf/ble_cfg.c
    src/rf/dfu.c
)

# ANT+ Bicycle Power on the sdk-ant add-on, only in ANT builds (ANT=1)
target_sources_ifdef(CONFIG_ANT app PRIVATE
    src/rf/ant_bpwr.c
)

# The update hooks pull bootutil/image.h from the MCUboot side library
if(CONFIG_MCUBOOT_BOOTUTIL_LIB)
    zephyr_link_libraries(MCUBOOT_BOOTUTIL)
endif()

# USB service: the serial of the commands, where the USB device stack is on
if(CONFIG_USB_DEVICE_STACK_NEXT)
    target_sources(app PRIVATE src/svc/usb/usb_svc.c)
endif()
