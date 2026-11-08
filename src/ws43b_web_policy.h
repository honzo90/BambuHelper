#pragma once
// Pure WebUI access policy (no Arduino types) so host tests can cover it.
//  - Host check: the request must name this panel (IP, hostname, hostname.local).
//    Stops DNS rebinding, where a web page re-points its own domain at the panel.
//  - Origin check: a browser request that changes state must come from a page
//    served by this panel. Stops cross-site requests (CSRF) from any web page a
//    device in the LAN happens to open. Tools without Origin/Referer still work.
//  - Optional PIN (HTTP Basic, user "admin"): 4-8 digits, empty = off.
#include <stddef.h>
#include <string.h>

namespace ws43b_web_policy {

inline char lower(char c) { return (c >= 'A' && c <= 'Z') ? char(c - 'A' + 'a') : c; }

// Case-insensitive compare of a[0..n) with the whole of b.
inline bool equalsN(const char* a, size_t n, const char* b) {
  if (!a || !b || strlen(b) != n) return false;
  for (size_t i = 0; i < n; ++i)
    if (lower(a[i]) != lower(b[i])) return false;
  return true;
}

// Length of the host part of "host[:port]".
inline size_t hostLength(const char* authority) {
  size_t n = 0;
  while (authority[n] && authority[n] != ':' && authority[n] != '/') ++n;
  return n;
}

// Host header names this panel. Empty Host (HTTP/1.0 tools) is allowed.
inline bool hostAllowed(const char* host, const char* ip, const char* hostname) {
  if (!host || !host[0]) return true;
  const size_t n = hostLength(host);
  if (host[n] && host[n] != ':') return false;
  if (ip && ip[0] && equalsN(host, n, ip)) return true;
  if (!hostname || !hostname[0]) return false;
  if (equalsN(host, n, hostname)) return true;
  // hostname + a local-only suffix (mDNS or names handed out by home routers).
  // Public suffixes stay refused: a rebinding attacker can register those.
  static const char* const kLocalSuffixes[] = {".local", ".lan", ".home", ".home.arpa",
                                               ".localdomain", ".internal", ".fritz.box"};
  const size_t h = strlen(hostname);
  if (n <= h || !equalsN(host, h, hostname)) return false;
  for (const char* suffix : kLocalSuffixes)
    if (equalsN(host + h, n - h, suffix)) return true;
  return false;
}

// "http://host[:port]/path" -> pointer to "host[:port]...", or nullptr.
inline const char* authorityOf(const char* url) {
  if (!url) return nullptr;
  const char* p = strstr(url, "://");
  return p ? p + 3 : nullptr;
}

// Same authority (host and port) as the Host header.
inline bool sameAuthority(const char* url, const char* host) {
  const char* a = authorityOf(url);
  if (!a || !host) return false;
  size_t n = 0;
  while (a[n] && a[n] != '/' && a[n] != '?' && a[n] != '#') ++n;
  return equalsN(a, n, host);
}

// A state-changing request may run: no browser origin info (curl, scripts),
// or Origin/Referer pointing at this panel. "Origin: null" is refused.
inline bool originAllowed(const char* origin, const char* referer, const char* host) {
  if (origin && origin[0]) return sameAuthority(origin, host);
  if (referer && referer[0]) return sameAuthority(referer, host);
  return true;
}

constexpr size_t kPinMin = 4, kPinMax = 8;

// Empty disables the PIN; otherwise 4-8 ASCII digits.
inline bool pinValid(const char* pin) {
  if (!pin) return false;
  const size_t n = strlen(pin);
  if (n == 0) return true;
  if (n < kPinMin || n > kPinMax) return false;
  for (size_t i = 0; i < n; ++i)
    if (pin[i] < '0' || pin[i] > '9') return false;
  return true;
}

}  // namespace ws43b_web_policy
