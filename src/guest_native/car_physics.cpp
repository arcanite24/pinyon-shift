// Car physics (#1071 P1): the physics world's per-body step.
//
// The physics-world step (base sub_82D4DE30, below CPhysicsWorld slot 22
// sub_82D4E2E0) walks its bodies and calls sub_82D46EF8(world, body, dt,
// ..., r6) for each one, on the simulation thread and from the islands
// jobs on the workers. The step clears a flag at body+2731, runs a body
// update, and then either the dynamics step sub_82D3A528 (body+2756 zero)
// or another update. Everything under it is about half of the physics
// time.
//
// pinyon_shift_physics_body_probe logs the bodies stepped, how often and
// with which dt, beside the cars of the world's car vector, so a body can
// be matched to its car: a car's ICarDynamics (car+0x2D90) sits at
// body+0xAD0. One step a simulation tick: 8.33 ms at 120 fps on the
// desktop, 16.67 ms at 60 fps on the Deck. The player's body always takes
// the dynamics step; AI bodies switch between it and the other branch as
// the race goes (2-6 of 7 on the dynamics step on the Deck).
//
// pinyon_shift_physics_ai_step_interval N > 1 runs an AI body's dynamics
// step on one tick in N with the summed time, staggered so the AI bodies
// share the ticks; the player's body steps every tick.

#include <algorithm>
#include <bit>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <mutex>
#include <string>
#include <unordered_map>

#include <fmt/format.h>
#include <rex/cvar.h>
#include <rex/ppc/context.h>
#include <rex/ppc/func.h>
#include <rex/system/xmemory.h>

#include "fh1_guest_address.h"
#include "guest_native/guest_native.h"
#include "pinyon_shift_diagnostics.h"

REXCVAR_DEFINE_BOOL(pinyon_shift_physics_body_probe, false, "Pinyon Shift",
                    "Diagnostic (#1071): log the physics bodies stepped each second "
                    "beside the world's cars")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_UINT32(pinyon_shift_physics_ai_step_interval, 1, "Pinyon Shift",
                      "Step AI cars' full dynamics on one simulation tick in N with the "
                      "summed time; the player's car steps every tick (#1071; 1 = every tick)")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

namespace pinyon_shift::guest_native {
namespace {

constexpr bool kV4 = pinyon_shift::fh1::kTitleUpdateV4;

uint8_t* Host(uint8_t* base, uint32_t address) {
  return base + address + rex::memory::detail::PhysicalHostOffset(address);
}
uint32_t LoadU32(uint8_t* base, uint32_t address) {
  uint32_t value;
  std::memcpy(&value, Host(base, address), sizeof(value));
  return std::byteswap(value);
}

bool ProbeEnabled() { return REXCVAR_GET(pinyon_shift_physics_body_probe); }
uint32_t AiInterval() { return REXCVAR_GET(pinyon_shift_physics_ai_step_interval); }
bool Enabled() { return ProbeEnabled() || AiInterval() > 1; }

// The world's car vector: [[[0x832DF024] + 4] + 4] + 128/132.
template <typename Visit>
void ForEachCar(uint8_t* base, Visit visit) {
  const uint32_t holder = LoadU32(base, FH1_ADDR(0x832DF024u));
  const uint32_t manager = holder ? LoadU32(base, holder + 4) : 0;
  const uint32_t world = manager ? LoadU32(base, manager + 4) : 0;
  if (!world) return;
  const uint32_t begin = LoadU32(base, world + 128), end = LoadU32(base, world + 132);
  for (uint32_t entry = begin; entry < end && entry - begin < 4 * 64; entry += 4) {
    const uint32_t car = LoadU32(base, entry);
    if (car) visit(car);
  }
}

struct AiBody {
  bool ai = false;
  uint32_t phase = 0;
  uint32_t ticks = 0;
  double carried = 0.0;
};
std::mutex ai_mutex;
std::unordered_map<uint32_t, AiBody> ai_bodies;
uint32_t ai_count = 0;
auto ai_since = std::chrono::steady_clock::now();

// Whether the body is an AI car's (driver not 0), by its ICarDynamics.
bool IsAiBody(uint8_t* base, uint32_t body) {
  bool ai = false;
  ForEachCar(base, [&](uint32_t car) {
    if (LoadU32(base, car + 0x2D90) == body + 0xAD0) ai = int32_t(LoadU32(base, car + 11728)) != 0;
  });
  return ai;
}

// True when this tick's dynamics step of an AI body is skipped.
bool SkipAiStep(PPCContext& ctx, uint8_t* base, uint32_t body) {
  const uint32_t interval = AiInterval();
  std::lock_guard lock(ai_mutex);
  const auto now = std::chrono::steady_clock::now();
  if (now - ai_since >= std::chrono::seconds(2)) {
    // Cars come and go between events; look them up again.
    ai_since = now;
    ai_bodies.clear();
    ai_count = 0;
  }
  auto [it, added] = ai_bodies.try_emplace(body);
  AiBody& state = it->second;
  if (added) {
    state.ai = IsAiBody(base, body);
    state.phase = state.ai ? ai_count++ : 0;
  }
  if (!state.ai || interval <= 1) return false;
  if ((state.ticks++ + state.phase) % interval != 0) {
    state.carried += ctx.f1.f64;
    return true;
  }
  ctx.f1.f64 += state.carried;
  state.carried = 0.0;
  return false;
}

struct BodyCount {
  uint32_t calls = 0;
  uint32_t car_path = 0;  // body+2756 zero: the dynamics step
  double dt_sum = 0.0;
};

std::mutex probe_mutex;
std::unordered_map<uint32_t, BodyCount> probe_bodies;
auto probe_since = std::chrono::steady_clock::now();

void EmitProbe(uint8_t* base) {
  // Each car's ICarDynamics (+0x2D90) and driver, to match bodies to cars.
  std::string cars;
  ForEachCar(base, [&](uint32_t car) {
    cars += fmt::format("{}{:08X}:{:08X}:{}", cars.empty() ? "" : "|", car,
                        LoadU32(base, car + 0x2D90), int32_t(LoadU32(base, car + 11728)));
  });
  std::string bodies;
  for (const auto& [body, count] : probe_bodies) {
    bodies += fmt::format("{}{:08X}:{}:{}:{:.5f}", bodies.empty() ? "" : "|", body, count.calls,
                          count.car_path, count.calls ? count.dt_sum / count.calls : 0.0);
  }
  diagnostics::RecordEvent("physics.body_probe",
                           {{"bodies", bodies}, {"count", fmt::format("{}", probe_bodies.size())},
                            {"cars", cars}});
  probe_bodies.clear();
}

bool BodyStepNative(PPCContext& ctx, uint8_t* base) {
  const uint32_t body = ctx.r4.u32;
  const bool car_path = body && LoadU32(base, body + 2756) == 0;
  if (car_path && AiInterval() > 1 && SkipAiStep(ctx, base, body)) return true;
  if (!ProbeEnabled()) return false;
  std::lock_guard lock(probe_mutex);
  auto& count = probe_bodies[body];
  ++count.calls;
  count.car_path += car_path;
  count.dt_sum += ctx.f1.f64;
  const auto now = std::chrono::steady_clock::now();
  if (now - probe_since >= std::chrono::seconds(1)) {
    probe_since = now;
    EmitProbe(base);
  }
  return false;  // the original step runs
}

Replacement body_step_replacement = {
    .name = "physics.body_step",
    .guest_address = kV4 ? 0x82E08FF8u : 0x82D46EF8u,
    .guest_code_size = 148,
    .guest_code_fnv1a = kV4 ? 0xA4510033DE362EC0ull : 0xF542A29CC13785D8ull,
    .returns = kReturnNone,
    .enabled = Enabled,
    .native = BodyStepNative,
    .written = nullptr,
};

}  // namespace
}  // namespace pinyon_shift::guest_native

PINYON_GUEST_NATIVE(82D46EF8, 82E08FF8, ::pinyon_shift::guest_native::body_step_replacement)
