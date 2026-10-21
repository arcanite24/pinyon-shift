"""Exercise the actual #703/#715 hook and its generated loop continuations."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[2]
CXX = (str(ROOT / ".local/toolchain/llvm-20.1.8/bin/clang++.exe")
       if os.name == "nt" else shutil.which("clang++") or shutil.which("g++"))
AVAILABLE = bool(CXX and Path(CXX).is_file()
                 and (os.name != "nt" or os.environ.get("INCLUDE")))


class AudioChildDispatchTests(unittest.TestCase):
    def test_base_and_v4_continuations(self):
        for folder, address, continuation in (
            ("analysis", 0x82FFD9E0, 0x82FFD9F0),
            ("analysis-v4", 0x830BEB68, 0x830BEB78),
        ):
            with self.subTest(folder=folder):
                analysis = tomllib.loads((ROOT / "config/rexglue" / folder /
                                          "main-xex.toml").read_text(encoding="utf-8"))
                hooks = [h for h in analysis["midasm_hook"]
                         if h["name"] == "PinyonShiftGuardEmptyAudioChild"]
                self.assertEqual(len(hooks), 1)
                self.assertEqual(hooks[0]["address"], address)
                self.assertEqual(hooks[0]["jump_address_on_true"], continuation)
                self.assertEqual(hooks[0]["registers"], ["r3", "r28", "r30", "r31"])
                self.assertFalse(hooks[0].get("after_instruction", False))

    @unittest.skipUnless(AVAILABLE, "C++ compiler/build environment required")
    def test_empty_slot_preserves_result_and_live_slots_are_untouched(self):
        source = (ROOT / "src/pinyon_shift_runtime_hooks.cpp").read_text(encoding="utf-8")
        start = source.index("bool PinyonShiftGuardEmptyAudioChild(")
        end = source.index("// Returns true to leave sub_82F9F130", start)
        prelude = r'''
#include <atomic>
#include <cassert>
#include <cstdint>
#include <initializer_list>
#include <string>
#include <string_view>
#include <utility>
union PPCRegister { uint64_t u64; uint32_t u32; };
std::string Hex32(uint32_t value) { return std::to_string(value); }
unsigned events = 0;
namespace pinyon_shift::diagnostics {
void RecordEvent(std::string_view name,
    std::initializer_list<std::pair<std::string_view, std::string_view>>) {
  assert(name == "audio.child_dispatch.empty"); ++events;
}
}
'''
        check = r'''
int main() {
  PPCRegister child{0}, result{0}, owner{0x2E36A230}, index{0};
  // Both reports: the first counted slot is zero. No guest reads are allowed.
  assert(PinyonShiftGuardEmptyAudioChild(child, result, owner, index));
  assert(child.u64 == 0 && result.u64 == 0);
  // A hole after a child error must not turn its result into success.
  result.u64 = 37;
  assert(PinyonShiftGuardEmptyAudioChild(child, result, owner, index));
  assert(child.u64 == 37 && result.u64 == 37);
  // Every nonzero pointer, even an invalid one, keeps the protected guest path.
  for (uint64_t pointer : {1ULL, 0x40000000ULL, 0xFFFFFFFFULL}) {
    child.u64 = pointer;
    assert(!PinyonShiftGuardEmptyAudioChild(child, result, owner, index));
    assert(child.u64 == pointer && result.u64 == 37);
  }
  for (unsigned i = 0; i < 32; ++i) {
    child.u64 = 0;
    assert(PinyonShiftGuardEmptyAudioChild(child, result, owner, index));
  }
  assert(events == 16);
  assert(owner.u64 == 0x2E36A230 && index.u64 == 0);
}
'''
        with tempfile.TemporaryDirectory(prefix="pinyon-audio-child-") as tmp:
            tmp = Path(tmp)
            cpp = tmp / "probe.cpp"
            exe = tmp / ("probe.exe" if os.name == "nt" else "probe")
            cpp.write_text(prelude + source[start:end] + check, encoding="utf-8")
            compiled = subprocess.run([str(CXX), "-std=c++23", str(cpp), "-o", str(exe)],
                                      capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            result = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
