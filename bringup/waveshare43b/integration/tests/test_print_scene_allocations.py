"""The real shared factory makes one PSRAM-only attempt and safely falls back."""
from pathlib import Path
import json
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class PrintSceneAllocations(unittest.TestCase):
    def test_optional_cache_one_attempt_across_modes_sizes_and_failures(self):
        heap = r'''
#pragma once
#include <cstdlib>
constexpr unsigned MALLOC_CAP_SPIRAM=0x0400,MALLOC_CAP_8BIT=0x0004;
namespace fake_heap {inline bool fail=false;inline unsigned calls=0,flags=0;inline size_t bytes=0;inline void *address=nullptr;}
inline void *heap_caps_malloc(size_t bytes,unsigned flags){
 ++fake_heap::calls;fake_heap::flags=flags;fake_heap::bytes=bytes;
 return fake_heap::address=fake_heap::fail?nullptr:std::malloc(bytes);
}
'''
        code = r'''
#include <cstdint>
namespace lgfx {using rgb565_t=uint16_t;}
#include "ws43b_print_scene.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>
struct Canvas {
 int w=112,h=104;std::vector<uint16_t> pixels;unsigned writes=0;
 Canvas(int scale):w(112*scale/2),h(104*scale/2),pixels(size_t(w)*h){}
 void pushImage(int x,int y,int a,int b,const lgfx::rgb565_t *p){
  assert(p&&x>=0&&y>=0&&a>0&&b>0&&x+a<=w&&y+b<=h);
  for(int yy=0;yy<b;++yy)for(int xx=0;xx<a;++xx){
   pixels[size_t(y+yy)*w+x+xx]=p[yy*a+xx];assert(++writes<=unsigned(w*h));
  }
 }
};
int main(int argc,char **argv){
 assert(argc==2);fake_heap::fail=!strcmp(argv[1],"fail");
 auto &shared=ws43b_print_scene::sharedRenderer();
 assert(fake_heap::calls==1&&fake_heap::bytes==sizeof(ws43b_print_scene::CacheStorage));
 assert(fake_heap::flags==(MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
 assert(shared.hasCache()!=fake_heap::fail);
 ws43b_print_scene::CacheStorage storage{};ws43b_print_scene::Renderer reference(&storage);
 unsigned frames=0;
 for(int scale:{2,3,2})for(unsigned mode=0;mode<4;++mode)for(uint32_t phase:{0u,950u,3200u,8000u,14400u}){
  Canvas actual(scale),expected(scale);const auto state=ws43b_print_scene::Mode(mode);
  assert(shared.render(actual,0,0,state,50,phase,0x87e3,0x67b6,0x0062,false,scale));
  assert(reference.render(expected,0,0,state,50,phase,0x87e3,0x67b6,0x0062,false,scale));
  assert(actual.pixels==expected.pixels&&actual.writes==unsigned(actual.w*actual.h));
  assert(&shared==&ws43b_print_scene::sharedRenderer()&&fake_heap::calls==1);++frames;
 }
 printf("{\"result\":\"PASS\",\"allocation_attempts\":%u,\"cache_bytes\":%zu,\"frames\":%u}\n",fake_heap::calls,fake_heap::bytes,frames);
 std::free(fake_heap::address);
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            (path/'esp_heap_caps.h').write_text(heap)
            (path/'test.cpp').write_text(code)
            result = subprocess.run([
                'clang++', '-std=c++17', '-O1', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', '-DARDUINO', '-I', str(path),
                '-I', str(ROOT/'include'), str(path/'test.cpp'), '-o', str(path/'test'),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            for mode in ('success', 'fail'):
                with self.subTest(mode=mode):
                    result = subprocess.run([str(path/'test'), mode], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    report = json.loads(result.stdout)
                    self.assertEqual(report['result'], 'PASS')
                    self.assertEqual(report['allocation_attempts'], 1)
                    self.assertEqual(report['cache_bytes'], 60736)
                    self.assertEqual(report['frames'], 60)


if __name__ == '__main__':
    unittest.main()
