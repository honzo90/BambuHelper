"""Host-only broker regression tests. Sockets use loopback/ephemeral ports."""
import asyncio
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import ssl
import struct
import subprocess
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('runtime_fixture',HERE/'fixtures/mqtt_broker.py')
broker=importlib.util.module_from_spec(spec);spec.loader.exec_module(broker)

def field(value):return struct.pack('!H',len(value))+value
CONNECT=broker.packet(0x10,field(b'MQTT')+bytes([4,0xc2,0,30])+field(b'test')+field(b'bblp')+field(b'TESTONLY'))
SUBSCRIBE=broker.packet(0x82,b'\x00\x01'+field(broker.TOPIC)+b'\x00')

class BrokerRuntime(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.args=SimpleNamespace(bind='127.0.0.1',panel='127.0.0.1',seconds=3600,
            control=self.root/'control.json',output=self.root/'stats.json')
        self.command={'scenario':'printing','rate':30,'padding':0}
        self.write_control();self.task=None;self.streams=[]
    def write_control(self):
        tmp=self.args.control.with_suffix('.tmp');tmp.write_text(json.dumps(self.command));tmp.replace(self.args.control)
    def stats(self):return json.loads(self.args.output.read_text())
    async def wait_state(self,predicate,timeout=2):
        async def wait():
            while True:
                if self.args.output.exists():
                    state=self.stats()
                    if predicate(state):return state
                await asyncio.sleep(.005)
        return await asyncio.wait_for(wait(),timeout)
    async def start(self,seconds=3600,ctx=None):
        self.args.seconds=seconds
        self.task=asyncio.create_task(broker.serve(self.args,ctx,port=0))
        return await self.wait_state(lambda s:s['server_state']=='running' and s['listening'])
    async def connect(self,subscribe=True,send_connect=True):
        reader,writer=await asyncio.open_connection('127.0.0.1',self.stats()['bound_port'])
        self.streams.append(writer)
        if send_connect:
            writer.write(CONNECT);await writer.drain()
            self.assertEqual(await asyncio.wait_for(broker.read_packet(reader),1),(0x20,b'\0\0'))
            if subscribe:
                writer.write(SUBSCRIBE);await writer.drain()
                self.assertEqual((await asyncio.wait_for(broker.read_packet(reader),1))[0],0x90)
                await self.wait_state(lambda s:s['published']>0)
        return reader,writer
    def request(self,nonce,run=None):
        self.command['outage']={'id':nonce,'run_id':run or self.stats()['run_id']};self.write_control()
    async def asyncTearDown(self):
        for writer in self.streams:writer.transport.abort()
        if self.task:
            if not self.task.done():self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):await asyncio.wait_for(self.task,3)

    async def test_expiry_closes_listener_and_established_client(self):
        await self.start(.3);reader,_=await self.connect()
        result=await asyncio.wait_for(self.task,2)
        state=self.stats()
        self.assertEqual(state['server_state'],'stopped')
        self.assertFalse(state['listening']);self.assertFalse(state['connected'])
        self.assertFalse(state['publisher_active']);self.assertFalse(result.clients)
        await asyncio.wait_for(reader.read(),1)
        self.assertTrue(reader.at_eof())
        with self.assertRaises(OSError):await asyncio.open_connection('127.0.0.1',state['bound_port'])

    async def test_heartbeat_advances_during_slow_publisher(self):
        self.command['rate']=.1;self.write_control()
        await self.start();await self.connect();first=self.stats()
        later=await self.wait_state(lambda s:s['heartbeat_elapsed_s']>first['heartbeat_elapsed_s']+.15)
        self.assertEqual(first['published'],later['published'])
        self.assertTrue(later['listening']);self.assertTrue(later['connected'])

    async def test_timed_outage_recovers_without_controller_and_cannot_replay(self):
        with patch.object(broker,'OUTAGE_SECONDS',.3):
            await self.start();await self.connect();self.request('A')
            active=await self.wait_state(lambda s:s['outage'] and s['outage']['state']=='active')
            self.assertTrue(active['listening']);self.assertFalse(active['mqtt_admission_open'])
            start=active['outage']['start_elapsed_s']
            # An overlapping command is consumed, never queued for later.
            self.request('B');await self.wait_state(lambda s:s['last_outage_rejection'] is not None)
            done=await self.wait_state(lambda s:s['outage']['state']=='completed')
            self.assertEqual(done['last_outage_rejection']['reason'],'outage_active')
            self.assertGreaterEqual(done['outage']['actual_s'],.3)
            self.assertLess(done['outage']['actual_s'],.5)
            self.assertTrue(done['listening']);self.assertTrue(done['mqtt_admission_open'])
            await self.connect();await self.wait_state(lambda s:s['outage']['first_publish_delay_s'] is not None)
            for nonce in ('A','B','A'):
                reads=self.stats()['control_reads'];self.request(nonce)
                await self.wait_state(lambda s:s['control_reads']>reads+1)
                self.assertEqual(self.stats()['outage']['state'],'completed')
                self.assertEqual(self.stats()['outage']['start_elapsed_s'],start)

    async def test_stale_run_and_short_remaining_runtime_reject_outage(self):
        await self.start(2);await self.connect();self.request('old','a-different-run')
        s=await self.wait_state(lambda s:s['last_outage_rejection'] is not None)
        self.assertEqual(s['last_outage_rejection']['reason'],'wrong_broker_run')
        self.request('short')
        s=await self.wait_state(lambda s:s['last_outage_rejection']['id']=='short')
        self.assertEqual(s['last_outage_rejection']['reason'],'insufficient_runtime')
        self.assertIsNone(s['outage']);self.assertTrue(s['connected'])

    async def test_invalid_control_does_not_delay_automatic_recovery(self):
        with patch.object(broker,'OUTAGE_SECONDS',.2):
            await self.start();await self.connect();self.request('invalid-file')
            await self.wait_state(lambda s:s['outage'] and s['outage']['state']=='active')
            self.args.control.write_text('{broken')
            done=await self.wait_state(lambda s:s['outage']['state']=='completed')
            self.assertGreater(done['control_errors'],0);self.assertTrue(done['mqtt_admission_open'])
            self.assertLess(done['outage']['actual_s'],.4)
            await self.connect()

    async def test_two_delayed_connects_cannot_both_own_session(self):
        await self.start()
        r1,w1=await self.connect(send_connect=False)
        r2,w2=await self.connect(send_connect=False)
        w1.write(CONNECT);w2.write(CONNECT);await asyncio.gather(w1.drain(),w2.drain())
        answers=await asyncio.wait_for(asyncio.gather(r1.readexactly(4),r2.readexactly(4),return_exceptions=True),1)
        self.assertEqual(sum(a==b'\x20\x02\0\0' for a in answers),1)
        self.assertEqual(self.stats()['accepted'],1)

    async def test_outage_closes_delayed_connect_and_rejects_new_session(self):
        with patch.object(broker,'OUTAGE_SECONDS',.3):
            await self.start()
            delayed,_=await self.connect(send_connect=False)
            await self.connect();self.request('gate')
            await self.wait_state(lambda s:s['outage'] and s['outage']['state']=='active')
            self.assertEqual(await asyncio.wait_for(delayed.read(),1),b'')
            reader,writer=await self.connect(send_connect=False)
            with contextlib.suppress(ConnectionError):writer.write(CONNECT);await writer.drain()
            try:self.assertEqual(await asyncio.wait_for(reader.read(),1),b'')
            except ConnectionResetError:pass
            self.assertEqual(self.stats()['accepted'],1)

    async def test_runtime_shutdown_interrupts_outage_without_reopening(self):
        with patch.object(broker,'OUTAGE_SECONDS',.5),patch.object(broker,'RECOVERY_RESERVE_SECONDS',0):
            await self.start(1);await self.connect();self.request('shutdown')
            await self.wait_state(lambda s:s['outage'] and s['outage']['state']=='active')
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):await self.task
            s=self.stats();self.assertEqual(s['outage']['state'],'interrupted')
            self.assertFalse(s['listening']);self.assertFalse(s['mqtt_admission_open'])

    async def test_bind_failure_does_not_replace_existing_health(self):
        await self.start();before=self.stats()['run_id']
        with self.assertRaises(OSError):await broker.serve(self.args,None,port=self.stats()['bound_port'])
        self.assertEqual(self.stats()['run_id'],before)

    async def test_shutdown_closes_incomplete_tls_handshake(self):
        cert=self.root/'cert.pem';key=self.root/'key.pem'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes',
            '-keyout',str(key),'-out',str(cert),'-days','1','-subj','/CN=localhost'],
            check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(cert,key)
        await self.start(.25,ctx)
        reader,writer=await asyncio.open_connection('127.0.0.1',self.stats()['bound_port'])
        self.streams.append(writer)
        await asyncio.wait_for(self.task,2)
        self.assertFalse(self.stats()['listening'])
        self.assertEqual(await asyncio.wait_for(reader.read(),1),b'')

    @unittest.skipUnless(os.environ.get('MQTT_REALTIME_75')=='1','opt-in 75-second loopback test')
    async def test_real_75_seconds_then_reconnect_without_restart(self):
        await self.start();reader,_=await self.connect();initial=self.stats()
        self.request('full-75-seconds')
        await self.wait_state(lambda s:s['outage'] and s['outage']['state']=='active')
        await asyncio.wait_for(reader.read(),2)
        self.assertTrue(reader.at_eof())
        done=await self.wait_state(lambda s:s['outage']['state']=='completed',timeout=80)
        self.assertGreaterEqual(done['outage']['actual_s'],75)
        self.assertLess(done['outage']['actual_s'],75.25)
        self.assertTrue(done['listening']);self.assertTrue(done['mqtt_admission_open'])
        receiver,_=await self.connect()
        kind,body=await asyncio.wait_for(broker.read_packet(receiver),1)
        self.assertEqual(kind,0x30)
        topic,payload_offset=broker.text_at(body,0)
        self.assertEqual(topic,broker.TOPIC)
        self.assertEqual(json.loads(body[payload_offset:])['print']['command'],'push_status')
        recovered=await self.wait_state(lambda s:s['outage']['first_publish_delay_s'] is not None)
        self.assertEqual(recovered['run_id'],initial['run_id'])
        self.assertEqual(recovered['accepted'],2)
        self.assertEqual(recovered['errors'],0)
        self.assertEqual(recovered['publisher_errors'],0)
        self.assertGreater(recovered['published'],initial['published'])
        evidence={'scope':'host loopback only; no ESP32 connection',
            'transport':'plain TCP on ephemeral loopback port; TLS shutdown separately tested',
            'outage':recovered['outage'],'same_broker_run':True,
            'connection_closed_during_outage':True,'listener_survived':done['listening'],
            'client_received_valid_report_after_reconnect':True,
            'accepted_before':initial['accepted'],'accepted_after':recovered['accepted'],
            'published_before':initial['published'],'published_after':recovered['published'],
            'errors':recovered['errors'],'publisher_errors':recovered['publisher_errors']}
        destination=os.environ.get('MQTT_REALTIME_EVIDENCE')
        if destination:
            with Path(destination).open('x') as output:json.dump(evidence,output,indent=2)
        print(json.dumps(evidence,sort_keys=True),flush=True)
