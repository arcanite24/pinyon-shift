// D3D source census (docs/D3D_RENDERER_RESEARCH.md DL-0.1, DL-0.2). See
// d3d_census.h. The device field offsets below are our reading of the D3D
// runtime in the base executable (.local/backlog-research/
// d3d-renderer-2026-10-14/dl01-probe.md): the census checks them, it does not
// depend on them for anything but its own counts.

#include "native_renderer/d3d_census.h"

#if defined(_WIN32)
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

#include "fh1_guest_address.h"
#include "pinyon_shift_diagnostics.h"

#include <algorithm>
#include <atomic>
#include <cstdint>
#include <cstring>
#include <iterator>
#include <mutex>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

#include <fmt/format.h>
#include <xxhash.h>

#include <rex/cvar.h>
#include <rex/logging/macros.h>
#include <rex/perf/counter.h>
#include <rex/ppc/context.h>
#include <rex/ppc/func.h>
#include <rex/system/d3d_census.h>
#include <rex/system/kernel_state.h>
#include <rex/system/xmemory.h>
#include <rex/types.h>

REXCVAR_DEFINE_BOOL(pinyon_shift_d3d_census, false, "Pinyon Shift",
                    "Diagnostics (D3D_RENDERER_RESEARCH DL-0.1): count the title's D3D draw "
                    "calls by the buffer they write into, the device class's slots, the "
                    "display lists' runs, fixups and origins, and tag every decoded draw by "
                    "the path that wrote it; logs a window every "
                    "pinyon_shift_d3d_census_window frames. Observation only; base-disc build")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_UINT32(pinyon_shift_d3d_census_window, 600, "Pinyon Shift",
                      "Frames per pinyon_shift_d3d_census window")
    .range(1, 100000)
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_INT32(pinyon_shift_d3d_census_bracket_frame, -1, "Pinyon Shift",
                     "Diagnostics (DL-0.2): with pinyon_shift_d3d_census, log every switch of "
                     "the D3D device's buffer (end pointer, recording and tiling state, tiling "
                     "stream head) during this source frame, with the code on both sides of it "
                     "(-1: off)")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_UINT32(pinyon_shift_d3d_census_list_log, 16, "Pinyon Shift",
                      "Display lists logged per pinyon_shift_d3d_census window, most runs first")
    .range(0, 4096)
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_BOOL(pinyon_shift_d3d_census_lean, false, "Pinyon Shift",
                    "With pinyon_shift_d3d_census (DL-1.1), classify draws only: drop the "
                    "DL-0.2 device snapshots here and, in the decoder, the mark lookups inside "
                    "display lists and the per-class timing, so the census costs less while "
                    "gpu_d3d_census_skip_visible is measured")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_BOOL(pinyon_shift_d3d_census_hash_lists, true, "Pinyon Shift",
                    "With pinyon_shift_d3d_census, hash each display list's bytes at every run "
                    "to tell unchanged lists from lists changed by fixups or other writers")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

namespace pinyon_shift::native_renderer {
namespace {

namespace census = rex::system::d3d_census;

// --- The D3D device (our reading; offsets from the device pointer) ---
// +48 the last dword written, +52 the current buffer's end, +56 the point at
// which a writer closes the segment.
constexpr uint32_t kWritePointer = 48, kBufferEnd = 52, kSegmentLimit = 56;
// Bit 7: a command buffer is being recorded.
constexpr uint32_t kRecordFlags = 11068;
// Bit 5: the device drops what it writes (segment submit skips).
constexpr uint32_t kDropFlags = 11069;
// Non-zero while a tiling bracket is open (segments go to the tiling stream).
constexpr uint32_t kTilingState = 13600;
// The tiling stream's write position (8-byte indirect-buffer entries).
constexpr uint32_t kTilingStreamHead = 13772;
// The command buffer being recorded.
constexpr uint32_t kRecordingBuffer = 13920;
// The start of the segment being written.
constexpr uint32_t kSegmentStart = 15332;
// D3D's own indirect buffer address (second INDIRECT_BUFFER producer).
constexpr uint32_t kD3dBufferAddress = 14192;
// --- A command buffer ---
constexpr uint32_t kListFlags = 108, kListChain = 116;

// The hooked draw entry points (main-xex.toml PinyonShiftD3dCensusDraw<n>;
// entry 5 shares the PERF-11 hook at its address).
constexpr uint32_t kDrawEntries = 9;
constexpr uint32_t kDrawEntryAddress[kDrawEntries] = {
    0x82416380, 0x82415F68, 0x8240DC70, 0x82408B70, 0x82460998,
    0x8240F4D8, 0x829F7C70, 0x824610C0, 0x823FA0A8};
// D3D-internal (built-in shader) draws.
constexpr uint32_t kInternalDraws = 5;
constexpr uint32_t kInternalAddress[kInternalDraws] = {0x8240E130, 0x829E82D0, 0x829E8428,
                                                       0x829F0928, 0x829FEFB0};
// CD3D9GraphicsDevice slots with a census hook (vtable 0x821451EC).
constexpr uint32_t kSlots = 18;
constexpr uint32_t kSlotNumber[kSlots] = {12, 22, 23, 24, 25, 26, 30, 31, 38,
                                          39, 40, 41, 42, 43, 44, 48, 65, 66};
constexpr uint32_t kSlotAddress[kSlots] = {
    0x8240BA48, 0x82415C88, 0x82444B18, 0x823FA198, 0x82418F50, 0x82417B90,
    0x8244A450, 0x82415CA8, 0x824131B8, 0x823F5980, 0x82415CE0, 0x82412DD8,
    0x8246EF98, 0x82C27340, 0x82C273B0, 0x82C27568, 0x82C27440, 0x823F74B0};
// Slots whose wrappers reach a draw entry point.
constexpr bool kSlotIsDraw[kSlots] = {false, false, false, false, false, false,
                                      false, false, true,  true,  true,  true,
                                      true,  true,  true,  true,  true,  true};
// Candidates for BeginCommandBuffer, EndCommandBuffer, BeginTiling and
// EndTiling (guesses: the stores to the recording buffer and the tiling
// state); DL-0.2 confirms or rejects them from the buffer switches.
constexpr uint32_t kBrackets = 4;
constexpr uint32_t kBracketAddress[kBrackets] = {0x82468C40, 0x823EA3E0, 0x823EB3D0,
                                                 0x82469290};
constexpr const char* kBracketName[kBrackets] = {"begin_cb?", "end_cb?", "begin_tiling?",
                                                 "end_tiling?"};
constexpr uint32_t kTilingCallback = 0x829F5948;

// Guest code ranges for the IB write watch's writer classes.
struct WriterRange {
  uint32_t begin, end;
  uint8_t writer_class;
};
constexpr WriterRange kWriterRanges[] = {
    // Fixup setters and record lookup, the dispatcher, the static-fixup
    // loaders and the engine's dynamic-fixup helpers.
    {0x8247B2E0, 0x8247B688, census::kWriterFixup},
    {0x829EB348, 0x829EB900, census::kWriterFixup},
    {0x82C58DA8, 0x82C58E84, census::kWriterFixup},
    {0x82C592F0, 0x82C59350, census::kWriterFixup},
    {0x82C5A7B0, 0x82C5A9B0, census::kWriterFixup},
    {0x82C5ABA0, 0x82C5AD90, census::kWriterFixup},
    {0x82450440, 0x82450508, census::kWriterFixup},
    {0x8245BBF0, 0x8245BFE0, census::kWriterFixup},
    {0x8245CA88, 0x8245CBB0, census::kWriterFixup},
    {0x8246ED00, 0x8246EED0, census::kWriterFixup},
    // The buffered file read.
    {0x82C76A90, 0x82C76C38, census::kWriterStream},
    // The clone copy and its caller.
    {0x829EB0B8, 0x829EB348, census::kWriterClone},
};

// Where a call's device writes.
enum Target : uint8_t {
  kTargetRing = 0,
  kTargetRecording,
  kTargetTiling,
  kTargetRecordingTiling,
  kTargetCount,
};
constexpr const char* kTargetName[kTargetCount] = {"ring", "rec", "tiling", "rec+tiling"};

// Observation sites for the device's buffer switches (DL-0.2).
enum Site : uint8_t {
  kSiteDraw0 = 0,
  kSiteInternal0 = kSiteDraw0 + kDrawEntries,
  kSiteRun = kSiteInternal0 + kInternalDraws,
  kSiteAsync,
  kSiteD3dIb,
  kSiteSubmit,
  kSiteClose,
  kSiteBracket0,
  kSiteInsertCallback = kSiteBracket0 + kBrackets,
  kSiteCount,
};

std::string SiteName(uint32_t site) {
  if (site < kSiteInternal0) return fmt::format("draw{}:{:08X}", site, kDrawEntryAddress[site]);
  if (site < kSiteRun) {
    return fmt::format("internal:{:08X}", kInternalAddress[site - kSiteInternal0]);
  }
  switch (site) {
    case kSiteRun:
      return "run:82416A00";
    case kSiteAsync:
      return "async:829EC928";
    case kSiteD3dIb:
      return "d3d_ib:8246FB98";
    case kSiteSubmit:
      return "submit:8240D070";
    case kSiteClose:
      return "close:8240CF68";
    case kSiteInsertCallback:
      return "insert_callback:823E67A8";
    default:
      break;
  }
  if (site >= kSiteBracket0 && site < kSiteBracket0 + kBrackets) {
    return fmt::format("{}:{:08X}", kBracketName[site - kSiteBracket0],
                       kBracketAddress[site - kSiteBracket0]);
  }
  return "?";
}

// Buffer-switch kinds (bits).
enum Change : uint32_t {
  kChangeEnd = 1,
  kChangeRecordOn = 2,
  kChangeRecordOff = 4,
  kChangeBuffer = 8,
  kChangeTilingOn = 16,
  kChangeTilingOff = 32,
  kChangeStreamHead = 64,
};

std::string ChangeNames(uint32_t changes) {
  std::string out;
  auto add = [&](uint32_t bit, const char* name) {
    if (changes & bit) {
      if (!out.empty()) out += '+';
      out += name;
    }
  };
  add(kChangeEnd, "end");
  add(kChangeRecordOn, "rec_on");
  add(kChangeRecordOff, "rec_off");
  add(kChangeBuffer, "rec_buffer");
  add(kChangeTilingOn, "tiling_on");
  add(kChangeTilingOff, "tiling_off");
  add(kChangeStreamHead, "stream_head");
  return out;
}

using Counter = std::atomic<uint64_t>;

struct Counters {
  Counter draw_calls[kDrawEntries][kTargetCount];
  Counter draw_nested[kDrawEntries];
  Counter draw_unmarked[kDrawEntries];
  Counter internal_calls[kInternalDraws][kTargetCount];
  Counter internal_nested[kInternalDraws];
  Counter slot_calls[kSlots];
  Counter runs[kTargetCount];
  Counter runs_null, runs_async_type, async_runs, d3d_ibs;
  Counter run_states[census::kListStateCount];
  // Fixups applied before a run: 0, 1, 2-3, 4-7, 8-15, 16 and more.
  Counter run_fixups[6];
  Counter run_dwords, run_entries;
  // [static][resource type]
  Counter fixups[2][16];
  Counter static_lookups, loads, stream_reads, stream_bytes, stream_physical_reads,
      stream_physical_bytes, clone_calls, clones;
  Counter segments[census::kSegmentModeCount], segment_bytes[census::kSegmentModeCount];
  Counter closes;
  Counter brackets[kBrackets];
  Counter callbacks, tiling_callbacks, tiling_callback_fires;
};
Counters counters;

uint64_t Take(Counter& counter) { return counter.exchange(0, std::memory_order_relaxed); }

std::atomic<bool> g_on{false};
std::atomic<bool> g_armed{false};
std::atomic<bool> g_lean{false};
std::atomic<uint32_t> g_armed_logs{0};
constexpr uint32_t kArmedLogLimit = 6000;

bool On() { return g_on.load(std::memory_order_relaxed); }

auto* Memory() { return rex::system::kernel_state()->memory(); }

bool GuestPointer(uint32_t address) { return address >= 0x10000u && address < 0xFFFF0000u; }

uint32_t Load32(uint32_t address) {
  return rex::byte_swap(*Memory()->template TranslateVirtual<uint32_t*>(address));
}
uint8_t Load8(uint32_t address) { return *Memory()->template TranslateVirtual<uint8_t*>(address); }

uint32_t Physical(uint32_t address) { return Memory()->GetPhysicalAddress(address); }

uint8_t TargetOf(uint32_t device) {
  const bool recording = (Load8(device + kRecordFlags) & 0x80) != 0;
  const bool tiling = Load32(device + kTilingState) != 0;
  return recording ? (tiling ? kTargetRecordingTiling : kTargetRecording)
                   : (tiling ? kTargetTiling : kTargetRing);
}

// Marks where the device's next packet goes as written by `source`.
bool MarkNext(uint32_t device, uint8_t source) {
  const uint32_t physical = Physical(Load32(device + kWritePointer) + 4);
  if (physical == UINT32_MAX) return false;
  census::MarkPacket(physical, source);
  return true;
}

// Calls still active on this thread, outermost first, by their entry stack
// pointer: a draw made inside another (a copying wrapper's draw, a built-in
// shader's rectangle) is attributed to the outermost.
struct Outer {
  uint32_t r1;
  uint8_t source;
};
thread_local Outer t_outers[4];
thread_local uint32_t t_outer_count = 0;
// The static-fixup lookup tail-calls the dispatcher with the same stack.
thread_local uint32_t t_static_r1 = 0;

void PopReturned(uint32_t r1) {
  while (t_outer_count && t_outers[t_outer_count - 1].r1 <= r1) --t_outer_count;
}

uint8_t EnterDraw(uint32_t r1, uint8_t own, bool* nested) {
  PopReturned(r1);
  *nested = t_outer_count != 0;
  const uint8_t source = *nested ? t_outers[0].source : own;
  if (t_outer_count < std::size(t_outers)) t_outers[t_outer_count++] = {r1, source};
  return source;
}

// --- DL-0.2: the device's buffer switches ---
struct DeviceState {
  uint32_t end, buffer, tiling, head, lr;
  uint8_t recording, site;
};
std::mutex g_device_mutex;
std::unordered_map<uint32_t, DeviceState> g_devices;
std::unordered_map<uint32_t, uint64_t> g_switches;  // prev site | site << 8 | changes << 16

void LogArmed(const std::string& line) {
  if (g_armed_logs.fetch_add(1, std::memory_order_relaxed) < kArmedLogLimit) {
    REXLOG_INFO("D3D census DL-0.2: {}", line);
  }
}

void Observe(uint32_t device, uint8_t site, uint32_t lr) {
  if (g_lean.load(std::memory_order_relaxed) || !GuestPointer(device)) return;
  DeviceState now{Load32(device + kBufferEnd), Load32(device + kRecordingBuffer),
                  Load32(device + kTilingState), Load32(device + kTilingStreamHead), lr,
                  uint8_t((Load8(device + kRecordFlags) & 0x80) ? 1 : 0), site};
  std::lock_guard<std::mutex> lock(g_device_mutex);
  auto [it, inserted] = g_devices.try_emplace(device, now);
  if (inserted) return;
  const DeviceState before = it->second;
  it->second = now;
  uint32_t changes = 0;
  if (now.end != before.end) changes |= kChangeEnd;
  if (now.recording && !before.recording) changes |= kChangeRecordOn;
  if (!now.recording && before.recording) changes |= kChangeRecordOff;
  if (now.buffer != before.buffer) changes |= kChangeBuffer;
  if (now.tiling && !before.tiling) changes |= kChangeTilingOn;
  if (!now.tiling && before.tiling) changes |= kChangeTilingOff;
  if (now.head != before.head && (now.tiling || before.tiling)) changes |= kChangeStreamHead;
  if (!changes) return;
  if (g_switches.size() < 4096 || g_switches.count(before.site | site << 8 | changes << 16)) {
    ++g_switches[before.site | uint32_t(site) << 8 | changes << 16];
  }
  if (g_armed.load(std::memory_order_relaxed)) {
    const uint32_t write = Load32(device + kWritePointer);
    LogArmed(fmt::format(
        "device {:08X} {} {} (lr {:08X}) -> {} (lr {:08X}): end {:08X} -> {:08X}, +48 "
        "{:08X} (physical {:08X}), now {}, recording buffer {:08X} -> {:08X}, tiling {:08X} "
        "-> {:08X}, stream head {:08X} -> {:08X}",
        device, ChangeNames(changes), SiteName(before.site), before.lr, SiteName(site), lr,
        before.end, now.end, write, Physical(write), kTargetName[TargetOf(device)],
        before.buffer, now.buffer, before.tiling, now.tiling, before.head, now.head));
  }
}

// --- Display lists ---
struct ListInfo {
  uint32_t first_frame = 0, last_frame = 0;
  uint64_t runs = 0, window_runs = 0, window_fixups = 0;
  uint32_t fixups_pending[16] = {};
  uint64_t states[census::kListStateCount] = {};
  uint64_t window_writes[census::kWriterClassCount] = {};
  uint64_t hash = 0;
  uint32_t dwords = 0, entries = 0, flags = 0, clone_source = 0;
  uint8_t origin = 0;
  bool seen_run = false;
};
std::mutex g_lists_mutex;
std::unordered_map<uint32_t, ListInfo> g_lists;

// NA-2.2 pass census: list runs by their owner, the guest functions that
// called the executor. The guest stack does not hold them (the generated
// code keeps LR in host locals), so they are read from the host stack: each
// return address there is mapped to the generated function containing it.
// The key is the executor's return address and its first two guest callers.
struct OwnerInfo {
  uint32_t lr = 0, owner = 0, owner_caller = 0, owner_caller2 = 0;
  uint64_t runs = 0, dwords = 0, fixups[16] = {};
  uint64_t states[census::kListStateCount] = {};
  uint32_t origins = 0;
  std::unordered_set<uint32_t> lists;
  census::ListDecoded decoded;
  // The order of the lists it runs: a hash of each frame's sequence, and how
  // many frames repeated the previous frame's sequence.
  uint32_t frame = 0;
  uint64_t sequence = 0, previous = 0, runs_this_frame = 0;
  uint64_t frames = 0, same_order = 0, run_count_changes = 0, previous_runs = 0;
};
std::unordered_map<uint64_t, OwnerInfo> g_owners;
std::unordered_map<uint32_t, uint64_t> g_list_owner;

#if defined(_WIN32)
// A generated function's body: the mapping's host pointer, or the target of
// the jump thunk it points to (as in hitch_sampler_win.cpp).
uintptr_t BodyStart(uintptr_t host) {
  const auto* code = reinterpret_cast<const uint8_t*>(host);
  for (int hops = 0; hops < 4; ++hops) {
    if (code[0] == 0xE9) {
      int32_t rel;
      std::memcpy(&rel, code + 1, 4);
      code = code + 5 + rel;
    } else if (code[0] == 0xFF && code[1] == 0x25) {
      int32_t rel;
      std::memcpy(&rel, code + 2, 4);
      code = *reinterpret_cast<const uint8_t* const*>(code + 6 + rel);
    } else {
      break;
    }
  }
  return reinterpret_cast<uintptr_t>(code);
}

// The guest function whose generated body contains `pc`, or 0.
uint32_t GuestFunctionAt(uintptr_t pc) {
  static const std::unordered_map<uintptr_t, uint32_t> bodies = [] {
    std::unordered_map<uintptr_t, uint32_t> out;
    for (size_t i = 0; PPCFuncMappings[i].guest != 0; ++i) {
      if (!PPCFuncMappings[i].host) continue;
      out.emplace(BodyStart(reinterpret_cast<uintptr_t>(PPCFuncMappings[i].host)),
                  uint32_t(PPCFuncMappings[i].guest));
    }
    return out;
  }();
  DWORD64 image_base = 0;
  const RUNTIME_FUNCTION* function = RtlLookupFunctionEntry(pc, &image_base, nullptr);
  if (!function) return 0;
  while (function->UnwindData & RUNTIME_FUNCTION_INDIRECT) {
    function = reinterpret_cast<const RUNTIME_FUNCTION*>(
        image_base + (function->UnwindData & ~RUNTIME_FUNCTION_INDIRECT));
  }
  const auto it = bodies.find(uintptr_t(image_base + function->BeginAddress));
  return it == bodies.end() ? 0 : it->second;
}
#endif

// The first `count` guest functions on the host stack above the executor
// (0x82416A00), innermost first; zeros where there are fewer.
void GuestCallers(uint32_t* out, int count) {
  for (int i = 0; i < count; ++i) out[i] = 0;
#if defined(_WIN32)
  void* pcs[32];
  const USHORT depth = RtlCaptureStackBackTrace(1, 32, pcs, nullptr);
  bool above = false;
  int found = 0;
  for (USHORT i = 0; i < depth && found < count; ++i) {
    const uint32_t guest = GuestFunctionAt(reinterpret_cast<uintptr_t>(pcs[i]));
    if (!guest) continue;
    if (!above) {
      above = guest == 0x82416A00u;
      if (above) continue;
      // The hook may run from a caller's frame if the executor was inlined.
      above = true;
    }
    out[found++] = guest;
  }
#endif
}

void CloseOwnerFrame(OwnerInfo& owner) {
  if (!owner.runs_this_frame) return;
  ++owner.frames;
  if (owner.sequence == owner.previous) ++owner.same_order;
  if (owner.runs_this_frame != owner.previous_runs) ++owner.run_count_changes;
  owner.previous = owner.sequence;
  owner.previous_runs = owner.runs_this_frame;
  owner.sequence = 0;
  owner.runs_this_frame = 0;
}
std::unordered_map<uint32_t, uint64_t> g_fixup_callers;
std::unordered_map<uint64_t, uint64_t> g_callbacks;  // callback << 32 | lr
uint64_t g_new_lists = 0;

// Physical pages a buffered file read wrote (512 MB / 4 KB).
std::atomic<uint64_t> g_stream_pages[(0x20000000u >> 12) / 64];

void MarkStreamPages(uint32_t physical, uint32_t bytes) {
  const uint32_t first = physical >> 12, last = (physical + bytes - 1) >> 12;
  for (uint32_t page = first; page <= last && page < (0x20000000u >> 12); ++page) {
    g_stream_pages[page / 64].fetch_or(uint64_t(1) << (page % 64), std::memory_order_relaxed);
  }
}

bool StreamPagesOverlap(uint32_t physical, uint32_t bytes) {
  if (!bytes) return false;
  const uint32_t first = physical >> 12, last = (physical + bytes - 1) >> 12;
  for (uint32_t page = first; page <= last && page < (0x20000000u >> 12); ++page) {
    if (g_stream_pages[page / 64].load(std::memory_order_relaxed) & (uint64_t(1) << (page % 64))) {
      return true;
    }
  }
  return false;
}

uint32_t FixupBucket(uint32_t fixups) {
  if (fixups == 0) return 0;
  if (fixups == 1) return 1;
  if (fixups < 4) return 2;
  if (fixups < 8) return 3;
  if (fixups < 16) return 4;
  return 5;
}

constexpr const char* kStateName[census::kListStateCount] = {
    "first", "unchanged", "fixup_only", "changed_no_fixup", "other_write"};

void OnRun(uint32_t r1, uint32_t device, uint32_t list, uint32_t lr) {
  Observe(device, kSiteRun, lr);
  PopReturned(r1);
  if (!GuestPointer(list)) {
    counters.runs_null.fetch_add(1, std::memory_order_relaxed);
    return;
  }
  if ((Load32(list) & 0xF) == 10) {
    // An asynchronous call: the async hook counts it.
    counters.runs_async_type.fetch_add(1, std::memory_order_relaxed);
    return;
  }
  counters.runs[TargetOf(device)].fetch_add(1, std::memory_order_relaxed);
  MarkNext(device, census::kSourceListRun);

  struct Range {
    uint32_t physical, bytes;
  };
  Range ranges[256];
  uint32_t count = 0, dwords = 0;
  const bool hashed = REXCVAR_GET(pinyon_shift_d3d_census_hash_lists);
  uint64_t hash = 0;
  uint32_t node = Load32(list + kListChain);
  for (uint32_t nodes = 0; GuestPointer(node) && nodes < 64 && count < std::size(ranges);
       ++nodes) {
    const uint32_t entries = std::min<uint32_t>(Load32(node + 4), 4096);
    for (uint32_t i = 0; i < entries && count < std::size(ranges); ++i) {
      const uint32_t size = Load32(node + 8 + 8 * i) & 0xFFFFFFu;
      const uint32_t physical = Load32(node + 12 + 8 * i) & 0x1FFFFFFFu;
      ranges[count++] = {physical, size * 4};
      dwords += size;
      if (hashed && size && size <= (1u << 20)) {
        hash = XXH3_64bits_withSeed(Memory()->template TranslatePhysical<const uint8_t*>(physical),
                                    size_t(size) * 4, hash);
      }
    }
    node = Load32(node);
  }
  counters.run_dwords.fetch_add(dwords, std::memory_order_relaxed);
  counters.run_entries.fetch_add(count, std::memory_order_relaxed);

  uint32_t writes[census::kWriterClassCount];
  census::TakeListWrites(list, writes);
  const uint32_t frame = census::Frame();
  uint8_t state, origin;
  uint32_t fixups = 0;
  {
    std::lock_guard<std::mutex> lock(g_lists_mutex);
    ListInfo& info = g_lists[list];
    const bool first = !info.seen_run;
    if (first) {
      ++g_new_lists;
      info.first_frame = frame;
      for (uint32_t i = 0; i < count; ++i) {
        if (StreamPagesOverlap(ranges[i].physical, ranges[i].bytes)) {
          info.origin |= census::kOriginStream;
          break;
        }
      }
    }
    uint32_t callers[3];
    GuestCallers(callers, 3);
    const uint64_t owner_key =
        (uint64_t(callers[0]) << 32 | callers[1]) * 0x9E3779B97F4A7C15ull ^ callers[2];
    OwnerInfo& owner = g_owners[owner_key];
    owner.lr = lr;
    owner.owner = callers[0];
    owner.owner_caller = callers[1];
    owner.owner_caller2 = callers[2];
    if (owner.frame != frame) {
      CloseOwnerFrame(owner);
      owner.frame = frame;
    }
    owner.sequence = (owner.sequence ^ list) * 0x100000001B3ull;
    ++owner.runs_this_frame;
    ++owner.runs;
    owner.dwords += dwords;
    owner.lists.insert(list);
    g_list_owner[list] = owner_key;
    for (uint32_t type = 0; type < 16; ++type) {
      owner.fixups[type] += info.fixups_pending[type];
    }
    for (uint32_t& pending : info.fixups_pending) {
      fixups += pending;
      pending = 0;
    }
    if (first) {
      state = census::kListFirstRun;
    } else if (hashed && hash == info.hash) {
      state = census::kListUnchanged;
    } else if (writes[census::kWriterOther]) {
      state = census::kListOtherWrite;
    } else if (fixups) {
      state = census::kListFixupOnly;
    } else {
      state = hashed ? census::kListChangedNoFixup : census::kListUnchanged;
    }
    info.hash = hash;
    info.seen_run = true;
    ++info.runs;
    ++info.window_runs;
    info.window_fixups += fixups;
    ++info.states[state];
    for (uint32_t i = 0; i < census::kWriterClassCount; ++i) info.window_writes[i] += writes[i];
    info.last_frame = frame;
    info.dwords = dwords;
    info.entries = count;
    info.flags = Load32(list + kListFlags);
    origin = info.origin;
    owner.origins |= origin;
    ++owner.states[state];
  }
  counters.run_states[state].fetch_add(1, std::memory_order_relaxed);
  counters.run_fixups[FixupBucket(fixups)].fetch_add(1, std::memory_order_relaxed);
  for (uint32_t i = 0; i < count; ++i) {
    census::MarkListBuffer(ranges[i].physical, ranges[i].bytes, list, origin, state);
  }
}

void OnAsyncRun(uint32_t device, uint32_t call, uint32_t lr) {
  Observe(device, kSiteAsync, lr);
  counters.async_runs.fetch_add(1, std::memory_order_relaxed);
  MarkNext(device, census::kSourceAsyncRun);
  if (g_armed.load(std::memory_order_relaxed)) {
    LogArmed(fmt::format("async call {:08X} run from lr {:08X}", call, lr));
  }
}

void OnD3dIb(uint32_t device, uint32_t lr) {
  Observe(device, kSiteD3dIb, lr);
  counters.d3d_ibs.fetch_add(1, std::memory_order_relaxed);
  MarkNext(device, census::kSourceD3dIb);
  const uint32_t buffer = Load32(device + kD3dBufferAddress) & 0x1FFFFFFFu;
  if (buffer) {
    census::MarkListBuffer(buffer, 0, device, census::kOriginD3dBuffer, census::kListFirstRun);
  }
}

void OnFixup(uint32_t r1, uint32_t holder, uint32_t record, uint32_t lr) {
  const bool is_static = t_static_r1 && t_static_r1 == r1;
  t_static_r1 = 0;
  const uint32_t type = GuestPointer(record) ? (Load32(record) & 0xF) : 0;
  counters.fixups[is_static ? 1 : 0][type].fetch_add(1, std::memory_order_relaxed);
  const uint32_t list = GuestPointer(holder) ? Load32(holder) : 0;
  if (!GuestPointer(list)) return;
  std::lock_guard<std::mutex> lock(g_lists_mutex);
  ListInfo& info = g_lists[list];
  ++info.fixups_pending[type];
  if (is_static) info.origin |= census::kOriginLoaded;
  if (!is_static && (g_fixup_callers.size() < 1024 || g_fixup_callers.count(lr))) {
    ++g_fixup_callers[lr];
  }
}

void OnStaticFixup(uint32_t r1, uint32_t holder) {
  t_static_r1 = r1;
  counters.static_lookups.fetch_add(1, std::memory_order_relaxed);
  const uint32_t list = GuestPointer(holder) ? Load32(holder) : 0;
  if (!GuestPointer(list)) return;
  std::lock_guard<std::mutex> lock(g_lists_mutex);
  g_lists[list].origin |= census::kOriginLoaded;
}

void OnSegmentSubmit(uint32_t device, uint32_t lr) {
  if (!GuestPointer(device)) return;
  Observe(device, kSiteSubmit, lr);
  uint8_t mode;
  if (Load8(device + kDropFlags) & 0x20) {
    mode = census::kSegmentDiscard;
  } else if (Load8(device + kRecordFlags) & 0x80) {
    mode = census::kSegmentRecording;
  } else if (Load32(device + kTilingState)) {
    mode = census::kSegmentTiling;
  } else {
    mode = census::kSegmentRing;
  }
  const uint32_t start = Load32(device + kSegmentStart);
  const uint32_t end = Load32(device + kWritePointer) + 4;
  const uint32_t bytes = end > start ? end - start : 0;
  counters.segments[mode].fetch_add(1, std::memory_order_relaxed);
  counters.segment_bytes[mode].fetch_add(bytes, std::memory_order_relaxed);
  const uint32_t physical = Physical(start);
  if (physical != UINT32_MAX && bytes) census::MarkSegment(physical, bytes, mode);
  if (mode == census::kSegmentRecording) {
    const uint32_t list = Load32(device + kRecordingBuffer);
    if (GuestPointer(list)) {
      std::lock_guard<std::mutex> lock(g_lists_mutex);
      g_lists[list].origin |= census::kOriginRecorded;
    }
  }
  if (g_armed.load(std::memory_order_relaxed)) {
    static constexpr const char* kModeName[census::kSegmentModeCount] = {
        "unknown", "ring", "tiling", "recording", "discard"};
    LogArmed(fmt::format("segment {:08X}+{:X} (physical {:08X}) submitted as {} from lr {:08X}",
                         start, bytes, physical, kModeName[mode], lr));
  }
}

void OnDraw(uint32_t entry, uint32_t r1, uint32_t device, uint32_t lr) {
  if (!GuestPointer(device) || entry >= kDrawEntries) return;
  Observe(device, uint8_t(kSiteDraw0 + entry), lr);
  bool nested;
  const uint8_t source = EnterDraw(r1, uint8_t(census::kSourceDrawEntry + entry), &nested);
  counters.draw_calls[entry][TargetOf(device)].fetch_add(1, std::memory_order_relaxed);
  if (nested) counters.draw_nested[entry].fetch_add(1, std::memory_order_relaxed);
  if (!MarkNext(device, source)) counters.draw_unmarked[entry].fetch_add(1, std::memory_order_relaxed);
}

void OnInternalDraw(uint32_t index, uint32_t r1, uint32_t device, uint32_t lr) {
  if (!GuestPointer(device) || index >= kInternalDraws) return;
  Observe(device, uint8_t(kSiteInternal0 + index), lr);
  bool nested;
  const uint8_t source = EnterDraw(r1, census::kSourceInternal, &nested);
  counters.internal_calls[index][TargetOf(device)].fetch_add(1, std::memory_order_relaxed);
  if (nested) counters.internal_nested[index].fetch_add(1, std::memory_order_relaxed);
  MarkNext(device, source);
}

void OnBracket(uint32_t index, uint32_t device, uint32_t arg, uint32_t lr) {
  if (index >= kBrackets) return;
  counters.brackets[index].fetch_add(1, std::memory_order_relaxed);
  if (!GuestPointer(device)) return;
  Observe(device, uint8_t(kSiteBracket0 + index), lr);
  if (g_armed.load(std::memory_order_relaxed)) {
    LogArmed(fmt::format("{} {:08X} entered from lr {:08X}: r4 {:08X}, recording buffer {:08X}, "
                         "tiling {:08X}, now {}",
                         kBracketName[index], kBracketAddress[index], lr, arg,
                         Load32(device + kRecordingBuffer), Load32(device + kTilingState),
                         kTargetName[TargetOf(device)]));
  }
}

void OnInsertCallback(uint32_t device, const uint32_t (&args)[4], uint32_t lr) {
  counters.callbacks.fetch_add(1, std::memory_order_relaxed);
  uint32_t callback = 0;
  for (uint32_t value : args) {
    if (value >= 0x82000000u && value < 0x84000000u) {
      callback = value;
      break;
    }
  }
  if (callback == kTilingCallback) {
    counters.tiling_callbacks.fetch_add(1, std::memory_order_relaxed);
  }
  if (GuestPointer(device)) Observe(device, kSiteInsertCallback, lr);
  {
    std::lock_guard<std::mutex> lock(g_lists_mutex);
    const uint64_t key = uint64_t(callback) << 32 | lr;
    if (g_callbacks.size() < 256 || g_callbacks.count(key)) ++g_callbacks[key];
  }
  if (g_armed.load(std::memory_order_relaxed)) {
    LogArmed(fmt::format("InsertCallback from lr {:08X}: r4 {:08X} r5 {:08X} r6 {:08X} r7 "
                         "{:08X}{}",
                         lr, args[0], args[1], args[2], args[3],
                         callback == kTilingCallback ? " (the tiling step)" : ""));
  }
}

// --- Window ---
uint32_t g_window_frames = 0;
uint32_t g_window_first_frame = 0;
bool g_v4_warned = false;

std::string Pct(uint64_t part, uint64_t whole) {
  return whole ? fmt::format("{:.1f}%", 100.0 * double(part) / double(whole)) : "-";
}

std::string Origin(uint8_t origin) {
  std::string out;
  if (origin & census::kOriginLoaded) out += "loaded,";
  if (origin & census::kOriginRecorded) out += "recorded,";
  if (origin & census::kOriginCloned) out += "cloned,";
  if (origin & census::kOriginStream) out += "streamed,";
  if (origin & census::kOriginD3dBuffer) out += "d3d,";
  if (out.empty()) return "unknown";
  out.pop_back();
  return out;
}

void Start() {
  for (const WriterRange& range : kWriterRanges) {
    census::AddWriterRange(range.begin, range.end, range.writer_class);
  }
  for (auto& word : g_stream_pages) word.store(0, std::memory_order_relaxed);
  g_window_frames = 0;
  g_window_first_frame = uint32_t(
      rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount));
  census::SetFrame(g_window_first_frame);
  census::SetEnabled(true);
  g_on.store(true, std::memory_order_release);
  REXLOG_INFO("D3D census: on from frame {} (window {} frames)", g_window_first_frame,
              REXCVAR_GET(pinyon_shift_d3d_census_window));
}

// With g_lists_mutex held: the owners of the window's list runs, most runs
// first, with what the decoder saw of their lists.
void LogOwners(double frames) {
  std::vector<std::pair<uint32_t, census::ListDecoded>> decoded;
  census::TakeListDecoded(&decoded);
  for (const auto& [list, counts] : decoded) {
    const auto it = g_list_owner.find(list);
    if (it == g_list_owner.end()) continue;
    census::ListDecoded& sum = g_owners[it->second].decoded;
    sum.draws += counts.draws;
    sum.copies += counts.copies;
    sum.events += counts.events;
    sum.memory_writes += counts.memory_writes;
    sum.waits += counts.waits;
    sum.constants += counts.constants;
    sum.shader_loads += counts.shader_loads;
  }
  std::vector<OwnerInfo*> owners;
  for (auto& [key, owner] : g_owners) {
    CloseOwnerFrame(owner);
    if (owner.runs) owners.push_back(&owner);
  }
  std::sort(owners.begin(), owners.end(),
            [](const OwnerInfo* a, const OwnerInfo* b) { return a->runs > b->runs; });
  auto per_frame = [&](uint64_t value) { return fmt::format("{:.1f}", double(value) / frames); };
  for (size_t i = 0; i < owners.size() && i < 24; ++i) {
    const OwnerInfo& o = *owners[i];
    std::string fixups, states;
    for (uint32_t type = 0; type < 16; ++type) {
      if (o.fixups[type]) fixups += fmt::format(" t{}={}", type, per_frame(o.fixups[type]));
    }
    for (uint32_t s = 0; s < census::kListStateCount; ++s) {
      if (o.states[s]) states += fmt::format(" {}={}", kStateName[s], o.states[s]);
    }
    REXLOG_INFO(
        "D3D census owner lr {:08X} callers {:08X} < {:08X} < {:08X}: {} lists, {} runs/frame, {:.0f} "
        "dwords/run, origin {}, fixups/frame{}, states{}; decoded/frame draws {} copies {} events "
        "{} memory writes {} waits {} constants {} shader loads {}; order same {} of {} frames, "
        "run count changed {}",
        o.lr, o.owner, o.owner_caller, o.owner_caller2, o.lists.size(), per_frame(o.runs),
        double(o.dwords) / double(std::max<uint64_t>(o.runs, 1)), Origin(uint8_t(o.origins)),
        fixups.empty() ? " none" : fixups, states, per_frame(o.decoded.draws),
        per_frame(o.decoded.copies), per_frame(o.decoded.events),
        per_frame(o.decoded.memory_writes), per_frame(o.decoded.waits),
        per_frame(o.decoded.constants), per_frame(o.decoded.shader_loads), o.same_order,
        o.frames, o.run_count_changes);
  }
  for (auto& [key, owner] : g_owners) {
    const uint32_t frame = owner.frame;
    const uint64_t previous = owner.previous, previous_runs = owner.previous_runs;
    owner = OwnerInfo{};
    owner.frame = frame;
    owner.previous = previous;
    owner.previous_runs = previous_runs;
  }
}

void LogWindow(uint32_t frame) {
  const double frames = std::max<uint32_t>(g_window_frames, 1);
  auto per_frame = [&](uint64_t value) { return fmt::format("{:.1f}", double(value) / frames); };
  REXLOG_INFO("D3D census window: frames {}-{} ({} frames)", g_window_first_frame, frame,
              g_window_frames);

  // (a) draw entry points by the buffer the device writes into.
  uint64_t top_level_ring = 0;
  for (uint32_t entry = 0; entry < kDrawEntries; ++entry) {
    uint64_t calls[kTargetCount], total = 0;
    for (uint32_t target = 0; target < kTargetCount; ++target) {
      calls[target] = Take(counters.draw_calls[entry][target]);
      total += calls[target];
    }
    const uint64_t nested = Take(counters.draw_nested[entry]);
    const uint64_t unmarked = Take(counters.draw_unmarked[entry]);
    if (!total) continue;
    top_level_ring += total - nested;
    REXLOG_INFO(
        "D3D census draw {:08X}: {}/frame (ring {}, rec {}, tiling {}, rec+tiling {}), nested "
        "{}, not physical {}",
        kDrawEntryAddress[entry], per_frame(total), per_frame(calls[kTargetRing]),
        per_frame(calls[kTargetRecording]), per_frame(calls[kTargetTiling]),
        per_frame(calls[kTargetRecordingTiling]), per_frame(nested), per_frame(unmarked));
  }
  for (uint32_t index = 0; index < kInternalDraws; ++index) {
    uint64_t total = 0, ring = 0;
    for (uint32_t target = 0; target < kTargetCount; ++target) {
      const uint64_t value = Take(counters.internal_calls[index][target]);
      total += value;
      if (target == kTargetRing) ring = value;
    }
    const uint64_t nested = Take(counters.internal_nested[index]);
    if (!total) continue;
    REXLOG_INFO("D3D census internal draw {:08X}: {}/frame (ring {}), nested {}",
                kInternalAddress[index], per_frame(total), per_frame(ring), per_frame(nested));
  }

  // (b) device-class slots.
  std::string slots;
  uint64_t draw_slots = 0;
  for (uint32_t slot = 0; slot < kSlots; ++slot) {
    const uint64_t calls = Take(counters.slot_calls[slot]);
    if (kSlotIsDraw[slot]) draw_slots += calls;
    if (calls) slots += fmt::format(" s{}={}", kSlotNumber[slot], per_frame(calls));
  }
  REXLOG_INFO("D3D census slots/frame:{}; draw slots {} against {} outermost draw calls",
              slots.empty() ? " none" : slots, per_frame(draw_slots), per_frame(top_level_ring));

  // (c) list lifecycle.
  uint64_t runs[kTargetCount], all_runs = 0;
  for (uint32_t target = 0; target < kTargetCount; ++target) {
    runs[target] = Take(counters.runs[target]);
    all_runs += runs[target];
  }
  uint64_t states[census::kListStateCount];
  for (uint32_t i = 0; i < census::kListStateCount; ++i) states[i] = Take(counters.run_states[i]);
  uint64_t buckets[6];
  for (uint32_t i = 0; i < 6; ++i) buckets[i] = Take(counters.run_fixups[i]);
  REXLOG_INFO(
      "D3D census runs/frame: {} (ring {}, rec {}, tiling {}, rec+tiling {}), async {}, d3d ib "
      "{}, null {}, async-type {}; {} dwords and {} buffers a frame; states first {} unchanged "
      "{} fixup_only {} changed_no_fixup {} other_write {}; fixups per run 0:{} 1:{} 2-3:{} "
      "4-7:{} 8-15:{} 16+:{}",
      per_frame(all_runs), per_frame(runs[kTargetRing]), per_frame(runs[kTargetRecording]),
      per_frame(runs[kTargetTiling]), per_frame(runs[kTargetRecordingTiling]),
      per_frame(Take(counters.async_runs)), per_frame(Take(counters.d3d_ibs)),
      per_frame(Take(counters.runs_null)), per_frame(Take(counters.runs_async_type)),
      per_frame(Take(counters.run_dwords)), per_frame(Take(counters.run_entries)),
      Pct(states[0], all_runs), Pct(states[1], all_runs), Pct(states[2], all_runs),
      Pct(states[3], all_runs), Pct(states[4], all_runs), buckets[0], buckets[1], buckets[2],
      buckets[3], buckets[4], buckets[5]);
  std::string fixups_dynamic, fixups_static;
  for (uint32_t type = 0; type < 16; ++type) {
    const uint64_t dynamic = Take(counters.fixups[0][type]);
    const uint64_t loaded = Take(counters.fixups[1][type]);
    if (dynamic) fixups_dynamic += fmt::format(" t{}={}", type, per_frame(dynamic));
    if (loaded) fixups_static += fmt::format(" t{}={}", type, loaded);
  }
  REXLOG_INFO(
      "D3D census fixups: dynamic/frame{}; static (window){}; static lookups {}, list loads "
      "{}, stream reads {} ({} KB), to physical {} ({} KB), clone calls {}, clones {}",
      fixups_dynamic.empty() ? " none" : fixups_dynamic,
      fixups_static.empty() ? " none" : fixups_static, Take(counters.static_lookups),
      Take(counters.loads), Take(counters.stream_reads), Take(counters.stream_bytes) / 1024,
      Take(counters.stream_physical_reads), Take(counters.stream_physical_bytes) / 1024,
      Take(counters.clone_calls), Take(counters.clones));
  {
    static constexpr const char* kModeName[census::kSegmentModeCount] = {
        "unknown", "ring", "tiling", "recording", "discard"};
    std::string segments;
    for (uint32_t mode = 0; mode < census::kSegmentModeCount; ++mode) {
      const uint64_t count = Take(counters.segments[mode]);
      const uint64_t bytes = Take(counters.segment_bytes[mode]);
      if (count) {
        segments += fmt::format(" {} {} ({} KB)", kModeName[mode], per_frame(count),
                                fmt::format("{:.1f}", double(bytes) / 1024.0 / frames));
      }
    }
    REXLOG_INFO("D3D census segments/frame:{}; segment closes {}",
                segments.empty() ? " none" : segments, per_frame(Take(counters.closes)));
  }

  // Per list, most runs first.
  {
    std::lock_guard<std::mutex> lock(g_lists_mutex);
    uint64_t origin_lists[32] = {}, origin_runs[32] = {};
    std::vector<std::pair<uint32_t, ListInfo*>> lists;
    for (auto it = g_lists.begin(); it != g_lists.end();) {
      ListInfo& info = it->second;
      if (info.window_runs) {
        ++origin_lists[info.origin & 31];
        origin_runs[info.origin & 31] += info.window_runs;
        lists.emplace_back(it->first, &info);
      }
      ++it;
    }
    std::string origins;
    for (uint32_t origin = 0; origin < 32; ++origin) {
      if (origin_lists[origin]) {
        origins += fmt::format(" {}: {} lists, {} runs/frame;", Origin(uint8_t(origin)),
                               origin_lists[origin], per_frame(origin_runs[origin]));
      }
    }
    REXLOG_INFO("D3D census lists run: {} ({} new);{}", lists.size(), g_new_lists, origins);
    std::sort(lists.begin(), lists.end(),
              [](const auto& a, const auto& b) { return a.second->window_runs > b.second->window_runs; });
    const uint32_t limit = REXCVAR_GET(pinyon_shift_d3d_census_list_log);
    for (size_t i = 0; i < lists.size() && i < limit; ++i) {
      const ListInfo& info = *lists[i].second;
      std::string state_text;
      for (uint32_t s = 0; s < census::kListStateCount; ++s) {
        if (info.states[s]) state_text += fmt::format(" {}={}", kStateName[s], info.states[s]);
      }
      REXLOG_INFO(
          "D3D census list {:08X}: {} runs/frame, {} dwords in {} buffers, flags {:08X}, origin "
          "{}, first frame {}, fixups/run {:.1f}, states{}, watched writes fixup {} stream {} "
          "clone {} other {}",
          lists[i].first, per_frame(info.window_runs), info.dwords, info.entries, info.flags,
          Origin(info.origin), info.first_frame,
          double(info.window_fixups) / double(std::max<uint64_t>(info.window_runs, 1)),
          state_text, info.window_writes[census::kWriterFixup],
          info.window_writes[census::kWriterStream], info.window_writes[census::kWriterClone],
          info.window_writes[census::kWriterOther]);
    }
    // Reset the window, drop lists not run for a minute.
    for (auto it = g_lists.begin(); it != g_lists.end();) {
      ListInfo& info = it->second;
      if (info.seen_run && frame - info.last_frame > 3600) {
        it = g_lists.erase(it);
        continue;
      }
      info.window_runs = info.window_fixups = 0;
      std::fill(std::begin(info.states), std::end(info.states), 0);
      std::fill(std::begin(info.window_writes), std::end(info.window_writes), 0);
      ++it;
    }
    g_new_lists = 0;
    LogOwners(frames);
    std::vector<std::pair<uint32_t, uint64_t>> callers(g_fixup_callers.begin(),
                                                       g_fixup_callers.end());
    std::sort(callers.begin(), callers.end(),
              [](const auto& a, const auto& b) { return a.second > b.second; });
    std::string caller_text;
    for (size_t i = 0; i < callers.size() && i < 8; ++i) {
      caller_text += fmt::format(" {:08X}={}", callers[i].first, per_frame(callers[i].second));
    }
    g_fixup_callers.clear();
    std::vector<std::pair<uint64_t, uint64_t>> callbacks(g_callbacks.begin(), g_callbacks.end());
    std::sort(callbacks.begin(), callbacks.end(),
              [](const auto& a, const auto& b) { return a.second > b.second; });
    std::string callback_text;
    for (size_t i = 0; i < callbacks.size() && i < 8; ++i) {
      callback_text += fmt::format(" {:08X} from {:08X}={}", uint32_t(callbacks[i].first >> 32),
                                   uint32_t(callbacks[i].first), per_frame(callbacks[i].second));
    }
    g_callbacks.clear();
    REXLOG_INFO("D3D census dynamic fixup callers/frame (lr):{}", caller_text);
    REXLOG_INFO(
        "D3D census callbacks/frame {} (tiling step queued {}, fired {}):{}",
        per_frame(Take(counters.callbacks)), per_frame(Take(counters.tiling_callbacks)),
        per_frame(Take(counters.tiling_callback_fires)), callback_text);
  }

  // (d) the IB write watch's writers, by class.
  census::WriterWindow writers;
  census::TakeWriterWindow(&writers);
  {
    std::string other;
    for (size_t i = 0; i < std::size(writers.other_lr) && writers.other_lr_count[i]; ++i) {
      other += fmt::format(" {:08X}={}", writers.other_lr[i], writers.other_lr_count[i]);
    }
    REXLOG_INFO(
        "D3D census watched writes (window): lists fixup {} stream {} clone {} other {}; outer "
        "fixup {} stream {} clone {} other {}; into known lists fixup {} stream {} clone {} "
        "other {}; other lrs:{}",
        writers.writes[0][census::kWriterFixup], writers.writes[0][census::kWriterStream],
        writers.writes[0][census::kWriterClone], writers.writes[0][census::kWriterOther],
        writers.writes[1][census::kWriterFixup], writers.writes[1][census::kWriterStream],
        writers.writes[1][census::kWriterClone], writers.writes[1][census::kWriterOther],
        writers.list_object_writes[census::kWriterFixup],
        writers.list_object_writes[census::kWriterStream],
        writers.list_object_writes[census::kWriterClone],
        writers.list_object_writes[census::kWriterOther], other.empty() ? " none" : other);
  }

  // (e) buffer switches by the sites around them.
  {
    std::string brackets;
    for (uint32_t i = 0; i < kBrackets; ++i) {
      brackets += fmt::format(" {}={}", kBracketName[i], per_frame(Take(counters.brackets[i])));
    }
    std::lock_guard<std::mutex> lock(g_device_mutex);
    std::vector<std::pair<uint32_t, uint64_t>> switches(g_switches.begin(), g_switches.end());
    std::sort(switches.begin(), switches.end(),
              [](const auto& a, const auto& b) { return a.second > b.second; });
    REXLOG_INFO("D3D census bracket candidates/frame:{}; devices {}; switch kinds {}", brackets,
                g_devices.size(), switches.size());
    for (size_t i = 0; i < switches.size() && i < 16; ++i) {
      const uint32_t key = switches[i].first;
      REXLOG_INFO("D3D census switch {}: {} -> {}, {}/frame", ChangeNames(key >> 16),
                  SiteName(key & 0xFF), SiteName((key >> 8) & 0xFF), per_frame(switches[i].second));
    }
    g_switches.clear();
  }

  // (f) drawn draws by the path that wrote them, from the decoder.
  census::DecoderWindow decoder;
  census::TakeDecoderWindow(&decoder);
  const double swaps = double(std::max<uint64_t>(decoder.swaps, 1));
  uint64_t drawn = 0;
  for (uint64_t value : decoder.drawn) drawn += value;
  static constexpr const char* kClassName[census::kDrawClassCount] = {
      "immediate", "tiled_immediate", "internal", "list", "d3d_buffer", "unattributed",
      "unknown_buffer"};
  std::string classes, times;
  uint64_t decode_ns = 0;
  for (uint32_t i = 0; i < census::kDrawClassCount; ++i) {
    classes += fmt::format(" {} {:.1f} ({})", kClassName[i], double(decoder.drawn[i]) / swaps,
                           Pct(decoder.drawn[i], drawn));
    times += fmt::format(" {} {:.3f}", kClassName[i], double(decoder.decode_ns[i]) / 1e6 / swaps);
    decode_ns += decoder.decode_ns[i];
  }
  const uint64_t list_drawn = decoder.drawn[census::kDrawList];
  // A draw is visible to an API-level renderer if it comes from a draw call
  // (immediate, tiled or internal) or from a list that changed only through
  // fixups (or not at all); everything else would need the PM4 fallback.
  const uint64_t list_other = decoder.list_drawn_by_state[census::kListOtherWrite] +
                              decoder.list_drawn_by_state[census::kListChangedNoFixup];
  const uint64_t visible = decoder.drawn[census::kDrawImmediate] +
                           decoder.drawn[census::kDrawTiledImmediate] +
                           decoder.drawn[census::kDrawInternal] + list_drawn - list_other;
  REXLOG_INFO("D3D census drawn/frame {:.1f} over {} swaps:{}; fallback {}",
              double(drawn) / swaps, decoder.swaps, classes, Pct(drawn - visible, drawn));
  REXLOG_INFO("D3D census decoder ms/frame {:.3f}:{}", double(decode_ns) / 1e6 / swaps, times);
  {
    std::string states_text;
    for (uint32_t s = 0; s < census::kListStateCount; ++s) {
      states_text += fmt::format(" {} {}", kStateName[s], Pct(decoder.list_drawn_by_state[s], list_drawn));
    }
    std::string origins;
    for (uint32_t origin = 0; origin < 32; ++origin) {
      if (decoder.list_drawn_by_origin[origin]) {
        origins += fmt::format(" {} {}", Origin(uint8_t(origin)),
                               Pct(decoder.list_drawn_by_origin[origin], list_drawn));
      }
    }
    REXLOG_INFO(
        "D3D census list draws by state since the previous run:{}; by origin:{}; mark spans "
        "with 0/1/more draws {}/{}/{}; marks found {}, in segment gaps {}",
        states_text, origins.empty() ? " none" : origins, decoder.spans[0], decoder.spans[1],
        decoder.spans[2], decoder.marks_found, decoder.gap_marks_found);
    static constexpr const char* kContextName[census::kContextCount] = {
        "ring", "segment", "tiled_segment", "rec_segment", "unknown_segment", "list",
        "d3d_buffer", "unknown_nested"};
    std::string ibs;
    for (uint32_t c = 0; c < census::kContextCount; ++c) {
      if (decoder.ibs[c]) ibs += fmt::format(" {} {:.1f}", kContextName[c], double(decoder.ibs[c]) / swaps);
    }
    REXLOG_INFO("D3D census buffers/frame by kind:{}", ibs.empty() ? " none" : ibs);
    for (uint32_t s = 0; s < census::kSourceCount; ++s) {
      std::string row;
      for (uint32_t c = 0; c < census::kContextCount; ++c) {
        if (decoder.drawn_by_source[s][c]) {
          row += fmt::format(" {} {:.1f}", kContextName[c], double(decoder.drawn_by_source[s][c]) / swaps);
        }
      }
      if (row.empty()) continue;
      std::string source_name;
      if (s >= census::kSourceDrawEntry && s < census::kSourceDrawEntry + kDrawEntries) {
        source_name = fmt::format("draw {:08X}", kDrawEntryAddress[s - census::kSourceDrawEntry]);
      } else if (s == census::kSourceInternal) {
        source_name = "internal";
      } else if (s == census::kSourceListRun) {
        source_name = "list run";
      } else if (s == census::kSourceAsyncRun) {
        source_name = "async run";
      } else if (s == census::kSourceD3dIb) {
        source_name = "d3d ib";
      } else {
        source_name = s ? fmt::format("source {}", s) : "no mark";
      }
      REXLOG_INFO("D3D census drawn/frame from {}:{}", source_name, row);
    }
  }

  const std::string frames_text = std::to_string(g_window_frames);
  const std::string drawn_text = fmt::format("{:.1f}", double(drawn) / swaps);
  const std::string immediate_text = Pct(decoder.drawn[census::kDrawImmediate] +
                                             decoder.drawn[census::kDrawTiledImmediate],
                                         drawn);
  const std::string internal_text = Pct(decoder.drawn[census::kDrawInternal], drawn);
  const std::string list_text = Pct(list_drawn, drawn);
  const std::string fallback_text = Pct(drawn - visible, drawn);
  const std::string decoder_text = fmt::format("{:.3f}", double(decode_ns) / 1e6 / swaps);
  const std::string runs_text = per_frame(all_runs);
  const std::string other_text = std::to_string(writers.writes[0][census::kWriterOther]);
  pinyon_shift::diagnostics::RecordEvent(
      "d3d.census.window", {{"frames", frames_text},
                            {"drawn_per_frame", drawn_text},
                            {"immediate", immediate_text},
                            {"internal", internal_text},
                            {"list", list_text},
                            {"fallback", fallback_text},
                            {"decoder_ms", decoder_text},
                            {"runs_per_frame", runs_text},
                            {"other_list_writes", other_text}});
}

}  // namespace

void D3dCensusFrame() {
  bool want = REXCVAR_GET(pinyon_shift_d3d_census);
  if (want && fh1::kTitleUpdateV4) {
    if (!g_v4_warned) {
      REXLOG_WARN("D3D census: the title-update build has no census hooks; staying off");
      g_v4_warned = true;
    }
    want = false;
  }
  if (want != On()) {
    if (want) {
      Start();
    } else {
      g_on.store(false, std::memory_order_release);
      census::SetEnabled(false);
      REXLOG_INFO("D3D census: off");
    }
  }
  if (!want) return;
  const uint32_t frame =
      uint32_t(rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount));
  census::SetFrame(frame);
  const bool lean = REXCVAR_GET(pinyon_shift_d3d_census_lean);
  if (lean != g_lean.load(std::memory_order_relaxed)) {
    REXLOG_INFO("D3D census: lean {} at frame {}", lean ? "on" : "off", frame);
    g_lean.store(lean, std::memory_order_relaxed);
    census::SetLean(lean);
  }
  const int32_t armed_frame = REXCVAR_GET(pinyon_shift_d3d_census_bracket_frame);
  const bool armed = armed_frame >= 0 && uint32_t(armed_frame) == frame;
  if (armed != g_armed.load(std::memory_order_relaxed)) {
    REXLOG_INFO("D3D census DL-0.2: buffer switch log {} at frame {}", armed ? "on" : "off", frame);
    g_armed_logs.store(0, std::memory_order_relaxed);
    g_armed.store(armed, std::memory_order_relaxed);
  }
  if (++g_window_frames >= REXCVAR_GET(pinyon_shift_d3d_census_window)) {
    LogWindow(frame);
    g_window_frames = 0;
    g_window_first_frame = frame;
  }
}

void D3dCensusDrawEntry(uint32_t entry, uint32_t r1, uint32_t device, uint32_t lr) {
  if (On()) OnDraw(entry, r1, device, lr);
}

}  // namespace pinyon_shift::native_renderer

// --- Mid-asm hooks (config/rexglue/analysis/main-xex.toml, "DL-0.1 D3D source
// census"). Each returns at once while the census is off. ---

using pinyon_shift::native_renderer::D3dCensusDrawEntry;
namespace census_impl = pinyon_shift::native_renderer;

#define PINYON_D3D_CENSUS_DRAW(n)                                                    \
  void PinyonShiftD3dCensusDraw##n(PPCRegister& r1, PPCRegister& r3, uint64_t& lr) { \
    D3dCensusDrawEntry(n, r1.u32, r3.u32, uint32_t(lr));                             \
  }
// Entry 0 (0x82416380) is PinyonShiftD3dCensusDraw0 in d3d_draw.cpp, with the
// DL-1.2 D3D-level draw marker.
// Entry 1 (0x82415F68) is PinyonShiftD3dCensusDraw1 in d3d_draw.cpp (DL-2.1 slice).
PINYON_D3D_CENSUS_DRAW(2)
PINYON_D3D_CENSUS_DRAW(3)
PINYON_D3D_CENSUS_DRAW(4)
// Entry 5 (0x8240F4D8) is PinyonShiftObserveTitleDrawEmitterBegin.
PINYON_D3D_CENSUS_DRAW(6)
PINYON_D3D_CENSUS_DRAW(7)
PINYON_D3D_CENSUS_DRAW(8)
#undef PINYON_D3D_CENSUS_DRAW

#define PINYON_D3D_CENSUS_INTERNAL(n)                                                    \
  void PinyonShiftD3dCensusInternal##n(PPCRegister& r1, PPCRegister& r3, uint64_t& lr) { \
    if (census_impl::On()) census_impl::OnInternalDraw(n, r1.u32, r3.u32, uint32_t(lr)); \
  }
PINYON_D3D_CENSUS_INTERNAL(0)
PINYON_D3D_CENSUS_INTERNAL(1)
PINYON_D3D_CENSUS_INTERNAL(2)
PINYON_D3D_CENSUS_INTERNAL(3)
PINYON_D3D_CENSUS_INTERNAL(4)
#undef PINYON_D3D_CENSUS_INTERNAL

#define PINYON_D3D_CENSUS_SLOT(slot, index)                                            \
  void PinyonShiftD3dCensusSlot##slot() {                                              \
    static_assert(census_impl::kSlotNumber[index] == slot);                            \
    if (census_impl::On()) {                                                           \
      census_impl::counters.slot_calls[index].fetch_add(1, std::memory_order_relaxed); \
    }                                                                                  \
  }
PINYON_D3D_CENSUS_SLOT(12, 0)
PINYON_D3D_CENSUS_SLOT(22, 1)
PINYON_D3D_CENSUS_SLOT(23, 2)
PINYON_D3D_CENSUS_SLOT(24, 3)
PINYON_D3D_CENSUS_SLOT(25, 4)
PINYON_D3D_CENSUS_SLOT(26, 5)
PINYON_D3D_CENSUS_SLOT(30, 6)
PINYON_D3D_CENSUS_SLOT(31, 7)
PINYON_D3D_CENSUS_SLOT(38, 8)
PINYON_D3D_CENSUS_SLOT(39, 9)
PINYON_D3D_CENSUS_SLOT(40, 10)
PINYON_D3D_CENSUS_SLOT(41, 11)
PINYON_D3D_CENSUS_SLOT(42, 12)
PINYON_D3D_CENSUS_SLOT(43, 13)
PINYON_D3D_CENSUS_SLOT(44, 14)
PINYON_D3D_CENSUS_SLOT(48, 15)
PINYON_D3D_CENSUS_SLOT(65, 16)
PINYON_D3D_CENSUS_SLOT(66, 17)
#undef PINYON_D3D_CENSUS_SLOT

namespace pinyon_shift::native_renderer {
void D3dProgramOnRun(uint32_t list);  // d3d_program.cpp
}

// 0x82416A00, D3DDevice_RunCommandBuffer: r3 the device, r4 the command buffer.
// Also the NA-2.4 pilot's list marking (d3d_program.cpp).
void PinyonShiftD3dCensusRunCommandBuffer(PPCRegister& r1, PPCRegister& r3, PPCRegister& r4,
                                          uint64_t& lr) {
  if (census_impl::On()) census_impl::OnRun(r1.u32, r3.u32, r4.u32, uint32_t(lr));
  pinyon_shift::native_renderer::D3dProgramOnRun(r4.u32);
}

// 0x829EC928, the asynchronous command-buffer call run: r3 the device, r4 the call.
void PinyonShiftD3dCensusRunAsync(PPCRegister& r3, PPCRegister& r4, uint64_t& lr) {
  if (census_impl::On()) census_impl::OnAsyncRun(r3.u32, r4.u32, uint32_t(lr));
}

// 0x8246FB98, D3D's own indirect buffer: r3 the device.
void PinyonShiftD3dCensusD3dIb(PPCRegister& r3, uint64_t& lr) {
  if (census_impl::On()) census_impl::OnD3dIb(r3.u32, uint32_t(lr));
}

// 0x82C58DA8, the fixup dispatcher: r3 points at the command buffer, r4 at the
// fixup record (handle and resource type in its first word).
void PinyonShiftD3dCensusFixup(PPCRegister& r1, PPCRegister& r3, PPCRegister& r4,
                               uint64_t& lr) {
  if (census_impl::On()) census_impl::OnFixup(r1.u32, r3.u32, r4.u32, uint32_t(lr));
}

// 0x82C592F0, the static fixup by handle (load path): r3 points at the command
// buffer; it tail-calls the dispatcher.
void PinyonShiftD3dCensusStaticFixup(PPCRegister& r1, PPCRegister& r3, uint64_t&) {
  if (census_impl::On()) census_impl::OnStaticFixup(r1.u32, r3.u32);
}

// 0x82C59E40, the serialised command-buffer reader.
void PinyonShiftD3dCensusListLoad(PPCRegister& r3, PPCRegister& r4, uint64_t& lr) {
  if (!census_impl::On()) return;
  census_impl::counters.loads.fetch_add(1, std::memory_order_relaxed);
  if (census_impl::g_armed.load(std::memory_order_relaxed)) {
    census_impl::LogArmed(fmt::format("list load r3 {:08X} r4 {:08X} from lr {:08X}", r3.u32,
                                      r4.u32, uint32_t(lr)));
  }
}

// 0x82C76A90, the buffered file read: r4 the destination, r5 the size.
void PinyonShiftD3dCensusStreamRead(PPCRegister& r4, PPCRegister& r5, uint64_t&) {
  if (!census_impl::On()) return;
  census_impl::counters.stream_reads.fetch_add(1, std::memory_order_relaxed);
  census_impl::counters.stream_bytes.fetch_add(r5.u32, std::memory_order_relaxed);
  if (!r5.u32 || r5.u32 > (64u << 20)) return;
  const uint32_t physical = census_impl::Physical(r4.u32);
  if (physical == UINT32_MAX) return;
  census_impl::counters.stream_physical_reads.fetch_add(1, std::memory_order_relaxed);
  census_impl::counters.stream_physical_bytes.fetch_add(r5.u32, std::memory_order_relaxed);
  census_impl::MarkStreamPages(physical & 0x1FFFFFFFu, r5.u32);
}

// 0x829EB2B0, the clone (sizes, allocates, copies).
void PinyonShiftD3dCensusCloneCall(PPCRegister& r3, PPCRegister&, uint64_t& lr) {
  if (!census_impl::On()) return;
  census_impl::counters.clone_calls.fetch_add(1, std::memory_order_relaxed);
  if (census_impl::g_armed.load(std::memory_order_relaxed)) {
    census_impl::LogArmed(fmt::format("clone of {:08X} from lr {:08X}", r3.u32, uint32_t(lr)));
  }
}

// 0x829EB0B8, the clone copy: r3 the source; with r5 set, r5 the new header
// and r7 its data.
void PinyonShiftD3dCensusCloneCopy(PPCRegister& r3, PPCRegister& r5, PPCRegister& r7,
                                   uint64_t&) {
  if (!census_impl::On() || !census_impl::GuestPointer(r5.u32)) return;
  census_impl::counters.clones.fetch_add(1, std::memory_order_relaxed);
  std::lock_guard<std::mutex> lock(census_impl::g_lists_mutex);
  census_impl::ListInfo& info = census_impl::g_lists[r5.u32];
  info.origin |= rex::system::d3d_census::kOriginCloned;
  info.clone_source = r3.u32;
  (void)r7;
}

// 0x8240D070, segment submit: r3 the device.
void PinyonShiftD3dCensusSegmentSubmit(PPCRegister& r3, uint64_t& lr) {
  if (census_impl::On()) census_impl::OnSegmentSubmit(r3.u32, uint32_t(lr));
}

// 0x8240CF68, segment close (called when a writer runs out of space).
void PinyonShiftD3dCensusSegmentClose(PPCRegister& r3, uint64_t& lr) {
  if (!census_impl::On()) return;
  census_impl::counters.closes.fetch_add(1, std::memory_order_relaxed);
  census_impl::Observe(r3.u32, census_impl::kSiteClose, uint32_t(lr));
}

#define PINYON_D3D_CENSUS_BRACKET(n)                                                       \
  void PinyonShiftD3dCensusBracket##n(PPCRegister& r3, PPCRegister& r4, uint64_t& lr) {   \
    if (census_impl::On()) census_impl::OnBracket(n, r3.u32, r4.u32, uint32_t(lr));       \
  }
PINYON_D3D_CENSUS_BRACKET(0)
PINYON_D3D_CENSUS_BRACKET(1)
PINYON_D3D_CENSUS_BRACKET(2)
PINYON_D3D_CENSUS_BRACKET(3)
#undef PINYON_D3D_CENSUS_BRACKET

// 0x823E67A8, InsertCallback: r3 the device.
void PinyonShiftD3dCensusInsertCallback(PPCRegister& r3, PPCRegister& r4, PPCRegister& r5,
                                        PPCRegister& r6, PPCRegister& r7, uint64_t& lr) {
  if (!census_impl::On()) return;
  const uint32_t args[4] = {r4.u32, r5.u32, r6.u32, r7.u32};
  census_impl::OnInsertCallback(r3.u32, args, uint32_t(lr));
}

// 0x829F5948, D3D's tiling step callback (queues a tile's replay).
void PinyonShiftD3dCensusTilingCallback(PPCRegister& r3, uint64_t& lr) {
  if (!census_impl::On()) return;
  census_impl::counters.tiling_callback_fires.fetch_add(1, std::memory_order_relaxed);
  if (census_impl::g_armed.load(std::memory_order_relaxed)) {
    census_impl::LogArmed(
        fmt::format("tiling step callback fired: r3 {:08X}, lr {:08X}", r3.u32, uint32_t(lr)));
  }
}
