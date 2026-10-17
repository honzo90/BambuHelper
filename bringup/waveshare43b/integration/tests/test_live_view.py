"""Live-screen scheduling and stale recovery without falsifying observations."""
from pathlib import Path
import re, subprocess, tempfile, unittest
ROOT=Path(__file__).resolve().parents[4]

class LiveView(unittest.TestCase):
 def test_humidity_recovery_tracks_the_displayed_sensor(self):
  code=r'''
#include "ws43b_live_view.h"
#include <cassert>
using namespace ws43b_live;
int main(){
 constexpr uint32_t now=100000, old=100;
 BambuMonitorTelemetry m;m.hasUsefulData=true;m.lastUsefulMs=now;
 m.status.set("RUNNING",now);
 auto &u=m.amsUnits[0];u.used=true;u.present.set(true,now);
 u.temp.set(50,now);u.dryRemainMin.set(60,now);
 auto refresh=[&](View v){return needsRefresh(m,v,0,true,now);};
 auto sig=[&](View v){return signature(m,v,0,true,now);};
 u.humidityRaw.set(14,now);u.humidity.set(3,old);
 assert(amsHumidityUsesRaw(u,now));
 for(auto v:{View::Dashboard,View::Ams,View::Clock,View::Gauges})assert(!refresh(v));
 const auto dashboard=sig(View::Dashboard),ams=sig(View::Ams);
 const auto clock=sig(View::Clock),gauges=sig(View::Gauges);
 u.humidity.set(4,old+1); // Hidden old level must neither poll nor repaint.
 assert(sig(View::Dashboard)==dashboard&&sig(View::Ams)==ams);
 assert(sig(View::Clock)==clock&&sig(View::Gauges)==gauges);
 assert(u.humidityRaw.updatedMs==now&&u.humidity.updatedMs==old+1);

 u.humidityRaw.set(14,old);u.humidity.set(3,now);
 assert(!amsHumidityUsesRaw(u,now));
 assert(!refresh(View::Dashboard)&&!refresh(View::Ams));
 assert(refresh(View::Clock)&&refresh(View::Gauges)); // These display raw RH.
 const auto fallback=sig(View::Ams);
 u.humidityRaw.set(15,old+1);assert(sig(View::Ams)==fallback);
 u.humidityRaw.set(3,now); // Same numeric value, different source and unit.
 assert(amsHumidityUsesRaw(u,now)&&sig(View::Ams)!=fallback);
 u.humidity.set(2,now+1);assert(amsHumidityUsesRaw(u,now+1)); // Prefer current RH.

 u.humidityRaw.set(14,old+2);u.humidity.set(3,old+1);
 assert(amsHumidityUsesRaw(u,now));
 for(auto v:{View::Dashboard,View::Ams,View::Clock,View::Gauges})assert(refresh(v));
 u.humidity.set(3,old+3);assert(!amsHumidityUsesRaw(u,now));
 assert(refresh(View::Ams)); // Both stale: recover the newer visible reading.

 u.humidityRaw.invalidate(now);u.humidity.set(3,now);
 assert(!refresh(View::Ams)&&!refresh(View::Clock)&&!refresh(View::Gauges));
 auto unknownRh=sig(View::Clock);u.humidity.set(4,old);
 assert(refresh(View::Ams)&&refresh(View::Gauges));
 assert(!refresh(View::Clock)&&sig(View::Clock)==unknownRh); // No coarse RH fallback.
 u.humidity.invalidate(now);
 for(auto v:{View::Dashboard,View::Ams,View::Clock,View::Gauges})assert(!refresh(v));
 u.humidityRaw.set(0,now);u.humidity.set(3,old);
 assert(!refresh(View::Ams)&&!refresh(View::Clock)); // Zero is a valid RH value.
 assert(refresh(View::Gauges)); // Its coarse fallback color is actually visible.
 u.humidityRaw.set(14,old);u.dryRemainMin.set(0,now);
 assert(!refresh(View::Clock)); // No drying card: no RH recovery interest.

 // Newer stale reading selection remains correct across millis() rollover.
 u.humidityRaw.set(14,0xfffffff0u);u.humidity.set(3,0xffffffe0u);
 assert(amsHumidityUsesRaw(u,100000));
 u.humidity.set(3,10);assert(!amsHumidityUsesRaw(u,100000));
}
'''
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);(p/'test.cpp').write_text('#include <initializer_list>\n'+code)
   r=subprocess.run(['clang++','-std=c++17','-fsanitize=address,undefined','-I',str(ROOT/'include'),str(p/'test.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
   r=subprocess.run([str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)

 def test_priority_delta_stale_and_request_budget(self):
  code=r'''
#include "ws43b_live_view.h"
#include <cassert>
using namespace ws43b_live;
int main(){
 BambuMonitorTelemetry m;m.hasUsefulData=true;m.lastUsefulMs=100;
 m.status.set("RUNNING",100);m.nozzleTemp.set(200,100);
 auto sig=[&](View v,uint32_t now){return signature(m,v,0,true,now);};
 auto dash=sig(View::Dashboard,100),details=sig(View::Details,100);
 m.nozzleTemp.set(210,110);
 assert(sig(View::Dashboard,110)!=dash && sig(View::Details,110)==details);
 dash=sig(View::Dashboard,110);m.nozzleTemp.set(210,120);
 assert(sig(View::Dashboard,120)==dash); // identical value, later observation
 m.chamberTemp.set(36,130);assert(sig(View::Details,130)!=details);
 assert(deferForRx(399,0,true,true,false));
 assert(!deferForRx(400,0,true,true,false));
 assert(!deferForRx(10,0,true,false,false)&&!deferForRx(10,0,true,true,true));
 assert(!deferForRx(10,0,false,true,false));
 assert(!repaintDue(199,0,2,1)&&repaintDue(200,0,2,1));
 assert(!repaintDue(1000,0,1,1)&&repaintDue(100,0xffffff00u,2,1));
 auto &u=m.amsUnits[0];u.used=true;u.dryRemainMin.set(30,100);u.temp.set(50,100);
 auto clock=sig(View::Clock,130);u.temp.set(51,140);assert(sig(View::Clock,140)!=clock);
 m.lastUsefulMs=60200;m.status.set("RUNNING",60200);m.chamberTemp.set(37,60200);
 assert(needsRefresh(m,View::Dashboard,0,true,60200));
 assert(!needsRefresh(m,View::Details,0,true,60200)); // hidden stale nozzle
 assert(!needsRefresh(m,View::Dashboard,0,false,60200));
 assert(!needsRefresh(m,View::Dashboard,0,true,122201)); // total silence
 assert(m.nozzleTemp.updatedMs==120 && !m.nozzleTemp.fresh(60200));
 m.nozzleTemp.invalidate(60200);u.temp.invalidate(60200);u.dryRemainMin.invalidate(60200);
 m.subtaskName.set("Unchanged job",100);m.totalLayers.set(291,100);
 assert(!needsRefresh(m,View::Dashboard,0,true,60200)); // metadata/unknown not a poll loop
 m.nozzleTemp.set(0,60200);assert(!needsRefresh(m,View::Dashboard,0,true,60200));
 auto before=sig(View::Dashboard,60200);m.nozzleTemp.invalidate(60200);
 assert(sig(View::Dashboard,60200)!=before); // explicit invalidation also repaints
 RefreshGate gate;
 assert(!gate.due(120099,100,100,120000,true));
 assert(gate.due(120100,100,100,120000,true));gate.mark(120100);
 assert(!gate.due(120101,100,100,120000,true)); // failed publish backs off too
 assert(!gate.due(240100,100,200000,120000,true)); // shared with periodic/recovery
 assert(gate.due(240100,100,100,120000,true));
 assert(!gate.due(240100,100,100,120000,false));
 gate={};assert(gate.due(40000,0xffff0000u,0xffff0000u,30000,true));
 m.newSession();assert(!needsRefresh(m,View::Dashboard,0,true,60200)&&!m.nozzleTemp.valid);
}
'''
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);(p/'test.cpp').write_text(code)
   r=subprocess.run(['clang++','-std=c++17','-fsanitize=address,undefined','-I',str(ROOT/'include'),str(p/'test.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
   r=subprocess.run([str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)

 def test_effective_loop_order_and_single_service(self):
  source=(ROOT/'src/main.cpp').read_text();source=source[source.index('void loop() {'):]
  source=re.sub(r'^\s*#include[^\n]*\n','',source,flags=re.M)
  for board in (False,True):
   r=subprocess.run(['clang++','-E','-P','-x','c++','-DBAMBU_MONITOR_ONLY=0',*(['-DBOARD_IS_WS43B=1'] if board else []),'-'],input=source,text=True,capture_output=True)
   self.assertEqual(r.returncode,0,r.stderr);s=r.stdout
   self.assertEqual(s.count('handleBambuMqtt();'),1)
   self.assertEqual(s.count('handleWakeButton();'),1)
   self.assertLess(s.index('handleWakeButton();'),s.index('handleBambuMqtt();'))
   if board:
    self.assertLess(s.index('handleBambuMqtt();'),s.index('updateDisplayedPrinterScreenState();'))
    self.assertLess(s.index('handleBambuMqtt();'),s.index('updateDisplay();'))
   else:self.assertLess(s.index('updateDisplay();'),s.index('handleBambuMqtt();'))
