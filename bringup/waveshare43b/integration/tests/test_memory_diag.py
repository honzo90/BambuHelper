"""Compile the real diagnostic module against deterministic heap/timer stubs."""
from pathlib import Path
import json, subprocess, tempfile, unittest
ROOT = Path(__file__).resolve().parents[4]
class MemoryDiagnostics(unittest.TestCase):
 def test_instantaneous_minima_nested_scopes_failure_and_bounded_json(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)
   (p/'Arduino.h').write_text(r'''#pragma once
#include <cstdint>
#define DRAM_ATTR
using portMUX_TYPE=int;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(x) ((void)0)
#define portEXIT_CRITICAL(x) ((void)0)
inline uint32_t tick=100;
inline uint32_t millis(){return tick;}
''')
   (p/'esp_heap_caps.h').write_text(r'''#pragma once
#include <cstdint>
#include <cstddef>
#define ESP_OK 0
#define MALLOC_CAP_INTERNAL 1
#define MALLOC_CAP_8BIT 2
inline uint32_t freeNow=80000,largestNow=32000,sumMin=2000;
using Hook=void(*)(size_t,uint32_t,const char*);
inline Hook hook=nullptr;
inline int heap_caps_register_failed_alloc_callback(Hook f){hook=f;return 0;}
inline size_t heap_caps_get_free_size(uint32_t){return freeNow;}
inline size_t heap_caps_get_largest_free_block(uint32_t){return largestNow;}
inline size_t heap_caps_get_minimum_free_size(uint32_t){return sumMin;}
''')
   (p/'esp_timer.h').write_text(r'''#pragma once
#include <cstdint>
using esp_timer_handle_t=void*;
struct esp_timer_create_args_t {void(*callback)(void*);const char*name;bool skip_unhandled_events;};
inline void(*timerCallback)(void*)=nullptr;
inline int esp_timer_create(const esp_timer_create_args_t*a,void**p){timerCallback=a->callback;*p=(void*)1;return 0;}
inline int esp_timer_start_periodic(void*,uint64_t){return 0;}
inline int64_t esp_timer_get_time(){return 123000;}
''')
   (p/'main.cpp').write_text(r'''
#include "Arduino.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "ws43b_memory_diag.h"
#include <cassert>
#include <iostream>
#include "ws43b_tls_memory.h"
namespace ws43b_tls { Stats stats(){return {false,0,0};} }
using namespace ws43b_memory;
int main(){
 begin();
 {Scope outer(Stage::MqttConnect);
  {Scope inner(Stage::MqttConnect);freeNow=45000;largestNow=12000;timerCallback(nullptr);}
  freeNow=40000;largestNow=11000;tick=200;timerCallback(nullptr);
  hook(8192,3,"ignored");
 }
 freeNow=70000;largestNow=25000;timerCallback(nullptr);
 char tiny[12];assert(formatJson(tiny,sizeof tiny)==0);
 char full[8192];assert(formatJson(full,sizeof full)>0);std::cout<<full;
}
''')
   subprocess.run(['clang++','-std=c++17','-fsanitize=address,undefined','-DBOARD_IS_WS43B','-DWS43B_MEMORY_DIAG=1','-I'+str(p),'-I'+str(ROOT/'src'),str(p/'main.cpp'),str(ROOT/'src/ws43b_memory_diag.cpp'),'-o',str(p/'probe')],check=True,capture_output=True)
   d=json.loads(subprocess.check_output([str(p/'probe')]))
   self.assertEqual(d['sampled_min_free_internal'],40000)
   self.assertEqual(d['sampled_min_largest_internal8'],11000)
   self.assertEqual(d['min_stage_mask'],1<<7)
   self.assertEqual(d['allocation_failures'],1)
   self.assertEqual(d['failed_stage_mask'],1<<7)
   self.assertEqual(d['failed_bytes'],8192)
   row=d['stages'][7]
   self.assertEqual(row['entries'],2)
   self.assertEqual(row['sampled_min_free'],40000)
   self.assertEqual(row['region_min_sum'],2000)
   self.assertTrue(d['hook_ok'] and d['timer_ok'])
 def test_disabled_build_has_no_hardware_dependencies(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'main.cpp').write_text('#include "ws43b_memory_diag.h"\nint main(){ws43b_memory::begin();ws43b_memory::Scope s(ws43b_memory::Stage::Render);}')
   subprocess.run(['clang++','-std=c++17','-I'+str(ROOT/'src'),str(p/'main.cpp'),str(ROOT/'src/ws43b_memory_diag.cpp'),'-o',str(p/'probe')],check=True,capture_output=True)
   subprocess.run([str(p/'probe')],check=True)
