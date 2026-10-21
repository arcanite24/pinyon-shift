#pragma once

// Windows HDR for the game's display while the game runs (WINDOWS HDR in
// DISPLAY settings): turned on before the swapchain is made, and back off
// when the game closes. Only displays the game turned on are turned off
// again; one the player already had in HDR is left alone. Other hosts have
// no system HDR switch and report kUnsupported.

#include <filesystem>
#include <optional>

namespace pinyon_shift::platform {

enum class DisplayHdrResult {
  kTurnedOn,     // It was off; the game turned it on and owns it now.
  kAlreadyOn,    // HDR was on already (by the player, or by this game).
  kUnsupported,  // The display (or the host) has no HDR mode.
  kFailed,       // Windows refused the change.
};

const char* DisplayHdrResultName(DisplayHdrResult result);

// Where the displays the game turned on are listed while they are on, so a
// crash or a killed process is undone at the next launch. Reads that list
// back: its displays count as the game's again. Call before the others.
void SetDisplayHdrRestoreFile(std::filesystem::path path);

// Turns HDR on for the display showing `native_window`, or, without one, the
// display holding the desktop point (x, y).
DisplayHdrResult TurnOnDisplayHdr(void* native_window);
DisplayHdrResult TurnOnDisplayHdrAt(int x, int y);

// Turns off every display the game turned on and clears the restore file.
// Safe to call more than once and from any thread, a crash handler included.
// Returns how many displays it turned off.
int RestoreDisplayHdr();

}  // namespace pinyon_shift::platform
