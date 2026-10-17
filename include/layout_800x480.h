#pragma once

// Native landscape ST7262. Legacy screen helpers still need their LY_* names
// at compile time; the dedicated monitor renderer below owns actual geometry.
// These are UI constants only, never hardware pins/timings or panel config.
#include "layout_480x480.h"
#undef LY_W
#define LY_W 800
#undef LY_BAR_W
#define LY_BAR_W 752

// Pong shares the bottom navigation with the native 800x480 renderer. Keep
// its paddle above y=433 and center the brick field across the actual width.
#undef LY_ARK_COLS
#define LY_ARK_COLS 13
#undef LY_ARK_START_X
#define LY_ARK_START_X 90
#undef LY_ARK_PADDLE_Y
#define LY_ARK_PADDLE_Y 416
#undef LY_ARK_PADDLE_W
#define LY_ARK_PADDLE_W 96
#undef LY_ARK_DATE_CLR_X
#define LY_ARK_DATE_CLR_X 0
#undef LY_ARK_DATE_CLR_W
#define LY_ARK_DATE_CLR_W 800


// Compile-time compatibility for shared legacy AMS helper definitions. The
// WS43B dispatcher never calls those screens; its actual cards use the
// geometry below. Keep placeholders bounded to this native landscape canvas.
#define LY_AMS_Y 294
#define LY_AMS_H 142
#define LY_AMS_BAR_H 62
#define LY_AMS_BAR_GAP 12
#define LY_AMS_GROUP_GAP 16
#define LY_AMS_LABEL_OFFY 4
#define LY_AMS_MARGIN 24
#define LY_AMS_BAR_MAX_W 169
#define LY_AMS_BAR_MAX_W_EXTRAS 169

namespace ws43b_layout {
constexpr int width = 800, height = 480, margin = 24;
constexpr int mainY = 86, progressW = 480, mainH = 190;
constexpr int tempX = 520, tempW = 256, tempH = 89;
constexpr int amsY = 294, amsH = 142, contentW = 752;
constexpr int trayY = 360, trayW = 169, trayH = 62, trayGap = 12;
static_assert(tempX + tempW == width - margin, "temperature card bounds");
static_assert(margin * 2 + contentW == width, "dashboard margins");
static_assert(amsY + amsH < height, "AMS bounds");
}
