#!/usr/bin/env python3
"""Build an isolated, tightly audited IDF 5.5.5 cache-line experiment.

No downloads, package updates, USB access, or firmware upload. All unchanged SDK
files and archive members are preserved byte for byte. Rebuilds only two pinned
translation units, first as a 32-byte control, then with a 64-byte cache line.
The control must reproduce all loadable sections, Xtensa linker metadata,
relocations and public/undefined symbols of the installed official objects.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import zipfile

HERE = Path(__file__).resolve().parent
INPUTS = HERE / 'cache64-inputs'
WORK = HERE / 'cache64-work'
OUTPUT = HERE / 'sdk-cache64'
MANIFEST = HERE / 'sdk-cache64-manifest.json'
def arduino_data():
    override=os.environ.get('WS43B_ARDUINO_DATA')
    if override:return Path(override).expanduser().resolve()
    config=json.loads(subprocess.check_output(['arduino-cli','config','dump','--format','json'],text=True)).get('config',{})
    directory=config.get('directories',{}).get('data')
    if directory:return Path(directory).expanduser().resolve()
    if sys.platform=='darwin':return Path.home()/'Library/Arduino15'
    if sys.platform.startswith('linux'):return Path.home()/'.arduino15'
    raise RuntimeError('Set WS43B_ARDUINO_DATA; this host has not been validated')
ARDUINO = arduino_data()
SDK = ARDUINO / 'packages/esp32/tools/esp32s3-libs/3.3.11'
TOOL_DIR = ARDUINO / 'packages/esp32/tools/esp-x32/2601'
GCC = TOOL_DIR / 'bin/xtensa-esp-elf-gcc'
AR = TOOL_DIR / 'bin/xtensa-esp-elf-ar'
OBJDUMP = TOOL_DIR / 'bin/xtensa-esp-elf-objdump'
ORIGINAL_ZIP = ARDUINO / 'staging/packages/esp32s3-libs-3.3.11.zip'
ZIP_SHA = 'fec76794708694120c6ec803cdbfc7dcd36286ea22b7d38097b7909bbd19f7b5'
IDF_COMMIT = 'b774170ff46c393eeb5e495ea37936038d3f4f4f'
BOOTSTRAP = INPUTS
TEMPLATES = HERE / 'cache64-templates'
SOURCES = {
    'components/esp_system/port/cpu_start.c': 'b90e0fac2c1e9a9eba5a37e419bf5aa4a81cc2fc5bf347b1c7c8a05b98ae717e',
    'components/spi_flash/cache_utils.c': '15bb5f74f4deb8dbe24ba18eadf90e417592f3d2e40988c8bf0c093144e500fe',
    'components/esp_system/port/include/private/esp_private/cache_err_int.h': '69e16e3058f1dce45cc5648e20d72c307288fd9f1fa4a29563c42f1ea05de907',
    'components/esp_system/port/include/esp_clk_internal.h': 'dd6a9ed1a41247bc5e46b9ba2f55ba0cb0b49f7e4e1ce7f3eb4f27f0d1e49535',
    'components/esp_system/port/include/private/esp_private/image_process.h': '69173cef4dd389a4898e3a2a233c3ef35e442fcddc241b942ea630e7f01e93d8',
}
COMMAND_SHA = {'cpu_start.c.obj': 'd84e1ed16b820dc7e926c8f9a1412aa8ff16cc77755ae68177084e7a5004292c', 'cache_utils.c.obj': '7410f414ba296b36e72a423efbd19072b4fd775d4f1cc5692609f4e7a00c55cc'}

OBJECTS = {
    'cpu_start.c.obj': 'qio_opi/libesp_system.a',
    'cache_utils.c.obj': 'qio_opi/libspi_flash.a',
}
MODIFIED_FILES = sorted(['qio_opi/include/sdkconfig.h', *OBJECTS.values()])


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree_hashes(root):
    paths = sorted(root.rglob('*'))
    require(not any(p.is_symlink() for p in paths), f'Symlink in {root}')
    return {str(p.relative_to(root)): digest(p) for p in paths if p.is_file()}


def run(argv, **kwargs):
    return subprocess.check_output([str(a) for a in argv], **kwargs)


def archive_members(path):
    names = run([AR, 't', path], text=True).splitlines()
    require(len(names) == len(set(names)), f'Duplicate archive members: {path}')
    return {name: run([AR, 'p', path, name]) for name in names}


class Elf32:
    """Small strict ELF32 LE parser: ignores only non-loadable debug content."""
    def __init__(self, data):
        self.data = data
        require(data[:7] == b'\x7fELF\x01\x01\x01', 'Not ELF32 little endian')
        header = struct.unpack_from('<16sHHIIIIIHHHHHH', data)
        self.identity = (header[1], header[2], header[3], header[7])
        require(header[1] == 1 and header[2] == 94, 'Expected Xtensa ET_REL')
        shoff, shsize, shnum, shstrndx = header[6], header[11], header[12], header[13]
        require(shsize == 40 and 0 < shnum < 65535, 'Unsupported section table')
        headers = [struct.unpack_from('<IIIIIIIIII', data, shoff + shsize * i)
                   for i in range(shnum)]
        strings = headers[shstrndx]
        names = data[strings[4]:strings[4] + strings[5]]
        self.sections = []
        for i, h in enumerate(headers):
            name = self.string(names, h[0])
            body = b'' if h[1] == 8 else data[h[4]:h[4] + h[5]]
            require(h[1] == 8 or len(body) == h[5], 'Truncated ELF section')
            self.sections.append(dict(index=i, name=name, type=h[1], flags=h[2],
                                      size=h[5], link=h[6], info=h[7], align=h[8],
                                      entsize=h[9], body=body))
        self.byname = {s['name']: s for s in self.sections}
        require(len(self.byname) == len(self.sections), 'Duplicate ELF section names')
        self.symtabs = {}
        for section in self.sections:
            if section['type'] != 2:
                continue
            require(section['entsize'] == 16, 'Unexpected ELF symbol size')
            strings = self.sections[section['link']]['body']
            symbols = []
            for offset in range(0, len(section['body']), 16):
                name, value, size, info, other, ndx = struct.unpack_from(
                    '<IIIBBH', section['body'], offset)
                symbols.append((self.string(strings, name), value, size, info,
                                other, self.sections[ndx]['name'] if ndx < shnum else ndx))
            self.symtabs[section['index']] = symbols

    @staticmethod
    def string(data, offset):
        end = data.find(b'\0', offset)
        require(0 <= offset < len(data) and end >= offset, 'Invalid ELF string')
        return data[offset:end].decode('utf-8')

    @staticmethod
    def relevant(section):
        return bool(section['flags'] & 2) or section['name'].startswith('.xt.')

    def section_content(self):
        return {s['name']: (s['type'], s['flags'], s['size'], s['align'], s['body'])
                for s in self.sections if self.relevant(s)}

    def relocations(self):
        result = {}
        for s in self.sections:
            if s['type'] not in (4, 9):
                continue
            target = self.sections[s['info']]
            if not self.relevant(target):
                continue
            fmt = '<IIi' if s['type'] == 4 else '<II'
            size = struct.calcsize(fmt)
            require(s['entsize'] == size, 'Unexpected relocation size')
            entries = []
            symbols = self.symtabs[s['link']]
            for off in range(0, len(s['body']), size):
                vals = struct.unpack_from(fmt, s['body'], off)
                location, info = vals[:2]
                entries.append((location, info & 255, symbols[info >> 8],
                                vals[2] if len(vals) == 3 else None))
            result[target['name']] = entries
        return result

    def public_symbols(self):
        return sorted(s for table in self.symtabs.values() for s in table
                      if (s[3] >> 4) != 0)


def object_gate(original, candidate, allowed_changes=None):
    a, b = Elf32(original), Elf32(candidate)
    require(a.identity == b.identity, 'ELF machine/flags changed')
    before, after = a.section_content(), b.section_content()
    require(before.keys() == after.keys(), 'Loadable/linker sections changed')
    changes = {}
    for name in before:
        left, right = before[name], after[name]
        require(left[:4] == right[:4], f'Section shape changed: {name}')
        if left[4] != right[4]:
            changes[name] = [[i, x, y] for i, (x, y) in enumerate(zip(left[4], right[4])) if x != y]
    require(changes == (allowed_changes or {}), f'Unexpected section bytes: {changes}')
    require(a.relocations() == b.relocations(), 'Loadable/linker relocations changed')
    require(a.public_symbols() == b.public_symbols(), 'Public/undefined symbol ABI changed')
    return dict(passed=True, allocated_sections=sum(bool(s['flags'] & 2) for s in a.sections),
                linker_metadata=[s['name'] for s in a.sections if s['name'].startswith('.xt.')],
                relocation_entries=sum(map(len, a.relocations().values())),
                public_symbols=len(a.public_symbols()), exact_byte_changes=changes)


def bootstrap_inputs(origin):
    INPUTS.mkdir(exist_ok=True)
    wanted = {f'esp-idf/{p}': h for p, h in SOURCES.items()}
    for name,sha in COMMAND_SHA.items():
        require(digest(TEMPLATES / (name+'.command.json'))==sha,'Compiler template changed')
    for relative, expected in wanted.items():
        target = INPUTS / relative
        if target.exists():
            require(digest(target) == expected, f'Changed preserved input: {target}')
            continue
        source = origin / relative
        require(source.is_file() and digest(source) == expected, f'Missing/changed pinned input: {source}')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return wanted


def original_sdk_hashes():
    require(ORIGINAL_ZIP.is_file() and digest(ORIGINAL_ZIP) == ZIP_SHA, 'Original SDK package checksum mismatch')
    with zipfile.ZipFile(ORIGINAL_ZIP) as z:
        files = {n.removeprefix('esp32s3-libs/'): hashlib.sha256(z.read(n)).hexdigest()
                 for n in z.namelist() if not n.endswith('/')}
    require(tree_hashes(SDK) == files, 'Installed SDK differs from pinned official package')
    return files


def compile_object(member, mode):
    recorded = json.loads((TEMPLATES / f'{member}.command.json').read_text())
    cmd = []
    for arg in recorded:
        arg = arg.replace('@ARDUINO@', str(ARDUINO)).replace('@IDF@', str(INPUTS / 'esp-idf')).replace('@WORK@',str(WORK / mode))
        if mode == 'cache64':
            arg = arg.replace(str(SDK / 'qio_opi/include'), str(WORK / 'cache64/include'))
            arg = arg.replace('control32-', 'cache64-')
        cmd.append(arg)
    out = WORK / mode / f'{mode}-{member}'
    require(cmd[0] == str(GCC) and Path(cmd[-1]) == out, 'Recorded compiler command shape changed')
    (WORK / mode).mkdir(exist_ok=True)
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (WORK / mode / f'{member}.compile.log').write_bytes(result.stdout)
    require(result.returncode == 0, f'Compile failed: {member} {mode}; see cache64-work log')
    (WORK / mode / f'{member}.command.json').write_text(json.dumps(cmd, indent=2) + '\n')
    (WORK / mode / f'{member}.disassembly.txt').write_bytes(run([OBJDUMP, '-dr', out]))
    return out


# Reviewed against pinned IDF source and objdump output. Startup changes only
# movi.n a12,32 -> 64 before rom_config_data_cache_mode(). cache_utils also
# constant-folds esp_enable_cache_wrap() differently for ICache32/DCache64;
# do not pretend this is just an immediate-byte change. That optional wrap
# function must be absent from the final linked image (checked by build.py).
def semantic_fingerprint(data):
    e = Elf32(data)
    record = {'identity': e.identity,
              'sections': {n: [*v[:4], v[4].hex()] for n, v in e.section_content().items()},
              'relocations': e.relocations(), 'symbols': e.public_symbols()}
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def cache64_object_gate(member, control, target):
    if member == 'cpu_start.c.obj':
        return object_gate(control, target, {'.iram1.9': [[104, 44, 76]]})
    require(member == 'cache_utils.c.obj', 'Unexpected cache64 object')
    # Fingerprints cover all loadable/linker bytes, shapes, relocations and
    # public/undefined symbols; no new difference is accepted automatically.
    require(semantic_fingerprint(control) ==
            '10c9f4dcb16424d6513a0a38ac2408eaf3315a0c56a642e61ba997872c81e313',
            'cache_utils control fingerprint mismatch')
    require(semantic_fingerprint(target) ==
            'cdc35cc1da497d9ed96639a41100dc8e6c8e42f395e5ce83d88024279f4a5868',
            'cache_utils cache64 fingerprint mismatch')
    return {'passed': True, 'exact_semantic_fingerprints': True,
            'reviewed_changes': ['esp_config_data_cache_mode: enum 1 -> 2',
                                 'esp_enable_cache_wrap: ICache32/DCache64 constant folding',
                                 'corresponding literal pool, relocations and Xtensa metadata'],
            'final_link_must_discard': ['esp_config_data_cache_mode', 'esp_enable_cache_wrap']}


def build(origin):
    require(not OUTPUT.exists() and not MANIFEST.exists(), 'Output exists; verify it instead of overwriting')
    require(not WORK.exists(), 'Work directory exists; preserve/audit previous attempt before retry')
    inputs = bootstrap_inputs(origin)
    original_files = original_sdk_hashes()
    WORK.mkdir()
    config = (SDK / 'qio_opi/include/sdkconfig.h').read_text()
    require(config.count('#define CONFIG_ESP32S3_DATA_CACHE_LINE_32B 1\n') == 1, 'Unexpected cache choice')
    require(config.count('#define CONFIG_ESP32S3_DATA_CACHE_LINE_SIZE 32\n') == 1, 'Unexpected cache line')
    config64 = config.replace('#define CONFIG_ESP32S3_DATA_CACHE_LINE_32B 1\n', '#define CONFIG_ESP32S3_DATA_CACHE_LINE_64B 1\n').replace(
        '#define CONFIG_ESP32S3_DATA_CACHE_LINE_SIZE 32\n', '#define CONFIG_ESP32S3_DATA_CACHE_LINE_SIZE 64\n')
    (WORK / 'cache64/include').mkdir(parents=True)
    (WORK / 'cache64/include/sdkconfig.h').write_text(config64)
    gates, replacements = {}, {}
    for member, relative in OBJECTS.items():
        original = archive_members(SDK / relative)
        require(member in original, f'Missing original archive member: {member}')
        (WORK / f'original-{member}').write_bytes(original[member])
        control = compile_object(member, 'control32')
        gates[member] = {'control32': object_gate(original[member], control.read_bytes())}
        target = compile_object(member, 'cache64')
        gates[member]['cache64'] = cache64_object_gate(member, control.read_bytes(), target.read_bytes())
        replacements[member] = target
    # No SDK copy/mutation until every object gate has passed.
    shutil.copytree(SDK, OUTPUT)
    (OUTPUT / 'qio_opi/include/sdkconfig.h').write_text(config64)
    archive_checks = {}
    for member, relative in OBJECTS.items():
        before = archive_members(SDK / relative)
        replacement = WORK / 'archive-members' / member
        replacement.parent.mkdir(exist_ok=True)
        shutil.copyfile(replacements[member], replacement)
        run([AR, 'rDs', OUTPUT / relative, replacement])
        after = archive_members(OUTPUT / relative)
        require(before.keys() == after.keys(), f'Archive member list changed: {relative}')
        changed = [name for name in before if before[name] != after[name]]
        require(changed == [member], f'Unexpected archive replacements: {changed}')
        require(after[member] == replacements[member].read_bytes(), 'Inserted object mismatch')
        archive_checks[relative] = {'members': len(before), 'changed_members': changed,
                                   'all_other_members_byte_identical': True}
    final_files = tree_hashes(OUTPUT)
    require(final_files.keys() == original_files.keys(), 'SDK file set changed')
    require(sorted(k for k in final_files if final_files[k] != original_files[k]) == MODIFIED_FILES,
            'Unexpected changed SDK files')
    require(tree_hashes(SDK) == original_files, 'Global SDK changed during build')
    manifest = dict(state='PASS', sdk_path=str(OUTPUT), cache_line_bytes=64,
                    idf_commit=IDF_COMMIT, original_sdk_zip_sha256=ZIP_SHA,
                    original_sdk_file_sha256=original_files, sdk_file_sha256=final_files,
                    modified_files=MODIFIED_FILES, source_input_sha256=inputs,
                    script_sha256=digest(__file__), objects=gates, archives=archive_checks,
                    tool_sha256={str(p): digest(p) for p in [GCC, AR, OBJDUMP, TOOL_DIR / 'lib/xtensa_esp32s3.so']},
                    scope='Only two recompiled objects and matching cache-line header; all other SDK files preserved; no full SDK rebuild',
                    hardware_validation='NOT_PERFORMED', uploaded=False)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + '\n')
    verify_sdk_manifest()
    print(json.dumps({'state': 'PASS', 'sdk_path': str(OUTPUT), 'files': len(final_files),
                      'modified_files': MODIFIED_FILES, 'manifest_sha256': digest(MANIFEST)}))


def verify_sdk_manifest():
    m = json.loads(MANIFEST.read_text())
    require(m['state'] == 'PASS' and m['cache_line_bytes'] == 64, 'Invalid SDK manifest status')
    require(m['sdk_path'] == str(OUTPUT) and m['idf_commit'] == IDF_COMMIT, 'SDK provenance mismatch')
    require(m['script_sha256'] == digest(__file__), 'SDK builder changed since generation')
    require(m['modified_files'] == MODIFIED_FILES, 'Unexpected SDK scope')
    require(tree_hashes(OUTPUT) == m['sdk_file_sha256'], 'Private SDK changed since generation')
    for name, expected in COMMAND_SHA.items():
        require(digest(TEMPLATES / (name+'.command.json'))==expected,'Compiler template changed')
    for name, expected in m['source_input_sha256'].items():
        require(digest(INPUTS / name) == expected, f'Changed source input: {name}')
    for name, expected in m['tool_sha256'].items():
        require(digest(name) == expected, f'Changed tool: {name}')
    return m


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bootstrap-from', type=Path, default=BOOTSTRAP)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.verify:
        m = verify_sdk_manifest()
        print(json.dumps({'state': 'PASS', 'sdk_path': m['sdk_path'], 'files': len(m['sdk_file_sha256'])}))
    else:
        build(args.bootstrap_from)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f'CACHE64 SDK FAIL: {exc}', file=sys.stderr)
        sys.exit(1)
