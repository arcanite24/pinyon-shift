#pragma once

#include <cstdint>
#include <functional>
#include <filesystem>
#include <string_view>
namespace rex::runtime { class FunctionDispatcher; }

// Private base-disc Rally series adapter, installed before the guest starts.
void PinyonShiftInstallRallySeriesLoader(rex::runtime::FunctionDispatcher* dispatcher);
// v4 diagnostic (pinyon_shift_car_challenge_gate_probe): report the Forza
// server as available to trace what 1000 Club needs offline.
void PinyonShiftInstallCarChallengeProbe(rex::runtime::FunctionDispatcher* dispatcher);
// Verified normal-launch DLC overlay or private probe, independent of mods.
bool PinyonShiftUseBuiltinRallyAdapter();
bool PinyonShiftRallyPaceEnabled();
std::filesystem::path PinyonShiftRallyAdapterRoot();
// Select an owned championship through its native activity flow. The guest
// thread validates the live activity and free-roam state before entering it.
bool PinyonShiftStartRallySeries(uint32_t series_id);
bool PinyonShiftCanStartRallySeries(uint32_t series_id);
uint32_t PinyonShiftRallyResumeStage(uint32_t series_id);
bool PinyonShiftRetireRallySeries();

// Kernel file-open observer: tracks whether the movie being played is a boot
// splash intro, which the opt-in opening-movie skip may complete early.
void PinyonShiftObserveGuestFileOpen(std::string_view guest_path);

// Called on the guest thread when the player picks SETTINGS in the pause menu;
// the handler must hand the work to the UI thread and return at once.
// NP-4.4 Hor+: the factor the title's 16:9 main-view aspect is multiplied by
// (1 keeps it), so a wider window shows more of the world horizontally.
void PinyonShiftSetViewportAspectScale(float scale);
// Called (on the title's thread) when the pause map opens or closes, so the
// presentation can show it as 16:9 instead of widened.
void PinyonShiftSetMapViewCallback(std::function<void(bool open)> callback);

void PinyonShiftSetPauseSettingsHandler(std::function<void()> handler);
