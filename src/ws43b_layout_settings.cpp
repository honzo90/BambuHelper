#include "ws43b_layout_settings.h"

#if defined(BOARD_IS_WS43B)
#include "config.h"
#include <Preferences.h>

static bool minimalLayout = false;
static uint32_t layoutRevision = 0;

bool ws43bMinimalLayout() { return minimalLayout; }
uint32_t ws43bLayoutRevision() { return layoutRevision; }

void loadWs43bLayout() {
  minimalLayout = false;
  layoutRevision = 0;
  Preferences local;
  if (!local.begin(NVS_NAMESPACE, true)) return;
  const uint16_t value = local.getUShort("w43_layout", 0x0100);
  local.end();
  // Absent, unknown or corrupt records fall back to Standard without writing NVS.
  if ((value & 0xFFFE) == 0x0100) minimalLayout = (value & 1) != 0;
}

bool saveWs43bLayout(bool minimal) {
  if (minimal == minimalLayout) return true;
  Preferences local;
  if (!local.begin(NVS_NAMESPACE, false)) return false;
  const uint16_t value = 0x0100 | (minimal ? 1 : 0);
  const bool saved = local.putUShort("w43_layout", value) == sizeof(value);
  local.end();
  if (!saved) return false;
  minimalLayout = minimal;
  ++layoutRevision;
  return true;
}
#endif
