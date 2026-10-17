"""Exercise actual cloud HTTP framing with slow segmented synthetic TLS bytes."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class CloudHttpReader(unittest.TestCase):
    def test_delayed_framing_deadline_bounds_and_partial_failures(self):
        source = r'''
#include "cloud_http_reader.h"
#include <cassert>
#include <string>
#include <vector>
#include <utility>
#include <algorithm>
using cloud_http::Result;
struct FakeTls {
 std::vector<std::pair<uint32_t,std::string>> segments;
 size_t segment=0, offset=0;uint32_t elapsed=0, clockBase=0;
 bool close=true;int transientReads=0;unsigned waits=0;
 int available(){return segment<segments.size()&&elapsed>=segments[segment].first ? segments[segment].second.size()-offset:0;}
 bool connected(){return !close||segment<segments.size();}
 int read(uint8_t* p,size_t n){if(transientReads>0){--transientReads;return -1;}
  int have=available();if(!have)return -1;size_t count=std::min(n,size_t(have));
  memcpy(p,segments[segment].second.data()+offset,count);offset+=count;
  if(offset==segments[segment].second.size()){offset=0;++segment;}return count;}
};
struct Answer{int status=-1;std::string cookies,body;};
Result read(FakeTls& f, Answer& a,size_t cap=8192,uint32_t deadline=12000){
 return cloud_http::readResponse(f,a.status,a.cookies,a.body,cap,
 [&]{return f.clockBase+f.elapsed;},[&]{++f.elapsed;++f.waits;},deadline);}
Result fast(const std::string& response,Answer& a,size_t cap=8192){FakeTls f{{{0,response}}};return read(f,a,cap);}
int main(){
 Answer a;
 FakeTls delayed{{{0,"HTTP/1.1 2"},{50,"00 OK\r"},{70,"\nContent-Len"},
  {200,"gth: 11\r\nSet-Cookie: token=one; Path=/\r\nset-cookie: csrf=two\r\n\r"},
  {400,"\n{\"ok\":"},{650,"true}"}}};
 assert(read(delayed,a)==Result::Complete&&a.status==200&&a.body=="{\"ok\":true}");
 assert(a.cookies=="token=one; Path=/\ncsrf=two\n"&&delayed.waits>=650);
 a={};FakeTls chunked{{{0,"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"},
 {40,"5;foo=bar\r"},{80,"\nhello"},{200,"\r"},{300,"\n6\r\n wor"},
 {410,"ld\r\n0\r\nDigest: ignored\r\n"},{600,"\r\n"}}};
 assert(read(chunked,a)==Result::Complete&&a.body=="hello world"&&chunked.waits>=600);
 a={};FakeTls identity{{{10,"HTTP/1.0 200 OK\r\n\r\nhe"},{80,"llo"}}};
 assert(read(identity,a)==Result::Complete&&a.body=="hello");
 a={};FakeTls transient{{{0,"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}"}}};transient.transientReads=3;
 assert(read(transient,a)==Result::Complete&&transient.waits==3&&a.body=="{}");
 // Complete empty bodies do not require a close or a spurious timeout.
 a={};FakeTls zero{{{0,"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"}}};zero.close=false;
 assert(read(zero,a)==Result::Complete&&a.body.empty()&&zero.waits==0);
 a={};assert(fast("HTTP/1.1 204 No Content\r\n\r\n",a)==Result::Complete);
 // A syntactically valid JSON prefix must not be accepted as a complete reply.
 a={};assert(fast("HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\n{}",a)==Result::Disconnected);
 a={};assert(fast("HTTP/1.1 200 OK\r\nContent-Length: 2\r",a)==Result::Disconnected);
 a={};FakeTls stuck{{{0,"HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\n{}"}}};stuck.close=false;
 assert(read(stuck,a,8192,75)==Result::Timeout&&stuck.elapsed==75&&stuck.waits==75);
 a={};FakeTls closeTimeout{{{0,"HTTP/1.1 200 OK\r\n\r\n{}"}}};closeTimeout.close=false;
 assert(read(closeTimeout,a,8192,75)==Result::Timeout);
 // One deadline spans headers, every body gap and trailers, including millis wrap.
 a={};FakeTls wrap{{{0,"HTTP/1.1 200 OK\r\n"},{40,"Content-Length: 2\r\n\r\n"},{90,"{}"}}};wrap.clockBase=0xfffffff0;
 assert(read(wrap,a,8192,75)==Result::Timeout&&wrap.elapsed==75);
 a={};FakeTls trailer{{{0,"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n2\r\n{}\r\n0\r\n"},{100,"\r\n"}}};
 assert(read(trailer,a,8192,75)==Result::Timeout);
 for(const std::string& bad:{
  "HTTP/1.1 200 OK\r\nContent-Length: -1\r\n\r\n",
  "HTTP/1.1 200 OK\r\nContent-Length: 2\r\nContent-Length: 3\r\n\r\n{}",
  "HTTP/1.1 200 OK\r\nContent-Length: 2\r\nTransfer-Encoding: chunked\r\n\r\n{}",
  "HTTP/1.1 200 OK\r\nTransfer-Encoding: gzip\r\n\r\n{}",
  "HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\nnope\r\n",
  "HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n1\r\naxx\r\n",
  "HTTP/1.1 200 OK\nContent-Length: 2\n\n{}",
  "HTTP/1.1 200 OK\r\nContent-Length: 999999999999999999999999999999999\r\n\r\n"}){
  a={};assert(fast(bad,a)==Result::Malformed);
 }
 a={};assert(fast("HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n2\r\n{}\r\n",a)==Result::Disconnected);
 a={};assert(fast("HTTP/1.1 200 OK\r\nContent-Length: 200\r\n\r\n",a,100)==Result::TooLarge&&a.body.empty());
 a={};assert(fast("HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n3\r\ndef\r\n0\r\n\r\n",a,5)==Result::TooLarge&&a.body=="abc");
 a={};assert(fast("HTTP/1.0 200 OK\r\n\r\nabcdef",a,5)==Result::TooLarge&&a.body=="abcde");
 std::string longLine="HTTP/1.1 200 OK\r\nX: "+std::string(2048,'x')+"\r\n\r\n";
 a={};assert(fast(longLine,a)==Result::TooLarge);
 std::string cookies="HTTP/1.1 200 OK\r\n";
 for(int i=0;i<5;++i)cookies+="Set-Cookie: "+std::string(1000,'x')+"\r\n";
 a={};assert(fast(cookies+"Content-Length: 0\r\n\r\n",a)==Result::TooLarge&&a.cookies.size()<=4096);
 std::string headers="HTTP/1.1 200 OK\r\n";
 for(int i=0;i<13;++i)headers+="X: "+std::string(1000,'x')+"\r\n";
 a={};assert(fast(headers+"\r\n",a)==Result::TooLarge);
 // Existing output above its cap must fail without unsigned size underflow.
 a={};a.body="already too long";
 assert(fast("HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}",a,3)==Result::TooLarge);
}
'''
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            (p / 'test.cpp').write_text(source)
            subprocess.run(['clang++', '-std=c++17', '-fsanitize=address,undefined',
                            '-I', str(ROOT / 'include'), str(p / 'test.cpp'), '-o', str(p / 'test')],
                           check=True, capture_output=True, text=True)
            subprocess.run([str(p / 'test')], check=True, capture_output=True, text=True, timeout=15)

    def test_cloud_transport_uses_complete_framing_before_cookie_commit(self):
        source = (ROOT / 'src/cloud_login.cpp').read_text()
        request = source[source.index('static bool cloudRequest('):source.index('//  Flow steps')]
        self.assertNotIn('tls->readStringUntil(', request)
        self.assertNotIn('tls->readBytes(', request)
        self.assertIn('cloud_http::readResponse(', request)
        self.assertIn('if (complete && useSession) jarAbsorb(', request)
        self.assertIn('delay(1)', request)


if __name__ == '__main__':
    unittest.main()
