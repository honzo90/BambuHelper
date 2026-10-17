"""Exercise delta retention through the real parser, UI policy and live-view gates."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
JSON_INCLUDE = ROOT / 'bringup/waveshare43b/integration/vendor/ArduinoJson-7.4.3/src'

HARNESS = r'''
#include "bambu_monitor_parser.h"
#include "ws43b_dashboard_policy.h"
#include "ws43b_live_view.h"
#include <cassert>
#include <cstring>
#include <iostream>
#include <string>

bool report(BambuMonitorTelemetry &m, const char *json, uint32_t now) {
  return bambu_monitor::parse(reinterpret_cast<const uint8_t*>(json), strlen(json), m, now);
}
void seed(BambuMonitorTelemetry &m, uint32_t now=100) {
  m.newSession();
  assert(report(m, R"({"print":{
    "gcode_state":"RUNNING","stg_cur":0,"subtask_name":"SYNTHETIC delta fixture",
    "mc_percent":42,"layer_num":84,"total_layer_num":200,"mc_remaining_time":30,
    "nozzle_temper":220,"nozzle_target_temper":220,"bed_temper":60,"bed_target_temper":60,
    "chamber_temper":36,"spd_lvl":2,"fan_gear":8421631,"heatbreak_fan_speed":"7",
    "ams":{"tray_now":"1","ams":[
      {"id":"0","temp":39,"humidity":"2","humidity_raw":"15","dry_time":30,
       "tray":[{"id":"0","tray_type":"PLA","tray_color":"FF0000FF","remain":40},
               {"id":"1","tray_type":"PETG","tray_color":"00FF00FF","remain":0}]},
      {"id":"1","temp":37,"humidity":"3","humidity_raw":"25","dry_time":20,
       "tray":[{"id":"0","tray_type":"ASA","tray_color":"0000FFFF","remain":60}]}]}
  }})", now));
}

void retained_delta() {
  BambuMonitorTelemetry m;seed(m);
  const auto details=ws43b_live::signature(m,ws43b_live::View::Details,0,true,100);
  assert(report(m,R"({"print":{"mc_percent":43}})",61001));
  assert(m.progress.value==43 && m.progress.updatedMs==61001 && m.progress.fresh(61001));
  assert(m.status.updatedMs==100 && !m.status.fresh(61001) && m.status.current(61001));
  assert(m.nozzleTemp.updatedMs==100 && !m.nozzleTemp.fresh(61001) && m.nozzleTemp.current(61001));
  assert(m.subtaskName.updatedMs==100 && m.subtaskName.current(61001));
  assert(m.totalLayers.updatedMs==100 && m.totalLayers.current(61001));
  assert(m.printStage.updatedMs==100 && m.printStage.current(61001));
  assert(m.amsUnits[0].humidityRaw.updatedMs==100 && m.amsUnits[0].humidityRaw.current(61001));
  assert(m.amsUnits[1].trays[0].remain.updatedMs==100 && m.amsUnits[1].trays[0].remain.current(61001));
  assert(m.amsUnits[0].trays[1].remain.valid && m.amsUnits[0].trays[1].remain.value==0);
  assert(ws43b_view::statusCurrent(m,true,61001));
  assert(ws43b_view::progressCurrent(m,true,61001));
  assert(ws43b_view::activity(m,true,61001,false)==ws43b_view::Activity::Printing);
  // No repaint or recovery solely because unchanged Details fields are >60s old.
  assert(ws43b_live::signature(m,ws43b_live::View::Details,0,true,61001)==details);
  for(const auto view:{ws43b_live::View::Dashboard,ws43b_live::View::Details,
                      ws43b_live::View::Ams,ws43b_live::View::Clock,ws43b_live::View::Gauges})
    assert(!ws43b_live::needsRefresh(m,view,0,true,61001));
  assert(m.nozzleTemp.current(121001) && !m.nozzleTemp.current(121002));
  assert(!ws43b_view::statusCurrent(m,true,121002));
  assert(ws43b_live::signature(m,ws43b_live::View::Details,0,true,121002)!=details);
}

void domain_isolation() {
  BambuMonitorTelemetry m;seed(m);
  assert(report(m,R"({"print":{"ams":{"ams":[{"id":"0","humidity":"3"}]}}})",61001));
  assert(m.amsUnits[0].temp.current(61001) && m.amsUnits[0].temp.updatedMs==100);
  assert(m.amsUnits[0].trays[0].remain.current(61001));
  assert(!m.amsUnits[1].temp.current(61001));
  assert(!m.nozzleTemp.current(61001) && !m.status.current(61001));
  assert(!ws43b_view::statusCurrent(m,true,61001));
  assert(!ws43b_view::progressCurrent(m,true,61001));
  assert(ws43b_live::needsRefresh(m,ws43b_live::View::Dashboard,0,true,61001));
  // Choosing RH vs the coarse humidity level still follows actual observations.
  assert(m.amsUnits[0].humidityRaw.current(61001));
  assert(!m.amsUnits[0].humidityRaw.fresh(61001));
  assert(!ws43b_live::amsHumidityUsesRaw(m.amsUnits[0],61001));
  assert(report(m,R"({"print":{"chamber_temper":37}})",61002));
  assert(m.nozzleTemp.current(61002) && m.amsUnits[1].temp.current(61002));
  assert(!m.status.current(61002) && !m.progress.current(61002));
  assert(!m.printStage.current(61002));
  assert(!ws43b_view::statusCurrent(m,true,61002));
  assert(ws43b_live::needsRefresh(m,ws43b_live::View::Dashboard,0,true,61002));

  seed(m);
  assert(report(m,R"({"print":{"subtask_name":"renamed metadata"}})",61001));
  assert(m.subtaskName.current(61001) && !m.status.current(61001));
  assert(!m.nozzleTemp.current(61001) && !m.amsUnits[0].temp.current(61001));
  assert(report(m,R"({"print":{"ams":{"tray_now":"0"}}})",61002));
  assert(m.activeTrayRaw.current(61002) && !m.amsUnits[0].temp.current(61002));
  assert(!m.status.current(61002));

  seed(m);
  // Other valid live core families retain non-job values, never the job stream.
  assert(report(m,R"({"print":{"fan_gear":0,"spd_lvl":3}})",61001));
  assert(m.nozzleTemp.current(61001) && m.amsUnits[0].temp.current(61001));
  assert(!m.status.current(61001) && !m.progress.current(61001));
}

void invalid_and_empty() {
  BambuMonitorTelemetry m;seed(m);
  const auto stamp=m.nozzleTemp.retainedMs;
  assert(!report(m,R"({"print":{"mc_percent":44}}) trailing)",61001));
  assert(m.progress.value==42 && m.nozzleTemp.retainedMs==stamp);
  // A valid ID proves identity, not new sensor/tray data for retention.
  report(m,R"({"print":{"ams":{"ams":[{"id":"0"}]}}})",61001);
  assert(!m.amsUnits[0].temp.current(61001));
  assert(!m.amsUnits[0].trays[0].remain.current(61001));
  report(m,R"({"print":{"ams":{"ams":[{"id":"0","temp":null,"humidity_raw":null,
    "tray":[{"id":"0","remain":-1}]}]}}})",61002);
  assert(!m.amsUnits[0].temp.valid && !m.amsUnits[0].humidityRaw.valid);
  assert(!m.amsUnits[0].trays[0].remain.valid);
  assert(!m.amsUnits[0].trays[1].remain.current(61002));
  // Live core can retain known siblings but cannot resurrect explicit unknowns.
  assert(report(m,R"({"print":{"layer_num":85,"nozzle_temper":null}})",61003));
  assert(!m.nozzleTemp.valid && !m.nozzleTemp.current(61003));
  assert(!m.amsUnits[0].temp.current(61003) && !m.amsUnits[0].humidityRaw.current(61003));
  assert(!m.amsUnits[0].trays[0].remain.current(61003));
  assert(m.amsUnits[0].trays[1].remain.current(61003));
  assert(report(m,R"({"print":{"ams":{"ams":[{"id":"0","tray":[{"id":"1","tray_type":""}]}]}}})",61004));
  const auto &empty=m.amsUnits[0].trays[1];
  assert(empty.present.valid && !empty.present.value);
  assert(!empty.colorRgb565.valid && !empty.remain.valid);
  assert(report(m,R"({"print":{"mc_percent":44}})",61005));
  assert(!empty.remain.current(61005) && !empty.colorRgb565.current(61005));
  MonitorField<int> missing;missing.retain(61005);assert(!missing.valid && !missing.current(61005));
  MonitorText<8> text;text.set("old",100);text.invalidate(200);text.retain(61005);
  assert(!text.valid && !text.current(61005));
}

void boundaries_and_offline() {
  BambuMonitorTelemetry m;seed(m);
  assert(report(m,R"({"print":{"gcode_state":"FINISH"}})",200));
  assert(report(m,R"({"print":{"gcode_state":"PREPARE"}})",61001));
  assert(m.status.current(61001));
  assert(!m.progress.valid && !m.layerNum.valid && !m.totalLayers.valid);
  assert(!m.remainingMinutes.valid && !m.subtaskName.valid && !m.printStage.valid);
  assert(!m.printedLayerSeen && !ws43b_view::progressCurrent(m,true,61001));
  assert(report(m,R"({"print":{"bed_temper":50}})",61002));
  assert(!m.progress.current(61002));
  const auto oldSession=m.session;m.newSession();
  assert(m.session==oldSession+1 && !m.hasUsefulData);
  assert(!m.status.valid && !m.nozzleTemp.valid && !m.amsUnits[0].used);
  assert(report(m,R"({"print":{"bed_temper":51}})",61003));
  assert(!m.status.current(61003) && !m.progress.current(61003));

  seed(m);
  assert(report(m,R"({"print":{"mc_remaining_time":29}})",61001));
  assert(ws43b_view::statusCurrent(m,true,61001));
  assert(!ws43b_view::statusCurrent(m,false,61001));
  assert(!ws43b_view::progressCurrent(m,false,61001));
  assert(ws43b_view::activity(m,false,61001,false)==ws43b_view::Activity::Offline);
  assert(ws43b_view::saver(m,false,61001,false,false)==ws43b_view::Saver::Clock);
  assert(!ws43b_live::needsRefresh(m,ws43b_live::View::Dashboard,0,false,61001));
  const auto live=ws43b_live::signature(m,ws43b_live::View::Dashboard,0,true,61001);
  assert(live!=ws43b_live::signature(m,ws43b_live::View::Dashboard,0,false,61001));
  // Full silence belongs to connection recovery rather than visible-field polling.
  assert(!ws43b_live::needsRefresh(m,ws43b_live::View::Dashboard,0,true,121002));
}

void empty_ams_inventory() {
  BambuMonitorTelemetry m;seed(m);
  assert(ws43b_view::dryingUnit(m,true,100)!=nullptr);
  // Omitted inventory is a delta, not a disconnected AMS declaration.
  assert(report(m,R"({"print":{"mc_percent":43,"ams":{"tray_now":"1"}}})",61001));
  assert(m.amsUnits[0].used && m.amsUnits[1].used);
  assert(m.amsUnits[0].dryRemainMin.current(61001));
  assert(ws43b_view::dryingUnit(m,true,61001)!=nullptr);
  // Explicit empty inventory wins over retention from core in the same report.
  assert(report(m,R"({"print":{"mc_percent":44,"ams":{"ams":[]}}})",61002));
  for(const auto &unit:m.amsUnits) {
    assert(!unit.used && !unit.present.valid && !unit.dryRemainMin.valid);
    for(const auto &tray:unit.trays)
      assert(!tray.present.valid && !tray.type.valid && !tray.remain.valid);
  }
  assert(!m.activeTrayRaw.valid);
  assert(ws43b_view::dryingUnit(m,true,61002)==nullptr);
  assert(report(m,R"({"print":{"layer_num":85,"bed_temper":60}})",61003));
  for(const auto &unit:m.amsUnits)assert(!unit.used && !unit.dryRemainMin.current(61003));
  assert(!m.activeTrayRaw.current(61003));
  assert(ws43b_view::dryingUnit(m,true,61003)==nullptr);
  // External spool/none sentinels do not describe an AMS that disappeared.
  for(unsigned raw:{254u,255u}) {
    seed(m);m.activeTrayRaw.set(static_cast<uint8_t>(raw),100);
    assert(report(m,R"({"print":{"mc_percent":44,"ams":{"ams":[]}}})",61001));
    assert(m.activeTrayRaw.valid && m.activeTrayRaw.value==raw);
    for(const auto &unit:m.amsUnits)assert(!unit.used);
  }
}

void wraparound() {
  BambuMonitorTelemetry m;seed(m,0xffff0000u);
  assert(!m.status.fresh(0x10u));
  assert(report(m,R"({"print":{"layer_num":85}})",0x10u));
  assert(m.status.current(0x10u) && !m.status.fresh(0x10u));
  assert(m.status.updatedMs==0xffff0000u && m.status.retainedMs==0x10u);
  assert(m.nozzleTemp.current(0x10u) && m.amsUnits[0].temp.current(0x10u));
  assert(ws43b_view::progressCurrent(m,true,0x10u));
  assert(!ws43b_live::needsRefresh(m,ws43b_live::View::Dashboard,0,true,0x10u));
  assert(m.status.current(0x10u+60000u) && !m.status.current(0x10u+60001u));
}

int main(int argc,char **argv) {
  assert(argc==2);const std::string name=argv[1];
  if(name=="retained_delta")retained_delta();
  else if(name=="domain_isolation")domain_isolation();
  else if(name=="invalid_and_empty")invalid_and_empty();
  else if(name=="boundaries_and_offline")boundaries_and_offline();
  else if(name=="empty_ams_inventory")empty_ams_inventory();
  else if(name=="wraparound")wraparound();
  else return 2;
  std::cout<<"PASS: "<<name<<'\n';
}
'''


class MonitorDeltaRetention(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('clang++') or shutil.which('c++')
        if not compiler:
            raise unittest.SkipTest('Native C++ compiler required')
        cls.folder = tempfile.TemporaryDirectory(prefix='bambu-delta-retention-')
        cls.addClassCleanup(cls.folder.cleanup)
        directory = Path(cls.folder.name)
        cpp = directory / 'test.cpp'
        cls.binary = directory / 'test'
        cpp.write_text(HARNESS)
        result = subprocess.run(
            [compiler, '-std=c++17', '-fsanitize=address,undefined',
             '-I', str(ROOT / 'include'), '-I', str(JSON_INCLUDE),
             str(cpp), '-o', str(cls.binary)], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stderr)

    def run_case(self, name):
        result = subprocess.run([str(self.binary), name], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS: ' + name, result.stdout)

    def test_unchanged_values_survive_deltas_without_rewriting_observation_age(self):
        self.run_case('retained_delta')

    def test_job_core_and_ams_streams_do_not_hide_each_others_stagnation(self):
        self.run_case('domain_isolation')

    def test_invalid_packets_fields_and_empty_slots_cannot_be_resurrected(self):
        self.run_case('invalid_and_empty')

    def test_new_job_session_and_offline_boundaries(self):
        self.run_case('boundaries_and_offline')

    def test_explicit_empty_ams_inventory_cannot_reappear_from_core_deltas(self):
        self.run_case('empty_ams_inventory')

    def test_wrap_safe_retention_and_expiry(self):
        self.run_case('wraparound')


if __name__ == '__main__':
    unittest.main()
