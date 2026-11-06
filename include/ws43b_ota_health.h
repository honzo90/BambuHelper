#pragma once
#include <stdint.h>
#include <stdio.h>
#include <string.h>

// Boot confirmation of a freshly installed OTA image (WS43B). The bootloader
// starts a new image in "pending verify" state; the firmware confirms it only
// after it has run healthily, otherwise the next reset rolls back to the
// previous slot. Pure policy, host-testable.
namespace ws43b_ota_health {

constexpr uint32_t kHealthyUptimeMs = 30000;   // running and drawing this long...
constexpr uint32_t kNoWifiUptimeMs = 180000;   // ...with Wi-Fi, or this long without it
constexpr uint32_t kMinFrames = 20;            // the display loop really draws
constexpr uint32_t kRestartUptimeMs = 10000;   // a user-requested restart after this confirms

// Confirm from the main loop. Wi-Fi is preferred proof, but a router that is
// down right after an update must not roll back a good image forever.
inline bool shouldConfirm(bool pending, uint32_t uptimeMs, uint32_t frames, bool wifiConnected) {
  if (!pending || frames < kMinFrames || uptimeMs < kHealthyUptimeMs) return false;
  return wifiConnected || uptimeMs >= kNoWifiUptimeMs;
}

// Confirm before a restart the user asked for (settings save, import, OTA):
// the image demonstrably works, and the restart must not undo the update.
inline bool confirmBeforeRestart(bool pending, uint32_t uptimeMs, uint32_t frames) {
  return pending && frames >= kMinFrames && uptimeMs >= kRestartUptimeMs;
}

// Version stored in the per-slot note "v4.1.1-alpha.2|1a2b3c4d", trusted only
// when the sha tag matches the image now in that slot. Writes "" otherwise.
inline void noteVersion(const char *note, const char *sha8, char *out, size_t cap) {
  if (!cap) return;
  out[0] = 0;
  if (!note || !sha8) return;
  const char *bar = strchr(note, '|');
  if (!bar || strcmp(bar + 1, sha8) != 0) return;
  size_t n = size_t(bar - note);
  if (n >= cap) n = cap - 1;
  memcpy(out, note, n);
  out[n] = 0;
}

// True when an online update URL points at the version that failed to boot.
inline bool urlIsFailedVersion(const char *url, const char *failed) {
  if (!url || !failed || !failed[0]) return false;
  char needle[64];
  const int n = snprintf(needle, sizeof(needle), "-%s-ota.bin", failed);
  if (n <= 0 || size_t(n) >= sizeof(needle)) return false;
  const size_t ul = strlen(url), nl = size_t(n);
  return ul >= nl && strcmp(url + ul - nl, needle) == 0;
}

}  // namespace ws43b_ota_health
