"""Active material captions repaint without polling or renewing AMS metadata."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class ActiveFilamentMetadata(unittest.TestCase):
    def test_active_ams_caption_lifecycle_and_recovery_budget(self):
        code = r'''
#include "ws43b_repaint_plan.h"
#include <cassert>
#include <cstring>
using namespace ws43b_repaint;
using ws43b_live::View;
int main() {
  constexpr uint32_t now=100000,old=100;
  BambuMonitorTelemetry m;m.hasUsefulData=true;m.lastUsefulMs=now;
  m.status.set("RUNNING",now);m.progress.set(50,now);
  m.activeTrayRaw.set(7*4+1,now);
  auto &first=m.amsUnits[0];first.used=true;first.id=0;
  first.present.set(true,now);first.temp.set(40,now);
  auto &active=m.amsUnits[3];active.used=true;active.id=7;
  active.present.set(true,old);active.temp.set(45,old);
  auto &tray=active.trays[1];tray.present.set(true,old);
  tray.type.set("PETG",old);tray.colorRgb565.set(0x07e0,old);
  auto key=[&]{return keys(m,View::Dashboard,0,true,now);};
  auto sig=[&](View view=View::Dashboard){return ws43b_live::signature(m,view,0,true,now);};
  auto color=[&]{uint32_t result=2166136261u;filament(result,m,true);return result;};
  auto refresh=[&]{return ws43b_live::needsRefresh(m,View::Dashboard,0,true,now);};
  Cache cache;cache.commit(key());
  const auto initial=sig(),ams=sig(View::Ams),details=sig(View::Details),sceneColor=color();
  assert(!refresh()); // Hidden AMS temperatures and retained metadata do not poll.
  unsigned visited=0;
  ws43b_live::visitActiveFilamentMetadata(m,[&](const auto &,bool expires){
    assert(!expires);++visited;
  });
  assert(visited==3);

  // Type changes with an identical color must update the primary caption even
  // when the four displayed spool cards belong to another AMS.
  tray.type.set("PLA",old+1);
  assert(sig()!=initial&&sig(View::Ams)==ams&&sig(View::Details)==details);
  assert(cache.dirty(key())==regionBit(Region::Primary));
  assert(color()==sceneColor&&!refresh());cache.commit(key());
  const auto same=sig();tray.type.set("PLA",old+2);
  assert(sig()==same&&cache.dirty(key())==0); // Same stale label, later report.
  const auto snapshot=m;
  (void)sig();(void)key();(void)refresh();
  assert(memcmp(&snapshot,&m,sizeof m)==0);
  assert(tray.type.updatedMs==old+2&&active.present.updatedMs==old);

  // Explicit type deletion removes the old caption; restoring it repaints.
  tray.type.invalidate(now);
  assert(cache.dirty(key())==regionBit(Region::Primary)&&sig()!=same);
  cache.commit(key());tray.type.set("PETG",old);
  assert(cache.dirty(key())==regionBit(Region::Primary));cache.commit(key());

  auto previous=sig();tray.present.set(false,old);
  assert(sig()!=previous&&cache.dirty(key())==regionBit(Region::Primary));
  cache.commit(key());previous=sig();tray.type.set("ASA",old);
  assert(sig()==previous&&cache.dirty(key())==0); // Empty tray hides stale type.
  tray.present.set(true,old);
  assert(sig()!=previous&&cache.dirty(key())==regionBit(Region::Primary));cache.commit(key());
  previous=sig();active.present.set(false,old);
  assert(sig()!=previous&&cache.dirty(key())==regionBit(Region::Primary));
  cache.commit(key());previous=sig();tray.type.set("ABS",old);
  assert(sig()==previous&&cache.dirty(key())==0); // Absent unit hides its tray.
  active.present.set(true,old);cache.commit(key());previous=sig();
  active.used=false;
  assert(sig()!=previous&&cache.dirty(key())==regionBit(Region::Primary));
  active.used=true;cache.commit(key());previous=sig();
  active=MonitorAmsUnit{};
  assert(sig()!=previous&&cache.dirty(key())==regionBit(Region::Primary));

  // External/unknown selection never attributes an arbitrary AMS material.
  m.activeTrayRaw.set(254,now);cache.commit(key());previous=sig();
  active.used=true;active.id=7;active.present.set(true,old);
  active.trays[1].type.set("PETG",old);
  assert(sig()==previous&&cache.dirty(key())==0&&!refresh());
  m.activeTrayRaw.set(29,now);cache.commit(key());previous=sig();
  m.newSession();
  assert(sig()!=previous&&(cache.dirty(key())&regionBit(Region::Primary)));
  assert(!m.activeTrayRaw.valid&&!m.amsUnits[3].used&&!refresh());
}
'''
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p / 'test.cpp').write_text(code)
            result = subprocess.run([
                'clang++', '-std=c++17', '-fsanitize=address,undefined',
                '-I', str(ROOT / 'include'), str(p / 'test.cpp'), '-o', str(p / 'test'),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(p / 'test')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
