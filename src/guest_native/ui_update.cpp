// User interface update at a lower rate (#1071 P3).
//
// The simulation thread updates the user interface once a frame through
// CUserInterface4's update slot (base sub_82E71F90, v4 sub_82F339E0;
// slot 48 in the base vtable, 51 in v4). It takes the frame time in f1 and
// walks the scene manager, the custom controls (the minimap renderer and
// its symbol layers, the HUD stackers) and the HUD. Profiles put it at
// about 40 % of the simulation thread outside physics, on the desktop, the
// Deck and the Odin.
//
// pinyon_shift_ui_update_interval N > 1 runs that update on one frame in N
// and skips the others, passing the skipped frames' time to the next update
// so animations and timers keep their speed. The HUD then moves at 1/N of
// the frame rate.
//
// The custom renderer controls (CCustomRendererCtrl slot 20, base
// sub_827DAA40, v4 sub_8288D9C0; the minimap is one) submit their drawing
// every frame from inside the update, and a frame without that submission
// shows garbage where the minimap goes. The submission reads only the
// control's own fields, so on skipped frames each control seen in the last
// full update is submitted again on its own.
//
// Measured with in-run A/B on fh1-race-sustained: one frame in two took
// 0.46 and 0.70 ms of CPU a frame off the simulation thread on the Steam
// Deck LCD (2026-11-13), so it is the default on Linux; on the Odin 2
// Portal (v4) the change was within noise (-0.16 +- 1.06 ms) and Android
// and the other platforms keep every frame. SETTINGS > GRAPHICS > HUD
// UPDATES sets it.

#include <array>
#include <cstdint>

#include <rex/cvar.h>
#include <rex/platform.h>
#include <rex/ppc/context.h>
#include <rex/ppc/func.h>

#include "fh1_guest_address.h"
#include "guest_native/guest_native.h"

REXCVAR_DEFINE_UINT32(pinyon_shift_ui_update_interval,
                      REX_PLATFORM_LINUX && !REX_PLATFORM_ANDROID ? 2 : 1, "Pinyon Shift",
                      "Run the user interface update on one frame in N, carrying the "
                      "skipped frames' time; custom renderer controls such as the minimap "
                      "still draw every frame (#1071; 1 = every frame)")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

#if defined(PINYON_SHIFT_TITLE_UPDATE_V4) && PINYON_SHIFT_TITLE_UPDATE_V4
extern "C" REX_FUNC(__imp__sub_8288D9C0);
#define PINYON_CUSTOM_RENDERER_SUBMIT __imp__sub_8288D9C0
#else
extern "C" REX_FUNC(__imp__sub_827DAA40);
#define PINYON_CUSTOM_RENDERER_SUBMIT __imp__sub_827DAA40
#endif

namespace pinyon_shift::guest_native {
namespace {

constexpr bool kV4 = pinyon_shift::fh1::kTitleUpdateV4;

uint32_t Interval() { return REXCVAR_GET(pinyon_shift_ui_update_interval); }
bool Enabled() { return Interval() > 1; }

// Only the simulation thread runs the update and the controls' submissions.
constexpr size_t kMaxControls = 16;
struct State {
  uint32_t ui_object = 0;
  uint32_t skipped = 0;
  double carried = 0.0;
  // Controls submitted during the last full update, and the one running.
  std::array<uint32_t, kMaxControls> controls{};
  size_t control_count = 0;
  std::array<uint32_t, kMaxControls> recording{};
  size_t recording_count = 0;
  bool recording_open = false;
};
State state;

void CloseRecording() {
  if (!state.recording_open) return;
  state.recording_open = false;
  state.controls = state.recording;
  state.control_count = state.recording_count;
}

bool UiUpdateNative(PPCContext& ctx, uint8_t* base) {
  CloseRecording();
  if (ctx.r3.u32 != state.ui_object) {
    state = State{};
    state.ui_object = ctx.r3.u32;
  }
  if (state.control_count != 0 && state.skipped + 1 < Interval()) {
    ++state.skipped;
    state.carried += ctx.f1.f64;
    for (size_t i = 0; i < state.control_count; ++i) {
      PPCContext call = ctx;
      call.r3.u64 = state.controls[i];
      PINYON_CUSTOM_RENDERER_SUBMIT(call, base);
    }
    return true;  // the rest of the update waits for the next full frame
  }
  // A full update with the summed time; it records the custom renderers.
  ctx.f1.f64 += state.carried;
  state.skipped = 0;
  state.carried = 0.0;
  state.recording_count = 0;
  state.recording_open = true;
  return false;
}

bool CustomRendererNative(PPCContext& ctx, uint8_t* /*base*/) {
  if (state.recording_open && state.recording_count < kMaxControls) {
    const uint32_t control = ctx.r3.u32;
    bool seen = false;
    for (size_t i = 0; i < state.recording_count; ++i) seen |= state.recording[i] == control;
    if (!seen) state.recording[state.recording_count++] = control;
  }
  return false;  // the original submits
}

Replacement ui_update_replacement = {
    .name = "ui.update_interval",
    .guest_address = kV4 ? 0x82F339E0u : 0x82E71F90u,
    .guest_code_size = 600,
    .guest_code_fnv1a = kV4 ? 0x5499AF7A40111290ull : 0xAB8CF47AA2608B06ull,
    .returns = kReturnNone,
    .enabled = Enabled,
    .native = UiUpdateNative,
    .written = nullptr,
};

Replacement custom_renderer_replacement = {
    .name = "ui.custom_renderer_submit",
    .guest_address = kV4 ? 0x8288D9C0u : 0x827DAA40u,
    .guest_code_size = 120,
    .guest_code_fnv1a = kV4 ? 0x44E26E5ACB2F9309ull : 0xDF155EEDEFAB4D59ull,
    .returns = kReturnNone,
    .enabled = Enabled,
    .native = CustomRendererNative,
    .written = nullptr,
};

}  // namespace
}  // namespace pinyon_shift::guest_native

PINYON_GUEST_NATIVE(82E71F90, 82F339E0, ::pinyon_shift::guest_native::ui_update_replacement)
PINYON_GUEST_NATIVE(827DAA40, 8288D9C0, ::pinyon_shift::guest_native::custom_renderer_replacement)
