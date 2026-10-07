#include <algorithm>
#include <cstdint>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <queue>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

#include <rex/filesystem/devices/stfs_container_device.h>
#include <rex/cvar.h>
#include <rex/filesystem/file.h>
#include <rex/kernel/init.h>
#include <rex/runtime.h>
#include <rex/system/user_module.h>
#include <rex/system/xex_module.h>
#include <rex/system/xam/content_manager.h>

#include "ui/hostui/fh1_archive.h"

using pinyon_shift::hostui::DecompressXmem;
using pinyon_shift::hostui::ParseXmemPayload;

int main(int argc, char** argv) {
  if (argc == 5 && std::string(argv[1]) == "--archive-member") {
    const auto archive = pinyon_shift::hostui::Fh1Archive::Open(argv[2]);
    const auto member = archive ? archive->Read(argv[3]) : std::nullopt;
    if (!member) {
      std::cerr << "archive member missing, invalid or failed CRC\n";
      return 1;
    }
    std::ofstream output(argv[4], std::ios::binary);
    output.write(reinterpret_cast<const char*>(member->data()), member->size());
    output.close();
    return output ? 0 : 1;
  }
  // Used only after the importer has checked the whole package against the
  // pinned catalog. Stage in a fresh root; the importer publishes it atomically.
  if (argc == 5 && std::string(argv[1]) == "--dlc-files") {
    try {
      using rex::X_STATUS;
      using rex::X_RESULT;
      auto destination = std::filesystem::absolute(argv[3]).lexically_normal();
#ifdef _WIN32
      // The runtime's content tree can exceed MAX_PATH in installed sources.
      if (!destination.native().starts_with(L"\\\\?\\"))
        destination = destination.native().starts_with(L"\\\\")
            ? L"\\\\?\\UNC\\" + destination.native().substr(2)
            : L"\\\\?\\" + destination.native();
#endif
      const std::string id = argv[4];
      if (id.empty() || id.size() > 42 || id.find_first_not_of("0123456789ABCDEF") != std::string::npos ||
          std::filesystem::exists(destination)) {
        throw std::runtime_error("expected a package ID and a new staging root");
      }
      rex::filesystem::StfsContainerDevice device("", argv[2]);
      if (!device.Initialize() || device.header().metadata.execution_info.title_id != 0x4D5309C9 ||
          device.header().metadata.content_type != rex::system::XContentType::kMarketplaceContent) {
        throw std::runtime_error("expected FH1 Marketplace content");
      }
      auto* root = device.ResolvePath("");
      if (!root) throw std::runtime_error("missing package root");
      rex::system::xam::ContentManager manager(nullptr, destination);
      rex::system::xam::XCONTENT_AGGREGATE_DATA data{};
      data.device_id = 1;
      data.content_type = rex::system::XContentType::kMarketplaceContent;
      data.title_id = 0x4D5309C9;
      data.xuid = 0;
      data.set_file_name(id);
      data.set_display_name(device.header().metadata.display_name(rex::system::XLanguage::kEnglish));
      const auto package_root = destination / "0000000000000000" / "4D5309C9" / "00000002" / id;
      std::queue<rex::filesystem::Entry*> entries;
      std::set<std::filesystem::path> paths;
      entries.push(root);
      std::vector<uint8_t> buffer(4 * 1024 * 1024);
      while (!entries.empty()) {
        auto* entry = entries.front();
        entries.pop();
        for (const auto& child : entry->children()) entries.push(child.get());
        if (entry == root) continue;
        // Validate individual components as well as the complete guest path.
        const auto& name = entry->name();
        if (name.empty() || name == "." || name == ".." || name.back() == '.' ||
            name.back() == ' ' || name.find_first_of("\\/:<>\"|?*") != std::string::npos ||
            std::any_of(name.begin(), name.end(), [](unsigned char c) { return c < 32; })) {
          throw std::runtime_error("unsafe package member name");
        }
        auto relative = std::filesystem::path(rex::string::utf8_fix_path_separators(entry->path()));
        if (relative.is_absolute() || relative.has_root_path() ||
            !paths.insert(relative).second) throw std::runtime_error("unsafe or duplicate package path");
        const auto output_path = package_root / relative;
        if (entry->attributes() & rex::filesystem::kFileAttributeDirectory) {
          std::filesystem::create_directories(output_path);
          continue;
        }
        std::filesystem::create_directories(output_path.parent_path());
        rex::filesystem::File* raw = nullptr;
        if (entry->Open(rex::filesystem::FileAccess::kFileReadData, &raw) != X_STATUS_SUCCESS)
          throw std::runtime_error("could not open package member");
        std::unique_ptr<rex::filesystem::File, void(*)(rex::filesystem::File*)> input(
            raw, [](rex::filesystem::File* file) { file->Destroy(); });
        std::ofstream output(output_path, std::ios::binary);
        for (size_t offset = 0; offset < entry->size();) {
          const auto size = std::min(buffer.size(), entry->size() - offset);
          size_t read = 0;
          if (input->ReadSync(std::span<uint8_t>(buffer.data(), size), offset, &read) !=
                  X_STATUS_SUCCESS || read != size)
            throw std::runtime_error("incomplete package member");
          output.write(reinterpret_cast<const char*>(buffer.data()), read);
          if (!output) throw std::runtime_error("could not write package member");
          offset += read;
        }
        output.close();
        if (!output) throw std::runtime_error("could not finish package member");
      }
      uint32_t license = 0;
      for (const auto& item : device.header().header.licenses)
        if (item.license_flags) license |= item.license_bits;
      if (manager.WriteContentHeaderFile(0, data, license) != X_ERROR_SUCCESS)
        throw std::runtime_error("could not write content header");
      return 0;
    } catch (const std::exception& error) {
      std::cerr << error.what() << '\n';
      return 1;
    }
  }
  if (argc == 4 && std::string(argv[1]) == "--title-update-files") {
    try {
      using rex::X_STATUS;
      const auto destination = std::filesystem::absolute(argv[3]);
      if (std::filesystem::exists(destination)) {
        throw std::runtime_error("title-update destination already exists");
      }
      rex::filesystem::StfsContainerDevice device("", argv[2]);
      if (!device.Initialize()) {
        throw std::runtime_error("failed to open title-update package");
      }
      auto* root = device.ResolvePath("/");
      if (!root || root->children().size() != 4) {
        throw std::runtime_error("expected four title-update files");
      }
      std::filesystem::create_directories(destination);
      for (const auto& entry : root->children()) {
        const auto& name = entry->name();
        if (name != "default.xexp" && name != "SpeechFacade_default.xexp" &&
            name != "XMediaFacade_default.xexp" && name != "media.zip") {
          throw std::runtime_error("unexpected title-update entry");
        }
        if (entry->size() > std::filesystem::file_size(argv[2])) {
          throw std::runtime_error("invalid title-update entry size");
        }
        rex::filesystem::File* file = nullptr;
        if (entry->Open(rex::filesystem::FileAccess::kFileReadData, &file) !=
            X_STATUS_SUCCESS) {
          throw std::runtime_error("failed to open title-update entry");
        }
        std::vector<uint8_t> data(entry->size());
        size_t read = 0;
        const auto status = file->ReadSync(data, 0, &read);
        file->Destroy();
        if (status != X_STATUS_SUCCESS || read != data.size()) {
          throw std::runtime_error("incomplete title-update entry");
        }
        std::ofstream output(destination / name, std::ios::binary);
        output.write(reinterpret_cast<const char*>(data.data()), data.size());
        output.close();
        if (!output) throw std::runtime_error("failed to write title-update entry");
      }
      return 0;
    } catch (const std::exception& error) {
      std::cerr << error.what() << '\n';
      return 1;
    }
  }
  if (argc == 6 && std::string(argv[1]) == "--title-update-image") {
    // Apply one title-update patch to its base module and write the patched
    // headers and image before imports are resolved, for page verification.
    try {
      using rex::X_STATUS;
      const auto read = [](const char* path) {
        std::ifstream file(std::filesystem::path(path), std::ios::binary);
        std::vector<uint8_t> data((std::istreambuf_iterator<char>(file)), {});
        if (!file.good() && !file.eof()) throw std::runtime_error(std::string("cannot read ") + path);
        return data;
      };
      const auto base = read(argv[2]), patch = read(argv[3]);
      const auto root = std::filesystem::canonical(argv[2]).parent_path();
      rex::Runtime runtime(root.string());
      if (runtime.Setup(rex::RuntimeConfig{
              .kernel_init = rex::kernel::InitializeKernel, .tool_mode = true}) != X_STATUS_SUCCESS) {
        std::cerr << "failed to initialize the runtime\n";
        return 1;
      }
      auto* kernel = runtime.kernel_state();
      rex::runtime::XexModule module(kernel->function_dispatcher(), kernel);
      rex::runtime::XexModule update(kernel->function_dispatcher(), kernel);
      if (!module.Load("base", "game:\\base", base.data(), base.size()) ||
          !update.Load("patch", "game:\\patch", patch.data(), patch.size()) || !update.is_patch()) {
        std::cerr << "failed to read the base module or its patch\n";
        return 1;
      }
      if (const int code = update.ApplyPatch(&module)) {
        std::cerr << "title update did not apply (code " << code << ")\n";
        return 2;
      }
      std::ofstream headers(argv[4], std::ios::binary | std::ios::trunc);
      headers.write(reinterpret_cast<const char*>(module.xex_header()),
                    module.xex_header()->header_size);
      std::ofstream image(argv[5], std::ios::binary | std::ios::trunc);
      image.write(reinterpret_cast<const char*>(
                      runtime.memory()->TranslateVirtual(module.base_address())),
                  module.image_size());
      headers.close();
      image.close();
      return headers && image ? 0 : 1;
    } catch (const std::exception& error) {
      std::cerr << error.what() << '\n';
      return 1;
    }
  }
  if ((argc == 4 || (argc == 5 && std::string(argv[4]) == "--apply-patch")) &&
      std::string(argv[1]) == "--xex-image") {
    try {
      using rex::X_STATUS;
      const auto input = std::filesystem::canonical(argv[2]);
      // A sibling .xexp is applied only on request (title-update builds).
      rex::cvar::SetFlagByName("xex_apply_patches", argc == 5 ? "true" : "false");
      rex::Runtime runtime(input.parent_path().string());
      if (runtime.Setup(rex::RuntimeConfig{
              .kernel_init = rex::kernel::InitializeKernel, .tool_mode = true}) !=
              X_STATUS_SUCCESS ||
          runtime.LoadXexImage("game:\\" + input.filename().string()) !=
              X_STATUS_SUCCESS) {
        std::cerr << "failed to load XEX image\n";
        return 1;
      }
      const auto* module = runtime.kernel_state()->GetExecutableModule()->xex_module();
      std::ofstream output(argv[3], std::ios::binary | std::ios::trunc);
      output.write(reinterpret_cast<const char*>(
                       runtime.memory()->TranslateVirtual(module->base_address())),
                   module->image_size());
      output.close();
      return output ? 0 : 1;
    } catch (const std::exception& error) {
      std::cerr << error.what() << '\n';
      return 1;
    }
  }
  if (argc == 2 && std::string(argv[1]) == "--self-test") {
    const std::vector<uint8_t> framed = {
        0x00, 0x03, 1, 2, 3, 0xFF, 0x00, 0x02, 0x00, 0x02, 4, 5};
    std::vector<uint8_t> payload;
    return ParseXmemPayload(framed, 0x8002, payload) &&
                   payload == std::vector<uint8_t>({1, 2, 3, 4, 5})
               ? 0
               : 1;
  }
  if (argc != 6) {
    std::cerr << "usage: fh1_archive_extract <archive> <offset> <compressed-size> "
                 "<uncompressed-size> <output>\n";
    return 2;
  }

  uint64_t offset;
  size_t compressed_size;
  size_t uncompressed_size;
  try {
    offset = std::stoull(argv[2]);
    compressed_size = std::stoull(argv[3]);
    uncompressed_size = std::stoull(argv[4]);
  } catch (const std::exception&) {
    std::cerr << "invalid archive entry range\n";
    return 2;
  }
  constexpr size_t kMaximumShaderEntrySize = 16 * 1024 * 1024;
  if (!compressed_size || !uncompressed_size ||
      compressed_size > kMaximumShaderEntrySize ||
      uncompressed_size > kMaximumShaderEntrySize) {
    std::cerr << "archive shader entry is outside the supported size range\n";
    return 2;
  }
  std::ifstream input(argv[1], std::ios::binary);
  std::vector<uint8_t> compressed(compressed_size);
  input.seekg(static_cast<std::streamoff>(offset));
  if (!input.read(reinterpret_cast<char*>(compressed.data()), compressed.size())) {
    std::cerr << "unable to read compressed archive entry\n";
    return 1;
  }

  const auto decompressed = DecompressXmem(compressed, uncompressed_size);
  if (!decompressed) {
    std::cerr << "XMem LZX decompression failed\n";
    return 1;
  }
  const std::vector<uint8_t>& output = *decompressed;

  const std::filesystem::path output_path(argv[5]);
  std::error_code error;
  if (!output_path.parent_path().empty()) {
    std::filesystem::create_directories(output_path.parent_path(), error);
  }
  if (error) {
    std::cerr << "unable to create output directory\n";
    return 1;
  }
  std::ofstream output_file(output_path, std::ios::binary | std::ios::trunc);
  output_file.write(reinterpret_cast<const char*>(output.data()), output.size());
  return output_file ? 0 : 1;
}
