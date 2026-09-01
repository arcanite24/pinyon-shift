#include "native_renderer/resolve_frame_accumulator.h"

#include <algorithm>
#include <limits>

namespace pinyon_shift::native_renderer {

namespace {

bool CheckedMultiply(uint32_t left, uint32_t right, uint32_t &result_out) {
  const uint64_t result = uint64_t(left) * right;
  if (result > UINT32_MAX) {
    return false;
  }
  result_out = uint32_t(result);
  return true;
}

bool CheckedAdd(uint32_t left, uint32_t right, uint32_t &result_out) {
  const uint64_t result = uint64_t(left) + right;
  if (result > UINT32_MAX) {
    return false;
  }
  result_out = uint32_t(result);
  return true;
}

}  // namespace

ProceduralFrameAccumulatorPhysicalLayout
BuildProceduralFrameAccumulatorPhysicalLayout(
    const ProceduralFrameAccumulatorTransition &transition,
    const ProceduralFrameAccumulatorSourceTopology &topology) {
  ProceduralFrameAccumulatorPhysicalLayout layout;
  if (!transition.append || transition.cancel) {
    return layout;
  }
  if (!topology.source_available || !topology.resolve_info_valid) {
    layout.status = ProceduralFrameAccumulatorLayoutStatus::kMissingTopology;
    return layout;
  }
  if (!topology.draw_scale_x || !topology.draw_scale_y ||
      topology.draw_scale_x > 7 || topology.draw_scale_y > 7) {
    layout.status = ProceduralFrameAccumulatorLayoutStatus::kInvalidScale;
    return layout;
  }
  if (topology.target_base_tiles != topology.resolve_base_tiles ||
      topology.target_pitch_tiles != topology.resolve_pitch_tiles ||
      topology.guest_msaa_samples !=
          topology.resolve_guest_msaa_samples) {
    layout.status = ProceduralFrameAccumulatorLayoutStatus::kTargetMismatch;
    return layout;
  }
  const bool supported_samples =
      topology.host_sample_count == topology.guest_msaa_samples ||
      (topology.guest_msaa_samples == 2 &&
       topology.host_sample_count == 4 && !topology.native_2x_msaa);
  // The proved family resolves all samples. Keep other resolve semantics closed
  // until their native single-sample conversion is implemented explicitly.
  if (!supported_samples || topology.sample_select != 6) {
    layout.status =
        ProceduralFrameAccumulatorLayoutStatus::kUnsupportedSamples;
    return layout;
  }

  uint32_t output_width = 0;
  uint32_t output_logical_height = 0;
  uint32_t output_storage_height = 0;
  uint32_t destination_row = 0;
  uint32_t destination_storage_rows = 0;
  uint32_t destination_copy_rows = 0;
  uint32_t expected_source_x = 0;
  uint32_t expected_source_y = 0;
  uint32_t expected_source_width = 0;
  uint32_t expected_source_height = 0;
  if (!CheckedMultiply(transition.logical_width, topology.draw_scale_x,
                       output_width) ||
      !CheckedMultiply(transition.logical_height, topology.draw_scale_y,
                       output_logical_height) ||
      !CheckedMultiply(topology.destination_height, topology.draw_scale_y,
                       output_storage_height) ||
      !CheckedMultiply(transition.destination_row, topology.draw_scale_y,
                       destination_row) ||
      !CheckedMultiply(transition.storage_row_count, topology.draw_scale_y,
                       destination_storage_rows) ||
      !CheckedMultiply(transition.logical_row_count, topology.draw_scale_y,
                       destination_copy_rows) ||
      !CheckedMultiply(topology.source_guest_x, topology.draw_scale_x,
                       expected_source_x) ||
      !CheckedMultiply(topology.source_guest_y, topology.draw_scale_y,
                       expected_source_y) ||
      !CheckedMultiply(topology.source_guest_width, topology.draw_scale_x,
                       expected_source_width) ||
      !CheckedMultiply(topology.source_guest_height, topology.draw_scale_y,
                       expected_source_height)) {
    layout.status = ProceduralFrameAccumulatorLayoutStatus::kOverflow;
    return layout;
  }
  uint32_t source_end_x = 0;
  uint32_t source_end_y = 0;
  uint32_t destination_copy_end = 0;
  uint32_t destination_storage_end = 0;
  if (!CheckedAdd(topology.source_physical_x,
                  topology.source_physical_width, source_end_x) ||
      !CheckedAdd(topology.source_physical_y,
                  topology.source_physical_height, source_end_y) ||
      !CheckedAdd(destination_row, destination_copy_rows,
                  destination_copy_end) ||
      !CheckedAdd(destination_row, destination_storage_rows,
                  destination_storage_end)) {
    layout.status = ProceduralFrameAccumulatorLayoutStatus::kOverflow;
    return layout;
  }
  const bool region_matches =
      topology.source_physical_x == expected_source_x &&
      topology.source_physical_y == expected_source_y &&
      topology.source_physical_width == expected_source_width &&
      topology.source_physical_height == expected_source_height &&
      topology.source_guest_width == transition.logical_width &&
      topology.source_guest_height == transition.logical_row_count &&
      topology.destination_x == 0 && topology.destination_y == 0 &&
      topology.destination_pitch == transition.logical_width &&
      topology.destination_height >= transition.logical_height &&
      uint64_t(topology.destination_height) <
          uint64_t(transition.logical_height) + 64 &&
      source_end_x <= topology.resource_width &&
      source_end_y <= topology.resource_height &&
      destination_copy_end <= output_logical_height &&
      destination_storage_end <= output_storage_height &&
      (!transition.commit ||
       destination_storage_end == output_storage_height) &&
      destination_copy_rows <= destination_storage_rows;
  if (!region_matches) {
    layout.status = ProceduralFrameAccumulatorLayoutStatus::kRegionMismatch;
    return layout;
  }

  layout.status = ProceduralFrameAccumulatorLayoutStatus::kReady;
  layout.output_width = output_width;
  layout.output_logical_height = output_logical_height;
  layout.output_storage_height = output_storage_height;
  layout.destination_row = destination_row;
  layout.destination_storage_rows = destination_storage_rows;
  layout.destination_copy_rows = destination_copy_rows;
  layout.source_x = topology.source_physical_x;
  layout.source_y = topology.source_physical_y;
  layout.source_width = topology.source_physical_width;
  layout.source_height = topology.source_physical_height;
  layout.padding_rows = destination_storage_rows - destination_copy_rows;
  layout.host_sample_count = topology.host_sample_count;
  layout.guest_msaa_samples = topology.guest_msaa_samples;
  layout.sample_select = topology.sample_select;
  return layout;
}

const char *ProceduralFrameAccumulatorLayoutStatusName(
    ProceduralFrameAccumulatorLayoutStatus status) {
  switch (status) {
    case ProceduralFrameAccumulatorLayoutStatus::kReady:
      return "ready";
    case ProceduralFrameAccumulatorLayoutStatus::kNoAppend:
      return "no_append";
    case ProceduralFrameAccumulatorLayoutStatus::kMissingTopology:
      return "missing_topology";
    case ProceduralFrameAccumulatorLayoutStatus::kInvalidScale:
      return "invalid_scale";
    case ProceduralFrameAccumulatorLayoutStatus::kTargetMismatch:
      return "target_mismatch";
    case ProceduralFrameAccumulatorLayoutStatus::kRegionMismatch:
      return "region_mismatch";
    case ProceduralFrameAccumulatorLayoutStatus::kUnsupportedSamples:
      return "unsupported_samples";
    case ProceduralFrameAccumulatorLayoutStatus::kOverflow:
      return "overflow";
  }
  return "unknown";
}

void ProceduralFrameAccumulatorPlanner::Reset(uint64_t frame_sequence) {
  frame_sequence_ = frame_sequence;
  target_ = {};
  source_surface_info_ = 0;
  source_info_ = 0;
  destination_info_ = 0;
  destination_pitch_ = 0;
  base_address_ = 0;
  next_address_ = 0;
  bytes_per_pixel_ = 0;
  padded_height_ = 0;
  chunk_count_ = 0;
  active_ = false;
  committed_ = false;
  target_conflict_ = false;
  frame_invalid_ = false;
}

ProceduralFrameAccumulatorTransition
ProceduralFrameAccumulatorPlanner::Cancel(
    ProceduralFrameAccumulatorCancelReason reason) {
  ProceduralFrameAccumulatorTransition transition{
      .frame_sequence = frame_sequence_,
      .source_surface_info = source_surface_info_,
      .source_info = source_info_,
      .destination_info = destination_info_,
      .destination_pitch = destination_pitch_,
      .base_address = base_address_,
      .logical_width = target_.logical_width,
      .logical_height = target_.logical_height,
      .padded_height = padded_height_,
      .bytes_per_pixel = bytes_per_pixel_,
      .chunk_count = chunk_count_,
      .cancel = active_ && !committed_,
      .cancel_reason = reason};
  active_ = false;
  if (reason != ProceduralFrameAccumulatorCancelReason::kFrameAdvanced) {
    frame_invalid_ = true;
  }
  return transition;
}

ProceduralFrameAccumulatorTransition
ProceduralFrameAccumulatorPlanner::Advance(uint64_t frame_sequence) {
  if (!frame_sequence_ || frame_sequence_ == frame_sequence) {
    if (!frame_sequence_) {
      Reset(frame_sequence);
    }
    return {};
  }
  ProceduralFrameAccumulatorTransition transition =
      Cancel(ProceduralFrameAccumulatorCancelReason::kFrameAdvanced);
  Reset(frame_sequence);
  return transition;
}

ProceduralFrameAccumulatorTransition
ProceduralFrameAccumulatorPlanner::Arm(
    const ProceduralResolveTarget &target) {
  ProceduralFrameAccumulatorTransition transition =
      Advance(target.frame_sequence);
  if (!target.valid() || target_conflict_) {
    return transition;
  }
  if (!target_.valid()) {
    target_ = target;
    return transition;
  }
  if (target_.surface_info == target.surface_info &&
      target_.color_info == target.color_info &&
      target_.logical_width == target.logical_width &&
      target_.logical_height == target.logical_height) {
    return transition;
  }
  ProceduralFrameAccumulatorTransition conflict =
      Cancel(ProceduralFrameAccumulatorCancelReason::kTargetConflict);
  target_ = {};
  target_conflict_ = true;
  return conflict.actionable() ? conflict : transition;
}

ProceduralFrameAccumulatorTransition
ProceduralFrameAccumulatorPlanner::Observe(
    const ProceduralResolveCopy &copy) {
  ProceduralFrameAccumulatorTransition transition =
      Advance(copy.frame_sequence);
  if (transition.actionable() || !target_.valid() || target_conflict_ ||
      frame_invalid_ ||
      copy.source || copy.source_surface_info != target_.surface_info ||
      copy.source_info != target_.color_info || !copy.written_length ||
      committed_) {
    return transition;
  }

  const uint32_t pitch_width = copy.destination_pitch & 0x3FFF;
  const uint32_t logical_height = (copy.destination_pitch >> 16) & 0x3FFF;
  const uint32_t color_format = (copy.destination_info >> 7) & 0x3F;
  const uint32_t bytes_per_pixel = XenosColorBytesPerPixel(color_format);
  const uint64_t row_bytes = uint64_t(pitch_width) * bytes_per_pixel;
  const bool valid_chunk =
      pitch_width == target_.logical_width &&
      logical_height == target_.logical_height && bytes_per_pixel &&
      row_bytes <= std::numeric_limits<uint32_t>::max() &&
      copy.written_length % row_bytes == 0 &&
      copy.written_length / row_bytes > 0 &&
      copy.written_length / row_bytes <=
          std::numeric_limits<uint32_t>::max();
  if (!valid_chunk) {
    return Cancel(ProceduralFrameAccumulatorCancelReason::kInvalidChunk);
  }

  if (!active_) {
    active_ = true;
    source_surface_info_ = copy.source_surface_info;
    source_info_ = copy.source_info;
    destination_info_ = copy.destination_info;
    destination_pitch_ = copy.destination_pitch;
    base_address_ = copy.written_address;
    next_address_ = copy.written_address;
    bytes_per_pixel_ = bytes_per_pixel;
  } else if (copy.destination_info != destination_info_ ||
             copy.destination_pitch != destination_pitch_ ||
             copy.written_address != next_address_) {
    return Cancel(
        ProceduralFrameAccumulatorCancelReason::kDestinationMismatch);
  }
  if (chunk_count_ == kMaximumChunks) {
    return Cancel(ProceduralFrameAccumulatorCancelReason::kChunkOverflow);
  }

  const uint32_t storage_rows = uint32_t(copy.written_length / row_bytes);
  if (padded_height_ > target_.logical_height + 63 ||
      storage_rows > target_.logical_height + 63 - padded_height_ ||
      uint64_t(copy.written_address) + copy.written_length > UINT32_MAX) {
    return Cancel(ProceduralFrameAccumulatorCancelReason::kInvalidChunk);
  }
  const uint32_t destination_row = padded_height_;
  const uint32_t logical_rows =
      destination_row >= target_.logical_height
          ? 0
          : std::min(storage_rows,
                     target_.logical_height - destination_row);
  padded_height_ += storage_rows;
  next_address_ = copy.written_address + copy.written_length;
  ++chunk_count_;

  const bool complete = chunk_count_ > 1 &&
                        padded_height_ >= target_.logical_height &&
                        padded_height_ < target_.logical_height + 64;
  transition = {.frame_sequence = frame_sequence_,
                .source_surface_info = source_surface_info_,
                .source_info = source_info_,
                .destination_info = destination_info_,
                .destination_pitch = destination_pitch_,
                .base_address = base_address_,
                .copy_address = copy.written_address,
                .copy_length = copy.written_length,
                .destination_row = destination_row,
                .storage_row_count = storage_rows,
                .logical_row_count = logical_rows,
                .logical_width = target_.logical_width,
                .logical_height = target_.logical_height,
                .padded_height = padded_height_,
                .bytes_per_pixel = bytes_per_pixel_,
                .chunk_count = chunk_count_,
                .begin = chunk_count_ == 1,
                .append = true,
                .commit = complete};
  committed_ = complete;
  return transition;
}

ProceduralFrameAccumulatorTransition
ProceduralFrameAccumulatorPlanner::Flush() {
  ProceduralFrameAccumulatorTransition transition =
      Cancel(ProceduralFrameAccumulatorCancelReason::kFrameAdvanced);
  Reset(0);
  return transition;
}

const char *ProceduralFrameAccumulatorCancelReasonName(
    ProceduralFrameAccumulatorCancelReason reason) {
  switch (reason) {
    case ProceduralFrameAccumulatorCancelReason::kNone:
      return "none";
    case ProceduralFrameAccumulatorCancelReason::kFrameAdvanced:
      return "frame_advanced";
    case ProceduralFrameAccumulatorCancelReason::kTargetConflict:
      return "target_conflict";
    case ProceduralFrameAccumulatorCancelReason::kDestinationMismatch:
      return "destination_mismatch";
    case ProceduralFrameAccumulatorCancelReason::kInvalidChunk:
      return "invalid_chunk";
    case ProceduralFrameAccumulatorCancelReason::kChunkOverflow:
      return "chunk_overflow";
  }
  return "unknown";
}

bool QualifiedProceduralResolveTargetFromFirstCopy(
    const ProceduralResolveCopy &copy, ProceduralResolveTarget &target_out) {
  target_out = {};
  constexpr uint32_t kSurfaceInfo = 0x14020500;
  constexpr uint32_t kFloatColorInfo = 0x00030000;
  constexpr uint32_t kFloatAs16ColorInfo = 0x000C0000;
  constexpr uint32_t kDestinationInfo = 0x003E0382;
  constexpr uint32_t kDestinationPitch = 0x02D00500;
  constexpr uint32_t kFirstAddress = 0x1C4E1000;
  constexpr uint32_t kFirstLength = 1280 * 4 * 256;
  const bool qualified_source =
      copy.source == 0 && copy.source_surface_info == kSurfaceInfo &&
      (copy.source_info == kFloatColorInfo ||
       copy.source_info == kFloatAs16ColorInfo);
  if (!qualified_source || copy.destination_info != kDestinationInfo ||
      copy.destination_pitch != kDestinationPitch ||
      copy.written_address != kFirstAddress ||
      copy.written_length != kFirstLength) {
    return false;
  }
  target_out = {.frame_sequence = copy.frame_sequence,
                .surface_info = copy.source_surface_info,
                .color_info = copy.source_info,
                .logical_width = 1280,
                .logical_height = 720};
  return true;
}

}  // namespace pinyon_shift::native_renderer
