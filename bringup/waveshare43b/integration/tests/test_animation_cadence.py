"""Print-head cadence is independent of ambient effects and yields to live data."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class AnimationCadence(unittest.TestCase):
    def test_independent_rates_fallback_full_repaint_rx_and_rollover(self):
        code = r'''
#include "ws43b_animation_policy.h"
#include "ws43b_live_view.h"
#include <cassert>
using ws43b_animation::Cadence;
int main() {
  Cadence c;
  unsigned head=0,weather=0;
  for(uint32_t now=0;now<=1000;++now) {
    auto f=c.due(now,0,true,true,true);
    head+=f.activity;weather+=f.ambient;c.mark(now,f);
  }
  assert(head==20 && weather==11); // Faster head must not double weather work.
  auto hidden=c.due(2000,0,false,false,true);
  assert(!hidden.activity && !hidden.ambient);
  Cadence fallback;
  head=weather=0;
  for(uint32_t now=0;now<=1000;++now) {
    auto f=fallback.due(now,0,true,true,false);
    head+=f.activity;weather+=f.ambient;fallback.mark(now,f);
  }
  assert(head==11 && weather==11); // No cache: keep the established cadence.
  auto f=c.due(2050,2040,true,true,true);
  assert(!f.activity && !f.ambient); // Give I/O a quiet interval after data redraws.
  f=c.due(2090,2040,true,true,true);assert(f.activity && !f.ambient);
  c.mark(2090,f);
  f=c.due(2124,2040,true,true,true);assert(!f.activity && f.ambient);
  c.mark(2124,f);
  // No burst of catch-up frames after a blocking operation or long offline gap.
  f=c.due(9000,2040,true,true,true);assert(f.activity&&f.ambient);c.mark(9000,f);
  f=c.due(9001,2040,true,true,true);assert(!f.activity&&!f.ambient);
  // Unsigned time arithmetic remains correct across millis() rollover.
  c.mark(0xfffffff0u,{true,true});
  f=c.due(0x21u,0xfffffff0u,true,true,true);assert(!f.activity&&!f.ambient);
  f=c.due(0x22u,0xfffffff0u,true,true,true);assert(f.activity&&!f.ambient);
  f=c.due(0x44u,0xfffffff0u,true,true,true);assert(f.activity&&f.ambient);
  // The existing live-data priority stays ahead of decoration.
  Cadence busy;head=0;
  for(uint32_t now=0;now<400;++now) {
    if(ws43b_live::deferForRx(now,0,true,true,false))continue;
    f=busy.due(now,0,true,false,true);head+=f.activity;busy.mark(now,f);
  }
  assert(head==0);
  assert(!ws43b_live::deferForRx(400,0,true,true,false));
  assert(!ws43b_live::deferForRx(1,0,true,true,true)); // Touch/force is not delayed.
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)
            (path/'test.cpp').write_text(code)
            result=subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I',str(ROOT/'include'),str(path/'test.cpp'),
                '-o',str(path/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(path/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
