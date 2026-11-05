"""WebUI hides settings the native 4.3B renderer never reads, without disabling them."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[4]

# WebUI field id -> firmware setting it writes (web_server.cpp).
FIELDS = {
    'clk_size': 'clockTimeSize', 'clk_dsize': 'clockDateSize', 'clk_hidedate': 'hideClockDate',
    'clkinfo': 'showClockInfo', 'timem': 'timeDisplayMode', 'hidelp': 'hideStatusReadout',
    'clr_eta': 'etaColor', 'clr_fin': 'finishColor', 'clr_pname': 'printerNameColor',
    'clr_dorc': 'doorClosedColor', 'clr_doro': 'doorOpenColor', 'dor_lbl': 'door',
}
# Modules the 4.3B renderer calls into and their headers.
NATIVE = ['src/display_ws43b.cpp', 'src/clock_pong.cpp', 'src/display_edge_glow.cpp',
          *map(str, (ROOT / 'src').glob('ws43b_*.cpp')), *map(str, (ROOT / 'include').glob('ws43b_*.h'))]


class UnusedSettings(unittest.TestCase):
    def setUp(self):
        self.js = (ROOT / 'web/app.js').read_text()
        m = re.search(r'var WS43B_UNUSED_SETTINGS = \[(.*?)\];', self.js, re.S)
        self.assertIsNotNone(m)
        self.hidden = re.findall(r"'([a-z_]+)'", m.group(1))

    def test_list_matches_reviewed_fields(self):
        self.assertEqual(sorted(self.hidden), sorted(FIELDS))

    def test_native_renderer_does_not_read_them(self):
        text = ''.join((ROOT / p).read_text() if not Path(p).is_absolute() else Path(p).read_text() for p in NATIVE)
        for field, setting in FIELDS.items():
            pattern = r'gaugeLabels\.door\b' if setting == 'door' else r'\b' + setting + r'\b'
            self.assertIsNone(re.search(pattern, text), f'{field} ({setting}) is used by the 4.3B renderer; do not hide it')
        # The legacy clock face, split view and card style are never called.
        for fn in ('drawClock', 'formatEtaLine', 'drawCardPrinting', 'drawCardIdle', 'drawCardFinished'):
            self.assertIsNone(re.search(r'\b' + fn + r'\(', text), fn)

    def test_hidden_fields_are_not_disabled(self):
        unsupported = re.search(r'var unsupported = \[(.*?)\];', self.js, re.S).group(1)
        for field in self.hidden:
            self.assertNotIn(f"'{field}'", unsupported, f'{field} must stay submitted')


if __name__ == '__main__':
    unittest.main()
