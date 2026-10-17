// Host raster of the production compact scenes. No substitute artwork.
#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <vector>
namespace lgfx {using rgb565_t=uint16_t;}
#include "ws43b_print_scene.h"

namespace {
using ws43b_print_scene::Mode;
using ws43b_print_scene::Renderer;
using ws43b_print_scene::CacheStorage;
constexpr uint16_t sentinel=0xd963,green=0x87e3,accent=0x67b6;
constexpr uint16_t saverBg=ws43b_native::rgb(3,14,23);
constexpr uint64_t guard=0xc13b5a7891a4f267ull;
struct Guarded {
  std::array<uint64_t,4> before{{guard,guard,guard,guard}};
  CacheStorage storage{};
  std::array<uint64_t,4> after{{guard,guard,guard,guard}};
  void check()const{for(auto v:before)assert(v==guard);for(auto v:after)assert(v==guard);}
};
struct Canvas {
  int x,y,w,h;std::vector<uint16_t> pixels;
  size_t writes=0,calls=0;
  Canvas(int x,int y,int scale):x(x),y(y),w(112*scale/2),h(104*scale/2),
    pixels(size_t(w+4)*(h+4),sentinel){}
  void counts(){writes=calls=0;}
  size_t index(int px,int py)const{return size_t(py-y+2)*(w+4)+px-x+2;}
  uint16_t get(int px,int py)const{return pixels[index(px,py)];}
  void pushImage(int px,int py,int width,int height,const lgfx::rgb565_t *data){
    assert(data&&width>0&&height>0&&width<=64);
    assert(px>=x&&py>=y&&px+width<=x+w&&py+height<=y+h);
    ++calls;
    for(int row=0;row<height;++row)for(int col=0;col<width;++col){
      assert(++writes<=size_t(w)*h);pixels[index(px+col,py+row)]=data[row*width+col];
    }
  }
  void check()const{
    assert(writes==size_t(w)*h&&calls==size_t((w+63)/64)*h);
    for(int row=0;row<h+4;++row)for(int col=0;col<w+4;++col)
      if(row<2||row>=h+2||col<2||col>=w+2)assert(pixels[size_t(row)*(w+4)+col]==sentinel);
  }
  void ppm(const char *path)const{
    FILE *out=fopen(path,"wb");assert(out);fprintf(out,"P6\n%d %d\n255\n",w,h);
    for(int py=y;py<y+h;++py)for(int px=x;px<x+w;++px){
      const auto value=get(px,py);const unsigned char rgb[]={ws43b_assets::red(value),ws43b_assets::green(value),ws43b_assets::blue(value)};
      assert(fwrite(rgb,1,3,out)==3);
    }
    assert(fclose(out)==0);
  }
};
unsigned period(Mode mode){
  switch(mode){case Mode::Printing:return 7200;case Mode::Cleaning:return ws43b_print_scene::cleaningPeriodMs;
    case Mode::Leveling:return 14400;case Mode::Calibration:return 8000;}
  assert(false);return 0;
}
void render(Renderer &renderer,Canvas &c,Mode mode,unsigned progress,uint32_t phase,
            uint16_t material=green,uint16_t base=saverBg,bool dashboard=false,uint16_t marker=accent){
  c.counts();assert(renderer.render(c,c.x,c.y,mode,progress,phase,material,marker,base,dashboard,c.w==112?2:3));c.check();
}
void freeRender(Canvas &c,Mode mode,unsigned progress,uint32_t phase,uint16_t material,uint16_t base,bool dashboard){
  c.counts();
  const auto invoke=[&](auto &target,int x,int y){
    switch(mode){
      case Mode::Printing:ws43b_print_scene::draw(target,x,y,progress,phase,material,base,false,dashboard);break;
      case Mode::Cleaning:ws43b_print_scene::cleaning(target,x,y,phase,base,dashboard);break;
      case Mode::Leveling:ws43b_print_scene::leveling(target,x,y,phase,accent,base,dashboard);break;
      case Mode::Calibration:ws43b_print_scene::calibrationLines(target,x,y,phase,material,base,dashboard);break;
    }
  };
  if(c.w==112)invoke(c,c.x,c.y);
  else {ws43b_print_scene::Scaled<Canvas> scaled{c,c.x,c.y};invoke(scaled,0,0);}
  c.check();
}

size_t verifyCleaningPose(){
  using ws43b_print_scene::CleaningPhase;
  using ws43b_print_scene::cleaningPose;
  constexpr auto cycle=ws43b_print_scene::cleaningPeriodMs;
  assert(cycle==3200u);
  const auto distance=[](const auto &a,const auto &b){
    return std::hypot(a.tipX-b.tipX,a.tipY-b.tipY);
  };
  const auto beginning=cleaningPose(0);
  assert(beginning.phase==CleaningPhase::Approach&&!beginning.contact);
  assert(std::abs(beginning.tipX-28.f)<0.001f&&std::abs(beginning.tipY-52.f)<0.001f);
  size_t samples=0;
  // The contact stroke must run along the brush, not across its support or
  // through empty space. Approach, withdrawal and rest remain non-contact.
  for(uint32_t t=0;t<cycle;++t){
    const auto p=cleaningPose(t),next=cleaningPose(t+1),repeated=cleaningPose(t+cycle);
    assert(std::isfinite(p.tipX)&&std::isfinite(p.tipY));
    assert(p.tipX>=28.f&&p.tipX<=73.f&&p.tipY>=52.f&&p.tipY<=75.f);
    assert(distance(p,next)<=0.2f); // Also includes every phase/stroke boundary.
    assert(distance(p,repeated)<0.001f&&p.contact==repeated.contact&&p.phase==repeated.phase);
    const auto expected=t<600?CleaningPhase::Approach:t<2400?CleaningPhase::Wipe:
      t<2700?CleaningPhase::Lift:t<2950?CleaningPhase::Retract:CleaningPhase::Rest;
    assert(p.phase==expected&&p.contact==(expected==CleaningPhase::Wipe));
    if(p.contact){
      assert(p.tipX>=43.f&&p.tipX<=73.f);
      assert(std::abs(p.tipY-(65.f+(p.tipX-43.f)/3.f))<0.002f);
    }
    if(expected==CleaningPhase::Rest)assert(distance(p,beginning)<0.001f);
    ++samples;
  }
  assert(distance(cleaningPose(cycle),beginning)<0.001f);
  // Six actual bidirectional sweeps, with no dwell jump at a turnaround.
  for(unsigned stroke=0;stroke<6;++stroke){
    const auto a=cleaningPose(600+stroke*300),b=cleaningPose(600+(stroke+1)*300);
    assert(std::abs(b.tipX-a.tipX)>29.9f);
    assert((stroke%2==0)==(b.tipX>a.tipX));
    const auto before=cleaningPose(599+(stroke+1)*300);
    assert(distance(before,b)<0.002f);
  }
  // Both output sizes must put the visible moving head at the same logical
  // pose. No changing pixels may escape its footprint or force recomposition.
  const uint32_t edges[]={0,599,600,899,900,1500,2399,2400,2699,2700,2949,2950,3199,3200};
  for(int scale:{2,3}){
    Guarded cache;Renderer renderer(&cache.storage);Canvas c(109,222,scale);
    unsigned compositions=0,headPreparations=0,filters=0;
    for(auto t:edges){
      render(renderer,c,Mode::Cleaning,0,t);
      const auto p=cleaningPose(t);
      const int hw=27*scale/2,hh=35*scale/2;
      const int left=int(p.tipX*float(scale)/2.f+0.5f)-(hw+1)/2;
      const int top=int(p.tipY*float(scale)/2.f+0.5f)-(hh*50+27)/55;
      assert(left>=0&&top>=0&&left+hw<=c.w&&top+hh<=c.h);
      size_t movingPixels=0;
      for(int y=0;y<c.h;++y)for(int x=0;x<c.w;++x){
        if(c.get(c.x+x,c.y+y)==cache.storage.pixels[y*c.w+x])continue;
        ++movingPixels;assert(x>=left&&x<left+hw&&y>=top&&y<top+hh);
      }
      assert(movingPixels>100);
      if(t==0){compositions=renderer.compositionCount();headPreparations=renderer.headPreparationCount();filters=renderer.filterSampleCount();}
      else assert(renderer.compositionCount()==compositions&&renderer.headPreparationCount()==headPreparations&&renderer.filterSampleCount()==filters);
      cache.check();
    }
    assert(compositions==1&&headPreparations==1);
  }
  return samples;
}

size_t verifyCleaningBackdrop(){
  // Cleaning owns only the moving head and its small stationary pad. The old
  // shared Plate sprite must not leave pixels anywhere else in this scene.
  const uint32_t phases[]={0,1,299,599,600,601,749,899,900,1049,1199,1200,
    1349,1499,1500,1649,1799,1800,1949,2099,2100,2249,2399,2400,2401,
    2549,2699,2700,2701,2824,2949,2950,3074,3199,3200};
  size_t frames=0;
  for(int scale:{2,3})for(bool dashboard:{false,true}){
    Guarded cache;Renderer cached(&cache.storage),fallback;
    const int x=dashboard?307:109,y=dashboard?107:222;
    const uint16_t base=dashboard?0x0084:saverBg;
    Canvas a(x,y,scale),b(x,y,scale);
    size_t oldPlateWitnesses=0;
    for(auto phase:phases){
      render(cached,a,Mode::Cleaning,0,phase,green,base,dashboard);
      render(fallback,b,Mode::Cleaning,0,phase,green,base,dashboard);
      assert(a.pixels==b.pixels);
      const auto pose=ws43b_print_scene::cleaningPose(phase);
      const int hw=27*scale/2,hh=35*scale/2;
      const int hx=int(pose.tipX*float(scale)/2.f+0.5f)-(hw+1)/2;
      const int hy=int(pose.tipY*float(scale)/2.f+0.5f)-(hh*50+27)/55;
      for(int py=0;py<a.h;++py)for(int px=0;px<a.w;++px){
        const bool head=px>=hx&&px<hx+hw&&py>=hy&&py<hy+hh;
        const bool pad=px>=30*scale/2&&px<=89*scale/2&&py>=57*scale/2&&py<=92*scale/2;
        if(head||pad)continue;
        const auto background=dashboard?ws43b_native::cardbg(x+px,y+py,66,242,base):base;
        assert(a.get(x+px,y+py)==background&&b.get(x+px,y+py)==background);
        // A concrete regression witness: these checked pixels were covered by
        // opaque Plate artwork before its omission, rather than empty margins.
        const int plateY=44*scale/2,plateHeight=55*scale/2;
        if(phase==0&&py>=plateY&&py<plateY+plateHeight){
          const auto &plate=ws43b_assets::descriptor(ws43b_assets::Asset::Plate);
          const auto old=ws43b_native::filtered(plate,(px*2+1)*plate.width*128/a.w-128,
            ((py-plateY)*2+1)*plate.height*128/plateHeight-128,0,false);
          if(old.alpha>=200&&ws43b_assets::blend(old.color,background,old.alpha)!=background)++oldPlateWitnesses;
        }
      }
      cache.check();++frames;
    }
    assert(oldPlateWitnesses>100);
    assert(cached.compositionCount()==1&&cached.headPreparationCount()==1);
  }
  return frames;
}

void verify(){
  const auto cleaningPoseSamples=verifyCleaningPose();
  const auto cleaningBackdropFrames=verifyCleaningBackdrop();
  const Mode modes[]={Mode::Printing,Mode::Cleaning,Mode::Leveling,Mode::Calibration};
  size_t frames=0,headSamples=0,materialPixels=0,wrapperFrames=0,sweepFrames=0;
  for(int scale:{2,3})for(bool dashboard:{false,true})for(uint16_t color:{uint16_t(0),uint16_t(0xffff),green})
    for(Mode mode:modes)for(unsigned progress:{0u,50u,100u}){
      if(mode!=Mode::Printing&&progress!=0)continue;
      Guarded cache;Renderer cached(&cache.storage),fallback;
      Canvas a(dashboard?307:250,dashboard?107:258,scale),b(a.x,a.y,scale);
      const uint16_t base=dashboard?0x0084:saverBg;
      const unsigned cycle=period(mode);
      const uint32_t phases[]={0,1,cycle/8,cycle/3,cycle/2,cycle-1,cycle,std::numeric_limits<uint32_t>::max()};
      std::vector<uint16_t> first,middle;
      unsigned prepared=0,composed=0,filtered=0;
      for(auto phase:phases){
        render(cached,a,mode,progress,phase,color,base,dashboard);
        render(fallback,b,mode,progress,phase,color,base,dashboard);
        assert(a.pixels==b.pixels);cache.check();++frames;
        if(phase==0){first=a.pixels;prepared=cached.headPreparationCount();composed=cached.compositionCount();filtered=cached.filterSampleCount();}
        else {assert(cached.headPreparationCount()==prepared&&cached.compositionCount()==composed&&cached.filterSampleCount()==filtered);}
        if(phase==cycle/8)middle=a.pixels;
        if(phase==cycle)assert(a.pixels==first);
        for(int dx:{0,a.w-1})for(int dy:{0,a.h-1})
          assert(a.get(a.x+dx,a.y+dy)==(dashboard?ws43b_native::cardbg(a.x+dx,a.y+dy,66,242,base):base));
      }
      assert(first!=middle&&prepared==1&&composed==1);
      assert(cached.hasCache()&&!fallback.hasCache()&&fallback.filterSampleCount()>cached.filterSampleCount());
      // Cache must preserve the exact filtered RGBA samples of the shared head.
      const int hw=27*scale/2,hh=35*scale/2;
      const auto &head=ws43b_assets::descriptor(ws43b_assets::Asset::Head);unsigned translucent=0;
      for(int y=0;y<hh;++y)for(int x=0;x<hw;++x){
        const auto expected=ws43b_native::filtered(head,(x*2+1)*head.width*128/hw-128,(y*2+1)*head.height*128/hh-128,0,false);
        const auto actual=cache.storage.head[y*hw+x];
        assert(actual.color==expected.color&&actual.alpha==expected.alpha);++headSamples;
        translucent+=actual.alpha>0&&actual.alpha<255;
      }
      assert(translucent>10);
    }
  // Dense full-cycle sweep retains the old geometry fixture's 37 ms sampling,
  // now checking every output pixel at both destination sizes under ASan.
  for(int scale:{2,3})for(Mode mode:modes)for(unsigned progress:{0u,1u,50u,99u,100u}){
    if(mode!=Mode::Printing&&progress!=0)continue;
    Guarded cache;Renderer renderer(&cache.storage);Canvas c(109,222,scale);
    for(uint32_t phase=0;phase<=period(mode)*2;phase+=37){
      render(renderer,c,mode,progress,phase);++sweepFrames;
    }
    cache.check();assert(renderer.compositionCount()==1&&renderer.headPreparationCount()==1);
  }
  // Public APIs and the saver adapter must use the same destination-size
  // sampling, including the actual absolute gradient origin on dashboard.
  for(int scale:{2,3})for(bool dashboard:{false,true})for(Mode mode:modes){
    Guarded cache;Renderer renderer(&cache.storage);
    Canvas a(109,222,scale),b(a.x,a.y,scale);
    render(renderer,a,mode,50,950,green,0x2104,dashboard);
    freeRender(b,mode,50,950,green,0x2104,dashboard);
    assert(a.pixels==b.pixels);++wrapperFrames;
  }
  // Material changes affect model/laid lines, not the plate or toolhead art.
  for(int scale:{2,3})for(Mode mode:modes){
    Guarded ca,cb;Renderer black(&ca.storage),colored(&cb.storage);
    Canvas a(109,222,scale),b(a.x,a.y,scale);
    render(black,a,mode,50,3500,0);render(colored,b,mode,50,3500,green);
    size_t differences=0;
    for(int y=0;y<a.h;++y)for(int x=0;x<a.w;++x){
      if(a.get(a.x+x,a.y+y)==b.get(b.x+x,b.y+y))continue;
      ++differences;
      assert(x>=18*scale/2&&x<98*scale/2&&y>=20*scale/2&&y<94*scale/2);
    }
    if(mode==Mode::Printing||mode==Mode::Calibration){assert(differences>50);materialPixels+=differences;}
    else assert(differences==0);
    const int count=(27*scale/2)*(35*scale/2);
    for(int i=0;i<count;++i){assert(ca.storage.head[i].color==cb.storage.head[i].color);assert(ca.storage.head[i].alpha==cb.storage.head[i].alpha);}
    ca.check();cb.check();
  }
  // Explicit presentation changes invalidate composition; unused preparation
  // telemetry does not. The head is prepared again only when scale changes.
  {
    Guarded cache;Renderer r(&cache.storage);Canvas c(307,107,2);
    render(r,c,Mode::Printing,50,0);const auto first=r.compositionCount();
    render(r,c,Mode::Printing,51,0);assert(r.compositionCount()==first+1);
    render(r,c,Mode::Printing,51,0,0xffff);assert(r.compositionCount()==first+2);
    render(r,c,Mode::Printing,51,0,0xffff,0xf800);assert(r.compositionCount()==first+3);
    render(r,c,Mode::Printing,51,0,0xffff,0xf800,true);assert(r.compositionCount()==first+4);
    Canvas shifted(308,108,2);render(r,shifted,Mode::Printing,51,0,0xffff,0xf800,true);assert(r.compositionCount()==first+5);
    assert(r.headPreparationCount()==1);
    Canvas large(109,222,3);render(r,large,Mode::Cleaning,0,0);
    const auto count=r.compositionCount(),filters=r.filterSampleCount();
    const auto unchanged=large.pixels;
    render(r,large,Mode::Cleaning,99,0,0xffff,saverBg,false,0xf800);
    assert(r.compositionCount()==count&&r.filterSampleCount()==filters&&large.pixels==unchanged);
    assert(r.headPreparationCount()==2);cache.check();
    render(r,large,Mode::Printing,100,1234);const auto maximum=large.pixels;
    render(r,large,Mode::Printing,std::numeric_limits<unsigned>::max(),1234);assert(large.pixels==maximum);
    for(int invalid:{0,1,4,-1}){large.counts();assert(!r.render(large,large.x,large.y,Mode::Printing,50,0,green,accent,saverBg,false,invalid));assert(large.writes==0);}
  }
  assert(ws43b_print_scene::mix(0,0xffff,0)==0&&ws43b_print_scene::mix(0,0xffff,255)==0xffff);
  printf("{\"result\":\"PASS\",\"cached_fallback_frames\":%zu,\"head_rgba_samples\":%zu,\"material_difference_pixels\":%zu,\"wrapper_frames\":%zu,\"dense_sweep_frames\":%zu,\"cleaning_pose_samples\":%zu,\"cleaning_backdrop_frames\":%zu}\n",frames,headSamples,materialPixels,wrapperFrames,sweepFrames,cleaningPoseSamples,cleaningBackdropFrames);
}

void benchmark(){
  const Mode modes[]={Mode::Printing,Mode::Printing,Mode::Printing,Mode::Cleaning,Mode::Leveling,Mode::Calibration};
  const unsigned progress[]={0,50,100,0,0,0};
  printf("{\"platform\":\"host CPU, optimized C++ raster fixture; not ESP32 timing\",\"cases\":[");bool comma=false;
  for(int scale:{2,3})for(unsigned which=0;which<6;++which){
    Guarded cache;Renderer cached(&cache.storage),fallback;
    Canvas a(109,222,scale),b(a.x,a.y,scale);const unsigned n=16;
    render(cached,a,modes[which],progress[which],0);render(fallback,b,modes[which],progress[which],0);
    const auto count=[&](Renderer &r,Canvas &c){
      const auto samples=r.filterSampleCount();const auto start=std::chrono::steady_clock::now();
      for(unsigned i=0;i<n;++i)render(r,c,modes[which],progress[which],i*137u);
      const auto elapsed=std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now()-start).count();
      return std::pair<long long,unsigned>{elapsed,r.filterSampleCount()-samples};
    };
    const auto warm=count(cached,a),cold=count(fallback,b);assert(a.pixels==b.pixels&&warm.second==0&&cold.second>0);
    printf("%s{\"scale\":%d,\"mode\":%u,\"progress\":%u,\"frames\":%u,\"pixels_per_frame\":%d,\"cached_us_total\":%lld,\"fallback_us_total\":%lld,\"cached_filter_samples\":%u,\"fallback_filter_samples\":%u}",
      comma?",":"",scale,unsigned(modes[which]),progress[which],n,a.w*a.h,warm.first,cold.first,warm.second,cold.second);comma=true;
  }
  puts("]}");
}
}

int main(int argc,char **argv){
  if(argc==10&&!strcmp(argv[1],"--frame")){
    const auto mode=Mode(strtoul(argv[2],nullptr,10));const int scale=atoi(argv[3]);
    const auto progress=unsigned(strtoul(argv[4],nullptr,10));const uint32_t phase=uint32_t(strtoul(argv[5],nullptr,10));
    const auto material=uint16_t(strtoul(argv[6],nullptr,10)),base=uint16_t(strtoul(argv[7],nullptr,10));
    const bool dashboard=atoi(argv[8])!=0;assert(unsigned(mode)<4&&(scale==2||scale==3));
    Guarded cache;Renderer renderer(&cache.storage);Canvas canvas(dashboard?307:109,dashboard?107:222,scale);
    render(renderer,canvas,mode,progress,phase,material,base,dashboard);canvas.ppm(argv[9]);return 0;
  }
  if(argc==2&&!strcmp(argv[1],"--benchmark")){benchmark();return 0;}
  verify();return 0;
}
