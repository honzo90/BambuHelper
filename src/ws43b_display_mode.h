#pragma once
#include <stdint.h>

#if defined(BOARD_IS_WS43B)
// One presentation choice shared by Print and the normal screensaver. It does
// not change clock/Pong, idle timers, telemetry or printer control settings.
bool ws43bAdvancedDisplay();
uint32_t ws43bDisplayModeRevision();
void loadWs43bDisplayMode();
bool saveWs43bDisplayMode(bool advanced);
#endif
