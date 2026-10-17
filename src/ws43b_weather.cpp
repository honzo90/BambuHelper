#include "ws43b_memory_diag.h"
#include "ws43b_weather_background.h"
#include "ws43b_weather.h"
#include "ws43b_tls_memory.h"
#include "ws43b_weather_schedule.h"
#if defined(BOARD_IS_WS43B)
#include "settings.h"
#include "bambu_mqtt.h"
#include "wifi_manager.h"
#include "ws43b_language.h"
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <freertos/idf_additions.h>
#include <esp_heap_caps.h>
#include <time.h>
extern const uint8_t rootca_crt_bundle_start[] asm("_binary_x509_crt_bundle_start");
extern const uint8_t rootca_crt_bundle_end[] asm("_binary_x509_crt_bundle_end");
namespace {
portMUX_TYPE guard=portMUX_INITIALIZER_UNLOCKED;
ws43b_weather::Config config;
ws43b_weather::Data data;
TaskHandle_t worker=nullptr;
void configJson(JsonDocument &j,const ws43b_weather::Config &c){
 j["enabled"]=c.enabled;j["solar"]=c.solar;j["latitude"]=c.latitude;j["longitude"]=c.longitude;j["city"]=c.city;j["night_seconds"]=c.nightSeconds;
}
class BoundedBody : public Stream {
 public:
 char *buf=nullptr;size_t used=0;uint32_t started=millis();
 BoundedBody(){buf=(char*)heap_caps_malloc(8193,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);}
 ~BoundedBody(){free(buf);}
 size_t write(uint8_t b) override{return write(&b,1);}
 size_t write(const uint8_t *p,size_t n) override {
  if(!buf||used+n>8192||uint32_t(millis()-started)>10000)return 0;
  memcpy(buf+used,p,n);used+=n;buf[used]=0;return n;
 }
 int available() override{return 0;}int read() override{return -1;}int peek() override{return -1;}void flush() override{}
};
bool fetch(const ws43b_weather::Config &c,ws43b_weather::Data &out) {
  ws43b_memory::Scope memory(ws43b_memory::Stage::Weather);
  ws43b_tls::WeatherScope tlsMemory;
  if (!tlsMemory.ready()) return false;
 WiFiClientSecure tls;tls.setCACertBundle(rootca_crt_bundle_start,rootca_crt_bundle_end-rootca_crt_bundle_start);tls.setHandshakeTimeout(5);
 HTTPClient http;http.setConnectTimeout(5000);http.setTimeout(2000);http.setFollowRedirects(HTTPC_DISABLE_FOLLOW_REDIRECTS);
 char url[360];snprintf(url,sizeof(url),"https://api.open-meteo.com/v1/forecast?latitude=%.5f&longitude=%.5f&current=temperature_2m,weather_code&daily=sunrise,sunset&timezone=auto&timeformat=unixtime&temperature_unit=celsius&forecast_days=3",double(c.latitude),double(c.longitude));
 if(!http.begin(tls,url))return false;
 http.addHeader("Accept","application/json");
 bool ok=false;
 if(http.GET()==200 && http.getSize()<=8192) {
  BoundedBody body;
  if(body.buf && http.writeToStream(&body)>0){JsonDocument j;ok=!deserializeJson(j,body.buf,body.used,DeserializationOption::NestingLimit(8))&&ws43b_weather::parseData(j.as<JsonVariantConst>(),out);}
 }
 http.end();return ok;
}
void weatherTask(void*) {
 ws43b_weather::FetchSchedule schedule;
 for(;;) {
  const auto c=ws43bWeatherConfig();
  // Let the first printer handshake finish before opening another TLS session.
  // An offline printer must not suppress weather indefinitely.
  const bool printerReady=!isAnyPrinterConfigured() || getMqttDiag().connectTime>0 || millis()>=30000;
  const bool ready=(c.enabled||c.solar)&&*c.city&&WiFi.status()==WL_CONNECTED&&
    time(nullptr)>1577836800 && ws43b_tls::canStartWeather(heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
      heap_caps_get_free_size(MALLOC_CAP_SPIRAM)) && printerReady;
  const uint32_t wait=schedule.waitMs(millis(),c.revision,ready);
  if(wait) {ulTaskNotifyTake(pdTRUE,pdMS_TO_TICKS(wait));continue;}
  ws43b_weather::Data next;
  const bool ok=fetch(c,next);
  ws43b_memory::weatherResult(ok);
  schedule.completed(millis(),ok);
  portENTER_CRITICAL(&guard);
  if(ok&&c.revision==config.revision){next.revision=data.revision+1;data=next;}
  portEXIT_CRITICAL(&guard);
 }
}
}
ws43b_weather::Config ws43bWeatherConfig(){portENTER_CRITICAL(&guard);auto c=config;portEXIT_CRITICAL(&guard);return c;}
ws43b_weather::Data ws43bWeatherData(){portENTER_CRITICAL(&guard);auto d=data;portEXIT_CRITICAL(&guard);return d;}
void loadWs43bWeather(){
 Preferences p;if(!p.begin(NVS_NAMESPACE,true))return;String text=p.getString("w43_weather","");p.end();
 if(text.length()>1024)return;JsonDocument j;ws43b_weather::Config c;
 if(!deserializeJson(j,text)&&ws43b_weather::parseConfig(j.as<JsonVariantConst>(),c))config=c;
}
bool saveWs43bWeather(ws43b_weather::Config c){
 JsonDocument j;configJson(j,c);ws43b_weather::Config valid;if(!ws43b_weather::parseConfig(j.as<JsonVariantConst>(),valid))return false;
 String next;serializeJson(j,next);JsonDocument prev;configJson(prev,ws43bWeatherConfig());String old;serializeJson(prev,old);if(old==next)return true;
 Preferences p;if(!p.begin(NVS_NAMESPACE,false))return false;bool ok=p.putString("w43_weather",next)==next.length();p.end();if(!ok)return false;
 portENTER_CRITICAL(&guard);
 const bool locationChanged=c.latitude!=config.latitude || c.longitude!=config.longitude || strcmp(c.city,config.city);
 c.revision=config.revision+1;config=c;
 if(locationChanged){const auto rev=data.revision+1;data={};data.revision=rev;}
 portEXIT_CRITICAL(&guard);
 if(worker)xTaskNotifyGive(worker);return true;
}
void tickWs43bWeather(){
 if(worker)return;
 static bool attempted=false;static uint32_t lastAttempt=0;
 if(attempted&&uint32_t(millis()-lastAttempt)<60000)return;
 const auto c=ws43bWeatherConfig();
 if((c.enabled||c.solar)&&*c.city&&isWiFiConnected()&&!isAPMode()) {
  attempted=true;lastAttempt=millis();
  if(xTaskCreatePinnedToCoreWithCaps(weatherTask,"weather",12288,nullptr,1,&worker,0,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT)!=pdPASS)worker=nullptr;
 }
}
bool ws43bSolarNight(bool &night){
 const auto c=ws43bWeatherConfig();if(!c.solar)return false;const time_t now=time(nullptr);if(now<1577836800)return false;
 struct tm local{};localtime_r(&now,&local);local.tm_hour=local.tm_min=local.tm_sec=0;local.tm_isdst=-1;const time_t begin=mktime(&local);
 ++local.tm_mday;local.tm_isdst=-1;const time_t end=mktime(&local);
 return ws43b_weather::solarNight(ws43bWeatherData(),now,begin,end,night);
}
const char *ws43bWeatherDescription(int c){
 switch(c) {
  case 0: return ws43bText("Bezchmurnie","Clear");
  case 1: return ws43bText("Przeważnie bezchmurnie","Mainly clear");
  case 2: return ws43bText("Częściowe zachmurzenie","Partly cloudy");
  case 3: return ws43bText("Zachmurzenie","Cloudy");
  case 45: return ws43bText("Mgła","Fog");
  case 48: return ws43bText("Mgła osadzająca szadź","Rime fog");
  case 51: return ws43bText("Lekka mżawka","Light drizzle");
  case 53: return ws43bText("Umiarkowana mżawka","Moderate drizzle");
  case 55: return ws43bText("Silna mżawka","Heavy drizzle");
  case 56: return ws43bText("Lekka marznąca mżawka","Light freezing drizzle");
  case 57: return ws43bText("Silna marznąca mżawka","Heavy freezing drizzle");
  case 61: return ws43bText("Lekki deszcz","Light rain");
  case 63: return ws43bText("Umiarkowany deszcz","Moderate rain");
  case 65: return ws43bText("Silny deszcz","Heavy rain");
  case 66: return ws43bText("Lekki marznący deszcz","Light freezing rain");
  case 67: return ws43bText("Silny marznący deszcz","Heavy freezing rain");
  case 71: return ws43bText("Lekki śnieg","Light snow");
  case 73: return ws43bText("Umiarkowany śnieg","Moderate snow");
  case 75: return ws43bText("Silny śnieg","Heavy snow");
  case 77: return ws43bText("Śnieg ziarnisty","Snow grains");
  case 80: return ws43bText("Lekkie przelotne opady","Light rain showers");
  case 81: return ws43bText("Przelotny deszcz","Rain showers");
  case 82: return ws43bText("Gwałtowne opady deszczu","Violent rain showers");
  case 85: return ws43bText("Przelotny śnieg","Snow showers");
  case 86: return ws43bText("Silne przelotne opady śniegu","Heavy snow showers");
  case 95: return ws43bText("Burza","Thunderstorm");
  case 96: return ws43bText("Burza z drobnym gradem","Thunderstorm with small hail");
  case 97: return ws43bText("Silna burza","Heavy thunderstorm");
  case 99: return ws43bText("Burza z silnym gradem","Thunderstorm with heavy hail");
  default: return ws43bText("Pogoda","Weather");
 }
}
// Completion lives on the device, never in browser storage. Skip changes no settings.
bool ws43bSetupDone(){
 Preferences p;if(!p.begin(NVS_NAMESPACE,true))return false;
 bool done=p.getBool("w43_setup",false);p.end();return done;
}
bool finishWs43bSetup(bool skip,bool dark){
 Preferences p;if(!p.begin(NVS_NAMESPACE,false))return false;
 bool ok=true;
 if(!skip){
  ok=p.putBool("dp_night",true)==1;
  ok=(p.putUChar("dp_nbright",dark?0:100)==1)&&ok;
 }
 if(ok)ok=p.putBool("w43_setup",true)==1;
 p.end();
 if(ok&&!skip){dpSettings.nightModeEnabled=true;dpSettings.nightBrightness=dark?0:100;}
 return ok;
}
#endif
