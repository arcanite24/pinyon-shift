#include "ui/achievements_menu.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cctype>
#include <cmath>
#include <fstream>
#include <sstream>
#include <string>
#include <system_error>
#include <vector>

#include <rex/system/achievement_manager.h>

#include "achievements/achievement_progress.h"
#include "achievements/achievement_strings.h"
#include "achievements/fh1_achievements.h"
#include "pinyon_shift_diagnostics.h"
#include "ui/achievement_icons.h"
#include "ui/hostui/glyph_atlas.h"
#include "ui/hostui/menu.h"
#include "ui/hostui/painter.h"

namespace pinyon_shift::ui {
namespace {

using achievements::AchievementMeta;
using achievements::Availability;
using achievements::Category;
using achievements::kWristbandAspect;
using achievements::kWristbandUv;
using achievements::Format;
using achievements::StickerFor;
using achievements::Text;
using achievements::Tr;
using achievements::Progress;
using achievements::ProgressSource;
using hostui::Fade;
using hostui::Font;
using hostui::HelpButton;
using hostui::HelpEntry;
using hostui::MenuScreen;
using hostui::NavCommand;
using hostui::Painter;
using hostui::Rgba;
using hostui::TextureMode;
using hostui::UvRect;

constexpr uint32_t kWhite = Rgba(255, 255, 255);
constexpr uint32_t kDimWhite = Rgba(255, 255, 255, 200);
constexpr uint32_t kFaint = Rgba(255, 255, 255, 110);
constexpr uint32_t kMagenta = Rgba(230, 0, 126);
constexpr uint32_t kGold = Rgba(255, 190, 70);
constexpr uint32_t kOrange = Rgba(255, 106, 19);

// Layout in title pixels (1280x720, inside the 90 % safe area).
constexpr float kLeft = 112.0f;
constexpr float kRight = 1196.0f;
constexpr float kTile = 100.0f;
constexpr float kTileGap = 12.0f;
constexpr float kTilePitch = kTile + kTileGap;
constexpr int kColumns = 5;
constexpr float kGridTop = 232.0f;
constexpr float kGridBottom = 638.0f;
constexpr float kSectionLabel = 30.0f;
constexpr float kPanelLeft = 688.0f;

// Texture regions measured on the disc's art (AC-0.3).
constexpr UvRect kSelectionUv = {0.21f, 0.12f, 0.79f, 0.87f};
constexpr UvRect kStatBarUv = {0.0f, 0.28f, 1.0f, 0.69f};
constexpr UvRect kNewUv = {0.047f, 0.375f, 0.953f, 0.625f};

constexpr int kTabTarget = 1000;

float EaseOut(float t) {
  t = std::clamp(t, 0.0f, 1.0f);
  return 1.0f - (1.0f - t) * (1.0f - t) * (1.0f - t);
}

std::string Upper(std::string_view text) { return hostui::UpperCase(text); }

// Some of the title's strings hold Windows-1252 punctuation (an ellipsis in
// 196 and 197) where UTF-8 is expected; the fonts would skip it.
std::string CleanText(std::string_view text) {
  std::string clean;
  for (size_t i = 0; i < text.size();) {
    const auto byte = static_cast<unsigned char>(text[i]);
    size_t length = byte < 0x80 ? 1 : (byte >> 5) == 0x6 ? 2 : (byte >> 4) == 0xE ? 3
                                    : (byte >> 3) == 0x1E ? 4 : 0;
    bool valid = length != 0 && i + length <= text.size();
    for (size_t k = 1; valid && k < length; ++k) {
      valid = (static_cast<unsigned char>(text[i + k]) & 0xC0) == 0x80;
    }
    if (valid) {
      clean.append(text.substr(i, length));
      i += length;
      continue;
    }
    switch (byte) {
      case 0x85: clean += "..."; break;
      case 0x91: case 0x92: clean += '\''; break;
      case 0x93: case 0x94: clean += '"'; break;
      case 0x96: case 0x97: clean += '-'; break;
      default: break;
    }
    ++i;
  }
  return clean;
}

// The unlock date in the player's language from a FILETIME (100 ns since
// 1601), or empty.
std::string FormatDate(uint64_t filetime) {
  if (filetime == 0) return {};
  constexpr int64_t kUnixEpoch = 11644473600;
  const int64_t seconds = int64_t(filetime / 10000000) - kUnixEpoch;
  if (seconds <= 0) return {};
  const std::chrono::sys_days days{
      std::chrono::floor<std::chrono::days>(std::chrono::sys_seconds{std::chrono::seconds{seconds}})};
  const std::chrono::year_month_day date{days};
  return achievements::FormatDate(int(date.year()), int(unsigned(date.month())),
                                  int(unsigned(date.day())));
}

std::string_view SourceLabel(ProgressSource source) {
  switch (source) {
    case ProgressSource::kWristbands: return Tr(Text::kProgressWristbands);
    case ProgressSource::kDiscountSigns: return Tr(Text::kProgressSigns);
    case ProgressSource::kRaceEncounters: return Tr(Text::kProgressRacers);
    case ProgressSource::kNone: break;
  }
  return {};
}

enum class Sort { kDefault, kNearest, kLockedFirst, kRecent, kValue, kCount };
constexpr std::array<std::string_view, size_t(Sort::kCount)> kSortLabels = {
    "SORT: TITLE ORDER", "SORT: NEAREST", "SORT: LOCKED FIRST", "SORT: RECENT", "SORT: VALUE"};
// The same, shown in the player's language (the events keep English).
constexpr std::array<Text, size_t(Sort::kCount)> kSortTexts = {
    Text::kSortTitle, Text::kSortNearest, Text::kSortLockedFirst, Text::kSortRecent,
    Text::kSortValue};

struct Item {
  rex::system::AchievementInfo info;
  AchievementMeta meta;
  std::string name;  // upper case, cleaned
  std::string description;
  bool unlocked = false;
  uint64_t unlock_time = 0;
  std::optional<Progress> progress;  // locked only, consistent with the lock

  bool available() const { return unlocked || meta.availability == Availability::kAvailable; }
};

struct Cell {
  size_t item = 0;
  float x = 0.0f, y = 0.0f;  // in the grid's scrolled content
};

struct Section {
  std::string label;
  float label_y = 0.0f;
};

class AchievementsScreen {
 public:
  AchievementsScreen(const rex::system::AchievementManager& manager, AchievementIcons* icons,
                     AchievementUiState& state)
      : manager_(manager), icons_(icons), state_(state) {
    state_.Prime(manager_);
    achievements::RequestRefresh();
    Refresh();
    Layout();
  }

  void Paint(Painter& painter);
  MenuScreen::Result Command(NavCommand command);
  bool Pointer(int target, MenuScreen::Pointer pointer);
  void Scroll(int steps) { Move(0, steps); }
  std::vector<HelpEntry> Help() const;

 private:
  void Refresh();
  void Layout();
  void Move(int dx, int dy);
  void Focus(size_t cell);
  void EnsureVisible();
  const Item* Focused() const {
    return cells_.empty() ? nullptr : &items_[cells_[std::min(focus_, cells_.size() - 1)].item];
  }
  bool Trackable(const Item& item) const { return !item.unlocked && item.available(); }

  void PaintHeader(Painter& painter, float intro);
  void PaintTabs(Painter& painter);
  void PaintGrid(Painter& painter);
  void PaintTile(Painter& painter, const Item& item, float x, float y, bool focused, float appear);
  void PaintDetail(Painter& painter);
  void PaintBar(Painter& painter, float x, float y, float width, float height, float fraction,
                uint32_t fill, uint32_t track);

  const rex::system::AchievementManager& manager_;
  AchievementIcons* icons_;
  AchievementUiState& state_;

  std::vector<Item> items_;
  std::vector<Category> tabs_;  // categories that have achievements; ALL first (kCount)
  size_t tab_ = 0;
  Sort sort_ = Sort::kDefault;
  std::vector<Section> sections_;
  std::vector<Cell> cells_;
  float content_height_ = 0.0f;
  size_t focus_ = 0;
  float scroll_ = 0.0f, scroll_target_ = 0.0f;
  float now_ = 0.0f, last_paint_ = 0.0f, last_refresh_ = 0.0f;
  float layout_at_ = 0.0f, focus_at_ = 0.0f;

  uint32_t earned_ = 0, total_ = 0, available_ = 0;
  size_t unlocked_count_ = 0;
};

void AchievementsScreen::Refresh() {
  const uint32_t focused_id = Focused() ? Focused()->info.id : 0;
  items_.clear();
  earned_ = total_ = available_ = 0;
  unlocked_count_ = 0;
  for (auto& info : manager_.ListAchievements()) {
    Item item;
    item.meta = achievements::FindAchievementMeta(info.id).value_or(AchievementMeta{info.id});
    item.unlocked = manager_.IsUnlocked(info.id);
    item.unlock_time = item.unlocked ? manager_.GetUnlockTime(info.id) : 0;
    item.name = Upper(CleanText(info.label));
    item.description = CleanText(!item.unlocked && !info.unachieved_description.empty()
                                     ? info.unachieved_description
                                     : info.description);
    if (!item.unlocked && item.available()) {
      // A value at or past the target on a locked achievement contradicts
      // the lock: the source is wrong for this save, so no bar.
      item.progress = achievements::ProgressFor(info.id);
      if (item.progress && item.progress->current >= item.progress->target) {
        item.progress.reset();
      }
    }
    total_ += info.gamerscore;
    if (item.available()) available_ += info.gamerscore;
    if (item.unlocked) {
      earned_ += info.gamerscore;
      ++unlocked_count_;
    }
    item.info = std::move(info);
    items_.push_back(std::move(item));
  }
  tabs_.assign(1, Category::kCount);
  for (size_t c = 0; c < size_t(Category::kCount); ++c) {
    if (std::any_of(items_.begin(), items_.end(),
                    [c](const Item& item) { return item.meta.category == Category(c); })) {
      tabs_.push_back(Category(c));
    }
  }
  tab_ = std::min(tab_, tabs_.size() - 1);
  if (focused_id) {
    // Keep the focus on the same achievement across a refresh.
    Layout();
    for (size_t i = 0; i < cells_.size(); ++i) {
      if (items_[cells_[i].item].info.id == focused_id) {
        focus_ = i;
        break;
      }
    }
  }
}

void AchievementsScreen::Layout() {
  const Category tab = tabs_[tab_];
  std::vector<size_t> order(items_.size());
  for (size_t i = 0; i < order.size(); ++i) order[i] = i;
  const auto nearness = [this](size_t i) {
    const Item& item = items_[i];
    if (item.unlocked) return -2.0f;
    if (!item.available()) return -3.0f;
    return item.progress ? item.progress->fraction() : -1.0f;
  };
  switch (sort_) {
    case Sort::kDefault:
      break;
    case Sort::kNearest:
      std::stable_sort(order.begin(), order.end(),
                       [&](size_t a, size_t b) { return nearness(a) > nearness(b); });
      break;
    case Sort::kLockedFirst:
      std::stable_sort(order.begin(), order.end(), [&](size_t a, size_t b) {
        return !items_[a].unlocked && items_[b].unlocked;
      });
      break;
    case Sort::kRecent:
      std::stable_sort(order.begin(), order.end(), [&](size_t a, size_t b) {
        return items_[a].unlock_time > items_[b].unlock_time;
      });
      break;
    case Sort::kValue:
      std::stable_sort(order.begin(), order.end(), [&](size_t a, size_t b) {
        return items_[a].info.gamerscore > items_[b].info.gamerscore;
      });
      break;
    case Sort::kCount:
      break;
  }

  sections_.clear();
  cells_.clear();
  float y = 0.0f;
  const auto add_section = [&](std::string label, const std::vector<size_t>& members) {
    if (members.empty()) return;
    sections_.push_back({std::move(label), y});
    y += kSectionLabel;
    for (size_t i = 0; i < members.size(); ++i) {
      cells_.push_back({members[i], float(i % kColumns) * kTilePitch,
                        y + float(i / kColumns) * kTilePitch});
    }
    y += float((members.size() + kColumns - 1) / kColumns) * kTilePitch + 8.0f;
  };
  if (tab == Category::kCount) {
    // ALL: the nearest locked achievements first, then everything that can
    // be earned, then what needs the closed online services.
    std::vector<size_t> nearest;
    for (size_t i = 0; i < items_.size(); ++i) {
      if (items_[i].progress && items_[i].progress->current > 0) nearest.push_back(i);
    }
    std::stable_sort(nearest.begin(), nearest.end(), [&](size_t a, size_t b) {
      return items_[a].progress->fraction() > items_[b].progress->fraction();
    });
    if (nearest.size() > 3) nearest.resize(3);
    std::vector<size_t> offline, online;
    for (size_t i : order) (items_[i].available() ? offline : online).push_back(i);
    add_section(std::string(Tr(Text::kAlmostThere)), nearest);
    add_section(std::string(Tr(Text::kTitle)), offline);
    add_section(std::string(Tr(Text::kNeedOnlineSection)), online);
  } else {
    std::vector<size_t> members, unavailable;
    for (size_t i : order) {
      if (items_[i].meta.category != tab) continue;
      (items_[i].available() ? members : unavailable).push_back(i);
    }
    const size_t done = std::count_if(members.begin(), members.end(),
                                      [&](size_t i) { return items_[i].unlocked; });
    add_section(std::string(achievements::CategoryName(tab)) + "  " +
                    Format(Text::kCountOf, {std::to_string(done),
                                            std::to_string(members.size() + unavailable.size())}),
                members);
    add_section(std::string(Tr(Text::kNeedOnlineSection)), unavailable);
  }
  content_height_ = y;
  focus_ = std::min(focus_, cells_.empty() ? size_t(0) : cells_.size() - 1);
}

void AchievementsScreen::Focus(size_t cell) {
  if (cell >= cells_.size()) return;
  if (cell != focus_) focus_at_ = now_;
  focus_ = cell;
  const Item& item = items_[cells_[cell].item];
  if (item.unlocked && state_.IsNew(item.info.id)) state_.MarkSeen(item.info.id);
  EnsureVisible();
}

void AchievementsScreen::EnsureVisible() {
  if (cells_.empty()) return;
  const float viewport = kGridBottom - kGridTop;
  const Cell& cell = cells_[focus_];
  // Room above the focused row for a section label.
  if (cell.y - kSectionLabel < scroll_target_) scroll_target_ = cell.y - kSectionLabel;
  if (cell.y + kTile + 6.0f > scroll_target_ + viewport) {
    scroll_target_ = cell.y + kTile + 6.0f - viewport;
  }
  scroll_target_ = std::clamp(scroll_target_, 0.0f, std::max(0.0f, content_height_ - viewport));
}

void AchievementsScreen::Move(int dx, int dy) {
  if (cells_.empty()) return;
  const Cell& from = cells_[focus_];
  if (dx != 0) {
    // Along the row only.
    const size_t next = focus_ + size_t(dx);
    if (next < cells_.size() && cells_[next].y == from.y) Focus(next);
    return;
  }
  // The nearest cell in the next row up or down, by column.
  size_t best = cells_.size();
  float best_row = 0.0f;
  for (size_t i = 0; i < cells_.size(); ++i) {
    const float row = cells_[i].y;
    if (dy > 0 ? row <= from.y : row >= from.y) continue;
    if (best == cells_.size() || (dy > 0 ? row < best_row : row > best_row)) {
      best = i;
      best_row = row;
    }
  }
  if (best == cells_.size()) return;
  size_t pick = best;
  for (size_t i = 0; i < cells_.size(); ++i) {
    if (cells_[i].y == best_row && std::abs(cells_[i].x - from.x) < std::abs(cells_[pick].x - from.x)) {
      pick = i;
    }
  }
  Focus(pick);
}

MenuScreen::Result AchievementsScreen::Command(NavCommand command) {
  switch (command) {
    case NavCommand::kUp: Move(0, -1); return MenuScreen::Result::kChanged;
    case NavCommand::kDown: Move(0, 1); return MenuScreen::Result::kChanged;
    case NavCommand::kLeft: Move(-1, 0); return MenuScreen::Result::kChanged;
    case NavCommand::kRight: Move(1, 0); return MenuScreen::Result::kChanged;
    case NavCommand::kPrevTab:
    case NavCommand::kNextTab: {
      const size_t count = tabs_.size();
      tab_ = command == NavCommand::kNextTab ? (tab_ + 1) % count : (tab_ + count - 1) % count;
      focus_ = 0;
      scroll_ = scroll_target_ = 0.0f;
      layout_at_ = now_;
      Layout();
      Focus(0);
      diagnostics::RecordEvent("achievements.tab",
                               {{"tab", tabs_[tab_] == Category::kCount
                                            ? std::string_view("ALL")
                                            : achievements::CategoryLabel(tabs_[tab_])}});
      return MenuScreen::Result::kChanged;
    }
    case NavCommand::kAuxX: {
      const uint32_t focused_id = Focused() ? Focused()->info.id : 0;
      sort_ = Sort((size_t(sort_) + 1) % size_t(Sort::kCount));
      Layout();
      for (size_t i = 0; i < cells_.size(); ++i) {
        if (items_[cells_[i].item].info.id == focused_id) {
          focus_ = i;
          break;
        }
      }
      layout_at_ = now_;
      EnsureVisible();
      diagnostics::RecordEvent("achievements.sort", {{"sort", kSortLabels[size_t(sort_)]}});
      return MenuScreen::Result::kChanged;
    }
    case NavCommand::kAuxY: {
      const Item* item = Focused();
      if (!item || !Trackable(*item)) return MenuScreen::Result::kNone;
      const bool tracked = state_.tracked() == item->info.id;
      state_.SetTracked(tracked ? std::nullopt : std::optional<uint32_t>(item->info.id));
      diagnostics::RecordEvent("achievements.track", {{"id", std::to_string(item->info.id)},
                                                      {"tracked", tracked ? "0" : "1"}});
      return MenuScreen::Result::kChanged;
    }
    case NavCommand::kAccept:
      return MenuScreen::Result::kNone;
    default:
      return MenuScreen::Result::kNone;
  }
}

bool AchievementsScreen::Pointer(int target, MenuScreen::Pointer pointer) {
  if (target >= kTabTarget) {
    if (pointer != MenuScreen::Pointer::kClick) return false;
    const size_t tab = size_t(target - kTabTarget);
    if (tab >= tabs_.size() || tab == tab_) return false;
    tab_ = tab;
    focus_ = 0;
    scroll_ = scroll_target_ = 0.0f;
    layout_at_ = now_;
    Layout();
    Focus(0);
    return true;
  }
  if (target < 0 || size_t(target) >= cells_.size() || size_t(target) == focus_) return false;
  Focus(size_t(target));
  return true;
}

std::vector<HelpEntry> AchievementsScreen::Help() const {
  std::vector<HelpEntry> help = {{HelpButton::kLB, ""},
                                 {HelpButton::kRB, std::string(Tr(Text::kHelpCategory))},
                                 {HelpButton::kX, std::string(Tr(kSortTexts[size_t(sort_)]))}};
  if (const Item* item = Focused(); item && Trackable(*item)) {
    help.push_back({HelpButton::kY, std::string(Tr(state_.tracked() == item->info.id
                                                       ? Text::kHelpStopTracking
                                                       : Text::kHelpTrack))});
  }
  help.push_back({HelpButton::kB, std::string(Tr(Text::kHelpBack))});
  return help;
}

void AchievementsScreen::PaintBar(Painter& painter, float x, float y, float width, float height,
                                  float fraction, uint32_t fill, uint32_t track) {
  rex::ui::ImmediateTexture* empty = painter.Texture("DirtTextures/StatBarEmpty.xds", TextureMode::kMask);
  rex::ui::ImmediateTexture* full = painter.Texture("DirtTextures/StatBarFill.xds", TextureMode::kMask);
  painter.Rect(x, y, width, height, track, empty, 0.0f, kStatBarUv);
  fraction = std::clamp(fraction, 0.0f, 1.0f);
  if (fraction > 0.0f) {
    painter.Rect(x, y, width * fraction, height, fill, full, 0.0f,
                 {0.0f, kStatBarUv.v0, fraction, kStatBarUv.v1});
  }
}

void AchievementsScreen::PaintHeader(Painter& painter, float intro) {
  painter.Text(Font::kDisplay, 56.0f, Tr(Text::kTitle), kLeft - 16.0f, 98.0f, kWhite);

  // Gamerscore, counting up as the screen opens.
  const uint32_t shown = uint32_t(std::lround(float(earned_) * intro));
  const std::string total = " / " + std::to_string(total_) + " G";
  const float total_width = painter.Measure(Font::kLabel, 26.0f, total);
  painter.Text(Font::kLabel, 26.0f, total, kRight, 92.0f, kDimWhite, 1.0f);
  const float score_width =
      painter.Text(Font::kDisplay, 50.0f, std::to_string(shown), kRight - total_width - 4.0f, 92.0f,
                   kGold, 1.0f);
  painter.Text(Font::kLabel, 18.0f,
               Format(Text::kUnlockedCount,
                      {std::to_string(unlocked_count_), std::to_string(items_.size())}),
               kRight, 118.0f, kFaint, 1.0f);

  // The completion wristband, left of the score.
  const auto bands = achievements::Wristbands();
  const int tier = achievements::CompletionTier(earned_, available_);
  const float band_height = 64.0f, band_width = band_height * kWristbandAspect;
  const float band_x = kRight - total_width - score_width - 40.0f - band_width;
  const auto& band = bands[size_t(std::clamp(tier, 0, int(bands.size()) - 1))];
  if (rex::ui::ImmediateTexture* art = painter.Texture(band.texture)) {
    const float lift = (1.0f - EaseOut((painter.seconds() - 0.1f) / 0.5f)) * 24.0f;
    painter.Rect(band_x, 46.0f - lift, band_width, band_height,
                 Fade(kWhite, tier < 0 ? 0.25f * intro : intro), art, 0.0f, kWristbandUv);
    if (tier == 7) {
      if (rex::ui::ImmediateTexture* crown = painter.Texture("Wristbands/HeadlineEvent.xds")) {
        painter.Rect(band_x - 58.0f, 48.0f, 56.0f, 56.0f, Fade(kWhite, intro), crown);
      }
    }
  }

  // The bar over the offline gamerscore, with each band's start marked in
  // its colour.
  const float bar_y = 132.0f, bar_width = kRight - kLeft;
  const float share = available_ ? float(earned_) / float(available_) : 0.0f;
  const uint32_t tier_colour = tier >= 0 ? band.colour : kMagenta;
  PaintBar(painter, kLeft, bar_y, bar_width, 14.0f, share * intro, tier_colour,
           Rgba(255, 255, 255, 40));
  for (int t = 0; t < 7; ++t) {
    const float x = kLeft + bar_width * achievements::TierThreshold(t);
    painter.Rect(x - 1.0f, bar_y - 4.0f, 3.0f, 22.0f, Fade(bands[size_t(t)].colour, t <= tier ? 1.0f : 0.45f));
  }
  // One sheen pass along the bar after it fills.
  if (rex::ui::ImmediateTexture* sheen = painter.Texture("Specular/SPEC_sheen.xds", TextureMode::kLuminance)) {
    const float pass = (painter.seconds() - 0.7f) / 0.9f;
    const float filled = bar_width * share;
    if (pass > 0.0f && pass < 1.0f && filled > 0.0f) {
      const float x = kLeft - 80.0f + (filled + 80.0f) * pass;
      const float x0 = std::max(x, kLeft), x1 = std::min(x + 80.0f, kLeft + filled);
      if (x1 > x0) {
        painter.Rect(x0, bar_y - 2.0f, x1 - x0, 18.0f, Rgba(255, 255, 255, 120), sheen, 0.0f,
                     {(x0 - x) / 80.0f, 0.0f, (x1 - x) / 80.0f, 1.0f});
      }
    }
  }
  std::string status;
  if (tier == 7) {
    status = Tr(Text::kEverythingYours);
  } else {
    const int next = tier + 1;
    const auto at = uint32_t(std::ceil(achievements::TierThreshold(next) * float(available_)));
    status = (tier >= 0 ? Format(Text::kBandNow, {achievements::BandName(tier)}) + "  "
                        : std::string()) +
             (next == 7 ? std::string(Tr(Text::kNextEverything))
                        : Format(Text::kNextBand,
                                 {achievements::BandName(next), std::to_string(at)}));
  }
  painter.Text(Font::kLabel, 18.0f, status, kLeft, 166.0f, kDimWhite);
  painter.Text(Font::kLabel, 18.0f,
               Format(Text::kShareOffline, {std::to_string(int(std::lround(share * 100.0f))),
                                            std::to_string(available_)}),
               kRight, 166.0f, kFaint, 1.0f);
}

void AchievementsScreen::PaintTabs(Painter& painter) {
  constexpr float kBaseline = 204.0f;
  float x = kLeft + 4.0f;
  if (rex::ui::ImmediateTexture* lb = painter.Texture("Controller/LBumper.xds")) {
    painter.Rect(kLeft - 40.0f, kBaseline - 24.0f, 30.0f, 30.0f, kWhite, lb);
  }
  rex::ui::ImmediateTexture* selection =
      painter.Texture("DirtMasks/SelectionContainer.xds", TextureMode::kMask);
  rex::ui::ImmediateTexture* tick = painter.Texture("Common/Tick.xds", TextureMode::kMask);
  for (size_t i = 0; i < tabs_.size(); ++i) {
    const Category category = tabs_[i];
    size_t count = 0, done = 0;
    for (const Item& item : items_) {
      if (category != Category::kCount && item.meta.category != category) continue;
      ++count;
      done += item.unlocked ? 1 : 0;
    }
    const std::string label =
        category == Category::kCount ? std::string(Tr(Text::kAll))
                                     : std::string(achievements::CategoryName(category));
    const std::string counts = std::to_string(done) + "/" + std::to_string(count);
    const float width = std::max(painter.Measure(Font::kDisplay, 22.0f, label),
                                 painter.Measure(Font::kLabel, 15.0f, counts)) +
                        (done == count ? 22.0f : 0.0f);
    const bool selected = i == tab_;
    if (selected) {
      painter.Rect(x - 14.0f, kBaseline - 26.0f, width + 28.0f, 48.0f, kMagenta, selection, 6.0f,
                   kSelectionUv);
    }
    painter.Text(Font::kDisplay, 22.0f, label, x, kBaseline, selected ? kWhite : kDimWhite);
    painter.Text(Font::kLabel, 15.0f, counts, x, kBaseline + 17.0f,
                 selected ? kWhite : kFaint);
    if (done == count && tick) {
      painter.Rect(x + width - 18.0f, kBaseline - 18.0f, 18.0f, 18.0f, kGold, tick, 0.0f,
                   {0.25f, 0.28f, 0.78f, 0.72f});
    }
    painter.Hit(kTabTarget + int(i), x - 12.0f, kBaseline - 26.0f, width + 24.0f, 48.0f);
    x += width + 30.0f;
  }
  if (rex::ui::ImmediateTexture* rb = painter.Texture("Controller/RBumper.xds")) {
    painter.Rect(x - 8.0f, kBaseline - 24.0f, 30.0f, 30.0f, kWhite, rb);
  }
}

void AchievementsScreen::PaintTile(Painter& painter, const Item& item, float x, float y,
                                   bool focused, float appear) {
  rex::ui::ImmediateTexture* tile = painter.Texture("Kitparts/bars/BarBase26px.xds", TextureMode::kMask);
  const float pulse = focused ? EaseOut((now_ - focus_at_) / 0.14f) : 0.0f;
  const float grow = 6.0f * pulse;
  const float x0 = x - grow * 0.5f, y0 = y - grow * 0.5f, size = kTile + grow;
  const auto faded = [appear](uint32_t colour) { return Fade(colour, appear); };
  if (focused) {
    painter.Rect(x0 - 5.0f, y0 - 5.0f, size + 10.0f, size + 10.0f, faded(kMagenta), tile);
  }
  const bool available = item.available();
  painter.Rect(x0, y0, size, size,
               faded(item.unlocked ? Rgba(46, 34, 58, 240) : Rgba(18, 16, 24, 225)), tile);
  if (item.unlocked && item.info.gamerscore >= 50) {
    // The biggest unlocks get a gold rim.
    painter.Rect(x0 + 2.0f, y0 + 2.0f, size - 4.0f, 3.0f, faded(kGold));
  }
  const float inset = 12.0f + grow * 0.2f;
  rex::ui::ImmediateTexture* icon = icons_ ? icons_->Get(item.info, !item.unlocked) : nullptr;
  if (icon) {
    const float alpha = item.unlocked ? 1.0f : available ? 0.8f : 0.35f;
    painter.Rect(x0 + inset, y0 + inset, size - inset * 2.0f, size - inset * 2.0f,
                 faded(Fade(kWhite, alpha)), icon);
  }
  // Gamerscore pill in the top right corner.
  const std::string score = std::to_string(item.info.gamerscore);
  const float pill_width = painter.Measure(Font::kLabel, 15.0f, score) + 12.0f;
  painter.Rect(x0 + size - pill_width - 3.0f, y0 + 3.0f, pill_width, 18.0f,
               faded(item.unlocked ? Rgba(255, 190, 70, 235) : Rgba(0, 0, 0, 170)), tile);
  painter.Text(Font::kLabel, 15.0f, score, x0 + size - pill_width * 0.5f - 3.0f, y0 + 17.0f,
               faded(item.unlocked ? Rgba(30, 20, 10) : kDimWhite), 0.5f);
  if (item.unlocked) {
    // A tick in the bottom right corner.
    if (rex::ui::ImmediateTexture* tick = painter.Texture("Common/Tick.xds", TextureMode::kMask)) {
      painter.Disc(x0 + size - 15.0f, y0 + size - 15.0f, 12.0f, faded(kMagenta));
      painter.Rect(x0 + size - 25.0f, y0 + size - 25.0f, 20.0f, 20.0f, faded(kWhite), tick, 0.0f,
                   {0.2f, 0.22f, 0.82f, 0.78f});
    }
    if (state_.IsNew(item.info.id)) {
      if (rex::ui::ImmediateTexture* fresh = painter.Texture("Common/NewPause.xds")) {
        painter.Rect(x0 - 4.0f, y0 + 4.0f, 52.0f, 14.5f, faded(kWhite), fresh, 0.0f, kNewUv);
      }
    }
  } else if (!available) {
    painter.Rect(x0, y0 + size - 22.0f, size, 22.0f, faded(Rgba(0, 0, 0, 170)));
    painter.Text(Font::kLabel, 14.0f, Tr(Text::kOnline), x0 + size * 0.5f, y0 + size - 6.0f,
                 faded(kOrange), 0.5f);
  } else if (item.progress) {
    painter.Rect(x0 + 10.0f, y0 + size - 12.0f, size - 20.0f, 5.0f, faded(Rgba(255, 255, 255, 50)));
    painter.Rect(x0 + 10.0f, y0 + size - 12.0f, (size - 20.0f) * item.progress->fraction(), 5.0f,
                 faded(kMagenta));
  } else if (rex::ui::ImmediateTexture* lock = painter.Texture("Icons/MiniPanel/Locked.xds")) {
    painter.Rect(x0 + size - 26.0f, y0 + size - 26.0f, 22.0f, 22.0f, faded(Fade(kWhite, 0.85f)), lock);
  }
  if (state_.tracked() == item.info.id) {
    painter.Rect(x0 + 4.0f, y0 + 4.0f, 6.0f, 6.0f, faded(kGold));
    painter.Text(Font::kLabel, 13.0f, Tr(Text::kTracked), x0 + 14.0f, y0 + 12.0f, faded(kGold));
  }
  // One sheen pass over the tile as it takes the focus.
  if (focused) {
    if (rex::ui::ImmediateTexture* sheen = painter.Texture("Specular/SPEC_sheen.xds", TextureMode::kLuminance)) {
      const float pass = (now_ - focus_at_ - 0.05f) / 0.45f;
      if (pass > 0.0f && pass < 1.0f) {
        const float band = 40.0f, sx = x0 - band + (size + band) * pass;
        const float sx0 = std::max(sx, x0), sx1 = std::min(sx + band, x0 + size);
        if (sx1 > sx0) {
          painter.Rect(sx0, y0, sx1 - sx0, size, Rgba(255, 255, 255, 60), sheen, 0.0f,
                       {(sx0 - sx) / band, 0.0f, (sx1 - sx) / band, 1.0f});
        }
      }
    }
  }
}

void AchievementsScreen::PaintGrid(Painter& painter) {
  const float viewport = kGridBottom - kGridTop;
  painter.Clip(kLeft - 12.0f, kGridTop - 6.0f, kTilePitch * kColumns + 12.0f, viewport + 12.0f);
  for (const Section& section : sections_) {
    const float y = kGridTop + section.label_y - scroll_;
    if (y + kSectionLabel < kGridTop - 6.0f || y > kGridBottom) continue;
    painter.Text(Font::kLabel, 18.0f, section.label, kLeft, y + 20.0f, kFaint);
  }
  for (size_t i = 0; i < cells_.size(); ++i) {
    const Cell& cell = cells_[i];
    const float x = kLeft + cell.x, y = kGridTop + cell.y - scroll_;
    // A row with only its top edge in the viewport stays hidden: its value
    // badges stick out above the tile and would show as stray marks over the
    // help bar.
    if (y + kTile < kGridTop - 12.0f || y > kGridBottom - 28.0f) continue;
    // Tiles come in row by row after a tab or sort change.
    const float row = std::max(0.0f, (cell.y - scroll_) / kTilePitch);
    const float appear = EaseOut((now_ - layout_at_ - 0.04f * row - 0.015f * (cell.x / kTilePitch)) / 0.22f);
    PaintTile(painter, items_[cell.item], x, y + (1.0f - appear) * 14.0f, i == focus_, appear);
    painter.Hit(int(i), x, y, kTile, kTile);
  }
  painter.Unclip();
  // A scroll indicator when the grid holds more than it shows.
  if (content_height_ > viewport) {
    const float track_x = kLeft + kTilePitch * kColumns + 2.0f;
    const float thumb = viewport * viewport / content_height_;
    const float top = kGridTop + (viewport - thumb) * (scroll_ / (content_height_ - viewport));
    painter.Rect(track_x, kGridTop, 3.0f, viewport, Rgba(255, 255, 255, 30));
    painter.Rect(track_x, top, 3.0f, thumb, kMagenta);
  }
}

void AchievementsScreen::PaintDetail(Painter& painter) {
  const float left = kPanelLeft, top = kGridTop - 4.0f, width = kRight - kPanelLeft;
  const float height = kGridBottom - top + 4.0f;
  painter.Gradient(left, top, width, height, Rgba(16, 12, 24, 225), Rgba(16, 12, 24, 160));
  if (rex::ui::ImmediateTexture* grain = painter.Texture("DirtMasks/Panel01.xds", TextureMode::kMask)) {
    painter.Rect(left, top, width, height, Rgba(255, 255, 255, 12), grain);
  }
  painter.Rect(left, top, 4.0f, height, kMagenta);
  const Item* item = Focused();
  if (!item) {
    painter.Text(Font::kLabel, 22.0f, Tr(Text::kNoAchievements), left + 24.0f, top + 40.0f,
                 kDimWhite);
    return;
  }
  // A short fade as the focus moves.
  const float in = EaseOut((now_ - focus_at_) / 0.18f);
  const auto faded = [in](uint32_t colour) { return Fade(colour, 0.35f + 0.65f * in); };

  const float icon_size = 120.0f, icon_x = left + 24.0f, icon_y = top + 22.0f;
  painter.Rect(icon_x - 3.0f, icon_y - 3.0f, icon_size + 6.0f, icon_size + 6.0f,
               faded(item->unlocked ? kGold : Rgba(255, 255, 255, 60)));
  if (rex::ui::ImmediateTexture* icon = icons_ ? icons_->Get(item->info, !item->unlocked) : nullptr) {
    painter.Rect(icon_x, icon_y, icon_size, icon_size, faded(kWhite), icon);
  } else {
    painter.Rect(icon_x, icon_y, icon_size, icon_size, faded(Rgba(40, 36, 50)));
  }
  const float text_x = icon_x + icon_size + 22.0f, text_width = kRight - 20.0f - text_x;
  painter.Text(Font::kLabel, 17.0f, achievements::CategoryName(item->meta.category), text_x,
               icon_y + 16.0f, faded(kMagenta));
  const float name_height =
      painter.Wrapped(Font::kDisplay, 26.0f, item->name, text_x, icon_y + 18.0f, text_width,
                      faded(kWhite), 3);
  // The value with its trophy sticker.
  const float value_y = std::max(icon_y + 18.0f + name_height + 4.0f, icon_y + 84.0f);
  if (rex::ui::ImmediateTexture* sticker = painter.Texture(StickerFor(item->info.gamerscore))) {
    painter.Rect(text_x, value_y, 34.0f, 34.0f,
                 faded(Fade(kWhite, item->unlocked ? 1.0f : 0.5f)), sticker);
  }
  painter.Text(Font::kDisplay, 26.0f, std::to_string(item->info.gamerscore) + " G", text_x + 42.0f,
               value_y + 27.0f, faded(item->unlocked ? kGold : kDimWhite));

  float y = icon_y + icon_size + 34.0f;
  const float body_x = left + 24.0f, body_width = width - 48.0f;
  if (item->unlocked) {
    const std::string date = FormatDate(item->unlock_time);
    painter.Text(Font::kDisplay, 22.0f, date.empty() ? std::string(Tr(Text::kUnlocked))
                                                 : Format(Text::kUnlockedOn, {date}), body_x, y,
                 faded(kGold));
  } else if (item->meta.availability == Availability::kNeedsOnline) {
    painter.Text(Font::kDisplay, 20.0f, Tr(Text::kNeedsLive), body_x, y,
                 faded(kOrange));
  } else if (item->meta.availability == Availability::kNeedsRivals) {
    painter.Text(Font::kDisplay, 20.0f, Tr(Text::kNeedsRivals), body_x, y,
                 faded(kOrange));
  } else {
    painter.Text(Font::kDisplay, 22.0f, Tr(Text::kLocked), body_x, y, faded(kDimWhite));
  }
  y += 8.0f;
  y += painter.Wrapped(Font::kLabel, 22.0f, item->description, body_x, y, body_width,
                       faded(kDimWhite), 4);

  if (item->progress) {
    const Progress& progress = *item->progress;
    const float bar_y = kGridBottom - 86.0f;
    painter.Text(Font::kLabel, 17.0f, SourceLabel(item->meta.progress), body_x, bar_y - 10.0f,
                 faded(kFaint));
    painter.Text(Font::kDisplay, 22.0f,
                 std::to_string(progress.current) + " / " + std::to_string(progress.target),
                 body_x + body_width, bar_y - 8.0f, faded(kWhite), 1.0f);
    PaintBar(painter, body_x, bar_y, body_width, 16.0f, progress.fraction() * in, kMagenta,
             Rgba(255, 255, 255, 45));
  }
  if (state_.tracked() == item->info.id) {
    painter.Text(Font::kLabel, 17.0f, Tr(Text::kTrackedHint), body_x, kGridBottom - 22.0f,
                 faded(kGold));
  } else if (Trackable(*item)) {
    painter.Text(Font::kLabel, 17.0f, Tr(Text::kTrackHint), body_x,
                 kGridBottom - 22.0f, faded(kFaint));
  }
}

void AchievementsScreen::Paint(Painter& painter) {
  now_ = painter.seconds();
  const float dt = std::clamp(now_ - last_paint_, 0.0f, 0.1f);
  last_paint_ = now_;
  if (now_ - last_refresh_ > 1.0f) {
    // Unlocks and progress can change while the screen is open.
    last_refresh_ = now_;
    Refresh();
    Layout();
    EnsureVisible();
  }
  // Ease the scroll towards its target.
  scroll_ += (scroll_target_ - scroll_) * std::min(1.0f, dt * 14.0f);
  if (std::abs(scroll_target_ - scroll_) < 0.5f) scroll_ = scroll_target_;

  // The title's pause menu opens behind host screens; the menu backdrop lets
  // its large items show through the grid, so darken the title space more.
  painter.Gradient(0.0f, 0.0f, 1280.0f, 720.0f, Rgba(8, 6, 12, 170), Rgba(8, 6, 12, 90));
  const float intro = EaseOut(now_ / 0.7f);
  PaintHeader(painter, intro);
  PaintTabs(painter);
  PaintGrid(painter);
  PaintDetail(painter);
}

}  // namespace

AchievementUiState::AchievementUiState(std::filesystem::path path) : path_(std::move(path)) {
  std::ifstream file(path_);
  if (!file) return;
  known_ = true;
  std::string line;
  while (std::getline(file, line)) {
    const size_t equals = line.find('=');
    if (line.empty() || line[0] == '#' || equals == std::string::npos) continue;
    std::string key = line.substr(0, equals);
    key.erase(std::remove(key.begin(), key.end(), ' '), key.end());
    std::string value = line.substr(equals + 1);
    for (char& c : value) {
      if (c == '[' || c == ']' || c == ',') c = ' ';
    }
    std::istringstream values(value);
    uint32_t number = 0;
    if (key == "tracked") {
      if (values >> number) tracked_ = number;
    } else if (key == "seen") {
      while (values >> number) seen_.insert(number);
    }
  }
}

void AchievementUiState::SetTracked(std::optional<uint32_t> id) {
  tracked_ = id;
  achievements::SetWanted(id.has_value());
  Save();
}

void AchievementUiState::MarkSeen(uint32_t id) {
  if (seen_.insert(id).second) Save();
}

void AchievementUiState::Prime(const rex::system::AchievementManager& manager) {
  if (known_) return;
  known_ = true;
  for (const auto& info : manager.ListAchievements()) {
    if (manager.IsUnlocked(info.id)) seen_.insert(info.id);
  }
  Save();
}

void AchievementUiState::Save() const {
  if (path_.empty()) return;
  std::error_code error;
  std::filesystem::create_directories(path_.parent_path(), error);
  std::ostringstream text;
  text << "# Pinyon Shift achievements screen: the tracked achievement and the unlocks\n"
          "# already seen (no NEW mark).\n";
  if (tracked_) text << "tracked = " << *tracked_ << "\n";
  text << "seen = [";
  bool first = true;
  for (uint32_t id : seen_) {
    text << (first ? "" : ", ") << id;
    first = false;
  }
  text << "]\n";
  // Written beside and moved over, so a failed write leaves the old file.
  const auto temporary = std::filesystem::path(path_).concat(".tmp");
  {
    std::ofstream file(temporary, std::ios::binary | std::ios::trunc);
    if (!file || !(file << text.str())) return;
  }
  std::filesystem::rename(temporary, path_, error);
}

std::unique_ptr<hostui::MenuScreen> CreateAchievementsScreen(
    const rex::system::AchievementManager& achievements, AchievementIcons* icons,
    AchievementUiState& state) {
  auto screen = std::make_shared<AchievementsScreen>(achievements, icons, state);
  auto menu = std::make_unique<hostui::MenuScreen>("ACHIEVEMENTS", std::vector<hostui::MenuRow>{});
  menu->set_paint([screen](Painter& painter) { screen->Paint(painter); });
  menu->set_command([screen](NavCommand command) { return screen->Command(command); });
  menu->set_pointer([screen](int target, MenuScreen::Pointer pointer) {
    return screen->Pointer(target, pointer);
  });
  menu->set_scroll([screen](int steps) { screen->Scroll(steps); });
  menu->set_help([screen] { return screen->Help(); });
  diagnostics::RecordEvent("achievements.open");
  return menu;
}

}  // namespace pinyon_shift::ui
