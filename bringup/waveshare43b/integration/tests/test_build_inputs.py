"""Build provenance includes visual sources while excluding raster/cache outputs."""
from pathlib import Path
import hashlib
import importlib.util
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
HERE = ROOT / 'bringup/waveshare43b/integration'
spec = importlib.util.spec_from_file_location('ws43b_build_inputs', HERE / 'build.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class BuildInputs(unittest.TestCase):
    def test_saved_font_and_visual_provenance_are_hashed(self):
        inputs = build.inputs()
        required = ['fonts/Inter-Regular.ttf', 'fonts/Inter-Bold.ttf',
                    'include/fonts/ws43b_dashboard_v2.h', 'include/ws43b_visual_assets_data.h']
        required += ['bringup/waveshare43b/integration/' + name for name in
                     ('generate_dashboard_fonts.py', 'generate_modern_fonts.py')]
        required += ['bringup/waveshare43b/integration/visual-v2/' + name for name in
                     ('generate.py', 'rasterize.cjs', 'assets.json', 'rasterizer.json',
                      'manifest.json', 'README.md', 'scene-components-prompt.txt', 'raw/scene-atlas.png',
                      'raw/scene-components.png', 'raw/icons/nozzle.svg',
                      'raw/icons/bed.svg', 'raw/icons/chamber.svg', 'raw/icons/print.svg',
                      'raw/icons/ams.svg', 'raw/icons/details.svg', 'raw/icons/settings.svg')]
        for relative in required:
            self.assertEqual(inputs[relative], hashlib.sha256((ROOT / relative).read_bytes()).hexdigest())
        self.assertFalse(any('/rasterized/' in name or '__pycache__' in name
                             or 'design-previews/' in name for name in inputs))

    def test_raw_source_changes_invalidate_but_transient_outputs_do_not(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            here = root / 'bringup/waveshare43b/integration'
            visual = here / 'visual-v2'
            source = visual / 'raw/icons/nozzle.svg'
            raster = visual / 'rasterized/Nozzle.png'
            cache = visual / '__pycache__/generate.pyc'
            for file in (source, raster, cache):
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(b'first')
            # Other fixed inputs need no synthetic payload; only the selected
            # source is read so this test stays independent of the real build.
            def digest(path):
                return hashlib.sha256(path.read_bytes()).hexdigest() if path == source else 'fixed'
            with patch.object(build, 'ROOT', root), patch.object(build, 'HERE', here), \
                 patch.object(build, '__file__', str(here / 'build.py')), patch.object(build, 'digest', digest):
                before = build.inputs()
                raster.write_bytes(b'changed raster');cache.write_bytes(b'changed cache')
                self.assertEqual(build.inputs(), before)
                source.write_bytes(b'changed source')
                after = build.inputs()
                self.assertEqual([name for name in before if before[name] != after[name]],
                                 [str(source.relative_to(root))])


if __name__ == '__main__':
    unittest.main()
