#include "native_renderer/shader_pack.h"

#include <algorithm>
#include <array>
#include <cstring>
#include <exception>
#include <fstream>
#include <limits>
#include <type_traits>
#include <utility>

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

#include <bcrypt.h>
#endif

namespace pinyon_shift::native_renderer {
namespace {

constexpr std::array<std::byte, 8> kMagic{std::byte{'P'}, std::byte{'N'}, std::byte{'Y'},
                                          std::byte{'N'}, std::byte{'S'}, std::byte{'H'},
                                          std::byte{'P'}, std::byte{'K'}};
constexpr uint32_t kVersion = 1;
constexpr uint32_t kHeaderSize = 80;
constexpr uint32_t kEntrySize = 68;
constexpr uint8_t kDxilFormat = 1;
constexpr uint32_t kMaximumEntryCount = 65'535;
constexpr uint64_t kMaximumBytecodeSize = 16 * 1024 * 1024;
constexpr uint64_t kMaximumPackSize = 512 * 1024 * 1024;

void SetError(std::string* error, std::string message) {
  if (error) {
    *error = std::move(message);
  }
}

template <typename T>
bool ReadLittle(std::span<const std::byte> source, size_t offset, T* value) {
  static_assert(std::is_unsigned_v<T>);
  if (!value || offset > source.size() || source.size() - offset < sizeof(T)) {
    return false;
  }
  T result = 0;
  for (size_t index = 0; index < sizeof(T); ++index) {
    result |= T(std::to_integer<uint8_t>(source[offset + index])) << (index * 8);
  }
  *value = result;
  return true;
}

bool CheckedAdd(uint64_t left, uint64_t right, uint64_t* result) {
  if (!result || right > std::numeric_limits<uint64_t>::max() - left) {
    return false;
  }
  *result = left + right;
  return true;
}

bool CheckedMultiply(uint64_t left, uint64_t right, uint64_t* result) {
  if (!result || (left && right > std::numeric_limits<uint64_t>::max() / left)) {
    return false;
  }
  *result = left * right;
  return true;
}

bool ComputeSha256(std::span<const std::byte> source, std::array<std::byte, 32>* digest) {
#ifdef _WIN32
  if (!digest || source.size() > std::numeric_limits<ULONG>::max()) {
    return false;
  }
  BCRYPT_ALG_HANDLE algorithm = nullptr;
  BCRYPT_HASH_HANDLE hash = nullptr;
  DWORD object_size = 0;
  DWORD returned_size = 0;
  std::vector<UCHAR> object;
  bool succeeded = false;
  if (!BCRYPT_SUCCESS(
          BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0)) ||
      !BCRYPT_SUCCESS(BCryptGetProperty(algorithm, BCRYPT_OBJECT_LENGTH,
                                        reinterpret_cast<PUCHAR>(&object_size), sizeof(object_size),
                                        &returned_size, 0))) {
    goto cleanup;
  }
  object.resize(object_size);
  if (!BCRYPT_SUCCESS(
          BCryptCreateHash(algorithm, &hash, object.data(), object_size, nullptr, 0, 0)) ||
      !BCRYPT_SUCCESS(
          BCryptHashData(hash, const_cast<PUCHAR>(reinterpret_cast<const UCHAR*>(source.data())),
                         static_cast<ULONG>(source.size()), 0)) ||
      !BCRYPT_SUCCESS(BCryptFinishHash(hash, reinterpret_cast<PUCHAR>(digest->data()),
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
#else
  (void)source;
  (void)digest;
  return false;
#endif
}

bool EqualBytes(std::span<const std::byte> left, std::span<const std::byte> right) {
  return left.size() == right.size() && std::equal(left.begin(), left.end(), right.begin());
}

}  // namespace

bool ShaderPack::Load(const std::filesystem::path& path, std::string* error) {
  Reset();
  if (error) {
    error->clear();
  }
  try {
    std::error_code file_error;
    const uint64_t file_size = std::filesystem::file_size(path, file_error);
    if (file_error || file_size < kHeaderSize || file_size > kMaximumPackSize ||
        file_size > std::numeric_limits<size_t>::max()) {
      SetError(error, "shader pack size is outside the supported range");
      return false;
    }
    std::vector<std::byte> file_data(static_cast<size_t>(file_size));
    std::ifstream stream(path, std::ios::binary);
    if (!stream.read(reinterpret_cast<char*>(file_data.data()),
                     static_cast<std::streamsize>(file_data.size())) ||
        stream.peek() != std::char_traits<char>::eof()) {
      SetError(error, "shader pack could not be read completely");
      return false;
    }
    const std::span<const std::byte> bytes(file_data);
    if (!EqualBytes(bytes.first(kMagic.size()), kMagic)) {
      SetError(error, "shader pack magic is invalid");
      return false;
    }

    uint32_t version = 0;
    uint32_t header_size = 0;
    uint32_t entry_size = 0;
    uint32_t entry_count = 0;
    uint64_t index_offset = 0;
    uint64_t data_offset = 0;
    uint64_t data_size = 0;
    if (!ReadLittle(bytes, 8, &version) || !ReadLittle(bytes, 12, &header_size) ||
        !ReadLittle(bytes, 16, &entry_size) || !ReadLittle(bytes, 20, &entry_count) ||
        !ReadLittle(bytes, 24, &index_offset) || !ReadLittle(bytes, 32, &data_offset) ||
        !ReadLittle(bytes, 40, &data_size) || version != kVersion || header_size != kHeaderSize ||
        entry_size != kEntrySize || entry_count == 0 || entry_count > kMaximumEntryCount ||
        index_offset != kHeaderSize) {
      SetError(error, "shader pack header is unsupported or invalid");
      return false;
    }

    uint64_t index_size = 0;
    uint64_t expected_data_offset = 0;
    uint64_t expected_file_size = 0;
    if (!CheckedMultiply(entry_count, entry_size, &index_size) ||
        !CheckedAdd(index_offset, index_size, &expected_data_offset) ||
        !CheckedAdd(data_offset, data_size, &expected_file_size) ||
        data_offset != expected_data_offset || expected_file_size != file_size) {
      SetError(error, "shader pack index or payload range is invalid");
      return false;
    }

    std::array<std::byte, 32> content_digest{};
    if (!ComputeSha256(bytes.subspan(static_cast<size_t>(index_offset)), &content_digest)) {
      SetError(error, "shader pack SHA-256 computation failed");
      return false;
    }
    if (!EqualBytes(content_digest, bytes.subspan(48, content_digest.size()))) {
      SetError(error, "shader pack content SHA-256 does not match");
      return false;
    }

    std::vector<Entry> entries;
    entries.reserve(entry_count);
    uint64_t previous_payload_end = 0;
    for (uint32_t index = 0; index < entry_count; ++index) {
      const size_t entry_offset = static_cast<size_t>(index_offset + uint64_t(index) * entry_size);
      const uint8_t stage_value = std::to_integer<uint8_t>(bytes[entry_offset]);
      const uint8_t bytecode_format = std::to_integer<uint8_t>(bytes[entry_offset + 1]);
      uint16_t reserved = 0;
      uint64_t guest_hash = 0;
      uint64_t specialization_mask = 0;
      uint64_t payload_offset = 0;
      uint64_t payload_size = 0;
      if (!ReadLittle(bytes, entry_offset + 2, &reserved) ||
          !ReadLittle(bytes, entry_offset + 4, &guest_hash) ||
          !ReadLittle(bytes, entry_offset + 12, &specialization_mask) ||
          !ReadLittle(bytes, entry_offset + 20, &payload_offset) ||
          !ReadLittle(bytes, entry_offset + 28, &payload_size) || reserved != 0 ||
          (stage_value != uint8_t(ShaderStage::kVertex) &&
           stage_value != uint8_t(ShaderStage::kPixel)) ||
          bytecode_format != kDxilFormat || payload_size == 0 ||
          payload_size > kMaximumBytecodeSize || payload_offset % 16 != 0 ||
          payload_offset < previous_payload_end) {
        SetError(error, "shader pack entry identity or bounds are invalid");
        return false;
      }
      uint64_t payload_end = 0;
      uint64_t absolute_payload_offset = 0;
      if (!CheckedAdd(payload_offset, payload_size, &payload_end) || payload_end > data_size ||
          !CheckedAdd(data_offset, payload_offset, &absolute_payload_offset) ||
          absolute_payload_offset > std::numeric_limits<size_t>::max()) {
        SetError(error, "shader pack entry escapes the payload");
        return false;
      }
      const auto padding =
          bytes.subspan(static_cast<size_t>(data_offset + previous_payload_end),
                        static_cast<size_t>(payload_offset - previous_payload_end));
      if (std::any_of(padding.begin(), padding.end(),
                      [](std::byte value) { return value != std::byte{}; })) {
        SetError(error, "shader pack payload padding is not zero");
        return false;
      }
      const auto bytecode = bytes.subspan(static_cast<size_t>(absolute_payload_offset),
                                          static_cast<size_t>(payload_size));
      constexpr std::array<std::byte, 4> kDxbc{std::byte{'D'}, std::byte{'X'}, std::byte{'B'},
                                               std::byte{'C'}};
      if (bytecode.size() < kDxbc.size() || !EqualBytes(bytecode.first(kDxbc.size()), kDxbc)) {
        SetError(error, "shader pack entry is not a DXIL container");
        return false;
      }
      std::array<std::byte, 32> bytecode_digest{};
      if (!ComputeSha256(bytecode, &bytecode_digest) ||
          !EqualBytes(bytecode_digest, bytes.subspan(entry_offset + 36, bytecode_digest.size()))) {
        SetError(error, "shader pack entry SHA-256 does not match");
        return false;
      }
      const ShaderIdentity identity{static_cast<ShaderStage>(stage_value), guest_hash,
                                    specialization_mask};
      if (!entries.empty() && !(entries.back().identity < identity)) {
        SetError(error, "shader pack identities are duplicated or not sorted");
        return false;
      }
      entries.push_back({identity, absolute_payload_offset, payload_size});
      previous_payload_end = payload_end;
    }
    if (previous_payload_end != data_size) {
      SetError(error, "shader pack payload contains unreferenced trailing data");
      return false;
    }

    file_data_ = std::move(file_data);
    entries_ = std::move(entries);
    return true;
  } catch (const std::exception& exception) {
    SetError(error, std::string("shader pack load failed: ") + exception.what());
    return false;
  }
}

void ShaderPack::Reset() {
  entries_.clear();
  file_data_.clear();
}

std::span<const std::byte> ShaderPack::Find(ShaderIdentity identity) const {
  const auto entry = std::lower_bound(entries_.begin(), entries_.end(), identity,
                                      [](const Entry& candidate, const ShaderIdentity& requested) {
                                        return candidate.identity < requested;
                                      });
  if (entry == entries_.end() || entry->identity != identity ||
      entry->bytecode_offset > file_data_.size() ||
      entry->bytecode_size > file_data_.size() - entry->bytecode_offset) {
    return {};
  }
  return std::span<const std::byte>(file_data_)
      .subspan(static_cast<size_t>(entry->bytecode_offset),
               static_cast<size_t>(entry->bytecode_size));
}

}  // namespace pinyon_shift::native_renderer
