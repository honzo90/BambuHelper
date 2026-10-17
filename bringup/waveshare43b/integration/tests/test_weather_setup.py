from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[4]
class SetupTests(unittest.TestCase):
 def test_persist_skip_finish_and_failure(self):
  source=(ROOT/'src/ws43b_weather.cpp').read_text()
  funcs=source[source.index('bool ws43bSetupDone()'):source.rfind('#endif')]
  code=r'''#include <cassert>
#include <cstring>
#include <map>
#include <string>
const char *NVS_NAMESPACE="test";
struct {bool nightModeEnabled=false;unsigned nightBrightness=30;} dpSettings;
std::map<std::string,unsigned> storage;bool writable=true;
struct Preferences{
 bool begin(const char*,bool){return true;}void end(){}
 bool getBool(const char*k,bool d){return storage.count(k)?storage[k]:d;}
 unsigned putBool(const char*k,bool v){if(!writable)return 0;storage[k]=v;return 1;}
 unsigned putUChar(const char*k,unsigned v){if(!writable)return 0;storage[k]=v;return 1;}
};
''' + funcs + r'''
int main(){
 assert(!ws43bSetupDone());assert(finishWs43bSetup(true,false));assert(ws43bSetupDone());
 assert(storage.size()==1&&!dpSettings.nightModeEnabled&&dpSettings.nightBrightness==30);
 storage.clear();writable=false;assert(!finishWs43bSetup(false,true));assert(!ws43bSetupDone());assert(!dpSettings.nightModeEnabled);
 writable=true;assert(finishWs43bSetup(false,true));assert(ws43bSetupDone()&&dpSettings.nightModeEnabled&&dpSettings.nightBrightness==0);
 assert(storage["dp_night"]==1&&storage["dp_nbright"]==0);
 assert(finishWs43bSetup(false,false));assert(dpSettings.nightBrightness==100&&storage["dp_nbright"]==100);
}'''
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);(p/'test.cpp').write_text(code)
   subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror',str(p/'test.cpp'),'-o',str(p/'test')],check=True)
   subprocess.run([str(p/'test')],check=True)
