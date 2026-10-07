#include "dlc/rally_progress.h"

#include <cmath>
#include <fstream>
#include <iomanip>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <utility>
#include <toml++/toml.hpp>

#include "platform/host_platform.h"

namespace pinyon_shift::rally {

uint32_t StageMapping::SeriesForRoute(uint32_t route) const {
  if (!has_series()) return 0;
  for (size_t i = 0; i < kSeriesRoutes.size(); ++i) {
    const auto& routes = kSeriesRoutes[i];
    if ((!series_id || series_id == i + 1) && std::find(routes.begin(), routes.end(), route) != routes.end())
      return static_cast<uint32_t>(i + 1);
  }
  return 0;
}

const SeriesEvent* StageMapping::EventForRoute(uint32_t route) const {
  if (const auto found = stages.find(route); found != stages.end()) return &found->second;
  const auto found = std::find_if(sequence.begin(), sequence.end(),
                                [route](const auto& stage) { return route && stage.route == route; });
  return found != sequence.end() ? &*found : nullptr;
}

StageMapping ReadStageMapping(const std::filesystem::path& path) {
  std::ifstream input(path, std::ios::binary);
  auto data = toml::parse(input);
  StageMapping mapping;
  auto& result = mapping.events;
  auto add = [&](toml::node_view<const toml::node> row) {
    const auto event = row["event_id"].value<int64_t>().value_or(0);
    const auto route = row["route"].value<int64_t>().value_or(0);
    if (event <= 0 || event > UINT32_MAX || route <= 0 || route > UINT32_MAX ||
        !StageIndex(static_cast<uint32_t>(route)) ||
        std::any_of(result.begin(), result.end(), [&](const auto& saved) { return saved.second == route; }) ||
        !result.emplace(static_cast<uint32_t>(event), static_cast<uint32_t>(route)).second)
      throw std::runtime_error("invalid or ambiguous Rally stage mapping");
  };
  const auto version = data["version"].value<int64_t>();
  if (version == 1) {
    add(toml::node_view<const toml::node>(data));
  } else if (version == 2 || version == 3 || version == 4) {
    const auto* stages = data["stages"].as_array();
    if (!stages || stages->empty() || stages->size() > kStageRoutes.size())
      throw std::runtime_error("invalid Rally stage mapping");
    for (const auto& row : *stages) add(toml::node_view<const toml::node>(row));
    if (version == 4) {
      if (stages->size() != kStageRoutes.size() || data.contains("series_id"))
        throw std::runtime_error("Rally selection requires all 28 stages");
      for (const auto& value : *stages) {
        const auto row = toml::node_view<const toml::node>(value);
        const auto name = row["event_name"].value<std::string>().value_or("");
        if (name.empty() || name.size() > 15 || name == "RALLY_PROBE" || name == "RALLY_NEXT" ||
            !std::all_of(name.begin(), name.end(), [](char c) {
              return (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_';
            }) || std::any_of(mapping.stages.begin(), mapping.stages.end(),
                            [&](const auto& stage) { return stage.second.name == name; }))
          throw std::runtime_error("invalid Rally stage event name");
        const auto route = static_cast<uint32_t>(*row["route"].value<int64_t>());
        mapping.stages.emplace(route, SeriesEvent{static_cast<uint32_t>(*row["event_id"].value<int64_t>()), route, name});
      }
    }
    if (version == 3) {
      const auto id = data["series_id"].value<int64_t>().value_or(0);
      if (id < 1 || id > kSeriesRoutes.size() || stages->size() != 4)
        throw std::runtime_error("invalid Rally series mapping");
      mapping.series_id = static_cast<uint32_t>(id);
      for (size_t i = 0; i < 4; ++i) {
        const auto row = toml::node_view<const toml::node>((*stages)[i]);
        const auto name = row["event_name"].value<std::string>().value_or("");
        if (row["route"].value<int64_t>() != kSeriesRoutes[id - 1][i] || name.empty() || name.size() > 15 ||
            (i == 0 && name != "RALLY_PROBE") ||
            !std::all_of(name.begin(), name.end(), [](char c) {
              return (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_';
            }) || std::any_of(mapping.sequence.begin(), mapping.sequence.begin() + i,
                             [&](const auto& stage) { return stage.name == name; }) || name == "RALLY_NEXT")
          throw std::runtime_error("invalid Rally series order or event name");
        mapping.sequence[i] = {static_cast<uint32_t>(*row["event_id"].value<int64_t>()),
                              kSeriesRoutes[id - 1][i], name};
      }
    }
  } else {
    throw std::runtime_error("unsupported Rally stage mapping version");
  }
  return mapping;
}

StageEvents ReadStageEvents(const std::filesystem::path& path) { return ReadStageMapping(path).events; }

double SeriesAttempt::total_seconds() const { return std::accumulate(seconds.begin(), seconds.end(), 0.0); }

uint32_t Progress::next_route() const {
  const auto& attempt = state_.attempt;
  return attempt.active ? kSeriesRoutes[attempt.series_id - 1][attempt.completed] : 0;
}

Progress::Progress(std::filesystem::path path, uint32_t series_id)
    : path_(std::move(path)), series_id_(series_id), extended_(series_id != 0) {
  try {
    if (series_id > kSeriesRoutes.size()) throw std::runtime_error("invalid Rally series ID");
    if (!std::filesystem::exists(path_)) return;
    std::ifstream input(path_, std::ios::binary);
    auto data = toml::parse(input);
    const auto version = data["version"].value<int64_t>();
    if (version != 1 && version != 2 && version != 3)
      throw std::runtime_error("unsupported Rally progress version");
    const auto* stages = data["stages"].as_array();
    const size_t expected = version == 1 ? 21 : kStageRoutes.size();
    if (!stages || stages->size() != expected)
      throw std::runtime_error("invalid Rally stage progress");
    ProgressState parsed;
    for (size_t i = 0; i < expected; ++i) {
      const auto stage = toml::node_view<const toml::node>((*stages)[i]);
      const auto count = stage["completions"].value<int64_t>();
      const auto seconds = stage["best_seconds"].value<double>();
      if (stage["route"].value<int64_t>() != kStageRoutes[i] || !count || *count < 0 ||
          *count > std::numeric_limits<uint32_t>::max() || !seconds ||
          !std::isfinite(*seconds) || *seconds < 0 || ((*count == 0) != (*seconds == 0)))
        throw std::runtime_error("invalid Rally stage result");
      parsed.stages[i] = {static_cast<uint32_t>(*count), *seconds};
    }
    if (version == 3) {
      extended_ = true;
      const auto* series = data["series"].as_array();
      if (!series || series->size() != kSeriesRoutes.size()) throw std::runtime_error("invalid Rally series progress");
      for (size_t i = 0; i < series->size(); ++i) {
        const auto row = toml::node_view<const toml::node>((*series)[i]);
        const auto count = row["completions"].value<int64_t>();
        const auto best = row["best_seconds"].value<double>();
        if (row["id"].value<int64_t>() != i + 1 || !count || *count < 0 || *count > UINT32_MAX ||
            !best || !std::isfinite(*best) || *best < 0 || ((*count == 0) != (*best == 0)))
          throw std::runtime_error("invalid Rally series result");
        parsed.series[i] = {static_cast<uint32_t>(*count), *best};
      }
      const auto attempt = data["attempt"];
      const auto id = attempt["series_id"].value<int64_t>();
      const auto completed = attempt["completed"].value<int64_t>();
      const auto active = attempt["active"].value<bool>();
      const auto* times = attempt["seconds"].as_array();
      const auto total = attempt["total_seconds"].value<double>();
      if (!id || *id < 0 || *id > kSeriesRoutes.size() || !completed || *completed < 0 || *completed > 4 ||
          !active || !times || times->size() != 4 || !total || !std::isfinite(*total) ||
          (*active ? (*id == 0 || *completed == 4) :
                     (*id == 0 ? *completed != 0 : *completed != 4)))
        throw std::runtime_error("invalid Rally series attempt");
      parsed.attempt.series_id = static_cast<uint32_t>(*id);
      parsed.attempt.completed = static_cast<uint32_t>(*completed);
      parsed.attempt.active = *active;
      for (size_t i = 0; i < 4; ++i) {
        const auto seconds = (*times)[i].value<double>();
        if (!seconds || !std::isfinite(*seconds) || (i < *completed ? *seconds <= 0 : *seconds != 0))
          throw std::runtime_error("invalid Rally attempt stage time");
        parsed.attempt.seconds[i] = *seconds;
      }
      if (std::abs(parsed.attempt.total_seconds() - *total) > 0.000001)
        throw std::runtime_error("invalid Rally attempt total");
      for (size_t i = 0; i < parsed.attempt.completed; ++i) {
        const auto route = kSeriesRoutes[parsed.attempt.series_id - 1][i];
        const auto& stage = parsed.stages[*StageIndex(route)];
        if (!stage.completions || stage.best_seconds > parsed.attempt.seconds[i])
          throw std::runtime_error("Rally attempt does not match saved stages");
      }
      if (parsed.attempt.completed == 4) {
        const auto& series = parsed.series[parsed.attempt.series_id - 1];
        if (!series.completions || series.best_seconds > *total)
          throw std::runtime_error("Rally attempt does not match saved series");
      }
    }
    state_ = parsed;
  } catch (const std::exception& error) {
    readable_ = false;
    error_ = error.what();  // Preserve an unreadable/newer save, never reset it.
  }
}

bool Progress::Write(const ProgressState& state) {
  const auto temporary = std::filesystem::path(path_.native() +
      std::filesystem::path(".tmp").native());
  try {
    std::ofstream output(temporary, std::ios::binary | std::ios::trunc);
    output << "version = " << (extended_ ? 3 : 2) << "\n" << std::setprecision(17) << std::showpoint;
    for (size_t i = 0; i < state.stages.size(); ++i)
      output << "\n[[stages]]\nroute = " << kStageRoutes[i] << "\ncompletions = " << state.stages[i].completions
             << "\nbest_seconds = " << state.stages[i].best_seconds << "\n";
    if (extended_) {
      for (size_t i = 0; i < state.series.size(); ++i)
        output << "\n[[series]]\nid = " << i + 1 << "\ncompletions = " << state.series[i].completions
               << "\nbest_seconds = " << state.series[i].best_seconds << "\n";
      const auto& attempt = state.attempt;
      output << "\n[attempt]\nseries_id = " << attempt.series_id << "\ncompleted = " << attempt.completed
             << "\nactive = " << (attempt.active ? "true" : "false") << "\nseconds = [";
      for (size_t i = 0; i < 4; ++i) output << (i ? ", " : "") << attempt.seconds[i];
      output << "]\ntotal_seconds = " << attempt.total_seconds() << "\n";
    }
    output.close();
    if (!output || !platform::ReplaceFileAtomically(temporary, path_))
      throw std::runtime_error("could not save Rally progress");
    error_.clear();
    return true;
  } catch (const std::exception& error) {
    error_ = error.what();
    std::error_code ignored;
    std::filesystem::remove(temporary, ignored);
    return false;
  }
}

bool Progress::CancelAttempt() {
  if (!readable_) return false;
  if (!state_.attempt.active) return true;
  auto updated = state_;
  updated.attempt = {};
  if (!Write(updated)) return false;
  state_ = updated;
  armed_ = prepared_ = false;
  return true;
}

bool Progress::SelectSeries(uint32_t series_id) {
  if (!readable_) return false;
  if (series_id > kSeriesRoutes.size()) {
    error_ = "invalid Rally series ID";
    return false;
  }
  if (state_.attempt.active && state_.attempt.series_id != series_id) {
    error_ = "retire the unfinished Rally series before selecting another";
    return false;
  }
  if (series_id_ != series_id) {
    Observe({});
    series_id_ = series_id;
  }
  if (series_id) extended_ = true;
  error_.clear();
  return true;
}

bool Progress::Observe(const StageSample& sample) {
  const auto index = StageIndex(sample.route);
  if (!index || sample.serial == 0) {
    route_ = serial_ = 0;
    armed_ = committed_ = false;
    prepared_ = false;
    final_seconds_.reset();
    return false;
  }
  if (sample.route != route_ || sample.serial != serial_) {
    route_ = sample.route;
    serial_ = sample.serial;
    armed_ = committed_ = false;
    prepared_ = false;
    final_seconds_.reset();
  }
  // Native restart retains the car serial. Returning to pre-race arms a new
  // attempt without changing any earned stage or championship records.
  if (!sample.started && !sample.ended && sample.seconds == 0) {
    armed_ = committed_ = prepared_ = false;
    final_seconds_.reset();
    return false;
  }
  if (sample.ended && sample.end_reason != 1) {
    if (armed_ && series_id_) CancelAttempt();
    armed_ = false;
    final_seconds_.reset();
    return false;
  }
  if (sample.started && !sample.ended && std::isfinite(sample.seconds) && sample.seconds >= 0) {
    if (!readable_) return false;
    if (series_id_ && !prepared_) {
      if (state_.attempt.active && state_.attempt.series_id != series_id_) {
        error_ = "retire the unfinished Rally series before selecting another";
        return false;
      }
      const auto& routes = kSeriesRoutes[series_id_ - 1];
      const auto found = std::find(routes.begin(), routes.end(), sample.route);
      const auto stage = static_cast<uint32_t>(found - routes.begin());
      if (found == routes.end() ||
          (stage != 0 && (!state_.attempt.active || state_.attempt.series_id != series_id_ ||
                          stage > state_.attempt.completed))) {
        error_ = "Rally series stage is out of order";
        return false;
      }
      auto updated = state_;
      if (stage == 0) updated.attempt = {series_id_, 0, true, {}};
      else {
        updated.attempt.completed = stage;
        std::fill(updated.attempt.seconds.begin() + stage, updated.attempt.seconds.end(), 0);
      }
      if (updated.attempt != state_.attempt) {
        if (!Write(updated)) return false;
        state_ = updated;
      }
      prepared_ = true;
      error_.clear();
    }
    armed_ = true;
    final_seconds_.reset();
    return false;
  }
  if (!readable_ || !armed_ || committed_ || !sample.started || !sample.ended ||
      sample.end_reason != 1 || !std::isfinite(sample.seconds) || sample.seconds <= 0) {
    final_seconds_.reset();
    return false;
  }
  if (!final_seconds_ || *final_seconds_ != sample.seconds) {
    final_seconds_ = sample.seconds;
    return false;
  }
  auto updated = state_;
  auto& stage = updated.stages[*index];
  if (!stage.completions || sample.seconds < stage.best_seconds) stage.best_seconds = sample.seconds;
  if (stage.completions < std::numeric_limits<uint32_t>::max()) ++stage.completions;
  if (series_id_) {
    auto& attempt = updated.attempt;
    if (!prepared_ || !attempt.active || attempt.series_id != series_id_ ||
        kSeriesRoutes[series_id_ - 1][attempt.completed] != sample.route) return false;
    attempt.seconds[attempt.completed++] = sample.seconds;
    const double total = attempt.total_seconds();
    if (!std::isfinite(total)) { error_ = "invalid Rally series total"; return false; }
    if (attempt.completed == 4) {
      attempt.active = false;
      auto& series = updated.series[series_id_ - 1];
      if (!series.completions || total < series.best_seconds) series.best_seconds = total;
      if (series.completions < UINT32_MAX) ++series.completions;
    }
  }
  if (!Write(updated)) return false;
  state_ = updated;
  committed_ = true;
  return true;
}

}  // namespace pinyon_shift::rally
