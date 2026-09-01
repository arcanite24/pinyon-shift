#include "native_renderer/resolve_assembly_tracker.h"

#include <algorithm>
#include <array>
#include <limits>

namespace pinyon_shift::native_renderer {
namespace {

uint32_t ColorBytesPerPixel(uint32_t format) {
  switch (format) {
    case 2:
    case 8:
    case 9:
      return 1;
    case 3:
    case 4:
    case 5:
    case 10:
    case 15:
    case 24:
    case 30:
      return 2;
    case 6:
    case 7:
    case 14:
    case 16:
    case 17:
    case 25:
    case 31:
    case 36:
      return 4;
    case 26:
    case 32:
    case 37:
    case 50:
    case 54:
    case 55:
    case 56:
      return 8;
    case 38:
      return 16;
    default:
      return 0;
  }
}

}  // namespace

std::optional<ProceduralResolveAssembly>
ProceduralResolveAssemblyTracker::Advance(uint64_t frame_sequence) {
  if (!frame_sequence_ || frame_sequence_ == frame_sequence) {
    if (!frame_sequence_) {
      Reset(frame_sequence);
    }
    return std::nullopt;
  }
  std::optional<ProceduralResolveAssembly> result = Finalize();
  Reset(frame_sequence);
  return result;
}

void ProceduralResolveAssemblyTracker::Reset(uint64_t frame_sequence) {
  frame_sequence_ = frame_sequence;
  target_ = {};
  copy_count_ = 0;
  copy_overflow_ = false;
  target_conflict_ = false;
}

std::optional<ProceduralResolveAssembly> ProceduralResolveAssemblyTracker::Arm(
    const ProceduralResolveTarget& target) {
  std::optional<ProceduralResolveAssembly> result =
      Advance(target.frame_sequence);
  if (!target.valid()) {
    return result;
  }
  if (target_conflict_) {
    return result;
  }
  if (!target_.valid()) {
    target_ = target;
  } else if (target_.surface_info != target.surface_info ||
             target_.color_info != target.color_info ||
             target_.logical_width != target.logical_width ||
             target_.logical_height != target.logical_height) {
    target_ = {};
    target_conflict_ = true;
  }
  return result;
}

std::optional<ProceduralResolveAssembly>
ProceduralResolveAssemblyTracker::Observe(const ProceduralResolveCopy& copy) {
  std::optional<ProceduralResolveAssembly> result =
      Advance(copy.frame_sequence);
  if (!copy.frame_sequence || copy.source >= 4 || !copy.written_length) {
    return result;
  }
  if (copy_count_ == copies_.size()) {
    copy_overflow_ = true;
    return result;
  }
  copies_[copy_count_++] = copy;
  return result;
}

std::optional<ProceduralResolveAssembly>
ProceduralResolveAssemblyTracker::Finalize() {
  if (!target_.valid()) {
    return std::nullopt;
  }

  std::array<ProceduralResolveCopy, kMaximumCopiesPerFrame> matches{};
  size_t match_count = 0;
  for (size_t index = 0; index < copy_count_; ++index) {
    const ProceduralResolveCopy& copy = copies_[index];
    if (copy.source || copy.source_surface_info != target_.surface_info ||
        copy.source_info != target_.color_info) {
      continue;
    }
    matches[match_count++] = copy;
  }
  if (!match_count) {
    return ProceduralResolveAssembly{.frame_sequence = frame_sequence_,
                                     .source_surface_info = target_.surface_info,
                                     .source_info = target_.color_info,
                                     .logical_width = target_.logical_width,
                                     .logical_height = target_.logical_height,
                                     .copy_overflow = copy_overflow_};
  }

  std::sort(matches.begin(), matches.begin() + match_count,
            [](const ProceduralResolveCopy& left,
               const ProceduralResolveCopy& right) {
              return left.written_address < right.written_address;
            });

  ProceduralResolveAssembly best{
      .frame_sequence = frame_sequence_,
      .source_surface_info = target_.surface_info,
      .source_info = target_.color_info,
      .logical_width = target_.logical_width,
      .logical_height = target_.logical_height,
      .copy_overflow = copy_overflow_};
  for (size_t begin = 0; begin < match_count;) {
    size_t end = begin + 1;
    const ProceduralResolveCopy& first = matches[begin];
    uint64_t total_bytes = first.written_length;
    while (end < match_count && end - begin < best.addresses.size() &&
           matches[end].destination_info == first.destination_info &&
           matches[end].destination_pitch == first.destination_pitch &&
           uint64_t(matches[end - 1].written_address) +
                   matches[end - 1].written_length ==
               matches[end].written_address) {
      total_bytes += matches[end].written_length;
      ++end;
    }

    const uint32_t chunk_count = uint32_t(end - begin);
    const uint32_t pitch_width = first.destination_pitch & 0x3FFF;
    const uint32_t logical_height =
        (first.destination_pitch >> 16) & 0x3FFF;
    const uint32_t color_format = (first.destination_info >> 7) & 0x3F;
    const uint32_t bytes_per_pixel = ColorBytesPerPixel(color_format);
    const uint64_t row_bytes = uint64_t(pitch_width) * bytes_per_pixel;
    const uint32_t padded_height =
        row_bytes && total_bytes % row_bytes == 0 &&
                total_bytes / row_bytes <= std::numeric_limits<uint32_t>::max()
            ? uint32_t(total_bytes / row_bytes)
            : 0;
    const bool exact =
        chunk_count > 1 && pitch_width == target_.logical_width &&
        logical_height == target_.logical_height && padded_height >= logical_height &&
        padded_height < logical_height + 64 && bytes_per_pixel &&
        !copy_overflow_;

    if (exact || chunk_count > best.chunk_count) {
      best.source = first.source;
      best.destination_info = first.destination_info;
      best.destination_pitch = first.destination_pitch;
      best.base_address = first.written_address;
      best.padded_height = padded_height;
      best.bytes_per_pixel = bytes_per_pixel;
      best.total_bytes = total_bytes;
      best.chunk_count = chunk_count;
      best.exact_contiguous_full_frame = exact;
      for (size_t index = begin; index < end; ++index) {
        best.addresses[index - begin] = matches[index].written_address;
        best.lengths[index - begin] = matches[index].written_length;
      }
    }
    if (exact) {
      break;
    }
    begin = end;
  }
  if (best.exact_contiguous_full_frame) {
    latest_qualified_ = best;
  }
  return best;
}

std::optional<ProceduralResolveAssembly>
ProceduralResolveAssemblyTracker::Flush() {
  std::optional<ProceduralResolveAssembly> result = Finalize();
  Reset(0);
  return result;
}

}  // namespace pinyon_shift::native_renderer
