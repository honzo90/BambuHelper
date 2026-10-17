#include "ws43b_clock_settings.h"

#if defined(BOARD_IS_WS43B)
#include "settings.h"
#include "config.h"
#include <Preferences.h>

static Ws43bClockSettings clockSettings;

static bool validIdleMinutes(uint16_t minutes) {
  return minutes == 0 || minutes == 1 || minutes == 5 ||
         minutes == 15 || minutes == 30;
}

const Ws43bClockSettings& ws43bClockSettings() { return clockSettings; }

void loadWs43bClockSettings() {
  clockSettings = {};
  clockSettings.use24h = netSettings.use24h;
  Preferences local;
  if (!local.begin(NVS_NAMESPACE, true)) return;
  const uint16_t value = local.getUShort("w43_clock", 0);
  local.end();
  if ((value & 0xFF80) != 0x0100 || !validIdleMinutes(value & 31)) return;
  clockSettings.idleMinutes = value & 31;
  clockSettings.screenOff = (value & 32) != 0;
  clockSettings.use24h = (value & 64) != 0;
  netSettings.use24h = clockSettings.use24h;
}

bool saveWs43bClockSettings(uint16_t idleMinutes, bool screenOff, bool use24h) {
  if (!validIdleMinutes(idleMinutes)) return false;
  if (clockSettings.idleMinutes == idleMinutes &&
      clockSettings.screenOff == screenOff && clockSettings.use24h == use24h) return true;
  Preferences local;
  if (!local.begin(NVS_NAMESPACE, false)) return false;
  // A single versioned record commits the whole choice without touching
  // Wi-Fi, printer credentials or the general settings save path.
  const uint16_t value = 0x0100 | idleMinutes | (screenOff ? 32 : 0) | (use24h ? 64 : 0);
  const bool saved = local.putUShort("w43_clock", value) == sizeof(value);
  local.end();
  if (!saved) return false;
  clockSettings.idleMinutes = idleMinutes;
  clockSettings.screenOff = screenOff;
  clockSettings.use24h = use24h;
  ++clockSettings.revision;
  netSettings.use24h = use24h;
  return true;
}
#endif
