# Waveshare ESP32-S3-Touch-LCD-4.3B

This branch contains the 800×480 display/touch port, native dashboard and scenes,
clock/weather views, Polish/English/German interface, and its host regression tests.
The board profile is `boards/ws_lcd_43b.ini`. Other board definitions are inherited
from upstream and have not been hardware-tested as part of this publication.

## Status

- **Stable: v4.1.0** (2026-11-05). A complete first installation through the
  browser USB installer was confirmed on a 4.3B board.
- **Beta: v4.1.1-beta.1** (2026-11-06) – built on an SDK with an IRAM-safe RGB
  interrupt handler, aimed at the picture glitches below.
- Known issues: occasional picture glitches during long prints (the framebuffer
  stays clean, so the cause is in display scan-out; fix in testing in the beta),
  and a rarely seen [black screen that does not wake on touch (#1)](https://github.com/honzo90/BambuHelper/issues/1).
- Host tests do not prove physical LCD/touch behaviour or full print cycles;
  every beta is checked on a real panel before it becomes stable.

Private hardware-operator scripts, device configuration, captures and test logs
are not part of the repository.

## Build dependencies

- Arduino CLI 1.5.1, Arduino ESP32 core **3.3.11**, esp-x32/2601 (no automatic fallback).
- Python 3, Git, `patch`; Pygments 2.21.0 from `requirements-build.txt`.
- The original `staging/packages/esp32s3-libs-3.3.11.zip` in the Arduino data directory;
  the SDK builder verifies SHA256 `fec76794708694120c6ec803cdbfc7dcd36286ea22b7d38097b7909bbd19f7b5`.
- A few GB of free disk space. The cache64 SDK is built in this checkout, leaving
  the installed Arduino SDK unchanged.

Install the pinned core through Arduino CLI if it is not already installed:

```sh
arduino-cli core update-index --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core install esp32:esp32@3.3.11 --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements-build.txt
python3 -B prepare_build.py
python3 -B bringup/waveshare43b/integration/cache64_sdk.py
python3 -B bringup/waveshare43b/integration/build.py
```

Run these from the repository root. `prepare_build.py` downloads checksum-pinned
public dependencies and creates a sibling `waveshare-4.3b-reference` checkout at
`04cc7ee4a85d796491084fc3baae3589b4f812cf`. It refuses modified dependencies.
Arduino data paths come from Arduino CLI configuration or `WS43B_ARDUINO_DATA`.
The toolchain workflow was developed on macOS; Linux/Windows are unverified.

These commands build only. They do not flash a device or contact a printer.
The resulting firmware uses `BAMBU_MONITOR_ONLY=0` and includes normal printer
controls; it is not a passive monitor build. Generated output stays ignored.
For first installation, use the [WS43B browser USB installer](https://honzo90.github.io/BambuHelper/)
with the exact ESP32-S3-Touch-LCD-4.3B board. Factory installation erases flash
and saved settings; a complete first installation of v4.1.0 was confirmed on a
4.3B board. For an existing installation, prefer the panel WebUI OTA flow
([OTA channel notes](docs/WS43B_OTA_CHANNEL.md)).

## Release builds

Releases use **Arduino ESP32 3.3.11**, **ESP-IDF 5.5.5**, the rebuilt
**cache64_xip** SDK and a **12 MHz** requested RGB PCLK. Each release's
`BUILD-INFO.json` records the exact source commit, SDK provenance, configuration
and validation results. Reproduction requires the separately prepared XIP SDK,
its matching manifest and SHA-256 (`WS43B_XIP_SDK_MANIFEST`,
`WS43B_XIP_SDK_MANIFEST_SHA256`), `WS43B_SDK_PROFILE=cache64_xip` and
`WS43B_RGB_PCLK_HZ=12000000`; the default cache64 build does not reproduce a
release. From v4.1.1 the SDK additionally enables `CONFIG_LCD_RGB_ISR_IRAM_SAFE`
(declared as `rgb_isr_iram_safe` in its manifest). The build fails if a local
filesystem path would end up in the image.

## Host tests

Host tests additionally need `clang++` and Node.js on `PATH`. `prepare_build.py`
already installs ArduinoJson; for a tests-only setup use
`python3 -B prepare_test_dependencies.py` once instead.

```sh
python3 -B scripts/agent_check.py        # all host tests; -k <name> for a subset
```

The long MQTT loopback timing test is opt-in. Read-only WebUI tests against a
live panel live in `bringup/waveshare43b/integration/webui-e2e/` (Playwright).

History: the first public source export (`5b9d48e`, 2026-10-17/18) passed 174
host tests and was rebuilt from a fresh clone on macOS (requested RGB PCLK
16 MHz, stock cache64 SDK). Releases since v4.0.0 use the XIP profile above.

Checked-in font and image headers are sufficient to build. Asset regeneration
requires additional Pillow/Playwright/Chromium tooling described alongside the
asset generators. Font and third-party notices are retained in `licenses/`;
see [attribution](THIRD_PARTY_NOTICES.md).
