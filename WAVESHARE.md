# Waveshare ESP32-S3-Touch-LCD-4.3B

This branch contains the 800×480 display/touch port, native dashboard and scenes,
clock/weather views, Polish/English/German interface, and its host regression tests.
German UI support is available from `v4.0.0-beta.3`.
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
For first installation, use the [WS43B browser USB installer](https://honzo90.github.io/BambuHelper/)
with the exact ESP32-S3-Touch-LCD-4.3B board. Factory installation erases flash
and saved settings; the browser USB workflow still needs physical acceptance.
For an existing installation, prefer the panel WebUI OTA flow described in
[README](README.md#building-and-validation) and [OTA channel notes](docs/WS43B_OTA_CHANNEL.md).

## Host tests

Host tests additionally need `clang++` and Node.js on `PATH`. `prepare_build.py`
already installs ArduinoJson; for a tests-only setup use
`python3 -B prepare_test_dependencies.py` once instead.

```sh
python3 -B -m unittest discover -s bringup/waveshare43b/integration/tests -p 'test_*.py'
```

Export validation on 17 October 2026: **174 host tests passed, 1 optional test
skipped**. The sandbox initially blocked 10 MQTT loopback cases; all 10 passed
when rerun with local socket access.

**Fresh-clone build verification, 18 October 2026:** the published source commit
`5b9d48e04b5b2ffee45e6f5b44ed6d4b61d9e07a` was rebuilt successfully on macOS
without tracked source changes. The build used Arduino CLI 1.5.1, Arduino ESP32
3.3.11, esp-x32/2601, requested RGB PCLK 16 MHz and the cache64 SDK; memory and connection
diagnostics were disabled. The application was 2,865,120 bytes within the
3,145,728-byte app partition, with SHA256
`f5e0d7dfc7a1e9473c71f1b9814458e0a8c599e919ab7110f62484238ff40277`.
SDK and legacy-I2C link checks passed.

Dependencies were prepared from pinned public sources. The core and S3 SDK used
an isolated data directory; existing compiler/helper tools were reused, so this
was not a clean-machine toolchain installation test. This build was neither
flashed nor published as a binary. It is separate from the earlier hardware
candidate identified above and provides no new physical LCD/touch acceptance.

The long MQTT loopback timing test is opt-in. The private historical flash-uploader
test is excluded along with its device-specific uploader. These tests do not
prove physical LCD/touch behavior or printer-cycle acceptance.

Checked-in font and image headers are sufficient to build. Asset regeneration
requires additional Pillow/Playwright/Chromium tooling described alongside the
asset generators. Font and third-party notices are retained in `licenses/`;
see [attribution](THIRD_PARTY_NOTICES.md).
