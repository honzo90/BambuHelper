#pragma once
#include <stddef.h>
#include <stdint.h>
#include <string.h>

namespace ws43b {
constexpr size_t CAPTURE_WIDTH = 800, CAPTURE_HEIGHT = 480;
constexpr size_t CAPTURE_ROW_BYTES = CAPTURE_WIDTH * 2;
constexpr size_t CAPTURE_HEADER_BYTES = 40;
constexpr size_t CAPTURE_PAYLOAD_BYTES = CAPTURE_ROW_BYTES * CAPTURE_HEIGHT * 2;
constexpr size_t CAPTURE_BYTES = CAPTURE_HEADER_BYTES + CAPTURE_PAYLOAD_BYTES;
struct FrameCaptureInfo {
  uint32_t frame, uptimeMs, frontIndex, resetReason;
};
inline void captureLE32(uint8_t *out, uint32_t value) {
  for (size_t i = 0; i < 4; ++i) out[i] = uint8_t(value >> (i * 8));
}
inline void captureHeader(uint8_t (&out)[CAPTURE_HEADER_BYTES], const FrameCaptureInfo &info) {
  memcpy(out, "W43CAP01", 8);
  out[8] = uint8_t(CAPTURE_WIDTH); out[9] = uint8_t(CAPTURE_WIDTH >> 8);
  out[10] = uint8_t(CAPTURE_HEIGHT); out[11] = uint8_t(CAPTURE_HEIGHT >> 8);
  captureLE32(out + 12, info.frame); captureLE32(out + 16, info.uptimeMs);
  captureLE32(out + 20, 1); // native RGB565, explicit little-endian transport
  captureLE32(out + 24, CAPTURE_ROW_BYTES);
  captureLE32(out + 28, CAPTURE_PAYLOAD_BYTES);
  captureLE32(out + 32, info.frontIndex); captureLE32(out + 36, info.resetReason);
}
// Read each source pixel exactly once, without PSRAM-to-PSRAM memcpy. Output is
// one canvas row followed by the corresponding current driver-front row.
inline bool captureRow(const volatile uint16_t *canvas, const volatile uint16_t *front,
                       size_t row, uint8_t *out, size_t capacity) {
  if (!canvas || !front || !out || row >= CAPTURE_HEIGHT || capacity < CAPTURE_ROW_BYTES * 2)
    return false;
  for (size_t x = 0; x < CAPTURE_WIDTH; ++x) {
    const uint16_t a = canvas[row * CAPTURE_WIDTH + x];
    const uint16_t b = front[row * CAPTURE_WIDTH + x];
    out[2*x] = uint8_t(a); out[2*x+1] = uint8_t(a >> 8);
    out[CAPTURE_ROW_BYTES+2*x] = uint8_t(b);
    out[CAPTURE_ROW_BYTES+2*x+1] = uint8_t(b >> 8);
  }
  return true;
}
} // namespace ws43b
