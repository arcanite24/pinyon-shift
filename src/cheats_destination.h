#pragma once

#include <array>
#include <charconv>
#include <cmath>
#include <optional>
#include <string_view>

namespace pinyon_shift::cheats {

using Destination = std::array<float, 3>;

inline bool ValidDestination(const Destination& point) {
  for (float value : point) {
    if (!std::isfinite(value) || std::abs(value) > 100000.0f) return false;
  }
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
    const auto parsed = std::from_chars(value.data(), value.data() + value.size(), point[i]);
    if (parsed.ec != std::errc{} || parsed.ptr != value.data() + value.size()) return {};
    if (comma != text.npos) text.remove_prefix(comma + 1);
  }
  return ValidDestination(point) ? std::optional(point) : std::nullopt;
}

}  // namespace pinyon_shift::cheats
