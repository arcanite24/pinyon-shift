// Per-draw pass culling on the render thread (#1071 P2).
//
// For every model part the scene walk submits (sub_82440CF8, below the
// free-roam walk sub_82D65608 and the track presentation), the renderer
// runs base sub_824400B0 (v4 sub_824701B8) once per mesh: r3 the
// renderer, r4 the draw item, r5 the item's pass list. For each pass id in
// the list (shadow cascades 0-5, the light passes 6-8, the views 9-14,
// passes 15 and up, and 24, the light-shadow pass) it decides from the
// item's flags, its bounding sphere and box, the pass's frustum planes, a
// distance-based LOD choice and the cascades' extents whether the item
// draws in that pass, and if so appends a 20-byte draw record to one or more
// of the pass's five buckets (std::vector-like, begin/end/capacity) at
// [renderer+13844] + (pass * 5 + bucket) * 16. For the light-shadow pass it
// also widens each cascade's depth range by the box's corners. It returns
// whether any pass took the item. On the Deck it is about 10 % of the render
// thread, most of it the translated code's own overhead (registers and
// condition codes in memory, a stack frame per helper).
//
// The native version computes the same decisions in host floats, first
// without side effects (the pushes and depth ranges are planned), then
// writes them. It hands the call back to the original when a bucket would
// have to grow or the plan does not fit, before writing anything. Rare
// guest helpers (the pass-9 probe selection sub_8243FA20 and two virtual
// queries) are called as guest code during planning. Written from our own
// analysis of what the code reads and writes (docs/LEGAL.md); see the
// rendering page's "per-draw pass culling" record.
//
// The procedural models (CProceduralModels: procedurally placed
// vegetation, crowds and props) cull their own instances in base sub_8243EE58 (v4 sub_8246EF60):
// per instance a box or sphere test against the pass's planes, a
// distance range, a mark of the passes it is visible in and a bucket push.
// The same cvar replaces it with a native version that runs the rare
// guest helpers (the model resolve and two virtual queries) as guest code
// and falls back to the guest push when a bucket is full.
//
// pinyon_shift_native_scene_cull turns both on (the desktop Linux default). With
// pinyon_shift_guest_native_verify=N every Nth call plans natively, runs the
// original with its bucket pushes and depth-range calls recorded, and
// compares the two.

#include <array>
#include <bit>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <string>

#include <fmt/format.h>
#include <rex/cvar.h>
#include <rex/platform.h>
#include <rex/ppc/context.h>
#include <rex/ppc/func.h>
#include <rex/system/xmemory.h>

#include "fh1_guest_address.h"
#include "guest_native/guest_native.h"
#include "pinyon_shift_diagnostics.h"

// On by default on desktop Linux, where the Deck measured it (#1071).
REXCVAR_DEFINE_BOOL(pinyon_shift_native_scene_cull, REX_PLATFORM_LINUX && !REX_PLATFORM_ANDROID,
                    "Pinyon Shift",
                    "Run the render thread's per-draw pass and procedural-model culling as "
                    "native code (#1071)")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

#if defined(PINYON_SHIFT_TITLE_UPDATE_V4) && PINYON_SHIFT_TITLE_UPDATE_V4
extern "C" REX_FUNC(__imp__sub_8246FB28);
#define PINYON_PROBE_SELECT __imp__sub_8246FB28
extern "C" REX_FUNC(__imp__sub_824715F0);
#define PINYON_BUCKET_PUSH __imp__sub_824715F0
extern "C" REX_FUNC(__imp__sub_8246F430);
#define PINYON_MODEL_RESOLVE __imp__sub_8246F430
#else
extern "C" REX_FUNC(__imp__sub_8243FA20);
#define PINYON_PROBE_SELECT __imp__sub_8243FA20
extern "C" REX_FUNC(__imp__sub_824414E8);
#define PINYON_BUCKET_PUSH __imp__sub_824414E8
extern "C" REX_FUNC(__imp__sub_8243F328);
#define PINYON_MODEL_RESOLVE __imp__sub_8243F328
#endif

namespace pinyon_shift::guest_native {
namespace {

constexpr bool kV4 = pinyon_shift::fh1::kTitleUpdateV4;
// The global holding the view-settings object (sub_82406E50) and the plane
// count of a cascade's frustum.
constexpr uint32_t kViewSettingsHolder = kV4 ? 0x835A1488u : 0x834ABB08u;
constexpr uint32_t kCascadePlaneCount = kV4 ? 0x833A45CCu : 0x832B8ADCu;

bool Enabled() { return REXCVAR_GET(pinyon_shift_native_scene_cull); }

// ---- guest memory -------------------------------------------------------

struct Mem {
  uint8_t* base;
  uint8_t* At(uint32_t a) const {
    return base + a + rex::memory::detail::PhysicalHostOffset(a);
  }
  uint32_t U32(uint32_t a) const {
    uint32_t v;
    std::memcpy(&v, At(a), 4);
    return std::byteswap(v);
  }
  int32_t S32(uint32_t a) const { return static_cast<int32_t>(U32(a)); }
  uint16_t U16(uint32_t a) const {
    uint16_t v;
    std::memcpy(&v, At(a), 2);
    return std::byteswap(v);
  }
  int16_t S16(uint32_t a) const { return static_cast<int16_t>(U16(a)); }
  uint8_t U8(uint32_t a) const { return *At(a); }
  float F32(uint32_t a) const { return std::bit_cast<float>(U32(a)); }
  void St32(uint32_t a, uint32_t v) const {
    v = std::byteswap(v);
    std::memcpy(At(a), &v, 4);
  }
  void StF32(uint32_t a, float v) const { St32(a, std::bit_cast<uint32_t>(v)); }
  void St8(uint32_t a, uint8_t v) const { *At(a) = v; }
};

struct V3 {
  float x, y, z;
};
V3 operator-(V3 a, V3 b) { return {a.x - b.x, a.y - b.y, a.z - b.z}; }
float Dot(V3 a, V3 b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
V3 LoadV3(const Mem& m, uint32_t a) { return {m.F32(a), m.F32(a + 4), m.F32(a + 8)}; }

// ---- the helpers' semantics ---------------------------------------------

// sub_8243FD70: a pass's bounding sphere against the item's (r3 the pass
// sphere: centre +0, scale +16, negative +20 means "no test", radius
// scale +24).
bool SphereTest(const Mem& m, uint32_t sphere, V3 p, float radius) {
  if (!(m.F32(sphere + 20) >= 0.0f)) return true;
  const V3 d = p - LoadV3(m, sphere);
  return m.F32(sphere + 16) * Dot(d, d) <= m.F32(sphere + 24) * radius;
}

// sub_82441048: an axis-aligned box against six planes (+0..+80, nx ny nz d,
// in a z-flipped space): 0 outside, 1 crossing, 2 inside.
int FrustumTest(const Mem& m, uint32_t planes, V3 mn, V3 mx) {
  uint32_t code = 0;
  for (uint32_t i = 0; i < 6; ++i) {
    const uint32_t p = planes + 16 * i;
    const float nx = m.F32(p), ny = m.F32(p + 4), nz = m.F32(p + 8), d = m.F32(p + 12);
    // Plane and point both carry the z flip; select the corners by the
    // flipped normal's signs.
    const float fx = nx, fy = ny, fz = -nz;
    const V3 pv = {fx >= 0 ? mx.x : mn.x, fy >= 0 ? mx.y : mn.y, fz >= 0 ? mx.z : mn.z};
    const V3 nv = {fx >= 0 ? mn.x : mx.x, fy >= 0 ? mn.y : mx.y, fz >= 0 ? mn.z : mx.z};
    const float dp = nx * pv.x + ny * pv.y + nz * -pv.z + d;
    const float dn = nx * nv.x + ny * nv.y + nz * -nv.z + d;
    if (dn > 0) code |= 3;
    if (dp >= 0) code |= 1;
  }
  return code == 3 ? 0 : code == 1 ? 1 : 2;
}

// sub_824412D0: a box (two corners) against n planes, true when it is not
// fully outside any of them.
bool PlanesTest(const Mem& m, V3 a, V3 b, uint32_t planes, uint32_t count) {
  const V3 c = {(a.x + b.x) * 0.5f, (a.y + b.y) * 0.5f, (a.z + b.z) * 0.5f};
  const V3 e = b - c;
  for (uint32_t i = 0; i < count; ++i) {
    const uint32_t p = planes + 16 * i;
    const float nx = m.F32(p), ny = m.F32(p + 4), nz = m.F32(p + 8), d = m.F32(p + 12);
    const float dist = nx * c.x + ny * c.y + nz * c.z + d;
    const float reach = std::fabs(nx) * e.x + std::fabs(ny) * e.y + std::fabs(nz) * e.z;
    if (dist - reach > 0) return false;
  }
  return true;
}

template <typename Visit>
void ForCorners(V3 a, V3 b, Visit visit) {
  for (int i = 0; i < 8; ++i) {
    visit(V3{i & 4 ? b.x : a.x, i & 2 ? b.y : a.y, i & 1 ? b.z : a.z});
  }
}

float Column(const Mem& m, uint32_t matrix, uint32_t column, V3 p) {
  return p.x * m.F32(matrix + column) + p.y * m.F32(matrix + 16 + column) +
         p.z * m.F32(matrix + 32 + column) + m.F32(matrix + 48 + column);
}

// sub_82449068: every corner of the box inside |x|, |y| <= limit of a
// cascade's projection.
bool Contained(const Mem& m, V3 a, V3 b, uint32_t matrix, float limit) {
  bool inside = true;
  ForCorners(a, b, [&](V3 p) {
    if (!inside) return;
    if (std::fabs(Column(m, matrix, 0, p)) > limit ||
        std::fabs(Column(m, matrix, 4, p)) > limit) {
      inside = false;
    }
  });
  return inside;
}

// sub_82440C10: the LOD level (0-3) by distance and whether the item has no
// mesh for it (true = culled).
bool LodCull(uint32_t flags, int32_t& level, float d2, float bias, float near, float mid,
             float far, uint8_t no_near) {
  if ((flags & 0x3800) == 0) return false;
  float b = bias >= 100.0f ? 100.0f : bias;
  b = b - 20.0f >= 0.0f ? b : 20.0f;
  const float threshold = mid - mid * 0.9375f * 0.0125f * (b - 20.0f);
  if (flags >> 31) return false;
  if (!(d2 < far)) {
    level = 3;
    return !(flags & 0x2000) || (flags & 0x4000);
  }
  if (!(d2 < threshold)) {
    level = 2;
    return !(flags & 0x2000);
  }
  if (!(d2 >= near) && no_near == 0) {
    level = 0;
    return !(flags & 0x800);
  }
  level = 1;
  return !(flags & 0x1000);
}

// The squared distance from a view position to the item's oriented box,
// zero inside (sub_8243FF70 and the transforms around it in the caller).
float DistanceToBox(const Mem& m, uint32_t item, uint32_t view) {
  if (!(m.U32(item + 12) & 0x08000000)) return 0.0f;
  const float cx = m.F32(view), cy = m.F32(view + 4), cz = m.F32(view + 8);
  // World to the item's space (+144, four rows).
  const uint32_t w = item + 144;
  const V3 local = {cx * m.F32(w) + cy * m.F32(w + 16) + cz * m.F32(w + 32) + m.F32(w + 48),
                    cx * m.F32(w + 4) + cy * m.F32(w + 20) + cz * m.F32(w + 36) + m.F32(w + 52),
                    cx * m.F32(w + 8) + cy * m.F32(w + 24) + cz * m.F32(w + 40) + m.F32(w + 56)};
  // The box (+84): rotation rows +0, +12, +24, centre +36, half extents +48.
  const uint32_t box = item + 84;
  const V3 d = local - LoadV3(m, box + 36);
  float t[3] = {Dot(LoadV3(m, box), d), Dot(LoadV3(m, box + 12), d), Dot(LoadV3(m, box + 24), d)};
  bool clamped = false;
  for (int k = 0; k < 3; ++k) {
    const float e = m.F32(box + 48 + 4 * k);
    if (!(t[k] >= -e)) {
      t[k] = -e;
      clamped = true;
    }
    if (!(t[k] <= e)) {
      t[k] = e;
      clamped = true;
    }
  }
  if (!clamped) return 0.0f;
  V3 q = LoadV3(m, box + 36);
  for (int k = 0; k < 3; ++k) {
    const V3 r = LoadV3(m, box + 12 * k);
    q = {q.x + t[k] * r.x, q.y + t[k] * r.y, q.z + t[k] * r.z};
  }
  // The item's space back to the world (+208, a 4x3 matrix).
  const uint32_t a = item + 208;
  V3 world = LoadV3(m, a + 36);
  const float s[3] = {q.x, q.y, q.z};
  for (int k = 0; k < 3; ++k) {
    const V3 r = LoadV3(m, a + 12 * k);
    world = {world.x + s[k] * r.x, world.y + s[k] * r.y, world.z + s[k] * r.z};
  }
  const V3 diff = {cx - world.x, cy - world.y, cz - world.z};
  return Dot(diff, diff);
}

// ---- the plan -------------------------------------------------------------

struct Push {
  uint32_t vector;
  uint32_t object;
  uint32_t value;
};
struct DepthRange {
  V3 a, b;
  uint32_t matrix, range;
};
constexpr size_t kMaxPushes = 192;
constexpr size_t kMaxRanges = 16;

struct Plan {
  std::array<Push, kMaxPushes> pushes;
  size_t push_count = 0;
  std::array<DepthRange, kMaxRanges> ranges;
  size_t range_count = 0;
  bool added = false;
  bool overflow = false;

  void AddPush(const Mem& m, uint32_t list, uint32_t pass, uint32_t bucket, uint32_t object,
               uint32_t value) {
    if (m.U32(object + 16) == 0) return;  // sub_82441488 skips these
    if (push_count == kMaxPushes) {
      overflow = true;
      return;
    }
    pushes[push_count++] = {list + (pass * 5 + bucket) * 16, object, value};
  }
  void AddRange(V3 a, V3 b, uint32_t matrix, uint32_t range) {
    if (range_count == kMaxRanges) {
      overflow = true;
      return;
    }
    ranges[range_count++] = {a, b, matrix, range};
  }
};

// Calls a guest function with a scratch frame below the caller's stack.
struct GuestCall {
  PPCContext& ctx;
  uint8_t* base;
  uint32_t saved_r1;
  uint32_t frame;
  GuestCall(PPCContext& c, uint8_t* b) : ctx(c), base(b), saved_r1(c.r1.u32) {
    frame = (saved_r1 - 160) & ~15u;
    Mem{base}.St32(frame, saved_r1);
    ctx.r1.u64 = frame;
  }
  ~GuestCall() { ctx.r1.u64 = saved_r1; }
  uint32_t Slot() const { return frame + 112; }
  void Indirect(uint32_t target) {
    rex::runtime::ResolveIndirectFunction(target)(ctx, base);
  }
};

uint32_t VirtualCall(PPCContext& ctx, uint8_t* base, uint32_t object, uint32_t slot_offset) {
  const Mem m{base};
  GuestCall call(ctx, base);
  ctx.r3.u64 = object;
  call.Indirect(m.U32(m.U32(object) + slot_offset));
  return ctx.r3.u32;
}

// sub_8243FDD0: the pass's sphere and frustum (or, for view 9 with probes,
// the probe selection, which writes `value`).
bool ViewTest(PPCContext& ctx, uint8_t* base, uint32_t item, uint32_t pass_desc,
              uint32_t pass_sphere, int32_t pass, uint32_t probes, int32_t probe_count,
              uint8_t probe_flag, uint32_t& value) {
  const Mem m{base};
  value = 0;
  if (!((m.U32(item + 4) >> 22) & 1)) {
    if (!SphereTest(m, pass_sphere, LoadV3(m, item + 20), m.F32(item + 16))) return false;
  }
  const V3 mn = LoadV3(m, item + 32), mx = LoadV3(m, item + 44);
  if (pass == 9 && probe_count >= 1) {
    GuestCall call(ctx, base);
    m.St32(call.Slot(), 0);
    ctx.r3.u64 = pass_desc;
    ctx.r4.u64 = probes;
    ctx.r5.s64 = probe_count;
    ctx.r6.u64 = probe_flag;
    ctx.r7.u64 = call.Slot();
    // Vector registers hold the guest's element 0 in the host's last lane.
    ctx.v1.f32[3] = mn.x, ctx.v1.f32[2] = mn.y, ctx.v1.f32[1] = mn.z;
    ctx.v1.f32[0] = m.F32(item + 44);
    ctx.v2.f32[3] = mx.x, ctx.v2.f32[2] = mx.y, ctx.v2.f32[1] = mx.z;
    ctx.v2.f32[0] = m.F32(item + 56);
    PINYON_PROBE_SELECT(ctx, base);
    value = m.U32(call.Slot());
    return ctx.r3.u32 != 0;
  }
  return FrustumTest(m, pass_desc, mn, mx) != 0;
}

// sub_824413A8: the sun cascades the box touches, stopping at the first
// that contains it or whose minimum size the box is under.
uint32_t CascadeMask(const Mem& m, uint32_t renderer, uint32_t count, V3 a, V3 b) {
  const uint32_t planes = m.U32(kCascadePlaneCount);
  uint32_t mask = 0;
  if (!count) return 0;
  const V3 h = {(b.x - a.x) * 0.5f, (b.y - a.y) * 0.5f, (b.z - a.z) * 0.5f};
  const float size = Dot(h, h);
  uint32_t c = renderer + 10240 + 240;
  for (uint32_t j = 0; j < count; ++j, c += 496) {
    if (size < m.F32(c + 200)) break;
    if (!PlanesTest(m, a, b, c, planes)) continue;
    mask |= j < 32 ? 1u << j : 0u;
    if (j == count - 1) continue;
    if (Contained(m, a, b, c - 64, m.F32(c + 240))) break;
  }
  return mask;
}

// The light-shadow pass (24): cascades of the sun shadow and of the local
// lights' shadows.
void LightShadowPass(const Mem& m, uint32_t renderer, uint32_t item, uint32_t passes, Plan& plan) {
  const uint32_t flags = m.U32(item + 4);
  const bool sun = (flags & 0x08000004) == 0x08000004;
  const bool local = (flags & 0x04000004) == 0x04000004 && !sun;
  if ((flags & 0x3800) && (sun || local)) {
    const float d2 = DistanceToBox(m, item, m.U32(passes + 152) + 144);
    float limit = (m.F32(renderer + 12176) + 1.0f) * m.F32(renderer + 12160);
    limit *= limit;
    if (d2 > limit) return;
    int32_t level = -1;
    if (LodCull(flags, level, d2, m.F32(passes + 164), m.F32(item + 56), m.F32(item + 60),
                m.F32(item + 64), m.U8(passes + 173))) {
      return;
    }
  }
  // The box in the cascades' z-flipped space.
  const V3 a = {m.F32(item + 32), m.F32(item + 36), -m.F32(item + 52)};
  const V3 b = {m.F32(item + 44), m.F32(item + 48), -m.F32(item + 40)};
  const uint32_t object = m.U32(item);
  const uint32_t sphere = renderer + ((m.U32(renderer + 36) + 253) << 5);
  const V3 centre = LoadV3(m, item + 20);
  const float radius = m.F32(item + 16);
  if (sun && SphereTest(m, sphere, centre, radius)) {
    const uint32_t count = m.U32(renderer + 12224);
    const uint32_t mask = CascadeMask(m, renderer, count, a, b);
    if (mask) {
      const uint32_t list = m.U32(renderer + 13844);
      bool ranged = false;
      for (uint32_t j = 0; j < count; ++j) {
        if (j >= 32 || !(mask & (1u << j))) continue;
        plan.AddPush(m, list, j + 24, 0, object, 0);
        const uint32_t cascade = renderer + 10288 + j * 496;
        if (m.U8(cascade + 436) == 0 && !ranged) {
          plan.AddRange(a, b, cascade, list + 2560 + j * 8);
          ranged = true;
        }
      }
      plan.added = true;
    }
  }
  if (local && SphereTest(m, sphere, centre, radius)) {
    const uint32_t list = m.U32(renderer + 13844);
    const uint32_t count = m.U32(renderer + 13840);
    for (uint32_t j = 0; j < count; ++j) {
      const uint32_t light = renderer + 12636 + j * 400;
      if (!PlanesTest(m, a, b, light - 204, 6)) continue;
      plan.AddPush(m, list, j + 28, 0, object, 0);
      if (m.U8(light) == 0) plan.AddRange(a, b, light - 396, list + 2592 + j * 8);
      if (j < count - 1 && Contained(m, a, b, light - 268, m.F32(light - 4))) return;
      plan.added = true;
    }
  }
}

bool PlanCull(PPCContext& ctx, uint8_t* base, Plan& plan) {
  const Mem m{base};
  const uint32_t renderer = ctx.r3.u32, item = ctx.r4.u32, passes = ctx.r5.u32;
  {
    const uint32_t f4 = m.U32(item + 4);
    if (m.U8(renderer + 24) == 0 && ((f4 >> 15) & 1)) return true;
    if (m.U32(m.U32(item) + 8) & 1) return true;
    if ((m.U32(item + 12) & 0xB0000000u) != 0xB0000000u) return true;
  }
  const int32_t pass_count = m.S32(passes + 156);
  const uint32_t pass_ids = m.U32(passes + 148);
  const uint32_t object = m.U32(item);
  for (int32_t i = 0; i < pass_count; ++i) {
    const int32_t pass = m.S32(pass_ids + 4 * i);
    const uint32_t flags = m.U32(item + 4);
    const bool shadow_item = (flags >> 24) & 1;
    if (pass > 5 ? shadow_item : !shadow_item) continue;
    if (((flags >> 23) & 1) && pass != 24) continue;
    if (pass == 24) {
      LightShadowPass(m, renderer, item, passes, plan);
      continue;
    }
    const uint32_t pass_desc = m.U32(passes) + pass * 192;
    const uint32_t pass_sphere = m.U32(passes + 4) + pass * 32;
    const uint8_t probe_flag = m.U8(passes + 172);
    const uint32_t list = m.U32(renderer + 13844);
    uint32_t value = 0;
    if (pass >= 15) {
      if (!((flags >> 5) & 1)) continue;
      if (!ViewTest(ctx, base, item, pass_desc, pass_sphere, pass, 0, 0, probe_flag, value)) {
        continue;
      }
      plan.AddPush(m, list, pass, 0, object, value);
      plan.added = true;
      continue;
    }
    bool keep = true;
    bool light = false;
    if (pass == 6 || pass == 7 || pass == 8) {
      light = true;
      if (!((flags >> 3) & 1)) {
        keep = (m.U32(item + 12) & 0x02000000) && !((flags >> 4) & 1);
      }
    }
    bool shadow = false;
    if (pass >= 0 && pass <= 5) {
      shadow = true;
      const float reach = m.F32(passes + 168);
      if (reach <= 0.0f) {
        keep = false;
      } else if (!((flags >> 6) & 1)) {
        const uint32_t pd = m.U32(passes) + pass * 192;
        const V3 c = {m.F32(pd + 160), m.F32(pd + 164), -m.F32(pd + 168)};
        const V3 lo = LoadV3(m, item + 32), hi = LoadV3(m, item + 44);
        const V3 q = {std::fmax(lo.x, std::fmin(hi.x, c.x)), std::fmax(lo.y, std::fmin(hi.y, c.y)),
                      std::fmax(lo.z, std::fmin(hi.z, c.z))};
        const V3 d = c - q;
        if (!(Dot(d, d) <= reach)) keep = false;
      }
    }
    int32_t level = -1;
    if ((flags & 0x3800) && keep) {
      float d2 = DistanceToBox(m, item, m.U32(passes + 152) + pass * 16);
      if ((shadow || light) && !(d2 >= m.F32(item + 60))) d2 = m.F32(item + 60);
      bool far = false;
      if (pass == 11) {
        const uint32_t settings = VirtualCall(ctx, base, m.U32(kViewSettingsHolder), 32);
        if (m.U8(settings + 4001) && m.F32(settings + 3960) < 0.99f) {
          float limit = (m.F32(renderer + 12176) + 1.0f) * m.F32(renderer + 12160);
          limit *= limit;
          far = !(d2 <= limit);
        }
      }
      if (far) {
        keep = false;
      } else {
        const uint32_t lod_flags = m.U32(item + 4);
        const uint32_t lods = lod_flags & 0x3800;
        keep = !LodCull(lod_flags, level, d2, m.F32(passes + 164), m.F32(item + 56),
                        m.F32(item + 60), m.F32(item + 64), m.U8(passes + 173));
        if (!keep && lods != 0x3800 && level < 2 && level != -1 &&
            ((((0u - lods) >> 1) & (lods >> 1)) == (1u << (level + 11)))) {
          // The coarser mesh is the item's first; keep the item while that
          // mesh is not resident.
          const uint32_t model = m.U32(object + 16);
          if (model) {
            const uint32_t table = m.U32(m.U32(renderer) + 52);
            const uint32_t own = m.U32(model + 132);
            const uint32_t index = own + m.S16(table + own * 28 + 16);
            if (index != own) {
              const uint32_t entry = table + index * 28;
              const uint32_t holder =
                  m.U32(m.U32(m.U32(renderer + 4)) + uint32_t(m.U16(entry + 14)) * 4);
              const bool marked = m.U8(m.U32(renderer + 8) + (int32_t(index) >> 3)) &
                                  (1u << (index & 7));
              const uint32_t resident = VirtualCall(ctx, base, holder, 52) & 0xFF;
              keep = resident != 0 || !marked;
            }
          }
        }
      }
    } else if (shadow || light) {
      keep = false;
    }
    if (!keep) continue;
    if (!ViewTest(ctx, base, item, pass_desc, pass_sphere, pass, renderer + 192,
                  m.S32(renderer + 224), probe_flag, value)) {
      continue;
    }
    const uint32_t f = m.U32(item + 4);
    if ((f & 0x10000000) == 0x10000000) {
      plan.AddPush(m, list, pass, 2, object, value);
      plan.added = true;
      continue;
    }
    if ((f & 0x02000000) == 0x02000000) {
      plan.AddPush(m, list, pass, 2, object, value);
      plan.added = true;
    }
    if (((f >> 2) & 1) || f == 0) {
      plan.AddPush(m, list, pass, 0, object, value);
      plan.added = true;
    }
    if ((f >> 1) & 1) {
      plan.AddPush(m, list, pass, 1, object, value);
      plan.added = true;
    }
    if ((f >> 7) & 1) {
      plan.AddPush(m, list, pass, 3, object, value);
      plan.added = true;
    }
    if ((f >> 8) & 1) {
      plan.AddPush(m, list, pass, 4, object, value);
      plan.added = true;
    }
  }
  return !plan.overflow;
}

// Whether every planned push fits the buckets' capacity.
bool Fits(const Mem& m, const Plan& plan) {
  for (size_t i = 0; i < plan.push_count; ++i) {
    const uint32_t vector = plan.pushes[i].vector;
    bool first = true;
    uint32_t count = 0;
    for (size_t j = 0; j < plan.push_count; ++j) {
      if (plan.pushes[j].vector != vector) continue;
      if (j < i) {
        first = false;
        break;
      }
      ++count;
    }
    if (!first) continue;
    const uint32_t end = m.U32(vector + 4), capacity = m.U32(vector + 8);
    if (end == 0 || capacity < end || capacity - end < 20 * count) return false;
  }
  return true;
}

void Apply(const Mem& m, const Plan& plan) {
  for (size_t i = 0; i < plan.push_count; ++i) {
    const Push& p = plan.pushes[i];
    const uint32_t end = m.U32(p.vector + 4);
    m.St32(end, p.object);
    m.St32(end + 4, 0);
    m.St32(end + 8, 0);
    m.St32(end + 12, p.value);
    m.St32(end + 16, 0);
    m.St32(p.vector + 4, end + 20);
  }
  for (size_t i = 0; i < plan.range_count; ++i) {
    // sub_82DDD040: the box corners' depth in the cascade (column +8).
    const DepthRange& r = plan.ranges[i];
    float lo = m.F32(r.range), hi = m.F32(r.range + 4);
    ForCorners(r.a, r.b, [&](V3 p) {
      const float z = Column(m, r.matrix, 8, p);
      lo = lo - z >= 0.0f ? z : lo;
      hi = hi - z >= 0.0f ? hi : z;
    });
    m.StF32(r.range, lo);
    m.StF32(r.range + 4, hi);
  }
}

bool CullNative(PPCContext& ctx, uint8_t* base) {
  Plan plan;
  if (!PlanCull(ctx, base, plan)) return false;
  const Mem m{base};
  if (!Fits(m, plan)) return false;
  Apply(m, plan);
  ctx.r3.u64 = plan.added ? 1 : 0;
  return true;
}

// ---- procedural models: sub_8243EE58 --------------------------------------
//
// The same per-pass decision for a procedural model (vegetation, crowds,
// animated scenery; base sub_8243EE58, v4 sub_8246EF60): r3 the renderer,
// r4 the model's reference (+8 the model once resolved), r5 one pass id, r6
// the item's pass list, r7 whether to apply the model's sphere flag. The
// model keeps a per-pass visibility byte (+76 + pass), a count of visible
// passes (+108) and a changed flag (+54), and its bounds at [model+4] (+8,
// +12 the shadow and cascade ranges, +16/+32 the box, +52/+56 a distance
// band). It pushes {0, reference, 0.0, value, flag} records to the same
// buckets; which of the five buckets come from the model's virtual slot 5,
// and a virtual at slot 12 decides per pass whether the model draws there.

struct ModelLog {
  struct Record {
    uint32_t vector, reference, value;
    uint8_t flag;
  };
  struct Mark {
    uint32_t model;
    uint32_t pass;
    uint8_t visible;
  };
  std::array<Record, 64> records;
  size_t record_count = 0;
  std::array<Mark, 64> marks;
  size_t mark_count = 0;
  std::array<DepthRange, kMaxRanges> ranges;
  size_t range_count = 0;
  std::array<uint32_t, 4> probes;
  size_t probe_count = 0;
  bool overflow = false;
};

struct ModelEffects {
  PPCContext& ctx;
  uint8_t* base;
  Mem m;
  ModelLog* log;  // planning only (verify): record instead of writing

  void Push(uint32_t vector, uint32_t reference, uint32_t value, uint8_t flag) {
    if (log) {
      if (log->record_count == log->records.size()) {
        log->overflow = true;
      } else {
        log->records[log->record_count++] = {vector, reference, value, flag};
      }
      return;
    }
    const uint32_t end = m.U32(vector + 4), capacity = m.U32(vector + 8);
    if (end != 0 && end != capacity) {
      m.St32(end, 0);
      m.St32(end + 4, reference);
      m.St32(end + 8, 0);
      m.St32(end + 12, value);
      m.St32(end + 16, uint32_t(flag) << 24);
      m.St32(vector + 4, end + 20);
      return;
    }
    // A full bucket grows through the game's own push (sub_824414E8).
    GuestCall call(ctx, base);
    const uint32_t record = call.Slot();
    m.St32(record, 0);
    m.St32(record + 4, reference);
    m.St32(record + 8, 0);
    m.St32(record + 12, value);
    m.St32(record + 16, uint32_t(flag) << 24);
    ctx.r3.u64 = vector;
    ctx.r4.u64 = record;
    PINYON_BUCKET_PUSH(ctx, base);
  }
  // sub_8243EE18.
  void Mark(uint32_t model, uint32_t pass, uint8_t visible) {
    if (log) {
      if (log->mark_count == log->marks.size()) {
        log->overflow = true;
      } else {
        log->marks[log->mark_count++] = {model, pass, visible};
      }
      return;
    }
    const uint32_t slot = model + pass + 76;
    if (m.U8(slot) == visible) return;
    m.St8(model + 54, 1);
    m.St8(slot, visible);
    m.St32(model + 108, m.U32(model + 108) + (visible ? 1u : ~0u));
  }
  void Range(V3 a, V3 b, uint32_t matrix, uint32_t range) {
    if (log) {
      if (log->range_count == log->ranges.size()) {
        log->overflow = true;
      } else {
        log->ranges[log->range_count++] = {a, b, matrix, range};
      }
      return;
    }
    float lo = m.F32(range), hi = m.F32(range + 4);
    ForCorners(a, b, [&](V3 p) {
      const float z = Column(m, matrix, 8, p);
      lo = lo - z >= 0.0f ? z : lo;
      hi = hi - z >= 0.0f ? hi : z;
    });
    m.StF32(range, lo);
    m.StF32(range + 4, hi);
  }
  // sub_82B52C18: the probe chosen for view 9.
  void Probe(uint32_t model, uint32_t value) {
    if (log) {
      if (log->probe_count == log->probes.size()) {
        log->overflow = true;
      } else {
        log->probes[log->probe_count++] = value;
      }
      return;
    }
    m.St32(model + 60, value);
  }
};

// sub_82448C20 by way of sub_82448BA0 (with a distance limit) and
// sub_8243F9A0 (without): the pass sphere against the box's bounding sphere.
bool BoxSphereTest(const Mem& m, uint32_t sphere, V3 a, V3 b, const float* max_distance2) {
  if (!(m.F32(sphere + 20) >= 0.0f)) return true;
  const V3 h = {(b.x - a.x) * 0.5f, (b.y - a.y) * 0.5f, (b.z - a.z) * 0.5f};
  const V3 c = {a.x + h.x, a.y + h.y, a.z + h.z};
  const float r2 = Dot(h, h);
  const V3 d = c - LoadV3(m, sphere);
  const float d2 = Dot(d, d);
  if (max_distance2 && d2 > *max_distance2) return false;
  return m.F32(sphere + 16) * d2 <= m.F32(sphere + 24) * r2;
}

// sub_8243EB10: the model's own distance limits from the pass position.
bool ModelInRange(const Mem& m, uint32_t model, V3 p, int32_t pass) {
  const uint32_t b = m.U32(model + 4);
  if (!b) return false;
  auto dist2 = [&] {
    const V3 lo = LoadV3(m, b + 16), hi = LoadV3(m, b + 32);
    const V3 q = {std::fmax(lo.x, std::fmin(hi.x, p.x)), std::fmax(lo.y, std::fmin(hi.y, p.y)),
                  std::fmax(lo.z, std::fmin(hi.z, p.z))};
    const V3 d = q - p;
    return Dot(d, d);
  };
  const float shadow = m.F32(b + 8);
  if (!(shadow < 0.0f) && pass == 6) {
    if (!(dist2() <= shadow * shadow)) return false;
  } else {
    const float cascade = m.F32(b + 12);
    if (!(cascade < 0.0f) && uint32_t(pass) <= 5) {
      if (!(dist2() <= cascade * cascade)) return false;
    }
  }
  const float near = m.F32(b + 52), far = m.F32(b + 56);
  if (near == 0.0f && far == 0.0f) return false;
  if (near < 0.0f && far < 0.0f) return true;
  const float d2 = dist2();
  if (!(near < 0.0f) && d2 < near * near) return false;
  if (far < 0.0f) return true;
  return !(d2 > far * far);
}

uint32_t ResolveModel(PPCContext& ctx, uint8_t* base, uint32_t reference) {
  const Mem m{base};
  const uint32_t resolved = m.U32(reference + 8);
  if (resolved) return resolved;
  GuestCall call(ctx, base);
  ctx.r3.u64 = reference;
  PINYON_MODEL_RESOLVE(ctx, base);
  return ctx.r3.u32;
}

void ModelPassCull(ModelEffects& fx, uint32_t renderer, uint32_t reference, int32_t pass,
                   uint32_t passes, uint8_t sphere_flag) {
  PPCContext& ctx = fx.ctx;
  uint8_t* base = fx.base;
  const Mem& m = fx.m;
  const uint32_t model = ResolveModel(ctx, base, reference);
  if (!model) return;
  const uint32_t shift = uint32_t(pass) & 63;
  if (shift >= 32 || !((m.U32(model + 68) >> shift) & 1)) return;
  const uint32_t bounds = m.U32(model + 4);
  // The box, and the box in the z-flipped space the frustum and sphere tests
  // use; read only where the original reads it (bounds may be null).
  V3 lo{}, hi{}, fa{}, fb{};
  auto load_box = [&] {
    lo = LoadV3(m, bounds + 16);
    hi = LoadV3(m, bounds + 32);
    fa = {lo.x, lo.y, -hi.z};
    fb = {hi.x, hi.y, -lo.z};
  };
  const uint32_t sphere = renderer + ((m.U32(renderer + 36) + 253) << 5);
  if (pass == 24) {
    load_box();
    if ((m.U32(model + 72) >> 24) & 1) {
      const uint32_t count = m.U32(renderer + 12224);
      for (uint32_t j = 0; j < count; ++j) fx.Mark(model, j + 24, 0);
      const float max_distance = m.F32(renderer + 12232);
      if (BoxSphereTest(m, sphere, fa, fb, &max_distance)) {
        const uint32_t mask = CascadeMask(m, renderer, count, lo, hi);
        if (mask) {
          bool ranged = false;
          for (uint32_t j = 0; j < count; ++j) {
            if (j >= 32 || !(mask & (1u << j))) continue;
            const uint32_t list = m.U32(renderer + 13844);
            fx.Push(list + 1920 + j * 80, reference, 0, 1);
            const uint32_t cascade = renderer + 10288 + j * 496;
            if (m.U8(cascade + 436) == 0 && !ranged) {
              fx.Range(lo, hi, cascade, list + 2560 + j * 8);
              ranged = true;
            }
            fx.Mark(model, j + 24, 1);
          }
        }
      }
    }
    if (!((m.U32(model + 72) >> 28) & 1)) return;
    const uint32_t count = m.U32(renderer + 13840);
    for (uint32_t j = 0; j < count; ++j) fx.Mark(model, j + 28, 0);
    if (!BoxSphereTest(m, sphere, fa, fb, nullptr)) return;
    const uint32_t ranges = m.U32(renderer + 13844) + 2592;
    for (uint32_t j = 0; j < count; ++j) {
      const uint32_t light = renderer + 12636 + j * 400;
      if (!PlanesTest(m, lo, hi, light - 204, 6)) continue;
      fx.Push(m.U32(renderer + 13844) + 2240 + j * 80, reference, 0, 1);
      if (m.U8(light) == 0) fx.Range(lo, hi, light - 396, ranges + j * 8);
      fx.Mark(model, j + 28, 1);
      if (j < m.U32(renderer + 13840) - 1 && Contained(m, lo, hi, light - 268, m.F32(light - 4))) {
        return;
      }
    }
    return;
  }
  // sub_8243EC70: the pass's own test of the model.
  const uint32_t pass_desc = m.U32(passes) + pass * 192;
  const uint32_t pass_sphere = m.U32(passes + 4) + pass * 32;
  uint32_t value = 0;
  uint8_t flag = 0;
  bool visible = false;
  const V3 at = {m.F32(pass_desc + 160), m.F32(pass_desc + 164), m.F32(pass_desc + 168)};
  if (ModelInRange(m, model, at, pass)) {
    {
      GuestCall call(ctx, base);
      const uint32_t point = call.Slot();
      m.StF32(point, at.x);
      m.StF32(point + 4, at.y);
      m.StF32(point + 8, at.z);
      m.St32(point + 12, 0);
      ctx.r3.u64 = model;
      ctx.r4.u64 = point;
      call.Indirect(m.U32(m.U32(model) + 48));
      flag = ctx.r3.u8;
    }
    load_box();
    if (flag && (!sphere_flag || !m.U8(model + 113) ||
                 BoxSphereTest(m, pass_sphere, fa, fb, nullptr))) {
      const int32_t probe_count = m.S32(renderer + 224);
      if (pass == 9 && probe_count >= 1) {
        GuestCall call(ctx, base);
        m.St32(call.Slot(), 0);
        ctx.r3.u64 = pass_desc;
        ctx.r4.u64 = renderer + 192;
        ctx.r5.s64 = probe_count;
        ctx.r6.u64 = m.U8(passes + 172);
        ctx.r7.u64 = call.Slot();
        ctx.v1.f32[3] = fa.x, ctx.v1.f32[2] = fa.y, ctx.v1.f32[1] = fa.z;
        ctx.v1.f32[0] = m.F32(bounds + 28);
        ctx.v2.f32[3] = fb.x, ctx.v2.f32[2] = fb.y, ctx.v2.f32[1] = fb.z;
        ctx.v2.f32[0] = m.F32(bounds + 44);
        PINYON_PROBE_SELECT(ctx, base);
        value = m.U32(call.Slot());
        visible = ctx.r3.u32 != 0;
      } else {
        visible = FrustumTest(m, pass_desc, fa, fb) != 0;
      }
    }
  }
  if (!visible) {
    fx.Mark(model, pass, 0);
    if (pass == 9) fx.Probe(model, 0);
    return;
  }
  fx.Mark(model, pass, 1);
  if (pass == 9) fx.Probe(model, value);
  const uint32_t buckets = VirtualCall(ctx, base, model, 20);
  for (uint32_t b = 0; b < 5; ++b) {
    if (!(buckets & (1u << b))) continue;
    fx.Push(m.U32(renderer + 13844) + (pass * 5 + b) * 16, reference, value, flag);
  }
}

bool ModelCullNative(PPCContext& ctx, uint8_t* base) {
  ModelEffects fx{ctx, base, Mem{base}, nullptr};
  ModelPassCull(fx, ctx.r3.u32, ctx.r4.u32, ctx.r5.s32, ctx.r6.u32, ctx.r7.u8);
  return true;
}

// ---- verify: the original's pushes and depth ranges, recorded -------------

struct Recording {
  std::array<Push, kMaxPushes> pushes;
  size_t push_count = 0;
  std::array<DepthRange, kMaxRanges> ranges;
  size_t range_count = 0;
  bool overflow = false;
};
thread_local Recording* recording = nullptr;
thread_local ModelLog* model_recording = nullptr;

bool Recording_() { return recording != nullptr; }
bool ModelRecording() { return model_recording != nullptr; }
bool AnyRecording() { return recording != nullptr || model_recording != nullptr; }

bool RecordPush(PPCContext& ctx, uint8_t* base) {
  const Mem m{base};
  Recording& r = *recording;
  const uint32_t object = ctx.r7.u32;
  if (m.U32(object + 16) != 0) {
    if (r.push_count == kMaxPushes) {
      r.overflow = true;
    } else {
      r.pushes[r.push_count++] = {ctx.r3.u32 + (ctx.r4.u32 * 5 + ctx.r5.u32) * 16, object,
                                  ctx.r8.u32};
    }
  }
  return false;  // the original pushes
}

bool RecordRange(PPCContext& ctx, uint8_t* base) {
  const Mem m{base};
  const DepthRange range = {LoadV3(m, ctx.r3.u32), LoadV3(m, ctx.r4.u32), ctx.r5.u32, ctx.r6.u32};
  if (model_recording) {
    ModelLog& r = *model_recording;
    if (r.range_count == r.ranges.size()) {
      r.overflow = true;
    } else {
      r.ranges[r.range_count++] = range;
    }
    return false;
  }
  Recording& r = *recording;
  if (r.range_count == kMaxRanges) {
    r.overflow = true;
  } else {
    r.ranges[r.range_count++] = range;
  }
  return false;
}

bool RecordModelPush(PPCContext& ctx, uint8_t* base) {
  const Mem m{base};
  ModelLog& r = *model_recording;
  if (r.record_count == r.records.size()) {
    r.overflow = true;
  } else {
    const uint32_t record = ctx.r4.u32;
    r.records[r.record_count++] = {ctx.r3.u32, m.U32(record + 4), m.U32(record + 12),
                                   m.U8(record + 16)};
  }
  return false;
}

bool RecordMark(PPCContext& ctx, uint8_t* /*base*/) {
  ModelLog& r = *model_recording;
  if (r.mark_count == r.marks.size()) {
    r.overflow = true;
  } else {
    r.marks[r.mark_count++] = {ctx.r3.u32, ctx.r4.u32, ctx.r5.u8};
  }
  return false;
}

bool RecordProbe(PPCContext& ctx, uint8_t* /*base*/) {
  ModelLog& r = *model_recording;
  if (r.probe_count == r.probes.size()) {
    r.overflow = true;
  } else {
    r.probes[r.probe_count++] = ctx.r4.u32;
  }
  return false;
}

bool Close(float a, float b) {
  return a == b || std::fabs(a - b) <= 1e-4f * std::fmax(std::fabs(a), std::fabs(b));
}

std::string Compare(const Plan& plan, const Recording& rec, uint32_t native_r3,
                    uint32_t original_r3) {
  if (rec.overflow) return {};
  if (native_r3 != original_r3) return fmt::format("r3 {} {}", native_r3, original_r3);
  if (plan.push_count != rec.push_count) {
    return fmt::format("pushes {} {}", plan.push_count, rec.push_count);
  }
  for (size_t i = 0; i < plan.push_count; ++i) {
    const Push &a = plan.pushes[i], &b = rec.pushes[i];
    if (a.vector != b.vector || a.object != b.object || a.value != b.value) {
      return fmt::format("push {} {:08X}/{:08X}/{} {:08X}/{:08X}/{}", i, a.vector, a.object,
                         a.value, b.vector, b.object, b.value);
    }
  }
  if (plan.range_count != rec.range_count) {
    return fmt::format("ranges {} {}", plan.range_count, rec.range_count);
  }
  for (size_t i = 0; i < plan.range_count; ++i) {
    const DepthRange &a = plan.ranges[i], &b = rec.ranges[i];
    if (a.matrix != b.matrix || a.range != b.range || !Close(a.a.x, b.a.x) ||
        !Close(a.a.z, b.a.z) || !Close(a.b.z, b.b.z)) {
      return fmt::format("range {}", i);
    }
  }
  return {};
}

void VerifyCull(Replacement& self, PPCFunc* original, PPCContext& ctx, uint8_t* base) {
  using Clock = std::chrono::steady_clock;
  Plan plan;
  PPCContext scratch = ctx;
  const auto t0 = Clock::now();
  const bool planned = PlanCull(scratch, base, plan);
  const auto t1 = Clock::now();
  Recording rec;
  recording = &rec;
  original(ctx, base);
  recording = nullptr;
  const auto t2 = Clock::now();
  if (!planned) {
    self.stats.declined.fetch_add(1, std::memory_order_relaxed);
    return;
  }
  self.stats.verified.fetch_add(1, std::memory_order_relaxed);
  // The original's time includes the recording hooks' dispatch.
  self.stats.native_ns.fetch_add(
      std::chrono::duration_cast<std::chrono::nanoseconds>(t1 - t0).count(),
      std::memory_order_relaxed);
  self.stats.original_ns.fetch_add(
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count(),
      std::memory_order_relaxed);
  const std::string difference = Compare(plan, rec, plan.added ? 1 : 0, ctx.r3.u32);
  if (difference.empty()) return;
  if (self.stats.mismatched.fetch_add(1, std::memory_order_relaxed) >= 16) return;
  diagnostics::RecordEvent("guest_native.mismatch",
                           {{"name", self.name},
                            {"difference", difference},
                            {"r3", fmt::format("{:08X}", scratch.r3.u32)},
                            {"r4", fmt::format("{:08X}", scratch.r4.u32)},
                            {"r5", fmt::format("{:08X}", scratch.r5.u32)}});
}

std::string CompareModel(const ModelLog& a, const ModelLog& b) {
  if (b.overflow || a.overflow) return {};
  if (a.record_count != b.record_count) {
    return fmt::format("records {} {}", a.record_count, b.record_count);
  }
  for (size_t i = 0; i < a.record_count; ++i) {
    const auto &x = a.records[i], &y = b.records[i];
    if (x.vector != y.vector || x.reference != y.reference || x.value != y.value ||
        x.flag != y.flag) {
      return fmt::format("record {} {:08X}/{:08X}/{}/{} {:08X}/{:08X}/{}/{}", i, x.vector,
                         x.reference, x.value, x.flag, y.vector, y.reference, y.value, y.flag);
    }
  }
  if (a.mark_count != b.mark_count) return fmt::format("marks {} {}", a.mark_count, b.mark_count);
  for (size_t i = 0; i < a.mark_count; ++i) {
    const auto &x = a.marks[i], &y = b.marks[i];
    if (x.model != y.model || x.pass != y.pass || x.visible != y.visible) {
      return fmt::format("mark {} {}/{} {}/{}", i, x.pass, x.visible, y.pass, y.visible);
    }
  }
  if (a.range_count != b.range_count) {
    return fmt::format("ranges {} {}", a.range_count, b.range_count);
  }
  for (size_t i = 0; i < a.range_count; ++i) {
    if (a.ranges[i].matrix != b.ranges[i].matrix || a.ranges[i].range != b.ranges[i].range) {
      return fmt::format("range {}", i);
    }
  }
  if (a.probe_count != b.probe_count) return "probes";
  for (size_t i = 0; i < a.probe_count; ++i) {
    if (a.probes[i] != b.probes[i]) return fmt::format("probe {}", i);
  }
  return {};
}

void VerifyModelCull(Replacement& self, PPCFunc* original, PPCContext& ctx, uint8_t* base) {
  using Clock = std::chrono::steady_clock;
  ModelLog planned;
  PPCContext scratch = ctx;
  const auto t0 = Clock::now();
  {
    ModelEffects fx{scratch, base, Mem{base}, &planned};
    ModelPassCull(fx, ctx.r3.u32, ctx.r4.u32, ctx.r5.s32, ctx.r6.u32, ctx.r7.u8);
  }
  const auto t1 = Clock::now();
  ModelLog seen;
  model_recording = &seen;
  original(ctx, base);
  model_recording = nullptr;
  const auto t2 = Clock::now();
  self.stats.verified.fetch_add(1, std::memory_order_relaxed);
  self.stats.native_ns.fetch_add(
      std::chrono::duration_cast<std::chrono::nanoseconds>(t1 - t0).count(),
      std::memory_order_relaxed);
  self.stats.original_ns.fetch_add(
      std::chrono::duration_cast<std::chrono::nanoseconds>(t2 - t1).count(),
      std::memory_order_relaxed);
  const std::string difference = CompareModel(planned, seen);
  if (difference.empty()) return;
  if (self.stats.mismatched.fetch_add(1, std::memory_order_relaxed) >= 16) return;
  diagnostics::RecordEvent("guest_native.mismatch",
                           {{"name", self.name},
                            {"difference", difference},
                            {"r4", fmt::format("{:08X}", scratch.r4.u32)},
                            {"r5", fmt::format("{}", scratch.r5.s32)}});
}

Replacement cull_replacement = {
    .name = "scene.pass_cull",
    .guest_address = kV4 ? 0x824701B8u : 0x824400B0u,
    .guest_code_size = 2888,
    .guest_code_fnv1a = kV4 ? 0x700DDC639CA17882ull : 0xAD7EBD6ABF55C311ull,
    .returns = kReturnR3,
    .enabled = Enabled,
    .native = CullNative,
    .written = nullptr,
    .verify = VerifyCull,
};

Replacement push_recorder = {
    .name = "scene.bucket_push_recorder",
    .guest_address = kV4 ? 0x82471590u : 0x82441488u,
    .guest_code_size = 96,
    .guest_code_fnv1a = 0x8B8FCB4DAA223F88ull,
    .returns = kReturnNone,
    .enabled = Recording_,
    .native = RecordPush,
    .written = nullptr,
};

Replacement model_cull_replacement = {
    .name = "scene.model_pass_cull",
    .guest_address = kV4 ? 0x8246EF60u : 0x8243EE58u,
    .guest_code_size = 1228,
    .guest_code_fnv1a = kV4 ? 0xAB61BCA1DC38FEEEull : 0xB6BCD770E9A7414Dull,
    .returns = kReturnNone,
    .enabled = Enabled,
    .native = ModelCullNative,
    .written = nullptr,
    .verify = VerifyModelCull,
};

Replacement model_push_recorder = {
    .name = "scene.model_push_recorder",
    .guest_address = kV4 ? 0x824715F0u : 0x824414E8u,
    .guest_code_size = 264,
    .guest_code_fnv1a = kV4 ? 0xD161973C7E893529ull : 0x49655C4738DFDD9Dull,
    .returns = kReturnNone,
    .enabled = ModelRecording,
    .native = RecordModelPush,
    .written = nullptr,
};

Replacement mark_recorder = {
    .name = "scene.model_mark_recorder",
    .guest_address = kV4 ? 0x8246EF20u : 0x8243EE18u,
    .guest_code_size = 64,
    .guest_code_fnv1a = 0x843FFEA019C16046ull,
    .returns = kReturnNone,
    .enabled = ModelRecording,
    .native = RecordMark,
    .written = nullptr,
};

Replacement probe_recorder = {
    .name = "scene.model_probe_recorder",
    .guest_address = kV4 ? 0x82EEC158u : 0x82B52C18u,
    .guest_code_size = 8,
    .guest_code_fnv1a = 0xCF49A33C581FAE3Eull,
    .returns = kReturnNone,
    .enabled = ModelRecording,
    .native = RecordProbe,
    .written = nullptr,
};

Replacement range_recorder = {
    .name = "scene.depth_range_recorder",
    .guest_address = kV4 ? 0x82E9F610u : 0x82DDD040u,
    .guest_code_size = 412,
    .guest_code_fnv1a = kV4 ? 0x920AE7C796DF785Cull : 0x840BEC1DC27F6026ull,
    .returns = kReturnNone,
    .enabled = AnyRecording,
    .native = RecordRange,
    .written = nullptr,
};

}  // namespace
}  // namespace pinyon_shift::guest_native

PINYON_GUEST_NATIVE(824400B0, 824701B8, ::pinyon_shift::guest_native::cull_replacement)
PINYON_GUEST_NATIVE(82441488, 82471590, ::pinyon_shift::guest_native::push_recorder)
PINYON_GUEST_NATIVE(82DDD040, 82E9F610, ::pinyon_shift::guest_native::range_recorder)
PINYON_GUEST_NATIVE(8243EE58, 8246EF60, ::pinyon_shift::guest_native::model_cull_replacement)
PINYON_GUEST_NATIVE(824414E8, 824715F0, ::pinyon_shift::guest_native::model_push_recorder)
PINYON_GUEST_NATIVE(8243EE18, 8246EF20, ::pinyon_shift::guest_native::mark_recorder)
PINYON_GUEST_NATIVE(82B52C18, 82EEC158, ::pinyon_shift::guest_native::probe_recorder)
