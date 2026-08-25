#pragma once

#include <filesystem>
#include <initializer_list>
#include <optional>
#include <string>
#include <string_view>
#include <utility>

namespace pinyon_shift::diagnostics {

using Field = std::pair<std::string_view, std::string_view>;

// Installs the crash reporter, resolves the deterministic state root, and
// checks the build's documented CPU floor before guest/runtime work begins.
bool InitializeEarly();

// Reinstalls the top-level filter after runtime components that may replace it.
// The vectored first-chance reporter remains installed for precursor faults.
void RefreshCrashReporter();

const std::filesystem::path& StateRoot();
const std::string& SessionId();
std::optional<std::filesystem::path> EnvironmentPath(const char* name);

// Writes one schema-versioned JSON object to the session JSONL file and to the
// ReXGlue logger. Values are JSON-escaped and intentionally represented as
// strings so callers never inject untrusted JSON fragments.
void RecordEvent(std::string_view event, std::initializer_list<Field> fields = {});

}  // namespace pinyon_shift::diagnostics
