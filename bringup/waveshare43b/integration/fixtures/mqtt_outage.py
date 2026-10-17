#!/usr/bin/env python3
"""Local host-only MQTT outage operator. Default: inspect, never write control.

Only --confirm GOTOWY submits one broker-owned 75-second MQTT admission outage.
TCP/TLS LISTEN remains open. Results prove host transport progress, never ESP RX
or touch responsiveness. This utility never connects to a panel or printer.
"""
import argparse, json, time, uuid
from pathlib import Path

class GateError(ValueError):pass

def read_json(path):
    try:
        raw=path.read_text();value=json.loads(raw)
        if not isinstance(value,dict):raise ValueError()
        return value,raw
    except (OSError,ValueError):raise GateError('unreadable_json') from None

def snapshot(path):
    state,_=read_json(path)
    required={'run_id','server_state','listening','mqtt_admission_open','connected',
        'publisher_active','publisher_state','publisher_errors','publisher_last_error',
        'heartbeat_elapsed_s','elapsed_s','runtime_remaining_s','published','errors',
        'control_errors','last_control_error','control_revision','publisher_control_revision',
        'scenario','rate','padding','outage','last_outage_rejection'}
    if not required<=state.keys():raise GateError('unsupported_broker_stats')
    try:
        uuid.UUID(state['run_id'])
        age=time.time()-path.stat().st_mtime
        lag=state['elapsed_s']-state['heartbeat_elapsed_s']
        if not -1<=age<=3 or not -.001<=lag<=1:raise ValueError()
    except (OSError,TypeError,ValueError,AttributeError):raise GateError('stale_broker_stats') from None
    return state

def ready(state,control):
    if state['server_state']!='running' or state['publisher_state']!='running':raise GateError('broker_not_running')
    if not all(state[key] is True for key in ('listening','mqtt_admission_open','connected','publisher_active')):
        raise GateError('broker_not_ready')
    if any(state[key]!=0 for key in ('errors','publisher_errors','control_errors')):
        raise GateError('broker_errors_present')
    if state['publisher_last_error'] is not None or state['last_control_error'] is not None:
        raise GateError('broker_errors_present')
    if state['outage'] is not None:
        if not isinstance(state['outage'],dict):raise GateError('unsupported_broker_stats')
        if state['outage'].get('state')=='active':raise GateError('outage_already_active')
    try:
        if state['runtime_remaining_s']<270:raise GateError('insufficient_runtime')
        if control.get('scenario')!='printing' or not 0<float(control.get('rate',0))<=30:
            raise GateError('printing_control_required')
        if any(state[key]!=control.get(key) for key in ('scenario','rate','padding')):
            raise GateError('control_not_applied')
        if state['publisher_control_revision']!=state['control_revision']:raise GateError('control_not_applied')
    except TypeError:raise GateError('unsupported_broker_stats') from None

def prepare(stats_path,control_path):
    control,raw=read_json(control_path);first=snapshot(stats_path);ready(first,control)
    time.sleep(1.2)
    second=snapshot(stats_path);ready(second,control)
    if read_json(control_path)[1]!=raw:raise GateError('control_changed')
    if second['run_id']!=first['run_id']:raise GateError('broker_restarted')
    if second['heartbeat_elapsed_s']<=first['heartbeat_elapsed_s']:raise GateError('heartbeat_not_advancing')
    if second['published']<=first['published']:raise GateError('publications_not_advancing')
    return second,control,raw

def atomic_json(path,value):
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(value,indent=2)+'\n');temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)

def monitor(stats_path,run_id,nonce,record):
    started=time.monotonic();deadline=started+260;acknowledged=False;available=False
    while time.monotonic()<deadline:
        state=snapshot(stats_path)
        if state['run_id']!=run_id:raise GateError('broker_restarted')
        if state['server_state']!='running' or not state['listening']:raise GateError('broker_stopped')
        if any(state[key]!=0 for key in ('errors','publisher_errors','control_errors')):raise GateError('broker_errors_present')
        rejection=state['last_outage_rejection']
        if rejection and rejection.get('id')==nonce:raise GateError('outage_rejected_'+str(rejection.get('reason','unknown')))
        outage=state['outage']
        if outage and outage.get('id')==nonce:
            if not acknowledged:
                print(json.dumps({'event':'OFFLINE_STARTED','id':nonce,'target_s':outage.get('target_s')}),flush=True)
            acknowledged=True
            record['outage']=dict(outage)
            if outage.get('target_s')!=75:raise GateError('unexpected_outage_duration')
            if outage.get('state')=='interrupted':raise GateError('outage_interrupted')
            if not available and outage.get('state')=='completed' and state['mqtt_admission_open']:
                print(json.dumps({'event':'MQTT_AVAILABLE','id':nonce,'actual_s':outage.get('actual_s')}),flush=True)
                available=True
            if (outage.get('state')=='completed' and outage.get('reconnect_delay_s') is not None
                    and outage.get('first_publish_delay_s') is not None):
                if not state['mqtt_admission_open'] or not state['connected']:raise GateError('recovery_not_live')
                record['status']='HOST_RECOVERY_OBSERVED';return
        if not acknowledged and time.monotonic()-started>=5:raise GateError('acknowledgement_timeout')
        time.sleep(.2)
    raise GateError('monitor_timeout')

def operate(stats_path,control_path,output_dir,confirm=None):
    state,control,raw=prepare(stats_path,control_path)
    if confirm is None:return {'status':'READY_READ_ONLY','run_id':state['run_id'],'runtime_remaining_s':state['runtime_remaining_s']}
    if confirm!='GOTOWY':raise GateError('literal_GOTOWY_required')
    nonce=uuid.uuid4().hex;artifact=output_dir/('mqtt-outage-'+nonce+'.json')
    record={'status':'PREPARED','run_id':state['run_id'],'id':nonce,'target_s':75,
        'evidence_scope':'host_only','esp_rx':'UNVERIFIED','touch':'UNVERIFIED',
        'baseline':{key:state[key] for key in ('published','errors','publisher_errors','control_errors')}}
    # Reserve a unique evidence file before submitting any outage command.
    with artifact.open('x') as stream:json.dump(record,stream,indent=2)
    try:
        if read_json(control_path)[1]!=raw:raise GateError('control_changed')
        control['outage']={'id':nonce,'run_id':state['run_id']}
        atomic_json(control_path,control)
        record['status']='SUBMITTED';atomic_json(artifact,record)
        monitor(stats_path,state['run_id'],nonce,record)
    except KeyboardInterrupt:record.update(status='MONITOR_INTERRUPTED',reason='broker_timer_remains_autonomous')
    except (GateError,OSError) as error:record.update(status='HOST_MONITOR_FAILED',reason=str(error) if isinstance(error,GateError) else 'local_io_error')
    finally:atomic_json(artifact,record)
    record['artifact']=str(artifact);return record

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('stats','control'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--output-dir',type=Path)
    parser.add_argument('--confirm',choices=['GOTOWY'])
    args=parser.parse_args()
    try:result=operate(args.stats,args.control,args.output_dir or args.stats.parent,args.confirm)
    except (GateError,OSError) as error:
        parser.exit(1,('FAIL: '+str(error) if isinstance(error,GateError) else 'FAIL: local_io_error')+'\n')
    print(json.dumps(result,indent=2))
    if result['status'] not in ('READY_READ_ONLY','HOST_RECOVERY_OBSERVED'):raise SystemExit(1)

if __name__=='__main__':main()
