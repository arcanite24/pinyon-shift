#pragma once

#include <cstdint>
#include <filesystem>
#include <memory>
#include <optional>
#include <set>

namespace rex::system {
class AchievementManager;
}

namespace pinyon_shift::hostui {
class MenuScreen;
}

namespace pinyon_shift::ui {

class AchievementIcons;

// What the achievements screen remembers between opens, beside the unlock
// state (<state>/user/achievements/pinyon-shift-ui.toml): the tracked
// achievement and the unlocks the player has seen, for the NEW marks.
class AchievementUiState {
 public:
  explicit AchievementUiState(std::filesystem::path path);

  std::optional<uint32_t> tracked() const { return tracked_; }
  void SetTracked(std::optional<uint32_t> id);
  // Unlocks not yet focused on the screen. Before the first save every
  // unlock counts as seen, so an existing save does not open full of marks.
  bool IsNew(uint32_t id) const { return known_ && !seen_.count(id); }
  void MarkSeen(uint32_t id);
  // Called when the screen opens: on the first open, takes every current
  // unlock as seen.
  void Prime(const rex::system::AchievementManager& achievements);

 private:
  void Save() const;

  std::filesystem::path path_;
  bool known_ = false;  // the file existed or the screen primed it
  std::optional<uint32_t> tracked_;
  std::set<uint32_t> seen_;
};

// The achievements screen (AC-2): a header with the gamerscore and the
// completion wristband, category tabs, a grid of icon tiles and the focused
// achievement's details with its unlock date and progress. F7, SETTINGS >
// ACHIEVEMENTS and the title's XamShowAchievementsUI open it.
std::unique_ptr<hostui::MenuScreen> CreateAchievementsScreen(
    const rex::system::AchievementManager& achievements, AchievementIcons* icons,
    AchievementUiState& state);

}  // namespace pinyon_shift::ui
