"""Exercise the real task-selective allocator, including cross-task freeing."""
from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[4]
class TlsMemory(unittest.TestCase):
 def test_only_weather_uses_psram_and_never_falls_back(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'freertos').mkdir();(p/'mbedtls').mkdir()
   (p/'freertos/FreeRTOS.h').write_text('#pragma once\nusing TaskHandle_t=void*;\n')
   (p/'freertos/task.h').write_text('#pragma once\ninline void* currentTask=(void*)1;\ninline void* xTaskGetCurrentTaskHandle(){return currentTask;}\n')
   (p/'esp_heap_caps.h').write_text(r'''#pragma once
#include <cstdlib>
#include <cassert>
#define MALLOC_CAP_SPIRAM 4
#define MALLOC_CAP_8BIT 8
inline int externalCalls=0,internalCalls=0,freeCalls=0;
inline bool failExternal=false;
inline void* heap_caps_calloc(size_t n,size_t size,unsigned caps){assert(caps==12);++externalCalls;return failExternal?nullptr:calloc(n,size);}
''')
   (p/'esp_mem.h').write_text(r'''#pragma once
inline void* esp_mbedtls_mem_calloc(size_t n,size_t size){++internalCalls;return calloc(n,size);}
inline void esp_mbedtls_mem_free(void* p){++freeCalls;free(p);}
''')
   (p/'mbedtls/platform.h').write_text(r'''#pragma once
inline void*(*allocate)(size_t,size_t)=nullptr;
inline void(*release)(void*)=nullptr;
inline int installedCalls=0;
inline int mbedtls_platform_set_calloc_free(void*(*a)(size_t,size_t),void(*f)(void*)){++installedCalls;allocate=a;release=f;return 0;}
''')
   (p/'main.cpp').write_text(r'''
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
extern "C" {
#include "esp_mem.h"
#include "mbedtls/platform.h"
}
#include "ws43b_tls_memory.h"
int main(){
 assert(!ws43b_tls::canStartWeather(39999,1024*1024));
 assert(!ws43b_tls::canStartWeather(80000,128*1024-1));
 assert(ws43b_tls::canStartWeather(40000,128*1024));
 {ws43b_tls::WeatherScope before;assert(!before.ready());}
 assert(ws43b_tls::begin()&&ws43b_tls::begin()&&installedCalls==1);
 void* a=allocate(2,32);assert(internalCalls==1&&externalCalls==0);
 void* b=nullptr;
 {ws43b_tls::WeatherScope weather;assert(weather.ready());
  {ws43b_tls::WeatherScope nested;assert(!nested.ready());}
  b=allocate(2,32);assert(externalCalls==1&&internalCalls==1);
  for(int i=0;i<64;++i)assert(static_cast<unsigned char*>(b)[i]==0);
  currentTask=(void*)2;void* c=allocate(1,8);assert(internalCalls==2);release(c);
  currentTask=(void*)1;failExternal=true;assert(!allocate(1,4096));assert(internalCalls==2);
 }
 currentTask=(void*)3;release(a);release(b);assert(freeCalls==3);
 void* d=allocate(1,8);assert(internalCalls==3);release(d);
 auto stats=ws43b_tls::stats();assert(stats.ready&&stats.psramAllocations==1&&stats.psramFailures==1);
}
''')
   subprocess.run(['clang++','-std=c++17','-fsanitize=address,undefined','-DBOARD_IS_WS43B','-I'+str(p),'-I'+str(ROOT/'src'),str(p/'main.cpp'),str(ROOT/'src/ws43b_tls_memory.cpp'),'-o',str(p/'probe')],check=True,capture_output=True)
   subprocess.run([str(p/'probe')],check=True,capture_output=True)
