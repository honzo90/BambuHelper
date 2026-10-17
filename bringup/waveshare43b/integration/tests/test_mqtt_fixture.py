"""Fixture isolation/validation tests; never connect to a real printer."""
from pathlib import Path
import asyncio,contextlib,importlib.util,io,json,struct,tempfile,unittest
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[4]
HERE=ROOT/'bringup/waveshare43b/integration'
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
broker=module('fixture_broker',HERE/'fixtures/mqtt_broker.py')
profile=module('fixture_profile',HERE/'fixture_profile.py')
class FixtureTests(unittest.TestCase):
 def test_fake_auth_only_and_bounded_messages(self):
  def field(x):return struct.pack('!H',len(x))+x
  base=field(b'MQTT')+bytes([4,0xc2,0,30])+field(b'test-client')+field(b'bblp')
  self.assertTrue(broker.validate_connect(base+field(b'TESTONLY')))
  self.assertFalse(broker.validate_connect(base+field(b'not-the-test-password')))
  with self.assertRaises(ValueError):broker.encoded_length(16385)
  self.assertEqual(broker.encoded_length(128),b'\x80\x01')
  for name,stage in [('cleaning',14),('leveling',1),('calibration',51),('printing',0)]:
   p=json.loads(broker.report(40,name,2048));self.assertEqual(p['print']['stg_cur'],stage)
   self.assertEqual(len(p['fixture_padding']),2048)
   self.assertTrue(p['print']['subtask_name'].startswith('TEST'))
   self.assertEqual(p['print']['spd_lvl'],2)
   self.assertEqual(p['print']['fan_gear'],8421631)
 def test_drying_and_printing_drying_are_independent(self):
  for scenario,state in [('drying','IDLE'),('printing_drying','RUNNING')]:
   p=json.loads(broker.report(68,scenario,0))['print']
   self.assertEqual(p['gcode_state'],state)
   self.assertEqual(p['ams']['ams'][0]['dry_time'],150)
   self.assertEqual(p['mc_percent'],68 if state=='RUNNING' else 0)
  self.assertEqual(json.loads(broker.report(68,'printing',0))['print']['ams']['ams'][0]['dry_time'],0)
 def test_staged_fixture_keeps_sources_and_blocks_persistence(self):
  originals={name:(ROOT/'src'/name).read_text() for name in ('main.cpp','settings.cpp','ws43b_weather.cpp','web_server.cpp','display_ws43b.cpp')}
  with tempfile.TemporaryDirectory() as tmp:
   stage=Path(tmp)
   for name,text in originals.items():(stage/name).write_text(text)
   record=profile.apply(stage,'10.10.10.24')
   self.assertTrue(record['synthetic_only'])
   main=(stage/'main.cpp').read_text();self.assertLess(main.index('loadSettings();'),main.index('SYNTHETIC FIXTURE'))
   self.assertIn('memset(&printers[i].config,0,sizeof(PrinterConfig))',main)
   self.assertIn('"TESTONLY"',main)
   self.assertIn('memcpy(fixture.gaugeSlots,testGauges,sizeof testGauges)',main)
   settings=(stage/'settings.cpp').read_text()
   for signature in ('void saveSettings() {','void savePrinterConfig(uint8_t index) {','void resetSettings() {'):
    self.assertIn(signature+'\n  return;',settings)
   web=(stage/'web_server.cpp').read_text();section=web.split('void initWebServer() {',1)[1].split('server.begin();return;',1)[0]
   self.assertNotIn('handleSavePrinter',section);self.assertNotIn('handleRoot',section)
   self.assertIn('HTTP_POST',section);self.assertIn('handleMemoryDiagnostics',section)
  for name,text in originals.items():self.assertEqual((ROOT/'src'/name).read_text(),text)
  for host in ('0.0.0.0','127.0.0.1','169.254.1.2','8.8.8.8','bad'):
   with self.assertRaises(ValueError):profile.validate_ip(host)

class FakeWriter:
    """Memory-only transport: the receive stream deliberately stays open."""
    def __init__(self,fail_publish=False,on_publish=None):
        self.transport=self;self.fail_publish=fail_publish;self.on_publish=on_publish
        self.closed=False;self.last_kind=None
    def get_extra_info(self,name):
        return ('10.10.10.41',12345) if name=='peername' else self
    def setsockopt(self,*args):pass
    def set_write_buffer_limits(self,**kwargs):pass
    def write(self,data):self.last_kind=data[0]>>4
    async def drain(self):
        if self.last_kind==3:
            if self.fail_publish:raise TimeoutError('TESTONLY must never reach diagnostics')
            if self.on_publish:self.on_publish()
    def close(self):self.closed=True
    async def wait_closed(self):pass

class PublisherLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.args=SimpleNamespace(panel='10.10.10.41',control=self.root/'control.json',output=self.root/'stats.json')
        self.control(30)
        self.broker=broker.Broker(self.args)
    def control(self,rate,scenario='printing'):
        self.args.control.write_text(json.dumps(dict(rate=rate,padding=0,scenario=scenario)))
    def reader(self):
        def field(value):return struct.pack('!H',len(value))+value
        connect=field(b'MQTT')+bytes([4,0xc2,0,30])+field(b'test-client')+field(b'bblp')+field(b'TESTONLY')
        reader=asyncio.StreamReader()
        reader.feed_data(broker.packet(0x10,connect)+broker.packet(0x82,b'\x00\x01'+field(broker.TOPIC)+b'\x00'))
        return reader
    def stats(self):return json.loads(self.args.output.read_text())
    async def wait_stats(self,predicate):
        async def wait():
            while True:
                if self.args.output.exists():
                    state=self.stats()
                    if predicate(state):return state
                await asyncio.sleep(.001)
        return await asyncio.wait_for(wait(),1)
    async def stop(self,task):
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):await task
    async def test_publish_failure_closes_asymmetric_session_and_redacts_output(self):
        writer=FakeWriter(fail_publish=True);reader=self.reader();output=io.StringIO()
        with contextlib.redirect_stdout(output),contextlib.redirect_stderr(output):
            await asyncio.wait_for(self.broker.client(reader,writer),1)
        state=self.stats()
        self.assertFalse(reader.at_eof()) # No receive EOF was needed for cleanup.
        self.assertTrue(writer.closed);self.assertFalse(state['connected'])
        self.assertFalse(state['publisher_active']);self.assertFalse(state['publish_in_flight'])
        self.assertEqual(state['publisher_state'],'failed')
        self.assertEqual(state['publisher_errors'],1);self.assertEqual(state['errors'],1)
        self.assertEqual(state['publisher_last_error'],'timeout')
        self.assertEqual(state['published'],0);self.assertEqual(state['bytes'],0)
        self.assertEqual(state['disconnects'],1)
        self.assertEqual(output.getvalue(),'')
        self.assertNotIn('TESTONLY',self.args.output.read_text())
        self.assertNotIn('bblp',self.args.output.read_text())
    async def test_completed_tx_saved_before_long_publish_sleep(self):
        self.control(.1)
        writer=FakeWriter();task=asyncio.create_task(self.broker.client(self.reader(),writer))
        try:
            state=await self.wait_stats(lambda state:state['published']==1)
            self.assertGreater(state['bytes'],0)
            self.assertIsNotNone(state['last_publish_elapsed_s'])
            self.assertFalse(state['publish_in_flight']);self.assertTrue(state['publisher_active'])
        finally:await self.stop(task)
        state=self.stats()
        self.assertEqual(state['published'],1);self.assertFalse(state['connected'])
        self.assertEqual(state['publisher_errors'],0)
    async def test_rate_zero_acknowledges_completed_tx_and_stays_connected(self):
        writer=FakeWriter(on_publish=lambda:self.control(0))
        task=asyncio.create_task(self.broker.client(self.reader(),writer))
        try:
            state=await self.wait_stats(lambda state:state['publisher_state']=='paused')
            self.assertTrue(state['connected']);self.assertTrue(state['publisher_active'])
            self.assertFalse(state['publish_in_flight']);self.assertEqual(state['rate'],0)
            self.assertEqual(state['published'],1)
            self.assertEqual(state['publisher_control_revision'],state['control_revision'])
            self.assertEqual(state['control_revision'],2)
            reads=state['control_reads']
            later=await self.wait_stats(lambda state:state['control_reads']>reads)
            self.assertEqual(later['published'],1)
            self.assertEqual(later['bytes'],state['bytes'])
        finally:await self.stop(task)
    async def test_normal_publisher_exit_closes_waiting_receiver(self):
        writer=FakeWriter(on_publish=lambda:self.control(0,'offline'))
        reader=self.reader()
        await asyncio.wait_for(self.broker.client(reader,writer),1)
        state=self.stats()
        self.assertFalse(reader.at_eof());self.assertTrue(writer.closed)
        self.assertFalse(state['connected']);self.assertFalse(state['publisher_active'])
        self.assertEqual(state['publisher_state'],'offline');self.assertEqual(state['published'],1)
        self.assertEqual(state['publisher_errors'],0);self.assertEqual(state['errors'],0)
