"""Host check of actual water geometry and clock formatting boundaries."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[4]
class WaterClockTest(unittest.TestCase):
    def test_geometry_and_time(self):
        code = r'''
#include <initializer_list>
#include "ws43b_water_clock.h"
#include <cassert>
int main() {
 using namespace ws43b_water;
 for (int x=0; x<800; x+=4) {
  for (unsigned t: {0u, 1000u, 6000u, 11999u, 0xffffffffu}) {
   assert(surface(0,true,x,t)==480);
   assert(surface(100,true,x,t)==0);
   assert(surface(73,false,x,t)==480);
   assert(surface(50,true,x,t)>=235 && surface(50,true,x,t)<=245);
   for (int p=1;p<100;++p) {
    const int y=surface(p,true,x,t);
    assert(y>=0 && y<=480);
   }
  }
  assert(surface(50,true,x,1000)==surface(50,true,x,13000));
 }
 assert(surface(50,true,0,0)!=surface(50,true,0,3000));
 assert(hour(0,false)==12 && hour(12,false)==12 && hour(23,false)==11);
 assert(hour(0,true)==0 && hour(23,true)==23);
}
'''
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'check.cpp'; source.write_text(code)
            binary=Path(folder)/'check'
            subprocess.run(['c++','-std=c++11','-I',str(ROOT/'include'),str(source),'-o',str(binary)],check=True)
            subprocess.run([str(binary)],check=True)
