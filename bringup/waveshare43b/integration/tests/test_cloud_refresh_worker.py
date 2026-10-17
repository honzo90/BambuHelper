"""Run actual automatic renewal lifecycle with a stalled detached HTTPS stub.
No account/network/USB access. Native ASan/UBSan checks cancellation and ownership.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


def section(source, start, end):
    begin = source.index(start)
    return source[begin:source.index(end, begin)]


class CloudRefreshWorker(unittest.TestCase):
    def test_detached_response_manual_cancel_config_and_second_factor(self):
        src = (ROOT / 'src/cloud_login.cpp').read_text()
        lifecycle = section(src, 'struct StoredRefreshJob {', '\n#endif // BOARD_MQTT_ASYNC_CONNECT')
        finalize = section(src, 'static bool finishStoredRefresh(', '\nbool cloudLoginRefreshStored()')
        reset = section(src, 'void cloudLoginReset() {', '\n// ---------------------------------------------------------------------------')
        stub = r'''
#include <atomic>
#include <thread>
#include <string>
#include <map>
#include <cassert>
#include <cstring>
#include <cstdio>
#include <chrono>
#include <cstdint>
#define BOARD_MQTT_ASYNC_CONNECT 1
#define MAX_ACTIVE_PRINTERS 2
#define CLOUD_EMAIL_MAX 95
#define CLOUD_PASSWORD_MAX 127
#define CLOUD_TOKEN_MAX 1200
#define pdPASS 1
using String = std::string;
enum CloudLoginState {CLOUD_LOGIN_IDLE, CLOUD_LOGIN_NEED_TFA,
 CLOUD_LOGIN_NEED_EMAIL_CODE, CLOUD_LOGIN_OK, CLOUD_LOGIN_FAILED};
CloudLoginState g_state = CLOUD_LOGIN_IDLE;
String g_message, g_jar, g_csrf, g_tfaKey, g_email;
bool g_neededTwoFactor = false, g_lastFailed = false;
uint32_t storedRefreshGeneration = 0;
void cloudLoginReset();
const auto mainThread = std::this_thread::get_id();
void onMain(){assert(std::this_thread::get_id()==mainThread);}
struct {void println(const char*){} template<typename... T>void printf(const char*,T...){} } Serial;
struct PrinterConfig {int mode=1, region=0; char serial[20]="PRINTER", cloudUserId[32]="USER";};
struct {PrinterConfig config;} printers[2];
bool isCloudMode(int mode){return mode==1;}
String savedEmail="user@example.invalid", savedPassword="ORIGINAL", savedToken="OLD";
int commits=0, clears=0, parsed=0;
bool read(String s,char* out,size_t size){onMain();if(s.empty())return false;assert(s.size()<size);strcpy(out,s.c_str());return true;}
bool loadCloudEmail(char* out,size_t n){return read(savedEmail,out,n);}
bool loadCloudPassword(char* out,size_t n){return read(savedPassword,out,n);}
bool loadCloudToken(char* out,size_t n){return read(savedToken,out,n);}
void clearCloudPassword(){onMain();savedPassword.clear();++clears;}
bool fail(const char* text){onMain();g_state=CLOUD_LOGIN_FAILED;g_message=text;g_lastFailed=true;return false;}
struct CloudResponse {int result=0;};
bool handleLoginReply(const CloudResponse& r){onMain();++parsed;
 if(r.result==0){savedToken="NEW";g_state=CLOUD_LOGIN_OK;++commits;return true;}
 if(r.result==1){g_state=CLOUD_LOGIN_NEED_TFA;g_neededTwoFactor=true;return true;}
 if(r.result==2){g_state=CLOUD_LOGIN_NEED_EMAIL_CODE;g_neededTwoFactor=true;return true;}
 if(r.result==3){g_neededTwoFactor=true;return fail("malformed tfa");}
 return fail("wrong password");
}
struct JsonDocument {std::map<String,String> v;String&operator[](const char*k){return v[k];}};
void serializeJson(JsonDocument& b,String& p){p=b.v["account"]+"|"+b.v["password"];}
const char* apiHost(int r){return r==0?"global.invalid":"cn.invalid";}
std::thread task;
std::atomic<bool> hold{false},entered{false};
bool taskOk=true, transportOk=true;int nextResult=0;
String sentPayload, sentHost;
bool cloudRequest(const char* host,const char*,const char*,const char* body,bool session,
 CloudResponse& r,size_t maxBody,bool feedWatchdog){
 assert(std::this_thread::get_id()!=mainThread && !session && !feedWatchdog && maxBody==8192);
 entered=true;while(hold)std::this_thread::sleep_for(std::chrono::milliseconds(1));
 sentPayload=body;sentHost=host;r.result=nextResult;return transportOk;
}
void vTaskDelete(void*){}
int xTaskCreatePinnedToCore(void(*fn)(void*),const char*,int bytes,void*,int,void*,int core){
 onMain();assert(bytes==8192&&core==0);if(!taskOk)return 0;task=std::thread([fn]{fn(nullptr);});return pdPASS;
}
'''
        cases = r'''
void waitEntered(){for(int i=0;i<1000&&!entered;++i)std::this_thread::sleep_for(std::chrono::milliseconds(1));assert(entered);}
void start(){savedEmail="user@example.invalid";savedPassword="ORIGINAL";savedToken="OLD";
 printers[0].config={};transportOk=true;nextResult=0;cloudLoginReset();entered=false;hold=true;
 assert(cloudLoginStartStoredRefresh(0));waitEntered();assert(cloudLoginStoredRefreshPending());}
void finish(){hold=false;task.join();cloudLoginServiceStoredRefresh();assert(!cloudLoginStoredRefreshPending());
 assert(storedRefreshJob.password[0]==0 && storedRefreshJob.token[0]==0 && storedRefreshJob.email[0]==0);}
int main(){
 start();for(int i=0;i<2000;++i)cloudLoginServiceStoredRefresh();
 assert(commits==0 && parsed==0 && !cloudLoginStartStoredRefresh(1));
 finish();assert(commits==1 && savedToken=="NEW" && sentPayload=="user@example.invalid|ORIGINAL");
 // Manual reset, password sign-in/email-code start and self-test all use reset.
 start();cloudLoginReset();g_state=CLOUD_LOGIN_NEED_TFA;g_tfaKey="MANUAL";finish();
 assert(commits==1&&g_state==CLOUD_LOGIN_NEED_TFA&&g_tfaKey=="MANUAL");
 // Slot lifecycle invalidation, even if the slot later has identical values.
 start();cloudLoginCancelStoredRefresh(0);finish();assert(commits==1);
 start();cloudLoginCancelStoredRefresh(1);finish();assert(commits==2);
 // Direct config or persisted credential changes are rejected as well.
 start();printers[0].config.region=1;finish();assert(commits==2&&sentHost=="global.invalid");
 start();strcpy(printers[0].config.serial,"REPLACED");finish();assert(commits==2);
 start();strcpy(printers[0].config.cloudUserId,"NEW_USER");finish();assert(commits==2);
 start();printers[0].config.mode=0;finish();assert(commits==2);
 start();savedEmail="other@example.invalid";finish();assert(commits==2);
 start();savedPassword="MANUAL_PASSWORD";finish();assert(commits==2&&sentPayload=="user@example.invalid|ORIGINAL");
 start();savedToken="PASTED_TOKEN";finish();assert(commits==2&&savedToken=="PASTED_TOKEN");
 start();savedToken.clear();finish();assert(commits==2&&savedToken.empty());
 // Transport/auth failure preserves password; second factor and malformed
 // challenge clear it on the main loop, without leaving unsolicited prompts.
 start();transportOk=false;finish();assert(savedPassword=="ORIGINAL"&&g_state==CLOUD_LOGIN_FAILED);
 start();nextResult=4;finish();assert(savedPassword=="ORIGINAL"&&g_state==CLOUD_LOGIN_FAILED);
 for(int result=1;result<=3;++result){start();nextResult=result;finish();
 assert(savedPassword.empty()&&g_state==CLOUD_LOGIN_FAILED);}
 assert(clears==3&&commits==2);
 // A stale second-factor answer must not clear a newly saved password.
 start();nextResult=1;cloudLoginReset();savedPassword="MANUAL_PASSWORD";finish();assert(clears==3&&savedPassword=="MANUAL_PASSWORD");
 cloudLoginReset();savedEmail="user@example.invalid";savedPassword="ORIGINAL";savedToken="OLD";
 taskOk=false;assert(!cloudLoginStartStoredRefresh(0)&&!cloudLoginStoredRefreshPending());
 assert(storedRefreshJob.password[0]==0);taskOk=true;
 savedToken.clear();assert(!cloudLoginStartStoredRefresh(0)&&!cloudLoginStoredRefreshPending());savedToken="OLD";
 for(auto state:{CLOUD_LOGIN_NEED_TFA,CLOUD_LOGIN_NEED_EMAIL_CODE}){g_state=state;assert(!cloudLoginStartStoredRefresh(0));}
 cloudLoginReset();assert(!cloudLoginStartStoredRefresh(MAX_ACTIVE_PRINTERS));
}
'''
        self.run_native(stub + reset + finalize + lifecycle + cases)

    def test_mqtt_automatic_path_is_scheduled_and_rate_limited(self):
        src = (ROOT / 'src/bambu_mqtt.cpp').read_text()
        function = section(src, 'static bool tryStoredPasswordRelogin(', '\n#endif\n\n// ---------------------------------------------------------------------------')
        stub = r'''
#include <cstdint>
#include <cassert>
#define BOARD_MQTT_ASYNC_CONNECT 1
#define HAS_CLOUD_LOGIN 1
#define MQTT_LOG(...) do{}while(0)
uint32_t now=0;uint32_t millis(){return now;}
bool cloudLoginCanAutoRefresh(){return true;}
int schedules=0;bool cloudLoginStartStoredRefresh(uint8_t slot){assert(slot==0);++schedules;return true;}
'''
        cases = r'''
int main(){assert(tryStoredPasswordRelogin(0));assert(!tryStoredPasswordRelogin(0));
 now=899999;assert(!tryStoredPasswordRelogin(0));now=900000;assert(tryStoredPasswordRelogin(0));
 now=0xffffff00;assert(tryStoredPasswordRelogin(0));now=10;assert(!tryStoredPasswordRelogin(0));
 now=900000;assert(tryStoredPasswordRelogin(0));assert(schedules==4);}
'''
        self.run_native(stub + function + cases)

    @staticmethod
    def run_native(source):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            (p / 'test.cpp').write_text(source)
            subprocess.run(['clang++', '-std=c++17', '-pthread', '-fsanitize=address,undefined',
                            str(p / 'test.cpp'), '-o', str(p / 'test')],
                           check=True, capture_output=True, text=True)
            subprocess.run([str(p / 'test')], check=True, capture_output=True, text=True, timeout=15)


if __name__ == '__main__':
    unittest.main()
