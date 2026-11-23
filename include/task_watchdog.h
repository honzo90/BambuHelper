#pragma once
// Feed the task watchdog only from tasks subscribed to it. The Arduino loop
// task is not subscribed (no enableLoopWDT()), and IDF 5.x logs
// "esp_task_wdt_reset(...): task not found" for every unsubscribed reset -
// once per MQTT message. esp_task_wdt_status() checks without logging.
#include <esp_task_wdt.h>

inline void feedTaskWatchdog() {
  if (esp_task_wdt_status(nullptr) == ESP_OK) esp_task_wdt_reset();
}
