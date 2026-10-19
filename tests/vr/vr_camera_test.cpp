// The headset's start space to head tracking's camera layer pose.

#include <cmath>
#include <cstdio>
#include <cstdlib>

#include "vr/vr_camera.h"

namespace {

int failures = 0;

void Near(float value, float expected, const char* what) {
  if (std::abs(value - expected) > 1e-3f) {
    std::printf("FAIL %s: %f, expected %f\n", what, value, expected);
    ++failures;
  }
}

// A rotation of `degrees` about the unit axis (x, y, z), as x, y, z, w.
void Quaternion(float x, float y, float z, float degrees, float out[4]) {
  const float half = degrees * 3.14159265f / 360.0f;
  out[0] = x * std::sin(half);
  out[1] = y * std::sin(half);
  out[2] = z * std::sin(half);
  out[3] = std::cos(half);
}

}  // namespace

int main() {
  using namespace pinyon_shift;
  const float origin[3] = {0.0f, 0.0f, 0.0f};
  float q[4];

  Quaternion(0, 1, 0, 0, q);
  auto pose = vr::PoseFromHeadset(origin, q);
  for (float value : pose) Near(value, 0.0f, "identity");

  // Looking right turns about +y by a negative angle (-z is forward).
  Quaternion(0, 1, 0, -30, q);
  pose = vr::PoseFromHeadset(origin, q);
  Near(pose[head_tracking::kYaw], 30.0f, "yaw right");
  Near(pose[head_tracking::kPitch], 0.0f, "yaw: pitch");
  Near(pose[head_tracking::kRoll], 0.0f, "yaw: roll");

  Quaternion(1, 0, 0, 15, q);
  pose = vr::PoseFromHeadset(origin, q);
  Near(pose[head_tracking::kPitch], 15.0f, "pitch up");
  Near(pose[head_tracking::kYaw], 0.0f, "pitch: yaw");

  // Tilting right turns about +z (towards the viewer) by a negative angle.
  Quaternion(0, 0, 1, -10, q);
  pose = vr::PoseFromHeadset(origin, q);
  Near(pose[head_tracking::kRoll], 10.0f, "roll right");
  Near(pose[head_tracking::kYaw], 0.0f, "roll: yaw");

  // Yaw then pitch: still read back as each.
  float yaw[4], pitch[4];
  Quaternion(0, 1, 0, -40, yaw);
  Quaternion(1, 0, 0, 20, pitch);
  const float combined[4] = {
      yaw[3] * pitch[0] + yaw[0] * pitch[3] + yaw[1] * pitch[2] - yaw[2] * pitch[1],
      yaw[3] * pitch[1] - yaw[0] * pitch[2] + yaw[1] * pitch[3] + yaw[2] * pitch[0],
      yaw[3] * pitch[2] + yaw[0] * pitch[1] - yaw[1] * pitch[0] + yaw[2] * pitch[3],
      yaw[3] * pitch[3] - yaw[0] * pitch[0] - yaw[1] * pitch[1] - yaw[2] * pitch[2]};
  pose = vr::PoseFromHeadset(origin, combined);
  Near(pose[head_tracking::kYaw], 40.0f, "combined yaw");
  Near(pose[head_tracking::kPitch], 20.0f, "combined pitch");
  Near(pose[head_tracking::kRoll], 0.0f, "combined roll");

  // Position: -z is forward.
  const float position[3] = {0.1f, 0.2f, -0.3f};
  Quaternion(0, 1, 0, 0, q);
  pose = vr::PoseFromHeadset(position, q);
  Near(pose[head_tracking::kX], 0.1f, "x right");
  Near(pose[head_tracking::kY], 0.2f, "y up");
  Near(pose[head_tracking::kZ], 0.3f, "z forward");

  if (failures == 0) std::printf("vr_camera: all checks passed\n");
  return failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
