// Title waits that spin (#431).
//
// The render thread's frame function (sub_8259F3E8, v4 sub_826164D0) returns
// early when the simulation has no new frame for it, after rebuilding the
// gamma ramp, reading the time and calling SleepEx(0, TRUE) (the wrapper
// sub_82A6D7D8, v4 sub_82B2A848). The host returns from a zero alertable sleep
// at once, so while the render thread waits for the simulation it runs that
// path back to back: on the Odin it then retired six times the instructions
// of a run without the wait, mostly clock reads, guest memcpy and the gamma
// path. With pinyon_shift_render_idle_sleep_us above zero (200 by default), a
// sleep from that call site first waits that long on a host timer (Windows'
// own alertable SleepEx cannot sleep under a millisecond), then runs the
// original, which delivers any APC that arrived meanwhile, so the title's
// view of the call is unchanged. In-run A/B on the Odin (fh1-race-sustained, 30 fps limit):
// the render thread's CPU fell from 477-839 to 242-253 ms a second, other
// threads unchanged, and frames over 40 ms from 8-13 to 3-4 a run.
//
// The same call site tells the simulation step gate that the render thread is
// waiting for a step (PinyonShiftNoteRenderIdle), with or without the sleep.
//
// The replacement never handles a call itself: it always returns false, so
// guest_native.summary counts every call of the wrapper as declined.

#include <chrono>
#include <rex/cs_scheduler.h>
#include <cstdint>

#include <rex/cvar.h>
#include <rex/ppc/context.h>
#include <rex/perf/counter.h>
#include <rex/thread.h>
#include <rex/types.h>

#include "fh1_guest_address.h"
#include "guest_native/guest_native.h"
#include "pinyon_shift_runtime_hooks.h"

REXCVAR_DEFINE_UINT32(pinyon_shift_render_idle_sleep_us, 200, "Pinyon Shift",
                      "Microseconds the render thread sleeps when it has no new frame to "
                      "draw, instead of yielding and polling again (#431; 0 = the title's own "
                      "spin)")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DECLARE(bool, pinyon_shift_step_count_drawn);

namespace pinyon_shift::guest_native {
namespace {

// Return address of the render frame's idle SleepEx(0, TRUE).
constexpr uint32_t kRenderIdleReturn =
    pinyon_shift::fh1::kTitleUpdateV4 ? 0x82616CD4u : 0x8259FBECu;

bool SleepIdle(PPCContext& ctx, uint8_t* base) {
  if (ctx.r3.u32 != 0 || static_cast<uint32_t>(ctx.lr) != kRenderIdleReturn) return false;
  // The frame function idles when the newest step the simulation started
  // (r22, from the queue at r31 + 2520) is no newer than the one it last drew
  // (r31 + 2380), or is not finished yet (0x8259F83C); r22 and r31 are
  // callee-saved, so still the function's here. (Base game offsets; v4's
  // frame function is not mapped.)
  if (!pinyon_shift::fh1::kTitleUpdateV4) {
    if (rex::perf::CriticalPathTraceEnabled()) {
      const uint32_t drawn =
          rex::byte_swap(*reinterpret_cast<const uint32_t*>(base + ctx.r31.u32 + 2380));
      rex::perf::TraceCriticalPath("render_idle", 0, int64_t(ctx.r22.u32), int64_t(drawn));
    }
    PinyonShiftNoteRenderIdle(ctx.r31.u32, ctx.r22.u32);
  }
  const uint32_t sleep_us = REXCVAR_GET(pinyon_shift_render_idle_sleep_us);
  if (sleep_us) {
    if (rex::cs_scheduler::InActor()) rex::cs_scheduler::Sleep(uint64_t(sleep_us)*1000);
    else rex::thread::WaitUntil(std::chrono::steady_clock::now() + std::chrono::microseconds(sleep_us));
  }
  return false;
}

// Also without the sleep when the step gate counts the drawn step: it needs to
// see the render thread wait.
bool SleepEnabled() {
  return REXCVAR_GET(pinyon_shift_render_idle_sleep_us) != 0 ||
         REXCVAR_GET(pinyon_shift_step_count_drawn);
}

Replacement sleep_replacement = {
    .name = "title.sleep_ex",
    .guest_address = pinyon_shift::fh1::kTitleUpdateV4 ? 0x82B2A848u : 0x82A6D7D8u,
    .guest_code_size = 56,
    .guest_code_fnv1a = 0x55426CA58921F8BEull,
    .returns = kReturnR3,
    .enabled = SleepEnabled,
    .native = SleepIdle,
    .written = nullptr,
};

}  // namespace
}  // namespace pinyon_shift::guest_native

PINYON_GUEST_NATIVE(82A6D7D8, 82B2A848, ::pinyon_shift::guest_native::sleep_replacement)
