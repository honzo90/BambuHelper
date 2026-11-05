"""Synthetic settings home preview using the implemented 800x480 geometry."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
root=Path(__file__).resolve().parents[3]; out=Path(__file__).with_name('settings-menu.png')
im=Image.new('RGB',(1600,960),'#081018');d=ImageDraw.Draw(im)
def rect(box,c,r=12):d.rounded_rectangle(tuple(v*2 for v in box),r*2,fill=c)
def text(x,y,s,size=18,c='#edf5ef'):
 f=ImageFont.truetype(str(root/'fonts/Inter-Regular.ttf'),size*2)
 d.text((x*2,y*2),s,font=f,fill=c)
text(24,24,'P2S',30);text(224,31,'Drukowanie',18,'#65d7af');text(697,24,'21:45',24)
d.ellipse((1334,64,1354,84),fill='#65d7af');d.line((48,132,1552,132),fill='#294048',width=2)
text(44,91,'Ustawienia',24)
for i,(title,hint) in enumerate([('Wygląd','Motyw kolorystyczny'),('Zegar i ekran','Czas bez dotyku i wygaszanie'),('Pogoda i noc','Pogoda, słońce i czas nocny'),('Język i dane','Polski / English, wentylatory')]):
 x=24+(i%2)*384;y=140+(i//2)*132
 rect((x,y,x+368,y+114),'#102329');text(x+20,y+20,title,24);text(x+20,y+65,hint,14,'#a6b8ba')
for i,title in enumerate(['Wydruk','AMS','Szczegóły','Ustawienia']):
 x=24+190*i;rect((x,435,x+178,473),'#164b3a' if i==3 else '#102329',8);text(x+12,445,title,18)
im.resize((800,480),Image.Resampling.LANCZOS).save(out)
print(out)
