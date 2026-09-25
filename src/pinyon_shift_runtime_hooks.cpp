#include <algorithm>
#include <atomic>
#include <array>
#include <bit>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <map>
#include <mutex>
#include <string>
#include <string_view>
#include <vector>

#include <fmt/format.h>
#include <rex/cvar.h>
#include <rex/memory.h>
#include <rex/ppc/context.h>
#include <rex/perf/counter.h>
#include <rex/system/kernel_state.h>
#include <rex/system/xmemory.h>

#include "pinyon_shift_diagnostics.h"
#include "fh1_render_test.h"
#include "native_renderer/graphics_hooks.h"
#include "ui/fh1_ui_api.h"

REXCVAR_DEFINE_BOOL(pinyon_shift_skip_opening_movies, false, "Pinyon Shift",
                    "Complete XMedia-backed movies immediately");
REXCVAR_DEFINE_BOOL(
    pinyon_shift_stabilize_vehicle_presentation, false, "Pinyon Shift",
    "Suppress isolated implausible player-vehicle presentation transforms");
REXCVAR_DEFINE_BOOL(disable_motion_blur, false, "Pinyon Shift",
                    "Disable Forza Horizon motion blur");
REXCVAR_DEFINE_BOOL(disable_depth_of_field, false, "Pinyon Shift",
                    "Disable Forza Horizon depth of field");

namespace {

std::atomic<uint32_t> g_cleanup_pointer_field{};
std::atomic<uint32_t> g_geometry_zero_index_buffer{};
std::atomic<uint64_t> g_last_frame_telemetry_ms{};
std::atomic<uint32_t> g_ui_component_trace_count{};
std::atomic<uint32_t> g_ui_list_trace_count{};
std::atomic<uint32_t> g_ui_pause_button_trace_count{};
std::atomic<uint32_t> g_ui_pause_menu_field_trace_count{};
std::atomic<uint32_t> g_ui_menu_field_trace_count{};
std::atomic<uint32_t> g_ui_menu_dispatch_trace_count{};
std::atomic<uint32_t> g_ui_text_value_trace_count{};
std::atomic<uint32_t> g_ui_pause_button_text_get_trace_count{};
// UI-14 crash probe counters. The label/text binding path is traced once the
// insert route reaches pause open, so each counter stays small.
std::atomic<uint32_t> g_ui_label_apply_trace_count{};
std::atomic<uint32_t> g_ui_text_bind_trace_count{};
std::atomic<uint32_t> g_ui_item_factory_trace_count{};
std::atomic<uint32_t> g_ui_binding_trace_count{};
std::atomic<uint32_t> g_ui_identity_append_trace_count{};
std::atomic<uint32_t> g_ui_identity_lookup_trace_count{};
std::atomic<uint32_t> g_ui_scene_identity_lookup_trace_count{};
std::atomic<uint32_t> g_ui_scene_identity_delivery_trace_count{};
std::atomic<uint32_t> g_ui_scene_tree_walk_trace_count{};
std::atomic<bool> g_ui_scene_tree_walk_trace_enabled{};
std::atomic<uint32_t> g_ui_scene_insert_first_button{};
std::atomic<uint32_t> g_ui_list_selection_trace_count{};
std::atomic<uint32_t> g_ui_scene_cleanup_trace_count{};
std::atomic<uint32_t> g_ui_insert_entry_trace_count{};
std::atomic<uint32_t> g_ui_pause_button_count{};
std::array<uint32_t, 128> g_ui_pause_buttons{};
pinyon_shift::ui::Api g_ui_experiment_api(4u);
pinyon_shift::ui::SceneHandle g_ui_experiment_scene;
uint64_t g_ui_experiment_generation = 0;
uint32_t g_ui_experiment_button = 0;
bool g_ui_experiment_applied = false;
constexpr uint32_t kUiExperimentTextTargets = 16u;
// Label-scan window: the observed UI allocations span the 0x2E... and 0x40...
// regions, so the window covers both. Each frame scans a bounded slice.
constexpr uint32_t kUiLabelScanBlockSize = 0x10000u;
constexpr uint32_t kUiLabelScanBytesPerFrame = 8u * 1024u * 1024u;
// Observed UI allocations live in these two regions; sweeping only them keeps a
// full pass under a tenth of a second, so a label string is patched almost as
// soon as the string table is loaded.
struct UiLabelScanRegion {
  uint32_t begin;
  uint32_t end;
};
constexpr std::array<UiLabelScanRegion, 2> kUiLabelScanRegions = {{
    {0x2E000000u, 0x30000000u},
    {0x40000000u, 0x42000000u},
}};
constexpr uint32_t kUiLabelScanBegin = kUiLabelScanRegions[0].begin;
constexpr uint32_t kUiLabelScanEnd = kUiLabelScanRegions[1].end;
constexpr uint32_t kUiLabelMaximumWrites = 64u;
constexpr uint32_t kUiLabelRescanIntervalFrames = 45u;
constexpr std::string_view kUiExperimentRequestedLabel = "Pinyon UI";
// LSB2 string-table interception. The title's LSB2 reader sub_82CAC5B8 loads a
// table into a fresh allocation and copies the payload verbatim when r5 bit 0 is
// set, so the first writable copy of every visible label exists between
// 0x82CAC740 (the read call returns) and the parse return. `label_patch`
// rewrites these literals there, at the same byte length, before the title can
// shape them into glyph runs.
struct UiLabelPatch {
  std::string_view source;
  std::string_view replacement;
};
constexpr std::array<UiLabelPatch, 2> kUiLabelPatches = {{
    {"MULTIPLAYER", "PINYONSHIFT"},
    {"PHOTO MODE", "PINYON MOD"},
}};
constexpr uint32_t kUiStringTraceLimit = 256u;
constexpr uint32_t kUiStringChunkMaximumBytes = 256u * 1024u;
constexpr uint32_t kUiStringChunkMaximumPatchHits = 64u;
std::atomic<uint32_t> g_ui_string_load_count{};
std::atomic<uint32_t> g_ui_string_chunk_count{};
std::atomic<uint32_t> g_ui_string_parsed_count{};
std::atomic<uint32_t> g_ui_string_patch_count{};
std::atomic<uint32_t> g_ui_string_lookup_count{};
std::atomic<uint32_t> g_ui_string_buffer{};
std::atomic<uint32_t> g_ui_string_buffer_size{};
// The loader runs on the guest thread, so the current path can be kept in a
// plain string: only the event-recording cap is bounded, never the patch.
std::string g_ui_string_current_path;
std::string g_ui_string_patched_path;
std::array<uint32_t, kUiExperimentTextTargets> g_ui_experiment_buttons{};
std::atomic<uint32_t> g_ui_experiment_buttons_count{};
std::atomic<bool> g_ui_experiment_buttons_queued{};
std::atomic<uint64_t> g_last_vehicle_pose_ms{};
std::atomic<uint64_t> g_last_vehicle_discontinuity_ms{};
std::atomic<uint32_t> g_title_generation{1};
std::atomic<bool> g_cleanup_pointer_live{};
std::atomic<bool> g_opening_movie_skip_logged{};
std::mutex g_vehicle_hook_sample_mutex;
std::mutex g_save_snapshot_mutex;
std::mutex g_geometry_zero_index_buffer_mutex;

struct VehiclePose {
  float x = 0.0f;
  float y = 0.0f;
  float z = 0.0f;
  float w = 1.0f;
  float forward_x = 0.0f;
  float forward_y = 0.0f;
  float forward_z = 1.0f;
  float forward_w = 0.0f;
};

struct VehiclePresentationState {
  bool valid = false;
  uint32_t generation = 0;
  uint32_t source = 0;
  VehiclePose accepted;
  bool pending = false;
  VehiclePose pending_last;
  uint64_t pending_since_ms = 0;
};

VehiclePresentationState g_vehicle_presentation_state;

std::string Hex32(uint32_t value) { return fmt::format("{:08X}", value); }

uint32_t LoadGuestU32(uint32_t address) {
  auto* kernel_state = rex::system::kernel_state();
  auto* base = kernel_state->memory()->virtual_membase();
  return static_cast<uint32_t>(
      *rex::memory::GuestPtr<rex::be_u32*>(base, address));
}

uint8_t LoadGuestU8(uint32_t address) {
  auto* kernel_state = rex::system::kernel_state();
  auto* base = kernel_state->memory()->virtual_membase();
  return *rex::memory::GuestPtr<uint8_t*>(base, address);
}

float LoadGuestF32(uint32_t address) {
  return std::bit_cast<float>(LoadGuestU32(address));
}

void StoreGuestU32(uint32_t address, uint32_t value) {
  auto* kernel_state = rex::system::kernel_state();
  auto* base = kernel_state->memory()->virtual_membase();
  *rex::memory::GuestPtr<rex::be_u32*>(base, address) = value;
}

void StoreGuestU8(uint32_t address, uint8_t value) {
  auto* kernel_state = rex::system::kernel_state();
  auto* base = kernel_state->memory()->virtual_membase();
  *rex::memory::GuestPtr<uint8_t*>(base, address) = value;
}

void StoreGuestF32(uint32_t address, float value) {
  StoreGuestU32(address, std::bit_cast<uint32_t>(value));
}

float PositionDistanceSquared(const VehiclePose& lhs, const VehiclePose& rhs) {
  const float dx = lhs.x - rhs.x;
  const float dy = lhs.y - rhs.y;
  const float dz = lhs.z - rhs.z;
  return dx * dx + dy * dy + dz * dz;
}

bool IsPlausibleVehiclePose(const VehiclePose& pose) {
  const float forward_length_sq =
      pose.forward_x * pose.forward_x + pose.forward_y * pose.forward_y +
      pose.forward_z * pose.forward_z;
  return std::isfinite(pose.x) && std::isfinite(pose.y) &&
         std::isfinite(pose.z) && std::isfinite(pose.w) &&
         std::isfinite(forward_length_sq) &&
         std::abs(pose.x) <= 10000000.0f &&
         std::abs(pose.y) <= 10000000.0f &&
         std::abs(pose.z) <= 10000000.0f && std::abs(pose.w - 1.0f) <= 0.01f &&
         forward_length_sq >= 0.81f && forward_length_sq <= 1.21f;
}

void StoreVehiclePose(uint32_t position_address, uint32_t forward_address,
                      const VehiclePose& pose) {
  StoreGuestF32(position_address, pose.x);
  StoreGuestF32(position_address + 4, pose.y);
  StoreGuestF32(position_address + 8, pose.z);
  StoreGuestF32(position_address + 12, pose.w);
  StoreGuestF32(forward_address, pose.forward_x);
  StoreGuestF32(forward_address + 4, pose.forward_y);
  StoreGuestF32(forward_address + 8, pose.forward_z);
  StoreGuestF32(forward_address + 12, pose.forward_w);
}

bool FrameTelemetryEnabled() {
  static const bool enabled = [] {
#if defined(_WIN32)
    char* value = nullptr;
    size_t value_size = 0;
    if (_dupenv_s(&value, &value_size, "PINYON_SHIFT_M4_TELEMETRY") != 0) {
      return false;
    }
    const bool result = value && std::string_view(value) == "1";
    std::free(value);
    return result;
#else
    const char* value = std::getenv("PINYON_SHIFT_M4_TELEMETRY");
    return value && std::string_view(value) == "1";
#endif
  }();
  return enabled;
}

bool SaveTraceEnabled() {
  static const bool enabled = [] {
#if defined(_WIN32)
    char* value = nullptr;
    size_t value_size = 0;
    if (_dupenv_s(&value, &value_size, "PINYON_SHIFT_M5_SAVE_TRACE") != 0) {
      return false;
    }
    const bool result = value && std::string_view(value) == "1";
    std::free(value);
    return result;
#else
    const char* value = std::getenv("PINYON_SHIFT_M5_SAVE_TRACE");
    return value && std::string_view(value) == "1";
#endif
  }();
  return enabled;
}

bool UiTraceEnabled() {
  static const bool enabled = [] {
#if defined(_WIN32)
    char* value = nullptr;
    size_t value_size = 0;
    if (_dupenv_s(&value, &value_size, "PINYON_SHIFT_UI_TRACE") != 0) {
      return false;
    }
    const bool result = value && std::string_view(value) == "1";
    std::free(value);
    return result;
#else
    const char* value = std::getenv("PINYON_SHIFT_UI_TRACE");
    return value && std::string_view(value) == "1";
#endif
  }();
  return enabled;
}

// Default-off UI experiments. `hide_first` keeps the earlier +160 state-byte
// probe; `text_probe` samples the two embedded 12-byte CUI4TextElement objects
// of every observed pause button at a bounded cadence and records their
// {+4, +8} pair plus any readable string those words point to. It writes no
// guest state.
enum class UiExperimentMode {
  kNone,
  kHideFirst,
  kTextProbe,
  kLabelScan,
  kLabelWrite,
  kLabelPatch,
  kInsertItem,
  kSceneProbe,
  kSceneInsert,
};

UiExperimentMode ComputeUiExperimentMode() {
  std::string_view requested;
#if defined(_WIN32)
  char* value = nullptr;
  size_t value_size = 0;
  if (_dupenv_s(&value, &value_size, "PINYON_SHIFT_UI_EXPERIMENT") != 0) {
    return UiExperimentMode::kNone;
  }
  const std::string owned = value ? std::string(value) : std::string();
  std::free(value);
  requested = owned;
#else
  const char* value = std::getenv("PINYON_SHIFT_UI_EXPERIMENT");
  requested = value ? std::string_view(value) : std::string_view();
#endif
  if (requested == "hide_first") {
    return UiExperimentMode::kHideFirst;
  }
  if (requested == "text_probe") {
    return UiExperimentMode::kTextProbe;
  }
  if (requested == "label_scan") {
    return UiExperimentMode::kLabelScan;
  }
  if (requested == "label_write") {
    return UiExperimentMode::kLabelWrite;
  }
  if (requested == "label_patch") {
    return UiExperimentMode::kLabelPatch;
  }
  if (requested == "insert_item") {
    return UiExperimentMode::kInsertItem;
  }
  if (requested == "scene_probe") {
    return UiExperimentMode::kSceneProbe;
  }
  if (requested == "scene_insert") {
    return UiExperimentMode::kSceneInsert;
  }
  return UiExperimentMode::kNone;
}

// Replacement literal for the label write mode. Same-length overwrite of the
// located string, so no allocation or length field is touched.
std::string_view UiLabelWriteLiteral() {
  static const std::string value = [] {
#if defined(_WIN32)
    char* raw = nullptr;
    size_t size = 0;
    if (_dupenv_s(&raw, &size, "PINYON_SHIFT_UI_LABEL_WRITE") != 0) {
      return std::string("PINYONSHIFT");
    }
    const std::string owned =
        raw && raw[0] != '\0' ? std::string(raw) : std::string("PINYONSHIFT");
    std::free(raw);
    return owned;
#else
    const char* raw = std::getenv("PINYON_SHIFT_UI_LABEL_WRITE");
    return raw && raw[0] != '\0' ? std::string(raw) : std::string("PINYONSHIFT");
#endif
  }();
  return value;
}

// Optional literal for the label scan, so the probe is not tied to one screen.
std::string_view UiLabelScanLiteral() {
  static const std::string value = [] {
#if defined(_WIN32)
    char* raw = nullptr;
    size_t size = 0;
    if (_dupenv_s(&raw, &size, "PINYON_SHIFT_UI_LABEL_SCAN") != 0) {
      return std::string("MULTIPLAYER");
    }
    const std::string owned = raw && raw[0] != '\0' ? std::string(raw)
                                                    : std::string("MULTIPLAYER");
    std::free(raw);
    return owned;
#else
    const char* raw = std::getenv("PINYON_SHIFT_UI_LABEL_SCAN");
    return raw && raw[0] != '\0' ? std::string(raw) : std::string("MULTIPLAYER");
#endif
  }();
  return value;
}

UiExperimentMode UiExperimentModeValue() {
  static const UiExperimentMode mode = ComputeUiExperimentMode();
  return mode;
}

uint32_t CareerCheckpointSeedStage() {
  static const uint32_t stage = [] {
#if defined(_WIN32)
    char* value = nullptr;
    size_t value_size = 0;
    if (_dupenv_s(&value, &value_size,
                  "PINYON_SHIFT_M5_TEST_CAREER_CHECKPOINT") != 0) {
      return 0u;
    }
    const std::string_view requested = value ? std::string_view(value)
                                             : std::string_view();
    const uint32_t result =
        requested == "2"  ? 2u
        : requested == "3" ? 3u
        : requested == "7" ? 7u
        : requested == "10" ? 10u
                              : 0u;
    std::free(value);
    return result;
#else
    const char* value =
        std::getenv("PINYON_SHIFT_M5_TEST_CAREER_CHECKPOINT");
    const std::string_view requested = value ? std::string_view(value)
                                             : std::string_view();
    return requested == "2"  ? 2u
           : requested == "3" ? 3u
           : requested == "7" ? 7u
           : requested == "10" ? 10u
                                 : 0u;
#endif
  }();
  return stage;
}

uint64_t HashGuestBytes(uint32_t address, uint32_t size) {
  auto* kernel_state = rex::system::kernel_state();
  auto* base = kernel_state->memory()->virtual_membase();
  const auto* bytes = reinterpret_cast<const uint8_t*>(base) + address;
  uint64_t hash = 1469598103934665603ull;
  for (uint32_t i = 0; i < size; ++i) {
    hash ^= bytes[i];
    hash *= 1099511628211ull;
  }
  return hash;
}

void SnapshotSavePayload(std::string_view kind, uint32_t address, uint32_t size,
                         uint32_t caller_lr) {
  // These are the two known plaintext secure-save payload sizes. Limiting the
  // hook to them keeps diagnostics narrow and avoids copying unrelated stream
  // traffic through this generic title writer.
  if (!SaveTraceEnabled() || address == 0 ||
      (size != 19472 && size != 2928)) {
    return;
  }

  const uint64_t hash = HashGuestBytes(address, size);
  // The title mirrors its first-time-career state at this fixed address while
  // the onboarding state machine is alive. Recording it beside the serialized
  // body lets us distinguish a failed save from an intentionally deferred
  // onboarding checkpoint without changing either state.
  constexpr uint32_t kFirstTimeCareerStageAddress = 0x833067E0u;
  const uint32_t first_time_career_stage =
      LoadGuestU32(kFirstTimeCareerStageAddress);
  const auto directory =
      pinyon_shift::diagnostics::StateRoot() / "logs" / "save-snapshots";
  const auto filename =
      fmt::format("payload-{}-{}-{:016X}.bin", kind, size, hash);
  const auto path = directory / filename;
  bool created = false;
  {
    std::scoped_lock lock(g_save_snapshot_mutex);
    std::error_code error;
    std::filesystem::create_directories(directory, error);
    if (!error && !std::filesystem::exists(path, error)) {
      auto* kernel_state = rex::system::kernel_state();
      auto* base = kernel_state->memory()->virtual_membase();
      const auto* bytes = reinterpret_cast<const char*>(base) + address;
      std::ofstream stream(path, std::ios::binary | std::ios::trunc);
      if (stream) {
        stream.write(bytes, size);
        created = stream.good();
      }
    }
  }
  pinyon_shift::diagnostics::RecordEvent(
      "save.payload.snapshot",
      {{"address", Hex32(address)},
       {"size", fmt::format("{}", size)},
       {"kind", std::string(kind)},
       {"caller_lr", Hex32(caller_lr)},
       {"first_time_career_stage",
        fmt::format("{}", first_time_career_stage)},
       {"hash", fmt::format("{:016X}", hash)},
       {"snapshot", path.string()},
       {"created", created ? "1" : "0"}});
}

void SeedCareerCheckpointInSavePayload(uint32_t address, uint32_t size) {
  const uint32_t requested_stage = CareerCheckpointSeedStage();
  if (requested_stage == 0 || address == 0 || size != 19472) {
    return;
  }

  auto* kernel_state = rex::system::kernel_state();
  auto* base = kernel_state->memory()->virtual_membase();
  auto* bytes = reinterpret_cast<uint8_t*>(base) + address;
  constexpr std::string_view kActivityKey = "first_time_career_activity";
  const std::string_view body(reinterpret_cast<const char*>(bytes), size);
  const size_t key_offset = body.find(kActivityKey);
  if (key_offset == std::string_view::npos || key_offset + 64u > size ||
      bytes[key_offset + 29u] != 0x15u ||
      body.substr(key_offset + 30u, 21u) != "CFirstTimeCareerState" ||
      bytes[key_offset + 54u] != 0x01u ||
      bytes[key_offset + 58u] != 0x05u) {
    pinyon_shift::diagnostics::RecordEvent(
        "save.career_checkpoint.payload_seed", {{"result", "layout_mismatch"}});
    return;
  }

  const uint32_t value_address =
      address + static_cast<uint32_t>(key_offset) + 59u;
  // CFirstTimeCareerState serializes its byte-at-40 active flag first, then
  // its big-endian uint32 stage-at-44: [active][stage].
  const uint8_t previous_active = LoadGuestU8(value_address);
  const uint32_t previous_stage = LoadGuestU32(value_address + 1u);
  bytes[key_offset + 59u] = 1u;
  StoreGuestU32(value_address + 1u, requested_stage);
  pinyon_shift::diagnostics::RecordEvent(
      "save.career_checkpoint.payload_seed",
      {{"result", "seeded"},
       {"offset", fmt::format("{}", key_offset + 59u)},
       {"previous_stage", fmt::format("{}", previous_stage)},
       {"previous_active", fmt::format("{}", previous_active)},
       {"stage", fmt::format("{}", requested_stage)},
       {"active", "1"}});
}

bool OpeningMovieSkipRequested() {
  if (REXCVAR_GET(pinyon_shift_skip_opening_movies)) {
    return true;
  }
#if defined(_WIN32)
  char* value = nullptr;
  size_t value_size = 0;
  if (_dupenv_s(&value, &value_size, "PINYON_SHIFT_SKIP_OPENING_MOVIES") != 0) {
    return false;
  }
  const bool result = value && std::string_view(value) == "1";
  std::free(value);
  return result;
#else
  const char* value = std::getenv("PINYON_SHIFT_SKIP_OPENING_MOVIES");
  return value && std::string_view(value) == "1";
#endif
}

}  // namespace

static bool PinyonShiftGuestRangeReadable(uint32_t address, uint32_t size);
static std::string PinyonShiftReadGuestAscii(uint32_t address,
                                             uint32_t maximum_length);

bool PinyonShiftDisableMotionBlur() {
  return REXCVAR_GET(disable_motion_blur);
}

bool PinyonShiftDisableDepthOfField(PPCRegister& r11) {
  if (!REXCVAR_GET(disable_depth_of_field)) {
    return false;
  }
  r11.u64 = 0;
  return true;
}

void PinyonShiftCompleteOpeningMovie(PPCRegister& r3, PPCRegister& r30,
                                     PPCRegister& r31) {
  const uint32_t original_result = r3.u32;
  const bool skip = OpeningMovieSkipRequested();
  if (skip) {
    // This is the XMedia facade's normal end-of-stream result. Returning it
    // through the title's own wrapper runs the ordinary movie-finished event
    // path instead of bypassing profile/setup state.
    r3.u32 = 0x16660026u;
  }
  if (skip && !g_opening_movie_skip_logged.exchange(true, std::memory_order_acq_rel)) {
    pinyon_shift::diagnostics::RecordEvent(
        "opening_movie.skipped",
        {{"address", "82E5D8AC"},
         {"original_result", Hex32(original_result)},
         {"result", Hex32(r3.u32)},
         {"argument", Hex32(r30.u32)},
         {"object", Hex32(r31.u32)}});
  }
}

void PinyonShiftTraceUiSceneRegistry(PPCRegister& r3, PPCRegister& r24,
                                     PPCRegister& r30) {
  if (!UiTraceEnabled()) {
    return;
  }

  pinyon_shift::diagnostics::RecordEvent(
      "ui.scene_registry.constructed",
      {{"address", "824850A4"},
       {"object", Hex32(r3.u32)},
       {"context", Hex32(r24.u32)},
       {"owner", Hex32(r30.u32)}});

  constexpr uint32_t kRegistrySize = 2820u;
  if (!PinyonShiftGuestRangeReadable(r3.u32, kRegistrySize)) {
    return;
  }
  std::array<std::string, 192> seen{};
  size_t seen_count = 0;
  for (uint32_t offset = 0;
       offset + 4u <= kRegistrySize && seen_count < seen.size(); offset += 4u) {
    const uint32_t pointer = LoadGuestU32(r3.u32 + offset);
    if (pointer < 0x82000000u || pointer >= 0x83000000u) {
      continue;
    }
    const std::string name = PinyonShiftReadGuestAscii(pointer, 64u);
    if (name.empty() ||
        std::find(seen.begin(), seen.begin() + seen_count, name) !=
            seen.begin() + seen_count) {
      continue;
    }
    seen[seen_count++] = name;
    pinyon_shift::diagnostics::RecordEvent(
        "ui.scene_registry.name",
        {{"address", "824850A4"},
         {"object", Hex32(r3.u32)},
         {"offset", Hex32(offset)},
         {"value", Hex32(pointer)},
         {"name", name}});
  }
}

namespace {

void TraceUiDispatch(std::string_view kind, std::string_view address,
                     PPCRegister& object, PPCRegister& argument,
                     PPCRegister& target, PPCRegister* result = nullptr,
                     PPCRegister* vtable = nullptr) {
  if (!UiTraceEnabled()) {
    return;
  }
  const std::string event =
      std::string("ui.dispatch.") + std::string(kind);
  if (result != nullptr && vtable != nullptr) {
    pinyon_shift::diagnostics::RecordEvent(
        event,
        {{"address", address},
         {"object", Hex32(object.u32)},
         {"argument", Hex32(argument.u32)},
         {"target", Hex32(target.u32)},
         {"result", Hex32(result->u32)},
         {"vtable", Hex32(vtable->u32)}});
  } else {
    pinyon_shift::diagnostics::RecordEvent(
        event,
        {{"address", address},
         {"object", Hex32(object.u32)},
         {"argument", Hex32(argument.u32)},
         {"target", Hex32(target.u32)}});
  }
}

}  // namespace

void PinyonShiftTraceUiRegistryDispatch(PPCRegister& r3, PPCRegister& r4,
                                        PPCRegister& r11) {
  TraceUiDispatch("registry", "824850CC", r3, r4, r11);
}

void PinyonShiftTraceUiResourceDispatch(PPCRegister& r3, PPCRegister& r4,
                                        PPCRegister& r11) {
  TraceUiDispatch("resource", "824850E8", r3, r4, r11);
}

void PinyonShiftTraceUiSceneDispatch(PPCRegister& r3, PPCRegister& r4,
                                     PPCRegister& r11, PPCRegister& r31,
                                     PPCRegister& r30) {
  TraceUiDispatch("scene", "82485110", r3, r4, r11, &r3, &r30);
  if (!UiTraceEnabled() || !PinyonShiftGuestRangeReadable(r4.u32, 4u)) {
    return;
  }
  pinyon_shift::diagnostics::RecordEvent(
      "ui.dispatch.scene_argument",
      {{"address", "82485110"},
       {"argument_word0", Hex32(LoadGuestU32(r4.u32))},
       {"owner", Hex32(r31.u32)}});
}

void PinyonShiftTraceUiManagerEvent(PPCRegister& r3, PPCRegister& r4,
                                    PPCRegister& r11) {
  TraceUiDispatch("manager_event", "82485128", r3, r4, r11);
}

namespace {

void TraceUiMethod(std::string_view address, PPCRegister& r3, PPCRegister& r4) {
  if (!UiTraceEnabled()) {
    return;
  }
  const uint32_t vtable = PinyonShiftGuestRangeReadable(r3.u32, 4u)
                              ? LoadGuestU32(r3.u32)
                              : 0u;
  pinyon_shift::diagnostics::RecordEvent(
      "ui.method.enter",
      {{"address", address},
       {"object", Hex32(r3.u32)},
       {"argument", Hex32(r4.u32)},
       {"vtable", Hex32(vtable)}});
  const auto read_field = [&](uint32_t offset) {
    return PinyonShiftGuestRangeReadable(r3.u32 + offset, 4u)
               ? Hex32(LoadGuestU32(r3.u32 + offset))
               : std::string("00000000");
  };
  const auto read_nested = [&](uint32_t field_offset, uint32_t nested_offset) {
    if (!PinyonShiftGuestRangeReadable(r3.u32 + field_offset, 4u)) {
      return std::string("00000000");
    }
    const uint32_t pointer = LoadGuestU32(r3.u32 + field_offset);
    return PinyonShiftGuestRangeReadable(pointer + nested_offset, 4u)
               ? Hex32(LoadGuestU32(pointer + nested_offset))
               : std::string("00000000");
  };
  pinyon_shift::diagnostics::RecordEvent(
      "ui.method.object_fields",
      {{"address", address},
       {"object", Hex32(r3.u32)},
       {"field_12", read_field(12u)},
       {"field_16", read_field(16u)},
       {"field_48", read_field(48u)},
       {"field_52", read_field(52u)},
       {"field_56", read_field(56u)},
       {"field_60", read_field(60u)},
       {"field_88", read_field(88u)},
       {"field_100", read_field(100u)},
       {"field_120", read_field(120u)},
       {"field_124", read_field(124u)},
       {"field_60_word0", read_nested(60u, 0u)},
       {"field_60_word4", read_nested(60u, 4u)},
       {"field_88_word0", read_nested(88u, 0u)}});
  if (!PinyonShiftGuestRangeReadable(r4.u32, 4u)) {
    return;
  }
  for (uint32_t offset = 0; offset < 64u; offset += 4u) {
    const uint32_t value = LoadGuestU32(r4.u32 + offset);
    if (value < 0x82000000u || value >= 0x83000000u) {
      continue;
    }
    const std::string text = PinyonShiftReadGuestAscii(value, 64u);
    if (!text.empty()) {
      pinyon_shift::diagnostics::RecordEvent(
          "ui.method.argument_string",
          {{"address", address},
           {"offset", Hex32(offset)},
           {"value", text}});
    }
  }
}

}  // namespace

void PinyonShiftTraceUiRegistryMethod(PPCRegister& r3, PPCRegister& r4) {
  TraceUiMethod("826413C8", r3, r4);
  if (!UiTraceEnabled() || !PinyonShiftGuestRangeReadable(r4.u32, 2820u)) {
    return;
  }
  pinyon_shift::diagnostics::RecordEvent(
      "ui.registry.attached",
      {{"address", "826413C8"},
       {"owner", Hex32(r3.u32)},
       {"registry", Hex32(r4.u32)}});
  std::array<std::string, 192> seen{};
  size_t seen_count = 0;
  for (uint32_t offset = 0;
       offset + 4u <= 2820u && seen_count < seen.size(); offset += 4u) {
    const uint32_t pointer = LoadGuestU32(r4.u32 + offset);
    if (pointer < 0x82000000u || pointer >= 0x83000000u) {
      continue;
    }
    const std::string name = PinyonShiftReadGuestAscii(pointer, 64u);
    if (name.empty() ||
        std::find(seen.begin(), seen.begin() + seen_count, name) !=
            seen.begin() + seen_count) {
      continue;
    }
    seen[seen_count++] = name;
    pinyon_shift::diagnostics::RecordEvent(
        "ui.registry.attached_name",
        {{"address", "826413C8"},
         {"registry", Hex32(r4.u32)},
         {"offset", Hex32(offset)},
         {"value", Hex32(pointer)},
         {"name", name}});
  }
}

void PinyonShiftTraceUiResourceMethod(PPCRegister& r3, PPCRegister& r4) {
  TraceUiMethod("82E5E0D0", r3, r4);
}

void PinyonShiftTraceUiSceneMethod(PPCRegister& r3, PPCRegister& r4) {
  TraceUiMethod("82E729F8", r3, r4);
}

namespace {

void TraceUiComponentMethod(std::string_view address, PPCRegister& r3,
                            PPCRegister& r4, PPCRegister* value = nullptr) {
  if (!UiTraceEnabled() ||
      g_ui_component_trace_count.fetch_add(1, std::memory_order_relaxed) >=
          512u) {
    return;
  }
  if (value != nullptr) {
    pinyon_shift::diagnostics::RecordEvent(
        "ui.component.method",
        {{"address", address},
         {"object", Hex32(r3.u32)},
         {"slot", Hex32(r4.u32 + 29u)},
         {"argument", Hex32(r4.u32)},
         {"value", Hex32(value->u32)}});
    return;
  }
  pinyon_shift::diagnostics::RecordEvent(
      "ui.component.method",
      {{"address", address},
       {"object", Hex32(r3.u32)},
       {"slot", Hex32(r4.u32 + 29u)},
       {"argument", Hex32(r4.u32)}});
}

}  // namespace

void PinyonShiftTraceUiComponentGet(PPCRegister& r3, PPCRegister& r4) {
  TraceUiComponentMethod("82E5E550", r3, r4);
}

void PinyonShiftTraceUiComponentStore(PPCRegister& r3, PPCRegister& r4,
                                       PPCRegister& r5) {
  TraceUiComponentMethod("82E5E568", r3, r4, &r5);
}

void PinyonShiftTraceUiComponentClear(PPCRegister& r3, PPCRegister& r4) {
  TraceUiComponentMethod("82E5E580", r3, r4);
}

namespace {

void TraceUiListMethod(std::string_view address, PPCRegister& r3,
                       PPCRegister& r4, PPCRegister& r5) {
  if (!UiTraceEnabled() ||
      g_ui_list_trace_count.fetch_add(1, std::memory_order_relaxed) >=
          1024u) {
    return;
  }
  const auto read_field = [&](uint32_t offset) {
    return PinyonShiftGuestRangeReadable(r3.u32 + offset, 4u)
               ? Hex32(LoadGuestU32(r3.u32 + offset))
               : std::string("00000000");
  };
  const auto read_value_field = [&](uint32_t offset) {
    return PinyonShiftGuestRangeReadable(r5.u32 + offset, 4u)
               ? Hex32(LoadGuestU32(r5.u32 + offset))
               : std::string("00000000");
  };
  const auto read_nested_vtable = [&](uint32_t offset) {
    if (!PinyonShiftGuestRangeReadable(r5.u32 + offset, 4u)) {
      return std::string("00000000");
    }
    const uint32_t pointer = LoadGuestU32(r5.u32 + offset);
    return PinyonShiftGuestRangeReadable(pointer, 4u)
               ? Hex32(LoadGuestU32(pointer))
               : std::string("00000000");
  };
  pinyon_shift::diagnostics::RecordEvent(
      "ui.list.method",
      {{"address", address},
       {"object", Hex32(r3.u32)},
       {"argument", Hex32(r4.u32)},
       {"value", Hex32(r5.u32)},
       {"vtable", read_field(0u)},
       {"field_8", read_field(8u)},
       {"field_12", read_field(12u)},
       {"field_32", read_field(32u)},
       {"field_36", read_field(36u)},
       {"field_116", read_field(116u)},
       {"field_120", read_field(120u)},
       {"field_312", read_field(312u)},
       {"value_vtable", read_value_field(0u)},
       {"value_field_4", read_value_field(4u)},
       {"value_field_8", read_value_field(8u)},
       {"value_field_12", read_value_field(12u)},
       {"value_field_364", read_value_field(364u)},
       {"value_field_468", read_value_field(468u)},
       {"value_field_472", read_value_field(472u)},
       {"value_field_476", read_value_field(476u)},
       {"value_field_508", read_value_field(508u)},
       {"value_field_364_vtable", read_nested_vtable(364u)},
       {"value_field_468_vtable", read_nested_vtable(468u)},
       {"value_field_472_vtable", read_nested_vtable(472u)},
       {"value_field_476_vtable", read_nested_vtable(476u)}});

  const uint32_t value_vtable =
      PinyonShiftGuestRangeReadable(r5.u32, 4u) ? LoadGuestU32(r5.u32) : 0u;
  if (value_vtable != 0x8205109Cu && value_vtable != 0x82059E8Cu) {
    return;
  }
  if (g_ui_pause_menu_field_trace_count.fetch_add(
          1, std::memory_order_relaxed) >= 128u) {
    return;
  }
  constexpr std::array<uint32_t, 6> kMenuVtables = {
      0x82063974u, 0x82063A0Cu, 0x8206D3B8u,
      0x8203363Cu, 0x82026B38u, 0x82063CA4u};
  for (uint32_t offset = 4u; offset <= 768u; offset += 4u) {
    if (!PinyonShiftGuestRangeReadable(r5.u32 + offset, 4u)) {
      break;
    }
    const uint32_t pointer = LoadGuestU32(r5.u32 + offset);
    if (!PinyonShiftGuestRangeReadable(pointer, 4u)) {
      continue;
    }
    const uint32_t nested_vtable = LoadGuestU32(pointer);
    if (std::find(kMenuVtables.begin(), kMenuVtables.end(), nested_vtable) ==
        kMenuVtables.end()) {
      continue;
    }
    pinyon_shift::diagnostics::RecordEvent(
        "ui.pause_menu.field",
        {{"owner", Hex32(r5.u32)},
         {"owner_vtable", Hex32(value_vtable)},
         {"offset", Hex32(offset)},
         {"pointer", Hex32(pointer)},
         {"vtable", Hex32(nested_vtable)}});
  }

  const uint32_t list_vtable =
      PinyonShiftGuestRangeReadable(r3.u32, 4u) ? LoadGuestU32(r3.u32) : 0u;
  if (list_vtable != 0x8206D3B8u ||
      g_ui_menu_field_trace_count.fetch_add(1, std::memory_order_relaxed) >=
          128u) {
    return;
  }
  constexpr std::array<uint32_t, 6> kUiVtables = {
      0x82063974u, 0x82063A0Cu, 0x8206D3B8u,
      0x8203363Cu, 0x82026B38u, 0x82063CA4u};
  for (uint32_t offset = 4u; offset <= 512u; offset += 4u) {
    if (!PinyonShiftGuestRangeReadable(r3.u32 + offset, 4u)) {
      break;
    }
    const uint32_t pointer = LoadGuestU32(r3.u32 + offset);
    if (!PinyonShiftGuestRangeReadable(pointer, 4u)) {
      continue;
    }
    const uint32_t nested_vtable = LoadGuestU32(pointer);
    if (std::find(kUiVtables.begin(), kUiVtables.end(), nested_vtable) ==
        kUiVtables.end()) {
      continue;
    }
    pinyon_shift::diagnostics::RecordEvent(
        "ui.menu.field",
        {{"owner", Hex32(r3.u32)},
         {"offset", Hex32(offset)},
         {"pointer", Hex32(pointer)},
         {"vtable", Hex32(nested_vtable)}});
  }
}

}  // namespace

void PinyonShiftTraceUiListMethod(PPCRegister& r3, PPCRegister& r4,
                                  PPCRegister& r5) {
  TraceUiListMethod("82E7CD78", r3, r4, r5);
}

void PinyonShiftTraceUiListMethod2(PPCRegister& r3, PPCRegister& r4,
                                   PPCRegister& r5) {
  TraceUiListMethod("82E77260", r3, r4, r5);
}

namespace {

std::string UiProbeField(uint32_t address, uint32_t offset) {
  return PinyonShiftGuestRangeReadable(address + offset, 4u)
             ? Hex32(LoadGuestU32(address + offset))
             : std::string("00000000");
}

}  // namespace

// UI-14 crash probe. `sub_827DD058` is the last function entered before the
// eighth-row access violation: it hands `object + 164` (the embedded
// CUI4TextElement) to `sub_82E78820` together with the resolved label string,
// and the faulting load is `*(element + 8)` inside that callee. Recording the
// receiver, its three embedded text elements, and the caller separates "the
// eighth button's text element was never bound" from "a stock row was
// corrupted by the extra record". Default-off, bounded, read-only.
void PinyonShiftTraceUiLabelApply(PPCRegister& r3, PPCRegister& r4,
                                  PPCRegister& r5, uint64_t& lr) {
  if (!UiTraceEnabled() ||
      g_ui_label_apply_trace_count.fetch_add(1, std::memory_order_relaxed) >=
          256u) {
    return;
  }
  const uint32_t object = r3.u32;
  const uint32_t text = object + 164u;
  if (UiExperimentModeValue() == UiExperimentMode::kSceneInsert &&
      PinyonShiftGuestRangeReadable(text, 12u) &&
      LoadGuestU32(text) == 0x82026B38u && LoadGuestU32(text + 8u) == 0u) {
    const uint32_t source =
        g_ui_scene_insert_first_button.load(std::memory_order_relaxed);
    const uint32_t source_text = source + 164u;
    if (source != 0u && source != object &&
        PinyonShiftGuestRangeReadable(source_text, 12u) &&
        LoadGuestU32(source_text) == 0x82026B38u &&
        LoadGuestU32(source_text + 8u) != 0u) {
      StoreGuestU32(text + 4u, LoadGuestU32(source_text + 4u));
      StoreGuestU32(text + 8u, LoadGuestU32(source_text + 8u));
      pinyon_shift::diagnostics::RecordEvent(
          "ui.experiment.scene_insert.text_repaired",
          {{"button", Hex32(object)}, {"source", Hex32(source)}});
    }
  }
  pinyon_shift::diagnostics::RecordEvent(
      "ui.label.apply",
      {{"object", Hex32(object)},
       {"vtable", UiProbeField(object, 0u)},
       {"argument_4", Hex32(r4.u32)},
       {"argument_5", Hex32(r5.u32)},
       {"return_address", Hex32(static_cast<uint32_t>(lr))},
       {"owner_84", UiProbeField(object, 84u)},
       {"owner_160", UiProbeField(object, 160u)},
       {"owner_200", UiProbeField(object, 200u)},
       {"owner_232", UiProbeField(object, 232u)},
       {"owner_234", UiProbeField(object, 234u)},
       {"owner_248", UiProbeField(object, 248u)},
       {"owner_252_vtable", UiProbeField(object, 252u)},
       {"owner_252_8", UiProbeField(object, 260u)},
       {"owner_264_vtable", UiProbeField(object, 264u)},
       {"owner_264_8", UiProbeField(object, 272u)},
       {"text_vtable", UiProbeField(text, 0u)},
       {"text_4", UiProbeField(text, 4u)},
       {"text_8", UiProbeField(text, 8u)},
       {"text_12", UiProbeField(text, 12u)},
       {"text_16", UiProbeField(text, 16u)}});
}

// Entry point of the callee that faults. `r3` is the embedded text element and
// `r4`/`r5` are the label arguments, so the record shows which element lost its
// resource pointer (element + 8) and which object owns it.
void PinyonShiftTraceUiTextBind(PPCRegister& r3, PPCRegister& r4,
                                PPCRegister& r5, uint64_t& lr) {
  if (!UiTraceEnabled() ||
      g_ui_text_bind_trace_count.fetch_add(1, std::memory_order_relaxed) >=
          256u) {
    return;
  }
  pinyon_shift::diagnostics::RecordEvent(
      "ui.text.bind",
      {{"element", Hex32(r3.u32)},
       {"vtable", UiProbeField(r3.u32, 0u)},
       {"element_4", UiProbeField(r3.u32, 4u)},
       {"element_8", UiProbeField(r3.u32, 8u)},
       {"element_12", UiProbeField(r3.u32, 12u)},
       {"element_16", UiProbeField(r3.u32, 16u)},
       {"argument_4", Hex32(r4.u32)},
       {"argument_5", Hex32(r5.u32)},
       {"return_address", Hex32(static_cast<uint32_t>(lr))}});
}

// Item factory of the scene deserializer. `r5` is the record's name hash and
// `r6` the authored identity index that the type-0x14 properties reference, so
// the record shows the identity values the duplicated row's records carry.
void PinyonShiftTraceUiItemFactory(PPCRegister& r3, PPCRegister& r4,
                                   PPCRegister& r5, PPCRegister& r6,
                                   PPCRegister& r7, PPCRegister& r8) {
  if (!UiTraceEnabled() ||
      g_ui_item_factory_trace_count.fetch_add(1, std::memory_order_relaxed) >=
          2048u) {
    return;
  }
  pinyon_shift::diagnostics::RecordEvent(
      "ui.item.factory",
      {{"container", Hex32(r3.u32)},
       {"parent", Hex32(r4.u32)},
       {"name", Hex32(r5.u32)},
       {"identity", Hex32(r6.u32)},
       {"kind", Hex32(r7.u32)},
       {"extra", Hex32(r8.u32)}});
}

// Property application of the deserializer for one resolved type-0x14 entry.
void PinyonShiftTraceUiBindingApply(PPCRegister& r3, PPCRegister& r4,
                                    PPCRegister& r5) {
  if (!UiTraceEnabled() ||
      g_ui_binding_trace_count.fetch_add(1, std::memory_order_relaxed) >=
          2048u) {
    return;
  }
  pinyon_shift::diagnostics::RecordEvent(
      "ui.binding.apply",
      {{"container", Hex32(r3.u32)},
       {"property", Hex32(r4.u32)},
       {"entry", Hex32(r5.u32)},
       {"entry_hash", UiProbeField(r5.u32, 0u)},
       {"entry_4", UiProbeField(r5.u32, 4u)},
       {"entry_8", UiProbeField(r5.u32, 8u)}});
}

// The identity table's append path records the table's final entry count.
void PinyonShiftTraceUiIdentityAppend(PPCRegister& r3) {
  if (!UiTraceEnabled()) {
    return;
  }
  const uint32_t count = g_ui_identity_append_trace_count.fetch_add(
                             1, std::memory_order_relaxed) +
                         1u;
  if (count > 2048u) {
    return;
  }
  pinyon_shift::diagnostics::RecordEvent(
      "ui.identity.append",
      {{"resolver", Hex32(r3.u32)},
       {"count", UiProbeField(r3.u32, 8u)},
       {"entries", UiProbeField(r3.u32, 12u)},
       {"appends", std::to_string(count)}});
}

// One identity lookup: `r4` indexes the table and the record exposes the
// table's bounds, so an out-of-range reference stays visible.
void PinyonShiftTraceUiIdentityLookup(PPCRegister& r3, PPCRegister& r4) {
  const bool scene_extension =
      UiExperimentModeValue() == UiExperimentMode::kSceneInsert &&
      r4.u32 >= 1006u;
  if ((!UiTraceEnabled() && !scene_extension) ||
      (scene_extension
           ? g_ui_scene_identity_lookup_trace_count.fetch_add(
                 1, std::memory_order_relaxed) >= 128u
           : g_ui_identity_lookup_trace_count.fetch_add(
                 1, std::memory_order_relaxed) >= 4096u)) {
    return;
  }
  const uint32_t count = PinyonShiftGuestRangeReadable(r3.u32 + 8u, 4u)
                             ? LoadGuestU32(r3.u32 + 8u)
                             : 0u;
  if (scene_extension && count == 1099u) {
    g_ui_scene_tree_walk_trace_enabled.store(true, std::memory_order_relaxed);
  }
  const uint32_t entries = PinyonShiftGuestRangeReadable(r3.u32 + 12u, 4u)
                               ? LoadGuestU32(r3.u32 + 12u)
                               : 0u;
  const uint32_t source_index =
      r4.u32 >= 1078u ? r4.u32 - 247u : r4.u32 - 986u;
  const uint32_t entry = entries + r4.u32 * 8u;
  const uint32_t source_entry = entries + source_index * 8u;
  const bool entries_readable =
      scene_extension && PinyonShiftGuestRangeReadable(entry, 8u) &&
      PinyonShiftGuestRangeReadable(source_entry, 8u);
  pinyon_shift::diagnostics::RecordEvent(
      "ui.identity.lookup",
      {{"resolver", Hex32(r3.u32)},
       {"index", Hex32(r4.u32)},
       {"count", Hex32(count)},
       {"in_range", count != 0u && r4.u32 < count ? "1" : "0"},
       {"source_index", scene_extension ? Hex32(source_index) : ""},
       {"entry_0", entries_readable ? Hex32(LoadGuestU32(entry)) : ""},
       {"entry_4", entries_readable ? Hex32(LoadGuestU32(entry + 4u)) : ""},
       {"source_0",
        entries_readable ? Hex32(LoadGuestU32(source_entry)) : ""},
       {"source_4",
        entries_readable ? Hex32(LoadGuestU32(source_entry + 4u)) : ""}});
}

void PinyonShiftTraceUiSceneTreeWalk(PPCRegister& r3, PPCRegister& r4) {
  if (UiExperimentModeValue() != UiExperimentMode::kSceneInsert) {
    return;
  }
  const bool readable = PinyonShiftGuestRangeReadable(r4.u32, 32u);
  const bool invalid_kind_five =
      readable && LoadGuestU8(r4.u32 + 30u) == 5u &&
      LoadGuestU32(r4.u32 + 4u) == 0u;
  if (readable && !invalid_kind_five &&
      g_ui_scene_tree_walk_trace_count.fetch_add(1u,
                                                  std::memory_order_relaxed) >=
          256u) {
    return;
  }
  pinyon_shift::diagnostics::RecordEvent(
      invalid_kind_five ? "ui.scene.tree_invalid" : "ui.scene.tree_walk",
      {{"owner", Hex32(r3.u32)},
       {"node", Hex32(r4.u32)},
       {"readable", readable ? "1" : "0"},
       {"field_0", readable ? Hex32(LoadGuestU32(r4.u32)) : ""},
       {"field_4", readable ? Hex32(LoadGuestU32(r4.u32 + 4u)) : ""},
       {"field_8", readable ? Hex32(LoadGuestU32(r4.u32 + 8u)) : ""},
       {"field_12", readable ? Hex32(LoadGuestU32(r4.u32 + 12u)) : ""},
       {"child", readable ? Hex32(LoadGuestU32(r4.u32 + 16u)) : ""},
       {"sibling", readable ? Hex32(LoadGuestU32(r4.u32 + 20u)) : ""},
       {"kind", readable ? Hex32(LoadGuestU8(r4.u32 + 30u)) : ""}});
}

void PinyonShiftTraceUiAnimationAllocate(PPCRegister& r3, PPCRegister& r4,
                                         PPCRegister& r6, PPCRegister& r7,
                                         PPCRegister& r8, PPCRegister& r31) {
  if (UiExperimentModeValue() != UiExperimentMode::kSceneInsert) {
    return;
  }
  const uint32_t identity_table =
      PinyonShiftGuestRangeReadable(r31.u32 + 124u, 4u)
          ? LoadGuestU32(r31.u32 + 124u)
          : 0u;
  pinyon_shift::diagnostics::RecordEvent(
      "ui.experiment.scene_insert.animation_allocate",
      {{"document", Hex32(r3.u32)},
       {"count", UiProbeField(r3.u32, 12u)},
       {"storage", UiProbeField(r3.u32, 8u)},
       {"allocator", UiProbeField(r3.u32, 32u)},
       {"identity", Hex32(r4.u32)},
       {"kind", Hex32(r6.u32)},
       {"field_7", Hex32(r7.u32)},
       {"field_8", Hex32(r8.u32)},
       {"parser", Hex32(r31.u32)},
       {"identity_table", Hex32(identity_table)},
       {"identity_1033", UiProbeField(identity_table, 1033u * 4u)},
       {"identity_1035", UiProbeField(identity_table, 1035u * 4u)}});
}

bool PinyonShiftGuardUiInvalidRttiCast(PPCRegister& r3, PPCRegister& r4,
                                       PPCRegister& r5, PPCRegister& r6,
                                       PPCRegister& r7, uint64_t& lr) {
  if (UiExperimentModeValue() != UiExperimentMode::kSceneInsert ||
      r3.u32 == 0u) {
    return false;
  }
  const bool readable = PinyonShiftGuestRangeReadable(r3.u32, 4u);
  const uint32_t vtable = readable ? LoadGuestU32(r3.u32) : 0u;
  const uint32_t metadata =
      vtable >= 4u && PinyonShiftGuestRangeReadable(vtable - 4u, 4u)
          ? LoadGuestU32(vtable - 4u)
          : 0u;
  if (readable && metadata != 0u) {
    return false;
  }
  pinyon_shift::diagnostics::RecordEvent(
      "ui.scene.invalid_rtti_guarded",
      {{"caller", Hex32(static_cast<uint32_t>(lr))},
       {"object", Hex32(r3.u32)},
       {"readable", readable ? "1" : "0"},
       {"vtable", Hex32(vtable)},
       {"target", Hex32(r4.u32)},
       {"source_type", Hex32(r5.u32)},
       {"target_type", Hex32(r6.u32)},
       {"flags", Hex32(r7.u32)}});
  return false;
}

void PinyonShiftTraceUiInvalidRttiCast(PPCRegister& r3, PPCRegister& r4,
                                       PPCRegister& r5, PPCRegister& r6,
                                       PPCRegister& r7, uint64_t& lr) {
  (void)PinyonShiftGuardUiInvalidRttiCast(r3, r4, r5, r6, r7, lr);
}

void PinyonShiftTraceUiPauseButtonArrayLookup(PPCRegister& r3,
                                               PPCRegister& r28,
                                               PPCRegister& r29,
                                               PPCRegister& r30,
                                               uint64_t& lr) {
  if (UiExperimentModeValue() != UiExperimentMode::kSceneInsert) {
    return;
  }
  // The cloned row has no authored navigation-layout objects. The stock
  // helper returns unresolved node hashes in that case; represent the absent
  // optional interface as null so the caller takes its existing skip path.
  const uint32_t candidate_vtable =
      PinyonShiftGuestRangeReadable(r3.u32, 4u) ? LoadGuestU32(r3.u32) : 0u;
  if (static_cast<uint32_t>(lr) == 0x8281BF4Cu && r3.u32 != 0u &&
      candidate_vtable != 0x8224B790u) {
    pinyon_shift::diagnostics::RecordEvent(
        "ui.experiment.scene_insert.optional_navigation_absent", {});
    r3.u64 = 0u;
  }
  uint32_t tracked_index = UINT32_MAX;
  for (uint32_t index = 0; index < kUiExperimentTextTargets; ++index) {
    if (g_ui_experiment_buttons[index] == r30.u32) {
      tracked_index = index;
      break;
    }
  }
  pinyon_shift::diagnostics::RecordEvent(
      "ui.scene.insert_button_lookup",
      {{"caller", Hex32(static_cast<uint32_t>(lr))},
       {"button", Hex32(r30.u32)},
       {"result", Hex32(r3.u32)},
       {"outer_index", Hex32(r28.u32)},
       {"inner_index", Hex32(r29.u32)},
       {"tracked_index", Hex32(tracked_index)},
       {"readable", PinyonShiftGuestRangeReadable(r3.u32, 4u) ? "1" : "0"},
       {"head", PinyonShiftGuestRangeReadable(r3.u32, 4u)
                    ? Hex32(LoadGuestU32(r3.u32))
                    : ""}});
}

void PinyonShiftTraceUiListSelectionSet(PPCRegister& r3, PPCRegister& r4) {
  if (!UiTraceEnabled() ||
      g_ui_list_selection_trace_count.fetch_add(1, std::memory_order_relaxed) >=
          512u) {
    return;
  }
  pinyon_shift::diagnostics::RecordEvent(
      "ui.list.selection_set",
      {{"list", Hex32(r3.u32)},
       {"value", Hex32(r4.u32)},
       {"current", UiProbeField(r3.u32, 340u)},
       {"pending", UiProbeField(r3.u32, 344u)},
       {"begin", UiProbeField(r3.u32, 348u)},
       {"end", UiProbeField(r3.u32, 352u)}});
}

void PinyonShiftTraceUiListSelectionGet(PPCRegister& r3) {
  if (!UiTraceEnabled() ||
      g_ui_list_selection_trace_count.fetch_add(1, std::memory_order_relaxed) >=
          512u) {
    return;
  }
  pinyon_shift::diagnostics::RecordEvent(
      "ui.list.selection_get",
      {{"list", Hex32(r3.u32)},
       {"current", UiProbeField(r3.u32, 340u)},
       {"pending", UiProbeField(r3.u32, 344u)},
       {"begin", UiProbeField(r3.u32, 348u)},
       {"end", UiProbeField(r3.u32, 352u)}});
}

void PinyonShiftTraceUiTextValue(PPCRegister& r3, PPCRegister& r4,
                                 PPCRegister& r5) {
  if (!UiTraceEnabled() || !PinyonShiftGuestRangeReadable(r3.u32, 12u)) {
    return;
  }
  if (LoadGuestU32(r3.u32) != 0x82026B38u) {
    return;
  }
  // The receiver may be any of the three verified CUI4TextElement subobjects
  // of an observed pause button; earlier probes only matched +252.
  constexpr std::array<uint32_t, 3> kElementOffsets = {164u, 252u, 264u};
  const uint32_t button_count = std::min<uint32_t>(
      g_ui_experiment_buttons_count.load(std::memory_order_relaxed),
      kUiExperimentTextTargets);
  for (uint32_t index = 0; index < button_count; ++index) {
    const uint32_t button = g_ui_experiment_buttons[index];
    if (button == 0u) {
      continue;
    }
    for (const uint32_t offset : kElementOffsets) {
      if (button + offset != r3.u32) {
        continue;
      }
      if (g_ui_text_value_trace_count.fetch_add(1, std::memory_order_relaxed) >=
          256u) {
        return;
      }
      pinyon_shift::diagnostics::RecordEvent(
          "ui.pause_button.text_set",
          {{"button", Hex32(button)},
           {"element_offset", std::to_string(offset)},
           {"argument_4", Hex32(r4.u32)},
           {"argument_5", Hex32(r5.u32)},
           {"argument_4_ascii", PinyonShiftReadGuestAscii(r4.u32, 32u)},
           {"argument_5_ascii", PinyonShiftReadGuestAscii(r5.u32, 32u)},
           {"field_4", Hex32(LoadGuestU32(r3.u32 + 4u))},
           {"field_8", Hex32(LoadGuestU32(r3.u32 + 8u))}});
      return;
    }
  }
  // Record any other text-element receiver so a miss stays distinguishable
  // from "the helper was never called on this route".
  if (g_ui_text_value_trace_count.fetch_add(1, std::memory_order_relaxed) >=
      256u) {
    return;
  }
  pinyon_shift::diagnostics::RecordEvent(
      "ui.text.value",
      {{"object", Hex32(r3.u32)},
       {"argument_4", Hex32(r4.u32)},
       {"argument_5", Hex32(r5.u32)},
       {"argument_4_ascii", PinyonShiftReadGuestAscii(r4.u32, 32u)},
       {"argument_5_ascii", PinyonShiftReadGuestAscii(r5.u32, 32u)},
       {"field_4", Hex32(LoadGuestU32(r3.u32 + 4u))},
       {"field_8", Hex32(LoadGuestU32(r3.u32 + 8u))}});
}

void PinyonShiftTraceUiPauseButtonTextGet(PPCRegister& r3,
                                           PPCRegister& r4) {
  if (!UiTraceEnabled() ||
      !PinyonShiftGuestRangeReadable(r3.u32, 116u) ||
      LoadGuestU32(r3.u32) != 0x8203363Cu ||
      g_ui_pause_button_text_get_trace_count.fetch_add(
          1, std::memory_order_relaxed) >= 256u) {
    return;
  }
  pinyon_shift::diagnostics::RecordEvent(
      "ui.pause_button.text_get",
      {{"button", Hex32(r3.u32)},
       {"argument_4", Hex32(r4.u32)},
       {"field_84", Hex32(LoadGuestU32(r3.u32 + 84u))},
       {"field_88", Hex32(LoadGuestU32(r3.u32 + 88u))},
       {"field_92", Hex32(LoadGuestU32(r3.u32 + 92u))},
       {"field_96", Hex32(LoadGuestU32(r3.u32 + 96u))},
       {"text_vtable", PinyonShiftGuestRangeReadable(r3.u32 + 252u, 4u)
                           ? Hex32(LoadGuestU32(r3.u32 + 252u))
                           : std::string("00000000")}});
}

void TraceUiMenuDispatch(std::string_view address, PPCRegister& r3,
                         PPCRegister& r4, PPCRegister& r5) {
  if (!UiTraceEnabled() ||
      g_ui_menu_dispatch_trace_count.fetch_add(1, std::memory_order_relaxed) >=
          512u) {
    return;
  }
  const auto read = [](uint32_t address) {
    return PinyonShiftGuestRangeReadable(address, 4u)
               ? Hex32(LoadGuestU32(address))
               : std::string("00000000");
  };
  const uint32_t child = PinyonShiftGuestRangeReadable(r3.u32 + 312u, 4u)
                             ? LoadGuestU32(r3.u32 + 312u)
                             : 0u;
  const uint32_t child_subobject = child + 8u;
  const uint32_t child_sub_vtable = PinyonShiftGuestRangeReadable(
                                       child_subobject, 4u)
                                       ? LoadGuestU32(child_subobject)
                                       : 0u;
  pinyon_shift::diagnostics::RecordEvent(
      "ui.menu.dispatch",
      {{"address", address},
       {"object", Hex32(r3.u32)},
       {"argument", Hex32(r4.u32)},
       {"value", Hex32(r5.u32)},
       {"vtable", read(r3.u32)},
       {"child_312", Hex32(child)},
       {"child_vtable", read(child)},
       {"child_subobject", Hex32(child_subobject)},
       {"child_sub_vtable", Hex32(child_sub_vtable)},
       {"child_slot_0", read(child_sub_vtable)},
       {"child_slot_1", read(child_sub_vtable + 4u)},
       {"value_vtable", read(r5.u32)}});
}

void PinyonShiftTraceUiMenuDispatch(PPCRegister& r3, PPCRegister& r4,
                                    PPCRegister& r5) {
  TraceUiMenuDispatch("82806DD0", r3, r4, r5);
}

void PinyonShiftTraceUiMenuDispatch2(PPCRegister& r3, PPCRegister& r4,
                                     PPCRegister& r5) {
  TraceUiMenuDispatch("82806E50", r3, r4, r5);
}

void PinyonShiftTraceUiListConstructed(PPCRegister& r3, PPCRegister& r4,
                                       PPCRegister& r31) {
  if (!UiTraceEnabled()) {
    return;
  }
  pinyon_shift::diagnostics::RecordEvent(
      "ui.list.constructed",
      {{"address", "828116C8"},
       {"object", Hex32(r3.u32)},
       {"owner", Hex32(r4.u32)},
       {"saved_object", Hex32(r31.u32)},
       {"vtable", PinyonShiftGuestRangeReadable(r31.u32, 4u)
                       ? Hex32(LoadGuestU32(r31.u32))
                       : std::string("00000000")},
      });
}

// Records the contract argument and caller of the PAUSE_MENU_BUTTON factory.
// The return address names the code that resolves the authored contract table,
// which is the seam a bounded insertion probe has to work through.
void PinyonShiftTraceUiButtonFactory(PPCRegister& r3, PPCRegister& r4,
                                     uint64_t& lr) {
  if (!UiTraceEnabled()) {
    return;
  }
  const auto read_field = [&](uint32_t offset) {
    return PinyonShiftGuestRangeReadable(r3.u32 + offset, 4u)
               ? Hex32(LoadGuestU32(r3.u32 + offset))
               : std::string("00000000");
  };
  pinyon_shift::diagnostics::RecordEvent(
      "ui.button.factory",
      {{"address", "82651438"},
       {"argument", Hex32(r3.u32)},
       {"argument_vtable", read_field(0u)},
       {"argument_field_4", read_field(4u)},
       {"argument_field_8", read_field(8u)},
       {"argument_field_12", read_field(12u)},
       {"argument_ascii", PinyonShiftReadGuestAscii(r3.u32, 32u)},
       {"second_argument", Hex32(r4.u32)},
       {"return_address", Hex32(static_cast<uint32_t>(lr))}});
}

// Records the caller of the per-child UI4 component builder, which names the
// loop that walks authored scene children (the insertion point for an extra
// item) and the child record it is processing.
void PinyonShiftTraceUiComponentBuilder(PPCRegister& r3, PPCRegister& r4,
                                        uint64_t& lr) {
  if (!UiTraceEnabled() ||
      g_ui_component_trace_count.fetch_add(1, std::memory_order_relaxed) >=
          256u) {
    return;
  }
  const auto read_field = [&](uint32_t offset) {
    return PinyonShiftGuestRangeReadable(r4.u32 + offset, 4u)
               ? Hex32(LoadGuestU32(r4.u32 + offset))
               : std::string("00000000");
  };
  pinyon_shift::diagnostics::RecordEvent(
      "ui.component.builder",
      {{"address", "82E7A238"},
       {"owner", Hex32(r3.u32)},
       {"record", Hex32(r4.u32)},
       {"record_vtable", read_field(0u)},
       {"record_field_4", read_field(4u)},
       {"record_field_8", read_field(8u)},
       {"record_field_12", read_field(12u)},
       {"return_address", Hex32(static_cast<uint32_t>(lr))}});
}

// One storage form an LSB2 string pool can use. The pool holds 16-bit code
// units, so the file's little-endian bytes appear byte-for-byte or byte-swapped
// once the stream layer has normalized them; a narrow pool would be ASCII.
struct UiLabelEncoding {
  std::string_view name;
  uint32_t stride;
  bool big_endian;
};
constexpr std::array<UiLabelEncoding, 3> kUiLabelEncodings = {{
    {"ascii", 1u, false},
    {"utf16le", 2u, false},
    {"utf16be", 2u, true},
}};

std::string EncodeUiLabelPattern(std::string_view text,
                                 const UiLabelEncoding& encoding) {
  std::string pattern;
  pattern.reserve(text.size() * encoding.stride);
  for (const char character : text) {
    if (encoding.stride == 2u && encoding.big_endian) {
      pattern.push_back('\0');
    }
    pattern.push_back(character);
    if (encoding.stride == 2u && !encoding.big_endian) {
      pattern.push_back('\0');
    }
  }
  return pattern;
}

std::string ReadUiLabelAt(uint32_t address, const UiLabelEncoding& encoding,
                          uint32_t length) {
  const uint32_t char_offset =
      encoding.stride == 2u && encoding.big_endian ? 1u : 0u;
  std::string text;
  text.reserve(length);
  for (uint32_t index = 0; index < length; ++index) {
    const uint8_t byte = LoadGuestU8(
        address + static_cast<uint32_t>(index * encoding.stride) + char_offset);
    text.push_back(byte >= 0x20u && byte <= 0x7Eu ? static_cast<char>(byte)
                                                  : '.');
  }
  return text;
}

// Rewrite every configured literal found in one LSB2 chunk. The chunk is copied
// into host memory once, so the sweep is one bounded pass over the payload; the
// same-length write plus the search for the source literal make the patch
// idempotent. `raw_copy` is the reader's ownership flag: only that form holds
// the verbatim payload (the other form expands the chunk into a fixed-stride
// table, where a text write would corrupt neighboring entries).
uint32_t ApplyUiStringTableLabelPatch(uint32_t buffer, uint32_t size,
                                      bool raw_copy, bool verbose) {
  uint32_t total_patched = 0;
  std::string bytes(size, '\0');
  for (uint32_t offset = 0; offset < size; ++offset) {
    bytes[offset] = static_cast<char>(LoadGuestU8(buffer + offset));
  }
  for (const UiLabelPatch& patch : kUiLabelPatches) {
    for (const UiLabelEncoding& encoding : kUiLabelEncodings) {
      const std::string pattern = EncodeUiLabelPattern(patch.source, encoding);
      const std::string replacement =
          EncodeUiLabelPattern(patch.replacement, encoding);
      if (pattern.size() != replacement.size()) {
        continue;
      }
      uint32_t hits = 0;
      uint32_t patched = 0;
      uint32_t first_address = 0;
      for (std::size_t at = bytes.find(pattern); at != std::string::npos;
           at = bytes.find(pattern, at + 1u)) {
        if (hits == 0u) {
          first_address = buffer + static_cast<uint32_t>(at);
        }
        ++hits;
        if (!raw_copy || patched >= kUiStringChunkMaximumPatchHits) {
          continue;
        }
        for (std::size_t index = 0; index < replacement.size(); ++index) {
          StoreGuestU8(buffer + static_cast<uint32_t>(at + index),
                       static_cast<uint8_t>(replacement[index]));
        }
        ++patched;
      }
      if (hits == 0u) {
        continue;
      }
      total_patched += patched;
      g_ui_string_patch_count.fetch_add(patched, std::memory_order_relaxed);
      if (!verbose) {
        continue;
      }
      pinyon_shift::diagnostics::RecordEvent(
          "ui.experiment.string_table_patch",
          {{"literal", std::string(patch.source)},
           {"replacement", std::string(patch.replacement)},
           {"encoding", std::string(encoding.name)},
           {"table", g_ui_string_current_path},
           {"hits", std::to_string(hits)},
           {"patched", std::to_string(patched)},
           {"address", Hex32(first_address)},
           {"after", ReadUiLabelAt(first_address, encoding,
                                   static_cast<uint32_t>(patch.source.size()))},
           {"source_present",
            bytes.find(pattern) != std::string::npos ? "1" : "0"}});
    }
  }
  if (!verbose) {
    return total_patched;
  }
  // Report the two literals that were looked for and not found in any form, so
  // a run that patches nothing still says what the chunk held.
  for (const UiLabelPatch& patch : kUiLabelPatches) {
    bool present = false;
    for (const UiLabelEncoding& encoding : kUiLabelEncodings) {
      if (bytes.find(EncodeUiLabelPattern(patch.source, encoding)) !=
          std::string::npos) {
        present = true;
      }
    }
    if (present) {
      continue;
    }
    pinyon_shift::diagnostics::RecordEvent(
        "ui.experiment.string_table_absent",
        {{"literal", std::string(patch.source)},
         {"table", g_ui_string_current_path},
         {"buffer", Hex32(buffer)},
         {"size", std::to_string(size)},
         {"head", ReadUiLabelAt(buffer, kUiLabelEncodings[0],
                                std::min(size, 32u))}});
  }
  return total_patched;
}

// 0x82CAFFA0 is just after the loader appended the ".str" suffix to the table
// path, so the stack string at r1+96 holds the final VFS path.
void PinyonShiftTraceUiStringTableLoad(PPCRegister& r1) {
  if (UiExperimentModeValue() != UiExperimentMode::kLabelPatch) {
    return;
  }
  // MSVC std::string: data/capacity at +0/+20, size at +16.
  const uint32_t object = r1.u32 + 96u;
  if (!PinyonShiftGuestRangeReadable(object, 24u)) {
    return;
  }
  const uint32_t capacity = LoadGuestU32(object + 20u);
  const uint32_t length = std::min(LoadGuestU32(object + 16u), 160u);
  const uint32_t data =
      capacity >= 16u ? LoadGuestU32(object) : object;
  std::string path;
  if (PinyonShiftGuestRangeReadable(data, length)) {
    path.reserve(length);
    for (uint32_t index = 0; index < length; ++index) {
      path.push_back(static_cast<char>(LoadGuestU8(data + index)));
    }
  }
  // The path is the label of the next chunk even when its event is capped.
  g_ui_string_current_path = path;
  if (g_ui_string_load_count.fetch_add(1, std::memory_order_relaxed) >=
      kUiStringTraceLimit) {
    return;
  }
  pinyon_shift::diagnostics::RecordEvent(
      "ui.experiment.string_table_load",
      {{"address", "82CAFFA0"}, {"path", path}});
}

// 0x82CAC740 is the instruction after the payload read inside sub_82CAC5B8:
// r30 is the payload start, r29 its length, r26 the ownership/verbatim flag.
void PinyonShiftTraceUiStringTableChunk(PPCRegister& r3, PPCRegister& r26,
                                        PPCRegister& r29, PPCRegister& r30,
                                        PPCRegister& r31) {
  if (UiExperimentModeValue() != UiExperimentMode::kLabelPatch) {
    return;
  }
  const uint32_t buffer = r30.u32;
  const uint32_t size = r29.u32;
  const uint32_t index =
      g_ui_string_chunk_count.fetch_add(1, std::memory_order_relaxed);
  if (buffer == 0u || size < 8u || size > kUiStringChunkMaximumBytes ||
      !PinyonShiftGuestRangeReadable(buffer, size)) {
    return;
  }
  const bool verbose = index < kUiStringTraceLimit;
  const bool raw_copy = r26.u32 != 0u;
  if (verbose) {
    pinyon_shift::diagnostics::RecordEvent(
        "ui.experiment.string_table_chunk",
        {{"address", "82CAC740"},
         {"index", std::to_string(index)},
         {"table", g_ui_string_current_path},
         {"buffer", Hex32(buffer)},
         {"size", std::to_string(size)},
         {"read", std::to_string(r3.u32)},
         {"handle", Hex32(r31.u32)},
         {"form", raw_copy ? "verbatim" : "expanded"},
         {"head", ReadUiLabelAt(buffer, kUiLabelEncodings[0],
                                std::min(size, 32u))}});
  }
  // Every chunk is patched; only the recording above is capped. Tables load in
  // name order, so a cap that skipped the write would miss the pause table.
  if (ApplyUiStringTableLabelPatch(buffer, size, raw_copy, verbose) > 0u) {
    g_ui_string_buffer.store(buffer, std::memory_order_relaxed);
    g_ui_string_buffer_size.store(size, std::memory_order_relaxed);
    g_ui_string_patched_path = g_ui_string_current_path;
  }
}

// 0x82CB00AC is where the string-table loader stores the parsed handle, so this
// records which allocation the localization manager keeps.
void PinyonShiftTraceUiStringTableParsed(PPCRegister& r3) {
  if (UiExperimentModeValue() != UiExperimentMode::kLabelPatch) {
    return;
  }
  if (g_ui_string_parsed_count.fetch_add(1, std::memory_order_relaxed) >=
      kUiStringTraceLimit) {
    return;
  }
  const auto field = [&](uint32_t offset) {
    return PinyonShiftGuestRangeReadable(r3.u32 + offset, 4u)
               ? Hex32(LoadGuestU32(r3.u32 + offset))
               : std::string("00000000");
  };
  pinyon_shift::diagnostics::RecordEvent(
      "ui.experiment.string_table_parsed",
      {{"address", "82CB00AC"},
       {"handle", Hex32(r3.u32)},
       {"field_4", field(4u)},
       {"field_8", field(8u)},
       {"field_12", field(12u)},
       {"field_16", field(16u)}});
}

// Read the recorded chunk back at the first pause interaction so the run shows
// whether the patched text is still in the pool when the menu is built.
void VerifyUiStringTablePatch() {
  const uint32_t buffer = g_ui_string_buffer.load(std::memory_order_relaxed);
  const uint32_t size = g_ui_string_buffer_size.load(std::memory_order_relaxed);
  if (buffer == 0u || size == 0u ||
      !PinyonShiftGuestRangeReadable(buffer, size)) {
    pinyon_shift::diagnostics::RecordEvent(
        "ui.experiment.string_table_patch_state",
        {{"buffer", Hex32(buffer)}, {"size", std::to_string(size)},
         {"state", "unreadable"}});
    return;
  }
  std::string bytes(size, '\0');
  for (uint32_t offset = 0; offset < size; ++offset) {
    bytes[offset] = static_cast<char>(LoadGuestU8(buffer + offset));
  }
  for (const UiLabelPatch& patch : kUiLabelPatches) {
    const auto count = [&](std::string_view needle) {
      uint32_t hits = 0;
      for (std::size_t at = bytes.find(needle); at != std::string::npos;
           at = bytes.find(needle, at + 1u)) {
        ++hits;
      }
      return hits;
    };
    for (const UiLabelEncoding& encoding : kUiLabelEncodings) {
      pinyon_shift::diagnostics::RecordEvent(
          "ui.experiment.string_table_patch_state",
          {{"buffer", Hex32(buffer)},
           {"size", std::to_string(size)},
           {"state", "readable"},
           {"table", g_ui_string_patched_path},
           {"encoding", std::string(encoding.name)},
           {"literal", std::string(patch.source)},
           {"literal_hits",
            std::to_string(count(EncodeUiLabelPattern(patch.source, encoding)))},
           {"replacement", std::string(patch.replacement)},
           {"replacement_hits", std::to_string(count(
                                    EncodeUiLabelPattern(patch.replacement,
                                                         encoding)))}});
    }
  }
}

// The wrapper sub_82CB1FB0 resolves a table key to text at 0x82CB2018 (r3 is
// the resolved string, r29 the key), so that continuation is the seam a label
// replacement has to survive.
bool UiLabelTextIsInteresting(std::string_view text) {
  static constexpr std::array<std::string_view, 8> kFragments = {
      "multiplayer", "photo mode", "pinyonshift", "pinyon mod",
      "pause",       "resume",     "message",    "profile",
  };
  for (const std::string_view fragment : kFragments) {
    if (text.size() < fragment.size()) {
      continue;
    }
    for (std::size_t at = 0; at + fragment.size() <= text.size(); ++at) {
      bool match = true;
      for (std::size_t index = 0; index < fragment.size(); ++index) {
        const char left = text[at + index];
        const char lowered =
            left >= 'A' && left <= 'Z' ? static_cast<char>(left + 32) : left;
        if (lowered != fragment[index]) {
          match = false;
          break;
        }
      }
      if (match) {
        return true;
      }
    }
  }
  return false;
}

void PinyonShiftTraceUiStringLookup(PPCRegister& r3, PPCRegister& r29) {
  if (UiExperimentModeValue() != UiExperimentMode::kLabelPatch) {
    return;
  }
  if (g_ui_string_lookup_count.load(std::memory_order_relaxed) >=
      kUiStringTraceLimit) {
    return;
  }
  const std::string resolved =
      PinyonShiftGuestRangeReadable(r3.u32, 48u)
          ? ReadUiLabelAt(r3.u32, kUiLabelEncodings[2], 24u)
          : std::string();
  std::string key;
  if (PinyonShiftGuestRangeReadable(r29.u32, 2u)) {
    key = ReadUiLabelAt(r29.u32, kUiLabelEncodings[0], 48u);
  }
  if (!UiLabelTextIsInteresting(resolved) && !UiLabelTextIsInteresting(key)) {
    return;
  }
  g_ui_string_lookup_count.fetch_add(1, std::memory_order_relaxed);
  pinyon_shift::diagnostics::RecordEvent(
      "ui.experiment.string_lookup",
      {{"address", "82CB2018"},
       {"key", key},
       {"resolved", resolved},
       {"result", Hex32(r3.u32)},
       {"key_address", Hex32(r29.u32)}});
}

void PinyonShiftTraceUiPauseButtonConstructed(PPCRegister& r3,
                                               PPCRegister& r31) {
  const UiExperimentMode experiment = UiExperimentModeValue();
  if (!UiTraceEnabled() && experiment == UiExperimentMode::kNone) {
    return;
  }
  const uint32_t button = r31.u32;
  const uint32_t slot =
      g_ui_pause_button_count.fetch_add(1, std::memory_order_relaxed);
  if (slot < g_ui_pause_buttons.size()) {
    g_ui_pause_buttons[slot] = button;
  }
  if (experiment == UiExperimentMode::kLabelPatch && slot == 0u) {
    VerifyUiStringTablePatch();
  }
  if (experiment == UiExperimentMode::kHideFirst && slot == 0u) {
    ++g_ui_experiment_generation;
    if (g_ui_experiment_api
            .SceneReady("pause_menu", g_ui_experiment_generation,
                        &g_ui_experiment_scene) == pinyon_shift::ui::Status::kOk &&
        g_ui_experiment_api.SetVisible(g_ui_experiment_scene,
                                       "pause.menu.first", false) ==
            pinyon_shift::ui::Status::kOk) {
      g_ui_experiment_button = button;
    }
  }
  if (experiment == UiExperimentMode::kTextProbe) {
    if (slot == 0u) {
      ++g_ui_experiment_generation;
      g_ui_experiment_buttons_count.store(0u, std::memory_order_relaxed);
      if (g_ui_experiment_api.SceneReady("pause_menu",
                                         g_ui_experiment_generation,
                                         &g_ui_experiment_scene) ==
          pinyon_shift::ui::Status::kOk) {
        // The probe is read-only; the requested label exercises the host queue
        // so the request path stays covered while the write target is open.
        g_ui_experiment_buttons_queued.store(
            g_ui_experiment_api.SetText(
                g_ui_experiment_scene, "pause.menu.label",
                std::string(kUiExperimentRequestedLabel)) ==
                pinyon_shift::ui::Status::kOk,
            std::memory_order_relaxed);
      }
    }
    const uint32_t index =
        g_ui_experiment_buttons_count.fetch_add(1, std::memory_order_relaxed);
    if (index < kUiExperimentTextTargets &&
        PinyonShiftGuestRangeReadable(button + 164u, 112u)) {
      g_ui_experiment_buttons[index] = button;
    }
  }
  if (!UiTraceEnabled()) {
    return;
  }
  if (g_ui_pause_button_trace_count.fetch_add(1, std::memory_order_relaxed) >=
      128u) {
    return;
  }
  const uint32_t text = button + 252u;
  if (!PinyonShiftGuestRangeReadable(text, 4u)) {
    return;
  }
  const auto read_field = [&](uint32_t offset) {
    return PinyonShiftGuestRangeReadable(text + offset, 4u)
               ? Hex32(LoadGuestU32(text + offset))
               : std::string("00000000");
  };
  const auto read_inline_text = [&]() {
    std::string value;
    value.reserve(16u);
    for (uint32_t offset = 84u; offset < 100u; ++offset) {
      if (!PinyonShiftGuestRangeReadable(text + offset, 1u)) {
        break;
      }
      const uint8_t byte = LoadGuestU8(text + offset);
      if (byte == 0u) {
        break;
      }
      if (byte < 0x20u || byte > 0x7Eu) {
        return std::string();
      }
      value.push_back(static_cast<char>(byte));
    }
    return value;
  };
  pinyon_shift::diagnostics::RecordEvent(
      "ui.pause_button.constructed",
      {{"address", "8264FC08"},
       {"button", Hex32(button)},
       {"text", Hex32(text)},
       {"text_vtable", read_field(0u)},
       {"button_field_84", PinyonShiftGuestRangeReadable(button + 84u, 4u)
                                 ? Hex32(LoadGuestU32(button + 84u))
                                 : std::string("00000000")},
       {"label_resource_vtable",
        PinyonShiftGuestRangeReadable(button + 84u, 4u) &&
                PinyonShiftGuestRangeReadable(LoadGuestU32(button + 84u), 4u)
            ? Hex32(LoadGuestU32(LoadGuestU32(button + 84u)))
            : std::string("00000000")},
       {"button_field_108", PinyonShiftGuestRangeReadable(button + 108u, 4u)
                                  ? Hex32(LoadGuestU32(button + 108u))
                                  : std::string("00000000")},
       {"button_field_112", PinyonShiftGuestRangeReadable(button + 112u, 4u)
                                  ? Hex32(LoadGuestU32(button + 112u))
                                  : std::string("00000000")},
       {"button_field_160", PinyonShiftGuestRangeReadable(button + 160u, 1u)
                                  ? Hex32(LoadGuestU8(button + 160u))
                                  : std::string("00")},
       {"button_field_235", PinyonShiftGuestRangeReadable(button + 235u, 1u)
                                  ? Hex32(LoadGuestU8(button + 235u))
                                  : std::string("00")},
       {"text_field_4", read_field(4u)},
       {"text_field_8", read_field(8u)},
       {"text_field_32", read_field(32u)},
       {"text_field_84", read_field(84u)},
       {"text_field_88", read_field(88u)},
       {"text_field_92", read_field(92u)},
       {"text_field_96", read_field(96u)},
       {"text_inline", read_inline_text()}});
}

// Records the caller of the per-child builder when the call enters at the
// interior dispatch address 0x82E7A240 instead of the function head. The menu
// item batches do that, so this is the only place that names the code walking
// a page's authored element records for the pause menu.
void PinyonShiftTraceUiItemBuilderEntry(PPCRegister& r3, PPCRegister& r4,
                                        uint64_t& lr) {
  if (!UiTraceEnabled()) {
    return;
  }
  // Calls that enter at the function head fall through this instruction with
  // the internal return address; only an interior entry keeps the caller's
  // return address here.
  const uint32_t caller = static_cast<uint32_t>(lr);
  if (caller == 0x82E7A240u) {
    return;
  }
  if (g_ui_insert_entry_trace_count.fetch_add(1, std::memory_order_relaxed) >=
      64u) {
    return;
  }
  pinyon_shift::diagnostics::RecordEvent(
      "ui.item.builder_entry",
      {{"address", "82E7A240"},
       {"frame",
        std::to_string(pinyon_shift::fh1_render_test::CurrentFrame())},
       {"owner", Hex32(r3.u32)},
       {"record", Hex32(r4.u32)},
       {"caller", Hex32(caller)},
       {"record_name_hash", PinyonShiftGuestRangeReadable(r4.u32, 4u)
                                ? Hex32(LoadGuestU32(r4.u32))
                                : std::string("00000000")}});
}

// Diagnostic probes for the per-child builder's dispatch chunks. The menu-item
// path enters the shared tail of sub_82E7A238 without passing the function
// head, so these record which chunk it enters and with what register state.
// Each probe logs only inside the pause window to keep the budget for the
// item batch and not the startup scene build.
void PinyonShiftUiRecordBuilderChunk(const char* chunk, uint32_t r1, uint32_t r3,
                                     uint32_t r4, uint32_t r28, uint32_t r31,
                                     uint64_t lr) {
  if (!UiTraceEnabled()) {
    return;
  }
  const uint64_t frame = pinyon_shift::fh1_render_test::CurrentFrame();
  if (frame < 700u) {
    return;
  }
  if (g_ui_insert_entry_trace_count.fetch_add(1, std::memory_order_relaxed) >=
      64u) {
    return;
  }
  pinyon_shift::diagnostics::RecordEvent(
      "ui.item.builder_chunk",
      {{"chunk", chunk},
       {"frame", std::to_string(frame)},
       {"r1", Hex32(r1)},
       {"back_chain", PinyonShiftGuestRangeReadable(r1, 4u)
                          ? Hex32(LoadGuestU32(r1))
                          : std::string("00000000")},
       {"r3", Hex32(r3)},
       {"r4", Hex32(r4)},
       {"r28", Hex32(r28)},
       {"r31", Hex32(r31)},
       {"lr", Hex32(static_cast<uint32_t>(lr))}});
}

// Live deserializer state captured at 0x82F268D0 (the item construction site of
// sub_82F26560) while the insertion experiment runs: r24 is the document that owns
// the item records (arena at +84, pool vector at +92 / data +124 / size +132), r25
// the element the component builder is called on, r26 the item record the builder
// receives and r31 the section context whose +92 vector is the record pool the
// stream's parent index resolves through. r26 proves that the published document is
// the one that produced the record the builder is now working on: both allocators
// store every new record at document+80, so a published document whose +80 is this
// record is this record's own document.
std::atomic<uint32_t> g_ui_insert_document{};
std::atomic<uint32_t> g_ui_insert_element{};
std::atomic<uint32_t> g_ui_insert_section{};
std::atomic<uint32_t> g_ui_insert_record{};
std::atomic<uint32_t> g_ui_deserialize_trace_count{};

// Item construction site of the scene deserializer sub_82F26560 (0x82F268D0).
// Every parsed item passes here; the indirect call four instructions later is the
// one that enters the component builder sub_82E7A238. The experiment reads the
// document, element and section pointers, tracing reads their state so a run
// shows what one authored item changes. Read-only.
void PinyonShiftTraceUiItemBuildCall(PPCRegister& r24, PPCRegister& r25,
                                     PPCRegister& r26, PPCRegister& r29,
                                     PPCRegister& r31) {
  if (UiExperimentModeValue() == UiExperimentMode::kInsertItem) {
    g_ui_insert_document.store(r24.u32, std::memory_order_relaxed);
    g_ui_insert_element.store(r25.u32, std::memory_order_relaxed);
    g_ui_insert_section.store(r31.u32, std::memory_order_relaxed);
    g_ui_insert_record.store(r26.u32, std::memory_order_relaxed);
  }
  if (!UiTraceEnabled() ||
      g_ui_deserialize_trace_count.fetch_add(1, std::memory_order_relaxed) >=
          32u) {
    return;
  }
  const auto word = [](uint32_t address) {
    return PinyonShiftGuestRangeReadable(address, 4u)
               ? Hex32(LoadGuestU32(address))
               : std::string("00000000");
  };
  pinyon_shift::diagnostics::RecordEvent(
      "ui.item.build_call",
      {{"frame",
        std::to_string(pinyon_shift::fh1_render_test::CurrentFrame())},
       {"document", Hex32(r24.u32)},
       {"document_12_stream", word(r24.u32 + 12u)},
       {"document_80_last_record", word(r24.u32 + 80u)},
       {"document_84_arena", word(r24.u32 + 84u)},
       {"document_92_pool", word(r24.u32 + 92u)},
       {"document_124_pool_data", word(r24.u32 + 124u)},
       {"document_128_pool_capacity", word(r24.u32 + 128u)},
       {"document_132_pool_size", word(r24.u32 + 132u)},
       {"element", Hex32(r25.u32)},
       {"element_vtable", word(r25.u32)},
       {"element_field_4", word(r25.u32 + 4u)},
       {"record", Hex32(r26.u32)},
       {"record_name_hash", word(r26.u32)},
       {"record_parent", word(r26.u32 + 12u)},
       {"has_builder_call", (r29.u32 & 0xFFu) != 0u ? "1" : "0"},
       {"section", Hex32(r31.u32)},
       {"section_vtable", word(r31.u32)},
       {"section_92_pool", word(r31.u32 + 92u)},
       {"section_124_pool_data", word(r31.u32 + 124u)},
       {"section_132_pool_size", word(r31.u32 + 132u)}});
}


#define PINYON_UI_BUILDER_CHUNK_PROBE(suffix, chunk)                       \
  void PinyonShiftUiBuilderChunk##suffix(                                  \
      PPCRegister& r1, PPCRegister& r3, PPCRegister& r4, PPCRegister& r28, \
      PPCRegister& r31, uint64_t& lr) {                                    \
    PinyonShiftUiRecordBuilderChunk(chunk, r1.u32, r3.u32, r4.u32, r28.u32, \
                                    r31.u32, lr);                          \
  }

PINYON_UI_BUILDER_CHUNK_PROBE(260, "82E7A260")
PINYON_UI_BUILDER_CHUNK_PROBE(27C, "82E7A27C")
PINYON_UI_BUILDER_CHUNK_PROBE(290, "82E7A290")
PINYON_UI_BUILDER_CHUNK_PROBE(2A0, "82E7A2A0")
PINYON_UI_BUILDER_CHUNK_PROBE(304, "82E7A304")
PINYON_UI_BUILDER_CHUNK_PROBE(310, "82E7A310")
PINYON_UI_BUILDER_CHUNK_PROBE(31C, "82E7A31C")
PINYON_UI_BUILDER_CHUNK_PROBE(324, "82E7A324")
PINYON_UI_BUILDER_CHUNK_PROBE(32C, "82E7A32C")

// --- Pause-item insertion (UI-04 insertion half) ---------------------------
//
// The title builds each authored element record into a live component inside
// the per-child builder sub_82E7A238: it allocates a 28-byte CUI4CustomObject
// descriptor, resolves the record's contract name into the stack object at
// r1+96, calls the create-by-name entry sub_82E78078, and then links the
// (descriptor, component) pair into the owner's +8 map and its +40 (and
// conditionally +56) child containers.
//
// The hook below sits on the create-by-name call site and re-runs that same
// builder for a copy of the current record. The copy keeps the owner's map key
// distinct from the stock item's record, so the added child coexists with
// every stock child instead of replacing one. The nested call is the title's
// own construction path: no descriptor layout, contract name, or container
// offset is reproduced in host code.
namespace {

// CPauseMenuButton's primary vtable. The constructor sub_8264FBA0 stores it at
// +0 (`lis r11,-32253; addi r11,r11,13988` = 0x820336A4); the +8 base at
// 0x8203363C is a secondary interface table, not the object's first word.
constexpr uint32_t kUiPauseMenuButtonVtable = 0x820336A4u;
constexpr uint32_t kUiComponentBuilderAddress = 0x82E7A238u;
constexpr uint32_t kUiInsertMaximumRecordBytes = 0x800u;
// Startup builds create dozens of non-button components before the pause items;
// keep a small generic sample and a separate budget for button creations.
constexpr uint32_t kUiInsertGenericTraceLimit = 16u;
constexpr uint32_t kUiInsertButtonTraceLimit = 32u;

std::atomic<bool> g_ui_insert_active{};
std::atomic<bool> g_ui_insert_done{};
std::atomic<uint32_t> g_ui_insert_button_count{};
std::atomic<uint32_t> g_ui_insert_generic_trace_count{};
std::atomic<uint32_t> g_ui_insert_button_trace_count{};
std::atomic<uint32_t> g_ui_record_dump_count{};
std::atomic<uint32_t> g_ui_owner_dump_count{};

// Ordinal of the create-by-name call to duplicate, counted over the calls that
// produced a CPauseMenuButton. The default matches the route's first item
// batch; PINYON_SHIFT_UI_INSERT_ORDINAL selects another one without a rebuild.
uint32_t UiInsertOrdinal() {
  static const uint32_t ordinal = [] {
    std::string_view requested;
#if defined(_WIN32)
    char* value = nullptr;
    size_t value_size = 0;
    if (_dupenv_s(&value, &value_size, "PINYON_SHIFT_UI_INSERT_ORDINAL") != 0) {
      return 1u;
    }
    const std::string owned = value ? std::string(value) : std::string();
    std::free(value);
    requested = owned;
#else
    const char* value = std::getenv("PINYON_SHIFT_UI_INSERT_ORDINAL");
    requested = value ? std::string_view(value) : std::string_view();
#endif
    uint32_t parsed = 0u;
    for (const char character : requested) {
      if (character < '0' || character > '9') {
        return 1u;
      }
      parsed = parsed * 10u + static_cast<uint32_t>(character - '0');
      if (parsed > 64u) {
        return 1u;
      }
    }
    return parsed == 0u ? 1u : parsed;
  }();
  return ordinal;
}

// Diagnostic switch: reuse the stock record as the added item's key instead of
// copying it. Default is a copy, which keeps the owner's map entry for the
// stock record intact.
bool UiInsertSharesRecord() {
  static const bool shares = [] {
#if defined(_WIN32)
    char* value = nullptr;
    size_t value_size = 0;
    if (_dupenv_s(&value, &value_size, "PINYON_SHIFT_UI_INSERT_SHARE_RECORD") !=
        0) {
      return false;
    }
    const bool result = value != nullptr && std::string_view(value) == "1";
    std::free(value);
    return result;
#else
    const char* value = std::getenv("PINYON_SHIFT_UI_INSERT_SHARE_RECORD");
    return value != nullptr && std::string_view(value) == "1";
#endif
  }();
  return shares;
}

// Invokes one recompiled guest function from a host hook. The nested context is
// a copy of the live context, so the callee sees the real thread pointer,
// nonvolatile registers and stack base, while the outer register state is left
// untouched. Only the FP control word is restored afterwards: the injected call
// must not change the mode the interrupted guest code has already committed to.
uint32_t CallGuestFunction(PPCContext& context, uint8_t* base, uint32_t address,
                           uint32_t argument0, uint32_t argument1,
                           uint32_t argument2 = 0u, uint32_t argument3 = 0u,
                           uint32_t argument4 = 0u, uint32_t argument5 = 0u) {
  PPCFunc* function = rex::runtime::ResolveIndirectFunction(address);
  if (function == nullptr) {
    return 0u;
  }
  const uint32_t saved_csr = context.fpscr.csr;
  PPCContext nested = context;
  nested.dispatch_address = 0;
  nested.lr = 0;
  nested.r1.u32 = context.r1.u32 - 0x70u;
  nested.r3.u64 = argument0;
  nested.r4.u64 = argument1;
  nested.r5.u64 = argument2;
  nested.r6.u64 = argument3;
  nested.r7.u64 = argument4;
  nested.r8.u64 = argument5;
  function(nested, base);
  const uint32_t result = nested.r3.u32;
  context.fpscr.csr = saved_csr;
  context.fpscr.setcsr(saved_csr);
  return result;
}

// The authored element record is a variable-size object: a flag word at +28
// whose bit 0 selects the entry-array base (+32 or +68), and a byte count at
// +31 for 8-byte entries. Copy everything the record describes plus one spare
// entry so the duplicate owns its own key and never aliases the stock tail.
// PINYON_SHIFT_UI_INSERT_SHARE_RECORD=1 reuses the stock record instead, which
// keeps the original map key; that variant is a diagnostic comparison only.
uint32_t UiElementRecordCopySize(uint32_t record) {
  if (!PinyonShiftGuestRangeReadable(record, 32u)) {
    return 0u;
  }
  const uint32_t header = LoadGuestU32(record + 28u);
  const uint32_t base = (header & 0x00010000u) != 0u ? 68u : 32u;
  const uint32_t count = header & 0xFFu;
  uint32_t size = base + count * 8u + 16u;
  size = (size + 15u) & ~15u;
  if (size > kUiInsertMaximumRecordBytes) {
    size = kUiInsertMaximumRecordBytes;
  }
  return PinyonShiftGuestRangeReadable(record, size) ? size : 0u;
}

// The document reserves 8192 bytes of property room per record (the
// sub_82F2DF08 / sub_82F2E870 call through the document's vtable slot 22), and
// any later pass that appends a property writes past the used entry count. Give
// the duplicate the same slack so a linked copy can never spill into the host
// heap allocation next to it.
constexpr uint32_t kUiInsertRecordAllocation = 0x2100u;

uint32_t CopyUiElementRecord(uint32_t source, uint32_t size) {
  auto* memory = rex::system::kernel_state()->memory();
  if (memory == nullptr) {
    return 0u;
  }
  const uint32_t destination =
      memory->SystemHeapAlloc(kUiInsertRecordAllocation, 16u);
  if (destination == 0u) {
    return 0u;
  }
  for (uint32_t offset = 0; offset < size; ++offset) {
    StoreGuestU8(destination + offset, LoadGuestU8(source + offset));
  }
  for (uint32_t offset = size; offset < kUiInsertRecordAllocation; ++offset) {
    StoreGuestU8(destination + offset, 0u);
  }
  return destination;
}

// The builder resolves the record's contract into an MSVC std::string at r1+96
// (inline buffer at +0, size at +16, capacity at +20) and hands it to the
// create-by-name entry, which looks the contract up in the UI registry. Reading
// it back names the component family without guessing a vtable.
std::string ReadUiContractName(uint32_t object) {
  if (!PinyonShiftGuestRangeReadable(object, 24u)) {
    return std::string();
  }
  const uint32_t size = LoadGuestU32(object + 16u);
  const uint32_t capacity = LoadGuestU32(object + 20u);
  if (size == 0u || size > 64u) {
    return std::string();
  }
  const uint32_t data = capacity >= 16u ? LoadGuestU32(object) : object;
  std::string text;
  text.reserve(size);
  for (uint32_t index = 0; index < size; ++index) {
    if (!PinyonShiftGuestRangeReadable(data + index, 1u)) {
      break;
    }
    const uint8_t byte = LoadGuestU8(data + index);
    text.push_back(byte >= 0x20u && byte <= 0x7Eu ? static_cast<char>(byte)
                                                  : '.');
  }
  return text;
}

// Structural dump of one authored element record and the object that owns it.
// The deserializer sub_82F26560 creates every item through sub_82F2DF08 (small
// record) or sub_82F2E870 (large record), appends each stream property through
// sub_82F2E000, and only then calls the owner's builder. Those three functions
// give the record layout: +0 stream name hash, +4 stream value, +12 parent,
// +16 next sibling, +20 first child, +28 halfword flag word (bit 0 selects the
// entry base), +30 kind byte, +31 property count, and {id, value} entries at
// +32, or at +68 when bit 0 of the flag halfword is set. Comparing the property
// entries of consecutive items names the field that carries the row's own value
// (the layout offset a duplicated item has to change to occupy a new slot).
void DumpUiElementRecord(uint32_t record, uint32_t owner, uint32_t ordinal) {
  if (!PinyonShiftGuestRangeReadable(record, 48u)) {
    return;
  }
  const uint32_t header = LoadGuestU32(record + 28u);
  const uint32_t flags = header >> 16;
  const uint32_t kind = (header >> 8) & 0xFFu;
  const uint32_t count = header & 0xFFu;
  const uint32_t base = (flags & 1u) != 0u ? 68u : 32u;
  const auto word = [](uint32_t address) {
    return PinyonShiftGuestRangeReadable(address, 4u)
               ? Hex32(LoadGuestU32(address))
               : std::string("00000000");
  };
  pinyon_shift::diagnostics::RecordEvent(
      "ui.record.header",
      {{"ordinal", Hex32(ordinal)},
       {"record", Hex32(record)},
       {"owner", Hex32(owner)},
       {"name_hash", Hex32(LoadGuestU32(record))},
       {"field_4", word(record + 4u)},
       {"parent", word(record + 12u)},
       {"next_sibling", word(record + 16u)},
       {"first_child", word(record + 20u)},
       {"flags", Hex32(flags)},
       {"kind", Hex32(kind)},
       {"property_count", Hex32(count)},
       {"entry_base", Hex32(base)}});
  const uint32_t entries = count > 24u ? 24u : count;
  for (uint32_t index = 0; index < entries; ++index) {
    const uint32_t at = record + base + index * 8u;
    pinyon_shift::diagnostics::RecordEvent(
        "ui.record.entry",
        {{"ordinal", Hex32(ordinal)},
         {"record", Hex32(record)},
         {"index", Hex32(index)},
         {"id", word(at)},
         {"value", word(at + 4u)}});
  }
  uint32_t child = LoadGuestU32(record + 20u);
  for (uint32_t index = 0; index < 8u && child != 0u; ++index) {
    if (!PinyonShiftGuestRangeReadable(child, 32u)) {
      break;
    }
    pinyon_shift::diagnostics::RecordEvent(
        "ui.record.child",
        {{"ordinal", Hex32(ordinal)},
         {"record", Hex32(record)},
         {"index", Hex32(index)},
         {"child", Hex32(child)},
         {"name_hash", Hex32(LoadGuestU32(child))},
         {"parent", word(child + 12u)},
         {"next_sibling", word(child + 16u)},
         {"first_child", word(child + 20u)}});
    child = LoadGuestU32(child + 16u);
  }
  // Walk up the record tree and name each ancestor's child list. The item
  // records are siblings under the element that owns the rows, so this prints
  // the list the visible rows are enumerated from.
  uint32_t ancestor = LoadGuestU32(record + 12u);
  for (uint32_t level = 0; level < 4u && ancestor != 0u; ++level) {
    if (!PinyonShiftGuestRangeReadable(ancestor, 32u)) {
      break;
    }
    const uint32_t ancestor_header = LoadGuestU32(ancestor + 28u);
    pinyon_shift::diagnostics::RecordEvent(
        "ui.record.ancestor",
        {{"ordinal", Hex32(ordinal)},
         {"level", Hex32(level)},
         {"record", Hex32(ancestor)},
         {"name_hash", Hex32(LoadGuestU32(ancestor))},
         {"parent", word(ancestor + 12u)},
         {"first_child", word(ancestor + 20u)},
         {"flags", Hex32(ancestor_header >> 16)},
         {"kind", Hex32((ancestor_header >> 8) & 0xFFu)},
         {"property_count", Hex32(ancestor_header & 0xFFu)}});
    uint32_t sibling = LoadGuestU32(ancestor + 20u);
    for (uint32_t index = 0; index < 12u && sibling != 0u; ++index) {
      if (!PinyonShiftGuestRangeReadable(sibling, 32u)) {
        break;
      }
      pinyon_shift::diagnostics::RecordEvent(
          "ui.record.sibling",
          {{"ordinal", Hex32(ordinal)},
           {"level", Hex32(level)},
           {"index", Hex32(index)},
           {"record", Hex32(sibling)},
           {"name_hash", Hex32(LoadGuestU32(sibling))},
           {"next_sibling", word(sibling + 16u)},
           {"first_child", word(sibling + 20u)}});
      sibling = LoadGuestU32(sibling + 16u);
    }
    ancestor = LoadGuestU32(ancestor + 12u);
  }
}

// One dump of the owning element and of the document it points at. The element's
// +8 map is keyed by record and holds the {descriptor, component} pair the
// builder inserts; +40 and +56 are the vectors that receive the same pair. The
// deserializer sub_82F26560 reaches the record arena through the element's
// virtual `vtable[128]()` and the property document through `vtable[56]()`, so
// both slots are printed instead of called: the element class is not identified
// statically yet and an unverified indirect call faults inside recompiled code.
void DumpUiElementOwner(PPCContext& context, uint8_t* base, uint32_t owner) {
  (void)context;
  (void)base;
  if (!PinyonShiftGuestRangeReadable(owner, 96u)) {
    return;
  }
  const auto word = [](uint32_t address) {
    return PinyonShiftGuestRangeReadable(address, 4u)
               ? Hex32(LoadGuestU32(address))
               : std::string("00000000");
  };
  const uint32_t vtable =
      PinyonShiftGuestRangeReadable(owner, 4u) ? LoadGuestU32(owner) : 0u;
  const uint32_t document =
      PinyonShiftGuestRangeReadable(owner + 4u, 4u) ? LoadGuestU32(owner + 4u)
                                                    : 0u;
  pinyon_shift::diagnostics::RecordEvent(
      "ui.record.owner",
      {{"owner", Hex32(owner)},
       {"vtable", Hex32(vtable)},
       {"vtable_slot_32", word(vtable + 32u)},
       {"vtable_slot_56", word(vtable + 56u)},
       {"vtable_slot_60", word(vtable + 60u)},
       {"vtable_slot_128", word(vtable + 128u)},
       {"document", Hex32(document)},
       {"field_8_begin", word(owner + 8u)},
       {"field_12_end", word(owner + 12u)},
       {"field_16", word(owner + 16u)},
       {"field_20", word(owner + 20u)},
       {"field_24", word(owner + 24u)},
       {"field_32", word(owner + 32u)},
       {"field_36", word(owner + 36u)},
       {"field_40_begin", word(owner + 40u)},
       {"field_44_end", word(owner + 44u)},
       {"field_48", word(owner + 48u)},
       {"field_56_begin", word(owner + 56u)},
       {"field_60_end", word(owner + 60u)},
       {"field_72", word(owner + 72u)},
       {"field_80", word(owner + 80u)},
       {"field_84", word(owner + 84u)},
       {"field_92", word(owner + 92u)},
       {"document_12", word(document + 12u)},
       {"document_16", word(document + 16u)},
       {"document_20", word(document + 20u)},
       {"document_80", word(document + 80u)},
       {"document_84", word(document + 84u)},
       {"document_92", word(document + 92u)},
       {"document_124_records", word(document + 124u)},
       {"document_128_capacity", word(document + 128u)},
       {"document_132_count", word(document + 132u)},
       {"document_136", word(document + 136u)}});
  const uint32_t pool_document = document;
  const uint32_t records =
      PinyonShiftGuestRangeReadable(pool_document + 124u, 4u)
          ? LoadGuestU32(pool_document + 124u)
          : 0u;
  const uint32_t record_count =
      PinyonShiftGuestRangeReadable(pool_document + 132u, 4u)
          ? LoadGuestU32(pool_document + 132u)
          : 0u;
  const uint32_t bounded =
      record_count > 16u ? 16u : record_count;
  for (uint32_t index = 0; index < bounded; ++index) {
    if (!PinyonShiftGuestRangeReadable(records + index * 4u, 4u)) {
      break;
    }
    const uint32_t entry = LoadGuestU32(records + index * 4u);
    pinyon_shift::diagnostics::RecordEvent(
        "ui.record.pool",
        {{"owner", Hex32(owner)},
         {"index", Hex32(index)},
         {"record", Hex32(entry)},
         {"name_hash",
          PinyonShiftGuestRangeReadable(entry, 4u)
              ? Hex32(LoadGuestU32(entry))
              : std::string("00000000")}});
  }
}

// The record tree is the structure the title links while it deserializes a page:
// sub_82F2DF08 / sub_82F2E870 write +12 parent, +16 next sibling and +20 first
// child, and sub_82F2E9A0 exists only to remap those three fields when a record
// moves. The builder writes nothing into it, so a duplicated record has to be
// linked here or no pass that walks the authored elements can see it.
// PINYON_SHIFT_UI_INSERT_LINK_TREE=0 keeps the original container-only variant
// for comparison.
bool UiInsertLinksTree() {
  static const bool links = [] {
#if defined(_WIN32)
    char* value = nullptr;
    size_t value_size = 0;
    if (_dupenv_s(&value, &value_size, "PINYON_SHIFT_UI_INSERT_LINK_TREE") != 0) {
      return true;
    }
    const bool result = value == nullptr || std::string_view(value) != "0";
    std::free(value);
    return result;
#else
    const char* value = std::getenv("PINYON_SHIFT_UI_INSERT_LINK_TREE");
    return value == nullptr || std::string_view(value) != "0";
#endif
  }();
  return links;
}

// Parses PINYON_SHIFT_UI_INSERT_IDENTITY as a hex name hash for the added
// wrapper record. The authored rows carry one distinct hash each in the wrapper
// record at +0, so a replay that duplicates the source hash also duplicates the
// row's identity; this override gives the added wrapper a hash of its own
// without a rebuild. Unset keeps the source record's hash.
struct UiInsertIdentity {
  bool requested = false;
  uint32_t hash = 0u;
};

const UiInsertIdentity& UiInsertIdentityValue() {
  static const UiInsertIdentity identity = [] {
    UiInsertIdentity parsed;
    std::string_view text;
#if defined(_WIN32)
    char* raw = nullptr;
    size_t raw_size = 0;
    if (_dupenv_s(&raw, &raw_size, "PINYON_SHIFT_UI_INSERT_IDENTITY") != 0) {
      return parsed;
    }
    const std::string owned = raw ? std::string(raw) : std::string();
    std::free(raw);
    text = owned;
    if (text.empty()) {
      return parsed;
    }
#else
    const char* raw = std::getenv("PINYON_SHIFT_UI_INSERT_IDENTITY");
    text = raw ? std::string_view(raw) : std::string_view();
#endif
    if (text.size() > 2u && text[0] == '0' &&
        (text[1] == 'x' || text[1] == 'X')) {
      text.remove_prefix(2u);
    }
    uint32_t value = 0u;
    for (const char character : text) {
      uint32_t digit = 0u;
      if (character >= '0' && character <= '9') {
        digit = static_cast<uint32_t>(character - '0');
      } else if (character >= 'a' && character <= 'f') {
        digit = static_cast<uint32_t>(character - 'a') + 10u;
      } else if (character >= 'A' && character <= 'F') {
        digit = static_cast<uint32_t>(character - 'A') + 10u;
      } else {
        return parsed;
      }
      value = value * 16u + digit;
    }
    parsed.hash = value;
    parsed.requested = true;
    return parsed;
  }();
  return identity;
}

// Bit mask over the replay's individual steps, so a run can bisect which step
// makes the title's later passes fail without a rebuild. Unset or zero runs
// the eight construction steps; counter rollback remains diagnostic-only:
//   1 create the wrapper record        2 append the wrapper's properties
//   4 create the element record        8 append the element's properties
//  16 push both records to the pool   32 run the component builder
//  64 copy the source records' headers (flag word, kind and count)
// 128 link the wrapper into the authored sibling chain
uint32_t UiInsertSteps() {
  static const uint32_t steps = [] {
    std::string_view text;
#if defined(_WIN32)
    char* raw = nullptr;
    size_t raw_size = 0;
    if (_dupenv_s(&raw, &raw_size, "PINYON_SHIFT_UI_INSERT_STEPS") != 0) {
      return 0xFFu;
    }
    const std::string owned = raw ? std::string(raw) : std::string();
    std::free(raw);
    text = owned;
#else
    const char* raw = std::getenv("PINYON_SHIFT_UI_INSERT_STEPS");
    text = raw ? std::string_view(raw) : std::string_view();
#endif
    if (text.empty()) {
      return 0xFFu;
    }
    if (text.size() > 2u && text[0] == '0' &&
        (text[1] == 'x' || text[1] == 'X')) {
      text.remove_prefix(2u);
    }
    uint32_t value = 0u;
    for (const char character : text) {
      uint32_t digit = 0u;
      if (character >= '0' && character <= '9') {
        digit = static_cast<uint32_t>(character - '0');
      } else if (character >= 'a' && character <= 'f') {
        digit = static_cast<uint32_t>(character - 'a') + 10u;
      } else if (character >= 'A' && character <= 'F') {
        digit = static_cast<uint32_t>(character - 'A') + 10u;
      } else {
        break;
      }
      value = value * 16u + digit;
    }
    return value == 0u ? 0xFFu : value;
  }();
  return steps;
}

constexpr uint32_t kUiInsertStepWrapper = 1u;
constexpr uint32_t kUiInsertStepWrapperProperties = 2u;
constexpr uint32_t kUiInsertStepElement = 4u;
constexpr uint32_t kUiInsertStepElementProperties = 8u;
constexpr uint32_t kUiInsertStepPoolPush = 16u;
constexpr uint32_t kUiInsertStepBuilder = 32u;
constexpr uint32_t kUiInsertStepHeader = 64u;
constexpr uint32_t kUiInsertStepLink = 128u;
// Diagnostic-only restores of the bookkeeping the allocators advance.
constexpr uint32_t kUiInsertStepRestoreCounters = 256u;
constexpr uint32_t kUiInsertStepRestoreCursor = 512u;
constexpr uint32_t kUiInsertStepRestorePool = 1024u;

// Parses PINYON_SHIFT_UI_INSERT_PROPERTY as `<id>:<value>` (both hex, with or
// without a 0x prefix) and rewrites the copied record's matching property entry.
// The deserializer stores each stream property as {id, value} through
// sub_82F2E000, and the create-by-name factory reads them, so patching the copy
// before the builder gives the duplicated row its own layout values without
// touching the stock item's record.
struct UiInsertProperty {
  bool requested = false;
  uint32_t id = 0u;
  uint32_t value = 0u;
};

const UiInsertProperty& UiInsertPropertyValue() {
  static const UiInsertProperty property = [] {
    UiInsertProperty parsed;
#if defined(_WIN32)
    char* raw = nullptr;
    size_t raw_size = 0;
    if (_dupenv_s(&raw, &raw_size, "PINYON_SHIFT_UI_INSERT_PROPERTY") != 0) {
      return parsed;
    }
    const std::string owned = raw ? std::string(raw) : std::string();
    std::free(raw);
    const std::string_view text = owned;
#else
    const char* raw = std::getenv("PINYON_SHIFT_UI_INSERT_PROPERTY");
    const std::string_view text = raw ? std::string_view(raw) : std::string_view();
#endif
    const size_t split = text.find(':');
    if (split == std::string_view::npos) {
      return parsed;
    }
    const auto parse = [](std::string_view digits) -> uint32_t {
      uint32_t value = 0u;
      if (digits.size() > 2u && digits[0] == '0' &&
          (digits[1] == 'x' || digits[1] == 'X')) {
        digits.remove_prefix(2u);
      }
      for (const char character : digits) {
        uint32_t digit = 0u;
        if (character >= '0' && character <= '9') {
          digit = static_cast<uint32_t>(character - '0');
        } else if (character >= 'a' && character <= 'f') {
          digit = static_cast<uint32_t>(character - 'a') + 10u;
        } else if (character >= 'A' && character <= 'F') {
          digit = static_cast<uint32_t>(character - 'A') + 10u;
        } else {
          break;
        }
        value = value * 16u + digit;
      }
      return value;
    };
    parsed.id = parse(text.substr(0u, split));
    parsed.value = parse(text.substr(split + 1u));
    parsed.requested = true;
    return parsed;
  }();
  return property;
}

// Returns 1 when the property was found and rewritten, 0 when no entry matched,
// and 2 when the record header is unreadable.
uint32_t UiInsertPatchProperty(uint32_t record) {
  const UiInsertProperty& property = UiInsertPropertyValue();
  if (!property.requested || !PinyonShiftGuestRangeReadable(record, 32u)) {
    return 0u;
  }
  const uint32_t header = LoadGuestU32(record + 28u);
  const uint32_t base = (header & 0x00010000u) != 0u ? 68u : 32u;
  const uint32_t count = header & 0xFFu;
  for (uint32_t index = 0; index < count; ++index) {
    const uint32_t at = record + base + index * 8u;
    if (!PinyonShiftGuestRangeReadable(at, 8u)) {
      return 2u;
    }
    if (LoadGuestU32(at) != property.id) {
      continue;
    }
    StoreGuestU32(at + 4u, property.value);
    return 1u;
  }
  return 0u;
}

// Counts one record's child list (+20 first child, +16 next sibling). A
// duplicated record that the page enumerates has to appear in this chain.
uint32_t UiCountRecordSiblings(uint32_t parent) {
  if (parent == 0u || !PinyonShiftGuestRangeReadable(parent + 20u, 4u)) {
    return 0u;
  }
  uint32_t child = LoadGuestU32(parent + 20u);
  uint32_t count = 0u;
  while (child != 0u && count < 64u) {
    if (!PinyonShiftGuestRangeReadable(child + 20u, 4u)) {
      break;
    }
    ++count;
    child = LoadGuestU32(child + 16u);
  }
  return count;
}

// 1 when the record is reachable from the parent's child chain, 0 otherwise.
uint32_t UiFindRecordInChain(uint32_t parent, uint32_t record) {
  if (parent == 0u || !PinyonShiftGuestRangeReadable(parent + 20u, 4u)) {
    return 0u;
  }
  uint32_t child = LoadGuestU32(parent + 20u);
  for (uint32_t index = 0; index < 64u && child != 0u; ++index) {
    if (child == record) {
      return 1u;
    }
    if (!PinyonShiftGuestRangeReadable(child + 20u, 4u)) {
      break;
    }
    child = LoadGuestU32(child + 16u);
  }
  return 0u;
}

// The three calls the scene deserializer sub_82F26560 makes for one authored
// item, in the order it makes them. sub_82F2E870 allocates the wrapper record
// (kind 7) that carries the item's own identity, sub_82F2DF08 allocates the
// element record whose +0 is the contract name hash, and sub_82F2E000 appends
// one stream property to the record the document last created. Replaying them is
// what makes an added item a real member of the authored page: the document's
// pool, tree links and counters advance exactly as they do for an authored item,
// so every later pass sees the same structures the stock items produce.
constexpr uint32_t kUiWrapperRecordAllocator = 0x82F2E870u;
constexpr uint32_t kUiElementRecordAllocator = 0x82F2DF08u;
constexpr uint32_t kUiPropertyAppend = 0x82F2E000u;
// The section record pool append the deserializer calls after creating a record.
constexpr uint32_t kUiSectionRecordPush = 0x82F2EA38u;

// 1 = replay the title's own item construction (default), 0 = only copy the
// stock record and re-run the builder.
bool UiInsertReplaysItem() {
  static const bool replays = [] {
#if defined(_WIN32)
    char* value = nullptr;
    size_t value_size = 0;
    if (_dupenv_s(&value, &value_size, "PINYON_SHIFT_UI_INSERT_MODE") != 0) {
      return true;
    }
    const bool result = value == nullptr || std::string_view(value) != "copy";
    std::free(value);
    return result;
#else
    const char* value = std::getenv("PINYON_SHIFT_UI_INSERT_MODE");
    return value == nullptr || std::string_view(value) != "copy";
#endif
  }();
  return replays;
}

// The record's flag halfword (+28) selects the entry base and carries the flag
// the deserializer passes to the allocator as its fifth argument.
uint32_t UiRecordFlag(uint32_t record) {
  return (LoadGuestU32(record + 28u) >> 16) & 1u;
}

uint32_t UiRecordKind(uint32_t record) { return LoadGuestU32(record + 30u) >> 24; }

// Appends every property the source record holds to the document's current
// record, in the stored order, through the title's own appender. The stored
// value of a resolved property is already the object the deserializer produced,
// so replaying the pair reproduces the record byte for byte.
void ReplayUiRecordProperties(PPCContext& context, uint8_t* base,
                              uint32_t document, uint32_t source) {
  const uint32_t header = LoadGuestU32(source + 28u);
  const uint32_t base_offset = (header & 0x00010000u) != 0u ? 68u : 32u;
  const uint32_t count = header & 0xFFu;
  for (uint32_t index = 0; index < count; ++index) {
    const uint32_t at = source + base_offset + index * 8u;
    if (!PinyonShiftGuestRangeReadable(at, 8u)) {
      return;
    }
    CallGuestFunction(context, base, kUiPropertyAppend, document,
                      LoadGuestU32(at), LoadGuestU32(at + 4u));
  }
}

// Appends one record to the deserializer's record pool with the title's own push
// (sub_82F2EA38, the std::vector<float>-style append the deserializer uses right
// after it creates a record). The pool is the array the stream's parent index
// resolves through, so an added item has to appear in it exactly like an authored
// one. The value is handed over through a scratch guest word because the push
// reads its argument indirectly.
void PushUiSectionRecord(PPCContext& context, uint8_t* base, uint32_t section,
                         uint32_t record) {
  auto* memory = rex::system::kernel_state()->memory();
  if (memory == nullptr || section == 0u || record == 0u) {
    return;
  }
  const uint32_t scratch = memory->SystemHeapAlloc(16u, 16u);
  if (scratch == 0u) {
    return;
  }
  StoreGuestU32(scratch, record);
  CallGuestFunction(context, base, kUiSectionRecordPush, section + 92u, scratch);
}

// Bounded hex read of a guest byte range, for the record-field dumps below.
std::string HexBytes(uint32_t address, uint32_t count) {
  if (count > 48u || address == 0u ||
      !PinyonShiftGuestRangeReadable(address, count)) {
    return std::string();
  }
  static constexpr char kDigits[] = "0123456789ABCDEF";
  std::string text;
  text.reserve(count * 2u);
  for (uint32_t index = 0; index < count; ++index) {
    const uint8_t byte = LoadGuestU8(address + index);
    text.push_back(kDigits[byte >> 4]);
    text.push_back(kDigits[byte & 0x0Fu]);
  }
  return text;
}

// Copies the fixed field region of an authored record onto a record the title's
// own allocator just created: the flag halfword at +28/+29 and everything between
// +32 and the first property entry, which is +68 for a wrapper record and +32 for
// an element record. The allocator only writes the fields it owns (link pointers,
// name hash, stream value and the reserve's own flag state); an authored record
// also carries authored or per-row values in that range (a wrapper record holds a
// float block at +48), and a later pass over the document reads them, so a record
// that leaves them at whatever the arena held is what makes the pass fail.
//
// The kind byte at +30 and the property count at +31 are deliberately not copied:
// the allocator sets the kind and each property append advances the count from
// zero, so copying an authored count would make the replay's own appends start
// past the entries it owns and leave the first slots uninitialised.
void CopyUiInsertFixedFields(uint32_t target, uint32_t source) {
  if (target == 0u || source == 0u ||
      !PinyonShiftGuestRangeReadable(source + 28u, 4u)) {
    return;
  }
  const uint32_t header = LoadGuestU32(source + 28u);
  const uint32_t base = (header & 0x00010000u) != 0u ? 68u : 32u;
  if (!PinyonShiftGuestRangeReadable(target + 28u, 2u) ||
      !PinyonShiftGuestRangeReadable(source + 28u, 2u)) {
    return;
  }
  StoreGuestU8(target + 28u, LoadGuestU8(source + 28u));
  StoreGuestU8(target + 29u, LoadGuestU8(source + 29u));
  for (uint32_t offset = 32u; offset < base; ++offset) {
    StoreGuestU8(target + offset, LoadGuestU8(source + offset));
  }
}

// One bounded read of the shapes a replayed row depends on: the wrapper record's
// single property (the row's own authored value) and the element record's four
// type-0x14 object references (the per-row geometry/identity objects the
// deserializer parsed). A replay that reuses the source record's stored values
// reuses these objects, so naming them is what tells a distinct added row apart
// from a duplicate of the row it was copied from. The document fields named here
// are the counters and cursors a later pass over the same document advances, so
// a run shows whether the replay's records are visible to those passes.
void LogUiInsertRecordShape(uint32_t wrapper, uint32_t record, uint32_t section,
                            uint32_t document, uint32_t wrapper_target,
                            uint32_t record_target) {
  const auto word = [](uint32_t address) {
    return PinyonShiftGuestRangeReadable(address, 4u)
               ? Hex32(LoadGuestU32(address))
               : std::string("00000000");
  };
  const auto entry = [&](uint32_t target, uint32_t index) {
    if (!PinyonShiftGuestRangeReadable(target + 28u, 4u)) {
      return std::pair<uint32_t, uint32_t>{0u, 0u};
    }
    const uint32_t header = LoadGuestU32(target + 28u);
    const uint32_t base = (header & 0x00010000u) != 0u ? 68u : 32u;
    if (index * 8u >= (header & 0xFFu) * 8u) {
      return std::pair<uint32_t, uint32_t>{0u, 0u};
    }
    const uint32_t at = target + base + index * 8u;
    if (!PinyonShiftGuestRangeReadable(at, 8u)) {
      return std::pair<uint32_t, uint32_t>{0u, 0u};
    }
    return std::pair<uint32_t, uint32_t>{LoadGuestU32(at), LoadGuestU32(at + 4u)};
  };
  const auto wrapper_property = entry(wrapper, 0u);
  const uint32_t document_vtable =
      PinyonShiftGuestRangeReadable(document, 4u) ? LoadGuestU32(document) : 0u;
  pinyon_shift::diagnostics::RecordEvent(
      "ui.item.insert.shape",
      {{"wrapper", Hex32(wrapper)},
       {"wrapper_hash", word(wrapper)},
       {"wrapper_flag", word(wrapper + 28u)},
       {"wrapper_field_4", word(wrapper + 4u)},
       {"wrapper_field_8", word(wrapper + 8u)},
       {"wrapper_field_24", word(wrapper + 24u)},
       {"wrapper_field_36", word(wrapper + 36u)},
       {"wrapper_field_44", word(wrapper + 44u)},
       {"wrapper_field_48", word(wrapper + 48u)},
       {"wrapper_property_id", Hex32(wrapper_property.first)},
       {"wrapper_property_value", Hex32(wrapper_property.second)},
       {"record", Hex32(record)},
       {"record_field_8", word(record + 8u)},
       {"record_field_24", word(record + 24u)},
       {"record_field_36", word(record + 36u)},
       {"record_field_44", word(record + 44u)},
       {"record_field_48", word(record + 48u)},
       {"record_flag", word(record + 28u)},
       {"wrapper_fixed_hex", HexBytes(wrapper + 28u, 40u)},
       {"wrapper_target_fixed_hex", HexBytes(wrapper_target + 28u, 40u)},
       {"record_fixed_hex", HexBytes(record + 28u, 40u)},
       {"record_target_fixed_hex", HexBytes(record_target + 28u, 40u)},
       {"document_vtable", Hex32(document_vtable)},
       {"document_reserve_fn",
        document_vtable != 0u ? word(document_vtable + 88u)
                              : std::string("00000000")},
       {"document_field_12", word(document + 12u)},
       {"document_field_16", word(document + 16u)},
       {"document_last_record", word(document + 80u)},
       {"document_cursor", word(document + 84u)},
       {"section_field_16", word(section + 16u)},
       {"section_field_20", word(section + 20u)},
       {"section_field_28", word(section + 28u)},
       {"section_capacity",
        PinyonShiftGuestRangeReadable(section + 128u, 4u)
            ? Hex32(LoadGuestU32(section + 128u))
            : std::string("00000000")},
       {"section_data",
        PinyonShiftGuestRangeReadable(section + 124u, 4u)
            ? Hex32(LoadGuestU32(section + 124u))
            : std::string("00000000")}});
  for (const uint32_t index : {2u, 4u, 5u, 8u}) {
    const auto row_entry = entry(record, index);
    pinyon_shift::diagnostics::RecordEvent(
        "ui.item.insert.object",
        {{"record", Hex32(record)},
         {"index", Hex32(index)},
         {"id", Hex32(row_entry.first)},
         {"value", Hex32(row_entry.second)},
         {"object_0", word(row_entry.second)},
         {"object_4", word(row_entry.second + 4u)},
         {"object_8", word(row_entry.second + 8u)},
         {"object_12", word(row_entry.second + 12u)},
         {"object_16", word(row_entry.second + 16u)}});
  }
}

// Guards the nested builder run so the hook it re-enters is not itself a
// second insertion target.
struct UiInsertGuard {
  ~UiInsertGuard() {
    g_ui_insert_active.store(false, std::memory_order_release);
  }
};

}  // namespace

// Called after every create-by-name call in the per-child builder: r3 is the
// created component, r28 the authored element record, r30 the 28-byte
// descriptor, and r31 the owning scene element. The configured `context` hook
// option supplies the live guest context and memory base, which is what lets
// the experiment run the title's builder a second time.
void PinyonShiftUiPauseItemInsert(PPCContext& context, uint8_t* base,
                                  PPCRegister& r3, PPCRegister& r28,
                                  PPCRegister& r30, PPCRegister& r31) {
  const uint32_t component = r3.u32;
  const uint32_t record = r28.u32;
  const uint32_t descriptor = r30.u32;
  const uint32_t owner = r31.u32;
  const uint32_t component_vtable =
      PinyonShiftGuestRangeReadable(component, 4u) ? LoadGuestU32(component)
                                                  : 0u;
  const uint32_t name_object = context.r1.u32 + 96u;
  const auto read_word = [](uint32_t address) {
    return PinyonShiftGuestRangeReadable(address, 4u)
               ? Hex32(LoadGuestU32(address))
               : std::string("00000000");
  };
  const bool is_menu_item = component_vtable == kUiPauseMenuButtonVtable;
  const uint32_t trace_budget =
      is_menu_item
          ? g_ui_insert_button_trace_count.fetch_add(1, std::memory_order_relaxed)
          : g_ui_insert_generic_trace_count.fetch_add(1, std::memory_order_relaxed);
  if (UiTraceEnabled() &&
      trace_budget < (is_menu_item ? kUiInsertButtonTraceLimit
                                   : kUiInsertGenericTraceLimit)) {
    pinyon_shift::diagnostics::RecordEvent(
        "ui.item.create",
        {{"address", "82E7A394"},
         {"frame",
          std::to_string(pinyon_shift::fh1_render_test::CurrentFrame())},
         {"contract", ReadUiContractName(name_object)},
         {"owner", Hex32(owner)},
         {"record", Hex32(record)},
         {"record_name_hash",
          PinyonShiftGuestRangeReadable(record, 4u)
              ? Hex32(LoadGuestU32(record))
              : std::string("00000000")},
         {"descriptor", Hex32(descriptor)},
         {"descriptor_owner", read_word(descriptor + 8u)},
         {"component", Hex32(component)},
         {"component_vtable", Hex32(component_vtable)},
         {"menu_item", is_menu_item ? "1" : "0"},
         {"registry_global", read_word(0x834B53D4u)},
         {"frame_saved_owner", read_word(context.r1.u32 + 160u)},
         {"frame_saved_lr", read_word(context.r1.u32 + 168u)}});
  }
  if (is_menu_item) {
    const uint32_t dump_ordinal =
        g_ui_record_dump_count.fetch_add(1, std::memory_order_relaxed) + 1u;
    if (dump_ordinal <= 8u) {
      DumpUiElementRecord(record, owner, dump_ordinal);
    }
    if (g_ui_owner_dump_count.fetch_add(1, std::memory_order_relaxed) < 4u) {
      DumpUiElementOwner(context, base, owner);
    }
  }
  if (UiExperimentModeValue() != UiExperimentMode::kInsertItem) {
    return;
  }
  if (g_ui_insert_active.exchange(true, std::memory_order_acq_rel)) {
    // The nested builder run reaches this hook again; only the outer call is a
    // target.
    return;
  }
  UiInsertGuard insert_guard;
  if (!is_menu_item) {
    return;
  }
  const uint32_t ordinal =
      g_ui_insert_button_count.fetch_add(1, std::memory_order_relaxed) + 1u;
  if (ordinal != UiInsertOrdinal()) {
    return;
  }
  if (g_ui_insert_done.exchange(true, std::memory_order_acq_rel)) {
    return;
  }
  // Replay the title's own construction when the deserializer's published
  // document, element and section belong to this item. The deserializer reaches
  // the builder through the element's own vtable slot 15, whose thunk loads the
  // CUI4CustomObject at element+32 and tail-calls slot 1 of its vtable, so the
  // builder's owner is element+32 -- not the element. Both record allocators also
  // leave the record they just created at document+80, and the element's slot 32
  // thunk returns element+500, which is that document. Checking those three
  // relations is what makes the captured pointers the item's own; the earlier
  // attempt compared the published element with the builder's owner, a relation
  // that never holds, so the replay was always skipped and the probe fell back to
  // the container-only copy.
  const uint32_t document = g_ui_insert_document.load(std::memory_order_relaxed);
  const uint32_t element = g_ui_insert_element.load(std::memory_order_relaxed);
  const uint32_t section = g_ui_insert_section.load(std::memory_order_relaxed);
  const uint32_t published_record =
      g_ui_insert_record.load(std::memory_order_relaxed);
  const uint32_t owner_element =
      PinyonShiftGuestRangeReadable(owner + 4u, 4u) ? LoadGuestU32(owner + 4u)
                                                    : 0u;
  const uint32_t element_owner =
      PinyonShiftGuestRangeReadable(element + 32u, 4u)
          ? LoadGuestU32(element + 32u)
          : 0u;
  const uint32_t document_last_record =
      PinyonShiftGuestRangeReadable(document + 80u, 4u)
          ? LoadGuestU32(document + 80u)
          : 0u;
  const bool document_current =
      document != 0u && document_last_record == record;
  const bool element_current = element_owner == owner || element == owner_element;
  const uint32_t source_parent =
      PinyonShiftGuestRangeReadable(record + 12u, 4u) ? LoadGuestU32(record + 12u)
                                                      : 0u;
  const uint32_t source_container =
      PinyonShiftGuestRangeReadable(source_parent + 12u, 4u)
          ? LoadGuestU32(source_parent + 12u)
          : 0u;
  const uint32_t pool_size_before =
      PinyonShiftGuestRangeReadable(section + 132u, 4u)
          ? LoadGuestU32(section + 132u)
          : 0u;
  uint32_t wrapper_record = 0u;
  uint32_t target_record = 0u;
  const uint32_t steps = UiInsertSteps();
  // The allocators advance the document's record counters, its last-record slot,
  // its arena cursor and the section pool's size, exactly as they do for an
  // authored item. A later pass over the same document reads those, so the
  // experiment records them before the replay and can put any of them back with
  // the restore steps below.
  const uint32_t counter_before_12 =
      PinyonShiftGuestRangeReadable(document + 12u, 4u) ? LoadGuestU32(document + 12u)
                                                        : 0u;
  const uint32_t counter_before_16 =
      PinyonShiftGuestRangeReadable(document + 16u, 4u) ? LoadGuestU32(document + 16u)
                                                        : 0u;
  const uint32_t cursor_before =
      PinyonShiftGuestRangeReadable(document + 84u, 4u) ? LoadGuestU32(document + 84u)
                                                        : 0u;
  const uint32_t last_record_before =
      PinyonShiftGuestRangeReadable(document + 80u, 4u) ? LoadGuestU32(document + 80u)
                                                        : 0u;
  const bool replays = UiInsertReplaysItem() && document_current &&
                       published_record == record && element != 0u &&
                       element_current && source_parent != 0u &&
                       source_container != 0u && section != 0u &&
                       PinyonShiftGuestRangeReadable(source_parent + 36u, 4u) &&
                       (steps & kUiInsertStepWrapper) != 0u;
  if (replays) {
    wrapper_record = CallGuestFunction(
        context, base, kUiWrapperRecordAllocator, document, source_container,
        LoadGuestU32(source_parent), LoadGuestU32(source_parent + 4u),
        UiRecordFlag(source_parent), LoadGuestU32(source_parent + 36u));
    if (wrapper_record != 0u) {
      const UiInsertIdentity& identity = UiInsertIdentityValue();
      if (identity.requested) {
        StoreGuestU32(wrapper_record, identity.hash);
      }
      if ((steps & kUiInsertStepHeader) != 0u) {
        // The allocators leave the flag/tag bytes at +28/+29 and the authored
        // values above them in the state their own reserve produced, which is not
        // always the state an authored record of the same shape carries (an
        // authored element record reads 0x200A where a freshly created one reads
        // 0x0002, and an authored wrapper carries 0x22302E30 at +48). Copy the
        // fixed field region so every later reader sees the authored encoding;
        // the link pointers and the property entries stay the replay's own.
        CopyUiInsertFixedFields(wrapper_record, source_parent);
      }
      if (!UiInsertLinksTree() ||
          (steps & kUiInsertStepLink) == 0u) {
        // Unlink the wrapper from the parent's child chain: the allocator already
        // appended it, so the last sibling now points at it.
        if (PinyonShiftGuestRangeReadable(source_parent + 16u, 4u) &&
            LoadGuestU32(source_parent + 16u) == wrapper_record) {
          StoreGuestU32(source_parent + 16u, 0u);
          StoreGuestU32(wrapper_record + 12u, 0u);
        }
      }
      if ((steps & kUiInsertStepWrapperProperties) != 0u) {
        ReplayUiRecordProperties(context, base, document, source_parent);
      }
      UiInsertPatchProperty(wrapper_record);
      if ((steps & kUiInsertStepElement) != 0u) {
        target_record = CallGuestFunction(
            context, base, kUiElementRecordAllocator, document, wrapper_record,
            LoadGuestU32(record), LoadGuestU32(record + 4u),
            UiRecordFlag(record), UiRecordKind(record));
      }
      if (target_record != 0u) {
        if ((steps & kUiInsertStepHeader) != 0u) {
          CopyUiInsertFixedFields(target_record, record);
        }
        if ((steps & kUiInsertStepElementProperties) != 0u) {
          ReplayUiRecordProperties(context, base, document, record);
        }
        // The deserializer appends every record it creates to the section's pool
        // right after creating it, and the stream's parent index resolves through
        // that array. Append both records with the title's own push so the pool
        // keeps one entry per authored record, in creation order.
        if ((steps & kUiInsertStepPoolPush) != 0u) {
          PushUiSectionRecord(context, base, section, wrapper_record);
          PushUiSectionRecord(context, base, section, target_record);
        }
      }
      // Diagnostic restores, so a run can name which bookkeeping change a later
      // pass is reading. They are off by default.
      if ((steps & kUiInsertStepRestoreCounters) != 0u) {
        StoreGuestU32(document + 12u, counter_before_12);
        StoreGuestU32(document + 16u, counter_before_16);
      }
      if ((steps & kUiInsertStepRestoreCursor) != 0u) {
        StoreGuestU32(document + 80u, last_record_before);
        StoreGuestU32(document + 84u, cursor_before);
      }
      if ((steps & kUiInsertStepRestorePool) != 0u) {
        StoreGuestU32(section + 132u, pool_size_before);
      }
    }
  }
  const uint32_t record_size = UiElementRecordCopySize(record);
  uint32_t record_target = target_record;
  uint32_t tree_parent = 0u;
  uint32_t tree_next_before = 0u;
  bool link_tree = false;
  bool share_record = false;
  // The container-only copy is the comparison path for a replay that was never
  // attempted (its precondition did not hold). A replay that ran and stopped
  // before producing a record leaves the target at zero so the bisect mask keeps
  // the run comparable instead of silently switching paths.
  if (record_target == 0u && !replays) {
    if (record_size == 0u) {
      pinyon_shift::diagnostics::RecordEvent(
          "ui.item.insert",
          {{"result", "unreadable_record"},
           {"frame",
            std::to_string(pinyon_shift::fh1_render_test::CurrentFrame())},
           {"owner", Hex32(owner)},
           {"record", Hex32(record)}});
      return;
    }
    share_record = UiInsertSharesRecord();
    record_target =
        share_record ? record : CopyUiElementRecord(record, record_size);
    if (record_target == 0u) {
      pinyon_shift::diagnostics::RecordEvent(
          "ui.item.insert",
          {{"result", "allocation_failed"},
           {"frame",
            std::to_string(pinyon_shift::fh1_render_test::CurrentFrame())},
           {"owner", Hex32(owner)},
           {"record", Hex32(record)},
           {"record_size", Hex32(record_size)}});
      return;
    }
    // The copied record is not in the authored tree, so link it as the next
    // sibling of the record it was copied from. This variant is the comparison
    // path: the title's own allocator does the linking in replay mode.
    link_tree = UiInsertLinksTree() &&
                PinyonShiftGuestRangeReadable(record_target + 20u, 4u);
    if (link_tree) {
      tree_parent = LoadGuestU32(record + 12u);
      tree_next_before = LoadGuestU32(record + 16u);
      StoreGuestU32(record_target + 12u, tree_parent);
      StoreGuestU32(record_target + 16u, tree_next_before);
      StoreGuestU32(record_target + 20u, 0u);
      StoreGuestU32(record + 16u, record_target);
    }
  }
  const uint32_t child_begin_before =
      PinyonShiftGuestRangeReadable(owner + 40u, 4u) ? LoadGuestU32(owner + 40u)
                                                     : 0u;
  const uint32_t child_end_before =
      PinyonShiftGuestRangeReadable(owner + 44u, 4u) ? LoadGuestU32(owner + 44u)
                                                     : 0u;
  const uint32_t child_count_before =
      child_end_before >= child_begin_before
          ? (child_end_before - child_begin_before) / 8u
          : 0u;
  const uint32_t property_result = UiInsertPatchProperty(record_target);
  uint32_t builder_result = 0u;
  if (record_target != 0u && (steps & kUiInsertStepBuilder) != 0u) {
    builder_result =
        CallGuestFunction(context, base, kUiComponentBuilderAddress, owner,
                          record_target);
  }
  const uint32_t child_begin_after =
      PinyonShiftGuestRangeReadable(owner + 40u, 4u) ? LoadGuestU32(owner + 40u)
                                                     : 0u;
  const uint32_t child_end_after =
      PinyonShiftGuestRangeReadable(owner + 44u, 4u) ? LoadGuestU32(owner + 44u)
                                                     : 0u;
  const uint32_t child_count_after =
      child_end_after >= child_begin_after
          ? (child_end_after - child_begin_after) / 8u
          : 0u;
  // The builder's return value is not the created component, so take the new
  // pair the container gained: {descriptor, component}. The push may relocate
  // the buffer, so compare entry counts, not buffer addresses.
  uint32_t added = 0u;
  if (child_count_after > child_count_before) {
    added = LoadGuestU32(child_end_after - 4u);
  }
  const uint32_t added_vtable =
      PinyonShiftGuestRangeReadable(added, 4u) ? LoadGuestU32(added) : 0u;
  const uint32_t pool_size_after =
      PinyonShiftGuestRangeReadable(section + 132u, 4u)
          ? LoadGuestU32(section + 132u)
          : 0u;
  if (UiTraceEnabled() && record_target != 0u) {
    DumpUiElementRecord(record_target, owner, 0xFFFFFFFFu);
  }
  if (UiTraceEnabled() && replays) {
    LogUiInsertRecordShape(source_parent, record, section, document,
                           wrapper_record, target_record);
  }
  pinyon_shift::diagnostics::RecordEvent(
      "ui.item.insert",
      {{"result", added != 0u ? "created" : "no_container_growth"},
       {"frame", std::to_string(pinyon_shift::fh1_render_test::CurrentFrame())},
       {"ordinal", Hex32(ordinal)},
       {"mode", replays ? "replay" : (share_record ? "shared_copy" : "copy")},
       {"steps", Hex32(steps)},
       {"owner", Hex32(owner)},
       {"record", Hex32(record)},
       {"record_copy", Hex32(record_target)},
       {"record_size", Hex32(record_size)},
       {"record_header", read_word(record + 28u)},
       {"shared_record", share_record ? "1" : "0"},
       {"document", Hex32(document)},
       {"element", Hex32(element)},
       {"element_matches_owner", element == owner ? "1" : "0"},
       {"owner_element", Hex32(owner_element)},
       {"element_owner", Hex32(element_owner)},
       {"element_current", element_current ? "1" : "0"},
       {"element_plus_500", Hex32(element + 500u)},
       {"document_current", document_current ? "1" : "0"},
       {"document_last_record", Hex32(document_last_record)},
       {"published_record", Hex32(published_record)},
       {"replay_blocked",
        replays ? std::string()
                : (document_current ? std::string("precondition")
                                    : std::string("stale_publish"))},
       {"section", Hex32(section)},
       {"section_capacity",
        PinyonShiftGuestRangeReadable(section + 128u, 4u)
            ? Hex32(LoadGuestU32(section + 128u))
            : std::string("00000000")},
       {"source_parent", Hex32(source_parent)},
       {"source_container", Hex32(source_container)},
       {"wrapper_record", Hex32(wrapper_record)},
       {"target_record", Hex32(record_target)},
       {"target_header", read_word(record_target + 28u)},
       {"target_parent", read_word(record_target + 12u)},
       {"target_name_hash", read_word(record_target)},
       {"pool_size_before", Hex32(pool_size_before)},
       {"pool_size_after", Hex32(pool_size_after)},
       {"pool_growth", Hex32(pool_size_after >= pool_size_before
                                 ? pool_size_after - pool_size_before
                                 : 0u)},
       {"descriptor", Hex32(descriptor)},
       {"stock_component", Hex32(component)},
       {"stock_vtable", Hex32(component_vtable)},
       {"stock_field_84", read_word(component + 84u)},
       {"stock_field_160", PinyonShiftGuestRangeReadable(component + 160u, 1u)
                               ? Hex32(LoadGuestU8(component + 160u))
                               : std::string("00")},
       {"added_component", Hex32(added)},
       {"added_vtable", Hex32(added_vtable)},
       {"added_field_84", read_word(added + 84u)},
       {"added_field_160", PinyonShiftGuestRangeReadable(added + 160u, 1u)
                               ? Hex32(LoadGuestU8(added + 160u))
                               : std::string("00")},
       {"builder_result", Hex32(builder_result)},
       {"child_begin", Hex32(child_begin_before)},
       {"child_end_before", Hex32(child_end_before)},
       {"child_end_after", Hex32(child_end_after)},
       {"linked_tree", link_tree ? "1" : "0"},
       {"tree_parent", Hex32(tree_parent)},
       {"tree_next_before", Hex32(tree_next_before)},
       {"property_result", Hex32(property_result)},
       {"sibling_count", Hex32(UiCountRecordSiblings(tree_parent))},
       {"inserted_in_chain",
        Hex32(UiFindRecordInChain(tree_parent, record_target))}});
}

void PinyonShiftValidateUiSceneVectorEntry(PPCRegister& r1, PPCRegister& r3,
                                           PPCRegister& r27, PPCRegister& r30,
                                           PPCRegister& r31) {
  if (UiExperimentModeValue() != UiExperimentMode::kSceneInsert ||
      (r3.u32 & 0xFFu) == 0u) {
    return;
  }
  const uint32_t object =
      PinyonShiftGuestRangeReadable(r1.u32 + 88u, 4u)
          ? LoadGuestU32(r1.u32 + 88u)
          : 0u;
  const uint32_t vtable =
      PinyonShiftGuestRangeReadable(object, 4u) ? LoadGuestU32(object) : 0u;
  const uint32_t method =
      PinyonShiftGuestRangeReadable(vtable + 12u, 4u)
          ? LoadGuestU32(vtable + 12u)
          : 0u;
  if (object != 0u && vtable != 0u &&
      method >= 0x82000000u && method < 0x84000000u) {
    return;
  }
  pinyon_shift::diagnostics::RecordEvent(
      "ui.experiment.scene_insert.invalid_vector_entry",
      {{"index", Hex32(r31.u32)},
       {"count", Hex32(r27.u32)},
       {"collection", Hex32(r30.u32)},
       {"object", Hex32(object)},
       {"vtable", Hex32(vtable)},
       {"method", Hex32(method)}});
  r3.u64 = 0u;
}

void PinyonShiftTraceUiSceneVectorCleanup(PPCRegister& r1, PPCRegister& r3,
                                          PPCRegister& r27, PPCRegister& r30,
                                          PPCRegister& r31) {
  if (UiExperimentModeValue() != UiExperimentMode::kSceneInsert ||
      g_ui_scene_cleanup_trace_count.fetch_add(1, std::memory_order_relaxed) >=
          128u) {
    return;
  }
  const uint32_t object =
      PinyonShiftGuestRangeReadable(r1.u32 + 92u, 4u)
          ? LoadGuestU32(r1.u32 + 92u)
          : 0u;
  const uint32_t vtable =
      PinyonShiftGuestRangeReadable(object, 4u) ? LoadGuestU32(object) : 0u;
  const uint32_t method =
      PinyonShiftGuestRangeReadable(vtable + 4u, 4u)
          ? LoadGuestU32(vtable + 4u)
          : 0u;
  pinyon_shift::diagnostics::RecordEvent(
      "ui.experiment.scene_insert.vector_cleanup",
      {{"index", Hex32(r31.u32)},
       {"count", Hex32(r27.u32)},
       {"collection", Hex32(r30.u32)},
       {"stack", Hex32(r1.u32)},
       {"lookup_result", Hex32(r3.u32)},
       {"object", Hex32(object)},
       {"vtable", Hex32(vtable)},
       {"method", Hex32(method)}});
}

void PinyonShiftTraceUiPauseOwnerInit(PPCRegister& r1, PPCRegister& r3,
                                      uint64_t& lr) {
  if (UiExperimentModeValue() != UiExperimentMode::kSceneInsert) {
    return;
  }
  pinyon_shift::diagnostics::RecordEvent(
      "ui.experiment.scene_insert.pause_owner_init",
      {{"stack", Hex32(r1.u32)},
       {"object", Hex32(r3.u32)},
       {"vtable", UiProbeField(r3.u32, 0u)},
       {"caller", Hex32(static_cast<uint32_t>(lr))}});
}

void PinyonShiftTraceUiPauseOwnerBinding(PPCRegister& r1, PPCRegister& r3,
                                         PPCRegister& r28, PPCRegister& r29,
                                         PPCRegister& r30) {
  if (UiExperimentModeValue() != UiExperimentMode::kSceneInsert) {
    return;
  }
  pinyon_shift::diagnostics::RecordEvent(
      "ui.experiment.scene_insert.pause_owner_binding",
      {{"owner", Hex32(r30.u32)},
       {"index", Hex32(r28.u32)},
       {"name", PinyonShiftReadGuestAscii(r1.u32 + 80u, 64u)},
       {"binding", Hex32(r29.u32)},
       {"value", Hex32(r3.u32)},
       {"binding_4", UiProbeField(r29.u32, 4u)}});
}


// Samples the two embedded 12-byte CUI4TextElement objects of every observed
// pause button. The element layout is verified statically as
// {vptr = 0x82026B38, +4, +8}, so a label lives in that pair or in the object
// it points to. Sampling repeats at a bounded cadence so one run shows both the
// pre-binding and the post-binding state of the same element. This is
// read-only: the earlier probe wrote at button + 336, which is outside the
// 280-byte CPauseMenuButton allocation.
void SampleUiTextPairs() {
  static uint32_t frame_tick = 0;
  static uint32_t samples = 0;
  static uint32_t recorded = 0;
  constexpr uint32_t kSampleIntervalFrames = 30u;
  constexpr uint32_t kMaximumSamples = 60u;
  constexpr uint32_t kMaximumRecordedPairs = 480u;
  // CPauseMenuButton embeds three verified 12-byte CUI4TextElement objects:
  // the grandparent constructor creates +164, the button constructor creates
  // +252 and +264 (sub_827E5150 / sub_8264FBA0).
  constexpr std::array<uint32_t, 3> kTextElementOffsets = {164u, 252u, 264u};
  ++frame_tick;
  if (samples >= kMaximumSamples || frame_tick % kSampleIntervalFrames != 0u) {
    return;
  }
  ++samples;
  const uint32_t count = std::min<uint32_t>(
      g_ui_experiment_buttons_count.load(std::memory_order_relaxed),
      kUiExperimentTextTargets);
  for (uint32_t index = 0; index < count; ++index) {
    const uint32_t button = g_ui_experiment_buttons[index];
    if (button == 0u) {
      continue;
    }
    for (const uint32_t offset : kTextElementOffsets) {
      if (recorded >= kMaximumRecordedPairs) {
        return;
      }
      const uint32_t element = button + offset;
      if (!PinyonShiftGuestRangeReadable(element, 12u) ||
          LoadGuestU32(element) != 0x82026B38u) {
        continue;
      }
      const uint32_t value = LoadGuestU32(element + 4u);
      const uint32_t resource = LoadGuestU32(element + 8u);
      const auto describe = [](uint32_t pointer) {
        if (pointer < 0x10000u ||
            !PinyonShiftGuestRangeReadable(pointer, 4u)) {
          return std::string("-");
        }
        const std::string text = PinyonShiftReadGuestAscii(pointer, 32u);
        return text.empty() ? std::string("-") : text;
      };
      if (offset == kTextElementOffsets[0]) {
        // One bounded dump of the button and its label resource per sample, so
        // a run shows where the visible item text is bound.
        std::string button_words;
        for (uint32_t word = 0u; word <= 32u; word += 4u) {
          button_words += Hex32(LoadGuestU32(button + word));
          button_words.push_back(' ');
        }
        const uint32_t label = PinyonShiftGuestRangeReadable(button + 84u, 4u)
                                   ? LoadGuestU32(button + 84u)
                                   : 0u;
        std::string label_words;
        if (label >= 0x10000u && PinyonShiftGuestRangeReadable(label, 32u)) {
          for (uint32_t word = 0u; word < 32u; word += 4u) {
            label_words += Hex32(LoadGuestU32(label + word));
            label_words.push_back(' ');
          }
        }
        pinyon_shift::diagnostics::RecordEvent(
            "ui.experiment.button_state",
            {{"sample", std::to_string(samples)},
             {"slot", std::to_string(index)},
             {"button", Hex32(button)},
             {"button_words_0_32", button_words},
             {"label_resource", Hex32(label)},
             {"label_words_0_32", label_words},
             {"label_ascii", describe(label)},
             {"label_nested_ascii",
              describe(label >= 0x10000u &&
                               PinyonShiftGuestRangeReadable(label, 4u)
                           ? LoadGuestU32(label)
                           : 0u)}});
      }
      ++recorded;
      pinyon_shift::diagnostics::RecordEvent(
          "ui.experiment.text_pair",
          {{"scene", "pause_menu"},
           {"sample", std::to_string(samples)},
           {"slot", std::to_string(index)},
           {"element_offset", std::to_string(offset)},
           {"element", Hex32(element)},
           {"value", Hex32(value)},
           {"resource", Hex32(resource)},
           {"value_ascii", describe(value)},
           {"resource_ascii", describe(resource)}});
    }
  }
}

// Applies the queued SetText operation by sampling the verified label pair of
// each observed pause button at the title update boundary. The operation is
// drained through the host API so the queue-to-guest plumbing stays exercised
// while the write target is still being established.
void ApplyUiTextProbe() {
  static bool saw_operation = false;
  if (!saw_operation) {
    for (const auto& operation : g_ui_experiment_api.Drain()) {
      if (operation.kind == pinyon_shift::ui::Operation::Kind::kSetText &&
          operation.component_id == "pause.menu.label") {
        saw_operation = true;
      }
    }
    if (!saw_operation) {
      return;
    }
  }
  SampleUiTextPairs();
}

// One bounded search over the readable parts of the UI heap region for a
// literal the running screen displays, plus the objects that point at it. Each
// 4 MiB chunk is validated once with QueryRangeAccess and then read directly,
// so the whole 128 MiB window costs a few tens of milliseconds and runs only
// once per process. `write_literal` is empty for the read-only scan mode.
void ScanAndWriteUiLabel(std::string_view write_literal) {
  static uint32_t region_index = 0u;
  static uint32_t cursor = kUiLabelScanBegin;
  static uint32_t rescan_wait = 0;
  static uint32_t total_written = 0;
  const std::string_view literal = UiLabelScanLiteral();
  const uint32_t literal_length = static_cast<uint32_t>(literal.size());
  if (literal_length < 4u || literal_length > 31u) {
    return;
  }
  if (region_index >= kUiLabelScanRegions.size()) {
    // Restart the sweep so a string copied later (for example when the pause
    // overlay is built) is still found while the screen is up.
    if (rescan_wait++ < kUiLabelRescanIntervalFrames) {
      return;
    }
    rescan_wait = 0;
    region_index = 0u;
    cursor = kUiLabelScanRegions[0].begin;
  }
  // A hit is reported once per sweep: `hit_stride` is 1 for ASCII and 2 for
  // UTF-16LE, so the same probe covers both storage forms.
  const auto handle_hit = [&](uint32_t address, uint32_t stride) {
    const auto read_literal = [&](uint32_t at) {
      std::string text;
      text.reserve(literal_length);
      for (uint32_t step = 0; step < literal_length; ++step) {
        const uint8_t byte = LoadGuestU8(at + step * stride);
        if (stride == 1u && byte == 0u) {
          break;
        }
        text.push_back(
            static_cast<char>(byte < 0x20u || byte > 0x7Eu ? '.' : byte));
      }
      return text;
    };
    std::string before;
    bool changed = false;
    if (!write_literal.empty() && total_written < kUiLabelMaximumWrites) {
      before = read_literal(address);
      for (uint32_t step = 0; step < literal_length; ++step) {
        const char replacement =
            step < write_literal.size()
                ? write_literal[step]
                : write_literal[write_literal.size() - 1u];
        StoreGuestU8(address + step * stride, static_cast<uint8_t>(replacement));
        if (stride == 2u) {
          StoreGuestU8(address + step * stride + 1u, 0u);
        }
      }
      ++total_written;
      changed = read_literal(address) != before;
    }
    if (total_written <= kUiLabelMaximumWrites) {
      pinyon_shift::diagnostics::RecordEvent(
          "ui.experiment.label_scan",
          {{"literal", std::string(literal)},
           {"encoding", stride == 1u ? "ascii" : "utf16"},
           {"address", Hex32(address)},
           {"ascii", read_literal(address)},
           {"replacement", std::string(write_literal)},
           {"before", before},
           {"changed", changed ? "1" : "0"}});
    }
  };
  uint32_t budget = kUiLabelScanBytesPerFrame;
  while (region_index < kUiLabelScanRegions.size() && budget > 0u) {
    const UiLabelScanRegion region = kUiLabelScanRegions[region_index];
    const uint32_t stop = std::min(region.end, cursor + budget);
    for (uint32_t block = cursor; block < stop; block += kUiLabelScanBlockSize) {
    const uint32_t block_end = std::min(stop, block + kUiLabelScanBlockSize);
    if (!PinyonShiftGuestRangeReadable(block, block_end - block)) {
      continue;
    }
    for (uint32_t base = block; base + 4u < block_end; base += 4u) {
      const uint32_t word = LoadGuestU32(base);
      const std::array<uint8_t, 4> bytes = {static_cast<uint8_t>(word >> 24),
                                            static_cast<uint8_t>(word >> 16),
                                            static_cast<uint8_t>(word >> 8),
                                            static_cast<uint8_t>(word)};
      for (uint32_t offset = 0; offset < 4u; ++offset) {
        const uint32_t address = base + offset;
        if (address + (literal_length - 1u) * 2u + 1u >= block_end) {
          // Keep every candidate read inside the block that was validated.
          continue;
        }
        for (const uint32_t stride : {1u, 2u}) {
          if (stride == 2u && (offset & 1u) != 0u) {
            continue;
          }
          if (bytes[offset] != static_cast<uint8_t>(literal[0])) {
            continue;
          }
          if (stride == 2u &&
              (offset + 1u >= bytes.size() || bytes[offset + 1u] != 0u)) {
            continue;
          }
          bool match = true;
          for (uint32_t index = 1; index < literal_length; ++index) {
            // Reads outside the validated block are re-checked by the block
            // granularity above; the addresses stay inside the sweep.
            if (LoadGuestU8(address + index * stride) !=
                    static_cast<uint8_t>(literal[index]) ||
                (stride == 2u && LoadGuestU8(address + index * stride + 1u) != 0u)) {
              match = false;
              break;
            }
          }
          if (match) {
            handle_hit(address, stride);
            break;
          }
        }
      }
    }
    }
    budget -= stop - cursor;
    cursor = stop;
    if (cursor >= region.end) {
      ++region_index;
      if (region_index < kUiLabelScanRegions.size()) {
        cursor = kUiLabelScanRegions[region_index].begin;
      }
    }
  }
}

void ApplyUiMutationExperiment() {
  const UiExperimentMode mode = UiExperimentModeValue();
  if (mode == UiExperimentMode::kNone) {
    return;
  }
  if (mode == UiExperimentMode::kTextProbe) {
    ApplyUiTextProbe();
    return;
  }
  if (mode == UiExperimentMode::kLabelScan) {
    ScanAndWriteUiLabel(std::string_view{});
    return;
  }
  if (mode == UiExperimentMode::kLabelWrite) {
    ScanAndWriteUiLabel(UiLabelWriteLiteral());
    return;
  }
  if (g_ui_experiment_button == 0u) {
    return;
  }
  if (!g_ui_experiment_applied) {
    for (const auto& operation : g_ui_experiment_api.Drain()) {
      if (operation.kind != pinyon_shift::ui::Operation::Kind::kSetVisible ||
          operation.component_id != "pause.menu.first" || operation.visible) {
        continue;
      }
      const uint32_t button = g_ui_experiment_button;
      const uint8_t before =
          PinyonShiftGuestRangeReadable(button + 160u, 1u)
              ? LoadGuestU8(button + 160u)
              : 0u;
      StoreGuestU8(button + 160u, 0u);
      g_ui_experiment_applied = true;
      pinyon_shift::diagnostics::RecordEvent(
          "ui.experiment.visible_mutation",
          {{"scene", operation.scene.id},
           {"component", operation.component_id},
           {"button", Hex32(button)},
           {"before", Hex32(before)},
           {"after", Hex32(LoadGuestU8(button + 160u))},
           {"api", "SetVisible"},
           {"boundary", "frame"}});
      break;
    }
  }
  if (g_ui_experiment_applied &&
      PinyonShiftGuestRangeReadable(g_ui_experiment_button + 160u, 1u)) {
    StoreGuestU8(g_ui_experiment_button + 160u, 0u);
  }
}

void PinyonShiftTraceFrameTelemetry(PPCRegister& r28, PPCRegister& r31) {
  PROFILE_SIMULATION_TICK();
  ApplyUiMutationExperiment();
  bool native_race_admitted = false;
  if (PinyonShiftGuestRangeReadable(r31.u32 + 4u, 4u)) {
    const uint32_t native_race_active = LoadGuestU32(r31.u32 + 4u);
    if (PinyonShiftGuestRangeReadable(native_race_active, 16u) &&
        LoadGuestU32(native_race_active) == 0x820148A0u) {
      const uint32_t activity = LoadGuestU32(native_race_active + 8u);
      native_race_admitted = LoadGuestU32(native_race_active + 12u) ==
                                 0x00010174u &&
                             PinyonShiftGuestRangeReadable(activity, 4u) &&
                             LoadGuestU32(activity) == 0x8202A344u;
    }
  }
  const uint64_t native_race_source_frame = rex::perf::GetTotalCounter(
      rex::perf::CounterId::kSourceFrameCount);
  pinyon_shift::native_renderer::PublishNativeRaceAdmission(
      native_race_source_frame, native_race_admitted);
  if (r28.u32 == 0) {
    return;
  }

  if (!FrameTelemetryEnabled()) {
    return;
  }

  const uint32_t route_state = LoadGuestU32(r28.u32 + 2404);
  const uint8_t transition_active = LoadGuestU8(r28.u32 + 4168);

  const uint64_t now_ms = static_cast<uint64_t>(
      std::chrono::duration_cast<std::chrono::milliseconds>(
          std::chrono::steady_clock::now().time_since_epoch())
          .count());
  uint64_t previous_ms =
      g_last_frame_telemetry_ms.load(std::memory_order_relaxed);
  if (now_ms - previous_ms < 200 ||
      !g_last_frame_telemetry_ms.compare_exchange_strong(
          previous_ms, now_ms, std::memory_order_relaxed)) {
    return;
  }

  // These fields are read directly by the frame-loop body immediately after
  // this hook. They provide a stable, read-only route-state seed while vehicle
  // object and transform offsets are discovered from differential captures.
  pinyon_shift::diagnostics::RecordEvent(
      "route.telemetry.frame",
      {{"address", "823EDA10"},
       {"frame_root", Hex32(r28.u32)},
       {"route_root", Hex32(r31.u32)},
       {"generation", Hex32(g_title_generation.load(std::memory_order_acquire))},
       {"route_state", Hex32(route_state)},
       {"transition_active", Hex32(transition_active)}});
}

void PinyonShiftObserveSimulationDelta(PPCRegister& f31) {
  const double seconds = f31.f64;
  if (!std::isfinite(seconds) || seconds < 0.0 || seconds > 0.25) {
    PROFILE_SIMULATION_DELTA_INVALID();
    return;
  }
  PROFILE_SIMULATION_TIME_NS(
      static_cast<int64_t>(std::llround(seconds * 1'000'000'000.0)));
}

void PinyonShiftTraceVehiclePose(PPCRegister& r1, PPCRegister& r30,
                                 PPCRegister& r31) {
  if (r31.u32 == 0) {
    return;
  }

  constexpr uint32_t kActiveSlotOffset = 1500;
  constexpr uint32_t kSlotStride = 1056;
  constexpr uint32_t kPositionOffset = 15120;
  constexpr uint32_t kForwardOffset = 15184;
  constexpr float kMaximumPerUpdateDistanceSquared = 100.0f;
  constexpr uint64_t kRebaseSynchronizationMs = 100;
  const uint32_t slot = LoadGuestU32(r31.u32 + kActiveSlotOffset);
  const uint64_t slot_base = static_cast<uint64_t>(r31.u32) +
                             static_cast<uint64_t>(slot) * kSlotStride;
  const uint64_t position_address_64 = slot_base + kPositionOffset;
  const uint64_t forward_address_64 = slot_base + kForwardOffset;
  if (slot > 4095 || forward_address_64 > UINT32_MAX) {
    return;
  }

  const uint32_t position_address = static_cast<uint32_t>(position_address_64);
  const uint32_t forward_address = static_cast<uint32_t>(forward_address_64);
  const uint64_t now_ms = static_cast<uint64_t>(
      std::chrono::duration_cast<std::chrono::milliseconds>(
          std::chrono::steady_clock::now().time_since_epoch())
          .count());
  const uint32_t generation =
      g_title_generation.load(std::memory_order_acquire);
  const VehiclePose observed{
      LoadGuestF32(position_address),
      LoadGuestF32(position_address + 4),
      LoadGuestF32(position_address + 8),
      LoadGuestF32(position_address + 12),
      LoadGuestF32(forward_address),
      LoadGuestF32(forward_address + 4),
      LoadGuestF32(forward_address + 8),
      LoadGuestF32(forward_address + 12),
  };
  VehiclePose effective = observed;
  bool suppressed = false;
  const bool stabilization_enabled =
      REXCVAR_GET(pinyon_shift_stabilize_vehicle_presentation);
  {
    std::lock_guard lock(g_vehicle_hook_sample_mutex);
    auto& state = g_vehicle_presentation_state;
    if (!stabilization_enabled) {
      state = {};
    } else if (!state.valid || state.generation != generation ||
               state.source != r30.u32) {
      if (IsPlausibleVehiclePose(observed)) {
        state = {true, generation, r30.u32, observed};
      }
    } else if (!IsPlausibleVehiclePose(observed)) {
      effective = state.accepted;
      suppressed = true;
      state.pending = false;
    } else if (PositionDistanceSquared(observed, state.accepted) <=
               kMaximumPerUpdateDistanceSquared) {
      state.accepted = observed;
      state.pending = false;
    } else {
      // The title builds this transform in a stack argument block. During a
      // world-cell rebase it exposes the new local pose before the companion
      // camera/world basis is ready. That 31-33-unit mismatch lasts for the
      // two or three frames visible in the supplied recording. Bridge only
      // that synchronization window, then accept a coherent rebased pose;
      // waiting for the local value to return would freeze ordinary driving.
      if (!state.pending ||
          PositionDistanceSquared(observed, state.pending_last) >
              kMaximumPerUpdateDistanceSquared) {
        state.pending = true;
        state.pending_last = observed;
        state.pending_since_ms = now_ms;
      } else {
        state.pending_last = observed;
      }
      if (state.pending &&
          now_ms - state.pending_since_ms >= kRebaseSynchronizationMs) {
        state.accepted = observed;
        state.pending = false;
      } else if (state.pending) {
        effective = state.accepted;
        suppressed = true;
      }
    }
  }

  if (suppressed) {
    StoreVehiclePose(position_address, forward_address, effective);
  }

  pinyon_shift::fh1_render_test::ObserveVehiclePose(effective.x, effective.y,
                                                    effective.z);

  if (suppressed && FrameTelemetryEnabled()) {
    uint64_t previous_discontinuity_ms =
        g_last_vehicle_discontinuity_ms.load(std::memory_order_relaxed);
    if (now_ms - previous_discontinuity_ms >= 100 &&
        g_last_vehicle_discontinuity_ms.compare_exchange_strong(
            previous_discontinuity_ms, now_ms, std::memory_order_relaxed)) {
      pinyon_shift::diagnostics::RecordEvent(
          "vehicle.telemetry.discontinuity",
          {{"address", "82BC5A3C"},
           {"generation", Hex32(generation)},
           {"caller_lr", Hex32(LoadGuestU32(r1.u32 + 392))},
           {"source", Hex32(r30.u32)},
           {"suppressed", "1"},
           {"x", fmt::format("{}", observed.x)},
           {"y", fmt::format("{}", observed.y)},
           {"z", fmt::format("{}", observed.z)},
           {"effective_x", fmt::format("{}", effective.x)},
           {"effective_y", fmt::format("{}", effective.y)},
           {"effective_z", fmt::format("{}", effective.z)}});
    }
  }
  if (!FrameTelemetryEnabled()) {
    return;
  }
  uint64_t previous_ms =
      g_last_vehicle_pose_ms.load(std::memory_order_relaxed);
  if (now_ms - previous_ms < 200 ||
      !g_last_vehicle_pose_ms.compare_exchange_strong(
          previous_ms, now_ms, std::memory_order_relaxed)) {
    return;
  }

  pinyon_shift::diagnostics::RecordEvent(
      "vehicle.telemetry.pose",
      {{"address", "82BC5A3C"},
       {"generation", Hex32(generation)},
       {"caller_lr", Hex32(LoadGuestU32(r1.u32 + 392))},
       {"source", Hex32(r30.u32)},
       {"owner", Hex32(r31.u32)},
       {"slot", fmt::format("{}", slot)},
       {"position_address", Hex32(position_address)},
       {"forward_address", Hex32(forward_address)},
       {"x", fmt::format("{}", effective.x)},
       {"y", fmt::format("{}", effective.y)},
       {"z", fmt::format("{}", effective.z)},
       {"w", fmt::format("{}", effective.w)},
       {"forward_x", fmt::format("{}", effective.forward_x)},
       {"forward_y", fmt::format("{}", effective.forward_y)},
       {"forward_z", fmt::format("{}", effective.forward_z)}});
}

void PinyonShiftTraceBdz82AD8138(PPCRegister& ctr) {
  if (ctr.u32 == 1) {
    pinyon_shift::diagnostics::RecordEvent(
        "bdz.out_of_range", {{"address", "82AD8138"}, {"selector", "6"}});
  }
}

void PinyonShiftTraceSavePayload(PPCRegister& r4, PPCRegister& r5,
                                 PPCRegister& r12) {
  SnapshotSavePayload("encrypted", r4.u32, r5.u32, r12.u32);
}

void PinyonShiftTraceSaveStreamPayload(PPCRegister& r4, PPCRegister& r5,
                                       PPCRegister& r12) {
  SnapshotSavePayload("stream", r4.u32, r5.u32, r12.u32);
}

void PinyonShiftTraceSavePreEncryption(PPCRegister& r4, PPCRegister& r5) {
  SeedCareerCheckpointInSavePayload(r4.u32, r5.u32);
  SnapshotSavePayload("plaintext", r4.u32, r5.u32, 0x82C666D4u);
}

void PinyonShiftRestoreCareerEligibility(PPCRegister& r3, PPCRegister& r4,
                                         PPCRegister& r31) {
  const uint32_t activity = LoadGuestU32(r31.u32 + 196u);
  if (activity == 0u || r3.u32 == 0u) {
    return;
  }

  const uint8_t active = LoadGuestU8(activity + 40u);
  const uint32_t stage = LoadGuestU32(activity + 44u);
  // Stage 1 is the in-progress Viper drive. Its serialized activity and car
  // position do not include the transient route/arrival trigger, so restoring
  // it produces route-less free roam. Only restore boundaries reached after
  // the title completes that drive.
  if (stage != 2u && stage != 7u && stage != 10u) {
    return;
  }

  // sub_8252AA48 reads the per-profile career eligibility byte at
  // r3 + r4 + 80. Merely overriding its return value is enough to reload the
  // saved activity, but leaves later progression gates seeing the byte as
  // false. Repair the actual byte before the title reads it so a restored
  // stage remains eligible to complete normally.
  const uint32_t eligibility_address = r3.u32 + r4.u32 + 80u;
  const uint8_t previous_eligibility = LoadGuestU8(eligibility_address);
  if (previous_eligibility != 0u) {
    return;
  }

  StoreGuestU8(eligibility_address, 1u);
  pinyon_shift::diagnostics::RecordEvent(
      "save.career_checkpoint.eligibility_restore",
      {{"result", "restored"},
       {"owner", Hex32(r31.u32)},
       {"activity", Hex32(activity)},
       {"eligibility_address", Hex32(eligibility_address)},
       {"previous_eligibility", fmt::format("{}", previous_eligibility)},
       {"active", fmt::format("{}", active)},
       {"stage", fmt::format("{}", stage)}});
}

void PinyonShiftRestoreCareerCheckpointGate(PPCRegister& r3,
                                             PPCRegister& r31) {
  const uint32_t activity = LoadGuestU32(r31.u32 + 196u);
  uint8_t active = activity ? LoadGuestU8(activity + 40u) : 0u;
  const uint32_t stage = activity ? LoadGuestU32(activity + 44u) : 0u;
  if (SaveTraceEnabled()) {
    pinyon_shift::diagnostics::RecordEvent(
        "save.career_checkpoint.gate",
        {{"owner", Hex32(r31.u32)},
         {"activity", Hex32(activity)},
         {"gate", fmt::format("{}", r3.u32)},
         {"active", fmt::format("{}", active)},
         {"stage", fmt::format("{}", stage)}});
  }

  // The activity is the durable checkpoint. Preserve the post-read return
  // override for older saves, and emit the established restore marker even
  // when the pre-read eligibility repair made the title's own result true.
  if (active != 1u ||
      (stage != 2u && stage != 7u && stage != 10u)) {
    return;
  }
  const bool gate_forced = r3.u32 == 0u;
  if (gate_forced) {
    r3.u32 = 1u;
  }
  pinyon_shift::diagnostics::RecordEvent(
      "save.career_checkpoint.gate_override",
      {{"result", "restored"},
       {"owner", Hex32(r31.u32)},
       {"activity", Hex32(activity)},
       {"gate_forced", gate_forced ? "1" : "0"},
       {"stage", fmt::format("{}", stage)}});
}

void PinyonShiftPersistPostViperCheckpoint(PPCRegister& r31) {
  const uint32_t activity = LoadGuestU32(r31.u32 + 196u);
  if (activity == 0) {
    return;
  }

  const uint8_t previous_active = LoadGuestU8(activity + 40u);
  const uint32_t previous_stage = LoadGuestU32(activity + 44u);
  if (previous_stage != 1u) {
    return;
  }

  // sub_828D7EB0 has just advanced the live first-time-career controller to
  // stage 2, the Corrado drive to the festival. Mirror that exact boundary to
  // the durable activity before the title's next ordinary profile save.
  StoreGuestU8(activity + 40u, 1u);
  StoreGuestU32(activity + 44u, 2u);
  pinyon_shift::diagnostics::RecordEvent(
      "save.career_checkpoint.advance",
      {{"owner", Hex32(r31.u32)},
       {"activity", Hex32(activity)},
       {"previous_active", fmt::format("{}", previous_active)},
       {"active", "1"},
       {"previous_stage", fmt::format("{}", previous_stage)},
       {"stage", "2"}});
}

void PinyonShiftTracePersistedProfileOwner(PPCRegister& r3, PPCRegister& r26,
                                           PPCRegister& r28, PPCRegister& r30,
                                           PPCRegister& r31) {
  if (!SaveTraceEnabled()) {
    return;
  }
  pinyon_shift::diagnostics::RecordEvent(
      "save.profile.owner_result",
      {{"address", "825195F4"},
       {"result", Hex32(r3.u32)},
       {"success_flag", Hex32(r26.u32)},
       {"refresh_requested", Hex32(r28.u32)},
       {"content_owner", Hex32(r30.u32)},
       {"profile_owner", Hex32(r31.u32)}});
}

void PinyonShiftTracePersistedProfileResult(PPCRegister& r3,
                                            PPCRegister& r31) {
  if (!SaveTraceEnabled()) {
    return;
  }
  pinyon_shift::diagnostics::RecordEvent(
      "save.profile.result",
      {{"address", "82568490"},
       {"result", Hex32(r3.u32)},
       {"owner", Hex32(r31.u32)}});
}

void PinyonShiftTraceFrontEndProfileResult(PPCRegister& r3,
                                           PPCRegister& r31) {
  if (!SaveTraceEnabled()) {
    return;
  }
  pinyon_shift::diagnostics::RecordEvent(
      "save.frontend.profile_result",
      {{"address", "824ED444"},
       {"result", Hex32(r3.u32)},
       {"owner", Hex32(r31.u32)}});
}

void PinyonShiftTraceFrontEndStateResult(PPCRegister& r3, PPCRegister& r29,
                                         PPCRegister& r31) {
  if (!SaveTraceEnabled()) {
    return;
  }
  pinyon_shift::diagnostics::RecordEvent(
      "save.frontend.state_result",
      {{"address", "827A1DC4"},
       {"result", Hex32(r3.u32)},
       {"payload", Hex32(r29.u32)},
       {"owner", Hex32(r31.u32)}});
}

void PinyonShiftTraceBdz82AD813C(PPCRegister& ctr) {
  if (ctr.u32 == 1) {
    pinyon_shift::diagnostics::RecordEvent(
        "bdz.out_of_range", {{"address", "82AD813C"}, {"selector", "7"}});
  }
}

void PinyonShiftTraceMainLoopExit(PPCRegister& r29, PPCRegister& r30,
                                  PPCRegister& r31) {
  const auto r29_hex = Hex32(r29.u32);
  const auto r30_hex = Hex32(r30.u32);
  const auto r31_hex = Hex32(r31.u32);
  pinyon_shift::diagnostics::RecordEvent(
      "main_loop.exit",
      {{"address", "823EE584"},
       {"r29", r29_hex},
       {"r30", r30_hex},
       {"r31", r31_hex}});
}

void PinyonShiftTraceCleanupPointerCheck(PPCRegister& r31) {
  const uint32_t field = r31.u32 + 684;
  g_cleanup_pointer_field.store(field, std::memory_order_release);
  const uint32_t value = LoadGuestU32(field);
  if (value != 0) {
    g_cleanup_pointer_live.store(true, std::memory_order_release);
  } else if (g_cleanup_pointer_live.exchange(false, std::memory_order_acq_rel)) {
    g_title_generation.fetch_add(1, std::memory_order_acq_rel);
    g_opening_movie_skip_logged.store(false, std::memory_order_release);
  }
  const auto owner_hex = Hex32(r31.u32);
  const auto field_hex = Hex32(field);
  const auto value_hex = Hex32(value);
  pinyon_shift::diagnostics::RecordEvent(
      "cleanup.pointer.check",
      {{"address", "82482264"},
       {"owner", owner_hex},
       {"field", field_hex},
       {"value", value_hex},
       {"generation", Hex32(g_title_generation.load(std::memory_order_acquire))}});
}

void PinyonShiftTraceCleanupPointerWait(PPCRegister& r31) {
  if (r31.u32 !=
      g_cleanup_pointer_field.load(std::memory_order_acquire)) {
    return;
  }
  const auto field_hex = Hex32(r31.u32);
  const auto value_hex = Hex32(LoadGuestU32(r31.u32));
  pinyon_shift::diagnostics::RecordEvent(
      "cleanup.pointer.wait",
      {{"address", "8247D534"},
       {"field", field_hex},
       {"value", value_hex}});
}

static bool PinyonShiftGuestRangeReadable(uint32_t address, uint32_t size) {
  if (size == 0) {
    return true;
  }
  const uint32_t end = address + size - 1u;
  auto* memory = rex::system::kernel_state()->memory();
  auto* heap = end >= address ? memory->LookupHeap(address) : nullptr;
  if (!heap || heap->QueryRangeAccess(address, end) ==
                   rex::memory::PageAccess::kNoAccess) {
    return false;
  }

  // QueryRangeAccess reflects the guest heap's page-table metadata. A stale
  // relocated geometry pointer can still land in a reserved or decommitted
  // host page whose guest metadata looks readable, and the generated load
  // dereferences the host mapping directly. Verify every host page touched by
  // the range as well so the validation hook cannot itself raise a read AV.
  const size_t page_size = rex::memory::page_size();
  uint64_t cursor = address;
  while (cursor <= end) {
    auto* host_address =
        memory->TranslateVirtual(static_cast<uint32_t>(cursor));
    size_t region_length = page_size;
    rex::memory::PageAccess host_access =
        rex::memory::PageAccess::kNoAccess;
    if (!rex::memory::QueryProtect(host_address, region_length, host_access) ||
        host_access == rex::memory::PageAccess::kNoAccess) {
      return false;
    }

    const uintptr_t host_value =
        reinterpret_cast<uintptr_t>(host_address);
    const size_t page_remaining =
        page_size - (host_value % page_size);
    const uint64_t range_remaining =
        static_cast<uint64_t>(end) - cursor + 1u;
    cursor += std::min<uint64_t>(range_remaining, page_remaining);
  }
  return true;
}

static std::string PinyonShiftReadGuestAscii(uint32_t address,
                                             uint32_t maximum_length) {
  if (maximum_length == 0 || !PinyonShiftGuestRangeReadable(address, 1u)) {
    return {};
  }
  std::string value;
  value.reserve(maximum_length);
  for (uint32_t offset = 0; offset < maximum_length; ++offset) {
    if (!PinyonShiftGuestRangeReadable(address + offset, 1u)) {
      return {};
    }
    const uint8_t character = LoadGuestU8(address + offset);
    if (character == 0) {
      return value.size() >= 3 ? value : std::string{};
    }
    if (character < 0x20 || character > 0x7E) {
      return {};
    }
    value.push_back(static_cast<char>(character));
  }
  return {};
}

// --- UI-14 scene-payload interception (pause insertion, stream side) -------
//
// The pause screen is built from `GAME:\Media\UI\Scenes\UI4\925_PAUSE_MENU.bgf`
// (image format string 0x82036AD4). Every authored item of that scene is
// produced by the deserializer sub_82F26560, which reads its per-item bytes
// through the 12-byte reader stored at section+12. That reader's slot-1 method
// sub_82F25568 copies from the source object held at reader+4, so the item
// stream is already a derived stream rather than a plain guest array.
//
// This probe answers the two questions the UI-14 stream route needs before any
// payload rewrite is attempted, read-only and default-off
// (`PINYON_SHIFT_UI_EXPERIMENT=scene_probe`):
//   1. where the pause item stream is, by dumping the section/reader/source
//      state and the parsed item fields in the pause window;
//   2. whether the pause item stream and the decompressed member exist writable
//      in guest memory, which a one-shot load-time rewrite would require.
namespace {

constexpr uint32_t kUiSceneProbeEventLimit = 24u;
constexpr uint32_t kUiSceneProbeBlockSize = 0x10000u;
constexpr uint32_t kUiSceneProbeFrameMinimum = 900u;
constexpr uint32_t kUiSceneProbeMaximumWordHits = 8u;
std::atomic<uint32_t> g_ui_scene_entry_count{};
std::atomic<uint32_t> g_ui_scene_length_count{};
std::atomic<uint32_t> g_ui_scene_item_count{};
std::atomic<uint32_t> g_ui_scene_insert_item_count{};
std::atomic<uint32_t> g_ui_scene_insert_capture_remaining{};
std::atomic<uint32_t> g_ui_scene_read_count{};
std::atomic<uint32_t> g_ui_scene_read_result_count{};
std::atomic<bool> g_ui_scene_payload_scanned{};
// 0x22352942 is the first pause row's wrapper name hash and 0xBDF05338 the
// pause_menu_button element contract hash; both appear seven times in the
// decompressed 925_PAUSE_MENU.bgf, so a scan that finds them names the item
// stream (or its source buffer) directly.
constexpr uint32_t kUiSceneRowWord = 0x22352942u;
constexpr uint32_t kUiSceneItemWord = 0xBDF05338u;

uint32_t UiSceneWordOrZero(uint32_t address) {
  return PinyonShiftGuestRangeReadable(address, 4u) ? LoadGuestU32(address) : 0u;
}

std::string UiSceneHexWords(uint32_t address, uint32_t count) {
  if (address == 0u ||
      !PinyonShiftGuestRangeReadable(address, count * 4u)) {
    return "unreadable";
  }
  std::string text;
  text.reserve(count * 9u);
  for (uint32_t index = 0; index < count; ++index) {
    if (index != 0u) {
      text.push_back(' ');
    }
    text += Hex32(LoadGuestU32(address + index * 4u));
  }
  return text;
}

std::string UiSceneGuestBytes(uint32_t address, uint32_t size) {
  if (address == 0u || !PinyonShiftGuestRangeReadable(address, size)) {
    return "unreadable";
  }
  std::string text;
  text.reserve(size * 3u);
  for (uint32_t index = 0; index < size; ++index) {
    if (index != 0u) {
      text.push_back(' ');
    }
    text += fmt::format("{:02X}", LoadGuestU8(address + index));
  }
  return text;
}

// One bounded host-side pass over one guest region for the pause wrapper name
// and the pause_menu_button contract hash. The scene builder runs it once.
void UiSceneScanRegion(uint32_t begin, uint32_t end,
                       std::array<uint32_t, kUiSceneProbeMaximumWordHits>&
                           row_hits,
                       uint32_t& row_count,
                       std::array<uint32_t, kUiSceneProbeMaximumWordHits>&
                           item_hits,
                       uint32_t& item_count) {
  for (uint32_t block = begin; block < end; block += kUiSceneProbeBlockSize) {
    const uint32_t block_end = std::min(end, block + kUiSceneProbeBlockSize);
    if (!PinyonShiftGuestRangeReadable(block, block_end - block)) {
      continue;
    }
    for (uint32_t base = block; base + 4u <= block_end; base += 4u) {
      const uint32_t word = LoadGuestU32(base);
      if (word == kUiSceneRowWord && row_count < kUiSceneProbeMaximumWordHits) {
        row_hits[row_count++] = base;
      }
      if (word == kUiSceneItemWord &&
          item_count < kUiSceneProbeMaximumWordHits) {
        item_hits[item_count++] = base;
      }
    }
  }
}

// The seven pause row wrapper name hashes as they appear in the authored
// 925_PAUSE_MENU.bgf; locating them inside the derived item stream is what
// ties the stream back to the file.
constexpr std::array<uint32_t, 7> kUiSceneRowWords = {
    0x22352942u, 0x22362981u, 0x223729C0u, 0x223829FFu,
    0x22392A3Eu, 0x223A2A7Du, 0x223B2ABCu};
std::atomic<uint32_t> g_ui_scene_stream_scan_count{};

const auto UiSceneHitsText = [](const auto& hits, uint32_t count) {
  std::string text;
  for (uint32_t index = 0; index < count; ++index) {
    if (!text.empty()) {
      text.push_back(',');
    }
    text += Hex32(hits[index]);
  }
  return text;
};

void UiSceneScanPayloadOnce(uint32_t section) {
  bool expected = false;
  if (!g_ui_scene_payload_scanned.compare_exchange_strong(
          expected, true, std::memory_order_relaxed)) {
    return;
  }
  std::array<uint32_t, kUiSceneProbeMaximumWordHits> row_hits{};
  std::array<uint32_t, kUiSceneProbeMaximumWordHits> item_hits{};
  uint32_t row_count = 0;
  uint32_t item_count = 0;
  for (const UiLabelScanRegion& region : kUiLabelScanRegions) {
    UiSceneScanRegion(region.begin, region.end, row_hits, row_count, item_hits,
                      item_count);
  }
  pinyon_shift::diagnostics::RecordEvent(
      "ui.scene.payload_scan",
      {{"address", "82F26560"},
       {"frame",
        std::to_string(pinyon_shift::fh1_render_test::CurrentFrame())},
       {"section", Hex32(section)},
       {"row_hits", std::to_string(row_count)},
       {"row_addresses", UiSceneHitsText(row_hits, row_count)},
       {"item_hits", std::to_string(item_count)},
       {"item_addresses", UiSceneHitsText(item_hits, item_count)},
       {"row_context",
        row_count > 0u ? UiSceneGuestBytes(row_hits[0], 64u)
                       : std::string("-")}});
}

// Describes one item section of the derived document stream: where its cursor
// sits, what it declares, and where the authored pause row records live inside
// it. Runs for every section until the row records have been located.
uint32_t g_ui_scene_buffer_base{};

void UiSceneStreamScanOnce(uint32_t cursor) {
  if (cursor == 0u || !PinyonShiftGuestRangeReadable(cursor, 8u)) {
    return;
  }
  const uint32_t declared = LoadGuestU32(cursor);
  std::string row_offsets;
  uint32_t row_hits = 0;
  for (const uint32_t row : kUiSceneRowWords) {
    for (uint32_t offset = 0; offset + 4u <= declared; offset += 4u) {
      if (!PinyonShiftGuestRangeReadable(cursor + offset, 4u)) {
        break;
      }
      if (LoadGuestU32(cursor + offset) == row) {
        if (!row_offsets.empty()) {
          row_offsets.push_back(',');
        }
        row_offsets += fmt::format("{}:{}", Hex32(row), std::to_string(offset));
        ++row_hits;
        break;
      }
    }
  }
  uint32_t item_hits = 0;
  uint32_t first_item_offset = 0;
  for (uint32_t offset = 0; offset + 4u <= declared; offset += 4u) {
    if (!PinyonShiftGuestRangeReadable(cursor + offset, 4u)) {
      break;
    }
    if (LoadGuestU32(cursor + offset) == kUiSceneItemWord) {
      if (item_hits == 0u) {
        first_item_offset = offset;
      }
      ++item_hits;
    }
  }
  const bool interesting = row_hits > 0u || item_hits > 0u;
  const uint32_t index =
      g_ui_scene_stream_scan_count.fetch_add(1, std::memory_order_relaxed);
  if (!interesting && index >= 6u) {
    return;
  }
  if (index >= 96u) {
    return;
  }
  pinyon_shift::diagnostics::RecordEvent(
      "ui.scene.stream_scan",
      {{"address", "82F265D4"},
       {"frame",
        std::to_string(pinyon_shift::fh1_render_test::CurrentFrame())},
       {"index", std::to_string(index)},
       {"cursor", Hex32(cursor)},
       {"buffer_base", Hex32(g_ui_scene_buffer_base)},
       {"buffer_offset", Hex32(cursor - g_ui_scene_buffer_base)},
       {"declared", Hex32(declared)},
       {"after_section", Hex32(UiSceneWordOrZero(cursor + declared))},
       {"head", UiSceneGuestBytes(cursor, 48u)},
       {"row_hits", std::to_string(row_hits)},
       {"row_offsets", row_offsets},
       {"item_hits", std::to_string(item_hits)},
       {"first_item_offset", std::to_string(first_item_offset)}});
}

}  // namespace

// --- UI-14 loader-boundary scene payload substitution (pause insertion) ----
//
// The pause member reaches the scene deserializer through the 12-byte reader at
// document+12 whose slot-1 method sub_82F25568 copies out of the object at
// reader+4. That object is a stream cursor: +4 is the member's byte offset
// already consumed (a run that reached the pause window read 0x3AE2 as the
// first item offset and 0x607/0x106 as the section's header counts) while +0
// is an internal buffer/index pointer of the file stream, not the member
// image, so the loader cannot be redirected by swapping that word. The bytes
// the loader actually receives are still the authored member verbatim, and the
// reader hands every one of them to its destination buffer inside slot 1, so
// the boundary is intercepted there: the re-encoded member is materialised in
// guest memory once and every byte the reader delivers for the pause member's
// stream is rewritten from it.
//
// `PINYON_SHIFT_UI_EXPERIMENT=scene_insert` enables this route. It is
// default-off, one-shot at load and does no per-frame work. The re-encoded
// member named by PINYON_SHIFT_UI_SCENE_INSERT_FILE is read from disk once and
// copied into one SystemHeapAlloc buffer; a stream is recognised as the pause
// member by the first 0x24 bytes it delivers (identical in the authored and
// re-encoded members), and from then on its deliveries are served from that
// guest copy. The item count sub_82F26560 reads as
// `*(section+16) + *(section+20)` is verified at the deserializer entry and
// repaired to the re-encoded count only when the member's header words did not
// already carry it, which covers the reads that preceded recognition.
namespace {

constexpr uint32_t kUiSceneInsertMaximumBytes = 4u * 1024u * 1024u;
constexpr uint32_t kUiSceneInsertEventLimit = 96u;
// Bytes of the member prefix the recognition compares. The authored member's
// first 0x24 bytes carry the container header and its member-specific id-space
// word, and the re-encoder leaves all of them untouched.
constexpr uint32_t kUiSceneInsertDecisionBytes = 0x24u;
constexpr uint32_t kUiSceneInsertMaximumTailEvents = 4u;

std::atomic<bool> g_ui_scene_insert_load_attempted{};
std::atomic<uint32_t> g_ui_scene_insert_buffer{};
std::atomic<uint32_t> g_ui_scene_insert_size{};
std::atomic<uint32_t> g_ui_scene_insert_expected_items{};
std::atomic<uint32_t> g_ui_scene_insert_expected_declared{};
std::atomic<uint32_t> g_ui_scene_insert_events{};
std::atomic<uint32_t> g_ui_scene_insert_tail_events{};
std::vector<uint8_t> g_ui_scene_insert_bytes;
// Guest direction word -> recognition and delivery state for that stream. The
// objects are recycled by the allocator, so a delivery that moves the offset
// backwards starts a new stream lifetime and is recognised again.
struct UiSceneInsertStreamState {
  std::array<uint8_t, kUiSceneInsertDecisionBytes> prefix{};
  std::array<bool, kUiSceneInsertDecisionBytes> seen{};
  bool decided = false;
  bool ours = false;
  uint32_t deliveries = 0;
  uint32_t substituted = 0;
  uint32_t maximum_position = 0;
};
struct UiSceneInsertReadRequest {
  uint32_t stream = 0;
  uint32_t destination = 0;
  uint32_t position = 0;
  uint32_t count = 0;
};
std::mutex g_ui_scene_insert_mutex;
std::map<uint32_t, UiSceneInsertStreamState> g_ui_scene_insert_streams;
std::map<uint32_t, UiSceneInsertReadRequest> g_ui_scene_insert_requests;

std::string UiSceneInsertEnvironment(const char* name) {
#if defined(_WIN32)
  char* value = nullptr;
  size_t value_size = 0;
  if (_dupenv_s(&value, &value_size, name) != 0) {
    return {};
  }
  const std::string owned = value ? std::string(value) : std::string();
  std::free(value);
  return owned;
#else
  const char* value = std::getenv(name);
  return value ? std::string(value) : std::string();
#endif
}

uint32_t UiSceneInsertEnvironmentWord(const char* name) {
  const std::string text = UiSceneInsertEnvironment(name);
  if (text.empty()) {
    return 0u;
  }
  char* end = nullptr;
  const unsigned long parsed = std::strtoul(text.c_str(), &end, 0);
  return end != text.c_str() ? static_cast<uint32_t>(parsed) : 0u;
}

uint32_t UiSceneInsertPayloadWord(uint32_t offset) {
  const std::vector<uint8_t>& bytes = g_ui_scene_insert_bytes;
  if (offset + 4u > bytes.size()) {
    return 0u;
  }
  return (static_cast<uint32_t>(bytes[offset]) << 24) |
         (static_cast<uint32_t>(bytes[offset + 1u]) << 16) |
         (static_cast<uint32_t>(bytes[offset + 2u]) << 8) |
         static_cast<uint32_t>(bytes[offset + 3u]);
}

void UiSceneInsertRecord(
    const char* event,
    std::initializer_list<pinyon_shift::diagnostics::Field> fields) {
  if (g_ui_scene_insert_events.fetch_add(1u, std::memory_order_relaxed) >=
      kUiSceneInsertEventLimit) {
    return;
  }
  pinyon_shift::diagnostics::RecordEvent(event, fields);
}

// Read the re-encoded member once and place one guest copy of it. Returns false
// while no payload is available, which leaves the guest stream untouched.
bool EnsureUiSceneInsertPayload() {
  if (g_ui_scene_insert_load_attempted.exchange(true,
                                                std::memory_order_acq_rel)) {
    return g_ui_scene_insert_buffer.load(std::memory_order_acquire) != 0u;
  }
  const std::string path =
      UiSceneInsertEnvironment("PINYON_SHIFT_UI_SCENE_INSERT_FILE");
  if (path.empty()) {
    UiSceneInsertRecord("ui.experiment.scene_insert.declined",
                        {{"reason", "missing_file"}});
    return false;
  }
  std::ifstream stream(path, std::ios::binary);
  if (!stream) {
    UiSceneInsertRecord("ui.experiment.scene_insert.declined",
                        {{"reason", "unreadable"}, {"path", path}});
    return false;
  }
  stream.seekg(0, std::ios::end);
  const std::streamoff length = stream.tellg();
  if (length <= 0 ||
      length > static_cast<std::streamoff>(kUiSceneInsertMaximumBytes)) {
    UiSceneInsertRecord("ui.experiment.scene_insert.declined",
                        {{"reason", "size"},
                         {"bytes", std::to_string(length)}});
    return false;
  }
  stream.seekg(0, std::ios::beg);
  g_ui_scene_insert_bytes.assign(static_cast<std::size_t>(length), 0u);
  stream.read(reinterpret_cast<char*>(g_ui_scene_insert_bytes.data()),
              static_cast<std::streamsize>(length));
  if (!stream) {
    g_ui_scene_insert_bytes.clear();
    UiSceneInsertRecord("ui.experiment.scene_insert.declined",
                        {{"reason", "short_read"}, {"path", path}});
    return false;
  }
  const std::vector<uint8_t>& bytes = g_ui_scene_insert_bytes;
  if (bytes.size() < 0x140u ||
      std::string_view(reinterpret_cast<const char*>(bytes.data() + 6u), 8u) !=
          "AnarkBGF") {
    UiSceneInsertRecord("ui.experiment.scene_insert.declined",
                        {{"reason", "not_a_scene"},
                         {"head", Hex32(UiSceneInsertPayloadWord(0u))}});
    return false;
  }
  // The re-encoded member carries its own item counts at the two header words
  // the title copies into the section, so the expected loop count is read from
  // it rather than trusted from the environment.
  const uint32_t elements = UiSceneInsertPayloadWord(0x24u);
  const uint32_t wrappers = UiSceneInsertPayloadWord(0x28u);
  const uint32_t declared =
      UiSceneInsertEnvironmentWord("PINYON_SHIFT_UI_SCENE_EXPECT_DECLARED");
  g_ui_scene_insert_expected_items.store(elements + wrappers,
                                         std::memory_order_release);
  g_ui_scene_insert_expected_declared.store(declared,
                                            std::memory_order_release);
  auto* memory = rex::system::kernel_state()->memory();
  const uint32_t buffer = memory->SystemHeapAlloc(
      static_cast<uint32_t>(bytes.size()), 16u);
  auto* base = memory->virtual_membase();
  std::memcpy(base + buffer, bytes.data(), bytes.size());
  g_ui_scene_insert_buffer.store(buffer, std::memory_order_release);
  g_ui_scene_insert_size.store(static_cast<uint32_t>(bytes.size()),
                               std::memory_order_release);
  UiSceneInsertRecord("ui.experiment.scene_insert.payload",
                      {{"path", path},
                       {"bytes", std::to_string(bytes.size())},
                       {"buffer", Hex32(buffer)},
                       {"elements", Hex32(elements)},
                       {"wrappers", Hex32(wrappers)},
                       {"expected_items", Hex32(elements + wrappers)},
                       {"expected_declared", Hex32(declared)}});
  return true;
}

std::string UiSceneInsertPrefixText(
    const UiSceneInsertStreamState& state) {
  std::string text;
  text.reserve(kUiSceneInsertDecisionBytes * 3u);
  for (uint32_t index = 0; index < kUiSceneInsertDecisionBytes; ++index) {
    if (index != 0u) {
      text.push_back(' ');
    }
    text += fmt::format("{:02X}", state.seen[index] ? state.prefix[index] : 0u);
  }
  return text;
}

// True when the guest stream at `stream` already delivers the re-encoded
// member. Used by the load-time checks that run outside the reader.
bool UiSceneInsertStreamIsOurs(uint32_t stream) {
  if (stream == 0u) {
    return false;
  }
  std::lock_guard lock(g_ui_scene_insert_mutex);
  const auto found = g_ui_scene_insert_streams.find(stream);
  return found != g_ui_scene_insert_streams.end() && found->second.decided &&
         found->second.ours;
}

void UiSceneInsertCaptureRead(uint32_t reader, uint32_t destination,
                              uint32_t count) {
  if (reader == 0u || count == 0u || count > 0x10000u ||
      !PinyonShiftGuestRangeReadable(reader + 4u, 4u)) {
    return;
  }
  const uint32_t stream = LoadGuestU32(reader + 4u);
  if (stream == 0u || !PinyonShiftGuestRangeReadable(stream + 4u, 4u)) {
    return;
  }
  std::lock_guard lock(g_ui_scene_insert_mutex);
  g_ui_scene_insert_requests[reader] = {
      stream, destination, LoadGuestU32(stream + 4u), count};
}

// One reader delivery: `delivered` bytes were just written to `destination`
// for the member offset `position`. Recognition happens on the first 0x24
// delivered bytes; afterwards the bytes are replaced by the re-encoded member's
// bytes at the same offsets.
void UiSceneInsertDeliver(uint32_t stream, uint32_t destination,
                          uint32_t delivered, uint32_t position) {
  if (stream == 0u || delivered == 0u || delivered > 0x10000u) {
    return;
  }
  if (!EnsureUiSceneInsertPayload()) {
    return;
  }
  const std::vector<uint8_t>& payload = g_ui_scene_insert_bytes;
  std::lock_guard lock(g_ui_scene_insert_mutex);
  UiSceneInsertStreamState& state = g_ui_scene_insert_streams[stream];
  // The allocator recycles the stream objects. A delivery at offset zero, or a
  // large backwards jump, starts a new stream lifetime; a one or two byte
  // unget stays inside the current one.
  constexpr uint32_t kUiSceneInsertRewindBytes = 0x1000u;
  if (state.maximum_position > 0u &&
      (position == 0u ||
       position + kUiSceneInsertRewindBytes < state.maximum_position)) {
    state = UiSceneInsertStreamState{};
  }
  state.deliveries += 1u;
  if (position + delivered > state.maximum_position) {
    state.maximum_position = position + delivered;
  }
  if (!state.decided && position < kUiSceneInsertDecisionBytes) {
    const uint32_t limit =
        std::min(delivered, kUiSceneInsertDecisionBytes - position);
    for (uint32_t index = 0; index < limit; ++index) {
      state.prefix[position + index] = LoadGuestU8(destination + index);
      state.seen[position + index] = true;
    }
  }
  if (!state.decided) {
    for (uint32_t index = 0; index < kUiSceneInsertDecisionBytes; ++index) {
      if (!state.seen[index]) {
        return;
      }
    }
    bool matches = payload.size() > kUiSceneInsertDecisionBytes;
    for (uint32_t index = 0; matches && index < kUiSceneInsertDecisionBytes;
         ++index) {
      matches = state.prefix[index] == payload[index];
    }
    state.decided = true;
    state.ours = matches;
    UiSceneInsertRecord("ui.experiment.scene_insert.stream",
                        {{"stream", Hex32(stream)},
                         {"decision", matches ? "pause_member" : "other"},
                         {"bytes_seen", Hex32(state.maximum_position)},
                         {"deliveries", Hex32(state.deliveries)},
                         {"prefix", UiSceneInsertPrefixText(state)},
                         {"words", UiSceneHexWords(stream, 12u)}});
  }
  if (!state.ours) {
    return;
  }
  const uint32_t buffer =
      g_ui_scene_insert_buffer.load(std::memory_order_acquire);
  const uint32_t buffer_size =
      g_ui_scene_insert_size.load(std::memory_order_acquire);
  if (buffer == 0u) {
    return;
  }
  const bool first = state.substituted == 0u;
  const std::string before =
      first ? UiSceneGuestBytes(destination, std::min(delivered, 16u))
            : std::string();
  for (uint32_t index = 0; index < delivered; ++index) {
    const uint32_t offset = position + index;
    if (offset >= buffer_size) {
      break;
    }
    StoreGuestU8(destination + index, LoadGuestU8(buffer + offset));
  }
  state.substituted += delivered;
  if (first) {
    UiSceneInsertRecord(
        "ui.experiment.scene_insert.substituted",
        {{"stream", Hex32(stream)},
         {"position", Hex32(position)},
         {"delivered", Hex32(delivered)},
         {"buffer", Hex32(buffer)},
         {"size", Hex32(buffer_size)},
         {"member_bytes", UiSceneGuestBytes(buffer + position,
                                            std::min(delivered, 16u))},
         {"delivered_before", before}});
  }
  if (position + delivered + 0x200u >= buffer_size && position != 0u) {
    if (g_ui_scene_insert_tail_events.fetch_add(1u, std::memory_order_relaxed) <
        kUiSceneInsertMaximumTailEvents) {
      UiSceneInsertRecord("ui.experiment.scene_insert.tail",
                          {{"stream", Hex32(stream)},
                           {"position", Hex32(position)},
                           {"delivered", Hex32(delivered)},
                           {"member_bytes", Hex32(buffer_size)},
                           {"count", Hex32(delivered)}});
    }
  }
}

// Bulk path of the reader slot-1 method: r28 is the destination buffer and r3
// the byte count the copy returned; r30 is the reader object.
void PinyonShiftUiSceneInsertReadResult(PPCRegister& r3, PPCRegister& r28,
                                        PPCRegister& r29, PPCRegister& r30) {
  if (UiExperimentModeValue() != UiExperimentMode::kSceneInsert) {
    return;
  }
  if (!PinyonShiftGuestRangeReadable(r30.u32 + 4u, 4u)) {
    return;
  }
  const uint32_t stream = LoadGuestU32(r30.u32 + 4u);
  if (stream == 0u || !PinyonShiftGuestRangeReadable(stream, 8u)) {
    return;
  }
  UiSceneInsertReadRequest request;
  {
    std::lock_guard lock(g_ui_scene_insert_mutex);
    const auto found = g_ui_scene_insert_requests.find(r30.u32);
    if (found != g_ui_scene_insert_requests.end()) {
      request = found->second;
    }
  }
  if (request.stream == stream && request.destination == r28.u32 &&
      UiSceneInsertStreamIsOurs(stream)) {
    const uint32_t size =
        g_ui_scene_insert_size.load(std::memory_order_acquire);
    const uint32_t delivered =
        request.position < size
            ? std::min(request.count, size - request.position)
            : 0u;
    if (delivered != 0u) {
      UiSceneInsertDeliver(stream, r28.u32, delivered, request.position);
    }
    StoreGuestU32(stream + 4u, request.position + delivered);
    r3.u64 = delivered;
    r29.u64 = delivered;
    return;
  }
  const uint32_t position_after = LoadGuestU32(stream + 4u);
  if (r3.u32 != 0u && position_after >= r3.u32) {
    UiSceneInsertDeliver(stream, r28.u32, r3.u32, position_after - r3.u32);
  }
}

// Byte-at-a-time path of the reader slot-1 method: one byte was just copied to
// r28 + r31; r30 is the reader object.
void PinyonShiftUiSceneInsertReadStep(PPCRegister& r3, PPCRegister& r28,
                                      PPCRegister& r30, PPCRegister& r31) {
  if (UiExperimentModeValue() != UiExperimentMode::kSceneInsert) {
    return;
  }
  if (!PinyonShiftGuestRangeReadable(r30.u32 + 4u, 4u)) {
    return;
  }
  const uint32_t stream = LoadGuestU32(r30.u32 + 4u);
  if (stream == 0u || !PinyonShiftGuestRangeReadable(stream, 8u)) {
    return;
  }
  const uint32_t position_after = LoadGuestU32(stream + 4u);
  if (UiSceneInsertStreamIsOurs(stream)) {
    const uint32_t position =
        r3.u32 != 0u && position_after > 0u ? position_after - 1u
                                           : position_after;
    const uint32_t size =
        g_ui_scene_insert_size.load(std::memory_order_acquire);
    const uint32_t delivered = position < size ? 1u : 0u;
    if (delivered != 0u) {
      UiSceneInsertDeliver(stream, r28.u32 + r31.u32, 1u, position);
    }
    StoreGuestU32(stream + 4u, position + delivered);
    r3.u64 = delivered;
    return;
  }
  if (r3.u32 != 0u && position_after > 0u) {
    UiSceneInsertDeliver(stream, r28.u32 + r31.u32, 1u,
                         position_after - 1u);
  }
}

// The identity-table loader reads each string body through its stream's direct
// bulk helper rather than the virtual reader path above. Intercept that return
// as well so inserted bytes and their four-byte lengths come from one payload.
void UiSceneInsertDirectReadResult(PPCRegister& r3, uint32_t owner,
                                   uint32_t destination,
                                   uint32_t requested) {
  if (UiExperimentModeValue() != UiExperimentMode::kSceneInsert ||
      !PinyonShiftGuestRangeReadable(owner + 12u, 4u)) {
    return;
  }
  const uint32_t reader = LoadGuestU32(owner + 12u);
  if (reader == 0u || !PinyonShiftGuestRangeReadable(reader + 4u, 4u)) {
    return;
  }
  const uint32_t stream = LoadGuestU32(reader + 4u);
  if (stream == 0u || !PinyonShiftGuestRangeReadable(stream + 4u, 4u)) {
    return;
  }
  const uint32_t position_after = LoadGuestU32(stream + 4u);
  if (position_after < r3.u32) {
    return;
  }
  const uint32_t position = position_after - r3.u32;
  if (UiSceneInsertStreamIsOurs(stream) && requested != 0u) {
    const uint32_t size =
        g_ui_scene_insert_size.load(std::memory_order_acquire);
    const uint32_t delivered =
        position < size ? std::min(requested, size - position) : 0u;
    if (delivered != 0u) {
      UiSceneInsertDeliver(stream, destination, delivered, position);
    }
    StoreGuestU32(stream + 4u, position + delivered);
    r3.u64 = delivered;
  } else if (r3.u32 != 0u) {
    UiSceneInsertDeliver(stream, destination, r3.u32, position);
  }
}

// Runs at the entry of the item deserializer sub_82F26560 with r3 = section:
// the loop bound is *(section+16) + *(section+20). The re-encoded member's
// header supplies the extra item count, so this repairs the field only when the
// header parse did not, and records which case held.
void PinyonShiftUiSceneInsertCount(PPCRegister& r3) {
  if (UiExperimentModeValue() != UiExperimentMode::kSceneInsert) {
    return;
  }
  const uint32_t buffer =
      g_ui_scene_insert_buffer.load(std::memory_order_acquire);
  if (buffer == 0u || !PinyonShiftGuestRangeReadable(r3.u32 + 20u, 4u)) {
    return;
  }
  const uint32_t reader =
      PinyonShiftGuestRangeReadable(r3.u32 + 12u, 4u) ? LoadGuestU32(r3.u32 + 12u)
                                                     : 0u;
  if (reader == 0u || !PinyonShiftGuestRangeReadable(reader + 4u, 4u) ||
      LoadGuestU32(reader + 4u) == 0u) {
    return;
  }
  const uint32_t stream = LoadGuestU32(reader + 4u);
  if (!UiSceneInsertStreamIsOurs(stream)) {
    return;
  }
  g_ui_scene_insert_item_count.store(0u, std::memory_order_relaxed);
  const uint32_t expected =
      g_ui_scene_insert_expected_items.load(std::memory_order_relaxed);
  const uint32_t elements = LoadGuestU32(r3.u32 + 16u);
  const uint32_t wrappers = LoadGuestU32(r3.u32 + 20u);
  const uint32_t total = elements + wrappers;
  if (expected == 0u || total == expected) {
    UiSceneInsertRecord("ui.experiment.scene_insert.count",
                        {{"state", "member"},
                         {"section", Hex32(r3.u32)},
                         {"elements", Hex32(elements)},
                         {"wrappers", Hex32(wrappers)},
                         {"expected", Hex32(expected)}});
    return;
  }
  const int32_t delta = static_cast<int32_t>(expected) - static_cast<int32_t>(total);
  if (delta < 0 || elements + static_cast<uint32_t>(delta) < elements) {
    UiSceneInsertRecord("ui.experiment.scene_insert.count",
                        {{"state", "unrepairable"},
                         {"elements", Hex32(elements)},
                         {"wrappers", Hex32(wrappers)},
                         {"expected", Hex32(expected)}});
    return;
  }
  StoreGuestU32(r3.u32 + 16u, elements + static_cast<uint32_t>(delta));
  UiSceneInsertRecord("ui.experiment.scene_insert.count",
                      {{"state", "repaired"},
                       {"section", Hex32(r3.u32)},
                       {"elements_before", Hex32(elements)},
                       {"wrappers_before", Hex32(wrappers)},
                       {"elements_after", Hex32(elements + static_cast<uint32_t>(delta))},
                       {"expected", Hex32(expected)}});
}

}  // namespace

void PinyonShiftUiSceneInsertIdentityReadResult(PPCRegister& r1,
                                                PPCRegister& r3,
                                                PPCRegister& r30,
                                                PPCRegister& r31) {
  UiSceneInsertDirectReadResult(r3, r30.u32, r31.u32,
                                UiSceneWordOrZero(r1.u32 + 80u));
}

void PinyonShiftUiSceneInsertItemReadResult(PPCRegister& r1, PPCRegister& r3,
                                            PPCRegister& r31) {
  UiSceneInsertDirectReadResult(r3, r31.u32, r1.u32 + 128u, 16u);
}

// Entry of the scene item deserializer sub_82F26560 (0x82F26560): r3 is the
// section context, r4 the element the document belongs to and lr the caller.
void PinyonShiftTraceUiSceneDeserializerEntry(PPCRegister& r3, PPCRegister& r4,
                                              uint64_t& lr) {
  PinyonShiftUiSceneInsertCount(r3);
  if (UiExperimentModeValue() != UiExperimentMode::kSceneProbe) {
    return;
  }
  const uint32_t frame = pinyon_shift::fh1_render_test::CurrentFrame();
  const uint32_t section = r3.u32;
  const uint32_t reader = UiSceneWordOrZero(section + 12u);
  const uint32_t source = reader != 0u ? UiSceneWordOrZero(reader + 4u) : 0u;
  // reader+4 is a sequential cursor object: +0 holds the buffer base and +4 the
  // number of bytes already consumed, so the section starts at base + consumed.
  const uint32_t buffer_base = source != 0u ? UiSceneWordOrZero(source) : 0u;
  const uint32_t consumed = source != 0u ? UiSceneWordOrZero(source + 4u) : 0u;
  const uint32_t cursor = buffer_base != 0u ? buffer_base + consumed : 0u;
  const uint32_t remaining = consumed;
  UiSceneScanPayloadOnce(section);
  g_ui_scene_buffer_base = buffer_base;
  UiSceneStreamScanOnce(cursor);
  const uint32_t index =
      g_ui_scene_entry_count.fetch_add(1, std::memory_order_relaxed);
  if (index >= kUiSceneProbeEventLimit) {
    return;
  }
  pinyon_shift::diagnostics::RecordEvent(
      "ui.scene.deserializer",
      {{"address", "82F26560"},
       {"frame", std::to_string(frame)},
       {"index", std::to_string(index)},
       {"caller", Hex32(static_cast<uint32_t>(lr))},
       {"section", Hex32(section)},
       {"element", Hex32(r4.u32)},
       {"section_words", UiSceneHexWords(section, 8u)},
       {"section_20", Hex32(UiSceneWordOrZero(section + 20u))},
       {"section_92_pool", Hex32(UiSceneWordOrZero(section + 92u))},
       {"section_124_data", Hex32(UiSceneWordOrZero(section + 124u))},
       {"section_132_size", Hex32(UiSceneWordOrZero(section + 132u))},
       {"reader", Hex32(reader)},
       {"reader_words", UiSceneHexWords(reader, 4u)},
       {"source", Hex32(source)},
       {"source_words", UiSceneHexWords(source, 12u)},
       {"cursor", Hex32(cursor)},
       {"remaining", Hex32(remaining)},
       {"declared_at_cursor",
        cursor != 0u ? Hex32(UiSceneWordOrZero(cursor)) : "-"},
       {"cursor_head", UiSceneGuestBytes(cursor, 48u)}});
}

// Continuation of sub_82F26560 after the section's declared byte length has
// been read into the frame at r1+116. r3 is the read return.
void PinyonShiftTraceUiSceneItemLength(PPCRegister& r1, PPCRegister& r3,
                                       PPCRegister& r31) {
  if (UiExperimentModeValue() == UiExperimentMode::kSceneInsert) {
    const uint32_t section = r31.u32;
    const uint32_t reader =
        PinyonShiftGuestRangeReadable(section + 12u, 4u)
            ? LoadGuestU32(section + 12u)
            : 0u;
    const uint32_t stream =
        reader != 0u && PinyonShiftGuestRangeReadable(reader + 4u, 4u)
            ? LoadGuestU32(reader + 4u)
            : 0u;
    if (stream != 0u && UiSceneInsertStreamIsOurs(stream)) {
      const uint32_t declared = LoadGuestU32(r1.u32 + 116u);
      const uint32_t expected =
          g_ui_scene_insert_expected_declared.load(std::memory_order_relaxed);
      UiSceneInsertRecord(
          "ui.experiment.scene_insert.declared",
          {{"state", expected == 0u || declared == expected ? "reencoded"
                                                            : "mismatch"},
           {"declared", Hex32(declared)},
           {"expected", Hex32(expected)},
           {"elements", Hex32(LoadGuestU32(section + 16u))},
           {"wrappers", Hex32(LoadGuestU32(section + 20u))}});
    }
  }
  if (UiExperimentModeValue() != UiExperimentMode::kSceneProbe) {
    return;
  }
  const uint32_t index =
      g_ui_scene_length_count.fetch_add(1, std::memory_order_relaxed);
  if (index >= kUiSceneProbeEventLimit) {
    return;
  }
  const uint32_t section = r31.u32;
  const uint32_t reader = UiSceneWordOrZero(section + 12u);
  const uint32_t source = reader != 0u ? UiSceneWordOrZero(reader + 4u) : 0u;
  pinyon_shift::diagnostics::RecordEvent(
      "ui.scene.item_length",
      {{"address", "82F265D4"},
       {"frame",
        std::to_string(pinyon_shift::fh1_render_test::CurrentFrame())},
       {"index", std::to_string(index)},
       {"declared_bytes", Hex32(UiSceneWordOrZero(r1.u32 + 116u))},
       {"read_return", Hex32(r3.u32)},
       {"section_16", Hex32(UiSceneWordOrZero(section + 16u))},
       {"section_20", Hex32(UiSceneWordOrZero(section + 20u))},
       {"source", Hex32(source)},
       {"source_words", UiSceneHexWords(source, 16u)},
       {"declared_bytes_raw", UiSceneGuestBytes(r1.u32 + 116u, 32u)}});
}

// 0x82F267C0 is where both record allocator branches of sub_82F26560 converge,
// so the stack slots still hold the fields read for this item: F1 at r1+96,
// F2 at r1+88, F3 at r1+92, the flag bytes at r1+80 (B2) and r1+81 (B1) and the
// wrapper's extra word at r1+112. r3 is the allocated record.
void PinyonShiftTraceUiSceneItemFields(PPCRegister& r1, PPCRegister& r3,
                                       PPCRegister& r31) {
  if (UiExperimentModeValue() == UiExperimentMode::kSceneInsert) {
    const uint32_t index =
        g_ui_scene_insert_item_count.fetch_add(1u, std::memory_order_relaxed);
    const uint32_t name = UiSceneWordOrZero(r1.u32 + 96u);
    if (name == 0x223C2AFBu) {
      g_ui_scene_insert_capture_remaining.store(39u, std::memory_order_relaxed);
      g_ui_scene_tree_walk_trace_count.store(0u, std::memory_order_relaxed);
    }
    uint32_t remaining =
        g_ui_scene_insert_capture_remaining.load(std::memory_order_relaxed);
    if (remaining != 0u) {
      g_ui_scene_insert_capture_remaining.store(remaining - 1u,
                                                std::memory_order_relaxed);
      UiSceneInsertRecord(
          "ui.experiment.scene_insert.item",
          {{"index", Hex32(index)},
           {"name", Hex32(name)},
           {"parent", Hex32(UiSceneWordOrZero(r1.u32 + 88u))},
           {"value", Hex32(UiSceneWordOrZero(r1.u32 + 92u))},
           {"kind", Hex32(PinyonShiftGuestRangeReadable(r1.u32 + 81u, 1u)
                              ? LoadGuestU8(r1.u32 + 81u)
                              : 0u)},
           {"flags", Hex32(PinyonShiftGuestRangeReadable(r1.u32 + 80u, 1u)
                               ? LoadGuestU8(r1.u32 + 80u)
                               : 0u)},
           {"record", Hex32(r3.u32)}});
    }
  }
  if (UiExperimentModeValue() != UiExperimentMode::kSceneProbe) {
    return;
  }
  const uint32_t frame = pinyon_shift::fh1_render_test::CurrentFrame();
  const uint32_t index =
      g_ui_scene_item_count.fetch_add(1, std::memory_order_relaxed);
  if (index >= kUiSceneProbeEventLimit) {
    return;
  }
  const uint32_t record = r3.u32;
  const uint32_t section = r31.u32;
  const uint32_t reader = UiSceneWordOrZero(section + 12u);
  const uint32_t source = reader != 0u ? UiSceneWordOrZero(reader + 4u) : 0u;
  const uint32_t b2 = PinyonShiftGuestRangeReadable(r1.u32 + 80u, 1u)
                          ? LoadGuestU8(r1.u32 + 80u)
                          : 0u;
  pinyon_shift::diagnostics::RecordEvent(
      "ui.scene.item_fields",
      {{"address", "82F267C0"},
       {"frame", std::to_string(frame)},
       {"index", std::to_string(index)},
       {"f1", Hex32(UiSceneWordOrZero(r1.u32 + 96u))},
       {"f2", Hex32(UiSceneWordOrZero(r1.u32 + 88u))},
       {"f3", Hex32(UiSceneWordOrZero(r1.u32 + 92u))},
       {"b1", Hex32(PinyonShiftGuestRangeReadable(r1.u32 + 81u, 1u)
                        ? LoadGuestU8(r1.u32 + 81u)
                        : 0u)},
       {"b2", Hex32(b2)},
       {"extra", Hex32(UiSceneWordOrZero(r1.u32 + 112u))},
       {"branch", (b2 & 0x04u) != 0u ? "wrapper" : "element"},
       {"record", Hex32(record)},
       {"record_0", Hex32(UiSceneWordOrZero(record))},
       {"record_4", Hex32(UiSceneWordOrZero(record + 4u))},
       {"record_kind", Hex32(PinyonShiftGuestRangeReadable(record + 30u, 1u)
                                 ? LoadGuestU8(record + 30u)
                                 : 0u)},
       {"source", Hex32(source)},
       {"source_words", UiSceneHexWords(source, 12u)}});
}

// Byte-at-a-time continuation of the same reader method (0x82F255C0), wired by
// its own hook so the loader-boundary scene insertion also covers this path.
void PinyonShiftTraceUiSceneReadStep(PPCRegister& r3, PPCRegister& r28,
                                     PPCRegister& r30, PPCRegister& r31) {
  PinyonShiftUiSceneInsertReadStep(r3, r28, r30, r31);
}

// Reader slot-1 method sub_82F25568 (0x82F25568) hands its per-read arguments
// to the copy helper, so this records where each item byte comes from.
void PinyonShiftTraceUiSceneStreamRead(PPCRegister& r3, PPCRegister& r4,
                                       PPCRegister& r5) {
  if (UiExperimentModeValue() == UiExperimentMode::kSceneInsert) {
    UiSceneInsertCaptureRead(r3.u32, r4.u32, r5.u32);
  }
  if (UiExperimentModeValue() != UiExperimentMode::kSceneProbe) {
    return;
  }
  const uint32_t frame = pinyon_shift::fh1_render_test::CurrentFrame();
  const uint32_t index =
      g_ui_scene_read_count.fetch_add(1, std::memory_order_relaxed);
  if (index >= kUiSceneProbeEventLimit) {
    return;
  }
  const uint32_t reader = r3.u32;
  const uint32_t source = UiSceneWordOrZero(reader + 4u);
  pinyon_shift::diagnostics::RecordEvent(
      "ui.scene.stream_read",
      {{"address", "82F25568"},
       {"frame", std::to_string(frame)},
       {"index", std::to_string(index)},
       {"reader", Hex32(reader)},
       {"destination", Hex32(r4.u32)},
       {"count", Hex32(r5.u32)},
       {"source", Hex32(source)},
       {"source_words", UiSceneHexWords(source, 12u)},
       {"image", UiSceneGuestBytes(source, 32u)}});
}


// Continuation of the reader slot-1 method sub_82F25568 after the bulk copy
// (0x82F255EC): r3 is the byte count the copy returned, r28 the destination
// buffer the reader validated at entry and r30 the reader object. Recording the
// delivered bytes next to the source cursor and its remaining count is what
// shows whether the stream is a plain memory copy or a decoding stream.
void PinyonShiftTraceUiSceneReadResult(PPCRegister& r3, PPCRegister& r28,
                                       PPCRegister& r29, PPCRegister& r30) {
  PinyonShiftUiSceneInsertReadResult(r3, r28, r29, r30);
  if (UiExperimentModeValue() != UiExperimentMode::kSceneProbe) {
    return;
  }
  const uint32_t index =
      g_ui_scene_read_result_count.fetch_add(1, std::memory_order_relaxed);
  if (index >= 48u) {
    return;
  }
  const uint32_t reader = r30.u32;
  const uint32_t source = UiSceneWordOrZero(reader + 4u);
  pinyon_shift::diagnostics::RecordEvent(
      "ui.scene.read_result",
      {{"address", "82F255EC"},
       {"frame",
        std::to_string(pinyon_shift::fh1_render_test::CurrentFrame())},
       {"index", std::to_string(index)},
       {"read", Hex32(r3.u32)},
       {"destination", Hex32(r28.u32)},
       {"delivered", UiSceneGuestBytes(r28.u32, 16u)},
       {"source", Hex32(source)},
       {"source_cursor", Hex32(UiSceneWordOrZero(source))},
       {"source_remaining", Hex32(UiSceneWordOrZero(source + 4u))},
       {"source_words", UiSceneHexWords(source, 12u)}});
}

void PinyonShiftValidateGeometryOutput(PPCRegister& r4, PPCRegister& r5,
                                       PPCRegister& r6) {
  // Every caller-owned result slot is 544 bytes. sub_82D3CD48's variable
  // vector writes fit that slot only while (count + 15) * 16 <= 544, so 19 is
  // the largest representable count. Redirecting an oversized result to a
  // shared discard buffer avoids the immediate write AV but leaves the caller
  // consuming a missing result and permits its outer loop to continue through
  // corrupted entries. Normalize the invalid serialized count instead; the
  // independent lookup hook still repairs an unreadable three-byte pointer.
  constexpr uint32_t kMaximumIndexCount = 19u;
  const uint32_t count = LoadGuestU8(r5.u32 + 4u);
  if (count <= kMaximumIndexCount) {
    return;
  }

  StoreGuestU8(r5.u32 + 4u, 0u);
  pinyon_shift::diagnostics::RecordEvent(
      "geometry.entry.oversized_count_repair",
      {{"address", "82D3CD58"},
       {"consumer", "82D3CD58"},
       {"owner", Hex32(r4.u32)},
       {"entry", Hex32(r5.u32)},
       {"count", Hex32(count)},
       {"maximum", Hex32(kMaximumIndexCount)},
       {"output", Hex32(r6.u32)}});
}

static uint32_t PinyonShiftGeometryZeroIndexBuffer() {
  uint32_t buffer =
      g_geometry_zero_index_buffer.load(std::memory_order_acquire);
  if (buffer != 0) {
    return buffer;
  }

  std::lock_guard lock(g_geometry_zero_index_buffer_mutex);
  buffer = g_geometry_zero_index_buffer.load(std::memory_order_relaxed);
  if (buffer != 0) {
    return buffer;
  }

  constexpr uint32_t kMaximumIndexCount = 256u;
  auto* memory = rex::system::kernel_state()->memory();
  buffer = memory->SystemHeapAlloc(kMaximumIndexCount, 16u);
  for (uint32_t index = 0; index < kMaximumIndexCount; ++index) {
    StoreGuestU8(buffer + index, 0u);
  }
  g_geometry_zero_index_buffer.store(buffer, std::memory_order_release);
  return buffer;
}

void PinyonShiftValidateGeometryLookup(PPCRegister& r4, PPCRegister& r5,
                                       PPCRegister& r6, PPCRegister& r11) {
  // sub_82D3CD48 consumes at least three byte indices from the pointer at
  // entry+0 before consulting the count at entry+4. Existing-save replay has
  // exposed multiple stale relocated pointers here, including the exact-build
  // 0x6CD00200 read AV. Preserve valid triplets. For an unreadable triplet,
  // redirect the entry to a process-lifetime zero-index buffer large enough
  // for the full uint8 count. The function reloads entry+0 in its later
  // variable-length loop, so repairing only r11 is insufficient. Preserve the
  // original count: changing it alters the caller's output sizing decisions.
  constexpr uint32_t kTripletSize = 3u;
  if (PinyonShiftGuestRangeReadable(r11.u32, kTripletSize)) {
    return;
  }

  const uint32_t original_pointer = r11.u32;
  const uint32_t original_count = LoadGuestU8(r5.u32 + 4u);
  const uint32_t fallback = PinyonShiftGeometryZeroIndexBuffer();
  StoreGuestU32(r5.u32, fallback);
  r11.u64 = fallback;

  pinyon_shift::diagnostics::RecordEvent(
      "geometry.lookup.unreadable_triplet_repair",
      {{"address", "82D3CD80"},
       {"consumer", "82D3CD80"},
       {"owner", Hex32(r4.u32)},
       {"entry", Hex32(r5.u32)},
       {"output", Hex32(r6.u32)},
       {"count", Hex32(original_count)},
       {"pointer", Hex32(original_pointer)},
       {"fallback", Hex32(fallback)}});
}

static bool PinyonShiftGeometryIndexListReadable(uint32_t list,
                                                 uint32_t count) {
  return PinyonShiftGuestRangeReadable(list, count);
}

void PinyonShiftValidateGeometryIndexList(PPCRegister& r8, PPCRegister& r29,
                                          PPCRegister& r31) {
  // sub_82D3DA48 relocates the geometry blob's entry pointers in place. Each
  // entry contains a byte count at +9 and the corresponding byte-index list at
  // +4. Continuation captures have observed both a null list and an
  // uncommitted list while the count remained nonzero. Treat only an unreadable
  // complete list as empty, preserving all valid geometry data and recording
  // the repaired serialized-blob invariant.
  const uint32_t count = r8.u32 & 0xFFu;
  if (count == 0) {
    return;
  }

  const uint32_t list = LoadGuestU32(r29.u32 + 4u);
  // sub_82D3DB00 reserves eight 544-byte result slots in its 4,544-byte
  // frame. A larger serialized count walks r6 beyond that array and also
  // indexes unrelated lookup-table entries. Treat the whole invalid list as
  // empty rather than preserving an arbitrary prefix of corrupted geometry.
  constexpr uint32_t kMaximumResultCount = 8u;
  if (count > kMaximumResultCount) {
    // Persist the repair in the transient relocated entry. Register-only
    // suppression leaves the invalid pair live and caused the same entry to be
    // repaired repeatedly during the long-play soak test.
    StoreGuestU8(r29.u32 + 9u, 0u);
    r8.u64 = 0;
    pinyon_shift::diagnostics::RecordEvent(
        "geometry.index.oversized_list_repair",
        {{"address", "82D3DB54"},
         {"consumer", "82D3DB6C"},
         {"owner", Hex32(r31.u32)},
         {"entry", Hex32(r29.u32)},
         {"count_address", Hex32(r29.u32 + 9u)},
         {"count", Hex32(count)},
         {"maximum", Hex32(kMaximumResultCount)},
         {"list", Hex32(list)},
         {"repair", "entry_count_zeroed"}});
    return;
  }

  if (PinyonShiftGeometryIndexListReadable(list, count)) {
    return;
  }

  StoreGuestU8(r29.u32 + 9u, 0u);
  r8.u64 = 0;
  pinyon_shift::diagnostics::RecordEvent(
      "geometry.index.unreadable_list_repair",
      {{"address", "82D3DB54"},
       {"consumer", "82D3DB6C"},
        {"owner", Hex32(r31.u32)},
        {"entry", Hex32(r29.u32)},
        {"count_address", Hex32(r29.u32 + 9u)},
        {"count", Hex32(count)},
        {"list", Hex32(list)},
        {"repair", "entry_count_zeroed"}});
}

void PinyonShiftValidateGeometrySecondaryIndexList(PPCRegister& r6,
                                                   PPCRegister& r29,
                                                   PPCRegister& r31) {
  // The same 12-byte entry contains a second byte-index list at +0 with its
  // count at +8. The first field replay that exercised the primary-list repair
  // immediately reached this sibling loop with the same invalid serialized
  // invariant. Validate it independently so repairing +4/+9 cannot fall
  // through to an equivalent read at 0x82D3DC1C.
  const uint32_t count = r6.u32 & 0xFFu;
  if (count == 0) {
    return;
  }

  const uint32_t list = LoadGuestU32(r29.u32);
  if (PinyonShiftGeometryIndexListReadable(list, count)) {
    return;
  }

  // Make the repaired invariant durable for every consumer of this relocated
  // entry, rather than suppressing only the current loop iteration.
  StoreGuestU8(r29.u32 + 8u, 0u);
  r6.u64 = 0;
  pinyon_shift::diagnostics::RecordEvent(
      "geometry.index.unreadable_secondary_list_repair",
      {{"address", "82D3DBF4"},
       {"consumer", "82D3DC1C"},
        {"owner", Hex32(r31.u32)},
        {"entry", Hex32(r29.u32)},
        {"count_address", Hex32(r29.u32 + 8u)},
        {"count", Hex32(count)},
        {"list", Hex32(list)},
        {"repair", "entry_count_zeroed"}});
}

void PinyonShiftTraceGeometryIndex(PPCRegister& r9, PPCRegister& r11,
                                   PPCRegister& r29, PPCRegister& r30,
                                   PPCRegister& r31) {
  // Runs immediately before the byte read at 0x82D3DB6C. Runs 103 and the
  // generation-contract regression both reached this instruction with an
  // uncommitted 0x25xxxxxx list pointer. Keep the hook observational: the
  // first-chance AV handler remains responsible for preserving the fault.
  if ((r11.u32 & 0xF0000000u) >= 0x40000000u) {
    return;
  }
  pinyon_shift::diagnostics::RecordEvent(
      "geometry.index.suspicious",
      {{"address", "82D3DB6C"},
       {"owner", Hex32(r31.u32)},
       {"entry", Hex32(r29.u32)},
       {"index", Hex32(r30.u32)},
       {"list", Hex32(r11.u32)},
       {"lookup_table", Hex32(r9.u32)}});
}

void PinyonShiftTraceRetainVtable(PPCRegister& r4, PPCRegister& r11,
                                  PPCRegister& r30, PPCRegister& r31) {
  // sub_826E1B10 is a shared/intrusive pointer assignment helper. At
  // 0x826E1B3C it is about to load the AddRef target from vtable+8. PID 25180
  // reached this instruction with a readable object whose vtable was 0x487C,
  // causing the authoritative read AV at guest 0x4884. Keep this hook
  // observational and narrowly log only pointers outside the title image.
  if (!FrameTelemetryEnabled() ||
      (r11.u32 >= 0x82000000u && r11.u32 < 0x84000000u)) {
    return;
  }
  pinyon_shift::diagnostics::RecordEvent(
      "object.retain.invalid_vtable",
      {{"address", "826E1B3C"},
       {"destination", Hex32(r30.u32)},
       {"source_slot", Hex32(r4.u32)},
       {"object", Hex32(r31.u32)},
       {"vtable", Hex32(r11.u32)}});
}

void PinyonShiftTraceRetainSourceSlot(PPCRegister& r3, PPCRegister& r4,
                                      PPCRegister& r26, PPCRegister& r27,
                                      PPCRegister& r29, PPCRegister& r31) {
  // PID 31612 reached sub_826E1B10 from this call site with source slot
  // 0x43D29E00. The owner inferred from its destination is normal in clean
  // replays, so retain only this direct source-slot correlation for a future
  // failing run. This executes immediately before the helper call.
  if (!FrameTelemetryEnabled() || r4.u32 != 0x43D29E00u) {
    return;
  }
  pinyon_shift::diagnostics::RecordEvent(
      "object.retain.source_slot",
      {{"address", "82C6DFA8"},
       {"destination", Hex32(r3.u32)},
       {"source_slot", Hex32(r4.u32)},
       {"state", Hex32(r26.u32)},
       {"table_base", Hex32(r27.u32)},
       {"slot_index", Hex32(r29.u32)},
       {"owner", Hex32(r31.u32)}});
}
