#pragma once
#include <stdint.h>
namespace ws43b_weather_bg {
enum class Kind { Neutral, Clear, Cloud, Fog, Rain, Snow, Storm };
// Open-Meteo WMO codes: https://open-meteo.com/en/docs
inline Kind classify(bool enabled, bool fresh, int code) {
  if (!enabled || !fresh) return Kind::Neutral;
  switch (code) {
    case 0: case 1: return Kind::Clear;
    case 2: case 3: return Kind::Cloud;
    case 45: case 48: return Kind::Fog;
    case 51: case 53: case 55: case 56: case 57:
    case 61: case 63: case 65: case 66: case 67:
    case 80: case 81: case 82: return Kind::Rain;
    case 71: case 73: case 75: case 77: case 85: case 86: return Kind::Snow;
    case 95: case 96: case 97: case 99: return Kind::Storm;
    default: return Kind::Neutral;
  }
}
inline uint16_t blend(uint16_t a,uint16_t b,unsigned weight) {
  return uint16_t((((((a>>11)&31)*(100-weight)+((b>>11)&31)*weight)/100)<<11) |
                  (((((a>>5)&63)*(100-weight)+((b>>5)&63)*weight)/100)<<5) |
                  (((a&31)*(100-weight)+(b&31)*weight)/100));
}
// Fixed geometry; no timer, allocations, bitmap assets or additional framebuffer.
// Called before opaque cards and text. The configured background remains the base.
template<class Surface> void draw(Surface &s,Kind kind,bool night,uint16_t base) {
  if(kind==Kind::Neutral)return;
  const uint16_t sky=blend(base,night?0x0845:kind==Kind::Clear?0x2946:0x19A9,30);
  const uint16_t cloud=blend(sky,night?0x3A0B:0x638F,22);
  const uint16_t detail=blend(sky,night?0x7BCF:0x9491,30);
  s.fillRect(0,0,800,480,sky);
  auto clouds=[&](int x,int y,int scale) {
    s.fillCircle(x-24*scale,y,17*scale,cloud);
    s.fillCircle(x,y-10*scale,24*scale,cloud);
    s.fillCircle(x+28*scale,y,18*scale,cloud);
    s.fillRoundRect(x-38*scale,y-2*scale,82*scale,20*scale,8*scale,cloud);
  };
  // Clear weather uses only the sky tint here; its symbol sits beside temperature.
  if(kind!=Kind::Clear) {
    clouds(405,35,1);clouds(658,445,2);
    if(kind==Kind::Fog) {
      for(int y=432;y<=464;y+=16)s.drawFastHLine(260,y,180,cloud);
    }
    const int drops[][2]={{295,51},{456,50},{491,179},{10,248},{790,212},{580,458},{716,454}};
    for(const auto &p:drops) {
      if(kind==Kind::Rain || kind==Kind::Storm)s.drawLine(p[0],p[1],p[0]-4,p[1]+9,detail);
      if(kind==Kind::Snow) {
        s.drawFastHLine(p[0]-2,p[1],5,detail);s.drawFastVLine(p[0],p[1]-2,5,detail);
      }
    }
    if(kind==Kind::Storm) {
      s.drawLine(660,430,652,443,detail);s.drawLine(652,443,662,443,detail);
      s.drawLine(662,443,653,457,detail);
    }
  }
}
// Compact 28 px weather symbol. The crescent only paints its lit portion,
// preserving the existing sky underneath instead of erasing with a flat color.
template<class Surface> void clearIcon(Surface &s,int x,int y,bool night,uint16_t color) {
  if(night) {
    for(int dy=-11;dy<=11;++dy)
      for(int dx=-11;dx<=11;++dx)
        if(dx*dx+dy*dy<=121 && (dx-5)*(dx-5)+(dy+3)*(dy+3)>100)
          s.drawFastHLine(x+dx,y+dy,1,color);
  } else {
    s.fillCircle(x,y,6,color);
    const int rays[][4]={{0,-10,0,-13},{7,-7,10,-10},{10,0,13,0},{7,7,10,10},
                        {0,10,0,13},{-7,7,-10,10},{-10,0,-13,0},{-7,-7,-10,-10}};
    for(const auto &r:rays)s.drawLine(x+r[0],y+r[1],x+r[2],y+r[3],color);
  }
}

}
