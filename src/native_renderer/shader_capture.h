#pragma once

namespace rex::system {
class IGraphicsSystem;
}

namespace pinyon_shift::native_renderer {

void InstallShaderCapture(rex::system::IGraphicsSystem *graphics_system);
void UninstallShaderCapture(rex::system::IGraphicsSystem *graphics_system);

} // namespace pinyon_shift::native_renderer
