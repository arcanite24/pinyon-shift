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
REXCVAR_DEFINE_STRING(
    pinyon_shift_native_renderer, "xenos", "Pinyon Shift",
    "Guest-output renderer: xenos, diagnostic_clear, diagnostic_triangle")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

namespace {

std::atomic<bool> g_failure_latched{};
std::atomic<uint64_t> g_callback_count{};
std::atomic<uint64_t> g_claimed_count{};
enum class DiagnosticMode : uint32_t { kClear, kTriangle };
std::atomic<DiagnosticMode> g_mode{DiagnosticMode::kClear};

bool RenderDiagnosticOutput(
    const rex::system::NativeGuestOutputRenderContext& context) {
  const uint64_t callback =
      g_callback_count.fetch_add(1, std::memory_order_relaxed) + 1;
  if (g_failure_latched.load(std::memory_order_acquire)) {
    return false;
  }
  if (context.backend != rex::system::NativeGuestOutputBackend::kD3D12) {
    if (!g_failure_latched.exchange(true, std::memory_order_acq_rel)) {
      pinyon_shift::diagnostics::RecordEvent(
          "native_renderer.output.failure",
          {{"reason", "unsupported_context"}, {"fallback", "xenos"}});
    }
    return false;
  }

  const DiagnosticMode mode = g_mode.load(std::memory_order_relaxed);
  bool rendered = false;
  if (mode == DiagnosticMode::kTriangle &&
      context.draw_diagnostic_triangle) {
    rendered = context.draw_diagnostic_triangle(
        context, uint32_t((context.submission / 120) & 1));
  } else if (mode == DiagnosticMode::kClear && context.clear_color) {
    const bool alternate = ((context.submission / 120) & 1) != 0;
    const float color[4] = {alternate ? 0.04f : 0.85f, 0.16f,
                            alternate ? 0.55f : 0.03f, 1.0f};
    rendered = context.clear_color(context, color);
  }
  if (!rendered) {
    if (!g_failure_latched.exchange(true, std::memory_order_acq_rel)) {
      pinyon_shift::diagnostics::RecordEvent(
          "native_renderer.output.failure",
          {{"reason", mode == DiagnosticMode::kTriangle
                          ? "diagnostic_triangle_failed"
                          : "diagnostic_clear_failed"},
           {"fallback", "xenos"}});
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
         {"mode", mode == DiagnosticMode::kTriangle
                      ? "diagnostic_triangle"
                      : "diagnostic_clear"}});
  }
  return true;
}

}  // namespace

namespace pinyon_shift::native_renderer {

void InstallGuestOutputRenderer(rex::system::IGraphicsSystem* graphics_system) {
  if (!graphics_system) {
    return;
  }
  const std::string mode = REXCVAR_GET(pinyon_shift_native_renderer);
  const bool legacy_clear =
      REXCVAR_GET(pinyon_shift_native_renderer_diagnostic_clear);
  if (mode == "xenos" && !legacy_clear) {
    diagnostics::RecordEvent("native_renderer.output.state",
                             {{"mode", "xenos"}, {"authority", "xenos"}});
    return;
  }
  if (mode != "diagnostic_clear" && mode != "diagnostic_triangle" &&
      !(mode == "xenos" && legacy_clear)) {
    diagnostics::RecordEvent(
        "native_renderer.output.failure",
        {{"reason", "unsupported_mode"}, {"fallback", "xenos"}});
    return;
  }
  const DiagnosticMode selected_mode =
      mode == "diagnostic_triangle" ? DiagnosticMode::kTriangle
                                    : DiagnosticMode::kClear;
  g_mode.store(selected_mode, std::memory_order_release);
  g_failure_latched.store(false, std::memory_order_release);
  g_callback_count.store(0, std::memory_order_release);
  g_claimed_count.store(0, std::memory_order_release);
  graphics_system->SetNativeGuestOutputRenderer(&RenderDiagnosticOutput);
  diagnostics::RecordEvent("native_renderer.output.installed",
                           {{"mode", selected_mode == DiagnosticMode::kTriangle
                                         ? "diagnostic_triangle"
                                         : "diagnostic_clear"},
                            {"fallback", "xenos"}});
}

void UninstallGuestOutputRenderer(
    rex::system::IGraphicsSystem* graphics_system) {
  if (graphics_system) {
    graphics_system->SetNativeGuestOutputRenderer(nullptr);
  }
}

}  // namespace pinyon_shift::native_renderer
