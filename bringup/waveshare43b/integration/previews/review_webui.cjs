// Browser review of synthetic WebUI; all requests intercepted before network.
const {chromium}=require('playwright');
const fs=require('fs');
const output=process.argv[2]||'/tmp/bambu-webui-preview';
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 const context=await browser.newContext({viewport:{width:1440,height:1000},colorScheme:'dark'});
 const requests=[],errors=[];
 await context.route('**/*',async route=>{
  const request=route.request(),u=new URL(request.url());requests.push({path:u.pathname,method:request.method()});
  if(u.hostname!=='bambu-preview.test')return route.abort();
  const files={'/':'index.html','/setup':'setup.html','/app.css':'app.css','/app.js':'app.js'};
  if(files[u.pathname])return route.fulfill({status:200,contentType:u.pathname.endsWith('.js')?'application/javascript':u.pathname.endsWith('.css')?'text/css':'text/html',body:fs.readFileSync(output+'/'+files[u.pathname])});
  const fixtures={
   '/status':{connected:true,configured:true,name:'Bambu P2S',state:'RUNNING',progress:68,nozzle:245,nozzle_t:245,bed:70,bed_t:70,heap_kb:72,flash_kb:16384,psram_kb:8192,rssi:-48,uptime:3620,ip:'192.0.2.10'},
   '/monitor/display':{theme:0,fan_match_printer:true},'/monitor/clock':{idle_minutes:1,screen_off:0,use24h:1},
   '/monitor/weather':{enabled:true,solar:true,city:'Schanbach',lat:48.75,lon:9.38,night_seconds:60},'/monitor/weather/setup':{done:true},
   '/wifi/scan':{state:'done',networks:[{ssid:'Domowa sieć',rssi:-48,secure:true}]},
   '/api/timezones':{zones:[],current:'Europe/Berlin'},'/printer/config':{name:'Bambu P2S',ip:'192.0.2.42',mode:'local',serial:'DEMO00000000001',lightState:1},
   '/debug':{heap:73728,uptime:3620,printers:[]},'/ota/slots':{rollback_available:false},
  };
  return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(fixtures[u.pathname]||{status:'ok'})});
 });
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://bambu-preview.test/');await page.waitForTimeout(600);
 const sections=await page.locator('.nav-item').evaluateAll(els=>els.map(e=>e.dataset.section));
 const issues=[];
 for(const width of [1440,390,320]){
  await page.setViewportSize({width,height:1000});
  for(const id of sections){
   await page.evaluate(id=>loadSection(id),id);await page.waitForTimeout(100);
   const dims=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,view:innerWidth}));
   if(dims.scroll>dims.view+1)issues.push({width,id,...dims,nodes:await page.locator('#sec-'+id+' *').evaluateAll(els=>els.filter(e=>e.getBoundingClientRect().right>innerWidth+1&&e.getBoundingClientRect().width).map(e=>({tag:e.tagName,id:e.id,cls:e.className,right:e.getBoundingClientRect().right,text:e.textContent.slice(0,50)})).slice(0,12))});
  }
 }
 await page.setViewportSize({width:390,height:844});
 await page.evaluate(()=>loadSection('wifi'));await page.waitForTimeout(1000);
 await page.screenshot({path:output+'/webui-mobile-wifi.png',fullPage:false});
 await page.locator('#hamburger').click();await page.waitForTimeout(220);
 await page.screenshot({path:output+'/webui-mobile-menu.png'});
 if(await page.locator('#hamburger').getAttribute('aria-expanded')!=='true')issues.push('drawer failed');
 await page.keyboard.press('Escape');
 if(await page.locator('#hamburger').getAttribute('aria-expanded')!=='false')issues.push('escape failed');
 await page.evaluate(()=>loadSection('display'));await page.screenshot({path:output+'/webui-mobile-display.png'});
 await page.setViewportSize({width:1440,height:1000});await page.evaluate(()=>loadSection('printer'));
 await page.screenshot({path:output+'/webui-desktop.png'});
 await page.locator('#themeToggle').click();await page.waitForTimeout(250);
 await page.screenshot({path:output+'/webui-desktop-light.png'});
 await page.reload();if(await page.locator('html').getAttribute('data-theme')!=='light')issues.push('theme persistence failed');
 await page.setViewportSize({width:390,height:844});await page.goto('http://bambu-preview.test/setup');await page.waitForTimeout(900);
 await page.screenshot({path:output+'/webui-setup.png'});
 const report={errors,issues,sections,requests:[...new Set(requests.map(r=>r.method+' '+r.path))]};
 fs.writeFileSync(output+'/review.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 await browser.close();if(errors.length||issues.length)process.exitCode=1;
})();
