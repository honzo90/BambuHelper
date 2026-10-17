"""Offline verification of actual conditional cloud/TLS code in both profiles.

Preprocesses project sources and compiles real request/client functions against
counting TLS/HTTP stubs. Never starts networking, serial or account login.
"""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[4]


def without_includes(source):
    return re.sub(r'^\s*#include[^\n]*\n', '', source, flags=re.M)


def compiler():
    result = shutil.which('clang++') or shutil.which('c++')
    if not result:
        raise unittest.SkipTest('Native C++ compiler required')
    return result


def preprocess(relative, monitor):
    source = without_includes((REPO / 'include/config.h').read_text())
    source += '\nCLOUD_POLICY_FEATURE HAS_CLOUD_LOGIN\n'
    source += without_includes((REPO / relative).read_text())
    args = [compiler(), '-E', '-P', '-x', 'c++', f'-DBAMBU_MONITOR_ONLY={monitor}']
    if monitor:
        args += ['-DBOARD_IS_WS43B=1', '-DBOARD_HAS_PSRAM=1']
    result = subprocess.run(args + ['-'], input=source, capture_output=True, text=True, check=True)
    return result.stdout


def section(source, begin, end):
    start = source.index(begin)
    return source[start:source.index(end, start)]


def native(source, monitor):
    with tempfile.TemporaryDirectory(prefix='bambu-cloud-policy-') as folder:
        cpp, binary = Path(folder) / 'policy.cpp', Path(folder) / 'policy'
        cpp.write_text('#include "ws43b_memory_diag.h"\n' + source)
        args = [compiler(), '-std=c++17', '-I' + str(REPO / 'src'), f'-DBAMBU_MONITOR_ONLY={monitor}']
        if monitor:
            args.append('-DBOARD_IS_WS43B=1')
        subprocess.run(args + [str(cpp), '-o', str(binary)], capture_output=True, text=True, check=True)
        subprocess.run([str(binary)], capture_output=True, text=True, check=True)


class CloudPolicyTests(unittest.TestCase):
    def test_actual_config_excludes_password_login_translation_unit(self):
        monitor = preprocess('src/cloud_login.cpp', 1)
        normal = preprocess('src/cloud_login.cpp', 0)
        self.assertIn('CLOUD_POLICY_FEATURE 0', monitor)
        self.assertIn('CLOUD_POLICY_FEATURE 1', normal)
        for symbol in ('cloudLoginWithPassword(', 'cloudLoginRequestEmailCode(',
                       'cloudLoginSubmitCode(', 'cloudLoginRefreshStored(',
                       'loadCloudPassword(', 'user/login', 'sendemail/code'):
            self.assertNotIn(symbol, monitor)
            self.assertIn(symbol, normal)

    def test_cloud_https_fail_closed_and_sensitive_logs_excluded(self):
        monitor = preprocess('src/bambu_cloud.cpp', 1)
        normal = preprocess('src/bambu_cloud.cpp', 0)
        self.assertNotIn('setInsecure(', monitor)
        self.assertIn('setInsecure(', normal)
        self.assertNotIn('response.substring(0, 300)', monitor)
        self.assertIn('response.substring(0, 300)', normal)
        self.assertIn('cloudFetchUserId(', monitor)  # explicit token path retained
        self.assertIn('rootca_crt_bundle_end - rootca_crt_bundle_start', monitor)

    def test_mqtt_has_no_password_login_call_or_definition(self):
        monitor = preprocess('src/bambu_mqtt.cpp', 1)
        normal = preprocess('src/bambu_mqtt.cpp', 0)
        for symbol in ('tryStoredPasswordRelogin(', 'cloudLoginCanAutoRefresh(', 'cloudLoginRefreshStored('):
            self.assertNotIn(symbol, monitor)
            self.assertIn(symbol, normal)
        # LAN's original self-signed-certificate behavior is explicitly retained.
        self.assertIn('c.tls->setInsecure()', monitor)
        self.assertIn('rootca_crt_bundle_end - rootca_crt_bundle_start', monitor)

    def test_actual_https_request_never_retries_insecure_in_monitor(self):
        source = (REPO / 'src/bambu_cloud.cpp').read_text()
        function = section(source, 'static int httpsRequest(const char*', '// Base64url decode')
        harness = r'''
#include <cassert>
#include <cstdint>
#include <cstddef>
#include <new>
#include <string>
using String=std::string;
uint8_t bundle[32]{};
const uint8_t* rootca_crt_bundle_start=bundle;
const uint8_t* rootca_crt_bundle_end=bundle+sizeof(bundle);
static int requests=0,insecure=0,bundleArgs=0,firstResult=-1;
static size_t bundleSize=0;
struct WiFiClientSecure {
 void setTimeout(int) {} void setHandshakeTimeout(int) {}
 void setCACertBundle(const uint8_t*) { bundleArgs=1; }
 void setCACertBundle(const uint8_t*,size_t size) {bundleArgs=2;bundleSize=size;}
 void setInsecure() {++insecure;}
};
struct Console {void println(const char*) {}} Serial;
int httpsRequestWith(WiFiClientSecure&,const char*,const char*,const char*,const char*,String&,const char*) {
 ++requests;return requests==1?firstResult:200;
}
''' + function
        harness += r'''
int main() {
 String response;
 auto result=httpsRequest("GET","https://synthetic.example/",nullptr,"synthetic-token",response);
#if BAMBU_MONITOR_ONLY
 assert(result==-1 && requests==1 && insecure==0);
 assert(bundleArgs==2 && bundleSize==32);
#else
 assert(result==200 && requests==2 && insecure==1);
 assert(bundleArgs==1);
#endif
 requests=0;insecure=0;firstResult=200;
 result=httpsRequest("GET","https://synthetic.example/",nullptr,"synthetic-token",response);
 assert(result==200 && requests==1 && insecure==0);
}
'''
        native(harness, 1)
        native(harness, 0)

    def test_actual_mqtt_client_selects_verified_cloud_and_existing_lan_tls(self):
        source = (REPO / 'src/bambu_mqtt.cpp').read_text()
        function = section(source, 'static bool ensureClients(', '//  Request pushall')
        # Include only the function: the trailing separator comments are harmless.
        harness = r'''
#include <cassert>
#include <cstdint>
#include <cstddef>
#include <new>
#define MQTT_LOG(...) do {} while(0)
#define BAMBU_MIN_FREE_HEAP 100
#define BAMBU_BUFFER_SIZE 4096
#define BAMBU_PORT 8883
#define BAMBU_CLOUD_KEEPALIVE 120
#define BAMBU_KEEPALIVE 30
uint8_t bundle[32]{};
const uint8_t* rootca_crt_bundle_start=bundle;
const uint8_t* rootca_crt_bundle_end=bundle+sizeof(bundle);
struct Esp {uint32_t getFreeHeap(){return 100000;}} ESP;
struct WiFiClientSecure {
 int bundleArgs=0,insecure=0;size_t bundleSize=0;
 void setTimeout(int) {}
 void setCACertBundle(const uint8_t*) {bundleArgs=1;}
 void setCACertBundle(const uint8_t*,size_t size) {bundleArgs=2;bundleSize=size;}
 void setInsecure() {++insecure;}
};
struct MqttRxClient {
 using Handler = void(*)();
 explicit MqttRxClient(WiFiClientSecure&) {}
 bool begin(size_t,void(*)()) {return true;}
};
struct PubSubClient {
 explicit PubSubClient(MqttRxClient&) {}
 void setServer(const char*,int) {}
 bool setBufferSize(size_t) {return true;}
 void setCallback(void(*)()) {}
 void setKeepAlive(int) {}
};
void mqttCallback() {}
struct PrinterConfig {int mode=1;int region=0;char ip[16]{};};
struct Printer {PrinterConfig config;} printers[1];
bool isCloudMode(int mode) {return mode==1;}
const char* getBambuBroker(int) {return "synthetic.example";}
struct MqttConn {int slotIndex=0;WiFiClientSecure* tls=nullptr;MqttRxClient* io=nullptr;PubSubClient* mqtt=nullptr;};
''' + function
        harness += r'''
int main() {
 MqttConn cloud;printers[0].config.mode=1;
 assert(ensureClients(cloud, printers[0].config));assert(cloud.tls->insecure==0);
#if BAMBU_MONITOR_ONLY
 assert(cloud.tls->bundleArgs==2 && cloud.tls->bundleSize==32);
#else
 assert(cloud.tls->bundleArgs==1);
#endif
 delete cloud.mqtt;delete cloud.io;delete cloud.tls;
 MqttConn lan;printers[0].config.mode=0;
 assert(ensureClients(lan, printers[0].config));assert(lan.tls->insecure==1 && lan.tls->bundleArgs==0);
 delete lan.mqtt;delete lan.io;delete lan.tls;
}
'''
        native(harness, 1)
        native(harness, 0)


if __name__ == '__main__':
    unittest.main()
