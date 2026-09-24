#pragma once

#include <cstdint>
#include <filesystem>
#include <memory>
#include <span>

struct ID3D12Device;

namespace pinyon_shift::native_renderer {

struct Snr04SharedTarget;
std::shared_ptr<Snr04SharedTarget> CreateSnr04SharedTarget(
    ID3D12Device* device, uint32_t samples);
struct Snr04BatchResult {
  uint64_t source_frame = 0;
  uint32_t draws = 0, covered_pixels = 0;
  uint64_t target_setup_us = 0, upload_cpu_us = 0, upload_bytes = 0;
  uint64_t gpu_draw_us = 0, stage_wall_us = 0;
};
Snr04BatchResult RunSnr04BatchDiagnostic(
    const std::filesystem::path& manifest, ID3D12Device* device,
    uint32_t samples);

struct Snr04SegmentOptions {
  uint64_t first_sequence = 0, last_sequence = 0;
  uint32_t first_id = 0, draw_count = 0;
  std::filesystem::path prior_output;
  std::filesystem::path alpha_bc3;
  std::shared_ptr<Snr04SharedTarget> shared_target;
  bool shared_first = false, shared_final = false;
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

uint32_t RunSnr04ProceduralDiagnostic(
    const std::filesystem::path& fixture,
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

uint32_t RunSnr04ManagerDiagnostic(
    const std::filesystem::path& fixture,
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

}  // namespace pinyon_shift::native_renderer
