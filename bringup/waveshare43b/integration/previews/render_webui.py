"""Prepare the actual localized WebUI with synthetic template values for browser review.
No device connections, credentials or live settings are read.
"""
from pathlib import Path
import re, sys
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import localize_web as loc
out=Path(sys.argv[1]) if len(sys.argv)>1 else Path('/tmp/bambu-webui-preview')
out.mkdir(parents=True,exist_ok=True)
source=(ROOT/'include/web_pages.h').read_text()
# Select the full-feature board, with automatic update disabled like the board build.
active=True;stack=[];lines=[]
for line in source.splitlines(True):
 if re.match(r'#if(?:def)? ',line):
  stack.append(active);active=active and 'ENABLE_OTA_AUTO' not in line
 elif line.startswith('#else'):active=stack[-1] and not active
 elif line.startswith('#endif'):active=stack.pop()
 elif active:lines.append(line)
raw=re.findall(r'R"rawliteral\((.*?)\)rawliteral"',''.join(lines),re.S)
html=loc.markup(''.join(raw[1:]),loc.catalog())
fw=re.search(r'-DFW_VERSION=\\?"([^"\\]+)',(ROOT/'boards/ws_lcd_43b.ini').read_text())
values={'BOARD':'ws_lcd_43b','FW_VER':fw[1] if fw else 'dev','FLASHMB':'16','OTASLOT':'3145728','ISROUND':'0','FIXED_AUDIO':'0','HMSFULL':'1','BOARDBTN':'0',
 'MAXP':'2','PNAME':'Bambu P2S','IP':'192.0.2.42','SERIAL':'DEMO00000000001','SSID':'Domowa sieć','STATUS_CLASS':'status-pill status-ok','STATUS_TEXT':'Połączono · sieć lokalna',
 'MODE_LOCAL':'selected','NET_DHCP':'selected','BRIGHT':'255','NBRIGHT':'255','SSBRIGHT':'255','USE24H':'checked','SHOWIP':'checked','CSSVER':'preview','JSVER':'preview',
 'HMS_NAV':'<button class="nav-item" type="button" data-section="errors"><span>Błędy drukarki</span></button>',
 'PRINTER_TABS':'<button class="tab-btn" id="tab1" type="button" onclick="selectPrinterTab(1)">Drukarka 2</button>',
 'NIGHT_START_OPTS':'<option value="22">22:00</option>','NIGHT_END_OPTS':'<option value="7">07:00</option>'}
html=re.sub(r'%([A-Z][A-Z0-9_]*)%',lambda m:values.get(m[1],''),html)
(out/'index.html').write_text(html)
(out/'setup.html').write_text(loc.markup(raw[0],loc.catalog()))
(out/'app.css').write_text((ROOT/'web/app.css').read_text())
(out/'app.js').write_text(loc.javascript((ROOT/'web/app.js').read_text()))
print(out)
