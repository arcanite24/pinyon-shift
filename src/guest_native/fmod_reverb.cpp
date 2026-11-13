// FMOD reverb off (#1071 P5).
//
// FMOD Ex's SFX reverb unit reads its input through a DSP read callback
// (base sub_82FBE908, v4 sub_8307F9B8; r3 the unit, r4 the input, r5 the
// output, r6 the sample count, r7 the channel count). When the unit's
// channel mask leaves the input's channels out, the callback copies the
// input to the output, which is FMOD's own bypass; otherwise it runs the
// reverb (sub_8300D580), about a fifth of FMOD's mixer thread. The world
// reverb is computed whatever its levels in the track's reverb XML (see
// the audio page).
//
// pinyon_shift_fmod_reverb=false always takes the copy: the mix keeps its
// dry signal and loses the room reverb.

#include <cstdint>
#include <cstring>

#include <rex/cvar.h>
#include <rex/ppc/context.h>
#include <rex/ppc/func.h>
#include <rex/system/xmemory.h>

#include "fh1_guest_address.h"
#include "guest_native/guest_native.h"

REXCVAR_DEFINE_BOOL(pinyon_shift_fmod_reverb, true, "Pinyon Shift",
                    "Run FMOD's room reverb; false passes the sound through it unchanged, "
                    "which saves about a fifth of the audio mixer's CPU (#1071)")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

namespace pinyon_shift::guest_native {
namespace {

constexpr bool kV4 = pinyon_shift::fh1::kTitleUpdateV4;

bool Enabled() { return !REXCVAR_GET(pinyon_shift_fmod_reverb); }

uint8_t* Host(uint8_t* base, uint32_t address) {
  return base + address + rex::memory::detail::PhysicalHostOffset(address);
}

bool ReverbBypass(PPCContext& ctx, uint8_t* base) {
  const uint32_t input = ctx.r4.u32, output = ctx.r5.u32;
  const uint32_t bytes = ctx.r6.u32 * ctx.r7.u32 * 4;
  if (input == 0 || output == 0 || bytes == 0 || bytes > 1u << 20) {
    return false;  // the original handles it
  }
  if (input != output) std::memmove(Host(base, output), Host(base, input), bytes);
  ctx.r3.u64 = 0;
  return true;
}

Replacement reverb_replacement = {
    .name = "fmod.reverb_bypass",
    .guest_address = kV4 ? 0x8307F9B8u : 0x82FBE908u,
    .guest_code_size = 196,
    .guest_code_fnv1a = kV4 ? 0x5B298CBD2E9096CDull : 0x7C7B2D2AB00A6F71ull,
    .returns = kReturnR3,
    .enabled = Enabled,
    .native = ReverbBypass,
    .written = nullptr,
};

}  // namespace
}  // namespace pinyon_shift::guest_native

PINYON_GUEST_NATIVE(82FBE908, 8307F9B8, ::pinyon_shift::guest_native::reverb_replacement)
