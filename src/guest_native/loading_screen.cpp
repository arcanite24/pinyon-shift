// The loading screen's minimum time on screen (docs/CONSOLE_ERA_RESEARCH.md,
// "Loading screen minimum time").
//
// When the title shows its tip loading screen ("PLEASE WAIT" with a tip), the
// renderer's show method (base sub_825A2CB8, v4 sub_8261A100) sets a deadline
// at renderer +2088: the render stopwatch plus a minimum time on screen
// (float +2072; 1 s from the title screen to free roam, 3 s into an event).
// The main thread's load step yields until the render frame clears that
// deadline (-1.0), so a load that finishes early still waits it out. On a disc
// the load took longer than the minimum anyway; from a modern drive it is
// pure waiting: 1.0 s of the 1.56 s title-to-free-roam load and 2.9 s of the
// 4.6 s car-select-to-race load on multivac.
//
// With pinyon_shift_loading_screen_minimum off (the default), this wrapper
// runs the title's show method and then clears the deadline, as the render
// frame would once it passed. The loading screen still appears and fades as
// before; it leaves when loading is done.

#include <cstdint>

#include <rex/cvar.h>
#include <rex/memory.h>
#include <rex/ppc/context.h>
#include <rex/ppc/func.h>

#include "fh1_guest_address.h"
#include "guest_native/guest_native.h"

REXCVAR_DEFINE_BOOL(pinyon_shift_loading_screen_minimum, false, "Pinyon Shift",
                    "Keep the console's minimum time on screen for loading screens (1 s from "
                    "the title, 3 s into events) even when loading finished sooner")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

extern "C" REX_FUNC(PINYON_GUEST_NATIVE_JOIN(__imp__sub_, PINYON_GUEST_NATIVE_PICK(825A2CB8,
                                                                                  8261A100)));

namespace pinyon_shift::guest_native {
namespace {

constexpr uint32_t kDeadlineOffset = 2088;
// -1.0 as a double: the render frame's "no deadline" value.
constexpr uint64_t kNoDeadline = 0xBFF0000000000000ull;

bool SkipMinimum() { return !REXCVAR_GET(pinyon_shift_loading_screen_minimum); }

bool ShowWithoutMinimum(PPCContext& ctx, uint8_t* base) {
  const uint32_t renderer = ctx.r3.u32;
  PINYON_GUEST_NATIVE_JOIN(__imp__sub_, PINYON_GUEST_NATIVE_PICK(825A2CB8, 8261A100))(ctx, base);
  *rex::memory::GuestPtr<rex::be_u64*>(base, renderer + kDeadlineOffset) = kNoDeadline;
  return true;
}

Replacement show_replacement = {
    .name = "render.loading_screen_minimum",
    .guest_address = pinyon_shift::fh1::kTitleUpdateV4 ? 0x8261A100u : 0x825A2CB8u,
    .guest_code_size = 132,
    .guest_code_fnv1a =
        pinyon_shift::fh1::kTitleUpdateV4 ? 0x7C862F9DA1C4E754ull : 0x5A8E7E38487214B2ull,
    .returns = kReturnNone,
    .enabled = SkipMinimum,
    .native = ShowWithoutMinimum,
    .written = nullptr,
};

}  // namespace
}  // namespace pinyon_shift::guest_native

PINYON_GUEST_NATIVE(825A2CB8, 8261A100, ::pinyon_shift::guest_native::show_replacement)
