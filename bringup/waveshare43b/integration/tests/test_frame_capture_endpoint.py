"""Exercise the real WS43B capture handler and pixel helper without sockets.

The C++ handler is extracted verbatim and built with ASan/UBSan. Python decodes
the resulting wire bytes independently, using known, distinct canvas/front
patterns. No serial ports, credentials, network or physical display are used.
"""
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[4]


HARNESS = r'''
#include <algorithm>
#include <cassert>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <limits>
#include <string>
#include <vector>
#include "ws43b_frame_capture.h"
#define DRAM_ATTR
constexpr int MSG_DONTWAIT = 0x40;
static std::string mode, wire;
static uint32_t nowMs = 100, firstMs = 100;
static size_t sends = 0, reads = 0, infoReads = 0, stops = 0;
static std::vector<uint16_t> canvas(800*480), front(800*480);
uint32_t millis() { return nowMs; }
void delay(unsigned ms) { assert(ms == 1); nowMs += ms; }
bool isAPMode() { return mode == "ap"; }
bool isPrinterConfigured(unsigned slot) { assert(slot == 0); return mode != "unconfigured"; }
struct ClientStub {
  int fd() const { return mode == "invalid_fd" ? -1 : 7; }
  void stop() { ++stops; }
};
struct ServerStub { ClientStub client() { return {}; } } server;
int send(int fd, const void *bytes, size_t count, int flags) {
  assert(fd == 7 && flags == MSG_DONTWAIT && count > 0);
  ++sends;
  if (mode == "closed") return 0;
  if (mode == "error" || (mode == "error_after_data" && wire.size() >= 6600)) {
    errno = EPIPE; return -1;
  }
  if (mode == "blocked" || mode == "blocked_wrap") { errno = EAGAIN; return -1; }
  if (mode == "retry" && sends <= 3) {
    errno = sends == 1 ? EAGAIN : sends == 2 ? EWOULDBLOCK : EINTR;
    return -1;
  }
  if (mode == "slow" || mode == "slow_wrap") nowMs += 19;
  if (mode == "partial" || mode == "retry") count = std::min(count, size_t(1021));
  wire.append(static_cast<const char *>(bytes), count);
  return int(count);
}
namespace ws43b {
bool frameCaptureInfo(FrameCaptureInfo &info) {
  ++infoReads;
  info = {0x12345678u, 0xabcdef01u, 1, 11};
  return mode != "before_monitor";
}
bool readFrameCaptureRow(size_t row, uint8_t *out, size_t capacity) {
  ++reads;
  if (mode == "row_failure" && row == 7) return false;
  return captureRow(canvas.data(), front.data(), row, out, capacity);
}
}
'''

MAIN = r'''
static void helperBoundaryChecks() {
  std::vector<uint8_t> guarded(3202, 0x5a);
  uint8_t *out = guarded.data() + 1;
  auto unchanged = [&]() {
    for (uint8_t value : guarded) assert(value == 0x5a);
  };
  assert(!ws43b::captureRow(nullptr, front.data(), 0, out, 3200)); unchanged();
  assert(!ws43b::captureRow(canvas.data(), nullptr, 0, out, 3200)); unchanged();
  assert(!ws43b::captureRow(canvas.data(), front.data(), 0, nullptr, 3200)); unchanged();
  assert(!ws43b::captureRow(canvas.data(), front.data(), 480, out, 3200)); unchanged();
  assert(!ws43b::captureRow(canvas.data(), front.data(), SIZE_MAX, out, 3200)); unchanged();
  assert(!ws43b::captureRow(canvas.data(), front.data(), 0, out, 3199)); unchanged();
  for (size_t row : {size_t(0), size_t(1), size_t(479)}) {
    assert(ws43b::captureRow(canvas.data(), front.data(), row, out, 3200));
    assert(guarded.front() == 0x5a && guarded.back() == 0x5a);
    for (size_t x = 0; x < 800; ++x) {
      const unsigned a = unsigned(out[2*x]) + unsigned(out[2*x+1])*256;
      const unsigned b = unsigned(out[1600+2*x]) + unsigned(out[1600+2*x+1])*256;
      assert(a == canvas[row*800+x] && b == front[row*800+x]);
    }
  }
}
int main(int argc, char **argv) {
  assert(argc == 2); mode = argv[1];
  for (size_t y = 0; y < 480; ++y) {
    for (size_t x = 0; x < 800; ++x) {
      canvas[y*800+x] = uint16_t((x*73) ^ (y*257) ^ 0xa51c);
      front[y*800+x] = uint16_t((x*17 + y*511 + 0x1357) & 0xffff);
    }
  }
  if (mode == "helper") { helperBoundaryChecks(); return 0; }
  if (mode == "blocked_wrap" || mode == "slow_wrap") nowMs = UINT32_MAX-99;
  firstMs = nowMs;
  if (mode == "already_expired" || mode == "already_expired_wrap") {
    if (mode == "already_expired_wrap") nowMs = 200;
    const uint8_t byte = 0x5a;
    assert(!sendFrameBytes(7, &byte, 1, uint32_t(nowMs-8000)));
    assert(sends == 0);
  } else {
    handleFrameCapture();
    assert(stops == 1);
  }
  std::cout.write(wire.data(), static_cast<std::streamsize>(wire.size()));
  std::cerr << "{\"sends\":" << sends << ",\"reads\":" << reads
    << ",\"info_reads\":" << infoReads << ",\"stops\":" << stops
    << ",\"elapsed_ms\":" << uint32_t(nowMs-firstMs) << "}\n";
}
'''


class FrameCaptureEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('clang++') or shutil.which('c++')
        if not compiler:
            raise unittest.SkipTest('Native C++ compiler required')
        cls.folder = tempfile.TemporaryDirectory(prefix='bambu-frame-capture-')
        cls.addClassCleanup(cls.folder.cleanup)
        tmp = Path(cls.folder.name)
        source = (REPO / 'src/web_server.cpp').read_text()
        start = source.index('static bool sendFrameBytes(')
        end = source.index('\n#endif', start)
        cpp = tmp / 'frame_capture.cpp'
        cls.binary = tmp / 'frame_capture'
        cpp.write_text(HARNESS + source[start:end] + MAIN)
        result = subprocess.run(
            [compiler, '-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
             '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
             '-I', str(REPO / 'src'), str(cpp), '-o', str(cls.binary)],
            capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise AssertionError(result.stderr)

    def run_capture(self, mode):
        result = subprocess.run([str(self.binary), mode], capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        return result.stdout, json.loads(result.stderr)

    def parse_http(self, wire, expected_code=200):
        head, body = wire.split(b'\r\n\r\n', 1)
        lines = head.decode('ascii').split('\r\n')
        self.assertEqual(int(lines[0].split()[1]), expected_code)
        headers = dict(line.split(': ', 1) for line in lines[1:])
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(headers['Connection'], 'close')
        return headers, body

    def assert_complete_frame(self, wire):
        headers, body = self.parse_http(wire)
        self.assertEqual(headers['Content-Type'], 'application/octet-stream')
        self.assertEqual(int(headers['Content-Length']), 40 + 1536000)
        self.assertEqual(len(body), 40 + 1536000)
        self.assertEqual(struct.unpack_from('<8sHH7I', body), (
            b'W43CAP01', 800, 480, 0x12345678, 0xabcdef01, 1,
            1600, 1536000, 1, 11))
        # Decoder knows transport layout, not the implementation's constants.
        # Distinct front data detects exporting canvas twice or wrong order.
        for y in range(480):
            self.assertEqual(struct.unpack_from('<800H', body, 40+y*3200),
                             tuple(((x*73) ^ (y*257) ^ 0xa51c) & 0xffff for x in range(800)))
            self.assertEqual(struct.unpack_from('<800H', body, 40+y*3200+1600),
                             tuple((x*17 + y*511 + 0x1357) & 0xffff for x in range(800)))

    def test_setup_ap_unconfigured_never_read_pixels(self):
        for mode in ('before_monitor', 'ap', 'unconfigured'):
            with self.subTest(mode=mode):
                wire, stats = self.run_capture(mode)
                headers, body = self.parse_http(wire, 409)
                self.assertEqual(headers['Content-Length'], '0')
                self.assertEqual(body, b'')
                self.assertEqual(stats['reads'], 0)
                self.assertEqual(stats['info_reads'], int(mode == 'before_monitor'))
                self.assertEqual(stats['stops'], 1)

    def test_complete_interleaved_canvas_and_front_frame(self):
        wire, stats = self.run_capture('complete')
        self.assert_complete_frame(wire)
        self.assertEqual(stats['reads'], 480)
        self.assertEqual(stats['info_reads'], 1)

    def test_partial_writes_and_transient_errors_preserve_bytes(self):
        reference, _ = self.run_capture('complete')
        for mode in ('partial', 'retry'):
            with self.subTest(mode=mode):
                wire, stats = self.run_capture(mode)
                self.assertEqual(wire, reference)
                self.assertEqual(stats['reads'], 480)
                self.assertLess(stats['elapsed_ms'], 8000)

    def test_closed_invalid_and_failed_client_stop(self):
        for mode in ('closed', 'invalid_fd', 'error'):
            with self.subTest(mode=mode):
                wire, stats = self.run_capture(mode)
                self.assertEqual(wire, b'')
                self.assertEqual(stats['reads'], 0)
                self.assertEqual(stats['stops'], 1)
                self.assertEqual(stats['sends'], 0 if mode == 'invalid_fd' else 1)

    def test_midstream_error_and_row_failure_leave_rejectable_truncation(self):
        for mode in ('error_after_data', 'row_failure'):
            with self.subTest(mode=mode):
                wire, stats = self.run_capture(mode)
                headers, body = self.parse_http(wire)
                self.assertLess(len(body), int(headers['Content-Length']))
                self.assertGreaterEqual(len(body), 40)
                self.assertEqual(stats['stops'], 1)
                self.assertNotIn(b'HTTP/', body)
                if mode == 'row_failure':
                    self.assertEqual(len(body), 40+7*3200)
                    self.assertEqual(stats['reads'], 8)

    def test_blocked_client_eight_second_deadline_including_wrap(self):
        for mode in ('blocked', 'blocked_wrap'):
            with self.subTest(mode=mode):
                wire, stats = self.run_capture(mode)
                self.assertEqual(wire, b'')
                self.assertEqual(stats['elapsed_ms'], 8000)
                self.assertEqual(stats['sends'], 8000)
                self.assertEqual(stats['reads'], 0)
                self.assertEqual(stats['stops'], 1)

    def test_deadline_is_absolute_across_rows_including_wrap(self):
        for mode in ('slow', 'slow_wrap'):
            with self.subTest(mode=mode):
                wire, stats = self.run_capture(mode)
                headers, body = self.parse_http(wire)
                self.assertLess(len(body), int(headers['Content-Length']))
                self.assertEqual(stats['elapsed_ms'], 8000)
                self.assertLess(stats['reads'], 480)
                self.assertEqual(stats['stops'], 1)

    def test_expired_deadline_sends_no_byte_including_wrap(self):
        for mode in ('already_expired', 'already_expired_wrap'):
            with self.subTest(mode=mode):
                wire, stats = self.run_capture(mode)
                self.assertEqual(wire, b'')
                self.assertEqual(stats['sends'], 0)

    def test_helper_null_bounds_capacity_and_corner_rows(self):
        result = subprocess.run([str(self.binary), 'helper'], capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        self.assertEqual(result.stdout, b'')


if __name__ == '__main__':
    unittest.main()
