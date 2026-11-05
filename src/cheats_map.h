#pragma once

#include <cstdint>
#include <optional>

namespace pinyon_shift::cheats {

// Map markers for the hidden collectibles (NP-8.6): whether the map should
// show every discount sign and barn find (cheat_show_collectibles, with
// cheats on).
bool ShowCollectibles();

// Called once per title frame (frame.tick, before the guest tasks run): while
// the cheat is on, queues a pass that puts the not-yet-found collectibles'
// markers on the title's map and minimap, and one that takes them off again
// when it is turned off.
void UpdateCollectibleMarkers();

// A read-only count of the free-roam collectibles for the achievements
// screen (AC-4.1); nullopt while the world's activities are not loaded. It
// reads guest memory only and works with cheats off. Guest tasks only.
struct CollectibleCount {
  uint32_t discount_signs = 0, discount_signs_found = 0;
  uint32_t barn_finds = 0, barn_finds_found = 0;
  bool free_roam = false;
};
std::optional<CollectibleCount> CountCollectibles();

}  // namespace pinyon_shift::cheats
