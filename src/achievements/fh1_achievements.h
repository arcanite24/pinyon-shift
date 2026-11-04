#pragma once

#include <cstdint>
#include <optional>
#include <span>
#include <string_view>

#include "ui/hostui/painter.h"

namespace pinyon_shift::achievements {

// Our own grouping of FH1's 70 achievements (base 155-205, Rally 206-215,
// 1000 Club 216-225) for the achievements screen (AC-0.1). Names and
// descriptions stay the title's own (its XDBF and the package spa.bin);
// this table holds only IDs and our classification.
enum class Category : uint8_t {
  kCareer,    // the festival: arrival, wristbands, the championship
  kRacing,    // race wins and series
  kFame,      // popularity, PR stunts, sponsorships
  kExplore,   // the world: collectibles, roads, speed traps
  kFestival,  // the festival's places and services: Autoshow, paint, store
  kOnline,
  kRally,
  kClub,      // 1000 Club
  kCount,
};

// Short tab label, upper case.
std::string_view CategoryLabel(Category category);

// Whether an achievement can be earned offline in this port. Online play
// (Xbox LIVE) and the Rivals ghosts are gone; until there is a local
// replacement these cannot be unlocked here.
enum class Availability : uint8_t {
  kAvailable,
  kNeedsOnline,  // LIVE races, Playground games, online levels, Storefront
  kNeedsRivals,  // Rivals mode's online ghosts
};

// Where a locked achievement's progress comes from (AC-0.2). Only sources
// with a known meaning are listed; every other achievement shows no bar.
enum class ProgressSource : uint8_t {
  kNone,
  kWristbands,      // wristbands received, from the profile's Main/WristbandLevel
  kDiscountSigns,   // discount signs found
  kRaceEncounters,  // festival racers beaten after challenging them
};

struct AchievementMeta {
  uint32_t id = 0;
  Category category = Category::kCareer;
  Availability availability = Availability::kAvailable;
  ProgressSource progress = ProgressSource::kNone;
  uint32_t target = 0;  // the progress value that unlocks it
};

// The table, in the title's order; nullopt for an ID it does not list.
std::span<const AchievementMeta> AllAchievementMeta();
std::optional<AchievementMeta> FindAchievementMeta(uint32_t id);

// The festival's wristbands in the order the title awards them, numbered 1
// to 7 on the bands themselves (Wristbands/*.xds), then Platinum.
struct Wristband {
  std::string_view name;      // upper case
  std::string_view texture;   // Horizon.zip member, the large art
  uint32_t colour;            // RGBA for accents
};
// The band inside each large wristband texture (512x256), measured on the
// disc's art, and its width over its height.
inline constexpr hostui::UvRect kWristbandUv = {0.098f, 0.172f, 0.818f, 0.797f};
inline constexpr float kWristbandAspect = 2.30f;
std::span<const Wristband> Wristbands();
// The trophy sticker (Horizon.zip) for an achievement's gamerscore.
std::string_view StickerFor(uint32_t gamerscore);
// Completion tier from the share of the gamerscore that can be earned
// offline: -1 below the first band, 0 (Yellow) to 6 (Gold), 7 when
// everything that can be earned is.
int CompletionTier(uint32_t earned, uint32_t available);
// The gamerscore share (0 to 1) at which `tier` starts.
float TierThreshold(int tier);

}  // namespace pinyon_shift::achievements
