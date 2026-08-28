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

  std::cout << "native renderer buffer cache tests passed\n";
  return EXIT_SUCCESS;
}
