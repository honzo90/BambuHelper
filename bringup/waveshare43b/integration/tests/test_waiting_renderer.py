#!/usr/bin/env python3
"""Independent host checks of the production WS43B stale-job saver renderer.

No firmware edits, network calls or hardware access. The existing fixture
provides only display/platform stubs; decisions and rendering come from the
current firmware source and headers. Compiler outputs live in a temporary dir.
"""
import ast
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


def existing_stub():
    fixture = ROOT / 'bringup/waveshare43b/integration/tests/test_combined_saver.py'
    tree = ast.parse(fixture.read_text(), filename=str(fixture))
    values = [node.value.value for node in ast.walk(tree)
              if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == 'stub'
                      for target in node.targets)
              and isinstance(node.value, ast.Constant)
              and isinstance(node.value.value, str)]
    if len(values) != 1:
        raise AssertionError('Expected exactly one literal stub in test_combined_saver.py')
    stub = values[0]
    old = 'return ws43b_view::saver(m,online,now,cooling,alert);'
    new = 'return ws43b_view::saver(m,online,now,cooling,alert,corePrinting);'
    if stub.count(old) != 1:
        raise AssertionError('Existing fixture saverView changed; inspect before adapting')
    stub = stub.replace('bool alert=false,cooling=false;',
                        'bool alert=false,cooling=false,corePrinting=true;')
    stub = stub.replace(old, new)
    # Make whole-clock repaints observable instead of leaving them as a no-op.
    old = 'void drawClockBackground(bool,int,uint32_t){}'
    if stub.count(old) != 1:
        raise AssertionError('Existing fixture clock-background stub changed')
    stub = stub.replace(old, 'unsigned clockBackgrounds=0;\n'
                       'void drawClockBackground(bool,int,uint32_t){++clockBackgrounds;}')
    return stub


def production_renderer():
    source = (ROOT / 'src/display_ws43b.cpp').read_text()
    start = source.index('// The two concurrent activities have independent timers.')
    end = source.index('void setupScreen(', start)
    progress = source.index('bool clockHasProgress(')
    progress_end = source.index('bool coolingView(', progress)
    return source[progress:progress_end] + source[start:end]


CASES = r'''
#include <cstdlib>
#include <iostream>

static const char *qCase="initialization";
static unsigned qChecks=0;
void qRequire(bool condition,const char *message) {
  ++qChecks;
  if(condition)return;
  std::cerr<<"FAIL ["<<qCase<<"] "<<message<<"\nRendered texts:\n";
  for(const auto &text:texts)std::cerr<<"  "<<text<<"\n";
  std::exit(1);
}
bool qHas(const char *needle) {
  for(const auto &text:texts)if(text.find(needle)!=std::string::npos)return true;
  return false;
}
bool qExact(const char *needle) {
  for(const auto &text:texts)if(text==needle)return true;
  return false;
}
bool qHistorical(const char *value) {
  for(const auto &text:texts)
    if(text.find(value)!=std::string::npos &&
       (text.find("Ostatni")!=std::string::npos || text.find("Ostatnio")!=std::string::npos))return true;
  return false;
}
void qRender(BambuMonitorTelemetry &m,bool online,uint32_t now,bool partial=false) {
  texts.clear();clears.clear();printingAnimations=0;clockBackgrounds=0;
  clockScreen(m,online,now,partial);
}
BambuMonitorTelemetry qJob(const char *state,unsigned progress=3,bool drying=false) {
  BambuMonitorTelemetry m;
  m.status.set(state,100);m.progress.set(progress,100);m.remainingMinutes.set(864,100);
  if(drying) {
    auto &unit=m.amsUnits[0];unit.used=true;unit.id=128;
    unit.dryRemainMin.set(981,70000);unit.temp.set(55,70000);unit.humidityRaw.set(14,70000);
  }
  return m;
}
void qPartial(BambuMonitorTelemetry &m,bool drying) {
  // Any active print pixels in the ordinary combined print region would
  // change with time. A waiting marker may remain static, while AMS animates.
  const int x=drying?250:109,y=drying?258:222,w=drying?112:168,h=drying?104:156;
  tft.capture(x,y,w,h);qRender(m,true,70001,true);const auto first=tft.scene;
  qRequire(texts.empty(),"partial waiting frame rewrote labels or clock digits");
  qRequire(clockBackgrounds==0,"partial waiting frame repainted clock background");
  qRequire(printingAnimations==0,"partial waiting frame started printing animation");
  for(const auto &rect:clears)
    qRequire(rect.y>=220,"partial waiting frame cleared the clock region");
  tft.capture(x,y,w,h);qRender(m,true,70777,true);
  qRequire(texts.empty() && clockBackgrounds==0,"later partial frame rewrote clock or text");
  qRequire(printingAnimations==0,"later partial frame started printing animation");
  qRequire(tft.scene==first,"printing-region pixels animate while waiting for job data");
  for(const auto &rect:clears)
    qRequire(rect.y>=220,"later partial frame cleared the clock region");
}
void qWaiting(const char *state,bool drying) {
  qCase=drying?"stale job with fresh AMS":"stale job without AMS";
  auto m=qJob(state,3,drying);
  qRequire(saverView(m,true,70000)==ws43b_view::Saver::Waiting,"stale active job is not Saver::Waiting");
  qRender(m,true,70000);
  qRequire(qHas("Oczekiwanie na dane"),"missing explicit waiting-for-data heading");
  qRequire(qHistorical("3%"),"historical progress lacks its Ostatni/Ostatnio label");
  qRequire(qHistorical("14 h 24 min"),"historical ETA lacks its Ostatni/Ostatnio label");
  qRequire(!qExact("3%"),"cached percentage is displayed as a fresh unlabelled value");
  qRequire(printingAnimations==0,"waiting job started printing animation");
  qRequire(qHas("SUSZENIE")==drying,"fresh AMS drying visibility disagrees with input");
  qRequire(qHas("16 h 21 min")==drying,"fresh AMS timer is missing or fabricated");
  qPartial(m,drying);

  qCase="fresh job delta resumes ordinary printing";
  // A progress-only delta must renew the unchanged cached RUNNING/PREPARE.
  m.progress.set(4,71000);qRender(m,true,71000);
  qRequire(saverView(m,true,71000)==ws43b_view::Saver::Print,"fresh job delta did not restore Saver::Print");
  qRequire(qExact("4%") && !qHas("Oczekiwanie na dane"),"fresh progress remains labelled as waiting/history");

  qCase="valid zero progress remains historical zero";
  auto zero=qJob(state,0,drying);qRender(zero,true,70000);
  qRequire(qHistorical("0%") && !qExact("0%"),"valid zero progress must remain an explicitly historical zero");
  qRequire(!printingAnimations,"historical zero started printing animation");

  qCase="missing progress and ETA are not synthetic zeros";
  auto unknown=qJob(state,3,drying);
  unknown.progress.invalidate(101);unknown.remainingMinutes.invalidate(101);
  qRender(unknown,true,70000);
  qRequire(saverView(unknown,true,70000)==ws43b_view::Saver::Waiting,"unknown fields incorrectly end a cached active job");
  qRequire(qHas("Oczekiwanie na dane"),"unknown fields lost waiting heading");
  qRequire(!qHas("0%") && !qHas("3%") && !qHas("0 h 00 min") && !qHas("14 h 24 min"),
           "missing progress/ETA fabricated zero or leaked invalid historical value");
  qRequire(!printingAnimations,"missing fields started printing animation");

  qCase="only progress is unknown";
  auto noProgress=qJob(state,3,drying);noProgress.progress.invalidate(101);
  qRender(noProgress,true,70000);
  qRequire(!qHas("3%") && !qHas("0%") && qHistorical("14 h 24 min"),
           "unknown progress contaminated otherwise-valid historical ETA");
  qCase="only ETA is unknown";
  auto noEta=qJob(state,3,drying);noEta.remainingMinutes.invalidate(101);
  qRender(noEta,true,70000);
  qRequire(qHistorical("3%") && !qHas("14 h 24 min") && !qHas("0 h 00 min"),
           "unknown ETA contaminated otherwise-valid historical progress");
}
void qExcludedStates() {
  for(const char *state:{"FINISH","FAILED","IDLE"})for(bool fresh:{false,true}) {
    qCase="terminal or idle state is not waiting";
    auto m=qJob(state);if(fresh)m.status.set(state,70000);
    qRequire(saverView(m,true,70000)!=ws43b_view::Saver::Waiting,"terminal/idle status entered Waiting");
    qRender(m,true,70000);
    qRequire(!qHas("Oczekiwanie na dane") && !qHistorical("3%"),"terminal/idle renderer leaked active-job waiting history");
    qRequire(!printingAnimations,"terminal/idle renderer started printing animation");
  }
  qCase="offline job is not waiting";
  auto offline=qJob("RUNNING");qRender(offline,false,70000);
  qRequire(saverView(offline,false,70000)!=ws43b_view::Saver::Waiting,"offline job entered Waiting");
  qRequire(!qHas("Oczekiwanie na dane") && !qHistorical("3%") && !printingAnimations,
           "offline renderer leaked online waiting state");
  qCase="new session drops old job history";
  auto newSession=qJob("RUNNING");newSession.newSession();qRender(newSession,true,70000);
  qRequire(saverView(newSession,true,70000)!=ws43b_view::Saver::Waiting,"new session entered Waiting from previous job");
  qRequire(!qHas("Oczekiwanie na dane") && !qHistorical("3%") && !qHistorical("14 h 24 min"),
           "previous-session job values survived in waiting renderer");
  qCase="core printing flag gates stale active job";
  corePrinting=false;auto stopped=qJob("RUNNING");qRender(stopped,true,70000);
  qRequire(saverView(stopped,true,70000)!=ws43b_view::Saver::Waiting,"stale job entered Waiting while corePrinting=false");
  qRequire(!qHas("Oczekiwanie na dane") && !qHistorical("3%") && !printingAnimations,
           "renderer ignored cleared core printing state");
  corePrinting=true;
}
int main() {
  for(bool advanced:{false,true}) {
    advancedDisplay=advanced;
    for(const char *state:{"RUNNING","PREPARE"})for(bool drying:{false,true})qWaiting(state,drying);
    qExcludedStates();
  }
  std::cout<<"PASS: production waiting renderer; "<<qChecks<<" checks; simple + advanced modes\n";
}
'''


class WaitingRenderer(unittest.TestCase):
    def test_actual_renderer_waiting_history_and_independent_drying(self):
        code = existing_stub() + production_renderer() + CASES
        with tempfile.TemporaryDirectory(prefix='ws43b-waiting-renderer-') as temporary:
            directory = Path(temporary)
            source = directory / 'waiting_renderer.cpp'
            binary = directory / 'waiting_renderer'
            source.write_text(code)
            command = ['clang++', '-std=c++17', '-fsanitize=address,undefined',
                       '-I', str(ROOT / 'include'), str(source), '-o', str(binary)]
            compiled = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(compiled.returncode, 0,
                             'Production renderer harness failed to compile. '
                             'Expected policy API: saver(..., corePrinting), Saver::Waiting.\n'
                             + compiled.stdout + compiled.stderr)
            result = subprocess.run([str(binary)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0,
                             'Production waiting-renderer contract failed:\n'
                             + result.stdout + result.stderr)
            print(result.stdout.strip())


if __name__ == '__main__':
    unittest.main(verbosity=2)
