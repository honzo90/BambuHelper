from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[4]
class WeatherIcons(unittest.TestCase):
 def test_codes_geometry_and_day_night(self):
  code=r'''
#include "ws43b_weather_icons.h"
#include "ws43b_weather_background.h"
#include <cassert>
#include <set>
#include <utility>
struct Surface {
 std::set<std::pair<int,int>> pixels;
 void point(int x,int y){assert(x>=-32&&x<=32&&y>=-32&&y<=32);pixels.insert({x,y});}
 void drawLine(int x,int y,int a,int b,uint16_t){point(x,y);point(a,b);}
 void drawCircle(int x,int y,int r,uint16_t){point(x-r,y-r);point(x+r,y+r);}
};
int main(){
 using namespace ws43b_weather_icon;
 int codes[]={0,1,2,3,45,48,51,53,55,56,57,61,63,65,66,67,71,73,75,77,80,81,82,85,86,95,96,97,99};
 for(int c:codes){
  assert(classify(true,c)!=Symbol::Unknown);
  assert(ws43b_weather_bg::classify(true,true,c)!=ws43b_weather_bg::Kind::Neutral);
  assert(classify(false,c)==Symbol::Unknown);
  for(int scale:{1,2})for(bool night:{false,true})for(unsigned phase=0;phase<6400;phase+=97){
   Surface s;draw(s,classify(true,c),0,0,scale,night,1,2,3,phase);assert(!s.pixels.empty());
  }
 }
 assert(classify(true,4)==Symbol::Unknown);
 std::set<std::set<std::pair<int,int>>> shapes;
 for(int c:{0,2,3,45,51,61,66,71,95,99,-1}){Surface s;draw(s,classify(true,c),0,0,1,false,1,2,3);assert(shapes.insert(s.pixels).second);}
 for(auto symbol:{Symbol::Partial,Symbol::Fog,Symbol::Drizzle,Symbol::Rain,Symbol::Ice,Symbol::Snow,Symbol::Storm,Symbol::Hail}) {
  Surface first,later;draw(first,symbol,0,0,2,false,0xffff,0xffe0,0x5ede,0);
  draw(later,symbol,0,0,2,false,0xffff,0xffe0,0x5ede,950);assert(first.pixels!=later.pixels);
 }
 Surface day,night;draw(day,Symbol::Clear,0,0,1,false,1,2,3);draw(night,Symbol::Clear,0,0,1,true,1,2,3);assert(day.pixels!=night.pixels);
}
'''
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'test.cpp').write_text(code)
   subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(ROOT/'include'),str(p/'test.cpp'),'-o',str(p/'test')],check=True,capture_output=True)
   subprocess.run([str(p/'test')],check=True,capture_output=True)

 def test_native_pixels_transparency_shading_and_fixed_bounds(self):
  code=r'''
#include "ws43b_weather_icons.h"
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdlib>
#include <set>
struct Surface {
 static constexpr int width=128,cx=61,cy=57;
 std::array<uint16_t,width*width> pixels{},before{};
 std::array<bool,width*width> touched{};
 int scale=1,calls=0;
 explicit Surface(int scale):scale(scale){
  for(int y=0;y<width;++y)for(int x=0;x<width;++x)
   pixels[y*width+x]=uint16_t(0x0841+((x*13+y*29)&0x07ff));
  before=pixels;
 }
 void point(int x,int y,uint16_t color){
  assert(x>=cx-15*scale&&x<=cx+15*scale);
  assert(y>=cy-15*scale&&y<=cy+15*scale);
  assert(x>=0&&x<width&&y>=0&&y<width);
  pixels[y*width+x]=color;touched[y*width+x]=true;
 }
 void drawLine(int x,int y,int a,int b,uint16_t color){
  ++calls;const int dx=std::abs(a-x),dy=-std::abs(b-y);
  const int sx=x<a?1:-1,sy=y<b?1:-1;int error=dx+dy;
  while(true){point(x,y,color);if(x==a&&y==b)break;
   const int twice=error*2;
   if(twice>=dy){error+=dy;x+=sx;}
   if(twice<=dx){error+=dx;y+=sy;}
  }
 }
};
int main(){
 using namespace ws43b_weather_icon;
 const Symbol symbols[]={Symbol::Unknown,Symbol::Clear,Symbol::Partial,Symbol::Cloud,
  Symbol::Fog,Symbol::Drizzle,Symbol::Rain,Symbol::Ice,Symbol::Snow,Symbol::Storm,Symbol::Hail};
 for(int scale:{1,2,3})for(bool night:{false,true})for(Symbol symbol:symbols)
  for(unsigned phase:{0u,1u,950u,1799u,1800u,3199u,6399u,6400u,0xffffffffu}){
   Surface s(scale);draw(s,symbol,Surface::cx,Surface::cy,scale,night,0xef9f,0xf5cb,0x5ede,phase);
   assert(s.calls>0&&s.calls<=32*scale+12);
   std::set<uint16_t> colors;
   for(size_t i=0;i<s.pixels.size();++i){
    if(s.touched[i])colors.insert(s.pixels[i]);else assert(s.pixels[i]==s.before[i]);
   }
   if(symbol!=Symbol::Unknown)assert(colors.size()>3);
   // The crescent opening and empty box corners retain the exact backdrop.
   for(int dx:{-15,15})for(int dy:{-15,15})
    assert(!s.touched[(Surface::cy+dy*scale)*Surface::width+Surface::cx+dx*scale]);
   if(symbol==Symbol::Clear&&night)
    assert(!s.touched[(Surface::cy-3*scale)*Surface::width+Surface::cx+4*scale]);
   if(symbol==Symbol::Unknown){
    assert(s.calls==1&&colors.size()==1);
    assert(std::count(s.touched.begin(),s.touched.end(),true)==10*scale+1);
   }
  }
 for(int scale:{0,-1}){Surface s(1);draw(s,Symbol::Clear,61,57,scale,false,1,2,3);assert(s.calls==0);}
 // Exact established WMO categories, including freezing drizzle/rain and hail.
 for(int code:{0,1})assert(classify(true,code)==Symbol::Clear);
 for(int code:{45,48})assert(classify(true,code)==Symbol::Fog);
 for(int code:{51,53,55})assert(classify(true,code)==Symbol::Drizzle);
 for(int code:{56,57,66,67})assert(classify(true,code)==Symbol::Ice);
 for(int code:{61,63,65,80,81,82})assert(classify(true,code)==Symbol::Rain);
 for(int code:{71,73,75,77,85,86})assert(classify(true,code)==Symbol::Snow);
 for(int code:{95,97})assert(classify(true,code)==Symbol::Storm);
 for(int code:{96,99})assert(classify(true,code)==Symbol::Hail);
 for(int code:{-1,4,100,32767})assert(classify(true,code)==Symbol::Unknown);
}
'''
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'test.cpp').write_text(code)
   subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror',
    '-fsanitize=address,undefined','-I',str(ROOT/'include'),str(p/'test.cpp'),'-o',str(p/'test')],check=True,capture_output=True)
   subprocess.run([str(p/'test')],check=True,capture_output=True)
