#include "cheats_destination.h"

#include <cassert>
#include <limits>

int main() {
  using namespace pinyon_shift::cheats;
  const auto point = ParseDestination("-1234.5, 67.25,9000");
  assert(point && (*point == Destination{-1234.5f, 67.25f, 9000.0f}));
  assert(ParseDestination("0,0,0"));
  for (const auto bad : {"", "1,2", "1,2,3,4", "1,,3", "1,2,3m", "1,2,3,",
                         "nan,2,3", "1,inf,3", "1,2,1e100", "100001,2,3"})
    assert(!ParseDestination(bad));
  assert(!ValidDestination({0, std::numeric_limits<float>::infinity(), 0}));
  assert(!ValidDestination({0, 0, std::numeric_limits<float>::quiet_NaN()}));
}
