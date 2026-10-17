#include "ws43b_weather_background.h"
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <array>
using namespace ws43b_weather_bg;
struct Canvas {
 std::array<uint16_t,800*480> pixels{};
 void pixel(int x,int y,uint16_t c){if(x>=0&&x<800&&y>=0&&y<480)pixels[y*800+x]=c;}
 void fillRect(int x,int y,int w,int h,uint16_t c){for(int j=y;j<y+h;++j)for(int i=x;i<x+w;++i)pixel(i,j,c);}
 void fillCircle(int x,int y,int r,uint16_t c){for(int j=-r;j<=r;++j)for(int i=-r;i<=r;++i)if(i*i+j*j<=r*r)pixel(x+i,y+j,c);}
 void fillRoundRect(int x,int y,int w,int h,int r,uint16_t c){fillRect(x+r,y,w-2*r,h,c);fillRect(x,y+r,w,h-2*r,c);for(int a:{x+r,x+w-r-1})for(int b:{y+r,y+h-r-1})fillCircle(a,b,r,c);}
 void drawLine(int x,int y,int xx,int yy,uint16_t c){int dx=abs(xx-x),sx=x<xx?1:-1,dy=-abs(yy-y),sy=y<yy?1:-1,e=dx+dy;for(;;){pixel(x,y,c);if(x==xx&&y==yy)break;int t=2*e;if(t>=dy){e+=dy;x+=sx;}if(t<=dx){e+=dx;y+=sy;}}}
 void drawFastHLine(int x,int y,int w,uint16_t c){fillRect(x,y,w,1,c);}
 void drawFastVLine(int x,int y,int h,uint16_t c){fillRect(x,y,1,h,c);}
 void save(const char *path){std::ofstream f(path,std::ios::binary);f<<"P6\n800 480\n255\n";for(auto p:pixels){const char b[]={char(((p>>11)&31)*255/31),char(((p>>5)&63)*255/63),char((p&31)*255/31)};f.write(b,3);}}
};
int main(int argc,char**argv){
 for(int c=-1;c<=100;++c){assert(classify(false,true,c)==Kind::Neutral);assert(classify(true,false,c)==Kind::Neutral);}
 for(int c:{71,73,75,77,85,86})assert(classify(true,true,c)==Kind::Snow);
 for(int c:{51,53,55,56,57,61,63,65,66,67,80,81,82})assert(classify(true,true,c)==Kind::Rain);
 for(int c:{95,96,99})assert(classify(true,true,c)==Kind::Storm);
 assert(classify(true,true,0)==Kind::Clear);assert(classify(true,true,1)==Kind::Clear);
 assert(classify(true,true,2)==Kind::Cloud);assert(classify(true,true,3)==Kind::Cloud);
 assert(classify(true,true,45)==Kind::Fog);assert(classify(true,true,48)==Kind::Fog);
 assert(classify(true,true,50)==Kind::Neutral);
 Canvas s;s.fillRect(0,0,800,480,0x0843);auto initial=s.pixels;draw(s,Kind::Neutral,true,0x0843);assert(s.pixels==initial);
 for(auto k:{Kind::Clear,Kind::Cloud,Kind::Fog,Kind::Rain,Kind::Snow,Kind::Storm}){
   draw(s,k,false,0x0843);auto day=s.pixels;draw(s,k,false,0x0843);assert(s.pixels==day);
   draw(s,k,true,0x0843);assert(s.pixels!=day);
 }
 if(argc==4){s.fillRect(0,0,800,480,0x0843);draw(s,Kind(atoi(argv[1])),atoi(argv[2])!=0,0x0843);s.save(argv[3]);}
 puts("PASS: weather mapping, freshness fallback, deterministic rendering and night palettes");
}
