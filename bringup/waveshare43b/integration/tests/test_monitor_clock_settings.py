"""Real clock handlers and NVS logic against synthetic storage, without a device."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[4]
JSON_INCLUDE = REPO / 'bringup/waveshare43b/integration/vendor/ArduinoJson-7.4.3/src'


class MonitorClockSettingsTests(unittest.TestCase):
    def test_atomic_storage_and_strict_handlers(self):
        compiler = shutil.which('clang++') or shutil.which('c++')
        if not compiler:
            self.skipTest('Native C++ compiler required')
        storage = (REPO / 'src/ws43b_clock_settings.cpp').read_text()
        storage = storage[storage.index('static Ws43bClockSettings'):storage.rindex('#endif')]
        source = (REPO / 'src/web_server.cpp').read_text()
        begin = source.index('static void handleMonitorClockGet() {')
        handlers = source[begin:source.index('\n#endif', begin)]
        harness = r'''
#include <cassert>
#include <cstring>
#include <string>
#include <utility>
#include <vector>
#include <ArduinoJson.h>
#include "ws43b_clock_settings.h"
using String=std::string;
struct {bool use24h=false;} netSettings;
constexpr const char* NVS_NAMESPACE="synthetic";
static bool openOk=true, writeOk=true;
static uint16_t persisted=0;
static unsigned writes=0;
struct Preferences {
 bool begin(const char* ns, bool){assert(!strcmp(ns,NVS_NAMESPACE));return openOk;}
 uint16_t getUShort(const char* key, uint16_t){assert(!strcmp(key,"w43_clock"));return persisted;}
 size_t putUShort(const char* key, uint16_t value){
  assert(!strcmp(key,"w43_clock"));++writes;if(!writeOk)return 0;persisted=value;return 2;
 }
 void end(){}
};
struct ServerStub {
 std::vector<std::pair<String,String>> fields;
 int code=0;String body,cache;
 int args(){return fields.size();}
 bool hasArg(const char* key){for(const auto& f:fields)if(f.first==key)return true;return false;}
 String arg(const char* key){for(const auto& f:fields)if(f.first==key)return f.second;return "";}
 void sendHeader(const char* key,const char* value){assert(String(key)=="Cache-Control");cache=value;}
 void send(int status,const char* type,const String& content){assert(String(type)=="application/json");code=status;body=content;}
} server;
''' + storage + handlers + r'''
void get() {
 const auto before=writes;server={};handleMonitorClockGet();
 assert(server.code==200 && server.cache=="no-store" && writes==before);
 JsonDocument doc;assert(!deserializeJson(doc,server.body));assert(doc.as<JsonObject>().size()==3);
 assert(doc["idle_minutes"].is<unsigned>() && doc["idle_minutes"]==ws43bClockSettings().idleMinutes);
 assert(doc["screen_off"].is<unsigned>() && doc["screen_off"]==(ws43bClockSettings().screenOff?1:0));
 assert(doc["use24h"].is<unsigned>() && doc["use24h"]==(netSettings.use24h?1:0));
}
int main() {
 loadWs43bClockSettings();assert(!ws43bClockSettings().use24h && !ws43bClockSettings().idleMinutes && writes==0);
 assert(saveWs43bClockSettings(0,false,false) && writes==0 && ws43bClockSettings().revision==0);
 assert(!saveWs43bClockSettings(2,false,true) && writes==0);
 for(auto value:{0x0102,0x0205,0x0185,0xFFFF}) {
  persisted=value;loadWs43bClockSettings();assert(!ws43bClockSettings().idleMinutes && writes==0);
 }
 persisted=0;loadWs43bClockSettings();
 for(const auto& idle:{"0","1","5","15","30"})for(const auto& off:{"0","1"})for(const auto& format:{"0","1"}){
  server={};server.fields={{"idle_minutes",idle},{"screen_off",off},{"use24h",format}};
  const auto before=writes, revision=ws43bClockSettings().revision;
  handleMonitorClockSave();assert(server.code==200 && server.cache=="no-store");
  assert(ws43bClockSettings().idleMinutes==std::stoi(idle));
  assert(ws43bClockSettings().screenOff==(String(off)=="1") && netSettings.use24h==(String(format)=="1"));
  assert(ws43bClockSettings().revision==revision+writes-before);get();
 }
 const auto saved=ws43bClockSettings();const auto before=writes;get();
 using Fields=decltype(server.fields);
 for(const auto& fields:std::vector<Fields>{
  {},{{"idle_minutes","1"},{"screen_off","0"}},
  {{"idle_minutes","01"},{"screen_off","0"},{"use24h","1"}},
  {{"idle_minutes","-1"},{"screen_off","0"},{"use24h","1"}},
  {{"idle_minutes","60"},{"screen_off","0"},{"use24h","1"}},
  {{"idle_minutes","1 "},{"screen_off","0"},{"use24h","1"}},
  {{"idle_minutes","1x"},{"screen_off","0"},{"use24h","1"}},
  {{"idle_minutes","1"},{"screen_off","true"},{"use24h","1"}},
  {{"idle_minutes","1"},{"screen_off","0"},{"use24h","01"}},
  {{"idle_minutes","1"},{"screen_off","0"},{"screen_off","1"}},
  {{"idle_minutes","1"},{"screen_off","0"},{"use24h","1"},{"token","SYNTHETIC"}}
 }) {
  server={};server.fields=fields;handleMonitorClockSave();
  assert(server.code==400 && writes==before && ws43bClockSettings().revision==saved.revision);
  assert(server.body.find("SYNTHETIC")==String::npos);
 }
 openOk=false;assert(!saveWs43bClockSettings(1,false,false) && writes==before);
 openOk=true;writeOk=false;server={};server.fields={{"idle_minutes","1"},{"screen_off","0"},{"use24h","0"}};
 handleMonitorClockSave();assert(server.code==500 && writes==before+1);
 assert(ws43bClockSettings().revision==saved.revision && ws43bClockSettings().idleMinutes==saved.idleMinutes);
 assert(ws43bClockSettings().screenOff==saved.screenOff && netSettings.use24h==saved.use24h);
 netSettings.use24h=false;loadWs43bClockSettings();
 assert(ws43bClockSettings().idleMinutes==saved.idleMinutes && ws43bClockSettings().screenOff==saved.screenOff);
 assert(netSettings.use24h==saved.use24h && ws43bClockSettings().revision==0);
}
'''
        with tempfile.TemporaryDirectory(prefix='bambu-clock-settings-') as folder:
            cpp, binary = Path(folder) / 'test.cpp', Path(folder) / 'test'
            cpp.write_text(harness)
            result = subprocess.run([compiler, '-std=c++17', '-DBOARD_IS_WS43B',
                                     '-I', str(REPO / 'src'), '-I', str(JSON_INCLUDE),
                                     str(cpp), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
