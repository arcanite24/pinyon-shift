#include "native_renderer/shader_capture.h"

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <limits>
#include <mutex>
#include <span>
#include <string>
#include <vector>

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <Windows.h>
#include <bcrypt.h>

#include <fmt/format.h>
#include <rex/system/interfaces/graphics.h>

#include "pinyon_shift_diagnostics.h"

namespace {

constexpr size_t kMaximumEntries = 256;
constexpr size_t kMaximumBytecodeBytes = 16 * 1024 * 1024;
constexpr size_t kMaximumCaptureBytes = 128 * 1024 * 1024;

struct CaptureEntry {
  rex::system::GraphicsShaderStage stage{};
  uint64_t guest_hash = 0;
  uint64_t specialization_mask = 0;
  size_t bytecode_size = 0;
  std::array<std::byte, 32> digest{};
  std::string file_name;
};

struct CaptureState {
  std::mutex mutex;
  std::filesystem::path root;
  std::vector<CaptureEntry> entries;
  size_t bytecode_bytes = 0;
  size_t duplicate_callbacks = 0;
  size_t rejected_callbacks = 0;
  bool active = false;
};

CaptureState g_capture;

bool ComputeSha256(std::span<const std::byte> source,
                   std::array<std::byte, 32> *digest) {
  if (!digest || source.size() > std::numeric_limits<ULONG>::max()) {
    return false;
  }
  BCRYPT_ALG_HANDLE algorithm = nullptr;
  BCRYPT_HASH_HANDLE hash = nullptr;
  DWORD object_size = 0;
  DWORD returned_size = 0;
  std::vector<UCHAR> object;
  bool succeeded = false;
  if (!BCRYPT_SUCCESS(BCryptOpenAlgorithmProvider(
          &algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0)) ||
      !BCRYPT_SUCCESS(BCryptGetProperty(algorithm, BCRYPT_OBJECT_LENGTH,
                                        reinterpret_cast<PUCHAR>(&object_size),
                                        sizeof(object_size), &returned_size,
                                        0))) {
    goto cleanup;
  }
  object.resize(object_size);
  if (!BCRYPT_SUCCESS(BCryptCreateHash(algorithm, &hash, object.data(),
                                       object_size, nullptr, 0, 0)) ||
      !BCRYPT_SUCCESS(BCryptHashData(
          hash,
          const_cast<PUCHAR>(reinterpret_cast<const UCHAR *>(source.data())),
          static_cast<ULONG>(source.size()), 0)) ||
      !BCRYPT_SUCCESS(
          BCryptFinishHash(hash, reinterpret_cast<PUCHAR>(digest->data()),
                           static_cast<ULONG>(digest->size()), 0))) {
    goto cleanup;
  }
  succeeded = true;

cleanup:
  if (hash) {
    BCryptDestroyHash(hash);
  }
  if (algorithm) {
    BCryptCloseAlgorithmProvider(algorithm, 0);
  }
  return succeeded;
}

std::string DigestHex(const std::array<std::byte, 32> &digest) {
  std::string result;
  result.reserve(digest.size() * 2);
  for (std::byte value : digest) {
    fmt::format_to(std::back_inserter(result), "{:02x}",
                   std::to_integer<uint8_t>(value));
  }
  return result;
}

bool IsCaptureRoot(const std::filesystem::path &path) {
  if (!path.is_absolute()) {
    return false;
  }
  return std::any_of(path.begin(), path.end(), [](const auto &component) {
    return component.native() == L".local";
  });
}

bool ReplaceFile(const std::filesystem::path &temporary,
                 const std::filesystem::path &destination) {
  return MoveFileExW(temporary.c_str(), destination.c_str(),
                     MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) != 0;
}

bool WriteFileAtomically(const std::filesystem::path &destination,
                         std::span<const std::byte> bytes) {
  std::filesystem::path temporary = destination;
  temporary += L".tmp";
  std::error_code error;
  std::filesystem::remove(temporary, error);
  std::ofstream output(temporary, std::ios::binary | std::ios::trunc);
  if (!output.write(reinterpret_cast<const char *>(bytes.data()),
                    static_cast<std::streamsize>(bytes.size())) ||
      !output.flush()) {
    output.close();
    std::filesystem::remove(temporary, error);
    return false;
  }
  output.close();
  if (!ReplaceFile(temporary, destination)) {
    std::filesystem::remove(temporary, error);
    return false;
  }
  return true;
}

bool ExistingFileMatches(const std::filesystem::path &path,
                         std::span<const std::byte> expected) {
  std::error_code error;
  if (std::filesystem::file_size(path, error) != expected.size() || error) {
    return false;
  }
  std::vector<std::byte> actual(expected.size());
  std::ifstream input(path, std::ios::binary);
  return input.read(reinterpret_cast<char *>(actual.data()),
                    static_cast<std::streamsize>(actual.size())) &&
         input.peek() == std::char_traits<char>::eof() &&
         std::equal(actual.begin(), actual.end(), expected.begin());
}

bool WriteManifestLocked(const CaptureEntry &pending) {
  std::vector<CaptureEntry> entries = g_capture.entries;
  entries.push_back(pending);
  std::sort(entries.begin(), entries.end(),
            [](const auto &left, const auto &right) {
              if (left.stage != right.stage) {
                return left.stage < right.stage;
              }
              if (left.guest_hash != right.guest_hash) {
                return left.guest_hash < right.guest_hash;
              }
              return left.specialization_mask < right.specialization_mask;
            });

  std::string document =
      "{\n  \"schema\": \"pinyon-shift.native-shader-pack.v1\",\n"
      "  \"backend\": \"d3d12\",\n  \"entries\": [\n";
  for (size_t index = 0; index < entries.size(); ++index) {
    const CaptureEntry &entry = entries[index];
    const char *stage = entry.stage == rex::system::GraphicsShaderStage::kVertex
                            ? "vertex"
                            : "pixel";
    document += fmt::format("    {{\n      \"stage\": \"{}\",\n"
                            "      \"guest_hash\": \"{:016X}\",\n"
                            "      \"specialization_mask\": \"{:016X}\",\n"
                            "      \"bytecode\": \"dxil/{}\",\n"
                            "      \"sha256\": \"{}\"\n    }}{}\n",
                            stage, entry.guest_hash, entry.specialization_mask,
                            entry.file_name, DigestHex(entry.digest),
                            index + 1 == entries.size() ? "" : ",");
  }
  document += "  ]\n}\n";
  return WriteFileAtomically(
      g_capture.root / L"shader-manifest.json",
      std::as_bytes(std::span<const char>(document.data(), document.size())));
}

void ObserveShaderTranslation(
    const rex::system::GraphicsShaderTranslationObservation &observation) {
  const auto bytecode =
      std::as_bytes(std::span(observation.bytecode, observation.bytecode_size));
  std::lock_guard lock(g_capture.mutex);
  if (!g_capture.active) {
    return;
  }
  if ((observation.stage != rex::system::GraphicsShaderStage::kVertex &&
       observation.stage != rex::system::GraphicsShaderStage::kPixel) ||
      observation.guest_hash == 0 || bytecode.size() < 4 ||
      bytecode.size() > kMaximumBytecodeBytes ||
      std::memcmp(bytecode.data(), "DXBC", 4) != 0) {
    ++g_capture.rejected_callbacks;
    return;
  }

  auto existing = std::find_if(
      g_capture.entries.begin(), g_capture.entries.end(),
      [&](const CaptureEntry &entry) {
        return entry.stage == observation.stage &&
               entry.guest_hash == observation.guest_hash &&
               entry.specialization_mask == observation.specialization_mask;
      });
  if (existing != g_capture.entries.end()) {
    ++g_capture.duplicate_callbacks;
    return;
  }
  if (g_capture.entries.size() >= kMaximumEntries ||
      bytecode.size() > kMaximumCaptureBytes - g_capture.bytecode_bytes) {
    ++g_capture.rejected_callbacks;
    return;
  }

  CaptureEntry entry;
  entry.stage = observation.stage;
  entry.guest_hash = observation.guest_hash;
  entry.specialization_mask = observation.specialization_mask;
  entry.bytecode_size = bytecode.size();
  if (!ComputeSha256(bytecode, &entry.digest)) {
    ++g_capture.rejected_callbacks;
    return;
  }
  entry.file_name = fmt::format(
      "{}_{:016X}_{:016X}.dxil",
      entry.stage == rex::system::GraphicsShaderStage::kVertex ? "vertex"
                                                               : "pixel",
      entry.guest_hash, entry.specialization_mask);
  const std::filesystem::path destination =
      g_capture.root / L"dxil" / entry.file_name;
  std::error_code error;
  if (std::filesystem::exists(destination, error)) {
    if (error || !ExistingFileMatches(destination, bytecode)) {
      ++g_capture.rejected_callbacks;
      return;
    }
  } else if (!WriteFileAtomically(destination, bytecode)) {
    ++g_capture.rejected_callbacks;
    return;
  }
  if (!WriteManifestLocked(entry)) {
    ++g_capture.rejected_callbacks;
    return;
  }
  g_capture.bytecode_bytes += bytecode.size();
  g_capture.entries.push_back(std::move(entry));
}

} // namespace

namespace pinyon_shift::native_renderer {

void InstallShaderCapture(rex::system::IGraphicsSystem *graphics_system) {
  char *raw_path = nullptr;
  size_t raw_path_length = 0;
  if (_dupenv_s(&raw_path, &raw_path_length,
                "PINYON_SHIFT_NATIVE_SHADER_CAPTURE_DIR") != 0 ||
      !raw_path || raw_path_length <= 1) {
    std::free(raw_path);
    return;
  }
  const std::filesystem::path root =
      std::filesystem::absolute(std::filesystem::path(raw_path))
          .lexically_normal();
  std::free(raw_path);
  if (!graphics_system || !IsCaptureRoot(root)) {
    diagnostics::RecordEvent(
        "native_renderer.shader_capture.failure",
        {{"reason", "invalid_local_root"}, {"fallback", "xenos"}});
    return;
  }
  std::error_code error;
  std::filesystem::create_directories(root / L"dxil", error);
  if (error) {
    diagnostics::RecordEvent(
        "native_renderer.shader_capture.failure",
        {{"reason", "create_directory_failed"}, {"fallback", "xenos"}});
    return;
  }
  {
    std::lock_guard lock(g_capture.mutex);
    g_capture.root = root;
    g_capture.entries.clear();
    g_capture.bytecode_bytes = 0;
    g_capture.duplicate_callbacks = 0;
    g_capture.rejected_callbacks = 0;
    g_capture.active = true;
  }
  graphics_system->SetShaderTranslationObserver(&ObserveShaderTranslation);
  diagnostics::RecordEvent("native_renderer.shader_capture.installed",
                           {{"entry_limit", "256"},
                            {"byte_limit", "134217728"},
                            {"output", "local_only"},
                            {"mode", "pass_through"}});
}

void UninstallShaderCapture(rex::system::IGraphicsSystem *graphics_system) {
  if (graphics_system) {
    graphics_system->SetShaderTranslationObserver(nullptr);
  }
  size_t entries = 0;
  size_t bytes = 0;
  size_t duplicates = 0;
  size_t rejected = 0;
  {
    std::lock_guard lock(g_capture.mutex);
    if (!g_capture.active) {
      return;
    }
    g_capture.active = false;
    entries = g_capture.entries.size();
    bytes = g_capture.bytecode_bytes;
    duplicates = g_capture.duplicate_callbacks;
    rejected = g_capture.rejected_callbacks;
  }
  diagnostics::RecordEvent("native_renderer.shader_capture.summary",
                           {{"entries", std::to_string(entries)},
                            {"bytes", std::to_string(bytes)},
                            {"duplicate_callbacks", std::to_string(duplicates)},
                            {"rejected_callbacks", std::to_string(rejected)},
                            {"output", "local_only"},
                            {"mode", "pass_through"}});
}

} // namespace pinyon_shift::native_renderer
