"""build.py and the panel accept exactly the same RGB PCLK values."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


class PclkChoices(unittest.TestCase):
    def test_build_and_panel_agree(self):
        build = (ROOT / 'bringup/waveshare43b/integration/build.py').read_text()
        panel = (ROOT / 'src/lgfx_panel_ws43b.cpp').read_text()
        allowed = re.search(r"pclk_hz not in \(([^)]*)\)", build).group(1)
        build_values = {int(v) for v in re.findall(r"'(\d+)'", allowed)}
        assertion = panel[panel.index('static_assert(WS43B_RGB_PCLK_HZ') :]
        assertion = assertion[: assertion.index(';')]
        panel_values = {int(v) for v in re.findall(r'== (\d+)', assertion)}
        self.assertEqual(build_values, panel_values)
        self.assertEqual(build_values, {12000000, 14000000, 16000000, 18000000, 20000000})
        default = re.search(r"WS43B_RGB_PCLK_HZ', '(\d+)'", build).group(1)
        self.assertEqual(default, '16000000')


if __name__ == '__main__':
    unittest.main()
