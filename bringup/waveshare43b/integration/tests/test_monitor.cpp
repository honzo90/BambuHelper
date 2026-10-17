#include "bambu_monitor_parser.h"
#include <cassert>
#include <cstring>
#include <iostream>
#include <limits>

using bambu_monitor::parse;
static bool report(BambuMonitorTelemetry& m, const char* json, uint32_t ms) {
  return parse(reinterpret_cast<const uint8_t*>(json), strlen(json), m, ms);
}
int main() {
  // Arrival timing must distinguish a partial report from core temperatures.
  BambuMonitorTelemetry timing;
  assert(report(timing,R"({"print":{"mc_percent":20}})",100));
  assert(timing.firstUsefulMs==100&&!timing.coreSeen);
  assert(report(timing,R"({"print":{"gcode_state":"RUNNING","nozzle_temper":200}})",200));
  assert(timing.firstUsefulMs==100&&!timing.coreSeen);
  assert(report(timing,R"({"print":{"bed_temper":60}})",400));
  assert(timing.coreSeen&&timing.firstCoreMs==400);
  assert(report(timing,R"({"print":{"bed_temper":61}})",500));
  assert(timing.firstCoreMs==400&&timing.firstUsefulMs==100);
  timing.newSession();assert(!timing.coreSeen&&!timing.hasUsefulData&&timing.firstUsefulMs==0);
  BambuMonitorTelemetry m{};
  assert(!m.status.valid && !m.progress.valid && !m.hasUsefulData);
  m.newSession(); assert(m.session == 1);

  // Explicit zero remains a known zero, absent core fields remain unknown.
  assert(report(m, R"({"print":{"gcode_state":"RUNNING","mc_percent":0,"mc_remaining_time":0,"nozzle_temper":0,"nozzle_target_temper":0,"bed_temper":0,"bed_target_temper":0}})", 10));
  assert(m.progress.valid && m.progress.value == 0 && m.remainingMinutes.valid);
  assert(m.nozzleTemp.valid && m.bedTarget.valid && m.bedTarget.value == 0);
  assert(m.hasUsefulData && m.lastUsefulMs == 10 && m.status.fresh(10));

  // One field's delta must not refresh or zero any other field.
  assert(report(m, R"({"print":{"bed_temper":42.5}})", 20000));
  assert(m.bedTemp.value == 42.5 && m.bedTemp.updatedMs == 20000);
  assert(m.progress.updatedMs == 10 && !strcmp(m.status.value, "RUNNING"));
  assert(!m.status.fresh(60011) && m.bedTemp.fresh(60011));
  assert(!report(m, R"({"system":{"command":"unrelated"}})", 30000));
  assert(m.lastUsefulMs == 20000);

  // A malformed object cannot partly overwrite a previously valid field.
  assert(!report(m, R"({"print":{"mc_percent":77,)", 40000));
  assert(m.progress.value == 0 && m.progress.updatedMs == 10 && m.malformedReports == 1);
  assert(!report(m, R"({"print":{"mc_percent":77}}trailing)", 40001));
  assert(m.progress.value == 0 && m.malformedReports == 2);
  assert(!report(m, R"({"print":{"mc_percent":true,"mc_remaining_time":-1,"nozzle_temper":"hot"}})", 50000));
  assert(!m.progress.valid && !m.remainingMinutes.valid && !m.nozzleTemp.valid);
  assert(m.bedTemp.valid && m.bedTemp.value == 42.5);

  // Explicit AMS zero is not unknown; sparse tray arrays merge by raw ID.
  assert(report(m, R"({"print":{"ams":{"tray_now":"0","ams":[{"id":"0","temp":"28.5","humidity":"0","humidity_raw":"0","dry_time":0,"tray":[{"id":"0","tray_type":"PLA","tray_color":"FF0000FF","remain":0},{"id":"1","tray_type":"PETG","remain":70}]}]}}})", 60000));
  auto& u = m.amsUnits[0];
  assert(u.used && u.id == 0 && u.temp.valid && u.temp.value == 28.5);
  assert(u.humidityRaw.valid && u.humidityRaw.value == 0);
  assert(u.dryRemainMin.valid && u.dryRemainMin.value == 0);
  assert(u.trays[0].remain.valid && u.trays[0].remain.value == 0);
  assert(u.trays[0].colorRgb565.value == 0xf800);
  assert(m.activeTrayRaw.valid && m.activeTrayRaw.value == 0);
  assert(report(m, R"({"print":{"ams":{"ams":[{"id":"0","tray":[{"id":"1","remain":69}]}]}}})", 70000));
  assert(u.trays[1].remain.value == 69 && !strcmp(u.trays[1].type.value, "PETG"));
  assert(u.trays[0].remain.valid && u.trays[0].remain.updatedMs == 60000);
  assert(u.temp.updatedMs == 60000 && u.temp.value == 28.5);
  assert(m.activeTrayRaw.updatedMs == 60000);

  // Unknown is explicit: -1/null/bad numeric strings cannot become zero.
  assert(report(m, R"({"print":{"ams":{"ams":[{"id":"0","humidity_raw":null,"temp":"28garbage","tray":[{"id":"0","remain":-1}]}]}}})", 80000));
  assert(!u.temp.valid && !u.humidityRaw.valid && !u.trays[0].remain.valid);
  assert(u.trays[1].remain.valid && u.trays[1].remain.value == 69);
  assert(report(m, R"({"print":{"ams":{"ams":[{"id":"128","temp":"35"},{"id":"0","dry_time":30}]}}})", 90000));
  assert(m.amsUnits[0].id == 0 && m.amsUnits[1].id == 128);
  assert(m.amsUnits[0].dryRemainMin.value == 30 && m.amsUnits[1].temp.value == 35);
  assert(!report(m, R"({"print":{"ams":{"ams":[{"id":"oops","temp":"0"}]}}})", 100000));
  assert(m.amsUnits[0].temp.valid == false && m.amsUnits[2].used == false);

  // Empty tray is different from omitted tray; no previous colour survives.
  assert(report(m, R"({"print":{"ams":{"ams":[{"id":"0","tray":[{"id":"0","tray_type":""}]}]}}})", 110000));
  assert(u.trays[0].present.valid && !u.trays[0].present.value);
  assert(!u.trays[0].colorRgb565.valid && !u.trays[0].remain.valid);
  assert(!strcmp(u.trays[1].type.value, "PETG"));

  // P2S feeding filament comes from single-nozzle snow ahead of tray_now.
  assert(report(m, R"({"print":{"ams":{"tray_now":"0"},"device":{"extruder":{"info":[{"id":0,"snow":3}]}}}})", 111000));
  assert(m.activeTrayRaw.valid && m.activeTrayRaw.value == 3 && m.activeTrayRaw.updatedMs == 111000);
  // A snow-only delta must work without any print.ams object.
  assert(report(m, R"({"print":{"device":{"extruder":{"info":[{"id":0,"snow":258}]}}}})", 112000));
  assert(m.activeTrayRaw.value == 6);  // raw AMS id 1, tray 2, not array index
  assert(report(m, R"({"print":{"device":{"extruder":{"info":[{"id":0,"snow":65024}]}}}})", 113000));
  assert(m.activeTrayRaw.valid && m.activeTrayRaw.value == 254);  // external spool
  assert(report(m, R"({"print":{"device":{"extruder":{"info":[{"id":0,"snow":65280}]}}}})", 114000));
  assert(m.activeTrayRaw.value == 255);  // explicitly no active tray
  assert(!report(m, R"({"print":{"device":{"extruder":{"info":[{"id":0,"snow":32768}]}}}})", 115000));
  assert(!m.activeTrayRaw.valid);  // raw HT id 128 cannot wrap onto AMS2 slot zero
  assert(report(m, R"({"print":{"ams":{"tray_now":"0"}}})", 116000));
  assert(m.activeTrayRaw.valid && m.activeTrayRaw.value == 0);  // fallback when snow absent
  assert(!report(m, R"({"print":{"device":{"extruder":{"info":[{"id":0,"snow":"invalid"}]}}}})", 117000));
  assert(!m.activeTrayRaw.valid);
  // This target is P2S; do not repurpose the H2 dual-nozzle packed temp path.
  assert(report(m, R"({"print":{"nozzle_temper":210,"nozzle_target_temper":220,"device":{"extruder":{"info":[{"id":0,"temp":19661050}]}}}})", 118000));
  assert(m.nozzleTemp.value == 210 && m.nozzleTarget.value == 220);
  assert(!report(m, R"({"print":{"device":{"extruder":{"info":[{"id":0,"temp":19661050}]}}}})", 119000));
  assert(m.nozzleTemp.updatedMs == 118000 && m.nozzleTarget.updatedMs == 118000);

  // Print details use the same explicit zero/invalid/delta contract as the
  // summary. Text truncation must not leave a partial UTF-8 character.
  BambuMonitorTelemetry details{};
  assert(report(details, R"({"print":{"subtask_name":"Test PLA","layer_num":0,"total_layer_num":4294967295,"chamber_temper":0,"spd_lvl":2}})", 10));
  assert(details.subtaskName.valid && !strcmp(details.subtaskName.value, "Test PLA"));
  assert(details.layerNum.valid && details.layerNum.value == 0);
  assert(details.totalLayers.valid && details.totalLayers.value == UINT32_MAX);
  assert(details.chamberTemp.valid && details.chamberTemp.value == 0);
  assert(details.speedLevel.valid && details.speedLevel.value == 2);
  assert(report(details, R"({"print":{"layer_num":1}})", 20));
  assert(details.layerNum.value == 1 && details.subtaskName.updatedMs == 10);
  assert(details.totalLayers.updatedMs == 10 && details.chamberTemp.updatedMs == 10);
  assert(!report(details, R"({"print":{"subtask_name":null,"layer_num":-1,"total_layer_num":4294967296,"chamber_temper":null,"spd_lvl":5}})", 30));
  assert(!details.subtaskName.valid && !details.layerNum.valid && !details.totalLayers.valid);
  assert(!details.chamberTemp.valid && !details.speedLevel.valid);
  std::string longName(126, 'x'); longName += "\xc4\x85";
  std::string namedReport = "{\"print\":{\"subtask_name\":\"" + longName + "\"}}";
  assert(report(details, namedReport.c_str(), 40));
  assert(strlen(details.subtaskName.value) == 126);
  assert(report(details, R"({"print":{"ctc":{"info":{"temp":"3276832"}}}})", 50));
  assert(details.chamberTemp.value == 32); // packed target 50/current 32
  assert(report(details, R"({"print":{"device":{"ctc":{"info":{"temp":0}}}}})", 60));
  assert(details.chamberTemp.valid && details.chamberTemp.value == 0);
  assert(!report(details, R"({"print":{"chamber_temper":null,"ctc":{"info":{"temp":32}}}})", 70));
  assert(!details.chamberTemp.valid); // explicit invalid wins over fallback

  // Legacy fields accept complete 0..15 numeric strings. Packed gear wins
  // in the same report and later legacy deltas cannot refresh its timestamp.
  assert(report(details, R"({"print":{"cooling_fan_speed":"0","big_fan1_speed":1,"big_fan2_speed":"15"}})", 80));
  assert(details.partFanPct.valid && details.partFanPct.value == 0);
  assert(details.auxFanPct.value == 6 && details.chamberFanPct.value == 100);
  assert(details.partFanRoundedPct == 0 && details.auxFanRoundedPct == 0 && details.chamberFanRoundedPct == 100);
  assert(!report(details, R"({"print":{"cooling_fan_speed":"0oops","big_fan1_speed":16,"big_fan2_speed":null}})", 90));
  assert(!details.partFanPct.valid && !details.auxFanPct.valid && !details.chamberFanPct.valid);
  assert(report(details, R"({"print":{"fan_gear":16744448,"cooling_fan_speed":15,"big_fan1_speed":0,"big_fan2_speed":0}})", 100));
  assert(details.fanGearSeen && details.partFanPct.valid && details.partFanPct.value == 0);
  assert(details.auxFanPct.value == 50 && details.chamberFanPct.value == 100);
  assert(details.partFanRoundedPct == 0 && details.auxFanRoundedPct == 50 && details.chamberFanRoundedPct == 100);
  assert(!report(details, R"({"print":{"cooling_fan_speed":15,"big_fan1_speed":0,"big_fan2_speed":0}})", 110));
  assert(details.partFanPct.value == 0 && details.partFanPct.updatedMs == 100);
  assert(details.auxFanPct.value == 50 && details.chamberFanPct.value == 100);
  assert(!report(details, R"({"print":{"fan_gear":null,"cooling_fan_speed":15}})", 120));
  assert(!details.partFanPct.valid && !details.auxFanPct.valid && !details.chamberFanPct.valid);
  assert(report(details, R"({"print":{"fan_gear":140}})", 125));
  assert(details.partFanPct.value == 55 && details.partFanRoundedPct == 50);
  assert(report(details, R"({"print":{"heatbreak_fan_speed":"0"}})", 126));
  assert(details.heatbreakFanPct.valid && details.heatbreakFanPct.value == 0);
  assert(!report(details, R"({"print":{"heatbreak_fan_speed":null}})", 127));
  assert(!details.heatbreakFanPct.valid);
  details.newSession();
  assert(!details.subtaskName.valid && !details.layerNum.valid && !details.totalLayers.valid);
  assert(!details.chamberTemp.valid && !details.speedLevel.valid && !details.fanGearSeen);
  assert(!details.partFanPct.valid && !details.auxFanPct.valid && !details.chamberFanPct.valid);
  assert(report(details, R"({"print":{"cooling_fan_speed":"15"}})", 130));
  assert(details.partFanPct.value == 100 && !details.fanGearSeen);

  // New subscription session invalidates cached print + AMS before any report.
  m.newSession();
  assert(m.session == 2 && !m.hasUsefulData && !m.status.valid && !m.bedTemp.valid);
  assert(!m.amsUnits[0].used && !m.activeTrayRaw.valid && m.validReports == 0);
  assert(!report(m, R"({"print":{"unknown_field":0}})", 120000));
  assert(!m.hasUsefulData && !m.status.valid);  // MQTT message is not useful data

  // Per-field clocks remain correct around millis() wrap.
  m.progress.set(0, 0xfffffff0u);
  assert(m.progress.fresh(0x10u) && !m.progress.fresh(0x10000u));
  static_assert(!bambuMonitorPublishAllowed(), "monitor must never publish");
  std::cout << "PASS: telemetry zero/absent/invalid/delta/details/fans/AMS/session/freshness assertions\n";
}
