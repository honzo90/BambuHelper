"""Exercise actual gauge freshness and caller gating with mixed AMS sensors."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class GaugeHumidityFreshness(unittest.TestCase):
    def test_raw_rh_freshness_unit_identity_presence_and_offline_rendering(self):
        display = (ROOT / 'src/display_ws43b.cpp').read_text()
        start = display.index('bool gaugeDataFresh(')
        functions = display[start:display.index('\n#endif', start)]
        settings = (ROOT / 'src/settings.h').read_text()
        start = settings.index('enum GaugeType :')
        gauge_types = settings[start:settings.index('\n};', start) + 3]
        harness = r'''
#include "bambu_monitor.h"
#include "ws43b_dashboard_policy.h"
#include <cassert>
#include <cstring>
#include <string>
constexpr unsigned GAUGE_SLOT_COUNT=6;
struct BambuState {
 BambuMonitorTelemetry monitor;
 struct {struct {bool present=false;uint8_t id=0;}units[6];}ams;
 bool dualNozzle=false;uint32_t airductFuncs=0;
};
struct PrinterSlot {struct {uint8_t gaugeSlots[GAUGE_SLOT_COUNT]{};}config;BambuState state;};
struct {uint8_t displayIndex=0;}rotState;
unsigned drawn=0, notices=0;
std::string lastNotice;
const char* ws43bText(const char*,const char* en){return en;}
void small(const char* text,int,int,int){++notices;lastNotice=text;}
void drawGaugeTile(uint8_t,const BambuState&,uint8_t,int,int,int,int,bool,bool){++drawn;}
'''
        cases = r'''
int main(){
 constexpr uint32_t now=100000, old=1;
 PrinterSlot slot;
 auto &s=slot.state;auto &m=s.monitor;
 m.hasUsefulData=true;m.lastUsefulMs=now;
 // Display order and monitor storage order intentionally differ, including HT IDs.
 for(unsigned i=0;i<4;++i){
  s.ams.units[i].present=true;s.ams.units[i].id=128+i;
  auto &u=m.amsUnits[5-i];u.used=true;u.id=128+i;u.present.set(true,now);
  u.humidityRaw.set(14+i,old);u.humidity.set(3,now);
  auto type=uint8_t(GAUGE_AMS_HUM_1+i);
  assert(!gaugeDataFresh(type,s,now)); // Fresh coarse data cannot freshen raw RH.
  u.humidityRaw.set(14+i,now);u.humidity.set(3,old);
  assert(gaugeDataFresh(type,s,now)); // Hidden stale coarse data cannot stale RH.
  u.humidityRaw.invalidate(now);u.humidity.set(3,now);
  assert(!gaugeDataFresh(type,s,now)); // Unknown RH is not zero or coarse percent.
  u.humidityRaw.set(0,now);assert(gaugeDataFresh(type,s,now));
  u.present.set(false,now);assert(!gaugeDataFresh(type,s,now));
  u.present.set(true,now);s.ams.units[i].present=false;
  assert(!gaugeDataFresh(type,s,now));s.ams.units[i].present=true;
  u.used=false;assert(!gaugeDataFresh(type,s,now));u.used=true;
  s.ams.units[i].id=42;assert(!gaugeDataFresh(type,s,now));s.ams.units[i].id=128+i;
 }
 // Call the actual renderer to prove connection state gates even fresh data.
 auto &u=m.amsUnits[5];slot.config.gaugeSlots[0]=GAUGE_AMS_HUM_1;
 gaugesScreen(slot,true,now);assert(drawn==1&&notices==0);
 drawn=notices=0;gaugesScreen(slot,false,now);
 assert(drawn==0&&notices==1&&lastNotice=="Outdated");
 u.humidityRaw.set(14,old);u.humidity.set(3,now);drawn=notices=0;
 gaugesScreen(slot,true,now);assert(drawn==0&&notices==1&&lastNotice=="No data");
 // Progress is fresh but deliberately hidden until the first reported layer.
 slot.config.gaugeSlots[0]=GAUGE_PROGRESS;m.status.set("RUNNING",now);
 m.progress.set(12,now);m.remainingMinutes.set(80,now);m.printStage.set(0,now);m.layerNum.set(0,now);
 assert(ws43b_view::progressCurrent(m,true,now)&&!gaugeDataFresh(GAUGE_PROGRESS,s,now));
 drawn=notices=0;gaugesScreen(slot,true,now);assert(drawn==0&&notices==1&&lastNotice=="Preparing");
 drawn=notices=0;gaugesScreen(slot,false,now);assert(drawn==0&&notices==1&&lastNotice=="Outdated");
 m.layerNum.set(1,now+1);assert(gaugeDataFresh(GAUGE_PROGRESS,s,now+1));
 drawn=notices=0;gaugesScreen(slot,true,now+1);assert(drawn==1&&notices==0&&m.progress.updatedMs==now);
 m.printedLayerSeen=true;m.layerNum.set(0,now+2);m.progress.set(100,now+2);
 assert(gaugeDataFresh(GAUGE_PROGRESS,s,now+2));
 drawn=notices=0;gaugesScreen(slot,false,now+2);assert(drawn==0&&notices==1&&lastNotice=="Outdated");
 m.remainingMinutes.invalidate(now+2);assert(!gaugeDataFresh(GAUGE_PROGRESS,s,now+2));
 slot.config.gaugeSlots[0]=GAUGE_AMS_HUM_1;
 u.humidityRaw.invalidate(now);drawn=notices=0;
 gaugesScreen(slot,true,now);assert(drawn==0&&notices==1&&lastNotice=="No data");
 // Freshness boundary is field-specific, inclusive and wrap-safe.
 u.humidityRaw.set(14,40000);assert(gaugeDataFresh(GAUGE_AMS_HUM_1,s,100000));
 assert(!gaugeDataFresh(GAUGE_AMS_HUM_1,s,100001));
 u.humidityRaw.set(14,0xfffffff0u);assert(gaugeDataFresh(GAUGE_AMS_HUM_1,s,20));
}
'''
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p / 'test.cpp').write_text(harness + gauge_types + functions + cases)
            subprocess.run(['clang++', '-std=c++17', '-fsanitize=address,undefined',
                            '-I', str(ROOT / 'include'), str(p / 'test.cpp'),
                            '-o', str(p / 'test')], check=True, capture_output=True, text=True)
            subprocess.run([str(p / 'test')], check=True, capture_output=True, text=True)


if __name__ == '__main__':
    unittest.main()
