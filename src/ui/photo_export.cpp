#include "ui/photo_export.h"

#include <atomic>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <thread>

#include <fmt/chrono.h>
#include <fmt/format.h>

#include <rex/logging.h>
#include <rex/filesystem.h>
#include <rex/ui/presenter.h>

#include "pinyon_shift_diagnostics.h"
#include "ui/png_writer.h"

namespace pinyon_shift::ui {
namespace {
std::atomic<bool> g_saving{false};
}  // namespace

void SavePhoto(rex::ui::Presenter* presenter) {
  if (!presenter || g_saving.exchange(true)) {
    return;  // one photo at a time; a held key must not queue a burst
  }
  std::thread([presenter] {
    rex::ui::RawImage image;
    if (!presenter->CaptureGuestOutput(image) || !image.width || !image.height) {
      REXLOG_WARN("Photo: no guest output to capture");
      g_saving = false;
      return;
    }
    const std::vector<uint8_t> png =
        EncodePng(image.data.data(), image.width, image.height, image.stride, 4);
    const auto now = std::chrono::system_clock::now();
    const auto directory = diagnostics::StateRoot() / "photos";
    std::error_code error;
    std::filesystem::create_directories(directory, error);
    const auto path = directory / fmt::format(
        "pinyon-shift-{:%Y%m%dT%H%M%S}Z-{:03}.png",
        std::chrono::floor<std::chrono::seconds>(now),
        std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch()).count() %
            1000);
    std::ofstream file(path, std::ios::binary);
    file.write(reinterpret_cast<const char*>(png.data()), std::streamsize(png.size()));
    const bool written = bool(file);
    file.close();
    if (written) {
      REXLOG_INFO("Photo saved: {} ({}x{}, {} KB)", rex::path_to_utf8(path), image.width, image.height,
                  png.size() >> 10);
      diagnostics::RecordEvent("photo.saved", {{"path", rex::path_to_utf8(path)},
                                               {"width", std::to_string(image.width)},
                                               {"height", std::to_string(image.height)},
                                               {"bytes", std::to_string(png.size())}});
    } else {
      REXLOG_ERROR("Photo: could not write {}", rex::path_to_utf8(path));
    }
    g_saving = false;
  }).detach();
}

void WaitForPhoto() {
  const auto give_up = std::chrono::steady_clock::now() + std::chrono::seconds(5);
  while (g_saving && std::chrono::steady_clock::now() < give_up) {
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
}

}  // namespace pinyon_shift::ui
