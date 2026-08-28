#pragma once

#include <compare>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <span>
#include <string>
#include <vector>

namespace pinyon_shift::native_renderer {

enum class ShaderStage : uint8_t {
  kVertex = 1,
  kPixel = 2,
};

struct ShaderIdentity {
  ShaderStage stage{};
  uint64_t guest_hash{};
  uint64_t specialization_mask{};

  auto operator<=>(const ShaderIdentity&) const = default;
};

class ShaderPack {
 public:
  bool Load(const std::filesystem::path& path, std::string* error = nullptr);
  void Reset();

  [[nodiscard]] std::span<const std::byte> Find(ShaderIdentity identity) const;
  [[nodiscard]] size_t entry_count() const { return entries_.size(); }

 private:
  struct Entry {
    ShaderIdentity identity;
    uint64_t bytecode_offset{};
    uint64_t bytecode_size{};
  };

  std::vector<std::byte> file_data_;
  std::vector<Entry> entries_;
};

}  // namespace pinyon_shift::native_renderer
