const fs=require('fs'), assert=require('assert');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
 const root=require('path').resolve(__dirname,'../../../..');
 const js=fs.readFileSync(root+'/web/app.js','utf8').split('function setupWs43bWeather(){')[1];
 const css=fs.readFileSync(root+'/web/app.css','utf8');
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE || undefined});const page=await browser.newPage({viewport:{width:390,height:844},deviceScaleFactor:1});
 let writes=0;const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',async route=>{let u=new URL(route.request().url());let body={};
 if(route.request().method()==='POST')writes++;
 if(u.pathname==='/')return route.fulfill({contentType:'text/html',body:'<!doctype html><html lang="pl" data-theme="dark"><meta charset="utf-8"><style>'+css+'</style><body><section id="sec-display" class="section"></section><script>function setupWs43bWeather(){'+js+'</script><script>setupWs43bWeather()</script></body></html>'});
 if(u.pathname==='/monitor/weather')body={enabled:false,solar:false,latitude:0,longitude:0,city:'',night_seconds:30};
 if(u.pathname==='/monitor/weather/setup')body={done:false,dark:false};
 if(u.hostname==='geocoding-api.open-meteo.com')body=u.searchParams.get('name')==='Schanbach'?{results:[{name:'Schanbach',admin4:'Aichwald',admin1:'Badenia-Wirtembergia',country:'Niemcy',latitude:48.75862,longitude:9.37709}]}:{};
 await route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
 });
 await page.goto('http://fixture.test/');await page.locator('dialog[open]').waitFor();
 for(const theme of ['dark','light']){
 await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);
 for(const id of ['wsWeatherQuery','wsWeatherNight','wsSetupAction']){
 const colors=await page.locator('#'+id).evaluate(e=>{const s=getComputedStyle(e);return [s.color,s.backgroundColor,e.clientWidth]});assert(colors[0]!==colors[1]);assert(colors[2]>100);
 }
 assert(await page.locator('dialog').evaluate(e=>e.scrollWidth<=e.clientWidth));
 }
 await page.evaluate(()=>document.documentElement.dataset.theme='dark');
 await page.locator('#wsWeatherQuery').fill('Aichwald');await page.locator('#wsWeatherQuery').press('Enter');await page.getByText('Brak tej nazwy w bazie.',{exact:false}).waitFor();assert(writes===0);
 await page.screenshot({path:'/tmp/weather-ui-empty.png'});
 await page.locator('#wsWeatherQuery').fill('Schanbach');await page.locator('#wsWeatherSearch').click();await page.locator('#wsWeatherResults').waitFor({state:'visible'});
 assert((await page.locator('#wsWeatherResults').innerText()).includes('Aichwald'));
 assert((await page.locator('#wsWeatherLocation').innerText()).includes('Nie wybrano'));
 await page.locator('#wsWeatherResults').selectOption('0');assert((await page.locator('#wsWeatherLocation').innerText())==='Schanbach');
 await page.locator('dialog').evaluate(e=>e.scrollTop=0);await page.screenshot({path:'/tmp/weather-ui-fixed.png'});
 assert(errors.length===0,JSON.stringify(errors));assert(writes===0);
 console.log('PASS: mobile light/dark controls, no horizontal overflow, Enter searches without saving, empty results hint, explicit selection, municipality shown, no JS errors');await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
