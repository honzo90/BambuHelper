#pragma once
#include <stddef.h>
#include <stdint.h>
#include <limits.h>

namespace ws43b_assets {
// Each row is [skip:u16le, count:u15le|material:bit15, count*(rgb565:u16le,alpha:u8)].
// Transparent pixels are absent; row offsets delimit rows without sentinels.
struct Sprite {
  uint16_t width, height;
  const uint32_t *rowOffsets;
  size_t rowOffsetCount;
  const uint8_t *data;
  size_t dataSize;
};

#include "ws43b_visual_assets_data.h"

inline uint16_t read16(const uint8_t *p) {
  return uint16_t(p[0]) | uint16_t(uint16_t(p[1]) << 8);
}
inline uint8_t red(uint16_t c) { const unsigned v=c>>11;return uint8_t((v<<3)|(v>>2)); }
inline uint8_t green(uint16_t c) { const unsigned v=(c>>5)&63;return uint8_t((v<<2)|(v>>4)); }
inline uint8_t blue(uint16_t c) { const unsigned v=c&31;return uint8_t((v<<3)|(v>>2)); }
inline uint16_t rgb565(unsigned r,unsigned g,unsigned b) {
  return uint16_t(((r>>3)<<11)|((g>>2)<<5)|(b>>3));
}
inline uint16_t blend(uint16_t foreground,uint16_t background,uint8_t alpha) {
  if(alpha==255)return foreground;
  if(alpha==0)return background;
  const unsigned inverse=255-alpha;
  return rgb565((red(foreground)*alpha+red(background)*inverse+127)/255,
                (green(foreground)*alpha+green(background)*inverse+127)/255,
                (blue(foreground)*alpha+blue(background)*inverse+127)/255);
}
inline uint16_t recolor(uint16_t source,uint16_t tint) {
  unsigned shade=red(source);
  if(green(source)>shade)shade=green(source);
  if(blue(source)>shade)shade=blue(source);
  unsigned brightest=red(tint);
  if(green(tint)>brightest)brightest=green(tint);
  if(blue(tint)>brightest)brightest=blue(tint);
  // Dark material still reflects a little neutral light. Preserve the source
  // layer shading, capped at 20/255 for black; fade it away at a 48/255 tint.
  // This function is only called for masked material, never gray/metal pixels.
  const unsigned light=brightest<48?((48-brightest)*20*shade+6120)/12240:0;
  return rgb565((red(tint)*shade+127)/255+light,
                (green(tint)*shade+127)/255+light,
                (blue(tint)*shade+127)/255+light);
}

// Validates all encoded bounds before draw emits anything. No reads from an
// untrusted offset until its enclosing range, length and count have been checked.
inline bool valid(const Sprite &s) {
  if(!s.width || s.width>256 || !s.height || s.height>1024 || !s.rowOffsets ||
     !s.data || s.rowOffsetCount!=size_t(s.height)+1 ||
     s.rowOffsets[0]!=0 || s.rowOffsets[s.height]!=s.dataSize)return false;
  for(size_t y=0;y<s.height;++y) {
    size_t at=s.rowOffsets[y],end=s.rowOffsets[y+1],x=0;
    if(at>end || end>s.dataSize)return false;
    while(at<end) {
      if(end-at<4)return false;
      const size_t skip=read16(s.data+at),count=read16(s.data+at+2)&0x7fff;at+=4;
      if(skip>s.width-x || !count)return false;
      x+=skip;
      if(count>s.width-x || count>(end-at)/3)return false;
      for(size_t i=0;i<count;++i) {
        if(s.data[at+i*3+2]==0)return false;
      }
      at+=count*3;x+=count;
    }
  }
  return true;
}

// Background(x,y) returns host-order RGB565. Sink(x,y,pixels,count) consumes a
// contiguous opaque row span synchronously. Only 64 uint16 pixels live on stack;
// sprites up to 256 pixels wide are emitted in chunks. No heap allocation.
template<class Background,class Sink>
bool draw(const Sprite &s,int originX,int originY,Background background,Sink sink,
          bool applyTint=false,uint16_t tint=0) {
  if(!valid(s) || originX>INT_MAX-int(s.width-1) || originY>INT_MAX-int(s.height-1))return false;
  uint16_t pixels[64];
  for(size_t y=0;y<s.height;++y) {
    size_t at=s.rowOffsets[y],end=s.rowOffsets[y+1],x=0;
    while(at<end) {
      x+=read16(s.data+at);const uint16_t run=read16(s.data+at+2);
      const bool material=(run&0x8000)!=0;size_t remaining=run&0x7fff;at+=4;
      while(remaining) {
        const size_t count=remaining>64?64:remaining;
        for(size_t i=0;i<count;++i) {
          const uint8_t *p=s.data+at+i*3;
          uint16_t color=read16(p);
          if(applyTint && material)color=recolor(color,tint);
          const int px=originX+int(x+i),py=originY+int(y);
          pixels[i]=p[2]==255?color:blend(color,background(px,py),p[2]);
        }
        sink(originX+int(x),originY+int(y),pixels,count);
        at+=count*3;x+=count;remaining-=count;
      }
    }
  }
  return true;
}
template<class Background,class Sink>
bool draw(Asset asset,int x,int y,Background background,Sink sink,
          bool applyTint=false,uint16_t tint=0) {
  return draw(descriptor(asset),x,y,background,sink,applyTint,tint);
}
} // namespace ws43b_assets
