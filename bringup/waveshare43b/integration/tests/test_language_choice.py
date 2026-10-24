"""Real language persistence, generated assets and picker behavior, offline."""
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(os.environ.get('BAMBUHELPER_TEST_ROOT', Path(__file__).resolve().parents[4]))
HERE = ROOT / 'bringup/waveshare43b/integration'
sys.path.insert(0, str(HERE))
import localize_web as loc

PREFERENCES_STUB = r'''
#include <cassert>
#include <cstring>
#include <cstddef>
#include <cstdint>
static uint16_t stored=0;
static bool openOk=true, writeOk=true;
static unsigned writes=0, opens=0;
struct Preferences {
 bool begin(const char* ns,bool){++opens;assert(!strcmp(ns,"bambu"));return openOk;}
 uint16_t getUShort(const char* key,uint16_t){assert(!strcmp(key,"w43_lang"));return stored;}
 size_t putUShort(const char* key,uint16_t value){
  assert(!strcmp(key,"w43_lang"));++writes;
  if(!writeOk)return 0;stored=value;return sizeof(uint16_t);
 }
 void end(){}
};
'''


def compile_and_run(test, code, extra_includes=()):
    compiler = shutil.which('clang++') or shutil.which('c++')
    if not compiler:
        test.skipTest('Native C++ compiler required')
    with tempfile.TemporaryDirectory(prefix='bambu-language-') as tmp:
        d = Path(tmp)
        (d / 'config.h').write_text('#define BOARD_IS_WS43B 1\n#define NVS_NAMESPACE "bambu"\n')
        (d / 'Preferences.h').write_text(PREFERENCES_STUB)
        (d / 'test.cpp').write_text('#include "' + str(ROOT / 'src/ws43b_language.cpp') + '"\n' + code)
        command = [compiler, '-std=c++17', '-Wall', '-Wextra', '-I', str(d)]
        for path in extra_includes:
            command += ['-I', str(path)]
        result = subprocess.run(command + [str(d / 'test.cpp'), '-o', str(d / 'test')],
                                capture_output=True, text=True)
        test.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([str(d / 'test')], capture_output=True, text=True)
        test.assertEqual(result.returncode, 0, result.stderr)


class LanguageChoice(unittest.TestCase):
    def test_persistence_validation_and_failed_write(self):
        compile_and_run(self, r'''
void current(uint8_t id,const char* code) {
 assert(ws43bLanguage()==id);
 assert(ws43bPolish()==(id==0));
 assert(!strcmp(ws43bLanguageCode(),code));
 const char* expected=id==0?"polski":id==1?"english":"deutsch";
 assert(!strcmp(ws43bText("polski","english","deutsch"),expected));
 assert(!strcmp(ws43bText("polski","english"),id==0?"polski":"english"));
}
int main(){
 loadWs43bLanguage();current(0,"pl");
 const auto firstRevision=ws43bLanguageRevision();
 const auto firstOpens=opens;
 assert(saveWs43bLanguage(0) && writes==0 && opens==firstOpens);
 assert(!saveWs43bLanguage(3) && !saveWs43bLanguage(255));
 assert(writes==0 && ws43bLanguageRevision()==firstRevision);current(0,"pl");
 const char* codes[]={"pl","en","de"};
 for(uint8_t id=0;id<3;++id){
  uint8_t parsed=77;assert(ws43bParseLanguage(codes[id],parsed) && parsed==id);
 }
 const char* invalid[]={nullptr,"","DE","Pl","de-DE"," de","de ","de\n","0","2","fr","german"};
 for(const char* code:invalid){
  uint8_t parsed=77;const auto before=ws43bLanguageRevision();
  assert(!ws43bParseLanguage(code,parsed) && parsed==77);
  assert(ws43bLanguageRevision()==before);
 }
 assert(saveWs43bLanguage(1));current(1,"en");
 assert(stored==1 && writes==1 && ws43bLanguageRevision()==firstRevision+1);
 assert(saveWs43bLanguage(2));current(2,"de");
 assert(stored==2 && writes==2 && ws43bLanguageRevision()==firstRevision+2);
 const auto deRevision=ws43bLanguageRevision(),deOpens=opens;
 assert(saveWs43bLanguage(2) && writes==2 && opens==deOpens);
 assert(ws43bLanguageRevision()==deRevision);
 // Re-read the existing NVS code as after restarting; German must survive.
 loadWs43bLanguage();current(2,"de");assert(ws43bLanguageRevision()==deRevision);
 writeOk=false;assert(!saveWs43bLanguage(0));current(2,"de");
 assert(stored==2 && ws43bLanguageRevision()==deRevision);
 writeOk=true;openOk=false;const auto failedWrites=writes;
 assert(!saveWs43bLanguage(1));current(2,"de");
 assert(writes==failedWrites && stored==2 && ws43bLanguageRevision()==deRevision);
 openOk=true;assert(saveWs43bLanguage(0));current(0,"pl");
 assert(stored==0 && ws43bLanguageRevision()==deRevision+1);
 for(uint16_t value:{uint16_t(0),uint16_t(1),uint16_t(2)}) {
  stored=value;loadWs43bLanguage();current(uint8_t(value),codes[value]);
 }
 for(uint16_t value:{uint16_t(3),uint16_t(255),uint16_t(65535)}) {
  stored=value;loadWs43bLanguage();current(0,"pl");
 }
 stored=2;openOk=false;loadWs43bLanguage();current(0,"pl");
}
'''.replace('void current', '#include <initializer_list>\nvoid current', 1))

    def test_browser_save_and_failure_without_commands(self):
        html = (HERE / 'locale/language_picker.html').read_text()
        for code, name in [('pl', 'Polski'), ('en', 'English'), ('de', 'Deutsch')]:
            self.assertRegex(html, r'<option\s+value=[\"\x27]' + code + r'[\"\x27][^>]*>\s*' + name)
        js = re.search(r'<script>(.*?)</script>', html, re.S)[1]
        harness = r'''
const assert=require('assert'),vm=require('vm');
const script=SCRIPT;
function page(lang, outcome='ok') {
 let callback,reloads=0,requests=[];
 const select={value:'',disabled:false,addEventListener(type,cb){assert.equal(type,'change');callback=cb;}};
 const status={textContent:'old status'};
 const document={documentElement:{lang},getElementById(id){return id==='uiLanguage'?select:status;}};
 const location={reload(){reloads++;}};
 async function fetch(url,opts){
  assert(select.disabled);assert.equal(status.textContent,'');requests.push([url,opts]);
  if(outcome==='network')throw new Error('offline');
  return {ok:outcome==='ok'};
 }
 vm.runInNewContext(script,{document,location,fetch,encodeURIComponent});
 return {select,status,requests,get reloads(){return reloads;},change:async(value)=>{select.value=value;await callback();}};
}
(async()=>{
 const initial=page('de');assert.equal(initial.select.value,'de');assert.equal(initial.requests.length,0);
 for(const [from,to] of [['pl','de'],['de','en'],['en','pl']]){
  const p=page(from);assert.equal(p.select.value,from);await p.change(to);
  assert.equal(p.reloads,1);assert.equal(p.requests.length,1);
  const [url,opts]=p.requests[0];assert.equal(url,'/ui/language');
  assert.equal(opts.method,'POST');assert.equal(opts.body,'language='+to);
  assert.equal(opts.headers['Content-Type'],'application/x-www-form-urlencoded');
 }
 for(const outcome of ['http','network']){
  const p=page('de',outcome);await p.change('en');
  assert.equal(p.reloads,0);assert.equal(p.select.value,'de');assert(!p.select.disabled);
  assert.match(p.status.textContent,/nicht|fehlgeschlagen/i);
  assert.match(p.status.textContent,/gespeichert|speichern/i);
  assert(!/Nie zapisano|Language not saved/.test(p.status.textContent));
  assert.equal(p.requests.length,1);
 }
 const pl=page('pl','http');await pl.change('de');
 assert.equal(pl.select.value,'pl');assert.match(pl.status.textContent,/Nie zapisano/);
 const en=page('en','network');await en.change('de');
 assert.equal(en.select.value,'en');assert.match(en.status.textContent,/not saved|failed/i);
})().catch(e=>{console.error(e);process.exit(1);});
'''.replace('SCRIPT', json.dumps(js))
        result = subprocess.run(['node', '-e', harness], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_three_templates_and_versioned_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            src = d / 'src'
            src.mkdir()
            for name in ('web_pages.h', 'web_template.cpp', 'web_server.cpp', 'cloud_login.cpp'):
                original = ROOT / ('include' if name.endswith('.h') else 'src') / name
                shutil.copyfile(original, src / name)
            loc.stage(src, ROOT / 'web', d / 'web')
            for lang in ('en', 'pl', 'de'):
                pages = src / ('web_pages.h' if lang == 'en' else 'web_pages_' + lang + '.h')
                self.assertIn('lang="' + lang + '"', pages.read_text())
                self.assertIn('serveMainPage_' + lang + '()', (src / 'web_template.cpp').read_text())
                self.assertIn('webAssetJsVersion_' + lang + '()', (src / ('web_template_' + lang + '.cpp')).read_text())
            server = (src / 'web_server.cpp').read_text()
            self.assertIn('WEB_EN_APP_JS_VER', server)
            self.assertIn('WEB_DE_APP_JS_VER', server)
            self.assertIn('ws43bText(', server)
            self.assertIn('ledFx["seconds"]', server)
            self.assertNotIn('ledFx["sekundy"]', server)
            self.assertNotIn('ledFx["Sekunden"]', server)


if __name__ == '__main__':
    unittest.main()
