#include <atomic>
#include <cstdint>
#include <string>

#include <rex/cvar.h>

#include "pinyon_shift_diagnostics.h"

REXCVAR_DEFINE_BOOL(
    pinyon_shift_native_renderer_census, false, "Pinyon Shift",
    "Record bounded native-renderer census frame markers without changing rendering");

namespace {

constexpr uint64_t kFrameSummaryInterval = 300;
std::atomic<uint64_t> g_frame_sequence{};

}  // namespace

// This translation unit is the single owner for title-side graphics hooks.
// The hook runs immediately before FH1's sole VdSwap import and intentionally
// accepts no PPC registers: it cannot mutate guest arguments or control flow.
// All renderer experiments remain passive until their own explicit cvars are
// enabled and must dispatch through this owner.
void PinyonShiftObserveGraphicsFrame() {
  if (!REXCVAR_GET(pinyon_shift_native_renderer_census)) {
    return;
  }

  const uint64_t frame_sequence =
      g_frame_sequence.fetch_add(1, std::memory_order_relaxed) + 1;
  if (frame_sequence != 1 && frame_sequence % kFrameSummaryInterval != 0) {
    return;
  }

  const std::string frame = std::to_string(frame_sequence);
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.census.frame",
      {{"frame_sequence", frame},
       {"guest_address", "829EFEB8"},
       {"mode", "pass_through"}});
}
