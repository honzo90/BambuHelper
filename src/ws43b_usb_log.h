#pragma once

namespace ws43b_usb {
// HWCDC can wait twenty times per write when a host stops reading. Routine
// logs may be dropped; they must never delay Wi-Fi, MQTT or display updates.
constexpr unsigned LogTimeoutMs = 0;
constexpr unsigned ProtocolTimeoutMs = 100;  // pinned Arduino HWCDC default

template <class SerialPort>
void beginLogging(SerialPort &port) {
  port.setTxTimeoutMs(LogTimeoutMs);
}

// Improv replies are protocol packets, not disposable logs. Keep the original
// transmit allowance while handling a request, then restore nonblocking logs.
// Used only by the main loop; not a cross-task transport configuration API.
template <class SerialPort>
class ImprovReplyWindow {
 public:
  explicit ImprovReplyWindow(SerialPort &port) : port_(port) {
    port_.setTxTimeoutMs(ProtocolTimeoutMs);
  }
  ~ImprovReplyWindow() { beginLogging(port_); }
  ImprovReplyWindow(const ImprovReplyWindow &) = delete;
  ImprovReplyWindow &operator=(const ImprovReplyWindow &) = delete;
 private:
  SerialPort &port_;
};
}  // namespace ws43b_usb
