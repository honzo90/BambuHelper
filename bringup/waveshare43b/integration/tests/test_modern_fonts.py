"""Validate the linked VLW bytes, glyph coverage, antialiasing and clock fit."""
from pathlib import Path
import re
import struct
import unittest
ROOT=Path(__file__).resolve().parents[4]
class ModernFontTest(unittest.TestCase):
    def test_font_tables_and_layout(self):
        text=(ROOT/'include/fonts/ws43b_modern.h').read_text()
        fonts={}
        for name,table in re.findall(r'const uint8_t (\w+)\[\].*?\{(.*?)\};',text,re.S):
            data=bytes(int(v,16) for v in re.findall(r'0x([0-9a-f]{2})',table))
            n,version,size,_,asc,desc=struct.unpack_from('>6I',data)
            self.assertEqual(version,6)
            records=[struct.unpack_from('>IIIIiiI',data,24+i*28) for i in range(n)]
            self.assertEqual([r[0] for r in records],sorted(set(r[0] for r in records)))
            self.assertLess(max(r[1]*r[2]+r[2]*3 for r in records), 12*1024)
            end=24+n*28+sum(r[1]*r[2] for r in records)
            self.assertEqual(end,len(data))
            self.assertTrue(any(0 < v < 255 for v in data[24+n*28:]))
            fonts[name]=({chr(r[0]):r for r in records},asc+desc)
        digits,height=fonts['ws43b_inter_digits']
        for h in range(24):
            for m in range(60):
                self.assertLess(sum(digits[c][3] for c in f'{h:02}:{m:02}'),400)
        self.assertLess(height,180)
        body,_=fonts['ws43b_inter_body']
        for phrase in ['Wydruk zakończony','Stół stygnie · °C','Pozostało','ukończono','AM','PM']:
            self.assertTrue(all(c in body for c in phrase))
        self.assertTrue(all(c in digits for c in '0123456789:-°'))

        buttons,_=fonts['ws43b_dash_18']
        for phrase,width in [('Otwórz WebUI · kod QR',684),('Język: Polski',684),('< Język i dane',256),('< Ustawienia',150)]:
            self.assertTrue(all(c in buttons for c in phrase),phrase)
            self.assertLess(sum(buttons[c][3] for c in phrase),width)
