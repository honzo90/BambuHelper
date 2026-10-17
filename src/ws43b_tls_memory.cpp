#include "ws43b_tls_memory.h"
#if defined(BOARD_IS_WS43B)
#include <atomic>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <esp_heap_caps.h>
extern "C" {
#include <esp_mem.h>
#include <mbedtls/platform.h>
}

namespace ws43b_tls {
namespace {
std::atomic<TaskHandle_t> weatherTask{nullptr};
std::atomic<bool> installed{false};
std::atomic<uint32_t> allocations{0}, failures{0};

void *taskCalloc(size_t count, size_t size) {
  const TaskHandle_t selected = weatherTask.load(std::memory_order_acquire);
  if (selected && selected == xTaskGetCurrentTaskHandle()) {
    // The pinned IDF supports this same allocation pair in its external-RAM
    // mbedTLS profile. Do not fall back to scarce internal RAM on failure.
    void *p = heap_caps_calloc(count, size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    (p ? allocations : failures).fetch_add(1, std::memory_order_relaxed);
    return p;
  }
  // Preserve the SDK allocator for MQTT, cloud and all other tasks. Never
  // switch the global function pointers around a live TLS request.
  return esp_mbedtls_mem_calloc(count, size);
}
}

bool begin() {
  if (installed.load(std::memory_order_acquire)) return true;
  // IDF 5.5.5 esp_mbedtls_mem_free delegates to heap_caps_free, which accepts
  // both internal and PSRAM allocations, even if freed from another task.
  const bool ok = mbedtls_platform_set_calloc_free(taskCalloc, esp_mbedtls_mem_free) == 0;
  installed.store(ok, std::memory_order_release);
  return ok;
}
Stats stats() {
  return {installed.load(std::memory_order_acquire),
          allocations.load(std::memory_order_relaxed), failures.load(std::memory_order_relaxed)};
}
WeatherScope::WeatherScope() {
  if (!installed.load(std::memory_order_acquire)) return;
  TaskHandle_t expected = nullptr;
  active_ = weatherTask.compare_exchange_strong(expected, xTaskGetCurrentTaskHandle(),
                                               std::memory_order_acq_rel);
}
WeatherScope::~WeatherScope() {
  if (active_) weatherTask.store(nullptr, std::memory_order_release);
}
}
#endif
