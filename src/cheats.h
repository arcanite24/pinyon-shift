#pragma once

#include <cstddef>
#include <cstdint>
#include <functional>
#include <string>
#include <string_view>

namespace pinyon_shift::cheats {

// The trainer (NP-8). Cheats only apply with pinyon_shift_cheats on, which
// also switches the title to the separate modded profile, so a cheated save
// never replaces the player's own: they stay off until that profile is in use.
bool Enabled();

// Whether the player turned cheats on (config file or command line).
bool Requested();
// This exact one-shot recovery selects the isolated profile without enabling cheats.
inline constexpr std::string_view kCarRecoveryFields = "Main/CareerCar=0";
bool CarRecoveryRequested();
// Called once the title's profile is the separate modded one.
void SetProfileIsolated();

// The factor applied to the title's gameplay delta, 1 when cheats are off.
double TimeScale();

// The time of day the trainer holds, in seconds since midnight, or a negative
// value when it leaves the title's clock alone (cheat_time_of_day).
double TimeOfDaySeconds();

// How long a day lasts (cheat_day_length_minutes, #483): minutes per
// 24 game hours, kLocalClock to follow this PC's clock, or 0 to leave the
// title's own rate. A held time of day wins over it.
constexpr double kLocalClock = -1.0;
double DayLengthMinutes();

// Whether the cameras should be the title's free camera (cheat_free_camera).
bool FreeCamera();

// Whether events ignore their car restrictions (cheat_any_car_events): each
// event loads without its make, year and other EventRestrictions limits, and
// without the limit its class (Events.TargetClass) adds to them.
bool AnyCarInEvents();
bool FastTravelAnywhere();

// The cheats currently changing the game, as "name=value" pairs separated by
// commas ("" when none), for the modded profile's save tag.
std::string Active();

// The save editor (NP-8.3): when the title has just decrypted a profile,
// sets its credits to cheat_set_credits (once; -1 leaves them), for a value
// chosen before the profile loaded. The title's own saves then keep it.
// The exact car-recovery edit is also allowed with the trainer off, after isolation.
void EditLoadedProfile(uint8_t* body, size_t size);

// Live credits: cheat_set_credits changed while the game runs, and the
// trainer's additions, wait here until the running title's profile takes
// them through its own setter (the runtime hooks' frame task).
struct CreditsChange {
  int64_t set = -1;  // the balance to set first, or -1
  int64_t add = 0;   // then added to the balance
};
// Adds `amount` credits to the balance (with cheats on), at once when the
// profile is loaded, else as soon as it is.
void AddCredits(int32_t amount);
// Whether a change waits; cheap, for every frame.
bool CreditsPending();
// Takes the waiting change; ReturnCredits puts it back, ahead of any change
// made since, when the profile cannot take it yet.
CreditsChange TakeCredits();
void ReturnCredits(const CreditsChange& change);
// Called on the title's main thread once its setter took `change`, with the
// balance before and after: logs it and clears a live cheat_set_credits.
void CreditsApplied(const CreditsChange& change, uint32_t previous, uint32_t value);
// Called (on a guest thread) after a one-shot edit or a live credits set was
// applied, with the setting to clear so it does not apply again at the next
// start.
void SetAppliedCallback(std::function<void(std::string_view setting)> callback);

// Logs cheat.changed events for the settings the trainer changes; call once
// at startup.
void InstallChangeLog();

}  // namespace pinyon_shift::cheats
