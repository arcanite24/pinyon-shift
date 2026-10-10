#include "ui/hostui/host_ui.h"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <utility>

#include <rex/input/input.h>
#include <rex/input/input_system.h>
#include <rex/kernel/xam/module.h>
#include <rex/logging.h>
#include <rex/filesystem.h>
#include <rex/rex_app.h>
#include <rex/ui/presenter.h>
#include <rex/ui/ui_event.h>
#include <rex/ui/virtual_key.h>
#include <rex/ui/window.h>
#include <rex/ui/windowed_app_context.h>

#include "pinyon_shift_diagnostics.h"
#include "ui/hostui/fh1_archive.h"
#include "ui/hostui/xds_texture.h"

namespace pinyon_shift::hostui {
namespace {

using rex::ui::ImmediateTexture;
using rex::ui::ImmediateTextureFilter;
using rex::ui::VirtualKey;

// The title lays its UI out in 1280x720 with a 90 % safe area.
constexpr float kTitleWidth = 1280.0f;
constexpr float kTitleHeight = 720.0f;
constexpr float kSafeLeft = 64.0f;
constexpr float kSafeTop = 36.0f;
constexpr float kSafeRight = kTitleWidth - kSafeLeft;
constexpr float kSafeBottom = kTitleHeight - kSafeTop;

// Layout in title pixels, after the pause menu: a large display-font title,
// display-font rows with a slanted magenta brush behind the focused one, and
// a button help bar at the bottom.
constexpr float kTitleSize = 64.0f;
constexpr float kTitleBaseline = 150.0f;
constexpr float kRowSize = 40.0f;
constexpr float kRowPitch = 54.0f;
constexpr float kRowsTop = 196.0f;
constexpr float kRowsLeft = 128.0f;
constexpr float kValueRight = 1050.0f;
constexpr float kValueSize = 30.0f;
constexpr float kBadgeSize = 20.0f;
constexpr float kHelpSize = 26.0f;
constexpr float kHelpBaseline = kSafeBottom - 20.0f;
constexpr size_t kVisibleRows = 8;
// The panel inside DirtMasks/SelectionContainer.xds, with a little of its
// ragged border.
constexpr UvRect kSelectionMaskPanel = {0.21f, 0.12f, 0.79f, 0.87f};

constexpr uint32_t Rgba(uint32_t r, uint32_t g, uint32_t b, uint32_t a = 255) {
  return r | g << 8 | b << 16 | a << 24;
}
constexpr uint32_t kWhite = Rgba(255, 255, 255);
constexpr uint32_t kDimWhite = Rgba(255, 255, 255, 215);
constexpr uint32_t kDisabled = Rgba(255, 255, 255, 90);
constexpr uint32_t kMagenta = Rgba(230, 0, 126);
constexpr uint32_t kOrange = Rgba(255, 106, 19);
// Dark over the left where the title's own pause menu sits (it opens behind
// the host menu when the title sees system UI), lighter towards the right.
constexpr uint32_t kBackdropLeft = Rgba(8, 6, 12, 238);
constexpr uint32_t kBackdropRight = Rgba(8, 6, 12, 150);

// Fonts.zip members; the "ru" variants add Cyrillic to the same design.
constexpr const char* kFontMembers[][2] = {
    {"eru_vector_aa.dt", "e_vector_aa.dt"},  // heavy italic display (pause menu items)
    {"bru_vector_aa.dt", "b_vector_aa.dt"},  // condensed slab (help bar, values)
};

std::unique_ptr<ImmediateTexture> LoadTexture(rex::ui::ImmediateDrawer& drawer,
                                              const Fh1Archive& archive, const char* name,
                                              bool white) {
  auto data = archive.Read(name);
  auto image = data ? DecodeXds(*data) : std::nullopt;
  if (!image) {
    REXLOG_WARN("Host UI: could not load texture {}", name);
    return nullptr;
  }
  if (white) {
    // Masks carry their shape in alpha; the vertex colour tints them.
    for (size_t i = 0; i < image->rgba.size(); i += 4) {
      image->rgba[i] = image->rgba[i + 1] = image->rgba[i + 2] = 255;
    }
  }
  return drawer.CreateTexture(image->width, image->height, ImmediateTextureFilter::kLinear, false,
                              image->rgba.data());
}

}  // namespace

HostUi::HostUi(rex::ReXApp& app, rex::ui::Presenter& presenter, rex::ui::ImmediateDrawer& drawer,
               rex::ui::Window& window, rex::input::InputSystem* input_system,
               std::filesystem::path game_data_root)
    : app_(app),
      presenter_(presenter),
      drawer_(drawer),
      window_(window),
      input_system_(input_system),
      game_data_root_(std::move(game_data_root)) {}

HostUi::~HostUi() {
  alive_.reset();
  screens_.clear();
  toasts_.clear();
  FinishClose();
  ReleaseDrawer();
}

void HostUi::EnsureDrawer() {
  if (!drawer_registered_) {
    drawer_registered_ = true;
    presenter_.AddUIDrawerFromUIThread(this, kZOrder);
  }
}

void HostUi::ReleaseDrawer() {
  if (drawer_registered_) {
    drawer_registered_ = false;
    presenter_.RemoveUIDrawerFromUIThread(this);
  }
}

void HostUi::ShowToast(std::string heading, std::string title, std::string detail,
                       rex::ui::ImmediateTexture* icon) {
  if (!LoadAssets()) {
    return;
  }
  toasts_.push_back(Toast{std::move(heading), std::move(title), std::move(detail), icon});
  EnsureDrawer();
  RequestPaint();
}

bool HostUi::LoadAssets() {
  if (assets_loaded_ || assets_failed_) {
    return assets_loaded_;
  }
  const auto started = std::chrono::steady_clock::now();
  const auto ui_root = game_data_root_ / "media" / "ui";
  auto fonts = Fh1Archive::Open(ui_root / "Fonts.zip");
  if (!fonts) {
    REXLOG_ERROR("Host UI: cannot open {}", rex::path_to_utf8(ui_root / "Fonts.zip"));
    assets_failed_ = true;
    return false;
  }
  for (size_t face = 0; face < size_t(Face::kCount); ++face) {
    for (const char* member : kFontMembers[face]) {
      if (auto data = fonts->Read(member)) {
        fonts_[face] = VectorFont::Parse(*data);
        if (fonts_[face]) {
          break;
        }
      }
    }
    if (!fonts_[face]) {
      REXLOG_ERROR("Host UI: cannot load vector font {}", kFontMembers[face][1]);
      assets_failed_ = true;
      return false;
    }
  }
  const uint8_t white[4] = {255, 255, 255, 255};
  white_ = drawer_.CreateTexture(1, 1, ImmediateTextureFilter::kNearest, false, white);
  if (auto textures = Fh1Archive::Open(ui_root / "textures" / "Horizon.zip")) {
    selection_mask_ = LoadTexture(drawer_, *textures, "DirtMasks/SelectionContainer.xds", true);
    button_a_ = LoadTexture(drawer_, *textures, "Controller/A_Button.xds", false);
    button_b_ = LoadTexture(drawer_, *textures, "Controller/B_Button.xds", false);
  } else {
    REXLOG_WARN("Host UI: cannot open Horizon.zip; drawing without textures");
  }
  assets_loaded_ = true;
  REXLOG_INFO("Host UI assets loaded in {} ms",
              std::chrono::duration_cast<std::chrono::milliseconds>(
                  std::chrono::steady_clock::now() - started)
                  .count());
  return true;
}

bool HostUi::OpenDialog(std::unique_ptr<MenuScreen> screen) {
  if (is_open()) {
    Push(std::move(screen));
    return true;
  }
  dialog_mode_ = true;
  const bool opened = Open(std::move(screen));
  dialog_mode_ = opened;
  return opened;
}

void HostUi::Finish(const MenuScreen* screen) {
  if (applying_) {
    // The screen's own action is running; remove it once it returns.
    finish_pending_ = screen;
    return;
  }
  RemoveScreen(screen);
}

void HostUi::RemoveScreen(const MenuScreen* screen) {
  const auto it = std::find_if(screens_.begin(), screens_.end(),
                               [screen](const auto& entry) { return entry.get() == screen; });
  if (it == screens_.end()) {
    return;
  }
  screens_.erase(it);
  if (screens_.empty()) {
    Close();
  } else {
    RequestPaint();
  }
}

bool HostUi::Open(std::unique_ptr<MenuScreen> screen) {
  if (!screen || !LoadAssets()) {
    return false;
  }
  screens_.clear();
  screens_.push_back(std::move(screen));
  diagnostics::RecordEvent("hostui.open", {{"screen", screens_.back()->title()}});
  pad_.Reset();
  draining_ = false;
  if (!registered_) {
    registered_ = true;
    SetGuestUiActive(true);
    EnsureDrawer();
    window_.AddInputListener(this, kZOrder);
  }
  RequestPaint();
  return true;
}

void HostUi::Push(std::unique_ptr<MenuScreen> screen) {
  if (is_open() && screen) {
    screens_.push_back(std::move(screen));
    diagnostics::RecordEvent("hostui.screen", {{"screen", screens_.back()->title()},
                                               {"depth", std::to_string(screens_.size())}});
    RequestPaint();
  }
}

void HostUi::Close() {
  if (applying_) {
    // A row's action is running; destroying its screen now would destroy
    // the running function. Apply closes once the action returns.
    close_pending_ = true;
    return;
  }
  // Screens left without finishing (a dialog closed with Start) cancel.
  while (!screens_.empty()) {
    auto screen = std::move(screens_.back());
    screens_.pop_back();
    screen->NotifyBack();
  }
  row_rects_.clear();
  if (!registered_) {
    return;
  }
  // Stay registered, drawing nothing, until the input is released.
  draining_ = true;
  drain_started_ = std::chrono::steady_clock::now();
  RequestPaint();
}

void HostUi::FinishClose() {
  draining_ = false;
  dialog_mode_ = false;
  held_keys_.clear();
  if (!registered_) {
    return;
  }
  registered_ = false;
  window_.RemoveInputListener(this);
  SetGuestUiActive(false);
  if (toasts_.empty()) {
    ReleaseDrawer();
  }
  // Unregistered: the drawer, the input listener and the guest input
  // capture are all released.
  diagnostics::RecordEvent("hostui.closed");
  RequestPaint();
}

bool HostUi::InputReleased() {
  if (!held_keys_.empty()) {
    return false;
  }
  if (!input_system_) {
    return true;
  }
  rex::input::X_INPUT_STATE state = {};
  using rex::X_RESULT;  // X_ERROR_SUCCESS expands to an unqualified cast
  if (input_system_->GetHostPadState(0, &state) != X_ERROR_SUCCESS) {
    return true;
  }
  return !uint16_t(state.gamepad.buttons) && !state.gamepad.left_trigger &&
         !state.gamepad.right_trigger;
}

void HostUi::SetGuestUiActive(bool active) {
  if (guest_ui_active_ == active) {
    return;
  }
  guest_ui_active_ = active;
  if (active) {
    app_.AcquireGuestInputCapture();
    // XAM dialogs arrive with XN_SYS_UI already signalled by the dispatcher.
    signalled_system_ui_ = !dialog_mode_;
    if (signalled_system_ui_) {
      rex::kernel::xam::xeXamSetHostUIActive(true);
    }
  } else {
    app_.ReleaseGuestInputCapture();
    if (signalled_system_ui_) {
      rex::kernel::xam::xeXamSetHostUIActive(false);
    }
    signalled_system_ui_ = false;
  }
}

void HostUi::RequestPaint() { presenter_.RequestUIPaintFromUIThread(); }

void HostUi::CaptureKey(int virtual_key) {
  RunOnTopScreen([virtual_key](MenuScreen& screen) { screen.CaptureKey(virtual_key); });
}

void HostUi::RunOnTopScreen(const std::function<void(MenuScreen&)>& callback) {
  applying_ = true;
  callback(*screens_.back());
  applying_ = false;
  if (close_pending_) {
    close_pending_ = false;
    finish_pending_ = nullptr;
    Close();
    return;
  }
  if (const MenuScreen* finished = std::exchange(finish_pending_, nullptr)) {
    RemoveScreen(finished);
    return;
  }
  RequestPaint();
}

void HostUi::Apply(NavCommand command) {
  if (!is_open()) {
    return;
  }
  if (command == NavCommand::kClose) {
    Close();
    return;
  }
  applying_ = true;
  const MenuScreen::Result result = screens_.back()->Handle(command);
  applying_ = false;
  if (close_pending_) {
    close_pending_ = false;
    finish_pending_ = nullptr;
    Close();
    return;
  }
  if (const MenuScreen* finished = std::exchange(finish_pending_, nullptr)) {
    RemoveScreen(finished);
    return;
  }
  if (result == MenuScreen::Result::kBack) {
    auto left = std::move(screens_.back());
    screens_.pop_back();
    left->NotifyBack();
    if (screens_.empty()) {
      Close();
      return;
    }
    diagnostics::RecordEvent("hostui.screen", {{"screen", screens_.back()->title()},
                                               {"depth", std::to_string(screens_.size())}});
  }
  RequestPaint();
}

void HostUi::PollPad() {
  if (is_open() && screens_.back()->ticks()) {
    // Polling runs inside Draw; tick after it, and keep painting so the
    // screen keeps ticking while the game does not present.
    window_.app_context().CallInUIThreadDeferred(
        [alive = std::weak_ptr<bool>(alive_), this] {
          if (alive.expired() || !is_open() || !screens_.back()->ticks()) {
            return;
          }
          RunOnTopScreen([](MenuScreen& screen) { screen.Tick(); });
        });
    pad_.Reset();
    return;
  }
  if (!input_system_) {
    return;
  }
  rex::input::X_INPUT_STATE state = {};
  using rex::X_RESULT;  // X_ERROR_SUCCESS expands to an unqualified cast
  if (input_system_->GetHostPadState(0, &state) != X_ERROR_SUCCESS) {
    return;
  }
  const auto now = uint64_t(std::chrono::duration_cast<std::chrono::milliseconds>(
                                std::chrono::steady_clock::now() - start_time_)
                                .count());
  std::vector<NavCommand> commands =
      pad_.Poll(uint16_t(state.gamepad.buttons), int16_t(state.gamepad.thumb_lx),
                int16_t(state.gamepad.thumb_ly), now);
  if (commands.empty()) {
    return;
  }
  // Polling runs inside Draw, where settings that resize the window or
  // recreate the swap chain must not apply; run the commands after it.
  window_.app_context().CallInUIThreadDeferred(
      [alive = std::weak_ptr<bool>(alive_), this, commands = std::move(commands)] {
        if (alive.expired()) {
          return;
        }
        for (NavCommand command : commands) {
          Apply(command);
        }
      });
}

HostUi::Canvas HostUi::ComputeCanvas(rex::ui::UIDrawContext& context) const {
  float x = 0.0f, y = 0.0f;
  float width = float(context.render_target_width());
  float height = float(context.render_target_height());
  if (auto rect = presenter_.GetPaintedGuestOutputRectFromUIThread()) {
    x = float(rect->x);
    y = float(rect->y);
    width = float(rect->width);
    height = float(rect->height);
  }
  // Fit the 16:9 title space into the guest image.
  Canvas canvas;
  canvas.scale = std::min(width / kTitleWidth, height / kTitleHeight);
  canvas.x = x + (width - kTitleWidth * canvas.scale) * 0.5f;
  canvas.y = y + (height - kTitleHeight * canvas.scale) * 0.5f;
  return canvas;
}

HostUi::Text& HostUi::TextFor(Face face, float title_pixels) {
  const int pixels = std::max(1, int(std::lround(title_pixels * canvas_.scale)));
  const std::pair<int, int> key(int(face), pixels);
  for (auto& [existing, text] : texts_) {
    if (existing == key) {
      return text;
    }
  }
  atlases_.push_back(std::make_unique<GlyphAtlas>(*fonts_[size_t(face)], float(pixels)));
  Text text;
  text.atlas = atlases_.back().get();
  texts_.emplace_back(key, std::move(text));
  return texts_.back().second;
}

void HostUi::PrepareText(Text& text, std::u32string_view string) {
  text.dirty |= text.atlas->Prepare(string);
  if (text.dirty) {
    // Batches drawn earlier this frame use the old texture; point them at the
    // replacement, which holds a superset of its glyphs.
    auto replacement = drawer_.CreateTexture(text.atlas->width(), text.atlas->height(),
                                             ImmediateTextureFilter::kLinear, false,
                                             text.atlas->rgba().data());
    if (text.texture) {
      for (Batch& batch : batches_) {
        if (batch.texture == text.texture.get()) {
          batch.texture = replacement.get();
        }
      }
    }
    text.texture = std::move(replacement);
    text.dirty = false;
  }
}

float HostUi::DrawText(Face face, float title_pixels, std::string_view string, float x,
                       float baseline, uint32_t color, float align) {
  Text& text = TextFor(face, title_pixels);
  const std::u32string decoded = DecodeUtf8(string);
  PrepareText(text, decoded);
  const GlyphAtlas& atlas = *text.atlas;
  const float width = atlas.Measure(decoded);
  // Snap the pen to whole pixels; the atlas samples at pixel centres.
  float pen_x = std::round(canvas_.x + x * canvas_.scale - width * align);
  const float pen_y = std::round(canvas_.y + baseline * canvas_.scale);
  const float inverse_width = 1.0f / float(atlas.width());
  const float inverse_height = 1.0f / float(atlas.height());
  for (char32_t code_point : decoded) {
    const GlyphAtlas::Entry* entry = atlas.Find(code_point);
    if (!entry) {
      continue;
    }
    if (entry->width && entry->height) {
      const float x0 = std::round(pen_x) + float(entry->left);
      const float y0 = pen_y + float(entry->top);
      if (batches_.empty() || batches_.back().texture != text.texture.get() ||
          batches_.back().vertices.size() > 60000) {
        batches_.push_back(Batch{.texture = text.texture.get()});
      }
      Batch& batch = batches_.back();
      const auto base = uint16_t(batch.vertices.size());
      const float u0 = float(entry->x) * inverse_width;
      const float v0 = float(entry->y) * inverse_height;
      const float u1 = float(entry->x + entry->width) * inverse_width;
      const float v1 = float(entry->y + entry->height) * inverse_height;
      const float x1 = x0 + float(entry->width);
      const float y1 = y0 + float(entry->height);
      batch.vertices.push_back({x0, y0, u0, v0, color});
      batch.vertices.push_back({x1, y0, u1, v0, color});
      batch.vertices.push_back({x1, y1, u1, v1, color});
      batch.vertices.push_back({x0, y1, u0, v1, color});
      for (uint16_t index : {0, 1, 2, 0, 2, 3}) {
        batch.indices.push_back(uint16_t(base + index));
      }
    }
    pen_x += entry->advance;
  }
  return width / canvas_.scale;
}

float HostUi::DrawWrapped(Face face, float title_pixels, std::string_view text, float x,
                          float top, float width, uint32_t color) {
  Text& measure = TextFor(face, title_pixels);
  const float line_height = title_pixels * 1.25f;
  float y = top;
  size_t start = 0;
  while (start < text.size()) {
    // The longest run of whole words that fits; a hard break ends a line.
    size_t end = start, fitted = start;
    while (end < text.size()) {
      size_t next = end;
      while (next < text.size() && text[next] != ' ' && text[next] != '\n') {
        ++next;
      }
      const std::u32string candidate = DecodeUtf8(text.substr(start, next - start));
      PrepareText(measure, candidate);
      if (fitted != start && measure.atlas->Measure(candidate) / canvas_.scale > width) {
        break;
      }
      fitted = next;
      end = next;
      if (end < text.size() && text[end] == '\n') {
        break;
      }
      ++end;
    }
    if (fitted == start) {
      fitted = std::min(text.size(), start + 1);
    }
    y += line_height;
    DrawText(face, title_pixels, text.substr(start, fitted - start), x, y, color);
    start = fitted;
    while (start < text.size() && (text[start] == ' ' || text[start] == '\n')) {
      const bool hard_break = text[start] == '\n';
      ++start;
      if (hard_break) {
        break;
      }
    }
  }
  return y - top + line_height * 0.35f;
}

void HostUi::DrawRect(float x, float y, float width, float height, uint32_t color,
                      ImmediateTexture* texture, float skew, UvRect uv) {
  DrawGradient(x, y, width, height, color, color, texture, skew, uv);
}

void HostUi::DrawGradient(float x, float y, float width, float height, uint32_t left_color,
                          uint32_t right_color, ImmediateTexture* texture, float skew,
                          UvRect uv) {
  // Solid fills sample a white texel: the drawer's untextured path draws
  // nothing here.
  if (!texture) {
    texture = white_.get();
  }
  if (batches_.empty() || batches_.back().texture != texture ||
      batches_.back().vertices.size() > 60000) {
    batches_.push_back(Batch{.texture = texture});
  }
  Batch& batch = batches_.back();
  const float x0 = canvas_.x + x * canvas_.scale;
  const float y0 = canvas_.y + y * canvas_.scale;
  const float x1 = x0 + width * canvas_.scale;
  const float y1 = y0 + height * canvas_.scale;
  const float shift = skew * canvas_.scale;
  const auto base = uint16_t(batch.vertices.size());
  batch.vertices.push_back({x0 + shift, y0, uv.u0, uv.v0, left_color});
  batch.vertices.push_back({x1 + shift, y0, uv.u1, uv.v0, right_color});
  batch.vertices.push_back({x1, y1, uv.u1, uv.v1, right_color});
  batch.vertices.push_back({x0, y1, uv.u0, uv.v1, left_color});
  for (uint16_t index : {0, 1, 2, 0, 2, 3}) {
    batch.indices.push_back(uint16_t(base + index));
  }
}

void HostUi::RecordLayout(const std::string& title, size_t first_batch, size_t first_vertex) {
  // Once per screen and output size: where the menu drew, against the
  // title's 90 % safe area, so scripted routes can check the layout.
  const std::string key = title + "@" + std::to_string(canvas_.x) + "," +
                          std::to_string(canvas_.y) + "," + std::to_string(canvas_.scale);
  if (key == layout_key_) {
    return;
  }
  layout_key_ = key;
  float x0 = 1e9f, y0 = 1e9f, x1 = -1e9f, y1 = -1e9f;
  for (size_t b = first_batch; b < batches_.size(); ++b) {
    const auto& vertices = batches_[b].vertices;
    for (size_t v = b == first_batch ? first_vertex : 0; v < vertices.size(); ++v) {
      x0 = std::min(x0, vertices[v].x);
      y0 = std::min(y0, vertices[v].y);
      x1 = std::max(x1, vertices[v].x);
      y1 = std::max(y1, vertices[v].y);
    }
  }
  const float safe_x0 = canvas_.x + kSafeLeft * canvas_.scale;
  const float safe_y0 = canvas_.y + kSafeTop * canvas_.scale;
  const float safe_x1 = canvas_.x + kSafeRight * canvas_.scale;
  const float safe_y1 = canvas_.y + kSafeBottom * canvas_.scale;
  const bool inside = x0 >= safe_x0 && y0 >= safe_y0 && x1 <= safe_x1 && y1 <= safe_y1;
  const auto f = [](float value) { return std::to_string(int(std::lround(value))); };
  diagnostics::RecordEvent("hostui.layout",
                           {{"screen", title},
                            {"scale", std::to_string(canvas_.scale)},
                            {"content", f(x0) + "," + f(y0) + "," + f(x1) + "," + f(y1)},
                            {"safe", f(safe_x0) + "," + f(safe_y0) + "," + f(safe_x1) + "," +
                                         f(safe_y1)},
                            {"inside", inside ? "1" : "0"}});
}

void HostUi::Flush() {
  for (const Batch& batch : batches_) {
    if (batch.indices.empty()) {
      continue;
    }
    rex::ui::ImmediateDrawBatch draw_batch;
    draw_batch.vertices = batch.vertices.data();
    draw_batch.vertex_count = int(batch.vertices.size());
    draw_batch.indices = batch.indices.data();
    draw_batch.index_count = int(batch.indices.size());
    drawer_.BeginDrawBatch(draw_batch);
    rex::ui::ImmediateDraw draw;
    draw.count = int(batch.indices.size());
    draw.texture = batch.texture;
    drawer_.Draw(draw);
    drawer_.EndDrawBatch();
  }
  batches_.clear();
}

void HostUi::Draw(rex::ui::UIDrawContext& context) {
  if (draining_) {
    // A second is plenty for a press to end; never hold the guest longer.
    constexpr auto kMaximumDrain = std::chrono::seconds(1);
    if (InputReleased() || std::chrono::steady_clock::now() - drain_started_ > kMaximumDrain) {
      FinishClose();
    } else {
      RequestPaint();
    }
  } else if (is_open()) {
    DrawHud(context);
    PollPad();
    if (is_open()) {
      DrawMenu(context);
    }
  } else {
    DrawHud(context);
    DrawRallyPace(context);
    DrawOverlay(context);
  }
  DrawToasts(context);
  if (!registered_ && toasts_.empty() && !HasHud()) {
    ReleaseDrawer();
  }
}

bool HostUi::HasHud() const {
  return (hud_source_ && !hud_source_().empty()) ||
         (rally_pace_source_ && !rally_pace_source_().icons.empty()) ||
         (overlay_source_ && !overlay_source_().empty());
}

void HostUi::DrawRallyPace(rex::ui::UIDrawContext& context) {
  if (!rally_pace_source_) return;
  const auto phrase = rally_pace_source_();
  if (phrase.icons.empty()) {
    if (!rally_pace_drawn_.icons.empty()) {
      diagnostics::RecordEvent("dlc.rally.pace_hud", {{"icons", ""}, {"visible", "0"}});
      rally_pace_drawn_ = {};
    }
    return;
  }
  if (!PrepareCanvas(context)) return;
  if (!rally_pace_atlas_attempted_) {
    rally_pace_atlas_attempted_ = true;
    // The accepted atlas is 512x64 with five 64-pixel turn tiles. No owned
    // pixels are shipped with the executable or extracted into the repository.
    std::ifstream input(rally_pace_atlas_path_, std::ios::binary | std::ios::ate);
    if (input && input.tellg() == 65588) {
      std::vector<uint8_t> data(65588);
      input.seekg(0); input.read(reinterpret_cast<char*>(data.data()), data.size());
      auto image = input ? DecodeXds(data) : std::nullopt;
      if (image && image->width == 512 && image->height == 64)
        rally_pace_atlas_ = drawer_.CreateTexture(512, 64, ImmediateTextureFilter::kLinear,
                                               false, image->rgba.data());
    }
    if (!rally_pace_atlas_) {
      diagnostics::RecordEvent("dlc.rally.pace_hud_error", {{"error", "owned co-driver atlas unavailable"}});
      return;
    }
  }
  if (!rally_pace_atlas_) return;
  // Leave the speedometer, minimap, race timer and central sight line clear.
  constexpr float size = 64, pitch = 72, top = 76;
  const size_t count = std::min(phrase.icons.size(), size_t(5));
  const float left = (kTitleWidth - (float(count - 1) * pitch + size)) / 2;
  drawer_.Begin(context, float(context.render_target_width()), float(context.render_target_height()));
  std::string drawn_icons;
  for (size_t i = 0; i < count; ++i) {
    const auto& icon = phrase.icons[i];
    int tile = -1;
    for (const auto& [name, index] : {std::pair{"Easy", 0}, {"Medium", 1}, {"Hard", 2},
                                     {"Square", 3}, {"Hairpin", 4}})
      if (icon == std::string(name) + "Right" || icon == std::string(name) + "Left") tile = index;
    if (tile < 0) continue;
    UvRect uv{float(tile) / 8, 0, float(tile + 1) / 8, 1};
    if (icon.ends_with("Left")) std::swap(uv.u0, uv.u1);
    DrawRect(left + float(i) * pitch, top, size, size, kWhite, rally_pace_atlas_.get(), 0, uv);
    if (i == phrase.active) DrawRect(left + float(i) * pitch + 10, top + size + 3, 44, 3, kWhite);
    if (!drawn_icons.empty()) drawn_icons += ',';
    drawn_icons += icon;
  }
  Flush(); drawer_.End();
  if (phrase != rally_pace_drawn_ || canvas_.scale != rally_pace_drawn_scale_) {
    diagnostics::RecordEvent("dlc.rally.pace_hud", {{"icons", drawn_icons}, {"visible", "1"},
        {"active", phrase.active == size_t(-1) ? "none" : std::to_string(phrase.active)},
        {"scale", std::to_string(canvas_.scale)},
        {"width", std::to_string(context.render_target_width())},
        {"height", std::to_string(context.render_target_height())}});
    rally_pace_drawn_ = phrase; rally_pace_drawn_scale_ = canvas_.scale;
  }
}

void HostUi::DrawOverlay(rex::ui::UIDrawContext& context) {
  if (!overlay_source_) return;
  const auto discs = overlay_source_();
  if (discs.empty() || !PrepareCanvas(context)) return;
  drawer_.Begin(context, float(context.render_target_width()),
                float(context.render_target_height()));
  for (const auto& disc : discs) {
    DrawDisc(disc.x, disc.y, disc.radius, disc.pressed ? Rgba(255, 255, 255, 120)
                                                       : Rgba(255, 255, 255, 45));
    if (!disc.label.empty()) {
      // Labels in title units: the canvas maps them back to these pixels.
      const float size = std::max(14.0f, disc.radius / canvas_.scale * 0.55f);
      DrawText(Face::kLabel, size, disc.label, (disc.x - canvas_.x) / canvas_.scale,
               (disc.y - canvas_.y) / canvas_.scale + size * 0.35f, Rgba(255, 255, 255, 210),
               0.5f);
    }
  }
  Flush();
  drawer_.End();
  // The controls fade out after a while without a touch.
  RequestPaint();
}

void HostUi::DrawDisc(float x, float y, float radius, uint32_t color) {
  ImmediateTexture* texture = white_.get();
  if (batches_.empty() || batches_.back().texture != texture ||
      batches_.back().vertices.size() > 60000) {
    batches_.push_back(Batch{.texture = texture});
  }
  Batch& batch = batches_.back();
  constexpr int kSegments = 32;
  const auto centre = uint16_t(batch.vertices.size());
  batch.vertices.push_back({x, y, 0.5f, 0.5f, color});
  for (int i = 0; i <= kSegments; ++i) {
    const float angle = float(i) * 6.2831853f / float(kSegments);
    batch.vertices.push_back(
        {x + radius * std::cos(angle), y + radius * std::sin(angle), 0.5f, 0.5f, color});
  }
  for (int i = 0; i < kSegments; ++i) {
    batch.indices.push_back(centre);
    batch.indices.push_back(uint16_t(centre + 1 + i));
    batch.indices.push_back(uint16_t(centre + 2 + i));
  }
}

void HostUi::HudChanged() {
  if (HasHud() && LoadAssets()) {
    EnsureDrawer();
  }
  RequestPaint();
}

void HostUi::DrawHud(rex::ui::UIDrawContext& context) {
  if (!hud_source_) return;
  const auto labels = hud_source_();
  if (labels.empty() || !PrepareCanvas(context)) return;
  drawer_.Begin(context, float(context.render_target_width()),
                float(context.render_target_height()));
  for (const auto& label : labels) {
    // A one-pixel shadow keeps light text readable over the sky.
    DrawText(Face::kLabel, label.size, label.text, label.x + 1.5f, label.y + 1.5f,
             Rgba(0, 0, 0, 200));
    DrawText(Face::kLabel, label.size, label.text, label.x, label.y, kWhite);
  }
  Flush();
  drawer_.End();
}

bool HostUi::PrepareCanvas(rex::ui::UIDrawContext& context) {
  canvas_ = ComputeCanvas(context);
  if (canvas_.scale <= 0.0f) {
    return false;
  }
  if (canvas_.scale != atlas_scale_) {
    // New output size: rasterize the fonts again at the new pixel sizes.
    batches_.clear();
    texts_.clear();
    atlases_.clear();
    atlas_scale_ = canvas_.scale;
  }
  return true;
}

void HostUi::DrawToasts(rex::ui::UIDrawContext& context) {
  if (toasts_.empty() || !PrepareCanvas(context)) {
    return;
  }
  // One at a time, 5 s each with a quarter-second fade at both ends, in the
  // top of the safe area where the title's own notifications do not sit.
  constexpr float kShowSeconds = 5.0f;
  constexpr float kFadeSeconds = 0.25f;
  const auto now = std::chrono::steady_clock::now();
  Toast& toast = toasts_.front();
  if (toast.shown == std::chrono::steady_clock::time_point{}) {
    toast.shown = now;
  }
  const float age = std::chrono::duration<float>(now - toast.shown).count();
  if (age >= kShowSeconds) {
    toasts_.erase(toasts_.begin());
    RequestPaint();
    return;
  }
  const float alpha = std::clamp(std::min(age, kShowSeconds - age) / kFadeSeconds, 0.0f, 1.0f);
  const auto fade = [alpha](uint32_t color) {
    return (color & 0x00FFFFFFu) | (uint32_t(float(color >> 24) * alpha) << 24);
  };
  constexpr float kWidth = 520.0f, kHeight = 96.0f;
  const float left = (kTitleWidth - kWidth) * 0.5f;
  const float top = kSafeTop + 8.0f;
  drawer_.Begin(context, float(context.render_target_width()),
                float(context.render_target_height()));
  DrawGradient(left, top, kWidth, kHeight, fade(kBackdropLeft), fade(kBackdropRight));
  DrawRect(left, top, 8.0f, kHeight, fade(kMagenta));
  float text_left = left + 28.0f;
  if (toast.icon) {
    DrawRect(left + 24.0f, top + 16.0f, 64.0f, 64.0f, fade(kWhite), toast.icon);
    text_left = left + 104.0f;
  }
  DrawText(Face::kLabel, kBadgeSize, toast.heading, text_left, top + 28.0f, fade(kMagenta));
  DrawText(Face::kDisplay, 30.0f, toast.title, text_left, top + 60.0f, fade(kWhite));
  if (!toast.detail.empty()) {
    DrawText(Face::kLabel, kBadgeSize, toast.detail, text_left, top + 84.0f, fade(kDimWhite));
  }
  Flush();
  drawer_.End();
  RequestPaint();
}

void HostUi::DrawMenu(rex::ui::UIDrawContext& context) {
  if (!PrepareCanvas(context)) {
    return;
  }
  const MenuScreen& screen = *screens_.back();

  drawer_.Begin(context, float(context.render_target_width()),
                float(context.render_target_height()));
  // Dim the title behind the menu across the whole guest image.
  if (auto rect = presenter_.GetPaintedGuestOutputRectFromUIThread()) {
    const Canvas saved = canvas_;
    canvas_ = Canvas{float(rect->x), float(rect->y), 1.0f};
    DrawGradient(0.0f, 0.0f, float(rect->width), float(rect->height), kBackdropLeft,
                 kBackdropRight);
    canvas_ = saved;
  } else {
    DrawGradient(0.0f, 0.0f, kTitleWidth, kTitleHeight, kBackdropLeft, kBackdropRight);
  }
  const size_t content_batch = batches_.size() - 1;
  const size_t content_vertex = batches_.back().vertices.size();

  DrawText(Face::kDisplay, kTitleSize, screen.title(), kRowsLeft - 16.0f, kTitleBaseline, kWhite);
  // A dialog's text sits between the title and its rows.
  float rows_top = kRowsTop;
  if (!screen.body().empty()) {
    rows_top += DrawWrapped(Face::kLabel, kValueSize, screen.body(), kRowsLeft, kRowsTop,
                            kSafeRight - kRowsLeft - 64.0f, kDimWhite) +
                16.0f;
  }

  const auto& rows = screen.rows();
  // A note takes the last row's place, above the button help.
  const std::string note = screen.note();
  const size_t visible_rows = note.empty() ? kVisibleRows : kVisibleRows - 1;
  size_t first = 0;
  if (rows.size() > visible_rows && screen.focus() >= visible_rows / 2) {
    first = std::min(screen.focus() - visible_rows / 2, rows.size() - visible_rows);
  }
  row_rects_.assign(rows.size(), RowRect{0, 0, -1, -1});
  for (size_t i = first; i < rows.size() && i < first + visible_rows; ++i) {
    const MenuRow& row = rows[i];
    const bool focused = i == screen.focus();
    const bool enabled = row.is_enabled();
    const float top = rows_top + float(i - first) * kRowPitch;
    const float baseline = top + kRowPitch * 0.72f;
    const float row_right = row.value ? kValueRight + 40.0f : kRowsLeft + 560.0f;
    if (focused) {
      DrawRect(kRowsLeft - 36.0f, top + 2.0f, row_right - kRowsLeft + 72.0f, kRowPitch - 4.0f,
               kMagenta, selection_mask_.get(), 10.0f, kSelectionMaskPanel);
    }
    const uint32_t label_color = !enabled ? kDisabled : (focused ? kWhite : kDimWhite);
    const float label_width =
        DrawText(Face::kDisplay, kRowSize, row.label, kRowsLeft, baseline, label_color);
    // Rows that usually apply at once show the badge only while a change
    // still waits for a restart.
    const bool pending = row.restart_pending && row.restart_pending();
    if (row.restart_required || pending) {
      DrawText(Face::kLabel, kBadgeSize, "RESTART", kRowsLeft + label_width + 16.0f,
               baseline - 12.0f, pending ? kOrange : kDisabled);
    }
    if (row.value) {
      const std::string value = row.value();
      const float value_baseline = baseline - 3.0f;
      const float value_width =
          DrawText(Face::kLabel, kValueSize, value, kValueRight, value_baseline, label_color, 1.0f);
      if (focused && row.adjust) {
        DrawText(Face::kLabel, kValueSize, "<", kValueRight - value_width - 16.0f, value_baseline,
                 kWhite, 1.0f);
        DrawText(Face::kLabel, kValueSize, ">", kValueRight + 16.0f, value_baseline, kWhite);
      }
    }
    row_rects_[i] = RowRect{canvas_.x + (kRowsLeft - 36.0f) * canvas_.scale,
                            canvas_.y + top * canvas_.scale,
                            canvas_.x + (row_right + 36.0f) * canvas_.scale,
                            canvas_.y + (top + kRowPitch) * canvas_.scale};
  }

  if (!note.empty()) {
    const float note_top = rows_top + float(std::min(rows.size(), visible_rows)) * kRowPitch;
    DrawText(Face::kLabel, kValueSize, note, kRowsLeft, note_top + 44.0f, kOrange);
  }

  // Button help bar.
  float help_x = kRowsLeft - 16.0f;
  const auto help = [&](ImmediateTexture* icon, const char* label) {
    if (icon) {
      DrawRect(help_x, kHelpBaseline - 24.0f, 30.0f, 30.0f, kWhite, icon);
      help_x += 36.0f;
    }
    help_x += DrawText(Face::kLabel, kHelpSize, label, help_x, kHelpBaseline, kWhite) + 32.0f;
  };
  help(button_a_.get(), "SELECT");
  help(button_b_.get(), screens_.size() > 1 ? "BACK" : "RESUME");

  RecordLayout(screen.title(), content_batch, content_vertex);
  Flush();
  drawer_.End();
  // Keep painting while open so the pad is polled even when the title is
  // paused and presents nothing new.
  RequestPaint();
}

void HostUi::OnKeyDown(rex::ui::KeyEvent& e) {
  const VirtualKey key = e.virtual_key();
  if (key >= VirtualKey::kF1 && key <= VirtualKey::kF24) {
    return;  // keybinds stay live
  }
  if (std::find(held_keys_.begin(), held_keys_.end(), int(key)) == held_keys_.end()) {
    held_keys_.push_back(int(key));
  }
  if (!is_open()) {
    return;
  }
  e.set_handled(true);
  if (screens_.back()->captures_keys()) {
    if (!e.prev_state()) {
      CaptureKey(int(key));
    }
    return;
  }
  switch (key) {
    case VirtualKey::kUp:
    case VirtualKey::kNumpad8:
      Apply(NavCommand::kUp);
      break;
    case VirtualKey::kDown:
    case VirtualKey::kNumpad2:
      Apply(NavCommand::kDown);
      break;
    case VirtualKey::kLeft:
    case VirtualKey::kNumpad4:
      Apply(NavCommand::kLeft);
      break;
    case VirtualKey::kRight:
    case VirtualKey::kNumpad6:
      Apply(NavCommand::kRight);
      break;
    case VirtualKey::kSpace:
      // Typed as a character (OnKeyChar) on text-entry screens.
      if (!e.prev_state() && !screens_.back()->accepts_text()) {
        Apply(NavCommand::kAccept);
      }
      break;
    case VirtualKey::kReturn:
      if (!e.prev_state()) {
        Apply(NavCommand::kAccept);
      }
      break;
    case VirtualKey::kBack:
      if (screens_.back()->accepts_text()) {
        screens_.back()->InputText(U'\b');
        RequestPaint();
        break;
      }
      [[fallthrough]];
    case VirtualKey::kEscape:
      if (!e.prev_state()) {
        Apply(NavCommand::kBack);
      }
      break;
    default:
      break;
  }
}

void HostUi::OnKeyUp(rex::ui::KeyEvent& e) {
  held_keys_.erase(std::remove(held_keys_.begin(), held_keys_.end(), int(e.virtual_key())),
                   held_keys_.end());
  if (is_open() && !(e.virtual_key() >= VirtualKey::kF1 && e.virtual_key() <= VirtualKey::kF24)) {
    e.set_handled(true);
  }
}

void HostUi::OnKeyChar(rex::ui::KeyEvent& e) {
  if (!is_open()) {
    return;
  }
  e.set_handled(true);
  // The virtual key slot holds the typed code point.
  const auto code_point = char32_t(e.virtual_key());
  if (screens_.back()->accepts_text() && code_point >= 0x20 && code_point != 0x7F) {
    screens_.back()->InputText(code_point);
    RequestPaint();
  }
}

void HostUi::OnMouseMove(rex::ui::MouseEvent& e) {
  if (!is_open()) {
    return;
  }
  e.set_handled(true);
  for (size_t i = 0; i < row_rects_.size(); ++i) {
    const RowRect& rect = row_rects_[i];
    if (float(e.x()) >= rect.x0 && float(e.x()) < rect.x1 && float(e.y()) >= rect.y0 &&
        float(e.y()) < rect.y1) {
      if (screens_.back()->focus() != i && screens_.back()->SetFocus(i)) {
        RequestPaint();
      }
      return;
    }
  }
}

void HostUi::OnMouseDown(rex::ui::MouseEvent& e) {
  if (!is_open()) {
    return;
  }
  e.set_handled(true);
  if (screens_.back()->captures_keys()) {
    switch (e.button()) {
      case rex::ui::MouseEvent::Button::kLeft:
        CaptureKey(int(VirtualKey::kLButton));
        break;
      case rex::ui::MouseEvent::Button::kRight:
        CaptureKey(int(VirtualKey::kRButton));
        break;
      case rex::ui::MouseEvent::Button::kMiddle:
        CaptureKey(int(VirtualKey::kMButton));
        break;
      default:
        break;
    }
    return;
  }
  if (e.button() == rex::ui::MouseEvent::Button::kRight) {
    Apply(NavCommand::kBack);
    return;
  }
  if (e.button() != rex::ui::MouseEvent::Button::kLeft) {
    return;
  }
  // The row under the pointer, focused first: a mouse has hovered it
  // already, but a tap on a touch screen arrives with no hover (AP-4.3).
  size_t focus = row_rects_.size();
  for (size_t i = 0; i < row_rects_.size(); ++i) {
    const RowRect& rect = row_rects_[i];
    if (float(e.x()) >= rect.x0 && float(e.x()) < rect.x1 && float(e.y()) >= rect.y0 &&
        float(e.y()) < rect.y1) {
      focus = i;
      break;
    }
  }
  if (focus >= row_rects_.size() || focus >= screens_.back()->rows().size()) {
    return;
  }
  if (focus != screens_.back()->focus() && !screens_.back()->SetFocus(focus)) {
    return;  // not a row that takes focus
  }
  const MenuRow& row = screens_.back()->rows()[focus];
  if (row.value && row.adjust) {
    // Clicking a value row steps it: on the value's left part backwards,
    // anywhere else forwards.
    const float split = canvas_.x + (kValueRight - 60.0f) * canvas_.scale;
    Apply(float(e.x()) < split ? NavCommand::kLeft : NavCommand::kRight);
  } else {
    Apply(NavCommand::kAccept);
  }
}

void HostUi::OnMouseUp(rex::ui::MouseEvent& e) {
  if (is_open()) {
    e.set_handled(true);
  }
}

void HostUi::OnMouseWheel(rex::ui::MouseEvent& e) {
  if (!is_open()) {
    return;
  }
  e.set_handled(true);
  if (e.scroll_y() > 0) {
    Apply(NavCommand::kUp);
  } else if (e.scroll_y() < 0) {
    Apply(NavCommand::kDown);
  }
}

}  // namespace pinyon_shift::hostui
