from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[4]
class TemperatureLastReading(unittest.TestCase):
 def test_cached_values_are_visible_but_never_presented_as_live(self):
  source=(ROOT/'src/display_ws43b.cpp').read_text()
  functions=source[source.index('template <class Field>\nconst char *missing'):source.index('void temperature(')]
  functions+=source[source.index('template<class Field>\nvoid amsReadingAge'):source.index('void amsView(')]
  functions+=source[source.index('void v2Clear('):source.index('int v2Text(')]
  functions+=source[source.index('void dashboardTemperature('):source.index('// Solar data')]
  code=r'''
#include "bambu_monitor.h"
#include "ws43b_dashboard_policy.h"
#include "ws43b_style.h"
namespace lgfx { using rgb565_t=uint16_t; }
#include "ws43b_native_scene.h"
#include <cstdio>
#include <string>
#include <vector>
#include <cassert>
#define MAX_ACTIVE_PRINTERS 1
struct{int displayIndex=0;}rotState;
constexpr int BG=0x0084,CARD=1,INK=2,DIM=3,WARN=4,ACCENT=5,TRACK=6;
constexpr uint8_t ws43b_v2_12[]={0},ws43b_v2_b29[]={0};
uint16_t v2Ink(){return INK;}uint16_t v2Dim(){return DIM;}
const char* ws43bText(const char*p,const char*){return p;}
struct Text{std::string value;int color;};std::vector<Text> text;
int top=66;
int v2Text(const char*s,int x,int y,int w,const uint8_t*,int h,int color,bool=false,bool=true){
 assert(x>=528&&x+w<=784&&y>=top&&y+h+5<=top+74);
 text.push_back({s,color});return 0;
}
struct Canvas {
 unsigned pixels=0;
 void point(int x,int y){assert(x>=528&&x<784&&y>=top&&y<top+74);++pixels;}
 void drawFastHLine(int x,int y,int w,uint16_t){for(int i=0;i<w;++i)point(x+i,y);}
 void drawRoundRect(int x,int y,int w,int h,int,uint16_t){point(x,y);point(x+w-1,y+h-1);}
 void pushImage(int x,int y,int w,int h,const lgfx::rgb565_t*){
  for(int row=0;row<h;++row)for(int i=0;i<w;++i)point(x+i,y+row);
 }
}tft;
'''+functions+r'''
bool has(const char*s,int color=-1){for(auto &v:text)if(v.value.find(s)!=std::string::npos&&(color==-1||v.color==color))return true;return false;}
int main(){
 BambuMonitorTelemetry m;m.nozzleTemp.set(250,100);m.nozzleTarget.set(250,100);
 dashboardTemperature(0,66,"DYSZA",m.nozzleTemp,m.nozzleTarget,true,100);
 assert(has("250°C",INK)&&has("Cel 250°")&&!has("temu"));
 text.clear();dashboardTemperature(0,66,"DYSZA",m.nozzleTemp,m.nozzleTarget,true,240100);
 assert(has("250°C",DIM)&&has("4 min temu",WARN)&&has("cel 250° stary",WARN));assert(!has("Stabilna")&&!has("Nagrzewanie"));
 assert(m.nozzleTemp.updatedMs==100&&m.nozzleTarget.updatedMs==100&&!m.nozzleTemp.fresh(240100));
 // A fresh actual measurement does not silently refresh an old target.
 text.clear();m.nozzleTemp.set(245,240100);
 dashboardTemperature(0,66,"DYSZA",m.nozzleTemp,m.nozzleTarget,true,240100);
 assert(has("245°C",INK)&&has("Cel 250° · nieaktualny",WARN));
 assert(!has("Stabilna")&&m.nozzleTarget.updatedMs==100&&!m.nozzleTarget.fresh(240100));
 // A validated related delta can retain the unchanged target, preserving its age.
 m.retainCore(240100);
 text.clear();dashboardTemperature(0,66,"DYSZA",m.nozzleTemp,m.nozzleTarget,true,240100);
 assert(has("245°C",INK)&&has("Cel 250°")&&!has("temu")&&!has("nieaktualny"));
 assert(m.nozzleTarget.updatedMs==100&&!m.nozzleTarget.fresh(240100));
 m.nozzleTemp.set(250,100);
 text.clear();dashboardTemperature(0,66,"DYSZA",m.nozzleTemp,m.nozzleTarget,false,240100);assert(has("offline")&&has("250°C",DIM));
 text.clear();m.nozzleTemp.set(0,240101);m.nozzleTarget.set(0,240101);
 dashboardTemperature(0,66,"DYSZA",m.nozzleTemp,m.nozzleTarget,true,240101);assert(has("0°C",INK)&&has("Cel 0°"));
 text.clear();m.nozzleTemp.invalidate(240102);m.nozzleTarget.invalidate(240102);
 dashboardTemperature(0,66,"DYSZA",m.nozzleTemp,m.nozzleTarget,true,240102);assert(has("--")&&!has("0°C")&&has("Brak danych"));
 char layers[160];m.layerNum.set(221,240100);m.totalLayers.set(291,100);
 jobLayerText(layers,sizeof(layers),m,true,240100);assert(std::string(layers)=="221 / 291 · razem: 4 min temu");
 jobLayerText(layers,sizeof(layers),m,false,240100);assert(std::string(layers).find("ostatnie odczyty")!=std::string::npos);
 m.newSession();jobLayerText(layers,sizeof(layers),m,true,240101);assert(std::string(layers)=="-- / --");
 text.clear();dashboardTemperature(0,66,"DYSZA",m.nozzleTemp,m.nozzleTarget,true,240101);assert(!has("250°C"));
 // Every thermal card keeps all actual sprite pixels inside the new 256x74 bounds.
 for(int channel=0;channel<3;++channel) {
  top=66+84*channel;text.clear();m.nozzleTemp.set(channel?1000:-273.15,240102);
  dashboardTemperature(channel,top,"THERMAL",m.nozzleTemp,m.nozzleTarget,true,240102);
  assert(has(channel?"1000°C":"-273°C",INK));
 }
 assert(tft.pixels>0);
}
'''
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'test.cpp').write_text(code)
   subprocess.run(['clang++','-std=c++17','-I',str(ROOT/'include'),str(p/'test.cpp'),'-o',str(p/'test')],check=True,capture_output=True)
   subprocess.run([str(p/'test')],check=True)
