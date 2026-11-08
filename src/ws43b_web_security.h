#pragma once
// WebUI access gate for the 4.3B panel; policy in ws43b_web_policy.h.
#if defined(BOARD_IS_WS43B)
class WebServer;

namespace ws43b_web_security {
// Load the PIN and install the gate as server middleware. Call before server.begin().
void begin(WebServer& server);
// Full check for the current request. On refusal it returns false and, with
// respond, sends 403/401. Upload handlers must call it (respond=false) at
// UPLOAD_FILE_START: uploads are parsed before middleware runs, so the
// middleware alone would not stop the first bytes; it answers afterwards.
bool allow(WebServer& server, bool respond = true);
// PIN for the panel's "Language and WebUI" screen; "" when off.
const char* pin();
// POST /security/pin  (pin=<4-8 digits> or empty to turn it off)
void handlePinSave(WebServer& server);
}  // namespace ws43b_web_security
#endif
