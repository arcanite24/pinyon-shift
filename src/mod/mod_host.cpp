#include "mod/mod_host.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <cstring>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <fstream>
#include <span>

#include <fmt/format.h>

#include <toml++/toml.hpp>

#include <rex/cvar.h>
#include <rex/kernel/xam/ui_provider.h>
#include <rex/logging.h>
#include <rex/platform/dynlib.h>
#include <rex/ppc/func.h>
#include <rex/system/kernel_state.h>
#include <rex/system/thread_state.h>
#include <rex/system/xmemory.h>
#include <rex/ui/keybinds.h>

#include "cheats.h"
#include "config/host_config.h"
#include "pinyon_shift_diagnostics.h"
#include "ui/ui_strings.h"

namespace pinyon_shift::mod {
namespace {

// ---- Symbol table (NP-7.2) --------------------------------------------------

struct SymbolEntry {
  const char* name;
  uint32_t address;
};
struct OffsetEntry {
  const char* name;
  int32_t offset;
};

// The title-update build uses its own verified symbol table (TU-3).
#if defined(PINYON_SHIFT_TITLE_UPDATE_V4) && PINYON_SHIFT_TITLE_UPDATE_V4
#define PINYON_FH1_SYMBOLS "mod/fh1_symbols_v4.inc"
#else
#define PINYON_FH1_SYMBOLS "mod/fh1_symbols.inc"
#endif
#define PINYON_SYMBOL_EXECUTABLE(executable, sha256)
#define PINYON_SYMBOL(name, address) {name, address},
#define PINYON_OFFSET(name, offset)
constexpr SymbolEntry kSymbols[] = {
#include PINYON_FH1_SYMBOLS
};
#undef PINYON_SYMBOL
#undef PINYON_OFFSET
#define PINYON_SYMBOL(name, address)
#define PINYON_OFFSET(name, offset) {name, offset},
constexpr OffsetEntry kOffsets[] = {
#include PINYON_FH1_SYMBOLS
};
#undef PINYON_SYMBOL
#undef PINYON_OFFSET
#undef PINYON_SYMBOL_EXECUTABLE
#define PINYON_SYMBOL_EXECUTABLE(executable, sha256) constexpr const char* kExecutableSha = sha256;
#define PINYON_SYMBOL(name, address)
#define PINYON_OFFSET(name, offset)
#include PINYON_FH1_SYMBOLS
#undef PINYON_SYMBOL
#undef PINYON_OFFSET
#undef PINYON_SYMBOL_EXECUTABLE

// ---- Hooks and guest tasks (NP-7.1) -----------------------------------------

struct Subscriber {
  uint64_t handle;
  PinyonHookCallback callback;
  void* user;
};
constexpr size_t kHookSlots = 7;  // PinyonHook values 1-6
std::mutex g_subscribers_mutex;
std::array<std::vector<Subscriber>, kHookSlots> g_subscribers;
std::array<std::atomic<uint32_t>, kHookSlots> g_subscriber_counts{};
uint64_t g_next_handle = 1;

std::mutex g_tasks_mutex;
std::vector<std::pair<PinyonGuestTask, void*>> g_tasks;
std::vector<std::function<void()>> g_host_tasks;
std::atomic<bool> g_tasks_pending{false};
thread_local bool g_in_guest_task = false;

// ---- Loaded mods ------------------------------------------------------------

struct LoadedMod {
  ModInfo info;
  std::string name;
  std::string directory;
  rex::platform::DynamicLibrary library;
  PinyonModApi api{};
  PinyonMod mod{};
  std::vector<std::string> hide_dlc;
};
std::vector<std::unique_ptr<LoadedMod>> g_loaded;
std::vector<ModInfo> g_mods;
HostServices g_services;
std::map<std::string, std::unique_ptr<std::string>, std::less<>> g_mod_cvars;
std::filesystem::path g_modded_user_root;

std::mutex g_ui_mutex;
std::map<uint32_t, HudLabel> g_hud_labels;
std::vector<MenuAction> g_menu_actions;
std::function<void()> g_hud_changed;

uint64_t Fnv1a(const uint8_t* data, size_t size, uint64_t hash = 0xCBF29CE484222325ull) {
  for (size_t i = 0; i < size; ++i) {
    hash = (hash ^ data[i]) * 0x100000001B3ull;
  }
  return hash;
}

std::string JsonString(std::string_view text) {
  std::string out = "\"";
  for (char c : text) {
    if (c == '"' || c == '\\') out += '\\';
    if (static_cast<unsigned char>(c) >= 0x20) out += c;
  }
  return out + "\"";
}

// ---- The API table ------------------------------------------------------------

void ApiLog(PinyonLogLevel level, const char* text) {
  const char* safe = text ? text : "";
  switch (level) {
    case PINYON_LOG_DEBUG:
      REXLOG_DEBUG("Mod: {}", safe);
      break;
    case PINYON_LOG_WARNING:
      REXLOG_WARN("Mod: {}", safe);
      break;
    case PINYON_LOG_ERROR:
      REXLOG_ERROR("Mod: {}", safe);
      break;
    default:
      REXLOG_INFO("Mod: {}", safe);
      break;
  }
}

void ApiLogEvent(const char* event, const char* const* keys, const char* const* values,
                 uint32_t count) {
  std::vector<diagnostics::Field> fields;
  for (uint32_t i = 0; keys && values && i < count; ++i) {
    fields.emplace_back(keys[i] ? keys[i] : "", values[i] ? values[i] : "");
  }
  diagnostics::RecordEvent(std::string("mod.") + (event ? event : "event"),
                           std::span<const diagnostics::Field>(fields));
}

bool GuestRangeValid(uint32_t address, uint32_t size) {
  return address >= 0x10000 && uint64_t(address) + size <= 0x100000000ull;
}

int ApiReadGuest(uint32_t address, void* out, uint32_t size) {
  auto* kernel_state = rex::system::kernel_state();
  if (!kernel_state || !out || !GuestRangeValid(address, size)) return -1;
  std::memcpy(out, kernel_state->memory()->TranslateVirtual(address), size);
  return 0;
}

int ApiWriteGuest(uint32_t address, const void* data, uint32_t size) {
  auto* kernel_state = rex::system::kernel_state();
  if (!kernel_state || !data || !GuestRangeValid(address, size)) return -1;
  std::memcpy(kernel_state->memory()->TranslateVirtual(address), data, size);
  return 0;
}

uint32_t ApiFindSymbol(const char* name) {
  if (!name) return 0;
  for (const auto& symbol : kSymbols) {
    if (std::strcmp(symbol.name, name) == 0) return symbol.address;
  }
  return 0;
}

int32_t ApiFindOffset(const char* name) {
  if (!name) return -1;
  for (const auto& offset : kOffsets) {
    if (std::strcmp(offset.name, name) == 0) return offset.offset;
  }
  return -1;
}

uint64_t ApiSubscribe(uint32_t hook, PinyonHookCallback callback, void* user) {
  if (hook == 0 || hook >= kHookSlots || !callback) return 0;
  std::lock_guard lock(g_subscribers_mutex);
  const uint64_t handle = g_next_handle++;
  g_subscribers[hook].push_back({handle, callback, user});
  g_subscriber_counts[hook].store(uint32_t(g_subscribers[hook].size()),
                                  std::memory_order_release);
  return handle;
}

void ApiUnsubscribe(uint64_t handle) {
  std::lock_guard lock(g_subscribers_mutex);
  for (size_t hook = 1; hook < kHookSlots; ++hook) {
    auto& list = g_subscribers[hook];
    list.erase(std::remove_if(list.begin(), list.end(),
                              [handle](const Subscriber& s) { return s.handle == handle; }),
               list.end());
    g_subscriber_counts[hook].store(uint32_t(list.size()), std::memory_order_release);
  }
}

void ApiEnqueueGuestTask(PinyonGuestTask task, void* user) {
  if (!task) return;
  std::lock_guard lock(g_tasks_mutex);
  g_tasks.emplace_back(task, user);
  g_tasks_pending.store(true, std::memory_order_release);
}

uint32_t ApiCallGuest(uint32_t address, const uint32_t* args, uint32_t count) {
  if (!g_in_guest_task) {
    REXLOG_ERROR("Mod: call_guest outside a guest task is ignored");
    return 0;
  }
  auto* kernel_state = rex::system::kernel_state();
  if (!kernel_state || !kernel_state->function_dispatcher()->GetFunction(address)) return 0;
  // Kernel callbacks (including file completion while loading an audio bank)
  // use ThreadState's live context. Dispatch on that same context and restore
  // it through the SDK trap frame instead of passing an unbound local copy.
  uint64_t values[6]{};
  for (uint32_t i = 0; i < 6; ++i) {
    values[i] = (args && i < count) ? args[i] : 0;
  }
  return uint32_t(kernel_state->function_dispatcher()->ExecuteTrap(
      rex::runtime::ThreadState::Get(), address, values, 6));
}

int ApiRegisterCvar(const char* name, const char* default_value, const char* description) {
  if (!name || !*name) return -1;
  std::string key = name;
  if (g_mod_cvars.count(key)) return -1;
  auto storage = std::make_unique<std::string>(default_value ? default_value : "");
  std::string* value = storage.get();
  rex::cvar::FlagEntry entry;
  entry.name = key;
  entry.type = rex::cvar::FlagType::String;
  entry.category = "Mods";
  entry.description = description ? description : "";
  entry.default_value = *value;
  entry.setter = [value](std::string_view v) {
    *value = std::string(v);
    return true;
  };
  entry.getter = [value] { return *value; };
  if (!rex::cvar::RegisterFlag(std::move(entry)).has_value()) return -1;
  g_mod_cvars.emplace(key, std::move(storage));
  // Registered after the settings file was read: apply its saved value.
  if (g_services.config) {
    if (auto saved = g_services.config->Get(key)) {
      rex::cvar::SetFlagByName(key, *saved);
    }
  }
  return 0;
}

bool FlagExists(std::string_view name) {
  for (const auto& entry : rex::cvar::GetRegistry()) {
    if (entry.name == name) return true;
  }
  return false;
}

int ApiGetCvar(const char* name, char* out, uint32_t out_size) {
  if (!name || !out || !out_size || !FlagExists(name)) return -1;
  const std::string value = rex::cvar::GetFlagByName(name);
  const size_t length = std::min<size_t>(value.size(), out_size - 1);
  std::memcpy(out, value.data(), length);
  out[length] = '\0';
  return value.size() < out_size ? 0 : 1;
}

int ApiSetCvar(const char* name, const char* value) {
  if (!name || !value) return -1;
  return rex::cvar::SetFlagByName(name, value) ? 0 : -1;
}

int ApiRegisterBind(const char* name, const char* default_key, const char* description,
                    PinyonBindCallback callback, void* user) {
  if (!name || !callback) return -1;
  rex::ui::RegisterBind(name, default_key ? default_key : "", description ? description : "",
                        [callback, user] { callback(user); });
  return 0;
}

void ApiShowDialog(const char* title, const char* text, const char* const* buttons,
                   uint32_t button_count, PinyonDialogCallback callback, void* user) {
  std::vector<std::string> labels;
  for (uint32_t i = 0; buttons && i < button_count; ++i) {
    labels.emplace_back(buttons[i] ? buttons[i] : "");
  }
  auto* provider = rex::kernel::xam::GetXamUiProvider();
  if (!provider || !g_services.post_to_ui) {
    if (callback) callback(user, UINT32_MAX);
    return;
  }
  g_services.post_to_ui([provider, title = std::string(title ? title : ""),
                         text = std::string(text ? text : ""), labels, callback, user] {
    provider->ShowMessageBox(title, text, labels, 0, [callback, user](uint32_t button) {
      if (callback) callback(user, button);
    });
  });
}

void ApiSetHudText(uint32_t id, const char* text, float x, float y, float size) {
  std::function<void()> changed;
  {
    std::lock_guard lock(g_ui_mutex);
    const uint32_t key = id;
    if (!text || !*text) {
      g_hud_labels.erase(key);
    } else {
      g_hud_labels[key] = HudLabel{text, std::clamp(x, 0.0f, 1280.0f),
                                   std::clamp(y, 0.0f, 720.0f), std::clamp(size, 8.0f, 96.0f)};
    }
    changed = g_hud_changed;
  }
  if (changed) changed();
}

int ApiAddMenuAction(const char* label, PinyonBindCallback callback, void* user) {
  if (!label || !callback) return -1;
  std::lock_guard lock(g_ui_mutex);
  g_menu_actions.push_back(MenuAction{label, callback, user});
  return 0;
}

int ApiSetUiString(const char* table, uint32_t key, const char* text) {
  if (!table || !*table || !text || key > 0xFFFEu) return -1;
  ui::SetUiString(table, static_cast<uint16_t>(key), ui::Utf8ToUtf16(text));
  diagnostics::RecordEvent("mod.ui_string",
                           {{"table", table}, {"key", fmt::format("{:04X}", key)}});
  return 0;
}

// ---- Discovery ----------------------------------------------------------------

std::vector<std::string> SplitList(const std::string& text) {
  std::vector<std::string> names;
  size_t start = 0;
  while (start <= text.size()) {
    const size_t comma = text.find(',', start);
    std::string name = text.substr(start, comma == std::string::npos ? std::string::npos
                                                                     : comma - start);
    name.erase(0, name.find_first_not_of(" \t"));
    name.erase(name.find_last_not_of(" \t") + 1);
    if (!name.empty() && std::find(names.begin(), names.end(), name) == names.end()) {
      names.push_back(name);
    }
    if (comma == std::string::npos) break;
    start = comma + 1;
  }
  return names;
}

std::vector<std::string> StringArray(const toml::table& table, std::string_view key) {
  std::vector<std::string> values;
  if (const auto* array = table[key].as_array()) {
    for (const auto& element : *array) {
      if (auto value = element.value<std::string>()) values.push_back(*value);
    }
  }
  return values;
}

struct Manifest {
  std::string version;
  std::filesystem::path library;
  std::vector<std::string> requires_mods, load_after, conflicts;
  std::vector<std::string> hide_dlc;  // marketplace package IDs
  std::string profile;                // its own save tree, user-<profile>
  bool shares_save = false;           // visual only: keeps the player's save
};

bool ValidName(const std::string& name) {
  return !name.empty() && name.size() <= 64 &&
         std::all_of(name.begin(), name.end(), [](unsigned char c) {
           return std::isalnum(c) || c == '_' || c == '-';
         });
}

std::string ReadManifest(const std::string& name, const std::filesystem::path& directory,
                         Manifest& manifest) {
  if (!ValidName(name)) return "the name may only use letters, digits, _ and -";
  toml::table table;
  try {
    table = toml::parse_file((directory / "mod.toml").string());
  } catch (const toml::parse_error& error) {
    return "mod.toml cannot be read: " + std::string(error.description());
  }
  if (table["name"].value_or(std::string()) != name) return "mod.toml names another mod";
  if (table["abi"].value_or(int64_t(0)) != int64_t(PINYON_MOD_ABI_VERSION)) {
    return "mod.toml asks for another mod ABI version";
  }
  // game_version names the executable(s) a mod was made for: one prefix, or
  // a list when it supports several builds (the base disc and the v4 title
  // update have separate symbol tables, so name-based mods can target both).
  const auto matches = [](const std::string& game) {
    return game.empty() || std::string_view(kExecutableSha).rfind(game, 0) == 0 ||
           game.rfind(kExecutableSha, 0) == 0;
  };
  if (const auto* games = table["game_version"].as_array()) {
    bool supported = false;
    for (const auto& entry : *games) {
      const auto game = entry.value<std::string>();
      if (!game) return "mod.toml game_version lists a non-string entry";
      supported = supported || matches(*game);
    }
    if (!supported) return "made for another game executable";
  } else if (!matches(table["game_version"].value_or(std::string()))) {
    return "made for another game executable";
  }
  manifest.version = table["version"].value_or(std::string("0"));
  // No library: an asset-only mod (just game/ files).
  if (auto library = table["library"].value<std::string>()) {
    manifest.library = directory / *library;
  }
  manifest.requires_mods = StringArray(table, "requires");
  manifest.load_after = StringArray(table, "load_after");
  manifest.conflicts = StringArray(table, "conflicts");
  manifest.hide_dlc = StringArray(table, "hide_dlc");
  manifest.profile = table["profile"].value_or(std::string());
  manifest.shares_save = table["shares_save"].value_or(false);
  if (!manifest.profile.empty() && !ValidName(manifest.profile)) {
    return "mod.toml profile may only use letters, digits, _ and -";
  }
  for (const auto& package : manifest.hide_dlc) {
    if (package.empty() || package.size() > 42 ||
        !std::all_of(package.begin(), package.end(),
                     [](unsigned char c) { return std::isxdigit(c); })) {
      return "mod.toml hide_dlc lists something other than a package ID";
    }
  }
  return {};
}

}  // namespace

bool HasSubscribers(PinyonHook hook) {
  const size_t index = size_t(hook);
  return index < kHookSlots && g_subscriber_counts[index].load(std::memory_order_acquire);
}

void Dispatch(const PinyonHookEvent& event) {
  const size_t index = event.hook;
  if (index >= kHookSlots || !g_subscriber_counts[index].load(std::memory_order_acquire)) {
    return;
  }
  std::vector<Subscriber> subscribers;
  {
    std::lock_guard lock(g_subscribers_mutex);
    subscribers = g_subscribers[index];
  }
  for (const auto& subscriber : subscribers) {
    subscriber.callback(subscriber.user, &event);
  }
}

void RunGuestTasks() {
  if (!g_tasks_pending.load(std::memory_order_acquire)) return;
  std::vector<std::pair<PinyonGuestTask, void*>> tasks;
  std::vector<std::function<void()>> host_tasks;
  {
    std::lock_guard lock(g_tasks_mutex);
    tasks.swap(g_tasks);
    host_tasks.swap(g_host_tasks);
    g_tasks_pending.store(false, std::memory_order_release);
  }
  g_in_guest_task = true;
  for (const auto& task : host_tasks) {
    task();
  }
  for (const auto& [task, user] : tasks) {
    task(user);
  }
  g_in_guest_task = false;
}

void EnqueueHostGuestTask(std::function<void()> task) {
  if (!task) return;
  std::lock_guard lock(g_tasks_mutex);
  g_host_tasks.push_back(std::move(task));
  g_tasks_pending.store(true, std::memory_order_release);
}

uint32_t CallGuest(uint32_t address, std::initializer_list<uint32_t> args) {
  const std::vector<uint32_t> values(args);
  return ApiCallGuest(address, values.data(), uint32_t(values.size()));
}

std::string RequestedProfile(const std::filesystem::path& state_root,
                             const std::string& enabled_mods) {
  for (const auto& name : SplitList(enabled_mods)) {
    Manifest manifest;
    if (ReadManifest(name, state_root / "mods" / name, manifest).empty() &&
        !manifest.profile.empty()) {
      return manifest.profile;
    }
  }
  return {};
}

bool ModsShareSave(const std::filesystem::path& state_root, const std::string& enabled_mods) {
  const auto names = SplitList(enabled_mods);
  if (names.empty()) return false;
  for (const auto& name : names) {
    Manifest manifest;
    if (!ReadManifest(name, state_root / "mods" / name, manifest).empty() ||
        !manifest.shares_save || !manifest.profile.empty()) {
      return false;
    }
  }
  return true;
}

void LoadMods(const std::filesystem::path& state_root, const std::string& enabled_mods,
              HostServices services) {
  g_services = std::move(services);
  const std::vector<std::string> enabled = SplitList(enabled_mods);
  std::map<std::string, Manifest> manifests;
  for (const auto& name : enabled) {
    ModInfo info;
    info.name = name;
    info.directory = state_root / "mods" / name;
    Manifest manifest;
    info.problem = ReadManifest(name, info.directory, manifest);
    info.version = manifest.version;
    if (info.problem.empty()) {
      for (const auto& other : manifest.conflicts) {
        if (std::find(enabled.begin(), enabled.end(), other) != enabled.end()) {
          info.problem = "conflicts with " + other;
        }
      }
      for (const auto& other : manifest.requires_mods) {
        if (std::find(enabled.begin(), enabled.end(), other) == enabled.end()) {
          info.problem = "requires " + other + ", which is not enabled";
        }
      }
    }
    if (info.problem.empty()) manifests.emplace(name, std::move(manifest));
    g_mods.push_back(std::move(info));
  }

  // Load order: after everything a mod requires or loads after; otherwise the
  // enabled_mods order. A mod whose requirement fails is not loaded either.
  std::vector<std::string> order;
  std::set<std::string> placed, visiting;
  std::function<bool(const std::string&)> place = [&](const std::string& name) -> bool {
    if (placed.count(name)) return true;
    if (!manifests.count(name) || visiting.count(name)) return false;
    visiting.insert(name);
    const Manifest& manifest = manifests.at(name);
    bool ok = true;
    for (const auto& before : manifest.requires_mods) ok = place(before) && ok;
    for (const auto& before : manifest.load_after) {
      if (manifests.count(before)) place(before);
    }
    visiting.erase(name);
    if (ok) {
      placed.insert(name);
      order.push_back(name);
    }
    return ok;
  };
  for (const auto& name : enabled) place(name);

  for (const auto& name : order) {
    auto info_it = std::find_if(g_mods.begin(), g_mods.end(),
                                [&](const ModInfo& info) { return info.name == name; });
    const Manifest& manifest = manifests.at(name);
    bool requirements_loaded = true;
    for (const auto& required : manifest.requires_mods) {
      requirements_loaded = requirements_loaded &&
                            std::any_of(g_loaded.begin(), g_loaded.end(), [&](const auto& mod) {
                              return mod->name == required;
                            });
    }
    if (!requirements_loaded) {
      info_it->problem = "a mod it requires did not load";
      continue;
    }
    auto loaded = std::make_unique<LoadedMod>();
    loaded->info = *info_it;
    loaded->name = name;
    loaded->directory = info_it->directory.string();
    loaded->hide_dlc = manifest.hide_dlc;
    if (manifest.library.empty()) {
      info_it->loaded = true;
      loaded->info.loaded = true;
      g_loaded.push_back(std::move(loaded));
      continue;
    }
    if (!loaded->library.Load(manifest.library)) {
      info_it->problem = "cannot load " + manifest.library.string();
      continue;
    }
    auto abi = loaded->library.GetSymbol<PinyonModAbiVersionFn>("rex_mod_abi_version");
    auto create = loaded->library.GetSymbol<PinyonModCreateFn>("rex_mod_create");
    if (!abi || !create) {
      info_it->problem = "the library does not export rex_mod_abi_version and rex_mod_create";
      continue;
    }
    if (abi() != PINYON_MOD_ABI_VERSION) {
      info_it->problem = "the library was built for another mod ABI version";
      continue;
    }
    PinyonModApi& api = loaded->api;
    api.abi_version = PINYON_MOD_ABI_VERSION;
    api.size = sizeof(PinyonModApi);
    api.mod_name = loaded->name.c_str();
    api.mod_directory = loaded->directory.c_str();
    api.log = ApiLog;
    api.log_event = ApiLogEvent;
    api.read_guest = ApiReadGuest;
    api.write_guest = ApiWriteGuest;
    api.find_symbol = ApiFindSymbol;
    api.find_offset = ApiFindOffset;
    api.subscribe = ApiSubscribe;
    api.unsubscribe = ApiUnsubscribe;
    api.enqueue_guest_task = ApiEnqueueGuestTask;
    api.call_guest = ApiCallGuest;
    api.register_cvar = ApiRegisterCvar;
    api.get_cvar = ApiGetCvar;
    api.set_cvar = ApiSetCvar;
    api.register_bind = ApiRegisterBind;
    api.show_dialog = ApiShowDialog;
    api.set_hud_text = ApiSetHudText;
    api.add_menu_action = ApiAddMenuAction;
    api.set_ui_string = ApiSetUiString;
    if (create(&loaded->api, &loaded->mod) != 0) {
      info_it->problem = "rex_mod_create failed";
      continue;
    }
    info_it->loaded = true;
    loaded->info.loaded = true;
    g_loaded.push_back(std::move(loaded));
  }

  for (const auto& info : g_mods) {
    if (info.loaded) {
      REXLOG_INFO("Mods: loaded {} {}", info.name, info.version);
      diagnostics::RecordEvent("mod.loaded", {{"name", info.name}, {"version", info.version}});
    } else {
      REXLOG_ERROR("Mods: {} was not loaded: {}", info.name, info.problem);
      diagnostics::RecordEvent("mod.rejected", {{"name", info.name}, {"reason", info.problem}});
    }
  }
}

const std::vector<ModInfo>& Mods() { return g_mods; }

std::vector<HudLabel> HudLabels() {
  std::lock_guard lock(g_ui_mutex);
  std::vector<HudLabel> labels;
  for (const auto& [key, label] : g_hud_labels) labels.push_back(label);
  return labels;
}

std::vector<MenuAction> MenuActions() {
  std::lock_guard lock(g_ui_mutex);
  return g_menu_actions;
}

void SetHudChangedCallback(std::function<void()> callback) {
  std::lock_guard lock(g_ui_mutex);
  g_hud_changed = std::move(callback);
}

void SetModdedProfile(std::filesystem::path user_root) { g_modded_user_root = std::move(user_root); }

bool ModdedProfile() { return !g_modded_user_root.empty(); }

std::string ModSetHash() {
  std::string text;
  for (const auto& mod : g_loaded) {
    text += mod->name + "@" + mod->info.version + ";";
  }
  return fmt::format("{:016X}", Fnv1a(reinterpret_cast<const uint8_t*>(text.data()), text.size()));
}

void RecordSave(uint32_t body_address, uint32_t body_size) {
  auto* kernel_state = rex::system::kernel_state();
  if (g_modded_user_root.empty() || !kernel_state || !GuestRangeValid(body_address, body_size)) {
    return;
  }
  const auto* body = kernel_state->memory()->TranslateVirtual<const uint8_t*>(body_address);
  std::string mods;
  for (const auto& mod : g_loaded) {
    if (!mods.empty()) mods += ",";
    mods += "{\"name\":" + JsonString(mod->name) + ",\"version\":" + JsonString(mod->info.version) +
            "}";
  }
  const std::string json = fmt::format(
      "{{\"schema\":1,\"mods\":[{}],\"mod_set\":\"{}\",\"cheats\":{},"
      "\"body_size\":{},\"body_fnv1a64\":\"{:016X}\"}}\n",
      mods, ModSetHash(), JsonString(cheats::Active()), body_size, Fnv1a(body, body_size));
  std::error_code error;
  std::filesystem::create_directories(g_modded_user_root, error);
  const auto path = g_modded_user_root / "pinyon_shift_mods.json";
  std::ofstream(path.string() + ".tmp", std::ios::binary | std::ios::trunc) << json;
  std::filesystem::rename(path.string() + ".tmp", path, error);
  diagnostics::RecordEvent("mod.save.tagged", {{"mod_set", ModSetHash()}});
}

bool AnyModLoaded() { return !g_loaded.empty(); }

std::vector<std::filesystem::path> OverlayRoots() {
  std::vector<std::filesystem::path> roots;
  std::error_code error;
  for (const auto& mod : g_loaded) {
    const auto root = mod->info.directory / "game";
    if (std::filesystem::is_directory(root, error)) roots.push_back(root);
  }
  return roots;
}

std::vector<std::string> HiddenDlc() {
  std::vector<std::string> packages;
  for (const auto& mod : g_loaded) {
    for (const auto& package : mod->hide_dlc) {
      if (std::find(packages.begin(), packages.end(), package) == packages.end()) {
        packages.push_back(package);
      }
    }
  }
  return packages;
}

std::vector<std::filesystem::path> TextureRoots() {
  std::vector<std::filesystem::path> roots;
  std::error_code error;
  for (const auto& mod : g_loaded) {
    const auto root = mod->info.directory / "textures";
    if (std::filesystem::is_directory(root, error)) roots.push_back(root);
  }
  return roots;
}

void NotifyCreateDialogs() {
  for (const auto& mod : g_loaded) {
    if (mod->mod.on_create_dialogs) mod->mod.on_create_dialogs(mod->mod.self);
  }
}

void NotifyModuleLaunched() {
  for (const auto& mod : g_loaded) {
    if (mod->mod.on_module_launched) mod->mod.on_module_launched(mod->mod.self);
  }
}

void NotifyShutdown() {
  // Once: the window-close path and OnShutdown both call it.
  static std::atomic<bool> notified{false};
  if (notified.exchange(true)) return;
  for (const auto& mod : g_loaded) {
    if (mod->mod.on_shutdown) mod->mod.on_shutdown(mod->mod.self);
  }
}

}  // namespace pinyon_shift::mod
