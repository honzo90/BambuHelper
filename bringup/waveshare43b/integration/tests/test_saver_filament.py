from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[4]
class SaverFilament(unittest.TestCase):
 def test_slot_switch_staleness_and_black_filament(self):
  s=(ROOT/'src/display_ws43b.cpp').read_text()
  f=s[s.index('uint16_t saverFilamentColor(const BambuMonitorTelemetry &m'):s.index('void saverAnimation(')]
  code='#include "bambu_monitor.h"\n#include <cassert>\n'+f+r'''
int main(){
 BambuMonitorTelemetry m;
 auto &u=m.amsUnits[0];u.used=true;u.id=2;
 u.trays[0].colorRgb565.set(0,10);u.trays[1].colorRgb565.set(0xfd20,10);
 m.activeTrayRaw.set(8,70000);
 assert(saverFilamentColor(m,true,70000)==0); // valid black, cached metadata
 m.activeTrayRaw.set(9,70001);assert(saverFilamentColor(m,true,70001)==0xfd20);
 assert(saverFilamentColor(m,false,70001)==0xbdf7);
 assert(saverFilamentColor(m,true,140002)==0xfd20); // omitted tray_now is not a slot change
 m.activeTrayRaw.set(8,140003);assert(saverFilamentColor(m,true,140003)==0);
 m.activeTrayRaw.set(9,140004);assert(saverFilamentColor(m,true,140004)==0xfd20);
 u.trays[1].present.set(false,70002);assert(saverFilamentColor(m,true,70002)==0xbdf7);
 m.activeTrayRaw.set(254,70003);assert(saverFilamentColor(m,true,70003)==0xbdf7);
 m.activeTrayRaw.set(255,70004);assert(saverFilamentColor(m,true,70004)==0xbdf7);
 m.activeTrayRaw.invalidate(70005);assert(saverFilamentColor(m,true,70005)==0xbdf7);
 m.newSession();assert(saverFilamentColor(m,true,70004)==0xbdf7);
}
'''
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'test.cpp').write_text(code)
   subprocess.run(['clang++','-std=c++17','-I',str(ROOT/'include'),str(p/'test.cpp'),'-o',str(p/'test')],check=True,capture_output=True)
   subprocess.run([str(p/'test')],check=True,capture_output=True)
