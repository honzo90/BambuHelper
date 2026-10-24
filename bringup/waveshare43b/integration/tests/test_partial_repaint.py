"""Exercise real panel grouping on a retained, deterministic recording canvas.

Glyphs and decorative shapes use simple host marks. This verifies paint routing,
clearing and text retention; it does not claim device-font or artwork fidelity.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class PartialRepaint(unittest.TestCase):
    def test_real_grouped_render_matches_complete_composition(self):
        source = (ROOT / 'src/display_ws43b.cpp').read_text()
        ams = source[source.index('const MonitorAmsUnit *amsUnit('):
                     source.index('void dashboardTemperature(')]
        dashboard = source[source.index('uint16_t dashboardSlotBg('):
                           source.index('// Match the dashboard/AMS policy:')]
        clear = source[source.index('void v2Clear('):source.index('int v2Text(')]
        panel_icon = source[source.index('using UiAsset='):
                            source.index('void v2Clear(')]
        code = r'''
#include "bambu_monitor.h"
#include "ws43b_dashboard_policy.h"
#include "ws43b_repaint_plan.h"
#include <array>
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <string>
#include <vector>
namespace lgfx { using rgb565_t=uint16_t; }
#include "ws43b_native_scene.h"
#include "ws43b_ui_icons.h"
using namespace ws43b_repaint;
using ws43b_live::View;
constexpr uint16_t BG=0,CARD=1,INK=2,WARN=3,DIM=4,ACCENT=5,TRACK=6;
unsigned selectedAms=0;
bool advancedDisplay=true; // Existing detailed assertions describe advanced mode.
bool ws43bAdvancedDisplay(){return advancedDisplay;}
const char *ws43bText(const char *pl,const char*,const char* = nullptr) { return pl; }
struct Rect { int x,y,w,h,color; };
struct Text { std::string value;int x,y,w,size,color; };
struct Canvas {
  std::array<uint16_t,800*480> pixels{};
  std::vector<Rect> fills;std::vector<Text> texts;
  int cx=0,cy=0,cw=800,ch=480;
  void clear(){pixels.fill(BG);fills.clear();texts.clear();clearClipRect();}
  void operations(){fills.clear();texts.clear();}
  void setClipRect(int x,int y,int w,int h){cx=x;cy=y;cw=w;ch=h;}
  void clearClipRect(){cx=cy=0;cw=800;ch=480;}
  void drawPixel(int x,int y,int color) {
    if(x>=0&&x<800&&y>=0&&y<480&&x>=cx&&x<cx+cw&&y>=cy&&y<cy+ch)
      pixels[size_t(y)*800+x]=uint16_t(color);
  }
  void fillRect(int x,int y,int w,int h,int color) {
    const int left=std::max(0,std::max(x,cx)),top=std::max(0,std::max(y,cy));
    const int right=std::min(800,std::min(x+w,cx+cw)),bottom=std::min(480,std::min(y+h,cy+ch));
    if(right>left&&bottom>top)fills.push_back({left,top,right-left,bottom-top,color});
    for(int yy=top;yy<bottom;++yy)
      for(int xx=left;xx<right;++xx)
        drawPixel(xx,yy,color);
  }
  void pushImage(int x,int y,int w,int h,const lgfx::rgb565_t *data) {
    for(int row=0;row<h;++row)for(int column=0;column<w;++column)
      fillRect(x+column,y+row,1,1,data[row*w+column]);
  }
  void fillRoundRect(int x,int y,int w,int h,int,int color){fillRect(x,y,w,h,color);}
  void drawFastHLine(int x,int y,int w,int color){fillRect(x,y,w,1,color);}
  void drawFastVLine(int x,int y,int h,int color){fillRect(x,y,1,h,color);}
  void drawRoundRect(int x,int y,int w,int h,int,int color) {
    drawFastHLine(x,y,w,color);drawFastHLine(x,y+h-1,w,color);
    drawFastVLine(x,y,h,color);drawFastVLine(x+w-1,y,h,color);
  }
  void resetOps(){operations();}
} tft;
const uint8_t ws43b_v2_12[]={0},ws43b_v2_13[]={0},ws43b_v2_b14[]={0},
  ws43b_v2_b16[]={0},ws43b_v2_b17[]={0},ws43b_v2_b23[]={0},ws43b_v2_b28[]={0},
  ws43b_v2_b43[]={0},ws43b_v2_b64[]={0};
uint16_t v2Ink(){return INK;}uint16_t v2Dim(){return DIM;}uint16_t v2Accent(){return ACCENT;}
void dashText(const char *s,int x,int y,int w,int size=18,int color=INK) {
  if(!s)return;
  tft.texts.push_back({s,x,y,w,size,color});
  // Each source byte leaves a distinct mark; shorter text requires a clear.
  for(size_t i=0;s[i]&&int(i*6+4)<=w;++i)
    if(s[i]!=' ')tft.fillRect(x+int(i)*6,y,4,size-2,(color<<8)|uint8_t(s[i]));
}
void button(const char *s,int x,int y,int w,int h,bool){
  tft.fillRoundRect(x,y,w,h,9,CARD);dashText(s,x+12,y+8,w-24,18,INK);
}
int v2Text(const char *s,int x,int y,int w,const uint8_t*,int height,
           uint16_t color,bool right=false,bool fit=true) {
  if(!s||!*s)return 0;
  // Deterministic glyph marks and actual clip/right-alignment contract. Font
  // metrics/artwork have separate tests; this canvas checks retained pixels.
  const int natural=int(strlen(s))*6,width=fit?std::min(w,natural):natural;
  tft.texts.push_back({s,x,y,w,height,color});tft.setClipRect(x,y,w,height+5);
  for(int i=0;s[i]&&i*6<width;++i)
    if(s[i]!=' ')tft.fillRect((right?x+w-width:x)+i*6,y,4,height-2,(color<<8)|uint8_t(s[i]));
  tft.clearClipRect();return width;
}
namespace ws43b_style {
enum class Icon { Spool };
template<class C>void icon(C &c,Icon,int x,int y,int color){c.fillRect(x-10,y-10,20,20,color);}
template<class C>void spool(C &c,int x,int y,float scale,int color,bool known){
  c.fillRect(x,y,int(50*scale),int(45*scale),known?color:DIM);
}
}
namespace ws43b_drying_scene {
template<class C>void draw(C &c,int x,int y,int scale,uint32_t,int accent,int,int,int){
  c.fillRect(x-scale/2,y-scale/2,scale,scale,accent);
}
}
template<class Field>const char *missing(const Field &f,bool online,uint32_t now){
  if(!f.valid)return "Brak danych";
  if(!online||!f.fresh(now))return "Nieaktualne";
  return nullptr;
}
const char *statusText(const MonitorText<16> &f,bool online,uint32_t now){
  return missing(f,online,now)?missing(f,online,now):f.value;
}
bool dashboardCooling=false,dashboardCoolingPainted=false;
int dashboardProgressEdge=0;
ws43b_view::ActivityClock dashboardActivity;
void dashboardActivityIcon(uint32_t,bool force=false){assert(force);tft.fillRect(228,74,270,170,ACCENT);}
void dashboardCoolingCard(const BambuMonitorTelemetry &,uint32_t,bool){assert(false);}
struct {bool use24h=true;} netSettings;
bool getLocalTime(tm*,uint32_t){return false;}
void dashboardTemperature(int,int y,const char *name,const MonitorField<float> &actual,
                          const MonitorField<float> &target,bool online,uint32_t now){
  tft.fillRoundRect(528,y,256,74,12,CARD);
  dashText(name,585,y+16,70,12,DIM);
  char text[60];snprintf(text,sizeof text,"%.0f/%.0f/%d",double(actual.value),double(target.value),online&&actual.fresh(now));
  dashText(text,649,y+12,121,29,online?INK:DIM);
}
''' + panel_icon + '\n' + clear + '\n' + ams + '\n' + dashboard + r'''
bool has(const char *needle){for(const auto &text:tft.texts)if(text.value.find(needle)!=std::string::npos)return true;return false;}
bool exact(const char *needle){for(const auto &text:tft.texts)if(text.value==needle)return true;return false;}
bool fillsRect(int x,int y,int w,int h,int color){
  for(const auto &r:tft.fills)if(r.x==x&&r.y==y&&r.w==w&&r.h==h&&r.color==color)return true;
  return false;
}
bool writesOutside(int x,int y,int w,int h){
  for(const auto &r:tft.fills)if(r.x<x||r.y<y||r.x+r.w>x+w||r.y+r.h>y+h)return true;
  return false;
}
bool clearsNativeRect(int x,int y,int w,int h){
  // Check every pixel's first write, before cards/text paint over the clear.
  // Gradient chunks can cross Bayer phases; a uniform row is not equivalent.
  std::vector<bool> seen(size_t(w)*h,false);size_t covered=0;
  for(const auto &r:tft.fills) {
    const int left=std::max(x,r.x),top=std::max(y,r.y);
    const int right=std::min(x+w,r.x+r.w),bottom=std::min(y+h,r.y+r.h);
    for(int py=top;py<bottom;++py)for(int px=left;px<right;++px) {
      const size_t at=size_t(py-y)*w+px-x;
      if(seen[at])continue;
      if(r.color!=ws43b_native::textbg(px,py,BG))return false;
      seen[at]=true;++covered;
    }
  }
  return covered==size_t(w)*h;
}
struct Scenario {
  BambuMonitorTelemetry m;Cache cache;View view;bool online=true;uint32_t now=1100;
  explicit Scenario(View v):view(v){
    m.hasUsefulData=true;m.lastUsefulMs=1000;
    m.status.set("RUNNING",1000);m.progress.set(50,1000);m.printStage.set(0,1000);
    m.remainingMinutes.set(45,1000);m.subtaskName.set("Long original print name with suffix",1000);
    m.layerNum.set(50,1000);m.totalLayers.set(100,1000);
    m.nozzleTemp.set(220,1000);m.nozzleTarget.set(220,1000);
    m.bedTemp.set(60,1000);m.bedTarget.set(60,1000);m.chamberTemp.set(36,1000);
    m.activeTrayRaw.set(1,1000);
    auto &u=m.amsUnits[0];u.used=true;u.id=0;u.present.set(true,1000);
    u.temp.set(40,1000);u.humidityRaw.set(14,1000);u.humidity.set(1,1000);u.dryRemainMin.set(0,1000);
    for(auto &tray:u.trays){tray.present.set(true,1000);tray.type.set("PETG Basic",1000);tray.remain.set(80,1000);tray.colorRgb565.set(12345,1000);}
    selectedAms=0;dashboardActivity.state=ws43b_view::Activity::Printing;
    tft.clear();draw(All);cache.commit(key());tft.operations();
  }
  Keys key(){return keys(m,view,0,online,now);}
  void draw(Mask mask){
    if(view==View::Dashboard)dashboardScreen(m,online,now,mask);
    else amsView(m,online,now,true,mask);
  }
  Mask update(){
    const auto next=key();const auto mask=cache.dirty(next);tft.operations();draw(mask);cache.commit(next);return mask;
  }
  void equivalent(){
    const auto partial=tft.pixels;
    tft.clear();draw(All);
    if(partial!=tft.pixels){
      unsigned differences=0;
      for(size_t i=0;i<partial.size();++i)if(partial[i]!=tft.pixels[i]){
        if(differences++<8)fprintf(stderr,"pixel mismatch view=%u x=%zu y=%zu partial=%u full=%u\n",unsigned(view),i%800,i/800,unsigned(partial[i]),unsigned(tft.pixels[i]));
      }
      fprintf(stderr,"total mismatches=%u\n",differences);assert(false);
    }
    tft.operations();
  }
};
int main(){
  {
    // Exercise a non-aligned patch wider than the production 64-pixel chunk.
    tft.clear();tft.pixels.fill(0xffff);v2Clear(17,67,70,5);
    assert(clearsNativeRect(17,67,70,5));assert(!writesOutside(17,67,70,5));
    for(int y=0;y<480;++y)for(int x=0;x<800;++x)
      assert(tft.pixels[size_t(y)*800+x]==
        (x>=17&&x<87&&y>=67&&y<72?ws43b_native::textbg(x,y,BG):0xffff));
  }
  {
    Scenario s(View::Dashboard);
    assert(s.update()==0);assert(tft.fills.empty()&&tft.texts.empty());
    s.m.subtaskName.set("Short",s.now);
    assert(s.update()==regionBit(Region::Primary));assert(has("Short")&&has("AMS 1 / 2")&&!has("1 PETG"));
    assert(clearsNativeRect(16,66,500,242));assert(!writesOutside(16,66,500,242));s.equivalent();
    s.m.nozzleTemp.set(225,s.now);
    assert(s.update()==regionBit(Region::Nozzle));assert(has("DYSZA")&&!has("STÓŁ")&&!has("Short"));
    assert(!writesOutside(528,66,256,74));s.equivalent();
    s.m.amsUnits[0].trays[2].remain.set(20,s.now);
    assert(s.update()==regionBit(Region::Ams2));assert(has("20%")&&!has("Short")&&!has("DYSZA"));
    assert(!writesOutside(404,345,184,80));s.equivalent();
    s.m.amsUnits[0].trays[2].present.set(false,s.now);s.update();assert(has("Pusty"));s.equivalent();
    s.m.amsUnits[0].trays[2]=MonitorAmsTray{};s.update();assert(has("Brak odczytu"));s.equivalent();
    s.m.amsUnits[0].present.set(false,s.now);s.update();assert(has("Oczekiwanie na dane AMS"));s.equivalent();
    s.m.amsUnits[0].present.set(true,s.now);s.update();s.equivalent();
    s.online=false;s.now=5500;s.update();assert(has("offline"));s.equivalent();
    s.now=71000;s.update();assert(has("1 min temu"));s.equivalent();
    s.m.newSession();s.update();assert(has("Oczekiwanie na dane AMS")&&!has("PETG"));s.equivalent();
  }
  {
    Scenario s(View::Dashboard);
    const auto progressTime=s.m.progress.updatedMs;
    s.m.layerNum.set(0,s.now);
    auto changed=s.update();
    assert((changed&(regionBit(Region::Header)|regionBit(Region::Primary)))==
      (regionBit(Region::Header)|regionBit(Region::Primary)));
    assert(has("PRZYGOTOWANIE")&&has("Przed pierwszą")&&!has("%"));
    assert(!fillsRect(32,247,234,6,ACCENT));s.equivalent();
    // A layer-only delta restores the same numeric percentage and progress bar.
    s.m.layerNum.set(1,s.now);changed=s.update();
    assert((changed&(regionBit(Region::Header)|regionBit(Region::Primary)))==
      (regionBit(Region::Header)|regionBit(Region::Primary)));
    assert(has("POSTĘP WYDRUKU")&&has("50")&&has("%")&&!has("Przed pierwszą"));
    assert(fillsRect(32,247,234,6,ACCENT)&&s.m.progress.updatedMs==progressTime);s.equivalent();
    // End G-code can reset the layer before FINISH without resetting this job.
    s.m.printedLayerSeen=true;s.m.layerNum.set(0,s.now);s.m.progress.set(100,s.now);
    s.update();assert(has("100")&&has("%")&&!has("PRZYGOTOWANIE"));
    assert(fillsRect(32,247,468,6,ACCENT));s.equivalent();
    // A reset latch itself must invalidate both status and primary presentation.
    s.m.printedLayerSeen=false;changed=s.update();
    assert((changed&(regionBit(Region::Header)|regionBit(Region::Primary)))==
      (regionBit(Region::Header)|regionBit(Region::Primary)));
    assert(has("PRZYGOTOWANIE")&&!has("%"));s.equivalent();
  }
  {
    Scenario s(View::Dashboard);
    auto &tray=s.m.amsUnits[0].trays[1];
    tray.type.set("ASA",s.now);
    assert(s.update()==(regionBit(Region::Primary)|regionBit(Region::Ams1)));
    assert(has("AMS 1 / 2 · ASA"));s.equivalent();
    for(uint16_t color:{uint16_t(0xf800),uint16_t(0),uint16_t(0xffff)}) {
      tray.colorRgb565.set(color,s.now);
      assert(s.update()==(regionBit(Region::Primary)|regionBit(Region::Ams1)));s.equivalent();
    }
    tray.remain.invalidate(s.now);s.update();assert(has("--")&&!has("Pusty"));s.equivalent();
    tray.type.invalidate(s.now);s.update();assert(has("Brak odczytu")&&has("Materiał: brak danych"));s.equivalent();
    tray.present.set(false,s.now);s.update();assert(has("Pusty"));s.equivalent();
    tray.present.set(true,s.now);tray.type.set("PLA",s.now);tray.remain.set(0,s.now);
    s.update();assert(has("0%")&&!has("Pusty"));s.equivalent();
    // Long-to-short values and explicit unknowns must erase old glyphs/bars.
    s.m.progress.set(100,s.now);s.m.remainingMinutes.set(125,s.now);s.update();s.equivalent();
    s.m.progress.set(0,s.now);s.m.remainingMinutes.set(5,s.now);s.update();s.equivalent();
    s.m.progress.invalidate(s.now);s.m.remainingMinutes.invalidate(s.now);s.update();s.equivalent();
    s.m.layerNum.set(50000,s.now);s.m.totalLayers.set(60000,s.now);s.update();s.equivalent();
    s.m.layerNum.set(1,s.now);s.m.totalLayers.set(2,s.now);s.update();s.equivalent();
  }
  {
    Scenario s(View::Dashboard);
    auto &unit=s.m.amsUnits[3];unit.used=true;unit.id=7;unit.present.set(true,s.now);
    auto &tray=unit.trays[1];tray.present.set(true,s.now);tray.type.set("PETG",s.now);
    tray.colorRgb565.set(0x07e0,s.now);
    s.m.activeTrayRaw.set(29,s.now);s.update();s.equivalent();
    tray.type.set("ASA",s.now);
    assert(s.update()==regionBit(Region::Primary));assert(has("AMS 8 / 2 · ASA"));s.equivalent();
    // Only selection freshness changes: keep the retained material/colour,
    // but repaint the caption warning even though other AMS cards are shown.
    s.m.activeTrayRaw.set(29,s.now-BAMBU_MONITOR_FRESH_MS-1u);
    assert(s.update()==regionBit(Region::Primary));assert(has("Materiał: ostatni odczyt"));s.equivalent();
    s.m.activeTrayRaw.set(29,s.now);
    assert(s.update()==regionBit(Region::Primary));assert(has("Dane na żywo"));s.equivalent();
    unit.present.set(false,s.now);
    assert(s.update()==regionBit(Region::Primary));assert(has("Materiał: brak danych"));s.equivalent();
    unit.present.set(true,s.now);s.update();s.equivalent();
    unit=MonitorAmsUnit{};
    assert(s.update()==regionBit(Region::Primary));assert(has("Materiał: brak danych"));s.equivalent();
  }
  {
    // Simple Wydruk uses actual MQTT progress, including 0% before layer 1,
    // while retaining the thermal/AMS cards and native animation region.
    advancedDisplay=false;
    Scenario s(View::Dashboard);s.draw(All);
    assert(has("DYSZA")&&has("STÓŁ")&&has("KOMORA")&&has("PETG"));
    assert(!has("Warstwa")&&!has("Materiał")&&!has("AMS 1 / 2"));
    s.m.layerNum.set(0,s.now);s.m.progress.set(0,s.now);s.update();
    assert(exact("0")&&exact("%")&&!has("Przed pierwszą"));
    assert(!has("Warstwa")&&!has("Materiał")&&!has("AMS 1 / 2"));s.equivalent();
    const auto progressTime=s.m.progress.updatedMs;
    for(int stage:{14,1,51,0}) {
      s.m.printStage.set(stage,s.now);s.update();
      // Force the primary labels at the unchanged percentage; stage changes
      // can leave the generic status wording unchanged in simple mode.
      s.draw(regionBit(Region::Primary));
      assert(exact("0")&&exact("%")&&s.m.progress.updatedMs==progressTime);
      assert(!has("Warstwa")&&!has("Materiał")&&!has("AMS 1 / 2"));s.equivalent();
    }
    s.m.progress.set(1,s.now);s.update();assert(exact("1")&&exact("%"));s.equivalent();
    s.m.status.set("PREPARE",s.now);s.update();assert(exact("1")&&exact("%"));s.equivalent();
    s.m.progress.invalidate(s.now);s.update();assert(!exact("%"));s.equivalent();
    s.m.progress.set(1,s.now);s.online=false;s.update();
    assert(!exact("%")&&has("Offline"));s.equivalent();
    s.online=true;s.now=71000;s.update();assert(!exact("%"));s.equivalent();
    s.m.status.set("RUNNING",s.now);s.m.progress.set(1,s.now);s.update();
    assert(exact("1")&&exact("%"));s.equivalent();
    // Switching back must restore advanced metadata and its first-layer gate.
    advancedDisplay=true;s.draw(All);
    assert(has("Przed pierwszą")&&has("Warstwa"));
  }
  {
    Scenario s(View::Ams);assert(s.update()==0);assert(tft.fills.empty()&&tft.texts.empty());
    auto &u=s.m.amsUnits[0];
    u.humidity.set(3,s.now);assert(s.update()==0);assert(tft.fills.empty()); // hidden coarse sensor
    u.humidityRaw.set(15,s.now);
    assert(s.update()==regionBit(Region::AmsSummary));assert(has("15% RH")&&!has("PETG"));
    assert(!writesOutside(24,84,752,156));s.equivalent();
    u.trays[0].type.set("ASA",s.now);assert(s.update()==regionBit(Region::Ams0));
    assert(has("ASA")&&!has("15% RH"));assert(!writesOutside(24,250,182,174));s.equivalent();
    u.trays[3].remain.set(0,s.now);s.update();assert(has("0%"));s.equivalent();
    u.present.set(false,s.now);s.update();assert(has("Brak danych AMS"));s.equivalent();
    u.present.set(true,s.now);s.update();s.equivalent();
    u.dryRemainMin.set(121,s.now);s.update();assert(has("2 h 01 min"));s.equivalent();
    u.dryRemainMin.set(0,s.now);s.update();assert(has("Wyłączone"));s.equivalent();
    s.now=71000;s.m.lastUsefulMs=s.now;u.humidity.set(4,s.now);
    s.update();assert(has("4/5")&&!has("15% RH"));s.equivalent();
    s.online=false;s.update();assert(has("offline"));s.equivalent();
    s.online=true;u.temp.set(44,s.now);u.humidityRaw.set(16,s.now);
    s.update();assert(has("44°C")&&has("16% RH"));s.equivalent();
  }
}
'''
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p / 'test.cpp').write_text(code)
            result = subprocess.run([
                'clang++', '-std=c++17', '-fsanitize=address,undefined',
                '-I', str(ROOT / 'include'), str(p / 'test.cpp'), '-o', str(p / 'test'),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(p / 'test')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
