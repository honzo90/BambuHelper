from pathlib import Path
import json,subprocess,unittest
ROOT=Path(__file__).resolve().parents[4]

class WifiSetup(unittest.TestCase):
 def test_scan_selection_safe_labels_and_failed_save(self):
  html=(ROOT/'include/web_pages.h').read_text().split('static const char PAGE_AP_HTML[]',1)[1].split(')rawliteral";',1)[0]
  script=html.split('<script>',1)[1].split('</script>',1)[0]
  harness=r'''
const vm=require('vm'),assert=require('assert');
const ids={};for(const id of ['networks','scan','scanmsg','ssid','pass','msg'])ids[id]={value:'',textContent:'',style:{},disabled:false,options:[],length:1,appendChild(o){this.options.push(o)},focus(){this.focused=true}};
let body={innerHTML:''},calls=[],fail=false;
const context={document:{getElementById(id){return ids[id]},createElement(){return {}},body},console:{warn(){}},URLSearchParams,setTimeout(f){f()},fetch:async(url,opts)=>{
 calls.push([url,opts]);
 if(url==='/save/wifi')return {ok:false,json:async()=>({status:'error'})};
 if(opts&&opts.method==='POST')return {ok:true};
 return {ok:true,json:async()=>fail?{state:'failed'}:{state:'done',networks:[{ssid:'<img src=x onerror=alert(1)>',rssi:-44,secure:true},{ssid:'Open',rssi:-70,secure:false}]}};
}};
vm.createContext(context);vm.runInContext(SCRIPT,context);
setImmediate(async()=>{
 assert.equal(ids.networks.options.length,2);
 assert(ids.networks.options[0].textContent.startsWith('<img'));
 assert.equal(ids.networks.options[0].innerHTML,undefined);
 ids.networks.value='Open';ids.pass.value='old';context.chooseNetwork();
 assert.equal(ids.ssid.value,'Open');assert.equal(ids.pass.value,'');
 context.saveWifi();await new Promise(setImmediate);
 const save=calls.find(c=>c[0]==='/save/wifi');assert(save[1].body.includes('clear_pass=1'));
 assert.equal(body.innerHTML,'');assert.equal(ids.msg.textContent,'Connection error');
 fail=true;await context.scanWifi();assert.equal(ids.scan.disabled,false);assert(ids.scanmsg.textContent.includes('Scan failed'));
 ids.networks.value='';context.chooseNetwork();assert(ids.ssid.focused);
});
'''.replace('SCRIPT',json.dumps(script))
  subprocess.run(['node','-e',harness],check=True,capture_output=True)

 def test_full_webui_scan_does_not_save_and_preserves_exact_ssid(self):
  source=(ROOT/'web/app.js').read_text()
  script=source.split('/* ============ WiFi network selection ============ */',1)[1].split('/* ============ Save WiFi ============ */',1)[0]
  harness=r'''
const vm=require('vm'),assert=require('assert');
const ids={};for(const id of ['networks','scan','scanmsg','ssid','pass'])ids[id]={value:'',defaultValue:'Home',textContent:'',disabled:false,length:1,options:[],appendChild(o){this.options.push(o)},focus(){this.focused=true}};
ids.ssid.value='Home';ids.pass.value='typed-secret';let calls=[],failed=false,transient=0,radioFailures=0,posts=0;
const context={document:{getElementById(id){return ids[id]},createElement(){return {}}},AbortController,Object,setTimeout(f,ms){if(ms===800)f();return 1},clearTimeout(){},fetch:async(url,opts)=>{
 calls.push(url);assert.equal(url,'/wifi/scan');
 if(opts&&opts.method==='POST')posts++;
 if(transient>0){transient--;throw Error('radio switched channel');}
 if(radioFailures>0 && (!opts||!opts.method)){radioFailures--;return {ok:true,json:async()=>({state:'failed'})};}
 return {ok:!failed,json:async()=>({state:'done',networks:[{ssid:' New <network> ',rssi:-40,secure:false},{ssid:'Home',rssi:-60,secure:true}]})};
}};
vm.createContext(context);vm.runInContext(SCRIPT,context);
(async()=>{
 await context.scanWifi();assert.equal(ids.networks.options.length,2);assert.equal(ids.ssid.value,'Home');assert.equal(ids.pass.value,'typed-secret');
 assert.equal(ids.networks.options[0].textContent,' New <network>  · -40 dBm');assert.equal(ids.networks.options[0].innerHTML,undefined);
 ids.networks.value=' New <network> ';context.chooseNetwork();assert.equal(ids.ssid.value,' New <network> ');assert.equal(ids.pass.value,'');
 assert(context.wifiClearSavedPassword(' New <network> '));assert(!context.wifiClearSavedPassword('Home'));
 ids.networks.value='Home';context.chooseNetwork();assert(!context.wifiClearSavedPassword('Home'));
 assert(context.wifiClearSavedPassword('Manual hidden'));
 transient=2;await context.scanWifi();assert.equal(transient,0);assert(ids.scanmsg.textContent.includes('Select a network'));
 radioFailures=1;const beforePosts=posts;await context.scanWifi();assert.equal(posts,beforePosts+2);assert(ids.scanmsg.textContent.includes('Select a network'));
 failed=true;await context.scanWifi();assert.equal(ids.scan.disabled,false);assert(ids.scanmsg.textContent.includes('Scan failed'));
})().catch(e=>{console.error(e);process.exit(1)});
'''.replace('SCRIPT',json.dumps(script))
  subprocess.run(['node','-e',harness],check=True,capture_output=True)
