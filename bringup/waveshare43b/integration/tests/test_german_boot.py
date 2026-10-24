"""German boot layout using the production scene, text fitting and VLW masks.

The existing PL/EN 40-case test remains unchanged. This adds German coverage
without editing the preview renderer or drawing a replacement implementation.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(os.environ.get('BAMBUHELPER_TEST_ROOT', Path(__file__).resolve().parents[4]))
HERE = ROOT / 'bringup/waveshare43b/integration'
spec = importlib.util.spec_from_file_location('german_render_boot', HERE / 'previews/render_boot.py')
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


class GermanBoot(unittest.TestCase):
    def test_german_boot_fonts_bounds_and_partial_frame_equivalence(self):
        with tempfile.TemporaryDirectory(prefix='ws43b-boot-de-') as temporary:
            directory = Path(temporary)
            # Reuse production v2Text extraction, pgmspace stub and compiler setup.
            # The original preview source and its PL/EN verification stay intact.
            renderer.compile_preview(directory)
            source = (HERE / 'previews/boot_preview.cpp').read_text()
            old = 'ws43b_boot::draw(tft,text,phase,p,pl,detail?detail:context(phase,pl),now);'
            new = 'ws43b_boot::draw(tft,text,phase,p,pl,detail?detail:context(phase,pl),now,true);'
            self.assertEqual(source.count(old), 1)
            source = source.replace(old, new)
            old = 'for(bool pl:{true,false})'
            self.assertEqual(source.count(old), 1)
            source = source.replace(old, 'for(bool pl:{false})')
            marker = '  const ws43b_boot::Palette palettes[]='
            self.assertEqual(source.count(marker), 1)
            source = source.replace(marker, '''  for(unsigned phase=0;phase<4;++phase) {
    assert(std::strcmp(ws43b_boot::title(P(phase),false,true),ws43b_boot::title(P(phase),false))!=0);
    assert(std::strcmp(ws43b_boot::subtitle(P(phase),false,true),ws43b_boot::subtitle(P(phase),false))!=0);
  }
''' + marker)
            (directory / 'boot_german.cpp').write_text(source)
            binary = directory / 'boot_german'
            compiled = subprocess.run(['clang++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                                       '-I', str(directory), '-I', str(ROOT / 'include'),
                                       str(directory / 'boot_german.cpp'), '-o', str(binary)],
                                      capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            run = subprocess.run([str(binary), '--verify'], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            evidence = json.loads(run.stdout)
            self.assertEqual(evidence['result'], 'PASS')
            self.assertEqual(evidence['full_cases'], 20)
            self.assertEqual(evidence['partial_comparisons'], 260)
            self.assertEqual(evidence['partial_allocations'], 0)
            self.assertEqual(evidence['unsupported_glyphs'], 0)
            self.assertEqual(evidence['clipped_text_pixels'], 0)


if __name__ == '__main__':
    unittest.main()
