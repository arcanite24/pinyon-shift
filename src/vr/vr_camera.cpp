#include "vr/vr_camera.h"

#include <atomic>
#include <cmath>
#include <mutex>

#include <rex/cvar.h>
#include <rex/ui/vulkan/openxr.h>

REXCVAR_DEFINE_DOUBLE(xr_fov_scale, 1.0, "Display",
                      "In VR stereo, scale the game's field of view (1.6 roughly fills a "
                      "Quest 3; the headset shows whatever the game renders at its true size)")
    .range(0.5, 2.5)
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
};

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
  return rex::ui::vulkan::openxr::TagFov(fov_y * REXCVAR_GET(xr_fov_scale), l.previous_tag);
}

}  // namespace pinyon_shift::vr
