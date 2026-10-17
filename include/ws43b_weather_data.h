#pragma once
#include <ArduinoJson.h>
#include <stdint.h>
#include <math.h>
#include <string.h>
namespace ws43b_weather {
struct Config { bool enabled=false, solar=false; float latitude=0, longitude=0; uint16_t nightSeconds=30; char city[64]={}; uint32_t revision=0; };
struct Data { bool valid=false; float temperature=0; int code=0; int64_t observed=0; int64_t rise[3]={},set[3]={}; uint32_t revision=0; };
inline bool parseConfig(JsonVariantConst v, Config &out) {
 if(!v.is<JsonObjectConst>() || v.size()!=6 || !v["enabled"].is<bool>() || !v["solar"].is<bool>() ||
    !v["latitude"].is<float>() || !v["longitude"].is<float>() || !v["night_seconds"].is<unsigned>() || !v["city"].is<const char*>()) return false;
 Config c; c.enabled=v["enabled"];c.solar=v["solar"];c.latitude=v["latitude"];c.longitude=v["longitude"];c.nightSeconds=v["night_seconds"];
 const char *city=v["city"];
 if(strlen(city)>=sizeof(c.city) || !isfinite(c.latitude)||!isfinite(c.longitude)||fabs(c.latitude)>90||fabs(c.longitude)>180||
    (c.nightSeconds!=30&&c.nightSeconds!=60&&c.nightSeconds!=300)||((c.enabled||c.solar)&&!*city))return false;
 for(const unsigned char *p=(const unsigned char*)city;*p;++p)if(*p<32||*p==127)return false;
 strcpy(c.city,city);out=c;return true;
}
inline bool parseData(JsonVariantConst v,Data &out) {
 auto current=v["current"];Data d;
 if(!current["temperature_2m"].is<float>()||!current["time"].is<int64_t>()||!current["weather_code"].is<int>())return false;
 d.temperature=current["temperature_2m"];d.observed=current["time"];d.code=current["weather_code"];
 if(!isfinite(d.temperature)||d.temperature< -100||d.temperature>70||d.observed<1577836800||d.code<0||d.code>99)return false;
 auto rise=v["daily"]["sunrise"],set=v["daily"]["sunset"];
 for(int i=0;i<3;++i)if(rise[i].is<int64_t>()&&set[i].is<int64_t>()) {
   int64_t a=rise[i],b=set[i];
   if(a>1577836800 && b>a && b-a<86400){d.rise[i]=a;d.set[i]=b;}
 }
 d.valid=true;out=d;return true;
}
inline bool fresh(const Data &d,int64_t now) {return d.valid && now>=d.observed && now-d.observed<=1800;}
// Caller supplies the local calendar day's epoch boundaries, including DST.
inline bool solarNight(const Data &d,int64_t now,int64_t dayStart,int64_t dayEnd,bool &night) {
 for(int i=0;i<3;++i)if(d.rise[i]>=dayStart&&d.rise[i]<dayEnd&&d.set[i]>d.rise[i]&&d.set[i]<dayEnd) {
   night=now<d.rise[i]||now>=d.set[i];return true;
 }
 return false;
}
}
