#pragma once
#include <stddef.h>
#include <stdint.h>
#ifndef WS43B_MEMORY_DIAG
#define WS43B_MEMORY_DIAG 0
#endif
namespace ws43b_memory {
enum class Stage : uint8_t { Setup, Settings, DisplayInit, WifiInit, Services,
  Wifi, MqttAllocate, MqttConnect, MqttParse, Weather, Render, Web, Thumbnail, Count };
#if defined(BOARD_IS_WS43B) && WS43B_MEMORY_DIAG
void begin();
void weatherResult(bool success);
void enter(Stage stage);
void leave(Stage stage);
size_t formatJson(char *out, size_t capacity);
#else
inline void begin() {}
inline void weatherResult(bool) {}
inline void enter(Stage) {}
inline void leave(Stage) {}
#endif
class Scope {
 public:
  explicit Scope(Stage stage) : stage_(stage) { enter(stage_); }
  ~Scope() { leave(stage_); }
  Scope(const Scope &) = delete;
  Scope &operator=(const Scope &) = delete;
 private:
  Stage stage_;
};
}
