#pragma once
#include <stdint.h>
#include "bambu_monitor.h"
namespace ws43b_view {
enum class Thermal { Unknown, Stable, Heating, Cooling };
// Per-printer channel, with hysteresis and a five-second candidate dwell.
struct ThermalPolicy {
  Thermal state=Thermal::Unknown, candidate=Thermal::Unknown;
  uint32_t since=0, lastFall=0; float previous=0; bool seen=false, falling=false;
  Thermal update(uint32_t now, bool fresh, float actual, bool targetFresh, float target) {
    if (!fresh) { state=candidate=Thermal::Unknown; seen=falling=false; return state; }
    if (seen && actual <= previous-0.5f) { lastFall=now; falling=true; previous=actual; }
    if (!seen || actual >= previous+0.5f) previous=actual;
    seen=true;
    Thermal desired=Thermal::Stable;
    if (targetFresh && target>0) {
      if(actual<target-2 || (state==Thermal::Heating && actual<target-1)) desired=Thermal::Heating;
      else if(actual>target+3 || (state==Thermal::Cooling && actual>target+1)) desired=Thermal::Cooling;
    } else if(targetFresh && falling && uint32_t(now-lastFall)<90000) desired=Thermal::Cooling;
    if(desired!=candidate) { candidate=desired; since=now; }
    if(uint32_t(now-since)>=5000) state=candidate;
    return state;
  }
};
// A display hint, not a printer FINISH event or a safe-removal temperature.
struct FinishCoolingPolicy {
  bool seen=false,falling=false;float previous=0;uint32_t lastFall=0,session=0;
  bool update(const BambuMonitorTelemetry &m,bool online,uint32_t now) {
    const bool lastLayer=m.layerNum.current(now) && m.totalLayers.current(now) &&
      m.totalLayers.value>0 && m.layerNum.value>=m.totalLayers.value;
    const bool finishing=m.progress.current(now) && m.progress.value>=98 && m.progress.value<=100 &&
      m.nozzleTarget.current(now) && m.nozzleTarget.value==0;
    const bool eligible=online && m.status.current(now) &&
      (!strcmp(m.status.value,"RUNNING") || !strcmp(m.status.value,"FINISH")) &&
      (lastLayer || finishing) && m.bedTemp.current(now) &&
      m.bedTarget.current(now) && m.bedTarget.value==0;
    if(session!=m.session || !eligible){seen=falling=false;session=m.session;}
    if(!eligible)return false;
    if(seen && m.bedTemp.value<=previous-0.5f){lastFall=now;falling=true;previous=m.bedTemp.value;}
    if(!seen || m.bedTemp.value>=previous+0.5f)previous=m.bedTemp.value;
    seen=true;
    return falling && uint32_t(now-lastFall)<90000;
  }
};
// Only stage codes already named by the project's Bambu protocol mapping.
enum class Activity { Unknown, Offline, Idle, Preparing, Cleaning, Leveling, CalibrationLines, Heating, Printing, Change, Load, Unload, Pause, Cooling, Finished, Error };
// Prefer fresh cycles; retain a valid positive last reading for a labelled history.
inline const MonitorAmsUnit *dryingUnit(const BambuMonitorTelemetry &m,bool online,uint32_t now) {
  const MonitorAmsUnit *best=nullptr;
  for(const auto &u:m.amsUnits) {
    if(!u.used || (u.present.valid&&!u.present.value) || !u.dryRemainMin.valid || !u.dryRemainMin.value)continue;
    const bool fresh=online&&u.dryRemainMin.current(now);
    const bool bestFresh=best&&online&&best->dryRemainMin.current(now);
    if(!best || (fresh&&!bestFresh) || (fresh==bestFresh&&u.dryRemainMin.value>best->dryRemainMin.value))best=&u;
  }
  return best;
}
// MQTT print reports are deltas. An unchanged RUNNING/PREPARE state and
// percentage can remain usable while new job progress, layers or ETA arrive.
// Temperatures/AMS traffic alone do not keep a cached print alive.
inline bool activeJob(const BambuMonitorTelemetry &m) {
  return m.status.valid && (!strcmp(m.status.value,"RUNNING") || !strcmp(m.status.value,"PREPARE"));
}
inline bool jobDeltaFresh(const BambuMonitorTelemetry &m,uint32_t now) {
  return m.progress.fresh(now) || m.layerNum.fresh(now) || m.remainingMinutes.fresh(now);
}
inline bool statusCurrent(const BambuMonitorTelemetry &m,bool online,uint32_t now) {
  return online && m.status.valid && (m.status.current(now) || (activeJob(m) && jobDeltaFresh(m,now)));
}
inline bool progressCurrent(const BambuMonitorTelemetry &m,bool online,uint32_t now) {
  return statusCurrent(m,online,now) && m.progress.valid &&
         (m.progress.current(now) || (activeJob(m) && jobDeltaFresh(m,now)));
}
// Presentation only: a fresh percentage can describe startup, or still be
// awaiting replacement at a job boundary. Do not turn that into a stale link.
inline bool beforeFirstLayer(const BambuMonitorTelemetry &m,bool online,uint32_t now) {
  if(!statusCurrent(m,online,now) || !activeJob(m))return false;
  // Preserve started jobs through sparse deltas, pause/reheat and the firmware's
  // layer-zero reset at completion. The parser clears this latch for a new job.
  if(m.printedLayerSeen || (m.layerNum.valid && m.layerNum.value>0))return false;
  if(!strcmp(m.status.value,"PREPARE") || (m.layerNum.valid && m.layerNum.value==0))return true;
  if(m.printStage.current(now))switch(m.printStage.value) {
    case 1:case 2:case 3:case 7:case 8:case 9:case 10:case 11:case 12:case 13:
    case 14:case 15:case 18:case 19:case 40:case 47:case 48:case 51:return true;
    default:break;
  }
  return false; // An absent layer in a RUNNING delta is not a reported zero.
}
inline bool printProgressVisible(const BambuMonitorTelemetry &m,bool online,uint32_t now) {
  return progressCurrent(m,online,now) && !beforeFirstLayer(m,online,now);
}
inline bool dashboardProgressVisible(const BambuMonitorTelemetry &m,bool online,uint32_t now,bool advanced) {
  return advanced?printProgressVisible(m,online,now):progressCurrent(m,online,now);
}
enum class Saver { Clock, Print, Cooling, Pause, Alert };
inline Saver saver(const BambuMonitorTelemetry &m,bool online,uint32_t now,bool cooling,bool alert) {
  if(!statusCurrent(m,online,now))return Saver::Clock;
  if(alert)return Saver::Alert;
  if(!strcmp(m.status.value,"PAUSE"))return Saver::Pause;
  // A thermal hint must not replace the printer's current job percentage.
  // Keep cooling as a post-print view (or when no current progress exists).
  if(cooling && !(activeJob(m) && progressCurrent(m,online,now)))return Saver::Cooling;
  if(!strcmp(m.status.value,"RUNNING") || !strcmp(m.status.value,"PREPARE"))return Saver::Print;
  return Saver::Clock; // FAILED is a job outcome, not proof of a live fault.
}
inline float dryingTurn(uint32_t elapsed) { return float(elapsed%60000u)/60000.0f; }
inline Activity activity(const BambuMonitorTelemetry &m,bool online,uint32_t now,bool cooling) {
  if(!online)return Activity::Offline;
  if(!statusCurrent(m,online,now))return Activity::Unknown;
  const char *s=m.status.value;
  if(!strcmp(s,"FAILED"))return Activity::Error;
  if(!strcmp(s,"PAUSE"))return Activity::Pause;
  if(cooling && (!strcmp(s,"RUNNING") || !strcmp(s,"FINISH")))return Activity::Cooling;
  if(!strcmp(s,"FINISH"))return Activity::Finished;
  if(!strcmp(s,"IDLE"))return Activity::Idle;
  if(strcmp(s,"RUNNING") && strcmp(s,"PREPARE"))return Activity::Unknown;
  if(m.printStage.current(now)) {
    switch(m.printStage.value) {
      case 4:return Activity::Change;
      case 22:return Activity::Unload;
      case 24:return Activity::Load;
      case 2:case 7:return Activity::Heating;
      case 14:return Activity::Cleaning;
      case 51:return Activity::CalibrationLines;
      case 1:case 40:case 47:case 48:return Activity::Leveling;
      case 3:case 8:case 9:case 10:case 11:case 12:case 13:case 15:case 18:case 19:return Activity::Preparing;
      case 0:case -1:case 255:break;
      default:return Activity::Unknown;
    }
  }
  return !strcmp(s,"PREPARE") || beforeFirstLayer(m,online,now)?Activity::Preparing:Activity::Printing;
}
struct ActivityClock {
  Activity state=Activity::Unknown;
  uint32_t since=0,session=0;uint8_t printer=255;
  bool update(Activity next,uint32_t now,uint32_t nextSession,uint8_t nextPrinter) {
    if(next==state && session==nextSession && printer==nextPrinter)return false;
    state=next;since=now;session=nextSession;printer=nextPrinter;return true;
  }
  uint32_t elapsed(uint32_t now) const {return uint32_t(now-since);}
  bool animated(uint32_t now) const {
    return state!=Activity::Unknown && state!=Activity::Offline && state!=Activity::Idle && state!=Activity::Error &&
      (state!=Activity::Finished || elapsed(now)<1800);
  }
};
inline bool navigationVisible(uint32_t now,uint32_t activity,bool pinned) {
  return pinned || uint32_t(now-activity)<5000;
}
inline int navigationItem(uint16_t x,uint16_t y) {
  if(y<440 || y>=476 || x<16 || x>=782) return -1;
  const unsigned relative=x-16;
  return relative%194<184 ? int(relative/194) : -1;
}
}
