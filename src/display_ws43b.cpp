#include "ws43b_weather_icons.h"
#include "ws43b_style.h"
#include "ws43b_live_view.h"
#include "ws43b_repaint_plan.h"
#include "ws43b_animation_policy.h"
#include "config.h"
#if defined(BOARD_IS_WS43B)
#include "ws43b_weather.h"
#include "ws43b_weather_background.h"
#include "display_ws43b.h"
#include "display_ui.h"
#include "bambu_state.h"
#include "bambu_mqtt.h"
#include "wifi_manager.h"
#include "ws43b_hardware.h"
#include "settings.h"
#include "clock_mode.h"
#if WS43B_FULL_WEBUI
#include "display_edge_glow.h"
#include "clock_pong.h"
#endif
#include "fonts.h"
#include "fonts/ws43b_modern.h"
#include "fonts/ws43b_dashboard_v2.h"
#include "ws43b_native_scene.h"
#include "ws43b_print_scene.h"
#include "ws43b_ui_icons.h"
#include "ws43b_boot_scene.h"
#include "ws43b_drying_scene.h"
#include "ws43b_clock_settings.h"
#include "ws43b_display_mode.h"
#include "ws43b_language.h"
#include "ws43b_idle_policy.h"
#include "ws43b_water_clock.h"
#include "ws43b_dashboard_policy.h"
#include <WiFi.h>
#include <stdio.h>
#include <time.h>

namespace {
constexpr uint16_t CARD = ws43b_style::card;
uint16_t INK = 0xF7BE, DIM = 0x9D34, GREEN = 0x77B2;
constexpr uint16_t WARN = 0xF5CB, RED = 0xF38F;
uint16_t BG = ws43b_style::background, ACCENT = ws43b_style::mint, TRACK = ws43b_style::border;
uint32_t lastFrame = 0;
bool painted = false;
enum class Page { Dashboard, Details, Clock, Settings, ClockSettings, Gauges, Ams, WeatherSettings, Appearance, GeneralSettings, WebQr, System, FactoryReset };
Page page = Page::Dashboard;
uint32_t navigationActivity = 0;
uint8_t selectedAms = 0;
ws43b_live::View liveView() {
  using V=ws43b_live::View;
  if(page==Page::Dashboard)return V::Dashboard;
  if(page==Page::Details)return V::Details;
  if(page==Page::Gauges)return V::Gauges;
  if(page==Page::Ams)return V::Ams;
  if(page==Page::Clock)return V::Clock;
  return V::None;
}
unsigned liveAms(const BambuMonitorTelemetry &m) {
  for(unsigned step=0;step<6;++step) {
    const unsigned i=page==Page::Ams?(selectedAms+step)%6:step;
    if(m.amsUnits[i].used&&!(m.amsUnits[i].present.valid&&!m.amsUnits[i].present.value))return i;
  }
  return 0;
}
bool navigationShown(uint32_t now) {
  return ws43b_view::navigationVisible(now, navigationActivity,
      page == Page::System || page == Page::FactoryReset || page == Page::Appearance || page == Page::WebQr || page == Page::GeneralSettings || page == Page::Settings || page == Page::ClockSettings || page == Page::WeatherSettings);
}
bool touchHeld = false, touchMoved = false, touchNeedsRelease = false;
uint16_t pressX = 0, pressY = 0;
uint32_t pressMs = 0;
bool systemTouchArea(uint16_t x,uint16_t y) { return x>=660 && x<776 && y>=82 && y<124; }
const char *settingsNotice = nullptr;
ws43b_view::IdlePolicy idlePolicy;
bool automaticIdle = false, screenOff = false;
uint8_t previousFreshState = 0;
bool coolingRecoveryPending = true;
bool recoveryBedSeen = false;
float recoveryBedTemp = 0;
uint32_t recoveryBedSample = 0;
uint32_t nightActivity=0;
bool previousNight=false;
bool idleEligible() {
  // Inactivity means no touch, regardless of printer activity or telemetry.
  // Keep initial setup visible until the panel has a configured printer.
  return isAnyPrinterConfigured() && !isAPMode();
}
void updateIdleView(uint32_t now) {
  const auto &clock = ws43bClockSettings();
  // A newly reported print/pause/failure/finish brings a manually opened clock
  // back to monitoring too, including reconnect after unknown/stale data.
  const auto &state = displayedPrinter().state;
  const auto &status = state.monitor.status;
  const bool online = isWiFiConnected() && state.connected;
  uint8_t current = 0;
  if (ws43b_view::statusCurrent(state.monitor, online, now)) {
    if (!strcmp(status.value, "IDLE")) current = 1;
    else if (!strcmp(status.value, "FINISH")) current = 2;
    else if (!strcmp(status.value, "RUNNING")) current = 3;
    else if (!strcmp(status.value, "PREPARE")) current = 4;
    else if (!strcmp(status.value, "PAUSE")) current = 5;
    else if (!strcmp(status.value, "FAILED")) current = 6;
    else current = 7;
  }
  bool night=false;
#if WS43B_FULL_WEBUI
  night=isNightModeActive();
#endif
  if(night!=previousNight){nightActivity=now;previousNight=night;}
  const bool nightExpired=night && uint32_t(now-nightActivity)>=uint32_t(ws43bWeatherConfig().nightSeconds)*1000u;
  bool daytimePrint = current == 3 || current == 4 || current == 5 ||
                      ws43b_view::waitingForJobData(state.monitor, online, now, state.printing);
#if WS43B_FULL_WEBUI
  daytimePrint = daytimePrint && !isNightModeActive();
#endif
  bool idle = idlePolicy.update(now, idleEligible(), clock.idleMinutes, clock.revision);
  if(night)idle=nightExpired;
  // A fresh active job keeps the overview visible by day. Do not reset the
  // inactivity timer from telemetry: expiry returns submenus/manual clock home.
  if (idle && daytimePrint) {
    if (page != Page::Dashboard) {
      page = Page::Dashboard;
      navigationActivity = now;
      painted = false;
    }
    idle = false;
  } else if (idle && !night && !automaticIdle && page != Page::Dashboard && page != Page::Clock) {
    // Outside a daytime print, retain the two-stage submenu/idle policy.
    page = Page::Dashboard;
    idlePolicy.activity(now);
    navigationActivity = now;
    idle = false;
    painted = false;
  }
  if (idle != automaticIdle) {
    automaticIdle = idle;
    page = idle ? Page::Clock : Page::Dashboard;
    painted = false;
  }
  const bool wantOff = (idle && !night && clock.screenOff)
#if WS43B_FULL_WEBUI
    || isNightBlackout()
#endif
    ;
  if (wantOff != screenOff) {
    screenOff = wantOff;
    setBacklight(screenOff ? 0 : 255);
    painted = false;
  }
  // After boot, recover an already finished job only from fresh evidence of
  // falling bed temperature with the heater target off. No guessed safe-removal
  // threshold, synthetic print state, or wake of a blacked-out screen.
  bool recoveredCooling=false;
  if(coolingRecoveryPending) {
    const auto &m=state.monitor;
    if(current!=0 && current!=2)coolingRecoveryPending=false;
    else if(current==2 && m.bedTemp.current(now) && m.bedTarget.current(now) && m.bedTarget.value==0) {
      if(recoveryBedSeen && m.bedTemp.updatedMs!=recoveryBedSample && m.bedTemp.value<recoveryBedTemp) {
        recoveredCooling=true;coolingRecoveryPending=false;
      }
      recoveryBedSeen=true;recoveryBedTemp=m.bedTemp.value;recoveryBedSample=m.bedTemp.updatedMs;
    } else recoveryBedSeen=false;
  }
  // An observed active-job -> FINISH transition opens cooling immediately.
  // A stale state, 100% progress or reaching the last layer is not completion.
  if (recoveredCooling || (current == 2 && (previousFreshState == 3 || previousFreshState == 4 || previousFreshState == 5))) {
    page = Page::Clock;
    painted = false;
  }
  if (page == Page::Clock && !automaticIdle && current != 2 &&
      current != previousFreshState && (current == 0 || current >= 2)) {
    page = Page::Dashboard;
    painted = false;
  }
  previousFreshState = current;
}
void label(const char *text, int x, int y, int w, int h,
           const lgfx::IFont *font, uint16_t color = INK) {
  tft.setFont(font);
  tft.setTextColor(color);
  tft.setTextDatum(TL_DATUM);
  tft.setClipRect(x, y, w, h);
  tft.drawString(text, x, y);
  tft.clearClipRect();
}
void small(const char *text, int x, int y, int w, uint16_t color = DIM) {
  if(!text || !*text)return;
  ::setFont(tft,FONT_NONE);tft.loadFont(ws43b_dash_14);tft.setTextSize(1);
  tft.setTextColor(color);tft.setTextDatum(TL_DATUM);tft.setClipRect(x,y,w,24);
  tft.drawString(text,x,y);tft.clearClipRect();tft.unloadFont();
}
void button(const char *text, int x, int y, int w, int h, bool active) {
  tft.fillRoundRect(x, y, w, h, 9, CARD);
  tft.drawRoundRect(x, y, w, h, 9, active ? ACCENT : TRACK);
  ::setFont(tft,FONT_NONE);tft.loadFont(ws43b_dash_18);tft.setTextSize(1);
  tft.setTextColor(active?ACCENT:INK);tft.setTextDatum(TL_DATUM);
  tft.setClipRect(x+12,y,w-24,h);
  tft.drawString(text,x+12,y+(h-20)/2);
  tft.clearClipRect();tft.unloadFont();
}
// Fonts are loaded only while drawing; reset the shared font cache as on the clock.
void dashText(const char *text, int x, int y, int w, int size=18, uint16_t color=INK) {
  ::setFont(tft, FONT_NONE);
  const uint8_t *font = size==72 ? ws43b_dash_large : size==30 ? ws43b_dash_30 :
                        size==24 ? ws43b_dash_24 : size==14 ? ws43b_dash_14 : ws43b_dash_18;
  tft.loadFont(font); tft.setTextSize(1); tft.setTextColor(color);
  tft.setTextDatum(TL_DATUM); tft.setClipRect(x,y,w,size+10);
  if(text) {
    if(size==72 && tft.textWidth(text)>w) {
      tft.unloadFont();tft.loadFont(ws43b_dash_30);tft.setTextSize(2);
    }
    char fitted[256];snprintf(fitted,sizeof(fitted),"%s",text);
    if(tft.textWidth(text)>w) {
      size_t n=strlen(fitted);
      do {
        if(!n)break;
        do{--n;}while(n&&(uint8_t(fitted[n])&0xc0)==0x80);
        fitted[n]=0;
      }while(tft.textWidth((String(fitted)+"...").c_str())>w);
      strncat(fitted,"...",sizeof(fitted)-strlen(fitted)-1);
      tft.drawString(fitted,x,y);
    } else tft.drawString(text,x,y);
  }
  tft.clearClipRect(); tft.unloadFont();
}
// The native dashboard follows the approved 800x480 composition. Keep this
// typography separate from menus so their established layout is unaffected.
uint16_t v2Ink() { return BG==ws43b_style::background&&(INK==CLR_TEXT_DEFAULT||INK==ws43b_style::ink)?ws43b_native::ink:INK; }
uint16_t v2Dim() { return BG==ws43b_style::background&&(DIM==CLR_TEXT_DIM_DEFAULT||DIM==0x9D34||DIM==ws43b_style::dim)?ws43b_native::dim:DIM; }
uint16_t v2Accent() { return BG==ws43b_style::background&&ACCENT==ws43b_style::mint?ws43b_native::rgb(128,229,155):ACCENT; }
using UiAsset=ws43b_assets::Asset;
void panelIcon(UiAsset asset,int cx,int cy,uint16_t background,int extent=33,
               bool tint=false,uint16_t color=0) {
  ws43b_ui_icons::flat(tft,asset,cx,cy,extent,background,tint,color);
}
void v2Clear(int x,int y,int w,int h) {
  ws43b_native::gradientRect(tft,x,y,w,h,[=](int px,int py){return ws43b_native::textbg(px,py,BG);});
}
int v2Text(const char *text,int x,int y,int w,const uint8_t *font,int height,
           uint16_t color,bool right=false,bool fit=true) {
  // Alignment must use the same space advance as the VLW rasterizer.
  if(!text || !*text)return 0;
  ::setFont(tft,FONT_NONE);tft.loadFont(font);tft.setTextSize(1);
  tft.setTextColor(color);tft.setTextDatum(TL_DATUM);
  const auto word=[&](size_t at)->uint32_t {
    return (uint32_t(pgm_read_byte(font+at))<<24)|(uint32_t(pgm_read_byte(font+at+1))<<16)|
      (uint32_t(pgm_read_byte(font+at+2))<<8)|pgm_read_byte(font+at+3);
  };
  const unsigned line=word(16)+word(20),nominal=word(8);
  const int actualSpace=int((line>nominal?line:nominal)*2/7);
  int spaceDelta=0;
  for(unsigned i=0;i<word(0);++i)if(word(24+i*28)==32) {
    spaceDelta=actualSpace-int(word(36+i*28));break;
  }
  const auto measured=[&](const char *value) {
    int width=tft.textWidth(value);
    for(const char *c=value;*c;++c)if(*c==' ')width+=spaceDelta;
    return width;
  };
  char fitted[256];snprintf(fitted,sizeof(fitted),"%s",text);
  if(fit && measured(fitted)>w) {
    size_t n=strlen(fitted);
    do {
      if(!n)break;
      do {--n;} while(n&&(uint8_t(fitted[n])&0xc0)==0x80);
      fitted[n]=0;
    } while(measured((String(fitted)+"...").c_str())>w);
    strncat(fitted,"...",sizeof(fitted)-strlen(fitted)-1);
  }
  const int width=measured(fitted);
  // VLW ascent plus Polish descenders can exceed the nominal pixel size.
  // Keep the final alpha rows of e.g. POSTĘP while retaining the horizontal clip.
  tft.setClipRect(x,y,w,height+8);
  tft.drawString(fitted,right?x+w-width:x,y);
  tft.clearClipRect();tft.unloadFont();return width;
}
void footer(const BambuMonitorTelemetry &, uint32_t now) {
  if(!navigationShown(now)) {
    tft.fillRoundRect(375,456,50,4,2,DIM); return;
  }
  const uint16_t bg=BG==ws43b_style::background?ws43b_native::rgb(11,24,35):BG;
  const uint16_t activeBg=BG==ws43b_style::background&&ACCENT==ws43b_style::mint?ws43b_native::rgb(31,57,49):ws43b_native::mix(bg,ACCENT,35);
  tft.fillRect(0,435,800,45,bg);tft.drawFastHLine(0,435,800,ws43b_native::line);
  const Page pages[]={Page::Dashboard,Page::Ams,Page::Details,Page::Settings};
  const char *names[]={ws43bText("Wydruk","Print"),"AMS",ws43bText("Szczegóły","Details"),ws43bText("Ustawienia","Settings")};
  const ws43b_assets::Asset icons[]={ws43b_assets::Asset::Print,ws43b_assets::Asset::AMS,ws43b_assets::Asset::Details,ws43b_assets::Asset::Settings};
  for(int i=0;i<4;++i) {
    const bool active=page==pages[i] || (i==3 && (page==Page::Appearance || page==Page::GeneralSettings || page==Page::ClockSettings || page==Page::WeatherSettings || page==Page::WebQr || page==Page::System || page==Page::FactoryReset)) || (i==2 && page==Page::Gauges);
    const int x=16+i*194;
    if(active) {
      tft.fillRoundRect(x,440,184,36,9,activeBg);
      tft.drawRoundRect(x,440,184,36,9,ws43b_native::mix(activeBg,v2Accent(),85));
    }
    ::setFont(tft,FONT_NONE);tft.loadFont(ws43b_v2_b15);
    const int textWidth=tft.textWidth(names[i]);tft.unloadFont();
    const int left=x+(184-33-10-textWidth)/2;
    ws43b_native::sprite(tft,icons[i],left,441,[=](int,int){return active?activeBg:bg;});
    v2Text(names[i],left+43,450,textWidth+2,ws43b_v2_b15,15,active?v2Ink():v2Dim());
  }
}
void applyWs43bPalette() {
#if WS43B_FULL_WEBUI
  INK = dispSettings.textColor;
  DIM = dispSettings.textDimColor;
  GREEN = dispSettings.statusOkColor;
#endif
  BG = dispSettings.bgColor;
  TRACK = dispSettings.trackColor;
  ACCENT = dispSettings.progressBarColor;
  // Migrate only an exact old preset at render time; never overwrite custom NVS colors.
  if((BG==0x0843&&TRACK==0x2948)||(BG==0x0841&&TRACK==0x2104)) {
    BG=ws43b_style::background;TRACK=ws43b_style::border;
    if(ACCENT==0x4EFD)ACCENT=ws43b_style::mint;
  }
}
void startupText(const char *text,int x,int y,int w,int size,uint16_t color) {
  const uint8_t *font=size==25?ws43b_v2_b25:size==17?ws43b_v2_b17:ws43b_v2_b14;
  v2Text(text,x,y,w,font,size,color);
}
bool startupVisible=false;
uint32_t startupLastAnimation=0;
ws43b_boot::Palette startupPalette() {return {BG,v2Accent(),v2Ink(),v2Dim()};}
void startupScreen(ws43b_boot::Phase phase,const char *context,uint32_t now) {
  ws43b_boot::draw(tft,startupText,phase,startupPalette(),ws43bPolish(),context,now);
  startupVisible=true;startupLastAnimation=now;
}
void animateStartupScreen(uint32_t now) {
  if(!startupVisible || uint32_t(now-startupLastAnimation)<80u)return;
  tft.startWrite();ws43b::beginRenderDiagnostics(false);
  ws43b_boot::animate(tft,now,startupPalette());
  tft.endWrite();ws43b::endRenderDiagnostics(true);
  startupLastAnimation=now;
}
template <class Field>
const char *missing(const Field &f, bool online, uint32_t now) {
  if (!f.valid) return ws43bText("Brak danych", "No data");
  if (!online || !f.current(now)) return ws43bText("Nieaktualne", "Outdated");
  return nullptr;
}
template <class Field>
void number(char *out, size_t cap, const Field &f, bool online,
            uint32_t now, const char *suffix) {
  if (const char *why = missing(f, online, now)) snprintf(out, cap, "%s", why);
  else snprintf(out, cap, "%u%s", unsigned(f.value), suffix);
}
void temperature(int y, const char *title, const MonitorField<float> &actual,
                 const MonitorField<float> &target, bool online, uint32_t now) {
  using namespace ws43b_layout;
  tft.fillRoundRect(tempX, y, tempW, tempH, 12, CARD);
  small(title, tempX + 18, y + 10, 110);
  char buf[40];
  const char *why = missing(actual, online, now);
  if (why) snprintf(buf, sizeof(buf), "%s", why);
  else snprintf(buf, sizeof(buf), "%.0f C", double(actual.value));
  label(buf, tempX + 18, y + 37, 140, 38,
        why ? &fonts::FreeSans9pt7b : &fonts::FreeSansBold18pt7b, why ? DIM : INK);
  const char *targetMissing = missing(target, online, now);
  if (targetMissing) snprintf(buf, sizeof(buf), ws43bText("Cel: %s", "Target: %s"), target.valid ? ws43bText("stare", "stale") : ws43bText("brak", "none"));
  else snprintf(buf, sizeof(buf), ws43bText("Cel: %.0f C", "Target: %.0f C"), double(target.value));
  small(buf, tempX + 154, y + 48, 94);
}
const char *statusText(const MonitorText<16> &f, bool online, uint32_t now) {
  if (const char *why = missing(f, online, now)) return why;
  if (!strcmp(f.value, "RUNNING")) return ws43bText("Drukowanie", "Printing");
  if (!strcmp(f.value, "PAUSE")) return ws43bText("Pauza", "Paused");
  if (!strcmp(f.value, "PREPARE")) return ws43bText("Przygotowanie", "Preparing");
  if (!strcmp(f.value, "FINISH")) return ws43bText("Wydruk zakończony", "Print finished");
  if (!strcmp(f.value, "FAILED")) return ws43bText("Błąd wydruku", "Print failed");
  if (!strcmp(f.value, "IDLE")) return ws43bText("Gotowa", "Ready");
  return ws43bText("Inny stan", "Other state");
}
void detailCard(const char *title, const char *value, int x, int y, int w, uint16_t valueColor=INK) {
  tft.fillRoundRect(x,y,w,96,12,CARD);
  dashText(title,x+16,y+12,w-32,14,DIM);
  tft.loadFont(ws43b_dash_30);
  const int size=tft.textWidth(value)<=w-32?30:18;
  tft.unloadFont();
  dashText(value,x+16,y+39,w-32,size,valueColor);
}

void levelCard(int x,int y,int w,int h,int level,bool known,bool active) {
  tft.fillRoundRect(x,y,w,h,14,CARD);
  if(active)tft.drawRoundRect(x,y,w,h,14,ACCENT);
}
const MonitorAmsUnit *amsUnit(const BambuMonitorTelemetry &m,bool details) {
  for(unsigned step=0;step<6;++step) {
    const unsigned index=details?(selectedAms+step)%6:step;
    const auto &u=m.amsUnits[index];
    if(u.used && !(u.present.valid&&!u.present.value)) { if(details)selectedAms=index; return &u; }
  }
  return nullptr;
}
bool amsDryingAnimated(const BambuMonitorTelemetry &m,bool online,uint32_t now) {
  const auto *unit=amsUnit(m,true);
  return unit && !(unit->present.valid&&!unit->present.value) && online && m.hasUsefulData &&
    uint32_t(now-m.lastUsefulMs)<=BAMBU_MONITOR_FRESH_MS &&
    unit->dryRemainMin.current(now) && unit->dryRemainMin.value>0;
}
void amsDryingAnimation(uint32_t now) {
  // Same scene as the saver; only this small region changes between telemetry frames.
  tft.setClipRect(668,138,96,94);tft.fillRect(668,138,96,94,CARD);
  ws43b_drying_scene::draw(tft,718,184,42,now,ACCENT,TRACK,INK,CARD);
  tft.clearClipRect();
}
template<class Field>
void amsReadingAge(char *out,size_t cap,const Field &field,bool online,uint32_t now) {
  out[0]=0;
  if(!field.valid)return;
  const uint32_t seconds=uint32_t(now-field.updatedMs)/1000u;
  if(online && field.current(now))return;
  if(seconds<60)snprintf(out,cap,ws43bText("%lu s temu","%lu s ago"),(unsigned long)seconds);
  else if(seconds<3600)snprintf(out,cap,ws43bText("%lu min temu","%lu min ago"),(unsigned long)(seconds/60));
  else snprintf(out,cap,ws43bText("%lu h temu","%lu h ago"),(unsigned long)(seconds/3600));
  if(!online) {
    const size_t used=strlen(out);
    snprintf(out+used,cap-used," · offline");
  }
}
// Keep actual observation ages for expired/offline values. Related deltas may
// retain a known value without rewriting its observation timestamp.
void jobLayerText(char *out,size_t cap,const BambuMonitorTelemetry &m,bool online,uint32_t now) {
  char layer[24],total[24],age[64];
  if(m.layerNum.valid)snprintf(layer,sizeof(layer),"%u",unsigned(m.layerNum.value));else snprintf(layer,sizeof(layer),"--");
  if(m.totalLayers.valid)snprintf(total,sizeof(total),"%u",unsigned(m.totalLayers.value));else snprintf(total,sizeof(total),"--");
  amsReadingAge(age,sizeof(age),m.totalLayers,online,now);
  if(m.layerNum.valid && (!online || !m.layerNum.current(now)))
    snprintf(out,cap,ws43bText("%s / %s · ostatnie odczyty","%s / %s · last readings"),layer,total);
  else if(age[0])snprintf(out,cap,ws43bText("%s / %s · razem: %s","%s / %s · total: %s"),layer,total,age);
  else snprintf(out,cap,"%s / %s",layer,total);
}
void amsView(const BambuMonitorTelemetry &m,bool online,uint32_t now,bool details=false,
             ws43b_repaint::Mask regions=ws43b_repaint::All) {
  using R=ws43b_repaint::Region;
  const bool summary=regions&ws43b_repaint::regionBit(R::AmsSummary);
  constexpr auto slots=ws43b_repaint::regionBit(R::Ams0)|ws43b_repaint::regionBit(R::Ams1)|
    ws43b_repaint::regionBit(R::Ams2)|ws43b_repaint::regionBit(R::Ams3);
  if(!(regions&(slots|ws43b_repaint::regionBit(R::AmsSummary))))return;
  const auto *unit=amsUnit(m,details);
  const int heading=details?92:284, row=details?250:312;
  // Clear each changed region before drawing shorter labels or removed data.
  // The gaps between cards also need clearing on AMS/unit presence transitions.
  if(summary)tft.fillRect(24,details?84:280,752,details?156:32,BG);
  if((regions&slots)==slots || !unit)tft.fillRect(24,row,752,details?174:92,BG);
  // Text and color describe the last known slot in this MQTT session. They
  // change only on explicit updates; newSession() clears all cached fields.
  const bool linkCurrent=online && m.hasUsefulData && uint32_t(now-m.lastUsefulMs)<=BAMBU_MONITOR_FRESH_MS;
  char buf[180];
  if(details && unit)snprintf(buf,sizeof(buf),"AMS · ID %u%s",unsigned(unit->id),linkCurrent?"":ws43bText(" · nieaktualne"," · outdated"));
  else snprintf(buf,sizeof(buf),"AMS%s",linkCurrent?"":ws43bText(" · nieaktualne"," · outdated"));
  if(summary)dashText(buf,24,heading,details?510:360,18,linkCurrent?INK:WARN);
  if(summary && details)button(ws43bText("Kolejny AMS >","Next AMS >"),550,86,226,38,false);
  if(!unit) { dashText(ws43bText("Brak danych AMS","No AMS data"),24,row,700,18,DIM); return; }
  char temp[32],humidity[32],dry[32],ages[3][64];
  if(unit->temp.valid)snprintf(temp,sizeof(temp),"%.0f°C",double(unit->temp.value));
  else snprintf(temp,sizeof(temp),"%s",ws43bText("Brak danych","No data"));
  amsReadingAge(ages[0],sizeof(ages[0]),unit->temp,linkCurrent,now);
  // Prefer a current sensor; otherwise keep the most recent known measurement.
  const bool raw=ws43b_live::amsHumidityUsesRaw(*unit,now);
  const auto &hum=raw?unit->humidityRaw:unit->humidity;
  if(hum.valid)snprintf(humidity,sizeof(humidity),raw?"%u%% RH":"%u/5",unsigned(hum.value));
  else snprintf(humidity,sizeof(humidity),"%s",ws43bText("Brak danych","No data"));
  amsReadingAge(ages[1],sizeof(ages[1]),hum,linkCurrent,now);
  if(unit->dryRemainMin.valid && unit->dryRemainMin.value==0)snprintf(dry,sizeof(dry),"%s",ws43bText("Wyłączone","Off"));
  else if(unit->dryRemainMin.valid)snprintf(dry,sizeof(dry),"%u h %02u min",unsigned(unit->dryRemainMin.value/60),unsigned(unit->dryRemainMin.value%60));
  else snprintf(dry,sizeof(dry),"%s",ws43bText("Brak danych","No data"));
  amsReadingAge(ages[2],sizeof(ages[2]),unit->dryRemainMin,linkCurrent,now);
  if(summary && details) {
    const char *titles[]={ws43bText("TEMPERATURA","TEMPERATURE"),ws43bText("WILGOTNOŚĆ","HUMIDITY")};
    const char *values[]={temp,humidity};
    for(int i=0;i<2;++i) {
      const int x=24+190*i;
      tft.fillRoundRect(x,126,182,112,12,CARD);
      tft.drawRoundRect(x,126,182,112,12,TRACK);
      dashText(titles[i],x+14,138,154,14,DIM);
      dashText(values[i],x+14,166,154,24,ages[i][0]?DIM:INK);
      if(ages[i][0])dashText(ages[i],x+14,208,154,14,WARN);
    }
    const bool drying=amsDryingAnimated(m,online,now);
    tft.fillRoundRect(404,126,372,112,12,CARD);
    tft.drawRoundRect(404,126,372,112,12,drying?ACCENT:TRACK);
    dashText(ws43bText("SUSZENIE","DRYING"),420,138,238,14,drying?ACCENT:DIM);
    dashText(dry,420,166,238,24,ages[2][0]?DIM:INK);
    dashText(ages[2][0]?ages[2]:drying?ws43bText("Pozostały czas","Time remaining"):
      unit->dryRemainMin.valid?ws43bText("Suszenie nieaktywne","Drying inactive"):ws43bText("Oczekiwanie na dane","Waiting for data"),
      420,208,238,14,ages[2][0]?WARN:DIM);
    if(drying)amsDryingAnimation(now);
    else panelIcon(UiAsset::Spool,718,184,CARD,58,true,DIM);
  } else if(summary) {
    snprintf(buf,sizeof(buf),"%s%s%s%s · %s%s%s%s",temp,ages[0][0]?" (":"",ages[0],ages[0][0]?")":"",
      humidity,ages[1][0]?" (":"",ages[1],ages[1][0]?")":"");
    dashText(buf,385,heading+2,391,14,DIM);
  }
  for(int i=0;i<4;++i) {
    if(!(regions&ws43b_repaint::regionBit(static_cast<R>(unsigned(R::Ams0)+i))))continue;
    const auto &tray=unit->trays[i];const int x=24+i*190;
    const bool empty=tray.present.valid&&!tray.present.value;
    const bool active=!empty&&linkCurrent&&m.activeTrayRaw.current(now)&&unit->id<63&&m.activeTrayRaw.value==unit->id*4+i;
    const bool known=!empty&&tray.remain.valid&&tray.remain.value>=0;
    const bool recent=known&&linkCurrent&&tray.remain.current(now);
    const bool identified=!empty&&tray.type.valid;
    const uint16_t filament=identified&&tray.colorRgb565.valid?tray.colorRgb565.value:DIM;
    const int height=details?174:92;
    tft.fillRoundRect(x,row,182,height,12,CARD);
    tft.drawRoundRect(x,row,182,height,12,active?ACCENT:TRACK);
    const char *type=empty?ws43bText("Pusty","Empty"):identified?tray.type.value:ws43bText("Brak danych","No data");
    char age[64];amsReadingAge(age,sizeof(age),tray.remain,linkCurrent,now);
    if(empty || (!identified && !known)) {
      snprintf(buf,sizeof(buf),"SLOT %d",i+1);
      dashText(buf,x+12,row+7,158,14,DIM);
      // Unknown telemetry is not evidence of an empty spool.
      const int iconX=x+91,iconY=row+(details?85:40);
      panelIcon(empty?UiAsset::EmptySlot:UiAsset::UnknownData,iconX,iconY,CARD,details?48:33);
      dashText(empty?ws43bText("Pusty slot","Empty slot"):ws43bText("Brak odczytu","No reading"),
               x+12,row+(details?126:60),158,details?18:14,DIM);
      continue;
    }

    if(details) {
      snprintf(buf,sizeof(buf),"SLOT %d",i+1);dashText(buf,x+12,row+7,158,14,DIM);
      dashText(type,x+12,row+27,158,18,linkCurrent?INK:DIM);
      // Keep the spool below the complete 18px font line (including descent).
      panelIcon(UiAsset::Spool,x+91,row+81,CARD,64,true,filament);
      if(known)snprintf(buf,sizeof(buf),"%u%%",unsigned(tray.remain.value));else snprintf(buf,sizeof(buf),"--");
      dashText(buf,x+12,row+110,158,30,recent?INK:DIM);
      if(known&&age[0])dashText(age,x+12,row+145,158,14,WARN);
      else dashText(active?ws43bText("W użyciu","In use"):known?ws43bText("Pozostało","Remaining"):empty?ws43bText("Pusty slot","Empty slot"):ws43bText("Ilość nieznana","Amount unknown"),x+12,row+145,158,14,active?ACCENT:DIM);
    } else {
      panelIcon(UiAsset::Spool,x+38,row+44,CARD,69,true,filament);
      snprintf(buf,sizeof(buf),"%d %s",i+1,type);dashText(buf,x+76,row+8,98,14,linkCurrent?INK:DIM);
      if(known)snprintf(buf,sizeof(buf),"%u%%",unsigned(tray.remain.value));else snprintf(buf,sizeof(buf),"--");
      dashText(buf,x+76,row+32,98,24,recent?INK:DIM);
      if(known&&age[0])dashText(age,x+76,row+60,98,14,WARN);
      else if(active)dashText(ws43bText("W użyciu","In use"),x+76,row+60,98,14,ACCENT);
    }
    const int barY=row+height-9;
    if(recent) {
      tft.fillRoundRect(x+12,barY,158,5,2,TRACK);
      const int amount=tray.remain.value>100?100:tray.remain.value;
      if(amount>0)tft.fillRoundRect(x+12,barY,158*amount/100,5,2,ACCENT);
    }
  }

}
void dashboardTemperature(int channel,int y,const char *name,const MonitorField<float> &actual,
                          const MonitorField<float> &target,bool online,uint32_t now) {
  static ws43b_view::ThermalPolicy policies[MAX_ACTIVE_PRINTERS][3];
  auto &policy=policies[rotState.displayIndex][channel];
  const bool fresh=!missing(actual,online,now),targetFresh=!missing(target,online,now);
  const auto state=policy.update(now,fresh,actual.value,targetFresh,target.value);
  const bool changing=state==ws43b_view::Thermal::Heating||state==ws43b_view::Thermal::Cooling;
  const uint16_t color=state==ws43b_view::Thermal::Heating?WARN:state==ws43b_view::Thermal::Cooling?0x5EDE:v2Dim();
  v2Clear(528,y,256,74);ws43b_native::card(tft,528,y,256,74,BG);
  const ws43b_assets::Asset assets[]={ws43b_assets::Asset::Nozzle,ws43b_assets::Asset::Bed,ws43b_assets::Asset::Chamber};
  ws43b_native::sprite(tft,assets[channel],537,y+13,[=](int px,int py){return ws43b_native::cardbg(px,py,y,74,BG);});
  v2Text(name,585,y+16,70,ws43b_v2_12,12,v2Dim());
  char buf[160],age[64],targetAge[64];
  if(actual.valid)snprintf(buf,sizeof(buf),"%.0f°C",double(actual.value));
  else snprintf(buf,sizeof(buf),"--");
  v2Text(buf,649,y+12,121,ws43b_v2_b29,29,fresh?v2Ink():v2Dim(),true,false);
  const char *status=!fresh?missing(actual,online,now):changing?
    (state==ws43b_view::Thermal::Heating?ws43bText("Nagrzewanie","Heating"):ws43bText("Stygnięcie","Cooling")):
    state==ws43b_view::Thermal::Unknown?ws43bText("Pomiar","Measuring"):
    !targetFresh?ws43bText("Odczyt","Reading"):ws43bText("Stabilna","Stable");
  amsReadingAge(age,sizeof(age),actual,online,now);
  amsReadingAge(targetAge,sizeof(targetAge),target,online,now);
  if(channel!=2 && target.valid && age[0])snprintf(buf,sizeof(buf),ws43bText("%s · cel %.0f°%s","%s · target %.0f°%s"),age,double(target.value),targetAge[0]?ws43bText(" stary"," stale"):"");
  else if(age[0])snprintf(buf,sizeof(buf),"%s",age);
  else if(channel!=2 && target.valid && targetAge[0])snprintf(buf,sizeof(buf),ws43bText("Cel %.0f° · nieaktualny","Target %.0f° · outdated"),double(target.value));
  else if(channel==2)snprintf(buf,sizeof(buf),"%s",fresh?ws43bText("Temperatura komory","Chamber temperature"):status);
  else if(target.valid)snprintf(buf,sizeof(buf),ws43bText("Cel %.0f° · %s","Target %.0f° · %s"),double(target.value),status);
  else snprintf(buf,sizeof(buf),ws43bText("Cel -- · %s","Target -- · %s"),status);
  v2Text(buf,585,y+47,185,ws43b_v2_12,12,age[0]||targetAge[0]?WARN:changing?color:v2Dim());
}
// Solar data selects the visual day/night palette. If unavailable, use the
// existing configured night schedule; this is a UI fallback, not an astronomy claim.
bool dashboardWeatherNight(const ws43b_weather::Data &weather) {
  const time_t now=time(nullptr);
  struct tm local{};
  if(localtime_r(&now,&local) && local.tm_year>=120) {
    local.tm_hour=local.tm_min=local.tm_sec=0;local.tm_isdst=-1;
    const time_t start=mktime(&local);
    ++local.tm_mday;local.tm_isdst=-1;
    const time_t end=mktime(&local);
    bool night=false;
    if(ws43b_weather::solarNight(weather,now,start,end,night))return night;
  }
#if WS43B_FULL_WEBUI
  return isNightModeActive();
#else
  return false;
#endif
}
bool weatherHeaderVisible=false;
void dashboardWeatherIcon(uint32_t now) {
  // The animation only restores its own patch, never the card below the header.
  const bool native=page==Page::Dashboard;
  const int x=native?606:525,y=native?11:16;
  tft.setClipRect(x,y,36,36);
  if(native)v2Clear(x,y,36,36);else tft.fillRect(x,y,36,36,BG);
  const auto weather=ws43bWeatherData();
  weatherHeaderVisible=ws43bWeatherConfig().enabled && ws43b_weather::fresh(weather,time(nullptr));
  if(weatherHeaderVisible)
    ws43b_weather_icon::draw(tft,ws43b_weather_icon::classify(true,weather.code),x+18,y+18,1,
      dashboardWeatherNight(weather),native?v2Ink():INK,WARN,0x5EDE,now);
  tft.clearClipRect();
}
void menuWeatherHeader(uint32_t now) {
  if(!ws43bWeatherConfig().enabled) { weatherHeaderVisible=false;return; }
  const auto weather=ws43bWeatherData();
  const bool fresh=ws43b_weather::fresh(weather,time(nullptr));
  dashboardWeatherIcon(now);
  char value[40];
  if(fresh)snprintf(value,sizeof(value),"%.0f°C",double(weather.temperature));
  else snprintf(value,sizeof(value),"--°C");
  if(page==Page::Dashboard) {
    ::setFont(tft,FONT_NONE);tft.loadFont(ws43b_v2_b17);
    const bool compact=tft.textWidth(value)>48;tft.unloadFont();
    v2Text(value,646,compact?24:22,48,compact?ws43b_v2_b14:ws43b_v2_b17,compact?14:17,fresh?v2Ink():v2Dim(),true,false);
  }
  else dashText(value,563,24,94,24,fresh?INK:DIM);
}
bool dashboardCooling=false, dashboardCoolingPainted=false;
ws43b_view::ActivityClock dashboardActivity;
int dashboardProgressEdge=24;
uint16_t saverFilamentColor(const BambuMonitorTelemetry &,bool,uint32_t);
void dashboardActivityIcon(uint32_t now,bool force=false) {
  using ws43b_view::Activity;
  const Activity state=dashboardActivity.state;
  const uint32_t elapsed=dashboardActivity.elapsed(now);
  const float phase=float(elapsed%3000u)*0.0020943951f;
  const uint16_t color=state==Activity::Error?RED:state==Activity::Heating?WARN:v2Accent();
  const auto &slot=displayedPrinter();
  const bool online=isWiFiConnected()&&slot.state.connected;
  const auto &m=slot.state.monitor;
  const uint16_t filament=saverFilamentColor(m,online,now);
  const unsigned percent=ws43b_view::dashboardProgressVisible(m,online,now,ws43bAdvancedDisplay())?m.progress.value:0;
  if(state==Activity::Printing && ws43b_native::hero(tft,228,74,percent,filament,BG,elapsed,force))return;
  tft.setClipRect(228,74,270,170);
  ws43b_native::gradientRect(tft,228,74,270,170,[=](int px,int py){return ws43b_native::cardbg(px,py,66,242,BG);});
  const int x=307,y=107,cx=363,cy=160;
  const auto icon=[&](UiAsset asset,int size=48,bool tint=false,uint16_t ink=0) {
    ws43b_ui_icons::draw(tft,asset,cx,cy,size,
      [=](int px,int py){return ws43b_native::cardbg(px,py,66,242,BG);},tint,ink);
  };
  switch(state) {
    case Activity::Printing:
      ws43b_print_scene::draw(tft,x,y,percent,elapsed,filament,BG,false,true);break;
    case Activity::CalibrationLines:
      ws43b_print_scene::calibrationLines(tft,x,y,elapsed,filament,BG,true);break;
    case Activity::Leveling:ws43b_print_scene::leveling(tft,x,y,elapsed,v2Accent(),BG,true);break;
    case Activity::Cleaning:ws43b_print_scene::cleaning(tft,x,y,elapsed,BG,true);break;
    case Activity::Preparing:
      tft.drawCircle(cx,cy,28,TRACK);
      tft.fillCircle(cx+int(cosf(phase)*28),cy+int(sinf(phase)*28),4,color);break;
    case Activity::Heating:
      icon(UiAsset::Bed,52);
      for(int i=0;i<3;++i)tft.fillCircle(cx-16+i*16,cy-27-int((elapsed/120)%12),2,color);break;
    case Activity::Change:case Activity::Load:case Activity::Unload:
      icon(UiAsset::Spool,64,true,filament);
      tft.drawFastHLine(cx-32,cy+36,60,color);
      tft.fillCircle(cx-32+int((state==Activity::Unload?3000-elapsed%3000:elapsed%3000)/50),cy+36,3,v2Ink());break;
    case Activity::Pause:icon(UiAsset::Pause,48,true,WARN);break;
    case Activity::Finished:icon(UiAsset::Check,48,true,v2Accent());break;
    case Activity::Idle:icon(UiAsset::Printer,56);break;
    case Activity::Error:icon(UiAsset::Alert,48,true,RED);break;
    case Activity::Offline:
      icon(UiAsset::Network);
      tft.drawLine(cx-24,cy+24,cx+24,cy-24,v2Dim());break;
    default:icon(UiAsset::UnknownData);break;
  }
  tft.clearClipRect();
}
void dashboardCoolingCard(const BambuMonitorTelemetry &m,uint32_t now,bool partial) {
  if(!partial) {
    tft.fillRoundRect(24,84,460,193,14,CARD);
    tft.drawRoundRect(24,84,460,193,14,ACCENT);
    dashText(ws43bText("Chłodzenie stołu","Bed cooling"),40,101,420,18,ACCENT);
    char temp[32];snprintf(temp,sizeof(temp),"%.0f°C",double(m.bedTemp.value));
    dashText(temp,244,142,216,30,INK);
    dashText(ws43bText("Grzanie wyłączone","Heater off"),244,184,216,14,DIM);
  }
  // The only animated area: no repaint of AMS, text or weather background.
  tft.setClipRect(40,128,178,90);tft.fillRect(40,128,178,90,CARD);
  panelIcon(UiAsset::Fan,84,170,CARD,64);
  for(int i=0;i<3;++i) {
    const int x=126+int((now/35+i*7)%28),y=149+i*19;
    tft.drawFastHLine(x,y,28,ACCENT);tft.fillCircle(x+34,y-2,2,DIM);
  }
  tft.fillRoundRect(126,209,86,5,2,TRACK);
  tft.clearClipRect();
}
uint16_t dashboardSlotBg(int x,int y,bool active) {
  const unsigned weight=active?(y<345?24:unsigned(24-(y>424?79:y-345)*12/79)):0;
  return ws43b_native::cardbg(x,y,345,80,BG,v2Accent(),weight);
}
void dashboardSlotCard(int x,bool active) {
  v2Clear(x,345,184,80);
  for(int row=0;row<80;++row) {
    const int d=row<10?9-row:row>=70?row-70:0;
    const int inset=d>0?10-int(sqrtf(float(100-d*d))):0;
    ws43b_native::gradientRect(tft,x+inset,345+row,184-2*inset,1,
      [=](int px,int py){return dashboardSlotBg(px,py,active);});
  }
  tft.drawRoundRect(x,345,184,80,10,active?v2Accent():ws43b_native::line);
}
void dashboardAms(const BambuMonitorTelemetry &m,bool online,uint32_t now,ws43b_repaint::Mask regions) {
  using R=ws43b_repaint::Region;
  const auto *unit=amsUnit(m,false);
  const bool linkCurrent=online&&m.hasUsefulData&&uint32_t(now-m.lastUsefulMs)<=BAMBU_MONITOR_FRESH_MS;
  if(regions&ws43b_repaint::regionBit(R::AmsSummary)) {
    v2Clear(16,314,768,27);
    v2Text(linkCurrent?"AMS":ws43bText("AMS · nieaktualne","AMS · outdated"),20,320,190,ws43b_v2_b16,16,linkCurrent?v2Ink():WARN);
    char temp[24],humidity[24],ages[2][64],buf[200];
    if(unit) {
      if(unit->temp.valid)snprintf(temp,sizeof(temp),"%.0f°C",double(unit->temp.value));else snprintf(temp,sizeof(temp),"--°C");
      const bool raw=ws43b_live::amsHumidityUsesRaw(*unit,now);
      const auto &hum=raw?unit->humidityRaw:unit->humidity;
      if(hum.valid)snprintf(humidity,sizeof(humidity),raw?"%u%% RH":"%u/5",unsigned(hum.value));else snprintf(humidity,sizeof(humidity),"--%% RH");
      amsReadingAge(ages[0],sizeof(ages[0]),unit->temp,linkCurrent,now);
      amsReadingAge(ages[1],sizeof(ages[1]),hum,linkCurrent,now);
      if(ages[0][0]&&ages[1][0]&&!strcmp(ages[0],ages[1]))snprintf(buf,sizeof(buf),"%s · %s · %s",temp,humidity,ages[0]);
      else snprintf(buf,sizeof(buf),"%s%s%s%s · %s%s%s%s",temp,ages[0][0]?" (":"",ages[0],ages[0][0]?")":"",humidity,ages[1][0]?" (":"",ages[1],ages[1][0]?")":"");
    } else snprintf(buf,sizeof(buf),"%s",ws43bText("Oczekiwanie na dane AMS","Waiting for AMS data"));
    v2Text(buf,212,323,568,ws43b_v2_12,12,v2Dim(),true);
  }
  for(int i=0;i<4;++i) {
    if(!(regions&ws43b_repaint::regionBit(static_cast<R>(unsigned(R::Ams0)+i))))continue;
    const int x=16+194*i;
    const auto *tray=unit?&unit->trays[i]:nullptr;
    const bool empty=tray&&tray->present.valid&&!tray->present.value;
    const bool identified=tray&&!empty&&tray->type.valid;
    const bool known=tray&&!empty&&tray->remain.valid&&tray->remain.value>=0;
    const bool recent=known&&linkCurrent&&tray->remain.current(now);
    const bool active=tray&&!empty&&linkCurrent&&m.activeTrayRaw.current(now)&&unit->id<63&&m.activeTrayRaw.value==unit->id*4+i;
    dashboardSlotCard(x,active);
    char buf[80];
    if(empty || (!identified&&!known)) {
      ws43b_ui_icons::draw(tft,empty?UiAsset::EmptySlot:UiAsset::UnknownData,x+36,385,40,
        [=](int px,int py){return dashboardSlotBg(px,py,active);});
      snprintf(buf,sizeof(buf),"SLOT %d",i+1);
      v2Text(buf,x+73,356,103,ws43b_v2_b14,14,v2Dim());
      v2Text(empty?ws43bText("Pusty","Empty"):ws43bText("Brak odczytu","No reading"),x+73,383,103,ws43b_v2_b14,14,v2Dim());
      continue;
    }
    const uint16_t filament=identified&&tray->colorRgb565.valid?tray->colorRgb565.value:v2Dim();
    ws43b_native::sprite(tft,ws43b_assets::Asset::Spool,x+3,350,[=](int px,int py){return dashboardSlotBg(px,py,active);},true,filament);
    snprintf(buf,sizeof(buf),"%d %s",i+1,identified?tray->type.value:ws43bText("Materiał","Material"));
    v2Text(buf,x+73,356,103,ws43b_v2_b14,14,linkCurrent?v2Ink():v2Dim());
    if(known)snprintf(buf,sizeof(buf),"%u%%",unsigned(tray->remain.value));else snprintf(buf,sizeof(buf),"--");
    v2Text(buf,x+73,377,103,ws43b_v2_b23,23,recent?v2Ink():v2Dim(),false,false);
    char age[64];amsReadingAge(age,sizeof(age),tray->remain,linkCurrent,now);
    if(known&&age[0])v2Text(age,x+74,405,102,ws43b_v2_12,12,WARN);
    else if(active)v2Text(ws43bText("W użyciu","In use"),x+74,405,102,ws43b_v2_12,12,v2Accent());
    else if(recent) {
      tft.fillRoundRect(x+74,407,97,4,2,ws43b_native::rgb(52,73,89));
      const unsigned amount=tray->remain.value>100?100:unsigned(tray->remain.value);
      if(amount)tft.fillRoundRect(x+74,407,97*amount/100,4,2,filament);
    }
  }
}
void dashboardMaterialLine(char *out,size_t cap,const BambuMonitorTelemetry &m,bool online,uint32_t now) {
  const MonitorAmsUnit *unit=nullptr;const MonitorAmsTray *tray=nullptr;
  if(m.activeTrayRaw.valid&&m.activeTrayRaw.value<252)for(const auto &u:m.amsUnits) {
    if(!u.used||u.id>=63||u.id!=m.activeTrayRaw.value/4||(u.present.valid&&!u.present.value))continue;
    const auto &candidate=u.trays[m.activeTrayRaw.value%4];
    if(candidate.present.valid&&!candidate.present.value)break;
    unit=&u;tray=&candidate;break;
  }
  // Field-specific warnings stay visible even when the compact layer caption
  // fits beside the job name; cached metadata never becomes a live reading.
  const bool nameOld=m.subtaskName.valid&&(!online||!m.subtaskName.current(now));
  const bool layerOld=m.layerNum.valid&&(!online||!m.layerNum.current(now));
  const bool totalOld=m.totalLayers.valid&&(!online||!m.totalLayers.current(now));
  const bool materialOld=tray&&(!online||!m.activeTrayRaw.current(now));
  const char *notice=!online?"Offline":!ws43b_view::statusCurrent(m,online,now)?ws43bText("Dane nieaktualne","Data outdated"):layerOld?ws43bText("Warstwa nieaktualna","Layer outdated"):
    totalOld?ws43bText("Razem: ostatni odczyt","Total: last reading"):nameOld?ws43bText("Nazwa: ostatni odczyt","Name: last reading"):
    materialOld?ws43bText("Materiał: ostatni odczyt","Material: last reading"):ws43bText("Dane na żywo","Live data");
  if(tray&&tray->type.valid)snprintf(out,cap,"%s · AMS %u / %u · %s",notice,unsigned(unit->id)+1,unsigned(m.activeTrayRaw.value%4)+1,tray->type.value);
  else snprintf(out,cap,"%s · %s",notice,ws43bText("Materiał: brak danych","Material unavailable"));
}
void dashboardScreen(const BambuMonitorTelemetry &m,bool online,uint32_t now,
                     ws43b_repaint::Mask regions=ws43b_repaint::All) {
  using R=ws43b_repaint::Region;
  if(regions&ws43b_repaint::regionBit(R::Primary)) {
    v2Clear(16,66,500,242);ws43b_native::card(tft,16,66,500,242,BG);
    const bool advanced=ws43bAdvancedDisplay();
    const bool preparing=advanced&&ws43b_view::beforeFirstLayer(m,online,now);
    const bool progress=ws43b_view::dashboardProgressVisible(m,online,now,advanced);
    const char *title=!advanced?ws43bText("POSTĘP WYDRUKU","PRINT PROGRESS"):
      dashboardActivity.state==ws43b_view::Activity::Cleaning?ws43bText("CZYSZCZENIE DYSZY","NOZZLE CLEANING"):
      dashboardActivity.state==ws43b_view::Activity::Leveling?ws43bText("POZIOMOWANIE STOŁU","BED LEVELING"):
      dashboardActivity.state==ws43b_view::Activity::CalibrationLines?ws43bText("LINIE KALIBRACYJNE","CALIBRATION LINES"):
      preparing?ws43bText("PRZYGOTOWANIE","PREPARING"):ws43bText("POSTĘP WYDRUKU","PRINT PROGRESS");
    v2Text(title,32,80,196,ws43b_v2_13,13,v2Dim());
    char buf[200];
    if(preparing) {
      v2Text(ws43bText("Przed pierwszą","Before the first"),32,112,190,ws43b_v2_b17,17,v2Ink());
      v2Text(ws43bText("warstwą","layer"),32,139,190,ws43b_v2_b17,17,v2Ink());
    } else {
      if(progress)snprintf(buf,sizeof(buf),"%u",unsigned(m.progress.value));else snprintf(buf,sizeof(buf),"--");
      const int numberWidth=v2Text(buf,30,99,163,ws43b_v2_b64,64,progress?v2Ink():v2Dim(),false,false);
      if(progress)v2Text("%",30+numberWidth,120,48,ws43b_v2_b43,43,v2Ink(),false,false);
    }
    v2Text(ws43bText("Pozostało","Remaining"),33,170,184,ws43b_v2_13,13,v2Dim());
    const bool remaining=!missing(m.remainingMinutes,online,now);
    if(remaining) {
      if(m.remainingMinutes.value<60)snprintf(buf,sizeof(buf),"%u min",unsigned(m.remainingMinutes.value));
      else snprintf(buf,sizeof(buf),"%uh %02u",unsigned(m.remainingMinutes.value/60),unsigned(m.remainingMinutes.value%60));
    } else snprintf(buf,sizeof(buf),"--");
    v2Text(buf,32,188,190,ws43b_v2_b28,28,remaining?v2Ink():v2Dim(),false,false);
    struct tm local{};
    if(remaining&&ws43b_view::statusCurrent(m,online,now)&&(!strcmp(m.status.value,"RUNNING")||!strcmp(m.status.value,"PREPARE"))&&getLocalTime(&local,0)) {
      const time_t end=time(nullptr)+60u*m.remainingMinutes.value;localtime_r(&end,&local);
      snprintf(buf,sizeof(buf),ws43bText("Koniec około %02d:%02d","Ends around %02d:%02d"),local.tm_hour,local.tm_min);
    } else snprintf(buf,sizeof(buf),"%s",missing(m.remainingMinutes,online,now)?missing(m.remainingMinutes,online,now):statusText(m.status,online,now));
    v2Text(buf,33,223,190,ws43b_v2_13,13,v2Dim());
    dashboardActivityIcon(now,true);
    tft.fillRoundRect(32,247,468,6,3,ws43b_native::rgb(53,75,93));
    if(progress&&m.progress.value>0)tft.fillRoundRect(32,247,468*(m.progress.value>100?100:m.progress.value)/100,6,3,v2Accent());
    const bool nameOld=m.subtaskName.valid&&(!online||!m.subtaskName.current(now));
    v2Text(m.subtaskName.valid?m.subtaskName.value:ws43bText("Brak nazwy wydruku","Job name unavailable"),33,265,advanced?306:466,ws43b_v2_b17,17,nameOld?v2Dim():v2Ink());
    if(advanced) {
      char layer[24],total[24];
      if(m.layerNum.valid)snprintf(layer,sizeof(layer),"%u",unsigned(m.layerNum.value));else snprintf(layer,sizeof(layer),"--");
      if(m.totalLayers.valid)snprintf(total,sizeof(total),"%u",unsigned(m.totalLayers.value));else snprintf(total,sizeof(total),"--");
      snprintf(buf,sizeof(buf),ws43bText("Warstwa %s / %s","Layer %s / %s"),layer,total);
      v2Text(buf,346,267,153,ws43b_v2_13,13,v2Dim(),true);
      dashboardMaterialLine(buf,sizeof(buf),m,online,now);
      v2Text(buf,33,288,466,ws43b_v2_12,12,v2Dim());
    } else {
      const char *notice=!online?ws43bText("Offline · ostatnie dane","Offline · last readings"):
        !ws43b_view::statusCurrent(m,online,now)?ws43bText("Oczekiwanie na aktualne dane","Waiting for current data"):
        nameOld?ws43bText("Nazwa: ostatni odczyt","Name: last reading"):ws43bText("Dane z drukarki","Printer data");
      v2Text(notice,33,288,466,ws43b_v2_12,12,v2Dim());
    }
    dashboardCoolingPainted=false;
  }
  if(regions&ws43b_repaint::regionBit(R::Nozzle))dashboardTemperature(0,66,ws43bText("DYSZA","NOZZLE"),m.nozzleTemp,m.nozzleTarget,online,now);
  if(regions&ws43b_repaint::regionBit(R::Bed))dashboardTemperature(1,150,ws43bText("STÓŁ","BED"),m.bedTemp,m.bedTarget,online,now);
  MonitorField<float> noTarget;
  if(regions&ws43b_repaint::regionBit(R::Chamber))dashboardTemperature(2,234,ws43bText("KOMORA","CHAMBER"),m.chamberTemp,noTarget,online,now);
  dashboardAms(m,online,now,regions);
}
// Match the dashboard/AMS policy: label actual observation age only when
// the value is no longer current, or the connection is offline.
template<class Field>
void detailReadingCard(const char *title,const char *value,int x,int y,
                       const Field &field,bool online,uint32_t now) {
  const bool current=online&&field.current(now);
  detailCard(title,value,x,y,240,current?INK:DIM);
  char age[64];amsReadingAge(age,sizeof(age),field,online,now);
  if(age[0])dashText(age,x+16,y+73,208,14,WARN);
}
void detailsScreen(const BambuMonitorTelemetry &m, bool online, uint32_t now) {
  tft.fillRoundRect(24, 86, 752, 120, 10, CARD);
  char nameAge[64],jobTitle[100];
  amsReadingAge(nameAge,sizeof(nameAge),m.subtaskName,online,now);
  snprintf(jobTitle,sizeof(jobTitle),"%s%s%s",ws43bText("ZADANIE","JOB"),nameAge[0]?" · ":"",nameAge);
  dashText(jobTitle,40,99,530,14,nameAge[0]?WARN:DIM);
#if WS43B_FULL_WEBUI
  button(ws43bText("Wskaźniki >","Gauges >"),600,90,160,30,false);
#endif
  const char *why = missing(m.subtaskName, online, now);
  // Fit two lines with the actual selected font. UTF-8 is left intact; avoid
  // splitting a multibyte sequence when a long name wraps or is abbreviated.
  const char *source = m.subtaskName.valid ? m.subtaskName.value : ws43bText("Brak nazwy wydruku","Job name unavailable");
  tft.loadFont(ws43b_dash_18);
  for (int line = 0; line < 2 && *source; ++line) {
    char text[132]{};
    size_t used = 0;
    while (source[used] && used < sizeof(text) - 5) {
      size_t next = used + 1;
      while (source[next] && (uint8_t(source[next]) & 0xC0) == 0x80) ++next;
      if (next >= sizeof(text) - 4) break;
      memcpy(text + used, source + used, next - used); text[next] = 0;
      if (tft.textWidth(text) > 700) { text[used] = 0; break; }
      used = next;
    }
    if (!used) break;
    if (line == 1 && source[used]) {
      while (used && tft.textWidth((String(text) + "...").c_str()) > 700) {
        do { --used; } while (used && (uint8_t(text[used]) & 0xC0) == 0x80);
        text[used] = 0;
      }
      strncat(text, "...", sizeof(text) - strlen(text) - 1);
    }
    dashText(text,40,131+line*32,716,18,why?DIM:INK);
    tft.loadFont(ws43b_dash_18);
    source += used;
  }
  tft.unloadFont();
  char buf[160];
  jobLayerText(buf,sizeof(buf),m,online,now);
  char *ageSuffix=strstr(buf," · ");
  if(ageSuffix)*ageSuffix=0;
  detailCard(ws43bText("WARSTWA / RAZEM", "LAYER / TOTAL"), buf, 24, 218, 240);
  if(ageSuffix)dashText(ageSuffix+4,40,293,208,14,WARN);
  if (!m.chamberTemp.valid) snprintf(buf, sizeof(buf), "%s", ws43bText("Brak danych","No data"));
  else snprintf(buf, sizeof(buf), "%.0f°C", double(m.chamberTemp.value));
  detailReadingCard(ws43bText("TEMP. KOMORY", "CHAMBER TEMP."),buf,280,218,m.chamberTemp,online,now);
  if (!m.speedLevel.valid) snprintf(buf, sizeof(buf), "%s", ws43bText("Brak danych","No data"));
  else {
    const char *names[] = {ws43bText("Brak danych", "No data"), ws43bText("Cichy", "Silent"), "Standard", "Sport", "Ludicrous"};
    snprintf(buf, sizeof(buf), "%s", m.speedLevel.value <= 4 ? names[m.speedLevel.value] : names[0]);
  }
  detailReadingCard(ws43bText("TRYB PRĘDKOŚCI", "SPEED MODE"),buf,536,218,m.speedLevel,online,now);
  const MonitorField<uint8_t> *fans[] = {&m.partFanPct, &m.auxFanPct, &m.chamberFanPct};
  const uint8_t rounded[] = {m.partFanRoundedPct, m.auxFanRoundedPct, m.chamberFanRoundedPct};
  const char *names[] = {ws43bText("NAWIEW NA WYDRUK", "PART FAN"), ws43bText("WENT. POMOCNICZY", "AUXILIARY FAN"), ws43bText("WENTYLATOR KOMORY", "CHAMBER FAN")};
  for (int i = 0; i < 3; ++i) {
    if (!fans[i]->valid) snprintf(buf, sizeof(buf), "%s", ws43bText("Brak danych","No data"));
    else snprintf(buf, sizeof(buf), "%u%%", dispSettings.fanMatchPrinter ? rounded[i] : fans[i]->value);
    const int x=24+256*i;
    detailReadingCard(names[i],buf,x,326,*fans[i],online,now);
    tft.fillRoundRect(x+16,417,208,3,1,TRACK);
    if(fans[i]->valid) {
      const unsigned percent=dispSettings.fanMatchPrinter?rounded[i]:fans[i]->value;
      const unsigned width=208*(percent>100?100:percent)/100;
      if(width)tft.fillRect(x+16,417,width,3,online&&fans[i]->current(now)?ACCENT:DIM);
    }
  }
}
void settingRow(const char *title,const char *value,int y,bool selected=false) {
  tft.fillRoundRect(44,y,708,48,9,CARD);tft.drawRoundRect(44,y,708,48,9,TRACK);
  dashText(title,60,y+13,320,18,INK);
  dashText(value,398,y+13,312,18,selected?ACCENT:DIM);
  tft.drawLine(727,y+18,733,y+24,DIM);tft.drawLine(733,y+24,727,y+30,DIM);
}
void settingsScreen() {
  dashText(ws43bText("Ustawienia", "Settings"),44,91,520,24,INK);
  const bool holding=touchHeld&&!touchMoved&&systemTouchArea(pressX,pressY);
  const uint32_t elapsed=holding?uint32_t(millis()-pressMs):0;
  dashText("System",680,96,96,18,holding?INK:DIM);
  if(holding)tft.fillRect(680,121,80*(elapsed>3000?3000:elapsed)/3000,2,ACCENT);
  const char *titles[]={ws43bText("Wygląd", "Appearance"),ws43bText("Zegar i ekran", "Clock and screen"),ws43bText("Pogoda i noc", "Weather and night"),ws43bText("Język i dane", "Language and data")};
  const char *hints[]={ws43bText("Motyw kolorystyczny", "Color theme"),ws43bText("Czas bez dotyku i wygaszanie", "Idle timeout and sleep"),ws43bText("Pogoda, słońce i czas nocny", "Weather, sun and night timeout"),ws43bText("Polski / English, wentylatory", "Polski / English, fans")};
  for(int i=0;i<4;++i) {
    const int x=24+(i%2)*384,y=140+(i/2)*132;
    tft.fillRoundRect(x,y,368,114,12,CARD);
    tft.drawRoundRect(x,y,368,114,12,TRACK);
    const UiAsset icons[]={UiAsset::Settings,UiAsset::Clock,UiAsset::Weather,UiAsset::Network};
    panelIcon(icons[i],x+34,y+33,CARD,36);
    dashText(titles[i],x+62,y+20,290,24,INK);
    dashText(hints[i],x+20,y+65,326,14,DIM);
  }
}
void systemSettingsScreen() {
  button(ws43bText("< Ustawienia","< Settings"),24,82,240,40,false);
  dashText("System",290,92,480,24,INK);
  button(ws43bText("Ustawienia fabryczne","Factory reset"),44,164,708,56,false);
  tft.drawRoundRect(44,164,708,56,9,RED);
  dashText(ws43bText("Usuwa konfigurację panelu i uruchamia go ponownie.","Clears panel configuration and restarts it."),44,246,708,18,DIM);
  dashText(ws43bText("Ustawienia drukarki pozostają bez zmian.","Printer settings remain unchanged."),44,280,708,18,DIM);
}
void factoryResetScreen(uint32_t now) {
  dashText(ws43bText("Ustawienia fabryczne","Factory reset"),44,90,708,24,WARN);
  dashText(ws43bText("Usunie: sieci Wi-Fi, konfigurację drukarek,","Removes: Wi-Fi networks, printer configuration,"),44,142,708,18,INK);
  dashText(ws43bText("token chmury, pogodę i ustawienia panelu.","cloud token, weather and panel settings."),44,174,708,18,INK);
  dashText(ws43bText("Firmware i ustawienia drukarki pozostaną.","Firmware and printer settings are preserved."),44,216,708,18,DIM);
  dashText(ws43bText("Po restarcie: asystent konfiguracji Wi-Fi.","After restart: Wi-Fi setup assistant."),44,248,708,18,DIM);
  const bool holding=touchHeld&&!touchMoved&&pressX>=44&&pressX<752&&pressY>=296&&pressY<356;
  const uint32_t elapsed=holding?uint32_t(now-pressMs):0;
  button(elapsed>=3000?ws43bText("Puść, aby zresetować","Release to reset"):
    ws43bText("Przytrzymaj 3 s, aby zresetować","Hold for 3 seconds to reset"),44,296,708,60,holding);
  if(holding)tft.fillRect(56,348,684*(elapsed>3000?3000:elapsed)/3000,4,WARN);
  button(ws43bText("Anuluj","Cancel"),44,374,708,42,false);
}
void appearanceSettingsScreen() {

  button(ws43bText("< Ustawienia", "< Settings"),44,98,174,36,false);
  dashText(ws43bText("Wygląd", "Appearance"),244,102,490,24,INK);
  const char *names[]={ws43bText("Miętowy", "Mint"),ws43bText("Zielony", "Green"),ws43bText("Bursztynowy", "Amber")};
  const uint16_t accents[]={0x67B6,0x77B2,0xF5CB};
  for(uint8_t i=0;i<3;++i) {
    const int y=151+66*i;
    const bool selected=ws43bViewTheme()==i;
    // Match ordinary settings rows; these are radio choices, not submenus.
    tft.fillRoundRect(44,y,708,48,9,CARD);
    tft.drawRoundRect(44,y,708,48,9,selected?ACCENT:TRACK);
    dashText(names[i],60,y+13,320,18,INK);
    const uint16_t samples[]={ws43b_style::background,CARD,accents[i]};
    for(int j=0;j<3;++j) {
      tft.fillRoundRect(398+j*32,y+13,24,22,4,samples[j]);
      tft.drawRoundRect(398+j*32,y+13,24,22,4,j==2?accents[i]:TRACK);
    }
    if(selected)dashText(ws43bText("Wybrany","Selected"),550,y+13,140,18,ACCENT);
    tft.drawCircle(724,y+24,8,selected?ACCENT:DIM);
    if(selected)tft.fillCircle(724,y+24,4,ACCENT);
  }
  button(ws43bText("Prosty","Simple"),44,347,220,46,!ws43bAdvancedDisplay());
  button(ws43bText("Zaawansowany (w budowie)","Advanced (in development)"),276,347,476,46,ws43bAdvancedDisplay());
  if(settingsNotice)small(settingsNotice,44,404,708);
  else dashText(ws43bText("Tryb ekranu: Wydruk i wygaszacz. Alarmy w obu trybach.","Display mode: Print and screensaver. Alerts in both modes."),44,404,708,14,DIM);
}
void generalSettingsScreen() {

  button(ws43bText("< Ustawienia", "< Settings"),44,98,174,36,false);
  dashText(ws43bText("Język i dane", "Language and data"),244,102,490,24,INK);
  settingRow(ws43bText("Język","Language"),ws43bPolish()?"Polski":"English",151);
  settingRow(ws43bText("Wentylatory","Fans"),dispSettings.fanMatchPrinter?ws43bText("Co 10%","Steps of 10%"):ws43bText("Co 1%","Steps of 1%"),217);
  settingRow(ws43bText("Otwórz WebUI","Open WebUI"),ws43bText("Kod QR","QR code"),283);
  dashText(ws43bText("Język wspólny dla panelu i WebUI.","Language shared by panel and WebUI."),44,348,708,18,DIM);
  small(settingsNotice,44,382,710);
}
void connectedWifiName(int x,int y,int w) {
  const String ssid=WiFi.SSID();
  // Wrap long network names without splitting a UTF-8 character.
  tft.loadFont(ws43b_dash_18);
  tft.setTextSize(1);
  unsigned split=ssid.length();
  while(split && tft.textWidth(ssid.substring(0,split).c_str())>w) {
    --split;
    while(split && (uint8_t(ssid[split])&0xc0)==0x80) --split;
  }
  tft.unloadFont();
  dashText(ssid.length()?ssid.substring(0,split).c_str():ws43bText("Brak nazwy sieci","Network name unavailable"),x,y,w,18,INK);
  if(split<ssid.length()) dashText(ssid.substring(split).c_str(),x,y+26,w,18,INK);
}
void webQrScreen() {
  button(ws43bText("< Język i dane", "< Language and data"),24,82,280,40,false);
  dashText(ws43bText("Otwórz WebUI", "Open WebUI"),350,92,420,24,INK);
  const IPAddress ip=WiFi.localIP();
  if(!isWiFiConnected() || uint32_t(ip)==0) {
    dashText(ws43bText("Brak połączenia Wi-Fi", "No Wi-Fi connection"),48,200,704,24,DIM);
    dashText(ws43bText("Kod QR pojawi się po uzyskaniu adresu IP.","QR code appears once an IP address is available."),48,249,704,18,DIM);
    return;
  }
  const String url=String("http://")+ip.toString()+"/";
  // Version 2 fits the longest IPv4 URL. Four-module white quiet zone.
  tft.qrcode(url.c_str(),48,132,280,2,true);
  tft.fillRoundRect(338,132,438,280,12,CARD);
  tft.drawRoundRect(338,132,438,280,12,TRACK);
  dashText(ws43bText("Połączono z Wi-Fi:", "Connected to Wi-Fi:"),352,140,420,18,DIM);
  connectedWifiName(352,168,420);
  dashText(url.c_str(),352,234,420,24,INK);
  dashText(ws43bText("Zeskanuj aparatem telefonu.","Scan with your phone camera."),352,286,420,18,DIM);
  dashText(ws43bText("Telefon musi mieć dostęp", "Your phone needs access"),352,330,420,18,DIM);
  dashText(ws43bText("do sieci panelu.", "to the panel network."),352,356,420,18,DIM);
}
void clockSettingsScreen() {
  const auto &clock = ws43bClockSettings();

  button(ws43bText("< Ustawienia", "< Settings"), 44, 98, 174, 36, false);
  small(ws43bText("ZEGAR I WYGASZANIE", "CLOCK AND IDLE SCREEN"), 222, 105, 520, ACCENT);
  char buf[64];
  if (clock.idleMinutes) snprintf(buf, sizeof(buf), "%u min", unsigned(clock.idleMinutes));
  else snprintf(buf, sizeof(buf), ws43bText("Wyłączone", "Disabled"));
  settingRow(ws43bText("Bez dotyku","No touch"),buf,151);
  settingRow(ws43bText("Po czasie","On timeout"),clock.screenOff?ws43bText("Wyłącz ekran","Turn off screen"):ws43bText("Pokaż zegar","Show clock"),217);
  settingRow(ws43bText("Format czasu","Time format"),clock.use24h?"24 h":"12 h (AM/PM)",283);

  small(settingsNotice, 44, 382, 710);
}
void weatherSettingsScreen() {
  const auto c=ws43bWeatherConfig();
  button(ws43bText("< Ustawienia","< Settings"),44,98,174,36,false);
  small(ws43bText("POGODA I DZIEŃ/NOC","WEATHER AND DAY/NIGHT"),222,105,530,ACCENT);
  settingRow(ws43bText("Pokaż pogodę","Show weather"),c.enabled?ws43bText("Włączone","On"):ws43bText("Wyłączone","Off"),151,c.enabled);
  settingRow(ws43bText("Tryb nocny","Night mode"),c.solar?ws43bText("Zachód / wschód słońca","Sunset / sunrise"):ws43bText("Ręczne godziny","Manual hours"),217,c.solar);
  char text[80];snprintf(text,sizeof(text),"%u s",c.nightSeconds);
  settingRow(ws43bText("Noc: bez dotyku","Night: no touch"),text,283);
  dashText(*c.city?c.city:ws43bText("Wybierz miejscowość w WebUI","Choose location in WebUI"),44,349,710,18,DIM);
  small(dpSettings.nightModeEnabled?settingsNotice:ws43bText("Harmonogram nocny włącz w WebUI.","Enable the night schedule in WebUI."),44,382,710);
}
#if WS43B_FULL_WEBUI
bool gaugeDataFresh(uint8_t type, const BambuState &state, uint32_t now) {
  const auto &m = state.monitor;
  int unit = -1;
  if (type >= GAUGE_AMS_HUM_1 && type <= GAUGE_AMS_HUM_4) unit = type - GAUGE_AMS_HUM_1;
  if (type >= GAUGE_AMS_TEMP_1 && type <= GAUGE_AMS_TEMP_4) unit = type - GAUGE_AMS_TEMP_1;
  if (type >= GAUGE_AMS_FILAMENT_1 && type <= GAUGE_AMS_FILAMENT_4) unit = type - GAUGE_AMS_FILAMENT_1;
  if (type >= GAUGE_AMS_BARS_1 && type <= GAUGE_AMS_BARS_4) unit = type - GAUGE_AMS_BARS_1;
  if (unit >= 0) {
    const MonitorAmsUnit *matched = nullptr;
    for (const auto &candidate : m.amsUnits)
      if (candidate.used && candidate.id == state.ams.units[unit].id) { matched = &candidate; break; }
    if (!state.ams.units[unit].present || !matched) return false;
    const auto &u = *matched;
    if (!u.used || (u.present.valid && !u.present.value)) return false;
    if (type <= GAUGE_AMS_HUM_4) return u.humidityRaw.current(now); // The gauge's numeric value is raw RH.
    if (type >= GAUGE_AMS_TEMP_1 && type <= GAUGE_AMS_TEMP_4) return u.temp.current(now);
    // Filament renderers already represent empty/unknown trays individually.
    return m.hasUsefulData && uint32_t(now - m.lastUsefulMs) <= BAMBU_MONITOR_FRESH_MS;
  }
  switch (type) {
    // The caller separately gates the entire gauge on its online connection.
    case GAUGE_PROGRESS: return !ws43b_view::beforeFirstLayer(m,true,now) && m.progress.current(now) && m.remainingMinutes.current(now);
    case GAUGE_NOZZLE: return m.nozzleTemp.current(now);
    case GAUGE_BED: return m.bedTemp.current(now);
    case GAUGE_PART_FAN: return m.partFanPct.current(now);
    case GAUGE_AUX_FAN: return m.auxFanPct.current(now);
    case GAUGE_CHAMBER_FAN: return m.chamberFanPct.current(now);
    case GAUGE_CHAMBER_TEMP: return m.chamberTemp.current(now);
    case GAUGE_HEATBREAK: return m.heatbreakFanPct.current(now);
    case GAUGE_AUX_FAN_RIGHT: return (state.airductFuncs & (1u << 6)) && m.hasUsefulData && uint32_t(now-m.lastUsefulMs)<=BAMBU_MONITOR_FRESH_MS;
    case GAUGE_EXHAUST_FAN: return (state.airductFuncs & (1u << 2)) && m.hasUsefulData && uint32_t(now-m.lastUsefulMs)<=BAMBU_MONITOR_FRESH_MS;
    case GAUGE_NOZZLE_RIGHT: case GAUGE_NOZZLE_LEFT: return state.dualNozzle && m.nozzleTemp.current(now);
    case GAUGE_LAYER: return m.layerNum.current(now) && m.totalLayers.current(now);
    default: return m.hasUsefulData && uint32_t(now - m.lastUsefulMs) <= BAMBU_MONITOR_FRESH_MS;
  }
}
void gaugesScreen(const PrinterSlot &slot, bool online, uint32_t now) {
  for (unsigned i = 0; i < GAUGE_SLOT_COUNT; ++i) {
    const uint8_t type = slot.config.gaugeSlots[i];
    const int cx = 150 + (i % 3) * 250, cy = 168 + (i / 3) * 176;
    if (type == GAUGE_EMPTY) continue;
    if(type==GAUGE_PROGRESS && ws43b_view::beforeFirstLayer(slot.state.monitor,online,now)) {
      small(ws43bText("Przygotowanie", "Preparing"),cx-90,cy-10,180);
      continue;
    }
    if (type != GAUGE_CLOCK && type != GAUGE_POWER && (!online || !gaugeDataFresh(type, slot.state, now))) {
      small(online ? ws43bText("Brak danych", "No data") : ws43bText("Nieaktualne", "Outdated"), cx - 72, cy - 10, 145);
      continue;
    }
    drawGaugeTile(type, slot.state, rotState.displayIndex, cx, cy, 67, 8, true, false);
  }
}
#endif

// Native-size antialiased Inter; avoid loading fonts outside the dirty band.
void modernText(const char *text, int x, int y, bool digits, uint16_t color) {
  int32_t cx, cy, cw, ch;
  tft.getClipRect(&cx, &cy, &cw, &ch);
  const int radius = digits ? 90 : 24;
  if (y + radius < cy || y - radius >= cy + ch) return;
  tft.setTextSize(1);
  ::setFont(tft, FONT_NONE);
  if (!tft.loadFont(digits ? ws43b_inter_digits : ws43b_inter_body))
    tft.setFont(digits ? (const lgfx::IFont *)&fonts::FreeSans24pt7b : (const lgfx::IFont *)&fonts::FreeSans12pt7b);
  tft.setTextDatum(MC_DATUM);
  tft.setTextColor(color); // Equal foreground/background enables canvas AA blending.
  tft.drawString(text, x, y);
  tft.unloadFont();
}
uint16_t waterColor(int y) {
  // Dark emerald stays readable beneath white text even at 100%.
  const int depth = y * 255 / 479;
  return tft.color565(2, 104 - depth * 66 / 255, 78 - depth * 43 / 255);
}
bool clockHasProgress(const BambuMonitorTelemetry &m,bool online,uint32_t now) {
  // The saver mirrors mc_percent even during preparation. The dashboard's
  // first-layer presentation gate intentionally remains independent.
  return ws43b_view::progressCurrent(m,online,now) &&
    (!strcmp(m.status.value,"RUNNING") || !strcmp(m.status.value,"PREPARE") || !strcmp(m.status.value,"PAUSE"));
}
bool coolingView(const BambuMonitorTelemetry &m) {
  const bool online=isWiFiConnected()&&displayedPrinter().state.connected;
  return online&&m.status.current(millis())&&m.bedTemp.current(millis())&&dashboardCooling;
}
ws43b_view::Saver saverView(const BambuMonitorTelemetry &m,bool online,uint32_t now) {
  bool alert=false;
#if WS43B_FULL_WEBUI
  alert=hmsScreenAlerting();
#endif
  return ws43b_view::saver(m,online,now,coolingView(m),alert,displayedPrinter().state.printing);
}
void modernText(const char *,int,int,bool,uint16_t);
void drawClockBackground(bool,int,uint32_t);
void clockWeatherIcon(const BambuMonitorTelemetry &,bool,uint32_t);
void coolingScreen(const BambuMonitorTelemetry &m,bool online,uint32_t now,bool partial) {
  const bool fresh=online&&m.status.current(now)&&m.bedTemp.current(now);
  if(!partial) {
    drawClockBackground(false,0,now);
    char text[80];struct tm local{};const bool synced=getLocalTime(&local,0);
    if(synced)snprintf(text,sizeof(text),"%02d.%02d.%04d",local.tm_mday,local.tm_mon+1,local.tm_year+1900);
    else snprintf(text,sizeof(text),"%s",ws43bText("Synchronizacja czasu","Synchronizing time"));
    modernText(text,400,34,false,DIM);
    if(synced)snprintf(text,sizeof(text),"%02d:%02d",ws43b_water::hour(local.tm_hour,netSettings.use24h),local.tm_min);else snprintf(text,sizeof(text),"--:--");
    modernText(text,400,133,true,INK);
    if(synced&&!netSettings.use24h)dashText(local.tm_hour<12?"AM":"PM",626,151,72,18,DIM);
    tft.drawFastHLine(260,208,280,TRACK);
    dashText(ws43bText("CHŁODZENIE STOŁU","BED COOLING"),310,239,466,24,ACCENT);
    if(fresh)snprintf(text,sizeof(text),"%.0f°C",double(m.bedTemp.value));else snprintf(text,sizeof(text),"--°C");
    dashText(text,310,290,466,30,INK);
    dashText(fresh?ws43bText("Grzanie wyłączone","Heater off"):ws43bText("Dane nieaktualne","Data outdated"),310,340,466,18,fresh?DIM:WARN);
    if(const auto *u=ws43b_view::dryingUnit(m,online,now)) {
      const bool current=online&&u->dryRemainMin.current(now);
      snprintf(text,sizeof(text),current?ws43bText("AMS · Suszenie: %u h %02u min","AMS · Drying: %u h %02u min"):ws43bText("AMS · Ostatnio: %u h %02u min","AMS · Last: %u h %02u min"),unsigned(u->dryRemainMin.value/60),unsigned(u->dryRemainMin.value%60));
      dashText(text,32,391,736,14,current?ACCENT:WARN);
    }
  }
  tft.setClipRect(108,222,170,158);tft.fillRect(108,222,170,158,tft.color565(3,14,23));
  const int cx=187,cy=278;
  panelIcon(UiAsset::Fan,cx,cy,tft.color565(3,14,23),72);
  // Airflow moves beneath the shared fan miniature; it is symbolic, not RPM.
  for(int lane=0;lane<3;++lane) {
    const int drift=fresh?int((now/90+lane*5)%16):8;
    tft.drawFastHLine(cx-28+drift,cy+42+lane*5,38,lane==1?ACCENT:DIM);
  }
  panelIcon(UiAsset::Bed,cx,357,tft.color565(3,14,23),40);
  tft.clearClipRect();clockWeatherIcon(m,online,now);
}
// Shared saver canvas: the wave is decorative and never crosses the clock.
void drawClockBackground(bool, int, uint32_t now) {
  int32_t x,y,w,h;tft.getClipRect(&x,&y,&w,&h);
  tft.fillRect(x,y,w,h,tft.color565(3,14,23));
  for(int col=x/4*4;col<x+w;col+=4) {
    const int back=424+int(5*sinf(col*0.014f+now*0.0003f));
    const int front=436+int(6*sinf(col*0.012f-now*0.0004f));
    tft.fillRect(col,back,4,480-back,tft.color565(5,35,45));
    tft.fillRect(col,front,4,480-front,tft.color565(5,43,49));
  }
}
void clockWeatherIcon(const BambuMonitorTelemetry &,bool,uint32_t now) {
  // Redraw the whole footer together, so icon and text share the same canvas.
  tft.setClipRect(0,416,800,64);drawClockBackground(false,0,now);tft.clearClipRect();
  const auto config=ws43bWeatherConfig();
  if(!config.enabled)return;
  const auto weather=ws43bWeatherData();
  const bool fresh=ws43b_weather::fresh(weather,time(nullptr));
  if(!fresh) {
    dashText(ws43bText("Pogoda chwilowo niedostępna","Weather temporarily unavailable"),32,423,736,18,DIM);
    dashText(config.city,32,450,610,14,DIM);
    return;
  }
  ws43b_weather_icon::draw(tft,ws43b_weather_icon::classify(fresh,weather.code),48,447,1,
    dashboardWeatherNight(weather),fresh?INK:DIM,WARN,0x5EDE,now);
  char text[32];
  if(fresh)snprintf(text,sizeof(text),"%.0f°C",double(weather.temperature));
  else snprintf(text,sizeof(text),"--°C");
  dashText(text,78,431,110,30,INK);
  dashText(fresh?ws43bWeatherDescription(weather.code):ws43bText("Brak danych pogody","No weather data"),204,421,568,18,INK);
  dashText(config.city,204,449,440,14,DIM);
  dashText("Open-Meteo",665,449,115,14,DIM);
}
uint16_t saverFilamentColor(const BambuMonitorTelemetry &m,bool online,uint32_t now) {
  // MQTT deltas need not repeat tray_now. Keep the last confirmed selection
  // in this session until an explicit update; newSession() clears it.
  (void)now;
  if(online && m.activeTrayRaw.valid && m.activeTrayRaw.value<252) {
    for(const auto &u:m.amsUnits) {
      if(!u.used || u.id>=63 || (u.present.valid&&!u.present.value))continue;
      if(m.activeTrayRaw.value/4!=u.id)continue;
      const auto &tray=u.trays[m.activeTrayRaw.value%4];
      if(!(tray.present.valid&&!tray.present.value) && tray.colorRgb565.valid)return tray.colorRgb565.value;
    }
  }
  return 0xBDF7; // Unknown/external spool: neutral, never invent a filament color.
}
void saverAnimation(bool printing,bool drying,uint16_t filament,uint32_t now,unsigned progress) {
  const uint16_t bg=tft.color565(3,14,23);
  tft.setClipRect(108,222,170,158);tft.fillRect(108,222,170,158,bg);
  if(drying) {
    ws43b_drying_scene::draw(tft,190,298,74,now,ACCENT,TRACK,INK,bg);
  } else if(printing) {
    ws43b_print_scene::Scaled<decltype(tft)> scene{tft,109,222};
    ws43b_print_scene::draw(scene,0,0,progress,now,filament,bg,false);
  }
  tft.clearClipRect();
}
// The two concurrent activities have independent timers. These cards only use
// fresh drying telemetry; cached/offline values stay in the labelled history.
const char *saverStageCaption(const BambuMonitorTelemetry &m,bool online,uint32_t now,
                             ws43b_view::Activity activity) {
  using A=ws43b_view::Activity;
  if(ws43bAdvancedDisplay())switch(activity) {
    case A::Cleaning:return ws43bText("Czyszczenie dyszy","Nozzle cleaning");
    case A::Leveling:return ws43bText("Poziomowanie stołu","Bed leveling");
    case A::CalibrationLines:return ws43bText("Linie kalibracyjne","Calibration lines");
    case A::Heating:return ws43bText("Nagrzewanie","Heating");
    case A::Change:return ws43bText("Zmiana filamentu","Changing filament");
    case A::Load:return ws43bText("Ładowanie filamentu","Loading filament");
    case A::Unload:return ws43bText("Wyładowywanie filamentu","Unloading filament");
    default:break;
  }
  return ws43b_view::beforeFirstLayer(m,online,now)||!strcmp(m.status.value,"PREPARE")?
    ws43bText("PRZYGOTOWANIE","PREPARING"):ws43bText("DRUKOWANIE","PRINTING");
}
void saverDryingMetrics(const MonitorAmsUnit &unit,bool online,uint32_t now,int x,int y,int width,int size=18) {
  char temp[24],rh[24],text[64];
  if(online&&unit.temp.current(now))snprintf(temp,sizeof temp,"%.0f°C",double(unit.temp.value));
  else snprintf(temp,sizeof temp,"--°C");
  if(online&&unit.humidityRaw.current(now))snprintf(rh,sizeof rh,"%u%% RH",unsigned(unit.humidityRaw.value));
  else snprintf(rh,sizeof rh,"--%% RH");
  snprintf(text,sizeof text,"%s · %s",temp,rh);
  dashText(text,x,y,width,size,DIM);
}
void saverDryingEnd(const MonitorAmsUnit &unit,uint32_t now,int x,int y,int width) {
  char text[80];struct tm local{};
  if(getLocalTime(&local,0)) {
    const time_t end=time(nullptr)-uint32_t(now-unit.dryRemainMin.updatedMs)/1000u+time_t(unit.dryRemainMin.value)*60;
    struct tm finish{};localtime_r(&end,&finish);
    snprintf(text,sizeof text,ws43bText("Koniec około %02d:%02d%s","Ends around %02d:%02d%s"),ws43b_water::hour(finish.tm_hour,netSettings.use24h),finish.tm_min,netSettings.use24h?"":finish.tm_hour<12?" AM":" PM");
  } else snprintf(text,sizeof text,"%s",ws43bText("Oczekiwanie na godzinę","Waiting for clock sync"));
  dashText(text,x,y,width,18,DIM);
}
void combinedSaverCards(const BambuMonitorTelemetry &m,const MonitorAmsUnit &unit,
                        bool online,uint32_t now,ws43b_view::Activity activity,bool partial,
                        bool waiting=false) {
  const uint16_t bg=tft.color565(7,25,34);
  const bool cleaning=activity==ws43b_view::Activity::Cleaning;
  const bool leveling=activity==ws43b_view::Activity::Leveling;
  const bool calibration=activity==ws43b_view::Activity::CalibrationLines;
  const bool progressValid=clockHasProgress(m,online,now);
  if(!partial) {
    for(int x:{24,408}) {
      tft.fillRoundRect(x,220,368,184,14,bg);
      tft.drawRoundRect(x,220,368,184,14,TRACK);
    }
    char text[100];
    if(waiting) {
      dashText(ws43bText("Oczekiwanie na dane","Waiting for data"),44,234,328,18,ACCENT);
      if(m.progress.valid)snprintf(text,sizeof text,ws43bText("Ostatnio: %u%%","Last: %u%%"),unsigned(m.progress.value));
      else snprintf(text,sizeof text,"--%%");
      dashText(text,44,278,194,24,DIM);
      if(m.remainingMinutes.valid)
        snprintf(text,sizeof text,ws43bText("Ostatni czas: %u h %02u min","Last remaining: %u h %02u min"),unsigned(m.remainingMinutes.value/60),unsigned(m.remainingMinutes.value%60));
      else snprintf(text,sizeof text,"%s",ws43bText("Ostatni czas: --","Last remaining: --"));
      dashText(text,44,350,328,14,DIM);
    } else {
      dashText(saverStageCaption(m,online,now,activity),44,234,328,18,ACCENT);
      if(progressValid)snprintf(text,sizeof text,"%u%%",unsigned(m.progress.value));
      else snprintf(text,sizeof text,"--%%");
      dashText(text,44,257,194,72,progressValid?INK:DIM);
      if(missing(m.remainingMinutes,online,now)==nullptr)
        snprintf(text,sizeof text,ws43bText("Pozostało %u h %02u min","Remaining %u h %02u min"),unsigned(m.remainingMinutes.value/60),unsigned(m.remainingMinutes.value%60));
      else snprintf(text,sizeof text,"%s",ws43bText("Czas niedostępny","Time unavailable"));
      dashText(text,44,350,194,14,DIM);
      tft.fillRoundRect(44,386,328,5,2,TRACK);
      const int fill=progressValid?328*int(m.progress.value>100?100:m.progress.value)/100:0;
      if(fill>0)tft.fillRoundRect(44,386,fill,5,2,ACCENT);
    }
    snprintf(text,sizeof text,ws43bText("SUSZENIE · AMS %u","DRYING · AMS %u"),unsigned(unit.id));
    dashText(text,428,234,328,18,ACCENT);
    snprintf(text,sizeof text,"%u h %02u min",unsigned(unit.dryRemainMin.value/60),unsigned(unit.dryRemainMin.value%60));
    dashText(text,428,278,240,30,INK);
    saverDryingMetrics(unit,online,now,428,326,328);
    saverDryingEnd(unit,now,428,362,328);
  }
  // Independent small dirty regions: never repaint the clock or either timer
  // for an animation frame. The print model retains the selected filament.
  tft.setClipRect(250,258,112,104);tft.fillRect(250,258,112,104,bg);
  if(waiting) {
    panelIcon(UiAsset::Printer,306,310,bg,48);
  } else if(cleaning)ws43b_print_scene::cleaning(tft,250,258,dashboardActivity.elapsed(now),bg);
  else if(leveling)ws43b_print_scene::leveling(tft,250,258,now,ACCENT,bg);
  else if(calibration)ws43b_print_scene::calibrationLines(tft,250,258,now,saverFilamentColor(m,online,now),bg);
  else if(progressValid)ws43b_print_scene::draw(tft,250,258,m.progress.value,now,saverFilamentColor(m,online,now),bg,false);
  else panelIcon(UiAsset::Printer,306,310,bg,48);
  tft.clearClipRect();
  // Airflow around a spool, contained in the existing small dirty region.
  tft.setClipRect(680,262,68,62);tft.fillRect(680,262,68,62,bg);
  ws43b_drying_scene::draw(tft,714,292,29,now,ACCENT,TRACK,INK,bg);
  tft.clearClipRect();
}
void clockScreen(const BambuMonitorTelemetry &m, bool online, uint32_t now, bool partial = false) {
  const auto view=saverView(m,online,now);
  if(view==ws43b_view::Saver::Cooling){coolingScreen(m,online,now,partial);return;}
  const bool waiting=view==ws43b_view::Saver::Waiting;
  const bool print=view==ws43b_view::Saver::Print && clockHasProgress(m,online,now);
  const auto activity=ws43b_view::activity(m,online,now,false);
  const bool cleaning=saverView(m,online,now)==ws43b_view::Saver::Print && activity==ws43b_view::Activity::Cleaning;
  const bool leveling=saverView(m,online,now)==ws43b_view::Saver::Print && activity==ws43b_view::Activity::Leveling;
  const bool calibration=saverView(m,online,now)==ws43b_view::Saver::Print && activity==ws43b_view::Activity::CalibrationLines;
  const bool genericPreparation=view==ws43b_view::Saver::Print && ws43b_view::beforeFirstLayer(m,online,now) && !cleaning&&!leveling&&!calibration;
  const bool preparationScene=cleaning||leveling||calibration||genericPreparation;
  const auto *unit=ws43b_view::dryingUnit(m,online,now);
  const bool dryFresh=unit && online && unit->dryRemainMin.current(now);
  const bool notice=view==ws43b_view::Saver::Pause || view==ws43b_view::Saver::Alert;
  const bool combined=dryFresh&&(view==ws43b_view::Saver::Print||waiting);
  const bool dryOnly=!combined&&!print&&!preparationScene&&!notice&&!waiting&&dryFresh;
  const uint16_t white=tft.color565(237,247,244);
  if(!partial) {
    drawClockBackground(false,0,now);
    struct tm local{};char text[160];const bool timeValid=getLocalTime(&local,0);
    if(timeValid)snprintf(text,sizeof(text),"%02d.%02d.%04d",local.tm_mday,local.tm_mon+1,local.tm_year+1900);
    else snprintf(text,sizeof(text),"%s",ws43bText("Synchronizacja czasu","Synchronizing time"));
    modernText(text,400,34,false,DIM);
    if(timeValid)snprintf(text,sizeof(text),"%02d:%02d",ws43b_water::hour(local.tm_hour,netSettings.use24h),local.tm_min);
    else snprintf(text,sizeof(text),"--:--");
    modernText(text,400,133,true,white);
    if(timeValid&&!netSettings.use24h)dashText(local.tm_hour<12?"AM":"PM",626,151,72,18,DIM);
    tft.drawFastHLine(260,208,280,TRACK);
    if(combined) {
      // Both cards are rendered below on full and partial frames.
    } else if(preparationScene && !print) {
      dashText(saverStageCaption(m,online,now,activity),310,239,466,24,ACCENT);
      dashText(ws43bText("Przygotowanie wydruku","Preparing to print"),310,293,466,24,white);
      if(genericPreparation && !missing(m.remainingMinutes,online,now)) {
        snprintf(text,sizeof text,ws43bText("Pozostało %u h %02u min","Remaining %u h %02u min"),unsigned(m.remainingMinutes.value/60),unsigned(m.remainingMinutes.value%60));
        dashText(text,310,341,466,18,DIM);
      } else dashText(!ws43bAdvancedDisplay()?ws43bText("Oczekiwanie na aktualny postęp","Waiting for current progress"):
        genericPreparation?ws43bText("Oczekiwanie na pierwszą warstwę","Waiting for the first layer"):calibration?ws43bText("Drukowanie linii kalibracyjnych","Printing calibration lines"):leveling?ws43bText("Sprawdzanie punktów na stole","Probing points on the bed"):ws43bText("Dysza czyści się przed drukiem","Nozzle wipe before printing"),310,341,466,18,DIM);
    } else if(print) {
      dashText(saverStageCaption(m,online,now,activity),310,229,466,24,ACCENT);
      snprintf(text,sizeof(text),"%u%%",unsigned(m.progress.value));
      dashText(text,310,263,460,72,white);
      if(missing(m.remainingMinutes,online,now)==nullptr)
        snprintf(text,sizeof(text),ws43bText("Pozostało %u h %02u min","Remaining %u h %02u min"),unsigned(m.remainingMinutes.value/60),unsigned(m.remainingMinutes.value%60));
      else snprintf(text,sizeof(text),"%s",ws43bText("Czas: brak aktualnych danych","Time: no current data"));
      dashText(text,310,345,466,18,DIM);
      tft.fillRoundRect(310,376,450,7,3,TRACK);
      const int fill=450*int(m.progress.value>100?100:m.progress.value)/100;
      if(fill>0)tft.fillRoundRect(310,376,fill,7,3,ACCENT);
    } else if(waiting) {
      dashText(ws43bText("Oczekiwanie na dane","Waiting for data"),310,229,466,24,ACCENT);
      if(m.progress.valid)snprintf(text,sizeof(text),ws43bText("Ostatnio: %u%%","Last: %u%%"),unsigned(m.progress.value));
      else snprintf(text,sizeof(text),"--%%");
      dashText(text,310,278,460,30,DIM);
      if(m.remainingMinutes.valid)
        snprintf(text,sizeof(text),ws43bText("Ostatni czas: %u h %02u min","Last remaining: %u h %02u min"),unsigned(m.remainingMinutes.value/60),unsigned(m.remainingMinutes.value%60));
      else snprintf(text,sizeof(text),"%s",ws43bText("Ostatni czas: --","Last remaining: --"));
      dashText(text,310,345,466,18,DIM);
      panelIcon(UiAsset::Printer,190,298,tft.color565(3,14,23),74);
    } else if(dryOnly) {
      snprintf(text,sizeof text,ws43bText("SUSZENIE · AMS %u","DRYING · AMS %u"),unsigned(unit->id));
      dashText(text,310,229,466,24,ACCENT);
      snprintf(text,sizeof(text),"%u h %02u min",unsigned(unit->dryRemainMin.value/60),unsigned(unit->dryRemainMin.value%60));
      dashText(text,310,277,466,30,white);
      saverDryingEnd(*unit,now,310,331,466);
      saverDryingMetrics(*unit,online,now,310,373,466,18);
    } else {
      const bool current=ws43b_view::statusCurrent(m,online,now);
      const bool finished=current&&!strcmp(m.status.value,"FINISH");
      const bool ready=current&&!strcmp(m.status.value,"IDLE");
      const bool paused=view==ws43b_view::Saver::Pause;
      const bool alert=view==ws43b_view::Saver::Alert;
      const char *message=alert?ws43bText("BŁĄD DRUKARKI","PRINTER ERROR"):paused?ws43bText("WYDRUK WSTRZYMANY","PRINT PAUSED"):
        finished?ws43bText("WYDRUK ZAKOŃCZONY","PRINT FINISHED"):ready?ws43bText("Gotowa do pracy","Ready"):
        !online?ws43bText("Brak połączenia z drukarką","Printer disconnected"):ws43bText("Oczekiwanie na aktualne dane","Waiting for current data");
      panelIcon(alert?UiAsset::Alert:paused?UiAsset::Pause:
        finished?UiAsset::Check:ready?UiAsset::Printer:!online?UiAsset::Network:UiAsset::UnknownData,
        180,285,tft.color565(3,14,23),64,alert||paused||finished,alert?RED:paused?WARN:ACCENT);
      dashText(message,250,250,520,24,alert?RED:paused?WARN:INK);
      if(paused || alert)dashText(ws43bText("Sprawdź komunikat na drukarce","Check the message on the printer"),250,300,520,18,DIM);
      else if(finished && m.progress.current(now)) {
        snprintf(text,sizeof(text),"%u%%",unsigned(m.progress.value));dashText(text,250,299,520,30,ACCENT);
      } else if(!ready&&!finished)dashText(ws43bText("Ostatnie dane mogą być nieaktualne","Last readings may be outdated"),250,300,520,18,WARN);
    }
    if(unit && !notice && !dryOnly && !combined) {
      if(dryFresh)snprintf(text,sizeof(text),ws43bText("AMS %u · Suszenie · %u h %02u min","AMS %u · Drying · %u h %02u min"),unsigned(unit->id),unsigned(unit->dryRemainMin.value/60),unsigned(unit->dryRemainMin.value%60));
      else snprintf(text,sizeof(text),ws43bText("AMS · Dane sprzed %u min · suszenie niepotwierdzone","AMS · Data %u min old · drying unconfirmed"),unsigned(uint32_t(now-unit->dryRemainMin.updatedMs)/60000u));
      dashText(text,32, (print||preparationScene||waiting)?391:346,736,14,dryFresh?ACCENT:WARN);
    }
  }
  // Restore only moving regions; large digits stay untouched between samples.
  if(combined)combinedSaverCards(m,*unit,online,now,activity,partial,waiting);
  else if(preparationScene) {
    const uint16_t bg=tft.color565(3,14,23);
    tft.setClipRect(108,222,170,158);tft.fillRect(108,222,170,158,bg);
    ws43b_print_scene::Scaled<decltype(tft)> scene{tft,109,222};
    if(genericPreparation)panelIcon(activity==ws43b_view::Activity::Heating?UiAsset::Bed:UiAsset::Printer,190,298,bg,74);
    else if(calibration)ws43b_print_scene::calibrationLines(scene,0,0,now,saverFilamentColor(m,online,now),bg);
    else if(leveling)ws43b_print_scene::leveling(scene,0,0,now,ACCENT,bg);
    else ws43b_print_scene::cleaning(scene,0,0,dashboardActivity.elapsed(now),bg);
    tft.clearClipRect();
  } else if(print||dryOnly)saverAnimation(print,dryOnly,saverFilamentColor(m,online,now),now,print?m.progress.value:0);
  clockWeatherIcon(m,online,now);
  tft.setTextDatum(TL_DATUM);
}
void setupScreen(bool ap, bool wifi) {
  if(!ap && !(wifi && uint32_t(WiFi.localIP())!=0)) {
    const String ssid=WiFi.SSID();
    startupScreen(ws43b_boot::Phase::Wifi,ssid.c_str(),millis());
    small(ws43bText("Konfiguracja sieci będzie dostępna po zakończeniu próby.",
                   "Network setup will be available after this attempt."),24,444,752);
    return;
  }
  ws43b_native::screen(tft,BG);
  v2Text("BambuHelper",24,19,400,ws43b_v2_b25,25,v2Ink());
  v2Text(ws43bText("KONFIGURACJA","SETUP"),602,28,174,ws43b_v2_b14,14,v2Dim());
  tft.drawFastHLine(24,62,752,ws43b_native::line);
  if(ap) {
    dashText(ws43bText("Połącz telefon z panelem","Connect your phone to the panel"),32,116,736,24,ACCENT);
    const String ssid=getAPSSID();
    // Wi-Fi QR syntax: escape reserved characters independently of text labels.
    auto escaped=[](const String &value) {
      String result;
      for(size_t i=0;i<value.length();++i) {
        const char c=value[i];
        if(c=='\\'||c==';'||c==','||c==':'||c=='"')result+='\\';
        result+=c;
      }
      return result;
    };
    const String payload="WIFI:T:WPA;S:"+escaped(ssid)+";P:"+escaped(String(WIFI_AP_PASSWORD))+";;";
    tft.fillRect(32,150,280,280,TFT_WHITE);
    tft.qrcode(payload.c_str(),48,166,248,2,true);
    ws43b_native::card(tft,326,150,450,280,BG);
    dashText(ws43bText("Zeskanuj aparatem telefonu","Scan with your phone camera"),340,169,430,18,INK);
    dashText(ws43bText("Sieć Wi-Fi","Wi-Fi network"),340,217,430,14,DIM);
    dashText(ssid.c_str(),340,242,430,24,INK);
    dashText(ws43bText("Hasło","Password"),340,284,430,14,DIM);
    dashText(WIFI_AP_PASSWORD,340,309,430,24,INK);
    dashText(ws43bText("Następnie otwórz w przeglądarce:","Then open in your browser:"),340,357,430,14,DIM);
    dashText("http://192.168.4.1/",340,383,430,24,INK);
    dashText(ws43bText("Brak internetu w tej sieci jest normalny.","No internet on this setup network is normal."),32,448,736,14,DIM);
    return;
  }
  if (wifi && uint32_t(WiFi.localIP())!=0) {
    dashText(ws43bText("Dodaj drukarkę","Add a printer"),32,116,736,24,ACCENT);
    const String url=String("http://")+WiFi.localIP().toString()+"/";
    // URL QR opens WebUI; no Wi-Fi or printer credentials in this payload.
    tft.qrcode(url.c_str(),32,158,272,2,true);
    ws43b_native::card(tft,320,150,456,280,BG);
    dashText(ws43bText("Połączono z Wi-Fi:","Connected to Wi-Fi:"),336,161,440,18,DIM);
    connectedWifiName(336,189,440);
    dashText(ws43bText("Konfiguracja panelu:","Panel setup:"),336,249,440,18,DIM);
    dashText(url.c_str(),336,280,440,24,INK);
    dashText(ws43bText("Zeskanuj kod aparatem telefonu.","Scan the code with your phone."),336,334,440,18,INK);
    dashText(ws43bText("Telefon musi mieć dostęp","Your phone needs access"),336,369,440,18,DIM);
    dashText(ws43bText("do sieci panelu.","to the panel network."),336,395,440,18,DIM);
  }

  dashText(ws43bText("Tryb monitorowania","Monitoring mode"),24,451,752,14,DIM);
}
}

void beginWs43bErrorScreen(const char *printer) {
  tft.fillScreen(ws43b_style::background);
  panelIcon(UiAsset::Alert,48,40,ws43b_style::background,40,true,RED);
  dashText(ws43bText("Komunikaty drukarki","Printer messages"),80,24,696,30,INK);
  dashText(printer,24,66,752,14,DIM);
}
void drawWs43bErrorCard(unsigned row,const char *title,const char *code,const char *description,uint16_t color) {
  const int y=92+int(row)*106;
  tft.fillRoundRect(24,y,752,98,12,CARD);tft.drawRoundRect(24,y,752,98,12,TRACK);
  tft.fillRoundRect(24,y+12,3,74,1,color);
  dashText(title,40,y+8,280,18,color);dashText(code,342,y+8,416,18,DIM);
  // Wrap on UTF-8 boundaries with a visible ellipsis on the final line.
  const char *source=description?description:"";
  for(int line=0;line<2&&*source;++line) {
    char text[256]={};size_t n=0;
    tft.loadFont(ws43b_dash_18);
    while(source[n]&&n<sizeof(text)-5) {
      size_t next=n+1;while(source[next]&&(uint8_t(source[next])&0xc0)==0x80)++next;
      if(next>=sizeof(text)-4)break;
      memcpy(text+n,source+n,next-n);text[next]=0;
      if(tft.textWidth(text)>700){text[n]=0;break;}n=next;
    }
    tft.unloadFont();if(!n)break;
    if(line==1&&source[n])strncat(text,"...",sizeof(text)-strlen(text)-1);
    dashText(text,40,y+35+line*27,712,18,INK);source+=n;
  }
}
void endWs43bErrorScreen(unsigned remaining) {
  char text[120];
  if(remaining)snprintf(text,sizeof(text),ws43bText("Dalsze komunikaty: %u · pełna lista w WebUI","More messages: %u · full list in WebUI"),remaining);
  else snprintf(text,sizeof(text),"%s",ws43bText("Dotknij, aby wrócić","Tap to return"));
  dashText(text,24,439,752,18,DIM);
}

void drawWs43bBootScreen() {
  applyWs43bPalette();
  tft.startWrite();
  startupScreen(ws43b_boot::Phase::Panel,nullptr,millis());
  small(ws43bText("Twój wydruk. Wszystko w jednym miejscu.",
                 "Your print. Everything in one place."),24,444,752,v2Dim());
  tft.endWrite();
}
void tickWs43bBootScreen() { animateStartupScreen(millis()); }


void cancelWs43bMonitorTouch() {
  if(touchHeld && (page==Page::Settings || page==Page::FactoryReset))painted=false;
  touchHeld = false;
  touchNeedsRelease = true;
}

void handleWs43bMonitorTouch(uint16_t x, uint16_t y, bool down) {
  const uint32_t now = millis();
  if (!isAnyPrinterConfigured() || isAPMode()) { cancelWs43bMonitorTouch(); return; }
  if (down) {
    coolingRecoveryPending=false;
    idlePolicy.activity(now);
    nightActivity=now;
    const bool revealNavigation = !navigationShown(now) && page != Page::Clock &&
                                  !automaticIdle && !screenOff;
    navigationActivity = now;
    if(revealNavigation && !touchHeld && !touchNeedsRelease) {
      painted=false; cancelWs43bMonitorTouch(); return;
    }
#if WS43B_FULL_WEBUI
    if (isNightModeActive()) nightWake();
    if (glowIsArmed()) glowDismiss();
#endif
  }
  if (down && (automaticIdle || screenOff)) {
    // The wake touch never activates the control underneath the finger.
    automaticIdle = false;
    if (screenOff) { screenOff = false; setBacklight(255); }
    page = Page::Dashboard;
    painted = false;
    cancelWs43bMonitorTouch();
    return;
  }
  if (touchNeedsRelease) { if (!down) touchNeedsRelease = false; return; }
  if (down) {
    if (x >= 800 || y >= 480) { cancelWs43bMonitorTouch(); return; }
    if (!touchHeld) { pressX = x; pressY = y; pressMs = now; touchMoved = false; }
    else if (abs(int(x) - int(pressX)) > 16 || abs(int(y) - int(pressY)) > 16) touchMoved = true;
    touchHeld = true;
    if((page==Page::FactoryReset || (page==Page::Settings && systemTouchArea(pressX,pressY))) && uint32_t(now-lastFrame)>=100)painted=false;
    return;
  }
  if (!touchHeld) return;
  touchHeld = false;
  const uint32_t duration = now - pressMs;
  if(page==Page::Settings && systemTouchArea(pressX,pressY)) {
    painted=false;
    bool allowed=true;
#if WS43B_FULL_WEBUI
    allowed=!hmsScreenAlerting();
#endif
    if(allowed && !touchMoved && duration>=3000 && systemTouchArea(x,y))page=Page::System;
    return;
  }
  if(page==Page::FactoryReset) {
    painted=false;
    bool resetAllowed=true;
#if WS43B_FULL_WEBUI
    resetAllowed=!hmsScreenAlerting();
#endif
    if(resetAllowed && !touchMoved && duration>=3000 && pressX>=44 && pressX<752 && pressY>=296 && pressY<356 &&
       x>=44 && x<752 && y>=296 && y<356) {
      cancelWs43bMonitorTouch();
      resetSettings();
      return;
    }
  }
  // Stay below the existing driver's 1000 ms stale-contact timeout: a lost
  // GT911 stream must not be interpreted as a release that saves a setting.
  if (touchMoved || duration < 40 || duration > 750) return;
#if WS43B_FULL_WEBUI
  // Dismiss an existing HMS overlay before routing the same tap underneath it.
  if(handleWs43bErrorTap(false)) { painted=false; return; }
#endif
  if(page==Page::Dashboard && ws43bWeatherConfig().enabled &&
     pressY<56 && pressX>=600 && pressX<694) {
    page=Page::Clock; painted=false; return;
  }
  if (page == Page::Clock && (!dispSettings.pongClock || ws43bWeatherConfig().enabled || ws43b_view::dryingUnit(displayedPrinter().state.monitor,isWiFiConnected()&&displayedPrinter().state.connected,now) || coolingView(displayedPrinter().state.monitor))) {
    page = Page::Dashboard; painted = false; return;
  }
  if(page==Page::FactoryReset) {
    if(pressX>=44&&pressX<752&&pressY>=374&&pressY<416)page=Page::System;
    painted=false;return;
  }
  if(page==Page::System) {
    if(pressX>=24&&pressX<264&&pressY>=82&&pressY<122)page=Page::Settings;
    else if(pressX>=44&&pressX<752&&pressY>=164&&pressY<220)page=Page::FactoryReset;
    painted=false;return;
  }
  if((page==Page::Dashboard?pressY<56&&pressX>=700:pressY<66&&pressX>=690)) { page=Page::Clock; painted=false; return; }
#if WS43B_FULL_WEBUI
  if(page==Page::Details && pressX>=600 && pressX<760 && pressY>=90 && pressY<120) {
    page=Page::Gauges; painted=false; return;
  }
  if (handleWs43bErrorTap(page==Page::Dashboard?pressY<56&&pressX>=216&&pressX<240:pressY<66&&pressX>=658&&pressX<690)) { painted = false; return; }
  if (page==Page::Dashboard?pressY<56&&pressX<216:pressY<80&&pressX<440) {
    for (uint8_t step = 1; step < MAX_ACTIVE_PRINTERS; ++step) {
      const uint8_t candidate = (rotState.displayIndex + step) % MAX_ACTIVE_PRINTERS;
      if (!isPrinterConfigured(candidate)) continue;
      rotState.displayIndex = candidate;
      rotState.lastRotateMs = now;
      rotState.displayHoldUntilMs = now + rotState.intervalMs;
      painted = false;
      return;
    }
  }
#endif
  if (pressY >= 435) {
    const int item=ws43b_view::navigationItem(pressX,pressY);
    const Page pages[]={Page::Dashboard,Page::Ams,Page::Details,Page::Settings};
    if(item<0) return;
    page=pages[item];
  } else if (page == Page::Clock) {
    page = Page::Dashboard;
  } else if(page==Page::Ams && pressY>=85 && pressY<125 && pressX>=550) {
    selectedAms=(selectedAms+1)%6;
  } else if(page==Page::WeatherSettings) {
    if(pressX>=44&&pressX<218&&pressY>=98&&pressY<134){page=Page::Settings;settingsNotice=nullptr;painted=false;return;}
    if(pressX<44||pressX>=752)return;
    auto c=ws43bWeatherConfig();
    if(pressY>=151&&pressY<199)c.enabled=!c.enabled;
    else if(pressY>=217&&pressY<265)c.solar=!c.solar;
    else if(pressY>=283&&pressY<331)c.nightSeconds=c.nightSeconds==30?60:c.nightSeconds==60?300:30;
    else return;
    settingsNotice=saveWs43bWeather(c)?ws43bText("Zapisano ustawienia.","Settings saved."):ws43bText("Wybierz miejscowosc w WebUI.","Choose location in WebUI.");
  } else if (page == Page::ClockSettings) {
    const auto &clock = ws43bClockSettings();
    uint16_t idle = clock.idleMinutes;
    bool off = clock.screenOff, use24h = clock.use24h;
    if (pressX >= 44 && pressX < 218 && pressY >= 98 && pressY < 134) {
      page = Page::Settings; painted = false; return;
    }
    if (pressX < 44 || pressX >= 752) return;
    if (pressY >= 151 && pressY < 199) {
      const uint16_t minutes[] = {0, 1, 5, 15, 30};
      for (unsigned i = 0; i < 5; ++i) if (idle == minutes[i]) { idle = minutes[(i + 1) % 5]; break; }
    } else if (pressY >= 217 && pressY < 265) off = !off;
    else if (pressY >= 283 && pressY < 331) use24h = !use24h;
    else return;
    settingsNotice = saveWs43bClockSettings(idle, off, use24h) ? ws43bText("Zapisano ustawienia zegara.", "Clock settings saved.") : ws43bText("Blad zapisu. Sprobuj ponownie.", "Save failed. Please retry.");
  } else if (page == Page::Settings) {
    if(pressX<24||pressX>=776||pressY<140||pressY>=386)return;
    const int x=pressX-24,y=pressY-140;
    if(x%384>=368 || y%132>=114)return;
    const Page destinations[]={Page::Appearance,Page::ClockSettings,Page::WeatherSettings,Page::GeneralSettings};
    page=destinations[(y/132)*2+x/384];settingsNotice=nullptr;
  } else if(page==Page::WebQr) {
    if(pressX>=24&&pressX<304&&pressY>=82&&pressY<122) {
      page=Page::GeneralSettings;painted=false;
    }
    return;
  } else if(page==Page::Appearance || page==Page::GeneralSettings) {
    if(pressX>=44&&pressX<218&&pressY>=98&&pressY<134) {
      page=Page::Settings;settingsNotice=nullptr;painted=false;return;
    }
    if(pressX<44||pressX>=752)return;
    if(page==Page::Appearance && pressY>=347&&pressY<393) {
      if(pressX>=264&&pressX<276)return;
      const bool saved=saveWs43bDisplayMode(pressX>=276);
      settingsNotice=saved?ws43bText("Zapisano tryb ekranu.","Display mode saved."):ws43bText("Blad zapisu. Sprobuj ponownie.","Save failed. Please retry.");
      painted=false;return;
    }
    if(page==Page::GeneralSettings && pressY>=283&&pressY<331) {
      page=Page::WebQr;painted=false;return;
    }
    if(page==Page::GeneralSettings && pressY>=151&&pressY<199) {
      const bool saved=saveWs43bLanguage(ws43bPolish()?1:0);
      settingsNotice=saved?ws43bText("Zapisano jezyk.","Language saved."):ws43bText("Blad zapisu. Sprobuj ponownie.","Save failed. Please retry.");
    } else {
      uint8_t theme=ws43bViewTheme();bool fanMatch=dispSettings.fanMatchPrinter;
      if(page==Page::Appearance && pressY>=151&&pressY<331 && (pressY-151)%66<48)theme=(pressY-151)/66;
      else if(page==Page::GeneralSettings && pressY>=217&&pressY<265)fanMatch=!fanMatch;
      else return;
      settingsNotice=saveWs43bViewSettings(theme,fanMatch)?ws43bText("Zapisano ustawienia panelu.","Panel settings saved."):ws43bText("Blad zapisu. Sprobuj ponownie.","Save failed. Please retry.");
    }
  } else return;
  painted = false;
}

bool ws43bVisibleDataNeedsRefresh(uint8_t slot,uint32_t now) {
  if(slot!=rotState.displayIndex||screenOff||isAPMode()||ws43b::otaDisplayActive())return false;
  const auto &s=displayedPrinter().state;
  return ws43b_live::needsRefresh(s.monitor,liveView(),liveAms(s.monitor),isWiFiConnected()&&s.connected,now);
}

void renderWs43bMonitor(bool force) {
  static bool otaWasActive=false;
  if(ws43b::otaDisplayActive()){otaWasActive=true;return;}
  if(otaWasActive){otaWasActive=false;painted=false;force=true;cancelWs43bMonitorTouch();}
  if (!settingsNotice && page!=Page::Appearance) settingsNotice = ws43bText("Zmiany dotycza tylko panelu.", "Changes affect this panel only.");
  static uint32_t languageRevision = 0;
  if (languageRevision != ws43bLanguageRevision()) {
    languageRevision = ws43bLanguageRevision();
    settingsNotice = ws43bText("Zapisano jezyk.", "Language saved.");
    painted = false;
  }
  static uint32_t displayModeRevision=0;
  if(displayModeRevision!=ws43bDisplayModeRevision()) {
    displayModeRevision=ws43bDisplayModeRevision();
    painted=false;
  }
  const uint32_t now = millis();
  if(page!=Page::Dashboard)startupVisible=false;
  static bool waterCached = false;
  updateIdleView(now);
  static ws43b_view::FinishCoolingPolicy coolingPolicies[MAX_ACTIVE_PRINTERS];
  const auto &coolingState=displayedPrinter().state;
  const bool observedCooling=coolingPolicies[rotState.displayIndex].update(coolingState.monitor,isWiFiConnected()&&coolingState.connected,now);
  const bool activeProgress=ws43b_view::activeJob(coolingState.monitor)&&
    ws43b_view::progressCurrent(coolingState.monitor,isWiFiConnected()&&coolingState.connected,now);
  const bool coolingNow=observedCooling&&(ws43bAdvancedDisplay()||!activeProgress);
  if(coolingNow!=dashboardCooling){dashboardCooling=coolingNow;painted=false;}
  if(dashboardActivity.update(ws43b_view::activity(coolingState.monitor,isWiFiConnected()&&coolingState.connected,now,coolingNow),now,coolingState.monitor.session,rotState.displayIndex))painted=false;
  bool nightDim=false;
#if WS43B_FULL_WEBUI
  nightDim=isNightModeActive() && !isAPMode() && isAnyPrinterConfigured() &&
           uint32_t(now-nightActivity)>=uint32_t(ws43bWeatherConfig().nightSeconds)*1000u;
#endif
  if(ws43b::setColorPercent(nightDim?30:100)) {
    painted=false;waterCached=false;force=true;
  }
#if WS43B_FULL_WEBUI
  if(glowConsumeCleanup())painted=false;
#endif
  static bool wasNavigation=true;
  const bool showNavigation=navigationShown(now);
  if(showNavigation!=wasNavigation && page!=Page::Clock) painted=false;
  wasNavigation=showNavigation;
  if (screenOff) return;
  // Drop decorative frames while readable telemetry is waiting. Never defer
  // a new screen/touch/alert; cap the pause so a busy stream still gets shown.
  if(ws43b_live::deferForRx(now,lastFrame,bambuMqttReceivePending(rotState.displayIndex),painted,force))return;
#if WS43B_FULL_WEBUI
  static bool pongWasActive = false;
  const bool pongActive = page == Page::Clock && !ws43b_view::beforeFirstLayer(coolingState.monitor,isWiFiConnected()&&coolingState.connected,now) && ws43b_view::pongAvailable(dispSettings.pongClock,dpSettings.keepDisplayOn,dpSettings.showClockAfterFinish) && dashboardActivity.state!=ws43b_view::Activity::Cleaning && dashboardActivity.state!=ws43b_view::Activity::Leveling && dashboardActivity.state!=ws43b_view::Activity::CalibrationLines && !ws43b_view::dryingUnit(coolingState.monitor,isWiFiConnected()&&coolingState.connected,now) && saverView(coolingState.monitor,isWiFiConnected()&&coolingState.connected,now)==ws43b_view::Saver::Print && !ws43bWeatherConfig().enabled && !coolingView(displayedPrinter().state.monitor) && (automaticIdle || getScreenState() != SCREEN_HMS);
  if (pongActive) {
    if (uint32_t(now - lastFrame) < 50 && painted && !force) return;
    tft.startWrite();
    ws43b::beginRenderDiagnostics(false); // Pong redraws deltas; do not probe-fill its first row.
    if (!pongWasActive || !painted || force) resetPongClock();
    tickPongClock();
    footer(displayedPrinter().state.monitor, now);
    tft.endWrite();
    ws43b::endRenderDiagnostics(true);
    pongWasActive = true; painted = true; lastFrame = now;
    return;
  }
  if (pongWasActive) { pongWasActive = false; painted = false; }
#endif
  static uint32_t drawnDataSignature=0;
  const uint32_t dataSignature=ws43b_live::signature(coolingState.monitor,liveView(),liveAms(coolingState.monitor),isWiFiConnected()&&coolingState.connected,now);
  const bool dataDue=ws43b_live::repaintDue(now,lastFrame,dataSignature,drawnDataSignature);
  if (painted && !force && !dataDue && uint32_t(now - lastFrame) < (page == Page::Clock ? 84u : 1000u)) {
    if(startupVisible){animateStartupScreen(now);return;}
    static ws43b_animation::Cadence animationCadence;
    bool animateWeather=page!=Page::Clock && weatherHeaderVisible && !(page==Page::Dashboard && dashboardCooling) && !isAPMode() && isAnyPrinterConfigured();
    bool animate=page==Page::Dashboard && dashboardActivity.animated(now) && (!dashboardCooling || dashboardCoolingPainted) && !isAPMode() && isAnyPrinterConfigured();
    bool animateDrying=page==Page::Ams && !isAPMode() && isAnyPrinterConfigured() &&
      amsDryingAnimated(coolingState.monitor,isWiFiConnected()&&coolingState.connected,now);
#if WS43B_FULL_WEBUI
    animate=animate && getScreenState()!=SCREEN_HMS;
    animateWeather=animateWeather && getScreenState()!=SCREEN_HMS;
    animateDrying=animateDrying && getScreenState()!=SCREEN_HMS;
#endif
    const bool cachedPrintHead=animate && !dashboardCooling &&
      dashboardActivity.state==ws43b_view::Activity::Printing && ws43b_native::heroHeadCacheReady();
    const auto animationFrame=animationCadence.due(now,lastFrame,animate,
      animateWeather||animateDrying,cachedPrintHead);
    if(animationFrame.activity||animationFrame.ambient) {
      tft.startWrite();ws43b::beginRenderDiagnostics(false);
      if(animationFrame.activity) {
        if(dashboardCooling)coolingScreen(displayedPrinter().state.monitor,isWiFiConnected()&&displayedPrinter().state.connected,now,true);
        else dashboardActivityIcon(now);
      }
      if(animationFrame.ambient && animateWeather)dashboardWeatherIcon(now);
      if(animationFrame.ambient && animateDrying)amsDryingAnimation(now);
      tft.endWrite();ws43b::endRenderDiagnostics(true);animationCadence.mark(now,animationFrame);
    }
    return;
  }
  const bool reuseWater = painted && !force;
  drawnDataSignature=dataSignature;
  painted = true; lastFrame = now;
  if (!isPrinterConfigured(rotState.displayIndex)) {
    for (uint8_t slot = 0; slot < MAX_ACTIVE_PRINTERS; ++slot)
      if (isPrinterConfigured(slot)) { rotState.displayIndex = slot; break; }
  }
  applyWs43bPalette();

  static char previousWaterKey[240] = {};
  bool waterVisible = page == Page::Clock && !isAPMode() && isAnyPrinterConfigured();
#if WS43B_FULL_WEBUI
  waterVisible = waterVisible && (getScreenState() != SCREEN_HMS || automaticIdle);
#endif
  if (waterVisible) {
    const auto &state = displayedPrinter().state;
    const auto &m = state.monitor;
    const bool online = isWiFiConnected() && state.connected;
    const bool valid = saverView(m,online,now)==ws43b_view::Saver::Print && clockHasProgress(m,online,now);
    const auto activity=ws43b_view::activity(m,online,now,false);
    const bool cleaning=saverView(m,online,now)==ws43b_view::Saver::Print && activity==ws43b_view::Activity::Cleaning;
    const bool leveling=saverView(m,online,now)==ws43b_view::Saver::Print && activity==ws43b_view::Activity::Leveling;
    const bool calibration=saverView(m,online,now)==ws43b_view::Saver::Print && activity==ws43b_view::Activity::CalibrationLines;
    const bool beforeStart=ws43b_view::beforeFirstLayer(m,online,now);
    const bool preparationScene=cleaning||leveling||calibration||beforeStart;
    const bool remaining = missing(m.remainingMinutes, online, now) == nullptr;
    struct tm clockTime{};
    const bool timeValid = getLocalTime(&clockTime, 0);
    char key[240];
    snprintf(key, sizeof(key), "p%d/r%d/%d/%u/%d/%u/%d/%d/%d/%d/%d/%d/%d/%lu",
             m.progress.valid, m.remainingMinutes.valid, valid, unsigned(m.progress.value), remaining, unsigned(m.remainingMinutes.value),
             timeValid, clockTime.tm_year, clockTime.tm_yday, clockTime.tm_hour, clockTime.tm_min,
             netSettings.use24h, int(rotState.displayIndex), (unsigned long)ws43bLanguageRevision());
    const bool cooling = saverView(m,online,now)==ws43b_view::Saver::Cooling;
    const bool coolingFresh = online && m.status.current(now) && m.bedTemp.current(now);
    const size_t nozzleUsed=strlen(key);
    snprintf(key+nozzleUsed,sizeof(key)-nozzleUsed,"/b%d/c%d/l%d/k%d/n%d/%.0f/%d/%.0f/%s",beforeStart,cleaning,leveling,calibration,online&&m.nozzleTemp.current(now),double(m.nozzleTemp.value),online&&m.nozzleTarget.current(now),double(m.nozzleTarget.value),m.status.value);
    const size_t used = strlen(key);
    snprintf(key + used, sizeof(key) - used, "/%d/%d/%.0f/%d/%.0f", cooling, coolingFresh,
             double(m.bedTemp.value), online && m.bedTarget.current(now), double(m.bedTarget.value));
    const auto weather=ws43bWeatherData();
    const auto weatherConfig=ws43bWeatherConfig();
    const size_t weatherUsed=strlen(key);
    snprintf(key+weatherUsed,sizeof(key)-weatherUsed,"/w%lu/%lu/%d",(unsigned long)weather.revision,(unsigned long)weatherConfig.revision,ws43b_weather::fresh(weather,time(nullptr)));
    const auto *drying=ws43b_view::dryingUnit(m,online,now);
    const bool dryingFresh=drying&&online&&drying->dryRemainMin.current(now);
    const size_t dryingUsed=strlen(key);
    snprintf(key+dryingUsed,sizeof(key)-dryingUsed,"/d%d/%d/%u/s%d/a%lu",drying?int(drying->id):-1,dryingFresh,drying?unsigned(drying->dryRemainMin.value):0,int(saverView(m,online,now)),drying&&!dryingFresh?(unsigned long)(uint32_t(now-drying->dryRemainMin.updatedMs)/60000u):0UL);
    if(drying) {
      const size_t n=strlen(key);
      snprintf(key+n,sizeof(key)-n,"/t%d/%.0f/h%d/%u",online&&drying->temp.current(now),double(drying->temp.value),online&&drying->humidityRaw.current(now),unsigned(drying->humidityRaw.value));
    }
    const size_t sessionUsed=strlen(key);
    snprintf(key+sessionUsed,sizeof(key)-sessionUsed,"/q%lu/%d/%d",(unsigned long)m.session,online,ws43b_view::statusCurrent(m,online,now));
    const size_t activityUsed=strlen(key);
    snprintf(key+activityUsed,sizeof(key)-activityUsed,"/v%d/m%d",int(activity),ws43bAdvancedDisplay());
    const bool partial = reuseWater && waterCached && !strcmp(key, previousWaterKey);
    // No wave at endpoints or when progress is missing: preserve the static frame.
    if (partial && !preparationScene && !dryingFresh && !(weatherConfig.enabled && !drying && !cooling) && (cooling ? !coolingFresh : (!valid || m.progress.value == 0 || m.progress.value >= 100))) return;
    tft.startWrite();
    ws43b::beginRenderDiagnostics(!partial);
    tft.unloadFont();
    tft.setTextSize(1);
    clockScreen(m, online, now, partial);
    tft.endWrite();
    ws43b::endRenderDiagnostics(true);
    snprintf(previousWaterKey, sizeof(previousWaterKey), "%s", key);
    waterCached = true;
    return;
  }
  waterCached = false;
  const bool wifi = isWiFiConnected();
  const bool ap = isAPMode();
  const auto &slot = displayedPrinter();
  const auto &s = slot.state;
  const auto &m = s.monitor;
  const bool online = wifi && s.connected;
  const bool useful = online && m.hasUsefulData && uint32_t(now - m.lastUsefulMs) <= BAMBU_MONITOR_FRESH_MS;
  static bool receivedTelemetry=false;
  receivedTelemetry=receivedTelemetry||useful;

  // Keep the base canvas between telemetry frames. Only changed visible groups
  // are repainted; field timestamps and MQTT scheduling remain independent.
  using R=ws43b_repaint::Region;
  static ws43b_repaint::Cache repaint;
  static uint32_t previousPresentation=0;
  bool regional=!ap && isAnyPrinterConfigured() &&
    (page==Page::Ams || page==Page::Details || (page==Page::Dashboard && receivedTelemetry && !dashboardCooling));
#if WS43B_FULL_WEBUI
  regional=regional && getScreenState()!=SCREEN_HMS && !glowIsArmed();
#endif
  uint32_t presentation=2166136261u;
  ws43b_repaint::add(presentation,page);
  ws43b_repaint::add(presentation,rotState.displayIndex);
  ws43b_repaint::addText(presentation,slot.config.name);
  ws43b_repaint::add(presentation,ws43bLanguageRevision());
  ws43b_repaint::add(presentation,netSettings.use24h);
  ws43b_repaint::add(presentation,ws43bAdvancedDisplay());
  ws43b_repaint::add(presentation,dispSettings.fanMatchPrinter);
  for(const uint16_t color:{BG,TRACK,ACCENT,INK,DIM,GREEN})ws43b_repaint::add(presentation,color);
  auto keys=ws43b_repaint::keys(m,liveView(),liveAms(m),online,now);
  auto &headerKey=keys[static_cast<unsigned>(R::Header)];
  auto &primaryKey=keys[static_cast<unsigned>(R::Primary)];
  struct tm minute{};
  const bool clockValid=getLocalTime(&minute,0);
  uint32_t clockKey=2166136261u;
  ws43b_repaint::add(clockKey,clockValid);
  if(clockValid) {
    ws43b_repaint::add(clockKey,minute.tm_year);ws43b_repaint::add(clockKey,minute.tm_yday);
    ws43b_repaint::add(clockKey,minute.tm_hour);ws43b_repaint::add(clockKey,minute.tm_min);
  }
  ws43b_repaint::add(headerKey,clockKey);ws43b_repaint::add(primaryKey,clockKey);
  const auto weather=ws43bWeatherData();
  const auto weatherConfig=ws43bWeatherConfig();
  ws43b_repaint::add(headerKey,weather.revision);
  ws43b_repaint::add(headerKey,weatherConfig.revision);
  ws43b_repaint::add(headerKey,ws43b_weather::fresh(weather,time(nullptr)));
  ws43b_repaint::add(headerKey,dashboardWeatherNight(weather));
  const bool partial=regional && reuseWater && repaint.valid && presentation==previousPresentation;
  const auto regions=repaint.dirty(keys,!partial);
  if(!regional)repaint.invalidate();
  if(partial && !regions) {
#if WS43B_FULL_WEBUI
    // A newly latched alert can start without changing any telemetry group.
    tft.startWrite();ws43b::beginRenderDiagnostics(false);
    glowTick(tft,rotState.displayIndex,false);
    if(glowConsumeCleanup())painted=false;
    tft.endWrite();ws43b::endRenderDiagnostics(true);
#endif
    return;
  }
  tft.startWrite();
  // The diagnostics fill probe is allowed only before a complete canvas clear.
  ws43b::beginRenderDiagnostics(!partial);
  tft.unloadFont();
  tft.setTextSize(1);
  if(!partial) {
    startupVisible=false;
    const bool startupCanvas=ap || !isAnyPrinterConfigured() || (!receivedTelemetry && page==Page::Dashboard);
    if(!startupCanvas) {
      if(page==Page::Dashboard&&!dashboardCooling)ws43b_native::screen(tft,BG);
      else tft.fillScreen(BG);
    }
    weatherHeaderVisible=false;
  }
#if WS43B_FULL_WEBUI
  if (getScreenState() == SCREEN_HMS && !automaticIdle) {
    drawWs43bHmsScreen();
    tft.endWrite();
    ws43b::endRenderDiagnostics(true);
    return;
  }
#endif
  if (ap || !isAnyPrinterConfigured()) {
    setupScreen(ap, wifi);
    tft.endWrite();
    ws43b::endRenderDiagnostics(false);
    return;
  }

  if(!receivedTelemetry && page==Page::Dashboard) {
    const String context=wifi?String(slot.config.name):WiFi.SSID();
    startupScreen(ws43b_boot::connectionPhase(wifi,online),context.c_str(),now);
    footer(m,now);
    tft.endWrite();ws43b::endRenderDiagnostics(true);return;
  }
  if (page == Page::Clock) {
    clockScreen(m, online, now);
    tft.endWrite();
    ws43b::endRenderDiagnostics(true);
    return;
  }
  if(page==Page::Dashboard && dashboardCooling) {
    coolingScreen(m,online,now,false);footer(m,now);dashboardCoolingPainted=true;
    tft.endWrite();ws43b::endRenderDiagnostics(true);return;
  }
  if(regions&ws43b_repaint::regionBit(R::Header)) {
  if(partial) {
    if(page==Page::Dashboard)v2Clear(0,0,800,56);
    else tft.fillRect(0,0,800,80,BG);
  }
  const char *headerStatus=statusText(m.status,online,now);
  if(ws43b_view::statusCurrent(m,online,now) && !m.status.current(now))
    headerStatus=!strcmp(m.status.value,"RUNNING")?ws43bText("Drukowanie","Printing"):ws43bText("Przygotowanie","Preparing");
  if(ws43b_view::beforeFirstLayer(m,online,now))headerStatus=ws43bText("Przygotowanie","Preparing");
  if(page==Page::Dashboard) {
    switch(monitorFilamentStage(m,online,now)) {
      case 4:headerStatus=ws43bText("Zmiana filamentu","Changing filament");break;
      case 22:headerStatus=ws43bText("Wyładowywanie filamentu","Unloading filament");break;
      case 24:headerStatus=ws43bText("Ładowanie filamentu","Loading filament");break;
    }
  }
  if(page==Page::Dashboard && dashboardActivity.state==ws43b_view::Activity::CalibrationLines)
    headerStatus=ws43bText("Linie kalibracyjne","Calibration lines");
  if(page==Page::Dashboard && dashboardActivity.state==ws43b_view::Activity::Leveling)
    headerStatus=ws43bText("Poziomowanie stołu","Bed leveling");
  if(page==Page::Dashboard && dashboardActivity.state==ws43b_view::Activity::Cleaning)
    headerStatus=ws43bText("Czyszczenie dyszy","Cleaning nozzle");
  // Receiving one temperature must not make an expired print state look current.
  const bool statusCurrent = ws43b_view::statusCurrent(m,online,now);
  const bool activePrint = statusCurrent && (!strcmp(m.status.value,"RUNNING") ||
      !strcmp(m.status.value,"PREPARE") || !strcmp(m.status.value,"PAUSE"));
  const bool printCurrent = useful && statusCurrent && (!activePrint || ws43b_view::progressCurrent(m,online,now));
  const uint16_t dataColor=!online?RED:printCurrent?(GREEN==CLR_GREEN?v2Accent():GREEN):WARN;
  char header[80];struct tm local{};
  if(getLocalTime(&local,0))snprintf(header,sizeof(header),"%02d:%02d",netSettings.use24h?local.tm_hour:(local.tm_hour%12?local.tm_hour%12:12),local.tm_min);
  else snprintf(header,sizeof(header),"--:--");
  if(page==Page::Dashboard) {
    v2Text(slot.config.name[0]?slot.config.name:"BambuHelper",20,16,180,ws43b_v2_b25,25,v2Ink());
    tft.fillCircle(220,31,4,dataColor);
    v2Text(headerStatus,232,24,362,ws43b_v2_b14,14,!online?v2Dim():statusCurrent?v2Ink():WARN);
    tft.drawFastVLine(701,19,25,ws43b_native::line);
    if(netSettings.use24h || !getLocalTime(&local,0))v2Text(header,705,17,76,ws43b_v2_b25,25,v2Ink(),true,false);
    else {
      snprintf(header,sizeof(header),"%02d:%02d %s",local.tm_hour%12?local.tm_hour%12:12,local.tm_min,local.tm_hour<12?"AM":"PM");
      v2Text(header,705,24,76,ws43b_v2_b14,14,v2Ink(),true,false);
    }
    menuWeatherHeader(now);
    tft.drawFastHLine(16,55,768,ws43b_native::line);
  } else {
    dashText(slot.config.name[0]?slot.config.name:"BambuHelper",24,24,190,30,INK);
    dashText(headerStatus,224,31,290,18,!online?DIM:statusCurrent?ACCENT:WARN);
    tft.fillCircle(672,37,5,!online?RED:printCurrent?GREEN:WARN);
    dashText(header,697,24,79,24,INK);
    menuWeatherHeader(now);
    tft.drawFastHLine(24,66,752,TRACK);
  }
  }

  if (page != Page::Dashboard) {
#if WS43B_FULL_WEBUI
    if (page == Page::Gauges) gaugesScreen(slot, online, now);
    else
#endif
    if (page == Page::Ams) amsView(m,online,now,true,regions);
    else if (page == Page::Details) {
      if(regions&ws43b_repaint::regionBit(R::DetailsBody)) {
        if(partial)tft.fillRect(24,84,752,340,BG);
        detailsScreen(m, online, now);
      }
    }
    else if (page == Page::ClockSettings) clockSettingsScreen();
    else if (page == Page::WeatherSettings) weatherSettingsScreen();
    else if(page==Page::Appearance)appearanceSettingsScreen();
    else if(page==Page::GeneralSettings)generalSettingsScreen();
    else if(page==Page::WebQr)webQrScreen();
    else if(page==Page::System)systemSettingsScreen();
    else if(page==Page::FactoryReset)factoryResetScreen(now);
    else settingsScreen();
    if(!partial)footer(m, now);
    if(regional) {repaint.commit(keys);previousPresentation=presentation;}
#if WS43B_FULL_WEBUI
    glowTick(tft, rotState.displayIndex, true);
    if(glowConsumeCleanup())painted=false;
#endif
    tft.endWrite();
    ws43b::endRenderDiagnostics(true);
    return;
  }

  dashboardScreen(m,online,now,regions);
  if(!partial)footer(m, now);
  if(regional) {repaint.commit(keys);previousPresentation=presentation;}
#if WS43B_FULL_WEBUI
  glowTick(tft, rotState.displayIndex, true);
  if(glowConsumeCleanup())painted=false;
#endif
  tft.endWrite();
  ws43b::endRenderDiagnostics(true);
}
#endif
