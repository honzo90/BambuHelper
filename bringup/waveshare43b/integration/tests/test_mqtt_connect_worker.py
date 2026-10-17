"""Execute the real worker/handoff code with a stalled fake transport and ASan.
Hardware tests separately cover FreeRTOS/TLS and physical touch responsiveness.
"""
from pathlib import Path
import subprocess, tempfile, unittest
ROOT=Path(__file__).resolve().parents[4]

class ConnectWorker(unittest.TestCase):
 def test_stall_cancel_handoff_failure_and_config_snapshot(self):
  src=(ROOT/'src/bambu_mqtt.cpp').read_text()
  worker=src[src.index('struct ConnectJob {'):src.index('\n#endif\n\nstatic void reconnectConn')]
  stub=r'''
#include <atomic>
#include <thread>
#include <cassert>
#include <cstring>
#include <cstdio>
#include <chrono>
#include <cstdint>
#define BOARD_MQTT_ASYNC_CONNECT 1
#define BAMBU_MONITOR_ONLY 1
#define BAMBU_PORT 8883
#define BAMBU_USERNAME "bblp"
#define MAX_ACTIVE_PRINTERS 2
#define CONN_LOCAL 0
#define pdPASS 1
using Handler=void(*)();
void mqttCallback(){}
struct PrinterConfig {int mode=0;int region=0;char ip[16]{};char serial[20]{};char accessCode[12]{};char cloudUserId[32]{};};
struct Printer {PrinterConfig config;struct {bool connected=false;} state;} printers[2];
bool isCloudMode(int m){return m!=0;}const char* getBambuBroker(int){return "cloud";}
bool tokenOk=true;bool loadCloudToken(char*b,size_t){strcpy(b,"TOKEN");return tokenOk;}
uint32_t millis(){return uint32_t(std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now().time_since_epoch()).count());}
uint32_t esp_random(){return 42;}struct {uint64_t getEfuseMac(){return 42;}} ESP;
namespace ws43b_memory {enum class Stage {MqttConnect};struct Scope {Scope(Stage){}};}
std::atomic<bool> hold{false},entered{false};bool transportOk=true,allocateOk=true,taskOk=true,probeOk=true,subscribeOk=true;
std::string passwordUsed;std::thread task;
struct WiFiClient {bool connect(const char*,int,int){return probeOk;}void stop(){}};
struct WiFiClientSecure {void setHandshakeTimeout(int){}};
struct MqttRxClient {using Handler=::Handler;bool connecting=false;Handler h=nullptr;void setHandler(Handler x){h=x;}};
struct PubSubClient {Handler h=nullptr;const char* server=nullptr;
 bool connect(const char*,const char*,const char*pw){entered=true;while(hold)std::this_thread::sleep_for(std::chrono::milliseconds(1));passwordUsed=pw;return transportOk;}
 int state(){return transportOk?0:-4;}bool subscribe(const char*){return subscribeOk;}
 void setServer(const char*s,int){server=s;}void setCallback(Handler x){h=x;}
};
struct MqttDiag {uint32_t attempts=0,probes=0,connectDurMs=0,connectStackFree=0;bool tcpOk=false,connectPending=false;int lastRc=0;};
struct MqttConn {uint8_t slotIndex=0;WiFiClientSecure*tls=nullptr;MqttRxClient*io=nullptr;PubSubClient*mqtt=nullptr;MqttDiag diag;bool active=false,printerUnreachable=false;uint32_t consecutiveFails=0,lastReconnectAttempt=0;};
MqttConn conns[2];std::atomic<int> bundles{0};
bool ensureClients(MqttConn&c,const PrinterConfig&,Handler h){assert(h==nullptr);if(!allocateOk)return false;c.tls=new WiFiClientSecure;c.io=new MqttRxClient;c.mqtt=new PubSubClient;++bundles;return true;}
void releaseClients(MqttConn&c){if(c.tls)--bundles;delete c.mqtt;delete c.io;delete c.tls;c.mqtt=nullptr;c.io=nullptr;c.tls=nullptr;}
int sessions=0;void acceptMqttSession(MqttConn&c){++sessions;printers[c.slotIndex].state.connected=true;}
void vTaskDelete(void*){}unsigned uxTaskGetStackHighWaterMark(void*){return 4096;}
int xTaskCreatePinnedToCore(void(*fn)(void*),const char*,int,void*,int,void*,int){if(!taskOk)return 0;task=std::thread([fn]{fn(nullptr);});return 1;}
'''
  case=r'''
void waitWorker(){for(int i=0;i<1000&&!entered;++i)std::this_thread::sleep_for(std::chrono::milliseconds(1));assert(entered);}
int main(){
 auto&c=conns[0];c.active=true;auto&cfg=printers[0].config;strcpy(cfg.ip,"10.0.0.1");strcpy(cfg.accessCode,"ORIGINAL");
 hold=true;startConnectJob(c,cfg);waitWorker();assert(c.diag.connectPending&&connectJobBusy&&c.mqtt==nullptr);
 // Main/UI continues polling a stalled worker, and config changes cannot race
 // its immutable credential snapshot. Cancellation does not delete its clients.
 int uiTicks=0;for(int i=0;i<1000;++i){finishConnectJob();++uiTicks;}assert(uiTicks==1000&&sessions==0);
 strcpy(cfg.accessCode,"NEW");++connectGeneration[0];hold=false;task.join();finishConnectJob();
 assert(passwordUsed=="ORIGINAL"&&sessions==0&&bundles==0&&!connectJobBusy&&c.mqtt==nullptr);
 startConnectJob(c,cfg);task.join();assert(sessions==0);finishConnectJob();
 assert(sessions==1&&bundles==1&&!c.diag.connectPending&&c.mqtt&&c.mqtt->h==mqttCallback&&c.io->h==mqttCallback);
 assert(c.mqtt->server==cfg.ip&&passwordUsed=="NEW");releaseClients(c);
 transportOk=false;startConnectJob(c,cfg);task.join();finishConnectJob();assert(c.diag.lastRc==-4&&bundles==0&&!c.diag.connectPending&&sessions==1);
 transportOk=true;subscribeOk=false;startConnectJob(c,cfg);task.join();finishConnectJob();assert(c.diag.lastRc==-2&&bundles==0&&sessions==1);subscribeOk=true;
 allocateOk=false;startConnectJob(c,cfg);task.join();finishConnectJob();assert(bundles==0&&!connectJobBusy);allocateOk=true;
 taskOk=false;startConnectJob(c,cfg);assert(!connectJobBusy&&!c.diag.connectPending&&bundles==0);taskOk=true;
 cfg.mode=1;tokenOk=false;startConnectJob(c,cfg);assert(!connectJobBusy&&bundles==0);tokenOk=true;
 startConnectJob(c,cfg);task.join();c.active=false;finishConnectJob();assert(bundles==0&&sessions==1);
}
'''
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);(p/'test.cpp').write_text(stub+worker+case)
   r=subprocess.run(['clang++','-std=c++17','-pthread','-fsanitize=address,undefined',str(p/'test.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
   r=subprocess.run([str(p/'test')],capture_output=True,text=True,timeout=15)
   self.assertEqual(r.returncode,0,r.stderr)
