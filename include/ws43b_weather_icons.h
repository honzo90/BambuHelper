#pragma once
#include <stdint.h>
#include <math.h>
namespace ws43b_weather_icon {
enum class Symbol { Unknown, Clear, Partial, Cloud, Fog, Drizzle, Rain, Ice, Snow, Storm, Hail };
inline Symbol classify(bool fresh,int code) {
  if(!fresh)return Symbol::Unknown;
  switch(code) {
    case 0:case 1:return Symbol::Clear;
    case 2:return Symbol::Partial;
    case 3:return Symbol::Cloud;
    case 45:case 48:return Symbol::Fog;
    case 51:case 53:case 55:return Symbol::Drizzle;
    case 56:case 57:case 66:case 67:return Symbol::Ice;
    case 61:case 63:case 65:case 80:case 81:case 82:return Symbol::Rain;
    case 71:case 73:case 75:case 77:case 85:case 86:return Symbol::Snow;
    case 95:case 97:return Symbol::Storm;
    case 96:case 99:return Symbol::Hail;
    default:return Symbol::Unknown;
  }
}
// Filled, softly lit symbols inside the existing 32 px box. Phase is elapsed
// milliseconds; zero gives a still frame. Only the silhouette is painted: no
// background tile, framebuffer or heap allocation is needed at any scale.
inline uint16_t shade(uint16_t a,uint16_t b,int weight) {
  const int r=(((a>>11)&31)*(256-weight)+((b>>11)&31)*weight)/256;
  const int g=(((a>>5)&63)*(256-weight)+((b>>5)&63)*weight)/256;
  const int bl=((a&31)*(256-weight)+(b&31)*weight)/256;
  return uint16_t((r<<11)|(g<<5)|bl);
}
template<class Surface> void draw(Surface &s,Symbol kind,int x,int y,int scale,bool night,
                                  uint16_t ink,uint16_t sun,uint16_t wet,unsigned phase=0) {
  if(scale<=0)return;
  auto line=[&](float a,float b,float c,float d,uint16_t color) {
    s.drawLine(x+int(lroundf(a*scale)),y+int(lroundf(b*scale)),
               x+int(lroundf(c*scale)),y+int(lroundf(d*scale)),color);
  };
  // Scanline silhouettes preserve the background through a crescent and around
  // rounded clouds. Shading follows their surface instead of adding a dark tile.
  auto shape=[&](float ox,float oy,int radius,bool moon,uint16_t top,uint16_t bottom) {
    for(int row=-radius*scale;row<=radius*scale;++row) {
      int start=-100;
      for(int col=-radius*scale;col<=radius*scale+1;++col) {
        const float dx=float(col)/scale,dy=float(row)/scale;
        const bool inside=col<=radius*scale && dx*dx+dy*dy<=radius*radius &&
          (!moon || (dx-radius*.55f)*(dx-radius*.55f)+(dy+radius*.35f)*(dy+radius*.35f)>radius*radius*.81f);
        if(inside && start==-100)start=col;
        if(!inside && start!=-100) {
          const uint16_t tone=shade(top,bottom,(row+radius*scale)*256/(2*radius*scale));
          s.drawLine(x+int(ox*scale)+start,y+int(oy*scale)+row,x+int(ox*scale)+col-1,y+int(oy*scale)+row,tone);
          start=-100;
        }
      }
    }
  };
  const float cycle=float(phase%6400u)*6.2831853f/6400;
  auto sky=[&](float ox,float oy,int radius) {
    if(night) {
      shape(ox,oy,radius+2,true,shade(ink,wet,12),shade(ink,wet,116));
      // The star occupies the open side of the crescent; the cutout itself is
      // untouched, including on a gradient or patterned parent background.
      const uint16_t star=shade(ink,wet,48);
      line(ox+radius-1,oy-radius+1,ox+radius+1,oy-radius+1,star);
      line(ox+radius,oy-radius,ox+radius,oy-radius+2,star);
      return;
    }
    const uint16_t ray=shade(sun,ink,int(36+18*sinf(cycle)));
    for(int i=0;i<8;++i) {
      const float a=i*.78539816f;
      line(ox+cosf(a)*(radius+2),oy+sinf(a)*(radius+2),
           ox+cosf(a)*(radius+4),oy+sinf(a)*(radius+4),ray);
    }
    shape(ox,oy,radius,false,shade(sun,ink,40),shade(sun,0xC301,44));
  };
  if(kind==Symbol::Unknown) {
    line(-5,0,5,0,shade(ink,wet,64));return;
  }
  if(kind==Symbol::Clear){sky(0,0,7);return;}
  if(kind==Symbol::Partial)sky(-6,-6,4);
  const float drift=phase?0.8f*sinf(cycle):0;
  const bool storm=kind==Symbol::Storm || kind==Symbol::Hail;
  const uint16_t top=shade(ink,wet,storm?92:18),bottom=shade(ink,0x528A,storm?170:112);
  for(int row=-11*scale;row<=4*scale;++row) {
    const float cy=float(row)/scale;
    int left=100,right=-100;
    for(int col=-14*scale;col<=14*scale;++col) {
      const float cx=float(col)/scale-drift;
      const bool inside=(cx+8)*(cx+8)+(cy+1)*(cy+1)<=25 ||
        cx*cx+(cy+4)*(cy+4)<=49 || (cx-8)*(cx-8)+cy*cy<=16 ||
        (cx>=-8&&cx<=8&&cy>=-1&&cy<=4);
      if(inside){if(left==100)left=col;right=col;}
    }
    if(right>=left)s.drawLine(x+left,y+row,x+right,y+row,
      shade(top,bottom,(row+11*scale)*256/(15*scale)));
  }
  // Three short curved glints pick out the separate cloud lobes. The broad
  // scanline shading stays cheap; these six strokes add depth at native size.
  const uint16_t glint=shade(top,ink,storm?82:142);
  line(drift-11,-3,drift-10,-4,glint);line(drift-10,-4,drift-8,-5,glint);
  line(drift-4,-8,drift-2,-9,glint);line(drift-2,-9,drift+1,-9,glint);
  line(drift+8,-3,drift+10,-2,glint);line(drift+10,-2,drift+11,-1,glint);
  if(kind==Symbol::Fog) {
    for(int i=0;i<3;++i){const float dx=1.2f*sinf(cycle+i);line(-11+dx+i*2,7+i*3,10+dx-i,7+i*3,shade(ink,wet,50+i*45));}
    return;
  }
  if(storm) {
    const uint16_t bolt=shade(sun,ink,int(24+16*sinf(cycle)));
    // A filled bolt with a steady, gently varying tone; never a flash.
    for(int i=0;i<3*scale;++i) {
      s.drawLine(x+2*scale-i,y+5*scale,x-2*scale-i,y+10*scale,bolt);
      s.drawLine(x+2*scale-i,y+9*scale,x-2*scale-i,y+15*scale,bolt);
    }
  }
  for(int i=0;i<3;++i) {
    const float a=-9+i*9;
    const float fall=float((phase+unsigned(i)*530u)%1800u)/1800;
    const float h=6+fall*6;
    const uint16_t drop=shade(wet,0x528A,int(112*fall*fall));
    if(kind==Symbol::Rain || (kind==Symbol::Storm&&i!=1)) {
      line(a,h,a-1.5f,h+2.5f,drop);
      line(a+1,h+.5f,a,h+2,shade(drop,ink,52));
    }
    if(kind==Symbol::Drizzle)line(a,h+1,a,h+2,drop);
    if(kind==Symbol::Snow) {
      const float dx=a+.7f*sinf(cycle+i),dy=7+fall*6;
      line(dx-1.5f,dy,dx+1.5f,dy,shade(ink,wet,50));
      line(dx,dy-1.5f,dx,dy+1.5f,shade(ink,wet,50));
    }
    if(kind==Symbol::Ice) {
      line(a,h,a-1,h+2,drop);line(a-1,h+3,a+1,h+3,shade(ink,wet,24));
    }
    if(kind==Symbol::Hail && i!=1)
      shape(a,8+fall*5,1,false,shade(ink,wet,36),shade(wet,0x528A,64));
  }
}
}
