#pragma once
#include <stdint.h>
#include <math.h>

namespace ws43b_water {
// Pure geometry: 0/100 are exact endpoints; unknown is never shown as 0%.
inline int surface(int progress, bool valid, int x, uint32_t now) {
  if (!valid || progress <= 0) return 480;
  if (progress >= 100) return 0;
  const float phase = float(now % 12000u) * (6.2831853f / 12000.0f);
  const int amplitude = progress < 2 || progress > 98 ? 2 : 5;
  const int y = 480 - (480 * progress / 100) +
      int(amplitude * sinf(float(x) * (6.2831853f / 400.0f) + phase));
  return y < 0 ? 0 : y > 480 ? 480 : y;
}
inline int hour(int h, bool use24h) { return use24h ? h : (h % 12 ? h % 12 : 12); }
}
