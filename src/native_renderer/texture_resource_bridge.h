#pragma once

namespace rex::system {
class IGraphicsSystem;
}

namespace pinyon_shift::native_renderer {

void InstallTextureResourceBridge(rex::system::IGraphicsSystem* graphics_system);
void UninstallTextureResourceBridge(rex::system::IGraphicsSystem* graphics_system);

}  // namespace pinyon_shift::native_renderer
