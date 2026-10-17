from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[4]
class IconBackground(unittest.TestCase):
 def test_dirty_restore_matches_full_frame(self):
  src=(ROOT/'src/display_ws43b.cpp').read_text()
  water=src[src.index('uint16_t waterColor('):src.index('bool clockHasProgress(')]
  background=src[src.index('void drawClockBackground(bool, int, uint32_t now) {'):src.index('void clockWeatherIcon(const BambuMonitorTelemetry &,bool,uint32_t now) {')]
  code=r'''
#include <cstdint>
#include <cmath>
#include <vector>
#include <cassert>
#include <algorithm>
#include "ws43b_water_clock.h"
struct Surface {
 std::vector<uint16_t> p=std::vector<uint16_t>(800*480);int cx=0,cy=0,cw=800,ch=480;
 uint16_t color565(int r,int g,int b){return ((r>>3)<<11)|((g>>2)<<5)|(b>>3);}
 void getClipRect(int32_t*x,int32_t*y,int32_t*w,int32_t*h){*x=cx;*y=cy;*w=cw;*h=ch;}
 void dot(int x,int y,uint16_t c){if(x>=cx&&x<cx+cw&&y>=cy&&y<cy+ch&&x>=0&&x<800&&y>=0&&y<480)p[y*800+x]=c;}
 void drawFastHLine(int x,int y,int w,uint16_t c){for(int i=0;i<w;++i)dot(x+i,y,c);}
 void fillRect(int x,int y,int w,int h,uint16_t c){for(int j=0;j<h;++j)drawFastHLine(x,y+j,w,c);}
}tft;
'''+water+background+r'''
int main(){
 for(bool valid:{false,true})for(int progress:{0,1,45,46,50,56,60,63,99,100})for(unsigned now:{0u,500u,1234u,65000u}){
  tft.cx=0;tft.cy=0;tft.cw=800;tft.ch=480;drawClockBackground(valid,progress,now);auto full=tft.p;
  // Restore the animated footer exactly, without changing the clock or status.
  tft.cx=0;tft.cy=416;tft.cw=800;tft.ch=64;tft.fillRect(0,416,800,64,0xffff);
  drawClockBackground(valid,progress,now);assert(tft.p==full);
 }
}
'''
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'test.cpp').write_text(code)
   subprocess.run(['clang++','-std=c++17','-I',str(ROOT/'include'),str(p/'test.cpp'),'-o',str(p/'test')],check=True,capture_output=True)
   subprocess.run([str(p/'test')],check=True,capture_output=True)
