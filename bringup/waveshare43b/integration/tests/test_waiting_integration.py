#!/usr/bin/env python3
"""Offline Waiting integration QA; adapt existing fixtures in memory only.

Run directly or discover with unittest; the repository root is derived from this file.
The firmware and repository tests are read-only. Temporary C++ executables are
the existing host fixtures, extended with real routing/cache lifecycle cases.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[4]
TESTS = ROOT / "bringup/waveshare43b/integration/tests"


def replace_once(text, before, after):
    count = text.count(before)
    if count != 1:
        raise AssertionError(f"Fixture marker drift: expected one occurrence, found {count}: {before[:110]!r}")
    return text.replace(before, after, 1)


IDLE_CASES = r'''
 // Independent Waiting integration cases, after every original fixture case.
 {
  auto &ws=printers[0].state;
  auto &wm=ws.monitor;
  auto resetWaiting=[&](){
   wm.newSession();wifi=true;configured=true;ap=false;
   ws.connected=true;ws.printing=true;now=1000000;
   page=Page::Dashboard;painted=false;automaticIdle=false;screenOff=false;
   idlePolicy={};previousFreshState=0;coolingRecoveryPending=false;recoveryBedSeen=false;
   nightWindow=false;nightBlackout=false;previousNight=false;nightActivity=now;
   dashboardCooling=false;clockSettings.idleMinutes=1;clockSettings.screenOff=true;++clockSettings.revision;
   wm.status.set("RUNNING",now-70000);wm.progress.set(3,now-70000);
   wm.layerNum.set(1,now-70000);wm.remainingMinutes.set(864,now-70000);
  };
  resetWaiting();
  assert(saverView(wm,true,now)==ws43b_view::Saver::Waiting);
  updateIdleView(now);assert(previousFreshState==0);
  now+=60001;updateIdleView(now);
  assert(page==Page::Dashboard&&!automaticIdle&&!screenOff);
  assert(previousFreshState==0); // Waiting is not an observed fresh RUNNING.
  assert(!wm.status.current(now)&&!ws43b_view::progressCurrent(wm,true,now));

  // A genuine job delta revives the common current predicate without a new
  // gcode_state field; the page-state classifier must use the same predicate.
  wm.remainingMinutes.set(863,now);updateIdleView(now);
  assert(!wm.status.current(now));
  assert(ws43b_view::statusCurrent(wm,true,now));
  assert(previousFreshState==3&&page==Page::Dashboard&&!automaticIdle);
  assert(saverView(wm,true,now)==ws43b_view::Saver::Print);

#if WS43B_FULL_WEBUI
  resetWaiting();nightWindow=true;updateIdleView(now);
  now+=30001;updateIdleView(now);
  assert(page==Page::Clock&&automaticIdle&&!screenOff);
  assert(previousFreshState==0);
  assert(saverView(wm,true,now)==ws43b_view::Saver::Waiting);
#endif

  for(const char *terminal:{"FINISH","FAILED","IDLE","PAUSE"}){
   resetWaiting();wm.status.set(terminal,now);
   assert(saverView(wm,true,now)!=ws43b_view::Saver::Waiting);
  }
  resetWaiting();ws.printing=false;
  assert(saverView(wm,true,now)==ws43b_view::Saver::Clock);
  resetWaiting();ws.connected=false;
  assert(saverView(wm,isWiFiConnected()&&ws.connected,now)==ws43b_view::Saver::Clock);
  updateIdleView(now);now+=60001;updateIdleView(now);
  assert(automaticIdle&&screenOff&&previousFreshState==0);
  resetWaiting();wifi=false;
  assert(saverView(wm,isWiFiConnected()&&ws.connected,now)==ws43b_view::Saver::Clock);

  // Core printing can survive MQTT reconnect; the cleared monitor may not.
  resetWaiting();wm.newSession();
  auto &dry=wm.amsUnits[0];dry.used=true;dry.dryRemainMin.set(90,now);
  assert(ws.printing&&!wm.status.valid);
  assert(saverView(wm,true,now)==ws43b_view::Saver::Clock);
  updateIdleView(now);now+=60001;updateIdleView(now);
  assert(automaticIdle&&screenOff&&previousFreshState==0);
 }
'''


CACHE_CASES = r'''
 // Independent Waiting cache lifecycle with a fixed displayed clock minute.
 {
  rotState.displayIndex=0;
  auto &ws=printers[0].state;auto &job=ws.monitor;
  configured=true;ap=false;wifi=true;ws.connected=true;ws.printing=true;
  screenOff=false;automaticIdle=false;page=Page::Clock;painted=false;
  rxPending=false;glowArmed=false;glowLatched=false;glowCleanup=false;cleanupAtTick=false;
  screen=0;night=false;dashboardCooling=false;advancedDisplay=false;
  weatherConfig.enabled=false;weather.valid=false;
  clockMinute=23;const unsigned fixedMinute=clockMinute;
  currentMs=1000000;job.newSession();seed(job);
  job.layerNum.set(1,currentMs);job.printedLayerSeen=true;
  job.amsUnits[0].dryRemainMin.set(90,currentMs);
  tick(true);assert(clockCount==1&&!lastClockPartial&&probes==1);
  assert(saverView(job,true,currentMs)==ws43b_view::Saver::Print);

  currentMs+=60001;job.amsUnits[0].dryRemainMin.set(89,currentMs);
  tick();assert(saverView(job,true,currentMs)==ws43b_view::Saver::Waiting);
  assert(clockMinute==fixedMinute&&clockCount==1&&!lastClockPartial&&probes==1);

  job.remainingMinutes.set(19,currentMs);tick();
  assert(saverView(job,true,currentMs)==ws43b_view::Saver::Print);
  assert(clockMinute==fixedMinute&&clockCount==1&&!lastClockPartial&&probes==1);

  currentMs+=60001;job.amsUnits[0].dryRemainMin.set(88,currentMs);
  tick();assert(saverView(job,true,currentMs)==ws43b_view::Saver::Waiting);
  assert(clockCount==1&&!lastClockPartial&&probes==1);
  tick();assert(clockCount==1&&lastClockPartial); // The steady card can reuse its cache.

  // Only upstream corePrinting changes. Telemetry, AMS and wall-clock minute
  // are unchanged: this catches a cache key which omits Waiting/Clock choice.
  ws.printing=false;tick();
  assert(saverView(job,true,currentMs)==ws43b_view::Saver::Clock);
  assert(clockMinute==fixedMinute&&clockCount==1&&!lastClockPartial&&probes==1);
  ws.printing=true;tick();
  assert(saverView(job,true,currentMs)==ws43b_view::Saver::Waiting);
  assert(clockMinute==fixedMinute&&clockCount==1&&!lastClockPartial&&probes==1);

  ws.connected=false;tick();
  assert(saverView(job,false,currentMs)==ws43b_view::Saver::Clock);
  assert(clockCount==1&&!lastClockPartial&&probes==1);
  ws.connected=true;job.newSession();tick();
  assert(ws.printing&&!job.status.valid);
  assert(saverView(job,true,currentMs)==ws43b_view::Saver::Clock);
  assert(clockCount==1&&!lastClockPartial&&probes==1);
 }
'''


class WaitingIntegration(unittest.TestCase):
    def test_real_idle_and_saver_view(self):
        path = TESTS / "test_ws43b_view_interaction.py"
        text = path.read_text()
        old_state = "struct Printer { struct State {bool connected=true; BambuMonitorTelemetry monitor;} state; } printers[1];"
        new_state = "struct Printer { struct State {bool connected=true; bool printing=false; BambuMonitorTelemetry monitor;} state; } printers[1];"
        if old_state in text:
            text = replace_once(text, old_state, new_state)
        elif new_state not in text:
            raise AssertionError("Fixture State drift: printing default must be adapted explicitly")
        marker = "\n}\n'''\nwith tempfile.TemporaryDirectory(prefix='ws43b-view-')"
        text = replace_once(text, marker, "\n" + IDLE_CASES + marker)
        namespace = {"__file__": str(path), "__name__": "waiting_view_fixture"}
        exec(compile(text, str(path) + " [in-memory Waiting extension]", "exec"), namespace)
        print("PASS: real updateIdleView/saverView, fresh-state separation, night, terminal/offline/session gates")

    def test_real_dispatcher_waiting_cache_lifecycle(self):
        self._run_dispatcher_cases(CACHE_CASES)
        print("PASS: real dispatcher full redraws Print/Waiting/Clock without changing the clock minute")

    def test_waiting_historical_validity_cache(self):
        marker = "  // Only upstream corePrinting changes."
        for field in ("progress", "remainingMinutes"):
            for restored in (False, True):
                with self.subTest(field=field, transition="invalid-to-valid" if restored else "valid-to-invalid"):
                    before = (f"job.{field}.valid=false;tick(true);" if restored else "")
                    mutation = f"job.{field}.valid=true;" if restored else f"job.{field}.invalidate(currentMs);"
                    case = f"""
  // Historical validity changes alone must redraw the label. The reverse
  // transition restores the existing stale sample, not a fresh job update.
  {before}
  const auto historicalValue=job.{field}.value;
  {mutation}
  tick();
  assert(job.{field}.value==historicalValue);
  assert(saverView(job,true,currentMs)==ws43b_view::Saver::Waiting);
  assert(clockMinute==fixedMinute&&clockCount==1&&!lastClockPartial&&probes==1);

"""
                    self._run_dispatcher_cases(replace_once(CACHE_CASES, marker, case + marker))
        print("CHECKED: historical progress/remaining validity redraws in both directions while still Waiting")

    def _run_dispatcher_cases(self, cases):
        path = TESTS / "test_repaint_integration.py"
        text = path.read_text()
        text = replace_once(text,
                            "'clang++', '-std=c++17',",
                            "'clang++', '-std=c++17', '-Werror=format',")
        old_state = "struct {bool connected=true;BambuMonitorTelemetry monitor;} state;"
        new_state = "struct {bool connected=true;bool printing=false;BambuMonitorTelemetry monitor;} state;"
        if old_state in text:
            text = replace_once(text, old_state, new_state)
        elif new_state not in text:
            raise AssertionError("Repaint State drift: printing default must be adapted explicitly")
        old_saver = "return ws43b_view::saver(m,online,now,dashboardCooling,screen==SCREEN_HMS);"
        new_saver = "return ws43b_view::saver(m,online,now,dashboardCooling,screen==SCREEN_HMS,displayedPrinter().state.printing);"
        if old_saver in text:
            text = replace_once(text, old_saver, new_saver)
        elif new_saver not in text:
            raise AssertionError("Repaint saverView drift: core printing must be passed explicitly")
        marker = ' cool.status.set("FINISH",currentMs);tick();assert(dashboardCooling&&bodyCount==1);\n}'
        text = replace_once(text, marker, marker[:-1] + cases + "}")
        namespace = {"__file__": str(path), "__name__": "waiting_cache_fixture"}
        exec(compile(text, str(path) + " [in-memory Waiting extension]", "exec"), namespace)
        instance = namespace["RepaintIntegration"]("test_actual_dispatcher_cache_invalidation")
        instance.test_actual_dispatcher_cache_invalidation()


if __name__ == "__main__":
    print("Offline Waiting integration QA; repository sources/tests remain read-only", flush=True)
    unittest.main(verbosity=2)
