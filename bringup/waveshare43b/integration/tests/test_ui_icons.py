"""Verify shared icon composition against independent per-pixel expectations."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class UiIcons(unittest.TestCase):
    def test_alpha_aspect_ratio_clip_and_state_tints(self):
        code = r'''
#include <cstdint>
namespace lgfx {using rgb565_t=uint16_t;}
#include "ws43b_ui_icons.h"
#include <array>
#include <cassert>
#include <algorithm>
struct Canvas {
 std::array<uint16_t,128*128> pixels{};
 int x0=0,y0=0,x1=128,y1=128,writes=0;
 void pushImage(int x,int y,int w,int h,const lgfx::rgb565_t *p) {
  assert(w>0&&w<=64&&h==1);
  for(int i=0;i<w;++i)if(x+i>=x0&&x+i<x1&&y>=y0&&y<y1) {
   assert(x+i>=0&&x+i<128&&y>=0&&y<128);
   pixels[y*128+x+i]=p[i];++writes;
  }
 }
};
int main() {
 using A=ws43b_assets::Asset;
 const A assets[]={A::Nozzle,A::Bed,A::Chamber,A::Print,A::AMS,A::Details,A::Settings,
  A::Spool,A::Clock,A::Weather,A::Network,A::Check,A::Pause,A::Alert,A::EmptySlot,
  A::UnknownData,A::Printer,A::Fan};
 const auto bg=[](int x,int y){return ws43b_native::cardbg(x,y,0,128,0x0084,0x67b6,24);};
 for(A asset:assets)for(int extent:{33,40,48,58,64,69,72,96})
 for(uint16_t tint:{uint16_t(0),uint16_t(0xf5cb),uint16_t(0xf38f)}) {
  const auto &s=ws43b_assets::descriptor(asset);
  const int major=std::max(s.width,s.height);
  const int w=(s.width*extent+major/2)/major,h=(s.height*extent+major/2)/major;
  const int ox=64-w/2,oy=64-h/2;
  Canvas full;for(int y=0;y<128;++y)for(int x=0;x<128;++x)full.pixels[y*128+x]=bg(x,y);
  const auto before=full.pixels;
  assert(ws43b_ui_icons::draw(full,asset,64,64,extent,bg,true,tint));
  assert(full.writes>0);
  for(int y=0;y<128;++y)for(int x=0;x<128;++x) {
   uint16_t expected=bg(x,y);
   if(x>=ox&&x<ox+w&&y>=oy&&y<oy+h) {
    const auto sample=w==s.width&&h==s.height?
     ws43b_native::sample(s,x-ox,y-oy,tint,true):
     ws43b_native::filtered(s,((x-ox)*2+1)*s.width*128/w-128,
                          ((y-oy)*2+1)*s.height*128/h-128,tint,true);
    expected=ws43b_assets::blend(sample.color,expected,sample.alpha);
   }
   assert(full.pixels[y*128+x]==expected);
  }
  Canvas clipped;clipped.pixels=before;clipped.x0=53;clipped.x1=76;clipped.y0=48;clipped.y1=85;
  assert(ws43b_ui_icons::draw(clipped,asset,64,64,extent,bg,true,tint));
  assert(clipped.x0==53&&clipped.y0==48&&clipped.x1==76&&clipped.y1==85);
  for(int y=0;y<128;++y)for(int x=0;x<128;++x)
   assert(clipped.pixels[y*128+x]==(x>=53&&x<76&&y>=48&&y<85?full.pixels[y*128+x]:before[y*128+x]));
 }
 Canvas c;const auto original=c.pixels;
 for(int extent:{-1,0,97,1000})assert(!ws43b_ui_icons::flat(c,A::Printer,64,64,extent,0));
 assert(!ws43b_ui_icons::flat(c,A::Count,64,64,33,0));
 assert(c.pixels==original&&c.writes==0);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / 'test.cpp').write_text(code)
            subprocess.run(['clang++', '-std=c++17', '-O1', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                            '-I', str(ROOT / 'include'), str(p / 'test.cpp'), '-o', str(p / 'test')],
                           check=True, capture_output=True)
            subprocess.run([str(p / 'test')], check=True, capture_output=True)
