#include "pinyon_shift_app.h"
#include "pinyon_shift_init.h"

#define WIN32_LEAN_AND_MEAN
#include <Windows.h>

#include <filesystem>
#include <fstream>
#include <regex>
#include <sstream>
#include <string>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/perf/counter.h>
#include <rex/runtime.h>
#include <rex/system/kernel_state.h>
#include <rex/system/xthread.h>

#include "pinyon_shift_diagnostics.h"

#include <cstdio>

REXCVAR_DEFINE_UINT32(pinyon_shift_config_schema, 3, "Pinyon Shift",
                      "Pinyon Shift host configuration schema version");

namespace {

constexpr uint32_t kConfigSchema = 3;

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
              "pinyon_shift_stabilize_vehicle_presentation = false\n"
              "pinyon_shift_skip_opening_movies = false\n";
    created = true;
    return output.good();
  }

  std::ifstream input(path, std::ios::binary);
  if (!input) {
    return false;
  }
  std::ostringstream contents;
  contents << input.rdbuf();
  input.close();
  const std::string config_text = contents.str();
  const std::regex schema_pattern(
      R"((?:^|\n)\s*pinyon_shift_config_schema\s*=\s*([0-9]+)\s*(?:#.*)?(?:\r?\n|$))");
  std::smatch match;
  if (!std::regex_search(config_text, match, schema_pattern) || match.size() != 2) {
    return false;
  }
  try {
    const uint32_t schema = std::stoul(match[1].str());
    if (schema == kConfigSchema) {
      return true;
    }
    if (schema != 1 && schema != 2) {
      return false;
    }

    std::string migrated_text = config_text;
    migrated_text.replace(static_cast<size_t>(match.position(1)),
                          static_cast<size_t>(match.length(1)),
                          std::to_string(kConfigSchema));
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

    std::filesystem::path temporary = path;
    temporary += L".migrating";
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
    if (!MoveFileExW(temporary.c_str(), path.c_str(),
                     MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) {
      std::error_code error;
      std::filesystem::remove(temporary, error);
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
    ExitProcess(ERROR_NOT_SUPPORTED);
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
  paths.user_data_root = state_root / "user";
  paths.update_data_root = state_root / "update";
  paths.cache_root = state_root / "cache";
  paths.config_path = state_root / "config" / "pinyon_shift.toml";

  bool config_created = false;
  bool config_migrated = false;
  if (!EnsureSupportedConfig(paths.config_path, config_created,
                             config_migrated)) {
    diagnostics::RecordEvent("config.unsupported",
                             {{"path", paths.config_path.string()},
                              {"required_schema", std::to_string(kConfigSchema)}});
    MessageBoxW(nullptr,
                L"Pinyon Shift could not create the host configuration, or its schema is "
                L"unsupported. Remove or migrate pinyon_shift.toml before retrying.",
                L"Unsupported configuration", MB_OK | MB_ICONERROR);
    ExitProcess(ERROR_REVISION_MISMATCH);
  }

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

void PinyonShiftApp::OnPostInitLogging() {
  const std::string perf_csv = rex::cvar::GetFlagByName("perf_log_csv");
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
                        {"renderer", "d3d12"},
                        {"resolution", rex::cvar::GetFlagByName("resolution")},
                        {"vsync", rex::cvar::GetFlagByName("vsync")},
                        {"draw_resolution_scale_x",
                         rex::cvar::GetFlagByName("draw_resolution_scale_x")},
                        {"draw_resolution_scale_y",
                         rex::cvar::GetFlagByName("draw_resolution_scale_y")},
                        {"perf_csv_enabled", perf_csv.empty() ? "0" : "1"},
                        {"perf_csv", perf_csv}});
}

void PinyonShiftApp::OnPreSetup(rex::RuntimeConfig& config) {
  // ReXGlue 0.9 separates the Xenos implementation into a runtime-loaded
  // plugin. The CMake helper stages it; this selects it deliberately.
  config.gpu_plugin = "xenos";
  pinyon_shift::diagnostics::RecordEvent(
      "runtime.setup.begin",
      {{"graphics_requested", (config.graphics || !config.gpu_plugin.empty()) ? "1" : "0"},
       {"gpu_plugin", config.gpu_plugin},
       {"audio_requested", config.audio_factory ? "1" : "0"},
       {"input_requested", config.input_factory ? "1" : "0"}});
}

void PinyonShiftApp::OnPostLoadXexImage() {
  const auto title_id = runtime() && runtime()->kernel_state()
                            ? runtime()->kernel_state()->title_id()
                            : 0;
  char title[16]{};
  std::snprintf(title, sizeof(title), "%08X", title_id);
  pinyon_shift::diagnostics::RecordEvent("xex.loaded", {{"title_id", title}});
}

void PinyonShiftApp::OnPostSetup() {
  pinyon_shift::diagnostics::RefreshCrashReporter();
  pinyon_shift::diagnostics::RecordEvent(
      "runtime.setup.complete",
      {{"memory", runtime() && runtime()->memory() ? "1" : "0"},
       {"vfs", runtime() && runtime()->file_system() ? "1" : "0"},
       {"kernel", runtime() && runtime()->kernel_state() ? "1" : "0"},
       {"graphics", runtime() && runtime()->graphics_system() ? "1" : "0"},
       {"audio", runtime() && runtime()->audio_system() ? "1" : "0"},
       {"input", runtime() && runtime()->input_system() ? "1" : "0"}});
}

void PinyonShiftApp::OnPreLaunchModule() {
  pinyon_shift::diagnostics::RefreshCrashReporter();
  pinyon_shift::diagnostics::RecordEvent("guest.launch.begin");
}

void PinyonShiftApp::OnPostLaunchModule(rex::system::XThread* thread) {
  const std::string thread_id = thread ? std::to_string(thread->thread_id()) : "none";
  pinyon_shift::diagnostics::RecordEvent("guest.thread.prepared", {{"thread_id", thread_id}});
}

void PinyonShiftApp::OnGuestThreadExit(rex::system::XThread* thread) {
  const std::string thread_id = thread ? std::to_string(thread->thread_id()) : "none";
  pinyon_shift::diagnostics::RecordEvent("guest.thread.exit", {{"thread_id", thread_id}});
}

bool PinyonShiftApp::OnWindowCloseRequested() {
  // ReXGlue 0.9 deliberately hard-exits after accepting a window-close
  // request, so OnDestroy/OnShutdown are not reached on that path. Record the
  // clean qualification boundary before allowing the SDK to terminate.
  RecordShutdownOnce();
  return true;
}

void PinyonShiftApp::OnShutdown() {
  RecordShutdownOnce();
}

void PinyonShiftApp::RecordShutdownOnce() {
  if (!shutdown_recorded_.exchange(true, std::memory_order_acq_rel)) {
    pinyon_shift::diagnostics::RecordEvent("process.shutdown");
  }
}
