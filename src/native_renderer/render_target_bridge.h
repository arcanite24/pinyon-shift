#pragma once

#include <cstddef>
#include <cstdint>
#include <mutex>
#include <optional>
#include <vector>

#include "native_renderer/resource_identity.h"

namespace pinyon_shift::native_renderer {

using NativeRenderTargetHandle = uint64_t;

enum class NativeRenderTargetUsage : uint32_t {
  kColor = 1u << 0,
  kDepth = 1u << 1,
  kShaderResource = 1u << 2,
  kUnorderedAccess = 1u << 3,
};

[[nodiscard]] constexpr uint32_t RenderTargetUsageBits(
    NativeRenderTargetUsage usage) {
  return static_cast<uint32_t>(usage);
}

[[nodiscard]] constexpr NativeRenderTargetUsage operator|(
    NativeRenderTargetUsage left, NativeRenderTargetUsage right) {
  return static_cast<NativeRenderTargetUsage>(RenderTargetUsageBits(left) |
                                              RenderTargetUsageBits(right));
}

struct NativeRenderTargetKey {
  uint32_t host_format = 0;
  uint32_t width = 0;
  uint32_t height = 0;
  uint32_t sample_count = 0;
  NativeRenderTargetUsage usage = NativeRenderTargetUsage::kColor;

  [[nodiscard]] bool valid() const;
  bool operator==(const NativeRenderTargetKey &) const = default;
};

struct NativeRenderTargetKeyHash {
  [[nodiscard]] size_t operator()(const NativeRenderTargetKey &key) const;
};

struct NativeRenderTargetAcquireResult {
  NativeRenderTargetHandle handle = 0;
  bool hit = false;
};

struct NativeResolveRegion {
  PhysicalRange guest_destination;
  uint32_t source_x = 0;
  uint32_t source_y = 0;
  uint32_t width = 0;
  uint32_t height = 0;
  uint32_t row_pitch_bytes = 0;
  uint32_t mip_level = 0;
  uint32_t array_slice = 0;

  [[nodiscard]] bool valid_for(const NativeRenderTargetKey &key) const;
  bool operator==(const NativeResolveRegion &) const = default;
};

enum class NativeProducerLookupState : uint8_t {
  kGuestDecodeAllowed,
  kNativeProducer,
  kBridgeRequired,
};

struct NativeProducerRequest {
  PhysicalRange guest_source;
  uint32_t host_format = 0;
  uint32_t width = 0;
  uint32_t height = 0;
};

struct NativeProducerLookup {
  NativeProducerLookupState state =
      NativeProducerLookupState::kGuestDecodeAllowed;
  NativeRenderTargetHandle handle = 0;
  NativeRenderTargetKey key;
  NativeResolveRegion region;
  uint64_t producer_submission = 0;
};

struct RetiredRenderTarget {
  NativeRenderTargetHandle handle = 0;
  uint64_t allocation_bytes = 0;
  uint64_t retire_after_submission = 0;
};

struct RenderTargetBridgeMetrics {
  uint64_t pool_hits = 0;
  uint64_t pool_misses = 0;
  uint64_t bridge_hits = 0;
  uint64_t bridge_refusals = 0;
  uint64_t resolve_publications = 0;
  uint64_t gpu_output_records = 0;
  uint64_t known_output_overflows = 0;
  uint64_t guest_invalidations = 0;
  uint64_t live_count = 0;
  uint64_t live_bytes = 0;
  uint64_t retired_count = 0;
  uint64_t retired_bytes = 0;
};

// Backend-neutral render-target pool and resolve provenance bridge. A target is
// reusable only when it is checked in, no guest resolve mapping pins it, and
// every submission that referenced it has completed. Known GPU-produced ranges
// never fall through to guest-memory decode when their producer is stale or
// incompatible.
class NativeRenderTargetBridge {
 public:
  static constexpr size_t kKnownGpuOutputLimit = 4096;

  // candidate_handle and allocation_bytes are consumed only on a pool miss.
  // The backend retains ownership of an unused candidate supplied on a hit.
  [[nodiscard]] std::optional<NativeRenderTargetAcquireResult> Acquire(
      const NativeRenderTargetKey &key,
      NativeRenderTargetHandle candidate_handle, uint64_t allocation_bytes,
      uint64_t frame, uint64_t current_submission,
      uint64_t completed_submission);

  // Imports an exact backend-owned allocation. Re-observing the same handle
  // may check it out again even while an existing mapping pins it because this
  // is continued use of that allocation, never pool alias reuse. The caller
  // retains the backend resource only when this returns a miss.
  [[nodiscard]] std::optional<NativeRenderTargetAcquireResult> ImportObserved(
      const NativeRenderTargetKey &key,
      NativeRenderTargetHandle observed_handle, uint64_t allocation_bytes,
      uint64_t frame, uint64_t current_submission);

  bool Release(NativeRenderTargetHandle handle, uint64_t current_submission);

  // Publishes a single-sample, shader-readable native producer for the exact
  // guest resolve destination. Re-publishing an overlapping destination
  // supersedes and unpins the older producer mapping.
  bool PublishResolve(NativeRenderTargetHandle handle,
                      const NativeResolveRegion &region,
                      uint64_t producer_submission);

  // Records a successful GPU write before its concrete sampled allocation is
  // observed. Any older overlapping producer becomes stale immediately.
  bool RecordGpuOutput(const PhysicalRange &range,
                       uint64_t producer_submission);

  [[nodiscard]] NativeProducerLookup LookupProducer(
      const NativeProducerRequest &request, uint64_t frame,
      uint64_t current_submission);

  // A guest write replaces GPU provenance for every overlapping destination.
  // The target remains pooled, but the written range may be decoded normally.
  size_t InvalidateGuestWrite(const PhysicalRange &written_range,
                              uint64_t current_submission);

  bool Retire(NativeRenderTargetHandle handle, uint64_t current_submission);
  size_t RetireAll(uint64_t current_submission);

  [[nodiscard]] std::vector<RetiredRenderTarget> Collect(
      uint64_t completed_submission);
  [[nodiscard]] RenderTargetBridgeMetrics metrics() const;

 private:
  struct TargetEntry {
    NativeRenderTargetKey key;
    NativeRenderTargetHandle handle = 0;
    uint64_t allocation_bytes = 0;
    uint64_t last_use_frame = 0;
    uint64_t last_use_submission = 0;
    uint64_t available_after_submission = 0;
    uint64_t mapping_pins = 0;
    bool checked_out = false;
  };

  struct ResolveMapping {
    NativeResolveRegion region;
    NativeRenderTargetHandle handle = 0;
    uint64_t producer_submission = 0;
  };

  [[nodiscard]] TargetEntry *FindTargetLocked(NativeRenderTargetHandle handle);
  void RemoveMappingsForHandleLocked(NativeRenderTargetHandle handle,
                                     bool preserve_known_output);
  void RemoveMappingLocked(size_t mapping_index);
  bool RememberKnownOutputLocked(const PhysicalRange &range);
  void ForgetKnownOutputLocked(const PhysicalRange &range);

  mutable std::mutex mutex_;
  std::vector<TargetEntry> targets_;
  std::vector<ResolveMapping> mappings_;
  std::vector<PhysicalRange> known_gpu_outputs_;
  bool known_output_overflow_ = false;
  std::vector<RetiredRenderTarget> retired_;
  RenderTargetBridgeMetrics metrics_;
};

}  // namespace pinyon_shift::native_renderer
