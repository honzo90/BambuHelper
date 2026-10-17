#pragma once
#include <stdint.h>
#ifndef WS43B_CONNECT_DIAG
#define WS43B_CONNECT_DIAG 0
#endif
#if WS43B_CONNECT_DIAG
namespace ws43b_connection {
struct Timing { uint32_t transportMs = 0, tlsMs = 0; bool tlsReady = false; };
// Diagnostic-only split of the pinned core's connect() sequence. No application
// data may be sent until startTLS succeeds. Certificate policy is unchanged.
template<class Client, class Address, class Clock>
int connect(Client &client, Address address, uint16_t port, Timing &timing, Clock clock) {
  timing = {};
  client.setPlainStart();
  uint32_t start = clock();
  int result = client.connect(address, port);
  timing.transportMs = uint32_t(clock() - start);
  if (!result) return 0;
  start = clock();
  result = client.startTLS();
  timing.tlsMs = uint32_t(clock() - start);
  timing.tlsReady = result == 1;
  if (!timing.tlsReady) client.stop();
  return timing.tlsReady ? 1 : 0;
}
}
#endif
