#!/usr/bin/env python3
"""Render actual portable firmware scene/palette/assets, without physical hardware.

Only Canvas drawing primitives are supplied by the host. Layout output deliberately
excludes fonts and telemetry; it is not a framebuffer capture or full UI proof.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import subprocess
import tempfile
import zlib

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]

def chunk(kind,payload):
    return struct.pack('>I',len(payload))+kind+payload+struct.pack('>I',zlib.crc32(kind+payload)&0xffffffff)

def png_from_ppm(source,destination):
    data=source.read_bytes();magic,size,maxvalue,pixels=data.split(b'\n',3)
    if magic!=b'P6' or maxvalue!=b'255':raise ValueError('Unexpected native renderer output')
    width,height=map(int,size.split())
    if len(pixels)!=width*height*3:raise ValueError('Truncated native pixels')
    scan=b''.join(b'\0'+pixels[y*width*3:(y+1)*width*3] for y in range(height))
    destination.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+
                           chunk(b'IDAT',zlib.compress(scan,9))+chunk(b'IEND',b''))
    return {'width':width,'height':height,'sha256':hashlib.sha256(destination.read_bytes()).hexdigest()}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=HERE.parent/'test-output/native-scene-v2')
    args=parser.parse_args();args.output_dir.mkdir(parents=True,exist_ok=True)
    record={'scope':'native production Scene/palette/assets with host Canvas; no fonts/live telemetry or hardware scanout',
            'source_sha256':{},'images':[]}
    for path in [HERE/'preview_native.cpp',ROOT/'include/ws43b_native_scene.h',ROOT/'include/ws43b_visual_assets.h',ROOT/'include/ws43b_visual_assets_data.h']:
        record['source_sha256'][str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory() as temporary:
        binary=Path(temporary)/'preview_native'
        subprocess.run(['clang++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-I',str(ROOT/'include'),
                        str(HERE/'preview_native.cpp'),'-o',str(binary)],check=True)
        result=subprocess.run([str(binary),'--verify'],check=True,text=True,capture_output=True)
        record['tests']=json.loads(result.stdout)
        cases=[('hero-green-68',68,'67b6','0084',2700,'hero'),
               ('hero-green-36',36,'67b6','0084',2700,'hero'),
               ('hero-green-49',49,'67b6','0084',2700,'hero'),
               ('hero-green-0',0,'67b6','0084',1800,'hero'),
               ('hero-green-100',100,'67b6','0084',5400,'hero'),
               ('hero-white-68',68,'ffff','0084',2700,'hero'),
               ('hero-black-68',68,'0000','0084',2700,'hero'),
               ('hero-red-68',68,'f800','0084',2700,'hero'),
               ('hero-blue-68',68,'001f','0084',2700,'hero'),
               ('native-artwork-layout',68,'67b6','0084',2700,'layout')]
        for name,progress,color,theme,phase,mode in cases:
            ppm=Path(temporary)/(name+'.ppm');png=args.output_dir/(name+'.png')
            subprocess.run([str(binary),'--preview',str(ppm),str(progress),color,theme,str(phase),mode],check=True)
            record['images'].append({'name':name,'progress':progress,'rgb565_tint':color,'theme':theme,'phase':phase,
                                     **png_from_ppm(ppm,png)})
    (args.output_dir/'preview-result.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({'output':str(args.output_dir),'tests':record['tests'],'images':len(record['images'])}))

if __name__=='__main__':main()
