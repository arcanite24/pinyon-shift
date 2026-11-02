#include "achievements/fh1_achievements.h"

#include <algorithm>
#include <array>

#include "ui/hostui/painter.h"

namespace pinyon_shift::achievements {
namespace {

using enum Category;
using A = Availability;
using P = ProgressSource;

// AC-0.1 and AC-0.2: every achievement the base XEX, v4 and the 1000 Club
// spa.bin define (163 is unused). Progress targets come from the
// achievements' own descriptions.
constexpr AchievementMeta kAchievements[] = {
    {155, kCareer},
    {156, kFestival},
    {157, kCareer},
    {158, kCareer},
    {159, kRacing},
    {160, kRacing},
    {161, kRacing},
    {162, kRacing, A::kAvailable, P::kRaceEncounters, 10},
    {164, kExplore},
    {165, kRacing, A::kNeedsRivals},
    {166, kFestival},
    {167, kFestival},
    {168, kFestival, A::kNeedsOnline},
    {169, kFestival},
    {170, kFame},
    {171, kFame},
    {172, kFame},
    {173, kFame},
    {174, kFame},
    {175, kCareer, A::kAvailable, P::kWristbands, 1},
    {176, kCareer, A::kAvailable, P::kWristbands, 2},
    {177, kCareer, A::kAvailable, P::kWristbands, 3},
    {178, kCareer, A::kAvailable, P::kWristbands, 4},
    {179, kCareer, A::kAvailable, P::kWristbands, 5},
    {180, kCareer, A::kAvailable, P::kWristbands, 6},
    {181, kCareer, A::kAvailable, P::kWristbands, 7},
    {182, kCareer},
    {183, kRacing},
    {184, kRacing},
    {185, kRacing},
    {186, kRacing},
    {187, kRacing},
    {188, kRacing},
    {189, kFame},
    {190, kFame},
    {191, kFame},
    {192, kExplore},
    {193, kExplore, A::kAvailable, P::kDiscountSigns, 10},
    {194, kExplore, A::kAvailable, P::kDiscountSigns, 100},
    {195, kExplore},
    {196, kOnline, A::kNeedsOnline},
    {197, kOnline, A::kNeedsOnline},
    {198, kOnline, A::kNeedsOnline},
    {199, kOnline, A::kNeedsOnline},
    {200, kOnline, A::kNeedsOnline},
    {201, kOnline, A::kNeedsOnline},
    {202, kOnline, A::kNeedsOnline},
    {203, kOnline, A::kNeedsOnline},
    {204, kOnline, A::kNeedsOnline},
    {205, kOnline, A::kNeedsOnline},
    {206, kRally},
    {207, kRally},
    {208, kRally},
    {209, kRally},
    {210, kRally},
    {211, kRally},
    {212, kRally, A::kNeedsRivals},
    {213, kRally, A::kNeedsOnline},
    {214, kRally},
    {215, kRally},
    {216, kClub},
    {217, kClub},
    {218, kClub},
    {219, kClub},
    {220, kClub},
    {221, kClub},
    {222, kClub},
    {223, kClub},
    {224, kClub},
    {225, kClub},
};

constexpr std::array<std::string_view, size_t(kCount)> kCategoryLabels = {
    "CAREER", "RACING", "FAME", "EXPLORE", "FESTIVAL", "ONLINE", "RALLY", "1000 CLUB",
};

using hostui::Rgba;
constexpr Wristband kWristbands[] = {
    {"YELLOW", "Wristbands/YellowXl.xds", Rgba(255, 222, 0)},
    {"GREEN", "Wristbands/GreenXl.xds", Rgba(90, 210, 40)},
    {"BLUE", "Wristbands/BlueXl.xds", Rgba(30, 150, 255)},
    {"PINK", "Wristbands/PinkXl.xds", Rgba(255, 40, 170)},
    {"ORANGE", "Wristbands/OrangeXl.xds", Rgba(255, 110, 20)},
    {"PURPLE", "Wristbands/PurpleXl.xds", Rgba(150, 70, 230)},
    {"GOLD", "Wristbands/GoldXl.xds", Rgba(240, 190, 70)},
};

// Shares of the offline gamerscore at which each band starts; the last
// entry is everything.
constexpr float kTierThresholds[] = {0.05f, 0.15f, 0.30f, 0.45f, 0.60f, 0.75f, 0.90f, 1.0f};

}  // namespace

std::string_view CategoryLabel(Category category) {
  return size_t(category) < kCategoryLabels.size() ? kCategoryLabels[size_t(category)] : "";
}

std::span<const AchievementMeta> AllAchievementMeta() { return kAchievements; }

std::optional<AchievementMeta> FindAchievementMeta(uint32_t id) {
  for (const auto& meta : kAchievements) {
    if (meta.id == id) return meta;
  }
  return std::nullopt;
}

std::span<const Wristband> Wristbands() { return kWristbands; }

std::string_view StickerFor(uint32_t gamerscore) {
  return gamerscore >= 30   ? "Icons/TicketStickerGold.xds"
         : gamerscore >= 15 ? "Icons/TicketStickerSilver.xds"
                            : "Icons/TicketStickerBronze.xds";
}

int CompletionTier(uint32_t earned, uint32_t available) {
  if (available == 0) return -1;
  if (earned >= available) return 7;
  const float share = float(earned) / float(available);
  int tier = -1;
  for (int i = 0; i < 7; ++i) {
    if (share >= kTierThresholds[i]) tier = i;
  }
  return tier;
}

float TierThreshold(int tier) { return kTierThresholds[std::clamp(tier, 0, 7)]; }

}  // namespace pinyon_shift::achievements
