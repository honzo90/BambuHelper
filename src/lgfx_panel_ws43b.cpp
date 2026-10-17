#if defined(BOARD_IS_WS43B)

#include "lgfx_panel_ws43b.hpp"
#include "ws43b_frame_copy.h"
#include "ws43b_solid_fill.h"
#include <lgfx/v1/misc/common_function.hpp>
#include <Arduino.h>
#include <esp_display_panel.hpp>
#include <esp_arduino_version.h>
#include <esp_heap_caps.h>
#include <esp_psram.h>
#include <esp_lcd_panel_io.h>
#include <esp_lcd_panel_rgb.h>
#include <esp32s3/rom/cache.h>
#include <limits.h>
#include <string.h>

#ifndef BOARD_WAVESHARE_ESP32_S3_TOUCH_LCD_4_3_B
#error "WS43B requires the exact manufacturer 4.3-B profile"
#endif
#if ESP_ARDUINO_VERSION != ESP_ARDUINO_VERSION_VAL(3, 3, 11)
#error "WS43B uses the physically tested Arduino ESP32 3.3.11 toolchain"
#endif
#if !defined(CONFIG_SPIRAM_MODE_OCT) || CONFIG_SPIRAM_SPEED != 80
#error "WS43B requires OPI PSRAM at 80 MHz"
#endif
#if !defined(WS43B_EXPECT_DCACHE_LINE_BYTES) || CONFIG_ESP32S3_DATA_CACHE_LINE_SIZE != WS43B_EXPECT_DCACHE_LINE_BYTES
#error "WS43B requires the private SDK matching its expected DCache line size"
#endif

#ifndef WS43B_RGB_PCLK_HZ
#define WS43B_RGB_PCLK_HZ 16000000
#endif
static_assert(WS43B_RGB_PCLK_HZ == 12000000 || WS43B_RGB_PCLK_HZ == 14000000 ||
              WS43B_RGB_PCLK_HZ == 16000000, "Unsupported WS43B PCLK experiment");

namespace {
esp_panel::board::Board board;
esp_panel::drivers::LCD *lcd = nullptr;
esp_panel::drivers::Touch *touch = nullptr;
bool boardReady = false;
uint8_t colorPercent = 100;
uint32_t measuredDcacheLineBytes = 0;
lgfx::Panel_WS43B *diagnosticPanel = nullptr;
ws43b::RenderDiagnostics renderStats{};
bool monitorFrameReady = false;
uint32_t renderStartedUs = 0;
uint32_t touchErrors = 0;
bool touchDown = false;
uint16_t touchX = 0, touchY = 0;
uint32_t touchLastFrame = 0;
constexpr uint32_t TOUCH_STALE_MS = 1000;
constexpr uint32_t FRAME_RELEASE_TIMEOUT_MS = 250;
// Controlled RGB refill experiment: Espressif's RGB application note
// recommends >=20 lines against underrun. Two internal DMA buffers now use
// 64000 bytes instead of 32000. Keep the manufacturer's pins/timings intact.
constexpr uint32_t RGB_BOUNCE_PIXELS = 800 * 20;
static_assert((800 * 480) % RGB_BOUNCE_PIXELS == 0,
              "The IDF RGB bounce size must divide the complete frame");
// The bounce ISR and the Arduino loop share only this tiny internal-RAM state.
DRAM_ATTR portMUX_TYPE refreshMux = portMUX_INITIALIZER_UNLOCKED;
DRAM_ATTR volatile uint32_t refreshSequence = 0;
alignas(64) DRAM_ATTR uint32_t copyRow[800 * sizeof(uint16_t) / sizeof(uint32_t)];

bool IRAM_ATTR onFrameComplete(void *) {
  portENTER_CRITICAL_ISR(&refreshMux);
  ++refreshSequence;
  portEXIT_CRITICAL_ISR(&refreshMux);
  return false; // No task notification or allocation from the ISR.
}

uint32_t completedFrames() {
  portENTER_CRITICAL(&refreshMux);
  const uint32_t sequence = refreshSequence;
  portEXIT_CRITICAL(&refreshMux);
  return sequence;
}

void waitForFrameRelease(uint32_t afterSwitch) {
  const uint32_t started = millis();
  while (!ws43b::frameReleaseObserved(completedFrames(), afterSwitch)) {
    if (uint32_t(millis() - started) >= FRAME_RELEASE_TIMEOUT_MS)
      ws43b::fatal("FRAME_RELEASE_TIMEOUT");
    delay(1);
  }
}

void beginBoard() {
  if (boardReady) return;
  // Read the hardware state established by SDK startup; do not reconfigure a
  // live cache from setup(). A header-only/compiler-define override must fail.
  measuredDcacheLineBytes = Cache_Get_DCache_Line_Size();
  if (measuredDcacheLineBytes != WS43B_EXPECT_DCACHE_LINE_BYTES)
    ws43b::fatal("DCACHE_LINE_SIZE");
  if (!psramFound() || esp_psram_get_size() != 8 * 1024 * 1024)
    ws43b::fatal("PSRAM_EXPECTED_8M");
  if (ESP.getFlashChipSize() != 16 * 1024 * 1024)
    ws43b::fatal("FLASH_EXPECTED_16M");
  if (!board.init()) ws43b::fatal("BOARD_INIT");
  lcd = board.getLCD();
  touch = board.getTouch();
  if (!lcd || !touch || !board.getBacklight()) ws43b::fatal("BSP_COMPONENT_MISSING");
  if (lcd->getFrameWidth() != 800 || lcd->getFrameHeight() != 480)
    ws43b::fatal("WRONG_RESOLUTION");
  if (!lcd->getBus() || lcd->getBus()->getBasicAttributes().type != ESP_PANEL_BUS_TYPE_RGB)
    ws43b::fatal("RGB_BUS_REQUIRED");
  if (!lcd->configFrameBufferNumber(2)) ws43b::fatal("FRAMEBUFFER_CONFIG");
  auto *rgb = static_cast<esp_panel::drivers::BusRGB *>(lcd->getBus());
  // Configure before BSP bus init; only PCLK changes in the A/B experiment.
  if (!rgb->configRGB_FreqHz(WS43B_RGB_PCLK_HZ)) ws43b::fatal("PCLK_CONFIG");
  if (!rgb->configRGB_BounceBufferSize(RGB_BOUNCE_PIXELS)) ws43b::fatal("BOUNCE_CONFIG");
  if (!board.begin()) ws43b::fatal("BOARD_BEGIN");
  // BSP 1.0.0 on IDF 5.5.5 maps this to on_frame_buf_complete, which is a
  // buffer-release event. A generic VSYNC event is not equivalent here.
  if (!lcd->attachRefreshFinishCallback(onFrameComplete)) ws43b::fatal("FRAME_CALLBACK");
  if (lcd->getFrameColorBits() != 16) ws43b::fatal("FRAMEBUFFER_NOT_RGB565");
  if (!touch->getBus() || !touch->getBus()->getControlPanelHandle())
    ws43b::fatal("TOUCH_BUS_MISSING");
  if (!heap_caps_check_integrity_all(false)) ws43b::fatal("HEAP_INTEGRITY");
  boardReady = true;
}
}

namespace ws43b {
bool setColorPercent(uint8_t percent) {
  if(percent>100)percent=100;
  const bool changed=colorPercent!=percent;colorPercent=percent;return changed;
}

bool ready() { return boardReady; }
uint32_t bounceBufferPixels() { return boardReady ? RGB_BOUNCE_PIXELS : 0; }
uint32_t requestedPclkHz() { return boardReady ? WS43B_RGB_PCLK_HZ : 0; }
uint32_t dcacheLineBytes() { return measuredDcacheLineBytes; }
uint32_t touchErrorCount() { return touchErrors; }

void beginRenderDiagnostics(bool fullRedraw) {
  monitorFrameReady = false;
  renderStartedUs = micros();
  if (diagnosticPanel && fullRedraw) diagnosticPanel->probeLegacyFill();
}

void endRenderDiagnostics(bool monitorFrame) {
  renderStats.lastRenderUs = uint32_t(micros() - renderStartedUs);
  if (renderStats.lastRenderUs > renderStats.maxRenderUs)
    renderStats.maxRenderUs = renderStats.lastRenderUs;
  ++renderStats.frames;
  monitorFrameReady = monitorFrame;
}

RenderDiagnostics renderDiagnostics() { return renderStats; }

bool frameCaptureInfo(FrameCaptureInfo &info) {
  return monitorFrameReady && diagnosticPanel && diagnosticPanel->captureInfo(info);
}

bool readFrameCaptureRow(size_t row, uint8_t *out, size_t capacity) {
  return monitorFrameReady && diagnosticPanel && diagnosticPanel->captureRow(row, out, capacity);
}

[[noreturn]] void fatal(const char *reason) {
  if (boardReady && board.getBacklight()) board.getBacklight()->off();
  boardReady = false;
  // Stop in place, without a reboot loop or falling back to another board.
  for (;;) {
    Serial.printf("WS43B_FATAL reason=%s\n", reason);
    delay(1000);
  }
}

static bool otaDisplayLocked=false;
static uint8_t requestedBacklight=255;
bool otaDisplayActive(){return otaDisplayLocked;}
bool beginOtaDisplay() {
  if(otaDisplayLocked || !boardReady)return false;
  if(!board.getBacklight()->off())return false;
  otaDisplayLocked=true;return true;
}
void endOtaDisplay() {
  if(!otaDisplayLocked)return;
  // Flash writes can desynchronise RGB DMA. Resynchronise before relighting.
  if(lcd) {
    esp_lcd_rgb_panel_restart(lcd->getRefreshPanelHandle());
    delay(100);
  }
  otaDisplayLocked=false;
  setBacklight(requestedBacklight);
}
bool setBacklight(uint8_t brightness) {
  requestedBacklight=brightness;
  if(otaDisplayLocked)return true;
  if (!boardReady) return false;
  return brightness ? board.getBacklight()->on() : board.getBacklight()->off();
}

bool readTouch(uint16_t &x, uint16_t &y, bool &down) {
  if (otaDisplayLocked || !boardReady || !touch) return false;
  // The BSP readPoints() API returns zero both for a release and between
  // reports. Check GT911's data-ready bit through its existing BSP I2C handle
  // so button.cpp receives a stable level, not a series of false releases.
  // This reads no coordinates directly and does not reset/reconfigure GT911.
  uint8_t status = 0;
  if (esp_lcd_panel_io_rx_param(touch->getBus()->getControlPanelHandle(),
                               0x814E, &status, sizeof(status)) != ESP_OK) {
    ++touchErrors;
    return false;
  }
  if (status & 0x80) {
    esp_panel::drivers::TouchPoint points[5];
    const int count = touch->readPoints(points, 5, 0);
    if (count < 0 || count > 5 || (status & 0x0F) > 5) {
      ++touchErrors;
      return false;
    }
    for (int i = 0; i < count; ++i) {
      if (points[i].x < 0 || points[i].x >= 800 || points[i].y < 0 || points[i].y >= 480) {
        ++touchErrors;
        return false;
      }
    }
    touchDown = count > 0;
    if (touchDown) {
      touchX = points[0].x;
      touchY = points[0].y;
    }
    touchLastFrame = millis();
  } else if (touchDown && uint32_t(millis() - touchLastFrame) > TOUCH_STALE_MS) {
    // A stopped controller must not latch an indefinitely held button.
    touchDown = false;
    return false; // Unavailable, never a release confirming a destructive hold.
  }
  x = touchX;
  y = touchY;
  down = touchDown;
  return true;
}
}

namespace lgfx {
inline namespace v1 {

Panel_WS43B::Panel_WS43B() {
  _cfg.memory_width = _cfg.panel_width = WIDTH;
  _cfg.memory_height = _cfg.panel_height = HEIGHT;
  _cfg.offset_rotation = 0;
  _cfg.pin_cs = _cfg.pin_rst = _cfg.pin_busy = -1;
  _cfg.readable = true; // Reads come from the owned canvas, not the LCD bus.
  _cfg.bus_shared = false;
  _cfg.rgb_order = false;
  setColorDepth(color_depth_t::rgb565_nonswapped);
}

color_depth_t Panel_WS43B::setColorDepth(color_depth_t) {
  // Unlike an SPI byte stream, the RGB BSP consumes native uint16_t RGB565.
  _write_depth = _read_depth = color_depth_t::rgb565_nonswapped;
  return _write_depth;
}

bool Panel_WS43B::guardsIntact() const {
  if (!_allocation) return false;
  for (size_t i = 0; i < GUARD; ++i) {
    if (_allocation[i] != 0xA5 || _canvas[CANVAS_BYTES + i] != 0x5A) return false;
  }
  return true;
}

bool Panel_WS43B::init(bool) {
  if (_initialized) return true;
  if (!psramFound() || esp_psram_get_size() != 8 * 1024 * 1024)
    ws43b::fatal("PSRAM_EXPECTED_8M");
  _allocation = static_cast<uint8_t *>(heap_caps_malloc(
      CANVAS_BYTES + 2 * GUARD, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  if (!_allocation) ws43b::fatal("CANVAS_ALLOC");
  _canvas = _allocation + GUARD;
  memset(_allocation, 0xA5, GUARD);
  memset(_canvas + CANVAS_BYTES, 0x5A, GUARD);
  // Full allocation pattern/readback before starting the display driver.
  auto *probe = reinterpret_cast<volatile uint32_t *>(_canvas);
  for (size_t i = 0; i < CANVAS_BYTES / 4; ++i) probe[i] = 0xa55a1234u ^ uint32_t(i);
  for (size_t i = 0; i < CANVAS_BYTES / 4; ++i)
    if (probe[i] != (0xa55a1234u ^ uint32_t(i))) ws43b::fatal("CANVAS_PATTERN");
  memset(_canvas, 0, CANVAS_BYTES);
  for (int y = 0; y < HEIGHT; ++y) _rows[y] = _canvas + y * WIDTH * sizeof(uint16_t);
  _lines_buffer = _rows;
  beginBoard();
  _scanout[0] = static_cast<uint8_t *>(lcd->getFrameBufferByIndex(0));
  _scanout[1] = static_cast<uint8_t *>(lcd->getFrameBufferByIndex(1));
  if (!_scanout[0] || !_scanout[1] || _scanout[0] == _scanout[1])
    ws43b::fatal("FRAMEBUFFER_POINTERS");
  _auto_display = true;
  _range_mod.top = _range_mod.left = INT16_MAX;
  _range_mod.right = _range_mod.bottom = 0;
  Panel_FrameBufferBase::setRotation(0);
  _initialized = true;
  display(0, 0, WIDTH, HEIGHT);
  diagnosticPanel = this;
  Serial.printf("WS43B_PANEL_READY width=800 height=480 rgb565=1 rgb_framebuffers=2 bounce_pixels=%lu dcache_line_bytes=%lu copy_readback=1 release_events=2 solid_fill=volatile16 diag_version=5\n",
                static_cast<unsigned long>(ws43b::bounceBufferPixels()),
                static_cast<unsigned long>(ws43b::dcacheLineBytes()));
  return true;
}

void Panel_WS43B::writeFillRectPreclipped(uint_fast16_t x, uint_fast16_t y,
                                         uint_fast16_t w, uint_fast16_t h,
                                         uint32_t rawcolor) {
  if (!w || !h) return;
  if (!_canvas || _write_bits != 16 || x >= _width || y >= _height ||
      w > uint_fast16_t(_width - x) || h > uint_fast16_t(_height - y))
    ws43b::fatal("SOLID_FILL_BOUNDS");
  // Match Panel_FrameBufferBase's logical-to-physical rotation exactly.
  const uint_fast8_t r = _internal_rotation;
  if (r) {
    if ((1u << r) & 0b10010110) y = _height - (y + h);
    if (r & 2) x = _width - (x + w);
    if (r & 1) { std::swap(x, y); std::swap(w, h); }
  }
  if (!ws43b::fillSolidRectChecked(reinterpret_cast<uint16_t *>(_canvas),
                                 WIDTH, HEIGHT, x, y, w, h, uint16_t(rawcolor))) {
    ++renderStats.fillReadbackErrors;
    ws43b::fatal("SOLID_FILL_READBACK");
  }
  _range_mod.left = std::min<int_fast16_t>(_range_mod.left, x);
  _range_mod.right = std::max<int_fast16_t>(_range_mod.right, x + w - 1);
  _range_mod.top = std::min<int_fast16_t>(_range_mod.top, y);
  _range_mod.bottom = std::max<int_fast16_t>(_range_mod.bottom, y + h - 1);
}

void Panel_WS43B::probeLegacyFill() {
  if (!_initialized || !guardsIntact()) ws43b::fatal("FILL_PROBE_STATE");
  constexpr uint16_t colors[] = {0x0843, 0x10C5, 0xF7BE, 0x4EFD};
  const uint32_t index = renderStats.legacyFillProbes++;
  const uint16_t color = colors[index & 3];
  const size_t offset = index & 1; // Exercise both 4-byte aligned and +2 fills.
  auto *row = reinterpret_cast<uint16_t *>(_canvas) + offset;
  const size_t count = WIDTH - offset;
  // The canvas is not a driver framebuffer. beginRenderDiagnostics is called
  // inside startWrite BEFORE fillScreen, which overwrites this entire row.
  // This intentionally retains the old operation solely as a diagnostic probe.
  memset_multi(reinterpret_cast<uint8_t *>(row), color, sizeof(uint16_t), count);
  const volatile uint16_t *check = row;
  for (size_t i = 0; i < count; ++i) {
    if (check[i] != color) {
      ++renderStats.legacyFillMismatches; // Failed probes, not pixel count.
      break;
    }
  }
}

void Panel_WS43B::setBrightness(uint8_t brightness) {
  if (!ws43b::setBacklight(brightness)) ws43b::fatal("BACKLIGHT");
}

bool Panel_WS43B::captureInfo(ws43b::FrameCaptureInfo &info) const {
  if (!_initialized || !ws43b::ready() || !guardsIntact()) return false;
  info = {renderStats.frames, millis(), uint32_t(_backIndex ^ 1), uint32_t(esp_reset_reason())};
  return true;
}

bool Panel_WS43B::captureRow(size_t row, uint8_t *out, size_t capacity) const {
  if (!_initialized || !ws43b::ready() || !guardsIntact()) return false;
  // display() has already waited for release and flipped _backIndex. The
  // driver only reads this front; no renderer runs during this HTTP handler.
  return ws43b::captureRow(reinterpret_cast<const volatile uint16_t *>(_canvas),
                           reinterpret_cast<const volatile uint16_t *>(_scanout[_backIndex ^ 1]),
                           row, out, capacity);
}

void Panel_WS43B::display(uint_fast16_t x, uint_fast16_t y,
                         uint_fast16_t w, uint_fast16_t h) {
  if (!_initialized || !ws43b::ready()) ws43b::fatal("DISPLAY_BEFORE_INIT");
  if (!guardsIntact()) ws43b::fatal("CANVAS_GUARD");
  if (w > 0 && h > 0) {
    const uint_fast8_t r = _internal_rotation;
    if ((1u << r) & 0b10010110) y = _height - (y + h);
    if (r & 2) x = _width - (x + w);
    if (r & 1) { std::swap(x, y); std::swap(w, h); }
    _range_mod.left = std::min<int_fast16_t>(_range_mod.left, x);
    _range_mod.right = std::max<int_fast16_t>(_range_mod.right, x + w - 1);
    _range_mod.top = std::min<int_fast16_t>(_range_mod.top, y);
    _range_mod.bottom = std::max<int_fast16_t>(_range_mod.bottom, y + h - 1);
  }
  if(_presentedPercent != colorPercent) {
    _presentedPercent=colorPercent;
    _pendingRows.mark(0,HEIGHT); // Both alternating buffers need the new level.
    _range_mod.left=0;_range_mod.right=WIDTH-1;
    _range_mod.top=0;_range_mod.bottom=HEIGHT-1;
  }
  if (_range_mod.empty()) return;
  if (_range_mod.left < 0 || _range_mod.right >= WIDTH ||
      _range_mod.top < 0 || _range_mod.bottom >= HEIGHT) ws43b::fatal("DIRTY_RANGE");
  // Refresh all rows changed since this particular back buffer was current.
  // Untouched rows already match the canvas, including across alternating frames.
  if (!_pendingRows.mark(_range_mod.top, _range_mod.bottom + 1))
    ws43b::fatal("DIRTY_ROWS");
  uint8_t *back = _scanout[_backIndex];
  const size_t first = _pendingRows.top[_backIndex];
  const size_t rows = _pendingRows.bottom[_backIndex] - first;
  const size_t offset = first * WIDTH * sizeof(uint16_t);
  if (!ws43b::copyFrameChecked(back + offset, _canvas + offset, copyRow, sizeof(copyRow),
                              WIDTH * sizeof(uint16_t), rows, colorPercent))
    ws43b::fatal("FRAME_COPY_READBACK");
  _pendingRows.copied(_backIndex);
  if (!guardsIntact()) ws43b::fatal("CANVAS_GUARD");
  if (!lcd->switchFrameBufferTo(back)) ws43b::fatal("FRAME_SWITCH");
  const uint32_t afterSwitch = completedFrames();
  waitForFrameRelease(afterSwitch);
  // Neither the new front nor the previous front is written during the wait.
  _backIndex ^= 1;
  _range_mod.top = _range_mod.left = INT16_MAX;
  _range_mod.right = _range_mod.bottom = 0;
}

} // namespace v1
} // namespace lgfx

#endif // BOARD_IS_WS43B
