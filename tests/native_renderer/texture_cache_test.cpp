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

nr::TextureResourceKey MakeKey(nr::PhysicalResourceTracker& tracker,
                               uint32_t address = 0x94649000,
                               uint64_t signature =
                                   UINT64_C(0x747837906D0BF484)) {
  const auto base =
      nr::PhysicalRange::FromGraphicsAddress(address, 32768);
  Require(base.has_value(), "selected DXN range must be valid");
  return {*base, std::nullopt, signature, tracker.Capture(*base)};
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

  nr::PhysicalResourceTracker budget_tracker;
  nr::NativeTextureCache budget_cache(
      budget_tracker, {},
      {.maximum_live_bytes = 65536,
       .maximum_live_count = 1,
       .maximum_state_count = 2,
       .maximum_evictions_per_maintenance = 1,
       .normal_idle_frames = 10,
       .pressure_idle_frames = 3});
  const auto budget_a = MakeKey(budget_tracker, 0x00130000, 0xA1);
  const auto budget_b = MakeKey(budget_tracker, 0x00140000, 0xB2);
  const auto budget_c = MakeKey(budget_tracker, 0x00150000, 0xC3);
  const auto request_a = budget_cache.Request(budget_a, 1, 1);
  Require(budget_cache.Complete(request_a.decode_ticket,
                                nr::TextureDecodeResult::kReady, 601,
                                65536, 1, 1),
          "the first texture must fit the configured budget");
  const auto request_b = budget_cache.Request(budget_b, 5, 2);
  Require(budget_cache.Complete(request_b.decode_ticket,
                                nr::TextureDecodeResult::kReady, 602,
                                65536, 5, 2),
          "pressure admission must replace an idle texture");
  Require(budget_cache.Collect(1).empty() &&
              budget_cache.Collect(2).size() == 1,
          "evicted texture destruction must wait for its final submission");
  const auto request_c = budget_cache.Request(budget_c, 6, 3);
  Require(request_c.state == nr::TextureRequestState::kDecodeRequired &&
              !budget_cache.Complete(request_c.decode_ticket,
                                     nr::TextureDecodeResult::kReady, 603,
                                     65536, 6, 3),
          "a recent live texture must force strict budget refusal");
  Require(budget_cache.Request(budget_c, 7, 4).state ==
              nr::TextureRequestState::kRetryPending,
          "budget refusal must retry later instead of becoming permanent");
  Require(budget_cache.Trim(8, 4, false) == 0,
          "normal maintenance must keep textures within the long idle guard");
  Require(budget_cache.Trim(9, 5, true) == 1,
          "pressure maintenance must use the shorter idle guard");
  const auto budget_metrics = budget_cache.metrics();
  Require(budget_metrics.budget_evictions == 2 &&
              budget_metrics.budget_refusals == 1 &&
              budget_metrics.state_evictions == 2 &&
              budget_metrics.state_count <= 2,
          "texture budget, state cap, and eviction telemetry must be bounded");

  std::cout << "native renderer texture cache tests passed\n";
  return EXIT_SUCCESS;
}
