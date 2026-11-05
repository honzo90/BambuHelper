"""Printer TLS connect waits for a quiet WebUI and free internal RAM (max 20 s)."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
CODE = r'''
#include <cassert>
#include "ws43b_connect_gate.h"
using namespace ws43b_gate;
int main(){
 ConnectGate g;
 // Idle panel with plenty of RAM: connect at once.
 assert(allowConnect(g,1000,55000,30000,false,0));
 // Browser just loaded the WebUI: wait until 1.5 s of quiet.
 assert(!allowConnect(g,5000,55000,30000,true,4500));
 assert(allowConnect(g,6000,55000,30000,true,4500));
 // Quiet but RAM busy (free or largest block too small): wait.
 assert(!allowConnect(g,10000,30000,30000,true,0));
 assert(!allowConnect(g,10001,55000,8000,true,0));
 // ...but never longer than 20 s, so the printer is not starved.
 assert(!allowConnect(g,10000+kMaxWaitMs-1,30000,30000,true,0));
 assert(allowConnect(g,10000+kMaxWaitMs,30000,30000,true,0));
 // The wait restarts after a successful decision; millis wrap is handled.
 ConnectGate w; assert(!allowConnect(w,0xFFFFFF00u,30000,30000,false,0));
 assert(allowConnect(w,0xFFFFFF00u+kMaxWaitMs,30000,30000,false,0));
 // WebUI load shedding: only during a connect, only when critical, never OTA.
 assert(shedWebRequest(true,10000,false));
 assert(!shedWebRequest(true,10000,true));
 assert(!shedWebRequest(false,1000,false));
 assert(!shedWebRequest(true,20000,false));
 return 0;
}
'''


class ConnectGate(unittest.TestCase):
    def test_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'g.cpp'; src.write_text(CODE); exe = Path(tmp) / 'g'
            subprocess.run(['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'include'),
                            str(src), '-o', str(exe)], check=True, capture_output=True, text=True)
            subprocess.run([str(exe)], check=True)

    def test_wired_in(self):
        mqtt = (ROOT / 'src/bambu_mqtt.cpp').read_text()
        body = mqtt[mqtt.index('static void reconnectConn'):]
        body = body[:body.index('c.diag.lastAttemptMs = now;')]
        self.assertIn('ws43b_gate::allowConnect(', body)  # gate sits before the attempt is recorded
        web = (ROOT / 'src/web_server.cpp').read_text()
        self.assertIn('server.addMiddleware(', web)
        self.assertIn('s.uri().startsWith("/ota/")', web)


if __name__ == '__main__':
    unittest.main()
