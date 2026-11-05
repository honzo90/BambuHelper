#pragma once
#include <stdint.h>
void renderWs43bMonitor(bool force);
bool ws43bVisibleDataNeedsRefresh(uint8_t slot,uint32_t now);
void drawWs43bBootScreen();
void tickWs43bBootScreen();
void handleWs43bMonitorTouch(uint16_t x, uint16_t y, bool down);
void cancelWs43bMonitorTouch();

#if WS43B_FULL_WEBUI
bool handleWs43bErrorTap(bool open);
void drawWs43bHmsScreen();
#endif
void beginWs43bErrorScreen(const char *printer);
void drawWs43bErrorCard(unsigned row,const char *label,const char *code,const char *description,uint16_t color);
void endWs43bErrorScreen(unsigned remaining);

#if defined(BOARD_IS_WS43B)
// Screensaver clock flip statistics (last finished flip).
uint16_t ws43bLastFlipFrames();
uint32_t ws43bLastFlipMs();
#endif
