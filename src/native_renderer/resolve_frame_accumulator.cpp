#include "native_renderer/resolve_frame_accumulator.h"

#include <algorithm>
#include <limits>

namespace pinyon_shift::native_renderer {

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

}  // namespace pinyon_shift::native_renderer
