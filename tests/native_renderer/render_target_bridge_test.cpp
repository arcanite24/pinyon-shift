#include "native_renderer/render_target_bridge.h"

#include <cstdlib>
#include <iostream>

namespace nr = pinyon_shift::native_renderer;

namespace {

void Require(bool condition, const char *message) {
  if (!condition) {
    std::cerr << message << '\n';
    std::exit(EXIT_FAILURE);
  }
}

nr::NativeRenderTargetKey ColorTarget(uint32_t format = 10) {
  return {format, 640, 360, 1,
          nr::NativeRenderTargetUsage::kColor |
              nr::NativeRenderTargetUsage::kShaderResource};
}

nr::NativeResolveRegion ResolveRegion(uint32_t address = 0x11200000) {
  const auto destination =
      nr::PhysicalRange::FromGraphicsAddress(address, 640 * 360 * 4);
  Require(destination.has_value(), "resolve destination must be valid");
  return {*destination, 0, 0, 640, 360, 640 * 4, 0, 0};
}

nr::NativeProducerRequest ProducerRequest(uint32_t format = 10,
                                          uint32_t address = 0x11200000) {
  const auto source =
      nr::PhysicalRange::FromGraphicsAddress(address, 640 * 360 * 4);
  Require(source.has_value(), "producer request must be valid");
  return {*source, format, 640, 360};
}

}  // namespace

int main() {
  const nr::NativeRenderTargetKey color = ColorTarget();
  Require(color.valid(), "exact color target key must be valid");
  Require(!nr::NativeRenderTargetKey{10, 640, 360, 1,
                                     nr::NativeRenderTargetUsage::kColor |
                                         nr::NativeRenderTargetUsage::kDepth}
               .valid(),
          "a target cannot be both color and depth");

  nr::NativeRenderTargetBridge exact_pool;
  const auto exact_first =
      exact_pool.Acquire(color, 91, 4 * 1024 * 1024, 1, 1, 0);
  Require(exact_first && !exact_first->hit && exact_pool.Release(91, 1),
          "the exact-key probe must check in its first allocation");
  const auto exact_format_miss =
      exact_pool.Acquire(ColorTarget(11), 92, 4 * 1024 * 1024, 2, 2, 1);
  Require(exact_format_miss && !exact_format_miss->hit &&
              exact_format_miss->handle == 92,
          "a host-format change must not reuse an incompatible target");
  nr::NativeRenderTargetKey multisampled = color;
  multisampled.sample_count = 4;
  const auto exact_sample_miss =
      exact_pool.Acquire(multisampled, 93, 4 * 1024 * 1024, 3, 3, 2);
  Require(exact_sample_miss && !exact_sample_miss->hit &&
              exact_sample_miss->handle == 93,
          "a sample-count change must not reuse an incompatible target");
  Require(!exact_pool.PublishResolve(93, ResolveRegion(), 3),
          "a multisampled producer must resolve before publication");
  Require(exact_pool.RetireAll(3) == 3 && exact_pool.Collect(3).size() == 3,
          "the exact-key probe must retire all allocations safely");

  nr::NativeRenderTargetBridge bridge;

  const auto first = bridge.Acquire(color, 101, 4 * 1024 * 1024, 1, 10, 9);
  Require(first && !first->hit && first->handle == 101,
          "a cold target must consume the candidate allocation");
  Require(bridge.PublishResolve(101, ResolveRegion(), 10),
          "a checked-out shader-readable target must publish its resolve");
  Require(bridge.Release(101, 10),
          "the producer target must check into the pool");

  const auto producer = bridge.LookupProducer(ProducerRequest(), 2, 11);
  Require(producer.state == nr::NativeProducerLookupState::kNativeProducer &&
              producer.handle == 101 && producer.producer_submission == 10,
          "an exact fetch must receive the native producer");
  Require(bridge.LookupProducer(ProducerRequest(11), 2, 11).state ==
              nr::NativeProducerLookupState::kBridgeRequired,
          "format mismatch must refuse guest decode for a GPU output");

  const auto second = bridge.Acquire(color, 102, 4 * 1024 * 1024, 3, 12, 11);
  Require(second && !second->hit && second->handle == 102,
          "a mapped producer must remain pinned instead of being reused");
  Require(bridge.PublishResolve(102, ResolveRegion(), 12),
          "a newer resolve must supersede the previous producer");
  Require(bridge.Release(102, 12), "the replacement target must check in");

  const auto reused = bridge.Acquire(color, 103, 4 * 1024 * 1024, 4, 13, 11);
  Require(reused && reused->hit && reused->handle == 101,
          "an unpinned target must be reused after its final submission");

  const auto write = nr::PhysicalRange::FromGraphicsAddress(0xB1200080, 64);
  Require(write.has_value() && bridge.InvalidateGuestWrite(*write, 14) == 1,
          "an aliased guest write must invalidate overlapping provenance");
  Require(bridge.LookupProducer(ProducerRequest(), 5, 14).state ==
              nr::NativeProducerLookupState::kGuestDecodeAllowed,
          "guest-written content may return to the decode path");

  const auto after_write =
      bridge.Acquire(color, 104, 4 * 1024 * 1024, 6, 15, 14);
  Require(after_write && after_write->hit && after_write->handle == 102,
          "guest invalidation must unpin the superseded producer");
  Require(bridge.PublishResolve(after_write->handle, ResolveRegion(), 15) &&
              bridge.Release(after_write->handle, 15),
          "the recycled target must publish a new producer");
  Require(bridge.Retire(after_write->handle, 16),
          "retiring a mapped target must remove it from the live pool");
  Require(bridge.LookupProducer(ProducerRequest(), 7, 16).state ==
              nr::NativeProducerLookupState::kBridgeRequired,
          "a known GPU output with a retired producer must refuse decode");
  Require(bridge.Collect(15).empty(),
          "retired producer must remain alive through its final submission");
  const auto collected = bridge.Collect(16);
  Require(collected.size() == 1 && collected[0].handle == 102,
          "retired producer must collect at the fence-safe submission");

  Require(bridge.Release(101, 17),
          "the independently reused target must check in before shutdown");
  Require(bridge.RetireAll(17) == 1,
          "shutdown must retire the remaining pooled target");
  Require(bridge.Collect(16).empty(),
          "shutdown retirement must also honor its submission fence");
  Require(bridge.Collect(17).size() == 1,
          "shutdown target must collect once the fence completes");

  const nr::RenderTargetBridgeMetrics metrics = bridge.metrics();
  Require(metrics.pool_hits == 2 && metrics.pool_misses == 2 &&
              metrics.bridge_hits == 1 && metrics.bridge_refusals == 2 &&
              metrics.resolve_publications == 3 &&
              metrics.guest_invalidations == 1 && !metrics.live_count &&
              !metrics.live_bytes && !metrics.retired_count &&
              !metrics.retired_bytes,
          "render-target telemetry must describe the complete lifecycle");

  std::cout << "native renderer render-target bridge tests passed\n";
  return EXIT_SUCCESS;
}
