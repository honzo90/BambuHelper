"""Real drying raster: shared spool, fixed clip bounds and symbolic airflow."""
from pathlib import Path
import json
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]

# The preview imports this same fixture. No production primitives are replaced:
# drawLine and fillEllipse rasterize pixels; pushImage consumes the real assets.
HARNESS = r'''
#include <cstdint>
namespace lgfx {using rgb565_t=uint16_t;}
#include "ws43b_drying_scene.h"
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <vector>
struct Layout {int x,y,w,h,cx,cy,radius,extent;};
const Layout layouts[]={
 {668,138,96,94,718,184,42,69},
 {680,262,68,62,714,292,29,48},
 {108,222,170,158,190,298,74,96}
};
constexpr uint16_t bg=0x0864,accent=0x67b6,track=0x324b,ink=0xef9f;
struct Canvas {
 Layout l;std::vector<uint16_t> pixels,sprite;
 std::vector<uint8_t> spriteMask;
 unsigned writes=0,lines=0,pushes=0;
 explicit Canvas(Layout l):l(l),pixels(size_t(l.w)*l.h,bg),
   sprite(pixels.size(),bg),spriteMask(pixels.size(),0){}
 size_t index(int x,int y)const{
  // Reject out-of-region calls instead of silently clipping them away.
  assert(x>=l.x&&x<l.x+l.w&&y>=l.y&&y<l.y+l.h);
  return size_t(y-l.y)*l.w+x-l.x;
 }
 void point(int x,int y,uint16_t color){
  assert(++writes<20000);pixels[index(x,y)]=color;
 }
 void drawLine(int x,int y,int a,int b,uint16_t color){
  assert(++lines<=192);const int dx=std::abs(a-x),dy=-std::abs(b-y);
  const int sx=x<a?1:-1,sy=y<b?1:-1;int error=dx+dy;
  while(true){point(x,y,color);if(x==a&&y==b)break;
   const int twice=error*2;
   if(twice>=dy){error+=dy;x+=sx;}
   if(twice<=dx){error+=dx;y+=sy;}
  }
 }
 void fillEllipse(int cx,int cy,int rx,int ry,uint16_t color){
  assert(rx>0&&ry>0);index(cx-rx,cy-ry);index(cx+rx,cy+ry);
  for(int y=-ry;y<=ry;++y)for(int x=-rx;x<=rx;++x)
   if(int64_t(x)*x*ry*ry+int64_t(y)*y*rx*rx<=int64_t(rx)*rx*ry*ry)
    point(cx+x,cy+y,color);
 }
 void pushImage(int x,int y,int w,int h,const lgfx::rgb565_t *data){
  // The native 69px asset emits separate RLE material/alpha spans. It can
  // require more calls than the two chunks per row of the resized variants.
  assert(data&&w>0&&h>0&&++pushes<=1024);
  index(x,y);index(x+w-1,y+h-1);
  for(int row=0;row<h;++row)for(int column=0;column<w;++column){
   const auto at=index(x+column,y+row);const uint16_t color=data[row*w+column];
   sprite[at]=color;spriteMask[at]=1;point(x+column,y+row,color);
  }
 }
 void ppm(const char *path)const{
  FILE *out=fopen(path,"wb");assert(out);
  fprintf(out,"P6\n%d %d\n255\n",l.w,l.h);
  for(uint16_t c:pixels){const unsigned char rgb[]={ws43b_assets::red(c),
    ws43b_assets::green(c),ws43b_assets::blue(c)};assert(fwrite(rgb,1,3,out)==3);}
  assert(fclose(out)==0);
 }
};
void frame(Canvas &c,uint32_t phase){
 ws43b_drying_scene::draw(c,c.l.cx,c.l.cy,c.l.radius,phase,accent,track,ink,bg);
}
int main(int argc,char **argv){
 if(argc==4){const unsigned which=unsigned(strtoul(argv[1],nullptr,10));assert(which<3);
  Canvas c(layouts[which]);frame(c,uint32_t(strtoul(argv[2],nullptr,10)));c.ppm(argv[3]);return 0;}
 unsigned frames=0,maxWrites=0,maxPushes=0;
 const auto &asset=ws43b_assets::descriptor(ws43b_assets::Asset::Spool);
 for(const auto &l:layouts){
  Canvas expected(l),first(l);
  assert(ws43b_ui_icons::flat(expected,ws43b_assets::Asset::Spool,l.cx,l.cy,l.extent,bg,true,0xBDF7));
  assert(expected.pushes>0);
  const int major=std::max(asset.width,asset.height);
  const int w=(int(asset.width)*l.extent+major/2)/major;
  const int h=(int(asset.height)*l.extent+major/2)/major;
  const int left=l.cx-w/2,top=l.cy-h/2;
  frame(first,0);bool movingAir=false;
  std::vector<uint32_t> phases={0,1,950,2399,4799,4800,0xffffffffu};
  for(uint32_t phase=0;phase<4800;phase+=137)phases.push_back(phase);
  for(uint32_t phase:phases){
   Canvas c(l);frame(c,phase);++frames;maxWrites=std::max(maxWrites,c.writes);
   maxPushes=std::max(maxPushes,c.pushes);
   assert(c.pushes>0&&c.lines==(l.radius>=40?192u:96u));
   // Exact production asset, scale, neutral tint and alpha compositing at
   // every phase. The geometric spool itself never rotates or morphs.
   assert(c.sprite==expected.sprite&&c.spriteMask==expected.spriteMask);
   for(int y=top;y<top+h;++y)for(int x=left;x<left+w;++x){
    const auto at=c.index(x,y);
    // Front airflow intentionally overlays the lower spool. Its upper/core
    // pixels must remain identical to the asset even in the final image.
    if(y<=l.cy+l.radius/4&&expected.spriteMask[at])
     assert(c.pixels[at]==expected.pixels[at]);
   }
   for(size_t at=0;at<c.pixels.size();++at){
    const int x=l.x+int(at%l.w),y=l.y+int(at/l.w);
    if((x<left||x>=left+w||y<top||y>=top+h)&&c.pixels[at]!=first.pixels[at])movingAir=true;
   }
   if(phase==4800)assert(c.pixels==first.pixels);
  }
  assert(movingAir);
 }
 printf("{\"frames\":%u,\"max_pixel_writes\":%u,\"max_push_calls\":%u,\"result\":\"PASS\"}\n",frames,maxWrites,maxPushes);
}
'''


class DryingIcons(unittest.TestCase):
    def test_shared_spool_bounds_and_airflow_at_all_production_sizes(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            (path/'drying.cpp').write_text(HARNESS)
            result = subprocess.run([
                'clang++', '-std=c++17', '-O1', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', '-I', str(ROOT/'include'),
                str(path/'drying.cpp'), '-o', str(path/'drying'),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(path/'drying')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report['result'], 'PASS')
            self.assertEqual(report['frames'], 129)
            self.assertLess(report['max_pixel_writes'], 20000)


if __name__ == '__main__':
    unittest.main()
