#pragma once

#include <cstdint>
#include <initializer_list>
#include <string>
#include <string_view>

#include "achievements/fh1_achievements.h"

namespace pinyon_shift::achievements {

// The achievements screen's and notifications' own words (AC-2.7) in the
// title's string-table languages: English, Japanese, German, French,
// Spanish, Italian, Korean, Traditional Chinese, Brazilian Portuguese,
// Polish, Russian, Swedish, Norwegian and Dutch, chosen by `user_language`
// as the title chooses its own (the other menu languages run the title in
// English). Achievement names and descriptions are the title's own.
enum class Text : uint16_t {
  kTitle,
  kAll,
  kCareer,
  kRacing,
  kFame,
  kExplore,
  kFestival,
  kOnline,
  kRally,
  kClub,
  kYellow,
  kGreen,
  kBlue,
  kPink,
  kOrange,
  kPurple,
  kGold,
  kAlmostThere,
  kNeedOnlineSection,
  kCountOf,
  kUnlockedCount,
  kHelpCategory,
  kHelpTrack,
  kHelpStopTracking,
  kHelpBack,
  kSortTitle,
  kSortNearest,
  kSortLockedFirst,
  kSortRecent,
  kSortValue,
  kEverythingYours,
  kBandNow,
  kNextBand,
  kNextEverything,
  kShareOffline,
  kTracked,
  kNoAchievements,
  kUnlocked,
  kUnlockedOn,
  kNeedsLive,
  kNeedsRivals,
  kLocked,
  kTrackedHint,
  kTrackHint,
  kProgressWristbands,
  kProgressSigns,
  kProgressRacers,
  kToastUnlocked,
  kToastTotal,
  kToastCategory,
  kToastCategoryDetail,
  kToastEverything,
  kToastTier,
  kToastAllOffline,
  kToastWristband,
  kToastGOf,
  kToastTracked,
  kToastProgress,
  kCount,
};

std::string_view Tr(Text text);
// `text` with {0}, {1}... replaced by `args`.
std::string Format(Text text, std::initializer_list<std::string_view> args);
// A date in the language's own form ("26 AUG 2026", "2026年8月26日", "26.08.2026").
std::string FormatDate(int year, int month, int day);
std::string_view CategoryName(Category category);
// Wristband `index` (0 Yellow to 6 Gold).
std::string_view BandName(int index);

}  // namespace pinyon_shift::achievements
