from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[4]
VENDOR = ROOT / 'bringup/waveshare43b/integration/vendor/ArduinoJson-7.4.3/src'

CPP = r'''#include "bambu_monitor_parser.h"
#include <cassert>
#include <cstdio>

static bool report(BambuMonitorTelemetry& m, const char* json, uint32_t now) {
  return bambu_monitor::parse(reinterpret_cast<const uint8_t*>(json), strlen(json), m, now);
}

static void status(BambuMonitorTelemetry& m, const char* value, uint32_t now) {
  char json[96];
  snprintf(json, sizeof(json), "{\"print\":{\"gcode_state\":\"%s\"}}", value);
  assert(report(m, json, now));
}

static BambuMonitorTelemetry previousJob(const char* terminal) {
  BambuMonitorTelemetry m;
  m.newSession();
  assert(report(m, R"({"print":{"gcode_state":"RUNNING","stg_cur":4,
    "subtask_name":"previous.gcode","mc_percent":100,"layer_num":200,
    "total_layer_num":200,"mc_remaining_time":5,"nozzle_temper":210,
    "nozzle_target_temper":220,"bed_temper":60,"bed_target_temper":60,
    "chamber_temper":35,"ams":{"tray_now":1,"ams":[{"id":0,"temp":42,
    "humidity":3,"dry_time":90,"tray":[{"id":1,"tray_type":"PLA",
    "tray_color":"00FF00","remain":62}]}]}}})", 100));
  assert(m.printedLayerSeen);
  status(m, terminal, 200);
  // A terminal report may itself include a valid stage; boundary must drop it.
  assert(report(m, R"({"print":{"stg_cur":0}})", 201));
  return m;
}

static void nonJobDataPreserved(const BambuMonitorTelemetry& m) {
  assert(m.session == 1 && m.coreSeen && m.firstCoreMs == 100);
  assert(m.hasUsefulData && m.firstUsefulMs == 100);
  assert(m.nozzleTemp.valid && m.nozzleTemp.value == 210 && m.nozzleTemp.updatedMs == 100);
  assert(m.nozzleTarget.valid && m.nozzleTarget.value == 220 && m.nozzleTarget.updatedMs == 100);
  assert(m.bedTemp.valid && m.bedTemp.value == 60 && m.bedTemp.updatedMs == 100);
  assert(m.bedTarget.valid && m.bedTarget.value == 60 && m.bedTarget.updatedMs == 100);
  assert(m.chamberTemp.valid && m.chamberTemp.value == 35 && m.chamberTemp.updatedMs == 100);
  assert(m.activeTrayRaw.valid && m.activeTrayRaw.value == 1 && m.activeTrayRaw.updatedMs == 100);
  const auto& ams = m.amsUnits[0];
  assert(ams.used && ams.id == 0 && ams.present.valid && ams.present.value);
  assert(ams.temp.valid && ams.temp.value == 42 && ams.temp.updatedMs == 100);
  assert(ams.humidity.valid && ams.humidity.value == 3 && ams.humidity.updatedMs == 100);
  assert(ams.dryRemainMin.valid && ams.dryRemainMin.value == 90 && ams.dryRemainMin.updatedMs == 100);
  const auto& tray = ams.trays[1];
  assert(tray.present.valid && tray.present.value && tray.present.updatedMs == 100);
  assert(tray.type.valid && !strcmp(tray.type.value, "PLA") && tray.type.updatedMs == 100);
  assert(tray.colorRgb565.valid && tray.colorRgb565.value == 0x07e0 && tray.colorRgb565.updatedMs == 100);
  assert(tray.remain.valid && tray.remain.value == 62 && tray.remain.updatedMs == 100);
}

static void explicitBoundaries() {
  for (const char* terminal : {"IDLE", "FINISH", "FAILED"}) {
    for (const char* active : {"PREPARE", "RUNNING"}) {
      auto m = previousJob(terminal);
      status(m, active, 300);
      assert(!m.progress.valid && m.progress.updatedMs == 300);
      assert(!m.layerNum.valid && m.layerNum.updatedMs == 300);
      assert(!m.totalLayers.valid && m.totalLayers.updatedMs == 300);
      assert(!m.remainingMinutes.valid && m.remainingMinutes.updatedMs == 300);
      assert(!m.subtaskName.valid && m.subtaskName.updatedMs == 300);
      assert(!m.printStage.valid && m.printStage.updatedMs == 300);
      assert(!m.printedLayerSeen);
      assert(m.validReports == 4 && m.malformedReports == 0 && m.lastUsefulMs == 300);
      nonJobDataPreserved(m);
    }
  }
}

static void oldPercentNeverReturns() {
  auto m = previousJob("FINISH");
  assert(report(m, R"({"print":{"gcode_state":"PREPARE","layer_num":0}})", 300));
  assert(m.layerNum.valid && m.layerNum.value == 0 && !m.printedLayerSeen);
  assert(!m.progress.valid);
  assert(report(m, R"({"print":{"gcode_state":"RUNNING","layer_num":1}})", 400));
  assert(m.layerNum.valid && m.layerNum.value == 1 && m.printedLayerSeen);
  assert(!m.progress.valid && m.progress.updatedMs == 300);
  assert(!m.totalLayers.valid && !m.remainingMinutes.valid && !m.subtaskName.valid);
  assert(report(m, R"({"print":{"layer_num":2,"mc_remaining_time":90}})", 500));
  assert(!m.progress.valid); // Fresh new-job deltas cannot revive old 100%.
  assert(report(m, R"({"print":{"mc_percent":0}})", 600));
  assert(m.progress.valid && m.progress.value == 0 && m.progress.updatedMs == 600);
}

static void incomingFieldsWin() {
  for (const char* terminal : {"IDLE", "FINISH", "FAILED"}) {
    auto m = previousJob(terminal);
    assert(report(m, R"({"print":{"gcode_state":"RUNNING","stg_cur":1,
      "subtask_name":"new.gcode","mc_percent":13,"layer_num":2,
      "total_layer_num":50,"mc_remaining_time":10}})", 300));
    assert(m.progress.valid && m.progress.value == 13 && m.progress.updatedMs == 300);
    assert(m.layerNum.valid && m.layerNum.value == 2 && m.layerNum.updatedMs == 300);
    assert(m.totalLayers.valid && m.totalLayers.value == 50 && m.totalLayers.updatedMs == 300);
    assert(m.remainingMinutes.valid && m.remainingMinutes.value == 10 && m.remainingMinutes.updatedMs == 300);
    assert(m.subtaskName.valid && !strcmp(m.subtaskName.value, "new.gcode") && m.subtaskName.updatedMs == 300);
    assert(m.printStage.valid && m.printStage.value == 1 && m.printStage.updatedMs == 300);
    assert(m.printedLayerSeen);
    nonJobDataPreserved(m);
  }
}

static void sameJobTransitions() {
  for (const char* prior : {"PAUSE", "PREPARE", "RUNNING"}) {
    auto m = previousJob(prior);
    status(m, "RUNNING", 300);
    assert(m.progress.valid && m.progress.value == 100 && m.progress.updatedMs == 100);
    assert(m.layerNum.valid && m.layerNum.value == 200 && m.layerNum.updatedMs == 100);
    assert(m.totalLayers.valid && m.totalLayers.value == 200 && m.totalLayers.updatedMs == 100);
    assert(m.remainingMinutes.valid && m.remainingMinutes.value == 5 && m.remainingMinutes.updatedMs == 100);
    assert(m.subtaskName.valid && !strcmp(m.subtaskName.value, "previous.gcode"));
    assert(m.printedLayerSeen);
  }
  // RUNNING -> PREPARE is not treated as a proven new-job boundary.
  auto m = previousJob("RUNNING");
  status(m, "PREPARE", 300);
  assert(m.progress.valid && m.layerNum.valid && m.printedLayerSeen);

  // Attaching mid-print may receive job fields before the first status delta.
  BambuMonitorTelemetry attaching;
  assert(report(attaching, R"({"print":{"mc_percent":37,"layer_num":12}})", 100));
  status(attaching, "RUNNING", 200);
  assert(attaching.progress.valid && attaching.progress.value == 37);
  assert(attaching.layerNum.valid && attaching.layerNum.value == 12 && attaching.printedLayerSeen);
}

static void stickyLayerEvidence() {
  for (const char* terminal : {"RUNNING", "FINISH", "FAILED", "IDLE"}) {
    BambuMonitorTelemetry m;
    // Seed from a positive existing field too, before zero overwrites it.
    m.status.set("RUNNING", 100);
    m.layerNum.set(200, 100);
    assert(!m.printedLayerSeen);
    char json[128];
    snprintf(json, sizeof(json), "{\"print\":{\"gcode_state\":\"%s\",\"layer_num\":0,\"total_layer_num\":1}}", terminal);
    assert(report(m, json, 200));
    assert(m.layerNum.valid && m.layerNum.value == 0 && m.printedLayerSeen);
    assert(report(m, R"({"print":{"bed_temper":25}})", 300));
    assert(m.printedLayerSeen);
    report(m, R"({"print":{"layer_num":null}})", 400);
    assert(!m.layerNum.valid && m.printedLayerSeen);
    const uint32_t oldSession = m.session;
    m.newSession();
    assert(m.session == oldSession + 1 && !m.printedLayerSeen && !m.layerNum.valid);
  }
  for (const char* invalid : {"null", "true", "-1", "1.5", "4294967296", "\"1\""}) {
    BambuMonitorTelemetry m;
    char json[128];
    snprintf(json, sizeof(json), "{\"print\":{\"gcode_state\":\"RUNNING\",\"layer_num\":%s}}", invalid);
    assert(report(m, json, 100));
    assert(!m.layerNum.valid && !m.printedLayerSeen);
  }
  BambuMonitorTelemetry missing;
  status(missing, "RUNNING", 100);
  assert(!missing.layerNum.valid && !missing.printedLayerSeen);
}

static void malformedIsAtomic() {
  auto m = previousJob("FINISH");
  assert(!report(m, R"({"print":{"gcode_state":"PREPARE","layer_num":0}} trailing)", 300));
  assert(m.status.valid && !strcmp(m.status.value, "FINISH"));
  assert(m.progress.valid && m.progress.value == 100 && m.printedLayerSeen);
  assert(m.layerNum.valid && m.layerNum.value == 200);
  assert(m.validReports == 3 && m.malformedReports == 1);
}

int main() {
  explicitBoundaries();
  oldPercentNeverReturns();
  incomingFieldsWin();
  sameJobTransitions();
  stickyLayerEvidence();
  malformedIsAtomic();
}
'''


class PrintJobBoundary(unittest.TestCase):
    def test_parser_job_boundaries_and_layer_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            source = work / 'boundary.cpp'
            binary = work / 'boundary'
            source.write_text(CPP)
            subprocess.run([
                'clang++', '-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                '-Wno-deprecated-declarations', '-fsanitize=address,undefined',
                '-I', str(ROOT / 'include'), '-I', str(VENDOR), str(source),
                '-o', str(binary),
            ], check=True, capture_output=True)
            subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    unittest.main()
