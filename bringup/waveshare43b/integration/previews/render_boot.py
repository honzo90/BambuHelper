#!/usr/bin/env python3
"""Render the shared firmware boot composition with actual assets and VLW masks.

The host emulates drawing primitives and the pinned VLW metrics. Images are
source previews, not LCD captures, hardware timing, networking or touch proof.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import subprocess
import tempfile
import zlib

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def compile_preview(directory):
    directory = Path(directory)
    source = (ROOT / 'src/display_ws43b.cpp').read_text()
    start = source.index('int v2Text(')
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        if source[end] == '{':
            depth += 1
        elif source[end] == '}':
            depth -= 1
        end += 1
    implementation = source[start:end]
    (directory / 'production_boot_text.h').write_text(implementation)
    (directory / 'pgmspace.h').write_text(
        '#pragma once\n#define PROGMEM\n'
        '#define pgm_read_byte(p) (*static_cast<const uint8_t *>(p))\n')
    binary = directory / 'boot_preview'
    subprocess.run(['clang++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                    '-I', str(directory), '-I', str(ROOT / 'include'),
                    str(HERE / 'boot_preview.cpp'), '-o', str(binary)],
                   check=True, text=True, capture_output=True)
    return binary


def chunk(kind, payload):
    return (struct.pack('>I', len(payload)) + kind + payload +
            struct.pack('>I', zlib.crc32(kind + payload) & 0xffffffff))


def png_from_ppm(source, destination):
    data = source.read_bytes()
    magic, size, maximum, pixels = data.split(b'\n', 3)
    if magic != b'P6' or maximum != b'255':
        raise ValueError('Unexpected native pixels')
    width, height = map(int, size.split())
    if len(pixels) != width * height * 3:
        raise ValueError('Truncated native pixels')
    scan = b''.join(b'\0' + pixels[y * width * 3:(y + 1) * width * 3]
                    for y in range(height))
    destination.write_bytes(
        b'\x89PNG\r\n\x1a\n' +
        chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) +
        chunk(b'IDAT', zlib.compress(scan, 9)) + chunk(b'IEND', b''))
    return {'width': width, 'height': height,
            'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path,
                        default=HERE.parent / 'test-output' / 'boot-native-preview')
    parser.add_argument('--overview', action='store_true', help='Create a 2x2 PL contact sheet (Pillow).')
    parser.add_argument('--gif', action='store_true', help='Create a 2.4 s wait animation (Pillow).')
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    inputs = ['src/display_ws43b.cpp', 'include/ws43b_boot_scene.h',
              'include/ws43b_native_scene.h', 'include/ws43b_ui_icons.h',
              'include/ws43b_visual_assets.h', 'include/ws43b_visual_assets_data.h',
              'include/fonts/ws43b_dashboard_v2.h']
    inputs.extend(str(p.relative_to(ROOT)) for p in
                  [Path(__file__).resolve(), HERE / 'boot_preview.cpp'])
    record = {'scope': __doc__, 'source_sha256': {
        p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
        'images': []}
    with tempfile.TemporaryDirectory(prefix='ws43b-boot-preview-') as temporary:
        directory = Path(temporary)
        binary = compile_preview(directory)
        result = subprocess.run([str(binary), '--verify'], check=True,
                                capture_output=True, text=True)
        record['tests'] = json.loads(result.stdout)
        for language in ['pl', 'en']:
            for phase, name in enumerate(['panel', 'wifi', 'printer', 'data']):
                filename = f'boot-{phase + 1}-{name}-{language}'
                ppm = directory / f'{filename}.ppm'
                png = args.output_dir / f'{filename}.png'
                subprocess.run([str(binary), '--preview', str(ppm), str(phase),
                                language, '0084', '880'], check=True)
                record['images'].append({'name': filename, 'phase': name,
                                         'language': language,
                                         **png_from_ppm(ppm, png)})
        if args.overview or args.gif:
            from PIL import Image
        if args.overview:
            overview = Image.new('RGB', (1600, 960))
            for phase, name in enumerate(['panel', 'wifi', 'printer', 'data']):
                with Image.open(args.output_dir / f'boot-{phase + 1}-{name}-pl.png') as image:
                    overview.paste(image, ((phase % 2) * 800, (phase // 2) * 480))
            path = args.output_dir / 'boot-overview.png'
            overview.save(path)
            record['overview_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        if args.gif:
            frames = []
            for now in range(0, 2400, 160):
                ppm = directory / f'animation-{now}.ppm'
                subprocess.run([str(binary), '--preview', str(ppm), '2',
                                'pl', '0084', str(now)], check=True)
                with Image.open(ppm) as image:
                    frames.append(image.copy())
            path = args.output_dir / 'boot-printer-animation.gif'
            frames[0].save(path, save_all=True, append_images=frames[1:],
                           duration=160, loop=0, optimize=False, disposal=2)
            record['animation'] = {'frames': len(frames), 'duration_ms': 2400,
                                   'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                   'scope': 'Host animation only; not a measured LCD frame rate.'}
    (args.output_dir / 'boot-preview-result.json').write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'output': str(args.output_dir), 'tests': record['tests'],
                      'images': len(record['images'])}))


if __name__ == '__main__':
    main()
