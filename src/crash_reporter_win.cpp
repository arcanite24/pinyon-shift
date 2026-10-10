#include "crash_reporter.h"

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <Windows.h>
#include <DbgHelp.h>

#include <array>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <iomanip>
#include <sstream>
#include <string_view>

namespace pinyon_shift::diagnostics::crash {
namespace {

std::filesystem::path g_crash_root;
std::string g_session_id;
std::atomic_flag g_access_fault_reported = ATOMIC_FLAG_INIT;

constexpr MINIDUMP_TYPE kCrashDumpType = static_cast<MINIDUMP_TYPE>(
    MiniDumpWithThreadInfo | MiniDumpWithUnloadedModules |
    MiniDumpWithIndirectlyReferencedMemory | MiniDumpWithFullMemoryInfo |
    MiniDumpWithHandleData);

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
  const std::filesystem::path dump_path = std::filesystem::path(base) += ".dmp";
  const std::filesystem::path text_path = std::filesystem::path(base) += ".txt";

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
  const std::filesystem::path dump_path = std::filesystem::path(base) += ".dmp";
  const std::filesystem::path text_path = std::filesystem::path(base) += ".txt";

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

void Install(const std::filesystem::path& crash_root, const std::string& session_id) {
  g_crash_root = crash_root;
  g_session_id = session_id;
  SetUnhandledExceptionFilter(UnhandledExceptionReporter);
  AddVectoredExceptionHandler(1, AccessViolationReporter);
}

void Refresh() { SetUnhandledExceptionFilter(UnhandledExceptionReporter); }

void RaiseAccessViolation() { RaiseException(EXCEPTION_ACCESS_VIOLATION, 0, 0, nullptr); }

void ExecuteNull() {
  volatile uintptr_t null_target = 0;
  reinterpret_cast<void (*)()>(null_target)();
}

}  // namespace pinyon_shift::diagnostics::crash
