#pragma once

#include <stddef.h>
#include <stdint.h>

namespace ws43b {

// RGB565 canvas only. Volatile stores deliberately prevent the optimizer from
// replacing this with a PSRAM-to-PSRAM expanding memcpy/memset operation.
// Verification proves the CPU-visible rectangle, not physical LCD output.
inline bool fillSolidRectChecked(uint16_t *pixels, size_t stridePixels,
                                 size_t height, size_t x, size_t y,
                                 size_t w, size_t h, uint16_t color) {
  if (!pixels || !stridePixels || !height ||
      (reinterpret_cast<uintptr_t>(pixels) & 1) ||
      stridePixels > SIZE_MAX / height) return false;
  const size_t count = stridePixels * height;
  if (count > SIZE_MAX / sizeof(uint16_t)) return false;
  const size_t bytes = count * sizeof(uint16_t);
  if (reinterpret_cast<uintptr_t>(pixels) > UINTPTR_MAX - bytes ||
      x > stridePixels || y > height ||
      w > stridePixels - x || h > height - y) return false;
  if (!w || !h) return true;
  volatile uint16_t *target = pixels;
  for (size_t row = y; row < y + h; ++row)
    for (size_t col = x; col < x + w; ++col)
      target[row * stridePixels + col] = color;
  // Check after the complete write, so a later row cannot silently damage an
  // earlier row within the requested rectangle.
  for (size_t row = y; row < y + h; ++row)
    for (size_t col = x; col < x + w; ++col)
      if (target[row * stridePixels + col] != color) return false;
  return true;
}

} // namespace ws43b
