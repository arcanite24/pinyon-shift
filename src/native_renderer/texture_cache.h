#pragma once

#include <array>
#include <cstdint>
#include <mutex>
#include <optional>
#include <span>
#include <vector>

#include "native_renderer/resource_identity.h"

namespace pinyon_shift::native_renderer {

constexpr uint32_t kXenosTextureFormatDxn = 49;

struct NativeTextureDescriptor {
  uint32_t format = 0;
  uint32_t endianness = 0;
  uint32_t dimension = 0;
  uint32_t width = 0;
  uint32_t height = 0;
  uint32_t depth = 0;
  uint32_t pitch = 0;
  uint32_t mip_min_level = 0;
  uint32_t mip_max_level = 0;
  bool tiled = false;
  bool packed_mips = false;

  static std::optional<NativeTextureDescriptor> FromFetchWords(
      const std::array<uint32_t, 6>& words);

  bool operator==(const NativeTextureDescriptor&) const = default;
};

using NativeTextureHandle = uint64_t;

enum class TextureRequestState : uint8_t {
  kReady,
  kDecodeRequired,
  kRetryPending,
  kPermanentFailure,
};

struct TextureCacheRequest {
  TextureRequestState state = TextureRequestState::kRetryPending;
  uint64_t decode_ticket = 0;
  NativeTextureHandle sampled_handle = 0;
  uint32_t attempt = 0;
  bool serving_previous = false;
};

enum class TextureDecodeResult : uint8_t {
  kReady,
  kIncompletePayload,
  kPermanentFailure,
};

struct TextureRetryPolicy {
  uint32_t maximum_attempts = 4;
  uint32_t base_delay_frames = 2;
  uint32_t maximum_delay_frames = 32;
};

struct RetiredTexture {
  NativeTextureHandle handle = 0;
  uint64_t allocation_bytes = 0;
  uint64_t retire_after_submission = 0;
};

struct TextureCacheMetrics {
  uint64_t hits = 0;
  uint64_t misses = 0;
  uint64_t decode_requests = 0;
  uint64_t incomplete_payloads = 0;
  uint64_t retries = 0;
  uint64_t permanent_failures = 0;
  uint64_t invalidations = 0;
  uint64_t live_count = 0;
  uint64_t live_bytes = 0;
  uint64_t retired_count = 0;
  uint64_t retired_bytes = 0;
};

// Backend-neutral texture decode and lifetime state. Decode work is requested
// by ticket and committed later; incomplete streaming data uses bounded
// exponential backoff while the previous generation (or handle zero as the
// neutral fallback) remains sampleable.
class NativeTextureCache {
 public:
  explicit NativeTextureCache(PhysicalResourceTracker& tracker,
                              TextureRetryPolicy retry_policy = {});

  [[nodiscard]] TextureCacheRequest Request(const TextureResourceKey& key,
                                            uint64_t frame,
                                            uint64_t submission);
  bool Complete(uint64_t decode_ticket, TextureDecodeResult result,
                NativeTextureHandle handle, uint64_t allocation_bytes,
                uint64_t frame, uint64_t submission);

  size_t RetireInvalidated(
      std::span<const ResourceInvalidation> invalidations,
      const PhysicalRange& written_range, uint64_t current_submission);
  size_t RetireAll(uint64_t current_submission);

  [[nodiscard]] std::vector<RetiredTexture> Collect(
      uint64_t completed_submission);
  [[nodiscard]] TextureCacheMetrics metrics() const;

 private:
  struct LiveTexture {
    TextureResourceKey key;
    uint64_t resource_id = 0;
    NativeTextureHandle handle = 0;
    uint64_t allocation_bytes = 0;
    uint64_t last_use_frame = 0;
    uint64_t last_use_submission = 0;
  };

  struct Slot {
    PhysicalRange base;
    std::optional<PhysicalRange> mips;
    uint64_t fetch_signature = 0;
    std::optional<LiveTexture> live;
    std::optional<TextureResourceKey> pending;
    uint64_t decode_ticket = 0;
    uint64_t next_retry_frame = 0;
    uint32_t attempt = 0;
    bool decode_in_flight = false;
    bool permanent_failure = false;
  };

  [[nodiscard]] Slot* FindSlotLocked(const TextureResourceKey& key);
  void RetireLiveLocked(Slot& slot, uint64_t current_submission);
  [[nodiscard]] uint64_t RetryDelay(uint32_t attempt) const;

  PhysicalResourceTracker& tracker_;
  TextureRetryPolicy retry_policy_;
  mutable std::mutex mutex_;
  std::vector<Slot> slots_;
  std::vector<RetiredTexture> retired_;
  TextureCacheMetrics metrics_;
  uint64_t next_resource_id_ = 1;
  uint64_t next_decode_ticket_ = 1;
};

}  // namespace pinyon_shift::native_renderer
