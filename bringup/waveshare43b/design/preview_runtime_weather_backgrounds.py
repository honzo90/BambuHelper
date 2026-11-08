"""Actual C++ background, synthetic opaque card masks (not a full LCD screenshot)."""

from pathlib import Path
import subprocess
import tempfile
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).with_name('runtime-weather-backgrounds.png')
with tempfile.TemporaryDirectory() as tmp:
    exe = str(Path(tmp) / 'weather')
    subprocess.run(
        [
            'clang++',
            '-std=c++17',
            '-I' + str(ROOT / 'include'),
            str(ROOT / 'bringup/waveshare43b/integration/tests/test_weather_background.cpp'),
            '-o',
            exe,
        ],
        check=True,
    )
    sheet = Image.new('RGB', (800, 7 * 264), '#101820')
    labels = ImageDraw.Draw(sheet)
    for k, name in enumerate(['Neutral', 'Clear', 'Cloud', 'Fog', 'Rain', 'Snow', 'Storm']):
        for night in range(2):
            ppm = str(Path(tmp) / 'frame.ppm')
            subprocess.run([exe, str(k), str(night), ppm], check=True, stdout=subprocess.DEVNULL)
            frame = Image.open(ppm)
            d = ImageDraw.Draw(frame)
            for box in [
                (24, 84, 484, 277),
                (502, 84, 776, 145),
                (502, 150, 776, 211),
                (502, 216, 776, 277),
            ] + [(24 + i * 190, 330, 204 + i * 190, 398) for i in range(4)]:
                d.rounded_rectangle(box, 12, fill='#102329')
            sheet.paste(frame.resize((400, 240)), (400 * night, 264 * k + 24))
            labels.text(
                (400 * night + 8, 264 * k + 5), name + (' NIGHT' if night else ' DAY'), fill='white'
            )
    sheet.save(OUT)
print(OUT)
