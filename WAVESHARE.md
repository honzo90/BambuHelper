# Waveshare ESP32-S3-Touch-LCD-4.3B

This branch contains the 800×480 display/touch port, native dashboard and scenes,
clock/weather views, Polish/English interface, and its host regression tests.
The board profile is `boards/ws_lcd_43b.ini`. Other board definitions are inherited
from upstream and have not been hardware-tested as part of this publication.

## Snapshot and status

Application sources match the recorded 16 October 2026 panel build (23:20:30 +0200):
SHA256 `96d92f834b9a9145f859578ffdbb1caff2c39bc09bb23ff9a90ede786c5dd07f`,
2,864,112 bytes, Arduino ESP32 3.3.11, RGB PCLK 16 MHz. This hash identifies the
locally tested candidate; no binary with this hash is distributed here and a
fresh build is not claimed to be bit-for-bit identical.

The recorded flash verification matched the installed app to that candidate.
Physical acceptance remains incomplete: a dark screen with no touch wake was
reported, its cause is unverified, and full print-cycle checks remain pending.
Host tests and a later diagnostic observation do not resolve this known issue.

Packaging changes only make build/test tooling portable: Arduino tool paths,
public pinned cache64 build inputs, Node lookup and a standalone upstream LED
fixture. Application sources are unchanged. Private hardware-operator scripts,
device configuration, captures and test logs are excluded.

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
Flashing, OTA and recovery instructions are outside this initial source upload.

## Host tests

Host tests additionally need `clang++` and Node.js on `PATH`. `prepare_build.py`
already installs ArduinoJson; for a tests-only setup use
`python3 -B prepare_test_dependencies.py` once instead.

```sh
python3 -B -m unittest discover -s bringup/waveshare43b/integration/tests -p 'test_*.py'
```

Export validation on 17 October 2026: **174 host tests passed, 1 optional test
skipped**. The sandbox initially blocked 10 MQTT loopback cases; all 10 passed
when rerun with local socket access. A full firmware rebuild of this exported
snapshot has not been performed.

The long MQTT loopback timing test is opt-in. The private historical flash-uploader
test is excluded along with its device-specific uploader. These tests do not
prove physical LCD/touch behavior or printer-cycle acceptance.

Checked-in font and image headers are sufficient to build. Asset regeneration
requires additional Pillow/Playwright/Chromium tooling described alongside the
asset generators. Font and third-party notices are retained in `licenses/`;
see [attribution](THIRD_PARTY_NOTICES.md).
