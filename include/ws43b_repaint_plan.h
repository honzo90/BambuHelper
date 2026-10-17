#pragma once
#include <array>
#include "ws43b_live_view.h"
#include "ws43b_dashboard_policy.h"

// A repaint cache owns only presentation fingerprints. It neither caches nor
// refreshes telemetry, and the caller keeps screen transitions/full redraws.
namespace ws43b_repaint {
enum class Region : uint8_t {
  Header=0, Primary, Nozzle, Bed, Chamber, AmsSummary,
  Ams0, Ams1, Ams2, Ams3, DetailsBody, Count
};
constexpr size_t Count=static_cast<size_t>(Region::Count);
using Keys=std::array<uint32_t,Count>;
using Mask=uint16_t;
constexpr Mask regionBit(Region region) { return Mask(1u<<static_cast<unsigned>(region)); }
constexpr Mask All=Mask((1u<<Count)-1u);
inline void addBytes(uint32_t &key,const void *bytes,size_t size) {
  ws43b_live::hashBytes(key,bytes,size);
}
template<class T> inline void add(uint32_t &key,const T &value) {
  addBytes(key,&value,sizeof value);
}
inline void addText(uint32_t &key,const char *text) {
  addBytes(key,text,strlen(text)+1);
}
template<class T> inline void addValue(uint32_t &key,const T &value) { add(key,value); }
template<size_t N> inline void addValue(uint32_t &key,const char (&value)[N]) {
  addText(key,value);
}
template<class Field>
inline void field(uint32_t &key,const Field &value,bool online,uint32_t now,bool showAge=true) {
  const uint8_t state=!value.valid?0:online&&value.current(now)?2:1;
  add(key,state);
  if(!value.valid)return;
  addValue(key,value.value);
  if(showAge && state==1) {
    // Exactly the labels rendered by amsReadingAge: seconds, minutes, hours.
    const uint32_t seconds=uint32_t(now-value.updatedMs)/1000u;
    const uint8_t unit=seconds<60?0:seconds<3600?1:2;
    const uint32_t age=unit==0?seconds:unit==1?seconds/60u:seconds/3600u;
    add(key,unit);add(key,age);
  }
}
inline uint32_t seed(const BambuMonitorTelemetry &m,ws43b_live::View view,bool online) {
  uint32_t key=2166136261u;
  add(key,view);add(key,m.session);add(key,online);
  return key;
}
inline bool useful(const BambuMonitorTelemetry &m,bool online,uint32_t now) {
  return online&&m.hasUsefulData&&uint32_t(now-m.lastUsefulMs)<=BAMBU_MONITOR_FRESH_MS;
}
inline void filament(uint32_t &key,const BambuMonitorTelemetry &m,bool online) {
  // The print scene deliberately retains the last confirmed selection/color
  // for this session. Freshness of unrelated AMS fields is not a dependency.
  const bool selected=online&&m.activeTrayRaw.valid&&m.activeTrayRaw.value<252;
  add(key,selected);
  if(!selected)return;
  add(key,m.activeTrayRaw.value);
  for(const auto &unit:m.amsUnits) {
    if(!unit.used||unit.id>=63||unit.id!=m.activeTrayRaw.value/4 ||
       (unit.present.valid&&!unit.present.value))continue;
    const auto &tray=unit.trays[m.activeTrayRaw.value%4];
    const bool known=!(tray.present.valid&&!tray.present.value)&&tray.colorRgb565.valid;
    add(key,known);
    if(known)add(key,tray.colorRgb565.value);
    return;
  }
  const bool known=false;add(key,known);
}
inline Keys keys(const BambuMonitorTelemetry &m,ws43b_live::View view,unsigned ams,
                 bool online,uint32_t now) {
  Keys result{};
  const uint32_t base=seed(m,view,online);
  auto start=[&](Region region)->uint32_t& {
    auto &key=result[static_cast<size_t>(region)];key=base;return key;
  };
  auto &header=start(Region::Header);
  field(header,m.status,online,now,false);field(header,m.progress,online,now,false);
  field(header,m.printStage,online,now,false);
  add(header,useful(m,online,now));
  add(header,ws43b_view::statusCurrent(m,online,now));
  add(header,ws43b_view::progressCurrent(m,online,now));
  add(header,ws43b_view::beforeFirstLayer(m,online,now));

  if(view==ws43b_live::View::Dashboard) {
    auto &primary=start(Region::Primary);
    field(primary,m.status,online,now,false);field(primary,m.progress,online,now,false);
    field(primary,m.remainingMinutes,online,now,false);field(primary,m.printStage,online,now,false);
    field(primary,m.subtaskName,online,now);field(primary,m.layerNum,online,now,false);
    field(primary,m.totalLayers,online,now);
    add(primary,ws43b_view::statusCurrent(m,online,now));
    add(primary,ws43b_view::progressCurrent(m,online,now));
    add(primary,ws43b_view::beforeFirstLayer(m,online,now));
    filament(primary,m,online);
    // The material caption labels stale selection separately from the retained
    // scene color; crossing its freshness boundary must repaint this region.
    field(primary,m.activeTrayRaw,online,now,false);
    ws43b_live::visitActiveFilamentMetadata(m,[&](const auto &metadata,bool) {
      field(primary,metadata,online,now,false);
    });
    auto &nozzle=start(Region::Nozzle);
    field(nozzle,m.nozzleTemp,online,now);field(nozzle,m.nozzleTarget,online,now);
    auto &bed=start(Region::Bed);
    field(bed,m.bedTemp,online,now);field(bed,m.bedTarget,online,now);
    auto &chamber=start(Region::Chamber);field(chamber,m.chamberTemp,online,now);
    // Keep thermal hysteresis progressing with unchanged observations. The
    // retained policy can finish its five-second dwell or cooling timeout.
    const uint32_t thermalTick=now/1000u;
    add(nozzle,thermalTick);add(bed,thermalTick);add(chamber,thermalTick);
  }
  if(view==ws43b_live::View::Dashboard||view==ws43b_live::View::Ams) {
    auto &summary=start(Region::AmsSummary);
    const bool link=useful(m,online,now);
    add(summary,ams);add(summary,link);
    const auto *unit=ams<sizeof(m.amsUnits)/sizeof(m.amsUnits[0])?&m.amsUnits[ams]:nullptr;
    const bool present=unit&&unit->used&&!(unit->present.valid&&!unit->present.value);
    add(summary,present);
    if(present) {
      add(summary,unit->id);
      field(summary,unit->temp,link,now);
      const bool raw=ws43b_live::amsHumidityUsesRaw(*unit,now);add(summary,raw);
      if(raw)field(summary,unit->humidityRaw,link,now);
      else field(summary,unit->humidity,link,now);
      field(summary,unit->dryRemainMin,link,now);
    }
    for(unsigned i=0;i<4;++i) {
      auto &key=start(static_cast<Region>(static_cast<unsigned>(Region::Ams0)+i));
      add(key,ams);add(key,present);add(key,link);
      if(!present)continue;
      add(key,unit->id);
      const auto &tray=unit->trays[i];
      const bool empty=tray.present.valid&&!tray.present.value;
      add(key,empty);field(key,tray.present,link,now,false);
      if(empty)continue;
      field(key,tray.type,link,now,false);field(key,tray.colorRgb565,link,now,false);
      field(key,tray.remain,link,now);
      const bool active=link&&m.activeTrayRaw.current(now)&&unit->id<63&&
        m.activeTrayRaw.value==unit->id*4+i;
      add(key,active);
    }
  }
  if(view==ws43b_live::View::Details) {
    auto &details=start(Region::DetailsBody);
    field(details,m.subtaskName,online,now);field(details,m.layerNum,online,now,false);
    field(details,m.totalLayers,online,now);field(details,m.chamberTemp,online,now);
    field(details,m.speedLevel,online,now);
    field(details,m.partFanPct,online,now);field(details,m.auxFanPct,online,now);
    field(details,m.chamberFanPct,online,now);
    add(details,m.partFanRoundedPct);add(details,m.auxFanRoundedPct);add(details,m.chamberFanRoundedPct);
  }
  return result;
}
struct Cache {
  Keys drawn{};bool valid=false;
  Mask dirty(const Keys &next,bool force=false) const {
    if(force||!valid)return All;
    Mask mask=0;
    for(size_t i=0;i<Count;++i)if(drawn[i]!=next[i])mask|=Mask(1u<<i);
    return mask;
  }
  void commit(const Keys &next) { drawn=next;valid=true; }
  void invalidate() { valid=false; }
};
} // namespace ws43b_repaint
