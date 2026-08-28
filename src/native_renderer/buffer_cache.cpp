#include "native_renderer/buffer_cache.h"

#include <algorithm>

namespace pinyon_shift::native_renderer {

NativeBufferCache::NativeBufferCache(PhysicalResourceTracker& tracker,
                                     NativeResourceCacheBudget budget)
    : tracker_(tracker), budget_(budget) {
  budget_.Normalize();
}

std::optional<BufferCacheAcquireResult> NativeBufferCache::Acquire(
    const BufferResourceKey& key, NativeBufferHandle candidate_handle, uint64_t allocation_bytes,
    uint64_t frame, uint64_t submission) {
  if (!key.range.valid() || !candidate_handle || !allocation_bytes) {
    return std::nullopt;
  }
  const std::scoped_lock lock(mutex_);
  auto existing = live_.find(key);
  if (existing != live_.end()) {
    existing->second.last_use_frame = std::max(existing->second.last_use_frame, frame);
    existing->second.last_use_submission =
        std::max(existing->second.last_use_submission, submission);
    ++metrics_.hits;
    return BufferCacheAcquireResult{existing->second, true};
  }

  ++metrics_.misses;
  if (allocation_bytes > budget_.maximum_live_bytes) {
    ++metrics_.budget_refusals;
    return std::nullopt;
  }
  if (!HasCapacityLocked(allocation_bytes)) {
    EvictLocked(frame, submission, budget_.pressure_idle_frames,
                budget_.maximum_evictions_per_maintenance, true,
                allocation_bytes);
  }
  if (!HasCapacityLocked(allocation_bytes)) {
    ++metrics_.budget_refusals;
    return std::nullopt;
  }

  const uint64_t resource_id = next_resource_id_++;
  BufferCacheEntry entry{resource_id, key, candidate_handle, allocation_bytes, frame, submission};
  live_.emplace(key, entry);
  keys_by_id_.emplace(resource_id, key);
  const TrackedResourceId tracked{TrackedResourceClass::kBuffer, resource_id};
  tracker_.Track(tracked, std::span<const PhysicalRange>(&key.range, 1));
  ++metrics_.live_count;
  metrics_.live_bytes += allocation_bytes;
  return BufferCacheAcquireResult{entry, false};
}

std::optional<BufferCacheEntry> NativeBufferCache::Find(const BufferResourceKey& key,
                                                        uint64_t frame, uint64_t submission) {
  const std::scoped_lock lock(mutex_);
  auto existing = live_.find(key);
  if (existing == live_.end()) {
    ++metrics_.misses;
    return std::nullopt;
  }
  existing->second.last_use_frame = std::max(existing->second.last_use_frame, frame);
  existing->second.last_use_submission = std::max(existing->second.last_use_submission, submission);
  ++metrics_.hits;
  return existing->second;
}

size_t NativeBufferCache::RetireInvalidated(std::span<const ResourceInvalidation> invalidations,
                                            uint64_t current_submission) {
  const std::scoped_lock lock(mutex_);
  size_t retired_count = 0;
  for (const ResourceInvalidation& invalidation : invalidations) {
    if (invalidation.resource.resource_class != TrackedResourceClass::kBuffer) {
      continue;
    }
    const auto key = keys_by_id_.find(invalidation.resource.value);
    if (key == keys_by_id_.end()) {
      continue;
    }
    auto entry = live_.find(key->second);
    if (entry == live_.end()) {
      keys_by_id_.erase(key);
      continue;
    }
    RetireLocked(entry, current_submission);
    ++retired_count;
  }
  metrics_.invalidations += retired_count;
  return retired_count;
}

size_t NativeBufferCache::RetireAll(uint64_t current_submission) {
  const std::scoped_lock lock(mutex_);
  const size_t retired_count = live_.size();
  while (!live_.empty()) {
    RetireLocked(live_.begin(), current_submission);
  }
  return retired_count;
}

size_t NativeBufferCache::Trim(uint64_t frame, uint64_t current_submission,
                               bool under_pressure) {
  const std::scoped_lock lock(mutex_);
  ++metrics_.maintenance_passes;
  return EvictLocked(
      frame, current_submission,
      under_pressure ? budget_.pressure_idle_frames
                     : budget_.normal_idle_frames,
      budget_.maximum_evictions_per_maintenance, false, 0);
}

std::vector<RetiredBuffer> NativeBufferCache::Collect(uint64_t completed_submission) {
  const std::scoped_lock lock(mutex_);
  std::vector<RetiredBuffer> ready;
  auto retained =
      std::remove_if(retired_.begin(), retired_.end(), [&](const RetiredBuffer& resource) {
        if (resource.retire_after_submission > completed_submission) {
          return false;
        }
        ready.push_back(resource);
        metrics_.retired_bytes -= resource.allocation_bytes;
        --metrics_.retired_count;
        return true;
      });
  retired_.erase(retained, retired_.end());
  return ready;
}

BufferCacheMetrics NativeBufferCache::metrics() const {
  const std::scoped_lock lock(mutex_);
  return metrics_;
}

void NativeBufferCache::RetireLocked(LiveMap::iterator entry, uint64_t current_submission) {
  const BufferCacheEntry resource = entry->second;
  retired_.push_back({resource.handle, resource.allocation_bytes,
                      std::max(resource.last_use_submission, current_submission)});
  tracker_.Untrack({TrackedResourceClass::kBuffer, resource.resource_id});
  keys_by_id_.erase(resource.resource_id);
  live_.erase(entry);
  --metrics_.live_count;
  metrics_.live_bytes -= resource.allocation_bytes;
  ++metrics_.retired_count;
  metrics_.retired_bytes += resource.allocation_bytes;
}

size_t NativeBufferCache::EvictLocked(uint64_t frame,
                                      uint64_t current_submission,
                                      uint64_t idle_frames,
                                      size_t maximum_count,
                                      bool only_until_capacity,
                                      uint64_t incoming_bytes) {
  size_t evicted = 0;
  while (evicted < maximum_count && !live_.empty() &&
         (!only_until_capacity || !HasCapacityLocked(incoming_bytes))) {
    auto oldest = live_.end();
    for (auto candidate = live_.begin(); candidate != live_.end();
         ++candidate) {
      if (!IsIdleFor(frame, candidate->second.last_use_frame, idle_frames)) {
        continue;
      }
      if (oldest == live_.end() ||
          candidate->second.last_use_frame < oldest->second.last_use_frame ||
          (candidate->second.last_use_frame == oldest->second.last_use_frame &&
           candidate->second.resource_id < oldest->second.resource_id)) {
        oldest = candidate;
      }
    }
    if (oldest == live_.end()) {
      break;
    }
    RetireLocked(oldest, current_submission);
    ++evicted;
    ++metrics_.budget_evictions;
  }
  return evicted;
}

bool NativeBufferCache::HasCapacityLocked(uint64_t incoming_bytes) const {
  return incoming_bytes <= budget_.maximum_live_bytes &&
         metrics_.live_count < budget_.maximum_live_count &&
         metrics_.live_bytes <=
             budget_.maximum_live_bytes - incoming_bytes;
}

}  // namespace pinyon_shift::native_renderer
