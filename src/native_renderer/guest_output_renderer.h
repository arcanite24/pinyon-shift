#pragma once

namespace rex::system {
class IGraphicsSystem;
}

namespace pinyon_shift::native_renderer {

void InstallGuestOutputRenderer(rex::system::IGraphicsSystem* graphics_system);
void UninstallGuestOutputRenderer(rex::system::IGraphicsSystem* graphics_system);

}  // namespace pinyon_shift::native_renderer
