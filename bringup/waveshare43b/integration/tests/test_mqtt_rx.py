"""Exercise the upstream packet adapter with synthetic, fragmented MQTT frames."""
from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[4]
class MqttRx(unittest.TestCase):
 def test_fragmentation_controls_invalid_lengths_and_recovery(self):
  s=(ROOT/'src/bambu_mqtt.cpp').read_text();start=s.index('class MqttRxClient : public Client {');end=s.index('\n};',start)+3
  code=r'''
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <algorithm>
#include <vector>
#include <string>
using byte=uint8_t;struct IPAddress{};
static int yields=0;void vTaskDelay(int){++yields;}
#define MQTT_LOG(...) do {} while(0)
struct Client {
 virtual int connect(IPAddress,uint16_t)=0;virtual int connect(const char*,uint16_t)=0;
 virtual size_t write(uint8_t)=0;virtual size_t write(const uint8_t*,size_t)=0;
 virtual int available()=0;virtual int read()=0;virtual int read(uint8_t*,size_t)=0;virtual int peek()=0;
 virtual void flush()=0;virtual void stop()=0;virtual uint8_t connected()=0;virtual operator bool()=0;
};
struct WiFiClientSecure {
 std::vector<uint8_t> in;size_t pos=0;bool live=true;
 int connect(IPAddress,uint16_t,int=0){return live=true;}int connect(const char*,uint16_t,int=0){return live=true;}
 size_t write(uint8_t){return 1;}size_t write(const uint8_t*,size_t n){return n;}
 int available(){return in.size()-pos;}int read(){return available()?in[pos++]:-1;}
 int read(uint8_t*b,size_t n){n=std::min(n,size_t(available()));memcpy(b,in.data()+pos,n);pos+=n;return n;}
 void flush(){}void stop(){live=false;}uint8_t connected(){return live;}operator bool(){return live;}
 void add(std::initializer_list<uint8_t> b){in.insert(in.end(),b);}
};
''' + s[start:end] + r'''
static int callbacks=0;static std::string topic,payload;
void got(char*t,byte*p,unsigned n){++callbacks;topic=t;payload.assign((char*)p,n);}
int main(){
 WiFiClientSecure tls;MqttRxClient rx(tls);assert(rx.begin(128,got));
#if BOARD_MQTT_ASYNC_CONNECT
 rx.connecting=true;rx.setHandler(nullptr);
 tls.add({0x30,4,0,1,'t','x'});rx.available();assert(callbacks==0&&yields>0);
 tls.add({0x20,2,0,0});assert(rx.available()==4);uint8_t ack[4];assert(rx.read(ack,4)==4);
 rx.connecting=false;rx.setHandler(got);
#endif
 tls.add({0x30,6,0});assert(rx.available()==0&&callbacks==0);
 tls.add({1,'t','a','b','c'});assert(rx.available()==0&&callbacks==1&&topic=="t"&&payload=="abc");
 tls.add({0x20,2,0,0});assert(rx.available()==4);assert(rx.peek()==0x20);uint8_t out[4];assert(rx.read(out,4)==4&&out[0]==0x20&&out[1]==2&&out[3]==0);
 tls.add({0x30,4,0,1,'t','1',0x30,4,0,1,'t','2'});
 rx.available();assert(callbacks==2&&payload=="1");rx.available();assert(callbacks==3&&payload=="2");
 tls.add({0x30,2,0,8});rx.available();assert(callbacks==3); // invalid topic length
 tls.add({0x30,0x81,1});for(int i=0;i<129;++i)tls.in.push_back(0); // oversize publish discarded
 tls.add({0xD0,0});assert(rx.available()==2);assert(rx.read()==0xD0&&rx.read()==0);assert(callbacks==3);
 tls.add({0x30,0x80,0x80,0x80,0x80});rx.available();assert(!tls.live);
 tls.in.clear();tls.pos=0;rx.connect("fixture",8883);tls.add({0x30,4,0,1,'t','3'});rx.available();assert(callbacks==4&&payload=="3");
}
'''
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);(p/'rx.cpp').write_text(code)
   for async_connect in (0,1):
    subprocess.run(['clang++','-std=c++17',f'-DBOARD_MQTT_ASYNC_CONNECT={async_connect}','-fsanitize=address,undefined',str(p/'rx.cpp'),'-o',str(p/'rx')],check=True,capture_output=True)
    subprocess.run([str(p/'rx')],check=True,capture_output=True)
