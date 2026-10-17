from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[4]
class DashboardPolicy(unittest.TestCase):
 def test_thermal_and_navigation(self):
  code=r'''#include "ws43b_dashboard_policy.h"
#include <cassert>
using namespace ws43b_view;
int main(){
 ThermalPolicy p;
 assert(p.update(100,true,210,true,220)==Thermal::Unknown);
 assert(p.update(5099,true,210,true,220)==Thermal::Unknown);
 assert(p.update(5100,true,210,true,220)==Thermal::Heating);
 assert(p.update(5200,true,218.5,true,220)==Thermal::Heating);
 p.update(5300,true,220,true,220);
 assert(p.update(10300,true,220,true,220)==Thermal::Stable);
 assert(p.update(10301,false,220,true,220)==Thermal::Unknown);
 ThermalPolicy q;
 q.update(0,true,60,true,0);q.update(1000,true,59,true,0);
 assert(q.update(6000,true,58,true,0)==Thermal::Cooling);
 q.update(96001,true,58,true,0);
 assert(q.update(101001,true,58,true,0)==Thermal::Stable);
 ThermalPolicy n; n.update(0,true,40,true,40);
 for(unsigned t=1;t<30000;t+=1000)assert(n.update(t,true,t%2?41:39,true,40)==(t<5000?Thermal::Unknown:Thermal::Stable));
 assert(navigationVisible(4999,0,false)); assert(!navigationVisible(5000,0,false));
 assert(navigationVisible(8000,0,true));assert(navigationVisible(20,0xfffffff0,false));
 for(int i=0;i<4;++i){
   const int left=16+i*194,right=left+183;
   assert(navigationItem(left,440)==i);assert(navigationItem(right,475)==i);
   assert(navigationItem(left,439)==-1);assert(navigationItem(right,476)==-1);
   if(i<3)for(int x=right+1;x<left+194;++x)assert(navigationItem(x,458)==-1);
 }
 assert(navigationItem(15,458)==-1);assert(navigationItem(782,458)==-1);
 assert(navigationItem(799,479)==-1);
}'''
  with tempfile.TemporaryDirectory() as tmp:
   src=Path(tmp)/'test.cpp';exe=Path(tmp)/'test';src.write_text(code)
   subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(ROOT/'include'),str(src),'-o',str(exe)],check=True)
   subprocess.run([str(exe)],check=True)
