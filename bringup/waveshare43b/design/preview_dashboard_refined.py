"""UI proposal only: synthetic data, 800x480, no firmware or device changes."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
S = 3
BG = '#081719'
CARD = '#112629'
INK = '#eef8f3'
DIM = '#adc1bb'
GREEN = '#61e3aa'
LINE = '#26403f'
im = Image.new('RGB', (800 * S, 480 * S), BG)
d = ImageDraw.Draw(im)


def font(n, bold=False):
    return ImageFont.truetype(
        str(ROOT / 'fonts' / ('Inter-Bold.ttf' if bold else 'Inter-Regular.ttf')), n * S
    )


def text(x, y, t, n=14, c=INK, bold=False, anchor='lt'):
    d.text((x * S, y * S), t, font=font(n, bold), fill=c, anchor=anchor)


def rect(box, c, r=12, outline=None):
    d.rounded_rectangle(tuple(v * S for v in box), r * S, fill=c, outline=outline, width=S)


def line(points, c=LINE):
    d.line([(x * S, y * S) for x, y in points], fill=c, width=S)


def circle(x, y, r, c):
    d.ellipse(((x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S), fill=c)


def level(box, percent, active=False):
    x, y, xx, yy = box
    w = (xx - x) * S
    h = (yy - y) * S
    rect(box, CARD)
    if percent is not None:
        mask = Image.new('L', (w, h))
        md = ImageDraw.Draw(mask)
        md.rounded_rectangle((0, 0, w - 1, h - 1), 12 * S, fill=255)
        md.rectangle((round(w * percent / 100), 0, w, h), fill=0)
        im.paste('#164b3a' if active else '#12392f', (x * S, y * S), mask)
    if active:
        rect(box, None, 12, '#3a926b')


# Compact weather stays separate from the printer status dot.
text(20, 20, 'P2S', 28, bold=True)
text(107, 30, 'Drukowanie', 16, GREEN)
circle(518, 32, 6, DIM)
circle(527, 26, 9, DIM)
circle(536, 32, 6, DIM)
text(552, 21, '11°C', 24)
text(510, 56, 'Schanbach · pochmurno', 14, DIM)
circle(671, 34, 4, GREEN)
text(780, 18, '20:03', 28, anchor='rt')
text(780, 56, '08.10.2026', 14, DIM, anchor='rt')
line([(20, 78), (780, 78)])
level((20, 94, 496, 286), 75, True)
text(38, 110, 'POSTĘP WYDRUKU', 14, DIM)
text(34, 133, '75%', 76, bold=True)
line([(270, 140), (270, 207)], '#36705a')
text(290, 139, 'Pozostało', 14, DIM)
text(288, 163, '1h 25', 32, bold=True)
text(290, 204, 'Koniec ok. 21:28', 14, DIM)
text(38, 239, 'Obudowa czujnika', 18)
text(38, 265, 'Warstwa 218 / 291', 14, DIM)
for y, title, value, detail in [
    (94, 'DYSZA', '220°C', 'Cel 220°C · stabilna'),
    (162, 'STÓŁ', '55°C', 'Cel 55°C · stabilny'),
    (230, 'KOMORA', '31°C', 'Temperatura komory'),
]:
    rect((512, y, 780, y + 56), CARD)
    text(526, y + 9, title, 14, DIM)
    text(766, y + 6, value, 26, anchor='rt')
    text(526, y + 35, detail, 14, DIM)
text(20, 305, 'AMS 2 Pro', 18, bold=True)
text(780, 308, '32°C  ·  26% RH', 14, DIM, anchor='rt')
for i, (label, pct, col, active) in enumerate(
    [
        ('PLA Basic', 100, '#edf3eb', False),
        ('PLA Matte', 68, '#c7e46d', True),
        ('PETG Basic', 42, '#354345', False),
        ('PLA', None, '#f2884b', False),
    ]
):
    x = 20 + i * 194
    level((x, 338, x + 178, 414), pct, active)
    circle(x + 15, 357, 5, col)
    text(x + 28, 348, f'{i + 1}  {label}', 14)
    text(
        x + 12,
        380,
        'Brak danych' if pct is None else f'{pct}%',
        18 if pct is None else 22,
        c=DIM if pct is None else INK,
        bold=pct is not None,
    )
    if active:
        text(x + 165, 386, 'W użyciu', 14, GREEN, anchor='rt')
# Save both real navigation states, not simultaneous UI elements.
base = im.copy()
rect((375, 454, 425, 458), '#6d9186', 2)
im.resize((800, 480), Image.Resampling.LANCZOS).save(OUT / 'dashboard-refined-hidden.png')
im = base
d = ImageDraw.Draw(im)
for i, label in enumerate(['Wydruk', 'AMS', 'Szczegóły', 'Ustawienia']):
    x = 20 + i * 194
    rect((x, 432, x + 178, 474), '#184032' if i == 0 else CARD, 10)
    text(x + 89, 445, label, 16, GREEN if i == 0 else DIM, anchor='mt')
im.resize((800, 480), Image.Resampling.LANCZOS).save(OUT / 'dashboard-refined-navigation.png')
print(OUT / 'dashboard-refined-hidden.png')
print(OUT / 'dashboard-refined-navigation.png')
