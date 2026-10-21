#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <utility>
#include <vector>

#include <rex/cvar.h>

#include "cheats.h"
#include "pinyon_shift_diagnostics.h"
#include "save/profile_body.h"

// Diagnostics are not part of the profile mutation contract.
namespace pinyon_shift::diagnostics {
void RecordEvent(std::string_view, std::initializer_list<Field>) {}
}

namespace {
void Be32(std::vector<uint8_t>& body, uint32_t value) {
  for (int shift : {24, 16, 8, 0}) body.push_back(uint8_t(value >> shift));
}
void Field(std::vector<uint8_t>& body, std::string_view name, uint8_t type) {
  Be32(body, uint32_t(name.size()));
  body.insert(body.end(), name.begin(), name.end());
  Be32(body, 0x20);
  Be32(body, 0);
  body.push_back(type);
}
std::vector<uint8_t> Body() {
  std::vector<uint8_t> body;
  Be32(body, 1);
  Field(body, "Main", 0x0F);
  Be32(body, 3);
  for (const auto& [name, value] :
       {std::pair{"Credits", 167700u}, {"CareerCar", 7u}, {"XP", 820u}}) {
    Field(body, name, 0x03);
    Be32(body, value);
  }
  body.insert(body.end(), 8, 0xBB);
  return body;
}
void Set(std::string_view name, std::string_view value) {
  assert(rex::cvar::SetFlagByName(name, value));
}
}

int main() {
  using namespace pinyon_shift;
  Set("pinyon_shift_cheats", "false");
  Set("cheat_set_credits", "12345");
  Set("cheat_time_scale", "2.0");
  Set("cheat_free_camera", "true");
  Set("cheat_any_car_events", "true");
  const auto original = Body();
  auto body = original;
  Set("cheat_set_profile_fields", cheats::kCarRecoveryFields);
  assert(cheats::CarRecoveryRequested());
  cheats::EditLoadedProfile(body.data(), body.size());
  assert(body == original);  // An unisolated profile must never be edited.
  cheats::SetProfileIsolated();
  Set("cheat_set_profile_fields", "Main/CareerCar=0,Main/XP=1000");
  assert(!cheats::CarRecoveryRequested());
  cheats::EditLoadedProfile(body.data(), body.size());
  assert(body == original);  // The recovery exception cannot enable other edits.
  int applied = 0;
  cheats::SetAppliedCallback([&](std::string_view setting) {
    assert(setting == "cheat_set_profile_fields");
    ++applied;
    Set(setting, "");
  });
  Set("cheat_set_profile_fields", cheats::kCarRecoveryFields);
  cheats::EditLoadedProfile(body.data(), body.size());
  auto expected = original;
  const auto car = save::FindProfileField(body.data(), body.size(), "Main/CareerCar");
  assert(car && car->size == 4);
  std::memset(expected.data() + car->offset, 0, 4);
  assert(body == expected && applied == 1);
  assert(!cheats::CarRecoveryRequested() && !cheats::Enabled());
  assert(cheats::TimeScale() == 1.0 && !cheats::FreeCamera() && !cheats::AnyCarInEvents());
  assert(!cheats::CreditsPending());
  Set("cheat_set_profile_fields", cheats::kCarRecoveryFields);
  body = original;
  cheats::EditLoadedProfile(body.data(), body.size());
  assert(body == original && applied == 1);  // Once per process, even if re-armed.
  std::puts("car recovery tests passed");
}
