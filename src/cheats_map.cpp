#include "cheats_map.h"
#include "fh1_guest_address.h"

#include <algorithm>
#include <atomic>
#include <bit>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <mutex>
#include <optional>
#include <string>
#include <unordered_set>

#include <fmt/format.h>

#include <rex/cvar.h>
#include <rex/memory.h>
#include <rex/system/kernel_state.h>
#include <rex/system/xmemory.h>

#include "cheats.h"
#include "cheats_travel.h"
#include "dlc_treasure_map.h"
#include "mod/mod_host.h"
#include "pinyon_shift_diagnostics.h"

REXCVAR_DEFINE_BOOL(cheat_show_collectibles, false, "Cheats",
                    "Show the discount signs and barn finds not yet found on the map and "
                    "minimap, with the title's own markers (found ones keep their collected "
                    "marker)")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

REXCVAR_DEFINE_STRING(cheat_gps_destination, "", "Cheats",
                      "Set a GPS destination once in free roam as x,y,z in world metres; "
                      "an empty string leaves the route alone")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_STRING(cheat_saved_destination, "", "Cheats",
                      "Saved map destination as x,y,z in world metres, for the trainer's GPS action")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_STRING(cheat_teleport_destination, "", "Cheats",
                      "Travel once to the nearest road at x,y,z in world metres. Open the map "
                      "first; the request expires after 10 seconds")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

// How the title marks its collectibles (NP-8.6, found with the NP-8.4
// method). Discount signs are "flyers" in the code: GameModes\Colorado\
// Flyers.xml lists flyer_001 to flyer_100 as ActivityFlyers, placed by the
// gameplay objects of the same name in the track's GameObjs.xml; the barn
// finds are the nine ActivityBarnFind entries of GameModes\Colorado\
// barnfinds.xml, placed by their TriggerZone objects. Each activity makes two
// map entities (sub_828E9EC0) with the activity_type tags the map profiles
// (media\ui\MapProfileFullscreen.xml, MapProfileMinimap.xml) draw: "flyer" and
// "flyer_collected", "barnfind" and "barnfind_collected". The found state is
// the activity's record in the profile's class-serialised game state
// (CFlyerState, CBarnFindState, looked up by the activity's name).
//
// The title draws a found sign's collected marker (a grey dot) and a found
// barn find's (a dark barn) itself, but an unfound one's marker (a pink dot, a
// tan barn) only once it is "revealed": its Treasure Map (a token purchase
// that "reveals the locations of every Discount Sign" and a barn find's exact
// location) calls sub_828AF6F8 on the activity manager, which runs each
// discount sign, barn find, speed camera, average speed zone and gas
// station's reveal (vtable +72). That also sets the activity's revealed byte
// (+8) and its saved record's (+40), so it is permanent. This cheat puts the
// same unfound markers on the map through the title's own entity calls
// without touching either flag, and takes the ones it added off again when it
// is turned off. The map's own FILTER (Discount Signs, Barn Finds) still
// applies to them. A barn find that has not spawned yet (no rumour) gets no
// marker, as with the Treasure Map: there is nothing to find there yet. The
// reveal's other three types (speed cameras, average speed zones, gas
// stations) are left to the title: a mid-career save already has all 22, 9
// and 10 of them revealed, so how they come to be is not traced.
namespace {

// The world's component list, as sub_825F6FB0 reaches it:
// [[[0x832DF024] + 4] + 76], an array indexed by a component type's index.
constexpr uint32_t kWorldHolder = FH1_ADDR(0x832DF024u);
constexpr uint32_t kHolderHandle = 4;
constexpr uint32_t kHandleComponents = 76;
// The activity manager's component index (as sub_828AF6F8's callers, e.g.
// sub_82560B80, look it up); the manager holds its activities as a vector of
// pointers at +4 (begin) and +8 (end).
constexpr uint32_t kActivityManagerIndex = FH1_ADDR(0x832FEE8Cu);
constexpr uint32_t kManagerBegin = 4;
constexpr uint32_t kManagerEnd = 8;

constexpr uint32_t kActivityRevealed = 8;  // u8, set by the reveal (vtable +72)
constexpr uint32_t kActivityName = 16;     // MSVC std::string (inline under 16 bytes)
// A map entity handle (constructor sub_828E6028): the entity at +4, whose
// byte at +52 is set while it is on the map.
constexpr uint32_t kHandleEntity = 4;
constexpr uint32_t kEntityOnMap = 52;

// CActivityFlyers (vtable 0x82078DE4, set up by sub_828C3460).
constexpr uint32_t kFlyerVtable = FH1_ADDR(0x82078DE4u);
constexpr uint32_t kFlyerMarker = 56;       // handle, tag "flyer"
constexpr uint32_t kFlyerFoundMarker = 96;  // handle, tag "flyer_collected"
constexpr uint32_t kFlyerObject = 136;      // gameplay object; float4 position at +112
constexpr uint32_t kFlyerSmashed = 140;     // u8, set by sub_828C0C80
constexpr uint32_t kFlyerState = 148;       // CFlyerState record
constexpr uint32_t kFlyerStateSmashed = 44;

// CActivityBarnFind (vtable 0x82078B5C, set up by sub_828B99C8).
constexpr uint32_t kBarnFindVtable = FH1_ADDR(0x82078B5Cu);
constexpr uint32_t kBarnFindDiscovered = 44;    // u8, set on discovery (sub_828B9448)
constexpr uint32_t kBarnFindPosition = 112;     // float4
constexpr uint32_t kBarnFindMarker = 320;       // handle, tag "barnfind"
constexpr uint32_t kBarnFindFoundMarker = 360;  // handle, tag "barnfind_collected"
constexpr uint32_t kBarnFindState = 424;        // CBarnFindState record
constexpr uint32_t kBarnFindCollected = 513;    // u8, the record's +45
constexpr uint32_t kBarnFindStateDiscovered = 44;
// The record's status: 3 before the barn find spawns, 4 while its spawn is
// pending (sub_828BC5E0), 5 once spawned and its rumour runs (sub_828BC658;
// only then can it be discovered), 1 when discovered (sub_828B9BF8) and 0
// once collected (sub_828BC3B0).
constexpr uint32_t kBarnFindStateStatus = 56;
constexpr uint32_t kBarnFindNotSpawned = 3;
constexpr uint32_t kBarnFindSpawnPending = 4;

// sub_828BC9D8: whether free-roam collectibles are live (not during the
// first-time career, and in free roam); the flyers' reveal checks it.
constexpr uint32_t kCollectiblesLive = FH1_ADDR(0x828BC9D8u);
// sub_828E3580: puts a handle's entity on the map when it is not (vtable +12
// of the handle, as the reveal uses it); sub_828E4F58 takes it off.
constexpr uint32_t kMarkerShow = FH1_ADDR(0x828E3580u);
constexpr uint32_t kMarkerRemove = FH1_ADDR(0x828E4F58u);
// sub_828A5BF8(barn find, show): the barn find's exact-location marker on or
// off, and its collected marker once found.
constexpr uint32_t kBarnFindShowLocation = FH1_ADDR(0x828A5BF8u);

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

float LoadF32(uint32_t address) { return std::bit_cast<float>(Load32(address)); }

void Store32(uint32_t address, uint32_t value) {
  auto* base = rex::system::kernel_state()->memory()->virtual_membase();
  *rex::memory::GuestPtr<rex::be_u32*>(base, address) = value;
}

// A pointer field, 0 unless it and `size` bytes behind it are readable.
uint32_t LoadPointer(uint32_t address, uint32_t size) {
  if (!Readable(address, 4)) return 0;
  const uint32_t value = Load32(address);
  return Readable(value, size) ? value : 0;
}

std::string ActivityName(uint32_t activity) {
  const uint32_t capacity = Load32(activity + kActivityName + 20);
  const uint32_t length = std::min<uint32_t>(Load32(activity + kActivityName + 16), 64);
  const uint32_t text =
      capacity >= 16 ? LoadPointer(activity + kActivityName, length + 1) : activity + kActivityName;
  if (text == 0 || !Readable(text, length)) return {};
  std::string name;
  for (uint32_t i = 0; i < length; ++i) name.push_back(char(Load8(text + i)));
  return name;
}

uint32_t ActivityManager() {
  const uint32_t holder = LoadPointer(kWorldHolder, kHolderHandle + 4);
  const uint32_t handle = holder ? LoadPointer(holder + kHolderHandle, kHandleComponents + 4) : 0;
  const uint32_t components = handle ? LoadPointer(handle + kHandleComponents, 4) : 0;
  const uint32_t array = components ? LoadPointer(components, 4) : 0;
  if (!array || !Readable(kActivityManagerIndex, 4)) return 0;
  const uint32_t index = Load32(kActivityManagerIndex);
  if (index > 4096) return 0;
  return LoadPointer(array + 4 * index, kManagerEnd + 4);
}

bool HasEntity(uint32_t handle) {
  return LoadPointer(handle + kHandleEntity, kEntityOnMap + 1) != 0;
}

bool EntityOnMap(uint32_t handle) {
  const uint32_t entity = LoadPointer(handle + kHandleEntity, kEntityOnMap + 1);
  return entity != 0 && Load8(entity + kEntityOnMap) != 0;
}

// One collectible as the pass sees it.
struct Collectible {
  bool flyer = false;
  bool found = false;
  bool revealed = false;
  uint32_t status = 0;  // a barn find's record status
  uint32_t marker = 0;        // the unfound marker's handle
  uint32_t found_marker = 0;  // the collected marker's handle
};

std::optional<Collectible> Inspect(uint32_t activity) {
  const uint32_t vtable = Load32(activity);
  Collectible item;
  item.revealed = Load8(activity + kActivityRevealed) != 0;
  if (vtable == kFlyerVtable) {
    const uint32_t state = LoadPointer(activity + kFlyerState, kFlyerStateSmashed + 1);
    item.flyer = true;
    item.found = Load8(activity + kFlyerSmashed) != 0 ||
                 (state && Load8(state + kFlyerStateSmashed) != 0);
    item.marker = activity + kFlyerMarker;
    item.found_marker = activity + kFlyerFoundMarker;
    return item;
  }
  if (vtable == kBarnFindVtable) {
    const uint32_t state = LoadPointer(activity + kBarnFindState, kBarnFindStateStatus + 4);
    item.status = state ? Load32(state + kBarnFindStateStatus) : 0;
    item.found = Load8(activity + kBarnFindDiscovered) != 0 ||
                 Load8(activity + kBarnFindCollected) != 0 ||
                 (state && Load8(state + kBarnFindStateDiscovered) != 0);
    item.marker = activity + kBarnFindMarker;
    item.found_marker = activity + kBarnFindFoundMarker;
    return item;
  }
  return std::nullopt;
}

struct Census {
  uint32_t flyers = 0, flyers_found = 0, barn_finds = 0, barn_finds_found = 0;
  bool operator==(const Census&) const = default;
};

// The marker handles this cheat put on the map (so turning it off takes only
// those away), for the activity list they belong to. Guest tasks only.
std::unordered_set<uint32_t> g_added;
uint32_t g_added_list = 0;

void LogCollectible(uint32_t activity, const Collectible& item) {
  const uint32_t object = item.flyer ? LoadPointer(activity + kFlyerObject, 128) : 0;
  const uint32_t position = item.flyer ? (object ? object + 112 : 0)
                                       : activity + kBarnFindPosition;
  pinyon_shift::diagnostics::RecordEvent(
      "cheat.collectible",
      {{"kind", item.flyer ? "discount_sign" : "barn_find"},
       {"name", ActivityName(activity)},
       {"x", position ? fmt::format("{:.1f}", LoadF32(position)) : ""},
       {"y", position ? fmt::format("{:.1f}", LoadF32(position + 4)) : ""},
       {"z", position ? fmt::format("{:.1f}", LoadF32(position + 8)) : ""},
       {"found", item.found ? "1" : "0"},
       {"status", item.flyer ? "" : fmt::format("{}", item.status)},
       {"revealed", item.revealed ? "1" : "0"},
       {"marker_on_map", EntityOnMap(item.marker) ? "1" : "0"},
       {"found_marker_on_map", EntityOnMap(item.found_marker) ? "1" : "0"}});
}

// One pass over the activities: `show` puts each unfound, unrevealed
// collectible's marker on the map, otherwise takes the ones this added off
// again. Each collectible is logged (cheat.collectible) after the pass when
// `log` is set or the totals changed since the last log (a load, a find).
void SyncMarkers(bool show, bool log) {
  static Census logged;
  const uint32_t manager = ActivityManager();
  if (manager == 0) return;
  const uint32_t begin = Load32(manager + kManagerBegin);
  const uint32_t end = Load32(manager + kManagerEnd);
  if (end < begin || (end - begin) % 4 != 0 || end - begin > 4 * 4096 ||
      !Readable(begin, end - begin)) {
    return;
  }
  if (begin != g_added_list) {
    g_added.clear();
    g_added_list = begin;
  }
  // Not while the game mode is missing: the query would read guest 0x38.
  const bool live = show && pinyon_shift::dlc::GameModeReady() &&
                    (pinyon_shift::mod::CallGuest(kCollectiblesLive, {0}) & 0xFF) != 0;
  Census census;
  uint32_t shown = 0, removed = 0;
  for (uint32_t slot = begin; slot < end; slot += 4) {
    const uint32_t activity = LoadPointer(slot, kBarnFindCollected + 1);
    if (activity == 0) continue;
    const auto item = Inspect(activity);
    if (!item) continue;
    (item->flyer ? census.flyers : census.barn_finds) += 1;
    (item->flyer ? census.flyers_found : census.barn_finds_found) += item->found ? 1 : 0;
    if (!HasEntity(item->marker)) continue;
    const bool on_map = EntityOnMap(item->marker);
    if (item->flyer) {
      // A revealed sign's marker is the title's to show.
      const bool eligible = !item->found && !item->revealed;
      if (show && live && eligible && !on_map) {
        pinyon_shift::mod::CallGuest(kMarkerShow, {item->marker});
        g_added.insert(item->marker);
        ++shown;
      } else if (!show && on_map && g_added.count(item->marker) && eligible) {
        pinyon_shift::mod::CallGuest(kMarkerRemove, {item->marker});
        ++removed;
      }
    } else {
      // As the title's own reveal (sub_828A78B0) decides it: only a spawned
      // barn find (status 5) has anything to find, and a found one already
      // has the title's collected marker.
      const bool eligible = !item->found && !item->revealed &&
                            item->status != kBarnFindNotSpawned &&
                            item->status != kBarnFindSpawnPending;
      if (show && live && eligible && !on_map) {
        pinyon_shift::mod::CallGuest(kBarnFindShowLocation, {activity, 1u});
        g_added.insert(item->marker);
        ++shown;
      } else if (!show && on_map && g_added.count(item->marker) && eligible) {
        pinyon_shift::mod::CallGuest(kBarnFindShowLocation, {activity, 0u});
        ++removed;
      }
    }
  }
  if (!show) g_added.clear();
  log = log || (census.flyers + census.barn_finds != 0 && !(census == logged));
  if (log) {
    logged = census;
    for (uint32_t slot = begin; slot < end; slot += 4) {
      const uint32_t activity = LoadPointer(slot, kBarnFindCollected + 1);
      if (activity == 0) continue;
      if (const auto item = Inspect(activity)) LogCollectible(activity, *item);
    }
  }
  if (log || shown || removed) {
    pinyon_shift::diagnostics::RecordEvent(
        "cheat.collectibles",
        {{"enabled", show ? "1" : "0"},
         {"live", live ? "1" : "0"},
         {"discount_signs", fmt::format("{}", census.flyers)},
         {"discount_signs_found", fmt::format("{}", census.flyers_found)},
         {"barn_finds", fmt::format("{}", census.barn_finds)},
         {"barn_finds_found", fmt::format("{}", census.barn_finds_found)},
         {"shown", fmt::format("{}", shown)},
         {"removed", fmt::format("{}", removed)}});
  }
}

}  // namespace

namespace pinyon_shift::cheats {

namespace {
std::mutex g_destination_mutex;
std::optional<Destination> g_map_destination;
std::atomic<bool> g_gps_queued{false};
std::atomic<bool> g_travel_queued{false};
std::mutex g_travel_mutex;
struct MapTravelRequest {
  uint32_t road = 0;
  uint32_t components = 0;
  std::chrono::steady_clock::time_point expires{};
  uint32_t armed_map = 0;
};
MapTravelRequest g_map_travel;
uint32_t g_observed_map = 0;
bool g_observed_enabled = false;
// The map whose last predicate call was admitted only by FAST TRAVEL ANYWHERE.
uint32_t g_overridden_map = 0;

uint32_t Components() {
  const uint32_t holder = LoadPointer(kWorldHolder, 8);
  const uint32_t handle = holder ? LoadPointer(holder + 4, 80) : 0;
  return handle ? LoadPointer(handle + 76, 4) : 0;
}

uint32_t Component(uint32_t components, uint32_t index_address, uint32_t size) {
  const uint32_t array = LoadPointer(components, 4);
  if (!array || !Readable(index_address, 4)) return 0;
  const uint32_t index = Load32(index_address);
  return index <= 4096 ? LoadPointer(array + 4 * index, size) : 0;
}

bool FreeRoam() {
  const uint32_t holder = LoadPointer(kWorldHolder, 8);
  const uint32_t handle = holder ? LoadPointer(holder + 4, 8) : 0;
  const uint32_t world = handle ? LoadPointer(handle + 4, 128) : 0;
  const uint32_t session = world ? LoadPointer(world + 124, 60) : 0;
  return session && Load32(session + 56) == 17;
}

std::optional<Destination> RoadPosition(uint32_t road) {
  if (!Readable(road, 20)) return {};
  const Destination point{LoadF32(road + 4), LoadF32(road + 8), LoadF32(road + 12)};
  return ValidDestination(point) ? std::optional(point) : std::nullopt;
}

void SetGpsDestination(const Destination& point) {
  if (!Enabled() || !FreeRoam()) {
    diagnostics::RecordEvent("cheat.gps", {{"result", "requires_free_roam"}});
    return;
  }
  const uint32_t components = mod::CallGuest(FH1_ADDR(0x825F6FB0u), {});
  // Both managers are required: the action otherwise silently skips its work.
  const uint32_t satnav = Component(components, FH1_ADDR(0x832FF054u), 766);
  if (!Component(components, FH1_ADDR(0x832FF090u), 4) || !satnav) {
    diagnostics::RecordEvent("cheat.gps", {{"result", "managers_unavailable"}});
    return;
  }
  if (Load8(satnav + 764)) {
    diagnostics::RecordEvent("cheat.gps", {{"result", "destination_locked"}});
    return;
  }
  auto* memory = rex::system::kernel_state()->memory();
  const uint32_t action = memory->SystemHeapAlloc(48, 16);
  if (!action) {
    diagnostics::RecordEvent("cheat.gps", {{"result", "allocation_failed"}});
    return;
  }
  std::memset(memory->TranslateVirtual(action), 0, 48);
  // CSetSatNavDestinationPos's execute reads only these descriptor fields.
  Store32(action + 28, components);
  for (uint32_t i = 0; i < 3; ++i) Store32(action + 32 + 4 * i, std::bit_cast<uint32_t>(point[i]));
  const bool accepted = (mod::CallGuest(FH1_ADDR(0x829423B0u), {action, 0, 0}) & 0xFFu) != 0;
  memory->SystemHeapFree(action);
  diagnostics::RecordEvent("cheat.gps", {{"result", accepted ? "accepted" : "rejected"},
      {"x", fmt::format("{}", point[0])}, {"y", fmt::format("{}", point[1])},
      {"z", fmt::format("{}", point[2])}});
}
}  // namespace

std::optional<Destination> MapDestination() {
  std::lock_guard lock(g_destination_mutex);
  return g_map_destination;
}

bool RequestGpsDestination(const Destination& point) {
  if (!Enabled() || !ValidDestination(point) || g_gps_queued.exchange(true)) return false;
  mod::EnqueueHostGuestTask([point] {
    SetGpsDestination(point);
    g_gps_queued.store(false);
  });
  return true;
}

bool RequestTeleportDestination(const Destination& point) {
  if (!Enabled() || !ValidDestination(point) || g_travel_queued.exchange(true)) return false;
  mod::EnqueueHostGuestTask([point] {
    const uint32_t components = Components();
    if (!Enabled() || !FreeRoam()) {
      g_travel_queued.store(false);
      diagnostics::RecordEvent("cheat.teleport", {{"result", "requires_free_roam"}});
      return;
    }
    // v4 routes this lookup through the GPS position manager instead.
    constexpr uint32_t kLookupIndex = fh1::kTitleUpdateV4 ? FH1_ADDR(0x832FF090u)
                                                         : FH1_ADDR(0x832FF094u);
    if (!Component(components, kLookupIndex, 4)) {
      g_travel_queued.store(false);
      diagnostics::RecordEvent("cheat.teleport", {{"result", "managers_unavailable"}});
      return;
    }
    auto* memory = rex::system::kernel_state()->memory();
    const uint32_t position = memory->SystemHeapAlloc(16, 16);
    if (!position) {
      g_travel_queued.store(false);
      diagnostics::RecordEvent("cheat.teleport", {{"result", "allocation_failed"}});
      return;
    }
    for (uint32_t i = 0; i < 3; ++i)
      Store32(position + 4 * i, std::bit_cast<uint32_t>(point[i]));
    Store32(position + 12, 0);
    // The native map lookup resolves a road graph point; r3 is unused.
    const uint32_t road = mod::CallGuest(FH1_ADDR(0x827FADE8u), {0, position});
    memory->SystemHeapFree(position);
    if (!RoadPosition(road)) {
      g_travel_queued.store(false);
      diagnostics::RecordEvent("cheat.teleport", {{"result", "road_unavailable"}});
      return;
    }
    {
      std::lock_guard lock(g_travel_mutex);
      g_map_travel = {road, components, std::chrono::steady_clock::now() + std::chrono::seconds(10)};
    }
    diagnostics::RecordEvent("cheat.teleport", {{"result", "waiting_for_map"},
        {"x", fmt::format("{}", point[0])}, {"y", fmt::format("{}", point[1])},
        {"z", fmt::format("{}", point[2])}});
  });
  return true;
}

void UpdateDestinations() {
  static bool reached_free_roam = false;
  reached_free_roam |= FreeRoam();
  {
    std::lock_guard lock(g_travel_mutex);
    if (g_map_travel.road && (!Enabled() || !FreeRoam() ||
                             std::chrono::steady_clock::now() > g_map_travel.expires ||
                             Components() != g_map_travel.components)) {
      diagnostics::RecordEvent("cheat.teleport", {{"result", "cancelled"}});
      g_map_travel = {};
      g_travel_queued.store(false);
    }
  }
  // Launch settings wait for the first free roam. Later requests in another
  // mode are consumed and rejected, never deferred until a race ends.
  if (!Enabled() || !reached_free_roam) return;
  const std::string travel = REXCVAR_GET(cheat_teleport_destination);
  if (!travel.empty() && pinyon_shift::dlc::GameModeReady()) {
    const auto point = ParseDestination(travel);
    if (!point || RequestTeleportDestination(*point)) {
      if (!point) diagnostics::RecordEvent("cheat.teleport", {{"result", "invalid_coordinates"}});
      rex::cvar::SetFlagByName("cheat_teleport_destination", "");
      TeleportDestinationApplied();
    }
  }
  const std::string text = REXCVAR_GET(cheat_gps_destination);
  if (text.empty()) return;
  // Wait for the mode at startup, then consume once. The guest task rejects
  // races instead of retaining a request until the next free-roam session.
  if (!pinyon_shift::dlc::GameModeReady()) return;
  const auto point = ParseDestination(text);
  if (point && !RequestGpsDestination(*point)) return;
  if (!point) diagnostics::RecordEvent("cheat.gps", {{"result", "invalid_coordinates"}});
  rex::cvar::SetFlagByName("cheat_gps_destination", "");
  GpsDestinationApplied();
}

bool AllowMapTravel(uint32_t map, bool title_enabled, bool title_admitted) {
  if (!Enabled()) return false;
  const bool readable = Readable(map, 580);
  std::lock_guard travel_lock(g_travel_mutex);
  g_overridden_map = 0;
  if (map != g_observed_map || title_enabled != g_observed_enabled) {
    g_observed_map = map;
    g_observed_enabled = title_enabled;
    diagnostics::RecordEvent("cheat.map", {{"map", fmt::format("{:08X}", map)},
        {"readable", readable ? "1" : "0"}, {"title_enabled", title_enabled ? "1" : "0"},
        {"free_roam", FreeRoam() ? "1" : "0"}});
  }
  if (!readable) return false;
  // v4 added three fields ahead of the map's nearest road-point pointer.
  constexpr uint32_t kRoadPoint = fh1::kTitleUpdateV4 ? 576 : 564;
  const auto requested = RoadPosition(g_map_travel.road);
  const bool custom = requested && g_map_travel.components == Components() &&
      title_enabled && FreeRoam();
  if (custom) Store32(map + kRoadPoint, g_map_travel.road);
  const auto point = custom ? requested : RoadPosition(Load32(map + kRoadPoint));
  if (!point) return false;
  {
    std::lock_guard lock(g_destination_mutex);
    g_map_destination = *point;
  }
  if (custom && g_map_travel.armed_map == map && Load8(map + 426)) {
    Store32(map + 444, 0);
    diagnostics::RecordEvent("cheat.teleport", {{"result", "native_map_handoff"},
        {"road_x", fmt::format("{}", (*point)[0])}, {"road_y", fmt::format("{}", (*point)[1])},
        {"road_z", fmt::format("{}", (*point)[2])}});
    g_map_travel = {};
    g_travel_queued.store(false);
  }
  if (!title_enabled || !FreeRoam() || !(custom || FastTravelAnywhere())) return false;
  // Only a destination the title refused takes the road fallback; an eligible
  // hovered marker keeps its own placement.
  if (!custom && !title_admitted) g_overridden_map = map;
  return true;
}

bool PrepareMapTravelInput(uint32_t map) {
  std::lock_guard lock(g_travel_mutex);
  constexpr uint32_t kRoadPoint = fh1::kTitleUpdateV4 ? 576 : 564;
  g_map_travel.armed_map = 0;
  if (!Enabled() || !FreeRoam() || !Readable(map, kRoadPoint + 4)) return false;
  if (g_map_travel.components == Components() && RoadPosition(g_map_travel.road)) {
    Store32(map + kRoadPoint, g_map_travel.road);
    auto* base = rex::system::kernel_state()->memory()->virtual_membase();
    *rex::memory::GuestPtr<uint8_t*>(base, map + 426) = 1;
    g_map_travel.armed_map = map;
    return true;
  }
  return false;
}

bool UseMapRoadFallback(uint32_t map, bool admitted) {
  std::lock_guard lock(g_travel_mutex);
  return admitted && Enabled() && map != 0 && map == g_overridden_map;
}

bool ShowCollectibles() { return Enabled() && REXCVAR_GET(cheat_show_collectibles); }

void UpdateCollectibleMarkers() {
  // Activities come and go with free roam (loads, events), so while the cheat
  // is on a pass runs twice a second; the markers it adds stay until a pass
  // with the cheat off. Each change of the setting logs every collectible.
  static std::atomic<bool> shown{false};
  static uint32_t frames = 0;
  const bool wanted = ShowCollectibles();
  const bool changed = wanted != shown.load(std::memory_order_relaxed);
  if (!wanted && !changed) return;
  if (!changed && ++frames < 30) return;
  frames = 0;
  shown.store(wanted, std::memory_order_relaxed);
  pinyon_shift::mod::EnqueueHostGuestTask([wanted, changed] { SyncMarkers(wanted, changed); });
}

}  // namespace pinyon_shift::cheats
