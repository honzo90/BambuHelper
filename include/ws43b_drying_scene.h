#pragma once
#include <stdint.h>
#include <math.h>
#include "ws43b_ui_icons.h"

// Symbolic airflow, not a measurement of fan speed or drying progress.
// The same shaded spool as the AMS slots, with air passing around it.
// Fixed work and no allocations; AMS and both saver sizes share this scene.
namespace ws43b_drying_scene {
inline uint16_t mix(uint16_t a,uint16_t b,unsigned weight) {
  const unsigned inv=255-weight;
  return ((((a>>11)*inv+(b>>11)*weight)/255)<<11)
       | (((((a>>5)&63)*inv+((b>>5)&63)*weight)/255)<<5)
       | (((a&31)*inv+(b&31)*weight)/255);
}
template<class Canvas>
void draw(Canvas &c,int cx,int cy,int radius,uint32_t now,
          uint16_t accent,uint16_t track,uint16_t ink,uint16_t bg) {
  if(radius<1 || radius>80)return;
  (void)ink;
  constexpr float tau=6.2831853f;
  const float phase=float(now%4800u)/4800.0f;
  auto px=[&](float x){return cx+int(x*radius);};
  auto py=[&](float y){return cy+int(y*radius);};
  // Two continuous ribbons. Only the soft highlight travels: no orbiting dots.
  auto air=[&](bool front) {
    for(int lane=0;lane<2;++lane) {
      for(int i=0;i<24;++i) {
        const float u=float(i)/24,v=float(i+1)/24;
        auto y=[&](float t) {
          // Keep the upper air outside the alpha-composited sprite rectangle.
          // Its transparent margins must not cut a moving ribbon in half.
          return front?.65f+lane*.16f-.20f*t+.085f*sinf(t*tau+lane*.8f)
            :-.90f-lane*.08f-.03f*t+.03f*sinf(t*tau+lane*.8f);
        };
        float travel=u-phase+lane*.31f;
        travel-=floorf(travel);
        const float pulse=.5f+.5f*cosf(travel*tau);
        const float fade=sinf(u*3.14159265f);
        const unsigned strength=unsigned((55+175*pulse*pulse*pulse)*fade);
        const int x=px(-1.05f+2.10f*u),xx=px(-1.05f+2.10f*v);
        const int yy=py(y(u)),yyy=py(y(v));
        if(radius>=40)c.drawLine(x,yy+1,xx,yyy+1,mix(bg,accent,strength/4));
        c.drawLine(x,yy,xx,yyy,mix(bg,accent,strength));
      }
    }
  };
  // Soft grounded shadow, with a neutral spool (no invented filament colour).
  c.fillEllipse(cx,py(.78f),int(radius*.78f),int(radius*.13f),mix(bg,track,45));
  c.fillEllipse(cx,py(.78f),int(radius*.59f),int(radius*.065f),bg);
  air(false);
  int extent=(radius*69+21)/42;
  if(extent>96)extent=96;
  // Drying concerns the AMS unit, not necessarily the selected printing tray.
  // Neutral filament avoids claiming an unreported colour or remaining amount.
  ws43b_ui_icons::flat(c,ws43b_assets::Asset::Spool,cx,cy,extent,bg,true,0xBDF7);
  air(true);
}
} // namespace ws43b_drying_scene
