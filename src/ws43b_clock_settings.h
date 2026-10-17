#pragma once
#include <stdint.h>

#if defined(BOARD_IS_WS43B)
struct Ws43bClockSettings {
  uint16_t idleMinutes = 0;
  bool screenOff = false;
  bool use24h = true;
  uint32_t revision = 0;
};

const Ws43bClockSettings& ws43bClockSettings();
void loadWs43bClockSettings();
bool saveWs43bClockSettings(uint16_t idleMinutes, bool screenOff, bool use24h);
#endif
