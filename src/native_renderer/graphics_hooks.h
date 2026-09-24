#pragma once

#include <cstdint>
#include <memory>

namespace rex::system {
class IGraphicsSystem;
}
namespace rex::memory {
class Memory;
}

namespace pinyon_shift::native_renderer {

struct Snr04LiveScene;

void InstallGraphicsCensus(rex::system::IGraphicsSystem* graphics_system,
                           rex::memory::Memory* memory);
void UninstallGraphicsCensus(rex::system::IGraphicsSystem* graphics_system);
bool Snr03ProbeEnabled();
void ObserveSnr03OutputFrame(uint64_t output_frame, void* device);
bool Snr02ItemProbeEnabled();
void ObserveSnr02ItemOutputFrame(uint64_t output_frame, void* device);
void ObserveSnr02TrackOutputFrame(uint64_t output_frame);
std::shared_ptr<const Snr04LiveScene> SnapshotSnr04LiveScene(
    uint64_t output_frame);
void ObserveSnr04BatchOutputFrame(uint64_t output_frame, void* device,
                                 uint64_t capture_us);
void FinishSnr04BatchDiagnostic();

}  // namespace pinyon_shift::native_renderer
