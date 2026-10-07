#include <chrono>
#include <cstdio>
#include <fstream>
#include <limits>
#include "dlc/rally_pace_notes.h"

using namespace pinyon_shift::rally;
static int failures = 0;
#define CHECK(c) do { if (!(c)) { std::fprintf(stderr, "%d: %s\n", __LINE__, #c); ++failures; } } while (false)
static PaceCall Call(double x, const char* cue) {
  return {1, cue, 20, {x, 0, 0}, {1, 0, 0},
          {{"CoDriver/Distance", cue, "None"}, {"CoDriver/Turns/Right", "HardRight", "HardRight"}}};
}
int main(int argc, char** argv) {
  CHECK(CoDriverLanguage(1, 103) == "EN");
  CHECK(CoDriverLanguage(5, 71) == "MX");
  CHECK(CoDriverLanguage(5, 31) == "ES");
  CHECK(CoDriverLanguage(1, 23) == "EN"); // No Czech speech bank.
  CHECK(CoDriverLanguage(2, 53) == "JP");
  CHECK(CoDriverLanguage(8, 101) == "CHT");
  CHECK(CoDriverLanguage(15, 75) == "NB");
  CHECK(CoDriverLanguage(999, 0) == "EN");
  // An optional owned metadata path exercises every imported transform/reference.
  if (argc == 2) {
    try { std::printf("validated %zu owned calls\n", ReadPaceNotes(argv[1]).size()); }
    catch (const std::exception& e) { std::fprintf(stderr, "%s\n", e.what()); return 1; }
  }
  PaceNotes notes({Call(20, "Second"), Call(0, "First")});
  CHECK(notes.Observe(1, 7, 0, {-10, 0, 0}));
  CHECK(!notes.Observe(1, 7, 1, {30, 100, 0}));
  CHECK(notes.pending() == 4 && notes.front()->cue == "First");
  CHECK(notes.hud().icons == std::vector<std::string>{"HardRight"});
  CHECK(notes.hud().active == size_t(-1));
  notes.Pop(); CHECK(notes.front()->cue == "HardRight");
  CHECK(notes.hud().active == 0);
  notes.Pop(); CHECK(notes.front()->cue == "Second");
  notes.Pop(); notes.Pop(); CHECK(!notes.front());
  // Backtracking without rewind never repeats a call; a new race does.
  notes.Observe(1, 7, 2, {-10, 0, 0}); notes.Observe(1, 7, 3, {30, 0, 0});
  CHECK(!notes.front());
  CHECK(notes.Observe(1, 8, 0, {-10, 0, 0}));
  notes.Observe(1, 8, 1, {30, 0, 0}); CHECK(notes.pending() == 4);
  // Rewind drops stale speech and re-arms only gates after the restored time.
  CHECK(notes.Observe(1, 8, 0.5, {10, 0, 0})); CHECK(!notes.front());
  notes.Observe(1, 8, 1, {30, 0, 0});
  CHECK(notes.pending() == 2 && notes.front()->cue == "Second");
  CHECK(notes.Observe(0, 0, 0, {})); CHECK(!notes.front());
  // Missing presentation updates while paused cancel speech, but do not
  // turn a live race into an exit or repeat already crossed gates.
  notes.Observe(1, 9, 0, {-10, 0, 0});
  notes.Observe(1, 9, 1, {10, 0, 0}); CHECK(notes.pending() == 2);
  CHECK(notes.Suspend(1, 9, 1)); CHECK(!notes.front() && notes.hud().icons.empty());
  CHECK(!notes.Suspend(1, 9, 1));
  notes.Observe(1, 9, 1, {-10, 0, 0});
  notes.Observe(1, 9, 2, {30, 0, 0});
  CHECK(notes.pending() == 2 && notes.front()->cue == "Second");
  // Rewind can happen while presentation is suspended as well.
  CHECK(notes.Suspend(1, 9, 0));
  notes.Observe(1, 9, 0, {-10, 0, 0}); notes.Observe(1, 9, 1, {30, 0, 0});
  CHECK(notes.pending() == 4);
  CHECK(notes.Suspend(1, 10, 0));
  notes.Observe(1, 10, 0, {-10, 0, 0}); notes.Observe(1, 10, 1, {30, 0, 0});
  CHECK(notes.pending() == 4);
  // Notifications may read the copied UI state; they must run outside its lock.
  int hud_changes = 0;
  SetPaceHudChangedCallback([&] { ++hud_changes; CHECK(ReadPaceHud() == notes.hud()); });
  PublishPaceHud(notes.hud()); PublishPaceHud(notes.hud());
  CHECK(hud_changes == 1);
  auto copy = ReadPaceHud(); copy.icons.clear();
  CHECK(!ReadPaceHud().icons.empty());
  SetPaceHudChangedCallback(nullptr); PublishPaceHud({});
  // Width, direction, teleports, stationary samples and invalid coordinates.
  PaceNotes missed({Call(0, "Gate")});
  missed.Observe(1, 1, 0, {10, 0, 0}); missed.Observe(1, 1, 1, {-10, 0, 0});
  CHECK(!missed.front());
  missed.Observe(1, 4, 0, {-10, 0, 11});
  missed.Observe(1, 4, 1, {10, 0, 11}); CHECK(!missed.front());
  missed.Observe(1, 2, 0, {-101, 0, 0}); missed.Observe(1, 2, 1, {1, 0, 0});
  CHECK(!missed.front());
  missed.Observe(1, 3, 0, {0, 0, 0}); missed.Observe(1, 3, 1, {0, 0, 0});
  CHECK(!missed.front());
  CHECK(missed.Observe(1, 3, 2, {std::numeric_limits<double>::quiet_NaN(), 0, 0}));
  missed.Observe(1, 3, 3, {10, 0, 0}); CHECK(!missed.front());
  // Corrupt metadata must fail before any native audio call.
  const auto path = std::filesystem::temp_directory_path() /
      ("pinyon-pace-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()) + ".toml");
  const std::string valid = "version = 1\n[[calls]]\nroute = 1\nname = 'gate'\nwidth = 20.0\n"
      "position = [0.0, 0.0, 0.0]\nfacing = [1.0, 0.0, 0.0]\n"
      "[[calls.samples]]\ngroup = 'CoDriver/Distance'\ncue = '50Distance'\nicon = 'None'\n";
  std::ofstream(path) << valid;
  CHECK(ReadPaceNotes(path).size() == 1);
  for (const auto& [before, after] : std::vector<std::pair<std::string, std::string>>{
      {"version = 1", "version = 2"}, {"route = 1", "route = 24"},
      {"width = 20.0", "width = nan"}, {"width = 20.0", "width = -1.0"},
      {"[1.0, 0.0, 0.0]", "[0.0, 0.0, 0.0]"}, {"[0.0, 0.0, 0.0]", "[nan, 0.0, 0.0]"},
      {"CoDriver/Distance", "../Distance"}, {"50Distance", "bad\\path"}}) {
    auto text = valid; text.replace(text.find(before), before.size(), after);
    std::ofstream(path) << text;
    bool rejected = false;
    try { ReadPaceNotes(path); } catch (const std::exception&) { rejected = true; }
    CHECK(rejected);
  }
  std::filesystem::remove(path);
  return failures ? 1 : 0;
}
