#pragma once
#include <stdint.h>
#include <string.h>

// Calendar-page flip of the screensaver clock digits ("HH:MM").
// Only characters that differ move: the old one slides down out of its cell,
// the new one follows from above. Pure logic, host-testable.
namespace ws43b_clock_flip {

constexpr uint32_t kDurationMs = 1000;  // a calm page turn
constexpr uint32_t kFrameMs = 40;       // ~25 fps while flipping (panel refresh limit)
constexpr int kTravel = 120;            // > digit height: old and new never overlap
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

// Smooth start and stop (cubic ease-in-out), 0..1000.
inline unsigned ease(unsigned p) {
  if (p >= 1000) return 1000;
  if (p < 500) return unsigned(uint64_t(4) * p * p * p / 1000000);
  const uint64_t q = 1000 - p;
  return unsigned(1000 - uint64_t(4) * q * q * q / 1000000);
}
// Like a calendar page: the old digit moves down out of its cell while the new
// one follows from above, a constant kTravel apart, so they never overlap.
inline int oldOffset(unsigned p) { return int(int64_t(kTravel) * ease(p) / 1000); }
inline int newOffset(unsigned p) { return oldOffset(p) - kTravel; }

}  // namespace ws43b_clock_flip
