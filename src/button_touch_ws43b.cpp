#include "button_touch_backend.h"

#if defined(BOARD_IS_WS43B) && defined(USE_GT911)

#include "ws43b_hardware.h"
#include "display_ws43b.h"

void touchInit() {
  // The display already initialized the exact 4.3B BSP, including GT911 reset
  // via CH422G. Reinitializing Wire here would conflict with the BSP I2C host.
  if (!ws43b::ready()) ws43b::fatal("TOUCH_BEFORE_DISPLAY");
  Serial.println("WS43B_TOUCH_READY driver=GT911 coordinates=800x480");
}

TouchPoll touchPoll() {
  uint16_t x = 0, y = 0;
  bool down = false;
  if (!ws43b::readTouch(x, y, down)) {
    cancelWs43bMonitorTouch();
    return {TouchEvent::Unavailable, false};
  }
  handleWs43bMonitorTouch(x, y, down);
  return {TouchEvent::None, down};
}

#endif // BOARD_IS_WS43B && USE_GT911
