#pragma once
// VR stereo (FB-12.15): the cockpit camera per frame for the OpenXR output's
// alternate-eye rendering (shiftglue-sdk rex/ui/vulkan/openxr.h). Each game
// frame asks for the next eye; the head tracking camera layers then take that
// eye's pose, and the field of view carries the frame's tag, so the presenter
// knows which eye a finished frame is and where it was seen from.

#include <cstdint>
#include <optional>

#include "head_tracking/head_tracking.h"

namespace pinyon_shift::vr {

// The headset's start space (x right, y up, -z forward, metres; orientation a
// unit quaternion x, y, z, w) as head tracking's pose: yaw, pitch and roll in
// degrees (look right, look up, tilt right) and x, y, z (right, up, forward).
head_tracking::Pose PoseFromHeadset(const float position[3], const float orientation[4]);

// Once per game frame: the next eye from the OpenXR output, or none.
void Update();

// This frame's eye as a camera offset, zero while VR stereo is off.
head_tracking::Pose CameraOffset();

// The vertical field of view with this frame's tag, and xr_fov_scale, while
// VR stereo runs; unchanged otherwise and for cube map cameras (90 degrees).
double TagFieldOfView(double fov_y);

// Whether the HUD is hidden for VR stereo (xr_hide_hud): drawn at the same
// place for both eyes, it would float at the wrong depth.
bool HidesHud();

}  // namespace pinyon_shift::vr
