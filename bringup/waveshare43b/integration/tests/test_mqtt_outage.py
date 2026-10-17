"""Pure local-file/mocked-time operator tests; no sockets or process control."""
import copy
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('mqtt_outage_operator',HERE/'fixtures/mqtt_outage.py')
operator=importlib.util.module_from_spec(spec);spec.loader.exec_module(operator)

class OutageOperator(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.stats=self.root/'stats.json';self.control=self.root/'control.json'
        self.command={'scenario':'printing','rate':1,'padding':0,'operator_note':'preserve'}
        self.control.write_text(json.dumps(self.command))
        self.state={'run_id':str(uuid.uuid4()),'server_state':'running','listening':True,
            'mqtt_admission_open':True,'connected':True,'publisher_active':True,'publisher_state':'running',
            'publisher_errors':0,'publisher_last_error':None,'heartbeat_elapsed_s':20.,'elapsed_s':20.,
            'runtime_remaining_s':1000.,'published':5,'errors':0,'control_errors':0,'last_control_error':None,
            'control_revision':1,'publisher_control_revision':1,'scenario':'printing','rate':1,'padding':0,
            'outage':None,'last_outage_rejection':None}
        self.save()
    def save(self):self.stats.write_text(json.dumps(self.state))
    def advance(self,_):
        self.state['heartbeat_elapsed_s']+=1.2;self.state['elapsed_s']+=1.2
        self.state['published']+=1;self.save()
    def prepared(self):return copy.deepcopy(self.state),copy.deepcopy(self.command),self.control.read_text()

    def test_default_is_read_only_after_two_advancing_samples(self):
        original=self.control.read_bytes()
        with patch.object(operator.time,'sleep',side_effect=self.advance):
            result=operator.operate(self.stats,self.control,self.root)
        self.assertEqual(result['status'],'READY_READ_ONLY')
        self.assertEqual(self.control.read_bytes(),original)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()),['control.json','stats.json'])

    def test_approval_is_literal_and_cannot_write_on_other_text(self):
        with patch.object(operator,'prepare',return_value=self.prepared()):
            with self.assertRaisesRegex(operator.GateError,'literal_GOTOWY_required'):
                operator.operate(self.stats,self.control,self.root,'gotowy')
        self.assertNotIn('outage',json.loads(self.control.read_text()))

    def test_unsupported_stale_stalled_and_restarted_broker_refused(self):
        self.stats.write_text('{}')
        with self.assertRaisesRegex(operator.GateError,'unsupported'):operator.snapshot(self.stats)
        self.save()
        with patch.object(operator.time,'time',return_value=self.stats.stat().st_mtime+4):
            with self.assertRaisesRegex(operator.GateError,'stale'):operator.snapshot(self.stats)
        with patch.object(operator.time,'sleep'):
            with self.assertRaisesRegex(operator.GateError,'heartbeat_not_advancing'):operator.prepare(self.stats,self.control)
        def restart(_):self.state['run_id']=str(uuid.uuid4());self.advance(0)
        with patch.object(operator.time,'sleep',side_effect=restart):
            with self.assertRaisesRegex(operator.GateError,'broker_restarted'):operator.prepare(self.stats,self.control)

    def test_publications_must_advance_and_readiness_is_strict(self):
        def heartbeat_only(_):self.state['heartbeat_elapsed_s']+=1;self.state['elapsed_s']+=1;self.save()
        with patch.object(operator.time,'sleep',side_effect=heartbeat_only):
            with self.assertRaisesRegex(operator.GateError,'publications_not_advancing'):operator.prepare(self.stats,self.control)
        for changes in ({'runtime_remaining_s':269.9},{'errors':1},{'control_errors':1},
                {'publisher_errors':1},{'mqtt_admission_open':False},{'outage':{'state':'active'}},
                {'publisher_control_revision':0},{'publisher_active':False},{'scenario':'cleaning'}):
            with self.subTest(changes=changes),self.assertRaises(operator.GateError):
                operator.ready(dict(self.state,**changes),self.command)

    def test_atomic_submit_preserves_control_and_saves_only_host_evidence(self):
        def completed(path,run_id,nonce,record):
            command=json.loads(self.control.read_text())
            self.assertEqual({k:v for k,v in command.items() if k!='outage'},self.command)
            self.assertEqual(command['outage'],{'run_id':run_id,'id':nonce})
            record['status']='HOST_RECOVERY_OBSERVED';record['outage']={'id':nonce,'target_s':75}
        with patch.object(operator,'prepare',return_value=self.prepared()),patch.object(operator,'monitor',side_effect=completed):
            result=operator.operate(self.stats,self.control,self.root,'GOTOWY')
        artifact=json.loads(Path(result['artifact']).read_text())
        self.assertEqual(artifact['esp_rx'],'UNVERIFIED');self.assertEqual(artifact['touch'],'UNVERIFIED')
        self.assertEqual(artifact['status'],'HOST_RECOVERY_OBSERVED')
        self.assertFalse(list(self.root.glob('*.tmp')))

    def test_control_change_prevents_submission_and_records_failure(self):
        prepared=self.prepared();self.control.write_text(json.dumps(dict(self.command,rate=2)))
        with patch.object(operator,'prepare',return_value=prepared),patch.object(operator,'monitor') as monitor:
            result=operator.operate(self.stats,self.control,self.root,'GOTOWY')
        self.assertEqual(result['reason'],'control_changed');monitor.assert_not_called()
        self.assertEqual(result['status'],'HOST_MONITOR_FAILED')
        self.assertNotIn('outage',json.loads(self.control.read_text()))

    def test_monitor_records_broker_metrics_and_never_restores_control(self):
        outage={'id':'once','state':'active','target_s':75,'reconnect_delay_s':None,'first_publish_delay_s':None}
        active=dict(self.state,outage=outage,mqtt_admission_open=False,connected=False)
        completed=dict(self.state,outage=dict(outage,state='completed',actual_s=75.01,reconnect_delay_s=2.,first_publish_delay_s=2.1))
        record={};original=self.control.read_bytes();output=io.StringIO()
        available=dict(self.state,outage=dict(outage,state='completed',actual_s=75.01))
        with patch.object(operator,'snapshot',side_effect=[active,active,available,available,completed]),patch.object(operator.time,'sleep'),contextlib.redirect_stdout(output):
            operator.monitor(self.stats,self.state['run_id'],'once',record)
        self.assertEqual(record['status'],'HOST_RECOVERY_OBSERVED')
        self.assertEqual(record['outage']['actual_s'],75.01);self.assertEqual(self.control.read_bytes(),original)
        events=[json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([event['event'] for event in events],['OFFLINE_STARTED','MQTT_AVAILABLE'])
        self.assertEqual(events[0]['target_s'],75);self.assertEqual(events[1]['actual_s'],75.01)

    def test_rejection_restart_timeout_and_interruption_leave_command_alone(self):
        for changes,reason in (({'last_outage_rejection':{'id':'once','reason':'outage_active'}},'outage_rejected'),
                ({'run_id':str(uuid.uuid4())},'broker_restarted')):
            with self.subTest(reason=reason),patch.object(operator,'snapshot',return_value=dict(self.state,**changes)):
                with self.assertRaisesRegex(operator.GateError,reason):operator.monitor(self.stats,self.state['run_id'],'once',{})
        with patch.object(operator.time,'monotonic',side_effect=[0,0,6]),patch.object(operator,'snapshot',return_value=self.state):
            with self.assertRaisesRegex(operator.GateError,'acknowledgement_timeout'):operator.monitor(self.stats,self.state['run_id'],'once',{})
        with patch.object(operator,'prepare',return_value=self.prepared()),patch.object(operator,'monitor',side_effect=KeyboardInterrupt):
            result=operator.operate(self.stats,self.control,self.root,'GOTOWY')
        self.assertEqual(result['status'],'MONITOR_INTERRUPTED')
        self.assertEqual(json.loads(self.control.read_text())['outage']['id'],result['id'])
