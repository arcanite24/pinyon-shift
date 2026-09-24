#pragma once

#include <array>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <span>
#include <string>
#include <vector>

struct ID3D12Device;

namespace pinyon_shift::native_renderer {

struct Snr04VegetationItem {
  struct Variant {
    uint64_t sequence = 0;
    std::array<uint32_t, 64> system{};
    std::array<uint32_t, 96> vertex_constants{};
  };
  uint32_t packet = 0, vertex_count = 0;
  std::array<uint32_t, 96> constants{};
  std::array<uint32_t, 3> pixel_registers{};
  std::array<uint32_t, 12> pixel_constants{};
  std::array<uint32_t, 64> system{}, original_system{};
  std::array<uint32_t, 4> fetch{};
  std::vector<Variant> variants;
  std::vector<char> vertices;
};
struct Snr04VegetationScene {
  uint64_t source_frame = 0;
  bool sequenced = true;
  std::string fixture_sha256;
  std::vector<Snr04VegetationItem> items;
};

struct Snr04ProceduralDraw {
  uint64_t sequence = 0, vertex_shader = 0;
  uint32_t vertex_count = 0;
  std::array<uint32_t, 64> system{};
  std::array<float, 6> viewport{};
  std::array<int32_t, 4> scissor{};
};
struct Snr04ProceduralItem {
  uint32_t packet = 0;
  std::vector<char> vertices;
  std::array<uint32_t, 4> fetch{};
  std::vector<uint32_t> constants;
  std::vector<Snr04ProceduralDraw> draws;
};
struct Snr04ProceduralScene {
  uint64_t frame = 0;
  bool character = false;
  std::string sha;
  std::vector<Snr04ProceduralItem> items;
};

// Immutable ownership of one source frame at the output decision boundary.
// The first live pilot requires track, items and vegetation; other families
// remain available when complete, without making characters an L1 gate.
struct Snr04LiveScene {
  uint64_t source_frame = 0;
  std::shared_ptr<const std::vector<char>> track, characters, manager, remainder;
  std::shared_ptr<const Snr04ProceduralScene> items;
  std::shared_ptr<const Snr04VegetationScene> vegetation;
  uint32_t core_draws = 0;
};

struct Snr04SharedTarget;
std::shared_ptr<Snr04SharedTarget> CreateSnr04SharedTarget(
    ID3D12Device* device, uint32_t samples);
struct Snr04BatchSegmentInput {
  std::shared_ptr<const std::vector<char>> fixture;
  std::shared_ptr<const Snr04VegetationScene> vegetation;
  std::shared_ptr<const Snr04ProceduralScene> procedural;
  std::filesystem::path shader, output;
  uint8_t family = 0;
  uint64_t first_sequence = 0, last_sequence = 0;
  uint32_t first_id = 0, draw_count = 0;
};
struct Snr04BatchInput {
  uint64_t source_frame = 0;
  std::vector<Snr04BatchSegmentInput> segments;
  bool require_shader_fixture_digest = true;
};
struct Snr04BatchResult {
  uint64_t source_frame = 0;
  uint32_t draws = 0, covered_pixels = 0;
  uint64_t target_setup_us = 0, upload_cpu_us = 0, upload_bytes = 0;
  uint64_t upload_reused_bytes = 0, upload_cross_frame_reused_bytes = 0;
  uint64_t cache_key_bytes = 0;
  uint32_t cache_entries = 0;
  uint64_t gpu_draw_us = 0, stage_wall_us = 0;
  uint64_t queue_wait_us = 0;
};
Snr04BatchResult RunSnr04BatchDiagnostic(
    const std::filesystem::path& manifest, ID3D12Device* device,
    uint32_t samples, bool require_shader_fixture_digest = true);
Snr04BatchResult RunSnr04BatchDiagnosticFromBytes(
    const Snr04BatchInput& input, ID3D12Device* device, uint32_t samples,
    const std::filesystem::path& timing_path = {});

struct Snr04SegmentOptions {
  uint64_t first_sequence = 0, last_sequence = 0;
  uint32_t first_id = 0, draw_count = 0;
  std::filesystem::path prior_output;
  std::filesystem::path alpha_bc3;
  std::shared_ptr<Snr04SharedTarget> shared_target;
  bool shared_first = false, shared_final = false;
  bool require_shader_fixture_digest = true;
  uint64_t* gpu_draw_us = nullptr;
};

uint32_t RunSnr04OwnedSceneDiagnostic(
    const std::filesystem::path& fixture,
    const std::filesystem::path& vertex_shader,
    const std::filesystem::path& output_directory,
    ID3D12Device* device = nullptr, uint32_t samples = 1,
    const Snr04SegmentOptions* segment = nullptr);

uint32_t RunSnr04OwnedSceneDiagnostic(
    std::span<const char> fixture,
    const std::filesystem::path& vertex_shader,
    const std::filesystem::path& output_directory,
    ID3D12Device* device = nullptr, uint32_t samples = 1,
    const Snr04SegmentOptions* segment = nullptr);

uint32_t RunSnr04OwnedSceneDiagnostic(
    const Snr04VegetationScene& scene,
    const std::filesystem::path& vertex_shader,
    const std::filesystem::path& output_directory,
    ID3D12Device* device = nullptr, uint32_t samples = 1,
    const Snr04SegmentOptions* segment = nullptr);

uint32_t RunSnr04ProceduralDiagnostic(
    const std::filesystem::path& fixture,
    const std::filesystem::path& shader_directory,
    const std::filesystem::path& output_directory,
    ID3D12Device* device = nullptr, uint32_t samples = 1,
    const Snr04SegmentOptions* segment = nullptr);

uint32_t RunSnr04ProceduralDiagnosticFromBytes(
    std::span<const char> fixture,
    const std::filesystem::path& shader_directory,
    const std::filesystem::path& output_directory,
    ID3D12Device* device = nullptr, uint32_t samples = 1,
    const Snr04SegmentOptions* segment = nullptr);

uint32_t RunSnr04ProceduralDiagnostic(
    const Snr04ProceduralScene& scene,
    const std::filesystem::path& shader_directory,
    const std::filesystem::path& output_directory,
    ID3D12Device* device = nullptr, uint32_t samples = 1,
    const Snr04SegmentOptions* segment = nullptr);

uint32_t RunSnr04TrackDiagnostic(
    const std::filesystem::path& fixture,
    const std::filesystem::path& shader_directory,
    const std::filesystem::path& output_directory,
    ID3D12Device* device = nullptr, uint32_t samples = 1,
    const Snr04SegmentOptions* segment = nullptr);

uint32_t RunSnr04TrackDiagnosticFromBytes(
    std::span<const char> fixture,
    const std::filesystem::path& shader_directory,
    const std::filesystem::path& output_directory,
    ID3D12Device* device = nullptr, uint32_t samples = 1,
    const Snr04SegmentOptions* segment = nullptr);

uint32_t RunSnr04ManagerDiagnostic(
    const std::filesystem::path& fixture,
    const std::filesystem::path& shader_directory,
    const std::filesystem::path& output_directory,
    ID3D12Device* device = nullptr, uint32_t samples = 1,
    const Snr04SegmentOptions* segment = nullptr);

uint32_t RunSnr04ManagerDiagnosticFromBytes(
    std::span<const char> fixture,
    const std::filesystem::path& shader_directory,
    const std::filesystem::path& output_directory,
    ID3D12Device* device = nullptr, uint32_t samples = 1,
    const Snr04SegmentOptions* segment = nullptr);

uint32_t RunSnr04RemainderDiagnostic(
    const std::filesystem::path& fixture,
    const std::filesystem::path& shader_directory,
    const std::filesystem::path& output_directory,
    ID3D12Device* device = nullptr, uint32_t samples = 1,
    const Snr04SegmentOptions* segment = nullptr);

uint32_t RunSnr04RemainderDiagnosticFromBytes(
    std::span<const char> fixture,
    const std::filesystem::path& shader_directory,
    const std::filesystem::path& output_directory,
    ID3D12Device* device = nullptr, uint32_t samples = 1,
    const Snr04SegmentOptions* segment = nullptr);

}  // namespace pinyon_shift::native_renderer
