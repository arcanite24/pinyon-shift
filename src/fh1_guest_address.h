#pragma once

#include <cstdint>

// Guest addresses in host code are written as their base-disc (0.0.0.10)
// values and wrapped in FH1_ADDR. A title-update v4 build translates them at
// compile time through the generated table in fh1_v4_addresses.inc
// (tools/generate-fh1-v4-addresses.py); an address without a verified v4
// mapping fails to compile instead of pointing at unrelated code.

namespace pinyon_shift::fh1 {

#if defined(PINYON_SHIFT_TITLE_UPDATE_V4) && PINYON_SHIFT_TITLE_UPDATE_V4
struct GuestAddressPair {
  uint32_t base;
  uint32_t v4;
};

inline constexpr GuestAddressPair kV4GuestAddresses[] = {
#include "fh1_v4_addresses.inc"
};

consteval uint32_t GuestAddress(uint32_t base) {
  for (const auto& pair : kV4GuestAddresses) {
    if (pair.base == base) return pair.v4;
  }
  // Reaching this in a constant evaluation is a compile error.
  throw "guest address has no verified v4 mapping; run tools/generate-fh1-v4-addresses.py";
}
#else
consteval uint32_t GuestAddress(uint32_t base) { return base; }
#endif

}  // namespace pinyon_shift::fh1

#define FH1_ADDR(base) (::pinyon_shift::fh1::GuestAddress(base))

// Addresses used only by base-disc features that the v4 title update replaces
// natively (the base-disc Rally adapter). They are 0 in a v4 build, where
// those features must stay disabled; see kTitleUpdateV4.
#if defined(PINYON_SHIFT_TITLE_UPDATE_V4) && PINYON_SHIFT_TITLE_UPDATE_V4
#define FH1_BASE_ONLY_ADDR(base) (0u)
#else
#define FH1_BASE_ONLY_ADDR(base) (::pinyon_shift::fh1::GuestAddress(base))
#endif

namespace pinyon_shift::fh1 {
#if defined(PINYON_SHIFT_TITLE_UPDATE_V4) && PINYON_SHIFT_TITLE_UPDATE_V4
inline constexpr bool kTitleUpdateV4 = true;
#else
inline constexpr bool kTitleUpdateV4 = false;
#endif

// Native input actions that resume from the pause menu. v4 inserts an input
// action, so both move up by one (its pause handler compares 96/104).
inline constexpr uint32_t kResumeActionBack = kTitleUpdateV4 ? 96 : 95;
inline constexpr uint32_t kResumeActionStart = kTitleUpdateV4 ? 104 : 103;
}  // namespace pinyon_shift::fh1
