"""Native backpressure model: logs never wait; Improv retains packet allowance."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class UsbLogPolicy(unittest.TestCase):
    def test_unread_logs_and_improv_reply_use_different_wait_policies(self):
        code = r'''
#include "ws43b_usb_log.h"
#include <cassert>
#include <string>
struct Port {
  unsigned timeout = 100, waited = 0;
  bool hostReading = false;
  std::string received;
  void setTxTimeoutMs(unsigned value) { timeout = value; }
  // Model a full TX FIFO. A reading host needs one tick to free space.
  unsigned write(const std::string &packet) {
    if (!timeout) return 0;
    if (!hostReading) { waited += 20 * timeout; return 0; }
    ++waited;
    received += packet;
    return packet.size();
  }
};
void reply(Port &port) {
  ws43b_usb::ImprovReplyWindow<Port> window(port);
  assert(port.timeout == 100);
  assert(port.write("IMPROV reply") == 12);
  return; // Every exit restores the log policy.
}
int main() {
  Port port;
  ws43b_usb::beginLogging(port);
  for (unsigned i = 0; i < 100; ++i) port.write("boot log");
  assert(port.waited == 0 && port.received.empty());
  port.hostReading = true;
  reply(port);
  assert(port.received == "IMPROV reply" && port.waited == 1);
  assert(port.timeout == 0);
  port.hostReading = false;
  port.write("MQTT status");
  assert(port.waited == 1);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'test.cpp').write_text(code)
            subprocess.run(['clang++', '-std=c++11', '-Wall', '-Wextra', '-Werror',
                            '-I' + str(ROOT / 'src'), str(path / 'test.cpp'),
                            '-o', str(path / 'test')], check=True, capture_output=True)
            subprocess.run([str(path / 'test')], check=True, capture_output=True)
