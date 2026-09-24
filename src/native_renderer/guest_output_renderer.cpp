#include <rex/system/interfaces/graphics.h>
#include <rex/cvar.h>

#include <chrono>

#include "fh1_render_test.h"
#include "native_renderer/graphics_hooks.h"
#include "native_renderer/guest_output_renderer.h"
#include "native_renderer/snr04_owned_scene_diagnostic.h"

REXCVAR_DEFINE_BOOL(pinyon_shift_native_output_clear_probe, false,
                    "Pinyon Shift",
                    "Exercise opt-in early native output selection during render tests")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);
REXCVAR_DEFINE_BOOL(pinyon_shift_native_scene_clear_probe, false,
                    "Pinyon Shift",
                    "Claim render-test output only with a current owned race scene")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

namespace {

bool ObserveRenderTestOutput(
    const rex::system::NativeGuestOutputRenderContext& context) {
  static thread_local uint64_t captured_frame = 0;
  static thread_local uint64_t capture_us = 0;
  if (context.phase == rex::system::NativeGuestOutputPhase::kNativeAttempt) {
    const auto capture_begin = std::chrono::steady_clock::now();
    pinyon_shift::native_renderer::ObserveSnr03OutputFrame(
        context.frame_sequence, context.device);
    pinyon_shift::native_renderer::ObserveSnr02ItemOutputFrame(
        context.frame_sequence, context.device);
    pinyon_shift::native_renderer::ObserveSnr02TrackOutputFrame(
        context.frame_sequence);
    captured_frame = context.frame_sequence;
    capture_us = std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::steady_clock::now() - capture_begin).count();
    if (REXCVAR_GET(pinyon_shift_native_scene_clear_probe) &&
        pinyon_shift::fh1_render_test::Enabled() &&
        context.guest_output_width == 1280 &&
        context.guest_output_height == 720 && context.clear_color) {
      auto scene = pinyon_shift::native_renderer::SnapshotSnr04LiveScene(
          context.frame_sequence);
      if (scene) {
        const float color[4]{float(scene->core_draws) / 4096.f, 0.375f,
                             (scene->source_frame & 1) ? 0.75f : 0.25f, 1.f};
        return context.clear_color(context, color);
      }
    }
    if (!REXCVAR_GET(pinyon_shift_native_output_clear_probe) ||
        !pinyon_shift::fh1_render_test::Enabled() ||
        context.guest_output_width != 1280 ||
        context.guest_output_height != 720 || !context.clear_color)
      return false;
    const float color[4]{0.125f, 0.375f,
                         (context.frame_sequence & 1) ? 0.75f : 0.25f, 1.f};
    return context.clear_color(context, color);
  }
  pinyon_shift::fh1_render_test::ObserveOutput(context);
  pinyon_shift::native_renderer::ObserveSnr04BatchOutputFrame(
      context.frame_sequence, context.device,
      captured_frame == context.frame_sequence ? capture_us : 0);
  return false;
}

}  // namespace

namespace pinyon_shift::native_renderer {

void InstallGuestOutputRenderer(rex::system::IGraphicsSystem* graphics_system) {
  if (graphics_system) {
    graphics_system->SetNativeGuestOutputRenderer(
        fh1_render_test::Enabled() || Snr03ProbeEnabled() || Snr02ItemProbeEnabled() ||
                REXCVAR_GET(pinyon_shift_native_output_clear_probe) ||
                REXCVAR_GET(pinyon_shift_native_scene_clear_probe)
            ? &ObserveRenderTestOutput : nullptr);
  }
}

void UninstallGuestOutputRenderer(
    rex::system::IGraphicsSystem* graphics_system) {
  if (graphics_system) {
    graphics_system->SetNativeGuestOutputRenderer(nullptr);
  }
  FinishSnr04BatchDiagnostic();
}

}  // namespace pinyon_shift::native_renderer
