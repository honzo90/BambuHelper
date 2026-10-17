"""Validate approved sprite provenance, lossless row coding and native safety."""
from pathlib import Path
import hashlib
import importlib.util
import json
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
PIPELINE = ROOT / 'bringup/waveshare43b/integration/visual-v2'
spec = importlib.util.spec_from_file_location('visual_v2_generator', PIPELINE / 'generate.py')
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class VisualAssets(unittest.TestCase):
    def test_source_dimensions_provenance_and_pixel_roundtrip(self):
        manifest = json.loads((PIPELINE / 'manifest.json').read_text())
        self.assertLess(manifest['total_encoded_and_offsets_bytes'], 165 * 1024)
        self.assertEqual(hashlib.sha256((ROOT / manifest['generated_header']).read_bytes()).hexdigest(),
                         manifest['generated_header_sha256'])
        expected = {'Nozzle':(42,46), 'Bed':(42,46), 'Chamber':(42,46),
                    'Print':(33,33), 'AMS':(33,33), 'Details':(33,33),
                    'Settings':(33,33), 'Spool':(64,69), 'Model':(160,132),
                    'Plate':(220,108), 'Head':(36,47), 'Clock':(33,33),
                    'Weather':(33,33), 'Network':(33,33), 'Check':(33,33),
                    'Pause':(33,33), 'Alert':(33,33), 'EmptySlot':(33,33),
                    'UnknownData':(33,33), 'Printer':(33,33), 'Fan':(33,33)}
        self.assertEqual({asset['name'] for asset in manifest['assets']},set(expected))
        for asset in manifest['assets']:
            with self.subTest(asset=asset['name']):
                width,height=asset['width'],asset['height']
                self.assertEqual((width,height),expected[asset['name']])
                self.assertEqual(generator.sha(PIPELINE / asset['source']), asset['source_sha256'])
                self.assertEqual(generator.source_dimensions(PIPELINE / asset['source']), asset['source_pixel_dimensions'])
                if asset['name']=='Spool':
                    self.assertEqual(asset['source_pixel_dimensions'],[1254,1254])
                    self.assertEqual((asset['image_width'],asset['image_height']),(1280,1280))
                if asset['name'] in ('Model','Plate','Head'):
                    self.assertEqual(asset['source_pixel_dimensions'],[1448,1086])
                raw=(PIPELINE / 'rasterized' / (asset['name']+'.rgba')).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(),asset['rgba_sha256'])
                self.assertEqual(len(raw),width*height*4)
                offsets,data,tinted=generator.encode(asset,raw)
                self.assertEqual(len(data),asset['encoded_bytes'])
                self.assertEqual(tinted,asset['material_pixels'])
                if asset['name'] in ('Check','Pause','Alert'):
                    self.assertGreater(tinted,40)
                    self.assertLess(tinted,width*height//2)
                elif asset['name'] in ('Clock','Weather','Network','EmptySlot','UnknownData','Printer','Fan'):
                    self.assertEqual(tinted,0)
                decoded=[None]*(width*height)
                for y in range(height):
                    at,end,x=offsets[y],offsets[y+1],0
                    while at<end:
                        skip,flags=struct.unpack_from('<HH',data,at);at+=4;x+=skip
                        count,mask=flags&0x7fff,flags>>15
                        self.assertLessEqual(x+count,width)
                        for _ in range(count):
                            color,alpha=struct.unpack_from('<HB',data,at);at+=3
                            self.assertGreater(alpha,0)
                            decoded[y*width+x]=(color,alpha,mask);x+=1
                    self.assertEqual(at,end)
                for i,pixel in enumerate(decoded):
                    r,g,b,a=raw[i*4:i*4+4]
                    if not a:self.assertIsNone(pixel)
                    else:self.assertEqual(pixel,(generator.rgb565(r,g,b),a,
                         generator.material(r,g,b) if asset.get('green_material') else 0))
                self.assertTrue(any(raw[i]==0 for i in range(3,len(raw),4)))
        for name,digest in manifest['pipeline_sha256'].items():
            self.assertEqual(generator.sha(PIPELINE/name),digest,name)

    def test_native_alpha_recolor_chunking_and_malformed_rows(self):
        code=r'''
#include "ws43b_visual_assets.h"
#include <cassert>
#include <array>
#include <vector>
using namespace ws43b_assets;
int main() {
  for(unsigned i=0;i<unsigned(Asset::Count);++i)assert(valid(descriptor(Asset(i))));
  assert(!valid(descriptor(Asset::Count)));
  assert(descriptor(Asset::Model).width==160&&descriptor(Asset::Plate).width==220);
  // Transparent first pixel, alpha-covered material, then fixed opaque metal.
  uint32_t offsets[]={0,14};
  uint8_t data[]={1,0,1,128,0xe0,0x07,128, 0,0,1,0,0x10,0x84,255};
  Sprite sample{3,1,offsets,2,data,sizeof(data)};
  assert(valid(sample));
  assert(blend(0xffff,0,0)==0&&blend(0xffff,0,255)==0xffff);
  assert(blend(0xffff,0,128)==rgb565(128,128,128));
  assert(recolor(0x07e0,0)==rgb565(20,20,20));
  assert(recolor(rgb565(0,80,0),0)!=recolor(0x07e0,0));
  for(unsigned shade=0;shade<=255;++shade) {
    const auto lit=recolor(rgb565(0,shade,0),0);
    assert(red(lit)<=20&&green(lit)<=20&&blue(lit)<=20);
  }
  // The dark-only neutral reflection fades toward the 48/255 threshold.
  unsigned previousExtra=21;
  for(unsigned value=0;value<=255;++value) {
    const auto tint=rgb565(value,value,value),lit=recolor(0x07e0,tint);
    const unsigned maximum=green(tint)>red(tint)?green(tint):red(tint);
    if(maximum>=48)assert(lit==tint);
    else {
      const unsigned extra=green(lit)-green(tint);
      assert(extra<=previousExtra+4);previousExtra=extra;
    }
  }
  for(uint16_t tint:{uint16_t(0xf800),uint16_t(0x07e0),uint16_t(0x001f),uint16_t(0xffff),uint16_t(0)}) {
    const uint16_t materialColor=tint? tint:rgb565(20,20,20);
    assert(recolor(0x07e0,tint)==materialColor);
    std::array<uint16_t,3> result={0x1234,0x1234,0x1234};unsigned callbacks=0,backgrounds=0;
    auto background=[&](int x,int y){assert(x==11&&y==20);++backgrounds;return uint16_t(0x001f);};
    auto sink=[&](int x,int y,const uint16_t *pixels,size_t count){
      assert(y==20&&count==1);++callbacks;result[size_t(x-10)]=pixels[0];
    };
    assert(draw(sample,10,20,background,sink,true,tint));
    assert(callbacks==2&&backgrounds==1&&result[0]==0x1234);
    assert(result[1]==blend(materialColor,0x001f,128));assert(result[2]==0x8410);
    assert(draw(sample,10,20,background,sink,false,tint));
    assert(result[1]==blend(0x07e0,0x001f,128)&&result[2]==0x8410);
  }
  bool negativeBackgroundSeen=false;
  assert(draw(sample,-12,-9,[&](int x,int y){
    assert(x==-11&&y==-9);negativeBackgroundSeen=true;return uint16_t(0xf800);
  },[](int x,int y,const uint16_t*,size_t count){assert((x==-11||x==-10)&&y==-9&&count==1);}));
  assert(negativeBackgroundSeen);
  // A wider future scene asset must emit bounded chunks, never a large stack row.
  std::vector<uint8_t> wide={0,0,0,1};
  for(unsigned i=0;i<256;++i){wide.push_back(uint8_t(i));wide.push_back(0);wide.push_back(255);}
  uint32_t wideOffsets[]={0,uint32_t(wide.size())};
  Sprite width256{256,1,wideOffsets,2,wide.data(),wide.size()};
  unsigned emitted=0,calls=0;
  assert(draw(width256,-128,0,[](int,int){assert(false);return uint16_t(0);},
    [&](int x,int y,const uint16_t *pixels,size_t count){
      assert(x==int(emitted)-128&&y==0&&count<=64);++calls;
      for(size_t i=0;i<count;++i)assert(pixels[i]==emitted+i);
      emitted+=count;
    }));
  assert(calls==4&&emitted==256);
  auto rejected=[&](const Sprite &bad){
    bool called=false;
    assert(!draw(bad,0,0,[&](int,int){called=true;return uint16_t(0);},
       [&](int,int,const uint16_t*,size_t){called=true;}));assert(!called);
  };
  Sprite bad=sample;bad.width=0;rejected(bad);bad=sample;bad.width=257;rejected(bad);
  bad=sample;bad.rowOffsetCount=1;rejected(bad);bad=sample;bad.dataSize=13;rejected(bad);
  bad=sample;bad.data=nullptr;rejected(bad);bad=sample;bad.rowOffsets=nullptr;rejected(bad);
  uint32_t wrongStart[]={1,14};bad=sample;bad.rowOffsets=wrongStart;rejected(bad);
  uint32_t shortRows[]={0,3};bad=sample;bad.rowOffsets=shortRows;bad.dataSize=3;rejected(bad);
  uint8_t original=data[0];data[0]=4;rejected(sample);data[0]=original;
  data[2]=0;rejected(sample);data[2]=1;data[2]=4;rejected(sample);data[2]=1;
  data[6]=0;rejected(sample);data[6]=128;
  assert(!draw(sample,INT_MAX,0,[](int,int){return uint16_t(0);},[](int,int,const uint16_t*,size_t){}));
  // Reject invalid later rows before emitting a valid first row.
  uint32_t twoRows[]={0,7,14};Sprite truncated{3,2,twoRows,3,data,sizeof(data)};
  data[9]=0;rejected(truncated);data[9]=1;
  // Render every real asset with and without tint over a varying RGB565 backdrop.
  for(unsigned i=0;i<unsigned(Asset::Count);++i)for(bool apply:{false,true}) {
    const auto &s=descriptor(Asset(i));size_t samples=0;
    assert(draw(s,0,0,[](int x,int y){return uint16_t((x*13+y*31)&65535);},
      [&](int x,int y,const uint16_t*,size_t count){assert(x>=0&&y>=0&&x+count<=s.width&&y<s.height&&count<=64);samples+=count;},apply,0xf800));
    assert(samples>0&&samples<=size_t(s.width)*s.height);
  }
}
'''
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);(p/'test.cpp').write_text(code)
            result=subprocess.run(['clang++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I',str(ROOT/'include'),str(p/'test.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(p/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
