#pragma once

#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <vector>

namespace pinyon_shift::hostui {

enum class NavCommand {
  kUp,
  kDown,
  kLeft,
  kRight,
  kAccept,
  kBack,
  kClose,  // leave every screen (Start, like the title's pause menu)
};

// One row of a host menu. A row with `value` shows it on the right and
// changes it with `adjust` (-1 or +1); a row without is an action row that
// runs `activate`.
struct MenuRow {
  std::string label;
  std::function<std::string()> value;
  std::function<void(int direction)> adjust;
  std::function<void()> activate;
  std::function<bool()> enabled;
  // The change takes effect after a restart; the screen shows a badge,
  // highlighted while `restart_pending` reports a saved change not yet live.
  bool restart_required = false;
  std::function<bool()> restart_pending;

  bool is_enabled() const { return !enabled || enabled(); }
};

class MenuScreen {
 public:
  MenuScreen(std::string title, std::vector<MenuRow> rows,
             std::function<std::string()> note = nullptr);

  const std::string& title() const { return title_; }
  // Paragraph drawn wrapped under the title (dialog text), or empty.
  const std::string& body() const { return body_; }
  void set_body(std::string body) { body_ = std::move(body); }
  // Called when the screen is left with back or close, not when an action
  // finishes it (dialogs report a cancel here).
  void set_on_back(std::function<void()> on_back) { on_back_ = std::move(on_back); }
  void NotifyBack() {
    if (auto on_back = std::move(on_back_)) {
      on_back();
    }
  }
  // Typed characters for text entry: printable code points, and '\b' for
  // backspace (which then does not leave the screen).
  void set_text_input(std::function<void(char32_t)> text_input) {
    text_input_ = std::move(text_input);
  }
  bool accepts_text() const { return bool(text_input_); }
  void InputText(char32_t code_point) {
    if (text_input_) {
      text_input_(code_point);
    }
  }
  // The next key or mouse button press as a virtual key code, before menu
  // navigation sees it, for a screen that asks for a key (a keybind).
  void set_key_capture(std::function<void(int virtual_key)> key_capture) {
    key_capture_ = std::move(key_capture);
  }
  bool captures_keys() const { return bool(key_capture_); }
  void CaptureKey(int virtual_key) {
    if (key_capture_) {
      key_capture_(virtual_key);
    }
  }
  // A line shown under the rows, or empty.
  std::string note() const { return note_ ? note_() : std::string(); }
  const std::vector<MenuRow>& rows() const { return rows_; }
  size_t focus() const { return focus_; }
  // Moves the focus to `index` if that row is enabled.
  bool SetFocus(size_t index);

  enum class Result { kNone, kChanged, kBack };
  // Applies a navigation command: up and down move the focus over enabled
  // rows with wrap-around, left and right adjust a value row, accept runs an
  // action row or steps a value row forward, back leaves the screen.
  Result Handle(NavCommand command);

 private:
  std::string title_;
  std::string body_;
  std::vector<MenuRow> rows_;
  std::function<std::string()> note_;
  std::function<void()> on_back_;
  std::function<void(char32_t)> text_input_;
  std::function<void(int)> key_capture_;
  size_t focus_ = 0;
};

// Turns polled pad state into navigation commands with the usual menu key
// repeat. Buttons use the XINPUT_GAMEPAD bit values.
class PadNavigator {
 public:
  static constexpr uint16_t kDpadUp = 0x0001;
  static constexpr uint16_t kDpadDown = 0x0002;
  static constexpr uint16_t kDpadLeft = 0x0004;
  static constexpr uint16_t kDpadRight = 0x0008;
  static constexpr uint16_t kStart = 0x0010;
  static constexpr uint16_t kButtonA = 0x1000;
  static constexpr uint16_t kButtonB = 0x2000;
  static constexpr int16_t kStickThreshold = 16000;
  static constexpr uint64_t kRepeatDelayMs = 400;
  static constexpr uint64_t kRepeatIntervalMs = 110;

  // Returns the commands for this poll. Directions (d-pad or left stick)
  // repeat while held; A, B and Start fire once per press. The first poll after
  // Reset only records what is held, so the press that opened the UI does
  // not also act inside it.
  std::vector<NavCommand> Poll(uint16_t buttons, int16_t thumb_lx, int16_t thumb_ly,
                               uint64_t now_ms);
  void Reset() { primed_ = false; }

 private:
  bool primed_ = false;
  uint16_t previous_buttons_ = 0;
  int held_direction_ = -1;
  uint64_t next_repeat_ms_ = 0;
};

}  // namespace pinyon_shift::hostui
