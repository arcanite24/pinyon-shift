#pragma once

#include <array>
#include <cerrno>
#include <cmath>
#include <cstdlib>
#include <optional>
#include <string>
#include <string_view>

#include <locale.h>
#if defined(__APPLE__)
#include <xlocale.h>
#endif

namespace pinyon_shift::cheats {

using Destination = std::array<float, 3>;

inline bool ValidDestination(const Destination& point) {
  for (float value : point) {
    if (!std::isfinite(value) || std::abs(value) > 100000.0f) return false;
  }
  return true;
}

// Locale-independent float parse. std::from_chars for float is unavailable
// below macOS 26 (libc++ availability), and the macOS build targets 13.3, so
// this uses strtof in the "C" locale on a NUL-terminated copy. The whole token
// must be consumed. Like from_chars, it rejects leading '+', whitespace and
// hex floats, and treats a result outside the float range as an error.
inline bool ParseFloatToken(std::string_view value, float& out) {
  if (value.empty() || value.front() == '+') return false;
  for (char c : value) {
    const bool ok = (c >= '0' && c <= '9') || c == '-' || c == '+' || c == '.' ||
                    c == 'e' || c == 'E' || c == 'n' || c == 'a' || c == 'i' || c == 'f' ||
                    c == 'N' || c == 'A' || c == 'I' || c == 'F';
    if (!ok) return false;  // blocks whitespace, hex ("0x"), "(...)" and letters
  }
  const std::string token(value);
  char* end = nullptr;
  errno = 0;
#if defined(_WIN32)
  static _locale_t c_locale = _create_locale(LC_NUMERIC, "C");
  const float parsed = _strtof_l(token.c_str(), &end, c_locale);
#else
  static locale_t c_locale = newlocale(LC_NUMERIC_MASK, "C", static_cast<locale_t>(nullptr));
  const float parsed = strtof_l(token.c_str(), &end, c_locale);
#endif
  if (end != token.c_str() + token.size() || errno == ERANGE) return false;
  out = parsed;
  return true;
}

// Coordinates supplied by a setting or a mod must be exactly three finite metres.
inline std::optional<Destination> ParseDestination(std::string_view text) {
  Destination point{};
  for (size_t i = 0; i < point.size(); ++i) {
    const size_t comma = text.find(',');
    if ((comma != text.npos) != (i + 1 < point.size())) return {};
    auto value = text.substr(0, comma);
    while (!value.empty() && value.front() == ' ') value.remove_prefix(1);
    while (!value.empty() && value.back() == ' ') value.remove_suffix(1);
    if (value.empty()) return {};
    if (!ParseFloatToken(value, point[i])) return {};
    if (comma != text.npos) text.remove_prefix(comma + 1);
  }
  return ValidDestination(point) ? std::optional(point) : std::nullopt;
}

}  // namespace pinyon_shift::cheats
