#pragma once

#include <stdint.h>
#include "ws43b_frame_capture.h"

// The display owns the manufacturer's BSP, I2C host and reset sequence.
// Only call these from the application loop; do not create a second Wire host.
namespace ws43b {
bool ready();
// Loop-only presentation scaling; true when changed. Backlight stays binary.
bool setColorPercent(uint8_t percent);
// Applied RGB bounce size, in pixels per buffer; zero before successful BSP init.
uint32_t bounceBufferPixels();
// Requested driver clock, not a physical measurement of the PCLK pin.
uint32_t requestedPclkHz();
// Actual ROM query before LCD init, not the compile-time sdkconfig value.
uint32_t dcacheLineBytes();
// CH422G is a switch, not a PWM dimmer: 0 = off, all other values = on.
bool setBacklight(uint8_t brightness);
// Main-loop OTA lifecycle: hide scanout while Flash writes disable caches.
bool beginOtaDisplay();
void endOtaDisplay();
bool otaDisplayActive();
// Coordinates are native landscape 800 x 480, exactly as in the passed smoke.
// false means unavailable/invalid data; callers must not treat it as a release.
bool readTouch(uint16_t &x, uint16_t &y, bool &down);
uint32_t touchErrorCount();
// CPU-side rendering diagnostics only; these do not certify LCD scanout.
struct RenderDiagnostics {
  uint32_t frames;
  uint32_t lastRenderUs;
  uint32_t maxRenderUs;
  uint32_t legacyFillProbes;
  uint32_t legacyFillMismatches;
  uint32_t fillReadbackErrors;
};
void beginRenderDiagnostics(bool fullRedraw = true);
void endRenderDiagnostics(bool monitorFrame);
RenderDiagnostics renderDiagnostics();
// Both are loop-only: the synchronous HTTP handler must finish before the
// next redraw. Setup/provisioning frames are never available for capture.
bool frameCaptureInfo(FrameCaptureInfo &info);
bool readFrameCaptureRow(size_t row, uint8_t *out, size_t capacity);
[[noreturn]] void fatal(const char *reason);
}
