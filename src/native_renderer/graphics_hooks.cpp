#include "native_renderer/graphics_hooks.h"

#include "native_renderer/d3d_census.h"
#include "native_renderer/d3d_draw.h"

#include "fh1_guest_address.h"
#include "pinyon_shift_runtime_hooks.h"

#include <atomic>
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <mutex>
#include <vector>

#include <rex/cvar.h>
#include <rex/logging/macros.h>
#include <rex/perf/counter.h>
#include <rex/ppc/context.h>
#include <rex/runtime.h>
#include <rex/system/gpu_write_signal.h>
#include <rex/system/interfaces/graphics.h>
#include <rex/system/kernel_state.h>
#include <rex/system/xmemory.h>
#include <rex/thread/mutex.h>
#include <rex/types.h>

REXCVAR_DEFINE_BOOL(pinyon_shift_fh1_gpu_corpus, false, "Pinyon Shift",
                    "Sample native GPU pass and texture-request timings every 60 frames "
                    "(read by the D3D12 command processor)")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);
REXCVAR_DEFINE_DOUBLE(pinyon_shift_fh1_env_map_rate, REX_PLATFORM_ANDROID ? 0.25 : 1.0,
                      "Pinyon Shift",
                      "Scales how often the dynamic cubemap that cars reflect is redrawn "
                      "(the render scenarios' EnvMapFrequencyScale; 1: the game's rate, 0: "
                      "never, reflections go dark). 0.25 saves about 2.3 ms a frame on the "
                      "Odin 2 Portal with reflections that look the same")
    .range(0.0, 1.0)
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_BOOL(pinyon_shift_fh1_shadows, !REX_PLATFORM_ANDROID, "Pinyon Shift",
                    "Draw the sun's shadows. Off sets the render scenarios' "
                    "SkipShadowMapUnlessCockpit (no shadow maps, depth pre-pass or shadow "
                    "mask: about 6.4 ms a frame on the Odin 2 Portal) and keeps the "
                    "screen's shadow mask lit; needs the Vulkan FH1 executor. Off applies only "
                    "while the cars' lights are off (08:02 to 18:50), since it also "
                    "removes the headlights' light on the road")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_BOOL(pinyon_shift_reuse_gamma_ramp, true, "Pinyon Shift",
                    "Reuse the title's gamma ramp when it is rebuilt from the same settings. "
                    "A finished gamma transition never ends, so the title rebuilds the same "
                    "ramp (up to 256 software pow calls) every frame after a fade, which "
                    "showed as hitching after races and at boot")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_BOOL(pinyon_shift_skip_unchanged_device_gamma, true, "Pinyon Shift",
                    "Skip D3D's SetPWLGamma when the ramp and the device's copy are what its "
                    "last call left: it converts and compares 1,536 bytes every frame, about "
                    "30 % of the render thread, to find nothing changed")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_BOOL(pinyon_shift_block_on_gpu_fence, true, "Pinyon Shift",
                    "Block the title's GPU fence polling until the command processor next "
                    "writes guest memory (bounded to 1 ms) instead of spinning")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_UINT32(pinyon_shift_gpu_fence_spin_us, 20, "Pinyon Shift",
                      "Microseconds a blocked GPU fence wait polls the fence word before "
                      "it sleeps until the command processor writes guest memory")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

namespace pinyon_shift::native_renderer {
namespace {

using Clock = std::chrono::steady_clock;

struct TitleEmitterSample {
  uint64_t frame;
  Clock::time_point begin;
};
thread_local std::vector<TitleEmitterSample> title_emitters;
thread_local uint64_t title_emitter_frame = 0;
thread_local uint64_t title_emitter_calls = 0;
thread_local uint64_t title_emitter_time_ns = 0;
thread_local uint64_t title_packet_count = 0;
thread_local int64_t title_first_packet_ns = 0;
thread_local int64_t title_last_packet_ns = 0;
// The gameplay render scenarios (every one sets EnvMapFrequencyScale), for
// the render settings that apply while the game runs: the reflection rate
// scales each scenario's EnvMapFrequencyScale from the value its XML set,
// and shadows off sets SkipShadowMapUnlessCockpit in each. Shadows go off
// only once the GPU backend has resolved the screen's shadow mask, so its
// texture is known and can be kept lit.
struct RenderScenario {
  uint32_t address;
  uint32_t env_control;
  float env_value;
  uint8_t skip_value;
  bool skip_set;
};
std::mutex render_scenarios_mutex;
std::vector<RenderScenario> render_scenarios;
float applied_env_rate = 1.0f;
bool shadows_skipped = false;
// Shadow mask resolves seen at the last frame and when the mask was last
// filled: the cockpit view still draws shadows (SkipShadowMapUnlessCockpit),
// and the other views must not keep its last mask.
uint32_t mask_resolves_seen = 0;
uint32_t mask_resolves_filled = UINT32_MAX;

// SkipShadowMapUnlessCockpit (id 35) is embedded in each scenario at +0x194;
// bit 35 of the bitset at +36 marks it set by the scenario.
constexpr uint32_t kSkipShadowOffset = 0x194, kSkipShadowVtable = FH1_ADDR(0x8223C6C4u);
constexpr uint32_t kSetBitsOffset = 40, kSkipShadowBit = 1u << 3;

uint8_t* SkipShadowControl(rex::memory::Memory* memory, uint32_t scenario) {
  auto* skip = memory->TranslateVirtual<uint8_t*>(scenario + kSkipShadowOffset);
  return rex::byte_swap(*reinterpret_cast<uint32_t*>(skip)) == kSkipShadowVtable ? skip
                                                                                  : nullptr;
}

void SetShadowsSkipped(rex::memory::Memory* memory, const RenderScenario& scenario,
                       bool skipped) {
  uint8_t* skip = SkipShadowControl(memory, scenario.address);
  if (!skip) return;
  skip[4] = skipped ? 1 : scenario.skip_value;
  auto* set_bits = memory->TranslateVirtual<uint32_t*>(scenario.address + kSetBitsOffset);
  uint32_t bits = rex::byte_swap(*set_bits) & ~kSkipShadowBit;
  if (skipped || scenario.skip_set) bits |= kSkipShadowBit;
  *set_bits = rex::byte_swap(bits);
}

void SetEnvMapRate(rex::memory::Memory* memory, const RenderScenario& scenario, float rate) {
  const float value = scenario.env_value * rate;
  uint32_t bits;
  std::memcpy(&bits, &value, sizeof(bits));
  memory->TranslateVirtual<uint32_t*>(scenario.env_control)[1] = rex::byte_swap(bits);
}

// SkipShadowMapUnlessCockpit also drops the headlights' projected pool on
// the road (#532), so shadows off only applies while the cars' lights are
// off: the track's SwitchOnLights curve is zero from 08:02 to 18:50.
bool CarLightsOn() {
  const double seconds = PinyonShiftGameSecondsOfDay();
  return seconds >= 0.0 && (seconds < 482.0 * 60.0 || seconds > 1130.0 * 60.0);
}

// Called with render_scenarios_mutex held.
void KeepShadowsOff(rex::memory::Memory* memory) {
  auto* graphics = rex::system::kernel_state()->emulator()->graphics_system();
  uint32_t mask_base, mask_length, mask_resolves;
  if (!graphics || !graphics->fh1_shadow_mask(&mask_base, &mask_length, &mask_resolves)) return;
  if (!shadows_skipped) {
    for (const RenderScenario& scenario : render_scenarios) {
      SetShadowsSkipped(memory, scenario, true);
    }
    shadows_skipped = true;
    REXLOG_INFO("Shadows off: {} render scenarios, shadow mask {:08X}+{:X}",
                render_scenarios.size(), mask_base, mask_length);
  }
  // Without the shadow passes the mask keeps what was last there: written
  // white (lit), and again whenever something else writes it. While the
  // game resolves the mask every frame (the cockpit view draws shadows) it
  // is left alone; the first frame without a resolve fills it again.
  const bool resolving = mask_resolves != mask_resolves_seen;
  mask_resolves_seen = mask_resolves;
  if (resolving) return;
  auto* mask = memory->TranslatePhysical<uint32_t*>(mask_base);
  // Lit geometry in a resolved mask is bytes 00 FF FF 00 (the same word
  // either endianness): the two shadow terms full, the other two channels
  // zero. All FF also sets those, and the car shaders of the garage's
  // thumbnail studio read them: panels blown out to cyan or pink (#700).
  constexpr uint32_t kLitMask = 0x00FFFF00u;
  if (mask_resolves == mask_resolves_filled && mask[0] == kLitMask &&
      mask[mask_length / 4 - 1] == kLitMask) {
    return;
  }
  mask_resolves_filled = mask_resolves;
  std::fill(mask, mask + mask_length / 4, kLitMask);
  memory->TriggerPhysicalMemoryCallbacks(rex::thread::global_critical_region::AcquireDirect(),
                                         0xA0000000u + mask_base, mask_length, true, false);
}

// Once a frame: brings the scenarios to the settings' current values.
void ApplyRenderSettings() {
  auto* memory = rex::system::kernel_state()->memory();
  std::lock_guard<std::mutex> lock(render_scenarios_mutex);
  const float rate = float(REXCVAR_GET(pinyon_shift_fh1_env_map_rate));
  if (rate != applied_env_rate) {
    for (const RenderScenario& scenario : render_scenarios) SetEnvMapRate(memory, scenario, rate);
    applied_env_rate = rate;
  }
  if (!REXCVAR_GET(pinyon_shift_fh1_shadows) && !CarLightsOn()) {
    KeepShadowsOff(memory);
  } else if (shadows_skipped) {
    for (const RenderScenario& scenario : render_scenarios) {
      SetShadowsSkipped(memory, scenario, false);
    }
    shadows_skipped = false;
    REXLOG_INFO("Shadows on");
  }
}

}  // namespace

}  // namespace pinyon_shift::native_renderer

using pinyon_shift::native_renderer::Clock;
using namespace pinyon_shift::native_renderer;

// FH1's sole VdSwap call is the source-frame boundary used by the real-frame
// presentation and performance gates. It intentionally changes no guest state.
void PinyonShiftObserveGraphicsFrame() {
  if (rex::perf::CriticalPathTraceEnabled() &&
      (title_emitter_calls || title_packet_count)) {
    rex::perf::TraceCriticalPath("title_emitter", int64_t(title_emitter_frame),
                                 int64_t(title_emitter_time_ns),
                                 int64_t(title_emitter_calls));
    rex::perf::TraceCriticalPath("pm4_publish", int64_t(title_emitter_frame),
                                 int64_t(title_packet_count), title_first_packet_ns,
                                 title_last_packet_ns);
  }
  ApplyRenderSettings();
  PinyonShiftNoteTitleSwap();
  PROFILE_SOURCE_FRAME();
  title_emitter_frame = uint64_t(rex::perf::GetTotalCounter(
      rex::perf::CounterId::kSourceFrameCount));
  title_emitter_calls = title_emitter_time_ns = title_packet_count = 0;
  title_first_packet_ns = title_last_packet_ns = 0;
  rex::perf::TraceCriticalPath("source_frame", int64_t(title_emitter_frame));
  D3dCensusFrame();
  D3dDrawFrame();
}

void PinyonShiftObserveTitleDrawEmitterBegin() {
  if (rex::perf::CriticalPathTraceEnabled()) {
    title_emitters.push_back({uint64_t(rex::perf::GetTotalCounter(
                                  rex::perf::CounterId::kSourceFrameCount)),
                              Clock::now()});
  }
}

// The same hook with the registers the D3D census (DL-0.1) reads: this is its
// draw entry 5. The registerless form above stays for builds whose generated
// code predates the census.
void PinyonShiftObserveTitleDrawEmitterBegin(PPCRegister& r1, PPCRegister& r3, uint64_t& lr) {
  PinyonShiftObserveTitleDrawEmitterBegin();
  D3dCensusDrawEntry(5, r1.u32, r3.u32, uint32_t(lr));
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
      std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - sample.begin)
          .count());
}

void PinyonShiftObserveTitleDrawPacketPublish(PPCRegister&, PPCRegister&, PPCRegister&) {
  if (!rex::perf::CriticalPathTraceEnabled()) {
    return;
  }
  const int64_t now_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
                             Clock::now().time_since_epoch())
                             .count();
  if (!title_packet_count) {
    title_first_packet_ns = now_ns;
  }
  title_last_packet_ns = now_ns;
  ++title_packet_count;
}

// 0x829F04A8 is the predicate FH1's D3D fence waits (sub_823E91F0 and six
// other loops) call while the GPU fence word has not reached their target.
// r3 is the wait record: +0 the device, +8 the fence value last seen. The
// device keeps a pointer to the fence word at +11024 (written by the
// command processor's EVENT_WRITE_SHD) and a lost-device flag at bit 1 of
// +11069. The predicate spins briefly and checks its own no-progress
// timeout; this blocks first, until the command processor writes guest
// memory, so the loop re-checks the fence without burning the core. The
// 1 ms bound keeps the predicate's timeout and kick logic running.
void PinyonShiftGpuFenceWait(PPCRegister& r3) {
  if (!REXCVAR_GET(pinyon_shift_block_on_gpu_fence)) {
    return;
  }
  auto* memory = rex::system::kernel_state()->memory();
  // Through TranslateVirtual: the fence word is in the 0xE0000000 physical
  // view, whose host mapping is offset.
  auto load = [memory](uint32_t address) {
    return rex::byte_swap(
        std::atomic_ref<uint32_t>(*memory->TranslateVirtual<uint32_t*>(address))
            .load(std::memory_order_acquire));
  };
  const uint32_t device = load(r3.u32);
  if (!device || (*memory->TranslateVirtual(device + 11069) & 0x2)) {
    return;
  }
  const uint32_t fence_address = load(device + 11024);
  const uint32_t last_seen = load(r3.u32 + 8);
  if (!fence_address || load(fence_address) != last_seen) {
    return;
  }
  // Fences a few microseconds away are cheaper to catch spinning.
  const auto spin_end =
      Clock::now() + std::chrono::microseconds(REXCVAR_GET(pinyon_shift_gpu_fence_spin_us));
  do {
    if (load(fence_address) != last_seen) {
      return;
    }
  } while (Clock::now() < spin_end);
  const uint32_t sequence = rex::system::GpuWriteSequence();
  if (load(fence_address) != last_seen) {
    return;
  }
  const auto wait_start = Clock::now();
  rex::system::WaitForGpuWrite(sequence, std::chrono::milliseconds(1));
  PERF_counter_inc(kTitleGpuFenceWaitCount);
  PERF_counter_add(kTitleGpuFenceWaitNs, std::chrono::duration_cast<std::chrono::nanoseconds>(
                                             Clock::now() - wait_start)
                                             .count());
}

// After the title loads a DynamicRenderSettings control from a render
// scenario's XML (r30 the control, r26 the scenario): records each gameplay
// scenario by its EnvMapFrequencyScale (how often the dynamic cubemap that
// cars reflect is redrawn, the control's float at +4) and applies the
// reflection rate and shadow settings to it.
void PinyonShiftRenderSettingLoaded(PPCRegister& r26, PPCRegister& r30) {
  auto* memory = rex::system::kernel_state()->memory();
  auto* control = memory->TranslateVirtual<uint32_t*>(r30.u32);
  if (rex::byte_swap(control[0]) != FH1_ADDR(0x8223C5F4u)) return;
  RenderScenario scenario = {r26.u32, r30.u32, 0.0f, 0, false};
  const uint32_t bits = rex::byte_swap(control[1]);
  std::memcpy(&scenario.env_value, &bits, sizeof(bits));
  if (const uint8_t* skip = SkipShadowControl(memory, r26.u32)) {
    scenario.skip_value = skip[4];
    scenario.skip_set = (rex::byte_swap(*memory->TranslateVirtual<uint32_t*>(
                             r26.u32 + kSetBitsOffset)) &
                         kSkipShadowBit) != 0;
  }
  std::lock_guard<std::mutex> lock(render_scenarios_mutex);
  if (render_scenarios.empty()) {
    applied_env_rate = float(REXCVAR_GET(pinyon_shift_fh1_env_map_rate));
  }
  render_scenarios.push_back(scenario);
  SetEnvMapRate(memory, scenario, applied_env_rate);
  if (shadows_skipped) SetShadowsSkipped(memory, scenario, true);
}

// The title's gamma ramp builder (sub_82C28070, r3 the display object, f1 the
// exponent, f2 and f3 the offset and range, r4 and r5 the curve and encoding)
// fills a ramp on its stack from those arguments, the display's ramp format
// and constants, then hands it to the device: as 128 piecewise-linear entries
// a channel (r1 + 128) or 256 entries a channel (r1 + 1664), 1,536 bytes
// either way. Its caller (sub_82586CD8) clamps a gamma transition's progress
// to 1 but clears the transition only past 1, so once the title has faded
// the screen it rebuilds the same ramp every frame. The hooks at the start of
// each format's path find a ramp built from the same arguments, put it back
// on the stack and jump to the device call; the hooks at the device call
// keep each newly built ramp.
namespace {

struct GammaRamp {
  bool valid = false;
  uint64_t key[4] = {};
  uint8_t data[1536];
};
constexpr uint32_t kGammaRampOffset[2] = {128, 1664};
thread_local GammaRamp gamma_ramps[2];
thread_local int gamma_ramp_pending = -1;
thread_local uint64_t gamma_ramp_pending_key[4];

// At the start of a path: f28 holds f1, f27 f3 + 1, f2 is still the argument,
// r26 and r25 hold r4 and r5, r24 holds r3.
bool GammaRampBegin(PPCContext& ctx, uint8_t* base, int path) {
  gamma_ramp_pending = -1;
  if (!REXCVAR_GET(pinyon_shift_reuse_gamma_ramp)) return false;
  const uint64_t key[4] = {ctx.f28.u64, ctx.f27.u64, ctx.f2.u64,
                           (uint64_t(ctx.r26.u32) << 32) | ctx.r25.u32};
  GammaRamp& ramp = gamma_ramps[path];
  if (!ramp.valid || std::memcmp(ramp.key, key, sizeof(key))) {
    std::memcpy(gamma_ramp_pending_key, key, sizeof(key));
    gamma_ramp_pending = path;
    return false;
  }
  const uint32_t stack = ctx.r1.u32 + kGammaRampOffset[path];
  std::memcpy(base + stack, ramp.data, sizeof(ramp.data));
  // The arguments of the device call the hook jumps to.
  ctx.r3.u64 = rex::byte_swap(*reinterpret_cast<uint32_t*>(base + ctx.r24.u32 + 20));
  ctx.r4.u64 = 2;
  ctx.r5.u64 = stack;
  return true;
}

void GammaRampBuilt(PPCContext& ctx, uint8_t* base, int path) {
  if (gamma_ramp_pending != path) return;
  gamma_ramp_pending = -1;
  GammaRamp& ramp = gamma_ramps[path];
  std::memcpy(ramp.data, base + ctx.r1.u32 + kGammaRampOffset[path], sizeof(ramp.data));
  std::memcpy(ramp.key, gamma_ramp_pending_key, sizeof(ramp.key));
  ramp.valid = true;
}

// The device call (sub_829F1EF8, D3D's SetPWLGamma; r3 the device, r5 the
// ramp) converts the ramp through the display gamma table into 1,536 bytes,
// compares them with the device's copy at +15408 and, only if they differ,
// stores them and marks the gamma dirty. The display gamma is fixed
// (VdGetCurrentDisplayGamma), so the conversion depends on the ramp alone:
// with the ramp and the device's copy as the last call left them, the call
// finds them equal and does nothing.
constexpr uint32_t kDeviceGammaCopy = 15408;
struct DeviceGamma {
  bool valid = false;
  uint32_t device = 0;
  uint8_t ramp[1536];
  uint8_t copy[1536];
};
thread_local DeviceGamma device_gamma;
thread_local uint8_t device_gamma_pending_ramp[1536];

}  // namespace

bool PinyonShiftGammaRampPwlBegin(PPCContext& ctx, uint8_t* base) {
  return GammaRampBegin(ctx, base, 0);
}

// At the device call: keeps a newly built ramp, then skips the call when it
// would change nothing.
bool PinyonShiftGammaRampPwlBuilt(PPCContext& ctx, uint8_t* base) {
  GammaRampBuilt(ctx, base, 0);
  const uint8_t* ramp = base + ctx.r5.u32;
  std::memcpy(device_gamma_pending_ramp, ramp, sizeof(device_gamma_pending_ramp));
  return REXCVAR_GET(pinyon_shift_skip_unchanged_device_gamma) && device_gamma.valid &&
         device_gamma.device == ctx.r3.u32 &&
         !std::memcmp(device_gamma.ramp, ramp, sizeof(device_gamma.ramp)) &&
         !std::memcmp(device_gamma.copy, base + ctx.r3.u32 + kDeviceGammaCopy,
                      sizeof(device_gamma.copy));
}

// After the device call (or its skip): the device's copy now matches the
// ramp just passed. r24 still holds the builder's r3, whose +20 is the device.
void PinyonShiftGammaRampPwlDeviceSet(PPCContext& ctx, uint8_t* base) {
  const uint32_t device = rex::byte_swap(*reinterpret_cast<uint32_t*>(base + ctx.r24.u32 + 20));
  device_gamma.device = device;
  std::memcpy(device_gamma.ramp, device_gamma_pending_ramp, sizeof(device_gamma.ramp));
  std::memcpy(device_gamma.copy, base + device + kDeviceGammaCopy, sizeof(device_gamma.copy));
  device_gamma.valid = true;
}

bool PinyonShiftGammaRampLinearBegin(PPCContext& ctx, uint8_t* base) {
  return GammaRampBegin(ctx, base, 1);
}

void PinyonShiftGammaRampLinearBuilt(PPCContext& ctx, uint8_t* base) {
  GammaRampBuilt(ctx, base, 1);
}
