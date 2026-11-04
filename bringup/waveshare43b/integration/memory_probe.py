#!/usr/bin/env python3
"""Read-only bounded numeric diagnostics; no configuration or control requests."""
import argparse,ipaddress,json,time,urllib.request
from pathlib import Path
from pclk_probe import FIELDS

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ip',required=True);p.add_argument('--seconds',type=int,default=120);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 ip=ipaddress.IPv4Address(a.ip)
 if not ip.is_private or ip.is_unspecified or ip.is_multicast:raise SystemExit('LAN IPv4 required')
 if not 5<=a.seconds<=1800:raise SystemExit('Duration must be 5..1800 seconds')
 if a.output.exists():raise SystemExit('Never overwrite existing evidence')
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 def get(path):
  with opener.open(f'http://{ip}{path}',timeout=5) as r:b=r.read(8193)
  if len(b)>8192:raise ValueError('Oversize response')
  return json.loads(b)
 report={'samples':[],'errors':[],'sampling_note':'50ms timer and stage boundaries; short minima may be missed. Stage overlap is correlation, not causation.'}
 start=time.monotonic()
 for n in range(a.seconds//5+1):
  time.sleep(max(0,start+n*5-time.monotonic()))
  try:
   raw=get('/monitor/status');status={k:raw[k] for k in FIELDS if k in raw and (raw[k] is None or type(raw[k]) in (int,bool))}
   memory=get('/diagnostics/memory')
   if memory.get('version')!=1:raise ValueError('Wrong diagnostics')
   report['samples'].append({'elapsed_s':round(time.monotonic()-start,3),'status':status,'memory':memory})
   if n%6==0:print(json.dumps({'elapsed_s':round(time.monotonic()-start),'free':status.get('free_heap'),'sampled_min':memory['sampled_min_free_internal'],'largest_min':memory['sampled_min_largest_internal8'],'failures':memory['allocation_failures'],'stage_mask':memory['min_stage_mask']}),flush=True)
  except Exception as e:report['errors'].append({'elapsed_s':round(time.monotonic()-start,3),'type':type(e).__name__})
  tmp=a.output.with_suffix('.tmp');tmp.write_text(json.dumps(report,indent=2)+'\n');tmp.replace(a.output)
 print('Saved',len(report['samples']),'samples;',len(report['errors']),'errors',flush=True)
if __name__=='__main__':main()
