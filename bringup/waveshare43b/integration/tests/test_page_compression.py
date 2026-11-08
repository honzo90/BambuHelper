"""Compressed WebUI pages: lossless chunks, preserved #if blocks, host inflater."""

from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'bringup/waveshare43b/integration'))
import localize_web as L  # noqa: E402


def chunks(body):
    data = bytes(int(x, 16) for x in re.findall(r'0x([0-9a-f]{2})', body))
    pos, out = 0, []
    while pos < len(data):
        c = int.from_bytes(data[pos : pos + 4], 'little')
        r = int.from_bytes(data[pos + 4 : pos + 8], 'little')
        raw = zlib.decompress(data[pos + 8 : pos + 8 + c])
        assert len(raw) == r
        out.append(raw)
        pos += 8 + c
    return out


class PageCompression(unittest.TestCase):
    def test_lossless_and_preprocessor_preserved(self):
        src = (ROOT / 'include/web_pages.h').read_text()
        out = L.compress_pages(src)
        for name in L.COMPRESSED_PAGES:
            decl = 'static const char ' + name + '[] PROGMEM ='
            start = src.index(decl)
            end = src.index(')rawliteral";', start)
            original = src[start : end + len(')rawliteral";')]
            raw = [
                m.encode() for m in re.findall(r'R"rawliteral\((.*?)\)rawliteral"', original, re.S)
            ]
            pre = [l for l in original.splitlines() if l.startswith('#')]
            m = re.search(
                r'static const uint8_t ' + name + r'_Z\[\] PROGMEM = \{(.*?)\n\};', out, re.S
            )
            self.assertIsNotNone(m, name)
            self.assertEqual(chunks(m.group(1)), raw, name)
            self.assertEqual([l for l in m.group(1).splitlines() if l.startswith('#')], pre, name)
            self.assertNotIn(decl, out)
        # Unrelated pages (AP setup page) stay as plain text.
        self.assertIn('PAGE_AP_HTML', out)
        self.assertLess(len(out.encode()) - 3 * 0, len(src.encode()) * 2)  # sanity

    def test_serve_main_page_is_patched(self):
        template = (ROOT / 'src/web_template.cpp').read_text()
        self.assertIn(L.SERVE_MAIN_RAW, template)  # the build replaces exactly this block
        self.assertIn('/ota/upload', L.SERVE_MAIN_Z)  # emergency firmware upload
        self.assertIn('name=firmware', L.SERVE_MAIN_Z)

    def test_host_inflater(self):
        import random

        random.seed(3)
        parts = [bytes(random.choice(b'abc<>%XY ') for _ in range(n)) for n in (1, 500, 40000, 7)]
        blob = b''.join(
            len(z).to_bytes(4, 'little') + len(p).to_bytes(4, 'little') + z
            for p in parts
            for z in [zlib.compress(p, 9)]
        )
        expected = b''.join(parts)
        code = r'''
#include <cassert>
#include <cstdio>
#include <vector>
#include <zlib.h>
#include "ws43b_page_inflate.h"
static const uint8_t blob[] = {BLOB};
static size_t inf(uint8_t *dst, size_t dstLen, const uint8_t *src, size_t srcLen) {
  uLongf n = dstLen; return uncompress(dst, &n, src, srcLen) == Z_OK ? n : SIZE_MAX;
}
int main(){
  const size_t len = ws43b_page::rawLength(blob, sizeof blob);
  assert(len == EXPECTED);
  std::vector<char> out(len);
  assert(ws43b_page::inflateAll(blob, sizeof blob, out.data(), len, inf));
  fwrite(out.data(), 1, len, stdout);
  // Truncated or corrupted containers are rejected.
  assert(ws43b_page::rawLength(blob, sizeof blob - 1) == 0);
  std::vector<uint8_t> bad(blob, blob + sizeof blob); bad[20] ^= 0x55;
  assert(!ws43b_page::inflateAll(bad.data(), bad.size(), out.data(), len, inf));
  assert(!ws43b_page::inflateAll(blob, sizeof blob, out.data(), len - 1, inf)); // capacity mismatch
  return 0;
}
'''.replace('BLOB', ','.join(str(b) for b in blob)).replace('EXPECTED', str(len(expected)))
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'inf.cpp'
            src.write_text(code)
            exe = Path(tmp) / 'inf'
            subprocess.run(
                [
                    'clang++',
                    '-std=c++17',
                    '-Wall',
                    '-Wextra',
                    '-Werror',
                    '-I',
                    str(ROOT / 'include'),
                    str(src),
                    '-lz',
                    '-o',
                    str(exe),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            result = subprocess.run([str(exe)], check=True, capture_output=True)
            self.assertEqual(result.stdout, expected)


if __name__ == '__main__':
    unittest.main()
