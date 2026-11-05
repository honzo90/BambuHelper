#pragma once
#include <stddef.h>
#include <stdint.h>

// Internal-RAM arbitration between the printer TLS handshake and the WebUI.
// Measured on the panel: a browser loading the WebUI with six parallel
// connections while the MQTT/TLS connect runs left ~1.8 KB of internal heap
// (36 KB with no WebUI, 13 KB with sequential requests). Pure policy,
// host-testable; the firmware feeds it heap figures and timestamps.
namespace ws43b_gate {

constexpr size_t kMinFreeInternal = 40000;   // start TLS only with this much free...
constexpr size_t kMinLargestBlock = 16000;   // ...and a block for its record buffers
constexpr uint32_t kWebQuietMs = 1500;       // no WebUI request for this long
constexpr uint32_t kMaxWaitMs = 20000;       // never delay the printer longer
constexpr size_t kCriticalFreeInternal = 14000;  // below this, shed WebUI load

struct ConnectGate {
  uint32_t waitSince = 0;
  bool waiting = false;
};

// True when a printer connect may start now. Waits for a quiet WebUI and
// enough internal RAM, but at most kMaxWaitMs, so the printer is never starved.
inline bool allowConnect(ConnectGate &g, uint32_t now, size_t freeInternal, size_t largestBlock,
                         bool webSeen, uint32_t lastWebMs) {
  const bool quiet = !webSeen || uint32_t(now - lastWebMs) >= kWebQuietMs;
  const bool roomy = freeInternal >= kMinFreeInternal && largestBlock >= kMinLargestBlock;
  if (quiet && roomy) { g.waiting = false; return true; }
  if (!g.waiting) { g.waiting = true; g.waitSince = now; }
  if (uint32_t(now - g.waitSince) >= kMaxWaitMs) { g.waiting = false; return true; }
  return false;
}

// True when a WebUI request should get "503, retry" instead of running:
// only while a printer connect is in progress and internal RAM is critical.
// Firmware upload and rollback are never refused.
inline bool shedWebRequest(bool connectPending, size_t freeInternal, bool otaRequest) {
  return connectPending && !otaRequest && freeInternal < kCriticalFreeInternal;
}

}  // namespace ws43b_gate
