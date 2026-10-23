"""Independent WS43B Waiting policy contract; host only, no network or hardware."""
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
#include <cassert>
#include <cstring>
#include <iostream>
#include <string>
using namespace ws43b_view;

bool report(BambuMonitorTelemetry &m, const char *json, uint32_t now) {
  return bambu_monitor::parse(reinterpret_cast<const uint8_t *>(json), strlen(json), m, now);
}
void seed(BambuMonitorTelemetry &m, uint32_t now=100, const char *state="RUNNING") {
  m.newSession();
  assert(report(m, R"({"print":{"gcode_state":"RUNNING","mc_percent":42,
    "layer_num":84,"total_layer_num":200,"mc_remaining_time":30,
    "nozzle_temper":220,"bed_temper":60,
    "ams":{"ams":[{"id":"0","temp":39,"humidity_raw":"15","dry_time":30}]}}})", now));
  m.status.set(state, now);
}
void expect_waiting(const BambuMonitorTelemetry &m, uint32_t now) {
  assert(!statusCurrent(m,true,now));
  assert(!progressCurrent(m,true,now));
  assert(waitingForJobData(m,true,now,true));
  assert(saver(m,true,now,false,false,true)==Saver::Waiting);
  // Neither a cooling hint nor a cached percentage masks the missing job stream.
  assert(saver(m,true,now,true,false,true)==Saver::Waiting);
  assert(saver(m,true,now,false,true,true)==Saver::Alert);
  assert(saver(m,true,now,true,true,true)==Saver::Alert);
}

void boundary_and_gates() {
  for(const char *state:{"RUNNING","PREPARE"}) {
    BambuMonitorTelemetry m; seed(m,100,state);
    for(uint32_t now:{100u,60099u,60100u}) {
      assert(statusCurrent(m,true,now));
      assert(!waitingForJobData(m,true,now,true));
      assert(saver(m,true,now,false,false,true)==Saver::Print);
    }
    for(uint32_t now:{60101u,300100u,3600100u}) {
      expect_waiting(m,now);
      assert(!waitingForJobData(m,true,now,false));
      assert(!waitingForJobData(m,false,now,true));
      assert(!waitingForJobData(m,false,now,false));
      assert(saver(m,false,now,false,false,true)==Saver::Clock);
      assert(saver(m,false,now,true,true,true)==Saver::Clock);
      assert(saver(m,true,now,false,false)==Saver::Clock);
      assert(saver(m,true,now,true,true)==Saver::Clock);
      assert(saver(m,true,now,true,true,false)==Saver::Clock);
    }
  }
}

void excluded_states() {
  for(const char *state:{"PAUSE","FINISH","FAILED","IDLE","UNKNOWN",""}) {
    BambuMonitorTelemetry m; seed(m,100,state);
    for(uint32_t now:{100u,60100u,60101u,3600100u}) {
      assert(!waitingForJobData(m,true,now,true));
      const auto chosen=saver(m,true,now,false,false,true);
      assert(chosen!=Saver::Waiting && chosen!=Saver::Print);
      if(!strcmp(state,"PAUSE"))
        assert(chosen==(now<=60100u?Saver::Pause:Saver::Clock));
    }
    // Fresh job fields cannot convert a stale PAUSE or ended job into RUNNING.
    m.progress.set(43,61001); m.layerNum.set(85,61001); m.remainingMinutes.set(29,61001);
    assert(!waitingForJobData(m,true,61001,true));
    assert(saver(m,true,61001,false,false,true)!=Saver::Print);
    assert(saver(m,true,61001,false,false,true)!=Saver::Waiting);
  }
  BambuMonitorTelemetry missing;
  assert(!waitingForJobData(missing,true,100,true));
  assert(saver(missing,true,100,false,false,true)==Saver::Clock);
  seed(missing); missing.status.invalidate(61001);
  assert(!waitingForJobData(missing,true,61001,true));
  assert(saver(missing,true,61001,false,false,true)==Saver::Clock);
}

void independent_job_delta_freshness() {
  // Exercise the policy's actual-field fallback independently of parser retention.
  for(int field=0;field<3;++field) {
    BambuMonitorTelemetry m; seed(m);
    const uint32_t now=61001;
    if(field==0)m.progress.set(43,now);
    if(field==1)m.layerNum.set(85,now);
    if(field==2)m.remainingMinutes.set(29,now);
    assert(!m.status.current(now));
    assert(statusCurrent(m,true,now));
    assert(progressCurrent(m,true,now));
    assert(!waitingForJobData(m,true,now,true));
    assert(saver(m,true,now,true,false,true)==Saver::Print);
    assert(!waitingForJobData(m,true,now+60000u,true));
    expect_waiting(m,now+60001u);
  }
}

void unrelated_traffic_isolation() {
  BambuMonitorTelemetry m; seed(m);
  assert(report(m,R"({"print":{"ams":{"ams":[{"id":"0","temp":40,"humidity_raw":"14"}]}}})",61001));
  assert(m.amsUnits[0].temp.current(61001));
  assert(m.amsUnits[0].humidityRaw.current(61001));
  expect_waiting(m,61001);
  assert(report(m,R"({"print":{"nozzle_temper":219,"bed_temper":59}})",61002));
  assert(m.nozzleTemp.current(61002) && m.bedTemp.current(61002));
  assert(m.amsUnits[0].temp.current(61002));
  expect_waiting(m,61002);
  assert(m.status.updatedMs==100 && m.status.retainedMs==100);
  assert(m.progress.updatedMs==100 && m.progress.retainedMs==100);
  assert(m.layerNum.updatedMs==100 && m.layerNum.retainedMs==100);
  assert(m.remainingMinutes.updatedMs==100 && m.remainingMinutes.retainedMs==100);
  assert(m.progress.value==42 && m.layerNum.value==84 && m.remainingMinutes.value==30);
  assert(report(m,R"({"print":{"nozzle_temper":218,"ams":{"ams":[{"id":"0","humidity_raw":"13"}]}}})",3600100));
  assert(m.nozzleTemp.current(3600100) && m.amsUnits[0].humidityRaw.current(3600100));
  expect_waiting(m,3600100);
  assert(m.status.retainedMs==100 && m.progress.retainedMs==100);
}

void actual_job_delta_resumption() {
  for(const char *delta:{R"({"print":{"mc_percent":43}})",
                        R"({"print":{"layer_num":85}})",
                        R"({"print":{"mc_remaining_time":29}})"}) {
    BambuMonitorTelemetry m; seed(m);
    expect_waiting(m,61001);
    assert(report(m,delta,61002));
    assert(m.status.updatedMs==100 && m.status.retainedMs==61002);
    assert(statusCurrent(m,true,61002) && progressCurrent(m,true,61002));
    assert(!waitingForJobData(m,true,61002,true));
    assert(saver(m,true,61002,false,false,true)==Saver::Print);
    assert(!waitingForJobData(m,true,121002,true));
    expect_waiting(m,121003);
  }
}

void reconnect_and_session_reset() {
  BambuMonitorTelemetry m; seed(m); expect_waiting(m,61001);
  assert(!waitingForJobData(m,false,61001,true));
  const auto session=m.session; m.newSession();
  assert(m.session==session+1 && !m.status.valid && !m.progress.valid);
  for(uint32_t now:{61001u,121002u,3600100u}) {
    assert(!waitingForJobData(m,true,now,true));
    assert(!statusCurrent(m,true,now) && !progressCurrent(m,true,now));
    assert(saver(m,true,now,false,false,true)==Saver::Clock);
  }
  // Reconnection plus live temperatures/AMS is still no evidence of a new job.
  assert(report(m,R"({"print":{"bed_temper":51,"ams":{"ams":[{"id":"0","temp":38}]}}})",3600101));
  assert(!m.status.valid && !m.progress.valid);
  assert(!waitingForJobData(m,true,3600101,true));
  assert(saver(m,true,3600101,false,false,true)==Saver::Clock);
  assert(report(m,R"({"print":{"gcode_state":"RUNNING","mc_percent":1}})",3600102));
  assert(saver(m,true,3600102,false,false,true)==Saver::Print);
}

void rollover() {
  constexpr uint32_t start=0xffffff00u;
  BambuMonitorTelemetry m; seed(m,start);
  const uint32_t boundary=start+60000u;
  const uint32_t stale=start+60001u;
  assert(boundary<start && stale<start);
  assert(statusCurrent(m,true,boundary));
  assert(!waitingForJobData(m,true,boundary,true));
  expect_waiting(m,stale);
  assert(report(m,R"({"print":{"mc_remaining_time":29}})",stale+1u));
  assert(!waitingForJobData(m,true,stale+1u,true));
  assert(saver(m,true,stale+1u,false,false,true)==Saver::Print);
  expect_waiting(m,stale+60002u);
}

void no_mutation() {
  BambuMonitorTelemetry m; seed(m);
  unsigned char before[sizeof(m)]; memcpy(before,&m,sizeof(m));
  for(uint32_t now:{100u,60100u,60101u,3600100u})
    for(bool online:{false,true})for(bool core:{false,true})
      for(bool cooling:{false,true})for(bool alert:{false,true}) {
        (void)waitingForJobData(m,online,now,core);
        (void)saver(m,online,now,cooling,alert,core);
        (void)statusCurrent(m,online,now);
        (void)progressCurrent(m,online,now);
        assert(memcmp(before,&m,sizeof(m))==0);
      }
}

void default_contract() {
  struct Case { const char *state; uint32_t now; bool online,cooling,alert; Saver expected; };
  const Case cases[]={
    {"RUNNING",100,true,false,false,Saver::Print},
    {"PREPARE",100,true,false,false,Saver::Print},
    {"RUNNING",100,true,true,false,Saver::Print},
    {"PREPARE",100,true,true,false,Saver::Print},
    {"RUNNING",100,true,false,true,Saver::Alert},
    {"PAUSE",100,true,true,false,Saver::Pause},
    {"PAUSE",100,true,false,true,Saver::Alert},
    {"FINISH",100,true,true,false,Saver::Cooling},
    {"FINISH",100,true,false,false,Saver::Clock},
    {"FAILED",100,true,false,false,Saver::Clock},
    {"IDLE",100,true,false,false,Saver::Clock},
    {"IDLE",100,true,true,false,Saver::Cooling},
    {"RUNNING",60101,true,false,false,Saver::Clock},
    {"RUNNING",60101,true,true,true,Saver::Clock},
    {"PAUSE",60101,true,true,true,Saver::Clock},
    {"RUNNING",100,false,true,true,Saver::Clock},
    {"PAUSE",100,false,false,false,Saver::Clock}
  };
  for(const auto &c:cases) {
    BambuMonitorTelemetry m; seed(m,100,c.state);
    assert(saver(m,c.online,c.now,c.cooling,c.alert)==c.expected);
    assert(saver(m,c.online,c.now,c.cooling,c.alert,false)==c.expected);
  }
  BambuMonitorTelemetry m; seed(m); m.progress.invalidate(100);
  assert(saver(m,true,100,true,false)==Saver::Cooling);
}

int main(int argc,char **argv) {
  assert(argc==2); const std::string name=argv[1];
  if(name=="boundary_and_gates")boundary_and_gates();
  else if(name=="excluded_states")excluded_states();
  else if(name=="independent_job_delta_freshness")independent_job_delta_freshness();
  else if(name=="unrelated_traffic_isolation")unrelated_traffic_isolation();
  else if(name=="actual_job_delta_resumption")actual_job_delta_resumption();
  else if(name=="reconnect_and_session_reset")reconnect_and_session_reset();
  else if(name=="rollover")rollover();
  else if(name=="no_mutation")no_mutation();
  else if(name=="default_contract")default_contract();
  else return 2;
  std::cout<<"PASS: "<<name<<'\n';
}
'''


class WaitingPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('clang++')
        if not compiler:
            raise RuntimeError('clang++ is required; missing compiler is not a PASS')
        cls.folder = tempfile.TemporaryDirectory(prefix='ws43b-waiting-contract-')
        cls.addClassCleanup(cls.folder.cleanup)
        cpp = Path(cls.folder.name) / 'test.cpp'
        cls.binary = Path(cls.folder.name) / 'test'
        cpp.write_text(HARNESS, encoding='utf-8')
        result = subprocess.run(
            [compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
             '-Wno-deprecated-declarations', '-ferror-limit=3',
             '-I', str(ROOT / 'include'), '-I', str(JSON_INCLUDE),
             str(cpp), '-o', str(cls.binary)],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode:
            raise AssertionError('Contract harness failed to compile:\n' + result.stdout + result.stderr)

    def run_case(self, name):
        result = subprocess.run([str(self.binary), name], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS: ' + name, result.stdout)

    def test_60_second_boundary_connection_and_core_gates(self):
        self.run_case('boundary_and_gates')

    def test_pause_finished_failed_idle_and_invalid_do_not_become_waiting(self):
        self.run_case('excluded_states')

    def test_fresh_job_deltas_keep_the_job_current(self):
        self.run_case('independent_job_delta_freshness')

    def test_ams_and_temperature_reports_cannot_refresh_job_timestamps(self):
        self.run_case('unrelated_traffic_isolation')

    def test_real_parser_job_delta_restores_print_after_gap(self):
        self.run_case('actual_job_delta_resumption')

    def test_reconnect_requires_new_job_evidence(self):
        self.run_case('reconnect_and_session_reset')

    def test_unsigned_millisecond_rollover(self):
        self.run_case('rollover')

    def test_policy_calls_never_mutate_telemetry(self):
        self.run_case('no_mutation')

    def test_original_five_argument_saver_contract(self):
        self.run_case('default_contract')


if __name__ == '__main__':
    unittest.main(verbosity=2)
