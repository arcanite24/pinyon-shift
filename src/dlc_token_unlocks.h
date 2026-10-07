#pragma once

#include <cstddef>
#include <cstdint>

namespace pinyon_shift::dlc {

// Token-store unlocks kept in the profile itself. Called with each decrypted
// secure file as it loads; edits only the ForzaProfile body, and only to
// grant: turning a setting off never takes an unlock away.
void GrantProfileUnlocks(uint8_t* body, size_t size);

// Called once per title frame: on the v4 build, queues the free-roam grant of
// Fast Travel Anywhere into the live profile (once per loaded profile).
void UpdateTokenUnlocks();

}  // namespace pinyon_shift::dlc
