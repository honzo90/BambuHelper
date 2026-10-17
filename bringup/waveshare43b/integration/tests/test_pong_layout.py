"""Native Pong geometry must fit both the framebuffer and navigation."""
from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[4]
class PongLayout(unittest.TestCase):
 def test_playfield_fits_native_screen_and_avoids_footer(self):
  code=r'''
#include "layout_800x480.h"
#include <cassert>
int main(){
 static_assert(LY_ARK_COLS<=13,"shared renderer brick array capacity");
 static_assert(2*LY_ARK_START_X+LY_ARK_COLS*LY_ARK_BRICK_W+(LY_ARK_COLS-1)*LY_ARK_BRICK_GAP==800,"center the brick field");
 static_assert(LY_ARK_PADDLE_Y+8<433,"footer must not erase the paddle");
 static_assert(LY_ARK_TIME_Y+LY_ARK_DIGIT_H<LY_ARK_PADDLE_Y,"clock stays above paddle");
 static_assert(LY_ARK_DATE_CLR_X+LY_ARK_DATE_CLR_W<=800,"date clear bounds");
}
'''
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'test.cpp').write_text(code)
   subprocess.run(['clang++','-std=c++17','-I'+str(ROOT/'include'),str(p/'test.cpp'),'-o',str(p/'test')],check=True,capture_output=True)
   subprocess.run([str(p/'test')],check=True)
