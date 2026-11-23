#pragma once
// Photo screensaver policy for the 4.3B: file names, limits, image headers,
// scaling, settings record and slideshow timing. No hardware, no Arduino
// types, so the host tests can exercise every rule (test_photo_policy.py).
#include <stddef.h>
#include <stdint.h>

namespace ws43b_photo {

enum class Format : uint8_t { None, Jpeg, Png };

// Names live in a fixed PSRAM table: 200 x 48 bytes. Longer names are refused
// at upload rather than silently truncated on the card.
constexpr size_t kNameMax = 48;
constexpr unsigned kMaxFiles = 200;
// Decode time and SD read time grow with file size; the loop task decodes,
// so keep one slide well under a few seconds even at 4 MHz SPI.
constexpr uint32_t kMaxJpegBytes = 4u << 20;
constexpr uint32_t kMaxPngBytes = 2u << 20;
constexpr uint16_t kMaxSide = 4096;
constexpr uint16_t kScreenW = 800, kScreenH = 480;
constexpr uint16_t kIntervals[] = {10, 30, 60, 300};

inline char lower(char c) { return c >= 'A' && c <= 'Z' ? char(c - 'A' + 'a') : c; }

inline bool endsWith(const char *name, size_t length, const char *suffix) {
  size_t s = 0;
  while (suffix[s]) ++s;
  if (length <= s) return false;
  for (size_t i = 0; i < s; ++i)
    if (lower(name[length - s + i]) != suffix[i]) return false;
  return true;
}

inline Format format(const char *name) {
  if (!name) return Format::None;
  size_t length = 0;
  while (name[length]) ++length;
  if (endsWith(name, length, ".jpg") || endsWith(name, length, ".jpeg")) return Format::Jpeg;
  if (endsWith(name, length, ".png")) return Format::Png;
  return Format::None;
}

// A plain file name inside /images: no path separators, no hidden files, no
// "..", only characters that are safe in a URL query and on FAT.
inline bool safeName(const char *name) {
  if (!name || !name[0] || name[0] == '.' || name[0] == ' ') return false;
  size_t length = 0;
  for (; name[length]; ++length) {
    if (length + 1 >= kNameMax) return false;
    const char c = name[length];
    const bool ok = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') ||
                    c == '_' || c == '-' || c == '.' || c == ' ' || c == '(' || c == ')';
    if (!ok) return false;
    if (c == '.' && name[length + 1] == '.') return false;
  }
  return format(name) != Format::None;
}

inline bool sizeAllowed(Format f, uint32_t bytes) {
  if (!bytes) return false;
  return f == Format::Jpeg ? bytes <= kMaxJpegBytes : f == Format::Png ? bytes <= kMaxPngBytes : false;
}

inline bool dimensionsAllowed(uint16_t w, uint16_t h) {
  return w && h && w <= kMaxSide && h <= kMaxSide;
}

inline uint16_t be16(const uint8_t *p) { return uint16_t((p[0] << 8) | p[1]); }
inline uint32_t be32(const uint8_t *p) {
  return (uint32_t(p[0]) << 24) | (uint32_t(p[1]) << 16) | (uint32_t(p[2]) << 8) | p[3];
}

// read(offset, buffer, count) -> true only when all count bytes were read.
// JPEG: walk the marker segments to the first SOF (EXIF blocks can be tens of
// KB, so a fixed-size prefix is not enough). PNG: IHDR is always first.
template <class Read>
bool imageSize(Format f, Read read, uint32_t fileSize, uint16_t &w, uint16_t &h) {
  uint8_t b[24];
  if (f == Format::Png) {
    static constexpr uint8_t sig[8] = {0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A};
    if (fileSize < 24 || !read(0, b, 24)) return false;
    for (int i = 0; i < 8; ++i)
      if (b[i] != sig[i]) return false;
    if (b[12] != 'I' || b[13] != 'H' || b[14] != 'D' || b[15] != 'R') return false;
    const uint32_t pw = be32(b + 16), ph = be32(b + 20);
    if (pw > 0xFFFF || ph > 0xFFFF) return false;
    w = uint16_t(pw);
    h = uint16_t(ph);
    return true;
  }
  if (f != Format::Jpeg || fileSize < 4 || !read(0, b, 2) || b[0] != 0xFF || b[1] != 0xD8) return false;
  uint32_t offset = 2;
  for (int segments = 0; segments < 64 && offset + 4 <= fileSize; ++segments) {
    if (!read(offset, b, 4) || b[0] != 0xFF) return false;
    if (b[1] == 0xFF) { ++offset; continue; }  // fill byte before a marker
    const uint8_t marker = b[1];
    const uint16_t length = be16(b + 2);
    if (marker == 0xD9 || marker == 0xDA || length < 2) return false;  // EOI/SOS before SOF
    const bool sof = marker >= 0xC0 && marker <= 0xCF && marker != 0xC4 && marker != 0xC8 &&
                     marker != 0xCC;
    if (sof) {
      if (offset + 9 > fileSize || !read(offset, b, 9)) return false;
      h = be16(b + 5);
      w = be16(b + 7);
      return w && h;
    }
    offset += 2u + length;
  }
  return false;
}

// Zoom for LovyanGFX drawJpg/drawPng (centred in 800x480). Fit shows the whole
// picture; fill covers the screen and crops. Small pictures are enlarged at
// most 2x, beyond that they only get blurrier.
inline float zoom(uint16_t w, uint16_t h, bool fill) {
  if (!w || !h) return 1.0f;
  const float zx = float(kScreenW) / w, zy = float(kScreenH) / h;
  float z = fill ? (zx > zy ? zx : zy) : (zx < zy ? zx : zy);
  return z > 2.0f ? 2.0f : z;
}

struct Settings {
  bool enabled = false;
  uint8_t interval = 1;  // index into kIntervals
  uint8_t corner = 0;    // 0 bottom-right, 1 bottom-left, 2 top-right, 3 top-left
  bool fill = false;
};

// One versioned NVS record ("w43_photo"), like the clock settings.
inline uint16_t encode(const Settings &s) {
  return uint16_t(0x0200 | (s.enabled ? 1 : 0) | ((s.interval & 3) << 1) | ((s.corner & 3) << 3) |
                  (s.fill ? 32 : 0));
}
inline bool decode(uint16_t value, Settings &s) {
  if ((value & 0xFFC0) != 0x0200) return false;
  s.enabled = value & 1;
  s.interval = (value >> 1) & 3;
  s.corner = (value >> 3) & 3;
  s.fill = (value & 32) != 0;
  return true;
}
inline int intervalIndex(unsigned seconds) {
  for (int i = 0; i < 4; ++i)
    if (kIntervals[i] == seconds) return i;
  return -1;
}

struct Slideshow {
  uint16_t index = 0;
  uint32_t shownMs = 0;
  bool started = false;
  bool due(uint32_t now, uint16_t seconds) const {
    return !started || uint32_t(now - shownMs) >= uint32_t(seconds) * 1000u;
  }
  // The next file to try; wraps, and stays valid when the list shrinks.
  uint16_t next(uint16_t count) {
    if (!count) return index = 0;
    index = started ? uint16_t((index + 1) % count) : uint16_t(index % count);
    return index;
  }
  void shown(uint32_t now) {
    started = true;
    shownMs = now;
  }
};

struct Rect {
  int x, y, w, h;
};
// Clock card over the photo; taller while a print is shown.
inline Rect card(uint8_t corner, bool printing) {
  const int w = printing ? 300 : 250, h = printing ? 124 : 96, m = 24;
  const bool right = (corner & 1) == 0, bottom = corner < 2;
  return {right ? kScreenW - m - w : m, bottom ? kScreenH - m - h : m, w, h};
}

// Darken a native RGB565 pixel towards the panel's background (9,19,30) so
// white text stays readable on any photo. amount 0..256.
inline uint16_t dim(uint16_t c, unsigned amount) {
  const unsigned r = (c >> 11) & 31, g = (c >> 5) & 63, b = c & 31;
  const unsigned br = 9 >> 3, bg = 19 >> 2, bb = 30 >> 3;
  const unsigned keep = 256 - amount;
  return uint16_t((((r * keep + br * amount) >> 8) << 11) | (((g * keep + bg * amount) >> 8) << 5) |
                  ((b * keep + bb * amount) >> 8));
}
// Rounded card corners: true when (x,y) inside a w x h card lies inside the
// rounded shape of radius r.
inline bool insideRounded(int x, int y, int w, int h, int r) {
  const int cx = x < r ? r : x >= w - r ? w - r - 1 : x;
  const int cy = y < r ? r : y >= h - r ? h - r - 1 : y;
  const int dx = x - cx, dy = y - cy;
  return dx * dx + dy * dy <= r * r;
}

}  // namespace ws43b_photo
