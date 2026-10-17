from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[4]
class OtaDisplay(unittest.TestCase):
 def test_actual_backlight_lifecycle(self):
  s=(ROOT/'src/lgfx_panel_ws43b.cpp').read_text()
  body=s[s.index('static bool otaDisplayLocked='):s.index('bool readTouch(')]
  code=r'''
#include <cassert>
#include <cstdint>
#include <vector>
std::vector<int> events;
struct Light {bool ok=true;bool off(){events.push_back(0);return ok;}bool on(){events.push_back(1);return ok;}} light;
struct Board {Light*getBacklight(){return &light;}} board;
struct Lcd {void*getRefreshPanelHandle(){return nullptr;}} panel,*lcd=&panel;
bool boardReady=true;
void esp_lcd_rgb_panel_restart(void*){events.push_back(2);}
void delay(int t){assert(t==100);events.push_back(3);}
bool setBacklight(uint8_t);
''' + body + r'''
int main(){
 setBacklight(255);events.clear();assert(beginOtaDisplay());assert(otaDisplayActive());
 assert(!beginOtaDisplay());setBacklight(255);assert(events==std::vector<int>{0});
 endOtaDisplay();assert(!otaDisplayActive());assert((events==std::vector<int>{0,2,3,1}));
 events.clear();endOtaDisplay();assert(events.empty());
 setBacklight(0);events.clear();assert(beginOtaDisplay());endOtaDisplay();
 assert((events==std::vector<int>{0,2,3,0}));
 light.ok=false;assert(!beginOtaDisplay());assert(!otaDisplayActive());
 boardReady=false;assert(!beginOtaDisplay());
}'''
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'test.cpp').write_text(code)
   subprocess.run(['c++','-std=c++17',str(p/'test.cpp'),'-o',str(p/'test')],check=True)
   subprocess.run([str(p/'test')],check=True)
