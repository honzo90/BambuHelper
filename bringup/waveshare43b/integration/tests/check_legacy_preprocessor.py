#!/usr/bin/env python3
"""Offline conditional-source regression audit; NOT a legacy firmware build.

Compares the task's modified existing source files against the recorded base.
Dependency headers are represented by include markers; config.h is separately
prepended to derive the project's feature flags. Thus changed include selection
is visible without fetching or compiling any old board dependency/toolchain.
"""
import hashlib
import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
BASE = 'd610cb4d488f6582998ed37648bf1f8a44c25a91'
OUT = REPO / 'bringup/waveshare43b/integration/test-output/legacy-preprocessor.json'
MATRIX = {
    's3_spi': {'BOARD_IS_S3': 1, 'BOARD_HAS_PSRAM': 1},
    'c3_low_ram': {'BOARD_IS_C3': 1, 'BOARD_LOW_RAM': 1},
    'cyd': {'DISPLAY_CYD': 1, 'BOARD_LOW_RAM': 1},
    'sensecap_rgb': {'BOARD_IS_SENSECAP': 1, 'DISPLAY_480x480': 1,
                     'BOARD_HAS_PSRAM': 1, 'USE_FT5X06': 1},
    'ws28c_rgb_gt911': {'BOARD_IS_WS28C': 1, 'DISPLAY_ROUND_480': 1,
                       'BOARD_HAS_PSRAM': 1, 'USE_GT911': 1,
                       'BOARD_HAS_BATTERY': 1, 'BOARD_HAS_BAT_ADC': 1},
    'axs_sprite': {'BOARD_IS_JC3248W535': 1, 'BOARD_HAS_PSRAM': 1,
                   'DISPLAY_320x480': 1},
}


def git(*args):
    return subprocess.run(['git', *args], cwd=REPO, check=True, text=True,
                          capture_output=True).stdout


def includes_as_markers(source):
    # Preserve include selection as comparison tokens without reading external
    # headers. This also avoids hiding changed layout or driver include paths.
    return re.sub(r'^\s*#\s*include\s+([^\n]+)',
                  lambda m: 'AUDIT_INCLUDE(' + json.dumps(m.group(1).strip()) + ')',
                  source, flags=re.M)


def preprocess(source, config, flags, monitor):
    prefix = '' if source == config else includes_as_markers(config) + '\n'
    defines = ['-DESP_ARDUINO_VERSION_MAJOR=2', '-DESP_IDF_VERSION_MAJOR=4']
    if monitor is not None:
        defines += [f'-DBAMBU_MONITOR_ONLY={monitor}']
    defines += [f'-D{k}={v}' for k, v in flags.items()]
    result = subprocess.run(['clang++', '-E', '-P', '-x', 'c++', *defines, '-'],
                            input=prefix + includes_as_markers(source), text=True,
                            capture_output=True, check=True)
    return result.stdout


# Preserve whitespace INSIDE quoted/raw strings; ignore only token whitespace.
TOKEN = re.compile(r'R"([^ ()\\\t\r\n]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[A-Za-z_][A-Za-z_0-9]*|[0-9]+(?:\.[0-9]+)?|[^\s]', re.S)


def tokens(source):
    return [m.group(0) for m in TOKEN.finditer(source)]


def main():
    paths = [p for p in git('diff', '--name-only', BASE).splitlines()
             if p.startswith(('include/', 'src/')) and p.endswith(('.cpp', '.h'))]
    old = {p: git('show', f'{BASE}:{p}') for p in paths}
    current = {p: (REPO / p).read_text() for p in paths}
    old_config = git('show', f'{BASE}:include/config.h')
    new_config = (REPO / 'include/config.h').read_text()
    results = []
    for board, flags in MATRIX.items():
        for monitor in (None, 0):
            for path in paths:
                before = preprocess(old[path], old_config, flags, monitor)
                after = preprocess(current[path], new_config, flags, monitor)
                identical = tokens(before) == tokens(after)
                exception = None
                if not identical and path == 'src/display_ui.cpp':
                    # Existing sanitizeRotation is identity when WS43B undefined.
                    identity = re.search(r'static uint8_t sanitizeRotation\(uint8_t r\)\s*\{\s*return r;\s*\}', after)
                    expanded = after.replace('tft.setRotation(sanitizeRotation(dispSettings.rotation));',
                                             'tft.setRotation(dispSettings.rotation);', 1)
                    if identity and tokens(before) == tokens(expanded):
                        exception = 'IDENTITY_ROTATION_WRAPPER_ONLY'
                results.append({'board': board, 'monitor_define': monitor,
                                'path': path, 'same_tokens': identical,
                                'explained_difference': exception})
    stable = all((REPO / p).read_text() == text for p, text in current.items())
    unexpected = [r for r in results if not r['same_tokens'] and not r['explained_difference']]
    report = {'base_commit': BASE, 'matrix': MATRIX, 'dependency_headers_compiled': False,
              'full_board_build': False, 'source_snapshot_stable': stable,
              'source_sha256': {p: hashlib.sha256(s.encode()).hexdigest() for p,s in current.items()},
              'comparisons': len(results), 'identical_token_comparisons': sum(r['same_tokens'] for r in results),
              'explained_identity_wrapper_comparisons': sum(bool(r['explained_difference']) for r in results),
              'unexpected_differences': unexpected, 'details': results}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('matrix','source_sha256','details')}, indent=2))
    print('Artifact:', OUT.relative_to(REPO))
    return 0 if stable and not unexpected else 1


if __name__ == '__main__':
    raise SystemExit(main())
