#pragma once
#include "ws43b_ui_icons.h"
#include "ws43b_version.h"

// Shared startup composition: production assets, palette and fonts via Text.
// Stages represent observed connection state, never an estimated percentage.
namespace ws43b_boot {
enum class Phase : uint8_t { Panel, Wifi, Printer, Data };
struct Palette { uint16_t background, accent, ink, dim; };
inline Phase connectionPhase(bool wifi,bool mqtt) {
  return !wifi?Phase::Wifi:!mqtt?Phase::Printer:Phase::Data;
}
inline const char *title(Phase phase,bool pl,bool de=false) {
  switch(phase) {
    case Phase::Panel:return pl?"Przygotowywanie panelu":de?"Panel wird vorbereitet":"Preparing the panel";
    case Phase::Wifi:return pl?"Łączenie z Wi-Fi":de?"Verbindung mit WLAN":"Connecting to Wi-Fi";
    case Phase::Printer:return pl?"Łączenie z drukarką":de?"Verbindung zum Drucker":"Connecting to printer";
    default:return pl?"Oczekiwanie na dane":de?"Warten auf Druckerdaten":"Waiting for printer data";
  }
}
inline const char *subtitle(Phase phase,bool pl,bool de=false) {
  switch(phase) {
    case Phase::Panel:return pl?"Za chwilę pojawi się Twój panel.":de?"Deine Übersicht erscheint in Kürze.":"Your dashboard will appear shortly.";
    case Phase::Wifi:return pl?"Nawiązywanie połączenia z zapisaną siecią.":de?"Verbindung zum gespeicherten WLAN.":"Connecting to the saved network.";
    case Phase::Printer:return pl?"Panel jest w sieci. Oczekiwanie na drukarkę.":de?"Panel ist online. Warten auf den Drucker.":"Panel is online. Waiting for the printer.";
    default:return pl?"Połączono. Oczekiwanie na pierwsze odczyty.":de?"Verbunden. Warte auf erste Messwerte.":"Connected. Waiting for the first readings.";
  }
}
// Only this 72x16 region changes between connection updates. No framebuffer,
// allocation or whole-screen animation; exact background restoration avoids trails.
template<class Canvas> void animate(Canvas &c,uint32_t now,const Palette &p) {
  ws43b_native::gradientRect(c,246,291,72,16,[&](int x,int y) {
    return ws43b_native::cardbg(x,y,84,252,p.background);
  });
  for(unsigned i=0;i<3;++i) {
    const unsigned phase=(now/80u+30u-i*5u)%30u;
    const unsigned strength=phase<15u?phase:30u-phase;
    const uint16_t color=ws43b_native::mix(ws43b_native::line,p.accent,48u+strength*13u);
    c.fillCircle(254+int(i)*24,299,3,color);
  }
}
template<class Canvas,class Text>
void draw(Canvas &c,Text text,Phase phase,const Palette &p,bool pl,
          const char *context,uint32_t now,bool de=false) {
  using namespace ws43b_native;
  screen(c,p.background);
  text("BambuHelper " WS43B_DISPLAY_VERSION,24,19,400,25,p.ink);
  text(pl?"URUCHAMIANIE":de?"STARTET":"STARTING UP",602,28,174,14,p.dim);
  c.drawFastHLine(24,62,752,line);
  card(c,24,84,752,252,p.background);
  const auto icon=phase==Phase::Wifi?ws43b_assets::Asset::Network:
    phase==Phase::Data?ws43b_assets::Asset::Details:ws43b_assets::Asset::Printer;
  ws43b_ui_icons::draw(c,icon,136,206,96,[&](int x,int y) {
    return cardbg(x,y,84,252,p.background);
  });
  text(pl?"TWÓJ PANEL DRUKARKI":de?"DEINE DRUCKERÜBERSICHT":"YOUR PRINTER DASHBOARD",246,113,496,14,p.accent);
  text(title(phase,pl,de),246,153,496,25,p.ink);
  text(subtitle(phase,pl,de),246,203,496,17,p.dim);
  if(context&&*context)text(context,246,246,496,17,p.ink);
  animate(c,now,p);
  const char *labelsPl[]={"Panel","Wi-Fi","Drukarka","Dane"};
  const char *labelsEn[]={"Panel","Wi-Fi","Printer","Data"};
  const char *labelsDe[]={"Panel","WLAN","Drucker","Daten"};
  for(unsigned i=0;i<4;++i) {
    const int x=24+int(i)*190;
    const bool done=i<unsigned(phase),active=i==unsigned(phase);
    card(c,x,360,182,60,p.background);
    if(active)c.drawRoundRect(x,360,182,60,12,mix(line,p.accent,150));
    const uint16_t color=(done||active)?p.accent:p.dim;
    c.drawCircle(x+24,390,9,done||active?color:line);
    if(done) {
      c.drawLine(x+19,390,x+23,394,color);
      c.drawLine(x+23,394,x+29,386,color);
    } else if(active)c.fillCircle(x+24,390,3,color);
    text(pl?labelsPl[i]:de?labelsDe[i]:labelsEn[i],x+43,382,129,17,active?p.ink:color);
  }
}
} // namespace ws43b_boot
