#include "ui/music.h"

#include <algorithm>
#include <cctype>

#include <rex/audio/host_music.h>
#include <rex/cvar.h>
#include <rex/kernel/xam/apps/xmp_app.h>
#include <rex/logging.h>

#include "pinyon_shift_diagnostics.h"

REXCVAR_DEFINE_BOOL(pinyon_shift_music, false, "Audio",
                    "Your music: play the MP3 and WAV files in pinyon_shift_music_folder "
                    "instead of the game's radio, which the game then mutes")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_STRING(pinyon_shift_music_folder, "", "Audio",
                      "The folder (and its subfolders) your music plays from; empty: "
                      "<state>/music")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_BOOL(pinyon_shift_music_shuffle, false, "Audio",
                    "Play your music in a random order")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_INT32(pinyon_shift_music_volume, 80, "Audio", "Your music's volume, 0 to 100")
    .range(0, 100)
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

namespace pinyon_shift::music {

namespace {

std::string Upper(std::string text) {
  std::transform(text.begin(), text.end(), text.begin(),
                 [](unsigned char c) { return char(std::toupper(c)); });
  return text;
}

// The note under the AUDIO page fits the page's width (#420).
constexpr size_t kStatusWidth = 52;

std::string Fit(std::string text) {
  if (text.size() > kStatusWidth) text = text.substr(0, kStatusWidth - 3) + "...";
  return text;
}

// The state's own folder by name; another one by its last two parts.
std::string ShortFolder() {
  if (REXCVAR_GET(pinyon_shift_music_folder).empty()) return "THE STATE'S MUSIC FOLDER";
  const auto folder = Folder();
  const auto parent = folder.parent_path().filename();
  return Upper((parent.empty() ? folder.filename() : parent / folder.filename()).string());
}

std::filesystem::path g_playing_folder;
constexpr const char* kSettings[] = {"pinyon_shift_music", "pinyon_shift_music_folder",
                                     "pinyon_shift_music_shuffle", "pinyon_shift_music_volume"};

void Apply() {
  auto& player = rex::audio::HostMusicPlayer::Get();
  player.SetVolume(float(REXCVAR_GET(pinyon_shift_music_volume)) / 100.0f);
  player.SetShuffle(REXCVAR_GET(pinyon_shift_music_shuffle));
  if (!REXCVAR_GET(pinyon_shift_music)) {
    if (!g_playing_folder.empty()) {
      player.Stop();
      g_playing_folder.clear();
    }
    return;
  }
  const auto folder = Folder();
  if (folder == g_playing_folder) return;
  std::error_code error;
  std::filesystem::create_directories(folder, error);
  g_playing_folder = folder;
  const bool playing = player.Play(folder);
  diagnostics::RecordEvent("music.started",
                           {{"folder", folder.string()},
                            {"tracks", std::to_string(player.GetStatus().count)},
                            {"playing", playing ? "1" : "0"}});
}

}  // namespace

std::filesystem::path Folder() {
  const std::string folder = REXCVAR_GET(pinyon_shift_music_folder);
  return folder.empty() ? diagnostics::StateRoot() / "music" : std::filesystem::path(folder);
}

void Install(std::function<void(std::function<void()>)> post_to_ui) {
  rex::audio::HostMusicPlayer::Get().SetActiveCallback([](bool active) {
    if (auto* xmp = rex::kernel::xam::apps::XmpApp::Get()) {
      xmp->SetHostPlayback(active);
    }
    diagnostics::RecordEvent("music.active", {{"active", active ? "1" : "0"}});
  });
  for (const char* name : kSettings) {
    rex::cvar::RegisterChangeCallback(name, [post_to_ui](std::string_view, std::string_view) {
      post_to_ui(Apply);
    });
  }
  Apply();
}

void Shutdown() {
  for (const char* name : kSettings) rex::cvar::UnregisterChangeCallbacks(name);
  auto& player = rex::audio::HostMusicPlayer::Get();
  player.SetActiveCallback(nullptr);
  player.Close();
  g_playing_folder.clear();
}

std::string StatusLine() {
  if (!REXCVAR_GET(pinyon_shift_music)) {
    return Fit("MP3 AND WAV FILES FROM " + ShortFolder());
  }
  const auto status = rex::audio::HostMusicPlayer::Get().GetStatus();
  if (!status.count) {
    return Fit("NO MP3 OR WAV FILES IN " + ShortFolder());
  }
  return Fit(std::string(status.paused ? "PAUSED " : "PLAYING ") +
             std::to_string(status.index + 1) + "/" + std::to_string(status.count) + ": " +
             Upper(status.title));
}

void Next() {
  if (REXCVAR_GET(pinyon_shift_music)) rex::audio::HostMusicPlayer::Get().Next();
}

void Previous() {
  if (REXCVAR_GET(pinyon_shift_music)) rex::audio::HostMusicPlayer::Get().Previous();
}

}  // namespace pinyon_shift::music
