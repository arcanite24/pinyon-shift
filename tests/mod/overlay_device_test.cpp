#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>

#include <rex/filesystem/vfs.h>

#include "mod/overlay_device.h"
#include "pinyon_shift_diagnostics.h"

namespace pinyon_shift::diagnostics {
void RecordEvent(std::string_view, std::initializer_list<Field>) {}
}

namespace fs = std::filesystem;

int main() {
  const auto root = fs::temp_directory_path() / ("pinyon-overlay-" +
      std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
  fs::create_directories(root / "base/media/shared");
  fs::create_directories(root / "overlay/media/shared");
  fs::create_directories(root / "overlay/media/ColoradoDirt/Ribbon_00");
  std::ofstream(root / "base/media/shared/keep.xml") << "base";
  std::ofstream(root / "overlay/media/shared/replacement.xml") << "mod";
  std::ofstream(root / "overlay/media/ColoradoDirt/Ribbon_00/track.col") << "terrain";
  bool passed = true;
  {
    rex::filesystem::VirtualFileSystem vfs;
    auto device = std::make_unique<pinyon_shift::mod::OverlayDevice>(
        "\\Device\\Test", root / "base", std::vector<fs::path>{root / "overlay"});
    passed &= device->Initialize() && vfs.RegisterDevice(std::move(device)) &&
              vfs.RegisterSymbolicLink("game:", "\\Device\\Test");
    for (const auto& [path, expected] : {
        std::pair{"game:\\media\\shared\\keep.xml", "base"},
        std::pair{"game:\\media\\shared\\replacement.xml", "mod"},
        std::pair{"game:\\media\\ColoradoDirt\\Ribbon_00\\track.col", "terrain"}}) {
      rex::filesystem::File* file = nullptr;
      rex::filesystem::FileAction action{};
      const auto status = vfs.OpenFile(nullptr, path, rex::filesystem::FileDisposition::kOpen,
          rex::filesystem::FileAccess::kGenericRead, false, true, &file, &action);
      passed &= status == 0 && file;
      if (file) {
        uint8_t bytes[32]{};
        size_t read = 0;
        passed &= file->ReadSync(bytes, 0, &read) == 0 &&
                  std::string(reinterpret_cast<char*>(bytes), read) == expected;
        file->Destroy();
      }
    }
    // A directory lists the mod's new files beside the base's, as the title
    // enumerates some directories.
    const auto listed = [&](const char* directory, const char* name) {
      auto* entry = vfs.ResolvePath(directory);
      if (!entry) return false;
      for (const auto& child : entry->children()) {
        if (child->name() == name) return true;
      }
      return false;
    };
    passed &= listed("game:\\media\\shared", "keep.xml") &&
              listed("game:\\media\\shared", "replacement.xml") &&
              listed("game:\\media", "ColoradoDirt");
  }
  fs::remove_all(root);
  if (!passed) {
    std::cerr << "Overlay hides base files, cannot open new directories or omits mod files "
                 "from listings\n";
    return 1;
  }
  std::cout << "Overlay keeps base files, opens assets in new directories and lists mod files.\n";
}
