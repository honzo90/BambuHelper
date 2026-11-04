#pragma once
#include <stdint.h>
#include <string.h>

// Calendar-page flip of the screensaver clock digits ("HH:MM").
// Only characters that differ move: the old one drops down and fades out,
// the new one slides in from above and fades in. Pure logic, host-testable.
namespace ws43b_clock_flip {

constexpr uint32_t kDurationMs = 1100;  // a calm page turn
constexpr uint32_t kFrameMs = 40;       // ~25 fps while flipping (panel refresh limit)
constexpr int kTravel = 70;             // px the digits move (band is ~140 px tall)
constexpr unsigned kTextMax = 8;

struct Flip {
  char from[kTextMax] = {};
  char to[kTextMax] = {};
  uint32_t start = 0;
  bool active = false;
};

inline void begin(Flip &f, const char *from, const char *to, uint32_t now) {
  strncpy(f.from, from, kTextMax - 1); f.from[kTextMax - 1] = 0;
  strncpy(f.to, to, kTextMax - 1); f.to[kTextMax - 1] = 0;
  f.start = now;
  f.active = strcmp(f.from, f.to) != 0 && strlen(f.from) == strlen(f.to);
}

inline void cancel(Flip &f) { f.active = false; }

// Progress 0..1000; ends the flip once the duration has elapsed.
inline unsigned progress(Flip &f, uint32_t now) {
  if (!f.active) return 1000;
  const uint32_t elapsed = now - f.start;
  if (elapsed >= kDurationMs) { f.active = false; return 1000; }
  return unsigned(elapsed * 1000u / kDurationMs);
}

inline bool changed(const Flip &f, unsigned i) {
  return f.active && i < kTextMax && f.from[i] != f.to[i];
}

// Old character: accelerates downward like a falling page (ease-in).
inline int oldOffset(unsigned p) { return int(int64_t(kTravel) * p * p / 1000000); }
// New character: decelerates into place from above (ease-out).
inline int newOffset(unsigned p) {
  const unsigned q = 1000 - p;
  return -int(int64_t(kTravel) * q * q / 1000000);
}
// Opacity 0..255: the old character fades out faster, the new one fades in.
inline unsigned oldAlpha(unsigned p) { return p >= 700 ? 0 : 255 - p * 255 / 700; }
inline unsigned newAlpha(unsigned p) { return p <= 250 ? 0 : (p - 250) * 255 / 750; }

}  // namespace ws43b_clock_flip
