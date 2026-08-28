#include "native_renderer/texture_resource_bridge.h"

#include <rex/cvar.h>
#include <rex/system/interfaces/graphics.h>

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

#include "native_renderer/resource_identity.h"
#include "native_renderer/texture_cache.h"
#include "pinyon_shift_diagnostics.h"

REXCVAR_DEFINE_BOOL(pinyon_shift_native_renderer_texture_bridge, false, "Pinyon Shift",
                    "Retain GPU-ready textures for native-renderer replay diagnostics")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

namespace {

using NativeObservation = rex::system::GraphicsNativeTextureSetObservation;
using NativeResource = rex::system::GraphicsNativeTextureResourceObservation;

constexpr uint32_t kRetainedPassTextureFormat =
    pinyon_shift::native_renderer::kXenosTextureFormatDxn;
constexpr uint32_t kRetainedPassTextureWidth = 256;
constexpr uint32_t kRetainedPassTextureHeight = 64;
constexpr uint32_t kRetainedPassTexturePitch = 256;

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

class TextureResourceBridge {
 public:
  void Observe(const NativeObservation& observation) {
    bool has_candidate = false;
    for (uint32_t resource_index = 0; resource_index < observation.resource_count;
         ++resource_index) {
      has_candidate |= IsRetainedPassCandidate(observation.resources[resource_index]);
    }
    if (!has_candidate && observed_resource_count_.load(std::memory_order_relaxed) >= 16) {
      return;
    }
    const std::scoped_lock lock(mutex_);
    ++observation_count_;
    if (observation.backend != rex::system::GraphicsNativeTextureBackend::kD3D12) {
      RecordFailureOnce("unsupported_backend");
      return;
    }

    ReleaseCollected(cache_.Collect(observation.completed_submission));
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
      if (IsRetainedPassCandidate(resource)) {
        Retain(resource, observation);
      }
    }

    if (resource_count_ && (!last_summary_submission_ ||
                            observation.current_submission >= last_summary_submission_ + 300)) {
      last_summary_submission_ = observation.current_submission;
      const auto metrics = cache_.metrics();
      pinyon_shift::diagnostics::RecordEvent(
          "native_renderer.texture_bridge.summary",
          {{"observations", std::to_string(observation_count_)},
           {"resources", std::to_string(resource_count_)},
           {"live", std::to_string(metrics.live_count)},
           {"live_bytes", std::to_string(metrics.live_bytes)},
           {"retired", std::to_string(metrics.retired_count)},
           {"hits", std::to_string(metrics.hits)},
           {"misses", std::to_string(metrics.misses)},
           {"submission", std::to_string(observation.current_submission)},
           {"completed_submission", std::to_string(observation.completed_submission)},
           {"xenos_draw", "preserved"}});
    }
  }

  void Shutdown() {
    const std::scoped_lock lock(mutex_);
    cache_.RetireAll(0);
    ReleaseCollected(cache_.Collect(UINT64_MAX));
    const auto metrics = cache_.metrics();
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.texture_bridge.stopped",
        {{"observations", std::to_string(observation_count_)},
         {"resources", std::to_string(resource_count_)},
         {"live", std::to_string(metrics.live_count)},
         {"retained_refs", std::to_string(RetainedReferenceCount())},
         {"xenos_draw", "preserved"}});
  }

 private:
  struct RetainedReference {
    rex::system::GraphicsNativeTextureRelease release = nullptr;
    uint64_t count = 0;
  };

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
    auto request = cache_.Request(key, observation_count_, observation.current_submission);
    if (request.state != pinyon_shift::native_renderer::TextureRequestState::kDecodeRequired) {
      return;
    }

    resource.retain(resource.resource);
    const bool completed = cache_.Complete(
        request.decode_ticket, pinyon_shift::native_renderer::TextureDecodeResult::kReady, handle,
        resource.host_allocation_bytes, observation_count_, observation.current_submission);
    const auto confirmed = cache_.Request(key, observation_count_, observation.current_submission);
    if (!completed ||
        confirmed.state != pinyon_shift::native_renderer::TextureRequestState::kReady ||
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
  pinyon_shift::native_renderer::NativeTextureCache cache_{tracker_};
  std::unordered_map<uint64_t, RetainedReference> retained_;
  std::atomic<uint64_t> observed_resource_count_{};
  uint64_t observation_count_ = 0;
  uint64_t resource_count_ = 0;
  uint64_t last_summary_submission_ = 0;
  bool failure_recorded_ = false;
};

std::unique_ptr<TextureResourceBridge> g_texture_resource_bridge;

void ObserveNativeTextures(const NativeObservation& observation) {
  if (g_texture_resource_bridge) {
    g_texture_resource_bridge->Observe(observation);
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
  diagnostics::RecordEvent("native_renderer.texture_bridge.installed",
                           {{"backend", "d3d12"},
                            {"ownership", "explicit_retain_release"},
                            {"xenos_draw", "preserved"},
                            {"suppression", "disabled"}});
}

void UninstallTextureResourceBridge(rex::system::IGraphicsSystem* graphics_system) {
  if (graphics_system) {
    graphics_system->SetNativeTextureSetObserver(nullptr);
  }
  if (g_texture_resource_bridge) {
    g_texture_resource_bridge->Shutdown();
    g_texture_resource_bridge.reset();
  }
}

}  // namespace pinyon_shift::native_renderer
