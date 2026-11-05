"""Synthetic data; geometry follows AMS/details implementation, not a device capture."""
from pathlib import Path
base=Path(__file__).with_name('preview_settings_menu.py').read_text().split("text(44,91")[0]
for page in ('ams','details'):
 exec(compile(base,'preview_settings_menu.py','exec'))
 if page=='ams':
  text(24,96,'AMS · ID 0',18);rect((550,86,776,124),'#102329');text(562,95,'Kolejny AMS >',18)
  for i,(title,value) in enumerate([('TEMPERATURA','32°C'),('WILGOTNOŚĆ','26% RH'),('SUSZENIE · POZOSTAŁO','0 min')]):
   x=24+256*i;rect((x,136,x+240,196),'#102329');text(x+14,143,title,14,'#a6b8ba');text(x+14,163,value,24)
  for i,(name,pct,color,active) in enumerate([('PLA Basic',100,'#eeeeee',False),('PLA Matte',68,'#b8d76a',True),('PETG Basic',0,'#343d46',False),('PLA',None,'#ff8539',False)]):
   x=24+190*i;rect((x,210,x+182,418),'#102329')
   if pct:
    from PIL import Image,ImageDraw
    mask=Image.new('L',(364,416));md=ImageDraw.Draw(mask);md.rounded_rectangle((0,0,363,415),28,fill=255);md.rectangle((round(364*pct/100),0,364,416),fill=0);im.paste('#164b3a',(x*2,420),mask)
   if active:d.rounded_rectangle((x*2,420,(x+182)*2,836),28,outline='#65d7af',width=2)
   d.ellipse(((x+9)*2,448,(x+19)*2,468),fill=color)
   text(x+26,219,f'SLOT {i+1}',14,'#a6b8ba');text(x+12,253,name,18)
   text(x+12,296,'Brak danych' if pct is None else f'{pct}%',14 if pct is None else 30)
   text(x+12,343,'Pozostało',14,'#a6b8ba')
   if active:text(x+12,383,'W użyciu',18,'#65d7af')
 else:
  rect((24,86,776,206),'#102329');text(40,99,'ZADANIE',14,'#a6b8ba');text(612,99,'Wskaźniki >',14)
  text(40,131,'Obudowa sterownika — wersja końcowa',18);text(40,163,'Panel przedni i uchwyt',18)
  values=[('WARSTWA / RAZEM','218 / 291'),('TEMP. KOMORY','31°C'),('TRYB PRĘDKOŚCI','Standard'),('NAWIEW NA WYDRUK','60%'),('WENT. POMOCNICZY','50%'),('WENTYLATOR KOMORY','0%')]
  for i,(title,value) in enumerate(values):
   x=24+(i%3)*256;y=218 if i<3 else 326
   rect((x,y,x+240,y+96),'#102329');text(x+16,y+12,title,14,'#a6b8ba');text(x+16,y+39,value,30)
   if i>=3:
    rect((x+16,408,x+224,412),'#294048',2)
    if i<5:rect((x+16,408,x+16+208*(.6 if i==3 else .5),412),'#65d7af',2)
 for i,title in enumerate(['Wydruk','AMS','Szczegóły','Ustawienia']):
  x=24+190*i;rect((x,435,x+178,473),'#164b3a' if i==(1 if page=='ams' else 2) else '#102329',8);text(x+12,445,title,18)
 out=Path(__file__).with_name(page+'-redesigned.png');im.resize((800,480),Image.Resampling.LANCZOS).save(out);print(out)
