#!/usr/bin/env python3
"""Preview real thermal/AMS dashboard functions with synthetic telemetry.

Uses the firmware's VLW font masks and RGB565 sprite decoder on the existing
boot preview Canvas. Only the thermal and AMS regions are rendered; empty areas
of the 800x480 frame are intentionally outside scope. This is not an LCD capture.
An alternate include directory overrides the generated artwork header only.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile

from render_boot import png_from_ppm

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
FUNCTIONS = (
    'uint16_t v2Ink()', 'uint16_t v2Dim()', 'uint16_t v2Accent()',
    'void v2Clear(', 'int v2Text(',
    'template <class Field>\nconst char *missing(',
    'const MonitorAmsUnit *amsUnit(',
    'template<class Field>\nvoid amsReadingAge(',
    'void dashboardTemperature(', 'uint16_t dashboardSlotBg(',
    'void dashboardSlotCard(', 'void dashboardAms(',
)


def function(source, signature):
    """Extract one complete C++ function, ignoring braces in strings/comments."""
    start = source.index(signature)
    opening = source.index('{', start)
    token = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{}]', re.S)
    depth = 0
    for match in token.finditer(source, opening):
        if match[0] == '{':
            depth += 1
        elif match[0] == '}':
            depth -= 1
            if depth == 0:
                return source[start:match.end()]
    raise ValueError('Unterminated production function: ' + signature)


def canvas_source():
    source = (HERE / 'boot_preview.cpp').read_text()
    canvas = source[source.index('uint32_t be32('):source.index('#include "production_boot_text.h"')]
    # The dashboard also draws the small filament bars. Keep these host-only
    # primitives consistent with the rounded geometry of the reused Canvas.
    extra = '''
  void fillRect(int x,int y,int w,int h,uint16_t c){
    for(int yy=0;yy<h;++yy)for(int xx=0;xx<w;++xx)put(x+xx,y+yy,c);
  }
  void fillRoundRect(int x,int y,int w,int h,int r,uint16_t c){
    for(int yy=0;yy<h;++yy)for(int xx=0;xx<w;++xx)
      if(rounded(xx,yy,w,h,r))put(x+xx,y+yy,c);
  }
'''
    marker = '  void drawRoundRect('
    if canvas.count(marker) != 1:
        raise ValueError('Boot Canvas structure changed; review host adapter')
    return canvas.replace(marker, extra + marker, 1)


PRELUDE = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>
namespace lgfx {struct rgb565_t {uint16_t raw;};}
#include "ws43b_native_scene.h"
#include "ws43b_ui_icons.h"
#include "ws43b_style.h"
#include "ws43b_repaint_plan.h"
#include "fonts/ws43b_dashboard_v2.h"
using String=std::string;
constexpr int FONT_NONE=0,TL_DATUM=0,MAX_ACTIVE_PRINTERS=1;
constexpr uint16_t BG=ws43b_style::background,INK=ws43b_style::ink,
 DIM=ws43b_style::dim,ACCENT=ws43b_style::mint,WARN=0xf5cb;
struct {unsigned displayIndex=0;}rotState;
unsigned selectedAms=0;
using UiAsset=ws43b_assets::Asset;
const char *ws43bText(const char *pl,const char*){return pl;}
'''

FIXTURE = r'''
int main(int argc,char **argv){
  assert(argc==2);
  constexpr uint32_t now=1000;
  BambuMonitorTelemetry m;
  m.hasUsefulData=true;m.lastUsefulMs=now;
  m.nozzleTemp.set(140,now);m.nozzleTarget.set(140,now);
  m.bedTemp.set(55,now);m.bedTarget.set(55,now);m.chamberTemp.set(34,now);
  auto &unit=m.amsUnits[0];unit.used=true;unit.id=0;unit.present.set(true,now);
  const char *materials[]={"PETG Basic","PLA Matte","PLA Basic","PLA"};
  const int remaining[]={12,9,0};
  for(int i=0;i<4;++i){
    auto &tray=unit.trays[i];tray.present.set(true,now);tray.type.set(materials[i],now);
    if(i<3)tray.remain.set(remaining[i],now);
  }
  // No invented selected slot, material color, humidity or AMS temperature.
  // Unknown remaining for slot 4 and known zero for slot 3 remain distinct.
  assert(!m.activeTrayRaw.valid&&!unit.trays[3].remain.valid);
  ws43b_native::screen(tft,BG);
  dashboardTemperature(0,66,"DYSZA",m.nozzleTemp,m.nozzleTarget,true,now);
  dashboardTemperature(1,150,"STÓŁ",m.bedTemp,m.bedTarget,true,now);
  MonitorField<float> noTarget;
  dashboardTemperature(2,234,"KOMORA",m.chamberTemp,noTarget,true,now);
  dashboardAms(m,true,now,ws43b_repaint::All);
  assert(tft.outside==0);
  tft.ppm(argv[1]);
}
'''


def compile_preview(directory, artwork_header):
    # Copy the three include parents as well: quote includes resolve beside
    # their parent header before searching -I, so an -I override alone is wrong.
    for name in ('ws43b_native_scene.h', 'ws43b_ui_icons.h', 'ws43b_visual_assets.h'):
        shutil.copyfile(ROOT / 'include' / name, directory / name)
    shutil.copyfile(artwork_header, directory / 'ws43b_visual_assets_data.h')
    (directory / 'pgmspace.h').write_text(
        '#pragma once\n#define PROGMEM\n'
        '#define pgm_read_byte(p) (*static_cast<const uint8_t *>(p))\n')
    source = (ROOT / 'src/display_ws43b.cpp').read_text()
    config = (ROOT / 'include/config.h').read_text()
    defaults = '\n'.join(re.search(r'^#define ' + name + r'\s+[^\n]+', config, re.M)[0]
                         for name in ('CLR_TEXT_DEFAULT', 'CLR_TEXT_DIM_DEFAULT'))
    code = PRELUDE + defaults + '\n' + canvas_source() + '\n'
    code += '\n'.join(function(source, signature) for signature in FUNCTIONS) + '\n' + FIXTURE
    (directory / 'dashboard_icons.cpp').write_text(code)
    binary = directory / 'dashboard_icons'
    subprocess.run(['clang++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                    '-I', str(directory), '-I', str(ROOT / 'include'),
                    str(directory / 'dashboard_icons.cpp'), '-o', str(binary)], check=True)
    return binary


def crop_ppm(source, destination, box):
    magic, size, maximum, pixels = source.read_bytes().split(b'\n', 3)
    width, height = map(int, size.split())
    x, y, w, h = box
    if magic != b'P6' or maximum != b'255' or len(pixels) != width * height * 3:
        raise ValueError('Unexpected native preview pixels')
    if min(x, y, w, h) < 0 or x + w > width or y + h > height:
        raise ValueError('Crop outside the native frame')
    rows = b''.join(pixels[((y + row) * width + x) * 3:((y + row) * width + x + w) * 3]
                    for row in range(h))
    destination.write_bytes(f'P6\n{w} {h}\n255\n'.encode() + rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--include-dir', type=Path, default=ROOT / 'include',
                        help='Directory containing an alternate ws43b_visual_assets_data.h')
    args = parser.parse_args()
    artwork = args.include_dir.resolve() / 'ws43b_visual_assets_data.h'
    if not artwork.is_file():
        parser.error('Artwork header not found: ' + str(artwork))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    inputs = [ROOT / 'src/display_ws43b.cpp', ROOT / 'include/config.h',
              HERE / 'boot_preview.cpp', HERE / 'render_boot.py', Path(__file__),
              ROOT / 'include/fonts/ws43b_dashboard_v2.h', artwork]
    inputs.extend(ROOT / 'include' / name for name in
                  ('ws43b_native_scene.h', 'ws43b_ui_icons.h', 'ws43b_visual_assets.h',
                   'ws43b_repaint_plan.h', 'ws43b_style.h', 'bambu_monitor.h',
                   'ws43b_dashboard_policy.h', 'ws43b_live_view.h'))
    record = {'scope': __doc__, 'artwork_header': str(artwork),
              'source_sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
              'fixture': {'thermal': {'nozzle': [140, 140], 'bed': [55, 55], 'chamber': [34, None]},
                          'ams': [['PETG Basic', 12], ['PLA Matte', 9], ['PLA Basic', 0], ['PLA', None]],
                          'active_slot': None, 'colors': 'unknown: native neutral fallback',
                          'ams_temperature': None, 'ams_humidity': None}, 'images': []}
    with tempfile.TemporaryDirectory(prefix='ws43b-dashboard-icons-') as temporary:
        directory = Path(temporary)
        binary = compile_preview(directory, artwork)
        full = directory / 'dashboard-icons.ppm'
        subprocess.run([str(binary), str(full)], check=True)
        for name, box in [('dashboard-icons', (0, 0, 800, 480)),
                          ('thermal-icons', (528, 66, 256, 242)),
                          ('ams-icons', (16, 314, 768, 111))]:
            ppm = directory / (name + '-crop.ppm')
            crop_ppm(full, ppm, box)
            record['images'].append({'name': name, 'box': box,
                                     **png_from_ppm(ppm, args.output_dir / (name + '.png'))})
    (args.output_dir / 'preview-result.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({'output': str(args.output_dir), 'images': len(record['images']),
                      'scope': 'synthetic thermal and AMS regions; actual production functions/fonts/assets'}))


if __name__ == '__main__':
    main()
