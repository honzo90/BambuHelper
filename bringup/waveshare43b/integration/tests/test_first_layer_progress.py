"""Advanced first-layer policy differs from the saver's current MQTT progress."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class FirstLayerProgress(unittest.TestCase):
    def test_first_layer_evidence_sparse_fields_and_activity_precedence(self):
        display = (ROOT / 'src/display_ws43b.cpp').read_text()
        start = display.index('bool clockHasProgress(')
        clock_gate = display[start:display.index('bool coolingView(', start)]
        start = display.index('uint16_t saverFilamentColor(const BambuMonitorTelemetry &m')
        filament = display[start:display.index('void saverAnimation(', start)]
        code = r'''
#include "ws43b_dashboard_policy.h"
#include "ws43b_live_view.h"
#include <cassert>
#include <initializer_list>
using namespace ws43b_view;
''' + clock_gate + filament + r'''
BambuMonitorTelemetry active(const char *status="RUNNING",uint32_t now=100) {
 BambuMonitorTelemetry m;
 m.status.set(status,now);m.progress.set(12,now);m.remainingMinutes.set(80,now);
 m.printStage.set(0,now);return m;
}
void visible(const BambuMonitorTelemetry &m,uint32_t now=100) {
 assert(statusCurrent(m,true,now));assert(progressCurrent(m,true,now));
 assert(!beforeFirstLayer(m,true,now));assert(printProgressVisible(m,true,now));
 assert(clockHasProgress(m,true,now));
}
void preparing(const BambuMonitorTelemetry &m,uint32_t now=100) {
 // The gate is a presentation decision, never a stale/absent telemetry result.
 assert(statusCurrent(m,true,now));assert(progressCurrent(m,true,now));
 assert(beforeFirstLayer(m,true,now));assert(!printProgressVisible(m,true,now));
 // The saver deliberately differs from advanced Wydruk: show the MQTT value.
 assert(clockHasProgress(m,true,now));assert(saver(m,true,now,false,false)==Saver::Print);
}
int main() {
 auto m=active();visible(m); // Missing layer and ordinary RUNNING retain compatibility.
 assert(activity(m,true,100,false)==Activity::Printing);
 m.layerNum.set(0,100);preparing(m);
 assert(activity(m,true,100,false)==Activity::Preparing);
 const auto percent=m.progress.value;const auto progressAge=m.progress.updatedMs;
 // Layer alone can reveal the same percentage; it need not arrive again.
 m.layerNum.set(1,101);visible(m,101);
 assert(m.progress.value==percent&&m.progress.updatedMs==progressAge);
 assert(activity(m,true,101,false)==Activity::Printing);
 // Current positive evidence also protects hosts/session recovery before latch update.
 m.printStage.set(14,101);visible(m,101);
 assert(activity(m,true,101,false)==Activity::Cleaning);
 m.printedLayerSeen=true;m.layerNum.set(0,102);m.printStage.set(0,102);visible(m,102);
 m.progress.set(100,102);visible(m,102); // End-of-print layer reset must not hide 100%.
 m.layerNum.invalidate(103);visible(m,103);
 m.status.set("PAUSE",104);visible(m,104);
 assert(activity(m,true,104,false)==Activity::Pause&&saver(m,true,104,false,false)==Saver::Pause);
 m.status.set("RUNNING",105);visible(m,105);
 m.status.set("FINISH",106);
 assert(!beforeFirstLayer(m,true,106)&&printProgressVisible(m,true,106));
 assert(!clockHasProgress(m,true,106));
 assert(activity(m,true,106,false)==Activity::Finished);
 m.newSession();assert(!m.printedLayerSeen&&!printProgressVisible(m,true,107));

 m=active("PREPARE");preparing(m);
 assert(activity(m,true,100,false)==Activity::Preparing);
 m.layerNum.set(1,100);visible(m); // Explicit first layer beats the PREPARE label.
 m=active();
 const int preparationStages[]={1,2,3,7,8,9,10,11,12,13,14,15,18,19,40,47,48,51};
 for(int stage:preparationStages) {
  m.printStage.set(stage,100);preparing(m);
  if(stage==14)assert(activity(m,true,100,false)==Activity::Cleaning);
  if(stage==51)assert(activity(m,true,100,false)==Activity::CalibrationLines);
  if(stage==1||stage==40||stage==47||stage==48)assert(activity(m,true,100,false)==Activity::Leveling);
  if(stage==2||stage==7)assert(activity(m,true,100,false)==Activity::Heating);
 }
 for(int stage:{0,-1,255,4,22,24,999}) {
  m.printStage.set(stage,100);visible(m);
 }
 // A stale stage alone cannot assert preparation or refresh a job.
 m=active("RUNNING",70000);m.printStage.set(14,1);visible(m,70000);
 m=active();m.layerNum.set(0,100);m.remainingMinutes.set(79,70000);preparing(m,70000);
 assert(!m.progress.fresh(70000)&&!m.status.fresh(70000));
 m.layerNum.set(1,70001);visible(m,70001);
 m.printedLayerSeen=true;m.layerNum.invalidate(70002);m.remainingMinutes.set(78,140000);visible(m,140000);
 m.nozzleTemp.set(220,200001);
 assert(!statusCurrent(m,true,200001)&&!progressCurrent(m,true,200001));
 assert(!beforeFirstLayer(m,true,200001)&&!printProgressVisible(m,true,200001));
 assert(!clockHasProgress(m,true,200001));
 assert(activity(m,true,200001,false)==Activity::Unknown);
 m=active();m.layerNum.set(0,100);
 assert(!statusCurrent(m,false,100)&&!beforeFirstLayer(m,false,100)&&!printProgressVisible(m,false,100));
 assert(activity(m,false,100,false)==Activity::Offline);
 assert(!clockHasProgress(m,false,100));
 m.progress.invalidate(100);assert(beforeFirstLayer(m,true,100)&&!printProgressVisible(m,true,100));
 assert(!clockHasProgress(m,true,100));
 m=active();m.layerNum.set(0,100);m.status.invalidate(100);
 assert(!beforeFirstLayer(m,true,100)&&!printProgressVisible(m,true,100));
 assert(!clockHasProgress(m,true,100));
 // The activity hierarchy for fault, pause and cooling remains authoritative.
 for(const char *status:{"IDLE","FINISH","FAILED","PAUSE","unknown"}) {
  m=active(status);m.layerNum.set(0,100);assert(!beforeFirstLayer(m,true,100));
 }
 m=active();m.layerNum.set(0,100);assert(activity(m,true,100,true)==Activity::Cooling);
 // Freshness boundaries are inclusive and unsigned wrap remains supported.
 m=active("RUNNING",0xfffffff0u);m.layerNum.set(0,0xfffffff0u);preparing(m,20);
 m.layerNum.set(1,20);visible(m,20);
 m=active();m.layerNum.set(0,100);preparing(m,60100);
 assert(!printProgressVisible(m,true,60101)&&!beforeFirstLayer(m,true,60101));
 // Black is valid material metadata and must not affect the first-layer gate.
 m=active();m.layerNum.set(1,100);auto &unit=m.amsUnits[0];unit.used=true;unit.id=2;
 unit.trays[0].colorRgb565.set(0,100);m.activeTrayRaw.set(8,100);
 visible(m);assert(saverFilamentColor(m,true,100)==0);
 // Layer/latch changes still update the preparation subtitle and animation,
 // even though the saver keeps showing the unchanged MQTT percentage.
 m=active();m.layerNum.set(0,100);
 auto signature=[&](ws43b_live::View view){return ws43b_live::signature(m,view,0,true,100);};
 auto clockBefore=signature(ws43b_live::View::Clock);
 m.layerNum.set(1,100);assert(signature(ws43b_live::View::Clock)!=clockBefore);
 m.layerNum.set(0,100);clockBefore=signature(ws43b_live::View::Clock);
 const auto dashboardBefore=signature(ws43b_live::View::Dashboard);
 const auto gaugesBefore=signature(ws43b_live::View::Gauges);
 const auto amsBefore=signature(ws43b_live::View::Ams);
 m.printedLayerSeen=true;
 assert(signature(ws43b_live::View::Clock)!=clockBefore);
 assert(signature(ws43b_live::View::Dashboard)!=dashboardBefore);
 assert(signature(ws43b_live::View::Gauges)!=gaugesBefore);
 assert(signature(ws43b_live::View::Ams)==amsBefore);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p / 'test.cpp').write_text(code)
            result = subprocess.run([
                'clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', '-I', str(ROOT / 'include'),
                str(p / 'test.cpp'), '-o', str(p / 'test'),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(p / 'test')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
