"""Read-only verifier helpers for cache64 XIP SDK integration."""

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

PINS = {
    "lib-builder": "ee57070cc8571c488a64b8ef028684acdc6ff5e2",
    "esp-idf": "b774170ff46c393eeb5e495ea37936038d3f4f4f",
    "arduino-src": "0d7a8614b4f82d1e37874cf56281a36f8cb0b92f",
    "tinyusb-src": "53f8c53c2cbd73a91a172f1ae35e9abc00eb5075",
    "camera": "202df95d7b1dc72e9303ad78f47b8dc9f339e6a1",
}

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _require(ok, message):
    if not ok:
        raise RuntimeError(message)


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _tool(record, name, args):
    tool = record["tools"][name]
    path = Path(tool["path"])
    expected = tool["sha256"]

    _require(path.is_absolute(), f"tool path must be absolute: {path}")
    path = path.resolve()
    _require(path.exists(), f"tool does not exist: {path}")
    _require(path.is_file(), f"tool is not a file: {path}")
    _require(os.access(path, os.X_OK), f"tool is not executable: {path}")
    _require(bool(_HEX64.match(expected)), f"invalid expected tool hash: {expected}")
    _require(_digest(path) == expected, f"tool hash mismatch: {path}")

    return subprocess.check_output(
        [str(path), *map(str, args)],
        text=True,
        timeout=30,
    )


def _config(text, header=False):
    config = {}

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        if header:
            match = re.match(r"^#define\s+CONFIG_([A-Za-z0-9_]+)\s+(.+)$", line)
            if not match:
                continue
            key = f"CONFIG_{match.group(1)}"
            value = match.group(2).strip()
        else:
            match = re.match(r"^CONFIG_([A-Za-z0-9_]+)=(.*)$", line)
            if match:
                key = f"CONFIG_{match.group(1)}"
                value = match.group(2).strip()
            else:
                match = re.match(r"^#\s*CONFIG_([A-Za-z0-9_]+)\s+is not set$", line)
                if not match:
                    continue
                key = "CONFIG_" + match.group(1)
                value = "0"

        if value.lower() == "y":
            value = "1"
        elif value.lower() == "n":
            value = "0"

        if key in config and config[key] != value:
            raise RuntimeError(f"conflicting config value: {key}")

        config[key] = value

    return config


def verify_sdk_manifest(manifest_path=None, expected_sha256=None):
    if manifest_path is None:
        manifest_path = os.environ.get("WS43B_XIP_SDK_MANIFEST")
    if expected_sha256 is None:
        expected_sha256 = os.environ.get("WS43B_XIP_SDK_MANIFEST_SHA256")

    _require(manifest_path is not None, "manifest path is required")
    _require(
        isinstance(expected_sha256, str) and _HEX64.match(expected_sha256),
        f"invalid expected manifest hash: {expected_sha256}",
    )

    manifest_path = Path(manifest_path)
    _require(manifest_path.is_absolute(), f"manifest path must be absolute: {manifest_path}")
    manifest_path = manifest_path.resolve()
    _require(manifest_path.is_file(), f"manifest does not exist: {manifest_path}")

    raw = manifest_path.read_bytes()
    _require(
        hashlib.sha256(raw).hexdigest() == expected_sha256,
        "manifest hash mismatch",
    )

    try:
        m = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"malformed manifest JSON: {exc}") from exc

    _require(isinstance(m, dict), "manifest must be a JSON object")

    _require(m.get("schema_version") == 1, "invalid schema_version")
    _require(m.get("profile") == "cache64_xip", "invalid profile")
    _require(m.get("state") == "PASS", "invalid state")
    _require(m.get("target") == "esp32s3", "invalid target")
    _require(m.get("memory_type") == "qio_opi", "invalid memory_type")
    _require(m.get("app_core_version") == "3.3.11", "invalid app_core_version")
    _require(m.get("cache_line_bytes") == 64, "invalid cache_line_bytes")
    _require(m.get("pins") == PINS, "invalid pins")

    xip = m.get("xip")
    _require(isinstance(xip, dict), "invalid xip section")
    _require(xip.get("enabled") is True, "xip.enabled must be True")
    _require(xip.get("fetch_instructions") is True, "xip.fetch_instructions must be True")
    _require(xip.get("rodata") is True, "xip.rodata must be True")

    bootstrap = m.get("bootstrap")
    _require(isinstance(bootstrap, dict), "invalid bootstrap section")
    _require(bootstrap.get("psram_boot_init") is True, "bootstrap.psram_boot_init must be True")

    build = m.get("build")
    _require(isinstance(build, dict), "invalid build section")
    _require(build.get("status") == "PASS", "invalid build.status")
    _require(build.get("scope") == "full_sdk_rebuild", "invalid build.scope")

    sdk_path = m.get("sdk_path")
    _require(isinstance(sdk_path, str), "sdk_path must be a string")
    root = Path(sdk_path)
    _require(root.is_absolute(), f"sdk_path must be absolute: {sdk_path}")
    _require(not root.is_symlink(), "sdk_path root must not be a symlink")
    root = root.resolve()
    _require(root.is_dir(), f"sdk_path is not a directory: {sdk_path}")

    actual = {}
    for path in root.rglob("*"):
        _require(not path.is_symlink(), f"symlink not allowed: {path}")
        if path.is_file():
            rel = path.relative_to(root)
            parts = rel.parts
            _require(
                all(part not in ("", ".", "..") for part in parts),
                f"invalid relative path: {rel}",
            )
            actual[str(rel)] = _digest(path)

    expected_files = m.get("sdk_file_sha256")
    _require(isinstance(expected_files, dict), "sdk_file_sha256 must be a mapping")
    _require(actual == expected_files, "sdk file hash mismatch")

    for key, value in expected_files.items():
        _require(isinstance(key, str), f"invalid manifest key: {key}")
        _require(
            isinstance(value, str) and _HEX64.match(value),
            f"invalid manifest hash for {key}",
        )
        parts = key.split("/")
        _require(
            key and all(part not in ("", ".", "..") for part in parts),
            f"invalid manifest path key: {key}",
        )

    required_dirs = ["include", "lib", "ld"]
    required_files = [
        "sdkconfig",
        "dependencies.lock",
        "flags/defines",
        "flags/includes",
        "flags/c_flags",
        "flags/cpp_flags",
        "flags/S_flags",
        "flags/ld_flags",
        "flags/ld_scripts",
        "flags/ld_libs",
        "bin/bootloader_qio_80m.elf",
        "qio_opi/include/sdkconfig.h",
        "qio_opi/sections.ld",
        "qio_opi/libesp_system.a",
        "qio_opi/libspi_flash.a",
        "qio_opi/libesp_psram.a",
        "qio_opi/libfreertos.a",
        "qio_opi/libbootloader_support.a",
        "qio_opi/libesp_hw_support.a",
    ]

    for directory in required_dirs:
        _require((root / directory).is_dir(), f"missing required directory: {directory}")
    for filename in required_files:
        _require((root / filename).is_file(), f"missing required file: {filename}")

    _require(
        _digest(root / "sdkconfig") == build.get("configuration_sha256"),
        "sdkconfig hash mismatch",
    )
    _require(
        _digest(root / "dependencies.lock") == build.get("dependencies_lock_sha256"),
        "dependencies.lock hash mismatch",
    )

    sdkconfig_text = (root / "sdkconfig").read_text()
    header_text = (root / "qio_opi/include/sdkconfig.h").read_text()
    configs = (_config(sdkconfig_text), _config(header_text, True))

    enabled = [
        "CONFIG_SPIRAM_XIP_FROM_PSRAM",
        "CONFIG_SPIRAM_FETCH_INSTRUCTIONS",
        "CONFIG_SPIRAM_RODATA",
        "CONFIG_SPIRAM_BOOT_INIT",
        "CONFIG_SPIRAM_MODE_OCT",
        "CONFIG_SPIRAM_SPEED_80M",
        "CONFIG_ESP32S3_DATA_CACHE_LINE_64B",
        "CONFIG_LCD_RGB_RESTART_IN_VSYNC",
    ]
    for config in configs:
        for key in enabled:
            _require(config.get(key) == "1", f"required config not enabled: {key}")
        _require(config.get("CONFIG_ESP32S3_DATA_CACHE_LINE_SIZE") == "64",
                "cache line size must be 64")

        disabled = [
            "CONFIG_ESP32S3_DATA_CACHE_LINE_16B",
            "CONFIG_ESP32S3_DATA_CACHE_LINE_32B",
            "CONFIG_LCD_RGB_ISR_IRAM_SAFE",
            "CONFIG_SPI_FLASH_SHARE_SPI1_BUS",
            "CONFIG_SPI_FLASH_DISABLE_SCHEDULER_IN_SUSPEND",
        ]
        for key in disabled:
            _require(config.get(key, "0") == "0", f"forbidden config enabled: {key}")

    archive_result = _archive_checks(m)

    return {
        **m,
        "manifest_sha256": expected_sha256,
        "verification": {
            "passed": True,
            "files": len(actual),
            "archive_checks": archive_result,
        },
    }


def _archive_checks(record):
    sdk = Path(record["sdk_path"]) / "qio_opi"

    archives = {
        "libesp_system.a": ("cpu_start.c.obj",),
        "libspi_flash.a": ("spi_flash_os_func_app.c.obj",),
        "libesp_psram.a": ("esp_psram.c.obj", "mmu_psram_flash.c.obj"),
    }

    checked_members = {}
    for archive_name, members in archives.items():
        archive_path = sdk / archive_name
        listing = _tool(record, "ar", ["t", archive_path])
        listed = {line.strip() for line in listing.splitlines() if line.strip()}
        for member in members:
            _require(member in listed, f"missing archive member: {archive_name}:{member}")
            checked_members[f"{archive_name}:{member}"] = True

    nm_outputs = {}
    for archive_name in ("libesp_psram.a", "libspi_flash.a"):
        nm_outputs[archive_name] = _tool(record, "nm", ["-A", "-g", sdk / archive_name])

    psram_lines = nm_outputs["libesp_psram.a"].splitlines()
    spi_lines = nm_outputs["libspi_flash.a"].splitlines()

    def parse_nm_line(line):
        # Expected shape: /ABS/archive.a:member.obj:ADDR TYPE SYMBOL
        # or /ABS/archive.a:member.obj:ADDR U SYMBOL.
        if ":" not in line:
            return None
        archive_part, rest = line.split(":", 1)
        if ":" not in rest:
            return None
        member_part, symbol_part = rest.split(":", 1)
        tokens = symbol_part.split()
        if len(tokens) < 2:
            return None
        symbol = tokens[-1]
        typ = tokens[-2]
        return archive_part, member_part, typ, symbol

    mmu_defined = {}
    for line in psram_lines:
        parsed = parse_nm_line(line)
        if not parsed:
            continue
        archive_part, member_part, typ, symbol = parsed
        if archive_part != str(sdk / "libesp_psram.a"):
            continue
        if member_part != "mmu_psram_flash.c.obj":
            continue
        if symbol in ("mmu_config_psram_text_segment", "mmu_config_psram_rodata_segment"):
            if typ in ("T", "t"):
                mmu_defined[symbol] = True

    _require(
        mmu_defined.get("mmu_config_psram_text_segment") is True,
        "mmu_psram_flash.c.obj must define T/t mmu_config_psram_text_segment",
    )
    _require(
        mmu_defined.get("mmu_config_psram_rodata_segment") is True,
        "mmu_psram_flash.c.obj must define T/t mmu_config_psram_rodata_segment",
    )

    spi_mutex = {}
    forbidden_spi_tokens = {
        "cache_disable",
        "cache_enable",
        "spi_flash_disable_interrupts_caches_and_other_cpu",
        "spi_flash_enable_interrupts_caches_and_other_cpu",
    }

    for line in spi_lines:
        parsed = parse_nm_line(line)
        if not parsed:
            continue
        archive_part, member_part, typ, symbol = parsed
        if archive_part != str(sdk / "libspi_flash.a"):
            continue
        if member_part == "spi_flash_os_func_app.c.obj":
            if symbol in forbidden_spi_tokens:
                _require(
                    False,
                    f"spi_flash_os_func_app.c.obj must not reference forbidden token: {symbol}",
                )
            if typ == "U" and symbol in ("_lock_acquire", "_lock_release"):
                spi_mutex[symbol] = True

    _require(
        spi_mutex.get("_lock_acquire") is True,
        "spi_flash_os_func_app.c.obj must have U _lock_acquire",
    )
    _require(
        spi_mutex.get("_lock_release") is True,
        "spi_flash_os_func_app.c.obj must have U _lock_release",
    )

    return {
        "passed": True,
        "checked_members": checked_members,
        "mutex_checks": {
            "spi_flash_os_func_app.c.obj:_lock_acquire": True,
            "spi_flash_os_func_app.c.obj:_lock_release": True,
        },
        "xip_checks": {
            "mmu_psram_flash.c.obj:mmu_config_psram_text_segment": True,
            "mmu_psram_flash.c.obj:mmu_config_psram_rodata_segment": True,
        },
    }


def verify_link_map(record, map_path, elf_path):
    sdk = Path(record["sdk_path"]) / "qio_opi"
    map_text = Path(map_path).read_text()

    header = "Linker script and memory map"
    header_pos = map_text.find(header)
    if header_pos < 0:
        return {
            "cpu_start.c.obj": False,
            "esp_psram.c.obj": False,
            "mmu_psram_flash.c.obj": False,
            "spi_flash_os_func_app.c.obj": False,
            "old_sdk_absent": True,
            "final_symbols": False,
            "iram_placement": False,
            "passed": False,
        }

    cross_pos = map_text.find("Cross Reference Table", header_pos)
    used_text = map_text[header_pos:cross_pos if cross_pos >= 0 else len(map_text)]

    required = {
        "cpu_start.c.obj": sdk / "libesp_system.a",
        "esp_psram.c.obj": sdk / "libesp_psram.a",
        "mmu_psram_flash.c.obj": sdk / "libesp_psram.a",
        "spi_flash_os_func_app.c.obj": sdk / "libspi_flash.a",
    }

    member_present = {}
    for member, archive in required.items():
        needle = str(archive) + "(" + member + ")"
        member_present[member] = needle in used_text

    own_sdk_prefix = str(Path(record["sdk_path"])) + "/"
    scan_text = used_text.replace(own_sdk_prefix, "")
    old_sdk_absent = ("/sdk-cache64/" not in scan_text) and ("/esp32s3-libs/" not in scan_text)

    nm_output = _tool(record, "nm", ["-S", "-C", "--defined-only", elf_path])

    definitions = {}
    for line in nm_output.splitlines():
        m = re.fullmatch(r"\s*([0-9a-fA-F]+)\s+(?:([0-9a-fA-F]+)\s+)?([A-Za-z])\s+([^\s]+)\s*", line)
        if not m:
            continue
        addr = m.group(1)
        size = int(m.group(2), 16) if m.group(2) else 0
        typ = m.group(3)
        symbol = m.group(4)
        definitions.setdefault(symbol, []).append((addr, size, typ))

    def one_defined(name):
        entries = definitions.get(name, [])
        return len(entries) == 1 and entries[0][2] in ("T", "t")

    def one_boundary(name):
        entries = definitions.get(name, [])
        return len(entries) == 1 and entries[0][2] in ("B", "A", "T", "t")

    required_final = [
        "esp_psram_init",
        "esp_flash_app_enable_os_functions",
        "mmu_config_psram_text_segment",
        "mmu_config_psram_rodata_segment",
    ]
    final_symbols = all(one_defined(name) for name in required_final)

    iram_names = ["_iram_start", "_iram_end", "_iram_text_start", "_iram_text_end"]
    iram_defs = {name: definitions.get(name, []) for name in iram_names}
    iram_single = all(one_boundary(name) for name in iram_names)

    iram_placement = False
    if iram_single and final_symbols:
        iram_start = int(iram_defs["_iram_start"][0][0], 16)
        iram_end = int(iram_defs["_iram_end"][0][0], 16)
        text_start = int(iram_defs["_iram_text_start"][0][0], 16)
        text_end = int(iram_defs["_iram_text_end"][0][0], 16)

        # Pinned ESP32S3 ICACHE16KB memory.ld IRAM bounds used by this profile.
        if 0x40374000 <= iram_start <= text_start < text_end <= iram_end <= 0x403CB700:
            mmu_ok = True
            for name in ("mmu_config_psram_text_segment", "mmu_config_psram_rodata_segment"):
                addr, size, typ = definitions[name][0]
                addr = int(addr, 16)
                if size <= 0 or addr < text_start or addr + size > text_end:
                    mmu_ok = False
                    break
            iram_placement = mmu_ok

    gate = {
        "cpu_start.c.obj": member_present["cpu_start.c.obj"],
        "esp_psram.c.obj": member_present["esp_psram.c.obj"],
        "mmu_psram_flash.c.obj": member_present["mmu_psram_flash.c.obj"],
        "spi_flash_os_func_app.c.obj": member_present["spi_flash_os_func_app.c.obj"],
        "old_sdk_absent": old_sdk_absent,
        "final_symbols": final_symbols,
        "iram_placement": iram_placement,
    }

    gate["passed"] = all(gate.values())
    return gate
