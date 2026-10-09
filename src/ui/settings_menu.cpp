#include "ui/settings_menu.h"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <optional>
#include <memory>
#include <cctype>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

#include <filesystem>

#include <rex/audio/downmix.h>
#include <rex/input/pad_remap.h>
#if defined(__ANDROID__)
#include <rex/ui/vulkan/android_gpu_driver.h>
#endif

#include "cheats.h"
#include "mod/mod_host.h"
#include "pinyon_shift_diagnostics.h"
#include "pinyon_shift_runtime_hooks.h"
#include <rex/cvar.h>
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
  MenuRow Page(std::string label, std::unique_ptr<MenuScreen> (SettingsPages::*page)());
  std::function<std::string()> RestartNote(std::vector<MenuRow>& rows);
  void Save();

  std::unique_ptr<MenuScreen> Display();
  std::unique_ptr<MenuScreen> Graphics();
  std::unique_ptr<MenuScreen> Audio();
  std::unique_ptr<MenuScreen> Controls();
  std::unique_ptr<MenuScreen> Profile();
  std::unique_ptr<MenuScreen> Gamertag();
  std::unique_ptr<MenuScreen> Backups();
  std::unique_ptr<MenuScreen> ControllerButtons();
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
  row.adjust = [this, shared](int direction) {
    const auto& choices = *shared;
    const int count = int(choices.size());
    const int current = Find(choices, [this](const std::string& name) { return Saved(name); });
    const int next = current < 0 ? 0 : (current + direction + count) % count;
    for (const auto& [name, literal] : choices[size_t(next)].values) {
      config_.Set(name, literal);
      if (!NeedsRestart(name)) {
        rex::cvar::SetFlagByName(name, Unquote(literal));
      }
    }
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
  const bool fsr = SameValue(Unquote(Saved("present_effect")), "fsr");
  if (output_width * output_height > render_width * render_height) {
    return line + (fsr ? ", FSR 1 UPSCALES TO " : ", STRETCHED TO ") +
           size(output_width, output_height);
  }
  return line + ", DOWNSCALED TO " + size(output_width, output_height);
}

void SettingsPages::Save() {
  if (!config_.Save()) {
    REXLOG_ERROR("Settings: could not write {}", config_.path().string());
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
  rows.push_back(Toggle("VSYNC", "vsync"));
  rows.push_back(Setting("FRAME RATE LIMIT",
                         {{"OFF", {{"host_present_fps_limit", "0"}}},
                          {"30", {{"host_present_fps_limit", "30"}}},
                          {"60", {{"host_present_fps_limit", "60"}}},
                          {"120", {{"host_present_fps_limit", "120"}}},
                          {"240", {{"host_present_fps_limit", "240"}}}}));
  // How the rendered image is scaled to the window: FSR 1 and CAS keep 2x
  // on a 4K display and 3x on 1440p sharp where bilinear blurs. The page's
  // note gives both sizes.
  rows.push_back(Setting("OUTPUT SCALING",
                         {{"BILINEAR", {{"present_effect", "\"bilinear\""}}},
                          {"CAS", {{"present_effect", "\"cas\""}}},
                          {"FSR 1", {{"present_effect", "\"fsr\""}}}}));
  // The rate the game simulates and renders at, which sets every CPU cost
  // (LS-1.4). DISPLAY follows the refresh rate: 144 Hz and faster displays
  // then render that many frames. 40 is an even third of 120 Hz (LS-1.6).
  rows.push_back(Setting("GAME FRAME RATE LIMIT",
                         {{"DISPLAY", {{"pinyon_shift_fh1_render_fps_limit", "0"}}},
                          {"30", {{"pinyon_shift_fh1_render_fps_limit", "30"}}},
                          {"40", {{"pinyon_shift_fh1_render_fps_limit", "40"}}},
                          {"60", {{"pinyon_shift_fh1_render_fps_limit", "60"}}},
                          {"120", {{"pinyon_shift_fh1_render_fps_limit", "120"}}}}));
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
    return ResolutionLine();
  };
  return std::make_unique<MenuScreen>("DISPLAY", std::move(rows), std::move(note));
}

std::unique_ptr<MenuScreen> SettingsPages::Graphics() {
  std::vector<MenuRow> rows;
  // PB-5: whole setups at once; any other combination reads CUSTOM. All
  // render on Vulkan with the split GPU commands thread.
#if defined(__ANDROID__)
  // AP-7.5: a handheld renders at 1x (AP-2.5) and trades frame rate for
  // battery and heat. QUALITY 30 is the Xbox 360's own rate (the guest
  // vblank at 60 Hz) with the game's 4x MSAA and shadows; SMOOTH 60 doubles
  // it without MSAA or shadows: on the Odin 2 Portal (Turnip Gen8 V37) that
  // holds 60 fps in free roam and races at 15.5 ms of GPU a frame, where 4x
  // with shadows takes about 27 ms. Both draw FH1's tiles in one pass and
  // redraw the reflection cubemap at a quarter of the game's rate (no
  // visible change), scale to the panel bilinearly and keep the game's own
  // anisotropic filtering: FSR 1 at the panel's 2400x1504 cost 1.4 ms a
  // frame and forced 4x anisotropy 0.4 ms, measured by alternating each in
  // one run.
  rows.push_back(Setting("GRAPHICS PRESET",
                         {{"QUALITY 30",
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
                            {"host_present_fps_limit", "0"},
                            {"pinyon_shift_fh1_render_fps_limit", "30"}}},
                          {"SMOOTH 60",
                           {{"gpu_backend", "\"vulkan\""},
                            {"gpu_record_thread", "true"},
                            {"draw_resolution_scale_x", "1"},
                            {"draw_resolution_scale_y", "1"},
                            {"present_effect", "\"bilinear\""},
                            {"anisotropic_override", "-1"},
                            {"fh1_msaa_single_sample", "true"},
                            {"fh1_untile_predicated_tiling", "true"},
                            {"pinyon_shift_fh1_env_map_rate", "0.25"},
                            {"pinyon_shift_fh1_shadows", "false"},
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
        const std::string name = it->path().filename().string();
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
        {"pinyon_shift_fh1_render_fps_limit", fps}};
    values.insert(values.end(), extra.begin(), extra.end());
    return values;
  };
  const std::vector<std::pair<std::string, std::string>> cheapest = {
      {"anisotropic_override", "-1"}, {"swap_post_effect", "\"none\""}};
  rows.push_back(Setting(
      "GRAPHICS PRESET",
      {{"LOW-SPEC 60", preset("1", "\"bilinear\"", "true", "60", cheapest)},
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
  // FXAA over the finished frame; the game's MSAA is its own row.
  rows.push_back(Setting("POST-PROCESS AA",
                         {{"OFF", {{"swap_post_effect", "\"none\""}}},
                          {"FXAA", {{"swap_post_effect", "\"fxaa\""}}},
                          {"FXAA EXTREME", {{"swap_post_effect", "\"fxaa_extreme\""}}}}));
  // The sun's shadows: off drops the shadow maps, a depth pre-pass and the
  // screen's shadow mask (about 6 ms a frame on the Odin 2 Portal) and
  // lights everything. Applies on the next frame.
  rows.push_back(Toggle("SHADOWS", "pinyon_shift_fh1_shadows"));
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

std::unique_ptr<MenuScreen> SettingsPages::Audio() {
  std::vector<MenuRow> rows;
  std::vector<Choice> volumes;
  for (int volume = 0; volume <= 100; volume += 10) {
    volumes.push_back({std::to_string(volume), {{"pinyon_shift_master_volume",
                                                 std::to_string(volume)}}});
  }
  rows.push_back(Setting("MASTER VOLUME", std::move(volumes)));
  rows.push_back(Toggle("MUTE", "audio_mute"));
  return std::make_unique<MenuScreen>("AUDIO", std::move(rows));
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

std::unique_ptr<MenuScreen> SettingsPages::Mods() {
  // One row per folder in <state>/mods, switched on and off in enabled_mods
  // (at the next start); the note under the list is the focused mod's state.
  std::vector<std::string> names;
  std::error_code error;
  for (auto it = std::filesystem::directory_iterator(services_.mods_root, error);
       !error && it != std::filesystem::directory_iterator(); it.increment(error)) {
    if (it->is_directory(error)) names.push_back(it->path().filename().string());
  }
  std::sort(names.begin(), names.end());
  const auto enabled_list = [this] {
    std::vector<std::string> list;
    std::string text = Unquote(Saved("enabled_mods"));
    size_t start = 0;
    while (start <= text.size()) {
      const size_t comma = text.find(',', start);
      std::string name = text.substr(start, comma == std::string::npos ? std::string::npos
                                                                       : comma - start);
      if (!name.empty()) list.push_back(name);
      if (comma == std::string::npos) break;
      start = comma + 1;
    }
    return list;
  };
  std::vector<MenuRow> rows;
  for (const auto& name : names) {
    MenuRow row;
    row.label = Upper(name);
    row.restart_required = true;
    row.value = [enabled_list, name] {
      const auto list = enabled_list();
      return std::string(std::find(list.begin(), list.end(), name) != list.end() ? "ON" : "OFF");
    };
    row.adjust = [this, enabled_list, name](int) {
      auto list = enabled_list();
      const auto it = std::find(list.begin(), list.end(), name);
      if (it != list.end()) {
        list.erase(it);
      } else {
        list.push_back(name);
      }
      std::string text;
      for (const auto& entry : list) text += (text.empty() ? "" : ",") + entry;
      config_.Set("enabled_mods", config::Quote(text));
      Save();
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
  rows.push_back(Toggle("FREE CAMERA", "cheat_free_camera"));
  // The discount signs and barn finds not yet found, on the map and minimap
  // (NP-8.6).
  rows.push_back(Toggle("SHOW COLLECTIBLES", "cheat_show_collectibles"));
  return std::make_unique<MenuScreen>("WORLD", std::move(rows));
}

std::unique_ptr<MenuScreen> SettingsPages::TrainerVehicle() {
  // The pose the project hooks is the car's presentation transform; freezing
  // or moving the car needs the physics body, which is still to be located.
  std::vector<MenuRow> rows(2);
  rows[0].label = "FREEZE POSITION";
  rows[0].value = [] { return std::string("NOT YET"); };
  rows[0].enabled = [] { return false; };
  rows[1].label = "TELEPORT";
  rows[1].value = [] { return std::string("NOT YET"); };
  rows[1].enabled = [] { return false; };
  return std::make_unique<MenuScreen>("VEHICLE", std::move(rows), [] {
    return std::string("NEEDS THE CAR'S PHYSICS BODY, STILL TO BE FOUND");
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

std::unique_ptr<MenuScreen> SettingsPages::Controls() {
  std::vector<MenuRow> rows;
  MenuRow controller;
  controller.label = "CONTROLLER BUTTONS";
  controller.activate = [this] { host_ui_.Push(ControllerButtons()); };
  rows.push_back(std::move(controller));
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
      {"A", "keybind_a"},
      {"B", "keybind_b"},
      {"X", "keybind_x"},
      {"Y", "keybind_y"},
      {"LEFT TRIGGER", "keybind_left_trigger"},
      {"RIGHT TRIGGER", "keybind_right_trigger"},
      {"LEFT BUMPER", "keybind_left_shoulder"},
      {"RIGHT BUMPER", "keybind_right_shoulder"},
      {"STEER LEFT", "keybind_lstick_left"},
      {"STEER RIGHT", "keybind_lstick_right"},
      {"BACK", "keybind_back"},
      {"START", "keybind_start"},
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
  reset.activate = [this] {
    for (const auto& [label, name] : binds) {
      (void)label;
      if (const auto* info = rex::cvar::GetFlagInfo(name)) {
        config_.Set(name, config::Quote(info->default_value));
        rex::cvar::SetFlagByName(name, info->default_value);
      }
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
    REXLOG_ERROR("Settings: cannot read {}; changes will not be saved", config.path().string());
  }
  return std::make_shared<SettingsPages>(host_ui, config, std::move(services))->Root();
}

std::unique_ptr<hostui::MenuScreen> CreateTrainerMenu(hostui::HostUi& host_ui,
                                                      config::HostConfig& config) {
  if (!config.Load()) {
    REXLOG_ERROR("Trainer: cannot read {}; changes will not be saved", config.path().string());
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
