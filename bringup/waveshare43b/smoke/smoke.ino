// Isolated hardware smoke, based on Waveshare 08_DrawColorBar + its exact
// BOARD_WAVESHARE_ESP32_S3_TOUCH_LCD_4_3_B profile. No printer client or commands.
#include <Arduino.h>
#include <WiFi.h>
#include <esp_wifi.h>
#include <esp_heap_caps.h>
#include <esp_psram.h>
#include <esp_partition.h>
#include <esp_system.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <atomic>
#include "board_select.h"

using namespace esp_panel::board;
using namespace esp_panel::drivers;
static constexpr int W=800, H=480;
static Board board;
static LCD *lcd;
static Touch *touch;
static uint16_t *canvas;
static volatile uint32_t *ramProbe;
static constexpr size_t PROBE_WORDS=65536; // 256 KiB, separate from framebuffers
static uint32_t bootId, lastDiag, wifiSince, runSince, lastDropCount;
static std::atomic<uint32_t> drops{0};
// Events run on the network task. Copy numeric diagnostics only; never retain
// event_info SSID/BSSID/IP. A disconnect reason is historical, with an age.
static portMUX_TYPE wifiReasonMux=portMUX_INITIALIZER_UNLOCKED;
static int lastWifiReason=-1;
static uint32_t lastWifiDisconnectMs;
static std::atomic<uint32_t> wifiAssociations{0}, wifiGotIpEvents{0};
enum class WifiTraceKind : uint8_t { START, STOP, CONNECTED, DISCONNECTED, GOT_IP, LOST_IP };
struct WifiTraceEvent {
  uint32_t seq, uptimeMs;
  WifiTraceKind kind;
  int16_t reason;
};
static constexpr size_t WIFI_TRACE_CAPACITY=16;
static StaticQueue_t wifiTraceControl;
static uint8_t wifiTraceStorage[WIFI_TRACE_CAPACITY*sizeof(WifiTraceEvent)];
static QueueHandle_t wifiTraceQueue;
static uint32_t wifiTraceSeq; // Written only by the network event task.
static std::atomic<uint32_t> wifiTraceDropped{0};
// A separate diagnostic mode: one scan before any connection/run, then reset.
// Target name and AP records never leave RAM; only numeric summaries go to USB.
static bool scanConsumed, scanActive, wifiAttempted;
static char scanTarget[33];
static uint32_t scanStartedMs;
static std::atomic<bool> scanListening{false}, scanDone{false};
static std::atomic<uint32_t> scanStatus{0};
static uint8_t targets;
static uint32_t touchErrors, memoryErrors;
static bool running, readyPrinted;
static const int tx[5]={50,750,50,750,400}, ty[5]={65,65,410,410,240};
static const uint16_t colors[8]={0xf800,0x07e0,0x001f,0xffff,0x0000,0xffe0,0x07ff,0xf81f};
// Original compact 5x7 glyphs, columns, ASCII digits and uppercase letters.
static const uint8_t glyphs[36][5]={
 {62,81,73,69,62},{0,66,127,64,0},{66,97,81,73,70},{33,65,69,75,49},{24,20,18,127,16},
 {39,69,69,69,57},{60,74,73,73,48},{1,113,9,5,3},{54,73,73,73,54},{6,73,73,41,30},
 {126,17,17,17,126},{127,73,73,73,54},{62,65,65,65,34},{127,65,65,34,28},{127,73,73,73,65},
 {127,9,9,9,1},{62,65,73,73,122},{127,8,8,8,127},{0,65,127,65,0},{32,64,65,63,1},
 {127,8,20,34,65},{127,64,64,64,64},{127,2,12,2,127},{127,4,8,16,127},{62,65,65,65,62},
 {127,9,9,9,6},{62,65,81,33,94},{127,9,25,41,70},{38,73,73,73,50},{1,1,127,1,1},
 {63,64,64,64,63},{31,32,64,32,31},{63,64,56,64,63},{99,20,8,20,99},{7,8,112,8,7},{97,81,73,69,67}
};
static void die(const char *reason) {
  for (;;) { Serial.printf("FATAL boot=%08lx reason=%s\n", (unsigned long)bootId, reason); delay(1000); }
}
static const char *wifiTraceName(WifiTraceKind kind) {
  switch(kind) {
    case WifiTraceKind::START:return "START";
    case WifiTraceKind::STOP:return "STOP";
    case WifiTraceKind::CONNECTED:return "CONNECTED";
    case WifiTraceKind::DISCONNECTED:return "DISCONNECTED";
    case WifiTraceKind::GOT_IP:return "GOT_IP";
    case WifiTraceKind::LOST_IP:return "LOST_IP";
  }
  return "UNKNOWN";
}
static void enqueueWifiEvent(WifiTraceKind kind,int reason=-1) {
  const WifiTraceEvent item{++wifiTraceSeq,millis(),kind,int16_t(reason)};
  if(xQueueSend(wifiTraceQueue,&item,0)!=pdTRUE) ++wifiTraceDropped;
}
static void drainWifiEvents() {
  // Single consumer; peek until the serial buffer can take a complete record.
  // Never wait on the network task or add blocking writes under backpressure.
  for(size_t i=0;i<WIFI_TRACE_CAPACITY;++i) {
    WifiTraceEvent item;
    if(xQueuePeek(wifiTraceQueue,&item,0)!=pdTRUE) break;
    char text[160];
    const int n=snprintf(text,sizeof(text),
      "WIFI_EVENT boot=%08lx seq=%lu uptime_ms=%lu event=%s reason=%d\n",
      (unsigned long)bootId,(unsigned long)item.seq,(unsigned long)item.uptimeMs,
      wifiTraceName(item.kind),int(item.reason));
    if(n<=0 || size_t(n)>=sizeof(text)) break;
    if(Serial.availableForWrite()<n) break;
    if(xQueueReceive(wifiTraceQueue,&item,0)!=pdTRUE) break;
    if(Serial.write(reinterpret_cast<const uint8_t*>(text),size_t(n))!=size_t(n)) ++wifiTraceDropped;
  }
}
static void rect(int x,int y,int w,int h,uint16_t c) {
  for(int j=max(0,y);j<min(H,y+h);++j) for(int i=max(0,x);i<min(W,x+w);++i) canvas[j*W+i]=c;
}
static void label(int x,int y,const char *s,int scale=2,uint16_t color=0xffff) {
  for(;*s;++s,x+=6*scale) {
    int g=(*s>='0'&&*s<='9')?*s-'0':((*s>='A'&&*s<='Z')?*s-'A'+10:-1);
    if(g<0) continue;
    for(int col=0;col<5;++col) for(int row=0;row<7;++row)
      if(glyphs[g][col]&(1<<row)) rect(x+col*scale,y+row*scale,scale,scale,color);
  }
}
static void flushRows(int y,int h) {
  y=max(0,y); h=min(H-y,h);
  if(!lcd->drawBitmap(0,y,W,h,reinterpret_cast<uint8_t*>(canvas+y*W))) die("LCD_DRAW");
}
static void drawTarget(int i) {
  const uint16_t c=(targets&(1<<i))?0x07e0:0xffff;
  rect(tx[i]-26,ty[i]-26,53,53,0); rect(tx[i]-24,ty[i]-24,49,49,c);
  rect(tx[i]-21,ty[i]-21,43,43,0); char n[2]={char('1'+i),0}; label(tx[i]-7,ty[i]-10,n,3,c);
}
static void pattern() {
  for(int i=0;i<8;++i) rect(i*100,0,100,H,colors[i]);
  rect(0,0,W,30,0); label(8,8,"WAVESHARE 4 3B 800 X 480   TOP",2);
  rect(0,H-35,W,35,0); label(8,H-28,"RGB W K Y C M   TOUCH TARGETS 1 2 3 4 5",2);
  for(int i=0;i<5;++i) drawTarget(i);
  flushRows(0,H);
}
static bool checkRam() {
  for(size_t i=0;i<PROBE_WORDS;++i) if(ramProbe[i]!=(0xa55a1234u ^ uint32_t(i)*2654435761u)) return false;
  return true;
}
static const char *resetName() {
  switch(esp_reset_reason()) {
    case ESP_RST_POWERON:return "POWERON"; case ESP_RST_SW:return "SOFTWARE";
    case ESP_RST_PANIC:return "PANIC"; case ESP_RST_INT_WDT:return "INT_WDT";
    case ESP_RST_TASK_WDT:return "TASK_WDT"; case ESP_RST_WDT:return "WDT";
    case ESP_RST_BROWNOUT:return "BROWNOUT"; case ESP_RST_DEEPSLEEP:return "DEEPSLEEP";
    case ESP_RST_EXT:return "EXTERNAL"; case ESP_RST_USB:return "USB";
    default:return "OTHER";
  }
}
static void bootReport() {
  Serial.println("SMOKE_ID waveshare43b-v4 800x480");
  Serial.printf("BOOT boot=%08lx reset=%d reset_name=%s flash=%lu psram_physical=%u psram_heap=%lu sdk=%s\n",
    (unsigned long)bootId,int(esp_reset_reason()),resetName(),(unsigned long)ESP.getFlashChipSize(),
    unsigned(esp_psram_get_size()),(unsigned long)ESP.getPsramSize(),ESP.getSdkVersion());
}
static void scanError(const char *stage, int32_t code, bool stop=false) {
  scanListening=false; scanActive=false;
  const esp_err_t stopResult=stop?esp_wifi_scan_stop():ESP_OK;
  const esp_err_t clearResult=esp_wifi_clear_ap_list();
  memset(scanTarget,0,sizeof(scanTarget));
  Serial.printf("SCAN_ERROR boot=%08lx stage=%s code=%ld\n",
    (unsigned long)bootId,stage,(long)code);
  if(stopResult!=ESP_OK) Serial.printf("SCAN_ERROR boot=%08lx stage=POLL code=%ld\n",(unsigned long)bootId,(long)stopResult);
  if(clearResult!=ESP_OK) Serial.printf("SCAN_ERROR boot=%08lx stage=POLL code=%ld\n",(unsigned long)bootId,(long)clearResult);
}
static void beginScan(const char *target) {
  if(scanConsumed||wifiAttempted||running) {
    Serial.printf("SCAN_REJECTED boot=%08lx reason=BUSY\n",(unsigned long)bootId); return;
  }
  const size_t length=strlen(target);
  if(!length||length>32||strchr(target,'\t')) {
    Serial.printf("SCAN_REJECTED boot=%08lx reason=SSID\n",(unsigned long)bootId); return;
  }
  memcpy(scanTarget,target,length+1);
  scanConsumed=true; scanDone=false; scanListening=true; scanStartedMs=millis();
  wifi_scan_config_t config{};
  config.channel=0; config.show_hidden=true; config.scan_type=WIFI_SCAN_TYPE_ACTIVE;
  config.scan_time.active.min=100; config.scan_time.active.max=300;
  // IDF directly: Arduino's wrapper may also return zero after allocation error.
  // No country override, connection, password, directed SSID probe or BSSID filter.
  const esp_err_t result=esp_wifi_scan_start(&config,false);
  if(result!=ESP_OK) { scanError("START",result); return; }
  scanActive=true;
  Serial.printf("SCAN_BEGIN boot=%08lx\n",(unsigned long)bootId);
}
static void pollScan() {
  if(!scanActive) return;
  if(!scanDone.load()) {
    if(uint32_t(millis()-scanStartedMs)>20000) scanError("TIMEOUT",ESP_ERR_TIMEOUT,true);
    return;
  }
  scanListening=false;
  if(scanStatus.load()!=0) { scanError("POLL",int32_t(scanStatus.load())); return; }
  uint16_t total=0, matches=0;
  esp_err_t result=esp_wifi_scan_get_ap_num(&total);
  if(result!=ESP_OK) { scanError("POLL",result); return; }
  int bestRssi=0, bestChannel=0, bestAuth=-1;
  const size_t targetLength=strlen(scanTarget);
  for(uint32_t i=0;i<total;++i) {
    wifi_ap_record_t ap{};
    result=esp_wifi_scan_get_ap_record(&ap); // Frees this record in driver RAM.
    if(result!=ESP_OK) { memset(&ap,0,sizeof(ap)); scanError("POLL",result); return; }
    const size_t length=strnlen(reinterpret_cast<const char*>(ap.ssid),sizeof(ap.ssid));
    if(length>32) { memset(&ap,0,sizeof(ap)); scanError("POLL",ESP_ERR_INVALID_RESPONSE); return; }
    if(length==targetLength&&!memcmp(ap.ssid,scanTarget,length)) {
      if(ap.rssi < -127 || ap.rssi>0 || ap.primary<1 || ap.primary>14 || int(ap.authmode)<0 || int(ap.authmode)>255) {
        memset(&ap,0,sizeof(ap)); scanError("POLL",ESP_ERR_INVALID_RESPONSE); return;
      }
      if(!matches||ap.rssi>bestRssi) { bestRssi=ap.rssi; bestChannel=ap.primary; bestAuth=int(ap.authmode); }
      ++matches;
    }
    memset(&ap,0,sizeof(ap));
  }
  result=esp_wifi_clear_ap_list();
  if(result!=ESP_OK) { scanError("POLL",result); return; }
  memset(scanTarget,0,sizeof(scanTarget)); scanActive=false;
  Serial.printf("SCAN_RESULT boot=%08lx total=%u matches=%u best_rssi=%d best_channel=%d best_auth=%d elapsed_ms=%lu\n",
    (unsigned long)bootId,unsigned(total),unsigned(matches),bestRssi,bestChannel,bestAuth,
    (unsigned long)(millis()-scanStartedMs));
}
static void command(char *line) {
  if(!strcmp(line,"STATUS")) { bootReport(); return; }
  if(!strncmp(line,"SCAN\t",5)) { beginScan(line+5); return; }
  if(scanConsumed) { Serial.println("COMMAND_REJECTED"); return; } // Reset before connection/acceptance test.
  if(!strcmp(line,"START")) {
    running=true; readyPrinted=false; runSince=millis(); wifiSince=0;
    targets=0; drops=0; lastDropCount=0; pattern();
    Serial.printf("RUN_BEGIN boot=%08lx\n",(unsigned long)bootId); return;
  }
  if(strncmp(line,"WIFI\t",5)) { Serial.println("COMMAND_REJECTED"); return; }
  char *ssid=line+5, *password=strchr(ssid,'\t');
  if(!password) { Serial.println("WIFI_REJECTED"); return; }
  *password++=0;
  if(strlen(ssid)<1||strlen(ssid)>32||strlen(password)>64) { Serial.println("WIFI_REJECTED"); return; }
  wifiAttempted=true;
  const wl_status_t beginStatus=WiFi.begin(ssid,password); // persistent(false): RAM only
  Serial.printf("WIFI_BEGIN boot=%08lx status=%d\n",(unsigned long)bootId,int(beginStatus));
  Serial.println("WIFI_ACCEPTED"); // no SSID, password, IP, MAC or printer credentials
}
static void serialInput() {
  static char line[128]; static size_t len; static bool discard;
  while(Serial.available()) {
    const char c=char(Serial.read());
    if(c=='\n') {
      if(!discard) { line[len]=0; command(line); }
      memset(line,0,sizeof(line)); len=0; discard=false;
    } else if(c!='\r') {
      if(len<sizeof(line)-1&&!discard) line[len++]=c; else discard=true;
    }
  }
}
void setup() {
  Serial.begin(115200); delay(1500); bootId=esp_random(); bootReport();
  if(esp_partition_find_first(ESP_PARTITION_TYPE_DATA,ESP_PARTITION_SUBTYPE_DATA_COREDUMP,nullptr)) die("COREDUMP_PARTITION_FORBIDDEN");
  if(!psramFound() || esp_psram_get_size()!=8*1024*1024) die("PSRAM_EXPECTED_8M");
  if(ESP.getFlashChipSize()!=16*1024*1024) die("FLASH_EXPECTED_16M");
  ramProbe=static_cast<uint32_t*>(heap_caps_malloc(PROBE_WORDS*4,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
  canvas=static_cast<uint16_t*>(heap_caps_malloc(W*H*2,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
  if(!ramProbe||!canvas) die("PSRAM_ALLOC");
  for(size_t i=0;i<PROBE_WORDS;++i) ramProbe[i]=0xa55a1234u ^ uint32_t(i)*2654435761u;
  if(!checkRam()) die("PSRAM_PATTERN");
  if(!board.init()) die("BOARD_INIT");
  lcd=board.getLCD(); touch=board.getTouch();
  if(!lcd||!touch) die("LCD_OR_TOUCH_MISSING");
  if(lcd->getFrameWidth()!=W||lcd->getFrameHeight()!=H) die("WRONG_RESOLUTION");
  if(!lcd->configFrameBufferNumber(1)) die("FRAMEBUFFER_CONFIG");
  if(!static_cast<BusRGB*>(lcd->getBus())->configRGB_BounceBufferSize(W*10)) die("BOUNCE_CONFIG");
  if(!board.begin()) die("BOARD_BEGIN");
  if(lcd->getFrameColorBits()!=16) die("FRAMEBUFFER_NOT_RGB565");
  pattern();
  wifiTraceQueue=xQueueCreateStatic(WIFI_TRACE_CAPACITY,sizeof(WifiTraceEvent),wifiTraceStorage,&wifiTraceControl);
  if(!wifiTraceQueue) die("WIFI_TRACE_QUEUE_ALLOC");
  WiFi.persistent(false);
  WiFi.onEvent([](WiFiEvent_t event, WiFiEventInfo_t info) {
    if(event==ARDUINO_EVENT_WIFI_SCAN_DONE) {
      if(scanListening.load()) { scanStatus=info.wifi_scan_done.status; scanDone=true; }
    } else if(event==ARDUINO_EVENT_WIFI_STA_DISCONNECTED) {
      const uint32_t eventMs=millis();
      portENTER_CRITICAL(&wifiReasonMux);
      lastWifiDisconnectMs=eventMs;
      lastWifiReason=int(info.wifi_sta_disconnected.reason);
      portEXIT_CRITICAL(&wifiReasonMux);
      ++drops;
      enqueueWifiEvent(WifiTraceKind::DISCONNECTED,int(info.wifi_sta_disconnected.reason));
    } else if(event==ARDUINO_EVENT_WIFI_STA_CONNECTED) {
      ++wifiAssociations;
      enqueueWifiEvent(WifiTraceKind::CONNECTED);
    } else if(event==ARDUINO_EVENT_WIFI_STA_GOT_IP) {
      ++wifiGotIpEvents;
      enqueueWifiEvent(WifiTraceKind::GOT_IP);
    } else if(event==ARDUINO_EVENT_WIFI_STA_LOST_IP) {
      enqueueWifiEvent(WifiTraceKind::LOST_IP);
    } else if(event==ARDUINO_EVENT_WIFI_STA_START) {
      enqueueWifiEvent(WifiTraceKind::START);
    } else if(event==ARDUINO_EVENT_WIFI_STA_STOP) {
      enqueueWifiEvent(WifiTraceKind::STOP);
    }
  });
  WiFi.mode(WIFI_STA); WiFi.setAutoReconnect(true);
  Serial.println("READY WIFI credentials over USB only; START begins observation; no hardware PASS implied");
}
void loop() {
  serialInput();
  drainWifiEvents();
  pollScan();
  const uint32_t now=millis(), count=drops.load();
  const bool connected=WiFi.status()==WL_CONNECTED;
  if(!connected || count!=lastDropCount) wifiSince=0;
  if(connected&&!wifiSince) wifiSince=now;
  lastDropCount=count;
  TouchPoint points[5]; const int n=touch->readPoints(points,5,0);
  if(n<0) ++touchErrors;
  for(int i=0;i<n;++i) {
    const int x=points[i].x, y=points[i].y;
    if(x<0||x>=W||y<0||y>=H) { ++touchErrors; continue; }
    for(int t=0;t<5;++t) if(abs(x-tx[t])<=24&&abs(y-ty[t])<=24) { targets|=1<<t; drawTarget(t); flushRows(ty[t]-26,53); }
    rect(x-9,y-1,19,3,0); rect(x-1,y-9,3,19,0);
    rect(x-7,y,15,1,0xffff); rect(x,y-7,1,15,0xffff);
    flushRows(max(0,y-9),19);
    Serial.printf("TOUCH boot=%08lx x=%d y=%d targets=%u\n",(unsigned long)bootId,x,y,targets);
  }
  if(now-lastDiag>=5000) {
    lastDiag=now;
    if(!checkRam()||!heap_caps_check_integrity_all(false)) ++memoryErrors;
    const uint32_t stable=wifiSince?now-wifiSince:0;
    const uint32_t elapsed=running?now-runSince:0;
    int reason;
    uint32_t disconnectMs;
    portENTER_CRITICAL(&wifiReasonMux);
    reason=lastWifiReason;
    disconnectMs=lastWifiDisconnectMs;
    portEXIT_CRITICAL(&wifiReasonMux);
    const int64_t reasonAge=reason<0 ? -1 : int64_t(uint32_t(millis()-disconnectMs));
    Serial.printf("WIFI_DIAG boot=%08lx status=%d last_reason=%d reason_age_ms=%lld disconnects=%lu associations=%lu got_ip_events=%lu\n",
      (unsigned long)bootId,int(WiFi.status()),reason,(long long)reasonAge,
      (unsigned long)drops.load(),(unsigned long)wifiAssociations.load(),(unsigned long)wifiGotIpEvents.load());
    Serial.printf("WIFI_TRACE boot=%08lx queued_dropped=%lu\n",
      (unsigned long)bootId,(unsigned long)wifiTraceDropped.load());
    Serial.printf("DIAG boot=%08lx uptime_ms=%lu run_ms=%lu wifi=%u wifi_ms=%lu drops=%lu heap=%lu min_heap=%lu largest=%u psram_free=%lu targets=%u touch_errors=%lu memory_errors=%lu\n",
      (unsigned long)bootId,(unsigned long)now,(unsigned long)elapsed,connected,(unsigned long)stable,
      (unsigned long)count,(unsigned long)ESP.getFreeHeap(),(unsigned long)ESP.getMinFreeHeap(),
      unsigned(heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)),
      (unsigned long)ESP.getFreePsram(),targets,(unsigned long)touchErrors,(unsigned long)memoryErrors);
    rect(0,0,W,30,0); char msg[65];
    snprintf(msg,sizeof(msg),"TOP 800 X 480  WIFI %s  SEC %lu  TOUCH %u",connected?"OK":"LOST",(unsigned long)(elapsed/1000),targets);
    label(8,8,msg,2); flushRows(0,30);
    if(running&&!readyPrinted&&elapsed>=600000&&stable>=600000&&targets==31&&!touchErrors&&!memoryErrors&&count==0) {
      Serial.println("WINDOW_READY requires human visual confirmation; NOT_HARDWARE_PASS"); readyPrinted=true;
    }
  }
  delay(30);
}
