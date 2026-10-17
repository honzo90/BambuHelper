"""Exercise real touch routing and the narrow NVS save path without hardware."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
display = (ROOT / 'src/display_ws43b.cpp').read_text()
settings = (ROOT / 'src/settings.cpp').read_text()
state = display[display.index('enum class Page'):display.index('void label(')]
cooling = display[display.index('bool coolingView('):display.index('void coolingScreen(')]
touch = display[display.index('void cancelWs43bMonitorTouch()'):display.index('void renderWs43bMonitor(bool force)')]
store = settings[settings.index('static uint8_t ws43bTheme'):settings.index('\n#endif\n\n// ---', settings.index('static uint8_t ws43bTheme'))]
harness = r'''
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
#include "bambu_monitor.h"
#include "ws43b_idle_policy.h"
#include "ws43b_dashboard_policy.h"
#include "ws43b_live_view.h"
#if !WS43B_FULL_WEBUI
struct {uint8_t displayIndex=0;} rotState;
#endif
namespace ws43b { bool otaDisplayActive(){return false;} }
#include "ws43b_clock_settings.h"
#include "ws43b_language.h"
struct WeatherConfig {bool enabled=false,solar=false;unsigned nightSeconds=30;char city[64]={};};
bool weatherEnabled=false;
WeatherConfig ws43bWeatherConfig(){WeatherConfig c;c.enabled=weatherEnabled;return c;}
bool saveWs43bWeather(WeatherConfig){return true;}
static bool polish = true;
bool ws43bPolish(){ return polish; }
bool saveWs43bLanguage(uint8_t value){ if(value>1)return false; polish=value==0;return true; }
bool advancedDisplay=false,modeWriteOk=true;unsigned modeWrites=0;uint32_t modeRevision=0;
bool ws43bAdvancedDisplay(){return advancedDisplay;}
uint32_t ws43bDisplayModeRevision(){return modeRevision;}
bool saveWs43bDisplayMode(bool advanced){
 if(advanced==advancedDisplay)return true;
 ++modeWrites;if(!modeWriteOk)return false;
 advancedDisplay=advanced;++modeRevision;return true;
}
void loadWs43bDisplayMode(){}
struct DisplaySettings { uint16_t bgColor, trackColor, progressBarColor; bool fanMatchPrinter; bool pongClock=false; } dispSettings{};
struct Printer { struct State {bool connected=true; BambuMonitorTelemetry monitor;} state; } printers[1];
static bool wifi=true;
bool dashboardCooling=false;
bool hmsScreenAlerting(){return false;}
static uint8_t backlight=255;
void setBacklight(uint8_t level){backlight=level;}
bool isWiFiConnected(){return wifi;}
static Ws43bClockSettings clockSettings;
const Ws43bClockSettings& ws43bClockSettings(){return clockSettings;}
bool saveWs43bClockSettings(uint16_t minutes,bool off,bool use24h){
 clockSettings.idleMinutes=minutes;clockSettings.screenOff=off;clockSettings.use24h=use24h;
 ++clockSettings.revision;return true;
}
constexpr const char *NVS_NAMESPACE="test";
static bool openOk=true, writeOk=true, configured=true, configuredSecond=false, ap=false, painted=true;
static unsigned writes=0;
static uint16_t persisted=0;
struct Preferences {
 bool begin(const char *ns, bool readonly) { assert(!strcmp(ns,NVS_NAMESPACE) && !readonly); return openOk; }
 size_t putUShort(const char *key, uint16_t value) {
   assert(!strcmp(key,"w43_view")); ++writes;
   if (!writeOk) return 0;
   persisted=value; return 2;
 }
 void end() {}
};
static uint32_t now=1000, lastFrame=0;
uint32_t millis(){return now;}
bool isPrinterConfigured(uint8_t slot){assert(slot<2);return configured&&(slot==0||configuredSecond);}
bool isAnyPrinterConfigured(){return configured;}
Printer& displayedPrinter(){return printers[0];}
#if WS43B_FULL_WEBUI
constexpr uint8_t MAX_ACTIVE_PRINTERS=2;
struct { uint8_t displayIndex=0; uint32_t lastRotateMs=0,displayHoldUntilMs=0,intervalMs=60000; } rotState;
#endif
void saveSettings(){}
unsigned factoryResets=0;void resetSettings(){++factoryResets;}
bool nightBlackout=false, nightWindow=false;
bool isNightModeActive(){return nightWindow || nightBlackout;}
bool isNightBlackout(){return nightBlackout;}
void nightWake(){nightBlackout=false;}
bool glowIsArmed(){return false;}
void glowDismiss(){}
bool hmsOpen=false;unsigned hmsOpens=0;
bool handleWs43bErrorTap(bool open){if(hmsOpen){hmsOpen=false;return true;}if(open){hmsOpen=true;++hmsOpens;return true;}return false;}
bool isAPMode(){return ap;}
''' + store + state + cooling + touch + r'''
void rawTap(uint16_t x,uint16_t y) {
 handleWs43bMonitorTouch(x,y,true); now+=100;
 handleWs43bMonitorTouch(x,y,false); now+=50;
}
void tap(uint16_t x, uint16_t y) {
 // Legacy scenario coordinates map to named destinations in the new layout.
 if(y==458) { if(x==250)x=450; else if(x==450 || x==500)x=650;
   else if(x==330){x=740;y=35;} }
 if(!navigationShown(now) && page!=Page::Clock && !automaticIdle && !screenOff)
   rawTap(799,430);
 rawTap(x,y);
}
int main() {
 // Boot recovery needs observed cooling, never FINISH alone or stale/heated data.
 { auto &m=printers[0].state.monitor;
   clockSettings.idleMinutes=0;configured=true;wifi=true;
   m.status.set("FINISH",now);m.bedTemp.set(43,now);
   updateIdleView(now);assert(page==Page::Dashboard);
   m.bedTarget.set(0,now);updateIdleView(now);assert(page==Page::Dashboard);
   ++now;m.status.set("FINISH",now);m.bedTemp.set(43,now);updateIdleView(now);assert(page==Page::Dashboard);
   ++now;m.bedTemp.set(42,now);updateIdleView(now);assert(page==Page::Clock && !coolingRecoveryPending);
   page=Page::Dashboard;++now;m.bedTemp.set(41,now);updateIdleView(now);assert(page==Page::Dashboard);
   coolingRecoveryPending=true;recoveryBedSeen=false;m.bedTarget.set(55,now);
   ++now;m.bedTemp.set(40,now);updateIdleView(now);assert(page==Page::Dashboard);
   m.status.set("RUNNING",now);updateIdleView(now);assert(!coolingRecoveryPending);
#if WS43B_FULL_WEBUI
   nightWindow=true;m.status.set("FINISH",now);updateIdleView(now);
   assert(page==Page::Clock && !coolingView(m)); // No observed cooling supplied by renderer.
   nightBlackout=true;updateIdleView(now);assert(screenOff && backlight==0);
   nightBlackout=false;nightWindow=false;
#endif
   m=BambuMonitorTelemetry{};previousFreshState=0;page=Page::Dashboard;
   updateIdleView(now);
 }

 // Dashboard hitboxes follow the compact native header and exclude cards.
 struct TapPoint {uint16_t x,y;};
 weatherEnabled=true;
 for(const auto p:{TapPoint{600,0},{606,35},{657,35},{672,37},{693,55},{700,0},{740,35},{799,55}}) {
  page=Page::Dashboard;tap(p.x,p.y);assert(page==Page::Clock && hmsOpens==0);
 }
 for(const auto p:{TapPoint{520,35},{544,35},{599,35},{694,35},{699,35},
                  {600,56},{693,66},{700,56},{740,66},{200,415},{600,415}}) {
  page=Page::Dashboard;tap(p.x,p.y);assert(page==Page::Dashboard && hmsOpens==0);
 }
#if WS43B_FULL_WEBUI
 for(const auto p:{TapPoint{216,0},{220,31},{239,55}}) {
  page=Page::Dashboard;const auto before=hmsOpens;
  tap(p.x,p.y);assert(hmsOpen&&hmsOpens==before+1);
  tap(606,35);assert(!hmsOpen&&page==Page::Dashboard); // Dismiss only.
  tap(606,35);assert(page==Page::Clock&&hmsOpens==before+1);
 }
 for(const auto p:{TapPoint{240,35},{220,56},{220,66}}) {
  page=Page::Dashboard;const auto before=hmsOpens;
  tap(p.x,p.y);assert(!hmsOpen&&hmsOpens==before&&page==Page::Dashboard);
 }
 // Enable a second configured printer only for selector boundary checks.
 configuredSecond=true;
 for(const auto p:{TapPoint{0,0},{100,35},{215,55}}) {
  page=Page::Dashboard;rotState.displayIndex=0;
  tap(p.x,p.y);assert(rotState.displayIndex==1&&page==Page::Dashboard);
 }
 for(const auto p:{TapPoint{215,56},{20,66},{100,80},{200,120},{430,35}}) {
  page=Page::Dashboard;rotState.displayIndex=0;
  tap(p.x,p.y);assert(rotState.displayIndex==0&&page==Page::Dashboard);
 }
 // Other pages retain their original header regions, including y=66..79.
 for(Page destination:{Page::Ams,Page::Details,Page::Settings}) {
  for(const auto p:{TapPoint{0,0},{100,66},{439,79}}) {
   page=destination;rotState.displayIndex=0;
   tap(p.x,p.y);assert(rotState.displayIndex==1&&page==destination);
  }
  for(const auto p:{TapPoint{440,35},{100,80},{606,35}}) {
   page=destination;rotState.displayIndex=0;
   tap(p.x,p.y);assert(rotState.displayIndex==0&&page==destination);
  }
  for(const auto p:{TapPoint{658,0},{672,37},{689,65}}) {
   page=destination;const auto before=hmsOpens;
   tap(p.x,p.y);assert(hmsOpen&&hmsOpens==before+1&&page==destination);
   tap(700,35);assert(!hmsOpen&&page==destination);
  }
 }
 configuredSecond=false;rotState.displayIndex=0;
#endif
 for(Page destination:{Page::Ams,Page::Details,Page::Settings}) {
  for(const auto p:{TapPoint{690,0},{740,35},{799,65}}) {
   page=destination;tap(p.x,p.y);assert(page==Page::Clock);
  }
  for(const auto p:{TapPoint{690,66},{740,70},{606,35}}) {
   page=destination;tap(p.x,p.y);assert(page==destination);
  }
 }
 weatherEnabled=false;
 for(unsigned x:{600u,606u,657u,693u}) {
  page=Page::Dashboard;const auto before=hmsOpens;
  tap(x,35);assert(page==Page::Dashboard&&hmsOpens==before);
 }

 applyWs43bViewSettings(0,true);
 assert(!saveWs43bViewSettings(3,false) && writes==0);
 assert(saveWs43bViewSettings(0,true) && writes==0);
 openOk=false; assert(!saveWs43bViewSettings(1,true) && ws43bViewTheme()==0);
 openOk=true; writeOk=false;
 assert(!saveWs43bViewSettings(1,true) && ws43bViewTheme()==0);
 writeOk=true; writes=0;
 tap(250,458); assert(page==Page::Details && writes==0);
 tap(450,458); assert(page==Page::Settings && writes==0);
 // Gaps and opening categories must never change persisted values.
 tap(400,190);assert(page==Page::Settings && writes==0);
 tap(100,260);assert(page==Page::Settings && writes==0);
 tap(100,190);assert(page==Page::Appearance && writes==0);
 tap(310,240); assert(ws43bViewTheme()==1 && writes==1 && persisted==0x105);
 tap(310,240); assert(writes==1); // Holding/reselecting does not wear NVS.
 // Global display-mode controls share the same Appearance page but do not
 // overlap theme selection or the gap between Simple and Advanced.
 assert(!advancedDisplay&&modeWrites==0);
 for(const auto p:{TapPoint{43,370},{264,370},{275,370},{752,370},{300,346},{300,393}}){
  rawTap(p.x,p.y);assert(!advancedDisplay&&modeWrites==0&&writes==1);
 }
 painted=true;rawTap(300,370);
 assert(advancedDisplay&&modeWrites==1&&modeRevision==1&&!painted&&writes==1);
 rawTap(300,370);assert(advancedDisplay&&modeWrites==1); // Reselect is no-op.
 modeWriteOk=false;rawTap(100,370);
 assert(advancedDisplay&&modeWrites==2&&modeRevision==1&&settingsNotice);
 modeWriteOk=true;rawTap(100,370);
 assert(!advancedDisplay&&modeWrites==3&&modeRevision==2&&writes==1);
 // Drag and cancelled contact never save the display mode.
 handleWs43bMonitorTouch(300,370,true);now+=100;
 handleWs43bMonitorTouch(350,370,true);now+=100;
 handleWs43bMonitorTouch(350,370,false);assert(!advancedDisplay&&modeWrites==3);
 handleWs43bMonitorTouch(300,370,true);cancelWs43bMonitorTouch();now+=100;
 handleWs43bMonitorTouch(300,370,false);assert(!advancedDisplay&&modeWrites==3);

 tap(100,115);tap(600,300);assert(page==Page::GeneralSettings);
 unsigned beforeQrWrites=writes;
 rawTap(500,305);assert(page==Page::WebQr && writes==beforeQrWrites);
 rawTap(500,230);assert(page==Page::WebQr && writes==beforeQrWrites);
 rawTap(100,100);assert(page==Page::GeneralSettings && writes==beforeQrWrites);
 tap(100,240); assert(!dispSettings.fanMatchPrinter && writes==2 && persisted==0x101);
 tap(100,115);tap(100,190);assert(page==Page::Appearance);
 writeOk=false; tap(560,305);
 assert(ws43bViewTheme()==1 && !dispSettings.fanMatchPrinter);
 assert(strstr(settingsNotice,"Blad") && writes==3);
 writeOk=true;
 // Drag, very short tap, long hold and failed I2C read cannot commit settings.
 handleWs43bMonitorTouch(560,305,true); now+=100;
 handleWs43bMonitorTouch(600,305,true); now+=100;
 handleWs43bMonitorTouch(600,305,false); assert(writes==3);
 handleWs43bMonitorTouch(560,305,true); now+=10;
 handleWs43bMonitorTouch(560,305,false); assert(writes==3);
 handleWs43bMonitorTouch(560,305,true); now+=1001;
 handleWs43bMonitorTouch(560,305,false); assert(writes==3);
 handleWs43bMonitorTouch(560,305,true); cancelWs43bMonitorTouch();
 now+=100; handleWs43bMonitorTouch(560,305,true);
 handleWs43bMonitorTouch(560,305,false); assert(writes==3);
 ap=true; tap(560,305); assert(writes==3); ap=false;
 handleWs43bMonitorTouch(0,0,false);
 now=UINT32_MAX-50; tap(560,305); assert(ws43bViewTheme()==2 && writes==4);
 tap(60,458); assert(page==Page::Dashboard && writes==4);
 // Manual clock and the settings subpage use the new footer hitboxes.
 tap(330,458); assert(page==Page::Clock);
 tap(100,220); assert(page==Page::Dashboard);
 tap(330,458); assert(page==Page::Clock);
 tap(450,458); assert(page==Page::Dashboard); // Fullscreen: no invisible settings hitbox.
 tap(330,458); assert(page==Page::Clock);
 tap(100,30); assert(page==Page::Dashboard); // No invisible printer selector.
 tap(450,458); tap(600,190); assert(page==Page::ClockSettings);
 tap(100,175); assert(clockSettings.idleMinutes==1);
 tap(100,240); assert(clockSettings.screenOff);
 tap(100,305); assert(!clockSettings.use24h);
 tap(100,115); assert(page==Page::Settings);
 // All submenus return to the overview at N, then sleep at 2N.
 // The policy uses monotonic time, not incoming printer telemetry.
 for(Page submenu:{Page::Details,Page::Ams,Page::Gauges,Page::Appearance,Page::GeneralSettings,Page::Settings,Page::ClockSettings,Page::WeatherSettings}) {
   for(bool off:{false,true}) {
     clockSettings.idleMinutes=1;clockSettings.screenOff=off;++clockSettings.revision;
     page=submenu;automaticIdle=false;screenOff=false;backlight=255;
     updateIdleView(now);now+=59999;updateIdleView(now);assert(page==submenu && !automaticIdle);
     ++now;painted=true;updateIdleView(now);
     assert(page==Page::Dashboard && !automaticIdle && !screenOff && !painted && navigationShown(now));
     now+=59999;updateIdleView(now);assert(page==Page::Dashboard && !automaticIdle);
     ++now;updateIdleView(now);assert(page==Page::Clock && automaticIdle && screenOff==off);
     tap(799,430);assert(page==Page::Dashboard && !automaticIdle && !screenOff);
   }
 }
 // Touch near expiry postpones the submenu return; disabled timeout never returns.
 page=Page::Settings;clockSettings.idleMinutes=1;++clockSettings.revision;
 updateIdleView(now);now+=59000;tap(799,430);now+=59000;updateIdleView(now);
 assert(page==Page::Settings);now+=1000;updateIdleView(now);assert(page==Page::Dashboard);
 page=Page::Details;clockSettings.idleMinutes=0;++clockSettings.revision;
 updateIdleView(now);now+=3600000;updateIdleView(now);assert(page==Page::Details && !automaticIdle);
 // Changing the configured interval starts a complete new submenu interval.
 page=Page::Ams;clockSettings.idleMinutes=1;++clockSettings.revision;updateIdleView(now);
 now+=30000;clockSettings.idleMinutes=5;++clockSettings.revision;updateIdleView(now);
 now+=299999;updateIdleView(now);assert(page==Page::Ams);
 ++now;updateIdleView(now);assert(page==Page::Dashboard);
 // Wrap around uint32 milliseconds also performs exactly one return.
 page=Page::Settings;clockSettings.idleMinutes=1;clockSettings.screenOff=true;++clockSettings.revision;
 now=UINT32_MAX-30000;updateIdleView(now);now+=60000;updateIdleView(now);
 assert(page==Page::Dashboard && !automaticIdle);now+=60000;updateIdleView(now);
 assert(automaticIdle && screenOff);tap(799,430);
 // Restore a fresh overview interval for the existing idle regression scenarios.
 page=Page::Dashboard;++clockSettings.revision;
 // Non-printing states still permit timeout; telemetry does not count as touch.
 now=200000; auto& status=printers[0].state.monitor.status;
 status.set("IDLE",now); updateIdleView(now); assert(!screenOff);
 now+=59999; updateIdleView(now); assert(!screenOff);
 ++now; updateIdleView(now); assert(screenOff && automaticIdle && backlight==0);
 tap(450,458); assert(!screenOff && !automaticIdle && backlight==255 && page==Page::Dashboard);
 for(const char* stateName:{"FAILED","UNKNOWN","FINISH"}) {
   status.set(stateName,now);updateIdleView(now);
   for(unsigned second=0;second<59;++second) {
     now+=1000;status.set(stateName,now);updateIdleView(now);assert(!screenOff);
   }
   // A touch immediately before the deadline postpones it by a full minute.
   tap(799,430);now+=59849;status.set(stateName,now);updateIdleView(now);assert(!screenOff);
   ++now;updateIdleView(now);assert(screenOff && automaticIdle && backlight==0);
   tap(450,458);assert(!screenOff && page==Page::Dashboard);
 }
 // Daytime printing returns every submenu (including manual clock) to Print,
 // then stays there for repeated idle intervals while telemetry stays fresh.
 for(const char* printing:{"RUNNING","PREPARE","PAUSE"}) {
   for(Page submenu:{Page::Dashboard,Page::Details,Page::Ams,Page::Gauges,Page::Appearance,Page::GeneralSettings,Page::Settings,Page::ClockSettings,Page::WeatherSettings,Page::Clock}) {
     clockSettings.idleMinutes=1;++clockSettings.revision;
     status.set(printing,now);updateIdleView(now);page=submenu;
     now+=59999;status.set(printing,now);updateIdleView(now);assert(page==submenu);
     ++now;status.set(printing,now);updateIdleView(now);
     assert(page==Page::Dashboard && !automaticIdle && !screenOff);
     for(int n=0;n<3;++n) {
       now+=60000;status.set(printing,now);updateIdleView(now);
       assert(page==Page::Dashboard && !automaticIdle && !screenOff);
     }
   }
 }
#if WS43B_FULL_WEBUI
 // Night schedule overrides daytime printing, and morning restores Print.
 nightWindow=true;nightBlackout=true;status.set("RUNNING",now);updateIdleView(now);
 assert(screenOff);
 tap(799,430);assert(!screenOff && page==Page::Dashboard);
 nightBlackout=true;now+=30000;status.set("RUNNING",now);updateIdleView(now);assert(screenOff);
 nightWindow=false;nightBlackout=false;status.set("RUNNING",now);updateIdleView(now);
 assert(page==Page::Dashboard && !screenOff);
 now+=60000;status.set("RUNNING",now);updateIdleView(now);
 assert(page==Page::Dashboard && !automaticIdle);
#endif
 // A stale active status cannot hold the display awake indefinitely.
 now+=60001;updateIdleView(now);assert(automaticIdle && screenOff);
 tap(799,430);status.set("IDLE",now);updateIdleView(now);
 // A state change and AMS drying halfway through must not restart the timer.
 updateIdleView(now);now+=30000;status.set("IDLE",now);
 auto& unit=printers[0].state.monitor.amsUnits[0];unit.used=true;unit.dryRemainMin.set(10,now);
 updateIdleView(now);now+=30000;updateIdleView(now);assert(screenOff);
 wifi=false;printers[0].state.connected=false;updateIdleView(now);assert(screenOff);
 now+=60001;updateIdleView(now);assert(screenOff); // stale data does not wake
 wifi=true;printers[0].state.connected=true;status.set("FINISH",now);
 updateIdleView(now);assert(screenOff); // reconnect and finish do not wake
 tap(450,458);assert(!screenOff && page==Page::Dashboard);
 // No telemetry at all still allows timeout on a configured panel.
 status={};wifi=false;printers[0].state.connected=false;
 updateIdleView(now);now+=60000;updateIdleView(now);assert(screenOff);
 ++clockSettings.revision;clockSettings.idleMinutes=0;updateIdleView(now);assert(!screenOff);
 ++clockSettings.revision;clockSettings.idleMinutes=1;updateIdleView(now);
 now+=60000;updateIdleView(now);assert(screenOff);
 // Setup remains visible, and returning to normal gives a full interval.
 ap=true;updateIdleView(now);assert(!screenOff);now+=60000;updateIdleView(now);assert(!screenOff);
 ap=false;configured=false;updateIdleView(now);assert(!idleEligible());
 configured=true;updateIdleView(now);now+=59999;updateIdleView(now);assert(!screenOff);
 ++now;updateIdleView(now);assert(screenOff);
 tap(450,458);assert(!screenOff);wifi=true;printers[0].state.connected=true;
 // Clock-only mode still follows the timeout without switching the backlight off.
 ++clockSettings.revision;clockSettings.screenOff=false;updateIdleView(now);
 now+=60000;updateIdleView(now);assert(automaticIdle && !screenOff && page==Page::Clock && backlight==255);
 tap(450,458);assert(!automaticIdle && page==Page::Dashboard);
 status.set("RUNNING",now);updateIdleView(now);page=Page::Clock;
 updateIdleView(now);assert(page==Page::Clock);
 status.set("PAUSE",now);updateIdleView(now);assert(page==Page::Dashboard);
 // Last-layer/100% while RUNNING does not trigger completion.
 status.set("RUNNING",now);updateIdleView(now);
 printers[0].state.monitor.progress.set(100,now);
 printers[0].state.monitor.layerNum.set(60,now);printers[0].state.monitor.totalLayers.set(60,now);
 updateIdleView(now);assert(page==Page::Dashboard && !coolingView(printers[0].state.monitor));
 status.set("FINISH",now);updateIdleView(now);assert(page==Page::Clock && !coolingView(printers[0].state.monitor)); // FINISH alone is insufficient.
 tap(100,220);assert(page==Page::Dashboard);
 updateIdleView(now);assert(page==Page::Dashboard); // Repeated FINISH does not steal focus.

 wifi=false;updateIdleView(now);page=Page::Clock;
 wifi=true;status.set("RUNNING",now);updateIdleView(now);assert(page==Page::Dashboard);
#if WS43B_FULL_WEBUI
 idlePolicy.activity(now);nightBlackout=true;updateIdleView(now);assert(screenOff);
 tap(450,458);assert(!nightBlackout&&!screenOff&&page==Page::Dashboard);
 updateIdleView(now);assert(!screenOff);
 // Additional gauge navigation does not write any settings.
 tap(250,458);tap(650,105);assert(page==Page::Gauges);
#endif
 tap(500,458);assert(page==Page::Settings);
 // Hidden footer: the first contact reveals only, second selects AMS.
 page=Page::Dashboard;navigationActivity=now;now+=5000;
 assert(!navigationShown(now));rawTap(280,458);assert(page==Page::Dashboard && navigationShown(now));
 rawTap(280,458);assert(page==Page::Ams);
 rawTap(600,105);assert(selectedAms==1);
 rawTap(650,458);assert(page==Page::Settings);
 now+=6000;assert(navigationShown(now)); // Settings are pinned.
 const auto writesBeforeCategories=writes;
 rawTap(100,300);assert(page==Page::WeatherSettings && writes==writesBeforeCategories);
 rawTap(100,115);assert(page==Page::Settings);
 rawTap(600,190);assert(page==Page::ClockSettings);
 rawTap(100,115);assert(page==Page::Settings && writes==writesBeforeCategories);
 const auto beforeLanguage=writes;
 tap(600,300);assert(page==Page::GeneralSettings);
 tap(450,175);assert(!polish && writes==beforeLanguage);
 tap(450,175);assert(polish && writes==beforeLanguage);
 page=Page::Settings;rawTap(710,100);assert(page==Page::Settings);
 handleWs43bMonitorTouch(710,100,true);now+=2999;handleWs43bMonitorTouch(710,100,false);assert(page==Page::Settings);
 handleWs43bMonitorTouch(710,100,true);now+=3000;cancelWs43bMonitorTouch();handleWs43bMonitorTouch(710,100,false);assert(page==Page::Settings);
 handleWs43bMonitorTouch(710,100,true);now+=1500;handleWs43bMonitorTouch(630,100,true);now+=1600;handleWs43bMonitorTouch(710,100,false);assert(page==Page::Settings);
 handleWs43bMonitorTouch(710,100,true);now+=3000;handleWs43bMonitorTouch(710,100,true);assert(page==Page::Settings && factoryResets==0);
 handleWs43bMonitorTouch(710,100,false);assert(page==Page::System && factoryResets==0);
 rawTap(100,100);assert(page==Page::Settings);
 // Entry also works across the millis() wrap boundary.
 now=0xffffff00u;handleWs43bMonitorTouch(710,100,true);now+=3000;handleWs43bMonitorTouch(710,100,false);assert(page==Page::System);

 rawTap(300,190);assert(page==Page::FactoryReset && factoryResets==0);
 rawTap(300,320);assert(factoryResets==0);
 handleWs43bMonitorTouch(300,320,true);now+=2999;handleWs43bMonitorTouch(300,320,false);assert(factoryResets==0);
 handleWs43bMonitorTouch(300,320,true);now+=3100;cancelWs43bMonitorTouch();handleWs43bMonitorTouch(300,320,false);assert(factoryResets==0);
 handleWs43bMonitorTouch(300,320,true);now+=1500;handleWs43bMonitorTouch(300,260,true);now+=1600;handleWs43bMonitorTouch(300,320,false);assert(factoryResets==0);
 rawTap(300,395);assert(page==Page::System && factoryResets==0);
 rawTap(300,190);assert(page==Page::FactoryReset);
 handleWs43bMonitorTouch(300,320,true);now+=3000;handleWs43bMonitorTouch(300,320,true);assert(factoryResets==0);
 handleWs43bMonitorTouch(300,320,false);assert(factoryResets==1);

}
'''
with tempfile.TemporaryDirectory(prefix='ws43b-view-') as tmp:
    source = Path(tmp) / 'test.cpp'
    binary = Path(tmp) / 'test'
    source.write_text(harness)
    subprocess.run(['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                    '-DBOARD_IS_WS43B=1', '-I', str(ROOT/'include'), '-I', str(ROOT/'src'),
                    str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
    subprocess.run(['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                    '-DBOARD_IS_WS43B=1', '-DWS43B_FULL_WEBUI=1',
                    '-I', str(ROOT/'include'), '-I', str(ROOT/'src'),
                    str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print('PASS: both portal profiles; timeout during print/drying/offline, touch reset/wake, navigation and local settings')
