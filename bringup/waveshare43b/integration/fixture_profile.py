"""Explicit, staging-only synthetic MQTT profile; never changes repository src.
This image must not be shipped. The manifest records all transformed source
hashes. Printer credentials are replaced in RAM; their persistence is blocked.
The web server exposes only diagnostics and a fixture view selector. Restore a
normal image after hardware stress testing.
"""
import hashlib, ipaddress

def validate_ip(value):
    ip=ipaddress.IPv4Address(value)
    if not ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_unspecified:
        raise ValueError('Fixture requires an explicit private LAN IPv4 address')
    return str(ip)

def apply(staged,host):
    host=validate_ip(host);changed={}
    def replace(name,old,new):
        p=staged/name;s=p.read_text()
        if s.count(old)!=1:raise RuntimeError(f'Fixture patch mismatch: {name}: {old[:70]}')
        p.write_text(s.replace(old,new));changed[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    anchor='  { ws43b_memory::Scope memory(ws43b_memory::Stage::Settings); loadSettings(); }'
    replace('main.cpp',anchor,anchor+'''\n  // SYNTHETIC FIXTURE: replace printer identity in RAM only.
  for (uint8_t i=0;i<MAX_PRINTERS;++i) memset(&printers[i].config,0,sizeof(PrinterConfig));
  auto &fixture = printers[0].config;
  fixture.mode=CONN_LOCAL;
  strlcpy(fixture.ip,"'''+host+'''",sizeof fixture.ip);
  strlcpy(fixture.serial,"SYNTHETIC000001",sizeof fixture.serial);
  strlcpy(fixture.accessCode,"TESTONLY",sizeof fixture.accessCode);
  strlcpy(fixture.name,"TEST MQTT",sizeof fixture.name);
  const uint8_t testGauges[]={GAUGE_PROGRESS,GAUGE_NOZZLE,GAUGE_BED,GAUGE_PART_FAN,GAUGE_AUX_FAN,GAUGE_CHAMBER_FAN};
  memcpy(fixture.gaugeSlots,testGauges,sizeof testGauges);
  activePrinterIndex=0;rotState.displayIndex=0;rotState.splitEnabled=false;
  dpSettings.keepDisplayOn=true;dpSettings.nightModeEnabled=false;
  dispSettings.hmsEnabled=true;dispSettings.hmsSeverityAll=true;
  dispSettings.hmsAutoPresent=0;dispSettings.hmsAlertMask=0;
  dispSettings.pongClock=false;
  for(uint8_t i=0;i<TASMOTA_PLUG_COUNT;++i)tasmotaSettings[i].enabled=false;
''')
    for signature in ('void saveSettings() {','void savePrinterConfig(uint8_t index) {','void resetSettings() {'):
        replace('settings.cpp',signature,signature+'\n  return; // Fixture: never persist synthetic printer identity or reset NVS.\n')
    replace('ws43b_weather.cpp','void loadWs43bWeather(){','void loadWs43bWeather(){\n config={};config.enabled=false;config.solar=false;return; // Synthetic profile: no weather network traffic.\n')
    replace('web_server.cpp','void initWebServer() {','''extern bool ws43bFixtureView(const char *view);
void initWebServer() {
  // No configuration, OTA, reset or printer-control routes in this test image.
  server.on("/monitor/status",HTTP_GET,handleMonitorStatus);
  server.on("/diagnostics/memory",HTTP_GET,handleMemoryDiagnostics);
  server.on("/diagnostics/frame",HTTP_GET,handleFrameCapture);
  server.on("/diagnostics/view",HTTP_POST,[](){
    bool ok=ws43bFixtureView(server.arg("name").c_str());
    server.send(ok?200:400,"application/json",ok?"{\\"ok\\":true}":"{\\"ok\\":false}");
  });
  server.onNotFound([](){server.send(403,"text/plain","Synthetic test image: diagnostics only");});
  server.begin();return;
''')
    # One external helper, still calling the real page renderer. No fake bitmap.
    p=staged/'display_ws43b.cpp';s=p.read_text();s+='''
// Diagnostic-only generated code, absent from normal source/builds.
bool ws43bFixtureView(const char *view) {
  if(!strcmp(view,"hms"))return handleWs43bErrorTap(true);
  handleWs43bErrorTap(false);
  if(!strcmp(view,"printing"))page=Page::Dashboard;
  else if(!strcmp(view,"ams"))page=Page::Ams;
  else if(!strcmp(view,"details"))page=Page::Details;
  else if(!strcmp(view,"gauges"))page=Page::Gauges;
  else if(!strcmp(view,"settings"))page=Page::Settings;
  else if(!strcmp(view,"clock")||!strcmp(view,"pong"))page=Page::Clock;
  else return false;
  dispSettings.pongClock=!strcmp(view,"pong");
  dpSettings.keepDisplayOn=strcmp(view,"pong")!=0;
  dpSettings.showClockAfterFinish=true;
  idlePolicy.activity(millis());automaticIdle=false;navigationActivity=millis();painted=false;
  return true;
}
''';p.write_text(s);changed[p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
    return {'synthetic_only':True,'host':host,'serial':'SYNTHETIC000001',
            'persistent_printer_writes_blocked':True,'web_routes':'diagnostics_only',
            'weather_disabled':True,'transformed_sources_sha256':changed}
