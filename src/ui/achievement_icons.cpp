#include "ui/achievement_icons.h"

#include <algorithm>
#include <fstream>
#include <iterator>
#include <system_error>

#include <rex/system/kernel_state.h>
#include <rex/system/util/xdbf_utils.h>
#include <rex/ui/image_decode.h>
#include <rex/ui/immediate_drawer.h>

namespace pinyon_shift::ui {
namespace {

using rex::system::util::XdbfSection;

}  // namespace

AchievementIcons::AchievementIcons(rex::ui::ImmediateDrawer& drawer,
                                   std::filesystem::path content_root)
    : drawer_(drawer), content_root_(std::move(content_root)) {}

AchievementIcons::~AchievementIcons() = default;

void AchievementIcons::LoadPackages() {
  packages_loaded_ = true;
  auto* kernel_state = rex::system::kernel_state();
  if (!kernel_state) return;
  // Achievements the title itself defines keep the title's images.
  std::vector<uint32_t> title_ids;
  if (const auto title = kernel_state->title_xdbf(); title.is_valid()) {
    for (const auto& entry : title.GetAchievements()) title_ids.push_back(entry.id);
  }
  std::error_code error;
  if (!std::filesystem::is_directory(content_root_, error)) return;
  for (const auto& package : std::filesystem::directory_iterator(content_root_, error)) {
    std::ifstream file(package.path() / "spa.bin", std::ios::binary);
    if (!file) continue;
    const std::vector<uint8_t> data((std::istreambuf_iterator<char>(file)),
                                    std::istreambuf_iterator<char>());
    const rex::system::util::XdbfGameData db(data.data(), data.size());
    if (!db.is_valid()) continue;
    for (const auto& entry : db.GetAchievements()) {
      const uint32_t id = entry.id;
      if (std::find(title_ids.begin(), title_ids.end(), id) != title_ids.end() ||
          package_images_.count(id)) {
        continue;
      }
      if (const auto block = db.GetEntry(XdbfSection::kImage, uint64_t(uint32_t(entry.image_id)))) {
        package_images_[id].assign(block.buffer, block.buffer + block.size);
      }
    }
  }
}

std::vector<uint8_t> AchievementIcons::FindImage(const rex::system::AchievementInfo& achievement) {
  if (!packages_loaded_) LoadPackages();
  if (const auto it = package_images_.find(achievement.id); it != package_images_.end()) {
    return it->second;
  }
  auto* kernel_state = rex::system::kernel_state();
  if (!kernel_state || achievement.image_id == 0) return {};
  const auto title = kernel_state->title_xdbf();
  if (!title.is_valid()) return {};
  const auto block = title.GetEntry(XdbfSection::kImage, uint64_t(achievement.image_id));
  return block ? std::vector<uint8_t>(block.buffer, block.buffer + block.size)
               : std::vector<uint8_t>();
}

rex::ui::ImmediateTexture* AchievementIcons::Get(const rex::system::AchievementInfo& achievement,
                                                 bool grey) {
  auto [it, added] = icons_.try_emplace(achievement.id);
  Entry& entry = it->second;
  if (added) {
    const std::vector<uint8_t> image = FindImage(achievement);
    int width = 0, height = 0;
    std::vector<uint8_t> rgba =
        image.empty() ? std::vector<uint8_t>()
                      : rex::ui::DecodeImageRGBA(image.data(), image.size(), width, height);
    if (!rgba.empty() && width > 0 && height > 0) {
      entry.colour = drawer_.CreateTexture(uint32_t(width), uint32_t(height),
                                           rex::ui::ImmediateTextureFilter::kLinear, false,
                                           rgba.data());
      // Locked: luminance, darkened a little so the colour icons stand out.
      for (size_t i = 0; i + 3 < rgba.size(); i += 4) {
        const uint32_t luma =
            (uint32_t(rgba[i]) * 54 + uint32_t(rgba[i + 1]) * 183 + uint32_t(rgba[i + 2]) * 19) >> 8;
        rgba[i] = rgba[i + 1] = rgba[i + 2] = uint8_t(luma * 3 / 5 + 20);
      }
      entry.grey = drawer_.CreateTexture(uint32_t(width), uint32_t(height),
                                         rex::ui::ImmediateTextureFilter::kLinear, false,
                                         rgba.data());
    }
  }
  return grey ? entry.grey.get() : entry.colour.get();
}

}  // namespace pinyon_shift::ui
