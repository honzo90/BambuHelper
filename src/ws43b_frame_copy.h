#pragma once

#include <stddef.h>
#include <stdint.h>
#include <string.h>

namespace ws43b {

// Scale each RGB565 component once while presenting; never modify the canvas.
inline uint16_t dimRgb565(uint16_t pixel, unsigned percent) {
  return uint16_t(((((pixel>>11)&31)*percent/100)<<11) |
                  ((((pixel>>5)&63)*percent/100)<<5) | ((pixel&31)*percent/100));
}
inline bool frameRangesOverlap(uintptr_t a, size_t aSize, uintptr_t b, size_t bSize) {
  return a < b + bSize && b < a + aSize;
}

// One internal-SRAM row separates reads of the PSRAM canvas from writes to
// the inactive PSRAM scanout buffer. The caller owns all three ranges and
// must not let the display read destination until this function succeeds.
// Readback checks CPU-visible bytes, not physical LCD output or DMA timing.
inline bool copyFrameChecked(uint8_t *destination, const uint8_t *source,
                             uint32_t *scratch, size_t scratchBytes,
                             size_t rowBytes, size_t rows, unsigned percent = 100) {
  if (percent > 100 || !destination || !source || !scratch || !rowBytes || !rows ||
      (rowBytes & 3) || scratchBytes < rowBytes || rows > SIZE_MAX / rowBytes)
    return false;
  const uintptr_t dst = reinterpret_cast<uintptr_t>(destination);
  const uintptr_t src = reinterpret_cast<uintptr_t>(source);
  const uintptr_t tmp = reinterpret_cast<uintptr_t>(scratch);
  const size_t bytes = rowBytes * rows;
  if ((dst | src | tmp) & 3) return false;
  if (dst > UINTPTR_MAX - bytes || src > UINTPTR_MAX - bytes ||
      tmp > UINTPTR_MAX - scratchBytes) return false;
  if (frameRangesOverlap(dst, bytes, src, bytes) ||
      frameRangesOverlap(dst, bytes, tmp, scratchBytes) ||
      frameRangesOverlap(src, bytes, tmp, scratchBytes)) return false;
  for (size_t y = 0; y < rows; ++y) {
    memcpy(scratch, source + y * rowBytes, rowBytes);
    if(percent != 100)for(size_t x=0;x<rowBytes/4;++x) {
      const uint32_t p=scratch[x];
      scratch[x]=uint32_t(dimRgb565(uint16_t(p),percent)) |
                 (uint32_t(dimRgb565(uint16_t(p>>16),percent))<<16);
    }
    memcpy(destination + y * rowBytes, scratch, rowBytes);
    const volatile uint32_t *readback =
        reinterpret_cast<const volatile uint32_t *>(destination + y * rowBytes);
    for (size_t x = 0; x < rowBytes / sizeof(uint32_t); ++x)
      if (readback[x] != scratch[x]) return false;
  }
  return true;
}

// Each inactive buffer can be one frame behind. Track pending rows for BOTH
// buffers; copying only the current dirty rectangle would resurrect old pixels.
struct PendingFrameRows {
  size_t height;
  size_t top[2];
  size_t bottom[2]; // exclusive
  explicit PendingFrameRows(size_t h) : height(h), top{0,0}, bottom{h,h} {}
  bool mark(size_t first, size_t end) {
    if (first >= end || end > height) return false;
    for (unsigned i = 0; i < 2; ++i) {
      if (first < top[i]) top[i] = first;
      if (end > bottom[i]) bottom[i] = end;
    }
    return true;
  }
  void copied(unsigned i) { top[i] = height; bottom[i] = 0; }
};

// Waiting for two fresh completed-frame events after requesting the switch
// conservatively covers an interrupt already in flight at the hand-off.
inline bool frameReleaseObserved(uint32_t now, uint32_t afterSwitch) {
  return uint32_t(now - afterSwitch) >= 2;
}

} // namespace ws43b
