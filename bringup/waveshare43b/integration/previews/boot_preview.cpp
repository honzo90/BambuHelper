// Host proof of the production boot composition and actual firmware VLW masks.
// Hardware scanout, timing, touch and network behavior are deliberately excluded.
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <limits>
#include <new>
#include <string>
#include <vector>

size_t hostAllocations=0;
void *operator new(size_t n){++hostAllocations;if(void *p=std::malloc(n?n:1))return p;throw std::bad_alloc();}
void *operator new[](size_t n){return ::operator new(n);}
void operator delete(void *p) noexcept{std::free(p);}
void operator delete[](void *p) noexcept{std::free(p);}
void operator delete(void *p,size_t) noexcept{std::free(p);}
void operator delete[](void *p,size_t) noexcept{std::free(p);}

namespace lgfx { struct rgb565_t {uint16_t raw;}; }
#include "ws43b_boot_scene.h"
#include "fonts/ws43b_dashboard_v2.h"
using String=std::string;
constexpr int FONT_NONE=0,TL_DATUM=0;
uint32_t be32(const uint8_t *p){return uint32_t(p[0])<<24|uint32_t(p[1])<<16|uint32_t(p[2])<<8|p[3];}
uint32_t codepoint(const uint8_t *&p){
  uint32_t cp=*p++;unsigned tail=0;
  if(cp>=0xf0){cp&=7;tail=3;}else if(cp>=0xe0){cp&=15;tail=2;}else if(cp>=0xc0){cp&=31;tail=1;}
  while(tail--){assert((*p&0xc0)==0x80);cp=cp<<6|(*p++&63);}return cp;
}
struct Canvas {
  struct Glyph{uint32_t code;int height,width,advance,dy,dx;const uint8_t *alpha;};
  std::array<Glyph,160> glyphs{};unsigned glyphCount=0;
  std::vector<uint16_t> pixels=std::vector<uint16_t>(800*480,0xc13b);
  unsigned writes=0,outside=0,clippedInk=0,textCalls=0,abbreviated=0;
  int left=0,top=0,right=800,bottom=480,baseline=0,space=0;
  bool clip=false;int clipX=0,clipY=0,clipW=0,clipH=0;
  uint16_t textColor=0;char drawn[256]{};
  void resetCounts(){writes=outside=clippedInk=textCalls=abbreviated=0;}
  void bounds(int x,int y,int w,int h){left=x;top=y;right=x+w;bottom=y+h;}
  void put(int x,int y,uint16_t c){
    if(x<left||y<top||x>=right||y>=bottom)++outside;
    if(x>=0&&y>=0&&x<800&&y<480)pixels[size_t(y)*800+x]=c;++writes;
  }
  uint16_t get(int x,int y)const{assert(x>=0&&y>=0&&x<800&&y<480);return pixels[size_t(y)*800+x];}
  void drawFastHLine(int x,int y,int w,uint16_t c){for(int i=0;i<w;++i)put(x+i,y,c);}
  void fillCircle(int x,int y,int r,uint16_t c){for(int yy=-r;yy<=r;++yy)for(int xx=-r;xx<=r;++xx)if(xx*xx+yy*yy<=r*r)put(x+xx,y+yy,c);}
  void drawCircle(int x,int y,int r,uint16_t c){for(int yy=-r;yy<=r;++yy)for(int xx=-r;xx<=r;++xx)if(xx*xx+yy*yy<=r*r&&xx*xx+yy*yy>=(r-1)*(r-1))put(x+xx,y+yy,c);}
  void drawLine(int x,int y,int xx,int yy,uint16_t c){
    const int dx=std::abs(xx-x),sx=x<xx?1:-1,dy=-std::abs(yy-y),sy=y<yy?1:-1;int error=dx+dy;
    for(;;){put(x,y,c);if(x==xx&&y==yy)break;const int twice=error*2;if(twice>=dy){error+=dy;x+=sx;}if(twice<=dx){error+=dx;y+=sy;}}
  }
  static bool rounded(int x,int y,int w,int h,int r){
    if(x<0||y<0||x>=w||y>=h)return false;
    r=std::max(0,std::min(r,std::min(w,h)/2));if(!r)return true;
    const int dx=x-std::clamp(x,r,w-r-1),dy=y-std::clamp(y,r,h-r-1);return dx*dx+dy*dy<=r*r;
  }
  void drawRoundRect(int x,int y,int w,int h,int r,uint16_t c){
    for(int yy=0;yy<h;++yy)for(int xx=0;xx<w;++xx)
      if(rounded(xx,yy,w,h,r)&&!rounded(xx-1,yy-1,w-2,h-2,r-1))put(x+xx,y+yy,c);
  }
  void pushImage(int x,int y,int w,int h,const lgfx::rgb565_t *p){for(int yy=0;yy<h;++yy)for(int xx=0;xx<w;++xx)put(x+xx,y+yy,p[size_t(yy)*w+xx].raw);}
  void loadFont(const uint8_t *p){
    glyphCount=be32(p);assert(glyphCount<=glyphs.size());baseline=int(be32(p+16));int descent=int(be32(p+20));
    space=std::max(int(be32(p+8)),baseline+descent)*2/7;
    const uint8_t *bitmap=p+24+28*glyphCount;
    for(unsigned i=0;i<glyphCount;++i){
      const uint8_t *r=p+24+i*28;
      auto &g=glyphs[i];g={be32(r),int(be32(r+4)),int(be32(r+8)),int(be32(r+12)),int16_t(be32(r+16)),int8_t(be32(r+20)),bitmap};
      bitmap+=g.width*g.height;
      if(g.code>255||(g.code>32&&g.code<160&&g.code!=127)){baseline=std::max(baseline,g.dy);descent=std::max(descent,g.height-g.dy);}
    }
  }
  const Glyph &glyph(uint32_t cp)const{for(unsigned i=0;i<glyphCount;++i)if(glyphs[i].code==cp)return glyphs[i];assert(false&&"unsupported glyph");return glyphs[0];}
  int textWidth(const char *s)const{
    int left=0,right=0;
    for(auto p=reinterpret_cast<const uint8_t*>(s);*p;){const auto &g=glyph(codepoint(p));if(!left&&!right&&g.dx<0)left=right=-g.dx;right=left+std::max(g.advance,g.width+g.dx);left+=g.advance;}
    return right;
  }
  void setTextSize(int n){assert(n==1);}void setTextColor(uint16_t c){textColor=c;}
  void setTextDatum(int n){assert(n==TL_DATUM);}
  void setClipRect(int x,int y,int w,int h){clip=true;clipX=x;clipY=y;clipW=w;clipH=h;}
  void clearClipRect(){clip=false;}void unloadFont(){}
  void drawString(const char *s,int x,int y){
    ++textCalls;std::snprintf(drawn,sizeof drawn,"%s",s);int cursor=0;bool first=true;
    for(auto p=reinterpret_cast<const uint8_t*>(s);*p;){const auto &g=glyph(codepoint(p));
      if(first){cursor=std::max(-g.dx,0);first=false;}if(g.code==32){cursor+=space;continue;}
      for(int yy=0;yy<g.height;++yy)for(int xx=0;xx<g.width;++xx){
        const unsigned a=g.alpha[yy*g.width+xx];if(!a)continue;
        const int px=x+cursor+g.dx+xx,py=y+baseline-g.dy+yy;
        if(clip&&(px<clipX||py<clipY||px>=clipX+clipW||py>=clipY+clipH)){++clippedInk;continue;}
        put(px,py,ws43b_assets::blend(textColor,get(px,py),uint8_t(a)));
      }
      cursor+=g.advance;
    }
  }
  void ppm(const char *path)const{
    std::ofstream out(path,std::ios::binary);assert(out.good());out<<"P6\n800 480\n255\n";
    for(uint16_t p:pixels){const char rgb[]={char(ws43b_assets::red(p)),char(ws43b_assets::green(p)),char(ws43b_assets::blue(p))};out.write(rgb,3);}assert(out.good());
  }
} tft;
void setFont(Canvas &,int){}
#include "production_boot_text.h"

const char *context(ws43b_boot::Phase phase,bool pl){
  (void)pl;
  switch(phase){
    case ws43b_boot::Phase::Panel:return nullptr;
    case ws43b_boot::Phase::Wifi:return "Dom-Test";
    case ws43b_boot::Phase::Printer:return "Bambu P2S";
    default:return "Bambu P2S";
  }
}
void text(const char *s,int x,int y,int w,int size,uint16_t color){
  const uint8_t *font=size==25?ws43b_v2_b25:size==17?ws43b_v2_b17:ws43b_v2_b14;
  v2Text(s,x,y,w,font,size,color);
  if(std::strcmp(s,tft.drawn))++tft.abbreviated;
}
void frame(ws43b_boot::Phase phase,const ws43b_boot::Palette &p,bool pl,uint32_t now,const char *detail=nullptr){
  ws43b_boot::draw(tft,text,phase,p,pl,detail?detail:context(phase,pl),now);
}
void verify(){
  using P=ws43b_boot::Phase;
  assert(ws43b_boot::connectionPhase(false,false)==P::Wifi);
  assert(ws43b_boot::connectionPhase(false,true)==P::Wifi);
  assert(ws43b_boot::connectionPhase(true,false)==P::Printer);
  assert(ws43b_boot::connectionPhase(true,true)==P::Data);
  const ws43b_boot::Palette palettes[]={{0x0084,ws43b_native::rgb(128,229,155),ws43b_native::ink,ws43b_native::dim},{0x0841,0x77b2,0xf7be,0x9d34},{0x0841,0xf5cb,0xf7be,0x9d34},{0,0xffff,0xffff,0x8410},{0xffff,0xf800,0,0x8410}};
  const uint32_t times[]={0,1,79,80,399,400,1199,1200,2399,2400,6500,std::numeric_limits<uint32_t>::max(),0};
  unsigned fullCases=0,partialCases=0;
  for(const auto &palette:palettes)for(bool pl:{true,false})for(unsigned phase=0;phase<4;++phase){
    tft.bounds(0,0,800,480);tft.resetCounts();frame(P(phase),palette,pl,0);
    assert(tft.outside==0&&tft.clippedInk==0&&tft.abbreviated==0&&tft.textCalls==(phase?10u:9u));++fullCases;
    std::vector<uint16_t> retained=tft.pixels;
    for(uint32_t now:times){
      tft.pixels=retained;tft.bounds(246,291,72,16);tft.resetCounts();const auto before=hostAllocations;
      ws43b_boot::animate(tft,now,palette);
      assert(hostAllocations==before&&tft.outside==0&&tft.writes<1300&&tft.textCalls==0);
      retained=tft.pixels;tft.bounds(0,0,800,480);tft.resetCounts();frame(P(phase),palette,pl,now);
      assert(tft.pixels==retained&&tft.outside==0&&tft.clippedInk==0&&tft.abbreviated==0);++partialCases;
    }
    // A maximum-length, wide SSID is fitted on a UTF-8 boundary, not clipped.
    tft.resetCounts();frame(P(phase),palette,pl,0,"WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW");
    assert(tft.outside==0&&tft.clippedInk==0);
  }
  std::cout<<"{\"result\":\"PASS\",\"full_cases\":"<<fullCases<<",\"partial_comparisons\":"<<partialCases
    <<",\"partial_allocations\":0,\"partial_bounds\":[246,291,72,16],\"unsupported_glyphs\":0,\"clipped_text_pixels\":0}\n";
}
int main(int argc,char **argv){
  if(argc==2&&!std::strcmp(argv[1],"--verify")){verify();return 0;}
  if(argc==7&&!std::strcmp(argv[1],"--preview")){
    const unsigned phase=unsigned(std::stoul(argv[3]));assert(phase<4);
    ws43b_boot::Palette p{uint16_t(std::stoul(argv[5],nullptr,16)),ws43b_native::rgb(128,229,155),ws43b_native::ink,ws43b_native::dim};
    frame(ws43b_boot::Phase(phase),p,!std::strcmp(argv[4],"pl"),uint32_t(std::stoul(argv[6])));
    assert(tft.outside==0&&tft.clippedInk==0&&tft.abbreviated==0);tft.ppm(argv[2]);return 0;
  }
  std::cerr<<"Usage: --verify | --preview output.ppm phase pl|en themeHex phaseMs\n";return 2;
}
