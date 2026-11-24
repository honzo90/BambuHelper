#pragma once
// Photo screensaver for the 4.3B: JPG/PNG files from /images on the TF card.
// Everything here is loop-task only (display, SD card and web server share it).
#if defined(BOARD_IS_WS43B)
#include <stdint.h>
#include "ws43b_photo_policy.h"

// The renderer guards its photo code with this, so host tests that compile
// slices of display_ws43b.cpp without this module keep working.
#define WS43B_PHOTO_SAVER 1

class WebServer;

const ws43b_photo::Settings &ws43bPhotoSettings();
void loadWs43bPhotoSettings();
bool saveWs43bPhotoSettings(const ws43b_photo::Settings &settings);

// Mounts the card when needed and decodes the next slide when it is due.
// True when a decoded slide is ready to show. Decoding blocks the loop for
// the decode time of one picture (measure: Serial "PHOTO decode" line).
bool ws43bPhotoPrepare(uint32_t now);
// Changes whenever a new slide was decoded.
uint32_t ws43bPhotoSlideRevision();
// Copy the slide (clipped to the rectangle) onto the canvas.
void ws43bPhotoPush(int x, int y, int w, int h);
// Copy the rectangle darkened with rounded corners, as a card background.
void ws43bPhotoDimmedCard(int x, int y, int w, int h);
// Frees the 768 KB PSRAM slide; called when the feature is turned off.
void ws43bPhotoRelease();

// GET/POST /monitor/photos, upload, delete and file preview.
void ws43bPhotoRegisterRoutes(WebServer &server);
#endif
