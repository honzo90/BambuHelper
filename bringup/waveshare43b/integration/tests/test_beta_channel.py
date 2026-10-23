#!/usr/bin/env python3
"""Independent offline acceptance: WS43B Beta channel; never contacts a device/network."""
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[4]
HERE = ROOT / "bringup/waveshare43b/integration"
sys.path[:0] = [str(HERE), str(HERE / "tests")]
import localize_web
from test_full_webui import function

FUNCTIONS = (
    "compareWs43bVersions", "selectWs43bRelease", "changeWs43bOtaChannel",
    "checkWs43bUpdates", "checkForUpdates",
)


class ChannelMarkup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.selects = []
        self.current = None
        self.option = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "select" and attrs.get("id") == "otaChannel":
            self.current = {"attrs": attrs, "options": []}
            self.selects.append(self.current)
        if tag == "option" and self.current is not None:
            self.option = {"attrs": attrs, "text": ""}
            self.current["options"].append(self.option)

    def handle_data(self, data):
        if self.option is not None:
            self.option["text"] += data

    def handle_endtag(self, tag):
        if tag == "option":
            self.option = None
        if tag == "select":
            self.current = None


HARNESS = r'''
const assert = require('assert');
const FORK='https://api.github.com/repos/honzo90/BambuHelper/';
const DOWNLOAD='https://github.com/honzo90/BambuHelper/releases/download/';
let fields, DEV, _autoOtaUrl, calls, requests;
const document={getElementById(id){return fields[id] || null;}};
// Pure in-memory promises; this fetch never leaves Node.
const fetch=(url)=>{calls.push(url);return new Promise((resolve,reject)=>requests.push({resolve,reject}));};
const localStorage=new Proxy({}, {get(){throw Error('channel must not use localStorage');}});
const sessionStorage=new Proxy({}, {get(){throw Error('channel must not use sessionStorage');}});
function reset(){
 fields={};
 for(const id of ['otaChannel','updateResult','updateInfo','installBtn','updateLink','updateVer','updateDate'])
  fields[id]={value:'',style:{display:''},textContent:'',disabled:false,href:'',setAttribute(k,v){this[k]=v;},removeAttribute(k){delete this[k];}};
 fields.otaChannel.value='stable';
 DEV={board:'ws_lcd_43b',fw:'v4.0.0-alpha.1',otaSlot:'3145728',flashMb:'16'};
 _autoOtaUrl='';calls=[];requests=[];
 for(const k of Object.keys(checkWs43bUpdates)) delete checkWs43bUpdates[k];
}
const clone=x=>JSON.parse(JSON.stringify(x));
function release(tag,prerelease=/-/.test(tag),bytes=2866336){
 const name='BambuHelper-ws_lcd_43b-'+tag+'-ota.bin';
 return {tag_name:tag,draft:false,prerelease,published_at:'2026-10-23T22:00:00Z',
  assets:[{name,size:bytes,browser_download_url:DOWNLOAD+tag+'/'+name}]};
}
async function flush(){for(let i=0;i<4;i++)await new Promise(r=>setImmediate(r));}
function respond(index,data,status=200,jsonError=false){
 assert(requests[index], 'expected a request at '+index);
 requests[index].resolve({ok:status===200,status,json:async()=>{if(jsonError)throw Error('bad JSON');return data;}});
}
function noOffer(label){
 assert.equal(_autoOtaUrl,'',label+': no cached installation URL');
 assert.equal(fields.updateInfo.style.display,'none',label+': hidden offer');
 assert.equal(fields.installBtn.style.display,'none',label+': hidden install');
 assert.equal(fields.updateLink.style.display,'none',label+': hidden download');
}
function offered(tag){
 const want=release(tag).assets[0].browser_download_url;
 assert.equal(_autoOtaUrl,want);
 assert.equal(fields.updateLink.href,want);
 assert.equal(fields.updateInfo.style.display,'block');
 assert.notEqual(fields.installBtn.style.display,'none');
 assert.equal(fields.updateVer.textContent,tag);
}
'''

CASES = r'''
async function main(){
 // Full SemVer ordering, including values the Beta filter deliberately rejects.
 for(const [a,b] of [
  ['v4.0.0-alpha.1','v4.0.0-beta.1'],['v4.0.0-beta.2','v4.0.0-beta.10'],
  ['v4.0.0-beta.10','v4.0.0'],['v4.0.0','v4.0.1-alpha.1'],
  ['v4.9.9','v4.10.0'],['v4.0.0-alpha','v4.0.0-alpha.1'],
  ['v4.0.0-alpha.1','v4.0.0-alpha.beta'],['v4.0.0-beta','v4.0.0-beta.1'],
  ['v4.0.0-beta.11','v4.0.0-rc.1'],['v4.0.0-rc.1','v4.0.0'],
  ['v3.9.1-ws43b-test.1','v3.9.1'],['v3.9.1-ws43b-test.1','v4.0.0-beta.1'],
  ['v4.0.0-beta.9007199254740992','v4.0.0-beta.9007199254740993'],
  ['v9007199254740992.0.0','v9007199254740993.0.0']
 ]){
  assert.equal(compareWs43bVersions(a,b),-1,a+' < '+b);
  assert.equal(compareWs43bVersions(b,a),1,b+' > '+a);
 }
 for(const [a,b] of [['v4.0.0','4.0.0'],['v4.0.0+one','v4.0.0+two'],
  ['v4.0.0-beta.1+build.7','v4.0.0-beta.1'],['v4.0.0-beta.1','v4.0.0-beta.1']])
  assert.equal(compareWs43bVersions(a,b),0);
 for(const bad of ['',null,undefined,42,{},'v4','v4.0','v04.0.0','v4.01.0','v4.0.01',
   'v4.0.0-beta.01','v4.0.0-','v4.0.0+','v4.0.0-alpha..1','v4.0.0 beta','v4.0.0\n',
   ' v4.0.0','v4.0.0-beta.1+!','v4.0.0-beta.1+','v4.0.0+build..1']){
  assert.equal(compareWs43bVersions(bad,'v4.0.0'),null,'invalid left: '+String(bad));
  assert.equal(compareWs43bVersions('v4.0.0',bad),null,'invalid right: '+String(bad));
 }

 const stable=release('v4.0.0',false), beta=release('v4.0.0-beta.1');
 let found=selectWs43bRelease(stable,'stable',3145728);
 assert.equal(found.release.tag_name,'v4.0.0');assert.equal(found.asset.name,stable.assets[0].name);
 assert.equal(selectWs43bRelease(beta,'stable',3145728),null);
 const mix=[release('v9.0.0-alpha.1'),release('v8.0.0-rc.1'),release('v4.0.0-beta.2'),
  {...release('v99.0.0-beta.1'),draft:true},release('v4.0.0-beta.10')];
 mix[2].published_at='2099-01-01T00:00:00Z';
 assert.equal(selectWs43bRelease(mix,'beta',3145728).release.tag_name,'v4.0.0-beta.10');
 assert.equal(selectWs43bRelease([...mix,stable],'beta',3145728).release.tag_name,'v4.0.0');
 for(const tag of ['v4.0.0-alpha.1','v4.0.0-rc.1','v4.0.0-beta','v4.0.0-beta.0',
   'v4.0.0-beta.01','v4.0.0-beta.1.extra','v4.0.0-beta.-1','v4.0.0-BETA.1','latest'])
  assert.equal(selectWs43bRelease([release(tag)],'beta',3145728),null,'excluded tag '+tag);
 assert.equal(selectWs43bRelease([release('v4.0.0',true)],'beta',3145728),null);
 assert.equal(selectWs43bRelease([release('v4.0.0-beta.1',false)],'beta',3145728),null);
 for(const flag of [undefined,null,0,1,'false','true']){
  const s=release('v4.0.0',false),b=release('v4.0.0-beta.1',true);
  s.prerelease=flag;b.prerelease=flag;
  assert.equal(selectWs43bRelease(s,'stable',3145728),null,'stable flag must be false');
  assert.equal(selectWs43bRelease([b],'beta',3145728),null,'Beta flag must be true');
 }
 for(const tag of ['4.0.0','v04.0.0','v4.0.0+build.1','4.0.0-beta.1','v4.0.0-beta.1+build.1']){
  assert.equal(selectWs43bRelease([release(tag)],'beta',3145728),null,'strict published tag '+tag);
  assert.equal(selectWs43bRelease(release(tag),'stable',3145728),null,'strict stable tag '+tag);
 }
 for(const slot of [0,-1,NaN,Infinity,3145728.5,Number.MAX_SAFE_INTEGER+1])
  assert.equal(selectWs43bRelease([beta],'beta',slot),null,'invalid slot '+slot);
 for(const bytes of [0,-1,NaN,Infinity,0.5,3145729,Number.MAX_SAFE_INTEGER+1,'2866336']){
  const item=clone(beta);item.assets[0].size=bytes;
  assert.equal(selectWs43bRelease([item],'beta',3145728),null,'invalid asset size '+bytes);
 }
 assert(selectWs43bRelease([release('v4.0.0-beta.1',true,3145728)],'beta',3145728));
 for(const mutate of [
  x=>x.assets=[], x=>delete x.assets, x=>x.assets={},
  x=>x.assets[0].name='BambuHelper-esp32s3-v4.0.0-beta.1-ota.bin',
  x=>x.assets[0].name='BambuHelper-ws_lcd_43b-v4.0.0-beta.2-ota.bin',
  x=>x.assets[0].name='BambuHelper-ws_lcd_43b-v4.0.0-beta.1-Full.bin',
  x=>x.assets[0].browser_download_url=x.assets[0].browser_download_url.replace('honzo90','Keralots'),
  x=>x.assets[0].browser_download_url=x.assets[0].browser_download_url.replace('/v4.0.0-beta.1/','/v4.0.0-beta.2/'),
  x=>x.assets[0].browser_download_url='http:'+x.assets[0].browser_download_url.slice(6),
  x=>x.assets[0].browser_download_url+='?x=1',
  x=>x.assets[0].browser_download_url+='#fragment',
  x=>x.assets[0].browser_download_url=x.assets[0].browser_download_url.replace('github.com','example.com'),
  x=>x.assets[0].browser_download_url=x.assets[0].browser_download_url.replace('BambuHelper/releases','Other/releases'),
  x=>x.draft=true
 ]){
  const item=clone(beta);mutate(item);
  assert.equal(selectWs43bRelease([item],'beta',3145728),null,'malformed or incompatible release');
 }
 for(const data of [null,undefined,{},[],[null],[{}],[{tag_name:'v4.0.0-beta.1',assets:[null]}]])
  assert.equal(selectWs43bRelease(data,'beta',3145728),null,'malformed Beta response');
 const older=release('v4.0.0-beta.2'),tooBig=release('v4.0.0-beta.3',true,4000000);
 assert.equal(selectWs43bRelease([tooBig,older],'beta',3145728).release.tag_name,'v4.0.0-beta.2');
 const afterBad=clone(beta),validAsset=afterBad.assets[0];
 afterBad.assets=[null,{name:'unrelated.txt',size:1,browser_download_url:'https://example.com/unrelated.txt'},validAsset];
 assert.equal(selectWs43bRelease([afterBad],'beta',3145728).asset.name,validAsset.name);

 // WS43B routing, explicit opt-in, and Alpha -> Beta offer.
 reset();checkForUpdates();assert.equal(calls[0],FORK+'releases/latest');
 respond(0,release('v3.9.1',false));await flush();noOffer('stable older than installed Alpha');
 fields.otaChannel.value='beta';changeWs43bOtaChannel();noOffer('channel reset');
 checkForUpdates();assert.equal(calls[calls.length-1],FORK+'releases?per_page=100');
 respond(requests.length-1,[beta]);await flush();offered('v4.0.0-beta.1');
 assert.equal(checkWs43bUpdates.channel,'beta');

 // Equal version, older candidate, invalid current and invalid response never install.
 for(const current of ['v4.0.0-beta.1','v4.0.0-beta.2','v4.0.0','invalid-current']){
  reset();DEV.fw=current;fields.otaChannel.value='beta';checkWs43bUpdates();
  if(requests.length)respond(0,[beta]);
  await flush();noOffer('current '+current);
 }
 reset();delete fields.otaChannel;checkWs43bUpdates();
 assert.equal(calls[0],FORK+'releases/latest');
 respond(0,release('v3.9.1',false));await flush();noOffer('missing selector defaults to stable');
 for(const unknownSlot of ['',undefined,null,'invalid','0','-1']){
  reset();DEV.otaSlot=unknownSlot;fields.otaChannel.value='beta';checkWs43bUpdates();
  if(requests.length)respond(0,[beta]);
  await flush();noOffer('unknown/invalid slot '+String(unknownSlot));
 }
 reset();DEV.fw='v4.0.0-beta.10';fields.otaChannel.value='beta';checkWs43bUpdates();
 respond(0,[stable]);await flush();offered('v4.0.0');
 for(const scenario of ['404','403','network','json','malformed']){
  reset();_autoOtaUrl='old-url';checkWs43bUpdates();noOffer('initial '+scenario);
  if(scenario==='network')requests[0].reject(Error('offline'));
  else if(scenario==='json')respond(0,null,200,true);
  else if(scenario==='malformed')respond(0,{});
  else respond(0,{},Number(scenario));
  await flush();noOffer(scenario);
  if(scenario==='404')assert.equal(fields.updateResult.textContent,STABLE404);
  if(['403','network','json'].includes(scenario))assert.equal(fields.updateResult.style.color,'var(--danger)');
 }
 reset();fields.otaChannel.value='beta';checkWs43bUpdates();respond(0,[]);await flush();noOffer('no Beta releases');
 for(const channel of ['stable','beta']){
  for(const payload of [null,42,'unexpected',channel==='stable'?[]:{}]){
   reset();fields.otaChannel.value=channel;checkWs43bUpdates();respond(0,payload);
   await flush();noOffer('invalid JSON shape');
   assert.equal(fields.updateResult.style.color,'var(--danger)','invalid JSON shape must report error');
  }
 }

 // Channel reset invalidates both late fetch completion and late JSON completion.
 for(const latePhase of ['fetch','json']){
  reset();fields.otaChannel.value='beta';checkWs43bUpdates();let finishJson;
  if(latePhase==='json'){
   requests[0].resolve({ok:true,status:200,json:()=>new Promise(r=>finishJson=r)});await flush();
  }
  fields.otaChannel.value='stable';changeWs43bOtaChannel();noOffer('switch while pending');
  checkWs43bUpdates();const stableRequest=requests.length-1;
  assert.equal(calls[stableRequest],FORK+'releases/latest');
  respond(stableRequest,release('v3.9.1',false));await flush();
  const currentText=fields.updateResult.textContent;
  if(latePhase==='json')finishJson([beta]);else respond(0,[beta]);
  await flush();noOffer('late '+latePhase);assert.equal(fields.updateResult.textContent,currentText);
 }
 // Same-channel newer request wins, including a late error from the first request.
 for(const lateError of [false,true]){
  reset();fields.otaChannel.value='beta';checkWs43bUpdates();checkWs43bUpdates();
  respond(1,[release('v4.0.0-beta.2')]);await flush();offered('v4.0.0-beta.2');
  const currentText=fields.updateResult.textContent;
  if(lateError)requests[0].reject(Error('old failure'));else respond(0,[beta]);
  await flush();offered('v4.0.0-beta.2');assert.equal(fields.updateResult.textContent,currentText);
 }

 // In-flight installation is immutable: no new check, reset, or channel switch.
 reset();fields.otaChannel.value='beta';checkWs43bUpdates();respond(0,[beta]);await flush();
 fields.installBtn.disabled=true;const savedUrl=_autoOtaUrl,savedText=fields.updateResult.textContent,n=calls.length;
 checkWs43bUpdates();assert.equal(calls.length,n);assert.equal(_autoOtaUrl,savedUrl);
 fields.otaChannel.value='stable';changeWs43bOtaChannel();
 assert.equal(fields.otaChannel.value,'beta');assert.equal(calls.length,n);assert.equal(_autoOtaUrl,savedUrl);
 assert.equal(fields.updateResult.textContent,savedText);offered('v4.0.0-beta.1');

 // Other boards still use the upstream endpoint and original stable behavior.
 reset();DEV.board='esp32s3';DEV.fw='v3.9.0';delete fields.otaChannel;
 checkForUpdates();assert.equal(calls[0],'https://api.github.com/repos/Keralots/BambuHelper/releases/latest');
 const legacy=release('v3.9.1',false);legacy.assets[0]={name:'BambuHelper-esp32s3-v3.9.1-ota.bin',size:2000000,
  browser_download_url:'https://github.com/Keralots/BambuHelper/releases/download/v3.9.1/BambuHelper-esp32s3-v3.9.1-ota.bin'};
 respond(0,legacy);await flush();assert.equal(_autoOtaUrl,legacy.assets[0].browser_download_url);
 console.log('PASS: SemVer, selection/assets, channel routing, errors/races, busy guard, legacy board');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
'''


class BetaAcceptance(unittest.TestCase):
    def test_behavior_en_pl(self):
        source = (ROOT / "web/app.js").read_text()
        for language in ("en", "pl"):
            with self.subTest(language=language):
                localized = localize_web.javascript(source) if language == "pl" else source
                snippets = []
                for name in FUNCTIONS:
                    try:
                        snippets.append(function(localized, "function " + name + "("))
                    except ValueError:
                        self.fail("Missing required function: " + name)
                label = "No stable release has been published for this channel yet."
                if language == "pl":
                    label = localize_web.catalog()[label]
                script = "const STABLE404=" + json.dumps(label) + ";\n" + HARNESS + "\n".join(snippets) + CASES
                result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, language + ":\n" + result.stdout + result.stderr)

    def test_review_edge_cases(self):
        """Run independent cases to report every edge failure in one repair pass."""
        source = (ROOT / "web/app.js").read_text()
        edge_cases = r'''
const failures=[];
async function scenario(name,fn){
 try {await fn();}
 catch(e){failures.push(name+': '+String(e.message).replace(/\s+/g,' ').slice(0,180));}
}
async function edges(){
 await scenario('final build metadata is ignored',()=>assert.equal(compareWs43bVersions('v4.0.0+build.1','v4.0.0+build.2'),0));
 await scenario('prerelease build metadata is ignored',()=>assert.equal(compareWs43bVersions('v4.0.0-beta.1+build.1','v4.0.0-beta.1'),0));
 for(const version of ['v4.0.0-beta.1+!','v4.0.0-beta.1+','v4.0.0-beta.1+build..1',
  'v4.0.0-beta.1+build_1','v4.0.0-beta.1+build+1','v4.0.0-','v4.0.0-beta.01',
  'v4.0.0-01','v04.0.0',' v4.0.0','v4.0.0 ','v4.0.0\n']){
  await scenario('reject invalid SemVer '+JSON.stringify(version),()=>assert.equal(compareWs43bVersions(version,'v4.0.0'),null));
 }
 await scenario('huge core has exact numeric ordering',()=>assert.equal(compareWs43bVersions('v9007199254740992.0.0','v9007199254740993.0.0'),-1));
 await scenario('huge prerelease has exact numeric ordering',()=>assert.equal(compareWs43bVersions('v4.0.0-beta.9007199254740992','v4.0.0-beta.9007199254740993'),-1));
 for(const slot of [Number.MAX_SAFE_INTEGER+1,Infinity,3145728.5]){
  await scenario('reject unsafe slot '+String(slot),()=>assert.equal(selectWs43bRelease([release('v4.0.0-beta.1')],'beta',slot),null));
 }
 for(const channel of ['stable','beta']){
  for(const invalidFlag of [undefined,null,'false',0,'true']){
   await scenario('explicit prerelease flag '+channel+' '+String(invalidFlag),()=>{
    const item=release(channel==='stable'?'v4.0.0':'v4.0.0-beta.1');
    if(invalidFlag===undefined)delete item.prerelease;else item.prerelease=invalidFlag;
    assert.equal(selectWs43bRelease(channel==='stable'?item:[item],channel,3145728),null);
   });
  }
 }
 for(const kind of ['oversize','missing assets','wrong board','wrong URL']){
  await scenario('fallback to older compatible release after '+kind,()=>{
   const good=release('v4.0.0-beta.2'),bad=release('v4.0.0-beta.3');
   if(kind==='oversize')bad.assets[0].size=4000000;
   if(kind==='missing assets')bad.assets=[];
   if(kind==='wrong board')bad.assets[0].name='BambuHelper-esp32s3-v4.0.0-beta.3-ota.bin';
   if(kind==='wrong URL')bad.assets[0].browser_download_url='https://example.com/firmware.bin';
   const chosen=selectWs43bRelease([bad,good],'beta',3145728);
   assert(chosen,'compatible older release was hidden by incompatible newest release');
   assert.equal(chosen.release.tag_name,good.tag_name);
  });
 }
 for(const channel of ['stable','beta']){
  const invalidData=[null,17,'unexpected',false,channel==='stable'?[]:{}];
  for(const data of invalidData){
   await scenario('HTTP 200 malformed JSON payload '+channel+' '+JSON.stringify(data),async()=>{
    reset();fields.otaChannel.value=channel;checkWs43bUpdates();respond(0,data);await flush();
    noOffer('malformed JSON payload');assert.equal(fields.updateResult.style.color,'var(--danger)');
    assert.notEqual(fields.updateResult.textContent,STABLE404);
   });
  }
 }
 await scenario('stable HTTP 404 retains informational message',async()=>{
  reset();checkWs43bUpdates();respond(0,{},404);await flush();noOffer('404');
  assert.equal(fields.updateResult.style.color,'var(--info)');assert.equal(fields.updateResult.textContent,STABLE404);
 });
 await scenario('fresh check clears previous link href immediately',async()=>{
  reset();fields.updateLink.href=release('v4.0.0-beta.1').assets[0].browser_download_url;
  _autoOtaUrl=fields.updateLink.href;checkWs43bUpdates();
  assert.equal(fields.updateLink.href,'');noOffer('fresh check');
  respond(0,release('v3.9.1',false));await flush();
 });
 assert.deepStrictEqual(failures,[],'Independent review edge failures');
 console.log('PASS: independent review edge cases');
}
edges().catch(e=>{console.error(e);process.exitCode=1;});
'''
        for language in ("en", "pl"):
            with self.subTest(language=language):
                localized = localize_web.javascript(source) if language == "pl" else source
                snippets = [function(localized, "function " + name + "(") for name in FUNCTIONS]
                label = "No stable release has been published for this channel yet."
                if language == "pl":
                    label = localize_web.catalog()[label]
                script = "const STABLE404=" + json.dumps(label) + ";\n" + HARNESS + "\n".join(snippets) + edge_cases
                result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, language + ":\n" + result.stdout + result.stderr)

    def test_markup_compilation_and_labels_en_pl(self):
        source = (ROOT / "include/web_pages.h").read_text()
        for language in ("en", "pl"):
            localized = localize_web.cpp(source) if language == "pl" else source
            # Actual C++ preprocessing checks that guards exclude the picker.
            minimal = re.sub(r"^\s*#\s*(?:include|pragma)\b[^\n]*", "", localized, flags=re.M)
            for ws43b, auto in ((True, True), (False, True), (True, False), (False, False)):
                with self.subTest(language=language, ws43b=ws43b, auto=auto):
                    argv = ["clang++", "-E", "-P", "-x", "c++", "-DPROGMEM="]
                    if ws43b:
                        argv += ["-DBOARD_IS_WS43B=1"]
                    if auto:
                        argv += ["-DENABLE_OTA_AUTO=1"]
                    result = subprocess.run(argv + ["-"], input=minimal, capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    parser = ChannelMarkup()
                    parser.feed(result.stdout)
                    self.assertEqual(len(parser.selects), int(ws43b and auto))
                    if not parser.selects:
                        continue
                    picker = parser.selects[0]
                    self.assertRegex(picker["attrs"].get("onchange", ""), r"\bchangeWs43bOtaChannel\s*\(")
                    options = picker["options"]
                    self.assertEqual([o["attrs"].get("value") for o in options], ["stable", "beta"])
                    self.assertEqual([o["text"].strip() for o in options], ["Stabilny" if language == "pl" else "Stable", "Beta"])
                    self.assertNotIn("selected", options[1]["attrs"])
                    hint = ("Beta zawiera wydania testowe i może działać niestabilnie. Po ponownym otwarciu strony wybrany jest kanał stabilny." if language == "pl" else "Beta includes test releases and may be unstable. Stable is selected when this page is reopened.")
                    self.assertIn(hint, result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
