#include "cloud_login.h"

#if HAS_CLOUD_LOGIN

#include "bambu_cloud.h"
#include "settings.h"
#include "cloud_http_reader.h"

#include <WiFiClientSecure.h>
#include <ArduinoJson.h>
#include <esp_task_wdt.h>
#if BOARD_MQTT_ASYNC_CONNECT
#include <atomic>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#endif

extern const uint8_t rootca_crt_bundle_start[] asm("_binary_x509_crt_bundle_start");
#if defined(BOARD_IS_WS43B)
extern const uint8_t rootca_crt_bundle_end[] asm("_binary_x509_crt_bundle_end");
#endif

// ---------------------------------------------------------------------------
//  Session state
// ---------------------------------------------------------------------------
static CloudLoginState g_state = CLOUD_LOGIN_IDLE;
static String g_message;
static String g_jar;        // "name=value; name=value" carried between calls
static String g_csrf;       // bbl_csrf_token value, echoed in a header
static String g_tfaKey;
static String g_email;
static bool   g_neededTwoFactor = false;
// A refused code leaves the flow waiting on the same step, so the state alone
// cannot tell the portal whether to show the message as a prompt or a problem.
static bool   g_lastFailed = false;
#if BOARD_MQTT_ASYNC_CONNECT
// Main-loop generation: a manual sign-in/reset supersedes any detached reply.
static uint32_t storedRefreshGeneration = 0;
#endif

CloudLoginState cloudLoginState()   { return g_state; }
const char*     cloudLoginMessage() { return g_message.c_str(); }
bool            cloudLoginLastFailed() { return g_lastFailed; }

// Wait on a step: the message is an instruction, not a complaint.
static bool prompt(CloudLoginState state, const char* message) {
  g_state = state;
  g_message = message;
  g_lastFailed = false;
  return true;
}

static bool fail(const char* message, CloudLoginState state = CLOUD_LOGIN_FAILED) {
  g_state = state;
  g_message = message;
  g_lastFailed = true;
  return false;
}

void cloudLoginReset() {
#if BOARD_MQTT_ASYNC_CONNECT
  ++storedRefreshGeneration;
#endif
  g_state = CLOUD_LOGIN_IDLE;
  g_message = "";
  g_lastFailed = false;
  g_jar = "";
  g_csrf = "";
  g_tfaKey = "";
  g_email = "";
  g_neededTwoFactor = false;
}

// ---------------------------------------------------------------------------
//  Cookie jar
// ---------------------------------------------------------------------------

// Replace or append one "name=value" pair.
static void jarPut(const String& pair) {
  int eq = pair.indexOf('=');
  if (eq <= 0) return;
  // An empty value must never replace a good one. /api/auth/token answers some
  // sessions with `Set-Cookie: token=` and that used to wipe the real session
  // token the sign-in had just handed us.
  if (eq == (int)pair.length() - 1) return;
  String needle = pair.substring(0, eq) + "=";

  // Seek a real name boundary. "token=" also matches inside "bbl_csrf_token=",
  // and stopping at that first hit would leave the old cookie in place and
  // append a second one under the same name - the server then reads the stale
  // one, which is first in the jar.
  int at = g_jar.indexOf(needle);
  while (at > 0 && g_jar[at - 1] != ' ') at = g_jar.indexOf(needle, at + 1);

  if (at >= 0) {
    int end = g_jar.indexOf(';', at);
    if (end < 0) end = g_jar.length();
    else if (end + 2 <= (int)g_jar.length()) end += 2;   // eat "; " too
    g_jar = g_jar.substring(0, at) + g_jar.substring(end);
  }
  if (g_jar.length() > 0 && !g_jar.endsWith("; ")) g_jar += "; ";
  g_jar += pair;
}

// Take every cookie out of the collected Set-Cookie lines.
static void jarAbsorb(const String& setCookieLines) {
  int pos = 0;
  while (pos < (int)setCookieLines.length()) {
    int nl = setCookieLines.indexOf('\n', pos);
    if (nl < 0) nl = setCookieLines.length();
    String line = setCookieLines.substring(pos, nl);
    line.trim();
    int semi = line.indexOf(';');
    String pair = semi < 0 ? line : line.substring(0, semi);
    pair.trim();
    if (pair.indexOf('=') > 0) {
      jarPut(pair);
      if (pair.startsWith("bbl_csrf_token=")) g_csrf = pair.substring(15);
    }
    pos = nl + 1;
  }
}

static String jarValue(const char* name) {
  String needle = String(name) + "=";
  int at = g_jar.indexOf(needle);
  while (at > 0 && g_jar[at - 1] != ' ') {          // avoid matching a suffix
    at = g_jar.indexOf(needle, at + 1);
  }
  if (at < 0) return "";
  int start = at + needle.length();
  int end = g_jar.indexOf(';', start);
  if (end < 0) end = g_jar.length();
  return g_jar.substring(start, end);
}

// ---------------------------------------------------------------------------
//  Raw HTTPS
//
//  HTTPClient is unusable here: with duplicate response headers it keeps only
//  the last one (the append branch in the core's handleHeaderResponse is
//  commented out), and sign-in hands back two Set-Cookie headers at once.
// ---------------------------------------------------------------------------
struct CloudResponse {
  int    status = -1;
  String setCookies;
  String body;
  bool   truncated = false;   // body hit the cap, so it is not parseable JSON
};

// The account API answers the sign-in calls; the website host only carries the
// authenticator leg.
static const char* apiHost(CloudRegion region) {
  return region == REGION_CN ? "api.bambulab.cn" : "api.bambulab.com";
}
static const char* siteHost(CloudRegion region) {
  return region == REGION_CN ? "bambulab.cn" : "bambulab.com";
}

// `useSession` covers the website host's cookie ritual: send the jar and the
// CSRF header, and keep whatever Set-Cookie comes back. The account API needs
// none of it, and mixing the two has already cost one debugging round.
static bool cloudRequest(const char* host, const char* path, const char* method,
                         const char* body, bool useSession, CloudResponse& out,
                         size_t maxBody = 8192, bool feedWatchdog = true) {   // a login reply carries two JWTs

  WiFiClientSecure* tls = new (std::nothrow) WiFiClientSecure();
  if (!tls) { out.status = -2; return false; }

  // Stream timeout is milliseconds on current Arduino cores. HTTP framing is
  // handled below with an absolute deadline and yielding reads instead of the
  // version-dependent readStringUntil()/readBytes() helpers.
#if defined(BOARD_IS_WS43B)
  tls->setTimeout(5000); // Arduino 3.x: Stream milliseconds
#else
  tls->setTimeout(5);    // retain existing legacy-core socket configuration
#endif
  tls->setHandshakeTimeout(6);
#if defined(BOARD_IS_WS43B)
  tls->setCACertBundle(rootca_crt_bundle_start, rootca_crt_bundle_end - rootca_crt_bundle_start);
#else
  tls->setCACertBundle(rootca_crt_bundle_start);
#endif

  if (feedWatchdog) esp_task_wdt_reset();
#if defined(BOARD_IS_WS43B)
  bool connected = tls->connect(host, 443, 5000); // separate TCP/socket timeout
#else
  bool connected = tls->connect(host, 443);
#endif
  if (feedWatchdog) esp_task_wdt_reset();          // the handshake itself can eat several seconds
  if (!connected) {
    delete tls;
    out.status = -1;
    return false;
  }

  String req = String(method) + " " + path + " HTTP/1.1\r\n";
  req += "Host: ";        req += host; req += "\r\n";
  req += "User-Agent: bambu_network_agent/01.09.05.01\r\n";
  req += "Accept: application/json\r\n";
  req += "Content-Type: application/json\r\n";
  if (useSession && g_jar.length() > 0)  { req += "Cookie: ";           req += g_jar;  req += "\r\n"; }
  if (useSession && g_csrf.length() > 0) { req += "x-bbl-csrf-token: "; req += g_csrf; req += "\r\n"; }
  req += "Connection: close\r\n";
  if (body) { req += "Content-Length: "; req += strlen(body); req += "\r\n"; }
  req += "\r\n";
  if (body) req += body;
  const bool sent = tls->print(req) == req.length();
  const auto result = sent ? cloud_http::readResponse(*tls, out.status,
    out.setCookies, out.body, maxBody,
    [] { return uint32_t(millis()); },
    [feedWatchdog] { if (feedWatchdog) esp_task_wdt_reset(); delay(1); })
    : cloud_http::Result::Disconnected;
  out.truncated = result != cloud_http::Result::Complete;

  tls->stop();
  delete tls;
  if (feedWatchdog) esp_task_wdt_reset();

  // Never commit cookies or parse an incomplete/malformed token response.
  const bool complete = result == cloud_http::Result::Complete;
  if (complete && useSession) jarAbsorb(out.setCookies);
  return complete;
}

// ---------------------------------------------------------------------------
//  Flow steps
// ---------------------------------------------------------------------------

static CloudRegion currentRegion() {
  return printers[0].config.region;
}

// Every write to the site host is CSRF-guarded, so the cookie has to exist
// before the authenticator POST.
static bool ensureCsrf() {
  if (g_csrf.length() > 0) return true;
  CloudResponse r;
  cloudRequest(siteHost(currentRegion()), "/api/csrf", "GET", nullptr, true, r);
  if (g_csrf.length() == 0) {
    return fail("Could not reach the Bambu sign-in service.", g_state);
  }
  return true;
}

// Pull the error text the site returns, so the user sees Bambu's own wording
// ("Incorrect account or password.") instead of a status code.
static void setErrorFrom(const CloudResponse& r, const char* fallback) {
  JsonDocument doc;
  if (r.body.length() > 0 && !deserializeJson(doc, r.body) && doc["error"].is<const char*>()) {
    fail((const char*)doc["error"]);
  } else {
    fail(fallback);
  }
}

// Bambu spells the token differently depending on which of its own endpoints
// answered, and sometimes wraps the payload in "data".
static String extractToken(const String& body) {
  JsonDocument doc;
  if (body.length() == 0 || deserializeJson(doc, body)) return "";

  const char* keys[] = { "accessToken", "token" };
  for (size_t i = 0; i < 2; i++) {
    if (doc[keys[i]].is<const char*>())         return (const char*)doc[keys[i]];
    if (doc["data"][keys[i]].is<const char*>()) return (const char*)doc["data"][keys[i]];
  }
  return "";
}

static bool storeToken(const String& token) {
  if (token.length() == 0) {
    return fail("Signed in, but no token came back.");
  }
  // Every consumer reads the token back through a 1200-byte buffer, so storing
  // a longer one would truncate on load and surface later as an expired token
  // that never stops being expired.
  if (token.length() >= CLOUD_TOKEN_MAX) {
    Serial.printf("CLOUD: token is %d bytes, too long to store\n", token.length());
    return fail("Bambu's token is larger than this device can store.");
  }

  if (!saveCloudToken(token.c_str())) {
    // A sign-in that reports success but silently lost its token leaves the
    // user with nothing to debug - refuse loudly instead.
    return fail("Signed in, but the token could not be stored - settings storage is full. Factory-reset (export settings first) and try again.");
  }
  if (g_email.length() > 0) saveCloudEmail(g_email.c_str());

  // A stored password is only useful for silent re-login, which 2FA rules out.
  if (g_neededTwoFactor) clearCloudPassword();

  Serial.println("CLOUD: sign-in complete, token stored");
  prompt(CLOUD_LOGIN_OK, "Signed in.");
  return true;
}

// The account endpoint answers {account,password} and {account,code} with the
// same envelope: either the token, or which second factor it wants next.
static bool handleLoginReply(const CloudResponse& r) {
  if (r.status != 200) {
    setErrorFrom(r, "Sign-in was refused.");
    return false;
  }

  String token = extractToken(r.body);
  if (token.length() > 0) return storeToken(token);

  // A cut-off body parses as nothing, which would otherwise be reported as a
  // reply that carried no token - two very different problems.
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, r.body);
  if (r.truncated || err) {
    Serial.printf("CLOUD: login reply unreadable (%s), len=%d, truncated=%d\n",
                  err.c_str(), r.body.length(), r.truncated ? 1 : 0);
    return fail(r.truncated ? "Bambu's answer was too large to read."
                            : "Bambu's answer could not be read.");
  }

  const char* loginType = doc["loginType"].as<const char*>();
  if (!loginType) loginType = "";
  const char* tfaKey = doc["tfaKey"].as<const char*>();
  if (!tfaKey) tfaKey = "";

  // Measured on a TOTP account: Bambu answers the challenge with a tfaKey and
  // an EMPTY loginType, so keying off loginType alone never enters this branch.
  // The handed-out tfaKey is the challenge; that is what decides.
  if (strcmp(loginType, "tfa") == 0 || (loginType[0] == '\0' && tfaKey[0] != '\0')) {
    if (tfaKey[0] == '\0') {
      // Without the key the verify call can only ever be refused, so asking for
      // a code would trap the user in a step that cannot succeed. Still record
      // that a second factor was demanded - a stored password cannot satisfy
      // this account either, and the refresh path reads that flag to stop
      // retrying a login that can only fail.
      g_neededTwoFactor = true;
      Serial.println("CLOUD: 2FA demanded but no tfaKey came with it");
      return fail("Bambu asked for a 2FA code but sent no challenge. Try again.");
    }
    g_tfaKey = tfaKey;
    g_neededTwoFactor = true;
    return prompt(CLOUD_LOGIN_NEED_TFA,
                  "Enter the 6-digit code from your authenticator app.");
  }
  if (strcmp(loginType, "verifyCode") == 0) {
    g_neededTwoFactor = true;
    return prompt(CLOUD_LOGIN_NEED_EMAIL_CODE, "Enter the code Bambu just emailed you.");
  }

  // Describe the envelope without printing it: strings are reported by length
  // only, since any of them may be a credential. Numbers, booleans and the two
  // enum-ish routing fields are safe to show and are what actually explains a
  // refusal.
  String fields;
  for (JsonPair kv : doc.as<JsonObject>()) {
    if (fields.length() > 0) fields += ' ';
    fields += kv.key().c_str();
    fields += '=';

    const char* key = kv.key().c_str();
    if (kv.value().isNull()) {
      fields += "null";
    } else if (kv.value().is<JsonObjectConst>()) {
      fields += "{...}";        // never serialize a subtree - it may hold a token
    } else if (kv.value().is<JsonArrayConst>()) {
      fields += "[...]";
    } else if (kv.value().is<const char*>()) {
      if (strcmp(key, "loginType") == 0 || strcmp(key, "accessMethod") == 0) {
        fields += '"';
        fields += kv.value().as<const char*>();
        fields += '"';
      } else {
        fields += "len";
        fields += strlen(kv.value().as<const char*>());
      }
    } else {
      fields += kv.value().as<String>();
    }
  }
  Serial.printf("CLOUD: login reply had no token, len=%d, fields: %s\n",
                r.body.length(), fields.c_str());

  return fail("Bambu accepted the sign-in but sent no token.");
}

bool cloudLoginWithPassword(const char* email, const char* password) {
  cloudLoginReset();
  g_email = email;

  JsonDocument body;
  body["account"]  = email;
  body["password"] = password;
  String payload;
  serializeJson(body, payload);

  CloudResponse r;
  if (!cloudRequest(apiHost(currentRegion()), "/v1/user-service/user/login", "POST",
                    payload.c_str(), false, r)) {
    return fail("Could not reach the Bambu sign-in service.");
  }
  Serial.printf("CLOUD: user/login HTTP %d, len=%d\n", r.status, r.body.length());
  return handleLoginReply(r);
}

bool cloudLoginRequestEmailCode(const char* email) {
  cloudLoginReset();
  g_email = email;
  g_neededTwoFactor = true;      // this path never has a password to store

  JsonDocument body;
  body["email"] = email;
  body["type"]  = "codeLogin";
  String payload;
  serializeJson(body, payload);

  CloudResponse r;
  if (!cloudRequest(apiHost(currentRegion()), "/v1/user-service/user/sendemail/code",
                    "POST", payload.c_str(), false, r)) {
    return fail("Could not reach the Bambu sign-in service.");
  }
  Serial.printf("CLOUD: sendemail/code HTTP %d\n", r.status);

  if (r.status != 200) {
    setErrorFrom(r, "Bambu refused to send a code to that address.");
    return false;
  }

  return prompt(CLOUD_LOGIN_NEED_EMAIL_CODE, "Enter the code Bambu just emailed you.");
}

bool cloudLoginSubmitCode(const char* code) {
#if BOARD_MQTT_ASYNC_CONNECT
  ++storedRefreshGeneration;
#endif
  const CloudLoginState keep = g_state;   // so a mistyped code can be retried
  if (keep != CLOUD_LOGIN_NEED_TFA && keep != CLOUD_LOGIN_NEED_EMAIL_CODE) {
    return fail("Nothing is waiting for a code - start again.", keep);
  }

  // The authenticator leg is the one Bambu keeps on the website host, session
  // cookies and all; the emailed code goes back to the account endpoint.
  const bool tfa = (keep == CLOUD_LOGIN_NEED_TFA);
  if (tfa && !ensureCsrf()) {
    g_state = keep;
    return false;
  }

  JsonDocument body;
  if (tfa) {
    body["tfaKey"]  = g_tfaKey;
    body["tfaCode"] = code;
  } else {
    body["account"] = g_email;
    body["code"]    = code;
  }
  String payload;
  serializeJson(body, payload);

  const char* host = tfa ? siteHost(currentRegion()) : apiHost(currentRegion());
  const char* path = tfa ? "/api/sign-in/tfa" : "/v1/user-service/user/login";

  CloudResponse r;
  if (!cloudRequest(host, path, "POST", payload.c_str(), tfa, r)) {
    // A blip on the way out must not throw away a code the user still holds.
    return fail("Could not reach the Bambu sign-in service - try the code again.", keep);
  }
  Serial.printf("CLOUD: %s HTTP %d, len=%d\n", path, r.status, r.body.length());

  if (r.status != 200) {
    setErrorFrom(r, "That code was not accepted.");
    g_state = keep;
    return false;
  }

  if (!tfa) {
    bool ok = handleLoginReply(r);
    // handleLoginReply describes a finished sign-in; back on the code step that
    // reads as a contradiction, so say what the user can act on.
    if (!ok) fail("That code was not accepted.", keep);
    return ok;
  }

  // The site answers the authenticator leg with a session cookie, and only
  // sometimes echoes the token in the body.
  String token = extractToken(r.body);
  if (token.length() == 0) token = jarValue("token");
  if (!storeToken(token)) {
    g_state = keep;
    return false;
  }
  return true;
}

bool cloudLoginCanAutoRefresh() {
  char pw[CLOUD_PASSWORD_MAX + 1]{};
  const bool stored = loadCloudPassword(pw, sizeof(pw));
  memset(pw, 0, sizeof(pw));
  return stored;
}

static bool finishStoredRefresh(bool ok) {
  // Key this on "a second factor was demanded", not on the call's return value:
  // a malformed 2FA challenge fails the call outright, and testing `ok` there
  // would keep the password and re-run the same doomed login every 15 minutes.
  // A transport failure sets no such flag, so a Wi-Fi blip still keeps it.
  if (g_neededTwoFactor && g_state != CLOUD_LOGIN_OK) {
    // A code prompt cannot be answered without a human, so a 2FA account can
    // never refresh silently. Drop the password rather than keep asking - and
    // clear the pending step, or the portal would poll this background attempt
    // and pop a code prompt at somebody who never asked to sign in.
    Serial.println("CLOUD: account asks for 2FA - stored password cannot refresh it");
    clearCloudPassword();
    cloudLoginReset();
    g_state = CLOUD_LOGIN_FAILED;
    g_message = "The saved password needs a 2FA code, so the token could not be renewed. Sign in again.";
    return false;
  }
  return ok && g_state == CLOUD_LOGIN_OK;
}

bool cloudLoginRefreshStored() {
  // Somebody is standing at the portal holding a code. This runs from the MQTT
  // reconnect path and would reset the session out from under them, so their
  // code would come back "nothing is waiting for a code".
  if (g_state == CLOUD_LOGIN_NEED_TFA || g_state == CLOUD_LOGIN_NEED_EMAIL_CODE) {
    Serial.println("CLOUD: skipping background refresh, a sign-in is waiting for a code");
    return false;
  }

  char email[CLOUD_EMAIL_MAX + 1];
  char pw[CLOUD_PASSWORD_MAX + 1];
  if (!loadCloudEmail(email, sizeof(email)) || !loadCloudPassword(pw, sizeof(pw))) {
    return false;
  }

  Serial.println("CLOUD: refreshing token with the stored password");
  bool ok = cloudLoginWithPassword(email, pw);
  memset(pw, 0, sizeof(pw));

  return finishStoredRefresh(ok);
}

#if BOARD_MQTT_ASYNC_CONNECT
// One detached HTTPS request. Only this task touches its response; no session,
// settings, NVS, printer state or UI operations occur in the worker. Completion
// is published once, then all parsing/persistence is done on the MQTT/UI loop.
struct StoredRefreshJob {
  PrinterConfig config{};
  uint8_t slot = 0;
  uint32_t generation = 0;
  char email[CLOUD_EMAIL_MAX + 1]{};
  char password[CLOUD_PASSWORD_MAX + 1]{};
  char token[CLOUD_TOKEN_MAX]{};
  CloudResponse response;
  bool reachedService = false;
  std::atomic<bool> done{false};
};
static StoredRefreshJob storedRefreshJob;
static bool storedRefreshBusy = false; // main loop only

static void storedRefreshWorker(void*) {
  auto& j = storedRefreshJob;
  // Destroy local JSON/payload before publishing completion or deleting task.
  {
    JsonDocument body;
    body["account"] = j.email;
    body["password"] = j.password;
    String payload;
    serializeJson(body, payload);
    // No cookies/global session access; this task is not registered with WDT.
    j.reachedService = cloudRequest(apiHost(j.config.region),
      "/v1/user-service/user/login", "POST", payload.c_str(), false,
      j.response, 8192, false);
  }
  j.done.store(true, std::memory_order_release);
  vTaskDelete(nullptr);
}

static void clearStoredRefreshJob() {
  auto& j = storedRefreshJob;
  memset(j.password, 0, sizeof j.password);
  memset(j.token, 0, sizeof j.token);
  memset(j.email, 0, sizeof j.email);
  j.config = {};
  j.response = {};
  storedRefreshBusy = false;
}

bool cloudLoginStoredRefreshPending() { return storedRefreshBusy; }

void cloudLoginCancelStoredRefresh(uint8_t slot) {
  if (storedRefreshBusy && storedRefreshJob.slot == slot)
    ++storedRefreshGeneration; // never destroy a worker-owned object/client
}

bool cloudLoginStartStoredRefresh(uint8_t slot) {
  if (storedRefreshBusy || slot >= MAX_ACTIVE_PRINTERS ||
      !isCloudMode(printers[slot].config.mode) ||
      g_state == CLOUD_LOGIN_NEED_TFA || g_state == CLOUD_LOGIN_NEED_EMAIL_CODE)
    return false;
  auto& j = storedRefreshJob;
  j.config = printers[slot].config;
  j.slot = slot;
  j.generation = storedRefreshGeneration;
  if (!loadCloudEmail(j.email, sizeof j.email) ||
      !loadCloudPassword(j.password, sizeof j.password) ||
      !loadCloudToken(j.token, sizeof j.token)) {
    clearStoredRefreshJob();
    return false;
  }
  j.reachedService = false;
  j.response = {};
  j.done.store(false, std::memory_order_relaxed);
  storedRefreshBusy = true;
  if (xTaskCreatePinnedToCore(storedRefreshWorker, "cloud_refresh", 8192,
                            nullptr, 1, nullptr, 0) != pdPASS) {
    clearStoredRefreshJob();
    return false;
  }
  return true;
}

void cloudLoginServiceStoredRefresh() {
  if (!storedRefreshBusy || !storedRefreshJob.done.load(std::memory_order_acquire)) return;
  auto& j = storedRefreshJob;
  const auto& config = printers[j.slot].config;
  // A changed/logout/pasted token must never be overwritten by an old reply.
  // Reset and slot lifecycle also invalidate ABA changes made through the UI.
  char email[CLOUD_EMAIL_MAX + 1]{};
  char password[CLOUD_PASSWORD_MAX + 1]{};
  char token[CLOUD_TOKEN_MAX]{};
  const bool current = j.generation == storedRefreshGeneration &&
    config.mode == j.config.mode && config.region == j.config.region &&
    strcmp(config.serial, j.config.serial) == 0 &&
    strcmp(config.cloudUserId, j.config.cloudUserId) == 0 &&
    loadCloudEmail(email, sizeof email) && strcmp(email, j.email) == 0 &&
    loadCloudPassword(password, sizeof password) && strcmp(password, j.password) == 0 &&
    loadCloudToken(token, sizeof token) && strcmp(token, j.token) == 0;
  memset(password, 0, sizeof password);
  memset(token, 0, sizeof token);
  if (current) {
    cloudLoginReset();
    g_email = j.email;
    const bool ok = j.reachedService ? handleLoginReply(j.response)
      : fail("Could not reach the Bambu sign-in service.");
    const bool renewed = finishStoredRefresh(ok);
    Serial.printf("CLOUD: background token renewal %s\n", renewed ? "complete" : "failed");
  }
  clearStoredRefreshJob();
}
#endif // BOARD_MQTT_ASYNC_CONNECT

// ---------------------------------------------------------------------------
//  Self-test - proves the path without touching a real account
// ---------------------------------------------------------------------------
void cloudLoginSelfTest(String& out) {
  cloudLoginReset();

  // Throwaway credentials: reaching "Incorrect account or password." proves the
  // account endpoint answers this device. A multi-kilobyte HTML body instead
  // means Cloudflare stepped in - historically rate limiting, so wait it out
  // before reading anything more into it.
  CloudResponse login;
  bool ok1 = cloudRequest(apiHost(currentRegion()), "/v1/user-service/user/login", "POST",
                          "{\"account\":\"probe@bambuhelper.invalid\","
                          "\"password\":\"not-a-real-password\"}", false, login, 1024);

  // The authenticator leg needs this cookie, so it is worth reporting too.
  CloudResponse csrf;
  bool ok2 = cloudRequest(siteHost(currentRegion()), "/api/csrf", "GET", nullptr, true, csrf);

  out = "{\"login_http\":";
  out += ok1 ? login.status : -1;
  out += ",\"login_len\":";
  out += login.body.length();
  out += ",\"login_body\":\"";
  for (size_t i = 0; i < login.body.length() && i < 200; i++) {
    char c = login.body[i];
    if (c == '"' || c == '\\') out += '\\';
    if ((uint8_t)c >= 0x20) out += c;
  }
  out += "\",\"csrf_http\":";
  out += ok2 ? csrf.status : -1;
  out += ",\"have_csrf\":";
  out += g_csrf.length() > 0 ? "true" : "false";
  out += "}";

  cloudLoginReset();
}

#endif // HAS_CLOUD_LOGIN
