#include <algorithm>
#include <array>
#include <atomic>
#include <bit>
#include <charconv>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <limits>
#include <mutex>
#include <span>
#include <string>
#include <thread>
#include <type_traits>
#include <vector>

#include <fmt/format.h>
#include <rex/cvar.h>
#include <rex/graphics/xenos.h>
#include <rex/memory.h>
#include <rex/ppc/context.h>
#include <rex/system/interfaces/graphics.h>
#include <rex/system/kernel_state.h>
#include <rex/system/xmemory.h>

#include "native_renderer/graphics_hooks.h"
#include "native_renderer/resource_identity.h"
#include "pinyon_shift_diagnostics.h"

REXCVAR_DEFINE_BOOL(
    pinyon_shift_native_renderer_census, false, "Pinyon Shift",
    "Record bounded native-renderer census metadata without changing rendering")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);
REXCVAR_DEFINE_BOOL(
    pinyon_shift_native_renderer_dispatch_discovery, false, "Pinyon Shift",
                    "Record bounded title graphics-wrapper caller metadata "
                    "without changing rendering")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);
REXCVAR_DEFINE_BOOL(
    pinyon_shift_native_renderer_sky_horizon_suppression, false,
    "Pinyon Shift",
    "Request the fail-closed sky/horizon suppression experiment")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

namespace {

constexpr uint64_t kFrameSummaryInterval = 300;
constexpr size_t kSignatureCapacity = 4096;
constexpr size_t kSummaryLimit = 16;
constexpr size_t kCandidateSummaryLimit = 32;
constexpr size_t kPreparedShaderPairCapacity = 1024;
constexpr size_t kCommandBufferLineageCapacity = 4096;
constexpr size_t kResolveTargetCapacity = 4096;
constexpr size_t kResolvePageCapacity = 32768;
constexpr size_t kResolveSummaryLimit = 32;
constexpr size_t kPassConsumerDetailLimit = 64;
constexpr size_t kPassConsumerSignatureCapacity = 1024;
constexpr size_t kGuestCpuVisibilityTargetCapacity = 64;
constexpr uint64_t kGuestPageSize = 4096;
constexpr uint64_t kPhysicalApertureSize = UINT64_C(0x20000000);
constexpr uint32_t kVertexIndexMask = 0x00FFFFFF;
constexpr uint32_t kMaximumIndexScanCount = 1 << 20;
constexpr uint64_t kMaximumIndexScanBytes = UINT64_C(4) << 20;
constexpr uint32_t kMaximumTextureScanResources = 4;
constexpr uint64_t kMaximumTextureScanResourceBytes = UINT64_C(16) << 20;
constexpr uint64_t kMaximumTextureScanTotalBytes = UINT64_C(32) << 20;
constexpr uint32_t kMaximumConsumerReadbackSamples = 16;
constexpr uint64_t kPassPublicationDetailLimit = 64;
constexpr uint64_t kSuppressionWarmupFrameCount = 8;
constexpr uint64_t kSuppressionFailureCooldownFrameCount = 120;
constexpr uint64_t kSuppressionStateDetailLimit = 32;
constexpr size_t kDispatchCallerCapacity = 256;
constexpr size_t kTitlePacketProvenanceCapacity = 16384;
constexpr size_t kTitleDrawProvenanceCapacity = 4096;
constexpr size_t kTitleOriginStackCapacity = 32;
constexpr size_t kTitleIndirectPacketBucketCount = 4096;
constexpr size_t kTitleIndirectPacketWays = 4;
constexpr size_t kTitleIndirectPacketCapacity =
    kTitleIndirectPacketBucketCount * kTitleIndirectPacketWays;
constexpr size_t kTitleIndirectStackCapacity = 32;
constexpr size_t kIndirectConstructorStackCapacity = 32;
constexpr size_t kIndirectOwnerStackCapacity = 32;
constexpr size_t kIndirectProducerStackCapacity = 32;
constexpr size_t kIndirectContextStackCapacity = 32;
constexpr size_t kSemanticReceiverLifecycleCapacity = 1024;
constexpr size_t kSemanticReceiverStackCapacity = 32;
constexpr size_t kSemanticVisibilityCategoryCapacity = 32;
constexpr size_t kSemanticVisibilityLodCapacity = 32;
constexpr size_t kSemanticVisibilityResultValueCapacity = 256;
constexpr size_t kSemanticVisibilityPolicyOutcomeCapacity = 3;
constexpr size_t kSemanticVisibilitySpatialExponentCapacity = 256;
constexpr size_t kSemanticVisibilityWorksetCapacity = 4096;
constexpr size_t kSemanticVisibilityPreparedCandidateCapacity = 4096;
constexpr uint64_t kSemanticVisibilityMaximumPolicyAgeFrames = 1;
constexpr size_t kSemanticInstanceCapacity = 4096;
constexpr size_t kSemanticSubmissionCapacity = 8192;
constexpr size_t kSemanticRenderItemStackCapacity = 32;
constexpr size_t kSemanticPreparedTemplateCapacity =
    kTitleDrawProvenanceCapacity;
constexpr size_t kSemanticBatchOpportunityCapacity =
    kTitleDrawProvenanceCapacity;
constexpr size_t kSemanticStateCacheWays = 4;
constexpr size_t kSemanticStateCacheCompactBucketCount = 16;
constexpr size_t kSemanticStateCacheBalancedBucketCount = 64;
constexpr size_t kSemanticStateCacheHeadroomBucketCount = 256;
constexpr size_t kSemanticStateCacheMaximumCapacity =
    kSemanticStateCacheHeadroomBucketCount * kSemanticStateCacheWays;
constexpr uint64_t kSemanticBatchMaximumParameterPayloadBytes =
    2 * rex::system::kGraphicsFloatConstantObservationLimit *
        5 * sizeof(uint32_t) +
    8 * 2 * sizeof(uint32_t) + sizeof(uint32_t) +
    32 * sizeof(uint32_t);
constexpr size_t kSemanticDescriptorWordCount = 92 / sizeof(uint32_t);
constexpr size_t kSemanticRuntimeWordCount = 68 / sizeof(uint32_t);
constexpr size_t kSemanticTransformWordCount = 192 / sizeof(uint32_t);
constexpr uint64_t kSemanticObservationPayloadBytes = 380;
constexpr uint64_t kSemanticSubmissionMaximumPayloadBytes = 64;
constexpr uint32_t kResourceBindingKeyCacheAddress = 0x834AD4CC;
constexpr uint64_t kSkyHorizonAnchorSignature = UINT64_C(0x747837906D0BF484);
constexpr uint64_t kSkyHorizonFollowerSignature = UINT64_C(0x1D253A52B55C9FB3);
std::atomic<uint64_t> g_frame_sequence{};

enum class DispatchWrapper : uint32_t {
  kDrawIndexed = 1,
  kDrawImmediate = 2,
  kDrawAdapter = 3,
  kVizQueryBegin = 4,
  kVizQueryEnd = 5,
  kResolveController = 6,
  kResolveSetup = 7,
  kVizQueryOwner = 8,
  kBinningScissorState = 9,
  kBinningStateReset = 10,
  kProceduralModelDrawIndexed = 11,
};

struct DispatchCallerEntry {
  std::atomic<uint64_t> key{};
  std::atomic<uint64_t> calls{};
  std::atomic<uint64_t> first_frame{};
  std::atomic<uint32_t> first_r3{};
  std::atomic<uint32_t> first_r4{};
  std::atomic<uint32_t> first_r5{};
  std::atomic<uint32_t> first_r6{};
  std::atomic<uint32_t> first_r7{};
  std::atomic<uint32_t> first_r8{};
  std::atomic<uint32_t> first_r9{};
  std::atomic<uint32_t> first_r10{};
};

std::array<DispatchCallerEntry, kDispatchCallerCapacity> g_dispatch_callers;
std::atomic<uint64_t> g_dispatch_caller_overflow{};
std::atomic<bool> g_dispatch_discovery_installed{};

enum class SemanticVisibilityWorksetJoin : uint32_t {
  kMissing = 0,
  kSelected = 1,
  kRejected = 2,
};

struct SemanticDrawIdentity {
  uint64_t submission_key = 0;
  uint64_t visibility_policy_frame = 0;
  uint32_t receiver_address = 0;
  uint32_t receiver_generation = 0;
  uint32_t record_index = 0;
  uint32_t descriptor_address = 0;
  uint32_t runtime_address = 0;
  uint32_t descriptor_kind = 0;
  uint32_t helper_state = 0;
  uint32_t primary_resource_key = 0;
  uint32_t secondary_resource_key = 0;
  uint32_t visibility_category = 0;
  uint32_t visibility_result_mask = 0;
  uint32_t title_lod_index = 0;
  uint32_t direct_title_origins = 0;
  uint32_t indirect_packet_origins = 0;
  SemanticVisibilityWorksetJoin visibility_workset_join =
      SemanticVisibilityWorksetJoin::kMissing;
  bool secondary_resource_present = false;
  bool title_lod_valid = false;
  bool valid = false;
};

struct TitleDrawOrigin {
  DispatchWrapper wrapper = DispatchWrapper::kDrawIndexed;
  uint32_t caller = 0;
  std::array<uint32_t, 8> arguments{};
  SemanticDrawIdentity semantic_draw{};
  bool valid = false;
};

struct TitlePacketProvenanceEntry {
  uint32_t packet_physical_address = 0;
  uint64_t submission_sequence = 0;
  TitleDrawOrigin origin{};
  bool ever_used = false;
  bool occupied = false;
};

struct SemanticPreparedDrawContract {
  uint64_t template_key = 0;
  uint64_t batch_pipeline_key = 0;
  uint64_t draw_argument_hash = 0;
  uint64_t prepared_pipeline_hash = 0;
  uint64_t geometry_layout_hash = 0;
  uint64_t texture_layout_hash = 0;
  uint64_t batch_geometry_layout_hash = 0;
  uint64_t batch_texture_layout_hash = 0;
  uint64_t render_state_hash = 0;
  uint64_t geometry_resource_hash = 0;
  uint64_t texture_resource_hash = 0;
  uint64_t render_target_resource_hash = 0;
  uint64_t vertex_shader_hash = 0;
  uint64_t pixel_shader_hash = 0;
  uint64_t vertex_specialization_mask = 0;
  uint64_t pixel_specialization_mask = 0;
  uint64_t template_variations = 0;
  uint64_t resource_variations = 0;
  uint32_t primitive_type = 0;
  uint32_t source_select = 0;
  uint32_t minimum_index_count = 0;
  uint32_t maximum_index_count = 0;
  uint32_t index_buffer_address = 0;
  uint32_t index_buffer_length = 0;
  uint32_t index_format = 0;
  uint32_t index_endianness = 0;
  uint32_t vertex_binding_count = 0;
  uint32_t vertex_attribute_count = 0;
  uint32_t first_vertex_address = 0;
  uint32_t first_vertex_size = 0;
  uint32_t first_vertex_stride_words = 0;
  uint32_t first_vertex_endianness = 0;
  uint32_t texture_fetch_mask = 0;
  uint32_t texture_layout_valid_mask = 0;
  uint32_t texture_state_count = 0;
  bool indexed = false;
  bool geometry_bounded = false;
  bool texture_layout_bounded = false;
  bool valid = false;
};

enum class SemanticBatchRejection : uint32_t {
  kNone = 0,
  kMissingTitleResource = 1,
  kNonOpaque = 2,
  kResolvedInput = 3,
  kQueryOrConditional = 4,
  kMemexport = 5,
  kUnboundedGeometry = 6,
  kUnsupportedGeometry = 7,
  kConstantOverflow = 8,
  kUnboundedTextureLayout = 9,
  kTextureCount = 10,
  kIncompletePreparedPipeline = 11,
  kRenderTargetCoverage = 12,
  kCount = 13,
};

struct SemanticBatchOpportunityEntry {
  uint64_t key = 0;
  uint64_t template_key = 0;
  uint64_t geometry_resource_hash = 0;
  uint64_t texture_resource_hash = 0;
  uint64_t draws = 0;
  uint64_t frames = 0;
  uint64_t first_frame = 0;
  uint64_t last_frame = 0;
  uint64_t consecutive_runs = 0;
  uint64_t multi_draw_runs = 0;
  uint64_t multi_draw_draws = 0;
  uint64_t maximum_run_length = 0;
  uint64_t instance_switches = 0;
  uint64_t same_instance_continuations = 0;
  uint32_t primary_resource_key = 0;
  uint32_t secondary_resource_key = 0;
  SemanticBatchRejection rejection = SemanticBatchRejection::kNone;
  bool secondary_resource_present = false;
};

struct SemanticVisibilityPreparedCandidateEntry {
  uint64_t key = 0;
  uint64_t prepared_signature = 0;
  uint64_t template_key = 0;
  uint64_t geometry_resource_hash = 0;
  uint64_t texture_resource_hash = 0;
  uint64_t draws = 0;
  uint64_t first_frame = 0;
  uint64_t last_frame = 0;
  uint64_t maximum_policy_age_frames = 0;
  uint64_t vertex_shader_hash = 0;
  uint64_t pixel_shader_hash = 0;
  uint64_t vertex_specialization_mask = 0;
  uint64_t pixel_specialization_mask = 0;
  uint32_t receiver_address = 0;
  uint32_t receiver_generation = 0;
  uint32_t record_index = 0;
  uint32_t visibility_category = 0;
  uint32_t visibility_result_mask = 0;
  uint32_t title_lod_index = 0;
  uint32_t mechanical_rejection_mask = 0;
  bool mechanically_eligible = false;
  bool title_lod_valid = false;
};

struct SemanticBatchRun {
  uint64_t key = 0;
  uint64_t frame = 0;
  uint64_t length = 0;
  size_t opportunity_index = 0;
  uint32_t receiver_address = 0;
  uint32_t receiver_generation = 0;
  uint32_t record_index = 0;
  bool valid = false;
};

enum class SemanticBatchEquivalence : uint32_t {
  kMeshMaterial = 0,
  kMaterial = 1,
  kPipeline = 2,
  kCount = 3,
};

struct SemanticBatchEquivalenceEntry {
  uint64_t key = 0;
  uint64_t pipeline_key = 0;
  uint64_t draw_argument_hash = 0;
  uint64_t geometry_resource_hash = 0;
  uint64_t texture_resource_hash = 0;
  uint64_t render_target_resource_hash = 0;
  uint64_t draws = 0;
  uint64_t frames = 0;
  uint64_t first_frame = 0;
  uint64_t last_frame = 0;
  uint64_t consecutive_runs = 0;
  uint64_t multi_draw_runs = 0;
  uint64_t multi_draw_draws = 0;
  uint64_t maximum_run_length = 0;
  uint64_t instance_switches = 0;
  uint64_t same_instance_continuations = 0;
  uint64_t parameter_switches = 0;
  uint64_t same_parameter_continuations = 0;
};

struct SemanticBatchEquivalenceRun {
  uint64_t key = 0;
  uint64_t frame = 0;
  uint64_t length = 0;
  uint64_t parameter_hash = 0;
  size_t opportunity_index = 0;
  uint32_t receiver_address = 0;
  uint32_t receiver_generation = 0;
  uint32_t record_index = 0;
  bool valid = false;
};

enum class SemanticStateCacheLevel : uint32_t {
  kMaterial = 0,
  kPipeline = 1,
  kCount = 2,
};

enum class SemanticStateCacheProfile : uint32_t {
  kCompact = 0,
  kBalanced = 1,
  kHeadroom = 2,
  kCount = 3,
};

struct SemanticStateCacheEntry {
  uint64_t key = 0;
  uint64_t last_use_sequence = 0;
  uint64_t last_frame = 0;
};

struct SemanticStateCacheStats {
  uint64_t lookups = 0;
  uint64_t hits = 0;
  uint64_t misses = 0;
  uint64_t evictions = 0;
  uint64_t full_bucket_misses = 0;
  uint64_t consecutive_hits = 0;
  uint64_t nonconsecutive_same_frame_hits = 0;
  uint64_t cross_frame_hits = 0;
  uint64_t resident_entries = 0;
  uint64_t maximum_resident_entries = 0;
  uint64_t use_sequence = 0;
  uint64_t previous_key = 0;
  uint64_t previous_frame = 0;
  bool previous_valid = false;
};

struct TitleDrawProvenanceEntry {
  uint64_t backend_signature = 0;
  uint32_t backend_outcome = 0;
  uint64_t calls = 0;
  uint64_t first_frame = 0;
  uint64_t last_frame = 0;
  uint64_t first_draw = 0;
  uint32_t first_packet_physical_address = 0;
  TitleDrawOrigin origin{};
  std::array<uint32_t, 8> last_arguments{};
  std::array<uint32_t, 8> minimum_arguments{};
  std::array<uint32_t, 8> maximum_arguments{};
  uint32_t varying_argument_mask = 0;
  SemanticPreparedDrawContract semantic_contract{};
  bool prepared = false;
};

struct TitleIndirectPacketEntry {
  uint32_t packet_physical_address = UINT32_MAX;
  uint32_t constructor_store_address = 0;
  uint32_t constructor_function_address = 0;
  uint32_t constructor_return_address = 0;
  std::array<uint32_t, 8> constructor_arguments{};
  uint32_t owner_function_address = 0;
  uint32_t owner_return_address = 0;
  std::array<uint32_t, 8> owner_arguments{};
  uint32_t producer_function_address = 0;
  uint32_t producer_return_address = 0;
  std::array<uint32_t, 8> producer_arguments{};
  uint32_t context_function_address = 0;
  uint32_t context_return_address = 0;
  std::array<uint32_t, 8> context_arguments{};
  uint32_t context_root_address = 0;
  uint32_t semantic_receiver_address = 0;
  uint32_t semantic_receiver_generation = 0;
  uint64_t semantic_visibility_epoch = 0;
  uint64_t semantic_render_state_epoch = 0;
  uint64_t semantic_render_state_visibility_epoch = 0;
  uint64_t submission_sequence = 0;
  bool constructor_origin_known = false;
  bool owner_origin_known = false;
  bool producer_origin_known = false;
  bool context_origin_known = false;
  bool semantic_receiver_known = false;
  bool occupied = false;
};

struct IndirectConstructorOrigin {
  struct Owner {
    struct Producer {
      struct Context {
        uint32_t function_address = 0;
        uint32_t return_address = 0;
        std::array<uint32_t, 8> arguments{};
        uint32_t root_address = 0;
        uint32_t semantic_receiver_address = 0;
        uint32_t semantic_receiver_generation = 0;
        uint64_t semantic_visibility_epoch = 0;
        uint64_t semantic_render_state_epoch = 0;
        uint64_t semantic_render_state_visibility_epoch = 0;
        bool semantic_receiver_known = false;
        bool valid = false;
      } context{};
      uint32_t function_address = 0;
      uint32_t return_address = 0;
      std::array<uint32_t, 8> arguments{};
      bool valid = false;
    } producer{};
    uint32_t function_address = 0;
    uint32_t return_address = 0;
    std::array<uint32_t, 8> arguments{};
    bool valid = false;
  } owner{};
  uint32_t function_address = 0;
  uint32_t return_address = 0;
  std::array<uint32_t, 8> arguments{};
  bool valid = false;
};

struct ActiveTitleIndirectBuffer {
  uint32_t packet_physical_address = UINT32_MAX;
  uint32_t target_buffer_physical_address = UINT32_MAX;
  uint32_t parent_packet_physical_address = UINT32_MAX;
  uint32_t root_buffer_physical_address = UINT32_MAX;
  uint32_t constructor_store_address = 0;
  IndirectConstructorOrigin constructor_origin{};
  uint32_t depth = 0;
};

std::array<TitlePacketProvenanceEntry, kTitlePacketProvenanceCapacity>
    g_title_packet_provenance{};
std::array<TitleDrawProvenanceEntry, kTitleDrawProvenanceCapacity>
    g_title_draw_provenance{};
std::array<SemanticBatchOpportunityEntry,
           kSemanticBatchOpportunityCapacity>
    g_semantic_batch_opportunities{};
std::array<SemanticVisibilityPreparedCandidateEntry,
           kSemanticVisibilityPreparedCandidateCapacity>
    g_semantic_visibility_prepared_candidates{};
std::array<std::array<SemanticBatchEquivalenceEntry,
                      kSemanticBatchOpportunityCapacity>,
           size_t(SemanticBatchEquivalence::kCount)>
    g_semantic_batch_equivalence_opportunities{};
std::array<std::array<std::array<SemanticStateCacheEntry,
                                 kSemanticStateCacheMaximumCapacity>,
                      size_t(SemanticStateCacheProfile::kCount)>,
           size_t(SemanticStateCacheLevel::kCount)>
    g_semantic_state_caches{};
std::array<std::array<SemanticStateCacheStats,
                      size_t(SemanticStateCacheProfile::kCount)>,
           size_t(SemanticStateCacheLevel::kCount)>
    g_semantic_state_cache_stats{};
std::array<TitleIndirectPacketEntry, kTitleIndirectPacketCapacity>
    g_title_indirect_packets{};
std::mutex g_title_packet_provenance_mutex;
std::atomic<bool> g_title_provenance_installed{};
std::atomic<rex::memory::Memory *> g_title_provenance_memory{};
std::atomic<bool> g_command_buffer_lineage_installed{};
std::atomic<rex::memory::Memory *> g_command_buffer_lineage_memory{};
uint64_t g_title_packets_recorded = 0;
uint64_t g_title_packets_matched = 0;
uint64_t g_title_packet_address_failures = 0;
uint64_t g_title_packet_reused_live_addresses = 0;
uint64_t g_title_packet_table_overflow = 0;
uint64_t g_title_backend_unattributed_draws = 0;
uint64_t g_title_matched_unprepared_draws = 0;
uint64_t g_backend_draw_outcomes_observed = 0;
uint64_t g_backend_draw_outcome_mismatches = 0;
uint64_t g_backend_draw_outcome_missing = 0;
std::array<uint64_t, 19> g_backend_draw_outcome_counts{};
std::array<uint64_t, 19> g_title_backend_outcome_counts{};
std::atomic<uint64_t> g_title_forwarding_mismatches{};
std::atomic<uint64_t> g_title_origins_pushed{};
std::atomic<uint64_t> g_title_origins_consumed{};
std::atomic<uint64_t> g_title_origin_stack_overflow{};
std::atomic<uint64_t> g_title_packets_without_origin{};
uint64_t g_title_draw_provenance_count = 0;
uint64_t g_title_draw_provenance_overflow = 0;
uint64_t g_semantic_batch_observations = 0;
uint64_t g_semantic_visibility_prepared_observations = 0;
uint64_t g_semantic_visibility_prepared_selected_joins = 0;
uint64_t g_semantic_visibility_prepared_fresh_candidates = 0;
uint64_t g_semantic_visibility_prepared_stale_exclusions = 0;
uint64_t g_semantic_visibility_prepared_future_exclusions = 0;
uint64_t g_semantic_visibility_prepared_rejected_exclusions = 0;
uint64_t g_semantic_visibility_prepared_missing_exclusions = 0;
uint64_t g_semantic_visibility_prepared_candidate_count = 0;
uint64_t g_semantic_visibility_prepared_candidate_overflow = 0;
uint64_t g_semantic_batch_eligible_draws = 0;
uint64_t g_semantic_batch_rejected_draws = 0;
uint64_t g_semantic_batch_opportunity_count = 0;
uint64_t g_semantic_batch_opportunity_overflow = 0;
uint64_t g_semantic_batch_consecutive_runs = 0;
uint64_t g_semantic_batch_multi_draw_runs = 0;
uint64_t g_semantic_batch_multi_draw_draws = 0;
uint64_t g_semantic_batch_maximum_run_length = 0;
uint64_t g_semantic_batch_instance_switches = 0;
uint64_t g_semantic_batch_same_instance_continuations = 0;
uint64_t g_semantic_batch_frame_count = 0;
uint64_t g_semantic_batch_current_frame = 0;
uint64_t g_semantic_batch_current_frame_draws = 0;
uint64_t g_semantic_batch_maximum_draws_per_frame = 0;
uint64_t g_semantic_batch_template_transitions = 0;
uint64_t g_semantic_batch_geometry_transitions = 0;
uint64_t g_semantic_batch_texture_transitions = 0;
uint64_t g_semantic_batch_title_resource_transitions = 0;
std::array<uint64_t, size_t(SemanticBatchRejection::kCount)>
    g_semantic_batch_rejections{};
SemanticBatchRun g_semantic_batch_run{};
SemanticPreparedDrawContract g_semantic_batch_previous_contract{};
SemanticDrawIdentity g_semantic_batch_previous_identity{};
uint64_t g_semantic_batch_previous_frame = 0;
bool g_semantic_batch_previous_eligible = false;
uint64_t g_semantic_batch_parameter_payload_bytes = 0;
uint64_t g_semantic_batch_maximum_parameter_payload_bytes = 0;
std::array<uint64_t, size_t(SemanticBatchEquivalence::kCount)>
    g_semantic_batch_equivalence_counts{};
std::array<uint64_t, size_t(SemanticBatchEquivalence::kCount)>
    g_semantic_batch_equivalence_overflows{};
std::array<SemanticBatchEquivalenceRun,
           size_t(SemanticBatchEquivalence::kCount)>
    g_semantic_batch_equivalence_runs{};
uint64_t g_title_packet_submission_sequence = 0;
uint64_t g_title_indirect_packets_recorded = 0;
uint64_t g_title_indirect_packet_address_failures = 0;
uint64_t g_title_indirect_packet_table_overflow = 0;
uint64_t g_title_indirect_packet_evictions = 0;
uint64_t g_title_indirect_packet_submission_sequence = 0;
uint64_t g_title_indirect_buffer_enters = 0;
uint64_t g_title_indirect_buffer_exits = 0;
uint64_t g_title_indirect_buffer_matches = 0;
uint64_t g_title_indirect_buffer_unmatched = 0;
uint64_t g_title_indirect_stack_faults = 0;
uint64_t g_title_indirect_draw_stack_faults = 0;
std::atomic<uint64_t> g_indirect_constructor_entries{};
std::atomic<uint64_t> g_indirect_constructor_exits{};
std::atomic<uint64_t> g_indirect_constructor_stack_faults{};
std::atomic<uint64_t> g_indirect_packets_without_constructor_origin{};
std::atomic<uint64_t> g_indirect_owner_entries{};
std::atomic<uint64_t> g_indirect_owner_exits{};
std::atomic<uint64_t> g_indirect_owner_stack_faults{};
std::atomic<uint64_t> g_indirect_constructors_without_owner_origin{};
std::atomic<uint64_t> g_indirect_constructor_owner_mismatches{};
std::atomic<uint64_t> g_indirect_producer_entries{};
std::atomic<uint64_t> g_indirect_producer_exits{};
std::atomic<uint64_t> g_indirect_producer_stack_faults{};
std::atomic<uint64_t> g_indirect_owners_without_producer_origin{};
std::atomic<uint64_t> g_indirect_owner_producer_mismatches{};
std::atomic<uint64_t> g_indirect_context_entries{};
std::atomic<uint64_t> g_indirect_context_exits{};
std::atomic<uint64_t> g_indirect_context_stack_faults{};
std::atomic<uint64_t> g_indirect_producers_without_context_origin{};
std::atomic<uint64_t> g_indirect_producer_context_mismatches{};
std::atomic<uint64_t> g_title_indirect_buffers_open{};
std::atomic<uint64_t> g_indirect_constructor_invocations_open{};
std::atomic<uint64_t> g_indirect_owner_invocations_open{};
std::atomic<uint64_t> g_indirect_producer_invocations_open{};
std::atomic<uint64_t> g_indirect_context_invocations_open{};
enum class SemanticReceiverState : uint32_t {
  kEmpty = 0,
  kLive = 1,
  kDestroying = 2,
  kDestroyed = 3,
};

struct SemanticReceiverLifecycleEntry {
  std::atomic<uint32_t> address{};
  std::atomic<uint32_t> generation{};
  std::atomic<uint32_t> state{};
  std::atomic<uint64_t> dispatches{};
  std::atomic<uint64_t> visibility_preparations{};
  std::atomic<uint64_t> render_state_preparations{};
  std::atomic<uint64_t> visibility_epoch{};
  std::atomic<uint64_t> render_state_epoch{};
  std::atomic<uint64_t> render_state_visibility_epoch{};
  // Legacy event field names retained for capture compatibility. These count
  // whether both optional observed stages had history before a dispatch; they
  // are not a universal slot-41 readiness predicate.
  std::atomic<uint64_t> dispatches_with_preparation{};
  std::atomic<uint64_t> dispatches_without_preparation{};
  std::atomic<uint64_t> dispatches_without_visibility{};
  std::atomic<uint64_t> dispatches_without_render_state{};
};

std::array<SemanticReceiverLifecycleEntry,
           kSemanticReceiverLifecycleCapacity>
    g_semantic_receiver_lifecycles{};
std::atomic<uint64_t> g_semantic_receiver_constructor_entries{};
std::atomic<uint64_t> g_semantic_receiver_constructor_exits{};
std::atomic<uint64_t> g_semantic_receiver_constructor_open{};
std::atomic<uint64_t> g_semantic_receiver_destructor_entries{};
std::atomic<uint64_t> g_semantic_receiver_destructor_exits{};
std::atomic<uint64_t> g_semantic_receiver_destructor_open{};
std::atomic<uint64_t> g_semantic_receiver_stack_faults{};
std::atomic<uint64_t> g_semantic_receiver_instances_published{};
std::atomic<uint64_t> g_semantic_receiver_instances_destroyed{};
std::atomic<uint64_t> g_semantic_receiver_address_reuses{};
std::atomic<uint64_t> g_semantic_receiver_table_overflow{};
std::atomic<uint64_t> g_semantic_receiver_dispatches{};
std::atomic<uint64_t> g_semantic_receiver_live_dispatches{};
std::atomic<uint64_t> g_semantic_receiver_unregistered_dispatches{};
std::atomic<uint64_t> g_semantic_receiver_destroying_dispatches{};
std::atomic<uint64_t> g_semantic_receiver_destroyed_dispatches{};
std::atomic<uint64_t> g_semantic_receiver_destructors_without_instance{};
std::atomic<uint64_t> g_semantic_visibility_entries{};
std::atomic<uint64_t> g_semantic_visibility_exits{};
std::atomic<uint64_t> g_semantic_visibility_open{};
std::atomic<uint64_t> g_semantic_render_state_entries{};
std::atomic<uint64_t> g_semantic_render_state_exits{};
std::atomic<uint64_t> g_semantic_render_state_open{};
std::atomic<uint64_t> g_semantic_stage_stack_faults{};
std::atomic<uint64_t> g_semantic_stage_unknown_receivers{};

struct SemanticVisibilityCategoryStats {
  std::atomic<uint64_t> entries{};
  std::atomic<uint64_t> completions{};
  std::atomic<uint64_t> selected{};
  std::atomic<uint64_t> rejected{};
  std::atomic<uint64_t> early_rejected{};
  std::atomic<uint64_t> lod_writes{};
};

enum class SemanticVisibilityPolicyOutcome : size_t {
  kEarlyRejected,
  kRejected,
  kSelected,
};

struct SemanticVisibilityPolicyStats {
  std::atomic<uint64_t> records{};
  std::atomic<uint64_t> spatial_samples{};
  std::atomic<uint64_t> runtime_threshold_observations{};
  std::atomic<uint64_t> runtime_distance_less{};
  std::atomic<uint64_t> descriptor_threshold_observations{};
  std::atomic<uint64_t> descriptor_distance_exceeded{};
};

struct SemanticVisibilityOracleStats {
  std::atomic<uint64_t> records{};
  std::atomic<uint64_t> candidate_threshold_observations{};
  std::atomic<uint64_t> candidate_threshold_passes{};
  std::atomic<uint64_t> local_distance_observations{};
  std::atomic<uint64_t> local_distance_passes{};
  std::atomic<uint64_t> spatial_helper_observations{};
  std::atomic<uint64_t> spatial_helper_passes{};
  std::atomic<uint64_t> category_helper_observations{};
  std::array<std::atomic<uint64_t>, 3> category_results{};
};

struct SemanticVisibilityShadowStats {
  std::atomic<uint64_t> modelled_records{};
  std::atomic<uint64_t> predicted_selected{};
  std::atomic<uint64_t> predicted_rejected{};
  std::atomic<uint64_t> title_matches{};
  std::atomic<uint64_t> false_positive{};
  std::atomic<uint64_t> false_negative{};
  std::atomic<uint64_t> result_1_records{};
  std::atomic<uint64_t> result_2_records{};
  std::atomic<uint64_t> mixed_nonzero_records{};
};

struct SemanticVisibilitySpatialShadowStats {
  std::atomic<uint64_t> input_observations{};
  std::atomic<uint64_t> comparisons{};
  std::atomic<uint64_t> matches{};
  std::atomic<uint64_t> false_positive{};
  std::atomic<uint64_t> false_negative{};
  std::atomic<uint64_t> invalid_inputs{};
};

struct SemanticVisibilityCategoryShadowStats {
  std::atomic<uint64_t> input_observations{};
  std::atomic<uint64_t> comparisons{};
  std::atomic<uint64_t> matches{};
  std::atomic<uint64_t> false_result{};
  std::atomic<uint64_t> invalid_inputs{};
};

struct SemanticVisibilityAssemblyShadowStats {
  std::atomic<uint64_t> records{};
  std::atomic<uint64_t> modelled_records{};
  std::atomic<uint64_t> predicted_selected{};
  std::atomic<uint64_t> predicted_rejected{};
  std::atomic<uint64_t> title_matches{};
  std::atomic<uint64_t> false_positive{};
  std::atomic<uint64_t> false_negative{};
  std::atomic<uint64_t> spatial_input_observations{};
  std::atomic<uint64_t> spatial_predicted_passes{};
  std::atomic<uint64_t> category_input_observations{};
  std::array<std::atomic<uint64_t>, 3> category_predictions{};
  std::atomic<uint64_t> invalid_inputs{};
};

struct SemanticVisibilityWorksetEntry {
  uint64_t key = 0;
  uint64_t observations = 0;
  uint64_t first_frame = 0;
  uint64_t last_frame = 0;
  uint64_t predicted_selected = 0;
  uint64_t predicted_rejected = 0;
  uint64_t title_matches = 0;
  uint64_t title_mismatches = 0;
  uint64_t semantic_instance_joins = 0;
  uint64_t title_lod_observations = 0;
  uint32_t receiver_address = 0;
  uint32_t receiver_generation = 0;
  uint32_t record_index = 0;
  uint32_t category = 0;
  uint32_t latest_category_result_mask = 0;
  uint32_t latest_title_lod_index = 0;
  bool latest_selected = false;
  bool latest_title_lod_valid = false;
};

std::atomic<uint64_t> g_semantic_visibility_record_entries{};
std::atomic<uint64_t> g_semantic_visibility_record_completions{};
std::atomic<uint64_t> g_semantic_visibility_records_open{};
std::atomic<uint64_t> g_semantic_visibility_result_observations{};
std::atomic<uint64_t> g_semantic_visibility_selected_records{};
std::atomic<uint64_t> g_semantic_visibility_rejected_records{};
std::atomic<uint64_t> g_semantic_visibility_early_rejected_records{};
std::atomic<uint64_t> g_semantic_visibility_lod_writes{};
std::atomic<uint64_t> g_semantic_visibility_selected_with_lod{};
std::atomic<uint64_t> g_semantic_visibility_selected_without_lod{};
std::atomic<uint64_t> g_semantic_visibility_record_stack_faults{};
std::atomic<uint64_t> g_semantic_visibility_entry_overlaps{};
std::atomic<uint64_t> g_semantic_visibility_lod_without_record{};
std::atomic<uint64_t> g_semantic_visibility_lod_rewrites{};
std::atomic<uint64_t> g_semantic_visibility_result_without_record{};
std::atomic<uint64_t> g_semantic_visibility_duplicate_result{};
std::atomic<uint64_t> g_semantic_visibility_completion_without_record{};
std::atomic<uint64_t> g_semantic_visibility_exit_with_record{};
std::atomic<uint64_t> g_semantic_visibility_record_identity_mismatches{};
std::atomic<uint64_t> g_semantic_visibility_record_unknown_receivers{};
std::atomic<uint64_t> g_semantic_visibility_category_overflow{};
std::atomic<uint64_t> g_semantic_visibility_lod_overflow{};
std::array<SemanticVisibilityCategoryStats,
           kSemanticVisibilityCategoryCapacity>
    g_semantic_visibility_categories{};
std::array<std::atomic<uint64_t>, kSemanticVisibilityLodCapacity>
    g_semantic_visibility_lod_histogram{};
std::array<std::atomic<uint64_t>, kSemanticVisibilityResultValueCapacity>
    g_semantic_visibility_result_value_histogram{};
std::array<std::array<SemanticVisibilityPolicyStats,
                      kSemanticVisibilityPolicyOutcomeCapacity>,
           kSemanticVisibilityCategoryCapacity>
    g_semantic_visibility_policy_categories{};
std::array<std::array<std::atomic<uint64_t>,
                      kSemanticVisibilitySpatialExponentCapacity>,
           kSemanticVisibilityPolicyOutcomeCapacity>
    g_semantic_visibility_spatial_exponents{};
std::atomic<uint64_t> g_semantic_visibility_policy_invalid_spatial_values{};
std::atomic<uint64_t> g_semantic_visibility_policy_invalid_threshold_values{};
std::atomic<uint64_t> g_semantic_visibility_policy_hook_faults{};
std::atomic<uint64_t> g_semantic_visibility_runtime_threshold_without_record{};
std::atomic<uint64_t> g_semantic_visibility_duplicate_runtime_threshold{};
std::atomic<uint64_t> g_semantic_visibility_descriptor_threshold_without_record{};
std::atomic<uint64_t> g_semantic_visibility_duplicate_descriptor_threshold{};
std::array<std::array<SemanticVisibilityOracleStats,
                      kSemanticVisibilityPolicyOutcomeCapacity>,
           kSemanticVisibilityCategoryCapacity>
    g_semantic_visibility_oracle_categories{};
std::atomic<uint64_t> g_semantic_visibility_spatial_helper_without_record{};
std::atomic<uint64_t> g_semantic_visibility_candidate_threshold_without_record{};
std::atomic<uint64_t> g_semantic_visibility_local_distance_without_record{};
std::atomic<uint64_t> g_semantic_visibility_local_distance_without_candidate_pass{};
std::atomic<uint64_t> g_semantic_visibility_oracle_invalid_values{};
std::atomic<uint64_t> g_semantic_visibility_spatial_helper_without_local_pass{};
std::atomic<uint64_t> g_semantic_visibility_category_helper_without_record{};
std::atomic<uint64_t> g_semantic_visibility_category_helper_without_spatial_pass{};
std::atomic<uint64_t> g_semantic_visibility_category_helper_invalid_result{};
std::array<std::array<SemanticVisibilityShadowStats,
                      kSemanticVisibilityPolicyOutcomeCapacity>,
           kSemanticVisibilityCategoryCapacity>
    g_semantic_visibility_shadow_categories{};
std::array<std::array<SemanticVisibilitySpatialShadowStats,
                      kSemanticVisibilityPolicyOutcomeCapacity>,
           kSemanticVisibilityCategoryCapacity>
    g_semantic_visibility_spatial_shadow_categories{};
std::atomic<uint64_t> g_semantic_visibility_spatial_shadow_input_without_record{};
std::atomic<uint64_t> g_semantic_visibility_spatial_shadow_result_without_input{};
std::array<std::array<SemanticVisibilityCategoryShadowStats,
                      kSemanticVisibilityPolicyOutcomeCapacity>,
           kSemanticVisibilityCategoryCapacity>
    g_semantic_visibility_category_shadow_categories{};
std::atomic<uint64_t> g_semantic_visibility_category_shadow_input_without_record{};
std::atomic<uint64_t> g_semantic_visibility_category_shadow_result_without_input{};
std::array<std::array<SemanticVisibilityAssemblyShadowStats,
                      kSemanticVisibilityPolicyOutcomeCapacity>,
           kSemanticVisibilityCategoryCapacity>
    g_semantic_visibility_assembly_shadow_categories{};
std::array<SemanticVisibilityWorksetEntry,
           kSemanticVisibilityWorksetCapacity>
    g_semantic_visibility_workset{};
std::mutex g_semantic_visibility_workset_mutex;
uint64_t g_semantic_visibility_workset_modelled_records = 0;
uint64_t g_semantic_visibility_workset_predicted_selected = 0;
uint64_t g_semantic_visibility_workset_predicted_rejected = 0;
uint64_t g_semantic_visibility_workset_title_matches = 0;
uint64_t g_semantic_visibility_workset_title_mismatches = 0;
uint64_t g_semantic_visibility_workset_title_lod_records = 0;
uint64_t g_semantic_visibility_workset_invalid_records = 0;
uint64_t g_semantic_visibility_workset_entries = 0;
uint64_t g_semantic_visibility_workset_overflow = 0;
uint64_t g_semantic_visibility_workset_semantic_instance_lookups = 0;
uint64_t g_semantic_visibility_workset_selected_joins = 0;
uint64_t g_semantic_visibility_workset_rejected_joins = 0;
uint64_t g_semantic_visibility_workset_missing_joins = 0;

struct SemanticInstanceEntry {
  uint64_t key = 0;
  uint64_t calls = 0;
  uint64_t first_frame = 0;
  uint64_t last_frame = 0;
  uint64_t descriptor_hash = 0;
  uint64_t runtime_hash = 0;
  uint64_t transform_hash = 0;
  uint64_t descriptor_variations = 0;
  uint64_t runtime_variations = 0;
  uint64_t transform_variations = 0;
  uint32_t receiver_address = 0;
  uint32_t receiver_generation = 0;
  uint32_t record_index = 0;
  uint32_t descriptor_count = 0;
  uint32_t descriptor_address = 0;
  uint32_t runtime_address = 0;
  uint32_t descriptor_kind = 0;
  uint32_t active_buffer_index = 0;
  uint32_t per_record_resource_capacity = 0;
  std::array<uint32_t, 7> helper_arguments{};
  std::array<uint32_t, kSemanticDescriptorWordCount> descriptor_words{};
  std::array<uint32_t, kSemanticRuntimeWordCount> runtime_words{};
  std::array<uint32_t, kSemanticTransformWordCount> transform_words{};
};

std::array<SemanticInstanceEntry, kSemanticInstanceCapacity>
    g_semantic_instances{};
std::mutex g_semantic_instance_mutex;
uint64_t g_semantic_instance_observations = 0;
uint64_t g_semantic_instance_live_observations = 0;
uint64_t g_semantic_instance_unknown_receivers = 0;
uint64_t g_semantic_instance_invalid_layouts = 0;
uint64_t g_semantic_instance_invalid_indices = 0;
uint64_t g_semantic_instance_payload_bytes = 0;
uint64_t g_semantic_instance_replay_fallbacks = 0;
uint64_t g_semantic_instance_native_admissions = 0;
uint64_t g_semantic_instance_overflow = 0;
uint64_t g_semantic_instance_count = 0;

struct SemanticSubmissionEntry {
  uint64_t key = 0;
  uint64_t calls = 0;
  uint64_t first_frame = 0;
  uint64_t last_frame = 0;
  uint32_t receiver_address = 0;
  uint32_t receiver_generation = 0;
  uint32_t record_index = 0;
  uint32_t descriptor_kind = 0;
  uint32_t helper_state = 0;
  uint32_t graphics_context = 0;
  uint32_t graphics_vtable = 0;
  uint32_t graphics_submission_method = 0;
  uint32_t resource_lookup_context = 0;
  uint32_t primary_resource_index = 0;
  uint32_t primary_resource_key = 0;
  uint32_t primary_bound_resource_object = 0;
  uint32_t primary_resource_provider_object = 0;
  uint32_t primary_resource_provider_vtable = 0;
  uint32_t primary_resource_predicate_24_method = 0;
  uint32_t primary_resource_primary_36_method = 0;
  uint32_t primary_resource_fallback_40_method = 0;
  uint32_t primary_resource_predicate_44_method = 0;
  uint32_t primary_resource_provider_selection = 0;
  uint32_t primary_resource_object_source = 0;
  int32_t secondary_resource_index = -1;
  uint32_t secondary_resource_key = 0;
  uint32_t secondary_bound_resource_object = 0;
  uint32_t secondary_resource_provider_object = 0;
  uint32_t secondary_resource_provider_vtable = 0;
  uint32_t secondary_resource_predicate_24_method = 0;
  uint32_t secondary_resource_primary_36_method = 0;
  uint32_t secondary_resource_fallback_40_method = 0;
  uint32_t secondary_resource_predicate_44_method = 0;
  uint32_t secondary_resource_provider_selection = 0;
  uint32_t secondary_resource_object_source = 0;
  uint32_t runtime_submission_object = 0;
  uint32_t primitive_type = 13;
  uint32_t count_units = 0;
  uint32_t count_bytes = 0;
  uint32_t source_address = 0;
  bool secondary_resource_present = false;
  bool counted_runtime_source = false;
};

enum class SemanticResourceProviderSelection : uint32_t {
  kUnknown = 0,
  kLookupMissing = 1,
  kPrimaryMethod = 2,
  kFallbackMethod = 3,
  kUnavailable = 4,
};

enum class SemanticResourceObjectSource : uint32_t {
  kUnknown = 0,
  kProviderMethod = 1,
  kSecondaryResolution = 2,
  kNone = 3,
};

struct SemanticResourceProviderProvenance {
  uint32_t provider_object = 0;
  uint32_t provider_vtable = 0;
  uint32_t predicate_24_method = 0;
  uint32_t primary_36_method = 0;
  uint32_t fallback_40_method = 0;
  uint32_t predicate_44_method = 0;
  SemanticResourceProviderSelection selection =
      SemanticResourceProviderSelection::kUnknown;
  SemanticResourceObjectSource object_source =
      SemanticResourceObjectSource::kUnknown;
};

struct PendingSemanticResourceBindings {
  uint32_t receiver_address = 0;
  uint32_t descriptor_address = 0;
  uint32_t runtime_address = 0;
  uint32_t graphics_context = 0;
  uint32_t resource_lookup_context = 0;
  uint32_t primary_resource_key = 0;
  uint32_t primary_bound_resource_object = 0;
  SemanticResourceProviderProvenance primary_provider{};
  uint32_t secondary_resource_key = 0;
  uint32_t secondary_bound_resource_object = 0;
  SemanticResourceProviderProvenance secondary_provider{};
  bool primary_seen = false;
  bool primary_resolution_known = false;
  bool secondary_seen = false;
  bool secondary_resolution_known = false;
};

struct SemanticBindingCacheSlot {
  uint32_t resource_key = 0;
  uint32_t bound_resource_object = 0;
  SemanticResourceProviderProvenance provider{};
  bool key_known = false;
};

struct SemanticResolverCacheSlot {
  uint32_t resolver_cache_slot = 0;
  uint32_t resource_key = 0;
  uint32_t bound_resource_object = 0;
  SemanticResourceProviderProvenance provider{};
  bool key_known = false;
};

struct PendingSemanticResourceResolution {
  uint32_t resource_key = 0;
  uint32_t binding_slot = 0;
  uint32_t graphics_context = 0;
  uint32_t resolved_resource_object = 0;
  SemanticResourceProviderProvenance provider{};
  uint32_t provider_method_result = 0;
  uint32_t secondary_resolution_result = 0;
  uint32_t resolver_cache_slot = 0;
  int32_t resolver_cache_index = -1;
  bool active = false;
  bool result_seen = false;
  bool cache_candidate = false;
  bool resolver_cache_candidate = false;
  bool provider_lookup_seen = false;
  bool primary_predicate_seen = false;
  bool fallback_predicate_seen = false;
  bool provider_method_result_seen = false;
  bool secondary_resolution_result_seen = false;
};

std::array<SemanticSubmissionEntry, kSemanticSubmissionCapacity>
    g_semantic_submissions{};
std::mutex g_semantic_submission_mutex;
uint64_t g_semantic_submission_observations = 0;
uint64_t g_semantic_submission_live_observations = 0;
uint64_t g_semantic_submission_unknown_receivers = 0;
uint64_t g_semantic_submission_binding_mismatches = 0;
uint64_t g_semantic_submission_invalid_record_joins = 0;
uint64_t g_semantic_submission_invalid_resource_joins = 0;
uint64_t g_semantic_submission_invalid_geometry = 0;
uint64_t g_semantic_submission_invalid_dispatch_targets = 0;
uint64_t g_semantic_submission_payload_bytes = 0;
uint64_t g_semantic_submission_replay_fallbacks = 0;
uint64_t g_semantic_submission_native_admissions = 0;
uint64_t g_semantic_submission_overflow = 0;
uint64_t g_semantic_submission_count = 0;
uint64_t g_semantic_primary_binding_observations = 0;
uint64_t g_semantic_secondary_binding_observations = 0;
uint64_t g_semantic_resource_resolution_attempts = 0;
uint64_t g_semantic_resource_resolution_successes = 0;
uint64_t g_semantic_resource_resolution_misses = 0;
uint64_t g_semantic_resource_resolution_cache_hits = 0;
uint64_t g_semantic_resource_bind_dispatches = 0;
uint64_t g_semantic_resource_resolution_protocol_faults = 0;
uint64_t g_semantic_provider_lookup_observations = 0;
uint64_t g_semantic_provider_cache_hits = 0;
uint64_t g_semantic_provider_lookup_misses = 0;
uint64_t g_semantic_provider_primary_selections = 0;
uint64_t g_semantic_provider_fallback_selections = 0;
uint64_t g_semantic_provider_unavailable_selections = 0;
uint64_t g_semantic_provider_method_results = 0;
uint64_t g_semantic_provider_method_null_results = 0;
uint64_t g_semantic_secondary_resolution_attempts = 0;
uint64_t g_semantic_secondary_resolution_successes = 0;
uint64_t g_semantic_secondary_resolution_misses = 0;
uint64_t g_semantic_provider_metadata_bytes = 0;
uint64_t g_semantic_submission_unresolved_resource_joins = 0;
std::atomic<uint64_t> g_semantic_render_item_entries{};
std::atomic<uint64_t> g_semantic_render_item_exits{};
std::atomic<uint64_t> g_semantic_render_items_open{};
std::atomic<uint64_t> g_semantic_render_item_stack_faults{};
std::atomic<uint64_t> g_semantic_render_item_valid_scopes{};
std::atomic<uint64_t> g_semantic_render_item_scopes_without_submission{};
std::atomic<uint64_t> g_semantic_draw_scope_joins{};
std::atomic<uint64_t> g_semantic_draw_scope_mismatches{};
std::atomic<uint64_t> g_semantic_draw_origins_captured{};
std::atomic<uint64_t> g_semantic_draw_dispatches_with_direct_title_origin{};
std::atomic<uint64_t>
    g_semantic_draw_dispatches_without_direct_title_origin{};
std::atomic<uint64_t> g_semantic_draw_indirect_packet_origins_captured{};
std::atomic<uint64_t> g_semantic_draw_dispatches_with_indirect_packet_origin{};
std::atomic<uint64_t>
    g_semantic_draw_dispatches_without_indirect_packet_origin{};
std::atomic<uint64_t> g_semantic_draw_packets_recorded{};
std::atomic<uint64_t> g_semantic_draw_packet_matches{};
std::atomic<uint64_t> g_semantic_draw_prepared_matches{};
std::atomic<uint64_t> g_semantic_draw_unprepared_matches{};
std::array<SemanticBindingCacheSlot, 5> g_semantic_binding_cache_slots{};
std::array<SemanticResolverCacheSlot, 5> g_semantic_resolver_cache_slots{};
thread_local PendingSemanticResourceBindings g_pending_semantic_bindings{};
thread_local PendingSemanticResourceResolution
    g_pending_semantic_resource_resolution{};
thread_local std::array<SemanticDrawIdentity,
                        kSemanticRenderItemStackCapacity>
    g_semantic_render_item_stack{};
thread_local size_t g_semantic_render_item_stack_depth = 0;
thread_local size_t g_semantic_render_item_stack_overflow_depth = 0;
thread_local TitleDrawOrigin g_pending_adapter_origin;
thread_local std::array<TitleDrawOrigin, kTitleOriginStackCapacity>
    g_title_origin_stack;
thread_local size_t g_title_origin_stack_depth = 0;
thread_local std::array<ActiveTitleIndirectBuffer, kTitleIndirectStackCapacity>
    g_title_indirect_stack;
thread_local size_t g_title_indirect_stack_depth = 0;
thread_local std::array<IndirectConstructorOrigin,
                        kIndirectConstructorStackCapacity>
    g_indirect_constructor_stack;
thread_local size_t g_indirect_constructor_stack_depth = 0;
thread_local size_t g_indirect_constructor_stack_overflow_depth = 0;
thread_local std::array<IndirectConstructorOrigin::Owner,
                        kIndirectOwnerStackCapacity>
    g_indirect_owner_stack;
thread_local size_t g_indirect_owner_stack_depth = 0;
thread_local size_t g_indirect_owner_stack_overflow_depth = 0;
thread_local std::array<IndirectConstructorOrigin::Owner::Producer,
                        kIndirectProducerStackCapacity>
    g_indirect_producer_stack;
thread_local size_t g_indirect_producer_stack_depth = 0;
thread_local size_t g_indirect_producer_stack_overflow_depth = 0;
thread_local std::array<IndirectConstructorOrigin::Owner::Producer::Context,
                        kIndirectContextStackCapacity>
    g_indirect_context_stack;
thread_local size_t g_indirect_context_stack_depth = 0;
thread_local size_t g_indirect_context_stack_overflow_depth = 0;
thread_local std::array<uint32_t, kSemanticReceiverStackCapacity>
    g_semantic_receiver_constructor_stack{};
thread_local size_t g_semantic_receiver_constructor_stack_depth = 0;
thread_local size_t g_semantic_receiver_constructor_overflow_depth = 0;
thread_local std::array<uint32_t, kSemanticReceiverStackCapacity>
    g_semantic_receiver_destructor_stack{};
thread_local size_t g_semantic_receiver_destructor_stack_depth = 0;
thread_local size_t g_semantic_receiver_destructor_overflow_depth = 0;
struct SemanticReceiverStageScope {
  uint32_t address = 0;
  uint32_t generation = 0;
};
thread_local std::array<SemanticReceiverStageScope,
                        kSemanticReceiverStackCapacity>
    g_semantic_visibility_stack{};
thread_local size_t g_semantic_visibility_stack_depth = 0;
thread_local size_t g_semantic_visibility_overflow_depth = 0;
struct ActiveSemanticVisibilityRecord {
  uint32_t receiver_address = 0;
  uint32_t receiver_generation = 0;
  uint32_t record_index = 0;
  uint32_t category = 0;
  uint32_t descriptor_address = 0;
  uint32_t runtime_address = 0;
  uint32_t lod_index = 0;
  uint8_t spatial_exponent = 0;
  bool joined = false;
  bool result_seen = false;
  bool selected = false;
  bool lod_seen = false;
  bool spatial_sample_valid = false;
  bool runtime_threshold_seen = false;
  bool runtime_distance_less = false;
  bool descriptor_threshold_seen = false;
  bool descriptor_distance_exceeded = false;
  uint32_t candidate_threshold_observations = 0;
  uint32_t candidate_threshold_passes = 0;
  uint32_t local_distance_observations = 0;
  uint32_t local_distance_passes = 0;
  uint32_t spatial_helper_observations = 0;
  uint32_t spatial_helper_passes = 0;
  uint32_t spatial_shadow_input_observations = 0;
  uint32_t spatial_shadow_comparisons = 0;
  uint32_t spatial_shadow_matches = 0;
  uint32_t spatial_shadow_false_positive = 0;
  uint32_t spatial_shadow_false_negative = 0;
  uint32_t spatial_shadow_invalid_inputs = 0;
  uint32_t category_helper_observations = 0;
  std::array<uint32_t, 3> category_helper_results{};
  uint32_t category_shadow_input_observations = 0;
  uint32_t category_shadow_comparisons = 0;
  uint32_t category_shadow_matches = 0;
  uint32_t category_shadow_false_result = 0;
  uint32_t category_shadow_invalid_inputs = 0;
  uint32_t assembly_spatial_predicted_passes = 0;
  std::array<uint32_t, 3> assembly_category_predictions{};
  bool spatial_shadow_pending = false;
  bool spatial_shadow_valid = false;
  bool spatial_shadow_prediction = false;
  bool category_shadow_pending = false;
  bool category_shadow_valid = false;
  uint32_t category_shadow_prediction = 0;
  bool active = false;
};
thread_local ActiveSemanticVisibilityRecord
    g_active_semantic_visibility_record{};

uint64_t SemanticVisibilityWorksetKey(uint32_t receiver_address,
                                      uint32_t receiver_generation,
                                      uint32_t record_index) {
  uint64_t hash = UINT64_C(0xCBF29CE484222325);
  for (uint32_t value :
       {receiver_address, receiver_generation, record_index}) {
    hash ^= value;
    hash *= UINT64_C(0x100000001B3);
  }
  return hash ? hash : 1;
}

void PublishSemanticVisibilityWorkset(
    const ActiveSemanticVisibilityRecord &record,
    uint32_t invalid_inputs) {
  if (!record.category_shadow_input_observations || !record.joined ||
      invalid_inputs) {
    if (record.category_shadow_input_observations) {
      std::scoped_lock lock(g_semantic_visibility_workset_mutex);
      ++g_semantic_visibility_workset_invalid_records;
    }
    return;
  }
  const bool predicted_selected =
      record.assembly_category_predictions[1] != 0 ||
      record.assembly_category_predictions[2] != 0;
  const bool title_selected = record.result_seen && record.selected;
  const uint32_t result_mask =
      uint32_t(record.assembly_category_predictions[0] != 0) |
      (uint32_t(record.assembly_category_predictions[1] != 0) << 1) |
      (uint32_t(record.assembly_category_predictions[2] != 0) << 2);
  const uint64_t key = SemanticVisibilityWorksetKey(
      record.receiver_address, record.receiver_generation,
      record.record_index);
  const uint64_t frame = g_frame_sequence.load(std::memory_order_relaxed);

  std::scoped_lock lock(g_semantic_visibility_workset_mutex);
  ++g_semantic_visibility_workset_modelled_records;
  ++(predicted_selected
         ? g_semantic_visibility_workset_predicted_selected
         : g_semantic_visibility_workset_predicted_rejected);
  ++(predicted_selected == title_selected
         ? g_semantic_visibility_workset_title_matches
         : g_semantic_visibility_workset_title_mismatches);
  if (record.lod_seen) {
    ++g_semantic_visibility_workset_title_lod_records;
  }
  size_t index = size_t(key % kSemanticVisibilityWorksetCapacity);
  for (size_t probe = 0; probe < kSemanticVisibilityWorksetCapacity;
       ++probe) {
    SemanticVisibilityWorksetEntry &entry =
        g_semantic_visibility_workset[index];
    if (!entry.key) {
      entry.key = key;
      entry.first_frame = frame;
      entry.receiver_address = record.receiver_address;
      entry.receiver_generation = record.receiver_generation;
      entry.record_index = record.record_index;
      entry.category = record.category;
      ++g_semantic_visibility_workset_entries;
    }
    if (entry.key == key &&
        entry.receiver_address == record.receiver_address &&
        entry.receiver_generation == record.receiver_generation &&
        entry.record_index == record.record_index) {
      ++entry.observations;
      entry.last_frame = frame;
      ++(predicted_selected ? entry.predicted_selected
                            : entry.predicted_rejected);
      ++(predicted_selected == title_selected ? entry.title_matches
                                              : entry.title_mismatches);
      entry.category = record.category;
      entry.latest_category_result_mask = result_mask;
      entry.latest_selected = predicted_selected;
      entry.title_lod_observations += uint64_t(record.lod_seen);
      entry.latest_title_lod_index = record.lod_index;
      entry.latest_title_lod_valid = record.lod_seen;
      return;
    }
    index = (index + 1) % kSemanticVisibilityWorksetCapacity;
  }
  ++g_semantic_visibility_workset_overflow;
}

SemanticVisibilityWorksetJoin JoinSemanticVisibilityWorkset(
    uint32_t receiver_address, uint32_t receiver_generation,
    uint32_t record_index, SemanticDrawIdentity *semantic_draw) {
  const uint64_t key = SemanticVisibilityWorksetKey(
      receiver_address, receiver_generation, record_index);
  std::scoped_lock lock(g_semantic_visibility_workset_mutex);
  ++g_semantic_visibility_workset_semantic_instance_lookups;
  size_t index = size_t(key % kSemanticVisibilityWorksetCapacity);
  for (size_t probe = 0; probe < kSemanticVisibilityWorksetCapacity;
       ++probe) {
    SemanticVisibilityWorksetEntry &entry =
        g_semantic_visibility_workset[index];
    if (!entry.key) {
      ++g_semantic_visibility_workset_missing_joins;
      return SemanticVisibilityWorksetJoin::kMissing;
    }
    if (entry.key == key && entry.receiver_address == receiver_address &&
        entry.receiver_generation == receiver_generation &&
        entry.record_index == record_index) {
      ++entry.semantic_instance_joins;
      semantic_draw->visibility_policy_frame = entry.last_frame;
      semantic_draw->visibility_category = entry.category;
      semantic_draw->visibility_result_mask =
          entry.latest_category_result_mask;
      semantic_draw->title_lod_index = entry.latest_title_lod_index;
      semantic_draw->title_lod_valid = entry.latest_title_lod_valid;
      if (entry.latest_selected) {
        ++g_semantic_visibility_workset_selected_joins;
        semantic_draw->visibility_workset_join =
            SemanticVisibilityWorksetJoin::kSelected;
        return SemanticVisibilityWorksetJoin::kSelected;
      }
      ++g_semantic_visibility_workset_rejected_joins;
      semantic_draw->visibility_workset_join =
          SemanticVisibilityWorksetJoin::kRejected;
      return SemanticVisibilityWorksetJoin::kRejected;
    }
    index = (index + 1) % kSemanticVisibilityWorksetCapacity;
  }
  ++g_semantic_visibility_workset_missing_joins;
  return SemanticVisibilityWorksetJoin::kMissing;
}
thread_local std::array<SemanticReceiverStageScope,
                        kSemanticReceiverStackCapacity>
    g_semantic_render_state_stack{};
thread_local size_t g_semantic_render_state_stack_depth = 0;
thread_local size_t g_semantic_render_state_overflow_depth = 0;

const char *DispatchWrapperName(DispatchWrapper wrapper) {
  switch (wrapper) {
  case DispatchWrapper::kDrawIndexed:
    return "draw_indexed";
  case DispatchWrapper::kDrawImmediate:
    return "draw_immediate";
  case DispatchWrapper::kDrawAdapter:
    return "draw_adapter";
  case DispatchWrapper::kVizQueryBegin:
    return "viz_query_begin";
  case DispatchWrapper::kVizQueryEnd:
    return "viz_query_end";
  case DispatchWrapper::kResolveController:
    return "resolve_controller";
  case DispatchWrapper::kResolveSetup:
    return "resolve_setup";
  case DispatchWrapper::kVizQueryOwner:
    return "viz_query_owner";
  case DispatchWrapper::kBinningScissorState:
    return "binning_scissor_state";
  case DispatchWrapper::kBinningStateReset:
    return "binning_state_reset";
  case DispatchWrapper::kProceduralModelDrawIndexed:
    return "procedural_model_draw_indexed";
  }
  return "unknown";
}

const char *DispatchWrapperAddress(DispatchWrapper wrapper) {
  switch (wrapper) {
  case DispatchWrapper::kDrawIndexed:
    return "8240F4D8";
  case DispatchWrapper::kDrawImmediate:
    return "829F7C70";
  case DispatchWrapper::kDrawAdapter:
    return "824079B8";
  case DispatchWrapper::kVizQueryBegin:
    return "829F21A0";
  case DispatchWrapper::kVizQueryEnd:
    return "829F2280";
  case DispatchWrapper::kResolveController:
    return "824587D8";
  case DispatchWrapper::kResolveSetup:
    return "82458A88";
  case DispatchWrapper::kVizQueryOwner:
    return "82D951E0";
  case DispatchWrapper::kBinningScissorState:
    return "82413AB8";
  case DispatchWrapper::kBinningStateReset:
    return "824736F0";
  case DispatchWrapper::kProceduralModelDrawIndexed:
    return "82415F68";
  }
  return "00000000";
}

const char *DrawOutcomeName(uint32_t outcome) {
  using Status = rex::system::GraphicsDrawOutcomeStatus;
  switch (Status(outcome)) {
  case Status::kCompleted:
    return "completed";
  case Status::kEdramCopy:
    return "edram_copy";
  case Status::kMissingVertexShader:
    return "missing_vertex_shader";
  case Status::kZeroSurfacePitch:
    return "zero_surface_pitch";
  case Status::kNoRasterizationOrMemexport:
    return "no_rasterization_or_memexport";
  case Status::kSubmissionFailed:
    return "submission_failed";
  case Status::kPrimitiveProcessingFailed:
    return "primitive_processing_failed";
  case Status::kNoHostVertices:
    return "no_host_vertices";
  case Status::kRenderTargetUpdateFailed:
    return "render_target_update_failed";
  case Status::kPipelineConfigurationFailed:
    return "pipeline_configuration_failed";
  case Status::kPipelinePending:
    return "pipeline_pending";
  case Status::kBindingUpdateFailed:
    return "binding_update_failed";
  case Status::kInvalidVertexFetch:
    return "invalid_vertex_fetch";
  case Status::kVertexResidencyFailed:
    return "vertex_residency_failed";
  case Status::kMemexportResidencyFailed:
    return "memexport_residency_failed";
  case Status::kUnsupportedPrimitive:
    return "unsupported_primitive";
  case Status::kScratchIndexBufferFailed:
    return "scratch_index_buffer_failed";
  case Status::kUnsupportedIndexBuffer:
    return "unsupported_index_buffer";
  }
  return "observer_missing";
}

std::string CensusSceneMarker();

TitleDrawOrigin MakeTitleDrawOrigin(DispatchWrapper wrapper, uint32_t caller,
                                    uint32_t r3, uint32_t r4, uint32_t r5,
                                    uint32_t r6, uint32_t r7, uint32_t r8,
                                    uint32_t r9, uint32_t r10) {
  TitleDrawOrigin origin;
  origin.wrapper = wrapper;
  origin.caller = caller;
  origin.arguments = {r3, r4, r5, r6, r7, r8, r9, r10};
  if (g_semantic_render_item_stack_depth) {
    SemanticDrawIdentity &semantic_draw =
        g_semantic_render_item_stack[g_semantic_render_item_stack_depth - 1];
    if (semantic_draw.valid) {
      origin.semantic_draw = semantic_draw;
      ++semantic_draw.direct_title_origins;
    }
  }
  origin.valid = true;
  return origin;
}

void ResetTitleDrawProvenance() {
  std::scoped_lock lock(g_title_packet_provenance_mutex);
  for (TitlePacketProvenanceEntry &entry : g_title_packet_provenance) {
    entry = {};
  }
  for (TitleDrawProvenanceEntry &entry : g_title_draw_provenance) {
    entry = {};
  }
  for (SemanticBatchOpportunityEntry &entry :
       g_semantic_batch_opportunities) {
    entry = {};
  }
  for (SemanticVisibilityPreparedCandidateEntry &entry :
       g_semantic_visibility_prepared_candidates) {
    entry = {};
  }
  for (auto &level : g_semantic_batch_equivalence_opportunities) {
    for (SemanticBatchEquivalenceEntry &entry : level) {
      entry = {};
    }
  }
  for (auto &level : g_semantic_state_caches) {
    for (auto &cache : level) {
      for (SemanticStateCacheEntry &entry : cache) {
        entry = {};
      }
    }
  }
  for (TitleIndirectPacketEntry &entry : g_title_indirect_packets) {
    entry = {};
  }
  g_title_packets_recorded = 0;
  g_title_packets_matched = 0;
  g_title_packet_address_failures = 0;
  g_title_packet_reused_live_addresses = 0;
  g_title_packet_table_overflow = 0;
  g_title_backend_unattributed_draws = 0;
  g_title_matched_unprepared_draws = 0;
  g_backend_draw_outcomes_observed = 0;
  g_backend_draw_outcome_mismatches = 0;
  g_backend_draw_outcome_missing = 0;
  g_backend_draw_outcome_counts = {};
  g_title_backend_outcome_counts = {};
  g_title_forwarding_mismatches.store(0, std::memory_order_relaxed);
  g_title_origins_pushed.store(0, std::memory_order_relaxed);
  g_title_origins_consumed.store(0, std::memory_order_relaxed);
  g_title_origin_stack_overflow.store(0, std::memory_order_relaxed);
  g_title_packets_without_origin.store(0, std::memory_order_relaxed);
  g_title_draw_provenance_count = 0;
  g_title_draw_provenance_overflow = 0;
  g_semantic_batch_observations = 0;
  g_semantic_visibility_prepared_observations = 0;
  g_semantic_visibility_prepared_selected_joins = 0;
  g_semantic_visibility_prepared_fresh_candidates = 0;
  g_semantic_visibility_prepared_stale_exclusions = 0;
  g_semantic_visibility_prepared_future_exclusions = 0;
  g_semantic_visibility_prepared_rejected_exclusions = 0;
  g_semantic_visibility_prepared_missing_exclusions = 0;
  g_semantic_visibility_prepared_candidate_count = 0;
  g_semantic_visibility_prepared_candidate_overflow = 0;
  g_semantic_batch_eligible_draws = 0;
  g_semantic_batch_rejected_draws = 0;
  g_semantic_batch_opportunity_count = 0;
  g_semantic_batch_opportunity_overflow = 0;
  g_semantic_batch_consecutive_runs = 0;
  g_semantic_batch_multi_draw_runs = 0;
  g_semantic_batch_multi_draw_draws = 0;
  g_semantic_batch_maximum_run_length = 0;
  g_semantic_batch_instance_switches = 0;
  g_semantic_batch_same_instance_continuations = 0;
  g_semantic_batch_frame_count = 0;
  g_semantic_batch_current_frame = 0;
  g_semantic_batch_current_frame_draws = 0;
  g_semantic_batch_maximum_draws_per_frame = 0;
  g_semantic_batch_template_transitions = 0;
  g_semantic_batch_geometry_transitions = 0;
  g_semantic_batch_texture_transitions = 0;
  g_semantic_batch_title_resource_transitions = 0;
  g_semantic_batch_rejections = {};
  g_semantic_batch_run = {};
  g_semantic_batch_previous_contract = {};
  g_semantic_batch_previous_identity = {};
  g_semantic_batch_previous_frame = 0;
  g_semantic_batch_previous_eligible = false;
  g_semantic_batch_parameter_payload_bytes = 0;
  g_semantic_batch_maximum_parameter_payload_bytes = 0;
  g_semantic_batch_equivalence_counts = {};
  g_semantic_batch_equivalence_overflows = {};
  g_semantic_batch_equivalence_runs = {};
  g_semantic_state_cache_stats = {};
  g_title_packet_submission_sequence = 0;
  g_title_indirect_packets_recorded = 0;
  g_title_indirect_packet_address_failures = 0;
  g_title_indirect_packet_table_overflow = 0;
  g_title_indirect_packet_evictions = 0;
  g_title_indirect_packet_submission_sequence = 0;
  g_title_indirect_buffer_enters = 0;
  g_title_indirect_buffer_exits = 0;
  g_title_indirect_buffer_matches = 0;
  g_title_indirect_buffer_unmatched = 0;
  g_title_indirect_stack_faults = 0;
  g_title_indirect_draw_stack_faults = 0;
  g_indirect_constructor_entries.store(0, std::memory_order_relaxed);
  g_indirect_constructor_exits.store(0, std::memory_order_relaxed);
  g_indirect_constructor_stack_faults.store(0, std::memory_order_relaxed);
  g_indirect_packets_without_constructor_origin.store(
      0, std::memory_order_relaxed);
  g_indirect_owner_entries.store(0, std::memory_order_relaxed);
  g_indirect_owner_exits.store(0, std::memory_order_relaxed);
  g_indirect_owner_stack_faults.store(0, std::memory_order_relaxed);
  g_indirect_constructors_without_owner_origin.store(
      0, std::memory_order_relaxed);
  g_indirect_constructor_owner_mismatches.store(
      0, std::memory_order_relaxed);
  g_indirect_producer_entries.store(0, std::memory_order_relaxed);
  g_indirect_producer_exits.store(0, std::memory_order_relaxed);
  g_indirect_producer_stack_faults.store(0, std::memory_order_relaxed);
  g_indirect_owners_without_producer_origin.store(
      0, std::memory_order_relaxed);
  g_indirect_owner_producer_mismatches.store(
      0, std::memory_order_relaxed);
  g_indirect_context_entries.store(0, std::memory_order_relaxed);
  g_indirect_context_exits.store(0, std::memory_order_relaxed);
  g_indirect_context_stack_faults.store(0, std::memory_order_relaxed);
  g_indirect_producers_without_context_origin.store(
      0, std::memory_order_relaxed);
  g_indirect_producer_context_mismatches.store(
      0, std::memory_order_relaxed);
  g_title_indirect_buffers_open.store(0, std::memory_order_relaxed);
  g_indirect_constructor_invocations_open.store(0,
                                                std::memory_order_relaxed);
  g_indirect_owner_invocations_open.store(0, std::memory_order_relaxed);
  g_indirect_producer_invocations_open.store(0, std::memory_order_relaxed);
  g_indirect_context_invocations_open.store(0, std::memory_order_relaxed);
  for (SemanticReceiverLifecycleEntry &entry :
       g_semantic_receiver_lifecycles) {
    entry.address.store(0, std::memory_order_relaxed);
    entry.generation.store(0, std::memory_order_relaxed);
    entry.state.store(0, std::memory_order_relaxed);
    entry.dispatches.store(0, std::memory_order_relaxed);
    entry.visibility_preparations.store(0, std::memory_order_relaxed);
    entry.render_state_preparations.store(0, std::memory_order_relaxed);
    entry.visibility_epoch.store(0, std::memory_order_relaxed);
    entry.render_state_epoch.store(0, std::memory_order_relaxed);
    entry.render_state_visibility_epoch.store(0,
                                               std::memory_order_relaxed);
    entry.dispatches_with_preparation.store(0, std::memory_order_relaxed);
    entry.dispatches_without_preparation.store(0,
                                                std::memory_order_relaxed);
    entry.dispatches_without_visibility.store(0,
                                               std::memory_order_relaxed);
    entry.dispatches_without_render_state.store(0,
                                                 std::memory_order_relaxed);
  }
  g_semantic_receiver_constructor_entries.store(0,
                                                 std::memory_order_relaxed);
  g_semantic_receiver_constructor_exits.store(0,
                                               std::memory_order_relaxed);
  g_semantic_receiver_constructor_open.store(0,
                                              std::memory_order_relaxed);
  g_semantic_receiver_destructor_entries.store(0,
                                                std::memory_order_relaxed);
  g_semantic_receiver_destructor_exits.store(0,
                                              std::memory_order_relaxed);
  g_semantic_receiver_destructor_open.store(0,
                                             std::memory_order_relaxed);
  g_semantic_receiver_stack_faults.store(0, std::memory_order_relaxed);
  g_semantic_receiver_instances_published.store(0,
                                                 std::memory_order_relaxed);
  g_semantic_receiver_instances_destroyed.store(0,
                                                 std::memory_order_relaxed);
  g_semantic_receiver_address_reuses.store(0, std::memory_order_relaxed);
  g_semantic_receiver_table_overflow.store(0, std::memory_order_relaxed);
  g_semantic_receiver_dispatches.store(0, std::memory_order_relaxed);
  g_semantic_receiver_live_dispatches.store(0,
                                             std::memory_order_relaxed);
  g_semantic_receiver_unregistered_dispatches.store(
      0, std::memory_order_relaxed);
  g_semantic_receiver_destroying_dispatches.store(
      0, std::memory_order_relaxed);
  g_semantic_receiver_destroyed_dispatches.store(
      0, std::memory_order_relaxed);
  g_semantic_receiver_destructors_without_instance.store(
      0, std::memory_order_relaxed);
  g_semantic_visibility_entries.store(0, std::memory_order_relaxed);
  g_semantic_visibility_exits.store(0, std::memory_order_relaxed);
  g_semantic_visibility_open.store(0, std::memory_order_relaxed);
  g_semantic_render_state_entries.store(0, std::memory_order_relaxed);
  g_semantic_render_state_exits.store(0, std::memory_order_relaxed);
  g_semantic_render_state_open.store(0, std::memory_order_relaxed);
  g_semantic_stage_stack_faults.store(0, std::memory_order_relaxed);
  g_semantic_stage_unknown_receivers.store(0,
                                            std::memory_order_relaxed);
  g_semantic_visibility_record_entries.store(0,
                                               std::memory_order_relaxed);
  g_semantic_visibility_record_completions.store(
      0, std::memory_order_relaxed);
  g_semantic_visibility_records_open.store(0,
                                            std::memory_order_relaxed);
  g_semantic_visibility_result_observations.store(
      0, std::memory_order_relaxed);
  g_semantic_visibility_selected_records.store(
      0, std::memory_order_relaxed);
  g_semantic_visibility_rejected_records.store(
      0, std::memory_order_relaxed);
  g_semantic_visibility_early_rejected_records.store(
      0, std::memory_order_relaxed);
  g_semantic_visibility_lod_writes.store(0,
                                         std::memory_order_relaxed);
  g_semantic_visibility_selected_with_lod.store(
      0, std::memory_order_relaxed);
  g_semantic_visibility_selected_without_lod.store(
      0, std::memory_order_relaxed);
  g_semantic_visibility_record_stack_faults.store(
      0, std::memory_order_relaxed);
  g_semantic_visibility_entry_overlaps.store(0,
                                              std::memory_order_relaxed);
  g_semantic_visibility_lod_without_record.store(
      0, std::memory_order_relaxed);
  g_semantic_visibility_lod_rewrites.store(0,
                                            std::memory_order_relaxed);
  g_semantic_visibility_result_without_record.store(
      0, std::memory_order_relaxed);
  g_semantic_visibility_duplicate_result.store(
      0, std::memory_order_relaxed);
  g_semantic_visibility_completion_without_record.store(
      0, std::memory_order_relaxed);
  g_semantic_visibility_exit_with_record.store(
      0, std::memory_order_relaxed);
  g_semantic_visibility_record_identity_mismatches.store(
      0, std::memory_order_relaxed);
  g_semantic_visibility_record_unknown_receivers.store(
      0, std::memory_order_relaxed);
  g_semantic_visibility_category_overflow.store(
      0, std::memory_order_relaxed);
  g_semantic_visibility_lod_overflow.store(0,
                                            std::memory_order_relaxed);
  for (auto &category : g_semantic_visibility_categories) {
    category.entries.store(0, std::memory_order_relaxed);
    category.completions.store(0, std::memory_order_relaxed);
    category.selected.store(0, std::memory_order_relaxed);
    category.rejected.store(0, std::memory_order_relaxed);
    category.early_rejected.store(0, std::memory_order_relaxed);
    category.lod_writes.store(0, std::memory_order_relaxed);
  }
  for (auto &lod : g_semantic_visibility_lod_histogram) {
    lod.store(0, std::memory_order_relaxed);
  }
  for (auto &value : g_semantic_visibility_result_value_histogram) {
    value.store(0, std::memory_order_relaxed);
  }
  for (auto &category : g_semantic_visibility_policy_categories) {
    for (auto &outcome : category) {
      outcome.records.store(0, std::memory_order_relaxed);
      outcome.spatial_samples.store(0, std::memory_order_relaxed);
      outcome.runtime_threshold_observations.store(
          0, std::memory_order_relaxed);
      outcome.runtime_distance_less.store(0, std::memory_order_relaxed);
      outcome.descriptor_threshold_observations.store(
          0, std::memory_order_relaxed);
      outcome.descriptor_distance_exceeded.store(
          0, std::memory_order_relaxed);
    }
  }
  for (auto &outcome : g_semantic_visibility_spatial_exponents) {
    for (auto &bucket : outcome) {
      bucket.store(0, std::memory_order_relaxed);
    }
  }
  g_semantic_visibility_policy_invalid_spatial_values.store(
      0, std::memory_order_relaxed);
  g_semantic_visibility_policy_invalid_threshold_values.store(
      0, std::memory_order_relaxed);
  g_semantic_visibility_policy_hook_faults.store(
      0, std::memory_order_relaxed);
  g_semantic_visibility_runtime_threshold_without_record.store(
      0, std::memory_order_relaxed);
  g_semantic_visibility_duplicate_runtime_threshold.store(
      0, std::memory_order_relaxed);
  g_semantic_visibility_descriptor_threshold_without_record.store(
      0, std::memory_order_relaxed);
  g_semantic_visibility_duplicate_descriptor_threshold.store(
      0, std::memory_order_relaxed);
  {
    std::scoped_lock lock(g_semantic_visibility_workset_mutex);
    g_semantic_visibility_workset = {};
    g_semantic_visibility_workset_modelled_records = 0;
    g_semantic_visibility_workset_predicted_selected = 0;
    g_semantic_visibility_workset_predicted_rejected = 0;
    g_semantic_visibility_workset_title_matches = 0;
    g_semantic_visibility_workset_title_mismatches = 0;
    g_semantic_visibility_workset_title_lod_records = 0;
    g_semantic_visibility_workset_invalid_records = 0;
    g_semantic_visibility_workset_entries = 0;
    g_semantic_visibility_workset_overflow = 0;
    g_semantic_visibility_workset_semantic_instance_lookups = 0;
    g_semantic_visibility_workset_selected_joins = 0;
    g_semantic_visibility_workset_rejected_joins = 0;
    g_semantic_visibility_workset_missing_joins = 0;
  }
  {
    std::scoped_lock lock(g_semantic_instance_mutex);
    std::memset(g_semantic_instances.data(), 0, sizeof(g_semantic_instances));
    g_semantic_instance_observations = 0;
    g_semantic_instance_live_observations = 0;
    g_semantic_instance_unknown_receivers = 0;
    g_semantic_instance_invalid_layouts = 0;
    g_semantic_instance_invalid_indices = 0;
    g_semantic_instance_payload_bytes = 0;
    g_semantic_instance_replay_fallbacks = 0;
    g_semantic_instance_native_admissions = 0;
    g_semantic_instance_overflow = 0;
    g_semantic_instance_count = 0;
  }
  {
    std::scoped_lock lock(g_semantic_submission_mutex);
    std::memset(g_semantic_submissions.data(), 0,
                sizeof(g_semantic_submissions));
    g_semantic_submission_observations = 0;
    g_semantic_submission_live_observations = 0;
    g_semantic_submission_unknown_receivers = 0;
    g_semantic_submission_binding_mismatches = 0;
    g_semantic_submission_invalid_record_joins = 0;
    g_semantic_submission_invalid_resource_joins = 0;
    g_semantic_submission_invalid_geometry = 0;
    g_semantic_submission_invalid_dispatch_targets = 0;
    g_semantic_submission_payload_bytes = 0;
    g_semantic_submission_replay_fallbacks = 0;
    g_semantic_submission_native_admissions = 0;
    g_semantic_submission_overflow = 0;
    g_semantic_submission_count = 0;
    g_semantic_primary_binding_observations = 0;
    g_semantic_secondary_binding_observations = 0;
    g_semantic_resource_resolution_attempts = 0;
    g_semantic_resource_resolution_successes = 0;
    g_semantic_resource_resolution_misses = 0;
    g_semantic_resource_resolution_cache_hits = 0;
    g_semantic_resource_bind_dispatches = 0;
    g_semantic_resource_resolution_protocol_faults = 0;
    g_semantic_provider_lookup_observations = 0;
    g_semantic_provider_cache_hits = 0;
    g_semantic_provider_lookup_misses = 0;
    g_semantic_provider_primary_selections = 0;
    g_semantic_provider_fallback_selections = 0;
    g_semantic_provider_unavailable_selections = 0;
    g_semantic_provider_method_results = 0;
    g_semantic_provider_method_null_results = 0;
    g_semantic_secondary_resolution_attempts = 0;
    g_semantic_secondary_resolution_successes = 0;
    g_semantic_secondary_resolution_misses = 0;
    g_semantic_provider_metadata_bytes = 0;
    g_semantic_submission_unresolved_resource_joins = 0;
    g_semantic_binding_cache_slots = {};
    g_semantic_resolver_cache_slots = {};
  }
  g_semantic_render_item_entries.store(0, std::memory_order_relaxed);
  g_semantic_render_item_exits.store(0, std::memory_order_relaxed);
  g_semantic_render_items_open.store(0, std::memory_order_relaxed);
  g_semantic_render_item_stack_faults.store(0,
                                             std::memory_order_relaxed);
  g_semantic_render_item_valid_scopes.store(0,
                                             std::memory_order_relaxed);
  g_semantic_render_item_scopes_without_submission.store(
      0, std::memory_order_relaxed);
  g_semantic_draw_scope_joins.store(0, std::memory_order_relaxed);
  g_semantic_draw_scope_mismatches.store(0, std::memory_order_relaxed);
  g_semantic_draw_origins_captured.store(0, std::memory_order_relaxed);
  g_semantic_draw_dispatches_with_direct_title_origin.store(
      0, std::memory_order_relaxed);
  g_semantic_draw_dispatches_without_direct_title_origin.store(
      0, std::memory_order_relaxed);
  g_semantic_draw_indirect_packet_origins_captured.store(
      0, std::memory_order_relaxed);
  g_semantic_draw_dispatches_with_indirect_packet_origin.store(
      0, std::memory_order_relaxed);
  g_semantic_draw_dispatches_without_indirect_packet_origin.store(
      0, std::memory_order_relaxed);
  g_semantic_draw_packets_recorded.store(0, std::memory_order_relaxed);
  g_semantic_draw_packet_matches.store(0, std::memory_order_relaxed);
  g_semantic_draw_prepared_matches.store(0, std::memory_order_relaxed);
  g_semantic_draw_unprepared_matches.store(0, std::memory_order_relaxed);
  g_pending_semantic_bindings = {};
  g_pending_semantic_resource_resolution = {};
  g_semantic_render_item_stack = {};
  g_semantic_render_item_stack_depth = 0;
  g_semantic_render_item_stack_overflow_depth = 0;
  g_pending_adapter_origin = {};
  g_title_origin_stack = {};
  g_title_origin_stack_depth = 0;
  g_title_indirect_stack = {};
  g_title_indirect_stack_depth = 0;
  g_indirect_constructor_stack = {};
  g_indirect_constructor_stack_depth = 0;
  g_indirect_constructor_stack_overflow_depth = 0;
  g_indirect_owner_stack = {};
  g_indirect_owner_stack_depth = 0;
  g_indirect_owner_stack_overflow_depth = 0;
  g_indirect_producer_stack = {};
  g_indirect_producer_stack_depth = 0;
  g_indirect_producer_stack_overflow_depth = 0;
  g_indirect_context_stack = {};
  g_indirect_context_stack_depth = 0;
  g_indirect_context_stack_overflow_depth = 0;
  g_semantic_receiver_constructor_stack = {};
  g_semantic_receiver_constructor_stack_depth = 0;
  g_semantic_receiver_constructor_overflow_depth = 0;
  g_semantic_receiver_destructor_stack = {};
  g_semantic_receiver_destructor_stack_depth = 0;
  g_semantic_receiver_destructor_overflow_depth = 0;
  g_semantic_visibility_stack = {};
  g_semantic_visibility_stack_depth = 0;
  g_semantic_visibility_overflow_depth = 0;
  g_active_semantic_visibility_record = {};
  g_semantic_render_state_stack = {};
  g_semantic_render_state_stack_depth = 0;
  g_semantic_render_state_overflow_depth = 0;
}

void ConfigureTitleDrawProvenance(bool census_requested,
                                  rex::memory::Memory *memory) {
  ResetTitleDrawProvenance();
  const bool dispatch_requested =
      REXCVAR_GET(pinyon_shift_native_renderer_dispatch_discovery);
  const bool armed = dispatch_requested && census_requested && memory;
  g_title_provenance_memory.store(armed ? memory : nullptr,
                                  std::memory_order_release);
  g_title_provenance_installed.store(armed, std::memory_order_release);
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.discovery.title_provenance_config",
      {{"status", armed ? "armed" : "disabled"},
       {"scene", CensusSceneMarker()},
       {"title_packet_hooks", "82410328,829F7CB0"},
       {"semantic_packet_hooks", "82416260,824162F4"},
       {"title_indirect_packet_hooks",
        "824095B4,82416EFC,8246FC1C,8263BD64,829E8E88,829EC49C"},
       {"packet_key", "physical_pm4_header_address"},
       {"packet_capacity", std::to_string(kTitlePacketProvenanceCapacity)},
       {"aggregate_capacity", std::to_string(kTitleDrawProvenanceCapacity)},
       {"semantic_batch_opportunity_capacity",
        std::to_string(kSemanticBatchOpportunityCapacity)},
       {"origin_stack_capacity", std::to_string(kTitleOriginStackCapacity)},
       {"semantic_render_item_stack_capacity",
        std::to_string(kSemanticRenderItemStackCapacity)},
       {"indirect_packet_capacity",
        std::to_string(kTitleIndirectPacketCapacity)},
       {"indirect_packet_bucket_count",
        std::to_string(kTitleIndirectPacketBucketCount)},
       {"indirect_packet_ways", std::to_string(kTitleIndirectPacketWays)},
       {"indirect_stack_capacity",
        std::to_string(kTitleIndirectStackCapacity)},
       {"constructor_stack_capacity",
        std::to_string(kIndirectConstructorStackCapacity)},
       {"owner_stack_capacity", std::to_string(kIndirectOwnerStackCapacity)},
       {"producer_stack_capacity",
        std::to_string(kIndirectProducerStackCapacity)},
       {"context_stack_capacity",
        std::to_string(kIndirectContextStackCapacity)},
       {"metadata",
        "origin_wrapper,entry_lr,r3-r10,outcome,backend_outcome,"
        "backend_signature,semantic_submission_key,semantic_receiver,"
        "semantic_record_index,semantic_template_key,geometry_resource,"
        "texture_resource,title_resource_keys"},
       {"semantic_batch_planner",
        "exact_consecutive_opaque_prepared_draw_order"},
       {"semantic_batch_equivalence_ladder",
        "mesh_material,material,pipeline"},
       {"semantic_batch_pipeline_identity",
        "resource_free_layout_and_prepared_state"},
       {"semantic_batch_instance_parameters",
        "shader_constants_and_semantic_instance"},
       {"semantic_batch_maximum_parameter_payload_bytes",
        std::to_string(kSemanticBatchMaximumParameterPayloadBytes)},
       {"semantic_state_cache_levels", "material,pipeline"},
       {"semantic_state_cache_profiles",
        "compact:64,balanced:256,headroom:1024"},
       {"semantic_state_cache_ways",
        std::to_string(kSemanticStateCacheWays)},
       {"semantic_state_cache_maximum_capacity",
        std::to_string(kSemanticStateCacheMaximumCapacity)},
       {"semantic_state_cache_policy", "set_associative_lru"},
       {"semantic_state_cache_lifetime", "census_session"},
       {"semantic_state_cache_execution", "shadow_measurement_only"},
       {"semantic_batch_execution", "disabled_measurement_only"},
       {"guest_payload_read", "false"},
       {"guest_state_changed", "false"},
       {"control_flow_changed", "false"},
       {"xenos_authority", "true"},
       {"suppression_allowed", "false"}});
}

void CaptureAdapterOrigin(uint32_t caller, uint32_t r3, uint32_t r4,
                          uint32_t r5, uint32_t r6, uint32_t r7,
                          uint32_t r8, uint32_t r9, uint32_t r10) {
  if (!g_title_provenance_installed.load(std::memory_order_acquire)) {
    return;
  }
  g_pending_adapter_origin = MakeTitleDrawOrigin(
      DispatchWrapper::kDrawAdapter, caller, r3, r4, r5, r6, r7, r8, r9,
      r10);
}

void CapturePacketWrapperOrigin(DispatchWrapper wrapper, uint32_t caller,
                                uint32_t r3, uint32_t r4, uint32_t r5,
                                uint32_t r6, uint32_t r7, uint32_t r8,
                                uint32_t r9, uint32_t r10) {
  if (!g_title_provenance_installed.load(std::memory_order_acquire)) {
    return;
  }
  TitleDrawOrigin origin;
  if (wrapper == DispatchWrapper::kDrawIndexed && caller == 0x824079FC) {
    if (g_pending_adapter_origin.valid) {
      origin = g_pending_adapter_origin;
      g_pending_adapter_origin = {};
    } else {
      ++g_title_forwarding_mismatches;
    }
  }
  if (!origin.valid) {
    origin = MakeTitleDrawOrigin(wrapper, caller, r3, r4, r5, r6, r7, r8,
                                 r9, r10);
  }
  if (g_title_origin_stack_depth == kTitleOriginStackCapacity) {
    ++g_title_origin_stack_overflow;
    return;
  }
  if (origin.semantic_draw.valid) {
    g_semantic_draw_origins_captured.fetch_add(1,
                                                std::memory_order_relaxed);
  }
  g_title_origin_stack[g_title_origin_stack_depth++] = origin;
  ++g_title_origins_pushed;
}

void RecordTitleDrawPacketOrigin(uint32_t packet_guest_address,
                                 const TitleDrawOrigin &origin) {
  if (!g_title_provenance_installed.load(std::memory_order_acquire)) {
    return;
  }
  rex::memory::Memory *memory =
      g_title_provenance_memory.load(std::memory_order_acquire);
  if (!memory) {
    return;
  }
  const uint32_t packet_physical_address =
      memory->GetPhysicalAddress(packet_guest_address);
  std::scoped_lock lock(g_title_packet_provenance_mutex);
  if (!g_title_provenance_installed.load(std::memory_order_acquire)) {
    return;
  }
  if (packet_physical_address == UINT32_MAX) {
    ++g_title_packet_address_failures;
    return;
  }
  const size_t initial =
      (packet_physical_address >> 2) % kTitlePacketProvenanceCapacity;
  size_t available = kTitlePacketProvenanceCapacity;
  bool reused_live_address = false;
  for (size_t probe = 0; probe < kTitlePacketProvenanceCapacity; ++probe) {
    const size_t index = (initial + probe) % kTitlePacketProvenanceCapacity;
    TitlePacketProvenanceEntry &entry = g_title_packet_provenance[index];
    if (entry.occupied &&
        entry.packet_physical_address == packet_physical_address) {
      reused_live_address = true;
    }
    if (!entry.occupied && available == kTitlePacketProvenanceCapacity) {
      available = index;
    }
    if (!entry.ever_used) {
      break;
    }
  }
  if (available == kTitlePacketProvenanceCapacity) {
    ++g_title_packet_table_overflow;
    return;
  }
  TitlePacketProvenanceEntry &entry = g_title_packet_provenance[available];
  entry.packet_physical_address = packet_physical_address;
  entry.submission_sequence = ++g_title_packet_submission_sequence;
  entry.origin = origin;
  entry.ever_used = true;
  entry.occupied = true;
  if (reused_live_address) {
    ++g_title_packet_reused_live_addresses;
  }
  if (origin.semantic_draw.valid) {
    g_semantic_draw_packets_recorded.fetch_add(1,
                                                std::memory_order_relaxed);
  }
  ++g_title_packets_recorded;
}

void RecordTitleDrawPacket(uint32_t packet_guest_address) {
  if (!g_title_provenance_installed.load(std::memory_order_acquire)) {
    return;
  }
  if (!g_title_provenance_memory.load(std::memory_order_acquire)) {
    return;
  }
  if (!g_title_origin_stack_depth) {
    ++g_title_packets_without_origin;
    return;
  }
  const TitleDrawOrigin origin =
      g_title_origin_stack[--g_title_origin_stack_depth];
  ++g_title_origins_consumed;
  RecordTitleDrawPacketOrigin(packet_guest_address, origin);
}

void RecordProceduralModelSemanticDrawPacket(
    uint32_t packet_guest_address, uint32_t constructor_store_address,
    std::array<uint32_t, 8> arguments) {
  if (!g_title_provenance_installed.load(std::memory_order_acquire) ||
      !g_semantic_render_item_stack_depth) {
    return;
  }
  SemanticDrawIdentity &semantic_draw =
      g_semantic_render_item_stack[g_semantic_render_item_stack_depth - 1];
  if (!semantic_draw.valid) {
    g_semantic_draw_scope_mismatches.fetch_add(1,
                                                std::memory_order_relaxed);
    return;
  }
  TitleDrawOrigin origin{};
  origin.wrapper = DispatchWrapper::kProceduralModelDrawIndexed;
  origin.caller = constructor_store_address;
  origin.arguments = arguments;
  origin.semantic_draw = semantic_draw;
  origin.valid = true;
  ++semantic_draw.direct_title_origins;
  g_semantic_draw_origins_captured.fetch_add(1,
                                              std::memory_order_relaxed);
  RecordTitleDrawPacketOrigin(packet_guest_address, origin);
}

uint32_t ExpectedIndirectOwnerFunction(uint32_t constructor_function_address,
                                       uint32_t constructor_return_address) {
  if (constructor_function_address == 0x82409398) {
    switch (constructor_return_address) {
    case 0x82409838:
      return 0x82409668;
    case 0x829F6308:
    case 0x829F633C:
      return 0x829F5FF0;
    default:
      return 0;
    }
  }
  if (constructor_function_address == 0x82416A00) {
    switch (constructor_return_address) {
    case 0x82416898:
      return 0x824167F8;
    case 0x8246E930:
      return 0x8246E8F8;
    default:
      return 0;
    }
  }
  return 0;
}

uint32_t ExpectedIndirectProducerFunction(uint32_t owner_function_address,
                                          uint32_t owner_return_address) {
  if (owner_function_address == 0x82409668 &&
      owner_return_address == 0x8240D1B0) {
    return 0x8240D070;
  }
  if (owner_function_address == 0x824167F8 &&
      owner_return_address == 0x824170BC) {
    return 0x82417060;
  }
  if (owner_function_address == 0x829F5FF0 &&
      owner_return_address == 0x829F6608) {
    return 0x829F6360;
  }
  return 0;
}

uint32_t ExpectedIndirectContextFunction(uint32_t producer_function_address,
                                         uint32_t producer_return_address) {
  if (producer_function_address == 0x8240D070 &&
      producer_return_address == 0x8240D000) {
    return 0x8240CF68;
  }
  if (producer_function_address == 0x82417060 &&
      (producer_return_address == 0x82418A28 ||
       producer_return_address == 0x82418ECC)) {
    return 0x82417BC0;
  }
  if (producer_function_address == 0x82417060 &&
      producer_return_address == 0x82437048) {
    return 0x824365B0;
  }
  if (producer_function_address == 0x829F6360 &&
      producer_return_address == 0x829F67B0) {
    return 0x829F6620;
  }
  return 0;
}

uint32_t DeriveIndirectContextRoot(
    uint32_t function_address, const std::array<uint32_t, 8> &arguments) {
  switch (function_address) {
  case 0x8240CF68:
  case 0x829F6620:
    return arguments[0];
  case 0x82417BC0:
    return arguments[3] + 59712;
  case 0x824365B0:
    return arguments[0] + 59712;
  default:
    return 0;
  }
}

size_t SemanticReceiverLifecycleIndex(uint32_t address) {
  return size_t((address >> 4) % kSemanticReceiverLifecycleCapacity);
}

SemanticReceiverLifecycleEntry *FindSemanticReceiverLifecycle(
    uint32_t address) {
  size_t index = SemanticReceiverLifecycleIndex(address);
  for (size_t probe = 0; probe < kSemanticReceiverLifecycleCapacity;
       ++probe) {
    SemanticReceiverLifecycleEntry &entry =
        g_semantic_receiver_lifecycles[index];
    const uint32_t observed =
        entry.address.load(std::memory_order_acquire);
    if (observed == address) {
      return &entry;
    }
    if (!observed) {
      return nullptr;
    }
    index = (index + 1) % kSemanticReceiverLifecycleCapacity;
  }
  return nullptr;
}

SemanticReceiverLifecycleEntry *FindOrClaimSemanticReceiverLifecycle(
    uint32_t address) {
  size_t index = SemanticReceiverLifecycleIndex(address);
  for (size_t probe = 0; probe < kSemanticReceiverLifecycleCapacity;
       ++probe) {
    SemanticReceiverLifecycleEntry &entry =
        g_semantic_receiver_lifecycles[index];
    uint32_t observed = entry.address.load(std::memory_order_acquire);
    if (observed == address) {
      return &entry;
    }
    if (!observed && entry.address.compare_exchange_strong(
                         observed, address, std::memory_order_acq_rel,
                         std::memory_order_acquire)) {
      return &entry;
    }
    index = (index + 1) % kSemanticReceiverLifecycleCapacity;
  }
  g_semantic_receiver_table_overflow.fetch_add(1,
                                                std::memory_order_relaxed);
  return nullptr;
}

void PublishSemanticReceiver(uint32_t address) {
  SemanticReceiverLifecycleEntry *entry =
      FindOrClaimSemanticReceiverLifecycle(address);
  if (!entry) {
    return;
  }
  const auto previous = static_cast<SemanticReceiverState>(
      entry->state.load(std::memory_order_acquire));
  if (previous == SemanticReceiverState::kLive ||
      previous == SemanticReceiverState::kDestroying) {
    g_semantic_receiver_stack_faults.fetch_add(1,
                                                std::memory_order_relaxed);
    return;
  }
  uint32_t generation =
      entry->generation.load(std::memory_order_relaxed) + 1;
  if (!generation) {
    generation = 1;
  }
  if (previous == SemanticReceiverState::kDestroyed) {
    g_semantic_receiver_address_reuses.fetch_add(1,
                                                  std::memory_order_relaxed);
  }
  entry->dispatches.store(0, std::memory_order_relaxed);
  entry->visibility_preparations.store(0, std::memory_order_relaxed);
  entry->render_state_preparations.store(0, std::memory_order_relaxed);
  entry->visibility_epoch.store(0, std::memory_order_relaxed);
  entry->render_state_epoch.store(0, std::memory_order_relaxed);
  entry->render_state_visibility_epoch.store(0,
                                              std::memory_order_relaxed);
  entry->dispatches_with_preparation.store(0, std::memory_order_relaxed);
  entry->dispatches_without_preparation.store(0,
                                               std::memory_order_relaxed);
  entry->dispatches_without_visibility.store(0,
                                              std::memory_order_relaxed);
  entry->dispatches_without_render_state.store(0,
                                                std::memory_order_relaxed);
  entry->generation.store(generation, std::memory_order_relaxed);
  entry->state.store(uint32_t(SemanticReceiverState::kLive),
                     std::memory_order_release);
  g_semantic_receiver_instances_published.fetch_add(
      1, std::memory_order_relaxed);
}

void BeginSemanticReceiverConstruction(uint32_t address) {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire)) {
    return;
  }
  g_semantic_receiver_constructor_entries.fetch_add(
      1, std::memory_order_relaxed);
  if (g_semantic_receiver_constructor_stack_depth ==
      kSemanticReceiverStackCapacity) {
    g_semantic_receiver_stack_faults.fetch_add(1,
                                                std::memory_order_relaxed);
    ++g_semantic_receiver_constructor_overflow_depth;
    return;
  }
  g_semantic_receiver_constructor_stack
      [g_semantic_receiver_constructor_stack_depth++] = address;
  g_semantic_receiver_constructor_open.fetch_add(1,
                                                  std::memory_order_relaxed);
}

void EndSemanticReceiverConstruction() {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire)) {
    return;
  }
  g_semantic_receiver_constructor_exits.fetch_add(
      1, std::memory_order_relaxed);
  if (g_semantic_receiver_constructor_overflow_depth) {
    --g_semantic_receiver_constructor_overflow_depth;
    return;
  }
  if (!g_semantic_receiver_constructor_stack_depth) {
    g_semantic_receiver_stack_faults.fetch_add(1,
                                                std::memory_order_relaxed);
    return;
  }
  const uint32_t address = g_semantic_receiver_constructor_stack
      [--g_semantic_receiver_constructor_stack_depth];
  g_semantic_receiver_constructor_open.fetch_sub(1,
                                                  std::memory_order_relaxed);
  PublishSemanticReceiver(address);
}

void BeginSemanticReceiverDestruction(uint32_t address) {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire)) {
    return;
  }
  g_semantic_receiver_destructor_entries.fetch_add(
      1, std::memory_order_relaxed);
  if (g_semantic_receiver_destructor_stack_depth ==
      kSemanticReceiverStackCapacity) {
    g_semantic_receiver_stack_faults.fetch_add(1,
                                                std::memory_order_relaxed);
    ++g_semantic_receiver_destructor_overflow_depth;
    return;
  }
  g_semantic_receiver_destructor_stack
      [g_semantic_receiver_destructor_stack_depth++] = address;
  g_semantic_receiver_destructor_open.fetch_add(1,
                                                 std::memory_order_relaxed);
  SemanticReceiverLifecycleEntry *entry =
      FindSemanticReceiverLifecycle(address);
  uint32_t expected_state = uint32_t(SemanticReceiverState::kLive);
  if (!entry || !entry->state.compare_exchange_strong(
                    expected_state,
                    uint32_t(SemanticReceiverState::kDestroying),
                    std::memory_order_acq_rel,
                    std::memory_order_acquire)) {
    g_semantic_receiver_destructors_without_instance.fetch_add(
        1, std::memory_order_relaxed);
  }
}

void EndSemanticReceiverDestruction() {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire)) {
    return;
  }
  g_semantic_receiver_destructor_exits.fetch_add(
      1, std::memory_order_relaxed);
  if (g_semantic_receiver_destructor_overflow_depth) {
    --g_semantic_receiver_destructor_overflow_depth;
    return;
  }
  if (!g_semantic_receiver_destructor_stack_depth) {
    g_semantic_receiver_stack_faults.fetch_add(1,
                                                std::memory_order_relaxed);
    return;
  }
  const uint32_t address = g_semantic_receiver_destructor_stack
      [--g_semantic_receiver_destructor_stack_depth];
  g_semantic_receiver_destructor_open.fetch_sub(1,
                                                 std::memory_order_relaxed);
  SemanticReceiverLifecycleEntry *entry =
      FindSemanticReceiverLifecycle(address);
  uint32_t expected_state = uint32_t(SemanticReceiverState::kDestroying);
  if (!entry || !entry->state.compare_exchange_strong(
                    expected_state,
                    uint32_t(SemanticReceiverState::kDestroyed),
                    std::memory_order_acq_rel,
                    std::memory_order_acquire)) {
    g_semantic_receiver_stack_faults.fetch_add(1,
                                                std::memory_order_relaxed);
    return;
  }
  g_semantic_receiver_instances_destroyed.fetch_add(
      1, std::memory_order_relaxed);
}

enum class SemanticReceiverStage {
  kVisibility,
  kRenderState,
};

void BeginSemanticReceiverStage(uint32_t address,
                                SemanticReceiverStage stage) {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire)) {
    return;
  }
  auto &entries = stage == SemanticReceiverStage::kVisibility
                      ? g_semantic_visibility_entries
                      : g_semantic_render_state_entries;
  auto &open = stage == SemanticReceiverStage::kVisibility
                   ? g_semantic_visibility_open
                   : g_semantic_render_state_open;
  auto &stack = stage == SemanticReceiverStage::kVisibility
                    ? g_semantic_visibility_stack
                    : g_semantic_render_state_stack;
  size_t &depth = stage == SemanticReceiverStage::kVisibility
                      ? g_semantic_visibility_stack_depth
                      : g_semantic_render_state_stack_depth;
  size_t &overflow_depth = stage == SemanticReceiverStage::kVisibility
                               ? g_semantic_visibility_overflow_depth
                               : g_semantic_render_state_overflow_depth;
  entries.fetch_add(1, std::memory_order_relaxed);
  if (depth == kSemanticReceiverStackCapacity) {
    g_semantic_stage_stack_faults.fetch_add(1,
                                             std::memory_order_relaxed);
    ++overflow_depth;
    return;
  }
  SemanticReceiverStageScope &scope = stack[depth++];
  scope = {};
  scope.address = address;
  SemanticReceiverLifecycleEntry *entry =
      FindSemanticReceiverLifecycle(address);
  if (!entry || entry->state.load(std::memory_order_acquire) !=
                    uint32_t(SemanticReceiverState::kLive)) {
    g_semantic_stage_unknown_receivers.fetch_add(
        1, std::memory_order_relaxed);
  } else {
    scope.generation = entry->generation.load(std::memory_order_relaxed);
  }
  open.fetch_add(1, std::memory_order_relaxed);
}

void EndSemanticReceiverStage(SemanticReceiverStage stage) {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire)) {
    return;
  }
  auto &exits = stage == SemanticReceiverStage::kVisibility
                    ? g_semantic_visibility_exits
                    : g_semantic_render_state_exits;
  auto &open = stage == SemanticReceiverStage::kVisibility
                   ? g_semantic_visibility_open
                   : g_semantic_render_state_open;
  auto &stack = stage == SemanticReceiverStage::kVisibility
                    ? g_semantic_visibility_stack
                    : g_semantic_render_state_stack;
  size_t &depth = stage == SemanticReceiverStage::kVisibility
                      ? g_semantic_visibility_stack_depth
                      : g_semantic_render_state_stack_depth;
  size_t &overflow_depth = stage == SemanticReceiverStage::kVisibility
                               ? g_semantic_visibility_overflow_depth
                               : g_semantic_render_state_overflow_depth;
  exits.fetch_add(1, std::memory_order_relaxed);
  if (overflow_depth) {
    --overflow_depth;
    return;
  }
  if (!depth) {
    g_semantic_stage_stack_faults.fetch_add(1,
                                             std::memory_order_relaxed);
    return;
  }
  const SemanticReceiverStageScope scope = stack[--depth];
  open.fetch_sub(1, std::memory_order_relaxed);
  SemanticReceiverLifecycleEntry *entry =
      FindSemanticReceiverLifecycle(scope.address);
  if (!scope.generation || !entry ||
      entry->state.load(std::memory_order_acquire) !=
          uint32_t(SemanticReceiverState::kLive) ||
      entry->generation.load(std::memory_order_relaxed) != scope.generation) {
    g_semantic_stage_unknown_receivers.fetch_add(
        1, std::memory_order_relaxed);
    return;
  }
  if (stage == SemanticReceiverStage::kVisibility) {
    entry->visibility_preparations.fetch_add(1,
                                              std::memory_order_relaxed);
    entry->visibility_epoch.fetch_add(1, std::memory_order_release);
  } else {
    entry->render_state_visibility_epoch.store(
        entry->visibility_epoch.load(std::memory_order_acquire),
        std::memory_order_relaxed);
    entry->render_state_preparations.fetch_add(1,
                                                std::memory_order_relaxed);
    entry->render_state_epoch.fetch_add(1, std::memory_order_release);
  }
}

bool SemanticVisibilitySpatialExponent(double value, uint8_t *exponent) {
  const float narrowed = static_cast<float>(value);
  if (!std::isfinite(narrowed) || narrowed < 0.0f) {
    return false;
  }
  *exponent = uint8_t((std::bit_cast<uint32_t>(narrowed) >> 23) & 0xFF);
  return true;
}

float LoadSemanticVisibilityGuestFloat(rex::memory::Memory *memory,
                                       uint32_t address) {
  const uint32_t bits = static_cast<uint32_t>(
      *rex::memory::GuestPtr<rex::be_u32 *>(memory->virtual_membase(),
                                            address));
  return std::bit_cast<float>(bits);
}

float SemanticVisibilitySumSquares3(float x, float y, float z) {
  const float xy = float(float(x * x) + float(y * y));
  return float(xy + float(z * z));
}

void ObserveSemanticVisibilitySpatialHelperInput(uint32_t query_address,
                                                 uint32_t endpoint_a_address,
                                                 uint32_t endpoint_b_address) {
  ActiveSemanticVisibilityRecord &record =
      g_active_semantic_visibility_record;
  if (!record.active) {
    g_semantic_visibility_spatial_shadow_input_without_record.fetch_add(
        1, std::memory_order_relaxed);
    return;
  }
  ++record.spatial_shadow_input_observations;
  if (record.spatial_shadow_pending ||
      record.spatial_shadow_input_observations >
          record.local_distance_passes) {
    g_semantic_visibility_policy_hook_faults.fetch_add(
        1, std::memory_order_relaxed);
    ++record.spatial_shadow_invalid_inputs;
  }
  record.spatial_shadow_pending = true;
  record.spatial_shadow_valid = false;
  if (!query_address || !endpoint_a_address || !endpoint_b_address ||
      (query_address & 3) || (endpoint_a_address & 3) ||
      (endpoint_b_address & 3)) {
    ++record.spatial_shadow_invalid_inputs;
    return;
  }
  rex::memory::Memory *memory =
      g_command_buffer_lineage_memory.load(std::memory_order_acquire);
  if (!memory) {
    ++record.spatial_shadow_invalid_inputs;
    return;
  }
  std::array<float, 10> values = {
      LoadSemanticVisibilityGuestFloat(memory, query_address + 0),
      LoadSemanticVisibilityGuestFloat(memory, query_address + 4),
      LoadSemanticVisibilityGuestFloat(memory, query_address + 8),
      LoadSemanticVisibilityGuestFloat(memory, query_address + 16),
      LoadSemanticVisibilityGuestFloat(memory, query_address + 20),
      LoadSemanticVisibilityGuestFloat(memory, query_address + 24),
      LoadSemanticVisibilityGuestFloat(memory, endpoint_a_address + 0),
      LoadSemanticVisibilityGuestFloat(memory, endpoint_a_address + 4),
      LoadSemanticVisibilityGuestFloat(memory, endpoint_a_address + 8),
      LoadSemanticVisibilityGuestFloat(memory, endpoint_b_address + 0),
  };
  const float endpoint_b_y =
      LoadSemanticVisibilityGuestFloat(memory, endpoint_b_address + 4);
  const float endpoint_b_z =
      LoadSemanticVisibilityGuestFloat(memory, endpoint_b_address + 8);
  if (!std::all_of(values.begin(), values.end(), [](float value) {
        return std::isfinite(value);
      }) ||
      !std::isfinite(endpoint_b_y) || !std::isfinite(endpoint_b_z)) {
    ++record.spatial_shadow_invalid_inputs;
    return;
  }
  if (values[4] < 0.0f) {
    record.spatial_shadow_prediction = true;
    record.spatial_shadow_valid = true;
    return;
  }
  const float half_x = float(float(values[9] - values[6]) * 0.5f);
  const float half_y = float(float(endpoint_b_y - values[7]) * 0.5f);
  const float half_z = float(float(endpoint_b_z - values[8]) * 0.5f);
  const float midpoint_x = float(values[6] + half_x);
  const float midpoint_y = float(values[7] + half_y);
  const float midpoint_z = float(values[8] + half_z);
  const float segment_distance_squared =
      SemanticVisibilitySumSquares3(half_x, half_y, half_z);
  const float query_x = float(midpoint_x - values[0]);
  const float query_y = float(midpoint_y - values[1]);
  const float query_z = float(midpoint_z - values[2]);
  const float query_distance_squared =
      SemanticVisibilitySumSquares3(query_x, query_y, query_z);
  const float lhs = float(values[3] * query_distance_squared);
  const float rhs = float(values[5] * segment_distance_squared);
  if (!std::isfinite(lhs) || !std::isfinite(rhs)) {
    ++record.spatial_shadow_invalid_inputs;
    return;
  }
  record.spatial_shadow_prediction = lhs <= rhs;
  record.spatial_shadow_valid = true;
}

float SemanticVisibilityDot4(float ax, float ay, float az, float aw,
                             float bx, float by, float bz, float bw) {
  const simde__m128 a = simde_mm_set_ps(ax, ay, az, aw);
  const simde__m128 b = simde_mm_set_ps(bx, by, bz, bw);
  return simde_mm_cvtss_f32(simde_mm_dp_ps(a, b, 0xFF));
}

uint32_t ClassifySemanticVisibilityCategory(
    const std::array<std::array<float, 4>, 6> &planes,
    const std::array<float, 3> &endpoint_a,
    const std::array<float, 3> &endpoint_b) {
  constexpr std::array<float, 3> kAxisSigns = {1.0f, 1.0f, -1.0f};
  uint32_t classification_bits = 0;
  for (const std::array<float, 4> &plane : planes) {
    const std::array<float, 3> axis = {
        plane[0] * kAxisSigns[0], plane[1] * kAxisSigns[1],
        plane[2] * kAxisSigns[2]};
    std::array<float, 3> positive{};
    std::array<float, 3> negative{};
    for (size_t axis_index = 0; axis_index < 3; ++axis_index) {
      const bool nonnegative = axis[axis_index] >= 0.0f;
      positive[axis_index] =
          nonnegative ? endpoint_b[axis_index] : endpoint_a[axis_index];
      negative[axis_index] =
          nonnegative ? endpoint_a[axis_index] : endpoint_b[axis_index];
    }
    const float positive_dot = SemanticVisibilityDot4(
        axis[0], axis[1], axis[2], plane[3], positive[0], positive[1],
        positive[2], 1.0f);
    const float negative_dot = SemanticVisibilityDot4(
        axis[0], axis[1], axis[2], plane[3], negative[0], negative[1],
        negative[2], 1.0f);
    if (positive_dot >= 0.0f) {
      classification_bits |= 1;
    }
    if (negative_dot > 0.0f) {
      classification_bits |= 3;
    }
  }
  return classification_bits == 3 ? 0 : (classification_bits == 1 ? 1 : 2);
}

void ObserveSemanticVisibilityCategoryHelperInput(
    uint32_t plane_address, const PPCVRegister &endpoint_a,
    const PPCVRegister &endpoint_b) {
  ActiveSemanticVisibilityRecord &record =
      g_active_semantic_visibility_record;
  if (!record.active) {
    g_semantic_visibility_category_shadow_input_without_record.fetch_add(
        1, std::memory_order_relaxed);
    return;
  }
  ++record.category_shadow_input_observations;
  if (record.category_shadow_pending ||
      record.category_shadow_input_observations >
          record.spatial_helper_passes ||
      record.category_shadow_input_observations >
          record.assembly_spatial_predicted_passes) {
    g_semantic_visibility_policy_hook_faults.fetch_add(
        1, std::memory_order_relaxed);
    ++record.category_shadow_invalid_inputs;
  }
  record.category_shadow_pending = true;
  record.category_shadow_valid = false;
  if (!plane_address || (plane_address & 15)) {
    ++record.category_shadow_invalid_inputs;
    return;
  }
  rex::memory::Memory *memory =
      g_command_buffer_lineage_memory.load(std::memory_order_acquire);
  if (!memory) {
    ++record.category_shadow_invalid_inputs;
    return;
  }

  const std::array<float, 3> a = {endpoint_a.f32[3], endpoint_a.f32[2],
                                  endpoint_a.f32[1]};
  const std::array<float, 3> b = {endpoint_b.f32[3], endpoint_b.f32[2],
                                  endpoint_b.f32[1]};
  if (!std::all_of(a.begin(), a.end(),
                   [](float value) { return std::isfinite(value); }) ||
      !std::all_of(b.begin(), b.end(),
                   [](float value) { return std::isfinite(value); })) {
    ++record.category_shadow_invalid_inputs;
    return;
  }

  std::array<std::array<float, 4>, 6> planes{};
  for (uint32_t plane_index = 0; plane_index < 6; ++plane_index) {
    const uint32_t offset = plane_address + plane_index * 16;
    planes[plane_index] = {
        LoadSemanticVisibilityGuestFloat(memory, offset + 0),
        LoadSemanticVisibilityGuestFloat(memory, offset + 4),
        LoadSemanticVisibilityGuestFloat(memory, offset + 8),
        LoadSemanticVisibilityGuestFloat(memory, offset + 12)};
    const std::array<float, 4> &plane = planes[plane_index];
    if (!std::all_of(plane.begin(), plane.end(),
                     [](float value) { return std::isfinite(value); })) {
      ++record.category_shadow_invalid_inputs;
      return;
    }
  }
  record.category_shadow_prediction =
      ClassifySemanticVisibilityCategory(planes, a, b);
  record.category_shadow_valid = true;
}

void BeginSemanticVisibilityRecord(uint32_t receiver_address,
                                   uint32_t record_index,
                                   uint32_t category,
                                   uint32_t descriptor_address,
                                   uint32_t runtime_address,
                                   double spatial_distance_squared) {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire)) {
    return;
  }
  g_semantic_visibility_record_entries.fetch_add(
      1, std::memory_order_relaxed);
  if (g_active_semantic_visibility_record.active) {
    g_semantic_visibility_record_stack_faults.fetch_add(
        1, std::memory_order_relaxed);
    g_semantic_visibility_entry_overlaps.fetch_add(
        1, std::memory_order_relaxed);
    g_semantic_visibility_records_open.fetch_sub(
        1, std::memory_order_relaxed);
    g_active_semantic_visibility_record = {};
  }

  ActiveSemanticVisibilityRecord &record =
      g_active_semantic_visibility_record;
  record.active = true;
  record.receiver_address = receiver_address;
  record.record_index = record_index;
  record.category = category;
  record.descriptor_address = descriptor_address;
  record.runtime_address = runtime_address;
  record.spatial_sample_valid = SemanticVisibilitySpatialExponent(
      spatial_distance_squared, &record.spatial_exponent);
  if (!record.spatial_sample_valid) {
    g_semantic_visibility_policy_invalid_spatial_values.fetch_add(
        1, std::memory_order_relaxed);
  }
  g_semantic_visibility_records_open.fetch_add(
      1, std::memory_order_relaxed);
  if (g_semantic_visibility_stack_depth) {
    const SemanticReceiverStageScope &scope =
        g_semantic_visibility_stack[g_semantic_visibility_stack_depth - 1];
    record.receiver_generation = scope.generation;
    record.joined = scope.address == receiver_address && scope.generation &&
                    descriptor_address && runtime_address &&
                    !(descriptor_address & 3) && !(runtime_address & 3);
  }
  if (!record.joined) {
    g_semantic_visibility_record_unknown_receivers.fetch_add(
        1, std::memory_order_relaxed);
  }
  if (category < kSemanticVisibilityCategoryCapacity) {
    g_semantic_visibility_categories[category].entries.fetch_add(
        1, std::memory_order_relaxed);
  } else {
    g_semantic_visibility_category_overflow.fetch_add(
        1, std::memory_order_relaxed);
  }
}

void ObserveSemanticVisibilityRuntimeThreshold(
    double spatial_distance_squared, double threshold_squared) {
  ActiveSemanticVisibilityRecord &record =
      g_active_semantic_visibility_record;
  if (!record.active) {
    g_semantic_visibility_runtime_threshold_without_record.fetch_add(
        1, std::memory_order_relaxed);
    return;
  }
  if (record.runtime_threshold_seen) {
    g_semantic_visibility_policy_hook_faults.fetch_add(
        1, std::memory_order_relaxed);
    g_semantic_visibility_duplicate_runtime_threshold.fetch_add(
        1, std::memory_order_relaxed);
    return;
  }
  record.runtime_threshold_seen = true;
  if (!std::isfinite(spatial_distance_squared) ||
      !std::isfinite(threshold_squared) || spatial_distance_squared < 0.0 ||
      threshold_squared < 0.0) {
    g_semantic_visibility_policy_invalid_threshold_values.fetch_add(
        1, std::memory_order_relaxed);
    return;
  }
  record.runtime_distance_less =
      spatial_distance_squared < threshold_squared;
}

void ObserveSemanticVisibilityDescriptorThreshold(
    double spatial_distance_squared, double threshold_squared) {
  ActiveSemanticVisibilityRecord &record =
      g_active_semantic_visibility_record;
  if (!record.active) {
    g_semantic_visibility_descriptor_threshold_without_record.fetch_add(
        1, std::memory_order_relaxed);
    return;
  }
  if (record.descriptor_threshold_seen) {
    g_semantic_visibility_policy_hook_faults.fetch_add(
        1, std::memory_order_relaxed);
    g_semantic_visibility_duplicate_descriptor_threshold.fetch_add(
        1, std::memory_order_relaxed);
    return;
  }
  record.descriptor_threshold_seen = true;
  if (!std::isfinite(spatial_distance_squared) ||
      !std::isfinite(threshold_squared) || spatial_distance_squared < 0.0 ||
      threshold_squared < 0.0) {
    g_semantic_visibility_policy_invalid_threshold_values.fetch_add(
        1, std::memory_order_relaxed);
    return;
  }
  record.descriptor_distance_exceeded =
      spatial_distance_squared > threshold_squared;
}

void ObserveSemanticVisibilityCandidateThreshold(double threshold,
                                                  double zero_reference) {
  ActiveSemanticVisibilityRecord &record =
      g_active_semantic_visibility_record;
  if (!record.active) {
    g_semantic_visibility_candidate_threshold_without_record.fetch_add(
        1, std::memory_order_relaxed);
    return;
  }
  ++record.candidate_threshold_observations;
  if (!std::isfinite(threshold) || !std::isfinite(zero_reference)) {
    g_semantic_visibility_oracle_invalid_values.fetch_add(
        1, std::memory_order_relaxed);
    return;
  }
  if (threshold >= zero_reference) {
    ++record.candidate_threshold_passes;
  }
}

void ObserveSemanticVisibilityLocalDistance(double distance_squared,
                                             double threshold_squared) {
  ActiveSemanticVisibilityRecord &record =
      g_active_semantic_visibility_record;
  if (!record.active) {
    g_semantic_visibility_local_distance_without_record.fetch_add(
        1, std::memory_order_relaxed);
    return;
  }
  if (record.local_distance_observations >=
      record.candidate_threshold_passes) {
    g_semantic_visibility_policy_hook_faults.fetch_add(
        1, std::memory_order_relaxed);
    g_semantic_visibility_local_distance_without_candidate_pass.fetch_add(
        1, std::memory_order_relaxed);
  }
  ++record.local_distance_observations;
  if (!std::isfinite(distance_squared) ||
      !std::isfinite(threshold_squared) || distance_squared < 0.0 ||
      threshold_squared < 0.0) {
    g_semantic_visibility_oracle_invalid_values.fetch_add(
        1, std::memory_order_relaxed);
    return;
  }
  if (distance_squared <= threshold_squared) {
    ++record.local_distance_passes;
  }
}

void ObserveSemanticVisibilitySpatialHelperResult(uint32_t result) {
  ActiveSemanticVisibilityRecord &record =
      g_active_semantic_visibility_record;
  if (!record.active) {
    g_semantic_visibility_spatial_helper_without_record.fetch_add(
        1, std::memory_order_relaxed);
    return;
  }
  if (!record.spatial_shadow_pending) {
    g_semantic_visibility_spatial_shadow_result_without_input.fetch_add(
        1, std::memory_order_relaxed);
  } else {
    if (record.spatial_shadow_valid) {
      ++record.spatial_shadow_comparisons;
      const bool title_result = (result & 0xFF) != 0;
      if (record.spatial_shadow_prediction) {
        ++record.assembly_spatial_predicted_passes;
      }
      if (record.spatial_shadow_prediction == title_result) {
        ++record.spatial_shadow_matches;
      } else if (record.spatial_shadow_prediction) {
        ++record.spatial_shadow_false_positive;
      } else {
        ++record.spatial_shadow_false_negative;
      }
    }
    record.spatial_shadow_pending = false;
    record.spatial_shadow_valid = false;
  }
  if (record.spatial_helper_observations >= record.local_distance_passes) {
    g_semantic_visibility_policy_hook_faults.fetch_add(
        1, std::memory_order_relaxed);
    g_semantic_visibility_spatial_helper_without_local_pass.fetch_add(
        1, std::memory_order_relaxed);
  }
  ++record.spatial_helper_observations;
  if ((result & 0xFF) != 0) {
    ++record.spatial_helper_passes;
  }
}

void ObserveSemanticVisibilityCategoryHelperResult(uint32_t result) {
  ActiveSemanticVisibilityRecord &record =
      g_active_semantic_visibility_record;
  if (!record.active) {
    g_semantic_visibility_category_helper_without_record.fetch_add(
        1, std::memory_order_relaxed);
    return;
  }
  if (!record.category_shadow_pending) {
    g_semantic_visibility_category_shadow_result_without_input.fetch_add(
        1, std::memory_order_relaxed);
  } else {
    if (record.category_shadow_valid) {
      ++record.category_shadow_comparisons;
      if (record.category_shadow_prediction <
          record.assembly_category_predictions.size()) {
        ++record.assembly_category_predictions[
            record.category_shadow_prediction];
      } else {
        ++record.category_shadow_invalid_inputs;
      }
      if (record.category_shadow_prediction == result) {
        ++record.category_shadow_matches;
      } else {
        ++record.category_shadow_false_result;
      }
    }
    record.category_shadow_pending = false;
    record.category_shadow_valid = false;
  }
  if (record.category_helper_observations >=
      record.spatial_helper_passes) {
    g_semantic_visibility_policy_hook_faults.fetch_add(
        1, std::memory_order_relaxed);
    g_semantic_visibility_category_helper_without_spatial_pass.fetch_add(
        1, std::memory_order_relaxed);
  }
  ++record.category_helper_observations;
  if (result < record.category_helper_results.size()) {
    ++record.category_helper_results[result];
  } else {
    g_semantic_visibility_policy_hook_faults.fetch_add(
        1, std::memory_order_relaxed);
    g_semantic_visibility_category_helper_invalid_result.fetch_add(
        1, std::memory_order_relaxed);
  }
}

void ObserveSemanticVisibilityLod(uint32_t lod_index) {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire)) {
    return;
  }
  ActiveSemanticVisibilityRecord &record =
      g_active_semantic_visibility_record;
  if (!record.active) {
    g_semantic_visibility_record_stack_faults.fetch_add(
        1, std::memory_order_relaxed);
    g_semantic_visibility_lod_without_record.fetch_add(
        1, std::memory_order_relaxed);
    return;
  }
  if (record.lod_seen) {
    record.lod_index = lod_index;
    g_semantic_visibility_lod_rewrites.fetch_add(
        1, std::memory_order_relaxed);
    return;
  }
  record.lod_seen = true;
  record.lod_index = lod_index;
  g_semantic_visibility_lod_writes.fetch_add(1,
                                              std::memory_order_relaxed);
  if (record.category < kSemanticVisibilityCategoryCapacity) {
    g_semantic_visibility_categories[record.category].lod_writes.fetch_add(
        1, std::memory_order_relaxed);
  }
  if (lod_index < kSemanticVisibilityLodCapacity) {
    g_semantic_visibility_lod_histogram[lod_index].fetch_add(
        1, std::memory_order_relaxed);
  } else {
    g_semantic_visibility_lod_overflow.fetch_add(
        1, std::memory_order_relaxed);
  }
}

void ObserveSemanticVisibilityResult(uint32_t selected) {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire)) {
    return;
  }
  ActiveSemanticVisibilityRecord &record =
      g_active_semantic_visibility_record;
  if (!record.active) {
    g_semantic_visibility_record_stack_faults.fetch_add(
        1, std::memory_order_relaxed);
    g_semantic_visibility_result_without_record.fetch_add(
        1, std::memory_order_relaxed);
    return;
  }
  if (record.result_seen) {
    g_semantic_visibility_record_stack_faults.fetch_add(
        1, std::memory_order_relaxed);
    g_semantic_visibility_duplicate_result.fetch_add(
        1, std::memory_order_relaxed);
    return;
  }
  record.result_seen = true;
  record.selected = selected != 0;
  g_semantic_visibility_result_value_histogram[selected & 0xFF].fetch_add(
      1, std::memory_order_relaxed);
  g_semantic_visibility_result_observations.fetch_add(
      1, std::memory_order_relaxed);
}

void EndSemanticVisibilityRecord(uint32_t receiver_address,
                                 uint32_t record_index) {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire)) {
    return;
  }
  g_semantic_visibility_record_completions.fetch_add(
      1, std::memory_order_relaxed);
  ActiveSemanticVisibilityRecord record =
      g_active_semantic_visibility_record;
  g_active_semantic_visibility_record = {};
  if (!record.active) {
    g_semantic_visibility_record_stack_faults.fetch_add(
        1, std::memory_order_relaxed);
    g_semantic_visibility_completion_without_record.fetch_add(
        1, std::memory_order_relaxed);
    return;
  }
  g_semantic_visibility_records_open.fetch_sub(
      1, std::memory_order_relaxed);
  if (record.receiver_address != receiver_address ||
      record.record_index != record_index) {
    g_semantic_visibility_record_identity_mismatches.fetch_add(
        1, std::memory_order_relaxed);
  }

  SemanticVisibilityCategoryStats *category =
      record.category < kSemanticVisibilityCategoryCapacity
          ? &g_semantic_visibility_categories[record.category]
          : nullptr;
  if (category) {
    category->completions.fetch_add(1, std::memory_order_relaxed);
  }
  if (!record.result_seen) {
    g_semantic_visibility_early_rejected_records.fetch_add(
        1, std::memory_order_relaxed);
    if (category) {
      category->early_rejected.fetch_add(1,
                                          std::memory_order_relaxed);
    }
  } else if (record.selected) {
    g_semantic_visibility_selected_records.fetch_add(
        1, std::memory_order_relaxed);
    if (category) {
      category->selected.fetch_add(1, std::memory_order_relaxed);
    }
  } else {
    g_semantic_visibility_rejected_records.fetch_add(
        1, std::memory_order_relaxed);
    if (category) {
      category->rejected.fetch_add(1, std::memory_order_relaxed);
    }
  }
  const SemanticVisibilityPolicyOutcome policy_outcome =
      !record.result_seen
          ? SemanticVisibilityPolicyOutcome::kEarlyRejected
          : (record.selected ? SemanticVisibilityPolicyOutcome::kSelected
                             : SemanticVisibilityPolicyOutcome::kRejected);
  const size_t policy_outcome_index = size_t(policy_outcome);
  if (record.spatial_shadow_pending) {
    ++record.spatial_shadow_invalid_inputs;
    g_semantic_visibility_policy_hook_faults.fetch_add(
        1, std::memory_order_relaxed);
  }
  if (record.category_shadow_pending) {
    ++record.category_shadow_invalid_inputs;
    g_semantic_visibility_policy_hook_faults.fetch_add(
        1, std::memory_order_relaxed);
  }
  if (record.category < kSemanticVisibilityCategoryCapacity) {
    SemanticVisibilityPolicyStats &policy =
        g_semantic_visibility_policy_categories[record.category]
                                              [policy_outcome_index];
    policy.records.fetch_add(1, std::memory_order_relaxed);
    if (record.spatial_sample_valid) {
      policy.spatial_samples.fetch_add(1, std::memory_order_relaxed);
    }
    if (record.runtime_threshold_seen) {
      policy.runtime_threshold_observations.fetch_add(
          1, std::memory_order_relaxed);
      if (record.runtime_distance_less) {
        policy.runtime_distance_less.fetch_add(
            1, std::memory_order_relaxed);
      }
    }
    if (record.descriptor_threshold_seen) {
      policy.descriptor_threshold_observations.fetch_add(
          1, std::memory_order_relaxed);
      if (record.descriptor_distance_exceeded) {
        policy.descriptor_distance_exceeded.fetch_add(
            1, std::memory_order_relaxed);
      }
    }
    SemanticVisibilityOracleStats &oracle =
        g_semantic_visibility_oracle_categories[record.category]
                                                [policy_outcome_index];
    oracle.records.fetch_add(1, std::memory_order_relaxed);
    oracle.candidate_threshold_observations.fetch_add(
        record.candidate_threshold_observations,
        std::memory_order_relaxed);
    oracle.candidate_threshold_passes.fetch_add(
        record.candidate_threshold_passes, std::memory_order_relaxed);
    oracle.local_distance_observations.fetch_add(
        record.local_distance_observations, std::memory_order_relaxed);
    oracle.local_distance_passes.fetch_add(
        record.local_distance_passes, std::memory_order_relaxed);
    oracle.spatial_helper_observations.fetch_add(
        record.spatial_helper_observations, std::memory_order_relaxed);
    oracle.spatial_helper_passes.fetch_add(
        record.spatial_helper_passes, std::memory_order_relaxed);
    oracle.category_helper_observations.fetch_add(
        record.category_helper_observations, std::memory_order_relaxed);
    for (size_t result = 0; result < record.category_helper_results.size();
         ++result) {
      oracle.category_results[result].fetch_add(
          record.category_helper_results[result],
          std::memory_order_relaxed);
    }
    SemanticVisibilityShadowStats &shadow =
        g_semantic_visibility_shadow_categories[record.category]
                                               [policy_outcome_index];
    if (record.category_helper_observations) {
      shadow.modelled_records.fetch_add(1, std::memory_order_relaxed);
      const bool result_1_seen = record.category_helper_results[1] != 0;
      const bool result_2_seen = record.category_helper_results[2] != 0;
      const bool predicted_selected = result_1_seen || result_2_seen;
      const bool title_selected = record.result_seen && record.selected;
      (predicted_selected ? shadow.predicted_selected
                          : shadow.predicted_rejected)
          .fetch_add(1, std::memory_order_relaxed);
      if (predicted_selected == title_selected) {
        shadow.title_matches.fetch_add(1, std::memory_order_relaxed);
      } else if (predicted_selected) {
        shadow.false_positive.fetch_add(1, std::memory_order_relaxed);
      } else {
        shadow.false_negative.fetch_add(1, std::memory_order_relaxed);
      }
      if (result_1_seen) {
        shadow.result_1_records.fetch_add(1, std::memory_order_relaxed);
      }
      if (result_2_seen) {
        shadow.result_2_records.fetch_add(1, std::memory_order_relaxed);
      }
      if (result_1_seen && result_2_seen) {
        shadow.mixed_nonzero_records.fetch_add(1,
                                               std::memory_order_relaxed);
      }
    }
    SemanticVisibilitySpatialShadowStats &spatial_shadow =
        g_semantic_visibility_spatial_shadow_categories[record.category]
                                                       [policy_outcome_index];
    if (record.spatial_shadow_input_observations ||
        record.spatial_shadow_invalid_inputs) {
      spatial_shadow.input_observations.fetch_add(
          record.spatial_shadow_input_observations,
          std::memory_order_relaxed);
      spatial_shadow.comparisons.fetch_add(
          record.spatial_shadow_comparisons, std::memory_order_relaxed);
      spatial_shadow.matches.fetch_add(record.spatial_shadow_matches,
                                       std::memory_order_relaxed);
      spatial_shadow.false_positive.fetch_add(
          record.spatial_shadow_false_positive, std::memory_order_relaxed);
      spatial_shadow.false_negative.fetch_add(
          record.spatial_shadow_false_negative, std::memory_order_relaxed);
      spatial_shadow.invalid_inputs.fetch_add(
          record.spatial_shadow_invalid_inputs, std::memory_order_relaxed);
    }
    SemanticVisibilityCategoryShadowStats &category_shadow =
        g_semantic_visibility_category_shadow_categories[record.category]
                                                         [policy_outcome_index];
    if (record.category_shadow_input_observations ||
        record.category_shadow_invalid_inputs) {
      category_shadow.input_observations.fetch_add(
          record.category_shadow_input_observations,
          std::memory_order_relaxed);
      category_shadow.comparisons.fetch_add(
          record.category_shadow_comparisons, std::memory_order_relaxed);
      category_shadow.matches.fetch_add(record.category_shadow_matches,
                                        std::memory_order_relaxed);
      category_shadow.false_result.fetch_add(
          record.category_shadow_false_result, std::memory_order_relaxed);
      category_shadow.invalid_inputs.fetch_add(
          record.category_shadow_invalid_inputs, std::memory_order_relaxed);
    }
    SemanticVisibilityAssemblyShadowStats &assembly =
        g_semantic_visibility_assembly_shadow_categories[record.category]
                                                        [policy_outcome_index];
    assembly.records.fetch_add(1, std::memory_order_relaxed);
    assembly.spatial_input_observations.fetch_add(
        record.spatial_shadow_input_observations, std::memory_order_relaxed);
    assembly.spatial_predicted_passes.fetch_add(
        record.assembly_spatial_predicted_passes, std::memory_order_relaxed);
    assembly.category_input_observations.fetch_add(
        record.category_shadow_input_observations, std::memory_order_relaxed);
    uint32_t assembly_category_predictions = 0;
    for (size_t result = 0;
         result < record.assembly_category_predictions.size(); ++result) {
      const uint32_t count = record.assembly_category_predictions[result];
      assembly.category_predictions[result].fetch_add(
          count, std::memory_order_relaxed);
      assembly_category_predictions += count;
    }
    const uint32_t assembly_invalid_inputs =
        record.spatial_shadow_invalid_inputs +
        record.category_shadow_invalid_inputs +
        uint32_t(record.assembly_spatial_predicted_passes !=
                 record.category_shadow_input_observations) +
        uint32_t(assembly_category_predictions !=
                 record.category_shadow_comparisons);
    assembly.invalid_inputs.fetch_add(assembly_invalid_inputs,
                                      std::memory_order_relaxed);
    PublishSemanticVisibilityWorkset(record, assembly_invalid_inputs);
    if (record.category_shadow_input_observations) {
      assembly.modelled_records.fetch_add(1, std::memory_order_relaxed);
      const bool predicted_selected =
          record.assembly_category_predictions[1] != 0 ||
          record.assembly_category_predictions[2] != 0;
      const bool title_selected = record.result_seen && record.selected;
      (predicted_selected ? assembly.predicted_selected
                          : assembly.predicted_rejected)
          .fetch_add(1, std::memory_order_relaxed);
      if (predicted_selected == title_selected) {
        assembly.title_matches.fetch_add(1, std::memory_order_relaxed);
      } else if (predicted_selected) {
        assembly.false_positive.fetch_add(1, std::memory_order_relaxed);
      } else {
        assembly.false_negative.fetch_add(1, std::memory_order_relaxed);
      }
    }
  }
  if (record.spatial_sample_valid) {
    g_semantic_visibility_spatial_exponents[policy_outcome_index]
                                            [record.spatial_exponent]
        .fetch_add(1, std::memory_order_relaxed);
  }
  if (record.category == 9 && record.selected) {
    (record.lod_seen ? g_semantic_visibility_selected_with_lod
                     : g_semantic_visibility_selected_without_lod)
        .fetch_add(1, std::memory_order_relaxed);
  }
  if (record.lod_seen && record.result_seen && !record.selected) {
    g_semantic_visibility_record_identity_mismatches.fetch_add(
        1, std::memory_order_relaxed);
  }
}

bool ResolveSemanticReceiver(uint32_t address, uint32_t *generation,
                             uint64_t *visibility_epoch,
                             uint64_t *render_state_epoch,
                             uint64_t *render_state_visibility_epoch) {
  g_semantic_receiver_dispatches.fetch_add(1, std::memory_order_relaxed);
  SemanticReceiverLifecycleEntry *entry =
      FindSemanticReceiverLifecycle(address);
  if (!entry) {
    g_semantic_receiver_unregistered_dispatches.fetch_add(
        1, std::memory_order_relaxed);
    return false;
  }
  const auto state = static_cast<SemanticReceiverState>(
      entry->state.load(std::memory_order_acquire));
  if (state != SemanticReceiverState::kLive) {
    if (state == SemanticReceiverState::kDestroying) {
      g_semantic_receiver_destroying_dispatches.fetch_add(
          1, std::memory_order_relaxed);
    } else {
      g_semantic_receiver_destroyed_dispatches.fetch_add(
          1, std::memory_order_relaxed);
    }
    return false;
  }
  *generation = entry->generation.load(std::memory_order_relaxed);
  if (entry->state.load(std::memory_order_acquire) !=
      uint32_t(SemanticReceiverState::kLive)) {
    g_semantic_receiver_destroying_dispatches.fetch_add(
        1, std::memory_order_relaxed);
    return false;
  }
  entry->dispatches.fetch_add(1, std::memory_order_relaxed);
  *visibility_epoch =
      entry->visibility_epoch.load(std::memory_order_acquire);
  *render_state_epoch =
      entry->render_state_epoch.load(std::memory_order_acquire);
  *render_state_visibility_epoch =
      entry->render_state_visibility_epoch.load(std::memory_order_relaxed);
  if (!*visibility_epoch) {
    entry->dispatches_without_visibility.fetch_add(
        1, std::memory_order_relaxed);
  }
  if (!*render_state_epoch) {
    entry->dispatches_without_render_state.fetch_add(
        1, std::memory_order_relaxed);
  }
  if (*visibility_epoch && *render_state_epoch &&
      *render_state_visibility_epoch) {
    entry->dispatches_with_preparation.fetch_add(
        1, std::memory_order_relaxed);
  } else {
    entry->dispatches_without_preparation.fetch_add(
        1, std::memory_order_relaxed);
  }
  g_semantic_receiver_live_dispatches.fetch_add(
      1, std::memory_order_relaxed);
  return *generation != 0;
}

void PushIndirectContextOrigin(uint32_t function_address,
                               uint32_t return_address, uint32_t r3,
                               uint32_t r4, uint32_t r5, uint32_t r6,
                               uint32_t r7, uint32_t r8, uint32_t r9,
                               uint32_t r10) {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire)) {
    return;
  }
  g_indirect_context_entries.fetch_add(1, std::memory_order_relaxed);
  if (g_indirect_context_stack_depth == kIndirectContextStackCapacity) {
    g_indirect_context_stack_faults.fetch_add(1,
                                               std::memory_order_relaxed);
    ++g_indirect_context_stack_overflow_depth;
    return;
  }
  IndirectConstructorOrigin::Owner::Producer::Context &context =
      g_indirect_context_stack[g_indirect_context_stack_depth++];
  context = {};
  context.function_address = function_address;
  context.return_address = return_address;
  context.arguments = {r3, r4, r5, r6, r7, r8, r9, r10};
  context.root_address =
      DeriveIndirectContextRoot(function_address, context.arguments);
  if (function_address == 0x82417BC0) {
    context.semantic_receiver_address = r3;
    context.semantic_receiver_known = ResolveSemanticReceiver(
        r3, &context.semantic_receiver_generation,
        &context.semantic_visibility_epoch,
        &context.semantic_render_state_epoch,
        &context.semantic_render_state_visibility_epoch);
  }
  context.valid = true;
  g_indirect_context_invocations_open.fetch_add(1,
                                                 std::memory_order_relaxed);
}

void PopIndirectContextOrigin(uint32_t function_address) {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire)) {
    return;
  }
  g_indirect_context_exits.fetch_add(1, std::memory_order_relaxed);
  if (g_indirect_context_stack_overflow_depth) {
    --g_indirect_context_stack_overflow_depth;
    return;
  }
  if (!g_indirect_context_stack_depth) {
    g_indirect_context_stack_faults.fetch_add(1,
                                               std::memory_order_relaxed);
    return;
  }
  if (g_indirect_context_stack[g_indirect_context_stack_depth - 1]
          .function_address != function_address) {
    g_indirect_context_stack_faults.fetch_add(1,
                                               std::memory_order_relaxed);
    g_indirect_context_invocations_open.fetch_sub(
        g_indirect_context_stack_depth, std::memory_order_relaxed);
    g_indirect_context_stack_depth = 0;
    return;
  }
  --g_indirect_context_stack_depth;
  g_indirect_context_invocations_open.fetch_sub(1,
                                                 std::memory_order_relaxed);
}

void PushIndirectProducerOrigin(uint32_t function_address,
                                uint32_t return_address, uint32_t r3,
                                uint32_t r4, uint32_t r5, uint32_t r6,
                                uint32_t r7, uint32_t r8, uint32_t r9,
                                uint32_t r10) {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire)) {
    return;
  }
  g_indirect_producer_entries.fetch_add(1, std::memory_order_relaxed);
  if (g_indirect_producer_stack_depth == kIndirectProducerStackCapacity) {
    g_indirect_producer_stack_faults.fetch_add(1,
                                                std::memory_order_relaxed);
    ++g_indirect_producer_stack_overflow_depth;
    return;
  }
  IndirectConstructorOrigin::Owner::Producer &producer =
      g_indirect_producer_stack[g_indirect_producer_stack_depth++];
  producer = {};
  producer.function_address = function_address;
  producer.return_address = return_address;
  producer.arguments = {r3, r4, r5, r6, r7, r8, r9, r10};
  const uint32_t expected_context =
      ExpectedIndirectContextFunction(function_address, return_address);
  if (expected_context && g_indirect_context_stack_depth) {
    const IndirectConstructorOrigin::Owner::Producer::Context &context =
        g_indirect_context_stack[g_indirect_context_stack_depth - 1];
    if (context.valid && context.function_address == expected_context &&
        context.root_address == r3) {
      producer.context = context;
    } else {
      g_indirect_producer_context_mismatches.fetch_add(
          1, std::memory_order_relaxed);
    }
  } else if (expected_context) {
    g_indirect_producer_context_mismatches.fetch_add(
        1, std::memory_order_relaxed);
  }
  if (!producer.context.valid) {
    g_indirect_producers_without_context_origin.fetch_add(
        1, std::memory_order_relaxed);
  }
  producer.valid = true;
  g_indirect_producer_invocations_open.fetch_add(
      1, std::memory_order_relaxed);
}

void PopIndirectProducerOrigin(uint32_t function_address) {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire)) {
    return;
  }
  g_indirect_producer_exits.fetch_add(1, std::memory_order_relaxed);
  if (g_indirect_producer_stack_overflow_depth) {
    --g_indirect_producer_stack_overflow_depth;
    return;
  }
  if (!g_indirect_producer_stack_depth) {
    g_indirect_producer_stack_faults.fetch_add(1,
                                                std::memory_order_relaxed);
    return;
  }
  if (g_indirect_producer_stack[g_indirect_producer_stack_depth - 1]
          .function_address != function_address) {
    g_indirect_producer_stack_faults.fetch_add(1,
                                                std::memory_order_relaxed);
    g_indirect_producer_invocations_open.fetch_sub(
        g_indirect_producer_stack_depth, std::memory_order_relaxed);
    g_indirect_producer_stack_depth = 0;
    return;
  }
  --g_indirect_producer_stack_depth;
  g_indirect_producer_invocations_open.fetch_sub(
      1, std::memory_order_relaxed);
}

void PushIndirectOwnerOrigin(uint32_t function_address,
                             uint32_t return_address, uint32_t r3,
                             uint32_t r4, uint32_t r5, uint32_t r6,
                             uint32_t r7, uint32_t r8, uint32_t r9,
                             uint32_t r10) {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire)) {
    return;
  }
  g_indirect_owner_entries.fetch_add(1, std::memory_order_relaxed);
  if (g_indirect_owner_stack_depth == kIndirectOwnerStackCapacity) {
    g_indirect_owner_stack_faults.fetch_add(1,
                                             std::memory_order_relaxed);
    ++g_indirect_owner_stack_overflow_depth;
    return;
  }
  IndirectConstructorOrigin::Owner &owner =
      g_indirect_owner_stack[g_indirect_owner_stack_depth++];
  owner = {};
  owner.function_address = function_address;
  owner.return_address = return_address;
  owner.arguments = {r3, r4, r5, r6, r7, r8, r9, r10};
  const uint32_t expected_producer =
      ExpectedIndirectProducerFunction(function_address, return_address);
  if (expected_producer && g_indirect_producer_stack_depth) {
    const IndirectConstructorOrigin::Owner::Producer &producer =
        g_indirect_producer_stack[g_indirect_producer_stack_depth - 1];
    if (producer.valid && producer.function_address == expected_producer) {
      owner.producer = producer;
    } else {
      g_indirect_owner_producer_mismatches.fetch_add(
          1, std::memory_order_relaxed);
    }
  } else if (expected_producer) {
    g_indirect_owner_producer_mismatches.fetch_add(
        1, std::memory_order_relaxed);
  }
  if (!owner.producer.valid) {
    g_indirect_owners_without_producer_origin.fetch_add(
        1, std::memory_order_relaxed);
  }
  owner.valid = true;
  g_indirect_owner_invocations_open.fetch_add(1,
                                               std::memory_order_relaxed);
}

void PopIndirectOwnerOrigin(uint32_t function_address) {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire)) {
    return;
  }
  g_indirect_owner_exits.fetch_add(1, std::memory_order_relaxed);
  if (g_indirect_owner_stack_overflow_depth) {
    --g_indirect_owner_stack_overflow_depth;
    return;
  }
  if (!g_indirect_owner_stack_depth) {
    g_indirect_owner_stack_faults.fetch_add(1,
                                             std::memory_order_relaxed);
    return;
  }
  if (g_indirect_owner_stack[g_indirect_owner_stack_depth - 1]
          .function_address != function_address) {
    g_indirect_owner_stack_faults.fetch_add(1,
                                             std::memory_order_relaxed);
    g_indirect_owner_invocations_open.fetch_sub(
        g_indirect_owner_stack_depth, std::memory_order_relaxed);
    g_indirect_owner_stack_depth = 0;
    return;
  }
  --g_indirect_owner_stack_depth;
  g_indirect_owner_invocations_open.fetch_sub(1,
                                               std::memory_order_relaxed);
}

void PushIndirectConstructorOrigin(uint32_t function_address,
                                   uint32_t return_address, uint32_t r3,
                                   uint32_t r4, uint32_t r5, uint32_t r6,
                                   uint32_t r7, uint32_t r8, uint32_t r9,
                                   uint32_t r10) {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire)) {
    return;
  }
  g_indirect_constructor_entries.fetch_add(1,
                                             std::memory_order_relaxed);
  if (g_indirect_constructor_stack_depth ==
      kIndirectConstructorStackCapacity) {
    g_indirect_constructor_stack_faults.fetch_add(
        1, std::memory_order_relaxed);
    ++g_indirect_constructor_stack_overflow_depth;
    return;
  }
  IndirectConstructorOrigin &origin =
      g_indirect_constructor_stack[g_indirect_constructor_stack_depth++];
  origin = {};
  origin.function_address = function_address;
  origin.return_address = return_address;
  origin.arguments = {r3, r4, r5, r6, r7, r8, r9, r10};
  const uint32_t expected_owner =
      ExpectedIndirectOwnerFunction(function_address, return_address);
  if (expected_owner && g_indirect_owner_stack_depth) {
    const IndirectConstructorOrigin::Owner &owner =
        g_indirect_owner_stack[g_indirect_owner_stack_depth - 1];
    if (owner.valid && owner.function_address == expected_owner) {
      origin.owner = owner;
    } else {
      g_indirect_constructor_owner_mismatches.fetch_add(
          1, std::memory_order_relaxed);
    }
  } else if (expected_owner) {
    g_indirect_constructor_owner_mismatches.fetch_add(
        1, std::memory_order_relaxed);
  }
  if (!origin.owner.valid) {
    g_indirect_constructors_without_owner_origin.fetch_add(
        1, std::memory_order_relaxed);
  }
  origin.valid = true;
  g_indirect_constructor_invocations_open.fetch_add(
      1, std::memory_order_relaxed);
}

void PopIndirectConstructorOrigin(uint32_t function_address) {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire)) {
    return;
  }
  g_indirect_constructor_exits.fetch_add(1,
                                          std::memory_order_relaxed);
  if (g_indirect_constructor_stack_overflow_depth) {
    --g_indirect_constructor_stack_overflow_depth;
    return;
  }
  if (!g_indirect_constructor_stack_depth) {
    g_indirect_constructor_stack_faults.fetch_add(
        1, std::memory_order_relaxed);
    return;
  }
  if (g_indirect_constructor_stack[g_indirect_constructor_stack_depth - 1]
          .function_address != function_address) {
    g_indirect_constructor_stack_faults.fetch_add(
        1, std::memory_order_relaxed);
    g_indirect_constructor_invocations_open.fetch_sub(
        g_indirect_constructor_stack_depth, std::memory_order_relaxed);
    g_indirect_constructor_stack_depth = 0;
    return;
  }
  --g_indirect_constructor_stack_depth;
  g_indirect_constructor_invocations_open.fetch_sub(
      1, std::memory_order_relaxed);
}

IndirectConstructorOrigin CurrentIndirectConstructorOrigin(
    uint32_t function_address) {
  if (!g_indirect_constructor_stack_depth) {
    g_indirect_packets_without_constructor_origin.fetch_add(
        1, std::memory_order_relaxed);
    return {};
  }
  const IndirectConstructorOrigin &origin =
      g_indirect_constructor_stack[g_indirect_constructor_stack_depth - 1];
  if (!origin.valid || origin.function_address != function_address) {
    g_indirect_packets_without_constructor_origin.fetch_add(
        1, std::memory_order_relaxed);
    return {};
  }
  return origin;
}

void RecordTitleIndirectPacket(uint32_t packet_guest_address,
                               uint32_t constructor_store_address,
                               uint32_t constructor_function_address) {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire)) {
    return;
  }
  rex::memory::Memory *memory =
      g_command_buffer_lineage_memory.load(std::memory_order_acquire);
  if (!memory) {
    return;
  }
  const uint32_t packet_physical_address =
      memory->GetPhysicalAddress(packet_guest_address);
  std::scoped_lock lock(g_title_packet_provenance_mutex);
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire)) {
    return;
  }
  if (packet_physical_address == UINT32_MAX ||
      (packet_physical_address & 3)) {
    ++g_title_indirect_packet_address_failures;
    return;
  }
  if (g_semantic_render_item_stack_depth) {
    SemanticDrawIdentity &semantic_draw =
        g_semantic_render_item_stack[g_semantic_render_item_stack_depth - 1];
    if (semantic_draw.valid) {
      ++semantic_draw.indirect_packet_origins;
      g_semantic_draw_indirect_packet_origins_captured.fetch_add(
          1, std::memory_order_relaxed);
    }
  }
  const size_t bucket =
      (packet_physical_address >> 2) % kTitleIndirectPacketBucketCount;
  const size_t first = bucket * kTitleIndirectPacketWays;
  size_t selected = first;
  uint64_t oldest_sequence = UINT64_MAX;
  bool found_free = false;
  for (size_t way = 0; way < kTitleIndirectPacketWays; ++way) {
    const size_t index = first + way;
    const TitleIndirectPacketEntry &entry = g_title_indirect_packets[index];
    if (!entry.occupied) {
      selected = index;
      found_free = true;
      break;
    }
    if (entry.submission_sequence < oldest_sequence) {
      selected = index;
      oldest_sequence = entry.submission_sequence;
    }
  }
  if (!found_free) {
    ++g_title_indirect_packet_evictions;
  }
  TitleIndirectPacketEntry &entry = g_title_indirect_packets[selected];
  const IndirectConstructorOrigin origin =
      CurrentIndirectConstructorOrigin(constructor_function_address);
  entry.packet_physical_address = packet_physical_address;
  entry.constructor_store_address = constructor_store_address;
  entry.constructor_function_address = origin.function_address;
  entry.constructor_return_address = origin.return_address;
  entry.constructor_arguments = origin.arguments;
  entry.owner_function_address = origin.owner.function_address;
  entry.owner_return_address = origin.owner.return_address;
  entry.owner_arguments = origin.owner.arguments;
  entry.producer_function_address = origin.owner.producer.function_address;
  entry.producer_return_address = origin.owner.producer.return_address;
  entry.producer_arguments = origin.owner.producer.arguments;
  entry.context_function_address =
      origin.owner.producer.context.function_address;
  entry.context_return_address = origin.owner.producer.context.return_address;
  entry.context_arguments = origin.owner.producer.context.arguments;
  entry.context_root_address = origin.owner.producer.context.root_address;
  entry.semantic_receiver_address =
      origin.owner.producer.context.semantic_receiver_address;
  entry.semantic_receiver_generation =
      origin.owner.producer.context.semantic_receiver_generation;
  entry.semantic_visibility_epoch =
      origin.owner.producer.context.semantic_visibility_epoch;
  entry.semantic_render_state_epoch =
      origin.owner.producer.context.semantic_render_state_epoch;
  entry.semantic_render_state_visibility_epoch =
      origin.owner.producer.context.semantic_render_state_visibility_epoch;
  entry.submission_sequence = ++g_title_indirect_packet_submission_sequence;
  entry.constructor_origin_known = origin.valid;
  entry.owner_origin_known = origin.owner.valid;
  entry.producer_origin_known = origin.owner.producer.valid;
  entry.context_origin_known = origin.owner.producer.context.valid;
  entry.semantic_receiver_known =
      origin.owner.producer.context.semantic_receiver_known;
  entry.occupied = true;
  ++g_title_indirect_packets_recorded;
}

TitleIndirectPacketEntry MatchTitleIndirectPacket(
    uint32_t packet_physical_address) {
  std::scoped_lock lock(g_title_packet_provenance_mutex);
  const size_t bucket =
      (packet_physical_address >> 2) % kTitleIndirectPacketBucketCount;
  const size_t first = bucket * kTitleIndirectPacketWays;
  size_t oldest_match = kTitleIndirectPacketCapacity;
  uint64_t oldest_sequence = UINT64_MAX;
  for (size_t way = 0; way < kTitleIndirectPacketWays; ++way) {
    const size_t index = first + way;
    const TitleIndirectPacketEntry &entry = g_title_indirect_packets[index];
    if (entry.occupied &&
        entry.packet_physical_address == packet_physical_address &&
        entry.submission_sequence < oldest_sequence) {
      oldest_match = index;
      oldest_sequence = entry.submission_sequence;
    }
  }
  if (oldest_match != kTitleIndirectPacketCapacity) {
    TitleIndirectPacketEntry &entry = g_title_indirect_packets[oldest_match];
    const TitleIndirectPacketEntry matched = entry;
    entry.occupied = false;
    ++g_title_indirect_buffer_matches;
    return matched;
  }
  ++g_title_indirect_buffer_unmatched;
  return {};
}

void ObserveIndirectBuffer(
    const rex::system::GraphicsIndirectBufferObservation &observation) {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire)) {
    return;
  }
  if (observation.entering) {
    ++g_title_indirect_buffer_enters;
    if (g_title_indirect_stack_depth == kTitleIndirectStackCapacity ||
        observation.depth != g_title_indirect_stack_depth + 1) {
      ++g_title_indirect_stack_faults;
      return;
    }
    ActiveTitleIndirectBuffer &active =
        g_title_indirect_stack[g_title_indirect_stack_depth++];
    active.packet_physical_address = observation.packet_physical_address;
    active.target_buffer_physical_address =
        observation.target_buffer_physical_address;
    active.parent_packet_physical_address =
        observation.packet_physical_address;
    active.root_buffer_physical_address =
        observation.root_buffer_physical_address;
    const TitleIndirectPacketEntry matched =
        MatchTitleIndirectPacket(observation.packet_physical_address);
    active.constructor_store_address = matched.constructor_store_address;
    active.constructor_origin.function_address =
        matched.constructor_function_address;
    active.constructor_origin.return_address =
        matched.constructor_return_address;
    active.constructor_origin.arguments = matched.constructor_arguments;
    active.constructor_origin.valid = matched.constructor_origin_known;
    active.constructor_origin.owner.function_address =
        matched.owner_function_address;
    active.constructor_origin.owner.return_address =
        matched.owner_return_address;
    active.constructor_origin.owner.arguments = matched.owner_arguments;
    active.constructor_origin.owner.valid = matched.owner_origin_known;
    active.constructor_origin.owner.producer.function_address =
        matched.producer_function_address;
    active.constructor_origin.owner.producer.return_address =
        matched.producer_return_address;
    active.constructor_origin.owner.producer.arguments =
        matched.producer_arguments;
    active.constructor_origin.owner.producer.valid =
        matched.producer_origin_known;
    active.constructor_origin.owner.producer.context.function_address =
        matched.context_function_address;
    active.constructor_origin.owner.producer.context.return_address =
        matched.context_return_address;
    active.constructor_origin.owner.producer.context.arguments =
        matched.context_arguments;
    active.constructor_origin.owner.producer.context.root_address =
        matched.context_root_address;
    active.constructor_origin.owner.producer.context.semantic_receiver_address =
        matched.semantic_receiver_address;
    active.constructor_origin.owner.producer.context
        .semantic_receiver_generation = matched.semantic_receiver_generation;
    active.constructor_origin.owner.producer.context.semantic_visibility_epoch =
        matched.semantic_visibility_epoch;
    active.constructor_origin.owner.producer.context.semantic_render_state_epoch =
        matched.semantic_render_state_epoch;
    active.constructor_origin.owner.producer.context
        .semantic_render_state_visibility_epoch =
        matched.semantic_render_state_visibility_epoch;
    active.constructor_origin.owner.producer.context.semantic_receiver_known =
        matched.semantic_receiver_known;
    active.constructor_origin.owner.producer.context.valid =
        matched.context_origin_known;
    active.depth = observation.depth;
    g_title_indirect_buffers_open.fetch_add(1, std::memory_order_relaxed);
    return;
  }

  ++g_title_indirect_buffer_exits;
  if (!g_title_indirect_stack_depth) {
    ++g_title_indirect_stack_faults;
    return;
  }
  const ActiveTitleIndirectBuffer &active =
      g_title_indirect_stack[g_title_indirect_stack_depth - 1];
  if (active.packet_physical_address != observation.packet_physical_address ||
      active.target_buffer_physical_address !=
          observation.target_buffer_physical_address ||
      active.depth != observation.depth) {
    ++g_title_indirect_stack_faults;
    return;
  }
  --g_title_indirect_stack_depth;
  g_title_indirect_buffers_open.fetch_sub(1, std::memory_order_relaxed);
}

const ActiveTitleIndirectBuffer *CurrentTitleIndirectBuffer(
    const rex::system::GraphicsDrawObservation &observation) {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire)) {
    return nullptr;
  }
  if (!observation.command_buffer_depth) {
    return nullptr;
  }
  if (!g_title_indirect_stack_depth) {
    ++g_title_indirect_draw_stack_faults;
    return nullptr;
  }
  const ActiveTitleIndirectBuffer &active =
      g_title_indirect_stack[g_title_indirect_stack_depth - 1];
  if (active.depth != observation.command_buffer_depth ||
      active.target_buffer_physical_address !=
          observation.command_buffer_physical_address ||
      active.parent_packet_physical_address !=
          observation.command_buffer_parent_packet_physical_address ||
      active.root_buffer_physical_address !=
          observation.command_buffer_root_physical_address) {
    ++g_title_indirect_draw_stack_faults;
    return nullptr;
  }
  return &active;
}

bool ConsumeTitleDrawPacket(uint32_t packet_physical_address,
                            TitleDrawOrigin &origin) {
  if (!g_title_provenance_installed.load(std::memory_order_acquire) ||
      packet_physical_address == UINT32_MAX) {
    return false;
  }
  std::scoped_lock lock(g_title_packet_provenance_mutex);
  if (!g_title_provenance_installed.load(std::memory_order_acquire)) {
    return false;
  }
  const size_t initial =
      (packet_physical_address >> 2) % kTitlePacketProvenanceCapacity;
  size_t oldest_match = kTitlePacketProvenanceCapacity;
  uint64_t oldest_sequence = UINT64_MAX;
  for (size_t probe = 0; probe < kTitlePacketProvenanceCapacity; ++probe) {
    const size_t index = (initial + probe) % kTitlePacketProvenanceCapacity;
    TitlePacketProvenanceEntry &entry = g_title_packet_provenance[index];
    if (!entry.ever_used) {
      break;
    }
    if (entry.occupied &&
        entry.packet_physical_address == packet_physical_address &&
        entry.submission_sequence < oldest_sequence) {
      oldest_match = index;
      oldest_sequence = entry.submission_sequence;
    }
  }
  if (oldest_match != kTitlePacketProvenanceCapacity) {
    TitlePacketProvenanceEntry &entry =
        g_title_packet_provenance[oldest_match];
    origin = entry.origin;
    entry.occupied = false;
    if (origin.semantic_draw.valid) {
      g_semantic_draw_packet_matches.fetch_add(1,
                                                std::memory_order_relaxed);
    }
    ++g_title_packets_matched;
    return true;
  }
  ++g_title_backend_unattributed_draws;
  return false;
}

void ResetDispatchDiscovery() {
  for (DispatchCallerEntry &entry : g_dispatch_callers) {
    entry.key.store(0, std::memory_order_relaxed);
    entry.calls.store(0, std::memory_order_relaxed);
    entry.first_frame.store(0, std::memory_order_relaxed);
    entry.first_r3.store(0, std::memory_order_relaxed);
    entry.first_r4.store(0, std::memory_order_relaxed);
    entry.first_r5.store(0, std::memory_order_relaxed);
    entry.first_r6.store(0, std::memory_order_relaxed);
    entry.first_r7.store(0, std::memory_order_relaxed);
    entry.first_r8.store(0, std::memory_order_relaxed);
    entry.first_r9.store(0, std::memory_order_relaxed);
    entry.first_r10.store(0, std::memory_order_relaxed);
  }
  g_dispatch_caller_overflow.store(0, std::memory_order_relaxed);
}

void ConfigureDispatchDiscovery() {
  ResetDispatchDiscovery();
  const bool requested =
      REXCVAR_GET(pinyon_shift_native_renderer_dispatch_discovery);
  g_dispatch_discovery_installed.store(requested, std::memory_order_release);
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.discovery.dispatch_config",
      {{"status", requested ? "armed" : "disabled"},
       {"scene", CensusSceneMarker()},
       {"wrappers",
        "824079B8,8240F4D8,82413AB8,824587D8,82458A88,824736F0,"
        "829F21A0,829F2280,829F7C70,82D951E0"},
       {"caller_capacity", std::to_string(kDispatchCallerCapacity)},
       {"metadata", "entry_lr_via_r12,r3-r10,frame"},
       {"guest_payload_read", "false"},
       {"xenos_draw", "preserved"},
       {"suppression_eligible", "false"}});
}

void ObserveTitleDispatch(DispatchWrapper wrapper, uint32_t caller,
                          uint32_t r3, uint32_t r4, uint32_t r5,
                          uint32_t r6, uint32_t r7, uint32_t r8,
                          uint32_t r9, uint32_t r10) {
  if (!g_dispatch_discovery_installed.load(std::memory_order_acquire)) {
    return;
  }
  const uint32_t caller_key = caller ? caller : 1;
  const uint64_t key = (static_cast<uint64_t>(wrapper) << 32) | caller_key;
  size_t index = (caller_key ^ (caller_key >> 11)) % kDispatchCallerCapacity;
  for (size_t probe = 0; probe < kDispatchCallerCapacity; ++probe) {
    DispatchCallerEntry &entry = g_dispatch_callers[index];
    uint64_t observed = entry.key.load(std::memory_order_acquire);
    if (observed == key) {
      entry.calls.fetch_add(1, std::memory_order_relaxed);
      return;
    }
    if (observed == 0 &&
        entry.key.compare_exchange_strong(observed, key,
                                          std::memory_order_acq_rel)) {
      // Publish the initial count before the descriptive first-sample fields.
      // A second graphics thread may observe the claimed key immediately; its
      // fetch_add must not be overwritten by a late initializing store.
      entry.calls.store(1, std::memory_order_release);
      entry.first_frame.store(g_frame_sequence.load(std::memory_order_relaxed),
                              std::memory_order_relaxed);
      entry.first_r3.store(r3, std::memory_order_relaxed);
      entry.first_r4.store(r4, std::memory_order_relaxed);
      entry.first_r5.store(r5, std::memory_order_relaxed);
      entry.first_r6.store(r6, std::memory_order_relaxed);
      entry.first_r7.store(r7, std::memory_order_relaxed);
      entry.first_r8.store(r8, std::memory_order_relaxed);
      entry.first_r9.store(r9, std::memory_order_relaxed);
      entry.first_r10.store(r10, std::memory_order_relaxed);
      return;
    }
    index = (index + 1) % kDispatchCallerCapacity;
  }
  g_dispatch_caller_overflow.fetch_add(1, std::memory_order_relaxed);
}

void EmitDispatchDiscoverySummary() {
  if (!g_dispatch_discovery_installed.exchange(false,
                                                std::memory_order_acq_rel)) {
    return;
  }
  uint64_t tracked_calls = 0;
  uint64_t tracked_callers = 0;
  for (const DispatchCallerEntry &entry : g_dispatch_callers) {
    const uint64_t calls = entry.calls.load(std::memory_order_acquire);
    const uint64_t key = entry.key.load(std::memory_order_acquire);
    if (!calls || !key) {
      continue;
    }
    const auto wrapper = static_cast<DispatchWrapper>(key >> 32);
    const uint32_t caller = static_cast<uint32_t>(key);
    tracked_calls += calls;
    ++tracked_callers;
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.discovery.dispatch_caller",
        {{"wrapper", DispatchWrapperName(wrapper)},
         {"wrapper_address", DispatchWrapperAddress(wrapper)},
         {"caller", fmt::format("{:08X}", caller)},
         {"calls", std::to_string(calls)},
         {"first_frame",
          std::to_string(entry.first_frame.load(std::memory_order_relaxed))},
         {"first_r3",
          fmt::format("{:08X}",
                      entry.first_r3.load(std::memory_order_relaxed))},
         {"first_r4",
          fmt::format("{:08X}",
                      entry.first_r4.load(std::memory_order_relaxed))},
         {"first_r5",
          fmt::format("{:08X}",
                      entry.first_r5.load(std::memory_order_relaxed))},
         {"first_r6",
          fmt::format("{:08X}",
                      entry.first_r6.load(std::memory_order_relaxed))},
         {"first_r7",
          fmt::format("{:08X}",
                      entry.first_r7.load(std::memory_order_relaxed))},
         {"first_r8",
          fmt::format("{:08X}",
                      entry.first_r8.load(std::memory_order_relaxed))},
         {"first_r9",
          fmt::format("{:08X}",
                      entry.first_r9.load(std::memory_order_relaxed))},
         {"first_r10",
          fmt::format("{:08X}",
                      entry.first_r10.load(std::memory_order_relaxed))},
         {"mode", "read_only_metadata"},
         {"xenos_draw", "preserved"},
         {"suppression_eligible", "false"}});
  }
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.discovery.dispatch_summary",
      {{"tracked_callers", std::to_string(tracked_callers)},
       {"tracked_calls", std::to_string(tracked_calls)},
       {"overflow_calls",
        std::to_string(
            g_dispatch_caller_overflow.load(std::memory_order_relaxed))},
       {"capacity", std::to_string(kDispatchCallerCapacity)},
       {"guest_payload_read", "false"},
       {"guest_state_changed", "false"},
       {"control_flow_changed", "false"},
       {"xenos_authority", "true"},
       {"suppression_allowed", "false"}});
}

std::string CensusSceneMarker() {
  char *value = nullptr;
  size_t length = 0;
  if (_dupenv_s(&value, &length, "PINYON_SHIFT_NATIVE_RENDERER_SCENE") != 0 ||
      !value || length <= 1) {
    std::free(value);
    return "unmarked";
  }
  std::string marker(value);
  std::free(value);
  if (marker.size() > 32 ||
      !std::all_of(marker.begin(), marker.end(), [](unsigned char character) {
        return (character >= 'a' && character <= 'z') || character == '_';
      })) {
    return "invalid";
  }
  return marker;
}

struct IndexScanState {
  uint64_t target_signature = 0;
  bool requested = false;
  bool completed = false;
  bool valid = true;
};

IndexScanState g_index_scan;

struct TextureScanState {
  uint64_t target_signature = 0;
  bool requested = false;
  bool completed = false;
  bool valid = true;
};

TextureScanState g_texture_scan;

struct ReplaySnapshotState {
  uint64_t target_signature = 0;
  std::filesystem::path output_root;
  bool requested = false;
  bool completed = false;
  bool valid = true;
};

ReplaySnapshotState g_replay_snapshot;

struct IsolatedDrawState {
  uint64_t target_signature = 0;
  uint64_t prepared_signature = 0;
  uint64_t frame = 0;
  uint64_t draw = 0;
  uint64_t captured_signature = 0;
  uint64_t captured_frame = 0;
  uint64_t captured_draw = 0;
  uint64_t pass_anchor_frame = 0;
  uint64_t pass_anchor_draw = 0;
  uint32_t prepared_title_lod_index = 0;
  rex::system::GraphicsDrawObservation prepared_sample;
  std::filesystem::path output_root;
  std::jthread artifact_writer;
  std::jthread reference_artifact_writer;
  std::jthread depth_artifact_writer;
  std::jthread reference_depth_artifact_writer;
  bool requested = false;
  bool readback_requested = false;
  bool completed = false;
  bool valid = true;
  bool prepared_candidate_valid = false;
  bool prepared_candidate_eligible = false;
  bool prepared_visibility_candidate_fresh = false;
  bool prepared_title_lod_valid = false;
  bool require_fresh_visibility_candidate = false;
  bool require_title_lod_candidate = false;
  bool auto_select_fresh_visibility_candidate = false;
  bool visibility_wait_reported = false;
  bool title_lod_wait_reported = false;
  bool awaiting_pass_follower = false;
  bool pass_anchor_recorded = false;
  bool pass_repeat_reported = false;
};

IsolatedDrawState g_isolated_draw;

struct PassFollowerState {
  uint64_t target_signature = 0;
  uint64_t anchor_frame = 0;
  uint64_t anchor_draw = 0;
  uint64_t adjacency_mismatches = 0;
  bool requested = false;
  bool valid = true;
  bool awaiting_follower = false;
  bool completed = false;
};

PassFollowerState g_pass_follower;

struct PassPublicationState {
  uint64_t attempts = 0;
  uint64_t published = 0;
  uint64_t failures = 0;
  uint64_t detail_events = 0;
  uint64_t detail_overflow = 0;
  uint64_t last_frame = 0;
  uint64_t last_draw = 0;
  bool requested = false;
  bool valid = true;
};

PassPublicationState g_pass_publication;

struct SkyHorizonSuppressionState {
  enum class RuntimeMode {
    kDisabled,
    kWarming,
    kActive,
    kCooldown,
  };

  uint64_t attempts = 0;
  uint64_t suppressed = 0;
  uint64_t suppressed_vertices = 0;
  uint64_t fallbacks = 0;
  uint64_t unexpected_suppressions = 0;
  uint64_t yielded_attempts = 0;
  uint64_t yielded_vertices = 0;
  uint64_t warmup_publications = 0;
  uint64_t warmup_frames = 0;
  uint64_t warmup_resets = 0;
  uint64_t cooldown_entries = 0;
  uint64_t state_detail_events = 0;
  uint64_t state_detail_overflow = 0;
  uint64_t last_frame = 0;
  uint64_t last_draw = 0;
  uint64_t last_successful_frame = 0;
  uint64_t active_from_frame = 0;
  uint64_t cooldown_until_frame = 0;
  const char *last_yield_reason = "disabled";
  RuntimeMode mode = RuntimeMode::kDisabled;
  bool requested = false;
  bool armed = false;
  bool attempt_suppression_requested = false;
};

SkyHorizonSuppressionState g_sky_horizon_suppression;

const char *SuppressionRuntimeModeName(
    SkyHorizonSuppressionState::RuntimeMode mode) {
  switch (mode) {
  case SkyHorizonSuppressionState::RuntimeMode::kDisabled:
    return "disabled";
  case SkyHorizonSuppressionState::RuntimeMode::kWarming:
    return "warming";
  case SkyHorizonSuppressionState::RuntimeMode::kActive:
    return "active";
  case SkyHorizonSuppressionState::RuntimeMode::kCooldown:
    return "cooldown";
  }
  return "invalid";
}

void RecordSuppressionStateTransition(
    SkyHorizonSuppressionState::RuntimeMode previous,
    SkyHorizonSuppressionState::RuntimeMode next, uint64_t frame,
    const char *reason) {
  if (previous == next) {
    return;
  }
  if (g_sky_horizon_suppression.state_detail_events >=
      kSuppressionStateDetailLimit) {
    ++g_sky_horizon_suppression.state_detail_overflow;
    return;
  }
  ++g_sky_horizon_suppression.state_detail_events;
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.suppression_state",
      {{"family", "sky_horizon"},
       {"previous", SuppressionRuntimeModeName(previous)},
       {"current", SuppressionRuntimeModeName(next)},
       {"reason", reason},
       {"frame", std::to_string(frame)},
       {"warmup_frames",
        std::to_string(g_sky_horizon_suppression.warmup_frames)},
       {"cooldown_until_frame",
        std::to_string(g_sky_horizon_suppression.cooldown_until_frame)},
       {"xenos_fallback", "mandatory"}});
}

void SetSuppressionRuntimeMode(
    SkyHorizonSuppressionState::RuntimeMode mode, uint64_t frame,
    const char *reason) {
  const auto previous = g_sky_horizon_suppression.mode;
  g_sky_horizon_suppression.mode = mode;
  RecordSuppressionStateTransition(previous, mode, frame, reason);
}

void ResetSuppressionWarmup(uint64_t frame, const char *reason) {
  if (g_sky_horizon_suppression.warmup_frames ||
      g_sky_horizon_suppression.mode ==
          SkyHorizonSuppressionState::RuntimeMode::kActive) {
    ++g_sky_horizon_suppression.warmup_resets;
  }
  g_sky_horizon_suppression.warmup_frames = 0;
  g_sky_horizon_suppression.last_successful_frame = 0;
  g_sky_horizon_suppression.active_from_frame = 0;
  SetSuppressionRuntimeMode(
      SkyHorizonSuppressionState::RuntimeMode::kWarming, frame, reason);
}

void EnterSuppressionCooldown(uint64_t frame, const char *reason) {
  ++g_sky_horizon_suppression.cooldown_entries;
  g_sky_horizon_suppression.warmup_frames = 0;
  g_sky_horizon_suppression.last_successful_frame = 0;
  g_sky_horizon_suppression.active_from_frame = 0;
  g_sky_horizon_suppression.cooldown_until_frame =
      frame + kSuppressionFailureCooldownFrameCount;
  g_sky_horizon_suppression.last_yield_reason = reason;
  SetSuppressionRuntimeMode(
      SkyHorizonSuppressionState::RuntimeMode::kCooldown, frame, reason);
}

bool PrepareSuppressionAttempt(uint64_t frame) {
  g_sky_horizon_suppression.attempt_suppression_requested = false;
  if (!g_sky_horizon_suppression.armed) {
    g_sky_horizon_suppression.last_yield_reason = "not_armed";
    return false;
  }
  if (g_sky_horizon_suppression.mode ==
      SkyHorizonSuppressionState::RuntimeMode::kCooldown) {
    if (frame < g_sky_horizon_suppression.cooldown_until_frame) {
      g_sky_horizon_suppression.last_yield_reason = "failure_cooldown";
      return false;
    }
    ResetSuppressionWarmup(frame, "cooldown_expired");
  }
  if (g_sky_horizon_suppression.last_successful_frame &&
      frame > g_sky_horizon_suppression.last_successful_frame + 1) {
    ResetSuppressionWarmup(frame, "frame_gap");
  }
  if (g_sky_horizon_suppression.mode ==
      SkyHorizonSuppressionState::RuntimeMode::kActive) {
    if (frame >= g_sky_horizon_suppression.active_from_frame) {
      g_sky_horizon_suppression.attempt_suppression_requested = true;
      g_sky_horizon_suppression.last_yield_reason = "none";
      return true;
    }
    g_sky_horizon_suppression.last_yield_reason = "warmup_frame_boundary";
    return false;
  }
  g_sky_horizon_suppression.last_yield_reason = "warmup";
  return false;
}

void AdvanceSuppressionWarmup(uint64_t frame) {
  ++g_sky_horizon_suppression.warmup_publications;
  if (g_sky_horizon_suppression.mode ==
      SkyHorizonSuppressionState::RuntimeMode::kCooldown) {
    return;
  }
  if (g_sky_horizon_suppression.last_successful_frame == frame) {
    return;
  }
  if (g_sky_horizon_suppression.last_successful_frame + 1 == frame) {
    ++g_sky_horizon_suppression.warmup_frames;
  } else {
    if (g_sky_horizon_suppression.warmup_frames) {
      ++g_sky_horizon_suppression.warmup_resets;
    }
    g_sky_horizon_suppression.warmup_frames = 1;
  }
  g_sky_horizon_suppression.last_successful_frame = frame;
  if (g_sky_horizon_suppression.warmup_frames >=
      kSuppressionWarmupFrameCount) {
    g_sky_horizon_suppression.active_from_frame = frame + 1;
    SetSuppressionRuntimeMode(
        SkyHorizonSuppressionState::RuntimeMode::kActive, frame,
        "warmup_complete");
  }
}

struct ConsumerFamilyMarkerState {
  uint64_t vertex_shader_hash = 0;
  uint64_t pixel_shader_hash = 0;
  uint64_t vertex_specialization_mask = 0;
  uint64_t pixel_specialization_mask = 0;
  uint64_t capture_frame = 0;
  uint64_t capture_draw = 0;
  uint64_t matched_draws = 0;
  uint64_t marker_requests = 0;
  uint64_t readback_requests = 0;
  uint64_t readback_completions = 0;
  uint64_t readback_samples_completed = 0;
  uint32_t readback_sample_limit = 1;
  uint32_t current_capture_completions = 0;
  uint32_t current_capture_index = 0;
  std::filesystem::path readback_root;
  std::vector<std::jthread> artifact_writers;
  bool requested = false;
  bool readback_requested = false;
  bool readback_in_flight = false;
  bool valid = true;
  bool current_match = false;
};

ConsumerFamilyMarkerState g_consumer_family_marker;

bool IsLocalArtifactRoot(const std::filesystem::path &path);

void ConfigureSignatureScan(const char *name, uint64_t &target_signature,
                            bool &requested, bool &valid) {
  char *value = nullptr;
  size_t length = 0;
  if (_dupenv_s(&value, &length, name) != 0 || !value || length <= 1) {
    std::free(value);
    return;
  }
  const std::string setting(value);
  std::free(value);
  requested = true;
  if (setting.size() != 16) {
    valid = false;
    return;
  }
  const char *begin = setting.data();
  const char *end = begin + setting.size();
  const auto parsed = std::from_chars(begin, end, target_signature, 16);
  if (parsed.ec != std::errc{} || parsed.ptr != end || !target_signature) {
    valid = false;
  }
}

void ConfigureIndexScan() {
  g_index_scan = {};
  ConfigureSignatureScan("PINYON_SHIFT_NATIVE_RENDERER_INDEX_SCAN_SIGNATURE",
                         g_index_scan.target_signature,
                         g_index_scan.requested, g_index_scan.valid);
}

void ConfigurePassFollower() {
  g_pass_follower = {};
  ConfigureSignatureScan(
      "PINYON_SHIFT_NATIVE_RENDERER_PASS_ANCHOR_SIGNATURE",
      g_pass_follower.target_signature, g_pass_follower.requested,
      g_pass_follower.valid);
  if (!g_pass_follower.requested &&
      g_sky_horizon_suppression.requested) {
    g_pass_follower.target_signature = kSkyHorizonAnchorSignature;
    g_pass_follower.requested = true;
  }
  if (g_isolated_draw.auto_select_fresh_visibility_candidate &&
      g_pass_follower.requested) {
    g_pass_follower.valid = false;
  }
}

void ConfigureConsumerFamilyMarker() {
  g_consumer_family_marker = {};
  char *value = nullptr;
  size_t length = 0;
  if (_dupenv_s(&value, &length,
                "PINYON_SHIFT_NATIVE_RENDERER_CONSUMER_FAMILY") != 0 ||
      !value || length <= 1) {
    std::free(value);
    return;
  }
  const std::string setting(value);
  std::free(value);
  g_consumer_family_marker.requested = true;
  if (setting.size() != 67 || setting[16] != '/' || setting[33] != '/' ||
      setting[50] != '/') {
    g_consumer_family_marker.valid = false;
    return;
  }
  std::array<uint64_t *, 4> fields = {
      &g_consumer_family_marker.vertex_shader_hash,
      &g_consumer_family_marker.pixel_shader_hash,
      &g_consumer_family_marker.vertex_specialization_mask,
      &g_consumer_family_marker.pixel_specialization_mask,
  };
  for (size_t index = 0; index < fields.size(); ++index) {
    const char *begin = setting.data() + index * 17;
    const char *end = begin + 16;
    const auto parsed = std::from_chars(begin, end, *fields[index], 16);
    if (parsed.ec != std::errc{} || parsed.ptr != end) {
      g_consumer_family_marker.valid = false;
      return;
    }
  }
  if (!g_consumer_family_marker.vertex_shader_hash ||
      !g_consumer_family_marker.pixel_shader_hash) {
    g_consumer_family_marker.valid = false;
  }
  value = nullptr;
  length = 0;
  if (_dupenv_s(&value, &length,
                "PINYON_SHIFT_NATIVE_RENDERER_CONSUMER_READBACK_DIR") != 0 ||
      !value || length <= 1) {
    std::free(value);
    return;
  }
  g_consumer_family_marker.readback_requested = true;
  g_consumer_family_marker.readback_root =
      std::filesystem::absolute(std::filesystem::path(value)).lexically_normal();
  std::free(value);
  if (!g_consumer_family_marker.valid ||
      !IsLocalArtifactRoot(g_consumer_family_marker.readback_root)) {
    g_consumer_family_marker.valid = false;
    return;
  }
  value = nullptr;
  length = 0;
  if (_dupenv_s(&value, &length,
                "PINYON_SHIFT_NATIVE_RENDERER_CONSUMER_READBACK_SAMPLES") !=
          0 ||
      !value || length <= 1) {
    std::free(value);
    return;
  }
  const std::string sample_setting(value);
  std::free(value);
  uint32_t sample_limit = 0;
  const auto parsed = std::from_chars(
      sample_setting.data(), sample_setting.data() + sample_setting.size(),
      sample_limit, 10);
  if (parsed.ec != std::errc{} ||
      parsed.ptr != sample_setting.data() + sample_setting.size() ||
      !sample_limit || sample_limit > kMaximumConsumerReadbackSamples) {
    g_consumer_family_marker.valid = false;
    return;
  }
  g_consumer_family_marker.readback_sample_limit = sample_limit;
}

std::string ConsumerFamilyId() {
  if (!g_consumer_family_marker.requested ||
      !g_consumer_family_marker.valid) {
    return "";
  }
  return fmt::format(
      "{:016X}/{:016X}/{:016X}/{:016X}",
      g_consumer_family_marker.vertex_shader_hash,
      g_consumer_family_marker.pixel_shader_hash,
      g_consumer_family_marker.vertex_specialization_mask,
      g_consumer_family_marker.pixel_specialization_mask);
}

void ConfigureTextureScan() {
  g_texture_scan = {};
  ConfigureSignatureScan(
      "PINYON_SHIFT_NATIVE_RENDERER_TEXTURE_SCAN_SIGNATURE",
      g_texture_scan.target_signature, g_texture_scan.requested,
      g_texture_scan.valid);
}

bool IsLocalArtifactRoot(const std::filesystem::path &path) {
  return path.is_absolute() &&
         std::any_of(path.begin(), path.end(), [](const auto &component) {
           return component.native() == L".local";
         });
}

void ConfigureReplaySnapshot() {
  g_replay_snapshot = {};
  ConfigureSignatureScan(
      "PINYON_SHIFT_NATIVE_RENDERER_SNAPSHOT_SIGNATURE",
      g_replay_snapshot.target_signature, g_replay_snapshot.requested,
      g_replay_snapshot.valid);
  const bool signature_requested = g_replay_snapshot.requested;
  char *value = nullptr;
  size_t length = 0;
  if (_dupenv_s(&value, &length,
                "PINYON_SHIFT_NATIVE_RENDERER_SNAPSHOT_DIR") != 0 ||
      !value || length <= 1) {
    std::free(value);
    if (g_replay_snapshot.requested) {
      g_replay_snapshot.valid = false;
    }
    return;
  }
  g_replay_snapshot.requested = true;
  g_replay_snapshot.output_root =
      std::filesystem::absolute(std::filesystem::path(value)).lexically_normal();
  std::free(value);
  if (!signature_requested ||
      !IsLocalArtifactRoot(g_replay_snapshot.output_root)) {
    g_replay_snapshot.valid = false;
  }
}

void ConfigureIsolatedDraw() {
  g_isolated_draw = {};
  ConfigureSignatureScan(
      "PINYON_SHIFT_NATIVE_RENDERER_ISOLATED_DRAW_SIGNATURE",
      g_isolated_draw.target_signature, g_isolated_draw.requested,
      g_isolated_draw.valid);
  const bool signature_requested = g_isolated_draw.requested;
  char *value = nullptr;
  size_t length = 0;
  if (_dupenv_s(
          &value, &length,
          "PINYON_SHIFT_NATIVE_RENDERER_AUTO_SELECT_FRESH_VISIBILITY_CANDIDATE") ==
          0 &&
      value && length > 1) {
    const std::string setting(value);
    g_isolated_draw.auto_select_fresh_visibility_candidate = setting == "true";
    if (setting != "true" && setting != "false") {
      g_isolated_draw.valid = false;
    }
  }
  std::free(value);
  if (g_isolated_draw.auto_select_fresh_visibility_candidate) {
    g_isolated_draw.requested = true;
    g_isolated_draw.require_fresh_visibility_candidate = true;
    if (signature_requested || g_sky_horizon_suppression.requested) {
      g_isolated_draw.valid = false;
    }
  }
  value = nullptr;
  length = 0;
  if (_dupenv_s(
          &value, &length,
          "PINYON_SHIFT_NATIVE_RENDERER_REQUIRE_TITLE_LOD_CANDIDATE") == 0 &&
      value && length > 1) {
    const std::string setting(value);
    g_isolated_draw.require_title_lod_candidate = setting == "true";
    if ((setting != "true" && setting != "false") ||
        (g_isolated_draw.require_title_lod_candidate &&
         !g_isolated_draw.auto_select_fresh_visibility_candidate)) {
      g_isolated_draw.valid = false;
    }
  }
  std::free(value);
  if (!g_isolated_draw.requested &&
      g_sky_horizon_suppression.requested) {
    g_isolated_draw.target_signature = kSkyHorizonFollowerSignature;
    g_isolated_draw.requested = true;
  }
  const bool draw_requested = g_isolated_draw.requested;
  value = nullptr;
  length = 0;
  if (_dupenv_s(&value, &length,
                "PINYON_SHIFT_NATIVE_RENDERER_ISOLATED_DRAW_DIR") != 0 ||
      !value || length <= 1) {
    std::free(value);
    if (g_isolated_draw.auto_select_fresh_visibility_candidate) {
      g_isolated_draw.valid = false;
    }
    return;
  }
  g_isolated_draw.readback_requested = true;
  g_isolated_draw.output_root =
      std::filesystem::absolute(std::filesystem::path(value)).lexically_normal();
  std::free(value);
  if (!draw_requested ||
      !IsLocalArtifactRoot(g_isolated_draw.output_root)) {
    g_isolated_draw.valid = false;
  }
  value = nullptr;
  length = 0;
  if (_dupenv_s(
          &value, &length,
          "PINYON_SHIFT_NATIVE_RENDERER_REQUIRE_FRESH_VISIBILITY_CANDIDATE") ==
          0 &&
      value && length > 1) {
    const std::string setting(value);
    const bool require_fresh = setting == "true";
    if (!g_isolated_draw.auto_select_fresh_visibility_candidate) {
      g_isolated_draw.require_fresh_visibility_candidate = require_fresh;
    } else if (!require_fresh) {
      g_isolated_draw.valid = false;
    }
    if (setting != "true" && setting != "false") {
      g_isolated_draw.valid = false;
    }
  }
  std::free(value);
}

void ConfigurePassPublication() {
  g_pass_publication = {};
  char *value = nullptr;
  size_t length = 0;
  if (_dupenv_s(&value, &length,
                "PINYON_SHIFT_NATIVE_RENDERER_PUBLISH_RETAINED_PASS") != 0 ||
      !value || length <= 1) {
    std::free(value);
    if (g_sky_horizon_suppression.requested) {
      g_pass_publication.requested = true;
      g_pass_publication.valid =
          g_isolated_draw.requested && g_isolated_draw.valid &&
          g_pass_follower.requested && g_pass_follower.valid &&
          g_isolated_draw.target_signature !=
              g_pass_follower.target_signature;
    }
    return;
  }
  const std::string setting(value);
  std::free(value);
  if (setting == "false") {
    return;
  }
  g_pass_publication.requested = true;
  g_pass_publication.valid =
      setting == "true" && g_isolated_draw.requested &&
      g_isolated_draw.valid && g_pass_follower.requested &&
      g_pass_follower.valid &&
      g_isolated_draw.target_signature != g_pass_follower.target_signature;
}

void EmitSkyHorizonSuppressionControl() {
  const bool requested = g_sky_horizon_suppression.requested;
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.suppression_control",
      {{"family", "sky_horizon"},
       {"anchor_signature", "747837906D0BF484"},
       {"follower_signature", "1D253A52B55C9FB3"},
       {"requested", requested ? "true" : "false"},
       {"status", !requested
                      ? "disabled"
                      : (g_sky_horizon_suppression.armed
                             ? "armed_experimental"
                             : "blocked_invalid_configuration")},
       {"activation", "startup_only"},
       {"default_enabled", "false"},
       {"implementation", "fail_closed_follower_draw"},
       {"state_gate", "consecutive_publication_warmup"},
       {"warmup_frames", std::to_string(kSuppressionWarmupFrameCount)},
       {"failure_cooldown_frames",
        std::to_string(kSuppressionFailureCooldownFrameCount)},
       {"xenos_fallback", "mandatory"},
       {"xenos_draw", requested ? "anchor_preserved_follower_conditional"
                                  : "preserved"},
       {"draw_suppression", requested ? "follower_after_publication_only"
                                        : "false"},
       {"resolve_suppression", "false"},
       {"suppression_allowed",
        g_sky_horizon_suppression.armed ? "after_state_gate" : "false"}});
}

void ArmSkyHorizonSuppression() {
  g_sky_horizon_suppression.armed =
      g_sky_horizon_suppression.requested && g_isolated_draw.requested &&
      g_isolated_draw.valid &&
      g_isolated_draw.target_signature == kSkyHorizonFollowerSignature &&
      g_pass_follower.requested && g_pass_follower.valid &&
      g_pass_follower.target_signature == kSkyHorizonAnchorSignature &&
      g_pass_publication.requested && g_pass_publication.valid;
  g_sky_horizon_suppression.mode =
      g_sky_horizon_suppression.armed
          ? SkyHorizonSuppressionState::RuntimeMode::kWarming
          : SkyHorizonSuppressionState::RuntimeMode::kDisabled;
  g_sky_horizon_suppression.last_yield_reason =
      g_sky_horizon_suppression.armed ? "warmup" : "not_armed";
}

struct DrawSignatureEntry {
  uint64_t signature = 0;
  uint64_t draw_count = 0;
  uint64_t first_frame = 0;
  uint64_t last_frame = 0;
  uint32_t min_index_count = 0;
  uint32_t max_index_count = 0;
  uint32_t min_index_buffer_length = 0;
  uint64_t vertex_specialization_mask = 0;
  uint64_t pixel_specialization_mask = 0;
  rex::system::GraphicsPreparedDrawObservation prepared_sample;
  bool samples_resolved_target = false;
  rex::system::GraphicsDrawObservation sample;
};

struct DrawCensus {
  std::array<DrawSignatureEntry, kSignatureCapacity> entries{};
  uint64_t window_first_frame = 0;
  uint64_t window_last_frame = 0;
  uint64_t window_draw_count = 0;
  uint64_t unique_signature_count = 0;
  uint64_t overflow_draw_count = 0;
};

DrawCensus g_draw_census;
DrawCensus g_candidate_census;

struct PreparedShaderPairEntry {
  uint64_t identity = 0;
  rex::system::GraphicsPreparedDrawObservation sample;
};

std::array<PreparedShaderPairEntry, kPreparedShaderPairCapacity>
    g_prepared_shader_pairs{};
uint64_t g_prepared_shader_pair_count = 0;
uint64_t g_prepared_shader_pair_overflow = 0;
uint64_t g_candidate_unprepared_draw_count = 0;
uint64_t g_candidate_prepared_without_observation_count = 0;

struct CommandBufferLineageEntry {
  uint64_t sample_prepared_signature = 0;
  uint64_t calls = 0;
  uint64_t first_frame = 0;
  uint64_t last_frame = 0;
  uint64_t first_draw = 0;
  uint64_t last_draw = 0;
  uint32_t packet_physical_address = UINT32_MAX;
  uint32_t command_buffer_physical_address = UINT32_MAX;
  uint32_t sample_command_buffer_length_dwords = 0;
  uint32_t min_command_buffer_length_dwords = UINT32_MAX;
  uint32_t max_command_buffer_length_dwords = 0;
  uint32_t min_packet_offset_bytes = UINT32_MAX;
  uint32_t max_packet_offset_bytes = 0;
  uint32_t parent_packet_physical_address = UINT32_MAX;
  uint32_t root_physical_address = UINT32_MAX;
  uint32_t min_parent_root_offset_bytes = UINT32_MAX;
  uint32_t max_parent_root_offset_bytes = 0;
  uint32_t constructor_store_address = 0;
  uint32_t constructor_function_address = 0;
  uint32_t constructor_return_address = 0;
  std::array<uint32_t, 8> sample_constructor_arguments{};
  uint32_t constructor_argument_varying_mask = 0;
  uint32_t owner_function_address = 0;
  uint32_t owner_return_address = 0;
  std::array<uint32_t, 8> sample_owner_arguments{};
  uint32_t owner_argument_varying_mask = 0;
  uint32_t producer_function_address = 0;
  uint32_t producer_return_address = 0;
  std::array<uint32_t, 8> sample_producer_arguments{};
  uint32_t producer_argument_varying_mask = 0;
  uint32_t context_function_address = 0;
  uint32_t context_return_address = 0;
  std::array<uint32_t, 8> sample_context_arguments{};
  uint32_t context_argument_varying_mask = 0;
  uint32_t sample_context_root_address = 0;
  bool context_root_address_varied = false;
  uint32_t semantic_receiver_address = 0;
  uint32_t semantic_receiver_generation = 0;
  uint64_t semantic_visibility_epoch = 0;
  uint64_t semantic_render_state_epoch = 0;
  uint64_t semantic_render_state_visibility_epoch = 0;
  uint32_t depth = 0;
  bool constructor_origin_known = false;
  bool owner_origin_known = false;
  bool producer_origin_known = false;
  bool context_origin_known = false;
  bool semantic_receiver_known = false;
  bool semantic_preparation_epoch_varied = false;
  bool prepared_signature_varied = false;
};

std::array<CommandBufferLineageEntry, kCommandBufferLineageCapacity>
    g_command_buffer_lineages{};
uint64_t g_command_buffer_lineage_draws = 0;
uint64_t g_command_buffer_lineage_primary_draws = 0;
uint64_t g_command_buffer_lineage_indirect_draws = 0;
uint64_t g_command_buffer_lineage_invalid = 0;
uint64_t g_command_buffer_lineage_prepared_draws = 0;
uint64_t g_command_buffer_lineage_entry_count = 0;
uint64_t g_command_buffer_lineage_overflow = 0;
bool g_graphics_census_installed = false;
rex::memory::Memory *g_graphics_census_memory = nullptr;
void *g_guest_cpu_access_callback = nullptr;

struct GuestCpuVisibilityTargetEntry {
  std::atomic<uint32_t> address{};
  std::atomic<uint32_t> length{};
  std::atomic<uint64_t> generation{};
  std::atomic<uint64_t> resolve_count{};
  std::atomic<uint64_t> read_page_events{};
  std::atomic<uint64_t> write_page_events{};
  std::atomic<uint64_t> read_generations{};
  std::atomic<uint64_t> write_generations{};
  std::atomic<uint64_t> last_read_generation{};
  std::atomic<uint64_t> last_write_generation{};
};

std::array<GuestCpuVisibilityTargetEntry,
           kGuestCpuVisibilityTargetCapacity>
    g_guest_cpu_visibility_targets{};
std::atomic<size_t> g_guest_cpu_visibility_target_count{};
std::atomic<uint64_t> g_guest_cpu_visibility_armed_resolves{};
std::atomic<uint64_t> g_guest_cpu_visibility_armed_bytes{};
std::atomic<uint64_t> g_guest_cpu_visibility_target_overflow{};

struct PendingCandidateObservation {
  rex::system::GraphicsDrawObservation sample;
  TitleDrawOrigin title_origin{};
  std::array<size_t, 64> family_targets{};
  size_t family_target_count = 0;
  uint64_t family_base_fetch_mask = 0;
  uint64_t family_mip_fetch_mask = 0;
  uint64_t family_sample_references = 0;
  uint32_t first_family_fetch_index = 0;
  bool first_family_fetch_is_mip = false;
  bool samples_resolved_target = false;
  bool valid = false;
};

thread_local PendingCandidateObservation g_pending_candidate;

struct ResolveTargetEntry {
  uint32_t address = 0;
  uint32_t length = 0;
  uint32_t maximum_length = 0;
  uint32_t last_fetch_index = 0;
  uint64_t resolve_count = 0;
  uint64_t resolved_bytes = 0;
  uint64_t first_resolve_frame = 0;
  uint64_t last_resolve_frame = 0;
  uint64_t sampled_draw_count = 0;
  uint64_t sample_reference_count = 0;
  uint64_t first_sample_frame = 0;
  uint64_t last_sample_frame = 0;
  uint64_t conditional_sample_draw_count = 0;
  uint64_t query_state_sample_draw_count = 0;
  uint64_t memexport_sample_draw_count = 0;
  uint64_t window_resolve_count = 0;
  uint64_t window_sampled_draw_count = 0;
  uint64_t family_frame = 0;
  uint64_t family_draw = 0;
  uint64_t family_sampled_draw_count = 0;
  uint64_t family_sample_reference_count = 0;
  bool last_fetch_was_mip = false;
  bool latest_resolve_from_traced_family = false;
  bool family_consumer_reported = false;
  rex::system::GraphicsCopyObservation sample;
};

struct ResolvePageEntry {
  uint32_t page = 0;
  uint32_t target_index_plus_one = 0;
};

struct DependencyCensus {
  std::array<ResolveTargetEntry, kResolveTargetCapacity> targets{};
  std::array<ResolvePageEntry, kResolvePageCapacity> pages{};
  uint64_t window_first_frame = 0;
  uint64_t window_last_frame = 0;
  uint64_t window_resolve_count = 0;
  uint64_t window_resolve_bytes = 0;
  uint64_t window_failed_copy_count = 0;
  uint64_t window_zero_length_copy_count = 0;
  uint64_t window_sampled_draw_count = 0;
  uint64_t window_sample_reference_count = 0;
  uint64_t window_sampled_target_count = 0;
  uint64_t window_query_draw_count = 0;
  uint64_t window_memexport_draw_count = 0;
  uint64_t target_count = 0;
  uint64_t target_overflow_count = 0;
  uint64_t page_count = 0;
  uint64_t page_overflow_count = 0;
};

DependencyCensus g_dependency_census;

struct PassConsumerSignatureEntry {
  uint64_t signature = 0;
  uint64_t sample_events = 0;
  uint64_t first_frame = 0;
  uint64_t last_frame = 0;
  uint64_t query_sample_events = 0;
  uint64_t memexport_sample_events = 0;
  uint64_t family_base_fetch_mask = 0;
  uint64_t family_mip_fetch_mask = 0;
  bool prepared_valid = false;
  rex::system::GraphicsDrawObservation sample;
  rex::system::GraphicsPreparedDrawObservation prepared_sample;
};

struct PassConsumerTrace {
  rex::system::GraphicsDrawObservation pending_target;
  uint64_t pending_frame = 0;
  uint64_t pending_draw = 0;
  uint64_t family_occurrences = 0;
  uint64_t family_resolves = 0;
  uint64_t family_resolve_bytes = 0;
  uint64_t sampled_resolves = 0;
  uint64_t sampled_draws = 0;
  uint64_t sample_references = 0;
  uint64_t overwritten_unsampled = 0;
  uint64_t active_unsampled = 0;
  uint64_t superseded_without_resolve = 0;
  uint64_t consumer_signature_count = 0;
  uint64_t consumer_signature_overflow = 0;
  uint64_t unprepared_consumer_draws = 0;
  uint64_t unprepared_consumer_references = 0;
  uint64_t detail_events = 0;
  uint64_t detail_overflow = 0;
  bool pending = false;
  std::array<PassConsumerSignatureEntry, kPassConsumerSignatureCapacity>
      consumer_signatures{};
};

PassConsumerTrace g_pass_consumer_trace;

static_assert(std::is_trivially_copyable_v<DrawCensus>);
static_assert(std::is_trivially_copyable_v<DependencyCensus>);
static_assert(std::is_trivially_copyable_v<PassConsumerTrace>);

void ResetDrawCensus() {
  std::memset(&g_draw_census, 0, sizeof(g_draw_census));
  std::memset(&g_candidate_census, 0, sizeof(g_candidate_census));
}

void ResetPreparedShaderPairs() {
  std::memset(g_prepared_shader_pairs.data(), 0,
              sizeof(g_prepared_shader_pairs));
  g_prepared_shader_pair_count = 0;
  g_prepared_shader_pair_overflow = 0;
  g_candidate_unprepared_draw_count = 0;
  g_candidate_prepared_without_observation_count = 0;
  g_pending_candidate.valid = false;
}

void ResetCommandBufferLineage() {
  std::memset(g_command_buffer_lineages.data(), 0,
              sizeof(g_command_buffer_lineages));
  g_command_buffer_lineage_draws = 0;
  g_command_buffer_lineage_primary_draws = 0;
  g_command_buffer_lineage_indirect_draws = 0;
  g_command_buffer_lineage_invalid = 0;
  g_command_buffer_lineage_prepared_draws = 0;
  g_command_buffer_lineage_entry_count = 0;
  g_command_buffer_lineage_overflow = 0;
}

void ResetDependencyCensus() {
  std::memset(&g_dependency_census, 0, sizeof(g_dependency_census));
  std::memset(&g_pass_consumer_trace, 0, sizeof(g_pass_consumer_trace));
}

void ResetGuestCpuVisibility() {
  for (auto &target : g_guest_cpu_visibility_targets) {
    target.address.store(0, std::memory_order_relaxed);
    target.length.store(0, std::memory_order_relaxed);
    target.generation.store(0, std::memory_order_relaxed);
    target.resolve_count.store(0, std::memory_order_relaxed);
    target.read_page_events.store(0, std::memory_order_relaxed);
    target.write_page_events.store(0, std::memory_order_relaxed);
    target.read_generations.store(0, std::memory_order_relaxed);
    target.write_generations.store(0, std::memory_order_relaxed);
    target.last_read_generation.store(0, std::memory_order_relaxed);
    target.last_write_generation.store(0, std::memory_order_relaxed);
  }
  g_guest_cpu_visibility_target_count.store(0, std::memory_order_relaxed);
  g_guest_cpu_visibility_armed_resolves.store(0, std::memory_order_relaxed);
  g_guest_cpu_visibility_armed_bytes.store(0, std::memory_order_relaxed);
  g_guest_cpu_visibility_target_overflow.store(0,
                                                std::memory_order_relaxed);
}

void ObserveGuestCpuAccess(void *, uint32_t physical_address, uint32_t length,
                           bool is_write) {
  const uint64_t access_first = physical_address;
  const uint64_t access_last = access_first + length;
  const size_t target_count = g_guest_cpu_visibility_target_count.load(
      std::memory_order_acquire);
  for (size_t i = 0; i < target_count; ++i) {
    auto &target = g_guest_cpu_visibility_targets[i];
    const uint64_t target_first =
        target.address.load(std::memory_order_acquire);
    const uint64_t target_length =
        target.length.load(std::memory_order_acquire);
    if (!target_length || access_first >= target_first + target_length ||
        access_last <= target_first) {
      continue;
    }
    const uint64_t generation =
        target.generation.load(std::memory_order_acquire);
    auto &page_events = is_write ? target.write_page_events
                                 : target.read_page_events;
    auto &generations = is_write ? target.write_generations
                                 : target.read_generations;
    auto &last_generation = is_write ? target.last_write_generation
                                     : target.last_read_generation;
    page_events.fetch_add(1, std::memory_order_relaxed);
    uint64_t previous = last_generation.load(std::memory_order_relaxed);
    while (previous != generation &&
           !last_generation.compare_exchange_weak(
               previous, generation, std::memory_order_relaxed,
               std::memory_order_relaxed)) {
    }
    if (previous != generation) {
      generations.fetch_add(1, std::memory_order_relaxed);
    }
  }
}

void ArmGuestCpuVisibility(uint32_t address, uint32_t length) {
  if (!g_graphics_census_memory || !g_guest_cpu_access_callback || !length) {
    return;
  }
  size_t target_count = g_guest_cpu_visibility_target_count.load(
      std::memory_order_relaxed);
  GuestCpuVisibilityTargetEntry *target = nullptr;
  for (size_t i = 0; i < target_count; ++i) {
    if (g_guest_cpu_visibility_targets[i].address.load(
            std::memory_order_relaxed) == address) {
      target = &g_guest_cpu_visibility_targets[i];
      break;
    }
  }
  if (!target) {
    if (target_count == kGuestCpuVisibilityTargetCapacity) {
      g_guest_cpu_visibility_target_overflow.fetch_add(
          1, std::memory_order_relaxed);
      return;
    }
    target = &g_guest_cpu_visibility_targets[target_count];
    target->address.store(address, std::memory_order_relaxed);
    g_guest_cpu_visibility_target_count.store(target_count + 1,
                                               std::memory_order_release);
  }
  const uint64_t generation =
      g_guest_cpu_visibility_armed_resolves.fetch_add(
          1, std::memory_order_relaxed) +
      1;
  g_guest_cpu_visibility_armed_bytes.fetch_add(length,
                                                std::memory_order_relaxed);
  target->length.store(length, std::memory_order_relaxed);
  target->generation.store(generation, std::memory_order_release);
  target->resolve_count.fetch_add(1, std::memory_order_relaxed);
  g_graphics_census_memory->EnablePhysicalMemoryAccessCallbacks(
      address, length, false, false, true);
}

uint64_t HashCombine(uint64_t hash, uint64_t value) {
  value += 0x9E3779B97F4A7C15ull + (hash << 6) + (hash >> 2);
  return hash ^ value;
}

uint32_t LoadSemanticGuestU32(rex::memory::Memory *memory,
                              uint32_t address) {
  return static_cast<uint32_t>(
      *rex::memory::GuestPtr<rex::be_u32 *>(memory->virtual_membase(),
                                            address));
}

template <size_t N>
void LoadSemanticGuestWords(rex::memory::Memory *memory, uint32_t address,
                            std::array<uint32_t, N> &words) {
  for (size_t i = 0; i < N; ++i) {
    words[i] = LoadSemanticGuestU32(
        memory, address + static_cast<uint32_t>(i * sizeof(uint32_t)));
  }
}

template <size_t N>
uint64_t HashSemanticWords(const std::array<uint32_t, N> &words) {
  uint64_t hash = 0xCBF29CE484222325ull;
  for (uint32_t word : words) {
    hash = HashCombine(hash, word);
  }
  return hash ? hash : 1;
}

bool RecordProceduralModelSemanticInstance(
    uint32_t stack_pointer, uint32_t receiver_address,
    std::array<uint32_t, 7> helper_arguments,
    SemanticDrawIdentity *semantic_draw) {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire)) {
    return false;
  }
  rex::memory::Memory *memory =
      g_command_buffer_lineage_memory.load(std::memory_order_acquire);
  if (!memory) {
    return false;
  }

  std::scoped_lock lock(g_semantic_instance_mutex);
  ++g_semantic_instance_observations;
  SemanticReceiverLifecycleEntry *lifecycle =
      FindSemanticReceiverLifecycle(receiver_address);
  if (!lifecycle ||
      lifecycle->state.load(std::memory_order_acquire) !=
          uint32_t(SemanticReceiverState::kLive)) {
    ++g_semantic_instance_unknown_receivers;
    return false;
  }
  const uint32_t receiver_generation =
      lifecycle->generation.load(std::memory_order_relaxed);
  if (!receiver_generation || stack_pointer > UINT32_MAX - 84 ||
      receiver_address > UINT32_MAX - 512) {
    ++g_semantic_instance_invalid_layouts;
    return false;
  }

  const uint32_t record_index =
      LoadSemanticGuestU32(memory, stack_pointer + 84);
  const uint32_t owner =
      LoadSemanticGuestU32(memory, receiver_address + 124);
  const uint32_t runtime_base =
      LoadSemanticGuestU32(memory, receiver_address + 128);
  const uint32_t active_buffer_index =
      LoadSemanticGuestU32(memory, receiver_address + 136);
  const uint32_t per_record_resource_capacity =
      LoadSemanticGuestU32(memory, receiver_address + 140);
  if (!owner || !runtime_base || (owner & 3) || (runtime_base & 3) ||
      owner > UINT32_MAX - 16) {
    ++g_semantic_instance_invalid_layouts;
    return false;
  }
  const uint32_t descriptor_base = LoadSemanticGuestU32(memory, owner);
  const uint32_t descriptor_count =
      LoadSemanticGuestU32(memory, owner + 12);
  if (!descriptor_base || (descriptor_base & 3) || !descriptor_count) {
    ++g_semantic_instance_invalid_layouts;
    return false;
  }
  if (record_index >= descriptor_count) {
    ++g_semantic_instance_invalid_indices;
    return false;
  }
  const uint64_t descriptor_address_64 =
      uint64_t(descriptor_base) + uint64_t(record_index) * 92;
  const uint64_t runtime_address_64 =
      uint64_t(runtime_base) + uint64_t(record_index) * 68;
  if (descriptor_address_64 + 92 > uint64_t(UINT32_MAX) + 1 ||
      runtime_address_64 + 68 > uint64_t(UINT32_MAX) + 1) {
    ++g_semantic_instance_invalid_layouts;
    return false;
  }
  const uint32_t descriptor_address = uint32_t(descriptor_address_64);
  const uint32_t runtime_address = uint32_t(runtime_address_64);
  *semantic_draw = {
      .receiver_address = receiver_address,
      .receiver_generation = receiver_generation,
      .record_index = record_index,
      .descriptor_address = descriptor_address,
      .runtime_address = runtime_address,
  };

  std::array<uint32_t, kSemanticDescriptorWordCount> descriptor_words{};
  std::array<uint32_t, kSemanticRuntimeWordCount> runtime_words{};
  std::array<uint32_t, kSemanticTransformWordCount> transform_words{};
  LoadSemanticGuestWords(memory, descriptor_address, descriptor_words);
  LoadSemanticGuestWords(memory, runtime_address, runtime_words);
  LoadSemanticGuestWords(memory, receiver_address + 320, transform_words);
  const uint64_t descriptor_hash = HashSemanticWords(descriptor_words);
  const uint64_t runtime_hash = HashSemanticWords(runtime_words);
  const uint64_t transform_hash = HashSemanticWords(transform_words);
  JoinSemanticVisibilityWorkset(receiver_address, receiver_generation,
                                record_index, semantic_draw);
  ++g_semantic_instance_live_observations;
  g_semantic_instance_payload_bytes += kSemanticObservationPayloadBytes;
  ++g_semantic_instance_replay_fallbacks;
  uint64_t key = 0xCBF29CE484222325ull;
  key = HashCombine(key, receiver_address);
  key = HashCombine(key, receiver_generation);
  key = HashCombine(key, record_index);
  key = key ? key : 1;

  size_t index = size_t(key % kSemanticInstanceCapacity);
  for (size_t probe = 0; probe < kSemanticInstanceCapacity; ++probe) {
    SemanticInstanceEntry &entry = g_semantic_instances[index];
    if (!entry.key) {
      entry.key = key;
      entry.calls = 1;
      entry.first_frame = g_frame_sequence.load(std::memory_order_relaxed);
      entry.last_frame = entry.first_frame;
      entry.descriptor_hash = descriptor_hash;
      entry.runtime_hash = runtime_hash;
      entry.transform_hash = transform_hash;
      entry.receiver_address = receiver_address;
      entry.receiver_generation = receiver_generation;
      entry.record_index = record_index;
      entry.descriptor_count = descriptor_count;
      entry.descriptor_address = descriptor_address;
      entry.runtime_address = runtime_address;
      entry.descriptor_kind = descriptor_words[36 / sizeof(uint32_t)];
      entry.active_buffer_index = active_buffer_index;
      entry.per_record_resource_capacity = per_record_resource_capacity;
      entry.helper_arguments = helper_arguments;
      entry.descriptor_words = descriptor_words;
      entry.runtime_words = runtime_words;
      entry.transform_words = transform_words;
      ++g_semantic_instance_count;
      return true;
    }
    if (entry.key == key && entry.receiver_address == receiver_address &&
        entry.receiver_generation == receiver_generation &&
        entry.record_index == record_index) {
      ++entry.calls;
      entry.last_frame = g_frame_sequence.load(std::memory_order_relaxed);
      entry.descriptor_variations += entry.descriptor_hash != descriptor_hash;
      entry.runtime_variations += entry.runtime_hash != runtime_hash;
      entry.transform_variations += entry.transform_hash != transform_hash;
      return true;
    }
    index = (index + 1) % kSemanticInstanceCapacity;
  }
  ++g_semantic_instance_overflow;
  return true;
}

void BeginProceduralModelRenderItem(
    uint32_t stack_pointer, uint32_t receiver_address,
    std::array<uint32_t, 7> helper_arguments) {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire)) {
    return;
  }
  g_semantic_render_item_entries.fetch_add(1, std::memory_order_relaxed);
  if (g_semantic_render_item_stack_depth ==
      kSemanticRenderItemStackCapacity) {
    g_semantic_render_item_stack_faults.fetch_add(
        1, std::memory_order_relaxed);
    ++g_semantic_render_item_stack_overflow_depth;
    return;
  }
  SemanticDrawIdentity &semantic_draw =
      g_semantic_render_item_stack[g_semantic_render_item_stack_depth++];
  semantic_draw = {};
  if (RecordProceduralModelSemanticInstance(
          stack_pointer, receiver_address, helper_arguments,
          &semantic_draw)) {
    g_semantic_render_item_valid_scopes.fetch_add(
        1, std::memory_order_relaxed);
  }
  g_semantic_render_items_open.fetch_add(1, std::memory_order_relaxed);
}

void EndProceduralModelRenderItem() {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire)) {
    return;
  }
  g_semantic_render_item_exits.fetch_add(1, std::memory_order_relaxed);
  if (g_semantic_render_item_stack_overflow_depth) {
    --g_semantic_render_item_stack_overflow_depth;
    return;
  }
  if (!g_semantic_render_item_stack_depth) {
    g_semantic_render_item_stack_faults.fetch_add(
        1, std::memory_order_relaxed);
    return;
  }
  const SemanticDrawIdentity &semantic_draw =
      g_semantic_render_item_stack[g_semantic_render_item_stack_depth - 1];
  if (semantic_draw.receiver_generation && !semantic_draw.valid) {
    g_semantic_render_item_scopes_without_submission.fetch_add(
        1, std::memory_order_relaxed);
  } else if (semantic_draw.valid && semantic_draw.direct_title_origins) {
    g_semantic_draw_dispatches_with_direct_title_origin.fetch_add(
        1, std::memory_order_relaxed);
  } else if (semantic_draw.valid) {
    g_semantic_draw_dispatches_without_direct_title_origin.fetch_add(
        1, std::memory_order_relaxed);
  }
  if (semantic_draw.valid && semantic_draw.indirect_packet_origins) {
    g_semantic_draw_dispatches_with_indirect_packet_origin.fetch_add(
        1, std::memory_order_relaxed);
  } else if (semantic_draw.valid) {
    g_semantic_draw_dispatches_without_indirect_packet_origin.fetch_add(
        1, std::memory_order_relaxed);
  }
  --g_semantic_render_item_stack_depth;
  g_semantic_render_items_open.fetch_sub(1, std::memory_order_relaxed);
}

void EmitSemanticVisibilityWorkset() {
  std::scoped_lock lock(g_semantic_visibility_workset_mutex);
  uint64_t entry_observations = 0;
  uint64_t entry_selected = 0;
  uint64_t entry_rejected = 0;
  uint64_t entry_title_matches = 0;
  uint64_t entry_title_mismatches = 0;
  uint64_t entry_semantic_joins = 0;
  uint64_t entry_title_lod_observations = 0;
  for (const SemanticVisibilityWorksetEntry &entry :
       g_semantic_visibility_workset) {
    if (!entry.key) {
      continue;
    }
    entry_observations += entry.observations;
    entry_selected += entry.predicted_selected;
    entry_rejected += entry.predicted_rejected;
    entry_title_matches += entry.title_matches;
    entry_title_mismatches += entry.title_mismatches;
    entry_semantic_joins += entry.semantic_instance_joins;
    entry_title_lod_observations += entry.title_lod_observations;
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.discovery.semantic_visibility_workset_entry",
        {{"status", "complete"},
         {"key", fmt::format("{:016X}", entry.key)},
         {"receiver_address",
          fmt::format("{:08X}", entry.receiver_address)},
         {"receiver_generation",
          std::to_string(entry.receiver_generation)},
         {"record_index", std::to_string(entry.record_index)},
         {"category", std::to_string(entry.category)},
         {"observations", std::to_string(entry.observations)},
         {"first_frame", std::to_string(entry.first_frame)},
         {"last_frame", std::to_string(entry.last_frame)},
         {"predicted_selected",
          std::to_string(entry.predicted_selected)},
         {"predicted_rejected",
          std::to_string(entry.predicted_rejected)},
         {"title_matches", std::to_string(entry.title_matches)},
         {"title_mismatches", std::to_string(entry.title_mismatches)},
         {"semantic_instance_joins",
          std::to_string(entry.semantic_instance_joins)},
         {"latest_category_result_mask",
          std::to_string(entry.latest_category_result_mask)},
         {"latest_selected", entry.latest_selected ? "true" : "false"},
         {"title_lod_observations",
          std::to_string(entry.title_lod_observations)},
         {"latest_title_lod_index",
          std::to_string(entry.latest_title_lod_index)},
         {"latest_title_lod_valid",
          entry.latest_title_lod_valid ? "true" : "false"},
         {"title_lod_lineage", "latest_exact_title_record_observation"},
         {"execution", "bounded_host_visibility_workset"},
         {"guest_state_changed", "false"},
         {"title_culling_changed", "false"},
         {"native_draw", "false"},
         {"xenos_authority", "true"},
         {"suppression_allowed", "false"}});
  }
  const bool accounting_complete =
      g_semantic_visibility_workset_modelled_records ==
          g_semantic_visibility_workset_predicted_selected +
              g_semantic_visibility_workset_predicted_rejected &&
      g_semantic_visibility_workset_modelled_records ==
          g_semantic_visibility_workset_title_matches +
              g_semantic_visibility_workset_title_mismatches &&
      g_semantic_visibility_workset_modelled_records ==
          entry_observations + g_semantic_visibility_workset_overflow &&
      g_semantic_visibility_workset_predicted_selected == entry_selected &&
      g_semantic_visibility_workset_predicted_rejected == entry_rejected &&
      g_semantic_visibility_workset_title_matches == entry_title_matches &&
      g_semantic_visibility_workset_title_mismatches ==
          entry_title_mismatches &&
      g_semantic_visibility_workset_title_lod_records ==
          entry_title_lod_observations &&
      g_semantic_visibility_workset_semantic_instance_lookups ==
          g_semantic_visibility_workset_selected_joins +
              g_semantic_visibility_workset_rejected_joins +
              g_semantic_visibility_workset_missing_joins &&
      entry_semantic_joins ==
          g_semantic_visibility_workset_selected_joins +
              g_semantic_visibility_workset_rejected_joins;
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.discovery.semantic_visibility_workset_summary",
      {{"status", accounting_complete ? "complete" : "incomplete"},
       {"modelled_records",
        std::to_string(g_semantic_visibility_workset_modelled_records)},
       {"predicted_selected",
        std::to_string(g_semantic_visibility_workset_predicted_selected)},
       {"predicted_rejected",
        std::to_string(g_semantic_visibility_workset_predicted_rejected)},
       {"title_matches",
        std::to_string(g_semantic_visibility_workset_title_matches)},
       {"title_mismatches",
        std::to_string(g_semantic_visibility_workset_title_mismatches)},
       {"title_lod_records",
        std::to_string(g_semantic_visibility_workset_title_lod_records)},
       {"entry_title_lod_observations",
        std::to_string(entry_title_lod_observations)},
       {"invalid_records",
        std::to_string(g_semantic_visibility_workset_invalid_records)},
       {"entries", std::to_string(g_semantic_visibility_workset_entries)},
       {"entry_observations", std::to_string(entry_observations)},
       {"capacity", std::to_string(kSemanticVisibilityWorksetCapacity)},
       {"overflow", std::to_string(g_semantic_visibility_workset_overflow)},
       {"semantic_instance_lookups",
        std::to_string(
            g_semantic_visibility_workset_semantic_instance_lookups)},
       {"selected_joins",
        std::to_string(g_semantic_visibility_workset_selected_joins)},
       {"rejected_joins",
        std::to_string(g_semantic_visibility_workset_rejected_joins)},
       {"missing_joins",
        std::to_string(g_semantic_visibility_workset_missing_joins)},
       {"accounting_complete", accounting_complete ? "true" : "false"},
       {"model", "independent_policy_to_semantic_candidate_handoff"},
       {"identity", "receiver_generation_record_index"},
       {"title_lod_lineage", "latest_exact_title_record_observation"},
       {"execution", "bounded_host_visibility_workset"},
       {"guest_state_changed", "false"},
       {"control_flow_changed", "false"},
       {"title_culling_changed", "false"},
       {"native_lod", "false"},
       {"native_draw", "false"},
       {"xenos_authority", "true"},
       {"suppression_allowed", "false"}});
}

void EmitProceduralModelSemanticInstances() {
  std::scoped_lock lock(g_semantic_instance_mutex);
  for (const SemanticInstanceEntry &entry : g_semantic_instances) {
    if (!entry.key) {
      continue;
    }
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.discovery.semantic_instance_entry",
        {{"class", "proceduralGeometry::CProceduralModels"},
         {"key", fmt::format("{:016X}", entry.key)},
         {"calls", std::to_string(entry.calls)},
         {"first_frame", std::to_string(entry.first_frame)},
         {"last_frame", std::to_string(entry.last_frame)},
         {"receiver_address",
          fmt::format("{:08X}", entry.receiver_address)},
         {"receiver_generation",
          std::to_string(entry.receiver_generation)},
         {"record_index", std::to_string(entry.record_index)},
         {"descriptor_count", std::to_string(entry.descriptor_count)},
         {"descriptor_address",
          fmt::format("{:08X}", entry.descriptor_address)},
         {"runtime_address", fmt::format("{:08X}", entry.runtime_address)},
         {"descriptor_kind", std::to_string(entry.descriptor_kind)},
         {"active_buffer_index",
          std::to_string(entry.active_buffer_index)},
         {"per_record_resource_capacity",
          std::to_string(entry.per_record_resource_capacity)},
         {"helper_arguments",
          fmt::format(
              "{:08X},{:08X},{:08X},{:08X},{:08X},{:08X},{:08X}",
              entry.helper_arguments[0], entry.helper_arguments[1],
              entry.helper_arguments[2], entry.helper_arguments[3],
              entry.helper_arguments[4], entry.helper_arguments[5],
              entry.helper_arguments[6])},
         {"descriptor_hash", fmt::format("{:016X}", entry.descriptor_hash)},
         {"runtime_hash", fmt::format("{:016X}", entry.runtime_hash)},
         {"transform_hash", fmt::format("{:016X}", entry.transform_hash)},
         {"descriptor_variations",
          std::to_string(entry.descriptor_variations)},
         {"runtime_variations", std::to_string(entry.runtime_variations)},
         {"transform_variations",
          std::to_string(entry.transform_variations)},
         {"immutable_sample_words", "88"},
         {"classification", "unclassified_material_or_state"},
         {"fallback", "xenos_replay"},
         {"guest_payload_read", "bounded_semantic_records_only"},
         {"guest_state_changed", "false"},
         {"native_upload", "false"},
         {"native_draw", "false"},
         {"xenos_authority", "true"},
         {"suppression_allowed", "false"}});
  }
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.discovery.semantic_instance_summary",
      {{"observations", std::to_string(g_semantic_instance_observations)},
       {"live_observations",
        std::to_string(g_semantic_instance_live_observations)},
       {"unknown_receivers",
        std::to_string(g_semantic_instance_unknown_receivers)},
       {"invalid_layouts",
        std::to_string(g_semantic_instance_invalid_layouts)},
       {"invalid_indices",
        std::to_string(g_semantic_instance_invalid_indices)},
       {"payload_bytes",
        std::to_string(g_semantic_instance_payload_bytes)},
       {"replay_fallbacks",
        std::to_string(g_semantic_instance_replay_fallbacks)},
       {"native_admissions",
        std::to_string(g_semantic_instance_native_admissions)},
       {"entries", std::to_string(g_semantic_instance_count)},
       {"capacity", std::to_string(kSemanticInstanceCapacity)},
       {"overflow", std::to_string(g_semantic_instance_overflow)},
       {"payload_bytes_per_live_observation",
        std::to_string(kSemanticObservationPayloadBytes)},
       {"fallback", "xenos_replay"},
       {"guest_payload_read", "bounded_semantic_records_only"},
       {"guest_state_changed", "false"},
       {"native_upload", "false"},
       {"native_draw", "false"},
       {"xenos_authority", "true"},
       {"suppression_allowed", "false"}});
}

const char *SemanticResourceProviderSelectionName(
    SemanticResourceProviderSelection selection) {
  switch (selection) {
  case SemanticResourceProviderSelection::kLookupMissing:
    return "lookup_missing";
  case SemanticResourceProviderSelection::kPrimaryMethod:
    return "primary_method_36";
  case SemanticResourceProviderSelection::kFallbackMethod:
    return "fallback_method_40";
  case SemanticResourceProviderSelection::kUnavailable:
    return "provider_unavailable";
  default:
    return "unknown";
  }
}

const char *SemanticResourceObjectSourceName(
    SemanticResourceObjectSource source) {
  switch (source) {
  case SemanticResourceObjectSource::kProviderMethod:
    return "provider_method";
  case SemanticResourceObjectSource::kSecondaryResolution:
    return "secondary_resolution";
  case SemanticResourceObjectSource::kNone:
    return "none";
  default:
    return "unknown";
  }
}

bool IsResolvedSemanticResourceProviderProvenance(
    const SemanticResourceProviderProvenance &provider) {
  const bool selected_provider_path =
      provider.selection == SemanticResourceProviderSelection::kPrimaryMethod ||
      provider.selection ==
          SemanticResourceProviderSelection::kFallbackMethod ||
      provider.selection == SemanticResourceProviderSelection::kUnavailable;
  const bool produced_object =
      provider.object_source == SemanticResourceObjectSource::kProviderMethod ||
      provider.object_source ==
          SemanticResourceObjectSource::kSecondaryResolution;
  return provider.provider_object && provider.provider_vtable &&
         provider.predicate_24_method && provider.primary_36_method &&
         provider.fallback_40_method && provider.predicate_44_method &&
         selected_provider_path && produced_object;
}

void PublishProceduralModelResourceBinding(
    uint32_t binding_slot, uint32_t bound_resource_object,
    const SemanticResourceProviderProvenance &provider) {
  if (binding_slot == 0) {
    g_pending_semantic_bindings.primary_bound_resource_object =
        bound_resource_object;
    g_pending_semantic_bindings.primary_provider = provider;
    g_pending_semantic_bindings.primary_resolution_known = true;
  } else if (binding_slot == 1) {
    g_pending_semantic_bindings.secondary_bound_resource_object =
        bound_resource_object;
    g_pending_semantic_bindings.secondary_provider = provider;
    g_pending_semantic_bindings.secondary_resolution_known = true;
  }
}

void InvalidateProceduralModelResolverCacheCandidate(
    PendingSemanticResourceResolution &resolution) {
  if (!resolution.resolver_cache_candidate) {
    return;
  }
  if (resolution.resolver_cache_index >= 0 &&
      size_t(resolution.resolver_cache_index) <
          g_semantic_resolver_cache_slots.size()) {
    g_semantic_resolver_cache_slots[size_t(resolution.resolver_cache_index)] =
        {};
  }
  resolution.resolved_resource_object = 0;
  resolution.provider = {};
  resolution.resolver_cache_candidate = false;
  resolution.resolver_cache_index = -1;
}

bool FinalizeProceduralModelResourceCacheCandidate() {
  PendingSemanticResourceResolution &resolution =
      g_pending_semantic_resource_resolution;
  if (!resolution.active || !resolution.cache_candidate ||
      resolution.binding_slot >= 5 ||
      !resolution.resolved_resource_object) {
    return false;
  }
  ++g_semantic_resource_resolution_cache_hits;
  if (resolution.binding_slot > 1) {
    return false;
  }
  g_semantic_binding_cache_slots[resolution.binding_slot] = {
      .resource_key = resolution.resource_key,
      .bound_resource_object = resolution.resolved_resource_object,
      .provider = resolution.provider,
      .key_known = true,
  };
  PublishProceduralModelResourceBinding(resolution.binding_slot,
                                        resolution.resolved_resource_object,
                                        resolution.provider);
  resolution = {};
  return true;
}

void RecordProceduralModelResourceBinding(
    uint32_t expected_slot, uint32_t graphics_argument,
    uint32_t resource_key, uint32_t binding_slot,
    uint32_t lookup_argument, uint32_t lookup_context,
    uint32_t runtime_address, uint32_t receiver_address,
    uint32_t descriptor_address, uint32_t graphics_context) {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire)) {
    return;
  }
  std::scoped_lock lock(g_semantic_submission_mutex);
  if (expected_slot == 0) {
    ++g_semantic_primary_binding_observations;
    g_pending_semantic_bindings = {};
  } else {
    ++g_semantic_secondary_binding_observations;
  }
  if (g_pending_semantic_resource_resolution.active &&
      !FinalizeProceduralModelResourceCacheCandidate()) {
    ++g_semantic_resource_resolution_protocol_faults;
    g_pending_semantic_resource_resolution = {};
  }
  if (binding_slot != expected_slot || graphics_argument != graphics_context ||
      lookup_argument != lookup_context || !receiver_address ||
      !descriptor_address || !runtime_address || !graphics_context) {
    g_pending_semantic_bindings = {};
    return;
  }
  if (expected_slot == 0) {
    g_pending_semantic_bindings = {
        .receiver_address = receiver_address,
        .descriptor_address = descriptor_address,
        .runtime_address = runtime_address,
        .graphics_context = graphics_context,
        .resource_lookup_context = lookup_context,
        .primary_resource_key = resource_key,
        .primary_seen = true,
    };
  } else {
    if (!g_pending_semantic_bindings.primary_seen ||
        g_pending_semantic_bindings.receiver_address != receiver_address ||
        g_pending_semantic_bindings.descriptor_address != descriptor_address ||
        g_pending_semantic_bindings.runtime_address != runtime_address ||
        g_pending_semantic_bindings.graphics_context != graphics_context ||
        g_pending_semantic_bindings.resource_lookup_context != lookup_context) {
      g_pending_semantic_bindings = {};
      return;
    }
    g_pending_semantic_bindings.secondary_resource_key = resource_key;
    g_pending_semantic_bindings.secondary_seen = true;
  }

  auto *kernel_state = rex::system::kernel_state();
  auto *memory = kernel_state ? kernel_state->memory() : nullptr;
  const uint32_t guest_cached_key =
      memory ? LoadSemanticGuestU32(
                   memory, kResourceBindingKeyCacheAddress + binding_slot * 4)
             : ~resource_key;
  const bool title_binding_cache_hit = int32_t(resource_key) >= 0 &&
                                       guest_cached_key == resource_key;
  SemanticBindingCacheSlot &cached_binding =
      g_semantic_binding_cache_slots[binding_slot];
  if (cached_binding.key_known &&
      cached_binding.resource_key != guest_cached_key) {
    cached_binding = {};
  }
  int32_t resolver_cache_index = -1;
  for (size_t index = 0; index < g_semantic_resolver_cache_slots.size();
       ++index) {
    const SemanticResolverCacheSlot &candidate =
        g_semantic_resolver_cache_slots[index];
    if (candidate.key_known && candidate.resource_key == resource_key &&
        candidate.bound_resource_object) {
      resolver_cache_index = int32_t(index);
      break;
    }
  }
  const bool resolver_cache_candidate = resolver_cache_index >= 0;
  const bool binding_mirror_candidate =
      cached_binding.key_known && cached_binding.resource_key == resource_key &&
      cached_binding.bound_resource_object;
  const bool cache_candidate =
      title_binding_cache_hit &&
      (binding_mirror_candidate || resolver_cache_candidate);
  const SemanticResourceProviderProvenance cached_provider =
      binding_mirror_candidate
          ? cached_binding.provider
          : resolver_cache_candidate
                ? g_semantic_resolver_cache_slots[size_t(resolver_cache_index)]
                      .provider
                : SemanticResourceProviderProvenance{};
  const uint32_t cached_object =
      binding_mirror_candidate
          ? cached_binding.bound_resource_object
          : resolver_cache_candidate
                ? g_semantic_resolver_cache_slots[size_t(resolver_cache_index)]
                      .bound_resource_object
                : 0;
  const uint32_t cached_resolver_slot =
      resolver_cache_candidate
          ? g_semantic_resolver_cache_slots[size_t(resolver_cache_index)]
                .resolver_cache_slot
          : 0;
  if (!cache_candidate) {
    ++g_semantic_resource_resolution_attempts;
  }
  g_pending_semantic_resource_resolution = {
      .resource_key = resource_key,
      .binding_slot = binding_slot,
      .graphics_context = graphics_context,
      .resolved_resource_object = cached_object,
      .provider = cached_provider,
      .resolver_cache_slot = cached_resolver_slot,
      .resolver_cache_index = resolver_cache_index,
      .active = true,
      .cache_candidate = cache_candidate,
      .resolver_cache_candidate =
          !title_binding_cache_hit && resolver_cache_candidate,
  };
}

void RecordProceduralModelResourceProviderLookup(uint32_t provider_object,
                                                 uint32_t lookup_context,
                                                 uint32_t resolver_cache_slot) {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire) ||
      !g_pending_semantic_resource_resolution.active) {
    return;
  }
  std::scoped_lock lock(g_semantic_submission_mutex);
  PendingSemanticResourceResolution &resolution =
      g_pending_semantic_resource_resolution;
  if (!resolution.active || resolution.provider_lookup_seen ||
      lookup_context != g_pending_semantic_bindings.resource_lookup_context ||
      !resolver_cache_slot || (resolver_cache_slot & 3)) {
    ++g_semantic_resource_resolution_protocol_faults;
    resolution = {};
    return;
  }
  if (resolution.cache_candidate) {
    ++g_semantic_resource_resolution_protocol_faults;
    resolution = {};
    return;
  }
  InvalidateProceduralModelResolverCacheCandidate(resolution);
  ++g_semantic_provider_lookup_observations;
  resolution.provider_lookup_seen = true;
  resolution.resolver_cache_slot = resolver_cache_slot;
  int32_t cache_index = -1;
  int32_t empty_index = -1;
  for (size_t index = 0; index < g_semantic_resolver_cache_slots.size();
       ++index) {
    const SemanticResolverCacheSlot &candidate =
        g_semantic_resolver_cache_slots[index];
    if (candidate.resolver_cache_slot == resolver_cache_slot) {
      cache_index = int32_t(index);
      break;
    }
    if (!candidate.resolver_cache_slot && empty_index < 0) {
      empty_index = int32_t(index);
    }
  }
  if (cache_index < 0) {
    cache_index = empty_index;
  }
  if (cache_index < 0) {
    ++g_semantic_resource_resolution_protocol_faults;
    resolution = {};
    return;
  }
  resolution.resolver_cache_index = cache_index;
  g_semantic_resolver_cache_slots[size_t(cache_index)] = {
      .resolver_cache_slot = resolver_cache_slot,
  };
  if (!provider_object) {
    ++g_semantic_provider_lookup_misses;
    resolution.provider.selection =
        SemanticResourceProviderSelection::kLookupMissing;
    return;
  }
  auto *kernel_state = rex::system::kernel_state();
  if (!kernel_state || !kernel_state->memory() || (provider_object & 3)) {
    ++g_semantic_resource_resolution_protocol_faults;
    resolution = {};
    return;
  }
  auto *memory = kernel_state->memory();
  const uint32_t provider_vtable =
      LoadSemanticGuestU32(memory, provider_object);
  if (!provider_vtable || (provider_vtable & 3) ||
      provider_vtable > UINT32_MAX - 44) {
    ++g_semantic_resource_resolution_protocol_faults;
    resolution = {};
    return;
  }
  SemanticResourceProviderProvenance provider = {
      .provider_object = provider_object,
      .provider_vtable = provider_vtable,
      .predicate_24_method = LoadSemanticGuestU32(memory, provider_vtable + 24),
      .primary_36_method = LoadSemanticGuestU32(memory, provider_vtable + 36),
      .fallback_40_method = LoadSemanticGuestU32(memory, provider_vtable + 40),
      .predicate_44_method = LoadSemanticGuestU32(memory, provider_vtable + 44),
  };
  if (!provider.predicate_24_method || !provider.primary_36_method ||
      !provider.fallback_40_method || !provider.predicate_44_method ||
      (provider.predicate_24_method & 3) || (provider.primary_36_method & 3) ||
      (provider.fallback_40_method & 3) || (provider.predicate_44_method & 3)) {
    ++g_semantic_resource_resolution_protocol_faults;
    resolution = {};
    return;
  }
  resolution.provider = provider;
  g_semantic_provider_metadata_bytes += 20;
}

void RecordProceduralModelResourceProviderPrimaryPredicate(
    uint32_t predicate_result, uint32_t provider_object) {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire) ||
      !g_pending_semantic_resource_resolution.active) {
    return;
  }
  std::scoped_lock lock(g_semantic_submission_mutex);
  PendingSemanticResourceResolution &resolution =
      g_pending_semantic_resource_resolution;
  if (!resolution.active || !resolution.provider_lookup_seen ||
      !resolution.provider.provider_object ||
      resolution.provider.provider_object != provider_object ||
      resolution.primary_predicate_seen) {
    ++g_semantic_resource_resolution_protocol_faults;
    resolution = {};
    return;
  }
  resolution.primary_predicate_seen = true;
  if (predicate_result & 0xFF) {
    resolution.provider.selection =
        SemanticResourceProviderSelection::kPrimaryMethod;
    ++g_semantic_provider_primary_selections;
  }
}

void RecordProceduralModelResourceProviderFallbackPredicate(
    uint32_t predicate_result, uint32_t provider_object) {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire) ||
      !g_pending_semantic_resource_resolution.active) {
    return;
  }
  std::scoped_lock lock(g_semantic_submission_mutex);
  PendingSemanticResourceResolution &resolution =
      g_pending_semantic_resource_resolution;
  if (!resolution.active || !resolution.primary_predicate_seen ||
      resolution.provider.selection !=
          SemanticResourceProviderSelection::kUnknown ||
      resolution.provider.provider_object != provider_object ||
      resolution.fallback_predicate_seen) {
    ++g_semantic_resource_resolution_protocol_faults;
    resolution = {};
    return;
  }
  resolution.fallback_predicate_seen = true;
  if (predicate_result & 0xFF) {
    resolution.provider.selection =
        SemanticResourceProviderSelection::kFallbackMethod;
    ++g_semantic_provider_fallback_selections;
  } else {
    resolution.provider.selection =
        SemanticResourceProviderSelection::kUnavailable;
    ++g_semantic_provider_unavailable_selections;
  }
}

void RecordProceduralModelResourceProviderMethodResult(
    uint32_t provider_method_result, uint32_t provider_object,
    uint32_t resolver_cache_slot) {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire) ||
      !g_pending_semantic_resource_resolution.active) {
    return;
  }
  std::scoped_lock lock(g_semantic_submission_mutex);
  PendingSemanticResourceResolution &resolution =
      g_pending_semantic_resource_resolution;
  if (!resolution.active || resolution.provider_method_result_seen ||
      resolution.provider.provider_object != provider_object ||
      resolution.resolver_cache_slot != resolver_cache_slot ||
      (resolution.provider.selection !=
           SemanticResourceProviderSelection::kPrimaryMethod &&
       resolution.provider.selection !=
           SemanticResourceProviderSelection::kFallbackMethod)) {
    ++g_semantic_resource_resolution_protocol_faults;
    resolution = {};
    return;
  }
  ++g_semantic_provider_method_results;
  if (!provider_method_result) {
    ++g_semantic_provider_method_null_results;
  }
  resolution.provider_method_result_seen = true;
  resolution.provider_method_result = provider_method_result;
}

void RecordProceduralModelResourceSecondaryResolutionResult(
    uint32_t secondary_resolution_result, uint32_t provider_object,
    uint32_t resolver_cache_slot) {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire) ||
      !g_pending_semantic_resource_resolution.active) {
    return;
  }
  std::scoped_lock lock(g_semantic_submission_mutex);
  PendingSemanticResourceResolution &resolution =
      g_pending_semantic_resource_resolution;
  const bool secondary_resolution_expected =
      resolution.provider.selection ==
          SemanticResourceProviderSelection::kUnavailable ||
      (resolution.provider_method_result_seen &&
       !resolution.provider_method_result);
  if (!resolution.active || !secondary_resolution_expected ||
      resolution.secondary_resolution_result_seen ||
      resolution.provider.provider_object != provider_object ||
      resolution.resolver_cache_slot != resolver_cache_slot) {
    ++g_semantic_resource_resolution_protocol_faults;
    resolution = {};
    return;
  }
  ++g_semantic_secondary_resolution_attempts;
  if (secondary_resolution_result) {
    ++g_semantic_secondary_resolution_successes;
  } else {
    ++g_semantic_secondary_resolution_misses;
  }
  resolution.secondary_resolution_result_seen = true;
  resolution.secondary_resolution_result = secondary_resolution_result;
}

void RecordProceduralModelResourceResolutionResult(
    uint32_t resolved_resource_object, uint32_t graphics_context,
    uint32_t binding_slot) {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire) ||
      !g_pending_semantic_resource_resolution.active) {
    return;
  }
  std::scoped_lock lock(g_semantic_submission_mutex);
  PendingSemanticResourceResolution &resolution =
      g_pending_semantic_resource_resolution;
  if (!resolution.active || resolution.result_seen ||
      resolution.graphics_context != graphics_context ||
      resolution.binding_slot != binding_slot || binding_slot >= 5) {
    ++g_semantic_resource_resolution_protocol_faults;
    resolution = {};
    return;
  }
  if (resolution.cache_candidate) {
    ++g_semantic_resource_resolution_protocol_faults;
    resolution = {};
    return;
  }
  if (resolution.resolver_cache_candidate) {
    if (resolution.provider_lookup_seen || !resolved_resource_object ||
        resolved_resource_object != resolution.resolved_resource_object ||
        !IsResolvedSemanticResourceProviderProvenance(resolution.provider)) {
      ++g_semantic_resource_resolution_protocol_faults;
      resolution = {};
      return;
    }
    ++g_semantic_provider_cache_hits;
    resolution.result_seen = true;
    return;
  }
  bool provider_chain_valid = resolution.provider_lookup_seen;
  if (resolution.provider.selection ==
      SemanticResourceProviderSelection::kLookupMissing) {
    provider_chain_valid = provider_chain_valid && !resolved_resource_object;
    resolution.provider.object_source = SemanticResourceObjectSource::kNone;
  } else if (resolution.provider.selection ==
                 SemanticResourceProviderSelection::kPrimaryMethod ||
             resolution.provider.selection ==
                 SemanticResourceProviderSelection::kFallbackMethod) {
    provider_chain_valid =
        provider_chain_valid && resolution.provider_method_result_seen;
    if (resolution.provider_method_result) {
      provider_chain_valid =
          provider_chain_valid &&
          !resolution.secondary_resolution_result_seen &&
          resolved_resource_object == resolution.provider_method_result;
      resolution.provider.object_source =
          SemanticResourceObjectSource::kProviderMethod;
    } else {
      provider_chain_valid =
          provider_chain_valid && resolution.secondary_resolution_result_seen &&
          resolved_resource_object == resolution.secondary_resolution_result;
      resolution.provider.object_source =
          SemanticResourceObjectSource::kSecondaryResolution;
    }
  } else if (resolution.provider.selection ==
             SemanticResourceProviderSelection::kUnavailable) {
    provider_chain_valid =
        provider_chain_valid && !resolution.provider_method_result_seen &&
        resolution.secondary_resolution_result_seen &&
        resolved_resource_object == resolution.secondary_resolution_result;
    resolution.provider.object_source =
        SemanticResourceObjectSource::kSecondaryResolution;
  } else {
    provider_chain_valid = false;
  }
  if (!provider_chain_valid) {
    ++g_semantic_resource_resolution_protocol_faults;
    resolution = {};
    return;
  }
  resolution.result_seen = true;
  resolution.resolved_resource_object = resolved_resource_object;
  if (resolved_resource_object) {
    return;
  }

  ++g_semantic_resource_resolution_misses;
  if (resolution.resolver_cache_index < 0 ||
      size_t(resolution.resolver_cache_index) >=
          g_semantic_resolver_cache_slots.size()) {
    ++g_semantic_resource_resolution_protocol_faults;
    resolution = {};
    return;
  }
  g_semantic_resolver_cache_slots[size_t(resolution.resolver_cache_index)] = {
      .resolver_cache_slot = resolution.resolver_cache_slot,
      .resource_key = resolution.resource_key,
      .bound_resource_object = 0,
      .provider = resolution.provider,
      .key_known = true,
  };
  if (binding_slot == 0) {
    g_pending_semantic_bindings.primary_resolution_known = true;
  } else {
    g_pending_semantic_bindings.secondary_resolution_known = true;
  }
  resolution = {};
}

void RecordProceduralModelResourceBindDispatch(
    uint32_t graphics_argument, uint32_t binding_slot,
    uint32_t bound_resource_object, uint32_t graphics_context,
    uint32_t expected_slot) {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire) ||
      !g_pending_semantic_resource_resolution.active) {
    return;
  }
  std::scoped_lock lock(g_semantic_submission_mutex);
  PendingSemanticResourceResolution &resolution =
      g_pending_semantic_resource_resolution;
  if (!resolution.active || !resolution.result_seen ||
      resolution.graphics_context != graphics_context ||
      graphics_argument != graphics_context ||
      resolution.binding_slot != binding_slot || binding_slot != expected_slot ||
      binding_slot >= 5 || !bound_resource_object ||
      resolution.resolved_resource_object != bound_resource_object) {
    ++g_semantic_resource_resolution_protocol_faults;
    resolution = {};
    return;
  }

  ++g_semantic_resource_resolution_successes;
  ++g_semantic_resource_bind_dispatches;
  if (resolution.resolver_cache_index < 0 ||
      size_t(resolution.resolver_cache_index) >=
          g_semantic_resolver_cache_slots.size()) {
    ++g_semantic_resource_resolution_protocol_faults;
    resolution = {};
    return;
  }
  g_semantic_resolver_cache_slots[size_t(resolution.resolver_cache_index)] = {
      .resolver_cache_slot = resolution.resolver_cache_slot,
      .resource_key = resolution.resource_key,
      .bound_resource_object = bound_resource_object,
      .provider = resolution.provider,
      .key_known = true,
  };
  g_semantic_binding_cache_slots[binding_slot] = {
      .resource_key = resolution.resource_key,
      .bound_resource_object = bound_resource_object,
      .provider = resolution.provider,
      .key_known = true,
  };
  PublishProceduralModelResourceBinding(
      binding_slot, bound_resource_object, resolution.provider);
  resolution = {};
}

const char *ProceduralModelDescriptorKindGroup(uint32_t descriptor_kind) {
  if (descriptor_kind == 4 || descriptor_kind == 5) {
    return "kind_4_5";
  }
  if (descriptor_kind == 1 || descriptor_kind == 3) {
    return "kind_1_3";
  }
  return "other";
}

const char *ProceduralModelHelperStateFamily(uint32_t helper_state) {
  if (helper_state == 9) {
    return "state_9_table_4_28";
  }
  if (helper_state == 11) {
    return "state_11_table_196_220";
  }
  if (helper_state >= 24 && helper_state <= 27) {
    return "state_24_27_table_148_172";
  }
  if (helper_state >= 6 && helper_state <= 8) {
    return "state_6_8_table_100_124";
  }
  return "default_table_52_76";
}

void JoinProceduralModelSemanticDraw(uint64_t submission_key,
                                     uint32_t receiver_address,
                                     uint32_t receiver_generation,
                                     uint32_t record_index,
                                     uint32_t descriptor_address,
                                     uint32_t runtime_address,
                                     uint32_t descriptor_kind,
                                     uint32_t helper_state,
                                     uint32_t primary_resource_key,
                                     uint32_t secondary_resource_key,
                                     bool secondary_resource_present) {
  if (!g_semantic_render_item_stack_depth) {
    g_semantic_draw_scope_mismatches.fetch_add(1,
                                                std::memory_order_relaxed);
    return;
  }
  SemanticDrawIdentity &semantic_draw =
      g_semantic_render_item_stack[g_semantic_render_item_stack_depth - 1];
  if (!submission_key || semantic_draw.valid ||
      semantic_draw.receiver_address != receiver_address ||
      semantic_draw.receiver_generation != receiver_generation ||
      semantic_draw.record_index != record_index ||
      semantic_draw.descriptor_address != descriptor_address ||
      semantic_draw.runtime_address != runtime_address) {
    g_semantic_draw_scope_mismatches.fetch_add(1,
                                                std::memory_order_relaxed);
    return;
  }
  semantic_draw.submission_key = submission_key;
  semantic_draw.descriptor_kind = descriptor_kind;
  semantic_draw.helper_state = helper_state;
  semantic_draw.primary_resource_key = primary_resource_key;
  semantic_draw.secondary_resource_key = secondary_resource_key;
  semantic_draw.secondary_resource_present = secondary_resource_present;
  semantic_draw.valid = true;
  g_semantic_draw_scope_joins.fetch_add(1, std::memory_order_relaxed);
}

void RecordProceduralModelGeometrySubmission(
    uint32_t resource_lookup_context, uint32_t count_units,
    uint32_t source_address, uint32_t helper_state,
    uint32_t runtime_address, uint32_t receiver_address,
    uint32_t descriptor_address, uint32_t graphics_context) {
  if (!g_command_buffer_lineage_installed.load(std::memory_order_acquire)) {
    return;
  }
  rex::memory::Memory *memory =
      g_command_buffer_lineage_memory.load(std::memory_order_acquire);
  if (!memory) {
    return;
  }

  std::scoped_lock lock(g_semantic_submission_mutex);
  ++g_semantic_submission_observations;
  if (g_pending_semantic_resource_resolution.active &&
      !FinalizeProceduralModelResourceCacheCandidate()) {
    ++g_semantic_resource_resolution_protocol_faults;
    ++g_semantic_submission_unresolved_resource_joins;
    g_pending_semantic_resource_resolution = {};
    g_pending_semantic_bindings = {};
    return;
  }
  const PendingSemanticResourceBindings pending =
      g_pending_semantic_bindings;
  g_pending_semantic_bindings = {};
  if (!pending.primary_seen || pending.receiver_address != receiver_address ||
      pending.descriptor_address != descriptor_address ||
      pending.runtime_address != runtime_address ||
      pending.graphics_context != graphics_context ||
      pending.resource_lookup_context != resource_lookup_context) {
    ++g_semantic_submission_binding_mismatches;
    return;
  }

  SemanticReceiverLifecycleEntry *lifecycle =
      FindSemanticReceiverLifecycle(receiver_address);
  if (!lifecycle ||
      lifecycle->state.load(std::memory_order_acquire) !=
          uint32_t(SemanticReceiverState::kLive)) {
    ++g_semantic_submission_unknown_receivers;
    return;
  }
  const uint32_t receiver_generation =
      lifecycle->generation.load(std::memory_order_relaxed);
  if (!receiver_generation || receiver_address > UINT32_MAX - 144 ||
      (descriptor_address & 3) || (runtime_address & 3)) {
    ++g_semantic_submission_invalid_record_joins;
    return;
  }

  const uint32_t owner =
      LoadSemanticGuestU32(memory, receiver_address + 124);
  const uint32_t runtime_base =
      LoadSemanticGuestU32(memory, receiver_address + 128);
  const uint32_t resource_table =
      LoadSemanticGuestU32(memory, receiver_address + 8);
  if (!owner || !runtime_base || !resource_table || (owner & 3) ||
      (runtime_base & 3) || (resource_table & 3) ||
      owner > UINT32_MAX - 16) {
    ++g_semantic_submission_invalid_record_joins;
    return;
  }
  const uint32_t descriptor_base = LoadSemanticGuestU32(memory, owner);
  const uint32_t descriptor_count = LoadSemanticGuestU32(memory, owner + 12);
  if (!descriptor_base || (descriptor_base & 3) || !descriptor_count ||
      descriptor_address < descriptor_base || runtime_address < runtime_base) {
    ++g_semantic_submission_invalid_record_joins;
    return;
  }
  const uint32_t descriptor_delta = descriptor_address - descriptor_base;
  const uint32_t runtime_delta = runtime_address - runtime_base;
  if (descriptor_delta % 92 || runtime_delta % 68) {
    ++g_semantic_submission_invalid_record_joins;
    return;
  }
  const uint32_t record_index = descriptor_delta / 92;
  if (runtime_delta / 68 != record_index || record_index >= descriptor_count) {
    ++g_semantic_submission_invalid_record_joins;
    return;
  }

  const uint32_t primary_resource_index =
      LoadSemanticGuestU32(memory, descriptor_address);
  const int32_t secondary_resource_index = int32_t(
      LoadSemanticGuestU32(memory, descriptor_address + 4));
  const uint32_t descriptor_kind =
      LoadSemanticGuestU32(memory, descriptor_address + 36);
  const uint32_t runtime_submission_object =
      LoadSemanticGuestU32(memory, runtime_address);
  const uint32_t runtime_default_source =
      LoadSemanticGuestU32(memory, runtime_address + 24);
  const uint32_t runtime_count_units =
      LoadSemanticGuestU32(memory, runtime_address + 28);
  const uint32_t runtime_counted_source =
      LoadSemanticGuestU32(memory, runtime_address + 32);
  if (!graphics_context || (graphics_context & 3) ||
      graphics_context > UINT32_MAX - 4) {
    ++g_semantic_submission_invalid_dispatch_targets;
    return;
  }
  const uint32_t graphics_vtable =
      LoadSemanticGuestU32(memory, graphics_context);
  if (!graphics_vtable || (graphics_vtable & 3) ||
      graphics_vtable > UINT32_MAX - 164) {
    ++g_semantic_submission_invalid_dispatch_targets;
    return;
  }
  const uint32_t graphics_submission_method =
      LoadSemanticGuestU32(memory, graphics_vtable + 160);
  if (!graphics_submission_method || (graphics_submission_method & 3)) {
    ++g_semantic_submission_invalid_dispatch_targets;
    return;
  }
  const uint64_t primary_resource_address_64 =
      uint64_t(resource_table) + uint64_t(primary_resource_index) * 8;
  if (primary_resource_address_64 + 4 > uint64_t(UINT32_MAX) + 1) {
    ++g_semantic_submission_invalid_resource_joins;
    return;
  }
  const uint32_t primary_resource_key = LoadSemanticGuestU32(
      memory, uint32_t(primary_resource_address_64));
  if (primary_resource_key != pending.primary_resource_key) {
    ++g_semantic_submission_invalid_resource_joins;
    return;
  }
  if (!pending.primary_resolution_known ||
      !pending.primary_bound_resource_object ||
      !IsResolvedSemanticResourceProviderProvenance(pending.primary_provider)) {
    ++g_semantic_submission_unresolved_resource_joins;
    return;
  }

  uint32_t secondary_resource_key = 0;
  const bool secondary_resource_present = secondary_resource_index >= 0;
  uint64_t payload_bytes = 60;
  if (secondary_resource_present) {
    const uint64_t secondary_resource_address_64 =
        uint64_t(resource_table) + uint64_t(secondary_resource_index) * 8;
    if (secondary_resource_address_64 + 4 > uint64_t(UINT32_MAX) + 1 ||
        !pending.secondary_seen) {
      ++g_semantic_submission_invalid_resource_joins;
      return;
    }
    secondary_resource_key = LoadSemanticGuestU32(
        memory, uint32_t(secondary_resource_address_64));
    payload_bytes += 4;
    if (secondary_resource_key != pending.secondary_resource_key) {
      ++g_semantic_submission_invalid_resource_joins;
      return;
    }
    if (!pending.secondary_resolution_known ||
        !pending.secondary_bound_resource_object ||
        !IsResolvedSemanticResourceProviderProvenance(
            pending.secondary_provider)) {
      ++g_semantic_submission_unresolved_resource_joins;
      return;
    }
  } else if (pending.secondary_seen) {
    ++g_semantic_submission_invalid_resource_joins;
    return;
  }

  const bool counted_runtime_source_matches =
      count_units == runtime_count_units &&
      source_address == runtime_counted_source;
  const bool default_runtime_source =
      count_units == 0 && source_address == runtime_default_source;
  if (!runtime_submission_object || !source_address ||
      (!counted_runtime_source_matches && !default_runtime_source)) {
    ++g_semantic_submission_invalid_geometry;
    return;
  }
  // Prefer the default classification when both zero-count source fields are
  // identical. The submitted tuple is exact even though those equal values do
  // not distinguish which earlier title branch selected it.
  const bool counted_runtime_source =
      counted_runtime_source_matches && !default_runtime_source;

  ++g_semantic_submission_live_observations;
  g_semantic_submission_payload_bytes += payload_bytes;
  ++g_semantic_submission_replay_fallbacks;
  const uint32_t count_bytes = count_units << 2;
  uint64_t key = 0xCBF29CE484222325ull;
  for (uint64_t value :
       {uint64_t(receiver_address), uint64_t(receiver_generation),
        uint64_t(record_index), uint64_t(descriptor_kind),
        uint64_t(helper_state), uint64_t(graphics_vtable),
        uint64_t(graphics_submission_method), uint64_t(primary_resource_key),
        uint64_t(pending.primary_bound_resource_object),
        uint64_t(pending.primary_provider.provider_object),
        uint64_t(pending.primary_provider.provider_vtable),
        uint64_t(pending.primary_provider.predicate_24_method),
        uint64_t(pending.primary_provider.primary_36_method),
        uint64_t(pending.primary_provider.fallback_40_method),
        uint64_t(pending.primary_provider.predicate_44_method),
        uint64_t(pending.primary_provider.selection),
        uint64_t(pending.primary_provider.object_source),
        uint64_t(secondary_resource_present),
        uint64_t(secondary_resource_key),
        uint64_t(pending.secondary_bound_resource_object),
        uint64_t(pending.secondary_provider.provider_object),
        uint64_t(pending.secondary_provider.provider_vtable),
        uint64_t(pending.secondary_provider.predicate_24_method),
        uint64_t(pending.secondary_provider.primary_36_method),
        uint64_t(pending.secondary_provider.fallback_40_method),
        uint64_t(pending.secondary_provider.predicate_44_method),
        uint64_t(pending.secondary_provider.selection),
        uint64_t(pending.secondary_provider.object_source),
        uint64_t(runtime_submission_object), uint64_t(count_bytes),
        uint64_t(source_address)}) {
    key = HashCombine(key, value);
  }
  key = key ? key : 1;
  JoinProceduralModelSemanticDraw(
      key, receiver_address, receiver_generation, record_index,
      descriptor_address, runtime_address, descriptor_kind, helper_state,
      primary_resource_key, secondary_resource_key,
      secondary_resource_present);

  size_t index = size_t(key % kSemanticSubmissionCapacity);
  for (size_t probe = 0; probe < kSemanticSubmissionCapacity; ++probe) {
    SemanticSubmissionEntry &entry = g_semantic_submissions[index];
    if (!entry.key) {
      entry = {
          .key = key,
          .calls = 1,
          .first_frame = g_frame_sequence.load(std::memory_order_relaxed),
          .last_frame = g_frame_sequence.load(std::memory_order_relaxed),
          .receiver_address = receiver_address,
          .receiver_generation = receiver_generation,
          .record_index = record_index,
          .descriptor_kind = descriptor_kind,
          .helper_state = helper_state,
          .graphics_context = graphics_context,
          .graphics_vtable = graphics_vtable,
          .graphics_submission_method = graphics_submission_method,
          .resource_lookup_context = resource_lookup_context,
          .primary_resource_index = primary_resource_index,
          .primary_resource_key = primary_resource_key,
          .primary_bound_resource_object =
              pending.primary_bound_resource_object,
          .primary_resource_provider_object =
              pending.primary_provider.provider_object,
          .primary_resource_provider_vtable =
              pending.primary_provider.provider_vtable,
          .primary_resource_predicate_24_method =
              pending.primary_provider.predicate_24_method,
          .primary_resource_primary_36_method =
              pending.primary_provider.primary_36_method,
          .primary_resource_fallback_40_method =
              pending.primary_provider.fallback_40_method,
          .primary_resource_predicate_44_method =
              pending.primary_provider.predicate_44_method,
          .primary_resource_provider_selection =
              uint32_t(pending.primary_provider.selection),
          .primary_resource_object_source =
              uint32_t(pending.primary_provider.object_source),
          .secondary_resource_index = secondary_resource_index,
          .secondary_resource_key = secondary_resource_key,
          .secondary_bound_resource_object =
              pending.secondary_bound_resource_object,
          .secondary_resource_provider_object =
              pending.secondary_provider.provider_object,
          .secondary_resource_provider_vtable =
              pending.secondary_provider.provider_vtable,
          .secondary_resource_predicate_24_method =
              pending.secondary_provider.predicate_24_method,
          .secondary_resource_primary_36_method =
              pending.secondary_provider.primary_36_method,
          .secondary_resource_fallback_40_method =
              pending.secondary_provider.fallback_40_method,
          .secondary_resource_predicate_44_method =
              pending.secondary_provider.predicate_44_method,
          .secondary_resource_provider_selection =
              uint32_t(pending.secondary_provider.selection),
          .secondary_resource_object_source =
              uint32_t(pending.secondary_provider.object_source),
          .runtime_submission_object = runtime_submission_object,
          .primitive_type = 13,
          .count_units = count_units,
          .count_bytes = count_bytes,
          .source_address = source_address,
          .secondary_resource_present = secondary_resource_present,
          .counted_runtime_source = counted_runtime_source,
      };
      ++g_semantic_submission_count;
      return;
    }
    if (entry.key == key && entry.receiver_address == receiver_address &&
        entry.receiver_generation == receiver_generation &&
        entry.record_index == record_index &&
        entry.descriptor_kind == descriptor_kind &&
        entry.helper_state == helper_state &&
        entry.graphics_context == graphics_context &&
        entry.graphics_vtable == graphics_vtable &&
        entry.graphics_submission_method == graphics_submission_method &&
        entry.resource_lookup_context == resource_lookup_context &&
        entry.primary_resource_index == primary_resource_index &&
        entry.primary_resource_key == primary_resource_key &&
        entry.primary_bound_resource_object ==
            pending.primary_bound_resource_object &&
        entry.primary_resource_provider_object ==
            pending.primary_provider.provider_object &&
        entry.primary_resource_provider_vtable ==
            pending.primary_provider.provider_vtable &&
        entry.primary_resource_predicate_24_method ==
            pending.primary_provider.predicate_24_method &&
        entry.primary_resource_primary_36_method ==
            pending.primary_provider.primary_36_method &&
        entry.primary_resource_fallback_40_method ==
            pending.primary_provider.fallback_40_method &&
        entry.primary_resource_predicate_44_method ==
            pending.primary_provider.predicate_44_method &&
        entry.primary_resource_provider_selection ==
            uint32_t(pending.primary_provider.selection) &&
        entry.primary_resource_object_source ==
            uint32_t(pending.primary_provider.object_source) &&
        entry.secondary_resource_present == secondary_resource_present &&
        entry.secondary_resource_index == secondary_resource_index &&
        entry.secondary_resource_key == secondary_resource_key &&
        entry.secondary_bound_resource_object ==
            pending.secondary_bound_resource_object &&
        entry.secondary_resource_provider_object ==
            pending.secondary_provider.provider_object &&
        entry.secondary_resource_provider_vtable ==
            pending.secondary_provider.provider_vtable &&
        entry.secondary_resource_predicate_24_method ==
            pending.secondary_provider.predicate_24_method &&
        entry.secondary_resource_primary_36_method ==
            pending.secondary_provider.primary_36_method &&
        entry.secondary_resource_fallback_40_method ==
            pending.secondary_provider.fallback_40_method &&
        entry.secondary_resource_predicate_44_method ==
            pending.secondary_provider.predicate_44_method &&
        entry.secondary_resource_provider_selection ==
            uint32_t(pending.secondary_provider.selection) &&
        entry.secondary_resource_object_source ==
            uint32_t(pending.secondary_provider.object_source) &&
        entry.runtime_submission_object == runtime_submission_object &&
        entry.count_units == count_units &&
        entry.count_bytes == count_bytes &&
        entry.source_address == source_address &&
        entry.counted_runtime_source == counted_runtime_source) {
      ++entry.calls;
      entry.last_frame = g_frame_sequence.load(std::memory_order_relaxed);
      return;
    }
    index = (index + 1) % kSemanticSubmissionCapacity;
  }
  ++g_semantic_submission_overflow;
}

void EmitProceduralModelSemanticSubmissions() {
  std::scoped_lock lock(g_semantic_submission_mutex);
  for (const SemanticSubmissionEntry &entry : g_semantic_submissions) {
    if (!entry.key) {
      continue;
    }
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.discovery.semantic_submission_entry",
        {{"class", "proceduralGeometry::CProceduralModels"},
         {"key", fmt::format("{:016X}", entry.key)},
         {"calls", std::to_string(entry.calls)},
         {"first_frame", std::to_string(entry.first_frame)},
         {"last_frame", std::to_string(entry.last_frame)},
         {"receiver_address", fmt::format("{:08X}", entry.receiver_address)},
         {"receiver_generation", std::to_string(entry.receiver_generation)},
         {"record_index", std::to_string(entry.record_index)},
         {"descriptor_kind", std::to_string(entry.descriptor_kind)},
         {"helper_state", std::to_string(entry.helper_state)},
         {"graphics_context", fmt::format("{:08X}", entry.graphics_context)},
         {"graphics_vtable", fmt::format("{:08X}", entry.graphics_vtable)},
         {"graphics_submission_vtable_offset", "160"},
         {"graphics_submission_method",
          fmt::format("{:08X}", entry.graphics_submission_method)},
         {"resource_lookup_context",
          fmt::format("{:08X}", entry.resource_lookup_context)},
         {"primary_resource_index",
          std::to_string(entry.primary_resource_index)},
         {"primary_resource_key",
          fmt::format("{:08X}", entry.primary_resource_key)},
         {"primary_bound_resource_object",
          fmt::format("{:08X}", entry.primary_bound_resource_object)},
         {"primary_resource_provider_object",
          fmt::format("{:08X}", entry.primary_resource_provider_object)},
         {"primary_resource_provider_vtable",
          fmt::format("{:08X}", entry.primary_resource_provider_vtable)},
         {"primary_resource_predicate_24_method",
          fmt::format("{:08X}", entry.primary_resource_predicate_24_method)},
         {"primary_resource_primary_36_method",
          fmt::format("{:08X}", entry.primary_resource_primary_36_method)},
         {"primary_resource_fallback_40_method",
          fmt::format("{:08X}", entry.primary_resource_fallback_40_method)},
         {"primary_resource_predicate_44_method",
          fmt::format("{:08X}", entry.primary_resource_predicate_44_method)},
         {"primary_resource_provider_selection",
          SemanticResourceProviderSelectionName(
              SemanticResourceProviderSelection(
                  entry.primary_resource_provider_selection))},
         {"primary_resource_object_source",
          SemanticResourceObjectSourceName(SemanticResourceObjectSource(
              entry.primary_resource_object_source))},
         {"secondary_resource_present",
          entry.secondary_resource_present ? "true" : "false"},
         {"secondary_resource_index",
          std::to_string(entry.secondary_resource_index)},
         {"secondary_resource_key",
          fmt::format("{:08X}", entry.secondary_resource_key)},
         {"secondary_bound_resource_object",
          fmt::format("{:08X}", entry.secondary_bound_resource_object)},
         {"secondary_resource_provider_object",
          fmt::format("{:08X}", entry.secondary_resource_provider_object)},
         {"secondary_resource_provider_vtable",
          fmt::format("{:08X}", entry.secondary_resource_provider_vtable)},
         {"secondary_resource_predicate_24_method",
          fmt::format("{:08X}", entry.secondary_resource_predicate_24_method)},
         {"secondary_resource_primary_36_method",
          fmt::format("{:08X}", entry.secondary_resource_primary_36_method)},
         {"secondary_resource_fallback_40_method",
          fmt::format("{:08X}", entry.secondary_resource_fallback_40_method)},
         {"secondary_resource_predicate_44_method",
          fmt::format("{:08X}", entry.secondary_resource_predicate_44_method)},
         {"secondary_resource_provider_selection",
          SemanticResourceProviderSelectionName(
              SemanticResourceProviderSelection(
                  entry.secondary_resource_provider_selection))},
         {"secondary_resource_object_source",
          SemanticResourceObjectSourceName(SemanticResourceObjectSource(
              entry.secondary_resource_object_source))},
         {"runtime_submission_object",
          fmt::format("{:08X}", entry.runtime_submission_object)},
         {"primitive_type", std::to_string(entry.primitive_type)},
         {"count_units", std::to_string(entry.count_units)},
         {"count_bytes", std::to_string(entry.count_bytes)},
         {"source_address", fmt::format("{:08X}", entry.source_address)},
         {"source_contract", entry.counted_runtime_source
                                 ? "runtime_record_28_32"
                                 : "runtime_record_24_default"},
         {"descriptor_kind_group",
          ProceduralModelDescriptorKindGroup(entry.descriptor_kind)},
         {"helper_state_family",
          ProceduralModelHelperStateFamily(entry.helper_state)},
         {"classification",
          "resolved_resource_state_variant_and_dispatch_submission"},
         {"fallback", "xenos_replay"},
         {"guest_payload_read",
          "bounded_submission_and_dispatch_fields_only"},
         {"guest_state_changed", "false"},
         {"native_upload", "false"},
         {"native_draw", "false"},
         {"xenos_authority", "true"},
         {"suppression_allowed", "false"}});
  }
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.discovery.semantic_submission_summary",
      {{"observations", std::to_string(g_semantic_submission_observations)},
       {"live_observations",
        std::to_string(g_semantic_submission_live_observations)},
       {"unknown_receivers",
        std::to_string(g_semantic_submission_unknown_receivers)},
       {"binding_mismatches",
        std::to_string(g_semantic_submission_binding_mismatches)},
       {"invalid_record_joins",
        std::to_string(g_semantic_submission_invalid_record_joins)},
       {"invalid_resource_joins",
        std::to_string(g_semantic_submission_invalid_resource_joins)},
       {"unresolved_resource_joins",
        std::to_string(g_semantic_submission_unresolved_resource_joins)},
       {"invalid_geometry",
        std::to_string(g_semantic_submission_invalid_geometry)},
       {"invalid_dispatch_targets",
        std::to_string(g_semantic_submission_invalid_dispatch_targets)},
       {"primary_binding_observations",
        std::to_string(g_semantic_primary_binding_observations)},
       {"secondary_binding_observations",
        std::to_string(g_semantic_secondary_binding_observations)},
       {"resource_resolution_attempts",
        std::to_string(g_semantic_resource_resolution_attempts)},
       {"resource_resolution_successes",
        std::to_string(g_semantic_resource_resolution_successes)},
       {"resource_resolution_misses",
        std::to_string(g_semantic_resource_resolution_misses)},
       {"resource_resolution_cache_hits",
        std::to_string(g_semantic_resource_resolution_cache_hits)},
       {"resource_binding_key_cache_hits",
        std::to_string(g_semantic_resource_resolution_cache_hits)},
       {"resource_bind_dispatches",
        std::to_string(g_semantic_resource_bind_dispatches)},
       {"resource_resolution_protocol_faults",
        std::to_string(g_semantic_resource_resolution_protocol_faults)},
       {"provider_lookup_observations",
        std::to_string(g_semantic_provider_lookup_observations)},
       {"provider_cache_hits", std::to_string(g_semantic_provider_cache_hits)},
       {"provider_lookup_misses",
        std::to_string(g_semantic_provider_lookup_misses)},
       {"provider_primary_selections",
        std::to_string(g_semantic_provider_primary_selections)},
       {"provider_fallback_selections",
        std::to_string(g_semantic_provider_fallback_selections)},
       {"provider_unavailable_selections",
        std::to_string(g_semantic_provider_unavailable_selections)},
       {"provider_method_results",
        std::to_string(g_semantic_provider_method_results)},
       {"provider_method_null_results",
        std::to_string(g_semantic_provider_method_null_results)},
       {"secondary_resolution_attempts",
        std::to_string(g_semantic_secondary_resolution_attempts)},
       {"secondary_resolution_successes",
        std::to_string(g_semantic_secondary_resolution_successes)},
       {"secondary_resolution_misses",
        std::to_string(g_semantic_secondary_resolution_misses)},
       {"provider_metadata_bytes",
        std::to_string(g_semantic_provider_metadata_bytes)},
       {"provider_metadata_bytes_per_lookup", "20"},
       {"payload_bytes",
        std::to_string(g_semantic_submission_payload_bytes)},
       {"maximum_payload_bytes_per_live_observation",
        std::to_string(kSemanticSubmissionMaximumPayloadBytes)},
       {"replay_fallbacks",
        std::to_string(g_semantic_submission_replay_fallbacks)},
       {"native_admissions",
        std::to_string(g_semantic_submission_native_admissions)},
       {"entries", std::to_string(g_semantic_submission_count)},
       {"capacity", std::to_string(kSemanticSubmissionCapacity)},
       {"overflow", std::to_string(g_semantic_submission_overflow)},
       {"classification",
        "resolved_resource_state_variant_and_dispatch_submission"},
       {"fallback", "xenos_replay"},
       {"guest_payload_read",
        "bounded_submission_and_dispatch_fields_only"},
       {"guest_state_changed", "false"},
       {"native_upload", "false"},
       {"native_draw", "false"},
       {"xenos_authority", "true"},
       {"suppression_allowed", "false"}});
}

uint64_t PreparedPipelineHash(
    const rex::system::GraphicsPreparedDrawObservation &prepared) {
  uint64_t hash = 0xCBF29CE484222325ull;
  for (uint64_t value :
       {uint64_t(prepared.guest_primitive_type),
        uint64_t(prepared.host_primitive_type),
        uint64_t(prepared.host_vertex_shader_type),
        uint64_t(prepared.tessellation_mode),
        uint64_t(prepared.index_buffer_type),
        uint64_t(prepared.host_index_format),
        uint64_t(prepared.host_primitive_reset_enabled),
        uint64_t(prepared.normalized_depth_control),
        uint64_t(prepared.normalized_color_mask),
        uint64_t(prepared.bound_render_target_bits), uint64_t(prepared.flags)}) {
    hash = HashCombine(hash, value);
  }
  for (uint32_t format : prepared.bound_render_target_formats) {
    hash = HashCombine(hash, format);
  }
  return hash ? hash : 1;
}

uint64_t HashBytes(const uint8_t *data, uint64_t length) {
  uint64_t hash = 0xCBF29CE484222325ull;
  for (uint64_t i = 0; i < length; ++i) {
    hash ^= data[i];
    hash *= 0x100000001B3ull;
  }
  return hash;
}

void TryFingerprintCandidateTextures(
    const rex::system::GraphicsDrawObservation &observation,
    uint64_t signature) {
  if (!g_texture_scan.requested || !g_texture_scan.valid ||
      g_texture_scan.completed ||
      signature != g_texture_scan.target_signature) {
    return;
  }
  g_texture_scan.completed = true;

  const auto reject = [&](const char *reason) {
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.census.texture_scan",
        {{"signature", fmt::format("{:016X}", signature)},
         {"status", "rejected"},
         {"reason", reason},
         {"frame", std::to_string(observation.frame_sequence)},
         {"draw", std::to_string(observation.draw_sequence)},
         {"guest_payload_read", "false"},
         {"native_upload", "false"},
         {"native_draw", "false"},
         {"suppression_eligible", "false"}});
  };

  const uint32_t resource_count = std::popcount(observation.texture_fetch_mask);
  if (!resource_count || resource_count > kMaximumTextureScanResources ||
      observation.texture_state_overflow) {
    reject("texture_resource_count_out_of_bounds");
    return;
  }
  if ((observation.texture_fetch_layout_valid_mask &
       observation.texture_fetch_mask) != observation.texture_fetch_mask) {
    reject("texture_layout_unavailable");
    return;
  }

  uint64_t total_bytes = 0;
  for (uint32_t fetch = 0; fetch < 32; ++fetch) {
    if (!(observation.texture_fetch_mask & (uint32_t(1) << fetch))) {
      continue;
    }
    const uint64_t base_address =
        pinyon_shift::native_renderer::CanonicalPhysicalAddress(
            observation.texture_fetch_addresses[fetch]);
    const uint64_t base_length = observation.texture_fetch_base_lengths[fetch];
    const uint64_t mip_address =
        pinyon_shift::native_renderer::CanonicalPhysicalAddress(
            observation.texture_fetch_mip_addresses[fetch]);
    const uint64_t mip_length = observation.texture_fetch_mip_lengths[fetch];
    if (!base_length || base_length > kMaximumTextureScanResourceBytes ||
        mip_length > kMaximumTextureScanResourceBytes ||
        base_address + base_length > kPhysicalApertureSize ||
        (mip_length && (!mip_address ||
                        mip_address + mip_length > kPhysicalApertureSize))) {
      reject("texture_allocation_out_of_bounds");
      return;
    }
    total_bytes += base_length + mip_length;
    if (total_bytes > kMaximumTextureScanTotalBytes) {
      reject("texture_scan_total_out_of_bounds");
      return;
    }
  }

  auto *kernel_state = rex::system::kernel_state();
  if (!kernel_state || !kernel_state->memory()) {
    reject("guest_memory_unavailable");
    return;
  }

  uint32_t resource = 0;
  for (uint32_t fetch = 0; fetch < 32; ++fetch) {
    if (!(observation.texture_fetch_mask & (uint32_t(1) << fetch))) {
      continue;
    }
    const uint32_t base_address = observation.texture_fetch_addresses[fetch];
    const uint32_t base_length =
        observation.texture_fetch_base_lengths[fetch];
    const uint32_t mip_address =
        observation.texture_fetch_mip_addresses[fetch];
    const uint32_t mip_length = observation.texture_fetch_mip_lengths[fetch];
    const uint8_t *base =
        kernel_state->memory()->TranslatePhysical<const uint8_t *>(base_address);
    const uint64_t base_hash = HashBytes(base, base_length);
    uint64_t mip_hash = 0;
    if (mip_length) {
      const uint8_t *mip =
          kernel_state->memory()->TranslatePhysical<const uint8_t *>(mip_address);
      mip_hash = HashBytes(mip, mip_length);
    }
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.census.texture_fingerprint",
        {{"signature", fmt::format("{:016X}", signature)},
         {"resource", std::to_string(resource++)},
         {"fetch_constant", std::to_string(fetch)},
         {"base_address", fmt::format("{:08X}", base_address)},
         {"base_bytes", std::to_string(base_length)},
         {"base_hash", fmt::format("{:016X}", base_hash)},
         {"mip_address", fmt::format("{:08X}", mip_address)},
         {"mip_bytes", std::to_string(mip_length)},
         {"mip_hash", mip_length ? fmt::format("{:016X}", mip_hash) : ""},
         {"guest_payload_read", "bounded_texture_only"},
         {"native_upload", "false"},
         {"native_draw", "false"},
         {"suppression_eligible", "false"}});
  }
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.census.texture_scan",
      {{"signature", fmt::format("{:016X}", signature)},
       {"status", "scanned"},
       {"frame", std::to_string(observation.frame_sequence)},
       {"draw", std::to_string(observation.draw_sequence)},
       {"resources", std::to_string(resource_count)},
       {"bytes_read", std::to_string(total_bytes)},
       {"guest_payload_read", "bounded_texture_only"},
       {"native_upload", "false"},
       {"native_draw", "false"},
       {"suppression_eligible", "false"}});
}

void TryScanCandidateIndices(
    const rex::system::GraphicsDrawObservation &observation,
    uint64_t signature) {
  if (!g_index_scan.requested || !g_index_scan.valid ||
      g_index_scan.completed || signature != g_index_scan.target_signature) {
    return;
  }
  g_index_scan.completed = true;

  const auto reject = [&](const char *reason) {
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.census.index_scan",
        {{"signature", fmt::format("{:016X}", signature)},
         {"status", "rejected"},
         {"reason", reason},
         {"frame", std::to_string(observation.frame_sequence)},
         {"draw", std::to_string(observation.draw_sequence)},
         {"guest_payload_read", "false"},
         {"native_upload", "false"},
         {"native_draw", "false"},
         {"suppression_eligible", "false"}});
  };

  if (!observation.indexed ||
      observation.source_select !=
          uint32_t(rex::graphics::xenos::SourceSelect::kDMA)) {
    reject("not_dma_indexed");
    return;
  }
  if (observation.index_format > 1 || observation.index_endianness > 3) {
    reject("unsupported_index_state");
    return;
  }
  if (!observation.index_count ||
      observation.index_count > kMaximumIndexScanCount) {
    reject("index_count_out_of_bounds");
    return;
  }
  if (observation.vertex_index_min > observation.vertex_index_max) {
    reject("invalid_vertex_index_clamp");
    return;
  }
  if (observation.vertex_binding_count != 1 ||
      observation.vertex_binding_overflow) {
    reject("unsupported_vertex_bindings");
    return;
  }

  const uint32_t element_bytes = observation.index_format ? 4 : 2;
  const uint64_t required_bytes =
      uint64_t(observation.index_count) * element_bytes;
  const uint64_t physical_address =
      uint64_t(pinyon_shift::native_renderer::CanonicalPhysicalAddress(
          observation.index_buffer_address));
  if (required_bytes > kMaximumIndexScanBytes ||
      required_bytes > observation.index_buffer_length) {
    reject("index_allocation_too_small");
    return;
  }
  if (physical_address + required_bytes > kPhysicalApertureSize) {
    reject("index_range_crosses_aperture");
    return;
  }
  auto *kernel_state = rex::system::kernel_state();
  if (!kernel_state || !kernel_state->memory()) {
    reject("guest_memory_unavailable");
    return;
  }

  const uint8_t *payload =
      kernel_state->memory()->TranslatePhysical<const uint8_t *>(
          observation.index_buffer_address);
  auto endianness =
      static_cast<rex::graphics::xenos::Endian>(observation.index_endianness);
  if (!observation.index_format) {
    if (endianness == rex::graphics::xenos::Endian::k8in32) {
      endianness = rex::graphics::xenos::Endian::k8in16;
    } else if (endianness == rex::graphics::xenos::Endian::k16in32) {
      endianness = rex::graphics::xenos::Endian::kNone;
    }
  }

  uint32_t decoded_minimum = std::numeric_limits<uint32_t>::max();
  uint32_t decoded_maximum = 0;
  uint32_t effective_minimum = std::numeric_limits<uint32_t>::max();
  uint32_t effective_maximum = 0;
  uint32_t non_reset_count = 0;
  uint32_t reset_count = 0;
  uint64_t decoded_hash = 0xCBF29CE484222325ull;
  for (uint32_t i = 0; i < observation.index_count; ++i) {
    uint32_t decoded = 0;
    if (observation.index_format) {
      std::memcpy(&decoded, payload + uint64_t(i) * element_bytes,
                  sizeof(decoded));
      decoded = rex::graphics::xenos::GpuSwap(decoded, endianness);
    } else {
      uint16_t decoded16 = 0;
      std::memcpy(&decoded16, payload + uint64_t(i) * element_bytes,
                  sizeof(decoded16));
      decoded = rex::graphics::xenos::GpuSwap(decoded16, endianness);
    }
    decoded &= kVertexIndexMask;
    decoded_hash = HashCombine(decoded_hash, decoded);
    if (observation.index_reset_enabled &&
        decoded == (observation.index_reset & kVertexIndexMask)) {
      ++reset_count;
      continue;
    }
    decoded_minimum = std::min(decoded_minimum, decoded);
    decoded_maximum = std::max(decoded_maximum, decoded);
    const uint32_t adjusted =
        (decoded + observation.vertex_index_offset) & kVertexIndexMask;
    const uint32_t effective = std::clamp(
        adjusted, observation.vertex_index_min, observation.vertex_index_max);
    effective_minimum = std::min(effective_minimum, effective);
    effective_maximum = std::max(effective_maximum, effective);
    ++non_reset_count;
  }
  if (!non_reset_count) {
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.census.index_scan",
        {{"signature", fmt::format("{:016X}", signature)},
         {"status", "empty_after_reset"},
         {"frame", std::to_string(observation.frame_sequence)},
         {"draw", std::to_string(observation.draw_sequence)},
         {"index_count", std::to_string(observation.index_count)},
         {"bytes_read", std::to_string(required_bytes)},
         {"reset_count", std::to_string(reset_count)},
         {"guest_payload_read", "bounded_index_only"},
         {"native_upload", "false"},
         {"native_draw", "false"},
         {"suppression_eligible", "false"}});
    return;
  }

  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.census.index_scan",
      {{"signature", fmt::format("{:016X}", signature)},
       {"status", "scanned"},
       {"frame", std::to_string(observation.frame_sequence)},
       {"draw", std::to_string(observation.draw_sequence)},
       {"index_count", std::to_string(observation.index_count)},
       {"bytes_read", std::to_string(required_bytes)},
       {"index_buffer_address",
        fmt::format("{:08X}", observation.index_buffer_address)},
       {"index_buffer_length", std::to_string(observation.index_buffer_length)},
       {"index_format", std::to_string(observation.index_format)},
       {"index_endianness", std::to_string(observation.index_endianness)},
       {"index_reset_enabled",
        observation.index_reset_enabled ? "true" : "false"},
       {"index_reset", fmt::format("{:08X}", observation.index_reset)},
       {"decoded_minimum", std::to_string(decoded_minimum)},
       {"decoded_maximum", std::to_string(decoded_maximum)},
       {"effective_minimum", std::to_string(effective_minimum)},
       {"effective_maximum", std::to_string(effective_maximum)},
       {"non_reset_count", std::to_string(non_reset_count)},
       {"reset_count", std::to_string(reset_count)},
       {"decoded_hash", fmt::format("{:016X}", decoded_hash)},
       {"vertex_binding_address",
        fmt::format("{:08X}", observation.vertex_bindings[0].address)},
       {"vertex_binding_size",
        std::to_string(observation.vertex_bindings[0].size)},
       {"guest_payload_read", "bounded_index_only"},
       {"native_upload", "false"},
       {"native_draw", "false"},
       {"suppression_eligible", "false"}});
}

bool WriteSnapshotFile(const std::filesystem::path &path,
                       std::span<const uint8_t> bytes) {
  std::ofstream output(path, std::ios::binary | std::ios::trunc);
  return output.write(reinterpret_cast<const char *>(bytes.data()),
                      static_cast<std::streamsize>(bytes.size())) &&
         output.flush();
}

void AppendFloatConstants(
    std::string &document, const char *name,
    const rex::system::GraphicsFloatConstantObservation *constants,
    uint32_t count) {
  document += fmt::format("    \"{}\": [", name);
  const uint32_t bounded_count = std::min(
      count, rex::system::kGraphicsFloatConstantObservationLimit);
  for (uint32_t i = 0; i < bounded_count; ++i) {
    if (i) {
      document += ",";
    }
    document += fmt::format(
        "\n      {{\"index\":{},\"words\":[\"{:08X}\",\"{:08X}\","
        "\"{:08X}\",\"{:08X}\"]}}",
        constants[i].index, constants[i].values[0], constants[i].values[1],
        constants[i].values[2], constants[i].values[3]);
  }
  document += bounded_count ? "\n    ]" : "]";
}

struct SnapshotTexturePayload {
  uint32_t fetch_constant = 0;
  uint32_t base_address = 0;
  uint32_t mip_address = 0;
  std::vector<uint8_t> base;
  std::vector<uint8_t> mip;
};

void TryCaptureReplaySnapshot(
    const rex::system::GraphicsDrawObservation &observation,
    bool samples_resolved_target,
    const rex::system::GraphicsPreparedDrawObservation &prepared,
    uint64_t signature) {
  if (!g_replay_snapshot.requested || !g_replay_snapshot.valid ||
      g_replay_snapshot.completed ||
      signature != g_replay_snapshot.target_signature) {
    return;
  }
  g_replay_snapshot.completed = true;

  const auto reject = [&](const char *reason) {
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.snapshot.capture",
        {{"signature", fmt::format("{:016X}", signature)},
         {"status", "rejected"},
         {"reason", reason},
         {"frame", std::to_string(observation.frame_sequence)},
         {"draw", std::to_string(observation.draw_sequence)},
         {"guest_payload_read", "false"},
         {"payload_persisted", "false"},
         {"native_upload", "false"},
         {"native_draw", "false"},
         {"suppression_eligible", "false"}});
  };

  if (samples_resolved_target) {
    reject("observed_resolve_dependency");
    return;
  }
  if (!observation.indexed ||
      observation.source_select !=
          uint32_t(rex::graphics::xenos::SourceSelect::kDMA) ||
      observation.index_format > 1 || observation.index_endianness > 3 ||
      !observation.index_count ||
      observation.index_count > kMaximumIndexScanCount) {
    reject("unsupported_index_state");
    return;
  }
  if (observation.vertex_binding_count != 1 ||
      observation.vertex_binding_overflow ||
      observation.vertex_attribute_overflow ||
      observation.vertex_float_constant_overflow ||
      observation.pixel_float_constant_overflow ||
      observation.texture_state_overflow || observation.vertex_memexport ||
      observation.viz_query_condition || (observation.pa_sc_viz_query & 1)) {
    reject("unsupported_draw_state");
    return;
  }
  if ((prepared.flags & 3) != 3 ||
      !(prepared.bound_render_target_bits & 2)) {
    reject("inactive_prepared_pipeline");
    return;
  }

  const uint32_t index_element_bytes = observation.index_format ? 4 : 2;
  const uint64_t index_bytes =
      uint64_t(observation.index_count) * index_element_bytes;
  const auto &binding = observation.vertex_bindings[0];
  const uint64_t vertex_bytes = binding.size;
  constexpr uint64_t kMaximumVertexSnapshotBytes = UINT64_C(64) << 20;
  const uint64_t index_address =
      uint64_t(pinyon_shift::native_renderer::CanonicalPhysicalAddress(
          observation.index_buffer_address));
  const uint64_t vertex_address =
      pinyon_shift::native_renderer::CanonicalPhysicalAddress(binding.address);
  if (!vertex_bytes || index_bytes > kMaximumIndexScanBytes ||
      index_bytes > observation.index_buffer_length ||
      vertex_bytes > kMaximumVertexSnapshotBytes ||
      index_address + index_bytes > kPhysicalApertureSize ||
      vertex_address + vertex_bytes > kPhysicalApertureSize) {
    reject("geometry_range_out_of_bounds");
    return;
  }

  const uint32_t texture_count = std::popcount(observation.texture_fetch_mask);
  if (!texture_count || texture_count > kMaximumTextureScanResources ||
      (observation.texture_fetch_layout_valid_mask &
       observation.texture_fetch_mask) != observation.texture_fetch_mask) {
    reject("texture_layout_unavailable");
    return;
  }
  uint64_t texture_bytes = 0;
  for (uint32_t fetch = 0; fetch < 32; ++fetch) {
    if (!(observation.texture_fetch_mask & (uint32_t(1) << fetch))) {
      continue;
    }
    const uint64_t base_bytes =
        observation.texture_fetch_base_lengths[fetch];
    const uint64_t mip_bytes = observation.texture_fetch_mip_lengths[fetch];
    const uint64_t base_address =
        pinyon_shift::native_renderer::CanonicalPhysicalAddress(
            observation.texture_fetch_addresses[fetch]);
    const uint64_t mip_address =
        pinyon_shift::native_renderer::CanonicalPhysicalAddress(
            observation.texture_fetch_mip_addresses[fetch]);
    if (!base_bytes || base_bytes > kMaximumTextureScanResourceBytes ||
        mip_bytes > kMaximumTextureScanResourceBytes ||
        base_address + base_bytes > kPhysicalApertureSize ||
        (mip_bytes && mip_address + mip_bytes > kPhysicalApertureSize) ||
        base_bytes + mip_bytes >
            kMaximumTextureScanTotalBytes - texture_bytes) {
      reject("texture_range_out_of_bounds");
      return;
    }
    texture_bytes += base_bytes + mip_bytes;
  }

  auto *kernel_state = rex::system::kernel_state();
  if (!kernel_state || !kernel_state->memory()) {
    reject("guest_memory_unavailable");
    return;
  }
  auto *memory = kernel_state->memory();
  const auto copy_physical = [&](uint32_t address, uint64_t size) {
    std::vector<uint8_t> result(size);
    const uint8_t *source =
        memory->TranslatePhysical<const uint8_t *>(address);
    std::memcpy(result.data(), source, size);
    return result;
  };

  std::vector<uint8_t> index_payload =
      copy_physical(observation.index_buffer_address, index_bytes);
  std::vector<uint8_t> vertex_payload =
      copy_physical(binding.address, vertex_bytes);
  std::vector<SnapshotTexturePayload> textures;
  textures.reserve(texture_count);
  for (uint32_t fetch = 0; fetch < 32; ++fetch) {
    if (!(observation.texture_fetch_mask & (uint32_t(1) << fetch))) {
      continue;
    }
    SnapshotTexturePayload texture;
    texture.fetch_constant = fetch;
    texture.base_address = observation.texture_fetch_addresses[fetch];
    texture.mip_address = observation.texture_fetch_mip_addresses[fetch];
    texture.base = copy_physical(
        texture.base_address, observation.texture_fetch_base_lengths[fetch]);
    if (observation.texture_fetch_mip_lengths[fetch]) {
      texture.mip = copy_physical(
          texture.mip_address, observation.texture_fetch_mip_lengths[fetch]);
    }
    textures.push_back(std::move(texture));
  }

  std::filesystem::path staging = g_replay_snapshot.output_root;
  staging += L".partial";
  std::error_code error;
  if (std::filesystem::exists(g_replay_snapshot.output_root, error) || error ||
      std::filesystem::exists(staging, error) || error ||
      !std::filesystem::create_directories(staging, error) || error) {
    reject("output_directory_unavailable");
    return;
  }

  const auto write_payload = [&](const std::filesystem::path &name,
                                 std::span<const uint8_t> payload) {
    return WriteSnapshotFile(staging / name, payload);
  };
  if (!write_payload(L"index.bin", index_payload) ||
      !write_payload(L"vertex.bin", vertex_payload)) {
    reject("geometry_write_failed");
    return;
  }
  for (const auto &texture : textures) {
    const auto base_name =
        std::filesystem::path(fmt::format("texture_{:02}_base.bin",
                                         texture.fetch_constant));
    if (!write_payload(base_name, texture.base)) {
      reject("texture_write_failed");
      return;
    }
    if (!texture.mip.empty()) {
      const auto mip_name =
          std::filesystem::path(fmt::format("texture_{:02}_mip.bin",
                                           texture.fetch_constant));
      if (!write_payload(mip_name, texture.mip)) {
        reject("texture_write_failed");
        return;
      }
    }
  }

  std::string document = fmt::format(
      "{{\n  \"schema\": \"pinyon-shift.native-replay-snapshot.v1\",\n"
      "  \"candidate_signature\": \"{:016X}\",\n"
      "  \"frame\": {},\n  \"draw\": {},\n"
      "  \"shaders\": {{\"vertex\":\"{:016X}\",\"pixel\":\"{:016X}\","
      "\"vertex_specialization\":\"{:016X}\","
      "\"pixel_specialization\":\"{:016X}\"}},\n"
      "  \"prepared_pipeline_hash\": \"{:016X}\",\n"
      "  \"prepared_pipeline\": {{\"guest_primitive\":{},"
      "\"host_primitive\":{},\"host_vertex_shader_type\":{},"
      "\"tessellation_mode\":{},\"index_buffer_type\":{},"
      "\"host_index_format\":{},\"host_primitive_reset\":{},"
      "\"depth_control\":\"{:08X}\",\"color_mask\":\"{:08X}\","
      "\"target_bits\":\"{:08X}\","
      "\"target_formats\":[{},{},{},{},{}],\"flags\":\"{:08X}\"}},\n"
      "  \"geometry\": {{\n"
      "    \"index\": {{\"file\":\"index.bin\",\"bytes\":{},"
      "\"hash\":\"{:016X}\",\"address\":\"{:08X}\","
      "\"format\":{},\"endianness\":{},\"count\":{}}},\n"
      "    \"vertex\": {{\"file\":\"vertex.bin\",\"bytes\":{},"
      "\"hash\":\"{:016X}\",\"address\":\"{:08X}\","
      "\"fetch_constant\":{},\"stride_words\":{},"
      "\"endianness\":{}}}\n  }},\n  \"textures\": [",
      signature, observation.frame_sequence, observation.draw_sequence,
      prepared.vertex_shader_hash, prepared.pixel_shader_hash,
      prepared.vertex_specialization_mask, prepared.pixel_specialization_mask,
      PreparedPipelineHash(prepared), prepared.guest_primitive_type,
      prepared.host_primitive_type, prepared.host_vertex_shader_type,
      prepared.tessellation_mode, prepared.index_buffer_type,
      prepared.host_index_format, prepared.host_primitive_reset_enabled,
      prepared.normalized_depth_control, prepared.normalized_color_mask,
      prepared.bound_render_target_bits, prepared.bound_render_target_formats[0],
      prepared.bound_render_target_formats[1],
      prepared.bound_render_target_formats[2],
      prepared.bound_render_target_formats[3],
      prepared.bound_render_target_formats[4], prepared.flags,
      index_payload.size(), HashBytes(index_payload.data(), index_payload.size()),
      observation.index_buffer_address, observation.index_format,
      observation.index_endianness, observation.index_count,
      vertex_payload.size(),
      HashBytes(vertex_payload.data(), vertex_payload.size()), binding.address,
      binding.fetch_constant, binding.stride_words, binding.endianness);
  for (size_t i = 0; i < textures.size(); ++i) {
    const auto &texture = textures[i];
    if (i) {
      document += ",";
    }
    document += fmt::format(
        "\n    {{\"fetch_constant\":{},\"base_file\":"
        "\"texture_{:02}_base.bin\",\"base_bytes\":{},"
        "\"base_hash\":\"{:016X}\",\"base_address\":\"{:08X}\","
        "\"mip_file\":{},\"mip_bytes\":{},\"mip_hash\":{},"
        "\"mip_address\":\"{:08X}\"}}",
        texture.fetch_constant, texture.fetch_constant, texture.base.size(),
        HashBytes(texture.base.data(), texture.base.size()),
        texture.base_address,
        texture.mip.empty()
            ? "null"
            : fmt::format("\"texture_{:02}_mip.bin\"",
                          texture.fetch_constant),
        texture.mip.size(),
        texture.mip.empty()
            ? "null"
            : fmt::format("\"{:016X}\"",
                          HashBytes(texture.mip.data(), texture.mip.size())),
        texture.mip_address);
  }
  document += "\n  ],\n  \"constants\": {\n";
  AppendFloatConstants(document, "vertex_float",
                       observation.vertex_float_constants,
                       observation.vertex_float_constant_count);
  document += ",\n";
  AppendFloatConstants(document, "pixel_float",
                       observation.pixel_float_constants,
                       observation.pixel_float_constant_count);
  document += ",\n    \"bool_bitmap\": [";
  for (uint32_t i = 0; i < 8; ++i) {
    document += fmt::format("{}\"{:08X}\"", i ? "," : "",
                            observation.bool_constant_bitmap[i]);
  }
  document += "],\n    \"bool_values\": [";
  for (uint32_t i = 0; i < 8; ++i) {
    document += fmt::format("{}\"{:08X}\"", i ? "," : "",
                            observation.bool_constant_values[i]);
  }
  document += fmt::format(
      "],\n    \"loop_bitmap\": \"{:08X}\",\n"
      "    \"loop_values\": [",
      observation.loop_constant_bitmap);
  for (uint32_t i = 0; i < 32; ++i) {
    document += fmt::format("{}\"{:08X}\"", i ? "," : "",
                            observation.loop_constant_values[i]);
  }
  document += "],\n    \"texture_states\": [";
  const uint32_t texture_state_count = std::min(
      observation.texture_state_count,
      rex::system::kGraphicsTextureFetchObservationLimit);
  for (uint32_t i = 0; i < texture_state_count; ++i) {
    const auto &state = observation.texture_states[i];
    if (i) {
      document += ",";
    }
    document += fmt::format(
        "\n      {{\"stage\":{},\"fetch_constant\":{},"
        "\"dwords\":[\"{:08X}\",\"{:08X}\",\"{:08X}\",\"{:08X}\","
        "\"{:08X}\",\"{:08X}\"],\"opcode\":{},\"dimension\":{},"
        "\"filters\":\"{:08X}\",\"flags\":\"{:08X}\","
        "\"lod_bias\":\"{:08X}\",\"offsets\":\"{:08X}\","
        "\"result_target\":{},\"result_index\":{},"
        "\"result_mask\":{},\"result_components\":{}}}",
        state.stage, state.fetch_constant, state.dwords[0], state.dwords[1],
        state.dwords[2], state.dwords[3], state.dwords[4], state.dwords[5],
        state.opcode, state.dimension, state.filters, state.flags,
        state.lod_bias, state.offsets, state.result_storage_target,
        state.result_storage_index, state.result_write_mask,
        state.result_components);
  }
  document += texture_state_count ? "\n    ]\n" : "]\n";
  document +=
      "  },\n  \"safety\": {\"guest_payload_read\":"
      "\"bounded_snapshot_only\",\"payload_scope\":\"local_only\","
      "\"native_upload\":false,\"native_draw\":false,"
      "\"suppression_allowed\":false,\"xenos_authority\":true}\n}\n";
  const auto manifest_bytes = std::span(
      reinterpret_cast<const uint8_t *>(document.data()), document.size());
  if (!write_payload(L"snapshot.json", manifest_bytes)) {
    reject("manifest_write_failed");
    return;
  }
  std::filesystem::rename(staging, g_replay_snapshot.output_root, error);
  if (error) {
    reject("snapshot_commit_failed");
    return;
  }

  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.snapshot.capture",
      {{"signature", fmt::format("{:016X}", signature)},
       {"status", "captured"},
       {"frame", std::to_string(observation.frame_sequence)},
       {"draw", std::to_string(observation.draw_sequence)},
       {"index_bytes", std::to_string(index_payload.size())},
       {"vertex_bytes", std::to_string(vertex_payload.size())},
       {"texture_resources", std::to_string(textures.size())},
       {"texture_bytes", std::to_string(texture_bytes)},
       {"guest_payload_read", "bounded_snapshot_only"},
       {"payload_persisted", "local_only"},
       {"native_upload", "false"},
       {"native_draw", "false"},
       {"suppression_eligible", "false"}});
}

uint64_t DrawStateHash(
    const rex::system::GraphicsDrawObservation &observation) {
  uint64_t hash = 0xCBF29CE484222325ull;
  const auto hash_float_constants = [&](const auto *constants, uint32_t count) {
    const uint32_t bounded_count = std::min(
        count, rex::system::kGraphicsFloatConstantObservationLimit);
    for (uint32_t i = 0; i < bounded_count; ++i) {
      hash = HashCombine(hash, constants[i].index);
      for (uint32_t value : constants[i].values) {
        hash = HashCombine(hash, value);
      }
    }
  };
  hash_float_constants(observation.vertex_float_constants,
                       observation.vertex_float_constant_count);
  hash_float_constants(observation.pixel_float_constants,
                       observation.pixel_float_constant_count);
  for (uint32_t i = 0; i < 8; ++i) {
    hash = HashCombine(hash, observation.bool_constant_bitmap[i]);
    hash = HashCombine(hash, observation.bool_constant_values[i] &
                                 observation.bool_constant_bitmap[i]);
  }
  hash = HashCombine(hash, observation.loop_constant_bitmap);
  for (uint32_t i = 0; i < 32; ++i) {
    if (observation.loop_constant_bitmap & (1u << i)) {
      hash = HashCombine(hash, observation.loop_constant_values[i]);
    }
  }
  const uint32_t texture_count = std::min(
      observation.texture_state_count,
      rex::system::kGraphicsTextureFetchObservationLimit);
  for (uint32_t i = 0; i < texture_count; ++i) {
    const auto &state = observation.texture_states[i];
    for (uint32_t value :
         {state.stage, state.fetch_constant, state.opcode, state.dimension,
          state.filters, state.flags, state.lod_bias, state.offsets,
          state.result_storage_target, state.result_storage_index,
          state.result_write_mask, state.result_components}) {
      hash = HashCombine(hash, value);
    }
    for (uint32_t value : state.dwords) {
      hash = HashCombine(hash, value);
    }
  }
  return hash ? hash : 1;
}

std::string SerializeFloatConstants(
    const rex::system::GraphicsFloatConstantObservation *constants,
    uint32_t count) {
  std::string result;
  const uint32_t bounded_count = std::min(
      count, rex::system::kGraphicsFloatConstantObservationLimit);
  for (uint32_t i = 0; i < bounded_count; ++i) {
    if (!result.empty()) {
      result += ";";
    }
    result += fmt::format("{}:{:08X}:{:08X}:{:08X}:{:08X}",
                          constants[i].index, constants[i].values[0],
                          constants[i].values[1], constants[i].values[2],
                          constants[i].values[3]);
  }
  return result;
}

std::string SerializeWordConstants(const uint32_t *bitmap,
                                   const uint32_t *values,
                                   uint32_t word_count) {
  std::string result;
  for (uint32_t i = 0; i < word_count; ++i) {
    if (!bitmap[i]) {
      continue;
    }
    if (!result.empty()) {
      result += ";";
    }
    result += fmt::format("{}:{:08X}:{:08X}", i, bitmap[i], values[i]);
  }
  return result;
}

std::string SerializeLoopConstants(uint32_t bitmap, const uint32_t *values) {
  std::string result;
  for (uint32_t i = 0; i < 32; ++i) {
    if (!(bitmap & (uint32_t(1) << i))) {
      continue;
    }
    if (!result.empty()) {
      result += ";";
    }
    result += fmt::format("{}:{:08X}", i, values[i]);
  }
  return result;
}

std::string SerializeTextureStates(
    const rex::system::GraphicsDrawObservation &observation) {
  std::string result;
  const uint32_t bounded_count = std::min(
      observation.texture_state_count,
      rex::system::kGraphicsTextureFetchObservationLimit);
  for (uint32_t i = 0; i < bounded_count; ++i) {
    const auto &state = observation.texture_states[i];
    if (!result.empty()) {
      result += ";";
    }
    result += fmt::format(
        "{}:{}:{:08X}:{:08X}:{:08X}:{:08X}:{:08X}:{:08X}:{}:{}:{:06X}:"
        "{:02X}:{:08X}:{:06X}:{}:{}:{:X}:{:X}",
        state.stage, state.fetch_constant, state.dwords[0], state.dwords[1],
        state.dwords[2], state.dwords[3], state.dwords[4], state.dwords[5],
        state.opcode, state.dimension, state.filters, state.flags,
        state.lod_bias, state.offsets, state.result_storage_target,
        state.result_storage_index, state.result_write_mask,
        state.result_components);
  }
  return result;
}

size_t ResolveTargetIndex(uint32_t address) {
  size_t index = size_t(HashCombine(0xCBF29CE484222325ull, address) %
                        kResolveTargetCapacity);
  for (size_t probe = 0; probe < kResolveTargetCapacity; ++probe) {
    const ResolveTargetEntry &entry = g_dependency_census.targets[index];
    if (!entry.resolve_count || entry.address == address) {
      return index;
    }
    index = (index + 1) % kResolveTargetCapacity;
  }
  return kResolveTargetCapacity;
}

void MapResolvePage(uint32_t page, size_t target_index) {
  size_t index =
      size_t(HashCombine(0x9E3779B97F4A7C15ull, page) % kResolvePageCapacity);
  for (size_t probe = 0; probe < kResolvePageCapacity; ++probe) {
    ResolvePageEntry &entry = g_dependency_census.pages[index];
    if (!entry.target_index_plus_one) {
      entry.page = page;
      entry.target_index_plus_one = uint32_t(target_index + 1);
      ++g_dependency_census.page_count;
      return;
    }
    if (entry.page == page) {
      entry.target_index_plus_one = uint32_t(target_index + 1);
      return;
    }
    index = (index + 1) % kResolvePageCapacity;
  }
  ++g_dependency_census.page_overflow_count;
}

void MapResolveRange(size_t target_index, uint32_t address, uint32_t length) {
  const uint64_t first_page = uint64_t(address) / kGuestPageSize;
  const uint64_t last_address = uint64_t(address) + uint64_t(length) - 1;
  const uint64_t last_page = last_address / kGuestPageSize;
  const uint64_t page_count = last_page - first_page + 1;
  const uint64_t bounded_page_count =
      std::min<uint64_t>(page_count, kResolvePageCapacity);
  for (uint64_t offset = 0; offset < bounded_page_count; ++offset) {
    MapResolvePage(uint32_t(first_page + offset), target_index);
  }
  if (page_count > bounded_page_count) {
    g_dependency_census.page_overflow_count += page_count - bounded_page_count;
  }
}

size_t FindResolveTarget(uint32_t address) {
  const uint32_t page = uint32_t(uint64_t(address) / kGuestPageSize);
  size_t index =
      size_t(HashCombine(0x9E3779B97F4A7C15ull, page) % kResolvePageCapacity);
  for (size_t probe = 0; probe < kResolvePageCapacity; ++probe) {
    const ResolvePageEntry &page_entry = g_dependency_census.pages[index];
    if (!page_entry.target_index_plus_one) {
      return kResolveTargetCapacity;
    }
    if (page_entry.page == page) {
      const size_t target_index = page_entry.target_index_plus_one - 1;
      const ResolveTargetEntry &target =
          g_dependency_census.targets[target_index];
      const uint64_t target_end =
          uint64_t(target.address) + uint64_t(target.length);
      return address >= target.address && uint64_t(address) < target_end
                 ? target_index
                 : kResolveTargetCapacity;
    }
    index = (index + 1) % kResolvePageCapacity;
  }
  return kResolveTargetCapacity;
}

void BeginDependencyWindow(uint64_t frame) {
  if (!g_dependency_census.window_first_frame) {
    g_dependency_census.window_first_frame = frame;
  }
  g_dependency_census.window_last_frame =
      std::max(g_dependency_census.window_last_frame, frame);
}

void ResetDependencyWindow() {
  g_dependency_census.window_first_frame = 0;
  g_dependency_census.window_last_frame = 0;
  g_dependency_census.window_resolve_count = 0;
  g_dependency_census.window_resolve_bytes = 0;
  g_dependency_census.window_failed_copy_count = 0;
  g_dependency_census.window_zero_length_copy_count = 0;
  g_dependency_census.window_sampled_draw_count = 0;
  g_dependency_census.window_sample_reference_count = 0;
  g_dependency_census.window_sampled_target_count = 0;
  g_dependency_census.window_query_draw_count = 0;
  g_dependency_census.window_memexport_draw_count = 0;
  for (ResolveTargetEntry &target : g_dependency_census.targets) {
    target.window_resolve_count = 0;
    target.window_sampled_draw_count = 0;
  }
}

void EmitDependencyCensusWindow() {
  if (!g_dependency_census.window_first_frame) {
    return;
  }

  const auto number = [](uint64_t value) { return std::to_string(value); };
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.census.resolve_window",
      {{"first_frame", number(g_dependency_census.window_first_frame)},
       {"last_frame", number(g_dependency_census.window_last_frame)},
       {"resolves", number(g_dependency_census.window_resolve_count)},
       {"resolve_bytes", number(g_dependency_census.window_resolve_bytes)},
       {"failed_copies", number(g_dependency_census.window_failed_copy_count)},
       {"zero_length_copies",
        number(g_dependency_census.window_zero_length_copy_count)},
       {"sampled_draws", number(g_dependency_census.window_sampled_draw_count)},
       {"sample_references",
        number(g_dependency_census.window_sample_reference_count)},
       {"sampled_targets",
        number(g_dependency_census.window_sampled_target_count)},
       {"query_draws", number(g_dependency_census.window_query_draw_count)},
       {"memexport_draws",
        number(g_dependency_census.window_memexport_draw_count)},
       {"tracked_targets", number(g_dependency_census.target_count)},
       {"target_overflow", number(g_dependency_census.target_overflow_count)},
       {"tracked_pages", number(g_dependency_census.page_count)},
       {"page_overflow", number(g_dependency_census.page_overflow_count)},
       {"target_capacity", "4096"},
       {"page_capacity", "32768"},
       {"summary_limit", "32"}});

  std::array<size_t, kResolveTargetCapacity> order{};
  for (size_t i = 0; i < order.size(); ++i) {
    order[i] = i;
  }
  std::sort(order.begin(), order.end(), [](size_t left, size_t right) {
    const ResolveTargetEntry &left_entry = g_dependency_census.targets[left];
    const ResolveTargetEntry &right_entry = g_dependency_census.targets[right];
    const uint64_t left_activity =
        left_entry.window_resolve_count + left_entry.window_sampled_draw_count;
    const uint64_t right_activity = right_entry.window_resolve_count +
                                    right_entry.window_sampled_draw_count;
    if (left_activity != right_activity) {
      return left_activity > right_activity;
    }
    return left_entry.address < right_entry.address;
  });

  size_t emitted = 0;
  for (size_t target_index : order) {
    const ResolveTargetEntry &target =
        g_dependency_census.targets[target_index];
    if ((!target.window_resolve_count && !target.window_sampled_draw_count) ||
        emitted == kResolveSummaryLimit) {
      break;
    }
    const bool sampled = target.sampled_draw_count != 0;
    const std::string query_relation =
        target.conditional_sample_draw_count ||
                target.query_state_sample_draw_count
            ? "related_draw_observed"
            : "unknown_uninstrumented";
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.census.resolve_target",
        {{"rank", number(++emitted)},
         {"address", fmt::format("{:08X}", target.address)},
         {"length", number(target.length)},
         {"maximum_length", number(target.maximum_length)},
         {"resolves", number(target.resolve_count)},
         {"resolved_bytes", number(target.resolved_bytes)},
         {"first_resolve_frame", number(target.first_resolve_frame)},
         {"last_resolve_frame", number(target.last_resolve_frame)},
         {"sampled_later", sampled ? "true" : "unobserved"},
         {"sampled_draws", number(target.sampled_draw_count)},
         {"sample_references", number(target.sample_reference_count)},
         {"first_sample_frame", number(target.first_sample_frame)},
         {"last_sample_frame", number(target.last_sample_frame)},
         {"conditional_sample_draws",
          number(target.conditional_sample_draw_count)},
         {"query_state_sample_draws",
          number(target.query_state_sample_draw_count)},
         {"memexport_sample_draws", number(target.memexport_sample_draw_count)},
         {"last_fetch_index", number(target.last_fetch_index)},
         {"last_fetch_kind", target.last_fetch_was_mip ? "mip" : "base"},
         {"copy_state", fmt::format("{:08X}:{:08X}:{:08X}:{:08X}",
                                    target.sample.rb_copy_control,
                                    target.sample.rb_copy_dest_info,
                                    target.sample.rb_copy_dest_pitch,
                                    target.sample.surface_info)},
         {"presentation_only", "unknown_uninstrumented"},
         {"guest_cpu_read", "unknown_uninstrumented"},
         {"query_dependency", query_relation},
         {"semantic_role", "unknown_unclassified"},
         {"suppression_eligible", "false"}});
  }

  ResetDependencyWindow();
}

void AdvanceDependencyWindow(uint64_t frame) {
  if (g_dependency_census.window_first_frame &&
      frame >= g_dependency_census.window_first_frame + kFrameSummaryInterval) {
    EmitDependencyCensusWindow();
  }
  BeginDependencyWindow(frame);
}

uint64_t
DrawSignature(const rex::system::GraphicsDrawObservation &observation) {
  uint64_t hash = 0xCBF29CE484222325ull;
  for (uint64_t value :
       {observation.vertex_shader_hash, observation.pixel_shader_hash,
        uint64_t(observation.primitive_type),
        uint64_t(observation.source_select), uint64_t(observation.indexed),
        uint64_t(observation.major_mode_explicit),
        uint64_t(observation.vertex_memexport),
        uint64_t(observation.surface_info), uint64_t(observation.color_info[0]),
        uint64_t(observation.color_info[1]),
        uint64_t(observation.color_info[2]),
        uint64_t(observation.color_info[3]), uint64_t(observation.depth_info),
        uint64_t(observation.window_scissor_tl),
        uint64_t(observation.window_scissor_br),
        uint64_t(observation.rb_modecontrol)}) {
    hash = HashCombine(hash, value);
  }
  return hash ? hash : 1;
}

uint64_t
CandidateSignature(const rex::system::GraphicsDrawObservation &observation,
                   bool samples_resolved_target,
                   const rex::system::GraphicsPreparedDrawObservation
                       &prepared) {
  uint64_t hash = DrawSignature(observation);
  for (uint64_t value : {prepared.vertex_specialization_mask,
                         prepared.pixel_specialization_mask,
                         PreparedPipelineHash(prepared),
                         uint64_t(observation.index_format),
                         uint64_t(observation.index_endianness),
                         uint64_t(observation.vertex_index_offset),
                         uint64_t(observation.vertex_index_min),
                         uint64_t(observation.vertex_index_max),
                         uint64_t(observation.vertex_binding_count),
                         uint64_t(observation.vertex_binding_overflow),
                         uint64_t(observation.vertex_attribute_count),
                         uint64_t(observation.vertex_attribute_overflow),
                         uint64_t(observation.vertex_float_constant_count),
                         uint64_t(observation.vertex_float_constant_overflow),
                         uint64_t(observation.pixel_float_constant_count),
                         uint64_t(observation.pixel_float_constant_overflow),
                         uint64_t(observation.texture_state_count),
                         uint64_t(observation.texture_state_overflow),
                         uint64_t(observation.viz_query_condition),
                         uint64_t(observation.pa_sc_viz_query),
                         uint64_t(samples_resolved_target),
                         uint64_t(observation.texture_fetch_mask),
                         uint64_t(observation.rb_color_mask),
                         uint64_t(observation.rb_blendcontrol[0]),
                         uint64_t(observation.rb_blendcontrol[1]),
                         uint64_t(observation.rb_blendcontrol[2]),
                         uint64_t(observation.rb_blendcontrol[3]),
                         uint64_t(observation.rb_depthcontrol),
                         uint64_t(observation.pa_su_sc_mode_cntl),
                         uint64_t(observation.pa_su_vtx_cntl)}) {
    hash = HashCombine(hash, value);
  }
  const uint32_t bounded_binding_count =
      std::min(observation.vertex_binding_count,
               rex::system::kGraphicsVertexBindingObservationLimit);
  for (uint32_t i = 0; i < bounded_binding_count; ++i) {
    const auto &binding = observation.vertex_bindings[i];
    hash = HashCombine(hash, binding.fetch_constant);
    hash = HashCombine(hash, binding.size);
    hash = HashCombine(hash, binding.stride_words);
    hash = HashCombine(hash, binding.endianness);
  }
  const uint32_t bounded_attribute_count =
      std::min(observation.vertex_attribute_count,
               rex::system::kGraphicsVertexAttributeObservationLimit);
  for (uint32_t i = 0; i < bounded_attribute_count; ++i) {
    const auto &attribute = observation.vertex_attributes[i];
    for (uint64_t value :
         {uint64_t(attribute.binding_index), uint64_t(attribute.fetch_constant),
          uint64_t(uint32_t(attribute.offset_words)),
          uint64_t(attribute.stride_words), uint64_t(attribute.data_format),
          uint64_t(attribute.fetch_word_mask),
          uint64_t(uint32_t(attribute.exp_adjust)),
          uint64_t(attribute.signed_rf_mode),
          uint64_t(attribute.result_storage_target),
          uint64_t(attribute.result_storage_index),
          uint64_t(attribute.result_write_mask),
          uint64_t(attribute.result_components), uint64_t(attribute.flags)}) {
      hash = HashCombine(hash, value);
    }
  }
  for (uint32_t value : observation.bool_constant_bitmap) {
    hash = HashCombine(hash, value);
  }
  hash = HashCombine(hash, observation.loop_constant_bitmap);
  const uint32_t bounded_texture_count = std::min(
      observation.texture_state_count,
      rex::system::kGraphicsTextureFetchObservationLimit);
  for (uint32_t i = 0; i < bounded_texture_count; ++i) {
    const auto &state = observation.texture_states[i];
    for (uint32_t value :
         {state.stage, state.fetch_constant, state.opcode, state.dimension,
          state.filters, state.flags, state.lod_bias, state.offsets,
          state.result_storage_target, state.result_storage_index,
          state.result_write_mask, state.result_components}) {
      hash = HashCombine(hash, value);
    }
  }
  return hash ? hash : 1;
}

bool HasValidCommandBufferLineage(
    const rex::system::GraphicsDrawObservation &observation) {
  if (observation.packet_physical_address == UINT32_MAX ||
      observation.command_buffer_physical_address == UINT32_MAX ||
      observation.command_buffer_root_physical_address == UINT32_MAX ||
      !observation.command_buffer_length_dwords) {
    return false;
  }
  const uint64_t buffer_begin =
      observation.command_buffer_physical_address;
  const uint64_t buffer_end =
      buffer_begin + uint64_t(observation.command_buffer_length_dwords) * 4;
  if ((buffer_begin & 3) ||
      observation.command_buffer_root_physical_address >=
          kPhysicalApertureSize ||
      (observation.command_buffer_root_physical_address & 3) ||
      buffer_end > kPhysicalApertureSize ||
      observation.packet_physical_address < buffer_begin ||
      observation.packet_physical_address >= buffer_end ||
      (observation.packet_physical_address & 3)) {
    return false;
  }
  if (!observation.command_buffer_depth) {
    return observation.command_buffer_parent_packet_physical_address ==
               UINT32_MAX &&
           observation.command_buffer_root_physical_address ==
               observation.command_buffer_physical_address;
  }
  if (observation.command_buffer_parent_packet_physical_address >=
          kPhysicalApertureSize ||
      (observation.command_buffer_parent_packet_physical_address & 3)) {
    return false;
  }
  if (observation.command_buffer_depth == 1) {
    return observation.command_buffer_root_physical_address ==
           observation.command_buffer_physical_address;
  }
  return observation.command_buffer_parent_packet_physical_address >=
         observation.command_buffer_root_physical_address;
}

void ObserveCommandBufferLineage(
    const rex::system::GraphicsDrawObservation &observation) {
  ++g_command_buffer_lineage_draws;
  if (observation.command_buffer_depth) {
    ++g_command_buffer_lineage_indirect_draws;
  } else {
    ++g_command_buffer_lineage_primary_draws;
  }
  if (!HasValidCommandBufferLineage(observation)) {
    ++g_command_buffer_lineage_invalid;
  }
}

void RecordPreparedCommandBufferLineage(
    uint64_t prepared_signature,
    const rex::system::GraphicsDrawObservation &observation) {
  if (!HasValidCommandBufferLineage(observation)) {
    return;
  }
  ++g_command_buffer_lineage_prepared_draws;
  const uint32_t packet_offset_bytes =
      observation.packet_physical_address -
      observation.command_buffer_physical_address;
  const uint32_t parent_root_offset_bytes =
      observation.command_buffer_depth > 1
          ? observation.command_buffer_parent_packet_physical_address -
                observation.command_buffer_root_physical_address
          : UINT32_MAX;
  const ActiveTitleIndirectBuffer *active =
      CurrentTitleIndirectBuffer(observation);
  const uint32_t constructor_store_address =
      active ? active->constructor_store_address : 0;
  const IndirectConstructorOrigin constructor_origin =
      active ? active->constructor_origin : IndirectConstructorOrigin{};
  uint64_t key = 0xCBF29CE484222325ull;
  for (uint64_t value :
       {uint64_t(constructor_store_address),
        uint64_t(constructor_origin.return_address),
        uint64_t(constructor_origin.owner.function_address),
        uint64_t(constructor_origin.owner.return_address),
        uint64_t(constructor_origin.owner.producer.function_address),
        uint64_t(constructor_origin.owner.producer.return_address),
        uint64_t(constructor_origin.owner.producer.context.function_address),
        uint64_t(constructor_origin.owner.producer.context.return_address),
        uint64_t(
            constructor_origin.owner.producer.context.semantic_receiver_address),
        uint64_t(constructor_origin.owner.producer.context
                     .semantic_receiver_generation),
        uint64_t(observation.command_buffer_depth)}) {
    key = HashCombine(key, value);
  }
  size_t index = size_t(key % kCommandBufferLineageCapacity);
  for (size_t probe = 0; probe < kCommandBufferLineageCapacity; ++probe) {
    CommandBufferLineageEntry &entry = g_command_buffer_lineages[index];
    if (!entry.calls) {
      entry.sample_prepared_signature = prepared_signature;
      entry.calls = 1;
      entry.first_frame = observation.frame_sequence;
      entry.last_frame = observation.frame_sequence;
      entry.first_draw = observation.draw_sequence;
      entry.last_draw = observation.draw_sequence;
      entry.packet_physical_address = observation.packet_physical_address;
      entry.command_buffer_physical_address =
          observation.command_buffer_physical_address;
      entry.sample_command_buffer_length_dwords =
          observation.command_buffer_length_dwords;
      entry.min_command_buffer_length_dwords =
          observation.command_buffer_length_dwords;
      entry.max_command_buffer_length_dwords =
          observation.command_buffer_length_dwords;
      entry.min_packet_offset_bytes = packet_offset_bytes;
      entry.max_packet_offset_bytes = packet_offset_bytes;
      entry.parent_packet_physical_address =
          observation.command_buffer_parent_packet_physical_address;
      entry.root_physical_address =
          observation.command_buffer_root_physical_address;
      entry.min_parent_root_offset_bytes = parent_root_offset_bytes;
      entry.max_parent_root_offset_bytes = parent_root_offset_bytes;
      entry.constructor_store_address = constructor_store_address;
      entry.constructor_function_address = constructor_origin.function_address;
      entry.constructor_return_address = constructor_origin.return_address;
      entry.sample_constructor_arguments = constructor_origin.arguments;
      entry.constructor_origin_known = constructor_origin.valid;
      entry.owner_function_address =
          constructor_origin.owner.function_address;
      entry.owner_return_address = constructor_origin.owner.return_address;
      entry.sample_owner_arguments = constructor_origin.owner.arguments;
      entry.owner_origin_known = constructor_origin.owner.valid;
      entry.producer_function_address =
          constructor_origin.owner.producer.function_address;
      entry.producer_return_address =
          constructor_origin.owner.producer.return_address;
      entry.sample_producer_arguments =
          constructor_origin.owner.producer.arguments;
      entry.producer_origin_known =
          constructor_origin.owner.producer.valid;
      entry.context_function_address =
          constructor_origin.owner.producer.context.function_address;
      entry.context_return_address =
          constructor_origin.owner.producer.context.return_address;
      entry.sample_context_arguments =
          constructor_origin.owner.producer.context.arguments;
      entry.sample_context_root_address =
          constructor_origin.owner.producer.context.root_address;
      entry.context_origin_known =
          constructor_origin.owner.producer.context.valid;
      entry.semantic_receiver_address = constructor_origin.owner.producer
                                            .context.semantic_receiver_address;
      entry.semantic_receiver_generation =
          constructor_origin.owner.producer.context
              .semantic_receiver_generation;
      entry.semantic_visibility_epoch = constructor_origin.owner.producer
                                            .context.semantic_visibility_epoch;
      entry.semantic_render_state_epoch = constructor_origin.owner.producer
                                              .context.semantic_render_state_epoch;
      entry.semantic_render_state_visibility_epoch =
          constructor_origin.owner.producer.context
              .semantic_render_state_visibility_epoch;
      entry.semantic_receiver_known = constructor_origin.owner.producer.context
                                          .semantic_receiver_known;
      entry.depth = observation.command_buffer_depth;
      ++g_command_buffer_lineage_entry_count;
      return;
    }
    if (entry.constructor_store_address == constructor_store_address &&
        entry.constructor_return_address == constructor_origin.return_address &&
        entry.owner_function_address ==
            constructor_origin.owner.function_address &&
        entry.owner_return_address == constructor_origin.owner.return_address &&
        entry.producer_function_address ==
            constructor_origin.owner.producer.function_address &&
        entry.producer_return_address ==
            constructor_origin.owner.producer.return_address &&
        entry.context_function_address ==
            constructor_origin.owner.producer.context.function_address &&
        entry.context_return_address ==
            constructor_origin.owner.producer.context.return_address &&
        entry.semantic_receiver_address ==
            constructor_origin.owner.producer.context
                .semantic_receiver_address &&
        entry.semantic_receiver_generation ==
            constructor_origin.owner.producer.context
                .semantic_receiver_generation &&
        entry.depth == observation.command_buffer_depth) {
      ++entry.calls;
      entry.semantic_preparation_epoch_varied |=
          entry.semantic_visibility_epoch !=
              constructor_origin.owner.producer.context
                  .semantic_visibility_epoch ||
          entry.semantic_render_state_epoch !=
              constructor_origin.owner.producer.context
                  .semantic_render_state_epoch ||
          entry.semantic_render_state_visibility_epoch !=
              constructor_origin.owner.producer.context
                  .semantic_render_state_visibility_epoch;
      entry.last_frame = observation.frame_sequence;
      entry.last_draw = observation.draw_sequence;
      entry.min_packet_offset_bytes =
          std::min(entry.min_packet_offset_bytes, packet_offset_bytes);
      entry.max_packet_offset_bytes =
          std::max(entry.max_packet_offset_bytes, packet_offset_bytes);
      entry.min_command_buffer_length_dwords =
          std::min(entry.min_command_buffer_length_dwords,
                   observation.command_buffer_length_dwords);
      entry.max_command_buffer_length_dwords =
          std::max(entry.max_command_buffer_length_dwords,
                   observation.command_buffer_length_dwords);
      entry.min_parent_root_offset_bytes =
          std::min(entry.min_parent_root_offset_bytes,
                   parent_root_offset_bytes);
      entry.max_parent_root_offset_bytes =
          std::max(entry.max_parent_root_offset_bytes,
                   parent_root_offset_bytes);
      entry.prepared_signature_varied |=
          entry.sample_prepared_signature != prepared_signature;
      if (entry.constructor_origin_known && constructor_origin.valid) {
        for (size_t argument = 0;
             argument < entry.sample_constructor_arguments.size(); ++argument) {
          if (entry.sample_constructor_arguments[argument] !=
              constructor_origin.arguments[argument]) {
            entry.constructor_argument_varying_mask |= 1u << argument;
          }
        }
      }
      if (entry.owner_origin_known && constructor_origin.owner.valid) {
        for (size_t argument = 0;
             argument < entry.sample_owner_arguments.size(); ++argument) {
          if (entry.sample_owner_arguments[argument] !=
              constructor_origin.owner.arguments[argument]) {
            entry.owner_argument_varying_mask |= 1u << argument;
          }
        }
      }
      if (entry.producer_origin_known &&
          constructor_origin.owner.producer.valid) {
        for (size_t argument = 0;
             argument < entry.sample_producer_arguments.size(); ++argument) {
          if (entry.sample_producer_arguments[argument] !=
              constructor_origin.owner.producer.arguments[argument]) {
            entry.producer_argument_varying_mask |= 1u << argument;
          }
        }
      }
      if (entry.context_origin_known &&
          constructor_origin.owner.producer.context.valid) {
        for (size_t argument = 0;
             argument < entry.sample_context_arguments.size(); ++argument) {
          if (entry.sample_context_arguments[argument] !=
              constructor_origin.owner.producer.context.arguments[argument]) {
            entry.context_argument_varying_mask |= 1u << argument;
          }
        }
        entry.context_root_address_varied |=
            entry.sample_context_root_address !=
            constructor_origin.owner.producer.context.root_address;
      }
      return;
    }
    index = (index + 1) % kCommandBufferLineageCapacity;
  }
  ++g_command_buffer_lineage_overflow;
}

void EmitCommandBufferLineageSummary() {
  EmitSemanticVisibilityWorkset();
  EmitProceduralModelSemanticInstances();
  EmitProceduralModelSemanticSubmissions();
  for (const CommandBufferLineageEntry &entry : g_command_buffer_lineages) {
    if (!entry.calls) {
      continue;
    }
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.discovery.command_buffer_lineage_entry",
        {{"sample_prepared_signature",
          fmt::format("{:016X}", entry.sample_prepared_signature)},
         {"prepared_signature_varied",
          entry.prepared_signature_varied ? "true" : "false"},
         {"calls", std::to_string(entry.calls)},
         {"first_frame", std::to_string(entry.first_frame)},
         {"last_frame", std::to_string(entry.last_frame)},
         {"first_draw", std::to_string(entry.first_draw)},
         {"last_draw", std::to_string(entry.last_draw)},
         {"sample_packet_physical_address",
          fmt::format("{:08X}", entry.packet_physical_address)},
         {"sample_command_buffer_physical_address",
          fmt::format("{:08X}", entry.command_buffer_physical_address)},
         {"sample_command_buffer_length_dwords",
          std::to_string(entry.sample_command_buffer_length_dwords)},
         {"min_command_buffer_length_dwords",
          std::to_string(entry.min_command_buffer_length_dwords)},
         {"max_command_buffer_length_dwords",
          std::to_string(entry.max_command_buffer_length_dwords)},
         {"min_packet_offset_bytes",
          std::to_string(entry.min_packet_offset_bytes)},
         {"max_packet_offset_bytes",
          std::to_string(entry.max_packet_offset_bytes)},
         {"sample_parent_packet_physical_address",
          fmt::format("{:08X}", entry.parent_packet_physical_address)},
         {"sample_root_physical_address",
          fmt::format("{:08X}", entry.root_physical_address)},
         {"min_parent_root_offset_bytes",
          entry.min_parent_root_offset_bytes == UINT32_MAX
              ? "none"
              : std::to_string(entry.min_parent_root_offset_bytes)},
         {"max_parent_root_offset_bytes",
          entry.max_parent_root_offset_bytes == UINT32_MAX
              ? "none"
              : std::to_string(entry.max_parent_root_offset_bytes)},
         {"constructor_store_address",
          entry.constructor_store_address
              ? fmt::format("{:08X}", entry.constructor_store_address)
              : "unknown"},
         {"constructor_function_address",
          entry.constructor_origin_known
              ? fmt::format("{:08X}", entry.constructor_function_address)
              : "unknown"},
         {"constructor_return_address",
          entry.constructor_origin_known
              ? fmt::format("{:08X}", entry.constructor_return_address)
              : "unknown"},
         {"sample_constructor_arguments",
          fmt::format(
              "{:08X},{:08X},{:08X},{:08X},{:08X},{:08X},{:08X},{:08X}",
              entry.sample_constructor_arguments[0],
              entry.sample_constructor_arguments[1],
              entry.sample_constructor_arguments[2],
              entry.sample_constructor_arguments[3],
              entry.sample_constructor_arguments[4],
              entry.sample_constructor_arguments[5],
              entry.sample_constructor_arguments[6],
              entry.sample_constructor_arguments[7])},
         {"constructor_argument_varying_mask",
          fmt::format("{:02X}", entry.constructor_argument_varying_mask)},
         {"owner_function_address",
          entry.owner_origin_known
              ? fmt::format("{:08X}", entry.owner_function_address)
              : "unknown"},
         {"owner_return_address",
          entry.owner_origin_known
              ? fmt::format("{:08X}", entry.owner_return_address)
              : "unknown"},
         {"sample_owner_arguments",
          fmt::format(
              "{:08X},{:08X},{:08X},{:08X},{:08X},{:08X},{:08X},{:08X}",
              entry.sample_owner_arguments[0], entry.sample_owner_arguments[1],
              entry.sample_owner_arguments[2], entry.sample_owner_arguments[3],
              entry.sample_owner_arguments[4], entry.sample_owner_arguments[5],
              entry.sample_owner_arguments[6], entry.sample_owner_arguments[7])},
         {"owner_argument_varying_mask",
          fmt::format("{:02X}", entry.owner_argument_varying_mask)},
         {"producer_function_address",
          entry.producer_origin_known
              ? fmt::format("{:08X}", entry.producer_function_address)
              : "unknown"},
         {"producer_return_address",
          entry.producer_origin_known
              ? fmt::format("{:08X}", entry.producer_return_address)
              : "unknown"},
         {"sample_producer_arguments",
          fmt::format(
              "{:08X},{:08X},{:08X},{:08X},{:08X},{:08X},{:08X},{:08X}",
              entry.sample_producer_arguments[0],
              entry.sample_producer_arguments[1],
              entry.sample_producer_arguments[2],
              entry.sample_producer_arguments[3],
              entry.sample_producer_arguments[4],
              entry.sample_producer_arguments[5],
              entry.sample_producer_arguments[6],
              entry.sample_producer_arguments[7])},
         {"producer_argument_varying_mask",
          fmt::format("{:02X}", entry.producer_argument_varying_mask)},
         {"context_function_address",
          entry.context_origin_known
              ? fmt::format("{:08X}", entry.context_function_address)
              : "unknown"},
         {"context_return_address",
          entry.context_origin_known
              ? fmt::format("{:08X}", entry.context_return_address)
              : "unknown"},
         {"sample_context_arguments",
          fmt::format(
              "{:08X},{:08X},{:08X},{:08X},{:08X},{:08X},{:08X},{:08X}",
              entry.sample_context_arguments[0],
              entry.sample_context_arguments[1],
              entry.sample_context_arguments[2],
              entry.sample_context_arguments[3],
              entry.sample_context_arguments[4],
              entry.sample_context_arguments[5],
              entry.sample_context_arguments[6],
              entry.sample_context_arguments[7])},
         {"context_argument_varying_mask",
          fmt::format("{:02X}", entry.context_argument_varying_mask)},
         {"sample_context_root_address",
          entry.context_origin_known
              ? fmt::format("{:08X}", entry.sample_context_root_address)
              : "unknown"},
         {"context_root_address_varied",
          entry.context_root_address_varied ? "true" : "false"},
         {"semantic_receiver_class",
          entry.semantic_receiver_known
              ? "proceduralGeometry::CProceduralModels"
              : "unknown"},
         {"semantic_receiver_address",
          entry.semantic_receiver_known
              ? fmt::format("{:08X}", entry.semantic_receiver_address)
              : "unknown"},
         {"semantic_receiver_generation",
          entry.semantic_receiver_known
              ? std::to_string(entry.semantic_receiver_generation)
              : "unknown"},
         {"semantic_visibility_epoch",
          entry.semantic_receiver_known
              ? std::to_string(entry.semantic_visibility_epoch)
              : "unknown"},
         {"semantic_render_state_epoch",
          entry.semantic_receiver_known
              ? std::to_string(entry.semantic_render_state_epoch)
              : "unknown"},
         {"semantic_render_state_visibility_epoch",
          entry.semantic_receiver_known
              ? std::to_string(entry.semantic_render_state_visibility_epoch)
              : "unknown"},
         {"semantic_preparation_epoch_varied",
          entry.semantic_preparation_epoch_varied ? "true" : "false"},
         {"depth", std::to_string(entry.depth)},
         {"guest_payload_read", "false"},
         {"guest_state_changed", "false"},
         {"xenos_authority", "true"},
         {"suppression_allowed", "false"}});
  }
  uint64_t semantic_receivers_tracked = 0;
  uint64_t semantic_receivers_live = 0;
  uint64_t semantic_receivers_destroying = 0;
  uint64_t semantic_receivers_destroyed = 0;
  for (const SemanticReceiverLifecycleEntry &entry :
       g_semantic_receiver_lifecycles) {
    const uint32_t address = entry.address.load(std::memory_order_acquire);
    if (!address) {
      continue;
    }
    ++semantic_receivers_tracked;
    const auto state = static_cast<SemanticReceiverState>(
        entry.state.load(std::memory_order_acquire));
    const char *state_name = "empty";
    switch (state) {
    case SemanticReceiverState::kLive:
      state_name = "live";
      ++semantic_receivers_live;
      break;
    case SemanticReceiverState::kDestroying:
      state_name = "destroying";
      ++semantic_receivers_destroying;
      break;
    case SemanticReceiverState::kDestroyed:
      state_name = "destroyed";
      ++semantic_receivers_destroyed;
      break;
    case SemanticReceiverState::kEmpty:
      break;
    }
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.discovery.semantic_receiver_lifecycle_entry",
        {{"class", "proceduralGeometry::CProceduralModels"},
         {"address", fmt::format("{:08X}", address)},
         {"generation",
          std::to_string(entry.generation.load(std::memory_order_relaxed))},
         {"state", state_name},
         {"dispatches",
          std::to_string(entry.dispatches.load(std::memory_order_relaxed))},
         {"visibility_preparations",
          std::to_string(entry.visibility_preparations.load(
              std::memory_order_relaxed))},
         {"render_state_preparations",
          std::to_string(entry.render_state_preparations.load(
              std::memory_order_relaxed))},
         {"visibility_epoch",
          std::to_string(
              entry.visibility_epoch.load(std::memory_order_relaxed))},
         {"render_state_epoch",
          std::to_string(
              entry.render_state_epoch.load(std::memory_order_relaxed))},
         {"render_state_visibility_epoch",
          std::to_string(entry.render_state_visibility_epoch.load(
              std::memory_order_relaxed))},
         {"dispatches_with_preparation",
          std::to_string(entry.dispatches_with_preparation.load(
              std::memory_order_relaxed))},
         {"dispatches_without_preparation",
          std::to_string(entry.dispatches_without_preparation.load(
              std::memory_order_relaxed))},
         {"dispatches_without_visibility",
          std::to_string(entry.dispatches_without_visibility.load(
              std::memory_order_relaxed))},
         {"dispatches_without_render_state",
          std::to_string(entry.dispatches_without_render_state.load(
              std::memory_order_relaxed))},
         {"identity_join", "exact_constructor_receiver_address"},
         {"guest_payload_read", "false"},
         {"xenos_authority", "true"},
         {"suppression_allowed", "false"}});
  }
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.discovery.command_buffer_lineage_summary",
      {{"draws", std::to_string(g_command_buffer_lineage_draws)},
       {"primary_draws",
        std::to_string(g_command_buffer_lineage_primary_draws)},
       {"indirect_draws",
        std::to_string(g_command_buffer_lineage_indirect_draws)},
       {"invalid_lineages",
        std::to_string(g_command_buffer_lineage_invalid)},
       {"prepared_draws",
        std::to_string(g_command_buffer_lineage_prepared_draws)},
       {"entries", std::to_string(g_command_buffer_lineage_entry_count)},
       {"overflow", std::to_string(g_command_buffer_lineage_overflow)},
       {"capacity", std::to_string(kCommandBufferLineageCapacity)},
       {"title_indirect_packets_recorded",
        std::to_string(g_title_indirect_packets_recorded)},
       {"title_indirect_packet_address_failures",
        std::to_string(g_title_indirect_packet_address_failures)},
       {"title_indirect_packet_table_overflow",
        std::to_string(g_title_indirect_packet_table_overflow)},
       {"title_indirect_packet_evictions",
        std::to_string(g_title_indirect_packet_evictions)},
       {"indirect_buffer_enters",
        std::to_string(g_title_indirect_buffer_enters)},
       {"indirect_buffer_exits",
        std::to_string(g_title_indirect_buffer_exits)},
       {"indirect_buffer_constructor_matches",
        std::to_string(g_title_indirect_buffer_matches)},
       {"indirect_buffer_constructor_unmatched",
        std::to_string(g_title_indirect_buffer_unmatched)},
       {"indirect_buffer_stack_faults",
        std::to_string(g_title_indirect_stack_faults)},
       {"indirect_draw_stack_faults",
        std::to_string(g_title_indirect_draw_stack_faults)},
       {"indirect_constructor_entries",
        std::to_string(g_indirect_constructor_entries.load(
            std::memory_order_relaxed))},
       {"indirect_constructor_exits",
        std::to_string(g_indirect_constructor_exits.load(
            std::memory_order_relaxed))},
       {"indirect_constructor_invocations_open_at_shutdown",
        std::to_string(g_indirect_constructor_invocations_open.load(
            std::memory_order_relaxed))},
       {"indirect_constructor_stack_faults",
        std::to_string(g_indirect_constructor_stack_faults.load(
            std::memory_order_relaxed))},
       {"indirect_packets_without_constructor_origin",
        std::to_string(g_indirect_packets_without_constructor_origin.load(
            std::memory_order_relaxed))},
       {"indirect_owner_entries",
        std::to_string(
            g_indirect_owner_entries.load(std::memory_order_relaxed))},
       {"indirect_owner_exits",
        std::to_string(
            g_indirect_owner_exits.load(std::memory_order_relaxed))},
       {"indirect_owner_invocations_open_at_shutdown",
        std::to_string(g_indirect_owner_invocations_open.load(
            std::memory_order_relaxed))},
       {"indirect_owner_stack_faults",
        std::to_string(
            g_indirect_owner_stack_faults.load(std::memory_order_relaxed))},
       {"indirect_constructors_without_owner_origin",
        std::to_string(g_indirect_constructors_without_owner_origin.load(
            std::memory_order_relaxed))},
       {"indirect_constructor_owner_mismatches",
        std::to_string(g_indirect_constructor_owner_mismatches.load(
            std::memory_order_relaxed))},
       {"indirect_producer_entries",
        std::to_string(g_indirect_producer_entries.load(
            std::memory_order_relaxed))},
       {"indirect_producer_exits",
        std::to_string(
            g_indirect_producer_exits.load(std::memory_order_relaxed))},
       {"indirect_producer_invocations_open_at_shutdown",
        std::to_string(g_indirect_producer_invocations_open.load(
            std::memory_order_relaxed))},
       {"indirect_producer_stack_faults",
        std::to_string(g_indirect_producer_stack_faults.load(
            std::memory_order_relaxed))},
       {"indirect_owners_without_producer_origin",
        std::to_string(g_indirect_owners_without_producer_origin.load(
            std::memory_order_relaxed))},
       {"indirect_owner_producer_mismatches",
        std::to_string(g_indirect_owner_producer_mismatches.load(
            std::memory_order_relaxed))},
       {"indirect_context_entries",
        std::to_string(
            g_indirect_context_entries.load(std::memory_order_relaxed))},
       {"indirect_context_exits",
        std::to_string(
            g_indirect_context_exits.load(std::memory_order_relaxed))},
       {"indirect_context_invocations_open_at_shutdown",
        std::to_string(g_indirect_context_invocations_open.load(
            std::memory_order_relaxed))},
       {"indirect_context_stack_faults",
        std::to_string(g_indirect_context_stack_faults.load(
            std::memory_order_relaxed))},
       {"indirect_producers_without_context_origin",
        std::to_string(g_indirect_producers_without_context_origin.load(
            std::memory_order_relaxed))},
       {"indirect_producer_context_mismatches",
        std::to_string(g_indirect_producer_context_mismatches.load(
            std::memory_order_relaxed))},
       {"semantic_receiver_class",
        "proceduralGeometry::CProceduralModels"},
       {"semantic_receiver_constructor_entries",
        std::to_string(g_semantic_receiver_constructor_entries.load(
            std::memory_order_relaxed))},
       {"semantic_receiver_constructor_exits",
        std::to_string(g_semantic_receiver_constructor_exits.load(
            std::memory_order_relaxed))},
       {"semantic_receiver_constructor_open_at_shutdown",
        std::to_string(g_semantic_receiver_constructor_open.load(
            std::memory_order_relaxed))},
       {"semantic_receiver_destructor_entries",
        std::to_string(g_semantic_receiver_destructor_entries.load(
            std::memory_order_relaxed))},
       {"semantic_receiver_destructor_exits",
        std::to_string(g_semantic_receiver_destructor_exits.load(
            std::memory_order_relaxed))},
       {"semantic_receiver_destructor_open_at_shutdown",
        std::to_string(g_semantic_receiver_destructor_open.load(
            std::memory_order_relaxed))},
       {"semantic_receiver_stack_faults",
        std::to_string(g_semantic_receiver_stack_faults.load(
            std::memory_order_relaxed))},
       {"semantic_receiver_instances_published",
        std::to_string(g_semantic_receiver_instances_published.load(
            std::memory_order_relaxed))},
       {"semantic_receiver_instances_destroyed",
        std::to_string(g_semantic_receiver_instances_destroyed.load(
            std::memory_order_relaxed))},
       {"semantic_receiver_address_reuses",
        std::to_string(g_semantic_receiver_address_reuses.load(
            std::memory_order_relaxed))},
       {"semantic_receiver_table_overflow",
        std::to_string(g_semantic_receiver_table_overflow.load(
            std::memory_order_relaxed))},
       {"semantic_receiver_dispatches",
        std::to_string(g_semantic_receiver_dispatches.load(
            std::memory_order_relaxed))},
       {"semantic_receiver_live_dispatches",
        std::to_string(g_semantic_receiver_live_dispatches.load(
            std::memory_order_relaxed))},
       {"semantic_receiver_unregistered_dispatches",
        std::to_string(g_semantic_receiver_unregistered_dispatches.load(
            std::memory_order_relaxed))},
       {"semantic_receiver_destroying_dispatches",
        std::to_string(g_semantic_receiver_destroying_dispatches.load(
            std::memory_order_relaxed))},
       {"semantic_receiver_destroyed_dispatches",
        std::to_string(g_semantic_receiver_destroyed_dispatches.load(
            std::memory_order_relaxed))},
       {"semantic_receiver_destructors_without_instance",
        std::to_string(g_semantic_receiver_destructors_without_instance.load(
            std::memory_order_relaxed))},
       {"semantic_visibility_entries",
        std::to_string(
            g_semantic_visibility_entries.load(std::memory_order_relaxed))},
       {"semantic_visibility_exits",
        std::to_string(
            g_semantic_visibility_exits.load(std::memory_order_relaxed))},
       {"semantic_visibility_open_at_shutdown",
        std::to_string(
            g_semantic_visibility_open.load(std::memory_order_relaxed))},
       {"semantic_render_state_entries",
        std::to_string(g_semantic_render_state_entries.load(
            std::memory_order_relaxed))},
       {"semantic_render_state_exits",
        std::to_string(
            g_semantic_render_state_exits.load(std::memory_order_relaxed))},
       {"semantic_render_state_open_at_shutdown",
        std::to_string(
            g_semantic_render_state_open.load(std::memory_order_relaxed))},
       {"semantic_stage_stack_faults",
        std::to_string(
            g_semantic_stage_stack_faults.load(std::memory_order_relaxed))},
       {"semantic_stage_unknown_receivers",
        std::to_string(g_semantic_stage_unknown_receivers.load(
            std::memory_order_relaxed))},
       {"semantic_receivers_tracked",
        std::to_string(semantic_receivers_tracked)},
       {"semantic_receivers_live_at_shutdown",
        std::to_string(semantic_receivers_live)},
       {"semantic_receivers_destroying_at_shutdown",
        std::to_string(semantic_receivers_destroying)},
       {"semantic_receivers_destroyed",
        std::to_string(semantic_receivers_destroyed)},
       {"indirect_buffers_open_at_shutdown",
        std::to_string(g_title_indirect_buffers_open.load(
            std::memory_order_relaxed))},
       {"correlation",
        "exact_title_store_to_backend_nested_command_buffer_shape"},
       {"semantic_identity", "unknown"},
       {"semantic_receiver_identity",
        "exact_rtti_lifetime_and_preparation_join"},
       {"guest_payload_read", "false"},
       {"guest_state_changed", "false"},
       {"control_flow_changed", "false"},
       {"xenos_authority", "true"},
       {"suppression_allowed", "false"}});
}

uint64_t SemanticGeometryLayoutHash(
    const rex::system::GraphicsDrawObservation &observation) {
  uint64_t hash = UINT64_C(0xCBF29CE484222325);
  for (uint64_t value :
       {uint64_t(observation.primitive_type),
        uint64_t(observation.source_select), uint64_t(observation.indexed),
        uint64_t(observation.index_format),
        uint64_t(observation.index_endianness),
        uint64_t(observation.index_reset_enabled),
        uint64_t(observation.index_reset),
        uint64_t(observation.vertex_index_offset),
        uint64_t(observation.vertex_index_min),
        uint64_t(observation.vertex_index_max),
        uint64_t(observation.vertex_binding_count),
        uint64_t(observation.vertex_binding_overflow),
        uint64_t(observation.vertex_attribute_count),
        uint64_t(observation.vertex_attribute_overflow)}) {
    hash = HashCombine(hash, value);
  }
  const uint32_t binding_count = std::min(
      observation.vertex_binding_count,
      rex::system::kGraphicsVertexBindingObservationLimit);
  for (uint32_t i = 0; i < binding_count; ++i) {
    const auto &binding = observation.vertex_bindings[i];
    for (uint32_t value : {binding.fetch_constant, binding.size,
                           binding.stride_words, binding.endianness}) {
      hash = HashCombine(hash, value);
    }
  }
  const uint32_t attribute_count = std::min(
      observation.vertex_attribute_count,
      rex::system::kGraphicsVertexAttributeObservationLimit);
  for (uint32_t i = 0; i < attribute_count; ++i) {
    const auto &attribute = observation.vertex_attributes[i];
    for (uint64_t value :
         {uint64_t(attribute.binding_index),
          uint64_t(attribute.fetch_constant),
          uint64_t(uint32_t(attribute.offset_words)),
          uint64_t(attribute.stride_words), uint64_t(attribute.data_format),
          uint64_t(attribute.fetch_word_mask),
          uint64_t(uint32_t(attribute.exp_adjust)),
          uint64_t(attribute.signed_rf_mode),
          uint64_t(attribute.result_storage_target),
          uint64_t(attribute.result_storage_index),
          uint64_t(attribute.result_write_mask),
          uint64_t(attribute.result_components), uint64_t(attribute.flags)}) {
      hash = HashCombine(hash, value);
    }
  }
  return hash ? hash : 1;
}

uint64_t SemanticTextureLayoutHash(
    const rex::system::GraphicsDrawObservation &observation) {
  uint64_t hash = UINT64_C(0xCBF29CE484222325);
  hash = HashCombine(hash, observation.texture_fetch_mask);
  hash = HashCombine(hash, observation.texture_fetch_layout_valid_mask);
  hash = HashCombine(hash, observation.texture_state_count);
  hash = HashCombine(hash, observation.texture_state_overflow);
  const uint32_t texture_count = std::min(
      observation.texture_state_count,
      rex::system::kGraphicsTextureFetchObservationLimit);
  for (uint32_t i = 0; i < texture_count; ++i) {
    const auto &state = observation.texture_states[i];
    for (uint32_t value :
         {state.stage, state.fetch_constant, state.opcode, state.dimension,
          state.filters, state.flags, state.lod_bias, state.offsets,
          state.result_storage_target, state.result_storage_index,
          state.result_write_mask, state.result_components}) {
      hash = HashCombine(hash, value);
    }
    for (uint32_t value : state.dwords) {
      hash = HashCombine(hash, value);
    }
  }
  return hash ? hash : 1;
}

uint64_t SemanticBatchGeometryLayoutHash(
    const rex::system::GraphicsDrawObservation &observation) {
  uint64_t hash = UINT64_C(0xCBF29CE484222325);
  for (uint64_t value :
       {uint64_t(observation.primitive_type),
        uint64_t(observation.source_select), uint64_t(observation.indexed),
        uint64_t(observation.index_format),
        uint64_t(observation.index_endianness),
        uint64_t(observation.index_reset_enabled),
        uint64_t(observation.vertex_binding_count),
        uint64_t(observation.vertex_binding_overflow),
        uint64_t(observation.vertex_attribute_count),
        uint64_t(observation.vertex_attribute_overflow)}) {
    hash = HashCombine(hash, value);
  }
  const uint32_t binding_count = std::min(
      observation.vertex_binding_count,
      rex::system::kGraphicsVertexBindingObservationLimit);
  for (uint32_t i = 0; i < binding_count; ++i) {
    const auto &binding = observation.vertex_bindings[i];
    for (uint32_t value : {binding.fetch_constant, binding.stride_words,
                           binding.endianness}) {
      hash = HashCombine(hash, value);
    }
  }
  const uint32_t attribute_count = std::min(
      observation.vertex_attribute_count,
      rex::system::kGraphicsVertexAttributeObservationLimit);
  for (uint32_t i = 0; i < attribute_count; ++i) {
    const auto &attribute = observation.vertex_attributes[i];
    for (uint64_t value :
         {uint64_t(attribute.binding_index),
          uint64_t(attribute.fetch_constant),
          uint64_t(uint32_t(attribute.offset_words)),
          uint64_t(attribute.stride_words), uint64_t(attribute.data_format),
          uint64_t(attribute.fetch_word_mask),
          uint64_t(uint32_t(attribute.exp_adjust)),
          uint64_t(attribute.signed_rf_mode),
          uint64_t(attribute.result_storage_target),
          uint64_t(attribute.result_storage_index),
          uint64_t(attribute.result_write_mask),
          uint64_t(attribute.result_components), uint64_t(attribute.flags)}) {
      hash = HashCombine(hash, value);
    }
  }
  return hash ? hash : 1;
}

uint64_t SemanticBatchTextureLayoutHash(
    const rex::system::GraphicsDrawObservation &observation) {
  uint64_t hash = UINT64_C(0xCBF29CE484222325);
  hash = HashCombine(hash, observation.texture_fetch_mask);
  hash = HashCombine(hash, observation.texture_fetch_layout_valid_mask);
  hash = HashCombine(hash, observation.texture_state_count);
  hash = HashCombine(hash, observation.texture_state_overflow);
  const uint32_t texture_count = std::min(
      observation.texture_state_count,
      rex::system::kGraphicsTextureFetchObservationLimit);
  for (uint32_t i = 0; i < texture_count; ++i) {
    const auto &state = observation.texture_states[i];
    for (uint32_t value :
         {state.stage, state.fetch_constant, state.opcode, state.dimension,
          state.filters, state.flags, state.lod_bias, state.offsets,
          state.result_storage_target, state.result_storage_index,
          state.result_write_mask, state.result_components}) {
      hash = HashCombine(hash, value);
    }
    for (uint32_t dword = 0; dword < std::size(state.dwords); ++dword) {
      uint32_t value = state.dwords[dword];
      if (dword == 1 || dword == 5) {
        value &= UINT32_C(0x00000FFF);
      }
      hash = HashCombine(hash, value);
    }
  }
  return hash ? hash : 1;
}

uint64_t SemanticBatchRenderStateHash(
    const rex::system::GraphicsDrawObservation &observation) {
  uint64_t hash = UINT64_C(0xCBF29CE484222325);
  for (uint64_t value :
       {observation.vertex_shader_hash, observation.pixel_shader_hash,
        uint64_t(observation.surface_info),
        uint64_t(observation.color_info[0] & UINT32_C(0xFFFF0000)),
        uint64_t(observation.color_info[1] & UINT32_C(0xFFFF0000)),
        uint64_t(observation.color_info[2] & UINT32_C(0xFFFF0000)),
        uint64_t(observation.color_info[3] & UINT32_C(0xFFFF0000)),
        uint64_t(observation.depth_info & UINT32_C(0xFFFF0000)),
        uint64_t(observation.rb_modecontrol),
        uint64_t(observation.rb_color_mask),
        uint64_t(observation.rb_blendcontrol[0]),
        uint64_t(observation.rb_blendcontrol[1]),
        uint64_t(observation.rb_blendcontrol[2]),
        uint64_t(observation.rb_blendcontrol[3]),
        uint64_t(observation.rb_depthcontrol),
        uint64_t(observation.pa_su_sc_mode_cntl),
        uint64_t(observation.pa_su_vtx_cntl),
        uint64_t(observation.vertex_float_constant_count),
        uint64_t(observation.vertex_float_constant_overflow),
        uint64_t(observation.pixel_float_constant_count),
        uint64_t(observation.pixel_float_constant_overflow),
        uint64_t(observation.loop_constant_bitmap)}) {
    hash = HashCombine(hash, value);
  }
  for (uint32_t value : observation.bool_constant_bitmap) {
    hash = HashCombine(hash, value);
  }
  return hash ? hash : 1;
}

uint64_t SemanticDrawArgumentHash(
    const rex::system::GraphicsDrawObservation &observation) {
  uint64_t hash = UINT64_C(0xCBF29CE484222325);
  for (uint64_t value :
       {uint64_t(observation.index_count),
        uint64_t(observation.vertex_index_offset),
        uint64_t(observation.vertex_index_min),
        uint64_t(observation.vertex_index_max),
        uint64_t(observation.index_reset)}) {
    hash = HashCombine(hash, value);
  }
  return hash ? hash : 1;
}

uint64_t SemanticRenderTargetResourceHash(
    const rex::system::GraphicsDrawObservation &observation) {
  uint64_t hash = UINT64_C(0xCBF29CE484222325);
  for (uint32_t color_info : observation.color_info) {
    hash = HashCombine(hash, color_info & UINT32_C(0x00000FFF));
  }
  hash = HashCombine(hash,
                     observation.depth_info & UINT32_C(0x00000FFF));
  return hash ? hash : 1;
}

uint64_t SemanticInstanceParameterHash(
    const rex::system::GraphicsDrawObservation &observation) {
  uint64_t hash = UINT64_C(0xCBF29CE484222325);
  const uint32_t vertex_count = std::min(
      observation.vertex_float_constant_count,
      rex::system::kGraphicsFloatConstantObservationLimit);
  for (uint32_t i = 0; i < vertex_count; ++i) {
    const auto &constant = observation.vertex_float_constants[i];
    hash = HashCombine(hash, constant.index);
    for (uint32_t value : constant.values) {
      hash = HashCombine(hash, value);
    }
  }
  const uint32_t pixel_count = std::min(
      observation.pixel_float_constant_count,
      rex::system::kGraphicsFloatConstantObservationLimit);
  for (uint32_t i = 0; i < pixel_count; ++i) {
    const auto &constant = observation.pixel_float_constants[i];
    hash = HashCombine(hash, constant.index);
    for (uint32_t value : constant.values) {
      hash = HashCombine(hash, value);
    }
  }
  for (uint32_t i = 0; i < std::size(observation.bool_constant_bitmap); ++i) {
    hash = HashCombine(hash, observation.bool_constant_bitmap[i]);
    hash = HashCombine(hash, observation.bool_constant_values[i] &
                                 observation.bool_constant_bitmap[i]);
  }
  hash = HashCombine(hash, observation.loop_constant_bitmap);
  for (uint32_t i = 0; i < std::size(observation.loop_constant_values); ++i) {
    if (observation.loop_constant_bitmap & (uint32_t(1) << i)) {
      hash = HashCombine(hash, observation.loop_constant_values[i]);
    }
  }
  return hash ? hash : 1;
}

uint64_t SemanticInstanceParameterPayloadBytes(
    const rex::system::GraphicsDrawObservation &observation) {
  const uint64_t vertex_count = std::min(
      observation.vertex_float_constant_count,
      rex::system::kGraphicsFloatConstantObservationLimit);
  const uint64_t pixel_count = std::min(
      observation.pixel_float_constant_count,
      rex::system::kGraphicsFloatConstantObservationLimit);
  uint64_t bytes =
      (vertex_count + pixel_count) * 5 * sizeof(uint32_t);
  for (uint32_t bitmap : observation.bool_constant_bitmap) {
    bytes += bitmap ? 2 * sizeof(uint32_t) : 0;
  }
  bytes += observation.loop_constant_bitmap ? sizeof(uint32_t) : 0;
  bytes += std::popcount(observation.loop_constant_bitmap) *
           sizeof(uint32_t);
  return bytes;
}

uint64_t SemanticRenderStateHash(
    const rex::system::GraphicsDrawObservation &observation) {
  uint64_t hash = UINT64_C(0xCBF29CE484222325);
  for (uint64_t value :
       {observation.vertex_shader_hash, observation.pixel_shader_hash,
        uint64_t(observation.surface_info),
        uint64_t(observation.color_info[0]),
        uint64_t(observation.color_info[1]),
        uint64_t(observation.color_info[2]),
        uint64_t(observation.color_info[3]),
        uint64_t(observation.depth_info),
        uint64_t(observation.rb_modecontrol),
        uint64_t(observation.rb_color_mask),
        uint64_t(observation.rb_blendcontrol[0]),
        uint64_t(observation.rb_blendcontrol[1]),
        uint64_t(observation.rb_blendcontrol[2]),
        uint64_t(observation.rb_blendcontrol[3]),
        uint64_t(observation.rb_depthcontrol),
        uint64_t(observation.pa_su_sc_mode_cntl),
        uint64_t(observation.pa_su_vtx_cntl),
        uint64_t(observation.vertex_float_constant_count),
        uint64_t(observation.vertex_float_constant_overflow),
        uint64_t(observation.pixel_float_constant_count),
        uint64_t(observation.pixel_float_constant_overflow),
        uint64_t(observation.loop_constant_bitmap)}) {
    hash = HashCombine(hash, value);
  }
  for (uint32_t value : observation.bool_constant_bitmap) {
    hash = HashCombine(hash, value);
  }
  return hash ? hash : 1;
}

uint64_t SemanticGeometryResourceHash(
    const rex::system::GraphicsDrawObservation &observation) {
  uint64_t hash = UINT64_C(0xCBF29CE484222325);
  hash = HashCombine(hash, observation.index_buffer_address);
  hash = HashCombine(hash, observation.index_buffer_length);
  const uint32_t binding_count = std::min(
      observation.vertex_binding_count,
      rex::system::kGraphicsVertexBindingObservationLimit);
  for (uint32_t i = 0; i < binding_count; ++i) {
    const auto &binding = observation.vertex_bindings[i];
    hash = HashCombine(hash, binding.address);
    hash = HashCombine(hash, binding.size);
  }
  return hash ? hash : 1;
}

uint64_t SemanticTextureResourceHash(
    const rex::system::GraphicsDrawObservation &observation) {
  uint64_t hash = UINT64_C(0xCBF29CE484222325);
  for (uint32_t fetch = 0; fetch < 32; ++fetch) {
    if (!(observation.texture_fetch_mask & (uint32_t(1) << fetch))) {
      continue;
    }
    hash = HashCombine(hash, fetch);
    hash = HashCombine(hash, observation.texture_fetch_addresses[fetch]);
    hash = HashCombine(hash, observation.texture_fetch_base_lengths[fetch]);
    hash = HashCombine(hash, observation.texture_fetch_mip_addresses[fetch]);
    hash = HashCombine(hash, observation.texture_fetch_mip_lengths[fetch]);
  }
  return hash ? hash : 1;
}

SemanticPreparedDrawContract BuildSemanticPreparedDrawContract(
    const rex::system::GraphicsDrawObservation &observation,
    const rex::system::GraphicsPreparedDrawObservation &prepared) {
  const uint32_t binding_count = std::min(
      observation.vertex_binding_count,
      rex::system::kGraphicsVertexBindingObservationLimit);
  const bool geometry_bounded =
      observation.index_count && observation.vertex_binding_count &&
      !observation.vertex_binding_overflow &&
      !observation.vertex_attribute_overflow &&
      (!observation.indexed ||
       (observation.index_buffer_address && observation.index_buffer_length));
  const bool texture_layout_bounded =
      !observation.texture_state_overflow &&
      (observation.texture_fetch_layout_valid_mask &
       observation.texture_fetch_mask) == observation.texture_fetch_mask;
  SemanticPreparedDrawContract contract{
      .draw_argument_hash = SemanticDrawArgumentHash(observation),
      .prepared_pipeline_hash = PreparedPipelineHash(prepared),
      .geometry_layout_hash = SemanticGeometryLayoutHash(observation),
      .texture_layout_hash = SemanticTextureLayoutHash(observation),
      .batch_geometry_layout_hash =
          SemanticBatchGeometryLayoutHash(observation),
      .batch_texture_layout_hash =
          SemanticBatchTextureLayoutHash(observation),
      .render_state_hash = SemanticRenderStateHash(observation),
      .geometry_resource_hash = SemanticGeometryResourceHash(observation),
      .texture_resource_hash = SemanticTextureResourceHash(observation),
      .render_target_resource_hash =
          SemanticRenderTargetResourceHash(observation),
      .vertex_shader_hash = prepared.vertex_shader_hash,
      .pixel_shader_hash = prepared.pixel_shader_hash,
      .vertex_specialization_mask = prepared.vertex_specialization_mask,
      .pixel_specialization_mask = prepared.pixel_specialization_mask,
      .primitive_type = observation.primitive_type,
      .source_select = observation.source_select,
      .minimum_index_count = observation.index_count,
      .maximum_index_count = observation.index_count,
      .index_buffer_address = observation.index_buffer_address,
      .index_buffer_length = observation.index_buffer_length,
      .index_format = observation.index_format,
      .index_endianness = observation.index_endianness,
      .vertex_binding_count = observation.vertex_binding_count,
      .vertex_attribute_count = observation.vertex_attribute_count,
      .texture_fetch_mask = observation.texture_fetch_mask,
      .texture_layout_valid_mask =
          observation.texture_fetch_layout_valid_mask,
      .texture_state_count = observation.texture_state_count,
      .indexed = observation.indexed,
      .geometry_bounded = geometry_bounded,
      .texture_layout_bounded = texture_layout_bounded,
      .valid = true,
  };
  if (binding_count) {
    const auto &binding = observation.vertex_bindings[0];
    contract.first_vertex_address = binding.address;
    contract.first_vertex_size = binding.size;
    contract.first_vertex_stride_words = binding.stride_words;
    contract.first_vertex_endianness = binding.endianness;
  }
  uint64_t template_key = UINT64_C(0xCBF29CE484222325);
  template_key = HashCombine(template_key, contract.prepared_pipeline_hash);
  template_key = HashCombine(template_key, contract.geometry_layout_hash);
  template_key = HashCombine(template_key, contract.texture_layout_hash);
  template_key = HashCombine(template_key, contract.render_state_hash);
  template_key = HashCombine(template_key, contract.vertex_shader_hash);
  template_key = HashCombine(template_key, contract.pixel_shader_hash);
  template_key =
      HashCombine(template_key, contract.vertex_specialization_mask);
  template_key = HashCombine(template_key, contract.pixel_specialization_mask);
  template_key = HashCombine(template_key, contract.primitive_type);
  template_key = HashCombine(template_key, contract.source_select);
  template_key = HashCombine(template_key, contract.indexed ? 1 : 0);
  template_key = HashCombine(template_key, contract.index_format);
  template_key = HashCombine(template_key, contract.index_endianness);
  template_key = HashCombine(template_key, contract.vertex_binding_count);
  template_key = HashCombine(template_key, contract.vertex_attribute_count);
  template_key = HashCombine(template_key, contract.first_vertex_stride_words);
  template_key = HashCombine(template_key, contract.first_vertex_endianness);
  template_key = HashCombine(template_key, contract.texture_fetch_mask);
  template_key = HashCombine(template_key, contract.texture_layout_valid_mask);
  template_key = HashCombine(template_key, contract.texture_state_count);
  contract.template_key = template_key ? template_key : 1;
  uint64_t batch_pipeline_key = UINT64_C(0xCBF29CE484222325);
  batch_pipeline_key =
      HashCombine(batch_pipeline_key, contract.prepared_pipeline_hash);
  batch_pipeline_key =
      HashCombine(batch_pipeline_key, contract.batch_geometry_layout_hash);
  batch_pipeline_key =
      HashCombine(batch_pipeline_key, contract.batch_texture_layout_hash);
  batch_pipeline_key = HashCombine(
      batch_pipeline_key, SemanticBatchRenderStateHash(observation));
  batch_pipeline_key =
      HashCombine(batch_pipeline_key, contract.vertex_shader_hash);
  batch_pipeline_key =
      HashCombine(batch_pipeline_key, contract.pixel_shader_hash);
  batch_pipeline_key =
      HashCombine(batch_pipeline_key, contract.vertex_specialization_mask);
  batch_pipeline_key =
      HashCombine(batch_pipeline_key, contract.pixel_specialization_mask);
  contract.batch_pipeline_key = batch_pipeline_key ? batch_pipeline_key : 1;
  return contract;
}

void UpdateSemanticPreparedDrawContract(
    SemanticPreparedDrawContract &contract,
    const rex::system::GraphicsDrawObservation &observation,
    const rex::system::GraphicsPreparedDrawObservation &prepared) {
  const SemanticPreparedDrawContract current =
      BuildSemanticPreparedDrawContract(observation, prepared);
  if (!contract.valid) {
    contract = current;
    return;
  }
  if (contract.template_key != current.template_key ||
      contract.prepared_pipeline_hash != current.prepared_pipeline_hash ||
      contract.geometry_layout_hash != current.geometry_layout_hash ||
      contract.texture_layout_hash != current.texture_layout_hash ||
      contract.render_state_hash != current.render_state_hash ||
      contract.vertex_shader_hash != current.vertex_shader_hash ||
      contract.pixel_shader_hash != current.pixel_shader_hash ||
      contract.vertex_specialization_mask !=
          current.vertex_specialization_mask ||
      contract.pixel_specialization_mask !=
          current.pixel_specialization_mask) {
    ++contract.template_variations;
  }
  if (contract.geometry_resource_hash != current.geometry_resource_hash ||
      contract.texture_resource_hash != current.texture_resource_hash ||
      contract.render_target_resource_hash !=
          current.render_target_resource_hash) {
    ++contract.resource_variations;
  }
  contract.minimum_index_count =
      std::min(contract.minimum_index_count, current.minimum_index_count);
  contract.maximum_index_count =
      std::max(contract.maximum_index_count, current.maximum_index_count);
  contract.geometry_bounded &= current.geometry_bounded;
  contract.texture_layout_bounded &= current.texture_layout_bounded;
}

void RecordTitleDrawProvenance(
    uint64_t backend_signature, bool prepared, uint32_t backend_outcome,
    const rex::system::GraphicsDrawObservation &observation,
    const TitleDrawOrigin &origin,
    const rex::system::GraphicsPreparedDrawObservation *prepared_observation =
        nullptr) {
  if (!origin.valid) {
    return;
  }
  if (origin.semantic_draw.valid) {
    (prepared ? g_semantic_draw_prepared_matches
              : g_semantic_draw_unprepared_matches)
        .fetch_add(1, std::memory_order_relaxed);
  }
  const SemanticPreparedDrawContract current_semantic_contract =
      origin.semantic_draw.valid && prepared_observation
          ? BuildSemanticPreparedDrawContract(observation,
                                              *prepared_observation)
          : SemanticPreparedDrawContract{};
  uint64_t key = backend_signature ^ (uint64_t(origin.caller) << 17) ^
                 (uint64_t(origin.wrapper) << 57) ^
                 (uint64_t(backend_outcome) << 41) ^
                 (prepared ? uint64_t(1) << 63 : 0);
  key = HashCombine(key, origin.semantic_draw.submission_key);
  key = HashCombine(key, current_semantic_contract.template_key);
  size_t index = size_t(key % kTitleDrawProvenanceCapacity);
  for (size_t probe = 0; probe < kTitleDrawProvenanceCapacity; ++probe) {
    TitleDrawProvenanceEntry &entry = g_title_draw_provenance[index];
    if (!entry.calls) {
      entry.backend_signature = backend_signature;
      entry.backend_outcome = backend_outcome;
      entry.calls = 1;
      entry.first_frame = observation.frame_sequence;
      entry.last_frame = observation.frame_sequence;
      entry.first_draw = observation.draw_sequence;
      entry.first_packet_physical_address =
          observation.packet_physical_address;
      entry.origin = origin;
      entry.last_arguments = origin.arguments;
      entry.minimum_arguments = origin.arguments;
      entry.maximum_arguments = origin.arguments;
      entry.prepared = prepared;
      if (current_semantic_contract.valid) {
        entry.semantic_contract = current_semantic_contract;
      }
      ++g_title_draw_provenance_count;
      return;
    }
    if (entry.backend_signature == backend_signature &&
        entry.backend_outcome == backend_outcome &&
        entry.prepared == prepared &&
        entry.origin.wrapper == origin.wrapper &&
        entry.origin.caller == origin.caller &&
        entry.origin.semantic_draw.submission_key ==
            origin.semantic_draw.submission_key &&
        entry.origin.semantic_draw.receiver_address ==
            origin.semantic_draw.receiver_address &&
        entry.origin.semantic_draw.receiver_generation ==
            origin.semantic_draw.receiver_generation &&
        entry.origin.semantic_draw.record_index ==
            origin.semantic_draw.record_index &&
        entry.semantic_contract.template_key ==
            current_semantic_contract.template_key) {
      ++entry.calls;
      entry.last_frame = observation.frame_sequence;
      for (size_t i = 0; i < origin.arguments.size(); ++i) {
        if (entry.last_arguments[i] != origin.arguments[i]) {
          entry.varying_argument_mask |= uint32_t(1) << i;
        }
        entry.last_arguments[i] = origin.arguments[i];
        entry.minimum_arguments[i] =
            std::min(entry.minimum_arguments[i], origin.arguments[i]);
        entry.maximum_arguments[i] =
            std::max(entry.maximum_arguments[i], origin.arguments[i]);
      }
      if (origin.semantic_draw.valid && prepared_observation) {
        UpdateSemanticPreparedDrawContract(entry.semantic_contract,
                                           observation,
                                           *prepared_observation);
      }
      return;
    }
    index = (index + 1) % kTitleDrawProvenanceCapacity;
  }
  ++g_title_draw_provenance_overflow;
}

void EmitTitleDrawProvenanceSummary() {
  if (!g_title_provenance_installed.exchange(false,
                                              std::memory_order_acq_rel)) {
    g_title_provenance_memory.store(nullptr, std::memory_order_release);
    return;
  }
  uint64_t prepared_matches = 0;
  uint64_t unprepared_matches = 0;
  uint64_t prepared_aggregate_count = 0;
  uint64_t unprepared_aggregate_count = 0;
  uint64_t semantic_contract_entries = 0;
  uint64_t semantic_contract_calls = 0;
  uint64_t semantic_bounded_geometry_calls = 0;
  uint64_t semantic_bounded_texture_calls = 0;
  uint64_t semantic_stable_template_calls = 0;
  uint64_t semantic_stable_resource_calls = 0;
  uint64_t semantic_template_variations = 0;
  uint64_t semantic_resource_variations = 0;
  for (const TitleDrawProvenanceEntry &entry : g_title_draw_provenance) {
    if (!entry.calls) {
      continue;
    }
    if (entry.prepared) {
      prepared_matches += entry.calls;
      ++prepared_aggregate_count;
    } else {
      unprepared_matches += entry.calls;
      ++unprepared_aggregate_count;
    }
    const SemanticPreparedDrawContract &semantic_contract =
        entry.semantic_contract;
    if (semantic_contract.valid) {
      ++semantic_contract_entries;
      semantic_contract_calls += entry.calls;
      semantic_bounded_geometry_calls +=
          semantic_contract.geometry_bounded ? entry.calls : 0;
      semantic_bounded_texture_calls +=
          semantic_contract.texture_layout_bounded ? entry.calls : 0;
      semantic_stable_template_calls +=
          !semantic_contract.template_variations ? entry.calls : 0;
      semantic_stable_resource_calls +=
          !semantic_contract.resource_variations ? entry.calls : 0;
      semantic_template_variations += semantic_contract.template_variations;
      semantic_resource_variations += semantic_contract.resource_variations;
    }
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.discovery.title_provenance_entry",
        {{"origin_wrapper", DispatchWrapperName(entry.origin.wrapper)},
         {"origin_wrapper_address",
          DispatchWrapperAddress(entry.origin.wrapper)},
         {"origin_caller", fmt::format("{:08X}", entry.origin.caller)},
         {"outcome", entry.prepared ? "prepared" : "not_prepared"},
         {"backend_outcome",
          entry.prepared ? "prepared_callback"
                         : DrawOutcomeName(entry.backend_outcome)},
         {"backend_signature",
          fmt::format("{:016X}", entry.backend_signature)},
         {"prepared_signature",
          entry.prepared ? fmt::format("{:016X}", entry.backend_signature)
                         : ""},
         {"semantic_template_key",
          semantic_contract.valid
              ? fmt::format("{:016X}", semantic_contract.template_key)
              : ""},
         {"semantic_batch_pipeline_key",
          semantic_contract.valid
              ? fmt::format("{:016X}",
                            semantic_contract.batch_pipeline_key)
              : ""},
         {"semantic_draw_argument_hash",
          semantic_contract.valid
              ? fmt::format("{:016X}",
                            semantic_contract.draw_argument_hash)
              : ""},
         {"semantic_prepared_pipeline_hash",
          semantic_contract.valid
              ? fmt::format("{:016X}",
                            semantic_contract.prepared_pipeline_hash)
              : ""},
         {"semantic_geometry_layout_hash",
          semantic_contract.valid
              ? fmt::format("{:016X}", semantic_contract.geometry_layout_hash)
              : ""},
         {"semantic_texture_layout_hash",
          semantic_contract.valid
              ? fmt::format("{:016X}", semantic_contract.texture_layout_hash)
              : ""},
         {"semantic_batch_geometry_layout_hash",
          semantic_contract.valid
              ? fmt::format(
                    "{:016X}",
                    semantic_contract.batch_geometry_layout_hash)
              : ""},
         {"semantic_batch_texture_layout_hash",
          semantic_contract.valid
              ? fmt::format("{:016X}",
                            semantic_contract.batch_texture_layout_hash)
              : ""},
         {"semantic_render_state_hash",
          semantic_contract.valid
              ? fmt::format("{:016X}", semantic_contract.render_state_hash)
              : ""},
         {"semantic_geometry_resource_hash",
          semantic_contract.valid
              ? fmt::format("{:016X}",
                            semantic_contract.geometry_resource_hash)
              : ""},
         {"semantic_texture_resource_hash",
          semantic_contract.valid
              ? fmt::format("{:016X}",
                            semantic_contract.texture_resource_hash)
              : ""},
         {"semantic_render_target_resource_hash",
          semantic_contract.valid
              ? fmt::format(
                    "{:016X}",
                    semantic_contract.render_target_resource_hash)
              : ""},
         {"semantic_vertex_shader",
          semantic_contract.valid
              ? fmt::format("{:016X}", semantic_contract.vertex_shader_hash)
              : ""},
         {"semantic_pixel_shader",
          semantic_contract.valid
              ? fmt::format("{:016X}", semantic_contract.pixel_shader_hash)
              : ""},
         {"semantic_vertex_specialization",
          semantic_contract.valid
              ? fmt::format("{:016X}",
                            semantic_contract.vertex_specialization_mask)
              : ""},
         {"semantic_pixel_specialization",
          semantic_contract.valid
              ? fmt::format("{:016X}",
                            semantic_contract.pixel_specialization_mask)
              : ""},
         {"semantic_primitive_type",
          semantic_contract.valid
              ? std::to_string(semantic_contract.primitive_type)
              : ""},
         {"semantic_source_select",
          semantic_contract.valid
              ? std::to_string(semantic_contract.source_select)
              : ""},
         {"semantic_indexed",
          semantic_contract.valid
              ? (semantic_contract.indexed ? "true" : "false")
              : ""},
         {"semantic_minimum_index_count",
          semantic_contract.valid
              ? std::to_string(semantic_contract.minimum_index_count)
              : ""},
         {"semantic_maximum_index_count",
          semantic_contract.valid
              ? std::to_string(semantic_contract.maximum_index_count)
              : ""},
         {"semantic_index_buffer_address",
          semantic_contract.valid
              ? fmt::format("{:08X}",
                            semantic_contract.index_buffer_address)
              : ""},
         {"semantic_index_buffer_length",
          semantic_contract.valid
              ? std::to_string(semantic_contract.index_buffer_length)
              : ""},
         {"semantic_index_format",
          semantic_contract.valid
              ? std::to_string(semantic_contract.index_format)
              : ""},
         {"semantic_index_endianness",
          semantic_contract.valid
              ? std::to_string(semantic_contract.index_endianness)
              : ""},
         {"semantic_vertex_binding_count",
          semantic_contract.valid
              ? std::to_string(semantic_contract.vertex_binding_count)
              : ""},
         {"semantic_vertex_attribute_count",
          semantic_contract.valid
              ? std::to_string(semantic_contract.vertex_attribute_count)
              : ""},
         {"semantic_first_vertex_address",
          semantic_contract.valid
              ? fmt::format("{:08X}",
                            semantic_contract.first_vertex_address)
              : ""},
         {"semantic_first_vertex_size",
          semantic_contract.valid
              ? std::to_string(semantic_contract.first_vertex_size)
              : ""},
         {"semantic_first_vertex_stride_words",
          semantic_contract.valid
              ? std::to_string(
                    semantic_contract.first_vertex_stride_words)
              : ""},
         {"semantic_first_vertex_endianness",
          semantic_contract.valid
              ? std::to_string(semantic_contract.first_vertex_endianness)
              : ""},
         {"semantic_texture_fetch_mask",
          semantic_contract.valid
              ? fmt::format("{:08X}",
                            semantic_contract.texture_fetch_mask)
              : ""},
         {"semantic_texture_layout_valid_mask",
          semantic_contract.valid
              ? fmt::format("{:08X}",
                            semantic_contract.texture_layout_valid_mask)
              : ""},
         {"semantic_texture_state_count",
          semantic_contract.valid
              ? std::to_string(semantic_contract.texture_state_count)
              : ""},
         {"semantic_geometry_bounded",
          semantic_contract.valid
              ? (semantic_contract.geometry_bounded ? "true" : "false")
              : ""},
         {"semantic_texture_layout_bounded",
          semantic_contract.valid
              ? (semantic_contract.texture_layout_bounded ? "true" : "false")
              : ""},
         {"semantic_template_variations",
          semantic_contract.valid
              ? std::to_string(semantic_contract.template_variations)
              : ""},
         {"semantic_resource_variations",
          semantic_contract.valid
              ? std::to_string(semantic_contract.resource_variations)
              : ""},
         {"semantic_catalog_classification",
          semantic_contract.valid
              ? "immutable_template_and_dynamic_resource_instance"
              : "unavailable"},
         {"calls", std::to_string(entry.calls)},
         {"first_frame", std::to_string(entry.first_frame)},
         {"last_frame", std::to_string(entry.last_frame)},
         {"first_draw", std::to_string(entry.first_draw)},
         {"first_packet_physical_address",
          fmt::format("{:08X}", entry.first_packet_physical_address)},
         {"semantic_submission_key",
          entry.origin.semantic_draw.valid
              ? fmt::format("{:016X}",
                            entry.origin.semantic_draw.submission_key)
              : ""},
         {"semantic_receiver_address",
          entry.origin.semantic_draw.valid
              ? fmt::format("{:08X}",
                            entry.origin.semantic_draw.receiver_address)
              : ""},
         {"semantic_receiver_generation",
          entry.origin.semantic_draw.valid
              ? std::to_string(
                    entry.origin.semantic_draw.receiver_generation)
              : ""},
         {"semantic_record_index",
          entry.origin.semantic_draw.valid
              ? std::to_string(entry.origin.semantic_draw.record_index)
              : ""},
         {"semantic_descriptor_address",
          entry.origin.semantic_draw.valid
              ? fmt::format("{:08X}",
                            entry.origin.semantic_draw.descriptor_address)
              : ""},
         {"semantic_runtime_address",
          entry.origin.semantic_draw.valid
              ? fmt::format("{:08X}",
                            entry.origin.semantic_draw.runtime_address)
              : ""},
         {"semantic_draw_association",
          entry.origin.semantic_draw.valid
              ? "exact_render_item_scope_and_physical_pm4_header"
              : "none"},
         {"first_r3", fmt::format("{:08X}", entry.origin.arguments[0])},
         {"first_r4", fmt::format("{:08X}", entry.origin.arguments[1])},
         {"first_r5", fmt::format("{:08X}", entry.origin.arguments[2])},
         {"first_r6", fmt::format("{:08X}", entry.origin.arguments[3])},
         {"first_r7", fmt::format("{:08X}", entry.origin.arguments[4])},
         {"first_r8", fmt::format("{:08X}", entry.origin.arguments[5])},
         {"first_r9", fmt::format("{:08X}", entry.origin.arguments[6])},
         {"first_r10", fmt::format("{:08X}", entry.origin.arguments[7])},
         {"last_arguments",
          fmt::format("{:08X}:{:08X}:{:08X}:{:08X}:{:08X}:{:08X}:{:08X}:{:08X}",
                      entry.last_arguments[0], entry.last_arguments[1],
                      entry.last_arguments[2], entry.last_arguments[3],
                      entry.last_arguments[4], entry.last_arguments[5],
                      entry.last_arguments[6], entry.last_arguments[7])},
         {"minimum_arguments",
          fmt::format("{:08X}:{:08X}:{:08X}:{:08X}:{:08X}:{:08X}:{:08X}:{:08X}",
                      entry.minimum_arguments[0], entry.minimum_arguments[1],
                      entry.minimum_arguments[2], entry.minimum_arguments[3],
                      entry.minimum_arguments[4], entry.minimum_arguments[5],
                      entry.minimum_arguments[6], entry.minimum_arguments[7])},
         {"maximum_arguments",
          fmt::format("{:08X}:{:08X}:{:08X}:{:08X}:{:08X}:{:08X}:{:08X}:{:08X}",
                      entry.maximum_arguments[0], entry.maximum_arguments[1],
                      entry.maximum_arguments[2], entry.maximum_arguments[3],
                      entry.maximum_arguments[4], entry.maximum_arguments[5],
                      entry.maximum_arguments[6], entry.maximum_arguments[7])},
         {"varying_argument_mask",
          fmt::format("{:02X}", entry.varying_argument_mask)},
         {"semantic_identity",
          entry.origin.semantic_draw.valid
              ? "procedural_model_submission"
              : "unknown"},
         {"xenos_draw", "preserved"},
         {"suppression_eligible", "false"}});
  }
  uint64_t pending_packets = 0;
  uint64_t semantic_pending_packets = 0;
  {
    std::scoped_lock lock(g_title_packet_provenance_mutex);
    for (const TitlePacketProvenanceEntry &entry :
         g_title_packet_provenance) {
      pending_packets += entry.occupied ? 1 : 0;
      semantic_pending_packets +=
          entry.occupied && entry.origin.semantic_draw.valid ? 1 : 0;
    }
  }
  const bool packet_accounting_complete =
      g_title_packets_recorded == g_title_packets_matched + pending_packets;
  const uint64_t origins_pushed =
      g_title_origins_pushed.load(std::memory_order_relaxed);
  const uint64_t origins_consumed =
      g_title_origins_consumed.load(std::memory_order_relaxed);
  const uint64_t semantic_scope_joins =
      g_semantic_draw_scope_joins.load(std::memory_order_relaxed);
  const uint64_t semantic_scope_mismatches =
      g_semantic_draw_scope_mismatches.load(std::memory_order_relaxed);
  const uint64_t semantic_origins =
      g_semantic_draw_origins_captured.load(std::memory_order_relaxed);
  const uint64_t semantic_dispatches_with_direct_title_origin =
      g_semantic_draw_dispatches_with_direct_title_origin.load(
          std::memory_order_relaxed);
  const uint64_t semantic_dispatches_without_direct_title_origin =
      g_semantic_draw_dispatches_without_direct_title_origin.load(
          std::memory_order_relaxed);
  const uint64_t semantic_indirect_packet_origins =
      g_semantic_draw_indirect_packet_origins_captured.load(
          std::memory_order_relaxed);
  const uint64_t semantic_dispatches_with_indirect_packet_origin =
      g_semantic_draw_dispatches_with_indirect_packet_origin.load(
          std::memory_order_relaxed);
  const uint64_t semantic_dispatches_without_indirect_packet_origin =
      g_semantic_draw_dispatches_without_indirect_packet_origin.load(
          std::memory_order_relaxed);
  const uint64_t semantic_packets =
      g_semantic_draw_packets_recorded.load(std::memory_order_relaxed);
  const uint64_t semantic_packet_matches =
      g_semantic_draw_packet_matches.load(std::memory_order_relaxed);
  const uint64_t semantic_prepared_matches =
      g_semantic_draw_prepared_matches.load(std::memory_order_relaxed);
  const uint64_t semantic_unprepared_matches =
      g_semantic_draw_unprepared_matches.load(std::memory_order_relaxed);
  const uint64_t semantic_render_item_entries =
      g_semantic_render_item_entries.load(std::memory_order_relaxed);
  const uint64_t semantic_render_item_exits =
      g_semantic_render_item_exits.load(std::memory_order_relaxed);
  const uint64_t semantic_render_items_open =
      g_semantic_render_items_open.load(std::memory_order_relaxed);
  const uint64_t semantic_render_item_stack_faults =
      g_semantic_render_item_stack_faults.load(std::memory_order_relaxed);
  const bool semantic_draw_overlap_probe_accounting_complete =
      semantic_scope_joins == g_semantic_submission_live_observations &&
      semantic_scope_joins ==
          semantic_dispatches_with_direct_title_origin +
              semantic_dispatches_without_direct_title_origin &&
      semantic_scope_joins ==
          semantic_dispatches_with_indirect_packet_origin +
              semantic_dispatches_without_indirect_packet_origin &&
      semantic_render_item_entries ==
          semantic_render_item_exits + semantic_render_items_open &&
      !semantic_render_item_stack_faults && !semantic_scope_mismatches;
  const bool semantic_draw_accounting_complete =
      semantic_draw_overlap_probe_accounting_complete &&
      !semantic_dispatches_without_direct_title_origin &&
      semantic_origins >= semantic_scope_joins &&
      semantic_packets == semantic_origins &&
      semantic_packets == semantic_packet_matches + semantic_pending_packets &&
      semantic_packet_matches ==
          semantic_prepared_matches + semantic_unprepared_matches &&
      semantic_render_item_entries ==
          semantic_render_item_exits + semantic_render_items_open;
  uint64_t title_backend_outcomes = 0;
  for (size_t outcome = 1; outcome < g_backend_draw_outcome_counts.size();
       ++outcome) {
    const uint64_t backend_draws = g_backend_draw_outcome_counts[outcome];
    const uint64_t title_matches = g_title_backend_outcome_counts[outcome];
    title_backend_outcomes += title_matches;
    if (!backend_draws && !title_matches) {
      continue;
    }
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.discovery.title_provenance_outcome",
        {{"backend_outcome", DrawOutcomeName(uint32_t(outcome))},
         {"backend_draws", std::to_string(backend_draws)},
         {"title_matches", std::to_string(title_matches)},
         {"xenos_authority", "true"},
         {"suppression_allowed", "false"}});
  }
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.discovery.title_provenance_summary",
      {{"title_packets_recorded", std::to_string(g_title_packets_recorded)},
       {"backend_packet_matches", std::to_string(g_title_packets_matched)},
       {"prepared_matches", std::to_string(prepared_matches)},
       {"matched_unprepared_draws",
        std::to_string(g_title_matched_unprepared_draws)},
       {"backend_draw_outcomes_observed",
        std::to_string(g_backend_draw_outcomes_observed)},
       {"backend_draw_outcome_mismatches",
        std::to_string(g_backend_draw_outcome_mismatches)},
       {"backend_draw_outcome_missing",
        std::to_string(g_backend_draw_outcome_missing)},
       {"title_backend_outcomes",
        std::to_string(title_backend_outcomes)},
       {"pending_packets", std::to_string(pending_packets)},
       {"semantic_submission_live_observations",
        std::to_string(g_semantic_submission_live_observations)},
       {"semantic_render_item_entries",
        std::to_string(semantic_render_item_entries)},
       {"semantic_render_item_exits",
        std::to_string(semantic_render_item_exits)},
       {"semantic_render_items_open_at_shutdown",
        std::to_string(semantic_render_items_open)},
       {"semantic_render_item_valid_scopes",
        std::to_string(g_semantic_render_item_valid_scopes.load(
            std::memory_order_relaxed))},
       {"semantic_render_item_scopes_without_submission",
        std::to_string(
            g_semantic_render_item_scopes_without_submission.load(
                std::memory_order_relaxed))},
       {"semantic_render_item_stack_faults",
        std::to_string(semantic_render_item_stack_faults)},
       {"semantic_draw_scope_joins",
        std::to_string(semantic_scope_joins)},
       {"semantic_draw_scope_mismatches",
        std::to_string(semantic_scope_mismatches)},
       {"semantic_draw_origins_captured",
        std::to_string(semantic_origins)},
       {"semantic_draw_dispatches_with_direct_title_origin",
        std::to_string(semantic_dispatches_with_direct_title_origin)},
       {"semantic_draw_dispatches_without_direct_title_origin",
        std::to_string(semantic_dispatches_without_direct_title_origin)},
       {"semantic_draw_overlap_probe_accounting_complete",
        semantic_draw_overlap_probe_accounting_complete ? "true" : "false"},
       {"semantic_draw_indirect_packet_origins_captured",
        std::to_string(semantic_indirect_packet_origins)},
       {"semantic_draw_dispatches_with_indirect_packet_origin",
        std::to_string(semantic_dispatches_with_indirect_packet_origin)},
       {"semantic_draw_dispatches_without_indirect_packet_origin",
        std::to_string(semantic_dispatches_without_indirect_packet_origin)},
       {"semantic_draw_packets_recorded",
        std::to_string(semantic_packets)},
       {"semantic_draw_packet_matches",
        std::to_string(semantic_packet_matches)},
       {"semantic_draw_prepared_matches",
        std::to_string(semantic_prepared_matches)},
       {"semantic_draw_unprepared_matches",
        std::to_string(semantic_unprepared_matches)},
       {"semantic_draw_pending_packets",
        std::to_string(semantic_pending_packets)},
       {"semantic_draw_accounting_complete",
        semantic_draw_accounting_complete ? "true" : "false"},
       {"semantic_contract_entries",
        std::to_string(semantic_contract_entries)},
       {"semantic_contract_calls", std::to_string(semantic_contract_calls)},
       {"semantic_bounded_geometry_calls",
        std::to_string(semantic_bounded_geometry_calls)},
       {"semantic_bounded_texture_calls",
        std::to_string(semantic_bounded_texture_calls)},
       {"semantic_stable_template_calls",
        std::to_string(semantic_stable_template_calls)},
       {"semantic_stable_resource_calls",
        std::to_string(semantic_stable_resource_calls)},
       {"semantic_template_variations",
        std::to_string(semantic_template_variations)},
       {"semantic_resource_variations",
        std::to_string(semantic_resource_variations)},
       {"semantic_catalog_accounting_complete",
        semantic_contract_calls == semantic_prepared_matches ? "true"
                                                              : "false"},
       {"backend_draws_without_title_packet",
        std::to_string(g_title_backend_unattributed_draws)},
       {"packet_address_failures",
        std::to_string(g_title_packet_address_failures)},
       {"reused_live_packet_addresses",
        std::to_string(g_title_packet_reused_live_addresses)},
       {"packet_table_overflow",
        std::to_string(g_title_packet_table_overflow)},
       {"forwarding_mismatches",
        std::to_string(
            g_title_forwarding_mismatches.load(std::memory_order_relaxed))},
       {"origins_pushed", std::to_string(origins_pushed)},
       {"origins_consumed", std::to_string(origins_consumed)},
       {"origin_stack_overflow",
        std::to_string(
            g_title_origin_stack_overflow.load(std::memory_order_relaxed))},
       {"packets_without_origin",
        std::to_string(
            g_title_packets_without_origin.load(std::memory_order_relaxed))},
       {"origin_accounting_complete",
        origins_pushed == origins_consumed ? "true" : "false"},
       {"aggregate_count", std::to_string(g_title_draw_provenance_count)},
       {"prepared_aggregate_count",
        std::to_string(prepared_aggregate_count)},
       {"unprepared_aggregate_count",
        std::to_string(unprepared_aggregate_count)},
       {"unprepared_aggregate_matches",
        std::to_string(unprepared_matches)},
       {"aggregate_overflow",
        std::to_string(g_title_draw_provenance_overflow)},
       {"packet_capacity", std::to_string(kTitlePacketProvenanceCapacity)},
       {"aggregate_capacity", std::to_string(kTitleDrawProvenanceCapacity)},
       {"origin_stack_capacity", std::to_string(kTitleOriginStackCapacity)},
       {"packet_accounting_complete",
        packet_accounting_complete ? "true" : "false"},
       {"correlation", "exact_physical_pm4_header_address"},
       {"semantic_identity", "direct_procedural_packet_overlap_probe"},
       {"guest_payload_read", "false"},
       {"guest_state_changed", "false"},
       {"control_flow_changed", "false"},
       {"xenos_authority", "true"},
       {"suppression_allowed", "false"}});
  g_title_provenance_memory.store(nullptr, std::memory_order_release);
}

bool IsOpaqueColorState(
    const rex::system::GraphicsDrawObservation &observation) {
  bool writes_color = false;
  for (uint32_t i = 0; i < 4; ++i) {
    if (!(observation.rb_color_mask & (uint32_t(0xF) << (i * 4)))) {
      continue;
    }
    writes_color = true;
    if (observation.rb_blendcontrol[i] != 0x00010001) {
      return false;
    }
  }
  return writes_color;
}

bool IsMechanicallyEligibleCandidate(const DrawSignatureEntry &entry) {
  const auto &observation = entry.sample;
  const bool query_draw = observation.viz_query_condition ||
                          (observation.pa_sc_viz_query & 1);
  const uint32_t texture_count =
      std::popcount(observation.texture_fetch_mask);
  return IsOpaqueColorState(observation) && !query_draw &&
         !observation.vertex_memexport && !entry.samples_resolved_target &&
         !observation.vertex_binding_overflow &&
         !observation.vertex_attribute_overflow &&
         !observation.vertex_float_constant_overflow &&
         !observation.pixel_float_constant_overflow &&
         !observation.texture_state_overflow &&
         observation.vertex_binding_count == 1 && texture_count >= 1 &&
         texture_count <= 4;
}

enum IsolatedDrawMechanicalRejection : uint32_t {
  kIsolatedRejectResolvedInput = 1u << 0,
  kIsolatedRejectUnsupportedGeometry = 1u << 1,
  kIsolatedRejectEmptyDraw = 1u << 2,
  kIsolatedRejectVertexBindingCount = 1u << 3,
  kIsolatedRejectVertexBindingOverflow = 1u << 4,
  kIsolatedRejectVertexAttributeOverflow = 1u << 5,
  kIsolatedRejectVertexConstantOverflow = 1u << 6,
  kIsolatedRejectPixelConstantOverflow = 1u << 7,
  kIsolatedRejectTextureStateOverflow = 1u << 8,
  kIsolatedRejectMemexport = 1u << 9,
  kIsolatedRejectQuery = 1u << 10,
  kIsolatedRejectTextureCount = 1u << 11,
  kIsolatedRejectTextureLayout = 1u << 12,
  kIsolatedRejectPreparedPipeline = 1u << 13,
  kIsolatedRejectRenderTargets = 1u << 14,
};

uint32_t IsolatedDrawMechanicalRejectionMask(
    const rex::system::GraphicsDrawObservation &observation,
    bool samples_resolved_target,
    const rex::system::GraphicsPreparedDrawObservation &prepared) {
  const uint32_t texture_count =
      std::popcount(observation.texture_fetch_mask);
  const bool supported_geometry =
      (observation.indexed &&
       observation.source_select ==
           uint32_t(rex::graphics::xenos::SourceSelect::kDMA) &&
       observation.index_format <= 1 && observation.index_endianness <= 3 &&
       prepared.index_buffer_type == 1) ||
      (!observation.indexed &&
       observation.source_select ==
           uint32_t(rex::graphics::xenos::SourceSelect::kAutoIndex) &&
       prepared.index_buffer_type == 0);
  uint32_t mask = 0;
  mask |= samples_resolved_target ? kIsolatedRejectResolvedInput : 0;
  mask |= !supported_geometry ? kIsolatedRejectUnsupportedGeometry : 0;
  mask |= !observation.index_count ? kIsolatedRejectEmptyDraw : 0;
  mask |= observation.vertex_binding_count != 1
              ? kIsolatedRejectVertexBindingCount
              : 0;
  mask |= observation.vertex_binding_overflow
              ? kIsolatedRejectVertexBindingOverflow
              : 0;
  mask |= observation.vertex_attribute_overflow
              ? kIsolatedRejectVertexAttributeOverflow
              : 0;
  mask |= observation.vertex_float_constant_overflow
              ? kIsolatedRejectVertexConstantOverflow
              : 0;
  mask |= observation.pixel_float_constant_overflow
              ? kIsolatedRejectPixelConstantOverflow
              : 0;
  mask |= observation.texture_state_overflow
              ? kIsolatedRejectTextureStateOverflow
              : 0;
  mask |= observation.vertex_memexport ? kIsolatedRejectMemexport : 0;
  mask |= observation.viz_query_condition || (observation.pa_sc_viz_query & 1)
              ? kIsolatedRejectQuery
              : 0;
  mask |= texture_count < 1 || texture_count > 4
              ? kIsolatedRejectTextureCount
              : 0;
  mask |= (observation.texture_fetch_layout_valid_mask &
           observation.texture_fetch_mask) != observation.texture_fetch_mask
              ? kIsolatedRejectTextureLayout
              : 0;
  mask |= (prepared.flags & 3) != 3 ? kIsolatedRejectPreparedPipeline : 0;
  mask |= prepared.bound_render_target_bits != 3
              ? kIsolatedRejectRenderTargets
              : 0;
  return mask;
}

bool IsIsolatedDrawEligible(
    const rex::system::GraphicsDrawObservation &observation,
    bool samples_resolved_target,
    const rex::system::GraphicsPreparedDrawObservation &prepared) {
  return !IsolatedDrawMechanicalRejectionMask(
      observation, samples_resolved_target, prepared);
}

const char *SemanticBatchRejectionName(SemanticBatchRejection rejection) {
  switch (rejection) {
  case SemanticBatchRejection::kNone:
    return "none";
  case SemanticBatchRejection::kMissingTitleResource:
    return "missing_title_resource";
  case SemanticBatchRejection::kNonOpaque:
    return "non_opaque";
  case SemanticBatchRejection::kResolvedInput:
    return "resolved_input";
  case SemanticBatchRejection::kQueryOrConditional:
    return "query_or_conditional";
  case SemanticBatchRejection::kMemexport:
    return "memexport";
  case SemanticBatchRejection::kUnboundedGeometry:
    return "unbounded_geometry";
  case SemanticBatchRejection::kUnsupportedGeometry:
    return "unsupported_geometry";
  case SemanticBatchRejection::kConstantOverflow:
    return "constant_overflow";
  case SemanticBatchRejection::kUnboundedTextureLayout:
    return "unbounded_texture_layout";
  case SemanticBatchRejection::kTextureCount:
    return "texture_count";
  case SemanticBatchRejection::kIncompletePreparedPipeline:
    return "incomplete_prepared_pipeline";
  case SemanticBatchRejection::kRenderTargetCoverage:
    return "render_target_coverage";
  case SemanticBatchRejection::kCount:
    break;
  }
  return "unknown";
}

SemanticBatchRejection ClassifySemanticBatchRejection(
    const rex::system::GraphicsDrawObservation &observation,
    bool samples_resolved_target,
    const rex::system::GraphicsPreparedDrawObservation &prepared,
    const SemanticDrawIdentity &identity,
    const SemanticPreparedDrawContract &contract) {
  if (!identity.primary_resource_key) {
    return SemanticBatchRejection::kMissingTitleResource;
  }
  if (!IsOpaqueColorState(observation)) {
    return SemanticBatchRejection::kNonOpaque;
  }
  if (samples_resolved_target) {
    return SemanticBatchRejection::kResolvedInput;
  }
  if (observation.viz_query_condition || (observation.pa_sc_viz_query & 1)) {
    return SemanticBatchRejection::kQueryOrConditional;
  }
  if (observation.vertex_memexport) {
    return SemanticBatchRejection::kMemexport;
  }
  if (!contract.geometry_bounded || observation.vertex_binding_count != 1) {
    return SemanticBatchRejection::kUnboundedGeometry;
  }
  const bool supported_geometry =
      (observation.indexed &&
       observation.source_select ==
           uint32_t(rex::graphics::xenos::SourceSelect::kDMA) &&
       observation.index_format <= 1 && observation.index_endianness <= 3 &&
       prepared.index_buffer_type == 1) ||
      (!observation.indexed &&
       observation.source_select ==
           uint32_t(rex::graphics::xenos::SourceSelect::kAutoIndex) &&
       prepared.index_buffer_type == 0);
  if (!supported_geometry) {
    return SemanticBatchRejection::kUnsupportedGeometry;
  }
  if (observation.vertex_float_constant_overflow ||
      observation.pixel_float_constant_overflow) {
    return SemanticBatchRejection::kConstantOverflow;
  }
  if (!contract.texture_layout_bounded) {
    return SemanticBatchRejection::kUnboundedTextureLayout;
  }
  const uint32_t texture_count = std::popcount(observation.texture_fetch_mask);
  if (texture_count < 1 || texture_count > 4) {
    return SemanticBatchRejection::kTextureCount;
  }
  if ((prepared.flags & 3) != 3) {
    return SemanticBatchRejection::kIncompletePreparedPipeline;
  }
  if (prepared.bound_render_target_bits != 3) {
    return SemanticBatchRejection::kRenderTargetCoverage;
  }
  return SemanticBatchRejection::kNone;
}

void FinalizeSemanticBatchFrame() {
  if (!g_semantic_batch_current_frame) {
    return;
  }
  ++g_semantic_batch_frame_count;
  g_semantic_batch_maximum_draws_per_frame =
      std::max(g_semantic_batch_maximum_draws_per_frame,
               g_semantic_batch_current_frame_draws);
  g_semantic_batch_current_frame = 0;
  g_semantic_batch_current_frame_draws = 0;
}

void FinalizeSemanticBatchRun() {
  if (!g_semantic_batch_run.valid) {
    return;
  }
  SemanticBatchOpportunityEntry &entry =
      g_semantic_batch_opportunities[g_semantic_batch_run.opportunity_index];
  ++entry.consecutive_runs;
  entry.maximum_run_length =
      std::max(entry.maximum_run_length, g_semantic_batch_run.length);
  ++g_semantic_batch_consecutive_runs;
  g_semantic_batch_maximum_run_length =
      std::max(g_semantic_batch_maximum_run_length,
               g_semantic_batch_run.length);
  if (g_semantic_batch_run.length > 1) {
    ++entry.multi_draw_runs;
    entry.multi_draw_draws += g_semantic_batch_run.length;
    ++g_semantic_batch_multi_draw_runs;
    g_semantic_batch_multi_draw_draws += g_semantic_batch_run.length;
  }
  g_semantic_batch_run = {};
}

size_t FindOrCreateSemanticBatchOpportunity(
    uint64_t key, const SemanticPreparedDrawContract &contract,
    const SemanticDrawIdentity &identity, SemanticBatchRejection rejection) {
  size_t index = size_t(key % kSemanticBatchOpportunityCapacity);
  for (size_t probe = 0; probe < kSemanticBatchOpportunityCapacity; ++probe) {
    SemanticBatchOpportunityEntry &entry =
        g_semantic_batch_opportunities[index];
    if (!entry.key) {
      entry.key = key;
      entry.template_key = contract.template_key;
      entry.geometry_resource_hash = contract.geometry_resource_hash;
      entry.texture_resource_hash = contract.texture_resource_hash;
      entry.primary_resource_key = identity.primary_resource_key;
      entry.secondary_resource_key = identity.secondary_resource_key;
      entry.secondary_resource_present = identity.secondary_resource_present;
      entry.rejection = rejection;
      ++g_semantic_batch_opportunity_count;
      return index;
    }
    if (entry.key == key && entry.template_key == contract.template_key &&
        entry.geometry_resource_hash == contract.geometry_resource_hash &&
        entry.texture_resource_hash == contract.texture_resource_hash &&
        entry.primary_resource_key == identity.primary_resource_key &&
        entry.secondary_resource_key == identity.secondary_resource_key &&
        entry.secondary_resource_present ==
            identity.secondary_resource_present &&
        entry.rejection == rejection) {
      return index;
    }
    index = (index + 1) % kSemanticBatchOpportunityCapacity;
  }
  ++g_semantic_batch_opportunity_overflow;
  return kSemanticBatchOpportunityCapacity;
}

const char *SemanticBatchEquivalenceName(
    SemanticBatchEquivalence equivalence) {
  switch (equivalence) {
  case SemanticBatchEquivalence::kMeshMaterial:
    return "mesh_material_instance";
  case SemanticBatchEquivalence::kMaterial:
    return "material_state_reuse";
  case SemanticBatchEquivalence::kPipeline:
    return "pipeline_state_reuse";
  case SemanticBatchEquivalence::kCount:
    break;
  }
  return "unknown";
}

const char *SemanticStateCacheLevelName(SemanticStateCacheLevel level) {
  switch (level) {
  case SemanticStateCacheLevel::kMaterial:
    return "material_state";
  case SemanticStateCacheLevel::kPipeline:
    return "pipeline_state";
  case SemanticStateCacheLevel::kCount:
    break;
  }
  return "unknown";
}

const char *SemanticStateCacheProfileName(
    SemanticStateCacheProfile profile) {
  switch (profile) {
  case SemanticStateCacheProfile::kCompact:
    return "compact";
  case SemanticStateCacheProfile::kBalanced:
    return "balanced";
  case SemanticStateCacheProfile::kHeadroom:
    return "headroom";
  case SemanticStateCacheProfile::kCount:
    break;
  }
  return "unknown";
}

size_t SemanticStateCacheBucketCount(
    SemanticStateCacheProfile profile) {
  switch (profile) {
  case SemanticStateCacheProfile::kCompact:
    return kSemanticStateCacheCompactBucketCount;
  case SemanticStateCacheProfile::kBalanced:
    return kSemanticStateCacheBalancedBucketCount;
  case SemanticStateCacheProfile::kHeadroom:
    return kSemanticStateCacheHeadroomBucketCount;
  case SemanticStateCacheProfile::kCount:
    break;
  }
  return 0;
}

uint64_t SemanticStateCacheKey(
    SemanticStateCacheLevel level,
    const SemanticPreparedDrawContract &contract) {
  uint64_t key = UINT64_C(0xCBF29CE484222325);
  key = HashCombine(key, contract.batch_pipeline_key);
  if (level == SemanticStateCacheLevel::kMaterial) {
    key = HashCombine(key, contract.texture_resource_hash);
    key = HashCombine(key, contract.render_target_resource_hash);
  }
  return key ? key : 1;
}

void BreakSemanticStateCacheContinuity() {
  for (auto &level : g_semantic_state_cache_stats) {
    for (SemanticStateCacheStats &stats : level) {
      stats.previous_valid = false;
    }
  }
}

void RecordSemanticStateCacheLookup(
    SemanticStateCacheLevel level, SemanticStateCacheProfile profile,
    uint64_t frame,
    const SemanticPreparedDrawContract &contract) {
  const size_t level_index = size_t(level);
  const size_t profile_index = size_t(profile);
  SemanticStateCacheStats &stats =
      g_semantic_state_cache_stats[level_index][profile_index];
  auto &cache = g_semantic_state_caches[level_index][profile_index];
  const uint64_t key = SemanticStateCacheKey(level, contract);
  const size_t bucket_count = SemanticStateCacheBucketCount(profile);
  const size_t bucket = size_t(key % bucket_count);
  const size_t first_way = bucket * kSemanticStateCacheWays;
  size_t hit_index = kSemanticStateCacheMaximumCapacity;
  size_t empty_index = kSemanticStateCacheMaximumCapacity;
  size_t least_recent_index = first_way;
  uint64_t least_recent_sequence = UINT64_MAX;
  for (size_t way = 0; way < kSemanticStateCacheWays; ++way) {
    const size_t index = first_way + way;
    const SemanticStateCacheEntry &entry = cache[index];
    if (entry.key == key) {
      hit_index = index;
      break;
    }
    if (!entry.key &&
        empty_index == kSemanticStateCacheMaximumCapacity) {
      empty_index = index;
    }
    if (entry.key && entry.last_use_sequence < least_recent_sequence) {
      least_recent_sequence = entry.last_use_sequence;
      least_recent_index = index;
    }
  }

  ++stats.lookups;
  ++stats.use_sequence;
  if (hit_index != kSemanticStateCacheMaximumCapacity) {
    ++stats.hits;
    SemanticStateCacheEntry &entry = cache[hit_index];
    if (stats.previous_valid && stats.previous_frame == frame &&
        stats.previous_key == key) {
      ++stats.consecutive_hits;
    } else if (entry.last_frame == frame) {
      ++stats.nonconsecutive_same_frame_hits;
    } else {
      ++stats.cross_frame_hits;
    }
    entry.last_use_sequence = stats.use_sequence;
    entry.last_frame = frame;
  } else {
    ++stats.misses;
    size_t insert_index = empty_index;
    if (insert_index == kSemanticStateCacheMaximumCapacity) {
      insert_index = least_recent_index;
      ++stats.full_bucket_misses;
      ++stats.evictions;
    } else {
      ++stats.resident_entries;
      stats.maximum_resident_entries =
          std::max(stats.maximum_resident_entries,
                   stats.resident_entries);
    }
    cache[insert_index] = {
        .key = key,
        .last_use_sequence = stats.use_sequence,
        .last_frame = frame,
    };
  }
  stats.previous_key = key;
  stats.previous_frame = frame;
  stats.previous_valid = true;
}

void RecordSemanticStateCacheLookups(
    uint64_t frame, const SemanticPreparedDrawContract &contract) {
  for (size_t level = 0;
       level < size_t(SemanticStateCacheLevel::kCount); ++level) {
    for (size_t profile = 0;
         profile < size_t(SemanticStateCacheProfile::kCount); ++profile) {
      RecordSemanticStateCacheLookup(
          SemanticStateCacheLevel(level),
          SemanticStateCacheProfile(profile), frame, contract);
    }
  }
}

void FinalizeSemanticBatchEquivalenceRun(
    SemanticBatchEquivalence equivalence) {
  const size_t level = size_t(equivalence);
  SemanticBatchEquivalenceRun &run =
      g_semantic_batch_equivalence_runs[level];
  if (!run.valid) {
    return;
  }
  SemanticBatchEquivalenceEntry &entry =
      g_semantic_batch_equivalence_opportunities[level]
                                                [run.opportunity_index];
  ++entry.consecutive_runs;
  entry.maximum_run_length = std::max(entry.maximum_run_length, run.length);
  if (run.length > 1) {
    ++entry.multi_draw_runs;
    entry.multi_draw_draws += run.length;
  }
  run = {};
}

void FinalizeSemanticBatchEquivalenceRuns() {
  for (size_t level = 0;
       level < size_t(SemanticBatchEquivalence::kCount); ++level) {
    FinalizeSemanticBatchEquivalenceRun(
        SemanticBatchEquivalence(level));
  }
}

size_t FindOrCreateSemanticBatchEquivalenceOpportunity(
    SemanticBatchEquivalence equivalence, uint64_t key,
    const SemanticPreparedDrawContract &contract) {
  const size_t level = size_t(equivalence);
  const uint64_t draw_argument_hash =
      equivalence == SemanticBatchEquivalence::kMeshMaterial
          ? contract.draw_argument_hash
          : 0;
  const uint64_t geometry_resource_hash =
      equivalence == SemanticBatchEquivalence::kMeshMaterial
          ? contract.geometry_resource_hash
          : 0;
  const uint64_t texture_resource_hash =
      equivalence != SemanticBatchEquivalence::kPipeline
          ? contract.texture_resource_hash
          : 0;
  const uint64_t render_target_resource_hash =
      equivalence != SemanticBatchEquivalence::kPipeline
          ? contract.render_target_resource_hash
          : 0;
  size_t index = size_t(key % kSemanticBatchOpportunityCapacity);
  for (size_t probe = 0; probe < kSemanticBatchOpportunityCapacity; ++probe) {
    SemanticBatchEquivalenceEntry &entry =
        g_semantic_batch_equivalence_opportunities[level][index];
    if (!entry.key) {
      entry.key = key;
      entry.pipeline_key = contract.batch_pipeline_key;
      entry.draw_argument_hash = draw_argument_hash;
      entry.geometry_resource_hash = geometry_resource_hash;
      entry.texture_resource_hash = texture_resource_hash;
      entry.render_target_resource_hash = render_target_resource_hash;
      ++g_semantic_batch_equivalence_counts[level];
      return index;
    }
    if (entry.key == key &&
        entry.pipeline_key == contract.batch_pipeline_key &&
        entry.draw_argument_hash == draw_argument_hash &&
        entry.geometry_resource_hash == geometry_resource_hash &&
        entry.texture_resource_hash == texture_resource_hash &&
        entry.render_target_resource_hash == render_target_resource_hash) {
      return index;
    }
    index = (index + 1) % kSemanticBatchOpportunityCapacity;
  }
  ++g_semantic_batch_equivalence_overflows[level];
  return kSemanticBatchOpportunityCapacity;
}

void RecordSemanticBatchEquivalenceOpportunity(
    SemanticBatchEquivalence equivalence,
    const rex::system::GraphicsDrawObservation &observation,
    const SemanticPreparedDrawContract &contract,
    const SemanticDrawIdentity &identity, uint64_t parameter_hash) {
  uint64_t key = UINT64_C(0xCBF29CE484222325);
  key = HashCombine(key, contract.batch_pipeline_key);
  if (equivalence == SemanticBatchEquivalence::kMeshMaterial) {
    key = HashCombine(key, contract.draw_argument_hash);
    key = HashCombine(key, contract.geometry_resource_hash);
  }
  if (equivalence != SemanticBatchEquivalence::kPipeline) {
    key = HashCombine(key, contract.texture_resource_hash);
    key = HashCombine(key, contract.render_target_resource_hash);
  }
  key = key ? key : 1;
  const size_t opportunity_index =
      FindOrCreateSemanticBatchEquivalenceOpportunity(equivalence, key,
                                                      contract);
  const size_t level = size_t(equivalence);
  if (opportunity_index == kSemanticBatchOpportunityCapacity) {
    FinalizeSemanticBatchEquivalenceRun(equivalence);
    return;
  }
  SemanticBatchEquivalenceEntry &entry =
      g_semantic_batch_equivalence_opportunities[level][opportunity_index];
  ++entry.draws;
  if (!entry.first_frame) {
    entry.first_frame = observation.frame_sequence;
  }
  if (entry.last_frame != observation.frame_sequence) {
    ++entry.frames;
  }
  entry.last_frame = observation.frame_sequence;

  SemanticBatchEquivalenceRun &run =
      g_semantic_batch_equivalence_runs[level];
  if (run.valid && run.frame == observation.frame_sequence &&
      run.key == key) {
    const bool same_instance =
        run.receiver_address == identity.receiver_address &&
        run.receiver_generation == identity.receiver_generation &&
        run.record_index == identity.record_index;
    if (same_instance) {
      ++entry.same_instance_continuations;
    } else {
      ++entry.instance_switches;
    }
    if (run.parameter_hash == parameter_hash) {
      ++entry.same_parameter_continuations;
    } else {
      ++entry.parameter_switches;
    }
    ++run.length;
    run.parameter_hash = parameter_hash;
    run.receiver_address = identity.receiver_address;
    run.receiver_generation = identity.receiver_generation;
    run.record_index = identity.record_index;
    return;
  }
  FinalizeSemanticBatchEquivalenceRun(equivalence);
  run = {
      .key = key,
      .frame = observation.frame_sequence,
      .length = 1,
      .parameter_hash = parameter_hash,
      .opportunity_index = opportunity_index,
      .receiver_address = identity.receiver_address,
      .receiver_generation = identity.receiver_generation,
      .record_index = identity.record_index,
      .valid = true,
  };
}

bool RecordSemanticVisibilityPreparedCandidate(
    const rex::system::GraphicsDrawObservation &observation,
    const SemanticDrawIdentity &identity,
    const SemanticPreparedDrawContract &contract,
    uint64_t prepared_signature, uint32_t mechanical_rejection_mask) {
  ++g_semantic_visibility_prepared_observations;
  if (identity.visibility_workset_join ==
      SemanticVisibilityWorksetJoin::kMissing) {
    ++g_semantic_visibility_prepared_missing_exclusions;
    return false;
  }
  if (identity.visibility_workset_join ==
      SemanticVisibilityWorksetJoin::kRejected) {
    ++g_semantic_visibility_prepared_rejected_exclusions;
    return false;
  }

  ++g_semantic_visibility_prepared_selected_joins;
  if (observation.frame_sequence < identity.visibility_policy_frame) {
    ++g_semantic_visibility_prepared_future_exclusions;
    return false;
  }
  const uint64_t policy_age_frames =
      observation.frame_sequence - identity.visibility_policy_frame;
  if (policy_age_frames > kSemanticVisibilityMaximumPolicyAgeFrames) {
    ++g_semantic_visibility_prepared_stale_exclusions;
    return false;
  }
  ++g_semantic_visibility_prepared_fresh_candidates;

  uint64_t key = UINT64_C(0xCBF29CE484222325);
  for (uint64_t value :
       {uint64_t(identity.receiver_address),
        uint64_t(identity.receiver_generation),
        uint64_t(identity.record_index), contract.template_key,
        contract.geometry_resource_hash, contract.texture_resource_hash,
        prepared_signature,
        uint64_t(identity.visibility_category),
        uint64_t(identity.visibility_result_mask),
        uint64_t(identity.title_lod_valid),
        uint64_t(identity.title_lod_index),
        uint64_t(mechanical_rejection_mask)}) {
    key = HashCombine(key, value);
  }
  key = key ? key : 1;
  size_t index =
      size_t(key % kSemanticVisibilityPreparedCandidateCapacity);
  for (size_t probe = 0;
       probe < kSemanticVisibilityPreparedCandidateCapacity; ++probe) {
    SemanticVisibilityPreparedCandidateEntry &entry =
        g_semantic_visibility_prepared_candidates[index];
    if (!entry.key) {
      entry = {
          .key = key,
          .prepared_signature = prepared_signature,
          .template_key = contract.template_key,
          .geometry_resource_hash = contract.geometry_resource_hash,
          .texture_resource_hash = contract.texture_resource_hash,
          .draws = 1,
          .first_frame = observation.frame_sequence,
          .last_frame = observation.frame_sequence,
          .maximum_policy_age_frames = policy_age_frames,
          .vertex_shader_hash = contract.vertex_shader_hash,
          .pixel_shader_hash = contract.pixel_shader_hash,
          .vertex_specialization_mask =
              contract.vertex_specialization_mask,
          .pixel_specialization_mask = contract.pixel_specialization_mask,
          .receiver_address = identity.receiver_address,
          .receiver_generation = identity.receiver_generation,
          .record_index = identity.record_index,
          .visibility_category = identity.visibility_category,
          .visibility_result_mask = identity.visibility_result_mask,
          .title_lod_index = identity.title_lod_index,
          .mechanical_rejection_mask = mechanical_rejection_mask,
          .mechanically_eligible = !mechanical_rejection_mask,
          .title_lod_valid = identity.title_lod_valid,
      };
      ++g_semantic_visibility_prepared_candidate_count;
      return true;
    }
    if (entry.key == key &&
        entry.prepared_signature == prepared_signature &&
        entry.template_key == contract.template_key &&
        entry.geometry_resource_hash == contract.geometry_resource_hash &&
        entry.texture_resource_hash == contract.texture_resource_hash &&
        entry.vertex_shader_hash == contract.vertex_shader_hash &&
        entry.pixel_shader_hash == contract.pixel_shader_hash &&
        entry.vertex_specialization_mask ==
            contract.vertex_specialization_mask &&
        entry.pixel_specialization_mask ==
            contract.pixel_specialization_mask &&
        entry.mechanical_rejection_mask == mechanical_rejection_mask &&
        entry.receiver_address == identity.receiver_address &&
        entry.receiver_generation == identity.receiver_generation &&
        entry.record_index == identity.record_index &&
        entry.visibility_category == identity.visibility_category &&
        entry.visibility_result_mask == identity.visibility_result_mask &&
        entry.title_lod_index == identity.title_lod_index &&
        entry.title_lod_valid == identity.title_lod_valid) {
      ++entry.draws;
      entry.last_frame = observation.frame_sequence;
      entry.maximum_policy_age_frames =
          std::max(entry.maximum_policy_age_frames, policy_age_frames);
      return true;
    }
    index =
        (index + 1) % kSemanticVisibilityPreparedCandidateCapacity;
  }
  ++g_semantic_visibility_prepared_candidate_overflow;
  return false;
}

struct SemanticVisibilityPreparedAdmission {
  bool fresh = false;
  bool title_lod_valid = false;
  uint32_t title_lod_index = 0;
};

SemanticVisibilityPreparedAdmission RecordSemanticBatchOpportunity(
    const rex::system::GraphicsDrawObservation &observation,
    bool samples_resolved_target,
    const rex::system::GraphicsPreparedDrawObservation &prepared,
    const TitleDrawOrigin &origin, uint64_t prepared_signature) {
  if (!origin.semantic_draw.valid) {
    return {};
  }
  const SemanticDrawIdentity &identity = origin.semantic_draw;
  const SemanticPreparedDrawContract contract =
      BuildSemanticPreparedDrawContract(observation, prepared);
  const uint32_t mechanical_rejection_mask =
      IsolatedDrawMechanicalRejectionMask(
      observation, samples_resolved_target, prepared);
  const bool fresh_visibility_candidate =
      RecordSemanticVisibilityPreparedCandidate(observation, identity,
                                                contract, prepared_signature,
                                                 mechanical_rejection_mask);
  const SemanticVisibilityPreparedAdmission visibility_admission = {
      .fresh = fresh_visibility_candidate,
      .title_lod_valid = fresh_visibility_candidate && identity.title_lod_valid,
      .title_lod_index = identity.title_lod_index,
  };
  const SemanticBatchRejection rejection =
      ClassifySemanticBatchRejection(observation, samples_resolved_target,
                                     prepared, identity, contract);
  const bool eligible = rejection == SemanticBatchRejection::kNone;
  ++g_semantic_batch_observations;
  if (g_semantic_batch_current_frame != observation.frame_sequence) {
    FinalizeSemanticBatchFrame();
    g_semantic_batch_current_frame = observation.frame_sequence;
  }
  ++g_semantic_batch_current_frame_draws;

  uint64_t key = UINT64_C(0xCBF29CE484222325);
  for (uint64_t value :
       {contract.template_key, contract.geometry_resource_hash,
        contract.texture_resource_hash, uint64_t(identity.primary_resource_key),
        uint64_t(identity.secondary_resource_present),
        uint64_t(identity.secondary_resource_key), uint64_t(rejection)}) {
    key = HashCombine(key, value);
  }
  key = key ? key : 1;
  const size_t opportunity_index = FindOrCreateSemanticBatchOpportunity(
      key, contract, identity, rejection);
  if (opportunity_index == kSemanticBatchOpportunityCapacity) {
    FinalizeSemanticBatchRun();
    FinalizeSemanticBatchEquivalenceRuns();
    BreakSemanticStateCacheContinuity();
    g_semantic_batch_previous_eligible = false;
    return visibility_admission;
  }
  SemanticBatchOpportunityEntry &entry =
      g_semantic_batch_opportunities[opportunity_index];
  ++entry.draws;
  if (!entry.first_frame) {
    entry.first_frame = observation.frame_sequence;
  }
  if (entry.last_frame != observation.frame_sequence) {
    ++entry.frames;
  }
  entry.last_frame = observation.frame_sequence;

  if (!eligible) {
    ++g_semantic_batch_rejected_draws;
    ++g_semantic_batch_rejections[size_t(rejection)];
    FinalizeSemanticBatchRun();
    FinalizeSemanticBatchEquivalenceRuns();
    BreakSemanticStateCacheContinuity();
    g_semantic_batch_previous_eligible = false;
    return visibility_admission;
  }
  ++g_semantic_batch_eligible_draws;
  const uint64_t parameter_hash =
      SemanticInstanceParameterHash(observation);
  const uint64_t parameter_payload_bytes =
      SemanticInstanceParameterPayloadBytes(observation);
  g_semantic_batch_parameter_payload_bytes += parameter_payload_bytes;
  g_semantic_batch_maximum_parameter_payload_bytes =
      std::max(g_semantic_batch_maximum_parameter_payload_bytes,
               parameter_payload_bytes);
  RecordSemanticStateCacheLookups(observation.frame_sequence, contract);
  for (size_t level = 0;
       level < size_t(SemanticBatchEquivalence::kCount); ++level) {
    RecordSemanticBatchEquivalenceOpportunity(
        SemanticBatchEquivalence(level), observation, contract, identity,
        parameter_hash);
  }
  if (g_semantic_batch_previous_eligible &&
      g_semantic_batch_previous_frame == observation.frame_sequence) {
    g_semantic_batch_template_transitions +=
        g_semantic_batch_previous_contract.template_key !=
        contract.template_key;
    g_semantic_batch_geometry_transitions +=
        g_semantic_batch_previous_contract.geometry_resource_hash !=
        contract.geometry_resource_hash;
    g_semantic_batch_texture_transitions +=
        g_semantic_batch_previous_contract.texture_resource_hash !=
        contract.texture_resource_hash;
    g_semantic_batch_title_resource_transitions +=
        g_semantic_batch_previous_identity.primary_resource_key !=
            identity.primary_resource_key ||
        g_semantic_batch_previous_identity.secondary_resource_present !=
            identity.secondary_resource_present ||
        g_semantic_batch_previous_identity.secondary_resource_key !=
            identity.secondary_resource_key;
  }
  g_semantic_batch_previous_contract = contract;
  g_semantic_batch_previous_identity = identity;
  g_semantic_batch_previous_frame = observation.frame_sequence;
  g_semantic_batch_previous_eligible = true;

  if (g_semantic_batch_run.valid &&
      g_semantic_batch_run.frame == observation.frame_sequence &&
      g_semantic_batch_run.key == key) {
    const bool same_instance =
        g_semantic_batch_run.receiver_address == identity.receiver_address &&
        g_semantic_batch_run.receiver_generation ==
            identity.receiver_generation &&
        g_semantic_batch_run.record_index == identity.record_index;
    if (same_instance) {
      ++entry.same_instance_continuations;
      ++g_semantic_batch_same_instance_continuations;
    } else {
      ++entry.instance_switches;
      ++g_semantic_batch_instance_switches;
    }
    ++g_semantic_batch_run.length;
    g_semantic_batch_run.receiver_address = identity.receiver_address;
    g_semantic_batch_run.receiver_generation = identity.receiver_generation;
    g_semantic_batch_run.record_index = identity.record_index;
    return visibility_admission;
  }
  FinalizeSemanticBatchRun();
  g_semantic_batch_run = {
      .key = key,
      .frame = observation.frame_sequence,
      .length = 1,
      .opportunity_index = opportunity_index,
      .receiver_address = identity.receiver_address,
      .receiver_generation = identity.receiver_generation,
      .record_index = identity.record_index,
      .valid = true,
  };
  return visibility_admission;
}

void EmitSemanticBatchEquivalenceSummary() {
  FinalizeSemanticBatchEquivalenceRuns();
  for (size_t level = 0;
       level < size_t(SemanticBatchEquivalence::kCount); ++level) {
    const SemanticBatchEquivalence equivalence =
        SemanticBatchEquivalence(level);
    uint64_t entry_draws = 0;
    uint64_t consecutive_runs = 0;
    uint64_t multi_draw_runs = 0;
    uint64_t multi_draw_draws = 0;
    uint64_t maximum_run_length = 0;
    uint64_t instance_switches = 0;
    uint64_t same_instance_continuations = 0;
    uint64_t parameter_switches = 0;
    uint64_t same_parameter_continuations = 0;
    for (const SemanticBatchEquivalenceEntry &entry :
         g_semantic_batch_equivalence_opportunities[level]) {
      if (!entry.key) {
        continue;
      }
      entry_draws += entry.draws;
      consecutive_runs += entry.consecutive_runs;
      multi_draw_runs += entry.multi_draw_runs;
      multi_draw_draws += entry.multi_draw_draws;
      maximum_run_length =
          std::max(maximum_run_length, entry.maximum_run_length);
      instance_switches += entry.instance_switches;
      same_instance_continuations += entry.same_instance_continuations;
      parameter_switches += entry.parameter_switches;
      same_parameter_continuations +=
          entry.same_parameter_continuations;
      pinyon_shift::diagnostics::RecordEvent(
          "native_renderer.discovery.semantic_batch_equivalence_entry",
          {{"equivalence", SemanticBatchEquivalenceName(equivalence)},
           {"opportunity_key", fmt::format("{:016X}", entry.key)},
           {"pipeline_key", fmt::format("{:016X}", entry.pipeline_key)},
           {"draw_argument_hash",
            entry.draw_argument_hash
                ? fmt::format("{:016X}", entry.draw_argument_hash)
                : ""},
           {"geometry_resource_hash",
            entry.geometry_resource_hash
                ? fmt::format("{:016X}", entry.geometry_resource_hash)
                : ""},
           {"texture_resource_hash",
            entry.texture_resource_hash
                ? fmt::format("{:016X}", entry.texture_resource_hash)
                : ""},
           {"render_target_resource_hash",
            entry.render_target_resource_hash
                ? fmt::format("{:016X}",
                              entry.render_target_resource_hash)
                : ""},
           {"draws", std::to_string(entry.draws)},
           {"frames", std::to_string(entry.frames)},
           {"first_frame", std::to_string(entry.first_frame)},
           {"last_frame", std::to_string(entry.last_frame)},
           {"consecutive_runs", std::to_string(entry.consecutive_runs)},
           {"multi_draw_runs", std::to_string(entry.multi_draw_runs)},
           {"multi_draw_draws", std::to_string(entry.multi_draw_draws)},
           {"maximum_run_length",
            std::to_string(entry.maximum_run_length)},
           {"instance_switches", std::to_string(entry.instance_switches)},
           {"same_instance_continuations",
            std::to_string(entry.same_instance_continuations)},
           {"parameter_switches", std::to_string(entry.parameter_switches)},
           {"same_parameter_continuations",
            std::to_string(entry.same_parameter_continuations)},
           {"ordering", "exact_consecutive_prepared_draw_order"},
           {"xenos_draw", "preserved"},
           {"native_batch", "false"},
           {"suppression_allowed", "false"}});
    }
    const bool accounting_complete =
        !g_semantic_batch_equivalence_overflows[level] &&
        entry_draws == g_semantic_batch_eligible_draws &&
        instance_switches + same_instance_continuations ==
            multi_draw_draws - multi_draw_runs &&
        parameter_switches + same_parameter_continuations ==
            multi_draw_draws - multi_draw_runs;
    const uint64_t potential_reduction =
        g_semantic_batch_eligible_draws >= consecutive_runs
            ? g_semantic_batch_eligible_draws - consecutive_runs
            : 0;
    const double reduction_percent = g_semantic_batch_eligible_draws
                                         ? 100.0 * potential_reduction /
                                               g_semantic_batch_eligible_draws
                                         : 0.0;
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.discovery.semantic_batch_equivalence_summary",
        {{"status", accounting_complete ? "complete" : "incomplete"},
         {"equivalence", SemanticBatchEquivalenceName(equivalence)},
         {"eligible_draws", std::to_string(g_semantic_batch_eligible_draws)},
         {"opportunity_entries",
          std::to_string(g_semantic_batch_equivalence_counts[level])},
         {"opportunity_overflow",
          std::to_string(g_semantic_batch_equivalence_overflows[level])},
         {"consecutive_runs", std::to_string(consecutive_runs)},
         {"multi_draw_runs", std::to_string(multi_draw_runs)},
         {"multi_draw_draws", std::to_string(multi_draw_draws)},
         {"maximum_run_length", std::to_string(maximum_run_length)},
         {"instance_switches", std::to_string(instance_switches)},
         {"same_instance_continuations",
          std::to_string(same_instance_continuations)},
         {"parameter_switches", std::to_string(parameter_switches)},
         {"same_parameter_continuations",
          std::to_string(same_parameter_continuations)},
         {"potential_reduction", std::to_string(potential_reduction)},
         {"potential_reduction_percent",
          fmt::format("{:.3f}", reduction_percent)},
         {"accounting_complete", accounting_complete ? "true" : "false"},
         {"identity",
          equivalence == SemanticBatchEquivalence::kMeshMaterial
              ? "pipeline,draw_arguments,geometry,texture,render_target"
              : (equivalence == SemanticBatchEquivalence::kMaterial
                     ? "pipeline,texture,render_target"
                     : "pipeline")},
         {"parameterization", "observed_not_executed"},
         {"ordering", "exact_consecutive_prepared_draw_order"},
         {"reordering", "false"},
         {"native_batch_execution", "false"},
         {"native_upload", "false"},
         {"native_draw", "false"},
         {"xenos_authority", "true"},
         {"suppression_allowed", "false"}});
  }
}

void EmitSemanticStateCacheSummary() {
  for (size_t level = 0;
       level < size_t(SemanticStateCacheLevel::kCount); ++level) {
    const SemanticStateCacheLevel cache_level =
        SemanticStateCacheLevel(level);
    for (size_t profile = 0;
         profile < size_t(SemanticStateCacheProfile::kCount); ++profile) {
      const SemanticStateCacheProfile cache_profile =
          SemanticStateCacheProfile(profile);
      const SemanticStateCacheStats &stats =
          g_semantic_state_cache_stats[level][profile];
      const size_t bucket_count =
          SemanticStateCacheBucketCount(cache_profile);
      const size_t capacity = bucket_count * kSemanticStateCacheWays;
      const bool accounting_complete =
          stats.lookups == g_semantic_batch_eligible_draws &&
          stats.hits + stats.misses == stats.lookups &&
          stats.consecutive_hits +
                  stats.nonconsecutive_same_frame_hits +
                  stats.cross_frame_hits ==
              stats.hits &&
          stats.evictions <= stats.misses &&
          stats.resident_entries <= capacity &&
          stats.maximum_resident_entries <= capacity;
      const uint64_t required_bindings =
          stats.lookups >= stats.consecutive_hits
              ? stats.lookups - stats.consecutive_hits
              : 0;
      const double hit_percent =
          stats.lookups ? 100.0 * stats.hits / stats.lookups : 0.0;
      const double bind_elision_percent =
          stats.lookups
              ? 100.0 * stats.consecutive_hits / stats.lookups
              : 0.0;
      pinyon_shift::diagnostics::RecordEvent(
          "native_renderer.discovery.semantic_state_cache_summary",
          {{"status", accounting_complete ? "complete" : "incomplete"},
           {"cache_level", SemanticStateCacheLevelName(cache_level)},
           {"cache_profile",
            SemanticStateCacheProfileName(cache_profile)},
           {"eligible_draws",
            std::to_string(g_semantic_batch_eligible_draws)},
           {"lookups", std::to_string(stats.lookups)},
           {"hits", std::to_string(stats.hits)},
           {"misses", std::to_string(stats.misses)},
           {"hit_percent", fmt::format("{:.3f}", hit_percent)},
           {"evictions", std::to_string(stats.evictions)},
           {"full_bucket_misses",
            std::to_string(stats.full_bucket_misses)},
           {"resident_entries", std::to_string(stats.resident_entries)},
           {"maximum_resident_entries",
            std::to_string(stats.maximum_resident_entries)},
           {"consecutive_hits",
            std::to_string(stats.consecutive_hits)},
           {"nonconsecutive_same_frame_hits",
            std::to_string(stats.nonconsecutive_same_frame_hits)},
           {"cross_frame_hits", std::to_string(stats.cross_frame_hits)},
           {"object_constructions", std::to_string(stats.misses)},
           {"object_constructions_avoided",
            std::to_string(stats.hits)},
           {"required_bindings", std::to_string(required_bindings)},
           {"binding_elisions",
            std::to_string(stats.consecutive_hits)},
           {"binding_elision_percent",
            fmt::format("{:.3f}", bind_elision_percent)},
           {"bucket_count", std::to_string(bucket_count)},
           {"ways", std::to_string(kSemanticStateCacheWays)},
           {"capacity", std::to_string(capacity)},
           {"policy", "set_associative_lru"},
           {"lifetime", "census_session"},
           {"accounting_complete",
            accounting_complete ? "true" : "false"},
           {"native_state_objects", "false"},
           {"native_bindings", "false"},
           {"native_draw", "false"},
           {"reordering", "false"},
           {"xenos_authority", "true"},
           {"suppression_allowed", "false"}});
    }
  }
}

const char *SemanticVisibilityPolicyOutcomeName(size_t outcome) {
  switch (SemanticVisibilityPolicyOutcome(outcome)) {
  case SemanticVisibilityPolicyOutcome::kEarlyRejected:
    return "early_rejected";
  case SemanticVisibilityPolicyOutcome::kRejected:
    return "rejected";
  case SemanticVisibilityPolicyOutcome::kSelected:
    return "selected";
  }
  return "unknown";
}

void EmitSemanticVisibilityCensus() {
  const uint64_t entries = g_semantic_visibility_record_entries.load(
      std::memory_order_relaxed);
  const uint64_t completions =
      g_semantic_visibility_record_completions.load(
          std::memory_order_relaxed);
  const uint64_t results =
      g_semantic_visibility_result_observations.load(
          std::memory_order_relaxed);
  const uint64_t selected =
      g_semantic_visibility_selected_records.load(
          std::memory_order_relaxed);
  const uint64_t rejected =
      g_semantic_visibility_rejected_records.load(
          std::memory_order_relaxed);
  const uint64_t early_rejected =
      g_semantic_visibility_early_rejected_records.load(
          std::memory_order_relaxed);
  const uint64_t lod_writes = g_semantic_visibility_lod_writes.load(
      std::memory_order_relaxed);
  uint64_t category_entries = 0;
  uint64_t category_completions = 0;
  uint64_t category_selected = 0;
  uint64_t category_rejected = 0;
  uint64_t category_early_rejected = 0;
  uint64_t category_lod_writes = 0;
  for (size_t index = 0; index < kSemanticVisibilityCategoryCapacity;
       ++index) {
    const SemanticVisibilityCategoryStats &category =
        g_semantic_visibility_categories[index];
    const uint64_t category_entry_count =
        category.entries.load(std::memory_order_relaxed);
    if (!category_entry_count) {
      continue;
    }
    const uint64_t category_completion_count =
        category.completions.load(std::memory_order_relaxed);
    const uint64_t category_selected_count =
        category.selected.load(std::memory_order_relaxed);
    const uint64_t category_rejected_count =
        category.rejected.load(std::memory_order_relaxed);
    const uint64_t category_early_rejected_count =
        category.early_rejected.load(std::memory_order_relaxed);
    const uint64_t category_lod_count =
        category.lod_writes.load(std::memory_order_relaxed);
    const bool category_complete =
        category_entry_count == category_completion_count &&
        category_completion_count == category_selected_count +
                                         category_rejected_count +
                                         category_early_rejected_count;
    category_entries += category_entry_count;
    category_completions += category_completion_count;
    category_selected += category_selected_count;
    category_rejected += category_rejected_count;
    category_early_rejected += category_early_rejected_count;
    category_lod_writes += category_lod_count;
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.discovery.semantic_visibility_category_summary",
        {{"status", category_complete ? "complete" : "incomplete"},
         {"category", std::to_string(index)},
         {"entries", std::to_string(category_entry_count)},
         {"completions", std::to_string(category_completion_count)},
         {"selected", std::to_string(category_selected_count)},
         {"rejected", std::to_string(category_rejected_count)},
         {"early_rejected",
          std::to_string(category_early_rejected_count)},
         {"lod_writes", std::to_string(category_lod_count)},
         {"title_visibility_authority", "true"},
         {"native_culling", "false"},
         {"native_lod", "false"},
         {"xenos_authority", "true"},
         {"suppression_allowed", "false"}});
  }

  uint64_t lod_histogram_total = 0;
  for (size_t index = 0; index < kSemanticVisibilityLodCapacity; ++index) {
    const uint64_t count = g_semantic_visibility_lod_histogram[index].load(
        std::memory_order_relaxed);
    if (!count) {
      continue;
    }
    lod_histogram_total += count;
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.discovery.semantic_lod_summary",
        {{"status", "complete"},
         {"lod_index", std::to_string(index)},
         {"writes", std::to_string(count)},
         {"source", "title_selected_runtime_record_plus_104"},
         {"native_lod", "false"},
         {"xenos_authority", "true"},
         {"suppression_allowed", "false"}});
  }

  uint64_t result_value_histogram_total = 0;
  for (size_t index = 0;
       index < kSemanticVisibilityResultValueCapacity; ++index) {
    const uint64_t count =
        g_semantic_visibility_result_value_histogram[index].load(
            std::memory_order_relaxed);
    if (!count) {
      continue;
    }
    result_value_histogram_total += count;
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.discovery.semantic_visibility_result_value_summary",
        {{"status", "complete"},
         {"selection_value", std::to_string(index)},
         {"observations", std::to_string(count)},
         {"interpretation", index ? "selected_nonzero" : "rejected_zero"},
         {"native_culling", "false"},
         {"xenos_authority", "true"},
         {"suppression_allowed", "false"}});
  }

  uint64_t policy_records = 0;
  uint64_t policy_spatial_samples = 0;
  uint64_t policy_runtime_observations = 0;
  uint64_t policy_runtime_less = 0;
  uint64_t policy_descriptor_observations = 0;
  uint64_t policy_descriptor_exceeded = 0;
  for (size_t category_index = 0;
       category_index < kSemanticVisibilityCategoryCapacity;
       ++category_index) {
    const SemanticVisibilityCategoryStats &category =
        g_semantic_visibility_categories[category_index];
    const std::array<uint64_t, kSemanticVisibilityPolicyOutcomeCapacity>
        expected_records = {
            category.early_rejected.load(std::memory_order_relaxed),
            category.rejected.load(std::memory_order_relaxed),
            category.selected.load(std::memory_order_relaxed),
        };
    for (size_t outcome_index = 0;
         outcome_index < kSemanticVisibilityPolicyOutcomeCapacity;
         ++outcome_index) {
      const SemanticVisibilityPolicyStats &policy =
          g_semantic_visibility_policy_categories[category_index]
                                                  [outcome_index];
      const uint64_t records =
          policy.records.load(std::memory_order_relaxed);
      if (!records) {
        continue;
      }
      const uint64_t spatial_samples =
          policy.spatial_samples.load(std::memory_order_relaxed);
      const uint64_t runtime_observations =
          policy.runtime_threshold_observations.load(
              std::memory_order_relaxed);
      const uint64_t runtime_less =
          policy.runtime_distance_less.load(std::memory_order_relaxed);
      const uint64_t descriptor_observations =
          policy.descriptor_threshold_observations.load(
              std::memory_order_relaxed);
      const uint64_t descriptor_exceeded =
          policy.descriptor_distance_exceeded.load(
              std::memory_order_relaxed);
      const bool policy_complete =
          records == expected_records[outcome_index] &&
          spatial_samples == records && runtime_less <= runtime_observations &&
          runtime_observations <= records &&
          descriptor_exceeded <= descriptor_observations &&
          descriptor_observations <= records;
      policy_records += records;
      policy_spatial_samples += spatial_samples;
      policy_runtime_observations += runtime_observations;
      policy_runtime_less += runtime_less;
      policy_descriptor_observations += descriptor_observations;
      policy_descriptor_exceeded += descriptor_exceeded;
      pinyon_shift::diagnostics::RecordEvent(
          "native_renderer.discovery.semantic_visibility_policy_category_summary",
          {{"status", policy_complete ? "complete" : "incomplete"},
           {"category", std::to_string(category_index)},
           {"outcome",
            SemanticVisibilityPolicyOutcomeName(outcome_index)},
           {"records", std::to_string(records)},
           {"spatial_samples", std::to_string(spatial_samples)},
           {"runtime_threshold_observations",
            std::to_string(runtime_observations)},
           {"runtime_distance_less", std::to_string(runtime_less)},
           {"descriptor_threshold_observations",
            std::to_string(descriptor_observations)},
           {"descriptor_distance_exceeded",
            std::to_string(descriptor_exceeded)},
           {"native_policy_execution", "false"},
           {"guest_state_changed", "false"},
           {"xenos_authority", "true"},
           {"suppression_allowed", "false"}});
    }
  }

  uint64_t policy_spatial_histogram_total = 0;
  for (size_t outcome_index = 0;
       outcome_index < kSemanticVisibilityPolicyOutcomeCapacity;
       ++outcome_index) {
    for (size_t exponent = 0;
         exponent < kSemanticVisibilitySpatialExponentCapacity;
         ++exponent) {
      const uint64_t records =
          g_semantic_visibility_spatial_exponents[outcome_index][exponent]
              .load(std::memory_order_relaxed);
      if (!records) {
        continue;
      }
      policy_spatial_histogram_total += records;
      pinyon_shift::diagnostics::RecordEvent(
          "native_renderer.discovery.semantic_visibility_spatial_exponent_summary",
          {{"status", "complete"},
           {"outcome",
            SemanticVisibilityPolicyOutcomeName(outcome_index)},
           {"float_exponent", std::to_string(exponent)},
           {"records", std::to_string(records)},
           {"source", "title_shared_spatial_distance_squared_f26"},
           {"native_policy_execution", "false"},
           {"guest_state_changed", "false"},
           {"xenos_authority", "true"},
           {"suppression_allowed", "false"}});
    }
  }

  const uint64_t policy_invalid_spatial =
      g_semantic_visibility_policy_invalid_spatial_values.load(
          std::memory_order_relaxed);
  const uint64_t policy_invalid_threshold =
      g_semantic_visibility_policy_invalid_threshold_values.load(
          std::memory_order_relaxed);
  const uint64_t policy_hook_faults =
      g_semantic_visibility_policy_hook_faults.load(
          std::memory_order_relaxed);
  const uint64_t runtime_without_record =
      g_semantic_visibility_runtime_threshold_without_record.load(
          std::memory_order_relaxed);
  const uint64_t duplicate_runtime =
      g_semantic_visibility_duplicate_runtime_threshold.load(
          std::memory_order_relaxed);
  const uint64_t descriptor_without_record =
      g_semantic_visibility_descriptor_threshold_without_record.load(
          std::memory_order_relaxed);
  const uint64_t duplicate_descriptor =
      g_semantic_visibility_duplicate_descriptor_threshold.load(
          std::memory_order_relaxed);
  const bool policy_complete =
      policy_records == completions && policy_spatial_samples == entries &&
      policy_spatial_histogram_total == policy_spatial_samples &&
      !policy_invalid_spatial && !policy_invalid_threshold &&
      !policy_hook_faults && !duplicate_runtime && !duplicate_descriptor;
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.discovery.semantic_visibility_policy_summary",
      {{"status", policy_complete ? "complete" : "incomplete"},
       {"records", std::to_string(policy_records)},
       {"spatial_samples", std::to_string(policy_spatial_samples)},
       {"runtime_threshold_observations",
        std::to_string(policy_runtime_observations)},
       {"runtime_distance_less", std::to_string(policy_runtime_less)},
       {"descriptor_threshold_observations",
        std::to_string(policy_descriptor_observations)},
       {"descriptor_distance_exceeded",
        std::to_string(policy_descriptor_exceeded)},
       {"spatial_histogram_records",
        std::to_string(policy_spatial_histogram_total)},
       {"invalid_spatial_values", std::to_string(policy_invalid_spatial)},
       {"invalid_threshold_values",
        std::to_string(policy_invalid_threshold)},
       {"hook_faults", std::to_string(policy_hook_faults)},
       {"runtime_threshold_without_record",
        std::to_string(runtime_without_record)},
       {"duplicate_runtime_threshold", std::to_string(duplicate_runtime)},
       {"descriptor_threshold_without_record",
        std::to_string(descriptor_without_record)},
       {"duplicate_descriptor_threshold",
        std::to_string(duplicate_descriptor)},
       {"accounting_complete", policy_complete ? "true" : "false"},
       {"scope", "active_title_record_only"},
       {"unscoped_continuations_excluded", "true"},
       {"classification", "title_spatial_policy_input_outcome_correlation"},
       {"guest_payload_read", "false"},
       {"guest_state_changed", "false"},
       {"control_flow_changed", "false"},
       {"native_policy_execution", "false"},
       {"native_culling", "false"},
       {"native_lod", "false"},
       {"xenos_authority", "true"},
       {"suppression_allowed", "false"}});

  uint64_t oracle_records = 0;
  uint64_t oracle_candidate_observations = 0;
  uint64_t oracle_candidate_passes = 0;
  uint64_t oracle_local_observations = 0;
  uint64_t oracle_local_passes = 0;
  uint64_t oracle_spatial_observations = 0;
  uint64_t oracle_spatial_passes = 0;
  uint64_t oracle_category_observations = 0;
  std::array<uint64_t, 3> oracle_category_results{};
  bool oracle_category_accounting_complete = true;
  for (size_t category_index = 0;
       category_index < kSemanticVisibilityCategoryCapacity;
       ++category_index) {
    const SemanticVisibilityCategoryStats &category =
        g_semantic_visibility_categories[category_index];
    const std::array<uint64_t, kSemanticVisibilityPolicyOutcomeCapacity>
        oracle_expected_records = {
            category.early_rejected.load(std::memory_order_relaxed),
            category.rejected.load(std::memory_order_relaxed),
            category.selected.load(std::memory_order_relaxed),
        };
    for (size_t outcome_index = 0;
         outcome_index < kSemanticVisibilityPolicyOutcomeCapacity;
         ++outcome_index) {
      SemanticVisibilityOracleStats &oracle =
          g_semantic_visibility_oracle_categories[category_index]
                                                  [outcome_index];
      const uint64_t records =
          oracle.records.load(std::memory_order_relaxed);
      if (!records) {
        continue;
      }
      const uint64_t spatial_observations =
          oracle.spatial_helper_observations.load(
              std::memory_order_relaxed);
      const uint64_t spatial_passes =
          oracle.spatial_helper_passes.load(std::memory_order_relaxed);
      const uint64_t candidate_observations =
          oracle.candidate_threshold_observations.load(
              std::memory_order_relaxed);
      const uint64_t candidate_passes =
          oracle.candidate_threshold_passes.load(
              std::memory_order_relaxed);
      const uint64_t local_observations =
          oracle.local_distance_observations.load(
              std::memory_order_relaxed);
      const uint64_t local_passes =
          oracle.local_distance_passes.load(std::memory_order_relaxed);
      const uint64_t category_observations =
          oracle.category_helper_observations.load(
              std::memory_order_relaxed);
      std::array<uint64_t, 3> category_results{};
      uint64_t category_result_total = 0;
      for (size_t result = 0; result < category_results.size(); ++result) {
        category_results[result] =
            oracle.category_results[result].load(std::memory_order_relaxed);
        category_result_total += category_results[result];
        oracle_category_results[result] += category_results[result];
      }
      const bool category_complete =
          records == oracle_expected_records[outcome_index] &&
          category_result_total == category_observations &&
          category_observations <= spatial_passes &&
          spatial_passes <= spatial_observations &&
          spatial_observations <= local_passes &&
          local_passes <= local_observations &&
          local_observations <= candidate_passes &&
          candidate_passes <= candidate_observations;
      oracle_category_accounting_complete &= category_complete;
      oracle_records += records;
      oracle_candidate_observations += candidate_observations;
      oracle_candidate_passes += candidate_passes;
      oracle_local_observations += local_observations;
      oracle_local_passes += local_passes;
      oracle_spatial_observations += spatial_observations;
      oracle_spatial_passes += spatial_passes;
      oracle_category_observations += category_observations;
      pinyon_shift::diagnostics::RecordEvent(
          "native_renderer.discovery.semantic_visibility_oracle_category_summary",
          {{"status", category_complete ? "complete" : "incomplete"},
           {"category", std::to_string(category_index)},
           {"outcome",
            SemanticVisibilityPolicyOutcomeName(outcome_index)},
           {"records", std::to_string(records)},
           {"candidate_threshold_observations",
            std::to_string(candidate_observations)},
           {"candidate_threshold_passes",
            std::to_string(candidate_passes)},
           {"local_distance_observations",
            std::to_string(local_observations)},
           {"local_distance_passes", std::to_string(local_passes)},
           {"spatial_helper_observations",
            std::to_string(spatial_observations)},
           {"spatial_helper_passes", std::to_string(spatial_passes)},
           {"category_helper_observations",
            std::to_string(category_observations)},
           {"category_result_0", std::to_string(category_results[0])},
           {"category_result_1", std::to_string(category_results[1])},
           {"category_result_2", std::to_string(category_results[2])},
           {"native_policy_execution", "false"},
           {"guest_state_changed", "false"},
           {"xenos_authority", "true"},
           {"suppression_allowed", "false"}});
    }
  }
  const uint64_t spatial_helper_without_record =
      g_semantic_visibility_spatial_helper_without_record.load(
          std::memory_order_relaxed);
  const uint64_t candidate_without_record =
      g_semantic_visibility_candidate_threshold_without_record.load(
          std::memory_order_relaxed);
  const uint64_t local_without_record =
      g_semantic_visibility_local_distance_without_record.load(
          std::memory_order_relaxed);
  const uint64_t local_without_candidate_pass =
      g_semantic_visibility_local_distance_without_candidate_pass.load(
          std::memory_order_relaxed);
  const uint64_t spatial_without_local_pass =
      g_semantic_visibility_spatial_helper_without_local_pass.load(
          std::memory_order_relaxed);
  const uint64_t oracle_invalid_values =
      g_semantic_visibility_oracle_invalid_values.load(
          std::memory_order_relaxed);
  const uint64_t category_helper_without_record =
      g_semantic_visibility_category_helper_without_record.load(
          std::memory_order_relaxed);
  const uint64_t category_without_spatial_pass =
      g_semantic_visibility_category_helper_without_spatial_pass.load(
          std::memory_order_relaxed);
  const uint64_t category_invalid_result =
      g_semantic_visibility_category_helper_invalid_result.load(
          std::memory_order_relaxed);
  const bool oracle_complete =
      oracle_category_accounting_complete && oracle_records == completions &&
      oracle_category_observations == oracle_category_results[0] +
                                                oracle_category_results[1] +
                                                oracle_category_results[2] &&
      oracle_category_observations <= oracle_spatial_passes &&
      oracle_spatial_passes <= oracle_spatial_observations &&
      oracle_spatial_observations <= oracle_local_passes &&
      oracle_local_passes <= oracle_local_observations &&
      oracle_local_observations <= oracle_candidate_passes &&
      oracle_candidate_passes <= oracle_candidate_observations &&
      !local_without_candidate_pass && !spatial_without_local_pass &&
      !oracle_invalid_values &&
      !category_without_spatial_pass && !category_invalid_result;
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.discovery.semantic_visibility_oracle_summary",
      {{"status", oracle_complete ? "complete" : "incomplete"},
       {"records", std::to_string(oracle_records)},
       {"candidate_threshold_observations",
        std::to_string(oracle_candidate_observations)},
       {"candidate_threshold_passes",
        std::to_string(oracle_candidate_passes)},
       {"local_distance_observations",
        std::to_string(oracle_local_observations)},
       {"local_distance_passes", std::to_string(oracle_local_passes)},
       {"spatial_helper_observations",
        std::to_string(oracle_spatial_observations)},
       {"spatial_helper_passes", std::to_string(oracle_spatial_passes)},
       {"category_helper_observations",
        std::to_string(oracle_category_observations)},
       {"category_result_0", std::to_string(oracle_category_results[0])},
       {"category_result_1", std::to_string(oracle_category_results[1])},
       {"category_result_2", std::to_string(oracle_category_results[2])},
       {"spatial_helper_without_record",
        std::to_string(spatial_helper_without_record)},
       {"candidate_threshold_without_record",
        std::to_string(candidate_without_record)},
       {"local_distance_without_record",
        std::to_string(local_without_record)},
       {"local_distance_without_candidate_pass",
        std::to_string(local_without_candidate_pass)},
       {"spatial_helper_without_local_pass",
        std::to_string(spatial_without_local_pass)},
       {"invalid_gate_values", std::to_string(oracle_invalid_values)},
       {"category_helper_without_record",
        std::to_string(category_helper_without_record)},
       {"category_helper_without_spatial_pass",
        std::to_string(category_without_spatial_pass)},
       {"category_helper_invalid_result",
        std::to_string(category_invalid_result)},
       {"accounting_complete", oracle_complete ? "true" : "false"},
       {"scope", "active_title_record_only"},
       {"unscoped_continuations_excluded", "true"},
       {"classification", "title_ordered_visibility_helper_oracle"},
       {"guest_payload_read", "false"},
       {"guest_state_changed", "false"},
       {"control_flow_changed", "false"},
       {"native_policy_execution", "false"},
       {"native_culling", "false"},
       {"native_lod", "false"},
        {"xenos_authority", "true"},
        {"suppression_allowed", "false"}});

  uint64_t shadow_records = 0;
  uint64_t shadow_modelled_records = 0;
  uint64_t shadow_predicted_selected = 0;
  uint64_t shadow_predicted_rejected = 0;
  uint64_t shadow_title_matches = 0;
  uint64_t shadow_false_positive = 0;
  uint64_t shadow_false_negative = 0;
  uint64_t shadow_result_1_records = 0;
  uint64_t shadow_result_2_records = 0;
  uint64_t shadow_mixed_nonzero_records = 0;
  bool shadow_category_accounting_complete = true;
  for (size_t category_index = 0;
       category_index < kSemanticVisibilityCategoryCapacity;
       ++category_index) {
    for (size_t outcome_index = 0;
         outcome_index < kSemanticVisibilityPolicyOutcomeCapacity;
         ++outcome_index) {
      const SemanticVisibilityShadowStats &shadow =
          g_semantic_visibility_shadow_categories[category_index]
                                                 [outcome_index];
      const uint64_t records =
          g_semantic_visibility_oracle_categories[category_index]
                                                 [outcome_index]
              .records.load(std::memory_order_relaxed);
      if (!records) {
        continue;
      }
      const uint64_t modelled_records =
          shadow.modelled_records.load(std::memory_order_relaxed);
      const uint64_t predicted_selected =
          shadow.predicted_selected.load(std::memory_order_relaxed);
      const uint64_t predicted_rejected =
          shadow.predicted_rejected.load(std::memory_order_relaxed);
      const uint64_t title_matches =
          shadow.title_matches.load(std::memory_order_relaxed);
      const uint64_t false_positive =
          shadow.false_positive.load(std::memory_order_relaxed);
      const uint64_t false_negative =
          shadow.false_negative.load(std::memory_order_relaxed);
      const uint64_t result_1_records =
          shadow.result_1_records.load(std::memory_order_relaxed);
      const uint64_t result_2_records =
          shadow.result_2_records.load(std::memory_order_relaxed);
      const uint64_t mixed_nonzero_records =
          shadow.mixed_nonzero_records.load(std::memory_order_relaxed);
      const bool category_complete =
          modelled_records <= records &&
          predicted_selected + predicted_rejected == modelled_records &&
          title_matches + false_positive + false_negative == modelled_records &&
          result_1_records <= modelled_records &&
          result_2_records <= modelled_records &&
          mixed_nonzero_records <= result_1_records &&
          mixed_nonzero_records <= result_2_records;
      shadow_category_accounting_complete &= category_complete;
      shadow_records += records;
      shadow_modelled_records += modelled_records;
      shadow_predicted_selected += predicted_selected;
      shadow_predicted_rejected += predicted_rejected;
      shadow_title_matches += title_matches;
      shadow_false_positive += false_positive;
      shadow_false_negative += false_negative;
      shadow_result_1_records += result_1_records;
      shadow_result_2_records += result_2_records;
      shadow_mixed_nonzero_records += mixed_nonzero_records;
      pinyon_shift::diagnostics::RecordEvent(
          "native_renderer.discovery.semantic_visibility_shadow_category_summary",
          {{"status", category_complete ? "complete" : "incomplete"},
           {"category", std::to_string(category_index)},
           {"outcome", SemanticVisibilityPolicyOutcomeName(outcome_index)},
           {"records", std::to_string(records)},
           {"modelled_records", std::to_string(modelled_records)},
           {"predicted_selected", std::to_string(predicted_selected)},
           {"predicted_rejected", std::to_string(predicted_rejected)},
           {"title_matches", std::to_string(title_matches)},
           {"false_positive", std::to_string(false_positive)},
           {"false_negative", std::to_string(false_negative)},
           {"result_1_records", std::to_string(result_1_records)},
           {"result_2_records", std::to_string(result_2_records)},
           {"mixed_nonzero_records",
            std::to_string(mixed_nonzero_records)},
           {"native_policy_execution", "shadow_only"},
           {"guest_state_changed", "false"},
           {"xenos_authority", "true"},
           {"suppression_allowed", "false"}});
    }
  }
  const bool shadow_complete =
      shadow_category_accounting_complete &&
      shadow_records == oracle_records &&
      shadow_modelled_records <= shadow_records &&
      shadow_predicted_selected + shadow_predicted_rejected ==
          shadow_modelled_records &&
      shadow_title_matches + shadow_false_positive + shadow_false_negative ==
          shadow_modelled_records &&
      shadow_result_1_records <= shadow_modelled_records &&
      shadow_result_2_records <= shadow_modelled_records &&
      shadow_mixed_nonzero_records <= shadow_result_1_records &&
      shadow_mixed_nonzero_records <= shadow_result_2_records &&
      !shadow_false_positive && !shadow_false_negative;
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.discovery.semantic_visibility_shadow_summary",
      {{"status", shadow_complete ? "complete" : "incomplete"},
       {"records", std::to_string(shadow_records)},
       {"modelled_records", std::to_string(shadow_modelled_records)},
       {"unmodelled_records",
        std::to_string(shadow_records - shadow_modelled_records)},
       {"predicted_selected", std::to_string(shadow_predicted_selected)},
       {"predicted_rejected", std::to_string(shadow_predicted_rejected)},
       {"title_matches", std::to_string(shadow_title_matches)},
       {"false_positive", std::to_string(shadow_false_positive)},
       {"false_negative", std::to_string(shadow_false_negative)},
       {"result_1_records", std::to_string(shadow_result_1_records)},
       {"result_2_records", std::to_string(shadow_result_2_records)},
       {"mixed_nonzero_records",
        std::to_string(shadow_mixed_nonzero_records)},
       {"accounting_complete", shadow_complete ? "true" : "false"},
       {"model", "any_nonzero_category_result_selects"},
       {"scope", "active_title_record_only"},
       {"classification", "title_result_domain_shadow_selection"},
       {"guest_payload_read", "false"},
       {"guest_state_changed", "false"},
       {"control_flow_changed", "false"},
       {"native_policy_execution", "shadow_only"},
       {"native_culling", "false"},
       {"native_lod", "false"},
       {"xenos_authority", "true"},
       {"suppression_allowed", "false"}});

  uint64_t spatial_shadow_records = 0;
  uint64_t spatial_shadow_inputs = 0;
  uint64_t spatial_shadow_comparisons = 0;
  uint64_t spatial_shadow_matches = 0;
  uint64_t spatial_shadow_false_positive = 0;
  uint64_t spatial_shadow_false_negative = 0;
  uint64_t spatial_shadow_invalid_inputs = 0;
  bool spatial_shadow_category_accounting_complete = true;
  for (size_t category_index = 0;
       category_index < kSemanticVisibilityCategoryCapacity;
       ++category_index) {
    for (size_t outcome_index = 0;
         outcome_index < kSemanticVisibilityPolicyOutcomeCapacity;
         ++outcome_index) {
      const SemanticVisibilitySpatialShadowStats &spatial_shadow =
          g_semantic_visibility_spatial_shadow_categories[category_index]
                                                         [outcome_index];
      const SemanticVisibilityOracleStats &oracle =
          g_semantic_visibility_oracle_categories[category_index]
                                                 [outcome_index];
      const uint64_t records =
          oracle.records.load(std::memory_order_relaxed);
      if (!records) {
        continue;
      }
      const uint64_t inputs =
          spatial_shadow.input_observations.load(std::memory_order_relaxed);
      const uint64_t comparisons =
          spatial_shadow.comparisons.load(std::memory_order_relaxed);
      const uint64_t matches =
          spatial_shadow.matches.load(std::memory_order_relaxed);
      const uint64_t false_positive =
          spatial_shadow.false_positive.load(std::memory_order_relaxed);
      const uint64_t false_negative =
          spatial_shadow.false_negative.load(std::memory_order_relaxed);
      const uint64_t invalid_inputs =
          spatial_shadow.invalid_inputs.load(std::memory_order_relaxed);
      const uint64_t expected_inputs =
          oracle.spatial_helper_observations.load(std::memory_order_relaxed);
      const bool category_complete =
          inputs == expected_inputs &&
          comparisons == inputs &&
          matches + false_positive + false_negative == comparisons &&
          !invalid_inputs;
      spatial_shadow_category_accounting_complete &= category_complete;
      spatial_shadow_records += records;
      spatial_shadow_inputs += inputs;
      spatial_shadow_comparisons += comparisons;
      spatial_shadow_matches += matches;
      spatial_shadow_false_positive += false_positive;
      spatial_shadow_false_negative += false_negative;
      spatial_shadow_invalid_inputs += invalid_inputs;
      pinyon_shift::diagnostics::RecordEvent(
          "native_renderer.discovery.semantic_visibility_spatial_shadow_category_summary",
          {{"status", category_complete ? "complete" : "incomplete"},
           {"category", std::to_string(category_index)},
           {"outcome", SemanticVisibilityPolicyOutcomeName(outcome_index)},
           {"records", std::to_string(records)},
           {"input_observations", std::to_string(inputs)},
           {"comparisons", std::to_string(comparisons)},
           {"matches", std::to_string(matches)},
           {"false_positive", std::to_string(false_positive)},
           {"false_negative", std::to_string(false_negative)},
           {"invalid_inputs", std::to_string(invalid_inputs)},
           {"native_policy_execution", "shadow_only"},
           {"guest_payload_read", "bounded_spatial_helper_inputs"},
           {"guest_state_changed", "false"},
           {"xenos_authority", "true"},
           {"suppression_allowed", "false"}});
    }
  }
  const uint64_t spatial_shadow_input_without_record =
      g_semantic_visibility_spatial_shadow_input_without_record.load(
          std::memory_order_relaxed);
  const uint64_t spatial_shadow_result_without_input =
      g_semantic_visibility_spatial_shadow_result_without_input.load(
          std::memory_order_relaxed);
  const bool spatial_shadow_complete =
      spatial_shadow_category_accounting_complete &&
      spatial_shadow_records == oracle_records &&
      spatial_shadow_inputs == oracle_spatial_observations &&
      spatial_shadow_comparisons == spatial_shadow_inputs &&
      spatial_shadow_matches + spatial_shadow_false_positive +
              spatial_shadow_false_negative ==
          spatial_shadow_comparisons &&
      !spatial_shadow_false_positive && !spatial_shadow_false_negative &&
      !spatial_shadow_invalid_inputs;
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.discovery.semantic_visibility_spatial_shadow_summary",
      {{"status", spatial_shadow_complete ? "complete" : "incomplete"},
       {"records", std::to_string(spatial_shadow_records)},
       {"input_observations", std::to_string(spatial_shadow_inputs)},
       {"comparisons", std::to_string(spatial_shadow_comparisons)},
       {"matches", std::to_string(spatial_shadow_matches)},
       {"false_positive", std::to_string(spatial_shadow_false_positive)},
       {"false_negative", std::to_string(spatial_shadow_false_negative)},
       {"invalid_inputs", std::to_string(spatial_shadow_invalid_inputs)},
       {"input_without_record",
        std::to_string(spatial_shadow_input_without_record)},
       {"result_without_input",
        std::to_string(spatial_shadow_result_without_input)},
       {"accounting_complete", spatial_shadow_complete ? "true" : "false"},
       {"model", "bounded_title_spatial_helper_scalar_mirror"},
       {"scope", "active_title_record_only"},
       {"unscoped_continuations_excluded", "true"},
       {"classification", "independent_spatial_helper_shadow"},
       {"guest_payload_read", "bounded_spatial_helper_inputs"},
       {"guest_state_changed", "false"},
       {"control_flow_changed", "false"},
       {"native_policy_execution", "shadow_only"},
       {"native_culling", "false"},
       {"native_lod", "false"},
       {"xenos_authority", "true"},
        {"suppression_allowed", "false"}});

  uint64_t category_shadow_records = 0;
  uint64_t category_shadow_inputs = 0;
  uint64_t category_shadow_comparisons = 0;
  uint64_t category_shadow_matches = 0;
  uint64_t category_shadow_false_result = 0;
  uint64_t category_shadow_invalid_inputs = 0;
  bool category_shadow_category_accounting_complete = true;
  for (size_t category_index = 0;
       category_index < kSemanticVisibilityCategoryCapacity;
       ++category_index) {
    for (size_t outcome_index = 0;
         outcome_index < kSemanticVisibilityPolicyOutcomeCapacity;
         ++outcome_index) {
      const SemanticVisibilityCategoryShadowStats &category_shadow =
          g_semantic_visibility_category_shadow_categories[category_index]
                                                           [outcome_index];
      const SemanticVisibilityOracleStats &oracle =
          g_semantic_visibility_oracle_categories[category_index]
                                                 [outcome_index];
      const uint64_t records =
          oracle.records.load(std::memory_order_relaxed);
      if (!records) {
        continue;
      }
      const uint64_t inputs =
          category_shadow.input_observations.load(std::memory_order_relaxed);
      const uint64_t comparisons =
          category_shadow.comparisons.load(std::memory_order_relaxed);
      const uint64_t matches =
          category_shadow.matches.load(std::memory_order_relaxed);
      const uint64_t false_result =
          category_shadow.false_result.load(std::memory_order_relaxed);
      const uint64_t invalid_inputs =
          category_shadow.invalid_inputs.load(std::memory_order_relaxed);
      const uint64_t expected_inputs =
          oracle.category_helper_observations.load(std::memory_order_relaxed);
      const bool category_complete =
          inputs == expected_inputs && comparisons == inputs &&
          matches + false_result == comparisons && !invalid_inputs;
      category_shadow_category_accounting_complete &= category_complete;
      category_shadow_records += records;
      category_shadow_inputs += inputs;
      category_shadow_comparisons += comparisons;
      category_shadow_matches += matches;
      category_shadow_false_result += false_result;
      category_shadow_invalid_inputs += invalid_inputs;
      pinyon_shift::diagnostics::RecordEvent(
          "native_renderer.discovery.semantic_visibility_category_shadow_category_summary",
          {{"status", category_complete ? "complete" : "incomplete"},
           {"category", std::to_string(category_index)},
           {"outcome", SemanticVisibilityPolicyOutcomeName(outcome_index)},
           {"records", std::to_string(records)},
           {"input_observations", std::to_string(inputs)},
           {"comparisons", std::to_string(comparisons)},
           {"matches", std::to_string(matches)},
           {"false_result", std::to_string(false_result)},
           {"invalid_inputs", std::to_string(invalid_inputs)},
           {"native_policy_execution", "shadow_only"},
           {"guest_payload_read", "bounded_category_planes"},
           {"guest_state_changed", "false"},
           {"xenos_authority", "true"},
           {"suppression_allowed", "false"}});
    }
  }
  const uint64_t category_shadow_input_without_record =
      g_semantic_visibility_category_shadow_input_without_record.load(
          std::memory_order_relaxed);
  const uint64_t category_shadow_result_without_input =
      g_semantic_visibility_category_shadow_result_without_input.load(
          std::memory_order_relaxed);
  const bool category_shadow_complete =
      category_shadow_category_accounting_complete &&
      category_shadow_records == oracle_records &&
      category_shadow_inputs == oracle_category_observations &&
      category_shadow_comparisons == category_shadow_inputs &&
      category_shadow_matches + category_shadow_false_result ==
          category_shadow_comparisons &&
      !category_shadow_false_result && !category_shadow_invalid_inputs;
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.discovery.semantic_visibility_category_shadow_summary",
      {{"status", category_shadow_complete ? "complete" : "incomplete"},
       {"records", std::to_string(category_shadow_records)},
       {"input_observations", std::to_string(category_shadow_inputs)},
       {"comparisons", std::to_string(category_shadow_comparisons)},
       {"matches", std::to_string(category_shadow_matches)},
       {"false_result", std::to_string(category_shadow_false_result)},
       {"invalid_inputs", std::to_string(category_shadow_invalid_inputs)},
       {"input_without_record",
        std::to_string(category_shadow_input_without_record)},
       {"result_without_input",
        std::to_string(category_shadow_result_without_input)},
       {"accounting_complete", category_shadow_complete ? "true" : "false"},
       {"model", "six_plane_support_point_classifier"},
       {"scope", "active_title_record_only"},
       {"unscoped_continuations_excluded", "true"},
       {"classification", "independent_category_helper_shadow"},
       {"guest_payload_read", "bounded_category_planes"},
       {"guest_state_changed", "false"},
       {"control_flow_changed", "false"},
       {"native_policy_execution", "shadow_only"},
       {"native_culling", "false"},
       {"native_lod", "false"},
       {"xenos_authority", "true"},
       {"suppression_allowed", "false"}});

  uint64_t assembly_records = 0;
  uint64_t assembly_modelled_records = 0;
  uint64_t assembly_predicted_selected = 0;
  uint64_t assembly_predicted_rejected = 0;
  uint64_t assembly_title_matches = 0;
  uint64_t assembly_false_positive = 0;
  uint64_t assembly_false_negative = 0;
  uint64_t assembly_spatial_inputs = 0;
  uint64_t assembly_spatial_passes = 0;
  uint64_t assembly_category_inputs = 0;
  std::array<uint64_t, 3> assembly_category_predictions{};
  uint64_t assembly_invalid_inputs = 0;
  bool assembly_category_accounting_complete = true;
  for (size_t category_index = 0;
       category_index < kSemanticVisibilityCategoryCapacity;
       ++category_index) {
    for (size_t outcome_index = 0;
         outcome_index < kSemanticVisibilityPolicyOutcomeCapacity;
         ++outcome_index) {
      const SemanticVisibilityAssemblyShadowStats &assembly =
          g_semantic_visibility_assembly_shadow_categories[category_index]
                                                              [outcome_index];
      const SemanticVisibilityOracleStats &oracle =
          g_semantic_visibility_oracle_categories[category_index]
                                                 [outcome_index];
      const SemanticVisibilitySpatialShadowStats &spatial_shadow =
          g_semantic_visibility_spatial_shadow_categories[category_index]
                                                         [outcome_index];
      const SemanticVisibilityCategoryShadowStats &category_shadow =
          g_semantic_visibility_category_shadow_categories[category_index]
                                                           [outcome_index];
      const uint64_t records =
          assembly.records.load(std::memory_order_relaxed);
      if (!records) {
        continue;
      }
      const uint64_t expected_records =
          oracle.records.load(std::memory_order_relaxed);
      const uint64_t modelled_records =
          assembly.modelled_records.load(std::memory_order_relaxed);
      const uint64_t predicted_selected =
          assembly.predicted_selected.load(std::memory_order_relaxed);
      const uint64_t predicted_rejected =
          assembly.predicted_rejected.load(std::memory_order_relaxed);
      const uint64_t title_matches =
          assembly.title_matches.load(std::memory_order_relaxed);
      const uint64_t false_positive =
          assembly.false_positive.load(std::memory_order_relaxed);
      const uint64_t false_negative =
          assembly.false_negative.load(std::memory_order_relaxed);
      const uint64_t spatial_inputs =
          assembly.spatial_input_observations.load(std::memory_order_relaxed);
      const uint64_t spatial_passes =
          assembly.spatial_predicted_passes.load(std::memory_order_relaxed);
      const uint64_t category_inputs =
          assembly.category_input_observations.load(std::memory_order_relaxed);
      std::array<uint64_t, 3> category_predictions{};
      uint64_t category_prediction_total = 0;
      bool category_predictions_match = true;
      for (size_t result = 0; result < category_predictions.size(); ++result) {
        category_predictions[result] =
            assembly.category_predictions[result].load(
                std::memory_order_relaxed);
        category_prediction_total += category_predictions[result];
        category_predictions_match &=
            category_predictions[result] ==
            oracle.category_results[result].load(std::memory_order_relaxed);
      }
      const uint64_t invalid_inputs =
          assembly.invalid_inputs.load(std::memory_order_relaxed);
      const bool category_complete =
          records == expected_records && modelled_records <= records &&
          predicted_selected + predicted_rejected == modelled_records &&
          title_matches + false_positive + false_negative == modelled_records &&
          spatial_inputs == spatial_shadow.input_observations.load(
                                std::memory_order_relaxed) &&
          spatial_passes == category_inputs &&
          category_inputs == category_shadow.input_observations.load(
                                 std::memory_order_relaxed) &&
          category_prediction_total == category_inputs &&
          category_predictions_match && !false_positive && !false_negative &&
          !invalid_inputs;
      assembly_category_accounting_complete &= category_complete;
      assembly_records += records;
      assembly_modelled_records += modelled_records;
      assembly_predicted_selected += predicted_selected;
      assembly_predicted_rejected += predicted_rejected;
      assembly_title_matches += title_matches;
      assembly_false_positive += false_positive;
      assembly_false_negative += false_negative;
      assembly_spatial_inputs += spatial_inputs;
      assembly_spatial_passes += spatial_passes;
      assembly_category_inputs += category_inputs;
      assembly_invalid_inputs += invalid_inputs;
      for (size_t result = 0; result < category_predictions.size(); ++result) {
        assembly_category_predictions[result] += category_predictions[result];
      }
      pinyon_shift::diagnostics::RecordEvent(
          "native_renderer.discovery.semantic_visibility_assembly_shadow_category_summary",
          {{"status", category_complete ? "complete" : "incomplete"},
           {"category", std::to_string(category_index)},
           {"outcome", SemanticVisibilityPolicyOutcomeName(outcome_index)},
           {"records", std::to_string(records)},
           {"modelled_records", std::to_string(modelled_records)},
           {"predicted_selected", std::to_string(predicted_selected)},
           {"predicted_rejected", std::to_string(predicted_rejected)},
           {"title_matches", std::to_string(title_matches)},
           {"false_positive", std::to_string(false_positive)},
           {"false_negative", std::to_string(false_negative)},
           {"spatial_input_observations", std::to_string(spatial_inputs)},
           {"spatial_predicted_passes", std::to_string(spatial_passes)},
           {"category_input_observations", std::to_string(category_inputs)},
           {"category_result_0", std::to_string(category_predictions[0])},
           {"category_result_1", std::to_string(category_predictions[1])},
           {"category_result_2", std::to_string(category_predictions[2])},
           {"invalid_inputs", std::to_string(invalid_inputs)},
           {"native_policy_execution", "shadow_only"},
           {"guest_payload_read", "bounded_spatial_and_category_inputs"},
           {"guest_state_changed", "false"},
           {"xenos_authority", "true"},
           {"suppression_allowed", "false"}});
    }
  }
  const bool assembly_complete =
      assembly_category_accounting_complete &&
      assembly_records == oracle_records &&
      assembly_spatial_inputs == oracle_spatial_observations &&
      assembly_spatial_passes == oracle_category_observations &&
      assembly_category_inputs == oracle_category_observations &&
      assembly_category_predictions[0] == oracle_category_results[0] &&
      assembly_category_predictions[1] == oracle_category_results[1] &&
      assembly_category_predictions[2] == oracle_category_results[2] &&
      assembly_predicted_selected + assembly_predicted_rejected ==
          assembly_modelled_records &&
      assembly_title_matches == assembly_modelled_records &&
      !assembly_false_positive && !assembly_false_negative &&
      !assembly_invalid_inputs;
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.discovery.semantic_visibility_assembly_shadow_summary",
      {{"status", assembly_complete ? "complete" : "incomplete"},
       {"records", std::to_string(assembly_records)},
       {"modelled_records", std::to_string(assembly_modelled_records)},
       {"unmodelled_records",
        std::to_string(assembly_records >= assembly_modelled_records
                           ? assembly_records - assembly_modelled_records
                           : 0)},
       {"predicted_selected", std::to_string(assembly_predicted_selected)},
       {"predicted_rejected", std::to_string(assembly_predicted_rejected)},
       {"title_matches", std::to_string(assembly_title_matches)},
       {"false_positive", std::to_string(assembly_false_positive)},
       {"false_negative", std::to_string(assembly_false_negative)},
       {"spatial_input_observations", std::to_string(assembly_spatial_inputs)},
       {"spatial_predicted_passes", std::to_string(assembly_spatial_passes)},
       {"category_input_observations", std::to_string(assembly_category_inputs)},
       {"category_result_0", std::to_string(assembly_category_predictions[0])},
       {"category_result_1", std::to_string(assembly_category_predictions[1])},
       {"category_result_2", std::to_string(assembly_category_predictions[2])},
       {"invalid_inputs", std::to_string(assembly_invalid_inputs)},
       {"accounting_complete", assembly_complete ? "true" : "false"},
       {"model", "independent_spatial_then_category_selection"},
       {"scope", "active_title_record_only"},
       {"classification", "independent_visibility_policy_assembly_shadow"},
       {"guest_payload_read", "bounded_spatial_and_category_inputs"},
       {"guest_state_changed", "false"},
       {"control_flow_changed", "false"},
       {"native_policy_execution", "shadow_only"},
       {"native_culling", "false"},
       {"native_lod", "false"},
       {"xenos_authority", "true"},
       {"suppression_allowed", "false"}});

  const uint64_t category_overflow =
      g_semantic_visibility_category_overflow.load(
          std::memory_order_relaxed);
  const uint64_t lod_overflow = g_semantic_visibility_lod_overflow.load(
      std::memory_order_relaxed);
  const uint64_t stack_faults =
      g_semantic_visibility_record_stack_faults.load(
          std::memory_order_relaxed);
  const uint64_t entry_overlaps =
      g_semantic_visibility_entry_overlaps.load(
          std::memory_order_relaxed);
  const uint64_t lod_without_record =
      g_semantic_visibility_lod_without_record.load(
          std::memory_order_relaxed);
  const uint64_t lod_rewrites =
      g_semantic_visibility_lod_rewrites.load(
          std::memory_order_relaxed);
  const uint64_t result_without_record =
      g_semantic_visibility_result_without_record.load(
          std::memory_order_relaxed);
  const uint64_t duplicate_result =
      g_semantic_visibility_duplicate_result.load(
          std::memory_order_relaxed);
  const uint64_t completion_without_record =
      g_semantic_visibility_completion_without_record.load(
          std::memory_order_relaxed);
  const uint64_t exit_with_record =
      g_semantic_visibility_exit_with_record.load(
          std::memory_order_relaxed);
  const uint64_t detailed_protocol_faults =
      entry_overlaps + lod_without_record + result_without_record +
      duplicate_result + completion_without_record + exit_with_record;
  const uint64_t identity_mismatches =
      g_semantic_visibility_record_identity_mismatches.load(
          std::memory_order_relaxed);
  const uint64_t unknown_receivers =
      g_semantic_visibility_record_unknown_receivers.load(
          std::memory_order_relaxed);
  const uint64_t records_open = g_semantic_visibility_records_open.load(
      std::memory_order_relaxed);
  const bool accounting_complete =
      entries && entries == completions &&
      completions == selected + rejected + early_rejected &&
      results == selected + rejected && !category_overflow &&
      category_entries == entries && category_completions == completions &&
      category_selected == selected && category_rejected == rejected &&
      category_early_rejected == early_rejected &&
      category_lod_writes == lod_writes &&
      lod_histogram_total + lod_overflow == lod_writes && !lod_overflow &&
      result_value_histogram_total == results &&
      stack_faults == detailed_protocol_faults && !stack_faults &&
      !identity_mismatches && !unknown_receivers &&
      !records_open;
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.discovery.semantic_visibility_summary",
      {{"status", accounting_complete ? "complete" : "incomplete"},
       {"record_entries", std::to_string(entries)},
       {"record_completions", std::to_string(completions)},
       {"result_observations", std::to_string(results)},
       {"selected_records", std::to_string(selected)},
       {"rejected_records", std::to_string(rejected)},
       {"early_rejected_records", std::to_string(early_rejected)},
       {"lod_writes", std::to_string(lod_writes)},
       {"lod_category_selected_with_lod",
        std::to_string(g_semantic_visibility_selected_with_lod.load(
            std::memory_order_relaxed))},
       {"lod_category_selected_without_lod",
        std::to_string(g_semantic_visibility_selected_without_lod.load(
            std::memory_order_relaxed))},
       {"category_capacity",
        std::to_string(kSemanticVisibilityCategoryCapacity)},
       {"lod_capacity", std::to_string(kSemanticVisibilityLodCapacity)},
       {"category_overflow", std::to_string(category_overflow)},
       {"lod_overflow", std::to_string(lod_overflow)},
       {"record_stack_faults", std::to_string(stack_faults)},
       {"entry_overlaps", std::to_string(entry_overlaps)},
       {"lod_without_record", std::to_string(lod_without_record)},
       {"lod_rewrites", std::to_string(lod_rewrites)},
       {"result_without_record", std::to_string(result_without_record)},
       {"duplicate_result", std::to_string(duplicate_result)},
       {"completion_without_record",
        std::to_string(completion_without_record)},
       {"visibility_exit_with_record", std::to_string(exit_with_record)},
       {"record_identity_mismatches",
        std::to_string(identity_mismatches)},
       {"record_unknown_receivers", std::to_string(unknown_receivers)},
       {"record_open_at_shutdown",
        std::to_string(records_open)},
       {"accounting_complete",
        accounting_complete ? "true" : "false"},
       {"classification",
        "title_authoritative_visibility_and_lod_observation"},
       {"guest_payload_read", "false"},
       {"guest_state_changed", "false"},
       {"control_flow_changed", "false"},
       {"native_culling", "false"},
       {"native_lod", "false"},
       {"native_draw", "false"},
       {"xenos_authority", "true"},
       {"suppression_allowed", "false"}});
}

void EmitSemanticVisibilityPreparedCandidates() {
  uint64_t entry_draws = 0;
  uint64_t entry_count = 0;
  uint64_t mechanically_eligible_draws = 0;
  uint64_t mechanically_eligible_entries = 0;
  uint64_t mechanically_ineligible_draws = 0;
  uint64_t mechanically_ineligible_entries = 0;
  uint64_t title_lod_draws = 0;
  uint64_t title_lod_entries = 0;
  for (const SemanticVisibilityPreparedCandidateEntry &entry :
       g_semantic_visibility_prepared_candidates) {
    if (!entry.key) {
      continue;
    }
    ++entry_count;
    entry_draws += entry.draws;
    if (entry.mechanically_eligible) {
      mechanically_eligible_draws += entry.draws;
      ++mechanically_eligible_entries;
    } else {
      mechanically_ineligible_draws += entry.draws;
      ++mechanically_ineligible_entries;
    }
    if (entry.title_lod_valid) {
      title_lod_draws += entry.draws;
      ++title_lod_entries;
    }
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.discovery.semantic_visibility_prepared_candidate_entry",
        {{"status", "complete"},
         {"candidate_key", fmt::format("{:016X}", entry.key)},
         {"prepared_signature",
          fmt::format("{:016X}", entry.prepared_signature)},
         {"template_key", fmt::format("{:016X}", entry.template_key)},
         {"geometry_resource_hash",
          fmt::format("{:016X}", entry.geometry_resource_hash)},
         {"texture_resource_hash",
          fmt::format("{:016X}", entry.texture_resource_hash)},
         {"vertex_shader",
          fmt::format("{:016X}", entry.vertex_shader_hash)},
         {"pixel_shader", fmt::format("{:016X}", entry.pixel_shader_hash)},
         {"vertex_specialization_mask",
          fmt::format("{:016X}", entry.vertex_specialization_mask)},
         {"pixel_specialization_mask",
          fmt::format("{:016X}", entry.pixel_specialization_mask)},
         {"receiver_address",
          fmt::format("{:08X}", entry.receiver_address)},
         {"receiver_generation",
          std::to_string(entry.receiver_generation)},
         {"record_index", std::to_string(entry.record_index)},
         {"visibility_category",
          std::to_string(entry.visibility_category)},
         {"visibility_result_mask",
          std::to_string(entry.visibility_result_mask)},
         {"title_lod_index", std::to_string(entry.title_lod_index)},
         {"title_lod_valid", entry.title_lod_valid ? "true" : "false"},
         {"title_lod_lineage", "exact_visibility_identity_to_prepared_draw"},
         {"draws", std::to_string(entry.draws)},
         {"first_frame", std::to_string(entry.first_frame)},
         {"last_frame", std::to_string(entry.last_frame)},
         {"maximum_policy_age_frames",
          std::to_string(entry.maximum_policy_age_frames)},
         {"mechanically_eligible",
          entry.mechanically_eligible ? "true" : "false"},
         {"mechanical_rejection_mask",
          fmt::format("{:08X}", entry.mechanical_rejection_mask)},
         {"mechanical_admission_contract", "isolated_draw_v1"},
         {"policy_age_limit_frames",
          std::to_string(kSemanticVisibilityMaximumPolicyAgeFrames)},
         {"classification", "fresh_visibility_selected_prepared_candidate"},
         {"guest_state_changed", "false"},
         {"control_flow_changed", "false"},
         {"native_upload", "false"},
         {"native_draw", "false"},
         {"xenos_draw", "preserved"},
         {"suppression_allowed", "false"}});
  }
  const bool accounting_complete =
      g_semantic_visibility_prepared_observations ==
          g_semantic_visibility_prepared_selected_joins +
              g_semantic_visibility_prepared_rejected_exclusions +
              g_semantic_visibility_prepared_missing_exclusions &&
      g_semantic_visibility_prepared_selected_joins ==
          g_semantic_visibility_prepared_fresh_candidates +
              g_semantic_visibility_prepared_stale_exclusions +
              g_semantic_visibility_prepared_future_exclusions &&
      g_semantic_visibility_prepared_fresh_candidates ==
          entry_draws +
              g_semantic_visibility_prepared_candidate_overflow &&
      g_semantic_visibility_prepared_candidate_count == entry_count &&
      mechanically_eligible_draws + mechanically_ineligible_draws ==
          entry_draws &&
      mechanically_eligible_entries + mechanically_ineligible_entries ==
          entry_count &&
      title_lod_draws <= entry_draws && title_lod_entries <= entry_count;
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.discovery.semantic_visibility_prepared_candidate_summary",
      {{"status", !g_semantic_visibility_prepared_observations
                       ? "not_observed"
                       : (accounting_complete ? "complete" : "incomplete")},
       {"observations",
        std::to_string(g_semantic_visibility_prepared_observations)},
       {"selected_joins",
        std::to_string(g_semantic_visibility_prepared_selected_joins)},
       {"fresh_candidates",
        std::to_string(g_semantic_visibility_prepared_fresh_candidates)},
       {"stale_exclusions",
        std::to_string(g_semantic_visibility_prepared_stale_exclusions)},
       {"future_exclusions",
        std::to_string(g_semantic_visibility_prepared_future_exclusions)},
       {"rejected_exclusions",
        std::to_string(g_semantic_visibility_prepared_rejected_exclusions)},
       {"missing_exclusions",
        std::to_string(g_semantic_visibility_prepared_missing_exclusions)},
       {"candidate_entries",
        std::to_string(g_semantic_visibility_prepared_candidate_count)},
       {"entry_draws", std::to_string(entry_draws)},
       {"mechanically_eligible_entries",
        std::to_string(mechanically_eligible_entries)},
       {"mechanically_eligible_draws",
        std::to_string(mechanically_eligible_draws)},
       {"mechanically_ineligible_entries",
        std::to_string(mechanically_ineligible_entries)},
       {"mechanically_ineligible_draws",
        std::to_string(mechanically_ineligible_draws)},
       {"mechanical_admission_contract", "isolated_draw_v1"},
       {"title_lod_entries", std::to_string(title_lod_entries)},
       {"title_lod_draws", std::to_string(title_lod_draws)},
       {"capacity",
        std::to_string(kSemanticVisibilityPreparedCandidateCapacity)},
       {"overflow",
        std::to_string(g_semantic_visibility_prepared_candidate_overflow)},
       {"policy_age_limit_frames",
        std::to_string(kSemanticVisibilityMaximumPolicyAgeFrames)},
       {"accounting_complete", accounting_complete ? "true" : "false"},
       {"identity", "receiver_generation_record_index"},
       {"prepared_lineage", "exact_semantic_pm4_prepared_draw"},
       {"selection", "independent_visibility_selected_and_fresh"},
       {"title_lod_lineage", "exact_visibility_identity_to_prepared_draw"},
       {"guest_state_changed", "false"},
       {"control_flow_changed", "false"},
       {"native_upload", "false"},
       {"native_draw", "false"},
       {"xenos_draw", "preserved"},
       {"suppression_allowed", "false"}});
}

void EmitSemanticBatchOpportunitySummary() {
  FinalizeSemanticBatchRun();
  FinalizeSemanticBatchFrame();
  EmitSemanticVisibilityPreparedCandidates();
  EmitSemanticBatchEquivalenceSummary();
  EmitSemanticStateCacheSummary();
  uint64_t entry_draws = 0;
  uint64_t entry_eligible_draws = 0;
  uint64_t entry_rejected_draws = 0;
  uint64_t entry_runs = 0;
  uint64_t entry_multi_draw_runs = 0;
  uint64_t entry_multi_draw_draws = 0;
  uint64_t rejection_total = 0;
  for (uint64_t count : g_semantic_batch_rejections) {
    rejection_total += count;
  }
  for (const SemanticBatchOpportunityEntry &entry :
       g_semantic_batch_opportunities) {
    if (!entry.key) {
      continue;
    }
    entry_draws += entry.draws;
    if (entry.rejection == SemanticBatchRejection::kNone) {
      entry_eligible_draws += entry.draws;
    } else {
      entry_rejected_draws += entry.draws;
    }
    entry_runs += entry.consecutive_runs;
    entry_multi_draw_runs += entry.multi_draw_runs;
    entry_multi_draw_draws += entry.multi_draw_draws;
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.discovery.semantic_batch_entry",
        {{"opportunity_key", fmt::format("{:016X}", entry.key)},
         {"template_key", fmt::format("{:016X}", entry.template_key)},
         {"geometry_resource_hash",
          fmt::format("{:016X}", entry.geometry_resource_hash)},
         {"texture_resource_hash",
          fmt::format("{:016X}", entry.texture_resource_hash)},
         {"primary_resource_key",
          fmt::format("{:08X}", entry.primary_resource_key)},
         {"secondary_resource_present",
          entry.secondary_resource_present ? "true" : "false"},
         {"secondary_resource_key",
          fmt::format("{:08X}", entry.secondary_resource_key)},
         {"draws", std::to_string(entry.draws)},
         {"frames", std::to_string(entry.frames)},
         {"first_frame", std::to_string(entry.first_frame)},
         {"last_frame", std::to_string(entry.last_frame)},
         {"consecutive_runs", std::to_string(entry.consecutive_runs)},
         {"multi_draw_runs", std::to_string(entry.multi_draw_runs)},
         {"multi_draw_draws", std::to_string(entry.multi_draw_draws)},
         {"maximum_run_length",
          std::to_string(entry.maximum_run_length)},
         {"instance_switches", std::to_string(entry.instance_switches)},
         {"same_instance_continuations",
          std::to_string(entry.same_instance_continuations)},
         {"eligible",
          entry.rejection == SemanticBatchRejection::kNone ? "true"
                                                           : "false"},
         {"rejection", SemanticBatchRejectionName(entry.rejection)},
         {"classification",
          entry.rejection == SemanticBatchRejection::kNone
              ? "conservative_consecutive_batch_candidate"
              : "xenos_replay_rejected"},
         {"native_batch", "false"},
         {"xenos_draw", "preserved"},
         {"suppression_allowed", "false"}});
  }
  const bool accounting_complete =
      !g_semantic_batch_opportunity_overflow &&
      g_semantic_batch_observations ==
          g_semantic_batch_eligible_draws + g_semantic_batch_rejected_draws &&
      g_semantic_batch_observations == entry_draws &&
      g_semantic_batch_eligible_draws == entry_eligible_draws &&
      g_semantic_batch_rejected_draws == entry_rejected_draws &&
      g_semantic_batch_rejected_draws == rejection_total &&
      g_semantic_batch_consecutive_runs == entry_runs &&
      g_semantic_batch_multi_draw_runs == entry_multi_draw_runs &&
      g_semantic_batch_multi_draw_draws == entry_multi_draw_draws;
  const uint64_t projected_commands =
      g_semantic_batch_consecutive_runs + g_semantic_batch_rejected_draws;
  const uint64_t potential_command_reduction =
      g_semantic_batch_eligible_draws >= g_semantic_batch_consecutive_runs
          ? g_semantic_batch_eligible_draws -
                g_semantic_batch_consecutive_runs
          : 0;
  const double reduction_percent = g_semantic_batch_observations
                                       ? 100.0 * potential_command_reduction /
                                             g_semantic_batch_observations
                                       : 0.0;
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.discovery.semantic_batch_summary",
      {{"status", !g_semantic_batch_observations
                       ? "not_observed"
                       : (accounting_complete ? "complete"
                                              : "incomplete")},
       {"observations", std::to_string(g_semantic_batch_observations)},
       {"eligible_draws", std::to_string(g_semantic_batch_eligible_draws)},
       {"rejected_draws", std::to_string(g_semantic_batch_rejected_draws)},
       {"opportunity_entries",
        std::to_string(g_semantic_batch_opportunity_count)},
       {"opportunity_overflow",
        std::to_string(g_semantic_batch_opportunity_overflow)},
       {"consecutive_runs",
        std::to_string(g_semantic_batch_consecutive_runs)},
       {"multi_draw_runs",
        std::to_string(g_semantic_batch_multi_draw_runs)},
       {"multi_draw_draws",
        std::to_string(g_semantic_batch_multi_draw_draws)},
       {"maximum_run_length",
        std::to_string(g_semantic_batch_maximum_run_length)},
       {"instance_switches",
        std::to_string(g_semantic_batch_instance_switches)},
       {"same_instance_continuations",
        std::to_string(g_semantic_batch_same_instance_continuations)},
       {"frames", std::to_string(g_semantic_batch_frame_count)},
       {"maximum_draws_per_frame",
        std::to_string(g_semantic_batch_maximum_draws_per_frame)},
       {"template_transitions",
        std::to_string(g_semantic_batch_template_transitions)},
       {"geometry_transitions",
        std::to_string(g_semantic_batch_geometry_transitions)},
       {"texture_transitions",
        std::to_string(g_semantic_batch_texture_transitions)},
       {"title_resource_transitions",
        std::to_string(g_semantic_batch_title_resource_transitions)},
       {"parameter_payload_bytes",
        std::to_string(g_semantic_batch_parameter_payload_bytes)},
       {"maximum_parameter_payload_bytes",
        std::to_string(g_semantic_batch_maximum_parameter_payload_bytes)},
       {"parameter_payload_limit_bytes",
        std::to_string(kSemanticBatchMaximumParameterPayloadBytes)},
       {"projected_commands", std::to_string(projected_commands)},
       {"potential_command_reduction",
        std::to_string(potential_command_reduction)},
       {"potential_command_reduction_percent",
        fmt::format("{:.3f}", reduction_percent)},
       {"reject_missing_title_resource",
        std::to_string(g_semantic_batch_rejections[size_t(
            SemanticBatchRejection::kMissingTitleResource)])},
       {"reject_non_opaque",
        std::to_string(g_semantic_batch_rejections[
            size_t(SemanticBatchRejection::kNonOpaque)])},
       {"reject_resolved_input",
        std::to_string(g_semantic_batch_rejections[
            size_t(SemanticBatchRejection::kResolvedInput)])},
       {"reject_query_or_conditional",
        std::to_string(g_semantic_batch_rejections[size_t(
            SemanticBatchRejection::kQueryOrConditional)])},
       {"reject_memexport",
        std::to_string(g_semantic_batch_rejections[
            size_t(SemanticBatchRejection::kMemexport)])},
       {"reject_unbounded_geometry",
        std::to_string(g_semantic_batch_rejections[size_t(
            SemanticBatchRejection::kUnboundedGeometry)])},
       {"reject_unsupported_geometry",
        std::to_string(g_semantic_batch_rejections[size_t(
            SemanticBatchRejection::kUnsupportedGeometry)])},
       {"reject_constant_overflow",
        std::to_string(g_semantic_batch_rejections[
            size_t(SemanticBatchRejection::kConstantOverflow)])},
       {"reject_unbounded_texture_layout",
        std::to_string(g_semantic_batch_rejections[size_t(
            SemanticBatchRejection::kUnboundedTextureLayout)])},
       {"reject_texture_count",
        std::to_string(g_semantic_batch_rejections[
            size_t(SemanticBatchRejection::kTextureCount)])},
       {"reject_incomplete_prepared_pipeline",
        std::to_string(g_semantic_batch_rejections[size_t(
            SemanticBatchRejection::kIncompletePreparedPipeline)])},
       {"reject_render_target_coverage",
        std::to_string(g_semantic_batch_rejections[size_t(
            SemanticBatchRejection::kRenderTargetCoverage)])},
       {"accounting_complete", accounting_complete ? "true" : "false"},
       {"ordering", "exact_consecutive_prepared_draw_order"},
       {"reordering", "false"},
       {"native_batch_execution", "false"},
       {"native_upload", "false"},
       {"native_draw", "false"},
       {"xenos_authority", "true"},
       {"suppression_allowed", "false"}});
}

void RecordCandidate(
    const rex::system::GraphicsDrawObservation &observation,
    bool samples_resolved_target,
    const rex::system::GraphicsPreparedDrawObservation &prepared);
void CommitPassConsumer(
    const rex::system::GraphicsDrawObservation &observation,
    const rex::system::GraphicsPreparedDrawObservation &prepared,
    const PendingCandidateObservation &candidate);

void ObservePreparedDraw(
    const rex::system::GraphicsPreparedDrawObservation &observation) {
  g_isolated_draw.prepared_candidate_valid = false;
  g_consumer_family_marker.current_match = false;
  if (!g_pending_candidate.valid) {
    ++g_candidate_prepared_without_observation_count;
  } else {
    auto sample = g_pending_candidate.sample;
    sample.vertex_shader_hash = observation.vertex_shader_hash;
    sample.pixel_shader_hash = observation.pixel_shader_hash;
    CommitPassConsumer(sample, observation, g_pending_candidate);
    const uint64_t prepared_signature = CandidateSignature(
        sample, g_pending_candidate.samples_resolved_target, observation);
    RecordPreparedCommandBufferLineage(prepared_signature, sample);
    RecordTitleDrawProvenance(prepared_signature, true, 0, sample,
                              g_pending_candidate.title_origin,
                              &observation);
    const SemanticVisibilityPreparedAdmission visibility_admission =
        RecordSemanticBatchOpportunity(
            sample, g_pending_candidate.samples_resolved_target, observation,
            g_pending_candidate.title_origin, prepared_signature);
    g_isolated_draw.prepared_signature = prepared_signature;
    g_isolated_draw.frame = sample.frame_sequence;
    g_isolated_draw.draw = sample.draw_sequence;
    g_isolated_draw.prepared_sample = sample;
    g_isolated_draw.prepared_candidate_eligible = IsIsolatedDrawEligible(
        sample, g_pending_candidate.samples_resolved_target, observation);
    g_isolated_draw.prepared_visibility_candidate_fresh =
        visibility_admission.fresh;
    g_isolated_draw.prepared_title_lod_valid =
        visibility_admission.title_lod_valid;
    g_isolated_draw.prepared_title_lod_index =
        visibility_admission.title_lod_index;
    g_isolated_draw.prepared_candidate_valid = true;
    if (g_pass_follower.requested && g_pass_follower.valid &&
        !g_pass_follower.completed) {
      if (g_pass_follower.awaiting_follower) {
        if (sample.frame_sequence == g_pass_follower.anchor_frame &&
            sample.draw_sequence == g_pass_follower.anchor_draw + 1) {
          const bool query_draw = sample.viz_query_condition ||
                                  (sample.pa_sc_viz_query & 1);
          const std::string pipeline_state = fmt::format(
              "color_mask={:08X};blend={:08X}:{:08X}:{:08X}:{:08X};"
              "depth={:08X};raster={:08X};vertex={:08X}",
              sample.rb_color_mask, sample.rb_blendcontrol[0],
              sample.rb_blendcontrol[1], sample.rb_blendcontrol[2],
              sample.rb_blendcontrol[3], sample.rb_depthcontrol,
              sample.pa_su_sc_mode_cntl, sample.pa_su_vtx_cntl);
          pinyon_shift::diagnostics::RecordEvent(
              "native_renderer.census.pass_follower",
              {{"anchor_signature",
                fmt::format("{:016X}", g_pass_follower.target_signature)},
               {"follower_signature",
                fmt::format("{:016X}", prepared_signature)},
               {"anchor_frame", std::to_string(g_pass_follower.anchor_frame)},
               {"anchor_draw", std::to_string(g_pass_follower.anchor_draw)},
               {"follower_frame", std::to_string(sample.frame_sequence)},
               {"follower_draw", std::to_string(sample.draw_sequence)},
               {"vertex_shader",
                fmt::format("{:016X}", sample.vertex_shader_hash)},
               {"pixel_shader", fmt::format("{:016X}", sample.pixel_shader_hash)},
               {"vertex_specialization_mask",
                fmt::format("{:016X}", observation.vertex_specialization_mask)},
               {"pixel_specialization_mask",
                fmt::format("{:016X}", observation.pixel_specialization_mask)},
               {"prepared_pipeline_hash",
                fmt::format("{:016X}", PreparedPipelineHash(observation))},
               {"host_primitive",
                std::to_string(observation.host_primitive_type)},
               {"host_index_buffer_type",
                std::to_string(observation.index_buffer_type)},
               {"host_index_format",
                std::to_string(observation.host_index_format)},
               {"host_primitive_reset",
                observation.host_primitive_reset_enabled ? "true" : "false"},
               {"prepared_pipeline_flags",
                fmt::format("{:08X}", observation.flags)},
               {"bound_render_target_bits",
                fmt::format("{:08X}", observation.bound_render_target_bits)},
               {"primitive", std::to_string(sample.primitive_type)},
               {"source_select", std::to_string(sample.source_select)},
               {"indexed", sample.indexed ? "true" : "false"},
               {"index_count", std::to_string(sample.index_count)},
               {"index_state",
                fmt::format("format={};endianness={}", sample.index_format,
                            sample.index_endianness)},
               {"vertex_binding_count",
                std::to_string(sample.vertex_binding_count)},
               {"vertex_attribute_count",
                std::to_string(sample.vertex_attribute_count)},
               {"texture_fetch_count",
                std::to_string(std::popcount(sample.texture_fetch_mask))},
               {"pipeline_state", pipeline_state},
               {"query", query_draw ? "true" : "false"},
               {"memexport", sample.vertex_memexport ? "true" : "false"},
               {"resolved_input",
                g_pending_candidate.samples_resolved_target ? "true" : "false"},
               {"mechanically_eligible",
                IsIsolatedDrawEligible(
                    sample, g_pending_candidate.samples_resolved_target,
                    observation)
                    ? "true"
                    : "false"},
               {"qualification", "metadata_contract_only"},
               {"xenos_draw", "preserved"},
               {"native_draw", "false"},
               {"suppression_eligible", "false"}});
          g_pass_follower.completed = true;
        } else {
          ++g_pass_follower.adjacency_mismatches;
        }
        g_pass_follower.awaiting_follower = false;
      }
      if (!g_pass_follower.completed &&
          prepared_signature == g_pass_follower.target_signature) {
        g_pass_follower.anchor_frame = sample.frame_sequence;
        g_pass_follower.anchor_draw = sample.draw_sequence;
        g_pass_follower.awaiting_follower = true;
      }
    }
    RecordCandidate(sample, g_pending_candidate.samples_resolved_target,
                    observation);
    g_pending_candidate.valid = false;
  }
  uint64_t identity = 0xCBF29CE484222325ull;
  for (uint64_t value :
       {observation.vertex_shader_hash, observation.pixel_shader_hash,
        observation.vertex_specialization_mask,
        observation.pixel_specialization_mask}) {
    identity = HashCombine(identity, value);
  }
  identity = identity ? identity : 1;
  size_t index = size_t(identity % kPreparedShaderPairCapacity);
  for (size_t probe = 0; probe < kPreparedShaderPairCapacity; ++probe) {
    PreparedShaderPairEntry &entry = g_prepared_shader_pairs[index];
    if (!entry.identity) {
      entry.identity = identity;
      entry.sample = observation;
      ++g_prepared_shader_pair_count;
      pinyon_shift::diagnostics::RecordEvent(
          "native_renderer.census.prepared_shader_pair",
          {{"vertex_shader",
            fmt::format("{:016X}", observation.vertex_shader_hash)},
           {"pixel_shader",
            fmt::format("{:016X}", observation.pixel_shader_hash)},
           {"vertex_specialization_mask",
            fmt::format("{:016X}", observation.vertex_specialization_mask)},
           {"pixel_specialization_mask",
            fmt::format("{:016X}", observation.pixel_specialization_mask)},
           {"mode", "pass_through"},
           {"suppression_eligible", "false"}});
      return;
    }
    if (entry.identity == identity &&
        entry.sample.vertex_shader_hash == observation.vertex_shader_hash &&
        entry.sample.pixel_shader_hash == observation.pixel_shader_hash &&
        entry.sample.vertex_specialization_mask ==
            observation.vertex_specialization_mask &&
        entry.sample.pixel_specialization_mask ==
            observation.pixel_specialization_mask) {
      return;
    }
    index = (index + 1) % kPreparedShaderPairCapacity;
  }
  ++g_prepared_shader_pair_overflow;
}

void EmitCandidateCensusWindow(uint64_t last_frame_value) {
  std::array<size_t, kSignatureCapacity> order{};
  uint64_t eligible_signatures = 0;
  uint64_t eligible_draws = 0;
  for (size_t i = 0; i < order.size(); ++i) {
    order[i] = i;
    const DrawSignatureEntry &entry = g_candidate_census.entries[i];
    if (entry.draw_count && IsMechanicallyEligibleCandidate(entry)) {
      ++eligible_signatures;
      eligible_draws += entry.draw_count;
    }
  }
  std::sort(order.begin(), order.end(), [](size_t left, size_t right) {
    const DrawSignatureEntry &left_entry = g_candidate_census.entries[left];
    const DrawSignatureEntry &right_entry = g_candidate_census.entries[right];
    const bool left_eligible = IsMechanicallyEligibleCandidate(left_entry);
    const bool right_eligible = IsMechanicallyEligibleCandidate(right_entry);
    if (left_eligible != right_eligible) {
      return left_eligible;
    }
    if (left_entry.draw_count != right_entry.draw_count) {
      return left_entry.draw_count > right_entry.draw_count;
    }
    return left_entry.signature < right_entry.signature;
  });
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.census.candidate_window",
      {{"first_frame", std::to_string(g_candidate_census.window_first_frame)},
       {"last_frame", std::to_string(last_frame_value)},
       {"draws", std::to_string(g_candidate_census.window_draw_count)},
       {"unique_signatures",
        std::to_string(g_candidate_census.unique_signature_count)},
       {"overflow_draws",
        std::to_string(g_candidate_census.overflow_draw_count)},
       {"eligible_signatures", std::to_string(eligible_signatures)},
       {"eligible_draws", std::to_string(eligible_draws)},
       {"signature_capacity", std::to_string(kSignatureCapacity)},
       {"summary_limit", std::to_string(kCandidateSummaryLimit)},
       {"mode", "metadata_shortlist_only"}});

  size_t emitted = 0;
  for (size_t index : order) {
    const DrawSignatureEntry &entry = g_candidate_census.entries[index];
    if (!entry.draw_count || emitted == kCandidateSummaryLimit) {
      break;
    }
    const auto &sample = entry.sample;
    std::string vertex_fetches;
    const uint32_t bounded_binding_count =
        std::min(sample.vertex_binding_count,
                 rex::system::kGraphicsVertexBindingObservationLimit);
    for (uint32_t i = 0; i < bounded_binding_count; ++i) {
      const auto &binding = sample.vertex_bindings[i];
      if (!vertex_fetches.empty()) {
        vertex_fetches += ";";
      }
      vertex_fetches += fmt::format(
          "{}:{:08X}:{}:{}:{}", binding.fetch_constant, binding.address,
          binding.size, binding.stride_words, binding.endianness);
    }
    std::string vertex_attributes;
    const uint32_t bounded_attribute_count =
        std::min(sample.vertex_attribute_count,
                 rex::system::kGraphicsVertexAttributeObservationLimit);
    for (uint32_t i = 0; i < bounded_attribute_count; ++i) {
      const auto &attribute = sample.vertex_attributes[i];
      if (!vertex_attributes.empty()) {
        vertex_attributes += ";";
      }
      vertex_attributes += fmt::format(
          "{}:{}:{}:{}:{}:{:X}:{}:{}:{}:{}:{:X}:{:X}:{:X}",
          attribute.binding_index, attribute.fetch_constant,
          attribute.offset_words, attribute.stride_words, attribute.data_format,
          attribute.fetch_word_mask, attribute.exp_adjust,
          attribute.signed_rf_mode, attribute.result_storage_target,
          attribute.result_storage_index, attribute.result_write_mask,
          attribute.result_components, attribute.flags);
    }
    const bool query_draw =
        sample.viz_query_condition || (sample.pa_sc_viz_query & 1);
    const std::string pipeline_state =
        fmt::format("color_mask={:08X};blend={:08X}:{:08X}:{:08X}:{:08X};"
                    "depth={:08X};raster={:08X};vertex={:08X}",
                    sample.rb_color_mask, sample.rb_blendcontrol[0],
                    sample.rb_blendcontrol[1], sample.rb_blendcontrol[2],
                    sample.rb_blendcontrol[3], sample.rb_depthcontrol,
                    sample.pa_su_sc_mode_cntl, sample.pa_su_vtx_cntl);
    const auto &prepared = entry.prepared_sample;
    const std::string bound_render_target_formats = fmt::format(
        "{:08X}:{:08X}:{:08X}:{:08X}:{:08X}",
        prepared.bound_render_target_formats[0],
        prepared.bound_render_target_formats[1],
        prepared.bound_render_target_formats[2],
        prepared.bound_render_target_formats[3],
        prepared.bound_render_target_formats[4]);
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.census.draw_candidate",
        {{"rank", std::to_string(++emitted)},
         {"signature", fmt::format("{:016X}", entry.signature)},
         {"draws", std::to_string(entry.draw_count)},
         {"first_frame", std::to_string(entry.first_frame)},
         {"last_frame", std::to_string(entry.last_frame)},
         {"vertex_shader", fmt::format("{:016X}", sample.vertex_shader_hash)},
         {"pixel_shader", fmt::format("{:016X}", sample.pixel_shader_hash)},
         {"vertex_specialization_mask",
          fmt::format("{:016X}", entry.vertex_specialization_mask)},
         {"pixel_specialization_mask",
          fmt::format("{:016X}", entry.pixel_specialization_mask)},
         {"primitive", std::to_string(sample.primitive_type)},
         {"source_select", std::to_string(sample.source_select)},
         {"index_count_min", std::to_string(entry.min_index_count)},
         {"index_count_max", std::to_string(entry.max_index_count)},
         {"index_state",
          fmt::format("format={};endianness={}", sample.index_format,
                      sample.index_endianness)},
         {"index_buffer_address",
          fmt::format("{:08X}", sample.index_buffer_address)},
         {"index_buffer_length_min",
          std::to_string(entry.min_index_buffer_length)},
         {"vertex_index_range",
          fmt::format("offset={};min={};max={}", sample.vertex_index_offset,
                      sample.vertex_index_min, sample.vertex_index_max)},
         {"vertex_binding_count", std::to_string(sample.vertex_binding_count)},
         {"vertex_fetches", vertex_fetches},
         {"vertex_attribute_count",
          std::to_string(sample.vertex_attribute_count)},
         {"vertex_attributes", vertex_attributes},
         {"texture_fetch_count",
          std::to_string(std::popcount(sample.texture_fetch_mask))},
         {"draw_state_hash", fmt::format("{:016X}", DrawStateHash(sample))},
         {"vertex_float_constant_count",
          std::to_string(sample.vertex_float_constant_count)},
         {"vertex_float_constants",
          SerializeFloatConstants(sample.vertex_float_constants,
                                  sample.vertex_float_constant_count)},
         {"pixel_float_constant_count",
          std::to_string(sample.pixel_float_constant_count)},
         {"pixel_float_constants",
          SerializeFloatConstants(sample.pixel_float_constants,
                                  sample.pixel_float_constant_count)},
         {"bool_constants",
          SerializeWordConstants(sample.bool_constant_bitmap,
                                 sample.bool_constant_values, 8)},
         {"loop_constants",
          SerializeLoopConstants(sample.loop_constant_bitmap,
                                 sample.loop_constant_values)},
         {"texture_state_count", std::to_string(sample.texture_state_count)},
         {"texture_states", SerializeTextureStates(sample)},
         {"pipeline_state", pipeline_state},
         {"prepared_pipeline_hash",
          fmt::format("{:016X}", PreparedPipelineHash(prepared))},
         {"host_primitive", std::to_string(prepared.host_primitive_type)},
         {"host_vertex_shader_type",
          std::to_string(prepared.host_vertex_shader_type)},
         {"tessellation_mode", std::to_string(prepared.tessellation_mode)},
         {"host_index_buffer_type",
          std::to_string(prepared.index_buffer_type)},
         {"host_index_format", std::to_string(prepared.host_index_format)},
         {"host_primitive_reset",
          prepared.host_primitive_reset_enabled ? "true" : "false"},
         {"normalized_depth_control",
          fmt::format("{:08X}", prepared.normalized_depth_control)},
         {"normalized_color_mask",
          fmt::format("{:08X}", prepared.normalized_color_mask)},
         {"bound_render_target_bits",
          fmt::format("{:08X}", prepared.bound_render_target_bits)},
         {"bound_render_target_formats", bound_render_target_formats},
         {"prepared_pipeline_flags", fmt::format("{:08X}", prepared.flags)},
         {"indexed", sample.indexed ? "true" : "false"},
         {"query", query_draw ? "true" : "false"},
         {"memexport", sample.vertex_memexport ? "true" : "false"},
         {"resolved_input", entry.samples_resolved_target ? "true" : "false"},
         {"opaque", IsOpaqueColorState(sample) ? "true" : "false"},
         {"vertex_overflow", sample.vertex_binding_overflow ? "true" : "false"},
         {"vertex_attribute_overflow",
          sample.vertex_attribute_overflow ? "true" : "false"},
         {"constant_overflow",
          (sample.vertex_float_constant_overflow ||
           sample.pixel_float_constant_overflow)
              ? "true"
              : "false"},
         {"texture_state_overflow",
          sample.texture_state_overflow ? "true" : "false"},
         {"mechanically_eligible",
          IsMechanicallyEligibleCandidate(entry) ? "true" : "false"},
         {"qualification", "metadata_shortlist_only"},
         {"suppression_eligible", "false"}});
  }
}

float HalfToFloat(uint16_t value) {
  const uint32_t sign = uint32_t(value & 0x8000) << 16;
  const uint32_t exponent = (value >> 10) & 0x1F;
  uint32_t mantissa = value & 0x03FF;
  uint32_t bits = 0;
  if (!exponent) {
    if (mantissa) {
      uint32_t normalized_exponent = 113;
      while (!(mantissa & 0x0400)) {
        mantissa <<= 1;
        --normalized_exponent;
      }
      bits = sign | (normalized_exponent << 23) |
             ((mantissa & 0x03FF) << 13);
    } else {
      bits = sign;
    }
  } else if (exponent == 0x1F) {
    bits = sign | 0x7F800000 | (mantissa << 13);
  } else {
    bits = sign | ((exponent + 112) << 23) | (mantissa << 13);
  }
  return std::bit_cast<float>(bits);
}

void CompleteConsumerFamilyReadbackArtifact(
    const rex::system::GraphicsIsolatedDrawReadback &readback,
    const char *attachment, const char *phase) {
  ++g_consumer_family_marker.readback_completions;
  const auto finish = []() {
    ++g_consumer_family_marker.current_capture_completions;
    if (g_consumer_family_marker.current_capture_completions == 4) {
      ++g_consumer_family_marker.readback_samples_completed;
      g_consumer_family_marker.readback_in_flight = false;
    }
  };
  const auto reject = [&](const char *status) {
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.census.consumer_family_readback",
        {{"consumer_family", ConsumerFamilyId()},
         {"status", status},
         {"detail", fmt::format("0x{:08X}", readback.detail)},
         {"frame", std::to_string(g_consumer_family_marker.capture_frame)},
         {"draw", std::to_string(g_consumer_family_marker.capture_draw)},
         {"sample",
          std::to_string(g_consumer_family_marker.current_capture_index)},
         {"attachment", attachment},
         {"phase", phase},
         {"xenos_draw", "preserved"},
         {"draw_suppression", "false"},
         {"resolve_suppression", "false"},
         {"suppression_eligible", "false"}});
    finish();
  };
  if (readback.status !=
      rex::system::GraphicsIsolatedDrawReadbackStatus::kReady) {
    if (readback.status ==
        rex::system::GraphicsIsolatedDrawReadbackStatus::
            kResolveAllocationFailed) {
      reject("resolve_allocation_failed");
    } else if (readback.status ==
               rex::system::GraphicsIsolatedDrawReadbackStatus::
                   kAllocationFailed) {
      reject("allocation_failed");
    } else if (readback.status ==
               rex::system::GraphicsIsolatedDrawReadbackStatus::kMapFailed) {
      reject("map_failed");
    } else {
      reject("unsupported_target");
    }
    return;
  }

  constexpr uint32_t kR16G16B16A16Float = 10;
  constexpr uint32_t kR8G8B8A8Unorm = 28;
  const bool is_color = std::strcmp(attachment, "color") == 0;
  const uint32_t bytes_per_pixel = is_color
                                       ? (readback.format ==
                                                  kR16G16B16A16Float
                                              ? 8
                                              : (readback.format ==
                                                         kR8G8B8A8Unorm
                                                     ? 4
                                                     : 0))
                                       : 0;
  const uint64_t required_size =
      is_color ? uint64_t(readback.row_pitch) * readback.height
               : readback.data_size;
  bool layout_valid = readback.data && readback.width && readback.height &&
                      required_size && required_size <= readback.data_size &&
                      required_size <= SIZE_MAX;
  if (is_color) {
    layout_valid &= bytes_per_pixel && readback.sample_count &&
                    uint64_t(readback.width) * bytes_per_pixel <=
                        readback.row_pitch;
  } else {
    layout_valid &= readback.sample_count && readback.plane_count &&
                    readback.plane_count <=
                        rex::system::GraphicsIsolatedDrawReadback::kMaxPlanes;
    for (uint32_t plane = 0;
         layout_valid && plane < readback.plane_count; ++plane) {
      const uint64_t plane_end =
          readback.plane_offsets[plane] +
          uint64_t(readback.plane_row_pitches[plane]) *
              (readback.plane_row_counts[plane] - 1) +
          readback.plane_row_sizes[plane];
      layout_valid &= readback.plane_row_pitches[plane] &&
                      readback.plane_row_sizes[plane] &&
                      readback.plane_row_sizes[plane] <=
                          readback.plane_row_pitches[plane] &&
                      readback.plane_row_counts[plane] &&
                      plane_end <= required_size;
    }
  }
  if (!layout_valid) {
    reject("unsupported_layout");
    return;
  }

  std::vector<uint8_t> bytes(readback.data,
                             readback.data + size_t(required_size));
  const std::string family = ConsumerFamilyId();
  const uint64_t frame = g_consumer_family_marker.capture_frame;
  const uint64_t draw = g_consumer_family_marker.capture_draw;
  const uint32_t sample = g_consumer_family_marker.current_capture_index;
  std::filesystem::path capture_root =
      g_consumer_family_marker.readback_root;
  if (g_consumer_family_marker.readback_sample_limit > 1) {
    capture_root /= fmt::format("sample-{:04}", sample);
  }
  const auto output_root = is_color
                               ? capture_root / phase
                               : capture_root / L"depth" / phase;
  const uint32_t width = readback.width;
  const uint32_t height = readback.height;
  const uint32_t row_pitch = readback.row_pitch;
  const uint32_t format = readback.format;
  const uint32_t source_sample_count = readback.sample_count;
  // D3D12 color MSAA readback is resolved before it reaches this callback.
  // Depth/stencil MSAA is extracted per sample and remains multisampled.
  const uint32_t sample_count = is_color ? 1 : source_sample_count;
  const uint32_t plane_count = readback.plane_count;
  std::string planes = "[";
  for (uint32_t plane = 0; plane < plane_count; ++plane) {
    if (plane) {
      planes += ',';
    }
    planes += fmt::format(
        "{{\"offset\":{},\"row_pitch\":{},\"row_size\":{},"
        "\"row_count\":{}}}",
        readback.plane_offsets[plane], readback.plane_row_pitches[plane],
        readback.plane_row_sizes[plane],
        readback.plane_row_counts[plane]);
  }
  planes += ']';
  const std::string encoding =
      is_color
          ? (format == kR16G16B16A16Float ? "rgba16_float"
                                          : "rgba8_unorm")
          : (sample_count > 1 ? "depth32_stencil8_sample_tuples"
                              : "d3d12_planar_depth_stencil");
  g_consumer_family_marker.artifact_writers.emplace_back(
      [bytes = std::move(bytes), family, frame, draw, sample, output_root,
       width, height, row_pitch, format, bytes_per_pixel, sample_count,
       source_sample_count, plane_count, planes = std::move(planes), encoding,
       attachment = std::string(attachment), phase = std::string(phase)]() {
        std::filesystem::path staging = output_root;
        staging += L".partial";
        std::error_code error;
        if (std::filesystem::exists(output_root, error) || error ||
            std::filesystem::exists(staging, error) || error ||
            !std::filesystem::create_directories(staging, error) || error) {
          pinyon_shift::diagnostics::RecordEvent(
              "native_renderer.census.consumer_family_readback",
              {{"consumer_family", family},
               {"status", "output_directory_unavailable"},
               {"frame", std::to_string(frame)},
               {"draw", std::to_string(draw)},
               {"sample", std::to_string(sample)},
               {"attachment", attachment},
               {"phase", phase},
               {"xenos_draw", "preserved"},
               {"suppression_eligible", "false"}});
          return;
        }
        const std::string metadata = fmt::format(
            "{{\n  \"schema\": "
            "\"pinyon-shift.consumer-family-readback.v1\",\n"
            "  \"consumer_family\": \"{}\",\n  \"frame\": {},\n"
            "  \"draw\": {},\n  \"sample\": {},\n"
            "  \"attachment\": \"{}\",\n"
            "  \"phase\": \"{}\",\n"
            "  \"source\": {{\"width\":{},\"height\":{},"
            "\"row_pitch\":{},\"dxgi_format\":{},"
            "\"bytes_per_pixel\":{},\"sample_count\":{},"
            "\"source_sample_count\":{},"
            "\"plane_count\":{},\"planes\":{},"
            "\"encoding\":\"{}\",\"bytes\":{},"
            "\"hash\":\"{:016X}\"}},\n"
            "  \"payload\": {{\"file\":\"target.bin\"}},\n"
            "  \"safety\": {{\"output_authority\":\"xenos\","
            "\"xenos_draw_preserved\":true,"
            "\"draw_suppression\":false,"
            "\"resolve_suppression\":false,"
            "\"suppression_allowed\":false}}\n}}\n",
            family, frame, draw, sample, attachment, phase, width, height,
            row_pitch, format, bytes_per_pixel, sample_count,
            source_sample_count, plane_count, planes, encoding, bytes.size(),
            HashBytes(bytes.data(), bytes.size()));
        const auto metadata_bytes = std::span(
            reinterpret_cast<const uint8_t *>(metadata.data()),
            metadata.size());
        if (!WriteSnapshotFile(staging / L"target.bin", bytes) ||
            !WriteSnapshotFile(staging / L"readback.json", metadata_bytes)) {
          std::filesystem::remove_all(staging, error);
          pinyon_shift::diagnostics::RecordEvent(
              "native_renderer.census.consumer_family_readback",
              {{"consumer_family", family},
               {"status", "artifact_write_failed"},
               {"frame", std::to_string(frame)},
               {"draw", std::to_string(draw)},
               {"sample", std::to_string(sample)},
               {"attachment", attachment},
               {"phase", phase},
               {"xenos_draw", "preserved"},
               {"suppression_eligible", "false"}});
          return;
        }
        std::filesystem::rename(staging, output_root, error);
        pinyon_shift::diagnostics::RecordEvent(
            "native_renderer.census.consumer_family_readback",
            {{"consumer_family", family},
             {"status", error ? "artifact_commit_failed" : "captured"},
             {"frame", std::to_string(frame)},
             {"draw", std::to_string(draw)},
             {"sample", std::to_string(sample)},
             {"attachment", attachment},
             {"phase", phase},
             {"source_width", std::to_string(width)},
             {"source_height", std::to_string(height)},
             {"readback_bytes", std::to_string(bytes.size())},
             {"xenos_draw", "preserved"},
             {"draw_suppression", "false"},
             {"resolve_suppression", "false"},
             {"suppression_eligible", "false"}});
      });
  finish();
}

void CompleteConsumerFamilyBeforeReadback(
    const rex::system::GraphicsIsolatedDrawReadback &readback) {
  CompleteConsumerFamilyReadbackArtifact(
      readback, "color", "before");
}

void CompleteConsumerFamilyAfterReadback(
    const rex::system::GraphicsIsolatedDrawReadback &readback) {
  CompleteConsumerFamilyReadbackArtifact(
      readback, "color", "after");
}

void CompleteConsumerFamilyBeforeDepthReadback(
    const rex::system::GraphicsIsolatedDrawReadback &readback) {
  CompleteConsumerFamilyReadbackArtifact(readback, "depth_stencil",
                                         "before");
}

void CompleteConsumerFamilyAfterDepthReadback(
    const rex::system::GraphicsIsolatedDrawReadback &readback) {
  CompleteConsumerFamilyReadbackArtifact(readback, "depth_stencil",
                                         "after");
}

void CompleteIsolatedReadbackArtifact(
    const rex::system::GraphicsIsolatedDrawReadback &readback,
    const char *capture_role, const std::filesystem::path &artifact_root,
    std::jthread &artifact_writer) {
  const auto reject = [&](const char *status) {
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.isolated_draw.readback",
        {{"signature",
          fmt::format("{:016X}", g_isolated_draw.captured_signature)},
         {"status", status},
         {"detail", fmt::format("0x{:08X}", readback.detail)},
         {"frame", std::to_string(g_isolated_draw.captured_frame)},
         {"draw", std::to_string(g_isolated_draw.captured_draw)},
         {"capture_role", capture_role},
         {"output_authority", "xenos"},
         {"suppression_eligible", "false"}});
  };
  if (readback.status !=
      rex::system::GraphicsIsolatedDrawReadbackStatus::kReady) {
    if (readback.status ==
        rex::system::GraphicsIsolatedDrawReadbackStatus::
            kResolveAllocationFailed) {
      reject("resolve_allocation_failed");
    } else if (readback.status ==
        rex::system::GraphicsIsolatedDrawReadbackStatus::kAllocationFailed) {
      reject("allocation_failed");
    } else if (readback.status ==
               rex::system::GraphicsIsolatedDrawReadbackStatus::kMapFailed) {
      reject("map_failed");
    } else {
      reject("unsupported_target");
    }
    return;
  }
  constexpr uint32_t kR16G16B16A16Float = 10;
  constexpr uint32_t kR8G8B8A8Unorm = 28;
  const uint32_t bytes_per_pixel =
      readback.format == kR16G16B16A16Float
          ? 8
          : (readback.format == kR8G8B8A8Unorm ? 4 : 0);
  const uint64_t required_size =
      uint64_t(readback.row_pitch) * readback.height;
  if (!bytes_per_pixel || !readback.data || !readback.width ||
      !readback.height ||
      uint64_t(readback.width) * bytes_per_pixel > readback.row_pitch ||
      required_size > readback.data_size || required_size > SIZE_MAX) {
    reject("unsupported_layout");
    return;
  }

  std::vector<uint8_t> bytes(readback.data,
                             readback.data + size_t(required_size));
  const uint64_t signature = g_isolated_draw.captured_signature;
  const uint64_t frame = g_isolated_draw.captured_frame;
  const uint64_t draw = g_isolated_draw.captured_draw;
  const auto output_root = artifact_root;
  const uint32_t width = readback.width;
  const uint32_t height = readback.height;
  const uint32_t row_pitch = readback.row_pitch;
  const uint32_t format = readback.format;
  artifact_writer = std::jthread(
      [bytes = std::move(bytes), signature, frame, draw, output_root, width,
       height, row_pitch, format, bytes_per_pixel,
       capture_role = std::string(capture_role)]() {
        uint32_t left = width;
        uint32_t top = height;
        uint32_t right = 0;
        uint32_t bottom = 0;
        bool nonzero = false;
        for (uint32_t y = 0; y < height; ++y) {
          const uint8_t *row = bytes.data() + uint64_t(y) * row_pitch;
          for (uint32_t x = 0; x < width; ++x) {
            const uint8_t *pixel = row + uint64_t(x) * bytes_per_pixel;
            bool pixel_nonzero = false;
            for (uint32_t i = 0; i < bytes_per_pixel; ++i) {
              pixel_nonzero |= pixel[i] != 0;
            }
            if (pixel_nonzero) {
              nonzero = true;
              left = std::min(left, x);
              top = std::min(top, y);
              right = std::max(right, x);
              bottom = std::max(bottom, y);
            }
          }
        }
        if (!nonzero) {
          pinyon_shift::diagnostics::RecordEvent(
              "native_renderer.isolated_draw.readback",
              {{"signature", fmt::format("{:016X}", signature)},
               {"status", "empty_target"},
               {"frame", std::to_string(frame)},
               {"draw", std::to_string(draw)},
               {"capture_role", capture_role},
               {"output_authority", "xenos"},
               {"suppression_eligible", "false"}});
          return;
        }

        const uint32_t crop_width = right - left + 1;
        const uint32_t crop_height = bottom - top + 1;
        std::vector<uint8_t> ppm;
        const std::string header =
            fmt::format("P6\n{} {}\n255\n", crop_width, crop_height);
        ppm.insert(ppm.end(), header.begin(), header.end());
        ppm.reserve(ppm.size() + uint64_t(crop_width) * crop_height * 3);
        for (uint32_t y = top; y <= bottom; ++y) {
          const uint8_t *row = bytes.data() + uint64_t(y) * row_pitch;
          for (uint32_t x = left; x <= right; ++x) {
            const uint8_t *pixel = row + uint64_t(x) * bytes_per_pixel;
            if (format == kR16G16B16A16Float) {
              for (uint32_t component = 0; component < 3; ++component) {
                uint16_t half = 0;
                std::memcpy(&half, pixel + component * sizeof(uint16_t),
                            sizeof(half));
                const float value =
                    std::clamp(HalfToFloat(half), 0.0f, 1.0f);
                ppm.push_back(uint8_t(std::lround(value * 255.0f)));
              }
            } else {
              ppm.insert(ppm.end(), pixel, pixel + 3);
            }
          }
        }

        std::filesystem::path staging = output_root;
        staging += L".partial";
        std::error_code error;
        if (std::filesystem::exists(output_root, error) || error ||
            std::filesystem::exists(staging, error) || error ||
            !std::filesystem::create_directories(staging, error) || error) {
          pinyon_shift::diagnostics::RecordEvent(
              "native_renderer.isolated_draw.readback",
              {{"signature", fmt::format("{:016X}", signature)},
               {"status", "output_directory_unavailable"},
               {"capture_role", capture_role},
               {"output_authority", "xenos"},
               {"suppression_eligible", "false"}});
          return;
        }
        const std::string metadata = fmt::format(
            "{{\n  \"schema\": \"pinyon-shift.isolated-draw-readback.v1\",\n"
            "  \"signature\": \"{:016X}\",\n  \"frame\": {},\n"
            "  \"draw\": {},\n  \"capture_role\": \"{}\",\n"
            "  \"source\": {{\"width\":{},"
            "\"height\":{},\"row_pitch\":{},\"dxgi_format\":{},"
            "\"bytes\":{},\"hash\":\"{:016X}\"}},\n"
            "  \"crop\": {{\"left\":{},\"top\":{},\"right\":{},"
            "\"bottom\":{},\"width\":{},\"height\":{}}},\n"
            "  \"image\": {{\"file\":\"isolated.ppm\","
            "\"encoding\":\"ppm-p6-linear-clamp\"}},\n"
            "  \"safety\": {{\"output_authority\":\"xenos\","
            "\"suppression_allowed\":false}}\n}}\n",
            signature, frame, draw, capture_role, width, height, row_pitch,
            format,
            bytes.size(), HashBytes(bytes.data(), bytes.size()), left, top,
            right, bottom, crop_width, crop_height);
        const auto metadata_bytes = std::span(
            reinterpret_cast<const uint8_t *>(metadata.data()),
            metadata.size());
        if (!WriteSnapshotFile(staging / L"isolated.bin", bytes) ||
            !WriteSnapshotFile(staging / L"isolated.ppm", ppm) ||
            !WriteSnapshotFile(staging / L"readback.json", metadata_bytes)) {
          std::filesystem::remove_all(staging, error);
          pinyon_shift::diagnostics::RecordEvent(
              "native_renderer.isolated_draw.readback",
              {{"signature", fmt::format("{:016X}", signature)},
               {"status", "artifact_write_failed"},
               {"capture_role", capture_role},
               {"output_authority", "xenos"},
               {"suppression_eligible", "false"}});
          return;
        }
        std::filesystem::rename(staging, output_root, error);
        pinyon_shift::diagnostics::RecordEvent(
            "native_renderer.isolated_draw.readback",
            {{"signature", fmt::format("{:016X}", signature)},
             {"status", error ? "artifact_commit_failed" : "captured"},
             {"frame", std::to_string(frame)},
             {"draw", std::to_string(draw)},
             {"source_width", std::to_string(width)},
             {"source_height", std::to_string(height)},
             {"crop_width", std::to_string(crop_width)},
             {"crop_height", std::to_string(crop_height)},
             {"readback_bytes", std::to_string(bytes.size())},
             {"capture_role", capture_role},
             {"output_authority", "xenos"},
             {"suppression_eligible", "false"}});
      });
}

void CompleteIsolatedDrawReadback(
    const rex::system::GraphicsIsolatedDrawReadback &readback) {
  CompleteIsolatedReadbackArtifact(
      readback, "native", g_isolated_draw.output_root,
      g_isolated_draw.artifact_writer);
}

void CompleteIsolatedReferenceReadback(
    const rex::system::GraphicsIsolatedDrawReadback &readback) {
  std::filesystem::path reference_root = g_isolated_draw.output_root;
  reference_root += L".xenos";
  CompleteIsolatedReadbackArtifact(
      readback, "xenos", reference_root,
      g_isolated_draw.reference_artifact_writer);
}

void CompleteIsolatedDepthReadbackArtifact(
    const rex::system::GraphicsIsolatedDrawReadback &readback,
    const char *capture_role, const std::filesystem::path &artifact_root,
    std::jthread &artifact_writer) {
  const auto reject = [&](const char *status) {
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.isolated_draw.readback",
        {{"signature",
          fmt::format("{:016X}", g_isolated_draw.captured_signature)},
         {"status", status},
         {"detail", fmt::format("0x{:08X}", readback.detail)},
         {"frame", std::to_string(g_isolated_draw.captured_frame)},
         {"draw", std::to_string(g_isolated_draw.captured_draw)},
         {"capture_role", capture_role},
         {"capture_content", "depth_stencil"},
         {"output_authority", "xenos"},
         {"suppression_eligible", "false"}});
  };
  if (readback.status !=
      rex::system::GraphicsIsolatedDrawReadbackStatus::kReady) {
    if (readback.status ==
        rex::system::GraphicsIsolatedDrawReadbackStatus::
            kResolveAllocationFailed) {
      reject("resolve_allocation_failed");
    } else if (readback.status ==
               rex::system::GraphicsIsolatedDrawReadbackStatus::
                   kAllocationFailed) {
      reject("allocation_failed");
    } else if (readback.status ==
               rex::system::GraphicsIsolatedDrawReadbackStatus::kMapFailed) {
      reject("map_failed");
    } else {
      reject("unsupported_target");
    }
    return;
  }
  if (!readback.data || !readback.width || !readback.height ||
      !readback.sample_count || !readback.plane_count ||
      readback.plane_count >
          rex::system::GraphicsIsolatedDrawReadback::kMaxPlanes ||
      !readback.data_size || readback.data_size > SIZE_MAX) {
    reject("unsupported_layout");
    return;
  }
  for (uint32_t plane = 0; plane < readback.plane_count; ++plane) {
    const uint64_t offset = readback.plane_offsets[plane];
    const uint64_t row_pitch = readback.plane_row_pitches[plane];
    const uint64_t row_size = readback.plane_row_sizes[plane];
    const uint64_t row_count = readback.plane_row_counts[plane];
    const uint64_t end =
        offset + (row_count ? (row_count - 1) * row_pitch : 0) + row_size;
    if (!row_count || !row_size || row_size > row_pitch ||
        end > readback.data_size) {
      reject("unsupported_layout");
      return;
    }
  }

  std::vector<uint8_t> bytes(readback.data,
                             readback.data + size_t(readback.data_size));
  const uint64_t signature = g_isolated_draw.captured_signature;
  const uint64_t frame = g_isolated_draw.captured_frame;
  const uint64_t draw = g_isolated_draw.captured_draw;
  const auto output_root = artifact_root;
  const uint32_t width = readback.width;
  const uint32_t height = readback.height;
  const uint32_t format = readback.format;
  const uint32_t sample_count = readback.sample_count;
  const uint32_t plane_count = readback.plane_count;
  std::array<uint64_t, rex::system::GraphicsIsolatedDrawReadback::kMaxPlanes>
      plane_offsets = {};
  std::array<uint32_t, rex::system::GraphicsIsolatedDrawReadback::kMaxPlanes>
      plane_row_pitches = {};
  std::array<uint32_t, rex::system::GraphicsIsolatedDrawReadback::kMaxPlanes>
      plane_row_sizes = {};
  std::array<uint32_t, rex::system::GraphicsIsolatedDrawReadback::kMaxPlanes>
      plane_row_counts = {};
  std::copy_n(readback.plane_offsets, plane_count, plane_offsets.begin());
  std::copy_n(readback.plane_row_pitches, plane_count,
              plane_row_pitches.begin());
  std::copy_n(readback.plane_row_sizes, plane_count, plane_row_sizes.begin());
  std::copy_n(readback.plane_row_counts, plane_count, plane_row_counts.begin());
  artifact_writer = std::jthread(
      [bytes = std::move(bytes), signature, frame, draw, output_root, width,
       height, format, sample_count, plane_count, plane_offsets,
       plane_row_pitches, plane_row_sizes, plane_row_counts,
       capture_role = std::string(capture_role)]() {
        std::string planes;
        for (uint32_t plane = 0; plane < plane_count; ++plane) {
          if (!planes.empty()) {
            planes += ",";
          }
          planes +=
              fmt::format("{{\"index\":{},\"offset\":{},\"row_pitch\":{},"
                          "\"row_size\":{},\"row_count\":{}}}",
                          plane, plane_offsets[plane], plane_row_pitches[plane],
                          plane_row_sizes[plane], plane_row_counts[plane]);
        }
        std::filesystem::path staging = output_root;
        staging += L".partial";
        std::error_code error;
        if (std::filesystem::exists(output_root, error) || error ||
            std::filesystem::exists(staging, error) || error ||
            !std::filesystem::create_directories(staging, error) || error) {
          pinyon_shift::diagnostics::RecordEvent(
              "native_renderer.isolated_draw.readback",
              {{"signature", fmt::format("{:016X}", signature)},
               {"status", "output_directory_unavailable"},
               {"capture_role", capture_role},
               {"capture_content", "depth_stencil"},
               {"output_authority", "xenos"},
               {"suppression_eligible", "false"}});
          return;
        }
        const std::string metadata = fmt::format(
            "{{\n  \"schema\": "
            "\"pinyon-shift.isolated-depth-readback.v1\",\n"
            "  \"signature\": \"{:016X}\",\n  \"frame\": {},\n"
            "  \"draw\": {},\n  \"capture_role\": \"{}\",\n"
            "  \"capture_content\": \"depth_stencil\",\n"
            "  \"source\": {{\"width\":{},\"height\":{},"
            "\"dxgi_format\":{},\"sample_count\":{},"
            "\"encoding\":\"{}\",\"bytes\":{},\"hash\":\"{:016X}\","
            "\"planes\":[{}]}},\n"
            "  \"safety\": {{\"output_authority\":\"xenos\","
            "\"suppression_allowed\":false}}\n}}\n",
            signature, frame, draw, capture_role, width, height, format,
            sample_count,
            sample_count > 1 ? "depth32_stencil8_sample_tuples"
                             : "d3d12_texture_planes",
            bytes.size(), HashBytes(bytes.data(), bytes.size()), planes);
        const auto metadata_bytes =
            std::span(reinterpret_cast<const uint8_t *>(metadata.data()),
                      metadata.size());
        if (!WriteSnapshotFile(staging / L"isolated.bin", bytes) ||
            !WriteSnapshotFile(staging / L"readback.json", metadata_bytes)) {
          std::filesystem::remove_all(staging, error);
          pinyon_shift::diagnostics::RecordEvent(
              "native_renderer.isolated_draw.readback",
              {{"signature", fmt::format("{:016X}", signature)},
               {"status", "artifact_write_failed"},
               {"capture_role", capture_role},
               {"capture_content", "depth_stencil"},
               {"output_authority", "xenos"},
               {"suppression_eligible", "false"}});
          return;
        }
        std::filesystem::rename(staging, output_root, error);
        pinyon_shift::diagnostics::RecordEvent(
            "native_renderer.isolated_draw.readback",
            {{"signature", fmt::format("{:016X}", signature)},
             {"status", error ? "artifact_commit_failed" : "captured"},
             {"frame", std::to_string(frame)},
             {"draw", std::to_string(draw)},
             {"source_width", std::to_string(width)},
             {"source_height", std::to_string(height)},
             {"sample_count", std::to_string(sample_count)},
             {"plane_count", std::to_string(plane_count)},
             {"readback_bytes", std::to_string(bytes.size())},
             {"capture_role", capture_role},
             {"capture_content", "depth_stencil"},
             {"output_authority", "xenos"},
             {"suppression_eligible", "false"}});
      });
}

void CompleteIsolatedDepthReadback(
    const rex::system::GraphicsIsolatedDrawReadback &readback) {
  std::filesystem::path depth_root = g_isolated_draw.output_root;
  depth_root += L".depth";
  CompleteIsolatedDepthReadbackArtifact(
      readback, "native", depth_root, g_isolated_draw.depth_artifact_writer);
}

void CompleteIsolatedReferenceDepthReadback(
    const rex::system::GraphicsIsolatedDrawReadback &readback) {
  std::filesystem::path depth_root = g_isolated_draw.output_root;
  depth_root += L".depth.xenos";
  CompleteIsolatedDepthReadbackArtifact(
      readback, "xenos", depth_root,
      g_isolated_draw.reference_depth_artifact_writer);
}

void CompleteIsolatedDraw(
    const rex::system::GraphicsIsolatedDrawResult &result) {
  const char *status = "unsupported_state";
  if (result.status ==
      rex::system::GraphicsIsolatedDrawStatus::kRecorded) {
    status = "recorded";
  } else if (result.status ==
             rex::system::GraphicsIsolatedDrawStatus::kTargetCreationFailed) {
    status = "target_creation_failed";
  }
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.isolated_draw.result",
      {{"signature",
        fmt::format("{:016X}", g_isolated_draw.captured_signature)},
       {"status", status},
       {"frame", std::to_string(g_isolated_draw.captured_frame)},
       {"draw", std::to_string(g_isolated_draw.captured_draw)},
       {"target_width", std::to_string(result.target_width)},
       {"target_height", std::to_string(result.target_height)},
       {"native_draw", result.status ==
                                   rex::system::GraphicsIsolatedDrawStatus::kRecorded
                               ? "isolated_only"
                               : "false"},
       {"xenos_draw", "preserved"},
       {"output_authority", "xenos"},
       {"suppression_eligible", "false"}});
}

void CompleteIsolatedPassAnchor(
    const rex::system::GraphicsIsolatedDrawResult &result) {
  g_isolated_draw.pass_anchor_recorded =
      result.status == rex::system::GraphicsIsolatedDrawStatus::kRecorded;
  const char *status = g_isolated_draw.pass_anchor_recorded
                           ? "recorded"
                           : (result.status == rex::system::
                                                   GraphicsIsolatedDrawStatus::
                                                       kTargetCreationFailed
                                  ? "target_creation_failed"
                                  : "unsupported_state");
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.isolated_pass.stage",
      {{"anchor_signature",
        fmt::format("{:016X}", g_pass_follower.target_signature)},
       {"follower_signature",
        fmt::format("{:016X}", g_isolated_draw.target_signature)},
       {"stage", "anchor"},
       {"status", status},
       {"frame", std::to_string(g_isolated_draw.pass_anchor_frame)},
       {"draw", std::to_string(g_isolated_draw.pass_anchor_draw)},
       {"target_width", std::to_string(result.target_width)},
       {"target_height", std::to_string(result.target_height)},
       {"xenos_draw", "preserved"},
       {"output_authority", "xenos"},
       {"suppression_eligible", "false"}});
}

void CompleteIsolatedPassFollower(
    const rex::system::GraphicsIsolatedDrawResult &result) {
  const bool recorded =
      result.status == rex::system::GraphicsIsolatedDrawStatus::kRecorded;
  if (recorded) {
    g_isolated_draw.completed = true;
  }
  const char *status = recorded
                           ? "recorded"
                           : (result.status == rex::system::
                                                   GraphicsIsolatedDrawStatus::
                                                       kTargetCreationFailed
                                  ? "target_creation_failed"
                                  : "unsupported_state");
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.isolated_pass.result",
      {{"anchor_signature",
        fmt::format("{:016X}", g_pass_follower.target_signature)},
       {"follower_signature",
        fmt::format("{:016X}", g_isolated_draw.target_signature)},
       {"status", status},
       {"frame", std::to_string(g_isolated_draw.captured_frame)},
       {"anchor_draw", std::to_string(g_isolated_draw.pass_anchor_draw)},
       {"follower_draw", std::to_string(g_isolated_draw.captured_draw)},
       {"draw_count", recorded ? "2" : "0"},
       {"target_width", std::to_string(result.target_width)},
       {"target_height", std::to_string(result.target_height)},
       {"native_draw", recorded ? "isolated_pass" : "false"},
       {"xenos_draw", "preserved"},
       {"output_authority", "xenos"},
       {"suppression_eligible", "false"}});
}

void CompleteIsolatedPassRepeat(
    const rex::system::GraphicsIsolatedDrawResult &result) {
  const bool recorded =
      result.status == rex::system::GraphicsIsolatedDrawStatus::kRecorded;
  g_isolated_draw.pass_repeat_reported = true;
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.isolated_pass.repeat",
      {{"anchor_signature",
        fmt::format("{:016X}", g_pass_follower.target_signature)},
       {"follower_signature",
        fmt::format("{:016X}", g_isolated_draw.target_signature)},
       {"status", recorded ? "recorded" : "failed"},
       {"frame", std::to_string(g_isolated_draw.frame)},
       {"anchor_draw", std::to_string(g_isolated_draw.pass_anchor_draw)},
       {"follower_draw", std::to_string(g_isolated_draw.draw)},
       {"target_width", std::to_string(result.target_width)},
       {"target_height", std::to_string(result.target_height)},
       {"xenos_draw", "preserved"},
       {"output_authority", "xenos"},
       {"suppression_eligible", "false"}});
}

void CompleteRetainedPassPublication(
    const rex::system::GraphicsIsolatedDrawPublicationResult &result) {
  ++g_pass_publication.attempts;
  g_pass_publication.last_frame = g_isolated_draw.frame;
  g_pass_publication.last_draw = g_isolated_draw.draw;
  const bool published =
      result.status ==
          rex::system::GraphicsIsolatedDrawPublicationStatus::kPublished &&
      result.color_published && result.depth_stencil_published;
  if (published) {
    ++g_pass_publication.published;
  } else {
    ++g_pass_publication.failures;
  }
  if (g_sky_horizon_suppression.armed) {
    g_sky_horizon_suppression.last_frame = g_isolated_draw.frame;
    g_sky_horizon_suppression.last_draw = g_isolated_draw.draw;
    if (g_sky_horizon_suppression.attempt_suppression_requested) {
      ++g_sky_horizon_suppression.attempts;
    } else {
      ++g_sky_horizon_suppression.yielded_attempts;
      g_sky_horizon_suppression.yielded_vertices +=
          g_isolated_draw.prepared_sample.index_count;
    }
    if (result.guest_draw_suppressed &&
        !g_sky_horizon_suppression.attempt_suppression_requested) {
      ++g_sky_horizon_suppression.unexpected_suppressions;
      EnterSuppressionCooldown(g_isolated_draw.frame,
                               "backend_ignored_state_yield");
    } else if (result.guest_draw_suppressed &&
               g_sky_horizon_suppression.attempt_suppression_requested) {
      ++g_sky_horizon_suppression.suppressed;
      g_sky_horizon_suppression.suppressed_vertices +=
          g_isolated_draw.prepared_sample.index_count;
      g_sky_horizon_suppression.last_successful_frame =
          g_isolated_draw.frame;
    } else if (g_sky_horizon_suppression.attempt_suppression_requested) {
      ++g_sky_horizon_suppression.fallbacks;
      EnterSuppressionCooldown(g_isolated_draw.frame,
                               published ? "backend_preserved_follower"
                                         : "publication_failure");
    } else if (published) {
      AdvanceSuppressionWarmup(g_isolated_draw.frame);
    } else {
      EnterSuppressionCooldown(g_isolated_draw.frame,
                               "warmup_publication_failure");
    }
  }
  const char *status = "unavailable";
  switch (result.status) {
  case rex::system::GraphicsIsolatedDrawPublicationStatus::kPublished:
    status = published ? "published" : "incomplete";
    break;
  case rex::system::GraphicsIsolatedDrawPublicationStatus::kUnsupportedPath:
    status = "unsupported_path";
    break;
  case rex::system::GraphicsIsolatedDrawPublicationStatus::kTargetMismatch:
    status = "target_mismatch";
    break;
  case rex::system::GraphicsIsolatedDrawPublicationStatus::kUnavailable:
    break;
  }
  if (g_pass_publication.detail_events >= kPassPublicationDetailLimit) {
    ++g_pass_publication.detail_overflow;
    return;
  }
  ++g_pass_publication.detail_events;
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.retained_pass.publication",
      {{"anchor_signature",
        fmt::format("{:016X}", g_pass_follower.target_signature)},
       {"follower_signature",
        fmt::format("{:016X}", g_isolated_draw.target_signature)},
       {"status", status},
       {"frame", std::to_string(g_isolated_draw.frame)},
       {"follower_draw", std::to_string(g_isolated_draw.draw)},
       {"target_width", std::to_string(result.target_width)},
       {"target_height", std::to_string(result.target_height)},
       {"sample_count", std::to_string(result.sample_count)},
       {"color", result.color_published ? "published" : "preserved_xenos"},
       {"depth_stencil",
        result.depth_stencil_published ? "published" : "preserved_xenos"},
       {"guest_target_content", published ? "native_retained_pass" : "xenos"},
       {"xenos_draw", result.guest_draw_suppressed
                          ? "anchor_preserved_follower_suppressed"
                          : "preserved"},
       {"draw_suppression",
        result.guest_draw_suppressed ? "follower" : "false"},
       {"resolve_suppression", "false"},
       {"side_effects", "setup_barriers_resolves_consumers_preserved"},
       {"fallback", result.guest_draw_suppressed
                        ? (g_sky_horizon_suppression
                                   .attempt_suppression_requested
                               ? "not_needed"
                               : "unsafe_unexpected_suppression")
                        : (g_sky_horizon_suppression
                                   .attempt_suppression_requested
                               ? "original_follower_executed"
                               : "state_gate_xenos")},
       {"state_gate",
        SuppressionRuntimeModeName(g_sky_horizon_suppression.mode)},
       {"yield_reason", g_sky_horizon_suppression.last_yield_reason},
       {"suppression_eligible",
        g_sky_horizon_suppression.attempt_suppression_requested ? "true"
                                                                 : "false"}});
}

void RequestIsolatedDraw(
    const rex::system::GraphicsPreparedDrawObservation &,
    rex::system::GraphicsIsolatedDrawRequest &request) {
  if (g_consumer_family_marker.current_match) {
    request.consumer_reference_marker_requested = true;
    ++g_consumer_family_marker.marker_requests;
    if (g_consumer_family_marker.readback_requested &&
        !g_consumer_family_marker.readback_in_flight &&
        g_consumer_family_marker.readback_requests <
            g_consumer_family_marker.readback_sample_limit) {
      g_consumer_family_marker.readback_in_flight = true;
      g_consumer_family_marker.current_capture_completions = 0;
      ++g_consumer_family_marker.readback_requests;
      g_consumer_family_marker.current_capture_index =
          uint32_t(g_consumer_family_marker.readback_requests);
      request.consumer_reference_readback_requested = true;
      request.consumer_reference_depth_readback_requested = true;
      request.consumer_reference_before_readback_completion =
          &CompleteConsumerFamilyBeforeReadback;
      request.consumer_reference_after_readback_completion =
          &CompleteConsumerFamilyAfterReadback;
      request.consumer_reference_before_depth_readback_completion =
          &CompleteConsumerFamilyBeforeDepthReadback;
      request.consumer_reference_after_depth_readback_completion =
          &CompleteConsumerFamilyAfterDepthReadback;
    }
  }
  if (!g_isolated_draw.requested || !g_isolated_draw.valid ||
      !g_isolated_draw.prepared_candidate_valid) {
    return;
  }
  const bool pass_mode = g_pass_follower.requested &&
                         g_pass_follower.valid &&
                         !g_isolated_draw
                              .auto_select_fresh_visibility_candidate &&
                         g_pass_follower.target_signature !=
                             g_isolated_draw.target_signature;
  const bool candidate_eligible =
      g_isolated_draw.prepared_candidate_eligible &&
      (!g_isolated_draw.require_fresh_visibility_candidate ||
       g_isolated_draw.prepared_visibility_candidate_fresh) &&
      (!g_isolated_draw.require_title_lod_candidate ||
       g_isolated_draw.prepared_title_lod_valid);
  if (pass_mode) {
    const uint64_t signature = g_isolated_draw.prepared_signature;
    if (signature == g_pass_follower.target_signature) {
      g_isolated_draw.awaiting_pass_follower = false;
      g_isolated_draw.pass_anchor_recorded = false;
      if (!candidate_eligible) {
        return;
      }
      g_isolated_draw.pass_anchor_frame = g_isolated_draw.frame;
      g_isolated_draw.pass_anchor_draw = g_isolated_draw.draw;
      g_isolated_draw.awaiting_pass_follower = true;
      g_isolated_draw.pass_anchor_recorded = g_isolated_draw.completed;
      request.requested = true;
      request.frame_sequence = g_isolated_draw.frame;
      request.retain_target = true;
      request.reference_marker_requested = true;
      request.completion = g_isolated_draw.completed
                               ? nullptr
                               : &CompleteIsolatedPassAnchor;
      return;
    }
    if (!g_isolated_draw.awaiting_pass_follower) {
      return;
    }
    const bool adjacent =
        signature == g_isolated_draw.target_signature &&
        g_isolated_draw.frame == g_isolated_draw.pass_anchor_frame &&
        g_isolated_draw.draw == g_isolated_draw.pass_anchor_draw + 1;
    g_isolated_draw.awaiting_pass_follower = false;
    if (!adjacent || !g_isolated_draw.pass_anchor_recorded ||
        !candidate_eligible) {
      return;
    }
    if (g_pass_consumer_trace.pending) {
      ++g_pass_consumer_trace.superseded_without_resolve;
    }
    g_pass_consumer_trace.pending_target = g_isolated_draw.prepared_sample;
    g_pass_consumer_trace.pending_frame = g_isolated_draw.frame;
    g_pass_consumer_trace.pending_draw = g_isolated_draw.draw;
    ++g_pass_consumer_trace.family_occurrences;
    g_pass_consumer_trace.pending = true;
    request.requested = true;
    request.frame_sequence = g_isolated_draw.frame;
    request.reuse_target = true;
    request.reference_marker_requested = true;
    if (g_pass_publication.requested && g_pass_publication.valid) {
      request.publish_to_guest_requested = true;
      request.publication_completion = &CompleteRetainedPassPublication;
      request.suppress_guest_draw_if_published =
          PrepareSuppressionAttempt(g_isolated_draw.frame);
    }
    if (!g_isolated_draw.completed) {
      g_isolated_draw.captured_signature = signature;
      g_isolated_draw.captured_frame = g_isolated_draw.frame;
      g_isolated_draw.captured_draw = g_isolated_draw.draw;
      request.readback_requested = g_isolated_draw.readback_requested;
      request.reference_readback_requested =
          g_isolated_draw.readback_requested;
      request.depth_readback_requested = g_isolated_draw.readback_requested;
      request.reference_depth_readback_requested =
          g_isolated_draw.readback_requested;
      request.completion = &CompleteIsolatedPassFollower;
      request.readback_completion = g_isolated_draw.readback_requested
                                        ? &CompleteIsolatedDrawReadback
                                        : nullptr;
      request.reference_readback_completion =
          g_isolated_draw.readback_requested
              ? &CompleteIsolatedReferenceReadback
              : nullptr;
      request.depth_readback_completion =
          g_isolated_draw.readback_requested
              ? &CompleteIsolatedDepthReadback
              : nullptr;
      request.reference_depth_readback_completion =
          g_isolated_draw.readback_requested
              ? &CompleteIsolatedReferenceDepthReadback
              : nullptr;
    } else if (!g_isolated_draw.pass_repeat_reported) {
      request.completion = &CompleteIsolatedPassRepeat;
    }
    return;
  }
  if (g_isolated_draw.auto_select_fresh_visibility_candidate &&
      !g_isolated_draw.target_signature) {
    if (!candidate_eligible) {
      if (g_isolated_draw.prepared_candidate_eligible &&
          g_isolated_draw.prepared_visibility_candidate_fresh &&
          g_isolated_draw.require_title_lod_candidate &&
          !g_isolated_draw.prepared_title_lod_valid &&
          !g_isolated_draw.title_lod_wait_reported) {
        pinyon_shift::diagnostics::RecordEvent(
            "native_renderer.isolated_draw.title_lod_gate",
            {{"status", "waiting_for_exact_title_lod_observation"},
             {"frame", std::to_string(g_isolated_draw.frame)},
             {"draw", std::to_string(g_isolated_draw.draw)},
             {"mechanically_eligible", "true"},
             {"fresh_visibility_candidate", "true"},
             {"title_lod_valid", "false"},
             {"native_draw", "false"},
             {"xenos_draw", "preserved"},
             {"output_authority", "xenos"},
             {"suppression_eligible", "false"}});
        g_isolated_draw.title_lod_wait_reported = true;
      }
      return;
    }
    g_isolated_draw.target_signature = g_isolated_draw.prepared_signature;
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.isolated_draw.auto_selection",
        {{"signature",
          fmt::format("{:016X}", g_isolated_draw.target_signature)},
         {"status",
          g_isolated_draw.require_title_lod_candidate
              ? "locked_first_fresh_eligible_title_lod_candidate"
              : "locked_first_fresh_eligible_candidate"},
         {"frame", std::to_string(g_isolated_draw.frame)},
         {"draw", std::to_string(g_isolated_draw.draw)},
         {"mechanically_eligible", "true"},
         {"fresh_visibility_candidate", "true"},
         {"title_lod_gate_required",
          g_isolated_draw.require_title_lod_candidate ? "true" : "false"},
         {"title_lod_valid",
          g_isolated_draw.prepared_title_lod_valid ? "true" : "false"},
         {"title_lod_index",
          std::to_string(g_isolated_draw.prepared_title_lod_index)},
         {"native_draw", "isolated_only"},
         {"xenos_draw", "preserved"},
         {"output_authority", "xenos"},
         {"suppression_eligible", "false"}});
  }
  if (g_isolated_draw.prepared_signature !=
      g_isolated_draw.target_signature) {
    return;
  }
  request.reference_marker_requested = true;
  if (g_isolated_draw.completed) {
    // Keep the private replay visible to frame debuggers after the one-shot
    // result has been recorded. This path has no readback or completion
    // callback, and the authoritative Xenos draw still follows unmodified.
    request.requested = candidate_eligible;
    request.frame_sequence = request.requested ? g_isolated_draw.frame : 0;
    return;
  }
  if (g_isolated_draw.prepared_candidate_eligible &&
      g_isolated_draw.require_fresh_visibility_candidate &&
      !g_isolated_draw.prepared_visibility_candidate_fresh) {
    if (!g_isolated_draw.visibility_wait_reported) {
      pinyon_shift::diagnostics::RecordEvent(
          "native_renderer.isolated_draw.visibility_gate",
          {{"signature",
            fmt::format("{:016X}", g_isolated_draw.prepared_signature)},
           {"status", "waiting_for_fresh_selected_candidate"},
           {"frame", std::to_string(g_isolated_draw.frame)},
           {"draw", std::to_string(g_isolated_draw.draw)},
           {"mechanically_eligible", "true"},
           {"fresh_visibility_candidate", "false"},
           {"native_draw", "false"},
           {"xenos_draw", "preserved"},
           {"output_authority", "xenos"},
           {"suppression_eligible", "false"}});
      g_isolated_draw.visibility_wait_reported = true;
    }
    return;
  }
  g_isolated_draw.completed = true;
  if (!candidate_eligible) {
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.isolated_draw.result",
        {{"signature",
          fmt::format("{:016X}", g_isolated_draw.prepared_signature)},
         {"status", "rejected_by_title_gate"},
         {"frame", std::to_string(g_isolated_draw.frame)},
         {"draw", std::to_string(g_isolated_draw.draw)},
         {"native_draw", "false"},
         {"mechanically_eligible",
          g_isolated_draw.prepared_candidate_eligible ? "true" : "false"},
         {"fresh_visibility_candidate",
          g_isolated_draw.prepared_visibility_candidate_fresh ? "true"
                                                              : "false"},
         {"visibility_gate_required",
          g_isolated_draw.require_fresh_visibility_candidate ? "true"
                                                             : "false"},
         {"xenos_draw", "preserved"},
         {"output_authority", "xenos"},
         {"suppression_eligible", "false"}});
    return;
  }
  g_isolated_draw.captured_signature = g_isolated_draw.prepared_signature;
  g_isolated_draw.captured_frame = g_isolated_draw.frame;
  g_isolated_draw.captured_draw = g_isolated_draw.draw;
  request.requested = true;
  request.frame_sequence = g_isolated_draw.frame;
  request.readback_requested = g_isolated_draw.readback_requested;
  request.reference_readback_requested =
      g_isolated_draw.readback_requested;
  request.depth_readback_requested = g_isolated_draw.readback_requested;
  request.reference_depth_readback_requested =
      g_isolated_draw.readback_requested;
  request.completion = &CompleteIsolatedDraw;
  request.readback_completion = g_isolated_draw.readback_requested
                                    ? &CompleteIsolatedDrawReadback
                                    : nullptr;
  request.reference_readback_completion =
      g_isolated_draw.readback_requested
          ? &CompleteIsolatedReferenceReadback
          : nullptr;
  request.depth_readback_completion =
      g_isolated_draw.readback_requested ? &CompleteIsolatedDepthReadback
                                         : nullptr;
  request.reference_depth_readback_completion =
      g_isolated_draw.readback_requested
          ? &CompleteIsolatedReferenceDepthReadback
          : nullptr;
}

void EmitDrawCensusWindow(uint64_t last_frame_value) {
  std::array<size_t, kSignatureCapacity> order{};
  for (size_t i = 0; i < order.size(); ++i) {
    order[i] = i;
  }
  std::sort(order.begin(), order.end(), [](size_t left, size_t right) {
    const DrawSignatureEntry &left_entry = g_draw_census.entries[left];
    const DrawSignatureEntry &right_entry = g_draw_census.entries[right];
    if (left_entry.draw_count != right_entry.draw_count) {
      return left_entry.draw_count > right_entry.draw_count;
    }
    return left_entry.signature < right_entry.signature;
  });

  const std::string first_frame =
      std::to_string(g_draw_census.window_first_frame);
  const std::string last_frame = std::to_string(last_frame_value);
  const std::string draws = std::to_string(g_draw_census.window_draw_count);
  const std::string unique =
      std::to_string(g_draw_census.unique_signature_count);
  const std::string overflow =
      std::to_string(g_draw_census.overflow_draw_count);
  const std::string capacity = std::to_string(kSignatureCapacity);
  pinyon_shift::diagnostics::RecordEvent("native_renderer.census.draw_window",
                                         {{"first_frame", first_frame},
                                          {"last_frame", last_frame},
                                          {"draws", draws},
                                          {"unique_signatures", unique},
                                          {"overflow_draws", overflow},
                                          {"signature_capacity", capacity},
                                          {"summary_limit", "16"}});

  size_t emitted = 0;
  for (size_t index : order) {
    const DrawSignatureEntry &entry = g_draw_census.entries[index];
    if (!entry.draw_count || emitted == kSummaryLimit) {
      break;
    }
    const auto &sample = entry.sample;
    const std::string rank = std::to_string(++emitted);
    const std::string count = std::to_string(entry.draw_count);
    const std::string first = std::to_string(entry.first_frame);
    const std::string last = std::to_string(entry.last_frame);
    const std::string index_count = std::to_string(sample.index_count);
    const std::string signature = fmt::format("{:016X}", entry.signature);
    const std::string vertex_shader =
        fmt::format("{:016X}", sample.vertex_shader_hash);
    const std::string pixel_shader =
        fmt::format("{:016X}", sample.pixel_shader_hash);
    const std::string primitive = std::to_string(sample.primitive_type);
    const std::string target_state = fmt::format(
        "{:08X}:{:08X}:{:08X}:{:08X}:{:08X}:{:08X}", sample.surface_info,
        sample.color_info[0], sample.color_info[1], sample.color_info[2],
        sample.color_info[3], sample.depth_info);
    const std::string scissor = fmt::format(
        "{:08X}:{:08X}", sample.window_scissor_tl, sample.window_scissor_br);
    const std::string index_buffer = fmt::format(
        "{:08X}:{}", sample.index_buffer_address, sample.index_buffer_length);
    const std::string index_state =
        fmt::format("format={};endianness={}", sample.index_format,
                    sample.index_endianness);
    std::string vertex_fetches;
    const uint32_t bounded_binding_count =
        std::min(sample.vertex_binding_count,
                 rex::system::kGraphicsVertexBindingObservationLimit);
    for (uint32_t i = 0; i < bounded_binding_count; ++i) {
      const auto &binding = sample.vertex_bindings[i];
      if (!vertex_fetches.empty()) {
        vertex_fetches += ";";
      }
      vertex_fetches += fmt::format(
          "{}:{:08X}:{}:{}:{}", binding.fetch_constant, binding.address,
          binding.size, binding.stride_words, binding.endianness);
    }
    const bool query_draw =
        sample.viz_query_condition || (sample.pa_sc_viz_query & 1);
    const std::string pipeline_state =
        fmt::format("color_mask={:08X};blend={:08X}:{:08X}:{:08X}:{:08X};"
                    "depth={:08X};raster={:08X};vertex={:08X}",
                    sample.rb_color_mask, sample.rb_blendcontrol[0],
                    sample.rb_blendcontrol[1], sample.rb_blendcontrol[2],
                    sample.rb_blendcontrol[3], sample.rb_depthcontrol,
                    sample.pa_su_sc_mode_cntl, sample.pa_su_vtx_cntl);
    const std::string flags = fmt::format(
        "indexed={};explicit_major={};memexport={};query={};"
        "resolved_input={};opaque={};vertex_overflow={}",
        sample.indexed, sample.major_mode_explicit, sample.vertex_memexport,
        query_draw, entry.samples_resolved_target, IsOpaqueColorState(sample),
        bool(sample.vertex_binding_overflow));
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.census.draw_signature",
        {{"rank", rank},
         {"signature", signature},
         {"draws", count},
         {"first_frame", first},
         {"last_frame", last},
         {"vertex_shader", vertex_shader},
         {"pixel_shader", pixel_shader},
         {"primitive", primitive},
         {"index_count", index_count},
         {"target_state", target_state},
         {"scissor", scissor},
         {"index_buffer", index_buffer},
         {"index_state", index_state},
         {"vertex_binding_count", std::to_string(sample.vertex_binding_count)},
         {"vertex_fetches", vertex_fetches},
         {"texture_fetch_count",
          std::to_string(std::popcount(sample.texture_fetch_mask))},
         {"pipeline_state", pipeline_state},
         {"indexed", sample.indexed ? "true" : "false"},
         {"query", query_draw ? "true" : "false"},
         {"memexport", sample.vertex_memexport ? "true" : "false"},
         {"resolved_input", entry.samples_resolved_target ? "true" : "false"},
         {"opaque", IsOpaqueColorState(sample) ? "true" : "false"},
         {"vertex_overflow", sample.vertex_binding_overflow ? "true" : "false"},
         {"flags", flags}});
  }

  EmitCandidateCensusWindow(last_frame_value);
  ResetDrawCensus();
}

bool CopyReadsPassTarget(
    const rex::system::GraphicsCopyObservation &copy,
    const rex::system::GraphicsDrawObservation &target) {
  if (copy.surface_info != target.surface_info) {
    return false;
  }
  const uint32_t source = copy.rb_copy_control & 7;
  if (source < 4) {
    return copy.color_info[source] == target.color_info[source];
  }
  return source == 4 && copy.depth_info == target.depth_info;
}

bool ShouldEmitPassConsumerDetail() {
  if (g_pass_consumer_trace.detail_events == kPassConsumerDetailLimit) {
    ++g_pass_consumer_trace.detail_overflow;
    return false;
  }
  ++g_pass_consumer_trace.detail_events;
  return true;
}

void ObservePassConsumerSignature(
    const rex::system::GraphicsDrawObservation &observation,
    const rex::system::GraphicsPreparedDrawObservation &prepared,
    uint64_t base_fetch_mask, uint64_t mip_fetch_mask) {
  const uint64_t signature = DrawSignature(observation);
  PassConsumerSignatureEntry *entry = nullptr;
  for (size_t i = 0; i < g_pass_consumer_trace.consumer_signature_count; ++i) {
    if (g_pass_consumer_trace.consumer_signatures[i].signature == signature) {
      entry = &g_pass_consumer_trace.consumer_signatures[i];
      break;
    }
  }
  if (!entry) {
    if (g_pass_consumer_trace.consumer_signature_count ==
        kPassConsumerSignatureCapacity) {
      ++g_pass_consumer_trace.consumer_signature_overflow;
      return;
    }
    entry = &g_pass_consumer_trace.consumer_signatures
                 [g_pass_consumer_trace.consumer_signature_count++];
    entry->signature = signature;
    entry->first_frame = observation.frame_sequence;
    entry->sample = observation;
    entry->prepared_sample = prepared;
    entry->prepared_valid = true;
  }
  ++entry->sample_events;
  entry->last_frame = observation.frame_sequence;
  if (observation.viz_query_condition || (observation.pa_sc_viz_query & 1)) {
    ++entry->query_sample_events;
  }
  if (observation.vertex_memexport) {
    ++entry->memexport_sample_events;
  }
  entry->family_base_fetch_mask |= base_fetch_mask;
  entry->family_mip_fetch_mask |= mip_fetch_mask;
}

void CommitPassConsumer(
    const rex::system::GraphicsDrawObservation &observation,
    const rex::system::GraphicsPreparedDrawObservation &prepared,
    const PendingCandidateObservation &candidate) {
  if (!candidate.family_sample_references) {
    return;
  }
  bool active_family_target = false;
  for (size_t i = 0; i < candidate.family_target_count; ++i) {
    active_family_target |=
        g_dependency_census.targets[candidate.family_targets[i]]
            .latest_resolve_from_traced_family;
  }
  if (!active_family_target) {
    return;
  }
  ++g_pass_consumer_trace.sampled_draws;
  g_pass_consumer_trace.sample_references +=
      candidate.family_sample_references;
  if (g_consumer_family_marker.requested &&
      g_consumer_family_marker.valid &&
      observation.vertex_shader_hash ==
          g_consumer_family_marker.vertex_shader_hash &&
      observation.pixel_shader_hash ==
          g_consumer_family_marker.pixel_shader_hash &&
      prepared.vertex_specialization_mask ==
          g_consumer_family_marker.vertex_specialization_mask &&
      prepared.pixel_specialization_mask ==
          g_consumer_family_marker.pixel_specialization_mask) {
    g_consumer_family_marker.current_match = true;
    ++g_consumer_family_marker.matched_draws;
    if (g_consumer_family_marker.readback_requested &&
        !g_consumer_family_marker.readback_in_flight &&
        g_consumer_family_marker.readback_requests <
            g_consumer_family_marker.readback_sample_limit) {
      g_consumer_family_marker.capture_frame = observation.frame_sequence;
      g_consumer_family_marker.capture_draw = observation.draw_sequence;
    }
  }
  ObservePassConsumerSignature(observation, prepared,
                               candidate.family_base_fetch_mask,
                               candidate.family_mip_fetch_mask);
  for (size_t i = 0; i < candidate.family_target_count; ++i) {
    ResolveTargetEntry &target =
        g_dependency_census.targets[candidate.family_targets[i]];
    if (!target.latest_resolve_from_traced_family) {
      continue;
    }
    ++target.family_sampled_draw_count;
    target.family_sample_reference_count +=
        candidate.family_sample_references;
    if (!target.family_consumer_reported) {
      ++g_pass_consumer_trace.sampled_resolves;
      target.family_consumer_reported = true;
      if (ShouldEmitPassConsumerDetail()) {
        pinyon_shift::diagnostics::RecordEvent(
            "native_renderer.census.pass_family_consumer",
            {{"anchor_signature",
              fmt::format("{:016X}", g_pass_follower.target_signature)},
             {"follower_signature",
              fmt::format("{:016X}", g_isolated_draw.target_signature)},
             {"family_frame", std::to_string(target.family_frame)},
             {"family_follower_draw", std::to_string(target.family_draw)},
             {"resolve_frame", std::to_string(target.last_resolve_frame)},
             {"address", fmt::format("{:08X}", target.address)},
             {"length", std::to_string(target.length)},
             {"consumer_frame", std::to_string(observation.frame_sequence)},
             {"consumer_draw", std::to_string(observation.draw_sequence)},
             {"consumer_signature",
              fmt::format("{:016X}", DrawSignature(observation))},
             {"fetch_index",
              std::to_string(candidate.first_family_fetch_index)},
             {"fetch_kind",
              candidate.first_family_fetch_is_mip ? "mip" : "base"},
             {"query", observation.viz_query_condition ||
                           (observation.pa_sc_viz_query & 1)
                       ? "true"
                       : "false"},
             {"memexport", observation.vertex_memexport ? "true" : "false"},
             {"prepared_metadata", "observed"},
             {"xenos_draw", "preserved"},
             {"suppression_eligible", "false"}});
      }
    }
  }
}

void DiscardPendingPassConsumer() {
  if (!g_pending_candidate.valid ||
      !g_pending_candidate.family_sample_references) {
    return;
  }
  ++g_pass_consumer_trace.unprepared_consumer_draws;
  g_pass_consumer_trace.unprepared_consumer_references +=
      g_pending_candidate.family_sample_references;
}

void ObserveDrawOutcome(
    const rex::system::GraphicsDrawOutcomeObservation &observation) {
  ++g_backend_draw_outcomes_observed;
  const uint32_t outcome = uint32_t(observation.status);
  if (outcome >= g_backend_draw_outcome_counts.size()) {
    ++g_backend_draw_outcome_mismatches;
  } else {
    ++g_backend_draw_outcome_counts[outcome];
  }
  if (observation.prepared) {
    if (g_pending_candidate.valid) {
      ++g_backend_draw_outcome_mismatches;
      DiscardPendingPassConsumer();
      g_pending_candidate.valid = false;
    }
    return;
  }
  if (!g_pending_candidate.valid) {
    ++g_backend_draw_outcome_mismatches;
    return;
  }
  const bool exact_candidate =
      observation.frame_sequence ==
          g_pending_candidate.sample.frame_sequence &&
      observation.draw_sequence == g_pending_candidate.sample.draw_sequence &&
      observation.packet_physical_address ==
          g_pending_candidate.sample.packet_physical_address;
  ++g_candidate_unprepared_draw_count;
  if (!exact_candidate || !outcome ||
      outcome >= g_backend_draw_outcome_counts.size()) {
    ++g_backend_draw_outcome_mismatches;
  } else if (g_pending_candidate.title_origin.valid) {
    ++g_title_matched_unprepared_draws;
    ++g_title_backend_outcome_counts[outcome];
    RecordTitleDrawProvenance(DrawSignature(g_pending_candidate.sample),
                              false, outcome, g_pending_candidate.sample,
                              g_pending_candidate.title_origin);
  }
  DiscardPendingPassConsumer();
  g_pending_candidate.valid = false;
}

void ObserveCopy(const rex::system::GraphicsCopyObservation &observation) {
  AdvanceDependencyWindow(observation.frame_sequence);
  if (!observation.succeeded) {
    ++g_dependency_census.window_failed_copy_count;
    return;
  }
  if (!observation.written_length) {
    ++g_dependency_census.window_zero_length_copy_count;
    return;
  }

  ++g_dependency_census.window_resolve_count;
  g_dependency_census.window_resolve_bytes += observation.written_length;
  const size_t target_index = ResolveTargetIndex(observation.written_address);
  if (target_index == kResolveTargetCapacity) {
    ++g_dependency_census.target_overflow_count;
    return;
  }

  ResolveTargetEntry &target = g_dependency_census.targets[target_index];
  const bool family_resolve = g_pass_consumer_trace.pending &&
                              CopyReadsPassTarget(
                                  observation,
                                  g_pass_consumer_trace.pending_target);
  if (target.latest_resolve_from_traced_family) {
    if (!target.family_sampled_draw_count) {
      ++g_pass_consumer_trace.overwritten_unsampled;
    }
    target.latest_resolve_from_traced_family = false;
    target.family_consumer_reported = false;
  }
  if (!target.resolve_count) {
    target.address = observation.written_address;
    target.first_resolve_frame = observation.frame_sequence;
    ++g_dependency_census.target_count;
  }
  target.length = observation.written_length;
  target.maximum_length =
      std::max(target.maximum_length, observation.written_length);
  ++target.resolve_count;
  target.resolved_bytes += observation.written_length;
  target.last_resolve_frame = observation.frame_sequence;
  ++target.window_resolve_count;
  target.sample = observation;
  if (family_resolve) {
    target.latest_resolve_from_traced_family = true;
    target.family_consumer_reported = false;
    target.family_frame = g_pass_consumer_trace.pending_frame;
    target.family_draw = g_pass_consumer_trace.pending_draw;
    target.family_sampled_draw_count = 0;
    target.family_sample_reference_count = 0;
    ++g_pass_consumer_trace.family_resolves;
    g_pass_consumer_trace.family_resolve_bytes += observation.written_length;
    ArmGuestCpuVisibility(observation.written_address,
                          observation.written_length);
    if (ShouldEmitPassConsumerDetail()) {
      pinyon_shift::diagnostics::RecordEvent(
          "native_renderer.census.pass_family_resolve",
          {{"anchor_signature",
            fmt::format("{:016X}", g_pass_follower.target_signature)},
           {"follower_signature",
            fmt::format("{:016X}", g_isolated_draw.target_signature)},
           {"family_frame", std::to_string(target.family_frame)},
           {"family_follower_draw", std::to_string(target.family_draw)},
           {"resolve_frame", std::to_string(observation.frame_sequence)},
           {"resolve_sequence", std::to_string(observation.copy_sequence)},
           {"address", fmt::format("{:08X}", observation.written_address)},
           {"length", std::to_string(observation.written_length)},
           {"copy_source", std::to_string(observation.rb_copy_control & 7)},
           {"classification", "tracked_guest_gpu_output"},
           {"xenos_draw", "preserved"},
           {"suppression_eligible", "false"}});
    }
    g_pass_consumer_trace.pending = false;
  }
  MapResolveRange(target_index, observation.written_address,
                  observation.written_length);
}

void EmitResolvedTextureDependency(
    const rex::system::GraphicsDrawObservation &observation,
    const ResolveTargetEntry &target, uint32_t fetch_index, bool is_mip) {
  pinyon_shift::diagnostics::RecordEvent(
      "native_renderer.census.resolve_dependency",
      {{"address", fmt::format("{:08X}", target.address)},
       {"length", std::to_string(target.length)},
       {"resolve_frame", std::to_string(target.last_resolve_frame)},
       {"sample_frame", std::to_string(observation.frame_sequence)},
       {"sample_draw", std::to_string(observation.draw_sequence)},
       {"fetch_index", std::to_string(fetch_index)},
       {"fetch_kind", is_mip ? "mip" : "base"},
       {"conditional_draw", observation.viz_query_condition ? "true" : "false"},
       {"query_state", (observation.pa_sc_viz_query & 1) ? "true" : "false"},
       {"memexport_draw", observation.vertex_memexport ? "true" : "false"},
       {"presentation_only", "unknown_uninstrumented"},
       {"guest_cpu_read", "unknown_uninstrumented"},
       {"query_dependency", "unknown_uninstrumented"},
       {"semantic_role", "unknown_unclassified"},
       {"suppression_eligible", "false"}});
}

void ObserveResolvedFetch(
    const rex::system::GraphicsDrawObservation &observation,
    uint32_t fetch_index, uint32_t address, bool is_mip,
    std::array<size_t, 64> &sampled_targets, size_t &sampled_target_count,
    PendingCandidateObservation &candidate) {
  if (!address) {
    return;
  }
  const size_t target_index = FindResolveTarget(address);
  if (target_index == kResolveTargetCapacity) {
    return;
  }

  ResolveTargetEntry &target = g_dependency_census.targets[target_index];
  ++target.sample_reference_count;
  ++g_dependency_census.window_sample_reference_count;
  if (target.latest_resolve_from_traced_family) {
    if (!candidate.family_sample_references) {
      candidate.first_family_fetch_index = fetch_index;
      candidate.first_family_fetch_is_mip = is_mip;
    }
    ++candidate.family_sample_references;
    if (fetch_index < 64) {
      (is_mip ? candidate.family_mip_fetch_mask
              : candidate.family_base_fetch_mask) |= UINT64_C(1) << fetch_index;
    }
  }
  target.last_fetch_index = fetch_index;
  target.last_fetch_was_mip = is_mip;
  for (size_t i = 0; i < sampled_target_count; ++i) {
    if (sampled_targets[i] == target_index) {
      return;
    }
  }
  sampled_targets[sampled_target_count++] = target_index;

  const bool first_sample = !target.sampled_draw_count;
  if (first_sample) {
    target.first_sample_frame = observation.frame_sequence;
  }
  if (!target.window_sampled_draw_count) {
    ++g_dependency_census.window_sampled_target_count;
  }
  ++target.sampled_draw_count;
  ++target.window_sampled_draw_count;
  if (target.latest_resolve_from_traced_family) {
    candidate.family_targets[candidate.family_target_count++] = target_index;
  }
  target.last_sample_frame = observation.frame_sequence;
  if (observation.viz_query_condition) {
    ++target.conditional_sample_draw_count;
  }
  if (observation.pa_sc_viz_query & 1) {
    ++target.query_state_sample_draw_count;
  }
  if (observation.vertex_memexport) {
    ++target.memexport_sample_draw_count;
  }
  if (first_sample) {
    EmitResolvedTextureDependency(observation, target, fetch_index, is_mip);
  }
}

void RecordCandidate(
    const rex::system::GraphicsDrawObservation &observation,
    bool samples_resolved_target,
    const rex::system::GraphicsPreparedDrawObservation &prepared) {
  ++g_candidate_census.window_draw_count;
  const uint64_t signature =
      CandidateSignature(observation, samples_resolved_target, prepared);
  TryScanCandidateIndices(observation, signature);
  TryFingerprintCandidateTextures(observation, signature);
  TryCaptureReplaySnapshot(observation, samples_resolved_target, prepared,
                           signature);
  size_t index = size_t(signature % kSignatureCapacity);
  for (size_t probe = 0; probe < kSignatureCapacity; ++probe) {
    DrawSignatureEntry &entry = g_candidate_census.entries[index];
    if (!entry.draw_count) {
      entry.signature = signature;
      entry.draw_count = 1;
      entry.first_frame = observation.frame_sequence;
      entry.last_frame = observation.frame_sequence;
      entry.min_index_count = observation.index_count;
      entry.max_index_count = observation.index_count;
      entry.min_index_buffer_length = observation.index_buffer_length;
      entry.vertex_specialization_mask =
          prepared.vertex_specialization_mask;
      entry.pixel_specialization_mask = prepared.pixel_specialization_mask;
      entry.prepared_sample = prepared;
      entry.samples_resolved_target = samples_resolved_target;
      entry.sample = observation;
      ++g_candidate_census.unique_signature_count;
      return;
    }
    if (entry.signature == signature) {
      ++entry.draw_count;
      entry.last_frame = observation.frame_sequence;
      entry.min_index_count =
          std::min(entry.min_index_count, observation.index_count);
      entry.max_index_count =
          std::max(entry.max_index_count, observation.index_count);
      if (observation.indexed) {
        entry.min_index_buffer_length = std::min(
            entry.min_index_buffer_length, observation.index_buffer_length);
      }
      return;
    }
    index = (index + 1) % kSignatureCapacity;
  }
  ++g_candidate_census.overflow_draw_count;
}

void ObserveDraw(const rex::system::GraphicsDrawObservation &observation) {
  AdvanceDependencyWindow(observation.frame_sequence);
  ObserveCommandBufferLineage(observation);
  const bool query_draw =
      observation.viz_query_condition || (observation.pa_sc_viz_query & 1);
  if (query_draw) {
    ++g_dependency_census.window_query_draw_count;
  }
  if (observation.vertex_memexport) {
    ++g_dependency_census.window_memexport_draw_count;
  }

  std::array<size_t, 64> sampled_targets{};
  size_t sampled_target_count = 0;
  PendingCandidateObservation candidate;
  candidate.sample = observation;
  ConsumeTitleDrawPacket(observation.packet_physical_address,
                         candidate.title_origin);
  for (uint32_t fetch_index = 0; fetch_index < 32; ++fetch_index) {
    if (!(observation.texture_fetch_mask & (uint32_t(1) << fetch_index))) {
      continue;
    }
    ObserveResolvedFetch(observation, fetch_index,
                         observation.texture_fetch_addresses[fetch_index],
                         false, sampled_targets, sampled_target_count,
                         candidate);
    ObserveResolvedFetch(observation, fetch_index,
                         observation.texture_fetch_mip_addresses[fetch_index],
                         true, sampled_targets, sampled_target_count,
                         candidate);
  }
  if (sampled_target_count) {
    ++g_dependency_census.window_sampled_draw_count;
  }

  if (!g_draw_census.window_first_frame) {
    g_draw_census.window_first_frame = observation.frame_sequence;
    g_candidate_census.window_first_frame = observation.frame_sequence;
  } else if (observation.frame_sequence >=
             g_draw_census.window_first_frame + kFrameSummaryInterval) {
    EmitDrawCensusWindow(observation.frame_sequence - 1);
    g_draw_census.window_first_frame = observation.frame_sequence;
    g_candidate_census.window_first_frame = observation.frame_sequence;
  }
  g_draw_census.window_last_frame = observation.frame_sequence;
  g_candidate_census.window_last_frame = observation.frame_sequence;

  ++g_draw_census.window_draw_count;
  const bool samples_resolved_target = sampled_target_count != 0;
  if (g_pending_candidate.valid) {
    ++g_candidate_unprepared_draw_count;
    ++g_backend_draw_outcome_missing;
    if (g_pending_candidate.title_origin.valid) {
      ++g_title_matched_unprepared_draws;
      RecordTitleDrawProvenance(DrawSignature(g_pending_candidate.sample),
                                false, 0, g_pending_candidate.sample,
                                g_pending_candidate.title_origin);
    }
    DiscardPendingPassConsumer();
  }
  candidate.samples_resolved_target = samples_resolved_target;
  g_pending_candidate = candidate;
  g_pending_candidate.valid = true;
  const uint64_t signature = DrawSignature(observation);
  size_t index = size_t(signature % kSignatureCapacity);
  for (size_t probe = 0; probe < kSignatureCapacity; ++probe) {
    DrawSignatureEntry &entry = g_draw_census.entries[index];
    if (!entry.draw_count) {
      entry.signature = signature;
      entry.draw_count = 1;
      entry.first_frame = observation.frame_sequence;
      entry.last_frame = observation.frame_sequence;
      entry.samples_resolved_target = samples_resolved_target;
      entry.sample = observation;
      ++g_draw_census.unique_signature_count;
      return;
    }
    if (entry.signature == signature) {
      ++entry.draw_count;
      entry.last_frame = observation.frame_sequence;
      return;
    }
    index = (index + 1) % kSignatureCapacity;
  }
  ++g_draw_census.overflow_draw_count;
}

} // namespace

namespace pinyon_shift::native_renderer {

void InstallGraphicsCensus(rex::system::IGraphicsSystem *graphics_system,
                           rex::memory::Memory *memory) {
  if (!graphics_system || !memory) {
    return;
  }
  ConfigureDispatchDiscovery();
  g_sky_horizon_suppression = {};
  g_sky_horizon_suppression.requested =
      REXCVAR_GET(pinyon_shift_native_renderer_sky_horizon_suppression);
  const bool census_requested =
      REXCVAR_GET(pinyon_shift_native_renderer_census);
  ConfigureTitleDrawProvenance(census_requested, memory);
  const bool lineage_armed = census_requested && memory;
  g_command_buffer_lineage_installed.store(false, std::memory_order_release);
  g_command_buffer_lineage_memory.store(nullptr, std::memory_order_release);
  if (!census_requested && !g_sky_horizon_suppression.requested) {
    EmitSkyHorizonSuppressionControl();
    return;
  }
  ResetDrawCensus();
  ResetPreparedShaderPairs();
  ResetCommandBufferLineage();
  ResetDependencyCensus();
  ResetGuestCpuVisibility();
  ConfigureIndexScan();
  ConfigureTextureScan();
  ConfigureReplaySnapshot();
  ConfigureIsolatedDraw();
  ConfigurePassFollower();
  ConfigurePassPublication();
  ArmSkyHorizonSuppression();
  EmitSkyHorizonSuppressionControl();
  ConfigureConsumerFamilyMarker();
  g_graphics_census_memory = memory;
  g_command_buffer_lineage_memory.store(lineage_armed ? memory : nullptr,
                                        std::memory_order_release);
  g_command_buffer_lineage_installed.store(lineage_armed,
                                           std::memory_order_release);
  if (g_pass_follower.requested && g_pass_follower.valid &&
      g_isolated_draw.requested && g_isolated_draw.valid) {
    g_guest_cpu_access_callback =
        memory->RegisterPhysicalMemoryAccessCallback(&ObserveGuestCpuAccess,
                                                     nullptr);
  }
  g_graphics_census_installed = true;
  graphics_system->SetDrawObserver(&ObserveDraw);
  graphics_system->SetIndirectBufferObserver(&ObserveIndirectBuffer);
  graphics_system->SetCopyObserver(&ObserveCopy);
  graphics_system->SetPreparedDrawObserver(&ObservePreparedDraw);
  graphics_system->SetDrawOutcomeObserver(&ObserveDrawOutcome);
  graphics_system->SetIsolatedDrawRequestObserver(&RequestIsolatedDraw);
  const std::string capacity = std::to_string(kSignatureCapacity);
  const std::string scene = CensusSceneMarker();
  diagnostics::RecordEvent("native_renderer.census.installed",
                           {{"signature_capacity", capacity},
                            {"summary_limit", "16"},
                            {"resolve_target_capacity", "4096"},
                            {"resolve_page_capacity", "32768"},
                            {"resolve_summary_limit", "32"},
                            {"prepared_shader_pair_capacity", "1024"},
                            {"command_buffer_lineage_capacity", "4096"},
                            {"semantic_receiver_lifecycle_capacity", "1024"},
                            {"guest_cpu_visibility_target_capacity", "64"},
                            {"scene", scene},
                            {"mode", g_sky_horizon_suppression.armed
                                         ? "experimental_suppression"
                                         : "pass_through"}});
  diagnostics::RecordEvent(
      "native_renderer.discovery.command_buffer_lineage_config",
      {{"status", "armed"},
       {"scene", scene},
       {"capacity", std::to_string(kCommandBufferLineageCapacity)},
       {"source",
        "title_store,constructor_function,constructor_return,r3-r10,"
        "owner_function,owner_return,owner_r3-r10,producer_function,"
        "producer_return,producer_r3-r10,context_function,context_return,"
        "context_r3-r10,context_root,semantic_receiver_generation,"
        "semantic_visibility_epoch,semantic_render_state_epoch,"
        "backend_packet,"
        "current_buffer,parent_packet,root_buffer,depth"},
       {"guest_payload_read", "false"},
       {"guest_state_changed", "false"},
       {"control_flow_changed", "false"},
       {"xenos_authority", "true"},
       {"suppression_allowed", "false"}});
  diagnostics::RecordEvent(
      "native_renderer.discovery.semantic_receiver_config",
      {{"status", "armed"},
       {"class", "proceduralGeometry::CProceduralModels"},
       {"dispatch", "82417BC0"},
       {"receiver", "entry_r3"},
       {"command_root", "entry_r6_plus_59712"},
       {"constructor", "82E1C9A0"},
       {"destructor", "82E1CA28"},
       {"deleting_destructor", "82E1D9B0"},
       {"object_size", "512"},
       {"visibility_function", "82E1FD00"},
       {"render_state_function", "824170D8"},
       {"descriptor_record_stride", "92"},
       {"runtime_record_stride", "68"},
       {"transform_matrix_ranges", "320:64,384:64,448:64"},
       {"identity_join", "exact_constructor_receiver_address_generation"},
       {"guest_payload_read", "false"},
       {"guest_state_changed", "false"},
       {"control_flow_changed", "false"},
       {"xenos_authority", "true"},
       {"suppression_allowed", "false"}});
  diagnostics::RecordEvent(
      "native_renderer.discovery.semantic_visibility_config",
      {{"status", lineage_armed ? "armed" : "disabled"},
       {"class", "proceduralGeometry::CProceduralModels"},
       {"visibility_function", "82E1FD00"},
       {"record_entry_hook", "82E20094"},
       {"lod_write_hooks", "82E205E4,82E206DC"},
       {"result_hook", "82E206F8"},
       {"record_completion_hook", "82E2084C"},
       {"record_identity",
        "receiver_generation,record_index,category,descriptor,runtime"},
       {"visibility_result", "runtime_selection_byte_18"},
       {"lod_selection", "runtime_record_plus_104"},
       {"category_capacity",
        std::to_string(kSemanticVisibilityCategoryCapacity)},
       {"lod_capacity", std::to_string(kSemanticVisibilityLodCapacity)},
       {"result_value_capacity",
        std::to_string(kSemanticVisibilityResultValueCapacity)},
       {"classification",
        "title_authoritative_visibility_and_lod_observation"},
       {"guest_payload_read", "false"},
       {"guest_state_changed", "false"},
       {"control_flow_changed", "false"},
       {"native_culling", "false"},
       {"native_lod", "false"},
       {"native_draw", "false"},
       {"xenos_authority", "true"},
       {"suppression_allowed", "false"}});
  diagnostics::RecordEvent(
      "native_renderer.discovery.semantic_visibility_policy_config",
      {{"status", lineage_armed ? "armed" : "disabled"},
       {"class", "proceduralGeometry::CProceduralModels"},
       {"visibility_function", "82E1FD00"},
       {"record_entry_hook", "82E20094"},
       {"runtime_threshold_hook", "82E20134"},
       {"descriptor_threshold_hook", "82E201B0"},
       {"spatial_helper_result_hook", "82E20350"},
       {"category_helper_result_hook", "82E20368"},
       {"spatial_distance_source", "f26"},
       {"threshold_source", "f0"},
       {"runtime_distance_scalar_offset", "44"},
       {"descriptor_distance_scalar_offset", "60"},
       {"spatial_exponent_capacity",
        std::to_string(kSemanticVisibilitySpatialExponentCapacity)},
       {"outcomes", "early_rejected,rejected,selected"},
       {"scope", "active_title_record_only"},
       {"classification",
        "title_spatial_policy_input_outcome_correlation"},
       {"guest_payload_read", "false"},
       {"guest_state_changed", "false"},
       {"control_flow_changed", "false"},
       {"native_policy_execution", "false"},
       {"native_culling", "false"},
       {"native_lod", "false"},
       {"native_draw", "false"},
       {"xenos_authority", "true"},
       {"suppression_allowed", "false"}});
  diagnostics::RecordEvent(
      "native_renderer.discovery.semantic_visibility_oracle_config",
      {{"status", lineage_armed ? "armed" : "disabled"},
       {"class", "proceduralGeometry::CProceduralModels"},
       {"visibility_function", "82E1FD00"},
       {"record_entry_hook", "82E20094"},
       {"candidate_threshold_hook", "82E20258"},
       {"local_distance_hook", "82E202D8"},
       {"spatial_helper", "8243F9A0"},
       {"spatial_helper_result_hook", "82E20350"},
       {"category_helper", "82441048"},
       {"category_helper_result_hook", "82E20368"},
       {"category_result_domain", "0,1,2"},
       {"outcomes", "early_rejected,rejected,selected"},
       {"scope", "active_title_record_only"},
       {"classification", "title_ordered_visibility_helper_oracle"},
       {"guest_payload_read", "false"},
       {"guest_state_changed", "false"},
       {"control_flow_changed", "false"},
       {"native_policy_execution", "false"},
       {"native_culling", "false"},
       {"native_lod", "false"},
       {"native_draw", "false"},
       {"xenos_authority", "true"},
       {"suppression_allowed", "false"}});
  diagnostics::RecordEvent(
      "native_renderer.discovery.semantic_visibility_shadow_config",
      {{"status", lineage_armed ? "armed" : "disabled"},
       {"class", "proceduralGeometry::CProceduralModels"},
       {"visibility_function", "82E1FD00"},
       {"record_entry_hook", "82E20094"},
       {"category_helper_result_hook", "82E20368"},
       {"title_result_hook", "82E206F8"},
       {"record_completion_hook", "82E2084C"},
       {"model", "any_nonzero_category_result_selects"},
       {"category_result_domain", "0,1,2"},
       {"outcomes", "early_rejected,rejected,selected"},
       {"scope", "active_title_record_only"},
       {"classification", "title_result_domain_shadow_selection"},
       {"guest_payload_read", "false"},
       {"guest_state_changed", "false"},
       {"control_flow_changed", "false"},
       {"native_policy_execution", "shadow_only"},
       {"native_culling", "false"},
       {"native_lod", "false"},
       {"native_draw", "false"},
       {"xenos_authority", "true"},
       {"suppression_allowed", "false"}});
  diagnostics::RecordEvent(
      "native_renderer.discovery.semantic_visibility_spatial_shadow_config",
      {{"status", lineage_armed ? "armed" : "disabled"},
       {"class", "proceduralGeometry::CProceduralModels"},
       {"visibility_function", "82E1FD00"},
       {"input_hook", "82E2034C"},
       {"result_hook", "82E20350"},
       {"helper", "8243F9A0"},
       {"distance_helper", "8243FD70"},
       {"query_vector_offsets", "0,4,8"},
       {"query_scalar_offsets", "16,20,24"},
       {"endpoint_vector_offsets", "0,4,8"},
       {"interpolation_factor", "0.5"},
       {"shortcut", "query_scalar_20_less_than_zero_selects"},
       {"comparison",
        "query_scalar_16_times_distance_squared_le_query_scalar_24_times_half_segment_squared"},
       {"bounded_guest_payload_bytes", "52"},
       {"scope", "active_title_record_only"},
       {"classification", "independent_spatial_helper_shadow"},
       {"guest_payload_read", "bounded_spatial_helper_inputs"},
       {"guest_state_changed", "false"},
       {"control_flow_changed", "false"},
       {"native_policy_execution", "shadow_only"},
       {"native_culling", "false"},
       {"native_lod", "false"},
       {"native_draw", "false"},
       {"xenos_authority", "true"},
       {"suppression_allowed", "false"}});
  diagnostics::RecordEvent(
      "native_renderer.discovery.semantic_visibility_category_shadow_config",
      {{"status", lineage_armed ? "armed" : "disabled"},
       {"class", "proceduralGeometry::CProceduralModels"},
       {"visibility_function", "82E1FD00"},
       {"input_hook", "82E20364"},
       {"result_hook", "82E20368"},
       {"helper", "82441048"},
       {"plane_vector_offsets", "0,16,32,48,64,80"},
       {"plane_vector_count", "6"},
       {"endpoint_registers", "v1,v2"},
       {"axis_signs", "1,1,-1"},
       {"support_rule", "plane_axis_nonnegative_selects_v2_for_positive"},
       {"positive_comparison", "greater_equal_zero_sets_intersection_bit"},
       {"negative_comparison", "greater_zero_sets_outside_bits"},
       {"result_mapping", "bits_3_to_0_bits_1_to_1_other_to_2"},
       {"bounded_guest_payload_bytes", "96"},
       {"scope", "active_title_record_only"},
       {"classification", "independent_category_helper_shadow"},
       {"guest_payload_read", "bounded_category_planes"},
       {"guest_state_changed", "false"},
       {"control_flow_changed", "false"},
       {"native_policy_execution", "shadow_only"},
       {"native_culling", "false"},
       {"native_lod", "false"},
       {"native_draw", "false"},
       {"xenos_authority", "true"},
       {"suppression_allowed", "false"}});
  diagnostics::RecordEvent(
      "native_renderer.discovery.semantic_visibility_assembly_shadow_config",
      {{"status", lineage_armed ? "armed" : "disabled"},
       {"class", "proceduralGeometry::CProceduralModels"},
       {"visibility_function", "82E1FD00"},
       {"record_entry_hook", "82E20094"},
       {"spatial_input_hook", "82E2034C"},
       {"spatial_result_hook", "82E20350"},
       {"category_input_hook", "82E20364"},
       {"category_result_hook", "82E20368"},
       {"title_result_hook", "82E206F8"},
       {"record_completion_hook", "82E2084C"},
       {"model", "independent_spatial_then_category_selection"},
       {"selection_rule", "any_nonzero_predicted_category_result_selects"},
       {"bounded_guest_payload_bytes_per_candidate", "148"},
       {"scope", "active_title_record_only"},
       {"classification", "independent_visibility_policy_assembly_shadow"},
       {"guest_payload_read", "bounded_spatial_and_category_inputs"},
       {"guest_state_changed", "false"},
       {"control_flow_changed", "false"},
       {"native_policy_execution", "shadow_only"},
       {"native_culling", "false"},
       {"native_lod", "false"},
       {"native_draw", "false"},
       {"xenos_authority", "true"},
       {"suppression_allowed", "false"}});
  diagnostics::RecordEvent(
      "native_renderer.discovery.semantic_visibility_workset_config",
      {{"status", lineage_armed ? "armed" : "disabled"},
       {"class", "proceduralGeometry::CProceduralModels"},
       {"record_completion_hook", "82E2084C"},
       {"title_lod_write_hooks", "82E205E4,82E206DC"},
       {"semantic_instance_hook", "8241741C"},
       {"capacity", std::to_string(kSemanticVisibilityWorksetCapacity)},
       {"model", "independent_policy_to_semantic_candidate_handoff"},
       {"identity", "receiver_generation_record_index"},
       {"title_lod_lineage", "latest_exact_title_record_observation"},
       {"selection_rule", "any_nonzero_predicted_category_result_selects"},
       {"execution", "bounded_host_visibility_workset"},
       {"guest_payload_read", "qualified_policy_inputs_only"},
       {"guest_state_changed", "false"},
       {"control_flow_changed", "false"},
       {"title_culling_changed", "false"},
       {"native_lod", "false"},
       {"native_draw", "false"},
       {"xenos_authority", "true"},
       {"suppression_allowed", "false"}});
  diagnostics::RecordEvent(
      "native_renderer.discovery.semantic_visibility_prepared_candidate_config",
      {{"status", lineage_armed ? "armed" : "disabled"},
       {"class", "proceduralGeometry::CProceduralModels"},
       {"semantic_instance_hook", "8241741C"},
       {"semantic_packet_hooks", "82416260,824162F4"},
       {"prepared_draw_join", "physical_pm4_header_generation"},
       {"capacity",
        std::to_string(kSemanticVisibilityPreparedCandidateCapacity)},
       {"policy_age_limit_frames",
        std::to_string(kSemanticVisibilityMaximumPolicyAgeFrames)},
       {"identity", "receiver_generation_record_index"},
       {"selection", "independent_visibility_selected_and_fresh"},
       {"prepared_lineage", "exact_semantic_pm4_prepared_draw"},
       {"title_lod_lineage", "exact_visibility_identity_to_prepared_draw"},
       {"mechanical_admission_contract", "isolated_draw_v1"},
       {"guest_state_changed", "false"},
       {"control_flow_changed", "false"},
       {"native_upload", "false"},
       {"native_draw", "false"},
       {"xenos_draw", "preserved"},
       {"suppression_allowed", "false"}});
  diagnostics::RecordEvent(
      "native_renderer.discovery.semantic_instance_config",
      {{"status", lineage_armed ? "armed" : "disabled"},
       {"class", "proceduralGeometry::CProceduralModels"},
       {"hook", "82417418"},
       {"hook_address", "8241741C"},
       {"receiver", "entry_r3"},
       {"descriptor_index", "caller_stack_plus_84"},
       {"descriptor_record", "owner[0]+index*92"},
       {"runtime_record", "receiver[128]+index*68"},
       {"transform_ranges", "receiver+320:192"},
       {"capacity", std::to_string(kSemanticInstanceCapacity)},
       {"immutable_sample_words", "88"},
       {"payload_bytes_per_live_observation",
        std::to_string(kSemanticObservationPayloadBytes)},
       {"classification", "semantic_extraction_no_rendering"},
       {"fallback", "xenos_replay_unclassified_material_or_state"},
       {"guest_payload_read", "bounded_semantic_records_only"},
       {"guest_state_changed", "false"},
       {"native_upload", "false"},
       {"native_draw", "false"},
       {"xenos_authority", "true"},
       {"suppression_allowed", "false"}});
  diagnostics::RecordEvent(
      "native_renderer.discovery.semantic_submission_config",
      {{"status", lineage_armed ? "armed" : "disabled"},
       {"class", "proceduralGeometry::CProceduralModels"},
       {"primary_resource_binding_hook", "82417A74"},
       {"secondary_resource_binding_hook", "82417A9C"},
       {"geometry_submission_hook", "82417B60"},
       {"graphics_submission_vtable_offset", "160"},
       {"resource_binding_helper", "82415BF8"},
       {"resource_lookup_function", "82410A58"},
       {"resource_provider_lookup_hook", "82415B64"},
       {"resource_provider_primary_predicate_hook", "82415B80"},
       {"resource_provider_fallback_predicate_hook", "82415BA4"},
       {"resource_provider_method_result_hook", "82415BC0"},
       {"resource_secondary_resolution_result_hook", "82415BE4"},
       {"resource_resolution_result_hook", "82415C50"},
       {"resource_bind_dispatch_hook", "82415C6C"},
       {"resource_binding_slots", "0,1"},
       {"descriptor_resource_indices", "offsets_0_4"},
       {"receiver_resource_table", "receiver_plus_8_stride_8"},
       {"runtime_submission_object", "runtime_plus_0"},
       {"geometry_source_contract",
        "runtime_plus_24_or_count_at_28_source_at_32"},
       {"descriptor_kind_groups", "kind_4_5,kind_1_3,other"},
       {"helper_state_families",
        "state_9,state_11,states_24_27,states_6_8,remaining_states"},
       {"primitive_type", "13"},
       {"count_scale", "4"},
       {"capacity", std::to_string(kSemanticSubmissionCapacity)},
       {"maximum_payload_bytes_per_live_observation",
        std::to_string(kSemanticSubmissionMaximumPayloadBytes)},
       {"classification",
        "resolved_resource_state_variant_and_dispatch_submission"},
       {"fallback", "xenos_replay"},
       {"guest_payload_read",
        "bounded_submission_and_dispatch_fields_only"},
       {"guest_state_changed", "false"},
       {"native_upload", "false"},
       {"native_draw", "false"},
       {"xenos_authority", "true"},
       {"suppression_allowed", "false"}});
  diagnostics::RecordEvent(
      "native_renderer.discovery.semantic_draw_config",
      {{"status", lineage_armed ? "armed" : "disabled"},
       {"scene", scene},
       {"class", "proceduralGeometry::CProceduralModels"},
       {"render_item_entry_hook", "8241741C"},
       {"render_item_exit_hook", "82417B80"},
       {"geometry_submission_hook", "82417B60"},
       {"title_packet_hooks", "82410328,829F7CB0"},
       {"semantic_packet_hooks", "82416260,824162F4"},
       {"graphics_submission_wrapper", "82415CE0"},
       {"graphics_submission_emitter", "82415F68"},
       {"semantic_packet_opcode", "PM4_DRAW_INDX_0x22"},
       {"semantic_catalog",
        "prepared_template_dynamic_resource_instance_and_batch_key"},
       {"semantic_catalog_capacity",
        std::to_string(kSemanticPreparedTemplateCapacity)},
       {"title_indirect_packet_hooks",
        "824095B4,82416EFC,8246FC1C,8263BD64,829E8E88,829EC49C"},
       {"render_item_stack_capacity",
        std::to_string(kSemanticRenderItemStackCapacity)},
       {"correlation",
        "exact_render_item_scope_to_emitted_and_backend_pm4_header"},
       {"classification", "procedural_submission_pm4_packet_boundary"},
       {"guest_payload_read", "bounded_submission_identity_only"},
       {"guest_state_changed", "false"},
       {"native_upload", "false"},
       {"native_draw", "false"},
       {"xenos_authority", "true"},
       {"suppression_allowed", "false"}});
  diagnostics::RecordEvent("native_renderer.census.scene_marker",
                           {{"scene", scene}, {"source", "operator"}});
  diagnostics::RecordEvent(
      "native_renderer.census.index_scan_config",
      {{"status", !g_index_scan.requested
                      ? "disabled"
                      : (g_index_scan.valid ? "armed" : "invalid_signature")},
       {"signature", g_index_scan.valid && g_index_scan.requested
                         ? fmt::format("{:016X}", g_index_scan.target_signature)
                         : ""},
       {"maximum_index_count", std::to_string(kMaximumIndexScanCount)},
       {"maximum_bytes", std::to_string(kMaximumIndexScanBytes)},
       {"mode", "bounded_diagnostic_read"}});
  diagnostics::RecordEvent(
      "native_renderer.census.texture_scan_config",
      {{"status", !g_texture_scan.requested
                      ? "disabled"
                      : (g_texture_scan.valid ? "armed" : "invalid_signature")},
       {"signature", g_texture_scan.valid && g_texture_scan.requested
                         ? fmt::format("{:016X}",
                                       g_texture_scan.target_signature)
                         : ""},
       {"maximum_resources",
        std::to_string(kMaximumTextureScanResources)},
       {"maximum_resource_bytes",
        std::to_string(kMaximumTextureScanResourceBytes)},
       {"maximum_total_bytes",
        std::to_string(kMaximumTextureScanTotalBytes)},
       {"mode", "bounded_diagnostic_read"}});
  diagnostics::RecordEvent(
      "native_renderer.census.pass_follower_config",
      {{"status", !g_pass_follower.requested
                      ? "disabled"
                      : (g_pass_follower.valid ? "armed" : "invalid_signature")},
       {"anchor_signature",
        g_pass_follower.valid && g_pass_follower.requested
            ? fmt::format("{:016X}", g_pass_follower.target_signature)
            : ""},
       {"maximum_followers", "1"},
       {"mode", "bounded_metadata"},
       {"xenos_draw", "preserved"},
       {"native_draw", "false"},
       {"suppression_eligible", "false"}});
  diagnostics::RecordEvent(
      "native_renderer.census.consumer_family_marker_config",
      {{"status", !g_consumer_family_marker.requested
                      ? "disabled"
                      : (g_consumer_family_marker.valid
                             ? (g_consumer_family_marker.readback_requested
                                    ? "armed_with_readback"
                                    : "armed")
                             : "invalid_configuration")},
       {"consumer_family", ConsumerFamilyId()},
       {"mode", g_consumer_family_marker.readback_requested
                    ? "authoritative_draw_marker_and_bounded_attachment_corpus"
                    : "authoritative_draw_marker_only"},
       {"readback",
        g_consumer_family_marker.readback_requested
            ? "before_after_color_and_depth_stencil"
            : "disabled"},
       {"readback_sample_limit",
        std::to_string(g_consumer_family_marker.readback_sample_limit)},
       {"readback_output",
        g_consumer_family_marker.readback_requested ? "local_only" : ""},
       {"xenos_draw", "preserved"},
       {"draw_suppression", "false"},
       {"resolve_suppression", "false"},
       {"suppression_eligible", "false"}});
  diagnostics::RecordEvent(
      "native_renderer.snapshot.config",
      {{"status", !g_replay_snapshot.requested
                      ? "disabled"
                      : (g_replay_snapshot.valid ? "armed"
                                                 : "invalid_configuration")},
       {"signature",
        g_replay_snapshot.valid && g_replay_snapshot.requested
            ? fmt::format("{:016X}", g_replay_snapshot.target_signature)
            : ""},
       {"output",
        g_replay_snapshot.valid && g_replay_snapshot.requested ? "local_only"
                                                               : ""},
       {"native_upload", "false"},
       {"native_draw", "false"},
       {"suppression_eligible", "false"}});
  diagnostics::RecordEvent(
      "native_renderer.isolated_draw.config",
      {{"status", !g_isolated_draw.requested
                      ? "disabled"
                      : (g_isolated_draw.valid
                             ? (g_isolated_draw.readback_requested
                                    ? "armed_with_readback"
                                    : "armed")
                                               : "invalid_configuration")},
       {"signature",
        g_isolated_draw.valid && g_isolated_draw.requested
            ? fmt::format("{:016X}", g_isolated_draw.target_signature)
            : ""},
       {"anchor_signature",
        g_isolated_draw.valid && g_isolated_draw.requested &&
                g_pass_follower.valid && g_pass_follower.requested
            ? fmt::format("{:016X}", g_pass_follower.target_signature)
            : ""},
       {"mode", g_pass_follower.valid && g_pass_follower.requested
                    ? "retained_pass"
                    : "single_draw"},
       {"native_draw", "isolated_only"},
       {"readback", g_isolated_draw.readback_requested ? "asynchronous"
                                                        : "disabled"},
       {"reference_marker", "exact_signature"},
       {"selection",
        g_isolated_draw.auto_select_fresh_visibility_candidate
            ? (g_isolated_draw.require_title_lod_candidate
                   ? "first_fresh_mechanically_eligible_title_lod_candidate"
                   : "first_fresh_mechanically_eligible_candidate")
            : "exact_signature"},
       {"visibility_gate",
        g_isolated_draw.require_fresh_visibility_candidate
            ? "fresh_selected_semantic_candidate"
            : "disabled"},
       {"title_lod_gate",
        g_isolated_draw.require_title_lod_candidate
            ? "exact_visibility_identity_lod_observation"
            : "disabled"},
       {"xenos_draw", "preserved"},
       {"output_authority", "xenos"},
       {"suppression_eligible", "false"}});
  diagnostics::RecordEvent(
      "native_renderer.retained_pass.publication_config",
      {{"status", !g_pass_publication.requested
                      ? "disabled"
                      : (g_pass_publication.valid ? "armed"
                                                  : "invalid_configuration")},
       {"anchor_signature",
        g_pass_publication.valid && g_pass_publication.requested
            ? fmt::format("{:016X}", g_pass_follower.target_signature)
            : ""},
       {"follower_signature",
        g_pass_publication.valid && g_pass_publication.requested
            ? fmt::format("{:016X}", g_isolated_draw.target_signature)
            : ""},
       {"activation", "startup_only"},
       {"default_enabled", "false"},
       {"publication", "color_and_depth_stencil_after_xenos_follower"},
       {"guest_target_content", "xenos_until_successful_publication"},
       {"fallback", "preserve_xenos_targets"},
       {"detail_limit", std::to_string(kPassPublicationDetailLimit)},
       {"xenos_draw", g_sky_horizon_suppression.armed
                          ? "anchor_preserved_follower_conditional"
                          : "preserved"},
       {"draw_suppression", g_sky_horizon_suppression.armed
                                ? "follower_after_publication_only"
                                : "false"},
       {"resolve_suppression", "false"},
       {"side_effects", "preserved"},
       {"suppression_eligible",
        g_sky_horizon_suppression.armed ? "true" : "false"}});
  diagnostics::RecordEvent(
      "native_renderer.census.guest_cpu_visibility_config",
      {{"status", g_guest_cpu_access_callback ? "armed" : "disabled"},
       {"scope", "exact_retained_pass_resolves"},
       {"observation", "one_shot_guest_page_access"},
       {"target_capacity",
        std::to_string(kGuestCpuVisibilityTargetCapacity)},
       {"xenos_draw", "preserved"},
       {"suppression_eligible", "false"}});
}

void UninstallGraphicsCensus(rex::system::IGraphicsSystem *graphics_system) {
  if (graphics_system) {
    graphics_system->SetDrawObserver(nullptr);
    graphics_system->SetIndirectBufferObserver(nullptr);
    graphics_system->SetCopyObserver(nullptr);
    graphics_system->SetPreparedDrawObserver(nullptr);
    graphics_system->SetDrawOutcomeObserver(nullptr);
    graphics_system->SetIsolatedDrawRequestObserver(nullptr);
  }
  g_command_buffer_lineage_installed.store(false, std::memory_order_release);
  g_command_buffer_lineage_memory.store(nullptr, std::memory_order_release);
  EmitDispatchDiscoverySummary();
  if (!g_graphics_census_installed) {
    return;
  }
  const bool guest_cpu_observer_installed =
      g_guest_cpu_access_callback != nullptr;
  if (g_guest_cpu_access_callback && g_graphics_census_memory) {
    g_graphics_census_memory->UnregisterPhysicalMemoryAccessCallback(
        g_guest_cpu_access_callback);
    g_guest_cpu_access_callback = nullptr;
  }
  if (g_isolated_draw.artifact_writer.joinable()) {
    g_isolated_draw.artifact_writer.join();
  }
  if (g_isolated_draw.reference_artifact_writer.joinable()) {
    g_isolated_draw.reference_artifact_writer.join();
  }
  if (g_isolated_draw.depth_artifact_writer.joinable()) {
    g_isolated_draw.depth_artifact_writer.join();
  }
  if (g_isolated_draw.reference_depth_artifact_writer.joinable()) {
    g_isolated_draw.reference_depth_artifact_writer.join();
  }
  for (std::jthread &artifact_writer :
       g_consumer_family_marker.artifact_writers) {
    if (artifact_writer.joinable()) {
      artifact_writer.join();
    }
  }
  if (g_pending_candidate.valid) {
    ++g_candidate_unprepared_draw_count;
    ++g_backend_draw_outcome_missing;
    if (g_pending_candidate.title_origin.valid) {
      ++g_title_matched_unprepared_draws;
      RecordTitleDrawProvenance(DrawSignature(g_pending_candidate.sample),
                                false, 0, g_pending_candidate.sample,
                                g_pending_candidate.title_origin);
    }
    DiscardPendingPassConsumer();
    g_pending_candidate.valid = false;
  }
  EmitSemanticVisibilityCensus();
  EmitTitleDrawProvenanceSummary();
  EmitSemanticBatchOpportunitySummary();
  EmitCommandBufferLineageSummary();
  if (g_pass_consumer_trace.pending) {
    ++g_pass_consumer_trace.superseded_without_resolve;
    g_pass_consumer_trace.pending = false;
  }
  for (const ResolveTargetEntry &target : g_dependency_census.targets) {
    if (target.latest_resolve_from_traced_family &&
        !target.family_sampled_draw_count) {
      ++g_pass_consumer_trace.active_unsampled;
    }
  }
  if (g_pass_follower.requested && g_pass_follower.valid &&
      g_isolated_draw.requested && g_isolated_draw.valid) {
    uint64_t guest_cpu_read_page_events = 0;
    uint64_t guest_cpu_write_page_events = 0;
    uint64_t guest_cpu_read_generations = 0;
    uint64_t guest_cpu_write_generations = 0;
    const size_t guest_cpu_target_count =
        g_guest_cpu_visibility_target_count.load(std::memory_order_acquire);
    for (size_t i = 0; i < guest_cpu_target_count; ++i) {
      const auto &target = g_guest_cpu_visibility_targets[i];
      const uint64_t read_page_events =
          target.read_page_events.load(std::memory_order_relaxed);
      const uint64_t write_page_events =
          target.write_page_events.load(std::memory_order_relaxed);
      const uint64_t read_generations =
          target.read_generations.load(std::memory_order_relaxed);
      const uint64_t write_generations =
          target.write_generations.load(std::memory_order_relaxed);
      guest_cpu_read_page_events += read_page_events;
      guest_cpu_write_page_events += write_page_events;
      guest_cpu_read_generations += read_generations;
      guest_cpu_write_generations += write_generations;
      diagnostics::RecordEvent(
          "native_renderer.census.pass_family_guest_cpu_target",
          {{"anchor_signature",
            fmt::format("{:016X}", g_pass_follower.target_signature)},
           {"follower_signature",
            fmt::format("{:016X}", g_isolated_draw.target_signature)},
           {"address", fmt::format(
                           "{:08X}", target.address.load(
                                             std::memory_order_relaxed))},
           {"latest_length", std::to_string(target.length.load(
                                 std::memory_order_relaxed))},
           {"resolve_count", std::to_string(target.resolve_count.load(
                                std::memory_order_relaxed))},
           {"read_page_events", std::to_string(read_page_events)},
           {"write_page_events", std::to_string(write_page_events)},
           {"read_generations", std::to_string(read_generations)},
           {"write_generations", std::to_string(write_generations)},
           {"guest_cpu_read", read_generations ? "observed" : "unobserved"},
           {"xenos_draw", "preserved"},
           {"suppression_eligible", "false"}});
    }
    const uint64_t armed_resolves =
        g_guest_cpu_visibility_armed_resolves.load(std::memory_order_relaxed);
    const uint64_t target_overflow =
        g_guest_cpu_visibility_target_overflow.load(std::memory_order_relaxed);
    const bool guest_cpu_observation_complete =
        guest_cpu_observer_installed && armed_resolves && !target_overflow &&
        armed_resolves == g_pass_consumer_trace.family_resolves;
    diagnostics::RecordEvent(
        "native_renderer.census.pass_family_guest_cpu_summary",
        {{"anchor_signature",
          fmt::format("{:016X}", g_pass_follower.target_signature)},
         {"follower_signature",
          fmt::format("{:016X}", g_isolated_draw.target_signature)},
         {"armed_resolves", std::to_string(armed_resolves)},
         {"armed_bytes",
          std::to_string(g_guest_cpu_visibility_armed_bytes.load(
              std::memory_order_relaxed))},
         {"target_count", std::to_string(guest_cpu_target_count)},
         {"target_overflow", std::to_string(target_overflow)},
         {"read_page_events", std::to_string(guest_cpu_read_page_events)},
         {"write_page_events", std::to_string(guest_cpu_write_page_events)},
         {"read_generations", std::to_string(guest_cpu_read_generations)},
         {"write_generations", std::to_string(guest_cpu_write_generations)},
         {"observation_complete",
          guest_cpu_observation_complete ? "true" : "false"},
         {"guest_cpu_visibility",
          !guest_cpu_observation_complete
              ? "unknown"
              : (guest_cpu_read_generations ? "fail" : "pass")},
         {"classification",
          !guest_cpu_observation_complete
              ? "incomplete_guest_cpu_observation"
              : (guest_cpu_read_generations
                     ? "guest_cpu_read_observed"
                     : "bounded_no_guest_cpu_read_observed")},
         {"xenos_draw", "preserved"},
         {"suppression_eligible", "false"}});
    uint64_t prepared_metadata_count = 0;
    for (size_t i = 0; i < g_pass_consumer_trace.consumer_signature_count; ++i) {
      const PassConsumerSignatureEntry &entry =
          g_pass_consumer_trace.consumer_signatures[i];
      prepared_metadata_count += entry.prepared_valid ? 1 : 0;
      const auto &sample = entry.sample;
      const auto &prepared = entry.prepared_sample;
      const std::string pipeline_state = fmt::format(
          "color_mask={:08X};blend={:08X}:{:08X}:{:08X}:{:08X};"
          "depth={:08X};raster={:08X};vertex={:08X}",
          sample.rb_color_mask, sample.rb_blendcontrol[0],
          sample.rb_blendcontrol[1], sample.rb_blendcontrol[2],
          sample.rb_blendcontrol[3], sample.rb_depthcontrol,
          sample.pa_su_sc_mode_cntl, sample.pa_su_vtx_cntl);
      diagnostics::RecordEvent(
          "native_renderer.census.pass_family_consumer_signature",
          {{"anchor_signature",
            fmt::format("{:016X}", g_pass_follower.target_signature)},
           {"follower_signature",
            fmt::format("{:016X}", g_isolated_draw.target_signature)},
           {"consumer_signature", fmt::format("{:016X}", entry.signature)},
           {"sample_events", std::to_string(entry.sample_events)},
           {"first_frame", std::to_string(entry.first_frame)},
           {"last_frame", std::to_string(entry.last_frame)},
           {"query_sample_events",
            std::to_string(entry.query_sample_events)},
           {"memexport_sample_events",
            std::to_string(entry.memexport_sample_events)},
           {"family_base_fetch_mask",
            fmt::format("{:016X}", entry.family_base_fetch_mask)},
           {"family_mip_fetch_mask",
            fmt::format("{:016X}", entry.family_mip_fetch_mask)},
           {"vertex_shader", fmt::format("{:016X}", sample.vertex_shader_hash)},
           {"pixel_shader", fmt::format("{:016X}", sample.pixel_shader_hash)},
           {"vertex_specialization_mask",
            entry.prepared_valid
                ? fmt::format("{:016X}", prepared.vertex_specialization_mask)
                : "unknown"},
           {"pixel_specialization_mask",
            entry.prepared_valid
                ? fmt::format("{:016X}", prepared.pixel_specialization_mask)
                : "unknown"},
           {"prepared_pipeline_hash",
            entry.prepared_valid
                ? fmt::format("{:016X}", PreparedPipelineHash(prepared))
                : "unknown"},
           {"host_primitive",
            entry.prepared_valid
                ? std::to_string(prepared.host_primitive_type)
                : "unknown"},
           {"host_index_buffer_type",
            entry.prepared_valid
                ? std::to_string(prepared.index_buffer_type)
                : "unknown"},
           {"host_index_format",
            entry.prepared_valid
                ? std::to_string(prepared.host_index_format)
                : "unknown"},
           {"prepared_pipeline_flags",
            entry.prepared_valid ? fmt::format("{:08X}", prepared.flags)
                                 : "unknown"},
           {"bound_render_target_bits",
            entry.prepared_valid
                ? fmt::format("{:08X}", prepared.bound_render_target_bits)
                : "unknown"},
           {"primitive", std::to_string(sample.primitive_type)},
           {"source_select", std::to_string(sample.source_select)},
           {"indexed", sample.indexed ? "true" : "false"},
           {"index_count", std::to_string(sample.index_count)},
           {"vertex_binding_count",
            std::to_string(sample.vertex_binding_count)},
           {"vertex_attribute_count",
            std::to_string(sample.vertex_attribute_count)},
           {"texture_fetch_count",
            std::to_string(std::popcount(sample.texture_fetch_mask))},
           {"pipeline_state", pipeline_state},
           {"prepared_metadata", entry.prepared_valid ? "observed" : "missing"},
           {"classification", "exact_family_guest_gpu_consumer"},
           {"xenos_draw", "preserved"},
           {"suppression_eligible", "false"}});
    }
    diagnostics::RecordEvent(
        "native_renderer.census.pass_family_consumer_summary",
        {{"anchor_signature",
          fmt::format("{:016X}", g_pass_follower.target_signature)},
         {"follower_signature",
          fmt::format("{:016X}", g_isolated_draw.target_signature)},
         {"family_occurrences",
          std::to_string(g_pass_consumer_trace.family_occurrences)},
         {"family_resolves",
          std::to_string(g_pass_consumer_trace.family_resolves)},
         {"family_resolve_bytes",
          std::to_string(g_pass_consumer_trace.family_resolve_bytes)},
         {"sampled_resolves",
          std::to_string(g_pass_consumer_trace.sampled_resolves)},
         {"sampled_draws",
          std::to_string(g_pass_consumer_trace.sampled_draws)},
         {"sample_references",
          std::to_string(g_pass_consumer_trace.sample_references)},
         {"overwritten_unsampled",
          std::to_string(g_pass_consumer_trace.overwritten_unsampled)},
         {"active_unsampled",
          std::to_string(g_pass_consumer_trace.active_unsampled)},
         {"superseded_without_resolve",
          std::to_string(
              g_pass_consumer_trace.superseded_without_resolve)},
         {"consumer_signature_count",
          std::to_string(g_pass_consumer_trace.consumer_signature_count)},
         {"consumer_signature_overflow",
          std::to_string(g_pass_consumer_trace.consumer_signature_overflow)},
         {"unprepared_consumer_draws",
          std::to_string(g_pass_consumer_trace.unprepared_consumer_draws)},
         {"unprepared_consumer_references",
          std::to_string(
              g_pass_consumer_trace.unprepared_consumer_references)},
         {"prepared_metadata_count",
          std::to_string(prepared_metadata_count)},
         {"prepared_metadata_missing",
          std::to_string(g_pass_consumer_trace.consumer_signature_count -
                         prepared_metadata_count)},
         {"detail_events",
          std::to_string(g_pass_consumer_trace.detail_events)},
         {"detail_overflow",
          std::to_string(g_pass_consumer_trace.detail_overflow)},
         {"classification", "bounded_exact_family_lineage"},
         {"guest_gpu_consumers",
          g_pass_consumer_trace.sampled_draws ? "observed" : "unobserved"},
         {"xenos_draw", "preserved"},
         {"suppression_eligible", "false"}});
  }
  diagnostics::RecordEvent(
      "native_renderer.census.consumer_family_marker_summary",
      {{"status", !g_consumer_family_marker.requested
                      ? "disabled"
                      : (g_consumer_family_marker.valid ? "complete"
                                                        : "invalid_family")},
       {"consumer_family", ConsumerFamilyId()},
       {"matched_draws",
        std::to_string(g_consumer_family_marker.matched_draws)},
       {"marker_requests",
        std::to_string(g_consumer_family_marker.marker_requests)},
       {"readback_requested",
        g_consumer_family_marker.readback_requested ? "true" : "false"},
       {"readback_requests",
        std::to_string(g_consumer_family_marker.readback_requests)},
       {"readback_completions",
        std::to_string(g_consumer_family_marker.readback_completions)},
       {"readback_sample_limit",
        std::to_string(g_consumer_family_marker.readback_sample_limit)},
       {"readback_samples_completed",
        std::to_string(g_consumer_family_marker.readback_samples_completed)},
       {"readback_expected_completions",
        std::to_string(g_consumer_family_marker.readback_requests * 4)},
       {"readback_in_flight",
        g_consumer_family_marker.readback_in_flight ? "true" : "false"},
       {"capture_frame",
        std::to_string(g_consumer_family_marker.capture_frame)},
       {"capture_draw", std::to_string(g_consumer_family_marker.capture_draw)},
       {"mode", g_consumer_family_marker.readback_requested
                    ? "authoritative_draw_marker_and_bounded_attachment_corpus"
                    : "authoritative_draw_marker_only"},
       {"xenos_draw", "preserved"},
       {"draw_suppression", "false"},
       {"resolve_suppression", "false"},
       {"suppression_eligible", "false"}});
  diagnostics::RecordEvent(
      "native_renderer.retained_pass.publication_summary",
      {{"status", !g_pass_publication.requested
                      ? "disabled"
                      : (!g_pass_publication.valid
                             ? "invalid_configuration"
                             : (g_pass_publication.failures
                                    ? "fallback_observed"
                                     : (g_pass_publication.published
                                            ? "complete"
                                           : "not_observed")))},
       {"attempts", std::to_string(g_pass_publication.attempts)},
       {"published", std::to_string(g_pass_publication.published)},
       {"failures", std::to_string(g_pass_publication.failures)},
       {"detail_events", std::to_string(g_pass_publication.detail_events)},
       {"detail_overflow", std::to_string(g_pass_publication.detail_overflow)},
       {"last_frame", std::to_string(g_pass_publication.last_frame)},
       {"last_draw", std::to_string(g_pass_publication.last_draw)},
       {"published_attachments", "color_and_depth_stencil"},
       {"guest_target_content", "per_attempt"},
       {"xenos_draw", g_sky_horizon_suppression.suppressed
                          ? "anchor_preserved_follower_suppressed"
                          : "preserved"},
       {"draw_suppression", g_sky_horizon_suppression.suppressed
                                ? "follower"
                                : "false"},
       {"resolve_suppression", "false"},
       {"side_effects", "preserved"},
       {"suppression_eligible",
        g_sky_horizon_suppression.armed ? "true" : "false"}});
  diagnostics::RecordEvent(
      "native_renderer.suppression_summary",
      {{"family", "sky_horizon"},
       {"status", !g_sky_horizon_suppression.requested
                      ? "disabled"
                      : (!g_sky_horizon_suppression.armed
                             ? "blocked_invalid_configuration"
                             : (g_sky_horizon_suppression.suppressed
                                    ? "active"
                                    : "not_observed"))},
       {"scope", "exact_follower_draw_after_full_pair_publication"},
       {"attempts", std::to_string(g_sky_horizon_suppression.attempts)},
       {"suppressed", std::to_string(g_sky_horizon_suppression.suppressed)},
       {"suppressed_vertices",
        std::to_string(g_sky_horizon_suppression.suppressed_vertices)},
       {"fallbacks", std::to_string(g_sky_horizon_suppression.fallbacks)},
       {"unexpected_suppressions",
        std::to_string(g_sky_horizon_suppression.unexpected_suppressions)},
       {"yielded_attempts",
        std::to_string(g_sky_horizon_suppression.yielded_attempts)},
       {"yielded_vertices",
        std::to_string(g_sky_horizon_suppression.yielded_vertices)},
       {"runtime_state",
        SuppressionRuntimeModeName(g_sky_horizon_suppression.mode)},
       {"warmup_publications",
        std::to_string(g_sky_horizon_suppression.warmup_publications)},
       {"warmup_frames",
        std::to_string(g_sky_horizon_suppression.warmup_frames)},
       {"warmup_resets",
        std::to_string(g_sky_horizon_suppression.warmup_resets)},
       {"cooldown_entries",
        std::to_string(g_sky_horizon_suppression.cooldown_entries)},
       {"state_detail_events",
        std::to_string(g_sky_horizon_suppression.state_detail_events)},
       {"state_detail_overflow",
        std::to_string(g_sky_horizon_suppression.state_detail_overflow)},
       {"last_yield_reason", g_sky_horizon_suppression.last_yield_reason},
       {"last_frame", std::to_string(g_sky_horizon_suppression.last_frame)},
       {"last_draw", std::to_string(g_sky_horizon_suppression.last_draw)},
       {"anchor_draw", "preserved"},
       {"follower_draw", g_sky_horizon_suppression.suppressed
                             ? "suppressed_after_publication"
                             : "preserved"},
       {"pm4_parsing", "preserved"},
       {"query_event_fence", "preserved"},
       {"memexport", "preserved"},
       {"resolves_consumers", "preserved"},
       {"resolve_suppression", "false"},
       {"xenos_fallback",
        "mandatory_on_state_yield_replay_or_publication_failure"}});
  g_graphics_census_installed = false;
  g_graphics_census_memory = nullptr;
  if (g_draw_census.window_first_frame && g_draw_census.window_draw_count) {
    EmitDrawCensusWindow(g_draw_census.window_last_frame);
  }
  EmitDependencyCensusWindow();
  if (g_index_scan.requested && g_index_scan.valid && !g_index_scan.completed) {
    diagnostics::RecordEvent(
        "native_renderer.census.index_scan",
        {{"signature", fmt::format("{:016X}", g_index_scan.target_signature)},
         {"status", "not_observed"},
         {"guest_payload_read", "false"},
         {"native_upload", "false"},
         {"native_draw", "false"},
         {"suppression_eligible", "false"}});
  }
  if (g_texture_scan.requested && g_texture_scan.valid &&
      !g_texture_scan.completed) {
    diagnostics::RecordEvent(
        "native_renderer.census.texture_scan",
        {{"signature",
         fmt::format("{:016X}", g_texture_scan.target_signature)},
         {"status", "not_observed"},
         {"guest_payload_read", "false"},
         {"native_upload", "false"},
         {"native_draw", "false"},
         {"suppression_eligible", "false"}});
  }
  if (g_pass_follower.requested && g_pass_follower.valid &&
      !g_pass_follower.completed) {
    diagnostics::RecordEvent(
        "native_renderer.census.pass_follower",
        {{"anchor_signature",
          fmt::format("{:016X}", g_pass_follower.target_signature)},
         {"status", "not_observed"},
         {"adjacency_mismatches",
          std::to_string(g_pass_follower.adjacency_mismatches)},
         {"qualification", "metadata_contract_only"},
         {"xenos_draw", "preserved"},
         {"native_draw", "false"},
         {"suppression_eligible", "false"}});
  }
  if (g_replay_snapshot.requested && g_replay_snapshot.valid &&
      !g_replay_snapshot.completed) {
    diagnostics::RecordEvent(
        "native_renderer.snapshot.capture",
        {{"signature",
          fmt::format("{:016X}", g_replay_snapshot.target_signature)},
         {"status", "not_observed"},
         {"guest_payload_read", "false"},
         {"payload_persisted", "false"},
         {"native_upload", "false"},
         {"native_draw", "false"},
         {"suppression_eligible", "false"}});
  }
  if (g_isolated_draw.requested && g_isolated_draw.valid &&
      !g_isolated_draw.completed) {
    diagnostics::RecordEvent(
        g_pass_follower.requested && g_pass_follower.valid
            ? "native_renderer.isolated_pass.result"
            : "native_renderer.isolated_draw.result",
      {{"signature",
          fmt::format("{:016X}", g_isolated_draw.target_signature)},
         {"anchor_signature",
          g_pass_follower.requested && g_pass_follower.valid
              ? fmt::format("{:016X}", g_pass_follower.target_signature)
              : ""},
         {"status", "not_observed"},
         {"title_lod_gate_required",
          g_isolated_draw.require_title_lod_candidate ? "true" : "false"},
         {"native_draw", "false"},
         {"xenos_draw", "preserved"},
         {"output_authority", "xenos"},
         {"suppression_eligible", "false"}});
  }
  diagnostics::RecordEvent(
      "native_renderer.census.prepared_shader_pair_summary",
      {{"pairs", std::to_string(g_prepared_shader_pair_count)},
       {"overflow", std::to_string(g_prepared_shader_pair_overflow)},
       {"candidate_unprepared_draws",
        std::to_string(g_candidate_unprepared_draw_count)},
       {"candidate_prepared_without_observation",
        std::to_string(g_candidate_prepared_without_observation_count)},
       {"capacity", std::to_string(kPreparedShaderPairCapacity)},
       {"mode", "pass_through"}});
}

} // namespace pinyon_shift::native_renderer

// This translation unit is the single owner for title-side graphics hooks.
// The hook runs immediately before FH1's sole VdSwap import and intentionally
// accepts no PPC registers: it cannot mutate guest arguments or control flow.
// All renderer experiments remain passive until their own explicit cvars are
// enabled and must dispatch through this owner.
void PinyonShiftObserveGraphicsFrame() {
  const bool census_requested =
      REXCVAR_GET(pinyon_shift_native_renderer_census);
  const bool dispatch_requested =
      REXCVAR_GET(pinyon_shift_native_renderer_dispatch_discovery);
  if (!census_requested && !dispatch_requested) {
    return;
  }

  const uint64_t frame_sequence =
      g_frame_sequence.fetch_add(1, std::memory_order_relaxed) + 1;
  if (frame_sequence != 1 && frame_sequence % kFrameSummaryInterval != 0) {
    return;
  }

  const std::string frame = std::to_string(frame_sequence);
  if (census_requested) {
    pinyon_shift::diagnostics::RecordEvent("native_renderer.census.frame",
                                           {{"frame_sequence", frame},
                                            {"guest_address", "829EFEB8"},
                                            {"mode", "pass_through"}});
  }
  if (dispatch_requested) {
    pinyon_shift::diagnostics::RecordEvent(
        "native_renderer.discovery.dispatch_frame",
        {{"frame_sequence", frame},
         {"guest_address", "829EFEB8"},
         {"mode", "read_only_metadata"}});
  }
}

void PinyonShiftObserveDrawIndexedDispatch(
    PPCRegister &r3, PPCRegister &r4, PPCRegister &r5, PPCRegister &r6,
    PPCRegister &r7, PPCRegister &r8, PPCRegister &r9, PPCRegister &r10,
    PPCRegister &r12) {
  ObserveTitleDispatch(DispatchWrapper::kDrawIndexed, r12.u32, r3.u32, r4.u32,
                       r5.u32, r6.u32, r7.u32, r8.u32, r9.u32, r10.u32);
  CapturePacketWrapperOrigin(DispatchWrapper::kDrawIndexed, r12.u32, r3.u32,
                             r4.u32, r5.u32, r6.u32, r7.u32, r8.u32,
                             r9.u32, r10.u32);
}

void PinyonShiftObserveDrawImmediateDispatch(
    PPCRegister &r3, PPCRegister &r4, PPCRegister &r5, PPCRegister &r6,
    PPCRegister &r7, PPCRegister &r8, PPCRegister &r9, PPCRegister &r10,
    PPCRegister &r12) {
  ObserveTitleDispatch(DispatchWrapper::kDrawImmediate, r12.u32, r3.u32, r4.u32,
                       r5.u32, r6.u32, r7.u32, r8.u32, r9.u32, r10.u32);
  CapturePacketWrapperOrigin(DispatchWrapper::kDrawImmediate, r12.u32, r3.u32,
                             r4.u32, r5.u32, r6.u32, r7.u32, r8.u32,
                             r9.u32, r10.u32);
}

void PinyonShiftObserveDrawAdapterDispatch(
    PPCRegister &r3, PPCRegister &r4, PPCRegister &r5, PPCRegister &r6,
    PPCRegister &r7, PPCRegister &r8, PPCRegister &r9, PPCRegister &r10,
    PPCRegister &r12) {
  ObserveTitleDispatch(DispatchWrapper::kDrawAdapter, r12.u32, r3.u32, r4.u32,
                       r5.u32, r6.u32, r7.u32, r8.u32, r9.u32, r10.u32);
  CaptureAdapterOrigin(r12.u32, r3.u32, r4.u32, r5.u32, r6.u32, r7.u32,
                       r8.u32, r9.u32, r10.u32);
}

void PinyonShiftObserveDrawPacketSubmission(PPCRegister &r3) {
  RecordTitleDrawPacket(r3.u32 + sizeof(uint32_t));
}

void ObserveIndirectConstructorEntry(
    uint32_t function_address, PPCRegister &r3, PPCRegister &r4,
    PPCRegister &r5, PPCRegister &r6, PPCRegister &r7, PPCRegister &r8,
    PPCRegister &r9, PPCRegister &r10, PPCRegister &r12) {
  PushIndirectConstructorOrigin(function_address, r12.u32, r3.u32, r4.u32,
                                r5.u32, r6.u32, r7.u32, r8.u32, r9.u32,
                                r10.u32);
}

#define PINYON_SHIFT_INDIRECT_CONSTRUCTOR_HOOKS(address)                       \
  void PinyonShiftObserveIndirectConstructor##address##Entry(                  \
      PPCRegister &r3, PPCRegister &r4, PPCRegister &r5, PPCRegister &r6,      \
      PPCRegister &r7, PPCRegister &r8, PPCRegister &r9, PPCRegister &r10,     \
      PPCRegister &r12) {                                                       \
    ObserveIndirectConstructorEntry(0x##address, r3, r4, r5, r6, r7, r8, r9,  \
                                    r10, r12);                                  \
  }                                                                             \
  void PinyonShiftObserveIndirectConstructor##address##Exit() {                \
    PopIndirectConstructorOrigin(0x##address);                                  \
  }

PINYON_SHIFT_INDIRECT_CONSTRUCTOR_HOOKS(82409398)
PINYON_SHIFT_INDIRECT_CONSTRUCTOR_HOOKS(82416A00)
PINYON_SHIFT_INDIRECT_CONSTRUCTOR_HOOKS(8246FB98)
PINYON_SHIFT_INDIRECT_CONSTRUCTOR_HOOKS(8263BCB8)
PINYON_SHIFT_INDIRECT_CONSTRUCTOR_HOOKS(829E8E00)
PINYON_SHIFT_INDIRECT_CONSTRUCTOR_HOOKS(829EC400)

#undef PINYON_SHIFT_INDIRECT_CONSTRUCTOR_HOOKS

void ObserveIndirectOwnerEntry(
    uint32_t function_address, PPCRegister &r3, PPCRegister &r4,
    PPCRegister &r5, PPCRegister &r6, PPCRegister &r7, PPCRegister &r8,
    PPCRegister &r9, PPCRegister &r10, PPCRegister &r12) {
  PushIndirectOwnerOrigin(function_address, r12.u32, r3.u32, r4.u32, r5.u32,
                          r6.u32, r7.u32, r8.u32, r9.u32, r10.u32);
}

#define PINYON_SHIFT_INDIRECT_OWNER_HOOKS(address)                             \
  void PinyonShiftObserveIndirectOwner##address##Entry(                        \
      PPCRegister &r3, PPCRegister &r4, PPCRegister &r5, PPCRegister &r6,      \
      PPCRegister &r7, PPCRegister &r8, PPCRegister &r9, PPCRegister &r10,     \
      PPCRegister &r12) {                                                       \
    ObserveIndirectOwnerEntry(0x##address, r3, r4, r5, r6, r7, r8, r9, r10,   \
                              r12);                                            \
  }                                                                             \
  void PinyonShiftObserveIndirectOwner##address##Exit() {                      \
    PopIndirectOwnerOrigin(0x##address);                                        \
  }

PINYON_SHIFT_INDIRECT_OWNER_HOOKS(82409668)
PINYON_SHIFT_INDIRECT_OWNER_HOOKS(824167F8)
PINYON_SHIFT_INDIRECT_OWNER_HOOKS(8246E8F8)
PINYON_SHIFT_INDIRECT_OWNER_HOOKS(829F5FF0)

#undef PINYON_SHIFT_INDIRECT_OWNER_HOOKS

void ObserveIndirectProducerEntry(
    uint32_t function_address, PPCRegister &r3, PPCRegister &r4,
    PPCRegister &r5, PPCRegister &r6, PPCRegister &r7, PPCRegister &r8,
    PPCRegister &r9, PPCRegister &r10, PPCRegister &r12) {
  PushIndirectProducerOrigin(function_address, r12.u32, r3.u32, r4.u32,
                             r5.u32, r6.u32, r7.u32, r8.u32, r9.u32,
                             r10.u32);
}

#define PINYON_SHIFT_INDIRECT_PRODUCER_HOOKS(address)                          \
  void PinyonShiftObserveIndirectProducer##address##Entry(                     \
      PPCRegister &r3, PPCRegister &r4, PPCRegister &r5, PPCRegister &r6,      \
      PPCRegister &r7, PPCRegister &r8, PPCRegister &r9, PPCRegister &r10,     \
      PPCRegister &r12) {                                                       \
    ObserveIndirectProducerEntry(0x##address, r3, r4, r5, r6, r7, r8, r9,     \
                                 r10, r12);                                     \
  }                                                                             \
  void PinyonShiftObserveIndirectProducer##address##Exit() {                   \
    PopIndirectProducerOrigin(0x##address);                                     \
  }

PINYON_SHIFT_INDIRECT_PRODUCER_HOOKS(8240D070)
PINYON_SHIFT_INDIRECT_PRODUCER_HOOKS(82417060)
PINYON_SHIFT_INDIRECT_PRODUCER_HOOKS(829F6360)

#undef PINYON_SHIFT_INDIRECT_PRODUCER_HOOKS

void ObserveIndirectContextEntry(
    uint32_t function_address, PPCRegister &r3, PPCRegister &r4,
    PPCRegister &r5, PPCRegister &r6, PPCRegister &r7, PPCRegister &r8,
    PPCRegister &r9, PPCRegister &r10, PPCRegister &r12) {
  PushIndirectContextOrigin(function_address, r12.u32, r3.u32, r4.u32,
                            r5.u32, r6.u32, r7.u32, r8.u32, r9.u32,
                            r10.u32);
}

#define PINYON_SHIFT_INDIRECT_CONTEXT_HOOKS(address)                           \
  void PinyonShiftObserveIndirectContext##address##Entry(                      \
      PPCRegister &r3, PPCRegister &r4, PPCRegister &r5, PPCRegister &r6,      \
      PPCRegister &r7, PPCRegister &r8, PPCRegister &r9, PPCRegister &r10,     \
      PPCRegister &r12) {                                                       \
    ObserveIndirectContextEntry(0x##address, r3, r4, r5, r6, r7, r8, r9,      \
                                r10, r12);                                     \
  }                                                                             \
  void PinyonShiftObserveIndirectContext##address##Exit() {                    \
    PopIndirectContextOrigin(0x##address);                                      \
  }

PINYON_SHIFT_INDIRECT_CONTEXT_HOOKS(8240CF68)
PINYON_SHIFT_INDIRECT_CONTEXT_HOOKS(82417BC0)
PINYON_SHIFT_INDIRECT_CONTEXT_HOOKS(824365B0)
PINYON_SHIFT_INDIRECT_CONTEXT_HOOKS(829F6620)

#undef PINYON_SHIFT_INDIRECT_CONTEXT_HOOKS

void PinyonShiftObserveProceduralModelConstructorEntry(PPCRegister &r3) {
  BeginSemanticReceiverConstruction(r3.u32);
}

void PinyonShiftObserveProceduralModelConstructorExit() {
  EndSemanticReceiverConstruction();
}

void PinyonShiftObserveProceduralModelDestructorEntry(PPCRegister &r3) {
  BeginSemanticReceiverDestruction(r3.u32);
}

void PinyonShiftObserveProceduralModelDestructorExit() {
  EndSemanticReceiverDestruction();
}

void PinyonShiftObserveProceduralModelVisibilityEntry(PPCRegister &r3) {
  BeginSemanticReceiverStage(r3.u32, SemanticReceiverStage::kVisibility);
}

void PinyonShiftObserveProceduralModelVisibilityExit() {
  if (g_active_semantic_visibility_record.active) {
    g_semantic_visibility_record_stack_faults.fetch_add(
        1, std::memory_order_relaxed);
    g_semantic_visibility_exit_with_record.fetch_add(
        1, std::memory_order_relaxed);
    g_semantic_visibility_records_open.fetch_sub(
        1, std::memory_order_relaxed);
    g_active_semantic_visibility_record = {};
  }
  EndSemanticReceiverStage(SemanticReceiverStage::kVisibility);
}

void PinyonShiftObserveProceduralModelVisibilityRecordEntry(
    PPCRegister &r15, PPCRegister &r16, PPCRegister &r20,
    PPCRegister &r21, PPCRegister &r23, PPCRegister &f26) {
  BeginSemanticVisibilityRecord(r20.u32, r16.u32, r15.u32, r23.u32,
                                r21.u32, f26.f64);
}

void PinyonShiftObserveProceduralModelVisibilityRuntimeThreshold(
    PPCRegister &f0, PPCRegister &f26) {
  ObserveSemanticVisibilityRuntimeThreshold(f26.f64, f0.f64);
}

void PinyonShiftObserveProceduralModelVisibilityDescriptorThreshold(
    PPCRegister &f0, PPCRegister &f26) {
  ObserveSemanticVisibilityDescriptorThreshold(f26.f64, f0.f64);
}

void PinyonShiftObserveProceduralModelVisibilityCandidateThreshold(
    PPCRegister &f0, PPCRegister &f29) {
  ObserveSemanticVisibilityCandidateThreshold(f0.f64, f29.f64);
}

void PinyonShiftObserveProceduralModelVisibilityLocalDistance(
    PPCRegister &f0, PPCRegister &f31) {
  ObserveSemanticVisibilityLocalDistance(f31.f64, f0.f64);
}

void PinyonShiftObserveProceduralModelVisibilitySpatialHelperInput(
    PPCRegister &r3, PPCRegister &r4, PPCRegister &r5) {
  ObserveSemanticVisibilitySpatialHelperInput(r3.u32, r4.u32, r5.u32);
}

void PinyonShiftObserveProceduralModelVisibilitySpatialHelperResult(
    PPCRegister &r3) {
  ObserveSemanticVisibilitySpatialHelperResult(r3.u32);
}

void PinyonShiftObserveProceduralModelVisibilityCategoryHelperInput(
    PPCRegister &r3, PPCVRegister &v1, PPCVRegister &v2) {
  ObserveSemanticVisibilityCategoryHelperInput(r3.u32, v1, v2);
}

void PinyonShiftObserveProceduralModelVisibilityCategoryHelperResult(
    PPCRegister &r3) {
  ObserveSemanticVisibilityCategoryHelperResult(r3.u32);
}

void PinyonShiftObserveProceduralModelVisibilityLodPrimary(
    PPCRegister &r6) {
  ObserveSemanticVisibilityLod(r6.u32);
}

void PinyonShiftObserveProceduralModelVisibilityLodSecondary(
    PPCRegister &r6) {
  ObserveSemanticVisibilityLod(r6.u32);
}

void PinyonShiftObserveProceduralModelVisibilityResult(PPCRegister &r11) {
  ObserveSemanticVisibilityResult(r11.u32);
}

void PinyonShiftObserveProceduralModelVisibilityRecordExit(
    PPCRegister &r16, PPCRegister &r20) {
  EndSemanticVisibilityRecord(r20.u32, r16.u32);
}

void PinyonShiftObserveProceduralModelRenderStateEntry(PPCRegister &r3) {
  BeginSemanticReceiverStage(r3.u32, SemanticReceiverStage::kRenderState);
}

void PinyonShiftObserveProceduralModelRenderStateExit() {
  EndSemanticReceiverStage(SemanticReceiverStage::kRenderState);
}

void PinyonShiftObserveProceduralModelRenderItem(
    PPCRegister &r1, PPCRegister &r3, PPCRegister &r4, PPCRegister &r5,
    PPCRegister &r6, PPCRegister &r7, PPCRegister &r8, PPCRegister &r9,
    PPCRegister &r10) {
  BeginProceduralModelRenderItem(
      r1.u32, r3.u32,
      {r4.u32, r5.u32, r6.u32, r7.u32, r8.u32, r9.u32, r10.u32});
}

void PinyonShiftObserveProceduralModelRenderItemExit() {
  EndProceduralModelRenderItem();
}

void PinyonShiftObserveProceduralModelPrimaryResourceBinding(
    PPCRegister &r3, PPCRegister &r4, PPCRegister &r5, PPCRegister &r6,
    PPCRegister &r20, PPCRegister &r26, PPCRegister &r27, PPCRegister &r28,
    PPCRegister &r31) {
  RecordProceduralModelResourceBinding(
      0, r3.u32, r4.u32, r5.u32, r6.u32, r20.u32, r26.u32, r27.u32,
      r28.u32, r31.u32);
}

void PinyonShiftObserveProceduralModelSecondaryResourceBinding(
    PPCRegister &r3, PPCRegister &r4, PPCRegister &r5, PPCRegister &r6,
    PPCRegister &r20, PPCRegister &r26, PPCRegister &r27, PPCRegister &r28,
    PPCRegister &r31) {
  RecordProceduralModelResourceBinding(
      1, r3.u32, r4.u32, r5.u32, r6.u32, r20.u32, r26.u32, r27.u32,
      r28.u32, r31.u32);
}

void PinyonShiftObserveProceduralModelResourceResolutionResult(
    PPCRegister &r3, PPCRegister &r30, PPCRegister &r31) {
  RecordProceduralModelResourceResolutionResult(r3.u32, r30.u32, r31.u32);
}

void PinyonShiftObserveProceduralModelResourceProviderLookup(PPCRegister &r3,
                                                             PPCRegister &r29,
                                                             PPCRegister &r31) {
  RecordProceduralModelResourceProviderLookup(r3.u32, r29.u32, r31.u32);
}

void PinyonShiftObserveProceduralModelResourceProviderPrimaryPredicate(
    PPCRegister &r3, PPCRegister &r30) {
  RecordProceduralModelResourceProviderPrimaryPredicate(r3.u32, r30.u32);
}

void PinyonShiftObserveProceduralModelResourceProviderFallbackPredicate(
    PPCRegister &r3, PPCRegister &r30) {
  RecordProceduralModelResourceProviderFallbackPredicate(r3.u32, r30.u32);
}

void PinyonShiftObserveProceduralModelResourceProviderMethodResult(
    PPCRegister &r3, PPCRegister &r30, PPCRegister &r31) {
  RecordProceduralModelResourceProviderMethodResult(r3.u32, r30.u32, r31.u32);
}

void PinyonShiftObserveProceduralModelResourceSecondaryResolutionResult(
    PPCRegister &r3, PPCRegister &r30, PPCRegister &r31) {
  RecordProceduralModelResourceSecondaryResolutionResult(r3.u32, r30.u32,
                                                         r31.u32);
}

void PinyonShiftObserveProceduralModelResourceBindDispatch(
    PPCRegister &r3, PPCRegister &r4, PPCRegister &r5,
    PPCRegister &r30, PPCRegister &r31) {
  RecordProceduralModelResourceBindDispatch(
      r3.u32, r4.u32, r5.u32, r30.u32, r31.u32);
}

void PinyonShiftObserveProceduralModelGeometrySubmission(
    PPCRegister &r20, PPCRegister &r22, PPCRegister &r24, PPCRegister &r25,
    PPCRegister &r26, PPCRegister &r27, PPCRegister &r28,
    PPCRegister &r31) {
  RecordProceduralModelGeometrySubmission(
      r20.u32, r22.u32, r24.u32, r25.u32, r26.u32, r27.u32, r28.u32,
      r31.u32);
}

void PinyonShiftObserveProceduralModelDirectDrawPacket(
    PPCRegister &r23, PPCRegister &r24, PPCRegister &r25, PPCRegister &r28,
    PPCRegister &r29, PPCRegister &r30) {
  RecordProceduralModelSemanticDrawPacket(
      r30.u32 + sizeof(uint32_t), 0x82416260,
      {r23.u32, r24.u32, r25.u32, r28.u32, r29.u32, r30.u32, 0, 0});
}

void PinyonShiftObserveProceduralModelAlternateDrawPacket(
    PPCRegister &r6, PPCRegister &r23, PPCRegister &r24, PPCRegister &r25,
    PPCRegister &r28, PPCRegister &r29) {
  RecordProceduralModelSemanticDrawPacket(
      r6.u32 + sizeof(uint32_t), 0x824162F4,
      {r23.u32, r24.u32, r25.u32, r28.u32, r29.u32, r6.u32, 0, 0});
}

void PinyonShiftObserveIndirectPacket824095B4(PPCRegister &r11,
                                               PPCRegister &r28) {
  RecordTitleIndirectPacket(r11.u32 + r28.u32, 0x824095B4, 0x82409398);
}

void PinyonShiftObserveIndirectPacket82416EFC(PPCRegister &r30) {
  RecordTitleIndirectPacket(r30.u32 + sizeof(uint32_t), 0x82416EFC,
                            0x82416A00);
}

void PinyonShiftObserveIndirectPacket8246FC1C(PPCRegister &r11) {
  RecordTitleIndirectPacket(r11.u32 + sizeof(uint32_t), 0x8246FC1C,
                            0x8246FB98);
}

void PinyonShiftObserveIndirectPacket8263BD64(PPCRegister &r9) {
  RecordTitleIndirectPacket(r9.u32 + sizeof(uint32_t), 0x8263BD64,
                            0x8263BCB8);
}

void PinyonShiftObserveIndirectPacket829E8E88(PPCRegister &r1) {
  RecordTitleIndirectPacket(r1.u32 + 88, 0x829E8E88, 0x829E8E00);
}

void PinyonShiftObserveIndirectPacket829EC49C(PPCRegister &r11) {
  RecordTitleIndirectPacket(r11.u32 + sizeof(uint32_t), 0x829EC49C,
                            0x829EC400);
}

void PinyonShiftObserveResolveControllerDispatch(
    PPCRegister &r3, PPCRegister &r4, PPCRegister &r5, PPCRegister &r6,
    PPCRegister &r7, PPCRegister &r8, PPCRegister &r9, PPCRegister &r10,
    PPCRegister &r12) {
  ObserveTitleDispatch(DispatchWrapper::kResolveController, r12.u32, r3.u32,
                       r4.u32, r5.u32, r6.u32, r7.u32, r8.u32, r9.u32,
                       r10.u32);
}

void PinyonShiftObserveResolveSetupDispatch(
    PPCRegister &r3, PPCRegister &r4, PPCRegister &r5, PPCRegister &r6,
    PPCRegister &r7, PPCRegister &r8, PPCRegister &r9, PPCRegister &r10,
    PPCRegister &r12) {
  ObserveTitleDispatch(DispatchWrapper::kResolveSetup, r12.u32, r3.u32, r4.u32,
                       r5.u32, r6.u32, r7.u32, r8.u32, r9.u32, r10.u32);
}

void PinyonShiftObserveVizQueryBeginDispatch(
    PPCRegister &r3, PPCRegister &r4, PPCRegister &r5, PPCRegister &r6,
    PPCRegister &r7, PPCRegister &r8, PPCRegister &r9, PPCRegister &r10,
    PPCRegister &r12) {
  ObserveTitleDispatch(DispatchWrapper::kVizQueryBegin, r12.u32, r3.u32,
                       r4.u32, r5.u32, r6.u32, r7.u32, r8.u32, r9.u32,
                       r10.u32);
}

void PinyonShiftObserveVizQueryEndDispatch(
    PPCRegister &r3, PPCRegister &r4, PPCRegister &r5, PPCRegister &r6,
    PPCRegister &r7, PPCRegister &r8, PPCRegister &r9, PPCRegister &r10,
    PPCRegister &r12) {
  ObserveTitleDispatch(DispatchWrapper::kVizQueryEnd, r12.u32, r3.u32, r4.u32,
                       r5.u32, r6.u32, r7.u32, r8.u32, r9.u32, r10.u32);
}

void PinyonShiftObserveVizQueryOwnerDispatch(
    PPCRegister &r3, PPCRegister &r4, PPCRegister &r5, PPCRegister &r6,
    PPCRegister &r7, PPCRegister &r8, PPCRegister &r9, PPCRegister &r10,
    PPCRegister &r12) {
  ObserveTitleDispatch(DispatchWrapper::kVizQueryOwner, r12.u32, r3.u32,
                       r4.u32, r5.u32, r6.u32, r7.u32, r8.u32, r9.u32,
                       r10.u32);
}

void PinyonShiftObserveBinningScissorStateDispatch(
    PPCRegister &r3, PPCRegister &r4, PPCRegister &r5, PPCRegister &r6,
    PPCRegister &r7, PPCRegister &r8, PPCRegister &r9, PPCRegister &r10,
    PPCRegister &r12) {
  ObserveTitleDispatch(DispatchWrapper::kBinningScissorState, r12.u32, r3.u32,
                       r4.u32, r5.u32, r6.u32, r7.u32, r8.u32, r9.u32,
                       r10.u32);
}

void PinyonShiftObserveBinningStateResetDispatch(
    PPCRegister &r3, PPCRegister &r4, PPCRegister &r5, PPCRegister &r6,
    PPCRegister &r7, PPCRegister &r8, PPCRegister &r9, PPCRegister &r10,
    PPCRegister &r12) {
  ObserveTitleDispatch(DispatchWrapper::kBinningStateReset, r12.u32, r3.u32,
                       r4.u32, r5.u32, r6.u32, r7.u32, r8.u32, r9.u32,
                       r10.u32);
}
