#include "ui/fh1_ui_api.h"

#include <cassert>

using pinyon_shift::ui::Api;
using pinyon_shift::ui::Status;

int main() {
  Api api(2);
  pinyon_shift::ui::SceneHandle scene;
  assert(api.SceneReady("pause_menu", 1, &scene) == Status::kOk);
  assert(api.SetText(scene, "title", "Pinyon Shift") == Status::kOk);
  assert(api.AddMenuItem(scene, "demo", "Pinyon Shift") == Status::kOk);
  assert(api.AddMenuItem(scene, "demo", "Duplicate") == Status::kDuplicateId);
  assert(api.SetVisible(scene, "title", true) == Status::kQueueFull);
  assert(api.Drain().size() == 2);
  assert(api.SetText(scene, "title", "old scene") == Status::kOk);
  assert(api.SetText(scene, std::string(129, 'x'), "too long") ==
         Status::kInvalidArgument);
  pinyon_shift::ui::SceneHandle replacement;
  assert(api.SceneReady("pause_menu", 2, &replacement) == Status::kOk);
  assert(api.Drain().empty());
  assert(api.SetText(scene, "title", "stale") == Status::kStaleScene);
  assert(api.SceneClosing(scene) == Status::kStaleScene);
  assert(api.AddMenuItem(replacement, "remove", "Remove") == Status::kOk);
  assert(api.SetText(replacement, "title", "queued") == Status::kOk);
  assert(api.RemoveComponent(replacement, "remove") == Status::kQueueFull);
  assert(api.Drain().size() == 2);
  assert(api.RemoveComponent(replacement, "remove") == Status::kOk);
  assert(api.SceneClosing(replacement) == Status::kOk);
  assert(api.Drain().empty());
  assert(api.SetText(replacement, "title", "closed") == Status::kStaleScene);
  assert(api.SceneReady("pause_menu", 1, &scene) == Status::kStaleScene);
  assert(api.SceneReady("pause_menu", 2, &scene) == Status::kStaleScene);
  assert(api.SceneReady("pause_menu", 3, &scene) == Status::kOk);
  assert(api.SetText(replacement, "title", "revived") == Status::kStaleScene);
  assert(api.AddMenuItem(scene, "remove", "fresh scene") == Status::kOk);
  assert(api.SceneClosing(scene) == Status::kOk);
  return 0;
}
