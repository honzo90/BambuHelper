#if defined(BOARD_IS_WS43B)
#include "ws43b_web_security.h"
#include "ws43b_web_policy.h"
#include "config.h"
#include "settings.h"
#include "wifi_manager.h"
#include <Preferences.h>
#include <WebServer.h>
#include <WiFi.h>

namespace ws43b_web_security {
namespace {
char storedPin[ws43b_web_policy::kPinMax + 1] = "";
const char* kPinKey = "w43_pin";
const char* kUser = "admin";
}  // namespace

const char* pin() { return storedPin; }

bool allow(WebServer& server, bool respond) {
  // Setup access point: only reachable with the AP password, and the captive
  // portal must answer the phone's foreign probe hosts. Nothing to check.
  if (isAPMode()) return true;

  const String host = server.hostHeader();
  const String ip = WiFi.localIP().toString();
  if (!ws43b_web_policy::hostAllowed(host.c_str(), ip.c_str(), netSettings.hostname)) {
    if (respond) server.send(403, "text/plain", "Forbidden host");
    return false;
  }
  const HTTPMethod method = server.method();
  if (method != HTTP_GET && method != HTTP_HEAD && method != HTTP_OPTIONS &&
      !ws43b_web_policy::originAllowed(server.header("Origin").c_str(),
                                       server.header("Referer").c_str(), host.c_str())) {
    if (respond) server.send(403, "text/plain", "Cross-site request refused");
    return false;
  }
  if (storedPin[0] && !server.authenticate(kUser, storedPin)) {
    if (respond) server.requestAuthentication(BASIC_AUTH, "BambuHelper");
    return false;
  }
  return true;
}

void begin(WebServer& server) {
  Preferences p;
  if (p.begin(NVS_NAMESPACE, true)) {
    const String saved = p.getString(kPinKey, "");
    p.end();
    if (ws43b_web_policy::pinValid(saved.c_str()))
      strlcpy(storedPin, saved.c_str(), sizeof(storedPin));
  }
  server.addMiddleware([](WebServer& s, Middleware::Callback next) {
    return allow(s) ? next() : true;
  });
}

void handlePinSave(WebServer& server) {
  const String value = server.arg("pin");
  if (!ws43b_web_policy::pinValid(value.c_str())) {
    server.send(400, "application/json", "{\"status\":\"error\",\"message\":\"PIN must be 4-8 digits\"}");
    return;
  }
  Preferences p;
  bool ok = p.begin(NVS_NAMESPACE, false);
  if (ok) {
    ok = value.length() ? p.putString(kPinKey, value) == value.length() : (p.remove(kPinKey), true);
    p.end();
  }
  if (!ok) {
    server.send(500, "application/json", "{\"status\":\"error\",\"message\":\"PIN could not be saved\"}");
    return;
  }
  strlcpy(storedPin, value.c_str(), sizeof(storedPin));
  server.send(200, "application/json", "{\"status\":\"ok\"}");
}

}  // namespace ws43b_web_security
#endif
