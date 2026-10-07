#include "dlc_treasure_map.h"
#include "fh1_guest_address.h"

#include <algorithm>
#include <atomic>
#include <cstdint>
#include <utility>

#include <fmt/format.h>

#include <rex/cvar.h>
#include <rex/memory.h>
#include <rex/system/kernel_state.h>
#include <rex/system/xmemory.h>

#include "mod/mod_host.h"
#include "pinyon_shift_diagnostics.h"

// On by default: the launcher offers it as a setting, since the purchase can
// no longer be made.
REXCVAR_DEFINE_BOOL(pinyon_shift_dlc_treasure_map, true, "Pinyon Shift",
                    "Own the Treasure Map add-on: every discount sign, and each barn find's "
                    "exact location once its rumour starts, show on the map, as buying it did. "
                    "Applied in free roam and saved with the profile; turning it off later does "
                    "not hide them again")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

// The Treasure Map is not a Marketplace content package. FH1 sold it in its
// in-game marketplace (the pause map's BUY TREASURE MAP, InGameMarketplace.str)
// for Tokens, Forza assets counted and consumed by Turn 10's web service
// (ForzaUserGetForzaAssetCounts, ForzaUserTwoPhaseConsumeForzaAsset), never
// through XamContent. The purchase is a CTreasureMapConsumeAssetTransaction
// (vtable 0x8201D920, base Forza::CConsumableAssetManager::ITransaction, made
// by sub_826DF9A0 for the map screen); when the service confirms it, its
// completion (sub_82560B80, vtable +28, r4 the result) shows the TREASURE MAP
// notification and calls sub_828AF6F8 on the activity manager, and that is
// all a purchase does. The reveal sets each discount sign's, barn find's,
// speed camera's, average speed zone's and gas station's revealed byte (+8)
// and its saved record's (+40), so the profile keeps it: at load a revealed
// record re-runs the reveal (sub_828B99C8), and a barn find whose rumour
// starts later shows its exact location (sub_828BC658, at status 5). There
// is no other entitlement: the map screen offers the purchase while
// sub_828AF780 finds an unrevealed activity. With the token service gone, the
// host runs that same reveal itself.
namespace {

// The activity manager, as sub_82560B80 reaches it: the component list
// [[[0x832DF024] + 4] + 76] (sub_825F6FB0), an array indexed by the manager's
// component index at 0x832FEE8C; the activities are a vector of pointers at
// +4 (begin) and +8 (end).
constexpr uint32_t kGameHolder = FH1_ADDR(0x832DF024u);
constexpr uint32_t kHolderHandle = 4;
constexpr uint32_t kHandleComponents = 76;
constexpr uint32_t kActivityManagerIndex = FH1_ADDR(0x832FEE8Cu);
constexpr uint32_t kManagerBegin = 4;
constexpr uint32_t kManagerEnd = 8;
constexpr uint32_t kActivityRevealed = 8;  // u8, set by an activity's reveal (vtable +72)

// sub_828BC9D8: nonzero while free roam's collectibles are live (free roam,
// not the first-time career); r3 is ignored.
constexpr uint32_t kCollectiblesLive = FH1_ADDR(0x828BC9D8u);
// sub_828AF780(manager): 1 when every revealable activity with a saved
// record is revealed, the state a bought Treasure Map leaves.
constexpr uint32_t kAllRevealed = FH1_ADDR(0x828AF780u);
// sub_828AF6F8(manager): the Treasure Map's reveal.
constexpr uint32_t kRevealAll = FH1_ADDR(0x828AF6F8u);

bool Readable(uint32_t address, uint32_t size) {
  if (address == 0 || size == 0 || address + size - 1u < address) return false;
  auto* memory = rex::system::kernel_state()->memory();
  const uint32_t end = address + size - 1u;
  auto* heap = memory->LookupHeap(address);
  if (!heap || heap->QueryRangeAccess(address, end) == rex::memory::PageAccess::kNoAccess) {
    return false;
  }
  // The guest page table can look readable over a decommitted host page.
  const size_t page_size = rex::memory::page_size();
  uint64_t cursor = address;
  while (cursor <= end) {
    auto* host = memory->TranslateVirtual(static_cast<uint32_t>(cursor));
    if (!rex::memory::IsHostReadable(host)) {
      return false;
    }
    const size_t page_left = page_size - (reinterpret_cast<uintptr_t>(host) % page_size);
    cursor += std::min<uint64_t>(uint64_t(end) - cursor + 1u, page_left);
  }
  return true;
}

uint32_t Load32(uint32_t address) {
  auto* base = rex::system::kernel_state()->memory()->virtual_membase();
  return static_cast<uint32_t>(*rex::memory::GuestPtr<rex::be_u32*>(base, address));
}

uint8_t Load8(uint32_t address) {
  auto* base = rex::system::kernel_state()->memory()->virtual_membase();
  return *rex::memory::GuestPtr<uint8_t*>(base, address);
}

// A pointer field, 0 unless it and `size` bytes behind it are readable.
uint32_t LoadPointer(uint32_t address, uint32_t size) {
  if (!Readable(address, 4)) return 0;
  const uint32_t value = Load32(address);
  return Readable(value, size) ? value : 0;
}

uint32_t ActivityManager() {
  const uint32_t holder = LoadPointer(kGameHolder, kHolderHandle + 4);
  const uint32_t handle = holder ? LoadPointer(holder + kHolderHandle, kHandleComponents + 4) : 0;
  const uint32_t components = handle ? LoadPointer(handle + kHandleComponents, 4) : 0;
  const uint32_t array = components ? LoadPointer(components, 4) : 0;
  if (!array || !Readable(kActivityManagerIndex, 4)) return 0;
  const uint32_t index = Load32(kActivityManagerIndex);
  if (index > 4096) return 0;
  return LoadPointer(array + 4 * index, kManagerEnd + 4);
}

// Activities and how many of them are revealed, 0 and 0 for an unreadable
// list.
std::pair<uint32_t, uint32_t> CountRevealed(uint32_t manager) {
  const uint32_t begin = Load32(manager + kManagerBegin);
  const uint32_t end = Load32(manager + kManagerEnd);
  if (end < begin || (end - begin) % 4 != 0 || end - begin > 4 * 4096 ||
      !Readable(begin, end - begin)) {
    return {0, 0};
  }
  uint32_t revealed = 0;
  for (uint32_t slot = begin; slot < end; slot += 4) {
    const uint32_t activity = LoadPointer(slot, kActivityRevealed + 1);
    revealed += activity && Load8(activity + kActivityRevealed) != 0 ? 1 : 0;
  }
  return {(end - begin) / 4, revealed};
}

std::atomic<bool> g_queued{false};

// One check, on the title's main thread: reveals everything once, when free
// roam's collectibles are live and something is still hidden. Logs
// dlc.treasure_map when it reveals and when it first finds the map owned.
void ApplyTreasureMap() {
  static uint32_t logged_owned = 0;
  const uint32_t manager = ActivityManager();
  if (manager == 0 || !pinyon_shift::dlc::GameModeReady()) return;
  if ((pinyon_shift::mod::CallGuest(kCollectiblesLive, {0}) & 0xFF) == 0) return;
  // While free roam loads the list is still empty, and sub_828AF780 finds an
  // empty list all revealed.
  const auto [activities, before] = CountRevealed(manager);
  if (activities == 0) return;
  if ((pinyon_shift::mod::CallGuest(kAllRevealed, {manager}) & 0xFF) != 0) {
    if (logged_owned != manager) {
      logged_owned = manager;
      pinyon_shift::diagnostics::RecordEvent(
          "dlc.treasure_map", {{"action", "owned"},
                               {"activities", fmt::format("{}", activities)},
                               {"revealed", fmt::format("{}", before)}});
    }
    return;
  }
  pinyon_shift::mod::CallGuest(kRevealAll, {manager});
  const uint32_t after = CountRevealed(manager).second;
  const bool owned = (pinyon_shift::mod::CallGuest(kAllRevealed, {manager}) & 0xFF) != 0;
  logged_owned = owned ? manager : 0;
  pinyon_shift::diagnostics::RecordEvent(
      "dlc.treasure_map", {{"action", "revealed"},
                           {"activities", fmt::format("{}", activities)},
                           {"revealed_before", fmt::format("{}", before)},
                           {"revealed_after", fmt::format("{}", after)},
                           {"owned", owned ? "1" : "0"}});
}

}  // namespace

namespace pinyon_shift::dlc {

bool GameModeReady() {
  // The world as sub_828BC9D8 reaches it ([[[0x832DF024] + 4] + 4]), and the
  // game mode object at +124 whose +56 sub_824878D0 returns.
  constexpr uint32_t kWorldGameMode = 124;
  constexpr uint32_t kGameModeValue = 56;
  const uint32_t holder = LoadPointer(kGameHolder, kHolderHandle + 4);
  const uint32_t handle = holder ? LoadPointer(holder + kHolderHandle, 8) : 0;
  const uint32_t world = handle ? LoadPointer(handle + 4, kWorldGameMode + 4) : 0;
  return world && LoadPointer(world + kWorldGameMode, kGameModeValue + 4) != 0;
}

void UpdateTreasureMap() {
  static uint32_t frames = 0;
  if (!REXCVAR_GET(pinyon_shift_dlc_treasure_map)) return;
  if (++frames < 30) return;
  frames = 0;
  if (g_queued.exchange(true, std::memory_order_acq_rel)) return;
  pinyon_shift::mod::EnqueueHostGuestTask([] {
    ApplyTreasureMap();
    g_queued.store(false, std::memory_order_release);
  });
}

}  // namespace pinyon_shift::dlc
