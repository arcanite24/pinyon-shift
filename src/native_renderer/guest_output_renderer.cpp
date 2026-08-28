#include <atomic>
#include <string>

#include <rex/cvar.h>
#include <rex/system/interfaces/graphics.h>

#include "native_renderer/guest_output_renderer.h"
#include "pinyon_shift_diagnostics.h"

REXCVAR_DEFINE_BOOL(
    pinyon_shift_native_renderer_diagnostic_clear, false, "Pinyon Shift",
    "Replace guest output with a diagnostic clear for native-renderer testing")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

namespace {

std::atomic<bool> g_failure_latched{};
std::atomic<uint64_t> g_callback_count{};
std::atomic<uint64_t> g_claimed_count{};

bool RenderDiagnosticOutput(
    const rex::system::NativeGuestOutputRenderContext& context) {
  const uint64_t callback =
      g_callback_count.fetch_add(1, std::memory_order_relaxed) + 1;
  if (g_failure_latched.load(std::memory_order_acquire)) {
    return false;
  }
  if (context.backend != rex::system::NativeGuestOutputBackend::kD3D12 ||
      !context.clear_color) {
    if (!g_failure_latched.exchange(true, std::memory_order_acq_rel)) {
      pinyon_shift::diagnostics::RecordEvent(
          "native_renderer.output.failure",
          {{"reason", "unsupported_context"}, {"fallback", "xenos"}});
    }
    return false;
  }

  const bool alternate = ((context.submission / 120) & 1) != 0;
  const float color[4] = {alternate ? 0.04f : 0.85f, 0.16f,
                          alternate ? 0.55f : 0.03f, 1.0f};
  if (!context.clear_color(context, color)) {
    if (!g_failure_latched.exchange(true, std::memory_order_acq_rel)) {
      pinyon_shift::diagnostics::RecordEvent(
          "native_renderer.output.failure",
          {{"reason", "diagnostic_clear_failed"}, {"fallback", "xenos"}});
    }
    return false;
  }

  const uint64_t claimed =
      g_claimed_count.fetch_add(1, std::memory_order_relaxed) + 1;
  if (callback == 1 || callback % 300 == 0) {
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.output.frame",
        {{"callback", std::to_string(callback)},
         {"claimed", std::to_string(claimed)},
         {"submission", std::to_string(context.submission)},
         {"guest_width", std::to_string(context.guest_output_width)},
         {"guest_height", std::to_string(context.guest_output_height)},
         {"display_width", std::to_string(context.display_width)},
         {"display_height", std::to_string(context.display_height)},
         {"format", std::to_string(context.output_format)},
         {"mode", "diagnostic_clear"}});
  }
  return true;
}

}  // namespace

namespace pinyon_shift::native_renderer {

void InstallGuestOutputRenderer(rex::system::IGraphicsSystem* graphics_system) {
  if (!graphics_system ||
      !REXCVAR_GET(pinyon_shift_native_renderer_diagnostic_clear)) {
    return;
  }
  g_failure_latched.store(false, std::memory_order_release);
  g_callback_count.store(0, std::memory_order_release);
  g_claimed_count.store(0, std::memory_order_release);
  graphics_system->SetNativeGuestOutputRenderer(&RenderDiagnosticOutput);
  diagnostics::RecordEvent("native_renderer.output.installed",
                           {{"mode", "diagnostic_clear"},
                            {"fallback", "xenos"}});
}

void UninstallGuestOutputRenderer(
    rex::system::IGraphicsSystem* graphics_system) {
  if (graphics_system) {
    graphics_system->SetNativeGuestOutputRenderer(nullptr);
  }
}

}  // namespace pinyon_shift::native_renderer
