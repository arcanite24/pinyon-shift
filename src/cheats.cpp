#include "cheats.h"
#include "cheats_travel.h"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <mutex>

#include <fmt/format.h>

#include <rex/cvar.h>

#include "pinyon_shift_diagnostics.h"
#include "save/profile_body.h"

REXCVAR_DEFINE_BOOL(pinyon_shift_cheats, false, "Cheats",
                    "Enable the trainer (F10). The title then plays the separate modded profile "
                    "(<state>/user-modded), so cheated progress never reaches the player's own save")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);
REXCVAR_DEFINE_DOUBLE(cheat_time_scale, 1.0, "Cheats",
                      "Game speed: the title's gameplay delta is multiplied by this (0.25 to 2)")
    .range(0.25, 2.0)
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_DOUBLE(cheat_time_of_day, -1.0, "Cheats",
                      "Hold the time of day at this hour (0 to 24, fractions allowed); -1 lets "
                      "the title's clock run")
    .range(-1.0, 24.0)
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_DOUBLE(cheat_day_length_minutes, 0.0, "Cheats",
                      "How many real minutes 24 game hours last (1 to 1440); 0 keeps the "
                      "title's rate, -1 follows this PC's clock. Scripted times of day "
                      "still apply, and cheat_time_of_day wins over it")
    .range(-1.0, 1440.0)
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_BOOL(cheat_free_camera, false, "Cheats",
                    "Switch the cameras to the title's free camera (moved with the pad); off "
                    "returns them to the player")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_BOOL(cheat_any_car_events, false, "Cheats",
                    "Let any car enter any event: events load without their class, make, year "
                    "and other car limits; applies the next time an event's ticket loads")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_BOOL(cheat_fast_travel_anywhere, false, "Cheats",
                    "Allow the map's fast travel to any road, using the title's loading and "
                    "streaming sequence; races and scripted travel locks still apply")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_STRING(cheat_set_profile_fields, "", "Cheats",
                      "Set these profile fields when it next loads, once, as "
                      "Path/Name=value pairs separated by commas (for example "
                      "Main/XP=450000); \"\" leaves them. Main/CareerCar=0 alone "
                      "recovers the isolated profile without enabling the trainer")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);
REXCVAR_DEFINE_INT32(cheat_set_credits, -1, "Cheats",
                     "Set the profile's credits to this, once: at once while it is loaded, "
                     "else when it next loads; -1 leaves them")
    .range(-1, 999999999)
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

namespace pinyon_shift::cheats {

namespace {
std::atomic<bool> g_profile_isolated{false};
std::atomic<bool> g_credits_applied{false};
std::atomic<int32_t> g_set_credits_value{-1};
std::atomic<bool> g_fields_applied{false};
std::mutex g_fields_mutex;
std::string g_fields_value;
std::mutex g_applied_mutex;
std::function<void(std::string_view)> g_applied;
// Live credits changes waiting for the running profile, and what they did.
std::mutex g_credits_mutex;
CreditsChange g_credits_change;
std::atomic<bool> g_credits_pending{false};
std::atomic<int64_t> g_credits_added{0};

void CallApplied(std::string_view setting) {
  std::function<void(std::string_view)> applied;
  {
    std::lock_guard lock(g_applied_mutex);
    applied = g_applied;
  }
  if (applied) applied(setting);
}

void StoreBe32(uint8_t* bytes, uint32_t value) {
  bytes[0] = uint8_t(value >> 24);
  bytes[1] = uint8_t(value >> 16);
  bytes[2] = uint8_t(value >> 8);
  bytes[3] = uint8_t(value);
}
}  // namespace

bool Requested() { return REXCVAR_GET(pinyon_shift_cheats); }

bool CarRecoveryRequested() {
  return REXCVAR_GET(cheat_set_profile_fields) == kCarRecoveryFields;
}

void SetProfileIsolated() { g_profile_isolated.store(true, std::memory_order_release); }

bool Enabled() { return Requested() && g_profile_isolated.load(std::memory_order_acquire); }

double TimeScale() {
  if (!Enabled()) return 1.0;
  const double scale = REXCVAR_GET(cheat_time_scale);
  return std::isfinite(scale) ? std::clamp(scale, 0.25, 2.0) : 1.0;
}

double TimeOfDaySeconds() {
  if (!Enabled()) return -1.0;
  const double hours = REXCVAR_GET(cheat_time_of_day);
  return std::isfinite(hours) && hours >= 0.0 ? std::min(hours, 24.0) * 3600.0 : -1.0;
}

double DayLengthMinutes() {
  if (!Enabled()) return 0.0;
  const double minutes = REXCVAR_GET(cheat_day_length_minutes);
  if (!std::isfinite(minutes)) return 0.0;
  if (minutes < 0.0) return kLocalClock;
  return minutes >= 1.0 ? std::min(minutes, 1440.0) : 0.0;
}

bool FreeCamera() { return Enabled() && REXCVAR_GET(cheat_free_camera); }

bool AnyCarInEvents() { return Enabled() && REXCVAR_GET(cheat_any_car_events); }
bool FastTravelAnywhere() { return Enabled() && REXCVAR_GET(cheat_fast_travel_anywhere); }

void GpsDestinationApplied() { CallApplied("cheat_gps_destination"); }
void TeleportDestinationApplied() { CallApplied("cheat_teleport_destination"); }

std::string Active() {
  std::string active;
  if (TimeScale() != 1.0) {
    active += fmt::format("time_scale={:.2f}", TimeScale());
  }
  if (FreeCamera()) {
    active += fmt::format("{}free_camera", active.empty() ? "" : ",");
  }
  if (AnyCarInEvents()) {
    active += fmt::format("{}any_car_events", active.empty() ? "" : ",");
  }
  if (FastTravelAnywhere()) active += fmt::format("{}fast_travel_anywhere", active.empty() ? "" : ",");
  if (const double seconds = TimeOfDaySeconds(); seconds >= 0.0) {
    active += fmt::format("{}time_of_day={:.2f}", active.empty() ? "" : ",", seconds / 3600.0);
  } else if (const double minutes = DayLengthMinutes(); minutes != 0.0) {
    active += fmt::format("{}day_length={}", active.empty() ? "" : ",",
                          minutes < 0.0 ? std::string("local") : fmt::format("{:g}", minutes));
  }
  if (const int32_t credits = g_set_credits_value.load(std::memory_order_acquire);
      credits >= 0) {
    active += fmt::format("{}set_credits={}", active.empty() ? "" : ",", credits);
  }
  if (const int64_t added = g_credits_added.load(std::memory_order_acquire); added != 0) {
    active += fmt::format("{}add_credits={}", active.empty() ? "" : ",", added);
  }
  if (g_fields_applied.load(std::memory_order_acquire)) {
    std::lock_guard lock(g_fields_mutex);
    active += fmt::format("{}set_profile_fields={}", active.empty() ? "" : ",", g_fields_value);
  }
  return active;
}

namespace {
// Sets `path=value` on a scalar field of a decrypted profile body; false when
// the field is missing, not scalar or the value does not parse.
bool SetProfileField(uint8_t* body, size_t size, std::string_view path, std::string_view text,
                     std::string& previous) {
  const auto field = save::FindProfileField(body, size, path);
  if (!field) return false;
  uint8_t* value = body + field->offset;
  const std::string owned(text);
  char* end = nullptr;
  switch (field->type) {
    case save::FieldType::kBool:
    case save::FieldType::kUInt8: {
      const unsigned long parsed = std::strtoul(owned.c_str(), &end, 10);
      if (end == owned.c_str() || *end || parsed > 0xFF) return false;
      previous = fmt::format("{}", value[0]);
      value[0] = uint8_t(parsed);
      return true;
    }
    case save::FieldType::kUInt32:
    case save::FieldType::kInt32: {
      const long long parsed = std::strtoll(owned.c_str(), &end, 10);
      if (end == owned.c_str() || *end || parsed < INT32_MIN || parsed > UINT32_MAX) return false;
      previous = fmt::format("{}", (uint32_t(value[0]) << 24) | (uint32_t(value[1]) << 16) |
                                       (uint32_t(value[2]) << 8) | uint32_t(value[3]));
      StoreBe32(value, uint32_t(parsed));
      return true;
    }
    case save::FieldType::kFloat: {
      const float parsed = std::strtof(owned.c_str(), &end);
      if (end == owned.c_str() || *end || !std::isfinite(parsed)) return false;
      uint32_t bits = (uint32_t(value[0]) << 24) | (uint32_t(value[1]) << 16) |
                      (uint32_t(value[2]) << 8) | uint32_t(value[3]);
      float old;
      std::memcpy(&old, &bits, sizeof(old));
      previous = fmt::format("{}", old);
      std::memcpy(&bits, &parsed, sizeof(bits));
      StoreBe32(value, bits);
      return true;
    }
    default:
      return false;
  }
}
}  // namespace

// Sets cheat_set_profile_fields on a decrypted profile, once.
static void EditLoadedProfileFields(uint8_t* body, size_t size) {
  const std::string fields = REXCVAR_GET(cheat_set_profile_fields);
  const bool recovery = fields == kCarRecoveryFields &&
      g_profile_isolated.load(std::memory_order_acquire);
  if ((!Enabled() && !recovery) || fields.empty() ||
      g_fields_applied.load(std::memory_order_acquire)) {
    return;
  }
  // Other secure files pass through here too; only the profile has Main.
  if (!save::FindProfileField(body, size, "Main/Credits")) {
    return;
  }
  if (g_fields_applied.exchange(true, std::memory_order_acq_rel)) {
    return;
  }
  size_t start = 0;
  while (start < fields.size()) {
    const size_t end = std::min(fields.find(',', start), fields.size());
    const std::string_view pair = std::string_view(fields).substr(start, end - start);
    start = end + 1;
    const size_t equals = pair.find('=');
    if (equals == std::string_view::npos) continue;
    const std::string_view path = pair.substr(0, equals);
    const std::string_view value = pair.substr(equals + 1);
    std::string previous;
    const bool set = SetProfileField(body, size, path, value, previous);
    diagnostics::RecordEvent("cheat.applied", {{"name", "cheat_set_profile_fields"},
                                               {"field", std::string(path)},
                                               {"previous", previous},
                                               {"value", std::string(value)},
                                               {"result", set ? "set" : "rejected"}});
  }
  {
    std::lock_guard lock(g_fields_mutex);
    g_fields_value = fields;
  }
  CallApplied("cheat_set_profile_fields");
}

void EditLoadedProfile(uint8_t* body, size_t size) {
  EditLoadedProfileFields(body, size);
  const int32_t credits = REXCVAR_GET(cheat_set_credits);
  if (!Enabled() || credits < 0 || g_credits_applied.load(std::memory_order_acquire)) {
    return;
  }
  // Other secure files pass through here too; only the profile has the field.
  const auto field = save::FindProfileField(body, size, "Main/Credits");
  if (!field || field->type != save::FieldType::kUInt32) {
    return;
  }
  if (g_credits_applied.exchange(true, std::memory_order_acq_rel)) {
    return;
  }
  uint8_t* value = body + field->offset;
  const uint32_t previous = (uint32_t(value[0]) << 24) | (uint32_t(value[1]) << 16) |
                            (uint32_t(value[2]) << 8) | uint32_t(value[3]);
  StoreBe32(value, static_cast<uint32_t>(credits));
  g_set_credits_value.store(credits, std::memory_order_release);
  {
    // Chosen while the profile was not loaded: the body took it, so the live
    // path must not set it again over later changes.
    std::lock_guard lock(g_credits_mutex);
    if (g_credits_change.set == credits) {
      g_credits_change.set = -1;
      g_credits_pending.store(g_credits_change.add != 0, std::memory_order_release);
    }
  }
  diagnostics::RecordEvent("cheat.applied", {{"name", "cheat_set_credits"},
                                             {"previous", fmt::format("{}", previous)},
                                             {"value", fmt::format("{}", credits)},
                                             {"when", "load"}});
  CallApplied("cheat_set_credits");
}

void AddCredits(int32_t amount) {
  if (!Enabled() || amount == 0) {
    return;
  }
  {
    std::lock_guard lock(g_credits_mutex);
    g_credits_change.add += amount;
    g_credits_pending.store(true, std::memory_order_release);
  }
  diagnostics::RecordEvent("cheat.changed",
                           {{"name", "cheat_add_credits"}, {"value", fmt::format("{}", amount)}});
}

bool CreditsPending() {
  return g_credits_pending.load(std::memory_order_acquire) && Enabled();
}

CreditsChange TakeCredits() {
  std::lock_guard lock(g_credits_mutex);
  const CreditsChange change = g_credits_change;
  g_credits_change = CreditsChange{};
  g_credits_pending.store(false, std::memory_order_release);
  return change;
}

void ReturnCredits(const CreditsChange& change) {
  std::lock_guard lock(g_credits_mutex);
  // Changes made meanwhile come after it: a set replaces it, additions add.
  if (g_credits_change.set < 0) {
    g_credits_change.set = change.set;
    g_credits_change.add += change.add;
  }
  g_credits_pending.store(g_credits_change.set >= 0 || g_credits_change.add != 0,
                          std::memory_order_release);
}

void CreditsApplied(const CreditsChange& change, uint32_t previous, uint32_t value) {
  if (change.set >= 0) {
    g_set_credits_value.store(int32_t(change.set), std::memory_order_release);
  }
  g_credits_added.fetch_add(change.add, std::memory_order_acq_rel);
  diagnostics::RecordEvent("cheat.applied",
                           {{"name", change.set >= 0 ? "cheat_set_credits" : "cheat_add_credits"},
                            {"set", fmt::format("{}", change.set)},
                            {"add", fmt::format("{}", change.add)},
                            {"previous", fmt::format("{}", previous)},
                            {"value", fmt::format("{}", value)},
                            {"when", "live"}});
  if (change.set >= 0) {
    CallApplied("cheat_set_credits");
  }
}

void SetAppliedCallback(std::function<void(std::string_view setting)> callback) {
  std::lock_guard lock(g_applied_mutex);
  g_applied = std::move(callback);
}

void InstallChangeLog() {
  // Every setting the trainer changes, including the graphics and debug ones
  // it shares with SETTINGS.
  for (const char* name : {"cheat_time_scale", "cheat_time_of_day", "cheat_day_length_minutes",
                           "cheat_free_camera",
                           "cheat_any_car_events", "cheat_show_collectibles",
                           "cheat_fast_travel_anywhere", "cheat_saved_destination",
                           "disable_motion_blur", "disable_depth_of_field",
                           "force_trilinear_filtering", "fh1_render_test_log_file_opens"}) {
    rex::cvar::RegisterChangeCallback(name, [](std::string_view name, std::string_view value) {
      diagnostics::RecordEvent("cheat.changed", {{"name", name}, {"value", value}});
    });
  }
  // A credits value chosen while the game runs waits for the running
  // profile; clearing it to -1 after it applied is not a change.
  rex::cvar::RegisterChangeCallback(
      "cheat_set_credits", [](std::string_view name, std::string_view value) {
        const std::string owned(value);
        char* end = nullptr;
        const long credits = std::strtol(owned.c_str(), &end, 10);
        if (!Enabled() || end == owned.c_str() || *end || credits < 0) {
          return;
        }
        {
          std::lock_guard lock(g_credits_mutex);
          g_credits_change.set = credits;
          // A set replaces the additions made before it.
          g_credits_change.add = 0;
          g_credits_pending.store(true, std::memory_order_release);
        }
        diagnostics::RecordEvent("cheat.changed", {{"name", name}, {"value", value}});
      });
}

}  // namespace pinyon_shift::cheats
