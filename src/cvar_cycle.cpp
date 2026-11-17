// Diagnostic: flip settings live on a timer, to measure a live change the
// same way every time (for example the renderer rebuild of a resolution or
// MSAA change; ported from Lavender Shift). Route scripts toggle cvars
// too; this works without a route, in normal play. Off unless
// pinyon_shift_cvar_cycle is set at launch:
//
//   --pinyon_shift_cvar_cycle="draw_resolution_scale_x,draw_resolution_scale_y=2|1@20"
//
// sets the listed cvars to each value in turn, starting after the first
// period, and holds the last value when the list ends. Several cycles,
// separated by ';', run side by side ("a=1|2@30;b=x|y@45").

#include "cvar_cycle.h"

#include <chrono>
#include <condition_variable>
#include <mutex>
#include <string>
#include <string_view>
#include <thread>
#include <vector>

#include <rex/cvar.h>
#include <rex/logging.h>

REXCVAR_DEFINE_STRING(pinyon_shift_cvar_cycle, "", "Pinyon Shift",
                      "Diagnostic: names=value1|value2@seconds sets the cvars to each value "
                      "in turn, one period apart");

namespace {

std::vector<std::string> Split(std::string_view text, char separator) {
  std::vector<std::string> parts;
  while (true) {
    const size_t at = text.find(separator);
    parts.emplace_back(text.substr(0, at));
    if (at == std::string_view::npos) break;
    text.remove_prefix(at + 1);
  }
  return parts;
}

std::mutex g_mutex;
std::condition_variable g_wake;
bool g_stop = false;
std::vector<std::thread> g_threads;

}  // namespace

namespace pinyon_shift::cvar_cycle {

static void StartOne(std::string_view spec) {
  const size_t equals = spec.find('='), at = spec.rfind('@');
  if (spec.empty() || equals == std::string_view::npos || at == std::string_view::npos ||
      at < equals) {
    return;
  }
  const std::vector<std::string> names = Split(spec.substr(0, equals), ',');
  const std::vector<std::string> values = Split(spec.substr(equals + 1, at - equals - 1), '|');
  const int seconds = std::atoi(std::string(spec.substr(at + 1)).c_str());
  if (seconds <= 0 || values.empty()) return;
  g_threads.emplace_back([names, values, seconds] {
    for (const std::string& value : values) {
      std::unique_lock lock(g_mutex);
      if (g_wake.wait_for(lock, std::chrono::seconds(seconds), [] { return g_stop; })) return;
      lock.unlock();
      for (const std::string& name : names) {
        const bool set = rex::cvar::SetFlagByName(name, value);
        REXLOG_INFO("Cvar cycle: {} = {}{}", name, value, set ? "" : " (rejected)");
      }
    }
  });
}

void Start() {
  std::string spec = REXCVAR_GET(pinyon_shift_cvar_cycle);
  std::erase(spec, '"');
  g_stop = false;
  for (const std::string& part : Split(spec, ';')) StartOne(part);
}

void Stop() {
  {
    std::lock_guard lock(g_mutex);
    g_stop = true;
  }
  g_wake.notify_all();
  for (std::thread& thread : g_threads) {
    if (thread.joinable()) thread.join();
  }
  g_threads.clear();
}

}  // namespace pinyon_shift::cvar_cycle
