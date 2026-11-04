#pragma once
#include <stdint.h>

#if defined(BOARD_IS_WS43B)
// Independent Standard / Minimalist screen-layout choice. It is separate from
// the display-mode setting and does not touch clock/Pong, idle timers,
// telemetry or printer control settings.
bool ws43bMinimalLayout();
uint32_t ws43bLayoutRevision();
void loadWs43bLayout();
bool saveWs43bLayout(bool minimal);
#endif
