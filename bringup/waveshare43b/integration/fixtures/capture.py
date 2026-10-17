#!/usr/bin/env python3
"""Decode existing read-only W43CAP01 diagnostic frames to PNG without dependencies.
Canvas/front pixels verify software output, not physical LCD scanout quality.
"""
import argparse,ipaddress,struct,urllib.request,zlib
from pathlib import Path

def decode(raw,prefix):
 if raw[:8]!=b'W43CAP01' or len(raw)!=1536040:raise ValueError('Wrong capture format/length')
 width,height=struct.unpack_from('<HH',raw,8)
 if (width,height)!= (800,480) or struct.unpack_from('<I',raw,20)[0]!=1:raise ValueError('Wrong dimensions/format')
 def chunk(name,data):return struct.pack('!I',len(data))+name+data+struct.pack('!I',zlib.crc32(name+data)&0xffffffff)
 for side in (0,1):
  rows=bytearray()
  for y in range(height):
   rows.append(0)
   offset=40+y*width*4+side*width*2
   for x in range(width):
    v=raw[offset+2*x]|raw[offset+2*x+1]<<8
    rows.extend((((v>>11)&31)*255//31,((v>>5)&63)*255//63,(v&31)*255//31))
  png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b'')
  Path(str(prefix)+('-canvas.png' if side==0 else '-front.png')).write_bytes(png)
 return {'frame':struct.unpack_from('<I',raw,12)[0],'uptime_ms':struct.unpack_from('<I',raw,16)[0],
         'canvas_equals_front':all(raw[40+y*3200:40+y*3200+1600]==raw[40+y*3200+1600:40+(y+1)*3200] for y in range(480))}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ip',required=True);p.add_argument('--output-prefix',type=Path,required=True);a=p.parse_args()
 ip=ipaddress.IPv4Address(a.ip)
 if not ip.is_private or ip.is_unspecified:raise SystemExit('LAN IP required')
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 with opener.open(f'http://{ip}/diagnostics/frame',timeout=20) as response:raw=response.read(1536041)
 import json
 print(json.dumps(decode(raw,a.output_prefix)))
if __name__=='__main__':main()
