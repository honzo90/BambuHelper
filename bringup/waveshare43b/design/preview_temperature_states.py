"""Static UI concept, synthetic data only. No firmware or device access.
Render with Pillow 12.3.0 and repository Inter font files.
"""
from pathlib import Path
import argparse
parser=argparse.ArgumentParser()
parser.add_argument("--cooling",action="store_true")
COOLING=parser.parse_args().cooling
from PIL import Image,ImageDraw,ImageFont
S=3
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
im=Image.new('RGB',(800*S,480*S),'#071519');d=ImageDraw.Draw(im)
BG='#071519';CARD='#102329';INK='#edf9f4';DIM='#8ca8a5';GREEN='#4de0a0';LINE='#22383d'
def font(size,bold=False):return ImageFont.truetype(str(ROOT/'fonts'/('Inter-Bold.ttf' if bold else 'Inter-Regular.ttf')),round(size*S))
def text(x,y,value,size=14,color=INK,bold=False,anchor='lt'):
 d.text((x*S,y*S),value,font=font(size,bold),fill=color,anchor=anchor)
def rect(box,fill,r=0,outline=None,width=1):
 box=tuple(round(v*S) for v in box)
 if r:d.rounded_rectangle(box,r*S,fill=fill,outline=outline,width=width*S)
 else:d.rectangle(box,fill=fill,outline=outline,width=width*S)
def line(points,color=LINE,width=1):d.line([(round(x*S),round(y*S)) for x,y in points],fill=color,width=width*S)
def circle(x,y,r,color):d.ellipse(((x-r)*S,(y-r)*S,(x+r)*S,(y+r)*S),fill=color)
def level_card(box,percent,radius=12,active=False):
 # Same horizontal quantity language across print progress and filament levels.
 x0,y0,x1,y1=box;w=round((x1-x0)*S);h=round((y1-y0)*S)
 rect(box,CARD,radius)
 if percent is not None and percent>0:
  width=round(w*max(0,min(100,percent))/100)
  mask=Image.new('L',(w,h));md=ImageDraw.Draw(mask)
  md.rounded_rectangle((0,0,w-1,h-1),radius*S,fill=255)
  if width<w:md.rectangle((width,0,w,h),fill=0)
  fill=Image.new('RGB',(w,h));fd=ImageDraw.Draw(fill)
  left=(17,75,57) if active else (15,58,47)
  right=(23,98,70) if active else (18,79,57)
  for x in range(width):
   t=x/max(1,width-1);c=tuple(round(a+(b-a)*t) for a,b in zip(left,right))
   fd.line((x,0,x,h),fill=c)
  im.paste(fill,(round(x0*S),round(y0*S)),mask)
 if active:rect(box,None,radius,GREEN)
# Header
text(24,24,'P2S',25,bold=True)
rect((92,23,213,49),'#12372c',13);circle(108,36,3,GREEN);text(119,29,'Zakończony' if COOLING else 'Drukowanie',12,GREEN)
circle(563,36,3,GREEN);text(575,30,'Dane: 1 s temu',12,DIM)
line([(690,24),(690,48)])
text(776,24,'14:32',22,INK,anchor='rt')
line([(24,66),(776,66)])
# Progress hero
level_card((24,84,484,277),100 if COOLING else 76,18,True)
text(44,102,'POSTĘP WYDRUKU',11,DIM,bold=True)
text(40,120,'100' if COOLING else '76',70 if COOLING else 78,INK,bold=True);text(186 if COOLING else 154,148,'%',38,GREEN)
line([(258,133),(258,200)],'#294047')
text(281,128,'Wydruk zakończony' if COOLING else 'Pozostało',12,DIM)
text(279,150,'Stół stygnie' if COOLING else '38 min',25 if COOLING else 32,INK)
text(281,190,'Obserwuj temperaturę' if COOLING else 'Koniec około 15:10',12,DIM)
text(44,219,'Obudowa czujnika',13,DIM)
text(44,248,'200 / 200 warstw' if COOLING else '152 / 200 warstw',12,DIM)
# Independent temperature tiles, state encoded by text + arrow + background.
AMBER='#efc267';AMBER_BG='#3a301d';AMBER_DIM='#c8ae7b'
rows=[('Dysza','87°','↓ Chłodzenie · cel 0°C',True),
      ('Stół','48°','↓ Chłodzenie · cel 0°C',True),
      ('Komora','34°','Temperatura',False)] if COOLING else [
      ('Dysza','210°','↑ Nagrzewanie · cel 220°C',True),
      ('Stół','55°','Stabilna · cel 55°C',False),
      ('Komora','34°','Temperatura',False)]
for i,(label,value,subtitle,changing) in enumerate(rows):
 y=84+i*66
 rect((500,y,776,y+61),AMBER_BG if changing else CARD,12)
 circle(518,y+19,3,AMBER if changing else GREEN if i==1 else '#7abed0')
 text(530,y+10,label,13,AMBER if changing else INK)
 text(758,y+7,value,28,AMBER if changing else INK,anchor='rt')
 text(518,y+42,subtitle,11,AMBER_DIM if changing else DIM)
# AMS section and tray cards
text(24,294,'AMS 2 Pro',16,INK,bold=True)
text(776,298,'32°C  ·  27% RH',12,DIM,anchor='rt')
trays=[('1','PLA Basic','100%','#e5eadc',False),('2','PLA Matte','68%','#bee44b',not COOLING),('3','PETG Basic','42%','#1e2226',False),('4','PLA','Brak danych','#ee7249',False)]
for i,(num,kind,remain,color,active) in enumerate(trays):
 x=24+i*190
 level_card((x,326,x+182,404),int(remain[:-1]) if remain.endswith('%') else None,12,active)
 text(x+13,338,num,11,GREEN if active else DIM,bold=True)
 circle(x+38,345,5,color)
 text(x+51,337,kind,12,INK)
 text(x+13,368,remain,19 if remain.endswith('%') else 13,INK if remain.endswith('%') else DIM)
 if active:
  text(x+168,374,'W użyciu',10,GREEN,anchor='rt')
# Hidden navigation keeps all data at the same coordinates.
rect((375,456,425,460),'#426059',2)
# 800x480 artifact, high-quality rasterization of the proposed vector-like UI.
im=im.resize((800,480),Image.Resampling.LANCZOS)
output=OUT/('dashboard-cooling-example.png' if COOLING else 'dashboard-heating-example.png')
im.save(output)
print(output)
