"""Night window with minute precision: real isNightHour() comparison, storage and export."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class NightMinutes(unittest.TestCase):
    def test_window_comparison(self):
        source = (ROOT / 'src/display_ui.cpp').read_text()
        body = source[source.index('static bool isNightHour()'):]
        body = body[body.index('  // Minutes of the day'):body.index('\n}\n')]
        harness = r'''
#include <cassert>
#include <cstdint>
#include <ctime>
struct {uint8_t nightStartHour,nightEndHour,nightStartMinute,nightEndMinute;} dpSettings;
bool night(int hour,int minute){ struct tm now{}; now.tm_hour=hour; now.tm_min=minute;
BODY
}
void set(int sh,int sm,int eh,int em){dpSettings.nightStartHour=sh;dpSettings.nightStartMinute=sm;dpSettings.nightEndHour=eh;dpSettings.nightEndMinute=em;}
int main(){
 set(22,30,6,45);                       // wraps midnight
 assert(!night(22,29) && night(22,30) && night(23,59) && night(0,0) && night(6,44) && !night(6,45) && !night(12,0));
 set(1,15,7,0);                         // same day
 assert(!night(1,14) && night(1,15) && night(6,59) && !night(7,0));
 set(22,0,7,0);                         // whole hours keep the old behaviour
 assert(night(22,0) && night(6,59) && !night(7,0) && !night(21,59));
 set(22,0,22,0); assert(!night(22,0) && !night(3,0)); // equal = disabled
 set(22,0,22,5); assert(night(22,0) && night(22,4) && !night(22,5)); // short window
 return 0;
}
'''.replace('BODY', body)
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'night.cpp'; src.write_text(harness)
            exe = Path(tmp) / 'night'
            subprocess.run(['clang++', '-std=c++17', '-Wall', '-Wextra', str(src), '-o', str(exe)],
                           check=True, capture_output=True, text=True)
            subprocess.run([str(exe)], check=True)

    def test_storage_form_and_export(self):
        settings = (ROOT / 'src/settings.cpp').read_text()
        for key in ('dp_nsmin', 'dp_nemin'):
            self.assertEqual(settings.count(f'"{key}"'), 2, key)  # load + save
            self.assertLessEqual(len(key), 15)                    # NVS key limit
        server = (ROOT / 'src/web_server.cpp').read_text()
        for arg in ('nsmin', 'nemin'):
            self.assertIn(f'server.hasArg("{arg}")', server)
            self.assertIn(f"p.append('{arg}'", (ROOT / 'web/app.js').read_text())
            self.assertIn(f'id="{arg}"', (ROOT / 'include/web_pages.h').read_text())
        for field in ('nightStartMinute', 'nightEndMinute'):
            self.assertIn(f'dp["{field}"] = dpSettings.{field};', server)
            # Old exports without minutes import as :00.
            self.assertRegex(server, r'dpSettings\.' + field + r' = dp\["' + field + r'"\]\.is<uint8_t>\(\).*: 0;')
        template = (ROOT / 'src/web_template.cpp').read_text()
        self.assertIn('NIGHT_SMIN_OPTS', template)
        self.assertIn('m += 5', template)


if __name__ == '__main__':
    unittest.main()
