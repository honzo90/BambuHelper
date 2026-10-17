"""Exercise the shared display mode through real storage, HTTP and backup code."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
JSON_INCLUDE = ROOT / 'bringup/waveshare43b/integration/vendor/ArduinoJson-7.4.3/src'


class DisplayModeSettings(unittest.TestCase):
    def compile_run(self, code):
        with tempfile.TemporaryDirectory(prefix='bambu-display-mode-') as directory:
            p = Path(directory)
            (p / 'test.cpp').write_text(code)
            result = subprocess.run(['clang++', '-std=c++17', '-DBOARD_IS_WS43B',
                                     '-fsanitize=address,undefined', '-Wno-deprecated-declarations',
                                     '-I', str(ROOT / 'src'), '-I', str(JSON_INCLUDE),
                                     str(p / 'test.cpp'), '-o', str(p / 'test')],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(p / 'test')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_atomic_record_and_strict_http(self):
        storage = (ROOT / 'src/ws43b_display_mode.cpp').read_text()
        storage = storage[storage.index('static bool advancedDisplay'):storage.rindex('#endif')]
        source = (ROOT / 'src/web_server.cpp').read_text()
        start = source.index('static void handleMonitorDisplayModeGet() {')
        handlers = source[start:source.index('\n#endif', start)]
        code = r'''
#include <cassert>
#include <cstring>
#include <string>
#include <map>
#include <vector>
#include <utility>
#include <ArduinoJson.h>
#include "ws43b_display_mode.h"
using String=std::string;
constexpr const char *NVS_NAMESPACE="synthetic";
bool openOk=true,writeOk=true;unsigned writes=0;
std::map<std::string,uint16_t> store={{"w43_clock",0x017e},{"w43_view",0x0106},{"pong",1}};
struct Preferences {
 bool begin(const char *ns,bool){assert(!strcmp(ns,NVS_NAMESPACE));return openOk;}
 uint16_t getUShort(const char *key,uint16_t fallback){assert(!strcmp(key,"w43_mode"));auto p=store.find(key);return p==store.end()?fallback:p->second;}
 size_t putUShort(const char *key,uint16_t value){assert(!strcmp(key,"w43_mode"));++writes;if(!writeOk)return 0;store[key]=value;return sizeof(value);}
 void end(){}
};
struct Server {
 std::vector<std::pair<String,String>> fields;int code=0;String body,cache;
 unsigned args(){return fields.size();}
 bool hasArg(const char *key){for(const auto&f:fields)if(f.first==key)return true;return false;}
 String arg(const char *key){for(const auto&f:fields)if(f.first==key)return f.second;return "";}
 void sendHeader(const char *key,const char *value){assert(String(key)=="Cache-Control");cache=value;}
 void send(int status,const char *type,const String&value){assert(String(type)=="application/json");code=status;body=value;}
}server;
''' + storage + handlers + r'''
void get(const char *expected){
 const auto before=writes;server={};handleMonitorDisplayModeGet();
 assert(server.code==200&&server.cache=="no-store"&&writes==before);
 JsonDocument doc;assert(!deserializeJson(doc,server.body));assert(doc.as<JsonObject>().size()==1);
 assert(doc["mode"].is<const char*>()&&!strcmp(doc["mode"],expected));
}
void post(const char *value){server={};server.fields={{"mode",value}};handleMonitorDisplayModeSave();}
int main(){
 const auto unrelated=store;
 loadWs43bDisplayMode();assert(!ws43bAdvancedDisplay()&&!ws43bDisplayModeRevision()&&!writes);get("simple");
 assert(saveWs43bDisplayMode(false)&&!writes);
 for(auto value:{0,1,0x0102,0x0201,0xffff}){
  store["w43_mode"]=value;loadWs43bDisplayMode();assert(!ws43bAdvancedDisplay()&&!writes);
 }
 for(auto value:{0x0100,0x0101}){
  store["w43_mode"]=value;loadWs43bDisplayMode();assert(ws43bAdvancedDisplay()==bool(value&1));assert(!writes&&!ws43bDisplayModeRevision());
 }
 post("simple");assert(server.code==200&&writes==1&&!ws43bAdvancedDisplay()&&ws43bDisplayModeRevision()==1);get("simple");
 post("advanced");assert(server.code==200&&writes==2&&ws43bAdvancedDisplay()&&ws43bDisplayModeRevision()==2);get("advanced");
 post("advanced");assert(server.code==200&&writes==2&&ws43bDisplayModeRevision()==2);
 using Fields=decltype(server.fields);
 for(const auto&fields:std::vector<Fields>{
  {},{{"mode",""}},{{"mode","0"}},{{"mode","1"}},{{"mode","true"}},{{"mode","Advanced"}},
  {{"mode","advanced "}},{{"mode","simple\n"}},{{"mode","unknown"}},
  {{"mode","simple"},{"mode","advanced"}},{{"mode","simple"},{"token","SYNTHETIC"}},{{"theme","simple"}}
 }){
  server={};server.fields=fields;handleMonitorDisplayModeSave();
  assert(server.code==400&&writes==2&&ws43bAdvancedDisplay()&&ws43bDisplayModeRevision()==2);
  assert(server.body.find("SYNTHETIC")==String::npos);
 }
 openOk=false;post("simple");assert(server.code==500&&writes==2&&ws43bAdvancedDisplay());
 openOk=true;writeOk=false;post("simple");assert(server.code==500&&writes==3&&ws43bAdvancedDisplay()&&ws43bDisplayModeRevision()==2);
 writeOk=true;loadWs43bDisplayMode();assert(ws43bAdvancedDisplay()&&!ws43bDisplayModeRevision());
 post("simple");assert(server.code==200&&writes==4&&!ws43bAdvancedDisplay());loadWs43bDisplayMode();assert(!ws43bAdvancedDisplay());
 for(const auto&pair:unrelated)assert(store.at(pair.first)==pair.second);
}
'''
        self.compile_run(code)

    def test_backup_optional_validation_and_roundtrip(self):
        source = (ROOT / 'src/web_server.cpp').read_text()
        export = next(line for line in source.splitlines() if 'native["display_mode"] =' in line)
        start = source.index('    // Optional for older backups: omission preserves the current presentation.')
        imported = source[start:source.index('    if (!native["language"].isNull())', start)]
        code = r'''
#include <cassert>
#include <cstring>
#include <ArduinoJson.h>
bool advanced=false;
bool ws43bAdvancedDisplay(){return advanced;}
struct Server{int code=0;void send(int status,const char*,const char*){code=status;}}server;
void exportMode(JsonObject native){
''' + export + r'''
}
void importMode(JsonObject native,bool &importedAdvancedDisplay){
''' + imported + r'''
}
int main(){
 for(bool initial:{false,true}){
  advanced=initial;JsonDocument doc;auto native=doc.to<JsonObject>();exportMode(native);
  assert(native["display_mode"].is<const char*>());
  bool importedAdvancedDisplay=!initial;importMode(native,importedAdvancedDisplay);
  assert(!server.code&&importedAdvancedDisplay==initial);
  doc.clear();native=doc.to<JsonObject>();importedAdvancedDisplay=initial;importMode(native,importedAdvancedDisplay);
  assert(!server.code&&importedAdvancedDisplay==initial); // old backup omits the setting
  for(const char *bad:{"null","1","true","\"Advanced\"","\"\"","[]","{}","\"advanced \""}){
   JsonDocument invalid;assert(!deserializeJson(invalid,bad));native["display_mode"].set(invalid.as<JsonVariant>());
   server.code=0;importedAdvancedDisplay=initial;importMode(native,importedAdvancedDisplay);
   assert(server.code==400&&importedAdvancedDisplay==initial);
  }
  server.code=0;
 }
}
'''
        self.compile_run(code)


if __name__ == '__main__':
    unittest.main()
