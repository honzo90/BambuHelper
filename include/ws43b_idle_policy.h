#pragma once

#include <stdint.h>

namespace ws43b_view {

// Match the shared Pong renderer gate; otherwise selecting it can leave an
// old clock frame on screen because tickPongClock() returns without drawing.
inline bool pongAvailable(bool enabled, bool keepDisplayOn, bool showClock) {
  return enabled && !keepDisplayOn && showClock;
}


// The caller keeps setup visible until the panel is configured; printer
// telemetry does not control eligibility. Use the same monotonic millisecond
// clock as activity; uint32_t subtraction handles the clock crossing zero.
class IdlePolicy {
 public:
  bool update(uint32_t now, bool eligible, uint16_t idleMinutes,
              uint32_t settingsRevision) {
    if (!initialized_ || revision_ != settingsRevision || minutes_ != idleMinutes) {
      initialized_ = true;
      revision_ = settingsRevision;
      minutes_ = idleMinutes;
      tracking_ = false;
      expired_ = false;
    }

    if (!eligible || idleMinutes == 0) {
      tracking_ = false;
      expired_ = false;
      return false;
    }

    // Becoming eligible starts a complete interval, even after hours in setup
    // or disabled. Zero is a valid start time, not an unset sentinel.
    if (!tracking_) {
      tracking_ = true;
      since_ = now;
      return false;
    }

    if (!expired_ && uint32_t(now - since_) >= uint32_t(idleMinutes) * 60000u)
      expired_ = true;
    return expired_;
  }

  // User activity also wakes an already expired display. Activity received
  // while ineligible cannot make the next eligible interval shorter.
  void activity(uint32_t now) {
    if (tracking_) since_ = now;
    expired_ = false;
  }

 private:
  bool initialized_ = false;
  bool tracking_ = false;
  bool expired_ = false;
  uint16_t minutes_ = 0;
  uint32_t revision_ = 0;
  uint32_t since_ = 0;
};

} // namespace ws43b_view
