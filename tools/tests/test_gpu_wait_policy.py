"""Exercise the actual WAIT_REG_MEM polling policy with counted thread calls."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
CXX = ROOT / '.local/toolchain/llvm-20.1.8/bin/clang++.exe'


@unittest.skipUnless(CXX.is_file() and os.environ.get('INCLUDE'),
                     'Windows C++ build environment required')
class GpuWaitPolicyTests(unittest.TestCase):
    def test_short_sleeps_work_without_vsync_and_zero_preserves_polling(self):
        source = (ROOT / 'thirdparty/shiftglue-sdk/src/graphics/command_processor.cpp').read_text()
        start = source.index('        if (!REXCVAR_GET(vsync)')
        end = source.index('        rex::thread::SyncMemory();', start)
        policy = source[start:end]
        harness = r'''
#include <chrono>
#include <cassert>
bool vsync; int wait_reg_mem_sleep_us, wait_reg_mem_yield_us;
int yields; long long sleep_us; bool slept;
#define REXCVAR_GET(name) name
namespace rex::thread {
void MaybeYield() { ++yields; }
template<class Rep, class Period> void Sleep(std::chrono::duration<Rep,Period> d) {
  sleep_us = std::chrono::duration_cast<std::chrono::microseconds>(d).count();
}
}
void poll(bool sync, int duration, bool early=false) {
  vsync=sync; wait_reg_mem_sleep_us=duration; wait_reg_mem_yield_us=100;
  yields=0; sleep_us=0; slept=false; int wait=0x200;
  auto wait_start=std::chrono::steady_clock::now() -
      std::chrono::seconds(early ? -10 : 10);
POLICY
}
int main() {
  poll(false,100); assert(slept && sleep_us==100 && yields==0);
  poll(false,0); assert(!slept && sleep_us==0 && yields==1);
  poll(true,100); assert(slept && sleep_us==100 && yields==0);
  poll(true,0); assert(slept && sleep_us==2000 && yields==0);
  poll(false,100,true); assert(!slept && sleep_us==0 && yields==1);
  poll(true,100,true); assert(!slept && sleep_us==0 && yields==1);
}
'''.replace('POLICY', policy)
        with tempfile.TemporaryDirectory(prefix='pinyon-wait-policy-') as directory:
            root = Path(directory)
            cpp = root / 'policy.cpp'
            cpp.write_text(harness, encoding='utf-8')
            exe = root / 'policy.exe'
            compiled = subprocess.run([str(CXX), '-std=c++20', str(cpp), '-o', str(exe)],
                                      capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            subprocess.run([str(exe)], check=True)


if __name__ == '__main__':
    unittest.main()
