#pragma once

#include <algorithm>
#include <cstddef>
#include <cstdint>

namespace pinyon_shift::native_renderer {

// Cache limits are intentionally expressed in backend-neutral resource bytes
// and logical entries. Retired allocations remain separately visible in cache
// telemetry until their final GPU submission completes.
struct NativeResourceCacheBudget {
  uint64_t maximum_live_bytes = 256 * 1024 * 1024;
  size_t maximum_live_count = 4096;
  size_t maximum_state_count = 8192;
  size_t maximum_evictions_per_maintenance = 16;
  uint64_t normal_idle_frames = 600;
  uint64_t pressure_idle_frames = 60;

  void Normalize() {
    maximum_live_bytes = std::max(maximum_live_bytes, uint64_t(1));
    maximum_live_count = std::max(maximum_live_count, size_t(1));
    maximum_state_count = std::max(maximum_state_count, maximum_live_count);
    maximum_evictions_per_maintenance = std::max(maximum_evictions_per_maintenance, size_t(1));
    normal_idle_frames = std::max(normal_idle_frames, uint64_t(1));
    pressure_idle_frames = std::clamp(pressure_idle_frames, uint64_t(1), normal_idle_frames);
  }
};

[[nodiscard]] inline bool IsIdleFor(uint64_t current_frame, uint64_t last_use_frame,
                                    uint64_t idle_frames) {
  return current_frame >= last_use_frame && current_frame - last_use_frame >= idle_frames;
}

}  // namespace pinyon_shift::native_renderer
