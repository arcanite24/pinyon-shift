#pragma once

#include <cstddef>
#include <cstdint>
#include <functional>
#include <optional>

#include "achievements/fh1_achievements.h"

namespace pinyon_shift::achievements {

// Progress toward locked achievements (AC-4.1), from read-only snapshots taken
// at safe points: the decrypted profile body at each load and save (the save
// hooks), and a pass over the free-roam collectibles on a host guest task.
// Nothing here writes guest memory or calls guest code. Thread safe.

struct Progress {
  uint32_t current = 0;
  uint32_t target = 0;
  float fraction() const {
    return target ? float(current < target ? current : target) / float(target) : 0.0f;
  }
};

// The save hooks' plaintext ForzaProfile body (guest thread).
void ObserveProfile(const uint8_t* body, size_t size);

// Once per title frame (the frame hook): queues the collectible count every
// couple of seconds while something shows progress.
void Update();

// Asks for a fresh collectible count at the next title frame (the screen
// opening).
void RequestRefresh();

// The progress of achievement `id`, or nullopt when it has no source or the
// source has not been read yet.
std::optional<Progress> ProgressFor(uint32_t id);

// Whether the player is in free roam, as of the latest count.
bool InFreeRoam();

// Called (on a guest thread) when a source's value changes, with the
// achievements whose progress moved; the UI posts it to its thread.
void SetChangedCallback(std::function<void(ProgressSource source, uint32_t previous,
                                           uint32_t current)> callback);

// Called (on a guest thread) when the player enters or leaves free roam, as
// of the latest count; the tracked achievement shows only there.
void SetFreeRoamCallback(std::function<void(bool free_roam)> callback);

// Keeps counting even while nothing asked for it (a tracked achievement, the
// milestone notifications).
void SetWanted(bool wanted);

}  // namespace pinyon_shift::achievements
