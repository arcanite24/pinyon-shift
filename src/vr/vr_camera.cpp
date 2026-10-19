#include "vr/vr_camera.h"

#include <atomic>
#include <cmath>
#include <iterator>
#include <mutex>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ui/vulkan/openxr.h>

REXCVAR_DEFINE_DOUBLE(xr_fov_scale, 1.0, "Display",
                      "In VR stereo, scale the game's field of view (1.6 roughly fills a "
                      "Quest 3; the headset shows whatever the game renders at its true size)")
    .range(0.5, 2.5)
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_BOOL(xr_fov_match, true, "Display",
                    "In VR stereo, give the game's main camera the headset's vertical field of "
                    "view (times xr_fov_scale), so the cockpit fills the headset")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_BOOL(xr_hide_hud, true, "Display",
                    "Hide the game's HUD in VR stereo: it is drawn at the same place for "
                    "both eyes, so it floats at the wrong depth")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

namespace pinyon_shift::vr {

namespace {

constexpr double kDegrees = 57.29577951308232;
constexpr double kCubeFov = 1.5707963267948966;

// A frame's camera layers run before the frame tick that asks for the next
// eye, and its field of view after it: the layers take the request the
// previous tick made, so the field of view carries that request's tag
// (xr_simulate's eye check showed every frame on the other eye otherwise).
struct Latched {
  std::mutex mutex;
  bool active = false;
  head_tracking::Pose pose{};
  uint32_t tag = 0;
  bool previous_active = false;
  uint32_t previous_tag = 0;
  // The field of view getter serves every camera. The main camera is the
  // one whose output the presented frame's lens shows (PresentedFovY); its
  // input is remembered from the latest calls, and only it gets the
  // headset's field of view.
  struct Call {
    double input = 0.0;
    float output = 0.0f;
  };
  // Several frames of calls: the presented frame is a few frames old, and
  // every camera (shadows, reflections, mirrors) calls each frame.
  Call calls[1024];
  uint32_t next_call = 0;
  double main_input = 0.0;
};

// How close a call's input must be to the main camera's to count as it:
// mirrors and other views sit further away.
constexpr double kMainTolerance = 0.01;

Latched& L() {
  static Latched latched;
  return latched;
}

}  // namespace

head_tracking::Pose PoseFromHeadset(const float position[3], const float orientation[4]) {
  const double x = orientation[0], y = orientation[1], z = orientation[2], w = orientation[3];
  // The rotated forward (0, 0, -1) axis, and the up and right axes' y.
  const double fx = -2.0 * (x * z + w * y), fy = -2.0 * (y * z - w * x),
               fz = -(1.0 - 2.0 * (x * x + y * y));
  const double uy = 1.0 - 2.0 * (x * x + z * z);
  const double ry = 2.0 * (x * y + w * z);
  head_tracking::Pose pose{};
  pose[head_tracking::kYaw] = float(std::atan2(fx, -fz) * kDegrees);
  pose[head_tracking::kPitch] = float(std::atan2(fy, std::sqrt(fx * fx + fz * fz)) * kDegrees);
  pose[head_tracking::kRoll] = float(std::atan2(-ry, uy) * kDegrees);
  pose[head_tracking::kX] = position[0];
  pose[head_tracking::kY] = position[1];
  pose[head_tracking::kZ] = -position[2];
  return pose;
}

void Update() {
  rex::ui::vulkan::openxr::EyeRequest request;
  const bool active = rex::ui::vulkan::openxr::NextEye(request);
  Latched& l = L();
  std::lock_guard lock(l.mutex);
  l.previous_active = l.active;
  l.previous_tag = l.tag;
  // Which recent call produced what the headset was last shown.
  const float presented = rex::ui::vulkan::openxr::PresentedFovY();
  if (presented > 0.0f) {
    for (const Latched::Call& call : l.calls) {
      if (call.output > 0.0f && std::abs(call.output - presented) < 2e-6f) {
        if (std::abs(call.input - l.main_input) > 1e-6) {
          REXLOG_INFO("VR: the main camera's field of view is {:.4f} rad (shown {:.4f})",
                      call.input, presented);
        }
        l.main_input = call.input;
        break;
      }
    }
  }
  l.active = active;
  if (!active) return;
  l.pose = PoseFromHeadset(request.position, request.orientation);
  l.tag = request.tag;
}

head_tracking::Pose CameraOffset() {
  Latched& l = L();
  std::lock_guard lock(l.mutex);
  return l.active ? l.pose : head_tracking::Pose{};
}

double TagFieldOfView(double fov_y) {
  Latched& l = L();
  std::lock_guard lock(l.mutex);
  if (!l.previous_active || std::abs(fov_y - kCubeFov) < 0.01) return fov_y;
  double base = fov_y;
  const double headset = rex::ui::vulkan::openxr::HeadsetFovY();
  if (REXCVAR_GET(xr_fov_match) && headset > 0.0 && l.main_input > 0.0 &&
      std::abs(fov_y - l.main_input) < kMainTolerance) {
    base = headset;
  }
  const double tagged =
      rex::ui::vulkan::openxr::TagFov(base * REXCVAR_GET(xr_fov_scale), l.previous_tag);
  l.calls[l.next_call++ % std::size(l.calls)] = {fov_y, float(tagged)};
  return tagged;
}

bool HidesHud() {
  Latched& l = L();
  std::lock_guard lock(l.mutex);
  return l.active && REXCVAR_GET(xr_hide_hud);
}

}  // namespace pinyon_shift::vr
