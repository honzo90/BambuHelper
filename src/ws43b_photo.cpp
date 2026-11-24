#if defined(BOARD_IS_WS43B)
// SD.h must come before LovyanGFX (display_ui.h): LovyanGFX only provides its
// fs::File image loaders when FS_H is already defined.
#include <SD.h>
#include <SPI.h>
#include <FS.h>
#include <WebServer.h>
#include <Preferences.h>
#include <esp_heap_caps.h>
#include <new>
#include <stdlib.h>
#include <string.h>
#include "config.h"
#include "display_ui.h"
#include "ws43b_hardware.h"
#include "ws43b_photo.h"
#include "ws43b_web_security.h"
#include "ws43b_language.h"

namespace {
using namespace ws43b_photo;

// TF slot wiring from the manufacturer's 03_SD_Test example. The card is the
// only device on this SPI host; CS is CH422G EXIO4 (ws43b::selectSdCard()).
constexpr int SD_SCK = 12, SD_MISO = 13, SD_MOSI = 11;
constexpr uint8_t SD_NO_CS_GPIO = 0xFF;  // the example's SD_SS -1
constexpr const char *DIR = "/images";
constexpr const char *UPLOAD_TMP = "/images/.upload.tmp";
constexpr uint32_t MOUNT_RETRY_MS = 15000, RESCAN_MS = 300000;

Settings settings;
SPIClass sdSpi(FSPI);
bool spiStarted = false, mounted = false;
uint32_t nextMountMs = 0;
bool listDirty = true;
uint32_t listedMs = 0;
// Name table in PSRAM: 200 x 48 bytes, sorted so the slideshow order is stable.
char (*names)[kNameMax] = nullptr;
uint16_t count = 0;
lgfx::LGFX_Sprite *slide = nullptr;
bool slideReady = false;
uint32_t revision = 0;
// Bumped when the set of pictures may have changed (upload, delete, a
// different list after a rescan); one unchanged picture is decoded once.
uint32_t listRevision = 0, decodedListRevision = 0, listHash = 0;
Slideshow show;

void unmount() {
  if (mounted) SD.end();
  mounted = false;
  count = 0;
  slideReady = false;
  listDirty = true;
}

bool mount(uint32_t now, bool force = false) {
  if (mounted) {
    if (SD.cardType() != CARD_NONE) return true;
    Serial.println("PHOTO sd: card removed");
    unmount();
  }
  if (!force && int32_t(now - nextMountMs) < 0) return false;
  nextMountMs = now + MOUNT_RETRY_MS;
  if (!ws43b::selectSdCard()) {
    Serial.println("PHOTO sd: chip select (CH422G EXIO4) failed");
    return false;
  }
  if (!spiStarted) {
    sdSpi.setHwCs(false);
    sdSpi.begin(SD_SCK, SD_MISO, SD_MOSI, -1);
    spiStarted = true;
  }
  // 20 MHz keeps a 2-4 MB photo read short; some cards mount only at the
  // library default of 4 MHz.
  uint32_t hz = 20000000;
  mounted = SD.begin(SD_NO_CS_GPIO, sdSpi, hz, "/sd", 2);
  if (!mounted) {
    hz = 4000000;
    mounted = SD.begin(SD_NO_CS_GPIO, sdSpi, hz, "/sd", 2);
  }
  Serial.printf("PHOTO sd: %s (%lu Hz)\n", mounted ? "mounted" : "no card", (unsigned long)hz);
  if (mounted) listDirty = true;
  return mounted;
}

void scan(uint32_t now) {
  listDirty = false;
  listedMs = now;
  count = 0;
  if (!names) {
    names = static_cast<char (*)[kNameMax]>(heap_caps_malloc(kMaxFiles * kNameMax, MALLOC_CAP_SPIRAM));
    if (!names) return;
  }
  File dir = SD.open(DIR);
  if (!dir || !dir.isDirectory()) {
    if (dir) dir.close();
    SD.mkdir(DIR);
    return;
  }
  for (File f = dir.openNextFile(); f && count < kMaxFiles; f = dir.openNextFile()) {
    const char *name = f.name();
    if (!f.isDirectory() && safeName(name) && sizeAllowed(format(name), uint32_t(f.size()))) {
      strncpy(names[count], name, kNameMax - 1);
      names[count][kNameMax - 1] = 0;
      ++count;
    }
    f.close();
  }
  dir.close();
  qsort(names, count, kNameMax,
        [](const void *a, const void *b) { return strcmp(static_cast<const char *>(a), static_cast<const char *>(b)); });
  uint32_t hash = 2166136261u;  // FNV-1a over the sorted names
  for (uint16_t i = 0; i < count; ++i)
    for (const char *c = names[i]; *c; ++c) hash = (hash ^ uint8_t(*c)) * 16777619u;
  if (hash != listHash) {
    listHash = hash;
    ++listRevision;
  }
  Serial.printf("PHOTO list: %u file(s) in %s\n", unsigned(count), DIR);
}

bool allocate() {
  if (slide) return true;
  slide = new (std::nothrow) lgfx::LGFX_Sprite(tft_ptr);
  if (!slide) return false;
  slide->setPsram(true);
  slide->setColorDepth(16);
  if (!slide->createSprite(kScreenW, kScreenH)) {
    Serial.println("PHOTO: no PSRAM for the 800x480 slide");
    delete slide;
    slide = nullptr;
    return false;
  }
  return true;
}

bool decode(const char *name) {
  char path[kNameMax + 16];
  snprintf(path, sizeof(path), "%s/%s", DIR, name);
  File f = SD.open(path, FILE_READ);
  if (!f) return false;
  const Format fmt = format(name);
  const uint32_t size = uint32_t(f.size());
  uint16_t w = 0, h = 0;
  auto read = [&f](uint32_t offset, uint8_t *buffer, size_t n) {
    return f.seek(offset) && f.read(buffer, n) == n;
  };
  if (!sizeAllowed(fmt, size) || !imageSize(fmt, read, size, w, h) || !dimensionsAllowed(w, h)) {
    f.close();
    Serial.printf("PHOTO skip %s: unsupported header or size\n", name);
    return false;
  }
  f.seek(0);
  const float z = zoom(w, h, settings.fill);
  const uint32_t started = millis();
  slide->fillScreen(0);
  const bool ok = fmt == Format::Jpeg
    ? slide->drawJpg(&f, 0, 0, kScreenW, kScreenH, 0, 0, z, z, lgfx::datum_t::middle_center)
    : slide->drawPng(&f, 0, 0, kScreenW, kScreenH, 0, 0, z, z, lgfx::datum_t::middle_center);
  f.close();
  Serial.printf("PHOTO decode %s %ux%u zoom %.2f %s %lu ms\n", name, unsigned(w), unsigned(h),
                double(z), ok ? "ok" : "FAILED", (unsigned long)(millis() - started));
  return ok;
}

void imagePath(char *out, size_t cap, const char *name) { snprintf(out, cap, "%s/%s", DIR, name); }

// ---- Web --------------------------------------------------------------------
void sendStatus(WebServer &server, int code, const char *message) {
  String body = code == 200 ? String("{\"status\":\"ok\"}")
                            : String("{\"status\":\"error\",\"message\":\"") + message + "\"}";
  server.send(code, "application/json", body);
}

// Streamed by hand: up to 200 entries would otherwise need ~20 KB of
// internal heap for a JSON document. Names are safeName() (no quotes).
void handleList(WebServer &server) {
  server.sendHeader("Cache-Control", "no-store");
  mount(millis());
  char head[256];
  snprintf(head, sizeof(head),
           "{\"enabled\":%s,\"interval\":%u,\"corner\":%u,\"fill\":%s,\"card\":%s,"
           "\"total_mb\":%lu,\"used_mb\":%lu,\"files\":[",
           settings.enabled ? "true" : "false", unsigned(kIntervals[settings.interval & 3]),
           unsigned(settings.corner & 3), settings.fill ? "true" : "false", mounted ? "true" : "false",
           mounted ? (unsigned long)(SD.totalBytes() >> 20) : 0UL,
           mounted ? (unsigned long)(SD.usedBytes() >> 20) : 0UL);
  server.setContentLength(CONTENT_LENGTH_UNKNOWN);
  server.send(200, "application/json", head);
  if (mounted) {
    File dir = SD.open(DIR);
    unsigned listed = 0;
    if (dir && dir.isDirectory()) {
      for (File f = dir.openNextFile(); f && listed < kMaxFiles; f = dir.openNextFile()) {
        const char *name = f.name();
        if (!f.isDirectory() && safeName(name)) {
          char entry[kNameMax + 64];
          snprintf(entry, sizeof(entry), "%s{\"name\":\"%s\",\"size\":%lu,\"ok\":%s}", listed ? "," : "",
                   name, (unsigned long)f.size(),
                   sizeAllowed(format(name), uint32_t(f.size())) ? "true" : "false");
          server.sendContent(entry);
          ++listed;
        }
        f.close();
      }
    }
    if (dir) dir.close();
  }
  server.sendContent("]}");
  server.sendContent("");
}

void handleSettings(WebServer &server) {
  server.sendHeader("Cache-Control", "no-store");
  const String enabled = server.arg("enabled"), corner = server.arg("corner"), fit = server.arg("fit");
  const int interval = intervalIndex(unsigned(server.arg("interval").toInt()));
  if (server.args() != 4 || (enabled != "0" && enabled != "1") || interval < 0 ||
      corner.length() != 1 || corner[0] < '0' || corner[0] > '3' || (fit != "fit" && fit != "fill")) {
    sendStatus(server, 400, ws43bText("Wybierz włączenie, interwał, narożnik i dopasowanie.", "Choose on/off, interval, corner and fit.", "Wähle An/Aus, Intervall, Ecke und Größe."));
    return;
  }
  Settings next;
  next.enabled = enabled == "1";
  next.interval = uint8_t(interval);
  next.corner = uint8_t(corner[0] - '0');
  next.fill = fit == "fill";
  if (!saveWs43bPhotoSettings(next)) {
    sendStatus(server, 500, ws43bText("Nie zapisano ustawień zdjęć. Spróbuj ponownie.", "Photo settings were not saved. Try again.", "Foto-Einstellungen nicht gespeichert. Versuch es erneut."));
    return;
  }
  sendStatus(server, 200, nullptr);
}

void handleDelete(WebServer &server) {
  server.sendHeader("Cache-Control", "no-store");
  const String name = server.arg("name");
  if (server.args() != 1 || !safeName(name.c_str())) {
    sendStatus(server, 400, ws43bText("Nieprawidłowa nazwa pliku.", "Invalid file name.", "Ungültiger Dateiname."));
    return;
  }
  if (!mount(millis(), true)) {
    sendStatus(server, 503, ws43bText("Brak karty pamięci.", "No memory card.", "Keine Speicherkarte."));
    return;
  }
  char path[kNameMax + 16];
  imagePath(path, sizeof(path), name.c_str());
  if (!SD.remove(path)) {
    sendStatus(server, 404, ws43bText("Nie znaleziono pliku.", "File not found.", "Datei nicht gefunden."));
    return;
  }
  listDirty = true;
  ++listRevision;
  sendStatus(server, 200, nullptr);
}

void handleFile(WebServer &server) {
  const String name = server.arg("name");
  if (!safeName(name.c_str()) || !mount(millis())) {
    server.send(404, "text/plain", "Not found");
    return;
  }
  char path[kNameMax + 16];
  imagePath(path, sizeof(path), name.c_str());
  File f = SD.open(path, FILE_READ);
  if (!f) {
    server.send(404, "text/plain", "Not found");
    return;
  }
  server.sendHeader("Cache-Control", "no-store");
  server.streamFile(f, format(name.c_str()) == Format::Png ? "image/png" : "image/jpeg");
  f.close();
}

File uploadFile;
bool uploadOk = false;
const char *uploadError = nullptr;
uint32_t uploadBytes = 0;
char uploadName[kNameMax] = {};

void dropUpload(const char *error) {
  if (uploadFile) uploadFile.close();
  SD.remove(UPLOAD_TMP);
  uploadError = error;
}

void handleUpload(WebServer &server) {
  HTTPUpload &upload = server.upload();
  if (upload.status == UPLOAD_FILE_START) {
    uploadOk = false;
    uploadError = nullptr;
    uploadBytes = 0;
    uploadName[0] = 0;
    // Uploads are parsed before middleware runs: check access before writing.
    if (!ws43b_web_security::allow(server, false)) {
      uploadError = ws43bText("Brak dostępu.", "Not allowed.", "Nicht erlaubt.");
      return;
    }
    if (!safeName(upload.filename.c_str())) {
      uploadError = ws43bText("Użyj nazwy .jpg, .jpeg lub .png tylko z liter, cyfr, spacji i - _ ( ).", "Use a .jpg, .jpeg or .png file name with letters, digits, spaces, - _ ( ) only.", "Nutze einen .jpg-, .jpeg- oder .png-Namen nur mit Buchstaben, Ziffern, Leerzeichen und - _ ( ).");
      return;
    }
    if (!mount(millis(), true)) {
      uploadError = ws43bText("Brak karty pamięci.", "No memory card.", "Keine Speicherkarte.");
      return;
    }
    SD.mkdir(DIR);
    snprintf(uploadName, sizeof(uploadName), "%s", upload.filename.c_str());
    // Written under a temporary name: an interrupted upload never shows up
    // as a broken slide (".upload.tmp" fails safeName()).
    uploadFile = SD.open(UPLOAD_TMP, FILE_WRITE);
    if (!uploadFile) uploadError = ws43bText("Nie można zapisać na karcie pamięci.", "Cannot write to the memory card.", "Speicherkarte nicht beschreibbar.");
  } else if (upload.status == UPLOAD_FILE_WRITE) {
    if (!uploadFile) return;
    uploadBytes += upload.currentSize;
    if (!sizeAllowed(format(uploadName), uploadBytes)) {
      dropUpload(ws43bText("Plik za duży (JPG do 4 MB, PNG do 2 MB).", "File too large (JPG up to 4 MB, PNG up to 2 MB).", "Datei zu groß (JPG bis 4 MB, PNG bis 2 MB)."));
      return;
    }
    if (uploadFile.write(upload.buf, upload.currentSize) != upload.currentSize)
      dropUpload(ws43bText("Błąd zapisu na karcie pamięci.", "Memory card write failed.", "Schreiben auf die Speicherkarte fehlgeschlagen."));
  } else if (upload.status == UPLOAD_FILE_END) {
    if (!uploadFile) return;
    uploadFile.close();
    char path[kNameMax + 16];
    imagePath(path, sizeof(path), uploadName);
    if (SD.exists(path)) SD.remove(path);
    if (!SD.rename(UPLOAD_TMP, path)) {
      dropUpload(ws43bText("Błąd zapisu na karcie pamięci.", "Memory card write failed.", "Schreiben auf die Speicherkarte fehlgeschlagen."));
      return;
    }
    uploadOk = true;
    listDirty = true;
    ++listRevision;  // same name replaced: the content changed
    Serial.printf("PHOTO upload %s %lu bytes\n", uploadName, (unsigned long)uploadBytes);
  } else if (upload.status == UPLOAD_FILE_ABORTED) {
    if (uploadFile) dropUpload(ws43bText("Przesyłanie przerwane.", "Upload interrupted.", "Hochladen abgebrochen."));
  }
}

void handleUploadDone(WebServer &server) {
  server.sendHeader("Cache-Control", "no-store");
  if (uploadOk) sendStatus(server, 200, nullptr);
  else sendStatus(server, 400, uploadError ? uploadError : ws43bText("Nie otrzymano pliku.", "No file received.", "Keine Datei empfangen."));
}
}  // namespace

const Settings &ws43bPhotoSettings() { return settings; }

void loadWs43bPhotoSettings() {
  settings = {};
  Preferences local;
  if (!local.begin(NVS_NAMESPACE, true)) return;
  const uint16_t value = local.getUShort("w43_photo", 0);
  local.end();
  Settings stored;
  if (decode(value, stored)) settings = stored;
}

bool saveWs43bPhotoSettings(const Settings &next) {
  Preferences local;
  if (!local.begin(NVS_NAMESPACE, false)) return false;
  const uint16_t value = encode(next);
  const bool saved = local.putUShort("w43_photo", value) == sizeof(value);
  local.end();
  if (!saved) return false;
  const bool redecode = next.fill != settings.fill;
  settings = next;
  if (!settings.enabled) ws43bPhotoRelease();
  else if (redecode) {  // show the current picture again, rescaled
    show = Slideshow{};
    slideReady = false;
  }
  return true;
}

bool ws43bPhotoPrepare(uint32_t now) {
  if (!settings.enabled) {
    ws43bPhotoRelease();
    return false;
  }
  if (!mount(now)) return false;
  if (listDirty || uint32_t(now - listedMs) >= RESCAN_MS) scan(now);
  if (!count || !names) {
    slideReady = false;
    return false;
  }
  if (!allocate()) return false;
  if (show.due(now, kIntervals[settings.interval & 3])) {
    if (!decodeDue(slideReady, count, listRevision, decodedListRevision)) {
      show.shown(now);
      return true;
    }
    bool decoded = false;
    for (unsigned attempt = 0; attempt < 3 && attempt < count && !decoded; ++attempt) {
      const uint16_t index = show.next(count);
      decoded = decode(names[index]);
      // A failed file must not be retried in place: advance past it next time.
      show.started = true;
    }
    if (decoded) {
      slideReady = true;
      decodedListRevision = listRevision;
      ++revision;
    } else if (SD.cardType() == CARD_NONE) {
      unmount();
    }
    // Success or not, wait one interval before the next decode.
    show.shown(now);
  }
  return slideReady;
}

uint32_t ws43bPhotoSlideRevision() { return revision; }

void ws43bPhotoPush(int x, int y, int w, int h) {
  if (!slide || !slideReady) return;
  // In bands with a 1 ms pause: the canvas is presented only at endWrite(),
  // so the pauses are invisible, and the scan-out gets PSRAM bandwidth.
  for (int top = y; top < y + h; top += kPushBandRows) {
    const int rows = y + h - top < kPushBandRows ? y + h - top : kPushBandRows;
    tft.setClipRect(x, top, w, rows);
    slide->pushSprite(tft_ptr, 0, 0);
    tft.clearClipRect();
    if (top + rows < y + h) delay(1);
  }
}

void ws43bPhotoDimmedCard(int x, int y, int w, int h) {
  if (!slide || !slideReady) return;
  lgfx::LGFX_Sprite card(tft_ptr);
  card.setPsram(true);
  card.setColorDepth(16);
  if (!card.createSprite(w, h)) {
    ws43bPhotoPush(x, y, w, h);
    return;
  }
  slide->pushSprite(&card, -x, -y);
  // 16-bit sprites keep RGB565 byte-swapped; dim in native order.
  auto *pixels = static_cast<uint16_t *>(card.getBuffer());
  for (int row = 0; row < h; ++row) {
    for (int col = 0; col < w; ++col) {
      if (!insideRounded(col, row, w, h, 14)) continue;
      uint16_t &value = pixels[row * w + col];
      const uint16_t dimmed = dim(uint16_t((value >> 8) | (value << 8)), 160);
      value = uint16_t((dimmed >> 8) | (dimmed << 8));
    }
  }
  card.pushSprite(tft_ptr, x, y);
  card.deleteSprite();
}

void ws43bPhotoRelease() {
  if (slide) {
    slide->deleteSprite();
    delete slide;
    slide = nullptr;
  }
  slideReady = false;
  show = Slideshow{};
}

void ws43bPhotoRegisterRoutes(WebServer &server) {
  server.on("/monitor/photos", HTTP_GET, [&server]() { handleList(server); });
  server.on("/monitor/photos", HTTP_POST, [&server]() { handleSettings(server); });
  server.on("/monitor/photos/delete", HTTP_POST, [&server]() { handleDelete(server); });
  server.on("/monitor/photos/file", HTTP_GET, [&server]() { handleFile(server); });
  server.on("/monitor/photos/upload", HTTP_POST, [&server]() { handleUploadDone(server); },
            [&server]() { handleUpload(server); });
}
#endif
