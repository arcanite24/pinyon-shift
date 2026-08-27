#pragma once

namespace rex::system {
class IGraphicsSystem;
}

namespace pinyon_shift::native_renderer {

void InstallDrawCensus(rex::system::IGraphicsSystem* graphics_system);
void UninstallDrawCensus(rex::system::IGraphicsSystem* graphics_system);

}  // namespace pinyon_shift::native_renderer
