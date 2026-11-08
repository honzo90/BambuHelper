"""Rectangle copies keep both alternating scanout buffers consistent."""

from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]

CODE = r'''
#include "ws43b_frame_copy.h"
#include <cassert>
#include <vector>
#include <algorithm>
#include <cstdlib>
int main() {
 constexpr unsigned W=800,H=480;
 std::vector<uint16_t> canvas(W*H), buffers[2]={std::vector<uint16_t>(W*H,1),std::vector<uint16_t>(W*H,2)};
 alignas(4) uint32_t scratch[W/2];
 ws43b::PendingFrameRects pending(W,H);
 assert(!pending.mark(0,0,0,1) && !pending.mark(0,801,0,1) && !pending.mark(0,1,480,481));
 srand(7);
 unsigned shown=100;
 for(unsigned frame=0;frame<400;++frame) {
  // Like display(): a new colour level re-presents the whole frame on both buffers.
  const unsigned percent=(frame/40)%3==0?100:(frame/40)%3==1?50:30;
  if(percent!=shown){shown=percent;assert(pending.mark(0,W,0,H));}
  // A random dirty rectangle, like _range_mod (inclusive), rounded like display().
  unsigned x0=rand()%W,x1=x0+rand()%(W-x0),y0=rand()%H,y1=y0+rand()%(H-y0);
  if(frame%37==0){x0=0;x1=W-1;y0=0;y1=H-1;}
  for(unsigned y=y0;y<=y1;++y)for(unsigned x=x0;x<=x1;++x)canvas[y*W+x]=uint16_t(frame*977u+x*13u+y);
  const unsigned left=x0&~1u,right=std::min(W,(x1+2)&~1u);
  assert(pending.mark(left,right,y0,y1+1));
  const unsigned i=(frame+1)%2; const auto untouched=buffers[i^1];
  const unsigned first=pending.top[i],rows=pending.bottom[i]-first;
  assert(ws43b::copyRectChecked((uint8_t*)(buffers[i].data()+first*W),(const uint8_t*)(canvas.data()+first*W),
    scratch,sizeof scratch,W*2,pending.left[i]*2,(pending.right[i]-pending.left[i])*2,rows,percent));
  pending.copied(i);
  for(unsigned p=0;p<W*H;++p)assert(buffers[i][p]==ws43b::dimRgb565(canvas[p],percent)); // whole frame current
  assert(buffers[i^1]==untouched); // the displayed buffer is never written
 }
 // Misaligned or out-of-range rectangles are rejected.
 alignas(4) uint8_t a[64]={},b[64]={};alignas(4) uint32_t s[8];
 assert(!ws43b::copyRectChecked(a,b,s,sizeof s,32,2,4,1));      // x not word aligned
 assert(!ws43b::copyRectChecked(a,b,s,sizeof s,32,0,6,1));      // width not word aligned
 assert(!ws43b::copyRectChecked(a,b,s,sizeof s,32,28,8,1));     // past the row end
 assert(ws43b::copyRectChecked(a,b,s,sizeof s,32,28,4,2));
 return 0;
}
'''


class PartialRects(unittest.TestCase):
    def test_rects(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'r.cpp'
            src.write_text(CODE)
            exe = Path(tmp) / 'r'
            subprocess.run(
                [
                    'clang++',
                    '-std=c++17',
                    '-O2',
                    '-Wall',
                    '-Wextra',
                    '-Werror',
                    '-I',
                    str(ROOT / 'src'),
                    str(src),
                    '-o',
                    str(exe),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run([str(exe)], check=True)


if __name__ == '__main__':
    unittest.main()
