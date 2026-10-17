#pragma once
#include <stdint.h>
namespace ws43b_weather {
// Poll prerequisites cheaply; network requests remain bounded and backed off.
struct FetchSchedule {
  bool attempted=false;
  uint8_t failures=0;
  uint32_t completedMs=0,intervalMs=0,revision=0;
  uint32_t waitMs(uint32_t now,uint32_t configRevision,bool ready) {
    if(configRevision!=revision) {revision=configRevision;intervalMs=20000;failures=0;}
    if(!ready)return 1000;
    if(!attempted)return 0;
    const uint32_t elapsed=now-completedMs;
    if(elapsed>=intervalMs)return 0;
    const uint32_t remaining=intervalMs-elapsed;
    return remaining<1000?remaining:1000;
  }
  void completed(uint32_t now,bool success) {
    attempted=true;completedMs=now;
    if(success){failures=0;intervalMs=600000;return;}
    if(failures<4)++failures;
    const uint32_t retry[]={20000,60000,180000,300000};
    intervalMs=retry[failures-1];
  }
};
}
