#pragma once

#include <memory>
#include <vector>

#include <rex/system/interfaces/graphics.h>
#include <rex/ui/imgui_dialog.h>

namespace pinyon_shift::ui {

// UI thread only. Destroy before the ImGui and immediate drawers.
class FrameInspector final : public rex::ui::ImGuiDialog {
public:
  FrameInspector(rex::ui::ImGuiDrawer &imgui, rex::ui::ImmediateDrawer &drawer,
                 rex::system::IGraphicsSystem &graphics, bool replay);
  ~FrameInspector() override;
  bool is_open() const { return open_; }

private:
  void OnDraw(ImGuiIO &io) override;
  void Preview(const rex::graphics::Fh1InspectionImage &image, size_t index);
  rex::ui::ImmediateDrawer &drawer_;
  rex::system::IGraphicsSystem &graphics_;
  std::shared_ptr<rex::graphics::Fh1FrameInspector> mailbox_;
  std::shared_ptr<const rex::graphics::Fh1FrameInspection> snapshot_;
  std::vector<std::unique_ptr<rex::ui::ImmediateTexture>> textures_;
  bool open_ = true, replay_ = false;
  int selected_surface_ = 0, selected_resolve_ = 0, view_ = 0;
  char dump_path_[4096] = {};
  std::string message_;
};
} // namespace pinyon_shift::ui
