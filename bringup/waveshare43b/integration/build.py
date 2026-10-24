#!/usr/bin/env python3
"""Build only: stage existing BambuHelper with the exact tested 4.3B toolchain.

No upload, USB, network fetch or printer access. Dependencies must already be
downloaded to the ignored vendor directory; archives and source hashes are
checked. All other boards retain their existing PlatformIO build configuration.
"""
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys
import tarfile
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
VENDOR = HERE / 'vendor'
STAGE = HERE / 'staging' / 'BambuHelper43B'
BUILD = HERE / 'build'
REFERENCE = ROOT.parent / 'waveshare-4.3b-reference'
REF_COMMIT = '04cc7ee4a85d796491084fc3baae3589b4f812cf'
LIBRARIES = {
    'LovyanGFX-1.2.26': ('LovyanGFX-1.2.26.tar.gz', '230e516f1eb3025e6faadf16cc7bdbf1ad8efd37359e7d7040115d19da1c12a7', '1.2.26'),
    'ArduinoJson-7.4.3': ('ArduinoJson-v7.4.3.tar.gz', 'a2a8a277fc3cd0404499199bf1468682ea3688f354be0eaf6af8648366911257', '7.4.3'),
    'pubsubclient-2.8': ('PubSubClient-2.8.tar.gz', 'f94bdfdc62bddaf89fcb680986ee3691369660f2fa7751d9414370c6d1c83b3d', '2.8'),
}

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def verify_extracted(path, archive):
    """Reject local dependency edits, including additional source files."""
    expected = {}
    with tarfile.open(archive) as package:
        for member in package.getmembers():
            if member.isfile():
                relative = Path(*Path(member.name).parts[1:])
                expected[str(relative)] = hashlib.sha256(package.extractfile(member).read()).hexdigest()
    actual = {str(p.relative_to(path)): digest(p) for p in path.rglob('*') if p.is_file()}
    if actual != expected:
        raise SystemExit(f'Dependency sources differ from pinned archive: {path.name}')

def git(*args):
    return subprocess.check_output(['git', '-C', str(REFERENCE), *args], text=True).strip()

def inputs():
    paths = []
    for directory in ['src', 'include', 'lib/ImprovWiFi/src']:
        paths += [p for p in (ROOT / directory).rglob('*') if p.is_file()]
    paths += [ROOT / 'boards/ws_lcd_43b.ini', ROOT / 'web/app.css', ROOT / 'web/app.js',
              ROOT / 'tools/gen_web_assets.py', HERE / 'partitions.csv', Path(__file__),
              HERE / 'cache64_sdk.py', HERE / 'fixture_profile.py', HERE / 'localize_web.py', HERE / 'locale/pl.json', HERE / 'locale/language_picker.html', HERE / 'locale/monitor_en.json', HERE / 'locale/de.json', HERE / 'locale/monitor_de.json']
    # Generated headers are already covered by include/. Record their source
    # artwork, fonts and pipeline provenance too, without transient raster/cache
    # outputs or the separate design-preview working directory.
    paths += [HERE / 'generate_dashboard_fonts.py', HERE / 'generate_modern_fonts.py',
              ROOT / 'fonts/Inter-Regular.ttf', ROOT / 'fonts/Inter-Bold.ttf']
    visual = HERE / 'visual-v2'
    paths += [visual / name for name in ('generate.py', 'rasterize.cjs', 'assets.json',
                                        'rasterizer.json', 'manifest.json', 'README.md',
                                        'scene-components-prompt.txt')]
    paths += [p for p in (visual / 'raw').rglob('*')
              if p.is_file() and p.suffix.lower() in ('.svg', '.png')]
    paths += [p for p in (HERE / 'patches').glob('*.patch')]
    paths += list((HERE / 'cache64-templates').glob('*.json'))
    return {str(p.relative_to(ROOT)): digest(p) for p in sorted(set(paths))}

def check_i2c_link(build):
    """Regression gate for the observed pre-setup IDF I2C conflict abort."""
    from cache64_sdk import TOOL_DIR
    nm = TOOL_DIR / 'bin/xtensa-esp-elf-nm'
    symbols = subprocess.check_output([str(nm), '-C', '--defined-only',
                                      str(build / 'BambuHelper43B.ino.elf')], text=True)
    linkmap = (build / 'BambuHelper43B.ino.map').read_text()
    modern = bool(re.search(r'\b(i2c_acquire_bus_handle|i2c_new_master_bus)\b', symbols))
    modern_objects = 'libesp_driver_i2c.a(' in linkmap
    legacy = bool(re.search(r'\bi2c_driver_install\b', symbols))
    conflict_guard = bool(re.search(r'\bcheck_i2c_driver_conflict\b', symbols))
    passed = legacy and conflict_guard and not modern and not modern_objects
    return {'passed': passed, 'legacy_driver_present': legacy,
            'conflict_guard_retained': conflict_guard,
            'modern_driver_symbols_present': modern,
            'modern_driver_archive_members_present': modern_objects}

class AssetEnv:
    def __init__(self, project=ROOT):
        self.project = project
    def subst(self, key):
        return {'$PROJECT_DIR': str(self.project), '$BUILD_DIR': str(BUILD)}[key]
    def Append(self, **_kwargs):
        pass

def main():
    if len(sys.argv) != 1:
        raise SystemExit('Build-only script takes no arguments; upload is intentionally unsupported.')
    fixture_ip = os.environ.get('WS43B_FIXTURE_IP', '')
    if fixture_ip:
        from fixture_profile import validate_ip
        fixture_ip = validate_ip(fixture_ip)
        if os.environ.get('WS43B_MEMORY_DIAG') != '1':
            raise SystemExit('Synthetic fixture requires memory diagnostics enabled.')
    connect_diag = os.environ.get('WS43B_CONNECT_DIAG', '0')
    if connect_diag not in ('0', '1'):
        raise SystemExit('WS43B_CONNECT_DIAG must be 0 or 1.')
    memory_diag = os.environ.get('WS43B_MEMORY_DIAG', '0')
    if memory_diag not in ('0', '1'):
        raise SystemExit('WS43B_MEMORY_DIAG must be 0 or 1.')
    pclk_hz = os.environ.get('WS43B_RGB_PCLK_HZ', '16000000')
    if pclk_hz not in ('12000000', '14000000', '16000000'):
        raise SystemExit('WS43B_RGB_PCLK_HZ must be 12000000, 14000000 or 16000000.')
    if git('rev-parse', 'HEAD') != REF_COMMIT or git('status', '--porcelain'):
        raise SystemExit('Manufacturer reference must be clean at the recorded commit.')
    profile = configparser.ConfigParser(interpolation=None)
    profile.read(ROOT / 'boards/ws_lcd_43b.ini')
    cfg = profile['ws_lcd_43b_arduino']
    from cache64_sdk import ARDUINO, TOOL_DIR
    core = ARDUINO / 'packages/esp32/hardware/esp32' / cfg['core_version']
    if not (core / 'platform.txt').is_file():
        raise SystemExit('The hardware-validated Arduino ESP32 3.3.11 core is required.')
    sdk_record = None
    sdk_manifest_hash = None
    sdk_profile = cfg.get('sdk_profile', 'stock')
    if sdk_profile == 'cache64':
        from cache64_sdk import verify_sdk_manifest
        sdk_record = verify_sdk_manifest()
        sdk_manifest_hash = digest(HERE / 'sdk-cache64-manifest.json')
    elif sdk_profile != 'stock':
        raise SystemExit('Unknown private SDK profile; no fallback is allowed.')
    libpaths = []
    for folder, (archive, sha, version) in LIBRARIES.items():
        path = VENDOR / folder
        if not (VENDOR / archive).is_file() or digest(VENDOR / archive) != sha:
            raise SystemExit(f'Missing or changed dependency archive: {archive}')
        if f'version={version}' not in (path / 'library.properties').read_text().splitlines():
            raise SystemExit(f'Wrong library version: {folder}')
        verify_extracted(path, VENDOR / archive)
        if folder == 'LovyanGFX-1.2.26':
            # Preserve pristine, hash-verified vendor sources. Apply the narrow
            # board-specific compatibility patch only to our generated copy.
            staged_lib = HERE / 'staging' / 'LovyanGFX'
            if staged_lib.exists():
                shutil.rmtree(staged_lib)
            shutil.copytree(path, staged_lib)
            patch = HERE / 'patches/lovyangfx-1.2.26-ws43b-bsp-i2c.patch'
            subprocess.run(['patch', '-p1', '-F', '0', '-t', '-i', str(patch)],
                           cwd=staged_lib, check=True)
            path = staged_lib
        libpaths.append(path)
    vendorlibs = REFERENCE / 'examples/Arduino/libraries'
    for name, version in [('ESP32_Display_Panel', '1.0.0'), ('ESP32_IO_Expander', '1.0.1'), ('esp-lib-utils', '0.1.2')]:
        path = vendorlibs / name
        if f'version={version}' not in (path / 'library.properties').read_text().splitlines():
            raise SystemExit(f'Wrong manufacturer library: {name}')
        libpaths.append(path)
    BUILD.mkdir(parents=True, exist_ok=True)
    STAGE.mkdir(parents=True, exist_ok=True)
    staged_src = STAGE / 'src'
    # Remove only our generated staging source; never touch the repository src.
    if staged_src.exists():
        shutil.rmtree(staged_src)
    staged_src.mkdir()
    for source_dir in ['src', 'include']:
        for source in (ROOT / source_dir).rglob('*'):
            if source.is_file():
                target = staged_src / source.relative_to(ROOT / source_dir)
                if target.exists():
                    raise SystemExit(f'Staging filename collision: {target.name}')
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
    # Arduino's dependency discovery expects library.properties; the upstream
    # project vendors Improv as a PlatformIO library.json. Supply metadata only
    # in staging and keep its source byte-identical to the repository copy.
    improv = HERE / 'staging' / 'ImprovWiFi'
    shutil.copytree(ROOT / 'lib/ImprovWiFi/src', improv / 'src', dirs_exist_ok=True)
    (improv / 'library.properties').write_text(
        'name=ImprovWiFi\nversion=0.0.2\nauthor=Jonathas Barbosa\n'
        'maintainer=Jonathas Barbosa\nsentence=Vendored Improv provisioning\n'
        'paragraph=Unmodified BambuHelper vendored Improv sources.\n'
        'category=Communication\narchitectures=esp32\n'
        'url=https://github.com/jnthas/Improv-WiFi-Library\n')
    libpaths.append(improv)
    (STAGE / 'BambuHelper43B.ino').write_text('// setup() and loop() entry points are compiled from src/main.cpp.\n')
    shutil.copyfile(HERE / 'partitions.csv', STAGE / 'partitions.csv')
    from localize_web import stage
    import pygments
    stage(staged_src, ROOT / "web", STAGE / "web")
    asset_env = AssetEnv(STAGE)
    runpy.run_path(str(ROOT / 'tools/gen_web_assets.py'), init_globals={'env': asset_env, 'Import': lambda _name: None})
    shutil.copyfile(BUILD / 'generated/web_assets_gz.h', staged_src / 'web_assets_gz.h')
    fixture_record = None
    if fixture_ip:
        from fixture_profile import apply
        fixture_record = apply(staged_src, fixture_ip)
    sources = inputs()
    library_hashes = {str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p.relative_to(REFERENCE)): digest(p)
                      for lib in libpaths for p in lib.rglob('*') if p.is_file() and '.git' not in p.parts}
    # Arduino CLI passes these tokens directly, without a shell escape layer.
    # Keep C string quotes in -D values literal; backslashes would reach GCC.
    flags = ' '.join(line.strip() for line in cfg['flags'].splitlines() if line.strip())
    if 'WS43B_RGB_PCLK_HZ' in flags:
        raise SystemExit('PCLK must be selected only through WS43B_RGB_PCLK_HZ environment.')
    if 'WS43B_MEMORY_DIAG' in flags:
        raise SystemExit('Memory diagnostics must be selected through WS43B_MEMORY_DIAG environment.')
    if 'WS43B_CONNECT_DIAG' in flags:
        raise SystemExit('Connection diagnostics must be selected through the environment.')
    flags += ' -DWS43B_CONNECT_DIAG=' + connect_diag
    flags += ' -DWS43B_RGB_PCLK_HZ=' + pclk_hz + ' -DWS43B_MEMORY_DIAG=' + memory_diag
    # All project headers are staged beside their source files and use quoted
    # includes. Do not pass the spaced workspace path through extra_flags;
    # Arduino handles library include paths itself.
    command = ['arduino-cli', 'compile', '--fqbn', cfg['fqbn'], '--build-path', str(BUILD),
               '--build-property', f'compiler.cpp.extra_flags={flags}',
               '--build-property', f'compiler.c.extra_flags={flags}',
               '--build-property', 'upload.maximum_size=' + cfg['app_limit']]
    if sdk_record:
        command += ['--build-property', 'compiler.sdk.path=' + sdk_record['sdk_path']]
    for path in libpaths:
        command += ['--library', str(path)]
    command += [str(STAGE)]
    env = os.environ.copy()
    env['ARDUINO_DIRECTORIES_DATA'] = str(ARDUINO)
    env['ARDUINO_BUILD_CACHE_PATH'] = str(BUILD / 'cache')
    started = time.strftime('%Y-%m-%dT%H:%M:%S%z')
    # Arduino CLI can recreate build-path after a recipe/library change.
    # Keep the open log outside that directory so diagnostics survive it.
    logpath = HERE / 'test-output' / 'compile.log'
    logpath.parent.mkdir(parents=True, exist_ok=True)
    print(f'Building BambuHelper ws_lcd_43b (no USB). Log: {logpath}', flush=True)
    with logpath.open('w') as log:
        result = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT)
    summary = logpath.read_text(errors='replace').splitlines()
    print('\n'.join(summary[-50:]))
    unchanged = sources == inputs()
    sdk_unchanged = True
    if sdk_record:
        sdk_unchanged = (sdk_record == verify_sdk_manifest() and
                         sdk_manifest_hash == digest(HERE / 'sdk-cache64-manifest.json'))
    sdk_link_check = None
    if result.returncode == 0 and sdk_record:
        linkmap = (BUILD / 'BambuHelper43B.ino.map').read_text()
        sdk_dir = Path(sdk_record['sdk_path']) / 'qio_opi'
        sdk_link_check = {
            'cpu_start_from_private_sdk': str(sdk_dir / 'libesp_system.a') + '(cpu_start.c.obj)' in linkmap,
            'cache_utils_from_private_sdk': str(sdk_dir / 'libspi_flash.a') + '(cache_utils.c.obj)' in linkmap,
        }
        nm = TOOL_DIR / 'bin/xtensa-esp-elf-nm'
        symbols = subprocess.check_output([str(nm), '-C', '--defined-only',
                                          str(BUILD / 'BambuHelper43B.ino.elf')], text=True)
        sdk_link_check['unused_cache_mode_and_wrap_discarded'] = not re.search(
            r'\b(esp_config_data_cache_mode|esp_enable_cache_wrap)\b', symbols)
        sdk_link_check['passed'] = all(sdk_link_check.values())
    i2c_check = check_i2c_link(BUILD) if result.returncode == 0 else None
    if i2c_check is not None:
        print('I2C link regression check: ' + json.dumps(i2c_check))
    record = {'started': started, 'profile': 'boards/ws_lcd_43b.ini', 'compile_exit_code': result.returncode,
              'requested_pclk_hz': int(pclk_hz), 'memory_diagnostics': memory_diag == '1', 'connection_diagnostics': connect_diag == '1', 'fixture': fixture_record,
              'inputs_unchanged_during_build': unchanged, 'fqbn': cfg['fqbn'], 'flags': flags,
              'core_version': cfg['core_version'], 'manufacturer_commit': REF_COMMIT,
              'source_sha256': sources, 'dependency_file_sha256': library_hashes,
              'i2c_link_check': i2c_check,
              'web_localization': {'languages': ['pl', 'en', 'de'], 'pygments': pygments.__version__},
              'compile_log_sha256': digest(logpath), 'artifacts': {}, 'uploaded': False}
    record['private_sdk'] = ({'profile': sdk_profile, 'sdk_path': sdk_record['sdk_path'],
                              'manifest_sha256': sdk_manifest_hash, 'inputs_unchanged': sdk_unchanged,
                              'link_check': sdk_link_check} if sdk_record else None)
    if result.returncode == 0 and unchanged and sdk_unchanged and i2c_check['passed'] and (not sdk_link_check or sdk_link_check['passed']):
        for name in ['BambuHelper43B.ino.bin', 'BambuHelper43B.ino.bootloader.bin', 'BambuHelper43B.ino.partitions.bin', 'boot_app0.bin']:
            artifact = BUILD / name
            if artifact.exists():
                record['artifacts'][name] = {'bytes': artifact.stat().st_size, 'sha256': digest(artifact)}
        if (BUILD / 'BambuHelper43B.ino.bin').stat().st_size > int(cfg['app_limit']):
            raise SystemExit('Application does not fit the preserved diagnostic partition.')
    (BUILD / 'manifest.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    if not unchanged:
        raise SystemExit('Sources changed during compilation; this image is not eligible for flashing.')
    if not sdk_unchanged or (sdk_link_check and not sdk_link_check['passed']):
        raise SystemExit('Private SDK input/link regression gate failed; do not flash this image.')
    if result.returncode == 0 and not i2c_check['passed']:
        raise SystemExit('I2C link regression gate failed; do not flash this image.')
    raise SystemExit(result.returncode)

if __name__ == '__main__':
    main()
