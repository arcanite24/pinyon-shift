#pragma once

#include <cstdint>
#include <filesystem>
#include <span>

struct ID3D12Device;

namespace pinyon_shift::native_renderer {

struct Snr04SegmentOptions {
  uint64_t first_sequence = 0, last_sequence = 0;
  uint32_t first_id = 0, draw_count = 0;
  std::filesystem::path prior_output;
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
    ID3D12Device* device = nullptr,
    const Snr04SegmentOptions* segment = nullptr);

uint32_t RunSnr04TrackDiagnostic(
    const std::filesystem::path& fixture,
    const std::filesystem::path& shader_directory,
    const std::filesystem::path& output_directory,
    ID3D12Device* device = nullptr,
    const Snr04SegmentOptions* segment = nullptr);

uint32_t RunSnr04ManagerDiagnostic(
    const std::filesystem::path& fixture,
    const std::filesystem::path& shader_directory,
    const std::filesystem::path& output_directory,
    ID3D12Device* device = nullptr,
    const Snr04SegmentOptions* segment = nullptr);

uint32_t RunSnr04RemainderDiagnostic(
    const std::filesystem::path& fixture,
    const std::filesystem::path& shader_directory,
    const std::filesystem::path& output_directory,
    ID3D12Device* device = nullptr,
    const Snr04SegmentOptions* segment = nullptr);

}  // namespace pinyon_shift::native_renderer
