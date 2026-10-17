from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[4]
class FilamentStages(unittest.TestCase):
 def test_partial_reports_freshness_and_state_changes(self):
  code=r'''#include "bambu_monitor_parser.h"
#include <cassert>
int main(){
 BambuMonitorTelemetry m;
 auto report=[&](const char*s,uint32_t t){return bambu_monitor::parse((const uint8_t*)s,strlen(s),m,t);};
 report(R"({"print":{"gcode_state":"RUNNING","stg_cur":4}})",100);
 assert(monitorFilamentStage(m,true,100)==4);
 report(R"({"print":{"bed_temper":55}})",200);
 assert(m.printStage.updatedMs==100 && monitorFilamentStage(m,true,200)==4);
 assert(monitorFilamentStage(m,false,200)==0);
 report(R"({"print":{"bed_temper":56}})",60101);
 assert(monitorFilamentStage(m,true,60101)==0); // Temperatures cannot renew job stages.
 report(R"({"print":{"gcode_state":"RUNNING"}})",60101);
 assert(monitorFilamentStage(m,true,60101)==4); // Same-job delta retains omitted stage.
 assert(m.printStage.updatedMs==100 && !m.printStage.fresh(60101));
 report(R"({"print":{"stg_cur":22}})",60102);assert(monitorFilamentStage(m,true,60102)==22);
 report(R"({"print":{"stg_cur":24}})",60103);assert(monitorFilamentStage(m,true,60103)==24);
 report(R"({"print":{"stg_cur":0}})",60104);assert(m.printStage.valid && monitorFilamentStage(m,true,60104)==0);
 for(const char*s:{"-1","255","7","99","null","true","4.5","256","-2","\"4\""}){
  char json[80];snprintf(json,sizeof(json),"{\"print\":{\"stg_cur\":%s}}",s);
  report(json,60105);assert(monitorFilamentStage(m,true,60105)==0);
 }
 report(R"({"print":{"stg_cur":4}})",60106);
 report(R"({"print":{"gcode_state":"PAUSE"}})",60107);assert(!m.printStage.valid);
 report(R"({"print":{"gcode_state":"RUNNING"}})",60108);assert(monitorFilamentStage(m,true,60108)==0);
 report(R"({"print":{"gcode_state":"FINISH","stg_cur":4}})",60109);assert(monitorFilamentStage(m,true,60109)==0);
 m.newSession();assert(!m.printStage.valid);
 report(R"({"print":{"gcode_state":"RUNNING","stg_cur":24}})",UINT32_MAX-20);
 assert(monitorFilamentStage(m,true,10)==24);
 assert(monitorFilamentStage(m,true,60000)==0);
}'''
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'test.cpp').write_text(code)
   subprocess.run(['clang++','-std=c++17','-Wno-deprecated-declarations','-I',str(ROOT/'include'),'-I',str(ROOT/'bringup/waveshare43b/integration/vendor/ArduinoJson-7.4.3/src'),str(p/'test.cpp'),'-o',str(p/'test')],check=True,capture_output=True)
   subprocess.run([str(p/'test')],check=True)
