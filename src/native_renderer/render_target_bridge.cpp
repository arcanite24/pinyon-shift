#include "native_renderer/render_target_bridge.h"

#include <algorithm>
#include <functional>

namespace pinyon_shift::native_renderer {

namespace {

size_t HashCombine(size_t seed, uint64_t value) {
  return seed ^ (std::hash<uint64_t>{}(value) + size_t(0x9E3779B9) +
                 (seed << 6) + (seed >> 2));
}

bool Contains(const PhysicalRange &outer, const PhysicalRange &inner) {
  return outer.valid() && inner.valid() && outer.address <= inner.address &&
         outer.end_exclusive() >= inner.end_exclusive();
}

}  // namespace

bool NativeRenderTargetKey::valid() const {
  const uint32_t usage_bits = RenderTargetUsageBits(usage);
  const uint32_t known_usage_bits =
      RenderTargetUsageBits(NativeRenderTargetUsage::kColor) |
      RenderTargetUsageBits(NativeRenderTargetUsage::kDepth) |
      RenderTargetUsageBits(NativeRenderTargetUsage::kShaderResource) |
      RenderTargetUsageBits(NativeRenderTargetUsage::kUnorderedAccess);
  const bool one_attachment =
      bool(usage_bits &
           RenderTargetUsageBits(NativeRenderTargetUsage::kColor)) !=
      bool(usage_bits & RenderTargetUsageBits(NativeRenderTargetUsage::kDepth));
  return host_format && width && height && sample_count && one_attachment &&
         !(usage_bits & ~known_usage_bits);
}

size_t NativeRenderTargetKeyHash::operator()(
    const NativeRenderTargetKey &key) const {
  size_t hash = 0;
  hash = HashCombine(hash, key.host_format);
  hash = HashCombine(hash, key.width);
  hash = HashCombine(hash, key.height);
  hash = HashCombine(hash, key.sample_count);
  return HashCombine(hash, RenderTargetUsageBits(key.usage));
}

bool NativeResolveRegion::valid_for(const NativeRenderTargetKey &key) const {
  if (!key.valid() || !guest_destination.valid() || !width || !height ||
      !row_pitch_bytes || mip_level || array_slice || key.sample_count != 1 ||
      !(RenderTargetUsageBits(key.usage) &
        RenderTargetUsageBits(NativeRenderTargetUsage::kShaderResource))) {
    return false;
  }
  const uint64_t right = uint64_t(source_x) + width;
  const uint64_t bottom = uint64_t(source_y) + height;
  return right <= key.width && bottom <= key.height &&
         uint64_t(row_pitch_bytes) * height <= guest_destination.length;
}

std::optional<NativeRenderTargetAcquireResult>
NativeRenderTargetBridge::Acquire(const NativeRenderTargetKey &key,
                                  NativeRenderTargetHandle candidate_handle,
                                  uint64_t allocation_bytes, uint64_t frame,
                                  uint64_t current_submission,
                                  uint64_t completed_submission) {
  if (!key.valid()) {
    return std::nullopt;
  }
  const std::scoped_lock lock(mutex_);
  auto reusable = std::find_if(
      targets_.begin(), targets_.end(), [&](const TargetEntry &target) {
        return target.key == key && !target.checked_out &&
               !target.mapping_pins &&
               target.available_after_submission <= completed_submission;
      });
  if (reusable != targets_.end()) {
    reusable->checked_out = true;
    reusable->last_use_frame = std::max(reusable->last_use_frame, frame);
    reusable->last_use_submission =
        std::max(reusable->last_use_submission, current_submission);
    ++metrics_.pool_hits;
    return NativeRenderTargetAcquireResult{reusable->handle, true};
  }
  if (!candidate_handle || !allocation_bytes ||
      FindTargetLocked(candidate_handle)) {
    return std::nullopt;
  }
  targets_.push_back({key, candidate_handle, allocation_bytes, frame,
                      current_submission, current_submission, 0, true});
  ++metrics_.pool_misses;
  ++metrics_.live_count;
  metrics_.live_bytes += allocation_bytes;
  return NativeRenderTargetAcquireResult{candidate_handle, false};
}

bool NativeRenderTargetBridge::Release(NativeRenderTargetHandle handle,
                                       uint64_t current_submission) {
  const std::scoped_lock lock(mutex_);
  TargetEntry *target = FindTargetLocked(handle);
  if (!target || !target->checked_out) {
    return false;
  }
  target->checked_out = false;
  target->last_use_submission =
      std::max(target->last_use_submission, current_submission);
  target->available_after_submission =
      std::max(target->available_after_submission, current_submission);
  return true;
}

bool NativeRenderTargetBridge::PublishResolve(NativeRenderTargetHandle handle,
                                              const NativeResolveRegion &region,
                                              uint64_t producer_submission) {
  const std::scoped_lock lock(mutex_);
  TargetEntry *target = FindTargetLocked(handle);
  if (!target || !target->checked_out || !region.valid_for(target->key)) {
    return false;
  }
  for (size_t mapping_index = mappings_.size(); mapping_index-- > 0;) {
    if (mappings_[mapping_index].region.guest_destination.Overlaps(
            region.guest_destination)) {
      RemoveMappingLocked(mapping_index);
    }
  }
  RememberKnownOutputLocked(region.guest_destination);
  mappings_.push_back({region, handle, producer_submission});
  ++target->mapping_pins;
  target->last_use_submission =
      std::max(target->last_use_submission, producer_submission);
  target->available_after_submission =
      std::max(target->available_after_submission, producer_submission);
  ++metrics_.resolve_publications;
  return true;
}

NativeProducerLookup NativeRenderTargetBridge::LookupProducer(
    const NativeProducerRequest &request, uint64_t frame,
    uint64_t current_submission) {
  const std::scoped_lock lock(mutex_);
  if (!request.guest_source.valid() || !request.host_format || !request.width ||
      !request.height) {
    ++metrics_.bridge_refusals;
    return {NativeProducerLookupState::kBridgeRequired};
  }
  const auto mapping = std::find_if(
      mappings_.begin(), mappings_.end(), [&](const ResolveMapping &candidate) {
        return Contains(candidate.region.guest_destination,
                        request.guest_source);
      });
  if (mapping != mappings_.end()) {
    TargetEntry *target = FindTargetLocked(mapping->handle);
    if (target && target->key.host_format == request.host_format &&
        mapping->region.width == request.width &&
        mapping->region.height == request.height) {
      target->last_use_frame = std::max(target->last_use_frame, frame);
      target->last_use_submission =
          std::max(target->last_use_submission, current_submission);
      target->available_after_submission =
          std::max(target->available_after_submission, current_submission);
      ++metrics_.bridge_hits;
      return {NativeProducerLookupState::kNativeProducer, target->handle,
              target->key, mapping->region, mapping->producer_submission};
    }
    ++metrics_.bridge_refusals;
    return {NativeProducerLookupState::kBridgeRequired};
  }
  const bool known_gpu_output =
      std::ranges::any_of(known_gpu_outputs_, [&](const PhysicalRange &known) {
        return known.Overlaps(request.guest_source);
      });
  if (known_gpu_output) {
    ++metrics_.bridge_refusals;
    return {NativeProducerLookupState::kBridgeRequired};
  }
  return {NativeProducerLookupState::kGuestDecodeAllowed};
}

size_t NativeRenderTargetBridge::InvalidateGuestWrite(
    const PhysicalRange &written_range, uint64_t current_submission) {
  if (!written_range.valid()) {
    return 0;
  }
  const std::scoped_lock lock(mutex_);
  size_t invalidated = 0;
  for (size_t mapping_index = mappings_.size(); mapping_index-- > 0;) {
    if (!mappings_[mapping_index].region.guest_destination.Overlaps(
            written_range)) {
      continue;
    }
    TargetEntry *target = FindTargetLocked(mappings_[mapping_index].handle);
    if (target) {
      target->last_use_submission =
          std::max(target->last_use_submission, current_submission);
      target->available_after_submission =
          std::max(target->available_after_submission, current_submission);
    }
    RemoveMappingLocked(mapping_index);
    ++invalidated;
  }
  ForgetKnownOutputLocked(written_range);
  metrics_.guest_invalidations += invalidated;
  return invalidated;
}

bool NativeRenderTargetBridge::Retire(NativeRenderTargetHandle handle,
                                      uint64_t current_submission) {
  const std::scoped_lock lock(mutex_);
  auto target = std::find_if(
      targets_.begin(), targets_.end(),
      [&](const TargetEntry &candidate) { return candidate.handle == handle; });
  if (target == targets_.end()) {
    return false;
  }
  RemoveMappingsForHandleLocked(handle, true);
  retired_.push_back(
      {target->handle, target->allocation_bytes,
       std::max(target->last_use_submission, current_submission)});
  --metrics_.live_count;
  metrics_.live_bytes -= target->allocation_bytes;
  ++metrics_.retired_count;
  metrics_.retired_bytes += target->allocation_bytes;
  targets_.erase(target);
  return true;
}

size_t NativeRenderTargetBridge::RetireAll(uint64_t current_submission) {
  const std::scoped_lock lock(mutex_);
  const size_t count = targets_.size();
  while (!targets_.empty()) {
    const TargetEntry target = targets_.back();
    RemoveMappingsForHandleLocked(target.handle, true);
    retired_.push_back(
        {target.handle, target.allocation_bytes,
         std::max(target.last_use_submission, current_submission)});
    --metrics_.live_count;
    metrics_.live_bytes -= target.allocation_bytes;
    ++metrics_.retired_count;
    metrics_.retired_bytes += target.allocation_bytes;
    targets_.pop_back();
  }
  return count;
}

std::vector<RetiredRenderTarget> NativeRenderTargetBridge::Collect(
    uint64_t completed_submission) {
  const std::scoped_lock lock(mutex_);
  std::vector<RetiredRenderTarget> ready;
  auto retained = std::remove_if(
      retired_.begin(), retired_.end(), [&](const RetiredRenderTarget &target) {
        if (target.retire_after_submission > completed_submission) {
          return false;
        }
        ready.push_back(target);
        --metrics_.retired_count;
        metrics_.retired_bytes -= target.allocation_bytes;
        return true;
      });
  retired_.erase(retained, retired_.end());
  return ready;
}

RenderTargetBridgeMetrics NativeRenderTargetBridge::metrics() const {
  const std::scoped_lock lock(mutex_);
  return metrics_;
}

NativeRenderTargetBridge::TargetEntry *
NativeRenderTargetBridge::FindTargetLocked(NativeRenderTargetHandle handle) {
  auto target = std::find_if(
      targets_.begin(), targets_.end(),
      [&](const TargetEntry &candidate) { return candidate.handle == handle; });
  return target == targets_.end() ? nullptr : &*target;
}

void NativeRenderTargetBridge::RemoveMappingsForHandleLocked(
    NativeRenderTargetHandle handle, bool preserve_known_output) {
  for (size_t mapping_index = mappings_.size(); mapping_index-- > 0;) {
    if (mappings_[mapping_index].handle != handle) {
      continue;
    }
    const PhysicalRange destination =
        mappings_[mapping_index].region.guest_destination;
    RemoveMappingLocked(mapping_index);
    if (!preserve_known_output) {
      ForgetKnownOutputLocked(destination);
    }
  }
}

void NativeRenderTargetBridge::RemoveMappingLocked(size_t mapping_index) {
  if (mapping_index >= mappings_.size()) {
    return;
  }
  TargetEntry *target = FindTargetLocked(mappings_[mapping_index].handle);
  if (target && target->mapping_pins) {
    --target->mapping_pins;
  }
  mappings_.erase(mappings_.begin() + mapping_index);
}

void NativeRenderTargetBridge::RememberKnownOutputLocked(
    const PhysicalRange &range) {
  if (std::ranges::none_of(known_gpu_outputs_, [&](const PhysicalRange &known) {
        return known == range;
      })) {
    known_gpu_outputs_.push_back(range);
  }
}

void NativeRenderTargetBridge::ForgetKnownOutputLocked(
    const PhysicalRange &range) {
  known_gpu_outputs_.erase(
      std::remove_if(
          known_gpu_outputs_.begin(), known_gpu_outputs_.end(),
          [&](const PhysicalRange &known) { return known.Overlaps(range); }),
      known_gpu_outputs_.end());
}

}  // namespace pinyon_shift::native_renderer
