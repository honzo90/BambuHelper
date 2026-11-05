#pragma once
#include <stdint.h>

namespace ws43b_tls {
struct Stats { bool ready; uint32_t psramAllocations, psramFailures; };
// TLS buffers now use PSRAM; retain an internal reserve for Wi-Fi/UI/MQTT.
inline bool canStartWeather(uint32_t internalFree, uint32_t psramFree) {
  return internalFree >= 40000 && psramFree >= 128u * 1024u;
}
#if defined(BOARD_IS_WS43B)
// Install once from setup, before any TLS client or weather task starts.
bool begin();
Stats stats();
class WeatherScope {
 public:
  WeatherScope();
  ~WeatherScope();
  bool ready() const { return active_; }
  WeatherScope(const WeatherScope &) = delete;
  WeatherScope &operator=(const WeatherScope &) = delete;
 private:
  bool active_ = false;
};
// Same for the printer (MQTT) connect task: the TLS handshake allocates the
// session's large record buffers, which then live in PSRAM. Measured on the
// panel: with them in internal RAM, WebUI traffic during a live printer
// connection left < 1 KB of internal heap.
class MqttConnectScope {
 public:
  MqttConnectScope();
  ~MqttConnectScope();
  MqttConnectScope(const MqttConnectScope &) = delete;
  MqttConnectScope &operator=(const MqttConnectScope &) = delete;
 private:
  bool active_ = false;
};
#endif
}
