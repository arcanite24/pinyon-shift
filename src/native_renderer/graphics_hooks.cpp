#include "native_renderer/graphics_hooks.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <bit>
#include <chrono>
#include <exception>
#include <filesystem>
#include <fstream>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <span>
#include <string>
#include <thread>
#include <vector>

#if defined(_WIN32)
#include <Windows.h>
#endif

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/memory/utils.h>
#include <rex/ppc/context.h>

#include <rex/perf/counter.h>
#include <rex/system/interfaces/graphics.h>
#include <rex/system/xmemory.h>

#include "native_renderer/fh1_gpu_corpus.h"
#include "fh1_render_test.h"
#include "pinyon_shift_diagnostics.h"
#if defined(_WIN32)
#include "native_renderer/snr04_owned_scene_diagnostic.h"
#endif

REXCVAR_DEFINE_BOOL(pinyon_shift_fh1_clear_producer_trace, false, "Pinyon Shift",
                    "Record bounded guest clear-producer timing and shader copies")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);
REXCVAR_DEFINE_INT32(pinyon_shift_snr01_trace_source_frame, 0, "Pinyon Shift",
                     "Trace one source frame's procedural scopes and indexed PM4 headers")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);
REXCVAR_DEFINE_BOOL(pinyon_shift_snr01_trace_following_frame, false,
                    "Pinyon Shift", "Also trace the following source frame")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);
REXCVAR_DEFINE_INT32(pinyon_shift_snr02_trace_first_rebuild_after_frame, 0,
                     "Pinyon Shift", "Trace the first track mesh rebuild after this frame")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);
REXCVAR_DEFINE_INT32(pinyon_shift_snr02_trace_view_call, 0, "Pinyon Shift",
                     "Restrict track rebuild capture to this view call (0: any)")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);
REXCVAR_DEFINE_BOOL(pinyon_shift_snr01_trace_resident_packet_writers, false,
                    "Pinyon Shift", "Trace bounded resident PM4 packet writes")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);
REXCVAR_DEFINE_BOOL(pinyon_shift_snr01_watch_packet_pages, false,
                    "Pinyon Shift", "Watch observed PM4 packet pages for guest access")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);
REXCVAR_DEFINE_INT32(pinyon_shift_snr_m02_trace_source_frame, 0, "Pinyon Shift",
                     "Trace the title command-position wait for three frames")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);
REXCVAR_DEFINE_INT32(pinyon_shift_snr03_probe_frame, 0, "Pinyon Shift",
                     "Publish one read-only view-8 vegetation scene snapshot")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);
REXCVAR_DEFINE_BOOL(pinyon_shift_snr02_item_payload_probe, false,
                    "Pinyon Shift", "Read selected procedural descriptor/runtime records")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);
REXCVAR_DEFINE_BOOL(pinyon_shift_snr02_track_payload_probe, false,
                    "Pinyon Shift", "Snapshot selected view-8 track geometry")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

namespace {

using ClearClock = std::chrono::steady_clock;
struct ClearProducerSample {
  uint32_t device, flags, rectangle, colour, stencil, stack;
  double depth;
  uint64_t frame;
  uint32_t shader_copies = 0, shader_bytes = 0, refills = 0;
  uint32_t first_shader_source = 0, first_shader_destination = 0;
  uint32_t command_cursor_before = 0;
  bool nested = false;
  ClearClock::time_point begin;
};
thread_local std::vector<ClearProducerSample> clear_producers;
std::atomic<uint64_t> clear_producer_records{0};
std::atomic<uint32_t> snr02_vehicle_material_bindings{0};
std::atomic<uint32_t> snr02_car_matrices{0};
thread_local uint32_t snr02_car_matrix_record = 0;

struct TitleEmitterSample {
  uint64_t frame;
  ClearClock::time_point begin;
};
thread_local std::vector<TitleEmitterSample> title_emitters;
thread_local uint64_t title_emitter_frame = 0;
thread_local uint64_t title_emitter_calls = 0;
thread_local uint64_t title_emitter_time_ns = 0;
thread_local uint64_t title_packet_count = 0;
thread_local int64_t title_first_packet_ns = 0;
thread_local int64_t title_last_packet_ns = 0;

struct Snr01ProceduralScope {
  uint32_t receiver;
  uint64_t first_packet;
  uint64_t first_semantic_packet;
  uint64_t ordinal;
  uint32_t descriptor_index = 0;
  uint32_t descriptor_address = 0;
  uint32_t descriptor_kind = 0;
  uint32_t render_state = 0;
  uint32_t runtime_address = 0;
  uint32_t submit_context = 0;
  uint32_t submit_primitive = 0;
  uint32_t submit_arg5 = 0;
  uint32_t submit_arg6 = 0;
  bool descriptor_seen = false;
  bool runtime_seen = false;
  bool submit_seen = false;
  uint32_t snapshot_packet = 0;
  uint32_t snapshot_packet_count = 0;
};
struct Snr01DispatchScope {
  uint32_t caller_lr;
  uint32_t receiver;
  uint32_t context;
  uint32_t arg5;
  uint32_t arg6;
  uint32_t arg7;
  uint32_t arg8;
  uint32_t arg9;
  uint32_t arg10;
  uint64_t first_semantic_packet;
  uint64_t first_procedural_call;
  uint64_t ordinal;
};
struct Snr01EmitterScope {
  uint32_t caller_lr;
  uint32_t owner;
  uint32_t arg4;
  uint32_t arg5;
  uint32_t arg6;
  uint64_t first_semantic_packet;
  uint64_t ordinal;
};
struct Snr01SecondPathScope {
  uint64_t frame;
  uint64_t ordinal;
  uint64_t view_call;
  uint64_t first_semantic;
  uint32_t caller_lr;
  uint32_t context;
  uint32_t arg4;
  uint32_t arg5;
  uint32_t arg6;
  uint32_t caller_object;
  uint32_t caller_object_word0;
};
struct Snr01ScalarDrawScope {
  uint64_t frame;
  uint64_t ordinal;
  uint64_t view_call;
  uint64_t first_direct;
  uint32_t caller_lr;
  uint32_t object;
  uint32_t object_first_word;
  uint32_t command;
  uint32_t outer_object;
  uint32_t outer_first_word;
  uint32_t outer_field4;
  uint32_t outer_field12;
  uint32_t outer_field16;
  uint32_t field4_word0;
  uint32_t field12_word0;
  uint32_t field16_word0;
  uint32_t selector;
  uint32_t input_count;
};
struct Snr01DynamicQuadScope {
  uint64_t frame;
  uint64_t first_direct;
  uint64_t view_call;
  uint32_t callsite;
  uint32_t object;
  uint32_t records;
  uint32_t output;
};
struct Snr01DynamicQuadParentScope {
  uint64_t frame;
  uint64_t first_direct;
  uint64_t view_call;
  uint32_t input;
  uint32_t owner;
  uint32_t receiver;
};
struct Snr01DirectScope {
  uint32_t caller_lr;
  uint32_t owner;
  uint32_t arg4;
  uint32_t arg5;
  uint32_t arg6;
  uint32_t arg7;
  uint64_t first_packet;
  uint64_t ordinal;
};
struct Snr01DirectFamilyScope {
  uint64_t frame;
  uint64_t ordinal;
  uint64_t view_call;
  uint64_t first_direct;
  uint32_t context;
  uint32_t device;
  uint32_t object;
  uint32_t list;
  uint32_t arg7;
  uint32_t arg8;
};
struct Snr01ViewScope {
  uint32_t view;
  uint32_t argument;
  uint64_t first_semantic_packet;
  uint64_t first_direct_packet;
  uint64_t first_primary_packet;
  uint64_t ordinal;
  uint32_t camera = 0;
};
struct Snr01TrackCallScope {
  uint64_t ordinal;
  uint64_t view_call;
  uint64_t first_bucket;
};
struct Snr01TrackBucketScope {
  uint32_t presenter;
  uint32_t view;
  uint32_t bucket;
  uint32_t entry;
  uint32_t record;
  uint32_t secondary_record = 0;
  uint32_t remaining;
  uint64_t first_semantic_packet;
  uint64_t first_direct_packet;
  uint64_t ordinal;
  bool secondary_seen = false;
  uint32_t first_object = 0;
  uint32_t first_vtable = 0;
  int32_t first_guard = -1;
  uint32_t secondary_resolved = 0;
  bool secondary_resolved_seen = false;
  uint8_t secondary_byte52 = 0;
  uint8_t secondary_byte55 = 0;
  uint32_t auxiliary_record = 0;
  uint32_t auxiliary_resolved = 0;
  uint32_t auxiliary_flag = 0;
  bool auxiliary_seen = false;
  uint32_t second_dispatch_target = 0;
  uint32_t bound_context = 0;
  uint32_t bound_slot = 0;
  uint32_t bound_record = 0;
  uint32_t bound_target = 0;
  uint32_t bound_vertex_descriptor = 0;
  uint32_t bound_vertex_address = 0;
  uint32_t bound_vertex_size = 0;
  uint32_t vegetation_owner = 0;
  uint32_t vegetation_record_offset = 0;
  uint32_t vegetation_stream_offset = 0;
  uint32_t vegetation_record_base = 0;
  uint32_t vegetation_selected_record = 0;
  uint64_t track_call = 0;
};
struct Snr01SecondDrawScope {
  uint64_t bucket_entry;
  uint32_t target;
  uint32_t context;
  uint32_t arg4;
  uint32_t arg5;
  uint32_t arg6;
  uint32_t bound_context;
  uint32_t bound_slot;
  uint32_t bound_record;
  uint32_t bound_target;
  uint32_t bound_vertex_descriptor;
  uint32_t bound_vertex_address;
  uint32_t bound_vertex_size;
  uint32_t vegetation_owner;
  uint32_t vegetation_record_offset;
  uint32_t vegetation_stream_offset;
  uint32_t vegetation_record_base;
  uint32_t vegetation_selected_record;
  uint64_t first_semantic_packet;
  uint64_t first_direct_packet;
  uint64_t ordinal;
  uint32_t packet_physical = 0;
  uint32_t packet_count = 0;
};
struct Snr03VegetationItem {
  uint32_t owner;
  uint32_t record;
  uint32_t vertex_descriptor;
  uint32_t vertex_address;
  uint32_t vertex_size;
  uint32_t packet_physical;
  uint64_t bucket_entry;
};
struct Snr03SceneSnapshot {
  uint64_t source_frame;
  uint32_t view;
  uint32_t camera;
  std::array<uint32_t, 16> camera80;
  std::array<uint32_t, 16> camera144;
  std::vector<Snr03VegetationItem> items;
};
struct Snr03FinalState {
  uint64_t draw_sequence;
  std::array<uint32_t, 64> system_constants;
  std::array<uint32_t, 4> fetch_47;
  bool operator==(const Snr03FinalState&) const = default;
};
struct Snr03PayloadState {
  struct Draw {
    std::vector<uint8_t> vertex_bytes;
    std::array<std::array<uint32_t, 4>, 24> vertex_constants;
    std::array<uint32_t, 3> pixel_registers;
    std::array<std::array<uint32_t, 4>, 3> pixel_constants;
    uint32_t guest_vertex_count;
    std::map<uint64_t, Snr03FinalState> final_states;
  };
  std::map<uint32_t, Draw> by_packet;
  size_t bytes = 0;
  bool rejected = false;
};
struct Snr03OwnedItem {
  Snr03VegetationItem metadata;
  std::vector<uint8_t> vertex_bytes;
  std::array<std::array<uint32_t, 4>, 24> vertex_constants;
  std::array<uint32_t, 3> pixel_registers;
  std::array<std::array<uint32_t, 4>, 3> pixel_constants;
  uint32_t guest_vertex_count;
  std::map<uint64_t, Snr03FinalState> final_states;
};
struct Snr03OwnedScene {
  std::shared_ptr<const Snr03SceneSnapshot> title;
  std::vector<Snr03OwnedItem> items;
};
struct Snr02ItemSnapshot {
  uint64_t call;
  uint32_t packet;
  uint32_t kind;
  std::array<uint32_t, 23> descriptor;
  std::array<uint32_t, 17> runtime;
};
struct Snr02ItemScene {
  uint64_t source_frame;
  std::array<uint32_t, 16> camera80;
  std::array<uint32_t, 16> camera144;
  std::vector<Snr02ItemSnapshot> items;
};
struct Snr02ItemDrawState {
  uint64_t vertex_shader = 0;
  uint64_t pixel_shader = 0;
  uint64_t dynamic_state = 0;
  uint32_t index_count = 0;
  uint32_t texture_count = 0;
  std::array<rex::system::GraphicsPreparedDrawTextureFetch, 2> textures{};
  std::array<uint64_t, 4> vertex_bitmap{};
  uint32_t vertex_constant_count = 0;
  std::array<uint32_t, 1024> vertex_constants{};
  std::array<uint32_t, 64> system_constants{};
  std::array<uint32_t, 4> fetch47{};
  bool final_seen = false;
};
struct Snr02ItemPayload {
  uint32_t base = 0;
  uint32_t length = 0;
  std::vector<uint8_t> vertex_bytes;
  std::map<uint64_t, Snr02ItemDrawState> draws;
};
struct Snr02ItemPayloadState {
  std::map<uint32_t, Snr02ItemPayload> by_packet;
  size_t bytes = 0;
  size_t draw_bytes = 0;
  bool rejected = false;
};
std::vector<char> EncodeSnr03Fixture(const Snr03OwnedScene& scene) {
  std::vector<char> bytes;
  auto write = [&](const auto& value) {
    const auto* data = reinterpret_cast<const char*>(&value);
    bytes.insert(bytes.end(), data, data + sizeof(value));
  };
  constexpr std::array<char, 8> magic{'S', 'N', 'R', '0', '3', 'F', '3', '\0'};
  write(magic);
  write(scene.title->source_frame);
  write(scene.title->view);
  write(scene.title->camera);
  write(uint32_t(scene.items.size()));
  write(scene.title->camera80);
  write(scene.title->camera144);
  for (const auto& item : scene.items) {
    const auto& metadata = item.metadata;
    write(metadata.owner);
    write(metadata.record);
    write(metadata.vertex_descriptor);
    write(metadata.vertex_address);
    write(metadata.vertex_size);
    write(metadata.packet_physical);
    write(metadata.bucket_entry);
    write(item.guest_vertex_count);
    write(uint32_t(item.vertex_bytes.size()));
    write(uint32_t(item.vertex_constants.size()));
    write(uint32_t(item.final_states.size()));
    write(item.vertex_constants);
    write(item.pixel_registers);
    write(item.pixel_constants);
    bytes.insert(bytes.end(), item.vertex_bytes.begin(), item.vertex_bytes.end());
    for (const auto& [dynamic, state] : item.final_states) {
      write(dynamic);
      write(state.draw_sequence);
      write(state.system_constants);
      write(state.fetch_47);
    }
  }
  return bytes;
}
bool WriteSceneFixture(std::span<const char> bytes, uint64_t source_frame,
                       const std::filesystem::path& directory, const char* prefix) {
  const auto path = directory /
      (std::string(prefix) + std::to_string(source_frame) + ".bin");
  auto temporary = path;
  temporary += ".tmp";
  std::ofstream output(temporary, std::ios::binary | std::ios::trunc);
  if (!output) {
    return false;
  }
  output.write(bytes.data(), bytes.size());
  output.close();
  std::error_code error;
  if (!output) {
    std::filesystem::remove(temporary, error);
    return false;
  }
  std::filesystem::rename(temporary, path, error);
  if (error) {
    std::filesystem::remove(temporary, error);
    return false;
  }
  return true;
}
thread_local std::vector<Snr03VegetationItem> snr03_vegetation_items;
thread_local bool snr03_scene_overflow = false;
std::mutex snr03_scene_mutex;
std::map<uint64_t, std::shared_ptr<const Snr03SceneSnapshot>> snr03_scenes;
std::map<uint64_t, Snr03PayloadState> snr03_payloads;
thread_local std::vector<Snr02ItemSnapshot> snr02_item_title_items;
thread_local bool snr02_item_title_rejected = false;
std::mutex snr02_item_scene_mutex;
std::map<uint64_t, std::shared_ptr<const Snr02ItemScene>> snr02_item_scenes;
std::map<uint64_t, Snr02ItemPayloadState> snr02_item_payloads;
struct Snr01ItemNodeScope {
  uint32_t node;
  uint32_t list_head;
  uint32_t receiver;
  uint32_t index;
  uint32_t render_owner;
  uint64_t view_call;
  uint64_t bucket_entry;
  uint64_t first_item_call;
  uint64_t first_semantic_packet;
  uint64_t ordinal;
};
thread_local std::vector<Snr01EmitterScope> snr01_emitter_scopes;
thread_local std::vector<Snr01SecondPathScope> snr01_second_path_scopes;
thread_local std::vector<Snr01ScalarDrawScope> snr01_scalar_draw_scopes;
thread_local std::vector<Snr01DynamicQuadScope> snr01_dynamic_quad_scopes;
thread_local std::vector<Snr01DynamicQuadParentScope> snr01_dynamic_quad_parent_scopes;
thread_local uint64_t snr01_dynamic_quad_entries = 0;
thread_local uint64_t snr01_dynamic_quad_count = 0;
thread_local uint64_t snr01_scalar_draw_count = 0;
thread_local uint64_t snr01_second_path_count = 0;
std::atomic<rex::memory::Memory*> snr01_memory{nullptr};
thread_local std::vector<Snr01DirectScope> snr01_direct_scopes;
thread_local std::vector<Snr01DirectFamilyScope> snr01_direct_family_scopes;
thread_local uint64_t snr01_direct_family_count = 0;
thread_local uint64_t snr01_direct_family_record_count = 0;
thread_local std::vector<uint32_t> snr01_indexed2_callers;
thread_local std::vector<Snr01ViewScope> snr01_view_scopes;
thread_local std::vector<Snr01TrackCallScope> snr01_track75_scopes;
thread_local std::vector<Snr01TrackBucketScope> snr01_track_bucket_scopes;
thread_local std::vector<Snr01SecondDrawScope> snr01_second_draw_scopes;
thread_local std::vector<Snr01ItemNodeScope> snr01_item_node_scopes;
thread_local std::vector<uint32_t> snr01_primary_indirect_callers;
thread_local std::vector<uint32_t> snr01_queued_indirect_callers;
struct Snr01WorkerScope {
  uint32_t stream;
  uint32_t queue;
  uint64_t first_packet;
};
thread_local std::vector<Snr01WorkerScope> snr01_worker_scopes;
thread_local std::vector<uint32_t> snr01_deferred_indirect_commands;
thread_local std::vector<uint32_t> snr01_inline_indirect_callers;
thread_local std::vector<uint32_t> snr01_command_refill_callers;
thread_local std::vector<uint32_t> snr01_render_request_callers;
struct Snr01RenderThreadRequest {
  uint64_t ordinal;
  uint32_t object;
  uint32_t mode;
  uint32_t request;
  uint64_t first_view;
};
thread_local std::vector<Snr01RenderThreadRequest> snr01_render_thread_requests;
thread_local uint64_t snr01_render_thread_request_count = 0;
thread_local uint64_t snr01_scene_indirect_count = 0;
thread_local std::vector<uint32_t> snr01_scene_indirect_callers;
std::mutex snr02_track_targets_mutex;
std::set<uint32_t> snr02_track_targets;
bool snr02_track_targets_overflow = false;
bool snr02_track_title_ready = false;
std::array<uint32_t, 16> snr02_track_camera80{};
std::array<uint32_t, 16> snr02_track_camera144{};
using Snr02TrackRange = std::pair<uint32_t, uint32_t>;
struct Snr02TrackDraw {
  uint64_t sequence, vertex_shader, pixel_shader, vertex_specialization;
  uint64_t dynamic_state = 0;
  uint32_t packet, command_buffer, index_count, stride_words, host_index_format;
  uint32_t host_primitive_type, host_primitive_reset, index_endianness;
  Snr02TrackRange vertex, index;
  std::array<uint64_t, 4> vertex_bitmap{};
  std::vector<uint32_t> vertex_packed;
  std::array<uint32_t, 64> system_constants{};
  std::array<uint32_t, 4> fetch47{};
  bool final_seen = false;
};
struct Snr02TrackPayload {
  std::map<Snr02TrackRange, std::vector<uint8_t>> vertices, indices;
  std::vector<Snr02TrackDraw> draws;
  uint32_t bytes = 0;
  bool rejected = false;
};
Snr02TrackPayload snr02_track_payload;
struct Snr01SceneListFlush {
  uint32_t caller;
  uint32_t owner;
  uint32_t owner_first_word;
  uint32_t input;
  uint64_t owner_call;
  uint32_t owner_caller_lr;
  std::array<uint32_t, 7> owner_args;
};
thread_local std::vector<Snr01SceneListFlush> snr01_scene_list_flushes;
struct Snr01CarOwnerCall {
  uint64_t ordinal = 0;
  uint32_t owner = 0;
  uint32_t caller_lr = 0;
  std::array<uint32_t, 7> args{};
};
thread_local Snr01CarOwnerCall snr01_car_owner_call;
thread_local uint64_t snr01_car_owner_call_count = 0;
std::atomic<uint32_t> snr01_vehicle_map_pool_root{0};
std::mutex snr01_player_mutex;
std::set<uint32_t> snr01_forza_players;
std::map<uint32_t, uint32_t> snr01_car_presentations;
thread_local std::set<uint32_t> snr01_view8_flush_owners;
thread_local std::vector<Snr01DispatchScope> snr01_dispatch_scopes;
thread_local std::vector<Snr01DispatchScope> snr01_render_state_scopes;
thread_local std::vector<Snr01ProceduralScope> snr01_procedural_scopes;
thread_local uint64_t snr01_packet_count = 0;
thread_local uint64_t snr01_semantic_packet_count = 0;
thread_local uint64_t snr01_procedural_count = 0;
thread_local uint64_t snr01_dispatch_count = 0;
thread_local uint64_t snr01_render_state_count = 0;
thread_local uint64_t snr01_emitter_count = 0;
thread_local uint64_t snr01_state_wrapper_count = 0;
thread_local uint64_t snr01_dispatch_wrapper_count = 0;
thread_local uint64_t snr01_track75_count = 0;
thread_local uint64_t snr01_unmatched_track75_exits = 0;
thread_local uint64_t snr01_track79_count = 0;
thread_local uint64_t snr01_track_pass_count = 0;
thread_local uint64_t snr01_view_begin_count = 0;
thread_local uint64_t snr01_view_frame = 0;
thread_local uint64_t snr01_view_selected_count = 0;
thread_local uint64_t snr01_view_track_count = 0;
thread_local uint64_t snr01_camera_method_count = 0;
thread_local uint64_t snr01_indexed2_owner_count = 0;
thread_local uint64_t snr01_track_bucket_count = 0;
thread_local uint64_t snr01_second_draw_count = 0;
thread_local uint64_t snr01_second_draw_skips = 0;
thread_local uint64_t snr01_unmatched_second_draw_exits = 0;
thread_local uint64_t snr01_item_node_count = 0;
thread_local uint64_t snr01_direct_call_count = 0;
thread_local uint64_t snr01_direct_packet_count = 0;
thread_local uint64_t snr01_resident_packet_count = 0;
std::mutex snr01_watch_mutex;
std::set<uint32_t> snr01_watch_pages;
void* snr01_watch_access_handle = nullptr;
void* snr01_watch_invalidation_handle = nullptr;
std::atomic<uint32_t> snr01_watch_events{0};
constexpr uint32_t kSnr01WatchPageLimit = 1024;
constexpr uint32_t kSnr01WatchEventLimit = 8192;
thread_local uint64_t snr01_primary_indirect_packet_count = 0;
thread_local uint64_t snr01_unmatched_direct_exits = 0;
thread_local uint64_t snr01_unmatched_track_bucket_exits = 0;
thread_local uint64_t snr01_unmatched_item_node_exits = 0;
thread_local uint64_t snr01_unmatched_emitter_exits = 0;
thread_local uint64_t snr01_unmatched_dispatch_exits = 0;
thread_local uint64_t snr01_unmatched_render_state_exits = 0;
thread_local uint64_t snr01_unmatched_exits = 0;
constexpr uint64_t kSnr01PacketLimit = 8192;
constexpr uint64_t kSnr01ProceduralLimit = 4096;
constexpr uint64_t kSnrM02WaitLimit = 512;
constexpr uint64_t kSnrM02WriterLimit = 2048;

struct SnrM02WaitScope {
  uint64_t ordinal;
  uint32_t device;
  uint32_t requested;
  uint32_t caller;
  uint32_t published_before;
  uint32_t produced_before;
  uint32_t snapshot_published = 0;
  uint32_t snapshot_counter = 0;
  uint32_t snapshot_timebase = 0;
  uint32_t recovery_counter = 0;
  uint32_t recoveries = 0;
  bool entered_loop = false;
  int64_t begin_ns;
};
thread_local std::vector<SnrM02WaitScope> snr_m02_wait_scopes;
thread_local uint64_t snr_m02_wait_count = 0;
thread_local uint64_t snr_m02_writer_count = 0;
std::atomic<uint64_t> snr02_rebuild_capture{0};
std::atomic<uint32_t> snr02_rebuild_flags_address{0};
std::atomic<uint32_t> snr02_rebuild_draw_count{0};
thread_local uint64_t snr02_view_frame = 0;
thread_local uint32_t snr02_view_count = 0;
thread_local std::vector<uint32_t> snr02_view_scopes;

bool SnrM02TraceCurrentFrame() {
  static const int32_t target = REXCVAR_GET(pinyon_shift_snr_m02_trace_source_frame);
  const auto frame = rex::perf::GetTotalCounter(
      rex::perf::CounterId::kSourceFrameCount);
  return target > 0 && frame + 1 >= uint64_t(target) &&
         frame <= uint64_t(target) + 1;
}

int64_t SnrM02NowNs() {
  return std::chrono::duration_cast<std::chrono::nanoseconds>(
             ClearClock::now().time_since_epoch())
      .count();
}

uint32_t SnrM02ReadU32(uint32_t address) {
  const auto* memory = snr01_memory.load(std::memory_order_acquire);
  return memory && address
             ? rex::memory::load_and_swap<uint32_t>(memory->TranslateVirtual(address))
             : 0;
}

int32_t Snr03TargetFrame() {
  static const int32_t target = REXCVAR_GET(pinyon_shift_snr03_probe_frame);
  return target;
}

int32_t Snr02ItemTargetFrame() {
  static const int32_t target = REXCVAR_GET(pinyon_shift_snr02_item_payload_probe)
                                    ? REXCVAR_GET(pinyon_shift_snr01_trace_source_frame)
                                    : 0;
  return target;
}

int32_t Snr02TrackTargetFrame() {
  static const int32_t target = REXCVAR_GET(pinyon_shift_snr02_track_payload_probe)
                                    ? REXCVAR_GET(pinyon_shift_snr01_trace_source_frame)
                                    : 0;
  return target;
}

uint64_t Snr03HashBytes(const std::vector<uint8_t>& bytes);

bool Snr02SelectTrackSnapshot(uint64_t frame, uint32_t command_buffer) {
  if (Snr02TrackTargetFrame() <= 0 ||
      frame != uint64_t(Snr02TrackTargetFrame()) + 1) return false;
  std::lock_guard lock(snr02_track_targets_mutex);
  return !snr02_track_targets_overflow &&
         snr02_track_targets.contains(command_buffer);
}

bool Snr02OwnTrackRange(
    std::map<Snr02TrackRange, std::vector<uint8_t>>& ranges,
    Snr02TrackRange key, const uint8_t* bytes, uint32_t status, uint64_t hash,
    Snr02TrackPayload& payload) {
  if (status != 1 || !bytes || !key.second) return false;
  const auto existing = ranges.find(key);
  if (existing != ranges.end()) {
    return std::equal(existing->second.begin(), existing->second.end(), bytes);
  }
  constexpr uint32_t kOwnedBytesLimit = 8 * 1024 * 1024;
  if (payload.bytes > kOwnedBytesLimit ||
      key.second > kOwnedBytesLimit - payload.bytes) return false;
  auto& owned = ranges[key];
  owned.assign(bytes, bytes + key.second);
  if (Snr03HashBytes(owned) != hash) {
    ranges.erase(key);
    return false;
  }
  payload.bytes += key.second;
  return true;
}

uint64_t Snr03Fingerprint(const Snr03SceneSnapshot& scene) {
  uint64_t hash = 14695981039346656037ull;
  const auto add = [&hash](uint64_t value) {
    hash ^= value;
    hash *= 1099511628211ull;
  };
  add(scene.source_frame);
  add(scene.view);
  add(scene.camera);
  for (const auto word : scene.camera80) add(word);
  for (const auto word : scene.camera144) add(word);
  for (const auto& item : scene.items) {
    add(item.owner);
    add(item.record);
    add(item.vertex_descriptor);
    add(item.vertex_address);
    add(item.vertex_size);
    add(item.packet_physical);
    add(item.bucket_entry);
  }
  return hash;
}

uint64_t Snr03HashBytes(const std::vector<uint8_t>& bytes) {
  uint64_t hash = 14695981039346656037ull;
  for (const uint8_t byte : bytes) {
    hash = (hash ^ byte) * 1099511628211ull;
  }
  return hash;
}

uint64_t Snr02HashWords(std::span<const uint32_t> words) {
  uint64_t hash = 14695981039346656037ull;
  for (uint32_t word : words) hash = (hash ^ word) * 1099511628211ull;
  return hash;
}

uint32_t SnrM02Physical(uint32_t address) {
  const auto* memory = snr01_memory.load(std::memory_order_acquire);
  return memory && address ? memory->GetPhysicalAddress(address) : UINT32_MAX;
}

void Snr01RecordWatchedPages(const char* path, uint32_t start, uint32_t length,
                            bool is_write) {
  static const int32_t target = REXCVAR_GET(pinyon_shift_snr01_trace_source_frame);
  const uint64_t frame = rex::perf::GetTotalCounter(
      rex::perf::CounterId::kSourceFrameCount);
  if (target <= 0 || frame + 1 < uint64_t(target) ||
      frame > uint64_t(target) + 1) {
    return;
  }
  std::lock_guard lock(snr01_watch_mutex);
  for (auto it = snr01_watch_pages.lower_bound(start);
       it != snr01_watch_pages.end() && uint64_t(*it) < uint64_t(start) + length;
       ++it) {
    const uint32_t ordinal = ++snr01_watch_events;
    if (ordinal > kSnr01WatchEventLimit) {
      if (ordinal == kSnr01WatchEventLimit + 1) {
        REXGPU_INFO("FH1 SNR01 watched page trace limit reached");
      }
      return;
    }
    REXGPU_INFO("FH1 SNR01 watched page {{\"frame\":{},\"path\":\"{}\","
                "\"page\":{},\"is_write\":{}}}",
                frame, path, *it, is_write);
  }
}

void Snr01WatchAccess(void*, uint32_t start, uint32_t length, bool is_write) {
  Snr01RecordWatchedPages("guest_access", start, length, is_write);
}

std::pair<uint32_t, uint32_t> Snr01WatchInvalidation(
    void*, uint32_t start, uint32_t length, bool exact_range) {
  Snr01RecordWatchedPages(exact_range ? "exact_invalidation" : "invalidation",
                          start, length, true);
  return {start, length};
}

void Snr01ArmPacketPage(uint32_t packet_physical) {
  auto* memory = snr01_memory.load(std::memory_order_acquire);
  if (!memory ||
      !((packet_physical >= 0x14000000 && packet_physical < 0x16000000) ||
        (packet_physical >= 0x17000000 && packet_physical < 0x18000000))) {
    return;
  }
  const uint32_t page_size = uint32_t(rex::memory::page_size());
  const uint32_t page = packet_physical & ~(page_size - 1);
  {
    std::lock_guard lock(snr01_watch_mutex);
    if (snr01_watch_pages.size() >= kSnr01WatchPageLimit ||
        !snr01_watch_pages.insert(page).second) {
      return;
    }
  }
  memory->EnablePhysicalMemoryAccessCallbacks(page, page_size, true, false,
                                               true);
  REXGPU_INFO("FH1 SNR01 watch armed {{\"frame\":{},\"page\":{}}}",
              rex::perf::GetTotalCounter(
                  rex::perf::CounterId::kSourceFrameCount),
              page);
}

bool Snr01TraceCurrentFrame() {
  static const int32_t target = REXCVAR_GET(pinyon_shift_snr01_trace_source_frame);
  const uint64_t frame = rex::perf::GetTotalCounter(
      rex::perf::CounterId::kSourceFrameCount);
  return (target > 0 &&
          (frame == uint64_t(target) ||
           (REXCVAR_GET(pinyon_shift_snr01_trace_following_frame) &&
            frame == uint64_t(target) + 1))) ||
         (Snr03TargetFrame() > 0 && frame == uint64_t(Snr03TargetFrame()));
}

bool Snr02TraceCapturedFrame() {
  const uint64_t capture = snr02_rebuild_capture.load(std::memory_order_acquire);
  return capture &&
         rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount) ==
             capture >> 32;
}

bool Snr01TracePrimaryIndirectFrame() {
  static const int32_t target = REXCVAR_GET(pinyon_shift_snr01_trace_source_frame);
  const uint64_t frame = rex::perf::GetTotalCounter(
      rex::perf::CounterId::kSourceFrameCount);
  return target > 0 && frame >= uint64_t(target) &&
         frame <= uint64_t(target) + 1;
}

bool Snr01TraceLinkedWriteFrame() {
  static const int32_t target = REXCVAR_GET(pinyon_shift_snr01_trace_source_frame);
  const uint64_t frame = rex::perf::GetTotalCounter(
      rex::perf::CounterId::kSourceFrameCount);
  return target > 0 && frame + 12 >= uint64_t(target) &&
         frame <= uint64_t(target) + 1;
}

uint64_t Snr01CameraMatrixHash(uint32_t camera, uint32_t offset) {
  if (!camera) {
    return 0;
  }
  auto* memory = snr01_memory.load(std::memory_order_acquire);
  if (!memory) {
    return 0;
  }
  uint64_t hash = 14695981039346656037ull;
  for (uint32_t i = 0; i < 16; ++i) {
    hash ^= rex::memory::load_and_swap<uint32_t>(
        memory->TranslateVirtual(camera + offset + i * 4));
    hash *= 1099511628211ull;
  }
  return hash;
}

void RecordSnr01ResidentPacket(const char* path, uint32_t previous_word,
                               uint32_t header_word, uint32_t command_owner) {
  static const bool enabled = REXCVAR_GET(
      pinyon_shift_snr01_trace_resident_packet_writers);
  if (!enabled) {
    return;
  }
  const uint32_t physical = (previous_word + 4) & 0x1FFFFFFF;
  if (physical < 0x14000000 ||
      (physical >= 0x16000000 && physical < 0x17000000) ||
      physical >= 0x18000000 ||
      ++snr01_resident_packet_count > kSnr01PacketLimit) {
    return;
  }
  REXGPU_INFO(
      "FH1 SNR01 resident packet {{\"frame\":{},\"ordinal\":{},"
      "\"path\":\"{}\",\"header_physical\":{},"
      "\"header_word\":{},\"command_owner\":{}}}",
      rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
      snr01_resident_packet_count, path, physical, header_word, command_owner);
}

void RecordSnr01SemanticPacket(const char* path, uint32_t previous_word,
                               uint32_t header_word, uint32_t command_owner) {
  RecordSnr01ResidentPacket(path, previous_word, header_word, command_owner);
  if (!Snr01TraceCurrentFrame()) {
    return;
  }
  const uint64_t ordinal = ++snr01_semantic_packet_count;
  if (ordinal > kSnr01PacketLimit) {
    return;
  }
  const uint32_t guest_address = previous_word + 4;
  if (Snr02ItemTargetFrame() > 0 &&
      rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount) ==
          uint64_t(Snr02ItemTargetFrame()) &&
      !snr01_procedural_scopes.empty() && !snr01_view_scopes.empty() &&
      snr01_view_scopes.back().ordinal == 8) {
    auto& item = snr01_procedural_scopes.back();
    item.snapshot_packet = guest_address & 0x1FFFFFFF;
    ++item.snapshot_packet_count;
  }
  if (Snr03TargetFrame() > 0 &&
      uint64_t(Snr03TargetFrame()) == uint64_t(rex::perf::GetTotalCounter(
          rex::perf::CounterId::kSourceFrameCount)) &&
      !snr01_second_draw_scopes.empty()) {
    auto& draw = snr01_second_draw_scopes.back();
    draw.packet_physical = guest_address & 0x1FFFFFFF;
    ++draw.packet_count;
  }
  REXGPU_INFO(
      "FH1 SNR01 semantic packet {{\"frame\":{},\"ordinal\":{},"
      "\"path\":\"{}\",\"header_guest\":{},\"header_physical\":{},"
      "\"header_word\":{},\"command_owner\":{},"
      "\"procedural_receiver\":{},\"procedural_call\":{},"
      "\"dispatch_receiver\":{},\"dispatch_call\":{},"
      "\"render_state_receiver\":{},\"render_state_call\":{},"
      "\"emitter_call\":{},\"emitter_caller_lr\":{}}}",
      rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
      ordinal, path, guest_address, guest_address & 0x1FFFFFFF,
      header_word, command_owner,
      snr01_procedural_scopes.empty()
          ? 0 : snr01_procedural_scopes.back().receiver,
      snr01_procedural_scopes.empty()
          ? 0 : snr01_procedural_scopes.back().ordinal,
      snr01_dispatch_scopes.empty()
          ? 0 : snr01_dispatch_scopes.back().receiver,
      snr01_dispatch_scopes.empty()
          ? 0 : snr01_dispatch_scopes.back().ordinal,
      snr01_render_state_scopes.empty()
          ? 0 : snr01_render_state_scopes.back().receiver,
      snr01_render_state_scopes.empty()
          ? 0 : snr01_render_state_scopes.back().ordinal,
      snr01_emitter_scopes.empty()
          ? 0 : snr01_emitter_scopes.back().ordinal,
      snr01_emitter_scopes.empty()
          ? 0 : snr01_emitter_scopes.back().caller_lr);
}

void RecordSnr01DirectPacket(const char* path, uint32_t previous_word,
                             uint32_t header_word, uint32_t command_owner) {
  RecordSnr01ResidentPacket(path, previous_word, header_word, command_owner);
  if (!Snr01TraceCurrentFrame()) {
    return;
  }
  const uint64_t ordinal = ++snr01_direct_packet_count;
  if (ordinal > kSnr01PacketLimit) {
    return;
  }
  const uint32_t guest_address = previous_word + 4;
  REXGPU_INFO(
      "FH1 SNR01 direct packet {{\"frame\":{},\"ordinal\":{},"
      "\"path\":\"{}\",\"header_guest\":{},"
      "\"header_physical\":{},\"header_word\":{},"
      "\"command_owner\":{},\"direct_call\":{},"
      "\"direct_caller_lr\":{},\"indexed2_caller_lr\":{}}}",
      rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
      ordinal, path, guest_address, guest_address & 0x1FFFFFFF,
      header_word, command_owner,
      snr01_direct_scopes.empty() ? 0 : snr01_direct_scopes.back().ordinal,
      snr01_direct_scopes.empty() ? 0 : snr01_direct_scopes.back().caller_lr,
      snr01_indexed2_callers.empty() ? 0 : snr01_indexed2_callers.back());
}

bool ClearProducerTraceEnabled() {
  static const bool enabled = REXCVAR_GET(pinyon_shift_fh1_clear_producer_trace);
  return enabled;
}

}  // namespace

namespace pinyon_shift::native_renderer {
namespace {

void ObserveSnr03VertexPayload(
    const rex::system::GraphicsPreparedDrawObservation& observation) {
  const int32_t target = Snr03TargetFrame();
  if (target <= 0 || observation.frame_sequence != uint64_t(target) + 1) {
    return;
  }
  std::lock_guard lock(snr03_scene_mutex);
  const auto scene_it = snr03_scenes.find(uint64_t(target));
  if (scene_it == snr03_scenes.end()) {
    return;
  }
  const auto& items = scene_it->second->items;
  const auto item_it = std::find_if(items.begin(), items.end(), [&](const auto& item) {
    return item.packet_physical == observation.draw_packet_physical_address;
  });
  if (item_it == items.end()) {
    return;
  }
  auto& payload = snr03_payloads[uint64_t(target)];
  const auto* fetch = observation.vertex_fetches;
  static constexpr std::array<uint32_t, 24> kVertexConstants = {
      128, 129, 130, 131, 157, 158, 159, 160, 161, 163, 214, 215,
      221, 241, 242, 243, 244, 245, 250, 251, 253, 254, 255, 256};
  if (observation.vertex_fetch_count != 1 || !fetch ||
      observation.vertex_shader_hash != 0x5834939992FFC765ull ||
      observation.pixel_shader_hash != 0xC2F1242C2535A57Eull ||
      observation.guest_primitive_type != 13 || observation.index_buffer_type != 0 ||
      observation.index_count == 0 || observation.index_count % 4 != 0 ||
      observation.index_count * 4 != (item_it->vertex_size & 0x03FFFFFC) ||
      !observation.vertex_float_constant_words ||
      !observation.pixel_float_constant_bitmap ||
      observation.pixel_float_constant_count != 3 ||
      fetch[0].fetch_constant != 95 || fetch[0].stride_words != 4 ||
      fetch[0].guest_base != (item_it->vertex_address & 0x1FFFFFFC) ||
      fetch[0].length != (item_it->vertex_size & 0x03FFFFFC) ||
      fetch[0].cpu_snapshot_status != 1 || !fetch[0].cpu_snapshot_bytes) {
    payload.rejected = true;
    return;
  }
  const uint32_t packet = item_it->packet_physical;
  const auto* begin = fetch[0].cpu_snapshot_bytes;
  Snr03PayloadState::Draw draw{};
  draw.guest_vertex_count = observation.index_count;
  for (size_t i = 0; i < kVertexConstants.size(); ++i) {
    const auto* words = observation.vertex_float_constant_words +
                        kVertexConstants[i] * 4;
    std::copy_n(words, 4, draw.vertex_constants[i].begin());
  }
  size_t pixel_count = 0;
  for (uint32_t reg = 0; reg < 256; ++reg) {
    if (!(observation.pixel_float_constant_bitmap[reg / 64] &
          (uint64_t(1) << (reg % 64)))) {
      continue;
    }
    if (pixel_count == draw.pixel_registers.size()) {
      payload.rejected = true;
      return;
    }
    draw.pixel_registers[pixel_count] = reg;
    std::copy_n(observation.vertex_float_constant_words + (256 + reg) * 4, 4,
                draw.pixel_constants[pixel_count].begin());
    ++pixel_count;
  }
  if (pixel_count != draw.pixel_registers.size()) {
    payload.rejected = true;
    return;
  }
  auto existing = payload.by_packet.find(packet);
  if (existing != payload.by_packet.end()) {
    if (existing->second.vertex_bytes.size() != fetch[0].length ||
        !std::equal(existing->second.vertex_bytes.begin(),
                    existing->second.vertex_bytes.end(), begin) ||
        existing->second.vertex_constants != draw.vertex_constants ||
        existing->second.pixel_registers != draw.pixel_registers ||
        existing->second.pixel_constants != draw.pixel_constants ||
        existing->second.guest_vertex_count != draw.guest_vertex_count) {
      payload.rejected = true;
    }
    return;
  }
  if (payload.by_packet.size() >= 512 ||
      fetch[0].length > 2 * 1024 * 1024 - payload.bytes) {
    payload.rejected = true;
    return;
  }
  payload.bytes += fetch[0].length;
  draw.vertex_bytes.assign(begin, begin + fetch[0].length);
  const auto& stored = payload.by_packet.emplace(packet, std::move(draw)).first->second;
  for (size_t i = 0; i < stored.pixel_registers.size(); ++i) {
    const auto& words = stored.pixel_constants[i];
    REXGPU_INFO("FH1 SNR03 pixel constant {{\"frame\":{},\"packet\":{},"
                "\"register\":{},\"words\":[{},{},{},{}]}}",
                observation.frame_sequence, packet, stored.pixel_registers[i],
                words[0], words[1], words[2], words[3]);
  }
}

void ObserveSnr02ItemFinalDrawState(
    const rex::system::GraphicsFinalDrawStateObservation& observation) {
  const int32_t target = Snr02ItemTargetFrame();
  if (target <= 0 || observation.frame_sequence != uint64_t(target) + 1) return;
  std::lock_guard lock(snr02_item_scene_mutex);
  const auto scene = snr02_item_scenes.find(uint64_t(target));
  if (scene == snr02_item_scenes.end()) return;
  const auto item = std::find_if(scene->second->items.begin(),
                                 scene->second->items.end(), [&](const auto& row) {
    return row.packet == observation.draw_packet_physical_address;
  });
  if (item == scene->second->items.end()) return;
  auto& state = snr02_item_payloads[uint64_t(target)];
  const auto geometry = state.by_packet.find(item->packet);
  if (geometry == state.by_packet.end() ||
      !observation.system_constant_words ||
      observation.system_constant_word_count < 64 ||
      !observation.fetch_47_words ||
      !observation.vertex_float_constant_words ||
      !observation.bound_vertex_float_constant_words) {
    state.rejected = true;
    return;
  }
  const auto variant = geometry->second.draws.find(observation.draw_sequence);
  if (variant == geometry->second.draws.end() || variant->second.final_seen ||
      variant->second.dynamic_state != observation.dynamic_state) {
    state.rejected = true;
    return;
  }
  auto& draw = variant->second;
  std::copy_n(observation.system_constant_words, draw.system_constants.size(),
              draw.system_constants.begin());
  std::copy_n(observation.fetch_47_words, draw.fetch47.size(),
              draw.fetch47.begin());
  const bool vertex_changed = !std::equal(
      draw.vertex_constants.begin(), draw.vertex_constants.end(),
      observation.vertex_float_constant_words);
  std::array<uint32_t, 1024> packed{};
  uint32_t packed_words = 0;
  for (uint32_t reg = 0; reg < 256; ++reg) {
    if (draw.vertex_bitmap[reg / 64] & (uint64_t(1) << (reg % 64))) {
      std::copy_n(draw.vertex_constants.begin() + reg * 4, 4,
                  packed.begin() + packed_words);
      packed_words += 4;
    }
  }
  if (observation.bound_vertex_float_constant_count * 4 != packed_words) {
    state.rejected = true;
    return;
  }
  const bool bound_changed = !std::equal(packed.begin(),
                                         packed.begin() + packed_words,
                                         observation.bound_vertex_float_constant_words);
  draw.final_seen = true;
  REXGPU_INFO("FH1 SNR02 item final state {{\"frame\":{},\"packet\":{},"
              "\"sequence\":{},\"dynamic\":{},\"system_hash\":{},"
              "\"fetch47_hash\":{},\"vertex_changed\":{},\"final_vertex_hash\":{},"
              "\"bound_changed\":{},\"bound_vertex_hash\":{}}}",
              observation.frame_sequence,
              item->packet, observation.draw_sequence, observation.dynamic_state,
              Snr02HashWords(draw.system_constants), Snr02HashWords(draw.fetch47),
              vertex_changed,
              Snr02HashWords(std::span(observation.vertex_float_constant_words,
                                       draw.vertex_constants.size())),
              bound_changed,
              Snr02HashWords(std::span(observation.bound_vertex_float_constant_words,
                                       packed_words)));
}

void ObserveSnr02TrackFinalDrawState(
    const rex::system::GraphicsFinalDrawStateObservation& observation) {
  if (Snr02TrackTargetFrame() <= 0 ||
      observation.frame_sequence != uint64_t(Snr02TrackTargetFrame()) + 1) return;
  std::lock_guard lock(snr02_track_targets_mutex);
  auto& payload = snr02_track_payload;
  const auto found = std::find_if(payload.draws.begin(), payload.draws.end(),
                                  [&](const auto& draw) {
    return draw.sequence == observation.draw_sequence;
  });
  if (found == payload.draws.end()) return;
  auto& draw = *found;
  if (draw.final_seen || draw.packet != observation.draw_packet_physical_address ||
      !observation.system_constant_words ||
      observation.system_constant_word_count < 64 ||
      !observation.fetch_47_words ||
      !observation.vertex_float_constant_words ||
      !observation.bound_vertex_float_constant_words ||
      observation.bound_vertex_float_constant_count * 4 !=
          draw.vertex_packed.size()) {
    payload.rejected = true;
    return;
  }
  uint32_t word = 0;
  bool vertex_changed = false;
  for (uint32_t reg = 0; reg < 256; ++reg) {
    if (draw.vertex_bitmap[reg / 64] & (uint64_t(1) << (reg % 64))) {
      vertex_changed |= !std::equal(
          draw.vertex_packed.begin() + word,
          draw.vertex_packed.begin() + word + 4,
          observation.vertex_float_constant_words + reg * 4);
      word += 4;
    }
  }
  const bool bound_changed = !std::equal(
      draw.vertex_packed.begin(), draw.vertex_packed.end(),
      observation.bound_vertex_float_constant_words);
  if (vertex_changed || bound_changed) payload.rejected = true;
  draw.dynamic_state = observation.dynamic_state;
  std::copy_n(observation.system_constant_words, 64,
              draw.system_constants.begin());
  std::copy_n(observation.fetch_47_words, 4, draw.fetch47.begin());
  draw.final_seen = true;
  REXGPU_INFO("FH1 SNR02 track final state {{\"frame\":{},\"packet\":{},"
              "\"sequence\":{},\"dynamic\":{},"
              "\"system_hash\":{},\"fetch47_hash\":{},"
              "\"vertex_changed\":{},\"bound_changed\":{},"
              "\"bound_hash\":{}}}",
              observation.frame_sequence, draw.packet, draw.sequence,
              draw.dynamic_state, Snr02HashWords(draw.system_constants),
              Snr02HashWords(draw.fetch47), vertex_changed, bound_changed,
              Snr02HashWords(std::span(
                  observation.bound_vertex_float_constant_words,
                  draw.vertex_packed.size())));
}

void ObserveSnr03FinalDrawState(
    const rex::system::GraphicsFinalDrawStateObservation& observation) {
  ObserveSnr02TrackFinalDrawState(observation);
  ObserveSnr02ItemFinalDrawState(observation);
  const int32_t target = Snr03TargetFrame();
  if (target <= 0 || observation.frame_sequence != uint64_t(target) + 1) {
    return;
  }
  std::lock_guard lock(snr03_scene_mutex);
  const auto scene = snr03_scenes.find(uint64_t(target));
  if (scene == snr03_scenes.end()) {
    return;
  }
  const auto item = std::find_if(scene->second->items.begin(),
                                 scene->second->items.end(), [&](const auto& value) {
    return value.packet_physical == observation.draw_packet_physical_address;
  });
  if (item == scene->second->items.end()) {
    return;
  }
  auto& payload = snr03_payloads[uint64_t(target)];
  const auto draw = payload.by_packet.find(item->packet_physical);
  if (draw == payload.by_packet.end() || !observation.system_constant_words ||
      observation.system_constant_word_count < 64 ||
      !observation.fetch_47_words) {
    payload.rejected = true;
    return;
  }
  Snr03FinalState state{};
  state.draw_sequence = observation.draw_sequence;
  auto& system = state.system_constants;
  auto& fetch = state.fetch_47;
  std::copy_n(observation.system_constant_words, system.size(), system.begin());
  std::copy_n(observation.fetch_47_words, fetch.size(), fetch.begin());
  auto& variants = draw->second.final_states;
  const auto existing = variants.find(observation.dynamic_state);
  if (existing != variants.end()) {
    payload.rejected = true;
    REXGPU_INFO("FH1 SNR03 repeated final state packet={} dynamic={:016X}",
                item->packet_physical, observation.dynamic_state);
    return;
  }
  if (variants.size() >= 4) {
    payload.rejected = true;
    return;
  }
  variants.emplace(observation.dynamic_state, state);
  REXGPU_INFO("FH1 SNR03 final draw state {{\"frame\":{},\"packet\":{},"
              "\"sequence\":{},\"dynamic\":\"{:016X}\","
              "\"system0\":[{},{},{},{}],\"system1\":[{},{},{},{}],"
              "\"system8\":[{},{},{},{}],\"system9\":[{},{},{},{}],"
              "\"system14\":[{},{},{},{}],\"system15\":[{},{},{},{}],"
              "\"fetch47\":[{},{},{},{}]}}",
              observation.frame_sequence, item->packet_physical,
              observation.draw_sequence,
              observation.dynamic_state,
              system[0], system[1], system[2], system[3],
              system[4], system[5], system[6], system[7],
              system[32], system[33], system[34], system[35],
              system[36], system[37], system[38], system[39],
              system[56], system[57], system[58], system[59],
              system[60], system[61], system[62], system[63],
              fetch[0], fetch[1], fetch[2], fetch[3]);
}

void ObserveSnr02ItemVertexPayload(
    const rex::system::GraphicsPreparedDrawObservation& observation) {
  const int32_t target = Snr02ItemTargetFrame();
  if (target <= 0 || observation.frame_sequence != uint64_t(target) + 1) return;
  std::lock_guard lock(snr02_item_scene_mutex);
  const auto scene = snr02_item_scenes.find(uint64_t(target));
  if (scene == snr02_item_scenes.end()) return;
  const auto item = std::find_if(scene->second->items.begin(),
                                 scene->second->items.end(), [&](const auto& row) {
    return row.packet == observation.draw_packet_physical_address;
  });
  if (item == scene->second->items.end()) return;
  auto& state = snr02_item_payloads[uint64_t(target)];
  if (observation.vertex_fetch_count != 1 || !observation.vertex_fetches ||
      observation.index_buffer_type != 0 || observation.guest_primitive_type != 13) {
    state.rejected = true;
    return;
  }
  const auto& fetch = observation.vertex_fetches[0];
  if (fetch.fetch_constant != 95 || fetch.stride_words != 10 ||
      fetch.length != observation.index_count * 10 ||
      fetch.cpu_snapshot_status != 1 || !fetch.cpu_snapshot_bytes ||
      !observation.draw_sequence || !observation.vertex_float_constant_words ||
      !observation.vertex_float_constant_bitmap ||
      observation.texture_fetch_count > 2 ||
      (observation.texture_fetch_count && !observation.texture_fetches)) {
    state.rejected = true;
    return;
  }
  auto existing = state.by_packet.find(item->packet);
  if (existing != state.by_packet.end()) {
    auto& value = existing->second;
    if (value.base != fetch.guest_base || value.length != fetch.length ||
        !std::equal(value.vertex_bytes.begin(), value.vertex_bytes.end(),
                    fetch.cpu_snapshot_bytes)) {
      state.rejected = true;
      return;
    }
  } else {
    if (state.by_packet.size() >= 512 ||
        fetch.length > 2 * 1024 * 1024 - state.bytes) {
      state.rejected = true;
      return;
    }
    Snr02ItemPayload value{};
    value.base = fetch.guest_base;
    value.length = fetch.length;
    value.vertex_bytes.assign(fetch.cpu_snapshot_bytes,
                              fetch.cpu_snapshot_bytes + fetch.length);
    if (Snr03HashBytes(value.vertex_bytes) != fetch.cpu_snapshot_hash) {
      state.rejected = true;
      return;
    }
    state.bytes += fetch.length;
    existing = state.by_packet.emplace(item->packet, std::move(value)).first;
  }
  if (existing->second.draws.size() >= 8 ||
      state.draw_bytes > 8 * 1024 * 1024 - sizeof(Snr02ItemDrawState) ||
      existing->second.draws.contains(observation.draw_sequence)) {
    state.rejected = true;
    return;
  }
  Snr02ItemDrawState draw{};
  draw.vertex_shader = observation.vertex_shader_hash;
  draw.pixel_shader = observation.pixel_shader_hash;
  draw.dynamic_state = observation.fh1_execution_key.dynamic_state;
  draw.index_count = observation.index_count;
  draw.texture_count = observation.texture_fetch_count;
  draw.vertex_constant_count = observation.vertex_float_constant_count;
  std::copy_n(observation.vertex_float_constant_bitmap, draw.vertex_bitmap.size(),
              draw.vertex_bitmap.begin());
  uint32_t mapped = 0;
  for (uint64_t bits : draw.vertex_bitmap) mapped += std::popcount(bits);
  if (mapped != draw.vertex_constant_count ||
      mapped != (draw.vertex_shader == 0x3BC346726C1C2535ull ||
                 draw.vertex_shader == 0xBDFD2AD68464101Aull ? 25u : 23u)) {
    state.rejected = true;
    return;
  }
  if (draw.texture_count) {
    std::copy_n(observation.texture_fetches, draw.texture_count,
                draw.textures.begin());
  }
  std::copy_n(observation.vertex_float_constant_words, draw.vertex_constants.size(),
              draw.vertex_constants.begin());
  REXGPU_INFO("FH1 SNR02 item draw state {{\"frame\":{},\"packet\":{},"
              "\"sequence\":{},\"vertex_hash\":{},"
              "\"bitmap\":[{},{},{},{}],\"mapped\":{}}}",
              observation.frame_sequence, item->packet, observation.draw_sequence,
              Snr02HashWords(draw.vertex_constants),
              draw.vertex_bitmap[0], draw.vertex_bitmap[1],
              draw.vertex_bitmap[2], draw.vertex_bitmap[3], mapped);
  existing->second.draws.emplace(observation.draw_sequence, std::move(draw));
  state.draw_bytes += sizeof(Snr02ItemDrawState);
}

void ObservePreparedDraw(
    const rex::system::GraphicsPreparedDrawObservation& observation) {
  ObserveSnr02ItemVertexPayload(observation);
  ObserveSnr03VertexPayload(observation);
  if (Snr02SelectTrackSnapshot(observation.frame_sequence,
                               observation.command_buffer_physical_address)) {
    bool captured = false;
    uint32_t packed_words = 0;
    uint64_t packed_hash = 0;
    std::array<uint64_t, 4> bitmap{};
    {
      std::lock_guard lock(snr02_track_targets_mutex);
      auto& payload = snr02_track_payload;
      if (!payload.rejected && payload.draws.size() < 4096 &&
          observation.draw_sequence && observation.guest_primitive_type == 6 &&
          observation.index_buffer_type == 1 &&
          observation.vertex_fetch_count == 1 && observation.vertex_fetches &&
          observation.vertex_fetch_capacity >= 1 &&
          observation.vertex_float_constant_bitmap &&
          observation.vertex_float_constant_words &&
          observation.vertex_float_constant_count <= 256) {
        const auto& fetch = observation.vertex_fetches[0];
        const Snr02TrackRange vertex{fetch.guest_base, fetch.length};
        const Snr02TrackRange index{observation.index_buffer_guest_base,
                                    observation.index_buffer_length};
        if (fetch.fetch_constant == 95 && fetch.stride_words >= 4 &&
            fetch.stride_words <= 9 &&
            Snr02OwnTrackRange(payload.vertices, vertex,
                               fetch.cpu_snapshot_bytes,
                               fetch.cpu_snapshot_status,
                               fetch.cpu_snapshot_hash, payload) &&
            Snr02OwnTrackRange(payload.indices, index,
                               observation.index_cpu_snapshot_bytes,
                               observation.index_cpu_snapshot_status,
                               observation.index_cpu_snapshot_hash, payload)) {
          Snr02TrackDraw draw{};
          draw.sequence = observation.draw_sequence;
          draw.vertex_shader = observation.vertex_shader_hash;
          draw.pixel_shader = observation.pixel_shader_hash;
          draw.vertex_specialization = observation.vertex_specialization_mask;
          draw.packet = observation.draw_packet_physical_address;
          draw.command_buffer = observation.command_buffer_physical_address;
          draw.index_count = observation.index_count;
          draw.stride_words = fetch.stride_words;
          draw.host_index_format = observation.host_index_format;
          draw.host_primitive_type = observation.host_primitive_type;
          draw.host_primitive_reset = observation.host_primitive_reset_enabled;
          draw.index_endianness = observation.index_buffer_guest_endianness;
          draw.vertex = vertex;
          draw.index = index;
          std::copy_n(observation.vertex_float_constant_bitmap, 4,
                      draw.vertex_bitmap.begin());
          bitmap = draw.vertex_bitmap;
          draw.vertex_packed.reserve(observation.vertex_float_constant_count * 4);
          for (uint32_t reg = 0; reg < 256; ++reg) {
            if (draw.vertex_bitmap[reg / 64] & (uint64_t(1) << (reg % 64))) {
              const auto* words = observation.vertex_float_constant_words + reg * 4;
              draw.vertex_packed.insert(draw.vertex_packed.end(), words, words + 4);
            }
          }
          if (draw.vertex_packed.size() ==
              observation.vertex_float_constant_count * 4) {
            packed_words = uint32_t(draw.vertex_packed.size());
            packed_hash = Snr02HashWords(draw.vertex_packed);
            payload.draws.push_back(std::move(draw));
            captured = true;
          }
        }
      }
      if (!captured) payload.rejected = true;
    }
    REXGPU_INFO("FH1 SNR02 track geometry {{\"frame\":{},\"packet\":{},"
                "\"command_buffer\":{},\"sequence\":{},"
                "\"index_base\":{},\"index_length\":{},"
                "\"index_status\":{},\"index_hash\":{},"
                "\"specialization\":{},\"host_index_format\":{},"
                "\"host_primitive\":{},\"host_restart\":{},"
                "\"index_endianness\":{},"
                "\"bitmap\":[{},{},{},{}],"
                "\"captured\":{},\"packed_words\":{},"
                "\"packed_hash\":{}}}",
                observation.frame_sequence,
                observation.draw_packet_physical_address,
                observation.command_buffer_physical_address,
                observation.draw_sequence,
                observation.index_buffer_guest_base,
                observation.index_buffer_length,
                observation.index_cpu_snapshot_status,
                observation.index_cpu_snapshot_hash,
                observation.vertex_specialization_mask,
                observation.host_index_format,
                observation.host_primitive_type,
                observation.host_primitive_reset_enabled,
                observation.index_buffer_guest_endianness,
                bitmap[0], bitmap[1], bitmap[2], bitmap[3], captured,
                packed_words, packed_hash);
  }
  static const bool corpus_enabled =
      rex::cvar::GetFlagByName("pinyon_shift_fh1_gpu_corpus") == "true";
  if (corpus_enabled) {
    RecordFh1GpuExecution(observation);
  }
  const uint64_t rebuild = snr02_rebuild_capture.load(std::memory_order_acquire);
  if (rebuild && observation.frame_sequence == (rebuild >> 32) + 1 &&
      observation.command_buffer_physical_address == uint32_t(rebuild)) {
    const uint32_t draw = snr02_rebuild_draw_count.fetch_add(
                              1, std::memory_order_relaxed) + 1;
    if (draw <= 512) {
      REXGPU_INFO("FH1 SNR02 rebuild prepared draw {{\"frame\":{},"
                  "\"draw\":{},\"command_target\":{},"
                  "\"dispatch_packet\":{},\"draw_packet\":{},"
                  "\"index_count\":{},\"index_base\":{},"
                  "\"index_length\":{},\"vertex_shader\":{},"
                  "\"pixel_shader\":{},\"vertex_fetch_count\":{},"
                  "\"texture_fetch_count\":{},\"surface_info\":{},"
                  "\"color_info\":[{},{},{},{}],\"depth_info\":{},"
                  "\"depth_control\":{},\"color_mask\":{}}}",
                  observation.frame_sequence, draw, uint32_t(rebuild),
                  observation.indirect_dispatch_packet_physical_address,
                  observation.draw_packet_physical_address,
                  observation.index_count, observation.index_buffer_guest_base,
                  observation.index_buffer_length, observation.vertex_shader_hash,
                  observation.pixel_shader_hash, observation.vertex_fetch_count,
                  observation.texture_fetch_count, observation.surface_info,
                  observation.color_info[0], observation.color_info[1],
                  observation.color_info[2], observation.color_info[3],
                  observation.depth_info, observation.normalized_depth_control,
                  observation.normalized_color_mask);
      for (uint32_t i = 0; i < observation.vertex_fetch_count &&
                           i < observation.vertex_fetch_capacity && i < 32; ++i) {
        const auto& fetch = observation.vertex_fetches[i];
        REXGPU_INFO("FH1 SNR02 rebuild vertex fetch {{\"draw\":{},"
                    "\"slot\":{},\"constant\":{},\"stride_words\":{},"
                    "\"guest_base\":{},\"length\":{},\"type\":{},"
                    "\"source_packet\":{}}}",
                    draw, i, fetch.fetch_constant, fetch.stride_words,
                    fetch.guest_base, fetch.length, fetch.type,
                    fetch.source_packet_physical_0);
      }
      for (uint32_t i = 0; i < observation.texture_fetch_count && i < 32; ++i) {
        const auto& fetch = observation.texture_fetches[i];
        REXGPU_INFO("FH1 SNR02 rebuild texture fetch {{\"draw\":{},"
                    "\"constant\":{},\"base\":{},\"mip\":{},"
                    "\"format\":{},\"dimension\":{}}}",
                    draw, fetch.fetch_constant, fetch.base_address,
                    fetch.mip_address, fetch.format, fetch.dimension);
      }
    } else if (draw == 513) {
      REXGPU_INFO("FH1 SNR02 rebuild draw limit reached");
    }
  }
  static const int32_t target = REXCVAR_GET(pinyon_shift_snr01_trace_source_frame);
  if (target <= 0 || observation.frame_sequence + 1 < uint64_t(target) ||
      observation.frame_sequence > uint64_t(target) + 1) {
    return;
  }
  static thread_local uint64_t logged_frame = 0;
  static thread_local uint64_t logged_draws = 0;
  if (logged_frame != observation.frame_sequence) {
    logged_frame = observation.frame_sequence;
    logged_draws = 0;
  }
  if (++logged_draws > kSnr01PacketLimit) {
    return;
  }
  uint32_t packet_bytes = 0;
  uint64_t packet_hash = 0;
  const uint32_t buffer_end_offset = observation.command_buffer_end_offset
                                         ? observation.command_buffer_end_offset
                                         : observation.command_buffer_bytes;
  if (const auto* memory = snr01_memory.load(std::memory_order_acquire);
      memory && buffer_end_offset <= observation.command_buffer_bytes &&
      observation.draw_packet_physical_address >=
          observation.command_buffer_physical_address) {
    const uint32_t packet_offset = observation.draw_packet_physical_address -
                                   observation.command_buffer_physical_address;
    if (packet_offset < buffer_end_offset) {
      packet_bytes = std::min<uint32_t>(buffer_end_offset - packet_offset, 32);
      packet_hash = 14695981039346656037ull;
      const uint8_t* packet = memory->TranslatePhysical(
          observation.draw_packet_physical_address);
      for (uint32_t i = 0; i < packet_bytes; ++i) {
        packet_hash = (packet_hash ^ packet[i]) * 1099511628211ull;
      }
    }
  }
  REXGPU_INFO(
      "FH1 SNR01 prepared draw {{\"frame\":{},\"ordinal\":{},\"sequence\":{},"
      "\"indirect_execution\":{},\"indirect_parent\":{},"
      "\"dispatch_packet_physical\":{},"
      "\"packet_physical\":{},\"packet_bytes\":{},"
      "\"packet_hash\":{},\"command_buffer\":{},"
      "\"command_bytes\":{},\"draw_end_offset\":{},\"vertex_shader\":{},"
      "\"pixel_shader\":{},\"index_count\":{},"
      "\"index_buffer_type\":{},\"index_buffer_guest_base\":{},"
      "\"index_buffer_length\":{},\"guest_primitive_type\":{},"
      "\"vertex_fetch_count\":{},\"texture_fetch_count\":{},"
      "\"render_target_bits\":{},\"attachment_state\":{},"
      "\"surface_info\":{},\"color_info\":[{},{},{},{}],"
      "\"depth_info\":{},\"depth_control\":{},"
      "\"color_mask\":{},\"draw_flags\":{}}}",
      observation.frame_sequence, logged_draws, observation.draw_sequence,
      observation.indirect_buffer_execution_id,
      observation.indirect_buffer_parent_execution_id,
      observation.indirect_dispatch_packet_physical_address,
      observation.draw_packet_physical_address,
      packet_bytes, packet_hash,
      observation.command_buffer_physical_address,
      observation.command_buffer_bytes,
      observation.command_buffer_end_offset, observation.vertex_shader_hash,
      observation.pixel_shader_hash, observation.index_count,
      observation.index_buffer_type, observation.index_buffer_guest_base,
      observation.index_buffer_length, observation.guest_primitive_type,
      observation.vertex_fetch_count, observation.texture_fetch_count,
      observation.bound_render_target_bits,
      observation.fh1_execution_key.attachment_state,
      observation.surface_info, observation.color_info[0],
      observation.color_info[1], observation.color_info[2],
      observation.color_info[3], observation.depth_info,
      observation.normalized_depth_control, observation.normalized_color_mask,
      observation.flags);
  if (REXCVAR_GET(pinyon_shift_snr01_watch_packet_pages) &&
      observation.frame_sequence + 1 == uint64_t(target) && packet_bytes) {
    Snr01ArmPacketPage(observation.draw_packet_physical_address);
  }
  if (observation.frame_sequence == uint64_t(target) ||
      observation.frame_sequence == uint64_t(target) + 1) {
    for (uint32_t i = 0; i < observation.texture_fetch_count; ++i) {
      const auto& fetch = observation.texture_fetches[i];
      REXGPU_INFO(
          "FH1 SNR01 prepared texture fetch {{\"frame\":{},"
          "\"draw\":{},\"packet_physical\":{},"
          "\"fetch_constant\":{},\"type\":{},"
          "\"base_address\":{},\"mip_address\":{},"
          "\"format\":{},\"dimension\":{},"
          "\"width\":{},\"height\":{},\"stack_depth\":{}}}",
          observation.frame_sequence, logged_draws,
          observation.draw_packet_physical_address, fetch.fetch_constant,
          fetch.type, fetch.base_address, fetch.mip_address, fetch.format,
          fetch.dimension, fetch.width, fetch.height, fetch.stack_depth);
    }
  }
  if (observation.frame_sequence == uint64_t(target) + 1) {
    for (uint32_t i = 0;
         i < observation.vertex_fetch_count &&
         i < observation.vertex_fetch_capacity; ++i) {
      const auto& fetch = observation.vertex_fetches[i];
      REXGPU_INFO(
          "FH1 SNR01 prepared vertex fetch {{\"frame\":{},"
          "\"draw\":{},\"packet_physical\":{},\"slot\":{},"
          "\"fetch_constant\":{},\"stride_words\":{},"
          "\"guest_base\":{},\"length\":{},\"type\":{},"
          "\"cpu_snapshot_status\":{},\"cpu_snapshot_hash\":{},"
          "\"source_packet_0\":{},\"source_packet_1\":{},"
          "\"source_execution_0\":{},\"source_execution_1\":{}}}",
          observation.frame_sequence, logged_draws,
          observation.draw_packet_physical_address, i,
          fetch.fetch_constant, fetch.stride_words, fetch.guest_base,
          fetch.length, fetch.type, fetch.cpu_snapshot_status,
          fetch.cpu_snapshot_hash, fetch.source_packet_physical_0,
          fetch.source_packet_physical_1, fetch.source_execution_0,
          fetch.source_execution_1);
    }
  }
}

void ObserveIndirectBuffer(
    const rex::system::GraphicsIndirectBufferObservation& observation) {
  const uint64_t rebuild = snr02_rebuild_capture.load(std::memory_order_acquire);
  if (rebuild && observation.frame_sequence == (rebuild >> 32) + 1 &&
      observation.command_buffer_physical_address == uint32_t(rebuild)) {
    REXGPU_INFO("FH1 SNR02 rebuild indirect {{\"frame\":{},"
                "\"command_target\":{},\"execution\":{},"
                "\"parent\":{},\"dispatch_packet\":{},"
                "\"command_bytes\":{}}}",
                observation.frame_sequence, uint32_t(rebuild),
                observation.execution_id, observation.parent_execution_id,
                observation.dispatch_packet_physical_address,
                observation.command_buffer_bytes);
  }
  static const int32_t target = REXCVAR_GET(pinyon_shift_snr01_trace_source_frame);
  if (target <= 0 || observation.frame_sequence + 1 < uint64_t(target) ||
      observation.frame_sequence > uint64_t(target) + 1) {
    return;
  }
  static thread_local uint64_t logged_frame = 0;
  static thread_local uint64_t logged_buffers = 0;
  if (logged_frame != observation.frame_sequence) {
    logged_frame = observation.frame_sequence;
    logged_buffers = 0;
  }
  if (++logged_buffers > kSnr01PacketLimit) {
    return;
  }
  REXGPU_INFO(
      "FH1 SNR01 indirect buffer {{\"frame\":{},\"ordinal\":{},"
      "\"execution\":{},\"parent\":{},\"dispatch_packet_physical\":{},"
      "\"command_buffer\":{},\"command_bytes\":{}}}",
      observation.frame_sequence, logged_buffers, observation.execution_id,
      observation.parent_execution_id,
      observation.dispatch_packet_physical_address,
      observation.command_buffer_physical_address,
      observation.command_buffer_bytes);
}

void ObserveCopy(const rex::system::GraphicsCopyObservation& observation) {
  RecordFh1GpuCopy(observation);
  static const int32_t target = REXCVAR_GET(pinyon_shift_snr01_trace_source_frame);
  if (target <= 0 || observation.frame_sequence + 1 < uint64_t(target) ||
      observation.frame_sequence > uint64_t(target) + 1) {
    return;
  }
  static thread_local uint64_t logged_frame = 0;
  static thread_local uint64_t logged_copies = 0;
  if (logged_frame != observation.frame_sequence) {
    logged_frame = observation.frame_sequence;
    logged_copies = 0;
  }
  if (++logged_copies > kSnr01PacketLimit) {
    return;
  }
  REXGPU_INFO(
      "FH1 SNR01 copy {{\"frame\":{},\"ordinal\":{},"
      "\"copy_sequence\":{},\"attachment_state\":{},"
      "\"surface_info\":{},\"color_info\":[{},{},{},{}],"
      "\"depth_info\":{},\"copy_control\":{},"
      "\"source_base_tiles\":{},\"resolve_base_tiles\":{},"
      "\"resolve_width\":{},\"resolve_height\":{},"
      "\"dest_base\":{},\"dest_pitch\":{},"
      "\"written_address\":{},\"written_length\":{},"
      "\"succeeded\":{}}}",
      observation.frame_sequence, logged_copies, observation.copy_sequence,
      observation.fh1_execution_key.attachment_state,
      observation.surface_info, observation.color_info[0],
      observation.color_info[1], observation.color_info[2],
      observation.color_info[3], observation.depth_info,
      observation.rb_copy_control, observation.source_target_base_tiles,
      observation.resolve_source_base_tiles, observation.resolve_guest_width,
      observation.resolve_guest_height, observation.rb_copy_dest_base,
      observation.rb_copy_dest_pitch, observation.written_address,
      observation.written_length, observation.succeeded);
}

}  // namespace

void InstallGraphicsCensus(rex::system::IGraphicsSystem* graphics_system,
                           rex::memory::Memory* memory) {
  if (!graphics_system) {
    return;
  }
  snr01_memory.store(memory, std::memory_order_release);
  if (memory && REXCVAR_GET(pinyon_shift_snr01_watch_packet_pages) &&
      REXCVAR_GET(pinyon_shift_snr01_trace_source_frame) > 0) {
    snr01_watch_events.store(0, std::memory_order_relaxed);
    snr01_watch_access_handle = memory->RegisterPhysicalMemoryAccessCallback(
        Snr01WatchAccess, nullptr);
    snr01_watch_invalidation_handle =
        memory->RegisterPhysicalMemoryInvalidationCallback(
            Snr01WatchInvalidation, nullptr);
    REXGPU_INFO("FH1 SNR01 packet page watch active page_limit={} event_limit={}",
                kSnr01WatchPageLimit, kSnr01WatchEventLimit);
  }
  if (REXCVAR_GET(pinyon_shift_snr01_trace_resident_packet_writers)) {
    REXGPU_INFO("FH1 SNR01 resident packet survey active "
                "range=[0x14000000,0x16000000)+[0x17000000,0x18000000) "
                "per_thread_limit={}",
                kSnr01PacketLimit);
  }
  const bool enabled = ResetFh1GpuCorpus();
  graphics_system->SetPreparedDrawObserver(
      enabled || REXCVAR_GET(pinyon_shift_snr01_trace_source_frame) > 0 ||
              REXCVAR_GET(pinyon_shift_snr02_trace_first_rebuild_after_frame) > 0 ||
              Snr03ProbeEnabled()
          ? &ObservePreparedDraw
          : nullptr);
  graphics_system->SetPreparedDrawSnapshotSelector(
      Snr02TrackTargetFrame() > 0 ? &Snr02SelectTrackSnapshot : nullptr);
  graphics_system->SetFinalDrawStateObserver(
      Snr03ProbeEnabled() || Snr02ItemProbeEnabled() ||
              Snr02TrackTargetFrame() > 0
          ? &ObserveSnr03FinalDrawState : nullptr);
  graphics_system->SetIndirectBufferObserver(
      REXCVAR_GET(pinyon_shift_snr01_trace_source_frame) > 0 ||
              REXCVAR_GET(pinyon_shift_snr02_trace_first_rebuild_after_frame) > 0
          ? &ObserveIndirectBuffer
          : nullptr);
  graphics_system->SetCopyObserver(
      enabled || REXCVAR_GET(pinyon_shift_snr01_trace_source_frame) > 0
          ? &ObserveCopy
          : nullptr);
}

void UninstallGraphicsCensus(rex::system::IGraphicsSystem* graphics_system) {
  if (graphics_system) {
    graphics_system->SetPreparedDrawObserver(nullptr);
    graphics_system->SetPreparedDrawSnapshotSelector(nullptr);
    graphics_system->SetFinalDrawStateObserver(nullptr);
    graphics_system->SetIndirectBufferObserver(nullptr);
    graphics_system->SetCopyObserver(nullptr);
  }
  auto* memory = snr01_memory.exchange(nullptr, std::memory_order_acq_rel);
  if (memory && snr01_watch_access_handle) {
    memory->UnregisterPhysicalMemoryAccessCallback(snr01_watch_access_handle);
    memory->UnregisterPhysicalMemoryInvalidationCallback(
        snr01_watch_invalidation_handle);
    snr01_watch_access_handle = nullptr;
    snr01_watch_invalidation_handle = nullptr;
    std::lock_guard lock(snr01_watch_mutex);
    snr01_watch_pages.clear();
  }
  FlushFh1GpuCorpus();
  {
    std::lock_guard lock(snr03_scene_mutex);
    snr03_scenes.clear();
    snr03_payloads.clear();
  }
  {
    std::lock_guard lock(snr02_item_scene_mutex);
    snr02_item_scenes.clear();
    snr02_item_payloads.clear();
  }
  {
    std::lock_guard lock(snr02_track_targets_mutex);
    snr02_track_targets.clear();
    snr02_track_targets_overflow = false;
    snr02_track_title_ready = false;
    snr02_track_camera80 = {};
    snr02_track_camera144 = {};
    snr02_track_payload = {};
  }
}

bool Snr03ProbeEnabled() { return Snr03TargetFrame() > 0; }
bool Snr02ItemProbeEnabled() { return Snr02ItemTargetFrame() > 0; }

void ObserveSnr02TrackOutputFrame(uint64_t output_frame) {
  if (Snr02TrackTargetFrame() <= 0 ||
      output_frame != uint64_t(Snr02TrackTargetFrame()) + 1) return;
  Snr02TrackPayload payload;
  std::set<uint32_t> targets;
  std::array<uint32_t, 16> camera80{}, camera144{};
  bool ready = false;
  {
    std::lock_guard lock(snr02_track_targets_mutex);
    ready = snr02_track_title_ready && !snr02_track_targets_overflow;
    targets = snr02_track_targets;
    camera80 = snr02_track_camera80;
    camera144 = snr02_track_camera144;
    payload = std::move(snr02_track_payload);
  }
  std::set<uint32_t> seen_targets;
  std::set<uint64_t> sequences;
  for (const auto& draw : payload.draws) {
    seen_targets.insert(draw.command_buffer);
    if (!sequences.insert(draw.sequence).second) payload.rejected = true;
    if (!draw.final_seen) payload.rejected = true;
  }
  if (!ready || payload.rejected || payload.draws.empty() ||
      seen_targets != targets) {
    REXGPU_INFO("FH1 SNR02 track owned scene rejected output_frame={} "
                "ready={} rejected={} targets={} seen={} draws={} bytes={}",
                output_frame, ready, payload.rejected, targets.size(),
                seen_targets.size(), payload.draws.size(), payload.bytes);
    return;
  }
  std::ranges::sort(payload.draws, {}, &Snr02TrackDraw::sequence);
  std::vector<char> encoded;
  auto write = [&](const auto& value) {
    const auto* bytes = reinterpret_cast<const char*>(&value);
    encoded.insert(encoded.end(), bytes, bytes + sizeof(value));
  };
  constexpr std::array<char, 8> magic{'S', 'N', 'R', '0', '2', 'T', '3', '\0'};
  write(magic);
  write(output_frame - 1);
  write(uint32_t(targets.size()));
  write(uint32_t(payload.draws.size()));
  write(uint32_t(payload.vertices.size()));
  write(uint32_t(payload.indices.size()));
  write(camera80);
  write(camera144);
  for (uint32_t target : targets) write(target);
  const auto write_ranges = [&](const auto& ranges) {
    for (const auto& [key, bytes] : ranges) {
      write(key.first);
      write(key.second);
      encoded.insert(encoded.end(), bytes.begin(), bytes.end());
    }
  };
  write_ranges(payload.vertices);
  write_ranges(payload.indices);
  for (const auto& draw : payload.draws) {
    write(draw.sequence);
    write(draw.vertex_shader);
    write(draw.pixel_shader);
    write(draw.packet);
    write(draw.command_buffer);
    write(draw.index_count);
    write(draw.stride_words);
    write(draw.vertex.first);
    write(draw.vertex.second);
    write(draw.index.first);
    write(draw.index.second);
    write(draw.vertex_specialization);
    write(draw.dynamic_state);
    write(draw.host_index_format);
    write(draw.host_primitive_type);
    write(draw.host_primitive_reset);
    write(draw.index_endianness);
    write(draw.vertex_bitmap);
    write(uint32_t(draw.vertex_packed.size()));
    for (uint32_t word : draw.vertex_packed) write(word);
    write(draw.system_constants);
    write(draw.fetch47);
  }
  const auto directory = fh1_render_test::OutputDirectory();
  const bool written = !directory.empty() &&
      WriteSceneFixture(std::span<const char>(encoded), output_frame - 1,
                        directory, "snr02-track-");
  REXGPU_INFO("FH1 SNR02 track owned scene consumed output_frame={} "
              "source_frame={} targets={} draws={} vertex_ranges={} "
              "index_ranges={} owned_bytes={} fixture_bytes={} written={}",
              output_frame, output_frame - 1, targets.size(), payload.draws.size(),
              payload.vertices.size(), payload.indices.size(), payload.bytes,
              encoded.size(), written);
}

void ObserveSnr02ItemOutputFrame(uint64_t output_frame, void* device) {
  if (!Snr02ItemProbeEnabled() ||
      output_frame != uint64_t(Snr02ItemTargetFrame()) + 1) return;
  std::shared_ptr<const Snr02ItemScene> scene;
  Snr02ItemPayloadState payload;
  {
    std::lock_guard lock(snr02_item_scene_mutex);
    const auto source = output_frame - 1;
    if (auto it = snr02_item_scenes.find(source); it != snr02_item_scenes.end()) {
      scene = std::move(it->second);
      snr02_item_scenes.erase(it);
    }
    if (auto it = snr02_item_payloads.find(source);
        it != snr02_item_payloads.end()) {
      payload = std::move(it->second);
      snr02_item_payloads.erase(it);
    }
  }
  if (!scene || payload.rejected ||
      payload.by_packet.size() != scene->items.size()) {
    REXGPU_INFO("FH1 SNR02 item owned scene rejected output_frame={} "
                "items={} payloads={} unstable={}", output_frame,
                scene ? scene->items.size() : 0, payload.by_packet.size(),
                payload.rejected);
    return;
  }
  std::vector<char> encoded;
  auto write = [&](const auto& value) {
    const auto* bytes = reinterpret_cast<const char*>(&value);
    encoded.insert(encoded.end(), bytes, bytes + sizeof(value));
  };
  constexpr std::array<char, 8> magic{'S', 'N', 'R', '0', '2', 'I', '3', '\0'};
  write(magic);
  write(scene->source_frame);
  write(uint32_t(scene->items.size()));
  write(scene->camera80);
  write(scene->camera144);
  uint32_t draws = 0;
  for (const auto& item : scene->items) {
    const auto it = payload.by_packet.find(item.packet);
    if (it == payload.by_packet.end()) return;
    const auto& geometry = it->second;
    write(item.call);
    write(item.packet);
    write(item.kind);
    write(item.descriptor);
    write(item.runtime);
    write(geometry.base);
    write(geometry.length);
    write(uint32_t(geometry.draws.size()));
    encoded.insert(encoded.end(), geometry.vertex_bytes.begin(),
                   geometry.vertex_bytes.end());
    for (const auto& [sequence, state] : geometry.draws) {
      if (!state.final_seen) {
        REXGPU_INFO("FH1 SNR02 item owned scene rejected missing_final packet={} sequence={}",
                    item.packet, sequence);
        return;
      }
      write(sequence);
      write(state.vertex_shader);
      write(state.pixel_shader);
      write(state.dynamic_state);
      write(state.index_count);
      write(state.texture_count);
      write(state.textures);
      write(state.vertex_bitmap);
      write(state.vertex_constant_count);
      write(state.vertex_constants);
      write(state.system_constants);
      write(state.fetch47);
    }
    draws += uint32_t(geometry.draws.size());
  }
  const auto directory = fh1_render_test::OutputDirectory();
  const bool written = !directory.empty() &&
      WriteSceneFixture(std::span<const char>(encoded), scene->source_frame,
                        directory, "snr02-items-");
  REXGPU_INFO("FH1 SNR02 item owned scene consumed output_frame={} "
              "source_frame={} calls={} draws={} vertex_bytes={} state_bytes={} "
              "fixture_bytes={} written={}", output_frame, scene->source_frame,
              scene->items.size(), draws, payload.bytes, payload.draw_bytes,
              encoded.size(), written);
#if defined(_WIN32)
  if (written && device) {
    if (const auto shaders = diagnostics::EnvironmentPath(
            "PINYON_SHIFT_SNR04_PROCEDURAL_VS_DIR")) {
      try {
        const auto covered = RunSnr04ProceduralDiagnostic(
            directory / ("snr02-items-" + std::to_string(scene->source_frame) + ".bin"),
            *shaders,
            directory / ("snr04-procedural-" + std::to_string(scene->source_frame)),
            static_cast<ID3D12Device*>(device));
        REXGPU_INFO("FH1 SNR04 procedural private diagnostic source_frame={} "
                    "calls={} draws={} covered_pixels={}", scene->source_frame,
                    scene->items.size(), draws, covered);
      } catch (const std::exception& error) {
        REXGPU_INFO("FH1 SNR04 procedural private diagnostic rejected "
                    "source_frame={} reason={}", scene->source_frame, error.what());
      }
    }
  }
#endif
}

void ObserveSnr03OutputFrame(uint64_t output_frame, void* device) {
  if (!Snr03ProbeEnabled() || output_frame != uint64_t(Snr03TargetFrame()) + 1) {
    return;
  }
  std::shared_ptr<const Snr03SceneSnapshot> scene;
  Snr03PayloadState payload;
  {
    std::lock_guard lock(snr03_scene_mutex);
    const auto it = snr03_scenes.find(output_frame - 1);
    if (it != snr03_scenes.end()) {
      scene = std::move(it->second);
      snr03_scenes.erase(it);
    }
    const auto payload_it = snr03_payloads.find(output_frame - 1);
    if (payload_it != snr03_payloads.end()) {
      payload = std::move(payload_it->second);
      snr03_payloads.erase(payload_it);
    }
  }
  if (!scene) {
    REXGPU_INFO("FH1 SNR03 scene missing output_frame={} source_frame={}",
                output_frame, output_frame - 1);
    return;
  }
  REXGPU_INFO("FH1 SNR03 scene consumed output_frame={} source_frame={} "
              "view={} camera={} items={} fingerprint={}",
              output_frame, scene->source_frame, scene->view, scene->camera,
              scene->items.size(), Snr03Fingerprint(*scene));
  if (payload.rejected || payload.by_packet.size() != scene->items.size()) {
    REXGPU_INFO("FH1 SNR03 geometry rejected output_frame={} items={} "
                "payloads={} bytes={} unstable={}", output_frame,
                scene->items.size(), payload.by_packet.size(), payload.bytes,
                payload.rejected);
    return;
  }
  Snr03OwnedScene owned_builder{scene, {}};
  owned_builder.items.reserve(scene->items.size());
  uint64_t fingerprint = Snr03Fingerprint(*scene);
  size_t final_variants = 0;
  for (const auto& item : scene->items) {
    auto it = payload.by_packet.find(item.packet_physical);
    if (it == payload.by_packet.end()) {
      REXGPU_INFO("FH1 SNR03 geometry rejected output_frame={} "
                  "missing_packet={}", output_frame, item.packet_physical);
      return;
    }
    if (it->second.final_states.empty()) {
      REXGPU_INFO("FH1 SNR03 geometry rejected output_frame={} "
                  "missing_final_state={}", output_frame, item.packet_physical);
      return;
    }
    const uint64_t hash = Snr03HashBytes(it->second.vertex_bytes);
    fingerprint = (fingerprint ^ hash) * 1099511628211ull;
    for (const auto& constant : it->second.vertex_constants) {
      for (const uint32_t word : constant) {
        fingerprint = (fingerprint ^ word) * 1099511628211ull;
      }
    }
    for (size_t i = 0; i < it->second.pixel_registers.size(); ++i) {
      fingerprint = (fingerprint ^ it->second.pixel_registers[i]) *
                    1099511628211ull;
      for (const uint32_t word : it->second.pixel_constants[i]) {
        fingerprint = (fingerprint ^ word) * 1099511628211ull;
      }
    }
    fingerprint = (fingerprint ^ it->second.guest_vertex_count) * 1099511628211ull;
    final_variants += it->second.final_states.size();
    for (const auto& [dynamic, state] : it->second.final_states) {
      fingerprint = (fingerprint ^ dynamic) * 1099511628211ull;
      for (const uint32_t word : state.system_constants) {
        fingerprint = (fingerprint ^ word) * 1099511628211ull;
      }
      for (const uint32_t word : state.fetch_47) {
        fingerprint = (fingerprint ^ word) * 1099511628211ull;
      }
    }
    owned_builder.items.push_back({item, std::move(it->second.vertex_bytes),
                                   it->second.vertex_constants,
                                   it->second.pixel_registers,
                                   it->second.pixel_constants,
                                   it->second.guest_vertex_count,
                                   std::move(it->second.final_states)});
  }
  std::shared_ptr<const Snr03OwnedScene> owned =
      std::make_shared<Snr03OwnedScene>(std::move(owned_builder));
  REXGPU_INFO("FH1 SNR03 geometry consumed output_frame={} source_frame={} "
              "items={} bytes={} vertex_constants=24 pixel_constants=3 "
              "system_words=64 "
              "fetch_words=4 final_variants={} fingerprint={}", output_frame,
              owned->title->source_frame, owned->items.size(), payload.bytes,
              final_variants, fingerprint);
  const auto directory = fh1_render_test::OutputDirectory();
  if (!directory.empty()) {
    const auto encoded = EncodeSnr03Fixture(*owned);
    const auto begin = std::chrono::steady_clock::now();
    const bool written = WriteSceneFixture(std::span<const char>(encoded),
                                           owned->title->source_frame, directory,
                                           "snr03-scene-");
    const auto elapsed = std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::steady_clock::now() - begin).count();
    REXGPU_INFO("FH1 SNR03 fixture output_frame={} written={} write_us={}",
                output_frame, written, elapsed);
#if defined(_WIN32)
    if (device) {
      const auto shader = diagnostics::EnvironmentPath("PINYON_SHIFT_SNR04_VS");
      if (shader) {
        const auto private_output = directory /
            ("snr04-private-" + std::to_string(owned->title->source_frame));
        const auto diagnostic_begin = std::chrono::steady_clock::now();
        try {
          const auto covered = RunSnr04OwnedSceneDiagnostic(
              std::span<const char>(encoded), *shader, private_output,
              static_cast<ID3D12Device*>(device),
              GetEnvironmentVariableA("PINYON_SHIFT_SNR04_MSAA4", nullptr, 0)
                  ? 4 : 1);
          const auto diagnostic_us = std::chrono::duration_cast<
              std::chrono::microseconds>(std::chrono::steady_clock::now() -
                                          diagnostic_begin).count();
          REXGPU_INFO("FH1 SNR04 private diagnostic output_frame={} "
                      "source_frame={} covered_pixels={} elapsed_us={}",
                      output_frame, owned->title->source_frame, covered,
                      diagnostic_us);
        } catch (const std::exception& error) {
          REXGPU_INFO("FH1 SNR04 private diagnostic rejected output_frame={} "
                      "reason={}", output_frame, error.what());
        }
      }
    }
#endif
  }
}

}  // namespace pinyon_shift::native_renderer

// FH1's sole VdSwap call is the source-frame boundary used by the real-frame
// presentation and performance gates. It intentionally changes no guest state.
void PinyonShiftObserveGraphicsFrame() {
  if (Snr01TraceCurrentFrame()) {
    REXGPU_INFO(
        "FH1 SNR01 summary {{\"frame\":{},\"indexed_packets\":{},"
        "\"semantic_packets\":{},"
        "\"procedural_calls\":{},\"dispatch_calls\":{},"
        "\"render_state_calls\":{},\"emitter_calls\":{},"
        "\"state_wrapper_calls\":{},\"dispatch_wrapper_calls\":{},"
        "\"track75_calls\":{},\"track79_calls\":{},"
        "\"unfinished_track75_scopes\":{},"
        "\"unmatched_track75_exits\":{},"
        "\"track_pass_calls\":{},"
        "\"track_bucket_entries\":{},"
        "\"unfinished_track_bucket_scopes\":{},"
        "\"unmatched_track_bucket_exits\":{},"
        "\"second_draw_calls\":{},\"unfinished_second_draw_scopes\":{},"
        "\"unmatched_second_draw_exits\":{},"
        "\"second_draw_skips\":{},"
        "\"item_nodes\":{},\"unfinished_item_node_scopes\":{},"
        "\"unmatched_item_node_exits\":{},"
        "\"direct_calls_swap_thread\":{},"
        "\"draw_header_packets_swap_thread\":{},"
        "\"unmatched_direct_exits_swap_thread\":{},"
        "\"unfinished_direct_scopes_swap_thread\":{},"
        "\"unmatched_exits\":{},"
        "\"unmatched_dispatch_exits\":{},"
        "\"unmatched_render_state_exits\":{},"
        "\"unmatched_emitter_exits\":{},"
        "\"unfinished_scopes\":{},\"unfinished_dispatch_scopes\":{},"
        "\"unfinished_render_state_scopes\":{},"
        "\"unfinished_emitter_scopes\":{},"
        "\"packet_limit\":{},\"scope_limit\":{}}}",
        rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
        snr01_packet_count, snr01_semantic_packet_count,
        snr01_procedural_count, snr01_dispatch_count,
        snr01_render_state_count, snr01_emitter_count,
        snr01_state_wrapper_count, snr01_dispatch_wrapper_count,
        snr01_track75_count, snr01_track79_count,
        snr01_track75_scopes.size(), snr01_unmatched_track75_exits,
        snr01_track_pass_count,
        snr01_track_bucket_count, snr01_track_bucket_scopes.size(),
        snr01_unmatched_track_bucket_exits,
        snr01_second_draw_count, snr01_second_draw_scopes.size(),
        snr01_unmatched_second_draw_exits,
        snr01_second_draw_skips,
        snr01_item_node_count, snr01_item_node_scopes.size(),
        snr01_unmatched_item_node_exits,
        snr01_direct_call_count, snr01_direct_packet_count,
        snr01_unmatched_direct_exits, snr01_direct_scopes.size(),
        snr01_unmatched_exits,
        snr01_unmatched_dispatch_exits,
        snr01_unmatched_render_state_exits,
        snr01_unmatched_emitter_exits,
        snr01_procedural_scopes.size(), snr01_dispatch_scopes.size(),
        snr01_render_state_scopes.size(),
        snr01_emitter_scopes.size(),
        kSnr01PacketLimit, kSnr01ProceduralLimit);
  }
  snr01_emitter_scopes.clear();
  snr01_track75_scopes.clear();
  snr01_track_bucket_scopes.clear();
  snr01_second_draw_scopes.clear();
  snr01_scalar_draw_scopes.clear();
  snr01_dynamic_quad_scopes.clear();
  snr01_dynamic_quad_parent_scopes.clear();
  snr01_item_node_scopes.clear();
  snr01_direct_scopes.clear();
  snr01_dispatch_scopes.clear();
  snr01_render_state_scopes.clear();
  snr01_procedural_scopes.clear();
  snr01_packet_count = snr01_semantic_packet_count =
      snr01_procedural_count = snr01_dispatch_count =
      snr01_render_state_count = snr01_unmatched_exits =
      snr01_unmatched_dispatch_exits =
      snr01_unmatched_render_state_exits = snr01_emitter_count =
      snr01_unmatched_emitter_exits = snr01_state_wrapper_count =
      snr01_dispatch_wrapper_count = snr01_track75_count =
      snr01_unmatched_track75_exits =
      snr01_track79_count = snr01_track_pass_count =
      snr01_track_bucket_count = snr01_unmatched_track_bucket_exits =
      snr01_second_draw_count = snr01_unmatched_second_draw_exits =
      snr01_second_draw_skips =
      snr01_item_node_count = snr01_unmatched_item_node_exits =
      snr01_scalar_draw_count =
      snr01_dynamic_quad_entries =
      snr01_dynamic_quad_count =
      snr01_direct_call_count = snr01_direct_packet_count =
      snr01_unmatched_direct_exits = 0;
  if (rex::perf::CriticalPathTraceEnabled() &&
      (title_emitter_calls || title_packet_count)) {
    rex::perf::TraceCriticalPath("title_emitter", int64_t(title_emitter_frame),
                                 int64_t(title_emitter_time_ns),
                                 int64_t(title_emitter_calls));
    rex::perf::TraceCriticalPath("pm4_publish", int64_t(title_emitter_frame),
                                 int64_t(title_packet_count), title_first_packet_ns,
                                 title_last_packet_ns);
  }
  PROFILE_SOURCE_FRAME();
  title_emitter_frame = uint64_t(rex::perf::GetTotalCounter(
      rex::perf::CounterId::kSourceFrameCount));
  title_emitter_calls = title_emitter_time_ns = title_packet_count = 0;
  title_first_packet_ns = title_last_packet_ns = 0;
  rex::perf::TraceCriticalPath("source_frame", int64_t(title_emitter_frame));
}

void PinyonShiftObserveTitleDrawEmitterBegin() {
  if (rex::perf::CriticalPathTraceEnabled()) {
    title_emitters.push_back({uint64_t(rex::perf::GetTotalCounter(
                                  rex::perf::CounterId::kSourceFrameCount)),
                              ClearClock::now()});
  }
}

void PinyonShiftObserveTitleDrawEmitterEnd() {
  if (!rex::perf::CriticalPathTraceEnabled() || title_emitters.empty()) {
    return;
  }
  const auto sample = title_emitters.back();
  title_emitters.pop_back();
  title_emitter_frame = sample.frame;
  ++title_emitter_calls;
  title_emitter_time_ns += uint64_t(
      std::chrono::duration_cast<std::chrono::nanoseconds>(ClearClock::now() -
                                                           sample.begin)
          .count());
}

void PinyonShiftObserveTitleCounterWaitBegin(PPCRegister& r12,
                                            PPCRegister& r3, PPCRegister& r4) {
  if (!SnrM02TraceCurrentFrame() && snr_m02_wait_scopes.empty()) {
    return;
  }
  const uint64_t ordinal = ++snr_m02_wait_count;
  const uint32_t device = r3.u32;
  const uint32_t published_ptr = SnrM02ReadU32(device + 11024);
  snr_m02_wait_scopes.push_back(
      {ordinal, device, r4.u32, r12.u32, SnrM02ReadU32(published_ptr),
       SnrM02ReadU32(device + 11036), 0, 0, 0, 0, 0, false, SnrM02NowNs()});
  if (ordinal == kSnrM02WaitLimit + 1) {
    REXGPU_INFO("FH1 SNRM02 wait trace limit reached on this title thread");
  }
}

void PinyonShiftObserveTitleCounterWaitSnapshot(PPCRegister& r1) {
  if (snr_m02_wait_scopes.empty()) {
    return;
  }
  auto& scope = snr_m02_wait_scopes.back();
  scope.entered_loop = true;
  scope.snapshot_published = SnrM02ReadU32(r1.u32 + 88);
  scope.snapshot_counter = SnrM02ReadU32(r1.u32 + 92);
  scope.snapshot_timebase = SnrM02ReadU32(r1.u32 + 100);
}

void PinyonShiftObserveTitleCounterRecovery(PPCRegister& r30) {
  if (!snr_m02_wait_scopes.empty()) {
    ++snr_m02_wait_scopes.back().recoveries;
    snr_m02_wait_scopes.back().recovery_counter = r30.u32;
  }
}

void PinyonShiftObserveTitleCounterWaitEnd() {
  if (snr_m02_wait_scopes.empty()) {
    return;
  }
  const auto scope = snr_m02_wait_scopes.back();
  snr_m02_wait_scopes.pop_back();
  if (scope.ordinal > kSnrM02WaitLimit) {
    return;
  }
  const uint32_t published_ptr = SnrM02ReadU32(scope.device + 11024);
  const int64_t end_ns = SnrM02NowNs();
  REXGPU_INFO(
      "FH1 SNRM02 wait {{\"frame\":{},\"ordinal\":{},"
      "\"caller_lr\":{},\"device\":{},\"requested\":{},"
      "\"published_ptr\":{},\"published_physical\":{},"
      "\"published_before\":{},"
      "\"published_after\":{},\"produced_before\":{},"
      "\"produced_after\":{},\"entered_loop\":{},"
      "\"snapshot_published\":{},\"snapshot_counter\":{},"
      "\"snapshot_timebase\":{},\"recovery_counter\":{},"
      "\"recoveries\":{},"
      "\"begin_ns\":{},\"end_ns\":{}}}",
      rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
      scope.ordinal, scope.caller, scope.device, scope.requested,
      published_ptr, SnrM02Physical(published_ptr), scope.published_before,
      SnrM02ReadU32(published_ptr),
      scope.produced_before, SnrM02ReadU32(scope.device + 11036),
      scope.entered_loop, scope.snapshot_published, scope.snapshot_counter,
      scope.snapshot_timebase, scope.recovery_counter, scope.recoveries,
      scope.begin_ns, end_ns);
}

void PinyonShiftObserveTitleCounterPublish(PPCRegister& r11,
                                           PPCRegister& r6) {
  if (!SnrM02TraceCurrentFrame()) {
    return;
  }
  const uint64_t ordinal = ++snr_m02_writer_count;
  if (ordinal > kSnrM02WriterLimit) {
    if (ordinal == kSnrM02WriterLimit + 1) {
      REXGPU_INFO("FH1 SNRM02 writer trace limit reached on this title thread");
    }
    return;
  }
  const uint32_t device = r11.u32;
  const uint32_t published_ptr = SnrM02ReadU32(device + 11024);
  const uint32_t flag = SnrM02ReadU32(device + 11068) >> 16 & 0xFF;
  const uint32_t disable_word = SnrM02ReadU32(device + 21940);
  REXGPU_INFO(
      "FH1 SNRM02 writer {{\"frame\":{},\"ordinal\":{},"
      "\"device\":{},\"published_ptr\":{},\"published\":{},"
      "\"produced_before\":{},\"disable_word\":{},"
      "\"publish_flag\":{},\"expected_title_store\":{},"
      "\"time_ns\":{}}}",
      rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
      ordinal, device, published_ptr, SnrM02ReadU32(published_ptr), r6.u32,
      disable_word, flag, disable_word == 0 && (flag & 2), SnrM02NowNs());
}

void PinyonShiftObserveTitleDrawPacketPublish(PPCRegister& r3, PPCRegister& r11,
                                             PPCRegister& r31) {
  if (Snr01TraceCurrentFrame()) {
    const uint64_t ordinal = ++snr01_packet_count;
    if (ordinal <= kSnr01PacketLimit) {
      const uint32_t guest_address = r3.u32 + 4;
      REXGPU_INFO(
          "FH1 SNR01 indexed packet {{\"frame\":{},\"ordinal\":{},"
          "\"header_guest\":{},\"header_physical\":{},"
          "\"header_word\":{},\"command_owner\":{},"
          "\"procedural_receiver\":{},\"procedural_call\":{}}}",
          rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
          ordinal, guest_address, guest_address & 0x1FFFFFFF, r11.u32,
          r31.u32, snr01_procedural_scopes.empty()
                       ? 0 : snr01_procedural_scopes.back().receiver,
          snr01_procedural_scopes.empty()
                       ? 0 : snr01_procedural_scopes.back().ordinal);
    }
  }
  if (!rex::perf::CriticalPathTraceEnabled()) {
    return;
  }
  const int64_t now_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
                             ClearClock::now().time_since_epoch())
                             .count();
  if (!title_packet_count) {
    title_first_packet_ns = now_ns;
  }
  title_last_packet_ns = now_ns;
  ++title_packet_count;
}

void PinyonShiftObservePresentationViewBegin(
    PPCRegister& r12, PPCRegister& r3, PPCRegister& r4, PPCRegister& r5,
    PPCRegister& r6, PPCRegister& r7, PPCRegister& r8) {
  if (REXCVAR_GET(pinyon_shift_snr02_trace_first_rebuild_after_frame) > 0) {
    const uint64_t frame = rex::perf::GetTotalCounter(
        rex::perf::CounterId::kSourceFrameCount);
    if (snr02_view_frame != frame && snr02_view_scopes.empty()) {
      snr02_view_count = 0;
      snr02_view_frame = frame;
    }
    snr02_view_scopes.push_back(++snr02_view_count);
  }
  if (!Snr01TraceCurrentFrame()) {
    return;
  }
  const uint64_t frame = rex::perf::GetTotalCounter(
      rex::perf::CounterId::kSourceFrameCount);
  if (snr01_view_frame != frame && snr01_view_scopes.empty()) {
    snr01_view_begin_count = 0;
    snr01_view_frame = frame;
  }
  const uint64_t ordinal = ++snr01_view_begin_count;
  if (ordinal == 8) {
    snr01_view8_flush_owners.clear();
    if (Snr02TrackTargetFrame() > 0 &&
        frame == uint64_t(Snr02TrackTargetFrame())) {
      std::lock_guard lock(snr02_track_targets_mutex);
      snr02_track_targets.clear();
      snr02_track_targets_overflow = false;
      snr02_track_title_ready = false;
      snr02_track_camera80 = {};
      snr02_track_camera144 = {};
      snr02_track_payload = {};
    }
    if (Snr02ItemTargetFrame() > 0 && frame == uint64_t(Snr02ItemTargetFrame())) {
      snr02_item_title_items.clear();
      snr02_item_title_rejected = false;
    }
    if (Snr03TargetFrame() > 0 && frame == uint64_t(Snr03TargetFrame())) {
      snr03_vegetation_items.clear();
      snr03_scene_overflow = false;
    }
  }
  snr01_view_scopes.push_back(
      {r3.u32, r4.u32, snr01_semantic_packet_count,
       snr01_direct_packet_count, snr01_primary_indirect_packet_count,
       ordinal});
  if (ordinal <= kSnr01ProceduralLimit) {
    REXGPU_INFO(
        "FH1 SNR01 view begin {{\"frame\":{},\"call\":{},"
        "\"caller_lr\":{},\"view\":{},\"arg4\":{},\"arg5\":{},"
        "\"arg6\":{},\"arg7\":{},\"arg8\":{}}}",
        rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
        ordinal, r12.u32, r3.u32, r4.u32, r5.u32, r6.u32, r7.u32,
        r8.u32);
  }
}

void PinyonShiftObservePresentationViewEnd() {
  if (!snr02_view_scopes.empty()) {
    snr02_view_scopes.pop_back();
  }
  if (snr01_view_scopes.empty()) {
    return;
  }
  const auto scope = snr01_view_scopes.back();
  snr01_view_scopes.pop_back();
  const uint64_t frame = uint64_t(rex::perf::GetTotalCounter(
      rex::perf::CounterId::kSourceFrameCount));
  if (scope.ordinal == 8 && Snr02TrackTargetFrame() > 0 &&
      frame == uint64_t(Snr02TrackTargetFrame())) {
    std::lock_guard lock(snr02_track_targets_mutex);
    if (!snr02_track_targets_overflow && !snr02_track_targets.empty() &&
        scope.camera) {
      for (uint32_t i = 0; i < 16; ++i) {
        snr02_track_camera80[i] = SnrM02ReadU32(scope.camera + 80 + i * 4);
        snr02_track_camera144[i] = SnrM02ReadU32(scope.camera + 144 + i * 4);
      }
      snr02_track_title_ready = true;
    }
    REXGPU_INFO("FH1 SNR02 track title scene frame={} targets={} ready={} overflow={}",
                frame, snr02_track_targets.size(), snr02_track_title_ready,
                snr02_track_targets_overflow);
  }
  if (scope.ordinal == 8 && Snr02ItemTargetFrame() > 0 &&
      frame == uint64_t(Snr02ItemTargetFrame())) {
    std::set<uint32_t> packets;
    for (const auto& item : snr02_item_title_items) {
      if (!packets.insert(item.packet).second) snr02_item_title_rejected = true;
    }
    if (snr02_item_title_rejected || snr02_item_title_items.empty() || !scope.camera) {
      REXGPU_INFO("FH1 SNR02 item scene rejected frame={} items={} invalid={} camera={}",
                  frame, snr02_item_title_items.size(), snr02_item_title_rejected,
                  scope.camera);
    } else {
      Snr02ItemScene snapshot{};
      snapshot.source_frame = frame;
      for (uint32_t i = 0; i < 16; ++i) {
        snapshot.camera80[i] = SnrM02ReadU32(scope.camera + 80 + i * 4);
        snapshot.camera144[i] = SnrM02ReadU32(scope.camera + 144 + i * 4);
      }
      snapshot.items = std::move(snr02_item_title_items);
      auto scene = std::make_shared<const Snr02ItemScene>(std::move(snapshot));
      {
        std::lock_guard lock(snr02_item_scene_mutex);
        if (snr02_item_scenes.size() == 2) {
          const auto old = snr02_item_scenes.begin()->first;
          snr02_item_scenes.erase(snr02_item_scenes.begin());
          snr02_item_payloads.erase(old);
        }
        snr02_item_scenes[frame] = scene;
      }
      REXGPU_INFO("FH1 SNR02 item scene published frame={} items={}",
                  frame, scene->items.size());
    }
  }
  if (scope.ordinal == 8 && Snr03TargetFrame() > 0 &&
      frame == uint64_t(Snr03TargetFrame())) {
    if (snr03_scene_overflow || snr03_vegetation_items.empty() ||
        !scope.camera) {
      REXGPU_INFO("FH1 SNR03 scene rejected frame={} overflow={} items={} camera={}",
                  frame, snr03_scene_overflow,
                  snr03_vegetation_items.size(), scope.camera);
    } else {
      Snr03SceneSnapshot snapshot{};
      snapshot.source_frame = frame;
      snapshot.view = scope.view;
      snapshot.camera = scope.camera;
      for (uint32_t i = 0; i < 16; ++i) {
        snapshot.camera80[i] = SnrM02ReadU32(scope.camera + 80 + i * 4);
        snapshot.camera144[i] = SnrM02ReadU32(scope.camera + 144 + i * 4);
      }
      snapshot.items = std::move(snr03_vegetation_items);
      std::shared_ptr<const Snr03SceneSnapshot> scene =
          std::make_shared<Snr03SceneSnapshot>(std::move(snapshot));
      const auto fingerprint = Snr03Fingerprint(*scene);
      uint64_t dropped_frame = 0;
      {
        std::lock_guard lock(snr03_scene_mutex);
        if (snr03_scenes.size() == 2) {
          dropped_frame = snr03_scenes.begin()->first;
          snr03_scenes.erase(snr03_scenes.begin());
          snr03_payloads.erase(dropped_frame);
        }
        snr03_scenes[frame] = scene;
      }
      if (dropped_frame) {
        REXGPU_INFO("FH1 SNR03 scene dropped frame={}", dropped_frame);
      }
      REXGPU_INFO("FH1 SNR03 scene published frame={} view={} camera={} "
                  "items={} fingerprint={}", frame, scene->view, scene->camera,
                  scene->items.size(), fingerprint);
      for (uint32_t row = 0; row < 4; ++row) {
        for (const auto* matrix : {&scene->camera80, &scene->camera144}) {
          REXGPU_INFO("FH1 SNR03 camera row {{\"frame\":{},\"offset\":{},"
                      "\"row\":{},\"words\":[{},{},{},{}]}}",
                      frame, matrix == &scene->camera80 ? 80 : 144, row,
                      (*matrix)[row * 4], (*matrix)[row * 4 + 1],
                      (*matrix)[row * 4 + 2], (*matrix)[row * 4 + 3]);
        }
      }
      for (size_t i = 0; i < scene->items.size(); ++i) {
        const auto& item = scene->items[i];
        REXGPU_INFO("FH1 SNR03 item {{\"frame\":{},\"ordinal\":{},"
                    "\"owner\":{},\"record\":{},"
                    "\"vertex_descriptor\":{},\"vertex_address\":{},"
                    "\"vertex_size\":{},\"packet_physical\":{},"
                    "\"bucket_entry\":{}}}",
                    frame, i + 1, item.owner, item.record,
                    item.vertex_descriptor, item.vertex_address,
                    item.vertex_size, item.packet_physical, item.bucket_entry);
      }
    }
  }
  if (scope.ordinal <= kSnr01ProceduralLimit) {
    REXGPU_INFO(
        "FH1 SNR01 view end {{\"frame\":{},\"call\":{},"
        "\"view\":{},\"arg4\":{},\"camera\":{},"
        "\"matrix80_hash\":{},\"matrix144_hash\":{},"
        "\"first_semantic\":{},\"last_semantic\":{},"
        "\"first_direct\":{},\"last_direct\":{},"
        "\"first_primary\":{},\"last_primary\":{}}}",
        rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
        scope.ordinal, scope.view, scope.argument, scope.camera,
        Snr01CameraMatrixHash(scope.camera, 80),
        Snr01CameraMatrixHash(scope.camera, 144),
        scope.first_semantic_packet + 1, snr01_semantic_packet_count,
        scope.first_direct_packet + 1, snr01_direct_packet_count,
        scope.first_primary_packet + 1,
        snr01_primary_indirect_packet_count);
  }
  if (scope.ordinal == 8) {
    const uint32_t root = snr01_vehicle_map_pool_root.load(
        std::memory_order_acquire);
    if (root) {
      REXGPU_INFO("FH1 SNR01 player map entity {{\"frame\":{},"
                  "\"pool\":{},\"entity\":{},\"vtable\":{},"
                  "\"vehicle_id\":{},\"context\":{},"
                  "\"link72\":{},\"link72_first_word\":{},"
                  "\"link76\":{},\"link76_first_word\":{},"
                  "\"link84\":{},\"link84_first_word\":{}}}",
                  rex::perf::GetTotalCounter(
                      rex::perf::CounterId::kSourceFrameCount),
                  root, root + 32, SnrM02ReadU32(root + 32),
                  SnrM02ReadU32(root + 44), SnrM02ReadU32(root + 16),
                  SnrM02ReadU32(root + 104),
                  SnrM02ReadU32(SnrM02ReadU32(root + 104)),
                  SnrM02ReadU32(root + 108),
                  SnrM02ReadU32(SnrM02ReadU32(root + 108)),
                  SnrM02ReadU32(root + 116),
                  SnrM02ReadU32(SnrM02ReadU32(root + 116)));
    }
    std::lock_guard lock(snr01_player_mutex);
    uint32_t local_car = 0;
    for (uint32_t player : snr01_forza_players) {
      if (SnrM02ReadU32(player) != 0x8201EB4C) {
        continue;
      }
      REXGPU_INFO("FH1 SNR01 Forza player {{\"frame\":{},\"player\":{},"
                  "\"vtable\":{},"
                  "\"link160\":{},\"link160_first_word\":{},"
                  "\"link164\":{},\"link164_first_word\":{},"
                  "\"link168\":{},\"link172\":{},\"link176\":{},"
                  "\"link180\":{},\"link180_first_word\":{}}}",
                  rex::perf::GetTotalCounter(
                      rex::perf::CounterId::kSourceFrameCount),
                  player, SnrM02ReadU32(player), SnrM02ReadU32(player + 160),
                  SnrM02ReadU32(SnrM02ReadU32(player + 160)),
                  SnrM02ReadU32(player + 164),
                  SnrM02ReadU32(SnrM02ReadU32(player + 164)),
                  SnrM02ReadU32(player + 168), SnrM02ReadU32(player + 172),
                  SnrM02ReadU32(player + 176), SnrM02ReadU32(player + 180),
                  SnrM02ReadU32(SnrM02ReadU32(player + 180)));
      if (SnrM02ReadU32(SnrM02ReadU32(player + 164)) == 0x82014510) {
        local_car = SnrM02ReadU32(player + 160);
      }
    }
    const uint32_t local_livery = local_car ? SnrM02ReadU32(local_car + 12292) : 0;
    for (const auto& [presentation, constructor_arg] :
         snr01_car_presentations) {
      if (SnrM02ReadU32(presentation) != 0x82003A54) {
        continue;
      }
      REXGPU_INFO(
          "FH1 SNR01 car presentation {{\"frame\":{},"
          "\"presentation\":{},\"constructor_arg\":{},"
          "\"constructor_arg_first_word\":{},\"view8_owner\":{}}}",
          rex::perf::GetTotalCounter(
              rex::perf::CounterId::kSourceFrameCount),
          presentation, constructor_arg, SnrM02ReadU32(constructor_arg),
          snr01_view8_flush_owners.contains(presentation));
      if (local_livery && SnrM02ReadU32(presentation + 2800) == local_livery) {
        const uint32_t model = SnrM02ReadU32(presentation + 5648);
        REXGPU_INFO(
            "FH1 SNR01 local car presentation link "
            "{{\"frame\":{},\"car\":{},\"presentation\":{},"
            "\"livery\":{},\"livery_vtable\":{},\"model\":{},"
            "\"model_vtable\":{},\"view8_owner\":{}}}",
            rex::perf::GetTotalCounter(
                rex::perf::CounterId::kSourceFrameCount),
            local_car, presentation, local_livery, SnrM02ReadU32(local_livery),
            model, SnrM02ReadU32(model),
            snr01_view8_flush_owners.contains(presentation));
      }
    }
  }
}

void PinyonShiftObservePresentationViewSelected(PPCRegister& r31,
                                                PPCRegister& r25) {
  if (!Snr01TraceCurrentFrame()) {
    return;
  }
  const uint64_t ordinal = ++snr01_view_selected_count;
  if (ordinal <= kSnr01ProceduralLimit) {
    REXGPU_INFO(
        "FH1 SNR01 view selected {{\"frame\":{},\"call\":{},"
        "\"view\":{},\"selected_context\":{}}}",
        rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
        ordinal, r31.u32, r25.u32);
  }
}

void PinyonShiftObservePresentationViewObject400(
    PPCRegister& r31, PPCRegister& r3, PPCRegister& r11) {
  if (!Snr01TraceCurrentFrame() || snr01_view_scopes.empty()) {
    return;
  }
  const uint32_t camera = r11.u32 == 0x82002F64 ? r3.u32 : 0;
  snr01_view_scopes.back().camera = camera;
  REXGPU_INFO(
      "FH1 SNR01 view object400 {{\"frame\":{},\"call\":{},"
      "\"view\":{},\"object\":{},\"vtable\":{},"
      "\"matrix80_hash\":{},\"matrix144_hash\":{}}}",
      rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
      snr01_view_scopes.back().ordinal, r31.u32, r3.u32, r11.u32,
      Snr01CameraMatrixHash(camera, 80), Snr01CameraMatrixHash(camera, 144));
}

void ObserveSnr01CameraMethod(uint32_t slot, PPCRegister& r3,
                             PPCRegister& r4) {
  if (!Snr01TraceLinkedWriteFrame() || ++snr01_camera_method_count > 1024) {
    return;
  }
  REXGPU_INFO(
      "FH1 SNR01 camera method {{\"frame\":{},\"ordinal\":{},"
      "\"slot\":{},\"camera\":{},\"arg4\":{},"
      "\"view_call\":{},\"view\":{}}}",
      rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
      snr01_camera_method_count, slot, r3.u32, r4.u32,
      snr01_view_scopes.empty() ? 0 : snr01_view_scopes.back().ordinal,
      snr01_view_scopes.empty() ? 0 : snr01_view_scopes.back().view);
}

void PinyonShiftObserveCameraMethod11(PPCRegister& r3, PPCRegister& r4) {
  ObserveSnr01CameraMethod(11, r3, r4);
}

void PinyonShiftObserveCameraMethod12(PPCRegister& r3, PPCRegister& r4) {
  ObserveSnr01CameraMethod(12, r3, r4);
}

void PinyonShiftObserveCameraMethod43(PPCRegister& r3, PPCRegister& r4) {
  ObserveSnr01CameraMethod(43, r3, r4);
}

void PinyonShiftObserveCameraMethod44(PPCRegister& r3, PPCRegister& r4) {
  ObserveSnr01CameraMethod(44, r3, r4);
}

void PinyonShiftObservePresentationSelectedContextVtable(
    PPCRegister& r31, PPCRegister& r25, PPCRegister& r11) {
  if (!Snr01TraceCurrentFrame() || snr01_view_scopes.empty()) {
    return;
  }
  REXGPU_INFO(
      "FH1 SNR01 selected context vtable {{\"frame\":{},\"call\":{},"
      "\"view\":{},\"context\":{},\"vtable\":{}}}",
      rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
      snr01_view_scopes.back().ordinal, r31.u32, r25.u32, r11.u32);
}

void PinyonShiftObservePresentationTrackLink(PPCRegister& r31,
                                             PPCRegister& r11,
                                             PPCRegister& r10) {
  if (!Snr01TraceCurrentFrame()) {
    return;
  }
  const uint64_t ordinal = ++snr01_view_track_count;
  if (ordinal <= kSnr01ProceduralLimit) {
    REXGPU_INFO(
        "FH1 SNR01 view track link {{\"frame\":{},\"call\":{},"
        "\"view\":{},\"view_state\":{},\"track_presenter\":{}}}",
        rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
        ordinal, r31.u32, r11.u32, r10.u32);
  }
}

void PinyonShiftObserveTrackPresentation75(
    PPCRegister& r12, PPCRegister& r3, PPCRegister& r4, PPCRegister& r5,
    PPCRegister& r6, PPCRegister& r7, PPCRegister& r8, PPCRegister& r9,
    PPCRegister& r10) {
  if (!Snr01TraceCurrentFrame()) {
    return;
  }
  const uint64_t ordinal = ++snr01_track75_count;
  const uint64_t view_call = snr01_view_scopes.empty()
                                 ? 0
                                 : snr01_view_scopes.back().ordinal;
  snr01_track75_scopes.push_back(
      {ordinal, view_call, snr01_track_bucket_count});
  if (ordinal <= kSnr01ProceduralLimit) {
    REXGPU_INFO(
        "FH1 SNR01 track presentation {{\"frame\":{},\"slot\":75,"
        "\"call\":{},\"view_call\":{},\"caller_lr\":{},\"receiver\":{},"
        "\"arg4\":{},\"arg5\":{},\"arg6\":{},\"arg7\":{},"
        "\"arg8\":{},\"arg9\":{},\"arg10\":{}}}",
        rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
        ordinal, view_call, r12.u32, r3.u32, r4.u32, r5.u32, r6.u32,
        r7.u32, r8.u32, r9.u32, r10.u32);
  }
}

void PinyonShiftObserveTrackPresentation75End() {
  if (snr01_track75_scopes.empty()) {
    if (Snr01TraceCurrentFrame()) {
      ++snr01_unmatched_track75_exits;
    }
    return;
  }
  const auto scope = snr01_track75_scopes.back();
  snr01_track75_scopes.pop_back();
  if (scope.ordinal <= kSnr01ProceduralLimit) {
    REXGPU_INFO(
        "FH1 SNR01 track presentation end {{\"frame\":{},"
        "\"call\":{},\"view_call\":{},"
        "\"first_bucket\":{},\"last_bucket\":{}}}",
        rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
        scope.ordinal, scope.view_call, scope.first_bucket + 1,
        snr01_track_bucket_count);
  }
}

void PinyonShiftObserveTrackBucketEntryBegin(
    PPCRegister& r31, PPCRegister& r24, PPCRegister& r20, PPCRegister& r11,
    PPCRegister& r27, PPCRegister& r28, PPCRegister& r22) {
  if (!Snr01TraceCurrentFrame()) {
    return;
  }
  snr01_track_bucket_scopes.push_back(
      {r31.u32, r24.u32, r20.u32, r11.u32 + r27.u32, r28.u32,
       0, r22.u32, snr01_semantic_packet_count, snr01_direct_packet_count,
       ++snr01_track_bucket_count});
  snr01_track_bucket_scopes.back().track_call =
      snr01_track75_scopes.empty() ? 0 : snr01_track75_scopes.back().ordinal;
}

void PinyonShiftObserveTrackBucketSecondaryRecord(PPCRegister& r11,
                                                  PPCRegister& r28) {
  if (snr01_track_bucket_scopes.empty()) {
    return;
  }
  auto& scope = snr01_track_bucket_scopes.back();
  if (scope.entry == r11.u32) {
    scope.secondary_record = r28.u32;
    scope.secondary_seen = true;
  }
}

void PinyonShiftObserveTrackBucketFirstObject(PPCRegister& r3,
                                              PPCRegister& r11) {
  if (!snr01_track_bucket_scopes.empty()) {
    auto& scope = snr01_track_bucket_scopes.back();
    scope.first_object = r3.u32;
    scope.first_vtable = r11.u32;
  }
}

void PinyonShiftObserveTrackBucketFirstGuard(PPCRegister& r3) {
  if (!snr01_track_bucket_scopes.empty()) {
    snr01_track_bucket_scopes.back().first_guard = r3.u32 & 0xFF;
  }
}

void PinyonShiftObserveTrackBucketSecondaryResolved(PPCRegister& r3) {
  if (!snr01_track_bucket_scopes.empty()) {
    auto& scope = snr01_track_bucket_scopes.back();
    scope.secondary_resolved = r3.u32;
    scope.secondary_resolved_seen = true;
    if (r3.u32) {
      if (auto* memory = snr01_memory.load(std::memory_order_acquire)) {
        scope.secondary_byte52 = *memory->TranslateVirtual(r3.u32 + 52);
        scope.secondary_byte55 = *memory->TranslateVirtual(r3.u32 + 55);
      }
    }
  }
}

void PinyonShiftObserveTrackBucketAuxiliaryResolved(
    PPCRegister& r3, PPCRegister& r28, PPCRegister& r14) {
  if (!snr01_track_bucket_scopes.empty()) {
    auto& scope = snr01_track_bucket_scopes.back();
    scope.auxiliary_record = r28.u32;
    scope.auxiliary_resolved = r3.u32;
    scope.auxiliary_flag = r14.u32;
    scope.auxiliary_seen = true;
  }
}

void PinyonShiftObserveTrackBucketEntryEnd() {
  if (snr01_track_bucket_scopes.empty()) {
    if (Snr01TraceCurrentFrame()) {
      ++snr01_unmatched_track_bucket_exits;
    }
    return;
  }
  const auto scope = snr01_track_bucket_scopes.back();
  snr01_track_bucket_scopes.pop_back();
  if (scope.ordinal <= kSnr01ProceduralLimit) {
    REXGPU_INFO(
        "FH1 SNR01 track bucket entry {{\"frame\":{},\"ordinal\":{},"
        "\"presenter\":{},\"view\":{},\"track_call\":{},\"bucket\":{},"
        "\"entry\":{},\"record\":{},\"secondary_record\":{},"
        "\"secondary_seen\":{},\"remaining\":{},"
        "\"first_object\":{},\"first_vtable\":{},"
        "\"first_guard\":{},\"secondary_resolved\":{},"
        "\"secondary_resolved_seen\":{},"
        "\"secondary_byte52\":{},\"secondary_byte55\":{},"
        "\"auxiliary_record\":{},\"auxiliary_resolved\":{},"
        "\"auxiliary_flag\":{},\"auxiliary_seen\":{},"
        "\"first_semantic\":{},\"last_semantic\":{},"
        "\"first_direct\":{},\"last_direct\":{}}}",
        rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
        scope.ordinal, scope.presenter, scope.view, scope.track_call,
        scope.bucket,
        scope.entry, scope.record, scope.secondary_record,
        scope.secondary_seen, scope.remaining,
        scope.first_object, scope.first_vtable, scope.first_guard,
        scope.secondary_resolved, scope.secondary_resolved_seen,
        scope.secondary_byte52, scope.secondary_byte55,
        scope.auxiliary_record, scope.auxiliary_resolved,
        scope.auxiliary_flag, scope.auxiliary_seen,
        scope.first_semantic_packet + 1, snr01_semantic_packet_count,
        scope.first_direct_packet + 1, snr01_direct_packet_count);
  }
}

void PinyonShiftObserveTrackPresentation79(
    PPCRegister& r12, PPCRegister& r3, PPCRegister& r4, PPCRegister& r5,
    PPCRegister& r6, PPCRegister& r7, PPCRegister& r8, PPCRegister& r9,
    PPCRegister& r10) {
  if (!Snr01TraceCurrentFrame()) {
    return;
  }
  const uint64_t ordinal = ++snr01_track79_count;
  if (ordinal <= kSnr01ProceduralLimit) {
    REXGPU_INFO(
        "FH1 SNR01 track presentation {{\"frame\":{},\"slot\":79,"
        "\"call\":{},\"caller_lr\":{},\"receiver\":{},"
        "\"arg4\":{},\"arg5\":{},\"arg6\":{},\"arg7\":{},"
        "\"arg8\":{},\"arg9\":{},\"arg10\":{}}}",
        rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
        ordinal, r12.u32, r3.u32, r4.u32, r5.u32, r6.u32,
        r7.u32, r8.u32, r9.u32, r10.u32);
  }
}

void PinyonShiftObserveTrackPassCaller(
    PPCRegister& r12, PPCRegister& r3, PPCRegister& r4, PPCRegister& r5,
    PPCRegister& r6, PPCRegister& r7, PPCRegister& r8) {
  if (!Snr01TraceCurrentFrame()) {
    return;
  }
  const uint64_t ordinal = ++snr01_track_pass_count;
  if (ordinal <= kSnr01ProceduralLimit) {
    REXGPU_INFO(
        "FH1 SNR01 track pass caller {{\"frame\":{},\"call\":{},"
        "\"caller_lr\":{},\"receiver\":{},\"arg4\":{},"
        "\"arg5\":{},\"arg6\":{},\"arg7\":{},\"arg8\":{}}}",
        rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
        ordinal, r12.u32, r3.u32, r4.u32, r5.u32, r6.u32,
        r7.u32, r8.u32);
  }
}

void PinyonShiftObserveProceduralStateWrapperCaller(
    PPCRegister& r12, PPCRegister& r3, PPCRegister& r4, PPCRegister& r5,
    PPCRegister& r6, PPCRegister& r7, PPCRegister& r8, PPCRegister& r9) {
  if (!Snr01TraceCurrentFrame()) {
    return;
  }
  const uint64_t ordinal = ++snr01_state_wrapper_count;
  if (ordinal <= kSnr01ProceduralLimit) {
    REXGPU_INFO(
        "FH1 SNR01 state wrapper {{\"frame\":{},\"call\":{},"
        "\"caller_lr\":{},\"arg3\":{},\"arg4\":{},\"arg5\":{},"
        "\"arg6\":{},\"arg7\":{},\"arg8\":{},\"arg9\":{}}}",
        rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
        ordinal, r12.u32, r3.u32, r4.u32, r5.u32, r6.u32,
        r7.u32, r8.u32, r9.u32);
  }
}

void PinyonShiftObserveProceduralDispatchWrapperCaller(
    PPCRegister& r12, PPCRegister& r3, PPCRegister& r4, PPCRegister& r5,
    PPCRegister& r6, PPCRegister& r7, PPCRegister& r8, PPCRegister& r9,
    PPCRegister& r10) {
  if (!Snr01TraceCurrentFrame()) {
    return;
  }
  const uint64_t ordinal = ++snr01_dispatch_wrapper_count;
  if (ordinal <= kSnr01ProceduralLimit) {
    REXGPU_INFO(
        "FH1 SNR01 dispatch wrapper {{\"frame\":{},\"call\":{},"
        "\"caller_lr\":{},\"arg3\":{},\"arg4\":{},\"arg5\":{},"
        "\"arg6\":{},\"arg7\":{},\"arg8\":{},\"arg9\":{},"
        "\"arg10\":{}}}",
        rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
        ordinal, r12.u32, r3.u32, r4.u32, r5.u32, r6.u32,
        r7.u32, r8.u32, r9.u32, r10.u32);
  }
}

void PinyonShiftObserveProceduralDispatchBegin(
    PPCRegister& r12, PPCRegister& r3, PPCRegister& r4, PPCRegister& r5,
    PPCRegister& r6, PPCRegister& r7, PPCRegister& r8, PPCRegister& r9,
    PPCRegister& r10) {
  if (!Snr01TraceCurrentFrame()) {
    return;
  }
  const uint64_t ordinal = ++snr01_dispatch_count;
  snr01_dispatch_scopes.push_back(
      {r12.u32, r3.u32, r4.u32, r5.u32, r6.u32, r7.u32, r8.u32,
       r9.u32, r10.u32,
       snr01_semantic_packet_count, snr01_procedural_count, ordinal});
}

void PinyonShiftObserveProceduralDispatchEnd() {
  if (!Snr01TraceCurrentFrame()) {
    return;
  }
  if (snr01_dispatch_scopes.empty()) {
    ++snr01_unmatched_dispatch_exits;
    return;
  }
  const auto scope = snr01_dispatch_scopes.back();
  snr01_dispatch_scopes.pop_back();
  if (scope.ordinal <= kSnr01ProceduralLimit) {
    REXGPU_INFO(
        "FH1 SNR01 procedural dispatch {{\"frame\":{},\"call\":{},"
        "\"caller_lr\":{},\"receiver\":{},\"context\":{},"
        "\"arg5\":{},\"arg6\":{},\"arg7\":{},"
        "\"arg8\":{},\"arg9\":{},\"arg10\":{},"
        "\"first_semantic_packet\":{},\"last_semantic_packet\":{},"
        "\"first_item_call\":{},\"last_item_call\":{}}}",
        rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
        scope.ordinal, scope.caller_lr, scope.receiver, scope.context,
        scope.arg5, scope.arg6, scope.arg7,
        scope.arg8, scope.arg9, scope.arg10,
        scope.first_semantic_packet + 1, snr01_semantic_packet_count,
        scope.first_procedural_call + 1, snr01_procedural_count);
  }
}

void PinyonShiftObserveProceduralRenderStateBegin(
    PPCRegister& r12, PPCRegister& r3, PPCRegister& r4, PPCRegister& r5,
    PPCRegister& r6, PPCRegister& r7, PPCRegister& r8, PPCRegister& r9,
    PPCRegister& r10) {
  if (!Snr01TraceCurrentFrame()) {
    return;
  }
  const uint64_t ordinal = ++snr01_render_state_count;
  snr01_render_state_scopes.push_back(
      {r12.u32, r3.u32, r4.u32, r5.u32, r6.u32, r7.u32, r8.u32,
       r9.u32, r10.u32,
       snr01_semantic_packet_count, snr01_procedural_count, ordinal});
}

void PinyonShiftObserveProceduralRenderStateEnd() {
  if (!Snr01TraceCurrentFrame()) {
    return;
  }
  if (snr01_render_state_scopes.empty()) {
    ++snr01_unmatched_render_state_exits;
    return;
  }
  const auto scope = snr01_render_state_scopes.back();
  snr01_render_state_scopes.pop_back();
  if (scope.ordinal <= kSnr01ProceduralLimit) {
    REXGPU_INFO(
        "FH1 SNR01 render state {{\"frame\":{},\"call\":{},"
        "\"caller_lr\":{},\"receiver\":{},\"context\":{},"
        "\"arg5\":{},\"arg6\":{},\"arg7\":{},"
        "\"arg8\":{},\"arg9\":{},\"arg10\":{},"
        "\"first_semantic_packet\":{},\"last_semantic_packet\":{},"
        "\"first_item_call\":{},\"last_item_call\":{}}}",
        rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
        scope.ordinal, scope.caller_lr, scope.receiver, scope.context,
        scope.arg5, scope.arg6, scope.arg7,
        scope.arg8, scope.arg9, scope.arg10,
        scope.first_semantic_packet + 1, snr01_semantic_packet_count,
        scope.first_procedural_call + 1, snr01_procedural_count);
  }
}

void PinyonShiftObserveProceduralItemNodeBegin(
    PPCRegister& r30, PPCRegister& r24, PPCRegister& r3,
    PPCRegister& r11, PPCRegister& r25) {
  if (!Snr01TraceCurrentFrame()) {
    return;
  }
  snr01_item_node_scopes.push_back(
      {r30.u32, r24.u32, r3.u32, r11.u32, r25.u32,
       snr01_view_scopes.empty() ? 0 : snr01_view_scopes.back().ordinal,
       snr01_track_bucket_scopes.empty()
           ? 0 : snr01_track_bucket_scopes.back().ordinal,
       snr01_procedural_count, snr01_semantic_packet_count,
       ++snr01_item_node_count});
}

void PinyonShiftObserveProceduralItemNodeEnd() {
  if (snr01_item_node_scopes.empty()) {
    if (Snr01TraceCurrentFrame()) {
      ++snr01_unmatched_item_node_exits;
    }
    return;
  }
  const auto scope = snr01_item_node_scopes.back();
  snr01_item_node_scopes.pop_back();
  if (scope.ordinal <= kSnr01ProceduralLimit) {
    REXGPU_INFO(
        "FH1 SNR01 item node {{\"frame\":{},\"ordinal\":{},"
        "\"node\":{},\"list_head\":{},\"receiver\":{},"
        "\"index\":{},\"render_owner\":{},\"view_call\":{},"
        "\"bucket_entry\":{},\"first_item\":{},\"last_item\":{},"
        "\"first_semantic\":{},\"last_semantic\":{}}}",
        rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
        scope.ordinal, scope.node, scope.list_head, scope.receiver,
        scope.index, scope.render_owner, scope.view_call,
        scope.bucket_entry, scope.first_item_call + 1,
        snr01_procedural_count, scope.first_semantic_packet + 1,
        snr01_semantic_packet_count);
  }
}

void PinyonShiftObserveProceduralItemBegin(
    PPCRegister& r3, PPCRegister& r4, PPCRegister& r7, PPCRegister& r8,
    PPCRegister& r9, PPCRegister& r10) {
  if (!Snr01TraceCurrentFrame()) {
    return;
  }
  const uint64_t ordinal = ++snr01_procedural_count;
  snr01_procedural_scopes.push_back(
      {r3.u32, snr01_packet_count, snr01_semantic_packet_count, ordinal});
  if (ordinal <= kSnr01ProceduralLimit) {
    REXGPU_INFO(
        "FH1 SNR01 item arguments {{\"frame\":{},\"call\":{},"
        "\"receiver\":{},\"context\":{},\"arg7\":{},\"arg8\":{},"
        "\"arg9\":{},\"arg10\":{},\"dispatch_call\":{},"
        "\"render_state_call\":{}}}",
        rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
        ordinal, r3.u32, r4.u32, r7.u32, r8.u32, r9.u32, r10.u32,
        snr01_dispatch_scopes.empty() ? 0
                                     : snr01_dispatch_scopes.back().ordinal,
        snr01_render_state_scopes.empty()
            ? 0 : snr01_render_state_scopes.back().ordinal);
  }
}

void PinyonShiftObserveProceduralDescriptor(PPCRegister& r9,
                                            PPCRegister& r28,
                                            PPCRegister& r8,
                                            PPCRegister& r25) {
  if (!Snr01TraceCurrentFrame() || snr01_procedural_scopes.empty()) {
    return;
  }
  auto& scope = snr01_procedural_scopes.back();
  scope.descriptor_index = r9.u32;
  scope.descriptor_address = r28.u32;
  scope.descriptor_kind = r8.u32;
  scope.render_state = r25.u32;
  scope.descriptor_seen = true;
}

void PinyonShiftObserveProceduralRuntimeRecord(PPCRegister& r26) {
  if (!Snr01TraceCurrentFrame() || snr01_procedural_scopes.empty()) {
    return;
  }
  auto& scope = snr01_procedural_scopes.back();
  scope.runtime_address = r26.u32;
  scope.runtime_seen = true;
}

void PinyonShiftObserveProceduralResourceCandidate(
    PPCRegister& r4, PPCRegister& r5, PPCRegister& r6) {
  if (!Snr01TraceCurrentFrame() || snr01_procedural_scopes.empty()) {
    return;
  }
  const auto& scope = snr01_procedural_scopes.back();
  if (scope.ordinal <= kSnr01ProceduralLimit) {
    REXGPU_INFO(
        "FH1 SNR01 resource candidate {{\"frame\":{},\"call\":{},"
        "\"descriptor\":{},\"key\":{},\"slot\":{},"
        "\"resolver_context\":{}}}",
        rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
        scope.ordinal, scope.descriptor_address, r4.u32, r5.u32, r6.u32);
  }
}

void PinyonShiftObserveProceduralResourceResolution(PPCRegister& r3) {
  if (!Snr01TraceCurrentFrame() || snr01_procedural_scopes.empty()) {
    return;
  }
  const auto& scope = snr01_procedural_scopes.back();
  if (scope.ordinal <= kSnr01ProceduralLimit) {
    REXGPU_INFO(
        "FH1 SNR01 resource resolution {{\"frame\":{},\"call\":{},"
        "\"object\":{}}}",
        rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
        scope.ordinal, r3.u32);
  }
}

void PinyonShiftObserveProceduralResourceBind(
    PPCRegister& r3, PPCRegister& r4, PPCRegister& r5,
    PPCRegister& r11) {
  if (!Snr01TraceCurrentFrame() || snr01_procedural_scopes.empty()) {
    return;
  }
  const auto& scope = snr01_procedural_scopes.back();
  if (scope.ordinal <= kSnr01ProceduralLimit) {
    REXGPU_INFO(
        "FH1 SNR01 resource bind {{\"frame\":{},\"call\":{},"
        "\"context\":{},\"slot\":{},\"object\":{},"
        "\"target\":{}}}",
        rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
        scope.ordinal, r3.u32, r4.u32, r5.u32, r11.u32);
  }
}

void PinyonShiftObserveSecondTrackDispatch(
    PPCRegister& r31, PPCRegister& r11, PPCRegister& r4,
    PPCRegister& r5, PPCRegister& r6, PPCRegister& r7,
    PPCRegister& r8, PPCRegister& r9, PPCRegister& r10) {
  if (!Snr01TraceCurrentFrame() || snr01_track_bucket_scopes.empty()) {
    return;
  }
  auto& bucket = snr01_track_bucket_scopes.back();
  bucket.second_dispatch_target = r11.u32;
  if (bucket.ordinal <= kSnr01ProceduralLimit) {
    REXGPU_INFO(
        "FH1 SNR01 second track dispatch {{\"frame\":{},"
        "\"bucket_entry\":{},\"object\":{},\"target\":{},"
        "\"arg4\":{},\"arg5\":{},\"arg6\":{},\"arg7\":{},"
        "\"arg8\":{},\"arg9\":{},\"arg10\":{}}}",
        rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
        bucket.ordinal, r31.u32, r11.u32, r4.u32, r5.u32,
        r6.u32, r7.u32, r8.u32, r9.u32, r10.u32);
  }
}

void PinyonShiftObserveSnr01ProceduralModelResource(
    PPCRegister& r3, PPCRegister& r14, PPCRegister& r20, PPCRegister& r30) {
  if (REXCVAR_GET(pinyon_shift_snr01_trace_source_frame) <= 0 ||
      !Snr01TraceCurrentFrame() || !r30.u32) {
    return;
  }
  const uint32_t vtable = SnrM02ReadU32(r30.u32);
  const uint32_t parent = SnrM02ReadU32(r30.u32 + 4);
  const uint32_t runtime = SnrM02ReadU32(r30.u32 + 16);
  REXGPU_INFO(
      "FH1 SNR01 procedural model resource {{\"frame\":{},"
      "\"manager\":{},\"state_base\":{},\"resource\":{},"
      "\"vtable\":{},\"slot8\":{},\"ready\":{},"
      "\"field4\":{},\"field16\":{},"
      "\"instance_word12\":{},\"parent_vtable\":{},"
      "\"parent_word12\":{},\"runtime_word0\":{}}}",
      rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
      r14.u32, r20.u32, r30.u32, vtable,
      vtable ? SnrM02ReadU32(vtable + 32) : 0, r3.u32,
      parent, runtime, SnrM02ReadU32(r30.u32 + 12),
      SnrM02ReadU32(parent), parent ? SnrM02ReadU32(parent + 12) : 0,
      SnrM02ReadU32(runtime));
}

void Snr01LogStateFlush(const char* phase, PPCRegister& r1,
                       PPCRegister& r31) {
  if (REXCVAR_GET(pinyon_shift_snr01_trace_source_frame) <= 0 ||
      !Snr01TraceCurrentFrame()) {
    return;
  }
  REXGPU_INFO("FH1 SNR01 state flush {} {{\"frame\":{},"
              "\"caller_lr\":{},\"state\":{},\"scene_packets\":{}}}",
              phase,
              rex::perf::GetTotalCounter(
                  rex::perf::CounterId::kSourceFrameCount),
              SnrM02ReadU32(r1.u32 + 88), r31.u32,
              snr01_scene_indirect_count);
}

void PinyonShiftObserveSnr01StateFlushBegin(PPCRegister& r1,
                                            PPCRegister& r31) {
  Snr01LogStateFlush("begin", r1, r31);
  if (!Snr02TraceCapturedFrame()) {
    return;
  }
  const uint64_t capture = snr02_rebuild_capture.load(std::memory_order_acquire);
  const uint32_t descriptor = SnrM02ReadU32(r31.u32 + 1200);
  const uint32_t command_target =
      descriptor ? SnrM02ReadU32(descriptor + 16) & 0x1FFFFFFF : 0;
  if (command_target == uint32_t(capture) &&
      SnrM02ReadU32(r1.u32 + 88) == 0x82437048) {
    REXGPU_INFO("FH1 SNR02 rebuild flush {{\"frame\":{},"
                "\"state\":{},\"descriptor\":{},"
                "\"command_target\":{},\"caller_lr\":{}}}",
                capture >> 32, r31.u32, descriptor, command_target,
                SnrM02ReadU32(r1.u32 + 88));
  }
}

void PinyonShiftObserveSnr01StateFlushEnd(PPCRegister& r1,
                                          PPCRegister& r31) {
  Snr01LogStateFlush("end", r1, r31);
}

void PinyonShiftObserveSnr01TrackModelBegin(PPCRegister& r3,
                                             PPCRegister& r7) {
  if (!Snr01TraceCurrentFrame() && !Snr02TraceCapturedFrame()) {
    return;
  }
  REXGPU_INFO("FH1 SNR01 track model begin {{\"frame\":{},"
              "\"state_base\":{},\"resource\":{},"
              "\"scene_packets\":{}}}",
              rex::perf::GetTotalCounter(
                  rex::perf::CounterId::kSourceFrameCount),
              r3.u32, r7.u32, snr01_scene_indirect_count);
}

void PinyonShiftObserveSnr01TrackModelReady(PPCRegister& r3,
                                             PPCRegister& r29,
                                             PPCRegister& r30) {
  if (!Snr01TraceCurrentFrame() && !Snr02TraceCapturedFrame()) {
    return;
  }
  const uint32_t vtable = SnrM02ReadU32(r30.u32);
  const uint32_t parent = SnrM02ReadU32(r30.u32 + 4);
  const uint32_t runtime = SnrM02ReadU32(r30.u32 + 16);
  REXGPU_INFO("FH1 SNR01 track model ready {{\"frame\":{},"
              "\"state_base\":{},\"resource\":{},\"vtable\":{},"
              "\"slot8\":{},\"ready\":{},\"parent\":{},"
              "\"runtime\":{},\"instance_word12\":{},"
              "\"parent_vtable\":{},\"parent_word12\":{},"
              "\"runtime_word0\":{}}}",
      rex::perf::GetTotalCounter(
          rex::perf::CounterId::kSourceFrameCount),
      r29.u32, r30.u32, vtable,
      vtable ? SnrM02ReadU32(vtable + 32) : 0, r3.u32,
      parent, runtime, SnrM02ReadU32(r30.u32 + 12),
      SnrM02ReadU32(parent), parent ? SnrM02ReadU32(parent + 12) : 0,
      SnrM02ReadU32(runtime));
}

void PinyonShiftObserveSnr01TrackDescriptor(
    PPCRegister& r19, PPCRegister& r24, PPCRegister& r25,
    PPCRegister& r26, PPCRegister& r28, PPCRegister& r30) {
  if (!Snr01TraceCurrentFrame() && !Snr02TraceCapturedFrame()) {
    return;
  }
  const uint32_t parent = SnrM02ReadU32(r30.u32 + 4);
  const uint32_t model_root = parent ? SnrM02ReadU32(parent + 48) : 0;
  const uint32_t table = SnrM02ReadU32(r19.u32 + 40);
  const uint32_t descriptor = table ? SnrM02ReadU32(table + 4 * r28.u32) : 0;
  uint32_t words[8] = {};
  if (descriptor) {
    for (uint32_t i = 0; i < 8; ++i) {
      words[i] = SnrM02ReadU32(descriptor + 4 * i);
    }
  }
  REXGPU_INFO("FH1 SNR01 track descriptor {{\"frame\":{},"
              "\"resource\":{},\"parent\":{},\"model_root\":{},"
              "\"container\":{},\"gate_word8\":{},\"table\":{},"
              "\"selector_a\":{},\"selector_b\":{},\"index\":{},"
              "\"state\":{},\"descriptor\":{},"
              "\"state_descriptor\":{},\"words\":[{},{},{},{},{},{},{},{}]}}",
              rex::perf::GetTotalCounter(
                  rex::perf::CounterId::kSourceFrameCount),
              r30.u32, parent, model_root, r19.u32,
              SnrM02ReadU32(r19.u32 + 8) >> 16, table,
              r24.u32, r26.u32, r28.u32, r25.u32,
              descriptor, SnrM02ReadU32(r25.u32 + 1200),
              words[0], words[1], words[2], words[3],
              words[4], words[5], words[6], words[7]);
}

void PinyonShiftObserveSnr02TrackNestedEntry(
    PPCRegister& r3, PPCRegister& r19, PPCRegister& r25,
    PPCRegister& r26, PPCRegister& r30) {
  if (!Snr01TraceCurrentFrame() && !Snr02TraceCapturedFrame()) {
    return;
  }
  REXGPU_INFO("FH1 SNR01 track nested entry {{\"frame\":{},"
              "\"flags_address\":{},\"container\":{},\"container_vtable\":{},"
              "\"submodel\":{},\"submodel_vtable\":{},"
              "\"entry\":{},\"entry_vtable\":{},"
              "\"entry_index\":{},\"selected\":{}}}",
              rex::perf::GetTotalCounter(
                  rex::perf::CounterId::kSourceFrameCount),
              r30.u32, r19.u32, SnrM02ReadU32(r19.u32),
              r26.u32, SnrM02ReadU32(r26.u32),
              r25.u32, SnrM02ReadU32(r25.u32),
              SnrM02ReadU32(r25.u32 + 40), r3.u32);
}

void PinyonShiftObserveSnr02TrackRebuildGate(
    PPCRegister& r1, PPCRegister& r25, PPCRegister& r27,
    PPCRegister& r28, PPCRegister& r30, PPCRegister& r31) {
  const int32_t target = REXCVAR_GET(pinyon_shift_snr01_trace_source_frame);
  const int32_t rebuild_after =
      REXCVAR_GET(pinyon_shift_snr02_trace_first_rebuild_after_frame);
  const int32_t view_filter = REXCVAR_GET(pinyon_shift_snr02_trace_view_call);
  const uint32_t view_call = snr02_view_scopes.empty()
                                 ? 0
                                 : snr02_view_scopes.back();
  if (target <= 0 && rebuild_after <= 0) {
    return;
  }
  const uint64_t frame = rex::perf::GetTotalCounter(
      rex::perf::CounterId::kSourceFrameCount);
  if (rebuild_after > 0 &&
      (view_filter <= 0 || view_call == uint32_t(view_filter)) &&
      frame >= uint64_t(rebuild_after) &&
      frame < 0xFFFFFFFFull && r31.u32 == 0 &&
      r30.u32 == r27.u32 + 56 &&
      r25.u32 == SnrM02ReadU32(r1.u32 + 84)) {
    const uint32_t descriptor = SnrM02ReadU32(r25.u32 + 1200);
    const uint32_t command_target =
        descriptor ? SnrM02ReadU32(descriptor + 16) & 0x1FFFFFFF : 0;
    if (command_target) {
      uint64_t empty = 0;
      if (snr02_rebuild_capture.compare_exchange_strong(
              empty, (frame << 32) | command_target,
              std::memory_order_acq_rel)) {
        snr02_rebuild_flags_address.store(r30.u32, std::memory_order_release);
        REXGPU_INFO("FH1 SNR02 rebuild capture {{\"frame\":{},"
                    "\"view_call\":{},"
                    "\"instance\":{},\"parent\":{},"
                    "\"flags_address\":{},\"mask\":{},"
                    "\"parent_flags\":{},\"state\":{},"
                    "\"descriptor\":{},\"command_target\":{},"
                    "\"descriptor_words\":[{},{},{},{},{},{},{},{}]}}",
                    frame, view_call, SnrM02ReadU32(r1.u32 + 1524), r27.u32,
                    r30.u32, r28.u32, SnrM02ReadU32(r27.u32 + 56),
                    r25.u32, descriptor, command_target,
                    SnrM02ReadU32(descriptor),
                    SnrM02ReadU32(descriptor + 4),
                    SnrM02ReadU32(descriptor + 8),
                    SnrM02ReadU32(descriptor + 12),
                    SnrM02ReadU32(descriptor + 16),
                    SnrM02ReadU32(descriptor + 20),
                    SnrM02ReadU32(descriptor + 24),
                    SnrM02ReadU32(descriptor + 28));
      }
    }
  }
  if (target <= 0) {
    return;
  }
  if (!Snr01TraceCurrentFrame()) {
    if (r31.u32 != 0 || frame >= uint64_t(target)) {
      return;
    }
    static thread_local uint64_t last_miss_bucket = uint64_t(-1);
    const uint64_t bucket = frame / 128;
    if (bucket == last_miss_bucket) {
      return;
    }
    last_miss_bucket = bucket;
  }
  REXGPU_INFO("FH1 SNR01 track rebuild gate {{\"frame\":{},"
              "\"flags_address\":{},\"parent\":{},\"mask\":{},"
              "\"parent_flags\":{},\"cached_flag\":{}}}",
              frame, r30.u32, r27.u32, r28.u32,
              SnrM02ReadU32(r27.u32 + 56), r31.u32);
}

void PinyonShiftObserveSnr02TrackRecordResource(
    PPCRegister& r4, PPCRegister& r11, PPCRegister& r27,
    PPCRegister& r30, PPCRegister& r31) {
  if (!Snr02TraceCapturedFrame() ||
      r30.u32 != snr02_rebuild_flags_address.load(std::memory_order_acquire)) {
    return;
  }
  const uint32_t index = SnrM02ReadU32(r31.u32);
  const uint32_t table = SnrM02ReadU32(r27.u32 + 16);
  REXGPU_INFO("FH1 SNR02 selected resource lookup {{\"frame\":{},"
              "\"record\":{},\"index\":{},\"table\":{},"
              "\"table_entry\":{},\"resource\":{},"
              "\"field60\":{},\"argument\":{}}}",
              rex::perf::GetTotalCounter(
                  rex::perf::CounterId::kSourceFrameCount),
              r31.u32, index, table,
              table ? SnrM02ReadU32(table + 4 * index) : 0,
              r11.u32, SnrM02ReadU32(r11.u32 + 60), r4.u32);
}

void PinyonShiftObserveSnr02TrackSelectedRecord(
    PPCRegister& r1, PPCRegister& r19, PPCRegister& r25,
    PPCRegister& r26, PPCRegister& r28, PPCRegister& r30,
    PPCRegister& r31) {
  if (!Snr01TraceCurrentFrame() && !Snr02TraceCapturedFrame()) {
    return;
  }
  const uint32_t record_root = SnrM02ReadU32(r1.u32 + 116);
  uint32_t words[14] = {};
  if (r31.u32) {
    for (uint32_t i = 0; i < 14; ++i) {
      words[i] = SnrM02ReadU32(r31.u32 + 4 * i);
    }
  }
  REXGPU_INFO("FH1 SNR01 track selected record {{\"frame\":{},"
              "\"flags_address\":{},\"container\":{},\"submodel\":{},"
              "\"entry\":{},\"entry_index\":{},"
              "\"mask\":{},\"resource_skip_flag\":{},"
              "\"range_skip_flag\":{},"
              "\"record_root\":{},\"record_base\":{},\"record\":{},"
              "\"words\":[{},{},{},{},{},{},{},{},{},{},{},{},{},{}]}}",
              rex::perf::GetTotalCounter(
                  rex::perf::CounterId::kSourceFrameCount),
              r30.u32, r19.u32, r26.u32, r25.u32,
              SnrM02ReadU32(r25.u32 + 40), r28.u32,
              (SnrM02ReadU32(r30.u32 + 8) & r28.u32) != 0,
              (SnrM02ReadU32(r30.u32 + 16) & r28.u32) != 0,
              record_root,
              SnrM02ReadU32(record_root), r31.u32,
              words[0], words[1], words[2], words[3],
              words[4], words[5], words[6], words[7],
              words[8], words[9], words[10], words[11],
              words[12], words[13]);
  if (Snr02TraceCapturedFrame() && r31.u32 &&
      r30.u32 == snr02_rebuild_flags_address.load(std::memory_order_acquire)) {
    const uint32_t start = words[10];
    const uint32_t end = words[11];
    const uint32_t count = end >= start && (end - start) % 4 == 0
                               ? (end - start) / 4
                               : 0;
    const uint32_t word140 = SnrM02ReadU32(r25.u32 + 140);
    REXGPU_INFO("FH1 SNR02 selected mesh range {{\"frame\":{},"
                "\"entry\":{},\"record\":{},\"range_start\":{},"
                "\"range_end\":{},\"range_count\":{},\"word140\":{}}}",
                rex::perf::GetTotalCounter(
                    rex::perf::CounterId::kSourceFrameCount),
                r25.u32, r31.u32, start, end, count, word140);
    if (count <= 20) {
      for (uint32_t i = 0; i < count; ++i) {
        REXGPU_INFO("FH1 SNR02 selected range word {{\"record\":{},"
                    "\"index\":{},\"value\":{}}}",
                    r31.u32, i, SnrM02ReadU32(start + 4 * i));
      }
    }
  }
}

void PinyonShiftObserveSnr01TrackModelEnd() {
  if (Snr01TraceCurrentFrame() || Snr02TraceCapturedFrame()) {
    REXGPU_INFO("FH1 SNR01 track model end {{\"frame\":{},"
                "\"scene_packets\":{}}}",
                rex::perf::GetTotalCounter(
                    rex::perf::CounterId::kSourceFrameCount),
                snr01_scene_indirect_count);
  }
}

void PinyonShiftObserveScalarDrawBegin(
    PPCRegister& r12, PPCRegister& r3, PPCRegister& r4, PPCRegister& r7,
    PPCRegister& r29) {
  if (!Snr01TraceCurrentFrame()) {
    return;
  }
  const bool outer_call = r12.u32 == 0x82443B98 ||
                          r12.u32 == 0x82443C40 ||
                          r12.u32 == 0x82444018;
  const uint32_t outer = outer_call ? r29.u32 : 0;
  const uint32_t field4 = outer ? SnrM02ReadU32(outer + 4) : 0;
  const uint32_t field12 = outer ? SnrM02ReadU32(outer + 12) : 0;
  const uint32_t field16 = outer ? SnrM02ReadU32(outer + 16) : 0;
  snr01_scalar_draw_scopes.push_back({
      uint64_t(rex::perf::GetTotalCounter(
          rex::perf::CounterId::kSourceFrameCount)),
      ++snr01_scalar_draw_count,
      snr01_view_scopes.empty() ? 0 : snr01_view_scopes.back().ordinal,
      snr01_direct_packet_count, r12.u32, r3.u32,
      SnrM02ReadU32(r3.u32), SnrM02ReadU32(r3.u32 + 20),
      outer, outer ? SnrM02ReadU32(outer) : 0,
      field4, field12, field16, SnrM02ReadU32(field4),
      SnrM02ReadU32(field12), SnrM02ReadU32(field16),
      r4.u32, r7.u32});
}

void PinyonShiftObserveSnr01GraphicsDeviceDraw(
    PPCRegister& r12, PPCRegister& r3, PPCRegister& r4,
    PPCRegister& r6, PPCRegister& r30) {
  if (!Snr01TraceCurrentFrame() || snr01_view_scopes.empty() ||
      snr01_view_scopes.back().ordinal != 8) {
    return;
  }
  REXGPU_INFO(
      "FH1 SNR01 graphics device draw {{\"frame\":{},\"view_call\":8,"
      "\"caller_lr\":{},\"device\":{},\"selector\":{},"
      "\"input_count\":{},\"caller_r30\":{},\"first_direct\":{}}}",
      rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
      r12.u32, r3.u32, r4.u32, r6.u32, r30.u32,
      snr01_direct_packet_count + 1);
}

void PinyonShiftObserveScalarDrawEnd() {
  if (snr01_scalar_draw_scopes.empty()) {
    return;
  }
  const auto scope = snr01_scalar_draw_scopes.back();
  snr01_scalar_draw_scopes.pop_back();
  if (scope.ordinal > kSnr01ProceduralLimit) {
    return;
  }
  REXGPU_INFO(
      "FH1 SNR01 scalar draw {{\"frame\":{},\"ordinal\":{},"
      "\"view_call\":{},\"caller_lr\":{},\"object\":{},"
      "\"object_first_word\":{},\"command\":{},"
      "\"outer_object\":{},\"outer_first_word\":{},"
      "\"outer_field4\":{},\"outer_field12\":{},"
      "\"outer_field16\":{},\"field4_word0\":{},"
      "\"field12_word0\":{},\"field16_word0\":{},"
      "\"selector\":{},\"input_count\":{},"
      "\"first_direct\":{},\"last_direct\":{}}}",
      scope.frame, scope.ordinal, scope.view_call, scope.caller_lr,
      scope.object, scope.object_first_word, scope.command,
      scope.outer_object, scope.outer_first_word,
      scope.outer_field4, scope.outer_field12, scope.outer_field16,
      scope.field4_word0, scope.field12_word0, scope.field16_word0,
      scope.selector,
      scope.input_count, scope.first_direct + 1, snr01_direct_packet_count);
}

void PinyonShiftObserveCarTextureResolution(
    PPCRegister& r30, PPCRegister& r31, PPCRegister& r29,
    PPCRegister& r3) {
  if (!Snr01TraceCurrentFrame() || snr01_view_scopes.empty() ||
      snr01_view_scopes.back().ordinal != 8 ||
      SnrM02ReadU32(r30.u32) != 0x8200306C) {
    return;
  }
  REXGPU_INFO(
      "FH1 SNR02 car texture resolution {{\"frame\":{},"
      "\"view_call\":8,\"device\":{},\"slot\":{},"
      "\"resource\":{},\"resolved\":{},"
      "\"descriptor_words\":[{},{},{},{},{},{}],"
      "\"next_direct\":{}}}",
      rex::perf::GetTotalCounter(
          rex::perf::CounterId::kSourceFrameCount),
      r30.u32, r31.u32, SnrM02ReadU32(r29.u32), r3.u32,
      r3.u32 ? SnrM02ReadU32(r3.u32 + 28) : 0,
      r3.u32 ? SnrM02ReadU32(r3.u32 + 32) : 0,
      r3.u32 ? SnrM02ReadU32(r3.u32 + 36) : 0,
      r3.u32 ? SnrM02ReadU32(r3.u32 + 40) : 0,
      r3.u32 ? SnrM02ReadU32(r3.u32 + 44) : 0,
      r3.u32 ? SnrM02ReadU32(r3.u32 + 48) : 0,
      snr01_direct_packet_count + 1);
}

void PinyonShiftObserveDynamicQuadEntry(PPCRegister& r3, PPCRegister& r4,
                                        uint64_t& lr) {
  if (!Snr01TraceCurrentFrame() || ++snr01_dynamic_quad_entries > 256) {
    return;
  }
  REXGPU_INFO("FH1 SNR01 dynamic quad entry {{\"frame\":{},"
              "\"view_call\":{},\"caller_lr\":{},\"device\":{},"
              "\"object\":{},\"state\":{},\"command\":{},"
              "\"records\":{},\"flags\":{}}}",
              rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
              snr01_view_scopes.empty() ? 0 : snr01_view_scopes.back().ordinal,
              uint32_t(lr), r3.u32, r4.u32, SnrM02ReadU32(r4.u32),
              SnrM02ReadU32(r4.u32 + 4), SnrM02ReadU32(r4.u32 + 8),
              SnrM02ReadU32(r4.u32 + 52));
}

void PinyonShiftObserveDynamicQuadDrawBegin(PPCRegister& r30,
                                            PPCRegister& r26,
                                            PPCRegister& r25,
                                            uint64_t& lr) {
  if (!Snr01TraceCurrentFrame()) {
    return;
  }
  snr01_dynamic_quad_scopes.push_back({
      uint64_t(rex::perf::GetTotalCounter(
          rex::perf::CounterId::kSourceFrameCount)),
      snr01_direct_packet_count,
      snr01_view_scopes.empty() ? 0 : snr01_view_scopes.back().ordinal,
      uint32_t(lr), r30.u32, r26.u32, r25.u32});
}

void PinyonShiftObserveDynamicQuadDrawEnd(PPCRegister& r19) {
  if (snr01_dynamic_quad_scopes.empty()) {
    return;
  }
  const auto scope = snr01_dynamic_quad_scopes.back();
  snr01_dynamic_quad_scopes.pop_back();
  if (++snr01_dynamic_quad_count > 256) {
    return;
  }
  REXGPU_INFO("FH1 SNR01 dynamic quad draw {{\"frame\":{},"
              "\"view_call\":{},\"callsite\":{},\"object\":{},"
              "\"records\":{},\"output\":{},\"quad_count\":{},"
              "\"first_direct\":{},\"last_direct\":{}}}",
              scope.frame, scope.view_call, scope.callsite, scope.object,
              scope.records, scope.output, r19.u32, scope.first_direct + 1,
              snr01_direct_packet_count);
}

void PinyonShiftObserveDynamicQuadParentBegin(PPCRegister& r1,
                                             PPCRegister& r31,
                                             PPCRegister& r30) {
  if (!Snr01TraceCurrentFrame()) {
    return;
  }
  snr01_dynamic_quad_parent_scopes.push_back({
      uint64_t(rex::perf::GetTotalCounter(
          rex::perf::CounterId::kSourceFrameCount)),
      snr01_direct_packet_count,
      snr01_view_scopes.empty() ? 0 : snr01_view_scopes.back().ordinal,
      r1.u32 + 128, r31.u32, r30.u32});
}

void PinyonShiftObserveDynamicQuadParentEnd() {
  if (snr01_dynamic_quad_parent_scopes.empty()) {
    return;
  }
  const auto scope = snr01_dynamic_quad_parent_scopes.back();
  snr01_dynamic_quad_parent_scopes.pop_back();
  if (scope.first_direct == snr01_direct_packet_count) {
    return;
  }
  REXGPU_INFO("FH1 SNR01 dynamic quad parent {{\"frame\":{},"
              "\"view_call\":{},\"input\":{},\"owner\":{},"
              "\"owner_first_word\":{},\"receiver\":{},"
              "\"first_direct\":{},\"last_direct\":{}}}",
              scope.frame, scope.view_call, scope.input, scope.owner,
              SnrM02ReadU32(scope.owner), scope.receiver,
              scope.first_direct + 1, snr01_direct_packet_count);
}

void PinyonShiftObserveSecondDrawBegin(
    PPCRegister& r3, PPCRegister& r4, PPCRegister& r5, PPCRegister& r6) {
  if (!Snr01TraceCurrentFrame() || snr01_track_bucket_scopes.empty()) {
    return;
  }
  const auto& bucket = snr01_track_bucket_scopes.back();
  snr01_second_draw_scopes.push_back(
      {bucket.ordinal, bucket.second_dispatch_target,
       r3.u32, r4.u32, r5.u32, r6.u32,
       bucket.bound_context, bucket.bound_slot, bucket.bound_record,
       bucket.bound_target, bucket.bound_vertex_descriptor,
       bucket.bound_vertex_address, bucket.bound_vertex_size,
       bucket.vegetation_owner, bucket.vegetation_record_offset,
       bucket.vegetation_stream_offset, bucket.vegetation_record_base,
       bucket.vegetation_selected_record,
       snr01_semantic_packet_count, snr01_direct_packet_count,
       ++snr01_second_draw_count});
}

void PinyonShiftObserveSecondStateBind(
    PPCRegister& r3, PPCRegister& r4, PPCRegister& r5,
    PPCRegister& r11) {
  if (!Snr01TraceCurrentFrame() || snr01_track_bucket_scopes.empty()) {
    return;
  }
  auto& bucket = snr01_track_bucket_scopes.back();
  bucket.bound_context = r3.u32;
  bucket.bound_slot = r4.u32;
  bucket.bound_record = r5.u32;
  bucket.bound_target = r11.u32;
  bucket.bound_vertex_descriptor = 0;
  bucket.bound_vertex_address = 0;
  bucket.bound_vertex_size = 0;
  if (r11.u32 == 0x82415CA8 && r4.u32 == 0 && r5.u32) {
    if (auto* memory = snr01_memory.load(std::memory_order_acquire)) {
      auto read = [memory](uint32_t address) {
        return rex::memory::load_and_swap<uint32_t>(memory->TranslateVirtual(address));
      };
      bucket.bound_vertex_descriptor = read(r5.u32);
      if (bucket.bound_vertex_descriptor) {
        bucket.bound_vertex_address = read(bucket.bound_vertex_descriptor + 24);
        bucket.bound_vertex_size = read(bucket.bound_vertex_descriptor + 28);
      }
    }
  }
}

void PinyonShiftObserveVegetationStateBind(
    PPCRegister& r3, PPCRegister& r4, PPCRegister& r5, PPCRegister& r11,
    PPCRegister& r23, PPCRegister& r24, PPCRegister& r26, PPCRegister& r27) {
  PinyonShiftObserveSecondStateBind(r3, r4, r5, r11);
  if (!Snr01TraceCurrentFrame() || snr01_track_bucket_scopes.empty()) {
    return;
  }
  auto& bucket = snr01_track_bucket_scopes.back();
  bucket.vegetation_owner = r23.u32;
  bucket.vegetation_record_offset = r24.u32;
  bucket.vegetation_stream_offset = r26.u32;
  bucket.vegetation_selected_record = r27.u32;
  if (auto* memory = snr01_memory.load(std::memory_order_acquire)) {
    bucket.vegetation_record_base = rex::memory::load_and_swap<uint32_t>(
        memory->TranslateVirtual(r23.u32 + 108 + r26.u32));
  }
}

void PinyonShiftObserveSecondDrawEnd() {
  if (snr01_second_draw_scopes.empty()) {
    if (Snr01TraceCurrentFrame() && !snr01_track_bucket_scopes.empty()) {
      ++snr01_second_draw_skips;
    }
    return;
  }
  const auto scope = snr01_second_draw_scopes.back();
  snr01_second_draw_scopes.pop_back();
  if (snr01_track_bucket_scopes.empty() ||
      snr01_track_bucket_scopes.back().ordinal != scope.bucket_entry) {
    ++snr01_unmatched_second_draw_exits;
  }
  if (Snr03TargetFrame() > 0 && scope.vegetation_owner &&
      uint64_t(Snr03TargetFrame()) == uint64_t(rex::perf::GetTotalCounter(
          rex::perf::CounterId::kSourceFrameCount)) &&
      !snr01_view_scopes.empty() && snr01_view_scopes.back().ordinal == 8) {
    if (scope.packet_count != 1 || !scope.packet_physical ||
        scope.bound_record != scope.vegetation_selected_record ||
        !scope.bound_vertex_descriptor || !scope.bound_vertex_address ||
        !scope.bound_vertex_size || snr03_vegetation_items.size() >= 512) {
      snr03_scene_overflow = true;
    } else {
      snr03_vegetation_items.push_back({
          scope.vegetation_owner, scope.bound_record,
          scope.bound_vertex_descriptor, scope.bound_vertex_address,
          scope.bound_vertex_size, scope.packet_physical,
          scope.bucket_entry});
    }
  }
  if (scope.ordinal <= kSnr01ProceduralLimit) {
    REXGPU_INFO(
        "FH1 SNR01 second draw call {{\"frame\":{},\"ordinal\":{},"
        "\"bucket_entry\":{},\"target\":{},\"context\":{},"
        "\"arg4\":{},\"arg5\":{},\"arg6\":{},"
        "\"bound_context\":{},\"bound_slot\":{},"
        "\"bound_record\":{},\"bound_target\":{},"
        "\"bound_vertex_descriptor\":{},\"bound_vertex_address\":{},"
        "\"bound_vertex_size\":{},"
        "\"vegetation_owner\":{},\"vegetation_record_offset\":{},"
        "\"vegetation_stream_offset\":{},\"vegetation_record_base\":{},"
        "\"vegetation_selected_record\":{},"
        "\"first_semantic\":{},\"last_semantic\":{},"
        "\"first_direct\":{},\"last_direct\":{}}}",
        rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
        scope.ordinal, scope.bucket_entry, scope.target,
        scope.context, scope.arg4, scope.arg5, scope.arg6,
        scope.bound_context, scope.bound_slot, scope.bound_record,
        scope.bound_target, scope.bound_vertex_descriptor,
        scope.bound_vertex_address, scope.bound_vertex_size,
        scope.vegetation_owner, scope.vegetation_record_offset,
        scope.vegetation_stream_offset, scope.vegetation_record_base,
        scope.vegetation_selected_record,
        scope.first_semantic_packet + 1, snr01_semantic_packet_count,
        scope.first_direct_packet + 1, snr01_direct_packet_count);
  }
}

void PinyonShiftObserveProceduralGeometrySubmit(
    PPCRegister& r3, PPCRegister& r4, PPCRegister& r5,
    PPCRegister& r6) {
  if (!Snr01TraceCurrentFrame() || snr01_procedural_scopes.empty()) {
    return;
  }
  auto& scope = snr01_procedural_scopes.back();
  scope.submit_context = r3.u32;
  scope.submit_primitive = r4.u32;
  scope.submit_arg5 = r5.u32;
  scope.submit_arg6 = r6.u32;
  scope.submit_seen = true;
}

void PinyonShiftObserveProceduralItemEnd() {
  if (!Snr01TraceCurrentFrame()) {
    return;
  }
  if (snr01_procedural_scopes.empty()) {
    ++snr01_unmatched_exits;
    return;
  }
  const auto scope = snr01_procedural_scopes.back();
  snr01_procedural_scopes.pop_back();
  const bool snapshot_view = Snr02ItemTargetFrame() > 0 &&
      rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount) ==
          uint64_t(Snr02ItemTargetFrame()) &&
      !snr01_view_scopes.empty() && snr01_view_scopes.back().ordinal == 8;
  if (snapshot_view && (scope.ordinal > 512 || !scope.descriptor_seen ||
                        !scope.runtime_seen || !scope.descriptor_address ||
                        !scope.runtime_address)) {
    snr02_item_title_rejected = true;
  }
  if (REXCVAR_GET(pinyon_shift_snr02_item_payload_probe) &&
      scope.ordinal <= 512 && scope.descriptor_seen && scope.runtime_seen &&
      scope.descriptor_address && scope.runtime_address &&
      !snr01_view_scopes.empty() && snr01_view_scopes.back().ordinal == 8) {
    std::string descriptor, runtime;
    Snr02ItemSnapshot snapshot{};
    snapshot.call = scope.ordinal;
    snapshot.packet = scope.snapshot_packet;
    snapshot.kind = scope.descriptor_kind;
    for (uint32_t word = 0; word < 23; ++word) {
      snapshot.descriptor[word] = SnrM02ReadU32(scope.descriptor_address + word * 4);
      descriptor += fmt::format("{:08X}", snapshot.descriptor[word]);
    }
    for (uint32_t word = 0; word < 17; ++word) {
      snapshot.runtime[word] = SnrM02ReadU32(scope.runtime_address + word * 4);
      runtime += fmt::format("{:08X}", snapshot.runtime[word]);
    }
    REXGPU_INFO("FH1 SNR02 item payload {{\"frame\":{},\"call\":{},"
                "\"descriptor\":{},\"runtime\":{},\"kind\":{},"
                "\"descriptor_words\":\"{}\",\"runtime_words\":\"{}\"}}",
                rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
                scope.ordinal, scope.descriptor_address, scope.runtime_address,
                scope.descriptor_kind, descriptor, runtime);
    if (snapshot_view) {
      if (!scope.submit_seen || scope.snapshot_packet_count != 1 ||
          snr02_item_title_items.size() >= 512) {
        snr02_item_title_rejected = true;
      } else {
        snr02_item_title_items.push_back(std::move(snapshot));
      }
    }
  }
  if (scope.ordinal <= kSnr01ProceduralLimit) {
    REXGPU_INFO(
        "FH1 SNR01 procedural item {{\"frame\":{},\"call\":{},"
        "\"receiver\":{},\"first_indexed_packet\":{},"
        "\"last_indexed_packet\":{},\"first_semantic_packet\":{},"
        "\"last_semantic_packet\":{},\"nested_depth\":{},"
        "\"descriptor_seen\":{},\"descriptor_index\":{},"
        "\"descriptor_address\":{},\"descriptor_kind\":{},"
        "\"render_state\":{},\"runtime_seen\":{},"
        "\"runtime_address\":{},\"submit_seen\":{},"
        "\"submit_context\":{},\"submit_primitive\":{},"
        "\"submit_arg5\":{},\"submit_arg6\":{}}}",
        rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
        scope.ordinal, scope.receiver, scope.first_packet + 1,
        snr01_packet_count, scope.first_semantic_packet + 1,
        snr01_semantic_packet_count, snr01_procedural_scopes.size(),
        scope.descriptor_seen, scope.descriptor_index,
        scope.descriptor_address, scope.descriptor_kind, scope.render_state,
        scope.runtime_seen, scope.runtime_address, scope.submit_seen,
        scope.submit_context, scope.submit_primitive,
        scope.submit_arg5, scope.submit_arg6);
  }
}

void PinyonShiftObserveSnr01SecondPathBegin(
    PPCRegister& r12, PPCRegister& r3, PPCRegister& r4,
    PPCRegister& r5, PPCRegister& r6, PPCRegister& r30) {
  if (!Snr01TraceCurrentFrame()) {
    return;
  }
  snr01_second_path_scopes.push_back({
      static_cast<uint64_t>(rex::perf::GetTotalCounter(
          rex::perf::CounterId::kSourceFrameCount)),
      ++snr01_second_path_count,
      snr01_view_scopes.empty() ? 0 : snr01_view_scopes.back().ordinal,
      snr01_semantic_packet_count, r12.u32, r3.u32, r4.u32, r5.u32,
      r6.u32, r30.u32,
      snr01_view_scopes.empty() || snr01_view_scopes.back().ordinal != 8
          ? 0 : SnrM02ReadU32(r30.u32)});
}

void PinyonShiftObserveSnr01SecondPathEnd() {
  if (snr01_second_path_scopes.empty()) {
    return;
  }
  const auto scope = snr01_second_path_scopes.back();
  snr01_second_path_scopes.pop_back();
  if (scope.ordinal > kSnr01ProceduralLimit) {
    return;
  }
  REXGPU_INFO(
      "FH1 SNR01 second path {{\"frame\":{},\"call\":{},"
      "\"view_call\":{},\"caller_lr\":{},\"context\":{},"
      "\"arg4\":{},\"arg5\":{},\"arg6\":{},"
      "\"caller_object\":{},\"caller_object_word0\":{},"
      "\"first_semantic\":{},\"last_semantic\":{}}}",
      scope.frame, scope.ordinal, scope.view_call, scope.caller_lr,
      scope.context, scope.arg4, scope.arg5, scope.arg6,
      scope.caller_object, scope.caller_object_word0,
      scope.first_semantic + 1, snr01_semantic_packet_count);
}

void PinyonShiftObserveSnr01SharedCaller(
    PPCRegister& r12, PPCRegister& r3, PPCRegister& r4,
    PPCRegister& r5, PPCRegister& r6, PPCRegister& r7) {
  if (!Snr01TraceCurrentFrame() || snr01_view_scopes.empty() ||
      snr01_view_scopes.back().ordinal != 8) {
    return;
  }
  REXGPU_INFO(
      "FH1 SNR01 shared caller {{\"frame\":{},\"view_call\":8,"
      "\"caller_lr\":{},\"parent\":{},\"parent_word0\":{},"
      "\"arg4\":{},\"arg5\":{},\"arg6\":{},\"arg7\":{}}}",
      rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
      r12.u32, r3.u32, SnrM02ReadU32(r3.u32), r4.u32, r5.u32,
      r6.u32, r7.u32);
}

void PinyonShiftObserveProceduralEmitterBegin(
    PPCRegister& r12, PPCRegister& r3, PPCRegister& r4, PPCRegister& r5,
    PPCRegister& r6) {
  if (!Snr01TraceCurrentFrame()) {
    return;
  }
  const uint64_t ordinal = ++snr01_emitter_count;
  snr01_emitter_scopes.push_back(
      {r12.u32, r3.u32, r4.u32, r5.u32, r6.u32,
       snr01_semantic_packet_count, ordinal});
}

void PinyonShiftObserveProceduralEmitterEnd() {
  if (!Snr01TraceCurrentFrame()) {
    return;
  }
  if (snr01_emitter_scopes.empty()) {
    ++snr01_unmatched_emitter_exits;
    return;
  }
  const auto scope = snr01_emitter_scopes.back();
  snr01_emitter_scopes.pop_back();
  if (scope.ordinal <= kSnr01ProceduralLimit) {
    REXGPU_INFO(
        "FH1 SNR01 emitter {{\"frame\":{},\"call\":{},"
        "\"caller_lr\":{},\"owner\":{},\"arg4\":{},"
        "\"arg5\":{},\"arg6\":{},"
        "\"first_semantic_packet\":{},\"last_semantic_packet\":{}}}",
        rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
        scope.ordinal, scope.caller_lr, scope.owner, scope.arg4,
        scope.arg5, scope.arg6, scope.first_semantic_packet + 1,
        snr01_semantic_packet_count);
  }
}

void PinyonShiftObserveProceduralDrawPacketPrimary(PPCRegister& r30,
                                                  PPCRegister& r11,
                                                  PPCRegister& r31) {
  RecordSnr01SemanticPacket("primary", r30.u32, r11.u32, r31.u32);
}

void PinyonShiftObserveProceduralDrawPacketSecondary(PPCRegister& r6,
                                                    PPCRegister& r9,
                                                    PPCRegister& r31) {
  RecordSnr01SemanticPacket("secondary", r6.u32, r9.u32, r31.u32);
}

void PinyonShiftObserveDirectIndexedBegin(
    PPCRegister& r12, PPCRegister& r3, PPCRegister& r4, PPCRegister& r5,
    PPCRegister& r6, PPCRegister& r7) {
  if (!Snr01TraceCurrentFrame()) {
    return;
  }
  const uint64_t ordinal = ++snr01_direct_call_count;
  snr01_direct_scopes.push_back(
      {r12.u32, r3.u32, r4.u32, r5.u32, r6.u32, r7.u32,
       snr01_direct_packet_count, ordinal});
}

void PinyonShiftObserveDirectIndexedPacketPrimary(
    PPCRegister& r25, PPCRegister& r11, PPCRegister& r31) {
  RecordSnr01DirectPacket("primary", r25.u32, r11.u32, r31.u32);
}

void PinyonShiftObserveDirectIndexedPacketSecondary(
    PPCRegister& r5, PPCRegister& r9, PPCRegister& r31) {
  RecordSnr01DirectPacket("secondary", r5.u32, r9.u32, r31.u32);
}

void PinyonShiftObserveDirectIndexedEnd() {
  if (!Snr01TraceCurrentFrame()) {
    return;
  }
  if (snr01_direct_scopes.empty()) {
    ++snr01_unmatched_direct_exits;
    return;
  }
  const auto scope = snr01_direct_scopes.back();
  snr01_direct_scopes.pop_back();
  if (scope.ordinal <= kSnr01ProceduralLimit) {
    REXGPU_INFO(
        "FH1 SNR01 direct call {{\"frame\":{},\"call\":{},"
        "\"caller_lr\":{},\"owner\":{},\"arg4\":{},"
        "\"arg5\":{},\"arg6\":{},\"arg7\":{},"
        "\"first_packet\":{},\"last_packet\":{}}}",
        rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
        scope.ordinal, scope.caller_lr, scope.owner, scope.arg4,
        scope.arg5, scope.arg6, scope.arg7, scope.first_packet + 1,
        snr01_direct_packet_count);
  }
}

void PinyonShiftObserveIndexed2PacketPrimary(PPCRegister& r30,
                                             PPCRegister& r11,
                                             PPCRegister& r31) {
  RecordSnr01DirectPacket("indexed2_primary", r30.u32, r11.u32, r31.u32);
}

void PinyonShiftObserveIndexed2Begin(PPCRegister& r12) {
  if (Snr01TraceCurrentFrame()) {
    snr01_indexed2_callers.push_back(r12.u32);
  }
}

void PinyonShiftObserveIndexed2End() {
  if (!snr01_indexed2_callers.empty()) {
    snr01_indexed2_callers.pop_back();
  }
}

void PinyonShiftObserveIndexed2Owner(PPCRegister& r12, PPCRegister& r3,
                                     PPCRegister& r4, PPCRegister& r5,
                                     PPCRegister& r7, PPCRegister& r8) {
  if (!Snr01TraceCurrentFrame() || r7.u32 != 4 ||
      snr01_view_scopes.empty() || snr01_view_scopes.back().ordinal != 8 ||
      ++snr01_indexed2_owner_count > 256) {
    return;
  }
  uint32_t receiver_word0 = 0;
  if (auto* memory = snr01_memory.load(std::memory_order_acquire)) {
    if (r3.u32) {
      receiver_word0 = rex::memory::load_and_swap<uint32_t>(
          memory->TranslateVirtual(r3.u32));
    }
  }
  std::string quad_words;
  for (uint32_t i = 0; i < 16; ++i) {
    if (i) quad_words += ',';
    quad_words += std::to_string(SnrM02ReadU32(r8.u32 + i * 4));
  }
  REXGPU_INFO(
      "FH1 SNR01 indexed2 owner {{\"frame\":{},\"ordinal\":{},"
      "\"caller_lr\":{},\"receiver\":{},\"receiver_word0\":{},"
      "\"arg4\":{},\"arg5\":{},\"arg7\":{},\"arg8\":{},"
      "\"arg8_word0\":{},\"quad_count\":{},\"quad_words\":[{}],"
      "\"view_call\":{}}}",
      rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
      snr01_indexed2_owner_count, r12.u32, r3.u32, receiver_word0, r4.u32,
      r5.u32, r7.u32, r8.u32, SnrM02ReadU32(r8.u32),
      SnrM02ReadU32(r8.u32 + 400), quad_words,
      snr01_view_scopes.empty() ? 0 : snr01_view_scopes.back().ordinal);
}

void PinyonShiftObserveQueuedIndirectBegin(
    PPCRegister& r12, PPCRegister&, PPCRegister&, PPCRegister&, PPCRegister&,
    PPCRegister&, PPCRegister&, PPCRegister&) {
  if (Snr01TraceLinkedWriteFrame()) {
    snr01_queued_indirect_callers.push_back(r12.u32);
  }
}

void PinyonShiftObserveQueuedIndirectEnd() {
  if (!snr01_queued_indirect_callers.empty()) {
    snr01_queued_indirect_callers.pop_back();
  }
}

void PinyonShiftObserveDeferredWorkerBegin(PPCRegister& r3,
                                           PPCRegister& r4) {
  if (!Snr01TracePrimaryIndirectFrame()) {
    return;
  }
  snr01_worker_scopes.push_back(
      {r3.u32, r4.u32, snr01_primary_indirect_packet_count});
  REXGPU_INFO(
      "FH1 SNR01 deferred worker begin {{\"frame\":{},"
      "\"stream\":{},\"queue\":{},\"first_packet\":{}}}",
      rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
      r3.u32, r4.u32, snr01_primary_indirect_packet_count + 1);
}

void PinyonShiftObserveDeferredWorkerEnd() {
  if (snr01_worker_scopes.empty()) {
    return;
  }
  const auto scope = snr01_worker_scopes.back();
  snr01_worker_scopes.pop_back();
  REXGPU_INFO(
      "FH1 SNR01 deferred worker end {{\"frame\":{},"
      "\"stream\":{},\"queue\":{},"
      "\"first_packet\":{},\"last_packet\":{}}}",
      rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
      scope.stream, scope.queue, scope.first_packet + 1,
      snr01_primary_indirect_packet_count);
}

void PinyonShiftObserveDeferredIndirectCommandBegin(PPCRegister& r31,
                                                    PPCRegister& r10,
                                                    PPCRegister& r11) {
  if (!Snr01TracePrimaryIndirectFrame()) {
    return;
  }
  snr01_deferred_indirect_commands.push_back(r31.u32);
  REXGPU_INFO(
      "FH1 SNR01 deferred indirect command {{\"frame\":{},"
      "\"command_guest\":{},\"command_physical\":{},"
      "\"opcode\":{},\"payload\":{},\"worker_stream\":{}}}",
      rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
      r31.u32, r31.u32 & 0x1FFFFFFF, r10.u32, r11.u32,
      snr01_worker_scopes.empty() ? 0 : snr01_worker_scopes.back().stream);
}

void PinyonShiftObserveDeferredIndirectCommandEnd() {
  if (!snr01_deferred_indirect_commands.empty()) {
    snr01_deferred_indirect_commands.pop_back();
  }
}

void PinyonShiftObserveLinkedIndirectWrite(
    PPCRegister& r29, PPCRegister& r11, PPCRegister& r30, PPCRegister& r27,
    PPCRegister& r25, PPCRegister& r31) {
  const uint64_t frame = rex::perf::GetTotalCounter(
      rex::perf::CounterId::kSourceFrameCount);
  if (!Snr01TraceLinkedWriteFrame()) {
    return;
  }
  REXGPU_INFO(
      "FH1 SNR01 linked indirect write {{\"frame\":{},\"block\":{},"
      "\"opcode_address\":{},\"opcode\":{},\"payload\":{},"
      "\"buffer\":{},\"device\":{},\"caller_lr\":{},"
      "\"view_call\":{},\"view\":{}}}",
      frame, r29.u32, r29.u32 + 4, r11.u32 | r30.u32, r27.u32,
      r25.u32, r31.u32,
      snr01_queued_indirect_callers.empty()
          ? 0
          : snr01_queued_indirect_callers.back(),
      snr01_view_scopes.empty() ? 0 : snr01_view_scopes.back().ordinal,
      snr01_view_scopes.empty() ? 0 : snr01_view_scopes.back().view);
}

void PinyonShiftObserveInlineIndirectBegin(PPCRegister& r12) {
  if (Snr01TraceLinkedWriteFrame()) {
    snr01_inline_indirect_callers.push_back(r12.u32);
  }
}

void PinyonShiftObserveCommandRefillBegin(PPCRegister& r12) {
  if (Snr01TraceCurrentFrame()) {
    snr01_command_refill_callers.push_back(r12.u32);
  }
}

void PinyonShiftObserveCommandRefillEnd() {
  if (!snr01_command_refill_callers.empty()) {
    snr01_command_refill_callers.pop_back();
  }
}

void PinyonShiftObserveRenderRequestBegin(PPCRegister& r12) {
  if (Snr01TraceCurrentFrame()) {
    snr01_render_request_callers.push_back(r12.u32);
  }
}

void PinyonShiftObserveRenderThreadRequestBegin(
    PPCRegister& r3, PPCRegister& r4, PPCRegister& r5) {
  if (!Snr01TraceCurrentFrame()) {
    return;
  }
  const uint64_t ordinal = ++snr01_render_thread_request_count;
  snr01_render_thread_requests.push_back(
      {ordinal, r3.u32, r4.u32, r5.u32, snr01_view_begin_count});
  REXGPU_INFO("FH1 SNR01 render thread request begin {{\"frame\":{},"
              "\"ordinal\":{},\"object\":{},\"mode\":{},"
              "\"request\":{},\"first_view\":{}}}",
              rex::perf::GetTotalCounter(
                  rex::perf::CounterId::kSourceFrameCount),
              ordinal, r3.u32, r4.u32, r5.u32, snr01_view_begin_count + 1);
}

void PinyonShiftObserveRenderThreadRequestEnd() {
  if (snr01_render_thread_requests.empty()) {
    return;
  }
  const auto request = snr01_render_thread_requests.back();
  snr01_render_thread_requests.pop_back();
  REXGPU_INFO("FH1 SNR01 render thread request end {{\"frame\":{},"
              "\"ordinal\":{},\"object\":{},\"mode\":{},"
              "\"request\":{},\"first_view\":{},\"last_view\":{}}}",
              rex::perf::GetTotalCounter(
                  rex::perf::CounterId::kSourceFrameCount),
              request.ordinal, request.object, request.mode, request.request,
              request.first_view + 1, snr01_view_begin_count);
}

void PinyonShiftObserveRenderRequestEnd() {
  if (!snr01_render_request_callers.empty()) {
    snr01_render_request_callers.pop_back();
  }
}

void PinyonShiftObserveInlineIndirectCachedWrite(
    PPCRegister& r3, PPCRegister& r9, PPCRegister& r11, PPCRegister& r31) {
  if (!Snr01TraceLinkedWriteFrame()) {
    return;
  }
  REXGPU_INFO(
      "FH1 SNR01 inline indirect write {{\"frame\":{},\"path\":0,"
      "\"command_guest\":{},\"command_physical\":{},"
      "\"opcode\":{},\"payload\":{},\"device\":{},"
      "\"caller_lr\":{},\"refill_caller_lr\":{},"
      "\"request_caller_lr\":{},"
      "\"view_call\":{},\"view\":{}}}",
      rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
      r3.u32, r3.u32 & 0x1FFFFFFF, r9.u32, r11.u32, r31.u32,
      snr01_inline_indirect_callers.empty()
          ? 0
          : snr01_inline_indirect_callers.back(),
      snr01_command_refill_callers.empty()
          ? 0
          : snr01_command_refill_callers.back(),
      snr01_render_request_callers.empty()
          ? 0
          : snr01_render_request_callers.back(),
      snr01_view_scopes.empty() ? 0 : snr01_view_scopes.back().ordinal,
      snr01_view_scopes.empty() ? 0 : snr01_view_scopes.back().view);
}

void PinyonShiftObserveInlineIndirectStreamWrite(
    PPCRegister& r11, PPCRegister& r30, PPCRegister& r29, PPCRegister& r31) {
  if (!Snr01TraceLinkedWriteFrame()) {
    return;
  }
  REXGPU_INFO(
      "FH1 SNR01 inline indirect write {{\"frame\":{},\"path\":1,"
      "\"command_guest\":{},\"command_physical\":{},"
      "\"opcode\":{},\"payload\":{},\"device\":{},"
      "\"caller_lr\":{},\"refill_caller_lr\":{},"
      "\"request_caller_lr\":{},"
      "\"view_call\":{},\"view\":{}}}",
      rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
      r11.u32, r11.u32 & 0x1FFFFFFF, r30.u32 | 0x81000000, r29.u32,
      r31.u32, snr01_inline_indirect_callers.empty()
                   ? 0
                   : snr01_inline_indirect_callers.back(),
      snr01_command_refill_callers.empty()
          ? 0
          : snr01_command_refill_callers.back(),
      snr01_render_request_callers.empty()
          ? 0
          : snr01_render_request_callers.back(),
      snr01_view_scopes.empty() ? 0 : snr01_view_scopes.back().ordinal,
      snr01_view_scopes.empty() ? 0 : snr01_view_scopes.back().view);
}

void PinyonShiftObserveInlineIndirectEnd() {
  if (!snr01_inline_indirect_callers.empty()) {
    snr01_inline_indirect_callers.pop_back();
  }
}

void PinyonShiftObservePrimaryIndirectBegin(PPCRegister& r12, PPCRegister&,
                                           PPCRegister&, PPCRegister&) {
  if (Snr01TracePrimaryIndirectFrame()) {
    snr01_primary_indirect_callers.push_back(r12.u32);
  }
}

void PinyonShiftObservePrimaryIndirectPacket(
    PPCRegister& r10, PPCRegister& r11, PPCRegister& r28, PPCRegister& r29,
    PPCRegister& r31, PPCRegister& r27, PPCRegister& r24, PPCRegister& r25,
    PPCRegister& r26, PPCRegister& r21) {
  if (!Snr01TracePrimaryIndirectFrame()) {
    return;
  }
  const uint64_t ordinal = ++snr01_primary_indirect_packet_count;
  if (ordinal > kSnr01PacketLimit) {
    return;
  }
  const uint32_t guest_address = r28.u32 + r11.u32 * sizeof(uint32_t);
  REXGPU_INFO(
      "FH1 SNR01 primary indirect packet {{\"frame\":{},\"ordinal\":{},"
      "\"header_physical\":{},\"header_word\":{},\"gpu_target\":{},"
      "\"device\":{},\"entry_array\":{},\"entry_count\":{},"
      "\"entry_index\":{},\"ring_mask\":{},\"mode\":{},"
      "\"caller_lr\":{},\"queued_caller_lr\":{},"
      "\"worker_stream\":{},\"worker_queue\":{},"
      "\"worker_command_physical\":{}}}",
      rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
      ordinal, guest_address & 0x1FFFFFFF, r10.u32, r31.u32, r27.u32,
      r24.u32, r25.u32, r26.u32, r29.u32, r21.u32,
      snr01_primary_indirect_callers.empty()
          ? 0
          : snr01_primary_indirect_callers.back(),
      snr01_queued_indirect_callers.empty()
          ? 0
          : snr01_queued_indirect_callers.back(),
      snr01_worker_scopes.empty() ? 0 : snr01_worker_scopes.back().stream,
      snr01_worker_scopes.empty() ? 0 : snr01_worker_scopes.back().queue,
      snr01_deferred_indirect_commands.empty()
          ? 0
          : snr01_deferred_indirect_commands.back() & 0x1FFFFFFF);
}

void PinyonShiftObservePrimaryIndirectEnd() {
  if (!snr01_primary_indirect_callers.empty()) {
    snr01_primary_indirect_callers.pop_back();
  }
}

void PinyonShiftObserveIndexed2PacketSecondary(PPCRegister& r6,
                                               PPCRegister& r9,
                                               PPCRegister& r31) {
  RecordSnr01DirectPacket("indexed2_secondary", r6.u32, r9.u32, r31.u32);
}

void PinyonShiftObserveIndexed3PacketPrimary(PPCRegister& r30,
                                             PPCRegister& r11,
                                             PPCRegister& r31) {
  RecordSnr01DirectPacket("indexed3_primary", r30.u32, r11.u32, r31.u32);
}

void PinyonShiftObserveIndexed3PacketSecondary(PPCRegister& r5,
                                               PPCRegister& r9,
                                               PPCRegister& r31) {
  RecordSnr01DirectPacket("indexed3_secondary", r5.u32, r9.u32, r31.u32);
}

void PinyonShiftObserveSwapDrawPacket(PPCRegister& r9, PPCRegister& r10,
                                      PPCRegister& r31) {
  RecordSnr01DirectPacket("swap", r9.u32, r10.u32, r31.u32);
}

// Read-only hooks at the checked producer entry/common epilogue. Logging is
// outside the measured interval. Nested calls are explicit because their
// observation overhead is included in the parent's elapsed wall time.
void PinyonShiftObserveClearProducerBegin(PPCRegister& r3, PPCRegister& r4,
                                         PPCRegister& r5, PPCRegister& r6,
                                         PPCRegister& r8, PPCRegister& r1,
                                         PPCRegister& f1) {
  if (!ClearProducerTraceEnabled()) {
    return;
  }
  if (!clear_producers.empty()) {
    clear_producers.back().nested = true;
  }
  ClearProducerSample sample{r3.u32, r4.u32, r5.u32, r6.u32, r8.u32, r1.u32,
                             f1.f64, static_cast<uint64_t>(rex::perf::GetTotalCounter(
                                         rex::perf::CounterId::kSourceFrameCount))};
  clear_producers.push_back(sample);
  clear_producers.back().command_cursor_before = SnrM02ReadU32(sample.device + 48);
  clear_producers.back().begin = ClearClock::now();
}

void PinyonShiftObserveClearShaderCopy(PPCRegister& r3, PPCRegister& r4,
                                      PPCRegister& r5) {
  if (!ClearProducerTraceEnabled() || clear_producers.empty()) {
    return;
  }
  auto& sample = clear_producers.back();
  if (!sample.shader_copies) {
    sample.first_shader_source = r4.u32;
    sample.first_shader_destination = r3.u32;
  }
  ++sample.shader_copies;
  sample.shader_bytes += r5.u32;
}

void PinyonShiftObserveClearCommandRefill() {
  if (ClearProducerTraceEnabled() && !clear_producers.empty()) {
    ++clear_producers.back().refills;
  }
}

void PinyonShiftObserveClearProducerEnd(PPCRegister& r31, PPCRegister& r1) {
  if (!ClearProducerTraceEnabled()) {
    return;
  }
  const auto end = ClearClock::now();
  const auto record = clear_producer_records.fetch_add(1, std::memory_order_relaxed);
  // ponytail: cap verbose records at 100,000; use aggregates for longer traces.
  if (clear_producers.empty() || clear_producers.back().device != r31.u32 ||
      clear_producers.back().stack != r1.u32 + 256) {
    clear_producers.clear();
    if (record < 100000) {
      REXGPU_INFO("FH1 clear producer unmatched end device={} stack={}",
                  r31.u32, r1.u32);
    }
    return;
  }
  const auto sample = clear_producers.back();
  clear_producers.pop_back();
  if (record >= 100000) {
    if (record == 100000) {
      REXGPU_INFO("FH1 clear producer record limit reached");
    }
    return;
  }
  REXGPU_INFO(
      "FH1 clear producer {{\"record\":{},\"thread\":{},\"frame\":{},"
      "\"device\":{},\"flags\":{},\"rectangle\":{},\"colour\":{},"
      "\"stencil\":{},\"depth\":{},\"elapsed_ns\":{},\"shader_copies\":{},"
      "\"shader_bytes\":{},\"first_shader_source\":{},"
      "\"first_shader_destination\":{},\"refills\":{},\"nested\":{},"
      "\"command_cursor_before\":{},\"command_cursor_after\":{}}}",
      record, std::hash<std::thread::id>{}(std::this_thread::get_id()), sample.frame,
      sample.device, sample.flags, sample.rectangle, sample.colour, sample.stencil,
      sample.depth, std::chrono::duration_cast<std::chrono::nanoseconds>(end - sample.begin).count(),
      sample.shader_copies, sample.shader_bytes, sample.first_shader_source,
      sample.first_shader_destination, sample.refills, sample.nested,
      sample.command_cursor_before, SnrM02ReadU32(sample.device + 48));
}

void PinyonShiftObserveSceneListFlushBegin(
    PPCRegister& r12, PPCRegister& r31, PPCRegister& r30,
    PPCRegister& r27, PPCRegister& r28, PPCRegister& r5) {
  if (Snr01TraceCurrentFrame()) {
    const uint32_t list_owner = r12.u32 == 0x8244CBF4 ? r28.u32 :
                                r12.u32 == 0x8244DD5C ||
                                        r12.u32 == 0x8244E2A8
                                    ? r27.u32
                                    : 0;
    const uint32_t owner =
        list_owner && SnrM02ReadU32(list_owner + 32860) == r5.u32
            ? list_owner
            : r12.u32 == 0x8241A2A4 ? r30.u32 :
                           r12.u32 == 0x824399F0 ||
                                   r12.u32 == 0x8243CE0C ||
                                   r12.u32 == 0x824170BC
                               ? r31.u32
                               : 0;
    snr01_scene_list_flushes.push_back({
        r12.u32, owner, owner ? SnrM02ReadU32(owner) : 0, r5.u32,
        snr01_car_owner_call.owner == owner ? snr01_car_owner_call.ordinal : 0,
        snr01_car_owner_call.owner == owner
            ? snr01_car_owner_call.caller_lr
            : 0,
        snr01_car_owner_call.owner == owner ? snr01_car_owner_call.args
                                            : std::array<uint32_t, 7>{}});
  }
}

void PinyonShiftObserveSceneListFlushEnd() {
  if (!snr01_scene_list_flushes.empty()) {
    snr01_scene_list_flushes.pop_back();
  }
}

void PinyonShiftObserveSnr01CarOwnerCall(
    PPCRegister& r12, PPCRegister& r3, PPCRegister& r4, PPCRegister& r5,
    PPCRegister& r6, PPCRegister& r7, PPCRegister& r8, PPCRegister& r9,
    PPCRegister& r10) {
  if (Snr01TraceCurrentFrame()) {
    snr01_car_owner_call = {
        ++snr01_car_owner_call_count, r3.u32, r12.u32,
        {r4.u32, r5.u32, r6.u32, r7.u32, r8.u32, r9.u32, r10.u32}};
    REXGPU_INFO(
        "FH1 SNR01 car owner call {{\"frame\":{},\"call\":{},"
        "\"owner\":{},\"owner_first_word\":{},\"caller_lr\":{},"
        "\"owner_args\":[{},{},{},{},{},{},{}],\"view_call\":{}}}",
        rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
        snr01_car_owner_call.ordinal, r3.u32, SnrM02ReadU32(r3.u32), r12.u32,
        r4.u32, r5.u32, r6.u32, r7.u32, r8.u32, r9.u32, r10.u32,
        snr01_view_scopes.empty() ? 0 : snr01_view_scopes.back().ordinal);
    if (SnrM02ReadU32(r3.u32) == 0x82001618) {
      REXGPU_INFO(
          "FH1 SNR02 car model inputs {{\"frame\":{},\"call\":{},"
          "\"model\":{},\"direct_list\":{},\"slot_lists\":[{},{},{},{}],"
          "\"view_call\":{}}}",
          rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
          snr01_car_owner_call.ordinal, r3.u32, SnrM02ReadU32(r3.u32 + 32860),
          SnrM02ReadU32(r3.u32 + 12752), SnrM02ReadU32(r3.u32 + 12756),
          SnrM02ReadU32(r3.u32 + 12760), SnrM02ReadU32(r3.u32 + 12764),
          snr01_view_scopes.empty() ? 0 : snr01_view_scopes.back().ordinal);
    }
  }
}

void PinyonShiftObserveSnr01CarOwnerSelection(PPCRegister& r3) {
  if (Snr01TraceCurrentFrame()) {
    REXGPU_INFO(
        "FH1 SNR01 car owner selection {{\"frame\":{},\"call\":{},"
        "\"owner\":{},\"selected_list\":{},\"view_call\":{}}}",
        rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
        snr01_car_owner_call.ordinal, snr01_car_owner_call.owner, r3.u32,
        snr01_view_scopes.empty() ? 0 : snr01_view_scopes.back().ordinal);
  }
}

void PinyonShiftObserveSnr02CarModelRecord(PPCRegister& r3) {
  if (Snr01TraceCurrentFrame()) {
    const uint32_t binding = SnrM02ReadU32(r3.u32 + 356);
    REXGPU_INFO(
        "FH1 SNR02 car model record {{\"frame\":{},\"call\":{},"
        "\"owner\":{},\"record\":{},\"record_first_word\":{},"
        "\"dynamic\":{},\"binding\":{},\"binding_first_word\":{},"
        "\"binding_words\":[{},{},{},{},{},{},{},{}],"
        "\"view_call\":{}}}",
        rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
        snr01_car_owner_call.ordinal, snr01_car_owner_call.owner, r3.u32,
        SnrM02ReadU32(r3.u32), SnrM02ReadU32(r3.u32 + 352), binding,
        SnrM02ReadU32(binding), SnrM02ReadU32(binding),
        SnrM02ReadU32(binding + 4), SnrM02ReadU32(binding + 8),
        SnrM02ReadU32(binding + 12), SnrM02ReadU32(binding + 16),
        SnrM02ReadU32(binding + 20), SnrM02ReadU32(binding + 24),
        SnrM02ReadU32(binding + 28),
        snr01_view_scopes.empty() ? 0 : snr01_view_scopes.back().ordinal);
  }
}

void PinyonShiftObserveSnr02CarMatrixBegin(PPCRegister& r6) {
  if (Snr01TraceCurrentFrame()) {
    snr02_car_matrix_record = r6.u32;
  }
}

void PinyonShiftObserveSnr02CarMatrixInput(PPCRegister& r3, PPCRegister& r4,
                                            PPCRegister& r5) {
  if (!Snr01TraceCurrentFrame() ||
      snr02_car_matrices.fetch_add(1) >= 512) {
    return;
  }
  const uint32_t matrix = r3.u32;
  REXGPU_INFO(
      "FH1 SNR02 car matrix input {{\"frame\":{},\"call\":{},"
      "\"owner\":{},\"record\":{},\"matrix\":{},\"render_state\":{},"
      "\"flags\":{},\"words\":[{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{}],"
      "\"view_call\":{}}}",
      rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
      snr01_car_owner_call.ordinal, snr01_car_owner_call.owner,
      snr02_car_matrix_record, matrix, r4.u32, r5.u32,
      SnrM02ReadU32(matrix), SnrM02ReadU32(matrix + 4),
      SnrM02ReadU32(matrix + 8), SnrM02ReadU32(matrix + 12),
      SnrM02ReadU32(matrix + 16), SnrM02ReadU32(matrix + 20),
      SnrM02ReadU32(matrix + 24), SnrM02ReadU32(matrix + 28),
      SnrM02ReadU32(matrix + 32), SnrM02ReadU32(matrix + 36),
      SnrM02ReadU32(matrix + 40), SnrM02ReadU32(matrix + 44),
      SnrM02ReadU32(matrix + 48), SnrM02ReadU32(matrix + 52),
      SnrM02ReadU32(matrix + 56), SnrM02ReadU32(matrix + 60),
      snr01_view_scopes.empty() ? 0 : snr01_view_scopes.back().ordinal);
}

void PinyonShiftObserveSnr01DirectFamilyBegin(
    PPCRegister& r3, PPCRegister& r4, PPCRegister& r5, PPCRegister& r6,
    PPCRegister& r7, PPCRegister& r8) {
  if (!Snr01TraceCurrentFrame()) {
    return;
  }
  snr01_direct_family_scopes.push_back({
      static_cast<uint64_t>(rex::perf::GetTotalCounter(
          rex::perf::CounterId::kSourceFrameCount)),
      ++snr01_direct_family_count,
      snr01_view_scopes.empty() ? 0 : snr01_view_scopes.back().ordinal,
      snr01_direct_packet_count,
      r3.u32, r4.u32, r5.u32, r6.u32, r7.u32, r8.u32});
}

void PinyonShiftObserveSnr01DirectFamilyEnd() {
  if (snr01_direct_family_scopes.empty()) {
    return;
  }
  const auto scope = snr01_direct_family_scopes.back();
  snr01_direct_family_scopes.pop_back();
  if (scope.ordinal > 512) {
    return;
  }
  REXGPU_INFO(
      "FH1 SNR01 direct family {{\"frame\":{},\"call\":{},"
      "\"view_call\":{},\"context\":{},\"context_word\":{},"
      "\"device\":{},\"device_word\":{},\"object\":{},"
      "\"object_word\":{},\"list\":{},\"list_word\":{},"
      "\"arg7\":{},\"arg8\":{},\"mode\":{},"
      "\"first_direct\":{},\"last_direct\":{}}}",
      scope.frame, scope.ordinal, scope.view_call,
      scope.context, SnrM02ReadU32(scope.context),
      scope.device, SnrM02ReadU32(scope.device),
      scope.object, SnrM02ReadU32(scope.object),
      scope.list, SnrM02ReadU32(scope.list),
      scope.arg7, scope.arg8,
      scope.object ? SnrM02ReadU32(scope.object + 448) : 0,
      scope.first_direct + 1, snr01_direct_packet_count);
}

void PinyonShiftObserveSnr01DirectFamilyRecord(
    PPCRegister& r29, PPCRegister& r27, PPCRegister& r30,
    PPCRegister& r31, PPCRegister& r6, PPCRegister& r7) {
  if (!Snr01TraceCurrentFrame() || snr01_direct_family_scopes.empty() ||
      ++snr01_direct_family_record_count > 512) {
    return;
  }
  const auto& scope = snr01_direct_family_scopes.back();
  REXGPU_INFO(
      "FH1 SNR01 direct family record {{\"frame\":{},\"family_call\":{},"
      "\"view_call\":{},\"next_direct\":{},\"record\":{},"
      "\"record_words\":[{},{},{},{}],\"source\":{},"
      "\"source_words\":[{},{},{}],\"context\":{},"
      "\"device\":{},\"arg6\":{},\"arg7\":{}}}",
      scope.frame, scope.ordinal, scope.view_call,
      snr01_direct_packet_count + 1, r29.u32,
      SnrM02ReadU32(r29.u32), SnrM02ReadU32(r29.u32 + 4),
      SnrM02ReadU32(r29.u32 + 8), SnrM02ReadU32(r29.u32 + 16),
      r27.u32, SnrM02ReadU32(r27.u32),
      SnrM02ReadU32(r27.u32 + 12), SnrM02ReadU32(r27.u32 + 20),
      r30.u32, r31.u32, r6.u32, r7.u32);
}

void PinyonShiftObserveSnr02CarDescriptor(
    PPCRegister& presentation, PPCRegister& header, PPCRegister& entry,
    PPCRegister& selector, PPCRegister& list) {
  if (Snr01TraceCurrentFrame()) {
    const uint32_t table = SnrM02ReadU32(presentation.u32 + 6044);
    const uint32_t table_owner = SnrM02ReadU32(table);
    REXGPU_INFO(
        "FH1 SNR02 car descriptor {{\"frame\":{},\"next_call\":{},"
        "\"presentation\":{},\"table_root\":{},"
        "\"table_first_word\":{},\"table_owner_first_word\":{},"
        "\"header\":{},"
        "\"header_begin\":{},\"header_end\":{},\"entry\":{},"
        "\"selector\":{},\"entry_words\":[{},{},{}],"
        "\"list\":{},\"list_first_word\":{},\"view_call\":{}}}",
        rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
        snr01_car_owner_call_count + 1, presentation.u32, table,
        table_owner, SnrM02ReadU32(table_owner), header.u32,
        SnrM02ReadU32(header.u32), SnrM02ReadU32(header.u32 + 4),
        entry.u32, selector.u32, SnrM02ReadU32(entry.u32),
        SnrM02ReadU32(entry.u32 + 4), SnrM02ReadU32(entry.u32 + 8),
        list.u32, SnrM02ReadU32(list.u32),
        snr01_view_scopes.empty() ? 0 : snr01_view_scopes.back().ordinal);
  }
}

void PinyonShiftObserveSnr02VehicleMaterialBinding(
    PPCRegister& caller, PPCRegister& root, PPCRegister& binding,
    PPCRegister& load_ui, PPCRegister& slod) {
  if (REXCVAR_GET(pinyon_shift_snr01_trace_source_frame) <= 0 ||
      snr02_vehicle_material_bindings.fetch_add(1) >= 512) {
    return;
  }
  REXGPU_INFO(
      "FH1 SNR02 vehicle material binding {{\"frame\":{},"
      "\"caller\":{},\"root\":{},\"root_first_word\":{},"
      "\"binding\":{},\"binding_offset\":{},"
      "\"load_ui\":{},\"slod\":{}}}",
      rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
      caller.u32, root.u32, SnrM02ReadU32(root.u32), binding.u32,
      binding.u32 - root.u32, load_ui.u32, slod.u32);
}

void PinyonShiftObserveSnr01VehiclePoseOwner(PPCRegister& r30,
                                              PPCRegister& r31) {
  if (Snr01TraceCurrentFrame()) {
    REXGPU_INFO("FH1 SNR01 vehicle pose owner {{\"frame\":{},\"source\":{},"
                "\"owner\":{},\"owner_first_word\":{}}}",
                rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
                r30.u32, r31.u32, SnrM02ReadU32(r31.u32));
  }
}

void PinyonShiftObserveSnr01VehicleMapPoolInstalled(PPCRegister& r3,
                                                     PPCRegister& r31) {
  if (REXCVAR_GET(pinyon_shift_snr01_trace_source_frame) <= 0) {
    return;
  }
  snr01_vehicle_map_pool_root.store(r3.u32, std::memory_order_release);
  REXGPU_INFO("FH1 SNR01 vehicle map pool {{\"frame\":{},"
              "\"installer\":{},\"pool\":{},\"player_entity\":{},"
              "\"player_vtable\":{},\"player_vehicle_id\":{}}}",
              rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
              r31.u32, r3.u32, r3.u32 ? r3.u32 + 32 : 0,
              r3.u32 ? SnrM02ReadU32(r3.u32 + 32) : 0,
              r3.u32 ? SnrM02ReadU32(r3.u32 + 44) : 0);
}

void PinyonShiftObserveSnr01VehicleIdAssigned(PPCRegister& r3,
                                               PPCRegister& r4) {
  const uint32_t root = snr01_vehicle_map_pool_root.load(
      std::memory_order_acquire);
  if (root && r3.u32 == root + 32) {
    REXGPU_INFO("FH1 SNR01 player vehicle ID assigned {{\"frame\":{},"
                "\"entity\":{},\"vehicle_id\":{}}}",
                rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
                r3.u32, r4.u32);
  }
}

void PinyonShiftObserveSnr01ForzaPlayerConstructed(PPCRegister& r3) {
  if (REXCVAR_GET(pinyon_shift_snr01_trace_source_frame) > 0) {
    std::lock_guard lock(snr01_player_mutex);
    if (snr01_forza_players.size() < 32) {
      snr01_forza_players.insert(r3.u32);
    }
  }
}

void PinyonShiftObserveSnr01CarPresentationConstructed(PPCRegister& r3,
                                                       PPCRegister& r4) {
  if (REXCVAR_GET(pinyon_shift_snr01_trace_source_frame) > 0) {
    std::lock_guard lock(snr01_player_mutex);
    if (snr01_car_presentations.size() < 64) {
      snr01_car_presentations.emplace(r3.u32, r4.u32);
    }
  }
}

void PinyonShiftObserveSceneCommandBufferBegin(
    PPCRegister& r12, PPCRegister& r3, PPCRegister& r4, PPCRegister& r5) {
  if (Snr01TraceCurrentFrame()) {
    snr01_scene_indirect_callers.push_back(r12.u32);
    REXGPU_INFO("FH1 SNR01 scene indirect scope {{\"frame\":{},"
                "\"caller_lr\":{},\"device\":{},\"list_object\":{},"
                "\"arg5\":{},\"view_call\":{}}}",
                rex::perf::GetTotalCounter(
                    rex::perf::CounterId::kSourceFrameCount),
                r12.u32, r3.u32, r4.u32, r5.u32,
                snr01_view_scopes.empty() ? 0 : snr01_view_scopes.back().ordinal);
  }
}

void PinyonShiftObserveSceneCommandBufferEnd() {
  if (!snr01_scene_indirect_callers.empty()) {
    snr01_scene_indirect_callers.pop_back();
  }
}

void PinyonShiftObserveSceneCommandBuffer(PPCRegister& r24, PPCRegister& r10,
                                         PPCRegister& r11, PPCRegister& r30,
                                         PPCRegister& r28, PPCRegister& r29) {
  if (Snr01TraceCurrentFrame() &&
      ++snr01_scene_indirect_count <= kSnr01PacketLimit) {
    if (Snr02TrackTargetFrame() > 0 &&
        uint64_t(Snr02TrackTargetFrame()) ==
            rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount) &&
        !snr01_view_scopes.empty() && snr01_view_scopes.back().ordinal == 8 &&
        !snr01_scene_list_flushes.empty() &&
        snr01_scene_list_flushes.back().caller == 0x824170BC && r10.u32) {
      std::lock_guard lock(snr02_track_targets_mutex);
      const uint32_t target = r10.u32 & 0x1FFFFFFF;
      if (snr02_track_targets.size() == 256 &&
          !snr02_track_targets.contains(target)) {
        snr02_track_targets_overflow = true;
      } else {
        snr02_track_targets.insert(target);
      }
    }
    if (!snr01_view_scopes.empty() &&
        snr01_view_scopes.back().ordinal == 8 &&
        !snr01_scene_list_flushes.empty() &&
        snr01_scene_list_flushes.back().owner) {
      snr01_view8_flush_owners.insert(snr01_scene_list_flushes.back().owner);
    }
    REXGPU_INFO(
        "FH1 SNR01 scene indirect packet {{\"frame\":{},\"ordinal\":{},"
        "\"header_physical\":{},\"target_physical\":{},"
        "\"words\":{},\"list_object\":{},\"node\":{},"
        "\"node_index\":{},\"node_count\":{},\"caller_lr\":{},"
        "\"flush_caller_lr\":{},\"flush_owner\":{},"
        "\"flush_owner_first_word\":{},"
        "\"flush_input\":{},"
        "\"owner_call\":{},\"owner_caller_lr\":{},"
        "\"owner_args\":[{},{},{},{},{},{},{}],"
        "\"view_call\":{},"
        "\"view\":{}}}",
        rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
        snr01_scene_indirect_count, r30.u32 & 0x1FFFFFFF,
        r10.u32 & 0x1FFFFFFF, r11.u32, r24.u32,
        r28.u32, r29.u32, SnrM02ReadU32(r28.u32 + 4),
        snr01_scene_indirect_callers.empty()
            ? 0
            : snr01_scene_indirect_callers.back(),
        snr01_scene_list_flushes.empty()
            ? 0
            : snr01_scene_list_flushes.back().caller,
        snr01_scene_list_flushes.empty()
            ? 0
            : snr01_scene_list_flushes.back().owner,
        snr01_scene_list_flushes.empty()
            ? 0
            : snr01_scene_list_flushes.back().owner_first_word,
        snr01_scene_list_flushes.empty()
            ? 0
            : snr01_scene_list_flushes.back().input,
        snr01_scene_list_flushes.empty()
            ? 0
            : snr01_scene_list_flushes.back().owner_call,
        snr01_scene_list_flushes.empty()
            ? 0
            : snr01_scene_list_flushes.back().owner_caller_lr,
        snr01_scene_list_flushes.empty()
            ? 0
            : snr01_scene_list_flushes.back().owner_args[0],
        snr01_scene_list_flushes.empty()
            ? 0
            : snr01_scene_list_flushes.back().owner_args[1],
        snr01_scene_list_flushes.empty()
            ? 0
            : snr01_scene_list_flushes.back().owner_args[2],
        snr01_scene_list_flushes.empty()
            ? 0
            : snr01_scene_list_flushes.back().owner_args[3],
        snr01_scene_list_flushes.empty()
            ? 0
            : snr01_scene_list_flushes.back().owner_args[4],
        snr01_scene_list_flushes.empty()
            ? 0
            : snr01_scene_list_flushes.back().owner_args[5],
        snr01_scene_list_flushes.empty()
            ? 0
            : snr01_scene_list_flushes.back().owner_args[6],
        snr01_view_scopes.empty() ? 0 : snr01_view_scopes.back().ordinal,
        snr01_view_scopes.empty() ? 0 : snr01_view_scopes.back().view);
  }
  static const bool enabled =
      rex::cvar::GetFlagByName("pinyon_shift_fh1_gpu_corpus") == "true" &&
      rex::cvar::GetFlagByName("pinyon_shift_fh1_scene_dump") == "true";
  if (!enabled) {
    return;
  }
  static std::mutex mutex;
  static std::set<std::array<uint32_t, 3>> observed;
  std::lock_guard lock(mutex);
  const std::array<uint32_t, 3> key = {r24.u32, r10.u32, r11.u32};
  if (observed.size() == 4096 || !observed.insert(key).second) {
    return;
  }
  REXGPU_INFO("FH1 scene producer {{\"object\":{},\"target\":{},\"words\":{}}}",
              r24.u32, r10.u32, r11.u32);
  if (observed.size() == 4096) {
    REXGPU_INFO("FH1 scene producer record limit reached");
  }
}
