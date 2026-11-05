#pragma once

#include <cstdint>
#include <filesystem>
#include <memory>
#include <unordered_map>
#include <vector>

#include <rex/system/achievement_store.h>

namespace rex::ui {
class ImmediateDrawer;
class ImmediateTexture;
}  // namespace rex::ui

namespace pinyon_shift::ui {

// Achievement icons for the host UI (AC-1.4): the title's XDBF images, and for
// achievements a content package adds (1000 Club's 216-225) the images in
// that package's spa.bin, which the title's XDBF does not hold. Each icon
// also has a grey copy for locked achievements. UI thread only.
class AchievementIcons {
 public:
  // `content_root` holds the installed packages
  // (<state>/user/<xuid>/<title>/00000002/<package>/spa.bin).
  AchievementIcons(rex::ui::ImmediateDrawer& drawer, std::filesystem::path content_root);
  ~AchievementIcons();

  rex::ui::ImmediateTexture* Get(const rex::system::AchievementInfo& achievement, bool grey);

 private:
  struct Entry {
    std::unique_ptr<rex::ui::ImmediateTexture> colour;
    std::unique_ptr<rex::ui::ImmediateTexture> grey;
  };
  std::vector<uint8_t> FindImage(const rex::system::AchievementInfo& achievement);
  void LoadPackages();

  rex::ui::ImmediateDrawer& drawer_;
  std::filesystem::path content_root_;
  bool packages_loaded_ = false;
  // Achievement ID -> the PNG bytes from a package's spa.bin.
  std::unordered_map<uint32_t, std::vector<uint8_t>> package_images_;
  std::unordered_map<uint32_t, Entry> icons_;
};

}  // namespace pinyon_shift::ui
