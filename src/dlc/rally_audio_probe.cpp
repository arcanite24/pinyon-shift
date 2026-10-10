#include "dlc/rally_audio_probe.h"

#include <algorithm>
#include <atomic>
#include <bit>
#include <cmath>
#include <cstring>
#include <fstream>
#include <memory>
#include <mutex>
#include <vector>
#include <rex/audio/sdl/sdl_audio_driver.h>
#include <rex/filesystem.h>
#include <rex/audio/sdl/sdl_audio_system.h>
#include <rex/runtime.h>
#include "fh1_render_test.h"
#include "platform/host_platform.h"
#include "pinyon_shift_diagnostics.h"

namespace pinyon_shift::rally {
using rex::X_STATUS;
namespace {
// Native frames are planar big-endian 6-channel, 256 samples at 48 kHz.
// Allocate before starting the guest; no allocation or disk work in SubmitFrame.
constexpr size_t kMaximumSamples = 8u * 48000u * 6u;
std::unique_ptr<float[]> samples;
std::mutex mutex;
std::atomic<bool> capturing{};
bool pending = false;
constexpr int frequency = 48000, channels = 6;
size_t count = 0;

void Capture(const uint32_t* buffer) {
  if (!capturing.load(std::memory_order_acquire)) return;
  std::lock_guard lock(mutex);
  if (!capturing.load(std::memory_order_relaxed)) return;
  for (size_t i = 0; i < 256 && count < kMaximumSamples; ++i) {
    for (size_t channel = 0; channel < 6; ++channel)
      samples[count++] = std::bit_cast<float>(std::byteswap(buffer[channel * 256 + i]));
  }
  if (count == kMaximumSamples) capturing.store(false, std::memory_order_release);
}

class ProbeDriver final : public rex::audio::sdl::SDLAudioDriver {
 public:
  using SDLAudioDriver::SDLAudioDriver;
  void SubmitFrame(uint32_t pointer) override {
    Capture(memory_->TranslateVirtual<const uint32_t*>(pointer));
    SDLAudioDriver::SubmitFrame(pointer);
  }
};
class ProbeSystem final : public rex::audio::sdl::SDLAudioSystem {
 public:
  using SDLAudioSystem::SDLAudioSystem;
  X_STATUS CreateDriver(size_t index, rex::thread::Semaphore* semaphore,
                        rex::audio::AudioDriver** out) override {
    if (index != 0) return SDLAudioSystem::CreateDriver(index, semaphore, out);
    auto driver = std::make_unique<ProbeDriver>(memory_, semaphore);
    if (!driver->Initialize()) { driver->Shutdown(); return X_STATUS_UNSUCCESSFUL; }
    *out = driver.release();
    return X_STATUS_SUCCESS;
  }
};
}  // namespace

void ConfigureAudioProbe(rex::RuntimeConfig& config) {
  if (!fh1_render_test::Enabled() ||
      platform::EnvironmentVariable("PINYON_SHIFT_RALLY_AUDIO_PROBE").value_or("").empty()) return;
  samples = std::make_unique<float[]>(kMaximumSamples);
  config.audio_factory = [](rex::runtime::FunctionDispatcher* dispatcher) {
    return std::make_unique<ProbeSystem>(dispatcher);
  };
}

void BeginAudioProbeCapture() {
  if (!samples) return;
  std::lock_guard lock(mutex);
  count = 0;
  pending = true;
  capturing.store(true, std::memory_order_release);
}

void FlushAudioProbeCapture() {
  if (!pending || capturing.load(std::memory_order_acquire)) return;
  std::lock_guard lock(mutex);
  pending = false;
  if (!count) {
    diagnostics::RecordEvent("dlc.rally.audio_capture_error", {{"error", "native PCM capture empty"}});
    return;
  }
  const auto path = fh1_render_test::OutputDirectory() / "rally-audio-probe.wav";
  std::ofstream file(path, std::ios::binary | std::ios::trunc);
  auto u16 = [&](uint16_t v) { char b[]{char(v), char(v >> 8)}; file.write(b, 2); };
  auto u32 = [&](uint32_t v) { char b[]{char(v), char(v >> 8), char(v >> 16), char(v >> 24)}; file.write(b, 4); };
  const uint32_t size = uint32_t(count * 2);
  file.write("RIFF", 4); u32(36 + size); file.write("WAVEfmt ", 8); u32(16);
  u16(1); u16(uint16_t(channels)); u32(uint32_t(frequency));
  u32(uint32_t(frequency * channels * 2)); u16(uint16_t(channels * 2)); u16(16);
  file.write("data", 4); u32(size);
  std::vector<int16_t> pcm(count);
  double energy = 0;
  float peak = 0;
  for (size_t i = 0; i < count; ++i) {
    const float sample = std::isfinite(samples[i]) ? std::clamp(samples[i], -1.f, 1.f) : 0.f;
    pcm[i] = int16_t(std::lround(sample * 32767));
    energy += double(sample) * sample;
    peak = std::max(peak, std::abs(sample));
  }
  // The supported Windows/macOS/Linux hosts are little endian.
  file.write(reinterpret_cast<const char*>(pcm.data()), std::streamsize(size));
  file.close();
  diagnostics::RecordEvent(file ? "dlc.rally.audio_capture_saved" : "dlc.rally.audio_capture_error",
      {{"path", rex::path_to_utf8(path)}, {"frequency", std::to_string(frequency)},
       {"source", "native_pre_device_pcm"},
       {"channels", std::to_string(channels)}, {"samples", std::to_string(count)},
       {"rms", std::to_string(std::sqrt(energy / double(count)))}, {"peak", std::to_string(peak)}});
}
}  // namespace pinyon_shift::rally
