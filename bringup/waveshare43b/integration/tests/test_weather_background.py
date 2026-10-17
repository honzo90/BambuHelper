"""Compile and exercise the actual firmware background classifier/drawing code."""
from pathlib import Path
import subprocess
import tempfile
import unittest

class WeatherBackgroundTest(unittest.TestCase):
    def test_native_rendering(self):
        root = Path(__file__).resolve().parents[4]
        with tempfile.TemporaryDirectory() as tmp:
            exe = str(Path(tmp) / 'weather-background')
            subprocess.run(['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-I'+str(root/'include'), str(Path(__file__).with_suffix('.cpp')),
                            '-o', exe], check=True, capture_output=True)
            subprocess.run([exe], check=True, capture_output=True)
