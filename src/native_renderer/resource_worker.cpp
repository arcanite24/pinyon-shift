#include "native_renderer/resource_worker.h"

#include <algorithm>
#include <utility>

namespace pinyon_shift::native_renderer {
namespace {

template <typename T>
void HashValue(T value, size_t& hash) {
  hash ^= std::hash<T>{}(value) + size_t{0x9E3779B9} + (hash << 6) +
          (hash >> 2);
}

uint8_t PriorityValue(NativeResourceWorkPriority priority) {
  return static_cast<uint8_t>(priority);
}

}  // namespace

size_t NativeResourceWorkKeyHash::operator()(
    const NativeResourceWorkKey& key) const {
  size_t hash = 0;
  HashValue(static_cast<uint8_t>(key.resource_class), hash);
  HashValue(key.identity, hash);
  HashValue(key.generation, hash);
  return hash;
}

size_t NativeResourceWorker::LogicalKeyHash::operator()(
    const LogicalKey& key) const {
  size_t hash = 0;
  HashValue(static_cast<uint8_t>(key.resource_class), hash);
  HashValue(key.identity, hash);
  return hash;
}

NativeResourceWorker::NativeResourceWorker(NativeResourceWorkerLimits limits,
                                           PrepareFunction prepare)
    : limits_(limits), prepare_(std::move(prepare)) {}

NativeResourceWorker::~NativeResourceWorker() { Stop(); }

bool NativeResourceWorker::Start() {
  const std::scoped_lock lock(mutex_);
  if (started_ || stopping_ || !prepare_ || !limits_.worker_count) {
    return false;
  }
  started_ = true;
  workers_.reserve(limits_.worker_count);
  for (size_t worker_index = 0; worker_index < limits_.worker_count;
       ++worker_index) {
    workers_.emplace_back(
        [this](std::stop_token stop_token) { WorkerMain(stop_token); });
  }
  wake_.notify_all();
  return true;
}

void NativeResourceWorker::Stop() {
  std::vector<std::jthread> workers;
  {
    const std::scoped_lock lock(mutex_);
    if (stopping_) {
      return;
    }
    stopping_ = true;
    workers.swap(workers_);
  }
  for (auto& worker : workers) {
    worker.request_stop();
  }
  wake_.notify_all();
  workers.clear();
  const std::scoped_lock lock(mutex_);
  for (const auto& queued : pending_) {
    RemoveOutstandingLocked(queued.request.key);
  }
  for (const auto& queued : prepared_) {
    RemoveOutstandingLocked(queued.resource.key);
  }
  pending_.clear();
  prepared_.clear();
  metrics_.pending_count = 0;
  metrics_.pending_bytes = 0;
  metrics_.prepared_count = 0;
  metrics_.prepared_bytes = 0;
  started_ = false;
}

bool NativeResourceWorker::Submit(NativeResourceWorkRequest request) {
  if (!request.key.valid()) {
    return false;
  }
  const uint64_t request_bytes = request.payload.size();
  const LogicalKey logical{request.key.resource_class, request.key.identity};
  const std::scoped_lock lock(mutex_);
  if (stopping_ || request_bytes > limits_.pending_bytes) {
    ++metrics_.capacity_refusals;
    return false;
  }
  const auto latest = latest_generation_.find(logical);
  if (latest != latest_generation_.end() &&
      request.key.generation < latest->second) {
    ++metrics_.stale_results;
    return false;
  }
  const auto committed = committed_generation_.find(logical);
  if ((committed != committed_generation_.end() &&
       request.key.generation <= committed->second) ||
      outstanding_.contains(request.key)) {
    state_touch_[logical] = next_sequence_++;
    ++metrics_.deduplications;
    return true;
  }
  if (latest == latest_generation_.end()) {
    while (latest_generation_.size() >= limits_.state_count) {
      auto oldest = state_touch_.end();
      for (auto candidate = state_touch_.begin();
           candidate != state_touch_.end(); ++candidate) {
        const bool outstanding = std::ranges::any_of(
            outstanding_, [&](const NativeResourceWorkKey& key) {
              return key.resource_class == candidate->first.resource_class &&
                     key.identity == candidate->first.identity;
            });
        if (!outstanding &&
            (oldest == state_touch_.end() ||
             candidate->second < oldest->second)) {
          oldest = candidate;
        }
      }
      if (oldest == state_touch_.end()) {
        ++metrics_.capacity_refusals;
        return false;
      }
      const LogicalKey oldest_key = oldest->first;
      state_touch_.erase(oldest);
      committed_generation_.erase(oldest_key);
      latest_generation_.erase(oldest_key);
      ++metrics_.state_evictions;
    }
  }
  latest_generation_[logical] = request.key.generation;
  state_touch_[logical] = next_sequence_;
  for (size_t index = pending_.size(); index-- > 0;) {
    const auto& pending_key = pending_[index].request.key;
    if (pending_key.resource_class != logical.resource_class ||
        pending_key.identity != logical.identity ||
        pending_key.generation >= request.key.generation) {
      continue;
    }
    metrics_.pending_bytes -= pending_[index].request.payload.size();
    RemoveOutstandingLocked(pending_key);
    pending_.erase(pending_.begin() + index);
    ++metrics_.stale_results;
  }
  metrics_.pending_count = pending_.size();
  for (size_t index = prepared_.size(); index-- > 0;) {
    const auto& prepared_key = prepared_[index].resource.key;
    if (prepared_key.resource_class != logical.resource_class ||
        prepared_key.identity != logical.identity ||
        prepared_key.generation >= request.key.generation) {
      continue;
    }
    metrics_.prepared_bytes -= prepared_[index].resource.payload.size();
    RemoveOutstandingLocked(prepared_key);
    prepared_.erase(prepared_.begin() + index);
    ++metrics_.stale_results;
  }
  metrics_.prepared_count = prepared_.size();

  while (pending_.size() >= limits_.pending_count ||
         metrics_.pending_bytes > limits_.pending_bytes - request_bytes) {
    if (pending_.empty()) {
      ++metrics_.capacity_refusals;
      return false;
    }
    const size_t worst_index = SelectWorstPendingLocked();
    if (PriorityValue(pending_[worst_index].request.priority) <=
        PriorityValue(request.priority)) {
      ++metrics_.capacity_refusals;
      return false;
    }
    metrics_.pending_bytes -= pending_[worst_index].request.payload.size();
    RemoveOutstandingLocked(pending_[worst_index].request.key);
    pending_.erase(pending_.begin() + worst_index);
    ++metrics_.pending_evictions;
  }
  outstanding_.insert(request.key);
  metrics_.pending_bytes += request_bytes;
  pending_.push_back({std::move(request), next_sequence_++});
  ++metrics_.submissions;
  metrics_.pending_count = pending_.size();
  wake_.notify_one();
  return true;
}

size_t NativeResourceWorker::DrainCommits(
    size_t maximum_items, uint64_t maximum_bytes,
    const CommitFunction& commit) {
  if (!maximum_items || !maximum_bytes || !commit) {
    return 0;
  }
  size_t committed_count = 0;
  uint64_t committed_bytes = 0;
  while (committed_count < maximum_items) {
    const std::scoped_lock lock(mutex_);
    if (prepared_.empty()) {
      break;
    }
    const size_t prepared_index = SelectPreparedLocked();
    const uint64_t resource_bytes =
        prepared_[prepared_index].resource.payload.size();
    if (resource_bytes > maximum_bytes - committed_bytes) {
      break;
    }
    NativePreparedResource resource =
        std::move(prepared_[prepared_index].resource);
    prepared_.erase(prepared_.begin() + prepared_index);
    metrics_.prepared_bytes -= resource_bytes;
    metrics_.prepared_count = prepared_.size();
    RemoveOutstandingLocked(resource.key);
    if (!IsCurrentLocked(resource.key)) {
      ++metrics_.stale_results;
      continue;
    }
    const NativeResourceWorkKey committed_key = resource.key;
    commit(std::move(resource));
    const LogicalKey logical{committed_key.resource_class,
                             committed_key.identity};
    committed_generation_[logical] = committed_key.generation;
    state_touch_[logical] = next_sequence_++;
    ++metrics_.commits;
    committed_bytes += resource_bytes;
    ++committed_count;
  }
  return committed_count;
}

NativeResourceWorkerMetrics NativeResourceWorker::metrics() const {
  const std::scoped_lock lock(mutex_);
  return metrics_;
}

void NativeResourceWorker::WorkerMain(std::stop_token stop_token) {
  while (!stop_token.stop_requested()) {
    QueuedRequest queued;
    {
      std::unique_lock lock(mutex_);
      wake_.wait(lock, stop_token,
                 [&] { return !pending_.empty() || stopping_; });
      if (stop_token.stop_requested() || stopping_) {
        return;
      }
      const size_t pending_index = SelectPendingLocked();
      queued = std::move(pending_[pending_index]);
      metrics_.pending_bytes -= queued.request.payload.size();
      pending_.erase(pending_.begin() + pending_index);
      metrics_.pending_count = pending_.size();
      ++metrics_.active_workers;
    }

    const NativeResourceWorkKey work_key = queued.request.key;
    std::optional<NativePreparedResource> result =
        prepare_(std::move(queued.request), stop_token);
    {
      const std::scoped_lock lock(mutex_);
      --metrics_.active_workers;
      if (!result || result->key != work_key) {
        RemoveOutstandingLocked(work_key);
        if (IsCurrentLocked(work_key)) {
          committed_generation_[{work_key.resource_class,
                                 work_key.identity}] = work_key.generation;
          state_touch_[{work_key.resource_class, work_key.identity}] =
              next_sequence_++;
        }
        ++metrics_.prepare_failures;
        continue;
      }
      if (!IsCurrentLocked(result->key)) {
        RemoveOutstandingLocked(result->key);
        ++metrics_.stale_results;
        continue;
      }
      const uint64_t result_bytes = result->payload.size();
      if (result_bytes > limits_.prepared_bytes) {
        RemoveOutstandingLocked(result->key);
        ++metrics_.capacity_refusals;
        continue;
      }
      while (prepared_.size() >= limits_.prepared_count ||
             metrics_.prepared_bytes > limits_.prepared_bytes - result_bytes) {
        if (prepared_.empty()) {
          break;
        }
        const size_t worst_index = SelectWorstPreparedLocked();
        if (PriorityValue(prepared_[worst_index].resource.priority) <=
            PriorityValue(result->priority)) {
          break;
        }
        metrics_.prepared_bytes -=
            prepared_[worst_index].resource.payload.size();
        RemoveOutstandingLocked(prepared_[worst_index].resource.key);
        prepared_.erase(prepared_.begin() + worst_index);
        ++metrics_.prepared_evictions;
      }
      if (prepared_.size() >= limits_.prepared_count ||
          metrics_.prepared_bytes > limits_.prepared_bytes - result_bytes) {
        RemoveOutstandingLocked(result->key);
        ++metrics_.capacity_refusals;
        continue;
      }
      metrics_.prepared_bytes += result_bytes;
      prepared_.push_back({std::move(*result), queued.sequence});
      ++metrics_.prepared;
      metrics_.prepared_count = prepared_.size();
    }
  }
}

size_t NativeResourceWorker::SelectPendingLocked() const {
  size_t selected = 0;
  for (size_t index = 1; index < pending_.size(); ++index) {
    if (PriorityValue(pending_[index].request.priority) <
            PriorityValue(pending_[selected].request.priority) ||
        (pending_[index].request.priority ==
             pending_[selected].request.priority &&
         pending_[index].sequence < pending_[selected].sequence)) {
      selected = index;
    }
  }
  return selected;
}

size_t NativeResourceWorker::SelectPreparedLocked() const {
  size_t selected = 0;
  for (size_t index = 1; index < prepared_.size(); ++index) {
    if (PriorityValue(prepared_[index].resource.priority) <
            PriorityValue(prepared_[selected].resource.priority) ||
        (prepared_[index].resource.priority ==
             prepared_[selected].resource.priority &&
         prepared_[index].sequence < prepared_[selected].sequence)) {
      selected = index;
    }
  }
  return selected;
}

size_t NativeResourceWorker::SelectWorstPendingLocked() const {
  size_t selected = 0;
  for (size_t index = 1; index < pending_.size(); ++index) {
    if (PriorityValue(pending_[index].request.priority) >
            PriorityValue(pending_[selected].request.priority) ||
        (pending_[index].request.priority ==
             pending_[selected].request.priority &&
         pending_[index].sequence > pending_[selected].sequence)) {
      selected = index;
    }
  }
  return selected;
}

size_t NativeResourceWorker::SelectWorstPreparedLocked() const {
  size_t selected = 0;
  for (size_t index = 1; index < prepared_.size(); ++index) {
    if (PriorityValue(prepared_[index].resource.priority) >
            PriorityValue(prepared_[selected].resource.priority) ||
        (prepared_[index].resource.priority ==
             prepared_[selected].resource.priority &&
         prepared_[index].sequence > prepared_[selected].sequence)) {
      selected = index;
    }
  }
  return selected;
}

bool NativeResourceWorker::IsCurrentLocked(
    const NativeResourceWorkKey& key) const {
  const auto latest = latest_generation_.find(
      {key.resource_class, key.identity});
  return latest != latest_generation_.end() &&
         latest->second == key.generation;
}

void NativeResourceWorker::RemoveOutstandingLocked(
    const NativeResourceWorkKey& key) {
  outstanding_.erase(key);
}

}  // namespace pinyon_shift::native_renderer
