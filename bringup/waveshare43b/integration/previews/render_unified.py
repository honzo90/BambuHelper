"""Host review of actual dashboard/AMS render functions, synthetic data only.
Text uses the firmware VLW glyph masks and advances. Host shapes and hardware blending may differ.
"""
from pathlib import Path
import subprocess,tempfile,re,struct
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[4]
SRC=(ROOT/'src/display_ws43b.cpp').read_text()
def section(a,b):return SRC[SRC.index(a):SRC.index(b,SRC.index(a))]
PRE=r'''
#include "bambu_monitor.h"
#include "ws43b_dashboard_policy.h"
#include "ws43b_style.h"
#include "ws43b_print_scene.h"
#include "ws43b_drying_scene.h"
#include "ws43b_repaint_plan.h"
#include <cstdio>
#include <cstring>
#include <cmath>
#include <ctime>
#include <algorithm>
constexpr int BG=ws43b_style::background,CARD=ws43b_style::card,INK=ws43b_style::ink,DIM=ws43b_style::dim,TRACK=ws43b_style::border,ACCENT=ws43b_style::mint,WARN=0xf5cb,RED=0xf38f,GREEN=ACCENT;
#define MAX_ACTIVE_PRINTERS 1
struct{int displayIndex=0;}rotState;
const char *ws43bText(const char *pl,const char*){return pl;}
struct Canvas{
 void setClipRect(int,int,int,int){}void clearClipRect(){}
 void fillRect(int x,int y,int w,int h,int c){printf("rect %d %d %d %d %d\n",x,y,w,h,c);}
 void drawRect(int x,int y,int w,int h,int c){printf("box %d %d %d %d %d\n",x,y,w,h,c);}
 void fillRoundRect(int x,int y,int w,int h,int r,int c){printf("round %d %d %d %d %d %d\n",x,y,w,h,r,c);}
 void drawRoundRect(int x,int y,int w,int h,int r,int c){printf("outline %d %d %d %d %d %d\n",x,y,w,h,r,c);}
 void fillEllipse(int x,int y,int rx,int ry,int c){printf("ellipse %d %d %d %d %d\n",x,y,rx,ry,c);}
 void drawEllipse(int x,int y,int rx,int ry,int c){printf("ring %d %d %d %d %d\n",x,y,rx,ry,c);}
 void fillCircle(int x,int y,int r,int c){fillEllipse(x,y,r,r,c);}void drawCircle(int x,int y,int r,int c){drawEllipse(x,y,r,r,c);}
 void drawLine(int x,int y,int xx,int yy,int c){printf("line %d %d %d %d %d\n",x,y,xx,yy,c);}
 void drawFastHLine(int x,int y,int w,int c){drawLine(x,y,x+w-1,y,c);}void drawFastVLine(int x,int y,int h,int c){drawLine(x,y,x,y+h-1,c);}
 void fillTriangle(int x,int y,int xx,int yy,int xxx,int yyy,int c){printf("triangle %d %d %d %d %d %d %d\n",x,y,xx,yy,xxx,yyy,c);}
 void drawTriangle(int x,int y,int xx,int yy,int xxx,int yyy,int c){drawLine(x,y,xx,yy,c);drawLine(xx,yy,xxx,yyy,c);drawLine(xxx,yyy,x,y,c);}
 void drawPixel(int x,int y,int c){fillRect(x,y,1,1,c);}
}tft;
void dashText(const char *s,int x,int y,int w,int size=18,int c=INK){printf("text %d %d %d %d %d|%s\n",x,y,w,size,c,s?s:"");}
void button(const char*s,int x,int y,int w,int h,bool a){tft.fillRoundRect(x,y,w,h,9,CARD);tft.drawRoundRect(x,y,w,h,9,a?ACCENT:TRACK);dashText(s,x+12,y+(h-20)/2,w-24,18,a?ACCENT:INK);}
bool touchHeld=false,touchMoved=false;unsigned pressX=0,pressY=0,pressMs=0;
unsigned millis(){return 100;}
bool systemTouchArea(unsigned x,unsigned y){return x>=660&&x<776&&y>=82&&y<124;}
const char *settingsNotice="Zmiany dotyczą tylko panelu.";
unsigned ws43bViewTheme(){return 0;}bool ws43bPolish(){return true;}
struct{bool fanMatchPrinter=true;}dispSettings;
struct{bool nightModeEnabled=true;}dpSettings;
struct Clock{unsigned idleMinutes=1;bool screenOff=false,use24h=true;};
Clock ws43bClockSettings(){return {};}
struct Weather{bool enabled=true,solar=true;unsigned nightSeconds=60;const char*city="Schanbach";};
Weather ws43bWeatherConfig(){return {};}

void small(const char*s,int x,int y,int w,int c=DIM){dashText(s,x,y,w,14,c);}
unsigned selectedAms=0;bool dashboardCooling=false,dashboardCoolingPainted=false;int dashboardProgressEdge=24;
ws43b_view::ActivityClock dashboardActivity;
struct{struct{BambuMonitorTelemetry monitor;bool connected=true;}state;}slot;
auto &displayedPrinter(){return slot;}bool isWiFiConnected(){return true;}
bool getLocalTime(tm *t,int){*t={};t->tm_hour=20;t->tm_min=4;return true;}
void dashboardCoolingCard(const BambuMonitorTelemetry&,unsigned,bool){}
'''
parts=[section('template <class Field>\nconst char *missing','void temperature('),section('const char *statusText(','void detailCard('),section('void levelCard(','void dashboardTemperature('),section('void dashboardTemperature(','// Solar data'),section('uint16_t saverFilamentColor(const BambuMonitorTelemetry &m','void saverAnimation('),section('void dashboardActivityIcon(','void dashboardCoolingCard('),section('void dashboardScreen(','void detailsScreen('),section('void settingRow(','void connectedWifiName('),section('void clockSettingsScreen()','#if WS43B_FULL_WEBUI\nbool gaugeDataFresh')]
parts=[p.replace('time(nullptr)', 'time_t(1791741840)') for p in parts]
END=r'''
int main(int argc,char**argv){
 auto &m=slot.state.monitor;m.hasUsefulData=true;m.lastUsefulMs=100;
 m.status.set("RUNNING",100);m.progress.set(68,100);m.remainingMinutes.set(92,100);
 m.subtaskName.set("CyberBrick Official Standard Remote",100);m.layerNum.set(86,100);m.totalLayers.set(291,100);
 m.nozzleTemp.set(250,100);m.nozzleTarget.set(250,100);m.bedTemp.set(70,100);m.bedTarget.set(70,100);m.chamberTemp.set(41,100);
 auto &u=m.amsUnits[0];u.used=true;u.temp.set(40,100);u.humidityRaw.set(14,100);u.dryRemainMin.set(0,100);
 u.trays[0].type.set("ASA",100);u.trays[0].colorRgb565.set(0,100);
 u.trays[1].type.set("PETG Basic",100);u.trays[1].colorRgb565.set(0x87e3,100);u.trays[1].remain.set(89,100);
 u.trays[3].type.set("PETG",100);u.trays[3].colorRgb565.set(0xffff,100);m.activeTrayRaw.set(1,100);
 dashboardActivity.update(ws43b_view::Activity::Printing,100,0,0);
 dashText("Bambu P2S",24,24,190,30,INK);dashText(argc>1&&!strcmp(argv[1],"cleaning")?"Czyszczenie dyszy":argc>1&&!strcmp(argv[1],"leveling")?"Poziomowanie stołu":argc>1&&!strcmp(argv[1],"calibration")?"Linie kalibracyjne":"Drukowanie",224,31,290,18,ACCENT);dashText("20:04",697,24,79,24,INK);
 tft.drawFastHLine(24,66,752,TRACK);
 if(argc>1&&!strcmp(argv[1],"stale")) {
   m.lastUsefulMs=240100;m.status.set("RUNNING",240100);m.progress.set(93,240100);
   m.layerNum.set(221,240100);m.remainingMinutes.set(17,240100);
   dashboardScreen(m,true,240100);
 }
 else if(argc>1&&(!strcmp(argv[1],"cleaning")||!strcmp(argv[1],"leveling")||!strcmp(argv[1],"calibration"))) {
   m.printStage.set(!strcmp(argv[1],"calibration")?51:!strcmp(argv[1],"leveling")?1:14,100);m.progress.set(0,100);m.remainingMinutes.set(81,100);
   m.subtaskName.set("GORAL V2 Low Ratio Gearbox",100);m.layerNum.set(0,100);
   m.nozzleTemp.set(!strcmp(argv[1],"leveling")?140:187,100);m.nozzleTarget.set(!strcmp(argv[1],"leveling")?140:165,100);
   dashboardActivity.update(ws43b_view::activity(m,true,100,false),100,0,0);
   dashboardScreen(m,true,!strcmp(argv[1],"calibration")?6800:1350);
 }
 else if(argc>1&&!strcmp(argv[1],"settings"))settingsScreen();
 else if(argc>1&&!strcmp(argv[1],"appearance"))appearanceSettingsScreen();
 else if(argc>1&&!strcmp(argv[1],"language"))generalSettingsScreen();
 else if(argc>1&&!strcmp(argv[1],"system"))systemSettingsScreen();
 else if(argc>1&&!strcmp(argv[1],"reset"))factoryResetScreen(100);
 else if(argc>1&&!strcmp(argv[1],"clock"))clockSettingsScreen();
 else if(argc>1&&!strcmp(argv[1],"weather"))weatherSettingsScreen();
 else if(argc>1)amsView(m,true,100,true);else dashboardScreen(m,true,100);
 const char*names[]={"Wydruk","AMS","Szczegóły","Ustawienia"};
 const ws43b_style::Icon icons[]={ws43b_style::Icon::Printer,ws43b_style::Icon::Spool,ws43b_style::Icon::Details,ws43b_style::Icon::Settings};
 const int selected=argc==1||!strcmp(argv[1],"stale")||!strcmp(argv[1],"cleaning")||!strcmp(argv[1],"leveling")||!strcmp(argv[1],"calibration")?0:!strcmp(argv[1],"ams")?1:3;
 tft.drawFastHLine(24,433,752,TRACK);
 for(int i=0;i<4;++i){int x=24+190*i;const bool active=i==selected;
 if(active)ws43b_style::navigationSelection(tft,x,ACCENT,CARD);
 ws43b_style::icon(tft,icons[i],x+21,454,active?ACCENT:DIM);dashText(names[i],x+46,445,130,18,active?INK:DIM);
 }
}
'''
# Decode the actual linked firmware font bytes rather than substitute a TTF.
FONTS={}
for name,table in re.findall(r'const uint8_t (\w+)\[\].*?\{(.*?)\};',(ROOT/'include/fonts/ws43b_modern.h').read_text(),re.S):
 data=bytes(int(v,16) for v in re.findall(r'0x([0-9a-f]{2})',table))
 n,version,size,_,asc,desc=struct.unpack_from('>6I',data);offset=24+n*28;glyphs={}
 for i in range(n):
  cp,h,w,advance,dy,dx,_=struct.unpack_from('>IIIIiiI',data,24+i*28)
  glyphs[chr(cp)]=(h,w,advance,dy,dx,data[offset:offset+w*h]);offset+=w*h
 FONTS[name]=(asc,glyphs)
def font_for(size):
 return FONTS['ws43b_dash_large' if size==72 else f'ws43b_dash_{size}']
def firmware_text(im,text,x,y,width,size,color):
 asc,glyphs=font_for(size);scale=1
 def length(t):return sum(glyphs.get(ch,(0,0,0,0,0,b''))[2]*scale for ch in t)
 if size==72 and length(text)>width:
  asc,glyphs=font_for(30);scale=2
 if length(text)>width:
  while text and length(text+'...')>width:text=text[:-1]
  text+='...'
 layer=Image.new('RGBA',(width,size+10))
 cursor=0
 for ch in text:
  h,w,advance,dy,dx,pixels=glyphs.get(ch,(0,0,0,0,0,b''))
  if w and h:
   mask=Image.frombytes('L',(w,h),pixels).resize((w*scale,h*scale),Image.Resampling.NEAREST)
   layer.paste(color,(cursor+dx*scale,(asc-dy)*scale),mask)
  cursor+=advance*scale
 layer=layer.resize((width*2,(size+10)*2),Image.Resampling.NEAREST)
 im.paste(layer,(x*2,y*2),layer)
def color(c):return ((c>>11)*255//31,((c>>5)&63)*255//63,(c&31)*255//31)
def render(ops,path):
 im=Image.new('RGB',(1600,960),color(0x0084));d=ImageDraw.Draw(im)
 for line in ops.splitlines():
  left,_,text=line.partition('|');args=left.split();op=args[0];v=list(map(int,args[1:]));c=color(v[-1]);v=v[:-1]
  if op=='text':
   x,y,w,size=v;firmware_text(im,text,x,y,w,size,c);continue
  if op in ('ellipse','ring'):
   x,y,rx,ry=v;box=((x-rx)*2,(y-ry)*2,(x+rx)*2,(y+ry)*2);d.ellipse(box,fill=c if op=='ellipse' else None,outline=c,width=2)
  elif op=='triangle':d.polygon(tuple((v[i]*2,v[i+1]*2) for i in (0,2,4)),fill=c)
  elif op=='line':d.line(tuple(n*2 for n in v),fill=c,width=2)
  else:
   x,y,w,h=v[:4];box=(x*2,y*2,(x+w-1)*2,(y+h-1)*2)
   if w<=0 or h<=0:continue
   if op in ('round','outline'):d.rounded_rectangle(box,radius=v[4]*2,fill=c if op=='round' else None,outline=c,width=2)
   else:d.rectangle(box,fill=c if op=='rect' else None,outline=c,width=2)
 im.resize((800,480),Image.Resampling.LANCZOS).save(path)
def main():
 out=Path(__file__).parent
 with tempfile.TemporaryDirectory() as temp:
  p=Path(temp);(p/'draw.cpp').write_text(PRE+'\n'.join(parts)+END)
  subprocess.run(['clang++','-std=c++17','-I',str(ROOT/'include'),str(p/'draw.cpp'),'-o',str(p/'draw')],check=True)
  for name,args in [('print',[]),('cleaning',['cleaning']),('leveling',['leveling']),('calibration',['calibration']),('stale',['stale']),('ams',['ams']),*[(name,[name]) for name in ['settings','appearance','language','system','reset','clock','weather']]]:render(subprocess.check_output([str(p/'draw'),*args],text=True),out/(name+'-native-layout.png'))
if __name__=='__main__':main()
