#include "native_renderer/resolve_assembly_tracker.h"

#include <cstdlib>
#include <iostream>

namespace nr = pinyon_shift::native_renderer;

namespace {

void Require(bool condition, const char* message) {
  if (!condition) {
    std::cerr << message << '\n';
    std::exit(EXIT_FAILURE);
  }
}

nr::ProceduralResolveCopy Copy(uint32_t address, uint32_t length,
                               uint64_t frame = 10) {
  return {.frame_sequence = frame,
          .source = 0,
          .source_surface_info = 0x14020500,
          .source_info = 0x00030000,
          .destination_info = 0x003E0382,
          .destination_pitch = 0x02D00500,
          .written_address = address,
          .written_length = length};
}

nr::ProceduralResolveTarget Target(uint64_t frame = 10) {
  return {.frame_sequence = frame,
          .surface_info = 0x14020500,
          .color_info = 0x00030000,
          .logical_width = 1280,
          .logical_height = 720};
}

}  // namespace

int main() {
  constexpr uint32_t kFirstLength = 1280 * 256 * 4;
  constexpr uint32_t kLastLength = 1280 * 224 * 4;
  constexpr uint32_t kBase = 0x1C4E1000;

  nr::ProceduralResolveAssemblyTracker tracker;
  Require(!tracker.Observe(Copy(kBase, kFirstLength)),
          "the current frame must remain pending");
  Require(!tracker.Arm(Target()), "arming must not finalize the same frame");
  Require(!tracker.Observe(Copy(kBase + kFirstLength, kFirstLength)),
          "the second chunk must remain pending");
  Require(!tracker.Observe(
              Copy(kBase + 2 * kFirstLength, kLastLength)),
          "the final chunk must remain pending until frame advance");
  const auto exact = tracker.Arm(Target(11));
  Require(exact && exact->exact_contiguous_full_frame &&
              exact->chunk_count == 3 && exact->logical_width == 1280 &&
              exact->logical_height == 720 && exact->padded_height == 736 &&
              exact->bytes_per_pixel == 4 &&
              exact->total_bytes == uint64_t(1280) * 736 * 4,
          "three contiguous chunks must qualify the padded full frame");
  Require(tracker.latest_qualified() &&
              tracker.latest_qualified()->frame_sequence == 10,
          "the last exact assembly must remain queryable");

  nr::ProceduralResolveAssemblyTracker gap;
  gap.Arm(Target());
  gap.Observe(Copy(kBase, kFirstLength));
  gap.Observe(Copy(kBase + kFirstLength + 0x1000, kFirstLength));
  const auto incomplete = gap.Flush();
  Require(incomplete && !incomplete->exact_contiguous_full_frame,
          "a gap must fail closed");

  nr::ProceduralResolveAssemblyTracker mismatch;
  mismatch.Arm(Target());
  auto wrong_source = Copy(kBase, kFirstLength);
  wrong_source.source_info = 0x00040000;
  mismatch.Observe(wrong_source);
  const auto rejected = mismatch.Flush();
  Require(rejected && !rejected->chunk_count,
          "a source-state mismatch must not enter the assembly");

  nr::ProceduralResolveAssemblyTracker conflicting_target;
  conflicting_target.Arm(Target());
  auto other_target = Target();
  other_target.color_info = 0x00040000;
  conflicting_target.Arm(other_target);
  conflicting_target.Arm(Target());
  conflicting_target.Observe(Copy(kBase, kFirstLength));
  Require(!conflicting_target.Flush(),
          "conflicting target states must invalidate the entire frame");

  nr::ProceduralResolveAssemblyTracker overflow;
  overflow.Arm(Target());
  overflow.Observe(Copy(kBase, kFirstLength));
  overflow.Observe(Copy(kBase + kFirstLength, kFirstLength));
  overflow.Observe(Copy(kBase + 2 * kFirstLength, kLastLength));
  for (size_t index = 3;
       index <= nr::ProceduralResolveAssemblyTracker::kMaximumCopiesPerFrame;
       ++index) {
    auto unrelated = Copy(0x1000 + uint32_t(index) * 0x1000, 0x1000);
    unrelated.source_info = 0x00040000;
    overflow.Observe(unrelated);
  }
  const auto overflowed = overflow.Flush();
  Require(overflowed && overflowed->copy_overflow &&
              !overflowed->exact_contiguous_full_frame,
          "copy overflow must fail the exact assembly closed");

  std::cout << "native renderer resolve assembly tracker tests passed\n";
  return EXIT_SUCCESS;
}
