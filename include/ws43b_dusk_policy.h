#pragma once
#include <stdint.h>

namespace ws43b_dusk {
// Color level for the panel, from darkest to brightest rule:
// - night hours (manual schedule) after the night timeout: 30% clock dim;
// - dark outside (solar night) but outside the night hours: 50% dusk dim
//   after the same no-touch timeout; a touch restores full colors;
// - otherwise full colors.
// `idleTimedOut` is true once the night no-touch timeout has passed since the
// last touch. `ready` is false in AP mode or without a configured printer.
inline uint8_t colorPercent(bool ready,bool nightHours,bool idleTimedOut,bool solarNight) {
  if(!ready || !idleTimedOut)return 100;
  if(nightHours)return 30;
  return solarNight?50:100;
}

// Dimming fades smoothly; brightening (a touch) is immediate. A stepped
// brighten collided with the touch repaint (navigation reveal) and stuttered.
constexpr uint8_t kFadeDownStep=5;      // percent per step
constexpr uint32_t kFadeDownMs=120;     // 100 -> 50 in about 1.2 s

// Next shown level on the way from `shown` to `target`; never overshoots.
inline uint8_t fadeStep(uint8_t shown,uint8_t target) {
  if(shown<target)return target;
  if(shown>target)return uint8_t(shown-target<=kFadeDownStep?target:shown-kFadeDownStep);
  return shown;
}
inline uint32_t fadeIntervalMs(uint8_t shown,uint8_t target) {
  return shown<target?0:kFadeDownMs;
}
}
