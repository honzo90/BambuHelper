"""Compile the actual render dispatcher to test cache and screen lifecycles."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class RepaintIntegration(unittest.TestCase):
    def test_actual_dispatcher_cache_invalidation(self):
        source = (ROOT / 'src/display_ws43b.cpp').read_text()
        render = source[source.index('void renderWs43bMonitor(bool force)'):source.rindex('\n#endif')]
        start = source.index('bool clockHasProgress(')
        clock_gate = source[start:source.index('bool coolingView(', start)]
        palette = source[source.index('void applyWs43bPalette()'):source.index('void startupText(')]
        code = r'''
#define WS43B_FULL_WEBUI 1
#include "ws43b_live_view.h"
#include "ws43b_animation_policy.h"
#define bit(b) (1UL << (b))
#include "ws43b_repaint_plan.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <string>
#include <vector>
using ws43b_repaint::Mask;using ws43b_repaint::Region;using ws43b_repaint::regionBit;
constexpr unsigned MAX_ACTIVE_PRINTERS=2;
enum class Page { Dashboard,Details,Clock,Settings,ClockSettings,Gauges,Ams,WeatherSettings,Appearance,GeneralSettings,WebQr,System,FactoryReset };
Page page=Page::Dashboard;
uint32_t currentMs=1000,lastFrame=0,nightActivity=0,language=0;
uint32_t millis(){return currentMs;}
bool advancedDisplay=false;uint32_t displayModeRevision=0;
bool ws43bAdvancedDisplay(){return advancedDisplay;}
uint32_t ws43bDisplayModeRevision(){return displayModeRevision;}
bool painted=false,screenOff=false,automaticIdle=false,configured=false,ap=false,wifi=true;
bool startupVisible=false;
using String=std::string;struct {String SSID(){return "Test Wi-Fi";}}WiFi;
bool navigation=true,night=false,ota=false,rxPending=false,glowArmed=false,glowCleanup=false;
bool cleanupAtTick=false,glowLatched=false;unsigned screen=0;constexpr unsigned SCREEN_HMS=1;
bool dashboardCooling=false,dashboardCoolingPainted=false,weatherHeaderVisible=false;
unsigned selectedAms=0;
uint16_t BG=0,TRACK=1,ACCENT=2,INK=3,DIM=4,GREEN=5;constexpr uint16_t WARN=6,RED=7;
constexpr uint16_t CLR_GREEN=5;
const uint8_t ws43b_v2_b14[]={0},ws43b_v2_b17[]={0},ws43b_v2_b25[]={0};
const char *settingsNotice=nullptr;
ws43b_view::ActivityClock dashboardActivity;
struct Printer {
  struct {char name[64]="Test printer";} config;
  struct {bool connected=true;BambuMonitorTelemetry monitor;} state;
} printers[MAX_ACTIVE_PRINTERS];
struct {unsigned displayIndex=0;} rotState;
Printer &displayedPrinter(){return printers[rotState.displayIndex];}
struct {bool pongClock=false,fanMatchPrinter=true;uint16_t textColor=3,textDimColor=4,statusOkColor=5,bgColor=0,trackColor=1,progressBarColor=2;} dispSettings;
struct {bool keepDisplayOn=false,showClockAfterFinish=false;} dpSettings;
struct {bool use24h=true;} netSettings;
struct WeatherData {uint32_t revision=0;bool valid=false;};WeatherData weather;
struct WeatherConfig {uint32_t revision=0,nightSeconds=30;bool enabled=false;};WeatherConfig weatherConfig;
WeatherData ws43bWeatherData(){return weather;}
WeatherConfig ws43bWeatherConfig(){return weatherConfig;}
namespace ws43b_weather {bool fresh(const WeatherData &d,time_t){return d.valid;}}
namespace ws43b_style {constexpr uint16_t background=10,border=11,mint=12;}
namespace ws43b_water {unsigned hour(unsigned h,bool full){return full?h:(h%12?h%12:12);}}
namespace ws43b_view {bool pongAvailable(bool,bool,bool){return false;}}
struct Rect {int x,y,w,h;};
struct Canvas {
  unsigned full=0,begin=0,end=0;std::vector<Rect> clears;std::vector<std::string> text;
  void startWrite(){++begin;}void endWrite(){++end;}
  void fillScreen(int){++full;}void fillRect(int x,int y,int w,int h,int){clears.push_back({x,y,w,h});}
  void unloadFont(){}void setTextSize(int){}void fillCircle(int,int,int,int){}void drawFastHLine(int,int,int,int){}
  void drawFastVLine(int,int,int,int){}
  void reset(){full=begin=end=0;clears.clear();text.clear();}
} tft;
namespace ws43b_native {
 constexpr uint16_t line=8;
 bool headCached=false;
 bool heroHeadCacheReady(){return headCached;}
 template<class C>void screen(C &c,uint16_t color){c.fillScreen(color);}
}
uint16_t v2Ink(){return INK;}uint16_t v2Dim(){return DIM;}uint16_t v2Accent(){return ACCENT;}
void v2Clear(int x,int y,int w,int h){tft.fillRect(x,y,w,h,BG);}
int v2Text(const char *s,int,int,int,const uint8_t*,int,uint16_t,bool=false,bool=true){tft.text.emplace_back(s);return 0;}
unsigned probes=0,partialFrames=0,frames=0,footerCount=0,setupCount=0,hmsCount=0,clockCount=0;
unsigned menuWeatherCount=0,bodyCount=0,detailCount=0,animationCount=0,cancelCount=0;
unsigned activityCount=0,weatherIconCount=0;
Mask bodyMask=0;bool lastClockPartial=false;
namespace ws43b {
 bool otaDisplayActive(){return ota;}
 bool setColorPercent(unsigned p){static unsigned previous=100;bool changed=p!=previous;previous=p;return changed;}
 void beginRenderDiagnostics(bool full=true){if(full)++probes;else ++partialFrames;}
 void endRenderDiagnostics(bool){++frames;}
}
void resetOps(){tft.reset();probes=partialFrames=frames=footerCount=setupCount=hmsCount=clockCount=0;menuWeatherCount=bodyCount=detailCount=animationCount=cancelCount=0;activityCount=weatherIconCount=0;bodyMask=0;}
bool isWiFiConnected(){return wifi;}bool isAPMode(){return ap;}bool isAnyPrinterConfigured(){return configured;}
bool isPrinterConfigured(unsigned i){return configured&&i<MAX_ACTIVE_PRINTERS;}
bool navigationShown(uint32_t){return navigation;}
bool isNightModeActive(){return night;}
unsigned getScreenState(){return screen;}
bool glowIsArmed(){return glowArmed;}
bool glowConsumeCleanup(){const bool result=glowCleanup;glowCleanup=false;return result;}
void glowTick(Canvas &,unsigned,bool){
 if(glowLatched){glowLatched=false;glowArmed=true;}
 if(cleanupAtTick){cleanupAtTick=false;glowArmed=false;glowCleanup=true;}
}
bool bambuMqttReceivePending(unsigned){return rxPending;}
uint32_t ws43bLanguageRevision(){return language;}
const char *ws43bText(const char *p,const char*){return p;}
void updateIdleView(uint32_t){}void cancelWs43bMonitorTouch(){++cancelCount;}
bool clockValid=true;unsigned clockMinute=15;
bool getLocalTime(tm *t,uint32_t){*t={};t->tm_year=126;t->tm_yday=100;t->tm_mday=10;t->tm_mon=3;t->tm_hour=10;t->tm_min=clockMinute;return clockValid;}
bool dashboardWeatherNight(const WeatherData &){return night;}
ws43b_live::View liveView(){
 if(page==Page::Dashboard)return ws43b_live::View::Dashboard;
 if(page==Page::Ams)return ws43b_live::View::Ams;
 if(page==Page::Details)return ws43b_live::View::Details;
 if(page==Page::Clock)return ws43b_live::View::Clock;
 return ws43b_live::View::None;
}
unsigned liveAms(const BambuMonitorTelemetry &){return selectedAms;}
template<class F>const char *missing(const F &f,bool online,uint32_t now){return !f.valid?"Brak danych":!online||!f.fresh(now)?"Nieaktualne":nullptr;}
const char *statusText(const MonitorText<16>&f,bool online,uint32_t now){return missing(f,online,now)?missing(f,online,now):f.value;}
bool coolingView(const BambuMonitorTelemetry &){return dashboardCooling;}
ws43b_view::Saver saverView(const BambuMonitorTelemetry &m,bool online,uint32_t now){return ws43b_view::saver(m,online,now,dashboardCooling,screen==SCREEN_HMS);}
bool amsDryingAnimated(const BambuMonitorTelemetry &m,bool online,uint32_t now){const auto *u=ws43b_view::dryingUnit(m,online,now);return u&&online&&u->dryRemainMin.fresh(now);}
void amsDryingAnimation(uint32_t){++animationCount;}
void dashboardActivityIcon(uint32_t,bool=false){++animationCount;++activityCount;}
void dashboardWeatherIcon(uint32_t){++animationCount;++weatherIconCount;}
void coolingScreen(const BambuMonitorTelemetry &,bool,uint32_t,bool){++bodyCount;}
void resetPongClock(){}void tickPongClock(){}
void dashText(const char *s,int,int,int,int=18,int=0){tft.text.emplace_back(s);}
void modernText(const char *s,int,int,bool,int){tft.text.emplace_back(s);}
void connectedWifiName(int,int,int){}
void setupScreen(bool,bool){++setupCount;tft.fillScreen(BG);}
void drawWs43bHmsScreen(){++hmsCount;}
void footer(const BambuMonitorTelemetry &,uint32_t){++footerCount;}
void clockScreen(const BambuMonitorTelemetry &,bool,uint32_t,bool partial=false){++clockCount;lastClockPartial=partial;}
void menuWeatherHeader(uint32_t){++menuWeatherCount;weatherHeaderVisible=weatherConfig.enabled&&weather.valid;}
void dashboardWeather(bool){}
void amsView(const BambuMonitorTelemetry &,bool,uint32_t,bool,Mask mask){++bodyCount;bodyMask=mask;}
void dashboardScreen(const BambuMonitorTelemetry &,bool,uint32_t,Mask mask){++bodyCount;bodyMask=mask;}
void detailsScreen(const BambuMonitorTelemetry &,bool,uint32_t){++detailCount;}
void gaugesScreen(const Printer &,bool,uint32_t){++bodyCount;}
void clockSettingsScreen(){}void weatherSettingsScreen(){}void appearanceSettingsScreen(){}
void generalSettingsScreen(){}void webQrScreen(){}void systemSettingsScreen(){}
void factoryResetScreen(uint32_t){}void settingsScreen(){}
namespace ws43b_boot {
 enum class Phase { Wifi, Printer, Data };
 Phase connectionPhase(bool w,bool m){return !w?Phase::Wifi:!m?Phase::Printer:Phase::Data;}
}
void startupScreen(ws43b_boot::Phase,const char*,uint32_t){startupVisible=true;tft.fillScreen(BG);tft.text.emplace_back("Oczekiwanie");}
void animateStartupScreen(uint32_t){++animationCount;}
''' + palette + clock_gate + render + r'''
bool has(const char *s){for(const auto &text:tft.text)if(text.find(s)!=std::string::npos)return true;return false;}
bool cleared(int x,int y,int w,int h){for(const auto &r:tft.clears)if(r.x==x&&r.y==y&&r.w==w&&r.h==h)return true;return false;}
void tick(bool force=false){currentMs+=1100;resetOps();renderWs43bMonitor(force);assert(tft.begin==tft.end);}
void full(){assert(tft.full==1&&probes==1);}
void seed(BambuMonitorTelemetry &m){
 m.hasUsefulData=true;m.lastUsefulMs=currentMs;m.status.set("RUNNING",currentMs);m.progress.set(50,currentMs);
 m.remainingMinutes.set(20,currentMs);m.nozzleTemp.set(220,currentMs);m.nozzleTarget.set(220,currentMs);
 m.bedTemp.set(60,currentMs);m.bedTarget.set(60,currentMs);m.chamberTemp.set(36,currentMs);
 auto &u=m.amsUnits[0];u.used=true;u.present.set(true,currentMs);u.temp.set(40,currentMs);u.humidityRaw.set(14,currentMs);u.dryRemainMin.set(0,currentMs);
 for(auto &tray:u.trays){tray.present.set(true,currentMs);tray.type.set("PETG",currentMs);tray.remain.set(80,currentMs);}
}
int main(){
 tick();full();assert(setupCount==1);
 configured=true;painted=false;tick();full();assert(startupVisible&&(has("Łączenie")||has("Oczekiwanie")));
 currentMs+=100;resetOps();renderWs43bMonitor(false);assert(animationCount==1&&!tft.full&&!bodyCount);
 page=Page::Details;painted=false;tick();assert(!startupVisible&&detailCount==1);
 page=Page::Dashboard;painted=false;tick();assert(startupVisible);
 seed(printers[0].state.monitor);tick();full();assert(!startupVisible&&bodyCount==1&&footerCount==1);
 // Weather-only header updates must not erase the cards now beginning at y=66
 // or the AMS row at y=345..424. Thermal ticks may repaint their own regions.
 weatherConfig.enabled=true;++weatherConfig.revision;weather.valid=true;++weather.revision;tick();
 assert(!tft.full&&!probes&&menuWeatherCount==1&&cleared(0,0,800,56));
 assert(!cleared(0,0,800,80)&&!cleared(24,404,752,29));
 assert(bodyMask&regionBit(Region::Header));
 assert(!(bodyMask&(regionBit(Region::Primary)|regionBit(Region::AmsSummary))));
 weatherConfig.enabled=false;++weatherConfig.revision;tick();
 assert(!tft.full&&cleared(0,0,800,56));
 page=Page::Ams;painted=false;tick();full();assert(bodyCount==1);
 tick();assert(!tft.full&&tft.clears.empty()&&tft.text.empty()&&!bodyCount&&!footerCount&&!menuWeatherCount); // cached no-op
 auto &m=printers[0].state.monitor;m.amsUnits[0].temp.set(41,currentMs);tick();
 assert(!tft.full&&!probes&&partialFrames==1&&bodyMask==regionBit(Region::AmsSummary));
 assert(!menuWeatherCount&&!footerCount);
 ++clockMinute;tick();assert(!tft.full&&!probes&&menuWeatherCount==1&&!footerCount);
 assert(bodyMask&regionBit(Region::Header));assert(cleared(0,0,800,80));
 weatherConfig.enabled=true;++weatherConfig.revision;weather.valid=true;++weather.revision;tick();
 assert(!tft.full&&menuWeatherCount==1); // weather key invalidates header alone
 weather.valid=false;tick();assert(!tft.full&&menuWeatherCount==1);
 navigation=false;tick();full();assert(footerCount==1);
 navigation=true;tick();full();
 ++dispSettings.progressBarColor;tick();full(); // external appearance changes
 ++language;tick();full();
 advancedDisplay=true;++displayModeRevision;tick();full(); // Local/Web mode selection invalidates retained layout.
 advancedDisplay=false;++displayModeRevision;tick();full();
 strcpy(printers[0].config.name,"Renamed");tick();full();assert(has("Renamed"));
 tick(true);full();assert(footerCount==1);
 screen=SCREEN_HMS;tick(true);full();assert(hmsCount==1&&!bodyCount);
 screen=0;tick();full();assert(bodyCount==1); // cached normal canvas was invalidated
 glowLatched=true;tick();assert(glowArmed&&!glowLatched&&!bodyCount&&!tft.full); // pending event while cache unchanged
 glowArmed=true;tick();full();
 cleanupAtTick=true;tick();full();assert(!painted); // glow ends during drawing
 tick();full();assert(painted);
 glowCleanup=true;tick();full(); // cleanup already pending before drawing
 ap=true;tick();full();assert(setupCount==1);
 ap=false;tick();full();assert(bodyCount==1);
 ota=true;tick();assert(!frames);
 ota=false;tick();full();assert(cancelCount==1);
 page=Page::Details;painted=false;tick();full();assert(detailCount==1);
 tick();assert(!tft.full&&tft.clears.empty()&&!detailCount);m.chamberTemp.set(37,currentMs);tick();
 assert(!tft.full&&!probes&&detailCount==1&&cleared(24,84,752,340));
 m.partFanRoundedPct=51;tick();assert(!tft.full&&detailCount==1);
 page=Page::Clock;painted=false;tick();assert(clockCount==1&&!lastClockPartial);
 tick();assert(clockCount==1&&lastClockPartial&&!probes);
 advancedDisplay=true;++displayModeRevision;tick();assert(clockCount==1&&!lastClockPartial);
 advancedDisplay=false;++displayModeRevision;tick();assert(clockCount==1&&!lastClockPartial);
 // First layer can arrive without a percentage/ETA or clock-minute change.
 // It changes presentation and must redraw labels, not just animate the icon.
 m.layerNum.set(0,currentMs);tick();assert(clockCount==1&&!lastClockPartial);
 assert(clockHasProgress(m,true,currentMs)&&ws43b_view::statusCurrent(m,true,currentMs));
 assert(!ws43b_view::printProgressVisible(m,true,currentMs)); // Dashboard retains its first-layer gate.
 const auto progressBefore=m.progress.value;const auto progressTime=m.progress.updatedMs;
 m.layerNum.set(1,currentMs);tick();assert(clockCount==1&&!lastClockPartial);
 assert(clockHasProgress(m,true,currentMs)&&m.progress.value==progressBefore&&m.progress.updatedMs==progressTime);
 tick();assert(clockCount==1&&lastClockPartial);
 // The latch alone is also a dependency if the parser invalidates a sparse layer.
 m.layerNum.set(0,currentMs);tick();assert(clockCount==1&&!lastClockPartial);
 m.printedLayerSeen=true;tick();assert(clockCount==1&&!lastClockPartial);
 assert(clockHasProgress(m,true,currentMs));
 // A new stage can keep the same percentage, ETA, minute and layer state.
 // Its caption still needs a full label redraw; subsequent frames stay partial.
 m.printStage.set(4,currentMs);tick();assert(clockCount==1&&!lastClockPartial);
 tick();assert(clockCount==1&&lastClockPartial);
 m.printStage.set(24,currentMs);tick();assert(clockCount==1&&!lastClockPartial);
 tick();assert(clockCount==1&&lastClockPartial);
 page=Page::Ams;painted=false;tick();full();assert(bodyCount==1);
 seed(printers[1].state.monitor);rotState.displayIndex=1;tick();full();
 rxPending=true;currentMs+=100;resetOps();renderWs43bMonitor(false);assert(!frames);
 painted=false;resetOps();renderWs43bMonitor(false);full(); // touch/new view bypasses backpressure
 // Exercise the real dispatcher at its new cadence, not just the pure timer.
 rxPending=false;page=Page::Dashboard;weatherConfig.enabled=true;weather.valid=true;
 ws43b_native::headCached=true;seed(printers[rotState.displayIndex].state.monitor);tick(true);full();
 currentMs+=49;resetOps();renderWs43bMonitor(false);assert(!animationCount);
 currentMs+=1;resetOps();renderWs43bMonitor(false);assert(activityCount==1&&!weatherIconCount);
 currentMs+=34;resetOps();renderWs43bMonitor(false);assert(!activityCount&&weatherIconCount==1);
 // A failed optional cache cannot accidentally accelerate the expensive path.
 ws43b_native::headCached=false;tick(true);full();
 currentMs+=50;resetOps();renderWs43bMonitor(false);assert(!animationCount);
 currentMs+=34;resetOps();renderWs43bMonitor(false);assert(activityCount==1&&weatherIconCount==1);
 // RX still blocks decoration; a new view/touch must bypass that backpressure.
 rxPending=true;currentMs+=100;resetOps();renderWs43bMonitor(false);assert(!frames);
 painted=false;resetOps();renderWs43bMonitor(false);full();
 // In simple mode, observed bed cooling must not replace an active MQTT
 // percentage. Advanced retains its explicit cooling view; FINISH permits
 // cooling in either mode. Switching modes must invalidate the same canvas.
 rxPending=false;advancedDisplay=false;++displayModeRevision;
 auto &cool=printers[rotState.displayIndex].state.monitor;
 seed(cool);cool.progress.set(99,currentMs);cool.nozzleTarget.set(0,currentMs);
 cool.bedTarget.set(0,currentMs);cool.bedTemp.set(50,currentMs);tick(true);
 cool.bedTemp.set(49,currentMs);tick();assert(!dashboardCooling);
 advancedDisplay=true;++displayModeRevision;cool.bedTemp.set(48,currentMs);
 tick();assert(dashboardCooling&&bodyCount==1);
 advancedDisplay=false;++displayModeRevision;tick();assert(!dashboardCooling);
 cool.status.set("FINISH",currentMs);tick();assert(dashboardCooling&&bodyCount==1);
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
