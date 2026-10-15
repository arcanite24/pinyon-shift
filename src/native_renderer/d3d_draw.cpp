// D3D-level draws (docs/D3D_RENDERER_RESEARCH.md DL-1.2). See d3d_draw.h.
//
// The device offsets and the dirty-mask layout below are our reading of the
// D3D runtime's indexed draw call (0x82416380) and its shader bind
// (0x82411C80) in the base executable
// (.local/backlog-research/d3d-renderer-2026-10-14/dl12.md). The decoder's
// verify mode (pinyon_shift_d3d_draw 1) checks every description against the
// registers, shader loads and draw packet the device wrote.

#include "native_renderer/d3d_draw.h"

#include "native_renderer/d3d_census.h"

#include <atomic>
#include <cstdint>
#include <cstring>
#include <string>

#include <fmt/format.h>

#include <rex/cvar.h>
#include <rex/logging/macros.h>
#include <rex/ppc/context.h>
#include <rex/system/d3d_draw.h>
#include <rex/system/kernel_state.h>
#include <rex/system/xmemory.h>
#include <rex/types.h>

REXCVAR_DEFINE_INT32(pinyon_shift_d3d_draw, 0, "Pinyon Shift",
                     "D3D_RENDERER_RESEARCH DL-1.2: describe the title's indexed D3D draw "
                     "calls from the device state at the call and hand them to the command "
                     "processor (0: off; 1: verify, the packets still draw and are compared "
                     "with the description; 2: draw from the description, the call's packets "
                     "are skipped). Base-disc build")
    .range(0, 2)
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_INT32(pinyon_shift_d3d_draw_scope, 0, "Pinyon Shift",
                     "With pinyon_shift_d3d_draw: 0 the HUD pass (draws whose render target "
                     "is 2_10_10_10_AS_10_10_10_10), 1 every indexed draw call outside tiling "
                     "and predication (in draw mode, not those recorded into command buffers)")
    .range(0, 1)
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_INT32(pinyon_shift_d3d_slice, 0, "Pinyon Shift",
                     "D3D_RENDERER_RESEARCH DL-2.1, the first native slice: the title's "
                     "indexed and auto-index D3D draw calls outside command-buffer recording "
                     "whose state flush is plain (no shader bind, per-tile state, clip planes "
                     "or wait) are replaced by a description of the call, and the GPU "
                     "decoder runs display lists from a compiled form (0: off; 1: verify, "
                     "the calls still run and lists still decode, both are compared; 2: on). "
                     "Applied at the next frame. Base-disc build")
    .range(0, 2)
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

namespace pinyon_shift::native_renderer {
namespace {

namespace d3d_draw = rex::system::d3d_draw;

// --- The D3D device (our reading; offsets from the device pointer) ---
// Dirty masks: +0 vertex shader float constants, +8 pixel shader float
// constants, +16 shader bind and the 0x2000-0x22xx groups, +24 fetch
// constants and 0x2280, +32 0x2380, clip planes, bool/loop constants, 0x2300.
constexpr uint32_t kMaskVsConstants = 0, kMaskPsConstants = 8, kMaskState = 16,
                   kMaskFetch = 24, kMaskMisc = 32;
constexpr uint32_t kWritePointer = 48, kSegmentLimit = 56;
// Shadows the dirty masks flush from.
constexpr uint32_t kFetchShadow = 1152, kVsConstantShadow = 1920, kPsConstantShadow = 6016,
                   kBoolLoopShadow = 10112, kClipPlaneShadow = 10272;
// RB_COLOR_INFO's shadow (in the 0x2000 group at +10368).
constexpr uint32_t kColorInfoShadow = 10372;
// Bit 0: predicated draws (queries); bit 6: the tiled shader-load path;
// bit 7: a command buffer is being recorded.
constexpr uint32_t kRecordFlags = 11068;
constexpr uint32_t kTilingState = 13600;
// The bound index buffer object: +0 flags (bit 31: 32-bit indices, bits
// 30-29 the endian swap), +24 its base address.
constexpr uint32_t kIndexBuffer = 12812;
// The draw packet's viz query word: a byte index at +12563 into a table at
// +12498.
constexpr uint32_t kVizIndex = 12563, kVizTable = 12498;
// The mask ANDed with the state mask for the per-tile state (0x8240F148).
constexpr uint32_t kMaskPerTile = 40;
// Bits 6 and 7 make the call write WAIT_UNTIL and 0x0E00/0x0E40 for mask
// +32 bits 62-63 (0x824091B8).
constexpr uint32_t kWaitFlags = 11072;

struct RegisterGroup {
  uint32_t mask;      // dirty-mask offset
  uint32_t top_bit;   // the mask bit of the first register
  uint32_t count;     // registers, one bit each
  uint32_t first;     // first register
  uint32_t shadow;    // shadow offset
};
// In the order the draw call flushes them (0x82416380).
constexpr RegisterGroup kStateGroups[] = {
    {kMaskState, 11, 12, 0x2200, 10548},
    {kMaskState, 16, 5, 0x2180, 10528},
    {kMaskState, 57, 16, 0x2000, 10368},
    {kMaskState, 41, 21, 0x2100, 10444},
};
constexpr RegisterGroup kFetchGroup2280 = {kMaskFetch, 54, 21, 0x2280, 10596};
constexpr RegisterGroup kMiscGroup2380 = {kMaskMisc, 45, 8, 0x2380, 10832};
constexpr RegisterGroup kMiscGroup2300 = {kMaskMisc, 37, 38, 0x2300, 10680};

auto* Memory() { return rex::system::kernel_state()->memory(); }
template <typename T>
T* Guest(uint32_t address) {
  return Memory()->template TranslateVirtual<T*>(address);
}
uint32_t Load32(uint32_t address) { return rex::byte_swap(*Guest<uint32_t>(address)); }
uint64_t Load64(uint32_t address) { return rex::byte_swap(*Guest<uint64_t>(address)); }
uint16_t Load16(uint32_t address) { return rex::byte_swap(*Guest<uint16_t>(address)); }
uint8_t Load8(uint32_t address) { return *Guest<uint8_t>(address); }
void Store32(uint32_t address, uint32_t value) { *Guest<uint32_t>(address) = rex::byte_swap(value); }
void Store64(uint32_t address, uint64_t value) { *Guest<uint64_t>(address) = rex::byte_swap(value); }

// The runtime's GPU address of a CPU address (0xE0000000 and up is offset by
// a page).
uint32_t GpuAddress(uint32_t address) {
  return (address & 0x1FFFFFFFu) + ((((address >> 20) & 0xFFFu) + 0x200u) & 0x1000u);
}

enum LoadKind : uint8_t { kLoadLiteral, kLoadShader, kLoadInline };
struct Load {
  LoadKind kind;
  uint32_t a, b, c;
};
constexpr uint32_t kMaxLoads = 32;

// The draw call this thread is inside.
struct Pending {
  bool active = false;
  bool overflow = false;
  uint32_t device = 0;
  uint32_t id = 0;
  uint32_t prim = 0, base_vertex = 0, start = 0, count = 0;
  uint64_t masks[5] = {};
  uint32_t load_count = 0;
  Load loads[kMaxLoads];
};
thread_local Pending t_pending;
thread_local d3d_draw::Description t_description;

struct Stats {
  std::atomic<uint64_t> calls{0}, markers{0}, published{0}, declined{0}, overflow{0},
      no_space{0}, too_long{0}, not_hud{0};
  // Not taken, by reason (recording, tiled shader path, predicated, tiling),
  // all calls and those whose target is the HUD's format at entry.
  std::atomic<uint64_t> not_ring[4] = {}, hud_not_ring[4] = {};
  std::atomic<uint64_t> hud_calls{0};
};
Stats g_stats;
uint32_t g_frames = 0;

void AddLoad(LoadKind kind, uint32_t a, uint32_t b, uint32_t c) {
  Pending& pending = t_pending;
  if (pending.load_count >= kMaxLoads) {
    pending.overflow = true;
    return;
  }
  pending.loads[pending.load_count++] = {kind, a, b, c};
}

class Writer {
 public:
  explicit Writer(d3d_draw::Description& description) : d_(description) {}
  bool overflow() const { return overflow_; }
  // Opens an entry; returns its payload, or nullptr if it does not fit.
  uint32_t* Entry(uint32_t kind, uint32_t first, uint32_t payload_words, uint32_t count) {
    if (d_.word_count + 2 + payload_words > d3d_draw::kMaxWords) {
      overflow_ = true;
      return nullptr;
    }
    uint32_t* words = d_.words + d_.word_count;
    words[0] = (kind << 16) | count;
    words[1] = first;
    d_.word_count += 2 + payload_words;
    return words + 2;
  }
  // A run of registers from the guest shadow, copied as stored (big-endian).
  void Run(uint32_t first, uint32_t count, uint32_t shadow) {
    if (!count) return;
    if (uint32_t* payload = Entry(d3d_draw::kEntryRegisters, first, count, count)) {
      std::memcpy(payload, Guest<uint32_t>(shadow), count * sizeof(uint32_t));
    }
  }
  // The registers of a group whose bits are set, in runs.
  void Group(const RegisterGroup& group, uint64_t mask, uint32_t device) {
    uint32_t i = 0;
    while (i < group.count) {
      if (!((mask >> (group.top_bit - i)) & 1)) {
        ++i;
        continue;
      }
      uint32_t end = i + 1;
      while (end < group.count && ((mask >> (group.top_bit - end)) & 1)) ++end;
      Run(group.first + i, end - i, device + group.shadow + i * 4);
      i = end;
    }
  }
  // 64 bits, each `per_bit` registers (shadow stride `per_bit` words).
  void Blocks(uint64_t mask, uint32_t first, uint32_t per_bit, uint32_t shadow) {
    uint32_t i = 0;
    while (i < 64) {
      if (!((mask >> (63 - i)) & 1)) {
        ++i;
        continue;
      }
      uint32_t end = i + 1;
      while (end < 64 && ((mask >> (63 - end)) & 1)) ++end;
      Run(first + i * per_bit, (end - i) * per_bit, shadow + i * per_bit * 4);
      i = end;
    }
  }

 private:
  d3d_draw::Description& d_;
  bool overflow_ = false;
};

// The registers and loads the call's state flush writes, in its order, then
// VGT_INDX_OFFSET (written by the call itself). With fetch_flush, also the
// fetch constant flush's trailing 0x5000-0x5002 write (DL-1.2 leaves it to
// the packets; a replaced call writes none).
void DescribeFlush(const Pending& pending, uint32_t device, Writer& writer, bool fetch_flush) {
  const uint64_t* masks = pending.masks;
  // Float constants, 4 float4 a bit.
  writer.Blocks(masks[0], 0x4000, 16, device + kVsConstantShadow);
  writer.Blocks(masks[1], 0x4400, 16, device + kPsConstantShadow);
  // The shader bind's loads, in order: literal constants and microcode.
  for (uint32_t i = 0; i < pending.load_count; ++i) {
    const Load& load = pending.loads[i];
    switch (load.kind) {
      case kLoadLiteral:
        if (uint32_t* payload =
                writer.Entry(d3d_draw::kEntryRegistersFromMemory, load.a, 1, load.b)) {
          payload[0] = load.c;
        }
        break;
      case kLoadShader:
        if (uint32_t* payload = writer.Entry(d3d_draw::kEntryShader, load.a, 2, 2)) {
          payload[0] = load.b;
          payload[1] = load.c;
        }
        break;
      case kLoadInline: {
        // Copied now: the device patched it in place after writing it, and
        // the command buffer is reused once the decoder has passed it.
        const uint32_t dwords = load.c / 4;
        if (uint32_t* payload =
                writer.Entry(d3d_draw::kEntryShader, load.a, 2 + dwords, 2 + dwords)) {
          payload[0] = GpuAddress(load.b);
          payload[1] = dwords;
          std::memcpy(payload + 2, Guest<uint32_t>(load.b), dwords * sizeof(uint32_t));
        }
      } break;
    }
  }
  for (const RegisterGroup& group : kStateGroups) writer.Group(group, masks[2], device);
  // Fetch constants, 6 registers a bit (low 32 bits).
  writer.Blocks(masks[3] << 32, 0x4800, 6, device + kFetchShadow);
  if (fetch_flush && uint32_t(masks[3])) {
    // 0x82415D50 ends with 0x5000-0x5002 = 0, 0x25000, 0 (verified in the
    // decoder, DL-2.1 verify).
    if (uint32_t* payload = writer.Entry(d3d_draw::kEntryRegisters, 0x5000, 3, 3)) {
      payload[0] = 0;
      payload[1] = rex::byte_swap(uint32_t(0x00025000));
      payload[2] = 0;
    }
  }
  writer.Group(kFetchGroup2280, masks[3], device);
  writer.Group(kMiscGroup2380, masks[4], device);
  // Clip planes, 4 registers a bit (mask bits 54-49).
  for (uint32_t plane = 0; plane < 6; ++plane) {
    if ((masks[4] >> (54 - plane)) & 1) {
      writer.Run(0x2388 + plane * 4, 4, device + kClipPlaneShadow + plane * 16);
    }
  }
  // Bool and loop constants, together (bit 56).
  if ((masks[4] >> 56) & 1) writer.Run(0x4900, 40, device + kBoolLoopShadow);
  writer.Group(kMiscGroup2300, masks[4], device);
  // VGT_INDX_OFFSET, written by the call itself.
  if (uint32_t* payload = writer.Entry(d3d_draw::kEntryRegisters, 0x2102, 1, 1)) {
    payload[0] = rex::byte_swap(pending.base_vertex);
  }
}

// The draw packet's viz query word: a byte index at +12563 into a table at
// +12498.
uint32_t VizWord(uint32_t device) {
  const uint8_t viz_index = Load8(device + kVizIndex);
  return (uint32_t(Load8(device + kVizTable + viz_index)) | (viz_index ? 0x100u : 0u)) & 0x13Fu;
}

// The indexed call's draw packet (0x82416380), a predicated DRAW_INDX of
// four words: viz query word, initiator, index base and size.
void DescribeIndexedDraw(const Pending& pending, uint32_t device,
                         d3d_draw::Description& description) {
  const uint32_t index_buffer = Load32(device + kIndexBuffer);
  const uint32_t ib_flags = Load32(index_buffer);
  const uint32_t ib_base = Load32(index_buffer + 24);
  const bool index32 = (ib_flags & 0x80000000u) != 0;
  const uint32_t endian = (ib_flags << 1) & 0xC0000000u;
  description.draw[0] = VizWord(device);
  description.draw[1] = (pending.count << 16) | pending.prim | (index32 ? 0x800u : 0u);
  description.draw[2] = GpuAddress(ib_base + pending.start * (index32 ? 4 : 2));
  description.draw[3] =
      (index32 ? ((pending.count << 1) & 0x00FFFFFEu) : (pending.count & 0x00FFFFFFu)) | endian;
  description.packet = 0xC0032201u;
}

void Describe(Pending& pending, d3d_draw::Description& description) {
  const uint32_t device = pending.device;
  description.flags = 0;
  description.word_count = 0;
  const uint32_t scope = uint32_t(REXCVAR_GET(pinyon_shift_d3d_draw_scope));
  if (scope == 0 && ((Load32(device + kColorInfoShadow) >> 16) & 0xF) != 10) {
    description.flags = d3d_draw::kFlagDeclined;
    return;
  }
  if (pending.overflow) {
    description.flags = d3d_draw::kFlagOverflow;
    return;
  }
  Writer writer(description);
  DescribeFlush(pending, device, writer, false);
  DescribeIndexedDraw(pending, device, description);
  if (writer.overflow()) {
    description.flags = d3d_draw::kFlagOverflow;
    description.word_count = 0;
  }
}

// --- DL-2.1 slice: replaced draw calls ---

enum SliceReason : uint32_t {
  kSliceRecording,
  kSliceQuery,
  kSliceBind,
  kSlicePerTile,
  kSliceClip,
  kSliceWait,
  kSliceCount,
  kSliceSpace,
  kSliceOverflow,
  kSliceArena,
  kSliceReasonCount,
};
constexpr const char* kSliceReasonName[] = {"recording",   "query",    "shader bind",
                                            "per-tile",    "clip",     "wait",
                                            "count",       "no space", "overflow",
                                            "arena full"};

struct SliceStats {
  // By entry: 0 the indexed call, 1 the auto-index call.
  std::atomic<uint64_t> calls[2] = {}, taken[2] = {};
  std::atomic<uint64_t> words{0};
  std::atomic<uint64_t> not_taken[2][kSliceReasonCount] = {};
};
SliceStats g_slice;

// The call at entry `entry` (0: 0x82416380, r4 primitive, r5 base vertex, r6
// start index, r7 index count; 1: 0x82415F68, r4 primitive, r5 start vertex,
// r6 vertex count). True if the call was replaced: the hook then returns
// from the call at once.
bool SliceCall(uint32_t entry, uint32_t mode, uint32_t device, uint32_t prim,
               uint32_t base_vertex, uint32_t start, uint32_t count) {
  SliceStats& stats = g_slice;
  stats.calls[entry].fetch_add(1, std::memory_order_relaxed);
  auto decline = [&](SliceReason reason) {
    stats.not_taken[entry][reason].fetch_add(1, std::memory_order_relaxed);
    return false;
  };
  const uint8_t record_flags = Load8(device + kRecordFlags);
  // Recorded calls stay: a command buffer's fixups point into its packets.
  if (record_flags & 0x80) return decline(kSliceRecording);
  if (record_flags & 0x01) return decline(kSliceQuery);
  Pending& pending = t_pending;
  pending.active = false;
  pending.masks[0] = Load64(device + kMaskVsConstants);
  pending.masks[1] = Load64(device + kMaskPsConstants);
  pending.masks[2] = Load64(device + kMaskState);
  pending.masks[3] = Load64(device + kMaskFetch);
  pending.masks[4] = Load64(device + kMaskMisc);
  // The flushes that do more than write registers from the shadows stay with
  // the guest call: the shader bind (+16 bits 17-20), the per-tile state, the
  // clip planes (with a coherency wait; +32 bits 49-54) and the wait (+32 bits
  // 62-63 with a wait flag set).
  if (pending.masks[2] & 0x1E0000u) return decline(kSliceBind);
  if (Load64(device + kMaskPerTile) & pending.masks[2]) return decline(kSlicePerTile);
  if (pending.masks[4] & (uint64_t(0x3F) << 49)) return decline(kSliceClip);
  if ((pending.masks[4] >> 62) && (Load8(device + kWaitFlags) & 0xC0)) {
    return decline(kSliceWait);
  }
  // The calls split counts over 65535.
  if (!count || count > 65535) return decline(kSliceCount);
  const uint32_t write = Load32(device + kWritePointer);
  if (write + 16 > Load32(device + kSegmentLimit)) return decline(kSliceSpace);

  d3d_draw::Description& description = t_description;
  description.id = d3d_draw::NextId() & 0x3FFFFFFFu;
  if (!description.id) description.id = 1;
  description.flags = 0;
  description.word_count = 0;
  pending.device = device;
  pending.prim = prim & 63;
  pending.base_vertex = base_vertex;
  pending.start = start;
  pending.count = count;
  pending.load_count = 0;
  pending.overflow = false;
  Writer writer(description);
  DescribeFlush(pending, device, writer, true);
  if (entry == 0) {
    DescribeIndexedDraw(pending, device, description);
  } else {
    // An auto-index, predicated DRAW_INDX of two words (0x82415F68).
    description.flags = d3d_draw::kFlagAutoIndex;
    description.draw[0] = VizWord(device);
    description.draw[1] = (count << 16) | pending.prim | 0x80u;
    description.draw[2] = description.draw[3] = 0;
    description.packet = 0xC0012201u;
  }
  if (writer.overflow()) return decline(kSliceOverflow);
  const uint32_t offset = d3d_draw::PublishArena(description);
  if (!offset) return decline(kSliceArena);
  // The marker, where the call's packets would start.
  Store32(write + 4, d3d_draw::kMarkerHeader);
  Store32(write + 8, d3d_draw::kReplaceMagic);
  Store32(write + 12, offset - 1);
  Store32(write + 16, (description.id << 2) | mode);
  Store32(device + kWritePointer, write + 16);
  stats.taken[entry].fetch_add(1, std::memory_order_relaxed);
  stats.words.fetch_add(description.word_count, std::memory_order_relaxed);
  if (mode != d3d_draw::kSliceOn) return false;
  // Replaced. The call's flushes store 0 into each non-zero mask; on this path
  // nothing else of the device changes but the write pointer.
  for (uint32_t mask = kMaskVsConstants; mask <= kMaskMisc; mask += 8) Store64(device + mask, 0);
  return true;
}

void SliceLog() {
  SliceStats& stats = g_slice;
  const uint64_t calls0 = stats.calls[0].exchange(0, std::memory_order_relaxed);
  const uint64_t calls1 = stats.calls[1].exchange(0, std::memory_order_relaxed);
  if (!calls0 && !calls1) return;
  std::string reasons;
  for (uint32_t entry = 0; entry < 2; ++entry) {
    reasons += entry ? "; auto-index:" : " indexed:";
    for (uint32_t r = 0; r < kSliceReasonCount; ++r) {
      const uint64_t n = stats.not_taken[entry][r].exchange(0, std::memory_order_relaxed);
      if (n) reasons += fmt::format(" {} {},", kSliceReasonName[r], n);
    }
  }
  const uint64_t taken0 = stats.taken[0].exchange(0, std::memory_order_relaxed);
  const uint64_t taken1 = stats.taken[1].exchange(0, std::memory_order_relaxed);
  const uint64_t words = stats.words.exchange(0, std::memory_order_relaxed);
  REXLOG_INFO(
      "D3D slice DL-2.1 (600 frames): indexed calls {} taken {}, auto-index calls {} taken {}, "
      "{:.1f} words a description; not taken by reason:{}",
      calls0, taken0, calls1, taken1,
      (taken0 + taken1) ? double(words) / double(taken0 + taken1) : 0.0, reasons);
}

}  // namespace

void D3dDrawFrame() {
  // DL-2.1: the slice mode for the next frame (the decoder reads it at its
  // swaps), and the frame that arena descriptions are tagged with.
  d3d_draw::SetSliceMode(uint32_t(REXCVAR_GET(pinyon_shift_d3d_slice)));
  d3d_draw::GuestFrame();
  if (++g_frames < 600) return;
  g_frames = 0;
  SliceLog();
  const uint64_t calls = g_stats.calls.exchange(0, std::memory_order_relaxed);
  if (!calls) return;
  REXLOG_INFO(
      "D3D draw DL-1.2 (600 frames): {} indexed calls, {} markers, {} published, {} declined, "
      "{} overflow; not taken: {} not the HUD target, {} no space, {} too long; "
      "recording/tiled path/predicated/tiling: {}/{}/{}/{}; HUD-format calls at entry {}, of "
      "them recording/tiled path/predicated/tiling: {}/{}/{}/{} (recording counts taken "
      "calls too)",
      calls, g_stats.markers.exchange(0, std::memory_order_relaxed),
      g_stats.published.exchange(0, std::memory_order_relaxed),
      g_stats.declined.exchange(0, std::memory_order_relaxed),
      g_stats.overflow.exchange(0, std::memory_order_relaxed),
      g_stats.not_hud.exchange(0, std::memory_order_relaxed),
      g_stats.no_space.exchange(0, std::memory_order_relaxed),
      g_stats.too_long.exchange(0, std::memory_order_relaxed),
      g_stats.not_ring[0].exchange(0, std::memory_order_relaxed),
      g_stats.not_ring[1].exchange(0, std::memory_order_relaxed),
      g_stats.not_ring[2].exchange(0, std::memory_order_relaxed),
      g_stats.not_ring[3].exchange(0, std::memory_order_relaxed),
      g_stats.hud_calls.exchange(0, std::memory_order_relaxed),
      g_stats.hud_not_ring[0].exchange(0, std::memory_order_relaxed),
      g_stats.hud_not_ring[1].exchange(0, std::memory_order_relaxed),
      g_stats.hud_not_ring[2].exchange(0, std::memory_order_relaxed),
      g_stats.hud_not_ring[3].exchange(0, std::memory_order_relaxed));
}

}  // namespace pinyon_shift::native_renderer

// --- Mid-asm hooks (config/rexglue/analysis/main-xex.toml, "DL-1.2 D3D-level
// draws"). Each returns at once while pinyon_shift_d3d_draw is 0. ---

namespace d3d_draw_impl = pinyon_shift::native_renderer;
using d3d_draw_impl::t_pending;

// 0x82415F68, the auto-index draw call (r3 the device, r4 the primitive, r5
// the start vertex, r6 the vertex count). Shared with the D3D census's draw
// entry 1. True: the DL-2.1 slice replaced the call, which returns at once.
bool PinyonShiftD3dCensusDraw1(PPCRegister& r1, PPCRegister& r3, PPCRegister& r4,
                               PPCRegister& r5, PPCRegister& r6, uint64_t& lr) {
  pinyon_shift::native_renderer::D3dCensusDrawEntry(1, r1.u32, r3.u32, uint32_t(lr));
  const uint32_t slice = rex::system::d3d_draw::GetSliceMode();
  return slice && d3d_draw_impl::SliceCall(1, slice, r3.u32, r4.u32, r5.u32, 0, r6.u32);
}

// 0x82416380, the indexed draw call (r3 the device, r4 the primitive, r5 the
// base vertex, r6 the start index, r7 the index count). Shared with the D3D
// census's draw entry 0. True: the DL-2.1 slice replaced the call, which
// returns at once.
bool PinyonShiftD3dCensusDraw0(PPCRegister& r1, PPCRegister& r3, PPCRegister& r4,
                               PPCRegister& r5, PPCRegister& r6, PPCRegister& r7, uint64_t& lr) {
  pinyon_shift::native_renderer::D3dCensusDrawEntry(0, r1.u32, r3.u32, uint32_t(lr));
  if (const uint32_t slice = rex::system::d3d_draw::GetSliceMode()) {
    d3d_draw_impl::t_pending.active = false;
    if (d3d_draw_impl::SliceCall(0, slice, r3.u32, r4.u32, r5.u32, r6.u32, r7.u32)) return true;
    // Verify, or a call the slice declined: as without the slice. A verified
    // call has a slice marker; DL-1.2 does not describe it as well.
    if (slice == rex::system::d3d_draw::kSliceVerify) return false;
  }
  const int32_t mode = REXCVAR_GET(pinyon_shift_d3d_draw);
  if (!mode) return false;
  using namespace d3d_draw_impl;
  auto& stats = d3d_draw_impl::g_stats;
  stats.calls.fetch_add(1, std::memory_order_relaxed);
  const uint32_t device = r3.u32;
  t_pending.active = false;
  const uint8_t record_flags = Load8(device + kRecordFlags);
  const bool reasons[4] = {(record_flags & 0x80) != 0, (record_flags & 0x40) != 0,
                           (record_flags & 0x01) != 0, Load32(device + kTilingState) != 0};
  const bool hud = ((Load32(device + kColorInfoShadow) >> 16) & 0xF) == 10;
  if (hud) stats.hud_calls.fetch_add(1, std::memory_order_relaxed);
  // Recording is fine: the marker and the packets go into the command buffer
  // together and the decoder meets them when the buffer runs.
  // But a recorded list can be patched between recording and its runs (verify
  // with scope 1 saw VGT_INDX_OFFSET changed once a frame), which a
  // description taken at recording cannot follow: outside the HUD scope,
  // whose recorded draws verify clean, recorded calls are only verified.
  const bool recorded_unsafe = reasons[0] && mode == 2 &&
                               REXCVAR_GET(pinyon_shift_d3d_draw_scope) != 0;
  if (reasons[1] || reasons[2] || reasons[3] || recorded_unsafe) {
    for (uint32_t i = 0; i < 4; ++i) {
      if (!reasons[i]) continue;
      stats.not_ring[i].fetch_add(1, std::memory_order_relaxed);
      if (hud) stats.hud_not_ring[i].fetch_add(1, std::memory_order_relaxed);
    }
    return false;
  }
  // The HUD scope by the target at entry (the exit check stays: the bind can
  // change it): no marker, so no description slot, for other draws.
  if (REXCVAR_GET(pinyon_shift_d3d_draw_scope) == 0 && !hud) {
    stats.not_hud.fetch_add(1, std::memory_order_relaxed);
    return false;
  }
  const uint32_t count = r7.u32;
  if (!count || count > 65535) {
    stats.too_long.fetch_add(1, std::memory_order_relaxed);
    return false;
  }
  const uint32_t write = Load32(device + kWritePointer);
  if (write + 16 > Load32(device + kSegmentLimit)) {
    stats.no_space.fetch_add(1, std::memory_order_relaxed);
    return false;
  }
  Pending& pending = t_pending;
  pending.active = true;
  pending.overflow = false;
  pending.device = device;
  pending.id = rex::system::d3d_draw::NextId();
  pending.prim = r4.u32 & 63;
  pending.base_vertex = r5.u32;
  pending.start = r6.u32;
  pending.count = count;
  pending.masks[0] = Load64(device + kMaskVsConstants);
  pending.masks[1] = Load64(device + kMaskPsConstants);
  pending.masks[2] = 0;  // the state mask after the bind (see the next hook)
  pending.masks[3] = Load64(device + kMaskFetch);
  pending.masks[4] = Load64(device + kMaskMisc);
  pending.load_count = 0;
  // The marker: a NOP before the call's own packets.
  Store32(write + 4, rex::system::d3d_draw::kMarkerHeader);
  Store32(write + 8, rex::system::d3d_draw::kMarkerMagic);
  Store32(write + 12, pending.id);
  Store32(write + 16, uint32_t(mode));
  Store32(device + kWritePointer, write + 16);
  stats.markers.fetch_add(1, std::memory_order_relaxed);
  if (reasons[0]) {
    stats.not_ring[0].fetch_add(1, std::memory_order_relaxed);
    if (hud) stats.hud_not_ring[0].fetch_add(1, std::memory_order_relaxed);
  }
  return false;
}

// 0x82416438, after the shader bind and the per-tile state: r30 the state
// mask the call flushes (the bind adds bits).
void PinyonShiftD3dDrawStateMask(PPCRegister& r30, PPCRegister& r31) {
  if (t_pending.active && t_pending.device == r31.u32) t_pending.masks[2] = r30.u64;
}

// 0x82411BD0, a shader's literal constant loads (r3 the device, r4 the
// table, r5 the microcode base): entries of a constant index, a dword count
// and an offset from the base, ended by a zero count.
void PinyonShiftD3dDrawLiterals(PPCRegister& r3, PPCRegister& r4, PPCRegister& r5) {
  if (!t_pending.active || t_pending.device != r3.u32) return;
  using namespace d3d_draw_impl;
  const uint32_t table = r4.u32;
  const uint32_t offset = Load32(table + 20);
  if (!offset) return;
  const uint32_t header = table + offset;
  uint32_t entry = header + 20;
  const uint32_t end = entry + Load32(header + 16);
  for (; entry < end; entry += 8) {
    const uint32_t index = Load16(entry);
    const uint32_t count = Load16(entry + 2);
    if (!count) break;
    AddLoad(kLoadLiteral, 0x4000 + index * 4, count, GpuAddress(Load32(entry + 4) + r5.u32));
  }
}

// 0x82411EBC, the bind wrote the pixel shader's IM_LOAD (r29 the pixel
// shader, r31 the device).
void PinyonShiftD3dDrawPixelShaderLoad(PPCRegister& r29, PPCRegister& r31) {
  if (!t_pending.active || t_pending.device != r31.u32) return;
  using namespace d3d_draw_impl;
  const uint32_t shader = r29.u32;
  const uint32_t program = shader + Load32(shader + 64);
  AddLoad(kLoadShader, 1, GpuAddress(Load32(program + 40) + Load32(shader + 24)),
          Load32(program + 44) >> 2);
}

// 0x824125F0, the bind wrote the vertex shader's IM_LOAD on the untiled path
// (r15 the variant, r30 the vertex shader, r31 the device).
void PinyonShiftD3dDrawVertexShaderLoad(PPCRegister& r15, PPCRegister& r30, PPCRegister& r31) {
  if (!t_pending.active || t_pending.device != r31.u32) return;
  using namespace d3d_draw_impl;
  const uint32_t shader = r30.u32;
  const uint32_t variant = shader + Load32(shader + 896 + 8 * r15.u32);
  AddLoad(kLoadShader, 0, GpuAddress(Load32(variant + 872) + Load32(shader + 32)),
          Load32(variant + 876) >> 2);
}

// 0x8240D348, a vertex shader variant built in the command buffer: r26 its
// microcode there, r27 its bytes, r30 the device (an IM_LOAD_IMMEDIATE).
void PinyonShiftD3dDrawVertexShaderInline(PPCRegister& r26, PPCRegister& r27, PPCRegister& r30) {
  if (!t_pending.active || t_pending.device != r30.u32) return;
  d3d_draw_impl::AddLoad(d3d_draw_impl::kLoadInline, 0, r26.u32, r27.u32);
}

// 0x824167EC, the draw call's exit (r31 the device).
void PinyonShiftD3dDrawExit(PPCRegister& r31) {
  if (!t_pending.active || t_pending.device != r31.u32) return;
  using namespace d3d_draw_impl;
  Pending& pending = t_pending;
  pending.active = false;
  rex::system::d3d_draw::Description& description = t_description;
  description.id = pending.id;
  Describe(pending, description);
  if (description.flags & rex::system::d3d_draw::kFlagDeclined) {
    g_stats.declined.fetch_add(1, std::memory_order_relaxed);
  } else if (description.flags & rex::system::d3d_draw::kFlagOverflow) {
    g_stats.overflow.fetch_add(1, std::memory_order_relaxed);
  } else {
    g_stats.published.fetch_add(1, std::memory_order_relaxed);
  }
  rex::system::d3d_draw::Publish(description);
}
