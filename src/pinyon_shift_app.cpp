#include "pinyon_shift_app.h"
#include "pinyon_shift_init.h"
#include "fh1_render_test.h"
#include "dlc/rally_audio_probe.h"
#include "dlc/rally_pace_notes.h"

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <regex>
#include <sstream>
#include <string>
#include <system_error>
#include <thread>

#include <rex/cvar.h>
#include <rex/kernel/xboxkrnl/io.h>
#include <rex/logging.h>
#include <rex/perf/counter.h>
#include <rex/runtime.h>
#include <rex/system/kernel_state.h>
#include <rex/system/xam/content_manager.h>
#include <rex/system/xthread.h>
#include <rex/thread.h>
#include <rex/input/input_system.h>
#include <rex/ui/flags.h>
#include <rex/ui/keybinds.h>
#include <rex/ui/presenter.h>
#if REX_HAS_VULKAN
#include <rex/ui/vulkan/provider.h>
#endif
#include <rex/ui/windowed_app_context.h>
#include <rex/ui/window.h>

#include "native_renderer/guest_output_renderer.h"
#include "native_renderer/shader_capture.h"
#include "pinyon_shift_diagnostics.h"
#include "platform/host_platform.h"
#include "pinyon_shift_runtime_hooks.h"
#include "config/host_config.h"
#include "ui/host_style.h"
#include "ui/hostui/host_ui.h"
#include "cheats.h"
#include "mod/mod_host.h"
#include "mod/overlay_device.h"
#include "save/car_cards.h"
#include "save_backups.h"
#include "ui/achievements_menu.h"
#include "ui/photo_export.h"
#include "ui/xam_dialogs.h"
#include "ui/settings_menu.h"
#include "ui/touch_pad.h"

#include <cstdio>

#ifdef PINYON_SHIFT_PGO_GENERATE
extern "C" int __llvm_profile_dump(void);
#endif

REXCVAR_DEFINE_BOOL(pinyon_shift_touch_controls, REX_PLATFORM_ANDROID, "Pinyon Shift",
                    "On-screen controls for touch screens: a steering stick, throttle, brake "
                    "and buttons, shown on a touch and hidden after a while without one")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);
REXCVAR_DEFINE_UINT32(pinyon_shift_config_schema, 28, "Pinyon Shift",
                      "Pinyon Shift host configuration schema version");
REXCVAR_DEFINE_STRING(enabled_mods, "", "Mods",
                      "Mods to load from <state>/mods, in order, separated by commas. With any "
                      "enabled the title plays a separate profile (<state>/user-modded)")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);
REXCVAR_DEFINE_BOOL(pinyon_shift_hor_plus, false, "Display",
                    "Ultrawide: widen the horizontal field of view to the window's aspect "
                    "(Hor+), shown stretched from the 16:9 image; the HUD stretches with it")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_BOOL(pinyon_shift_save_backups, true, "Pinyon Shift",
                    "Copy the save files to <state>/backups/saves after the title writes them "
                    "(restore from SETTINGS > PROFILE > SAVE BACKUPS)")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);
REXCVAR_DEFINE_BOOL(pinyon_shift_repair_car_cards, true, "Pinyon Shift",
                    "At start, move car cards that older builds saved striped to "
                    "<state>/backups/car-cards, so the title shows an empty card until the car "
                    "is saved again")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);
REXCVAR_DEFINE_INT32(pinyon_shift_save_backup_slots, 10, "Pinyon Shift",
                     "Save backups to keep; older ones are deleted")
    .range(1, 100)
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);
REXCVAR_DEFINE_BOOL(pinyon_shift_host_xam_dialogs, true, "Pinyon Shift",
                    "Draw the title's message boxes and keyboard with the host UI (the game's "
                    "fonts, pad navigation) instead of the built-in ImGui dialogs")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);
REXCVAR_DEFINE_BOOL(pinyon_shift_prepare_all_scales, false, "Pinyon Shift",
                    "Graphics preparation also prepares the shader packs of the other "
                    "resolution scales, so RESOLUTION SCALE changes in game without a restart")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);
REXCVAR_DEFINE_BOOL(pinyon_shift_capture_performance, true, "Pinyon Shift",
                    "Capture lightweight per-frame performance counters to a session CSV");
namespace {

std::filesystem::path LongHostPath(std::filesystem::path path) {
#if REX_PLATFORM_WIN32
  // DLC localized assets exceed MAX_PATH in installed state roots.
  path = std::filesystem::absolute(path).make_preferred();
  if (!path.native().starts_with(L"\\\\?\\"))
    path = path.native().starts_with(L"\\\\")
        ? L"\\\\?\\UNC\\" + path.native().substr(2) : L"\\\\?\\" + path.native();
#endif
  return path;
}

// Schema 22 added the renderer choice (fh1_renderer) and schema 23 made the
// native renderer its default. Schema 24 retires the choice: the native
// renderer is the only renderer, so migration drops fh1_renderer and the other
// renderer-era settings the runtime no longer registers. Schema 25 drops the
// occlusion-query mode and ZPD classification settings: the host-query path
// is the only occlusion path. Schema 26 turns clear_memory_page_state off: it
// made every frame upload again every page the CPU had uploaded, about 20 MB
// of vertex data per race frame, and the race window runs 12 % faster
// without it with no rendering difference on the race, photo, dealership and
// FMV routes. Schema 27 makes Vulkan the renderer's graphics API, with the
// GPU commands thread split into a decoder and a recorder: the 1x race runs
// at 120 fps there against about 55 on Direct3D 12 (docs/PERFORMANCE_BACKLOG.md).
// Schema 28 retires Direct3D 12 from player settings and moves its saved
// selections to Vulkan. The legacy backend remains available to developers.
constexpr uint32_t kConfigSchema = 28;

bool EnsureSupportedConfig(const std::filesystem::path& path, bool& created,
                           bool& migrated) {
  created = false;
  migrated = false;
  if (!std::filesystem::exists(path)) {
    std::ofstream output(path, std::ios::binary | std::ios::trunc);
    if (!output) {
      return false;
    }
    output << "# Pinyon Shift host configuration.\n"
              "# Increment this only with an explicit migration.\n"
              "# Controller support with keyboard emulation as a fallback.\n"
              "pinyon_shift_config_schema = "
           << kConfigSchema << "\n"
              "input_backend = \"sdl\"\n"
              "hid_mappings_file = \"gamecontrollerdb.txt\"\n"
              "mnk_mode = true\n"
              "keybind_a = \"LMB,Space\"\n"
              "keybind_start = \"Return\"\n"
              "d3d12_allow_variable_refresh_rate_and_tearing = false\n"
              "gpu_backend = \"vulkan\"\n"
              "gpu_record_thread = true\n"
              "vsync = true\n"
              "host_present_fps_limit = 0\n"
              "host_present_sleep_spin = true\n"
              "pinyon_shift_capture_performance = true\n"
              "xma_relaxed_padding_admission = false\n"
              "pinyon_shift_stabilize_vehicle_presentation = false\n"
              "pinyon_shift_skip_opening_movies = false\n"
              // LOW-SPEC 60 (LS-1.5): never the display's rate, which on a
              // 144-240 Hz display renders and simulates that many frames.
              // A capable machine moves to PERFORMANCE 120 once its GPU is
              // known (ApplyFirstRunHardwareDefaults).
              "pinyon_shift_fh1_render_fps_limit = 60\n"
              "pinyon_shift_fh1_source_presentation = true\n"
              "anisotropic_override = -1\n"
              "present_effect = \"bilinear\"\n"
              "swap_post_effect = \"none\"\n"
              "disable_bloom = true\n"
              "disable_motion_blur = true\n"
              "disable_depth_of_field = true\n"
              "fh1_msaa_single_sample = true\n"
              "draw_resolution_scale_x = 1\n"
              "draw_resolution_scale_y = 1\n"
              "clear_memory_page_state = false\n";
    created = true;
    return output.good();
  }

  const auto config_contents = pinyon_shift::config::ReadFile(path);
  if (!config_contents) {
    return false;
  }
  const std::string& config_text = *config_contents;
  const std::regex schema_pattern(
      R"((?:^|\n)\s*pinyon_shift_config_schema\s*=\s*([0-9]+)\s*(?:#.*)?(?:\r?\n|$))");
  std::smatch match;
  if (!std::regex_search(config_text, match, schema_pattern) || match.size() != 2) {
    // A file without a schema line was rewritten by something that keeps
    // only the settings it knows, such as the F4 settings overlay's save
    // before it merged into the file (#345, #364). Its settings are current,
    // so keep them under the current schema rather than refuse to start.
    if (std::regex_search(config_text, std::regex(R"((?:^|\n)\s*pinyon_shift_config_schema\s*=)"))) {
      return false;
    }
    std::filesystem::path backup = path;
    backup += ".noschema.bak";
    std::error_code backup_error;
    std::filesystem::copy_file(path, backup, std::filesystem::copy_options::overwrite_existing,
                               backup_error);
    if (backup_error) {
      return false;
    }
    const std::string repaired =
        "pinyon_shift_config_schema = " + std::to_string(kConfigSchema) + "\n" + config_text;
    if (!pinyon_shift::config::WriteAtomically(path, repaired)) {
      return false;
    }
    migrated = true;
    return true;
  }
  try {
    const uint32_t schema = std::stoul(match[1].str());
    if (schema == kConfigSchema) {
      return true;
    }
    if (schema < 1 || schema >= kConfigSchema) {
      return false;
    }

    std::filesystem::path backup = path;
    backup += ".schema" + std::to_string(schema) + ".bak";
    std::error_code backup_error;
    std::filesystem::copy_file(path, backup,
                               std::filesystem::copy_options::skip_existing,
                               backup_error);
    if (backup_error && backup_error != std::errc::file_exists) {
      return false;
    }

    std::string migrated_text = config_text;
    migrated_text.replace(static_cast<size_t>(match.position(1)),
                          static_cast<size_t>(match.length(1)),
                          std::to_string(kConfigSchema));
    const std::regex rejected_interpolation_pattern(
        R"((?:^|\n)\s*pinyon_shift_fh1_frame_interpolation\s*=\s*(?:true|false)\s*(?:#.*)?(?:\r?\n|$))",
        std::regex::icase);
    migrated_text = std::regex_replace(migrated_text,
                                       rejected_interpolation_pattern, "\n");
    if (schema < 27) {
      migrated_text = std::regex_replace(
          migrated_text,
          std::regex(R"((host_present_fps_limit\s*=\s*)\d+)",
                     std::regex::icase),
          "$1 0");
    }
    migrated_text = std::regex_replace(
        migrated_text,
        std::regex(
            R"((?:^|\n)\s*pinyon_shift_fh1_guest_vblank_hz\s*=\s*\d+\s*(?:#.*)?(?:\r?\n|$))",
            std::regex::icase),
        "\n");
    migrated_text = std::regex_replace(
        migrated_text,
        std::regex(
            R"((?:^|\n)\s*pinyon_shift_native_renderer_texture_bridge\s*=\s*(?:true|false)\s*(?:#.*)?(?:\r?\n|$))",
            std::regex::icase),
        "\n");
    for (const char* retired_setting : {
             "pinyon_shift_native_renderer",
             "pinyon_shift_native_renderer_sky_horizon_suppression",
             "pinyon_shift_fh1_native_v4",
             "readback_resolve_half_pixel_offset",
             "readback_memexport",
             "readback_memexport_fast",
             "pinyon_shift_native_renderer_census",
             // Schema 24: renderer-selection, native-shadow and Xenos-era
             // renderer settings that no longer exist.
             "fh1_renderer",
             "fh1_native_shadow",
             "fh1_native_shadow_dump_dir",
             "fh1_native_shadow_dump_frames",
             "fh1_native_shadow_verify",
             "fh1_native_shadow_verify_draws",
             "fh1_discovery_sampling",
             "fh1_owned_depth_clear",
             "fh1_owned_depth_tile_clear",
             "fh1_native_reflection_mips",
             "fh1_mip_decode_probe",
             "fh1_native_ui_boundary_probe",
             "fh1_glow_probe",
             "fh1_recycle_geometry_buffers",
             "fh1_contain_geometry_windows",
             "fh1_cache_geometry_rejections",
             "fh1_geometry_cache_mb",
             "native_stencil_value_output",
             "native_stencil_value_output_d3d12_intel",
             "pinyon_shift_native_race",
             "pinyon_shift_native_race_capture_start_frame",
             "pinyon_shift_native_ui_live",
             "pinyon_shift_native_ui_replay_source_frame",
             "pinyon_shift_native_ui_scene_probe",
             "pinyon_shift_native_ui_shadow_start_frame",
             "pinyon_shift_native_ui_clear_probe",
             "pinyon_shift_native_output_clear_probe",
             "pinyon_shift_native_scene_clear_probe",
             "pinyon_shift_native_scene_triangle_probe",
             "pinyon_shift_native_small_target_probe",
             "pinyon_shift_native_track_probe",
             "pinyon_shift_native_ordered_live_probe",
             "pinyon_shift_fh1_clear_producer_trace",
             "pinyon_shift_fh1_scene_dump",
             "pinyon_shift_snr01_trace_following_frame",
             "pinyon_shift_snr01_trace_resident_packet_writers",
             "pinyon_shift_snr01_trace_source_frame",
             "pinyon_shift_snr01_watch_packet_pages",
             "pinyon_shift_snr02_item_payload_probe",
             "pinyon_shift_snr02_trace_first_rebuild_after_frame",
             "pinyon_shift_snr02_trace_view_call",
             "pinyon_shift_snr02_track_payload_probe",
             "pinyon_shift_snr03_probe_following_frame",
             "pinyon_shift_snr03_probe_frame",
             "pinyon_shift_snr04_live_continuous",
             "pinyon_shift_snr04_live_handoff",
             "pinyon_shift_snr04_live_source_frame",
             "pinyon_shift_snr04_live_worker",
             "pinyon_shift_snr_m02_trace_source_frame",
             // Schema 25: one occlusion-query path.
             "occlusion_query",
             "zpd_end_policy",
             "zpd_end_fallback"}) {
      migrated_text = std::regex_replace(
          migrated_text,
          std::regex("(?:^|\\n)\\s*" + std::string(retired_setting) +
                         "\\s*=.*(?:\\r?\\n|$)",
                     std::regex::icase),
          "\n");
    }
    // readback_resolve stays a developer setting (none, fast, some, full), but
    // launchers before schema 24 wrote it for players, and `fast` never
    // reaches free roam: drop those values only.
    if (schema < 24) {
      migrated_text = std::regex_replace(
          migrated_text,
          std::regex(R"((?:^|\n)\s*readback_resolve\s*=.*(?:\r?\n|$))", std::regex::icase),
          "\n");
    }
    if (schema < 26) {
      migrated_text = std::regex_replace(
          migrated_text,
          std::regex(R"((^|\n)(\s*clear_memory_page_state\s*=\s*)true)", std::regex::icase),
          "$1$2false");
    }
    if (schema < 28) {
      // Vulkan is the supported backend. Replace old Direct3D 12 selections,
      // including "any"; the settings list below appends both when absent.
      migrated_text = std::regex_replace(
          migrated_text,
          std::regex(R"re((^|\n)(\s*gpu_backend\s*=\s*)"[^"]*")re", std::regex::icase),
          "$1$2\"vulkan\"");
      migrated_text = std::regex_replace(
          migrated_text,
          std::regex(R"((^|\n)(\s*gpu_record_thread\s*=\s*)false)", std::regex::icase),
          "$1$2true");
    }
    if (schema == 1) {
      const std::regex stabilization_pattern(
          R"((?:^|\n)\s*pinyon_shift_stabilize_vehicle_presentation\s*=\s*(true|false)\s*(?:#.*)?(?:\r?\n|$))");
      std::smatch stabilization_match;
      if (std::regex_search(migrated_text, stabilization_match,
                            stabilization_pattern)) {
        migrated_text.replace(
            static_cast<size_t>(stabilization_match.position(1)),
            static_cast<size_t>(stabilization_match.length(1)), "false");
      } else {
        if (!migrated_text.empty() && migrated_text.back() != '\n') {
          migrated_text.push_back('\n');
        }
        migrated_text +=
            "pinyon_shift_stabilize_vehicle_presentation = false\n";
      }
    }

    const std::regex accept_binding_pattern(
        R"((?:^|\n)\s*keybind_a\s*=\s*\"[^\"]*\"\s*(?:#.*)?(?:\r?\n|$))");
    if (!std::regex_search(migrated_text, accept_binding_pattern)) {
      if (!migrated_text.empty() && migrated_text.back() != '\n') {
        migrated_text.push_back('\n');
      }
      migrated_text += "keybind_a = \"LMB,Space\"\n";
    }

    const std::pair<const char*, const char*> graphics_settings[] = {
        {"xma_relaxed_padding_admission",
         "xma_relaxed_padding_admission = false\n"},
        {"anisotropic_override", "anisotropic_override = -1\n"},
        {"swap_post_effect", "swap_post_effect = \"none\"\n"},
        {"disable_bloom", "disable_bloom = true\n"},
        {"disable_motion_blur", "disable_motion_blur = true\n"},
        {"disable_depth_of_field", "disable_depth_of_field = true\n"},
        {"fh1_msaa_single_sample", "fh1_msaa_single_sample = true\n"},
        {"draw_resolution_scale_x", "draw_resolution_scale_x = 1\n"},
        {"draw_resolution_scale_y", "draw_resolution_scale_y = 1\n"},
        {"gpu_backend", "gpu_backend = \"vulkan\"\n"},
        {"gpu_record_thread", "gpu_record_thread = true\n"},
        {"vsync", "vsync = true\n"},
        {"host_present_fps_limit", "host_present_fps_limit = 0\n"},
        {"host_present_sleep_spin", "host_present_sleep_spin = true\n"},
        {"clear_memory_page_state", "clear_memory_page_state = false\n"},
        {"pinyon_shift_fh1_render_fps_limit",
         "pinyon_shift_fh1_render_fps_limit = 60\n"},
        {"pinyon_shift_fh1_source_presentation",
         "pinyon_shift_fh1_source_presentation = true\n"},
    };
    for (const auto& [name, line] : graphics_settings) {
      const std::regex setting_pattern("(?:^|\\n)\\s*" + std::string(name) +
                                       "\\s*=", std::regex::icase);
      if (!std::regex_search(migrated_text, setting_pattern)) {
        if (!migrated_text.empty() && migrated_text.back() != '\n') {
          migrated_text.push_back('\n');
        }
        migrated_text += line;
      }
    }

    std::filesystem::path temporary = path;
    temporary += ".migrating";
    {
      std::ofstream output(temporary, std::ios::binary | std::ios::trunc);
      if (!output) {
        return false;
      }
      output << migrated_text;
      if (!output.good()) {
        return false;
      }
    }
    if (!pinyon_shift::platform::ReplaceFileAtomically(temporary, path)) {
      return false;
    }
    migrated = true;
    return true;
  } catch (const std::exception&) {
    return false;
  }
}

}  // namespace

std::unique_ptr<rex::ui::WindowedApp> PinyonShiftApp::Create(
    rex::ui::WindowedAppContext& context) {
  if (!pinyon_shift::diagnostics::InitializeEarly()) {
#if REX_PLATFORM_WIN32
    ExitProcess(ERROR_NOT_SUPPORTED);
#else
    std::_Exit(EXIT_FAILURE);
#endif
  }
  return std::unique_ptr<PinyonShiftApp>(
      new PinyonShiftApp(context, "pinyon_shift", PPCImageConfig));
}

void PinyonShiftApp::OnConfigurePaths(rex::PathConfig& paths) {
  namespace diagnostics = pinyon_shift::diagnostics;
  const auto& state_root = diagnostics::StateRoot();
  if (auto game_root = diagnostics::EnvironmentPath("PINYON_SHIFT_GAME_ROOT")) {
    paths.game_data_root = *game_root;
  }
  paths.user_data_root = LongHostPath(state_root / "user");
#if defined(PINYON_SHIFT_TITLE_UPDATE_V4) && PINYON_SHIFT_TITLE_UPDATE_V4
  // The v4 build's code was generated from the patched executables: load the
  // player's verified title update (its .xexp files and media.zip) from a
  // folder the base build never mounts, and apply the patches while loading.
  paths.update_data_root = state_root / "title-update-v4";
  rex::cvar::SetFlagByName("xex_apply_patches", "true");
#else
  paths.update_data_root = state_root / "update";
#endif
  paths.cache_root = state_root / "cache";
  paths.config_path = state_root / "config" / "pinyon_shift.toml";
  host_config_ = std::make_unique<pinyon_shift::config::HostConfig>(paths.config_path);
  // A restore the player scheduled in the settings screen, before the title
  // can open the files.
  pinyon_shift::SaveBackups::ApplyPendingRestore(paths.user_data_root,
                                                 state_root / "backups" / "saves");
  if (REXCVAR_GET(pinyon_shift_repair_car_cards)) {
    const size_t repaired = pinyon_shift::save::QuarantineStripedCarCards(
        paths.user_data_root, state_root / "backups" / "car-cards");
    if (repaired) {
      REXLOG_INFO("Moved {} striped car card(s) to backups/car-cards", repaired);
      pinyon_shift::diagnostics::RecordEvent("save.car_cards.repaired",
                                             {{"cards", std::to_string(repaired)}});
    }
  }
  // Mods play a separate profile (NP-7.5), started from a copy of the
  // player's own the first time, so the unmodded save is never touched.
  // Cheats may come from the command line as well as the config file.
  bool cheats = pinyon_shift::cheats::Requested();
  if (host_config_->Load()) {
    enabled_mods_ = host_config_->Get("enabled_mods").value_or("");
    cheats = cheats || host_config_->Get("pinyon_shift_cheats").value_or("false") == "true";
  }
  if (!enabled_mods_.empty() || cheats) {
    const auto modded = LongHostPath(state_root / "user-modded");
    std::error_code error;
    if (!std::filesystem::exists(modded, error) &&
        std::filesystem::exists(paths.user_data_root, error)) {
      if (!pinyon_shift::SaveBackups::CopyProfile(paths.user_data_root, modded)) {
        pinyon_shift::platform::ShowFatalError(
            "Could not create the modded profile", "The player profile could not be copied.");
        pinyon_shift::platform::ExitImmediately(1);
      }
      diagnostics::RecordEvent("mod.profile.created", {{"path", modded.string()}});
    }
    paths.user_data_root = modded;
    pinyon_shift::mod::SetModdedProfile(modded);
    pinyon_shift::cheats::SetProfileIsolated();
  }

  bool config_created = false;
  bool config_migrated = false;
  if (!EnsureSupportedConfig(paths.config_path, config_created,
                             config_migrated)) {
    diagnostics::RecordEvent("config.unsupported",
                             {{"path", paths.config_path.string()},
                              {"required_schema", std::to_string(kConfigSchema)}});
    pinyon_shift::platform::ShowFatalError(
        "Unsupported configuration",
        "Pinyon Shift could not create the host configuration, or its schema is "
        "unsupported. Remove or migrate pinyon_shift.toml before retrying.");
    // ERROR_REVISION_MISMATCH, the code this exit has always had.
    pinyon_shift::platform::ExitImmediately(1306);
  }

  config_created_ = config_created;
  if (REXCVAR_GET(log_file).empty()) {
    REXCVAR_SET(log_file, (state_root / "logs" / "runtime.log").string());
  }

  diagnostics::RecordEvent(
      "paths.configured",
      {{"game", paths.game_data_root.string()},
       {"user", paths.user_data_root.string()},
       {"update", paths.update_data_root.string()},
       {"cache", paths.cache_root.string()},
       {"config", paths.config_path.string()},
       {"config_schema", std::to_string(kConfigSchema)},
       {"config_created", config_created ? "1" : "0"},
       {"config_migrated", config_migrated ? "1" : "0"},
       {"log", REXCVAR_GET(log_file)}});
}

std::optional<rex::PathConfig> PinyonShiftApp::OnFinalizePaths(
    const rex::PathConfig& defaults,
    std::function<void(rex::PathConfig)> resume) {
  (void)resume;
  const auto refresh = pinyon_shift::platform::DisplayRefreshRate(
      window() ? window()->GetNativeWindowHandle() : nullptr);
  if (refresh && *refresh >= 24 && *refresh <= 240) {
    REXCVAR_SET(video_mode_refresh_rate, double(*refresh));
    pinyon_shift::diagnostics::RecordEvent("display.refresh.detected",
                                           {{"hz", std::to_string(*refresh)}});
  }
  return defaults;
}

void PinyonShiftApp::OnConfigureFonts(ImFontAtlas* atlas) {
  float dpi_scale = 1.0f;
  if (const rex::ui::Window* host_window = window()) {
    dpi_scale = float(host_window->GetDpi()) / float(host_window->GetMediumDpi());
  }
  pinyon_shift::ui::ConfigureHostFonts(atlas, dpi_scale);
}

void PinyonShiftApp::OnConfigureStyle(ImGuiStyle& imgui_style, rex::ui::Style& ui_style) {
  pinyon_shift::ui::ConfigureHostStyle(imgui_style, ui_style);
}

void PinyonShiftApp::OnPostInitLogging() {
  std::string perf_csv = rex::cvar::GetFlagByName("perf_log_csv");
  if (perf_csv.empty() && REXCVAR_GET(pinyon_shift_capture_performance)) {
    perf_csv = (pinyon_shift::diagnostics::StateRoot() / "logs" /
                (pinyon_shift::diagnostics::SessionId() + ".perf.csv"))
                   .string();
  }
  if (!perf_csv.empty()) {
    rex::perf::SetCsvLogPath(perf_csv);
  }
  pinyon_shift::diagnostics::RecordEvent(
      "logging.ready", {{"config_schema", std::to_string(REXCVAR_GET(pinyon_shift_config_schema))},
                        {"d3d12_tearing_allowed",
                         rex::cvar::GetFlagByName(
                             "d3d12_allow_variable_refresh_rate_and_tearing")},
                        {"vehicle_presentation_stabilization",
                         rex::cvar::GetFlagByName(
                             "pinyon_shift_stabilize_vehicle_presentation")},
                        {"renderer", rex::cvar::GetFlagByName("gpu_backend")},
                        {"resolution", rex::cvar::GetFlagByName("resolution")},
                        {"vsync", rex::cvar::GetFlagByName("vsync")},
                        {"host_present_fps_limit",
                         rex::cvar::GetFlagByName("host_present_fps_limit")},
                        {"host_present_sleep_spin",
                         rex::cvar::GetFlagByName("host_present_sleep_spin")},
                        {"draw_resolution_scale_x",
                         rex::cvar::GetFlagByName("draw_resolution_scale_x")},
                        {"draw_resolution_scale_y",
                         rex::cvar::GetFlagByName("draw_resolution_scale_y")},
                        {"clear_memory_page_state",
                         rex::cvar::GetFlagByName("clear_memory_page_state")},
                        {"anisotropic_override",
                         rex::cvar::GetFlagByName("anisotropic_override")},
                        {"swap_post_effect", rex::cvar::GetFlagByName("swap_post_effect")},
                        {"disable_bloom", rex::cvar::GetFlagByName("disable_bloom")},
                        {"disable_motion_blur",
                         rex::cvar::GetFlagByName("disable_motion_blur")},
                        {"disable_depth_of_field",
                         rex::cvar::GetFlagByName("disable_depth_of_field")},
                        {"fh1_gpu_corpus",
                         rex::cvar::GetFlagByName(
                             "pinyon_shift_fh1_gpu_corpus")},
                        {"fh1_render_fps_limit",
                         rex::cvar::GetFlagByName(
                             "pinyon_shift_fh1_render_fps_limit")},
                        {"fh1_source_presentation",
                         rex::cvar::GetFlagByName(
                             "pinyon_shift_fh1_source_presentation")},
                        {"xma_relaxed_padding_admission",
                         rex::cvar::GetFlagByName(
                             "xma_relaxed_padding_admission")},
                        {"perf_csv_enabled", perf_csv.empty() ? "0" : "1"},
                        {"perf_csv", perf_csv}});
}

void PinyonShiftApp::OnPreSetup(rex::RuntimeConfig& config) {
  config.gpu_plugin =
      pinyon_shift::platform::EnvironmentVariable("PINYON_SHIFT_FH1_DISC_SHADER_CORPUS_DIR")
          ? "fh1-producer"
          : "fh1";
  pinyon_shift::fh1_render_test::Configure(config);
  pinyon_shift::rally::ConfigureAudioProbe(config);
  // The on-screen controls feed user 0 beside any controller (AP-4.2);
  // routes keep their scripted pad alone.
  if (REXCVAR_GET(pinyon_shift_touch_controls) && !pinyon_shift::fh1_render_test::Enabled() &&
      config.input_factory) {
    config.input_factory = [base = config.input_factory](bool tool_mode) {
      auto input = base(tool_mode);
      if (!tool_mode) {
        if (auto* system = dynamic_cast<rex::input::InputSystem*>(input.get())) {
          system->AddDriver(pinyon_shift::ui::TouchPad::Get().CreateDriver());
        }
      }
      return input;
    };
  }
  pinyon_shift::diagnostics::RecordEvent(
      "runtime.setup.begin",
      {{"graphics_requested", (config.graphics || !config.gpu_plugin.empty()) ? "1" : "0"},
       {"gpu_plugin", config.gpu_plugin},
       {"audio_requested", config.audio_factory ? "1" : "0"},
       {"input_requested", config.input_factory ? "1" : "0"}});
}

bool PinyonShiftApp::SetupPresentation() {
  if (ReXApp::SetupPresentation()) {
    return true;
  }
  pinyon_shift::diagnostics::RecordEvent("graphics.unavailable",
                                         {{"gpu_backend", rex::cvar::GetFlagByName("gpu_backend")}});
  if (!pinyon_shift::fh1_render_test::Enabled()) {
    pinyon_shift::platform::ShowFatalError(
        "Graphics unavailable",
        "Pinyon Shift could not start the graphics device. It needs a GPU whose "
        "driver supports Vulkan 1.3. Install the newest driver from AMD, Intel or "
        "NVIDIA, then retry. Older integrated graphics, such as Intel HD Graphics "
        "before the 6th generation, cannot run the game.");
  }
  pinyon_shift::platform::ExitImmediately(1308);
}

void PinyonShiftApp::OnPostLoadXexImage() {
  const auto title_id = runtime() && runtime()->kernel_state()
                            ? runtime()->kernel_state()->title_id()
                            : 0;
  char title[16]{};
  std::snprintf(title, sizeof(title), "%08X", title_id);
  pinyon_shift::diagnostics::RecordEvent("xex.loaded", {{"title_id", title}});
}

PinyonShiftApp::~PinyonShiftApp() = default;

void PinyonShiftApp::ToggleGameMenu() {
  if (host_ui_ && host_ui_->is_open()) {
    host_ui_->Close();
    return;
  }
  OpenSettingsMenu();
}

bool PinyonShiftApp::EnsureHostUi() {
  if (host_ui_) {
    return true;
  }
  rex::ui::Presenter* presenter =
      runtime() && runtime()->graphics_system() ? runtime()->graphics_system()->presenter()
                                                : nullptr;
  if (!presenter || !immediate_drawer() || !window()) {
    REXLOG_WARN("Host UI: presentation is not ready");
    return false;
  }
  host_ui_ = std::make_unique<pinyon_shift::hostui::HostUi>(
      *this, *presenter, *immediate_drawer(), *window(),
      static_cast<rex::input::InputSystem*>(runtime()->input_system()), game_data_root());
  // Mods' HUD labels (NP-11), drawn by the host UI over the title.
  host_ui_->SetHudSource([] {
    std::vector<pinyon_shift::hostui::HostUi::HudText> texts;
    for (const auto& label : pinyon_shift::mod::HudLabels()) {
      texts.push_back({label.text, label.x, label.y, label.size});
    }
    return texts;
  });
  pinyon_shift::mod::SetHudChangedCallback([this] {
    if (window()) {
      window()->app_context().CallInUIThreadDeferred([this] {
        if (host_ui_) host_ui_->HudChanged();
      });
    }
  });
  if (PinyonShiftRallyPaceEnabled()) {
    host_ui_->SetRallyPaceSource(pinyon_shift::rally::ReadPaceHud,
        PinyonShiftRallyAdapterRoot() / "game/media/UI/Textures/Horizon/Hud/Rally/CoDriverIconSet.xds");
    pinyon_shift::rally::SetPaceHudChangedCallback([this] {
      if (window()) window()->app_context().CallInUIThreadDeferred([this] {
        if (host_ui_) host_ui_->HudChanged();
      });
    });
  }
  if (REXCVAR_GET(pinyon_shift_touch_controls)) {
    auto& pad = pinyon_shift::ui::TouchPad::Get();
    window()->AddInputListener(&pad, 0);
    pad.SetChangedCallback([this] {
      if (window()) {
        window()->app_context().CallInUIThreadDeferred([this] {
          if (host_ui_) host_ui_->HudChanged();
        });
      }
    });
    host_ui_->SetOverlaySource([this] {
      std::vector<pinyon_shift::hostui::HostUi::OverlayDisc> discs;
      auto& pad = pinyon_shift::ui::TouchPad::Get();
      if (!window() || !pad.Visible() || (host_ui_ && host_ui_->is_open())) {
        return discs;
      }
      for (const auto& shape : pad.Shapes(float(window()->GetActualPhysicalWidth()),
                                          float(window()->GetActualPhysicalHeight()))) {
        discs.push_back({shape.x, shape.y, shape.radius, shape.stick ? "" : shape.label,
                         shape.pressed && !shape.stick});
        if (shape.stick) {
          discs.push_back({shape.stick_x, shape.stick_y, shape.radius * 0.45f, "",
                           shape.pressed});
        }
      }
      return discs;
    });
  }
  host_ui_->HudChanged();
  if (REXCVAR_GET(pinyon_shift_host_xam_dialogs)) {
    xam_dialogs_ = pinyon_shift::ui::CreateXamDialogs(*host_ui_, [this] {
      return pinyon_shift::ui::CreateAchievementsScreen(achievements());
    });
    rex::kernel::xam::SetXamUiProvider(xam_dialogs_.get());
  }
  return true;
}

void PinyonShiftApp::OpenSettingsMenu() {
  if (host_ui_ && host_ui_->is_open()) {
    return;
  }
  if (!EnsureHostUi()) {
    return;
  }
  if (!host_config_) {
    REXLOG_WARN("Host UI: the settings file is not known yet");
    return;
  }
  pinyon_shift::ui::SettingsServices services;
  services.achievements = [this] {
    return pinyon_shift::ui::CreateAchievementsScreen(achievements());
  };
  services.save_backups = save_backups_.get();
  services.mods_root = pinyon_shift::diagnostics::StateRoot() / "mods";
  services.draw_resolution_scale = [this]() -> uint32_t {
    auto* graphics = runtime() ? runtime()->graphics_system() : nullptr;
    return graphics ? graphics->draw_resolution_scale() : 0;
  };
  services.output_size = [this]() -> std::optional<std::pair<uint32_t, uint32_t>> {
    // The window, letterboxed to the title's 16:9 unless the image is
    // stretched to fill it (the FH1 source presentation paints no guest
    // output rectangle to read back).
    const uint32_t width = window() ? window()->GetActualPhysicalWidth() : 0;
    const uint32_t height = window() ? window()->GetActualPhysicalHeight() : 0;
    if (!width || !height) {
      return std::nullopt;
    }
    if (!REXCVAR_GET(present_letterbox) || REXCVAR_GET(pinyon_shift_hor_plus)) {
      return std::pair{width, height};
    }
    return uint64_t(width) * 9 > uint64_t(height) * 16
               ? std::pair{height * 16 / 9, height}
               : std::pair{width, width * 9 / 16};
  };
  services.save_photo = [this] {
    pinyon_shift::ui::SavePhoto(runtime() && runtime()->graphics_system()
                                    ? runtime()->graphics_system()->presenter()
                                    : nullptr);
  };
  services.trainer = true;
  host_ui_->Open(pinyon_shift::ui::CreateSettingsMenu(*host_ui_, *host_config_, services));
}

void PinyonShiftApp::UpdateHorPlus() {
  float scale = 1.0f;
  if (REXCVAR_GET(pinyon_shift_hor_plus) && window()) {
    const uint32_t width = window()->GetActualPhysicalWidth();
    const uint32_t height = window()->GetActualPhysicalHeight();
    if (width && height) {
      scale = std::max(1.0f, (float(width) / float(height)) / (16.0f / 9.0f));
    }
  }
  PinyonShiftSetViewportAspectScale(scale);
  // The HUD keeps 16:9 proportions in the stretched image; 16:9 screens do not squeeze.
  rex::cvar::SetFlagByName("fh1_hud_squeeze",
                           fmt::format("{:.6f}", map_view_open_ ? 1.0f : scale));
  pinyon_shift::diagnostics::RecordEvent("display.hor_plus",
                                         {{"scale", fmt::format("{:.4f}", scale)}});
}

void PinyonShiftApp::ApplyMapView(bool open) {
  map_view_open_ = open;
  if (!REXCVAR_GET(pinyon_shift_hor_plus)) return;
  // Wider View stretches the widened gameplay frame over the window; the
  // title's 16:9 screens (menus, Autoshow, map) are letterboxed (#363).
  rex::cvar::SetFlagByName("present_letterbox", open ? "true" : "false");
  UpdateHorPlus();
  pinyon_shift::diagnostics::RecordEvent("display.hor_plus_view", {{"wide", open ? "0" : "1"}});
}

void PinyonShiftApp::OnPostSetup() {
  // Launcher DLC selection is shared by normal and isolated modded profiles.
  // Saved games still use the active user root chosen in OnConfigurePaths.
  runtime()->kernel_state()->content_manager()->SetMarketplaceRoot(
      LongHostPath(pinyon_shift::diagnostics::StateRoot() / "user"));
  if (window() && !resize_listener_added_) {
    window()->AddListener(&resize_listener_);
    resize_listener_added_ = true;
  }
  rex::cvar::RegisterChangeCallback("pinyon_shift_hor_plus",
                                    [this](std::string_view, std::string_view) {
                                      if (window()) {
                                        window()->app_context().CallInUIThreadDeferred(
                                            [this] { ApplyMapView(map_view_open_); UpdateHorPlus(); });
                                      }
                                    });
  UpdateHorPlus();
  PinyonShiftSetMapViewCallback([this](bool open) {
    if (window()) {
      window()->app_context().CallInUIThreadDeferred([this, open] { ApplyMapView(open); });
    }
  });
  rex::ui::RegisterBind("bind_game_menu", "F6", "Open the in-game settings menu",
                        [this] { ToggleGameMenu(); });
#if defined(__ANDROID__)
  // Android's Back (the button or gesture; a key to the app) opens SETTINGS
  // when no host menu is up, so a player with only a touch screen reaches
  // them; inside the menus the host UI takes it first and steps back.
  rex::ui::RegisterBind("bind_android_back", "Escape", "Android Back: open the settings menu",
                        [this] {
                          if (!host_ui_ || !host_ui_->is_open()) {
                            OpenSettingsMenu();
                          }
                        });
#endif
  pinyon_shift::cheats::InstallChangeLog();
  // A one-shot save edit or a live credits set applied: clear its setting so
  // the next start (and, for the credits, the next profile load) keeps the
  // player's own progress.
  pinyon_shift::cheats::SetAppliedCallback([this](std::string_view setting) {
    if (!window()) return;
    window()->app_context().CallInUIThreadDeferred([this, name = std::string(setting)] {
      if (name == "cheat_set_credits") {
        rex::cvar::SetFlagByName(name, "-1");
      }
      if (host_config_ && host_config_->Load()) {
        // The credits take -1 for "leave them", the field list "".
        host_config_->Set(name, name == "cheat_set_credits" ? "-1" : "");
        if (!host_config_->Save()) {
          REXLOG_ERROR("Cheats: could not clear {} in {}", name, host_config_->path().string());
        }
      }
    });
  });
  rex::ui::RegisterBind("bind_trainer", "F10", "Open the trainer (cheats on)", [this] {
    if (!pinyon_shift::cheats::Enabled()) {
      return;
    }
    if (host_ui_ && host_ui_->is_open()) {
      host_ui_->Close();
    } else if (EnsureHostUi() && host_config_) {
      host_ui_->Open(pinyon_shift::ui::CreateTrainerMenu(*host_ui_, *host_config_));
    }
  });
  rex::ui::RegisterBind("bind_photo", "F8", "Save the current frame as a PNG photo", [this] {
    pinyon_shift::ui::SavePhoto(runtime() && runtime()->graphics_system()
                                    ? runtime()->graphics_system()->presenter()
                                    : nullptr);
  });
  rex::ui::RegisterBind("bind_fullscreen", "F11", "Toggle fullscreen", [this] {
    const bool fullscreen = !REXCVAR_GET(fullscreen);
    rex::cvar::SetFlagByName("fullscreen", fullscreen ? "true" : "false");
    if (host_config_ && host_config_->Load()) {
      host_config_->Set("fullscreen", fullscreen ? "true" : "false");
      host_config_->Save();
    }
  });
  // ResizeBuffers cannot toggle tearing: a changed preference makes the
  // presenter recreate its swap chain on the next surface update, which is
  // requested outside any drawing.
  rex::cvar::RegisterChangeCallback(
      "d3d12_allow_variable_refresh_rate_and_tearing", [this](std::string_view, std::string_view) {
        if (!window()) {
          return;
        }
        window()->app_context().CallInUIThreadDeferred([this] {
          if (runtime() && runtime()->graphics_system() &&
              runtime()->graphics_system()->presenter()) {
            runtime()->graphics_system()->presenter()->OnSurfaceResizeFromUIThread();
          }
        });
      });
  // SETTINGS in the pause menu (NP-1.5): the hook runs on the guest thread.
  PinyonShiftSetPauseSettingsHandler([this] {
    if (window()) {
      window()->app_context().CallInUIThreadDeferred([this] { OpenSettingsMenu(); });
    }
  });
  if (!enabled_mods_.empty()) {
    pinyon_shift::mod::HostServices services;
    services.config = host_config_.get();
    services.post_to_ui = [this](std::function<void()> task) {
      if (window()) {
        window()->app_context().CallInUIThreadDeferred(std::move(task));
      }
    };
    pinyon_shift::mod::LoadMods(pinyon_shift::diagnostics::StateRoot(), enabled_mods_,
                                std::move(services));
    // Mods' texture replacements, ahead of any folders already configured.
    if (auto textures = pinyon_shift::mod::TextureRoots(); !textures.empty()) {
      std::string dirs;
      for (const auto& root : textures) dirs += (dirs.empty() ? "" : ";") + root.string();
      // Defined in the GPU module, so read by name.
      if (const std::string configured = rex::cvar::GetFlagByName("texture_replacement_dirs");
          !configured.empty()) {
        dirs += ";" + configured;
      }
      rex::cvar::SetFlagByName("texture_replacement_dirs", dirs);
      pinyon_shift::diagnostics::RecordEvent("mod.textures", {{"dirs", dirs}});
    }
  }
  // Owned DLC overlays do not activate mods or select the modded save tree.
  // Explicit mods remain ahead of the built-in assets in the overlay order.
  auto overlays = pinyon_shift::mod::OverlayRoots();
  const bool builtin_rally = PinyonShiftUseBuiltinRallyAdapter();
  if (builtin_rally) overlays.push_back(PinyonShiftRallyAdapterRoot() / "game");
  if (!overlays.empty()) {
    for (auto& root : overlays) root = LongHostPath(root);
    constexpr const char* kGameMount = "\\Device\\Harddisk0\\Partition1";
    auto overlay = std::make_unique<pinyon_shift::mod::OverlayDevice>(
        kGameMount, game_data_root(), std::move(overlays));
    if (overlay->Initialize() && runtime()->file_system()->ReplaceDevice(std::move(overlay))) {
      pinyon_shift::diagnostics::RecordEvent(builtin_rally ? "dlc.rally.overlay_mounted" : "mod.overlay.mounted");
    } else {
      REXLOG_ERROR("Could not mount the game file overlays");
      if (builtin_rally) pinyon_shift::diagnostics::RecordEvent("dlc.rally.adapter_error", {
          {"error", "could not mount the built-in Rally overlay"}});
    }
  }
  if (REXCVAR_GET(pinyon_shift_save_backups)) {
    save_backups_ = std::make_unique<pinyon_shift::SaveBackups>(
        pinyon_shift::diagnostics::StateRoot() / "user",
        pinyon_shift::diagnostics::StateRoot() / "backups" / "saves",
        size_t(std::max(1, REXCVAR_GET(pinyon_shift_save_backup_slots))));
    save_backups_->Start();
  }
  // Now, not on first use, so the title's first message box already gets
  // the host dialogs.
  if (window()) {
    window()->app_context().CallInUIThreadDeferred([this] {
      EnsureHostUi();
      pinyon_shift::mod::NotifyCreateDialogs();
    });
  }
  pinyon_shift::ui::ApplyMasterVolume();
  rex::cvar::RegisterChangeCallback(
      "pinyon_shift_master_volume",
      [](std::string_view, std::string_view) { pinyon_shift::ui::ApplyMasterVolume(); });
  pinyon_shift::diagnostics::RefreshCrashReporter();
  rex::kernel::xboxkrnl::SetGuestFileOpenObserver(&PinyonShiftObserveGuestFileOpen);
  pinyon_shift::native_renderer::InstallGuestOutputRenderer(
      runtime() ? runtime()->graphics_system() : nullptr);
  pinyon_shift::native_renderer::InstallShaderCapture(
      runtime() ? runtime()->graphics_system() : nullptr);
#if REX_HAS_VULKAN
  if (auto* graphics = runtime() ? runtime()->graphics_system() : nullptr) {
    if (auto* provider = dynamic_cast<rex::ui::vulkan::VulkanProvider*>(
            graphics->provider())) {
      if (auto* device = provider->vulkan_device()) {
        const auto& properties = device->properties();
        pinyon_shift::diagnostics::RecordEvent(
            "graphics.device.selected",
            {{"backend", "vulkan"},
             {"name", properties.deviceName},
             {"vendor_id", std::to_string(properties.vendorID)},
             {"device_id", std::to_string(properties.deviceID)},
             {"api_version", std::to_string(properties.apiVersion)},
             {"driver_version", std::to_string(properties.driverVersion)}});
        if (config_created_) {
          ApplyFirstRunHardwareDefaults(*device);
        }
      }
    }
  }
#endif
  pinyon_shift::diagnostics::RecordEvent(
      "runtime.setup.complete",
      {{"memory", runtime() && runtime()->memory() ? "1" : "0"},
       {"vfs", runtime() && runtime()->file_system() ? "1" : "0"},
       {"kernel", runtime() && runtime()->kernel_state() ? "1" : "0"},
       {"graphics", runtime() && runtime()->graphics_system() ? "1" : "0"},
       {"audio", runtime() && runtime()->audio_system() ? "1" : "0"},
       {"input", runtime() && runtime()->input_system() ? "1" : "0"}});
}

#if REX_HAS_VULKAN
void PinyonShiftApp::ApplyFirstRunHardwareDefaults(const rex::ui::vulkan::VulkanDevice& device) {
  // LS-1.5: a new config starts at LOW-SPEC 60. A discrete GPU with 6 GB or
  // more of its own memory, 6 or more logical cores and a display of 120 Hz
  // or faster start at PERFORMANCE 120 instead. Only on the launch that
  // created the config, so a player's own choices are never changed.
  const auto& functions = device.vulkan_instance()->functions();
  VkPhysicalDeviceProperties properties = {};
  functions.vkGetPhysicalDeviceProperties(device.physical_device(), &properties);
  VkPhysicalDeviceMemoryProperties memory = {};
  functions.vkGetPhysicalDeviceMemoryProperties(device.physical_device(), &memory);
  uint64_t device_local = 0;
  for (uint32_t i = 0; i < memory.memoryHeapCount; ++i) {
    if (memory.memoryHeaps[i].flags & VK_MEMORY_HEAP_DEVICE_LOCAL_BIT) {
      device_local = std::max(device_local, uint64_t(memory.memoryHeaps[i].size));
    }
  }
  const bool discrete = properties.deviceType == VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU;
  const unsigned cores = rex::thread::logical_processor_count();
  const double refresh = REXCVAR_GET(video_mode_refresh_rate);
  const bool capable = discrete && device_local >= (uint64_t(6) << 30) && cores >= 6 &&
                       refresh >= 119.0;
  if (capable && host_config_ && host_config_->Load()) {
    for (const auto& [name, literal] :
         {std::pair{"present_effect", "\"fsr\""},
          std::pair{"pinyon_shift_fh1_render_fps_limit", "120"}}) {
      host_config_->Set(name, literal);
      std::string value = literal;
      std::erase(value, '"');
      rex::cvar::SetFlagByName(name, value);
    }
    if (!host_config_->Save()) {
      REXLOG_ERROR("Settings: could not write {}", host_config_->path().string());
    }
  }
  pinyon_shift::diagnostics::RecordEvent(
      "config.first_run.preset",
      {{"preset", capable ? "performance_120" : "low_spec_60"},
       {"discrete", discrete ? "1" : "0"},
       {"device_local_mb", std::to_string(device_local >> 20)},
       {"logical_cores", std::to_string(cores)},
       {"refresh_hz", fmt::format("{:.0f}", refresh)}});
}
#endif

std::unique_ptr<rex::ui::ImGuiDialog> PinyonShiftApp::CreateAchievementsOverlay() {
  if (host_ui_ && host_ui_->is_open()) {
    host_ui_->Close();
  } else if (EnsureHostUi()) {
    host_ui_->Open(pinyon_shift::ui::CreateAchievementsScreen(achievements()));
  }
  return nullptr;
}

void PinyonShiftApp::OnPreLaunchModule() {
  pinyon_shift::diagnostics::RefreshCrashReporter();
  pinyon_shift::diagnostics::RecordEvent("guest.launch.begin");
  pinyon_shift::mod::NotifyModuleLaunched();
  PinyonShiftInstallRallySeriesLoader(runtime()->function_dispatcher());
  PinyonShiftInstallCarChallengeProbe(runtime()->function_dispatcher());
  // Unlocks arrive on guest threads; the toast is drawn on the UI thread.
  achievement_listener_ = achievements().RegisterNotificationCallback(
      [this](const rex::system::AchievementEvent& event) {
        if (!window()) {
          return;
        }
        window()->app_context().CallInUIThreadDeferred([this, achievement = event.achievement] {
          if (!EnsureHostUi()) {
            return;
          }
          if (!achievement_icons_ && immediate_drawer()) {
            achievement_icons_ =
                std::make_unique<rex::ui::AchievementIconCache>(immediate_drawer(), runtime());
          }
          host_ui_->ShowToast("ACHIEVEMENT UNLOCKED", achievement.label,
                              std::to_string(achievement.gamerscore) + "G",
                              achievement_icons_ ? achievement_icons_->GetIcon(achievement)
                                                 : nullptr);
        });
      });
}

void PinyonShiftApp::OnPostLaunchModule(rex::system::XThread* thread) {
  const std::string thread_id = thread ? std::to_string(thread->thread_id()) : "none";
  pinyon_shift::diagnostics::RecordEvent("guest.thread.prepared", {{"thread_id", thread_id}});
  pinyon_shift::fh1_render_test::Start(
      runtime() ? runtime()->graphics_system() : nullptr, &app_context(),
      window(), [this] { OnWindowCloseRequested(); });
}

bool PinyonShiftApp::ShouldStartModuleThread() {
  // A frame replay drives the GPU on its own; the title stays suspended.
  return rex::cvar::GetFlagByName("fh1_frame_replay").empty();
}

void PinyonShiftApp::OnGuestThreadExit(rex::system::XThread* thread) {
  const std::string thread_id = thread ? std::to_string(thread->thread_id()) : "none";
  pinyon_shift::diagnostics::RecordEvent("guest.thread.exit", {{"thread_id", thread_id}});
}

bool PinyonShiftApp::OnWindowCloseRequested() {
  // ReXGlue 0.9 deliberately hard-exits after accepting a window-close
  // request, so OnDestroy/OnShutdown are not reached on that path. Record the
  // clean qualification boundary before allowing the SDK to terminate.
  pinyon_shift::native_renderer::UninstallShaderCapture(
      runtime() ? runtime()->graphics_system() : nullptr);
  // The same hard exit skips everything OnShutdown would do for players' data
  // and mods: finish a photo, stop the backup thread, tell mods.
  pinyon_shift::mod::NotifyShutdown();
  pinyon_shift::ui::WaitForPhoto();
  save_backups_.reset();
  RecordShutdownOnce();
#ifdef PINYON_SHIFT_PGO_GENERATE
  // The SDK's hard exit skips the executable's profile atexit handler.
  const int profile_result = __llvm_profile_dump();
  pinyon_shift::diagnostics::RecordEvent(
      "pgo.profile.dump", {{"result", std::to_string(profile_result)}});
#endif
  return true;
}

void PinyonShiftApp::OnShutdown() {
  pinyon_shift::mod::NotifyShutdown();
  rex::ui::UnregisterBind("bind_game_menu");
  rex::cvar::UnregisterChangeCallbacks("pinyon_shift_hor_plus");
  PinyonShiftSetMapViewCallback(nullptr);
  if (resize_listener_added_ && window()) {
    window()->RemoveListener(&resize_listener_);
    resize_listener_added_ = false;
  }
  rex::ui::UnregisterBind("bind_fullscreen");
  rex::ui::UnregisterBind("bind_photo");
  rex::ui::UnregisterBind("bind_trainer");
  pinyon_shift::cheats::SetAppliedCallback(nullptr);
  pinyon_shift::ui::WaitForPhoto();
  PinyonShiftSetPauseSettingsHandler(nullptr);
  rex::cvar::UnregisterChangeCallbacks("d3d12_allow_variable_refresh_rate_and_tearing");
  // Before the presenter, drawer and kernel it uses are torn down.
  if (achievement_listener_ && runtime() && runtime()->kernel_state()) {
    achievements().UnregisterCallback(achievement_listener_);
    achievement_listener_ = 0;
  }
  rex::kernel::xam::SetXamUiProvider(nullptr);
  pinyon_shift::mod::SetHudChangedCallback(nullptr);
  pinyon_shift::rally::SetPaceHudChangedCallback(nullptr);
  xam_dialogs_.reset();
  host_ui_.reset();
  achievement_icons_.reset();
  save_backups_.reset();
  pinyon_shift::fh1_render_test::Stop();
  pinyon_shift::native_renderer::UninstallShaderCapture(
      runtime() ? runtime()->graphics_system() : nullptr);
  pinyon_shift::native_renderer::UninstallGuestOutputRenderer(
      runtime() ? runtime()->graphics_system() : nullptr);
  RecordShutdownOnce();
}

void PinyonShiftApp::RecordShutdownOnce() {
  if (!shutdown_recorded_.exchange(true, std::memory_order_acq_rel)) {
    pinyon_shift::diagnostics::RecordEvent("process.shutdown");
  }
}
