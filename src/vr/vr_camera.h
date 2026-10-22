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

// The head tracking layers took the offset this frame. Only the cockpit and
// hood cameras have them: other cameras' frames go untagged, and show on
// the VR screen instead of in stereo.
void NoteLayersApplied();

// The vertical field of view with this frame's tag, and xr_fov_scale, while
// VR stereo runs; unchanged otherwise and for cube map cameras (90 degrees).
double TagFieldOfView(double fov_y);

// Whether this frame renders an eye in VR stereo: the cockpit and hood
// cameras while the headset (or xr_simulate) runs. Depth of field stays off
// then, since the eyes' swap reads as camera motion.
bool InStereo();

// Whether this run may render VR stereo (xr_enabled or xr_simulate, with
// xr_stereo), known at start. The game reads its motion blur switch once,
// when it sets up post-processing, so the blur goes by this instead of
// InStereo: the right eye's short step made it a smear across the frame.
bool StereoConfigured();

// The simulation step (the title's delta, in seconds) for VR stereo's paired
// eyes (xr_paired_steps): the step a right eye's frame is rendered from takes
// the title's smallest step, and the next one makes up the time, so each left
// and right frame show the same moment of the game and the world's motion
// does not read as depth. Unchanged outside stereo.
double PairStep(double seconds);

// Whether the HUD is hidden for VR stereo (xr_hide_hud): drawn at the same
// place for both eyes, it would float at the wrong depth. Not while the
// headset shows it on a panel of its own (xr_hud_panel).
bool HidesHud();

// In VR stereo, the main view's aspect scale (the viewport aspect hook's) for
// the headset eye's shape instead of 16:9, so no rendered pixel falls outside
// the eye's view; 0 otherwise. The headset is told the true field of view, so
// the picture is not distorted, and a taller render (draw_resolution_scale_y)
// then sharpens it.
float AspectScale();

}  // namespace pinyon_shift::vr
