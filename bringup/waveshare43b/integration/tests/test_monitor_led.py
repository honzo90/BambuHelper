"""Offline LED capability boundary and unchanged legacy preprocessing.

Compiles the actual monitor source against the actual public declarations,
without any GPIO, timer, PWM, RMT or NVS APIs available. No hardware is opened.
"""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
SOURCE = REPO / 'src/led.cpp'
HEADER = REPO / 'src/led.h'


def without_includes(source):
    return re.sub(r'^\s*#include[^\n]*\n', '', source, flags=re.M)


def preprocess(source, flags):
    return subprocess.run(
        ['clang++', '-E', '-P', '-x', 'c++', *flags, '-'],
        input=without_includes(source), text=True, capture_output=True,
        check=True).stdout


class MonitorLed(unittest.TestCase):
    def test_monitor_public_api_links_without_hardware_or_settings(self):
        calls = r'''
int main() {
  initLed(); ledTick(); applyLedDuty(255); sanitizeLedPin();
  for (unsigned pin = 0; pin < 256; ++pin) {
    if (isLedPinAllowed(pin) || isRgbLedPinAllowed(pin)) return 1;
  }
  uint8_t r = 7, g = 8, b = 9; bool anode = true;
  if (onboardRgbPins(r, g, b, anode)) return 2;
  if (r != 7 || g != 8 || b != 9 || !anode) return 3;
  previewLed(true, 2, 7, 8, 9, true, 255, 0xffffff);
  ledSetActivity(LED_ACT_FAILED); ledStartFinishEffect(); ledStopFinishEffect();
#if HAS_HMS_UI
  ledStartErrorEpisode(); ledStopErrorEpisode();
#endif
  if (ledTriggerTestEffect(1, 600, 255, 0xffffff)) return 4;
  ledOnUserInteraction(); ledSetSuspended(true); ledSetNightSuspended(true);
  if (ledHoldDimUpdate(true, 100000, false)) return 5;
  return 0;
}
'''
        body = ('#include <cstdint>\n' + without_includes(HEADER.read_text()) +
                '\n' + without_includes(SOURCE.read_text()) + calls)
        with tempfile.TemporaryDirectory(prefix='ws43b-led-test-') as folder:
            executable = Path(folder) / 'test-led'
            for hms in (0, 1):
                with self.subTest(hms=hms):
                    subprocess.run(
                        ['clang++', '-std=c++17', '-x', 'c++', '-Werror',
                         '-DBAMBU_MONITOR_ONLY=1', '-DHAS_LED_PIXEL=1',
                         f'-DHAS_HMS_UI={hms}', '-', '-o', str(executable)],
                        input=body, text=True, capture_output=True, check=True)
                    subprocess.run([str(executable)], check=True)

    def test_normal_profile_preprocessing_matches_upstream_baseline(self):
        import hashlib
        fixture = Path(__file__).parent / 'fixtures/upstream-led.cpp'
        raw = fixture.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), '712460ddaaec89953ecfb078ddf940da76464c18980927d0d8a8fb9bd7ac76ad')
        baseline = raw.decode()
        for board in ('DISPLAY_CYD', 'BOARD_IS_WS28C', 'BOARD_IS_SENSECAP',
                      'BOARD_IS_S3_ZERO', 'BOARD_IS_DIY'):
            for features in (0, 1):
                with self.subTest(board=board, features=features):
                    flags = ['-DBAMBU_MONITOR_ONLY=0', f'-D{board}=1',
                             f'-DHAS_HMS_UI={features}', f'-DHAS_LED_PIXEL={features}']
                    self.assertEqual(preprocess(baseline, flags),
                                     preprocess(SOURCE.read_text(), flags))


if __name__ == '__main__':
    unittest.main()
