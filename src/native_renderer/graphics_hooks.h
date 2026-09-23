#pragma once

#include <cstdint>

namespace rex::system {
class IGraphicsSystem;
}
namespace rex::memory {
class Memory;
}

namespace pinyon_shift::native_renderer {

void InstallGraphicsCensus(rex::system::IGraphicsSystem* graphics_system,
                           rex::memory::Memory* memory);
void UninstallGraphicsCensus(rex::system::IGraphicsSystem* graphics_system);
bool Snr03ProbeEnabled();
void ObserveSnr03OutputFrame(uint64_t output_frame, void* device);
bool Snr02ItemProbeEnabled();
void ObserveSnr02ItemOutputFrame(uint64_t output_frame, void* device);

}  // namespace pinyon_shift::native_renderer
