// The headset's start space to head tracking's camera layer pose, and the
// per-frame bookkeeping of VR stereo with the OpenXR output simulated
// (xr_simulate): the flat path, eye order and tags, and paired steps.

#include <cmath>
#include <cstdio>
#include <cstdlib>

#include <rex/cvar.h>
#include <rex/ui/vulkan/openxr.h>

#include "vr/vr_camera.h"

namespace {

int failures = 0;

void Near(float value, float expected, const char* what) {
  if (std::abs(value - expected) > 1e-3f) {
    std::printf("FAIL %s: %f, expected %f\n", what, value, expected);
    ++failures;
  }
}

void Check(bool condition, const char* what) {
  if (!condition) {
    std::printf("FAIL %s\n", what);
    ++failures;
  }
}

// One title frame of a cockpit camera: the next eye, then its head layers.
// Returns the eye the layers took, from the camera offset's x (the eyes are
// half the simulated IPD either side).
int CockpitFrame() {
  pinyon_shift::vr::Update();
  pinyon_shift::vr::NoteLayersApplied();
  return pinyon_shift::vr::CameraOffset()[pinyon_shift::head_tracking::kX] > 0.0f ? 1 : 0;
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

  // Before VR stereo has run, every call is the flat result (no lock taken),
  // also after a frame's Update while VR is not configured.
  vr::Update();
  Check(!vr::InStereo(), "flat: not in stereo");
  Check(vr::TagFieldOfView(1.2) == 1.2, "flat: field of view untouched");
  Check(vr::PairStep(0.016) == 0.016, "flat: step untouched");
  Check(vr::AspectScale() == 0.0f, "flat: aspect untouched");
  Check(!vr::HidesHud(), "flat: HUD shown");
  Check(vr::CameraOffset() == head_tracking::Pose{}, "flat: no camera offset");

  rex::cvar::SetFlagByName("xr_simulate", "true");
  rex::cvar::SetFlagByName("xr_simulate_hz", "50");
  constexpr double kPeriod = 1.0 / 50.0;

  // Eye order: the eyes alternate, from the first eye of a pair. The field of
  // view's tag runs one camera update behind the layers (TagFieldOfView takes
  // the previous update's), and decodes (LensEye) to the eye the layers drew.
  int previous = CockpitFrame();
  CockpitFrame();
  previous = CockpitFrame();
  for (int frame = 0; frame < 12; ++frame) {
    const int eye = CockpitFrame();
    Check(eye != previous, "eyes alternate");
    previous = eye;
    Check(vr::InStereo(), "cockpit frames are in stereo");
    const double tagged = vr::TagFieldOfView(1.2);
    Check(std::abs(tagged - 1.2) <= 0.0011, "the tag changes the field of view by 0.001 at most");
    Check(rex::ui::vulkan::openxr::LensEye(float(tagged)) == eye,
          "the frame's tag names the eye its layers drew");
  }
  // A camera without head layers (a chase camera): the frame after still
  // counts, two later the frames are untagged and shown on the screen.
  vr::Update();
  Check(vr::InStereo(), "one frame without head layers: still in stereo");
  vr::Update();
  Check(!vr::InStereo(), "two frames without head layers: not in stereo");
  Check(vr::TagFieldOfView(1.2) == 1.2, "untagged without head layers");

  // Paired steps: the step after the first eye's update is the title's
  // shortest, the time it leaves out is banked, and the pair's step is a
  // whole number of headset frames, the rest carried: over many pairs no
  // game time is lost or invented beyond one headset frame.
  while (CockpitFrame() != rex::ui::vulkan::openxr::FirstEye()) {
  }
  CockpitFrame();
  double in = 0.0, out = 0.0;
  for (int pair = 0; pair < 40; ++pair) {
    const double first_step = 0.011 + 0.0005 * (pair % 7);
    Check(CockpitFrame() == rex::ui::vulkan::openxr::FirstEye(), "pair starts with the first eye");
    const double shortened = vr::PairStep(first_step);
    Check(shortened == 0.0001, "the first eye's step is the shortest");
    const double second_step = 0.009 + 0.0007 * (pair % 5);
    CockpitFrame();
    const double paired = vr::PairStep(second_step);
    const double frames = paired / kPeriod;
    Check(std::abs(frames - std::round(frames)) < 1e-6 && frames >= 1.0,
          "the pair's step is whole headset frames");
    in += first_step + second_step;
    out += shortened + paired;
  }
  Check(std::abs(out - in) <= kPeriod + 1e-9, "paired steps keep the game's time");

  if (failures == 0) std::printf("vr_camera: all checks passed\n");
  return failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
