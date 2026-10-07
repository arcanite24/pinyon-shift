#pragma once

#include <filesystem>
#include <cstdint>
#include <functional>
#include <memory>
#include <string_view>

namespace rex {
struct RuntimeConfig;
namespace system {
class IGraphicsSystem;
struct NativeGuestOutputRenderContext;
class XThread;
}  // namespace system
namespace ui {
class Window;
class WindowedAppContext;
}  // namespace ui
}  // namespace rex

namespace pinyon_shift::fh1_render_test {

// Loads the optional FH1-only scripted render test and replaces physical input
// with its deterministic controller stream. Invalid requests fail the process.
void Configure(rex::RuntimeConfig& config);
bool Enabled();
std::filesystem::path OutputDirectory();

// Called at the final guest-output boundary. Returns false because validation
// observes the real output and never claims or modifies it.
bool ObserveOutput(const rex::system::NativeGuestOutputRenderContext& context);

// Records FH1's active vehicle presentation transform for timing validation.
// This is consumed only by the deterministic render-test capture events.
void ObserveVehiclePose(float x, float y, float z);

// Records a guest movie (.wmv) open, for scripted waits on movie playback.
void ObserveMovieOpened(std::string_view guest_path);

// Records any guest file open (lower-case path), for scripted waits on the
// assets a screen loads; logged as events with fh1_render_test_log_file_opens.
void ObserveFileOpened(std::string_view guest_path);

// A verified native Rally finish was committed to the active profile.
// Scripted stage runs wait for this before pressing through the results UI.
void ObserveRallyStageSaved();
// Native world session mode (17 is free roam, 3 is an event).
void ObserveGameMode(uint32_t mode);

// Most recent scripted-route frame. Zero when no route is running. Host-side
// UI experiments use it to scope a mutation to one part of the route instead
// of guessing from a creation ordinal.
uint64_t CurrentFrame();

void Start(rex::system::IGraphicsSystem* graphics_system,
           rex::ui::WindowedAppContext* app_context, rex::ui::Window* window,
           std::function<void()> before_close = {});
void Stop();

}  // namespace pinyon_shift::fh1_render_test
