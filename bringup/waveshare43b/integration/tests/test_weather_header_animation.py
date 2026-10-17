"""Exercise production header patches and icon animation for both header layouts."""
from pathlib import Path
import subprocess, tempfile, unittest
ROOT = Path(__file__).resolve().parents[4]

class WeatherHeaderAnimation(unittest.TestCase):
 def test_actual_patch_bounds_motion_and_missing_data(self):
  source = (ROOT/'src/display_ws43b.cpp').read_text()
  function = source[source.index('bool weatherHeaderVisible=false;'):source.index('bool dashboardCooling=false')]
  clear = source[source.index('void v2Clear('):source.index('int v2Text(')]
  code = r'''
#include "ws43b_weather_icons.h"
#include "fonts/ws43b_dashboard_v2.h"
#include <cassert>
#include <ctime>
#include <cstdio>
#include <string>
#include <set>
#include <utility>
#include <algorithm>
#include <array>
namespace lgfx {using rgb565_t=uint16_t;}
#include "ws43b_native_scene.h"
namespace ws43b_weather {
 struct Data{bool valid=true;int code=61;float temperature=8;};
 bool fresh(const Data& d,time_t){return d.valid;}
}
enum class Page {Dashboard,Ams,Details,Settings};Page page=Page::Dashboard;
ws43b_weather::Data data;
struct Config{bool enabled=true;}config;
auto ws43bWeatherData(){return data;}auto ws43bWeatherConfig(){return config;}
bool dashboardWeatherNight(const ws43b_weather::Data&){return false;}
constexpr int BG=0x0084,INK=0xf7be,WARN=0xf5cb,DIM=0x9d34,FONT_NONE=0;
uint16_t v2Ink(){return INK;}uint16_t v2Dim(){return DIM;}
std::string label;int labelColor=0;
void dashText(const char*s,int x,int y,int w,int size,int color){
 assert(page!=Page::Dashboard&&x==563&&y==24&&w==94&&size==24);label=s;labelColor=color;
}
int v2Text(const char*s,int x,int y,int w,const uint8_t *font,int size,int color,bool right,bool fit){
 assert(page==Page::Dashboard&&x==646&&w==48&&right&&!fit);
 assert((font==ws43b_v2_b17&&size==17&&y==22)||(font==ws43b_v2_b14&&size==14&&y==24));
 label=s;labelColor=color;return 0;
}
template<class C>void setFont(C&,int){}
struct Canvas {
 bool clipped=false;int clears=0,left=0,top=0;const uint8_t *font=nullptr;
 std::set<std::pair<int,int>> pixels;
 std::array<uint16_t,800*480> image{};
 void setClipRect(int x,int y,int w,int h){
  assert(!clipped&&x==(page==Page::Dashboard?606:525)&&y==(page==Page::Dashboard?11:16)&&w==36&&h==36);
  left=x;top=y;clipped=true;
 }
 void fillRect(int x,int y,int w,int h,int color){
  assert(page!=Page::Dashboard&&clipped&&x==left&&y==top&&w==36&&h==36&&color==BG);++clears;pixels.clear();
  for(int row=0;row<h;++row)for(int column=0;column<w;++column)
   image[size_t(y+row)*800+x+column]=uint16_t(color);
 }
 void pushImage(int x,int y,int w,int h,const lgfx::rgb565_t *data){
  assert(page==Page::Dashboard&&clipped&&data&&w>0&&h>0);
  assert(x>=left&&y>=top&&x+w<=left+36&&y+h<=top+36);
  assert(x>=0&&y>=0&&x+w<=800&&y+h<=480);
  if(x==left&&y==top){++clears;pixels.clear();}
  for(int row=0;row<h;++row)for(int column=0;column<w;++column){
   const int px=x+column,py=y+row;
   assert(data[row*w+column]==ws43b_native::textbg(px,py,BG));
   image[size_t(py)*800+px]=data[row*w+column];
  }
 }
 void point(int x,int y,uint16_t color){
  assert(clipped&&x>=left&&x<left+36&&y>=top&&y<top+36);
  pixels.insert({x,y});image[size_t(y)*800+x]=color;
 }
 void drawLine(int x,int y,int a,int b,uint16_t color){point(x,y,color);point(a,b,color);}
 void clearClipRect(){
  assert(clipped);
  // Every untouched icon pixel must be restored, including old animation marks.
  for(int y=top;y<top+36;++y)for(int x=left;x<left+36;++x)
   if(!pixels.count({x,y}))assert(image[size_t(y)*800+x]==
     (page==Page::Dashboard?ws43b_native::textbg(x,y,BG):BG));
  clipped=false;
 }
 void loadFont(const uint8_t *f){font=f;}void unloadFont(){font=nullptr;}
 static uint32_t be(const uint8_t *p){return uint32_t(p[0])<<24|uint32_t(p[1])<<16|uint32_t(p[2])<<8|p[3];}
 // VLW glyph metrics are real. The geometry recorder does not substitute fonts.
 int textWidth(const char *s){
  assert(font);int left=0,right=0;const auto count=be(font);
  while(*s){unsigned code=uint8_t(*s++);
   if(code>=0xc0){code&=0x1f;assert((uint8_t(*s)&0xc0)==0x80);code=(code<<6)|(uint8_t(*s++)&63);}
   bool found=false;
   for(unsigned i=0;i<count;++i){const auto *r=font+24+28*i;if(be(r)!=code)continue;
    const int advance=be(r+12),offset=int32_t(be(r+20)),width=be(r+8);
    if(left==0&&right==0&&offset<0)left=right=-offset;
    right=left+std::max(advance,width+offset);left+=advance;found=true;break;}
   assert(found);
  }
  return right;
 }
}tft;
''' + clear + function + r'''
int main(){
 for(Page destination:{Page::Dashboard,Page::Ams,Page::Details,Page::Settings}) {
  page=destination;data={};config.enabled=true;tft.clears=0;tft.image.fill(0xdead);
  dashboardWeatherIcon(0);assert(weatherHeaderVisible&&!tft.clipped&&!tft.pixels.empty());
  const auto first=tft.pixels;
  dashboardWeatherIcon(950);assert(first!=tft.pixels&&tft.clears==2);
  data.valid=false;dashboardWeatherIcon(1000);assert(!weatherHeaderVisible&&tft.pixels.empty());
  data.valid=true;config.enabled=false;dashboardWeatherIcon(2000);assert(!weatherHeaderVisible&&tft.pixels.empty());
  config.enabled=true;dashboardWeatherIcon(3000);assert(weatherHeaderVisible&&!tft.pixels.empty());
  menuWeatherHeader(3000);assert(label=="8°C"&&labelColor==INK&&weatherHeaderVisible);
  for(int temperature:{0,-12,-100,70}){
   data.temperature=temperature;menuWeatherHeader(3001);
   assert(label==std::to_string(temperature)+"°C"&&labelColor==INK);
  }
  data.valid=false;menuWeatherHeader(3003);assert(label=="--°C"&&labelColor==DIM&&!weatherHeaderVisible&&tft.pixels.empty());
  data.valid=true;menuWeatherHeader(3004);assert(label=="70°C"&&weatherHeaderVisible);
  // A valid but unrecognised WMO symbol retains only its neutral dash.
  data.code=4;dashboardWeatherIcon(3004);assert(tft.pixels.size()==2);
  assert(tft.pixels.count({tft.left+13,tft.top+18})&&tft.pixels.count({tft.left+23,tft.top+18}));
  config.enabled=false;label.clear();const int clears=tft.clears;
  menuWeatherHeader(3005);assert(label.empty()&&!weatherHeaderVisible&&tft.clears==clears);
  for(int y=0;y<480;++y)for(int x=0;x<800;++x)
   if(x<tft.left||x>=tft.left+36||y<tft.top||y>=tft.top+36)
    assert(tft.image[size_t(y)*800+x]==0xdead);
 }
}
'''
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'test.cpp').write_text(code);(p/'pgmspace.h').write_text('#pragma once\n#define PROGMEM\n')
   subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(p),'-I',str(ROOT/'include'),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
   subprocess.run([str(p/'test')],check=True)
