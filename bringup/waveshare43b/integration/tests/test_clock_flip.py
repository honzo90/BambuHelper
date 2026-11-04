"""Calendar-page flip of the screensaver digits: timing, motion, opacity."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]

HARNESS = r'''
#include <cassert>
#include "ws43b_clock_flip.h"
using namespace ws43b_clock_flip;
int main(){
 Flip f;
 begin(f,"21:59","22:00",1000);
 assert(f.active);
 // Only differing characters move: "2" stays, "1"->"2", ":" stays, "5"->"0", "9"->"0".
 assert(!changed(f,0)&&changed(f,1)&&!changed(f,2)&&changed(f,3)&&changed(f,4));
 assert(progress(f,1000)==0);
 // Old digit moves down out of the cell, the new one follows from above.
 assert(oldOffset(0)==0 && oldOffset(1000)==kTravel && newOffset(0)==-kTravel && newOffset(1000)==0);
 for(unsigned p=0;p<1000;p+=10){
  assert(oldOffset(p)<=oldOffset(p+10) && newOffset(p)<=newOffset(p+10));   // monotonic
  assert(oldOffset(p)-newOffset(p)==kTravel);                                // never overlap
  assert(oldOffset(p+10)-oldOffset(p)<=kTravel/20+1);                        // no jumps at 1% steps
 }
 assert(ease(0)==0 && ease(500)==500 && ease(1000)==1000 && ease(100)<100 && ease(900)>900); // soft start/stop
 static_assert(kTravel>=100,"travel must exceed the ~85 px digit height");
 // About a second at ~25 fps: enough frames for a smooth page turn.
 assert(kDurationMs>=900 && kDurationMs<=1500 && kFrameMs<=42);
 unsigned frames=0;for(uint32_t t=1000;f.active;t+=kFrameMs){progress(f,t);++frames;}
 assert(frames>=22 && frames<=36 && !f.active);
 assert(progress(f,999999)==1000);
 // Same text, different length or a cancelled flip never animate.
 begin(f,"10:00","10:00",0);assert(!f.active);
 begin(f,"--:--","10:00",0);assert(f.active);
 begin(f,"9:00","10:00",0);assert(!f.active);
 begin(f,"10:00","10:01",0);cancel(f);assert(!f.active && !changed(f,4));
 // Millis wrap.
 begin(f,"10:00","10:01",0xFFFFFF00u);assert(progress(f,0xFFFFFF00u+100u)<1000 && f.active);
 return 0;
}
'''


class ClockFlip(unittest.TestCase):
    def test_flip(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'flip.cpp'; src.write_text(HARNESS)
            exe = Path(tmp) / 'flip'
            subprocess.run(['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'include'),
                            str(src), '-o', str(exe)], check=True, capture_output=True, text=True)
            subprocess.run([str(exe)], check=True)


if __name__ == '__main__':
    unittest.main()
