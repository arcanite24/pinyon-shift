// Region oracle (#749, NA-1.1 of #757). For each root in the analysis
// config's oracle_regions the generator emits every function of the region
// twice more with logged stores (rex/ppc/oracle.h): `orr_sub_X` with the
// reference options and `orc_sub_X` with this build's options, the
// candidate. With pinyon_shift_region_oracle=N, every Nth call of a root runs
// three sides from the same registers and memory:
//
//   interpreter  the slow PowerPC interpreter (rex/ppc/interpreter.h), which
//                shares no instruction semantics with the generator
//   reference    the orr_ copy
//   candidate    the orc_ copy (a native region replaces it in Stage 2)
//
// rolls each side's stores back, then runs the root for real. It compares the
// interpreter with the reference and the candidate with the reference: the
// whole context (every GPR, FPR, vector register, CR field, XER, CTR and LR),
// every store outside the root's stack frame in order (address, size, value),
// and the exit (returned, or stopped at the same opaque boundary with the
// same context there). Finally the candidate's stores are checked against
// memory after the real run, so the logged copy is shown to be the code that
// runs. The game always keeps the real run's results.
//
// Policy, from the generator's documented assumptions: the candidate keeps
// CTR, XER and the CR fields in locals and publishes only what a callee or
// caller may read, so differences in CTR, XER and the volatile fields cr0,
// cr1 and cr5-cr7 (nothing reads them across a call or a return) are
// reported as dead volatiles, not counted against it; it keeps LR in a local
// too (host_local_lr), so LR is not compared. Everything else is compared.
// Stores into the root's own frame (below the entry stack pointer) are dead
// after the return and are counted, not compared; a frame value that matters
// shows up in a register or a visible store.
//
// pinyon_shift_region_oracle_fault seeds a fault into the candidate's run
// (drop_store, reorder_stores, volatile_register) to show the oracle catches
// it: route summaries report faults applied and caught.

#include "guest_native/guest_native.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <csetjmp>
#include <cstring>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include <fmt/format.h>
#include <rex/cvar.h>
#include <rex/platform/fpscr.h>
#include <rex/ppc/interpreter.h>
#include <rex/ppc/oracle.h>
#include <rex/ppc/reference.h>

#include "pinyon_shift_diagnostics.h"

#if defined(__x86_64__) || defined(_M_X64)
#include <x86intrin.h>
#endif

REXCVAR_DEFINE_UINT32(pinyon_shift_region_oracle, 0, "Pinyon Shift",
                      "Every Nth call of a region oracle root also runs the interpreter, the "
                      "reference copy and the candidate copy and compares them (0 = off)")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_UINT32(pinyon_shift_region_oracle_ulps, 0, "Pinyon Shift",
                      "Region oracle tolerance: floating-point registers and stored floats may "
                      "differ by up to this many single-precision ulps (0 = bit-exact)")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_STRING(pinyon_shift_region_oracle_fault, "", "Pinyon Shift",
                      "Seed a fault into the region oracle's candidate run: drop_store, "
                      "reorder_stores or volatile_register (empty = none)")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_UINT32(pinyon_shift_native_region, 0, "Pinyon Shift",
                      "Native regions (#750): 0 runs the generated root, 1 the native region, 2 "
                      "alternates the two call by call and times each (the in-run A/B)")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

namespace pinyon_shift::guest_native::region_oracle {
namespace {

constexpr uint64_t kMaxLoggedMismatches = 32;
// Stores within this distance below the entry stack pointer are the root's
// frame (and its callees' frames).
constexpr uint32_t kFrameWindow = 256 * 1024;

struct Range {
  uint32_t start;
  uint32_t end;
};

struct Counters {
  std::atomic<uint64_t> calls{0};
  std::atomic<uint64_t> checked{0};
  std::atomic<uint64_t> returned{0};
  std::atomic<uint64_t> halted{0};             // all sides stopped at the same boundary
  std::atomic<uint64_t> interp_mismatched{0};  // interpreter vs reference
  std::atomic<uint64_t> interp_unavailable{0}; // the interpreter stopped (unsupported, ...)
  std::atomic<uint64_t> candidate_mismatched{0};
  std::atomic<uint64_t> within_tolerance{0};   // differed only by FP values within the cvar
  std::atomic<uint64_t> candidate_dead_volatile{0};  // CTR/XER differed (not counted)
  std::atomic<uint64_t> real_mismatched{0};    // candidate copy vs the real run's memory
  std::atomic<uint64_t> visible_stores{0};
  std::atomic<uint64_t> frame_stores{0};
  std::atomic<uint64_t> faults_applied{0};
  std::atomic<uint64_t> faults_caught{0};
  std::atomic<uint64_t> faults_not_applicable{0};
  std::atomic<uint64_t> max_ulps{0};
  std::atomic<uint64_t> logged{0};
};

struct Region {
  const char* name;
  uint32_t root;
  PPCFunc* original;
  PPCFunc* reference;
  PPCFunc* candidate;
  std::vector<Range> ranges;
  Counters counters;
  // Host CRT functions the region calls (rex/ppc/oracle.h): the copies call
  // logged versions, and the interpreter runs the same through host_call.
  std::vector<std::pair<uint32_t, rex::ppc::OracleCrt>> crt;
  // The native region (native_regions): runs in place of `original` when
  // pinyon_shift_native_region selects it; the oracle then checks its logged
  // form instead of the candidate copy.
  PPCFunc* native = nullptr;
  // pinyon_shift_native_region=2: per side (0 generated, 1 native) the timed
  // calls, their ticks and squared ticks, and calls dropped as interrupted.
  struct Timing {
    std::atomic<uint64_t> calls{0};
    std::atomic<uint64_t> ticks{0};
    std::atomic<uint64_t> squares{0};
    std::atomic<uint64_t> dropped{0};
  } timing[2];
};

struct NativeRegistration {
  NativeRegistration(Region& region, PPCFunc* native, PPCFunc* candidate) {
    region.native = native;
    region.candidate = candidate;
  }
};

// A cheap monotonic counter for per-call timing: the TSC on x86, the
// virtual counter on arm64 (19.2 MHz on the Odin, so single calls are coarse
// and only the means over many calls count).
inline uint64_t Ticks() {
#if defined(__x86_64__) || defined(_M_X64)
  return __rdtsc();
#elif defined(__aarch64__)
  uint64_t value;
  asm volatile("isb\n\tmrs %0, cntvct_el0" : "=r"(value));
  return value;
#else
  return uint64_t(std::chrono::steady_clock::now().time_since_epoch().count());
#endif
}

uint64_t TicksPerSecond() {
#if defined(__aarch64__)
  uint64_t value;
  asm volatile("mrs %0, cntfrq_el0" : "=r"(value));
  return value;
#elif defined(__x86_64__) || defined(_M_X64)
  static const uint64_t measured = [] {
    const auto t0 = std::chrono::steady_clock::now();
    const uint64_t c0 = __rdtsc();
    while (std::chrono::steady_clock::now() - t0 < std::chrono::milliseconds(20)) {
    }
    const uint64_t c1 = __rdtsc();
    const auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
                        std::chrono::steady_clock::now() - t0)
                        .count();
    return uint64_t(double(c1 - c0) * 1e9 / double(ns));
  }();
  return measured;
#else
  return 1000000000ull;
#endif
}

std::mutex registry_mutex;
std::vector<Region*>& Registry() {
  static std::vector<Region*> registry;
  return registry;
}

struct Registration {
  explicit Registration(Region& region) {
    std::lock_guard lock(registry_mutex);
    Registry().push_back(&region);
  }
};

struct RangeRegistration {
  RangeRegistration(Region& region, uint32_t start, uint32_t end) {
    region.ranges.push_back({start, end});
  }
};

struct CrtRegistration {
  CrtRegistration(Region& region, uint32_t address, const char* name) {
    region.crt.emplace_back(address, rex::ppc::OracleCrtByName(std::string_view(name).substr(7)));
  }
};

// --- One side's run --------------------------------------------------------

struct Store {
  uint32_t guest;
  std::vector<uint8_t> bytes;  // guest order
};

struct Side {
  const char* name;
  alignas(64) PPCContext ctx;
  bool halted = false;
  uint32_t target = 0;
  uint32_t site = 0;
  bool available = true;      // the interpreter ran to an exit the others can have
  std::string unavailable;    // why not
  std::vector<Store> visible;
  uint64_t frame_stores = 0;
};

// The log as stores: frame stores dropped, and runs of single-byte stores to
// adjacent addresses (a partial vector store's byte loop) merged into one
// ascending store, so every side spells them the same.
void CollectStores(Side& side, uint32_t frame_lo, uint32_t frame_hi) {
  for (const rex::ppc::RefWrite& w : rex::ppc::RefLog()) {
    if (w.guest >= frame_lo && w.guest < frame_hi) {
      side.frame_stores++;
      continue;
    }
    Store store{w.guest, std::vector<uint8_t>(w.neu, w.neu + w.size)};
    if (w.size == 1 && !side.visible.empty()) {
      Store& last = side.visible.back();
      if (last.guest + last.bytes.size() == w.guest &&
          (last.bytes.size() == 1 || last.guest % 16 != 0)) {
        last.bytes.push_back(w.neu[0]);
        continue;
      }
      if (w.guest + 1 == last.guest && last.bytes.size() < 16) {
        last.bytes.insert(last.bytes.begin(), w.neu[0]);
        last.guest = w.guest;
        continue;
      }
    }
    side.visible.push_back(std::move(store));
  }
}

struct HostFp {
  uint32_t csr = rex::platform::FPSCRPlatform::getcsr();
  void Restore() const { rex::platform::FPSCRPlatform::setcsr(csr); }
};

void RunCopy(Side& side, PPCFunc* fn, const PPCContext& input, uint8_t* base, uint32_t frame_lo,
             uint32_t frame_hi, rex::ppc::RefFault* fault) {
  side.ctx = input;
  rex::ppc::OracleSide oracle;
  rex::ppc::OracleCurrentSide() = &oracle;
  rex::ppc::RefLogBegin();
  rex::ppc::RefFaultSlot() = fault;
  if (setjmp(oracle.exit) == 0) {
    fn(side.ctx, base);
  } else {
    side.halted = true;
    side.target = oracle.target;
    side.site = oracle.site;
    side.ctx = oracle.at;
  }
  if (fault)
    rex::ppc::RefFaultFinish(*fault);
  rex::ppc::RefFaultSlot() = nullptr;
  rex::ppc::OracleCurrentSide() = nullptr;
  CollectStores(side, frame_lo, frame_hi);
  rex::ppc::RefRollback();
}

struct InterpUser {
  const Region* region;
  uint8_t* base;
};

bool FetchGuest(void* user, uint32_t address, uint32_t* insn) {
  const auto* u = static_cast<InterpUser*>(user);
  if (address < 0x82000000u || address >= 0x84000000u)
    return false;
  *insn = rex::ppc::interp::detail::LoadBE<uint32_t>(u->base, address);
  return true;
}

bool InsideRegion(void* user, uint32_t address) {
  const auto* u = static_cast<InterpUser*>(user);
  for (const Range& r : u->region->ranges)
    if (address >= r.start && address < r.end)
      return true;
  return false;
}

bool HostCall(void* user, PPCContext& ctx, uint8_t* base, uint32_t target) {
  const auto* u = static_cast<InterpUser*>(user);
  for (const auto& [address, kind] : u->region->crt) {
    if (address == target) {
      rex::ppc::OracleCrtRun(kind, ctx, base);
      return true;
    }
  }
  return false;
}

void RunInterpreter(Side& side, const Region& region, const PPCContext& input, uint8_t* base,
                    uint32_t frame_lo, uint32_t frame_hi) {
  side.ctx = input;
  InterpUser user{&region, base};
  rex::ppc::interp::Config config;
  config.fetch = FetchGuest;
  config.fetch_user = &user;
  config.inside = InsideRegion;
  config.inside_user = &user;
  config.host_call = HostCall;
  config.host_call_user = &user;
  config.vmx_flush_denormals = !PPCFPSCRRegister::FixedMode();
  rex::ppc::RefLogBegin();
  const auto result = rex::ppc::interp::Run(side.ctx, base, region.root, config);
  switch (result.exit) {
    case rex::ppc::interp::Exit::kReturned:
      break;
    case rex::ppc::interp::Exit::kBoundary:
      side.halted = true;
      side.target = result.target;
      side.site = result.pc;
      break;
    default:
      side.available = false;
      side.unavailable = fmt::format("{} at {:08X} ({:08X})",
                                     rex::ppc::interp::ExitName(result.exit), result.pc,
                                     result.insn);
      break;
  }
  CollectStores(side, frame_lo, frame_hi);
  rex::ppc::RefRollback();
}

// --- Comparison --------------------------------------------------------------

double FprUlps(uint64_t a, uint64_t b) {
  double da, db;
  std::memcpy(&da, &a, 8);
  std::memcpy(&db, &b, 8);
  if (double(float(da)) == da && double(float(db)) == db) {
    const float fa = float(da), fb = float(db);
    uint32_t ia, ib;
    std::memcpy(&ia, &fa, 4);
    std::memcpy(&ib, &fb, 4);
    return rex::ppc::RefFloatUlps(ia, ib);
  }
  return rex::ppc::RefDoubleUlps(a, b);
}

struct Diff {
  std::string first;        // the first difference beyond tolerance, or ""
  std::string dead;         // a CTR/XER-only difference the policy does not count
  double max_ulps = 0;      // the largest FP distance seen
  bool any_fp = false;      // some FP value differed (within tolerance or not)
};

struct Policy {
  bool exempt_ctr_xer = false;  // candidate: CTR, XER and volatile CR fields live in locals
  bool exempt_lr = false;       // candidate: host_local_lr
  double tolerance = 0;
};

void NoteFp(Diff& d, const Policy& p, double ulps, const std::string& what) {
  d.any_fp = true;
  d.max_ulps = std::max(d.max_ulps, ulps);
  if (ulps > p.tolerance && d.first.empty())
    d.first = what;
}

void CompareContexts(const PPCContext& a, const PPCContext& b, const Policy& p, Diff& d) {
  auto gpr = [&](const char* name, uint64_t x, uint64_t y) {
    if (x != y && d.first.empty())
      d.first = fmt::format("{} {:016X} {:016X}", name, x, y);
  };
  static const char* const kGpr[32] = {
      "r0",  "r1",  "r2",  "r3",  "r4",  "r5",  "r6",  "r7",  "r8",  "r9",  "r10",
      "r11", "r12", "r13", "r14", "r15", "r16", "r17", "r18", "r19", "r20", "r21",
      "r22", "r23", "r24", "r25", "r26", "r27", "r28", "r29", "r30", "r31"};
  auto g = [](const PPCContext& c, int n) -> uint64_t {
    switch (n) {
      case 0: return c.r0.u64;
      case 1: return c.r1.u64;
      case 2: return c.r2.u64;
      case 3: return c.r3.u64;
      default: return (&c.r4)[n - 4].u64;
    }
  };
  for (int n = 0; n < 32; ++n)
    gpr(kGpr[n], g(a, n), g(b, n));
  for (int n = 0; n < 32; ++n) {
    const uint64_t x = (&a.f0)[n].u64, y = (&b.f0)[n].u64;
    if (x != y)
      NoteFp(d, p, FprUlps(x, y), fmt::format("f{} {:016X} {:016X}", n, x, y));
  }
  for (int n = 0; n < 128; ++n) {
    for (int lane = 0; lane < 4; ++lane) {
      const uint32_t x = (&a.v0)[n].u32[lane], y = (&b.v0)[n].u32[lane];
      if (x != y)
        NoteFp(d, p, rex::ppc::RefFloatUlps(x, y),
               fmt::format("v{}[{}] {:08X} {:08X}", n, 3 - lane, x, y));
    }
  }
  for (int n = 0; n < 8; ++n) {
    const uint32_t x = (&a.cr0)[n].raw(), y = (&b.cr0)[n].raw();
    if (x == y)
      continue;
    const bool volatile_field = n < 2 || n > 4;
    if (p.exempt_ctr_xer && volatile_field) {
      if (d.dead.empty())
        d.dead = fmt::format("cr{} {:X} {:X}", n, x, y);
    } else if (d.first.empty()) {
      d.first = fmt::format("cr{} {:X} {:X}", n, x, y);
    }
  }
  if (!p.exempt_lr)
    gpr("lr", a.lr, b.lr);
  const bool ctr = a.ctr.u64 != b.ctr.u64;
  const bool xer = a.xer.so != b.xer.so || a.xer.ov != b.xer.ov || a.xer.ca != b.xer.ca;
  if (p.exempt_ctr_xer) {
    if (ctr)
      d.dead = fmt::format("ctr {:016X} {:016X}", a.ctr.u64, b.ctr.u64);
    else if (xer)
      d.dead = "xer";
  } else {
    gpr("ctr", a.ctr.u64, b.ctr.u64);
    if (xer && d.first.empty())
      d.first = fmt::format("xer {}{}{} {}{}{}", a.xer.so, a.xer.ov, a.xer.ca, b.xer.so, b.xer.ov,
                            b.xer.ca);
  }
}

uint64_t LoadBe(const uint8_t* p, size_t n) {
  uint64_t v = 0;
  for (size_t i = 0; i < n; ++i)
    v = (v << 8) | p[i];
  return v;
}

void CompareStores(const Side& a, const Side& b, const Policy& p, Diff& d) {
  const size_t n = std::min(a.visible.size(), b.visible.size());
  for (size_t i = 0; i < n && d.first.empty(); ++i) {
    const Store& x = a.visible[i];
    const Store& y = b.visible[i];
    if (x.guest != y.guest || x.bytes.size() != y.bytes.size()) {
      d.first = fmt::format("store #{} at {:08X}+{} against {:08X}+{}", i, x.guest,
                            x.bytes.size(), y.guest, y.bytes.size());
      break;
    }
    if (x.bytes == y.bytes)
      continue;
    const size_t size = x.bytes.size();
    if (size == 4 || size == 16) {
      for (size_t lane = 0; lane < size; lane += 4) {
        const uint32_t u = uint32_t(LoadBe(x.bytes.data() + lane, 4));
        const uint32_t v = uint32_t(LoadBe(y.bytes.data() + lane, 4));
        if (u != v)
          NoteFp(d, p, rex::ppc::RefFloatUlps(u, v),
                 fmt::format("store #{} {:08X} {:08X} {:08X}", i, x.guest + lane, u, v));
      }
    } else if (size == 8) {
      const uint64_t u = LoadBe(x.bytes.data(), 8), v = LoadBe(y.bytes.data(), 8);
      NoteFp(d, p, FprUlps(u, v), fmt::format("store #{} {:08X} {:016X} {:016X}", i, x.guest, u, v));
    } else {
      d.first = fmt::format("store #{} {:08X} bytes differ", i, x.guest);
    }
  }
  if (d.first.empty() && a.visible.size() != b.visible.size())
    d.first = fmt::format("{} visible stores against {}", a.visible.size(), b.visible.size());
}

Diff CompareSides(const Side& a, const Side& b, const Policy& p) {
  Diff d;
  if (a.halted != b.halted || a.target != b.target ||
      (a.halted && a.site && b.site && a.site != b.site)) {
    d.first = fmt::format("exit {} {:08X}@{:08X} against {} {:08X}@{:08X}",
                          a.halted ? "boundary" : "return", a.target, a.site,
                          b.halted ? "boundary" : "return", b.target, b.site);
    return d;
  }
  CompareContexts(a.ctx, b.ctx, p, d);
  CompareStores(a, b, p, d);
  return d;
}

// The candidate copy's final visible bytes against memory after the real run.
std::string CompareWithMemory(const Side& candidate, uint8_t* base) {
  for (auto it = candidate.visible.rbegin(); it != candidate.visible.rend(); ++it) {
    for (size_t i = 0; i < it->bytes.size(); ++i) {
      // Only the newest store of a byte counts.
      const uint32_t at = it->guest + uint32_t(i);
      bool newer = false;
      for (auto later = candidate.visible.rbegin(); later != it && !newer; ++later)
        newer = at >= later->guest && at < later->guest + later->bytes.size();
      if (newer)
        continue;
      const uint8_t now = *rex::ppc::interp::detail::Host(base, at);
      if (now != it->bytes[i])
        return fmt::format("{:08X} copy {:02X} real {:02X}", at, it->bytes[i], now);
    }
  }
  return {};
}

void NoteMax(std::atomic<uint64_t>& slot, double ulps) {
  const uint64_t value = ulps > 1e18 ? UINT64_MAX : uint64_t(ulps);
  uint64_t seen = slot.load(std::memory_order_relaxed);
  while (value > seen && !slot.compare_exchange_weak(seen, value, std::memory_order_relaxed)) {
  }
}

std::string Hex64(uint64_t v) { return fmt::format("{:016X}", v); }

void LogMismatch(Region& region, const char* pair, const std::string& what,
                 const PPCContext& input, uint64_t call, const char* fault) {
  if (region.counters.logged.fetch_add(1, std::memory_order_relaxed) >= kMaxLoggedMismatches)
    return;
  diagnostics::RecordEvent("oracle.mismatch", {{"region", region.name},
                                               {"pair", pair},
                                               {"difference", what},
                                               {"call", std::to_string(call)},
                                               {"fault", fault},
                                               {"r3", Hex64(input.r3.u64)},
                                               {"r4", Hex64(input.r4.u64)},
                                               {"r5", Hex64(input.r5.u64)},
                                               {"r1", Hex64(input.r1.u64)}});
}

enum class Fault { kNone, kDrop, kReorder, kVolatile };

Fault ParseFault(const std::string& name) {
  if (name == "drop_store") return Fault::kDrop;
  if (name == "reorder_stores") return Fault::kReorder;
  if (name == "volatile_register") return Fault::kVolatile;
  return Fault::kNone;
}

const char* FaultName(Fault f) {
  switch (f) {
    case Fault::kDrop: return "drop_store";
    case Fault::kReorder: return "reorder_stores";
    case Fault::kVolatile: return "volatile_register";
    default: return "";
  }
}

void Check(Region& region, PPCFunc* run, PPCContext& ctx, uint8_t* base, uint64_t call) {
  Counters& c = region.counters;
  const PPCContext input = ctx;
  const uint32_t sp = input.r1.u32;
  const uint32_t frame_lo = sp > kFrameWindow ? sp - kFrameWindow : 0;
  const uint32_t frame_hi = sp;
  const Fault fault = ParseFault(REXCVAR_GET(pinyon_shift_region_oracle_fault));
  const HostFp fp;

  auto interp = std::make_unique<Side>();
  auto reference = std::make_unique<Side>();
  auto candidate = std::make_unique<Side>();
  interp->name = "interpreter";
  reference->name = "reference";
  candidate->name = "candidate";

  RunInterpreter(*interp, region, input, base, frame_lo, frame_hi);
  fp.Restore();
  RunCopy(*reference, region.reference, input, base, frame_lo, frame_hi, nullptr);
  fp.Restore();
  rex::ppc::RefFault seeded;
  if (fault == Fault::kDrop || fault == Fault::kReorder) {
    seeded.kind = fault == Fault::kDrop ? rex::ppc::RefFault::kDrop : rex::ppc::RefFault::kReorder;
    seeded.frame_lo = frame_lo;
    seeded.frame_hi = frame_hi;
  }
  RunCopy(*candidate, region.candidate, input, base, frame_lo, frame_hi,
          seeded.kind != rex::ppc::RefFault::kNone ? &seeded : nullptr);
  bool applied = seeded.applied;
  if (fault == Fault::kVolatile) {
    candidate->ctx.r10.u64 ^= 1;  // a volatile GPR a caller may read
    applied = true;
  }
  fp.Restore();

  // The real run: the game keeps its results.
  run(ctx, base);

  c.checked.fetch_add(1, std::memory_order_relaxed);
  c.visible_stores.fetch_add(reference->visible.size(), std::memory_order_relaxed);
  c.frame_stores.fetch_add(reference->frame_stores, std::memory_order_relaxed);
  (reference->halted ? c.halted : c.returned).fetch_add(1, std::memory_order_relaxed);

  const double tolerance = double(REXCVAR_GET(pinyon_shift_region_oracle_ulps));
  const char* fault_name = applied ? FaultName(fault) : "";

  if (!interp->available) {
    c.interp_unavailable.fetch_add(1, std::memory_order_relaxed);
    LogMismatch(region, "interpreter", interp->unavailable, input, call, fault_name);
  } else {
    const Diff d = CompareSides(*interp, *reference, Policy{false, false, tolerance});
    NoteMax(c.max_ulps, d.max_ulps);
    if (!d.first.empty()) {
      c.interp_mismatched.fetch_add(1, std::memory_order_relaxed);
      LogMismatch(region, "interpreter-reference", d.first, input, call, fault_name);
    }
  }

  const Diff d = CompareSides(*candidate, *reference, Policy{true, true, tolerance});
  NoteMax(c.max_ulps, d.max_ulps);
  if (!d.dead.empty())
    c.candidate_dead_volatile.fetch_add(1, std::memory_order_relaxed);
  const bool mismatch = !d.first.empty();
  if (mismatch) {
    c.candidate_mismatched.fetch_add(1, std::memory_order_relaxed);
    LogMismatch(region, "candidate-reference", d.first, input, call, fault_name);
  } else if (d.any_fp) {
    c.within_tolerance.fetch_add(1, std::memory_order_relaxed);
  }
  if (fault != Fault::kNone) {
    if (!applied) {
      c.faults_not_applicable.fetch_add(1, std::memory_order_relaxed);
    } else {
      c.faults_applied.fetch_add(1, std::memory_order_relaxed);
      if (mismatch)
        c.faults_caught.fetch_add(1, std::memory_order_relaxed);
    }
  } else if (!candidate->halted) {
    // The logged candidate is the code that runs: its stores are in memory.
    const std::string real = CompareWithMemory(*candidate, base);
    if (!real.empty()) {
      c.real_mismatched.fetch_add(1, std::memory_order_relaxed);
      LogMismatch(region, "candidate-real", real, input, call, "");
    }
  }
}

// Calls slower than this many ticks were interrupted (preempted, page
// faulted) and are counted apart: they would swamp the per-call means.
constexpr uint64_t kInterruptedTicks = 2'000'000;

void Dispatch(Region& region, PPCContext& ctx, uint8_t* base) {
  const uint32_t every = REXCVAR_GET(pinyon_shift_region_oracle);
  const uint32_t mode = region.native ? REXCVAR_GET(pinyon_shift_native_region) : 0;
  const uint64_t call = region.counters.calls.fetch_add(1, std::memory_order_relaxed);
  const int side = mode == 1 ? 1 : mode == 2 ? int(call & 1) : 0;
  PPCFunc* run = side ? region.native : region.original;
  if (every && call % every == 0) {
    Check(region, run, ctx, base, call);
    return;
  }
  if (mode != 2) {
    run(ctx, base);
    return;
  }
  const uint64_t t0 = Ticks();
  run(ctx, base);
  const uint64_t dt = Ticks() - t0;
  Region::Timing& timing = region.timing[side];
  if (dt > kInterruptedTicks) {
    timing.dropped.fetch_add(1, std::memory_order_relaxed);
    return;
  }
  timing.calls.fetch_add(1, std::memory_order_relaxed);
  timing.ticks.fetch_add(dt, std::memory_order_relaxed);
  timing.squares.fetch_add(dt * dt, std::memory_order_relaxed);
}

}  // namespace

void RecordSummary() {
  std::lock_guard lock(registry_mutex);
  for (Region* region : Registry()) {
    Counters& c = region->counters;
    auto n = [](const std::atomic<uint64_t>& v) {
      return std::to_string(v.load(std::memory_order_relaxed));
    };
    const uint64_t ulps = c.max_ulps.load(std::memory_order_relaxed);
    diagnostics::RecordEvent(
        "oracle.region",
        {{"region", region->name},
         {"ranges", std::to_string(region->ranges.size())},
         {"calls", n(c.calls)},
         {"checked", n(c.checked)},
         {"returned", n(c.returned)},
         {"halted", n(c.halted)},
         {"visible_stores", n(c.visible_stores)},
         {"frame_stores", n(c.frame_stores)},
         {"interp_mismatched", n(c.interp_mismatched)},
         {"interp_unavailable", n(c.interp_unavailable)},
         {"candidate_mismatched", n(c.candidate_mismatched)},
         {"within_tolerance", n(c.within_tolerance)},
         {"candidate_dead_volatile", n(c.candidate_dead_volatile)},
         {"real_mismatched", n(c.real_mismatched)},
         {"faults_applied", n(c.faults_applied)},
         {"faults_caught", n(c.faults_caught)},
         {"faults_not_applicable", n(c.faults_not_applicable)},
         {"tolerance_ulps", std::to_string(REXCVAR_GET(pinyon_shift_region_oracle_ulps))},
         {"fault", REXCVAR_GET(pinyon_shift_region_oracle_fault)},
         {"max_ulps", ulps == UINT64_MAX ? std::string("inf") : std::to_string(ulps)}});
    if (!region->native)
      continue;
    // The in-run A/B: mean ticks per call on each side with its standard
    // error, in nanoseconds through the counter's frequency.
    const double ns_per_tick = 1e9 / double(TicksPerSecond());
    std::vector<std::pair<std::string, std::string>> fields{
        {"region", region->name}, {"mode", std::to_string(REXCVAR_GET(pinyon_shift_native_region))}};
    for (int s = 0; s < 2; ++s) {
      const Region::Timing& timing = region->timing[s];
      const double n = double(timing.calls.load(std::memory_order_relaxed));
      const double mean = n ? double(timing.ticks.load(std::memory_order_relaxed)) / n : 0;
      const double var =
          n > 1 ? (double(timing.squares.load(std::memory_order_relaxed)) / n - mean * mean) * n /
                      (n - 1)
                : 0;
      const double se = n > 1 ? std::sqrt(std::max(var, 0.0) / n) : 0;
      const std::string key = s ? "native" : "generated";
      fields.emplace_back(key + "_calls", std::to_string(uint64_t(n)));
      fields.emplace_back(key + "_dropped",
                          std::to_string(timing.dropped.load(std::memory_order_relaxed)));
      fields.emplace_back(key + "_ns", fmt::format("{:.2f}", mean * ns_per_tick));
      fields.emplace_back(key + "_se_ns", fmt::format("{:.2f}", se * ns_per_tick));
    }
    std::vector<diagnostics::Field> view(fields.begin(), fields.end());
    diagnostics::RecordEvent("native.region", std::span<const diagnostics::Field>(view));
  }
}

}  // namespace pinyon_shift::guest_native::region_oracle

// One region per root: the strong `sub_X` routes through Dispatch, and the
// code ranges feed the interpreter's region test.
#define REX_ORACLE_REGION(address, name)                                                       \
  extern "C" REX_FUNC(__imp__##name);                                                          \
  extern "C" REX_FUNC(orr_##name);                                                             \
  extern "C" REX_FUNC(orc_##name);                                                             \
  namespace {                                                                                  \
  ::pinyon_shift::guest_native::region_oracle::Region oracle_region_##address{                 \
      #name, address, &__imp__##name, &orr_##name, &orc_##name, {}, {}};                       \
  ::pinyon_shift::guest_native::region_oracle::Registration oracle_registration_##address{     \
      oracle_region_##address};                                                                \
  }                                                                                            \
  extern "C" REX_FUNC(name) {                                                                  \
    ::pinyon_shift::guest_native::region_oracle::Dispatch(oracle_region_##address, ctx, base); \
  }
#define REX_ORACLE_RANGE(root, start, end)                                                     \
  namespace {                                                                                  \
  ::pinyon_shift::guest_native::region_oracle::RangeRegistration                               \
      REX_ORACLE_JOIN(oracle_range_, __LINE__){oracle_region_##root, start, end};              \
  }
#define REX_ORACLE_CRT(root, address, name)                                                    \
  namespace {                                                                                  \
  ::pinyon_shift::guest_native::region_oracle::CrtRegistration REX_ORACLE_JOIN(               \
      oracle_crt_, __LINE__){oracle_region_##root, address, #name};                            \
  }
#define REX_ORACLE_NATIVE(root, name)                                                          \
  extern "C" REX_FUNC(nr_##name);                                                              \
  extern "C" REX_FUNC(orn_root_##name);                                                        \
  namespace {                                                                                  \
  ::pinyon_shift::guest_native::region_oracle::NativeRegistration oracle_native_##root{        \
      oracle_region_##root, &nr_##name, &orn_root_##name};                                     \
  }
#define REX_ORACLE_JOIN2(a, b) a##b
#define REX_ORACLE_JOIN(a, b) REX_ORACLE_JOIN2(a, b)

// Generated beside the recompiled code; a frozen snapshot from an older
// generator has none, and then there are no regions.
#if __has_include("pinyon_shift_oracle.h")
#include "pinyon_shift_oracle.h"
#endif

// The logged CRT functions region copies call (one definition each, whatever
// regions use them).
#define REX_ORACLE_CRT_FUNCTION(name)                                                          \
  extern "C" REX_FUNC(orr_rexcrt_##name) {                                                     \
    ::rex::ppc::OracleCrtRun(::rex::ppc::OracleCrtByName(#name), ctx, base);                   \
  }                                                                                            \
  extern "C" REX_FUNC(orc_rexcrt_##name) {                                                     \
    ::rex::ppc::OracleCrtRun(::rex::ppc::OracleCrtByName(#name), ctx, base);                   \
  }                                                                                            \
  extern "C" REX_FUNC(orn_rexcrt_##name) {                                                     \
    ::rex::ppc::OracleCrtRun(::rex::ppc::OracleCrtByName(#name), ctx, base);                   \
  }
REX_ORACLE_CRT_FUNCTION(memcpy)
REX_ORACLE_CRT_FUNCTION(memmove)
REX_ORACLE_CRT_FUNCTION(memset)
