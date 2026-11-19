#include "hud_toggle.h"

#include <rex/cvar.h>
#include <rex/memory.h>
#include <rex/system/kernel_state.h>

#include "fh1_guest_address.h"
#include "pinyon_shift_diagnostics.h"
#include "vr/vr_camera.h"

// Not saved: a hidden HUD at the next start would look like a bug.
REXCVAR_DEFINE_BOOL(hud_hidden, false, "Pinyon Shift",
                    "Hide the game's HUD (minimap, speedometer, banners) for clean screenshots; "
                    "the HUD toggle key flips it")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

// Each HUD element's visibility update (sub_826BEC10) hides the element
// while the byte at 0x833023C1 is set and shows it again once the byte is
// clear. The nohud launch option is read only when an element is first
// shown, so writing it at run time changes nothing. The toggle holds the
// byte at 1 while the HUD is hidden and puts back what was there when it is
// shown again.
namespace {

constexpr uint32_t kHudHidden = FH1_ADDR(0x833023C1u);

bool g_applied = false;
uint8_t g_saved = 0;

uint8_t* HiddenByte() {
  auto* base = rex::system::kernel_state()->memory()->virtual_membase();
  return rex::memory::GuestPtr<uint8_t*>(base, kHudHidden);
}

}  // namespace

namespace pinyon_shift::hud {

void Toggle() {
  // In VR the HUD is on the headset's panel or hidden (vr_camera.h), so the
  // key turns the panel off and on for the run; the launcher's choice
  // (xr_hud_panel in the config) returns at the next start.
  if (vr::InVr()) {
    const bool shown = !REXCVAR_GET(hud_hidden) && !vr::HidesHud();
    rex::cvar::SetFlagByName("xr_hud_panel", shown ? "false" : "true");
    rex::cvar::SetFlagByName("hud_hidden", "false");
    // A config that keeps the HUD in the eyes (xr_hide_hud = false) hides
    // it the flat way.
    if (shown && !vr::HidesHud()) rex::cvar::SetFlagByName("hud_hidden", "true");
    return;
  }
  rex::cvar::SetFlagByName("hud_hidden", REXCVAR_GET(hud_hidden) ? "false" : "true");
}

void Update() {
  // VR stereo hides it as well (vr_camera.h).
  const bool hidden = REXCVAR_GET(hud_hidden) || vr::HidesHud();
  if (hidden) {
    uint8_t* byte = HiddenByte();
    if (!g_applied) g_saved = *byte;
    *byte = 1;
  } else if (g_applied) {
    *HiddenByte() = g_saved;
  }
  if (hidden != g_applied) {
    g_applied = hidden;
    diagnostics::RecordEvent("hud.toggled", {{"hidden", hidden ? "1" : "0"}});
  }
}

}  // namespace pinyon_shift::hud
