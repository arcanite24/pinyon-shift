#include "native_renderer/resolve_frame_accumulator.h"

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

nr::ProceduralResolveTarget Target(uint64_t frame = 10) {
  return {.frame_sequence = frame,
          .surface_info = 0x14020500,
          .color_info = 0x00030000,
          .logical_width = 1280,
          .logical_height = 720};
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

nr::ProceduralFrameAccumulatorSourceTopology Topology(
    uint32_t guest_height, uint32_t scale = 2) {
  return {.resource_width = 1280 * scale,
          .resource_height = 512 * scale,
          .host_sample_count = 4,
          .guest_msaa_samples = 4,
          .draw_scale_x = scale,
          .draw_scale_y = scale,
          .target_base_tiles = 0,
          .target_pitch_tiles = 32,
          .resolve_base_tiles = 0,
          .resolve_pitch_tiles = 32,
          .resolve_guest_msaa_samples = 4,
          .source_guest_x = 0,
          .source_guest_y = 0,
          .source_guest_width = 1280,
          .source_guest_height = guest_height,
          .source_physical_x = 0,
          .source_physical_y = 0,
          .source_physical_width = 1280 * scale,
          .source_physical_height = guest_height * scale,
          .destination_x = 0,
          .destination_y = 0,
          .destination_pitch = 1280,
          .destination_height = 736,
          .sample_select = 6,
          .source_available = true,
          .resolve_info_valid = true,
          .native_2x_msaa = true};
}

}  // namespace

int main() {
  constexpr uint32_t kRows256 = 1280 * 256 * 4;
  constexpr uint32_t kRows224 = 1280 * 224 * 4;
  constexpr uint32_t kBase = 0x1C4E1000;

  nr::ProceduralFrameAccumulatorPlanner planner;
  Require(!planner.Arm(Target()).actionable(), "arming must be passive");
  const auto first = planner.Observe(Copy(kBase, kRows256));
  Require(first.begin && first.append && !first.commit && !first.cancel &&
              first.destination_row == 0 &&
              first.storage_row_count == 256 &&
              first.logical_row_count == 256,
          "the first chunk must begin at row zero");
  const auto second = planner.Observe(Copy(kBase + kRows256, kRows256));
  Require(!second.begin && second.append && !second.commit &&
              second.destination_row == 256 &&
              second.storage_row_count == 256,
          "the second chunk must append at row 256");
  const auto third =
      planner.Observe(Copy(kBase + 2 * kRows256, kRows224));
  Require(third.append && third.commit && !third.cancel &&
              third.destination_row == 512 &&
              third.storage_row_count == 224 &&
              third.logical_row_count == 208 &&
              third.padded_height == 736 && third.chunk_count == 3,
          "the final chunk must commit 720 logical and 736 stored rows");

  const auto first_layout =
      nr::BuildProceduralFrameAccumulatorPhysicalLayout(first, Topology(256));
  Require(first_layout.ready() && first_layout.output_width == 2560 &&
              first_layout.output_logical_height == 1440 &&
              first_layout.output_storage_height == 1472 &&
              first_layout.destination_row == 0 &&
              first_layout.destination_copy_rows == 512 &&
              first_layout.padding_rows == 0 &&
              first_layout.source_width == 2560 &&
              first_layout.source_height == 512,
          "the first 2x resolve must map exactly into physical rows");
  const auto second_layout =
      nr::BuildProceduralFrameAccumulatorPhysicalLayout(second, Topology(256));
  Require(second_layout.ready() && second_layout.destination_row == 512 &&
              second_layout.output_storage_height == 1472 &&
              second_layout.destination_copy_rows == 512,
          "the second 2x resolve must append after the first physical rows");
  const auto third_layout =
      nr::BuildProceduralFrameAccumulatorPhysicalLayout(third, Topology(208));
  Require(third_layout.ready() && third_layout.destination_row == 1024 &&
              third_layout.output_logical_height == 1440 &&
              third_layout.output_storage_height == 1472 &&
              third_layout.destination_copy_rows == 416 &&
              third_layout.destination_storage_rows == 448 &&
              third_layout.padding_rows == 32 &&
              third_layout.source_y == 0 && third_layout.source_height == 416,
          "the final 2x resolve must preserve logical rows and padded storage");

  auto wrong_target = Topology(256);
  wrong_target.resolve_pitch_tiles = 31;
  Require(nr::BuildProceduralFrameAccumulatorPhysicalLayout(first,
                                                             wrong_target)
                  .status == nr::ProceduralFrameAccumulatorLayoutStatus::
                                 kTargetMismatch,
          "a different resolve target must fail closed");
  auto wrong_crop = Topology(256);
  wrong_crop.source_physical_y = 512;
  Require(nr::BuildProceduralFrameAccumulatorPhysicalLayout(first, wrong_crop)
                  .status == nr::ProceduralFrameAccumulatorLayoutStatus::
                                 kRegionMismatch,
          "a destination-row source crop must fail against resolve origin");
  auto wrong_samples = Topology(256);
  wrong_samples.sample_select = 0;
  Require(nr::BuildProceduralFrameAccumulatorPhysicalLayout(first,
                                                             wrong_samples)
                  .status == nr::ProceduralFrameAccumulatorLayoutStatus::
                                 kUnsupportedSamples,
          "a non-averaging sample selection must remain unsupported");
  auto missing_topology = Topology(256);
  missing_topology.resolve_info_valid = false;
  Require(nr::BuildProceduralFrameAccumulatorPhysicalLayout(first,
                                                             missing_topology)
                  .status == nr::ProceduralFrameAccumulatorLayoutStatus::
                                 kMissingTopology,
          "missing resolve geometry must fail closed");
  Require(!planner.Flush().actionable(),
          "a committed frame must not be cancelled at shutdown");

  nr::ProceduralFrameAccumulatorPlanner gap;
  gap.Arm(Target());
  gap.Observe(Copy(kBase, kRows256));
  const auto gap_result =
      gap.Observe(Copy(kBase + kRows256 + 0x1000, kRows256));
  Require(gap_result.cancel && !gap_result.append &&
              gap_result.cancel_reason ==
                  nr::ProceduralFrameAccumulatorCancelReason::
                      kDestinationMismatch,
          "an address gap must cancel the private plan");

  nr::ProceduralFrameAccumulatorPlanner mismatch;
  mismatch.Arm(Target());
  auto wrong_source = Copy(kBase, kRows256);
  wrong_source.source_info = 0x00040000;
  Require(!mismatch.Observe(wrong_source).actionable(),
          "a source mismatch must remain outside the plan");

  nr::ProceduralFrameAccumulatorPlanner invalid;
  invalid.Arm(Target());
  auto malformed = Copy(kBase, kRows256);
  malformed.destination_pitch = 0x02D00400;
  Require(!invalid.Observe(malformed).actionable(),
          "an invalid first chunk has no backend resource to cancel");
  Require(!invalid.Observe(Copy(kBase, kRows256)).actionable(),
          "an invalid matching chunk must poison the rest of the frame");

  nr::ProceduralFrameAccumulatorPlanner conflict;
  conflict.Arm(Target());
  conflict.Observe(Copy(kBase, kRows256));
  auto other_target = Target();
  other_target.color_info = 0x00040000;
  const auto conflict_result = conflict.Arm(other_target);
  Require(conflict_result.cancel &&
              conflict_result.cancel_reason ==
                  nr::ProceduralFrameAccumulatorCancelReason::kTargetConflict,
          "a target conflict must cancel the active plan");

  nr::ProceduralFrameAccumulatorPlanner advance;
  advance.Arm(Target());
  advance.Observe(Copy(kBase, kRows256));
  const auto advanced = advance.Arm(Target(11));
  Require(advanced.cancel &&
              advanced.cancel_reason ==
                  nr::ProceduralFrameAccumulatorCancelReason::kFrameAdvanced,
          "an incomplete frame must cancel on frame advance");

  nr::ProceduralFrameAccumulatorPlanner overflow;
  overflow.Arm(Target());
  constexpr uint32_t kRows80 = 1280 * 80 * 4;
  for (uint32_t chunk = 0;
       chunk < nr::ProceduralFrameAccumulatorPlanner::kMaximumChunks;
       ++chunk) {
    const auto appended =
        overflow.Observe(Copy(kBase + chunk * kRows80, kRows80));
    Require(appended.append && !appended.commit && !appended.cancel,
            "bounded partial chunks must append before the cap");
  }
  const auto overflowed = overflow.Observe(
      Copy(kBase +
               nr::ProceduralFrameAccumulatorPlanner::kMaximumChunks *
                   kRows80,
           kRows80));
  Require(overflowed.cancel &&
              overflowed.cancel_reason ==
                  nr::ProceduralFrameAccumulatorCancelReason::kChunkOverflow,
          "a ninth chunk must cancel the bounded plan");

  nr::ProceduralResolveTarget qualified_target;
  Require(nr::QualifiedProceduralResolveTargetFromFirstCopy(
              Copy(kBase, kRows256), qualified_target) &&
              qualified_target.frame_sequence == 10 &&
              qualified_target.surface_info == 0x14020500 &&
              qualified_target.color_info == 0x00030000 &&
              qualified_target.logical_width == 1280 &&
              qualified_target.logical_height == 720,
          "the qualified float first chunk must arm the full-frame target");

  auto float_as_16 = Copy(kBase, kRows256);
  float_as_16.source_info = 0x000C0000;
  Require(nr::QualifiedProceduralResolveTargetFromFirstCopy(
              float_as_16, qualified_target) &&
              qualified_target.color_info == 0x000C0000,
          "the qualified float-as-16 alias must arm the same host family");

  const auto rejected = [](nr::ProceduralResolveCopy copy) {
    nr::ProceduralResolveTarget target;
    return nr::QualifiedProceduralResolveTargetFromFirstCopy(copy, target);
  };
  auto near_miss = Copy(kBase, kRows256);
  near_miss.source_info = 0x00020000;
  Require(!rejected(near_miss), "an unproved source mode must fail closed");
  near_miss = Copy(kBase, kRows256);
  near_miss.destination_info ^= 1;
  Require(!rejected(near_miss), "a destination format mismatch must fail");
  near_miss = Copy(kBase, kRows256);
  near_miss.destination_pitch ^= 1;
  Require(!rejected(near_miss), "a destination extent mismatch must fail");
  near_miss = Copy(kBase + 1, kRows256);
  Require(!rejected(near_miss), "a first-address mismatch must fail");
  near_miss = Copy(kBase, kRows256 - 1);
  Require(!rejected(near_miss), "a first-row-count mismatch must fail");

  std::cout << "native renderer resolve frame accumulator tests passed\n";
  return EXIT_SUCCESS;
}
