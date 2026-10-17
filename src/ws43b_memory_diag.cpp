#include "ws43b_memory_diag.h"
#if defined(BOARD_IS_WS43B) && WS43B_MEMORY_DIAG
#include <Arduino.h>
#include "ws43b_tls_memory.h"
#include <esp_heap_caps.h>
#include <esp_timer.h>
#include <stdio.h>
#include <stdarg.h>
#include <limits.h>

namespace ws43b_memory {
namespace {
constexpr size_t count = size_t(Stage::Count);
const char *const names[count] = {"setup", "settings", "display_init", "wifi_init",
  "services", "wifi", "mqtt_allocate", "mqtt_connect", "mqtt_parse", "weather",
  "render", "web", "thumbnail"};
struct Row { uint32_t entries, samples, minFree, minLargest, minSum; };
struct Record {
  Row rows[count];
  uint32_t samples, minFree, minAtMs, minMask, minLargest, minLargestAtMs;
  uint32_t failures, failedBytes, failedCaps, failedMask, failedAtMs;
  uint32_t weatherSuccesses, weatherFailures;
  bool timerOk, hookOk;
};
DRAM_ATTR portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;
DRAM_ATTR Record record{};
DRAM_ATTR uint16_t depth[count]{};
DRAM_ATTR uint32_t activeMask = 0;
esp_timer_handle_t timer = nullptr;

void sample(void *) {
  // These are instantaneous values (not sums of historical region minima).
  // Calls are sequential: do not interpret free/largest as an atomic heap dump.
  const uint32_t free = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
  const uint32_t largest = heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  const uint32_t sum = heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL);
  const uint32_t now = millis();
  portENTER_CRITICAL(&mux);
  if (!record.samples || free < record.minFree) {
    record.minFree = free; record.minAtMs = now; record.minMask = activeMask;
  }
  if (!record.samples || largest < record.minLargest) {
    record.minLargest = largest; record.minLargestAtMs = now;
  }
  ++record.samples;
  for (size_t i = 0; i < count; ++i) if (activeMask & (1u << i)) {
    auto &r = record.rows[i];
    if (!r.samples || free < r.minFree) r.minFree = free;
    if (!r.samples || largest < r.minLargest) r.minLargest = largest;
    if (!r.samples || sum < r.minSum) r.minSum = sum;
    ++r.samples;
  }
  portEXIT_CRITICAL(&mux);
}

void failed(size_t size, uint32_t caps, const char *) {
  // Never allocate, print, format strings or retry allocations from this hook.
  portENTER_CRITICAL(&mux);
  ++record.failures;
  record.failedBytes = size > UINT32_MAX ? UINT32_MAX : uint32_t(size);
  record.failedCaps = caps; record.failedMask = activeMask;
  record.failedAtMs = uint32_t(esp_timer_get_time() / 1000);
  portEXIT_CRITICAL(&mux);
}
}

void begin() {
  record.hookOk = heap_caps_register_failed_alloc_callback(failed) == ESP_OK;
  sample(nullptr);
  esp_timer_create_args_t args{};
  args.callback = sample; args.name = "heap_diag";
  args.skip_unhandled_events = true;
  record.timerOk = esp_timer_create(&args, &timer) == ESP_OK &&
                   esp_timer_start_periodic(timer, 50000) == ESP_OK;
}
void weatherResult(bool success) {
  portENTER_CRITICAL(&mux);
  if (success) ++record.weatherSuccesses; else ++record.weatherFailures;
  portEXIT_CRITICAL(&mux);
}
void enter(Stage stage) {
  const auto i = size_t(stage);
  portENTER_CRITICAL(&mux);
  ++depth[i]; activeMask |= 1u << i; ++record.rows[i].entries;
  portEXIT_CRITICAL(&mux);
  sample(nullptr);
}
void leave(Stage stage) {
  sample(nullptr);
  const auto i = size_t(stage);
  portENTER_CRITICAL(&mux);
  if (depth[i] && !--depth[i]) activeMask &= ~(1u << i);
  portEXIT_CRITICAL(&mux);
}

size_t formatJson(char *out, size_t capacity) {
  Record snapshot;
  portENTER_CRITICAL(&mux); snapshot = record; portEXIT_CRITICAL(&mux);
  size_t used = 0; bool ok = true;
  auto add = [&](const char *fmt, ...) {
    if (!ok || used >= capacity) { ok = false; return; }
    va_list args; va_start(args, fmt);
    const int n = vsnprintf(out + used, capacity - used, fmt, args);
    va_end(args);
    if (n < 0 || size_t(n) >= capacity - used) { ok = false; return; }
    used += size_t(n);
  };
  add("{\"version\":1,\"sample_period_ms\":50,\"timer_ok\":%s,\"hook_ok\":%s,"
      "\"samples\":%u,\"sampled_min_free_internal\":%u,\"min_at_ms\":%u,\"min_stage_mask\":%u,"
      "\"sampled_min_largest_internal8\":%u,\"min_largest_at_ms\":%u,"
      "\"allocation_failures\":%u,\"failed_bytes\":%u,\"failed_caps\":%u,"
      "\"failed_stage_mask\":%u,\"failed_at_ms\":%u,\"stages\":[",
      snapshot.timerOk ? "true":"false", snapshot.hookOk ? "true":"false",
      snapshot.samples, snapshot.minFree, snapshot.minAtMs, snapshot.minMask,
      snapshot.minLargest, snapshot.minLargestAtMs, snapshot.failures, snapshot.failedBytes,
      snapshot.failedCaps, snapshot.failedMask, snapshot.failedAtMs);
  for (size_t i = 0; i < count; ++i) {
    const auto &r = snapshot.rows[i];
    add("%s{\"name\":\"%s\",\"bit\":%u,\"entries\":%u,\"samples\":%u,"
        "\"sampled_min_free\":%u,\"sampled_min_largest8\":%u,\"region_min_sum\":%u}",
        i ? ",":"", names[i], unsigned(1u << i), r.entries, r.samples,
        r.minFree, r.minLargest, r.minSum);
  }
  const auto tls = ws43b_tls::stats();
  add("],\"weather_tls_ready\":%s,\"weather_tls_psram_allocations\":%u,\"weather_tls_psram_failures\":%u,\"weather_successes\":%u,\"weather_failures\":%u}",
      tls.ready ? "true" : "false", tls.psramAllocations, tls.psramFailures, snapshot.weatherSuccesses, snapshot.weatherFailures);
  return ok ? used : 0;
}
}
#endif
