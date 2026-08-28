#include <array>
#include <cstdlib>
#include <iostream>

#include "native_renderer/texture_cache.h"

namespace nr = pinyon_shift::native_renderer;

namespace {

void Require(bool condition, const char* message) {
  if (!condition) {
    std::cerr << message << '\n';
    std::exit(EXIT_FAILURE);
  }
}

nr::TextureResourceKey MakeKey(nr::PhysicalResourceTracker& tracker) {
  const auto base =
      nr::PhysicalRange::FromGraphicsAddress(0x94649000, 32768);
  Require(base.has_value(), "selected DXN range must be valid");
  return {*base, std::nullopt, UINT64_C(0x747837906D0BF484),
          tracker.Capture(*base)};
}

}  // namespace

int main() {
  constexpr std::array<uint32_t, 6> selected_fetch = {
      0x82024002, 0x14649071, 0x0007E0FF,
      0x00A80D10, 0x00000003, 0x00000A00};
  const auto descriptor =
      nr::NativeTextureDescriptor::FromFetchWords(selected_fetch);
  Require(descriptor && descriptor->format == nr::kXenosTextureFormatDxn &&
              descriptor->width == 256 && descriptor->height == 64 &&
              descriptor->pitch == 256 && descriptor->tiled &&
              descriptor->endianness == 1,
          "the retained-pass fetch must decode as tiled 256x64 DXN");

  nr::PhysicalResourceTracker tracker;
  nr::NativeTextureCache cache(
      tracker, {.maximum_attempts = 4,
                .base_delay_frames = 2,
                .maximum_delay_frames = 8});
  const nr::TextureResourceKey key = MakeKey(tracker);
  const auto first = cache.Request(key, 10, 1);
  Require(first.state == nr::TextureRequestState::kDecodeRequired &&
              first.attempt == 1 && !first.sampled_handle,
          "a cold miss must request decode with the neutral fallback");
  Require(cache.Complete(first.decode_ticket,
                         nr::TextureDecodeResult::kIncompletePayload,
                         0, 0, 10, 1),
          "an incomplete streaming payload must be accepted");
  Require(cache.Request(key, 11, 2).state ==
              nr::TextureRequestState::kRetryPending,
          "retry must wait for its bounded backoff");
  const auto second = cache.Request(key, 12, 3);
  Require(second.state == nr::TextureRequestState::kDecodeRequired &&
              second.attempt == 2,
          "retry must become due after two frames");
  Require(cache.Complete(second.decode_ticket,
                         nr::TextureDecodeResult::kIncompletePayload,
                         0, 0, 12, 3),
          "a second incomplete payload must remain retryable");
  Require(cache.Request(key, 15, 4).state ==
              nr::TextureRequestState::kRetryPending,
          "exponential backoff must grow to four frames");
  const auto third = cache.Request(key, 16, 5);
  Require(third.state == nr::TextureRequestState::kDecodeRequired &&
              third.attempt == 3,
          "third decode must start at the bounded due frame");
  Require(cache.Complete(third.decode_ticket, nr::TextureDecodeResult::kReady,
                         501, 65536, 16, 6),
          "a complete decode must commit its native allocation");
  const auto hit = cache.Request(key, 17, 9);
  Require(hit.state == nr::TextureRequestState::kReady &&
              hit.sampled_handle == 501,
          "committed content must produce an exact cache hit");

  nr::TextureResourceKey replacement = key;
  ++replacement.content.generation;
  ++replacement.content.fingerprint;
  const auto refresh = cache.Request(replacement, 18, 10);
  Require(refresh.state == nr::TextureRequestState::kDecodeRequired &&
              refresh.sampled_handle == 501 && refresh.serving_previous,
          "a pending refresh may serve the previous complete texture");
  Require(cache.Complete(refresh.decode_ticket, nr::TextureDecodeResult::kReady,
                         502, 65536, 18, 11),
          "a refreshed generation must atomically replace the old one");
  Require(cache.Collect(10).empty(),
          "the replaced allocation must wait for its last submission");
  Require(cache.Collect(11).size() == 1,
          "the replaced allocation must collect at its final use");

  const auto write =
      nr::PhysicalRange::FromGraphicsAddress(0xB4649020, 16);
  Require(write.has_value(), "aliased texture write must canonicalize");
  const auto invalidations = tracker.Invalidate(*write);
  Require(cache.RetireInvalidated(invalidations, *write, 12) == 1,
          "a guest write must retire the overlapping native texture");
  Require(cache.Collect(11).empty(),
          "invalidated allocations must remain live through submission 12");
  Require(cache.Collect(12).size() == 1,
          "invalidated allocations must collect after submission 12");

  nr::NativeTextureCache bounded(
      tracker, {.maximum_attempts = 2,
                .base_delay_frames = 1,
                .maximum_delay_frames = 2});
  const nr::TextureResourceKey rewritten = MakeKey(tracker);
  const auto bounded_first = bounded.Request(rewritten, 20, 20);
  Require(bounded.Complete(bounded_first.decode_ticket,
                           nr::TextureDecodeResult::kIncompletePayload,
                           0, 0, 20, 20),
          "bounded retry first failure must complete");
  const auto bounded_second = bounded.Request(rewritten, 21, 21);
  Require(bounded.Complete(bounded_second.decode_ticket,
                           nr::TextureDecodeResult::kIncompletePayload,
                           0, 0, 21, 21),
          "bounded retry final failure must complete");
  Require(bounded.Request(rewritten, 100, 22).state ==
              nr::TextureRequestState::kPermanentFailure,
          "retry exhaustion must stop rescheduling decode work");

  const nr::TextureCacheMetrics metrics = cache.metrics();
  Require(metrics.hits == 1 && metrics.misses == 2 &&
              metrics.decode_requests == 4 &&
              metrics.incomplete_payloads == 2 && metrics.retries == 2 &&
              metrics.invalidations == 1 && !metrics.live_count &&
              !metrics.live_bytes && !metrics.retired_count &&
              !metrics.retired_bytes,
          "texture cache telemetry must describe the complete lifecycle");

  std::cout << "native renderer texture cache tests passed\n";
  return EXIT_SUCCESS;
}
