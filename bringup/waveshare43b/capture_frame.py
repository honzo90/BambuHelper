#!/usr/bin/env python3
"""Capture one monitor frame and its RGB scanout buffer; never access USB/config.

The diagnostic firmware gates this endpoint to an already published monitor
frame. Images may contain the printer name and visible telemetry. They remain
in a private, Git-ignored local directory. A buffer snapshot is not an LCD PASS.
"""
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zlib


MAGIC = b'W43CAP01'
HEADER = struct.Struct('<8sHH7I')
WIDTH, HEIGHT = 800, 480
ROW_BYTES = WIDTH * 2
PAYLOAD_BYTES = ROW_BYTES * HEIGHT * 2
TOTAL_BYTES = HEADER.size + PAYLOAD_BYTES
NETWORK_TIMEOUT = 6
OVERALL_TIMEOUT = 12
LOCAL_DIR = Path(__file__).resolve().parent / 'local'


class CaptureError(Exception):
    """A bounded, non-sensitive diagnostic suitable for display to the user."""


@dataclass(frozen=True)
class Frame:
    frame: int
    uptime_ms: int
    front_index: int
    reset_reason: int
    canvas: bytes
    front: bytes


def validate_host(value):
    """An IPv4 literal only: no names, URLs, credentials, ports or IPv6 zones."""
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError:
        raise CaptureError('Wymagany jest sam adres IPv4 panelu, bez URL i portu.') from None
    if str(address) != value:
        raise CaptureError('Wymagany jest jednoznaczny zapis adresu IPv4.')
    return str(address)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise CaptureError('Przekierowanie HTTP odrzucone; nie pobrano innego adresu.')


def download_direct(host):
    """Child-process-only network operation; parent enforces a hard deadline.

Socket timeout alone would not bound a slow HTTP header/body. The parent kills
this single-use process after OVERALL_TIMEOUT, including connection/headers.
No environment proxy, redirect, retry, authentication or configuration request.
"""
    host = validate_host(host)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(
        f'http://{host}/diagnostics/frame',
        headers={'Accept': 'application/octet-stream', 'Connection': 'close'},
        method='GET')
    try:
        with opener.open(request, timeout=NETWORK_TIMEOUT) as response:
            if response.status != 200:
                raise CaptureError('Panel nie zwrócił gotowej klatki diagnostycznej.')
            if response.headers.get_all('Content-Type') != ['application/octet-stream']:
                raise CaptureError('Odrzucono nieprawidłowy typ odpowiedzi HTTP.')
            if response.headers.get_all('Content-Length') != [str(TOTAL_BYTES)]:
                raise CaptureError('Odrzucono nieprawidłową długość odpowiedzi HTTP.')
            if response.headers.get('Transfer-Encoding') is not None or response.headers.get('Content-Encoding') is not None:
                raise CaptureError('Kodowana odpowiedź HTTP nie jest dozwolona.')
            result = bytearray()
            while len(result) <= TOTAL_BYTES:
                chunk = response.read1(min(65536, TOTAL_BYTES + 1 - len(result)))
                if not chunk:
                    break
                result.extend(chunk)
            if len(result) != TOTAL_BYTES:
                raise CaptureError('Odrzucono niepełną lub zbyt długą klatkę.')
            return bytes(result)
    except urllib.error.HTTPError as error:
        # Do not read/print the response body, reason or redirect Location.
        if error.code == 503:
            raise CaptureError('Panel nie udostępnia teraz klatki monitora (HTTP 503).') from None
        raise CaptureError(f'Panel odrzucił odczyt klatki (HTTP {error.code}).') from None
    except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError):
        raise CaptureError('Nie udało się pobrać klatki; sprawdź dostępność panelu.') from None


def download(host):
    """Bound the complete request even for a stalled/malformed HTTP peer."""
    host = validate_host(host)
    started = time.monotonic()
    try:
        process = subprocess.run(
            [sys.executable, '-B', str(Path(__file__).resolve()), '--_download', host],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=OVERALL_TIMEOUT, check=False)
    except subprocess.TimeoutExpired:
        raise CaptureError('Przekroczono 12 s na pobranie; proces odczytu został zakończony.') from None
    if process.returncode != 0:
        # Child messages are fixed, but avoid forwarding arbitrary stderr.
        raise CaptureError('Odczyt odrzucony lub niedostępny; nie zapisano obrazu. Sprawdź, czy działa firmware z diagnostyką klatki.')
    if len(process.stdout) != TOTAL_BYTES:
        raise CaptureError('Odrzucono niepełną lub zbyt długą klatkę.')
    return process.stdout, time.monotonic() - started


def decode_capture(raw):
    if len(raw) != TOTAL_BYTES:
        raise CaptureError('Odrzucono niepełną lub zbyt długą klatkę.')
    magic, width, height, frame, uptime, pixel_format, row_bytes, payload_bytes, front_index, reset_reason = HEADER.unpack_from(raw)
    if (magic, width, height, pixel_format, row_bytes, payload_bytes) != (
            MAGIC, WIDTH, HEIGHT, 1, ROW_BYTES, PAYLOAD_BYTES):
        raise CaptureError('Nagłówek nie pasuje do protokołu W43CAP01, RGB565, 800 × 480.')
    if front_index not in (0, 1):
        raise CaptureError('Nieprawidłowy indeks bufora wyświetlacza.')
    canvas, front = bytearray(), bytearray()
    for y in range(HEIGHT):
        offset = HEADER.size + y * ROW_BYTES * 2
        canvas.extend(raw[offset:offset + ROW_BYTES])
        front.extend(raw[offset + ROW_BYTES:offset + ROW_BYTES * 2])
    return Frame(frame, uptime, front_index, reset_reason, bytes(canvas), bytes(front))


def compare_pixels(frame):
    mismatch_count, first = 0, []
    for index, ((canvas,), (front,)) in enumerate(zip(
            struct.iter_unpack('<H', frame.canvas), struct.iter_unpack('<H', frame.front))):
        if canvas != front:
            mismatch_count += 1
            if len(first) < 20:
                first.append({'x': index % WIDTH, 'y': index // WIDTH,
                              'canvas_rgb565': canvas, 'front_rgb565': front})
    return {'mismatch_pixels': mismatch_count, 'first_mismatches': first,
            'first_mismatches_limit': 20}


def png_rgb565(pixels):
    """RGB565 LE -> PNG RGB888, rows top to bottom, columns left to right."""
    if len(pixels) != ROW_BYTES * HEIGHT:
        raise CaptureError('Nieprawidłowy rozmiar bufora obrazu.')
    scanlines = bytearray()
    for y in range(HEIGHT):
        scanlines.append(0)  # PNG filter None; no rotation or transpose.
        for (value,) in struct.iter_unpack('<H', pixels[y * ROW_BYTES:(y + 1) * ROW_BYTES]):
            red, green, blue = (value >> 11) & 31, (value >> 5) & 63, value & 31
            scanlines.extend(((red << 3) | (red >> 2),
                              (green << 2) | (green >> 4),
                              (blue << 3) | (blue >> 2)))

    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))

    return (b'\x89PNG\r\n\x1a\n' +
            chunk(b'IHDR', struct.pack('>IIBBBBB', WIDTH, HEIGHT, 8, 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(bytes(scanlines), 6)) + chunk(b'IEND', b''))


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def save_capture(raw, download_seconds, output_root=LOCAL_DIR):
    """Validate first, then create one private, unique directory. No host in JSON."""
    frame = decode_capture(raw)
    comparison = compare_pixels(frame)
    canvas_png, front_png = png_rgb565(frame.canvas), png_rgb565(frame.front)
    metadata = {
        'protocol': MAGIC.decode('ascii'), 'width': WIDTH, 'height': HEIGHT,
        'pixel_format': 'RGB565_LE', 'frame': frame.frame,
        'uptime_ms': frame.uptime_ms, 'reset_reason': frame.reset_reason,
        'front_buffer_index': frame.front_index,
        'download_seconds': round(download_seconds, 3),
        **comparison,
        'capture_sha256': sha256(raw), 'canvas_rgb565_sha256': sha256(frame.canvas),
        'front_rgb565_sha256': sha256(frame.front),
        'canvas_png_sha256': sha256(canvas_png), 'front_png_sha256': sha256(front_png),
        'hardware_pass': False,
    }
    output_root = Path(output_root)
    if output_root.is_symlink():
        raise CaptureError('Katalog lokalnych wyników nie może być dowiązaniem symbolicznym.')
    output_root.mkdir(mode=0o700, parents=False, exist_ok=True)
    prefix = datetime.now(timezone.utc).strftime('frame-capture-%Y%m%dT%H%M%SZ-')
    directory = Path(tempfile.mkdtemp(prefix=prefix, dir=output_root))
    os.chmod(directory, 0o700)
    artifacts = {'capture.bin': raw, 'canvas.png': canvas_png, 'front.png': front_png,
                 'metadata.json': (json.dumps(metadata, ensure_ascii=False, indent=2) + '\n').encode('utf-8')}
    try:
        for name, content in artifacts.items():
            fd = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(content)
    except BaseException:
        # Only this invocation's freshly created directory is removed.
        shutil.rmtree(directory)
        raise
    return directory, metadata


def main():
    parser = argparse.ArgumentParser(description=(
        'Pobierz jedną klatkę monitora i jego bufor RGB. Bez USB i odczytu konfiguracji. '
        'Prywatne pliki w local/ mogą zawierać nazwę drukarki i widoczne dane wydruku. '
        'Zrzut nie oznacza sprzętowego PASS.'))
    parser.add_argument('--host', help='Adres IPv4 panelu (bez URL, portu i danych dostępowych)')
    parser.add_argument('--_download', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if bool(args.host) == bool(args._download):
        parser.error('Podaj --host z adresem IPv4 panelu.')
    try:
        if args._download:
            # The parent receives at most TOTAL_BYTES; no human text on stdout.
            sys.stdout.buffer.write(download_direct(args._download))
            return 0
        raw, duration = download(args.host)
        directory, metadata = save_capture(raw, duration)
        print(f"Zapisano klatkę {metadata['frame']}; różniące się piksele: {metadata['mismatch_pixels']}.")
        print(f'Canvas: {directory / "canvas.png"}')
        print(f'Bufor LCD: {directory / "front.png"}')
        print(f'Metadane: {directory / "metadata.json"}')
        print('Pliki są prywatne i zawierają dane widoczne na panelu. Porównaj obrazy ze zdjęciem LCD wykonanym w tej samej chwili. Zrzut buforów nie oznacza sprzętowego PASS.')
        return 0
    except (CaptureError, OSError) as error:
        if isinstance(error, CaptureError):
            print(str(error), file=sys.stderr)
        else:
            print('Nie udało się zapisać prywatnego zrzutu.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
