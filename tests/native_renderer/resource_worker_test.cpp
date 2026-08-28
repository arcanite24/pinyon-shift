#include <atomic>
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <thread>
#include <vector>

#include "native_renderer/resource_worker.h"

namespace nr = pinyon_shift::native_renderer;

namespace {

void Require(bool condition, const char* message) {
  if (!condition) {
    std::cerr << message << '\n';
    std::exit(EXIT_FAILURE);
  }
}

nr::NativeResourceWorkRequest Request(
    uint64_t identity, uint64_t generation,
    nr::NativeResourceWorkPriority priority, uint8_t payload = 1) {
  return {{nr::NativeResourceWorkClass::kTexture, identity, generation},
          priority,
          {payload}};
}

bool WaitForPrepared(nr::NativeResourceWorker& worker, uint64_t count) {
  const auto deadline =
      std::chrono::steady_clock::now() + std::chrono::seconds(3);
  while (std::chrono::steady_clock::now() < deadline) {
    if (worker.metrics().prepared_count >= count) {
      return true;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(2));
  }
  return false;
}

}  // namespace

int main() {
  using Priority = nr::NativeResourceWorkPriority;
  nr::NativeResourceWorkerLimits limits;
  limits.worker_count = 1;
  limits.pending_count = 2;
  limits.pending_bytes = 8;
  limits.prepared_count = 2;
  limits.prepared_bytes = 8;

  nr::NativeResourceWorker worker(
      limits, [](nr::NativeResourceWorkRequest request, std::stop_token) {
        return std::optional<nr::NativePreparedResource>{{
            request.key, request.priority, std::move(request.payload)}};
      });
  Require(worker.Submit(Request(1, 1, Priority::kSpeculative)),
          "the first speculative request must queue");
  Require(worker.Submit(Request(2, 1, Priority::kStreamingPrewarm)),
          "the second prewarm request must queue");
  Require(worker.Submit(Request(3, 1, Priority::kVisibleMiss)),
          "a visible miss must evict lower-priority pending work");
  Require(!worker.Submit(Request(4, 1, Priority::kSpeculative)),
          "low-priority work must not displace urgent requests");
  Require(worker.Start(), "the worker pool must start exactly once");
  Require(!worker.Start(), "a running worker pool must not start twice");
  Require(WaitForPrepared(worker, 2), "both retained jobs must prepare");

  std::vector<uint64_t> committed;
  Require(worker.DrainCommits(
              1, 8, [&](nr::NativePreparedResource resource) {
                committed.push_back(resource.key.identity);
              }) == 1 &&
              committed.front() == 3,
          "visible work must commit before streaming prewarm");
  Require(worker.DrainCommits(
              1, 8, [&](nr::NativePreparedResource resource) {
                committed.push_back(resource.key.identity);
              }) == 1 &&
              committed.back() == 2,
          "the remaining prewarm request must commit second");
  Require(worker.Submit(Request(3, 1, Priority::kVisibleMiss)),
          "a committed generation must deduplicate successfully");
  worker.Stop();

  const nr::NativeResourceWorkerMetrics first_metrics = worker.metrics();
  Require(first_metrics.pending_evictions == 1 &&
              first_metrics.capacity_refusals == 1 &&
              first_metrics.deduplications == 1 &&
              first_metrics.commits == 2 && !first_metrics.pending_count &&
              !first_metrics.prepared_count && !first_metrics.active_workers,
          "bounded queue telemetry must match the exercised behavior");

  std::atomic<bool> generation_one_started = false;
  std::atomic<bool> release_generation_one = false;
  nr::NativeResourceWorker stale_worker(
      limits, [&](nr::NativeResourceWorkRequest request, std::stop_token stop) {
        if (request.key.generation == 1) {
          generation_one_started.store(true);
          while (!release_generation_one.load() && !stop.stop_requested()) {
            std::this_thread::yield();
          }
        }
        return std::optional<nr::NativePreparedResource>{{
            request.key, request.priority, std::move(request.payload)}};
      });
  Require(stale_worker.Submit(Request(9, 1, Priority::kVisibleMiss)) &&
              stale_worker.Start(),
          "the first generation must start preparing");
  const auto start_deadline =
      std::chrono::steady_clock::now() + std::chrono::seconds(3);
  while (!generation_one_started.load() &&
         std::chrono::steady_clock::now() < start_deadline) {
    std::this_thread::sleep_for(std::chrono::milliseconds(2));
  }
  Require(generation_one_started.load(), "generation one must reach the worker");
  Require(stale_worker.Submit(Request(9, 2, Priority::kVisibleMiss, 2)),
          "a newer generation must queue while the old one is in flight");
  release_generation_one.store(true);
  Require(WaitForPrepared(stale_worker, 1),
          "the newest generation must become commit-ready");
  uint64_t committed_generation = 0;
  Require(stale_worker.DrainCommits(
              1, 8, [&](nr::NativePreparedResource resource) {
                committed_generation = resource.key.generation;
              }) == 1 &&
              committed_generation == 2,
          "an obsolete worker result must never reach renderer commit");
  stale_worker.Stop();
  Require(stale_worker.metrics().stale_results >= 1,
          "stale result rejection must be observable");

  limits.state_count = 2;
  nr::NativeResourceWorker state_worker(
      limits, [](nr::NativeResourceWorkRequest request, std::stop_token) {
        return std::optional<nr::NativePreparedResource>{{
            request.key, request.priority, std::move(request.payload)}};
      });
  Require(state_worker.Start(), "the bounded state worker must start");
  for (uint64_t identity = 20; identity < 23; ++identity) {
    Require(state_worker.Submit(
                Request(identity, 1, Priority::kStreamingPrewarm)),
            "bounded state work must queue");
    Require(WaitForPrepared(state_worker, 1),
            "bounded state work must prepare");
    Require(state_worker.DrainCommits(
                1, 8, [](nr::NativePreparedResource) {}) == 1,
            "bounded state work must commit");
  }
  state_worker.Stop();
  Require(state_worker.metrics().state_evictions == 1,
          "completed logical state must remain bounded by LRU eviction");

  std::cout << "native renderer resource worker tests passed\n";
  return EXIT_SUCCESS;
}
