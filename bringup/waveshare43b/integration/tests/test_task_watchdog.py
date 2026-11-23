"""Task watchdog feeding: only subscribed tasks reset it, no log spam.

The Arduino loop task is not subscribed to the task watchdog; a direct
esp_task_wdt_reset() from it logs "task not found" on every MQTT message.
"""

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]

CODE = r'''
#include <cassert>
#include <cstdio>
typedef int esp_err_t;
constexpr esp_err_t ESP_OK=0, ESP_ERR_NOT_FOUND=0x105;
static bool subscribed=false; static int resets=0;
esp_err_t esp_task_wdt_status(void *task){assert(task==nullptr);return subscribed?ESP_OK:ESP_ERR_NOT_FOUND;}
esp_err_t esp_task_wdt_reset(){assert(subscribed);++resets;return ESP_OK;}
#include "task_watchdog_body.h"
int main(){
  feedTaskWatchdog();assert(resets==0);   // loop task: nothing, no error log
  subscribed=true;feedTaskWatchdog();assert(resets==1);
  puts("PASS: watchdog fed only from subscribed tasks");
}
'''


class TaskWatchdog(unittest.TestCase):
    def test_no_direct_resets_in_sources(self):
        for path in (ROOT / 'src').rglob('*.cpp'):
            text = path.read_text(errors='replace')
            self.assertIsNone(re.search(r'\besp_task_wdt_reset\s*\(', text), str(path))

    def test_helper_feeds_only_subscribed_tasks(self):
        header = (ROOT / 'include/task_watchdog.h').read_text()
        body = header.replace('#include <esp_task_wdt.h>', '')
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / 'task_watchdog_body.h').write_text(body)
            (p / 'test.cpp').write_text(CODE)
            subprocess.run(
                [
                    'clang++',
                    '-std=c++17',
                    '-Wall',
                    '-Werror',
                    '-I',
                    str(p),
                    str(p / 'test.cpp'),
                    '-o',
                    str(p / 'test'),
                ],
                check=True,
            )
            subprocess.run([str(p / 'test')], check=True)


if __name__ == '__main__':
    unittest.main()
