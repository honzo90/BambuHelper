#pragma once
#include <stdint.h>

namespace ws43b_dusk {
// Color level for the panel, from darkest to brightest rule:
// - night hours (manual schedule) after the night timeout: 30% clock dim;
// - dark outside (solar night) but outside the night hours: 50% dusk dim;
// - otherwise full colors.
// `ready` is false in AP mode or without a configured printer.
inline uint8_t colorPercent(bool ready,bool nightHours,bool nightTimedOut,bool solarNight) {
  if(!ready)return 100;
  if(nightHours)return nightTimedOut?30:100;
  return solarNight?50:100;
}
}
