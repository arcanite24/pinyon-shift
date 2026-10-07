#include "dlc/rally_pace_notes.h"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <mutex>
#include <stdexcept>
#include <utility>
#include <toml++/toml.hpp>

#include "dlc/rally_progress.h"

namespace pinyon_shift::rally {
namespace {
std::mutex g_hud_mutex;
PaceHud g_hud;
std::function<void()> g_hud_changed;
bool Finite(const std::array<double, 3>& point) {
  return std::all_of(point.begin(), point.end(), [](double v) { return std::isfinite(v); });
}
bool AudioName(const std::string& value, bool path = false) {
  return !value.empty() && value.size() <= 96 &&
      std::all_of(value.begin(), value.end(), [=](unsigned char c) {
        return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
               (c >= '0' && c <= '9') || c == '_' || (path && c == '/');
      });
}
}  // namespace

std::string_view CoDriverLanguage(uint32_t language, uint32_t country) {
  switch (language) {
    case 2: return "JP";
    case 3: return "DE";
    case 4: return "FR";
    case 5: return country == 71 ? "MX" : "ES";
    case 6: return "IT";
    case 7: return "KO";
    case 8: return "CHT";
    case 9: return "BR";
    case 11: return "PL";
    case 12: return "RU";
    case 13: return "SV";
    case 15: return "NB";
    case 16: return "NL";
    default: return "EN";
  }
}

PaceHud ReadPaceHud() {
  std::lock_guard lock(g_hud_mutex);
  return g_hud;
}
void PublishPaceHud(PaceHud hud) {
  std::function<void()> changed;
  {
    std::lock_guard lock(g_hud_mutex);
    if (hud == g_hud) return;
    g_hud = std::move(hud);
    changed = g_hud_changed;
  }
  if (changed) changed();
}
void SetPaceHudChangedCallback(std::function<void()> callback) {
  std::lock_guard lock(g_hud_mutex);
  g_hud_changed = std::move(callback);
}

std::vector<PaceCall> ReadPaceNotes(const std::filesystem::path& path) {
  std::ifstream input(path, std::ios::binary);
  const auto data = toml::parse(input);
  const auto* rows = data["calls"].as_array();
  if (data["version"].value<int64_t>() != 1 || !rows || rows->empty() || rows->size() > 2048)
    throw std::runtime_error("invalid Rally pace-note metadata");
  std::vector<PaceCall> calls;
  for (const auto& node : *rows) {
    const auto row = toml::node_view<const toml::node>(node);
    const auto route = row["route"].value<int64_t>().value_or(0);
    PaceCall call{};
    call.route = static_cast<uint32_t>(route);
    call.name = row["name"].value<std::string>().value_or("");
    call.width = row["width"].value<double>().value_or(0);
    if (route <= 0 || route > UINT32_MAX || !StageIndex(call.route) ||
        call.name.empty() || call.name.size() > 128 || !std::isfinite(call.width) ||
        call.width <= 0 || call.width > 1000)
      throw std::runtime_error("invalid Rally pace-note trigger");
    auto vector = [&](const char* key, auto& result) {
      const auto* values = row[key].as_array();
      if (!values || values->size() != 3) throw std::runtime_error("invalid pace-note transform");
      for (size_t i = 0; i < 3; ++i)
        result[i] = (*values)[i].value<double>().value_or(NAN);
      if (!Finite(result)) throw std::runtime_error("invalid pace-note transform");
    };
    vector("position", call.position);
    vector("facing", call.facing);
    double norm = 0;
    for (auto value : call.facing) norm += value * value;
    // Authored trigger gates face along the road and extend vertically.
    if (std::abs(norm - 1) > 0.001 || std::hypot(call.facing[0], call.facing[2]) < 0.9)
      throw std::runtime_error("invalid pace-note facing");
    const auto* samples = row["samples"].as_array();
    if (!samples || samples->empty() || samples->size() > 32)
      throw std::runtime_error("invalid pace-note phrase");
    for (const auto& sample_node : *samples) {
      const auto sample = toml::node_view<const toml::node>(sample_node);
      PaceSample entry{sample["group"].value<std::string>().value_or(""),
                       sample["cue"].value<std::string>().value_or(""),
                       sample["icon"].value<std::string>().value_or("")};
      if (!entry.group.starts_with("CoDriver/") || !AudioName(entry.group, true) ||
          !AudioName(entry.cue) || !AudioName(entry.icon))
        throw std::runtime_error("invalid pace-note audio reference");
      call.samples.push_back(std::move(entry));
    }
    calls.push_back(std::move(call));
  }
  return calls;
}

PaceNotes::PaceNotes(std::vector<PaceCall> calls)
    : calls_(std::move(calls)), fired_(calls_.size()) {}

bool PaceNotes::Observe(uint32_t route, uint32_t serial, double seconds,
                        std::array<double, 3> position) {
  return ObservePose(route, serial, seconds, position);
}
bool PaceNotes::Suspend(uint32_t route, uint32_t serial, double seconds) {
  return ObservePose(route, serial, seconds, std::nullopt);
}
bool PaceNotes::ObservePose(uint32_t route, uint32_t serial, double seconds,
                        std::optional<std::array<double, 3>> position) {
  const bool invalid = !route || !serial || !std::isfinite(seconds) || seconds < 0 ||
                       (position && !Finite(*position));
  if (invalid) route = serial = 0;
  const bool changed = route != route_ || serial != serial_;
  const bool rewind = !changed && seconds < seconds_ - 0.001;
  const bool suspended = !position && position_.has_value();
  if (changed || rewind || invalid || !position) {
    queue_.clear();
    for (auto& time : fired_) if (changed || invalid || (time && *time > seconds)) time.reset();
    position_.reset();
  }
  route_ = route; serial_ = serial;
  if (invalid) return true;
  if (!position) {
    seconds_ = seconds;
    return changed || rewind || suspended;
  }
  std::vector<std::pair<double, size_t>> crossed;
  if (position_) {
    const auto& previous = *position_;
    const auto& current = *position;
    // Ignore teleports/loading discontinuities instead of announcing crossed scenery.
    if (std::hypot(current[0] - previous[0], current[2] - previous[2]) <= 100) {
      for (size_t i = 0; i < calls_.size(); ++i) {
        const auto& call = calls_[i];
        if (call.route != route || fired_[i]) continue;
        const double norm = std::hypot(call.facing[0], call.facing[2]);
        const double nx = call.facing[0] / norm, nz = call.facing[2] / norm;
        auto side = [&](const auto& point) {
          return (point[0] - call.position[0]) * nx + (point[2] - call.position[2]) * nz;
        };
        const double before = side(previous), after = side(current);
        if (before >= 0 || after < 0) continue;
        const double fraction = -before / (after - before);
        const double x = previous[0] + fraction * (current[0] - previous[0]) - call.position[0];
        const double z = previous[2] + fraction * (current[2] - previous[2]) - call.position[2];
        if (std::abs(-x * nz + z * nx) <= call.width / 2) crossed.emplace_back(fraction, i);
      }
    }
  }
  std::sort(crossed.begin(), crossed.end());
  for (auto [fraction, index] : crossed) {
    fired_[index] = seconds_ + fraction * (seconds - seconds_);
    for (size_t sample = 0; sample < calls_[index].samples.size(); ++sample)
      queue_.push_back({index, sample});
  }
  seconds_ = seconds; position_ = position;
  return changed || rewind;
}

PaceHud PaceNotes::hud() const {
  PaceHud result;
  if (queue_.empty()) return result;
  const auto current = queue_.front();
  const auto& samples = calls_[current.call].samples;
  for (size_t i = 0; i < samples.size(); ++i) {
    if (samples[i].icon == "None") continue;
    if (i == current.sample) result.active = result.icons.size();
    result.icons.push_back(samples[i].icon);
  }
  return result;
}

const PaceSample* PaceNotes::front() const {
  return queue_.empty() ? nullptr : &calls_[queue_.front().call].samples[queue_.front().sample];
}
void PaceNotes::Pop() { if (!queue_.empty()) queue_.pop_front(); }

}  // namespace pinyon_shift::rally
