#pragma once
// Boot health of the running OTA image and the reason for the last reset
// (WS43B). See include/ws43b_ota_health.h for the policy.
namespace ws43b_ota_status {
void begin();                 // once in setup(), after recordBootSlotVersion()
void tick();                  // every loop(): confirms a healthy new image
void confirmBeforeRestart();  // before a restart the user asked for
bool pendingConfirm();        // the running image is still on probation
const char *failedVersion();  // last version that failed to boot, or ""
bool rolledBack();            // an image in the other slot failed to boot
bool brownoutReset();         // the last reset was a supply brownout
}
