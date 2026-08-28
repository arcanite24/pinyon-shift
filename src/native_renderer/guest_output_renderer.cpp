#include <atomic>
#include <filesystem>
#include <string>

#include <rex/cvar.h>
#include <rex/system/interfaces/graphics.h>

#include "native_renderer/guest_output_renderer.h"
#include "native_renderer/shader_pack.h"
#include "pinyon_shift_diagnostics.h"

REXCVAR_DEFINE_BOOL(
    pinyon_shift_native_renderer_diagnostic_clear, false, "Pinyon Shift",
    "Replace guest output with a diagnostic clear for native-renderer testing")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);
REXCVAR_DEFINE_STRING(pinyon_shift_native_renderer, "xenos", "Pinyon Shift",
                      "Guest-output renderer: xenos, diagnostic_clear, "
                      "diagnostic_triangle, diagnostic_retained_pass")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);
REXCVAR_DEFINE_STRING(
    pinyon_shift_native_shader_pack, "", "Pinyon Shift",
    "Local NR-02 D3D12 shader pack path; empty disables pack loading")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

namespace {

std::atomic<bool> g_failure_latched{};
std::atomic<uint64_t> g_callback_count{};
std::atomic<uint64_t> g_claimed_count{};
enum class DiagnosticMode : uint32_t { kClear, kTriangle, kRetainedPass };
std::atomic<DiagnosticMode> g_mode{DiagnosticMode::kClear};
pinyon_shift::native_renderer::ShaderPack g_shader_pack;

const char *DiagnosticModeName(DiagnosticMode mode) {
  switch (mode) {
  case DiagnosticMode::kTriangle:
    return "diagnostic_triangle";
  case DiagnosticMode::kRetainedPass:
    return "diagnostic_retained_pass";
  default:
    return "diagnostic_clear";
  }
}

bool RenderDiagnosticOutput(
    const rex::system::NativeGuestOutputRenderContext &context) {
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
  if (mode == DiagnosticMode::kTriangle && context.draw_diagnostic_triangle) {
    rendered = context.draw_diagnostic_triangle(
        context, uint32_t((context.submission / 120) & 1));
  } else if (mode == DiagnosticMode::kRetainedPass &&
             context.draw_retained_pass) {
    rendered = context.draw_retained_pass(context);
  } else if (mode == DiagnosticMode::kClear && context.clear_color) {
    const bool alternate = ((context.submission / 120) & 1) != 0;
    const float color[4] = {alternate ? 0.04f : 0.85f, 0.16f,
                            alternate ? 0.55f : 0.03f, 1.0f};
    rendered = context.clear_color(context, color);
  }
  if (!rendered) {
    if (mode == DiagnosticMode::kRetainedPass && context.draw_retained_pass) {
      if (callback == 1 || callback % 300 == 0) {
        pinyon_shift::diagnostics::RecordEvent(
            "native_renderer.output.waiting",
            {{"reason", "retained_pass_unavailable"},
             {"callback", std::to_string(callback)},
             {"fallback", "xenos"},
             {"suppression", "disabled"}});
      }
      return false;
    }
    if (!g_failure_latched.exchange(true, std::memory_order_acq_rel)) {
      pinyon_shift::diagnostics::RecordEvent(
          "native_renderer.output.failure",
          {{"reason", std::string(DiagnosticModeName(mode)) + "_failed"},
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
         {"mode", DiagnosticModeName(mode)},
         {"xenos_draw", "preserved"},
         {"suppression", "disabled"}});
  }
  return true;
}

} // namespace

namespace pinyon_shift::native_renderer {

void InstallGuestOutputRenderer(rex::system::IGraphicsSystem *graphics_system) {
  if (!graphics_system) {
    return;
  }
  const std::string shader_pack_path =
      REXCVAR_GET(pinyon_shift_native_shader_pack);
  g_shader_pack.Reset();
  if (!shader_pack_path.empty()) {
    const auto *shader_pack_path_begin =
        reinterpret_cast<const char8_t *>(shader_pack_path.data());
    const std::filesystem::path local_shader_pack_path(
        std::u8string(shader_pack_path_begin,
                      shader_pack_path_begin + shader_pack_path.size()));
    if (g_shader_pack.Load(local_shader_pack_path)) {
      diagnostics::RecordEvent(
          "native_renderer.shader_pack.ready",
          {{"entries", std::to_string(g_shader_pack.entry_count())},
           {"backend", "d3d12"}});
    } else {
      diagnostics::RecordEvent(
          "native_renderer.shader_pack.failure",
          {{"reason", "validation_failed"}, {"fallback", "xenos"}});
    }
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
      mode != "diagnostic_retained_pass" &&
      !(mode == "xenos" && legacy_clear)) {
    diagnostics::RecordEvent(
        "native_renderer.output.failure",
        {{"reason", "unsupported_mode"}, {"fallback", "xenos"}});
    return;
  }
  const DiagnosticMode selected_mode =
      mode == "diagnostic_triangle"        ? DiagnosticMode::kTriangle
      : mode == "diagnostic_retained_pass" ? DiagnosticMode::kRetainedPass
                                           : DiagnosticMode::kClear;
  g_mode.store(selected_mode, std::memory_order_release);
  g_failure_latched.store(false, std::memory_order_release);
  g_callback_count.store(0, std::memory_order_release);
  g_claimed_count.store(0, std::memory_order_release);
  graphics_system->SetNativeGuestOutputRenderer(&RenderDiagnosticOutput);
  diagnostics::RecordEvent("native_renderer.output.installed",
                           {{"mode", DiagnosticModeName(selected_mode)},
                            {"fallback", "xenos"},
                            {"xenos_draw", "preserved"},
                            {"suppression", "disabled"}});
}

void UninstallGuestOutputRenderer(
    rex::system::IGraphicsSystem *graphics_system) {
  if (graphics_system) {
    graphics_system->SetNativeGuestOutputRenderer(nullptr);
  }
  g_shader_pack.Reset();
}

} // namespace pinyon_shift::native_renderer
