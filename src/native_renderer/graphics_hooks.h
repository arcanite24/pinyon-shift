#pragma once

namespace rex::system {
class IGraphicsSystem;
}

namespace pinyon_shift::native_renderer {

void InstallGraphicsCensus(rex::system::IGraphicsSystem* graphics_system);
void UninstallGraphicsCensus(rex::system::IGraphicsSystem* graphics_system);

}  // namespace pinyon_shift::native_renderer
