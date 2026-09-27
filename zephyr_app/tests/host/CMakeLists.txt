# Host tests of the model modules of zephyr_app (Unity + CTest, GCC of the PC).
#
# Each module of zephyr_app/src/model is plain C without Zephyr types, so it
# compiles here as it is, against the PC's libc and libm. tools/fw/host_tests.sh
# drives the presets:
#
#   cmake --preset host-tests && cmake --build --preset host-tests && ctest --preset host-tests
#   cmake --preset host-cov   ...                                (with --coverage, for gcov)

cmake_minimum_required(VERSION 3.20)
project(pm_host_tests LANGUAGES C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS ON)

include(CTest)
include(FetchContent)

FetchContent_Declare(unity
    URL      https://github.com/ThrowTheSwitch/Unity/archive/refs/tags/v2.6.1.tar.gz
    URL_HASH SHA256=b41a66d45a6b99758fb3202ace6178177014d52fc524bf1f72687d93e9867292
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE
)
set(UNITY_EXTENSION_FIXTURE OFF CACHE BOOL "" FORCE)
set(UNITY_EXTENSION_MEMORY OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(unity)
target_compile_definitions(unity PUBLIC UNITY_INCLUDE_DOUBLE)

option(PM_COVERAGE "Compile the code under test with gcov instrumentation" OFF)

set(APP_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../..)

add_library(host_env INTERFACE)
target_include_directories(host_env INTERFACE
    ${CMAKE_CURRENT_SOURCE_DIR}/shim
    ${CMAKE_CURRENT_SOURCE_DIR}/support
    ${APP_DIR}/include
)
target_compile_definitions(host_env INTERFACE PM_HOST_TEST=1)
# The warning set of the firmware plus -Werror: a warning is a failure here.
target_compile_options(host_env INTERFACE
    -Wall
    -Wextra
    -Wno-unused-parameter
    -Werror
    -Werror=implicit-function-declaration
    -Werror=return-type
)
if(PM_COVERAGE)
    target_compile_options(host_env INTERFACE --coverage -O0)
    target_link_options(host_env INTERFACE --coverage)
endif()

# pm_add_test(<name> SOURCES <files under zephyr_app/src> [SUPPORT <files under support/>])
function(pm_add_test name)
    cmake_parse_arguments(T "" "" "SOURCES;SUPPORT" ${ARGN})
    set(code)
    foreach(src IN LISTS T_SOURCES)
        list(APPEND code ${APP_DIR}/src/${src})
    endforeach()
    foreach(src IN LISTS T_SUPPORT)
        list(APPEND code ${CMAKE_CURRENT_SOURCE_DIR}/support/${src})
    endforeach()
    add_executable(${name} ${name}.c ${code})
    target_link_libraries(${name} PRIVATE unity host_env m)
    add_test(NAME ${name} COMMAND ${name})
endfunction()

pm_add_test(test_bridge_calc SOURCES model/bridge_calc.c)
pm_add_test(test_crank_angle SOURCES model/crank_angle.c)
pm_add_test(test_rev_power SOURCES model/rev_power.c)
pm_add_test(test_calib SOURCES model/calib.c model/bridge_calc.c)
pm_add_test(test_cps_encode SOURCES model/cps_encode.c)
pm_add_test(test_pm_settings SOURCES model/pm_settings.c model/bridge_calc.c)
pm_add_test(test_health SOURCES model/health.c)
pm_add_test(test_pm_fsm SOURCES model/pm_fsm.c)
pm_add_test(test_pm_cmd SOURCES model/pm_cmd.c)
