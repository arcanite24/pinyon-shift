#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <rex/system/xam/content_manager.h>

namespace fs = std::filesystem;
using rex::system::xam::ContentManager;
using rex::system::xam::XCONTENT_AGGREGATE_DATA;
using rex::system::XContentType;

int main() {
  const auto root = fs::temp_directory_path() / ("pinyon-content-roots-" +
      std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
  if (!fs::create_directory(root)) return 1;
  const auto modded = root / "modded", shared = root / "shared";
  constexpr uint32_t title = 0x4D5309C9;
  constexpr uint64_t user = 0xB13EBABEBABEBABE;
  bool passed = true;
  {
    ContentManager manager(nullptr, modded);
    XCONTENT_AGGREGATE_DATA dlc{};
    dlc.title_id = title;
    dlc.content_type = XContentType::kMarketplaceContent;
    dlc.set_file_name("owned-rally");
    dlc.set_display_name(u"Owned Rally");
    // An unset override retains the SDK's original storage and enumeration.
    fs::create_directories(modded / "0000000000000000/4D5309C9/00000002/owned-rally");
    passed &= manager.WriteContentHeaderFile(0, dlc, 1) == 0;
    passed &= manager.ListContent(0, 0, dlc.content_type, title).size() == 1;

    manager.SetMarketplaceRoot(shared);
    passed &= manager.ListContent(0, 0, dlc.content_type, title).empty();
    fs::create_directories(shared / "0000000000000000/4D5309C9/00000002/owned-rally");
    dlc.set_display_name(u"Shared owned Rally");
    passed &= manager.WriteContentHeaderFile(user, dlc, 1) == 0;
    auto items = manager.ListContent(0, 0, dlc.content_type, title);
    passed &= items.size() == 1 && items.front().display_name() == u"Shared owned Rally";
    XCONTENT_AGGREGATE_DATA read{};
    passed &= manager.ReadContentHeaderFile("owned-rally", user, title, dlc.content_type, read) == 0;
    passed &= read.display_name() == u"Shared owned Rally";

    // Save content still belongs to the selected profile, including headers.
    XCONTENT_AGGREGATE_DATA save{};
    save.title_id = title;
    save.xuid = user;
    save.content_type = XContentType::kSavedGame;
    save.set_file_name("ForzaProfile");
    fs::create_directories(modded / "B13EBABEBABEBABE/4D5309C9/00000001/ForzaProfile");
    passed &= manager.WriteContentHeaderFile(user, save) == 0;
    passed &= manager.ListContent(0, user, save.content_type, title).size() == 1;
    passed &= fs::is_regular_file(modded / "B13EBABEBABEBABE/4D5309C9/Headers/00000001/ForzaProfile.header");
    passed &= !fs::exists(shared / "B13EBABEBABEBABE");

    // A second profile sees the same shared DLC without creating a DLC copy.
    ContentManager second(nullptr, root / "second-profile");
    second.SetMarketplaceRoot(shared);
    passed &= second.ListContent(0, 0, dlc.content_type, title).size() == 1;
    passed &= !fs::exists(root / "second-profile");
    manager.SetMarketplaceRoot({});
    items = manager.ListContent(0, 0, dlc.content_type, title);
    passed &= items.size() == 1 && items.front().display_name() == u"Owned Rally";
  }
  fs::remove_all(root);
  std::cout << (passed ? "Shared DLC roots preserve profile saves and default storage.\n" : "Content root test failed.\n");
  return passed ? 0 : 1;
}
