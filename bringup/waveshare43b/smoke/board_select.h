#pragma once
// All compilation units receive these flags via build.sh. Keep the official
// 4.3B profile: do not import the misconfigured 1024x600 vendor LVGL demo.
#ifndef BOARD_WAVESHARE_ESP32_S3_TOUCH_LCD_4_3_B
#error "Use ../build.sh: the exact Waveshare 4.3B profile is required"
#endif
#include <esp_display_panel.hpp>
#include <esp_arduino_version.h>
#if ESP_ARDUINO_VERSION != ESP_ARDUINO_VERSION_VAL(3, 3, 11)
#error "Pinned smoke toolchain: Arduino ESP32 3.3.11 required"
#endif
#if !defined(CONFIG_SPIRAM_MODE_OCT) || CONFIG_SPIRAM_SPEED != 80
#error "This smoke requires OPI PSRAM at 80 MHz"
#endif
