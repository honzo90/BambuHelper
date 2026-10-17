#pragma once

#include <LovyanGFX.hpp>
#include <lgfx/v1/panel/Panel_FrameBufferBase.hpp>
#include "ws43b_hardware.h"
#include "ws43b_frame_copy.h"

// Keep LovyanGFX's clipping, text, sprite and image conversion paths. RGB DMA,
// bounce buffering, GT911 reset and CH422G remain owned by the same BSP as the
// physically passed bringup/waveshare43b/smoke. No LovyanGFX Bus_RGB is used.
namespace lgfx {
inline namespace v1 {

class Panel_WS43B : public Panel_FrameBufferBase {
public:
  Panel_WS43B();
  bool init(bool use_reset) override;
  void initBus() override {}
  void releaseBus() override {}
  void writeCommand(uint32_t, uint_fast8_t) override {}
  void writeData(uint32_t, uint_fast8_t) override {}
  void setBrightness(uint8_t brightness) override;
  color_depth_t setColorDepth(color_depth_t) override;
  void writeFillRectPreclipped(uint_fast16_t x, uint_fast16_t y,
                              uint_fast16_t w, uint_fast16_t h,
                              uint32_t rawcolor) override;
  void display(uint_fast16_t x, uint_fast16_t y,
               uint_fast16_t w, uint_fast16_t h) override;
  // One hidden row of the canvas is probed before a full redraw, never sent
  // to the LCD. This diagnoses the legacy fill without exposing image data.
  void probeLegacyFill();
  bool captureInfo(ws43b::FrameCaptureInfo &info) const;
  bool captureRow(size_t row, uint8_t *out, size_t capacity) const;

private:
  static constexpr int WIDTH = 800;
  static constexpr int HEIGHT = 480;
  static constexpr size_t GUARD = 64;
  static constexpr size_t CANVAS_BYTES = WIDTH * HEIGHT * sizeof(uint16_t);
  uint8_t *_allocation = nullptr;
  uint8_t *_canvas = nullptr;
  uint8_t *_rows[HEIGHT] = {};
  uint8_t *_scanout[2] = {};
  ws43b::PendingFrameRows _pendingRows{HEIGHT};
  uint8_t _presentedPercent = 100;
  uint8_t _backIndex = 1; // IDF starts both cur_fb_index and bb_fb_index at zero.
  bool _initialized = false;
  bool guardsIntact() const;
};

} // namespace v1
} // namespace lgfx
