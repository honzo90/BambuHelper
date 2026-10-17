#pragma once
#include "ws43b_visual_assets.h"
#include <math.h>
#include <string.h>
#if defined(ARDUINO)
#include <esp_heap_caps.h>
#endif

// Production 800x480 raster composition. The static scene is cached in PSRAM;
// animation only restores the union of the previous and current nozzle bounds.
namespace ws43b_native {
constexpr uint16_t rgb(unsigned r,unsigned g,unsigned b) {
  return uint16_t(((r>>3)<<11)|((g>>2)<<5)|(b>>3));
}
constexpr uint16_t ink=rgb(237,243,248), dim=rgb(171,186,203), line=rgb(48,68,87);
inline uint16_t mix(uint16_t a,uint16_t b,unsigned weight) {
  return ws43b_assets::blend(b,a,uint8_t(weight>255?255:weight));
}
struct Color { unsigned r,g,b; };
inline Color color(uint16_t value) {
  return {ws43b_assets::red(value),ws43b_assets::green(value),ws43b_assets::blue(value)};
}
inline Color interpolate(Color a,Color b,unsigned weight) {
  if(weight>255)weight=255;
  return {(a.r*(255-weight)+b.r*weight+127)/255,
          (a.g*(255-weight)+b.g*weight+127)/255,
          (a.b*(255-weight)+b.b*weight+127)/255};
}
// A stationary 4x4 Bayer pattern spreads RGB565 rounding error. Both background
// restoration and sprite alpha sampling use absolute display coordinates, so
// the pattern cannot move or leave a seam when a region is repainted.
inline uint16_t ordered(Color value,int x,int y) {
  static constexpr uint8_t bayer[16]={0,8,2,10,12,4,14,6,3,11,1,9,15,7,13,5};
  const unsigned threshold=bayer[(unsigned(y)&3u)*4+(unsigned(x)&3u)]*16+8;
  const auto quantize=[&](unsigned channel,unsigned levels) {
    const unsigned scaled=channel*levels,whole=scaled/255,remainder=scaled%255;
    return whole+(remainder>threshold&&whole<levels);
  };
  return uint16_t(quantize(value.r,31)<<11|quantize(value.g,63)<<5|quantize(value.b,31));
}
inline Color screenColor(int y,uint16_t theme) {
  const unsigned t=unsigned(y<0?0:y>479?479:y)*255/479;
  Color a{17,30,43},b{9,19,30};
  if(theme!=0x0084){a=interpolate(color(theme),a,48);b=interpolate(color(theme),{0,0,0},48);}
  return interpolate(a,b,t);
}
inline uint16_t textbg(int x,int y,uint16_t theme) {return ordered(screenColor(y,theme),x,y);}
inline uint16_t textbg(int y,uint16_t theme) {return textbg(0,y,theme);}
inline Color cardColor(int y,int top,int height,uint16_t theme,uint16_t tint=0,unsigned tintWeight=0) {
  const unsigned t=height<=1?0:unsigned(y<top?0:y>=top+height?height-1:y-top)*255/unsigned(height-1);
  Color a{28,44,58},b{17,32,44};
  if(theme!=0x0084){a=interpolate(color(theme),a,170);b=interpolate(color(theme),b,170);}
  Color value=interpolate(a,b,t);
  return tintWeight?interpolate(value,color(tint),tintWeight):value;
}
inline uint16_t cardbg(int x,int y,int top,int height,uint16_t theme,uint16_t tint=0,unsigned tintWeight=0) {
  return ordered(cardColor(y,top,height,theme,tint,tintWeight),x,y);
}
inline uint16_t cardbg(int y,int top,int height,uint16_t theme) {return cardbg(0,y,top,height,theme);}
template<class Canvas,class Background>
void rasterRect(Canvas &c,int x,int y,int w,int h,Background background) {
  uint16_t row[64];
  for(int py=y;py<y+h;++py)for(int px=x;px<x+w;) {
    const int count=x+w-px<64?x+w-px:64;
    for(int i=0;i<count;++i)row[i]=background(px+i,py);
    c.pushImage(px,py,count,1,reinterpret_cast<const lgfx::rgb565_t*>(row));px+=count;
  }
}
// Background callbacks are 4-periodic in X by construction. Evaluate only one
// Bayer period per row; keep the generic rasterRect for artwork/other callbacks.
template<class Canvas,class Background>
void gradientRect(Canvas &c,int x,int y,int w,int h,Background background) {
  if(w<=0||h<=0)return;
  uint16_t row[64];
  const int period=w<4?w:4;
  for(int py=y;py<y+h;++py) {
    for(int i=0;i<period;++i)row[i]=background(x+i,py);
    for(int i=period;i<64;++i)row[i]=row[i%period];
    for(int px=x;px<x+w;) {
      const int count=x+w-px<64?x+w-px:64;
      c.pushImage(px,py,count,1,reinterpret_cast<const lgfx::rgb565_t*>(row));px+=count;
    }
  }
}
template<class Canvas> void screen(Canvas &c,uint16_t theme) {
  gradientRect(c,0,0,800,480,[&](int x,int y){return textbg(x,y,theme);});
}
template<class Canvas> void card(Canvas &c,int x,int y,int w,int h,uint16_t theme) {
  // Rounded row spans avoid a second full fill and keep alpha backgrounds exact.
  for(int row=0;row<h;++row) {
    int inset=0;const int d=row<12?11-row:row>=h-12?row-(h-12):0;
    if(d>0)inset=12-int(sqrtf(float(144-d*d)));
    gradientRect(c,x+inset,y+row,w-2*inset,1,
      [&](int px,int py){return cardbg(px,py,y,h,theme);});
  }
  c.drawRoundRect(x,y,w,h,12,line);
}
template<class Canvas,class Background>
bool sprite(Canvas &c,ws43b_assets::Asset asset,int x,int y,Background bg,
            bool tint=false,uint16_t color=0) {
  return ws43b_assets::draw(asset,x,y,bg,
    [&](int px,int py,const uint16_t *pixels,size_t count) {
      c.pushImage(px,py,int(count),1,reinterpret_cast<const lgfx::rgb565_t*>(pixels));
    },tint,color);
}
struct Point { int x,y; };
struct Pixel {uint16_t color;uint8_t alpha;};
// Random row lookup reads the existing RLE asset directly from flash. Callers
// validate the descriptor once per draw or once when preparing a head cache.
inline Pixel sample(const ws43b_assets::Sprite &s,int x,int y,uint16_t tint,bool applyTint) {
  if(x<0||y<0||x>=s.width||y>=s.height)return {0,0};
  size_t at=s.rowOffsets[y],end=s.rowOffsets[y+1],sx=0;
  while(at<end) {
    sx+=ws43b_assets::read16(s.data+at);
    const uint16_t flags=ws43b_assets::read16(s.data+at+2);at+=4;
    const size_t count=flags&0x7fff;
    if(size_t(x)<sx)return {0,0};
    if(size_t(x)<sx+count) {
      at+=(size_t(x)-sx)*3;
      uint16_t value=ws43b_assets::read16(s.data+at);
      if(applyTint&&(flags&0x8000))value=ws43b_assets::recolor(value,tint);
      return {value,s.data[at+2]};
    }
    at+=count*3;sx+=count;
  }
  return {0,0};
}
// Bilinear interpolation uses premultiplied alpha, retaining thin edges without
// a black fringe when the approved raster is scaled uniformly in X and Y.
inline Pixel filtered(const ws43b_assets::Sprite &s,int x256,int y256,uint16_t tint,bool applyTint) {
  const int x=x256>=0?x256/256:(x256-255)/256,y=y256>=0?y256/256:(y256-255)/256;
  const unsigned fx=unsigned(x256-x*256),fy=unsigned(y256-y*256);
  const unsigned weights[4]={(256-fx)*(256-fy),fx*(256-fy),(256-fx)*fy,fx*fy};
  const Pixel values[4]={sample(s,x,y,tint,applyTint),sample(s,x+1,y,tint,applyTint),
                         sample(s,x,y+1,tint,applyTint),sample(s,x+1,y+1,tint,applyTint)};
  uint32_t alpha=0,r=0,g=0,b=0;
  for(unsigned i=0;i<4;++i) {
    const uint32_t weight=weights[i]*values[i].alpha;alpha+=weight;
    r+=weight*ws43b_assets::red(values[i].color);
    g+=weight*ws43b_assets::green(values[i].color);
    b+=weight*ws43b_assets::blue(values[i].color);
  }
  if(!alpha)return {0,0};
  return {rgb((r+alpha/2)/alpha,(g+alpha/2)/alpha,(b+alpha/2)/alpha),uint8_t((alpha+32768)/65536)};
}
template<class Canvas,class Background>
bool scaledSprite(Canvas &c,ws43b_assets::Asset asset,int x,int y,int w,int h,Background bg,
                  bool tint=false,uint16_t color=0) {
  const auto &s=ws43b_assets::descriptor(asset);
  if(w<=0||h<=0||!ws43b_assets::valid(s))return false;
  rasterRect(c,x,y,w,h,[&](int px,int py) {
    const auto p=filtered(s,((px-x)*2+1)*s.width*128/w-128,
                         ((py-y)*2+1)*s.height*128/h-128,color,tint);
    return ws43b_assets::blend(p.color,bg(px,py),p.alpha);
  });
  return true;
}
class Scene {
public:
  static constexpr int width=270,height=170;
  static constexpr int modelX=87,modelWidth=112,modelBase=140;
  static constexpr int plateX=54,plateY=69,plateWidth=176,plateHeight=86;
  static constexpr int headWidth=42,headHeight=55,headTipX=21,headTipY=50;
  static constexpr size_t headCachePixels=size_t(headWidth)*headHeight;
  // Storage belongs to the caller. A missing optional head cache preserves the
  // exact filtered rendering path; neither path allocates during a frame.
  explicit Scene(uint16_t *storage,Pixel *headStorage=nullptr):pixels(storage),headPixels(headStorage) {}
  // These are geometric points on the source raster, not a guessed perspective:
  // left(7,40), back(73,7), right(151,23), front(85,60). Their projected offsets
  // remain constant at every percentage. Only their vertical translation varies.
  static constexpr Point sourceRim[4]={{7,40},{73,7},{151,23},{85,60}};
  int wallPixels() const {return wallHeight;}
  int top() const {return modelTop;}
  bool hasHeadCache() const {return headReady;}
  Point rimPoint(unsigned index) const {
    const auto &p=sourceRim[index%4];
    return {modelX+(p.x*modelWidth+80)/160,modelTop+(p.y*modelWidth+80)/160};
  }
  bool compose(int percentage,uint16_t tint,uint16_t background,int x=228,int y=74) {
    if(!pixels)return false;
    progress=percentage<0?0:percentage>100?100:percentage;
    material=tint;theme=background;originX=x;originY=y;
    for(int py=0;py<height;++py) {
      uint16_t period[4];
      for(int px=0;px<4;++px)period[px]=cardbg(originX+px,originY+py,66,242,theme);
      for(int px=0;px<width;++px)pixels[py*width+px]=period[px&3];
    }
    auto bg=[&](int px,int py){return pixels[py*width+px];};
    struct Raster {
      uint16_t *data;
      void pushImage(int x,int y,int w,int h,const lgfx::rgb565_t *row) {
        for(int i=0;i<h;++i)memcpy(data+(y+i)*width+x,reinterpret_cast<const uint16_t*>(row)+i*w,size_t(w)*2);
      }
    } raster{pixels};
    if(!scaledSprite(raster,ws43b_assets::Asset::Plate,plateX,plateY,plateWidth,plateHeight,bg))return false;
    // A small, stationary contact shadow follows the two exposed bottom edges.
    // Its anchor is the fixed footprint, independent of model height or phase.
    // Most of the stroke is covered by the model; a soft fringe grounds it on
    // the plate without adding artwork or changing its approved perspective.
    Point contact[3];
    for(unsigned i=0;i<3;++i) {
      const auto &p=sourceRim[i==0?0:i==1?3:2];
      contact[i]={modelX+(p.x*modelWidth+80)/160+1,
                  modelBase-43+(p.y*modelWidth+80)/160+2};
    }
    for(int py=modelBase-33;py<modelBase+6;++py)for(int px=modelX;px<modelX+modelWidth+4;++px) {
      float distanceSquared=25.f;
      for(unsigned edge=0;edge<2;++edge) {
        const auto a=contact[edge],b=contact[edge+1];
        const int vx=b.x-a.x,vy=b.y-a.y;
        float t=float((px-a.x)*vx+(py-a.y)*vy)/float(vx*vx+vy*vy);
        if(t<0.f)t=0.f;if(t>1.f)t=1.f;
        const float dx=float(px-a.x)-t*vx,dy=float(py-a.y)-t*vy;
        const float d=dx*dx+dy*dy;if(d<distanceSquared)distanceSquared=d;
      }
      if(distanceSquared<16.f) {
        const float fade=1.f-distanceSquared/16.f;
        const unsigned opacity=unsigned(26.f*fade*fade+0.5f);
        const int index=py*width+px;
        pixels[index]=ws43b_assets::blend(0,pixels[index],uint8_t(opacity));
      }
    }
    // A readable symbolic height curve; the diamond footprint never shrinks.
    // A thin first layer at 0% grows into the approved near-square wall shape.
    wallHeight=2+int(46.f*sqrtf(float(progress)/100.f)+0.5f);
    modelTop=modelBase-43-wallHeight;
    const auto &s=ws43b_assets::descriptor(ws43b_assets::Asset::Model);
    if(!ws43b_assets::valid(s)||s.width!=160||s.height!=132)return false;
    for(int dy=0;dy<45+wallHeight;++dy)for(int dx=0;dx<modelWidth;++dx) {
      const int sx=((dx*2+1)*160*128/modelWidth)-128;
      // The front rim is V-shaped in screen coordinates. A horizontal slice
      // would still shear its sides. Split each column at its own front edge.
      const int seam=sx<=85*256?39*256+(sx-4*256)*22/81:61*256-(sx-85*256)*40/69;
      const int projectedSeam=seam*modelWidth/160;
      const int sy=dy*256<=projectedSeam?
        ((dy*2+1)*160*128/modelWidth)-128:
        seam+(dy*256-projectedSeam)*68/wallHeight;
      auto p=filtered(s,sx,sy,material,true);
      // Very gentle lower-face depth (at most 12/255). The complete upper rim
      // and its original material palette remain untouched at every progress.
      if(sy>seam+8*256) {
        unsigned shade=unsigned(sy-seam-8*256)*12/(60*256);
        if(shade>12)shade=12;
        p.color=ws43b_assets::blend(0,p.color,uint8_t(shade));
      }
      const int index=(modelTop+dy)*width+modelX+dx;
      pixels[index]=ws43b_assets::blend(p.color,pixels[index],p.alpha);
    }
    valid=true;previous={-1,-1};return true;
  }
  Point position(uint32_t phase) const {
    // Smooth travel follows the same unchanged projected diamond as the pixels.
    const unsigned cycle=phase%7200u,segment=cycle/1800u;
    float t=float(cycle%1800u)/1800.f;t=t*t*(3.f-2.f*t);
    const auto a=rimPoint(segment),b=rimPoint((segment+1)%4);
    const int tipX=int(a.x+(b.x-a.x)*t+0.5f);
    const int tipY=int(a.y+(b.y-a.y)*t+0.5f);
    return {tipX-headTipX,tipY-headTipY};
  }
  template<class Canvas>
  bool render(Canvas &c,int x,int y,int percentage,uint16_t tint,uint16_t background,
              uint32_t phase,bool force=false) {
    const int bounded=percentage<0?0:percentage>100?100:percentage;
    const bool changed=!valid||progress!=bounded||material!=tint||theme!=background||originX!=x||originY!=y;
    if(changed&&!compose(bounded,tint,background,x,y))return false;
    const auto p=position(phase);
    // Adjacent phase values can round to the same destination. Retained pixels
    // are already correct, so do no display work until the head actually moves.
    if(!force&&!changed&&previous.x==p.x&&previous.y==p.y)return true;
    int left=0,top=0,right=width,bottom=height;
    if(!force&&!changed&&previous.x>=0) {
      left=p.x<previous.x?p.x:previous.x;top=p.y<previous.y?p.y:previous.y;
      right=(p.x>previous.x?p.x:previous.x)+headWidth;
      bottom=(p.y>previous.y?p.y:previous.y)+headHeight;
    }
    if(left<0)left=0;if(top<0)top=0;if(right>width)right=width;if(bottom>height)bottom=height;
    for(int row=top;row<bottom;++row)
      c.pushImage(x+left,y+row,right-left,1,
        reinterpret_cast<const lgfx::rgb565_t*>(pixels+row*width+left));
    const auto bg=[&](int px,int py){return pixels[(py-y)*width+px-x];};
    if(headPixels) {
      if(!headReady) {
        const auto &s=ws43b_assets::descriptor(ws43b_assets::Asset::Head);
        if(!ws43b_assets::valid(s))return false;
        for(int py=0;py<headHeight;++py)for(int px=0;px<headWidth;++px)
          headPixels[py*headWidth+px]=filtered(s,(px*2+1)*s.width*128/headWidth-128,
              (py*2+1)*s.height*128/headHeight-128,0,false);
        headReady=true;
      }
      rasterRect(c,x+p.x,y+p.y,headWidth,headHeight,[&](int px,int py) {
        const auto &sample=headPixels[(py-y-p.y)*headWidth+px-x-p.x];
        return ws43b_assets::blend(sample.color,bg(px,py),sample.alpha);
      });
    } else if(!scaledSprite(c,ws43b_assets::Asset::Head,x+p.x,y+p.y,headWidth,headHeight,bg))return false;
    previous=p;return true;
  }
private:
  uint16_t *pixels;
  Pixel *headPixels;
  bool valid=false,headReady=false;
  int progress=0,wallHeight=2,modelTop=95,originX=228,originY=74;
  uint16_t material=0,theme=0;
  Point previous{-1,-1};
};
#if defined(ARDUINO)
inline bool &heroHeadCacheState() {static bool ready=false;return ready;}
// The scheduler can select a faster cadence only after successful preparation.
// Reading readiness cannot allocate and stays false when external RAM is full.
inline bool heroHeadCacheReady() {return heroHeadCacheState();}
template<class Canvas>
bool hero(Canvas &c,int x,int y,int progress,uint16_t color,uint16_t background,
          uint32_t phase,bool force=false) {
  // One attempt, in external RAM only: allocation failure selects the compact
  // shared-artwork renderer without consuming the MQTT/TLS internal heap.
  static auto *storage=static_cast<uint16_t*>(heap_caps_malloc(
    Scene::width*Scene::height*sizeof(uint16_t),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
  // Optional 42x55 RGB565+alpha samples (9,240 bytes with this ABI). There is
  // deliberately no internal-heap retry and no repeated allocation attempt.
  static auto *headStorage=storage?static_cast<Pixel*>(heap_caps_malloc(
    Scene::headCachePixels*sizeof(Pixel),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT)):nullptr;
  static Scene scene(storage,headStorage);
  const bool result=scene.render(c,x,y,progress,color,background,phase,force);
  heroHeadCacheState()=scene.hasHeadCache();
  return result;
}
#endif
} // namespace ws43b_native
