#pragma once

#include <cstddef>
#include <cstdint>
#include <mutex>
#include <string>
#include <string_view>
#include <unordered_set>
#include <vector>

namespace pinyon_shift::ui {

enum class Status {
  kOk,
  kInvalidArgument,
  kStaleScene,
  kDuplicateId,
  kMissingComponent,
  kQueueFull,
};

enum class ComponentKind {
  kLabel,
  kMenuItem,
  kButton,
  kToggle,
  kChoiceRow,
};

struct SceneHandle {
  std::string id;
  uint64_t generation = 0;
};

struct Operation {
  enum class Kind {
    kSetText,
    kSetVisible,
    kAddMenuItem,
    kRemoveComponent,
  };

  Kind kind;
  SceneHandle scene;
  std::string component_id;
  std::string value;
  ComponentKind component_kind = ComponentKind::kLabel;
  int32_t insertion_index = -1;
  bool visible = true;
};

class Api {
 public:
  explicit Api(size_t queue_capacity = 64);

  Status SceneReady(std::string_view scene_id, uint64_t generation,
                    SceneHandle* handle);
  Status SceneClosing(const SceneHandle& handle);

  Status SetText(const SceneHandle& handle, std::string_view component_id,
                 std::string_view text);
  Status SetVisible(const SceneHandle& handle, std::string_view component_id,
                    bool visible);
  Status AddMenuItem(const SceneHandle& handle, std::string_view component_id,
                     std::string_view label, int32_t insertion_index = -1);
  Status RemoveComponent(const SceneHandle& handle,
                         std::string_view component_id);

  std::vector<Operation> Drain();

 private:
  struct SceneState {
    SceneHandle handle;
    std::unordered_set<std::string> component_ids;
    bool active = true;
  };

  Status ValidateSceneLocked(const SceneHandle& handle) const;
  Status EnqueueLocked(Operation operation);

  size_t queue_capacity_;
  std::vector<Operation> pending_;
  std::vector<SceneState> scenes_;
  mutable std::mutex mutex_;
};

}  // namespace pinyon_shift::ui
