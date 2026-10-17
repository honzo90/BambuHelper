#pragma once
#include "bambu_monitor.h"

namespace ws43b_live {
enum class View : uint8_t { None, Dashboard, Details, Ams, Clock, Gauges };

// Match the AMS cards: prefer current RH, otherwise the newest known sensor.
// Both sensor timestamps remain independent; choosing one never refreshes it.
inline bool amsHumidityUsesRaw(const MonitorAmsUnit &u,uint32_t now) {
  return u.humidityRaw.valid && (!u.humidity.valid || u.humidityRaw.fresh(now) ||
    uint32_t(now-u.humidityRaw.updatedMs)<=uint32_t(now-u.humidity.updatedMs));
}

// The dashboard's material caption follows the active tray, even when its AMS
// is not the unit shown in the four slot cards. Retained metadata never polls.
template<class Visitor>
void visitActiveFilamentMetadata(const BambuMonitorTelemetry &m,Visitor f) {
  if(!m.activeTrayRaw.valid || m.activeTrayRaw.value>=252)return;
  for(const auto &unit:m.amsUnits) {
    if(!unit.used || unit.id>=63 || unit.id!=m.activeTrayRaw.value/4)continue;
    f(unit.present,false);
    if(unit.present.valid&&!unit.present.value)return;
    const auto &tray=unit.trays[m.activeTrayRaw.value%4];
    f(tray.present,false);
    if(tray.present.valid&&!tray.present.value)return;
    f(tray.type,false);
    return;
  }
}

// A view describes display interest, never ownership of the telemetry cache.
// Slow metadata is included in repaint detection, not in recovery polling.
template<class Visitor>
void visit(const BambuMonitorTelemetry &m,View view,unsigned ams,uint32_t now,Visitor f) {
  if(view==View::None)return;
  f(m.status,true);
  if(view==View::Dashboard || view==View::Clock || view==View::Gauges) {
    f(m.progress,true);f(m.remainingMinutes,true);f(m.printStage,true);
    f(m.nozzleTemp,true);f(m.nozzleTarget,true);f(m.bedTemp,true);f(m.bedTarget,true);
  }
  if(view==View::Clock)f(m.layerNum,true);
  if(view==View::Dashboard || view==View::Details || view==View::Gauges) {
    f(m.subtaskName,false);f(m.layerNum,true);f(m.totalLayers,false);f(m.chamberTemp,true);
  }
  if(view==View::Details || view==View::Gauges) {
    f(m.speedLevel,true);f(m.heatbreakFanPct,true);f(m.partFanPct,true);f(m.auxFanPct,true);f(m.chamberFanPct,true);
  }
  if(view==View::Dashboard)visitActiveFilamentMetadata(m,f);
  if(view==View::Dashboard || view==View::Ams || view==View::Clock || view==View::Gauges) {
    f(m.activeTrayRaw,true);
    for(unsigned i=0;i<6;++i) {
      const auto &u=m.amsUnits[i];
      if(!u.used)continue;
      if(view!=View::Clock && view!=View::Gauges && i!=ams)continue;
      f(u.present,false);
      if(u.present.valid&&!u.present.value)continue;
      if(view==View::Clock && (!u.dryRemainMin.valid || !u.dryRemainMin.value))continue;
      f(u.temp,true);
      if(view==View::Clock)f(u.humidityRaw,true,1); // Saver labels RH only.
      else if(view==View::Gauges) {
        // The gauge value is always raw RH. Legacy level affects its color
        // only when raw RH is outside the supported color range.
        f(u.humidityRaw,true,1);
        if(!u.humidityRaw.valid || u.humidityRaw.value<1 || u.humidityRaw.value>100)
          f(u.humidity,true,2);
      } else if(amsHumidityUsesRaw(u,now))f(u.humidityRaw,true,1);
      else f(u.humidity,true,2);
      f(u.dryRemainMin,true);
      if(view!=View::Clock)for(const auto &t:u.trays) {
        f(t.present,false);f(t.type,false);f(t.colorRgb565,false);
        if(!t.present.valid||t.present.value)f(t.remain,true);
      }
    }
  }
}
inline void hashBytes(uint32_t &hash,const void *value,size_t size) {
  const auto *bytes=static_cast<const uint8_t*>(value);
  for(size_t i=0;i<size;++i){hash^=bytes[i];hash*=16777619u;}
}
inline uint32_t signature(const BambuMonitorTelemetry &m,View view,unsigned ams,
                          bool online,uint32_t now) {
  uint32_t hash=2166136261u;
  hashBytes(hash,&view,sizeof view);hashBytes(hash,&ams,sizeof ams);
  hashBytes(hash,&online,sizeof online);hashBytes(hash,&m.session,sizeof m.session);
  if(view==View::Dashboard || view==View::Clock || view==View::Gauges)
    hashBytes(hash,&m.printedLayerSeen,sizeof m.printedLayerSeen);
  visit(m,view,ams,now,[&](const auto &field,bool,uint8_t source=0){
    // Equal numbers from RH and the coarse level have different labels.
    hashBytes(hash,&source,sizeof source);
    const uint8_t state=!field.valid?0:online&&field.current(now)?2:1;
    hashBytes(hash,&state,sizeof state);
    if(field.valid)hashBytes(hash,&field.value,sizeof field.value);
  });
  return hash;
}
inline bool needsRefresh(const BambuMonitorTelemetry &m,View view,unsigned ams,
                         bool online,uint32_t now) {
  // Silence/offline is handled by connection recovery. Unknown/unsupported
  // fields do not cause a request loop. Never rewrite a field's observation time.
  if(!online||!m.hasUsefulData||uint32_t(now-m.lastUsefulMs)>BAMBU_MONITOR_FRESH_MS)return false;
  bool stale=false;
  visit(m,view,ams,now,[&](const auto &field,bool expires,uint8_t=0){
    stale|=expires&&field.valid&&!field.current(now);
  });
  return stale;
}
struct RefreshGate {
  uint32_t lastAttempt=0;bool attempted=false;
  bool due(uint32_t now,uint32_t connectedAt,uint32_t lastPushall,
           uint32_t interval,bool needed) const {
    return needed && uint32_t(now-connectedAt)>=interval &&
      uint32_t(now-lastPushall)>=interval &&
      (!attempted||uint32_t(now-lastAttempt)>=interval);
  }
  void mark(uint32_t now){lastAttempt=now;attempted=true;}
};
inline bool deferForRx(uint32_t now,uint32_t lastFrame,bool pending,bool painted,bool force) {
  return pending && painted && !force && uint32_t(now-lastFrame)<400u;
}
inline bool repaintDue(uint32_t now,uint32_t lastFrame,uint32_t current,uint32_t drawn) {
  // Coalesce bursts; data takes precedence over decoration without starving
  // MQTT/touch with an unbounded series of expensive full-screen redraws.
  return current!=drawn && uint32_t(now-lastFrame)>=200u;
}
} // namespace ws43b_live
