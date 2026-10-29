#include "vr/vr_camera.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <iterator>
#include <mutex>
#include <thread>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ui/vulkan/openxr.h>
#include <rex/ui/xr.h>

REXCVAR_DEFINE_DOUBLE(xr_fov_scale, 1.0, "Display",
                      "In VR stereo, scale the game's field of view (1.6 roughly fills a "
                      "Quest 3; the headset shows whatever the game renders at its true size)")
    .range(0.5, 2.5)
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_BOOL(xr_fov_match, true, "Display",
                    "In VR stereo, give the game's main camera the headset's vertical field of "
                    "view (times xr_fov_scale), so the cockpit fills the headset")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_DOUBLE(xr_render_aspect, 0.0, "Display",
                      "In VR stereo, the width / height the main view renders at: 0 follows "
                      "the headset's eyes (about 1.2 on a Quest 3), 1.778 keeps 16:9")
    .range(0.0, 3.0)
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_INT32(xr_simulate_hitch_ms, 0, "Display",
                     "Testing: stall the game thread this long every 300 frames while VR "
                     "stereo runs, to check the eyes survive a hitch")
    .range(0, 1000)
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_BOOL(xr_paired_steps, true, "Display",
                    "In VR stereo, show both eyes the same moment of the game: the step "
                    "rendered for the right eye takes almost no time and the next one makes "
                    "it up. Off, the world moves between the eyes' frames and shows false depth")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_INT32(xr_log_steps, 0, "Display",
                     "Testing: log each simulation step's time in and out of the VR paired "
                     "steps for this many steps from when it is set")
    .range(0, 2000)
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_INT32(xr_rotation_delay, 2, "Display",
                     "Testing: how many camera updates late the VR eye's rotation goes to the "
                     "rotation layers (0 the latest request)")
    .range(0, 3)
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_BOOL(xr_hide_hud, true, "Display",
                    "Hide the game's HUD in VR stereo: it is drawn at the same place for "
                    "both eyes, so it floats at the wrong depth")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);
REXCVAR_DEFINE_STRING(xr_render_scale, "", "Display",
                      "The draw resolution scale while VR is on (xr_enabled), across x down "
                      "such as 2x4; it replaces draw_resolution_scale_x and _y for the run, so "
                      "the flat resolution stays as it was. Empty: draw_resolution_scale_x and _y")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);
REXCVAR_DEFINE_BOOL(xr_camera_shake, false, "Display",
                    "Keep the immersive camera's speed shake and braking vibration, and the "
                    "game's speed shake and road-bump and tyre-slip vibration, in VR: the "
                    "headset did not make that motion, so it reads as the world shaking")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

REXCVAR_DECLARE(bool, xr_enabled);
REXCVAR_DECLARE(bool, xr_simulate);
REXCVAR_DECLARE(bool, xr_stereo);

namespace pinyon_shift::vr {

namespace {

constexpr double kDegrees = 57.29577951308232;
constexpr double kCubeFov = 1.5707963267948966;

// The camera layers take the latest request, but the camera renders what its
// layers were given one camera update earlier. So the layers record the tag
// of each update's request, and the field of view takes the previous
// update's: the camera and its tag come from one request however the ticks
// fall. (xr_simulate's eye check found every frame on the other eye with
// the latest update's tag, and with the tick's own.)
struct Latched {
  std::mutex mutex;
  bool active = false;
  head_tracking::Pose pose{};
  uint32_t tag = 0;
  int eye = 0;
  uint64_t ticks = 0;
  // The requests the layers applied in their last two updates, and at which
  // ticks (an update's six layers share a tick).
  bool applied = false;
  uint32_t applied_tag = 0, previous_applied_tag = 0;
  int applied_eye = 0;
  // The poses the layers took in their last four updates: the rotation
  // layers get an earlier one than the position layers (CameraOffset).
  head_tracking::Pose applied_pose{}, previous_applied_pose{}, older_applied_pose{},
      oldest_applied_pose{};
  uint64_t applied_tick = 0, updates = 0;
  // PairStep: game time the shortened steps left out, for the next step.
  double banked = 0.0;
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

// VR stereo has run in this process (an eye was requested). Until then every
// call below returns its flat result without taking the mutex: they run on
// hot paths (every camera's field of view, every simulation step, every
// frame's HUD and aspect) for players who never turn VR on.
std::atomic<bool> g_engaged{false};

bool Engaged() {
  return g_engaged.load(std::memory_order_relaxed);
}

// The layers applied an eye in this frame (before its tick) or the last:
// cockpit and hood cameras; other cameras' frames stay untagged.
bool LayersCurrent(const Latched& l) {
  return l.active && l.updates >= 2 && l.ticks - l.applied_tick <= 1;
}

}  // namespace

static double PairStepImpl(double seconds);

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
  if (const int hitch = REXCVAR_GET(xr_simulate_hitch_ms); hitch > 0) {
    static uint32_t frames = 0;
    if (++frames % 300 == 0) std::this_thread::sleep_for(std::chrono::milliseconds(hitch));
  }
  if (!Engaged() && !StereoConfigured()) return;
  rex::ui::vulkan::openxr::EyeRequest request;
  const bool active = rex::ui::vulkan::openxr::NextEye(request);
  if (active) g_engaged.store(true, std::memory_order_relaxed);
  Latched& l = L();
  std::lock_guard lock(l.mutex);
  ++l.ticks;
  // Which recent call produced what the headset was last shown, newest
  // first. A frame already given the headset's field of view says nothing:
  // every matched camera's output is the same, so the main camera is only
  // learnt again from an unmatched one (after a camera change).
  const float presented = rex::ui::vulkan::openxr::PresentedFovY();
  const double matched = rex::ui::vulkan::openxr::HeadsetFovY() * REXCVAR_GET(xr_fov_scale);
  const bool was_matched = REXCVAR_GET(xr_fov_match) && l.main_input > 0.0 && matched > 0.0 &&
                           std::abs(presented - matched) < 0.003;
  if (presented > 0.0f && !was_matched) {
    for (uint32_t i = 1; i <= std::size(l.calls); ++i) {
      const Latched::Call& call = l.calls[(l.next_call - i) % std::size(l.calls)];
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
  l.eye = request.eye;
}

head_tracking::Pose CameraOffset() {
  if (!Engaged()) return {};
  Latched& l = L();
  std::lock_guard lock(l.mutex);
  if (!l.active) return {};
  // A frame's image shows its rotation layers' factors from two updates
  // after its own request: with a simulated head turning, the rotation layers
  // given the latest request or the update before's drew the eye drawn
  // second with the next pair's turn (the scenery, dashboard and pillar
  // matched the next request to 1 px rms and its own to 15-20 px), and the
  // headset corrected it by the wrong turn, so that eye shook while the
  // other held still. Given the pose of two updates before, both eyes'
  // images match their own request (1 px rms). The rendered heading read
  // from the world's matrices is an update off from the image, so it is
  // not used to time this.
  head_tracking::Pose pose = l.pose;
  const head_tracking::Pose* const sources[] = {&l.pose, &l.previous_applied_pose,
                                                &l.older_applied_pose, &l.oldest_applied_pose};
  const head_tracking::Pose& rotation = *sources[std::clamp(REXCVAR_GET(xr_rotation_delay), 0, 3)];
  for (const auto axis : {head_tracking::kYaw, head_tracking::kPitch, head_tracking::kRoll}) {
    pose[axis] = rotation[axis];
  }
  return pose;
}

double TagFieldOfView(double fov_y) {
  if (!Engaged()) return fov_y;
  Latched& l = L();
  std::lock_guard lock(l.mutex);
  if (!LayersCurrent(l) || std::abs(fov_y - kCubeFov) < 0.01) return fov_y;
  double base = fov_y;
  const double headset = rex::ui::vulkan::openxr::HeadsetFovY();
  if (REXCVAR_GET(xr_fov_match) && headset > 0.0 && l.main_input > 0.0 &&
      std::abs(fov_y - l.main_input) < kMainTolerance) {
    base = headset;
  }
  const double tagged =
      rex::ui::vulkan::openxr::TagFov(base * REXCVAR_GET(xr_fov_scale), l.previous_applied_tag);
  l.calls[l.next_call++ % std::size(l.calls)] = {fov_y, float(tagged)};
  return tagged;
}

void NoteLayersApplied() {
  if (!Engaged()) return;
  Latched& l = L();
  std::lock_guard lock(l.mutex);
  if (!l.active || (l.applied && l.applied_tick == l.ticks)) return;
  l.previous_applied_tag = l.applied_tag;
  ++l.updates;
  l.applied = true;
  l.applied_tag = l.tag;
  l.applied_eye = l.eye;
  l.oldest_applied_pose = l.older_applied_pose;
  l.older_applied_pose = l.previous_applied_pose;
  l.previous_applied_pose = l.applied_pose;
  l.applied_pose = l.pose;
  l.applied_tick = l.ticks;
}

bool StereoConfigured() {
  return (REXCVAR_GET(xr_enabled) || REXCVAR_GET(xr_simulate)) && REXCVAR_GET(xr_stereo);
}

bool InVr() {
  return REXCVAR_GET(xr_enabled) || REXCVAR_GET(xr_simulate);
}

bool KeepsCameraShake() {
  return !StereoConfigured() || REXCVAR_GET(xr_camera_shake);
}

bool InStereo() {
  if (!Engaged()) return false;
  Latched& l = L();
  std::lock_guard lock(l.mutex);
  return LayersCurrent(l);
}

double PairStep(double seconds) {
  if (!Engaged()) return seconds;
  const double in = seconds;
  const double out = PairStepImpl(seconds);
  static int32_t last_setting = 0, remaining = 0;
  const int32_t setting = REXCVAR_GET(xr_log_steps);
  if (setting != last_setting) remaining = setting;
  last_setting = setting;
  if (remaining > 0) {
    --remaining;
    REXLOG_INFO("VR step: in {:.3f} ms, out {:.3f} ms", in * 1000.0, out * 1000.0);
  }
  return out;
}

static double PairStepImpl(double seconds) {
  // The title's own smallest step (it holds the delta to at least this).
  constexpr double kShortStep = 0.0001;
  // A long hitch is not replayed in one step.
  constexpr double kMaxBank = 0.1;
  Latched& l = L();
  std::lock_guard lock(l.mutex);
  // A pair is the eye drawn first and the other one after it, and its two
  // images must show the world at one moment. The image of the eye drawn
  // second shows the world of the step after the one whose layers took the
  // first eye's request, so the short step is the one after the first eye's
  // update. With the other eye's step shortened, driving at 100-170 km/h while
  // looking out the side window, the road moved 160-210 px between a pair's
  // images and only by the eyes' own parallax (20 px, as at a standstill)
  // from a pair to the next: the eyes were a whole step apart, the world
  // looked small and the ground close. The world's matrices drawn with each
  // frame say the opposite (6 cm within pairs, 40-67 cm between them); they
  // are a frame off from the images, as for the rotation (CameraOffset).
  const bool paired = REXCVAR_GET(xr_paired_steps) && LayersCurrent(l);
  if (paired && l.applied_eye == rex::ui::vulkan::openxr::FirstEye() && seconds > kShortStep) {
    l.banked = std::min(l.banked + seconds - kShortStep, kMaxBank);
    return kShortStep;
  }
  const double elapsed = seconds + l.banked;
  l.banked = 0.0;
  // The headset shows one pair per headset frame at an even rate, but the
  // title's steps follow its millisecond clock and the frames' uneven
  // timing (6 to 19 ms a step, 21 to 45 ms a pair at 90 fps on a Quest 3):
  // the world jumped on the headset. A pair's step is a whole number of
  // headset frames instead, and the rest of the time carries to the next.
  const uint32_t headset_hz = rex::ui::xr::HeadsetFrameHz();
  if (!paired || headset_hz == 0) return elapsed;
  const double period = 1.0 / double(headset_hz);
  const double frames = std::max(1.0, std::round(elapsed / period));
  const double step = frames * period;
  l.banked = std::clamp(elapsed - step, -period, kMaxBank);
  return step;
}

float AspectScale() {
  if (!Engaged()) return 0.0f;
  {
    Latched& l = L();
    std::lock_guard lock(l.mutex);
    if (!l.active || !LayersCurrent(l)) return 0.0f;
  }
  double aspect = REXCVAR_GET(xr_render_aspect);
  if (aspect <= 0.0) {
    const double fov_x = rex::ui::vulkan::openxr::HeadsetFovX();
    const double fov_y = rex::ui::vulkan::openxr::HeadsetFovY();
    if (!(fov_x > 0.0 && fov_y > 0.0)) return 0.0f;
    aspect = std::tan(fov_x * 0.5) / std::tan(fov_y * 0.5);
  }
  // The game's main view is 16:9; the hook scales its width / height.
  return float(std::clamp(aspect / (16.0 / 9.0), 0.3, 1.5));
}

bool HidesHud() {
  if (!InVr()) return false;
  // With the panel off (xr_hud_panel: the launcher's "Hide the HUD" and the
  // HUD key in VR) the HUD is hidden for the whole VR run, on the screen
  // views too, so the one switch means one thing; with it on, the HUD is on
  // the panel in stereo and in the screen's image elsewhere.
  return REXCVAR_GET(xr_hide_hud) && rex::cvar::GetFlagByName("xr_hud_panel") != "true";
}

}  // namespace pinyon_shift::vr
