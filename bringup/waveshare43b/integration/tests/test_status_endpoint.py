"""Actual monitor handleStatus compiled with pinned ArduinoJson and fake hardware.

No server or sockets are opened. Stubs provide only time, connection flags,
heap/reset/render counters and capture of the HTTP response.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[4]
JSON_INCLUDE = REPO / 'bringup/waveshare43b/integration/vendor/ArduinoJson-7.4.3/src'


class StatusEndpointTests(unittest.TestCase):
    def test_actual_status_json_connection_freshness_and_privacy(self):
        compiler = shutil.which('clang++') or shutil.which('c++')
        if not compiler:
            self.skipTest('Native C++ compiler required')
        self.assertTrue((JSON_INCLUDE / 'ArduinoJson.h').is_file(), 'Pinned ArduinoJson 7.4.3 required')
        source = (REPO / 'src/web_server.cpp').read_text()
        begin = source.index('static void handleStatus() {')
        end = source.index('// Clean reboot', begin)
        handler = source[begin:end]
        harness = r'''
#include <cassert>
#include <cstring>
#include <string>
#include <ArduinoJson.h>
#include "bambu_state.h"
#include "bambu_mqtt.h"
#include "ws43b_hardware.h"
// HMS rendering belongs to the old response below the monitor's return.
// Disable only that unrelated branch; compile the whole real handler otherwise.
#undef HAS_HMS_UI
#define HAS_HMS_UI 0
PrinterSlot printers[MAX_PRINTERS]{};
RotationState rotState{};
uint8_t activePrinterIndex=0;
static bool wifi=true,ap=false,configured=true;
static uint32_t nowMs=100000;
static int legacyNetworkQueries=0;
static MqttDiag diag{};
static ws43b::RenderDiagnostics renderDiag{};
static uint32_t bouncePixels=0;
static uint32_t cacheLineBytes=0;
namespace ws43b {
RenderDiagnostics renderDiagnostics() {return renderDiag;}
uint32_t bounceBufferPixels() {return bouncePixels;}
uint32_t requestedPclkHz() {return 14000000;}
uint32_t dcacheLineBytes() {return cacheLineBytes;}
}
uint32_t millis() {return nowMs;}
uint32_t uxTaskGetStackHighWaterMark(void*) {return 16384;}
bool isWiFiConnected() {return wifi;}
bool isAPMode() {return ap;}
bool isPrinterConfigured(uint8_t slot) {assert(slot==0);return configured;}
const MqttDiag& getMqttDiag(uint8_t slot) {assert(slot==0);return diag;}
int esp_reset_reason() {return 11;}
struct EspStub {
 uint32_t getFreeHeap(){return 100000;}
 uint32_t getMinFreeHeap(){return 90000;}
 uint32_t getFreePsram(){return 7000000;}
 uint32_t getFlashChipSize(){return 16777216;}
 uint32_t getPsramSize(){return 8388608;}
} ESP;
struct IpStub {String toString(){++legacyNetworkQueries;return "SYNTHETIC_PRIVATE_IP";}};
struct WifiStub {
 int RSSI(){++legacyNetworkQueries;return -50;}
 IpStub localIP(){++legacyNetworkQueries;return {};}
 String macAddress(){++legacyNetworkQueries;return "SYNTHETIC_PRIVATE_MAC";}
} WiFi;
enum {SCREEN_OFF};
int getScreenState(){return SCREEN_OFF;}
struct ServerStub {
 int code=0;String type,body,cache;
 void sendHeader(const char* key,const char* value){assert(std::string(key)=="Cache-Control");cache=value;}
 void send(int status,const char* contentType,const String& content){code=status;type=contentType;body=content;}
} server;
''' + handler
        harness += r'''
JsonDocument status() {
 server={};handleStatus();
 assert(server.code==200 && server.type=="application/json" && server.cache=="no-store");
 assert(server.body.find("SYNTHETIC_PRIVATE")==std::string::npos);
 assert(legacyNetworkQueries==0);
 JsonDocument doc;assert(!deserializeJson(doc,server.body));
 assert(doc["monitor_only"]==true);
 assert(doc["uptime_ms"]==nowMs);
 assert(doc["reset_reason"]==11);
 assert(doc["free_heap"]==100000 && doc["min_free_heap"]==90000 && doc["free_psram"]==7000000);
 assert(doc["display_diag_version"].is<uint32_t>() && doc["display_diag_version"]==6);
 assert(doc["display_bounce_pixels"].is<uint32_t>() && doc["display_bounce_pixels"]==bouncePixels);
 assert(doc["display_dcache_line_bytes"].is<uint32_t>() && doc["display_dcache_line_bytes"]==cacheLineBytes);
 assert(doc["display_frames"].is<uint32_t>() && doc["display_frames"]==renderDiag.frames);
 assert(doc["display_last_render_us"].is<uint32_t>() && doc["display_last_render_us"]==renderDiag.lastRenderUs);
 assert(doc["display_max_render_us"].is<uint32_t>() && doc["display_max_render_us"]==renderDiag.maxRenderUs);
 assert(doc["display_legacy_fill_probes"].is<uint32_t>() && doc["display_legacy_fill_probes"]==renderDiag.legacyFillProbes);
 assert(doc["display_legacy_fill_mismatches"].is<uint32_t>() && doc["display_legacy_fill_mismatches"]==renderDiag.legacyFillMismatches);
 assert(doc["display_fill_readback_errors"].is<uint32_t>() && doc["display_fill_readback_errors"]==renderDiag.fillReadbackErrors);
 assert(doc["display_requested_pclk_hz"]==14000000);
 assert(doc.as<JsonObject>().size()==32);
 assert(doc["loop_stack_high_water_mark"]==16384);
 for(auto key:{"ssid","password","code","token","serial","ip","mac","name","nozzle","bed","progress"})
   assert(!doc[key].is<JsonVariant>());  // never export identities or fake zero telemetry
 return doc;
}
int main() {
 auto& st=printers[0].state;
 strcpy(printers[0].config.name,"SYNTHETIC_PRIVATE_NAME");
 strcpy(printers[0].config.serial,"SYNTHETIC_PRIVATE");
 strcpy(printers[0].config.accessCode,"PRIVATE");
 // Broker up with no useful telemetry; rc is unknown until an attempt exists.
 st.connected=true;diag.lastRc=-5;diag.messagesRx=9;
 st.monitor.validReports=2;st.monitor.malformedReports=1;
 auto noData=status();
 bouncePixels=16000;  // Successful BSP init is reported without board identity/secrets.
 cacheLineBytes=64;  // Runtime ROM measurement remains separate from header constants.
 assert(noData["wifi_connected"]==true && noData["mqtt_connected"]==true);
 assert(noData["has_useful_data"]==false && noData["data_fresh"]==false);
 assert(noData["useful_age_s"].isNull() && noData["mqtt_last_rc"].isNull());
 assert(noData["messages"]==9 && noData["valid_reports"]==2 && noData["malformed_reports"]==1);
 assert(noData["first_data_delay_ms"].isNull()&&noData["first_core_delay_ms"].isNull());
 diag.attempts=1;diag.lastRc=0;diag.connectTime=1000;diag.connectDurMs=500;diag.pushallTotal=1;
 st.monitor.firstUsefulMs=1700;st.monitor.coreSeen=true;st.monitor.firstCoreMs=3200;
 st.monitor.hasUsefulData=true;st.monitor.lastUsefulMs=nowMs-1500;
 auto fresh=status();
 assert(fresh["first_data_delay_ms"]==700&&fresh["first_core_delay_ms"]==2200);
 assert(fresh["mqtt_connect_ms"]==500&&fresh["pushall_sent"]==1);
 assert(fresh["mqtt_last_rc"]==0 && fresh["mqtt_attempts"]==1);
 assert(fresh["has_useful_data"]==true && fresh["data_fresh"]==true && fresh["useful_age_s"]==1);
 // Cached MQTT=true must not survive real Wi-Fi loss or AP fallback in JSON.
 wifi=false;auto down=status();
 assert(down["wifi_connected"]==false && down["mqtt_connected"]==false && down["data_fresh"]==false);
 assert(down["has_useful_data"]==true);
 wifi=true;ap=true;auto apMode=status();
 assert(apMode["wifi_connected"]==false && apMode["mqtt_connected"]==false && apMode["data_fresh"]==false);
 ap=false;st.connected=false;auto mqttDown=status();
 assert(mqttDown["wifi_connected"]==true && mqttDown["mqtt_connected"]==false && mqttDown["data_fresh"]==false);
 // Boundary agrees with the actual telemetry freshness policy, including wrap.
 st.connected=true;st.monitor.lastUsefulMs=nowMs-BAMBU_MONITOR_FRESH_MS;
 assert(status()["data_fresh"]==true);
 st.monitor.lastUsefulMs-=1;
 assert(status()["data_fresh"]==false);
 nowMs=100;st.monitor.lastUsefulMs=UINT32_MAX-99;
 auto wrapped=status();assert(wrapped["data_fresh"]==true && wrapped["useful_age_s"]==0);
 configured=false;diag.attempts=2;diag.lastRc=-5;
 auto rc=status();assert(rc["configured"]==false && rc["mqtt_last_rc"]==-5);
 // CPU rendering counters preserve zero, actual anomalies and uint32_t limits.
 // Their numeric values must never export a framebuffer or any identity.
 renderDiag={123,80001,UINT32_MAX,122,3,2};
 status();
 renderDiag={UINT32_MAX,0,0,UINT32_MAX,UINT32_MAX,UINT32_MAX};
 status();
}
'''
        with tempfile.TemporaryDirectory(prefix='bambu-status-endpoint-') as folder:
            tmp = Path(folder)
            # Actual state/config/telemetry headers are used; Arduino types map
            # to native equivalents while pinned JSON uses its std::string writer.
            (tmp / 'Arduino.h').write_text('#pragma once\n#include <cstdint>\n#include <cstddef>\n#include <cstring>\n#include <string>\nusing String=std::string;\n')
            cpp, binary = tmp / 'status.cpp', tmp / 'status'
            cpp.write_text(harness)
            args = [compiler, '-std=c++17', '-DBAMBU_MONITOR_ONLY=1', '-DBOARD_IS_WS43B=1',
                    '-DDISPLAY_800x480=1', '-DBOARD_HAS_PSRAM=1', '-DBACKLIGHT_PIN=-1',
                    '-I', str(tmp), '-I', str(REPO / 'include'), '-I', str(REPO / 'src'),
                    '-I', str(JSON_INCLUDE), str(cpp), '-o', str(binary)]
            compile_result = subprocess.run(args, capture_output=True, text=True)
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
