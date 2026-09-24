#include "fh1_render_test.h"

#include <algorithm>
#include <atomic>
#include <condition_variable>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <memory>
#include <mutex>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include <rex/input/device_assignment.h>
#include <rex/cvar.h>
#include <rex/input/input.h>
#include <rex/input/input_driver.h>
#include <rex/input/input_system.h>
#include <rex/perf/counter.h>
#include <rex/runtime.h>
#include <rex/system/interfaces/graphics.h>
#include <rex/ui/presenter.h>
#include <rex/ui/window.h>
#include <rex/ui/windowed_app_context.h>

#include "pinyon_shift_diagnostics.h"

namespace pinyon_shift::fh1_render_test {
namespace {

using rex::X_RESULT;
using rex::X_STATUS;

constexpr rex::input::DeviceId kDevice =
    static_cast<rex::input::DeviceId>(0x46483154);  // FH1T

struct InputStep {
  uint64_t frame = 0;
  rex::input::X_INPUT_GAMEPAD state{};
};

struct NativeRaceStep {
  uint64_t frame = 0;
  bool enabled = false;
};

struct Capture {
  uint64_t frame = 0;
  std::string name;
  uint64_t trigger_output_frame = 0;
  uint64_t trigger_elapsed_us = 0;
  uint64_t capture_begin_elapsed_us = 0;
};

struct TestState {
  bool enabled = false;
  std::filesystem::path output;
  std::vector<InputStep> inputs;
  std::vector<NativeRaceStep> native_race_steps;
  size_t next_native_race_step = 0;
  std::vector<Capture> captures;
  uint64_t stop_frame = 0;
  uint32_t clock_hz = 0;
  std::atomic<uint64_t> frame{};
  std::chrono::steady_clock::time_point clock_origin{};
  std::mutex mutex;
  std::condition_variable condition;
  size_t next_capture = 0;
  bool capture_pending = false;
  bool capture_complete = false;
  bool stopping = false;
  rex::ui::Presenter* presenter = nullptr;
  rex::ui::WindowedAppContext* app_context = nullptr;
  rex::ui::Window* window = nullptr;
  std::function<void()> before_close;
  std::thread worker;
  std::mutex vehicle_pose_mutex;
  bool vehicle_pose_valid = false;
  float vehicle_x = 0.0f;
  float vehicle_y = 0.0f;
  float vehicle_z = 0.0f;
};

TestState g_test;

void RequestClose() {
  if (auto before_close = std::move(g_test.before_close)) {
    before_close();
  }
  auto* app_context = g_test.app_context;
  auto* window = g_test.window;
  app_context->CallInUIThread([window] { window->RequestClose(); });
}

[[noreturn]] void Fail(std::string_view reason) {
  diagnostics::RecordEvent("fh1.render_test.failure", {{"reason", reason}});
  std::exit(EXIT_FAILURE);
}

uint64_t ParseUnsigned(const std::string& text, int base,
                       std::string_view field) {
  size_t consumed = 0;
  unsigned long long value = 0;
  try {
    value = std::stoull(text, &consumed, base);
  } catch (...) {
    Fail(std::string("invalid_") + std::string(field));
  }
  if (consumed != text.size()) {
    Fail(std::string("invalid_") + std::string(field));
  }
  return uint64_t(value);
}

int64_t ParseSigned(const std::string& text, std::string_view field) {
  size_t consumed = 0;
  long long value = 0;
  try {
    value = std::stoll(text, &consumed, 10);
  } catch (...) {
    Fail(std::string("invalid_") + std::string(field));
  }
  if (consumed != text.size()) {
    Fail(std::string("invalid_") + std::string(field));
  }
  return int64_t(value);
}

void LoadScript(const std::filesystem::path& path) {
  std::ifstream input(path);
  if (!input) {
    Fail("script_unreadable");
  }
  std::string line;
  if (!std::getline(input, line) || line != "pinyon-shift-fh1-render-test-v1") {
    Fail("script_schema");
  }
  uint64_t previous_input_frame = 0;
  uint64_t previous_capture_frame = 0;
  uint64_t previous_native_race_frame = 0;
  bool have_input = false;
  while (std::getline(input, line)) {
    if (line.starts_with("# clock-hz ")) {
      if (g_test.clock_hz) {
        Fail("script_clock_duplicate");
      }
      g_test.clock_hz = static_cast<uint32_t>(
          ParseUnsigned(line.substr(11), 10, "clock_hz"));
      if (!g_test.clock_hz || g_test.clock_hz > 240) {
        Fail("script_clock_range");
      }
      continue;
    }
    if (line.empty() || line[0] == '#') {
      continue;
    }
    std::istringstream row(line);
    std::string command;
    row >> command;
    if (command == "input") {
      std::string frame, buttons, left_trigger, right_trigger, thumb_lx,
          thumb_ly, thumb_rx, thumb_ry, extra;
      if (!(row >> frame >> buttons >> left_trigger >> right_trigger >>
            thumb_lx >> thumb_ly >> thumb_rx >> thumb_ry) ||
          row >> extra) {
        Fail("script_input_columns");
      }
      InputStep step;
      step.frame = ParseUnsigned(frame, 10, "input_frame");
      const uint64_t button_value = ParseUnsigned(buttons, 16, "buttons");
      const uint64_t lt = ParseUnsigned(left_trigger, 10, "left_trigger");
      const uint64_t rt = ParseUnsigned(right_trigger, 10, "right_trigger");
      const int64_t lx = ParseSigned(thumb_lx, "thumb_lx");
      const int64_t ly = ParseSigned(thumb_ly, "thumb_ly");
      const int64_t rx = ParseSigned(thumb_rx, "thumb_rx");
      const int64_t ry = ParseSigned(thumb_ry, "thumb_ry");
      if ((have_input && step.frame <= previous_input_frame) ||
          button_value > UINT16_MAX || lt > UINT8_MAX || rt > UINT8_MAX ||
          lx < INT16_MIN || lx > INT16_MAX || ly < INT16_MIN ||
          ly > INT16_MAX || rx < INT16_MIN || rx > INT16_MAX ||
          ry < INT16_MIN || ry > INT16_MAX) {
        Fail("script_input_range");
      }
      step.state.buttons = uint16_t(button_value);
      step.state.left_trigger = uint8_t(lt);
      step.state.right_trigger = uint8_t(rt);
      step.state.thumb_lx = int16_t(lx);
      step.state.thumb_ly = int16_t(ly);
      step.state.thumb_rx = int16_t(rx);
      step.state.thumb_ry = int16_t(ry);
      g_test.inputs.push_back(step);
      previous_input_frame = step.frame;
      have_input = true;
    } else if (command == "native-race") {
      std::string frame, value, extra;
      if (!(row >> frame >> value) || row >> extra ||
          (value != "true" && value != "false")) {
        Fail("script_native_race_columns");
      }
      const uint64_t at = ParseUnsigned(frame, 10, "native_race_frame");
      if (!at || at <= previous_native_race_frame)
        Fail("script_native_race_order");
      g_test.native_race_steps.push_back({at, value == "true"});
      previous_native_race_frame = at;
    } else if (command == "capture") {
      std::string frame, name, extra;
      if (!(row >> frame >> name) || row >> extra || name.empty() ||
          name.find_first_not_of(
              "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_") !=
              std::string::npos) {
        Fail("script_capture_columns");
      }
      Capture capture{ParseUnsigned(frame, 10, "capture_frame"), name};
      if (capture.frame == 0 || capture.frame <= previous_capture_frame) {
        Fail("script_capture_order");
      }
      g_test.captures.push_back(std::move(capture));
      previous_capture_frame = g_test.captures.back().frame;
    } else if (command == "stop") {
      std::string frame, extra;
      if (!(row >> frame) || row >> extra || g_test.stop_frame) {
        Fail("script_stop_columns");
      }
      g_test.stop_frame = ParseUnsigned(frame, 10, "stop_frame");
    } else {
      Fail("script_command");
    }
  }
  if (!have_input || g_test.inputs.front().frame != 0 ||
      g_test.captures.empty() ||
      g_test.stop_frame <= g_test.captures.back().frame) {
    Fail("script_incomplete");
  }
}

class ScriptedInputDriver final : public rex::input::InputDriver {
 public:
  ScriptedInputDriver() : InputDriver(nullptr, 0) {}
  X_STATUS Setup() override { return X_STATUS_SUCCESS; }
  void EnumerateDevices(std::vector<rex::input::DeviceInfo>& out) override {
    rex::input::DeviceInfo info;
    info.id = kDevice;
    info.name = "FH1 deterministic render test";
    info.synthetic = true;
    out.push_back(std::move(info));
  }
  X_RESULT GetDeviceState(rex::input::DeviceId id,
                          rex::input::X_INPUT_STATE* out) override {
    if (id != kDevice) {
      return X_ERROR_DEVICE_NOT_CONNECTED;
    }
    if (out) {
      *out = {};
      const uint64_t frame = g_test.frame.load(std::memory_order_acquire);
      auto next = std::upper_bound(
          g_test.inputs.begin(), g_test.inputs.end(), frame,
          [](uint64_t value, const InputStep& step) {
            return value < step.frame;
          });
      out->gamepad = std::prev(next)->state;
      out->packet_number = uint32_t(frame);
      const size_t index = size_t(std::prev(next) - g_test.inputs.begin());
      size_t previous = last_input_step_.load(std::memory_order_relaxed);
      while (previous == SIZE_MAX || index > previous) {
        if (last_input_step_.compare_exchange_weak(previous, index,
                                                   std::memory_order_relaxed)) {
          rex::perf::TraceCriticalPath(
              "render_test_input",
              rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
              int64_t(g_test.inputs[index].frame), int64_t(frame));
          // Records delivery to the input API, not acceptance by a menu.
          diagnostics::RecordEvent(
              "fh1.render_test.input_step",
              {{"index", std::to_string(index)},
               {"scheduled_frame", std::to_string(g_test.inputs[index].frame)},
               {"observed_frame", std::to_string(frame)},
               {"buttons", std::to_string(out->gamepad.buttons)},
               {"skipped_steps", std::to_string(
                   previous == SIZE_MAX ? index : index - previous - 1)}});
          break;
        }
      }
    }
    return X_ERROR_SUCCESS;
  }
  X_RESULT GetDeviceCapabilities(
      rex::input::DeviceId id, uint32_t,
      rex::input::X_INPUT_CAPABILITIES* out) override {
    if (id != kDevice) {
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
      out->gamepad.thumb_rx = INT16_MAX;
      out->gamepad.thumb_ry = INT16_MAX;
    }
    return X_ERROR_SUCCESS;
  }
  X_RESULT SetDeviceVibration(rex::input::DeviceId id,
                              rex::input::X_INPUT_VIBRATION*) override {
    return id == kDevice ? X_ERROR_SUCCESS : X_ERROR_DEVICE_NOT_CONNECTED;
  }
  X_RESULT GetDeviceKeystroke(rex::input::DeviceId id, uint32_t,
                              rex::input::X_INPUT_KEYSTROKE*) override {
    return id == kDevice ? X_ERROR_EMPTY : X_ERROR_DEVICE_NOT_CONNECTED;
  }

 private:
  std::atomic<size_t> last_input_step_{SIZE_MAX};
};

std::unique_ptr<rex::system::IInputSystem> CreateInputSystem(bool) {
  auto input = std::make_unique<rex::input::InputSystem>(nullptr);
  input->AddDriver(std::make_unique<ScriptedInputDriver>());
  input->SetDeviceAssignment(std::make_unique<rex::input::SlotAssignment>());
  return input;
}

uint64_t Fnv1a64(const std::vector<uint8_t>& data) {
  uint64_t hash = UINT64_C(0xCBF29CE484222325);
  for (uint8_t value : data) {
    hash = (hash ^ value) * UINT64_C(0x100000001B3);
  }
  return hash;
}

bool WritePpm(const Capture& capture, const rex::ui::RawImage& image,
              const char* source, const char* suffix = "",
              bool record_event = true) {
  if (!image.width || !image.height || image.stride < image.width * 4 ||
      image.data.size() < image.stride * image.height) {
    return false;
  }
  const auto path =
      g_test.output / (capture.name + std::string(suffix) + ".ppm");
  std::ofstream output(path, std::ios::binary | std::ios::trunc);
  output << "P6\n" << image.width << ' ' << image.height << "\n255\n";
  for (uint32_t y = 0; y < image.height; ++y) {
    const uint8_t* row = image.data.data() + size_t(y) * image.stride;
    for (uint32_t x = 0; x < image.width; ++x) {
      output.write(reinterpret_cast<const char*>(row + size_t(x) * 4), 3);
    }
  }
  if (!output.good()) {
    return false;
  }
  if (record_event) {
    bool vehicle_pose_valid = false;
    float vehicle_x = 0.0f;
    float vehicle_y = 0.0f;
    float vehicle_z = 0.0f;
    {
      std::lock_guard lock(g_test.vehicle_pose_mutex);
      vehicle_pose_valid = g_test.vehicle_pose_valid;
      vehicle_x = g_test.vehicle_x;
      vehicle_y = g_test.vehicle_y;
      vehicle_z = g_test.vehicle_z;
    }
    diagnostics::RecordEvent(
      "fh1.render_test.capture",
      {{"name", capture.name},
       {"frame", std::to_string(capture.frame)},
       // The trigger is the current output callback. The image may come from
       // an earlier published resource, so this is not its source-frame ID.
       {"trigger_output_frame", std::to_string(capture.trigger_output_frame)},
       {"trigger_elapsed_us", std::to_string(capture.trigger_elapsed_us)},
       {"capture_begin_elapsed_us", std::to_string(capture.capture_begin_elapsed_us)},
       {"capture_end_elapsed_us", std::to_string(
           std::chrono::duration_cast<std::chrono::microseconds>(
               std::chrono::steady_clock::now() - g_test.clock_origin).count())},
       {"width", std::to_string(image.width)},
       {"height", std::to_string(image.height)},
       {"source", source},
       {"vehicle_pose_valid", vehicle_pose_valid ? "1" : "0"},
       {"vehicle_x", std::to_string(vehicle_x)},
       {"vehicle_y", std::to_string(vehicle_y)},
       {"vehicle_z", std::to_string(vehicle_z)},
       {"raw_hash", [&] {
          std::ostringstream text;
          text << std::hex << std::uppercase << std::setw(16)
               << std::setfill('0') << Fnv1a64(image.data);
          return text.str();
        }()}});
  }
  return true;
}

void Worker() {
  for (;;) {
    Capture capture;
    {
      std::unique_lock lock(g_test.mutex);
      g_test.condition.wait(lock, [] {
        return g_test.stopping || g_test.capture_pending;
      });
      if (g_test.stopping) {
        return;
      }
      capture = g_test.captures[g_test.next_capture];
    }
    capture.capture_begin_elapsed_us = uint64_t(
        std::chrono::duration_cast<std::chrono::microseconds>(
            std::chrono::steady_clock::now() - g_test.clock_origin).count());
    rex::ui::RawImage image;
    const bool captured = g_test.presenter->CaptureGuestOutput(image) &&
                          WritePpm(capture, image, "guest_output");
    {
      std::lock_guard lock(g_test.mutex);
      if (!captured) {
        diagnostics::RecordEvent("fh1.render_test.failure",
                                 {{"reason", "capture_failed"},
                                  {"name", capture.name}});
        g_test.stopping = true;
      } else {
        ++g_test.next_capture;
      }
      g_test.capture_pending = false;
      g_test.capture_complete = true;
    }
    g_test.condition.notify_all();
    if (!captured) {
      auto* context = g_test.app_context;
      auto* window = g_test.window;
      context->CallInUIThread([window] { window->RequestClose(); });
      return;
    }
  }
}

}  // namespace

void Configure(rex::RuntimeConfig& config) {
  const auto script = diagnostics::EnvironmentPath(
      "PINYON_SHIFT_FH1_RENDER_TEST_SCRIPT");
  const auto output = diagnostics::EnvironmentPath(
      "PINYON_SHIFT_FH1_RENDER_TEST_OUTPUT");
  if (!script && !output) {
    return;
  }
  if (!script || !output || std::filesystem::exists(*output)) {
    Fail("request_invalid_or_output_exists");
  }
  g_test.output = *output;
  LoadScript(*script);
  std::error_code error;
  std::filesystem::create_directories(g_test.output, error);
  if (error) {
    Fail("output_create_failed");
  }
  g_test.enabled = true;
  config.input_factory = &CreateInputSystem;
  diagnostics::RecordEvent(
      "fh1.render_test.configured",
      {{"script", script->string()},
       {"output", output->string()},
       {"input_steps", std::to_string(g_test.inputs.size())},
       {"captures", std::to_string(g_test.captures.size())},
       {"stop_frame", std::to_string(g_test.stop_frame)},
       {"clock", g_test.clock_hz ? "wall_time" : "fh1_guest_output_frame"},
       {"clock_hz", std::to_string(g_test.clock_hz)},
       {"input", "synthetic_only"},
       {"capture_source", "guest_output"}});
}

bool Enabled() { return g_test.enabled; }

std::filesystem::path OutputDirectory() {
  return g_test.enabled ? g_test.output : std::filesystem::path{};
}

bool ObserveOutput(
    const rex::system::NativeGuestOutputRenderContext& context) {
  if (!g_test.enabled) {
    return false;
  }
  uint64_t frame = context.frame_sequence;
  const auto now = std::chrono::steady_clock::now();
  if (g_test.clock_origin == std::chrono::steady_clock::time_point{}) {
    g_test.clock_origin = now;
  }
  if (g_test.clock_hz) {
    frame = static_cast<uint64_t>(
        std::chrono::duration_cast<std::chrono::milliseconds>(
            now - g_test.clock_origin)
            .count()) *
        g_test.clock_hz / 1000;
  }
  g_test.frame.store(frame, std::memory_order_release);
  while (g_test.next_native_race_step < g_test.native_race_steps.size() &&
         context.frame_sequence >=
             g_test.native_race_steps[g_test.next_native_race_step].frame) {
    const auto& step = g_test.native_race_steps[g_test.next_native_race_step++];
    if (!rex::cvar::SetFlagByName("pinyon_shift_native_race",
                                  step.enabled ? "true" : "false"))
      Fail("native_race_flag_rejected");
  }
  std::unique_lock lock(g_test.mutex);
  if (!g_test.clock_hz && g_test.next_capture < g_test.captures.size() &&
      context.frame_sequence > g_test.captures[g_test.next_capture].frame + 1) {
    const auto& capture = g_test.captures[g_test.next_capture];
    g_test.stopping = true;
    diagnostics::RecordEvent("fh1.render_test.failure",
                             {{"reason", "capture_frame_missed"},
                              {"name", capture.name},
                              {"frame", std::to_string(capture.frame)},
                              {"observed",
                               std::to_string(context.frame_sequence)}});
    g_test.condition.notify_all();
    RequestClose();
    return false;
  }
  if (g_test.next_capture < g_test.captures.size() &&
      (g_test.clock_hz
           ? frame >= g_test.captures[g_test.next_capture].frame
           : context.frame_sequence ==
                 g_test.captures[g_test.next_capture].frame + 1)) {
    auto& capture = g_test.captures[g_test.next_capture];
    capture.trigger_output_frame = context.frame_sequence;
    rex::perf::TraceCriticalPath(
        "render_test_capture",
        rex::perf::GetTotalCounter(rex::perf::CounterId::kSourceFrameCount),
        int64_t(capture.frame), int64_t(context.frame_sequence));
    capture.trigger_elapsed_us = uint64_t(
        std::chrono::duration_cast<std::chrono::microseconds>(
            now - g_test.clock_origin).count());
    g_test.capture_complete = false;
    g_test.capture_pending = true;
    g_test.condition.notify_all();
    g_test.condition.wait(lock, [] {
      return g_test.stopping || g_test.capture_complete;
    });
  }
  if ((g_test.clock_hz ? frame >= g_test.stop_frame
                       : context.frame_sequence >= g_test.stop_frame + 1) &&
      g_test.next_capture == g_test.captures.size() && !g_test.stopping) {
    g_test.stopping = true;
    diagnostics::RecordEvent(
        "fh1.render_test.complete",
        {{"frame", std::to_string(g_test.stop_frame)},
         {"captures", std::to_string(g_test.next_capture)}});
    g_test.condition.notify_all();
    RequestClose();
  }
  return false;
}

void ObserveVehiclePose(float x, float y, float z) {
  if (!g_test.enabled) {
    return;
  }
  std::lock_guard lock(g_test.vehicle_pose_mutex);
  g_test.vehicle_pose_valid = true;
  g_test.vehicle_x = x;
  g_test.vehicle_y = y;
  g_test.vehicle_z = z;
}

uint64_t CurrentFrame() {
  if (!g_test.enabled) {
    return 0;
  }
  return g_test.frame.load(std::memory_order_acquire);
}

void Start(rex::system::IGraphicsSystem* graphics_system,
           rex::ui::WindowedAppContext* app_context, rex::ui::Window* window,
           std::function<void()> before_close) {
  if (!g_test.enabled) {
    return;
  }
  g_test.presenter = graphics_system ? graphics_system->presenter() : nullptr;
  g_test.app_context = app_context;
  g_test.window = window;
  g_test.before_close = std::move(before_close);
  if (!g_test.presenter || !g_test.app_context || !g_test.window) {
    Fail("presenter_unavailable");
  }
  g_test.worker = std::thread(&Worker);
}

void Stop() {
  if (!g_test.enabled) {
    return;
  }
  {
    std::lock_guard lock(g_test.mutex);
    g_test.stopping = true;
  }
  g_test.condition.notify_all();
  if (g_test.worker.joinable()) {
    g_test.worker.join();
  }
}

}  // namespace pinyon_shift::fh1_render_test
