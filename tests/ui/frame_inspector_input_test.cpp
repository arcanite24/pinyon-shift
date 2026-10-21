#include <cassert>
#include <imgui.h>
#include <rex/ui/imgui_drawer.h>
#include <rex/ui/windowed_app_context.h>

using namespace rex::ui;

// No OS window or GPU: exercise the real adapter between ImGui repaints.
class Context final : public WindowedAppContext {
  void NotifyUILoopOfPendingFunctions() override {}
  void PlatformQuitFromUIThread() override {}
};
class TestWindow final : public Window {
public:
  explicit TestWindow(Context& context) : Window(context, "input test", 800, 600) {}
private:
  bool OpenImpl() override { return false; }
  void RequestCloseImpl() override {}
  std::unique_ptr<Surface> CreateSurfaceImpl(Surface::TypeFlags) override { return {}; }
  void RequestPaintImpl() override {}
};
class Drawer final : public ImGuiDrawer {
public:
  explicit Drawer(Window& window) : ImGuiDrawer(&window, 0) {}
  using ImGuiDrawer::OnMouseDown;
  using ImGuiDrawer::OnMouseUp;
  using ImGuiDrawer::OnKeyDown;
  using ImGuiDrawer::OnKeyUp;
};

int main() {
  Context context;
  TestWindow window(context);
  Drawer drawer(window);
  auto& io = drawer.GetIO();
  io.DisplaySize = ImVec2(800, 600);
  io.DeltaTime = 1.0f / 60;
  unsigned char* pixels;
  int width, height;
  io.Fonts->GetTexDataAsRGBA32(&pixels, &width, &height);
  ImGui::NewFrame();
  ImGui::EndFrame();

  MouseEvent click(&window, MouseEvent::Button::kLeft, 100, 100);
  drawer.OnMouseDown(click);
  assert(window.IsMouseCaptureRequested());
  drawer.OnMouseUp(click);
  assert(!window.IsMouseCaptureRequested());
  ImGui::NewFrame();
  assert(ImGui::IsMouseClicked(0));
  ImGui::EndFrame();
  ImGui::NewFrame();
  assert(ImGui::IsMouseReleased(0));
  ImGui::EndFrame();

  KeyEvent control(&window, VirtualKey::kControl, 1, false, false, true, false, false);
  KeyEvent a(&window, VirtualKey::kA, 1, false, false, true, false, false);
  drawer.OnKeyDown(control);
  drawer.OnKeyDown(a);
  drawer.OnKeyUp(a);
  drawer.OnKeyUp(control);
  bool selected = false;
  for (int i = 0; i < 4; ++i) {
    ImGui::NewFrame();
    selected |= io.KeyCtrl && ImGui::IsKeyPressed(ImGuiKey_A, false);
    ImGui::EndFrame();
  }
  assert(selected);
  assert(!io.KeyCtrl && !ImGui::IsKeyDown(ImGuiKey_A));
}
