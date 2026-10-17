"""Exercise integrated forms in both languages, including failed loads/saves."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path.insert(0,str(HERE))
import localize_web
from test_full_webui import function

class IntegratedDisplay(unittest.TestCase):
    def test_clock_toggle_keeps_native_idle_and_reports_write_failure(self):
        source=(ROOT/'src/web_server.cpp').read_text()
        start=source.index('  else if (key == "use24h") {')
        branch=source[start:source.index('\n#else',start)].replace('else if','if',1)
        harness=r'''#include <cassert>
#include <string>
struct Clock {int idleMinutes=15;bool screenOff=true;bool use24h=true;} clockState;
const Clock& ws43bClockSettings(){return clockState;}
bool writeOk=true;
bool saveWs43bClockSettings(int idle,bool off,bool format){
 assert(idle==15 && off);if(!writeOk)return false;clockState.use24h=format;return true;
}
struct Server {int code=0;void send(int c,const char*,const char*){code=c;}} server;
void toggle(bool on){std::string key="use24h";
''' + branch + r'''}
int main(){toggle(false);assert(!clockState.use24h && server.code==0);
writeOk=false;toggle(true);assert(!clockState.use24h && server.code==500);}
'''
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'test.cpp').write_text(harness)
            subprocess.run(['clang++','-std=c++17',str(p/'test.cpp'),'-o',str(p/'test')],check=True,capture_output=True)
            subprocess.run([str(p/'test')],check=True)

    def test_load_save_failure_and_retry_pl_en(self):
        original=(ROOT/'web/app.js').read_text()
        for source in (original,localize_web.javascript(original)):
            code=function(source,'function ws43bDisplaySettingsMarkup()')+'\n'+function(source,'function setupWs43bDisplaySettings()')
            harness=r'''
const assert=require('assert');let fields={}, requests=[], reloaded=0,failLoad=true,failSave=false,badMode=false,card=null;
function element(id){return fields[id] ||= {value:'',checked:false,disabled:false,style:{},textContent:'',querySelector(){return this.button ||= {disabled:true};}};}
const nightCard={style:{display:'none'},querySelector(){return {};}};
const field={querySelector(){return {};}};
const range={value:'60',closest(){return nightCard;},replaceWith(select){fields.nbright=select;}};
const intro={querySelector(){return {};},after(c){card=c;}};
const document={getElementById(id){
 if(id==='wsNativeSettings')return card;
 if(id==='keepon')return {closest(){return null;}};
 if(id==='nbright')return fields.nbright||range;
 return element(id);
},querySelector(){return intro;},createElement(){return {closest(){return field;}};}};
const location={reload(){reloaded++;}};
async function fetch(path,options){
 requests.push([path,options]);
 if(options.method==='POST')return {ok:!failSave,json:async()=>({status:failSave?'error':'ok',message:'save rejected'})};
 if(failLoad)return {ok:false,json:async()=>({message:'load rejected'})};
 return {ok:true,json:async()=>path==='/monitor/display'?{theme:2,fan_match_printer:true}:path==='/monitor/display-mode'?{mode:badMode?'unknown':'advanced'}:{idle_minutes:15,screen_off:1,use24h:0}};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
''' + code + r'''
(async()=>{
 setupWs43bDisplaySettings();await tick();
 assert.equal(nightCard.style.display,'');assert.equal(fields.nbright.value,'255');
 assert(card.innerHTML.includes('wsIdleForm'));assert(!card.innerHTML.includes('href="/monitor"'));
 assert(fields.wsThemeForm.button.disabled && fields.wsIdleForm.button.disabled && fields.wsDisplayModeForm.button.disabled);
 let posts=()=>requests.filter(x=>x[1].method==='POST');
 await fields.wsIdleForm.onsubmit({preventDefault(){}});assert.equal(posts().length,0);
 await fields.wsDisplayModeForm.onsubmit({preventDefault(){}});assert.equal(posts().length,0);
 failLoad=false;await fields.wsNativeReload.onclick();
 assert.equal(fields.wsTheme.value,'2');assert.equal(fields.wsIdle.value,'15');
 assert.equal(fields.wsIdleAction.value,'1');assert(!fields.use24h.checked && fields.fanmp.checked);
 assert.equal(fields.wsDisplayMode.value,'advanced');
 fields.wsIdle.value='5';fields.wsIdleAction.value='0';fields.use24h.checked=true;
 await fields.wsIdleForm.onsubmit({preventDefault(){}});
 assert.equal(posts()[0][0],'/monitor/clock');
 assert.deepEqual(Object.fromEntries(new URLSearchParams(posts()[0][1].body)),{idle_minutes:'5',screen_off:'0',use24h:'1'});
 assert(!fields.wsIdleForm.button.disabled && reloaded===0);
 fields.wsDisplayMode.value='simple';await fields.wsDisplayModeForm.onsubmit({preventDefault(){}});
 assert.equal(posts()[1][0],'/monitor/display-mode');
 assert.deepEqual(Object.fromEntries(new URLSearchParams(posts()[1][1].body)),{mode:'simple'});
 assert.equal(fields.wsIdle.value,'5');assert.equal(fields.wsIdleAction.value,'0');assert(fields.use24h.checked);
 failSave=true;fields.wsDisplayMode.value='advanced';await fields.wsDisplayModeForm.onsubmit({preventDefault(){}});
 assert.equal(fields.wsNativeStatus.textContent,'save rejected');assert(!fields.wsDisplayModeForm.button.disabled&&reloaded===0);
 failSave=true;await fields.wsThemeForm.onsubmit({preventDefault(){}});
 assert.equal(reloaded,0);assert(!fields.wsThemeForm.button.disabled);assert.equal(fields.wsNativeStatus.textContent,'save rejected');
 failSave=false;await fields.wsThemeForm.onsubmit({preventDefault(){}});
 assert.equal(reloaded,1);let last=posts().at(-1);assert.equal(last[0],'/monitor/display');
 assert.deepEqual(Object.fromEntries(new URLSearchParams(last[1].body)),{theme:'2',fan_match_printer:'1'});
 assert(requests.every(x=>['/monitor/clock','/monitor/display','/monitor/display-mode'].includes(x[0])));
 badMode=true;await fields.wsNativeReload.onclick();const count=posts().length;
 assert(fields.wsDisplayModeForm.button.disabled);await fields.wsDisplayModeForm.onsubmit({preventDefault(){}});assert.equal(posts().length,count);
 badMode=false;await fields.wsNativeReload.onclick();assert(!fields.wsDisplayModeForm.button.disabled);
})().catch(e=>{console.error(e);process.exit(1);});
'''
            with self.subTest(polish=source!=original):
                subprocess.run(['node','-e',harness],check=True,capture_output=True)

if __name__=='__main__':unittest.main()
