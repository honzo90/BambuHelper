#pragma once
#include <stdint.h>
#include <math.h>
#include "ws43b_native_scene.h"

// Compact symbolic scenes use the exact same artwork as the native dashboard.
// They describe an activity, never measured toolhead positions or G-code paths.
namespace ws43b_print_scene {
inline uint16_t mix(uint16_t a,uint16_t b,unsigned n) {return ws43b_native::mix(a,b,n);}
// Compatibility helpers no longer impose the old unrelated blue gradient.
inline uint16_t background(int,uint16_t base) {return base;}
template<class C> void patch(C &c,int x,int y,int w,int h,uint16_t base) {c.fillRect(x,y,w,h,base);}
template<class C> void card(C &c,uint16_t base,uint16_t edge) {
  c.fillRoundRect(24,84,460,193,14,base);c.drawRoundRect(24,84,460,193,14,edge);
}

enum class Mode { Printing, Cleaning, Leveling, Calibration };
inline constexpr uint32_t cleaningPeriodMs=3200;
enum class CleaningPhase { Approach, Wipe, Lift, Retract, Rest };
struct CleaningPose {
  float tipX,tipY;
  bool contact;
  CleaningPhase phase;
};
// Logical coordinates shared by both raster sizes. Each leg eases to rest at
// its endpoints: three complete wipes, a vertical lift, then a short retreat.
inline CleaningPose cleaningPose(uint32_t elapsed) {
  const unsigned time=elapsed%cleaningPeriodMs;
  const auto ease=[](float t){return t*t*(3.f-2.f*t);};
  if(time<600u) {
    const float t=ease(float(time)/600.f);
    return {28.f+15.f*t,52.f+13.f*t,false,CleaningPhase::Approach};
  }
  if(time<2400u) {
    const unsigned leg=(time-600u)/300u;
    float t=ease(float((time-600u)%300u)/300.f);
    if(leg&1u)t=1.f-t;
    return {43.f+30.f*t,65.f+10.f*t,true,CleaningPhase::Wipe};
  }
  if(time<2700u) {
    const float t=ease(float(time-2400u)/300.f);
    return {43.f,65.f-9.f*t,false,CleaningPhase::Lift};
  }
  if(time<2950u) {
    const float t=ease(float(time-2700u)/250.f);
    return {43.f-15.f*t,56.f-4.f*t,false,CleaningPhase::Retract};
  }
  return {28.f,52.f,false,CleaningPhase::Rest};
}
struct CacheStorage {
  uint16_t pixels[168*156];
  ws43b_native::Pixel head[40*52];
};

// One caller-owned optional cache. The no-cache renderer uses the same sampler
// and a bounded 64-pixel output row; no heap, framebuffer or display readback.
class Renderer {
  using Point=ws43b_native::Point;
  using Pixel=ws43b_native::Pixel;
  struct Geometry {
    int scale=2,width=112,height=104,plateY=44,plateWidth=112,plateHeight=55;
    int modelX=21,modelWidth=71,modelBase=89,modelTop=61,modelHeight=29,wallHeight=1;
    int headWidth=27,headHeight=35,tipX=14,tipY=32;
    int k(int value) const {return value*scale/2;}
    Point rim(unsigned index) const {
      const auto p=ws43b_native::Scene::sourceRim[index%4];
      return {modelX+(p.x*modelWidth+80)/160,modelTop+(p.y*modelWidth+80)/160};
    }
  } geometry;
  struct Stroke {Point a,b;uint16_t color;int radius;};
  struct Frame {
    Point head{};
    Stroke strokes[12]{};unsigned count=0;
    Point probe{};bool showProbe=false,brushContact=false;
    int left=0,top=0,right=0,bottom=0;
  };
  CacheStorage *storage;
  bool assetsReady=false,composed=false;
  int headScale=0,originX=0,originY=0;
  Mode mode=Mode::Printing;
  unsigned progress=0,compositions=0,headPreparations=0,filterSamples=0;
  uint16_t filament=0,accent=0,base=0;
  bool dashboard=false;

  static bool lineContains(int x,int y,Point a,Point b,int radius) {
    const int vx=b.x-a.x,vy=b.y-a.y,dx=x-a.x,dy=y-a.y;
    const int length=vx*vx+vy*vy,along=dx*vx+dy*vy;
    if(!length||along<=0)return dx*dx+dy*dy<=radius*radius;
    if(along>=length){const int ex=x-b.x,ey=y-b.y;return ex*ex+ey*ey<=radius*radius;}
    const int cross=dx*vy-dy*vx;
    return int64_t(cross)*cross<=int64_t(radius)*radius*length;
  }
  // Integer pixel-centre distance; dimensions are at most 168x156.
  static bool ellipseContains(int x,int y,Point center,int rx,int ry) {
    const int dx=x-center.x,dy=y-center.y;
    return int64_t(dx)*dx*ry*ry+int64_t(dy)*dy*rx*rx<=int64_t(rx)*rx*ry*ry;
  }
  Pixel filtered(const ws43b_assets::Sprite &s,int x,int y,uint16_t tint=0,bool apply=false) {
    ++filterSamples;return ws43b_native::filtered(s,x,y,tint,apply);
  }
  uint16_t backdrop(int x,int y) const {
    return dashboard?ws43b_native::cardbg(originX+x,originY+y,66,242,base):base;
  }
  void setGeometry(int scale,unsigned percent) {
    geometry.scale=scale;
    auto &g=geometry;
    g.width=g.k(112);g.height=g.k(104);
    g.plateY=g.k(44);g.plateWidth=g.width;g.plateHeight=g.k(55);
    g.modelX=g.k(21);g.modelWidth=g.k(71);g.modelBase=g.k(89);
    const int nativeWall=2+int(46.f*sqrtf(float(percent)/100.f)+0.5f);
    g.wallHeight=(nativeWall*g.modelWidth+56)/112;
    if(g.wallHeight<1)g.wallHeight=1;
    g.modelTop=g.modelBase-(43*g.modelWidth+56)/112-g.wallHeight;
    g.modelHeight=(45*g.modelWidth+56)/112+g.wallHeight;
    g.headWidth=g.k(27);g.headHeight=g.k(35);
    g.tipX=(g.headWidth+1)/2;g.tipY=(g.headHeight*50+27)/55;
  }
  uint16_t brushPixel(int x,int y,uint16_t value) const {
    const auto &g=geometry;
    if(x<g.k(30)||x>g.k(89)||y<g.k(57)||y>g.k(92))return value;
    // Project each face into the plate's two screen axes. Pixel centres and
    // face-local shading retain the same proportions/texture at either scale.
    const auto face=[&](int ox,int oy,int ux,int uy,int vx,int vy,int &u,int &v) {
      const int dx=x*2+1-ox*g.scale,dy=y*2+1-oy*g.scale;
      int determinant=ux*vy-uy*vx;
      int along=dx*vy-dy*vx,across=dy*ux-dx*uy;
      if(determinant<0){determinant=-determinant;along=-along;across=-across;}
      const int limit=determinant*g.scale;
      if(along<0||along>limit||across<0||across>limit)return false;
      u=along*255/limit;v=across*255/limit;return true;
    };
    using ws43b_native::rgb;
    int u=0,v=0;
    // Restrained footprint, then the brushed-metal holder's front, side and rim.
    if(face(31,76,46,15,11,-8,u,v))value=ws43b_assets::blend(0,value,38);
    if(face(31,69,46,15,0,6,u,v)) {
      value=mix(rgb(91,106,117),rgb(43,57,69),unsigned(v));
      if(v<32)value=mix(value,rgb(184,197,205),70);
    }
    if(face(77,84,11,-8,0,6,u,v))
      value=mix(rgb(67,82,94),rgb(35,48,60),unsigned(v));
    if(face(31,69,46,15,11,-8,u,v)) {
      value=mix(rgb(106,120,130),rgb(143,155,163),unsigned(v));
      if(u<10||u>245||v<22||v>233)value=mix(value,rgb(206,215,219),52);
    }
    // A low dense brush, not tall teeth: its narrow ridges follow the same
    // local axes as the pad. Warm neutral bristles echo the shared brass tip.
    if(face(35,64,39,13,0,5,u,v)) {
      value=mix(rgb(111,108,91),rgb(68,73,68),unsigned(v));
      if((u*13)%256<38)value=mix(value,0,45);
    }
    if(face(74,77,8,-6,0,5,u,v))
      value=mix(rgb(102,101,86),rgb(60,68,65),unsigned(v));
    if(face(35,64,39,13,8,-6,u,v)) {
      value=mix(rgb(126,121,101),rgb(166,155,126),unsigned(v));
      const int ridge=(u*13)%256;
      if(ridge<38)value=mix(value,rgb(68,76,71),65);
      else if(ridge>205)value=mix(value,rgb(211,201,167),38);
    }
    return value;
  }
  uint16_t gridPixel(int x,int y,uint16_t value) const {
    const auto &g=geometry;
    if(x<g.k(19)||x>g.k(93)||y<g.k(45)||y>g.k(85))return value;
    static constexpr int px[9]={22,44,66,78,56,34,46,68,90};
    static constexpr int py[9]={66,74,82,73,65,57,48,56,64};
    const auto point=[&](int i)->Point{return {g.k(px[i]),g.k(py[i])};};
    // These paths are symbolic probes, not a reported bed mesh.
    for(int i=0;i<3;++i)
      if(lineContains(x,y,point(i),point(6+i),1)||lineContains(x,y,point(i*3),point(i*3+2),1))
        value=ws43b_assets::blend(0x2946,value,85);
    for(int i=0;i<9;++i)if(ellipseContains(x,y,point(i),g.k(2),g.k(1)))value=0xBDD7;
    return value;
  }
  uint16_t staticPixel(int x,int y) {
    const auto &g=geometry;
    uint16_t value=backdrop(x,y);
    if(mode!=Mode::Cleaning&&y>=g.plateY&&y<g.plateY+g.plateHeight) {
      const auto &plate=ws43b_assets::descriptor(ws43b_assets::Asset::Plate);
      const auto p=filtered(plate,(x*2+1)*plate.width*128/g.plateWidth-128,
          ((y-g.plateY)*2+1)*plate.height*128/g.plateHeight-128);
      value=ws43b_assets::blend(p.color,value,p.alpha);
    }
    if(mode==Mode::Cleaning)return brushPixel(x,y,value);
    if(mode==Mode::Leveling)return gridPixel(x,y,value);
    if(mode!=Mode::Printing)return value;
    const int dx=x-g.modelX,dy=y-g.modelTop;
    if(dx<0||dx>=g.modelWidth||dy<0||dy>=g.modelHeight)return value;
    // Same source-column seam mapping as native::Scene: height translates the
    // intact upper rim and stretches only the walls, preserving perspective.
    const int sx=((dx*2+1)*160*128/g.modelWidth)-128;
    const int seam=sx<=85*256?39*256+(sx-4*256)*22/81:61*256-(sx-85*256)*40/69;
    const int projectedSeam=seam*g.modelWidth/160;
    const int sy=dy*256<=projectedSeam?((dy*2+1)*160*128/g.modelWidth)-128:
      seam+(dy*256-projectedSeam)*68/g.wallHeight;
    auto p=filtered(ws43b_assets::descriptor(ws43b_assets::Asset::Model),sx,sy,filament,true);
    if(sy>seam+8*256) {
      unsigned shade=unsigned(sy-seam-8*256)*12/(60*256);if(shade>12)shade=12;
      p.color=ws43b_assets::blend(0,p.color,uint8_t(shade));
    }
    return ws43b_assets::blend(p.color,value,p.alpha);
  }
  Frame frame(uint32_t elapsed) const {
    const auto &g=geometry;Frame result;
    Point tip{};
    if(mode==Mode::Printing) {
      const unsigned cycle=elapsed%7200u,segment=cycle/1800u;
      float t=float(cycle%1800u)/1800.f;t=t*t*(3.f-2.f*t);
      const auto a=g.rim(segment),b=g.rim(segment+1);
      tip={int(a.x+(b.x-a.x)*t+0.5f),int(a.y+(b.y-a.y)*t+0.5f)};
    } else if(mode==Mode::Cleaning) {
      const auto pose=cleaningPose(elapsed);
      tip={int(pose.tipX*g.scale/2.f+0.5f),int(pose.tipY*g.scale/2.f+0.5f)};
      result.probe=tip;result.brushContact=pose.contact;
      result.left=tip.x-g.k(5);result.right=tip.x+g.k(5)+1;
      result.top=tip.y-g.k(2);result.bottom=tip.y+g.k(3)+1;
    } else if(mode==Mode::Leveling) {
      static constexpr int px[9]={22,44,66,78,56,34,46,68,90};
      static constexpr int py[9]={66,74,82,73,65,57,48,56,64};
      const unsigned step=(elapsed/1600u)%9u,prev=(step+8u)%9u,part=elapsed%1600u;
      float t=part<900u?float(part)/900.f:1.f;t=t*t*(3.f-2.f*t);
      const int lift=part<900u?g.k(8):g.k(8)-int(g.k(8)*sinf(float(part-900u)*3.14159265f/700.f));
      tip={g.k(px[prev])+int(g.k(px[step]-px[prev])*t),g.k(py[prev])+int(g.k(py[step]-py[prev])*t)-lift};
      result.probe={g.k(px[step]),g.k(py[step])};result.showProbe=true;
      result.left=result.probe.x-g.k(5);result.right=result.probe.x+g.k(5)+1;
      result.top=result.probe.y-g.k(3);result.bottom=result.probe.y+g.k(3)+1;
    } else {
      const unsigned step=(elapsed/2000u)%4u,part=elapsed%2000u;
      const float t=part<1600u?float(part)/1600.f:1.f;
      for(unsigned i=0;i<=step;++i) {
        const Point a{g.k(20+int(i)*7),g.k(68-int(i)*6)};
        const float fraction=i<step?1.f:t;
        const Point b{a.x+int(g.k(52)*fraction),a.y+int(g.k(18)*fraction)};
        // A very small neutral reflection keeps black filament legible, using
        // the same material rule as the shared model rather than a substitute hue.
        const uint16_t lineColor=ws43b_assets::recolor(0x07e0,filament);
        result.strokes[result.count++]={{a.x,a.y+g.k(1)},{b.x,b.y+g.k(1)},mix(lineColor,0,70),g.k(1)};
        result.strokes[result.count++]={{a.x,a.y-g.k(1)},{b.x,b.y-g.k(1)},mix(lineColor,0xffff,28),g.k(1)};
        result.strokes[result.count++]={a,b,lineColor,g.k(1)};
      }
      tip={g.k(20+int(step)*7)+int(g.k(52)*t),g.k(68-int(step)*6)+int(g.k(18)*t)};
      if(part>=1600u) {
        const unsigned next=(step+1u)%4u;
        float move=float(part-1600u)/400.f;move=move*move*(3.f-2.f*move);
        tip.x+=int((g.k(20+int(next)*7)-tip.x)*move);
        tip.y+=int((g.k(68-int(next)*6)-tip.y)*move);
      }
      result.left=g.k(18);result.right=g.k(97);
      result.top=g.k(47);result.bottom=g.k(90);
    }
    result.head={tip.x-g.tipX,tip.y-g.tipY};return result;
  }
  uint16_t overlayPixel(int x,int y,uint16_t value,const Frame &f) const {
    if(x<f.left||x>=f.right||y<f.top||y>=f.bottom)return value;
    if(f.brushContact) {
      const Point contact{f.probe.x,f.probe.y+geometry.k(1)};
      if(ellipseContains(x,y,contact,geometry.k(4),geometry.k(1)))
        value=ws43b_assets::blend(0,value,45);
      // One small contact reflection stays underneath the shared RGBA head.
      if(y==f.probe.y&&x>=f.probe.x+geometry.k(2)&&x<=f.probe.x+geometry.k(3))
        value=mix(value,ws43b_native::rgb(219,214,186),65);
    }
    if(f.showProbe) {
      if(ellipseContains(x,y,f.probe,geometry.k(5),geometry.k(3)))value=ws43b_assets::blend(accent,value,120);
      if(ellipseContains(x,y,f.probe,geometry.k(2),geometry.k(1)))value=accent;
    }
    for(unsigned i=0;i<f.count;++i)
      if(lineContains(x,y,f.strokes[i].a,f.strokes[i].b,f.strokes[i].radius))value=f.strokes[i].color;
    return value;
  }
public:
  explicit Renderer(CacheStorage *optional=nullptr):storage(optional) {}
  bool hasCache() const {return storage!=nullptr;}
  unsigned compositionCount() const {return compositions;}
  unsigned headPreparationCount() const {return headPreparations;}
  unsigned filterSampleCount() const {return filterSamples;}
  template<class C>
  bool render(C &c,int x,int y,Mode nextMode,unsigned percent,uint32_t elapsed,
              uint16_t nextFilament,uint16_t nextAccent,uint16_t nextBase,
              bool nextDashboard=false,int scale=2) {
    if(scale!=2&&scale!=3)return false;
    if(!assetsReady) {
      const ws43b_assets::Asset assets[]={ws43b_assets::Asset::Plate,ws43b_assets::Asset::Model,ws43b_assets::Asset::Head};
      for(auto asset:assets)
        if(!ws43b_assets::valid(ws43b_assets::descriptor(asset)))return false;
      const auto &model=ws43b_assets::descriptor(ws43b_assets::Asset::Model);
      if(model.width!=160||model.height!=132)return false;
      assetsReady=true;
    }
    if(percent>100)percent=100;
    // Preparation never fabricates progress or a printed model. Ignore those
    // unused fields in its cache key so unrelated telemetry cannot rebuild art.
    if(nextMode!=Mode::Printing)percent=0;
    const uint16_t staticFilament=nextMode==Mode::Printing?nextFilament:0;
    const bool changed=!composed||mode!=nextMode||progress!=percent||
      (mode==Mode::Printing&&filament!=staticFilament)||base!=nextBase||
      dashboard!=nextDashboard||originX!=x||originY!=y||geometry.scale!=scale;
    mode=nextMode;progress=percent;filament=nextFilament;accent=nextAccent;
    base=nextBase;dashboard=nextDashboard;originX=x;originY=y;
    if(changed)setGeometry(scale,progress);
    const auto &g=geometry;
    if(storage) {
      if(changed) {
        for(int py=0;py<g.height;++py)for(int px=0;px<g.width;++px)
          storage->pixels[py*g.width+px]=staticPixel(px,py);
        composed=true;++compositions;
      }
      if(headScale!=scale) {
        const auto &s=ws43b_assets::descriptor(ws43b_assets::Asset::Head);
        for(int py=0;py<g.headHeight;++py)for(int px=0;px<g.headWidth;++px)
          storage->head[py*g.headWidth+px]=filtered(s,(px*2+1)*s.width*128/g.headWidth-128,
              (py*2+1)*s.height*128/g.headHeight-128);
        headScale=scale;++headPreparations;
      }
    }
    const auto f=frame(elapsed);
    const auto &head=ws43b_assets::descriptor(ws43b_assets::Asset::Head);
    ws43b_native::rasterRect(c,x,y,g.width,g.height,[&](int ax,int ay) {
      const int px=ax-x,py=ay-y;
      uint16_t value=storage?storage->pixels[py*g.width+px]:staticPixel(px,py);
      value=overlayPixel(px,py,value,f);
      const int hx=px-f.head.x,hy=py-f.head.y;
      if(hx>=0&&hy>=0&&hx<g.headWidth&&hy<g.headHeight) {
        const auto p=storage?storage->head[hy*g.headWidth+hx]:filtered(head,
          (hx*2+1)*head.width*128/g.headWidth-128,(hy*2+1)*head.height*128/g.headHeight-128);
        value=ws43b_assets::blend(p.color,value,p.alpha);
      }
      return value;
    });
    return true;
  }
};

// One shared instance across regular and Scaled canvas types and every mode.
// The optional 60,736-byte cache lives in external RAM only. Failure is final:
// the same artwork is sampled into short rows without an internal-heap retry.
inline Renderer &sharedRenderer() {
#if defined(ARDUINO)
  static auto *storage=static_cast<CacheStorage*>(heap_caps_malloc(
    sizeof(CacheStorage),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
  static Renderer renderer(storage);
#else
  static Renderer renderer;
#endif
  return renderer;
}

// Logical 1.5x adapter is retained for callers. Scene overloads below unwrap it
// and sample the source artwork directly at 168x156, preserving saver sharpness.
template<class C> struct Scaled {
  C &c;int x,y;
  static int k(int n){return n*3/2;}
  void drawFastHLine(int a,int b,int w,uint16_t color){c.fillRect(x+k(a),y+k(b),k(w),2,color);}
  void drawLine(int a,int b,int d,int e,uint16_t color){c.drawLine(x+k(a),y+k(b),x+k(d),y+k(e),color);}
  void fillTriangle(int a,int b,int d,int e,int f,int g,uint16_t color){c.fillTriangle(x+k(a),y+k(b),x+k(d),y+k(e),x+k(f),y+k(g),color);}
  void fillEllipse(int a,int b,int rx,int ry,uint16_t color){c.fillEllipse(x+k(a),y+k(b),k(rx),k(ry),color);}
  void fillRoundRect(int a,int b,int w,int h,int r,uint16_t color){c.fillRoundRect(x+k(a),y+k(b),k(w),k(h),k(r),color);}
  void fillRect(int a,int b,int w,int h,uint16_t color){c.fillRect(x+k(a),y+k(b),k(w),k(h),color);}
  void pushImage(int a,int b,int w,int h,const lgfx::rgb565_t *pixels) {
    // Generic bounded-image compatibility; production scenes bypass this path.
    uint16_t row[96];
    for(int py=0;py<h;++py)for(int left=0;left<w;left+=64) {
      const int count=w-left<64?w-left:64,start=k(a+left),end=k(a+left+count);
      for(int px=0;px<count;++px)
        for(int dx=k(a+left+px);dx<k(a+left+px+1);++dx)
          row[dx-start]=reinterpret_cast<const uint16_t*>(pixels)[py*w+left+px];
      for(int dy=k(b+py);dy<k(b+py+1);++dy)
        c.pushImage(x+start,y+dy,end-start,1,reinterpret_cast<const lgfx::rgb565_t*>(row));
    }
  }
};

template<class C>
void renderScene(C &c,int x,int y,Mode mode,unsigned percent,uint32_t elapsed,
                 uint16_t filament,uint16_t accent,uint16_t base,bool dashboard) {
  sharedRenderer().render(c,x,y,mode,percent,elapsed,filament,accent,base,dashboard,2);
}
template<class C>
void renderScene(Scaled<C> &c,int x,int y,Mode mode,unsigned percent,uint32_t elapsed,
                 uint16_t filament,uint16_t accent,uint16_t base,bool dashboard) {
  sharedRenderer().render(c.c,c.x+c.k(x),c.y+c.k(y),mode,percent,elapsed,filament,accent,base,dashboard,3);
}
template<class C>
void draw(C &c,int x,int y,unsigned percent,uint32_t elapsed,uint16_t filament,
          uint16_t base,bool clear=true,bool dashboard=false) {
  // A complete composition is emitted even when the caller already restored its
  // region. The flag remains source-compatible; all alpha sees actual artwork.
  (void)clear;renderScene(c,x,y,Mode::Printing,percent,elapsed,filament,0,base,dashboard);
}
template<class C>
void cleaning(C &c,int x,int y,uint32_t elapsed,uint16_t base=0,bool dashboard=false) {
  renderScene(c,x,y,Mode::Cleaning,0,elapsed,0,0,base,dashboard);
}
template<class C>
void leveling(C &c,int x,int y,uint32_t elapsed,uint16_t accent,uint16_t base=0,bool dashboard=false) {
  renderScene(c,x,y,Mode::Leveling,0,elapsed,0,accent,base,dashboard);
}
template<class C>
void calibrationLines(C &c,int x,int y,uint32_t elapsed,uint16_t filament,uint16_t base=0,bool dashboard=false) {
  renderScene(c,x,y,Mode::Calibration,0,elapsed,filament,0,base,dashboard);
}
} // namespace ws43b_print_scene
