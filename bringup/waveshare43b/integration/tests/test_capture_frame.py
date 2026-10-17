"""Offline protocol, RGB orientation, HTTP policy and private-output checks."""
from email.message import Message
import importlib.util
import json
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock
import zlib

SCRIPT = Path(__file__).resolve().parents[2] / 'capture_frame.py'
spec = importlib.util.spec_from_file_location('capture_frame', SCRIPT)
capture = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = capture
spec.loader.exec_module(capture)


def fixture(changes=(), header_changes=None):
    fields = [capture.MAGIC, 800, 480, 123, 456789, 1, 1600, 1536000, 1, 11]
    if header_changes:
        for field, value in header_changes.items():
            fields[field] = value
    result = bytearray(capture.HEADER.pack(*fields) + b'\x00' * capture.PAYLOAD_BYTES)
    for which, x, y, value in changes:
        offset = capture.HEADER.size + y * 3200 + which * 1600 + x * 2
        struct.pack_into('<H', result, offset, value)
    return bytes(result)


class FakeResponse:
    def __init__(self, body, headers=None, status=200):
        self.body, self.offset, self.status = body, 0, status
        self.headers = Message()
        for name, value in (headers or [
                ('Content-Type', 'application/octet-stream'),
                ('Content-Length', str(capture.TOTAL_BYTES))]):
            self.headers[name] = value

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read1(self, count):
        end = min(len(self.body), self.offset + count)
        result = self.body[self.offset:end]
        self.offset = end
        return result


class CaptureTests(unittest.TestCase):
    def test_protocol_interleaves_rows_and_little_endian_pixels(self):
        raw = fixture([(0, 0, 0, 0xf800), (1, 799, 0, 0x07e0),
                       (0, 0, 479, 0x001f), (1, 799, 479, 0xffff)])
        result = capture.decode_capture(raw)
        self.assertEqual((result.frame, result.uptime_ms, result.front_index, result.reset_reason),
                         (123, 456789, 1, 11))
        self.assertEqual(result.canvas[:2], b'\x00\xf8')
        self.assertEqual(result.front[1598:1600], b'\xe0\x07')
        self.assertEqual(result.canvas[-1600:-1598], b'\x1f\x00')
        self.assertEqual(result.front[-2:], b'\xff\xff')
        difference = capture.compare_pixels(result)
        self.assertEqual(difference['mismatch_pixels'], 4)
        self.assertEqual([(p['x'], p['y']) for p in difference['first_mismatches']],
                         [(0, 0), (799, 0), (0, 479), (799, 479)])

    def test_png_primary_colours_corners_orientation_and_crcs(self):
        raw = fixture([(0, 0, 0, 0xf800), (0, 799, 0, 0x07e0),
                       (0, 0, 479, 0x001f), (0, 799, 479, 0xffff)])
        png = capture.png_rgb565(capture.decode_capture(raw).canvas)
        self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')
        position, compressed, types = 8, bytearray(), []
        while position < len(png):
            size = struct.unpack_from('>I', png, position)[0]
            kind = png[position + 4:position + 8]
            data = png[position + 8:position + 8 + size]
            crc = struct.unpack_from('>I', png, position + 8 + size)[0]
            self.assertEqual(crc, zlib.crc32(kind + data))
            types.append(kind)
            if kind == b'IHDR':
                self.assertEqual(struct.unpack('>IIBBBBB', data), (800, 480, 8, 2, 0, 0, 0))
            if kind == b'IDAT':
                compressed.extend(data)
            position += size + 12
        self.assertEqual(types, [b'IHDR', b'IDAT', b'IEND'])
        pixels = zlib.decompress(bytes(compressed))
        self.assertEqual(len(pixels), 480 * 2401)
        for y in range(480):
            self.assertEqual(pixels[y * 2401], 0)
        def pixel(x, y):
            offset = y * 2401 + 1 + x * 3
            return pixels[offset:offset + 3]
        self.assertEqual(pixel(0, 0), b'\xff\x00\x00')
        self.assertEqual(pixel(799, 0), b'\x00\xff\x00')
        self.assertEqual(pixel(0, 479), b'\x00\x00\xff')
        self.assertEqual(pixel(799, 479), b'\xff\xff\xff')
        self.assertEqual(pixel(400, 200), b'\x00\x00\x00')

    def test_invalid_geometry_format_magic_index_and_lengths(self):
        for field, value in [(0, b'WRONG123'), (1, 480), (1, 65535), (2, 800),
                             (5, 0), (5, 2), (6, 1601), (7, 0xffffffff), (8, 2)]:
            with self.subTest(field=field, value=value), self.assertRaises(capture.CaptureError):
                capture.decode_capture(fixture(header_changes={field: value}))
        raw = fixture()
        for bad in (b'', raw[:39], raw[:-1], raw + b'X'):
            with self.assertRaises(capture.CaptureError):
                capture.decode_capture(bad)

    def test_uint32_counters_are_preserved_without_false_validity_checks(self):
        result = capture.decode_capture(fixture(header_changes={3: 0xffffffff, 4: 0, 9: 0xffffffff}))
        self.assertEqual((result.frame, result.uptime_ms, result.reset_reason), (0xffffffff, 0, 0xffffffff))

    def test_mismatch_detail_is_bounded_but_total_is_complete(self):
        raw = fixture([(0, x, 0, 1) for x in range(50)])
        comparison = capture.compare_pixels(capture.decode_capture(raw))
        self.assertEqual(comparison['mismatch_pixels'], 50)
        self.assertEqual(len(comparison['first_mismatches']), 20)
        self.assertEqual(capture.compare_pixels(capture.decode_capture(fixture()))['mismatch_pixels'], 0)

    def test_private_unique_artifacts_metadata_hashes_and_no_host(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'local'
            raw = fixture()
            directory, metadata = capture.save_capture(raw, 1.23456, root)
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
            self.assertEqual(sorted(p.name for p in directory.iterdir()),
                             ['canvas.png', 'capture.bin', 'front.png', 'metadata.json'])
            for artifact in directory.iterdir():
                self.assertEqual(stat.S_IMODE(artifact.stat().st_mode), 0o600)
            self.assertEqual((directory / 'capture.bin').read_bytes(), raw)
            self.assertEqual(json.loads((directory / 'metadata.json').read_text()), metadata)
            self.assertEqual(metadata['capture_sha256'], capture.sha256(raw))
            self.assertEqual(metadata['canvas_png_sha256'], capture.sha256((directory / 'canvas.png').read_bytes()))
            self.assertEqual(metadata['front_png_sha256'], capture.sha256((directory / 'front.png').read_bytes()))
            self.assertEqual(metadata['download_seconds'], 1.235)
            self.assertIs(metadata['hardware_pass'], False)
            self.assertEqual(set(metadata), {
                'protocol', 'width', 'height', 'pixel_format', 'frame', 'uptime_ms',
                'reset_reason', 'front_buffer_index', 'download_seconds',
                'mismatch_pixels', 'first_mismatches', 'first_mismatches_limit',
                'capture_sha256', 'canvas_rgb565_sha256', 'front_rgb565_sha256',
                'canvas_png_sha256', 'front_png_sha256', 'hardware_pass'})
            directory2, _ = capture.save_capture(raw, 1.0, root)
            self.assertNotEqual(directory, directory2)

    def test_bad_input_saves_nothing_and_symlink_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'local'
            with self.assertRaises(capture.CaptureError):
                capture.save_capture(b'invalid', 1.0, root)
            self.assertFalse(root.exists())
            root.symlink_to(temporary, target_is_directory=True)
            with self.assertRaises(capture.CaptureError):
                capture.save_capture(fixture(), 1.0, root)

    def test_host_is_only_ipv4_literal(self):
        self.assertEqual(capture.validate_host('10.10.10.28'), '10.10.10.28')
        for host in ('panel.local', 'http://10.10.10.28', '10.10.10.28:80',
                     '10.010.10.28', '127.1', '::1', 'user:pw@10.10.10.28',
                     '10.10.10.28/anything', '10.10.10.28\n', '256.1.1.1'):
            with self.subTest(host=host), self.assertRaises(capture.CaptureError):
                capture.validate_host(host)

    def fake_download(self, response):
        opener = Mock()
        opener.open.return_value = response
        with patch.object(capture.urllib.request, 'build_opener', return_value=opener) as factory:
            result = capture.download_direct('10.10.10.28')
            handlers = factory.call_args.args
            self.assertEqual(handlers[0].proxies, {})
            self.assertIsInstance(handlers[1], capture.NoRedirect)
            request = opener.open.call_args.args[0]
            self.assertEqual(request.full_url, 'http://10.10.10.28/diagnostics/frame')
            self.assertEqual(request.get_method(), 'GET')
            self.assertIsNone(request.data)
            self.assertEqual(opener.open.call_args.kwargs['timeout'], 6)
            self.assertEqual(opener.open.call_count, 1)
            return result

    def test_direct_http_is_no_proxy_one_get_and_has_exact_length(self):
        raw = fixture()
        self.assertEqual(self.fake_download(FakeResponse(raw)), raw)
        for body in (raw[:-1], raw + b'X'):
            with self.assertRaises(capture.CaptureError):
                self.fake_download(FakeResponse(body))

    def test_http_headers_fail_closed(self):
        base = [('Content-Type', 'application/octet-stream'), ('Content-Length', str(capture.TOTAL_BYTES))]
        variants = [base + [('Content-Length', str(capture.TOTAL_BYTES))],
                    base + [('Content-Type', 'application/octet-stream')],
                    base + [('Transfer-Encoding', 'chunked')],
                    base + [('Content-Encoding', 'gzip')],
                    [('Content-Type', 'text/html'), base[1]],
                    [base[0], ('Content-Length', str(capture.TOTAL_BYTES - 1))],
                    [base[0], ('Content-Length', '1536040, 1536040')]]
        for headers in variants:
            with self.subTest(headers=headers), self.assertRaises(capture.CaptureError):
                self.fake_download(FakeResponse(fixture(), headers))
        with self.assertRaises(capture.CaptureError):
            self.fake_download(FakeResponse(fixture(), status=503))

    def test_redirect_is_rejected_before_another_request(self):
        with self.assertRaises(capture.CaptureError):
            capture.NoRedirect().redirect_request(None, None, 302, 'Found', {},
                                                  'http://other.invalid/secrets')

    def test_overall_deadline_and_bounded_child_protocol(self):
        raw = fixture()
        result = subprocess.CompletedProcess([], 0, raw, b'')
        with patch.object(capture.subprocess, 'run', return_value=result) as run:
            self.assertEqual(capture.download('10.10.10.28')[0], raw)
            self.assertEqual(run.call_args.kwargs['timeout'], 12)
            self.assertEqual(run.call_args.args[0][-2:], ['--_download', '10.10.10.28'])
            self.assertNotIn('shell', run.call_args.kwargs)
        with patch.object(capture.subprocess, 'run', side_effect=subprocess.TimeoutExpired([], 12)):
            with self.assertRaises(capture.CaptureError):
                capture.download('10.10.10.28')
        for result in (subprocess.CompletedProcess([], 0, raw + b'X', b''),
                       subprocess.CompletedProcess([], 1, b'', b'PRIVATE_ERROR_TEXT')):
            with patch.object(capture.subprocess, 'run', return_value=result):
                with self.assertRaises(capture.CaptureError) as caught:
                    capture.download('10.10.10.28')
                self.assertNotIn('PRIVATE_ERROR_TEXT', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
