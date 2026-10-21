#include <rex/graphics/fh1_frame_inspector.h>

#include <cstdlib>
#include <iostream>
#include <thread>

using namespace rex::graphics;
void Check(bool value) {
  if (!value) {
    std::cerr << "inspector check failed\n";
    std::abort();
  }
}

int main() {
  Fh1FrameInspector inspector;
  Fh1InspectionView view;
  uint64_t generation;
  Check(!inspector.Begin(view, generation));
  Check(!inspector.Request(Fh1InspectionView(99)));
  Check(!inspector.Request(Fh1InspectionView::kWireframe));
  Check(!inspector.Request(Fh1InspectionView::kOverdraw));
  Check(!inspector.Request(Fh1InspectionView::kColor));
  inspector.SetCapabilities({true, true, true});
  Check(inspector.Request(Fh1InspectionView::kWireframe));
  Check(!inspector.Request(Fh1InspectionView::kColor));
  Check(inspector.Begin(view, generation));
  Check(view == Fh1InspectionView::kWireframe);
  Check(!inspector.Begin(view, generation));
  auto first = std::make_shared<Fh1FrameInspection>();
  first->frame = 7;
  first->surfaces.push_back({});
  first->surfaces[0].image.rgba = {1, 2, 3, 255};
  inspector.Publish(first, generation);
  auto retained = inspector.snapshot();
  Check(retained && retained->frame == 7 && !inspector.busy());
  Check(inspector.Request(Fh1InspectionView::kColor));
  Check(inspector.Begin(view, generation));
  inspector.Clear();
  Check(inspector.Request(Fh1InspectionView::kOverdraw));
  inspector.Publish(first, generation); // Closing must reject the old GPU work.
  Check(!inspector.snapshot() && inspector.busy());
  Check(inspector.Begin(view, generation));
  auto next = std::make_shared<Fh1FrameInspection>();
  next->frame = 8;
  std::thread gpu([&] { inspector.Publish(next, generation); });
  gpu.join();
  Check(inspector.snapshot()->frame == 8);
  inspector.Clear();
  Check(retained->surfaces[0].image.rgba[1] ==
        2); // CPU image outlives the renderer/mailbox.
  Check(!inspector.snapshot() && !inspector.busy());
  std::cout << "frame inspector contract passed\n";
}
