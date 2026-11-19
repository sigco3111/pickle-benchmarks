cmake_minimum_required(VERSION 3.13)

# ---------------------------------------------------------------------------
# TakeDeck TD-01 firmware — RP2040 (Seeed Studio XIAO RP2040), Pico SDK 1.5.x
#
#   export PICO_SDK_PATH=/path/to/pico-sdk      # 1.5.1, tinyusb submodule present
#   cmake -S . -B build -DPICO_BOARD=pico -DPICO_TOOLCHAIN_PATH=/path/to/arm-gnu-toolchain
#   cmake --build build                        # -> build/takedeck.elf / .uf2
#
# PICO_BOARD=pico is used as the SDK board profile: the firmware addresses raw
# RP2040 GPIO numbers (see include/config.h) and uses USB CDC, so none of the
# Pico board specific pins (LED on GP25, etc.) are touched. See
# ../HARDWARE_VERIFICATION.md for exactly what was built and what was not.
# ---------------------------------------------------------------------------

include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(takedeck C CXX ASM)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

add_executable(takedeck
    src/main.c
    src/app.c
    src/keys.c
    src/protocol.c
    src/ui.c
    src/ssd1306.c
)

target_include_directories(takedeck PRIVATE include)

target_link_libraries(takedeck
    pico_stdlib
    pico_rand
    hardware_i2c
    hardware_gpio
)

target_compile_definitions(takedeck PRIVATE
    # USB identity shown to the host (VID/PID stay at the Raspberry Pi SDK
    # values; a product for sale needs its own USB-IF assignment)
    USBD_MANUFACTURER="TakeDeck"
    USBD_PRODUCT="TakeDeck TD-01"
    # No vendor reset interface, and no "1200 baud close resets the board"
    # behaviour: a bridge app that reopens the port must not reboot the unit.
    PICO_STDIO_USB_ENABLE_RESET_VIA_VENDOR_INTERFACE=0
    PICO_STDIO_USB_ENABLE_RESET_VIA_BAUD_RATE=0
    # Bus powered: the SDK then advertises 250 mA bMaxPower. The measured
    # budget in REQUIREMENTS.md is far below that.
    PICO_STDIO_USB_DEVICE_SELF_POWERED=0
)

pico_enable_stdio_usb(takedeck 1)
pico_enable_stdio_uart(takedeck 0)

# .elf, .bin, .hex and .uf2 (the .uf2 is what gets copied to the RPI-RP2 drive)
pico_add_extra_outputs(takedeck)

# -Wundef is left out: the SDK headers use `#if LIB_*` patterns that trip it.
target_compile_options(takedeck PRIVATE -Wall -Wextra -Wshadow)
