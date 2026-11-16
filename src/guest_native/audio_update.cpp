// Game audio logic at a lower rate (docs/NATIVE_REPLACEMENT_RESEARCH.md NR-1).
//
// CAudioThread (base 82BAF5C8) drains, once per rendered frame, a list of
// deferred calls the game thread posted (the list executor is base
// sub_82450160, v4 sub_8247F818). Each list entry holds a marshalling thunk,
// the object and a copy of the arguments; the thunk makes the virtual call.
// On the Steam Deck LCD 98 % of the thread's time is inside four of them:
//
// - base sub_82BB9CD8 (v4 sub_82C78718): vtable +88 with the frame time in
//   f1 and a block of car state, the car audio model update (base
//   sub_82BC8410, v4 sub_82C86D38), one call per car; 58 %;
// - base sub_8249BE98 (v4 sub_82508890): vtable +44 with the frame time and
//   a flag, the audio engine update (base sub_824B7EE0, v4 sub_825253D0);
//   19 %;
// - base sub_8249BFC8 (v4 sub_825089C0): vtable +52 without a time (base
//   sub_824A5F10, v4 sub_82512C38); 19 %;
// - base sub_8249C130 (v4 sub_82508B40): vtable +64 (base sub_824A2918, v4
//   sub_8250F3F0); 5 %.
//
// At 60 fps these run twice as often as on the console's 30 fps.
// pinyon_shift_audio_update_interval N > 1 (2 by default) runs each of them
// on one call in up to N for each object and skips the others, as far as the
// frame time leaves them at 30 Hz or more (so not at all at 30 fps); the timed ones get the skipped
// calls' time added to their own, so the models' smoothing and timers keep
// their speed. The thunks are generic (any object's slot), so a call is
// skipped only when its object's vtable slot is the update named above; any
// other call through the same thunk, a one-off event, always runs. The
// engine update also runs whenever its flag differs from the last run's.
// pinyon_shift_audio_update_mask picks the calls (bit 0 car models, 1 engine
// update, 2 the +52 call, 3 the +64 call).

#include <array>
#include <bit>
#include <cstdint>
#include <cstring>

#include <rex/cvar.h>
#include <rex/ppc/context.h>
#include <rex/ppc/func.h>
#include <rex/system/xmemory.h>

#include "fh1_guest_address.h"
#include "guest_native/guest_native.h"

REXCVAR_DEFINE_UINT32(pinyon_shift_audio_update_interval, 2, "Pinyon Shift",
                      "Run the game's per-frame audio updates (car audio models, the audio "
                      "engine update and two others) on up to one frame in N, carrying the "
                      "skipped frames' time, and only as far as they stay at 30 Hz or more "
                      "(NR-1; 1 = every frame)")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_UINT32(pinyon_shift_audio_update_mask, 0xF, "Pinyon Shift",
                      "Which audio updates pinyon_shift_audio_update_interval slows: bit 0 car "
                      "audio models, 1 audio engine update, 2 the +52 update, 3 the +64 update")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

namespace pinyon_shift::guest_native {
namespace {

constexpr bool kV4 = pinyon_shift::fh1::kTitleUpdateV4;

uint8_t* Host(uint8_t* base, uint32_t address) {
  return base + address + rex::memory::detail::PhysicalHostOffset(address);
}
uint32_t Load32(uint8_t* base, uint32_t address) {
  uint32_t value;
  std::memcpy(&value, Host(base, address), sizeof(value));
  return std::byteswap(value);
}
float LoadF32(uint8_t* base, uint32_t address) {
  return std::bit_cast<float>(Load32(base, address));
}
void StoreF32(uint8_t* base, uint32_t address, float value) {
  const uint32_t bits = std::byteswap(std::bit_cast<uint32_t>(value));
  std::memcpy(Host(base, address), &bits, sizeof(bits));
}

struct Command {
  uint32_t slot_offset;  // vtable offset the thunk calls
  uint32_t target;       // the update that slot holds
  bool timed;            // payload +4 holds the frame time
  bool flagged;          // payload +8 holds a flag byte
};
constexpr std::array<Command, 4> kCommands = {{
    {88, kV4 ? 0x82C86D38u : 0x82BC8410u, true, false},
    {44, kV4 ? 0x825253D0u : 0x824B7EE0u, true, true},
    {52, kV4 ? 0x82512C38u : 0x824A5F10u, false, false},
    {64, kV4 ? 0x8250F3F0u : 0x824A2918u, false, false},
}};

// Only CAudioThread executes the lists.
struct Entry {
  uint32_t object = 0;
  uint32_t command = 0;
  uint32_t skipped = 0;
  float carried = 0.0f;
  uint8_t flag = 0;
};
constexpr size_t kMaxEntries = 64;
struct State {
  std::array<Entry, kMaxEntries> entries{};
  size_t count = 0;
  uint32_t carrying = 0;  // entries with time carried
  float frame_time = 0.0f;  // the last frame time a timed update was given
};
State state;

// Calls to run one in, so that the updates keep at least the console's
// 30 Hz: 2 from about 57 fps, 1 (every call) below that or before a frame
// time was seen; never above the cvar.
uint32_t Interval() {
  const uint32_t limit = REXCVAR_GET(pinyon_shift_audio_update_interval);
  if (limit <= 1 || state.frame_time <= 0.0f) return 1;
  const uint32_t fit = uint32_t((1.0f / 30.0f) / state.frame_time + 0.1f);
  return fit < 1 ? 1 : (fit < limit ? fit : limit);
}

Entry* Find(uint32_t command, uint32_t object, bool insert) {
  for (size_t i = 0; i < state.count; ++i) {
    Entry& e = state.entries[i];
    if (e.object == object && e.command == command) return &e;
  }
  if (!insert || state.count == kMaxEntries) return nullptr;
  Entry& e = state.entries[state.count++];
  e = Entry{};
  e.object = object;
  e.command = command;
  e.skipped = ~0u;  // the first call runs
  return &e;
}

void Run(Entry& e, const Command& c, PPCContext& ctx, uint8_t* base) {
  if (c.timed && e.carried != 0.0f) {
    const uint32_t time = ctx.r4.u32 + 4;
    StoreF32(base, time, LoadF32(base, time) + e.carried);
    --state.carrying;
  }
  e.carried = 0.0f;
  e.skipped = 0;
  if (c.flagged) e.flag = *Host(base, ctx.r4.u32 + 8);
}

template <size_t kIndex>
bool Gate(PPCContext& ctx, uint8_t* base) {
  const Command& c = kCommands[kIndex];
  const uint32_t object = ctx.r3.u32;
  if (object == 0) return false;
  const uint32_t table = Load32(base, object);
  if (table == 0 || Load32(base, table + c.slot_offset) != c.target) return false;
  if (c.timed) {
    const float dt = LoadF32(base, ctx.r4.u32 + 4);
    if (dt > 0.0f && dt < 1.0f) state.frame_time = dt;
  }
  const uint32_t interval = Interval();
  const bool on = interval > 1 && (REXCVAR_GET(pinyon_shift_audio_update_mask) >> kIndex) & 1;
  if (!on && state.carrying == 0) return false;
  Entry* e = Find(kIndex, object, on);
  if (e == nullptr) return false;
  const bool flag_changed = c.flagged && *Host(base, ctx.r4.u32 + 8) != e->flag;
  if (on && !flag_changed && e->skipped + 1 < interval) {
    ++e->skipped;
    if (c.timed) {
      if (e->carried == 0.0f) ++state.carrying;
      e->carried += LoadF32(base, ctx.r4.u32 + 4);
    }
    return true;  // this frame's call waits for the next run
  }
  Run(*e, c, ctx, base);
  return false;  // the original runs, with the carried time
}

bool Enabled() { return true; }  // Gate decides per call (the interval is hot)

size_t TimedWritten(const PPCContext& ctx, uint8_t* /*base*/, GuestRange* ranges) {
  ranges[0] = {ctx.r4.u32 + 4, 4};
  return 1;
}

#define PINYON_AUDIO_REPLACEMENT(var, index, label, base_address, v4_address, size, base_hash, \
                                 v4_hash, written_fn)                                       \
  Replacement var = {                                                                       \
      .name = label,                                                                        \
      .guest_address = kV4 ? v4_address : base_address,                                     \
      .guest_code_size = size,                                                              \
      .guest_code_fnv1a = kV4 ? v4_hash : base_hash,                                        \
      .returns = kReturnNone,                                                               \
      .enabled = Enabled,                                                                   \
      .native = Gate<index>,                                                                \
      .written = written_fn,                                                                \
  };

PINYON_AUDIO_REPLACEMENT(car_models_replacement, 0, "audio.update_rate.car_models", 0x82BB9CD8u,
                         0x82C78718u, 96, 0x3189C31701CC9FE7ull, 0x4FA413469884AAA1ull,
                         TimedWritten)
PINYON_AUDIO_REPLACEMENT(engine_replacement, 1, "audio.update_rate.engine", 0x8249BE98u,
                         0x82508890u, 24, 0x11094E4E9A208668ull, 0x11094E4E9A208668ull,
                         TimedWritten)
PINYON_AUDIO_REPLACEMENT(slot52_replacement, 2, "audio.update_rate.slot52", 0x8249BFC8u,
                         0x825089C0u, 96, 0x8E830442D5AFFDE6ull, 0xE8106FD9601DB107ull, nullptr)
PINYON_AUDIO_REPLACEMENT(slot64_replacement, 3, "audio.update_rate.slot64", 0x8249C130u,
                         0x82508B40u, 96, 0x678698BDB91DBCBCull, 0xA5A2D8350BBD4F32ull, nullptr)

#undef PINYON_AUDIO_REPLACEMENT

}  // namespace
}  // namespace pinyon_shift::guest_native

PINYON_GUEST_NATIVE(82BB9CD8, 82C78718, ::pinyon_shift::guest_native::car_models_replacement)
PINYON_GUEST_NATIVE(8249BE98, 82508890, ::pinyon_shift::guest_native::engine_replacement)
PINYON_GUEST_NATIVE(8249BFC8, 825089C0, ::pinyon_shift::guest_native::slot52_replacement)
PINYON_GUEST_NATIVE(8249C130, 82508B40, ::pinyon_shift::guest_native::slot64_replacement)
