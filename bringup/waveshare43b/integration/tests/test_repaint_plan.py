"""Selective repaint preserves field freshness, age labels and scene dependencies."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class RepaintPlan(unittest.TestCase):
    def test_regions_freshness_and_retained_canvas(self):
        code = r'''
#define bit(b) (1UL << (b)) // Arduino compatibility: this macro must stay untouched.
#include "ws43b_repaint_plan.h"
#include <cassert>
#include <cstring>
using namespace ws43b_repaint;
using ws43b_live::View;
int main() {
  BambuMonitorTelemetry m;
  m.hasUsefulData=true;m.lastUsefulMs=1000;
  m.status.set("RUNNING",1000);m.progress.set(50,1000);
  m.remainingMinutes.set(45,1000);m.printStage.set(0,1000);
  m.subtaskName.set("A long job name",1000);m.layerNum.set(50,1000);m.totalLayers.set(100,1000);
  m.nozzleTemp.set(220,1000);m.nozzleTarget.set(220,1000);
  m.bedTemp.set(60,1000);m.bedTarget.set(60,1000);m.chamberTemp.set(36,1000);
  m.speedLevel.set(2,1000);m.partFanPct.set(40,1000);
  auto &u=m.amsUnits[0];u.used=true;u.id=0;u.present.set(true,1000);
  u.temp.set(40,1000);u.humidityRaw.set(14,1000);u.humidity.set(1,1000);
  u.dryRemainMin.set(30,1000);m.activeTrayRaw.set(1,1000);
  for(auto &tray:u.trays) {
    tray.present.set(true,1000);tray.type.set("PETG",1000);
    tray.colorRgb565.set(0x07e0,1000);tray.remain.set(80,1000);
  }
  auto key=[&](View view,uint32_t now=1100,bool online=true){return keys(m,view,0,online,now);};
  Cache cache;auto initial=key(View::Dashboard);
  assert(cache.dirty(initial)==All);cache.commit(initial);assert(cache.dirty(initial)==0);
  // Identical MQTT deltas renew observations, but need no new pixels.
  m.nozzleTemp.set(220,1200);m.lastUsefulMs=1200;
  assert(cache.dirty(key(View::Dashboard,1200))==0);
  m.nozzleTemp.set(222,1300);
  assert(cache.dirty(key(View::Dashboard,1300))==regionBit(Region::Nozzle));
  cache.commit(key(View::Dashboard,1300));
  // Thermal state must still leave its candidate dwell on unchanged input.
  auto thermal=regionBit(Region::Nozzle)|regionBit(Region::Bed)|regionBit(Region::Chamber);
  assert(cache.dirty(key(View::Dashboard,2300))==thermal);
  cache.commit(key(View::Dashboard,2300));
  auto beforeHidden=key(View::Dashboard,2300);
  m.auxFanPct.set(50,2300);assert(beforeHidden==key(View::Dashboard,2300));
  m.bedTarget.set(0,2300);assert(cache.dirty(key(View::Dashboard,2300))==regionBit(Region::Bed));
  cache.commit(key(View::Dashboard,2300));
  // Hidden legacy humidity does not invalidate a fresh visible RH card.
  u.humidity.set(5,2300);assert(cache.dirty(key(View::Dashboard,2300))==0);
  u.humidityRaw.set(15,2300);
  assert(cache.dirty(key(View::Dashboard,2300))==regionBit(Region::AmsSummary));
  cache.commit(key(View::Dashboard,2300));
  u.trays[3].remain.set(79,2300);
  assert(cache.dirty(key(View::Dashboard,2300))==regionBit(Region::Ams3));
  cache.commit(key(View::Dashboard,2300));
  u.trays[1].colorRgb565.set(0xf800,2300);
  assert(cache.dirty(key(View::Dashboard,2300))==(regionBit(Region::Ams1)|regionBit(Region::Primary)));
  cache.commit(key(View::Dashboard,2300));
  m.activeTrayRaw.set(3,2300);
  assert(cache.dirty(key(View::Dashboard,2300))==
    (regionBit(Region::Ams1)|regionBit(Region::Ams3)|regionBit(Region::Primary)));
  // AMS units can be replaced while their displayed numeric values match.
  cache.commit(key(View::Ams,2300));u.id=2;
  assert(cache.dirty(key(View::Ams,2300))&regionBit(Region::AmsSummary));
  assert(cache.dirty(key(View::Ams,2300))&regionBit(Region::Ams0));
  u.present.set(false,2300);auto absent=key(View::Ams,2300);
  u.temp.set(70,2300);assert(absent==key(View::Ams,2300));
  u.present.set(true,2300);

  // Details also uses pre-rounded values, even if raw percentage is unchanged.
  cache.commit(key(View::Details,2300));m.partFanRoundedPct=41;
  assert(cache.dirty(key(View::Details,2300))==regionBit(Region::DetailsBody));
  cache.commit(key(View::Details,2300));
  m.nozzleTemp.set(240,2300);assert(cache.dirty(key(View::Details,2300))==0);
  m.subtaskName.set("Short",2300);
  assert(cache.dirty(key(View::Details,2300))==regionBit(Region::DetailsBody));

  // Stale age text advances on its visible unit, not every telemetry timestamp.
  MonitorField<float> fieldValue;fieldValue.set(40,1000);
  auto fieldKey=[&](uint32_t now,bool online){uint32_t hash=2166136261u;field(hash,fieldValue,online,now);return hash;};
  assert(fieldKey(1500,false)==fieldKey(1999,false));
  assert(fieldKey(1999,false)!=fieldKey(2000,false));
  assert(fieldKey(61001,true)==fieldKey(61999,true));
  assert(fieldKey(119999,true)!=fieldKey(121000,true));
  assert(fieldKey(3601000,true)==fieldKey(3661000,true));
  assert(fieldKey(60999,true)!=fieldKey(61001,true));
  fieldValue.invalidate(62000);assert(fieldKey(63000,true)==fieldKey(100000,true));
  fieldValue.set(0,0xfffffff0u);
  assert(fieldKey(20,true)==fieldKey(100,true)); // wrap-safe fresh zero

  // No aggregate signature may make cached readings appear freshly observed.
  unsigned char snapshot[sizeof m];memcpy(snapshot,&m,sizeof m);
  auto stale=key(View::Dashboard,70000);
  (void)keys(m,View::Ams,0,false,70000);(void)keys(m,View::Details,0,true,70000);
  assert(memcmp(snapshot,&m,sizeof m)==0);
  assert(stale!=key(View::Dashboard,70000,false));
  cache.commit(stale);m.newSession();assert(cache.dirty(key(View::Dashboard,70000))!=0);
  cache.commit(key(View::Dashboard,70000));cache.invalidate();
  assert(cache.dirty(key(View::Dashboard,70000))==All);
  cache.commit(key(View::Dashboard,70000));assert(cache.dirty(key(View::Dashboard,70000),true)==All);
  // Caller-owned context can invalidate exactly one area (e.g. weather/time).
  auto contextual=key(View::Dashboard,70000);add(contextual[0],uint32_t(123));
  assert(cache.dirty(contextual)==regionBit(Region::Header));
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
