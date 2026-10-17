from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[4]
class AmsLastReading(unittest.TestCase):
 def test_actual_view_preserves_values_without_claiming_freshness(self):
  source=(ROOT/'src/display_ws43b.cpp').read_text()
  view=source[source.index('const MonitorAmsUnit *amsUnit('):source.index('void dashboardTemperature(')]
  code=r'''
#include "bambu_monitor.h"
namespace lgfx {using rgb565_t=uint16_t;}
#include "ws43b_style.h"
#include "ws43b_drying_scene.h"
#include "ws43b_repaint_plan.h"
#include "ws43b_visual_assets.h"
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include <cassert>
#include <algorithm>
const char *ws43bText(const char *pl,const char*){return pl;}
unsigned selectedAms=0;constexpr int BG=0,CARD=1,INK=2,WARN=3,DIM=4,ACCENT=5,TRACK=6;
std::vector<std::string> text;std::vector<int> colors;
using UiAsset=ws43b_assets::Asset;
// This fixture observes telemetry labels and the requested filament tint;
// artwork pixels are checked by the icon and retained-canvas fixtures.
void panelIcon(UiAsset,int,int,uint16_t,int=33,bool tint=false,uint16_t color=0){
 if(tint)colors.push_back(color);
}
void dashText(const char*s,int,int,int,int,int){text.emplace_back(s);}
void button(const char*,int,int,int,int,bool){}
void levelCard(int,int,int,int,int,bool,bool){}
unsigned animationFrames=0;
struct {void setClipRect(int x,int y,int w,int h){assert(x==668&&y==138&&w==96&&h==94);++animationFrames;} void clearClipRect(){} void fillRect(int,int,int,int,int){} void drawRect(int,int,int,int,int){} void drawPixel(int,int,int){} void fillTriangle(int,int,int,int,int,int,int){} void drawTriangle(int,int,int,int,int,int,int){} void drawFastVLine(int,int,int,int){} void drawFastHLine(int,int,int,int){} void fillEllipse(int,int,int,int,int c){colors.push_back(c);} void drawEllipse(int,int,int,int,int){} void drawLine(int,int,int,int,int){} void drawCircle(int,int,int,int){} void drawRoundRect(int,int,int,int,int,int){} void fillRoundRect(int,int,int,int,int,int){} void fillCircle(int,int,int,int c){colors.push_back(c);} void pushImage(int,int,int,int,const lgfx::rgb565_t*){}}tft;
'''+view+r'''
bool has(const char*s){for(auto &v:text)if(v.find(s)!=std::string::npos)return true;return false;}
int main(){
 BambuMonitorTelemetry m;m.hasUsefulData=true;m.lastUsefulMs=100;
 auto &u=m.amsUnits[0];u.used=true;u.present.set(true,100);u.temp.set(40,100);u.humidityRaw.set(14,100);u.dryRemainMin.set(123,100);
 auto &t=u.trays[0];t.present.set(true,100);t.type.set("PETG",100);t.colorRgb565.set(12345,100);t.remain.set(84,100);
 amsView(m,true,100,true);assert(has("40°C")&&has("14% RH")&&has("2 h 03 min")&&!has("temu"));assert(has("Brak odczytu")&&!has("Pusty slot"));
 assert(animationFrames==1);assert(!amsDryingAnimated(m,false,100));
 text.clear();colors.clear();m.lastUsefulMs=70100;amsView(m,true,70100,true);
 assert(animationFrames==1);assert(!amsDryingAnimated(m,true,70100));
 assert(has("PETG")&&has("40°C")&&has("14% RH")&&has("84%")&&has("1 min temu"));assert(std::find(colors.begin(),colors.end(),12345)!=colors.end());
 text.clear();u.dryRemainMin.set(0,70100);amsView(m,true,70100,true);assert(has("Wyłączone")&&!has("0 h 00 min"));assert(animationFrames==1);
 text.clear();amsView(m,false,70100,true);assert(has("nieaktualne")&&has("offline")&&has("40°C"));
 text.clear();u.temp.invalidate(70101);t.present.set(false,70101);amsView(m,true,70101,true);assert(!has("40°C")&&has("Brak danych")&&has("Pusty")&&!has("PETG"));
 // A fresher coarse humidity reading supersedes an old raw reading.
 text.clear();u.humidity.set(3,70102);amsView(m,true,70102,true);assert(has("3/5")&&!has("14% RH"));
 text.clear();m.newSession();amsView(m,true,70103,true);assert(has("Brak danych AMS")&&!has("PETG"));
 char age[64];MonitorField<int> f;f.set(0,0xffffff00u);amsReadingAge(age,sizeof(age),f,true,0x100u);assert(!age[0]);
}
'''
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'test.cpp').write_text(code)
   compiled=subprocess.run(['clang++','-std=c++17','-I',str(ROOT/'include'),str(p/'test.cpp'),'-o',str(p/'test')],text=True,capture_output=True)
   self.assertEqual(compiled.returncode,0,compiled.stderr)
   subprocess.run([str(p/'test')],check=True,capture_output=True)
