"""Contact sheet of production weather symbols, rasterized at native pixels.

The varied backdrop exposes accidental opaque tiles. Only this host preview
uses Pillow, text fonts and dynamic memory.
"""
from pathlib import Path
import subprocess
import tempfile
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[4]
STATES = [
    ('Słońce / księżyc', 'Clear'), ('Zachmurzenie małe', 'Partial'),
    ('Chmury', 'Cloud'), ('Mgła', 'Fog'), ('Mżawka', 'Drizzle'),
    ('Deszcz', 'Rain'), ('Marznące opady', 'Ice'), ('Śnieg', 'Snow'),
    ('Burza', 'Storm'), ('Burza z gradem', 'Hail'), ('Brak odczytu', 'Unknown'),
]


def color(value):
    return ((value >> 11) * 255 // 31, ((value >> 5) & 63) * 255 // 63,
            (value & 31) * 255 // 31)


def line(image, x, y, end_x, end_y, value):
    """Integer line rasterization without supersampling that hides rough edges."""
    dx, dy = abs(end_x - x), -abs(end_y - y)
    sx, sy = (1 if x < end_x else -1), (1 if y < end_y else -1)
    error = dx + dy
    while True:
        image.putpixel((x, y), color(value))
        if x == end_x and y == end_y:
            return
        twice = 2 * error
        if twice >= dy:
            error += dy
            x += sx
        if twice <= dx:
            error += dx
            y += sy


def font(size):
    for name in ['/System/Library/Fonts/Supplemental/Arial.ttf', 'DejaVuSans.ttf']:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def main():
    image = Image.new('RGB', (1200, 480), (9, 19, 30))
    text = ImageDraw.Draw(image)
    text.text((18, 14), 'Pogoda · kod panelu 43B · dzień i noc', font=font(23), fill=(237, 243, 248))
    text.text((18, 46), 'Duże: skala 2. Małe: natywne 32 px, faza 950 ms. Bez wygładzania podglądu.',
              font=font(14), fill=(171, 186, 203))
    body = ['#include "ws43b_weather_icons.h"', '#include <cstdio>',
            'struct Surface { void drawLine(int x,int y,int a,int b,uint16_t c) {',
            'printf("%d %d %d %d %u\\n",x,y,a,b,unsigned(c)); }};',
            'int main(){Surface s;']
    for index, (label, symbol) in enumerate(STATES):
        x, y = 10 + index % 6 * 200, 80 + index // 6 * 196
        # Broad native-dashboard gradient; the last tile shows transparency
        # over a checkerboard as well as the ordinary gradient.
        for row in range(184):
            for column in range(188):
                light = row * 9 // 184
                check = 5 if index == 10 and (column // 8 + row // 8) % 2 else 0
                image.putpixel((x + column, y + row), (28-light+check, 44-light+check, 58-light+check))
        text.text((x + 8, y + 8), label, font=font(14), fill=(237, 243, 248))
        for night, offset, caption in [(False, 48, 'Dzień'), (True, 141, 'Noc')]:
            text.text((x+offset-19, y+32), caption, font=font(12), fill=(171, 186, 203))
            for scale, center_y in [(2, y + 88), (1, y + 151)]:
                body.append(f'ws43b_weather_icon::draw(s,ws43b_weather_icon::Symbol::{symbol},'
                            f'{x+offset},{center_y},{scale},{str(night).lower()},'
                            '0xef9f,0xf5cb,0x5ede,950);')
    body.append('}')
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary)
        (path/'weather.cpp').write_text('\n'.join(body))
        subprocess.run(['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                        '-I', str(ROOT/'include'), str(path/'weather.cpp'),
                        '-o', str(path/'weather')], check=True)
        output = subprocess.check_output([str(path/'weather')], text=True)
        for operation in output.splitlines():
            line(image, *map(int, operation.split()))
    destination = Path(__file__).with_name('weather-symbols-native-v4.png')
    image.save(destination)
    print(destination)


if __name__ == '__main__':
    main()
