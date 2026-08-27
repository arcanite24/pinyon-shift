#include <algorithm>
#include <atomic>
#include <bit>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <mutex>
#include <string>

#include <fmt/format.h>
#include <rex/cvar.h>
#include <rex/memory.h>
#include <rex/ppc/context.h>
#include <rex/perf/counter.h>
#include <rex/system/kernel_state.h>
#include <rex/system/xmemory.h>

#include "pinyon_shift_diagnostics.h"

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

void PinyonShiftTraceFrameTelemetry(PPCRegister& r28, PPCRegister& r31) {
  PROFILE_SIMULATION_TICK();
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
