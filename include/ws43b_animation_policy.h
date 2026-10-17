#pragma once
#include <stdint.h>

namespace ws43b_animation {
struct Frame {
  bool activity=false;
  bool ambient=false;
};

// Keep the small, cached print head independent from weather/drying effects.
// Missed frames are dropped: never replay a backlog after a slow render or RX.
// Data redraws also reserve a quiet interval for I/O, even if they touched only
// another card. These are upper rate limits, not a guaranteed animation FPS.
class Cadence {
public:
  static constexpr uint32_t cachedHeadMs=50, ambientMs=84;
  Frame due(uint32_t now,uint32_t lastDataFrame,bool activity,bool ambient,
            bool cachedPrintHead) const {
    const uint32_t activityMs=cachedPrintHead?cachedHeadMs:ambientMs;
    return {activity && uint32_t(now-lastDataFrame)>=activityMs &&
                         uint32_t(now-lastActivity)>=activityMs,
            ambient && uint32_t(now-lastDataFrame)>=ambientMs &&
                       uint32_t(now-lastAmbient)>=ambientMs};
  }
  void mark(uint32_t now,Frame frame) {
    if(frame.activity)lastActivity=now;
    if(frame.ambient)lastAmbient=now;
  }
private:
  uint32_t lastActivity=0,lastAmbient=0;
};
} // namespace ws43b_animation
