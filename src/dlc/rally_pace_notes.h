#pragma once

#include <array>
#include <cstdint>
#include <deque>
#include <filesystem>
#include <functional>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace pinyon_shift::rally {

// Owned speech banks follow the console language/country. Unvoiced UI
// languages use English, as no corresponding co-driver bank is supplied.
std::string_view CoDriverLanguage(uint32_t language, uint32_t country);

struct PaceSample { std::string group, cue, icon; };
struct PaceCall {
  uint32_t route;
  std::string name;
  double width;
  std::array<double, 3> position, facing;
  std::vector<PaceSample> samples;
};
std::vector<PaceCall> ReadPaceNotes(const std::filesystem::path& path);

// A copied phrase for the UI thread; drawing never reads guest objects.
struct PaceHud {
  std::vector<std::string> icons;
  size_t active = size_t(-1);
  bool operator==(const PaceHud&) const = default;
};
PaceHud ReadPaceHud();
void PublishPaceHud(PaceHud hud);
void SetPaceHudChangedCallback(std::function<void()> callback);

// Geometry and phrase order are independent of the guest audio interfaces.
class PaceNotes {
 public:
  explicit PaceNotes(std::vector<PaceCall> calls);
  // True tells the caller to stop its current voice after a retry, rewind or exit.
  bool Observe(uint32_t route, uint32_t serial, double seconds,
               std::array<double, 3> position);
  // A missing pose suspends speech without forgetting already crossed gates.
  bool Suspend(uint32_t route, uint32_t serial, double seconds);
  PaceHud hud() const;
  const PaceSample* front() const;
  // Call only while front() is non-null; indices address the imported metadata.
  size_t call_index() const { return queue_.front().call; }
  size_t sample_index() const { return queue_.front().sample; }
  void Pop();
  size_t pending() const { return queue_.size(); }

 private:
  bool ObservePose(uint32_t route, uint32_t serial, double seconds,
                   std::optional<std::array<double, 3>> position);
  struct Queued { size_t call, sample; };
  std::vector<PaceCall> calls_;
  std::vector<std::optional<double>> fired_;
  std::deque<Queued> queue_;
  uint32_t route_ = 0, serial_ = 0;
  double seconds_ = 0;
  std::optional<std::array<double, 3>> position_;
};

}  // namespace pinyon_shift::rally
