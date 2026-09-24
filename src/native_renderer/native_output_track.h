#pragma once

namespace rex::system {
struct NativeGuestOutputRenderContext;
}
namespace pinyon_shift::native_renderer {
struct Snr04LiveScene;
bool DrawNativeOutputTrack(
    const rex::system::NativeGuestOutputRenderContext& context,
    const Snr04LiveScene& scene);
}
