#pragma once

// What graphics APIs this PC offers, probed before the GPU plugin loads so
// the game can pick a backend the driver can run (D3D11_BACKLOG.md D11-2.1).

#include <cstdint>

namespace pinyon_shift::platform {

// The highest Vulkan API version of any physical device, as VK_MAKE_VERSION
// packs it, or 0 when there is no loader, no driver or no device.
uint32_t BestVulkanDeviceApiVersion();

// A Direct3D 11 hardware device can be made at feature level 11_0. Always
// false off Windows.
bool HasDirect3D11FeatureLevel11();

}  // namespace pinyon_shift::platform
