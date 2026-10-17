#ifndef BAMBU_MONITOR_H
#define BAMBU_MONITOR_H

#include <stdint.h>
#include <stddef.h>
#include <string.h>

// Validated telemetry for the Waveshare UI. Zero is a value, never missing.
// updatedMs/fresh() describe an actual field observation. retainedMs/current()
// also allow a known value omitted from a related MQTT delta to remain usable.
// Retention is session-local inference, not a new measurement; both expire on
// silence and callers must still gate current() with the connection state.
constexpr uint32_t BAMBU_MONITOR_FRESH_MS = 60000;
template <typename T> struct MonitorField {
  T value{};
  bool valid = false;
  uint32_t updatedMs = 0;
  uint32_t retainedMs = 0;
  void set(T v, uint32_t now) { value = v; valid = true; updatedMs = retainedMs = now; }
  void invalidate(uint32_t now) { valid = false; updatedMs = now; }
  void retain(uint32_t now) { if (valid) retainedMs = now; }
  bool current(uint32_t now, uint32_t maxAgeMs = BAMBU_MONITOR_FRESH_MS) const {
    return valid && uint32_t(now - retainedMs) <= maxAgeMs;
  }
  bool fresh(uint32_t now, uint32_t maxAgeMs = BAMBU_MONITOR_FRESH_MS) const {
    return valid && uint32_t(now - updatedMs) <= maxAgeMs;
  }
};
template <size_t N> struct MonitorText {
  char value[N]{};
  bool valid = false;
  uint32_t updatedMs = 0;
  uint32_t retainedMs = 0;
  void set(const char* v, uint32_t now) {
    size_t n = strlen(v);
    if (n >= N) {
      n = N - 1;
      // Do not split a UTF-8 character when a file/filament name is truncated.
      while (n && (static_cast<uint8_t>(v[n]) & 0xc0) == 0x80) --n;
    }
    memcpy(value, v, n); value[n] = 0; valid = true; updatedMs = retainedMs = now;
  }
  void invalidate(uint32_t now) { valid = false; updatedMs = now; }
  void retain(uint32_t now) { if (valid) retainedMs = now; }
  bool current(uint32_t now, uint32_t maxAgeMs = BAMBU_MONITOR_FRESH_MS) const {
    return valid && uint32_t(now - retainedMs) <= maxAgeMs;
  }
  bool fresh(uint32_t now, uint32_t maxAgeMs = BAMBU_MONITOR_FRESH_MS) const {
    return valid && uint32_t(now - updatedMs) <= maxAgeMs;
  }
};
struct MonitorAmsTray {
  MonitorField<bool> present;  // valid only if tray_type explicitly reports occupancy
  MonitorText<16> type;
  MonitorField<uint16_t> colorRgb565;
  MonitorField<int16_t> remain;  // explicit -1 / null = invalid; valid zero is retained
};
struct MonitorAmsUnit {
  bool used = false;
  uint8_t id = 0;             // stable raw ID, not array order (AMS HT may use 128+)
  MonitorField<bool> present;
  MonitorField<float> temp;
  MonitorField<uint8_t> humidity;
  MonitorField<uint8_t> humidityRaw;
  MonitorField<uint16_t> dryRemainMin;
  MonitorAmsTray trays[4];
  void retain(uint32_t now) {
    if (!used || (present.valid && !present.value)) return;
    present.retain(now); temp.retain(now); humidity.retain(now);
    humidityRaw.retain(now); dryRemainMin.retain(now);
    for (auto &t : trays) {
      t.present.retain(now);
      if (t.present.valid && !t.present.value) continue;
      t.type.retain(now); t.colorRgb565.retain(now); t.remain.retain(now);
    }
  }
};
struct BambuMonitorTelemetry {
  uint32_t session = 0;
  bool hasUsefulData = false;
  uint32_t lastUsefulMs = 0;
  uint32_t firstUsefulMs = 0, firstCoreMs = 0;
  bool coreSeen = false;
  uint32_t validReports = 0;
  uint32_t malformedReports = 0;
  MonitorText<16> status;
  MonitorField<int16_t> printStage; // stg_cur, per-field freshness; -1/255 idle
  MonitorText<128> subtaskName;
  MonitorField<uint8_t> progress;
  MonitorField<uint32_t> layerNum, totalLayers;
  // Job-local evidence: end G-code may reset layer_num to zero before FINISH.
  bool printedLayerSeen = false;
  MonitorField<uint16_t> remainingMinutes;
  MonitorField<float> nozzleTemp, nozzleTarget, bedTemp, bedTarget, chamberTemp;
  MonitorField<uint8_t> speedLevel; // 1 silent, 2 standard, 3 sport, 4 ludicrous
  MonitorField<uint8_t> partFanPct, auxFanPct, chamberFanPct, heatbreakFanPct;
  // Alternate display values share each corresponding FanPct valid/fresh gate.
  // Derive from the source PWM/legacy number, avoiding a second rounding of %.
  uint8_t partFanRoundedPct = 0, auxFanRoundedPct = 0, chamberFanRoundedPct = 0;
  bool fanGearSeen = false; // prefer packed PWM throughout this MQTT session
  MonitorField<uint8_t> activeTrayRaw; // printer's tray_now, 254 external / 255 none
  MonitorAmsUnit amsUnits[6];
  void retainJob(uint32_t now) {
    status.retain(now); printStage.retain(now); progress.retain(now);
    layerNum.retain(now); remainingMinutes.retain(now);
  }
  void retainCore(uint32_t now) {
    // Temperatures/fans may stay constant and disappear from partial reports.
    // They cannot renew job status/progress: that requires actual job traffic.
    subtaskName.retain(now); totalLayers.retain(now);
    nozzleTemp.retain(now); nozzleTarget.retain(now);
    bedTemp.retain(now); bedTarget.retain(now); chamberTemp.retain(now);
    speedLevel.retain(now); partFanPct.retain(now); auxFanPct.retain(now);
    chamberFanPct.retain(now); heatbreakFanPct.retain(now);
    activeTrayRaw.retain(now);
    for (auto &u : amsUnits) u.retain(now);
  }
  void newSession() {
    const uint32_t next = session + 1;
    *this = BambuMonitorTelemetry{};
    session = next;
  }
};

inline int monitorFilamentStage(const BambuMonitorTelemetry &m,bool online,uint32_t now) {
  if(!online || !m.status.current(now) || strcmp(m.status.value,"RUNNING") || !m.printStage.current(now))return 0;
  const int stage=m.printStage.value;
  return stage==4 || stage==22 || stage==24 ? stage : 0;
}

// In this profile neither refresh requests nor printer controls may publish.
// Kept in the host-testable contract; the MQTT translation unit also removes
// both actual PubSubClient::publish calls at preprocessing time.
constexpr bool bambuMonitorPublishAllowed() { return false; }

#endif
