#include "ui/touch_pad.h"
#if defined(__ANDROID__)
#include <jni.h>
#include <SDL3/SDL_system.h>
#include <rex/chrono/clock.h>
#include <rex/perf/counter.h>
#endif

#include <algorithm>
#include <cmath>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ui/ui_event.h>
#include <rex/ui/window.h>

namespace pinyon_shift::ui {
namespace {

using rex::input::DeviceId;
using rex::X_RESULT;
using rex::X_STATUS;

constexpr DeviceId kTouchDevice = static_cast<DeviceId>(0x54434850);  // TCHP
// Hidden this long after the last touch: a controller player never sees it.
constexpr auto kVisibleAfterTouch = std::chrono::seconds(20);
// The stick's travel, as a fraction of the window height.
constexpr float kStickTravel = 0.11f;

class TouchPadDriver final : public rex::input::InputDriver {
 public:
  explicit TouchPadDriver(TouchPad& pad) : InputDriver(nullptr, 0), pad_(pad) {}
  X_STATUS Setup() override { return X_STATUS_SUCCESS; }
  void EnumerateDevices(std::vector<rex::input::DeviceInfo>& out) override {
    rex::input::DeviceInfo info;
    info.id = kTouchDevice;
    info.name = "Touch screen controls";
    info.synthetic = true;
    out.push_back(std::move(info));
  }
  X_RESULT GetDeviceState(DeviceId id, rex::input::X_INPUT_STATE* out) override {
    if (id != kTouchDevice) {
      return X_ERROR_DEVICE_NOT_CONNECTED;
    }
    if (out) {
      *out = {};
      out->gamepad = pad_.State();
      out->packet_number = ++packet_;
    }
    return X_ERROR_SUCCESS;
  }
  X_RESULT GetDeviceCapabilities(DeviceId id, uint32_t,
                                 rex::input::X_INPUT_CAPABILITIES* out) override {
    if (id != kTouchDevice) {
      return X_ERROR_DEVICE_NOT_CONNECTED;
    }
    if (out) {
      *out = {};
      out->type = 1;
      out->sub_type = 1;
      out->gamepad.buttons = UINT16_MAX;
      out->gamepad.left_trigger = UINT8_MAX;
      out->gamepad.right_trigger = UINT8_MAX;
      out->gamepad.thumb_lx = INT16_MAX;
      out->gamepad.thumb_ly = INT16_MAX;
    }
    return X_ERROR_SUCCESS;
  }
  X_RESULT SetDeviceVibration(DeviceId id, rex::input::X_INPUT_VIBRATION* vibration) override {
    if (id != kTouchDevice) {
      return X_ERROR_DEVICE_NOT_CONNECTED;
    }
#if defined(__ANDROID__)
    if (vibration) {
      auto* env = static_cast<JNIEnv*>(SDL_GetAndroidJNIEnv());
      auto activity = static_cast<jobject>(SDL_GetAndroidActivity());
      if (env && activity) {
        jclass cls = env->GetObjectClass(activity);
        if (cls) {
          jmethodID mid = env->GetMethodID(cls, "onRumble", "(II)V");
          if (mid) {
            env->CallVoidMethod(activity, mid, jint(vibration->left_motor_speed),
                                jint(vibration->right_motor_speed));
          }
          if (env->ExceptionCheck()) env->ExceptionClear();
          env->DeleteLocalRef(cls);
        }
        env->DeleteLocalRef(activity);
      }
    }
#endif
    return X_ERROR_SUCCESS;
  }
  X_RESULT GetDeviceKeystroke(DeviceId id, uint32_t, rex::input::X_INPUT_KEYSTROKE*) override {
    return id == kTouchDevice ? X_ERROR_EMPTY : X_ERROR_DEVICE_NOT_CONNECTED;
  }

 private:
  TouchPad& pad_;
  uint32_t packet_ = 0;
};

}  // namespace

TouchPad& TouchPad::Get() {
  static TouchPad pad;
  return pad;
}

const std::vector<TouchPad::Layout>& TouchPad::Controls() {
  // Thumb reach on a landscape phone or handheld: throttle under the right
  // thumb with brake beside it, the face buttons above, the stick anywhere
  // in the lower left (its centre is where the finger lands).
  static const std::vector<Layout> controls = {
      {Control::kThrottle, "RT", 0.905f, 0.78f, 0.13f},
      {Control::kBrake, "LT", 0.745f, 0.84f, 0.10f},
      {Control::kA, "A", 0.83f, 0.52f, 0.075f},
      {Control::kB, "B", 0.93f, 0.43f, 0.075f},
      {Control::kX, "X", 0.73f, 0.43f, 0.075f},
      {Control::kY, "Y", 0.83f, 0.34f, 0.075f},
      {Control::kLeftBumper, "LB", 0.07f, 0.20f, 0.075f},
      {Control::kRightBumper, "RB", 0.93f, 0.20f, 0.075f},
      {Control::kBack, "BACK", 0.40f, 0.08f, 0.06f},
      {Control::kStart, "START", 0.60f, 0.08f, 0.06f},
  };
  return controls;
}

std::unique_ptr<rex::input::InputDriver> TouchPad::CreateDriver() {
  return std::make_unique<TouchPadDriver>(*this);
}

void TouchPad::SetChangedCallback(std::function<void()> callback) {
  std::lock_guard lock(mutex_);
  changed_ = std::move(callback);
}

void TouchPad::SetSuspended(bool suspended) {
  {
    std::lock_guard lock(mutex_);
    if (suspended_ == suspended) {
      return;
    }
    suspended_ = suspended;
    if (suspended) {
      fingers_.clear();  // the menus take over; nothing stays held
    }
  }
  Changed();
}

void TouchPad::Place(const Layout& control, float width, float height, float& x,
                     float& y) const {
  // The layout's fractions span the safe area, so no control sits under a
  // camera cutout or a rounded corner.
  const float safe_width = std::max(1.0f, width - safe_left_ - safe_right_);
  const float safe_height = std::max(1.0f, height - safe_top_ - safe_bottom_);
  x = safe_left_ + control.x * safe_width;
  y = safe_top_ + control.y * safe_height;
}

TouchPad::Control TouchPad::Hit(float x, float y, float width, float height) const {
  Control best = Control::kNone;
  float best_distance = 0.0f;
  for (const Layout& control : Controls()) {
    float control_x, control_y;
    Place(control, width, height, control_x, control_y);
    const float dx = x - control_x;
    const float dy = y - control_y;
    // A generous target: a thumb lands off-centre.
    const float reach = control.radius * height * 1.25f;
    const float distance = std::sqrt(dx * dx + dy * dy);
    if (distance <= reach && (best == Control::kNone || distance < best_distance)) {
      best = control.control;
      best_distance = distance;
    }
  }
  if (best == Control::kNone && x < width * 0.45f && y > height * 0.35f) {
    return Control::kStick;
  }
  return best;
}

void TouchPad::OnTouchEvent(rex::ui::TouchEvent& e) {
#if defined(__ANDROID__)
  (void)e;
  return;
#else
  const auto* window = e.target();
  if (!window) {
    return;
  }
  const float width = float(window->GetActualPhysicalWidth());
  const float height = float(window->GetActualPhysicalHeight());
  if (width <= 0.0f || height <= 0.0f) {
    return;
  }
  {
    std::lock_guard lock(mutex_);
    width_ = width;
    height_ = height;
    const auto insets = window->GetSafeAreaInsets();
    if (float(insets.left) != safe_left_ || float(insets.top) != safe_top_ ||
        float(insets.right) != safe_right_ || float(insets.bottom) != safe_bottom_) {
      REXLOG_INFO("Touch controls: safe area insets left {} top {} right {} bottom {}",
                  insets.left, insets.top, insets.right, insets.bottom);
    }
    safe_left_ = float(insets.left);
    safe_top_ = float(insets.top);
    safe_right_ = float(insets.right);
    safe_bottom_ = float(insets.bottom);
    if (suspended_) {
      return;
    }
    last_touch_ = std::chrono::steady_clock::now();
    switch (e.action()) {
      case rex::ui::TouchEvent::Action::kDown: {
        Finger finger;
        finger.control = Hit(e.x(), e.y(), width, height);
        finger.origin_x = finger.x = e.x();
        finger.origin_y = finger.y = e.y();
        fingers_[e.pointer_id()] = finger;
        break;
      }
      case rex::ui::TouchEvent::Action::kMove: {
        auto it = fingers_.find(e.pointer_id());
        if (it != fingers_.end()) {
          it->second.x = e.x();
          it->second.y = e.y();
        }
        break;
      }
      case rex::ui::TouchEvent::Action::kUp:
      case rex::ui::TouchEvent::Action::kCancel:
        fingers_.erase(e.pointer_id());
        break;
    }
  }
  Changed();
#endif
}

void TouchPad::Changed() {
  std::function<void()> changed;
  {
    std::lock_guard lock(mutex_);
    changed = changed_;
  }
  if (changed) {
    changed();
  }
}

bool TouchPad::Visible() const {
#if defined(__ANDROID__)
  return false;
#else
  std::lock_guard lock(mutex_);
  return !suspended_ && last_touch_ != std::chrono::steady_clock::time_point{} &&
         std::chrono::steady_clock::now() - last_touch_ < kVisibleAfterTouch;
#endif
}

void TouchPad::SetPadState(float steer, float throttle, float brake, float look_x, float look_y, uint32_t buttons) {
  std::lock_guard lock(mutex_);
  mobile_override_active_ = true;
  mobile_steer_x_ = steer;
  mobile_steer_y_ = 0.0f;
  mobile_throttle_ = throttle;
  mobile_brake_ = brake;
  mobile_look_x_ = look_x;
  mobile_look_y_ = look_y;
  mobile_buttons_ = buttons;
  last_touch_ = std::chrono::steady_clock::now();
}

void TouchPad::SetMobileOverrides(float steer_x, float throttle, float brake, uint16_t button_mask, float look_x, float look_y, float steer_y) {
  std::lock_guard lock(mutex_);
  mobile_override_active_ = true;
  mobile_steer_x_ = steer_x;
  mobile_steer_y_ = steer_y;
  mobile_throttle_ = throttle;
  mobile_brake_ = brake;
  mobile_look_x_ = look_x;
  mobile_look_y_ = look_y;
  mobile_buttons_ = button_mask;
  last_touch_ = std::chrono::steady_clock::now();
}

rex::input::X_INPUT_GAMEPAD TouchPad::State() const {
  rex::input::X_INPUT_GAMEPAD pad = {};
  std::lock_guard lock(mutex_);
  if (suspended_) {
    return pad;
  }
#if defined(__ANDROID__)
  pad.thumb_lx = int16_t(std::clamp(mobile_steer_x_, -1.0f, 1.0f) * 32767.0f);
  if (mobile_steer_y_ != 0.0f) {
    pad.thumb_ly = int16_t(std::clamp(mobile_steer_y_, -1.0f, 1.0f) * 32767.0f);
  } else {
    pad.thumb_ly = 0;
  }
  pad.right_trigger = uint8_t(std::clamp(mobile_throttle_, 0.0f, 1.0f) * 255.0f);
  pad.left_trigger = uint8_t(std::clamp(mobile_brake_, 0.0f, 1.0f) * 255.0f);
  pad.thumb_rx = int16_t(std::clamp(mobile_look_x_, -1.0f, 1.0f) * 32767.0f);
  pad.thumb_ry = int16_t(std::clamp(mobile_look_y_, -1.0f, 1.0f) * 32767.0f);
  pad.buttons = uint16_t(mobile_buttons_);
  return pad;
#else
  if (mobile_override_active_) {
    pad.thumb_lx = int16_t(std::clamp(mobile_steer_x_, -1.0f, 1.0f) * 32767.0f);
    pad.right_trigger = uint8_t(std::clamp(mobile_throttle_, 0.0f, 1.0f) * 255.0f);
    pad.left_trigger = uint8_t(std::clamp(mobile_brake_, 0.0f, 1.0f) * 255.0f);
    pad.thumb_rx = int16_t(std::clamp(mobile_look_x_, -1.0f, 1.0f) * 32767.0f);
    pad.thumb_ry = int16_t(std::clamp(mobile_look_y_, -1.0f, 1.0f) * 32767.0f);
    pad.buttons = mobile_buttons_;
    return pad;
  }
#endif
  uint16_t buttons = 0;
  for (const auto& [id, finger] : fingers_) {
    switch (finger.control) {
      case Control::kStick: {
        const float travel = std::max(1.0f, kStickTravel * height_);
        const float x = std::clamp((finger.x - finger.origin_x) / travel, -1.0f, 1.0f);
        const float y = std::clamp((finger.y - finger.origin_y) / travel, -1.0f, 1.0f);
        pad.thumb_lx = int16_t(x * 32767.0f);
        pad.thumb_ly = int16_t(-y * 32767.0f);
        break;
      }
      case Control::kThrottle:
        pad.right_trigger = 255;
        break;
      case Control::kBrake:
        pad.left_trigger = 255;
        break;
      case Control::kA:
        buttons |= rex::input::X_INPUT_GAMEPAD_A;
        break;
      case Control::kB:
        buttons |= rex::input::X_INPUT_GAMEPAD_B;
        break;
      case Control::kX:
        buttons |= rex::input::X_INPUT_GAMEPAD_X;
        break;
      case Control::kY:
        buttons |= rex::input::X_INPUT_GAMEPAD_Y;
        break;
      case Control::kLeftBumper:
        buttons |= rex::input::X_INPUT_GAMEPAD_LEFT_SHOULDER;
        break;
      case Control::kRightBumper:
        buttons |= rex::input::X_INPUT_GAMEPAD_RIGHT_SHOULDER;
        break;
      case Control::kBack:
        buttons |= rex::input::X_INPUT_GAMEPAD_BACK;
        break;
      case Control::kStart:
        buttons |= rex::input::X_INPUT_GAMEPAD_START;
        break;
      case Control::kNone:
        break;
    }
  }
  pad.buttons = buttons;
  return pad;
}

std::vector<TouchPad::Shape> TouchPad::Shapes(float width, float height) const {
  std::vector<Shape> shapes;
  std::lock_guard lock(mutex_);
  if (mobile_override_active_) {
    return shapes;
  }
  for (const Layout& control : Controls()) {
    Shape shape;
    Place(control, width, height, shape.x, shape.y);
    shape.radius = control.radius * height;
    shape.label = control.label;
    for (const auto& [id, finger] : fingers_) {
      shape.pressed |= finger.control == control.control;
    }
    shapes.push_back(std::move(shape));
  }
  // The stick where the finger holds it, or its resting place.
  Shape stick;
  stick.stick = true;
  Place({Control::kStick, "", 0.16f, 0.70f, kStickTravel}, width, height, stick.x, stick.y);
  stick.radius = kStickTravel * height;
  stick.stick_x = stick.x;
  stick.stick_y = stick.y;
  for (const auto& [id, finger] : fingers_) {
    if (finger.control == Control::kStick) {
      stick.pressed = true;
      stick.x = finger.origin_x;
      stick.y = finger.origin_y;
      const float dx = finger.x - finger.origin_x, dy = finger.y - finger.origin_y;
      const float length = std::sqrt(dx * dx + dy * dy);
      const float scale = length > stick.radius ? stick.radius / length : 1.0f;
      stick.stick_x = stick.x + dx * scale;
      stick.stick_y = stick.y + dy * scale;
    }
  }
  shapes.push_back(std::move(stick));
  return shapes;
}

}  // namespace pinyon_shift::ui

#if defined(__ANDROID__)
#include <jni.h>
#include <fmt/format.h>
#include "pinyon_shift_app.h"

extern "C" JNIEXPORT void JNICALL
Java_studio_deimos_pinyonshift_PinyonShiftActivity_nativeSetPadState(
    JNIEnv*, jclass, jfloat steer, jfloat throttle, jfloat brake, jfloat lookX, jfloat lookY, jint buttons) {
  pinyon_shift::ui::TouchPad::Get().SetPadState(
      float(steer), float(throttle), float(brake), float(lookX), float(lookY), uint32_t(buttons));
}

extern "C" JNIEXPORT void JNICALL
Java_studio_deimos_pinyonshift_PinyonShiftActivity_nativeSetMobileOverrides(
    JNIEnv*, jclass, jfloat steer_x, jfloat throttle, jfloat brake, jint button_mask, jfloat look_x, jfloat look_y, jfloat steer_y) {
  pinyon_shift::ui::TouchPad::Get().SetMobileOverrides(
      float(steer_x), float(throttle), float(brake), uint16_t(button_mask), float(look_x), float(look_y), float(steer_y));
}

extern "C" JNIEXPORT void JNICALL
Java_studio_deimos_pinyonshift_PinyonShiftActivity_nativeAction(
    JNIEnv*, jclass, jint actionId, jfloat value) {
  if (actionId == 1) {
    if (auto* app = PinyonShiftApp::Instance()) {
      app->TriggerPhoto();
    }
  } else if (actionId == 2) {
    if (auto* app = PinyonShiftApp::Instance()) {
      app->ToggleGameMenu();
    }
  } else if (actionId == 3) {
    if (value >= 0.0f) {
      std::string fps = std::to_string(int(value));
      rex::cvar::SetFlagByName("host_present_fps_limit", fps.c_str());
      rex::cvar::SetFlagByName("pinyon_shift_fh1_render_fps_limit", fps.c_str());
    } else {
      std::string env = fmt::format("{:.2f}", std::abs(value));
      rex::cvar::SetFlagByName("pinyon_shift_fh1_env_map_rate", env.c_str());
    }
  } else if (actionId == 4) {
    bool hor_plus = (value > 0.5f);
    rex::cvar::SetFlagByName("pinyon_shift_hor_plus", hor_plus ? "true" : "false");
    rex::cvar::SetFlagByName("present_letterbox", hor_plus ? "false" : "true");
    if (auto* app = PinyonShiftApp::Instance()) {
      app->UpdateHorPlus();
    }
  } else if (actionId == 5) {
    int u = int(value);
    const char* eff = (u == 1) ? "fsr" : (u == 2 ? "cas" : "bilinear");
    rex::cvar::SetFlagByName("present_effect", eff);
  } else if (actionId == 6) {
    int p = int(value);
    if (p == 0) { // QUALITY 30
      rex::cvar::SetFlagByName("pinyon_shift_fh1_shadows", "true");
      rex::cvar::SetFlagByName("pinyon_shift_fh1_env_map_rate", "0.25");
      rex::cvar::SetFlagByName("fh1_untile_predicated_tiling", "true");
      rex::cvar::SetFlagByName("host_present_fps_limit", "30");
      rex::cvar::SetFlagByName("pinyon_shift_fh1_render_fps_limit", "30");
    } else if (p == 1) { // SMOOTH 60
      rex::cvar::SetFlagByName("pinyon_shift_fh1_shadows", "false");
      rex::cvar::SetFlagByName("pinyon_shift_fh1_env_map_rate", "0.25");
      rex::cvar::SetFlagByName("fh1_untile_predicated_tiling", "true");
      rex::cvar::SetFlagByName("host_present_fps_limit", "60");
      rex::cvar::SetFlagByName("pinyon_shift_fh1_render_fps_limit", "60");
    } else if (p == 2) { // ULTRA
      rex::cvar::SetFlagByName("pinyon_shift_fh1_shadows", "true");
      rex::cvar::SetFlagByName("pinyon_shift_fh1_env_map_rate", "1.0");
      rex::cvar::SetFlagByName("fh1_untile_predicated_tiling", "false");
      rex::cvar::SetFlagByName("host_present_fps_limit", "0");
      rex::cvar::SetFlagByName("pinyon_shift_fh1_render_fps_limit", "0");
    }
  } else if (actionId == 7) {
    bool vs = (value > 0.5f);
    rex::cvar::SetFlagByName("vsync", vs ? "true" : "false");
  } else if (actionId == 8) {
    bool shadows = (value > 0.5f);
    rex::cvar::SetFlagByName("pinyon_shift_fh1_shadows", shadows ? "true" : "false");
  } else if (actionId == 9) {
    bool untile = (value > 0.5f);
    rex::cvar::SetFlagByName("fh1_untile_predicated_tiling", untile ? "true" : "false");
  } else if (actionId == 10) {
    std::string env = fmt::format("{:.2f}", value);
    rex::cvar::SetFlagByName("pinyon_shift_fh1_env_map_rate", env.c_str());
  } else if (actionId == 11) {
    bool bloom_on = (value > 0.5f);
    rex::cvar::SetFlagByName("disable_bloom", bloom_on ? "false" : "true");
  }
}

extern "C" JNIEXPORT void JNICALL
Java_studio_deimos_pinyonshift_PinyonShiftActivity_nativeSetCVar(
    JNIEnv* env, jclass, jstring name, jstring value) {
  if (!name || !value) return;
  const char* n = env->GetStringUTFChars(name, nullptr);
  const char* v = env->GetStringUTFChars(value, nullptr);
  if (n && v) {
    rex::cvar::SetFlagByName(n, v);
  }
  if (n) env->ReleaseStringUTFChars(name, n);
  if (v) env->ReleaseStringUTFChars(value, v);
}

extern "C" JNIEXPORT jfloat JNICALL
Java_studio_deimos_pinyonshift_PinyonShiftActivity_nativeGetFrameTimeMs(
    JNIEnv*, jclass) {
  static uint64_t last_tick = 0;
  static int64_t last_frames = 0;
  static float last_frame_time_ms = 16.6f;

  const uint64_t now_tick = rex::chrono::Clock::QueryHostTickCount();
  const uint64_t tick_freq = rex::chrono::Clock::QueryHostTickFrequency();
  if (tick_freq == 0) return 16.6f;

  int64_t frames = rex::perf::GetTotalCounter(rex::perf::CounterId::kPresentCount);
  if (frames == 0) {
    frames = rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount);
  }

  if (last_tick == 0) {
    last_tick = now_tick;
    last_frames = frames;
    return last_frame_time_ms;
  }

  if (now_tick > last_tick) {
    const uint64_t elapsed_ticks = now_tick - last_tick;
    if (elapsed_ticks >= tick_freq / 4) { // Update at least every 250ms
      const int64_t delta_frames = frames - last_frames;
      if (delta_frames > 0) {
        const double elapsed_seconds = double(elapsed_ticks) / double(tick_freq);
        const double fps = double(delta_frames) / elapsed_seconds;
        if (fps > 0.1) {
          last_frame_time_ms = static_cast<float>(1000.0 / fps);
        }
      }
      last_tick = now_tick;
      last_frames = frames;
    }
  }

  return last_frame_time_ms;
}
#endif
