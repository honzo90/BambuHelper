// Host renderer of the production scene, palette and compiled sprite decoder.
// No mock artwork or replacement scene logic. Fonts/live telemetry are excluded.
#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <limits>
#include <string>
#include <vector>

namespace lgfx { struct rgb565_t { uint16_t raw; }; }
#include "ws43b_native_scene.h"

namespace {
constexpr uint16_t sentinel=0xc13b;
struct Canvas {
  int width,height;
  std::vector<uint16_t> pixels;
  size_t writes=0, outside=0, calls=0;
  int left,top,right,bottom;
  explicit Canvas(int w,int h,uint16_t initial=sentinel)
      :width(w),height(h),pixels(size_t(w)*h,initial),left(0),top(0),right(w),bottom(h){}
  void bounds(int x,int y,int w,int h){left=x;top=y;right=x+w;bottom=y+h;}
  void resetCounts(){writes=outside=calls=0;}
  void put(int x,int y,uint16_t color) {
    if(x<left||y<top||x>=right||y>=bottom)++outside;
    if(x>=0&&y>=0&&x<width&&y<height)pixels[size_t(y)*width+x]=color;
    ++writes;
  }
  uint16_t get(int x,int y)const {assert(x>=0&&y>=0&&x<width&&y<height);return pixels[size_t(y)*width+x];}
  void drawFastHLine(int x,int y,int w,uint16_t color){for(int i=0;i<w;++i)put(x+i,y,color);}
  void fillRect(int x,int y,int w,int h,uint16_t color){for(int row=0;row<h;++row)drawFastHLine(x,y+row,w,color);}
  static bool rounded(int x,int y,int w,int h,int radius) {
    if(x<0||y<0||x>=w||y>=h)return false;
    const int r=std::max(0,std::min(radius,std::min(w,h)/2));
    if(!r)return true;
    const int cx=std::clamp(x,r,w-r-1),cy=std::clamp(y,r,h-r-1);
    const int dx=x-cx,dy=y-cy;return dx*dx+dy*dy<=r*r;
  }
  void drawRoundRect(int x,int y,int w,int h,int radius,uint16_t color){
    for(int yy=0;yy<h;++yy)for(int xx=0;xx<w;++xx)
      if(rounded(xx,yy,w,h,radius)&&!rounded(xx-1,yy-1,w-2,h-2,radius-1))put(x+xx,y+yy,color);
  }
  void pushImage(int x,int y,int w,int h,const lgfx::rgb565_t *data) {
    assert(w>=0&&h>=0);++calls;
    for(int row=0;row<h;++row)for(int col=0;col<w;++col)put(x+col,y+row,data[size_t(row)*w+col].raw);
  }
  void ppm(const std::string &filename,int x=0,int y=0,int w=0,int h=0)const {
    if(!w)w=width;if(!h)h=height;
    assert(x>=0&&y>=0&&x+w<=width&&y+h<=height);
    std::ofstream stream(filename,std::ios::binary);assert(stream.good());
    stream<<"P6\n"<<w<<' '<<h<<"\n255\n";
    for(int py=y;py<y+h;++py)for(int px=x;px<x+w;++px){const auto pixel=get(px,py);const char rgb[]={char(ws43b_assets::red(pixel)),char(ws43b_assets::green(pixel)),char(ws43b_assets::blue(pixel))};stream.write(rgb,3);}
    assert(stream.good());
  }
};

bool equivalent(const Canvas &a,const Canvas &b) {
  if(a.pixels==b.pixels)return true;
  for(size_t i=0;i<a.pixels.size();++i)if(a.pixels[i]!=b.pixels[i]) {
    std::cerr<<"Pixel mismatch at "<<i%a.width<<','<<i/a.width<<" partial="<<a.pixels[i]<<" fresh="<<b.pixels[i]<<'\n';break;
  }
  return false;
}

void verify() {
  using ws43b_native::Scene;
  const std::array<int,7> progressValues={0,1,36,49,68,99,100};
  const std::array<uint16_t,5> colors={0xf800,0x07e0,0x001f,0xffff,0x0000};
  const std::array<uint16_t,6> themes={0x0084,0x0861,0x1081,0,0xffff,0xf800};
  const std::array<uint32_t,21> phases={0,1,450,899,1799,1800,1801,2250,3599,3600,3601,
    4500,5399,5400,5401,6300,7199,7200,7201,14400,std::numeric_limits<uint32_t>::max()};
  std::vector<uint16_t> stored(size_t(Scene::width)*Scene::height),freshStorage(stored.size());
  std::array<ws43b_native::Pixel,Scene::headCachePixels+2> headStorage{};
  headStorage.front()={sentinel,123};headStorage.back()={sentinel,234};
  Scene partial(stored.data(),headStorage.data()+1);
  assert(!partial.hasHeadCache());
  Canvas retained(Scene::width+4,Scene::height+4);
  retained.bounds(2,2,Scene::width,Scene::height);
  size_t comparisons=0,partialFrames=0,positionChecks=0;
  for(int progress:progressValues)for(uint16_t color:colors)for(uint16_t theme:themes) {
    for(uint32_t phase:phases) {
      retained.resetCounts();
      assert(partial.render(retained,2,2,progress,color,theme,phase));
      assert(retained.outside==0);
      Canvas fresh(retained.width,retained.height);fresh.bounds(2,2,Scene::width,Scene::height);
      Scene full(freshStorage.data());
      assert(full.render(fresh,2,2,progress,color,theme,phase,true));
      assert(partial.hasHeadCache()&&!full.hasHeadCache());
      assert(fresh.outside==0&&equivalent(retained,fresh));
      if(retained.writes<fresh.writes)++partialFrames;
      ++comparisons;
    }
    // A forced repaint has the same visible result as the current retained frame.
    Canvas before=retained;
    assert(partial.render(retained,2,2,progress,color,theme,phases.back(),true));
    assert(equivalent(before,retained));
  }
  assert(partialFrames>0);
  // The cache contains the exact destination-resolution samples, including
  // alpha. Every comparison above uses cached incremental vs uncached full.
  size_t headSampleChecks=0;
  const auto &head=ws43b_assets::descriptor(ws43b_assets::Asset::Head);
  for(int py=0;py<Scene::headHeight;++py)for(int px=0;px<Scene::headWidth;++px) {
    const auto expected=ws43b_native::filtered(head,(px*2+1)*head.width*128/Scene::headWidth-128,
        (py*2+1)*head.height*128/Scene::headHeight-128,0,false);
    const auto actual=headStorage[1+py*Scene::headWidth+px];
    assert(actual.color==expected.color&&actual.alpha==expected.alpha);++headSampleChecks;
  }
  assert(headStorage.front().color==sentinel&&headStorage.front().alpha==123);
  assert(headStorage.back().color==sentinel&&headStorage.back().alpha==234);
  // The stationary phase pair, and an identical phase, emit zero pixels. Force
  // and scene changes still repaint even when the rounded head position agrees.
  size_t noOpFrames=0;
  for(bool cached:{false,true}) {
    Scene stationary(stored.data(),cached?headStorage.data()+1:nullptr);
    Canvas destination(Scene::width,Scene::height);
    assert(stationary.render(destination,0,0,68,0x07e0,0x0084,0));
    for(uint32_t phase:{0u,1u}) {
      destination.resetCounts();
      assert(stationary.render(destination,0,0,68,0x07e0,0x0084,phase));
      assert(destination.writes==0&&destination.calls==0);++noOpFrames;
    }
    assert(stationary.render(destination,0,0,68,0x07e0,0x0084,1,true));
    assert(destination.writes==size_t(Scene::width)*Scene::height+Scene::headCachePixels);
    destination.resetCounts();
    assert(stationary.render(destination,0,0,68,0xffff,0x0084,1));
    assert(destination.writes==size_t(Scene::width)*Scene::height+Scene::headCachePixels);
  }
  // Every point in the complete phase cycle must keep all head pixels in the cache.
  for(int progress=0;progress<=100;++progress) {
    assert(partial.compose(progress,0x07e0,0x0084));
    for(uint32_t phase=0;phase<=7200;++phase) {
      const auto point=partial.position(phase);
      assert(point.x>=0&&point.y>=0&&point.x+Scene::headWidth<=Scene::width&&point.y+Scene::headHeight<=Scene::height);
      ++positionChecks;
    }
  }
  // Invalid storage must neither write the destination nor report success.
  Scene absent(nullptr);Canvas untouched(Scene::width,Scene::height);
  assert(!absent.compose(50,0xffff,0x0084));
  assert(!absent.render(untouched,0,0,50,0xffff,0x0084,0));assert(untouched.writes==0);
  // Out-of-range telemetry progress is clamped to endpoints without changing pixels.
  for(const auto pair:std::array<std::array<int,2>,4>{{{{-100,0}},{{-1,0}},{{101,100}},{{10000,100}}}}) {
    Canvas a(Scene::width,Scene::height),b(Scene::width,Scene::height);
    Scene first(stored.data()),second(freshStorage.data());
    assert(first.render(a,0,0,pair[0],0xffff,0x0084,1700));
    assert(second.render(b,0,0,pair[1],0xffff,0x0084,1700));assert(equivalent(a,b));
  }
  // White and black produce different material while the static plate stays equal.
  Scene white(stored.data()),black(freshStorage.data());
  assert(white.compose(68,0xffff,0x0084)&&black.compose(68,0,0x0084));
  size_t materialDifferences=0;
  for(int y=0;y<Scene::height;++y)for(int x=0;x<Scene::width;++x) {
    if(stored[size_t(y)*Scene::width+x]!=freshStorage[size_t(y)*Scene::width+x]) {
      ++materialDifferences;assert(x>=Scene::modelX&&x<Scene::modelX+Scene::modelWidth&&y>=white.top()&&y<Scene::modelBase+3);
    }
  }
  assert(materialDifferences>1000);
  // Height changes translate the intact top diamond, never shear its edges.
  // Check all percentages, and compare actual opaque rim pixels after translation.
  std::array<ws43b_native::Point,4> rim{};
  std::array<uint16_t,24*Scene::modelWidth> firstTop{};
  int previousWall=0;size_t topPixelChecks=0;
  for(int progress=0;progress<=100;++progress) {
    assert(white.compose(progress,0x07e0,0x0084));
    assert(white.top()+43+white.wallPixels()==Scene::modelBase);
    assert(white.wallPixels()>=previousWall);previousWall=white.wallPixels();
    for(unsigned i=0;i<4;++i) {
      const auto point=white.rimPoint(i);
      if(!progress)rim[i]={point.x,point.y-white.top()};
      assert(point.x==rim[i].x&&point.y-white.top()==rim[i].y);
      const auto head=white.position(i*1800u);
      assert(head.x+Scene::headTipX==point.x&&head.y+Scene::headTipY==point.y);
    }
    // Pixel positions inside the unchanged upper rim. Nearly opaque source
    // pixels retain their appearance independently of the wall-height mapping.
    for(int row=0;row<24;++row)for(int column=0;column<Scene::modelWidth;++column) {
      const auto &asset=ws43b_assets::descriptor(ws43b_assets::Asset::Model);
      const auto sample=ws43b_native::filtered(asset,((column*2+1)*160*128/Scene::modelWidth)-128,
        ((row*2+1)*160*128/Scene::modelWidth)-128,0x07e0,true);
      const int topLimit=column<=60?27+(column-3)*16/57:43-(column-60)*29/48;
      if(sample.alpha<250||row>=topLimit-2)continue;
      const uint16_t actual=stored[(white.top()+row)*Scene::width+Scene::modelX+column];
      if(!progress)firstTop[row*Scene::modelWidth+column]=actual;
      else {
        const auto expected=firstTop[row*Scene::modelWidth+column];
        // Source alpha is253, so its2/255 background contribution may cross
        // one RGB565 rounding step after the rim translates vertically.
        assert(std::abs(int(ws43b_assets::red(actual))-int(ws43b_assets::red(expected)))<=9);
        assert(std::abs(int(ws43b_assets::green(actual))-int(ws43b_assets::green(expected)))<=5);
        assert(std::abs(int(ws43b_assets::blue(actual))-int(ws43b_assets::blue(expected)))<=9);
      }
      ++topPixelChecks;
    }
  }
  assert(topPixelChecks>10000);
  // Opaque backdrop corners equal the enclosing card at absolute coordinates.
  // Moving a scene by one pixel changes the dither origin and invalidates cache.
  for(auto theme:themes)for(const auto origin:std::array<ws43b_native::Point,3>{{{228,74},{229,75},{231,77}}}) {
    Canvas a(800,480),b(800,480);
    assert(white.render(a,origin.x,origin.y,49,0x07e0,theme,2700));
    Scene fresh(freshStorage.data());assert(fresh.render(b,origin.x,origin.y,49,0x07e0,theme,2700,true));
    assert(equivalent(a,b));
    for(int py=0;py<Scene::height;++py)for(int px:{0,1,Scene::width-2,Scene::width-1})
      assert(a.get(origin.x+px,origin.y+py)==ws43b_native::cardbg(origin.x+px,origin.y+py,66,242,theme));
  }
  // Region restoration is independent of how a rectangle is split into calls.
  size_t ditherCells=0;
  for(auto theme:themes) {
    Canvas whole(800,480),split(800,480);
    ws43b_native::screen(whole,theme);
    ws43b_native::gradientRect(split,0,0,401,480,[&](int x,int y){return ws43b_native::textbg(x,y,theme);});
    ws43b_native::gradientRect(split,401,0,399,480,[&](int x,int y){return ws43b_native::textbg(x,y,theme);});
    assert(equivalent(whole,split));
    // Averaged dither retains the intended 8-bit palette to within one display
    // code step; no temporal noise or frame phase enters this calculation.
    for(int py=66;py<308;py+=4) {
      unsigned sums[3]={};bool varied=false;uint16_t first=ws43b_native::cardbg(528,py,66,242,theme);
      for(int dy=0;dy<4;++dy)for(int dx=0;dx<4;++dx) {
        const auto value=ws43b_native::cardbg(528+dx,py+dy,66,242,theme);
        sums[0]+=ws43b_assets::red(value);sums[1]+=ws43b_assets::green(value);sums[2]+=ws43b_assets::blue(value);
        varied|=value!=first;
      }
      const auto target=ws43b_native::cardColor(py+1,66,242,theme);
      assert(std::abs(int(sums[0])-int(target.r*16))<=32);
      assert(std::abs(int(sums[1])-int(target.g*16))<=24);
      assert(std::abs(int(sums[2])-int(target.b*16))<=32);
      ditherCells+=varied;
    }
  }
  assert(ditherCells>300);
  size_t gradientComparisons=0;
  for(auto theme:themes)for(int origin:{-3,0,1,2,3,65})for(int extent:{1,2,3,4,63,64,65,137}) {
    Canvas optimized(210,30),generic(210,30);size_t optimizedSamples=0,genericSamples=0;
    auto background=[&](int x,int y){return ws43b_native::cardbg(x,y,0,30,theme,0x67b6,24);};
    ws43b_native::gradientRect(optimized,origin,3,extent,20,[&](int x,int y){++optimizedSamples;return background(x,y);});
    ws43b_native::rasterRect(generic,origin,3,extent,20,[&](int x,int y){++genericSamples;return background(x,y);});
    assert(equivalent(optimized,generic));assert(optimizedSamples<=80);
    assert(genericSamples==size_t(extent)*20);++gradientComparisons;
  }
  std::cout<<"{\"partial_full_comparisons\":"<<comparisons<<",\"partial_frames\":"<<partialFrames
           <<",\"position_checks\":"<<positionChecks<<",\"material_difference_pixels\":"<<materialDifferences
           <<",\"gradient_comparisons\":"<<gradientComparisons
           <<",\"head_sample_checks\":"<<headSampleChecks<<",\"cache_fallback_comparisons\":"<<comparisons
           <<",\"noop_frames\":"<<noOpFrames<<",\"head_cache_bytes\":"<<Scene::headCachePixels*sizeof(ws43b_native::Pixel)
           <<",\"top_pixel_checks\":"<<topPixelChecks<<",\"dither_cells\":"<<ditherCells
           <<",\"bounds\":\"PASS\",\"result\":\"PASS\"}\n";
}

void preview(const std::string &path,int progress,uint16_t color,uint16_t theme,uint32_t phase,bool heroOnly) {
  using namespace ws43b_native;
  std::vector<uint16_t> storage(size_t(Scene::width)*Scene::height);Scene scene(storage.data());
  if(heroOnly) {
    Canvas canvas(800,480);assert(scene.render(canvas,228,74,progress,color,theme,phase,true));
    canvas.ppm(path,228,74,Scene::width,Scene::height);return;
  }
  Canvas canvas(800,480);screen(canvas,theme);
  card(canvas,16,66,500,242,theme);
  assert(scene.render(canvas,228,74,progress,color,theme,phase,true));
  const ws43b_assets::Asset thermal[]={ws43b_assets::Asset::Nozzle,ws43b_assets::Asset::Bed,ws43b_assets::Asset::Chamber};
  for(unsigned i=0;i<3;++i) {
    const int top=66+84*int(i);card(canvas,528,top,256,74,theme);
    assert(sprite(canvas,thermal[i],538,top+14,[&](int x,int y){return canvas.get(x,y);}));
  }
  for(unsigned i=0;i<4;++i) {
    const int x=16+194*int(i);card(canvas,x,345,184,80,theme);
    const uint16_t shades[]={color,0xffff,0,0xf800};
    assert(sprite(canvas,ws43b_assets::Asset::Spool,x+4,351,[&](int px,int py){return canvas.get(px,py);},true,shades[i]));
  }
  canvas.fillRect(0,435,800,45,rgb(11,24,35));
  const ws43b_assets::Asset nav[]={ws43b_assets::Asset::Print,ws43b_assets::Asset::AMS,ws43b_assets::Asset::Details,ws43b_assets::Asset::Settings};
  for(unsigned i=0;i<4;++i)assert(sprite(canvas,nav[i],40+196*int(i),441,[&](int px,int py){return canvas.get(px,py);},i==0,color));
  assert(canvas.outside==0);canvas.ppm(path);
}

// CPU-only host comparison with the same work, including identical writes.
// It deliberately excludes first-frame composition/cache setup and is not an
// ESP32 FPS measurement: panel transfer, PSRAM bandwidth and scheduling differ.
void benchmark(int frames) {
  using namespace ws43b_native;
  assert(frames>0);
  std::vector<uint16_t> storage(size_t(Scene::width)*Scene::height);
  std::array<Pixel,Scene::headCachePixels> cache{};
  double elapsed[2]={};size_t writes[2]={},calls[2]={};
  uint64_t checksum[2]={};
  for(unsigned mode=0;mode<2;++mode) {
    Scene scene(storage.data(),mode?cache.data():nullptr);
    Canvas canvas(Scene::width,Scene::height);
    assert(scene.render(canvas,0,0,68,0x07e0,0x0084,0));
    canvas.resetCounts();
    const auto start=std::chrono::steady_clock::now();
    for(int frame=1;frame<=frames;++frame)
      assert(scene.render(canvas,0,0,68,0x07e0,0x0084,uint32_t(frame)*50u));
    elapsed[mode]=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
    writes[mode]=canvas.writes;calls[mode]=canvas.calls;
    for(auto pixel:canvas.pixels)checksum[mode]=checksum[mode]*131+pixel;
  }
  assert(writes[0]==writes[1]&&calls[0]==calls[1]&&checksum[0]==checksum[1]);
  std::cout<<"{\"measurement\":\"host CPU only, not ESP FPS\",\"frames_each\":"<<frames
      <<",\"fallback_ms\":"<<elapsed[0]<<",\"cache_ms\":"<<elapsed[1]
      <<",\"writes_each\":"<<writes[0]<<",\"calls_each\":"<<calls[0]
      <<",\"final_checksum_each\":"<<checksum[0]<<"}\n";
}

#if defined(WS43B_TEST_ALLOCATIONS)
void verifyAllocations(const std::string &mode) {
  using namespace ws43b_native;
  fake_heap::failAt=mode=="missing"?1:mode=="fallback"?2:0;
  assert(!heroHeadCacheReady()&&fake_heap::requests.empty());
  Canvas canvas(Scene::width,Scene::height);
  const bool available=mode!="missing",cached=mode=="cache";
  assert(hero(canvas,0,0,68,0x07e0,0x0084,0)==available);
  assert(heroHeadCacheReady()==cached);
  const auto attempts=fake_heap::requests.size();
  assert(attempts==(available?2u:1u));
  assert(fake_heap::requests[0].bytes==size_t(Scene::width)*Scene::height*sizeof(uint16_t));
  if(available)assert(fake_heap::requests[1].bytes==Scene::headCachePixels*sizeof(Pixel));
  for(const auto &request:fake_heap::requests)assert(request.flags==(MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
  for(unsigned frame=1;frame<=145;++frame) {
    canvas.resetCounts();
    assert(hero(canvas,0,0,68,0x07e0,0x0084,frame*50u)==available);
    assert(heroHeadCacheReady()==cached&&fake_heap::requests.size()==attempts);
    if(!available)assert(canvas.writes==0);
  }
  std::cout<<"{\"allocation_mode\":\""<<mode<<"\",\"allocation_attempts\":"<<attempts
      <<",\"frames\":146,\"result\":\"PASS\"}\n";
  for(const auto &request:fake_heap::requests)std::free(request.address);
}
#endif
}

int main(int argc,char **argv) {
  if(argc==2&&std::string(argv[1])=="--verify"){verify();return 0;}
  if(argc==3&&std::string(argv[1])=="--benchmark"){benchmark(std::stoi(argv[2]));return 0;}
#if defined(WS43B_TEST_ALLOCATIONS)
  if(argc==3&&std::string(argv[1])=="--verify-allocation"){verifyAllocations(argv[2]);return 0;}
#endif
  if(argc==8&&std::string(argv[1])=="--preview") {
    preview(argv[2],std::stoi(argv[3]),uint16_t(std::stoul(argv[4],nullptr,16)),
      uint16_t(std::stoul(argv[5],nullptr,16)),uint32_t(std::stoul(argv[6])),std::string(argv[7])=="hero");return 0;
  }
  std::cerr<<"Usage: preview_native --verify | --benchmark frames | --preview output.ppm progress tintHex themeHex phaseMs hero|layout\n";return 2;
}
