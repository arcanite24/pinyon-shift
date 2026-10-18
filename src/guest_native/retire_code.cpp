// Retire the guest code bytes after load (NEAR_NATIVE_RESEARCH NN-6.7).
//
// The executable's code section (14.7 MB, 0x823E0000-0x831EF59C; v4
// 0x82410000-0x832BA19C) is translated ahead of time. After load two things
// still read it: the guest_native replacements, to check their guest code
// before first use, and the generated code's switch dispatch, which loads its
// jump-table entries (421 tables in the base image) from the code section.
// With pinyon_shift_retire_guest_code at 1 the replacement checks run at once
// and every page without a jump table becomes no-access, so any later read or
// write faults (the trial); at 2 those pages are also freed.

#include <algorithm>
#include <cstdint>
#include <string>

#include <rex/ppc/func.h>

#include <rex/cvar.h>
#include <rex/system/xmemory.h>

#include "fh1_guest_address.h"
#include "guest_native/guest_native.h"
#include "guest_native/retire_code.h"
#include "pinyon_shift_diagnostics.h"

REXCVAR_DEFINE_UINT32(pinyon_shift_retire_guest_code, 0, "Pinyon Shift",
                      "After load, take all access from the game's translated code bytes "
                      "(1, a trial: a later access faults) and free their pages (2) (NN-6.7)")
    .range(0, 2)
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

[[gnu::weak]] const PPCFoldedRange PPCJumpTableRanges[] = {{0, 0}};

namespace pinyon_shift::guest_native {

void RetireGuestCode(rex::memory::Memory* memory) {
  const uint32_t mode = REXCVAR_GET(pinyon_shift_retire_guest_code);
  if (!mode || !memory || !PPCJumpTableRanges[0].size) return;
  const uint32_t code_base = pinyon_shift::fh1::kTitleUpdateV4 ? 0x82410000u : 0x823E0000u;
  const uint32_t code_size = pinyon_shift::fh1::kTitleUpdateV4 ? 0xEAA19Cu : 0xE0F59Cu;
  const size_t matched = CheckAllGuestCode(memory->virtual_membase());
  // Retire the gaps between jump tables (sorted by address); the memory call
  // aligns each gap inward to whole host pages, so table pages stay readable.
  const uint32_t code_end = code_base + code_size;
  uint32_t at = code_base;
  uint32_t gaps = 0, retired = 0, failed = 0, tables = 0;
  uint64_t retired_bytes = 0;
  auto retire = [&](uint32_t begin, uint32_t end) {
    if (end <= begin) return;
    ++gaps;
    const uint32_t first = (begin + 0xFFFu) & ~0xFFFu, last = end & ~0xFFFu;
    if (memory->RetireImageRange(begin, end - begin, mode >= 2)) {
      ++retired;
      retired_bytes += last > first ? last - first : 0;
    } else if (last > first) {
      ++failed;
    }
  };
  for (const PPCFoldedRange* table = PPCJumpTableRanges; table->size != 0; ++table) {
    if (table->guest + table->size <= code_base || table->guest >= code_end) continue;
    ++tables;
    retire(at, table->guest);
    at = std::max(at, table->guest + table->size);
  }
  retire(at, code_end);
  diagnostics::RecordEvent("guest_code.retired",
                           {{"mode", std::to_string(mode)},
                            {"jump_tables", std::to_string(tables)},
                            {"ranges", std::to_string(retired)},
                            {"failed", std::to_string(failed)},
                            {"bytes", std::to_string(retired_bytes)},
                            {"code_bytes", std::to_string(code_size)},
                            {"replacements_checked", std::to_string(matched)}});
}

}  // namespace pinyon_shift::guest_native
