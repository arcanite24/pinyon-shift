#pragma once

#include <filesystem>
#include <memory>
#include <string>
#include <string_view>
#include <vector>

#include <rex/filesystem/device.h>
#include <rex/filesystem/devices/host_path_device.h>

namespace pinyon_shift::mod {

// Whether the title has opened a mod's replacement for the game file at
// `guest_path` ("game:\media\x", "\media\x" or a trailing part such as
// "db\gamedb.slt", any case). The title checks
// each block it reads of some game files against a SHA-256 table for the
// original, which a replacement cannot match.
bool IsOverriddenGamePath(std::string_view guest_path);

// The game files with mods' files over them (NP-7.4): a file a mod ships under
// mods/<name>/game/ replaces the base file with the same path, earlier mods in
// the load order winning. Existing directories come from the base; new
// directories can come from a mod. Granularity is whole files, because the
// title reads its
// archives through C FILE* streams.
class OverlayDevice final : public rex::filesystem::Device {
 public:
  OverlayDevice(std::string_view mount_path, const std::filesystem::path& base_root,
                std::vector<std::filesystem::path> overlay_roots);

  bool Initialize() override;
  void Dump(rex::string::StringBuffer* string_buffer) override;
  rex::filesystem::Entry* ResolvePath(std::string_view path) override;

  const std::string& name() const override { return base_->name(); }
  uint32_t attributes() const override { return base_->attributes(); }
  uint32_t component_name_max_length() const override {
    return base_->component_name_max_length();
  }
  uint32_t total_allocation_units() const override { return base_->total_allocation_units(); }
  uint32_t available_allocation_units() const override {
    return base_->available_allocation_units();
  }
  uint32_t sectors_per_allocation_unit() const override {
    return base_->sectors_per_allocation_unit();
  }
  uint32_t bytes_per_sector() const override { return base_->bytes_per_sector(); }

 private:
  std::unique_ptr<rex::filesystem::HostPathDevice> base_;
  std::vector<std::unique_ptr<rex::filesystem::HostPathDevice>> overlays_;
};

}  // namespace pinyon_shift::mod
