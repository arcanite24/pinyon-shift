#pragma once

#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <mutex>
#include <optional>
#include <stop_token>
#include <thread>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace pinyon_shift::native_renderer {

enum class NativeResourceWorkClass : uint8_t {
  kTexture,
  kBuffer,
  kPipeline,
};

enum class NativeResourceWorkPriority : uint8_t {
  kVisibleMiss,
  kLoadingPrewarm,
  kStreamingPrewarm,
  kSpeculative,
};

struct NativeResourceWorkKey {
  NativeResourceWorkClass resource_class = NativeResourceWorkClass::kTexture;
  uint64_t identity = 0;
  uint64_t generation = 0;

  [[nodiscard]] bool valid() const { return identity != 0; }
  bool operator==(const NativeResourceWorkKey&) const = default;
};

struct NativeResourceWorkKeyHash {
  size_t operator()(const NativeResourceWorkKey& key) const;
};

struct NativeResourceWorkRequest {
  NativeResourceWorkKey key;
  NativeResourceWorkPriority priority =
      NativeResourceWorkPriority::kSpeculative;
  std::vector<uint8_t> payload;
};

struct NativePreparedResource {
  NativeResourceWorkKey key;
  NativeResourceWorkPriority priority =
      NativeResourceWorkPriority::kSpeculative;
  std::vector<uint8_t> payload;
};

struct NativeResourceWorkerLimits {
  size_t worker_count = 2;
  size_t pending_count = 256;
  uint64_t pending_bytes = 16 * 1024 * 1024;
  size_t prepared_count = 128;
  uint64_t prepared_bytes = 16 * 1024 * 1024;
  size_t state_count = 4096;
};

struct NativeResourceWorkerMetrics {
  uint64_t submissions = 0;
  uint64_t deduplications = 0;
  uint64_t pending_evictions = 0;
  uint64_t capacity_refusals = 0;
  uint64_t prepared = 0;
  uint64_t prepare_failures = 0;
  uint64_t stale_results = 0;
  uint64_t prepared_evictions = 0;
  uint64_t state_evictions = 0;
  uint64_t commits = 0;
  uint64_t pending_count = 0;
  uint64_t pending_bytes = 0;
  uint64_t prepared_count = 0;
  uint64_t prepared_bytes = 0;
  uint64_t active_workers = 0;
};

// CPU-only preparation runs on bounded worker threads. Backend object creation
// remains in DrainCommits, which must be called by the renderer thread.
class NativeResourceWorker {
 public:
  using PrepareFunction = std::function<std::optional<NativePreparedResource>(
      NativeResourceWorkRequest, std::stop_token)>;
  using CommitFunction = std::function<void(NativePreparedResource)>;

  NativeResourceWorker(NativeResourceWorkerLimits limits,
                       PrepareFunction prepare);
  ~NativeResourceWorker();

  NativeResourceWorker(const NativeResourceWorker&) = delete;
  NativeResourceWorker& operator=(const NativeResourceWorker&) = delete;

  bool Start();
  void Stop();
  bool Submit(NativeResourceWorkRequest request);

  // Returns the number of commits performed. Both item and byte budgets are
  // hard limits; zero means no work may be committed in this call. The commit
  // callback runs while generation publication is serialized and must not
  // call back into this worker.
  size_t DrainCommits(size_t maximum_items, uint64_t maximum_bytes,
                      const CommitFunction& commit);

  [[nodiscard]] NativeResourceWorkerMetrics metrics() const;

 private:
  struct LogicalKey {
    NativeResourceWorkClass resource_class =
        NativeResourceWorkClass::kTexture;
    uint64_t identity = 0;

    bool operator==(const LogicalKey&) const = default;
  };

  struct LogicalKeyHash {
    size_t operator()(const LogicalKey& key) const;
  };

  struct QueuedRequest {
    NativeResourceWorkRequest request;
    uint64_t sequence = 0;
  };

  struct QueuedPrepared {
    NativePreparedResource resource;
    uint64_t sequence = 0;
  };

  void WorkerMain(std::stop_token stop_token);
  [[nodiscard]] size_t SelectPendingLocked() const;
  [[nodiscard]] size_t SelectPreparedLocked() const;
  [[nodiscard]] size_t SelectWorstPendingLocked() const;
  [[nodiscard]] size_t SelectWorstPreparedLocked() const;
  [[nodiscard]] bool IsCurrentLocked(const NativeResourceWorkKey& key) const;
  void RemoveOutstandingLocked(const NativeResourceWorkKey& key);

  NativeResourceWorkerLimits limits_;
  PrepareFunction prepare_;
  mutable std::mutex mutex_;
  std::condition_variable_any wake_;
  std::vector<std::jthread> workers_;
  std::vector<QueuedRequest> pending_;
  std::vector<QueuedPrepared> prepared_;
  std::unordered_set<NativeResourceWorkKey, NativeResourceWorkKeyHash>
      outstanding_;
  std::unordered_map<LogicalKey, uint64_t, LogicalKeyHash> latest_generation_;
  std::unordered_map<LogicalKey, uint64_t, LogicalKeyHash> committed_generation_;
  std::unordered_map<LogicalKey, uint64_t, LogicalKeyHash> state_touch_;
  NativeResourceWorkerMetrics metrics_;
  uint64_t next_sequence_ = 1;
  bool started_ = false;
  bool stopping_ = false;
};

}  // namespace pinyon_shift::native_renderer
