#include <algorithm>
#include <array>
#include <atomic>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <string>
#include <type_traits>

#include <fmt/format.h>
#include <rex/cvar.h>
#include <rex/system/interfaces/graphics.h>

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

void RecordCandidate(
    const rex::system::GraphicsDrawObservation &observation,
    bool samples_resolved_target,
    const rex::system::GraphicsPreparedDrawObservation &prepared);

void ObservePreparedDraw(
    const rex::system::GraphicsPreparedDrawObservation &observation) {
  if (!g_pending_candidate.valid) {
    ++g_candidate_prepared_without_observation_count;
  } else {
    auto sample = g_pending_candidate.sample;
    sample.vertex_shader_hash = observation.vertex_shader_hash;
    sample.pixel_shader_hash = observation.pixel_shader_hash;
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
  for (size_t i = 0; i < order.size(); ++i) {
    order[i] = i;
  }
  std::sort(order.begin(), order.end(), [](size_t left, size_t right) {
    const DrawSignatureEntry &left_entry = g_candidate_census.entries[left];
    const DrawSignatureEntry &right_entry = g_candidate_census.entries[right];
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
         {"qualification", "metadata_shortlist_only"},
         {"suppression_eligible", "false"}});
  }
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
  g_graphics_census_installed = true;
  graphics_system->SetDrawObserver(&ObserveDraw);
  graphics_system->SetCopyObserver(&ObserveCopy);
  graphics_system->SetPreparedDrawObserver(&ObservePreparedDraw);
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
}

void UninstallGraphicsCensus(rex::system::IGraphicsSystem *graphics_system) {
  if (graphics_system) {
    graphics_system->SetDrawObserver(nullptr);
    graphics_system->SetCopyObserver(nullptr);
    graphics_system->SetPreparedDrawObserver(nullptr);
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
