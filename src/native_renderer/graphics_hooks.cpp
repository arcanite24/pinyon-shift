#include "native_renderer/graphics_hooks.h"

#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <vector>

#include <rex/cvar.h>
#include <rex/perf/counter.h>
#include <rex/ppc/context.h>
#include <rex/system/gpu_write_signal.h>
#include <rex/system/interfaces/graphics.h>
#include <rex/system/kernel_state.h>
#include <rex/system/xmemory.h>
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
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);
REXCVAR_DEFINE_BOOL(pinyon_shift_block_on_gpu_fence, true, "Pinyon Shift",
                    "Block the title's GPU fence polling until the command processor next "
                    "writes guest memory (bounded to 1 ms) instead of spinning")
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
                              Clock::now()});
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
  const auto spin_end = Clock::now() + std::chrono::microseconds(20);
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

// Scales the render scenario's EnvMapFrequencyScale (how often the dynamic
// cubemap that cars reflect is redrawn) after the title loads it from the
// DynamicRenderSettings XML: r30 is the control just loaded, its float at +4.
void PinyonShiftRenderSettingLoaded(PPCRegister& r30) {
  const float rate = REXCVAR_GET(pinyon_shift_fh1_env_map_rate);
  if (rate == 1.0f) return;
  auto* memory = rex::system::kernel_state()->memory();
  auto* control = memory->TranslateVirtual<uint32_t*>(r30.u32);
  if (rex::byte_swap(control[0]) != 0x8223C5F4u) return;
  uint32_t bits = rex::byte_swap(control[1]);
  float value;
  std::memcpy(&value, &bits, sizeof(value));
  value *= rate;
  std::memcpy(&bits, &value, sizeof(bits));
  control[1] = rex::byte_swap(bits);
}
