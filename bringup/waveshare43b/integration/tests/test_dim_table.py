"""The table-based dimming used while presenting equals dimRgb565() exactly."""

from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]

HARNESS = r'''
#include <cassert>
#include <initializer_list>
#include "ws43b_frame_copy.h"
int main(){
 for(unsigned percent:{0u,1u,10u,30u,33u,50u,67u,99u,100u}){
  const ws43b::DimTable dim(percent);
  for(uint32_t pixel=0;pixel<=0xFFFF;++pixel)
   assert(dim(uint16_t(pixel))==ws43b::dimRgb565(uint16_t(pixel),percent));
 }
 // The copy still applies it to both pixels of every 32-bit word.
 alignas(4) uint8_t src[8]={0xFF,0xFF,0x00,0xF8,0x1F,0x00,0xE0,0x07},dst[8]={};uint32_t scratch[2];
 assert(ws43b::copyFrameChecked(dst,src,scratch,sizeof scratch,8,1,50));
 const uint16_t *in=reinterpret_cast<const uint16_t*>(src),*out=reinterpret_cast<const uint16_t*>(dst);
 for(int i=0;i<4;++i)assert(out[i]==ws43b::dimRgb565(in[i],50));
 return 0;
}
'''


class DimTable(unittest.TestCase):
    def test_table_matches_formula(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'dim.cpp'
            src.write_text(HARNESS)
            exe = Path(tmp) / 'dim'
            subprocess.run(
                [
                    'clang++',
                    '-std=c++17',
                    '-O2',
                    '-Wall',
                    '-Wextra',
                    '-Werror',
                    '-I',
                    str(ROOT / 'src'),
                    str(src),
                    '-o',
                    str(exe),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run([str(exe)], check=True)


if __name__ == '__main__':
    unittest.main()
