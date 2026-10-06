"""Compile the actual opt-in child ownership probe with checked memory stubs."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[2]
CXX = os.environ.get("PINYON_CHILD_DISPATCH_TEST_CXX") or (str(ROOT / ".local/toolchain/llvm-20.1.8/bin/clang++.exe") if os.name == "nt" else shutil.which("clang++") or shutil.which("g++"))
AVAILABLE = bool(CXX and Path(CXX).is_file() and (os.name != "nt" or os.environ.get("INCLUDE")))

PRELUDE = r"""#include <cstdint>
#include <string>
#include <string_view>
#include <vector>
#include <map>
#include <cassert>
#include <cstdio>
#include <utility>
#include <initializer_list>
union PPCRegister { uint64_t u64; uint32_t u32; };
bool enabled=false; int reads=0;
std::map<uint32_t,uint32_t> words;
bool PinyonShiftGuestRangeReadable(uint32_t a,uint32_t size) { return size==4 && words.contains(a); }
uint32_t LoadGuestU32(uint32_t a) { ++reads; assert(words.contains(a)); return words.at(a); }
std::string Hex32(uint32_t a) { char b[9]; std::snprintf(b,9,"%08X",a); return b; }
namespace pinyon_shift::platform { bool EnvironmentFlag(const char*) { return enabled; } }
std::vector<std::map<std::string,std::string>> events;
namespace pinyon_shift::diagnostics {
void RecordEvent(std::string_view name,std::initializer_list<std::pair<std::string_view,std::string_view>> fields) {
 assert(name=="object.child_dispatch.parent_return"); std::map<std::string,std::string> e; for(auto f:fields)e.emplace(f.first,f.second);events.push_back(e);
}
}
"""

CHECK = r"""
int main(int argc,char**) {
 enabled=argc>1;
 PPCRegister parent{0x400000}, target{0x82C22000}, result{1};
 words={{0x400040,0x500000},{0x500000,0x82008000},{0x600040,0x700000},{0x700000,0x82009000}};
 PinyonShiftTraceChildDispatchBefore(parent,target);
 if(!enabled) {PinyonShiftTraceChildDispatchAfter(result,parent);assert(reads==0&&events.empty()&&g_child_dispatch_snapshots.empty());return 0;}
 PPCRegister nested{0x600000}; PinyonShiftTraceChildDispatchBefore(nested,target);
 PinyonShiftTraceChildDispatchAfter(result,nested);
 words[0x500000]=0x04D0487C;
 PinyonShiftTraceChildDispatchAfter(result,parent);
 assert(events.size()==2&&events[0]["parent"]=="00600000"&&events[1]["parent"]=="00400000");
 assert(events[1]["vtable_before"]=="82008000"&&events[1]["vtable_after"]=="04D0487C");
 assert(events[1]["child_before"]=="00500000"&&events[1]["child_after"]=="00500000");
 assert(parent.u64==0x400000&&target.u64==0x82C22000&&result.u64==1&&nested.u64==0x600000);
 assert(g_child_dispatch_snapshots.empty());
 PinyonShiftTraceChildDispatchAfter(result,parent);assert(events.size()==2);
 PPCRegister invalid{0xFFFFFFF0}; PinyonShiftTraceChildDispatchBefore(invalid,target);PinyonShiftTraceChildDispatchAfter(result,invalid);
 assert(events.back()["child_before"]=="unreadable"&&events.back()["vtable_after"]=="unreadable");
 words.erase(0x500000);PinyonShiftTraceChildDispatchBefore(parent,target);PinyonShiftTraceChildDispatchAfter(result,parent);assert(events.back()["vtable_before"]=="unreadable");
 assert(g_child_dispatch_snapshots.empty());
}
"""

@unittest.skipUnless(AVAILABLE, "C++ compiler/build environment required")
class ChildDispatchTraceTests(unittest.TestCase):
    def test_read_only_pairing_and_disabled_path(self):
        source = (ROOT / "src/pinyon_shift_runtime_hooks.cpp").read_text(encoding="utf-8")
        start = source.index("// Read-only ownership probe for the shared child dispatch")
        end = source.index("static std::string PinyonShiftReadGuestAscii(", start)
        hooks = tomllib.loads((ROOT / "config/rexglue/analysis/main-xex.toml").read_text(encoding="utf-8"))["midasm_hook"]
        for name, address, registers in [("Before", 0x82C222EC, ["r3", "r11"]), ("After", 0x82C222F0, ["r3", "r30"])]:
            matches = [h for h in hooks if h["name"] == "PinyonShiftTraceChildDispatch" + name]
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0]["address"], address)
            self.assertEqual(matches[0]["registers"], registers)
            self.assertFalse(matches[0].get("after_instruction", False))
        with tempfile.TemporaryDirectory(prefix="pinyon-child-dispatch-") as directory:
            directory = Path(directory)
            cpp = directory / "probe.cpp"
            exe = directory / ("probe.exe" if os.name == "nt" else "probe")
            cpp.write_text(PRELUDE + source[start:end] + CHECK, encoding="utf-8")
            compiled = subprocess.run([str(CXX), "-std=c++23", str(cpp), "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            for args in ([], ["enabled"]):
                with self.subTest(args=args):
                    result = subprocess.run([str(exe), *args], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

if __name__ == "__main__":
    unittest.main()
