#include "pinyon_shift_diagnostics.h"

#include <array>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <mutex>
#include <regex>
#include <sstream>
#include <string>
#include <system_error>

#include <rex/logging.h>
#include <rex/filesystem.h>

#include "crash_reporter.h"
#include "platform/host_platform.h"

// After every other header: its __cpuid macro breaks the declaration of the
// function of the same name in clang's MSVC <intrin.h>, which fmt includes
// (issue #325, where no precompiled header had included it first).
#if defined(__x86_64__) || defined(_M_X64)
#include <cpuid.h>
#endif

namespace pinyon_shift::diagnostics {
namespace {

constexpr uint32_t kDiagnosticsSchema = 1;
std::filesystem::path g_state_root;
std::filesystem::path g_event_path;
std::string g_session_id;
std::mutex g_event_mutex;

std::string UtcTimestamp(bool filename_safe) {
  const auto now = std::chrono::system_clock::now();
  const auto time = std::chrono::system_clock::to_time_t(now);
  std::tm utc{};
#if defined(_WIN32)
  gmtime_s(&utc, &time);
#else
  gmtime_r(&time, &utc);
#endif
  std::ostringstream stream;
  stream << std::put_time(&utc, filename_safe ? "%Y%m%dT%H%M%SZ" : "%Y-%m-%dT%H:%M:%SZ");
  return stream.str();
}

std::string JsonEscape(std::string_view value) {
  std::string escaped;
  escaped.reserve(value.size() + 8);
  constexpr char hex[] = "0123456789ABCDEF";
  for (const unsigned char character : value) {
    switch (character) {
      case '\"':
        escaped += "\\\"";
        break;
      case '\\':
        escaped += "\\\\";
        break;
      case '\b':
        escaped += "\\b";
        break;
      case '\f':
        escaped += "\\f";
        break;
      case '\n':
        escaped += "\\n";
        break;
      case '\r':
        escaped += "\\r";
        break;
      case '\t':
        escaped += "\\t";
        break;
      default:
        if (character < 0x20) {
          escaped += "\\u00";
          escaped += hex[character >> 4];
          escaped += hex[character & 0x0F];
        } else {
          escaped += static_cast<char>(character);
        }
        break;
    }
  }
  return escaped;
}

std::filesystem::path ExecutableDirectory() {
  const std::filesystem::path executable = platform::ExecutablePath();
  return executable.empty() ? std::filesystem::current_path() : executable.parent_path();
}

struct BuildProvenance {
  std::string schema = "unknown";
  std::string pinyon_shift_commit = "unknown";
  std::string pinyon_shift_dirty = "unknown";
  std::string source_payload_sha256 = "unknown";
  std::string rexglue_commit = "unknown";
  std::string rexglue_dirty = "unknown";
  std::string executable_sha256 = "unknown";
};

std::string JsonStringField(const std::string& json, std::string_view key) {
  const std::regex pattern("\"" + std::string(key) + "\"\\s*:\\s*\"([^\"]*)\"");
  std::smatch match;
  return std::regex_search(json, match, pattern) && match.size() == 2
             ? match[1].str()
             : "unknown";
}

BuildProvenance LoadBuildProvenance() {
  BuildProvenance result;
  // Beside the executable; Android packages it as an asset the activity
  // copies out and names in PINYON_SHIFT_BUILD_MANIFEST.
  const auto manifest = EnvironmentPath("PINYON_SHIFT_BUILD_MANIFEST")
                            .value_or(ExecutableDirectory() / "pinyon_shift_build.json");
  std::ifstream input(manifest, std::ios::binary);
  if (!input) {
    return result;
  }
  std::ostringstream contents;
  contents << input.rdbuf();
  const std::string json = contents.str();
  result.schema = JsonStringField(json, "schema_version");
  // schema_version is numeric in the manifest; retain a useful value without
  // introducing a general JSON parser solely for trusted flat build metadata.
  std::smatch schema_match;
  if (result.schema == "unknown" &&
      std::regex_search(json, schema_match,
                        std::regex(R"("schema_version"\s*:\s*([23]))"))) {
    result.schema = schema_match[1].str();
  }
  result.pinyon_shift_commit = JsonStringField(json, "pinyon_shift_commit");
  result.pinyon_shift_dirty = JsonStringField(json, "pinyon_shift_dirty");
  result.source_payload_sha256 =
      JsonStringField(json, "pinyon_shift_source_payload_sha256");
  result.rexglue_commit = JsonStringField(json, "rexglue_commit");
  result.rexglue_dirty = JsonStringField(json, "rexglue_dirty");
  result.executable_sha256 = JsonStringField(json, "executable_sha256");
  return result;
}

#if defined(__x86_64__) || defined(_M_X64)
bool CpuHasSse41() {
  unsigned int eax = 0, ebx = 0, ecx = 0, edx = 0;
  return __get_cpuid(1, &eax, &ebx, &ecx, &edx) && (ecx & (1u << 19)) != 0;
}

std::string CpuFeatureSummary() {
  unsigned int eax = 0, ebx7 = 0, ecx1 = 0, edx = 0, unused = 0;
  __get_cpuid(1, &eax, &unused, &ecx1, &edx);
  __get_cpuid_count(7, 0, &eax, &ebx7, &unused, &edx);
  return std::string("ssse3=") + ((ecx1 & (1u << 9)) ? "1" : "0") +
         ",sse4.1=" + ((ecx1 & (1u << 19)) ? "1" : "0") +
         ",avx=" + ((ecx1 & (1u << 28)) ? "1" : "0") +
         ",avx2=" + ((ebx7 & (1u << 5)) ? "1" : "0") +
         ",bmi1=" + ((ebx7 & (1u << 3)) ? "1" : "0") +
         ",bmi2=" + ((ebx7 & (1u << 8)) ? "1" : "0");
}
#else
// The x86 baseline check does not apply to other architectures.
bool CpuHasSse41() { return true; }
std::string CpuFeatureSummary() { return "non-x86"; }
#endif

}  // namespace

std::optional<std::filesystem::path> EnvironmentPath(const char* name) {
  return platform::EnvironmentPath(name);
}

bool InitializeEarly() {
  if (!g_state_root.empty()) {
    return CpuHasSse41();
  }

  g_state_root = EnvironmentPath("PINYON_SHIFT_STATE_ROOT")
                     .value_or(ExecutableDirectory() / "pinyon_shift_state");
  g_state_root = std::filesystem::absolute(g_state_root).lexically_normal();
  g_session_id = UtcTimestamp(true) + "-p" + std::to_string(platform::ProcessId());
  g_event_path = g_state_root / "logs" / (g_session_id + ".jsonl");

  std::error_code error;
  for (const char* directory : {"cache", "config", "crashes", "logs", "update", "user"}) {
    std::filesystem::create_directories(g_state_root / directory, error);
    if (error) {
      // The only trace of a silent exit on Android: logcat.
      REXLOG_ERROR("Cannot create the state folder {}: {}",
                   rex::path_to_utf8(g_state_root / directory), error.message());
      return false;
    }
  }

  crash::Install(g_state_root / "crashes", g_session_id);
  const std::string features = CpuFeatureSummary();
  const BuildProvenance build = LoadBuildProvenance();
  RecordEvent("process.start",
              {{"diagnostics_schema", "1"},
               {"build_config", REXGLUE_BUILD_CONFIG},
               {"build_manifest_schema", build.schema},
               {"pinyon_shift_commit", build.pinyon_shift_commit},
               {"pinyon_shift_dirty", build.pinyon_shift_dirty},
               {"pinyon_shift_source_payload_sha256", build.source_payload_sha256},
               {"rexglue_commit", build.rexglue_commit},
               {"rexglue_dirty", build.rexglue_dirty},
               {"executable_sha256", build.executable_sha256},
               {"cpu_baseline", PINYON_SHIFT_CPU_BASELINE},
               {"cpu_features", features},
               {"state_root", rex::path_to_utf8(g_state_root)}});

  if (!CpuHasSse41()) {
    RecordEvent("cpu.unsupported", {{"required", "sse4.1"}, {"detected", features}});
    platform::ShowFatalError("Unsupported processor",
                             "Pinyon Shift requires an x86-64 processor with SSE4.1 support.");
    return false;
  }

  if (platform::EnvironmentFlag("PINYON_SHIFT_CRASH_SELF_TEST")) {
    RecordEvent("diagnostics.crash_test.begin");
    crash::RaiseAccessViolation();
    return false;
  }
  if (platform::EnvironmentFlag("PINYON_SHIFT_EXECUTE_CRASH_SELF_TEST")) {
    RecordEvent("diagnostics.execute_crash_test.begin");
    crash::ExecuteNull();
    return false;
  }
  return true;
}

void RefreshCrashReporter() { crash::Refresh(); }

const std::filesystem::path& StateRoot() {
  return g_state_root;
}

const std::string& SessionId() {
  return g_session_id;
}

void RecordEvent(std::string_view event, std::initializer_list<Field> fields) {
  RecordEvent(event, std::span<const Field>(fields.begin(), fields.size()));
}

void RecordEvent(std::string_view event, std::span<const Field> fields) {
  std::ostringstream json;
  json << "{\"schema\":" << kDiagnosticsSchema << ",\"utc\":\"" << UtcTimestamp(false)
       << "\",\"session\":\"" << JsonEscape(g_session_id) << "\",\"event\":\""
       << JsonEscape(event) << "\",\"pid\":\"" << platform::ProcessId()
       << "\",\"tid\":\"" << platform::ThreadId() << '"';
  for (const auto& [key, value] : fields) {
    json << ",\"" << JsonEscape(key) << "\":\"" << JsonEscape(value) << '"';
  }
  json << '}';
  const std::string line = json.str();

  {
    std::scoped_lock lock(g_event_mutex);
    std::ofstream output(g_event_path, std::ios::app | std::ios::binary);
    if (output) {
      output << line << '\n';
      output.flush();
    }
  }
  REXLOG_INFO("M2_EVENT {}", line);
}

}  // namespace pinyon_shift::diagnostics
