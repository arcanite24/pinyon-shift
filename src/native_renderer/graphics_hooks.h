#pragma once

#include <cstdint>

namespace rex::system {
class IGraphicsSystem;
}
namespace rex::memory {
class Memory;
}

namespace pinyon_shift::native_renderer {

enum class NativeShadowPrototypeState : uint32_t {
  kDisabled,
  kFallbackXenos,
  kPublishedCurrentFrame,
  kFailClosed,
};

struct VehiclePoseObservation {
  uint32_t generation = 0;
  uint32_t source = 0;
  uint32_t owner = 0;
  uint32_t owner_vtable = 0;
  uint32_t slot = 0;
  uint32_t position_address = 0;
  uint32_t forward_address = 0;
  float x = 0.0f;
  float y = 0.0f;
  float z = 0.0f;
  float w = 0.0f;
  float forward_x = 0.0f;
  float forward_y = 0.0f;
  float forward_z = 0.0f;
  float forward_w = 0.0f;
  bool presentation_stabilized = false;
};

void ObserveVehiclePose(const VehiclePoseObservation& observation);
void BeginVehicleOwnerMethod(uint32_t method_address, uint32_t owner_address);
void EndVehicleOwnerMethod(uint32_t method_address);
void ObserveVehicleOwnerIndirectCall(uint32_t method_address,
                                     uint32_t callsite_address,
                                     uint32_t target_address,
                                     uint32_t object_address);

void InstallGraphicsCensus(rex::system::IGraphicsSystem* graphics_system,
                           rex::memory::Memory* memory);
void UninstallGraphicsCensus(rex::system::IGraphicsSystem* graphics_system);
NativeShadowPrototypeState GetNativeShadowPrototypeState(
    uint64_t frame_sequence);

}  // namespace pinyon_shift::native_renderer
