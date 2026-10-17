from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[4]
class WeatherSchedule(unittest.TestCase):
 def test_readiness_retry_configuration_and_wrap(self):
  code=r'''
#include "ws43b_weather_schedule.h"
#include <cassert>
int main(){
 using ws43b_weather::FetchSchedule;
 FetchSchedule s;
 assert(s.waitMs(0,0,false)==1000);assert(s.waitMs(2000,0,true)==0);
 s.completed(3000,false);assert(s.intervalMs==20000);
 assert(s.waitMs(22999,0,true)==1);assert(s.waitMs(23000,0,true)==0);
 s.completed(23000,false);assert(s.intervalMs==60000);
 s.completed(83000,false);assert(s.intervalMs==180000);
 s.completed(263000,false);assert(s.intervalMs==300000);
 s.completed(563000,false);assert(s.intervalMs==300000);
 s.completed(600000,true);assert(s.intervalMs==600000&&s.failures==0);
 assert(s.waitMs(1199999,0,true)==1);assert(s.waitMs(1200000,0,true)==0);
 // Location changes wake the worker but cannot hammer the remote endpoint.
 s.completed(1200000,true);assert(s.waitMs(1200001,1,true)==1000);
 assert(s.waitMs(1220000,1,true)==0);
 assert(s.waitMs(1220000,1,false)==1000);
 s.completed(0xfffffff0u,false);
 assert(s.waitMs(0x10u,1,true)==1000);
 assert(s.waitMs(uint32_t(0xfffffff0u+20000u),1,true)==0);
}
'''
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'test.cpp').write_text(code)
   subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(ROOT/'include'),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
   subprocess.run([str(p/'test')],check=True)
