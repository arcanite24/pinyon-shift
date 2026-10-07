#include <chrono>
#include <cmath>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <limits>

#include "dlc/rally_progress.h"

using pinyon_shift::rally::Progress;
using pinyon_shift::rally::StageSample;
namespace fs = std::filesystem;
static int failures = 0;
#define CHECK(c) do { if (!(c)) { std::fprintf(stderr, "%d: %s\n", __LINE__, #c); ++failures; } } while (false)

static std::string Read(const fs::path& path) {
  std::ifstream input(path, std::ios::binary);
  return {std::istreambuf_iterator<char>(input), {}};
}

int main(int argc, char** argv) {
  const auto directory = fs::temp_directory_path() /
      ("pinyon-rally-test-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
  fs::create_directories(directory);
  const auto mapping = directory / "rally-stage.toml";
  std::ofstream(mapping, std::ios::binary) << "version = 1\nevent_id = 247\nroute = 1\n";
  CHECK(pinyon_shift::rally::ReadStageEvents(mapping).at(247) == 1);
  const std::string two_stages = "version = 2\n[[stages]]\nevent_id = 247\nroute = 1\n"
      "[[stages]]\nevent_id = 248\nroute = 2\n";
  std::ofstream(mapping, std::ios::binary) << two_stages;
  const auto mapped = pinyon_shift::rally::ReadStageEvents(mapping);
  CHECK(mapped.size() == 2 && mapped.at(247) == 1 && mapped.at(248) == 2);
  for (const auto* invalid : {"version = 3\n", "version = 2\nstages = []\n",
      "version = 1\nevent_id = 0\nroute = 1\n",
      "version = 1\nevent_id = 247\nroute = 24\n",
      "version = 2\n[[stages]]\nevent_id = 247\nroute = 1\n[[stages]]\nevent_id = 247\nroute = 2\n",
      "version = 2\n[[stages]]\nevent_id = 247\nroute = 1\n[[stages]]\nevent_id = 248\nroute = 1\n"}) {
    std::ofstream(mapping, std::ios::binary) << invalid;
    bool rejected = false;
    try { pinyon_shift::rally::ReadStageEvents(mapping); } catch (const std::exception&) { rejected = true; }
    CHECK(rejected); CHECK(Read(mapping) == invalid);
  }
  const auto path = directory / "rally-progress.toml";
  // Series order is authored, including the reversed 10/11 pair and fourth stages.
  const auto series_mapping = directory / "series-mapping.toml";
  auto mapping_text = [](uint32_t id) {
    std::string text = "version = 3\nseries_id = " + std::to_string(id) + "\n";
    for (size_t i = 0; i < 4; ++i) text += "[[stages]]\nevent_id = " + std::to_string(247 + i) +
        "\nroute = " + std::to_string(pinyon_shift::rally::kSeriesRoutes[id - 1][i]) +
        "\nevent_name = \"" + (i == 0 ? std::string("RALLY_PROBE") : "RALLY_" + std::to_string(i + 1)) + "\"\n";
    return text;
  };
  for (uint32_t id = 1; id <= 7; ++id) {
    std::ofstream(series_mapping, std::ios::binary) << mapping_text(id);
    const auto value = pinyon_shift::rally::ReadStageMapping(series_mapping);
    CHECK(value.series_id == id && value.events.size() == 4);
    CHECK(value.sequence[3].route == pinyon_shift::rally::kSeriesRoutes[id - 1][3]);
  }
  const auto series_text = mapping_text(7);
  for (const auto& replacement : {std::pair{"route = 2", "route = 10"},
       std::pair{"series_id = 7", "series_id = 8"}, std::pair{"RALLY_2", "RALLY_PROBE"},
       std::pair{"RALLY_PROBE", "RALLY_NEXT"}, std::pair{"RALLY_PROBE", "abcdefghijklmnop"}}) {
    auto bad = series_text;
    bad.replace(bad.find(replacement.first), std::string(replacement.first).size(), replacement.second);
    std::ofstream(series_mapping, std::ios::binary) << bad;
    bool rejected = false;
    try { pinyon_shift::rally::ReadStageMapping(series_mapping); } catch (const std::exception&) { rejected = true; }
    CHECK(rejected); CHECK(Read(series_mapping) == bad);
  }
  std::string all_stages = "version = 4\n";
  uint32_t event_id = 247;
  for (const auto route : pinyon_shift::rally::kStageRoutes)
    all_stages += "[[stages]]\nevent_id = " + std::to_string(event_id++) + "\nroute = " +
        std::to_string(route) + "\nevent_name = \"RALLY_STAGE_" + std::to_string(route) + "\"\n";
  std::ofstream(mapping, std::ios::binary) << all_stages;
  const auto all = pinyon_shift::rally::ReadStageMapping(mapping);
  CHECK(all.has_series() && !all.series_id && all.events.size() == 28);
  CHECK(!all.SeriesForRoute(0) && !all.EventForRoute(0) && !all.EventForRoute(24));
  for (uint32_t id = 1; id <= 7; ++id)
    for (const auto route : pinyon_shift::rally::kSeriesRoutes[id - 1]) {
      CHECK(all.SeriesForRoute(route) == id);
      CHECK(all.EventForRoute(route)->route == route);
      CHECK(all.events.at(all.EventForRoute(route)->event_id) == route);
    }
  for (const auto& replacement : {std::pair{"RALLY_STAGE_2\"", "RALLY_STAGE_1\""},
      std::pair{"RALLY_STAGE_2\"", "RALLY_NEXT\""}, std::pair{"RALLY_STAGE_2\"", "RALLY_PROBE\""},
      std::pair{"RALLY_STAGE_2\"", "rally_bad\""}, std::pair{"RALLY_STAGE_2\"", "1234567890123456\""},
      std::pair{"version = 4", "version = 4\nseries_id = 7"}}) {
    auto invalid = all_stages;
    invalid.replace(invalid.find(replacement.first), std::string(replacement.first).size(), replacement.second);
    std::ofstream(mapping, std::ios::binary) << invalid;
    bool rejected = false;
    try { pinyon_shift::rally::ReadStageMapping(mapping); } catch (const std::exception&) { rejected = true; }
    CHECK(rejected && Read(mapping) == invalid);
  }
  std::ofstream(mapping, std::ios::binary) << all_stages.substr(0, all_stages.rfind("[[stages]]"));
  bool incomplete_rejected = false;
  try { pinyon_shift::rally::ReadStageMapping(mapping); } catch (const std::exception&) { incomplete_rejected = true; }
  CHECK(incomplete_rejected);
  const auto series_path = directory / "series-progress.toml";
  auto complete = [](Progress& ledger, uint32_t route, uint32_t serial, double seconds) {
    CHECK(!ledger.Observe({route, serial, true, false, 0, 1}));
    CHECK(!ledger.Observe({route, serial, true, true, 1, seconds}));
    CHECK(ledger.Observe({route, serial, true, true, 1, seconds}));
    CHECK(!ledger.Observe({route, serial, true, true, 1, seconds}));
  };
  // One profile selects all seven championships and resumes after each stage.
  // Switching cannot discard an earned checkpoint; selection alone is read-only.
  const auto selected_path = directory / "all-series.toml";
  for (uint32_t id = 1; id <= 7; ++id) {
    Progress selected(selected_path);
    const auto before_selection = Read(selected_path);
    CHECK(!selected.SelectSeries(8) && !selected.error().empty());
    CHECK(selected.SelectSeries(id) && selected.selected_series() == id);
    CHECK(Read(selected_path) == before_selection);
    const auto& routes = pinyon_shift::rally::kSeriesRoutes[id - 1];
    CHECK(!selected.Observe({routes[1], 100 + id, true, false, 0, 1}));
    CHECK(Read(selected_path) == before_selection && !selected.attempt().active);
    for (uint32_t i = 0; i < 4; ++i) {
      Progress resumed(selected_path);
      CHECK(resumed.SelectSeries(id));
      complete(resumed, routes[i], 100 + i, 100 + i);
      if (i < 3) {
        const auto checkpoint = Read(selected_path);
        CHECK(resumed.next_route() == routes[i + 1]);
        CHECK(!resumed.SelectSeries(id == 7 ? 1 : id + 1));
        CHECK(!resumed.SelectSeries(0));
        CHECK(Read(selected_path) == checkpoint && resumed.selected_series() == id);
        Progress wrong_series(selected_path, id == 7 ? 1 : id + 1);
        const auto other_first = pinyon_shift::rally::kSeriesRoutes[(id == 7 ? 1 : id + 1) - 1][0];
        CHECK(!wrong_series.Observe({other_first, 200, true, false, 0, 1}));
        CHECK(Read(selected_path) == checkpoint);
      } else {
        CHECK(!resumed.attempt().active && !resumed.next_route());
        CHECK(resumed.series()[id - 1].completions == 1 && resumed.series()[id - 1].best_seconds == 406);
      }
    }
  }
  {
    Progress selected(selected_path);
    for (const auto& series : selected.series()) CHECK(series.completions == 1 && series.best_seconds == 406);
    for (const auto& stage : selected.stages()) CHECK(stage.completions == 1);
    CHECK(selected.SelectSeries(7));
    complete(selected, 1, 300, 90);
    CHECK(!selected.SelectSeries(1));
    const auto unfinished = Read(selected_path);
    const auto blocked = fs::path(selected_path.native() + fs::path(".tmp").native());
    fs::create_directory(blocked);
    std::ofstream(blocked / "keep") << "block retirement";
    CHECK(!selected.CancelAttempt() && !selected.SelectSeries(1));
    CHECK(Read(selected_path) == unfinished && selected.attempt().active);
    fs::remove(blocked / "keep"); fs::remove(blocked);
    CHECK(selected.CancelAttempt() && selected.SelectSeries(1));
    const auto retired = Read(selected_path);
    CHECK(!selected.Observe({11, 301, true, true, 1, 90}));
    CHECK(Read(selected_path) == retired && selected.stages()[0].completions == 2);
  }
  // A native restart keeps the car serial and returns to a zero-clock
  // pre-race phase. A previous finish must not latch the next attempt shut.
  {
    const auto retry_path = directory / "same-serial-retry.toml";
    Progress retry(retry_path);
    complete(retry, 1, 77, 140);
    const auto earned = Read(retry_path);
    CHECK(!retry.Observe({1, 77, false, false, 0, 0}));
    CHECK(Read(retry_path) == earned && retry.stages()[0].completions == 1);
    CHECK(!retry.Observe({1, 77, true, true, 1, 140}));
    complete(retry, 1, 77, 130);
    CHECK(retry.stages()[0].completions == 2 && retry.stages()[0].best_seconds == 130);
    Progress reload_retry(retry_path);
    CHECK(reload_retry.stages()[0].completions == 2 && reload_retry.stages()[0].best_seconds == 130);
  }
  {
    Progress ledger(series_path, 7);
    CHECK(!ledger.Observe({2, 10, true, false, 0, 1}));
    CHECK(!fs::exists(series_path));  // Cannot start at stage two.
    complete(ledger, 1, 11, 100);
    CHECK(ledger.attempt().active && ledger.attempt().completed == 1 && ledger.next_route() == 2);
    CHECK(ledger.attempt().total_seconds() == 100);
  }
  const auto first_saved = Read(series_path);
  {
    const auto retry_series_path = directory / "same-serial-series-retry.toml";
    Progress retry_series(retry_series_path, 7);
    complete(retry_series, 1, 31, 100);
    complete(retry_series, 2, 32, 110);
    const auto earned = Read(retry_series_path);
    CHECK(!retry_series.Observe({2, 32, false, false, 0, 0}));
    CHECK(Read(retry_series_path) == earned);
    complete(retry_series, 2, 32, 105);
    CHECK(retry_series.attempt().completed == 2 && retry_series.attempt().total_seconds() == 205);
    CHECK(retry_series.stages()[0].completions == 1 && retry_series.stages()[1].completions == 2);
    Progress reloaded(retry_series_path, 7);
    CHECK(reloaded.attempt().total_seconds() == 205 && reloaded.stages()[1].best_seconds == 105);
  }
  {
    Progress resumed(series_path, 7);
    CHECK(resumed.error().empty() && resumed.next_route() == 2);
    CHECK(!resumed.Observe({1, 11, true, true, 1, 100}));
    CHECK(Read(series_path) == first_saved);  // Reloaded finish cannot advance twice.
    complete(resumed, 2, 12, 110);
    // Retry stage two truncates only its time, retaining stage one.
    CHECK(!resumed.Observe({2, 13, true, false, 0, 1}));
    CHECK(resumed.attempt().completed == 1 && resumed.attempt().total_seconds() == 100);
    CHECK(!resumed.Observe({2, 13, true, true, 1, 105}));
    CHECK(resumed.Observe({2, 13, true, true, 1, 105}));
    complete(resumed, 3, 14, 120);
    CHECK(!resumed.Observe({41, 15, true, false, 0, 1}));
    CHECK(!resumed.Observe({41, 15, true, true, 1, 130}));
    const auto before_final = Read(series_path);
    const auto blocked = fs::path(series_path.native() + fs::path(".tmp").native());
    fs::create_directory(blocked);
    std::ofstream(blocked / "keep") << "block write";
    CHECK(!resumed.Observe({41, 15, true, true, 1, 130}));
    CHECK(Read(series_path) == before_final && resumed.attempt().completed == 3);
    CHECK(resumed.series()[6].completions == 0);
    fs::remove(blocked / "keep"); fs::remove(blocked);
    CHECK(resumed.Observe({41, 15, true, true, 1, 130}));
    CHECK(!resumed.Observe({41, 15, true, true, 1, 130}));
    CHECK(!resumed.attempt().active && resumed.attempt().completed == 4 && resumed.next_route() == 0);
    CHECK(resumed.series()[6].completions == 1 && resumed.series()[6].best_seconds == 455);
  }
  const auto series_saved = Read(series_path);
  {
    // Normal owned-content startup has no selected series after completion.
    Progress completed_reload(series_path);
    CHECK(completed_reload.error().empty() && completed_reload.selected_series() == 0);
    CHECK(completed_reload.attempt().series_id == 7 && completed_reload.attempt().completed == 4);
    CHECK(!completed_reload.attempt().active && completed_reload.next_route() == 0);
    CHECK(completed_reload.attempt().total_seconds() == 455);
    CHECK(completed_reload.series()[6].completions == 1 && completed_reload.series()[6].best_seconds == 455);
    CHECK(!completed_reload.Observe({}));
    CHECK(!completed_reload.Observe({41, 15, true, true, 1, 130}));
    CHECK(Read(series_path) == series_saved);
  }
  // Even finite native stage samples must not produce an unreadable partial total.
  {
    const auto overflow_path = directory / "overflow-series.toml";
    Progress overflow(overflow_path, 7);
    complete(overflow, 1, 25, std::numeric_limits<double>::max() / 2);
    const auto before_overflow = Read(overflow_path);
    CHECK(!overflow.Observe({2, 26, true, false, 0, 1}));
    CHECK(!overflow.Observe({2, 26, true, true, 1, std::numeric_limits<double>::max()}));
    CHECK(!overflow.Observe({2, 26, true, true, 1, std::numeric_limits<double>::max()}));
    CHECK(!overflow.error().empty() && overflow.attempt().completed == 1);
    CHECK(overflow.stages()[1].completions == 0 && Read(overflow_path) == before_overflow);
    Progress reopened(overflow_path, 7);
    if (!reopened.error().empty()) std::fprintf(stderr, "overflow checkpoint: %s\n", reopened.error().c_str());
    CHECK(reopened.error().empty() && reopened.next_route() == 2);
  }
  {
    Progress reload_series(series_path, 7);
    CHECK(reload_series.error().empty() && reload_series.attempt().total_seconds() == 455);
    CHECK(reload_series.series()[6].completions == 1);
    // Beginning another series does not erase its previous result; retirement adds no series award.
    CHECK(!reload_series.Observe({1, 16, true, false, 0, 1}));
    CHECK(reload_series.attempt().active && reload_series.attempt().completed == 0);
    const auto beginning = Read(series_path);
    fs::create_directory(fs::path(series_path.native() + fs::path(".tmp").native()));
    CHECK(!reload_series.CancelAttempt());
    CHECK(Read(series_path) == beginning && reload_series.attempt().active);
    fs::remove(fs::path(series_path.native() + fs::path(".tmp").native()));
    CHECK(reload_series.CancelAttempt());
    CHECK(!reload_series.attempt().active && reload_series.attempt().series_id == 0);
    CHECK(reload_series.series()[6].completions == 1);
    CHECK(!reload_series.Observe({1, 16, true, true, 1, 90}));
  }
  // Malformed total and future formats remain untouched.
  for (const auto& replacement : {std::pair{"total_seconds = 455", "total_seconds = 999"},
                                  std::pair{"version = 3", "version = 4"}}) {
    auto bad = series_saved;
    bad.replace(bad.find(replacement.first), std::string(replacement.first).size(), replacement.second);
    std::ofstream(series_path, std::ios::binary) << bad;
    Progress corrupt(series_path, 7);
    CHECK(!corrupt.error().empty());
    CHECK(!corrupt.SelectSeries(1));
    CHECK(!corrupt.Observe({1, 17, true, false, 0, 1}));
    CHECK(!corrupt.CancelAttempt()); CHECK(Read(series_path) == bad);
  }
  StageSample running{1, 14, true, false, 0, 12.5};
  StageSample finish{1, 14, true, true, 1, 171.188133};
  Progress progress(path);
  // A loaded finish alone is not a new completion.
  CHECK(!progress.Observe(finish)); CHECK(!progress.Observe(finish));
  CHECK(!fs::exists(path));
  CHECK(!progress.Observe(running));
  auto retired = finish; retired.end_reason = 2;
  CHECK(!progress.Observe(retired)); CHECK(!progress.Observe(retired));
  CHECK(!progress.Observe(finish)); CHECK(!progress.Observe(finish));
  CHECK(!fs::exists(path));
  running.serial = finish.serial = 15;
  CHECK(!progress.Observe(running));
  auto invalid = finish; invalid.seconds = std::numeric_limits<double>::quiet_NaN();
  CHECK(!progress.Observe(invalid)); CHECK(!progress.Observe(invalid));
  CHECK(!progress.Observe(finish));
  auto changing = finish; changing.seconds += 1;
  CHECK(!progress.Observe(changing));
  CHECK(!progress.Observe(finish)); CHECK(progress.Observe(finish));
  CHECK(!progress.Observe(finish));
  CHECK(progress.stages()[0].completions == 1);
  CHECK(progress.stages()[0].best_seconds == finish.seconds);
  const auto saved = Read(path);
  Progress reload(path);
  CHECK(reload.error().empty());
  CHECK(reload.stages()[0].completions == 1);
  CHECK(reload.stages()[0].best_seconds == finish.seconds);
  CHECK(reload.stages()[20].completions == 0);
  CHECK(!reload.Observe(finish)); CHECK(!reload.Observe(finish));
  CHECK(Read(path) == saved);
  // Leaving the event cancels an armed attempt; another event cannot finish it.
  CHECK(!reload.Observe(running)); CHECK(!reload.Observe({}));
  CHECK(!reload.Observe(finish)); CHECK(!reload.Observe(finish));
  CHECK(!reload.Observe(running));
  auto other = finish; other.route = 2;
  CHECK(!reload.Observe(other)); CHECK(!reload.Observe(other));
  CHECK(Read(path) == saved);
  // Retry gets a new serial. Slower times count without replacing the best.
  running.serial = finish.serial = 16; finish.seconds = 180;
  CHECK(!reload.Observe(running)); CHECK(!reload.Observe(finish));
  CHECK(reload.Observe(finish)); CHECK(reload.stages()[0].completions == 2);
  CHECK(reload.stages()[0].best_seconds == 171.188133);
  running.serial = finish.serial = 18; finish.seconds = 160;
  CHECK(!reload.Observe(running)); CHECK(!reload.Observe(finish));
  CHECK(reload.Observe(finish)); CHECK(reload.stages()[0].best_seconds == 160);
  // A failed temporary-file write preserves disk and memory; retry can commit.
  const auto before_failure = Read(path);
  fs::create_directory(directory / "rally-progress.toml.tmp");
  running.serial = finish.serial = 20; finish.seconds = 150;
  CHECK(!reload.Observe(running)); CHECK(!reload.Observe(finish));
  CHECK(!reload.Observe(finish)); CHECK(!reload.error().empty());
  CHECK(reload.stages()[0].completions == 3); CHECK(Read(path) == before_failure);
  fs::remove(directory / "rally-progress.toml.tmp");
  CHECK(reload.Observe(finish)); CHECK(reload.error().empty());
  CHECK(reload.stages()[0].completions == 4);
  // Malformed and future versions must never silently reset existing progress.
  for (const auto* data : {"broken = [", "version = 3\n", "version = 1\nstages = []\n"}) {
    const auto bad_path = directory / "invalid.toml";
    std::ofstream(bad_path, std::ios::binary) << data;
    Progress bad(bad_path);
    CHECK(!bad.error().empty()); CHECK(!bad.Observe(running));
    CHECK(!bad.Observe(finish)); CHECK(!bad.Observe(finish));
    CHECK(Read(bad_path) == data);
  }
  auto malformed_row = saved;
  const auto last_route = malformed_row.find("route = 21");
  malformed_row.replace(last_route, 10, "route = 22");
  const auto bad_path = directory / "invalid-row.toml";
  std::ofstream(bad_path, std::ios::binary) << malformed_row;
  Progress bad_row(bad_path);
  CHECK(!bad_row.error().empty()); CHECK(bad_row.stages()[0].completions == 0);
  CHECK(!bad_row.Observe(running)); CHECK(!bad_row.Observe(finish));
  CHECK(!bad_row.Observe(finish)); CHECK(Read(bad_path) == malformed_row);
  // Version 1's 21 routes remain readable and migrate only on a new finish.
  auto legacy = saved.substr(0, saved.find("\n[[stages]]\nroute = 41"));
  legacy.replace(legacy.find("version = 2"), 11, "version = 1");
  const auto legacy_path = directory / "legacy.toml";
  std::ofstream(legacy_path, std::ios::binary) << legacy;
  Progress migrated(legacy_path);
  CHECK(migrated.error().empty()); CHECK(migrated.stages()[0].completions == 1);
  CHECK(migrated.stages()[21].completions == 0); CHECK(Read(legacy_path) == legacy);
  running.route = finish.route = 41;
  CHECK(!migrated.Observe(running)); CHECK(!migrated.Observe(finish));
  CHECK(migrated.Observe(finish));
  Progress fourth_stage(legacy_path);
  CHECK(fourth_stage.error().empty()); CHECK(fourth_stage.stages().size() == 28);
  CHECK(fourth_stage.stages()[0].completions == 1);
  CHECK(fourth_stage.stages()[0].best_seconds == 171.188133);
  CHECK(fourth_stage.stages()[21].completions == 1);
  CHECK(fourth_stage.stages()[21].best_seconds == 150);
  CHECK(Read(legacy_path).starts_with("version = 2\n"));
  // Starting a series upgrades an older stage ledger without losing any bests.
  const auto before_series_upgrade = Read(legacy_path);
  Progress upgraded(legacy_path);
  CHECK(upgraded.SelectSeries(7));
  CHECK(upgraded.error().empty() && Read(legacy_path) == before_series_upgrade);
  complete(upgraded, 1, 24, 200);
  CHECK(Read(legacy_path).starts_with("version = 3\n"));
  CHECK(upgraded.stages()[0].completions == 2 && upgraded.stages()[0].best_seconds == 171.188133);
  CHECK(upgraded.stages()[21].completions == 1 && upgraded.stages()[21].best_seconds == 150);
  Progress reopened_series(legacy_path, 7);
  CHECK(reopened_series.error().empty() && reopened_series.next_route() == 2);
  CHECK(reopened_series.attempt().total_seconds() == 200);
  // Gaps, free roam and developer/test routes are not championship stages.
  for (uint32_t route : {0u, 22u, 24u, 40u, 48u, 100u, 211u}) {
    CHECK(!pinyon_shift::rally::StageIndex(route));
    running.route = finish.route = route;
    CHECK(!fourth_stage.Observe(running)); CHECK(!fourth_stage.Observe(finish));
    CHECK(!fourth_stage.Observe(finish));
  }
  fs::remove_all(directory);  // Only this test's uniquely named temporary tree.
  // Optional read-only validation of a real prepared cache's metadata.
  if (argc == 2) {
    const auto owned = pinyon_shift::rally::ReadStageMapping(argv[1]);
    CHECK(owned.stages.size() == 28 && owned.has_series());
    for (uint32_t id = 1; id <= 7; ++id)
      for (const auto route : pinyon_shift::rally::kSeriesRoutes[id - 1])
        CHECK(owned.SeriesForRoute(route) == id && owned.EventForRoute(route));
  }
  std::printf("Rally progress: %d failures\n", failures);
  return failures ? 1 : 0;
}
