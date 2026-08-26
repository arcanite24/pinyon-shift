#include "pinyon_shift_diagnostics.h"

#if !defined(_WIN32)
#error Pinyon Shift M2 diagnostics currently support Windows only.
#endif

#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <DbgHelp.h>
#include <intrin.h>

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

namespace pinyon_shift::diagnostics {
namespace {

constexpr uint32_t kDiagnosticsSchema = 1;
std::filesystem::path g_state_root;
std::filesystem::path g_event_path;
std::filesystem::path g_crash_root;
std::string g_session_id;
std::mutex g_event_mutex;
std::atomic_flag g_access_fault_reported = ATOMIC_FLAG_INIT;

constexpr MINIDUMP_TYPE kCrashDumpType = static_cast<MINIDUMP_TYPE>(
    MiniDumpWithThreadInfo | MiniDumpWithUnloadedModules |
    MiniDumpWithIndirectlyReferencedMemory | MiniDumpWithFullMemoryInfo |
    MiniDumpWithHandleData);

std::string UtcTimestamp(bool filename_safe) {
  const auto now = std::chrono::system_clock::now();
  const auto time = std::chrono::system_clock::to_time_t(now);
  std::tm utc{};
  gmtime_s(&utc, &time);
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
  std::wstring buffer(32768, L'\0');
  const DWORD length =
      GetModuleFileNameW(nullptr, buffer.data(), static_cast<DWORD>(buffer.size()));
  if (length == 0 || length >= buffer.size()) {
    return std::filesystem::current_path();
  }
  buffer.resize(length);
  return std::filesystem::path(buffer).parent_path();
}

struct BuildProvenance {
  std::string schema = "unknown";
  std::string pinyon_shift_commit = "unknown";
  std::string pinyon_shift_dirty = "unknown";
  std::string source_payload_sha256 = "unknown";
  std::string rexglue_commit = "unknown";
  std::string rexglue_patch_set_sha256 = "unknown";
  std::string rexglue_patch_count = "unknown";
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
  std::ifstream input(ExecutableDirectory() / "pinyon_shift_build.json",
                      std::ios::binary);
  if (!input) {
    return result;
  }
  std::ostringstream contents;
  contents << input.rdbuf();
  const std::string json = contents.str();
  result.schema = JsonStringField(json, "schema_version");
  // schema_version is numeric in the manifest; retain a useful value without
  // introducing a general JSON parser solely for trusted flat build metadata.
  if (result.schema == "unknown" &&
      std::regex_search(json, std::regex(R"("schema_version"\s*:\s*2)"))) {
    result.schema = "2";
  }
  result.pinyon_shift_commit = JsonStringField(json, "pinyon_shift_commit");
  result.pinyon_shift_dirty = JsonStringField(json, "pinyon_shift_dirty");
  result.source_payload_sha256 =
      JsonStringField(json, "pinyon_shift_source_payload_sha256");
  result.rexglue_commit = JsonStringField(json, "rexglue_commit");
  result.rexglue_patch_set_sha256 =
      JsonStringField(json, "rexglue_patch_set_sha256");
  result.rexglue_patch_count = JsonStringField(json, "rexglue_patch_count");
  result.executable_sha256 = JsonStringField(json, "executable_sha256");
  return result;
}

bool CpuHasSse41() {
  int registers[4]{};
  __cpuid(registers, 1);
  return (static_cast<uint32_t>(registers[2]) & (1u << 19)) != 0;
}

std::string CpuFeatureSummary() {
  int leaf1[4]{};
  int leaf7[4]{};
  __cpuid(leaf1, 1);
  __cpuidex(leaf7, 7, 0);
  const uint32_t ecx1 = static_cast<uint32_t>(leaf1[2]);
  const uint32_t ebx7 = static_cast<uint32_t>(leaf7[1]);
  return std::string("ssse3=") + ((ecx1 & (1u << 9)) ? "1" : "0") +
         ",sse4.1=" + ((ecx1 & (1u << 19)) ? "1" : "0") +
         ",avx=" + ((ecx1 & (1u << 28)) ? "1" : "0") +
         ",avx2=" + ((ebx7 & (1u << 5)) ? "1" : "0") +
         ",bmi1=" + ((ebx7 & (1u << 3)) ? "1" : "0") +
         ",bmi2=" + ((ebx7 & (1u << 8)) ? "1" : "0");
}

void WriteHandle(HANDLE file, std::string_view text) {
  DWORD written = 0;
  WriteFile(file, text.data(), static_cast<DWORD>(text.size()), &written, nullptr);
}

void WriteSymbolizedStack(HANDLE file, EXCEPTION_POINTERS* exception) {
  HANDLE process = GetCurrentProcess();
  SymSetOptions(SYMOPT_DEFERRED_LOADS | SYMOPT_LOAD_LINES | SYMOPT_UNDNAME);
  if (!SymInitialize(process, nullptr, TRUE)) {
    WriteHandle(file, "SymInitialize failed\r\n");
    return;
  }

  CONTEXT context = *exception->ContextRecord;
  STACKFRAME64 frame{};
  frame.AddrPC.Offset = context.Rip;
  frame.AddrPC.Mode = AddrModeFlat;
  frame.AddrFrame.Offset = context.Rbp;
  frame.AddrFrame.Mode = AddrModeFlat;
  frame.AddrStack.Offset = context.Rsp;
  frame.AddrStack.Mode = AddrModeFlat;

  std::array<unsigned char, sizeof(SYMBOL_INFO) + MAX_SYM_NAME> symbol_storage{};
  auto* symbol = reinterpret_cast<SYMBOL_INFO*>(symbol_storage.data());
  symbol->SizeOfStruct = sizeof(SYMBOL_INFO);
  symbol->MaxNameLen = MAX_SYM_NAME;

  for (uint32_t index = 0; index < 64 && frame.AddrPC.Offset != 0; ++index) {
    const DWORD64 address = frame.AddrPC.Offset;
    DWORD64 symbol_displacement = 0;
    std::ostringstream line;
    line << '#' << index << " 0x" << std::hex << std::setw(16) << std::setfill('0') << address;
    if (SymFromAddr(process, address, &symbol_displacement, symbol)) {
      line << ' ' << symbol->Name << "+0x" << symbol_displacement;
    }
    IMAGEHLP_LINE64 source{};
    source.SizeOfStruct = sizeof(source);
    DWORD line_displacement = 0;
    if (SymGetLineFromAddr64(process, address, &line_displacement, &source)) {
      line << " (" << source.FileName << ':' << std::dec << source.LineNumber << ')';
    }
    line << "\r\n";
    WriteHandle(file, line.str());

    if (!StackWalk64(IMAGE_FILE_MACHINE_AMD64, process, GetCurrentThread(), &frame, &context,
                     nullptr, SymFunctionTableAccess64, SymGetModuleBase64, nullptr)) {
      break;
    }
  }
  SymCleanup(process);
}

void WriteNativeContext(HANDLE file, const CONTEXT& context) {
  char registers[768]{};
  const int length = std::snprintf(
      registers, sizeof(registers),
      "native_context rip=%016llX rsp=%016llX rbp=%016llX\r\n"
      "rax=%016llX rbx=%016llX rcx=%016llX rdx=%016llX\r\n"
      "rsi=%016llX rdi=%016llX r8=%016llX r9=%016llX\r\n"
      "r10=%016llX r11=%016llX r12=%016llX r13=%016llX\r\n"
      "r14=%016llX r15=%016llX\r\n",
      static_cast<unsigned long long>(context.Rip),
      static_cast<unsigned long long>(context.Rsp),
      static_cast<unsigned long long>(context.Rbp),
      static_cast<unsigned long long>(context.Rax),
      static_cast<unsigned long long>(context.Rbx),
      static_cast<unsigned long long>(context.Rcx),
      static_cast<unsigned long long>(context.Rdx),
      static_cast<unsigned long long>(context.Rsi),
      static_cast<unsigned long long>(context.Rdi),
      static_cast<unsigned long long>(context.R8),
      static_cast<unsigned long long>(context.R9),
      static_cast<unsigned long long>(context.R10),
      static_cast<unsigned long long>(context.R11),
      static_cast<unsigned long long>(context.R12),
      static_cast<unsigned long long>(context.R13),
      static_cast<unsigned long long>(context.R14),
      static_cast<unsigned long long>(context.R15));
  if (length > 0) {
    WriteHandle(file, std::string_view(registers, static_cast<size_t>(length)));
  }
}

void WriteFaultModule(HANDLE file, const void* address) {
  HMODULE module = nullptr;
  if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                             GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                         reinterpret_cast<LPCWSTR>(address), &module) ||
      !module) {
    WriteHandle(file, "fault_module=unknown fault_offset=unknown\r\n");
    return;
  }

  std::wstring buffer(32768, L'\0');
  const DWORD length =
      GetModuleFileNameW(module, buffer.data(), static_cast<DWORD>(buffer.size()));
  if (length == 0 || length >= buffer.size()) {
    WriteHandle(file, "fault_module=unknown fault_offset=unknown\r\n");
    return;
  }
  buffer.resize(length);
  const std::string name = std::filesystem::path(buffer).filename().string();
  const auto offset = reinterpret_cast<uintptr_t>(address) -
                      reinterpret_cast<uintptr_t>(module);
  char line[512]{};
  const int line_length = std::snprintf(
      line, sizeof(line), "fault_module=%s fault_offset=0x%llX\r\n", name.c_str(),
      static_cast<unsigned long long>(offset));
  if (line_length > 0) {
    WriteHandle(file, std::string_view(line, static_cast<size_t>(line_length)));
  }
}

LONG WINAPI UnhandledExceptionReporter(EXCEPTION_POINTERS* exception) {
  EXCEPTION_RECORD exception_record = *exception->ExceptionRecord;
  CONTEXT context = *exception->ContextRecord;
  EXCEPTION_POINTERS snapshot{&exception_record, &context};
  exception = &snapshot;
  const std::filesystem::path base = g_crash_root / (g_session_id + "-unhandled");
  const std::filesystem::path dump_path = base.string() + ".dmp";
  const std::filesystem::path text_path = base.string() + ".txt";

  HANDLE dump = CreateFileW(dump_path.c_str(), GENERIC_WRITE, FILE_SHARE_READ, nullptr,
                            CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
  if (dump != INVALID_HANDLE_VALUE) {
    MINIDUMP_EXCEPTION_INFORMATION exception_info{};
    exception_info.ThreadId = GetCurrentThreadId();
    exception_info.ExceptionPointers = exception;
    exception_info.ClientPointers = FALSE;
    MiniDumpWriteDump(GetCurrentProcess(), GetCurrentProcessId(), dump, kCrashDumpType,
                      &exception_info, nullptr, nullptr);
    CloseHandle(dump);
  }

  HANDLE text = CreateFileW(text_path.c_str(), GENERIC_WRITE, FILE_SHARE_READ, nullptr,
                            CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
  if (text != INVALID_HANDLE_VALUE) {
    char header[256]{};
    const int length = std::snprintf(
        header, sizeof(header), "Pinyon Shift unhandled exception\r\ncode=0x%08lX address=%p "
                                "thread=%lu\r\nsession=%s\r\n",
        exception->ExceptionRecord->ExceptionCode, exception->ExceptionRecord->ExceptionAddress,
        GetCurrentThreadId(), g_session_id.c_str());
    if (length > 0) {
      WriteHandle(text, std::string_view(header, static_cast<size_t>(length)));
    }
    WriteFaultModule(text, exception->ExceptionRecord->ExceptionAddress);
    WriteNativeContext(text, *exception->ContextRecord);
    WriteSymbolizedStack(text, exception);
    CloseHandle(text);
  }
  return EXCEPTION_EXECUTE_HANDLER;
}

void WriteAccessViolationSnapshot(EXCEPTION_POINTERS* exception) {
  EXCEPTION_RECORD exception_record = *exception->ExceptionRecord;
  CONTEXT context = *exception->ContextRecord;
  EXCEPTION_POINTERS snapshot{&exception_record, &context};
  exception = &snapshot;
  const ULONG_PTR operation = exception->ExceptionRecord->ExceptionInformation[0];
  const char* operation_name =
      operation == 0 ? "read" : operation == 1 ? "write" : operation == 8 ? "execute" : "unknown";
  const std::filesystem::path base =
      g_crash_root / (g_session_id + "-" + operation_name + "-av");
  const std::filesystem::path dump_path = base.string() + ".dmp";
  const std::filesystem::path text_path = base.string() + ".txt";

  HANDLE dump = CreateFileW(dump_path.c_str(), GENERIC_WRITE, FILE_SHARE_READ, nullptr,
                            CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
  if (dump != INVALID_HANDLE_VALUE) {
    MINIDUMP_EXCEPTION_INFORMATION exception_info{};
    exception_info.ThreadId = GetCurrentThreadId();
    exception_info.ExceptionPointers = exception;
    exception_info.ClientPointers = FALSE;
    MiniDumpWriteDump(GetCurrentProcess(), GetCurrentProcessId(), dump, kCrashDumpType,
                      &exception_info, nullptr, nullptr);
    CloseHandle(dump);
  }

  HANDLE text = CreateFileW(text_path.c_str(), GENERIC_WRITE, FILE_SHARE_READ, nullptr,
                            CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
  if (text != INVALID_HANDLE_VALUE) {
    char header[320]{};
    const int length = std::snprintf(
        header, sizeof(header),
        "Pinyon Shift first-chance access violation snapshot\r\n"
        "code=0x%08lX address=%p operation=%s target=0x%llX thread=%lu\r\n"
        "session=%s\r\n",
        exception->ExceptionRecord->ExceptionCode,
        exception->ExceptionRecord->ExceptionAddress,
        operation_name,
        static_cast<unsigned long long>(exception->ExceptionRecord->ExceptionInformation[1]),
        GetCurrentThreadId(), g_session_id.c_str());
    if (length > 0) {
      WriteHandle(text, std::string_view(header, static_cast<size_t>(length)));
    }
    WriteFaultModule(text, exception->ExceptionRecord->ExceptionAddress);
    WriteNativeContext(text, *exception->ContextRecord);
    CloseHandle(text);
  }
}

LONG CALLBACK AccessViolationReporter(EXCEPTION_POINTERS* exception) {
  if (!exception || !exception->ExceptionRecord ||
      exception->ExceptionRecord->ExceptionCode != EXCEPTION_ACCESS_VIOLATION ||
      exception->ExceptionRecord->NumberParameters < 2) {
    return EXCEPTION_CONTINUE_SEARCH;
  }

  // Some runtime components replace the process unhandled-exception filter after
  // startup. Capture the first access violation at first chance as a fallback so
  // read/write corruption and invalid indirect calls still leave an actionable dump. Avoid
  // first-chance DbgHelp symbolization here because the fault may occur on a
  // runtime thread whose live stack cannot safely tolerate that work.
  if (!g_access_fault_reported.test_and_set()) {
    WriteAccessViolationSnapshot(exception);
  }
  return EXCEPTION_CONTINUE_SEARCH;
}

}  // namespace

std::optional<std::filesystem::path> EnvironmentPath(const char* name) {
  char* value = nullptr;
  size_t length = 0;
  if (_dupenv_s(&value, &length, name) != 0 || !value || length <= 1) {
    std::free(value);
    return std::nullopt;
  }
  std::filesystem::path path(value);
  std::free(value);
  return std::filesystem::absolute(path).lexically_normal();
}

bool InitializeEarly() {
  if (!g_state_root.empty()) {
    return CpuHasSse41();
  }

  g_state_root = EnvironmentPath("PINYON_SHIFT_STATE_ROOT")
                     .value_or(ExecutableDirectory() / "pinyon_shift_state");
  g_state_root = std::filesystem::absolute(g_state_root).lexically_normal();
  g_session_id = UtcTimestamp(true) + "-p" + std::to_string(GetCurrentProcessId());
  g_crash_root = g_state_root / "crashes";
  g_event_path = g_state_root / "logs" / (g_session_id + ".jsonl");

  std::error_code error;
  for (const char* directory : {"cache", "config", "crashes", "logs", "update", "user"}) {
    std::filesystem::create_directories(g_state_root / directory, error);
    if (error) {
      return false;
    }
  }

  SetUnhandledExceptionFilter(UnhandledExceptionReporter);
  AddVectoredExceptionHandler(1, AccessViolationReporter);
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
               {"rexglue_patch_set_sha256", build.rexglue_patch_set_sha256},
               {"rexglue_patch_count", build.rexglue_patch_count},
               {"executable_sha256", build.executable_sha256},
               {"cpu_baseline", PINYON_SHIFT_CPU_BASELINE},
               {"cpu_features", features},
               {"state_root", g_state_root.string()}});

  if (!CpuHasSse41()) {
    RecordEvent("cpu.unsupported", {{"required", "sse4.1"}, {"detected", features}});
    MessageBoxW(nullptr,
                L"Pinyon Shift requires an x86-64 processor with SSE4.1 support.",
                L"Unsupported processor", MB_OK | MB_ICONERROR);
    return false;
  }

  char* crash_test = nullptr;
  size_t crash_test_length = 0;
  const bool run_crash_test =
      _dupenv_s(&crash_test, &crash_test_length, "PINYON_SHIFT_CRASH_SELF_TEST") == 0 &&
      crash_test && crash_test_length > 1 && std::string_view(crash_test) == "1";
  std::free(crash_test);
  if (run_crash_test) {
    RecordEvent("diagnostics.crash_test.begin");
    RaiseException(EXCEPTION_ACCESS_VIOLATION, 0, 0, nullptr);
    return false;
  }

  char* execute_crash_test = nullptr;
  size_t execute_crash_test_length = 0;
  const bool run_execute_crash_test =
      _dupenv_s(&execute_crash_test, &execute_crash_test_length,
                "PINYON_SHIFT_EXECUTE_CRASH_SELF_TEST") == 0 &&
      execute_crash_test && execute_crash_test_length > 1 &&
      std::string_view(execute_crash_test) == "1";
  std::free(execute_crash_test);
  if (run_execute_crash_test) {
    RecordEvent("diagnostics.execute_crash_test.begin");
    volatile uintptr_t null_target = 0;
    reinterpret_cast<void (*)()>(null_target)();
    return false;
  }
  return true;
}

void RefreshCrashReporter() {
  SetUnhandledExceptionFilter(UnhandledExceptionReporter);
}

const std::filesystem::path& StateRoot() {
  return g_state_root;
}

const std::string& SessionId() {
  return g_session_id;
}

void RecordEvent(std::string_view event, std::initializer_list<Field> fields) {
  std::ostringstream json;
  json << "{\"schema\":" << kDiagnosticsSchema << ",\"utc\":\"" << UtcTimestamp(false)
       << "\",\"session\":\"" << JsonEscape(g_session_id) << "\",\"event\":\""
       << JsonEscape(event) << "\",\"pid\":\"" << GetCurrentProcessId()
       << "\",\"tid\":\"" << GetCurrentThreadId() << '"';
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
