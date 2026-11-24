"""A 72 px saver value that does not fit steps down to crisp 64/43 px fonts.

The previous fallback drew the 30 px font at text size 2 (a blocky 2x
upscale). This compiles the production dashText() against a recording
canvas and checks which fonts and sizes the fallback really uses.
"""

from pathlib import Path
import subprocess, tempfile, unittest

ROOT = Path(__file__).resolve().parents[4]


class BigNumberFallback(unittest.TestCase):
    def test_fallback_fonts_and_sizes(self):
        source = (ROOT / 'src/display_ws43b.cpp').read_text()
        function = source[
            source.index(
                '// Fonts are loaded only while drawing; reset the shared font cache'
            ) : source.index('// The native dashboard follows the approved')
        ]
        code = (
            r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <cstdint>
#include <string>
#include <vector>
using String=std::string;
constexpr int FONT_NONE=0,TL_DATUM=0,INK=1;
// Fonts are identified by address; each has a fixed advance per character.
const uint8_t ws43b_dash_large[1]={},ws43b_dash_30[1]={},ws43b_dash_24[1]={},
  ws43b_dash_18[1]={},ws43b_dash_14[1]={},ws43b_v2_b64[1]={},ws43b_v2_b43[1]={};
int advance(const uint8_t *f){
  return f==ws43b_dash_large?44:f==ws43b_v2_b64?38:f==ws43b_v2_b43?36:f==ws43b_dash_30?18:10;
}
struct Draw{std::string text;const uint8_t *font;int size,x,y;};
struct Canvas {
  const uint8_t *font=nullptr;int size=1;std::vector<Draw> draws;
  void loadFont(const uint8_t *f){font=f;}void unloadFont(){font=nullptr;}
  void setTextSize(int s){size=s;}void setTextColor(int){}void setTextDatum(int){}
  void setClipRect(int,int,int,int){}void clearClipRect(){}
  int textWidth(const char *s){assert(font);return int(strlen(s))*advance(font)*size;}
  void drawString(const char *s,int x,int y){assert(font);draws.push_back({s,font,size,x,y});}
}tft;
template<class C>void setFont(C&,int){}
'''
            + function
            + r'''
int main(){
  // Fits at 72 px: drawn unchanged.
  dashText("68%",44,257,194,72,INK);
  assert(tft.draws.size()==1&&tft.draws[0].font==ws43b_dash_large&&tft.draws[0].size==1);
  // "100%" is too wide at 72 px for 150 px: 64 px digits + 43 px percent.
  tft.draws.clear();dashText("100%",44,257,150,72,INK);
  assert(tft.draws.size()==2);
  for(const auto &d:tft.draws)assert(d.size==1);
  bool digits=false,percent=false;
  for(const auto &d:tft.draws){
    if(d.text=="100"&&d.font==ws43b_v2_b64&&d.x==44)digits=true;
    if(d.text=="%"&&d.font==ws43b_v2_b43&&d.x==44+3*38)percent=true;
  }
  assert(digits&&percent);
  // Not numeric or still too wide: the 30 px font at size 1, never 2x.
  tft.draws.clear();dashText("--%",44,257,60,72,INK);
  assert(!tft.draws.empty());
  for(const auto &d:tft.draws)assert(d.size==1&&d.font==ws43b_dash_30);
  puts("PASS: big saver numbers step down to 64/43 px fonts, never a 2x upscale");
}
'''
        )
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / 'test.cpp').write_text(code)
            subprocess.run(
                [
                    'clang++',
                    '-std=c++17',
                    '-Wall',
                    '-Wextra',
                    '-Werror',
                    str(p / 'test.cpp'),
                    '-o',
                    str(p / 'test'),
                ],
                check=True,
            )
            subprocess.run([str(p / 'test')], check=True)


if __name__ == '__main__':
    unittest.main()
