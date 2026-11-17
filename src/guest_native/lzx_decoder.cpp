// Native replacement of the title's LZX block decoder (#431).
//
// sub_830F2210 (v4 sub_831B4090) decodes LZX symbols into the window until
// `count` bytes are written: a 10-bit main-tree table with an overflow tree,
// literals, matches with a length tree, position slots with verbatim and
// aligned-offset extra bits, the three repeated offsets, and window copies
// in 16-byte chunks. It runs on the streaming worker threads and took a fifth
// of one in races on desktop and the Odin: the recompiled loop keeps every
// register in the context. This port keeps the decoder state in locals and
// writes guest memory exactly as the original does, including the chunked
// copy's 16-byte loads and stores and the masked final store.
//
// Decoder state (r3), as the function uses it:
//   +0 window, +8 window mask, +12/+16/+20 repeated offsets R0-R2,
//   +24 main-tree table (1,024 16-bit entries for the top 10 bits),
//   +2072 length-tree table (256 entries), +2584 main-tree code lengths,
//   +3256 length-tree code lengths, +3508 aligned-offset table (128 bytes),
//   +3636 aligned-offset code lengths, +3644 / +9020 main / length overflow
//   trees, +11012 input pointer, +11016 input end, +11952 bit buffer,
//   +11956 bits left (signed byte), +11960 window position on return,
//   +12004 extra bits per position slot, +12056 position slot bases.
// Arguments: r4 window position, r5 bytes to decode. Returns r3 = bytes
// decoded past the request, or -1 when the input ran out (state not saved).

#include <algorithm>
#include <bit>
#include <cstdint>
#include <cstring>

#include <rex/perf/counter.h>
#include <rex/cvar.h>
#include <rex/ppc/context.h>
#include <rex/system/xmemory.h>

#include "fh1_guest_address.h"
#include "guest_native/guest_native.h"

REXCVAR_DEFINE_BOOL(pinyon_shift_native_lzx_decoder, true, "Pinyon Shift",
                    "Run the title's LZX block decoder (streaming workers) as native code "
                    "(#431)")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

namespace pinyon_shift::guest_native {
namespace {

// The final copy's byte-select constant.
constexpr uint32_t kCopyMask = pinyon_shift::fh1::kTitleUpdateV4 ? 0x822E8480u : 0x822D5360u;

// Guest memory. Flat: every address this call touches has the same physical
// view offset, already folded into `base`.
template <bool Flat>
struct Memory {
  uint8_t* base;
  static bool SameView(uint32_t a, uint32_t b) {
    return rex::memory::detail::PhysicalHostOffset(a) ==
           rex::memory::detail::PhysicalHostOffset(b);
  }
  uint8_t* host(uint32_t address) const {
    if constexpr (Flat) return base + address;
    return base + address + rex::memory::detail::PhysicalHostOffset(address);
  }
  uint32_t u8(uint32_t address) const { return *host(address); }
  int32_t s16(uint32_t address) const {
    uint16_t value;
    std::memcpy(&value, host(address), 2);
    return static_cast<int16_t>(std::byteswap(value));
  }
  uint32_t u32(uint32_t address) const {
    uint32_t value;
    std::memcpy(&value, host(address), 4);
    return std::byteswap(value);
  }
  void store8(uint32_t address, uint32_t value) const {
    *host(address) = static_cast<uint8_t>(value);
  }
  void store32(uint32_t address, uint32_t value) const {
    const uint32_t swapped = std::byteswap(value);
    std::memcpy(host(address), &swapped, 4);
  }
  // An unaligned 16-byte access may straddle the 0xE0000000 boundary only in
  // theory; byte by byte keeps the per-byte translation exact.
  void load16(uint32_t address, uint8_t* out) const {
    if (Flat || SameView(address, address + 15)) {
      std::memcpy(out, host(address), 16);
    } else {
      for (uint32_t i = 0; i < 16; ++i) out[i] = *host(address + i);
    }
  }
  void store16(uint32_t address, const uint8_t* in) const {
    if (Flat || SameView(address, address + 15)) {
      std::memcpy(host(address), in, 16);
    } else {
      for (uint32_t i = 0; i < 16; ++i) *host(address + i) = in[i];
    }
  }
};

uint32_t Slw(uint32_t value, uint32_t amount) {
  return (amount & 0x20) ? 0 : value << (amount & 0x1F);
}
uint32_t Srw(uint32_t value, uint32_t amount) {
  return (amount & 0x20) ? 0 : value >> (amount & 0x1F);
}
int32_t Extsb(int32_t value) { return static_cast<int8_t>(value); }

template <bool Flat>
struct Decoder {
  const Memory<Flat>& m;
  uint32_t state;
  uint32_t input;      // r30
  uint32_t bits;       // r10
  int32_t bits_left;   // r8

  // Consumes `length` bits and refills 16 when the count drops to zero or
  // below, as each of the original's refill sites does.
  void Consume(uint32_t length) {
    bits_left = Extsb(bits_left - static_cast<int32_t>(length));
    bits = Slw(bits, length);
    if (bits_left > 0) return;
    const uint32_t word = (m.u8(input + 1) << 8) | m.u8(input);
    const uint32_t shift = static_cast<uint32_t>(-bits_left);
    input += 2;
    bits_left = Extsb(bits_left + 16);
    bits |= Slw(word, shift);
  }

  // Walks an overflow tree from a negative table entry.
  int32_t Walk(int32_t entry, uint32_t bit, uint32_t tree) const {
    while (entry < 0) {
      const uint32_t set = (bit & bits) ? 1u : 0u;
      bit >>= 1;
      const uint32_t index = set - (static_cast<uint32_t>(entry) << 1);
      entry = m.s16(tree + ((index << 1) & ~1u));
    }
    return entry;
  }
};

template <bool Flat>
void Decode(PPCContext& ctx, const Memory<Flat>& m, const uint8_t* select) {
  const uint32_t s = ctx.r3.u32;
  uint64_t position = ctx.r4.u64;
  const uint64_t end = ctx.r4.u64 + ctx.r5.u64;
  const uint32_t input_end = m.u32(s + 11016);
  const uint32_t window = m.u32(s + 0);
  Decoder<Flat> d{m, s, m.u32(s + 11012), m.u32(s + 11952),
                  static_cast<int32_t>(m.u8(s + 11956))};
  const uint32_t repeats = s + 12;

  while (static_cast<int32_t>(position) < static_cast<int32_t>(end)) {
    int32_t symbol = m.s16(s + 24 + ((d.bits >> 22) << 1));
    symbol = d.Walk(symbol, 0x00200000, s + 3644);
    if (d.input >= input_end) {
      ctx.r3.u64 = ~0ull;
      return;
    }
    d.Consume(m.u8(s + 2584 + symbol));
    const int32_t match = symbol - 256;
    if (match < 0) {
      m.store8(window + static_cast<uint32_t>(position), static_cast<uint32_t>(match));
      position += 1;
      continue;
    }
    int32_t length_header = match & 7;
    if (length_header == 7) {
      int32_t length = m.s16(s + 2072 + ((d.bits >> 24) << 1));
      length = d.Walk(length, 0x00800000, s + 9020);
      d.Consume(m.u8(s + 3256 + length));
      length_header = length + 7;
    }
    const int32_t slot = Extsb(match >> 3);
    uint32_t offset;
    if (slot <= 2) {
      const uint32_t r0 = m.u32(repeats);
      offset = m.u32(repeats + static_cast<uint32_t>(slot) * 4);
      m.store32(repeats + static_cast<uint32_t>(slot) * 4, r0);
    } else {
      const uint32_t slot_base_address = s + static_cast<uint32_t>(slot + 3014) * 4;
      const uint32_t extra = m.u8(s + 12004 + static_cast<uint32_t>(slot));
      if (extra >= 3) {
        uint32_t verbatim = 0;
        if (extra != 3) {
          verbatim = Srw(d.bits, 35 - extra);
          d.bits_left = Extsb(Extsb(d.bits_left) - static_cast<int32_t>(extra) + 3);
          d.bits = Slw(d.bits, extra - 3);
          if (d.bits_left <= 0) d.Consume(0);
        }
        const int32_t aligned = static_cast<int8_t>(m.u8(s + 3508 + (d.bits >> 25)));
        const uint32_t slot_base = m.u32(slot_base_address);
        d.Consume(m.u8(s + 3636 + static_cast<uint32_t>(aligned)));
        offset = slot_base + (verbatim << 3) + static_cast<uint32_t>(aligned);
      } else if (extra != 0) {
        const uint32_t verbatim = Srw(d.bits, 32 - extra);
        d.Consume(extra);
        offset = m.u32(slot_base_address) + verbatim;
      } else {
        offset = m.u32(slot_base_address);
      }
      m.store32(repeats + 8, m.u32(repeats + 4));
      m.store32(repeats + 4, m.u32(repeats));
    }
    const uint32_t mask = m.u32(s + 8);
    m.store32(repeats, offset);
    uint32_t length = static_cast<uint32_t>(length_header + 2);
    uint32_t source = (static_cast<uint32_t>(position) - offset) & mask;
    const uint32_t distance = static_cast<uint32_t>(position) - source;
    if (distance < length && distance < 16) {
      for (; length; --length) {
        m.store8(window + static_cast<uint32_t>(position), m.u8(window + source));
        ++source;
        ++position;
      }
      continue;
    }
    uint8_t chunk[16];
    if (static_cast<int32_t>(length) > 16) {
      const uint32_t chunks = ((length - 17) >> 4) + 1;
      for (uint32_t i = 0; i < chunks; ++i) {
        m.load16(window + source, chunk);
        m.store16(window + static_cast<uint32_t>(position), chunk);
        source += 16;
        position += 16;
      }
      length -= chunks * 16;
    }
    // The last 1-16 bytes: a 16-byte store that keeps the destination's own
    // bytes where the select constant says so.
    uint8_t destination[16];
    m.load16(window + source, chunk);
    m.load16(window + static_cast<uint32_t>(position), destination);
    const uint32_t shift = (length - 1) & 15;
    for (uint32_t i = 0; i < 16; ++i) {
      const uint8_t permute = static_cast<uint8_t>(16 - shift + i);
      if (select[i] > permute) destination[i] = chunk[i];
    }
    m.store16(window + static_cast<uint32_t>(position), destination);
    position += length;
  }
  m.store8(s + 11956, static_cast<uint32_t>(d.bits_left));
  m.store32(s + 11952, d.bits);
  m.store32(s + 11012, d.input);
  m.store32(s + 11960, m.u32(s + 8) & static_cast<uint32_t>(position));
  ctx.r3.u64 = position - end;
}

// The state object (tables up to the position-slot bases), the window up to
// the longest overshoot past the request, and the input with its refill.
constexpr uint32_t kStateSize = 12056 + 64 * 4;

bool NativeDecode(PPCContext& ctx, uint8_t* base) {
  rex::perf::ScopedCounterNs census(rex::perf::CounterId::kTitleLzxNs,
                                    rex::perf::CounterId::kTitleLzxCalls);
  const Memory<false> m{base};
  uint8_t select[16];
  m.load16(kCopyMask, select);
  const uint32_t s = ctx.r3.u32;
  const uint32_t window = m.u32(s);
  const uint32_t window_end =
      window + std::max(m.u32(s + 8) + 1 + 16, ctx.r4.u32 + ctx.r5.u32 + 257 + 16);
  const uint32_t input = m.u32(s + 11012);
  const uint32_t input_end = m.u32(s + 11016) + 2;
  const uint32_t offset = rex::memory::detail::PhysicalHostOffset(s);
  using M = Memory<false>;
  if (M::SameView(s, s + kStateSize) && M::SameView(s, window) &&
      M::SameView(s, window_end) && M::SameView(s, input) && M::SameView(s, input_end) &&
      window_end > window && input_end > input) {
    Decode(ctx, Memory<true>{base + offset}, select);
  } else {
    Decode(ctx, m, select);
  }
  return true;
}

// For verify mode: the window from the start position to the longest
// overshoot (a 257-byte match and a 16-byte final store), the repeated
// offsets and the input/bit state.
size_t DecoderWrites(const PPCContext& ctx, uint8_t* base, GuestRange* ranges) {
  const Memory<false> m{base};
  const uint32_t s = ctx.r3.u32;
  ranges[0] = {m.u32(s) + ctx.r4.u32, ctx.r5.u32 + 257 + 16};
  ranges[1] = {s + 12, 12};
  ranges[2] = {s + 11012, 11964 - 11012};
  return 3;
}

bool DecoderEnabled() { return REXCVAR_GET(pinyon_shift_native_lzx_decoder); }

Replacement lzx_decoder_replacement = {
    .name = "lzx.decode",
    .guest_address = pinyon_shift::fh1::kTitleUpdateV4 ? 0x831B4090u : 0x830F2210u,
    .guest_code_size = 1068,
    .guest_code_fnv1a = pinyon_shift::fh1::kTitleUpdateV4 ? 0x5585AE27357C0B90ull : 0xBCA488A38A5F9C6Eull,
    .returns = kReturnR3,
    .enabled = DecoderEnabled,
    .native = NativeDecode,
    .written = DecoderWrites,
};

}  // namespace
}  // namespace pinyon_shift::guest_native

PINYON_GUEST_NATIVE(830F2210, 831B4090, ::pinyon_shift::guest_native::lzx_decoder_replacement)
