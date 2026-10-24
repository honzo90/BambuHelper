#pragma once
#include <stdint.h>
// A single persisted language for the native panel and its WebUI.
// Codes are protocol identifiers: 0 = Polish (default), 1 = English, 2 = German.
bool ws43bPolish();
uint8_t ws43bLanguage();
const char* ws43bLanguageCode();
bool ws43bParseLanguage(const char* code, uint8_t& value);
uint32_t ws43bLanguageRevision();
void loadWs43bLanguage();
bool saveWs43bLanguage(uint8_t language);
inline const char* ws43bText(const char* pl, const char* en, const char* de = nullptr) {
  const uint8_t id = ws43bLanguage();
  if (id == 0) return pl;
  if (id == 2) return de ? de : en;
  return en;
}
