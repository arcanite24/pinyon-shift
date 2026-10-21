#include "telemetry/telemetry_probe.h"

#include <chrono>
#include <cmath>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <string>

#include <fmt/format.h>

#include <rex/cvar.h>
#include <rex/filesystem.h>
#include <rex/logging.h>
#include <rex/logging/api.h>

REXCVAR_DEFINE_BOOL(telemetry_probe, false, "Telemetry",
                    "Record candidate car fields (suspension, surface, collisions, rumble, body "
                    "motion) to telemetry-probe-<time>.csv beside the runtime log, to confirm "
                    "them against a drive")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

namespace pinyon_shift::telemetry {

namespace {

using Clock = std::chrono::steady_clock;

struct ProbeFile {
  ProbeFile(const char* file_suffix, std::chrono::milliseconds row_period)
      : suffix(file_suffix), period(row_period) {}
  const char* suffix;
  std::chrono::milliseconds period;
  std::ofstream out;
  bool header_written = false;
  bool failed = false;
  Clock::time_point next{};
};

std::mutex g_mutex;
ProbeFile g_fast{"", std::chrono::milliseconds(33)};
ProbeFile g_slow{"-block", std::chrono::milliseconds(500)};
Clock::time_point g_start = Clock::now();

std::string Stamp() {
  const std::time_t now = std::time(nullptr);
  std::tm local{};
#ifdef _WIN32
  localtime_s(&local, &now);
#else
  localtime_r(&now, &local);
#endif
  return fmt::format("{:04}{:02}{:02}-{:02}{:02}{:02}", local.tm_year + 1900, local.tm_mon + 1,
                     local.tm_mday, local.tm_hour, local.tm_min, local.tm_sec);
}

bool Due(ProbeFile& file) {
  if (!REXCVAR_GET(telemetry_probe) || file.failed) return false;
  std::lock_guard lock(g_mutex);
  const auto now = Clock::now();
  if (now < file.next) return false;
  file.next = now + file.period;
  return true;
}

void Write(ProbeFile& file, std::string_view header, const std::vector<float>& values) {
  std::lock_guard lock(g_mutex);
  if (file.failed) return;
  if (!file.out.is_open()) {
    static const std::string stamp = Stamp();
    const std::filesystem::path log = rex::to_path(REXCVAR_GET(log_file));
    const std::filesystem::path dir = log.has_parent_path() ? log.parent_path() : ".";
    const auto path = dir / fmt::format("telemetry-probe-{}{}.csv", stamp, file.suffix);
    file.out.open(path, std::ios::out | std::ios::trunc);
    if (!file.out) {
      file.failed = true;
      REXLOG_WARN("Telemetry probe: cannot write {}", rex::path_to_utf8(path));
      return;
    }
    REXLOG_INFO("Telemetry probe: recording to {}", rex::path_to_utf8(path));
  }
  if (!file.header_written) {
    file.out << "t_ms," << header << '\n';
    file.header_written = true;
  }
  const auto ms =
      std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now() - g_start).count();
  std::string row = std::to_string(ms);
  for (const float value : values) {
    row += ',';
    if (std::isfinite(value)) row += fmt::format("{:.6g}", value);
  }
  row += '\n';
  file.out << row;
}

}  // namespace

bool ProbeWanted() { return REXCVAR_GET(telemetry_probe); }
bool ProbeFastDue() { return Due(g_fast); }
bool ProbeSlowDue() { return Due(g_slow); }

void ProbeWriteFast(std::string_view header, const std::vector<float>& values) {
  Write(g_fast, header, values);
}

void ProbeWriteSlow(std::string_view header, const std::vector<float>& values) {
  Write(g_slow, header, values);
}

}  // namespace pinyon_shift::telemetry
