#pragma once

#include <chrono>
#include <cstdint>
#include <filesystem>
#include <functional>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include <rex/ui/immediate_drawer.h>
#include <rex/ui/ui_drawer.h>
#include <rex/ui/window_listener.h>

#include "ui/hostui/glyph_atlas.h"
#include "ui/hostui/menu.h"
#include "ui/hostui/vector_font.h"
#include "dlc/rally_pace_notes.h"

namespace rex {
class ReXApp;
namespace input {
class InputSystem;
}
namespace ui {
class Presenter;
class Window;
}  // namespace ui
}  // namespace rex

namespace pinyon_shift::hostui {

// A texture sub-rectangle in normalized coordinates.
struct UvRect {
  float u0 = 0.0f;
  float v0 = 0.0f;
  float u1 = 1.0f;
  float v1 = 1.0f;
};

// Host-drawn menus over the title (NP-1.3): drawn with the title's own vector
// fonts and UI textures, rasterized at load from the player's disc, and laid
// out in the title's 1280x720 space inside the painted guest output so it
// scales with the internal resolution and keeps to the 90 % safe area.
//
// While a menu is open the title sees system UI (XN_SYS_UI, XamIsUIActive),
// the guest reads untouched pads and no mouse-and-keyboard input, and the
// menu takes pad, keyboard and mouse input itself. Everything runs on the UI
// thread; drawing never runs guest code.
class HostUi final : public rex::ui::UIDrawer, public rex::ui::WindowInputListener {
 public:
  // Above the guest's input listeners and below the ImGui XAM dialogs.
  static constexpr size_t kZOrder = 32;

  HostUi(rex::ReXApp& app, rex::ui::Presenter& presenter, rex::ui::ImmediateDrawer& drawer,
         rex::ui::Window& window, rex::input::InputSystem* input_system,
         std::filesystem::path game_data_root);
  ~HostUi() override;

  bool is_open() const { return !screens_.empty(); }
  // Opens with `screen` as the root. Fails (and logs) when the title's UI
  // assets cannot be loaded.
  bool Open(std::unique_ptr<MenuScreen> screen);
  void Push(std::unique_ptr<MenuScreen> screen);
  // Shows a XAM system dialog: on top of an open menu, or on its own. On its
  // own it captures input like a menu but does not signal system UI itself;
  // the XAM dispatcher already does.
  bool OpenDialog(std::unique_ptr<MenuScreen> screen);
  // Removes `screen` (after its action finished it); closes the UI when it
  // was the only one. Safe to call from the screen's own row action.
  void Finish(const MenuScreen* screen);
  // Shows a notification in the top of the safe area for a few seconds,
  // over the running title (no input capture), queued behind earlier ones.
  // `icon` must outlive the notification.
  void ShowToast(std::string heading, std::string title, std::string detail,
                 rex::ui::ImmediateTexture* icon);

  // Persistent text over the title (mods' HUD labels, NP-11), in the
  // title's 1280x720 layout. The source is read on every draw; call
  // HudChanged (UI thread) when it goes from empty to not or back.
  struct HudText {
    std::string text;
    float x = 0.0f, y = 0.0f, size = 24.0f;
  };
  void SetHudSource(std::function<std::vector<HudText>()> source) { hud_source_ = std::move(source); }
  // Private base-disc Rally adapter, using the player's owned icon atlas.
  void SetRallyPaceSource(std::function<rally::PaceHud()> source, std::filesystem::path atlas) {
    rally_pace_source_ = std::move(source);
    rally_pace_atlas_path_ = std::move(atlas);
  }
  // Discs drawn over the game while no menu is open (the touch controls), in
  // window pixels; pressed ones are brighter.
  struct OverlayDisc {
    float x = 0.0f, y = 0.0f, radius = 0.0f;
    std::string label;
    bool pressed = false;
  };
  void SetOverlaySource(std::function<std::vector<OverlayDisc>()> source) {
    overlay_source_ = std::move(source);
  }
  void HudChanged();
  // Closes every screen. Safe to call from a row's action. The guest gets its
  // input back only once no pad button or key is held, so the press that
  // closed the menu does not also reach the title (B would leave its pause
  // menu, Enter would press Start).
  void Close();

  void Draw(rex::ui::UIDrawContext& context) override;

  void OnKeyDown(rex::ui::KeyEvent& e) override;
  void OnKeyUp(rex::ui::KeyEvent& e) override;
  void OnKeyChar(rex::ui::KeyEvent& e) override;
  void OnMouseDown(rex::ui::MouseEvent& e) override;
  void OnMouseMove(rex::ui::MouseEvent& e) override;
  void OnMouseUp(rex::ui::MouseEvent& e) override;
  void OnMouseWheel(rex::ui::MouseEvent& e) override;

 private:
  enum class Face { kDisplay, kLabel, kCount };

  struct Canvas {
    float x = 0.0f;  // render-target pixels of the 1280x720 origin
    float y = 0.0f;
    float scale = 1.0f;  // render-target pixels per title pixel
  };

  struct Batch {
    std::vector<rex::ui::ImmediateVertex> vertices;
    std::vector<uint16_t> indices;
    rex::ui::ImmediateTexture* texture = nullptr;
  };

  struct Text {
    GlyphAtlas* atlas = nullptr;
    std::unique_ptr<rex::ui::ImmediateTexture> texture;
    bool dirty = true;
  };

  bool LoadAssets();
  void DrawMenu(rex::ui::UIDrawContext& context);
  void DrawToasts(rex::ui::UIDrawContext& context);
  void DrawHud(rex::ui::UIDrawContext& context);
  void DrawRallyPace(rex::ui::UIDrawContext& context);
  void DrawOverlay(rex::ui::UIDrawContext& context);
  void DrawDisc(float x, float y, float radius, uint32_t color);
  bool HasHud() const;
  // Sets the canvas for this draw; false while there is nothing to draw to.
  bool PrepareCanvas(rex::ui::UIDrawContext& context);
  void EnsureDrawer();
  void ReleaseDrawer();
  void Apply(NavCommand command);
  void PollPad();
  void RequestPaint();
  void SetGuestUiActive(bool active);
  void FinishClose();
  bool InputReleased();

  Canvas ComputeCanvas(rex::ui::UIDrawContext& context) const;
  Text& TextFor(Face face, float title_pixels);
  void PrepareText(Text& text, std::u32string_view string);
  float DrawText(Face face, float title_pixels, std::string_view string, float x, float baseline,
                 uint32_t color, float align = 0.0f);
  void DrawRect(float x, float y, float width, float height, uint32_t color,
                rex::ui::ImmediateTexture* texture = nullptr, float skew = 0.0f,
                UvRect uv = {});
  void DrawGradient(float x, float y, float width, float height, uint32_t left_color,
                    uint32_t right_color, rex::ui::ImmediateTexture* texture = nullptr,
                    float skew = 0.0f, UvRect uv = {});
  void Flush();
  // Draws `text` word-wrapped to `width` title pixels from `top`; returns
  // the height used.
  float DrawWrapped(Face face, float title_pixels, std::string_view text, float x, float top,
                    float width, uint32_t color);
  void RemoveScreen(const MenuScreen* screen);
  void RecordLayout(const std::string& title, size_t first_batch, size_t first_vertex);

  rex::ReXApp& app_;
  rex::ui::Presenter& presenter_;
  rex::ui::ImmediateDrawer& drawer_;
  rex::ui::Window& window_;
  rex::input::InputSystem* input_system_;
  std::filesystem::path game_data_root_;

  std::vector<std::unique_ptr<MenuScreen>> screens_;
  PadNavigator pad_;
  // Whether the input listener and guest input capture are registered (a
  // menu is open), and whether this is registered as a presenter drawer
  // (menus or notifications on screen).
  bool registered_ = false;
  bool drawer_registered_ = false;
  struct Toast {
    std::string heading, title, detail;
    rex::ui::ImmediateTexture* icon = nullptr;
    std::chrono::steady_clock::time_point shown{};  // set when it first draws
  };
  std::vector<Toast> toasts_;
  std::function<std::vector<HudText>()> hud_source_;
  std::function<rally::PaceHud()> rally_pace_source_;
  std::filesystem::path rally_pace_atlas_path_;
  std::unique_ptr<rex::ui::ImmediateTexture> rally_pace_atlas_;
  bool rally_pace_atlas_attempted_ = false;
  rally::PaceHud rally_pace_drawn_;
  float rally_pace_drawn_scale_ = 0;
  std::function<std::vector<OverlayDisc>()> overlay_source_;
  // Closed, waiting for held buttons and keys to be released.
  bool draining_ = false;
  std::chrono::steady_clock::time_point drain_started_;
  std::vector<int> held_keys_;
  // Expires with this object, for deferred work queued from Draw.
  std::shared_ptr<bool> alive_ = std::make_shared<bool>(true);
  bool applying_ = false;
  bool close_pending_ = false;
  const MenuScreen* finish_pending_ = nullptr;
  bool guest_ui_active_ = false;
  // Opened by OpenDialog: capture input without signalling system UI.
  bool dialog_mode_ = false;
  bool signalled_system_ui_ = false;
  std::chrono::steady_clock::time_point start_time_ = std::chrono::steady_clock::now();

  // Assets, loaded on first open.
  bool assets_loaded_ = false;
  bool assets_failed_ = false;
  std::optional<VectorFont> fonts_[size_t(Face::kCount)];
  std::unique_ptr<rex::ui::ImmediateTexture> white_;
  std::unique_ptr<rex::ui::ImmediateTexture> selection_mask_;
  std::unique_ptr<rex::ui::ImmediateTexture> button_a_;
  std::unique_ptr<rex::ui::ImmediateTexture> button_b_;

  // Per-draw state.
  Canvas canvas_;
  float atlas_scale_ = 0.0f;
  std::vector<std::unique_ptr<GlyphAtlas>> atlases_;
  std::vector<std::pair<std::pair<int, int>, Text>> texts_;  // (face, pixels) -> text
  std::vector<Batch> batches_;
  // Row hit rectangles in window pixels from the latest draw, for the mouse.
  struct RowRect {
    float x0, y0, x1, y1;
  };
  std::vector<RowRect> row_rects_;
  // Screen and output size of the last recorded layout event.
  std::string layout_key_;
};

}  // namespace pinyon_shift::hostui
