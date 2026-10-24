"""Synthetic integration checks; no GitHub/device requests or firmware writes."""
from pathlib import Path
import subprocess
import unittest
from test_full_webui import function

ROOT = Path(__file__).resolve().parents[4]


class Upstream390(unittest.TestCase):
    def test_legacy_update_requires_exact_board_newer_version_and_slot_capacity(self):
        js = function((ROOT / 'web/app.js').read_text(), 'function checkForUpdates()')
        harness = r'''
const assert=require('assert');
let fields={}, release={}, _autoOtaUrl='', calls=0;
let DEV={board:'ws_lcd_43',fw:'v3.9.0',otaSlot:'3145728',flashMb:'16'};
const document={getElementById(id){return fields[id] ||= {style:{},textContent:''};}};
const fetch=async(url)=>{assert.equal(url,'https://api.github.com/repos/Keralots/BambuHelper/releases/latest');calls++;return {ok:true,json:async()=>release};};
''' + js + r'''
async function check(tag,assets){
 release={tag_name:tag,assets,published_at:'2026-10-11'};
 checkForUpdates();await new Promise(r=>setImmediate(r));
 return fields.updateResult.textContent;
}
function asset(board,size=2400000){return {name:'BambuHelper-'+board+'-v3.10.0-ota.bin',size,browser_download_url:'https://example.invalid/ota.bin'};}
(async()=>{
 assert((await check('v3.10.0',[asset('wrong_board')])).includes('No compatible OTA'));
 assert.equal(_autoOtaUrl,'');assert.equal(fields.installBtn.style.display,'none');
 assert((await check('v3.10.0',[])).includes('No compatible OTA'));
 assert((await check('v3.9.0',[asset('ws_lcd_43')])).includes('You are up to date'));
 assert((await check('v3.8.3',[asset('ws_lcd_43')])).includes('Running newer version'));
 assert((await check('v3.10.0',[asset('ws_lcd_43',4000000)])).includes('does not fit'));
 assert.equal(_autoOtaUrl,'');
 assert.equal(await check('v3.10.0',[asset('ws_lcd_43')]),'Update available!');
 assert.equal(_autoOtaUrl,'https://example.invalid/ota.bin');
 assert.equal(fields.installBtn.style.display,'inline-block');
 assert((await check('v3.11.0',[])).includes('No compatible OTA'));assert.equal(_autoOtaUrl,'');
 assert.equal(calls,7);
})().catch(e=>{console.error(e);process.exit(1)});
'''
        subprocess.run(['node', '-e', harness], check=True, capture_output=True)

    def test_ws43b_update_delegates_to_channel_handler(self):
        # Full WS43B board/version/slot/channel cases live in test_beta_channel.
        js = function((ROOT / 'web/app.js').read_text(), 'function checkForUpdates()')
        harness = r'''
const assert=require('assert');let delegated=0;
const DEV={board:'ws_lcd_43b'};
const document={getElementById(){throw Error('legacy UI must not run for WS43B');}};
const fetch=()=>{throw Error('legacy updater must not fetch for WS43B');};
function checkWs43bUpdates(){++delegated;return 'channel-owned-result';}
''' + js + r'''
assert.equal(checkForUpdates(),'channel-owned-result');assert.equal(delegated,1);
'''
        subprocess.run(['node','-e',harness],check=True,capture_output=True)

    def test_native_board_excludes_cards_and_cloud_thumbnail_tasks(self):
        # Derive actual feature macros, avoiding dependencies not needed by config.
        import re
        config=(ROOT/'include/config.h').read_text()
        config=re.sub(r'^\s*#\s*include[^\n]*', '', config, flags=re.M)
        result=subprocess.run(['clang++','-E','-dM','-x','c++','-DBOARD_IS_WS43B=1',
                               '-DBOARD_HAS_PSRAM=1','-DDISPLAY_800x480=1','-'],
                              input=config,text=True,capture_output=True,check=True)
        for name in ['HAS_CARD_SKIN','HAS_CARD_THUMB','CARD_BAND_RENDER']:
            self.assertRegex(result.stdout, rf'#define {name} 0\b')

    def test_legacy_gestures_hidden_only_on_native_panel(self):
        js=function((ROOT/'web/app.js').read_text(),'function applyGestureVis()')
        harness=r'''
const assert=require('assert');let fields={};
const document={getElementById(id){return fields[id] ||= {style:{},value:'0',options:[]};}};
let DEV={board:'ws_lcd_43b',boardBtn:'0'};
''' + js + r'''
applyGestureVis();assert(fields.gestCard.hidden&&fields.gestOff.hidden);
assert(fields.gtap.disabled&&fields.gdbl.disabled&&fields.ghold.disabled);
fields={};DEV.board='other';applyGestureVis();assert(!fields.gestCard.hidden);
assert.equal(fields.gestCard.style.display,'none');
'''
        subprocess.run(['node','-e',harness],check=True,capture_output=True)


if __name__ == '__main__':
    unittest.main()
