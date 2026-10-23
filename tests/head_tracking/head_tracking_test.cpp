#include <cstdio>
#include <cstring>
#include <limits>
#include "head_tracking/head_tracking.h"

using namespace pinyon_shift::head_tracking;
static int failures = 0;
#define CHECK(c) do { if (!(c)) { std::fprintf(stderr, "%d: %s\n", __LINE__, #c); ++failures; } } while (false)

int main() {
  // OpenTrack: x, y, z in cm, then yaw, pitch, roll in degrees.
  const double values[6] = {2.0, -3.0, 50.0, 30.0, -10.0, 5.0};
  uint8_t packet[48];
  std::memcpy(packet, values, sizeof(packet));
  const auto pose = ParseOpenTrack(packet);
  CHECK(pose.has_value());
  if (pose) {
    CHECK((*pose)[kYaw] == 30.0f && (*pose)[kPitch] == -10.0f && (*pose)[kRoll] == 5.0f);
    CHECK((*pose)[kX] == 0.02f && (*pose)[kY] == -0.03f && (*pose)[kZ] == 0.5f);
  }
  CHECK(!ParseOpenTrack({packet, 40}));
  const double bad[6] = {std::numeric_limits<double>::quiet_NaN(), 0, 0,
                         std::numeric_limits<double>::infinity(), 0, 0};
  std::memcpy(packet, bad, sizeof(packet));
  const auto cleaned = ParseOpenTrack(packet);
  CHECK(cleaned && (*cleaned)[kX] == 0.0f && (*cleaned)[kYaw] == 0.0f);

  const auto invert = ParseInvert("yaw, z,bogus");
  CHECK(invert[kYaw] && invert[kZ] && !invert[kPitch] && !invert[kRoll] && !invert[kX]);
  CHECK(ParseInvert("") == (std::array<bool, 6>{}));

  if (failures) {
    std::fprintf(stderr, "%d failure(s)\n", failures);
    return 1;
  }
  std::printf("head tracking tests passed\n");
  return 0;
}
