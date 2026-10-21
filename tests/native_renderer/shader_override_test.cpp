#include <rex/graphics/vulkan/shader_override_files.h>
#include <spirv-tools/libspirv.h>

#include <chrono>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>

using namespace rex::graphics::vulkan;
namespace fs = std::filesystem;

void Check(bool ok) {
  if (!ok)
    throw std::runtime_error("shader override check failed");
}

// Independently authored test shader; no translated guest payload.
std::vector<uint8_t> Module(bool red = false, bool vertex = false) {
  std::string text = R"(
OpCapability Shader
OpMemoryModel Logical GLSL450
OpEntryPoint Fragment %main "main" %color
OpExecutionMode %main OriginUpperLeft
OpDecorate %color Location 0
%void = OpTypeVoid
%float = OpTypeFloat 32
%vec4 = OpTypeVector %float 4
%ptr = OpTypePointer Output %vec4
%fn = OpTypeFunction %void
%zero = OpConstant %float 0
%one = OpConstant %float 1
%value = OpConstantComposite %vec4 %one %one %one %one
%color = OpVariable %ptr Output
%main = OpFunction %void None %fn
%label = OpLabel
OpStore %color %value
OpReturn
OpFunctionEnd
)";
  if (red)
    text.replace(text.find("%one %one %one %one"), 19, "%one %zero %zero %one");
  if (vertex) {
    text.replace(text.find("Fragment"), 8, "Vertex");
    const auto pos = text.find("OpExecutionMode");
    text.erase(pos, text.find('\n', pos) - pos);
  }
  auto context = spvContextCreate(SPV_ENV_VULKAN_1_2);
  spv_binary binary = nullptr;
  Check(spvTextToBinary(context, text.data(), text.size(), &binary, nullptr) ==
        SPV_SUCCESS);
  std::vector<uint8_t> bytes(binary->wordCount * 4);
  std::memcpy(bytes.data(), binary->code, bytes.size());
  spvBinaryDestroy(binary);
  spvContextDestroy(context);
  return bytes;
}

void Write(const fs::path &root, const std::string &name,
           const std::vector<uint8_t> &bytes) {
  fs::create_directories(root);
  std::ofstream file(root / name, std::ios::binary);
  Check(bool(
      file.write(reinterpret_cast<const char *>(bytes.data()), bytes.size())));
}

int main() {
  const auto root =
      fs::temp_directory_path() /
      ("pinyon-shader-test-" +
       std::to_string(
           std::chrono::steady_clock::now().time_since_epoch().count()));
  try {
    const auto a = root / "first", b = root / "second";
    const auto original = Module(), red = Module(true);
    const auto name = VulkanShaderOverrideFilename(1, 2, original);
    std::string source;
    std::vector<std::string> warnings;
    auto load = [&](const std::vector<fs::path> &roots,
                    const std::vector<uint8_t> &base) {
      return LoadVulkanShaderOverride(
          roots, 1, 2, base, source,
          [&](const auto &warning) { warnings.push_back(warning); });
    };
    Write(a, name, red);
    Write(b, name, original);
    Check(load({a, b}, original) == red &&
          source.find("first") != std::string::npos);
    Check(load({b, a}, original) == original &&
          source.find("second") != std::string::npos);
    Check(load({a, b}, red)
              .empty()); // Changed translation cannot select an old filename.
    Check(load({}, original)
              .empty()); // Disabled mods cannot supply replacements.
    Write(a, name, {});
    Check(load({a, b}, original) == original && !warnings.empty());
    auto corrupt = red;
    corrupt[20] = 0;
    corrupt[21] = 0;
    corrupt[22] = 0;
    corrupt[23] = 0;
    Write(a, name, corrupt); // Correct header, invalid instruction.
    Check(load({a}, original).empty());
    Write(a, name, Module(false, true));
    Check(load({a}, original).empty()); // Valid SPIR-V, wrong stage.
    Write(a, name, std::vector<uint8_t>(21, 0));
    Check(load({a}, original).empty());
    std::ofstream large(a / name, std::ios::binary | std::ios::trunc);
    large.seekp(16 * 1024 * 1024);
    large.put(0);
    large.close();
    Check(load({a}, original).empty());
    fs::remove_all(root);
    std::cout << "shader override identity, priority, validation and fallback "
                 "passed\n";
    return 0;
  } catch (const std::exception &error) {
    fs::remove_all(root);
    std::cerr << error.what() << '\n';
    return 1;
  }
}
