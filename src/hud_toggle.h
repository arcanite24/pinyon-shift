#pragma once

namespace pinyon_shift::hud {

// Flips the hud_hidden setting (the HUD toggle key, #519); in VR, the
// headset's HUD panel (xr_hud_panel) instead.
void Toggle();
// Applies hud_hidden to the title's own nohud launch option when it changed;
// at frame.tick, on the title's main thread. Writes nothing until the player
// toggles the HUD.
void Update();

}  // namespace pinyon_shift::hud
