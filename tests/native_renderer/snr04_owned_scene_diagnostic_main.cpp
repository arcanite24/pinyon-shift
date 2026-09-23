#include <exception>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string_view>

#include "native_renderer/snr04_owned_scene_diagnostic.h"

int main(int argc, char** argv) {
  if (argc != 4 && (argc != 5 || std::string_view(argv[4]) != "--msaa4")) {
    std::cerr << "usage: snr04-owned-scene-diagnostic FIXTURE VS_DXBC OUTPUT_DIR [--msaa4]\n";
    return 1;
  }
  try {
    std::ifstream input(argv[1], std::ios::binary);
    char magic[8]{};
    input.read(magic, sizeof(magic));
    if (input && (std::string_view(magic, 7) == "SNR02I3" ||
                  std::string_view(magic, 7) == "SNR03C1")) {
      if (argc != 4) throw std::runtime_error("procedural diagnostic is 1x only");
      const auto covered = pinyon_shift::native_renderer::RunSnr04ProceduralDiagnostic(
          argv[1], argv[2], argv[3]);
      std::cout << "SNR04 " << (std::string_view(magic, 7) == "SNR03C1"
                                   ? "character" : "procedural")
                << " covered_pixels=" << covered << '\n';
      return 0;
    }
    if (input && (std::string_view(magic, 7) == "SNR02T3" ||
                  std::string_view(magic, 7) == "SNR02T4")) {
      if (argc != 4) throw std::runtime_error("track diagnostic is 1x only");
      const auto covered = pinyon_shift::native_renderer::RunSnr04TrackDiagnostic(
          argv[1], argv[2], argv[3]);
      std::cout << "SNR04 track covered_pixels=" << covered << '\n';
      return 0;
    }
    const auto covered = pinyon_shift::native_renderer::RunSnr04OwnedSceneDiagnostic(
        argv[1], argv[2], argv[3], nullptr, argc == 5 ? 4 : 1);
    std::cout << "SNR04 diagnostic covered_pixels=" << covered << '\n';
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
