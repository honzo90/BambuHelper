"""Dusk dimming: solar night only dims; manual hours alone decide the night."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]

HARNESS = r'''
#include <cassert>
#include "ws43b_dusk_policy.h"
using ws43b_dusk::colorPercent;
int main(){
 // Daytime: full colors with or without the solar option.
 assert(colorPercent(true,false,false,false)==100);
 // Dark outside, before 22:00 / after 06:00: 50% after the no-touch
 // timeout, full colors again right after a touch.
 assert(colorPercent(true,false,true,true)==50);
 assert(colorPercent(true,false,false,true)==100);
 assert(colorPercent(true,false,true,false)==100);
 // Night hours: full colors until the night timeout, then the 30% clock dim,
 // regardless of solar data.
 assert(colorPercent(true,true,false,true)==100);
 assert(colorPercent(true,true,true,true)==30);
 assert(colorPercent(true,true,true,false)==30);
 // AP mode / no printer: never dim.
 for(int bits=0;bits<8;++bits)
  assert(colorPercent(false,bits&1,bits&2,bits&4)==100);
 return 0;
}
'''


class DuskDim(unittest.TestCase):
    def test_color_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'dusk.cpp'
            source.write_text(HARNESS)
            binary = Path(tmp) / 'dusk'
            subprocess.run(['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-I', str(ROOT / 'include'), str(source), '-o', str(binary)],
                           check=True, capture_output=True, text=True)
            subprocess.run([str(binary)], check=True, capture_output=True, text=True)

    def test_night_hours_ignore_solar_data(self):
        source = (ROOT / 'src/display_ui.cpp').read_text()
        body = source[source.index('static bool isNightHour()'):]
        body = body[:body.index('\n}\n')]
        self.assertNotIn('ws43bSolarNight', body)
        self.assertIn('dpSettings.nightStartHour', body)

    def test_dispatcher_uses_policy(self):
        source = (ROOT / 'src/display_ws43b.cpp').read_text()
        self.assertIn('ws43b_dusk::colorPercent(', source)
        self.assertIsNone(re.search(r'setColorPercent\(\s*nightDim\s*\?', source))


if __name__ == '__main__':
    unittest.main()
