"""Exercise the real C++ scene under sanitizers, including incremental pixels."""
from pathlib import Path
import json
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[4]
HARNESS=ROOT/'bringup/waveshare43b/integration/visual-v2/preview_native.cpp'

class NativeScene(unittest.TestCase):
    def test_partial_matches_fresh_at_phase_boundaries_and_material_colors(self):
        with tempfile.TemporaryDirectory() as temporary:
            binary=Path(temporary)/'native-scene'
            result=subprocess.run(['clang++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I',str(ROOT/'include'),str(HARNESS),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary),'--verify'],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            data=json.loads(result.stdout)
            self.assertEqual(data['result'],'PASS')
            self.assertEqual(data['partial_full_comparisons'],4410)
            self.assertGreater(data['partial_frames'],4000)
            self.assertEqual(data['position_checks'],727301)
            self.assertGreater(data['material_difference_pixels'],1000)
            self.assertGreater(data['top_pixel_checks'],10000)
            self.assertGreater(data['dither_cells'],300)
            self.assertEqual(data['gradient_comparisons'],288)
            self.assertEqual(data['head_sample_checks'],42*55)
            self.assertEqual(data['cache_fallback_comparisons'],4410)
            self.assertEqual(data['noop_frames'],4)
            self.assertEqual(data['head_cache_bytes'],9240)

    def test_production_allocations_are_one_attempt_psram_only_with_safe_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            # Compile the actual ARDUINO hero wrapper against a heap fault stub.
            # Each process starts with fresh function-static allocations.
            (directory/'esp_heap_caps.h').write_text('''#pragma once
#include <cstdlib>
#include <vector>
constexpr unsigned MALLOC_CAP_SPIRAM=0x0400,MALLOC_CAP_8BIT=0x0004;
namespace fake_heap {
struct Request {size_t bytes;unsigned flags;void *address;};
inline unsigned failAt=0;
inline std::vector<Request> requests;
}
inline void *heap_caps_malloc(size_t bytes,unsigned flags) {
  void *address=fake_heap::requests.size()+1==fake_heap::failAt?nullptr:std::malloc(bytes);
  fake_heap::requests.push_back({bytes,flags,address});return address;
}
''')
            binary=directory/'native-allocations'
            result=subprocess.run(['clang++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-DARDUINO','-DWS43B_TEST_ALLOCATIONS',
                '-I',str(directory),'-I',str(ROOT/'include'),str(HARNESS),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            for mode,attempts in [('cache',2),('fallback',2),('missing',1)]:
                with self.subTest(mode=mode):
                    result=subprocess.run([str(binary),'--verify-allocation',mode],capture_output=True,text=True,timeout=15)
                    self.assertEqual(result.returncode,0,result.stderr)
                    data=json.loads(result.stdout)
                    self.assertEqual(data['result'],'PASS')
                    self.assertEqual(data['allocation_attempts'],attempts)
                    self.assertEqual(data['frames'],146)

if __name__=='__main__':unittest.main()
