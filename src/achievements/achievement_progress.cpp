#include "achievements/achievement_progress.h"

#include <atomic>
#include <iterator>
#include <mutex>
#include <string>

#include <fmt/format.h>

#include "cheats_map.h"
#include "mod/mod_host.h"
#include "pinyon_shift_diagnostics.h"
#include "save/profile_body.h"

namespace pinyon_shift::achievements {
namespace {

// The profile's Main/WristbandLevel counts from 0 for the first (Yellow) band:
// a save holding Yellow and Green (175, 176) reads 1. Received bands are one
// more.
constexpr uint32_t kWristbandLevelOffset = 1;

struct Snapshot {
  std::optional<uint32_t> wristbands;
  std::optional<uint32_t> discount_signs;        // from the collectibles
  std::optional<uint32_t> upgrade_discount;      // Main/UpgradeDiscount, 1 % a sign
  std::optional<uint32_t> race_encounters;       // Main/NumRaceEncountersWon
  bool free_roam = false;
};

std::mutex g_mutex;
Snapshot g_snapshot;
std::function<void(ProgressSource, uint32_t, uint32_t)> g_changed;
std::function<void(bool)> g_free_roam_changed;
std::atomic<bool> g_refresh{false};
std::atomic<bool> g_wanted{false};
std::atomic<bool> g_count_queued{false};

std::optional<uint32_t> Value(const Snapshot& snapshot, ProgressSource source) {
  switch (source) {
    case ProgressSource::kWristbands:
      return snapshot.wristbands;
    case ProgressSource::kDiscountSigns:
      // The live count while the world is loaded, else the saved discount.
      return snapshot.discount_signs ? snapshot.discount_signs : snapshot.upgrade_discount;
    case ProgressSource::kRaceEncounters:
      return snapshot.race_encounters;
    case ProgressSource::kNone:
      break;
  }
  return std::nullopt;
}

// Applies `update` to the snapshot and reports each source whose value moved.
template <typename Update>
void Change(Update&& update) {
  constexpr ProgressSource kSources[] = {ProgressSource::kWristbands,
                                         ProgressSource::kDiscountSigns,
                                         ProgressSource::kRaceEncounters};
  struct Moved {
    ProgressSource source;
    uint32_t previous, current;
  };
  Moved moved[std::size(kSources)];
  size_t count = 0;
  std::function<void(ProgressSource, uint32_t, uint32_t)> changed;
  {
    std::lock_guard lock(g_mutex);
    const Snapshot before = g_snapshot;
    update(g_snapshot);
    for (ProgressSource source : kSources) {
      const auto previous = Value(before, source);
      const auto current = Value(g_snapshot, source);
      if (current && current != previous) {
        moved[count++] = {source, previous.value_or(0), *current};
      }
    }
    changed = g_changed;
  }
  for (size_t i = 0; i < count; ++i) {
    diagnostics::RecordEvent(
        "achievements.progress",
        {{"source", moved[i].source == ProgressSource::kWristbands       ? "wristbands"
                    : moved[i].source == ProgressSource::kDiscountSigns ? "discount_signs"
                                                                         : "race_encounters"},
         {"previous", std::to_string(moved[i].previous)},
         {"value", std::to_string(moved[i].current)}});
    if (changed) changed(moved[i].source, moved[i].previous, moved[i].current);
  }
}

void CountOnGuestTask() {
  const auto count = cheats::CountCollectibles();
  g_count_queued.store(false);
  const bool free_roam = count && count->free_roam;
  // Logged when it changes: compared with Main/UpgradeDiscount in the
  // achievements.profile event.
  static uint32_t logged_signs = UINT32_MAX, logged_total = UINT32_MAX;
  if (count && (count->discount_signs_found != logged_signs ||
                count->discount_signs != logged_total)) {
    logged_signs = count->discount_signs_found;
    logged_total = count->discount_signs;
    diagnostics::RecordEvent("achievements.census",
                             {{"discount_signs", std::to_string(count->discount_signs)},
                              {"discount_signs_found", std::to_string(logged_signs)},
                              {"barn_finds", std::to_string(count->barn_finds)},
                              {"barn_finds_found", std::to_string(count->barn_finds_found)},
                              {"free_roam", free_roam ? "1" : "0"}});
  }
  bool was_free_roam = false;
  Change([&](Snapshot& snapshot) {
    was_free_roam = snapshot.free_roam;
    snapshot.free_roam = free_roam;
    if (count) snapshot.discount_signs = count->discount_signs_found;
  });
  if (free_roam != was_free_roam) {
    std::function<void(bool)> callback;
    {
      std::lock_guard lock(g_mutex);
      callback = g_free_roam_changed;
    }
    if (callback) callback(free_roam);
  }
}

}  // namespace

void ObserveProfile(const uint8_t* body, size_t size) {
  // Only a career profile has these fields; option-only bodies leave the
  // snapshot alone.
  const auto level = save::ReadProfileU32(body, size, "Main/WristbandLevel");
  if (!level) return;
  const auto discount = save::ReadProfileU32(body, size, "Main/UpgradeDiscount");
  const auto encounters = save::ReadProfileU32(body, size, "Main/NumRaceEncountersWon");
  const auto other_encounters = save::ReadProfileU32(body, size, "Main/NumEncountersWon");
  diagnostics::RecordEvent(
      "achievements.profile",
      {{"wristband_level", std::to_string(*level)},
       {"upgrade_discount", discount ? std::to_string(*discount) : ""},
       {"race_encounters_won", encounters ? std::to_string(*encounters) : ""},
       {"encounters_won", other_encounters ? std::to_string(*other_encounters) : ""}});
  Change([&](Snapshot& snapshot) {
    snapshot.wristbands = *level + kWristbandLevelOffset;
    if (discount) snapshot.upgrade_discount = *discount;
    if (encounters) snapshot.race_encounters = *encounters;
  });
}

void Update() {
  // Every two seconds at 60 frames a second, while anything shows progress.
  static uint32_t frames = 0;
  const bool requested = g_refresh.exchange(false);
  if (!requested && (!g_wanted.load(std::memory_order_relaxed) || ++frames < 120)) return;
  frames = 0;
  if (g_count_queued.exchange(true)) return;
  mod::EnqueueHostGuestTask(CountOnGuestTask);
}

void RequestRefresh() { g_refresh.store(true); }

void SetWanted(bool wanted) { g_wanted.store(wanted); }

std::optional<Progress> ProgressFor(uint32_t id) {
  const auto meta = FindAchievementMeta(id);
  if (!meta || meta->progress == ProgressSource::kNone || meta->target == 0) return std::nullopt;
  std::lock_guard lock(g_mutex);
  const auto value = Value(g_snapshot, meta->progress);
  if (!value) return std::nullopt;
  return Progress{*value, meta->target};
}

void SetFreeRoamCallback(std::function<void(bool free_roam)> callback) {
  std::lock_guard lock(g_mutex);
  g_free_roam_changed = std::move(callback);
}

bool InFreeRoam() {
  std::lock_guard lock(g_mutex);
  return g_snapshot.free_roam;
}

void SetChangedCallback(
    std::function<void(ProgressSource source, uint32_t previous, uint32_t current)> callback) {
  std::lock_guard lock(g_mutex);
  g_changed = std::move(callback);
}

}  // namespace pinyon_shift::achievements
