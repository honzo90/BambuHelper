"""Verify diagnostic TLS split fails closed and measures each bounded stage."""
from pathlib import Path
import subprocess, tempfile, unittest
ROOT=Path(__file__).resolve().parents[4]
class ConnectionTiming(unittest.TestCase):
 def test_tls_failure_never_reports_ready_and_wraparound_is_safe(self):
  code=r'''
#include "ws43b_connection_diag.h"
#include <cassert>
uint32_t now=0;
struct Fake {
 bool plain=false, stopped=false; int connected=1, secured=1, tlsCalls=0;
 uint32_t transportDelay=8,tlsDelay=64000;
 void setPlainStart(){plain=true;}
 int connect(const char*,uint16_t){assert(plain);now+=transportDelay;return connected;}
 int startTLS(){++tlsCalls;now+=tlsDelay;return secured;}
 void stop(){stopped=true;}
};
int main(){
 ws43b_connection::Timing t;
 auto clock=[](){return now;};
 Fake ok;now=0xfffffff0u;
 assert(ws43b_connection::connect(ok,"fixture",8883,t,clock)==1);
 assert(t.transportMs==8&&t.tlsMs==64000&&t.tlsReady&&!ok.stopped);
 Fake tcpFail;tcpFail.connected=0;
 assert(ws43b_connection::connect(tcpFail,"fixture",8883,t,clock)==0);
 assert(!t.tlsReady&&t.tlsMs==0&&tcpFail.tlsCalls==0);
 Fake tlsFail;tlsFail.secured=0;
 assert(ws43b_connection::connect(tlsFail,"fixture",8883,t,clock)==0);
 assert(!t.tlsReady&&tlsFail.stopped&&tlsFail.tlsCalls==1);
}
'''
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'test.cpp').write_text(code)
   subprocess.run(['clang++','-std=c++17','-DWS43B_CONNECT_DIAG=1','-I'+str(ROOT/'src'),str(p/'test.cpp'),'-o',str(p/'test')],check=True,capture_output=True)
   subprocess.run([str(p/'test')],check=True,capture_output=True)
