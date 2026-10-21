#pragma once

#include <cstdint>
#include <optional>

#include "cheats_destination.h"

namespace pinyon_shift::cheats {

// UI snapshots contain coordinates only; guest objects stay on the guest thread.
std::optional<Destination> MapDestination();
// True means queued. The title may reject it; teleport waits for its map and
// expires after ten seconds. Neither return value certifies a landing.
bool RequestGpsDestination(const Destination& point);
bool RequestTeleportDestination(const Destination& point);
void UpdateDestinations();
void GpsDestinationApplied();
void TeleportDestinationApplied();

// Native map hooks. None replaces the title's travel or streaming sequence.
// title_admitted is the predicate's own result before the trainer override.
bool AllowMapTravel(uint32_t map, bool title_enabled, bool title_admitted);
// True when a queued request was armed; the map then ignores its hovered marker.
bool PrepareMapTravelInput(uint32_t map);
// After the map update's predicate call: true when FAST TRAVEL ANYWHERE alone
// admitted the travel, so the hovered marker (one the title refused) is
// dropped for the nearest road point.
bool UseMapRoadFallback(uint32_t map, bool admitted);

}  // namespace pinyon_shift::cheats
