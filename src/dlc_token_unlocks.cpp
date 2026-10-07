#include "dlc_token_unlocks.h"

#include <atomic>
#include <cstring>

#include <fmt/format.h>

#include <rex/cvar.h>
#include <rex/memory.h>
#include <rex/system/kernel_state.h>

#include "dlc_treasure_map.h"
#include "fh1_guest_address.h"
#include "mod/mod_host.h"
#include "pinyon_shift_diagnostics.h"
#include "save/profile_body.h"

// On by default, like the Treasure Map: the purchase can no longer be made.
REXCVAR_DEFINE_BOOL(pinyon_shift_dlc_fast_travel_anywhere, true, "Pinyon Shift",
                    "Own the Fast Travel Anywhere unlock (title update v4): fast travel from the "
                    "map to any road, as buying it did. Saved with the profile; turning it off "
                    "later does not take it away")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

// v4 sold Fast Travel Anywhere in its in-game marketplace for Tokens (a
// CVIPFastTravelConsumeAssetTransaction confirmed by Turn 10's token service,
// now gone). The map's Y offers it while the profile value tree lacks
// Main/FastTravelAnywhere = true; sub_826E94B8 reads that path. The purchase
// completion, sub_825D5C00 (r4 the result, 0 for success), stores it:
//   profile = sub_82915BE0([0x833F4A80])
//   value   = sub_82CC7248(&value, 1)            (a bool value)
//   tree    = profile->vtable[88](profile)
//   sub_8255E4D0(tree, "Main/FastTravelAnywhere", &value)
//   sub_82CC6A30(&value)                         (destroys it)
// and then notifies the UI. The host performs the same store, without the
// notification; the next save keeps it. The base disc has none of this.
namespace {

constexpr uint32_t kProfileHolder = 0x833F4A80u;
constexpr uint32_t kGetProfile = 0x82915BE0u;
constexpr uint32_t kMakeBool = 0x82CC7248u;
constexpr uint32_t kSetPath = 0x8255E4D0u;
constexpr uint32_t kDestroyValue = 0x82CC6A30u;
constexpr uint32_t kTreeMethod = 88;
constexpr uint32_t kPathString = 0x8201949Cu;  // "Main/FastTravelAnywhere"
constexpr uint32_t kValueBytes = 64;

std::atomic<bool> g_queued{false};
uint32_t g_granted_profile = 0;

uint32_t Load32(uint32_t address) {
  auto* base = rex::system::kernel_state()->memory()->virtual_membase();
  return static_cast<uint32_t>(*rex::memory::GuestPtr<rex::be_u32*>(base, address));
}

bool Readable(uint32_t address, uint32_t size) {
  if (address == 0 || address + size - 1u < address) return false;
  auto* memory = rex::system::kernel_state()->memory();
  auto* heap = memory->LookupHeap(address);
  return heap && heap->QueryRangeAccess(address, address + size - 1u) !=
                     rex::memory::PageAccess::kNoAccess &&
         rex::memory::IsHostReadable(memory->TranslateVirtual(address)) &&
         rex::memory::IsHostReadable(memory->TranslateVirtual(address + size - 1u));
}

// On the title's main thread, once per loaded profile, in free roam.
void GrantFastTravelAnywhere() {
  if (!pinyon_shift::dlc::GameModeReady() || !Readable(kProfileHolder, 4)) return;
  const uint32_t holder = Load32(kProfileHolder);
  if (!holder) return;
  const uint32_t profile = pinyon_shift::mod::CallGuest(kGetProfile, {holder});
  if (!profile || profile == g_granted_profile || !Readable(profile, 4)) return;
  const uint32_t vtable = Load32(profile);
  if (!Readable(vtable + kTreeMethod, 4)) return;
  const uint32_t tree = pinyon_shift::mod::CallGuest(Load32(vtable + kTreeMethod), {profile});
  if (!tree) return;
  auto* memory = rex::system::kernel_state()->memory();
  const uint32_t value = memory->SystemHeapAlloc(kValueBytes, 16);
  if (!value) return;
  std::memset(memory->TranslateVirtual(value), 0, kValueBytes);
  pinyon_shift::mod::CallGuest(kMakeBool, {value, 1});
  pinyon_shift::mod::CallGuest(kSetPath, {tree, kPathString, value});
  pinyon_shift::mod::CallGuest(kDestroyValue, {value});
  memory->SystemHeapFree(value);
  g_granted_profile = profile;
  pinyon_shift::diagnostics::RecordEvent("dlc.fast_travel_anywhere",
                                         {{"action", "granted"}, {"profile", fmt::format("{:08X}", profile)}});
}

}  // namespace

namespace pinyon_shift::dlc {

void UpdateTokenUnlocks() {
  if constexpr (!fh1::kTitleUpdateV4) return;
  static uint32_t frames = 0;
  if (!REXCVAR_GET(pinyon_shift_dlc_fast_travel_anywhere)) return;
  if (++frames < 60) return;
  frames = 0;
  if (g_queued.exchange(true, std::memory_order_acq_rel)) return;
  mod::EnqueueHostGuestTask([] {
    GrantFastTravelAnywhere();
    g_queued.store(false, std::memory_order_release);
  });
}

void GrantProfileUnlocks(uint8_t* body, size_t size) {
  if (!body || !REXCVAR_GET(pinyon_shift_dlc_fast_travel_anywhere)) return;
  // Other secure files pass through here too; only the profile has Main.
  if (!save::FindProfileField(body, size, "Main/Credits")) return;
  // A profile the v4 title has already saved carries the field; grant it
  // before the title reads it. A base save gains it in free roam instead.
  const auto field = save::FindProfileField(body, size, "Main/FastTravelAnywhere");
  if (!field || field->type != save::FieldType::kBool || field->size == 0 ||
      field->offset + field->size > size) {
    return;
  }
  uint8_t* value = body + field->offset;
  if (value[field->size - 1]) return;
  std::memset(value, 0, field->size);
  value[field->size - 1] = 1;
  diagnostics::RecordEvent("dlc.fast_travel_anywhere", {{"action", "granted_at_load"}});
}

}  // namespace pinyon_shift::dlc
