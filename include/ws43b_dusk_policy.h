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
}
