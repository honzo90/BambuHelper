"""Real production pending-row/copy helpers: alternating scanout consistency."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[4]
class PartialFramesTest(unittest.TestCase):
    def test_alternating_buffers_keep_all_previous_changes(self):
        code=r'''
#include "ws43b_frame_copy.h"
#include "ws43b_water_clock.h"
#include <cassert>
#include <vector>
#include <algorithm>
int main() {
 constexpr unsigned W=400,H=480;
 std::vector<uint32_t> canvas(W*H), buffers[2]={std::vector<uint32_t>(W*H,1),std::vector<uint32_t>(W*H,2)};
 uint32_t scratch[W];
 ws43b::PendingFrameRows pending(H);
 assert(!pending.mark(480,481) && !pending.mark(7,7) && !pending.mark(8,7));
 for(unsigned frame=0;frame<300;++frame) {
  unsigned top=(frame*37)%479, end=std::min(top+19, H);
  if(frame%17==0) {top=0;end=H;}
  for(unsigned y=top;y<end;++y) for(unsigned x=0;x<W;++x) canvas[y*W+x]=frame*1234567u+x+y;
  assert(pending.mark(top,end));
  unsigned index=(frame+1)%2, first=pending.top[index], rows=pending.bottom[index]-first;
  auto untouched=buffers[index^1];
  assert(ws43b::copyFrameChecked((uint8_t*)(buffers[index].data()+first*W),
    (uint8_t*)(canvas.data()+first*W), scratch,sizeof(scratch),W*4,rows));
  pending.copied(index);
  assert(buffers[index]==canvas);
  assert(buffers[index^1]==untouched); // The displayed buffer is never written.
 }
 // Both phases and both wave surfaces fit the band's margins for every level.
 for(int p=1;p<100;++p) for(unsigned t=0;t<12000;t+=113) for(int x=0;x<800;x+=4) {
  int base=480-480*p/100, top=std::max(0,base-10), end=std::min(480,base+9);
  int front=ws43b_water::surface(p,true,x,t);
  int back=std::max(0,ws43b_water::surface(p,true,x+90,t+2400)-3);
  assert(front>=top && front<end && back>=top && back<end);
 }
}
'''
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'test.cpp';p.write_text(code);binary=Path(folder)/'test'
            subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(ROOT/'src'),'-I',str(ROOT/'include'),str(p),'-o',str(binary)],check=True)
            subprocess.run([str(binary)],check=True)
