"""Run the real saver renderer against synthetic simultaneous activities."""
from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[4]
class CombinedSaver(unittest.TestCase):
 def test_print_drying_priority_staleness_and_dirty_regions(self):
  s=(ROOT/'src/display_ws43b.cpp').read_text()
  start=s.index('// The two concurrent activities have independent timers.')
  end=s.index('void setupScreen(',start)
  real=s[start:end]
  start=s.index('bool clockHasProgress(')
  real=s[start:s.index('bool coolingView(',start)]+real
  stub=r'''
#include "bambu_monitor.h"
namespace lgfx {using rgb565_t=uint16_t;}
#include "ws43b_dashboard_policy.h"
#include "ws43b_print_scene.h"
#include "ws43b_drying_scene.h"
#include "ws43b_style.h"
#include "ws43b_water_clock.h"
#include "ws43b_visual_assets.h"
#include <vector>
#include <string>
#include <cassert>
#include <cstdio>
#include <ctime>
#include <initializer_list>
const int INK=0xffff,DIM=0xaaaa,TRACK=0x1234,ACCENT=0x7890,WARN=0xfaaa,RED=0xf800,TL_DATUM=0;
using UiAsset=ws43b_assets::Asset;
// Decorative pixels are outside this label/clear-routing fixture, as for the
// pre-existing primitive drawing stubs below.
void panelIcon(UiAsset,int,int,uint16_t,int=33,bool=false,uint16_t=0){}
struct Rect{int x,y,w,h;};std::vector<Rect> clears;std::vector<std::string> texts;
struct Canvas {
 int captureX=0,captureY=0,captureW=0,captureH=0;std::vector<uint16_t> scene;
 void capture(int x,int y,int w,int h){captureX=x;captureY=y;captureW=w;captureH=h;scene.assign(size_t(w)*h,0xd963);}
 uint16_t color565(int r,int g,int b){return ((r>>3)<<11)|((g>>2)<<5)|(b>>3);}
 void setClipRect(int,int,int,int){}void clearClipRect(){}void setTextDatum(int){}
 void fillRect(int x,int y,int w,int h,int){clears.push_back({x,y,w,h});}
 void drawRect(int,int,int,int,int){}void drawRoundRect(int,int,int,int,int,int){}
 void fillRoundRect(int,int,int,int,int,int){}void drawCircle(int,int,int,int){}void fillCircle(int,int,int,int){}
 void drawLine(int,int,int,int,int){}void drawFastHLine(int,int,int,int){}void drawFastVLine(int,int,int,int){}
 void fillEllipse(int,int,int,int,int){}void drawEllipse(int,int,int,int,int){}
 void fillTriangle(int,int,int,int,int,int,int){}void drawTriangle(int,int,int,int,int,int,int){}
 void drawPixel(int,int,int){}
 void pushImage(int x,int y,int w,int h,const lgfx::rgb565_t*data){
  for(int py=0;py<h;++py)for(int px=0;px<w;++px){
   const int dx=x+px-captureX,dy=y+py-captureY;
   if(dx>=0&&dy>=0&&dx<captureW&&dy<captureH)scene[size_t(dy)*captureW+dx]=data[py*w+px];
  }
 }
}tft;
bool advancedDisplay=false;
bool ws43bAdvancedDisplay(){return advancedDisplay;}
ws43b_view::ActivityClock dashboardActivity;
struct{bool use24h=true;}netSettings;
const char*ws43bText(const char*pl,const char*){return pl;}
void dashText(const char*s,int,int,int,int=18,uint16_t=INK){texts.push_back(s);}
void modernText(const char*s,int,int,bool,uint16_t){texts.push_back(s);}
bool getLocalTime(tm*t,int){*t={};t->tm_year=126;t->tm_mday=13;t->tm_mon=9;t->tm_hour=20;return true;}
void drawClockBackground(bool,int,uint32_t){}
void clockWeatherIcon(const BambuMonitorTelemetry&,bool,uint32_t){}
void coolingScreen(const BambuMonitorTelemetry&,bool,uint32_t,bool){texts.push_back("COOLING");}
uint16_t saverFilamentColor(const BambuMonitorTelemetry&,bool,uint32_t){return 0x7fe0;}
unsigned printingAnimations=0;
void saverAnimation(bool printing,bool,uint16_t,uint32_t,unsigned){if(printing)++printingAnimations;}
template<class F>const char*missing(const F&f,bool online,uint32_t now){return online&&f.fresh(now)?nullptr:"missing";}
bool alert=false,cooling=false;
auto saverView(const BambuMonitorTelemetry&m,bool online,uint32_t now){return ws43b_view::saver(m,online,now,cooling,alert);}
'''
  case=r'''
bool has(const char*s){for(auto&t:texts)if(t.find(s)!=std::string::npos)return true;return false;}
bool exact(const char*s){for(auto&t:texts)if(t==s)return true;return false;}
bool dual(){for(auto&r:clears)if(r.x==680&&r.y==262)return true;return false;}
void render(BambuMonitorTelemetry&m,bool online,uint32_t now,bool partial=false){texts.clear();clears.clear();printingAnimations=0;clockScreen(m,online,now,partial);}
void cleaningPhase(uint32_t started,uint32_t now,bool combined){
 BambuMonitorTelemetry m;m.status.set("RUNNING",now);m.printStage.set(14,now);m.layerNum.set(0,now);
 m.progress.set(12,now);m.remainingMinutes.set(80,now);
 if(combined){auto &unit=m.amsUnits[0];unit.used=true;unit.id=0;unit.dryRemainMin.set(30,now);}
 dashboardActivity={};dashboardActivity.update(ws43b_view::Activity::Cleaning,started,m.session,0);
 const int x=combined?250:109,y=combined?258:222,w=combined?112:168,h=combined?104:156;
 tft.capture(x,y,w,h);render(m,true,now);const auto actual=tft.scene;
 const uint16_t bg=combined?tft.color565(7,25,34):tft.color565(3,14,23);
 const auto expectedAt=[&](uint32_t elapsed){
  tft.capture(x,y,w,h);
  if(combined)ws43b_print_scene::cleaning(tft,x,y,elapsed,bg);
  else {ws43b_print_scene::Scaled<Canvas> scene{tft,x,y};ws43b_print_scene::cleaning(scene,0,0,elapsed,bg);}
 };
 expectedAt(uint32_t(now-started));
 assert(actual==tft.scene); // The actual caller must preserve the activity phase.
 expectedAt(now);assert(actual!=tft.scene); // Inputs distinguish the old uptime bug.
 // Repainting the same activity after visiting a different screen must not
 // restart its timer or use absolute uptime, including millis() rollover.
 assert(!dashboardActivity.update(ws43b_view::Activity::Cleaning,now,m.session,0));
 tft.capture(x,y,w,h);render(m,true,now,true);assert(actual==tft.scene);
}
void runMode(){
 BambuMonitorTelemetry m;m.status.set("RUNNING",100);m.progress.set(68,100);m.remainingMinutes.set(92,100);
 auto&u=m.amsUnits[0];u.used=true;u.id=128;u.dryRemainMin.set(150,100);u.temp.set(55,100);u.humidityRaw.set(14,100);
 render(m,true,100);assert(dual()&&has("68%")&&has("1 h 32 min")&&has("2 h 30 min")&&has("55°C · 14% RH")&&has("AMS 128"));
 render(m,true,101,true);assert(dual()&&texts.empty());for(auto&r:clears)assert(r.y>=258&&r.y+r.h<=362);
 m.progress.invalidate(100);render(m,true,100);assert(dual()&&has("--%")&&has("2 h 30 min"));m.progress.set(68,100);
 m.status.set("PREPARE",100);render(m,true,100);assert(dual()&&has("PRZYGOTOWANIE")&&!has("DRUKOWANIE"));m.status.set("RUNNING",100);
 // The saver displays the unchanged MQTT percentage before and after layer 1.
 // Advanced Wydruk keeps the first-layer presentation gate.
 auto first=m;first.layerNum.set(0,100);
 render(first,true,100);assert(dual()&&has("PRZYGOTOWANIE")&&exact("68%")&&!has("DRUKOWANIE"));
 assert(!ws43b_view::printProgressVisible(first,true,100));
 first.layerNum.set(1,101);render(first,true,101);
 assert(dual()&&has("68%")&&has("DRUKOWANIE")&&first.progress.updatedMs==100);
 first.amsUnits[0].dryRemainMin.set(0,101);first.layerNum.set(0,101);
 render(first,true,101);assert(!dual()&&has("PRZYGOTOWANIE")&&exact("68%"));
 assert(!ws43b_view::printProgressVisible(first,true,101));
 first.layerNum.set(1,102);render(first,true,102);
 assert(!dual()&&has("68%")&&has("DRUKOWANIE")&&printingAnimations==1);
 first.printedLayerSeen=true;first.layerNum.set(0,103);first.progress.set(100,103);
 render(first,true,103);assert(has("100%")&&!has("PRZYGOTOWANIE")&&printingAnimations==1);
 first.status.set("PAUSE",104);render(first,true,104);assert(has("WSTRZYMANY")&&!printingAnimations);
 first.status.set("RUNNING",105);render(first,true,105);assert(has("100%")&&printingAnimations==1);
 m.printStage.set(14,100);render(m,true,100);assert(dual()&&exact("68%"));
 m.printStage.set(0,100);m.status.set("PAUSE",100);render(m,true,100);assert(!dual()&&has("WSTRZYMANY"));
 m.status.set("RUNNING",100);alert=true;render(m,true,100);assert(!dual()&&has("BŁĄD"));alert=false;
 cooling=true;render(m,true,100);assert(dual()&&exact("68%")&&!has("COOLING"));
 m.status.set("PREPARE",100);render(m,true,100);assert(dual()&&exact("68%")&&!has("COOLING"));
 m.status.set("FINISH",100);render(m,true,100);assert(!dual()&&has("COOLING"));
 m.status.set("RUNNING",100);cooling=false;
 render(m,false,100);assert(!dual()&&has("suszenie niepotwierdzone")&&!has("SUSZENIE"));
 m.status.set("RUNNING",60200);m.progress.set(70,60200);render(m,true,60200);assert(!dual()&&has("70%")&&has("suszenie niepotwierdzone"));
 u.dryRemainMin.set(149,60200);render(m,true,60200);assert(dual()&&has("--°C · --% RH")&&!has("55°C"));
 u.dryRemainMin.set(0,60200);render(m,true,60200);assert(!dual()&&!has("SUSZENIE"));
 u.dryRemainMin.set(149,60200);m.status.set("IDLE",60200);render(m,true,60200);assert(!dual()&&has("SUSZENIE")&&has("2 h 29 min")&&!has("70%"));
 u.present.set(false,60200);render(m,true,60200);assert(!has("SUSZENIE"));
 m.newSession();render(m,true,60201);assert(!dual()&&!has("SUSZENIE"));
 // Exercise the real single/combined renderer at the values most easily
 // confused with missing progress. Stage-only changes must not suppress them.
 for(bool combined:{false,true})for(const char*status:{"RUNNING","PREPARE"})for(unsigned percent:{0u,1u}) {
  BambuMonitorTelemetry current;current.status.set(status,100);current.progress.set(percent,100);
  current.remainingMinutes.set(80,100);current.layerNum.set(0,100);
  if(combined){auto&unit=current.amsUnits[0];unit.used=true;unit.id=0;unit.dryRemainMin.set(30,100);}
  char expected[8];snprintf(expected,sizeof expected,"%u%%",percent);
  uint32_t now=100;
  for(int stage:{0,14,1,51,0}) {
   current.printStage.set(stage,++now);render(current,true,now);
   assert(dual()==combined&&exact(expected));
   assert(!ws43b_view::printProgressVisible(current,true,now));
   assert(current.progress.value==percent&&current.progress.updatedMs==100);
   if(advancedDisplay){
    if(stage==14)assert(exact("Czyszczenie dyszy"));
    if(stage==1)assert(exact("Poziomowanie stołu"));
    if(stage==51)assert(exact("Linie kalibracyjne"));
   } else assert(exact("PRZYGOTOWANIE")&&!has("Czyszczenie")&&!has("Poziomowanie")&&!has("kalibracyjne"));
  }
  // Absence is never a synthetic zero; the simple mode stays simple even
  // when a preparation stage arrives before the percentage field.
  current.progress.invalidate(++now);current.printStage.set(14,now);render(current,true,now);
  assert(!exact(expected));
  if(!advancedDisplay)assert(exact("PRZYGOTOWANIE")&&!has("CZYSZCZENIE")&&!has("Czyszczenie")&&!has("Dysza czyści"));
  current.progress.set(percent,++now);current.printStage.set(0,now);
  current.layerNum.set(1,++now);render(current,true,now);
  assert(dual()==combined&&exact(expected)&&ws43b_view::printProgressVisible(current,true,now));
  // Notice states win over progress and simultaneous drying. Hidden numbers
  // must not survive in cached labels after leaving the ordinary print state.
  alert=true;render(current,true,++now);assert(!dual()&&has("BŁĄD")&&!exact(expected)&&!printingAnimations);alert=false;
  current.status.set("PAUSE",++now);render(current,true,now);
  assert(!dual()&&has("WSTRZYMANY")&&!exact(expected)&&!printingAnimations);
  current.status.set(status,++now);render(current,false,now);
  assert(!dual()&&has("Brak połączenia")&&!exact(expected)&&!printingAnimations);
  render(current,true,now+60001);
  assert(!dual()&&has("Oczekiwanie na aktualne dane")&&!exact(expected)&&!printingAnimations);
  current.status.set(status,now+60002);current.progress.set(percent,now+60002);
  render(current,true,now+60002);assert(exact(expected));
 }
 for(bool combined:{false,true}){
  cleaningPhase(1234,1999,combined);
  cleaningPhase(4321,6501,combined);
  cleaningPhase(0xfffff123u,400u,combined);
 }
}
int main(){for(bool advanced:{false,true}){advancedDisplay=advanced;runMode();}}
'''
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);(p/'test.cpp').write_text(stub+real+case)
   r=subprocess.run(['clang++','-std=c++17','-fsanitize=address,undefined','-I',str(ROOT/'include'),str(p/'test.cpp'),'-o',str(p/'test')],text=True,capture_output=True)
   self.assertEqual(r.returncode,0,r.stderr)
   r=subprocess.run([str(p/'test')],text=True,capture_output=True);self.assertEqual(r.returncode,0,r.stderr)
