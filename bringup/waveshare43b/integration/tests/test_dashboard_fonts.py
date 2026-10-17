"""Validate the actual dashboard-v2 VLW payloads without requiring Pillow."""
from pathlib import Path
import hashlib
import re
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
HEADER = ROOT / 'include/fonts/ws43b_dashboard_v2.h'
GENERATOR = ROOT / 'bringup/waveshare43b/integration/generate_dashboard_fonts.py'
FULL = {'ws43b_v2_12', 'ws43b_v2_13', 'ws43b_v2_b14', 'ws43b_v2_b15',
        'ws43b_v2_b16', 'ws43b_v2_b17', 'ws43b_v2_b25'}
RESTRICTED = {
    'ws43b_v2_b23': '0123456789%- ',
    'ws43b_v2_b28': '0123456789:.,-+ hmind',
    'ws43b_v2_b29': '0123456789%.,:-+°C ',
    'ws43b_v2_b64': '0123456789- ',
    'ws43b_v2_b43': '%',
}


def tables():
    text = HEADER.read_text()
    return {name: bytes(int(value, 16) for value in re.findall(r'0x([0-9a-f]{2})', data))
            for name, data in re.findall(r'const uint8_t (\w+)\[\] PROGMEM = \{(.*?)\};', text, re.S)}


def records(data):
    count = struct.unpack_from('>I', data)[0]
    return [struct.unpack_from('>IIIIiiI', data, 24 + i * 28) for i in range(count)]


class DashboardFontTest(unittest.TestCase):
    def test_exact_symbols_vlw_bounds_and_flash_budget(self):
        fonts = tables()
        self.assertEqual(set(fonts), FULL | set(RESTRICTED))
        self.assertLessEqual(sum(map(len, fonts.values())), 180 * 1024)
        for name, data in fonts.items():
            with self.subTest(font=name):
                count, version, size, reserved, ascent, descent = struct.unpack_from('>6I', data)
                self.assertEqual(version, 6)
                self.assertEqual(size, int(re.search(r'(\d+)$', name)[1]))
                self.assertEqual(reserved, 0)
                self.assertGreater(ascent, 0)
                self.assertGreater(descent, 0)
                glyphs = records(data)
                points = [r[0] for r in glyphs]
                self.assertEqual(points, sorted(set(points)))
                self.assertEqual(len(data), 24 + count * 28 + sum(r[1] * r[2] for r in glyphs))
                self.assertTrue(all(r[6] == 0 for r in glyphs))
                # Existing renderer's conservative glyph alpha+row working set.
                self.assertLess(max(r[1] * r[2] + r[2] * 3 for r in glyphs), 4096)
                self.assertTrue(any(0 < byte < 255 for byte in data[24 + count * 28:]))
                if name in RESTRICTED:
                    self.assertEqual(set(map(chr, points)), set(RESTRICTED[name]))
                else:
                    expected = set(chr(i) for i in range(32, 127))
                    expected.update('ąćęłńóśźżĄĆĘŁŃÓŚŹŻ°·äöüÄÖÜßéèêàáâçñôûÉÇ–—…')
                    self.assertEqual(set(map(chr, points)), expected)

    def test_polish_labels_numeric_placeholders_and_layout_fit(self):
        fonts = {name: {chr(r[0]): r for r in records(data)} for name, data in tables().items()}
        for name in FULL:
            for phrase in ['Postęp wydruku', 'Pozostało', 'Szczegóły', 'Ustawienia',
                           'Dysza · Stół · Komora', 'W użyciu', 'Łączenie z drukarką',
                           'Świeże dane', 'Wilgotność', 'Ilość nieznana', 'Bambu P2S',
                           'Pogoda chwilowo niedostępna', 'Jürgen · Élodie · Rafał', '– — …']:
                self.assertTrue(all(character in fonts[name] for character in phrase), (name, phrase))
        for name, phrase, width in [
            ('ws43b_v2_b64', '100', 160),
            ('ws43b_v2_b64', '--', 160),
            ('ws43b_v2_b25', 'Bambu P2S', 180),
            ('ws43b_v2_b28', '32 min', 160),
            ('ws43b_v2_b28', '1h 35', 160),
            ('ws43b_v2_b28', '12h 59', 160),
            ('ws43b_v2_b28', '--', 160),
            ('ws43b_v2_b29', '250°C', 150),
            ('ws43b_v2_b29', '--°C', 150),
            ('ws43b_v2_b23', '%', 32),
            ('ws43b_v2_b23', '100%', 100),
            ('ws43b_v2_b23', '--', 100),
            ('ws43b_v2_b43', '%', 48),
        ]:
            self.assertTrue(all(c in fonts[name] for c in phrase), (name, phrase))
            self.assertLess(sum(fonts[name][c][3] for c in phrase), width, (name, phrase))

    def test_font_and_generator_provenance(self):
        text = HEADER.read_text()
        self.assertIn('// Pillow: 12.3.0;', text)
        self.assertIn(f'// Generator SHA256: {hashlib.sha256(GENERATOR.read_bytes()).hexdigest()}', text)
        for relative in ['fonts/Inter-Regular.ttf', 'fonts/Inter-Bold.ttf']:
            digest = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            self.assertIn(f'// {relative} SHA256: {digest}', text)
        for name, data in tables().items():
            self.assertIn(f'SHA256 {hashlib.sha256(data).hexdigest()}\nconst uint8_t {name}', text)


class DashboardVlwRenderingTest(unittest.TestCase):
    """Run the real v2Text function against the shipped VLW alpha masks.

    The test canvas follows LovyanGFX 1.2.26's VLWfont::loadFont,
    updateFontMetric/drawChar and LGFXBase::text_width/draw_string at size 1,
    TL_DATUM. In particular, the rasterizer guesses a space advance from the
    initial header line height; text_width reads the explicit glyph record.
    No Pillow, screen, hardware, generated mock font, or network is required.
    """
    @classmethod
    def setUpClass(cls):
        display = (ROOT / 'src/display_ws43b.cpp').read_text()
        implementation = display[display.index('int v2Text('):display.index('void footer(')]
        clock_match = re.search(
            r'snprintf\(header,sizeof\(header\),"%02d:%02d %s"[^\n]*\n\s*'
            r'(v2Text\(header,[^\n]+;)', display)
        if clock_match is None:
            raise AssertionError('The native twelve-hour clock call was not found')
        # Exercise the actual weather choice and actual clock call, so changing
        # either font, clip width, alignment, or fallback is covered as well.
        weather = display[display.index('void menuWeatherHeader('):display.index('bool dashboardCooling=')]
        weather_start = weather.index('    ::setFont(tft,FONT_NONE);')
        weather_end = weather.index('\n  }', weather_start)
        weather_call = weather[weather_start:weather_end]
        slot_match = re.search(
            r'v2Text\(empty\?ws43bText\("Pusty","Empty"\):ws43bText\("Brak odczytu","No reading"\),[^\n]+;',
            display)
        if slot_match is None:
            raise AssertionError('The native missing/empty slot call was not found')
        source = r"""
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include <utility>
#include "fonts/ws43b_dashboard_v2.h"
using String=std::string;
constexpr int FONT_NONE=0,TL_DATUM=0;
uint16_t v2Ink(){return 0;}
uint16_t v2Dim(){return 0;}
bool polish=true;
const char *ws43bText(const char *pl,const char *en){return polish?pl:en;}
uint32_t be32(const uint8_t *data) {
  return (uint32_t(data[0])<<24)|(uint32_t(data[1])<<16)|(uint32_t(data[2])<<8)|data[3];
}
std::vector<uint32_t> unicode(const char *text) {
  std::vector<uint32_t> result;
  for(const auto *p=reinterpret_cast<const uint8_t *>(text);*p;) {
    uint32_t code=*p++;unsigned tail=0;
    if(code>=0xf0){code&=7;tail=3;}
    else if(code>=0xe0){code&=15;tail=2;}
    else if(code>=0xc0){code&=31;tail=1;}
    while(tail--){assert((*p&0xc0)==0x80);code=(code<<6)|(*p++&63);}
    result.push_back(code);
  }
  return result;
}
std::string utf8(uint32_t cp) {
  std::string out;
  if(cp<128)out+=char(cp);
  else if(cp<2048){out+=char(0xc0|(cp>>6));out+=char(0x80|(cp&63));}
  else{out+=char(0xe0|(cp>>12));out+=char(0x80|((cp>>6)&63));out+=char(0x80|(cp&63));}
  return out;
}
struct TestCanvas {
  struct Glyph {uint32_t code;int height,width,advance,dy,dx;const uint8_t *alpha;};
  std::vector<Glyph> glyphs;
  int baseline=0,space=0,cx=0,cy=0,cw=0,ch=0;
  bool clipped=false;unsigned ink=0;std::string drawn;
  void loadFont(const uint8_t *font) {
    glyphs.clear();baseline=int(be32(font+16));int descent=int(be32(font+20));
    // This guess occurs before the glyph loop extends maxAscent/maxDescent.
    space=std::max(int(be32(font+8)),baseline+descent)*2/7;
    const uint32_t count=be32(font);const uint8_t *bitmap=font+24+28*count;
    for(unsigned i=0;i<count;++i) {
      const auto *r=font+24+28*i;
      Glyph g{be32(r),int(be32(r+4)),int(be32(r+8)),int(be32(r+12)),
              int16_t(be32(r+16)),int8_t(be32(r+20)),bitmap};
      glyphs.push_back(g);bitmap+=g.width*g.height;
      if(g.code>255 || (g.code>32&&g.code<160&&g.code!=127)) {
        baseline=std::max(baseline,g.dy);descent=std::max(descent,g.height-g.dy);
      }
    }
  }
  const Glyph &glyph(uint32_t code) const {
    for(const auto &g:glyphs)if(g.code==code)return g;
    assert(false&&"Text contains an unsupported glyph");return glyphs.front();
  }
  int textWidth(const char *text) const {
    int left=0,right=0;
    for(const auto cp:unicode(text)) {
      const auto &g=glyph(cp);
      if(left==0&&right==0&&g.dx<0)left=right=-g.dx;
      right=left+std::max(g.advance,g.width+g.dx);left+=g.advance;
    }
    return right;
  }
  void setTextSize(int size){assert(size==1);}
  void setTextColor(uint16_t){}
  void setTextDatum(int datum){assert(datum==TL_DATUM);}
  void setClipRect(int x,int y,int w,int h){cx=x;cy=y;cw=w;ch=h;clipped=false;ink=0;}
  void clearClipRect(){}
  void unloadFont(){}
  void drawString(const char *text,int x,int y) {
    drawn=text;const auto points=unicode(text);int cursor=points.empty()?0:std::max(-glyph(points[0]).dx,0);
    for(const auto cp:points) {
      const auto &g=glyph(cp);
      if(cp==32){cursor+=space;continue;}
      for(int row=0;row<g.height;++row)for(int col=0;col<g.width;++col)if(g.alpha[row*g.width+col]) {
        ++ink;const int px=x+cursor+g.dx+col,py=y+baseline-g.dy+row;
        clipped|=px<cx||px>=cx+cw||py<cy||py>=cy+ch;
      }
      cursor+=g.advance;
    }
  }
} tft;
void setFont(TestCanvas &,int){}
""" + implementation + r"""
void complete(const char *text) {
  if(tft.clipped||tft.drawn!=text) {
    fprintf(stderr,"Clipped or abbreviated: %s (clip %d,%d %dx%d; drawn %s)\n",text,tft.cx,tft.cy,tft.cw,tft.ch,tft.drawn.c_str());
    assert(false);
  }
}
int main(int argc,char **argv) {
  assert(argc==2);
  if(!strcmp(argv[1],"clock")) {
    char header[32];unsigned count=0;
    for(int hour=0;hour<24;++hour)for(int minute=0;minute<60;++minute) {
      snprintf(header,sizeof(header),"%02d:%02d %s",hour%12?hour%12:12,minute,hour<12?"AM":"PM");
""" + clock_match[1] + r"""
      complete(header);++count;
    }
    assert(count==1440);
    // This is the reported regression, not only an approximate advance sum.
    v2Text("04:44 AM",705,24,76,ws43b_v2_b14,14,0,true,false);complete("04:44 AM");
  } else if(!strcmp(argv[1],"weather")) {
    char value[32];const bool fresh=true;
    for(int temperature=-100;temperature<=101;++temperature) {
      if(temperature==101)snprintf(value,sizeof(value),"--°C");
      else snprintf(value,sizeof(value),"%d°C",temperature);
""" + weather_call + r"""
      complete(value);
    }
  } else if(!strcmp(argv[1],"slots")) {
    struct Case {bool pl,empty;const char *expected;};
    const Case cases[]={{true,true,"Pusty"},{true,false,"Brak odczytu"},
                        {false,true,"Empty"},{false,false,"No reading"}};
    for(const auto &test:cases)for(int slot=0;slot<4;++slot) {
      polish=test.pl;const bool empty=test.empty;const int x=16+194*slot;
""" + slot_match[0] + r"""
      complete(test.expected); // No ellipsis is acceptable in these state labels.
    }
  } else if(!strcmp(argv[1],"height")) {
    const uint8_t *all[]={ws43b_v2_12,ws43b_v2_13,ws43b_v2_b14,ws43b_v2_b15,
      ws43b_v2_b16,ws43b_v2_b17,ws43b_v2_b25,ws43b_v2_b23,ws43b_v2_b28,
      ws43b_v2_b29,ws43b_v2_b64,ws43b_v2_b43};
    for(const auto *font:all)for(unsigned i=0;i<be32(font);++i) {
      const auto value=utf8(be32(font+24+28*i));
      v2Text(value.c_str(),4,8,256,font,be32(font+8),0,false,false);complete(value.c_str());
    }
    // Polish ogonek and Latin cedilla each lost their final nonzero alpha row
    // with height+5, due to VLW maxAscent rather than the nominal font size.
    for(const auto pair:{std::make_pair(ws43b_v2_13,"Ę"),std::make_pair(ws43b_v2_b17,"Ç")}) {
      const int size=be32(pair.first+8);tft.loadFont(pair.first);
      tft.setClipRect(0,0,100,size+5);tft.drawString(pair.second,0,0);
      assert(tft.clipped&&tft.ink>0);
      v2Text(pair.second,0,0,100,pair.first,size,0,false,false);complete(pair.second);
    }
    // Multiple spaces exercise the same width correction used by the AMS
    // sensor strip; fitting is validated against emitted alpha, not textWidth.
    const char *sensors="40°C · 14% RH · 4 min temu · offline";
    v2Text(sensors,212,323,568,ws43b_v2_12,12,0,true,false);complete(sensors);
  } else assert(false&&"Unknown test case");
}
"""
        cls.temp = tempfile.TemporaryDirectory(prefix='ws43b-vlw-render-')
        cls.addClassCleanup(cls.temp.cleanup)
        directory = Path(cls.temp.name)
        (directory / 'pgmspace.h').write_text(
            '#pragma once\n#define PROGMEM\n'
            '#define pgm_read_byte(p) (*static_cast<const uint8_t *>(p))\n')
        cpp = directory / 'test.cpp'
        cpp.write_text(source)
        cls.binary = directory / 'test'
        subprocess.run(['c++', '-std=c++17', '-O1', '-Wall', '-Wextra',
                        '-I', str(directory), '-I', str(ROOT / 'include'),
                        str(cpp), '-o', str(cls.binary)], check=True,
                       capture_output=True, text=True)

    def test_all_twelve_hour_clock_values_fit_with_actual_space_advance(self):
        subprocess.run([str(self.binary), 'clock'], check=True)

    def test_weather_fallback_fits_full_supported_range_and_placeholder(self):
        subprocess.run([str(self.binary), 'weather'], check=True)

    def test_empty_and_unknown_slot_states_are_complete_in_both_languages(self):
        subprocess.run([str(self.binary), 'slots'], check=True)

    def test_vlw_alpha_descenders_fit_actual_clip_height(self):
        subprocess.run([str(self.binary), 'height'], check=True)


if __name__ == '__main__':
    unittest.main()
