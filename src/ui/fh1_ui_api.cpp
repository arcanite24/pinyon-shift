#include "ui/fh1_ui_api.h"

#include <algorithm>
#include <utility>

namespace pinyon_shift::ui {

namespace {
constexpr size_t kMaximumIdLength = 128;
constexpr size_t kMaximumTextLength = 512;
}  // namespace

Api::Api(size_t queue_capacity) : queue_capacity_(queue_capacity) {}

Status Api::ValidateSceneLocked(const SceneHandle& handle) const {
  if (handle.id.empty() || handle.generation == 0) {
    return Status::kInvalidArgument;
  }
  const auto scene = std::find_if(
      scenes_.begin(), scenes_.end(), [&](const SceneState& state) {
        return state.handle.id == handle.id;
      });
  if (scene == scenes_.end() || !scene->active ||
      scene->handle.generation != handle.generation) {
    return Status::kStaleScene;
  }
  return Status::kOk;
}

Status Api::EnqueueLocked(Operation operation) {
  if (pending_.size() >= queue_capacity_) {
    return Status::kQueueFull;
  }
  pending_.push_back(std::move(operation));
  return Status::kOk;
}

Status Api::SceneReady(std::string_view scene_id, uint64_t generation,
                       SceneHandle* handle) {
  if (handle == nullptr || scene_id.empty() ||
      scene_id.size() > kMaximumIdLength || generation == 0) {
    return Status::kInvalidArgument;
  }
  std::lock_guard lock(mutex_);
  const auto existing = std::find_if(
      scenes_.begin(), scenes_.end(), [&](const SceneState& state) {
        return state.handle.id == scene_id;
      });
  if (existing != scenes_.end() && generation <= existing->handle.generation) {
    return Status::kStaleScene;
  }
  if (existing != scenes_.end()) {
    const SceneHandle old_handle = existing->handle;
    pending_.erase(std::remove_if(pending_.begin(), pending_.end(),
                                  [&](const Operation& operation) {
                                    return operation.scene.id == old_handle.id &&
                                           operation.scene.generation ==
                                               old_handle.generation;
                                  }),
                   pending_.end());
    scenes_.erase(existing);
  }
  scenes_.push_back(SceneState{SceneHandle{std::string(scene_id), generation},
                               {}});
  *handle = scenes_.back().handle;
  return Status::kOk;
}

Status Api::SceneClosing(const SceneHandle& handle) {
  std::lock_guard lock(mutex_);
  if (const Status status = ValidateSceneLocked(handle); status != Status::kOk) {
    return status;
  }
  const auto scene = std::find_if(
      scenes_.begin(), scenes_.end(), [&](const SceneState& state) {
        return state.handle.id == handle.id;
      });
  // Retain the last generation so a later open cannot resurrect old handles.
  scene->active = false;
  scene->component_ids.clear();
  pending_.erase(std::remove_if(pending_.begin(), pending_.end(),
                                [&](const Operation& operation) {
                                  return operation.scene.id == handle.id &&
                                         operation.scene.generation ==
                                             handle.generation;
                                }),
                 pending_.end());
  return Status::kOk;
}

Status Api::SetText(const SceneHandle& handle, std::string_view component_id,
                    std::string_view text) {
  if (component_id.empty() || component_id.size() > kMaximumIdLength ||
      text.size() > kMaximumTextLength) {
    return Status::kInvalidArgument;
  }
  std::lock_guard lock(mutex_);
  if (const Status status = ValidateSceneLocked(handle); status != Status::kOk) {
    return status;
  }
  return EnqueueLocked(Operation{Operation::Kind::kSetText, handle,
                                 std::string(component_id), std::string(text)});
}

Status Api::SetVisible(const SceneHandle& handle, std::string_view component_id,
                       bool visible) {
  if (component_id.empty() || component_id.size() > kMaximumIdLength) {
    return Status::kInvalidArgument;
  }
  std::lock_guard lock(mutex_);
  if (const Status status = ValidateSceneLocked(handle); status != Status::kOk) {
    return status;
  }
  Operation operation{Operation::Kind::kSetVisible, handle,
                      std::string(component_id)};
  operation.visible = visible;
  return EnqueueLocked(std::move(operation));
}

Status Api::AddMenuItem(const SceneHandle& handle, std::string_view component_id,
                        std::string_view label, int32_t insertion_index) {
  if (component_id.empty() || component_id.size() > kMaximumIdLength ||
      label.empty() || label.size() > kMaximumTextLength ||
      insertion_index < -1) {
    return Status::kInvalidArgument;
  }
  std::lock_guard lock(mutex_);
  if (const Status status = ValidateSceneLocked(handle); status != Status::kOk) {
    return status;
  }
  const auto scene = std::find_if(
      scenes_.begin(), scenes_.end(), [&](const SceneState& state) {
        return state.handle.id == handle.id;
      });
  if (!scene->component_ids.insert(std::string(component_id)).second) {
    return Status::kDuplicateId;
  }
  Operation operation{Operation::Kind::kAddMenuItem, handle,
                      std::string(component_id), std::string(label),
                      ComponentKind::kMenuItem, insertion_index};
  const Status status = EnqueueLocked(std::move(operation));
  if (status != Status::kOk) {
    scene->component_ids.erase(std::string(component_id));
  }
  return status;
}

Status Api::RemoveComponent(const SceneHandle& handle,
                            std::string_view component_id) {
  if (component_id.empty() || component_id.size() > kMaximumIdLength) {
    return Status::kInvalidArgument;
  }
  std::lock_guard lock(mutex_);
  if (const Status status = ValidateSceneLocked(handle); status != Status::kOk) {
    return status;
  }
  const auto scene = std::find_if(
      scenes_.begin(), scenes_.end(), [&](const SceneState& state) {
        return state.handle.id == handle.id;
      });
  if (scene->component_ids.erase(std::string(component_id)) == 0) {
    return Status::kMissingComponent;
  }
  const Status status = EnqueueLocked(Operation{Operation::Kind::kRemoveComponent,
                                                handle,
                                                std::string(component_id)});
  if (status != Status::kOk) {
    scene->component_ids.insert(std::string(component_id));
  }
  return status;
}

std::vector<Operation> Api::Drain() {
  std::lock_guard lock(mutex_);
  std::vector<Operation> operations;
  operations.swap(pending_);
  return operations;
}

}  // namespace pinyon_shift::ui
