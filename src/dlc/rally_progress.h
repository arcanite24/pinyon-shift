#pragma once

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <map>
#include <optional>
#include <string>

namespace pinyon_shift::rally {

// The seven fourth stages use non-contiguous routes from the owned DLC.
inline constexpr std::array<uint32_t, 28> kStageRoutes = {
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21,
    41, 42, 43, 44, 45, 46, 47};
inline constexpr std::array<std::array<uint32_t, 4>, 7> kSeriesRoutes = {{
    {11, 10, 12, 44}, {13, 14, 15, 45}, {4, 5, 6, 42}, {19, 20, 21, 47},
    {7, 8, 9, 43}, {16, 17, 18, 46}, {1, 2, 3, 41}}};
inline std::optional<std::size_t> StageIndex(uint32_t route) {
  const auto found = std::find(kStageRoutes.begin(), kStageRoutes.end(), route);
  if (found == kStageRoutes.end()) return std::nullopt;
  return static_cast<std::size_t>(found - kStageRoutes.begin());
}

using StageEvents = std::map<uint32_t, uint32_t>;  // Native event ID -> route.
struct SeriesEvent {
  uint32_t event_id = 0, route = 0;
  std::string name;
};
struct StageMapping {
  StageEvents events;
  uint32_t series_id = 0;
  std::array<SeriesEvent, 4> sequence;
  std::map<uint32_t, SeriesEvent> stages;  // Route -> named native event (v4).
  bool has_series() const { return series_id || !stages.empty(); }
  uint32_t SeriesForRoute(uint32_t route) const;
  const SeriesEvent* EventForRoute(uint32_t route) const;
};
// Private adapter metadata. Version 1 maps one stage; version 2 maps several.
// Reject ambiguous IDs/routes and non-championship tracks before observing.
StageEvents ReadStageEvents(const std::filesystem::path& path);
// Version 3 adds one fixed series; version 4 names all 28 stages for selection.
StageMapping ReadStageMapping(const std::filesystem::path& path);

struct StageProgress {
  uint32_t completions = 0;
  double best_seconds = 0;
};
struct SeriesAttempt {
  uint32_t series_id = 0, completed = 0;
  bool active = false;
  std::array<double, 4> seconds{};
  double total_seconds() const;
  bool operator==(const SeriesAttempt&) const = default;
};
struct ProgressState {
  std::array<StageProgress, kStageRoutes.size()> stages{};
  std::array<StageProgress, kSeriesRoutes.size()> series{};
  SeriesAttempt attempt;
};

// Native observations of a mapped Rally event. Route 0 clears the current
// race observation; CancelAttempt explicitly retires the persisted series.
// A completed result cannot be awarded unless this process first
// observed that same race serial running, followed by a stable success time.
struct StageSample {
  uint32_t route = 0, serial = 0;
  bool started = false, ended = false;
  uint8_t end_reason = 0;
  double seconds = 0;
};

class Progress {
 public:
  explicit Progress(std::filesystem::path path, uint32_t series_id = 0);
  // True once per completed attempt, after its progress reaches disk.
  bool Observe(const StageSample& sample);
  // Retirement cancels the active attempt without changing completed results.
  bool CancelAttempt();
  // Select without discarding an unfinished championship. Retire it first
  // before selecting another. Selection alone never writes or awards progress.
  bool SelectSeries(uint32_t series_id);
  uint32_t selected_series() const { return series_id_; }
  const auto& stages() const { return state_.stages; }
  const auto& series() const { return state_.series; }
  const auto& attempt() const { return state_.attempt; }
  uint32_t next_route() const;
  const std::string& error() const { return error_; }

 private:
  bool Write(const ProgressState& state);
  std::filesystem::path path_;
  ProgressState state_;
  uint32_t series_id_ = 0;
  bool extended_ = false, prepared_ = false;
  uint32_t route_ = 0, serial_ = 0;
  bool armed_ = false, committed_ = false, readable_ = true;
  std::optional<double> final_seconds_;
  std::string error_;
};

}  // namespace pinyon_shift::rally
