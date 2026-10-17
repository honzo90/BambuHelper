#include "ws43b_display_mode.h"

#if defined(BOARD_IS_WS43B)
#include "config.h"
#include <Preferences.h>

static bool advancedDisplay = false;
static uint32_t displayModeRevision = 0;

bool ws43bAdvancedDisplay() { return advancedDisplay; }
uint32_t ws43bDisplayModeRevision() { return displayModeRevision; }

void loadWs43bDisplayMode() {
  advancedDisplay = false;
  displayModeRevision = 0;
  Preferences local;
  if (!local.begin(NVS_NAMESPACE, true)) return;
  const uint16_t value = local.getUShort("w43_mode", 0x0100);
  local.end();
  // Absent, unknown or corrupt records fall back to Simple without writing NVS.
  if ((value & 0xFFFE) == 0x0100) advancedDisplay = (value & 1) != 0;
}

bool saveWs43bDisplayMode(bool advanced) {
  if (advanced == advancedDisplay) return true;
  Preferences local;
  if (!local.begin(NVS_NAMESPACE, false)) return false;
  const uint16_t value = 0x0100 | (advanced ? 1 : 0);
  const bool saved = local.putUShort("w43_mode", value) == sizeof(value);
  local.end();
  if (!saved) return false;
  advancedDisplay = advanced;
  ++displayModeRevision;
  return true;
}
#endif
