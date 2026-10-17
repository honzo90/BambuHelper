#!/usr/bin/env python3
"""Bounded synthetic LAN MQTT/TLS fixture. No forwarding, no printer controls.
Only the designated panel IP is accepted, with TESTONLY credentials. All outputs
are counters/scenario names; never record CONNECT payloads or real credentials.
Run with a local self-signed certificate and an explicit local IPv4 address.
"""
import argparse, asyncio, contextlib, ipaddress, json, re, socket, ssl, struct, time, uuid
from pathlib import Path
SERIAL='SYNTHETIC000001'
TOPIC=f'device/{SERIAL}/report'.encode()
OUTAGE_SECONDS=75.0
RECOVERY_RESERVE_SECONDS=190.0
HEARTBEAT_SECONDS=0.1

def encoded_length(n):
    if not 0 <= n <= 16384: raise ValueError('packet exceeds fixture bound')
    out=bytearray()
    while True:
        b=n%128;n//=128;out.append(b | (128 if n else 0))
        if not n:return bytes(out)

def packet(kind,body):return bytes([kind])+encoded_length(len(body))+body

def text_at(body,offset):
    if offset+2>len(body):raise ValueError('short string')
    n=int.from_bytes(body[offset:offset+2],'big');end=offset+2+n
    if end>len(body):raise ValueError('short string body')
    return body[offset+2:end],end

def validate_connect(body):
    protocol,pos=text_at(body,0)
    if protocol!=b'MQTT' or len(body)<pos+4 or body[pos]!=4:return False
    flags=body[pos+1];pos+=4
    # Only username/password, clean-session flags: no Will and no reserved bit.
    if flags & ~0xc2 or flags & 0xc0 != 0xc0:return False
    _,pos=text_at(body,pos)
    username,pos=text_at(body,pos);password,pos=text_at(body,pos)
    return pos==len(body) and username==b'bblp' and password==b'TESTONLY'

async def read_packet(reader):
    kind=(await reader.readexactly(1))[0];length=0
    for i in range(4):
        b=(await reader.readexactly(1))[0];length+=(b&127)<<(7*i)
        if length>16384:raise ValueError('oversize')
        if not b&128:return kind,await reader.readexactly(length)
    raise ValueError('invalid length')

def report(seq,scenario,padding):
    stage={'printing':0,'cleaning':14,'leveling':1,'calibration':51,'hms':0}.get(scenario,0)
    p={'sequence_id':str(seq),'command':'push_status','gcode_state':'RUNNING','mc_percent':seq%100,
       'mc_remaining_time':32,'gcode_file':'TEST synthetic model.gcode','subtask_name':'TEST - synthetic MQTT',
       'layer_num':1+seq%200,'total_layer_num':200,'stg_cur':stage,
       'nozzle_temper':220,'nozzle_target_temper':220,'bed_temper':60,'bed_target_temper':60,
       'chamber_temper':36,'spd_lvl':2,'fan_gear':8421631,'hms':[], 'print_error':0,
       'ams':{'tray_now':'1','ams_exist_bits':'1','tray_exist_bits':'11',
              'ams':[{'id':'0','temp':'39','humidity':'1','humidity_raw':'15','dry_time':0,
                'tray':[{'id':'0','tray_type':'ASA','tray_color':'222222FF','remain':-1},
                        {'id':'1','tray_type':'PETG','tray_color':'79D638FF','remain':87},
                        {'id':'2'}, {'id':'3','tray_type':'PLA','tray_color':'FF9D00FF','remain':45}]}]}}
    # Known HMS fixture is added by the driver after confirming an exact code in
    # the repository's own catalogue; never invent a production diagnostic.
    if scenario=='hms':
        p['print_error']=0x03008001
        p['hms']=[{'attr':0x03000100,'code':0x00010001}]
    if scenario in ('drying','printing_drying'):
        p['ams']['ams'][0].update(dry_time=150,temp='55',humidity_raw='14')
        if scenario=='drying':
            p.update(gcode_state='IDLE',mc_percent=0,mc_remaining_time=0)
        else:
            p.update(mc_percent=68,mc_remaining_time=92)
    data={'print':p,'fixture_padding':'x'*padding}
    return json.dumps(data,separators=(',',':')).encode()

class Broker:
    def __init__(self,args):
        self.args=args;self.stats={'accepted':0,'rejected':0,'published':0,'bytes':0,'client_messages_ignored':0,'ping':0,'disconnects':0,'errors':0,'scenario':'printing','rate':1,'padding':0,
            'control_revision':0,'control_reads':0,'publisher_control_revision':0,
            'publisher_active':False,'publisher_state':'idle','publisher_errors':0,
            'publisher_last_error':None,'publish_in_flight':False,'last_publish_elapsed_s':None}
        self.live=False;self.start=time.monotonic();self.last_control=None
        self.server=None;self.deadline=None;self.stopping=False
        self.writers=set();self.clients=set();self.consumed_outages=set()
        self.base_control=(1.0,0,'printing');self.have_control=False
        self.outage_deadline=None
        self.stats.update(run_id=str(uuid.uuid4()),server_state='starting',
            heartbeat_elapsed_s=None,control_errors=0,last_control_error=None,
            outage=None,last_outage_rejection=None)
    def attach_server(self,server,seconds):
        self.server=server;self.deadline=time.monotonic()+seconds
        self.stats.update(server_state='running',bound_port=server.sockets[0].getsockname()[1])
        self.save()
    def mqtt_open(self):
        return (not self.stopping and self.outage_deadline is None and self.base_control[2]!='offline'
            and (self.deadline is None or time.monotonic()<self.deadline)
            and (self.server is None or self.server.is_serving()))
    def finish_outage_if_due(self):
        now=time.monotonic()
        if self.outage_deadline is not None and now>=self.outage_deadline:
            outage=self.stats['outage'];elapsed=now-self.start
            outage.update(state='completed',end_elapsed_s=elapsed,
                actual_s=elapsed-outage['start_elapsed_s'],
                timing_error_ms=(now-self.outage_deadline)*1000)
            self.outage_deadline=None
    def request_outage(self,request):
        if not isinstance(request,dict):raise ValueError('invalid outage request')
        nonce=request.get('id')
        if not isinstance(nonce,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',nonce):
            raise ValueError('invalid outage id')
        if nonce in self.consumed_outages:return
        if len(self.consumed_outages)>=32:
            self.stats['last_outage_rejection']={'id':nonce,'reason':'request_limit'};return
        # Consume rejected IDs too: an overlapping request cannot start later.
        self.consumed_outages.add(nonce)
        reason=None;now=time.monotonic()
        if request.get('run_id')!=self.stats['run_id']:reason='wrong_broker_run'
        elif self.outage_deadline is not None:reason='outage_active'
        elif self.stopping or not self.server or not self.server.is_serving():reason='not_listening'
        elif self.deadline is None or self.deadline-now<OUTAGE_SECONDS+RECOVERY_RESERVE_SECONDS:reason='insufficient_runtime'
        elif not self.live or not self.stats['publisher_active']:reason='no_live_session'
        elif self.base_control[2]=='offline' or self.base_control[0]<=0:reason='not_publishing'
        if reason:
            self.stats['last_outage_rejection']={'id':nonce,'reason':reason};return
        self.outage_deadline=now+OUTAGE_SECONDS
        self.stats['outage']={'id':nonce,'state':'active','target_s':OUTAGE_SECONDS,
            'start_elapsed_s':now-self.start,'deadline_elapsed_s':self.outage_deadline-self.start,
            'end_elapsed_s':None,'actual_s':None,'timing_error_ms':None,
            'reconnect_elapsed_s':None,'reconnect_delay_s':None,
            'first_publish_elapsed_s':None,'first_publish_delay_s':None}
        # Close MQTT admission and drop existing transports at the same boundary.
        # TCP/TLS LISTEN deliberately stays alive throughout the outage.
        for writer in tuple(self.writers):writer.transport.abort()
        for task in tuple(self.clients):task.cancel()
        self.save()
    def note_recovery(self,event):
        outage=self.stats['outage']
        if not outage or outage['state']!='completed' or outage[event+'_elapsed_s'] is not None:return
        elapsed=time.monotonic()-self.start
        outage[event+'_elapsed_s']=elapsed
        outage[event+'_delay_s']=elapsed-outage['end_elapsed_s']
    def control(self):
        self.finish_outage_if_due()
        try:
            d=json.loads(self.args.control.read_text());rate=float(d.get('rate',1));pad=int(d.get('padding',0));scenario=d.get('scenario','printing')
            if not 0<=rate<=30 or not 0<=pad<=8192 or scenario not in ('printing','cleaning','leveling','calibration','hms','offline','drying','printing_drying'):raise ValueError('invalid control')
            self.base_control=(rate,pad,scenario);self.have_control=True
            if 'outage' in d:self.request_outage(d['outage'])
        except (OSError,ValueError,TypeError,AttributeError):
            self.stats['control_errors']+=1;self.stats['last_control_error']='invalid_or_unreadable_control'
            if not self.have_control:raise ValueError('invalid initial control') from None
        rate,pad,scenario=self.base_control
        if self.outage_deadline is not None:rate,pad,scenario=0,0,'offline'
        current=(rate,pad,scenario)
        if current!=self.last_control:
            self.stats['control_revision']+=1;self.last_control=current
        self.stats['control_reads']+=1
        self.stats.update(rate=rate,padding=pad,scenario=scenario)
        return rate,pad,scenario
    def save(self):
        now=time.monotonic()
        d=dict(self.stats,elapsed_s=round(now-self.start,3),connected=self.live,
            listening=bool(self.server and self.server.is_serving()),
            mqtt_admission_open=self.mqtt_open(),
            runtime_remaining_s=max(0,self.deadline-now) if self.deadline is not None else None)
        tmp=self.args.output.with_suffix('.tmp');tmp.write_text(json.dumps(d,indent=2)+'\n');tmp.replace(self.args.output)
    async def publish(self,writer):
        seq=0
        self.stats['publisher_active']=True
        try:
            while True:
                rate,pad,scenario=self.control()
                # A paused publisher acknowledges this revision only after the
                # previous write/drain finished. No more reports are in flight.
                self.stats.update(publisher_control_revision=self.stats['control_revision'],
                    publisher_state='offline' if scenario=='offline' else 'paused' if rate==0 else 'running')
                self.save()
                if scenario=='offline':return
                if rate==0:await asyncio.sleep(.1);continue
                body=report(seq,scenario,pad);seq+=1
                data=packet(0x30,struct.pack('!H',len(TOPIC))+TOPIC+body)
                self.stats['publish_in_flight']=True;self.save()
                writer.write(data);await asyncio.wait_for(writer.drain(),5)
                self.stats['published']+=1;self.stats['bytes']+=len(data)
                self.stats.update(publish_in_flight=False,last_publish_elapsed_s=round(time.monotonic()-self.start,3))
                self.note_recovery('first_publish')
                # Persist completed TX before sleeping, including the final
                # report of a phase. This is transport progress, not an RX ACK.
                self.save()
                await asyncio.sleep(1/rate)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.stats['publisher_errors']+=1;self.stats['errors']+=1
            # Fixed categories only: exception messages can contain payloads.
            category='timeout' if isinstance(error,TimeoutError) else 'connection' if isinstance(error,ConnectionError) else 'invalid_control' if isinstance(error,ValueError) else 'unexpected'
            self.stats.update(publisher_state='failed',publisher_last_error=category)
        finally:
            self.stats.update(publisher_active=False,publish_in_flight=False)
            if self.stats['publisher_state'] not in ('failed','offline'):self.stats['publisher_state']='stopped'
            writer.close();self.save()
    async def client(self,reader,writer):
        publisher=None;incoming=None;owner=False
        task=asyncio.current_task();self.clients.add(task);self.writers.add(writer)
        try:
            peer=writer.get_extra_info('peername')[0]
            if peer!=self.args.panel or self.live:
                self.stats['rejected']+=1;return
            if self.control()[2]=='offline' or not self.mqtt_open():return
            kind,body=await asyncio.wait_for(read_packet(reader),10)
            if kind!=0x10 or not validate_connect(body):self.stats['rejected']+=1;return
            # CONNECT reading yielded: another client or an outage may now own
            # the state. Do not accept two owners or admit a delayed handshake.
            if self.live or not self.mqtt_open():self.stats['rejected']+=1;return
            self.live=True;owner=True;self.stats['accepted']+=1
            writer.get_extra_info('socket').setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,8192)
            writer.transport.set_write_buffer_limits(high=16384,low=8192)
            writer.write(b'\x20\x02\x00\x00');await writer.drain()
            self.note_recovery('reconnect');self.save()
            while True:
                incoming=asyncio.create_task(asyncio.wait_for(read_packet(reader),90))
                if publisher is not None:
                    done,_=await asyncio.wait((incoming,publisher),return_when=asyncio.FIRST_COMPLETED)
                    # A dead publisher must close the session even when the
                    # receive side remains healthy or has no packets to send.
                    if publisher in done:
                        await publisher
                        return
                kind,body=await incoming;incoming=None
                if kind==0x82:
                    topic,pos=text_at(body,2)
                    if topic!=TOPIC or pos+1!=len(body):raise ValueError('unexpected subscription')
                    writer.write(packet(0x90,body[:2]+b'\x00'));await writer.drain()
                    if publisher is None:publisher=asyncio.create_task(self.publish(writer))
                elif kind==0xc0:
                    self.stats['ping']+=1;writer.write(b'\xd0\x00');await writer.drain()
                elif kind>>4==3:
                    self.stats['client_messages_ignored']+=1
                    if (kind>>1)&3:raise ValueError('only qos0 accepted')
                elif kind==0xe0:return
                else:raise ValueError('unexpected packet')
                self.save()
        except (asyncio.IncompleteReadError,ConnectionError,TimeoutError):pass
        except Exception:self.stats['errors']+=1
        finally:
            try:
                if incoming:
                    incoming.cancel()
                    with contextlib.suppress(asyncio.CancelledError,Exception):await incoming
                if publisher:
                    publisher.cancel()
                    with contextlib.suppress(asyncio.CancelledError,Exception):await publisher
            finally:
                if owner:self.live=False
                self.stats['disconnects']+=1;writer.close()
                self.writers.discard(writer);self.clients.discard(task)
                self.save()
                with contextlib.suppress(Exception):await asyncio.wait_for(writer.wait_closed(),5)

    async def supervise(self):
        # Never depend on a publisher/client to service commands or deadlines.
        while not self.stopping and time.monotonic()<self.deadline:
            self.control()
            self.stats['heartbeat_elapsed_s']=time.monotonic()-self.start
            self.save()
            deadline=min(self.deadline,self.outage_deadline or self.deadline)
            await asyncio.sleep(min(HEARTBEAT_SECONDS,max(0,deadline-time.monotonic())))

    async def shutdown(self):
        self.stopping=True;self.stats['server_state']='stopping'
        if self.server:
            self.server.close()
            # Includes TLS handshakes that have not reached client() yet.
            if hasattr(self.server,'abort_clients'):self.server.abort_clients()
        for writer in tuple(self.writers):writer.transport.abort()
        tasks=tuple(self.clients)
        for task in tasks:task.cancel()
        if tasks:
            done,pending=await asyncio.wait(tasks,timeout=6)
            for task in pending:task.cancel()
            for task in done:
                with contextlib.suppress(asyncio.CancelledError,Exception):task.result()
        if self.server:
            try:await asyncio.wait_for(self.server.wait_closed(),2)
            except TimeoutError:self.stats['shutdown_error']='transport_cleanup_timeout'
        if self.outage_deadline is not None:
            self.stats['outage']['state']='interrupted';self.outage_deadline=None
        self.live=False;self.stats.update(server_state='stopped',publisher_active=False,
            publish_in_flight=False,shutdown_elapsed_s=time.monotonic()-self.start)
        self.save()

async def serve(args,ctx,port=8883):
    b=Broker(args);b.control()
    server=await asyncio.start_server(b.client,args.bind,port,ssl=ctx,ssl_handshake_timeout=10 if ctx else None,limit=32768)
    # Do not overwrite another broker's health file if bind failed.
    b.server=server
    try:
        b.attach_server(server,args.seconds)
        print('Synthetic MQTT/TLS ready; no forwarding; runtime bounded.',flush=True)
        await b.supervise()
    finally:await b.shutdown()
    return b

async def run(args):
    ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.minimum_version=ssl.TLSVersion.TLSv1_2;ctx.load_cert_chain(args.cert,args.key)
    return await serve(args,ctx)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('bind','panel'):p.add_argument('--'+name,required=True)
    for name in ('cert','key','control','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--seconds',type=int,default=1800);a=p.parse_args()
    for value in (a.bind,a.panel):
        ip=ipaddress.IPv4Address(value)
        if not ip.is_private or ip.is_unspecified or ip.is_loopback or ip.is_link_local:raise SystemExit('Explicit LAN addresses required')
    if not 1<=a.seconds<=3600:raise SystemExit('Bounded duration required')
    asyncio.run(run(a))
if __name__=='__main__':main()
