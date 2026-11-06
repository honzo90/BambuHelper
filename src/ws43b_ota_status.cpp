#if defined(BOARD_IS_WS43B)
#include "ws43b_ota_status.h"

#include <Arduino.h>
#include <Preferences.h>
#include <WiFi.h>
#include <esp_ota_ops.h>
#include <esp_system.h>

#include "config.h"
#include "settings.h"
#include "ws43b_hardware.h"
#include "ws43b_ota_health.h"

// Arduino confirms every image at boot unless this returns true; the
// firmware then confirms it from tick() once it has proven healthy.
extern "C" bool verifyRollbackLater() { return true; }

namespace {
bool pending = false;
bool brownout = false;
bool failedNow = false;
char failed[32] = "";
constexpr const char *kFailedKey = "ota_badver";

void sha8Of(const esp_partition_t *p, char *out) {
  esp_app_desc_t d;
  out[0] = 0;
  if (esp_ota_get_partition_description(p, &d) != ESP_OK) return;
  snprintf(out, 9, "%02x%02x%02x%02x", d.app_elf_sha256[0], d.app_elf_sha256[1],
           d.app_elf_sha256[2], d.app_elf_sha256[3]);
}

void confirm(const char *why) {
  if (!pending) return;
  if (esp_ota_mark_app_valid_cancel_rollback() == ESP_OK) {
    pending = false;
    Serial.printf("OTA: image confirmed (%s)\n", why);
  }
}
}  // namespace

namespace ws43b_ota_status {
void begin() {
  brownout = esp_reset_reason() == ESP_RST_BROWNOUT;
  esp_ota_img_states_t st;
  const esp_partition_t *run = esp_ota_get_running_partition();
  pending = run && esp_ota_get_state_partition(run, &st) == ESP_OK && st == ESP_OTA_IMG_PENDING_VERIFY;

  Preferences prefs;
  prefs.begin(NVS_NAMESPACE, false);
  strlcpy(failed, prefs.getString(kFailedKey, "").c_str(), sizeof(failed));
  if (const esp_partition_t *bad = esp_ota_get_last_invalid_partition()) {
    failedNow = true;
    char note[48], sha8[9], ver[32];
    sha8Of(bad, sha8);
    if (loadSlotVersionNote(bad->label, note, sizeof(note))) {
      ws43b_ota_health::noteVersion(note, sha8, ver, sizeof(ver));
      if (ver[0] && strcmp(ver, failed) != 0) {
        strlcpy(failed, ver, sizeof(failed));
        prefs.putString(kFailedKey, failed);
      }
    }
    Serial.printf("OTA: %s failed to boot and was rolled back\n", failed[0] ? failed : bad->label);
  }
  prefs.end();
  if (pending) Serial.println("OTA: new image on probation until it runs healthily");
}

void tick() {
  if (!pending) return;
  if (ws43b_ota_health::shouldConfirm(pending, millis(), ws43b::renderDiagnostics().frames,
                                      WiFi.status() == WL_CONNECTED))
    confirm("healthy");
}

void confirmBeforeRestart() {
  if (ws43b_ota_health::confirmBeforeRestart(pending, millis(), ws43b::renderDiagnostics().frames))
    confirm("restart requested");
}

bool pendingConfirm() { return pending; }
const char *failedVersion() { return failed; }
bool rolledBack() { return failedNow; }
bool brownoutReset() { return brownout; }
}  // namespace ws43b_ota_status
#endif
