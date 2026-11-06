"""A new OTA image stays on probation until it runs healthily; failures roll back and are skipped."""
from pathlib import Path
import json
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
CODE = r'''
#include <cassert>
#include <cstring>
#include "ws43b_ota_health.h"
using namespace ws43b_ota_health;
int main(){
 // Not on probation: nothing to confirm.
 assert(!shouldConfirm(false,600000,1000,true));
 // Healthy with Wi-Fi after 30 s of drawing.
 assert(!shouldConfirm(true,kHealthyUptimeMs-1,1000,true));
 assert(shouldConfirm(true,kHealthyUptimeMs,1000,true));
 // The display loop must really draw.
 assert(!shouldConfirm(true,600000,kMinFrames-1,true));
 // No Wi-Fi (router down): confirm later instead of never.
 assert(!shouldConfirm(true,kNoWifiUptimeMs-1,1000,false));
 assert(shouldConfirm(true,kNoWifiUptimeMs,1000,false));
 // A user-requested restart confirms a working image, but not one that
 // restarts right after boot.
 assert(confirmBeforeRestart(true,kRestartUptimeMs,kMinFrames));
 assert(!confirmBeforeRestart(true,kRestartUptimeMs-1,1000));
 assert(!confirmBeforeRestart(true,60000,kMinFrames-1));
 assert(!confirmBeforeRestart(false,60000,1000));
 // Slot note: version only when the sha tag matches the image in the slot.
 char v[32];
 noteVersion("v4.1.1-alpha.2|1a2b3c4d","1a2b3c4d",v,sizeof v); assert(!strcmp(v,"v4.1.1-alpha.2"));
 noteVersion("v4.1.1-alpha.2|1a2b3c4d","deadbeef",v,sizeof v); assert(!v[0]);
 noteVersion("broken","1a2b3c4d",v,sizeof v); assert(!v[0]);
 noteVersion(nullptr,"1a2b3c4d",v,sizeof v); assert(!v[0]);
 char tiny[4]; noteVersion("v4.1.1|aa","aa",tiny,sizeof tiny); assert(!strcmp(tiny,"v4."));
 // Online update URL of the failed version is refused; others pass.
 const char *u="https://github.com/honzo90/BambuHelper/releases/download/v4.1.1-beta.1/BambuHelper-ws_lcd_43b-v4.1.1-beta.1-ota.bin";
 assert(urlIsFailedVersion(u,"v4.1.1-beta.1"));
 assert(!urlIsFailedVersion(u,"v4.1.1-beta.10"));
 assert(!urlIsFailedVersion(u,"v4.1.1"));
 assert(!urlIsFailedVersion(u,""));
 assert(!urlIsFailedVersion(nullptr,"v4.1.1-beta.1"));
 return 0;
}
'''


class OtaHealth(unittest.TestCase):
    def test_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'o.cpp'; src.write_text(CODE); exe = Path(tmp) / 'o'
            subprocess.run(['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'include'),
                            str(src), '-o', str(exe)], check=True, capture_output=True, text=True)
            subprocess.run([str(exe)], check=True)

    def test_wired_in(self):
        status = (ROOT / 'src/ws43b_ota_status.cpp').read_text()
        # Arduino must not confirm at boot; the firmware does it from tick().
        self.assertIn('extern "C" bool verifyRollbackLater() { return true; }', status)
        self.assertIn('esp_ota_mark_app_valid_cancel_rollback()', status)
        self.assertIn('esp_ota_get_last_invalid_partition()', status)
        self.assertIn('ESP_RST_BROWNOUT', status)
        main = (ROOT / 'src/main.cpp').read_text()
        setup = main[main.index('void setup()'):main.index('void loop()')]
        self.assertLess(setup.index('recordBootSlotVersion();'), setup.index('ws43b_ota_status::begin();'))
        self.assertIn('ws43b_ota_status::tick();', main[main.index('void loop()'):])
        web = (ROOT / 'src/web_server.cpp').read_text()
        restart = web[web.index('if (pendingRestartAt && millis() >= pendingRestartAt)'):]
        self.assertLess(restart.index('ws43b_ota_status::confirmBeforeRestart();'), restart.index('ESP.restart();'))
        auto = web[web.index('static void handleOtaAuto()'):]
        self.assertLess(auto.index('urlIsFailedVersion('), auto.index('disconnectBambuMqtt();'))
        settings = (ROOT / 'src/settings.cpp').read_text()
        reset = settings[settings.index('prefs.clear();'):]
        self.assertLess(reset.index('ws43b_ota_status::confirmBeforeRestart();'), reset.index('ESP.restart();'))

    def test_webui_skips_failed_version(self):
        pages = (ROOT / 'include/web_pages.h').read_text()
        self.assertIn("otaFailed:'%OTAFAILED%'", pages)
        self.assertIn('"OTAFAILED"', (ROOT / 'src/web_template.cpp').read_text())
        app = (ROOT / 'web/app.js').read_text()
        body = app[app.index('function checkWs43bUpdates'):app.index('function checkForUpdates')]
        skip = body.index('picked.release.tag_name === DEV.otaFailed')
        self.assertLess(skip, body.index("installBtn.style.display = 'inline-block'"))
        msg = ('This version failed to start on this panel and was rolled back. '
               'Use the manual upload only if you want to try it again.')
        self.assertIn(msg, body)
        for lang in ('pl', 'de'):
            catalog = json.loads((ROOT / f'bringup/waveshare43b/integration/locale/{lang}.json').read_text())
            self.assertIn(msg, catalog)

    def test_panel_shows_health(self):
        display = (ROOT / 'src/display_ws43b.cpp').read_text()
        self.assertIn('const char *panelHealthNotice(bool shortForm)', display)
        general = display[display.index('void generalSettingsScreen()'):]
        general = general[:general.index('\n}\n')]
        self.assertIn('panelHealthNotice(false)', general)
        tiles = display[display.index('void settingsScreen()'):display.index('void systemSettingsScreen()')]
        self.assertIn('panelHealthNotice(true)', tiles)


if __name__ == '__main__':
    unittest.main()
