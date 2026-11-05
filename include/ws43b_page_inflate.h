#pragma once
// Compressed WebUI pages (WS43B build only). The build stores each raw-literal
// chunk of a page as [compressed length u32][raw length u32][zlib stream],
// keeping the page's #if blocks around the chunks, so the real preprocessor
// still decides which parts exist. At request time the chunks are inflated in
// order into one PSRAM buffer with the ESP32-S3 ROM inflater.
#include <stddef.h>
#include <stdint.h>
#include <string.h>

namespace ws43b_page {

inline uint32_t read32(const uint8_t *p) {
  return uint32_t(p[0]) | (uint32_t(p[1]) << 8) | (uint32_t(p[2]) << 16) | (uint32_t(p[3]) << 24);
}

// Total raw length of all chunks, or 0 if the container is malformed.
inline size_t rawLength(const uint8_t *z, size_t zlen) {
  size_t pos = 0, total = 0;
  while (pos < zlen) {
    if (zlen - pos < 8) return 0;
    const uint32_t c = read32(z + pos), r = read32(z + pos + 4);
    pos += 8;
    if (c > zlen - pos || r > 1u << 20) return 0;
    pos += c;
    total += r;
  }
  return total;
}

// Inflate every chunk into `out` (capacity >= rawLength). `inflate` is
// (dst, dstLen, src, srcLen) -> bytes written or SIZE_MAX on error; the
// firmware passes the ROM tinfl, host tests pass zlib.
template <class Inflate>
inline bool inflateAll(const uint8_t *z, size_t zlen, char *out, size_t capacity, Inflate inflate) {
  size_t pos = 0, written = 0;
  while (pos < zlen) {
    if (zlen - pos < 8) return false;
    const uint32_t c = read32(z + pos), r = read32(z + pos + 4);
    pos += 8;
    if (c > zlen - pos || r > capacity - written) return false;
    if (inflate(reinterpret_cast<uint8_t *>(out + written), r, z + pos, c) != r) return false;
    pos += c;
    written += r;
  }
  return written == capacity;
}

}  // namespace ws43b_page

#if defined(ARDUINO) && defined(BOARD_IS_WS43B)
#include <esp_heap_caps.h>
#include "miniz.h"  // ESP32-S3 ROM tinfl

namespace ws43b_page {
// Returns a NUL-terminated PSRAM buffer (free with heap_caps_free) or nullptr.
inline char *inflatePage(const uint8_t *z, size_t zlen, size_t &length) {
  length = rawLength(z, zlen);
  if (!length) return nullptr;
  char *out = static_cast<char *>(heap_caps_malloc(length + 1, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  // ~11 KB decompressor state: never on the web server task stack.
  auto *state = static_cast<tinfl_decompressor *>(
      heap_caps_malloc(sizeof(tinfl_decompressor), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  bool ok = out && state;
  if (ok) {
    ok = inflateAll(z, zlen, out, length, [state](uint8_t *dst, size_t dstLen, const uint8_t *src, size_t srcLen) {
      tinfl_init(state);
      size_t in = srcLen, outLen = dstLen;
      const tinfl_status status = tinfl_decompress(state, src, &in, dst, dst, &outLen,
          TINFL_FLAG_PARSE_ZLIB_HEADER | TINFL_FLAG_USING_NON_WRAPPING_OUTPUT_BUF);
      return status == TINFL_STATUS_DONE && in == srcLen ? outLen : SIZE_MAX;
    });
  }
  if (state) heap_caps_free(state);
  if (!ok) { if (out) heap_caps_free(out); length = 0; return nullptr; }
  out[length] = 0;
  return out;
}
}  // namespace ws43b_page
#endif
