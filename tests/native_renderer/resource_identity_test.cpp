#include <cstdlib>
#include <iostream>
#include <span>

#include "native_renderer/resource_identity.h"

namespace nr = pinyon_shift::native_renderer;

namespace {

void Require(bool condition, const char* message) {
  if (!condition) {
    std::cerr << message << '\n';
    std::exit(EXIT_FAILURE);
  }
}

}  // namespace

int main() {
  const auto canonical =
      nr::PhysicalRange::FromGraphicsAddress(0xA1234000, 0x2000);
  const auto already_physical =
      nr::PhysicalRange::FromGraphicsAddress(0x01234000, 0x2000);
  Require(canonical && already_physical,
          "valid aliased ranges must canonicalize");
  Require(*canonical == *already_physical,
          "physical-heap aliases must share one identity");
  Require(!nr::PhysicalRange::FromGraphicsAddress(0, 0),
          "empty resources must be rejected");
  Require(!nr::PhysicalRange::FromGraphicsAddress(0x1FFFFFF0, 0x20),
          "resources crossing the aperture must be rejected");

  const auto touching =
      nr::PhysicalRange::FromGraphicsAddress(0x01236000, 0x1000);
  const auto overlapping =
      nr::PhysicalRange::FromGraphicsAddress(0x01235FFF, 2);
  Require(touching && overlapping, "test ranges must be valid");
  Require(!canonical->Overlaps(*touching),
          "half-open ranges that only touch must not overlap");
  Require(canonical->Overlaps(*overlapping),
          "one-byte intersections must overlap");

  nr::PhysicalResourceTracker tracker;
  const auto initial = tracker.Capture(*canonical);
  const nr::TrackedResourceId vertex{nr::TrackedResourceClass::kBuffer, 7};
  const nr::TrackedResourceId texture{nr::TrackedResourceClass::kTexture, 9};
  tracker.Track(vertex, std::span<const nr::PhysicalRange>(&*canonical, 1));
  tracker.Track(texture,
                std::span<const nr::PhysicalRange>(&*touching, 1));

  const auto write =
      nr::PhysicalRange::FromGraphicsAddress(0x81234FFF, 2);
  Require(write.has_value(), "aliased write range must be valid");
  const auto invalidations = tracker.Invalidate(*write);
  Require(invalidations.size() == 1 &&
              invalidations.front().resource == vertex,
          "only overlapping resources must be invalidated");
  const auto changed = tracker.Capture(*already_physical);
  Require(changed.generation > initial.generation &&
              changed.fingerprint != initial.fingerprint,
          "a guest write must change the canonical content identity");
  Require(tracker.Capture(*touching).generation == 0,
          "adjacent content must retain its generation");

  const nr::PhysicalRange texture_ranges[] = {*canonical, *touching};
  tracker.Track(texture, texture_ranges);
  const auto both_hits = tracker.Invalidate(*overlapping);
  Require(both_hits.size() == 2,
          "one write must report each overlapping tracked resource once");
  Require(tracker.Untrack(vertex), "tracked resources must be removable");
  Require(!tracker.Untrack(vertex), "untracking must be idempotent");
  Require(tracker.Invalidate(*canonical).size() == 1,
          "untracked resources must not receive invalidations");

  const nr::BufferResourceKey vertex_key{
      *canonical, nr::BufferResourceClass::kVertex, 0x1234,
      tracker.Capture(*canonical)};
  const nr::BufferResourceKey index_key{
      *canonical, nr::BufferResourceClass::kIndex, 0x1234,
      tracker.Capture(*canonical)};
  Require(vertex_key != index_key,
          "buffer class must participate in resource identity");

  const nr::TextureResourceKey texture_key{
      *canonical, *touching, UINT64_C(0xABCDEF),
      tracker.Capture(texture_ranges)};
  Require(texture_key.base == *already_physical && texture_key.mips,
          "texture keys must preserve canonical base and mip identity");

  std::cout << "native renderer resource identity tests passed\n";
  return EXIT_SUCCESS;
}
