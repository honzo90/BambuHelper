#pragma once
#include <stdint.h>
// A single persisted language for the native panel and its WebUI.
// Codes are protocol identifiers: 0 = Polish (existing panel), 1 = English.
bool ws43bPolish();
uint32_t ws43bLanguageRevision();
void loadWs43bLanguage();
bool saveWs43bLanguage(uint8_t language);
inline const char* ws43bText(const char* pl, const char* en) {
  return ws43bPolish() ? pl : en;
}
