#include "native_renderer/texture_resource_bridge.h"

#include <rex/cvar.h>
#include <rex/system/interfaces/graphics.h>

#include <atomic>
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

#include "native_renderer/render_target_bridge.h"
#include "native_renderer/resource_identity.h"
#include "native_renderer/resource_worker.h"
#include "native_renderer/texture_cache.h"
#include "pinyon_shift_diagnostics.h"

REXCVAR_DEFINE_BOOL(pinyon_shift_native_renderer_texture_bridge, false, "Pinyon Shift",
                    "Retain GPU-ready textures for native-renderer replay diagnostics")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

namespace {

using NativeObservation = rex::system::GraphicsNativeTextureSetObservation;
using NativeResource = rex::system::GraphicsNativeTextureResourceObservation;
using ResolveObservation = rex::system::GraphicsCopyObservation;

constexpr uint32_t kRetainedPassTextureFormat =
    pinyon_shift::native_renderer::kXenosTextureFormatDxn;
constexpr uint32_t kRetainedPassTextureWidth = 256;
constexpr uint32_t kRetainedPassTextureHeight = 64;
constexpr uint32_t kRetainedPassTexturePitch = 256;
constexpr size_t kResolveRecordLimit = 4096;
constexpr size_t kProducerResourceLimit = 64;
constexpr uint64_t kProducerByteLimit = 128 * 1024 * 1024;
constexpr uint64_t kProducerStaleSubmissions = 600;
constexpr uint64_t kTextureCacheByteLimit = 128 * 1024 * 1024;
constexpr size_t kTextureCacheResourceLimit = 2048;
constexpr size_t kTextureCacheStateLimit = 4096;

uint64_t HashFetchWords(const uint32_t words[6]) {
  uint64_t hash = UINT64_C(14695981039346656037);
  for (size_t word_index = 0; word_index < 6; ++word_index) {
    uint32_t word = words[word_index];
    for (size_t byte_index = 0; byte_index < sizeof(word); ++byte_index) {
      hash ^= uint8_t(word >> (byte_index * 8));
      hash *= UINT64_C(1099511628211);
    }
  }
  return hash;
}

bool IsRetainedPassCandidate(const NativeResource& resource) {
  return resource.guest_format == kRetainedPassTextureFormat &&
         resource.guest_width == kRetainedPassTextureWidth &&
         resource.guest_height == kRetainedPassTextureHeight &&
         resource.guest_pitch == kRetainedPassTexturePitch && resource.guest_tiled;
}

std::optional<pinyon_shift::native_renderer::NativePreparedResource>
PrepareTextureMetadata(
    pinyon_shift::native_renderer::NativeResourceWorkRequest request,
    std::stop_token stop_token) {
  if (stop_token.stop_requested() ||
      request.payload.size() != sizeof(uint32_t) * 6) {
    return std::nullopt;
  }
  std::array<uint32_t, 6> fetch_words;
  std::memcpy(fetch_words.data(), request.payload.data(),
              request.payload.size());
  if (!pinyon_shift::native_renderer::NativeTextureDescriptor::FromFetchWords(
          fetch_words)) {
    return std::nullopt;
  }
  return pinyon_shift::native_renderer::NativePreparedResource{
      request.key, request.priority, std::move(request.payload)};
}

class TextureResourceBridge {
 public:
  TextureResourceBridge()
      : prewarm_worker_({}, &PrepareTextureMetadata) {
    if (!prewarm_worker_.Start()) {
      RecordFailureOnce("prewarm_worker_start_failed");
    }
  }

  void ObserveResolve(const ResolveObservation& observation) {
    if (!observation.succeeded || !observation.written_length) {
      return;
    }
    const auto destination =
        pinyon_shift::native_renderer::PhysicalRange::FromGraphicsAddress(
            observation.written_address, observation.written_length);
    if (!destination) {
      RecordFailureOnce("invalid_resolve_range");
      return;
    }

    const std::scoped_lock lock(mutex_);
    ReleaseCollected(render_target_bridge_.Collect(
        observation.completed_submission));
    render_target_bridge_.RecordGpuOutput(*destination,
                                          observation.current_submission);

    const bool is_depth = (observation.rb_copy_control & 0x7u) >= 4u;
    auto record = std::find_if(
        resolve_records_.begin(), resolve_records_.end(),
        [&](const ResolveRecord& candidate) {
          return candidate.destination == *destination;
        });
    if (record == resolve_records_.end()) {
      if (resolve_records_.size() >= kResolveRecordLimit) {
        resolve_records_.erase(resolve_records_.begin());
        ++resolve_record_evictions_;
      }
      resolve_records_.push_back(
          {*destination, observation.current_submission, is_depth});
    } else {
      *record = {*destination, observation.current_submission, is_depth};
    }
    ++resolve_observation_count_;

    if (resolve_observation_count_ <= 16) {
      pinyon_shift::diagnostics::RecordEvent(
          "native_renderer.resolve_bridge.observed",
          {{"address", std::to_string(destination->address)},
           {"bytes", std::to_string(destination->length)},
           {"attachment", is_depth ? "depth" : "color"},
           {"submission", std::to_string(observation.current_submission)},
           {"xenos_resolve", "preserved"}});
    }
  }

  void Observe(const NativeObservation& observation) {
    const std::scoped_lock lock(mutex_);
    ++observation_count_;
    if (observation.backend != rex::system::GraphicsNativeTextureBackend::kD3D12) {
      RecordFailureOnce("unsupported_backend");
      return;
    }

    ReleaseCollected(cache_.Collect(observation.completed_submission));
    ReleaseCollected(
        render_target_bridge_.Collect(observation.completed_submission));
    for (uint32_t resource_index = 0; resource_index < observation.resource_count;
         ++resource_index) {
      const NativeResource& resource = observation.resources[resource_index];
      const uint64_t observed = observed_resource_count_.fetch_add(1, std::memory_order_relaxed);
      if (observed < 16) {
        pinyon_shift::diagnostics::RecordEvent(
            "native_renderer.texture_bridge.observed",
            {{"fetch", std::to_string(resource.fetch_constant)},
             {"guest_format", std::to_string(resource.guest_format)},
             {"width", std::to_string(resource.guest_width)},
             {"height", std::to_string(resource.guest_height)},
             {"pitch", std::to_string(resource.guest_pitch)},
             {"tiled", resource.guest_tiled ? "1" : "0"},
             {"host_format", std::to_string(resource.host_resource_format)}});
      }
      SubmitTexturePreparation(resource);
      if (IsRetainedPassCandidate(resource)) {
        Retain(resource, observation);
      }
      ImportResolveProducer(resource, observation);
    }
    prewarm_worker_.DrainCommits(
        4, 64 * 1024,
        [](pinyon_shift::native_renderer::NativePreparedResource) {});

    if (resource_count_ && (!last_summary_submission_ ||
                            observation.current_submission >= last_summary_submission_ + 300)) {
      last_summary_submission_ = observation.current_submission;
      cache_.Trim(observation.current_submission,
                  observation.current_submission, false);
      ReleaseCollected(cache_.Collect(observation.completed_submission));
      const auto metrics = cache_.metrics();
      const auto target_metrics = render_target_bridge_.metrics();
      const auto worker_metrics = prewarm_worker_.metrics();
      pinyon_shift::diagnostics::RecordEvent(
          "native_renderer.texture_bridge.summary",
          {{"observations", std::to_string(observation_count_)},
           {"resources", std::to_string(resource_count_)},
           {"live", std::to_string(metrics.live_count)},
           {"live_bytes", std::to_string(metrics.live_bytes)},
           {"retired", std::to_string(metrics.retired_count)},
           {"retired_bytes", std::to_string(metrics.retired_bytes)},
           {"hits", std::to_string(metrics.hits)},
           {"misses", std::to_string(metrics.misses)},
           {"cache_budget_evictions",
            std::to_string(metrics.budget_evictions)},
           {"cache_budget_refusals",
            std::to_string(metrics.budget_refusals)},
           {"cache_state", std::to_string(metrics.state_count)},
           {"cache_state_evictions",
            std::to_string(metrics.state_evictions)},
           {"resolve_observations", std::to_string(resolve_observation_count_)},
           {"producer_publications",
            std::to_string(target_metrics.resolve_publications)},
           {"producer_deduplications",
            std::to_string(producer_deduplications_)},
           {"producer_budget_evictions",
            std::to_string(producer_budget_evictions_)},
           {"producer_budget_refusals",
            std::to_string(producer_budget_refusals_)},
           {"producer_hits", std::to_string(target_metrics.bridge_hits)},
           {"producer_refusals",
            std::to_string(target_metrics.bridge_refusals)},
           {"target_live", std::to_string(target_metrics.live_count)},
           {"target_live_bytes", std::to_string(target_metrics.live_bytes)},
           {"resolve_record_evictions",
            std::to_string(resolve_record_evictions_)},
           {"prewarm_submissions",
            std::to_string(worker_metrics.submissions)},
           {"prewarm_deduplications",
            std::to_string(worker_metrics.deduplications)},
           {"prewarm_prepared", std::to_string(worker_metrics.prepared)},
           {"prewarm_commits", std::to_string(worker_metrics.commits)},
           {"prewarm_stale", std::to_string(worker_metrics.stale_results)},
           {"prewarm_refusals",
            std::to_string(worker_metrics.capacity_refusals)},
           {"prewarm_pending", std::to_string(worker_metrics.pending_count)},
           {"submission", std::to_string(observation.current_submission)},
           {"completed_submission", std::to_string(observation.completed_submission)},
           {"xenos_draw", "preserved"}});
    }
  }

  void Shutdown() {
    const std::scoped_lock lock(mutex_);
    prewarm_worker_.Stop();
    cache_.RetireAll(0);
    render_target_bridge_.RetireAll(0);
    ReleaseCollected(cache_.Collect(UINT64_MAX));
    ReleaseCollected(render_target_bridge_.Collect(UINT64_MAX));
    const auto metrics = cache_.metrics();
    const auto worker_metrics = prewarm_worker_.metrics();
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.texture_bridge.stopped",
        {{"observations", std::to_string(observation_count_)},
         {"resources", std::to_string(resource_count_)},
         {"resolve_observations", std::to_string(resolve_observation_count_)},
         {"producer_resources", std::to_string(producer_resource_count_)},
         {"prewarm_submissions", std::to_string(worker_metrics.submissions)},
         {"prewarm_commits", std::to_string(worker_metrics.commits)},
         {"prewarm_pending", std::to_string(worker_metrics.pending_count)},
         {"prewarm_prepared", std::to_string(worker_metrics.prepared_count)},
         {"live", std::to_string(metrics.live_count)},
         {"live_bytes", std::to_string(metrics.live_bytes)},
         {"retired", std::to_string(metrics.retired_count)},
         {"retired_bytes", std::to_string(metrics.retired_bytes)},
         {"cache_budget_evictions",
          std::to_string(metrics.budget_evictions)},
         {"cache_budget_refusals",
          std::to_string(metrics.budget_refusals)},
         {"retained_refs", std::to_string(RetainedReferenceCount())},
         {"xenos_draw", "preserved"}});
  }

 private:
  struct ResolveRecord {
    pinyon_shift::native_renderer::PhysicalRange destination;
    uint64_t submission = 0;
    bool is_depth = false;
  };

  struct ProducerResource {
    pinyon_shift::native_renderer::NativeRenderTargetKey key;
    pinyon_shift::native_renderer::PhysicalRange destination;
    uint64_t last_resolve_submission = 0;
    uint64_t last_seen_submission = 0;
    uint64_t allocation_bytes = 0;
  };

  struct RetainedReference {
    rex::system::GraphicsNativeTextureRelease release = nullptr;
    uint64_t count = 0;
  };

  void SubmitTexturePreparation(const NativeResource& resource) {
    if (!resource.base_length) {
      return;
    }
    const auto base =
        pinyon_shift::native_renderer::PhysicalRange::FromGraphicsAddress(
            resource.base_address, resource.base_length);
    if (!base) {
      return;
    }
    const uint64_t fetch_signature = HashFetchWords(resource.fetch_dwords);
    uint64_t identity = base->address;
    identity ^= base->length + UINT64_C(0x9E3779B97F4A7C15) +
                (identity << 6) + (identity >> 2);
    identity ^= fetch_signature + UINT64_C(0x9E3779B97F4A7C15) +
                (identity << 6) + (identity >> 2);
    if (!identity) {
      identity = 1;
    }
    std::vector<uint8_t> payload(sizeof(resource.fetch_dwords));
    std::memcpy(payload.data(), resource.fetch_dwords, payload.size());
    prewarm_worker_.Submit(
        {{pinyon_shift::native_renderer::NativeResourceWorkClass::kTexture,
          identity, 1},
         pinyon_shift::native_renderer::NativeResourceWorkPriority::
             kVisibleMiss,
         std::move(payload)});
  }

  void Retain(const NativeResource& resource, const NativeObservation& observation) {
    if (!resource.resource || !resource.retain || !resource.release ||
        !resource.host_allocation_bytes || !resource.base_length) {
      return;
    }
    // This diagnostic bridge deliberately imports only the first measured
    // retained-pass contract. Expanding format coverage belongs to later
    // budgeted NR-03 work, not an unbounded observer-side cache.
    const auto base = pinyon_shift::native_renderer::PhysicalRange::FromGraphicsAddress(
        resource.base_address, resource.base_length);
    if (!base) {
      RecordFailureOnce("invalid_base_range");
      return;
    }
    std::optional<pinyon_shift::native_renderer::PhysicalRange> mips;
    if (resource.mip_length) {
      mips = pinyon_shift::native_renderer::PhysicalRange::FromGraphicsAddress(resource.mip_address,
                                                                               resource.mip_length);
      if (!mips) {
        RecordFailureOnce("invalid_mip_range");
        return;
      }
    }

    const uint64_t handle = reinterpret_cast<uint64_t>(resource.resource);
    const pinyon_shift::native_renderer::TextureResourceKey key{
        *base, mips, HashFetchWords(resource.fetch_dwords), {0, handle}};
    auto request = cache_.Request(key, observation.current_submission,
                                  observation.current_submission);
    if (request.state != pinyon_shift::native_renderer::TextureRequestState::kDecodeRequired) {
      return;
    }

    resource.retain(resource.resource);
    const uint64_t refusals_before = cache_.metrics().budget_refusals;
    const bool completed = cache_.Complete(
        request.decode_ticket, pinyon_shift::native_renderer::TextureDecodeResult::kReady, handle,
        resource.host_allocation_bytes, observation.current_submission,
        observation.current_submission);
    if (!completed) {
      resource.release(resource.resource);
      if (cache_.metrics().budget_refusals == refusals_before) {
        RecordFailureOnce("cache_commit_failed");
      }
      return;
    }
    const auto confirmed = cache_.Request(key, observation.current_submission,
                                          observation.current_submission);
    if (confirmed.state != pinyon_shift::native_renderer::TextureRequestState::kReady ||
        confirmed.sampled_handle != handle) {
      resource.release(resource.resource);
      RecordFailureOnce("cache_commit_failed");
      return;
    }
    auto& retained = retained_[handle];
    retained.release = resource.release;
    ++retained.count;
    ++resource_count_;

    if (resource_count_ <= 16) {
      pinyon_shift::diagnostics::RecordEvent(
          "native_renderer.texture_bridge.resource",
          {{"fetch", std::to_string(resource.fetch_constant)},
           {"fetch_signature", std::to_string(key.fetch_signature)},
           {"guest_format", std::to_string(resource.guest_format)},
           {"width", std::to_string(resource.guest_width)},
           {"height", std::to_string(resource.guest_height)},
           {"base_address", std::to_string(base->address)},
           {"base_bytes", std::to_string(base->length)},
           {"host_format", std::to_string(resource.host_resource_format)},
           {"host_view_format", std::to_string(resource.host_view_format)},
           {"host_bytes", std::to_string(resource.host_allocation_bytes)},
           {"ownership", "retained"},
           {"native_upload", "rexglue_reuse"},
           {"xenos_draw", "preserved"}});
    }
  }

  void ImportResolveProducer(const NativeResource& resource,
                             const NativeObservation& observation) {
    if (!resource.resource || !resource.retain || !resource.release ||
        !resource.host_resource_format || !resource.host_allocation_bytes ||
        !resource.base_length || !resource.guest_row_pitch_bytes ||
        !resource.guest_width || !resource.guest_height ||
        !resource.host_width || resource.host_width > UINT32_MAX ||
        !resource.host_height || resource.host_depth_or_array_size != 1 ||
        !resource.host_mip_levels) {
      return;
    }
    const auto base =
        pinyon_shift::native_renderer::PhysicalRange::FromGraphicsAddress(
            resource.base_address, resource.base_length);
    if (!base) {
      return;
    }
    const auto resolve = std::find_if(
        resolve_records_.rbegin(), resolve_records_.rend(),
        [&](const ResolveRecord& candidate) {
          return candidate.destination.address <= base->address &&
                 candidate.destination.end_exclusive() >=
                     base->end_exclusive();
        });
    if (resolve == resolve_records_.rend()) {
      return;
    }

    using pinyon_shift::native_renderer::NativeRenderTargetUsage;
    const NativeRenderTargetUsage attachment =
        resolve->is_depth ? NativeRenderTargetUsage::kDepth
                          : NativeRenderTargetUsage::kColor;
    const pinyon_shift::native_renderer::NativeRenderTargetKey key{
        resource.host_resource_format, uint32_t(resource.host_width),
        resource.host_height, 1,
        attachment | NativeRenderTargetUsage::kShaderResource};
    const uint64_t handle = reinterpret_cast<uint64_t>(resource.resource);
    auto existing = producer_resources_.find(handle);
    if (existing != producer_resources_.end() && existing->second.key == key &&
        existing->second.allocation_bytes ==
            resource.host_allocation_bytes &&
        existing->second.destination == *base &&
        existing->second.last_resolve_submission >= resolve->submission) {
      existing->second.last_seen_submission = observation.current_submission;
      ++producer_deduplications_;
      return;
    }
    if (existing != producer_resources_.end() &&
        (existing->second.key != key ||
         existing->second.allocation_bytes !=
             resource.host_allocation_bytes ||
         existing->second.destination != *base)) {
      RetireProducer(handle, observation.current_submission);
    }
    PruneProducers(observation.completed_submission,
                   observation.current_submission, handle,
                   resource.host_allocation_bytes);
    existing = producer_resources_.find(handle);
    if (existing == producer_resources_.end() &&
        (producer_resources_.size() >= kProducerResourceLimit ||
         resource.host_allocation_bytes > kProducerByteLimit ||
         producer_live_bytes_ >
             kProducerByteLimit - resource.host_allocation_bytes)) {
      ++producer_budget_refusals_;
      return;
    }
    const auto imported = render_target_bridge_.ImportObserved(
        key, handle, resource.host_allocation_bytes, observation_count_,
        observation.current_submission);
    if (!imported) {
      RecordFailureOnce("producer_import_failed");
      return;
    }
    if (!imported->hit) {
      resource.retain(resource.resource);
      auto& retained = retained_[handle];
      retained.release = resource.release;
      ++retained.count;
      producer_resources_[handle] =
          {key, *base, 0, observation.current_submission,
           resource.host_allocation_bytes};
      producer_live_bytes_ += resource.host_allocation_bytes;
    }

    const pinyon_shift::native_renderer::NativeResolveRegion region{
        *base, 0, 0, resource.guest_width, resource.guest_height,
        resource.guest_row_pitch_bytes, 0, 0};
    if (!render_target_bridge_.PublishResolve(handle, region,
                                               resolve->submission) ||
        !render_target_bridge_.Release(handle,
                                       observation.current_submission)) {
      RetireProducer(handle, observation.current_submission);
      ReleaseCollected(render_target_bridge_.Collect(
          observation.completed_submission));
      RecordFailureOnce("producer_publish_failed");
      return;
    }
    ++producer_resource_count_;
    auto& tracked = producer_resources_[handle];
    tracked.key = key;
    tracked.destination = *base;
    tracked.last_resolve_submission = resolve->submission;
    tracked.last_seen_submission = observation.current_submission;
    if (producer_resource_count_ <= 16) {
      pinyon_shift::diagnostics::RecordEvent(
          "native_renderer.resolve_bridge.producer",
          {{"address", std::to_string(base->address)},
           {"bytes", std::to_string(base->length)},
           {"host_format", std::to_string(resource.host_resource_format)},
           {"width", std::to_string(resource.guest_width)},
           {"height", std::to_string(resource.guest_height)},
           {"row_pitch", std::to_string(resource.guest_row_pitch_bytes)},
           {"pool", imported->hit ? "hit" : "miss"},
           {"ownership", "retained"},
           {"xenos_draw", "preserved"}});
    }
  }

  void PruneProducers(uint64_t completed_submission,
                      uint64_t current_submission,
                      uint64_t protected_handle,
                      uint64_t incoming_bytes) {
    std::vector<uint64_t> stale;
    for (const auto& [handle, producer] : producer_resources_) {
      if (handle != protected_handle &&
          producer.last_seen_submission + kProducerStaleSubmissions <=
              completed_submission) {
        stale.push_back(handle);
      }
    }
    for (uint64_t handle : stale) {
      RetireProducer(handle, current_submission);
    }
    while (!producer_resources_.empty() &&
           (producer_resources_.size() >= kProducerResourceLimit ||
            incoming_bytes > kProducerByteLimit ||
            producer_live_bytes_ > kProducerByteLimit - incoming_bytes)) {
      auto oldest = producer_resources_.end();
      for (auto candidate = producer_resources_.begin();
           candidate != producer_resources_.end(); ++candidate) {
        if (candidate->first == protected_handle) {
          continue;
        }
        if (oldest == producer_resources_.end() ||
            candidate->second.last_seen_submission <
                oldest->second.last_seen_submission) {
          oldest = candidate;
        }
      }
      if (oldest == producer_resources_.end()) {
        break;
      }
      const uint64_t handle = oldest->first;
      RetireProducer(handle, current_submission);
      ++producer_budget_evictions_;
    }
  }

  void RetireProducer(uint64_t handle, uint64_t current_submission) {
    auto producer = producer_resources_.find(handle);
    if (producer == producer_resources_.end()) {
      return;
    }
    if (!render_target_bridge_.Retire(handle, current_submission)) {
      RecordFailureOnce("producer_retire_failed");
    }
    producer_live_bytes_ -= producer->second.allocation_bytes;
    producer_resources_.erase(producer);
  }

  void ReleaseCollected(
      const std::vector<pinyon_shift::native_renderer::RetiredTexture>& collected) {
    for (const auto& texture : collected) {
      auto retained = retained_.find(texture.handle);
      if (retained == retained_.end() || !retained->second.count) {
        RecordFailureOnce("missing_retained_reference");
        continue;
      }
      retained->second.release(reinterpret_cast<void*>(texture.handle));
      if (!--retained->second.count) {
        retained_.erase(retained);
      }
    }
  }

  void ReleaseCollected(const std::vector<
                        pinyon_shift::native_renderer::RetiredRenderTarget>&
                            collected) {
    for (const auto& target : collected) {
      auto retained = retained_.find(target.handle);
      if (retained == retained_.end() || !retained->second.count) {
        RecordFailureOnce("missing_target_reference");
        continue;
      }
      retained->second.release(reinterpret_cast<void*>(target.handle));
      if (!--retained->second.count) {
        retained_.erase(retained);
      }
    }
  }

  uint64_t RetainedReferenceCount() const {
    uint64_t count = 0;
    for (const auto& [handle, retained] : retained_) {
      (void)handle;
      count += retained.count;
    }
    return count;
  }

  void RecordFailureOnce(const char* reason) {
    if (failure_recorded_) {
      return;
    }
    failure_recorded_ = true;
    pinyon_shift::diagnostics::RecordEvent("native_renderer.texture_bridge.failure",
                                           {{"reason", reason}, {"fallback", "xenos"}});
  }

  std::mutex mutex_;
  pinyon_shift::native_renderer::PhysicalResourceTracker tracker_;
  pinyon_shift::native_renderer::NativeTextureCache cache_{
      tracker_, {},
      {.maximum_live_bytes = kTextureCacheByteLimit,
       .maximum_live_count = kTextureCacheResourceLimit,
       .maximum_state_count = kTextureCacheStateLimit,
       .maximum_evictions_per_maintenance = 16,
       .normal_idle_frames = 1200,
       .pressure_idle_frames = 120}};
  pinyon_shift::native_renderer::NativeResourceWorker prewarm_worker_;
  pinyon_shift::native_renderer::NativeRenderTargetBridge
      render_target_bridge_;
  std::unordered_map<uint64_t, RetainedReference> retained_;
  std::unordered_map<uint64_t, ProducerResource> producer_resources_;
  std::vector<ResolveRecord> resolve_records_;
  std::atomic<uint64_t> observed_resource_count_{};
  uint64_t observation_count_ = 0;
  uint64_t resource_count_ = 0;
  uint64_t resolve_observation_count_ = 0;
  uint64_t producer_resource_count_ = 0;
  uint64_t producer_live_bytes_ = 0;
  uint64_t producer_deduplications_ = 0;
  uint64_t producer_budget_evictions_ = 0;
  uint64_t producer_budget_refusals_ = 0;
  uint64_t resolve_record_evictions_ = 0;
  uint64_t last_summary_submission_ = 0;
  bool failure_recorded_ = false;
};

std::unique_ptr<TextureResourceBridge> g_texture_resource_bridge;

void ObserveNativeTextures(const NativeObservation& observation) {
  if (g_texture_resource_bridge) {
    g_texture_resource_bridge->Observe(observation);
  }
}

void ObserveNativeResolve(const ResolveObservation& observation) {
  if (g_texture_resource_bridge) {
    g_texture_resource_bridge->ObserveResolve(observation);
  }
}

}  // namespace

namespace pinyon_shift::native_renderer {

void InstallTextureResourceBridge(rex::system::IGraphicsSystem* graphics_system) {
  if (!graphics_system || !REXCVAR_GET(pinyon_shift_native_renderer_texture_bridge)) {
    return;
  }
  g_texture_resource_bridge = std::make_unique<TextureResourceBridge>();
  graphics_system->SetNativeTextureSetObserver(&ObserveNativeTextures);
  graphics_system->SetNativeResolveObserver(&ObserveNativeResolve);
  diagnostics::RecordEvent("native_renderer.texture_bridge.installed",
                           {{"backend", "d3d12"},
                            {"ownership", "explicit_retain_release"},
                            {"xenos_draw", "preserved"},
                            {"suppression", "disabled"}});
}

void UninstallTextureResourceBridge(rex::system::IGraphicsSystem* graphics_system) {
  if (graphics_system) {
    graphics_system->SetNativeTextureSetObserver(nullptr);
    graphics_system->SetNativeResolveObserver(nullptr);
  }
  if (g_texture_resource_bridge) {
    g_texture_resource_bridge->Shutdown();
    g_texture_resource_bridge.reset();
  }
}

}  // namespace pinyon_shift::native_renderer
