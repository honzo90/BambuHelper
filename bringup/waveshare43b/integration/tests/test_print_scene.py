"""Actual compact-scene pixels, optional cache and public saver integration."""
from pathlib import Path
import json
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = Path(__file__).with_name('print_scene_fixture.cpp')


class PrintScene(unittest.TestCase):
    def test_real_pixels_bounds_cache_fallback_and_material(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            result = subprocess.run([
                'clang++', '-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', '-I', str(ROOT/'include'),
                str(FIXTURE), '-o', str(path/'print-scene'),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(path/'print-scene')], capture_output=True, text=True, timeout=90)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report['result'], 'PASS')
            self.assertEqual(report['cached_fallback_frames'], 576)
            self.assertGreater(report['head_rgba_samples'], 100000)
            self.assertGreater(report['material_difference_pixels'], 1000)
            self.assertEqual(report['wrapper_frames'], 16)
            self.assertGreater(report['dense_sweep_frames'], 5000)
            self.assertEqual(report['cleaning_pose_samples'], 3200)


if __name__ == '__main__':
    unittest.main()
