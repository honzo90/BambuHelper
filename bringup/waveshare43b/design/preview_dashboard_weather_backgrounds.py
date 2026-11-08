"""Generate synthetic UI proposals from the layout source, never from a screenshot.
No firmware changes. Background is static; cards are opaque.
"""

from pathlib import Path

source_path = Path(__file__).with_name('preview_dashboard_refined.py')
source = source_path.read_text()
background = r'''
# Static atmosphere behind opaque cards and all foreground text.
night=MODE=='night'
top=(11,20,34) if night else (15,34,42)
bottom=(7,16,23) if night else (8,23,25)
if MODE=='neutral':top=bottom=(8,23,25)
for y in range(480):
 t=y/479
 c=tuple(round(a+(b-a)*t) for a,b in zip(top,bottom))
 d.line((0,y*S,800*S,y*S),fill=c,width=S)
def cloud(x,y,k=1,c='#233b46'):
 circle(x-30*k,y,19*k,c);circle(x,y-13*k,29*k,c);circle(x+33*k,y,21*k,c)
 rect((x-45*k,y-2*k,x+49*k,y+19*k),c,14)
if MODE=='clear':
 circle(399,28,48,'#222f32');circle(399,28,33,'#39403a');circle(399,28,22,'#666851')
elif MODE in ('cloud','rain','snow'):
 cloud(402,27,1.4,'#20343e');cloud(353,52,.8,'#29414a')
 cloud(638,432,1.5,'#152d33')
 if MODE=='rain':
  for x,y in [(293,52),(323,69),(441,61),(468,53),(503,177),(797,206),(8,255),(584,449),(657,461),(714,448)]:
   line([(x,y),(x-5,y+10)],'#3c5962')
 if MODE=='snow':
  for x,y in [(293,52),(323,69),(459,53),(503,177),(794,206),(8,255),(584,449),(657,461),(714,448)]:
   circle(x,y,1.5,'#5b7076')
elif MODE=='night':
 circle(410,33,26,'#819395');circle(422,24,25,'#0b1522')
 for x,y in [(280,23),(322,47),(461,24),(363,16),(500,18),(798,304),(588,442),(207,321)]:
  circle(x,y,1,'#536975')
 cloud(375,64,.65,'#182e39')
'''
for mode, description, temp in [
    ('cloud', 'pochmurno', '11°C'),
    ('clear', 'bezchmurnie', '18°C'),
    ('rain', 'deszcz', '9°C'),
    ('snow', 'śnieg', '0°C'),
    ('night', 'bezchmurnie', '8°C'),
    ('neutral', 'pogoda: —', '—'),
]:
    s = source.replace(
        '# Compact weather stays separate',
        "MODE=" + repr(mode) + '\n' + background + '\n# Compact weather stays separate',
    )
    s = s.replace("'Schanbach · pochmurno'", repr('Schanbach · ' + description)).replace(
        "'11°C'", repr(temp)
    )
    if mode not in ('night', 'neutral'):
        s = s.replace("'20:03'", "'13:03'").replace("'Koniec ok. 21:28'", "'Koniec ok. 14:28'")
    icon = "circle(518,32,6,DIM);circle(527,26,9,DIM);circle(536,32,6,DIM)"
    if mode == 'clear':
        s = s.replace(icon, "circle(527,29,9,DIM)")
    if mode == 'night':
        s = s.replace(icon, "circle(525,28,10,DIM);circle(530,25,9,'#101e2c')")
    if mode == 'neutral':
        s = s.replace(icon, '')
    s = s.replace('dashboard-refined-hidden.png', 'dashboard-weather-' + mode + '.png').replace(
        'dashboard-refined-navigation.png', 'dashboard-weather-' + mode + '-navigation.png'
    )
    exec(
        compile(s, str(source_path), 'exec'), {'__file__': str(source_path), '__name__': '__main__'}
    )
