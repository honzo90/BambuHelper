from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[4]
class UnifiedStyle(unittest.TestCase):
 def test_spool_geometry_stays_in_its_tile(self):
  code=r'''
#include "ws43b_style.h"
#include <cassert>
struct Canvas {
 int ox=0,oy=0,extent=64,count=0;
 void point(int x,int y){assert(x>=ox&&x<ox+extent&&y>=oy&&y<oy+extent);++count;}
 void drawEllipse(int x,int y,int rx,int ry,int){point(x-rx,y-ry);point(x+rx,y+ry);}
 void fillEllipse(int x,int y,int rx,int ry,int c){drawEllipse(x,y,rx,ry,c);}
 void drawLine(int x,int y,int xx,int yy,int){point(x,y);point(xx,yy);}
};
int main(){for(bool known:{false,true})for(float scale:{1.f,1.5f,2.f})for(unsigned color:{0u,0xffffu,0x87e3u}){
 Canvas c;c.ox=24;c.oy=230;c.extent=64*scale;
 ws43b_style::spool(c,c.ox,c.oy,scale,color,known);assert(c.count>8);
}}
'''.replace('#include <cassert>','#include <cassert>\n#include <initializer_list>')
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'test.cpp').write_text(code)
   subprocess.run(['clang++','-std=c++17','-I',str(ROOT/'include'),str(p/'test.cpp'),'-o',str(p/'test')],check=True,capture_output=True)
   subprocess.run([str(p/'test')],check=True,capture_output=True)
