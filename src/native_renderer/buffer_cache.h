#pragma once

#include <cstdint>
#include <mutex>
#include <optional>
#include <span>
#include <unordered_map>
#include <vector>

#include "native_renderer/resource_identity.h"

namespace pinyon_shift::native_renderer {

// Backend-owned allocation identifier. Zero is never a valid allocation.
using NativeBufferHandle = uint64_t;

struct BufferCacheEntry {
  uint64_t resource_id = 0;
  BufferResourceKey key;
  NativeBufferHandle handle = 0;
  uint64_t allocation_bytes = 0;
  uint64_t last_use_frame = 0;
  uint64_t last_use_submission = 0;
};

struct BufferCacheAcquireResult {
  BufferCacheEntry entry;
  bool hit = false;
};

struct RetiredBuffer {
  NativeBufferHandle handle = 0;
  uint64_t allocation_bytes = 0;
  uint64_t retire_after_submission = 0;
};

struct BufferCacheMetrics {
  uint64_t hits = 0;
  uint64_t misses = 0;
  uint64_t invalidations = 0;
  uint64_t live_count = 0;
  uint64_t live_bytes = 0;
  uint64_t retired_count = 0;
  uint64_t retired_bytes = 0;
};

// Owns buffer-cache identity and lifetime metadata. The backend creates and
// destroys the opaque handles; this class guarantees that an invalidated live
// handle is not returned for destruction until its final submission completes.
class NativeBufferCache {
 public:
  explicit NativeBufferCache(PhysicalResourceTracker& tracker);

  // A zero handle or allocation size is rejected. On a key hit the supplied
  // handle remains caller-owned and the existing allocation is returned.
  [[nodiscard]] std::optional<BufferCacheAcquireResult> Acquire(const BufferResourceKey& key,
                                                                NativeBufferHandle candidate_handle,
                                                                uint64_t allocation_bytes,
                                                                uint64_t frame,
                                                                uint64_t submission);

  [[nodiscard]] std::optional<BufferCacheEntry> Find(const BufferResourceKey& key, uint64_t frame,
                                                     uint64_t submission);

  // Consumes central tracker notifications. Buffer entries are removed from
  // lookup immediately but their handles are queued for fence-safe collection.
  size_t RetireInvalidated(std::span<const ResourceInvalidation> invalidations,
                           uint64_t current_submission);
  size_t RetireAll(uint64_t current_submission);

  [[nodiscard]] std::vector<RetiredBuffer> Collect(uint64_t completed_submission);
  [[nodiscard]] BufferCacheMetrics metrics() const;

 private:
  using LiveMap = std::unordered_map<BufferResourceKey, BufferCacheEntry, BufferResourceKeyHash>;

  void RetireLocked(LiveMap::iterator entry, uint64_t current_submission);

  PhysicalResourceTracker& tracker_;
  mutable std::mutex mutex_;
  LiveMap live_;
  std::unordered_map<uint64_t, BufferResourceKey> keys_by_id_;
  std::vector<RetiredBuffer> retired_;
  BufferCacheMetrics metrics_;
  uint64_t next_resource_id_ = 1;
};

}  // namespace pinyon_shift::native_renderer
