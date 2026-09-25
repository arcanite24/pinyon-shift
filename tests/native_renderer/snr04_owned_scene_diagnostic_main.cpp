#include <exception>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <string_view>

#include "native_renderer/snr04_owned_scene_diagnostic.h"

namespace {
uint32_t run(const std::string& fixture, const std::string& shader,
             const std::string& output, uint32_t samples,
             const pinyon_shift::native_renderer::Snr04SegmentOptions* segment) {
  std::ifstream input(fixture, std::ios::binary);
  char magic[8]{};
  input.read(magic, sizeof(magic));
  if (!input) throw std::runtime_error("missing fixture");
  const auto kind = std::string_view(magic, 7);
  using namespace pinyon_shift::native_renderer;
  if (kind == "SNR02I3" || kind == "SNR03C1")
    return RunSnr04ProceduralDiagnostic(fixture, shader, output, nullptr,
                                       samples, segment);
  if (kind == "SNR02T3" || kind == "SNR02T4" || kind == "SNR02T5")
    return RunSnr04TrackDiagnostic(fixture, shader, output, nullptr,
                                   samples, segment);
  if (kind == "SNR03M1")
    return RunSnr04ManagerDiagnostic(fixture, shader, output, nullptr,
                                     samples, segment);
  if (kind == "SNR03R2" || kind == "SNR03R3" || kind == "SNR03R4")
    return RunSnr04RemainderDiagnostic(fixture, shader, output, nullptr,
                                       samples, segment);
  return RunSnr04OwnedSceneDiagnostic(std::filesystem::path(fixture), shader,
                                      output, nullptr,
                                      samples, segment);
}
}  // namespace

int main(int argc, char** argv) {
  if ((argc == 3 || argc == 4 || argc == 5) &&
      std::string_view(argv[1]) == "--batch") {
    try {
      const bool msaa4 = argc >= 4 && std::string_view(argv[3]) == "--msaa4";
      const bool live_shaders = argc == 5 &&
          std::string_view(argv[4]) == "--live-shaders";
      if ((argc >= 4 && !msaa4) || (argc == 5 && !live_shaders))
        throw std::runtime_error("invalid batch option");
      const auto result = pinyon_shift::native_renderer::RunSnr04BatchDiagnostic(
          argv[2], nullptr, msaa4 ? 4 : 1, !live_shaders);
      std::cout << "SNR04 shared target draws=" << result.draws
                << " covered_pixels=" << result.covered_pixels << '\n';
      return 0;
    } catch (const std::exception& error) {
      std::cerr << error.what() << '\n';
      return 1;
    }
  }
  const bool msaa4 = argc >= 5 && std::string_view(argv[4]) == "--msaa4";
  const bool alpha = argc == 13 && msaa4 &&
      std::string_view(argv[11]) == "--alpha-bc3";
  const bool segment =
      (argc == 10 && std::string_view(argv[4]) == "--segment") ||
      ((argc == 11 || alpha) && msaa4 &&
       std::string_view(argv[5]) == "--segment");
  if (argc != 4 && (argc != 5 || std::string_view(argv[4]) != "--msaa4") &&
      !segment) {
    std::cerr << "usage: snr04-owned-scene-diagnostic FIXTURE VS_DXBC OUTPUT_DIR [--msaa4] [--segment FIRST_SEQUENCE LAST_SEQUENCE FIRST_ID COUNT PRIOR_DIR_OR_DASH] [--alpha-bc3 BC3_MIPS]\n";
    return 1;
  }
  try {
    pinyon_shift::native_renderer::Snr04SegmentOptions options;
    if (segment) {
      const int first = msaa4 ? 6 : 5;
      options.first_sequence = std::stoull(argv[first]);
      options.last_sequence = std::stoull(argv[first + 1]);
      options.first_id = std::stoul(argv[first + 2]);
      options.draw_count = std::stoul(argv[first + 3]);
      if (std::string_view(argv[first + 4]) != "-")
        options.prior_output = argv[first + 4];
      if (alpha) options.alpha_bc3 = argv[12];
    }
    const auto* selected = segment ? &options : nullptr;
    std::ifstream input(argv[1], std::ios::binary);
    char magic[8]{};
    input.read(magic, sizeof(magic));
    if (alpha && std::string_view(magic, 7) != "SNR03F3" &&
        std::string_view(magic, 7) != "SNR03F4")
      throw std::runtime_error("alpha probe requires sequenced vegetation fixture");
    const auto covered = run(argv[1], argv[2], argv[3], msaa4 ? 4 : 1,
                             selected);
    std::cout << "SNR04 diagnostic covered_pixels=" << covered << '\n';
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
