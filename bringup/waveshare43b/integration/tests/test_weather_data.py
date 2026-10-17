from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[4]
class WeatherDataTests(unittest.TestCase):
 def test_validation_staleness_solar_boundaries(self):
  code=r'''#include "ws43b_weather_data.h"
#include <cassert>
using namespace ws43b_weather;
int main(){
 JsonDocument j;
 auto parse=[&](const char *s){j.clear();assert(!deserializeJson(j,s));};
 Config c;
 parse(R"({"enabled":true,"solar":true,"latitude":52.1,"longitude":13.2,"city":"Example","night_seconds":30})");
 assert(parseConfig(j.as<JsonVariantConst>(),c));assert(c.solar && c.nightSeconds==30);
 j["latitude"]=91;assert(!parseConfig(j.as<JsonVariantConst>(),c));j["latitude"]=0;
 j["city"]="";assert(!parseConfig(j.as<JsonVariantConst>(),c));j["city"]="Example";
 j["night_seconds"]=65566;assert(!parseConfig(j.as<JsonVariantConst>(),c));
 j["night_seconds"]=60;assert(parseConfig(j.as<JsonVariantConst>(),c));
 j["longitude"]="13";assert(!parseConfig(j.as<JsonVariantConst>(),c));
 parse(R"({"current":{"time":1700000000,"temperature_2m":0,"weather_code":0},"daily":{"sunrise":[1700021600,1700108000,null],"sunset":[1700064800,1700151200,null]}})");
 Data d;assert(parseData(j.as<JsonVariantConst>(),d));assert(d.valid && d.temperature==0);
 assert(fresh(d,1700001800));assert(!fresh(d,1700001801));assert(!fresh(d,1699999999));
 bool night=false;
 assert(solarNight(d,1700021599,1700000000,1700086400,night)&&night);
 assert(solarNight(d,1700021600,1700000000,1700086400,night)&&!night);
 assert(solarNight(d,1700064800,1700000000,1700086400,night)&&night);
 assert(!solarNight(d,1700172800,1700172800,1700259200,night)); // no today's solar data -> manual fallback
 j["current"]["temperature_2m"]=nullptr;assert(!parseData(j.as<JsonVariantConst>(),d));
 j["current"]["temperature_2m"]=120;assert(!parseData(j.as<JsonVariantConst>(),d));
 j["current"]["temperature_2m"]=-2; j["daily"]["sunrise"][0]=nullptr;
 assert(parseData(j.as<JsonVariantConst>(),d));assert(!solarNight(d,1700030000,1700000000,1700086400,night));
 d.rise[0]=1700021600;d.set[0]=1700064800;
 assert(solarNight(d,1700030000,1700000000,1700082800,night)&&!night); // 23-hour DST day
 assert(solarNight(d,1700070000,1700000000,1700090000,night)&&night); // 25-hour DST day
}'''
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'test.cpp').write_text(code)
   subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(ROOT/'include'),'-I',str(ROOT/'bringup/waveshare43b/integration/vendor/ArduinoJson-7.4.3/src'),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
   subprocess.run([str(p/'test')],check=True)
 def test_atomic_nvs_failure_and_roundtrip(self):
  source=(ROOT/'src/ws43b_weather.cpp').read_text()
  helper=source[source.index('void configJson('):source.index('class BoundedBody')]
  storage=source[source.index('void loadWs43bWeather()'):source.index('void tickWs43bWeather()')]
  code=r'''#include "ws43b_weather_data.h"
#include <cassert>
#include <string>
using String=std::string;
#define portENTER_CRITICAL(...)
#define portEXIT_CRITICAL(...)
const char *NVS_NAMESPACE="test";
ws43b_weather::Config config;
ws43b_weather::Data data;
int worker=0;void xTaskNotifyGive(int){}
ws43b_weather::Config ws43bWeatherConfig(){return config;}
String persisted;bool openOk=true,writeOk=true;unsigned writes=0;
struct Preferences {
 bool begin(const char*,bool){return openOk;}void end(){}
 String getString(const char *key,const char*){assert(!strcmp(key,"w43_weather"));return persisted;}
 size_t putString(const char *key,const String &v){assert(!strcmp(key,"w43_weather"));++writes;if(!writeOk)return 0;persisted=v;return v.length();}
};
''' + helper + storage + r'''
int main(){
 loadWs43bWeather();assert(!config.enabled);
 auto c=config;c.enabled=true;c.solar=true;c.latitude=52;c.longitude=13;strcpy(c.city,"Example");
 writeOk=false;assert(!saveWs43bWeather(c));assert(!config.enabled && data.revision==0);
 writeOk=true;assert(saveWs43bWeather(c));assert(config.enabled&&config.revision==1&&data.revision==1);
 unsigned n=writes;assert(saveWs43bWeather(c)&&writes==n);
 data.valid=true;const auto dataRevision=data.revision;
 c.nightSeconds=60;assert(saveWs43bWeather(c));assert(data.valid&&data.revision==dataRevision);n=writes;
 config={};loadWs43bWeather();assert(config.enabled&&config.solar&&!strcmp(config.city,"Example"));
 c.nightSeconds=17;assert(!saveWs43bWeather(c)&&writes==n);
 persisted="broken";config={};loadWs43bWeather();assert(!config.enabled);
 openOk=false;c.nightSeconds=60;assert(!saveWs43bWeather(c)&&writes==n);
}'''
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'test.cpp').write_text(code)
   subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(ROOT/'include'),'-I',str(ROOT/'bringup/waveshare43b/integration/vendor/ArduinoJson-7.4.3/src'),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
   subprocess.run([str(p/'test')],check=True)
