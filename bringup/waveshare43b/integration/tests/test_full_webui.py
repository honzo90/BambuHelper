"""Offline full portal tests. No device, network, credentials or real commands."""
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]

def function(source, signature):
    start = source.index(signature)
    brace = source.index('{', start)
    end, depth = brace + 1, 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]

class FullWebUI(unittest.TestCase):
    def test_partition_migration_preserves_existing_regions(self):
        def rows(path):
            return {v[0]: v[1:5] for line in path.read_text().splitlines()
                    if line and not line.startswith('#') and (v := line.split(','))}
        old = rows(ROOT/'bringup/waveshare43b/smoke/partitions.csv')
        new = rows(ROOT/'bringup/waveshare43b/integration/partitions.csv')
        for name in old: self.assertEqual(old[name], new[name])
        self.assertEqual(new['app1'], ['app','ota_1','0x310000','0x300000'])
        intervals = sorted((int(v[2],0),int(v[2],0)+int(v[3],0)) for v in new.values())
        self.assertTrue(all(a[1] <= b[0] for a,b in zip(intervals,intervals[1:])))
        self.assertLessEqual(intervals[-1][1],16*1024*1024)

    def test_browser_capabilities_are_board_scoped(self):
        js = (ROOT/'web/app.js').read_text()
        setup = function(js,'function setupWs43bPortal()')
        harness = r'''
const assert=require('assert');
let fields={}, buttons=[], card=null;
function setupWs43bDisplaySettings(){card={integrated:true};}
function setupWs43bWeather(){}
const document={
 getElementById(id){return fields[id] ||= {value:'test',checked:true,style:{},closest(){return {style:{}};}};},
 querySelector(){return {after(c){card=c;}};},
 createElement(){return {};},
 querySelectorAll(){return buttons;}
};
let DEV={board:'esp32s3'};
''' + setup + '\n' + function(js,'function toggleAfterPrint()') + r'''
setupWs43bPortal(); assert.equal(card,null);assert.deepEqual(fields,{});
DEV.board='ws_lcd_43b';
buttons=[{getAttribute(){return 'ledTestEffect()';}},{getAttribute(){return 'saveLightConfig()';}}];
setupWs43bPortal();assert(card.integrated);
assert(fields.btntype.disabled && fields.btntype.value==='3');
assert(fields.rotation.disabled && fields.rotation.value==='0');
assert(!fields.rotsplit.checked && fields.rotsplit.disabled);
assert(buttons[0].disabled && !buttons[1].disabled);
assert(!fields.nighten && !fields.pong); // Supported native scheduled off and pong remain usable.
document.getElementById('afterfin').value='off';toggleAfterPrint();assert(!fields.pong.disabled);
DEV.board='esp32s3';toggleAfterPrint();assert(fields.pong.disabled);
'''
        subprocess.run(['node','-e',harness],check=True,capture_output=True)

    def test_custom_palette_survives_loading_legacy_theme(self):
        source=(ROOT/'src/settings.cpp').read_text()
        start=source.index('static uint8_t ws43bTheme')
        helpers=source[start:source.index('\n#endif\n\n// ---',start)]
        start=source.index('  uint16_t view = prefs.getUShort("w43_view"')
        load=source[start:source.index('  prefs.end();',start)]
        harness=r'''
#include <cassert>
#include <cstdint>
#include <cstddef>
struct {uint16_t bgColor=0,trackColor=0,progressBarColor=0;bool fanMatchPrinter=true;}dispSettings;
const char*NVS_NAMESPACE="test";
static bool custom=false;static uint16_t persisted=0x0105;static int saves=0;
struct Preferences {
 bool begin(const char*,bool){return true;} void end(){}
 size_t putUShort(const char*,uint16_t v){persisted=v;return 2;}
 uint16_t getUShort(const char*,uint16_t){return persisted;}
 bool getBool(const char*,bool){return custom;}
}prefs;
void saveSettings(){custom=true;++saves;}
void sanitizeWs43bHardwareSettings(){}
''' + helpers + '\nvoid load(){\n#if defined(BOARD_IS_WS43B)\n' + load + r'''
}
int main(){
 load();assert(ws43bViewTheme()==1&&dispSettings.bgColor==0x0084);
 custom=true;dispSettings.bgColor=0x1234;dispSettings.trackColor=0x5678;
 load();assert(dispSettings.bgColor==0x1234&&dispSettings.trackColor==0x5678);
 assert(saveWs43bViewSettings(2,false)&&saves==1);
 assert(dispSettings.progressBarColor==0xF5CB&&!dispSettings.fanMatchPrinter);
 load();assert(ws43bViewTheme()==2&&dispSettings.progressBarColor==0xF5CB);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'test.cpp';p.write_text(harness);exe=Path(tmp)/'test'
            subprocess.run(['clang++','-std=c++17','-DBOARD_IS_WS43B=1','-DWS43B_FULL_WEBUI=1',str(p),'-o',str(exe)],check=True,capture_output=True)
            subprocess.run([str(exe)],check=True,capture_output=True)

    def test_upload_rejects_wrong_board_and_chip_and_handles_abort(self):
        source=(ROOT/'src/web_server.cpp').read_text()
        handler=function(source,'static void handleOtaUpload()')
        harness=r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <string>
struct String: std::string {
 using std::string::string;
 String(const std::string&s):std::string(s){}
 bool startsWith(const char*s)const{return rfind(s,0)==0;}
 bool endsWith(const char*s)const{return size()>=strlen(s)&&compare(size()-strlen(s),strlen(s),s)==0;}
};
constexpr int UPLOAD_FILE_START=0,UPLOAD_FILE_WRITE=1,UPLOAD_FILE_END=2,UPLOAD_FILE_ABORTED=3,UPDATE_ERROR_SPACE=9;
struct HTTPUpload {int status=0;String filename;size_t currentSize=0,totalSize=0;uint8_t buf[64]{};} uploadData;
struct Server {HTTPUpload& upload(){return uploadData;}bool hasHeader(const char*){return false;}String header(const char*){return "";}}server;
struct {template<class...T>void printf(T...args){} void println(const char*){}}Serial;
struct {int begins=0,writes=0,aborts=0,ends=0;bool begin(size_t){++begins;return true;}void abort(){++aborts;}size_t write(uint8_t*,size_t n){++writes;return n;}bool end(bool){++ends;return true;}String errorString(){return "error";}int getError(){return 0;}void setMD5(const char*){}}Update;
struct esp_partition_t {size_t size=0x300000;}partition, running;
bool singleSlot=false;
const esp_partition_t* esp_ota_get_next_update_partition(void*){return singleSlot ? &running : &partition;}
const esp_partition_t* esp_ota_get_running_partition(){return &running;}
namespace ws43b { bool displayAllowed=true; bool beginOtaDisplay(){return displayAllowed;} }
int disconnects=0;void disconnectBambuMqtt(){++disconnects;}
bool isUnderPartitioned(){return false;}const char* REPARTITION_HINT="";
String otaError;bool otaInProgress=false,otaFirstChunk=false,otaMqttReinitPending=false;
''' + handler + r'''
void start(const char*name){uploadData={};uploadData.filename=name;handleOtaUpload();}
void data(int chip,size_t size){uploadData.status=UPLOAD_FILE_WRITE;uploadData.currentSize=size;uploadData.buf[0]=0xE9;uploadData.buf[12]=chip;handleOtaUpload();}
int main(){
 start("BambuHelper-ws_lcd_43-ota.bin");assert(!otaError.empty()&&!otaInProgress&&Update.begins==0&&disconnects==0);
 data(9,24);assert(Update.writes==0);
 ws43b::displayAllowed=false;start("BambuHelper-ws_lcd_43b-v1-ota.bin");assert(!otaInProgress&&Update.begins==0&&disconnects==0);ws43b::displayAllowed=true;
 singleSlot=true;start("BambuHelper-ws_lcd_43b-v1-ota.bin");assert(!otaInProgress&&Update.begins==0);singleSlot=false;
 start("BambuHelper-ws_lcd_43b-v1-ota.bin");assert(otaInProgress&&Update.begins==1);
 data(0,24);assert(!otaInProgress&&Update.aborts==1&&Update.writes==0);
 start("BambuHelper-ws_lcd_43b-v1-ota.bin");data(9,13);assert(!otaInProgress&&Update.writes==0);
 start("BambuHelper-ws_lcd_43b-v1-ota.bin");data(9,24);assert(otaInProgress&&Update.writes==1);
 uploadData.status=UPLOAD_FILE_END;handleOtaUpload();assert(!otaInProgress&&Update.ends==1&&otaError.empty());
 start("BambuHelper-ws_lcd_43b-v1-ota.bin");uploadData.status=UPLOAD_FILE_ABORTED;handleOtaUpload();assert(!otaInProgress&&otaMqttReinitPending);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'test.cpp';p.write_text(harness);exe=Path(tmp)/'test'
            subprocess.run(['clang++','-std=c++17','-DBOARD_IS_WS43B=1','-fsanitize=address,undefined',str(p),'-o',str(exe)],check=True,capture_output=True)
            subprocess.run([str(exe)],check=True,capture_output=True)

if __name__=='__main__':unittest.main()
