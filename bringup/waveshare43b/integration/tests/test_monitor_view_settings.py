"""Compile the actual view handlers against fake storage; no device or network."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[4]
JSON_INCLUDE = REPO / 'bringup/waveshare43b/integration/vendor/ArduinoJson-7.4.3/src'


class MonitorViewSettingsTests(unittest.TestCase):
    def test_real_handlers_validate_before_storage_and_report_failures(self):
        compiler = shutil.which('clang++') or shutil.which('c++')
        if not compiler:
            self.skipTest('Native C++ compiler required')
        source = (REPO / 'src/web_server.cpp').read_text()
        begin = source.index('static void handleMonitorDisplayGet() {')
        end = source.index('\n#endif', begin)
        # No MQTT, restart or general saveSettings declarations are provided:
        # these real handler bodies can only use the view-storage contract.
        harness = r'''
#include <cassert>
#include <cstdint>
#include <string>
#include <utility>
#include <vector>
#include <ArduinoJson.h>
using String=std::string;
static uint8_t activeTheme=0;
static bool storageOk=true;
static int writes=0;
struct {bool fanMatchPrinter=true;} dispSettings;
uint8_t ws43bViewTheme() {return activeTheme;}
bool saveWs43bViewSettings(uint8_t theme,bool fan) {
 ++writes;if(!storageOk)return false;
 activeTheme=theme;dispSettings.fanMatchPrinter=fan;return true;
}
struct ServerStub {
 std::vector<std::pair<String,String>> fields;
 int code=0;String type,body,cache;
 int args(){return fields.size();}
 bool hasArg(const char* key){for(const auto& f:fields)if(f.first==key)return true;return false;}
 String arg(const char* key){for(const auto& f:fields)if(f.first==key)return f.second;return "";}
 void sendHeader(const char* key,const char* value){assert(String(key)=="Cache-Control");cache=value;}
 void send(int status,const char* contentType,const String& content){code=status;type=contentType;body=content;}
} server;
''' + source[begin:end] + r'''
JsonDocument reply(int expectedCode) {
 assert(server.code==expectedCode && server.type=="application/json" && server.cache=="no-store");
 JsonDocument doc;assert(!deserializeJson(doc,server.body));return doc;
}
void get() {
 const int before=writes;server={};handleMonitorDisplayGet();
 auto doc=reply(200);assert(writes==before);
 assert(doc.as<JsonObject>().size()==2);
 assert(doc["theme"].is<uint8_t>() && doc["theme"]==activeTheme);
 assert(doc["fan_match_printer"].is<bool>() && doc["fan_match_printer"]==dispSettings.fanMatchPrinter);
}
int main() {
 get();
 for(const auto& theme:{"0","1","2"})for(const auto& fan:{"0","1"}){
  server={};server.fields={{"theme",theme},{"fan_match_printer",fan}};
  const int before=writes;handleMonitorDisplaySave();auto doc=reply(200);
  assert(doc["status"]=="ok" && writes==before+1);
  assert(activeTheme==theme[0]-'0' && dispSettings.fanMatchPrinter==(String(fan)=="1"));get();
 }
 const auto oldTheme=activeTheme;const bool oldFan=dispSettings.fanMatchPrinter;
 using Fields=decltype(server.fields);
 const std::vector<Fields> invalid={
  {},{{"theme","1"}},{{"fan_match_printer","1"}},
  {{"theme",""},{"fan_match_printer","1"}},
  {{"theme","-1"},{"fan_match_printer","1"}},
  {{"theme","3"},{"fan_match_printer","1"}},
  {{"theme","01"},{"fan_match_printer","1"}},
  {{"theme"," 1"},{"fan_match_printer","1"}},
  {{"theme","1junk"},{"fan_match_printer","1"}},
  {{"theme","1"},{"fan_match_printer",""}},
  {{"theme","1"},{"fan_match_printer","2"}},
  {{"theme","1"},{"fan_match_printer","true"}},
  {{"theme","1"},{"fan_match_printer","00"}},
  {{"theme","1"},{"fan_match_printer","1 "}},
  {{"theme","1"},{"theme","2"}},
  {{"theme","1"},{"fan_match_printer","0"},{"fan_match_printer","1"}},
  {{"theme","1"},{"fan_match_printer","0"},{"token","SYNTHETIC_SECRET"}}
 };
 for(const auto& fields:invalid){
  server={};server.fields=fields;const int before=writes;
  handleMonitorDisplaySave();auto doc=reply(400);
  assert(doc["status"]=="error" && writes==before);
  assert(activeTheme==oldTheme && dispSettings.fanMatchPrinter==oldFan);
  assert(server.body.find("SYNTHETIC_SECRET")==String::npos);
 }
 storageOk=false;server={};server.fields={{"theme","0"},{"fan_match_printer","0"}};
 const int before=writes;handleMonitorDisplaySave();auto doc=reply(500);
 assert(doc["status"]=="error" && writes==before+1);
 assert(activeTheme==oldTheme && dispSettings.fanMatchPrinter==oldFan);get();
}
'''
        with tempfile.TemporaryDirectory(prefix='bambu-view-settings-') as folder:
            tmp = Path(folder)
            cpp, binary = tmp / 'view.cpp', tmp / 'view'
            cpp.write_text(harness)
            result = subprocess.run([compiler, '-std=c++17', '-I', str(JSON_INCLUDE),
                                     str(cpp), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
