#ifndef PINYON_SHIFT_NATIVE_RENDERER_RESOLVE_ASSEMBLY_TRACKER_H_
#define PINYON_SHIFT_NATIVE_RENDERER_RESOLVE_ASSEMBLY_TRACKER_H_

#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>

namespace pinyon_shift::native_renderer {

uint32_t XenosColorBytesPerPixel(uint32_t format);

struct ProceduralResolveTarget {
  uint64_t frame_sequence = 0;
  uint32_t surface_info = 0;
  uint32_t color_info = 0;
  uint32_t logical_width = 0;
  uint32_t logical_height = 0;

  bool valid() const {
    return frame_sequence && logical_width && logical_height;
  }
};

struct ProceduralResolveCopy {
  uint64_t frame_sequence = 0;
  uint32_t source = 0;
  uint32_t source_surface_info = 0;
  uint32_t source_info = 0;
  uint32_t destination_info = 0;
  uint32_t destination_pitch = 0;
  uint32_t written_address = 0;
  uint32_t written_length = 0;
};

struct ProceduralResolveAssembly {
  static constexpr size_t kMaximumChunks = 8;

  uint64_t frame_sequence = 0;
  uint32_t source = 0;
  uint32_t source_surface_info = 0;
  uint32_t source_info = 0;
  uint32_t destination_info = 0;
  uint32_t destination_pitch = 0;
  uint32_t base_address = 0;
  uint32_t logical_width = 0;
  uint32_t logical_height = 0;
  uint32_t padded_height = 0;
  uint32_t bytes_per_pixel = 0;
  uint64_t total_bytes = 0;
  uint32_t chunk_count = 0;
  std::array<uint32_t, kMaximumChunks> addresses{};
  std::array<uint32_t, kMaximumChunks> lengths{};
  bool exact_contiguous_full_frame = false;
  bool copy_overflow = false;
};

class ProceduralResolveAssemblyTracker {
 public:
  static constexpr size_t kMaximumCopiesPerFrame = 64;

  std::optional<ProceduralResolveAssembly> Arm(
      const ProceduralResolveTarget& target);
  std::optional<ProceduralResolveAssembly> Observe(
      const ProceduralResolveCopy& copy);
  std::optional<ProceduralResolveAssembly> Flush();
  const std::optional<ProceduralResolveAssembly>& latest_qualified() const {
    return latest_qualified_;
  }

 private:
  std::optional<ProceduralResolveAssembly> Advance(uint64_t frame_sequence);
  std::optional<ProceduralResolveAssembly> Finalize();
  void Reset(uint64_t frame_sequence);

  uint64_t frame_sequence_ = 0;
  ProceduralResolveTarget target_{};
  std::array<ProceduralResolveCopy, kMaximumCopiesPerFrame> copies_{};
  size_t copy_count_ = 0;
  bool copy_overflow_ = false;
  bool target_conflict_ = false;
  std::optional<ProceduralResolveAssembly> latest_qualified_;
};

}  // namespace pinyon_shift::native_renderer

#endif  // PINYON_SHIFT_NATIVE_RENDERER_RESOLVE_ASSEMBLY_TRACKER_H_
