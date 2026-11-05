#!/bin/bash
set -euo pipefail
[[ $# -eq 0 ]] || { echo 'This build-only script accepts no arguments.' >&2; exit 2; }
HERE="$(cd "$(dirname "$0")" && pwd)"
REF="$(cd "$HERE/../../.." && pwd)/waveshare-4.3b-reference"
VENDOR_SHA=04cc7ee4a85d796491084fc3baae3589b4f812cf
if [[ "$(git -C "$REF" rev-parse HEAD)" != "$VENDOR_SHA" ]] || [[ -n "$(git -C "$REF" status --porcelain)" ]]; then
  echo 'Expected pristine pinned Waveshare reference checkout; see WAVESHARE.md.' >&2; exit 1
fi
CORE="$HOME/Library/Arduino15/packages/esp32/hardware/esp32/3.3.11"
[[ -f "$CORE/platform.txt" ]] || { echo 'Required existing Arduino ESP32 core 3.3.11 is missing.' >&2; exit 1; }
mkdir -p "$HERE/build-v4" "$HERE/cache"
export ARDUINO_BUILD_CACHE_PATH="$HERE/cache"
FLAGS='-DESP_PANEL_BOARD_FILE_SKIP -DESP_PANEL_BOARD_DEFAULT_USE_SUPPORTED=1 -DBOARD_WAVESHARE_ESP32_S3_TOUCH_LCD_4_3_B'
FQBN='esp32:esp32:esp32s3:USBMode=hwcdc,CDCOnBoot=cdc,CPUFreq=240,FlashMode=qio,FlashSize=16M,PartitionScheme=custom,PSRAM=opi,DebugLevel=none,EraseFlash=none'
arduino-cli compile --fqbn "$FQBN" --build-path "$HERE/build-v4" \
  --libraries "$REF/examples/Arduino/libraries" \
  --build-property "compiler.cpp.extra_flags=$FLAGS" \
  --build-property "compiler.c.extra_flags=$FLAGS" \
  --build-property 'upload.maximum_size=3145728' \
  "$HERE/smoke"
# Deliberately no upload, flash, erase or serial-port access.
