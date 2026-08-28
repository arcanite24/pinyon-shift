#include <cstdlib>
#include <iostream>

#include "native_renderer/buffer_cache.h"

namespace nr = pinyon_shift::native_renderer;

namespace {

void Require(bool condition, const char* message) {
  if (!condition) {
    std::cerr << message << '\n';
    std::exit(EXIT_FAILURE);
  }
}

nr::BufferResourceKey MakeKey(nr::PhysicalResourceTracker& tracker, uint32_t address,
                              nr::BufferResourceClass resource_class) {
  const auto range = nr::PhysicalRange::FromGraphicsAddress(address, 4096);
  Require(range.has_value(), "test range must be valid");
  return {*range, resource_class, 0x1234, tracker.Capture(*range)};
}

}  // namespace

int main() {
  nr::PhysicalResourceTracker tracker;
  nr::NativeBufferCache cache(tracker);
  const nr::BufferResourceKey vertex =
      MakeKey(tracker, 0xA0100000, nr::BufferResourceClass::kVertex);

  const auto inserted = cache.Acquire(vertex, 101, 8192, 4, 10);
  Require(inserted && !inserted->hit && inserted->entry.handle == 101,
          "first acquire must insert the candidate allocation");
  const auto hit = cache.Acquire(vertex, 202, 8192, 5, 12);
  Require(hit && hit->hit && hit->entry.handle == 101,
          "same key must reuse the existing allocation");
  Require(cache.Find(vertex, 6, 13)->last_use_submission == 13,
          "cache hits must advance the final-use submission");
  Require(!cache.Acquire(vertex, 0, 8192, 0, 0), "zero backend handles must be rejected");

  const auto write = nr::PhysicalRange::FromGraphicsAddress(0x80100080, 16);
  Require(write.has_value(), "aliased write must canonicalize");
  const auto invalidations = tracker.Invalidate(*write);
  Require(cache.RetireInvalidated(invalidations, 11) == 1,
          "overlapping writes must retire the live buffer");
  Require(!cache.Find(vertex, 7, 14), "retired buffers must leave lookup immediately");
  Require(cache.Collect(12).empty(), "in-flight buffers must survive incomplete submissions");
  const auto collected = cache.Collect(13);
  Require(collected.size() == 1 && collected.front().handle == 101,
          "buffers must become destroyable at their final submission");

  const nr::BufferResourceKey rewritten =
      MakeKey(tracker, 0x00100000, nr::BufferResourceClass::kVertex);
  Require(rewritten != vertex, "an in-place write must force a generation-aware cache miss");
  Require(cache.Acquire(rewritten, 303, 4096, 8, 20).has_value(),
          "rewritten content must accept a replacement allocation");
  const nr::BufferResourceKey index = MakeKey(tracker, 0x00102000, nr::BufferResourceClass::kIndex);
  Require(cache.Acquire(index, 404, 2048, 8, 21).has_value(),
          "independent index buffers must be cacheable");
  Require(cache.RetireAll(25) == 2, "shutdown must retire every live allocation");
  Require(cache.Collect(24).empty(), "shutdown retirement must also respect the fence");
  Require(cache.Collect(25).size() == 2, "shutdown allocations must collect after completion");

  const nr::BufferCacheMetrics metrics = cache.metrics();
  Require(metrics.hits == 2 && metrics.misses == 4, "hit and miss telemetry must be deterministic");
  Require(metrics.invalidations == 1 && !metrics.live_count && !metrics.live_bytes &&
              !metrics.retired_count && !metrics.retired_bytes,
          "lifetime telemetry must return to zero after collection");

  nr::PhysicalResourceTracker budget_tracker;
  nr::NativeBufferCache budget_cache(
      budget_tracker,
      {.maximum_live_bytes = 8192,
       .maximum_live_count = 2,
       .maximum_state_count = 2,
       .maximum_evictions_per_maintenance = 1,
       .normal_idle_frames = 10,
       .pressure_idle_frames = 3});
  const auto budget_a =
      MakeKey(budget_tracker, 0x00110000, nr::BufferResourceClass::kVertex);
  const auto budget_b =
      MakeKey(budget_tracker, 0x00112000, nr::BufferResourceClass::kVertex);
  const auto budget_c =
      MakeKey(budget_tracker, 0x00114000, nr::BufferResourceClass::kIndex);
  Require(budget_cache.Acquire(budget_a, 601, 4096, 1, 1).has_value() &&
              budget_cache.Acquire(budget_b, 602, 4096, 2, 2).has_value(),
          "resources within byte and count limits must be admitted");
  Require(budget_cache.Acquire(budget_c, 603, 4096, 5, 3).has_value(),
          "pressure admission must evict one sufficiently idle resource");
  Require(!budget_cache.Find(budget_a, 5, 3) &&
              budget_cache.Find(budget_b, 5, 3).has_value(),
          "pressure eviction must select the least-recently-used resource");
  Require(budget_cache.Collect(2).empty() &&
              budget_cache.Collect(3).size() == 1,
          "budget eviction must remain fence-safe");
  Require(budget_cache.Trim(12, 4, false) == 0,
          "normal maintenance must preserve resources inside the long guard");
  Require(budget_cache.Trim(15, 5, false) == 1,
          "normal maintenance must amortize idle eviction to one batch");

  nr::PhysicalResourceTracker refusal_tracker;
  nr::NativeBufferCache refusal_cache(
      refusal_tracker,
      {.maximum_live_bytes = 4096,
       .maximum_live_count = 1,
       .maximum_state_count = 1,
       .maximum_evictions_per_maintenance = 1,
       .normal_idle_frames = 10,
       .pressure_idle_frames = 5});
  const auto recent_a =
      MakeKey(refusal_tracker, 0x00120000, nr::BufferResourceClass::kVertex);
  const auto recent_b =
      MakeKey(refusal_tracker, 0x00122000, nr::BufferResourceClass::kVertex);
  Require(refusal_cache.Acquire(recent_a, 701, 4096, 10, 10).has_value() &&
              !refusal_cache.Acquire(recent_b, 702, 4096, 11, 11),
          "a recent resource must not be evicted merely to exceed the budget");
  Require(refusal_cache.metrics().budget_refusals == 1,
          "strict admission refusal must be observable");

  std::cout << "native renderer buffer cache tests passed\n";
  return EXIT_SUCCESS;
}
