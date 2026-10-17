#pragma once
#include <stdint.h>
#include <math.h>
// Native, scalable line art; no bitmap allocations or per-frame asset decoding.
namespace ws43b_style {
constexpr uint16_t background=0x0084, card=0x1106, border=0x21EA;
constexpr uint16_t ink=0xF7BE, dim=0xA5D8, mint=0x67B6;
enum class Icon { Printer, Spool, Details, Settings, Clock, Weather, Network, Bed, Nozzle, Chamber, Check, Pause, Alert };
// Shared by the device and native preview: a quiet, theme-tinted selection pill.
template<class Canvas> void navigationSelection(Canvas &c,int x,uint16_t accent,uint16_t base) {
  const auto tint=[&](int amount) -> uint16_t {
    const int r=(((base>>11)&31)*(256-amount)+((accent>>11)&31)*amount)/256;
    const int g=(((base>>5)&63)*(256-amount)+((accent>>5)&63)*amount)/256;
    const int b=((base&31)*(256-amount)+(accent&31)*amount)/256;
    return uint16_t((r<<11)|(g<<5)|b);
  };
  c.fillRoundRect(x,436,182,38,11,tint(36));
  c.drawRoundRect(x,436,182,38,11,tint(84));
}
template<class Canvas> void icon(Canvas &c,Icon kind,int x,int y,uint16_t color) {
  const uint16_t shade=uint16_t((color&0xF7DEu)>>1);
  switch(kind) {
    case Icon::Printer:
      // Compact enclosure with a recessed window and a small printed object.
      c.fillRoundRect(x-13,y-14,27,29,5,shade);
      c.fillRoundRect(x-13,y-14,24,27,4,color);
      c.fillRoundRect(x-10,y-9,18,19,2,background);
      c.fillRect(x-9,y-8,16,2,shade);
      c.fillRoundRect(x-3,y-6,5,5,1,color);
      c.fillTriangle(x-3,y-1,x+2,y-1,x,y+2,color);
      c.fillRoundRect(x-5,y+5,10,3,1,color);
      c.fillRect(x-8,y+9,14,1,shade);
      break;
    case Icon::Spool:
      // Perspective spool with filled flanges instead of tiny outlined holes.
      c.fillEllipse(x-7,y,7,13,shade);
      c.drawEllipse(x-7,y,7,13,color);
      c.fillRoundRect(x-7,y-10,16,21,3,shade);
      for(int i=-5;i<7;i+=3)c.drawEllipse(x+i,y,4,10,color);
      c.fillEllipse(x+7,y,8,14,color);
      c.fillEllipse(x+7,y,5,11,shade);
      c.fillEllipse(x+7,y,2,4,background);
      break;
    case Icon::Details:
      // A clear stack of data cards, using the same solid rounded shapes.
      c.fillRoundRect(x-9,y-14,23,26,4,shade);
      c.fillRoundRect(x-14,y-10,24,25,4,color);
      c.fillRoundRect(x-10,y-5,4,4,1,background);
      c.fillRoundRect(x-3,y-5,9,3,1,background);
      c.fillRoundRect(x-10,y+2,16,2,1,shade);
      c.fillRoundRect(x-10,y+7,11,2,1,shade);
      break;
    case Icon::Settings: {
      // Broad filled gear ring; the hub stays open without a background tile.
      for(int i=0;i<64;++i) {
        const float a=i*6.2831853f/64,b=(i+1)*6.2831853f/64;
        const int r=(i%8<3||i%8>6)?15:12;
        const int rr=((i+1)%8<3||(i+1)%8>6)?15:12;
        const int ax=x+int(cosf(a)*r),ay=y+int(sinf(a)*r);
        const int bx=x+int(cosf(b)*rr),by=y+int(sinf(b)*rr);
        const int ix=x+int(cosf(a)*6),iy=y+int(sinf(a)*6);
        const int jx=x+int(cosf(b)*6),jy=y+int(sinf(b)*6);
        const uint16_t face=i<32?shade:color;
        c.fillTriangle(ax,ay,bx,by,ix,iy,face);
        c.fillTriangle(ix,iy,bx,by,jx,jy,face);
      }
      c.drawCircle(x,y,6,color);break;
    }
    case Icon::Clock:
      c.drawCircle(x,y,14,color);c.drawLine(x,y,x,y-9,color);c.drawLine(x,y,x+8,y+4,color);break;
    case Icon::Weather:
      c.drawCircle(x-8,y+2,7,color);c.drawCircle(x,y-3,10,color);c.drawCircle(x+10,y+3,6,color);
      c.fillRect(x-10,y,22,9,card);c.fillRect(x-4,y-7,8,16,card);
      c.drawFastHLine(x-9,y+9,20,color);break;
    case Icon::Network:
      c.drawCircle(x,y,13,color);c.drawEllipse(x,y,6,13,color);c.drawFastHLine(x-12,y,24,color);break;
    case Icon::Nozzle:
      c.drawRect(x-9,y-14,18,16,color);c.drawLine(x-9,y+2,x,y+14,color);c.drawLine(x+9,y+2,x,y+14,color);break;
    case Icon::Bed:
      c.drawRoundRect(x-14,y+4,28,8,2,color);
      for(int i=-1;i<=1;++i){c.drawLine(x+i*8,y,x+i*8-2,y-6,color);c.drawLine(x+i*8-2,y-6,x+i*8,y-12,color);}break;
    case Icon::Chamber:
      c.drawRoundRect(x-13,y-14,26,28,3,color);c.drawRoundRect(x-8,y-8,16,18,2,color);break;
    case Icon::Check:
      c.drawCircle(x,y,15,color);c.drawLine(x-8,y,x-2,y+6,color);c.drawLine(x-2,y+6,x+9,y-7,color);break;
    case Icon::Pause:
      c.drawCircle(x,y,15,color);c.fillRect(x-6,y-7,4,14,color);c.fillRect(x+2,y-7,4,14,color);break;
    case Icon::Alert:
      c.drawTriangle(x,y-16,x-16,y+13,x+16,y+13,color);c.drawFastVLine(x,y-7,11,color);c.fillCircle(x,y+8,1,color);break;
  }
}
// 36x34 shaded equipment miniatures, matching the isometric print scene.
template<class Canvas> void thermal(Canvas &c,int channel,int x,int y,uint16_t state) {
  const uint16_t metal=0x9CF3,dark=0x2946,edge=0x528A;
  if(channel==0) {
    c.fillRoundRect(x+6,y+1,24,20,3,dark);
    c.fillRoundRect(x+8,y+2,16,18,2,metal);
    c.fillRect(x+24,y+4,4,14,0x4209);
    for(int i=0;i<3;++i)c.drawFastHLine(x+11,y+6+i*4,10,dark);
    c.fillRect(x+13,y+21,10,4,0x8B65);
    c.fillTriangle(x+13,y+25,x+23,y+25,x+18,y+32,0xDCAA);
    c.drawLine(x+14,y+25,x+18,y+31,0xF6B3);
    c.fillRect(x+9,y+17,13,2,state);
  } else if(channel==1) {
    c.fillTriangle(x+1,y+20,x+25,y+28,x+35,y+16,dark);
    c.fillTriangle(x+1,y+20,x+35,y+16,x+11,y+8,dark);
    c.fillTriangle(x+1,y+17,x+25,y+25,x+35,y+13,0x632C);
    c.fillTriangle(x+1,y+17,x+35,y+13,x+11,y+5,0x632C);
    c.drawLine(x+2,y+18,x+25,y+26,metal);
    c.drawLine(x+25,y+26,x+35,y+14,edge);
    c.drawLine(x+6,y+17,x+24,y+23,state);
    c.drawLine(x+10,y+12,x+28,y+18,state);
  } else {
    c.fillTriangle(x+3,y+8,x+25,y+10,x+33,y+3,metal);
    c.fillTriangle(x+3,y+8,x+33,y+3,x+11,y+1,metal);
    c.fillTriangle(x+25,y+10,x+33,y+3,x+33,y+27,dark);
    c.fillTriangle(x+25,y+10,x+33,y+27,x+25,y+33,dark);
    c.fillRect(x+3,y+8,23,25,edge);
    c.fillRoundRect(x+6,y+11,17,19,2,0x0864);
    c.drawFastHLine(x+8,y+13,13,state);
    c.drawLine(x+8,y+25,x+19,y+27,metal);
    c.drawLine(x+19,y+27,x+22,y+23,edge);
    c.fillRect(x+20,y+17,1,5,metal);
  }
}
// 64x64 reference spool in perspective; scale=1 compact, scale=2 AMS detail.
template<class Canvas> void spool(Canvas &c,int x,int y,float scale,uint16_t filament,bool known) {
  const float s=scale;
  if(!known) {
    c.drawEllipse(x+20*s,y+32*s,12*s,26*s,dim);
    c.drawEllipse(x+43*s,y+32*s,12*s,26*s,dim);
    c.drawEllipse(x+43*s,y+32*s,4*s,8*s,dim);
    c.drawLine(x+20*s,y+6*s,x+43*s,y+6*s,dim);
    c.drawLine(x+20*s,y+58*s,x+43*s,y+58*s,dim);
    return;
  }
  // Dark flanges and filament-tinted winding; avoid bright wireframe rings.
  const uint16_t edge=0x528A, flange=0x0864;
  const uint16_t shade=filament==0?0x2104:
    uint16_t((((filament>>11)*3/4)<<11)|(((((filament>>5)&63)*3/4))<<5)|((filament&31)*3/4));
  c.fillEllipse(x+18*s,y+32*s,13*s,28*s,flange);
  c.drawEllipse(x+18*s,y+32*s,13*s,28*s,edge);
  for(int n=21;n<=43;n+=2) {
    c.fillEllipse(x+n*s,y+32*s,11*s,25*s,filament);
    c.drawEllipse(x+n*s,y+32*s,11*s,25*s,shade);
  }
  c.fillEllipse(x+45*s,y+32*s,13*s,28*s,flange);
  c.drawEllipse(x+45*s,y+32*s,13*s,28*s,edge);
  c.drawEllipse(x+45*s,y+32*s,4*s,9*s,edge);
}
}
