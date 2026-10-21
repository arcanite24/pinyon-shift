#include "ui/settings_menu.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <optional>
#include <memory>
#include <cctype>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

#include <filesystem>
#include <fstream>

#include <rex/audio/downmix.h>
#include <rex/input/dualsense.h>
#include <rex/input/pad_remap.h>
#include <rex/input/sdl/sdl_input_driver.h>
#include <rex/input/sdl/joystick_mapping.h>
#include <rex/input/sdl/wheel.h>
#if defined(__ANDROID__)
#include <rex/ui/vulkan/android_gpu_driver.h>
#endif
#include <rex/ui/vulkan/presenter.h>

#include "cheats.h"
#include "cheats_travel.h"
#include "config/default_keys.h"
#include "mod/mod_host.h"
#include "pinyon_shift_diagnostics.h"
#include "pinyon_shift_runtime_hooks.h"
#include "ui/music.h"
#include <rex/cvar.h>
#include <rex/filesystem.h>
#include <rex/logging.h>
#include <rex/ui/keybinds.h>
#include <rex/ui/virtual_key.h>

REXCVAR_DEFINE_INT32(pinyon_shift_master_volume, 100, "Pinyon Shift",
                     "Master volume, 0 to 100, applied to the output mix");

namespace pinyon_shift::ui {
namespace {

using hostui::MenuRow;
using hostui::MenuScreen;

// One choice of a setting: the label shown and the TOML literal each
// setting takes (several for choices such as the resolution scale, which
// sets both axes).
struct Choice {
  std::string label;
  std::vector<std::pair<std::string, std::string>> values;
};

std::string Unquote(std::string_view literal) {
  if (literal.size() >= 2 && literal.front() == '"' && literal.back() == '"') {
    literal = literal.substr(1, literal.size() - 2);
  }
  return std::string(literal);
}

// Whole-string number, so "-0.5" and "-0.500000" compare equal.
std::optional<double> Number(std::string_view text) {
  const std::string copy(text);
  char* end = nullptr;
  const double value = std::strtod(copy.c_str(), &end);
  if (copy.empty() || end != copy.c_str() + copy.size()) {
    return std::nullopt;
  }
  return value;
}

// An installed built-in mod (tools/build-mod-patches.py's marker) whose
// mod.toml says `always_enabled = true`; the launcher keeps it enabled.
bool AlwaysEnabledBuiltin(const std::filesystem::path& mod) {
  std::error_code error;
  if (!std::filesystem::is_regular_file(mod / ".pinyon-builtin", error)) return false;
  std::ifstream manifest(mod / "mod.toml");
  for (std::string line; std::getline(manifest, line);) {
    if (line.rfind("always_enabled", 0) == 0 && line.find("true") != std::string::npos) {
      return true;
    }
  }
  return false;
}

bool SameValue(std::string_view a, std::string_view b) {
  const auto number_a = Number(a);
  const auto number_b = Number(b);
  if (number_a && number_b) {
    return *number_a == *number_b;
  }
  return a.size() == b.size() &&
         std::equal(a.begin(), a.end(), b.begin(), [](char x, char y) {
           return std::tolower(static_cast<unsigned char>(x)) ==
                  std::tolower(static_cast<unsigned char>(y));
         });
}

// SDK lifecycle metadata covers renderer settings, including Android MSAA.
// Project settings below are consumed when the title or profile loads.
bool NeedsRestart(std::string_view name) {
  if (const auto* flag = rex::cvar::GetFlagInfo(name);
      flag && flag->lifecycle != rex::cvar::Lifecycle::kHotReload) return true;
  static constexpr std::string_view kNames[] = {
      "user_language",
      "user_country",      "pinyon_shift_cheats",      "cheat_set_profile_fields",
  };
  return std::find(std::begin(kNames), std::end(kNames), name) != std::end(kNames);
}

std::string Upper(std::string text) {
  std::transform(text.begin(), text.end(), text.begin(),
                 [](unsigned char c) { return char(std::toupper(c)); });
  return text;
}

std::string Lower(std::string text) {
  std::transform(text.begin(), text.end(), text.begin(),
                 [](unsigned char c) { return char(std::tolower(c)); });
  return text;
}

// present_effect values the presenter runs through a temporal upscaler
// provider; it falls back to FSR 1 when the provider can't run.
bool IsTemporalEffect(std::string_view effect) {
  return SameValue(effect, "fsr2") || SameValue(effect, "fsr3") || SameValue(effect, "dlss");
}

std::string TemporalUpscalerLabel(std::string_view id) {
  return SameValue(id, "fsr2")   ? "FSR 2"
         : SameValue(id, "fsr3") ? "FSR 3"
         : SameValue(id, "dlss") ? "DLSS"
                                 : Upper(std::string(id));
}

// Screens of one opening of the menu. The root screen's rows own the pages
// (every other screen sits above the root on the host UI's stack), so each
// function here may capture `this`.
class SettingsPages : public std::enable_shared_from_this<SettingsPages> {
 public:
  SettingsPages(hostui::HostUi& host_ui, config::HostConfig& config, SettingsServices services)
      : host_ui_(host_ui), config_(config), services_(std::move(services)) {}

  std::unique_ptr<MenuScreen> Root();

 private:
  // The value the game started with (what is live for restart settings).
  static std::string Live(const std::string& name) { return rex::cvar::GetFlagByName(name); }
  // The saved value, or the live one when the file does not set it.
  std::string Saved(const std::string& name) const {
    return config_.Get(name).value_or(Live(name));
  }

  static int Find(const std::vector<Choice>& choices, auto&& lookup) {
    for (size_t i = 0; i < choices.size(); ++i) {
      bool all = true;
      for (const auto& [name, literal] : choices[i].values) {
        all = all && SameValue(lookup(name), Unquote(literal));
      }
      if (all) {
        return int(i);
      }
    }
    return -1;
  }

  // A row needs a restart only for the settings in NeedsRestart; the rest of
  // a choice applies at once.
  MenuRow Setting(std::string label, std::vector<Choice> choices);
  MenuRow Toggle(std::string label, std::string name, bool inverted = false);
  // What the renderer draws and what reaches the window, for the display
  // and graphics pages' notes.
  std::string ResolutionLine() const;
  // Whether the presenter lists this temporal upscaler as able to run.
  bool TemporalUpscalerAvailable(std::string_view id) const {
    if (!services_.upscalers) return false;
    for (const rex::ui::UpscalerInfo& info : services_.upscalers()) {
      if (SameValue(info.id, id)) return info.available;
    }
    return false;
  }
  MenuRow Page(std::string label, std::unique_ptr<MenuScreen> (SettingsPages::*page)());
  std::function<std::string()> RestartNote(std::vector<MenuRow>& rows);
  void Save();
  // enabled_mods as saved (applied at the next start), and one mod switched.
  std::vector<std::string> EnabledMods() const;
  void SetModEnabled(const std::string& name, bool enabled);
  // One of the built-in mods (mods_src/builtin), when the launcher
  // installed it.
  bool BuiltinModInstalled(const std::string& name) const;

  std::unique_ptr<MenuScreen> Display();
  std::unique_ptr<MenuScreen> CameraEditor();
  std::unique_ptr<MenuScreen> HdrCalibration();
  std::unique_ptr<MenuScreen> Graphics();
  std::unique_ptr<MenuScreen> Audio();
  std::unique_ptr<MenuScreen> Controls();
  std::unique_ptr<MenuScreen> Wheel();
  std::unique_ptr<MenuScreen> DualSense();
  std::unique_ptr<MenuScreen> Hud();
  std::unique_ptr<MenuScreen> Gameplay();
  std::unique_ptr<MenuScreen> Profile();
  std::unique_ptr<MenuScreen> Gamertag();
  std::unique_ptr<MenuScreen> Backups();
  std::unique_ptr<MenuScreen> ControllerButtons();
  std::unique_ptr<MenuScreen> MapController();
  std::unique_ptr<MenuScreen> MapControllerOptions(rex::input::sdl::JoystickInfo joystick);
  std::unique_ptr<MenuScreen> MapControllerSteps(rex::input::sdl::JoystickInfo joystick);
  std::unique_ptr<MenuScreen> Mods();
  std::unique_ptr<MenuScreen> Cheats();
  std::unique_ptr<MenuScreen> ModActions();
  std::unique_ptr<MenuScreen> Rally();
  std::unique_ptr<MenuScreen> ConfirmRallyRetirement();

 public:
  std::unique_ptr<MenuScreen> Trainer();

 private:
  std::unique_ptr<MenuScreen> TrainerPlayer();
  std::unique_ptr<MenuScreen> TrainerWorld();
  std::unique_ptr<MenuScreen> TrainerVehicle();
  std::unique_ptr<MenuScreen> TrainerGraphics();
  std::unique_ptr<MenuScreen> TrainerDebug();
  std::unique_ptr<MenuScreen> ConfirmRestore(std::string slot);
  static constexpr size_t kMaxGamertag = 15;

  hostui::HostUi& host_ui_;
  config::HostConfig& config_;
  SettingsServices services_;
};

MenuRow SettingsPages::Setting(std::string label, std::vector<Choice> choices) {
  MenuRow row;
  row.label = std::move(label);
  // The badge shows when choosing between the choices needs a restart; a
  // row whose choices all keep the same restart setting (the presets'
  // Vulkan) is marked only while a saved change is pending.
  bool restart = false;
  for (const auto& choice : choices) {
    for (const auto& [name, literal] : choice.values) {
      if (!NeedsRestart(name)) {
        continue;
      }
      restart = true;
      for (const auto& other : choices) {
        const auto same = std::find_if(other.values.begin(), other.values.end(),
                                       [&](const auto& value) {
                                         return value.first == name &&
                                                SameValue(value.second, literal);
                                       });
        row.restart_required = row.restart_required || same == other.values.end();
      }
    }
  }
  auto shared = std::make_shared<std::vector<Choice>>(std::move(choices));
  row.value = [this, shared] {
    const int index = Find(*shared, [this](const std::string& name) { return Saved(name); });
    return index >= 0 ? (*shared)[size_t(index)].label : std::string("CUSTOM");
  };
  row.adjust = [this, shared, label = row.label](int direction) {
    const auto& choices = *shared;
    const int count = int(choices.size());
    const int current = Find(choices, [this](const std::string& name) { return Saved(name); });
    const int next = current < 0 ? 0 : (current + direction + count) % count;
    // A crash report then shows what was changed just before (#542).
    std::string values;
    for (const auto& [name, literal] : choices[size_t(next)].values) {
      config_.Set(name, literal);
      if (!NeedsRestart(name)) {
        rex::cvar::SetFlagByName(name, Unquote(literal));
      }
      values += (values.empty() ? "" : " ") + name + "=" + Unquote(literal);
    }
    diagnostics::RecordEvent("settings.changed", {{"row", label},
                                                  {"choice", choices[size_t(next)].label},
                                                  {"values", values}});
    Save();
  };
  if (restart) {
    row.restart_pending = [this, shared] {
      for (const auto& choice : *shared) {
        for (const auto& [name, literal] : choice.values) {
          if (NeedsRestart(name) && !SameValue(Unquote(Saved(name)), Live(name))) {
            return true;
          }
        }
      }
      return false;
    };
  }
  return row;
}

MenuRow SettingsPages::Toggle(std::string label, std::string name, bool inverted) {
  const char* on = inverted ? "false" : "true";
  const char* off = inverted ? "true" : "false";
  return Setting(std::move(label), {{"OFF", {{name, off}}}, {"ON", {{name, on}}}});
}

MenuRow SettingsPages::Page(std::string label,
                            std::unique_ptr<MenuScreen> (SettingsPages::*page)()) {
  MenuRow row;
  row.label = std::move(label);
  row.activate = [self = shared_from_this(), page] { self->host_ui_.Push(((*self).*page)()); };
  return row;
}

std::function<std::string()> SettingsPages::RestartNote(std::vector<MenuRow>& rows) {
  std::vector<std::function<bool()>> pending;
  for (const MenuRow& row : rows) {
    if (row.restart_pending) {
      pending.push_back(row.restart_pending);
    }
  }
  if (pending.empty()) {
    return nullptr;
  }
  return [pending] {
    for (const auto& check : pending) {
      if (check()) {
        return std::string("RESTART THE GAME TO APPLY THE MARKED CHANGES");
      }
    }
    return std::string();
  };
}

std::string SettingsPages::ResolutionLine() const {
  const auto number = [](const std::string& text, uint32_t fallback) {
    const auto value = Number(text);
    return value && *value >= 1 ? uint32_t(*value) : fallback;
  };
  uint32_t scale = services_.draw_resolution_scale ? services_.draw_resolution_scale() : 0;
  if (!scale) {
    scale = number(Unquote(Saved("draw_resolution_scale_x")), 1);
  }
  const uint32_t render_width = number(Live("video_mode_width"), 1280) * scale;
  const uint32_t render_height = number(Live("video_mode_height"), 720) * scale;
  const auto size = [](uint32_t width, uint32_t height) {
    return std::to_string(width) + "X" + std::to_string(height);
  };
  std::string line = "RENDERS " + size(render_width, render_height);
  const auto output = services_.output_size ? services_.output_size() : std::nullopt;
  if (!output || !output->first || !output->second) {
    return line;
  }
  const auto [output_width, output_height] = *output;
  if (output_width == render_width && output_height == render_height) {
    return line + ", SHOWN AT THAT SIZE";
  }
  const std::string effect = Unquote(Saved("present_effect"));
  const char* upscaler = SameValue(effect, "fsr")    ? ", FSR 1 UPSCALES TO "
                         : SameValue(effect, "fsr2") ? ", FSR 2 UPSCALES TO "
                         : SameValue(effect, "fsr3") ? ", FSR 3 UPSCALES TO "
                         : SameValue(effect, "dlss") ? ", DLSS UPSCALES TO "
                                                     : ", STRETCHED TO ";
  // A temporal upscaler the build lacks or whose runtime didn't load runs
  // as FSR 1 (#762): say so instead of naming the one that was chosen.
  std::string unavailable;
  if (IsTemporalEffect(effect) && !TemporalUpscalerAvailable(effect)) {
    upscaler = ", FSR 1 UPSCALES TO ";
    unavailable = " (" + TemporalUpscalerLabel(effect) + " UNAVAILABLE)";
  }
  if (output_width * output_height > render_width * render_height) {
    return line + upscaler + size(output_width, output_height) + unavailable;
  }
  return line + ", DOWNSCALED TO " + size(output_width, output_height);
}

void SettingsPages::Save() {
  if (!config_.Save()) {
    REXLOG_ERROR("Settings: could not write {}", rex::path_to_utf8(config_.path()));
  }
}

std::unique_ptr<MenuScreen> SettingsPages::Display() {
  std::vector<MenuRow> rows;
  // An Android activity is always full screen on its one display.
#if !defined(__ANDROID__)
  rows.push_back(Toggle("FULLSCREEN", "fullscreen"));
  rows.push_back(Setting("MONITOR",
                         {{"DEFAULT", {{"monitor", "0"}}},
                          {"1", {{"monitor", "1"}}},
                          {"2", {{"monitor", "2"}}},
                          {"3", {{"monitor", "3"}}}}));
  std::vector<Choice> sizes = {{"DEFAULT", {{"window_width", "0"}, {"window_height", "0"}}}};
  for (const auto& [width, height] : {std::pair{1280, 720}, std::pair{1600, 900},
                                      std::pair{1920, 1080}, std::pair{2560, 1440},
                                      std::pair{3840, 2160}}) {
    sizes.push_back({std::to_string(width) + "X" + std::to_string(height),
                     {{"window_width", std::to_string(width)},
                      {"window_height", std::to_string(height)}}});
  }
  rows.push_back(Setting("WINDOW SIZE", std::move(sizes)));
#endif
  // Letterbox keeps the guest's aspect with bars, crop fills the window by
  // cutting into the title's overscan margin, stretch fills it by scaling.
  rows.push_back(Setting("ASPECT RATIO",
                         {{"LETTERBOX", {{"present_letterbox", "true"},
                                         {"present_allow_overscan_cutoff", "false"}}},
                          {"CROP", {{"present_letterbox", "true"},
                                    {"present_allow_overscan_cutoff", "true"}}},
                          {"STRETCH", {{"present_letterbox", "false"},
                                       {"present_allow_overscan_cutoff", "false"}}}}));
  // Hor+ (NP-4.4): the title renders the window's wider aspect into its 16:9
  // image, stretched to fill the window; the HUD stretches with it.
  rows.push_back(Setting("ULTRAWIDE",
                         {{"OFF", {{"pinyon_shift_hor_plus", "false"}}},
                          {"WIDER VIEW", {{"pinyon_shift_hor_plus", "true"},
                                          {"present_letterbox", "false"},
                                          {"present_allow_overscan_cutoff", "false"}}}}));
  // Every camera's vertical field of view, applied at once (NP-4.4).
  {
    std::vector<Choice> fov;
    for (const char* value : {"0.9", "1.0", "1.1", "1.2", "1.3"}) {
      const int percent = int(std::lround(std::stod(value) * 100));
      fov.push_back({std::to_string(percent) + "%", {{"pinyon_shift_fov_scale", value}}});
    }
    rows.push_back(Setting("FIELD OF VIEW", std::move(fov)));
  }
  rows.push_back(Page("CAMERA EDITOR", &SettingsPages::CameraEditor));
  // G-forces, lean, speed shake and head motion layered on the game's own
  // camera physics (#419), from the built-in immersive_camera mod, which
  // always loads. Its effect groups scale while the game runs (#443): a
  // preset sets all four, and changing one shows CUSTOM. Lean, shake and
  // head motion are on the cockpit and hood cameras only.
  if (BuiltinModInstalled("immersive_camera")) {
    const std::string_view groups[] = {"pinyon_shift_camera_gforce", "pinyon_shift_camera_lean",
                                       "pinyon_shift_camera_shake", "pinyon_shift_camera_head"};
    std::vector<Choice> presets;
    for (const auto& [label, value] : {std::pair{"OFF", "0.0"}, std::pair{"SUBTLE", "0.5"},
                                       std::pair{"DEFAULT", "1.0"}, std::pair{"STRONG", "1.5"}}) {
      Choice preset{label, {}};
      for (const auto group : groups) preset.values.push_back({std::string(group), value});
      presets.push_back(std::move(preset));
    }
    rows.push_back(Setting("IMMERSIVE CAMERA", std::move(presets)));
    const char* labels[] = {"CAMERA G-FORCE", "CAMERA LEAN", "CAMERA SPEED SHAKE",
                            "CAMERA HEAD MOTION"};
    for (size_t i = 0; i < std::size(groups); ++i) {
      std::vector<Choice> amounts;
      for (int percent = 0; percent <= 200; percent += 25) {
        char value[16];
        std::snprintf(value, sizeof(value), "%.2f", percent / 100.0);
        amounts.push_back({std::to_string(percent) + "%", {{std::string(groups[i]), value}}});
      }
      rows.push_back(Setting(labels[i], std::move(amounts)));
    }
  }
  rows.push_back(Toggle("VSYNC", "vsync"));
  rows.push_back(Setting("FRAME RATE LIMIT",
                         {{"OFF", {{"host_present_fps_limit", "0"}}},
                          {"30", {{"host_present_fps_limit", "30"}}},
                          {"60", {{"host_present_fps_limit", "60"}}},
                          {"120", {{"host_present_fps_limit", "120"}}},
                          {"240", {{"host_present_fps_limit", "240"}}}}));
  // How the rendered image is scaled to the window: FSR 1 and CAS keep 2x
  // on a 4K display and 3x on 1440p sharp where bilinear blurs. The page's
  // note gives both sizes. Temporal upscalers (UP-8.1) are offered when
  // their runtime loaded, or while one is set; they use the game's depth,
  // motion and a jittered scene, and RESOLUTION SCALE is their render size.
  {
    std::vector<Choice> scaling = {{"BILINEAR", {{"present_effect", "\"bilinear\""}}},
                                   {"CAS", {{"present_effect", "\"cas\""}}},
                                   {"FSR 1", {{"present_effect", "\"fsr\""}}}};
    const std::string saved_effect = Unquote(Saved("present_effect"));
    std::vector<rex::ui::UpscalerInfo> upscalers =
        services_.upscalers ? services_.upscalers() : std::vector<rex::ui::UpscalerInfo>{};
    // The presenter lists its preferred provider first; the menu goes in
    // version order (FSR 2 before FSR 3).
    std::stable_sort(upscalers.begin(), upscalers.end(),
                     [](const auto& a, const auto& b) { return a.id < b.id; });
    bool saved_listed = false;
    for (const rex::ui::UpscalerInfo& info : upscalers) {
      if (info.kind != rex::ui::UpscalerKind::kTemporal ||
          (!info.available && !SameValue(saved_effect, info.id))) {
        continue;
      }
      saved_listed = saved_listed || SameValue(saved_effect, info.id);
      std::string label = TemporalUpscalerLabel(info.id);
      if (!info.available) label += " (UNAVAILABLE)";
      scaling.push_back({label, {{"present_effect", "\"" + info.id + "\""}}});
    }
    // Set in the launcher or the config for a build without it (DLSS on
    // Linux and macOS): still show the setting, as unavailable.
    if (IsTemporalEffect(saved_effect) && !saved_listed) {
      scaling.push_back({TemporalUpscalerLabel(saved_effect) + " (UNAVAILABLE)",
                         {{"present_effect", "\"" + Lower(saved_effect) + "\""}}});
    }
    rows.push_back(Setting("OUTPUT SCALING", std::move(scaling)));
  }
  // FSR 1's RCAS and the temporal upscalers' own sharpening, in stops of
  // reduction (the temporal sharpness is 1 - reduction / 2).
  rows.push_back(Setting("SHARPENING", {{"OFF", {{"present_fsr_sharpness_reduction", "2.0"}}},
                                        {"LOW", {{"present_fsr_sharpness_reduction", "1.0"}}},
                                        {"MEDIUM", {{"present_fsr_sharpness_reduction", "0.5"}}},
                                        {"HIGH", {{"present_fsr_sharpness_reduction", "0.2"}}},
                                        {"MAX", {{"present_fsr_sharpness_reduction", "0.0"}}}}));
  // HDR output (#417, #442): the image on an HDR (scRGB) swapchain with its
  // white at the paper white, so an HDR desktop does not wash it out, and the
  // scene's highlights (not the HUD or menus) expanded towards the display's
  // peak. All of it applies at once. Offered when the display has HDR on, or
  // while it is set.
#if defined(_WIN32)
  // Windows HDR on for the game's display while it runs and back off when it
  // closes; ON also turns the game's HDR output on (a display already in HDR
  // stays on).
  rows.push_back(Setting("WINDOWS HDR", {{"OFF", {{"pinyon_shift_windows_hdr", "false"}}},
                                         {"ON", {{"pinyon_shift_windows_hdr", "true"},
                                                 {"present_hdr", "true"}}}}));
#endif
  const rex::ui::vulkan::HdrOutputState hdr = rex::ui::vulkan::GetHdrOutputState();
  if (hdr.offered || hdr.active || SameValue(Unquote(Saved("present_hdr")), "true")) {
    rows.push_back(Toggle("HDR", "present_hdr"));
    std::vector<Choice> paper_white;
    for (const char* nits : {"100", "150", "200", "250", "300", "400"}) {
      paper_white.push_back(
          {std::string(nits) + " NITS", {{"present_hdr_paper_white_nits", nits}}});
    }
    rows.push_back(Setting("HDR PAPER WHITE", std::move(paper_white)));
    // How far SDR white in the scene goes from the paper white towards the
    // display's peak (set by the calibration).
    rows.push_back(Setting("HDR HIGHLIGHTS", {{"OFF", {{"present_hdr_highlights", "0.0"}}},
                                              {"LOW", {{"present_hdr_highlights", "0.25"}}},
                                              {"MEDIUM", {{"present_hdr_highlights", "0.5"}}},
                                              {"HIGH", {{"present_hdr_highlights", "1.0"}}}}));
    // 2.2 matches what an SDR monitor shows; sRGB's linear toe lifts the
    // blacks and washes the colors out.
    rows.push_back(Setting("HDR GAMMA", {{"2.2", {{"present_hdr_gamma", "2.2"}}},
                                         {"2.4", {{"present_hdr_gamma", "2.4"}}},
                                         {"SRGB", {{"present_hdr_gamma", "0.0"}}}}));
    // The SDR image on the left, the HDR one on the right; not saved.
    {
      MenuRow compare;
      compare.label = "HDR COMPARE";
      compare.value = [] {
        return std::string(rex::cvar::GetFlagByName("present_hdr_compare") == "true"
                               ? "SDR | HDR"
                               : "OFF");
      };
      compare.adjust = [](int) {
        const bool on = rex::cvar::GetFlagByName("present_hdr_compare") == "true";
        rex::cvar::SetFlagByName("present_hdr_compare", on ? "false" : "true");
      };
      rows.push_back(std::move(compare));
    }
    rows.push_back(Page("HDR CALIBRATION", &SettingsPages::HdrCalibration));
  }
  // The rate the game simulates and renders at, which sets every CPU cost
  // (LS-1.4). DISPLAY follows the refresh rate: 144 Hz and faster displays
  // then render that many frames. 40 is an even third of 120 Hz (LS-1.6).
  rows.push_back(Setting("GAME FRAME RATE LIMIT",
                         {{"DISPLAY", {{"pinyon_shift_fh1_render_fps_limit", "0"}}},
                          {"30", {{"pinyon_shift_fh1_render_fps_limit", "30"}}},
                          {"40", {{"pinyon_shift_fh1_render_fps_limit", "40"}}},
                          {"60", {{"pinyon_shift_fh1_render_fps_limit", "60"}}},
                          {"120", {{"pinyon_shift_fh1_render_fps_limit", "120"}}}}));
  rows.push_back(Page("HUD", &SettingsPages::Hud));
  auto note = [this, restart = RestartNote(rows)] {
    const std::string pending = restart ? restart() : std::string();
    if (!pending.empty()) {
      return pending;
    }
    // A presentation limit below the game's drops frames the game rendered.
    const auto present = Number(Unquote(Saved("host_present_fps_limit")));
    const auto game = Number(Unquote(Saved("pinyon_shift_fh1_render_fps_limit")));
    if (present && *present > 0 && game && (*game == 0 || *game > *present)) {
      return std::string("THE GAME RENDERS FRAMES THE FRAME RATE LIMIT DROPS");
    }
    if (SameValue(Unquote(Saved("present_hdr")), "true") &&
        !rex::ui::vulkan::GetHdrOutputState().offered) {
      return std::string("HDR NEEDS HDR TURNED ON FOR THIS DISPLAY");
    }
    return ResolutionLine();
  };
  return std::make_unique<MenuScreen>("DISPLAY", std::move(rows), std::move(note));
}

std::unique_ptr<MenuScreen> SettingsPages::CameraEditor() {
  std::vector<MenuRow> rows;
  for (const auto& [label, key, first, last] : {
           std::tuple{"CHASE HEIGHT", "pinyon_shift_chase_height", -2, 6},
           std::tuple{"CHASE DISTANCE", "pinyon_shift_chase_distance", -4, 12}}) {
    std::vector<Choice> choices;
    for (int step = first; step <= last; ++step) {
      char value[16], text[24];
      std::snprintf(value, sizeof(value), "%.2f", step * 0.25);
      std::snprintf(text, sizeof(text), "%+.2f M", step * 0.25);
      choices.push_back({step == 0 ? "DEFAULT" : text, {{key, value}}});
    }
    rows.push_back(Setting(label, std::move(choices)));
  }
  for (const auto& [label, key, first, last, increment] : {
           std::tuple{"CHASE FIELD OF VIEW", "pinyon_shift_chase_fov", 80, 130, 5},
           std::tuple{"CHASE STIFFNESS", "pinyon_shift_chase_stiffness", 50, 200, 25}}) {
    std::vector<Choice> choices;
    for (int percent = first; percent <= last; percent += increment) {
      char value[16];
      std::snprintf(value, sizeof(value), "%.2f", percent / 100.0);
      choices.push_back({percent == 100 ? "DEFAULT" : std::to_string(percent) + "%", {{key, value}}});
    }
    rows.push_back(Setting(label, std::move(choices)));
  }
  rows.push_back(Setting("DRIVING VIEW",
      {{"NORMAL", {{"pinyon_shift_drive_camera", "0"}}},
       {"WHEEL", {{"pinyon_shift_drive_camera", "10"}}},
       {"REPLAY", {{"pinyon_shift_drive_camera", "15"}}}}));
  MenuRow reset;
  reset.label = "RESET CAMERA EDITOR";
  reset.activate = [this] {
    for (const auto& [key, value] : {
             std::pair{"pinyon_shift_chase_height", "0.0"},
             std::pair{"pinyon_shift_chase_distance", "0.0"},
             std::pair{"pinyon_shift_chase_fov", "1.0"},
             std::pair{"pinyon_shift_chase_stiffness", "1.0"},
             std::pair{"pinyon_shift_drive_camera", "0"}}) {
      config_.Set(key, value);
      rex::cvar::SetFlagByName(key, value);
    }
    Save();
  };
  rows.push_back(std::move(reset));
  return std::make_unique<MenuScreen>("CAMERA EDITOR", std::move(rows), [] {
    return std::string("APPLIES LIVE TO BOTH CHASE VIEWS. OFFSETS ARE RELATIVE TO CAMERA DATA.");
  });
}

std::unique_ptr<MenuScreen> SettingsPages::HdrCalibration() {
  // Test patterns the HDR pass draws under the menu (#442), in three steps:
  // the TV's own brightness for the blacks, then the paper white, then the
  // display's peak, which the highlights expand towards. The pattern is
  // never saved; leaving the page removes it.
  auto step = std::make_shared<int>(1);
  const auto show = [](int pattern) {
    rex::cvar::SetFlagByName("present_hdr_test_pattern", std::to_string(pattern));
  };
  show(*step);
  std::vector<MenuRow> rows;
  {
    MenuRow pattern;
    pattern.label = "STEP";
    pattern.value = [step] {
      static constexpr const char* kSteps[] = {"1 BLACK LEVEL", "2 PAPER WHITE", "3 PEAK"};
      return std::string(kSteps[*step - 1]);
    };
    pattern.adjust = [step, show](int direction) {
      *step = (*step - 1 + (direction < 0 ? 2 : 1)) % 3 + 1;
      show(*step);
    };
    rows.push_back(std::move(pattern));
  }
  {
    std::vector<Choice> paper_white;
    for (int nits = 80; nits <= 500; nits += 10) {
      paper_white.push_back({std::to_string(nits) + " NITS",
                             {{"present_hdr_paper_white_nits", std::to_string(nits)}}});
    }
    MenuRow row = Setting("PAPER WHITE", std::move(paper_white));
    row.enabled = [step] { return *step == 2; };
    rows.push_back(std::move(row));
  }
  {
    std::vector<Choice> peak;
    for (int nits = 300; nits <= 4000; nits += nits < 1500 ? 50 : 100) {
      peak.push_back(
          {std::to_string(nits) + " NITS", {{"present_hdr_peak_nits", std::to_string(nits)}}});
    }
    MenuRow row = Setting("PEAK", std::move(peak));
    row.enabled = [step] { return *step == 3; };
    rows.push_back(std::move(row));
  }
  auto note = [step] {
    switch (*step) {
      case 1:
        return std::string("TV BRIGHTNESS: FIRST SQUARE BLACK, SECOND JUST SHOWS");
      case 2:
        return std::string("THE WHITE SQUARE SHOULD LOOK LIKE WHITE PAPER");
      default:
#if defined(__ANDROID__)
        return std::string("RAISE UNTIL SQUARE DISAPPEARS; IF IT STAYS VISIBLE, KEEP YOUR PEAK");
#else
        return std::string("RAISE THE PEAK UNTIL THE SQUARE DISAPPEARS");
#endif
    }
  };
  auto screen = std::make_unique<MenuScreen>("HDR CALIBRATION", std::move(rows), std::move(note));
  // The patterns' band (hdr_output.ps.glsl kPatternTop and kPatternBottom).
  screen->set_backdrop_gap(0.62f, 0.88f);
  screen->set_on_back([show] { show(0); });
  return screen;
}

std::unique_ptr<MenuScreen> SettingsPages::Graphics() {
  std::vector<MenuRow> rows;
  // PB-5: whole setups at once; any other combination reads CUSTOM. All
  // render on Vulkan with the split GPU commands thread.
#if defined(__ANDROID__)
  // AP-7.5: a handheld renders at 1x (AP-2.5) and trades frame rate for
  // battery and heat. QUALITY 30 is the Xbox 360's own rate (the guest
  // vblank at 60 Hz) with the game's 4x MSAA and shadows; SMOOTH 60 doubles
  // it with 2X MSAA and no shadows: on the Odin 2 Portal (Turnip Gen8 V37)
  // that holds 60 fps in free roam (p95 16.9 ms, about 15.4 ms of GPU a
  // frame since the EDRAM passes were specialized), where 4x with shadows
  // takes about 26 ms. Both draw FH1's tiles in one pass and
  // redraw the reflection cubemap at a quarter of the game's rate (no
  // visible change), scale to the panel bilinearly and keep the game's own
  // anisotropic filtering: FSR 1 at the panel's 2400x1504 cost 1.4 ms a
  // frame and forced 4x anisotropy 0.4 ms, measured by alternating each in
  // one run.
  // ULTRA LOW 30 (#515), for entry-level phones: QUALITY 30's rate without
  // MSAA or shadows, and textures at most 256 texels across (TEXTURE SIZE).
  rows.push_back(Setting("GRAPHICS PRESET",
                         {{"ULTRA LOW 30",
                           {{"gpu_backend", "\"vulkan\""},
                            {"gpu_record_thread", "true"},
                            {"draw_resolution_scale_x", "1"},
                            {"draw_resolution_scale_y", "1"},
                            {"present_effect", "\"bilinear\""},
                            {"anisotropic_override", "-1"},
                            {"fh1_msaa_single_sample", "true"},
                            {"fh1_msaa_2x", "false"},
                            {"fh1_untile_predicated_tiling", "true"},
                            {"pinyon_shift_fh1_env_map_rate", "0.25"},
                            {"pinyon_shift_fh1_shadows", "false"},
                            {"vulkan_texture_max_size", "256"},
                            {"host_present_fps_limit", "0"},
                            {"pinyon_shift_fh1_render_fps_limit", "30"}}},
                          {"QUALITY 30",
                           {{"gpu_backend", "\"vulkan\""},
                            {"gpu_record_thread", "true"},
                            {"draw_resolution_scale_x", "1"},
                            {"draw_resolution_scale_y", "1"},
                            {"present_effect", "\"bilinear\""},
                            {"anisotropic_override", "-1"},
                            {"fh1_msaa_single_sample", "false"},
                            {"fh1_msaa_2x", "false"},
                            {"fh1_untile_predicated_tiling", "true"},
                            {"pinyon_shift_fh1_env_map_rate", "0.25"},
                            {"pinyon_shift_fh1_shadows", "true"},
                            {"vulkan_texture_max_size", "0"},
                            {"host_present_fps_limit", "0"},
                            {"pinyon_shift_fh1_render_fps_limit", "30"}}},
                          {"SMOOTH 60",
                           {{"gpu_backend", "\"vulkan\""},
                            {"gpu_record_thread", "true"},
                            {"draw_resolution_scale_x", "1"},
                            {"draw_resolution_scale_y", "1"},
                            {"present_effect", "\"bilinear\""},
                            {"anisotropic_override", "-1"},
                            {"fh1_msaa_single_sample", "false"},
                            {"fh1_msaa_2x", "true"},
                            {"fh1_untile_predicated_tiling", "true"},
                            {"pinyon_shift_fh1_env_map_rate", "0.25"},
                            {"pinyon_shift_fh1_shadows", "false"},
                            {"vulkan_texture_max_size", "0"},
                            {"host_present_fps_limit", "0"},
                            {"pinyon_shift_fh1_render_fps_limit", "60"}}}}));
  // The game's 4x MSAA is most of a handheld GPU's frame: off, edges are
  // harder and the frame much cheaper.
  // Labelled apart from the FXAA row (POST-PROCESS AA) below.
  // 2X stores the game's 4x surfaces with two samples each (Vulkan): on the
  // Odin 2 Portal 16.2 ms of GPU a frame against 18.7 at 4X and 15.2 OFF.
  rows.push_back(Setting("MSAA", {{"4X", {{"fh1_msaa_single_sample", "false"},
                                          {"fh1_msaa_2x", "false"}}},
                                  {"2X", {{"fh1_msaa_single_sample", "false"},
                                          {"fh1_msaa_2x", "true"}}},
                                  {"OFF", {{"fh1_msaa_single_sample", "true"}}}}));
  // COARSE shades the scene and the shadow mask once per 2x2 pixels
  // (VK_KHR_fragment_shading_rate; alpha-to-coverage draws stay per pixel,
  // alpha-tested foliage steps its edges by the block): surfaces a little
  // softer, geometry edges unchanged. On the Odin 2 Portal about 1.1 ms of
  // GPU a frame at 1x with shadows and 2 ms at 4X, foliage 0.25 ms more.
  // Applies on the next frame.
  rows.push_back(Setting(
      "SCENE SHADING",
      {{"FULL", {{"fh1_coarse_shading", "\"\""}, {"fh1_coarse_shading_alpha_test", "false"}}},
       {"COARSE",
        {{"fh1_coarse_shading", "\"1024/32/4x/d1+0/32/4x/c3=2x2,0/16/1x/d1+720/16/1x/c0=2x2\""},
         {"fh1_coarse_shading_alpha_test", "true"}}}}));
  // FAST samples the game's gamma textures through sRGB views instead of
  // converting them with the console's curve in every shader: terrain and
  // foliage a little darker, about 0.4 ms of GPU a frame on the Odin 2
  // Portal with shadows. Applies at the next start.
  rows.push_back(Setting("TEXTURE GAMMA", {{"ACCURATE", {{"texture_gamma_host_srgb", "false"}}},
                                           {"FAST", {{"texture_gamma_host_srgb", "true"}}}}));
  // The Vulkan driver loaded at the next start: AUTO is the one recommended
  // for the GPU (Mesa Turnip Gen8 V37, bundled, on Adreno 7xx), SYSTEM the
  // device's own, and every package under state/drivers (bundled or
  // imported) by its folder name.
  {
    std::vector<Choice> drivers = {{"AUTO", {{"android_gpu_driver", "\"auto\""}}},
                                   {"SYSTEM", {{"android_gpu_driver", "\"\""}}}};
    if (const char* root = std::getenv("REX_ANDROID_DRIVERS_DIR")) {
      std::vector<std::string> names;
      std::error_code error;
      for (auto it = std::filesystem::directory_iterator(root, error);
           !error && it != std::filesystem::directory_iterator(); it.increment(error)) {
        const std::string name = rex::path_to_utf8(it->path().filename());
        if (it->is_directory(error) && !name.empty() && name[0] != '.') names.push_back(name);
      }
      std::sort(names.begin(), names.end());
      for (const auto& name : names) {
        drivers.push_back({Upper(name), {{"android_gpu_driver", config::Quote(name)}}});
      }
    }
    rows.push_back(Setting("GPU DRIVER", std::move(drivers)));
    // An adrenotools package (.zip with meta.json and the driver .so) from
    // the system's file picker, unpacked into state/drivers; it then shows
    // in GPU DRIVER the next time this page opens.
    MenuRow import;
    import.label = "IMPORT DRIVER (.ZIP)";
    import.activate = [] { rex::ui::vulkan::CallAndroidActivityMethod("importGpuDriver"); };
    rows.push_back(std::move(import));
  }
#else
  // LOW-SPEC 60 and BALANCED 40 (LS-1.1, LS-1.6) choose the cheapest
  // workload on purpose for weaker machines: the console's own resolution,
  // no MSAA (a quarter of the target memory and much of a small GPU's frame),
  // bilinear output, the game's own filtering and no FXAA. The game's rate
  // sets every CPU cost, so 60 is half the work a second of 120 and 40 a
  // third; 40 paces evenly on 120 Hz displays and the Steam Deck's 40 Hz mode.
  // Every preset clears the presentation limit, so the frames the game
  // renders are the frames shown.
  // ULTRA LOW 30 (#515) is for machines below that: also no shadows (about
  // 6 ms a frame on the Odin 2 Portal), the reflection cubemap at a quarter
  // rate, the scene's three tiles in one pass (about 3 ms on the Odin),
  // textures at most 256 texels across (TEXTURE SIZE, for small video
  // memory), and 30 fps, the console's own rate and half the CPU work of 60.
  // The other presets set those four back to the desktop defaults, so
  // leaving ULTRA LOW does not keep them.
  const auto preset = [](const char* scale, const char* effect, const char* msaa_off,
                         const char* fps,
                         std::vector<std::pair<std::string, std::string>> extra = {}) {
    std::vector<std::pair<std::string, std::string>> values = {
        {"gpu_backend", "\"vulkan\""},
        {"gpu_record_thread", "true"},
        {"draw_resolution_scale_x", scale},
        {"draw_resolution_scale_y", scale},
        {"present_effect", effect},
        {"fh1_msaa_single_sample", msaa_off},
        {"fh1_msaa_2x", "false"},
        {"host_present_fps_limit", "0"},
        {"pinyon_shift_fh1_render_fps_limit", fps},
        {"pinyon_shift_fh1_shadows", "true"},
        {"pinyon_shift_fh1_env_map_rate", "1"},
        {"fh1_untile_predicated_tiling", "false"},
        {"vulkan_texture_max_size", "0"}};
    for (auto& [name, value] : extra) {
      const auto it = std::find_if(values.begin(), values.end(),
                                   [&](const auto& setting) { return setting.first == name; });
      if (it != values.end()) {
        it->second = value;
      } else {
        values.emplace_back(name, value);
      }
    }
    return values;
  };
  const std::vector<std::pair<std::string, std::string>> cheapest = {
      {"anisotropic_override", "-1"}, {"swap_post_effect", "\"none\""}};
  auto ultra_low = cheapest;
  ultra_low.insert(ultra_low.end(), {{"pinyon_shift_fh1_shadows", "false"},
                                     {"pinyon_shift_fh1_env_map_rate", "0.25"},
                                     {"fh1_untile_predicated_tiling", "true"},
                                     {"vulkan_texture_max_size", "256"}});
  rows.push_back(Setting(
      "GRAPHICS PRESET",
      {{"ULTRA LOW 30", preset("1", "\"bilinear\"", "true", "30", ultra_low)},
       {"LOW-SPEC 60", preset("1", "\"bilinear\"", "true", "60", cheapest)},
       {"BALANCED 40", preset("1", "\"bilinear\"", "true", "40", cheapest)},
       // The reference desktop (Ryzen 7 5800X, RTX 4080) holds the 120 limit
       // in the race at 1x (8.3 ms median) and runs it at 9.5 ms at 3x.
       {"PERFORMANCE 120", preset("1", "\"fsr\"", "true", "120")},
       {"QUALITY 60", preset("2", "\"bilinear\"", "false", "60")}}));
  // The game's 4x MSAA, apart from the post-process FXAA row below: off,
  // edges are harder and targets take a quarter of the memory.
  // 2X stores the game's 4x surfaces with two samples each (Vulkan): on the
  // Odin 2 Portal 16.2 ms of GPU a frame against 18.7 at 4X and 15.2 OFF.
  rows.push_back(Setting("MSAA", {{"4X", {{"fh1_msaa_single_sample", "false"},
                                          {"fh1_msaa_2x", "false"}}},
                                  {"2X", {{"fh1_msaa_single_sample", "false"},
                                          {"fh1_msaa_2x", "true"}}},
                                  {"OFF", {{"fh1_msaa_single_sample", "true"}}}}));
  // FAST samples the game's gamma textures through sRGB views: terrain and
  // foliage a little darker. The frame-600 replay at 1x goes from 12.3-12.7
  // to 11.3-11.7 ms on an M4 Pro (MoltenVK); no change on an RTX 4080 (#427).
  // On the Steam Deck 11.2 to 11.0 ms. Applies at the next start.
  rows.push_back(Setting("TEXTURE GAMMA", {{"ACCURATE", {{"texture_gamma_host_srgb", "false"}}},
                                           {"FAST", {{"texture_gamma_host_srgb", "true"}}}}));
#if defined(__linux__)
  // COARSE shades the scene and the shadow mask once per 2x2 pixels, as on
  // Android: surfaces a little softer, geometry edges unchanged. The
  // frame-600 replay on the Steam Deck goes from 11.2 to 10.3 ms (#427).
  // Linux enables VK_KHR_fragment_shading_rate; without it the row does
  // nothing. Applies on the next frame.
  rows.push_back(Setting(
      "SCENE SHADING",
      {{"FULL", {{"fh1_coarse_shading", "\"\""}, {"fh1_coarse_shading_alpha_test", "false"}}},
       {"COARSE",
        {{"fh1_coarse_shading", "\"1024/32/4x/d1+0/32/4x/c3=2x2,0/16/1x/d1+720/16/1x/c0=2x2\""},
         {"fh1_coarse_shading_alpha_test", "true"}}}}));
#endif
#endif
  std::vector<Choice> scales;
  // Android renders at 1x: higher scales need resolve buffers a phone's
  // shared memory cannot hold (AP-2.5).
#if defined(__ANDROID__)
  constexpr int kMaxScale = 1;
#else
  constexpr int kMaxScale = 4;
#endif
  for (int scale = 1; scale <= kMaxScale; ++scale) {
    const std::string value = std::to_string(scale);
    scales.push_back({value + "X",
                      {{"draw_resolution_scale_x", value}, {"draw_resolution_scale_y", value}}});
  }
  // Vulkan switches resolution scale between frames.
  MenuRow resolution = Setting("RESOLUTION SCALE", std::move(scales));
  if (services_.draw_resolution_scale) {
    resolution.restart_pending = [this] {
      return std::to_string(services_.draw_resolution_scale()) !=
             Unquote(Saved("draw_resolution_scale_x"));
    };
  }
  rows.push_back(std::move(resolution));
  // anisotropic_override holds the Xenos filter: 3, 4 and 5 are 4x, 8x, 16x;
  // -1 keeps what each of the game's textures asks for.
  rows.push_back(Setting("ANISOTROPIC FILTERING",
                         {{"GAME", {{"anisotropic_override", "-1"}}},
                          {"4X", {{"anisotropic_override", "3"}}},
                          {"8X", {{"anisotropic_override", "4"}}},
                          {"16X", {{"anisotropic_override", "5"}}}}));
  rows.push_back(Toggle("TRILINEAR FILTERING", "force_trilinear_filtering"));
  rows.push_back(Setting("TEXTURE DETAIL",
                         {{"SOFT", {{"texture_mip_lod_bias", "0.5"}}},
                          {"DEFAULT", {{"texture_mip_lod_bias", "0.0"}}},
                          {"SHARP", {{"texture_mip_lod_bias", "-0.5"}}},
                          {"SHARPEST", {{"texture_mip_lod_bias", "-1.0"}}}}));
  // Mipmapped textures larger than this start at the first level that
  // fits, so the larger levels take no video memory and are not uploaded:
  // softer up close. 256 took the game's dedicated GPU memory from 877 to
  // 751 MB on a free-roam drive (RTX 4080). Applies at the next start.
  rows.push_back(Setting("TEXTURE SIZE", {{"FULL", {{"vulkan_texture_max_size", "0"}}},
                                         {"1024", {{"vulkan_texture_max_size", "1024"}}},
                                         {"512", {{"vulkan_texture_max_size", "512"}}},
                                         {"256", {{"vulkan_texture_max_size", "256"}}}}));
  // FXAA over the finished frame; the game's MSAA is its own row.
  rows.push_back(Setting("POST-PROCESS AA",
                         {{"OFF", {{"swap_post_effect", "\"none\""}}},
                          {"FXAA", {{"swap_post_effect", "\"fxaa\""}}},
                          {"FXAA EXTREME", {{"swap_post_effect", "\"fxaa_extreme\""}}}}));
  // The sun's shadows: off drops the shadow maps, a depth pre-pass and the
  // screen's shadow mask (about 6 ms a frame on the Odin 2 Portal) and
  // lights everything. Applies on the next frame, and only by day: from
  // 18:50 to 08:02 the same passes light the road for the headlights, so
  // the choice says so (#733).
  rows.push_back(Setting("SHADOWS", {{"OFF BY DAY", {{"pinyon_shift_fh1_shadows", "false"}}},
                                     {"ON", {{"pinyon_shift_fh1_shadows", "true"}}}}));
  // How often the dynamic cubemap that cars reflect is redrawn.
  rows.push_back(Setting("REFLECTION UPDATES",
                         {{"FULL", {{"pinyon_shift_fh1_env_map_rate", "1"}}},
                          {"QUARTER", {{"pinyon_shift_fh1_env_map_rate", "0.25"}}}}));
  // FH1's three predicated tiles drawn as one pass (the same image, about
  // 3 ms a frame cheaper on the Odin); a change rebuilds the renderer
  // between frames.
  rows.push_back(Toggle("SINGLE-PASS SCENE", "fh1_untile_predicated_tiling"));
  rows.push_back(Toggle("BLOOM", "disable_bloom", true));
  rows.push_back(Toggle("MOTION BLUR", "disable_motion_blur", true));
  rows.push_back(Toggle("DEPTH OF FIELD", "disable_depth_of_field", true));
  // POST-PROCESS AA covers the scene only, so HUD text stays sharp; ON also
  // smooths the HUD, as it did before. Menus without a scene get none.
  rows.push_back(Toggle("AA ON THE HUD", "swap_post_effect_scene_only", true));
  // A .cube colour LUT from state/luts on the scene; the HUD keeps its
  // colours. Applies on the next frame.
  {
    std::vector<Choice> luts = {{"OFF", {{"scene_lut_path", "\"\""}}}};
    std::vector<std::filesystem::path> files;
    std::error_code error;
    const std::filesystem::path root = services_.mods_root.parent_path() / "luts";
    for (auto it = std::filesystem::directory_iterator(root, error);
         !error && it != std::filesystem::directory_iterator(); it.increment(error)) {
      std::string extension = rex::path_to_utf8(it->path().extension());
      std::transform(extension.begin(), extension.end(), extension.begin(),
                     [](unsigned char c) { return char(std::tolower(c)); });
      if (it->is_regular_file(error) && extension == ".cube") files.push_back(it->path());
    }
    std::sort(files.begin(), files.end());
    for (const auto& file : files) {
      // UTF-8 throughout: path::string() throws on Windows for a name the
      // ANSI code page can't hold (#552).
      std::string path = rex::path_to_utf8(file);
      std::replace(path.begin(), path.end(), '\\', '/');
      luts.push_back({Upper(rex::path_to_utf8(file.stem())),
                      {{"scene_lut_path", config::Quote(path)}}});
    }
    rows.push_back(Setting("COLOUR LUT", std::move(luts)));
    std::vector<Choice> strengths;
    for (int strength : {25, 50, 75, 100}) {
      strengths.push_back(
          {std::to_string(strength) + "%", {{"scene_lut_strength", std::to_string(strength)}}});
    }
    rows.push_back(Setting("LUT STRENGTH", std::move(strengths)));
  }
  auto note = [this, restart = RestartNote(rows)] {
    const std::string pending = restart ? restart() : std::string();
    if (!pending.empty()) return pending;
#if defined(__ANDROID__)
    const std::string& driver = rex::ui::vulkan::LoadedAndroidGpuDriver();
    return ResolutionLine() + ", DRIVER " + (driver.empty() ? std::string("SYSTEM") : Upper(driver));
#else
    return ResolutionLine();
#endif
  };
  return std::make_unique<MenuScreen>("GRAPHICS", std::move(rows), std::move(note));
}

std::unique_ptr<MenuScreen> SettingsPages::Hud() {
  std::vector<MenuRow> rows;
  // The same switch as F2: the HUD's elements hide while it is off.
  rows.push_back(Toggle("HUD", "hud_hidden", true));
  // Size around the screen's centre, over the game world; menus without one
  // keep theirs. Vulkan renderer only; applies at once.
  std::vector<Choice> scales;
  for (int percent = 80; percent <= 120; percent += 5) {
    scales.push_back({std::to_string(percent) + "%",
                      {{"fh1_hud_scale", std::to_string(percent / 100.0)}}});
  }
  rows.push_back(Setting("HUD SCALE", std::move(scales)));
  // A margin kept clear on each side, for TVs that crop the picture.
  rows.push_back(Setting("SAFE ZONE", {{"OFF", {{"fh1_hud_safe_zone", "0.0"}}},
                                       {"2.5%", {{"fh1_hud_safe_zone", "0.025"}}},
                                       {"5%", {{"fh1_hud_safe_zone", "0.05"}}},
                                       {"7.5%", {{"fh1_hud_safe_zone", "0.075"}}},
                                       {"10%", {{"fh1_hud_safe_zone", "0.1"}}}}));
  return std::make_unique<MenuScreen>("HUD", std::move(rows));
}

// The Treasure Map, then switches from FH1's developer launch options (#477),
// which the retail game keeps but never reads from a command line; the host
// sets the flags. Those are all off by default and applied at once.
std::unique_ptr<MenuScreen> SettingsPages::Gameplay() {
  std::vector<MenuRow> rows;
  // The Treasure Map add-on (src/dlc_treasure_map.cpp), on by default since
  // it can no longer be bought; applied in free roam. The reveal is saved
  // with the profile, so turning it off does not hide the signs again.
  rows.push_back(Toggle("TREASURE MAP", "pinyon_shift_dlc_treasure_map"));
  // Dialogs wait for their voice-over to end before A closes them.
  rows.push_back(Toggle("SKIP VOICE-OVERS WITH A", "pinyon_shift_skip_voiceover"));
  // The game puts the car back on the road when it strays too far.
  rows.push_back(Toggle("AUTOMATIC CAR RESET", "pinyon_shift_no_auto_reset", true));
  // After about 55 s idle on the title screen the game replays its intro.
  rows.push_back(Toggle("REPLAY INTRO WHEN IDLE", "pinyon_shift_no_attract_video", true));
  // The boot splash movies end through the title's own end-of-stream path
  // (#617); read once at boot, so it applies at the next start.
  rows.push_back(Toggle("SKIP INTRO MOVIES", "pinyon_shift_skip_opening_movies"));
  // Passes Press Start and SINGLE PLAYER at boot when a profile exists
  // (#617); read at boot, so it applies at the next start.
  rows.push_back(Toggle("START IN SINGLE PLAYER", "pinyon_shift_auto_start_single_player"));
  // The photo mode camera stops at walls and terrain unless the
  // disablephotomodecollisiondetection developer flag is set (#488).
  rows.push_back(Toggle("PHOTO CAMERA THROUGH WALLS", "pinyon_shift_photo_camera_through_walls"));
  // Forza Data Out (Dash) packets for SimHub and dashboards (#481), to
  // telemetry_udp_target (127.0.0.1:5300 unless the settings file says
  // otherwise).
  rows.push_back(Toggle("TELEMETRY OUT (UDP)", "telemetry_udp"));
  // How the AI race (#482): without the rubber band and catch-up, or also
  // one difficulty level up. The game reads it when it sets up the next
  // event's opponents.
  rows.push_back(Setting("AI OPPONENTS",
                         {{"STOCK", {{"pinyon_shift_ai_opponents", "\"stock\""}}},
                          {"NO RUBBER-BANDING", {{"pinyon_shift_ai_opponents", "\"fair\""}}},
                          {"HARD", {{"pinyon_shift_ai_opponents", "\"hard\""}}}}));
  return std::make_unique<MenuScreen>("GAMEPLAY", std::move(rows), [] {
    return std::string("AI OPPONENTS APPLIES FROM THE NEXT EVENT");
  });
}

std::unique_ptr<MenuScreen> SettingsPages::Audio() {
  std::vector<MenuRow> rows;
  std::vector<Choice> volumes;
  for (int volume = 0; volume <= 100; volume += 10) {
    volumes.push_back({std::to_string(volume), {{"pinyon_shift_master_volume",
                                                 std::to_string(volume)}}});
  }
  rows.push_back(Setting("MASTER VOLUME", std::move(volumes)));
  rows.push_back(Toggle("MUTE", "audio_mute"));
  // The mixer (#486): the game's own level of each category, scaled; the
  // game reads the levels when it starts.
  const auto mix = [&](std::string label, std::string name) {
    std::vector<Choice> levels;
    for (int percent = 0; percent <= 200; percent += 10) {
      levels.push_back({std::to_string(percent) + "%", {{name, std::to_string(percent)}}});
    }
    rows.push_back(Setting(std::move(label), std::move(levels)));
  };
  mix("ENGINE", "pinyon_shift_mix_engine");
  mix("OTHER CARS", "pinyon_shift_mix_opponents");
  mix("TYRES", "pinyon_shift_mix_tyres");
  mix("WIND", "pinyon_shift_mix_wind");
  mix("AMBIENCE", "pinyon_shift_mix_ambience");
  mix("GAME MUSIC", "pinyon_shift_mix_music");
  rows.push_back(Toggle("FULL DYNAMIC RANGE", "pinyon_shift_mix_full_dynamic_range"));
  // Your music (#420): the player's own files instead of the game's radio,
  // which the game mutes once the host player has the music.
  rows.push_back(Toggle("YOUR MUSIC", "pinyon_shift_music"));
  std::vector<Choice> music_volumes;
  for (int volume = 0; volume <= 100; volume += 10) {
    music_volumes.push_back({std::to_string(volume), {{"pinyon_shift_music_volume",
                                                       std::to_string(volume)}}});
  }
  rows.push_back(Setting("MUSIC VOLUME", std::move(music_volumes)));
  rows.push_back(Toggle("SHUFFLE", "pinyon_shift_music_shuffle"));
  MenuRow next;
  next.label = "NEXT TRACK";
  next.activate = [] { music::Next(); };
  rows.push_back(std::move(next));
  MenuRow previous;
  previous.label = "PREVIOUS TRACK";
  previous.activate = [] { music::Previous(); };
  rows.push_back(std::move(previous));
  auto note = [restart = RestartNote(rows)] {
    const std::string pending = restart ? restart() : std::string();
    return pending.empty() ? music::StatusLine() : pending;
  };
  return std::make_unique<MenuScreen>("AUDIO", std::move(rows), std::move(note));
}

// The controller mapping assistant (#432): for a controller SDL's database
// does not know, or one the player wants to lay out differently, ask for each
// Xbox 360 control in turn, read the controller's raw input, let the player
// try the result and save it as an SDL mapping (kept in
// config/controller_mappings.txt). It works with the controller alone.
std::unique_ptr<MenuScreen> SettingsPages::MapController() {
  std::vector<MenuRow> rows;
  for (auto& joystick : rex::input::sdl::ListJoysticks()) {
    MenuRow row;
    row.label = Upper(joystick.name);
    row.value = [user = joystick.user_mapping, mapped = !joystick.mapping.empty()] {
      return std::string(user ? "YOUR MAPPING" : mapped ? "MAPPED" : "NOT MAPPED");
    };
    row.activate = [self = shared_from_this(), joystick] {
      self->host_ui_.Push(self->MapControllerOptions(joystick));
    };
    rows.push_back(std::move(row));
  }
  auto screen = std::make_unique<MenuScreen>("MAP CONTROLLER", std::move(rows));
  screen->set_body(screen->rows().empty()
                       ? "No controller is connected. Connect one and open this page again."
                       : "Choose a controller. The keyboard works here too if the controller "
                         "does not move through menus yet.");
  return screen;
}

std::unique_ptr<MenuScreen> SettingsPages::MapControllerOptions(
    rex::input::sdl::JoystickInfo joystick) {
  auto user_mapping = std::make_shared<bool>(joystick.user_mapping);
  auto screen_ref = std::make_shared<MenuScreen*>(nullptr);
  std::vector<MenuRow> rows;
  MenuRow map;
  map.label = "MAP BUTTONS";
  map.activate = [self = shared_from_this(), joystick] {
    self->host_ui_.Push(self->MapControllerSteps(joystick));
  };
  rows.push_back(std::move(map));
  MenuRow reset;
  reset.label = "RESET TO DEFAULT MAPPING";
  reset.enabled = [user_mapping] { return *user_mapping; };
  reset.activate = [user_mapping, screen_ref, guid = joystick.guid] {
    *user_mapping = false;
    (*screen_ref)
        ->set_body(rex::input::sdl::RemoveUserMapping(guid)
                       ? "Your mapping is removed and the default one applies."
                       : "Your mapping is removed. The default one applies after a restart.");
  };
  rows.push_back(std::move(reset));
  // A wheel SDL does not know as one: its steering and pedals are reshaped by
  // the RACING WHEEL page once it is marked here.
  MenuRow wheel;
  wheel.label = "RACING WHEEL";
  wheel.value = [guid = joystick.guid, known = joystick.wheel_type] {
    if (known) return std::string("YES (DETECTED)");
    return std::string(rex::input::sdl::IsListedWheel(guid) ? "YES" : "NO");
  };
  wheel.enabled = [known = joystick.wheel_type] { return !known; };
  wheel.adjust = [this, guid = joystick.guid](int) {
    rex::input::sdl::SetListedWheel(guid, !rex::input::sdl::IsListedWheel(guid));
    config_.Set("hid_wheel_guids", config::Quote(rex::cvar::GetFlagByName("hid_wheel_guids")));
    diagnostics::RecordEvent("settings.changed",
                             {{"row", "RACING WHEEL"},
                              {"values", "hid_wheel_guids=" +
                                             rex::cvar::GetFlagByName("hid_wheel_guids")}});
    Save();
  };
  wheel.activate = [adjust = wheel.adjust] { adjust(1); };
  rows.push_back(std::move(wheel));
  auto screen = std::make_unique<MenuScreen>(Upper(joystick.name), std::move(rows));
  *screen_ref = screen.get();
  screen->set_body(joystick.user_mapping ? "This controller uses a mapping you made."
                   : joystick.mapping.empty()
                       ? "SDL does not know this controller. Map its buttons to use it."
                       : "This controller uses SDL's mapping for it.");
  return screen;
}

std::unique_ptr<MenuScreen> SettingsPages::MapControllerSteps(
    rex::input::sdl::JoystickInfo joystick) {
  struct Step {
    const char* prompt;
    const char* output;
    // The same control's name on a PlayStation pad (FB-3.5), or null.
    const char* playstation = nullptr;
  };
  // SDL's names for the Xbox 360 controls; a leading sign is a half axis.
  static constexpr Step kSteps[] = {
      {"A", "a", "CROSS"},
      {"B", "b", "CIRCLE"},
      {"X", "x", "SQUARE"},
      {"Y", "y", "TRIANGLE"},
      {"LEFT BUMPER (LB)", "leftshoulder", "L1"},
      {"RIGHT BUMPER (RB)", "rightshoulder", "R1"},
      {"LEFT TRIGGER (LT)", "lefttrigger", "L2"},
      {"RIGHT TRIGGER (RT)", "righttrigger", "R2"},
      {"BACK", "back", "CREATE (SHARE)"},
      {"START", "start", "OPTIONS"},
      {"GUIDE (XBOX BUTTON)", "guide", "PS BUTTON"},
      {"D-PAD UP", "dpup"},
      {"D-PAD DOWN", "dpdown"},
      {"D-PAD LEFT", "dpleft"},
      {"D-PAD RIGHT", "dpright"},
      {"LEFT STICK LEFT", "-leftx"},
      {"LEFT STICK RIGHT", "+leftx"},
      {"LEFT STICK UP", "-lefty"},
      {"LEFT STICK DOWN", "+lefty"},
      {"LEFT STICK PRESS", "leftstick", "L3 (LEFT STICK PRESS)"},
      {"RIGHT STICK LEFT", "-rightx"},
      {"RIGHT STICK RIGHT", "+rightx"},
      {"RIGHT STICK UP", "-righty"},
      {"RIGHT STICK DOWN", "+righty"},
      {"RIGHT STICK PRESS", "rightstick", "R3 (RIGHT STICK PRESS)"},
  };
  static constexpr size_t kStepCount = std::size(kSteps);
  static constexpr auto kStepTime = std::chrono::seconds(8);
  static constexpr auto kHoldTime = std::chrono::seconds(2);
  enum class Phase { kCapture, kTest, kDone };
  struct Session {
    rex::input::sdl::JoystickInfo joystick;
    rex::input::sdl::JoystickCapture capture;
    rex::input::sdl::GamepadView view;
    // The captured input for each step, empty when skipped.
    std::vector<std::string> inputs = std::vector<std::string>(kStepCount);
    size_t step = 0;
    Phase phase = Phase::kCapture;
    std::string note;
    std::chrono::steady_clock::time_point step_started, phase_started;
    std::string held_control;
    std::chrono::steady_clock::time_point held_since;
    bool saved = false;
  };
  auto session = std::make_shared<Session>();
  session->joystick = std::move(joystick);
  const bool opened = session->capture.Begin(session->joystick.instance_id);
  session->step_started = std::chrono::steady_clock::now();

  // Prompts in the labels printed on the pad being mapped.
  const bool playstation = session->joystick.playstation;
  const auto prompt = [playstation](const Step& step) {
    return std::string(playstation && step.playstation ? step.playstation : step.prompt);
  };
  const auto control_name = [prompt](const std::string& output) {
    for (const Step& step : kSteps) {
      if (output == step.output) return prompt(step);
    }
    return Upper(output);
  };
  // Pairs of half axes on one input become a full axis ("leftx:a0").
  const auto mapping = [session] {
    std::vector<std::pair<std::string, std::string>> bindings;
    for (size_t i = 0; i < kStepCount; ++i) {
      const std::string output = kSteps[i].output;
      const std::string& input = session->inputs[i];
      if (input.empty()) continue;
      if (output[0] == '-' || output[0] == '+') {
        size_t other = 0;
        while (other < kStepCount &&
               (other == i ||
                std::string_view(kSteps[other].output).substr(1) != output.substr(1))) {
          ++other;
        }
        if (other < kStepCount) {
          const std::string& paired = session->inputs[other];
          if (input.size() > 1 && paired.size() > 1 && (input[0] == '+' || input[0] == '-') &&
              input.substr(1) == paired.substr(1) && input[0] != paired[0]) {
            if (output[0] == '+') {
              bindings.emplace_back(output.substr(1),
                                    input[0] == '+' ? input.substr(1) : input.substr(1) + "~");
            }
            continue;
          }
        }
      }
      bindings.emplace_back(output, input);
    }
    return rex::input::sdl::BuildMapping(session->joystick, bindings);
  };
  // Leaving or starting over while trying a mapping puts the old one back.
  const auto restore = [session] {
    if (session->phase == Phase::kTest && !session->joystick.mapping.empty()) {
      rex::input::sdl::ApplyMapping(session->joystick.mapping);
    }
  };
  const auto begin_test = [session, mapping] {
    session->capture.End();
    session->phase = Phase::kTest;
    session->phase_started = std::chrono::steady_clock::now();
    session->held_control.clear();
    if (!rex::input::sdl::ApplyMapping(mapping()) ||
        !session->view.Begin(session->joystick.instance_id)) {
      session->note = "The mapping could not be applied (see the log).";
    }
  };
  const auto restart = [session, restore] {
    restore();
    session->view.End();
    session->inputs.assign(kStepCount, std::string());
    session->step = 0;
    session->phase = Phase::kCapture;
    session->note.clear();
    session->capture.Begin(session->joystick.instance_id);
    session->step_started = std::chrono::steady_clock::now();
  };
  const auto save = [session, mapping] {
    session->view.End();
    session->saved = rex::input::sdl::SaveMapping(mapping());
    session->phase = Phase::kDone;
    session->phase_started = std::chrono::steady_clock::now();
  };
  const auto advance = [session, begin_test] {
    session->note.clear();
    if (++session->step >= kStepCount) {
      session->step = kStepCount - 1;
      begin_test();
    }
    session->step_started = std::chrono::steady_clock::now();
  };

  auto screen = std::make_unique<MenuScreen>(Upper(session->joystick.name), std::vector<MenuRow>{});
  MenuScreen* raw = screen.get();
  const auto show = [session, raw, control_name, prompt] {
    const auto now = std::chrono::steady_clock::now();
    const std::string note = session->note.empty() ? std::string() : session->note + "\n";
    std::string body;
    switch (session->phase) {
      case Phase::kCapture: {
        const auto left = std::chrono::duration_cast<std::chrono::seconds>(
            kStepTime - (now - session->step_started));
        body = "Press " + prompt(kSteps[session->step]) + " on the controller.\n" +
               std::to_string(session->step + 1) + " of " + std::to_string(kStepCount) +
               ". Skipped in " + std::to_string(std::max<int64_t>(0, left.count() + 1)) +
               " s if the controller has none.\n" + note +
               "Keyboard: any key skips, Backspace goes back, R starts over, Escape cancels.";
        break;
      }
      case Phase::kTest: {
        std::string held;
        for (const auto& control : session->view.Held()) {
          held += (held.empty() ? "" : ", ") + control_name(control);
        }
        body = "Try the controller. Held: " + (held.empty() ? std::string("nothing") : held) +
               "\n" + note +
               "Hold START for 2 s to save it, or BACK to map it again.\n"
               "Keyboard: Enter saves, R maps again, Escape cancels.";
        break;
      }
      case Phase::kDone:
        body = session->saved ? "Saved. The controller now works as an Xbox 360 controller."
                              : "The mapping could not be saved (see the log).";
        break;
    }
    raw->set_body(std::move(body));
  };
  if (!opened) {
    session->phase = Phase::kDone;
    raw->set_body("The controller could not be opened. Press any key to go back.");
  } else {
    show();
    screen->set_tick([self = shared_from_this(), session, raw, show, advance, restart, save, prompt] {
      const auto now = std::chrono::steady_clock::now();
      switch (session->phase) {
        case Phase::kCapture:
          if (auto input = session->capture.Poll()) {
            const auto used = std::find(session->inputs.begin(), session->inputs.end(), *input);
            if (used == session->inputs.end()) {
              session->inputs[session->step] = *input;
              advance();
            } else {
              session->note = "That is already " +
                              prompt(kSteps[used - session->inputs.begin()]) +
                              ". Press another control.";
            }
          } else if (now - session->step_started >= kStepTime) {
            advance();
          }
          break;
        case Phase::kTest: {
          // Holding START or BACK (through the new mapping) decides, so the
          // controller alone can finish.
          const auto held = session->view.Held();
          std::string control;
          for (const char* name : {"start", "back"}) {
            if (std::find(held.begin(), held.end(), name) != held.end()) control = name;
          }
          if (control != session->held_control) {
            session->held_control = control;
            session->held_since = now;
          } else if (!control.empty() && now - session->held_since >= kHoldTime) {
            if (control == "start") {
              save();
            } else {
              restart();
            }
          }
          break;
        }
        case Phase::kDone:
          // The result stays up for a few seconds, then the screen goes back
          // by itself, so a player with only the controller is not stuck.
          if (now - session->phase_started >= std::chrono::seconds(4)) {
            self->host_ui_.Finish(raw);
            return;
          }
          break;
      }
      show();
    });
  }
  screen->set_key_capture(
      [self = shared_from_this(), session, raw, show, advance, restart, save, restore](
          int virtual_key) {
        using rex::ui::VirtualKey;
        const auto key = VirtualKey(virtual_key);
        if (session->phase == Phase::kDone || key == VirtualKey::kEscape) {
          restore();
          session->capture.End();
          session->view.End();
          self->host_ui_.Finish(raw);
          return;
        }
        if (key == VirtualKey::kR) {
          restart();
        } else if (session->phase == Phase::kTest) {
          if (key == VirtualKey::kReturn) save();
        } else if (key == VirtualKey::kBack) {
          if (session->step > 0) {
            session->inputs[--session->step].clear();
            session->note.clear();
            session->step_started = std::chrono::steady_clock::now();
          }
        } else {
          advance();
        }
        show();
      });
  screen->set_on_back([session, restore] {
    restore();
    session->capture.End();
    session->view.End();
  });
  return screen;
}

std::unique_ptr<MenuScreen> SettingsPages::ControllerButtons() {
  // One row per physical control, showing what the title receives from it;
  // swapping A and B is A SENDS B and B SENDS A. Menus here keep the
  // physical layout whatever is set.
  using rex::input::PadControl;
  std::vector<MenuRow> rows;
  for (size_t i = 0; i < rex::input::kPadControlCount; ++i) {
    MenuRow row;
    row.label = std::string(rex::input::PadControlName(PadControl(i))) + " SENDS";
    row.value = [this, i] {
      const auto remap = rex::input::ParsePadRemap(Unquote(Saved("pad_remap")));
      return std::string(rex::input::PadControlName(remap[i]));
    };
    row.adjust = [this, i](int direction) {
      auto remap = rex::input::ParsePadRemap(Unquote(Saved("pad_remap")));
      const size_t count = rex::input::kPadControlCount;
      remap[i] = PadControl((size_t(remap[i]) + count + (direction > 0 ? 1 : count - 1)) % count);
      const std::string text = rex::input::FormatPadRemap(remap);
      config_.Set("pad_remap", config::Quote(text));
      rex::cvar::SetFlagByName("pad_remap", text);
      Save();
    };
    rows.push_back(std::move(row));
  }
  rows.push_back(Toggle("INVERT LOOK", "pad_invert_right_stick_y"));
  // Buttons held together that toggle the performance panel (F3 on a
  // keyboard); the game does not see them while they are held.
  rows.push_back(Setting("PERFORMANCE PANEL",
                         {{"LS + RS", {{"pad_chord_debug_overlay", "\"LS+RS\""}}},
                          {"BACK + RS", {{"pad_chord_debug_overlay", "\"BACK+RS\""}}},
                          {"OFF", {{"pad_chord_debug_overlay", "\"\""}}}}));
  // Opens these settings from a controller alone (Steam Deck, handhelds).
  rows.push_back(Setting("SETTINGS MENU",
                         {{"BACK + START", {{"pad_chord_game_menu", "\"BACK+START\""}}},
                          {"LS + RS + START", {{"pad_chord_game_menu", "\"LS+RS+START\""}}},
                          {"OFF", {{"pad_chord_game_menu", "\"\""}}}}));
  MenuRow reset;
  reset.label = "RESET TO DEFAULT";
  reset.activate = [this] {
    config_.Set("pad_remap", config::Quote(""));
    rex::cvar::SetFlagByName("pad_remap", "");
    Save();
  };
  rows.push_back(std::move(reset));
  return std::make_unique<MenuScreen>("CONTROLLER", std::move(rows), [this] {
    return rex::input::FormatPadRemap(rex::input::ParsePadRemap(Unquote(Saved("pad_remap"))))
                   .empty()
               ? std::string("EVERY BUTTON SENDS ITSELF")
               : std::string("CHANGES APPLY AT ONCE; MENUS HERE KEEP THE PHYSICAL LAYOUT");
  });
}

std::vector<std::string> SettingsPages::EnabledMods() const {
  std::vector<std::string> list;
  const std::string text = Unquote(Saved("enabled_mods"));
  size_t start = 0;
  while (start <= text.size()) {
    const size_t comma = text.find(',', start);
    std::string name =
        text.substr(start, comma == std::string::npos ? std::string::npos : comma - start);
    if (!name.empty()) list.push_back(name);
    if (comma == std::string::npos) break;
    start = comma + 1;
  }
  return list;
}

void SettingsPages::SetModEnabled(const std::string& name, bool enabled) {
  auto list = EnabledMods();
  const auto it = std::find(list.begin(), list.end(), name);
  if ((it != list.end()) == enabled) return;
  if (enabled) {
    list.push_back(name);
  } else {
    list.erase(it);
  }
  std::string text;
  for (const auto& entry : list) text += (text.empty() ? "" : ",") + entry;
  config_.Set("enabled_mods", config::Quote(text));
  Save();
}

bool SettingsPages::BuiltinModInstalled(const std::string& name) const {
  std::error_code error;
  return !services_.mods_root.empty() &&
         std::filesystem::is_regular_file(services_.mods_root / name / "mod.toml", error);
}

std::unique_ptr<MenuScreen> SettingsPages::Mods() {
  // One row per folder in <state>/mods, switched on and off in enabled_mods
  // (at the next start); the note under the list is the focused mod's state.
  std::vector<std::string> names;
  std::error_code error;
  for (auto it = std::filesystem::directory_iterator(services_.mods_root, error);
       !error && it != std::filesystem::directory_iterator(); it.increment(error)) {
    // A built-in mod that always loads (the immersive camera) has its own
    // settings instead of a row here.
    if (it->is_directory(error) && !AlwaysEnabledBuiltin(it->path())) {
      names.push_back(rex::path_to_utf8(it->path().filename()));
    }
  }
  std::sort(names.begin(), names.end());
  std::vector<MenuRow> rows;
  for (const auto& name : names) {
    MenuRow row;
    row.label = Upper(name);
    row.restart_required = true;
    row.value = [this, name] {
      const auto list = EnabledMods();
      return std::string(std::find(list.begin(), list.end(), name) != list.end() ? "ON" : "OFF");
    };
    row.adjust = [this, name](int) {
      const auto list = EnabledMods();
      SetModEnabled(name, std::find(list.begin(), list.end(), name) == list.end());
    };
    rows.push_back(std::move(row));
  }
  // Texture replacements (NP-10.3) reload in place, for editing them while
  // the game runs.
  const bool texture_reload = !rex::cvar::GetFlagByName("texture_replacement_dirs").empty();
  if (texture_reload) {
    MenuRow row;
    row.label = "RELOAD TEXTURES";
    row.activate = [] {
      const std::string current = rex::cvar::GetFlagByName("texture_replacement_reload");
      const int next = (current.empty() ? 0 : std::atoi(current.c_str())) + 1;
      rex::cvar::SetFlagByName("texture_replacement_reload", std::to_string(next));
      diagnostics::RecordEvent("mods.textures_reloaded", {{"generation", std::to_string(next)}});
    };
    rows.push_back(std::move(row));
  }
  auto self = std::make_shared<const MenuScreen*>(nullptr);
  auto screen = std::make_unique<MenuScreen>("MODS", std::move(rows), [self, names,
                                                                      texture_reload] {
    if (size_t((*self)->focus()) >= names.size()) {
      return std::string(texture_reload
                             ? "READS THE MODS' TEXTURES FOLDERS AGAIN AND RELOADS EVERY TEXTURE"
                             : "PUT MODS IN THE MODS FOLDER OF THE GAME'S STATE");
    }
    const std::string& name = names[(*self)->focus()];
    for (const auto& info : pinyon_shift::mod::Mods()) {
      if (info.name == name) {
        return info.loaded ? std::string("LOADED ") + info.version
                           : std::string("NOT LOADED: ") + Upper(info.problem);
      }
    }
    return std::string("MODS PLAY A SEPARATE PROFILE; CHANGES APPLY AT THE NEXT START");
  });
  *self = screen.get();
  return screen;
}

std::unique_ptr<MenuScreen> SettingsPages::ModActions() {
  // Actions mods added through the UI extension API (NP-11).
  std::vector<MenuRow> rows;
  for (const auto& action : pinyon_shift::mod::MenuActions()) {
    MenuRow row;
    row.label = Upper(action.label);
    row.activate = [action] {
      diagnostics::RecordEvent("mod.menu_action", {{"label", action.label}});
      action.callback(action.user);
    };
    rows.push_back(std::move(row));
  }
  return std::make_unique<MenuScreen>("MOD ACTIONS", std::move(rows));
}

std::unique_ptr<MenuScreen> SettingsPages::Cheats() {
  std::vector<MenuRow> rows;
  rows.push_back(Toggle("TRAINER", "pinyon_shift_cheats"));
  return std::make_unique<MenuScreen>("CHEATS", std::move(rows), [] {
    return std::string("F10 OPENS THE TRAINER; CHEATS PLAY THE SEPARATE MODDED PROFILE");
  });
}

std::unique_ptr<MenuScreen> SettingsPages::Trainer() {
  std::vector<MenuRow> rows;
  MenuRow resume;
  resume.label = "RESUME";
  resume.activate = [self = shared_from_this()] { self->host_ui_.Close(); };
  rows.push_back(std::move(resume));
  rows.push_back(Page("PLAYER", &SettingsPages::TrainerPlayer));
  rows.push_back(Page("WORLD", &SettingsPages::TrainerWorld));
  rows.push_back(Page("VEHICLE", &SettingsPages::TrainerVehicle));
  rows.push_back(Page("GRAPHICS", &SettingsPages::TrainerGraphics));
  rows.push_back(Page("DEBUG", &SettingsPages::TrainerDebug));
  return std::make_unique<MenuScreen>("TRAINER", std::move(rows), [] {
    return std::string("MODDED PROFILE: YOUR OWN SAVE IS NOT TOUCHED");
  });
}

std::unique_ptr<MenuScreen> SettingsPages::TrainerPlayer() {
  // Credits (NP-8.3) go through the title's own setter at once, or when the
  // profile loads if it has not yet: left and right pick the amount, enter
  // applies it. A set goes through cheat_set_credits (cleared once applied,
  // and kept in the file until then for a profile that loads next start).
  std::vector<MenuRow> rows;
  using Amount = std::pair<const char*, int32_t>;
  static constexpr Amount kSetAmounts[] = {
      {"0", 0}, {"250,000", 250000}, {"1,000,000", 1000000}, {"5,000,000", 5000000},
      {"20,000,000", 20000000}};
  static constexpr Amount kAddAmounts[] = {
      {"+100,000", 100000}, {"+1,000,000", 1000000}, {"+10,000,000", 10000000}};
  const auto amount_row = [](std::string label, const Amount* amounts, int count, int first,
                             std::function<void(int32_t)> apply) {
    auto index = std::make_shared<int>(first);
    MenuRow row;
    row.label = std::move(label);
    row.value = [amounts, index] { return std::string(amounts[*index].first); };
    row.adjust = [count, index](int direction) { *index = (*index + direction + count) % count; };
    row.activate = [amounts, index, apply = std::move(apply)] { apply(amounts[*index].second); };
    return row;
  };
  rows.push_back(amount_row("SET CREDITS", kSetAmounts, int(std::size(kSetAmounts)), 2,
                            [this](int32_t credits) {
                              const std::string value = std::to_string(credits);
                              config_.Set("cheat_set_credits", value);
                              rex::cvar::SetFlagByName("cheat_set_credits", value);
                              Save();
                            }));
  rows.push_back(amount_row("ADD CREDITS", kAddAmounts, int(std::size(kAddAmounts)), 1,
                            [](int32_t credits) { cheats::AddCredits(credits); }));
  // Any scalar profile field goes through cheat_set_profile_fields; the
  // wristband level also unlocks the events it gates.
  std::vector<Choice> wristbands;
  wristbands.push_back({"UNCHANGED", {{"cheat_set_profile_fields", ""}}});
  for (const char* level : {"1", "2", "3", "4", "5", "6", "7", "8"}) {
    wristbands.push_back(
        {std::string("LEVEL ") + level,
         {{"cheat_set_profile_fields", std::string("Main/WristbandLevel=") + level}}});
  }
  rows.push_back(Setting("SET WRISTBAND", std::move(wristbands)));
  return std::make_unique<MenuScreen>("PLAYER", std::move(rows), [] {
    return std::string(cheats::CreditsPending()
                           ? "CREDITS APPLY ONCE THE PROFILE HAS LOADED"
                           : "ENTER APPLIES CREDITS AT ONCE; WRISTBAND AT THE NEXT PROFILE LOAD");
  });
}

std::unique_ptr<MenuScreen> SettingsPages::TrainerWorld() {
  std::vector<MenuRow> rows;
  std::vector<Choice> speeds;
  for (const char* value : {"0.25", "0.5", "0.75", "1.0", "1.25", "1.5", "2.0"}) {
    speeds.push_back({std::string(value) + "X", {{"cheat_time_scale", value}}});
  }
  rows.push_back(Setting("GAME SPEED", std::move(speeds)));
  std::vector<Choice> times;
  times.push_back({"RUNNING", {{"cheat_time_of_day", "-1"}}});
  for (const char* hour : {"0", "3", "6", "9", "12", "15", "18", "21"}) {
    const std::string label = std::string(hour[1] ? "" : "0") + hour + ":00";
    times.push_back({label, {{"cheat_time_of_day", hour}}});
  }
  rows.push_back(Setting("TIME OF DAY", std::move(times)));
  // How long 24 game hours last while the time of day runs (#483); events
  // and scripts that set the time still do.
  rows.push_back(Setting("DAY LENGTH", {{"GAME", {{"cheat_day_length_minutes", "0"}}},
                                        {"12 MIN", {{"cheat_day_length_minutes", "12"}}},
                                        {"24 MIN", {{"cheat_day_length_minutes", "24"}}},
                                        {"48 MIN", {{"cheat_day_length_minutes", "48"}}},
                                        {"2 H", {{"cheat_day_length_minutes", "120"}}},
                                        {"6 H", {{"cheat_day_length_minutes", "360"}}},
                                        {"24 H", {{"cheat_day_length_minutes", "1440"}}},
                                        {"PC CLOCK", {{"cheat_day_length_minutes", "-1"}}}}));
  rows.push_back(Toggle("FREE CAMERA", "cheat_free_camera"));
  // The discount signs and barn finds not yet found, on the map and minimap
  // (NP-8.6).
  rows.push_back(Toggle("SHOW COLLECTIBLES", "cheat_show_collectibles"));
  // Events load without their class, make, year and other car limits (FB-12.3);
  // an event's ticket picks it up the next time it loads.
  rows.push_back(Toggle("ANY CAR IN ANY EVENT", "cheat_any_car_events"));
  return std::make_unique<MenuScreen>("WORLD", std::move(rows));
}

std::unique_ptr<MenuScreen> SettingsPages::TrainerVehicle() {
  std::vector<MenuRow> rows(1);
  rows[0].label = "FREEZE POSITION";
  rows[0].value = [] { return std::string("NOT YET"); };
  rows[0].enabled = [] { return false; };
  rows.push_back(Toggle("FAST TRAVEL ANYWHERE", "cheat_fast_travel_anywhere"));
  MenuRow teleport;
  teleport.label = "TELEPORT TO LAST MAP ROAD";
  teleport.enabled = [] { return cheats::MapDestination().has_value(); };
  teleport.activate = [this] {
    if (const auto point = cheats::MapDestination(); point && cheats::RequestTeleportDestination(*point))
      host_ui_.Close();
  };
  rows.push_back(std::move(teleport));
  MenuRow gps;
  gps.label = "GPS TO LAST MAP ROAD";
  gps.enabled = [] { return cheats::MapDestination().has_value(); };
  gps.activate = [this] {
    if (const auto point = cheats::MapDestination(); point && cheats::RequestGpsDestination(*point))
      host_ui_.Close();
  };
  rows.push_back(std::move(gps));
  MenuRow remember;
  remember.label = "SAVE LAST MAP ROAD";
  remember.enabled = [] { return cheats::MapDestination().has_value(); };
  remember.activate = [this] {
    if (const auto point = cheats::MapDestination()) {
      const std::string text = std::to_string((*point)[0]) + "," +
          std::to_string((*point)[1]) + "," + std::to_string((*point)[2]);
      config_.Set("cheat_saved_destination", "\"" + text + "\"");
      rex::cvar::SetFlagByName("cheat_saved_destination", text);
      Save();
    }
  };
  rows.push_back(std::move(remember));
  MenuRow saved;
  saved.label = "GPS TO SAVED ROAD";
  saved.enabled = [] {
    return cheats::ParseDestination(rex::cvar::GetFlagByName("cheat_saved_destination")).has_value();
  };
  saved.activate = [this] {
    const auto point = cheats::ParseDestination(rex::cvar::GetFlagByName("cheat_saved_destination"));
    if (point && cheats::RequestGpsDestination(*point)) host_ui_.Close();
  };
  rows.push_back(std::move(saved));
  MenuRow saved_travel;
  saved_travel.label = "TELEPORT TO SAVED ROAD";
  saved_travel.enabled = [] {
    return cheats::ParseDestination(rex::cvar::GetFlagByName("cheat_saved_destination")).has_value();
  };
  saved_travel.activate = [this] {
    const auto point = cheats::ParseDestination(rex::cvar::GetFlagByName("cheat_saved_destination"));
    if (point && cheats::RequestTeleportDestination(*point)) host_ui_.Close();
  };
  rows.push_back(std::move(saved_travel));
  return std::make_unique<MenuScreen>("VEHICLE", std::move(rows), [] {
    return std::string("TELEPORT: OPEN THE GAME MAP FIRST; THE TITLE STREAMS THE ROAD");
  });
}

std::unique_ptr<MenuScreen> SettingsPages::TrainerGraphics() {
  std::vector<MenuRow> rows;
  rows.push_back(Toggle("BLOOM", "disable_bloom", true));
  rows.push_back(Toggle("MOTION BLUR", "disable_motion_blur", true));
  rows.push_back(Toggle("DEPTH OF FIELD", "disable_depth_of_field", true));
  rows.push_back(Toggle("TRILINEAR FILTERING", "force_trilinear_filtering"));
  return std::make_unique<MenuScreen>("GRAPHICS", std::move(rows));
}

std::unique_ptr<MenuScreen> SettingsPages::TrainerDebug() {
  std::vector<MenuRow> rows;
  rows.push_back(Toggle("LOG FILE OPENS", "fh1_render_test_log_file_opens"));
  return std::make_unique<MenuScreen>("DEBUG", std::move(rows));
}

// Racing wheels (#337) through the SDL gamepad path: steering on the left
// stick's X axis and the pedals on the triggers, from SDL's database or MAP
// CONTROLLER. FH1 shapes that input for a thumbstick, so these rows reshape a
// wheel's input first; gamepads are untouched. All apply at once.
std::unique_ptr<MenuScreen> SettingsPages::Wheel() {
  std::vector<MenuRow> rows;
  const auto percents = [](const char* name, std::initializer_list<int> values) {
    std::vector<Choice> choices;
    for (int value : values) {
      choices.push_back({std::to_string(value) + "%", {{name, std::to_string(value)}}});
    }
    return choices;
  };
  // Full lock at this share of the wheel's rotation: 50% on a 900-degree
  // wheel locks at 225 degrees each side.
  rows.push_back(Setting("STEERING SATURATION",
                         percents("hid_wheel_steering_saturation",
                                  {100, 90, 80, 70, 60, 50, 40, 30, 20})));
  // Skips the game's stick deadzone so the car answers the first degrees.
  rows.push_back(Setting("STEERING DEADZONE",
                         percents("hid_wheel_steering_deadzone", {0, 5, 10, 15, 20, 25, 30})));
  std::vector<Choice> curves;
  for (const auto& [label, value] : std::initializer_list<std::pair<const char*, int>>{
           {"LINEAR", 100}, {"SOFT CENTRE", 150}, {"SOFTER CENTRE", 200}, {"SHARP CENTRE", 75}}) {
    curves.push_back({label, {{"hid_wheel_steering_linearity", std::to_string(value)}}});
  }
  rows.push_back(Setting("STEERING CURVE", std::move(curves)));
  rows.push_back(
      Setting("PEDAL DEADZONE", percents("hid_wheel_pedal_deadzone", {0, 5, 10, 15, 20})));
  MenuRow map;
  map.label = "MAP A WHEEL";
  map.activate = [this] { host_ui_.Push(MapController()); };
  rows.push_back(std::move(map));
  // The raw wheel path (wheel_enabled): the base, pedals and buttons each
  // from their own USB device, bound by the launcher's Wheel screen into the wheel_*
  // cvars, and the game's own Xbox 360 force feedback effects played on the
  // base. The rows below apply to that path only.
  rows.push_back(Toggle("SEPARATE DEVICES", "wheel_enabled"));
  rows.push_back(Setting("FORCE FEEDBACK", {{"OFF", {{"wheel_ffb_mode", "\"off\""}}},
                                            {"ON", {{"wheel_ffb_mode", "\"difference\""}}},
                                            {"RUMBLE ONLY", {{"wheel_ffb_mode", "\"rumble\""}}}}));
  rows.push_back(Setting("FFB STRENGTH", percents("wheel_ffb_strength", {10, 25, 50, 75, 100})));
  rows.push_back(Toggle("REVERSE FORCES", "wheel_ffb_invert"));
  rows.push_back(Toggle("RECORD FFB TRACE", "wheel_ffb_trace"));
  auto screen = std::make_unique<MenuScreen>("RACING WHEEL", std::move(rows), [] {
    int wheels = 0;
    for (const auto& joystick : rex::input::sdl::ListJoysticks()) {
      if (joystick.wheel_type || rex::input::sdl::IsListedWheel(joystick.guid)) ++wheels;
    }
    return wheels == 0   ? std::string("NO WHEEL CONNECTED")
           : wheels == 1 ? std::string("1 WHEEL CONNECTED")
                         : std::to_string(wheels) + " WHEELS CONNECTED";
  });
  screen->set_body(
      "A wheel drives through its controller mapping: steering on the left stick, throttle on "
      "the right trigger and brake on the left trigger. If the game does not see it, choose MAP "
      "A WHEEL, then the wheel, and mark it as a racing wheel. SEPARATE DEVICES reads the "
      "wheel, pedals and buttons from the devices bound in the launcher's Wheel screen instead, and "
      "plays the game's own force feedback; keep its strength low on a direct-drive base.");
  return screen;
}

// DualSense (#561): adaptive triggers, lightbar and tilt steering through
// SDL's PS5 driver. All of it applies at once; the triggers follow the
// title's brake and throttle wherever pad_remap puts them.
std::unique_ptr<MenuScreen> SettingsPages::DualSense() {
  std::vector<MenuRow> rows;
  rows.push_back(Setting("ADAPTIVE TRIGGERS", {{"OFF", {{"pad_ds_triggers", "\"off\""}}},
                                               {"BRAKE", {{"pad_ds_triggers", "\"brake\""}}},
                                               {"FULL", {{"pad_ds_triggers", "\"full\""}}}}));
  std::vector<Choice> strengths;
  for (int value : {25, 50, 75, 100}) {
    strengths.push_back(
        {std::to_string(value) + "%", {{"pad_ds_trigger_strength", std::to_string(value)}}});
  }
  rows.push_back(Setting("TRIGGER STRENGTH", std::move(strengths)));
  rows.push_back(Toggle("GEAR CLICK", "pad_ds_gear_click"));
  rows.push_back(Setting("LIGHTBAR", {{"PLAYER", {{"pad_ds_lightbar", "\"player\""}}},
                                      {"RPM", {{"pad_ds_lightbar", "\"rpm\""}}},
                                      {"OFF", {{"pad_ds_lightbar", "\"off\""}}}}));
  rows.push_back(Toggle("PLAYER LIGHTS", "pad_ds_player_leds"));
  rows.push_back(Toggle("TILT STEERING", "pad_gyro_steering"));
  std::vector<Choice> sensitivities;
  for (int value : {50, 75, 100, 150, 200, 300}) {
    sensitivities.push_back(
        {std::to_string(value) + "%", {{"pad_gyro_sensitivity", std::to_string(value)}}});
  }
  rows.push_back(Setting("TILT SENSITIVITY", std::move(sensitivities)));
  auto screen = std::make_unique<MenuScreen>("DUALSENSE", std::move(rows), [] {
    bool dualsense = false;
    bool wireless = false;
    bool steam = false;
    for (const auto& joystick : rex::input::sdl::ListJoysticks()) {
      if (joystick.dualsense) {
        dualsense = true;
        wireless |= joystick.wireless;
      }
      steam |= joystick.steam_virtual;
    }
    if (dualsense) {
      return std::string(wireless ? "DUALSENSE CONNECTED (BLUETOOTH)"
                                  : "DUALSENSE CONNECTED (USB)");
    }
    if (steam || rex::input::sdl::SteamInputHidesDualSense()) {
      return std::string("STEAM INPUT HAS THE CONTROLLER");
    }
    return std::string("NO DUALSENSE CONNECTED");
  });
  screen->set_body(
      "The brake trigger stiffens and pulses when the wheels lock; FULL adds a buzz on the "
      "throttle when the wheels spin. RPM colours the lightbar toward the redline. Tilt "
      "steering adds the pad's tilt to the left stick; press the touchpad to re-centre. If Steam "
      "Input has the controller, turn it off for this game (Steam: Properties, Controller, "
      "Disable Steam Input) and restart.");
  return screen;
}

std::unique_ptr<MenuScreen> SettingsPages::Controls() {
  std::vector<MenuRow> rows;
  MenuRow controller;
  controller.label = "CONTROLLER BUTTONS";
  controller.activate = [this] { host_ui_.Push(ControllerButtons()); };
  rows.push_back(std::move(controller));
  MenuRow map;
  map.label = "MAP CONTROLLER";
  map.activate = [this] { host_ui_.Push(MapController()); };
  rows.push_back(std::move(map));
  rows.push_back(Page("RACING WHEEL", &SettingsPages::Wheel));
  // Only when a DualSense (or Steam's stand-in for one) is here, or its
  // settings were changed, so other players never see it.
  {
    bool show = rex::input::sdl::SteamInputHidesDualSense() ||
                REXCVAR_GET(pad_ds_triggers) != "off" || REXCVAR_GET(pad_ds_lightbar) != "player" ||
                REXCVAR_GET(pad_gyro_steering);
    for (const auto& joystick : rex::input::sdl::ListJoysticks()) {
      show |= joystick.playstation || joystick.steam_virtual;
    }
    if (show) {
      rows.push_back(Page("DUALSENSE", &SettingsPages::DualSense));
    }
  }
  rows.push_back(Setting("RUMBLE",
                         {{"OFF", {{"pad_rumble_strength", "0"}}},
                          {"25%", {{"pad_rumble_strength", "25"}}},
                          {"50%", {{"pad_rumble_strength", "50"}}},
                          {"75%", {{"pad_rumble_strength", "75"}}},
                          {"100%", {{"pad_rumble_strength", "100"}}}}));
  rows.push_back(Toggle("MOUSE AND KEYBOARD", "mnk_mode"));
  rows.push_back(Setting("MOUSE",
                         {{"OFF", {{"mnk_mouse", "false"}, {"mnk_mouse_steering", "false"}}},
                          {"CAMERA", {{"mnk_mouse", "true"}, {"mnk_mouse_steering", "false"}}},
                          {"STEERING", {{"mnk_mouse", "false"}, {"mnk_mouse_steering", "true"}}}}));
  std::vector<Choice> sensitivities;
  for (const char* value : {"0.25", "0.5", "0.75", "1.0", "1.5", "2.0", "3.0"}) {
    sensitivities.push_back({value, {{"mnk_sensitivity", value}}});
  }
  rows.push_back(Setting("MOUSE SENSITIVITY", std::move(sensitivities)));
  // The keys each pad control maps to in mouse-and-keyboard mode (NP-6.1,
  // #401). Choosing a row asks for a key; it replaces the row's keys and
  // applies at once, since the keyboard driver reads them on every press.
  static constexpr std::pair<const char*, const char*> binds[] = {
      // Labelled with the pad control and its role while driving.
      {"THROTTLE (RT)", "keybind_right_trigger"},
      {"BRAKE (LT)", "keybind_left_trigger"},
      {"STEER LEFT", "keybind_lstick_left"},
      {"STEER RIGHT", "keybind_lstick_right"},
      {"HANDBRAKE, ACCEPT (A)", "keybind_a"},
      {"SHIFT UP, BACK (B)", "keybind_b"},
      {"SHIFT DOWN (X)", "keybind_x"},
      {"REWIND (Y)", "keybind_y"},
      {"CLUTCH (LB)", "keybind_left_shoulder"},
      {"CAMERA (RB)", "keybind_right_shoulder"},
      {"RIGHT STICK PRESS", "keybind_rstick_press"},
      {"BACK", "keybind_back"},
      {"PAUSE (START)", "keybind_start"},
  };
  for (const auto& [label, name] : binds) {
    MenuRow row;
    row.label = label;
    row.value = [this, name = std::string(name)] {
      std::string keys = Upper(Saved(name));
      for (size_t at = keys.find(','); at != std::string::npos; at = keys.find(',', at + 3)) {
        keys.replace(at, 1, " / ");
      }
      return keys.empty() ? std::string("NONE") : keys;
    };
    row.activate = [self = shared_from_this(), label = std::string(label),
                    name = std::string(name)] {
      auto prompt = std::make_unique<MenuScreen>("PRESS A KEY", std::vector<MenuRow>{});
      prompt->set_body("Press the key or mouse button for " + label +
                       ". Escape or the controller's B cancels.");
      const MenuScreen* screen = prompt.get();
      prompt->set_key_capture([self, screen, name](int virtual_key) {
        const auto key = rex::ui::VirtualKey(virtual_key);
        if (key == rex::ui::VirtualKey::kEscape) {
          self->host_ui_.Finish(screen);
          return;
        }
        const std::string key_name = rex::ui::VirtualKeyToString(key);
        if (key_name.empty()) {
          return;  // a key the keyboard driver cannot name; keep waiting
        }
        self->config_.Set(name, config::Quote(key_name));
        rex::cvar::SetFlagByName(name, key_name);
        self->Save();
        self->host_ui_.Finish(screen);
      });
      self->host_ui_.Push(std::move(prompt));
    };
    rows.push_back(std::move(row));
  }
  MenuRow reset;
  reset.label = "RESET KEYS";
  // Every keyboard bind, not only the rows above, back to Pinyon Shift's
  // driving-first keys (#432).
  reset.activate = [this] {
    for (const auto& key : config::kDefaultKeys) {
      config_.Set(key.name, config::Quote(key.keys));
      rex::cvar::SetFlagByName(key.name, key.keys);
    }
    Save();
  };
  rows.push_back(std::move(reset));
  return std::make_unique<MenuScreen>("CONTROLS", std::move(rows));
}

std::unique_ptr<MenuScreen> SettingsPages::Gamertag() {
  // Edited one character at a time so the pad works as well as the
  // keyboard: LETTER cycles the character at POSITION, SAVE writes it.
  struct Draft {
    std::string name;
    size_t cursor = 0;
  };
  auto draft = std::make_shared<Draft>();
  draft->name = Unquote(Saved("user_name"));
  draft->cursor = draft->name.size() < kMaxGamertag ? draft->name.size() : kMaxGamertag - 1;
  static constexpr std::string_view kCharacters =
      "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 ";
  std::vector<MenuRow> rows(5);
  rows[0].label = "NAME";
  rows[0].value = [draft] { return draft->name.empty() ? std::string("-") : draft->name; };
  rows[0].enabled = [] { return false; };
  rows[1].label = "LETTER";
  rows[1].value = [draft] {
    return draft->cursor < draft->name.size() ? std::string(1, draft->name[draft->cursor])
                                              : std::string("+");
  };
  rows[1].adjust = [draft](int direction) {
    const size_t count = kCharacters.size();
    if (draft->cursor >= draft->name.size()) {
      draft->name.push_back(direction > 0 ? kCharacters.front() : kCharacters.back());
      return;
    }
    const size_t index = kCharacters.find(draft->name[draft->cursor]);
    const size_t next = index == std::string_view::npos
                            ? 0
                            : (index + count + size_t(direction > 0 ? 1 : count - 1)) % count;
    draft->name[draft->cursor] = kCharacters[next];
  };
  rows[2].label = "POSITION";
  rows[2].value = [draft] {
    return std::to_string(draft->cursor + 1) + " OF " + std::to_string(kMaxGamertag);
  };
  rows[2].adjust = [draft](int direction) {
    const size_t last = std::min(draft->name.size(), kMaxGamertag - 1);
    draft->cursor = direction > 0 ? std::min(draft->cursor + 1, last)
                                  : (draft->cursor ? draft->cursor - 1 : 0);
  };
  rows[3].label = "DELETE LETTER";
  rows[3].activate = [draft] {
    if (draft->cursor < draft->name.size()) {
      draft->name.erase(draft->cursor, 1);
    } else if (!draft->name.empty()) {
      draft->name.pop_back();
      draft->cursor = draft->name.size();
    }
  };
  rows[4].label = "SAVE";
  rows[4].restart_required = true;
  rows[4].restart_pending = [this] {
    return !SameValue(Unquote(Saved("user_name")), Live("user_name"));
  };
  rows[4].activate = [this, draft] {
    config_.Set("user_name", config::Quote(draft->name));
    Save();
  };
  return std::make_unique<MenuScreen>("GAMERTAG", std::move(rows), [this] {
    return SameValue(Unquote(Saved("user_name")), Live("user_name"))
               ? std::string("LETTERS, DIGITS AND SPACES, UP TO 15")
               : std::string("RESTART THE GAME TO USE THE NEW GAMERTAG");
  });
}

std::unique_ptr<MenuScreen> SettingsPages::Profile() {
  std::vector<MenuRow> rows(2);
  rows[0].label = "GAMERTAG";
  rows[0].value = [this] { return Unquote(Saved("user_name")); };
  rows[0].activate = [this] { host_ui_.Push(Gamertag()); };
  rows[0].restart_required = true;
  rows[0].restart_pending = [this] {
    return !SameValue(Unquote(Saved("user_name")), Live("user_name"));
  };
  // FH1 picks its string table from the console language and country; each
  // pair was checked to load its table (probe of 2026-09-29).
  const std::tuple<const char*, int, int> languages[] = {
      {"ENGLISH (US)", 1, 103},        {"ENGLISH (UK)", 1, 35},
      {"FRENCH", 4, 34},               {"GERMAN", 3, 24},
      {"ITALIAN", 6, 50},              {"SPANISH (SPAIN)", 5, 31},
      {"SPANISH (MEXICO)", 5, 71},     {"PORTUGUESE (BRAZIL)", 9, 13},
      {"DUTCH", 16, 74},               {"DANISH", 1, 25},
      {"NORWEGIAN", 15, 75},           {"SWEDISH", 13, 90},
      {"FINNISH", 1, 32},              {"POLISH", 11, 82},
      {"CZECH", 1, 23},                {"HUNGARIAN", 1, 42},
      {"RUSSIAN", 12, 88},             {"JAPANESE", 2, 53},
      {"KOREAN", 7, 56},               {"CHINESE (TRADITIONAL)", 8, 101},
  };
  std::vector<Choice> choices;
  for (const auto& [label, language, country] : languages) {
    choices.push_back({label,
                       {{"user_language", std::to_string(language)},
                        {"user_country", std::to_string(country)}}});
  }
  rows[1] = Setting("LANGUAGE", std::move(choices));
  if (services_.save_backups) {
    MenuRow backups;
    backups.label = "SAVE BACKUPS";
    backups.activate = [this] { host_ui_.Push(Backups()); };
    rows.push_back(std::move(backups));
  }
  return std::make_unique<MenuScreen>("PROFILE", std::move(rows));
}

// "20260929T074240Z-session" as "2026-09-29 07:42 SESSION START".
std::string SlotLabel(const std::string& name) {
  if (name.size() < 16) {
    return Upper(name);
  }
  std::string label = name.substr(0, 4) + "-" + name.substr(4, 2) + "-" + name.substr(6, 2) +
                      " " + name.substr(9, 2) + ":" + name.substr(11, 2);
  const std::string reason = name.size() > 17 ? name.substr(17) : std::string();
  if (reason == "session") {
    label += " SESSION START";
  } else if (reason == "before-restore") {
    label += " BEFORE RESTORE";
  }
  return label;
}

std::unique_ptr<MenuScreen> SettingsPages::Backups() {
  SaveBackups* backups = services_.save_backups;
  std::vector<MenuRow> rows;
  if (backups->RestorePending()) {
    MenuRow cancel;
    cancel.label = "CANCEL THE RESTORE";
    cancel.activate = [backups] { backups->CancelRestore(); };
    rows.push_back(std::move(cancel));
  }
  for (const auto& slot : backups->List()) {
    MenuRow row;
    row.label = SlotLabel(slot.name);
    row.value = [kilobytes = slot.bytes >> 10] { return std::to_string(kilobytes) + " KB"; };
    row.activate = [this, name = slot.name] { host_ui_.Push(ConfirmRestore(name)); };
    rows.push_back(std::move(row));
  }
  const bool empty = rows.empty();
  return std::make_unique<MenuScreen>("SAVE BACKUPS", std::move(rows), [backups, empty] {
    if (backups->RestorePending()) {
      return std::string("RESTART THE GAME TO RESTORE THE CHOSEN BACKUP");
    }
    return std::string(empty ? "A BACKUP IS TAKEN AFTER EACH SAVE" : "NEWEST FIRST, UTC TIMES");
  });
}

std::unique_ptr<MenuScreen> SettingsPages::ConfirmRestore(std::string slot) {
  SaveBackups* backups = services_.save_backups;
  auto self = std::make_shared<const MenuScreen*>(nullptr);
  std::vector<MenuRow> rows(2);
  rows[0].label = "RESTORE AT NEXT START";
  rows[0].activate = [this, backups, slot, self] {
    backups->ScheduleRestore(slot);
    host_ui_.Finish(*self);
  };
  rows[1].label = "CANCEL";
  rows[1].activate = [this, self] { host_ui_.Finish(*self); };
  auto screen = std::make_unique<MenuScreen>("RESTORE BACKUP", std::move(rows));
  screen->set_body("The game will restore the saves from " + SlotLabel(slot) +
                   " when it next starts. Your current saves are backed up first, so this can "
                   "be undone.");
  screen->SetFocus(1);
  *self = screen.get();
  return screen;
}

std::unique_ptr<MenuScreen> SettingsPages::Root() {
  std::vector<MenuRow> rows;
  MenuRow resume;
  resume.label = "RESUME";
  resume.activate = [self = shared_from_this()] { self->host_ui_.Close(); };
  rows.push_back(std::move(resume));
  rows.push_back(Page("DISPLAY", &SettingsPages::Display));
  rows.push_back(Page("GRAPHICS", &SettingsPages::Graphics));
  rows.push_back(Page("AUDIO", &SettingsPages::Audio));
  rows.push_back(Page("CONTROLS", &SettingsPages::Controls));
  rows.push_back(Page("PROFILE", &SettingsPages::Profile));
  rows.push_back(Page("CHEATS", &SettingsPages::Cheats));
  if (!pinyon_shift::mod::MenuActions().empty()) {
    rows.push_back(Page("MOD ACTIONS", &SettingsPages::ModActions));
  }
  if (!services_.mods_root.empty()) {
    MenuRow row;
    row.label = "MODS";
    row.activate = [self = shared_from_this()] { self->host_ui_.Push(self->Mods()); };
    rows.push_back(std::move(row));
  }
  if (services_.achievements) {
    MenuRow row;
    row.label = "ACHIEVEMENTS";
    row.activate = [self = shared_from_this()] {
      self->host_ui_.Push(self->services_.achievements());
    };
    rows.push_back(std::move(row));
  }
  if (services_.trainer && pinyon_shift::cheats::Enabled()) {
    MenuRow row;
    row.label = "TRAINER";
    row.activate = [self = shared_from_this()] {
      self->host_ui_.Push(CreateTrainerMenu(self->host_ui_, self->config_));
    };
    rows.push_back(std::move(row));
  }
  if (services_.save_photo) {
    MenuRow row;
    row.label = "SAVE PHOTO";
    // After the menu closes, so the photo is the game alone.
    row.activate = [self = shared_from_this()] {
      self->host_ui_.Close();
      self->services_.save_photo();
    };
    rows.push_back(std::move(row));
  }
  if (PinyonShiftUseBuiltinRallyAdapter()) rows.push_back(Page("HORIZON RALLY", &SettingsPages::Rally));
  // Last, so the rows above keep their places for scripted routes.
  rows.push_back(Page("GAMEPLAY", &SettingsPages::Gameplay));
  return std::make_unique<MenuScreen>("SETTINGS", std::move(rows));
}

std::unique_ptr<MenuScreen> SettingsPages::Rally() {
  std::vector<MenuRow> rows;
  for (uint32_t id = 1; id <= 7; ++id) {
    MenuRow row;
    row.label = "CHAMPIONSHIP " + std::to_string(id);
    row.value = [id] {
      const auto stage = PinyonShiftRallyResumeStage(id);
      return stage ? "RESUME STAGE " + std::to_string(stage) : std::string("START");
    };
    row.enabled = [id] { return PinyonShiftCanStartRallySeries(id); };
    row.activate = [this, id] { if (PinyonShiftStartRallySeries(id)) host_ui_.Close(); };
    rows.push_back(std::move(row));
  }
  MenuRow retire;
  retire.label = "RETIRE CURRENT CHAMPIONSHIP";
  retire.enabled = [] {
    for (uint32_t id = 1; id <= 7; ++id)
      if (PinyonShiftRallyResumeStage(id) && PinyonShiftCanStartRallySeries(id)) return true;
    return false;
  };
  retire.activate = [this] { host_ui_.Push(ConfirmRallyRetirement()); };
  rows.push_back(std::move(retire));
  return std::make_unique<MenuScreen>("HORIZON RALLY", std::move(rows), [] {
    return std::string("FOUR STAGES PER CHAMPIONSHIP; LEAVE GARAGE OR SERVICE MENUS TO START");
  });
}

std::unique_ptr<MenuScreen> SettingsPages::ConfirmRallyRetirement() {
  auto self = std::make_shared<const MenuScreen*>(nullptr);
  std::vector<MenuRow> rows(2);
  rows[0].label = "RETIRE CHAMPIONSHIP";
  rows[0].activate = [this, self] {
    if (PinyonShiftRetireRallySeries()) host_ui_.Finish(*self);
  };
  rows[1].label = "KEEP CHAMPIONSHIP";
  rows[1].activate = [this, self] { host_ui_.Finish(*self); };
  auto screen = std::make_unique<MenuScreen>("RETIRE CHAMPIONSHIP?", std::move(rows));
  screen->set_body("End the unfinished championship and discard its current total. "
                   "Completed stage results and best times are kept.");
  screen->SetFocus(1);
  *self = screen.get();
  return screen;
}

}  // namespace

std::unique_ptr<hostui::MenuScreen> CreateSettingsMenu(hostui::HostUi& host_ui,
                                                       config::HostConfig& config,
                                                       SettingsServices services) {
  if (!config.Load()) {
    REXLOG_ERROR("Settings: cannot read {}; changes will not be saved", rex::path_to_utf8(config.path()));
  }
  return std::make_shared<SettingsPages>(host_ui, config, std::move(services))->Root();
}

std::unique_ptr<hostui::MenuScreen> CreateTrainerMenu(hostui::HostUi& host_ui,
                                                      config::HostConfig& config) {
  if (!config.Load()) {
    REXLOG_ERROR("Trainer: cannot read {}; changes will not be saved", rex::path_to_utf8(config.path()));
  }
  return std::make_shared<SettingsPages>(host_ui, config, SettingsServices{})->Trainer();
}

void ApplyMasterVolume() {
  const int volume = std::clamp(REXCVAR_GET(pinyon_shift_master_volume), 0, 100);
  // Squared so equal steps sound roughly even.
  const float linear = float(volume) / 100.0f;
  rex::audio::SetOutputGain(linear * linear);
}

}  // namespace pinyon_shift::ui
