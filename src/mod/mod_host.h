#pragma once

#include <cstdint>
#include <filesystem>
#include <functional>
#include <initializer_list>
#include <string>
#include <vector>

#include "pinyon_mod.h"

namespace pinyon_shift::config {
class HostConfig;
}

namespace pinyon_shift::mod {

// Hook dispatch (NP-7.1), called from the title's hook sites on guest
// threads. Cheap when no mod subscribed.
bool HasSubscribers(PinyonHook hook);
void Dispatch(const PinyonHookEvent& event);
// Runs the guest tasks mods queued; at frame.tick, on the title's main thread.
void RunGuestTasks();
// The host's own guest work (the trainer), run with the mods' tasks.
void EnqueueHostGuestTask(std::function<void()> task);
// Calls a guest function with up to six integer arguments (r3 to r8) and
// returns r3; only inside a guest task.
uint32_t CallGuest(uint32_t address, std::initializer_list<uint32_t> args);

// What the host gives the mod host besides the files.
struct HostServices {
  config::HostConfig* config = nullptr;  // saved values of mods' own settings
  // Runs `task` on the UI thread (for dialogs).
  std::function<void(std::function<void()> task)> post_to_ui;
};

// Discovery, validation, loading and lifecycle of mods (NP-7.3).
struct ModInfo {
  std::string name;
  std::string version;
  std::filesystem::path directory;
  bool loaded = false;
  std::string problem;  // why it was not loaded
};

// Parses `enabled_mods`, validates each mods/<name>/mod.toml (ABI, game
// version, requires, conflicts), orders them (requires and load_after, else
// the list order), and loads their libraries. Mods are never unloaded.
void LoadMods(const std::filesystem::path& state_root, const std::string& enabled_mods,
              HostServices services);
// The save tree the first valid enabled mod asks for with `profile` in its
// mod.toml (the XE mod needs a new save, so it plays user-xe), or "" for the
// shared modded profile. Read before the mods load, while paths are chosen.
std::string RequestedProfile(const std::filesystem::path& state_root,
                             const std::string& enabled_mods);
// True when every enabled mod declares `shares_save = true` (it changes
// only how the game looks or sounds, never what it saves), so the player's
// own profile stays in use. The generated archive mod counts as its sources
// do; the generated database mod never shares the save.
bool ModsShareSave(const std::filesystem::path& state_root, const std::string& enabled_mods);
const std::vector<ModInfo>& Mods();
bool AnyModLoaded();
// Directories of loaded mods' game/ overrides, in priority order.
std::vector<std::filesystem::path> OverlayRoots();
// Marketplace packages that loaded mods cannot run with (mod.toml
// hide_dlc): the title neither lists nor opens them while those mods are on.
std::vector<std::string> HiddenDlc();
// Directories of loaded mods' textures/ replacements (<hash>.dds, NP-10.3),
// in priority order.
std::vector<std::filesystem::path> TextureRoots();

// Profile isolation (NP-7.5). With mods enabled the title plays the separate
// `user_root` profile (<state>/user-modded); each save then writes
// pinyon_shift_mods.json there with the enabled mods, the mod-set hash and
// the plaintext save body hash.
void SetModdedProfile(std::filesystem::path user_root);
bool ModdedProfile();
// At save.before_encrypt: tags the modded profile's save.
void RecordSave(uint32_t body_address, uint32_t body_size);
// A stable hash of the loaded mods' names and versions.
std::string ModSetHash();

// UI extensions (NP-11): HUD labels and menu actions mods registered.
struct HudLabel {
  std::string text;
  float x = 0.0f, y = 0.0f, size = 24.0f;
};
std::vector<HudLabel> HudLabels();
struct MenuAction {
  std::string label;
  PinyonBindCallback callback = nullptr;
  void* user = nullptr;
};
std::vector<MenuAction> MenuActions();
// Called (on any thread) when HUD labels change, so the host can draw them.
void SetHudChangedCallback(std::function<void()> callback);

void NotifyCreateDialogs();
void NotifyModuleLaunched();
void NotifyShutdown();

}  // namespace pinyon_shift::mod
