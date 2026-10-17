#pragma once
#include "ws43b_native_scene.h"

// One artwork family for the 43B dashboard, menus and status screens.
// Preserve aspect ratio and composite alpha against the caller's actual canvas.
// No framebuffer, allocation, clip change or display readback is needed.
namespace ws43b_ui_icons {
template<class Canvas,class Background>
bool draw(Canvas &canvas,ws43b_assets::Asset asset,int cx,int cy,int extent,
          Background background,bool tint=false,uint16_t color=0) {
  if(extent<1 || extent>96)return false;
  const auto &s=ws43b_assets::descriptor(asset);
  if(!ws43b_assets::valid(s))return false;
  const int major=s.width>s.height?s.width:s.height;
  const int w=(int(s.width)*extent+major/2)/major;
  const int h=(int(s.height)*extent+major/2)/major;
  if(w<1 || h<1)return false;
  const int x=cx-w/2,y=cy-h/2;
  if(w==s.width && h==s.height)
    return ws43b_native::sprite(canvas,asset,x,y,background,tint,color);
  return ws43b_native::scaledSprite(canvas,asset,x,y,w,h,background,tint,color);
}
template<class Canvas>
bool flat(Canvas &canvas,ws43b_assets::Asset asset,int cx,int cy,int extent,
          uint16_t background,bool tint=false,uint16_t color=0) {
  return draw(canvas,asset,cx,cy,extent,[=](int,int){return background;},tint,color);
}
} // namespace ws43b_ui_icons
