"""Run actual boot composition, firmware text fitting, assets and VLW masks."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('render_boot', HERE / 'previews/render_boot.py')
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


class BootSceneTest(unittest.TestCase):
    def test_stages_fonts_bounds_and_partial_frame_equivalence(self):
        with tempfile.TemporaryDirectory(prefix='ws43b-boot-test-') as directory:
            binary = renderer.compile_preview(directory)
            result = subprocess.run([str(binary), '--verify'], check=True,
                                    capture_output=True, text=True)
            evidence = json.loads(result.stdout)
            self.assertEqual(evidence['result'], 'PASS')
            self.assertEqual(evidence['full_cases'], 40)
            self.assertEqual(evidence['partial_comparisons'], 520)
            self.assertEqual(evidence['partial_allocations'], 0)
            self.assertEqual(evidence['clipped_text_pixels'], 0)


if __name__ == '__main__':
    unittest.main()
