#include "native_renderer/texture_cache.h"

#include <algorithm>

namespace pinyon_shift::native_renderer {

std::optional<NativeTextureDescriptor> NativeTextureDescriptor::FromFetchWords(
    const std::array<uint32_t, 6>& words) {
  NativeTextureDescriptor descriptor;
  descriptor.pitch = ((words[0] >> 22) & 0x1FF) * 32;
  descriptor.tiled = (words[0] >> 31) != 0;
  descriptor.format = words[1] & 0x3F;
  descriptor.endianness = (words[1] >> 6) & 0x3;
  descriptor.width = (words[2] & 0x1FFF) + 1;
  descriptor.height = ((words[2] >> 13) & 0x1FFF) + 1;
  descriptor.depth = ((words[2] >> 26) & 0x3F) + 1;
  descriptor.mip_min_level = (words[4] >> 2) & 0xF;
  descriptor.mip_max_level = (words[4] >> 6) & 0xF;
  descriptor.dimension = (words[5] >> 9) & 0x3;
  descriptor.packed_mips = ((words[5] >> 11) & 1) != 0;
  if (!descriptor.pitch ||
      descriptor.mip_min_level > descriptor.mip_max_level) {
    return std::nullopt;
  }
  return descriptor;
}

NativeTextureCache::NativeTextureCache(PhysicalResourceTracker& tracker,
                                       TextureRetryPolicy retry_policy)
    : tracker_(tracker), retry_policy_(retry_policy) {
  retry_policy_.maximum_attempts =
      std::max(retry_policy_.maximum_attempts, uint32_t(1));
  retry_policy_.base_delay_frames =
      std::max(retry_policy_.base_delay_frames, uint32_t(1));
  retry_policy_.maximum_delay_frames = std::max(
      retry_policy_.maximum_delay_frames, retry_policy_.base_delay_frames);
}

TextureCacheRequest NativeTextureCache::Request(const TextureResourceKey& key,
                                                uint64_t frame,
                                                uint64_t submission) {
  if (!key.base.valid() || (key.mips && !key.mips->valid())) {
    return {TextureRequestState::kPermanentFailure};
  }
  const std::scoped_lock lock(mutex_);
  Slot* slot = FindSlotLocked(key);
  if (!slot) {
    slots_.push_back({key.base, key.mips, key.fetch_signature});
    slot = &slots_.back();
  }
  if (slot->live && slot->live->key == key) {
    slot->live->last_use_frame = std::max(slot->live->last_use_frame, frame);
    slot->live->last_use_submission =
        std::max(slot->live->last_use_submission, submission);
    ++metrics_.hits;
    return {TextureRequestState::kReady, 0, slot->live->handle,
            slot->attempt, false};
  }

  const bool new_content = !slot->pending || *slot->pending != key;
  if (new_content) {
    slot->pending = key;
    slot->decode_ticket = 0;
    slot->next_retry_frame = frame;
    slot->attempt = 0;
    slot->decode_in_flight = false;
    slot->permanent_failure = false;
    ++metrics_.misses;
  }
  const NativeTextureHandle fallback = slot->live ? slot->live->handle : 0;
  if (slot->permanent_failure) {
    return {TextureRequestState::kPermanentFailure, 0, fallback,
            slot->attempt, bool(slot->live)};
  }
  if (slot->decode_in_flight || frame < slot->next_retry_frame) {
    return {TextureRequestState::kRetryPending, slot->decode_ticket, fallback,
            slot->attempt, bool(slot->live)};
  }

  slot->decode_in_flight = true;
  slot->decode_ticket = next_decode_ticket_++;
  ++slot->attempt;
  ++metrics_.decode_requests;
  return {TextureRequestState::kDecodeRequired, slot->decode_ticket, fallback,
          slot->attempt, bool(slot->live)};
}

bool NativeTextureCache::Complete(uint64_t decode_ticket,
                                  TextureDecodeResult result,
                                  NativeTextureHandle handle,
                                  uint64_t allocation_bytes, uint64_t frame,
                                  uint64_t submission) {
  if (!decode_ticket) {
    return false;
  }
  const std::scoped_lock lock(mutex_);
  auto found = std::find_if(slots_.begin(), slots_.end(),
                            [&](const Slot& slot) {
                              return slot.decode_in_flight &&
                                     slot.decode_ticket == decode_ticket;
                            });
  if (found == slots_.end() || !found->pending) {
    return false;
  }
  Slot& slot = *found;
  slot.decode_in_flight = false;
  if (result == TextureDecodeResult::kIncompletePayload) {
    ++metrics_.incomplete_payloads;
    if (slot.attempt >= retry_policy_.maximum_attempts) {
      slot.permanent_failure = true;
      ++metrics_.permanent_failures;
    } else {
      slot.next_retry_frame = frame + RetryDelay(slot.attempt);
      ++metrics_.retries;
    }
    return true;
  }
  if (result == TextureDecodeResult::kPermanentFailure || !handle ||
      !allocation_bytes || (slot.live && slot.live->handle == handle)) {
    slot.permanent_failure = true;
    ++metrics_.permanent_failures;
    return true;
  }

  if (slot.live) {
    RetireLiveLocked(slot, submission);
  }
  const uint64_t resource_id = next_resource_id_++;
  slot.live = LiveTexture{*slot.pending, resource_id, handle,
                          allocation_bytes, frame, submission};
  PhysicalRange ranges[2] = {slot.live->key.base, {}};
  size_t range_count = 1;
  if (slot.live->key.mips) {
    ranges[range_count++] = *slot.live->key.mips;
  }
  tracker_.Track({TrackedResourceClass::kTexture, resource_id},
                 std::span<const PhysicalRange>(ranges, range_count));
  slot.pending.reset();
  slot.permanent_failure = false;
  ++metrics_.live_count;
  metrics_.live_bytes += allocation_bytes;
  return true;
}

size_t NativeTextureCache::RetireInvalidated(
    std::span<const ResourceInvalidation> invalidations,
    const PhysicalRange& written_range, uint64_t current_submission) {
  const std::scoped_lock lock(mutex_);
  size_t count = 0;
  for (Slot& slot : slots_) {
    if (slot.pending &&
        (slot.pending->base.Overlaps(written_range) ||
         (slot.pending->mips &&
          slot.pending->mips->Overlaps(written_range)))) {
      slot.pending.reset();
      slot.decode_in_flight = false;
      slot.permanent_failure = false;
    }
    if (!slot.live) {
      continue;
    }
    const bool invalidated = std::ranges::any_of(
        invalidations, [&](const ResourceInvalidation& invalidation) {
          return invalidation.resource.resource_class ==
                     TrackedResourceClass::kTexture &&
                 invalidation.resource.value == slot.live->resource_id;
        });
    if (invalidated) {
      RetireLiveLocked(slot, current_submission);
      ++count;
    }
  }
  metrics_.invalidations += count;
  return count;
}

size_t NativeTextureCache::RetireAll(uint64_t current_submission) {
  const std::scoped_lock lock(mutex_);
  size_t count = 0;
  for (Slot& slot : slots_) {
    slot.pending.reset();
    slot.decode_in_flight = false;
    if (slot.live) {
      RetireLiveLocked(slot, current_submission);
      ++count;
    }
  }
  return count;
}

std::vector<RetiredTexture> NativeTextureCache::Collect(
    uint64_t completed_submission) {
  const std::scoped_lock lock(mutex_);
  std::vector<RetiredTexture> ready;
  auto retained = std::remove_if(
      retired_.begin(), retired_.end(), [&](const RetiredTexture& texture) {
        if (texture.retire_after_submission > completed_submission) {
          return false;
        }
        ready.push_back(texture);
        --metrics_.retired_count;
        metrics_.retired_bytes -= texture.allocation_bytes;
        return true;
      });
  retired_.erase(retained, retired_.end());
  return ready;
}

TextureCacheMetrics NativeTextureCache::metrics() const {
  const std::scoped_lock lock(mutex_);
  return metrics_;
}

NativeTextureCache::Slot* NativeTextureCache::FindSlotLocked(
    const TextureResourceKey& key) {
  auto found = std::find_if(slots_.begin(), slots_.end(),
                            [&](const Slot& slot) {
                              return slot.base == key.base &&
                                     slot.mips == key.mips &&
                                     slot.fetch_signature == key.fetch_signature;
                            });
  return found == slots_.end() ? nullptr : &*found;
}

void NativeTextureCache::RetireLiveLocked(Slot& slot,
                                          uint64_t current_submission) {
  const LiveTexture texture = *slot.live;
  retired_.push_back(
      {texture.handle, texture.allocation_bytes,
       std::max(texture.last_use_submission, current_submission)});
  tracker_.Untrack({TrackedResourceClass::kTexture, texture.resource_id});
  slot.live.reset();
  --metrics_.live_count;
  metrics_.live_bytes -= texture.allocation_bytes;
  ++metrics_.retired_count;
  metrics_.retired_bytes += texture.allocation_bytes;
}

uint64_t NativeTextureCache::RetryDelay(uint32_t attempt) const {
  const uint32_t shift = std::min(attempt - 1, uint32_t(31));
  const uint64_t delay = uint64_t(retry_policy_.base_delay_frames) << shift;
  return std::min(delay, uint64_t(retry_policy_.maximum_delay_frames));
}

}  // namespace pinyon_shift::native_renderer
