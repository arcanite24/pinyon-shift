#pragma once

#include <string_view>

namespace pinyon_shift::config {

struct KeyDefault {
  std::string_view name;
  std::string_view keys;
};

// Keyboard defaults chosen for driving (#432), the same on every desktop
// platform. The pad's FH1 roles: RT throttle, LT brake, the left stick steers
// and moves through menus, A handbrake and accept, B shift up and back,
// X shift down, Y rewind, LB clutch, RB camera, Start pause. Driving needs
// only the keys around WASD, and nothing needs a numpad (laptops).
// New configurations get all of them; RESET KEYS restores them.
inline constexpr KeyDefault kDefaultKeys[] = {
    {"keybind_a", "Space,Return,LMB"},
    {"keybind_b", "E,Backspace"},
    {"keybind_x", "Q"},
    {"keybind_y", "R"},
    {"keybind_left_trigger", "S"},
    {"keybind_right_trigger", "W"},
    {"keybind_left_shoulder", "Z"},
    {"keybind_right_shoulder", "C"},
    {"keybind_lstick_up", "Up"},
    {"keybind_lstick_down", "Down"},
    {"keybind_lstick_left", "A,Left"},
    {"keybind_lstick_right", "D,Right"},
    {"keybind_lstick_press", "F"},
    {"keybind_rstick_up", "I"},
    {"keybind_rstick_down", "K"},
    {"keybind_rstick_left", "J"},
    {"keybind_rstick_right", "L"},
    {"keybind_rstick_press", "V"},
    {"keybind_dpad_up", "Shift+Up"},
    {"keybind_dpad_down", "Shift+Down"},
    {"keybind_dpad_left", "Shift+Left"},
    {"keybind_dpad_right", "Shift+Right"},
    {"keybind_back", "Tab,M"},
    {"keybind_start", "Escape"},
};

// The keys configurations had through schema 28 (the SDK's defaults with
// Pinyon Shift's A and Start). Migration writes them into older files so a
// player's keys do not change under them; RESET KEYS moves to kDefaultKeys.
inline constexpr KeyDefault kSchema28Keys[] = {
    {"keybind_a", "LMB,Space"},
    {"keybind_b", "Quote,Backspace"},
    {"keybind_x", "L"},
    {"keybind_y", "P"},
    {"keybind_left_trigger", "Q,I"},
    {"keybind_right_trigger", "E,O"},
    {"keybind_left_shoulder", "1"},
    {"keybind_right_shoulder", "3"},
    {"keybind_lstick_up", "W"},
    {"keybind_lstick_down", "S"},
    {"keybind_lstick_left", "A"},
    {"keybind_lstick_right", "D"},
    {"keybind_lstick_press", "F"},
    {"keybind_rstick_up", "Up"},
    {"keybind_rstick_down", "Down"},
    {"keybind_rstick_left", "Left"},
    {"keybind_rstick_right", "Right"},
    {"keybind_rstick_press", "K"},
    {"keybind_dpad_up", "Shift+Up"},
    {"keybind_dpad_down", "Shift+Down"},
    {"keybind_dpad_left", "Shift+Left"},
    {"keybind_dpad_right", "Shift+Right"},
    {"keybind_back", "Z,Tab"},
    {"keybind_start", "Return"},
};

// Host keys. F-keys are media keys by default on Mac keyboards, so macOS
// adds its own conventions (Cmd+, settings, Ctrl+Cmd+F fullscreen, Cmd+Q
// quit); the F-keys stay as alternatives everywhere.
#if defined(__APPLE__)
inline constexpr std::string_view kGameMenuKeys = "F6,Cmd+Comma";
inline constexpr std::string_view kPhotoKeys = "F8,Cmd+Shift+P";
inline constexpr std::string_view kTrainerKeys = "F10,Cmd+T";
inline constexpr std::string_view kFullscreenKeys = "F11,Ctrl+Cmd+F";
inline constexpr std::string_view kQuitKeys = "Cmd+Q";
#else
inline constexpr std::string_view kGameMenuKeys = "F6";
inline constexpr std::string_view kPhotoKeys = "F8";
inline constexpr std::string_view kTrainerKeys = "F10";
inline constexpr std::string_view kFullscreenKeys = "F11,Alt+Return";
inline constexpr std::string_view kQuitKeys = "";
#endif
// Your music (#420): next and previous track while it plays.
inline constexpr std::string_view kMusicNextKeys = "F9";
inline constexpr std::string_view kMusicPreviousKeys = "Shift+F9";

}  // namespace pinyon_shift::config
