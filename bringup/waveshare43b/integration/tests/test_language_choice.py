"""Language persistence, generated assets and browser save behavior, offline."""
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[2]
sys.path.insert(0,str(HERE))
import localize_web as loc

class LanguageChoice(unittest.TestCase):
    def test_persistence_validation_and_failed_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)
            (d/'config.h').write_text('#define BOARD_IS_WS43B 1\n#define NVS_NAMESPACE "bambu"\n')
            (d/'Preferences.h').write_text(r'''
#include <cassert>
#include <cstring>
#include <cstddef>
#include <cstdint>
static uint16_t stored=0; static bool openOk=true, writeOk=true; static unsigned writes=0;
struct Preferences {
 bool begin(const char* ns,bool){assert(!strcmp(ns,"bambu"));return openOk;}
 uint16_t getUShort(const char* key,uint16_t){assert(!strcmp(key,"w43_lang"));return stored;}
 size_t putUShort(const char* key,uint16_t value){assert(!strcmp(key,"w43_lang"));++writes;if(!writeOk)return 0;stored=value;return 2;}
 void end(){}
};
''')
            (d/'test.cpp').write_text('#include "'+str(ROOT/'src/ws43b_language.cpp')+'"\n'+r'''
int main(){
 loadWs43bLanguage();assert(ws43bPolish());
 assert(!saveWs43bLanguage(2) && writes==0);
 assert(saveWs43bLanguage(0) && writes==0);
 assert(saveWs43bLanguage(1) && !ws43bPolish() && stored==1);
 const auto rev=ws43bLanguageRevision();loadWs43bLanguage();assert(!ws43bPolish());
 writeOk=false;assert(!saveWs43bLanguage(0) && !ws43bPolish() && ws43bLanguageRevision()==rev);
 writeOk=true;openOk=false;assert(!saveWs43bLanguage(0) && !ws43bPolish());
 openOk=true;assert(saveWs43bLanguage(0) && ws43bPolish());
 stored=99;loadWs43bLanguage();assert(ws43bPolish());
}
''')
            subprocess.run(['clang++','-std=c++17','-I',str(d),str(d/'test.cpp'),'-o',str(d/'test')],check=True,capture_output=True)
            subprocess.run([str(d/'test')],check=True)

    def test_browser_save_and_failure_without_commands(self):
        html=(HERE/'locale/language_picker.html').read_text()
        js=re.search(r'<script>(.*?)</script>',html,re.S)[1]
        harness=r'''
const assert=require('assert');
let callback,reloads=0,requests=[],ok=true;
const select={value:'',disabled:false,addEventListener(type,cb){assert.equal(type,'change');callback=cb;}};
const status={textContent:''};
const document={documentElement:{lang:'pl'},getElementById(id){return id==='uiLanguage'?select:status;}};
const location={reload(){reloads++;}};
async function fetch(url,opts){requests.push([url,opts]);return {ok};}
'''+js+r'''
(async()=>{
 assert.equal(select.value,'pl');select.value='en';await callback();
 assert.equal(reloads,1);assert.equal(requests[0][0],'/ui/language');
 assert.equal(requests[0][1].method,'POST');assert.equal(requests[0][1].body,'language=en');
 ok=false;select.value='en';await callback();assert.equal(reloads,1);
 assert.equal(select.value,'pl');assert(!select.disabled);assert(status.textContent.includes('Nie zapisano'));
})().catch(e=>{console.error(e);process.exit(1);});
'''
        subprocess.run(['node','-e',harness],check=True,capture_output=True)

    def test_dual_templates_and_versioned_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);src=d/'src';src.mkdir()
            for name in ('web_pages.h','web_template.cpp','web_server.cpp','cloud_login.cpp'):
                original=ROOT/('include' if name.endswith('.h') else 'src')/name
                shutil.copyfile(original,src/name)
            loc.stage(src,ROOT/'web',d/'web')
            self.assertIn('serveMainPage_en()', (src/'web_template.cpp').read_text())
            self.assertIn('lang="en"',(src/'web_pages.h').read_text())
            self.assertIn('lang="pl"',(src/'web_pages_pl.h').read_text())
            self.assertIn('webAssetJsVersion_en()', (src/'web_template_en.cpp').read_text())
            server=(src/'web_server.cpp').read_text()
            self.assertIn('server.arg("v") == WEB_EN_APP_JS_VER',server)
            self.assertIn('value != "pl" && value != "en"',server)
            self.assertIn('ws43bText(',server)
            self.assertIn('doc["seconds"]',server) if 'doc["seconds"]' in (ROOT/'src/web_server.cpp').read_text() else None
            self.assertIn('ledFx["seconds"]',server)
            self.assertNotIn('ledFx["sekundy"]',server)

if __name__=='__main__':unittest.main()
