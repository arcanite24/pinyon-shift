#ifndef PINYON_SHIFT_NATIVE_RENDERER_RESOLVE_FRAME_ACCUMULATOR_H_
#define PINYON_SHIFT_NATIVE_RENDERER_RESOLVE_FRAME_ACCUMULATOR_H_

#include <cstdint>

#include "native_renderer/resolve_assembly_tracker.h"

namespace pinyon_shift::native_renderer {

enum class ProceduralFrameAccumulatorCancelReason : uint8_t {
  kNone,
  kFrameAdvanced,
  kTargetConflict,
  kDestinationMismatch,
  kInvalidChunk,
  kChunkOverflow,
};

struct ProceduralFrameAccumulatorTransition {
  uint64_t frame_sequence = 0;
  uint32_t source_surface_info = 0;
  uint32_t source_info = 0;
  uint32_t destination_info = 0;
  uint32_t destination_pitch = 0;
  uint32_t base_address = 0;
  uint32_t copy_address = 0;
  uint32_t copy_length = 0;
  uint32_t destination_row = 0;
  uint32_t storage_row_count = 0;
  uint32_t logical_row_count = 0;
  uint32_t logical_width = 0;
  uint32_t logical_height = 0;
  uint32_t padded_height = 0;
  uint32_t bytes_per_pixel = 0;
  uint32_t chunk_count = 0;
  bool begin = false;
  bool append = false;
  bool commit = false;
  bool cancel = false;
  ProceduralFrameAccumulatorCancelReason cancel_reason =
      ProceduralFrameAccumulatorCancelReason::kNone;

  bool actionable() const { return begin || append || commit || cancel; }
};

// Produces a backend-neutral, fail-closed row-copy plan for assembling the
// proved procedural EDRAM chunks into one private padded frame. It owns no GPU
// resources and cannot publish, suppress, or otherwise alter guest rendering.
class ProceduralFrameAccumulatorPlanner {
 public:
  static constexpr uint32_t kMaximumChunks =
      ProceduralResolveAssembly::kMaximumChunks;

  ProceduralFrameAccumulatorTransition Arm(
      const ProceduralResolveTarget &target);
  ProceduralFrameAccumulatorTransition Observe(
      const ProceduralResolveCopy &copy);
  ProceduralFrameAccumulatorTransition Flush();

 private:
  ProceduralFrameAccumulatorTransition Advance(uint64_t frame_sequence);
  ProceduralFrameAccumulatorTransition Cancel(
      ProceduralFrameAccumulatorCancelReason reason);
  void Reset(uint64_t frame_sequence);

  uint64_t frame_sequence_ = 0;
  ProceduralResolveTarget target_{};
  uint32_t source_surface_info_ = 0;
  uint32_t source_info_ = 0;
  uint32_t destination_info_ = 0;
  uint32_t destination_pitch_ = 0;
  uint32_t base_address_ = 0;
  uint32_t next_address_ = 0;
  uint32_t bytes_per_pixel_ = 0;
  uint32_t padded_height_ = 0;
  uint32_t chunk_count_ = 0;
  bool active_ = false;
  bool committed_ = false;
  bool target_conflict_ = false;
  bool frame_invalid_ = false;
};

const char *ProceduralFrameAccumulatorCancelReasonName(
    ProceduralFrameAccumulatorCancelReason reason);

// Recognizes the exact first resolve chunk of the qualified Forza full-frame
// family. The title uses two Xenos color modes that map to the same host
// R16G16B16A16_FLOAT resource; every other field remains fail-closed.
bool QualifiedProceduralResolveTargetFromFirstCopy(
    const ProceduralResolveCopy &copy, ProceduralResolveTarget &target_out);

}  // namespace pinyon_shift::native_renderer

#endif  // PINYON_SHIFT_NATIVE_RENDERER_RESOLVE_FRAME_ACCUMULATOR_H_
