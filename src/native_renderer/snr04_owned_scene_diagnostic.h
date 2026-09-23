#pragma once

#include <cstdint>
#include <filesystem>
#include <span>

struct ID3D12Device;

namespace pinyon_shift::native_renderer {

uint32_t RunSnr04OwnedSceneDiagnostic(
    const std::filesystem::path& fixture,
    const std::filesystem::path& vertex_shader,
    const std::filesystem::path& output_directory,
    ID3D12Device* device = nullptr, uint32_t samples = 1);

uint32_t RunSnr04OwnedSceneDiagnostic(
    std::span<const char> fixture,
    const std::filesystem::path& vertex_shader,
    const std::filesystem::path& output_directory,
    ID3D12Device* device = nullptr, uint32_t samples = 1);

uint32_t RunSnr04ProceduralDiagnostic(
    const std::filesystem::path& fixture,
    const std::filesystem::path& shader_directory,
    const std::filesystem::path& output_directory,
    ID3D12Device* device = nullptr);

}  // namespace pinyon_shift::native_renderer
