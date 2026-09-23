// Diagnostic only: replay the SNR-03 owned fixture into private D3D12 targets.
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <bcrypt.h>
#include <d3d12.h>
#include <d3dcompiler.h>
#include <dxgi1_6.h>
#include <wrl/client.h>

#include <algorithm>
#include <array>
#include <bit>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <set>
#include <span>
#include <source_location>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

#include "native_renderer/snr04_owned_scene_diagnostic.h"

using Microsoft::WRL::ComPtr;

namespace {
constexpr uint32_t width = 1280, height = 720;
constexpr char expected_vs_sha[] =
    "2adfe080228c468ce9aec7e21d19798fc8aaa32cdba5d7325c4fac4070f21faa";

void check(HRESULT result,
           std::source_location location = std::source_location::current()) {
  if (FAILED(result))
    throw std::runtime_error("D3D12 error " + std::to_string(uint32_t(result)) +
                             " at line " + std::to_string(location.line()));
}
void require(bool value, const char* message) {
  if (!value) throw std::runtime_error(message);
}
std::vector<char> read(const std::filesystem::path& path) {
  std::ifstream file(path, std::ios::binary);
  require(bool(file), "missing input");
  return {std::istreambuf_iterator<char>(file), {}};
}
std::string sha256(std::span<const char> data) {
  BCRYPT_ALG_HANDLE algorithm = nullptr;
  require(BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0) >= 0,
          "SHA-256 provider unavailable");
  std::array<UCHAR, 32> digest{};
  auto status = BCryptHash(algorithm, nullptr, 0,
                           reinterpret_cast<PUCHAR>(const_cast<char*>(data.data())),
                           ULONG(data.size()), digest.data(), ULONG(digest.size()));
  BCryptCloseAlgorithmProvider(algorithm, 0);
  require(status >= 0, "SHA-256 failed");
  std::ostringstream hex;
  for (auto byte : digest) hex << std::hex << std::setfill('0') << std::setw(2) << int(byte);
  return hex.str();
}

struct Reader {
  std::span<const char> data;
  size_t position = 0;
  template <typename T> T take() {
    require(position <= data.size() && sizeof(T) <= data.size() - position,
            "truncated fixture");
    T result;
    std::memcpy(&result, data.data() + position, sizeof(T));
    position += sizeof(T);
    return result;
  }
  std::vector<char> bytes(size_t count) {
    require(position <= data.size() && count <= data.size() - position,
            "truncated vertex bytes");
    std::vector<char> result(data.data() + position, data.data() + position + count);
    position += count;
    return result;
  }
};
struct Item {
  struct Variant {
    uint64_t sequence = 0;
    std::array<uint32_t, 64> system{};
  };
  uint32_t packet = 0;
  uint32_t vertex_count = 0;
  std::array<uint32_t, 96> constants{};
  std::array<uint32_t, 3> pixel_registers{};
  std::array<uint32_t, 12> pixel_constants{};
  std::array<uint32_t, 64> system{};
  std::array<uint32_t, 64> original_system{};
  std::array<uint32_t, 4> fetch{};
  std::vector<Variant> variants;
  std::vector<char> vertices;
};
struct Scene {
  uint64_t source_frame = 0;
  bool sequenced = false;
  std::string fixture_sha256;
  std::vector<Item> items;
};
Scene load_scene(std::span<const char> file) {
  Reader reader{file};
  const auto magic = reader.take<std::array<char, 8>>();
  const bool sequenced = magic ==
      std::array<char, 8>{'S', 'N', 'R', '0', '3', 'F', '3', '\0'};
  const bool extended = sequenced || magic ==
      std::array<char, 8>{'S', 'N', 'R', '0', '3', 'F', '2', '\0'};
  require(extended || magic ==
              std::array<char, 8>{'S', 'N', 'R', '0', '3', 'F', '1', '\0'},
          "wrong fixture magic");
  Scene scene;
  scene.sequenced = sequenced;
  scene.fixture_sha256 = sha256(file);
  scene.source_frame = reader.take<uint64_t>();
  reader.take<uint32_t>();  // Title view.
  reader.take<uint32_t>();  // Title camera.
  const auto count = reader.take<uint32_t>();
  require(count > 0 && count <= 512, "invalid item count");
  reader.take<std::array<uint32_t, 32>>();  // Two title camera word arrays.
  scene.items.reserve(count);
  std::set<uint32_t> packets;
  std::set<uint64_t> sequences;
  for (uint32_t ordinal = 0; ordinal < count; ++ordinal) {
    auto metadata = reader.take<std::array<uint32_t, 5>>();
    Item item;
    item.packet = reader.take<uint32_t>();
    require(packets.insert(item.packet).second, "duplicate packet");
    reader.take<uint64_t>();  // Bucket entry.
    item.vertex_count = reader.take<uint32_t>();
    const auto byte_count = reader.take<uint32_t>();
    const auto constant_count = reader.take<uint32_t>();
    const auto variant_count = reader.take<uint32_t>();
    require(constant_count == 24 && variant_count > 0 && variant_count <= 4 &&
                item.vertex_count > 0 && item.vertex_count % 4 == 0 &&
                item.vertex_count * 4 == byte_count && byte_count <= 32768 &&
                (metadata[4] & 0x03FFFFFC) == byte_count,
            "unsupported owned geometry");
    item.constants = reader.take<std::array<uint32_t, 96>>();
    if (extended) {
      item.pixel_registers = reader.take<std::array<uint32_t, 3>>();
      item.pixel_constants = reader.take<std::array<uint32_t, 12>>();
      require(item.pixel_registers[0] < item.pixel_registers[1] &&
                  item.pixel_registers[1] < item.pixel_registers[2] &&
                  item.pixel_registers[2] < 256,
              "invalid pixel constant registers");
    }
    item.vertices = reader.bytes(byte_count);
    for (uint32_t variant = 0; variant < variant_count; ++variant) {
      reader.take<uint64_t>();  // Dynamic-state identity.
      const uint64_t sequence = sequenced ? reader.take<uint64_t>() : 0;
      require(!sequenced || (sequence && sequences.insert(sequence).second),
              "duplicate or missing draw sequence");
      std::array<uint32_t, 64> system{};
      if (extended) {
        system = reader.take<std::array<uint32_t, 64>>();
      } else {
        const auto old = reader.take<std::array<uint32_t, 40>>();
        std::copy(old.begin(), old.end(), system.begin());
      }
      auto fetch = reader.take<std::array<uint32_t, 4>>();
      require(!(system[0] & 1) && system[4] == 0 && system[5] == 0 &&
                  (fetch[2] & 0x1FFFFFFC) == (metadata[3] & 0x1FFFFFFC) &&
                  (fetch[3] & 0x03FFFFFC) == byte_count,
              "unsupported vertex fetch state");
      if (variant == 0) {
        item.system = system;
        item.fetch = fetch;
      } else {
        require(fetch == item.fetch, "fetch changes across variants");
        for (size_t word = 0; word < system.size(); ++word)
          require(system[word] == item.system[word] || word == 33 || word == 37 ||
                      (extended && word >= 42 && word <= 45),
                  "non-diagnostic variant change");
      }
      item.variants.push_back({sequence, system});
    }
    auto bits = [](uint32_t word) { return std::bit_cast<float>(word); };
    const float scale_y = bits(item.system[33]);
    const float offset_y = bits(item.system[37]);
    require(std::isfinite(scale_y) && scale_y > 0 && std::isfinite(offset_y) &&
                std::abs((offset_y + 1) / scale_y - 1 + 1.f / height) < 1e-6f &&
                bits(item.system[32]) == 1 && bits(item.system[34]) == -1 &&
                std::abs(bits(item.system[36]) - 1.f / width) < 1e-6f &&
                bits(item.system[38]) == 1,
            "viewport remap does not normalize to reference resolution");
    item.original_system = item.system;
    item.system[33] = std::bit_cast<uint32_t>(1.f);
    item.system[37] = std::bit_cast<uint32_t>(-1.f / height);
    for (auto& variant : item.variants) {
      const float variant_scale_y = bits(variant.system[33]);
      const float variant_offset_y = bits(variant.system[37]);
      require(std::isfinite(variant_scale_y) && variant_scale_y > 0 &&
                  std::isfinite(variant_offset_y) &&
                  std::abs((variant_offset_y + 1) / variant_scale_y - 1 +
                           1.f / height) < 1e-6f,
              "variant viewport remap does not normalize");
      variant.system[33] = std::bit_cast<uint32_t>(1.f);
      variant.system[37] = std::bit_cast<uint32_t>(-1.f / height);
    }
    item.fetch[2] &= 3;  // Rebase fetch 95 onto the private raw buffer.
    scene.items.push_back(std::move(item));
  }
  require(reader.position == file.size(), "trailing fixture bytes");
  return scene;
}

ComPtr<ID3D12Resource> buffer(ID3D12Device* device, uint64_t size,
                              D3D12_HEAP_TYPE heap, D3D12_RESOURCE_STATES state,
                              D3D12_RESOURCE_FLAGS flags = D3D12_RESOURCE_FLAG_NONE) {
  D3D12_HEAP_PROPERTIES properties{};
  properties.Type = heap;
  D3D12_RESOURCE_DESC description{};
  description.Dimension = D3D12_RESOURCE_DIMENSION_BUFFER;
  description.Width = size;
  description.Height = description.DepthOrArraySize = description.MipLevels = 1;
  description.SampleDesc.Count = 1;
  description.Layout = D3D12_TEXTURE_LAYOUT_ROW_MAJOR;
  description.Flags = flags;
  ComPtr<ID3D12Resource> resource;
  check(device->CreateCommittedResource(&properties, D3D12_HEAP_FLAG_NONE,
                                        &description, state, nullptr,
                                        IID_PPV_ARGS(&resource)));
  return resource;
}
ComPtr<ID3D12Resource> upload(ID3D12Device* device, const void* bytes, size_t size) {
  auto resource = buffer(device, (size + 255) & ~uint64_t(255),
                         D3D12_HEAP_TYPE_UPLOAD, D3D12_RESOURCE_STATE_GENERIC_READ);
  void* mapping = nullptr;
  D3D12_RANGE empty{};
  check(resource->Map(0, &empty, &mapping));
  std::memcpy(mapping, bytes, size);
  resource->Unmap(0, nullptr);
  return resource;
}
ComPtr<ID3D12Resource> texture(ID3D12Device* device, DXGI_FORMAT format,
                               D3D12_RESOURCE_FLAGS flags,
                               D3D12_RESOURCE_STATES initial,
                               const D3D12_CLEAR_VALUE& clear,
                               uint32_t samples = 1) {
  D3D12_HEAP_PROPERTIES properties{};
  properties.Type = D3D12_HEAP_TYPE_DEFAULT;
  D3D12_RESOURCE_DESC description{};
  description.Dimension = D3D12_RESOURCE_DIMENSION_TEXTURE2D;
  description.Width = width;
  description.Height = height;
  description.DepthOrArraySize = description.MipLevels = 1;
  description.Format = samples == 4 && format == DXGI_FORMAT_D32_FLOAT
                           ? DXGI_FORMAT_R32_TYPELESS : format;
  description.SampleDesc.Count = samples;
  description.Flags = flags;
  ComPtr<ID3D12Resource> resource;
  check(device->CreateCommittedResource(&properties, D3D12_HEAP_FLAG_NONE,
                                        &description, initial, &clear,
                                        IID_PPV_ARGS(&resource)));
  return resource;
}
void transition(ID3D12GraphicsCommandList* commands, ID3D12Resource* resource,
                D3D12_RESOURCE_STATES from, D3D12_RESOURCE_STATES to) {
  D3D12_RESOURCE_BARRIER barrier{};
  barrier.Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
  barrier.Transition = {resource, D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES, from, to};
  commands->ResourceBarrier(1, &barrier);
}
}  // namespace

uint32_t pinyon_shift::native_renderer::RunSnr04OwnedSceneDiagnostic(
    std::span<const char> fixture,
    const std::filesystem::path& vertex_shader,
    const std::filesystem::path& output_directory,
    ID3D12Device* borrowed_device, uint32_t samples) {
  require(samples == 1 || samples == 4, "unsupported sample count");
  const auto begin = std::chrono::steady_clock::now();
  auto scene = load_scene(fixture);
  auto vs = read(vertex_shader);
  require(vs.size() == 19328 && std::memcmp(vs.data(), "DXBC", 4) == 0 &&
              sha256(vs) == expected_vs_sha,
          "wrong vegetation vertex shader");
  const auto extracted = std::chrono::steady_clock::now();

  ComPtr<ID3D12Device> device;
  if (borrowed_device) {
    device = borrowed_device;
  } else {
    ComPtr<ID3D12Debug> debug;
    if (SUCCEEDED(D3D12GetDebugInterface(IID_PPV_ARGS(&debug))))
      debug->EnableDebugLayer();
    ComPtr<IDXGIFactory6> factory;
    check(CreateDXGIFactory2(0, IID_PPV_ARGS(&factory)));
    ComPtr<IDXGIAdapter1> adapter;
    check(factory->EnumAdapterByGpuPreference(0, DXGI_GPU_PREFERENCE_HIGH_PERFORMANCE,
                                             IID_PPV_ARGS(&adapter)));
    check(D3D12CreateDevice(adapter.Get(), D3D_FEATURE_LEVEL_11_0,
                            IID_PPV_ARGS(&device)));
  }
  constexpr char ps_source[] =
      "cbuffer Item : register(b2) { uint id; };"
      "float4 main() : SV_Target0 {"
      " return float4((id & 255) / 255.0, ((id >> 8) & 255) / 255.0, 0, 1); }";
  ComPtr<ID3DBlob> ps, errors;
  check(D3DCompile(ps_source, sizeof(ps_source) - 1, nullptr, nullptr, nullptr,
                   "main", "ps_5_1", 0, 0, &ps, &errors));
  D3D12_ROOT_PARAMETER parameters[6]{};
  for (uint32_t i = 0; i < 4; ++i) {
    parameters[i].ParameterType =
        i == 3 ? D3D12_ROOT_PARAMETER_TYPE_SRV : D3D12_ROOT_PARAMETER_TYPE_CBV;
    parameters[i].Descriptor.ShaderRegister = i == 2 ? 3 : i == 3 ? 0 : i;
    parameters[i].ShaderVisibility = D3D12_SHADER_VISIBILITY_VERTEX;
  }
  parameters[4].ParameterType = D3D12_ROOT_PARAMETER_TYPE_32BIT_CONSTANTS;
  parameters[4].Constants.ShaderRegister = 2;
  parameters[4].Constants.Num32BitValues = 1;
  parameters[4].ShaderVisibility = D3D12_SHADER_VISIBILITY_PIXEL;
  parameters[5].ParameterType = D3D12_ROOT_PARAMETER_TYPE_UAV;
  parameters[5].Descriptor.ShaderRegister = 0;
  parameters[5].ShaderVisibility = D3D12_SHADER_VISIBILITY_VERTEX;
  D3D12_ROOT_SIGNATURE_DESC root_description{
      6, parameters, 0, nullptr,
      D3D12_ROOT_SIGNATURE_FLAG_ALLOW_INPUT_ASSEMBLER_INPUT_LAYOUT |
          D3D12_ROOT_SIGNATURE_FLAG_ALLOW_STREAM_OUTPUT};
  ComPtr<ID3DBlob> root_blob;
  check(D3D12SerializeRootSignature(&root_description, D3D_ROOT_SIGNATURE_VERSION_1,
                                    &root_blob, &errors));
  ComPtr<ID3D12RootSignature> root;
  check(device->CreateRootSignature(0, root_blob->GetBufferPointer(),
                                    root_blob->GetBufferSize(), IID_PPV_ARGS(&root)));
  D3D12_GRAPHICS_PIPELINE_STATE_DESC pipeline_description{};
  pipeline_description.pRootSignature = root.Get();
  pipeline_description.VS = {vs.data(), vs.size()};
  pipeline_description.PS = {ps->GetBufferPointer(), ps->GetBufferSize()};
  pipeline_description.SampleMask = UINT_MAX;
  pipeline_description.RasterizerState.FillMode = D3D12_FILL_MODE_SOLID;
  pipeline_description.RasterizerState.CullMode = D3D12_CULL_MODE_NONE;
  pipeline_description.RasterizerState.DepthClipEnable = TRUE;
  pipeline_description.BlendState.RenderTarget[0].RenderTargetWriteMask =
      D3D12_COLOR_WRITE_ENABLE_ALL;
  pipeline_description.DepthStencilState.DepthEnable = TRUE;
  pipeline_description.DepthStencilState.DepthWriteMask = D3D12_DEPTH_WRITE_MASK_ALL;
  pipeline_description.DepthStencilState.DepthFunc = D3D12_COMPARISON_FUNC_GREATER_EQUAL;
  pipeline_description.PrimitiveTopologyType = D3D12_PRIMITIVE_TOPOLOGY_TYPE_TRIANGLE;
  pipeline_description.NumRenderTargets = 1;
  pipeline_description.RTVFormats[0] = DXGI_FORMAT_R8G8B8A8_UNORM;
  pipeline_description.DSVFormat = DXGI_FORMAT_D32_FLOAT;
  pipeline_description.SampleDesc.Count = samples;
  ComPtr<ID3D12PipelineState> pipeline;
  auto pipeline_result = device->CreateGraphicsPipelineState(
      &pipeline_description, IID_PPV_ARGS(&pipeline));
  if (FAILED(pipeline_result)) {
    ComPtr<ID3D12InfoQueue> messages;
    if (SUCCEEDED(device.As(&messages))) {
      for (UINT64 i = 0; i < messages->GetNumStoredMessages(); ++i) {
        SIZE_T size = 0;
        messages->GetMessage(i, nullptr, &size);
        std::vector<char> storage(size);
        auto* message = reinterpret_cast<D3D12_MESSAGE*>(storage.data());
        if (SUCCEEDED(messages->GetMessage(i, message, &size)))
          std::cerr << message->pDescription << '\n';
      }
    }
    check(pipeline_result);
  }
  D3D12_SO_DECLARATION_ENTRY position_declaration{0, "SV_Position", 0, 0, 4, 0};
  UINT position_stride = 16;
  auto stream_description = pipeline_description;
  stream_description.PS = {};
  stream_description.StreamOutput = {&position_declaration, 1, &position_stride, 1,
                                     D3D12_SO_NO_RASTERIZED_STREAM};
  stream_description.PrimitiveTopologyType = D3D12_PRIMITIVE_TOPOLOGY_TYPE_POINT;
  stream_description.NumRenderTargets = 0;
  stream_description.RTVFormats[0] = DXGI_FORMAT_UNKNOWN;
  stream_description.DSVFormat = DXGI_FORMAT_UNKNOWN;
  stream_description.DepthStencilState.DepthEnable = FALSE;
  stream_description.SampleDesc.Count = 1;
  ComPtr<ID3D12PipelineState> stream_pipeline;
  auto stream_result = device->CreateGraphicsPipelineState(
      &stream_description, IID_PPV_ARGS(&stream_pipeline));
  if (FAILED(stream_result)) {
    ComPtr<ID3D12InfoQueue> messages;
    if (SUCCEEDED(device.As(&messages))) {
      for (UINT64 i = 0; i < messages->GetNumStoredMessages(); ++i) {
        SIZE_T size = 0;
        messages->GetMessage(i, nullptr, &size);
        std::vector<char> storage(size);
        auto* message = reinterpret_cast<D3D12_MESSAGE*>(storage.data());
        if (SUCCEEDED(messages->GetMessage(i, message, &size)))
          std::cerr << message->pDescription << '\n';
      }
    }
    check(stream_result);
  }

  D3D12_CLEAR_VALUE color_clear{};
  color_clear.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
  D3D12_CLEAR_VALUE depth_clear{};
  depth_clear.Format = DXGI_FORMAT_D32_FLOAT;
  depth_clear.DepthStencil.Depth = 0;
  auto color = texture(device.Get(), color_clear.Format,
                       D3D12_RESOURCE_FLAG_ALLOW_RENDER_TARGET,
                       D3D12_RESOURCE_STATE_RENDER_TARGET, color_clear, samples);
  auto depth = texture(device.Get(), depth_clear.Format,
                       D3D12_RESOURCE_FLAG_ALLOW_DEPTH_STENCIL,
                       D3D12_RESOURCE_STATE_DEPTH_WRITE, depth_clear, samples);
  D3D12_DESCRIPTOR_HEAP_DESC rtv_description{};
  rtv_description.Type = D3D12_DESCRIPTOR_HEAP_TYPE_RTV;
  rtv_description.NumDescriptors = 1;
  ComPtr<ID3D12DescriptorHeap> rtv;
  check(device->CreateDescriptorHeap(&rtv_description, IID_PPV_ARGS(&rtv)));
  device->CreateRenderTargetView(color.Get(), nullptr, rtv->GetCPUDescriptorHandleForHeapStart());
  D3D12_DESCRIPTOR_HEAP_DESC dsv_description{};
  dsv_description.Type = D3D12_DESCRIPTOR_HEAP_TYPE_DSV;
  dsv_description.NumDescriptors = 1;
  ComPtr<ID3D12DescriptorHeap> dsv;
  check(device->CreateDescriptorHeap(&dsv_description, IID_PPV_ARGS(&dsv)));
  D3D12_DEPTH_STENCIL_VIEW_DESC depth_view{};
  depth_view.Format = DXGI_FORMAT_D32_FLOAT;
  depth_view.ViewDimension = samples == 4 ? D3D12_DSV_DIMENSION_TEXTURE2DMS
                                          : D3D12_DSV_DIMENSION_TEXTURE2D;
  device->CreateDepthStencilView(depth.Get(), &depth_view,
                                 dsv->GetCPUDescriptorHandleForHeapStart());

  auto max_vertices = std::max_element(scene.items.begin(), scene.items.end(),
                                       [](const Item& a, const Item& b) {
                                         return a.vertex_count < b.vertex_count;
                                       })->vertex_count;
  require(max_vertices <= UINT16_MAX, "index range exceeds 16 bits");
  std::vector<uint16_t> indices;
  indices.reserve(max_vertices / 4 * 6);
  for (uint32_t first = 0; first < max_vertices; first += 4)
    for (uint32_t corner : {0u, 1u, 3u, 1u, 2u, 3u})
      indices.push_back(uint16_t(first + corner));
  auto index_buffer = upload(device.Get(), indices.data(), indices.size() * sizeof(uint16_t));
  struct Resources {
    ComPtr<ID3D12Resource> vertices, b0_original, b1, b3;
    std::vector<ComPtr<ID3D12Resource>> b0_variants;
  };
  std::vector<Resources> owned;
  owned.reserve(scene.items.size());
  for (const auto& item : scene.items) {
    std::array<uint32_t, 120> original_system{};
    std::copy(item.original_system.begin(), item.original_system.end(),
              original_system.begin());
    std::array<uint32_t, 192> fetch{};
    std::copy(item.fetch.begin(), item.fetch.end(), fetch.begin() + 188);
    Resources resource{
        upload(device.Get(), item.vertices.data(), item.vertices.size()),
        upload(device.Get(), original_system.data(), sizeof(original_system)),
        upload(device.Get(), item.constants.data(), 23 * 16),
        upload(device.Get(), fetch.data(), sizeof(fetch)), {}};
    for (const auto& variant : item.variants) {
      std::array<uint32_t, 120> system{};
      std::copy(variant.system.begin(), variant.system.end(), system.begin());
      resource.b0_variants.push_back(upload(device.Get(), system.data(),
                                            sizeof(system)));
    }
    owned.push_back(std::move(resource));
  }
  const auto built = std::chrono::steady_clock::now();

  D3D12_PLACED_SUBRESOURCE_FOOTPRINT color_layout{}, depth_layout{};
  uint64_t color_bytes = 0, depth_bytes = 0;
  ComPtr<ID3D12Resource> color_readback, depth_readback;
  ComPtr<ID3D12Resource> sample_output, sample_readback;
  ComPtr<ID3D12DescriptorHeap> sample_heap;
  ComPtr<ID3D12RootSignature> sample_root;
  ComPtr<ID3D12PipelineState> sample_pipeline;
  if (samples == 1) {
    auto color_description = color->GetDesc(), depth_description = depth->GetDesc();
    device->GetCopyableFootprints(&color_description, 0, 1, 0, &color_layout,
                                  nullptr, nullptr, &color_bytes);
    device->GetCopyableFootprints(&depth_description, 0, 1, 0, &depth_layout,
                                  nullptr, nullptr, &depth_bytes);
    color_readback = buffer(device.Get(), color_bytes, D3D12_HEAP_TYPE_READBACK,
                            D3D12_RESOURCE_STATE_COPY_DEST);
    depth_readback = buffer(device.Get(), depth_bytes, D3D12_HEAP_TYPE_READBACK,
                            D3D12_RESOURCE_STATE_COPY_DEST);
  } else {
    constexpr char sample_source[] =
        "Texture2DMS<float4> colors : register(t0);"
        "Texture2DMS<float> depths : register(t1);"
        "RWStructuredBuffer<uint2> result : register(u0);"
        "[numthreads(8,8,1)] void main(uint3 p : SV_DispatchThreadID) {"
        " if (p.x >= 1280 || p.y >= 720) return;"
        " [unroll] for (uint s = 0; s < 4; ++s) {"
        "  float4 c = colors.Load(p.xy, s);"
        "  uint id = (uint)round(c.r * 255.0) | ((uint)round(c.g * 255.0) << 8);"
        "  result[(p.y * 1280 + p.x) * 4 + s] = uint2(id, asuint(depths.Load(p.xy, s)));"
        " } }";
    ComPtr<ID3DBlob> shader;
    check(D3DCompile(sample_source, sizeof(sample_source) - 1, nullptr,
                     nullptr, nullptr, "main", "cs_5_1", 0, 0, &shader,
                     &errors));
    D3D12_DESCRIPTOR_RANGE range{};
    range.RangeType = D3D12_DESCRIPTOR_RANGE_TYPE_SRV;
    range.NumDescriptors = 2;
    D3D12_ROOT_PARAMETER roots[2]{};
    roots[0].ParameterType = D3D12_ROOT_PARAMETER_TYPE_DESCRIPTOR_TABLE;
    roots[0].DescriptorTable = {1, &range};
    roots[1].ParameterType = D3D12_ROOT_PARAMETER_TYPE_UAV;
    D3D12_ROOT_SIGNATURE_DESC root_desc{2, roots};
    ComPtr<ID3DBlob> serialized;
    check(D3D12SerializeRootSignature(&root_desc, D3D_ROOT_SIGNATURE_VERSION_1,
                                      &serialized, &errors));
    check(device->CreateRootSignature(0, serialized->GetBufferPointer(),
                                      serialized->GetBufferSize(),
                                      IID_PPV_ARGS(&sample_root)));
    D3D12_COMPUTE_PIPELINE_STATE_DESC compute_desc{};
    compute_desc.pRootSignature = sample_root.Get();
    compute_desc.CS = {shader->GetBufferPointer(), shader->GetBufferSize()};
    check(device->CreateComputePipelineState(&compute_desc,
                                              IID_PPV_ARGS(&sample_pipeline)));
    D3D12_DESCRIPTOR_HEAP_DESC heap_desc{};
    heap_desc.Type = D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV;
    heap_desc.NumDescriptors = 2;
    heap_desc.Flags = D3D12_DESCRIPTOR_HEAP_FLAG_SHADER_VISIBLE;
    check(device->CreateDescriptorHeap(&heap_desc, IID_PPV_ARGS(&sample_heap)));
    auto handle = sample_heap->GetCPUDescriptorHandleForHeapStart();
    D3D12_SHADER_RESOURCE_VIEW_DESC view{};
    view.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
    view.ViewDimension = D3D12_SRV_DIMENSION_TEXTURE2DMS;
    view.Shader4ComponentMapping = D3D12_DEFAULT_SHADER_4_COMPONENT_MAPPING;
    device->CreateShaderResourceView(color.Get(), &view, handle);
    handle.ptr += device->GetDescriptorHandleIncrementSize(
        D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV);
    view.Format = DXGI_FORMAT_R32_FLOAT;
    device->CreateShaderResourceView(depth.Get(), &view, handle);
    constexpr uint64_t sample_bytes = uint64_t(width) * height * 4 * 8;
    sample_output = buffer(device.Get(), sample_bytes, D3D12_HEAP_TYPE_DEFAULT,
                           D3D12_RESOURCE_STATE_UNORDERED_ACCESS,
                           D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS);
    sample_readback = buffer(device.Get(), sample_bytes, D3D12_HEAP_TYPE_READBACK,
                             D3D12_RESOURCE_STATE_COPY_DEST);
  }
  std::vector<uint64_t> position_offsets;
  uint64_t position_allocation = 0, position_bytes = 0;
  for (const auto& item : scene.items) {
    position_offsets.push_back(position_allocation);
    const auto bytes = uint64_t(item.vertex_count) * 16;
    position_allocation += bytes + 8;
    position_bytes += bytes;
  }
  auto position_output = buffer(device.Get(), position_allocation,
                                D3D12_HEAP_TYPE_DEFAULT, D3D12_RESOURCE_STATE_COPY_DEST);
  auto position_readback = buffer(device.Get(), position_allocation,
                                  D3D12_HEAP_TYPE_READBACK, D3D12_RESOURCE_STATE_COPY_DEST);
  const std::vector<char> zero_positions(position_allocation);
  auto position_zero = upload(device.Get(), zero_positions.data(), zero_positions.size());
  ComPtr<ID3D12CommandQueue> queue;
  D3D12_COMMAND_QUEUE_DESC queue_description{};
  check(device->CreateCommandQueue(&queue_description, IID_PPV_ARGS(&queue)));
  ComPtr<ID3D12CommandAllocator> allocator;
  check(device->CreateCommandAllocator(D3D12_COMMAND_LIST_TYPE_DIRECT,
                                       IID_PPV_ARGS(&allocator)));
  ComPtr<ID3D12GraphicsCommandList> commands;
  check(device->CreateCommandList(0, D3D12_COMMAND_LIST_TYPE_DIRECT,
                                  allocator.Get(), pipeline.Get(),
                                  IID_PPV_ARGS(&commands)));
  auto rtv_handle = rtv->GetCPUDescriptorHandleForHeapStart();
  auto dsv_handle = dsv->GetCPUDescriptorHandleForHeapStart();
  constexpr float clear_color[4]{};
  commands->ClearRenderTargetView(rtv_handle, clear_color, 0, nullptr);
  commands->ClearDepthStencilView(dsv_handle, D3D12_CLEAR_FLAG_DEPTH, 0, 0, 0, nullptr);
  commands->OMSetRenderTargets(1, &rtv_handle, FALSE, &dsv_handle);
  D3D12_VIEWPORT viewport{0, 0, float(width), float(height), 0, 0.5f};
  D3D12_RECT scissor{0, 0, LONG(width), LONG(height)};
  commands->RSSetViewports(1, &viewport);
  commands->RSSetScissorRects(1, &scissor);
  commands->SetGraphicsRootSignature(root.Get());
  commands->SetPipelineState(pipeline.Get());
  commands->IASetPrimitiveTopology(D3D_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
  D3D12_INDEX_BUFFER_VIEW index_view{index_buffer->GetGPUVirtualAddress(),
                                     UINT(indices.size() * sizeof(uint16_t)),
                                     DXGI_FORMAT_R16_UINT};
  commands->IASetIndexBuffer(&index_view);
  struct DrawRef { uint64_t sequence; size_t item, variant; };
  std::vector<DrawRef> draws;
  for (size_t ordinal = 0; ordinal < scene.items.size(); ++ordinal) {
    const auto& item = scene.items[ordinal];
    const size_t count = scene.sequenced ? item.variants.size() : 1;
    for (size_t variant = 0; variant < count; ++variant)
      draws.push_back({item.variants[variant].sequence, ordinal, variant});
  }
  if (scene.sequenced)
    std::sort(draws.begin(), draws.end(),
              [](const DrawRef& a, const DrawRef& b) {
                return a.sequence < b.sequence;
              });
  for (const auto& draw : draws) {
    const auto& item = scene.items[draw.item];
    const auto& resource = owned[draw.item];
    commands->SetGraphicsRootConstantBufferView(
        0, resource.b0_variants[draw.variant]->GetGPUVirtualAddress());
    commands->SetGraphicsRootConstantBufferView(1, resource.b1->GetGPUVirtualAddress());
    commands->SetGraphicsRootConstantBufferView(2, resource.b3->GetGPUVirtualAddress());
    commands->SetGraphicsRootShaderResourceView(3, resource.vertices->GetGPUVirtualAddress());
    commands->SetGraphicsRoot32BitConstant(4, UINT(draw.item + 1), 0);
    commands->DrawIndexedInstanced(item.vertex_count / 4 * 6, 1, 0, 0, 0);
  }
  commands->CopyBufferRegion(position_output.Get(), 0, position_zero.Get(), 0,
                             position_allocation);
  transition(commands.Get(), position_output.Get(), D3D12_RESOURCE_STATE_COPY_DEST,
             D3D12_RESOURCE_STATE_STREAM_OUT);
  commands->SetPipelineState(stream_pipeline.Get());
  commands->IASetPrimitiveTopology(D3D_PRIMITIVE_TOPOLOGY_POINTLIST);
  for (size_t ordinal = 0; ordinal < scene.items.size(); ++ordinal) {
    const auto& resource = owned[ordinal];
    const auto bytes = uint64_t(scene.items[ordinal].vertex_count) * 16;
    const auto address = position_output->GetGPUVirtualAddress() + position_offsets[ordinal];
    commands->SetGraphicsRootConstantBufferView(0, resource.b0_original->GetGPUVirtualAddress());
    commands->SetGraphicsRootConstantBufferView(1, resource.b1->GetGPUVirtualAddress());
    commands->SetGraphicsRootConstantBufferView(2, resource.b3->GetGPUVirtualAddress());
    commands->SetGraphicsRootShaderResourceView(3, resource.vertices->GetGPUVirtualAddress());
    D3D12_STREAM_OUTPUT_BUFFER_VIEW position_view{address, bytes, address + bytes};
    commands->SOSetTargets(0, 1, &position_view);
    commands->DrawInstanced(scene.items[ordinal].vertex_count, 1, 0, 0);
  }
  transition(commands.Get(), position_output.Get(), D3D12_RESOURCE_STATE_STREAM_OUT,
             D3D12_RESOURCE_STATE_COPY_SOURCE);
  commands->CopyResource(position_readback.Get(), position_output.Get());
  if (samples == 1) {
    transition(commands.Get(), color.Get(), D3D12_RESOURCE_STATE_RENDER_TARGET,
               D3D12_RESOURCE_STATE_COPY_SOURCE);
    transition(commands.Get(), depth.Get(), D3D12_RESOURCE_STATE_DEPTH_WRITE,
               D3D12_RESOURCE_STATE_COPY_SOURCE);
    D3D12_TEXTURE_COPY_LOCATION source{}, destination{};
    source.Type = D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;
    destination.Type = D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;
    source.pResource = color.Get();
    destination.pResource = color_readback.Get();
    destination.PlacedFootprint = color_layout;
    commands->CopyTextureRegion(&destination, 0, 0, 0, &source, nullptr);
    source.pResource = depth.Get();
    destination.pResource = depth_readback.Get();
    destination.PlacedFootprint = depth_layout;
    commands->CopyTextureRegion(&destination, 0, 0, 0, &source, nullptr);
  } else {
    transition(commands.Get(), color.Get(), D3D12_RESOURCE_STATE_RENDER_TARGET,
               D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE);
    transition(commands.Get(), depth.Get(), D3D12_RESOURCE_STATE_DEPTH_WRITE,
               D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE);
    ID3D12DescriptorHeap* heaps[]{sample_heap.Get()};
    commands->SetDescriptorHeaps(1, heaps);
    commands->SetComputeRootSignature(sample_root.Get());
    commands->SetPipelineState(sample_pipeline.Get());
    commands->SetComputeRootDescriptorTable(
        0, sample_heap->GetGPUDescriptorHandleForHeapStart());
    commands->SetComputeRootUnorderedAccessView(
        1, sample_output->GetGPUVirtualAddress());
    commands->Dispatch((width + 7) / 8, (height + 7) / 8, 1);
    transition(commands.Get(), sample_output.Get(),
               D3D12_RESOURCE_STATE_UNORDERED_ACCESS,
               D3D12_RESOURCE_STATE_COPY_SOURCE);
    commands->CopyResource(sample_readback.Get(), sample_output.Get());
  }
  const auto close_result = commands->Close();
  if (FAILED(close_result)) {
    ComPtr<ID3D12InfoQueue> messages;
    if (SUCCEEDED(device.As(&messages))) {
      for (UINT64 i = 0; i < messages->GetNumStoredMessages(); ++i) {
        SIZE_T size = 0;
        messages->GetMessage(i, nullptr, &size);
        std::vector<char> storage(size);
        auto* message = reinterpret_cast<D3D12_MESSAGE*>(storage.data());
        if (SUCCEEDED(messages->GetMessage(i, message, &size)))
          std::cerr << message->pDescription << '\n';
      }
    }
  }
  check(close_result);
  ID3D12CommandList* lists[]{commands.Get()};
  queue->ExecuteCommandLists(1, lists);
  ComPtr<ID3D12Fence> fence;
  check(device->CreateFence(0, D3D12_FENCE_FLAG_NONE, IID_PPV_ARGS(&fence)));
  check(queue->Signal(fence.Get(), 1));
  HANDLE event = CreateEvent(nullptr, FALSE, FALSE, nullptr);
  require(event != nullptr, "CreateEvent failed");
  auto wait_result = fence->SetEventOnCompletion(1, event);
  auto waited = SUCCEEDED(wait_result) ? WaitForSingleObject(event, 30000) : WAIT_FAILED;
  CloseHandle(event);
  check(wait_result);
  require(waited == WAIT_OBJECT_0, "GPU wait failed");
  check(device->GetDeviceRemovedReason());
  ComPtr<ID3D12InfoQueue> messages;
  if (SUCCEEDED(device.As(&messages))) {
    for (UINT64 i = 0; i < messages->GetNumStoredMessages(); ++i) {
      SIZE_T size = 0;
      check(messages->GetMessage(i, nullptr, &size));
      std::vector<char> storage(size);
      auto* message = reinterpret_cast<D3D12_MESSAGE*>(storage.data());
      check(messages->GetMessage(i, message, &size));
      require(message->Severity > D3D12_MESSAGE_SEVERITY_ERROR,
              message->pDescription);
    }
  }
  const auto drawn = std::chrono::steady_clock::now();

  std::filesystem::create_directories(output_directory);
  const auto& directory = output_directory;
  std::ofstream image(directory / "identity.ppm", std::ios::binary);
  image << "P6\n" << width << ' ' << height << "\n255\n";
  std::ofstream depth_file(directory / "depth.f32", std::ios::binary);
  std::ofstream positions_file(directory / "postvs.f32x4", std::ios::binary);
  void* positions = nullptr;
  D3D12_RANGE position_range{0, SIZE_T(position_allocation)};
  check(position_readback->Map(0, &position_range, &positions));
  for (size_t ordinal = 0; ordinal < scene.items.size(); ++ordinal) {
    const auto bytes = uint64_t(scene.items[ordinal].vertex_count) * 16;
    const auto* segment = static_cast<const char*>(positions) + position_offsets[ordinal];
    uint64_t positions_written = 0;
    std::memcpy(&positions_written, segment + bytes, 8);
    require(positions_written == bytes, "incomplete post-VS stream output");
    positions_file.write(segment, bytes);
  }
  position_readback->Unmap(0, nullptr);
  positions_file.close();
  require(bool(positions_file), "post-VS output write failed");
  uint32_t covered = 0;
  uint32_t covered_any = 0, covered_samples = 0;
  std::vector<uint32_t> item_pixels(scene.items.size());
  D3D12_RANGE empty{};
  if (samples == 1) {
    void *colors = nullptr, *depths = nullptr;
    D3D12_RANGE color_range{0, SIZE_T(color_bytes)}, depth_range{0, SIZE_T(depth_bytes)};
    check(color_readback->Map(0, &color_range, &colors));
    check(depth_readback->Map(0, &depth_range, &depths));
    for (uint32_t y = 0; y < height; ++y) {
      auto* color_row = static_cast<const uint8_t*>(colors) + y * color_layout.Footprint.RowPitch;
      auto* depth_row = reinterpret_cast<const float*>(
          static_cast<const uint8_t*>(depths) + y * depth_layout.Footprint.RowPitch);
      for (uint32_t x = 0; x < width; ++x) {
        const auto* pixel = color_row + x * 4;
        image.write(reinterpret_cast<const char*>(pixel), 3);
        const auto id = uint32_t(pixel[0]) | (uint32_t(pixel[1]) << 8);
        if (id) {
          require(id <= scene.items.size() && std::isfinite(depth_row[x]) &&
                      depth_row[x] > 0 && depth_row[x] <= 1,
                  "invalid covered pixel/depth");
          ++covered;
          ++item_pixels[id - 1];
        }
      }
      depth_file.write(reinterpret_cast<const char*>(depth_row), width * sizeof(float));
    }
    color_readback->Unmap(0, &empty);
    depth_readback->Unmap(0, &empty);
    covered_any = covered_samples = covered;
  } else {
    constexpr size_t sample_bytes = size_t(width) * height * 4 * 8;
    D3D12_RANGE range{0, sample_bytes};
    void* mapped = nullptr;
    check(sample_readback->Map(0, &range, &mapped));
    const auto* words = static_cast<const uint32_t*>(mapped);
    std::ofstream mask_file(directory / "coverage.u8", std::ios::binary);
    std::ofstream sample_depths(directory / "depth.f32x4", std::ios::binary);
    std::ofstream sample_ids(directory / "identity.u16x4", std::ios::binary);
    for (size_t pixel = 0; pixel < size_t(width) * height; ++pixel) {
      uint8_t mask = 0;
      for (uint32_t sample = 0; sample < 4; ++sample) {
        const auto id = words[(pixel * 4 + sample) * 2];
        const float value = std::bit_cast<float>(words[(pixel * 4 + sample) * 2 + 1]);
        require(id <= scene.items.size() && std::isfinite(value) &&
                    value >= 0 && value <= 1 && (!id || value > 0),
                "invalid four-sample identity/depth");
        if (id) {
          mask |= uint8_t(1u << sample);
          ++covered_samples;
        }
        const auto short_id = uint16_t(id);
        sample_ids.write(reinterpret_cast<const char*>(&short_id), sizeof(short_id));
        sample_depths.write(reinterpret_cast<const char*>(&value), sizeof(value));
        if (sample == 0) {
          const char rgb[3]{char(id & 255), char((id >> 8) & 255), 0};
          image.write(rgb, sizeof(rgb));
          depth_file.write(reinterpret_cast<const char*>(&value), sizeof(value));
          if (id) {
            ++covered;
            ++item_pixels[id - 1];
          }
        }
      }
      mask_file.write(reinterpret_cast<const char*>(&mask), sizeof(mask));
      covered_any += mask != 0;
    }
    sample_readback->Unmap(0, &empty);
    mask_file.close();
    sample_depths.close();
    sample_ids.close();
    require(bool(mask_file) && bool(sample_depths) && bool(sample_ids),
            "four-sample output write failed");
  }
  image.close();
  depth_file.close();
  require(bool(image) && bool(depth_file), "diagnostic output write failed");
  const auto complete = std::chrono::steady_clock::now();
  auto us = [](auto from, auto to) {
    return std::chrono::duration_cast<std::chrono::microseconds>(to - from).count();
  };
  std::ofstream summary(directory / "summary.json");
  summary << "{\"schema\":\"pinyon-shift.snr04-owned-diagnostic.v1\","
          << "\"label\":\"private unmasked geometry diagnostic, not compatibility or FPS\","
          << "\"source_frame\":" << scene.source_frame << ','
          << "\"fixture_sha256\":\"" << scene.fixture_sha256 << "\","
          << "\"vs_sha256\":\"" << expected_vs_sha << "\","
          << "\"depth_test\":\"greater_equal\","
          << "\"depth_viewport\":[0,0.5],"
          << "\"width\":" << width << ",\"height\":" << height << ','
          << "\"samples\":" << samples << ','
          << "\"items\":" << scene.items.size() << ','
          << "\"raster_draws\":" << draws.size() << ','
          << "\"covered_pixels\":" << covered << ','
          << "\"covered_any_pixels\":" << covered_any << ','
          << "\"covered_samples\":" << covered_samples << ','
          << "\"visible_items\":"
          << std::count_if(item_pixels.begin(), item_pixels.end(),
                           [](uint32_t value) { return value != 0; }) << ','
          << "\"postvs_bytes\":" << position_bytes << ','
          << "\"extract_us\":" << us(begin, extracted) << ','
          << "\"build_us\":" << us(extracted, built) << ','
          << "\"draw_readback_us\":" << us(built, drawn) << ','
          << "\"write_us\":" << us(drawn, complete) << ','
          << "\"item_pixels\":[";
  for (size_t ordinal = 0; ordinal < scene.items.size(); ++ordinal) {
    if (ordinal) summary << ',';
    summary << "{\"packet\":" << scene.items[ordinal].packet
            << ",\"pixels\":" << item_pixels[ordinal] << '}';
  }
  summary << "]}\n";
  summary.close();
  require(bool(summary) && covered > 0, "empty or unwritable diagnostic");
  return covered;
}

uint32_t pinyon_shift::native_renderer::RunSnr04OwnedSceneDiagnostic(
    const std::filesystem::path& fixture,
    const std::filesystem::path& vertex_shader,
    const std::filesystem::path& output_directory,
    ID3D12Device* device, uint32_t samples) {
  const auto bytes = read(fixture);
  return RunSnr04OwnedSceneDiagnostic(bytes, vertex_shader,
                                     output_directory, device, samples);
}

namespace {
struct ProceduralDraw {
  uint64_t sequence = 0;
  uint64_t vertex_shader = 0;
  uint32_t vertex_count = 0;
  std::array<uint32_t, 64> system{};
  std::array<float, 6> viewport{};
  std::array<int32_t, 4> scissor{};
};
struct ProceduralItem {
  uint32_t packet = 0;
  std::vector<char> vertices;
  std::array<uint32_t, 4> fetch{};
  std::vector<uint32_t> constants;
  std::vector<ProceduralDraw> draws;
};
struct ProceduralScene {
  uint64_t frame = 0;
  std::string sha;
  std::vector<ProceduralItem> items;
};
ProceduralScene load_character(std::span<const char> bytes) {
  Reader reader{bytes};
  require(reader.take<std::array<char, 8>>() ==
              (std::array<char, 8>{'S','N','R','0','3','C','1','\0'}),
          "wrong character fixture");
  ProceduralScene scene;
  scene.sha = sha256(bytes);
  scene.frame = reader.take<uint64_t>();
  reader.take<uint32_t>();  // View.
  reader.take<uint32_t>();  // Camera.
  const auto count = reader.take<uint32_t>();
  const auto draw_count = reader.take<uint32_t>();
  require(count > 0 && count <= 64 && draw_count >= count && draw_count <= 128,
          "invalid character counts");
  reader.take<std::array<uint32_t, 32>>();  // Two camera matrices.
  std::set<uint32_t> packets;
  std::set<uint64_t> sequences;
  size_t owned_bytes = 0;
  for (uint32_t ordinal = 0; ordinal < count; ++ordinal) {
    reader.take<uint32_t>();  // Title record.
    reader.take<uint32_t>();  // Vertex descriptor.
    const auto base = reader.take<uint32_t>();
    const auto size = reader.take<uint32_t>();
    ProceduralItem item;
    item.packet = reader.take<uint32_t>();
    reader.take<uint64_t>();  // Bucket entry.
    const auto length = reader.take<uint32_t>();
    const auto variants = reader.take<uint32_t>();
    require(packets.insert(item.packet).second && length > 0 &&
                length <= 32768 && length == (size & 0x03FFFFFC) &&
                length <= 512 * 1024 - owned_bytes &&
                variants > 0 && variants <= 8,
            "unsupported character geometry bound");
    owned_bytes += length;
    item.vertices = reader.bytes(length);
    for (uint32_t variant = 0; variant < variants; ++variant) {
      ProceduralDraw draw;
      draw.sequence = reader.take<uint64_t>();
      draw.vertex_shader = reader.take<uint64_t>();
      const auto pixel_shader = reader.take<uint64_t>();
      const auto specialization = reader.take<uint64_t>();
      reader.take<uint64_t>();  // Dynamic state.
      draw.vertex_count = reader.take<uint32_t>();
      const auto words = reader.take<uint32_t>();
      const auto bitmap = reader.take<std::array<uint64_t, 4>>();
      require(words <= 1024 &&
                  words == 4 * (std::popcount(bitmap[0]) +
                                std::popcount(bitmap[1]) +
                                std::popcount(bitmap[2]) +
                                std::popcount(bitmap[3])),
              "invalid character packed constants");
      std::vector<uint32_t> packed;
      packed.reserve(words);
      for (uint32_t word = 0; word < words; ++word)
        packed.push_back(reader.take<uint32_t>());
      draw.system = reader.take<std::array<uint32_t, 64>>();
      const auto fetch = reader.take<std::array<uint32_t, 4>>();
      const auto raster_mode = reader.take<uint32_t>();
      const auto clip_control = reader.take<uint32_t>();
      const auto depth_control = reader.take<uint32_t>();
      draw.viewport = reader.take<std::array<float, 6>>();
      draw.scissor = reader.take<std::array<int32_t, 4>>();
      const float tile_offset = float(height) - draw.viewport[3];
      require(draw.sequence && sequences.insert(draw.sequence).second &&
                  draw.vertex_shader == 0xAC345DADF2F24AE4ull &&
                  pixel_shader == 0xB77EC20EA53C20F8ull &&
                  specialization == 15 &&
                  draw.vertex_count > 0 && draw.vertex_count % 4 == 0 &&
                  draw.vertex_count <= UINT16_MAX &&
                  length == draw.vertex_count * 4 &&
                  (fetch[2] & 0x1FFFFFFC) == (base & 0x1FFFFFFC) &&
                  (fetch[3] & 0x03FFFFFC) == length && (fetch[2] & 3) == 3 &&
                  raster_mode == 0x218002 && clip_control == 0x80000 &&
                  depth_control == 0x87087E7 &&
                  draw.viewport[0] == 0 && draw.viewport[1] == 0 &&
                  draw.viewport[2] == width && tile_offset >= 0 &&
                  tile_offset == std::floor(tile_offset) &&
                  draw.scissor[0] == 0 && draw.scissor[1] == 0 &&
                  draw.scissor[2] == int32_t(width) &&
                  draw.scissor[3] > 0 &&
                  draw.scissor[3] <= draw.viewport[3] &&
                  tile_offset + draw.scissor[3] <= height,
              "unsupported character draw state");
      if (variant == 0) {
        item.constants = std::move(packed);
        item.fetch = fetch;
      } else {
        require(packed == item.constants && fetch == item.fetch,
                "character vertex input changes between draws");
      }
      item.draws.push_back(draw);
    }
    item.fetch[2] &= 3;
    scene.items.push_back(std::move(item));
  }
  require(reader.position == bytes.size() && sequences.size() == draw_count,
          "trailing character fixture or missing draw");
  return scene;
}
ProceduralScene load_procedural(std::span<const char> bytes) {
  Reader reader{bytes};
  require(reader.take<std::array<char, 8>>() ==
              (std::array<char, 8>{'S','N','R','0','2','I','3','\0'}),
          "wrong procedural fixture");
  ProceduralScene scene;
  scene.sha = sha256(bytes);
  scene.frame = reader.take<uint64_t>();
  const auto count = reader.take<uint32_t>();
  require(count > 0 && count <= 512, "invalid procedural item count");
  reader.take<std::array<uint32_t, 32>>();
  std::set<uint32_t> packets;
  std::set<uint64_t> sequences;
  size_t owned_bytes = 0;
  for (uint32_t ordinal = 0; ordinal < count; ++ordinal) {
    reader.take<uint64_t>();  // Title call.
    ProceduralItem item;
    item.packet = reader.take<uint32_t>();
    require(packets.insert(item.packet).second, "duplicate procedural packet");
    reader.take<uint32_t>();  // Raw title kind.
    reader.take<std::array<uint32_t, 23>>();
    reader.take<std::array<uint32_t, 17>>();
    const auto base = reader.take<uint32_t>();
    const auto length = reader.take<uint32_t>();
    const auto variants = reader.take<uint32_t>();
    require(length > 0 && length <= 256 * 1024 &&
                length <= 2 * 1024 * 1024 - owned_bytes &&
                variants > 0 && variants <= 8,
            "unsupported procedural geometry bound");
    owned_bytes += length;
    item.vertices = reader.bytes(length);
    for (uint32_t variant = 0; variant < variants; ++variant) {
      ProceduralDraw draw;
      draw.sequence = reader.take<uint64_t>();
      draw.vertex_shader = reader.take<uint64_t>();
      reader.take<uint64_t>();  // Pixel shader; identity diagnostic replaces it.
      reader.take<uint64_t>();  // Dynamic state.
      draw.vertex_count = reader.take<uint32_t>();
      const auto textures = reader.take<uint32_t>();
      reader.take<std::array<uint32_t, 18>>();
      const auto bitmap = reader.take<std::array<uint64_t, 4>>();
      const auto mapped = reader.take<uint32_t>();
      const auto registers = reader.take<std::array<uint32_t, 1024>>();
      draw.system = reader.take<std::array<uint32_t, 64>>();
      const auto fetch = reader.take<std::array<uint32_t, 4>>();
      require(draw.sequence && sequences.insert(draw.sequence).second &&
                  textures <= 2 && draw.vertex_count > 0 &&
                  draw.vertex_count % 4 == 0 && draw.vertex_count <= UINT16_MAX &&
                  length == draw.vertex_count * 10 &&
                  !(draw.system[0] & 1) && draw.system[4] == 0 &&
                  draw.system[5] == 0 && draw.system[6] <= draw.system[7] &&
                  (fetch[2] & 0x1FFFFFFC) == (base & 0x1FFFFFFC) &&
                  (fetch[3] & 0x03FFFFFC) == length && (fetch[2] & 3) == 3,
              "unsupported procedural draw state");
      std::vector<uint32_t> packed;
      for (uint32_t reg = 0; reg < 256; ++reg)
        if (bitmap[reg / 64] & (uint64_t(1) << (reg % 64)))
          packed.insert(packed.end(), registers.begin() + reg * 4,
                        registers.begin() + reg * 4 + 4);
      require(packed.size() == mapped * 4 && (mapped == 25 || mapped == 23),
              "invalid packed procedural constants");
      if (variant == 0) {
        item.constants = std::move(packed);
        item.fetch = fetch;
      } else {
        require(packed == item.constants && fetch == item.fetch,
                "procedural vertex input changes between draws");
      }
      auto bit_float = [](uint32_t word) { return std::bit_cast<float>(word); };
      const float sy = bit_float(draw.system[33]);
      const float oy = bit_float(draw.system[37]);
      require(std::isfinite(sy) && sy > 0 && std::isfinite(oy) &&
                  bit_float(draw.system[32]) == 1 &&
                  bit_float(draw.system[34]) == -1 &&
                  std::abs(bit_float(draw.system[36]) - 1.f / width) < 1e-6f &&
                  bit_float(draw.system[38]) == 1 &&
                  std::abs((oy + 1) / sy - 1 + 1.f / height) < 1e-5f,
              "unsupported procedural viewport");
      item.draws.push_back(draw);
    }
    item.fetch[2] &= 3;
    scene.items.push_back(std::move(item));
  }
  require(reader.position == bytes.size() && sequences.size() <= 512,
          "trailing procedural fixture or draw limit");
  return scene;
}
}  // namespace

uint32_t pinyon_shift::native_renderer::RunSnr04ProceduralDiagnostic(
    const std::filesystem::path& fixture,
    const std::filesystem::path& shader_directory,
    const std::filesystem::path& output_directory,
    ID3D12Device* borrowed_device) {
  const auto begin = std::chrono::steady_clock::now();
  const auto source = read(fixture);
  const bool character = source.size() >= 8 &&
      std::memcmp(source.data(), "SNR03C1", 7) == 0;
  const auto scene = character ? load_character(source) : load_procedural(source);
  struct ShaderSpec { uint64_t hash; const char* file; const char* sha; };
  constexpr std::array<ShaderSpec, 4> shaders{{
      {0x3BC346726C1C2535ull, "vertex_3BC346726C1C2535_000000000000000F.dxil",
       "113b8c594001b1593fff3f4861c788342721a8b7e0251bef9e41688a69ae7c31"},
      {0xBDFD2AD68464101Aull, "vertex_BDFD2AD68464101A_000000000000000F.dxil",
       "42cfd0a51e91b4f00f2f0f40cbc4a9f689316fbd6950abd9dbd2da4d3458a347"},
      {0xCB8AC98467C0C283ull, "vertex_CB8AC98467C0C283_000000000000007F.dxil",
       "f759d5de1be2b8e4913d86e9c11210cd1ee76f33ff004b88fa4dd533e347b02c"},
      {0xA715C815EDB8EEE8ull, "vertex_A715C815EDB8EEE8_000000000000007F.dxil",
       "5c8692ddf2ff735d28b7b5f1fdce740b6be443ee942191c8d912d9a22852a269"},
  }};
  std::map<uint64_t, std::vector<char>> vertex_shaders;
  auto add_shader = [&](const ShaderSpec& spec) {
    auto bytes = read(shader_directory / spec.file);
    require(bytes.size() >= 4 && std::memcmp(bytes.data(), "DXBC", 4) == 0 &&
                sha256(bytes) == spec.sha, "wrong procedural vertex shader");
    vertex_shaders.emplace(spec.hash, std::move(bytes));
  };
  if (character) {
    add_shader({0xAC345DADF2F24AE4ull,
        "vertex_AC345DADF2F24AE4_000000000000000F.dxil",
        "90929ccb75eb107fcb20b9f4d91612c8416f87dd3402802673d9235bebfe00f0"});
  } else {
    for (const auto& spec : shaders) add_shader(spec);
  }
  const auto extracted = std::chrono::steady_clock::now();
  ComPtr<ID3D12Device> device;
  if (borrowed_device) device = borrowed_device;
  else {
    ComPtr<ID3D12Debug> debug;
    if (SUCCEEDED(D3D12GetDebugInterface(IID_PPV_ARGS(&debug))))
      debug->EnableDebugLayer();
    ComPtr<IDXGIFactory6> factory;
    check(CreateDXGIFactory2(0, IID_PPV_ARGS(&factory)));
    ComPtr<IDXGIAdapter1> adapter;
    check(factory->EnumAdapterByGpuPreference(0, DXGI_GPU_PREFERENCE_HIGH_PERFORMANCE,
                                             IID_PPV_ARGS(&adapter)));
    check(D3D12CreateDevice(adapter.Get(), D3D_FEATURE_LEVEL_11_0,
                            IID_PPV_ARGS(&device)));
  }
  constexpr char ps_source[] =
      "cbuffer Item : register(b2) { uint id; };"
      "float4 main() : SV_Target0 {"
      " return float4((id & 255) / 255.0, ((id >> 8) & 255) / 255.0, 0, 1); }";
  ComPtr<ID3DBlob> ps, errors;
  check(D3DCompile(ps_source, sizeof(ps_source) - 1, nullptr, nullptr, nullptr,
                   "main", "ps_5_1", 0, 0, &ps, &errors));
  D3D12_ROOT_PARAMETER parameters[6]{};
  for (uint32_t i = 0; i < 4; ++i) {
    parameters[i].ParameterType = i == 3 ? D3D12_ROOT_PARAMETER_TYPE_SRV
                                       : D3D12_ROOT_PARAMETER_TYPE_CBV;
    parameters[i].Descriptor.ShaderRegister = i == 2 ? 3 : i == 3 ? 0 : i;
    parameters[i].ShaderVisibility = D3D12_SHADER_VISIBILITY_VERTEX;
  }
  parameters[4].ParameterType = D3D12_ROOT_PARAMETER_TYPE_32BIT_CONSTANTS;
  parameters[4].Constants.ShaderRegister = 2;
  parameters[4].Constants.Num32BitValues = 1;
  parameters[4].ShaderVisibility = D3D12_SHADER_VISIBILITY_PIXEL;
  parameters[5].ParameterType = D3D12_ROOT_PARAMETER_TYPE_UAV;
  parameters[5].Descriptor.ShaderRegister = 0;
  parameters[5].ShaderVisibility = D3D12_SHADER_VISIBILITY_VERTEX;
  D3D12_ROOT_SIGNATURE_DESC root_description{
      6, parameters, 0, nullptr,
      D3D12_ROOT_SIGNATURE_FLAG_ALLOW_INPUT_ASSEMBLER_INPUT_LAYOUT |
          D3D12_ROOT_SIGNATURE_FLAG_ALLOW_STREAM_OUTPUT};
  ComPtr<ID3DBlob> root_blob;
  check(D3D12SerializeRootSignature(&root_description, D3D_ROOT_SIGNATURE_VERSION_1,
                                    &root_blob, &errors));
  ComPtr<ID3D12RootSignature> root;
  check(device->CreateRootSignature(0, root_blob->GetBufferPointer(),
                                    root_blob->GetBufferSize(), IID_PPV_ARGS(&root)));
  D3D12_GRAPHICS_PIPELINE_STATE_DESC desc{};
  desc.pRootSignature = root.Get();
  desc.PS = {ps->GetBufferPointer(), ps->GetBufferSize()};
  desc.SampleMask = UINT_MAX;
  desc.RasterizerState.FillMode = D3D12_FILL_MODE_SOLID;
  desc.RasterizerState.CullMode = character ? D3D12_CULL_MODE_BACK
                                          : D3D12_CULL_MODE_NONE;
  desc.RasterizerState.FrontCounterClockwise = character;
  desc.RasterizerState.DepthClipEnable = TRUE;
  desc.BlendState.RenderTarget[0].RenderTargetWriteMask =
      D3D12_COLOR_WRITE_ENABLE_ALL;
  desc.DepthStencilState.DepthEnable = TRUE;
  desc.DepthStencilState.DepthWriteMask = D3D12_DEPTH_WRITE_MASK_ALL;
  desc.DepthStencilState.DepthFunc = D3D12_COMPARISON_FUNC_GREATER_EQUAL;
  desc.PrimitiveTopologyType = D3D12_PRIMITIVE_TOPOLOGY_TYPE_TRIANGLE;
  desc.NumRenderTargets = 1;
  desc.RTVFormats[0] = DXGI_FORMAT_R8G8B8A8_UNORM;
  desc.DSVFormat = DXGI_FORMAT_D32_FLOAT;
  desc.SampleDesc.Count = 1;
  std::map<uint64_t, ComPtr<ID3D12PipelineState>> pipelines;
  std::map<uint64_t, ComPtr<ID3D12PipelineState>> stream_pipelines;
  D3D12_SO_DECLARATION_ENTRY position_declaration{0, "SV_Position", 0, 0, 4, 0};
  UINT position_stride = 16;
  for (const auto& [hash, bytes] : vertex_shaders) {
    desc.VS = {bytes.data(), bytes.size()};
    ComPtr<ID3D12PipelineState> pipeline;
    check(device->CreateGraphicsPipelineState(&desc, IID_PPV_ARGS(&pipeline)));
    pipelines.emplace(hash, std::move(pipeline));
    auto stream_desc = desc;
    stream_desc.PS = {};
    stream_desc.StreamOutput = {&position_declaration, 1, &position_stride, 1,
                                D3D12_SO_NO_RASTERIZED_STREAM};
    stream_desc.PrimitiveTopologyType = D3D12_PRIMITIVE_TOPOLOGY_TYPE_POINT;
    stream_desc.NumRenderTargets = 0;
    stream_desc.RTVFormats[0] = DXGI_FORMAT_UNKNOWN;
    stream_desc.DSVFormat = DXGI_FORMAT_UNKNOWN;
    stream_desc.DepthStencilState.DepthEnable = FALSE;
    ComPtr<ID3D12PipelineState> stream_pipeline;
    const auto stream_result = device->CreateGraphicsPipelineState(
        &stream_desc, IID_PPV_ARGS(&stream_pipeline));
    if (FAILED(stream_result)) {
      std::cerr << "procedural stream PSO shader " << std::hex << hash << '\n';
      ComPtr<ID3D12InfoQueue> messages;
      if (SUCCEEDED(device.As(&messages))) {
        for (UINT64 i = 0; i < messages->GetNumStoredMessages(); ++i) {
          SIZE_T size = 0;
          messages->GetMessage(i, nullptr, &size);
          std::vector<char> storage(size);
          auto* message = reinterpret_cast<D3D12_MESSAGE*>(storage.data());
          if (SUCCEEDED(messages->GetMessage(i, message, &size)))
            std::cerr << message->pDescription << '\n';
        }
      }
    }
    check(stream_result);
    stream_pipelines.emplace(hash, std::move(stream_pipeline));
  }
  D3D12_CLEAR_VALUE color_clear{};
  color_clear.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
  D3D12_CLEAR_VALUE depth_clear{};
  depth_clear.Format = DXGI_FORMAT_D32_FLOAT;
  depth_clear.DepthStencil.Depth = 0;
  auto color = texture(device.Get(), color_clear.Format,
                       D3D12_RESOURCE_FLAG_ALLOW_RENDER_TARGET,
                       D3D12_RESOURCE_STATE_RENDER_TARGET, color_clear);
  auto depth = texture(device.Get(), depth_clear.Format,
                       D3D12_RESOURCE_FLAG_ALLOW_DEPTH_STENCIL,
                       D3D12_RESOURCE_STATE_DEPTH_WRITE, depth_clear);
  D3D12_DESCRIPTOR_HEAP_DESC heap_desc{};
  heap_desc.Type = D3D12_DESCRIPTOR_HEAP_TYPE_RTV;
  heap_desc.NumDescriptors = 1;
  ComPtr<ID3D12DescriptorHeap> rtv;
  check(device->CreateDescriptorHeap(&heap_desc, IID_PPV_ARGS(&rtv)));
  device->CreateRenderTargetView(color.Get(), nullptr,
                                 rtv->GetCPUDescriptorHandleForHeapStart());
  heap_desc.Type = D3D12_DESCRIPTOR_HEAP_TYPE_DSV;
  ComPtr<ID3D12DescriptorHeap> dsv;
  check(device->CreateDescriptorHeap(&heap_desc, IID_PPV_ARGS(&dsv)));
  device->CreateDepthStencilView(depth.Get(), nullptr,
                                 dsv->GetCPUDescriptorHandleForHeapStart());
  uint32_t max_vertices = 0;
  for (const auto& item : scene.items)
    for (const auto& draw : item.draws)
      max_vertices = (std::max)(max_vertices, draw.vertex_count);
  std::vector<uint16_t> indices;
  for (uint32_t first = 0; first < max_vertices; first += 4)
    for (uint32_t corner : {0u, 1u, 3u, 1u, 2u, 3u})
      indices.push_back(uint16_t(first + corner));
  auto index_buffer = upload(device.Get(), indices.data(),
                             indices.size() * sizeof(uint16_t));
  struct Resources {
    ComPtr<ID3D12Resource> vertices, b1, b3;
    std::vector<ComPtr<ID3D12Resource>> b0, b0_original;
  };
  std::vector<Resources> owned;
  for (const auto& item : scene.items) {
    std::array<uint32_t, 192> fetch{};
    std::copy(item.fetch.begin(), item.fetch.end(), fetch.begin() + 188);
    Resources resource{upload(device.Get(), item.vertices.data(), item.vertices.size()),
                       upload(device.Get(), item.constants.data(),
                              item.constants.size() * sizeof(uint32_t)),
                       upload(device.Get(), fetch.data(), sizeof(fetch)), {}};
    for (const auto& draw : item.draws) {
      std::array<uint32_t, 120> system{};
      std::copy(draw.system.begin(), draw.system.end(), system.begin());
      resource.b0_original.push_back(upload(device.Get(), system.data(), sizeof(system)));
      if (!character) {
        system[33] = std::bit_cast<uint32_t>(1.f);
        system[37] = std::bit_cast<uint32_t>(-1.f / height);
      }
      resource.b0.push_back(upload(device.Get(), system.data(), sizeof(system)));
    }
    owned.push_back(std::move(resource));
  }
  D3D12_PLACED_SUBRESOURCE_FOOTPRINT color_layout{}, depth_layout{};
  uint64_t color_bytes = 0, depth_bytes = 0;
  auto color_description = color->GetDesc(), depth_description = depth->GetDesc();
  device->GetCopyableFootprints(&color_description, 0, 1, 0, &color_layout,
                                nullptr, nullptr, &color_bytes);
  device->GetCopyableFootprints(&depth_description, 0, 1, 0, &depth_layout,
                                nullptr, nullptr, &depth_bytes);
  auto color_readback = buffer(device.Get(), color_bytes, D3D12_HEAP_TYPE_READBACK,
                               D3D12_RESOURCE_STATE_COPY_DEST);
  auto depth_readback = buffer(device.Get(), depth_bytes, D3D12_HEAP_TYPE_READBACK,
                               D3D12_RESOURCE_STATE_COPY_DEST);
  ComPtr<ID3D12CommandQueue> queue;
  D3D12_COMMAND_QUEUE_DESC queue_desc{};
  check(device->CreateCommandQueue(&queue_desc, IID_PPV_ARGS(&queue)));
  ComPtr<ID3D12CommandAllocator> allocator;
  check(device->CreateCommandAllocator(D3D12_COMMAND_LIST_TYPE_DIRECT,
                                       IID_PPV_ARGS(&allocator)));
  ComPtr<ID3D12GraphicsCommandList> commands;
  check(device->CreateCommandList(0, D3D12_COMMAND_LIST_TYPE_DIRECT,
                                  allocator.Get(), nullptr, IID_PPV_ARGS(&commands)));
  auto rtv_handle = rtv->GetCPUDescriptorHandleForHeapStart();
  auto dsv_handle = dsv->GetCPUDescriptorHandleForHeapStart();
  constexpr float clear_color[4]{};
  commands->ClearRenderTargetView(rtv_handle, clear_color, 0, nullptr);
  commands->ClearDepthStencilView(dsv_handle, D3D12_CLEAR_FLAG_DEPTH, 0, 0, 0, nullptr);
  commands->OMSetRenderTargets(1, &rtv_handle, FALSE, &dsv_handle);
  D3D12_VIEWPORT viewport{0, 0, float(width), float(height), 0, 0.5f};
  D3D12_RECT scissor{0, 0, LONG(width), LONG(height)};
  commands->RSSetViewports(1, &viewport);
  commands->RSSetScissorRects(1, &scissor);
  commands->SetGraphicsRootSignature(root.Get());
  commands->IASetPrimitiveTopology(D3D_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
  D3D12_INDEX_BUFFER_VIEW index_view{index_buffer->GetGPUVirtualAddress(),
                                     UINT(indices.size() * sizeof(uint16_t)),
                                     DXGI_FORMAT_R16_UINT};
  commands->IASetIndexBuffer(&index_view);
  struct DrawRef { uint64_t sequence; size_t item, variant; };
  std::vector<DrawRef> draws;
  for (size_t i = 0; i < scene.items.size(); ++i)
    for (size_t j = 0; j < scene.items[i].draws.size(); ++j)
      draws.push_back({scene.items[i].draws[j].sequence, i, j});
  std::sort(draws.begin(), draws.end(), [](const auto& a, const auto& b) {
    return a.sequence < b.sequence;
  });
  std::vector<uint64_t> position_offsets;
  uint64_t position_allocation = 0, position_bytes = 0;
  for (const auto& ref : draws) {
    position_offsets.push_back(position_allocation);
    const auto bytes = uint64_t(scene.items[ref.item].draws[ref.variant].vertex_count) * 16;
    position_allocation += bytes + 8;
    position_bytes += bytes;
  }
  auto position_output = buffer(device.Get(), position_allocation,
                                D3D12_HEAP_TYPE_DEFAULT,
                                D3D12_RESOURCE_STATE_COPY_DEST);
  auto position_readback = buffer(device.Get(), position_allocation,
                                  D3D12_HEAP_TYPE_READBACK,
                                  D3D12_RESOURCE_STATE_COPY_DEST);
  const std::vector<char> zero_positions(position_allocation);
  auto position_zero = upload(device.Get(), zero_positions.data(), zero_positions.size());
  const auto built = std::chrono::steady_clock::now();
  for (const auto& ref : draws) {
    const auto& draw = scene.items[ref.item].draws[ref.variant];
    const auto& resource = owned[ref.item];
    if (character) {
      const float tile_offset = float(height) - draw.viewport[3];
      D3D12_VIEWPORT selected{draw.viewport[0], tile_offset,
                              draw.viewport[2], draw.viewport[3],
                              draw.viewport[4], draw.viewport[5]};
      D3D12_RECT clip{draw.scissor[0],
                      draw.scissor[1] + LONG(tile_offset),
                      draw.scissor[2],
                      draw.scissor[3] + LONG(tile_offset)};
      commands->RSSetViewports(1, &selected);
      commands->RSSetScissorRects(1, &clip);
    }
    commands->SetPipelineState(pipelines.at(draw.vertex_shader).Get());
    commands->SetGraphicsRootConstantBufferView(0, resource.b0[ref.variant]->GetGPUVirtualAddress());
    commands->SetGraphicsRootConstantBufferView(1, resource.b1->GetGPUVirtualAddress());
    commands->SetGraphicsRootConstantBufferView(2, resource.b3->GetGPUVirtualAddress());
    commands->SetGraphicsRootShaderResourceView(3, resource.vertices->GetGPUVirtualAddress());
    commands->SetGraphicsRoot32BitConstant(4, UINT(ref.item + 1), 0);
    commands->DrawIndexedInstanced(draw.vertex_count / 4 * 6, 1, 0, 0, 0);
  }
  commands->CopyBufferRegion(position_output.Get(), 0, position_zero.Get(), 0,
                             position_allocation);
  transition(commands.Get(), position_output.Get(), D3D12_RESOURCE_STATE_COPY_DEST,
             D3D12_RESOURCE_STATE_STREAM_OUT);
  commands->IASetPrimitiveTopology(D3D_PRIMITIVE_TOPOLOGY_POINTLIST);
  for (size_t ordinal = 0; ordinal < draws.size(); ++ordinal) {
    const auto& ref = draws[ordinal];
    const auto& draw = scene.items[ref.item].draws[ref.variant];
    const auto& resource = owned[ref.item];
    const auto bytes = uint64_t(draw.vertex_count) * 16;
    const auto address = position_output->GetGPUVirtualAddress() + position_offsets[ordinal];
    commands->SetPipelineState(stream_pipelines.at(draw.vertex_shader).Get());
    commands->SetGraphicsRootConstantBufferView(
        0, resource.b0_original[ref.variant]->GetGPUVirtualAddress());
    commands->SetGraphicsRootConstantBufferView(1, resource.b1->GetGPUVirtualAddress());
    commands->SetGraphicsRootConstantBufferView(2, resource.b3->GetGPUVirtualAddress());
    commands->SetGraphicsRootShaderResourceView(3, resource.vertices->GetGPUVirtualAddress());
    D3D12_STREAM_OUTPUT_BUFFER_VIEW position_view{address, bytes, address + bytes};
    commands->SOSetTargets(0, 1, &position_view);
    commands->DrawInstanced(draw.vertex_count, 1, 0, 0);
  }
  transition(commands.Get(), position_output.Get(), D3D12_RESOURCE_STATE_STREAM_OUT,
             D3D12_RESOURCE_STATE_COPY_SOURCE);
  commands->CopyResource(position_readback.Get(), position_output.Get());
  transition(commands.Get(), color.Get(), D3D12_RESOURCE_STATE_RENDER_TARGET,
             D3D12_RESOURCE_STATE_COPY_SOURCE);
  transition(commands.Get(), depth.Get(), D3D12_RESOURCE_STATE_DEPTH_WRITE,
             D3D12_RESOURCE_STATE_COPY_SOURCE);
  D3D12_TEXTURE_COPY_LOCATION source_location{}, destination{};
  source_location.Type = D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;
  destination.Type = D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;
  source_location.pResource = color.Get();
  destination.pResource = color_readback.Get();
  destination.PlacedFootprint = color_layout;
  commands->CopyTextureRegion(&destination, 0, 0, 0, &source_location, nullptr);
  source_location.pResource = depth.Get();
  destination.pResource = depth_readback.Get();
  destination.PlacedFootprint = depth_layout;
  commands->CopyTextureRegion(&destination, 0, 0, 0, &source_location, nullptr);
  check(commands->Close());
  ID3D12CommandList* lists[]{commands.Get()};
  queue->ExecuteCommandLists(1, lists);
  ComPtr<ID3D12Fence> fence;
  check(device->CreateFence(0, D3D12_FENCE_FLAG_NONE, IID_PPV_ARGS(&fence)));
  check(queue->Signal(fence.Get(), 1));
  HANDLE event = CreateEvent(nullptr, FALSE, FALSE, nullptr);
  require(event != nullptr, "CreateEvent failed");
  auto wait_result = fence->SetEventOnCompletion(1, event);
  auto waited = SUCCEEDED(wait_result) ? WaitForSingleObject(event, 30000) : WAIT_FAILED;
  CloseHandle(event);
  check(wait_result);
  require(waited == WAIT_OBJECT_0, "procedural GPU wait failed");
  check(device->GetDeviceRemovedReason());
  const auto drawn = std::chrono::steady_clock::now();
  std::filesystem::create_directories(output_directory);
  std::ofstream image(output_directory / "identity.ppm", std::ios::binary);
  std::ofstream depth_file(output_directory / "depth.f32", std::ios::binary);
  std::ofstream positions_file(output_directory / "postvs.f32x4", std::ios::binary);
  void* positions = nullptr;
  D3D12_RANGE position_range{0, SIZE_T(position_allocation)};
  check(position_readback->Map(0, &position_range, &positions));
  for (size_t ordinal = 0; ordinal < draws.size(); ++ordinal) {
    const auto& ref = draws[ordinal];
    const auto bytes = uint64_t(scene.items[ref.item].draws[ref.variant].vertex_count) * 16;
    const auto* segment = static_cast<const char*>(positions) + position_offsets[ordinal];
    uint64_t written = 0;
    std::memcpy(&written, segment + bytes, sizeof(written));
    require(written == bytes, "incomplete procedural post-VS stream output");
    positions_file.write(segment, bytes);
  }
  position_readback->Unmap(0, nullptr);
  positions_file.close();
  require(bool(positions_file), "procedural post-VS write failed");
  image << "P6\n" << width << ' ' << height << "\n255\n";
  D3D12_RANGE color_range{0, SIZE_T(color_bytes)}, depth_range{0, SIZE_T(depth_bytes)};
  void *colors = nullptr, *depths = nullptr;
  check(color_readback->Map(0, &color_range, &colors));
  check(depth_readback->Map(0, &depth_range, &depths));
  uint32_t covered = 0;
  std::vector<uint32_t> item_pixels(scene.items.size());
  for (uint32_t y = 0; y < height; ++y) {
    const auto* color_row = static_cast<const uint8_t*>(colors) +
                            y * color_layout.Footprint.RowPitch;
    const auto* depth_row = reinterpret_cast<const float*>(
        static_cast<const uint8_t*>(depths) + y * depth_layout.Footprint.RowPitch);
    for (uint32_t x = 0; x < width; ++x) {
      const auto* pixel = color_row + x * 4;
      image.write(reinterpret_cast<const char*>(pixel), 3);
      const auto id = uint32_t(pixel[0]) | (uint32_t(pixel[1]) << 8);
      if (id) {
        require(id <= scene.items.size() && std::isfinite(depth_row[x]) &&
                    depth_row[x] > 0 && depth_row[x] <= 1,
                "invalid procedural identity/depth");
        ++covered;
        ++item_pixels[id - 1];
      }
    }
    depth_file.write(reinterpret_cast<const char*>(depth_row), width * sizeof(float));
  }
  D3D12_RANGE empty{};
  color_readback->Unmap(0, &empty);
  depth_readback->Unmap(0, &empty);
  image.close();
  depth_file.close();
  require(bool(image) && bool(depth_file) && covered > 0,
          "empty or unwritable procedural diagnostic");
  const auto complete = std::chrono::steady_clock::now();
  auto us = [](auto a, auto b) {
    return std::chrono::duration_cast<std::chrono::microseconds>(b - a).count();
  };
  std::ofstream summary(output_directory / "summary.json");
  summary << "{\"schema\":\"pinyon-shift.snr04-"
          << (character ? "character" : "procedural") << ".v1\","
          << "\"source_frame\":" << scene.frame << ','
          << "\"fixture_sha256\":\"" << scene.sha << "\","
          << "\"items\":" << scene.items.size() << ','
          << "\"draws\":" << draws.size() << ','
          << "\"postvs_bytes\":" << position_bytes << ','
          << "\"covered_pixels\":" << covered << ','
          << "\"extract_us\":" << us(begin, extracted) << ','
          << "\"build_us\":" << us(extracted, built) << ','
          << "\"draw_readback_us\":" << us(built, drawn) << ','
          << "\"write_us\":" << us(drawn, complete) << ','
          << "\"item_pixels\":[";
  for (size_t i = 0; i < scene.items.size(); ++i) {
    if (i) summary << ',';
    summary << "{\"packet\":" << scene.items[i].packet
            << ",\"pixels\":" << item_pixels[i] << '}';
  }
  summary << "]}\n";
  summary.close();
  require(bool(summary), "procedural summary write failed");
  return covered;
}

uint32_t pinyon_shift::native_renderer::RunSnr04TrackDiagnostic(
    const std::filesystem::path& fixture,
    const std::filesystem::path& shader_directory,
    const std::filesystem::path& output_directory,
    ID3D12Device* borrowed_device) {
  const auto source = read(fixture);
  Reader reader{source};
  const auto magic = reader.take<std::array<char, 8>>();
  const bool raster_captured = magic ==
      (std::array<char, 8>{'S','N','R','0','2','T','4','\0'});
  require(raster_captured || magic ==
              (std::array<char, 8>{'S','N','R','0','2','T','3','\0'}),
          "wrong track fixture");
  const auto frame = reader.take<uint64_t>();
  const auto targets = reader.take<uint32_t>();
  const auto draw_count = reader.take<uint32_t>();
  const auto vertex_count = reader.take<uint32_t>();
  const auto index_count = reader.take<uint32_t>();
  require(targets > 0 && targets <= 256 && draw_count > 0 && draw_count <= 4096 &&
              vertex_count <= 4096 && index_count <= 4096,
          "unsupported track fixture counts");
  reader.take<std::array<uint32_t, 32>>();  // Title camera words.
  std::set<uint32_t> target_addresses;
  for (uint32_t i = 0; i < targets; ++i)
    require(target_addresses.insert(reader.take<uint32_t>()).second,
            "duplicate track target");
  using Range = std::pair<uint32_t, uint32_t>;
  auto read_ranges = [&](uint32_t count, uint32_t limit) {
    std::map<Range, std::vector<char>> ranges;
    size_t total = 0;
    for (uint32_t i = 0; i < count; ++i) {
      const auto base = reader.take<uint32_t>();
      const auto length = reader.take<uint32_t>();
      require(length > 0 && length <= limit && total + length <= 8 * 1024 * 1024,
              "unsupported track geometry bound");
      total += length;
      require(ranges.emplace(Range{base, length}, reader.bytes(length)).second,
              "duplicate track geometry range");
    }
    return ranges;
  };
  auto vertices = read_ranges(vertex_count, 512 * 1024);
  auto indices = read_ranges(index_count, 64 * 1024);
  struct TrackDraw {
    uint64_t sequence, shader, specialization;
    uint32_t packet, count;
    Range vertex, index;
    std::vector<uint32_t> packed;
    std::array<uint32_t, 64> system;
    std::array<uint32_t, 4> fetch;
    uint32_t raster_mode = 0, clip_control = 0, depth_control = 0;
    std::array<float, 6> viewport{};
    std::array<int32_t, 4> scissor{};
  };
  std::vector<TrackDraw> draws;
  draws.reserve(draw_count);
  std::set<uint32_t> seen_targets;
  for (uint32_t i = 0; i < draw_count; ++i) {
    TrackDraw draw{};
    draw.sequence = reader.take<uint64_t>();
    draw.shader = reader.take<uint64_t>();
    reader.take<uint64_t>();  // Pixel shader: private identity shader replaces it.
    draw.packet = reader.take<uint32_t>();
    const auto target = reader.take<uint32_t>();
    draw.count = reader.take<uint32_t>();
    const auto stride = reader.take<uint32_t>();
    draw.vertex = {reader.take<uint32_t>(), reader.take<uint32_t>()};
    draw.index = {reader.take<uint32_t>(), reader.take<uint32_t>()};
    draw.specialization = reader.take<uint64_t>();
    reader.take<uint64_t>();  // Dynamic-state identity.
    const auto format = reader.take<uint32_t>();
    const auto primitive = reader.take<uint32_t>();
    const auto restart = reader.take<uint32_t>();
    const auto endian = reader.take<uint32_t>();
    const auto bitmap = reader.take<std::array<uint64_t, 4>>();
    const auto words = reader.take<uint32_t>();
    require(words > 0 && words <= 1024 &&
                std::popcount(bitmap[0]) + std::popcount(bitmap[1]) +
                    std::popcount(bitmap[2]) + std::popcount(bitmap[3]) == words / 4 &&
                words % 4 == 0, "invalid track constants");
    draw.packed.reserve(words);
    for (uint32_t word = 0; word < words; ++word)
      draw.packed.push_back(reader.take<uint32_t>());
    draw.system = reader.take<std::array<uint32_t, 64>>();
    draw.fetch = reader.take<std::array<uint32_t, 4>>();
    if (raster_captured) {
      draw.raster_mode = reader.take<uint32_t>();
      draw.clip_control = reader.take<uint32_t>();
      draw.depth_control = reader.take<uint32_t>();
      draw.viewport = reader.take<std::array<float, 6>>();
      draw.scissor = reader.take<std::array<int32_t, 4>>();
      require(std::all_of(draw.viewport.begin(), draw.viewport.end(),
                          [](float value) { return std::isfinite(value); }) &&
                  draw.viewport[2] > 0 && draw.viewport[3] > 0 &&
                  draw.scissor[0] < draw.scissor[2] &&
                  draw.scissor[1] < draw.scissor[3],
              "invalid captured track raster state");
    }
    require(draw.sequence && (!i || draw.sequence > draws.back().sequence) &&
                target_addresses.contains(target) && vertices.contains(draw.vertex) &&
                indices.contains(draw.index) && format == 0 && primitive == 6 &&
                restart == 1 && endian == 1 && draw.system[4] == endian &&
                draw.count > 0 && draw.index.second == draw.count * 2 &&
                stride >= 4 && stride <= 9 &&
                (draw.fetch[2] & 0x1FFFFFFC) ==
                    (draw.vertex.first & 0x1FFFFFFC) &&
                (draw.fetch[3] & 0x03FFFFFC) == draw.vertex.second &&
                (draw.fetch[2] & 3) == 3,
            "unsupported track draw state");
    if (raster_captured)
      require((draw.raster_mode & 7) == 0 ||
                  (draw.raster_mode & 7) == 2,
              "unsupported track culling");
    auto as_float = [](uint32_t word) { return std::bit_cast<float>(word); };
    const float scale = as_float(draw.system[33]);
    const float offset = as_float(draw.system[37]);
    require(std::isfinite(scale) && scale > 0 && std::isfinite(offset) &&
                as_float(draw.system[32]) == 1 &&
                as_float(draw.system[34]) == -1 &&
                std::abs(as_float(draw.system[36]) - 1.f / width) < 1e-6f &&
                as_float(draw.system[38]) == 1 &&
                std::abs((offset + 1) / scale - 1 + 1.f / height) < 1e-5f,
            "unsupported track viewport");
    seen_targets.insert(target);
    draws.push_back(std::move(draw));
  }
  require(reader.position == source.size() && seen_targets == target_addresses,
          "incomplete track fixture");

  std::ifstream digest_file(shader_directory / "manifest.sha256");
  require(bool(digest_file), "missing verified track shader manifest");
  std::string label, fixture_digest;
  require(bool(digest_file >> label >> fixture_digest) && label == "fixture" &&
              fixture_digest == sha256(source), "wrong track shader fixture");
  std::map<std::string, std::string> shader_digests;
  std::string digest, filename_entry;
  while (digest_file >> digest >> filename_entry)
    require(shader_digests.emplace(filename_entry, digest).second,
            "duplicate track shader digest");
  require(digest_file.eof(), "invalid track shader manifest");
  std::map<std::pair<uint64_t, uint64_t>, std::vector<char>> shaders;
  for (const auto& draw : draws) {
    const auto key = std::pair{draw.shader, draw.specialization};
    if (shaders.contains(key)) continue;
    std::ostringstream filename;
    filename << "vertex_" << std::uppercase << std::hex << std::setfill('0')
             << std::setw(16) << draw.shader << '_' << std::setw(16)
             << draw.specialization << ".dxil";
    auto bytes = read(shader_directory / filename.str());
    require(bytes.size() >= 4 && std::memcmp(bytes.data(), "DXBC", 4) == 0,
            "missing exact track vertex shader");
    require(shader_digests.contains(filename.str()) &&
                sha256(bytes) == shader_digests.at(filename.str()),
            "changed track vertex shader");
    shaders.emplace(key, std::move(bytes));
  }
  require(shaders.size() == shader_digests.size(),
          "track shader manifest has unused entries");

  ComPtr<ID3D12Device> device;
  if (borrowed_device) device = borrowed_device;
  else {
    ComPtr<IDXGIFactory6> factory;
    check(CreateDXGIFactory2(0, IID_PPV_ARGS(&factory)));
    ComPtr<IDXGIAdapter1> adapter;
    check(factory->EnumAdapterByGpuPreference(0, DXGI_GPU_PREFERENCE_HIGH_PERFORMANCE,
                                             IID_PPV_ARGS(&adapter)));
    check(D3D12CreateDevice(adapter.Get(), D3D_FEATURE_LEVEL_11_0,
                            IID_PPV_ARGS(&device)));
  }
  constexpr char ps_source[] =
      "cbuffer Item : register(b2) { uint id; };"
      "float4 main() : SV_Target0 {"
      " return float4((id & 255) / 255.0, ((id >> 8) & 255) / 255.0, 0, 1); }";
  ComPtr<ID3DBlob> ps, errors;
  check(D3DCompile(ps_source, sizeof(ps_source) - 1, nullptr, nullptr, nullptr,
                   "main", "ps_5_1", 0, 0, &ps, &errors));
  D3D12_ROOT_PARAMETER parameters[6]{};
  for (uint32_t i = 0; i < 4; ++i) {
    parameters[i].ParameterType = i == 3 ? D3D12_ROOT_PARAMETER_TYPE_SRV
                                       : D3D12_ROOT_PARAMETER_TYPE_CBV;
    parameters[i].Descriptor.ShaderRegister = i == 2 ? 3 : i == 3 ? 0 : i;
    parameters[i].ShaderVisibility = D3D12_SHADER_VISIBILITY_VERTEX;
  }
  parameters[4].ParameterType = D3D12_ROOT_PARAMETER_TYPE_32BIT_CONSTANTS;
  parameters[4].Constants.ShaderRegister = 2;
  parameters[4].Constants.Num32BitValues = 1;
  parameters[4].ShaderVisibility = D3D12_SHADER_VISIBILITY_PIXEL;
  parameters[5].ParameterType = D3D12_ROOT_PARAMETER_TYPE_UAV;
  parameters[5].Descriptor.ShaderRegister = 0;
  parameters[5].ShaderVisibility = D3D12_SHADER_VISIBILITY_VERTEX;
  D3D12_ROOT_SIGNATURE_DESC root_description{
      6, parameters, 0, nullptr,
      D3D12_ROOT_SIGNATURE_FLAG_ALLOW_INPUT_ASSEMBLER_INPUT_LAYOUT};
  ComPtr<ID3DBlob> root_blob;
  check(D3D12SerializeRootSignature(&root_description, D3D_ROOT_SIGNATURE_VERSION_1,
                                    &root_blob, &errors));
  ComPtr<ID3D12RootSignature> root;
  check(device->CreateRootSignature(0, root_blob->GetBufferPointer(),
                                    root_blob->GetBufferSize(), IID_PPV_ARGS(&root)));
  D3D12_GRAPHICS_PIPELINE_STATE_DESC desc{};
  desc.pRootSignature = root.Get();
  desc.PS = {ps->GetBufferPointer(), ps->GetBufferSize()};
  desc.SampleMask = UINT_MAX;
  desc.RasterizerState.FillMode = D3D12_FILL_MODE_SOLID;
  desc.RasterizerState.CullMode = D3D12_CULL_MODE_NONE;
  desc.RasterizerState.DepthClipEnable = TRUE;
  desc.BlendState.RenderTarget[0].RenderTargetWriteMask =
      D3D12_COLOR_WRITE_ENABLE_ALL;
  desc.DepthStencilState.DepthEnable = TRUE;
  desc.DepthStencilState.DepthWriteMask = D3D12_DEPTH_WRITE_MASK_ALL;
  desc.DepthStencilState.DepthFunc = D3D12_COMPARISON_FUNC_GREATER_EQUAL;
  desc.PrimitiveTopologyType = D3D12_PRIMITIVE_TOPOLOGY_TYPE_TRIANGLE;
  desc.IBStripCutValue = D3D12_INDEX_BUFFER_STRIP_CUT_VALUE_0xFFFF;
  desc.NumRenderTargets = 1;
  desc.RTVFormats[0] = DXGI_FORMAT_R8G8B8A8_UNORM;
  desc.DSVFormat = DXGI_FORMAT_D32_FLOAT;
  desc.SampleDesc.Count = 1;
  using PipelineKey = std::tuple<uint64_t, uint64_t, uint32_t, uint32_t, uint32_t>;
  std::map<PipelineKey, ComPtr<ID3D12PipelineState>> pipelines;
  for (const auto& draw : draws) {
    const PipelineKey key{draw.shader, draw.specialization, draw.raster_mode,
                          draw.clip_control, draw.depth_control};
    if (pipelines.contains(key)) continue;
    const auto& bytes = shaders.at({draw.shader, draw.specialization});
    desc.VS = {bytes.data(), bytes.size()};
    if (raster_captured) {
      desc.RasterizerState.CullMode = (draw.raster_mode & 2)
          ? D3D12_CULL_MODE_BACK : D3D12_CULL_MODE_NONE;
      desc.RasterizerState.FrontCounterClockwise =
          (draw.raster_mode & 4) == 0;
      desc.RasterizerState.DepthClipEnable =
          (draw.clip_control & (1u << 16)) == 0;
      desc.DepthStencilState.DepthEnable = (draw.depth_control & 2) != 0;
      desc.DepthStencilState.DepthWriteMask = (draw.depth_control & 4)
          ? D3D12_DEPTH_WRITE_MASK_ALL : D3D12_DEPTH_WRITE_MASK_ZERO;
      desc.DepthStencilState.DepthFunc = D3D12_COMPARISON_FUNC(
          uint32_t(D3D12_COMPARISON_FUNC_NEVER) +
          ((draw.depth_control >> 4) & 7));
    }
    ComPtr<ID3D12PipelineState> pipeline;
    check(device->CreateGraphicsPipelineState(&desc, IID_PPV_ARGS(&pipeline)));
    pipelines.emplace(key, std::move(pipeline));
  }
  D3D12_CLEAR_VALUE color_clear{};
  color_clear.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
  D3D12_CLEAR_VALUE depth_clear{};
  depth_clear.Format = DXGI_FORMAT_D32_FLOAT;
  depth_clear.DepthStencil.Depth = 0;
  auto color = texture(device.Get(), color_clear.Format,
                       D3D12_RESOURCE_FLAG_ALLOW_RENDER_TARGET,
                       D3D12_RESOURCE_STATE_RENDER_TARGET, color_clear);
  auto depth = texture(device.Get(), depth_clear.Format,
                       D3D12_RESOURCE_FLAG_ALLOW_DEPTH_STENCIL,
                       D3D12_RESOURCE_STATE_DEPTH_WRITE, depth_clear);
  D3D12_DESCRIPTOR_HEAP_DESC heap_desc{};
  heap_desc.Type = D3D12_DESCRIPTOR_HEAP_TYPE_RTV;
  heap_desc.NumDescriptors = 1;
  ComPtr<ID3D12DescriptorHeap> rtv;
  check(device->CreateDescriptorHeap(&heap_desc, IID_PPV_ARGS(&rtv)));
  device->CreateRenderTargetView(color.Get(), nullptr,
                                 rtv->GetCPUDescriptorHandleForHeapStart());
  heap_desc.Type = D3D12_DESCRIPTOR_HEAP_TYPE_DSV;
  ComPtr<ID3D12DescriptorHeap> dsv;
  check(device->CreateDescriptorHeap(&heap_desc, IID_PPV_ARGS(&dsv)));
  device->CreateDepthStencilView(depth.Get(), nullptr,
                                 dsv->GetCPUDescriptorHandleForHeapStart());
  std::map<Range, ComPtr<ID3D12Resource>> vertex_buffers, index_buffers;
  for (const auto& [key, bytes] : vertices)
    vertex_buffers.emplace(key, upload(device.Get(), bytes.data(), bytes.size()));
  for (const auto& [key, bytes] : indices)
    index_buffers.emplace(key, upload(device.Get(), bytes.data(), bytes.size()));
  struct Bindings { ComPtr<ID3D12Resource> b0, b1, b3; };
  std::vector<Bindings> bindings;
  bindings.reserve(draws.size());
  for (const auto& draw : draws) {
    std::array<uint32_t, 120> system{};
    std::copy(draw.system.begin(), draw.system.end(), system.begin());
    if (!raster_captured) {
      system[33] = std::bit_cast<uint32_t>(1.f);
      system[37] = std::bit_cast<uint32_t>(-1.f / height);
    }
    std::array<uint32_t, 192> fetch{};
    std::copy(draw.fetch.begin(), draw.fetch.end(), fetch.begin() + 188);
    fetch[190] &= 3;  // Preserve fetch endian; rebase owned bytes to offset zero.
    bindings.push_back({upload(device.Get(), system.data(), sizeof(system)),
                        upload(device.Get(), draw.packed.data(),
                               draw.packed.size() * sizeof(uint32_t)),
                        upload(device.Get(), fetch.data(), sizeof(fetch))});
  }
  D3D12_PLACED_SUBRESOURCE_FOOTPRINT color_layout{}, depth_layout{};
  uint64_t color_bytes = 0, depth_bytes = 0;
  auto color_description = color->GetDesc(), depth_description = depth->GetDesc();
  device->GetCopyableFootprints(&color_description, 0, 1, 0, &color_layout,
                                nullptr, nullptr, &color_bytes);
  device->GetCopyableFootprints(&depth_description, 0, 1, 0, &depth_layout,
                                nullptr, nullptr, &depth_bytes);
  auto color_readback = buffer(device.Get(), color_bytes, D3D12_HEAP_TYPE_READBACK,
                               D3D12_RESOURCE_STATE_COPY_DEST);
  auto depth_readback = buffer(device.Get(), depth_bytes, D3D12_HEAP_TYPE_READBACK,
                               D3D12_RESOURCE_STATE_COPY_DEST);
  ComPtr<ID3D12CommandQueue> queue;
  D3D12_COMMAND_QUEUE_DESC queue_desc{};
  check(device->CreateCommandQueue(&queue_desc, IID_PPV_ARGS(&queue)));
  ComPtr<ID3D12CommandAllocator> allocator;
  check(device->CreateCommandAllocator(D3D12_COMMAND_LIST_TYPE_DIRECT,
                                       IID_PPV_ARGS(&allocator)));
  ComPtr<ID3D12GraphicsCommandList> commands;
  check(device->CreateCommandList(0, D3D12_COMMAND_LIST_TYPE_DIRECT,
                                  allocator.Get(), nullptr, IID_PPV_ARGS(&commands)));
  const auto rtv_handle = rtv->GetCPUDescriptorHandleForHeapStart();
  const auto dsv_handle = dsv->GetCPUDescriptorHandleForHeapStart();
  constexpr float clear_color[4]{};
  commands->ClearRenderTargetView(rtv_handle, clear_color, 0, nullptr);
  commands->ClearDepthStencilView(dsv_handle, D3D12_CLEAR_FLAG_DEPTH, 0, 0, 0, nullptr);
  commands->OMSetRenderTargets(1, &rtv_handle, FALSE, &dsv_handle);
  D3D12_VIEWPORT viewport{0, 0, float(width), float(height), 0, 0.5f};
  D3D12_RECT scissor{0, 0, LONG(width), LONG(height)};
  commands->RSSetViewports(1, &viewport);
  commands->RSSetScissorRects(1, &scissor);
  commands->SetGraphicsRootSignature(root.Get());
  commands->IASetPrimitiveTopology(D3D_PRIMITIVE_TOPOLOGY_TRIANGLESTRIP);
  for (size_t ordinal = 0; ordinal < draws.size(); ++ordinal) {
    const auto& draw = draws[ordinal];
    const auto& state = bindings[ordinal];
    if (raster_captured) {
      // The 1280x720 target is replayed as 256, 256, and 208-row EDRAM tiles.
      // Each later viewport is shortened by its output row offset.
      const float tile_offset = float(height) - draw.viewport[3];
      require(tile_offset >= 0 && tile_offset == std::floor(tile_offset) &&
                  draw.viewport[0] == 0 && draw.viewport[1] == 0 &&
                  draw.viewport[2] == width && draw.scissor[0] == 0 &&
                  draw.scissor[1] == 0 && draw.scissor[2] == int32_t(width) &&
                  draw.scissor[3] <= draw.viewport[3] &&
                  tile_offset + draw.scissor[3] <= height,
              "unsupported track EDRAM tile");
      D3D12_VIEWPORT selected{draw.viewport[0], draw.viewport[1],
                              draw.viewport[2], draw.viewport[3],
                              draw.viewport[4], draw.viewport[5]};
      selected.TopLeftY += tile_offset;
      D3D12_RECT clip{draw.scissor[0], draw.scissor[1],
                      draw.scissor[2], draw.scissor[3]};
      clip.top += LONG(tile_offset);
      clip.bottom += LONG(tile_offset);
      commands->RSSetViewports(1, &selected);
      commands->RSSetScissorRects(1, &clip);
    }
    const auto& index = index_buffers.at(draw.index);
    D3D12_INDEX_BUFFER_VIEW index_view{index->GetGPUVirtualAddress(),
                                       draw.index.second, DXGI_FORMAT_R16_UINT};
    commands->IASetIndexBuffer(&index_view);
    commands->SetPipelineState(pipelines.at(
        {draw.shader, draw.specialization, draw.raster_mode,
         draw.clip_control, draw.depth_control}).Get());
    commands->SetGraphicsRootConstantBufferView(0, state.b0->GetGPUVirtualAddress());
    commands->SetGraphicsRootConstantBufferView(1, state.b1->GetGPUVirtualAddress());
    commands->SetGraphicsRootConstantBufferView(2, state.b3->GetGPUVirtualAddress());
    commands->SetGraphicsRootShaderResourceView(
        3, vertex_buffers.at(draw.vertex)->GetGPUVirtualAddress());
    commands->SetGraphicsRoot32BitConstant(4, UINT(ordinal + 1), 0);
    commands->DrawIndexedInstanced(draw.count, 1, 0, 0, 0);
  }
  transition(commands.Get(), color.Get(), D3D12_RESOURCE_STATE_RENDER_TARGET,
             D3D12_RESOURCE_STATE_COPY_SOURCE);
  transition(commands.Get(), depth.Get(), D3D12_RESOURCE_STATE_DEPTH_WRITE,
             D3D12_RESOURCE_STATE_COPY_SOURCE);
  D3D12_TEXTURE_COPY_LOCATION source_location{}, destination{};
  source_location.Type = D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;
  destination.Type = D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;
  source_location.pResource = color.Get();
  destination.pResource = color_readback.Get();
  destination.PlacedFootprint = color_layout;
  commands->CopyTextureRegion(&destination, 0, 0, 0, &source_location, nullptr);
  source_location.pResource = depth.Get();
  destination.pResource = depth_readback.Get();
  destination.PlacedFootprint = depth_layout;
  commands->CopyTextureRegion(&destination, 0, 0, 0, &source_location, nullptr);
  check(commands->Close());
  ID3D12CommandList* lists[]{commands.Get()};
  queue->ExecuteCommandLists(1, lists);
  ComPtr<ID3D12Fence> fence;
  check(device->CreateFence(0, D3D12_FENCE_FLAG_NONE, IID_PPV_ARGS(&fence)));
  check(queue->Signal(fence.Get(), 1));
  HANDLE event = CreateEvent(nullptr, FALSE, FALSE, nullptr);
  require(event != nullptr, "CreateEvent failed");
  const auto wait = fence->SetEventOnCompletion(1, event);
  const auto waited = SUCCEEDED(wait) ? WaitForSingleObject(event, 30000) : WAIT_FAILED;
  CloseHandle(event);
  check(wait);
  require(waited == WAIT_OBJECT_0, "track GPU wait failed");
  check(device->GetDeviceRemovedReason());
  std::filesystem::create_directories(output_directory);
  std::ofstream image(output_directory / "identity.ppm", std::ios::binary);
  std::ofstream depth_file(output_directory / "depth.f32", std::ios::binary);
  image << "P6\n" << width << ' ' << height << "\n255\n";
  void *colors = nullptr, *depths = nullptr;
  D3D12_RANGE color_range{0, SIZE_T(color_bytes)}, depth_range{0, SIZE_T(depth_bytes)};
  check(color_readback->Map(0, &color_range, &colors));
  check(depth_readback->Map(0, &depth_range, &depths));
  uint32_t covered = 0;
  std::vector<uint32_t> draw_pixels(draws.size());
  for (uint32_t y = 0; y < height; ++y) {
    const auto* color_row = static_cast<const uint8_t*>(colors) +
                            y * color_layout.Footprint.RowPitch;
    const auto* depth_row = reinterpret_cast<const float*>(
        static_cast<const uint8_t*>(depths) + y * depth_layout.Footprint.RowPitch);
    for (uint32_t x = 0; x < width; ++x) {
      const auto* pixel = color_row + x * 4;
      image.write(reinterpret_cast<const char*>(pixel), 3);
      const auto id = uint32_t(pixel[0]) | (uint32_t(pixel[1]) << 8);
      if (id) {
        require(id <= draws.size() && std::isfinite(depth_row[x]) &&
                    depth_row[x] > 0 && depth_row[x] <= 1,
                "invalid track identity/depth");
        ++covered;
        ++draw_pixels[id - 1];
      }
    }
    depth_file.write(reinterpret_cast<const char*>(depth_row), width * sizeof(float));
  }
  D3D12_RANGE empty{};
  color_readback->Unmap(0, &empty);
  depth_readback->Unmap(0, &empty);
  image.close();
  depth_file.close();
  require(bool(image) && bool(depth_file) && covered > 0,
          "empty or unwritable track diagnostic");
  std::ofstream summary(output_directory / "summary.json");
  summary << "{\"schema\":\"pinyon-shift.snr04-track.v1\","
          << "\"source_frame\":" << frame << ','
          << "\"fixture_sha256\":\"" << sha256(source) << "\","
          << "\"width\":" << width << ",\"height\":" << height << ','
          << "\"draws\":" << draws.size() << ','
          << "\"shaders\":" << shaders.size() << ','
          << "\"raster_state_captured\":"
          << (raster_captured ? "true" : "false") << ','
          << "\"viewport_cull_depth_applied\":"
          << (raster_captured ? "true" : "false") << ','
          << "\"edram_tiles_rebased\":"
          << (raster_captured ? "true" : "false") << ','
          << "\"raster_state_applied\":false,"
          << "\"covered_pixels\":" << covered << ','
          << "\"visible_draws\":"
          << std::count_if(draw_pixels.begin(), draw_pixels.end(),
                           [](uint32_t value) { return value != 0; }) << ','
          << "\"draw_pixels\":[";
  for (size_t ordinal = 0; ordinal < draws.size(); ++ordinal) {
    if (ordinal) summary << ',';
    summary << "{\"sequence\":" << draws[ordinal].sequence
            << ",\"packet\":" << draws[ordinal].packet
            << ",\"pixels\":" << draw_pixels[ordinal] << '}';
  }
  summary << "]}\n";
  summary.close();
  require(bool(summary), "track summary write failed");
  return covered;
}

uint32_t pinyon_shift::native_renderer::RunSnr04ManagerDiagnostic(
    const std::filesystem::path& fixture,
    const std::filesystem::path& shader_directory,
    const std::filesystem::path& output_directory,
    ID3D12Device* borrowed_device) {
  const auto source = read(fixture);
  Reader reader{source};
  require(reader.take<std::array<char, 8>>() ==
              (std::array<char, 8>{'S','N','R','0','3','M','1','\0'}),
          "wrong manager fixture");
  const auto frame = reader.take<uint64_t>();
  reader.take<uint32_t>();  // Title view.
  reader.take<uint32_t>();  // Title camera.
  const auto record_count = reader.take<uint32_t>();
  const auto draw_count = reader.take<uint32_t>();
  const auto range_counts = reader.take<std::array<uint32_t, 3>>();
  require(record_count > 0 && record_count <= 256 &&
              draw_count >= record_count && draw_count <= 512 &&
              range_counts[0] > 0 && range_counts[0] <= 256 &&
              range_counts[1] > 0 && range_counts[1] <= 16 &&
              range_counts[2] > 0 && range_counts[2] <= 512,
          "unsupported manager fixture counts");
  reader.take<std::array<uint32_t, 32>>();  // Title camera matrices.
  std::set<uint32_t> packets;
  for (uint32_t i = 0; i < record_count; ++i) {
    reader.take<uint64_t>();  // Direct-packet ordinal.
    reader.take<uint32_t>();  // Title record.
    reader.take<uint32_t>();  // Source entry.
    require(packets.insert(reader.take<uint32_t>()).second,
            "duplicate manager title packet");
    reader.take<std::array<uint32_t, 7>>();  // Title record/source words.
  }
  using Range = std::pair<uint32_t, uint32_t>;
  std::array<std::map<Range, std::vector<char>>, 3> ranges;
  size_t owned_bytes = 0;
  for (uint32_t slot = 0; slot < 3; ++slot) {
    for (uint32_t i = 0; i < range_counts[slot]; ++i) {
      const Range key{reader.take<uint32_t>(), reader.take<uint32_t>()};
      const uint32_t limit = slot == 1 ? 3 * 1024 * 1024 : 128 * 1024;
      require(key.second > 0 && key.second <= limit &&
                  owned_bytes <= 8 * 1024 * 1024 - key.second,
              "unsupported manager range");
      owned_bytes += key.second;
      require(ranges[slot].emplace(key, reader.bytes(key.second)).second,
              "duplicate manager range");
    }
  }
  uint32_t first_address = UINT32_MAX;
  uint64_t end_address = 0;
  std::vector<std::pair<uint64_t, uint64_t>> intervals;
  for (uint32_t slot = 0; slot < 2; ++slot) {
    for (const auto& [key, bytes] : ranges[slot]) {
      first_address = (std::min)(first_address, key.first);
      end_address = (std::max)(end_address, uint64_t(key.first) + key.second);
      intervals.emplace_back(key.first, uint64_t(key.first) + key.second);
    }
  }
  std::sort(intervals.begin(), intervals.end());
  for (size_t i = 1; i < intervals.size(); ++i)
    require(intervals[i - 1].second <= intervals[i].first,
            "overlapping manager vertex ranges");
  require(first_address != UINT32_MAX && end_address > first_address &&
              end_address - first_address <= 24 * 1024 * 1024,
          "unsupported manager vertex address span");
  std::vector<char> vertex_span(end_address - first_address);
  for (uint32_t slot = 0; slot < 2; ++slot)
    for (const auto& [key, bytes] : ranges[slot])
      std::copy(bytes.begin(), bytes.end(),
                vertex_span.begin() + (key.first - first_address));

  struct ManagerDraw {
    uint64_t sequence = 0;
    uint32_t packet = 0, count = 0;
    std::array<Range, 3> ranges{};
    std::vector<uint32_t> packed;
    std::array<uint32_t, 64> system{};
    std::array<uint32_t, 4> fetch{};
    std::array<float, 6> viewport{};
    std::array<int32_t, 4> scissor{};
  };
  std::vector<ManagerDraw> draws;
  std::set<uint32_t> drawn_packets;
  uint32_t raster_mode = 0, clip_control = 0, depth_control = 0;
  for (uint32_t i = 0; i < draw_count; ++i) {
    ManagerDraw draw{};
    draw.sequence = reader.take<uint64_t>();
    draw.packet = reader.take<uint32_t>();
    const auto shader = reader.take<uint64_t>();
    const auto pixel_shader = reader.take<uint64_t>();
    const auto specialization = reader.take<uint64_t>();
    reader.take<uint64_t>();  // Dynamic state.
    draw.count = reader.take<uint32_t>();
    const auto host_format = reader.take<uint32_t>();
    const auto endianness = reader.take<uint32_t>();
    for (auto& range : draw.ranges)
      range = {reader.take<uint32_t>(), reader.take<uint32_t>()};
    reader.take<std::array<uint32_t, 18>>();  // Two material descriptors.
    const auto bitmap = reader.take<std::array<uint64_t, 4>>();
    const auto packed_count = reader.take<uint32_t>();
    require(packed_count > 0 && packed_count <= 1024 &&
                packed_count == 4 * (std::popcount(bitmap[0]) +
                                     std::popcount(bitmap[1]) +
                                     std::popcount(bitmap[2]) +
                                     std::popcount(bitmap[3])),
            "invalid manager vertex constants");
    draw.packed.reserve(packed_count);
    for (uint32_t word = 0; word < packed_count; ++word)
      draw.packed.push_back(reader.take<uint32_t>());
    draw.system = reader.take<std::array<uint32_t, 64>>();
    draw.fetch = reader.take<std::array<uint32_t, 4>>();
    const auto mode = reader.take<uint32_t>();
    const auto clip = reader.take<uint32_t>();
    const auto depth = reader.take<uint32_t>();
    draw.viewport = reader.take<std::array<float, 6>>();
    draw.scissor = reader.take<std::array<int32_t, 4>>();
    const float tile_offset = float(height) - draw.viewport[3];
    require(draw.sequence && (!i || draw.sequence > draws.back().sequence) &&
                packets.contains(draw.packet) &&
                shader == 0xB8489164D5A86043ull &&
                pixel_shader == 0x68150A8E959006CDull &&
                specialization == 31 && host_format == 0 && endianness == 1 &&
                draw.count > 0 && draw.ranges[2].second == draw.count * 2 &&
                ranges[0].contains(draw.ranges[0]) &&
                ranges[1].contains(draw.ranges[1]) &&
                ranges[2].contains(draw.ranges[2]) &&
                (draw.fetch[0] & 0x1FFFFFFC) == draw.ranges[1].first &&
                (draw.fetch[1] & 0x03FFFFFC) == draw.ranges[1].second &&
                (draw.fetch[2] & 0x1FFFFFFC) == draw.ranges[0].first &&
                (draw.fetch[3] & 0x03FFFFFC) == draw.ranges[0].second &&
                (draw.fetch[0] & 3) == 3 && (draw.fetch[2] & 3) == 3 &&
                draw.viewport[0] == 0 && draw.viewport[1] == 0 &&
                draw.viewport[2] == width && tile_offset >= 0 &&
                tile_offset == std::floor(tile_offset) &&
                draw.scissor[0] == 0 && draw.scissor[1] == 0 &&
                draw.scissor[2] == int32_t(width) &&
                draw.scissor[3] > 0 &&
                tile_offset + draw.scissor[3] <= height,
            "unsupported manager draw state");
    const auto& guest_indices = ranges[2].at(draw.ranges[2]);
    for (size_t byte = 0; byte < guest_indices.size(); byte += 2) {
      const auto index = (uint16_t(uint8_t(guest_indices[byte])) << 8) |
                         uint8_t(guest_indices[byte + 1]);
      require(uint32_t(index) * 32 + 32 <= draw.ranges[0].second &&
                  uint32_t(index) * 12 + 12 <= draw.ranges[1].second,
              "manager index exceeds captured vertex fetch");
    }
    if (i == 0) {
      raster_mode = mode;
      clip_control = clip;
      depth_control = depth;
    } else {
      require(mode == raster_mode && clip == clip_control &&
                  depth == depth_control,
              "manager raster state changes between draws");
    }
    drawn_packets.insert(draw.packet);
    draw.fetch[0] = (draw.fetch[0] & 3) +
                    (draw.ranges[1].first - first_address);
    draw.fetch[2] = (draw.fetch[2] & 3) +
                    (draw.ranges[0].first - first_address);
    draws.push_back(std::move(draw));
  }
  require(reader.position == source.size() && drawn_packets == packets,
          "incomplete manager fixture");
  const auto shader = read(shader_directory /
      "vertex_B8489164D5A86043_000000000000001F.dxil");
  require(shader.size() >= 4 && std::memcmp(shader.data(), "DXBC", 4) == 0 &&
              sha256(shader) ==
                  "1cd5925b8515aadb7db9c94911cf3aee1f66746bf2e899e218428845d990a248",
          "wrong manager vertex shader");

  ComPtr<ID3D12Device> device;
  if (borrowed_device) device = borrowed_device;
  else {
    ComPtr<IDXGIFactory6> factory;
    check(CreateDXGIFactory2(0, IID_PPV_ARGS(&factory)));
    ComPtr<IDXGIAdapter1> adapter;
    check(factory->EnumAdapterByGpuPreference(0, DXGI_GPU_PREFERENCE_HIGH_PERFORMANCE,
                                             IID_PPV_ARGS(&adapter)));
    check(D3D12CreateDevice(adapter.Get(), D3D_FEATURE_LEVEL_11_0,
                            IID_PPV_ARGS(&device)));
  }
  constexpr char ps_source[] =
      "cbuffer Item : register(b2) { uint id; };"
      "float4 main() : SV_Target0 {"
      " return float4((id & 255) / 255.0, ((id >> 8) & 255) / 255.0, 0, 1); }";
  ComPtr<ID3DBlob> ps, errors;
  check(D3DCompile(ps_source, sizeof(ps_source) - 1, nullptr, nullptr, nullptr,
                   "main", "ps_5_1", 0, 0, &ps, &errors));
  D3D12_ROOT_PARAMETER parameters[6]{};
  for (uint32_t i = 0; i < 4; ++i) {
    parameters[i].ParameterType = i == 3 ? D3D12_ROOT_PARAMETER_TYPE_SRV
                                         : D3D12_ROOT_PARAMETER_TYPE_CBV;
    parameters[i].Descriptor.ShaderRegister = i == 2 ? 3 : i == 3 ? 0 : i;
    parameters[i].ShaderVisibility = D3D12_SHADER_VISIBILITY_VERTEX;
  }
  parameters[4].ParameterType = D3D12_ROOT_PARAMETER_TYPE_32BIT_CONSTANTS;
  parameters[4].Constants.ShaderRegister = 2;
  parameters[4].Constants.Num32BitValues = 1;
  parameters[4].ShaderVisibility = D3D12_SHADER_VISIBILITY_PIXEL;
  parameters[5].ParameterType = D3D12_ROOT_PARAMETER_TYPE_UAV;
  parameters[5].Descriptor.ShaderRegister = 0;
  parameters[5].ShaderVisibility = D3D12_SHADER_VISIBILITY_VERTEX;
  D3D12_ROOT_SIGNATURE_DESC root_desc{
      6, parameters, 0, nullptr,
      D3D12_ROOT_SIGNATURE_FLAG_ALLOW_INPUT_ASSEMBLER_INPUT_LAYOUT};
  ComPtr<ID3DBlob> root_blob;
  check(D3D12SerializeRootSignature(&root_desc, D3D_ROOT_SIGNATURE_VERSION_1,
                                    &root_blob, &errors));
  ComPtr<ID3D12RootSignature> root;
  check(device->CreateRootSignature(0, root_blob->GetBufferPointer(),
                                    root_blob->GetBufferSize(), IID_PPV_ARGS(&root)));
  D3D12_GRAPHICS_PIPELINE_STATE_DESC desc{};
  desc.pRootSignature = root.Get();
  desc.VS = {shader.data(), shader.size()};
  desc.PS = {ps->GetBufferPointer(), ps->GetBufferSize()};
  desc.SampleMask = UINT_MAX;
  desc.RasterizerState.FillMode = D3D12_FILL_MODE_SOLID;
  desc.RasterizerState.CullMode = (raster_mode & 2)
      ? D3D12_CULL_MODE_BACK : D3D12_CULL_MODE_NONE;
  desc.RasterizerState.FrontCounterClockwise = (raster_mode & 4) == 0;
  desc.RasterizerState.DepthClipEnable = (clip_control & (1u << 16)) == 0;
  desc.BlendState.RenderTarget[0].RenderTargetWriteMask =
      D3D12_COLOR_WRITE_ENABLE_ALL;
  desc.DepthStencilState.DepthEnable = (depth_control & 2) != 0;
  desc.DepthStencilState.DepthWriteMask = (depth_control & 4)
      ? D3D12_DEPTH_WRITE_MASK_ALL : D3D12_DEPTH_WRITE_MASK_ZERO;
  desc.DepthStencilState.DepthFunc = D3D12_COMPARISON_FUNC(
      uint32_t(D3D12_COMPARISON_FUNC_NEVER) + ((depth_control >> 4) & 7));
  desc.PrimitiveTopologyType = D3D12_PRIMITIVE_TOPOLOGY_TYPE_TRIANGLE;
  desc.NumRenderTargets = 1;
  desc.RTVFormats[0] = DXGI_FORMAT_R8G8B8A8_UNORM;
  desc.DSVFormat = DXGI_FORMAT_D32_FLOAT;
  desc.SampleDesc.Count = 1;
  ComPtr<ID3D12PipelineState> pipeline;
  check(device->CreateGraphicsPipelineState(&desc, IID_PPV_ARGS(&pipeline)));
  D3D12_CLEAR_VALUE color_clear{};
  color_clear.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
  D3D12_CLEAR_VALUE depth_clear{};
  depth_clear.Format = DXGI_FORMAT_D32_FLOAT;
  depth_clear.DepthStencil.Depth = 0;
  auto color = texture(device.Get(), color_clear.Format,
                       D3D12_RESOURCE_FLAG_ALLOW_RENDER_TARGET,
                       D3D12_RESOURCE_STATE_RENDER_TARGET, color_clear);
  auto depth = texture(device.Get(), depth_clear.Format,
                       D3D12_RESOURCE_FLAG_ALLOW_DEPTH_STENCIL,
                       D3D12_RESOURCE_STATE_DEPTH_WRITE, depth_clear);
  D3D12_DESCRIPTOR_HEAP_DESC heap_desc{};
  heap_desc.Type = D3D12_DESCRIPTOR_HEAP_TYPE_RTV;
  heap_desc.NumDescriptors = 1;
  ComPtr<ID3D12DescriptorHeap> rtv;
  check(device->CreateDescriptorHeap(&heap_desc, IID_PPV_ARGS(&rtv)));
  device->CreateRenderTargetView(color.Get(), nullptr,
                                 rtv->GetCPUDescriptorHandleForHeapStart());
  heap_desc.Type = D3D12_DESCRIPTOR_HEAP_TYPE_DSV;
  ComPtr<ID3D12DescriptorHeap> dsv;
  check(device->CreateDescriptorHeap(&heap_desc, IID_PPV_ARGS(&dsv)));
  device->CreateDepthStencilView(depth.Get(), nullptr,
                                 dsv->GetCPUDescriptorHandleForHeapStart());
  auto vertices = upload(device.Get(), vertex_span.data(), vertex_span.size());
  std::map<Range, ComPtr<ID3D12Resource>> index_buffers;
  // The translated VS swaps the raw k8in16 index received from D3D12.
  for (const auto& [key, bytes] : ranges[2])
    index_buffers.emplace(key, upload(device.Get(), bytes.data(), bytes.size()));
  struct Bindings { ComPtr<ID3D12Resource> b0, b1, b3; };
  std::vector<Bindings> bindings;
  for (const auto& draw : draws) {
    std::array<uint32_t, 120> system{};
    std::copy(draw.system.begin(), draw.system.end(), system.begin());
    std::array<uint32_t, 192> fetch{};
    std::copy(draw.fetch.begin(), draw.fetch.end(), fetch.begin() + 188);
    bindings.push_back({upload(device.Get(), system.data(), sizeof(system)),
                        upload(device.Get(), draw.packed.data(),
                               draw.packed.size() * sizeof(uint32_t)),
                        upload(device.Get(), fetch.data(), sizeof(fetch))});
  }
  D3D12_PLACED_SUBRESOURCE_FOOTPRINT color_layout{}, depth_layout{};
  uint64_t color_bytes = 0, depth_bytes = 0;
  auto color_desc = color->GetDesc(), depth_desc = depth->GetDesc();
  device->GetCopyableFootprints(&color_desc, 0, 1, 0, &color_layout,
                                nullptr, nullptr, &color_bytes);
  device->GetCopyableFootprints(&depth_desc, 0, 1, 0, &depth_layout,
                                nullptr, nullptr, &depth_bytes);
  auto color_readback = buffer(device.Get(), color_bytes, D3D12_HEAP_TYPE_READBACK,
                               D3D12_RESOURCE_STATE_COPY_DEST);
  auto depth_readback = buffer(device.Get(), depth_bytes, D3D12_HEAP_TYPE_READBACK,
                               D3D12_RESOURCE_STATE_COPY_DEST);
  ComPtr<ID3D12CommandQueue> queue;
  D3D12_COMMAND_QUEUE_DESC queue_desc{};
  check(device->CreateCommandQueue(&queue_desc, IID_PPV_ARGS(&queue)));
  ComPtr<ID3D12CommandAllocator> allocator;
  check(device->CreateCommandAllocator(D3D12_COMMAND_LIST_TYPE_DIRECT,
                                       IID_PPV_ARGS(&allocator)));
  ComPtr<ID3D12GraphicsCommandList> commands;
  check(device->CreateCommandList(0, D3D12_COMMAND_LIST_TYPE_DIRECT,
                                  allocator.Get(), nullptr, IID_PPV_ARGS(&commands)));
  const auto rtv_handle = rtv->GetCPUDescriptorHandleForHeapStart();
  const auto dsv_handle = dsv->GetCPUDescriptorHandleForHeapStart();
  constexpr float clear_color[4]{};
  commands->ClearRenderTargetView(rtv_handle, clear_color, 0, nullptr);
  commands->ClearDepthStencilView(dsv_handle, D3D12_CLEAR_FLAG_DEPTH, 0, 0, 0, nullptr);
  commands->OMSetRenderTargets(1, &rtv_handle, FALSE, &dsv_handle);
  commands->SetGraphicsRootSignature(root.Get());
  commands->IASetPrimitiveTopology(D3D_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
  for (size_t ordinal = 0; ordinal < draws.size(); ++ordinal) {
    const auto& draw = draws[ordinal];
    const auto& state = bindings[ordinal];
    const float tile_offset = float(height) - draw.viewport[3];
    D3D12_VIEWPORT viewport{draw.viewport[0], tile_offset,
                            draw.viewport[2], draw.viewport[3],
                            draw.viewport[4], draw.viewport[5]};
    D3D12_RECT scissor{draw.scissor[0], draw.scissor[1] + LONG(tile_offset),
                       draw.scissor[2], draw.scissor[3] + LONG(tile_offset)};
    commands->RSSetViewports(1, &viewport);
    commands->RSSetScissorRects(1, &scissor);
    const auto& index = index_buffers.at(draw.ranges[2]);
    D3D12_INDEX_BUFFER_VIEW index_view{index->GetGPUVirtualAddress(),
                                       draw.ranges[2].second, DXGI_FORMAT_R16_UINT};
    commands->IASetIndexBuffer(&index_view);
    commands->SetPipelineState(pipeline.Get());
    commands->SetGraphicsRootConstantBufferView(0, state.b0->GetGPUVirtualAddress());
    commands->SetGraphicsRootConstantBufferView(1, state.b1->GetGPUVirtualAddress());
    commands->SetGraphicsRootConstantBufferView(2, state.b3->GetGPUVirtualAddress());
    commands->SetGraphicsRootShaderResourceView(3, vertices->GetGPUVirtualAddress());
    commands->SetGraphicsRoot32BitConstant(4, UINT(ordinal + 1), 0);
    commands->DrawIndexedInstanced(draw.count, 1, 0, 0, 0);
  }
  transition(commands.Get(), color.Get(), D3D12_RESOURCE_STATE_RENDER_TARGET,
             D3D12_RESOURCE_STATE_COPY_SOURCE);
  transition(commands.Get(), depth.Get(), D3D12_RESOURCE_STATE_DEPTH_WRITE,
             D3D12_RESOURCE_STATE_COPY_SOURCE);
  D3D12_TEXTURE_COPY_LOCATION from{}, to{};
  from.Type = D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;
  to.Type = D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;
  from.pResource = color.Get();
  to.pResource = color_readback.Get();
  to.PlacedFootprint = color_layout;
  commands->CopyTextureRegion(&to, 0, 0, 0, &from, nullptr);
  from.pResource = depth.Get();
  to.pResource = depth_readback.Get();
  to.PlacedFootprint = depth_layout;
  commands->CopyTextureRegion(&to, 0, 0, 0, &from, nullptr);
  check(commands->Close());
  ID3D12CommandList* lists[]{commands.Get()};
  queue->ExecuteCommandLists(1, lists);
  ComPtr<ID3D12Fence> fence;
  check(device->CreateFence(0, D3D12_FENCE_FLAG_NONE, IID_PPV_ARGS(&fence)));
  check(queue->Signal(fence.Get(), 1));
  HANDLE event = CreateEvent(nullptr, FALSE, FALSE, nullptr);
  require(event != nullptr, "CreateEvent failed");
  const auto wait = fence->SetEventOnCompletion(1, event);
  const auto waited = SUCCEEDED(wait) ? WaitForSingleObject(event, 30000) : WAIT_FAILED;
  CloseHandle(event);
  check(wait);
  require(waited == WAIT_OBJECT_0, "manager GPU wait failed");
  check(device->GetDeviceRemovedReason());
  std::filesystem::create_directories(output_directory);
  std::ofstream image(output_directory / "identity.ppm", std::ios::binary);
  std::ofstream depth_file(output_directory / "depth.f32", std::ios::binary);
  image << "P6\n" << width << ' ' << height << "\n255\n";
  void *colors = nullptr, *depths = nullptr;
  D3D12_RANGE color_range{0, SIZE_T(color_bytes)}, depth_range{0, SIZE_T(depth_bytes)};
  check(color_readback->Map(0, &color_range, &colors));
  check(depth_readback->Map(0, &depth_range, &depths));
  uint32_t covered = 0;
  std::vector<uint32_t> draw_pixels(draws.size());
  for (uint32_t y = 0; y < height; ++y) {
    const auto* color_row = static_cast<const uint8_t*>(colors) +
                            y * color_layout.Footprint.RowPitch;
    const auto* depth_row = reinterpret_cast<const float*>(
        static_cast<const uint8_t*>(depths) + y * depth_layout.Footprint.RowPitch);
    for (uint32_t x = 0; x < width; ++x) {
      const auto* pixel = color_row + x * 4;
      image.write(reinterpret_cast<const char*>(pixel), 3);
      const auto id = uint32_t(pixel[0]) | (uint32_t(pixel[1]) << 8);
      if (id) {
        require(id <= draws.size() && std::isfinite(depth_row[x]) &&
                    depth_row[x] > 0 && depth_row[x] <= 1,
                "invalid manager identity/depth");
        ++covered;
        ++draw_pixels[id - 1];
      }
    }
    depth_file.write(reinterpret_cast<const char*>(depth_row), width * sizeof(float));
  }
  D3D12_RANGE empty{};
  color_readback->Unmap(0, &empty);
  depth_readback->Unmap(0, &empty);
  image.close();
  depth_file.close();
  require(bool(image) && bool(depth_file) && covered > 0,
          "empty or unwritable manager diagnostic");
  std::ofstream summary(output_directory / "summary.json");
  summary << "{\"schema\":\"pinyon-shift.snr04-manager.v1\","
          << "\"source_frame\":" << frame << ','
          << "\"fixture_sha256\":\"" << sha256(source) << "\","
          << "\"records\":" << record_count << ','
          << "\"draws\":" << draws.size() << ','
          << "\"vertex_span_bytes\":" << vertex_span.size() << ','
          << "\"covered_pixels\":" << covered << ','
          << "\"visible_draws\":"
          << std::count_if(draw_pixels.begin(), draw_pixels.end(),
                           [](uint32_t value) { return value != 0; }) << ','
          << "\"draw_pixels\":[";
  for (size_t i = 0; i < draws.size(); ++i) {
    if (i) summary << ',';
    summary << "{\"sequence\":" << draws[i].sequence
            << ",\"packet\":" << draws[i].packet
            << ",\"pixels\":" << draw_pixels[i] << '}';
  }
  summary << "]}\n";
  summary.close();
  require(bool(summary), "manager summary write failed");
  return covered;
}
