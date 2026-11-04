#include "ui/hostui/menu.h"

#include <utility>

namespace pinyon_shift::hostui {

MenuScreen::MenuScreen(std::string title, std::vector<MenuRow> rows,
                       std::function<std::string()> note)
    : title_(std::move(title)), rows_(std::move(rows)), note_(std::move(note)) {
  for (size_t i = 0; i < rows_.size(); ++i) {
    if (rows_[i].is_enabled()) {
      focus_ = i;
      break;
    }
  }
}

bool MenuScreen::SetFocus(size_t index) {
  if (index >= rows_.size() || !rows_[index].is_enabled()) {
    return false;
  }
  focus_ = index;
  return true;
}

MenuScreen::Result MenuScreen::Handle(NavCommand command) {
  if (command_) {
    // A painted screen handles its own commands; back still leaves it
    // unless the screen consumed it (closing a detail view).
    const Result result = command_(command);
    if (result != Result::kNone || command != NavCommand::kBack) {
      return result;
    }
  }
  if (command == NavCommand::kBack || command == NavCommand::kClose) {
    return Result::kBack;
  }
  if (command >= NavCommand::kPrevTab) {
    return Result::kNone;
  }
  if (rows_.empty()) {
    return Result::kNone;
  }
  if (command == NavCommand::kUp || command == NavCommand::kDown) {
    const size_t count = rows_.size();
    size_t index = focus_;
    for (size_t step = 0; step < count; ++step) {
      index = command == NavCommand::kDown ? (index + 1) % count : (index + count - 1) % count;
      if (rows_[index].is_enabled()) {
        const bool moved = index != focus_;
        focus_ = index;
        return moved ? Result::kChanged : Result::kNone;
      }
    }
    return Result::kNone;
  }
  MenuRow& row = rows_[focus_];
  if (!row.is_enabled()) {
    return Result::kNone;
  }
  if (command == NavCommand::kLeft || command == NavCommand::kRight) {
    if (row.value && row.adjust) {
      row.adjust(command == NavCommand::kRight ? 1 : -1);
      return Result::kChanged;
    }
    return Result::kNone;
  }
  // kAccept.
  if (row.activate) {
    row.activate();
    return Result::kChanged;
  }
  if (row.value && row.adjust) {
    row.adjust(1);
    return Result::kChanged;
  }
  return Result::kNone;
}

std::vector<NavCommand> PadNavigator::Poll(uint16_t buttons, int16_t thumb_lx, int16_t thumb_ly,
                                           uint64_t now_ms) {
  int direction = -1;
  if ((buttons & kDpadUp) || thumb_ly > kStickThreshold) {
    direction = int(NavCommand::kUp);
  } else if ((buttons & kDpadDown) || thumb_ly < -kStickThreshold) {
    direction = int(NavCommand::kDown);
  } else if ((buttons & kDpadLeft) || thumb_lx < -kStickThreshold) {
    direction = int(NavCommand::kLeft);
  } else if ((buttons & kDpadRight) || thumb_lx > kStickThreshold) {
    direction = int(NavCommand::kRight);
  }

  std::vector<NavCommand> commands;
  if (!primed_) {
    primed_ = true;
    previous_buttons_ = buttons;
    held_direction_ = direction;
    next_repeat_ms_ = UINT64_MAX;  // a direction held at open waits for release
    return commands;
  }
  if (direction != held_direction_) {
    held_direction_ = direction;
    if (direction >= 0) {
      commands.push_back(NavCommand(direction));
      next_repeat_ms_ = now_ms + kRepeatDelayMs;
    }
  } else if (direction >= 0 && now_ms >= next_repeat_ms_) {
    commands.push_back(NavCommand(direction));
    next_repeat_ms_ = now_ms + kRepeatIntervalMs;
  }
  const uint16_t pressed = buttons & ~previous_buttons_;
  if (pressed & kButtonA) {
    commands.push_back(NavCommand::kAccept);
  }
  if (pressed & kButtonB) {
    commands.push_back(NavCommand::kBack);
  }
  if (pressed & kStart) {
    commands.push_back(NavCommand::kClose);
  }
  if (pressed & kShoulderLeft) {
    commands.push_back(NavCommand::kPrevTab);
  }
  if (pressed & kShoulderRight) {
    commands.push_back(NavCommand::kNextTab);
  }
  if (pressed & kButtonX) {
    commands.push_back(NavCommand::kAuxX);
  }
  if (pressed & kButtonY) {
    commands.push_back(NavCommand::kAuxY);
  }
  previous_buttons_ = buttons;
  return commands;
}

}  // namespace pinyon_shift::hostui
