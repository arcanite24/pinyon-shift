#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>

#ifdef _WIN32
#include <Windows.h>
#endif

#include <rex/system/xam/content_manager.h>

#include "pinyon_shift_diagnostics.h"
#include "save_backups.h"

namespace pinyon_shift::diagnostics {
void RecordEvent(std::string_view, std::initializer_list<Field>) {}
}

namespace fs = std::filesystem;

fs::path LongPath(fs::path path) {
#ifdef _WIN32
  path = fs::absolute(path).make_preferred();
  path = L"\\\\?\\" + path.native();
#endif
  return path;
}

void Write(const fs::path& path, const std::string& value) {
  const auto output = LongPath(path);
  fs::create_directories(output.parent_path());
  std::ofstream(output) << value;
}

std::string Read(const fs::path& path) {
  std::ifstream file(LongPath(path));
  return {std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>()};
}

int main() {
  auto root = fs::temp_directory_path() / ("pinyon-dlc-backups-" +
      std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
  const auto user = root / "user", backups = root / "backups";
  const auto title = fs::path("0000000000000000/4D5309C9");
  const auto enabled = title / "00000002/owned/Media" / std::string(100, 'a') /
                       std::string(100, 'b') / "terrain.bin";
  const auto disabled = title / "Disabled/00000002/other/car.bin";
  const auto header = title / "Headers/00000002/owned.header";
  Write(user / "profile/ForzaProfile", "current save");
  Write(user / "profile/rally-progress.toml", "current Rally progress");
  Write(user / enabled, "current terrain");
  Write(user / disabled, "disabled car");
  Write(user / header, "current entitlement");
  Write(backups / "prior/user/profile/ForzaProfile", "prior save");
  Write(backups / "prior/user/profile/rally-progress.toml", "prior Rally progress");
  // Old snapshots may have copied installed DLC. Never restore that old data.
  Write(backups / "prior/user" / header, "obsolete entitlement");
  Write(backups / "restore-pending.txt", "prior");
  pinyon_shift::SaveBackups::ApplyPendingRestore(user, backups);
  bool passed = Read(user / "profile/ForzaProfile") == "prior save" &&
      Read(user / "profile/rally-progress.toml") == "prior Rally progress" &&
      Read(user / enabled) == "current terrain" && Read(user / disabled) == "disabled car" &&
      Read(user / header) == "current entitlement";
  pinyon_shift::SaveBackups manager(user, backups);
  const auto slots = manager.List();
  bool snapshot = false;
  for (const auto& slot : slots) {
    if (slot.name.find("before-restore") == std::string::npos) continue;
    snapshot = true;
    passed &= slot.files == 2 && Read(slot.path / "user/profile/ForzaProfile") == "current save" &&
              Read(slot.path / "user/profile/rally-progress.toml") == "current Rally progress" &&
              !fs::exists(slot.path / "user" / header) &&
              !fs::exists(slot.path / "user" / title / "00000002") &&
              !fs::exists(slot.path / "user" / title / "Disabled");
  }
  const auto modded = root / "user-modded";
  passed &= pinyon_shift::SaveBackups::CopyProfile(user, modded) &&
            Read(modded / "profile/ForzaProfile") == "prior save" &&
            Read(modded / "profile/rally-progress.toml") == "prior Rally progress" &&
            !fs::exists(modded / title / "00000002") &&
            !fs::exists(modded / title / "Disabled");
#ifdef _WIN32
  // A Windows handle without delete sharing blocks an atomic directory move.
  // Releasing it shortly after copying must let the new profile publish.
  const auto lock_source = root / "lock-source", lock_target = root / "lock-target";
  for (int index = 0; index < 512; ++index) {
    Write(lock_source / (std::to_string(index) + ".sav"), "private progress");
  }
  std::atomic<bool> finished = false, acquired = false;
  std::thread holder([&] {
    const auto staging = LongPath(lock_target.string() + ".partial");
    while (!finished.load()) {
      const auto handle = CreateFileW(staging.c_str(), GENERIC_READ,
          FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_EXISTING,
          FILE_FLAG_BACKUP_SEMANTICS, nullptr);
      if (handle != INVALID_HANDLE_VALUE) {
        acquired = true;
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
        CloseHandle(handle);
        return;
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
  });
  const bool copied = pinyon_shift::SaveBackups::CopyProfile(lock_source, lock_target);
  finished = true;
  holder.join();
  passed &= acquired && copied && Read(lock_target / "511.sav") == "private progress";
#endif
  // Both profiles enumerate the launcher's shared installation. A stale
  // Marketplace copy in an older modded profile must never become active.
  using rex::system::xam::ContentManager;
  using rex::system::xam::XCONTENT_AGGREGATE_DATA;
  using rex::system::XContentType;
  ContentManager content(nullptr, modded);
  content.SetMarketplaceRoot(user);
  XCONTENT_AGGREGATE_DATA data{};
  data.device_id = 1;
  data.title_id = 0x4D5309C9;
  data.content_type = XContentType::kMarketplaceContent;
  data.set_file_name("owned");
  data.set_display_name(u"Owned DLC");
  passed &= content.WriteContentHeaderFile(0, data, 1) == 0;
  Write(modded / title / "00000002/stale/car.bin", "stale copy");
  auto packages = content.ListContent(1, 0, XContentType::kMarketplaceContent, 0x4D5309C9);
  passed &= packages.size() == 1 && packages.front().file_name() == "owned";
  fs::rename(user / title / "00000002/owned", user / title / "Disabled/00000002/owned");
  passed &= content.ListContent(1, 0, XContentType::kMarketplaceContent, 0x4D5309C9).empty();
  data.content_type = XContentType::kSavedGame;
  data.set_file_name("isolated");
  Write(modded / title / "00000001/isolated/profile.bin", "modded progress");
  passed &= content.ContentExists(0, data) && content.WriteContentHeaderFile(0, data) == 0 &&
            fs::exists(modded / title / "Headers/00000001/isolated.header") &&
            !fs::exists(user / title / "Headers/00000001/isolated.header");
  fs::remove_all(LongPath(root));
  if (!passed || !snapshot) { std::cerr << "DLC changed or entered a save backup\n"; return 1; }
  std::cout << "Save restore preserves DLC; modded profiles share its selection.\n";
}
