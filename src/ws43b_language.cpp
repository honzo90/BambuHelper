#include "config.h"
#if defined(BOARD_IS_WS43B)
#include "ws43b_language.h"
#include <Preferences.h>
static uint8_t language = 0;
static uint32_t revision = 0;
bool ws43bPolish() { return language == 0; }
uint32_t ws43bLanguageRevision() { return revision; }
void loadWs43bLanguage() {
  Preferences p;
  language = 0;
  if (!p.begin(NVS_NAMESPACE, true)) return;
  const uint16_t stored = p.getUShort("w43_lang", 0);
  p.end();
  if (stored <= 1) language = uint8_t(stored);
}
bool saveWs43bLanguage(uint8_t value) {
  if (value > 1) return false;
  if (value == language) return true;
  Preferences p;
  if (!p.begin(NVS_NAMESPACE, false)) return false;
  const bool ok = p.putUShort("w43_lang", value) == sizeof(uint16_t);
  p.end();
  if (!ok) return false;
  language = value;
  ++revision;
  return true;
}
#endif
