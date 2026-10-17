#ifndef BAMBU_MONITOR_PARSER_H
#define BAMBU_MONITOR_PARSER_H

#include "bambu_monitor.h"
#include <ArduinoJson.h>
#include <math.h>
#include <stdlib.h>
#include <errno.h>

namespace bambu_monitor {
struct ReportReader {
  const uint8_t* bytes;
  size_t length;
  size_t offset = 0;
  int read() { return offset < length ? bytes[offset++] : -1; }
  size_t readBytes(char* dest, size_t count) {
    const size_t left = length - offset;
    if (count > left) count = left;
    memcpy(dest, bytes + offset, count); offset += count; return count;
  }
  bool onlyWhitespaceLeft() const {
    for (size_t i = offset; i < length; ++i)
      if (bytes[i] != ' ' && bytes[i] != '\t' && bytes[i] != '\r' && bytes[i] != '\n')
        return false;
    return true;
  }
};
// AMS fields are often numeric strings. Core print fields retain the upstream
// numeric JSON contract. Reject booleans, partial strings, NaN and overflows.
inline bool number(JsonVariantConst v, double& out, bool allowString = false) {
  if (v.isNull() || v.is<bool>()) return false;
  if (v.is<const char*>()) {
    if (!allowString) return false;
    const char* text = v.as<const char*>();
    if (!text || !*text) return false;
    char* end = nullptr;
    errno = 0;
    out = strtod(text, &end);
    if (end == text || *end != '\0' || errno == ERANGE) return false;
  } else if (v.is<double>()) out = v.as<double>();
  else return false;
  return isfinite(out);
}
template <typename T> inline bool mergeNumber(JsonObjectConst obj, const char* key,
    MonitorField<T>& field, uint32_t now, double low, double high,
    bool integral, bool stringAllowed = false) {
  if (!obj.containsKey(key)) return false;
  double value;
  if (!number(obj[key], value, stringAllowed) || value < low || value > high ||
      (integral && floor(value) != value)) {
    field.invalidate(now); return false;
  }
  field.set(static_cast<T>(value), now); return true;
}
template <size_t N> inline bool mergeText(JsonObjectConst obj, const char* key,
    MonitorText<N>& field, uint32_t now, bool emptyAllowed) {
  if (!obj.containsKey(key)) return false;
  if (!obj[key].is<const char*>()) { field.invalidate(now); return false; }
  const char* value = obj[key].as<const char*>();
  if (!emptyAllowed && !*value) { field.invalidate(now); return false; }
  field.set(value, now); return true;
}
inline int hexDigit(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  return -1;
}
inline bool color(JsonVariantConst v, uint16_t& rgb565) {
  if (!v.is<const char*>()) return false;
  const char* text = v.as<const char*>();
  const size_t len = strlen(text);
  if (len != 6 && len != 8) return false;
  uint32_t rgb = 0;
  for (size_t i = 0; i < len; ++i) {
    const int digit = hexDigit(text[i]); if (digit < 0) return false;
    if (i < 6) rgb = (rgb << 4) | digit;
  }
  rgb565 = ((rgb >> 8) & 0xf800) | ((rgb >> 5) & 0x07e0) | ((rgb >> 3) & 0x001f);
  return true;
}
inline bool mergeTray(JsonObjectConst obj, MonitorAmsTray& tray, uint32_t now) {
  bool useful = mergeText(obj, "tray_type", tray.type, now, true);
  if (obj.containsKey("tray_type")) {
    if (tray.type.valid) {
      tray.present.set(tray.type.value[0] != 0, now);
      // An explicit empty slot removes old filament details, but omission does
      // not. Otherwise a previous PLA colour/remain can leak into an empty slot.
      if (!tray.present.value) {
        tray.colorRgb565.invalidate(now); tray.remain.invalidate(now);
      }
    } else tray.present.invalidate(now);
  }
  if (obj["tray_sub_brands"].is<const char*>() &&
      obj["tray_sub_brands"].as<const char*>()[0]) {
    tray.type.set(obj["tray_sub_brands"].as<const char*>(), now); useful = true;
  }
  if (obj.containsKey("tray_color") || obj.containsKey("cols")) {
    uint16_t rgb = 0;
    bool ok = color(obj["tray_color"], rgb);
    if (!ok && obj["cols"].is<JsonArrayConst>()) ok = color(obj["cols"][0], rgb);
    if (ok) { tray.colorRgb565.set(rgb, now); useful = true; }
    else tray.colorRgb565.invalidate(now);
  }
  useful |= mergeNumber(obj, "remain", tray.remain, now, 0, 100, true, true);
  return useful;
}
inline bool mergeAms(JsonObjectConst obj, BambuMonitorTelemetry& m, uint32_t now) {
  bool useful = mergeNumber(obj, "tray_now", m.activeTrayRaw, now, 0, 255, true, true);
  if (obj["ams"].is<JsonArrayConst>() && obj["ams"].as<JsonArrayConst>().size() == 0) {
    // An explicitly empty inventory removes the AMS, unlike an omitted array
    // or a sparse update for one unit. Continued core deltas must not revive
    // its old drying cycle, filament or sensor readings.
    for (auto &u : m.amsUnits) u = MonitorAmsUnit{};
    if (m.activeTrayRaw.valid && m.activeTrayRaw.value < 252) m.activeTrayRaw.invalidate(now);
    return true;
  }
  for (JsonObjectConst incoming : obj["ams"].as<JsonArrayConst>()) {
    double rawId;
    if (!number(incoming["id"], rawId, true) || rawId < 0 || rawId > 255 ||
        floor(rawId) != rawId) continue;
    const uint8_t id = static_cast<uint8_t>(rawId);
    MonitorAmsUnit* unit = nullptr;
    for (auto& u : m.amsUnits) if (u.used && u.id == id) { unit = &u; break; }
    if (!unit) for (auto& u : m.amsUnits) if (!u.used) {
      unit = &u; u = MonitorAmsUnit{}; u.used = true; u.id = id; break;
    }
    if (!unit) continue;
    unit->present.set(true, now); useful = true;
    bool unitData = mergeNumber(incoming, "temp", unit->temp, now, -273.15, 1000, false, true);
    unitData |= mergeNumber(incoming, "humidity", unit->humidity, now, 0, 5, true, true);
    unitData |= mergeNumber(incoming, "humidity_raw", unit->humidityRaw, now, 0, 100, true, true);
    unitData |= mergeNumber(incoming, "dry_time", unit->dryRemainMin, now, 0, 65535, true, true);
    for (JsonObjectConst t : incoming["tray"].as<JsonArrayConst>()) {
      double rawTray;
      if (!number(t["id"], rawTray, true) || rawTray < 0 || rawTray >= 4 ||
          floor(rawTray) != rawTray) continue;
      unitData |= mergeTray(t, unit->trays[static_cast<uint8_t>(rawTray)], now);
    }
    // A valid ID alone (or a report containing only invalid sensor values)
    // proves presence, not continued delivery of the unit's measurements.
    if (unitData) unit->retain(now);
  }
  return useful;
}
inline bool mergeChamber(JsonObjectConst print, BambuMonitorTelemetry& m,
                         uint32_t now) {
  // Use upstream's ordered temperature sources, but an explicitly invalid
  // source stays unknown instead of borrowing an unrelated stale value.
  if (print.containsKey("chamber_temper"))
    return mergeNumber(print, "chamber_temper", m.chamberTemp, now,
                       -273.15, 1000, false);
  JsonObjectConst info = print["ctc"]["info"].as<JsonObjectConst>();
  if (!info.containsKey("temp"))
    info = print["device"]["ctc"]["info"].as<JsonObjectConst>();
  if (!info.containsKey("temp")) return false;
  double packed;
  if (!number(info["temp"], packed, true) || packed < 0 ||
      packed > 4294967295.0 || floor(packed) != packed) {
    m.chamberTemp.invalidate(now); return false;
  }
  const uint32_t current = static_cast<uint32_t>(packed) & 0xffff;
  if (current > 1000) { m.chamberTemp.invalidate(now); return false; }
  m.chamberTemp.set(static_cast<float>(current), now); return true;
}
inline bool mergeLegacyFan(JsonObjectConst print, const char* key,
                           MonitorField<uint8_t>& field, uint8_t& roundedPct,
                           uint32_t now) {
  if (!print.containsKey(key)) return false;
  double value;
  if (!number(print[key], value, true) || value < 0 || value > 15 ||
      floor(value) != value) {
    field.invalidate(now); return false;
  }
  const uint8_t raw = static_cast<uint8_t>(value);
  field.set(raw * 100 / 15, now);
  roundedPct = ((raw * 2) / 3) * 10; return true;
}
inline bool mergeFans(JsonObjectConst print, BambuMonitorTelemetry& m,
                      uint32_t now) {
  if (print.containsKey("fan_gear")) {
    double raw;
    if (!number(print["fan_gear"], raw) || raw < 0 || raw > 4294967295.0 ||
        floor(raw) != raw) {
      m.partFanPct.invalidate(now); m.auxFanPct.invalidate(now);
      m.chamberFanPct.invalidate(now); return false;
    }
    const uint32_t gear = static_cast<uint32_t>(raw);
    // Keep both upstream conversions from the same source PWM. The UI may
    // choose fanMatchPrinter without losing precision through double rounding.
    const auto pct = [](uint8_t pwm) -> uint8_t {
      return (static_cast<uint16_t>(pwm) * 100 + 127) / 255;
    };
    const auto rounded = [](uint8_t pwm) -> uint8_t {
      return ((static_cast<uint16_t>(pwm) * 10 + 127) / 255) * 10;
    };
    m.fanGearSeen = true;
    m.partFanPct.set(pct(gear & 0xff), now);
    m.auxFanPct.set(pct((gear >> 8) & 0xff), now);
    m.chamberFanPct.set(pct((gear >> 16) & 0xff), now);
    m.partFanRoundedPct = rounded(gear & 0xff);
    m.auxFanRoundedPct = rounded((gear >> 8) & 0xff);
    m.chamberFanRoundedPct = rounded((gear >> 16) & 0xff);
    return true;
  }
  // Lower precision legacy deltas must neither overwrite nor refresh fields
  // after this session has demonstrated support for the packed report.
  if (m.fanGearSeen) return false;
  bool useful = mergeLegacyFan(print, "cooling_fan_speed", m.partFanPct,
                               m.partFanRoundedPct, now);
  useful |= mergeLegacyFan(print, "big_fan1_speed", m.auxFanPct,
                            m.auxFanRoundedPct, now);
  useful |= mergeLegacyFan(print, "big_fan2_speed", m.chamberFanPct,
                            m.chamberFanRoundedPct, now);
  return useful;
}
// P2S is single-nozzle. Upstream reads id=0 snow for P-series and treats it
// as the feeding tray, ahead of the logically loaded ams.tray_now. Decode the
// same (unit << 8) | low-two-bit tray mapping, including external/none sentinels.
// Packed extruder temperatures are upstream's dual-nozzle-only H2 path; they
// are deliberately not guessed as a replacement for P2S nozzle_temper here.
inline bool mergeP2sSnow(JsonObjectConst extruder, BambuMonitorTelemetry& m,
                        uint32_t now) {
  JsonArrayConst info = extruder["info"].as<JsonArrayConst>();
  if (info.size() != 1) return false;  // multi-nozzle selection is outside this panel scope
  JsonObjectConst entry = info[0].as<JsonObjectConst>();
  double id;
  if (!number(entry["id"], id) || id != 0 || !entry.containsKey("snow")) return false;
  double encoded;
  if (!number(entry["snow"], encoded) || encoded < 0 || encoded > 4294967295.0 ||
      floor(encoded) != encoded) {
    m.activeTrayRaw.invalidate(now); return false;
  }
  const uint32_t snow = static_cast<uint32_t>(encoded);
  const uint8_t unit = static_cast<uint8_t>(snow >> 8);
  const uint8_t tray = static_cast<uint8_t>(snow & 0x03);
  if (unit == 254 || unit == 255) m.activeTrayRaw.set(unit, now);
  else if (unit < 63) m.activeTrayRaw.set(uint8_t(unit * 4 + tray), now);
  else {
    // This UI's flat tray indicator cannot encode raw HT IDs (128+). Invalidate
    // it instead of wrapping to a different AMS or retaining the previous tray.
    m.activeTrayRaw.invalidate(now); return false;
  }
  return true;
}
// Uses the project's ArduinoJson filtering / print report mechanism. No raw
// substring extraction: whitespace, braces inside strings and AMS deltas remain
// valid JSON. A malformed report cannot partially mutate displayed telemetry.
inline bool parse(const uint8_t* payload, size_t length, BambuMonitorTelemetry& m,
                  uint32_t now) {
  JsonDocument filter;
  JsonObject fields = filter["print"].to<JsonObject>();
  for (const char* key : {"gcode_state", "stg_cur", "mc_percent", "mc_remaining_time",
       "nozzle_temper", "nozzle_target_temper", "bed_temper", "bed_target_temper", "ams",
       "subtask_name", "layer_num", "total_layer_num", "chamber_temper", "spd_lvl",
       "fan_gear", "cooling_fan_speed", "big_fan1_speed", "big_fan2_speed", "heatbreak_fan_speed"})
    fields[key] = true;
  fields["device"]["extruder"] = true;
  fields["ctc"]["info"]["temp"] = true;
  fields["device"]["ctc"]["info"]["temp"] = true;
  JsonDocument doc;
  ReportReader reader{payload, length};
  if (deserializeJson(doc, reader, DeserializationOption::Filter(filter)) ||
      !reader.onlyWhitespaceLeft()) {
    ++m.malformedReports; return false;
  }
  JsonObjectConst print = doc["print"].as<JsonObjectConst>();
  if (print.isNull()) return false;
  ++m.validReports;
  const auto previousStatus=m.status;
  bool jobData = mergeText(print, "gcode_state", m.status, now, false);
  const bool newJob = previousStatus.valid && m.status.valid &&
      (!strcmp(previousStatus.value, "IDLE") || !strcmp(previousStatus.value, "FINISH") ||
       !strcmp(previousStatus.value, "FAILED")) &&
      (!strcmp(m.status.value, "PREPARE") || !strcmp(m.status.value, "RUNNING"));
  if (newJob) {
    // Reports are deltas. Drop only the previous job's fields before merging
    // this report, so omitted percentages cannot reappear at the first layer.
    m.progress.invalidate(now);
    m.layerNum.invalidate(now);
    m.totalLayers.invalidate(now);
    m.remainingMinutes.invalidate(now);
    m.subtaskName.invalidate(now);
    m.printStage.invalidate(now);
    m.printedLayerSeen = false;
  } else if (m.layerNum.valid && m.layerNum.value > 0) {
    // Also seed from existing telemetry before a terminal zero can replace it.
    m.printedLayerSeen = true;
  }
  if(previousStatus.valid!=m.status.valid || strcmp(previousStatus.value,m.status.value))m.printStage.invalidate(now);
  jobData |= mergeNumber(print,"stg_cur",m.printStage,now,-1,255,true);
  bool metadata = mergeText(print, "subtask_name", m.subtaskName, now, false);
  jobData |= mergeNumber(print, "mc_percent", m.progress, now, 0, 100, true);
  jobData |= mergeNumber(print, "layer_num", m.layerNum, now, 0, 4294967295.0, true);
  if (m.layerNum.valid && m.layerNum.value > 0) m.printedLayerSeen = true;
  metadata |= mergeNumber(print, "total_layer_num", m.totalLayers, now, 0, 4294967295.0, true);
  jobData |= mergeNumber(print, "mc_remaining_time", m.remainingMinutes, now, 0, 65535, true);
  bool useful = jobData;
  useful |= mergeNumber(print, "nozzle_temper", m.nozzleTemp, now, -273.15, 1000, false);
  useful |= mergeNumber(print, "nozzle_target_temper", m.nozzleTarget, now, 0, 1000, false);
  useful |= mergeNumber(print, "bed_temper", m.bedTemp, now, -273.15, 1000, false);
  useful |= mergeNumber(print, "bed_target_temper", m.bedTarget, now, 0, 1000, false);
  useful |= mergeChamber(print, m, now);
  useful |= mergeNumber(print, "spd_lvl", m.speedLevel, now, 1, 4, true);
  useful |= mergeFans(print, m, now);
  uint8_t heatbreakRounded = 0;
  useful |= mergeLegacyFan(print, "heatbreak_fan_speed", m.heatbreakFanPct, heatbreakRounded, now);
  // Apply leases only from validated live data, before AMS/metadata can make
  // the report useful. No value or actual observation timestamp is fabricated.
  if (jobData) m.retainJob(now);
  if (useful) m.retainCore(now);
  useful |= metadata;
  useful |= mergeAms(print["ams"].as<JsonObjectConst>(), m, now);
  // Resolve after AMS so a snow delta wins even if the same report includes
  // tray_now, and also works when the report omits the AMS object entirely.
  useful |= mergeP2sSnow(print["device"]["extruder"].as<JsonObjectConst>(), m, now);
  if (useful) {
    if(!m.hasUsefulData)m.firstUsefulMs=now;
    m.hasUsefulData = true; m.lastUsefulMs = now;
    if(!m.coreSeen && m.status.valid && m.nozzleTemp.valid && m.bedTemp.valid) {
      m.coreSeen=true;m.firstCoreMs=now;
    }
  }
  return useful;
}
}  // namespace bambu_monitor
#endif
