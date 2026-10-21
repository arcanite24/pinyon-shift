#pragma once

#include <array>
#include <cmath>

namespace pinyon_shift::camera {

// CameraSettings.ini's FollowLowCam / FollowHighCam blocks, in float order.
using Tuning = std::array<float, 14>;

struct Offset {
  float authored = 0, written = 0;
  bool initialized = false;

  float Apply(float current, float offset) {
    // A new car or camera reset can replace the per-car override at any time.
    if (!initialized || current != written) authored = current;
    initialized = true;
    written = authored + offset;
    return written;
  }
};

inline Tuning Adjust(Tuning stock, float height, float distance, float fov, float stiffness) {
  stock[0] += height;
  stock[3] += height;
  stock[4] += height;
  stock[1] += distance;
  stock[7] *= fov;
  // Preserve the damping ratio when changing the spring frequency.
  stock[8] *= stiffness;
  stock[9] *= std::sqrt(stiffness);
  stock[12] *= stiffness;
  stock[13] *= std::sqrt(stiffness);
  return stock;
}

}  // namespace pinyon_shift::camera
