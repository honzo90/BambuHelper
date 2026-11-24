"""Photo screensaver policy: names, limits, JPEG/PNG headers, zoom, settings.

Compiles include/ws43b_photo_policy.h on the host. JPEG and PNG headers are
built byte by byte here (including an EXIF block before the SOF marker), so
no image library, card or panel is involved.
"""

import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]

CODE = r'''
#include "ws43b_photo_policy.h"
#include <cassert>
#include <cstring>
#include <cstdio>
#include <vector>
using namespace ws43b_photo;
struct Bytes {
  std::vector<uint8_t> v;
  bool operator()(uint32_t off,uint8_t *out,size_t n) const {
    if(off+n>v.size())return false;memcpy(out,v.data()+off,n);return true;
  }
};
Bytes jpeg(uint16_t w,uint16_t h,unsigned exif,uint8_t sof=0xC0){
  Bytes b;b.v={0xFF,0xD8};
  // APP1 (EXIF) of arbitrary length, then a fill byte, then DQT, then SOF.
  b.v.insert(b.v.end(),{0xFF,0xE1,uint8_t((exif+2)>>8),uint8_t(exif+2)});b.v.resize(b.v.size()+exif,0x45);
  b.v.push_back(0xFF);
  b.v.insert(b.v.end(),{0xFF,0xDB,0x00,0x04,0x00,0x00});
  b.v.insert(b.v.end(),{0xFF,sof,0x00,0x11,0x08,uint8_t(h>>8),uint8_t(h),uint8_t(w>>8),uint8_t(w),0x03});
  b.v.resize(b.v.size()+16,0);b.v.insert(b.v.end(),{0xFF,0xD9});
  return b;
}
Bytes png(uint32_t w,uint32_t h){
  Bytes b;b.v={0x89,'P','N','G',0x0D,0x0A,0x1A,0x0A,0,0,0,13,'I','H','D','R',
    uint8_t(w>>24),uint8_t(w>>16),uint8_t(w>>8),uint8_t(w),uint8_t(h>>24),uint8_t(h>>16),uint8_t(h>>8),uint8_t(h)};
  b.v.resize(64,0);return b;
}
int main(){
  // Names: only plain image files in /images.
  assert(format("a.JPG")==Format::Jpeg&&format("b.jpeg")==Format::Jpeg&&format("c.Png")==Format::Png);
  assert(format("d.gif")==Format::None&&format(".jpg")==Format::None&&format("jpg")==Format::None);
  for(const char *ok:{"Wakacje 2026 (1).jpg","plate_A-1.png","x.jpeg"})assert(safeName(ok));
  for(const char *bad:{"","../a.jpg","a/b.jpg","a\\b.jpg",".hidden.jpg"," a.jpg","a..b.jpg",
                       "a.txt","zażółć.jpg","a?.jpg","a%2e.jpg"})assert(!safeName(bad));
  assert(!safeName(nullptr));
  char longName[64];memset(longName,'a',sizeof longName);strcpy(longName+kNameMax-4,".jpg");
  assert(!safeName(longName));longName[0]=0;
  char edge[kNameMax];memset(edge,'a',sizeof edge);strcpy(edge+kNameMax-5,".jpg");assert(strlen(edge)==kNameMax-1);
  assert(safeName(edge));
  // Size limits per format.
  assert(sizeAllowed(Format::Jpeg,kMaxJpegBytes)&&!sizeAllowed(Format::Jpeg,kMaxJpegBytes+1));
  assert(sizeAllowed(Format::Png,kMaxPngBytes)&&!sizeAllowed(Format::Png,kMaxPngBytes+1));
  assert(!sizeAllowed(Format::Jpeg,0)&&!sizeAllowed(Format::None,10));
  // Headers.
  uint16_t w=0,h=0;
  auto j=jpeg(4000,3000,30000);assert(imageSize(Format::Jpeg,j,uint32_t(j.v.size()),w,h)&&w==4000&&h==3000);
  auto p2=jpeg(640,480,10,0xC2);assert(imageSize(Format::Jpeg,p2,uint32_t(p2.v.size()),w,h)&&w==640&&h==480);
  auto huff=jpeg(1,1,10,0xC4);assert(!imageSize(Format::Jpeg,huff,uint32_t(huff.v.size()),w,h));
  Bytes notJpeg;notJpeg.v={0x00,0x11,0x22,0x33,0x44};assert(!imageSize(Format::Jpeg,notJpeg,5,w,h));
  auto cut=jpeg(100,100,40000);cut.v.resize(30000);assert(!imageSize(Format::Jpeg,cut,uint32_t(cut.v.size()),w,h));
  auto pg=png(800,480);assert(imageSize(Format::Png,pg,uint32_t(pg.v.size()),w,h)&&w==800&&h==480);
  auto bigPng=png(70000,10);assert(!imageSize(Format::Png,bigPng,uint32_t(bigPng.v.size()),w,h));
  auto badPng=png(10,10);badPng.v[1]='X';assert(!imageSize(Format::Png,badPng,64,w,h));
  assert(dimensionsAllowed(4096,4096)&&!dimensionsAllowed(4097,10)&&!dimensionsAllowed(0,10));
  // Zoom: fit shows all, fill covers, small images enlarge at most 2x.
  assert(zoom(1600,960,false)==0.5f&&zoom(1600,1200,false)==0.4f&&zoom(1600,1200,true)==0.5f);
  assert(zoom(100,100,false)==2.0f&&zoom(800,480,true)==1.0f);
  // Settings record round trip and rejection of foreign values.
  for(int e=0;e<2;++e)for(int i=0;i<4;++i)for(int c=0;c<4;++c)for(int f=0;f<2;++f){
    Settings s;s.enabled=e;s.interval=i;s.corner=c;s.fill=f;Settings back;
    assert(decode(encode(s),back)&&back.enabled==s.enabled&&back.interval==s.interval&&back.corner==s.corner&&back.fill==s.fill);
  }
  Settings ignored;assert(!decode(0,ignored)&&!decode(0x0100,ignored)&&!decode(0x02C0,ignored));
  assert(intervalIndex(30)==1&&intervalIndex(300)==3&&intervalIndex(45)==-1);
  // Slideshow: first slide immediately, then after the interval, wrapping.
  Slideshow show;assert(show.due(5,30)&&show.next(3)==0);show.shown(5);
  assert(!show.due(29004,30)&&show.due(30005,30)&&show.next(3)==1&&show.next(3)==2&&show.next(3)==0);
  show.index=7;assert(show.next(2)==0&&show.next(0)==0);
  Slideshow wrap;wrap.shown(0xFFFFF000u);assert(!wrap.due(0x00000FFFu,30)&&wrap.due(0x00008000u,30));
  // Card placement stays on screen in every corner.
  for(uint8_t c=0;c<4;++c)for(int printing=0;printing<2;++printing){
    const auto r=card(c,printing);assert(r.x>=24&&r.y>=24&&r.x+r.w<=776&&r.y+r.h<=456);
  }
  assert(card(0,false).x>400&&card(1,false).x==24&&card(2,false).y==24&&card(0,true).h==124);
  // Dimming keeps black black, darkens white, and rounds card corners.
  assert(dim(0xFFFF,0)==0xFFFF&&dim(0xFFFF,160)<0xFFFF&&dim(0x0000,256)==dim(0x1234,256));
  assert(!insideRounded(0,0,100,50,14)&&insideRounded(14,0,100,50,14)&&insideRounded(50,25,100,50,14));
  // Full repaint only when the canvas no longer holds the picture.
  Canvas canvas;assert(fullFrame(canvas,false,1,0,10));
  canvas.shown=true;canvas.revision=1;canvas.layout=0;canvas.frames=10;
  assert(!fullFrame(canvas,false,1,0,10));                 // nothing changed: card/minute only
  assert(fullFrame(canvas,true,1,0,10));                   // explicit redraw
  assert(fullFrame(canvas,false,2,0,10));                  // new slide
  assert(fullFrame(canvas,false,1,1,10));                  // card moved / print started
  assert(fullFrame(canvas,false,1,0,11));                  // something else rendered
  // A single unchanged picture is decoded once.
  assert(decodeDue(false,1,0,0)&&!decodeDue(true,1,3,3)&&decodeDue(true,1,4,3)&&decodeDue(true,2,3,3));
  assert(kScreenH%kPushBandRows==0);
  puts("PASS: photo names, limits, JPEG/PNG headers, zoom, settings, slideshow, card and repaint");
}
'''


class PhotoPolicy(unittest.TestCase):
    def test_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / 'test.cpp').write_text(CODE)
            subprocess.run(
                [
                    'clang++',
                    '-std=c++17',
                    '-Wall',
                    '-Wextra',
                    '-Werror',
                    '-I',
                    str(ROOT / 'include'),
                    str(p / 'test.cpp'),
                    '-o',
                    str(p / 'test'),
                ],
                check=True,
            )
            subprocess.run([str(p / 'test')], check=True)


if __name__ == '__main__':
    unittest.main()
