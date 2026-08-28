#include <algorithm>
#include <array>
#include <atomic>
#include <bit>
#include <charconv>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <limits>
#include <span>
#include <string>
#include <type_traits>
#include <vector>

#include <fmt/format.h>
#include <rex/cvar.h>
#include <rex/graphics/xenos.h>
#include <rex/memory.h>
#include <rex/system/interfaces/graphics.h>
#include <rex/system/kernel_state.h>

#include "native_renderer/graphics_hooks.h"
#include "pinyon_shift_diagnostics.h"

REXCVAR_DEFINE_BOOL(
    pinyon_shift_native_renderer_census, false, "Pinyon Shift",
    "Record bounded native-renderer census metadata without changing rendering")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

namespace {

constexpr uint64_t kFrameSummaryInterval = 300;
constexpr size_t kSignatureCapacity = 4096;
constexpr size_t kSummaryLimit = 16;
constexpr size_t kCandidateSummaryLimit = 32;
constexpr size_t kPreparedShaderPairCapacity = 1024;
constexpr size_t kResolveTargetCapacity = 4096;
constexpr size_t kResolvePageCapacity = 32768;
constexpr size_t kResolveSummaryLimit = 32;
constexpr uint64_t kGuestPageSize = 4096;
constexpr uint64_t kPhysicalApertureSize = UINT64_C(0x20000000);
constexpr uint32_t kVertexIndexMask = 0x00FFFFFF;
constexpr uint32_t kMaximumIndexScanCount = 1 << 20;
constexpr uint64_t kMaximumIndexScanBytes = UINT64_C(4) << 20;
constexpr uint32_t kMaximumTextureScanResources = 4;
constexpr uint64_t kMaximumTextureScanResourceBytes = UINT64_C(16) << 20;
constexpr uint64_t kMaximumTextureScanTotalBytes = UINT64_C(32) << 20;
std::atomic<uint64_t> g_frame_sequence{};

std::string CensusSceneMarker() {
  char *value = nullptr;
  size_t length = 0;
  if (_dupenv_s(&value, &length, "PINYON_SHIFT_NATIVE_RENDERER_SCENE") != 0 ||
      !value || length <= 1) {
    std::free(value);
    return "unmarked";
  }
  std::string marker(value);
  std::free(value);
  if (marker.size() > 32 ||
      !std::all_of(marker.begin(), marker.end(), [](unsigned char character) {
        return (character >= 'a' && character <= 'z') || character == '_';
      })) {
    return "invalid";
  }
  return marker;
}

struct IndexScanState {
  uint64_t target_signature = 0;
  bool requested = false;
  bool completed = false;
  bool valid = true;
};

IndexScanState g_index_scan;

struct TextureScanState {
  uint64_t target_signature = 0;
  bool requested = false;
  bool completed = false;
  bool valid = true;
};

TextureScanState g_texture_scan;

struct ReplaySnapshotState {
  uint64_t target_signature = 0;
  std::filesystem::path output_root;
  bool requested = false;
  bool completed = false;
  bool valid = true;
};

ReplaySnapshotState g_replay_snapshot;

struct IsolatedDrawState {
  uint64_t target_signature = 0;
  uint64_t prepared_signature = 0;
  uint64_t frame = 0;
  uint64_t draw = 0;
  bool requested = false;
  bool completed = false;
  bool valid = true;
  bool prepared_candidate_valid = false;
  bool prepared_candidate_eligible = false;
};

IsolatedDrawState g_isolated_draw;

void ConfigureSignatureScan(const char *name, uint64_t &target_signature,
                            bool &requested, bool &valid) {
  char *value = nullptr;
  size_t length = 0;
  if (_dupenv_s(&value, &length, name) != 0 || !value || length <= 1) {
    std::free(value);
    return;
  }
  const std::string setting(value);
  std::free(value);
  requested = true;
  if (setting.size() != 16) {
    valid = false;
    return;
  }
  const char *begin = setting.data();
  const char *end = begin + setting.size();
  const auto parsed = std::from_chars(begin, end, target_signature, 16);
  if (parsed.ec != std::errc{} || parsed.ptr != end || !target_signature) {
    valid = false;
  }
}

void ConfigureIndexScan() {
  g_index_scan = {};
  ConfigureSignatureScan("PINYON_SHIFT_NATIVE_RENDERER_INDEX_SCAN_SIGNATURE",
                         g_index_scan.target_signature,
                         g_index_scan.requested, g_index_scan.valid);
}

void ConfigureTextureScan() {
  g_texture_scan = {};
  ConfigureSignatureScan(
      "PINYON_SHIFT_NATIVE_RENDERER_TEXTURE_SCAN_SIGNATURE",
      g_texture_scan.target_signature, g_texture_scan.requested,
      g_texture_scan.valid);
}

bool IsLocalArtifactRoot(const std::filesystem::path &path) {
  return path.is_absolute() &&
         std::any_of(path.begin(), path.end(), [](const auto &component) {
           return component.native() == L".local";
         });
}

void ConfigureReplaySnapshot() {
  g_replay_snapshot = {};
  ConfigureSignatureScan(
      "PINYON_SHIFT_NATIVE_RENDERER_SNAPSHOT_SIGNATURE",
      g_replay_snapshot.target_signature, g_replay_snapshot.requested,
      g_replay_snapshot.valid);
  const bool signature_requested = g_replay_snapshot.requested;
  char *value = nullptr;
  size_t length = 0;
  if (_dupenv_s(&value, &length,
                "PINYON_SHIFT_NATIVE_RENDERER_SNAPSHOT_DIR") != 0 ||
      !value || length <= 1) {
    std::free(value);
    if (g_replay_snapshot.requested) {
      g_replay_snapshot.valid = false;
    }
    return;
  }
  g_replay_snapshot.requested = true;
  g_replay_snapshot.output_root =
      std::filesystem::absolute(std::filesystem::path(value)).lexically_normal();
  std::free(value);
  if (!signature_requested ||
      !IsLocalArtifactRoot(g_replay_snapshot.output_root)) {
    g_replay_snapshot.valid = false;
  }
}

void ConfigureIsolatedDraw() {
  g_isolated_draw = {};
  ConfigureSignatureScan(
      "PINYON_SHIFT_NATIVE_RENDERER_ISOLATED_DRAW_SIGNATURE",
      g_isolated_draw.target_signature, g_isolated_draw.requested,
      g_isolated_draw.valid);
}

struct DrawSignatureEntry {
  uint64_t signature = 0;
  uint64_t draw_count = 0;
  uint64_t first_frame = 0;
  uint64_t last_frame = 0;
  uint32_t min_index_count = 0;
  uint32_t max_index_count = 0;
  uint32_t min_index_buffer_length = 0;
  uint64_t vertex_specialization_mask = 0;
  uint64_t pixel_specialization_mask = 0;
  rex::system::GraphicsPreparedDrawObservation prepared_sample;
  bool samples_resolved_target = false;
  rex::system::GraphicsDrawObservation sample;
};

struct DrawCensus {
  std::array<DrawSignatureEntry, kSignatureCapacity> entries{};
  uint64_t window_first_frame = 0;
  uint64_t window_last_frame = 0;
  uint64_t window_draw_count = 0;
  uint64_t unique_signature_count = 0;
  uint64_t overflow_draw_count = 0;
};

DrawCensus g_draw_census;
DrawCensus g_candidate_census;

struct PreparedShaderPairEntry {
  uint64_t identity = 0;
  rex::system::GraphicsPreparedDrawObservation sample;
};

std::array<PreparedShaderPairEntry, kPreparedShaderPairCapacity>
    g_prepared_shader_pairs{};
uint64_t g_prepared_shader_pair_count = 0;
uint64_t g_prepared_shader_pair_overflow = 0;
uint64_t g_candidate_unprepared_draw_count = 0;
uint64_t g_candidate_prepared_without_observation_count = 0;
bool g_graphics_census_installed = false;

struct PendingCandidateObservation {
  rex::system::GraphicsDrawObservation sample;
  bool samples_resolved_target = false;
  bool valid = false;
};

thread_local PendingCandidateObservation g_pending_candidate;

struct ResolveTargetEntry {
  uint32_t address = 0;
  uint32_t length = 0;
  uint32_t maximum_length = 0;
  uint32_t last_fetch_index = 0;
  uint64_t resolve_count = 0;
  uint64_t resolved_bytes = 0;
  uint64_t first_resolve_frame = 0;
  uint64_t last_resolve_frame = 0;
  uint64_t sampled_draw_count = 0;
  uint64_t sample_reference_count = 0;
  uint64_t first_sample_frame = 0;
  uint64_t last_sample_frame = 0;
  uint64_t conditional_sample_draw_count = 0;
  uint64_t query_state_sample_draw_count = 0;
  uint64_t memexport_sample_draw_count = 0;
  uint64_t window_resolve_count = 0;
  uint64_t window_sampled_draw_count = 0;
  bool last_fetch_was_mip = false;
  rex::system::GraphicsCopyObservation sample;
};

struct ResolvePageEntry {
  uint32_t page = 0;
  uint32_t target_index_plus_one = 0;
};

struct DependencyCensus {
  std::array<ResolveTargetEntry, kResolveTargetCapacity> targets{};
  std::array<ResolvePageEntry, kResolvePageCapacity> pages{};
  uint64_t window_first_frame = 0;
  uint64_t window_last_frame = 0;
  uint64_t window_resolve_count = 0;
  uint64_t window_resolve_bytes = 0;
  uint64_t window_failed_copy_count = 0;
  uint64_t window_zero_length_copy_count = 0;
  uint64_t window_sampled_draw_count = 0;
  uint64_t window_sample_reference_count = 0;
  uint64_t window_sampled_target_count = 0;
  uint64_t window_query_draw_count = 0;
  uint64_t window_memexport_draw_count = 0;
  uint64_t target_count = 0;
  uint64_t target_overflow_count = 0;
  uint64_t page_count = 0;
  uint64_t page_overflow_count = 0;
};

DependencyCensus g_dependency_census;

static_assert(std::is_trivially_copyable_v<DrawCensus>);
static_assert(std::is_trivially_copyable_v<DependencyCensus>);

void ResetDrawCensus() {
  std::memset(&g_draw_census, 0, sizeof(g_draw_census));
  std::memset(&g_candidate_census, 0, sizeof(g_candidate_census));
}

void ResetPreparedShaderPairs() {
  std::memset(g_prepared_shader_pairs.data(), 0,
              sizeof(g_prepared_shader_pairs));
  g_prepared_shader_pair_count = 0;
  g_prepared_shader_pair_overflow = 0;
  g_candidate_unprepared_draw_count = 0;
  g_candidate_prepared_without_observation_count = 0;
  g_pending_candidate.valid = false;
}

void ResetDependencyCensus() {
  std::memset(&g_dependency_census, 0, sizeof(g_dependency_census));
}

uint64_t HashCombine(uint64_t hash, uint64_t value) {
  value += 0x9E3779B97F4A7C15ull + (hash << 6) + (hash >> 2);
  return hash ^ value;
}

uint64_t PreparedPipelineHash(
    const rex::system::GraphicsPreparedDrawObservation &prepared) {
  uint64_t hash = 0xCBF29CE484222325ull;
  for (uint64_t value :
       {uint64_t(prepared.guest_primitive_type),
        uint64_t(prepared.host_primitive_type),
        uint64_t(prepared.host_vertex_shader_type),
        uint64_t(prepared.tessellation_mode),
        uint64_t(prepared.index_buffer_type),
        uint64_t(prepared.host_index_format),
        uint64_t(prepared.host_primitive_reset_enabled),
        uint64_t(prepared.normalized_depth_control),
        uint64_t(prepared.normalized_color_mask),
        uint64_t(prepared.bound_render_target_bits), uint64_t(prepared.flags)}) {
    hash = HashCombine(hash, value);
  }
  for (uint32_t format : prepared.bound_render_target_formats) {
    hash = HashCombine(hash, format);
  }
  return hash ? hash : 1;
}

uint64_t HashBytes(const uint8_t *data, uint64_t length) {
  uint64_t hash = 0xCBF29CE484222325ull;
  for (uint64_t i = 0; i < length; ++i) {
    hash ^= data[i];
    hash *= 0x100000001B3ull;
  }
  return hash;
}

void TryFingerprintCandidateTextures(
    const rex::system::GraphicsDrawObservation &observation,
    uint64_t signature) {
  if (!g_texture_scan.requested || !g_texture_scan.valid ||
      g_texture_scan.completed ||
      signature != g_texture_scan.target_signature) {
    return;
  }
  g_texture_scan.completed = true;

  const auto reject = [&](const char *reason) {
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.census.texture_scan",
        {{"signature", fmt::format("{:016X}", signature)},
         {"status", "rejected"},
         {"reason", reason},
         {"frame", std::to_string(observation.frame_sequence)},
         {"draw", std::to_string(observation.draw_sequence)},
         {"guest_payload_read", "false"},
         {"native_upload", "false"},
         {"native_draw", "false"},
         {"suppression_eligible", "false"}});
  };

  const uint32_t resource_count = std::popcount(observation.texture_fetch_mask);
  if (!resource_count || resource_count > kMaximumTextureScanResources ||
      observation.texture_state_overflow) {
    reject("texture_resource_count_out_of_bounds");
    return;
  }
  if ((observation.texture_fetch_layout_valid_mask &
       observation.texture_fetch_mask) != observation.texture_fetch_mask) {
    reject("texture_layout_unavailable");
    return;
  }

  uint64_t total_bytes = 0;
  for (uint32_t fetch = 0; fetch < 32; ++fetch) {
    if (!(observation.texture_fetch_mask & (uint32_t(1) << fetch))) {
      continue;
    }
    const uint64_t base_address =
        observation.texture_fetch_addresses[fetch] & UINT64_C(0x1FFFFFFF);
    const uint64_t base_length = observation.texture_fetch_base_lengths[fetch];
    const uint64_t mip_address =
        observation.texture_fetch_mip_addresses[fetch] & UINT64_C(0x1FFFFFFF);
    const uint64_t mip_length = observation.texture_fetch_mip_lengths[fetch];
    if (!base_length || base_length > kMaximumTextureScanResourceBytes ||
        mip_length > kMaximumTextureScanResourceBytes ||
        base_address + base_length > kPhysicalApertureSize ||
        (mip_length && (!mip_address ||
                        mip_address + mip_length > kPhysicalApertureSize))) {
      reject("texture_allocation_out_of_bounds");
      return;
    }
    total_bytes += base_length + mip_length;
    if (total_bytes > kMaximumTextureScanTotalBytes) {
      reject("texture_scan_total_out_of_bounds");
      return;
    }
  }

  auto *kernel_state = rex::system::kernel_state();
  if (!kernel_state || !kernel_state->memory()) {
    reject("guest_memory_unavailable");
    return;
  }

  uint32_t resource = 0;
  for (uint32_t fetch = 0; fetch < 32; ++fetch) {
    if (!(observation.texture_fetch_mask & (uint32_t(1) << fetch))) {
      continue;
    }
    const uint32_t base_address = observation.texture_fetch_addresses[fetch];
    const uint32_t base_length =
        observation.texture_fetch_base_lengths[fetch];
    const uint32_t mip_address =
        observation.texture_fetch_mip_addresses[fetch];
    const uint32_t mip_length = observation.texture_fetch_mip_lengths[fetch];
    const uint8_t *base =
        kernel_state->memory()->TranslatePhysical<const uint8_t *>(base_address);
    const uint64_t base_hash = HashBytes(base, base_length);
    uint64_t mip_hash = 0;
    if (mip_length) {
      const uint8_t *mip =
          kernel_state->memory()->TranslatePhysical<const uint8_t *>(mip_address);
      mip_hash = HashBytes(mip, mip_length);
    }
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.census.texture_fingerprint",
        {{"signature", fmt::format("{:016X}", signature)},
         {"resource", std::to_string(resource++)},
         {"fetch_constant", std::to_string(fetch)},
         {"base_address", fmt::format("{:08X}", base_address)},
         {"base_bytes", std::to_string(base_length)},
         {"base_hash", fmt::format("{:016X}", base_hash)},
         {"mip_address", fmt::format("{:08X}", mip_address)},
         {"mip_bytes", std::to_string(mip_length)},
         {"mip_hash", mip_length ? fmt::format("{:016X}", mip_hash) : ""},
         {"guest_payload_read", "bounded_texture_only"},
         {"native_upload", "false"},
         {"native_draw", "false"},
         {"suppression_eligible", "false"}});
  }
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.census.texture_scan",
      {{"signature", fmt::format("{:016X}", signature)},
       {"status", "scanned"},
       {"frame", std::to_string(observation.frame_sequence)},
       {"draw", std::to_string(observation.draw_sequence)},
       {"resources", std::to_string(resource_count)},
       {"bytes_read", std::to_string(total_bytes)},
       {"guest_payload_read", "bounded_texture_only"},
       {"native_upload", "false"},
       {"native_draw", "false"},
       {"suppression_eligible", "false"}});
}

void TryScanCandidateIndices(
    const rex::system::GraphicsDrawObservation &observation,
    uint64_t signature) {
  if (!g_index_scan.requested || !g_index_scan.valid ||
      g_index_scan.completed || signature != g_index_scan.target_signature) {
    return;
  }
  g_index_scan.completed = true;

  const auto reject = [&](const char *reason) {
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.census.index_scan",
        {{"signature", fmt::format("{:016X}", signature)},
         {"status", "rejected"},
         {"reason", reason},
         {"frame", std::to_string(observation.frame_sequence)},
         {"draw", std::to_string(observation.draw_sequence)},
         {"guest_payload_read", "false"},
         {"native_upload", "false"},
         {"native_draw", "false"},
         {"suppression_eligible", "false"}});
  };

  if (!observation.indexed ||
      observation.source_select !=
          uint32_t(rex::graphics::xenos::SourceSelect::kDMA)) {
    reject("not_dma_indexed");
    return;
  }
  if (observation.index_format > 1 || observation.index_endianness > 3) {
    reject("unsupported_index_state");
    return;
  }
  if (!observation.index_count ||
      observation.index_count > kMaximumIndexScanCount) {
    reject("index_count_out_of_bounds");
    return;
  }
  if (observation.vertex_index_min > observation.vertex_index_max) {
    reject("invalid_vertex_index_clamp");
    return;
  }
  if (observation.vertex_binding_count != 1 ||
      observation.vertex_binding_overflow) {
    reject("unsupported_vertex_bindings");
    return;
  }

  const uint32_t element_bytes = observation.index_format ? 4 : 2;
  const uint64_t required_bytes =
      uint64_t(observation.index_count) * element_bytes;
  const uint64_t physical_address =
      uint64_t(observation.index_buffer_address & 0x1FFFFFFF);
  if (required_bytes > kMaximumIndexScanBytes ||
      required_bytes > observation.index_buffer_length) {
    reject("index_allocation_too_small");
    return;
  }
  if (physical_address + required_bytes > kPhysicalApertureSize) {
    reject("index_range_crosses_aperture");
    return;
  }
  auto *kernel_state = rex::system::kernel_state();
  if (!kernel_state || !kernel_state->memory()) {
    reject("guest_memory_unavailable");
    return;
  }

  const uint8_t *payload =
      kernel_state->memory()->TranslatePhysical<const uint8_t *>(
          observation.index_buffer_address);
  auto endianness =
      static_cast<rex::graphics::xenos::Endian>(observation.index_endianness);
  if (!observation.index_format) {
    if (endianness == rex::graphics::xenos::Endian::k8in32) {
      endianness = rex::graphics::xenos::Endian::k8in16;
    } else if (endianness == rex::graphics::xenos::Endian::k16in32) {
      endianness = rex::graphics::xenos::Endian::kNone;
    }
  }

  uint32_t decoded_minimum = std::numeric_limits<uint32_t>::max();
  uint32_t decoded_maximum = 0;
  uint32_t effective_minimum = std::numeric_limits<uint32_t>::max();
  uint32_t effective_maximum = 0;
  uint32_t non_reset_count = 0;
  uint32_t reset_count = 0;
  uint64_t decoded_hash = 0xCBF29CE484222325ull;
  for (uint32_t i = 0; i < observation.index_count; ++i) {
    uint32_t decoded = 0;
    if (observation.index_format) {
      std::memcpy(&decoded, payload + uint64_t(i) * element_bytes,
                  sizeof(decoded));
      decoded = rex::graphics::xenos::GpuSwap(decoded, endianness);
    } else {
      uint16_t decoded16 = 0;
      std::memcpy(&decoded16, payload + uint64_t(i) * element_bytes,
                  sizeof(decoded16));
      decoded = rex::graphics::xenos::GpuSwap(decoded16, endianness);
    }
    decoded &= kVertexIndexMask;
    decoded_hash = HashCombine(decoded_hash, decoded);
    if (observation.index_reset_enabled &&
        decoded == (observation.index_reset & kVertexIndexMask)) {
      ++reset_count;
      continue;
    }
    decoded_minimum = std::min(decoded_minimum, decoded);
    decoded_maximum = std::max(decoded_maximum, decoded);
    const uint32_t adjusted =
        (decoded + observation.vertex_index_offset) & kVertexIndexMask;
    const uint32_t effective = std::clamp(
        adjusted, observation.vertex_index_min, observation.vertex_index_max);
    effective_minimum = std::min(effective_minimum, effective);
    effective_maximum = std::max(effective_maximum, effective);
    ++non_reset_count;
  }
  if (!non_reset_count) {
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.census.index_scan",
        {{"signature", fmt::format("{:016X}", signature)},
         {"status", "empty_after_reset"},
         {"frame", std::to_string(observation.frame_sequence)},
         {"draw", std::to_string(observation.draw_sequence)},
         {"index_count", std::to_string(observation.index_count)},
         {"bytes_read", std::to_string(required_bytes)},
         {"reset_count", std::to_string(reset_count)},
         {"guest_payload_read", "bounded_index_only"},
         {"native_upload", "false"},
         {"native_draw", "false"},
         {"suppression_eligible", "false"}});
    return;
  }

  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.census.index_scan",
      {{"signature", fmt::format("{:016X}", signature)},
       {"status", "scanned"},
       {"frame", std::to_string(observation.frame_sequence)},
       {"draw", std::to_string(observation.draw_sequence)},
       {"index_count", std::to_string(observation.index_count)},
       {"bytes_read", std::to_string(required_bytes)},
       {"index_buffer_address",
        fmt::format("{:08X}", observation.index_buffer_address)},
       {"index_buffer_length", std::to_string(observation.index_buffer_length)},
       {"index_format", std::to_string(observation.index_format)},
       {"index_endianness", std::to_string(observation.index_endianness)},
       {"index_reset_enabled",
        observation.index_reset_enabled ? "true" : "false"},
       {"index_reset", fmt::format("{:08X}", observation.index_reset)},
       {"decoded_minimum", std::to_string(decoded_minimum)},
       {"decoded_maximum", std::to_string(decoded_maximum)},
       {"effective_minimum", std::to_string(effective_minimum)},
       {"effective_maximum", std::to_string(effective_maximum)},
       {"non_reset_count", std::to_string(non_reset_count)},
       {"reset_count", std::to_string(reset_count)},
       {"decoded_hash", fmt::format("{:016X}", decoded_hash)},
       {"vertex_binding_address",
        fmt::format("{:08X}", observation.vertex_bindings[0].address)},
       {"vertex_binding_size",
        std::to_string(observation.vertex_bindings[0].size)},
       {"guest_payload_read", "bounded_index_only"},
       {"native_upload", "false"},
       {"native_draw", "false"},
       {"suppression_eligible", "false"}});
}

bool WriteSnapshotFile(const std::filesystem::path &path,
                       std::span<const uint8_t> bytes) {
  std::ofstream output(path, std::ios::binary | std::ios::trunc);
  return output.write(reinterpret_cast<const char *>(bytes.data()),
                      static_cast<std::streamsize>(bytes.size())) &&
         output.flush();
}

void AppendFloatConstants(
    std::string &document, const char *name,
    const rex::system::GraphicsFloatConstantObservation *constants,
    uint32_t count) {
  document += fmt::format("    \"{}\": [", name);
  const uint32_t bounded_count = std::min(
      count, rex::system::kGraphicsFloatConstantObservationLimit);
  for (uint32_t i = 0; i < bounded_count; ++i) {
    if (i) {
      document += ",";
    }
    document += fmt::format(
        "\n      {{\"index\":{},\"words\":[\"{:08X}\",\"{:08X}\","
        "\"{:08X}\",\"{:08X}\"]}}",
        constants[i].index, constants[i].values[0], constants[i].values[1],
        constants[i].values[2], constants[i].values[3]);
  }
  document += bounded_count ? "\n    ]" : "]";
}

struct SnapshotTexturePayload {
  uint32_t fetch_constant = 0;
  uint32_t base_address = 0;
  uint32_t mip_address = 0;
  std::vector<uint8_t> base;
  std::vector<uint8_t> mip;
};

void TryCaptureReplaySnapshot(
    const rex::system::GraphicsDrawObservation &observation,
    bool samples_resolved_target,
    const rex::system::GraphicsPreparedDrawObservation &prepared,
    uint64_t signature) {
  if (!g_replay_snapshot.requested || !g_replay_snapshot.valid ||
      g_replay_snapshot.completed ||
      signature != g_replay_snapshot.target_signature) {
    return;
  }
  g_replay_snapshot.completed = true;

  const auto reject = [&](const char *reason) {
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.snapshot.capture",
        {{"signature", fmt::format("{:016X}", signature)},
         {"status", "rejected"},
         {"reason", reason},
         {"frame", std::to_string(observation.frame_sequence)},
         {"draw", std::to_string(observation.draw_sequence)},
         {"guest_payload_read", "false"},
         {"payload_persisted", "false"},
         {"native_upload", "false"},
         {"native_draw", "false"},
         {"suppression_eligible", "false"}});
  };

  if (samples_resolved_target) {
    reject("observed_resolve_dependency");
    return;
  }
  if (!observation.indexed ||
      observation.source_select !=
          uint32_t(rex::graphics::xenos::SourceSelect::kDMA) ||
      observation.index_format > 1 || observation.index_endianness > 3 ||
      !observation.index_count ||
      observation.index_count > kMaximumIndexScanCount) {
    reject("unsupported_index_state");
    return;
  }
  if (observation.vertex_binding_count != 1 ||
      observation.vertex_binding_overflow ||
      observation.vertex_attribute_overflow ||
      observation.vertex_float_constant_overflow ||
      observation.pixel_float_constant_overflow ||
      observation.texture_state_overflow || observation.vertex_memexport ||
      observation.viz_query_condition || (observation.pa_sc_viz_query & 1)) {
    reject("unsupported_draw_state");
    return;
  }
  if ((prepared.flags & 3) != 3 ||
      !(prepared.bound_render_target_bits & 2)) {
    reject("inactive_prepared_pipeline");
    return;
  }

  const uint32_t index_element_bytes = observation.index_format ? 4 : 2;
  const uint64_t index_bytes =
      uint64_t(observation.index_count) * index_element_bytes;
  const auto &binding = observation.vertex_bindings[0];
  const uint64_t vertex_bytes = binding.size;
  constexpr uint64_t kMaximumVertexSnapshotBytes = UINT64_C(64) << 20;
  const uint64_t index_address =
      uint64_t(observation.index_buffer_address & 0x1FFFFFFF);
  const uint64_t vertex_address = uint64_t(binding.address & 0x1FFFFFFF);
  if (!vertex_bytes || index_bytes > kMaximumIndexScanBytes ||
      index_bytes > observation.index_buffer_length ||
      vertex_bytes > kMaximumVertexSnapshotBytes ||
      index_address + index_bytes > kPhysicalApertureSize ||
      vertex_address + vertex_bytes > kPhysicalApertureSize) {
    reject("geometry_range_out_of_bounds");
    return;
  }

  const uint32_t texture_count = std::popcount(observation.texture_fetch_mask);
  if (!texture_count || texture_count > kMaximumTextureScanResources ||
      (observation.texture_fetch_layout_valid_mask &
       observation.texture_fetch_mask) != observation.texture_fetch_mask) {
    reject("texture_layout_unavailable");
    return;
  }
  uint64_t texture_bytes = 0;
  for (uint32_t fetch = 0; fetch < 32; ++fetch) {
    if (!(observation.texture_fetch_mask & (uint32_t(1) << fetch))) {
      continue;
    }
    const uint64_t base_bytes =
        observation.texture_fetch_base_lengths[fetch];
    const uint64_t mip_bytes = observation.texture_fetch_mip_lengths[fetch];
    const uint64_t base_address =
        observation.texture_fetch_addresses[fetch] & 0x1FFFFFFF;
    const uint64_t mip_address =
        observation.texture_fetch_mip_addresses[fetch] & 0x1FFFFFFF;
    if (!base_bytes || base_bytes > kMaximumTextureScanResourceBytes ||
        mip_bytes > kMaximumTextureScanResourceBytes ||
        base_address + base_bytes > kPhysicalApertureSize ||
        (mip_bytes && mip_address + mip_bytes > kPhysicalApertureSize) ||
        base_bytes + mip_bytes >
            kMaximumTextureScanTotalBytes - texture_bytes) {
      reject("texture_range_out_of_bounds");
      return;
    }
    texture_bytes += base_bytes + mip_bytes;
  }

  auto *kernel_state = rex::system::kernel_state();
  if (!kernel_state || !kernel_state->memory()) {
    reject("guest_memory_unavailable");
    return;
  }
  auto *memory = kernel_state->memory();
  const auto copy_physical = [&](uint32_t address, uint64_t size) {
    std::vector<uint8_t> result(size);
    const uint8_t *source =
        memory->TranslatePhysical<const uint8_t *>(address);
    std::memcpy(result.data(), source, size);
    return result;
  };

  std::vector<uint8_t> index_payload =
      copy_physical(observation.index_buffer_address, index_bytes);
  std::vector<uint8_t> vertex_payload =
      copy_physical(binding.address, vertex_bytes);
  std::vector<SnapshotTexturePayload> textures;
  textures.reserve(texture_count);
  for (uint32_t fetch = 0; fetch < 32; ++fetch) {
    if (!(observation.texture_fetch_mask & (uint32_t(1) << fetch))) {
      continue;
    }
    SnapshotTexturePayload texture;
    texture.fetch_constant = fetch;
    texture.base_address = observation.texture_fetch_addresses[fetch];
    texture.mip_address = observation.texture_fetch_mip_addresses[fetch];
    texture.base = copy_physical(
        texture.base_address, observation.texture_fetch_base_lengths[fetch]);
    if (observation.texture_fetch_mip_lengths[fetch]) {
      texture.mip = copy_physical(
          texture.mip_address, observation.texture_fetch_mip_lengths[fetch]);
    }
    textures.push_back(std::move(texture));
  }

  std::filesystem::path staging = g_replay_snapshot.output_root;
  staging += L".partial";
  std::error_code error;
  if (std::filesystem::exists(g_replay_snapshot.output_root, error) || error ||
      std::filesystem::exists(staging, error) || error ||
      !std::filesystem::create_directories(staging, error) || error) {
    reject("output_directory_unavailable");
    return;
  }

  const auto write_payload = [&](const std::filesystem::path &name,
                                 std::span<const uint8_t> payload) {
    return WriteSnapshotFile(staging / name, payload);
  };
  if (!write_payload(L"index.bin", index_payload) ||
      !write_payload(L"vertex.bin", vertex_payload)) {
    reject("geometry_write_failed");
    return;
  }
  for (const auto &texture : textures) {
    const auto base_name =
        std::filesystem::path(fmt::format("texture_{:02}_base.bin",
                                         texture.fetch_constant));
    if (!write_payload(base_name, texture.base)) {
      reject("texture_write_failed");
      return;
    }
    if (!texture.mip.empty()) {
      const auto mip_name =
          std::filesystem::path(fmt::format("texture_{:02}_mip.bin",
                                           texture.fetch_constant));
      if (!write_payload(mip_name, texture.mip)) {
        reject("texture_write_failed");
        return;
      }
    }
  }

  std::string document = fmt::format(
      "{{\n  \"schema\": \"pinyon-shift.native-replay-snapshot.v1\",\n"
      "  \"candidate_signature\": \"{:016X}\",\n"
      "  \"frame\": {},\n  \"draw\": {},\n"
      "  \"shaders\": {{\"vertex\":\"{:016X}\",\"pixel\":\"{:016X}\","
      "\"vertex_specialization\":\"{:016X}\","
      "\"pixel_specialization\":\"{:016X}\"}},\n"
      "  \"prepared_pipeline_hash\": \"{:016X}\",\n"
      "  \"prepared_pipeline\": {{\"guest_primitive\":{},"
      "\"host_primitive\":{},\"host_vertex_shader_type\":{},"
      "\"tessellation_mode\":{},\"index_buffer_type\":{},"
      "\"host_index_format\":{},\"host_primitive_reset\":{},"
      "\"depth_control\":\"{:08X}\",\"color_mask\":\"{:08X}\","
      "\"target_bits\":\"{:08X}\","
      "\"target_formats\":[{},{},{},{},{}],\"flags\":\"{:08X}\"}},\n"
      "  \"geometry\": {{\n"
      "    \"index\": {{\"file\":\"index.bin\",\"bytes\":{},"
      "\"hash\":\"{:016X}\",\"address\":\"{:08X}\","
      "\"format\":{},\"endianness\":{},\"count\":{}}},\n"
      "    \"vertex\": {{\"file\":\"vertex.bin\",\"bytes\":{},"
      "\"hash\":\"{:016X}\",\"address\":\"{:08X}\","
      "\"fetch_constant\":{},\"stride_words\":{},"
      "\"endianness\":{}}}\n  }},\n  \"textures\": [",
      signature, observation.frame_sequence, observation.draw_sequence,
      prepared.vertex_shader_hash, prepared.pixel_shader_hash,
      prepared.vertex_specialization_mask, prepared.pixel_specialization_mask,
      PreparedPipelineHash(prepared), prepared.guest_primitive_type,
      prepared.host_primitive_type, prepared.host_vertex_shader_type,
      prepared.tessellation_mode, prepared.index_buffer_type,
      prepared.host_index_format, prepared.host_primitive_reset_enabled,
      prepared.normalized_depth_control, prepared.normalized_color_mask,
      prepared.bound_render_target_bits, prepared.bound_render_target_formats[0],
      prepared.bound_render_target_formats[1],
      prepared.bound_render_target_formats[2],
      prepared.bound_render_target_formats[3],
      prepared.bound_render_target_formats[4], prepared.flags,
      index_payload.size(), HashBytes(index_payload.data(), index_payload.size()),
      observation.index_buffer_address, observation.index_format,
      observation.index_endianness, observation.index_count,
      vertex_payload.size(),
      HashBytes(vertex_payload.data(), vertex_payload.size()), binding.address,
      binding.fetch_constant, binding.stride_words, binding.endianness);
  for (size_t i = 0; i < textures.size(); ++i) {
    const auto &texture = textures[i];
    if (i) {
      document += ",";
    }
    document += fmt::format(
        "\n    {{\"fetch_constant\":{},\"base_file\":"
        "\"texture_{:02}_base.bin\",\"base_bytes\":{},"
        "\"base_hash\":\"{:016X}\",\"base_address\":\"{:08X}\","
        "\"mip_file\":{},\"mip_bytes\":{},\"mip_hash\":{},"
        "\"mip_address\":\"{:08X}\"}}",
        texture.fetch_constant, texture.fetch_constant, texture.base.size(),
        HashBytes(texture.base.data(), texture.base.size()),
        texture.base_address,
        texture.mip.empty()
            ? "null"
            : fmt::format("\"texture_{:02}_mip.bin\"",
                          texture.fetch_constant),
        texture.mip.size(),
        texture.mip.empty()
            ? "null"
            : fmt::format("\"{:016X}\"",
                          HashBytes(texture.mip.data(), texture.mip.size())),
        texture.mip_address);
  }
  document += "\n  ],\n  \"constants\": {\n";
  AppendFloatConstants(document, "vertex_float",
                       observation.vertex_float_constants,
                       observation.vertex_float_constant_count);
  document += ",\n";
  AppendFloatConstants(document, "pixel_float",
                       observation.pixel_float_constants,
                       observation.pixel_float_constant_count);
  document += ",\n    \"bool_bitmap\": [";
  for (uint32_t i = 0; i < 8; ++i) {
    document += fmt::format("{}\"{:08X}\"", i ? "," : "",
                            observation.bool_constant_bitmap[i]);
  }
  document += "],\n    \"bool_values\": [";
  for (uint32_t i = 0; i < 8; ++i) {
    document += fmt::format("{}\"{:08X}\"", i ? "," : "",
                            observation.bool_constant_values[i]);
  }
  document += fmt::format(
      "],\n    \"loop_bitmap\": \"{:08X}\",\n"
      "    \"loop_values\": [",
      observation.loop_constant_bitmap);
  for (uint32_t i = 0; i < 32; ++i) {
    document += fmt::format("{}\"{:08X}\"", i ? "," : "",
                            observation.loop_constant_values[i]);
  }
  document += "],\n    \"texture_states\": [";
  const uint32_t texture_state_count = std::min(
      observation.texture_state_count,
      rex::system::kGraphicsTextureFetchObservationLimit);
  for (uint32_t i = 0; i < texture_state_count; ++i) {
    const auto &state = observation.texture_states[i];
    if (i) {
      document += ",";
    }
    document += fmt::format(
        "\n      {{\"stage\":{},\"fetch_constant\":{},"
        "\"dwords\":[\"{:08X}\",\"{:08X}\",\"{:08X}\",\"{:08X}\","
        "\"{:08X}\",\"{:08X}\"],\"opcode\":{},\"dimension\":{},"
        "\"filters\":\"{:08X}\",\"flags\":\"{:08X}\","
        "\"lod_bias\":\"{:08X}\",\"offsets\":\"{:08X}\","
        "\"result_target\":{},\"result_index\":{},"
        "\"result_mask\":{},\"result_components\":{}}}",
        state.stage, state.fetch_constant, state.dwords[0], state.dwords[1],
        state.dwords[2], state.dwords[3], state.dwords[4], state.dwords[5],
        state.opcode, state.dimension, state.filters, state.flags,
        state.lod_bias, state.offsets, state.result_storage_target,
        state.result_storage_index, state.result_write_mask,
        state.result_components);
  }
  document += texture_state_count ? "\n    ]\n" : "]\n";
  document +=
      "  },\n  \"safety\": {\"guest_payload_read\":"
      "\"bounded_snapshot_only\",\"payload_scope\":\"local_only\","
      "\"native_upload\":false,\"native_draw\":false,"
      "\"suppression_allowed\":false,\"xenos_authority\":true}\n}\n";
  const auto manifest_bytes = std::span(
      reinterpret_cast<const uint8_t *>(document.data()), document.size());
  if (!write_payload(L"snapshot.json", manifest_bytes)) {
    reject("manifest_write_failed");
    return;
  }
  std::filesystem::rename(staging, g_replay_snapshot.output_root, error);
  if (error) {
    reject("snapshot_commit_failed");
    return;
  }

  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.snapshot.capture",
      {{"signature", fmt::format("{:016X}", signature)},
       {"status", "captured"},
       {"frame", std::to_string(observation.frame_sequence)},
       {"draw", std::to_string(observation.draw_sequence)},
       {"index_bytes", std::to_string(index_payload.size())},
       {"vertex_bytes", std::to_string(vertex_payload.size())},
       {"texture_resources", std::to_string(textures.size())},
       {"texture_bytes", std::to_string(texture_bytes)},
       {"guest_payload_read", "bounded_snapshot_only"},
       {"payload_persisted", "local_only"},
       {"native_upload", "false"},
       {"native_draw", "false"},
       {"suppression_eligible", "false"}});
}

uint64_t DrawStateHash(
    const rex::system::GraphicsDrawObservation &observation) {
  uint64_t hash = 0xCBF29CE484222325ull;
  const auto hash_float_constants = [&](const auto *constants, uint32_t count) {
    const uint32_t bounded_count = std::min(
        count, rex::system::kGraphicsFloatConstantObservationLimit);
    for (uint32_t i = 0; i < bounded_count; ++i) {
      hash = HashCombine(hash, constants[i].index);
      for (uint32_t value : constants[i].values) {
        hash = HashCombine(hash, value);
      }
    }
  };
  hash_float_constants(observation.vertex_float_constants,
                       observation.vertex_float_constant_count);
  hash_float_constants(observation.pixel_float_constants,
                       observation.pixel_float_constant_count);
  for (uint32_t i = 0; i < 8; ++i) {
    hash = HashCombine(hash, observation.bool_constant_bitmap[i]);
    hash = HashCombine(hash, observation.bool_constant_values[i] &
                                 observation.bool_constant_bitmap[i]);
  }
  hash = HashCombine(hash, observation.loop_constant_bitmap);
  for (uint32_t i = 0; i < 32; ++i) {
    if (observation.loop_constant_bitmap & (1u << i)) {
      hash = HashCombine(hash, observation.loop_constant_values[i]);
    }
  }
  const uint32_t texture_count = std::min(
      observation.texture_state_count,
      rex::system::kGraphicsTextureFetchObservationLimit);
  for (uint32_t i = 0; i < texture_count; ++i) {
    const auto &state = observation.texture_states[i];
    for (uint32_t value :
         {state.stage, state.fetch_constant, state.opcode, state.dimension,
          state.filters, state.flags, state.lod_bias, state.offsets,
          state.result_storage_target, state.result_storage_index,
          state.result_write_mask, state.result_components}) {
      hash = HashCombine(hash, value);
    }
    for (uint32_t value : state.dwords) {
      hash = HashCombine(hash, value);
    }
  }
  return hash ? hash : 1;
}

std::string SerializeFloatConstants(
    const rex::system::GraphicsFloatConstantObservation *constants,
    uint32_t count) {
  std::string result;
  const uint32_t bounded_count = std::min(
      count, rex::system::kGraphicsFloatConstantObservationLimit);
  for (uint32_t i = 0; i < bounded_count; ++i) {
    if (!result.empty()) {
      result += ";";
    }
    result += fmt::format("{}:{:08X}:{:08X}:{:08X}:{:08X}",
                          constants[i].index, constants[i].values[0],
                          constants[i].values[1], constants[i].values[2],
                          constants[i].values[3]);
  }
  return result;
}

std::string SerializeWordConstants(const uint32_t *bitmap,
                                   const uint32_t *values,
                                   uint32_t word_count) {
  std::string result;
  for (uint32_t i = 0; i < word_count; ++i) {
    if (!bitmap[i]) {
      continue;
    }
    if (!result.empty()) {
      result += ";";
    }
    result += fmt::format("{}:{:08X}:{:08X}", i, bitmap[i], values[i]);
  }
  return result;
}

std::string SerializeLoopConstants(uint32_t bitmap, const uint32_t *values) {
  std::string result;
  for (uint32_t i = 0; i < 32; ++i) {
    if (!(bitmap & (uint32_t(1) << i))) {
      continue;
    }
    if (!result.empty()) {
      result += ";";
    }
    result += fmt::format("{}:{:08X}", i, values[i]);
  }
  return result;
}

std::string SerializeTextureStates(
    const rex::system::GraphicsDrawObservation &observation) {
  std::string result;
  const uint32_t bounded_count = std::min(
      observation.texture_state_count,
      rex::system::kGraphicsTextureFetchObservationLimit);
  for (uint32_t i = 0; i < bounded_count; ++i) {
    const auto &state = observation.texture_states[i];
    if (!result.empty()) {
      result += ";";
    }
    result += fmt::format(
        "{}:{}:{:08X}:{:08X}:{:08X}:{:08X}:{:08X}:{:08X}:{}:{}:{:06X}:"
        "{:02X}:{:08X}:{:06X}:{}:{}:{:X}:{:X}",
        state.stage, state.fetch_constant, state.dwords[0], state.dwords[1],
        state.dwords[2], state.dwords[3], state.dwords[4], state.dwords[5],
        state.opcode, state.dimension, state.filters, state.flags,
        state.lod_bias, state.offsets, state.result_storage_target,
        state.result_storage_index, state.result_write_mask,
        state.result_components);
  }
  return result;
}

size_t ResolveTargetIndex(uint32_t address) {
  size_t index = size_t(HashCombine(0xCBF29CE484222325ull, address) %
                        kResolveTargetCapacity);
  for (size_t probe = 0; probe < kResolveTargetCapacity; ++probe) {
    const ResolveTargetEntry &entry = g_dependency_census.targets[index];
    if (!entry.resolve_count || entry.address == address) {
      return index;
    }
    index = (index + 1) % kResolveTargetCapacity;
  }
  return kResolveTargetCapacity;
}

void MapResolvePage(uint32_t page, size_t target_index) {
  size_t index =
      size_t(HashCombine(0x9E3779B97F4A7C15ull, page) % kResolvePageCapacity);
  for (size_t probe = 0; probe < kResolvePageCapacity; ++probe) {
    ResolvePageEntry &entry = g_dependency_census.pages[index];
    if (!entry.target_index_plus_one) {
      entry.page = page;
      entry.target_index_plus_one = uint32_t(target_index + 1);
      ++g_dependency_census.page_count;
      return;
    }
    if (entry.page == page) {
      entry.target_index_plus_one = uint32_t(target_index + 1);
      return;
    }
    index = (index + 1) % kResolvePageCapacity;
  }
  ++g_dependency_census.page_overflow_count;
}

void MapResolveRange(size_t target_index, uint32_t address, uint32_t length) {
  const uint64_t first_page = uint64_t(address) / kGuestPageSize;
  const uint64_t last_address = uint64_t(address) + uint64_t(length) - 1;
  const uint64_t last_page = last_address / kGuestPageSize;
  const uint64_t page_count = last_page - first_page + 1;
  const uint64_t bounded_page_count =
      std::min<uint64_t>(page_count, kResolvePageCapacity);
  for (uint64_t offset = 0; offset < bounded_page_count; ++offset) {
    MapResolvePage(uint32_t(first_page + offset), target_index);
  }
  if (page_count > bounded_page_count) {
    g_dependency_census.page_overflow_count += page_count - bounded_page_count;
  }
}

size_t FindResolveTarget(uint32_t address) {
  const uint32_t page = uint32_t(uint64_t(address) / kGuestPageSize);
  size_t index =
      size_t(HashCombine(0x9E3779B97F4A7C15ull, page) % kResolvePageCapacity);
  for (size_t probe = 0; probe < kResolvePageCapacity; ++probe) {
    const ResolvePageEntry &page_entry = g_dependency_census.pages[index];
    if (!page_entry.target_index_plus_one) {
      return kResolveTargetCapacity;
    }
    if (page_entry.page == page) {
      const size_t target_index = page_entry.target_index_plus_one - 1;
      const ResolveTargetEntry &target =
          g_dependency_census.targets[target_index];
      const uint64_t target_end =
          uint64_t(target.address) + uint64_t(target.length);
      return address >= target.address && uint64_t(address) < target_end
                 ? target_index
                 : kResolveTargetCapacity;
    }
    index = (index + 1) % kResolvePageCapacity;
  }
  return kResolveTargetCapacity;
}

void BeginDependencyWindow(uint64_t frame) {
  if (!g_dependency_census.window_first_frame) {
    g_dependency_census.window_first_frame = frame;
  }
  g_dependency_census.window_last_frame =
      std::max(g_dependency_census.window_last_frame, frame);
}

void ResetDependencyWindow() {
  g_dependency_census.window_first_frame = 0;
  g_dependency_census.window_last_frame = 0;
  g_dependency_census.window_resolve_count = 0;
  g_dependency_census.window_resolve_bytes = 0;
  g_dependency_census.window_failed_copy_count = 0;
  g_dependency_census.window_zero_length_copy_count = 0;
  g_dependency_census.window_sampled_draw_count = 0;
  g_dependency_census.window_sample_reference_count = 0;
  g_dependency_census.window_sampled_target_count = 0;
  g_dependency_census.window_query_draw_count = 0;
  g_dependency_census.window_memexport_draw_count = 0;
  for (ResolveTargetEntry &target : g_dependency_census.targets) {
    target.window_resolve_count = 0;
    target.window_sampled_draw_count = 0;
  }
}

void EmitDependencyCensusWindow() {
  if (!g_dependency_census.window_first_frame) {
    return;
  }

  const auto number = [](uint64_t value) { return std::to_string(value); };
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.census.resolve_window",
      {{"first_frame", number(g_dependency_census.window_first_frame)},
       {"last_frame", number(g_dependency_census.window_last_frame)},
       {"resolves", number(g_dependency_census.window_resolve_count)},
       {"resolve_bytes", number(g_dependency_census.window_resolve_bytes)},
       {"failed_copies", number(g_dependency_census.window_failed_copy_count)},
       {"zero_length_copies",
        number(g_dependency_census.window_zero_length_copy_count)},
       {"sampled_draws", number(g_dependency_census.window_sampled_draw_count)},
       {"sample_references",
        number(g_dependency_census.window_sample_reference_count)},
       {"sampled_targets",
        number(g_dependency_census.window_sampled_target_count)},
       {"query_draws", number(g_dependency_census.window_query_draw_count)},
       {"memexport_draws",
        number(g_dependency_census.window_memexport_draw_count)},
       {"tracked_targets", number(g_dependency_census.target_count)},
       {"target_overflow", number(g_dependency_census.target_overflow_count)},
       {"tracked_pages", number(g_dependency_census.page_count)},
       {"page_overflow", number(g_dependency_census.page_overflow_count)},
       {"target_capacity", "4096"},
       {"page_capacity", "32768"},
       {"summary_limit", "32"}});

  std::array<size_t, kResolveTargetCapacity> order{};
  for (size_t i = 0; i < order.size(); ++i) {
    order[i] = i;
  }
  std::sort(order.begin(), order.end(), [](size_t left, size_t right) {
    const ResolveTargetEntry &left_entry = g_dependency_census.targets[left];
    const ResolveTargetEntry &right_entry = g_dependency_census.targets[right];
    const uint64_t left_activity =
        left_entry.window_resolve_count + left_entry.window_sampled_draw_count;
    const uint64_t right_activity = right_entry.window_resolve_count +
                                    right_entry.window_sampled_draw_count;
    if (left_activity != right_activity) {
      return left_activity > right_activity;
    }
    return left_entry.address < right_entry.address;
  });

  size_t emitted = 0;
  for (size_t target_index : order) {
    const ResolveTargetEntry &target =
        g_dependency_census.targets[target_index];
    if ((!target.window_resolve_count && !target.window_sampled_draw_count) ||
        emitted == kResolveSummaryLimit) {
      break;
    }
    const bool sampled = target.sampled_draw_count != 0;
    const std::string query_relation =
        target.conditional_sample_draw_count ||
                target.query_state_sample_draw_count
            ? "related_draw_observed"
            : "unknown_uninstrumented";
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.census.resolve_target",
        {{"rank", number(++emitted)},
         {"address", fmt::format("{:08X}", target.address)},
         {"length", number(target.length)},
         {"maximum_length", number(target.maximum_length)},
         {"resolves", number(target.resolve_count)},
         {"resolved_bytes", number(target.resolved_bytes)},
         {"first_resolve_frame", number(target.first_resolve_frame)},
         {"last_resolve_frame", number(target.last_resolve_frame)},
         {"sampled_later", sampled ? "true" : "unobserved"},
         {"sampled_draws", number(target.sampled_draw_count)},
         {"sample_references", number(target.sample_reference_count)},
         {"first_sample_frame", number(target.first_sample_frame)},
         {"last_sample_frame", number(target.last_sample_frame)},
         {"conditional_sample_draws",
          number(target.conditional_sample_draw_count)},
         {"query_state_sample_draws",
          number(target.query_state_sample_draw_count)},
         {"memexport_sample_draws", number(target.memexport_sample_draw_count)},
         {"last_fetch_index", number(target.last_fetch_index)},
         {"last_fetch_kind", target.last_fetch_was_mip ? "mip" : "base"},
         {"copy_state", fmt::format("{:08X}:{:08X}:{:08X}:{:08X}",
                                    target.sample.rb_copy_control,
                                    target.sample.rb_copy_dest_info,
                                    target.sample.rb_copy_dest_pitch,
                                    target.sample.surface_info)},
         {"presentation_only", "unknown_uninstrumented"},
         {"guest_cpu_read", "unknown_uninstrumented"},
         {"query_dependency", query_relation},
         {"semantic_role", "unknown_unclassified"},
         {"suppression_eligible", "false"}});
  }

  ResetDependencyWindow();
}

void AdvanceDependencyWindow(uint64_t frame) {
  if (g_dependency_census.window_first_frame &&
      frame >= g_dependency_census.window_first_frame + kFrameSummaryInterval) {
    EmitDependencyCensusWindow();
  }
  BeginDependencyWindow(frame);
}

uint64_t
DrawSignature(const rex::system::GraphicsDrawObservation &observation) {
  uint64_t hash = 0xCBF29CE484222325ull;
  for (uint64_t value :
       {observation.vertex_shader_hash, observation.pixel_shader_hash,
        uint64_t(observation.primitive_type),
        uint64_t(observation.source_select), uint64_t(observation.indexed),
        uint64_t(observation.major_mode_explicit),
        uint64_t(observation.vertex_memexport),
        uint64_t(observation.surface_info), uint64_t(observation.color_info[0]),
        uint64_t(observation.color_info[1]),
        uint64_t(observation.color_info[2]),
        uint64_t(observation.color_info[3]), uint64_t(observation.depth_info),
        uint64_t(observation.window_scissor_tl),
        uint64_t(observation.window_scissor_br),
        uint64_t(observation.rb_modecontrol)}) {
    hash = HashCombine(hash, value);
  }
  return hash ? hash : 1;
}

uint64_t
CandidateSignature(const rex::system::GraphicsDrawObservation &observation,
                   bool samples_resolved_target,
                   const rex::system::GraphicsPreparedDrawObservation
                       &prepared) {
  uint64_t hash = DrawSignature(observation);
  for (uint64_t value : {prepared.vertex_specialization_mask,
                         prepared.pixel_specialization_mask,
                         PreparedPipelineHash(prepared),
                         uint64_t(observation.index_format),
                         uint64_t(observation.index_endianness),
                         uint64_t(observation.vertex_index_offset),
                         uint64_t(observation.vertex_index_min),
                         uint64_t(observation.vertex_index_max),
                         uint64_t(observation.vertex_binding_count),
                         uint64_t(observation.vertex_binding_overflow),
                         uint64_t(observation.vertex_attribute_count),
                         uint64_t(observation.vertex_attribute_overflow),
                         uint64_t(observation.vertex_float_constant_count),
                         uint64_t(observation.vertex_float_constant_overflow),
                         uint64_t(observation.pixel_float_constant_count),
                         uint64_t(observation.pixel_float_constant_overflow),
                         uint64_t(observation.texture_state_count),
                         uint64_t(observation.texture_state_overflow),
                         uint64_t(observation.viz_query_condition),
                         uint64_t(observation.pa_sc_viz_query),
                         uint64_t(samples_resolved_target),
                         uint64_t(observation.texture_fetch_mask),
                         uint64_t(observation.rb_color_mask),
                         uint64_t(observation.rb_blendcontrol[0]),
                         uint64_t(observation.rb_blendcontrol[1]),
                         uint64_t(observation.rb_blendcontrol[2]),
                         uint64_t(observation.rb_blendcontrol[3]),
                         uint64_t(observation.rb_depthcontrol),
                         uint64_t(observation.pa_su_sc_mode_cntl),
                         uint64_t(observation.pa_su_vtx_cntl)}) {
    hash = HashCombine(hash, value);
  }
  const uint32_t bounded_binding_count =
      std::min(observation.vertex_binding_count,
               rex::system::kGraphicsVertexBindingObservationLimit);
  for (uint32_t i = 0; i < bounded_binding_count; ++i) {
    const auto &binding = observation.vertex_bindings[i];
    hash = HashCombine(hash, binding.fetch_constant);
    hash = HashCombine(hash, binding.size);
    hash = HashCombine(hash, binding.stride_words);
    hash = HashCombine(hash, binding.endianness);
  }
  const uint32_t bounded_attribute_count =
      std::min(observation.vertex_attribute_count,
               rex::system::kGraphicsVertexAttributeObservationLimit);
  for (uint32_t i = 0; i < bounded_attribute_count; ++i) {
    const auto &attribute = observation.vertex_attributes[i];
    for (uint64_t value :
         {uint64_t(attribute.binding_index), uint64_t(attribute.fetch_constant),
          uint64_t(uint32_t(attribute.offset_words)),
          uint64_t(attribute.stride_words), uint64_t(attribute.data_format),
          uint64_t(attribute.fetch_word_mask),
          uint64_t(uint32_t(attribute.exp_adjust)),
          uint64_t(attribute.signed_rf_mode),
          uint64_t(attribute.result_storage_target),
          uint64_t(attribute.result_storage_index),
          uint64_t(attribute.result_write_mask),
          uint64_t(attribute.result_components), uint64_t(attribute.flags)}) {
      hash = HashCombine(hash, value);
    }
  }
  for (uint32_t value : observation.bool_constant_bitmap) {
    hash = HashCombine(hash, value);
  }
  hash = HashCombine(hash, observation.loop_constant_bitmap);
  const uint32_t bounded_texture_count = std::min(
      observation.texture_state_count,
      rex::system::kGraphicsTextureFetchObservationLimit);
  for (uint32_t i = 0; i < bounded_texture_count; ++i) {
    const auto &state = observation.texture_states[i];
    for (uint32_t value :
         {state.stage, state.fetch_constant, state.opcode, state.dimension,
          state.filters, state.flags, state.lod_bias, state.offsets,
          state.result_storage_target, state.result_storage_index,
          state.result_write_mask, state.result_components}) {
      hash = HashCombine(hash, value);
    }
  }
  return hash ? hash : 1;
}

bool IsOpaqueColorState(
    const rex::system::GraphicsDrawObservation &observation) {
  bool writes_color = false;
  for (uint32_t i = 0; i < 4; ++i) {
    if (!(observation.rb_color_mask & (uint32_t(0xF) << (i * 4)))) {
      continue;
    }
    writes_color = true;
    if (observation.rb_blendcontrol[i] != 0x00010001) {
      return false;
    }
  }
  return writes_color;
}

bool IsMechanicallyEligibleCandidate(const DrawSignatureEntry &entry) {
  const auto &observation = entry.sample;
  const bool query_draw = observation.viz_query_condition ||
                          (observation.pa_sc_viz_query & 1);
  const uint32_t texture_count =
      std::popcount(observation.texture_fetch_mask);
  return IsOpaqueColorState(observation) && !query_draw &&
         !observation.vertex_memexport && !entry.samples_resolved_target &&
         !observation.vertex_binding_overflow &&
         !observation.vertex_attribute_overflow &&
         !observation.vertex_float_constant_overflow &&
         !observation.pixel_float_constant_overflow &&
         !observation.texture_state_overflow &&
         observation.vertex_binding_count == 1 && texture_count >= 1 &&
         texture_count <= 4;
}

bool IsIsolatedDrawEligible(
    const rex::system::GraphicsDrawObservation &observation,
    bool samples_resolved_target,
    const rex::system::GraphicsPreparedDrawObservation &prepared) {
  const uint32_t texture_count =
      std::popcount(observation.texture_fetch_mask);
  return !samples_resolved_target && observation.indexed &&
         observation.source_select ==
             uint32_t(rex::graphics::xenos::SourceSelect::kDMA) &&
         observation.index_format <= 1 && observation.index_endianness <= 3 &&
         observation.index_count && observation.vertex_binding_count == 1 &&
         !observation.vertex_binding_overflow &&
         !observation.vertex_attribute_overflow &&
         !observation.vertex_float_constant_overflow &&
         !observation.pixel_float_constant_overflow &&
         !observation.texture_state_overflow && !observation.vertex_memexport &&
         !observation.viz_query_condition && !(observation.pa_sc_viz_query & 1) &&
         texture_count >= 1 && texture_count <= 4 &&
         (observation.texture_fetch_layout_valid_mask &
          observation.texture_fetch_mask) == observation.texture_fetch_mask &&
         (prepared.flags & 3) == 3 && prepared.bound_render_target_bits == 3 &&
         prepared.index_buffer_type == 1;
}

void RecordCandidate(
    const rex::system::GraphicsDrawObservation &observation,
    bool samples_resolved_target,
    const rex::system::GraphicsPreparedDrawObservation &prepared);

void ObservePreparedDraw(
    const rex::system::GraphicsPreparedDrawObservation &observation) {
  g_isolated_draw.prepared_candidate_valid = false;
  if (!g_pending_candidate.valid) {
    ++g_candidate_prepared_without_observation_count;
  } else {
    auto sample = g_pending_candidate.sample;
    sample.vertex_shader_hash = observation.vertex_shader_hash;
    sample.pixel_shader_hash = observation.pixel_shader_hash;
    g_isolated_draw.prepared_signature = CandidateSignature(
        sample, g_pending_candidate.samples_resolved_target, observation);
    g_isolated_draw.frame = sample.frame_sequence;
    g_isolated_draw.draw = sample.draw_sequence;
    g_isolated_draw.prepared_candidate_eligible = IsIsolatedDrawEligible(
        sample, g_pending_candidate.samples_resolved_target, observation);
    g_isolated_draw.prepared_candidate_valid = true;
    RecordCandidate(sample, g_pending_candidate.samples_resolved_target,
                    observation);
    g_pending_candidate.valid = false;
  }
  uint64_t identity = 0xCBF29CE484222325ull;
  for (uint64_t value :
       {observation.vertex_shader_hash, observation.pixel_shader_hash,
        observation.vertex_specialization_mask,
        observation.pixel_specialization_mask}) {
    identity = HashCombine(identity, value);
  }
  identity = identity ? identity : 1;
  size_t index = size_t(identity % kPreparedShaderPairCapacity);
  for (size_t probe = 0; probe < kPreparedShaderPairCapacity; ++probe) {
    PreparedShaderPairEntry &entry = g_prepared_shader_pairs[index];
    if (!entry.identity) {
      entry.identity = identity;
      entry.sample = observation;
      ++g_prepared_shader_pair_count;
      pinyon_shift::diagnostics::RecordEvent(
          "native_renderer.census.prepared_shader_pair",
          {{"vertex_shader",
            fmt::format("{:016X}", observation.vertex_shader_hash)},
           {"pixel_shader",
            fmt::format("{:016X}", observation.pixel_shader_hash)},
           {"vertex_specialization_mask",
            fmt::format("{:016X}", observation.vertex_specialization_mask)},
           {"pixel_specialization_mask",
            fmt::format("{:016X}", observation.pixel_specialization_mask)},
           {"mode", "pass_through"},
           {"suppression_eligible", "false"}});
      return;
    }
    if (entry.identity == identity &&
        entry.sample.vertex_shader_hash == observation.vertex_shader_hash &&
        entry.sample.pixel_shader_hash == observation.pixel_shader_hash &&
        entry.sample.vertex_specialization_mask ==
            observation.vertex_specialization_mask &&
        entry.sample.pixel_specialization_mask ==
            observation.pixel_specialization_mask) {
      return;
    }
    index = (index + 1) % kPreparedShaderPairCapacity;
  }
  ++g_prepared_shader_pair_overflow;
}

void EmitCandidateCensusWindow(uint64_t last_frame_value) {
  std::array<size_t, kSignatureCapacity> order{};
  uint64_t eligible_signatures = 0;
  uint64_t eligible_draws = 0;
  for (size_t i = 0; i < order.size(); ++i) {
    order[i] = i;
    const DrawSignatureEntry &entry = g_candidate_census.entries[i];
    if (entry.draw_count && IsMechanicallyEligibleCandidate(entry)) {
      ++eligible_signatures;
      eligible_draws += entry.draw_count;
    }
  }
  std::sort(order.begin(), order.end(), [](size_t left, size_t right) {
    const DrawSignatureEntry &left_entry = g_candidate_census.entries[left];
    const DrawSignatureEntry &right_entry = g_candidate_census.entries[right];
    const bool left_eligible = IsMechanicallyEligibleCandidate(left_entry);
    const bool right_eligible = IsMechanicallyEligibleCandidate(right_entry);
    if (left_eligible != right_eligible) {
      return left_eligible;
    }
    if (left_entry.draw_count != right_entry.draw_count) {
      return left_entry.draw_count > right_entry.draw_count;
    }
    return left_entry.signature < right_entry.signature;
  });
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.census.candidate_window",
      {{"first_frame", std::to_string(g_candidate_census.window_first_frame)},
       {"last_frame", std::to_string(last_frame_value)},
       {"draws", std::to_string(g_candidate_census.window_draw_count)},
       {"unique_signatures",
        std::to_string(g_candidate_census.unique_signature_count)},
       {"overflow_draws",
        std::to_string(g_candidate_census.overflow_draw_count)},
       {"eligible_signatures", std::to_string(eligible_signatures)},
       {"eligible_draws", std::to_string(eligible_draws)},
       {"signature_capacity", std::to_string(kSignatureCapacity)},
       {"summary_limit", std::to_string(kCandidateSummaryLimit)},
       {"mode", "metadata_shortlist_only"}});

  size_t emitted = 0;
  for (size_t index : order) {
    const DrawSignatureEntry &entry = g_candidate_census.entries[index];
    if (!entry.draw_count || emitted == kCandidateSummaryLimit) {
      break;
    }
    const auto &sample = entry.sample;
    std::string vertex_fetches;
    const uint32_t bounded_binding_count =
        std::min(sample.vertex_binding_count,
                 rex::system::kGraphicsVertexBindingObservationLimit);
    for (uint32_t i = 0; i < bounded_binding_count; ++i) {
      const auto &binding = sample.vertex_bindings[i];
      if (!vertex_fetches.empty()) {
        vertex_fetches += ";";
      }
      vertex_fetches += fmt::format(
          "{}:{:08X}:{}:{}:{}", binding.fetch_constant, binding.address,
          binding.size, binding.stride_words, binding.endianness);
    }
    std::string vertex_attributes;
    const uint32_t bounded_attribute_count =
        std::min(sample.vertex_attribute_count,
                 rex::system::kGraphicsVertexAttributeObservationLimit);
    for (uint32_t i = 0; i < bounded_attribute_count; ++i) {
      const auto &attribute = sample.vertex_attributes[i];
      if (!vertex_attributes.empty()) {
        vertex_attributes += ";";
      }
      vertex_attributes += fmt::format(
          "{}:{}:{}:{}:{}:{:X}:{}:{}:{}:{}:{:X}:{:X}:{:X}",
          attribute.binding_index, attribute.fetch_constant,
          attribute.offset_words, attribute.stride_words, attribute.data_format,
          attribute.fetch_word_mask, attribute.exp_adjust,
          attribute.signed_rf_mode, attribute.result_storage_target,
          attribute.result_storage_index, attribute.result_write_mask,
          attribute.result_components, attribute.flags);
    }
    const bool query_draw =
        sample.viz_query_condition || (sample.pa_sc_viz_query & 1);
    const std::string pipeline_state =
        fmt::format("color_mask={:08X};blend={:08X}:{:08X}:{:08X}:{:08X};"
                    "depth={:08X};raster={:08X};vertex={:08X}",
                    sample.rb_color_mask, sample.rb_blendcontrol[0],
                    sample.rb_blendcontrol[1], sample.rb_blendcontrol[2],
                    sample.rb_blendcontrol[3], sample.rb_depthcontrol,
                    sample.pa_su_sc_mode_cntl, sample.pa_su_vtx_cntl);
    const auto &prepared = entry.prepared_sample;
    const std::string bound_render_target_formats = fmt::format(
        "{:08X}:{:08X}:{:08X}:{:08X}:{:08X}",
        prepared.bound_render_target_formats[0],
        prepared.bound_render_target_formats[1],
        prepared.bound_render_target_formats[2],
        prepared.bound_render_target_formats[3],
        prepared.bound_render_target_formats[4]);
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.census.draw_candidate",
        {{"rank", std::to_string(++emitted)},
         {"signature", fmt::format("{:016X}", entry.signature)},
         {"draws", std::to_string(entry.draw_count)},
         {"first_frame", std::to_string(entry.first_frame)},
         {"last_frame", std::to_string(entry.last_frame)},
         {"vertex_shader", fmt::format("{:016X}", sample.vertex_shader_hash)},
         {"pixel_shader", fmt::format("{:016X}", sample.pixel_shader_hash)},
         {"vertex_specialization_mask",
          fmt::format("{:016X}", entry.vertex_specialization_mask)},
         {"pixel_specialization_mask",
          fmt::format("{:016X}", entry.pixel_specialization_mask)},
         {"primitive", std::to_string(sample.primitive_type)},
         {"source_select", std::to_string(sample.source_select)},
         {"index_count_min", std::to_string(entry.min_index_count)},
         {"index_count_max", std::to_string(entry.max_index_count)},
         {"index_state",
          fmt::format("format={};endianness={}", sample.index_format,
                      sample.index_endianness)},
         {"index_buffer_address",
          fmt::format("{:08X}", sample.index_buffer_address)},
         {"index_buffer_length_min",
          std::to_string(entry.min_index_buffer_length)},
         {"vertex_index_range",
          fmt::format("offset={};min={};max={}", sample.vertex_index_offset,
                      sample.vertex_index_min, sample.vertex_index_max)},
         {"vertex_binding_count", std::to_string(sample.vertex_binding_count)},
         {"vertex_fetches", vertex_fetches},
         {"vertex_attribute_count",
          std::to_string(sample.vertex_attribute_count)},
         {"vertex_attributes", vertex_attributes},
         {"texture_fetch_count",
          std::to_string(std::popcount(sample.texture_fetch_mask))},
         {"draw_state_hash", fmt::format("{:016X}", DrawStateHash(sample))},
         {"vertex_float_constant_count",
          std::to_string(sample.vertex_float_constant_count)},
         {"vertex_float_constants",
          SerializeFloatConstants(sample.vertex_float_constants,
                                  sample.vertex_float_constant_count)},
         {"pixel_float_constant_count",
          std::to_string(sample.pixel_float_constant_count)},
         {"pixel_float_constants",
          SerializeFloatConstants(sample.pixel_float_constants,
                                  sample.pixel_float_constant_count)},
         {"bool_constants",
          SerializeWordConstants(sample.bool_constant_bitmap,
                                 sample.bool_constant_values, 8)},
         {"loop_constants",
          SerializeLoopConstants(sample.loop_constant_bitmap,
                                 sample.loop_constant_values)},
         {"texture_state_count", std::to_string(sample.texture_state_count)},
         {"texture_states", SerializeTextureStates(sample)},
         {"pipeline_state", pipeline_state},
         {"prepared_pipeline_hash",
          fmt::format("{:016X}", PreparedPipelineHash(prepared))},
         {"host_primitive", std::to_string(prepared.host_primitive_type)},
         {"host_vertex_shader_type",
          std::to_string(prepared.host_vertex_shader_type)},
         {"tessellation_mode", std::to_string(prepared.tessellation_mode)},
         {"host_index_buffer_type",
          std::to_string(prepared.index_buffer_type)},
         {"host_index_format", std::to_string(prepared.host_index_format)},
         {"host_primitive_reset",
          prepared.host_primitive_reset_enabled ? "true" : "false"},
         {"normalized_depth_control",
          fmt::format("{:08X}", prepared.normalized_depth_control)},
         {"normalized_color_mask",
          fmt::format("{:08X}", prepared.normalized_color_mask)},
         {"bound_render_target_bits",
          fmt::format("{:08X}", prepared.bound_render_target_bits)},
         {"bound_render_target_formats", bound_render_target_formats},
         {"prepared_pipeline_flags", fmt::format("{:08X}", prepared.flags)},
         {"indexed", sample.indexed ? "true" : "false"},
         {"query", query_draw ? "true" : "false"},
         {"memexport", sample.vertex_memexport ? "true" : "false"},
         {"resolved_input", entry.samples_resolved_target ? "true" : "false"},
         {"opaque", IsOpaqueColorState(sample) ? "true" : "false"},
         {"vertex_overflow", sample.vertex_binding_overflow ? "true" : "false"},
         {"vertex_attribute_overflow",
          sample.vertex_attribute_overflow ? "true" : "false"},
         {"constant_overflow",
          (sample.vertex_float_constant_overflow ||
           sample.pixel_float_constant_overflow)
              ? "true"
              : "false"},
         {"texture_state_overflow",
          sample.texture_state_overflow ? "true" : "false"},
         {"mechanically_eligible",
          IsMechanicallyEligibleCandidate(entry) ? "true" : "false"},
         {"qualification", "metadata_shortlist_only"},
         {"suppression_eligible", "false"}});
  }
}

void CompleteIsolatedDraw(
    const rex::system::GraphicsIsolatedDrawResult &result) {
  const char *status = "unsupported_state";
  if (result.status ==
      rex::system::GraphicsIsolatedDrawStatus::kRecorded) {
    status = "recorded";
  } else if (result.status ==
             rex::system::GraphicsIsolatedDrawStatus::kTargetCreationFailed) {
    status = "target_creation_failed";
  }
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.isolated_draw.result",
      {{"signature",
        fmt::format("{:016X}", g_isolated_draw.prepared_signature)},
       {"status", status},
       {"frame", std::to_string(g_isolated_draw.frame)},
       {"draw", std::to_string(g_isolated_draw.draw)},
       {"target_width", std::to_string(result.target_width)},
       {"target_height", std::to_string(result.target_height)},
       {"native_draw", result.status ==
                                   rex::system::GraphicsIsolatedDrawStatus::kRecorded
                               ? "isolated_only"
                               : "false"},
       {"xenos_draw", "preserved"},
       {"output_authority", "xenos"},
       {"suppression_eligible", "false"}});
}

void RequestIsolatedDraw(
    const rex::system::GraphicsPreparedDrawObservation &,
    rex::system::GraphicsIsolatedDrawRequest &request) {
  if (!g_isolated_draw.requested || !g_isolated_draw.valid ||
      g_isolated_draw.completed ||
      !g_isolated_draw.prepared_candidate_valid ||
      g_isolated_draw.prepared_signature != g_isolated_draw.target_signature) {
    return;
  }
  g_isolated_draw.completed = true;
  if (!g_isolated_draw.prepared_candidate_eligible) {
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.isolated_draw.result",
        {{"signature",
          fmt::format("{:016X}", g_isolated_draw.prepared_signature)},
         {"status", "rejected_by_title_gate"},
         {"frame", std::to_string(g_isolated_draw.frame)},
         {"draw", std::to_string(g_isolated_draw.draw)},
         {"native_draw", "false"},
         {"xenos_draw", "preserved"},
         {"output_authority", "xenos"},
         {"suppression_eligible", "false"}});
    return;
  }
  request.requested = true;
  request.completion = &CompleteIsolatedDraw;
}

void EmitDrawCensusWindow(uint64_t last_frame_value) {
  std::array<size_t, kSignatureCapacity> order{};
  for (size_t i = 0; i < order.size(); ++i) {
    order[i] = i;
  }
  std::sort(order.begin(), order.end(), [](size_t left, size_t right) {
    const DrawSignatureEntry &left_entry = g_draw_census.entries[left];
    const DrawSignatureEntry &right_entry = g_draw_census.entries[right];
    if (left_entry.draw_count != right_entry.draw_count) {
      return left_entry.draw_count > right_entry.draw_count;
    }
    return left_entry.signature < right_entry.signature;
  });

  const std::string first_frame =
      std::to_string(g_draw_census.window_first_frame);
  const std::string last_frame = std::to_string(last_frame_value);
  const std::string draws = std::to_string(g_draw_census.window_draw_count);
  const std::string unique =
      std::to_string(g_draw_census.unique_signature_count);
  const std::string overflow =
      std::to_string(g_draw_census.overflow_draw_count);
  const std::string capacity = std::to_string(kSignatureCapacity);
  pinyon_shift::diagnostics::RecordEvent("native_renderer.census.draw_window",
                                         {{"first_frame", first_frame},
                                          {"last_frame", last_frame},
                                          {"draws", draws},
                                          {"unique_signatures", unique},
                                          {"overflow_draws", overflow},
                                          {"signature_capacity", capacity},
                                          {"summary_limit", "16"}});

  size_t emitted = 0;
  for (size_t index : order) {
    const DrawSignatureEntry &entry = g_draw_census.entries[index];
    if (!entry.draw_count || emitted == kSummaryLimit) {
      break;
    }
    const auto &sample = entry.sample;
    const std::string rank = std::to_string(++emitted);
    const std::string count = std::to_string(entry.draw_count);
    const std::string first = std::to_string(entry.first_frame);
    const std::string last = std::to_string(entry.last_frame);
    const std::string index_count = std::to_string(sample.index_count);
    const std::string signature = fmt::format("{:016X}", entry.signature);
    const std::string vertex_shader =
        fmt::format("{:016X}", sample.vertex_shader_hash);
    const std::string pixel_shader =
        fmt::format("{:016X}", sample.pixel_shader_hash);
    const std::string primitive = std::to_string(sample.primitive_type);
    const std::string target_state = fmt::format(
        "{:08X}:{:08X}:{:08X}:{:08X}:{:08X}:{:08X}", sample.surface_info,
        sample.color_info[0], sample.color_info[1], sample.color_info[2],
        sample.color_info[3], sample.depth_info);
    const std::string scissor = fmt::format(
        "{:08X}:{:08X}", sample.window_scissor_tl, sample.window_scissor_br);
    const std::string index_buffer = fmt::format(
        "{:08X}:{}", sample.index_buffer_address, sample.index_buffer_length);
    const std::string index_state =
        fmt::format("format={};endianness={}", sample.index_format,
                    sample.index_endianness);
    std::string vertex_fetches;
    const uint32_t bounded_binding_count =
        std::min(sample.vertex_binding_count,
                 rex::system::kGraphicsVertexBindingObservationLimit);
    for (uint32_t i = 0; i < bounded_binding_count; ++i) {
      const auto &binding = sample.vertex_bindings[i];
      if (!vertex_fetches.empty()) {
        vertex_fetches += ";";
      }
      vertex_fetches += fmt::format(
          "{}:{:08X}:{}:{}:{}", binding.fetch_constant, binding.address,
          binding.size, binding.stride_words, binding.endianness);
    }
    const bool query_draw =
        sample.viz_query_condition || (sample.pa_sc_viz_query & 1);
    const std::string pipeline_state =
        fmt::format("color_mask={:08X};blend={:08X}:{:08X}:{:08X}:{:08X};"
                    "depth={:08X};raster={:08X};vertex={:08X}",
                    sample.rb_color_mask, sample.rb_blendcontrol[0],
                    sample.rb_blendcontrol[1], sample.rb_blendcontrol[2],
                    sample.rb_blendcontrol[3], sample.rb_depthcontrol,
                    sample.pa_su_sc_mode_cntl, sample.pa_su_vtx_cntl);
    const std::string flags = fmt::format(
        "indexed={};explicit_major={};memexport={};query={};"
        "resolved_input={};opaque={};vertex_overflow={}",
        sample.indexed, sample.major_mode_explicit, sample.vertex_memexport,
        query_draw, entry.samples_resolved_target, IsOpaqueColorState(sample),
        bool(sample.vertex_binding_overflow));
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.census.draw_signature",
        {{"rank", rank},
         {"signature", signature},
         {"draws", count},
         {"first_frame", first},
         {"last_frame", last},
         {"vertex_shader", vertex_shader},
         {"pixel_shader", pixel_shader},
         {"primitive", primitive},
         {"index_count", index_count},
         {"target_state", target_state},
         {"scissor", scissor},
         {"index_buffer", index_buffer},
         {"index_state", index_state},
         {"vertex_binding_count", std::to_string(sample.vertex_binding_count)},
         {"vertex_fetches", vertex_fetches},
         {"texture_fetch_count",
          std::to_string(std::popcount(sample.texture_fetch_mask))},
         {"pipeline_state", pipeline_state},
         {"indexed", sample.indexed ? "true" : "false"},
         {"query", query_draw ? "true" : "false"},
         {"memexport", sample.vertex_memexport ? "true" : "false"},
         {"resolved_input", entry.samples_resolved_target ? "true" : "false"},
         {"opaque", IsOpaqueColorState(sample) ? "true" : "false"},
         {"vertex_overflow", sample.vertex_binding_overflow ? "true" : "false"},
         {"flags", flags}});
  }

  EmitCandidateCensusWindow(last_frame_value);
  ResetDrawCensus();
}

void ObserveCopy(const rex::system::GraphicsCopyObservation &observation) {
  AdvanceDependencyWindow(observation.frame_sequence);
  if (!observation.succeeded) {
    ++g_dependency_census.window_failed_copy_count;
    return;
  }
  if (!observation.written_length) {
    ++g_dependency_census.window_zero_length_copy_count;
    return;
  }

  ++g_dependency_census.window_resolve_count;
  g_dependency_census.window_resolve_bytes += observation.written_length;
  const size_t target_index = ResolveTargetIndex(observation.written_address);
  if (target_index == kResolveTargetCapacity) {
    ++g_dependency_census.target_overflow_count;
    return;
  }

  ResolveTargetEntry &target = g_dependency_census.targets[target_index];
  if (!target.resolve_count) {
    target.address = observation.written_address;
    target.first_resolve_frame = observation.frame_sequence;
    ++g_dependency_census.target_count;
  }
  target.length = observation.written_length;
  target.maximum_length =
      std::max(target.maximum_length, observation.written_length);
  ++target.resolve_count;
  target.resolved_bytes += observation.written_length;
  target.last_resolve_frame = observation.frame_sequence;
  ++target.window_resolve_count;
  target.sample = observation;
  MapResolveRange(target_index, observation.written_address,
                  observation.written_length);
}

void EmitResolvedTextureDependency(
    const rex::system::GraphicsDrawObservation &observation,
    const ResolveTargetEntry &target, uint32_t fetch_index, bool is_mip) {
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.census.resolve_dependency",
      {{"address", fmt::format("{:08X}", target.address)},
       {"length", std::to_string(target.length)},
       {"resolve_frame", std::to_string(target.last_resolve_frame)},
       {"sample_frame", std::to_string(observation.frame_sequence)},
       {"sample_draw", std::to_string(observation.draw_sequence)},
       {"fetch_index", std::to_string(fetch_index)},
       {"fetch_kind", is_mip ? "mip" : "base"},
       {"conditional_draw", observation.viz_query_condition ? "true" : "false"},
       {"query_state", (observation.pa_sc_viz_query & 1) ? "true" : "false"},
       {"memexport_draw", observation.vertex_memexport ? "true" : "false"},
       {"presentation_only", "unknown_uninstrumented"},
       {"guest_cpu_read", "unknown_uninstrumented"},
       {"query_dependency", "unknown_uninstrumented"},
       {"semantic_role", "unknown_unclassified"},
       {"suppression_eligible", "false"}});
}

void ObserveResolvedFetch(
    const rex::system::GraphicsDrawObservation &observation,
    uint32_t fetch_index, uint32_t address, bool is_mip,
    std::array<size_t, 64> &sampled_targets, size_t &sampled_target_count) {
  if (!address) {
    return;
  }
  const size_t target_index = FindResolveTarget(address);
  if (target_index == kResolveTargetCapacity) {
    return;
  }

  ResolveTargetEntry &target = g_dependency_census.targets[target_index];
  ++target.sample_reference_count;
  ++g_dependency_census.window_sample_reference_count;
  target.last_fetch_index = fetch_index;
  target.last_fetch_was_mip = is_mip;
  for (size_t i = 0; i < sampled_target_count; ++i) {
    if (sampled_targets[i] == target_index) {
      return;
    }
  }
  sampled_targets[sampled_target_count++] = target_index;

  const bool first_sample = !target.sampled_draw_count;
  if (first_sample) {
    target.first_sample_frame = observation.frame_sequence;
  }
  if (!target.window_sampled_draw_count) {
    ++g_dependency_census.window_sampled_target_count;
  }
  ++target.sampled_draw_count;
  ++target.window_sampled_draw_count;
  target.last_sample_frame = observation.frame_sequence;
  if (observation.viz_query_condition) {
    ++target.conditional_sample_draw_count;
  }
  if (observation.pa_sc_viz_query & 1) {
    ++target.query_state_sample_draw_count;
  }
  if (observation.vertex_memexport) {
    ++target.memexport_sample_draw_count;
  }
  if (first_sample) {
    EmitResolvedTextureDependency(observation, target, fetch_index, is_mip);
  }
}

void RecordCandidate(
    const rex::system::GraphicsDrawObservation &observation,
    bool samples_resolved_target,
    const rex::system::GraphicsPreparedDrawObservation &prepared) {
  ++g_candidate_census.window_draw_count;
  const uint64_t signature =
      CandidateSignature(observation, samples_resolved_target, prepared);
  TryScanCandidateIndices(observation, signature);
  TryFingerprintCandidateTextures(observation, signature);
  TryCaptureReplaySnapshot(observation, samples_resolved_target, prepared,
                           signature);
  size_t index = size_t(signature % kSignatureCapacity);
  for (size_t probe = 0; probe < kSignatureCapacity; ++probe) {
    DrawSignatureEntry &entry = g_candidate_census.entries[index];
    if (!entry.draw_count) {
      entry.signature = signature;
      entry.draw_count = 1;
      entry.first_frame = observation.frame_sequence;
      entry.last_frame = observation.frame_sequence;
      entry.min_index_count = observation.index_count;
      entry.max_index_count = observation.index_count;
      entry.min_index_buffer_length = observation.index_buffer_length;
      entry.vertex_specialization_mask =
          prepared.vertex_specialization_mask;
      entry.pixel_specialization_mask = prepared.pixel_specialization_mask;
      entry.prepared_sample = prepared;
      entry.samples_resolved_target = samples_resolved_target;
      entry.sample = observation;
      ++g_candidate_census.unique_signature_count;
      return;
    }
    if (entry.signature == signature) {
      ++entry.draw_count;
      entry.last_frame = observation.frame_sequence;
      entry.min_index_count =
          std::min(entry.min_index_count, observation.index_count);
      entry.max_index_count =
          std::max(entry.max_index_count, observation.index_count);
      if (observation.indexed) {
        entry.min_index_buffer_length = std::min(
            entry.min_index_buffer_length, observation.index_buffer_length);
      }
      return;
    }
    index = (index + 1) % kSignatureCapacity;
  }
  ++g_candidate_census.overflow_draw_count;
}

void ObserveDraw(const rex::system::GraphicsDrawObservation &observation) {
  AdvanceDependencyWindow(observation.frame_sequence);
  const bool query_draw =
      observation.viz_query_condition || (observation.pa_sc_viz_query & 1);
  if (query_draw) {
    ++g_dependency_census.window_query_draw_count;
  }
  if (observation.vertex_memexport) {
    ++g_dependency_census.window_memexport_draw_count;
  }

  std::array<size_t, 64> sampled_targets{};
  size_t sampled_target_count = 0;
  for (uint32_t fetch_index = 0; fetch_index < 32; ++fetch_index) {
    if (!(observation.texture_fetch_mask & (uint32_t(1) << fetch_index))) {
      continue;
    }
    ObserveResolvedFetch(observation, fetch_index,
                         observation.texture_fetch_addresses[fetch_index],
                         false, sampled_targets, sampled_target_count);
    ObserveResolvedFetch(observation, fetch_index,
                         observation.texture_fetch_mip_addresses[fetch_index],
                         true, sampled_targets, sampled_target_count);
  }
  if (sampled_target_count) {
    ++g_dependency_census.window_sampled_draw_count;
  }

  if (!g_draw_census.window_first_frame) {
    g_draw_census.window_first_frame = observation.frame_sequence;
    g_candidate_census.window_first_frame = observation.frame_sequence;
  } else if (observation.frame_sequence >=
             g_draw_census.window_first_frame + kFrameSummaryInterval) {
    EmitDrawCensusWindow(observation.frame_sequence - 1);
    g_draw_census.window_first_frame = observation.frame_sequence;
    g_candidate_census.window_first_frame = observation.frame_sequence;
  }
  g_draw_census.window_last_frame = observation.frame_sequence;
  g_candidate_census.window_last_frame = observation.frame_sequence;

  ++g_draw_census.window_draw_count;
  const bool samples_resolved_target = sampled_target_count != 0;
  if (g_pending_candidate.valid) {
    ++g_candidate_unprepared_draw_count;
  }
  g_pending_candidate.sample = observation;
  g_pending_candidate.samples_resolved_target = samples_resolved_target;
  g_pending_candidate.valid = true;
  const uint64_t signature = DrawSignature(observation);
  size_t index = size_t(signature % kSignatureCapacity);
  for (size_t probe = 0; probe < kSignatureCapacity; ++probe) {
    DrawSignatureEntry &entry = g_draw_census.entries[index];
    if (!entry.draw_count) {
      entry.signature = signature;
      entry.draw_count = 1;
      entry.first_frame = observation.frame_sequence;
      entry.last_frame = observation.frame_sequence;
      entry.samples_resolved_target = samples_resolved_target;
      entry.sample = observation;
      ++g_draw_census.unique_signature_count;
      return;
    }
    if (entry.signature == signature) {
      ++entry.draw_count;
      entry.last_frame = observation.frame_sequence;
      return;
    }
    index = (index + 1) % kSignatureCapacity;
  }
  ++g_draw_census.overflow_draw_count;
}

} // namespace

namespace pinyon_shift::native_renderer {

void InstallGraphicsCensus(rex::system::IGraphicsSystem *graphics_system) {
  if (!graphics_system || !REXCVAR_GET(pinyon_shift_native_renderer_census)) {
    return;
  }
  ResetDrawCensus();
  ResetPreparedShaderPairs();
  ResetDependencyCensus();
  ConfigureIndexScan();
  ConfigureTextureScan();
  ConfigureReplaySnapshot();
  ConfigureIsolatedDraw();
  g_graphics_census_installed = true;
  graphics_system->SetDrawObserver(&ObserveDraw);
  graphics_system->SetCopyObserver(&ObserveCopy);
  graphics_system->SetPreparedDrawObserver(&ObservePreparedDraw);
  graphics_system->SetIsolatedDrawRequestObserver(&RequestIsolatedDraw);
  const std::string capacity = std::to_string(kSignatureCapacity);
  const std::string scene = CensusSceneMarker();
  diagnostics::RecordEvent("native_renderer.census.installed",
                           {{"signature_capacity", capacity},
                            {"summary_limit", "16"},
                            {"resolve_target_capacity", "4096"},
                            {"resolve_page_capacity", "32768"},
                            {"resolve_summary_limit", "32"},
                            {"prepared_shader_pair_capacity", "1024"},
                            {"scene", scene},
                            {"mode", "pass_through"}});
  diagnostics::RecordEvent("native_renderer.census.scene_marker",
                           {{"scene", scene}, {"source", "operator"}});
  diagnostics::RecordEvent(
      "native_renderer.census.index_scan_config",
      {{"status", !g_index_scan.requested
                      ? "disabled"
                      : (g_index_scan.valid ? "armed" : "invalid_signature")},
       {"signature", g_index_scan.valid && g_index_scan.requested
                         ? fmt::format("{:016X}", g_index_scan.target_signature)
                         : ""},
       {"maximum_index_count", std::to_string(kMaximumIndexScanCount)},
       {"maximum_bytes", std::to_string(kMaximumIndexScanBytes)},
       {"mode", "bounded_diagnostic_read"}});
  diagnostics::RecordEvent(
      "native_renderer.census.texture_scan_config",
      {{"status", !g_texture_scan.requested
                      ? "disabled"
                      : (g_texture_scan.valid ? "armed" : "invalid_signature")},
       {"signature", g_texture_scan.valid && g_texture_scan.requested
                         ? fmt::format("{:016X}",
                                       g_texture_scan.target_signature)
                         : ""},
       {"maximum_resources",
        std::to_string(kMaximumTextureScanResources)},
       {"maximum_resource_bytes",
        std::to_string(kMaximumTextureScanResourceBytes)},
       {"maximum_total_bytes",
        std::to_string(kMaximumTextureScanTotalBytes)},
       {"mode", "bounded_diagnostic_read"}});
  diagnostics::RecordEvent(
      "native_renderer.snapshot.config",
      {{"status", !g_replay_snapshot.requested
                      ? "disabled"
                      : (g_replay_snapshot.valid ? "armed"
                                                 : "invalid_configuration")},
       {"signature",
        g_replay_snapshot.valid && g_replay_snapshot.requested
            ? fmt::format("{:016X}", g_replay_snapshot.target_signature)
            : ""},
       {"output",
        g_replay_snapshot.valid && g_replay_snapshot.requested ? "local_only"
                                                               : ""},
       {"native_upload", "false"},
       {"native_draw", "false"},
       {"suppression_eligible", "false"}});
  diagnostics::RecordEvent(
      "native_renderer.isolated_draw.config",
      {{"status", !g_isolated_draw.requested
                      ? "disabled"
                      : (g_isolated_draw.valid ? "armed"
                                               : "invalid_configuration")},
       {"signature",
        g_isolated_draw.valid && g_isolated_draw.requested
            ? fmt::format("{:016X}", g_isolated_draw.target_signature)
            : ""},
       {"native_draw", "isolated_only"},
       {"xenos_draw", "preserved"},
       {"output_authority", "xenos"},
       {"suppression_eligible", "false"}});
}

void UninstallGraphicsCensus(rex::system::IGraphicsSystem *graphics_system) {
  if (graphics_system) {
    graphics_system->SetDrawObserver(nullptr);
    graphics_system->SetCopyObserver(nullptr);
    graphics_system->SetPreparedDrawObserver(nullptr);
    graphics_system->SetIsolatedDrawRequestObserver(nullptr);
  }
  if (!g_graphics_census_installed) {
    return;
  }
  g_graphics_census_installed = false;
  if (g_draw_census.window_first_frame && g_draw_census.window_draw_count) {
    EmitDrawCensusWindow(g_draw_census.window_last_frame);
  }
  if (g_pending_candidate.valid) {
    ++g_candidate_unprepared_draw_count;
    g_pending_candidate.valid = false;
  }
  EmitDependencyCensusWindow();
  if (g_index_scan.requested && g_index_scan.valid && !g_index_scan.completed) {
    diagnostics::RecordEvent(
        "native_renderer.census.index_scan",
        {{"signature", fmt::format("{:016X}", g_index_scan.target_signature)},
         {"status", "not_observed"},
         {"guest_payload_read", "false"},
         {"native_upload", "false"},
         {"native_draw", "false"},
         {"suppression_eligible", "false"}});
  }
  if (g_texture_scan.requested && g_texture_scan.valid &&
      !g_texture_scan.completed) {
    diagnostics::RecordEvent(
        "native_renderer.census.texture_scan",
        {{"signature",
          fmt::format("{:016X}", g_texture_scan.target_signature)},
         {"status", "not_observed"},
         {"guest_payload_read", "false"},
         {"native_upload", "false"},
         {"native_draw", "false"},
         {"suppression_eligible", "false"}});
  }
  if (g_replay_snapshot.requested && g_replay_snapshot.valid &&
      !g_replay_snapshot.completed) {
    diagnostics::RecordEvent(
        "native_renderer.snapshot.capture",
        {{"signature",
          fmt::format("{:016X}", g_replay_snapshot.target_signature)},
         {"status", "not_observed"},
         {"guest_payload_read", "false"},
         {"payload_persisted", "false"},
         {"native_upload", "false"},
         {"native_draw", "false"},
         {"suppression_eligible", "false"}});
  }
  if (g_isolated_draw.requested && g_isolated_draw.valid &&
      !g_isolated_draw.completed) {
    diagnostics::RecordEvent(
        "native_renderer.isolated_draw.result",
        {{"signature",
          fmt::format("{:016X}", g_isolated_draw.target_signature)},
         {"status", "not_observed"},
         {"native_draw", "false"},
         {"xenos_draw", "preserved"},
         {"output_authority", "xenos"},
         {"suppression_eligible", "false"}});
  }
  diagnostics::RecordEvent(
      "native_renderer.census.prepared_shader_pair_summary",
      {{"pairs", std::to_string(g_prepared_shader_pair_count)},
       {"overflow", std::to_string(g_prepared_shader_pair_overflow)},
       {"candidate_unprepared_draws",
        std::to_string(g_candidate_unprepared_draw_count)},
       {"candidate_prepared_without_observation",
        std::to_string(g_candidate_prepared_without_observation_count)},
       {"capacity", std::to_string(kPreparedShaderPairCapacity)},
       {"mode", "pass_through"}});
}

} // namespace pinyon_shift::native_renderer

// This translation unit is the single owner for title-side graphics hooks.
// The hook runs immediately before FH1's sole VdSwap import and intentionally
// accepts no PPC registers: it cannot mutate guest arguments or control flow.
// All renderer experiments remain passive until their own explicit cvars are
// enabled and must dispatch through this owner.
void PinyonShiftObserveGraphicsFrame() {
  if (!REXCVAR_GET(pinyon_shift_native_renderer_census)) {
    return;
  }

  const uint64_t frame_sequence =
      g_frame_sequence.fetch_add(1, std::memory_order_relaxed) + 1;
  if (frame_sequence != 1 && frame_sequence % kFrameSummaryInterval != 0) {
    return;
  }

  const std::string frame = std::to_string(frame_sequence);
  pinyon_shift::diagnostics::RecordEvent("native_renderer.census.frame",
                                         {{"frame_sequence", frame},
                                          {"guest_address", "829EFEB8"},
                                          {"mode", "pass_through"}});
}
