#include "fh1_render_test.h"

#include <algorithm>
#include <cctype>
#include <atomic>
#include <condition_variable>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
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
#include <rex/kernel/xam/ui_provider.h>
#include <rex/system/achievement_manager.h>
#include <rex/system/kernel_state.h>
#include <rex/perf/counter.h>
#include <rex/runtime.h>
#include <rex/system/interfaces/graphics.h>
#include <rex/ui/presenter.h>
#include <rex/ui/window.h>
#include <rex/ui/windowed_app_context.h>

#include "pinyon_shift_diagnostics.h"

REXCVAR_DEFINE_BOOL(fh1_render_test_log_file_opens, false, "Pinyon Shift",
                    "Record every guest file open as a render-test event")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

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

// `wait <frame> <max-frames> <condition> [argument]`: at <frame> the script
// clock stops (inputs hold their state) until the game reaches the condition,
// then continues, so later steps keep their spacing from that point.
constexpr uint64_t kFileWaitLookbackFrames = 60;

struct WaitStep {
  enum class Condition { kVehicle, kVehicleMoved, kMovie, kFile, kRallyStageSaved, kFreeRoam };
  uint64_t frame = 0;
  uint64_t max_frames = 0;
  Condition condition = Condition::kVehicle;
  float distance = 0.0f;  // kVehicleMoved, in world units.
  std::string text;       // kMovie, kFile: substring of the lower-case guest path.
};

// `hostkey <frame> <key>`: presses and releases a key on the game window at
// <frame>, through the same listeners as a real key, to drive host-drawn
// screens (F6 settings) that the scripted controller cannot reach.
// `hostclick <frame> <left|right> <x> <y>` clicks at (x, y) in the title's
// 1280x720 space, mapped onto the painted guest output.
// `xamdialog <frame> message|keyboard` opens a sample XAM message box or
// keyboard through the installed host provider and records how it closed
// (fh1.render_test.xam_dialog), to drive the dialogs with hostkey steps.
struct HostKeyStep {
  uint64_t frame = 0;
  rex::ui::VirtualKey key = rex::ui::VirtualKey::kNone;
  rex::ui::MouseEvent::Button button = rex::ui::MouseEvent::Button::kNone;
  uint32_t x = 0;
  uint32_t y = 0;
  std::string xam_dialog;
  // cvar: set this flag to this value, as a settings change would.
  std::string cvar_name;
  std::string cvar_value;
  // snapshot: write the guest's physical memory to <output>/<name>.mem, for
  // offline scans (tools/scan-guest-snapshots.py).
  std::string snapshot;
  // poke: store a big-endian float at a guest physical address.
  bool poke = false;
  uint32_t poke_address = 0;
  float poke_value = 0.0f;
  // mark: keep a copy of the title's committed virtual heap pages for
  // scanpoke.
  bool mark = false;
  // scanpoke: poke every float in [scan_min, scan_max] that rose by the same
  // step between each pair of marks (clocks), confirming in the same run.
  bool scanpoke = false;
  float scan_min = 0.0f;
  float scan_max = 0.0f;
  // Optional: only values whose step between marks is in this range.
  float scan_step_min = 1e-6f;
  float scan_step_max = 1e30f;
  // Optional: poke only candidates [scan_first, scan_first + scan_count).
  uint32_t scan_first = 0;
  uint32_t scan_count = UINT32_MAX;
};

rex::ui::VirtualKey ParseHostKey(const std::string& name) {
  using rex::ui::VirtualKey;
  static const std::pair<const char*, VirtualKey> kNames[] = {
      {"f6", VirtualKey::kF6},       {"f7", VirtualKey::kF7},
      {"f8", VirtualKey::kF8},       {"f9", VirtualKey::kF9},
      {"f10", VirtualKey::kF10},
      {"enter", VirtualKey::kReturn},
      {"escape", VirtualKey::kEscape}, {"up", VirtualKey::kUp},
      {"down", VirtualKey::kDown},   {"left", VirtualKey::kLeft},
      {"right", VirtualKey::kRight}, {"space", VirtualKey::kSpace},
  };
  std::string lower = name;
  std::transform(lower.begin(), lower.end(), lower.begin(),
                 [](unsigned char c) { return char(std::tolower(c)); });
  for (const auto& [key_name, key] : kNames) {
    if (lower == key_name) return key;
  }
  return VirtualKey::kNone;
}

struct Capture {
  uint64_t frame = 0;
  std::string name;
  uint64_t trigger_output_frame = 0;
  uint64_t trigger_elapsed_us = 0;
  uint64_t capture_begin_elapsed_us = 0;
  // Renderer that produced the triggering output frame.
  rex::system::NativeGuestOutputPresenter presenter =
      rex::system::NativeGuestOutputPresenter::kNativeExecutor;
};

const char* PresenterName(rex::system::NativeGuestOutputPresenter presenter) {
  switch (presenter) {
    case rex::system::NativeGuestOutputPresenter::kNativeExecutor:
      return "native";
    case rex::system::NativeGuestOutputPresenter::kNull:
      return "null";
  }
  return "unknown";
}

struct TestState {
  bool enabled = false;
  std::filesystem::path output;
  std::vector<InputStep> inputs;
  std::vector<WaitStep> waits;
  size_t next_wait = 0;
  std::vector<HostKeyStep> host_keys;
  // One mark: committed runs of the virtual heaps as (address, bytes).
  struct MarkRegion {
    uint32_t address;
    std::vector<uint8_t> bytes;
  };
  std::vector<std::vector<MarkRegion>> marks;
  size_t next_host_key = 0;
  // Output frames spent in completed and active waits.
  uint64_t wait_offset = 0;
  bool wait_active = false;
  uint64_t wait_start_output = 0;
  uint64_t wait_start_vehicle_updates = 0;
  uint64_t wait_start_movie_opens = 0;
  uint64_t wait_start_file_opens = 0;
  std::atomic<uint64_t> rally_stage_saves{};
  std::atomic<uint32_t> game_mode{};
  uint64_t consumed_rally_stage_saves = 0;
  std::vector<Capture> captures;
  uint64_t stop_frame = 0;
  uint32_t clock_hz = 0;
  std::atomic<uint64_t> frame{};
  std::atomic<uint64_t> output_frame{};
  std::chrono::steady_clock::time_point clock_origin{};
  std::mutex mutex;
  std::condition_variable condition;
  size_t next_capture = 0;
  bool capture_pending = false;
  bool capture_complete = false;
  bool stopping = false;
  rex::ui::Presenter* presenter = nullptr;
  // gpu_backend=null: no presenter, captures are skipped.
  bool headless = false;
  rex::ui::WindowedAppContext* app_context = nullptr;
  rex::ui::Window* window = nullptr;
  std::function<void()> before_close;
  std::thread worker;
  std::mutex vehicle_pose_mutex;
  bool vehicle_pose_valid = false;
  float vehicle_x = 0.0f;
  float vehicle_y = 0.0f;
  float vehicle_z = 0.0f;
  uint64_t vehicle_pose_updates = 0;
  // First pose seen during the active wait.
  bool wait_pose_valid = false;
  float wait_x = 0.0f;
  float wait_y = 0.0f;
  float wait_z = 0.0f;
  uint64_t movie_opens = 0;
  std::string last_movie;
  // Recent file opens (sequence number, output frame, path), newest last.
  struct FileOpen {
    uint64_t sequence;
    uint64_t output_frame;
    std::string path;
  };
  uint64_t file_opens = 0;
  std::vector<FileOpen> recent_files;
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
  // SDK/SDL threads may already be running. Match the application's terminal
  // shutdown path so static destruction cannot race their remaining work.
  // RecordEvent flushes the failure receipt before this immediate exit.
  std::_Exit(EXIT_FAILURE);
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
  if (!std::getline(input, line)) Fail("script_schema");
  if (!line.empty() && line.back() == '\r') line.pop_back();
  if (line != "pinyon-shift-fh1-render-test-v1") {
    Fail("script_schema");
  }
  uint64_t previous_input_frame = 0;
  uint64_t previous_capture_frame = 0;
  bool have_input = false;
  while (std::getline(input, line)) {
    if (!line.empty() && line.back() == '\r') line.pop_back();
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
    } else if (command == "wait") {
      if (g_test.clock_hz) Fail("script_wait_needs_output_clock");
      std::string frame, max_frames, condition, argument, extra;
      if (!(row >> frame >> max_frames >> condition)) Fail("script_wait_columns");
      WaitStep wait;
      wait.frame = ParseUnsigned(frame, 10, "wait_frame");
      wait.max_frames = ParseUnsigned(max_frames, 10, "wait_max_frames");
      if (condition == "vehicle") {
        wait.condition = WaitStep::Condition::kVehicle;
      } else if (condition == "rally-stage-saved") {
        wait.condition = WaitStep::Condition::kRallyStageSaved;
      } else if (condition == "freeroam") {
        wait.condition = WaitStep::Condition::kFreeRoam;
      } else if (condition == "vehicle-moved" && row >> argument) {
        wait.condition = WaitStep::Condition::kVehicleMoved;
        wait.distance = float(ParseUnsigned(argument, 10, "wait_distance"));
      } else if (condition == "movie" && row >> argument) {
        wait.condition = WaitStep::Condition::kMovie;
        wait.text = argument;
      } else if (condition == "file" && row >> argument) {
        wait.condition = WaitStep::Condition::kFile;
        wait.text = argument;
      } else {
        Fail("script_wait_condition");
      }
      if (row >> extra || !wait.max_frames ||
          (!g_test.waits.empty() && wait.frame <= g_test.waits.back().frame)) {
        Fail("script_wait_order");
      }
      g_test.waits.push_back(std::move(wait));
    } else if (command == "hostkey") {
      std::string frame, name, extra;
      if (!(row >> frame >> name) || row >> extra) Fail("script_hostkey_columns");
      HostKeyStep step{ParseUnsigned(frame, 10, "hostkey_frame"), ParseHostKey(name)};
      if (step.key == rex::ui::VirtualKey::kNone) Fail("script_hostkey_name");
      if (!g_test.host_keys.empty() && step.frame <= g_test.host_keys.back().frame) {
        Fail("script_hostkey_order");
      }
      g_test.host_keys.push_back(step);
    } else if (command == "xamdialog") {
      std::string frame, kind, extra;
      if (!(row >> frame >> kind) || row >> extra ||
          (kind != "message" && kind != "keyboard" && kind != "achievements" &&
           kind != "toast")) {
        Fail("script_xamdialog_columns");
      }
      HostKeyStep step{ParseUnsigned(frame, 10, "xamdialog_frame")};
      step.xam_dialog = kind;
      if (!g_test.host_keys.empty() && step.frame <= g_test.host_keys.back().frame) {
        Fail("script_hostkey_order");
      }
      g_test.host_keys.push_back(step);
    } else if (command == "cvar") {
      std::string frame, name, value, extra;
      if (!(row >> frame >> name >> value) || row >> extra) Fail("script_cvar_columns");
      HostKeyStep step{ParseUnsigned(frame, 10, "cvar_frame")};
      step.cvar_name = name;
      step.cvar_value = value;
      if (!g_test.host_keys.empty() && step.frame <= g_test.host_keys.back().frame) {
        Fail("script_hostkey_order");
      }
      g_test.host_keys.push_back(step);
    } else if (command == "mark" || command == "scanpoke") {
      std::string frame, minimum, maximum, value, extra;
      HostKeyStep step;
      if (command == "mark") {
        if (!(row >> frame) || row >> extra) Fail("script_mark_columns");
        step.frame = ParseUnsigned(frame, 10, "mark_frame");
        step.mark = true;
      } else {
        std::string step_min, step_max, first, count;
        if (!(row >> frame >> minimum >> maximum >> value)) Fail("script_scanpoke_columns");
        if (row >> step_min && !(row >> step_max)) Fail("script_scanpoke_columns");
        if (row >> first && (!(row >> count) || row >> extra)) Fail("script_scanpoke_columns");
        if (!count.empty()) {
          step.scan_first = uint32_t(ParseUnsigned(first, 10, "scanpoke_first"));
          step.scan_count = uint32_t(ParseUnsigned(count, 10, "scanpoke_count"));
        }
        step.frame = ParseUnsigned(frame, 10, "scanpoke_frame");
        step.scanpoke = true;
        step.scan_min = std::strtof(minimum.c_str(), nullptr);
        step.scan_max = std::strtof(maximum.c_str(), nullptr);
        step.poke_value = std::strtof(value.c_str(), nullptr);
        if (!step_max.empty()) {
          step.scan_step_min = std::strtof(step_min.c_str(), nullptr);
          step.scan_step_max = std::strtof(step_max.c_str(), nullptr);
        }
      }
      if (!g_test.host_keys.empty() && step.frame <= g_test.host_keys.back().frame) {
        Fail("script_hostkey_order");
      }
      g_test.host_keys.push_back(step);
    } else if (command == "snapshot" || command == "poke") {
      std::string frame, first, second, extra;
      HostKeyStep step;
      if (command == "snapshot") {
        if (!(row >> frame >> first) || row >> extra) Fail("script_snapshot_columns");
        step.frame = ParseUnsigned(frame, 10, "snapshot_frame");
        step.snapshot = first;
      } else {
        if (!(row >> frame >> first >> second) || row >> extra) Fail("script_poke_columns");
        step.frame = ParseUnsigned(frame, 10, "poke_frame");
        step.poke = true;
        step.poke_address = uint32_t(ParseUnsigned(first, 16, "poke_address"));
        step.poke_value = std::strtof(second.c_str(), nullptr);
      }
      if (!g_test.host_keys.empty() && step.frame <= g_test.host_keys.back().frame) {
        Fail("script_hostkey_order");
      }
      g_test.host_keys.push_back(step);
    } else if (command == "hostclick") {
      std::string frame, button, x, y, extra;
      if (!(row >> frame >> button >> x >> y) || row >> extra) Fail("script_hostclick_columns");
      HostKeyStep step{ParseUnsigned(frame, 10, "hostclick_frame")};
      if (button == "left") {
        step.button = rex::ui::MouseEvent::Button::kLeft;
      } else if (button == "right") {
        step.button = rex::ui::MouseEvent::Button::kRight;
      } else {
        Fail("script_hostclick_button");
      }
      step.x = uint32_t(ParseUnsigned(x, 10, "hostclick_x"));
      step.y = uint32_t(ParseUnsigned(y, 10, "hostclick_y"));
      if (step.x >= 1280 || step.y >= 720) Fail("script_hostclick_range");
      if (!g_test.host_keys.empty() && step.frame <= g_test.host_keys.back().frame) {
        Fail("script_hostkey_order");
      }
      g_test.host_keys.push_back(step);
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

void RecordCaptureEvent(const Capture& capture, uint32_t width, uint32_t height,
                        const char* source, const std::string& raw_hash);

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
    std::ostringstream raw_hash;
    raw_hash << std::hex << std::uppercase << std::setw(16) << std::setfill('0')
             << Fnv1a64(image.data);
    RecordCaptureEvent(capture, image.width, image.height, source, raw_hash.str());
  }
  return true;
}

void RecordCaptureEvent(const Capture& capture, uint32_t width, uint32_t height,
                        const char* source, const std::string& raw_hash) {
  {
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
       {"width", std::to_string(width)},
       {"height", std::to_string(height)},
       {"source", source},
       {"presenter", PresenterName(capture.presenter)},
       {"session_renderer", "native"},
       {"game_mode", std::to_string(g_test.game_mode.load(std::memory_order_acquire))},
       {"vehicle_pose_valid", vehicle_pose_valid ? "1" : "0"},
       {"vehicle_x", std::to_string(vehicle_x)},
       {"vehicle_y", std::to_string(vehicle_y)},
       {"vehicle_z", std::to_string(vehicle_z)},
       {"raw_hash", raw_hash}});
  }
}

bool WaitSatisfied(const WaitStep& wait) {
  switch (wait.condition) {
    case WaitStep::Condition::kFreeRoam: {
      std::lock_guard lock(g_test.vehicle_pose_mutex);
      return g_test.game_mode.load(std::memory_order_acquire) == 17 &&
          g_test.vehicle_pose_updates > g_test.wait_start_vehicle_updates;
    }
    case WaitStep::Condition::kRallyStageSaved: {
      const auto saved = g_test.rally_stage_saves.load(std::memory_order_acquire);
      if (saved <= g_test.consumed_rally_stage_saves) return false;
      g_test.consumed_rally_stage_saves = saved;
      return true;
    }
    case WaitStep::Condition::kVehicle: {
      std::lock_guard lock(g_test.vehicle_pose_mutex);
      return g_test.vehicle_pose_updates > g_test.wait_start_vehicle_updates;
    }
    case WaitStep::Condition::kVehicleMoved: {
      std::lock_guard lock(g_test.vehicle_pose_mutex);
      if (g_test.vehicle_pose_updates <= g_test.wait_start_vehicle_updates) return false;
      if (!g_test.wait_pose_valid) {
        g_test.wait_pose_valid = true;
        g_test.wait_x = g_test.vehicle_x;
        g_test.wait_y = g_test.vehicle_y;
        g_test.wait_z = g_test.vehicle_z;
        return false;
      }
      const float dx = g_test.vehicle_x - g_test.wait_x;
      const float dy = g_test.vehicle_y - g_test.wait_y;
      const float dz = g_test.vehicle_z - g_test.wait_z;
      return dx * dx + dy * dy + dz * dz >= wait.distance * wait.distance;
    }
    case WaitStep::Condition::kMovie: {
      std::lock_guard lock(g_test.vehicle_pose_mutex);
      return g_test.movie_opens > g_test.wait_start_movie_opens &&
             g_test.last_movie.find(wait.text) != std::string::npos;
    }
    case WaitStep::Condition::kFile: {
      std::lock_guard lock(g_test.vehicle_pose_mutex);
      // A screen often opens its files within frames of the input that
      // requested it, before the script reaches the wait: opens up to
      // kFileWaitLookbackFrames before the wait began count too.
      return std::any_of(g_test.recent_files.begin(), g_test.recent_files.end(),
                         [&](const auto& file) {
                           return (file.sequence > g_test.wait_start_file_opens ||
                                   file.output_frame + kFileWaitLookbackFrames >=
                                       g_test.wait_start_output) &&
                                  file.path.find(wait.text) != std::string::npos;
                         });
    }
  }
  return false;
}

// Returns the script frame for an output frame, holding it at an active
// wait's frame until the wait's condition holds.
uint64_t ApplyWaits(uint64_t output_frame) {
  uint64_t script = output_frame - g_test.wait_offset;
  while (g_test.next_wait < g_test.waits.size() &&
         script >= g_test.waits[g_test.next_wait].frame) {
    const WaitStep& wait = g_test.waits[g_test.next_wait];
    if (!g_test.wait_active) {
      g_test.wait_active = true;
      g_test.wait_start_output = output_frame;
      std::lock_guard lock(g_test.vehicle_pose_mutex);
      g_test.wait_start_vehicle_updates = g_test.vehicle_pose_updates;
      g_test.wait_start_movie_opens = g_test.movie_opens;
      g_test.wait_start_file_opens = g_test.file_opens;
      g_test.wait_pose_valid = false;
    }
    if (WaitSatisfied(wait)) {
      diagnostics::RecordEvent(
          "fh1.render_test.wait",
          {{"frame", std::to_string(wait.frame)},
           {"waited_frames", std::to_string(output_frame - g_test.wait_start_output)},
           {"output_frame", std::to_string(output_frame)}});
      g_test.wait_active = false;
      ++g_test.next_wait;
      continue;
    }
    if (output_frame - g_test.wait_start_output > wait.max_frames) {
      uint64_t pose_updates;
      float distance;
      float vehicle_x, vehicle_y, vehicle_z;
      {
        std::lock_guard lock(g_test.vehicle_pose_mutex);
        pose_updates = g_test.vehicle_pose_updates - g_test.wait_start_vehicle_updates;
        vehicle_x = g_test.vehicle_x;
        vehicle_y = g_test.vehicle_y;
        vehicle_z = g_test.vehicle_z;
        distance = std::hypot(vehicle_x - g_test.wait_x,
                              vehicle_y - g_test.wait_y,
                              vehicle_z - g_test.wait_z);
      }
      std::lock_guard lock(g_test.mutex);
      if (!g_test.stopping) {
        g_test.stopping = true;
        diagnostics::RecordEvent("fh1.render_test.failure",
                                 {{"reason", "wait_timeout"},
                                  {"frame", std::to_string(wait.frame)},
                                  {"game_mode", std::to_string(g_test.game_mode.load())},
                                  {"vehicle_updates", std::to_string(pose_updates)},
                                  {"vehicle_x", std::to_string(vehicle_x)},
                                  {"vehicle_y", std::to_string(vehicle_y)},
                                  {"vehicle_z", std::to_string(vehicle_z)},
                                  {"distance", std::to_string(distance)}});
        g_test.condition.notify_all();
        RequestClose();
      }
    }
    g_test.wait_offset = output_frame - wait.frame;
    return wait.frame;
  }
  return script;
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
    // The null GPU backend draws nothing: the route runs, captures are noted.
    const bool skipped = g_test.headless;
    if (skipped) {
      RecordCaptureEvent(capture, 0, 0, "none_null_gpu_backend", "");
    }
    const bool captured = skipped || (g_test.presenter->CaptureGuestOutput(image) &&
                                      WritePpm(capture, image, "guest_output"));
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
  g_test.output_frame.store(context.frame_sequence, std::memory_order_release);
  // Script frame: the output frame less the frames spent waiting.
  const uint64_t sequence = ApplyWaits(context.frame_sequence);
  if (g_test.stopping) return false;
  uint64_t frame = sequence;
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
  while (g_test.next_host_key < g_test.host_keys.size() &&
         frame >= g_test.host_keys[g_test.next_host_key].frame) {
    const HostKeyStep step = g_test.host_keys[g_test.next_host_key++];
    diagnostics::RecordEvent("fh1.render_test.hostkey",
                             {{"frame", std::to_string(step.frame)},
                              {"key", std::to_string(int(step.key))},
                              {"button", std::to_string(int(step.button))},
                              {"output_frame", std::to_string(context.frame_sequence)}});
    auto* window = g_test.window;
    auto* presenter = g_test.presenter;
    if (step.mark || step.scanpoke) {
      auto* memory = REX_KERNEL_MEMORY();
      if (step.mark) {
        // The title's own heaps (4 KB pages below 0x40000000, 64 KB above).
        std::vector<TestState::MarkRegion> regions;
        size_t bytes = 0;
        for (const auto& [heap_start, heap_end] :
             {std::pair<uint32_t, uint32_t>{0x00010000, 0x40000000},
              std::pair<uint32_t, uint32_t>{0x40000000, 0x7F000000}}) {
          auto* heap = memory->LookupHeap(heap_start);
          if (!heap) continue;
          for (uint32_t address = heap_start; address < heap_end;) {
            rex::memory::HeapAllocationInfo info = {};
            if (!heap->QueryRegionInfo(address, &info) || !info.region_size) break;
            const uint32_t size = std::min(info.region_size, heap_end - address);
            // Committed and readable (guard and no-access pages are skipped).
            if ((info.state & rex::memory::kMemoryAllocationCommit) &&
                (info.protect & rex::memory::kMemoryProtectRead)) {
              const uint8_t* host = memory->TranslateVirtual(address);
              regions.push_back({address, std::vector<uint8_t>(host, host + size)});
              bytes += size;
            }
            address += size;
          }
        }
        g_test.marks.push_back(std::move(regions));
        diagnostics::RecordEvent("fh1.render_test.mark",
                                 {{"count", std::to_string(g_test.marks.size())},
                                  {"bytes", std::to_string(bytes)}});
        continue;
      }
      auto load = [](const uint8_t* bytes) {
        uint32_t bits;
        std::memcpy(&bits, bytes, sizeof(bits));
        bits = (bits >> 24) | ((bits >> 8) & 0xFF00) | ((bits << 8) & 0xFF0000) | (bits << 24);
        float value;
        std::memcpy(&value, &bits, sizeof(value));
        return value;
      };
      // A word's value in a mark, or nullptr where that mark lacks the page.
      auto find = [](const std::vector<TestState::MarkRegion>& regions,
                     uint32_t address) -> const uint8_t* {
        auto it = std::upper_bound(
            regions.begin(), regions.end(), address,
            [](uint32_t a, const TestState::MarkRegion& region) { return a < region.address; });
        if (it == regions.begin()) return nullptr;
        --it;
        if (address + 4 > it->address + it->bytes.size()) return nullptr;
        return it->bytes.data() + (address - it->address);
      };
      std::vector<uint32_t> addresses;
      std::vector<std::pair<float, float>> values;  // first mark's value, step
      if (g_test.marks.size() >= 3) {
        for (const TestState::MarkRegion& region : g_test.marks[0]) {
          for (size_t offset = 0; offset + 4 <= region.bytes.size(); offset += 4) {
            const uint32_t address = region.address + uint32_t(offset);
            float previous = load(region.bytes.data() + offset);
            if (!(previous >= step.scan_min && previous <= step.scan_max)) continue;
            float reference = 0.0f;
            bool steady = true;
            for (size_t i = 1; i < g_test.marks.size() && steady; ++i) {
              const uint8_t* word = find(g_test.marks[i], address);
              if (!word) {
                steady = false;
                break;
              }
              const float current = load(word);
              const float delta = current - previous;
              if (!(current >= step.scan_min && current <= step.scan_max) ||
                  !(delta >= step.scan_step_min && delta <= step.scan_step_max)) {
                steady = false;
              } else if (i == 1) {
                reference = delta;
              } else if (std::abs(delta - reference) > 0.02f * reference) {
                steady = false;
              }
              previous = current;
            }
            if (steady) {
              addresses.push_back(address);
              values.push_back({load(region.bytes.data() + offset), reference});
            }
          }
        }
      }
      uint32_t bits;
      std::memcpy(&bits, &step.poke_value, sizeof(bits));
      bits = (bits >> 24) | ((bits >> 8) & 0xFF00) | ((bits << 8) & 0xFF0000) | (bits << 24);
      // Candidates as index:address:first value:step; the slice is poked.
      std::string listed;
      uint32_t poked = 0;
      for (size_t i = 0; i < addresses.size(); ++i) {
        const bool poke = i >= step.scan_first && i - step.scan_first < step.scan_count;
        if (poke) {
          std::memcpy(memory->TranslateVirtual(addresses[i]), &bits, sizeof(bits));
          ++poked;
        }
        if (i < 64) {
          char text[64];
          std::snprintf(text, sizeof(text), "%s%zu:%08X:%g:%g%s", i ? " " : "", i, addresses[i],
                        values[i].first, values[i].second, poke ? "*" : "");
          listed += text;
        }
      }
      diagnostics::RecordEvent("fh1.render_test.scanpoke",
                               {{"count", std::to_string(addresses.size())},
                                {"poked", std::to_string(poked)},
                                {"value", std::to_string(step.poke_value)},
                                {"addresses", listed}});
      g_test.marks.clear();
      g_test.marks.shrink_to_fit();
      continue;
    }
    if (!step.snapshot.empty() || step.poke) {
      // Guest memory is touched from this thread, as the title runs: a
      // snapshot may tear, which scans for slowly changing values tolerate.
      auto* memory = REX_KERNEL_MEMORY();
      if (step.poke) {
        uint32_t bits;
        std::memcpy(&bits, &step.poke_value, sizeof(bits));
        bits = (bits >> 24) | ((bits >> 8) & 0xFF00) | ((bits << 8) & 0xFF0000) | (bits << 24);
        std::memcpy(memory->TranslatePhysical(step.poke_address), &bits, sizeof(bits));
        diagnostics::RecordEvent("fh1.render_test.poke",
                                 {{"address", std::to_string(step.poke_address)},
                                  {"value", std::to_string(step.poke_value)}});
      } else {
        const auto path = g_test.output / (step.snapshot + ".mem");
        std::ofstream(path, std::ios::binary)
            .write(reinterpret_cast<const char*>(memory->TranslatePhysical(0)), 0x20000000);
        diagnostics::RecordEvent("fh1.render_test.snapshot",
                                 {{"name", step.snapshot},
                                  {"output_frame", std::to_string(context.frame_sequence)}});
      }
      continue;
    }
    g_test.app_context->CallInUIThread([window, presenter, step] {
      if (!step.cvar_name.empty()) {
        const bool set = rex::cvar::SetFlagByName(step.cvar_name, step.cvar_value);
        diagnostics::RecordEvent("fh1.render_test.cvar", {{"name", step.cvar_name},
                                                          {"value", step.cvar_value},
                                                          {"result", set ? "set" : "rejected"}});
        return;
      }
      if (!step.xam_dialog.empty()) {
        auto* provider = rex::kernel::xam::GetXamUiProvider();
        if (!provider) {
          diagnostics::RecordEvent("fh1.render_test.xam_dialog", {{"result", "no_provider"}});
        } else if (step.xam_dialog == "achievements") {
          provider->ShowAchievements([] {
            diagnostics::RecordEvent("fh1.render_test.xam_dialog",
                                     {{"kind", "achievements"}, {"result", "closed"}});
          });
        } else if (step.xam_dialog == "toast") {
          // The first achievement's unlock notification, without unlocking.
          auto& achievements = REX_KERNEL_STATE()->achievements();
          const auto list = achievements.ListAchievements();
          const bool shown =
              !list.empty() && achievements.ShowAchievementNotification(list.front().id);
          diagnostics::RecordEvent("fh1.render_test.xam_dialog",
                                   {{"kind", "toast"}, {"result", shown ? "shown" : "none"}});
        } else if (step.xam_dialog == "message") {
          provider->ShowMessageBox(
              "Storage device", "The selected storage device is full. Choose another device "
              "or free some space, then try saving again.",
              {"Try again", "Continue without saving"}, 0, [](uint32_t button) {
                diagnostics::RecordEvent("fh1.render_test.xam_dialog",
                                         {{"kind", "message"},
                                          {"result", std::to_string(int32_t(button))}});
              });
        } else {
          provider->ShowKeyboard("Name", "Enter a name for this design.", "Pinyon", 15,
                                 [](bool accepted, std::string text) {
                                   diagnostics::RecordEvent("fh1.render_test.xam_dialog",
                                                            {{"kind", "keyboard"},
                                                             {"accepted", accepted ? "1" : "0"},
                                                             {"result", text}});
                                 });
        }
        return;
      }
      if (step.button == rex::ui::MouseEvent::Button::kNone) {
        window->InjectKey(step.key, true);
        window->InjectKey(step.key, false);
        return;
      }
      // Title space as the host UI lays it out: the painted guest image, or
      // the whole window when the last paint drew only UI (a paused title).
      double x = 0.0, y = 0.0, width = window->GetActualPhysicalWidth(),
             height = window->GetActualPhysicalHeight();
      if (auto rect = presenter ? presenter->GetPaintedGuestOutputRectFromUIThread()
                                : std::nullopt) {
        x = rect->x;
        y = rect->y;
        width = rect->width;
        height = rect->height;
      }
      const double scale = std::min(width / 1280.0, height / 720.0);
      if (scale <= 0.0) {
        return;
      }
      x += (width - 1280.0 * scale) * 0.5;
      y += (height - 720.0 * scale) * 0.5;
      window->InjectMouseClick(step.button, int32_t(x + step.x * scale),
                               int32_t(y + step.y * scale));
    });
  }
  std::unique_lock lock(g_test.mutex);
  if (!g_test.clock_hz && g_test.next_capture < g_test.captures.size() &&
      sequence > g_test.captures[g_test.next_capture].frame + 1) {
    const auto& capture = g_test.captures[g_test.next_capture];
    g_test.stopping = true;
    diagnostics::RecordEvent("fh1.render_test.failure",
                             {{"reason", "capture_frame_missed"},
                              {"name", capture.name},
                              {"frame", std::to_string(capture.frame)},
                              {"observed", std::to_string(sequence)}});
    g_test.condition.notify_all();
    RequestClose();
    return false;
  }
  if (g_test.next_capture < g_test.captures.size() &&
      (g_test.clock_hz
           ? frame >= g_test.captures[g_test.next_capture].frame
           : sequence == g_test.captures[g_test.next_capture].frame + 1)) {
    auto& capture = g_test.captures[g_test.next_capture];
    capture.trigger_output_frame = context.frame_sequence;
    capture.presenter = context.presenter;
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
                       : sequence >= g_test.stop_frame + 1) &&
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

void ObserveMovieOpened(std::string_view guest_path) {
  if (!g_test.enabled) return;
  std::lock_guard lock(g_test.vehicle_pose_mutex);
  g_test.last_movie.assign(guest_path);
  ++g_test.movie_opens;
}

void ObserveRallyStageSaved() {
  if (!g_test.enabled) return;
  g_test.rally_stage_saves.fetch_add(1, std::memory_order_release);
}

void ObserveGameMode(uint32_t mode) {
  if (!g_test.enabled) return;
  g_test.game_mode.store(mode, std::memory_order_release);
}

void ObserveFileOpened(std::string_view guest_path) {
  if (!g_test.enabled) return;
  static const bool log = REXCVAR_GET(fh1_render_test_log_file_opens);
  {
    std::lock_guard lock(g_test.vehicle_pose_mutex);
    ++g_test.file_opens;
    if (g_test.recent_files.size() >= 256) {
      g_test.recent_files.erase(g_test.recent_files.begin(),
                                g_test.recent_files.begin() + 128);
    }
    g_test.recent_files.push_back({g_test.file_opens,
                                   g_test.output_frame.load(std::memory_order_acquire),
                                   std::string(guest_path)});
  }
  if (log) {
    diagnostics::RecordEvent(
        "fh1.render_test.file_open",
        {{"path", std::string(guest_path)},
         {"frame", std::to_string(g_test.frame.load(std::memory_order_acquire))},
         {"output_frame", std::to_string(g_test.output_frame.load(std::memory_order_acquire))}});
  }
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
  ++g_test.vehicle_pose_updates;
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
  g_test.headless = !g_test.presenter && graphics_system &&
                   rex::cvar::GetFlagByName("gpu_backend") == "null";
  if ((!g_test.presenter && !g_test.headless) || !g_test.app_context || !g_test.window) {
    Fail("presenter_unavailable");
  }
  if (g_test.headless) {
    diagnostics::RecordEvent("fh1.render_test.headless", {{"gpu_backend", "null"}});
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
