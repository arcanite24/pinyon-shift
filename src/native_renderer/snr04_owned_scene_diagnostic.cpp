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
struct SegmentUploads {
  ComPtr<ID3D12Resource> color, depth, sample_upload;
  ComPtr<ID3D12RootSignature> sample_root;
  ComPtr<ID3D12PipelineState> sample_pipeline;
};
SegmentUploads initialize_segment_targets(
    ID3D12Device* device, ID3D12GraphicsCommandList* commands,
    ID3D12Resource* color, ID3D12Resource* depth,
    const D3D12_PLACED_SUBRESOURCE_FOOTPRINT& color_layout,
    const D3D12_PLACED_SUBRESOURCE_FOOTPRINT& depth_layout,
    D3D12_CPU_DESCRIPTOR_HANDLE rtv, D3D12_CPU_DESCRIPTOR_HANDLE dsv,
    const pinyon_shift::native_renderer::Snr04SegmentOptions* segment,
    uint32_t samples = 1) {
  SegmentUploads uploads;
  if (segment && !segment->prior_output.empty()) {
    if (samples == 4) {
      const auto ids = read(segment->prior_output / "identity.u16x4");
      const auto depths = read(segment->prior_output / "depth.f32x4");
      constexpr size_t count = size_t(width) * height * 4;
      require(ids.size() == count * sizeof(uint16_t) &&
                  depths.size() == count * sizeof(float),
              "wrong prior four-sample segment dimensions");
      std::vector<uint32_t> packed(count * 2);
      for (size_t index = 0; index < count; ++index) {
        uint16_t id;
        float value;
        std::memcpy(&id, ids.data() + index * sizeof(id), sizeof(id));
        std::memcpy(&value, depths.data() + index * sizeof(value), sizeof(value));
        require(id < segment->first_id && std::isfinite(value) &&
                    value >= 0 && value <= 1,
                "invalid prior four-sample identity/depth");
        packed[index * 2] = id;
        packed[index * 2 + 1] = std::bit_cast<uint32_t>(value);
      }
      uploads.sample_upload = upload(device, packed.data(),
                                     packed.size() * sizeof(uint32_t));
      constexpr char vs_source[] =
          "float4 main(uint id : SV_VertexID) : SV_Position {"
          " float2 uv = float2((id << 1) & 2, id & 2);"
          " return float4(uv * float2(2, -2) + float2(-1, 1), 0, 1); }";
      constexpr char ps_source[] =
          "StructuredBuffer<uint2> prior : register(t0);"
          "struct Output { float4 color : SV_Target0; float depth : SV_Depth; };"
          "Output main(float4 position : SV_Position, uint sample : SV_SampleIndex) {"
          " uint2 value = prior[((uint)position.y * 1280 + (uint)position.x) * 4 + sample];"
          " Output result;"
          " result.color = float4((value.x & 255) / 255.0,"
          " ((value.x >> 8) & 255) / 255.0, 0, 1);"
          " result.depth = asfloat(value.y); return result; }";
      ComPtr<ID3DBlob> vs, ps, errors, root_blob;
      check(D3DCompile(vs_source, sizeof(vs_source) - 1, nullptr, nullptr,
                       nullptr, "main", "vs_5_1", 0, 0, &vs, &errors));
      check(D3DCompile(ps_source, sizeof(ps_source) - 1, nullptr, nullptr,
                       nullptr, "main", "ps_5_1", 0, 0, &ps, &errors));
      D3D12_ROOT_PARAMETER parameter{};
      parameter.ParameterType = D3D12_ROOT_PARAMETER_TYPE_SRV;
      parameter.Descriptor.ShaderRegister = 0;
      parameter.ShaderVisibility = D3D12_SHADER_VISIBILITY_PIXEL;
      D3D12_ROOT_SIGNATURE_DESC root_description{1, &parameter};
      check(D3D12SerializeRootSignature(&root_description,
                                        D3D_ROOT_SIGNATURE_VERSION_1,
                                        &root_blob, &errors));
      check(device->CreateRootSignature(0, root_blob->GetBufferPointer(),
                                        root_blob->GetBufferSize(),
                                        IID_PPV_ARGS(&uploads.sample_root)));
      D3D12_GRAPHICS_PIPELINE_STATE_DESC pipeline{};
      pipeline.pRootSignature = uploads.sample_root.Get();
      pipeline.VS = {vs->GetBufferPointer(), vs->GetBufferSize()};
      pipeline.PS = {ps->GetBufferPointer(), ps->GetBufferSize()};
      pipeline.SampleMask = UINT_MAX;
      pipeline.RasterizerState.FillMode = D3D12_FILL_MODE_SOLID;
      pipeline.RasterizerState.CullMode = D3D12_CULL_MODE_NONE;
      pipeline.RasterizerState.DepthClipEnable = TRUE;
      pipeline.BlendState.RenderTarget[0].RenderTargetWriteMask =
          D3D12_COLOR_WRITE_ENABLE_ALL;
      pipeline.DepthStencilState.DepthEnable = TRUE;
      pipeline.DepthStencilState.DepthWriteMask = D3D12_DEPTH_WRITE_MASK_ALL;
      pipeline.DepthStencilState.DepthFunc = D3D12_COMPARISON_FUNC_ALWAYS;
      pipeline.PrimitiveTopologyType = D3D12_PRIMITIVE_TOPOLOGY_TYPE_TRIANGLE;
      pipeline.NumRenderTargets = 1;
      pipeline.RTVFormats[0] = DXGI_FORMAT_R8G8B8A8_UNORM;
      pipeline.DSVFormat = DXGI_FORMAT_D32_FLOAT;
      pipeline.SampleDesc.Count = 4;
      check(device->CreateGraphicsPipelineState(&pipeline,
                                                IID_PPV_ARGS(&uploads.sample_pipeline)));
      D3D12_VIEWPORT viewport{0, 0, float(width), float(height), 0, 1};
      D3D12_RECT scissor{0, 0, LONG(width), LONG(height)};
      commands->RSSetViewports(1, &viewport);
      commands->RSSetScissorRects(1, &scissor);
      commands->OMSetRenderTargets(1, &rtv, FALSE, &dsv);
      commands->SetGraphicsRootSignature(uploads.sample_root.Get());
      commands->SetPipelineState(uploads.sample_pipeline.Get());
      commands->SetGraphicsRootShaderResourceView(0,
                                                  uploads.sample_upload->GetGPUVirtualAddress());
      commands->IASetPrimitiveTopology(D3D_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
      commands->DrawInstanced(3, 1, 0, 0);
      return uploads;
    }
    require(color_layout.Footprint.RowPitch == width * 4 &&
                depth_layout.Footprint.RowPitch == width * 4,
            "unsupported segment copy pitch");
    const auto previous_color = read(segment->prior_output / "color.rgba");
    const auto previous_depth = read(segment->prior_output / "depth.f32");
    require(previous_color.size() == size_t(width) * height * 4 &&
                previous_depth.size() == previous_color.size(),
            "wrong prior segment dimensions");
    uploads.color = upload(device, previous_color.data(), previous_color.size());
    uploads.depth = upload(device, previous_depth.data(), previous_depth.size());
    for (const auto& [target, input, state, layout] : {
             std::tuple<ID3D12Resource*, ID3D12Resource*, D3D12_RESOURCE_STATES,
                        D3D12_PLACED_SUBRESOURCE_FOOTPRINT>{
                 color, uploads.color.Get(), D3D12_RESOURCE_STATE_RENDER_TARGET,
                 color_layout},
             {depth, uploads.depth.Get(), D3D12_RESOURCE_STATE_DEPTH_WRITE,
              depth_layout}}) {
      transition(commands, target, state, D3D12_RESOURCE_STATE_COPY_DEST);
      D3D12_TEXTURE_COPY_LOCATION from{}, to{};
      from.pResource = input;
      from.Type = D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;
      from.PlacedFootprint = layout;
      to.pResource = target;
      to.Type = D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;
      commands->CopyTextureRegion(&to, 0, 0, 0, &from, nullptr);
      transition(commands, target, D3D12_RESOURCE_STATE_COPY_DEST, state);
    }
  } else {
    constexpr float clear_color[4]{};
    commands->ClearRenderTargetView(rtv, clear_color, 0, nullptr);
    commands->ClearDepthStencilView(dsv, D3D12_CLEAR_FLAG_DEPTH, 0, 0, 0, nullptr);
  }
  return uploads;
}

struct SampleCapture {
  ComPtr<ID3D12Resource> output, readback;
  ComPtr<ID3D12DescriptorHeap> heap;
  ComPtr<ID3D12RootSignature> root;
  ComPtr<ID3D12PipelineState> pipeline;
};
SampleCapture make_sample_capture(ID3D12Device* device,
                                  ID3D12Resource* color, ID3D12Resource* depth) {
  constexpr char source[] =
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
  ComPtr<ID3DBlob> shader, errors, serialized;
  check(D3DCompile(source, sizeof(source) - 1, nullptr, nullptr, nullptr,
                   "main", "cs_5_1", 0, 0, &shader, &errors));
  D3D12_DESCRIPTOR_RANGE range{};
  range.RangeType = D3D12_DESCRIPTOR_RANGE_TYPE_SRV;
  range.NumDescriptors = 2;
  D3D12_ROOT_PARAMETER roots[2]{};
  roots[0].ParameterType = D3D12_ROOT_PARAMETER_TYPE_DESCRIPTOR_TABLE;
  roots[0].DescriptorTable = {1, &range};
  roots[1].ParameterType = D3D12_ROOT_PARAMETER_TYPE_UAV;
  D3D12_ROOT_SIGNATURE_DESC root_desc{2, roots};
  check(D3D12SerializeRootSignature(&root_desc, D3D_ROOT_SIGNATURE_VERSION_1,
                                    &serialized, &errors));
  SampleCapture capture;
  check(device->CreateRootSignature(0, serialized->GetBufferPointer(),
                                    serialized->GetBufferSize(),
                                    IID_PPV_ARGS(&capture.root)));
  D3D12_COMPUTE_PIPELINE_STATE_DESC compute{};
  compute.pRootSignature = capture.root.Get();
  compute.CS = {shader->GetBufferPointer(), shader->GetBufferSize()};
  check(device->CreateComputePipelineState(&compute,
                                           IID_PPV_ARGS(&capture.pipeline)));
  D3D12_DESCRIPTOR_HEAP_DESC heap_desc{};
  heap_desc.Type = D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV;
  heap_desc.NumDescriptors = 2;
  heap_desc.Flags = D3D12_DESCRIPTOR_HEAP_FLAG_SHADER_VISIBLE;
  check(device->CreateDescriptorHeap(&heap_desc, IID_PPV_ARGS(&capture.heap)));
  auto handle = capture.heap->GetCPUDescriptorHandleForHeapStart();
  D3D12_SHADER_RESOURCE_VIEW_DESC view{};
  view.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
  view.ViewDimension = D3D12_SRV_DIMENSION_TEXTURE2DMS;
  view.Shader4ComponentMapping = D3D12_DEFAULT_SHADER_4_COMPONENT_MAPPING;
  device->CreateShaderResourceView(color, &view, handle);
  handle.ptr += device->GetDescriptorHandleIncrementSize(
      D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV);
  view.Format = DXGI_FORMAT_R32_FLOAT;
  device->CreateShaderResourceView(depth, &view, handle);
  constexpr uint64_t sample_bytes = uint64_t(width) * height * 4 * 8;
  capture.output = buffer(device, sample_bytes, D3D12_HEAP_TYPE_DEFAULT,
                          D3D12_RESOURCE_STATE_UNORDERED_ACCESS,
                          D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS);
  capture.readback = buffer(device, sample_bytes, D3D12_HEAP_TYPE_READBACK,
                            D3D12_RESOURCE_STATE_COPY_DEST);
  return capture;
}
void record_sample_capture(ID3D12GraphicsCommandList* commands,
                           ID3D12Resource* color, ID3D12Resource* depth,
                           const SampleCapture& capture) {
  transition(commands, color, D3D12_RESOURCE_STATE_RENDER_TARGET,
             D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE);
  transition(commands, depth, D3D12_RESOURCE_STATE_DEPTH_WRITE,
             D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE);
  ID3D12DescriptorHeap* heaps[]{capture.heap.Get()};
  commands->SetDescriptorHeaps(1, heaps);
  commands->SetComputeRootSignature(capture.root.Get());
  commands->SetPipelineState(capture.pipeline.Get());
  commands->SetComputeRootDescriptorTable(
      0, capture.heap->GetGPUDescriptorHandleForHeapStart());
  commands->SetComputeRootUnorderedAccessView(
      1, capture.output->GetGPUVirtualAddress());
  commands->Dispatch((width + 7) / 8, (height + 7) / 8, 1);
  transition(commands, capture.output.Get(),
             D3D12_RESOURCE_STATE_UNORDERED_ACCESS,
             D3D12_RESOURCE_STATE_COPY_SOURCE);
  commands->CopyResource(capture.readback.Get(), capture.output.Get());
}
uint32_t write_sample_capture(const std::filesystem::path& directory,
                              const SampleCapture& capture, uint32_t max_id,
                              std::vector<uint32_t>* draw_pixels = nullptr,
                              uint32_t* zero_depth_pixels = nullptr) {
  constexpr size_t sample_bytes = size_t(width) * height * 4 * 8;
  D3D12_RANGE range{0, sample_bytes}, empty{};
  void* mapped = nullptr;
  check(capture.readback->Map(0, &range, &mapped));
  const auto* words = static_cast<const uint32_t*>(mapped);
  std::ofstream image(directory / "identity.ppm", std::ios::binary);
  std::ofstream depths(directory / "depth.f32", std::ios::binary);
  std::ofstream masks(directory / "coverage.u8", std::ios::binary);
  std::ofstream sample_ids(directory / "identity.u16x4", std::ios::binary);
  std::ofstream sample_depths(directory / "depth.f32x4", std::ios::binary);
  image << "P6\n" << width << ' ' << height << "\n255\n";
  uint32_t covered = 0;
  for (size_t pixel = 0; pixel < size_t(width) * height; ++pixel) {
    uint8_t mask = 0;
    for (uint32_t sample = 0; sample < 4; ++sample) {
      const auto id = words[(pixel * 4 + sample) * 2];
      const float depth = std::bit_cast<float>(words[(pixel * 4 + sample) * 2 + 1]);
      require(id <= max_id && std::isfinite(depth) && depth >= 0 && depth <= 1,
              "invalid four-sample identity/depth");
      if (id) mask |= uint8_t(1u << sample);
      const auto short_id = uint16_t(id);
      sample_ids.write(reinterpret_cast<const char*>(&short_id), sizeof(short_id));
      sample_depths.write(reinterpret_cast<const char*>(&depth), sizeof(depth));
      if (sample == 0) {
        const char rgb[3]{char(id & 255), char((id >> 8) & 255), 0};
        image.write(rgb, sizeof(rgb));
        depths.write(reinterpret_cast<const char*>(&depth), sizeof(depth));
        if (id) {
          ++covered;
          if (draw_pixels) ++(*draw_pixels)[id - 1];
          if (zero_depth_pixels) *zero_depth_pixels += depth == 0;
        }
      }
    }
    masks.write(reinterpret_cast<const char*>(&mask), sizeof(mask));
  }
  capture.readback->Unmap(0, &empty);
  require(bool(image) && bool(depths) && bool(masks) && bool(sample_ids) &&
              bool(sample_depths) && covered,
          "empty or unwritable four-sample diagnostic");
  return covered;
}

struct AlphaTexture {
  ComPtr<ID3D12Resource> image, staging;
  ComPtr<ID3D12DescriptorHeap> views, samplers;
  std::array<D3D12_PLACED_SUBRESOURCE_FOOTPRINT, 9> layouts{};
};
AlphaTexture make_alpha_texture(ID3D12Device* device,
                                const std::filesystem::path& path) {
  const auto bytes = read(path);
  require(bytes.size() == 87408 &&
              sha256(bytes) ==
                  "812af0dc0bcfe510207bab31eb22ff7e55693fbe65f109b3a19a0d7c25d5478e",
          "wrong matched-event BC3 mip chain");
  D3D12_RESOURCE_DESC description{};
  description.Dimension = D3D12_RESOURCE_DIMENSION_TEXTURE2D;
  description.Width = description.Height = 256;
  description.DepthOrArraySize = 1;
  description.MipLevels = 9;
  description.Format = DXGI_FORMAT_BC3_UNORM;
  description.SampleDesc.Count = 1;
  D3D12_HEAP_PROPERTIES properties{};
  properties.Type = D3D12_HEAP_TYPE_DEFAULT;
  AlphaTexture alpha;
  check(device->CreateCommittedResource(
      &properties, D3D12_HEAP_FLAG_NONE, &description,
      D3D12_RESOURCE_STATE_COPY_DEST, nullptr, IID_PPV_ARGS(&alpha.image)));
  std::array<UINT, 9> rows{};
  std::array<UINT64, 9> row_bytes{};
  uint64_t total = 0;
  device->GetCopyableFootprints(&description, 0, 9, 0, alpha.layouts.data(),
                                rows.data(), row_bytes.data(), &total);
  alpha.staging = buffer(device, total, D3D12_HEAP_TYPE_UPLOAD,
                         D3D12_RESOURCE_STATE_GENERIC_READ);
  void* mapped = nullptr;
  D3D12_RANGE empty{};
  check(alpha.staging->Map(0, &empty, &mapped));
  size_t offset = 0;
  for (uint32_t mip = 0; mip < 9; ++mip) {
    require(offset + rows[mip] * row_bytes[mip] <= bytes.size(),
            "truncated matched-event BC3 mip");
    for (UINT row = 0; row < rows[mip]; ++row)
      std::memcpy(static_cast<char*>(mapped) + alpha.layouts[mip].Offset +
                      row * alpha.layouts[mip].Footprint.RowPitch,
                  bytes.data() + offset + row * row_bytes[mip], row_bytes[mip]);
    offset += rows[mip] * row_bytes[mip];
  }
  alpha.staging->Unmap(0, nullptr);
  require(offset == bytes.size(), "extra matched-event BC3 bytes");
  D3D12_DESCRIPTOR_HEAP_DESC heap{};
  heap.Type = D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV;
  heap.NumDescriptors = 1;
  heap.Flags = D3D12_DESCRIPTOR_HEAP_FLAG_SHADER_VISIBLE;
  check(device->CreateDescriptorHeap(&heap, IID_PPV_ARGS(&alpha.views)));
  D3D12_SHADER_RESOURCE_VIEW_DESC view{};
  view.Format = DXGI_FORMAT_BC3_UNORM;
  view.ViewDimension = D3D12_SRV_DIMENSION_TEXTURE2DARRAY;
  view.Shader4ComponentMapping = D3D12_DEFAULT_SHADER_4_COMPONENT_MAPPING;
  view.Texture2DArray.ArraySize = 1;
  view.Texture2DArray.MipLevels = 9;
  device->CreateShaderResourceView(alpha.image.Get(), &view,
                                   alpha.views->GetCPUDescriptorHandleForHeapStart());
  heap.Type = D3D12_DESCRIPTOR_HEAP_TYPE_SAMPLER;
  check(device->CreateDescriptorHeap(&heap, IID_PPV_ARGS(&alpha.samplers)));
  D3D12_SAMPLER_DESC sampler{};
  sampler.Filter = D3D12_FILTER_ANISOTROPIC;
  sampler.AddressU = sampler.AddressV = sampler.AddressW =
      D3D12_TEXTURE_ADDRESS_MODE_CLAMP;
  sampler.MaxAnisotropy = 4;
  sampler.MaxLOD = D3D12_FLOAT32_MAX;
  device->CreateSampler(&sampler,
                        alpha.samplers->GetCPUDescriptorHandleForHeapStart());
  return alpha;
}
void upload_alpha_texture(ID3D12GraphicsCommandList* commands,
                          const AlphaTexture& alpha) {
  for (uint32_t mip = 0; mip < 9; ++mip) {
    D3D12_TEXTURE_COPY_LOCATION to{}, from{};
    to.pResource = alpha.image.Get();
    to.Type = D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;
    to.SubresourceIndex = mip;
    from.pResource = alpha.staging.Get();
    from.Type = D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;
    from.PlacedFootprint = alpha.layouts[mip];
    commands->CopyTextureRegion(&to, 0, 0, 0, &from, nullptr);
  }
  transition(commands, alpha.image.Get(), D3D12_RESOURCE_STATE_COPY_DEST,
             D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE);
}
}  // namespace

uint32_t pinyon_shift::native_renderer::RunSnr04OwnedSceneDiagnostic(
    std::span<const char> fixture,
    const std::filesystem::path& vertex_shader,
    const std::filesystem::path& output_directory,
    ID3D12Device* borrowed_device, uint32_t samples,
    const Snr04SegmentOptions* segment) {
  require(samples == 1 || samples == 4, "unsupported sample count");
  if (segment)
    require(segment->first_sequence &&
                segment->first_sequence <= segment->last_sequence &&
                segment->first_id && segment->draw_count &&
                segment->first_id + uint64_t(segment->draw_count) <= 65536,
            "invalid vegetation segment");
  const bool alpha_probe = segment && !segment->alpha_bc3.empty();
  if (alpha_probe)
    require(samples == 4 && segment->first_sequence == 10125747 &&
                segment->last_sequence == 10125747 &&
                segment->first_id == 290 && segment->draw_count == 1 &&
                !segment->prior_output.empty(),
            "alpha probe requires matched event 11204 and compatibility prior");
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
  // Event 11204's captured BC3 alpha path and four SV_Coverage thresholds.
  // Record three pixels with exactly one reference fragment for UV comparison.
  constexpr char alpha_source[] =
      "cbuffer Item : register(b2) { uint id; };"
      "Texture2DArray<float4> foliage : register(t0);"
      "SamplerState foliage_sampler : register(s0);"
      "RWStructuredBuffer<float4> observations : register(u0);"
      "struct Input { float4 uv : TEXCOORD0;"
      " centroid float4 v1 : TEXCOORD1; float4 v2 : TEXCOORD2;"
      " centroid float4 v3 : TEXCOORD3;"
      " centroid float4 fade : TEXCOORD4; float4 position : SV_Position; };"
      "struct Output { float4 color : SV_Target0; uint mask : SV_Coverage; };"
      "Output main(Input p) {"
      " float2 uv = p.uv.xy + 0.001465 / 256.0;"
      " float alpha = foliage.SampleGrad(foliage_sampler, float3(uv, 0),"
      " ddx_coarse(uv), ddy_coarse(uv)).a * p.fade.w;"
      " uint2 pixel = (uint2)p.position.xy;"
      " if (pixel.x == 1143 && pixel.y == 50)"
      " observations[0] = float4(p.uv.xy, p.fade.w, alpha);"
      " if (pixel.x == 1153 && pixel.y == 51)"
      " observations[1] = float4(p.uv.xy, p.fade.w, alpha);"
      " if (pixel.x == 1154 && pixel.y == 47)"
      " observations[2] = float4(p.uv.xy, p.fade.w, alpha);"
      " uint shift = (((uint)p.position.x & 1u) << 2) |"
      " (((uint)p.position.y & 1u) << 1);"
      " float dither = (float)((426u >> shift) & 3u) * 0.0625;"
      " Output o;"
      " o.mask = (alpha >= 0.75 - dither ? 1u : 0u) |"
      " (alpha >= 0.25 - dither ? 2u : 0u) |"
      " (alpha >= 0.50 - dither ? 4u : 0u) |"
      " (alpha >= 1.00 - dither ? 8u : 0u);"
      " o.color = float4((id & 255) / 255.0, ((id >> 8) & 255) / 255.0, 0, 1);"
      " return o; }";
  ComPtr<ID3DBlob> alpha_ps;
  if (alpha_probe)
    check(D3DCompile(alpha_source, sizeof(alpha_source) - 1, nullptr, nullptr,
                     nullptr, "main", "ps_5_1", 0, 0, &alpha_ps, &errors));
  D3D12_ROOT_PARAMETER parameters[9]{};
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
  D3D12_DESCRIPTOR_RANGE alpha_view_range{}, alpha_sampler_range{};
  if (alpha_probe) {
    alpha_view_range.RangeType = D3D12_DESCRIPTOR_RANGE_TYPE_SRV;
    alpha_view_range.NumDescriptors = 1;
    alpha_sampler_range.RangeType = D3D12_DESCRIPTOR_RANGE_TYPE_SAMPLER;
    alpha_sampler_range.NumDescriptors = 1;
    parameters[6].ParameterType = D3D12_ROOT_PARAMETER_TYPE_DESCRIPTOR_TABLE;
    parameters[6].DescriptorTable = {1, &alpha_view_range};
    parameters[6].ShaderVisibility = D3D12_SHADER_VISIBILITY_PIXEL;
    parameters[7].ParameterType = D3D12_ROOT_PARAMETER_TYPE_DESCRIPTOR_TABLE;
    parameters[7].DescriptorTable = {1, &alpha_sampler_range};
    parameters[7].ShaderVisibility = D3D12_SHADER_VISIBILITY_PIXEL;
    parameters[8].ParameterType = D3D12_ROOT_PARAMETER_TYPE_UAV;
    parameters[8].Descriptor.ShaderRegister = 0;
    parameters[8].ShaderVisibility = D3D12_SHADER_VISIBILITY_PIXEL;
  }
  D3D12_ROOT_SIGNATURE_DESC root_description{
      alpha_probe ? 9u : 6u, parameters, 0, nullptr,
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
  ComPtr<ID3D12PipelineState> alpha_pipeline;
  if (alpha_probe) {
    auto description = pipeline_description;
    description.PS = {alpha_ps->GetBufferPointer(), alpha_ps->GetBufferSize()};
    check(device->CreateGraphicsPipelineState(&description,
                                              IID_PPV_ARGS(&alpha_pipeline)));
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
  AlphaTexture alpha_texture;
  if (alpha_probe)
    alpha_texture = make_alpha_texture(device.Get(), segment->alpha_bc3);
  ComPtr<ID3D12Resource> alpha_inputs, alpha_inputs_readback, alpha_inputs_zero;
  if (alpha_probe) {
    alpha_inputs = buffer(device.Get(), 3 * 16, D3D12_HEAP_TYPE_DEFAULT,
                          D3D12_RESOURCE_STATE_COPY_DEST,
                          D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS);
    alpha_inputs_readback = buffer(device.Get(), 3 * 16,
                                   D3D12_HEAP_TYPE_READBACK,
                                   D3D12_RESOURCE_STATE_COPY_DEST);
    const std::array<float, 12> zeros{};
    alpha_inputs_zero = upload(device.Get(), zeros.data(), sizeof(zeros));
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
  auto prior = initialize_segment_targets(
      device.Get(), commands.Get(), color.Get(), depth.Get(), color_layout,
      depth_layout, rtv_handle, dsv_handle, segment, samples);
  if (alpha_probe) {
    upload_alpha_texture(commands.Get(), alpha_texture);
    commands->CopyBufferRegion(alpha_inputs.Get(), 0, alpha_inputs_zero.Get(), 0,
                               3 * 16);
    transition(commands.Get(), alpha_inputs.Get(), D3D12_RESOURCE_STATE_COPY_DEST,
               D3D12_RESOURCE_STATE_UNORDERED_ACCESS);
  }
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
  require(!segment || scene.sequenced, "vegetation segment needs draw sequences");
  uint32_t segment_draws = 0;
  for (const auto& draw : draws) {
    if (segment && (draw.sequence < segment->first_sequence ||
                    draw.sequence > segment->last_sequence)) continue;
    const auto& item = scene.items[draw.item];
    const auto& resource = owned[draw.item];
    if (alpha_probe) {
      const auto& system = item.variants[draw.variant].system;
      require(item.packet == 317998104 && system[0] == 984 &&
                  system[44] == 16191 && system[54] == 1 &&
                  system[55] == 1 && system[57] == 426,
              "matched foliage alpha state changed");
      ID3D12DescriptorHeap* heaps[]{alpha_texture.views.Get(),
                                    alpha_texture.samplers.Get()};
      commands->SetDescriptorHeaps(2, heaps);
      commands->SetGraphicsRootDescriptorTable(
          6, alpha_texture.views->GetGPUDescriptorHandleForHeapStart());
      commands->SetGraphicsRootDescriptorTable(
          7, alpha_texture.samplers->GetGPUDescriptorHandleForHeapStart());
      commands->SetGraphicsRootUnorderedAccessView(
          8, alpha_inputs->GetGPUVirtualAddress());
      commands->SetPipelineState(alpha_pipeline.Get());
    }
    commands->SetGraphicsRootConstantBufferView(
        0, resource.b0_variants[draw.variant]->GetGPUVirtualAddress());
    commands->SetGraphicsRootConstantBufferView(1, resource.b1->GetGPUVirtualAddress());
    commands->SetGraphicsRootConstantBufferView(2, resource.b3->GetGPUVirtualAddress());
    commands->SetGraphicsRootShaderResourceView(3, resource.vertices->GetGPUVirtualAddress());
    commands->SetGraphicsRoot32BitConstant(
        4, segment ? segment->first_id + segment_draws : UINT(draw.item + 1), 0);
    commands->DrawIndexedInstanced(item.vertex_count / 4 * 6, 1, 0, 0, 0);
    ++segment_draws;
  }
  require(!segment || segment_draws == segment->draw_count,
          "vegetation segment draw count mismatch");
  if (alpha_probe) {
    transition(commands.Get(), alpha_inputs.Get(),
               D3D12_RESOURCE_STATE_UNORDERED_ACCESS,
               D3D12_RESOURCE_STATE_COPY_SOURCE);
    commands->CopyResource(alpha_inputs_readback.Get(), alpha_inputs.Get());
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
  if (alpha_probe) {
    std::ofstream debug_file(directory / "alpha-inputs.f32x4", std::ios::binary);
    void* mapped = nullptr;
    D3D12_RANGE range{0, 3 * 16};
    check(alpha_inputs_readback->Map(0, &range, &mapped));
    debug_file.write(static_cast<const char*>(mapped), 3 * 16);
    D3D12_RANGE empty{};
    alpha_inputs_readback->Unmap(0, &empty);
    require(bool(debug_file), "alpha input readback write failed");
  }
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
    std::ofstream rgba(directory / "color.rgba", std::ios::binary);
    void *colors = nullptr, *depths = nullptr;
    D3D12_RANGE color_range{0, SIZE_T(color_bytes)}, depth_range{0, SIZE_T(depth_bytes)};
    check(color_readback->Map(0, &color_range, &colors));
    check(depth_readback->Map(0, &depth_range, &depths));
    for (uint32_t y = 0; y < height; ++y) {
      auto* color_row = static_cast<const uint8_t*>(colors) + y * color_layout.Footprint.RowPitch;
      auto* depth_row = reinterpret_cast<const float*>(
          static_cast<const uint8_t*>(depths) + y * depth_layout.Footprint.RowPitch);
      rgba.write(reinterpret_cast<const char*>(color_row), width * 4);
      for (uint32_t x = 0; x < width; ++x) {
        const auto* pixel = color_row + x * 4;
        image.write(reinterpret_cast<const char*>(pixel), 3);
        const auto id = uint32_t(pixel[0]) | (uint32_t(pixel[1]) << 8);
        if (id) {
          require((segment || id <= scene.items.size()) &&
                      std::isfinite(depth_row[x]) &&
                      (segment ? depth_row[x] >= 0 : depth_row[x] > 0) &&
                      depth_row[x] <= 1,
                  "invalid covered pixel/depth");
          ++covered;
          if (!segment) ++item_pixels[id - 1];
        }
      }
      depth_file.write(reinterpret_cast<const char*>(depth_row), width * sizeof(float));
    }
    color_readback->Unmap(0, &empty);
    depth_readback->Unmap(0, &empty);
    rgba.close();
    require(bool(rgba), "vegetation rgba write failed");
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
        require((segment || id <= scene.items.size()) && std::isfinite(value) &&
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
            if (!segment) ++item_pixels[id - 1];
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
  if (segment) {
    summary << "{\"schema\":\"pinyon-shift.snr04-segment.v1\","
            << "\"source_frame\":" << scene.source_frame << ','
            << "\"fixture_sha256\":\"" << scene.fixture_sha256 << "\","
            << "\"first_sequence\":" << segment->first_sequence << ','
            << "\"last_sequence\":" << segment->last_sequence << ','
            << "\"first_id\":" << segment->first_id << ','
            << "\"draws\":" << segment_draws << ','
            << "\"covered_pixels\":" << covered;
    if (alpha_probe) summary << ",\"alpha_probe\":true";
    summary << "}\n";
    summary.close();
    require(bool(summary), "vegetation segment summary write failed");
    return covered;
  }
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
    ID3D12Device* device, uint32_t samples,
    const Snr04SegmentOptions* segment) {
  const auto bytes = read(fixture);
  return RunSnr04OwnedSceneDiagnostic(bytes, vertex_shader,
                                     output_directory, device, samples, segment);
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
    ID3D12Device* borrowed_device, uint32_t samples,
    const Snr04SegmentOptions* segment) {
  require(samples == 1 || samples == 4, "unsupported procedural sample count");
  if (segment)
    require(segment->first_sequence &&
                segment->first_sequence <= segment->last_sequence &&
                segment->first_id && segment->draw_count &&
                segment->first_id + uint64_t(segment->draw_count) <= 65536,
            "invalid procedural segment");
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
  desc.SampleDesc.Count = samples;
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
                       D3D12_RESOURCE_STATE_RENDER_TARGET, color_clear, samples);
  auto depth = texture(device.Get(), depth_clear.Format,
                       D3D12_RESOURCE_FLAG_ALLOW_DEPTH_STENCIL,
                       D3D12_RESOURCE_STATE_DEPTH_WRITE, depth_clear, samples);
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
  D3D12_DEPTH_STENCIL_VIEW_DESC depth_view{};
  depth_view.Format = DXGI_FORMAT_D32_FLOAT;
  depth_view.ViewDimension = samples == 4 ? D3D12_DSV_DIMENSION_TEXTURE2DMS
                                          : D3D12_DSV_DIMENSION_TEXTURE2D;
  device->CreateDepthStencilView(depth.Get(), &depth_view,
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
  ComPtr<ID3D12Resource> color_readback, depth_readback;
  SampleCapture sample_capture;
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
    sample_capture = make_sample_capture(device.Get(), color.Get(), depth.Get());
  }
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
  auto prior = initialize_segment_targets(
      device.Get(), commands.Get(), color.Get(), depth.Get(), color_layout,
      depth_layout, rtv_handle, dsv_handle, segment, samples);
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
  uint32_t segment_draws = 0;
  for (const auto& ref : draws) {
    const auto& draw = scene.items[ref.item].draws[ref.variant];
    if (segment && (ref.sequence < segment->first_sequence ||
                    ref.sequence > segment->last_sequence)) continue;
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
    commands->SetGraphicsRoot32BitConstant(
        4, segment ? segment->first_id + segment_draws : UINT(ref.item + 1), 0);
    commands->DrawIndexedInstanced(draw.vertex_count / 4 * 6, 1, 0, 0, 0);
    ++segment_draws;
  }
  require(!segment || segment_draws == segment->draw_count,
          "procedural segment draw count mismatch");
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
  if (samples == 1) {
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
  } else {
    record_sample_capture(commands.Get(), color.Get(), depth.Get(), sample_capture);
  }
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
  uint32_t covered = 0;
  std::vector<uint32_t> item_pixels(scene.items.size());
  if (samples == 4) {
    covered = write_sample_capture(
        output_directory, sample_capture,
        segment ? segment->first_id + segment_draws - 1 : uint32_t(scene.items.size()),
        segment ? nullptr : &item_pixels);
  } else {
  std::ofstream image(output_directory / "identity.ppm", std::ios::binary);
  std::ofstream rgba(output_directory / "color.rgba", std::ios::binary);
  std::ofstream depth_file(output_directory / "depth.f32", std::ios::binary);
  image << "P6\n" << width << ' ' << height << "\n255\n";
  D3D12_RANGE color_range{0, SIZE_T(color_bytes)}, depth_range{0, SIZE_T(depth_bytes)};
  void *colors = nullptr, *depths = nullptr;
  check(color_readback->Map(0, &color_range, &colors));
  check(depth_readback->Map(0, &depth_range, &depths));
  for (uint32_t y = 0; y < height; ++y) {
    const auto* color_row = static_cast<const uint8_t*>(colors) +
                            y * color_layout.Footprint.RowPitch;
    const auto* depth_row = reinterpret_cast<const float*>(
        static_cast<const uint8_t*>(depths) + y * depth_layout.Footprint.RowPitch);
    rgba.write(reinterpret_cast<const char*>(color_row), width * 4);
    for (uint32_t x = 0; x < width; ++x) {
      const auto* pixel = color_row + x * 4;
      image.write(reinterpret_cast<const char*>(pixel), 3);
      const auto id = uint32_t(pixel[0]) | (uint32_t(pixel[1]) << 8);
      if (id) {
        require((segment || id <= scene.items.size()) &&
                    std::isfinite(depth_row[x]) &&
                    (segment ? depth_row[x] >= 0 : depth_row[x] > 0) &&
                    depth_row[x] <= 1,
                "invalid procedural identity/depth");
        ++covered;
        if (!segment) ++item_pixels[id - 1];
      }
    }
    depth_file.write(reinterpret_cast<const char*>(depth_row), width * sizeof(float));
  }
  D3D12_RANGE empty{};
  color_readback->Unmap(0, &empty);
  depth_readback->Unmap(0, &empty);
  image.close();
  rgba.close();
  depth_file.close();
  require(bool(image) && bool(rgba) && bool(depth_file) && covered > 0,
          "empty or unwritable procedural diagnostic");
  }
  const auto complete = std::chrono::steady_clock::now();
  auto us = [](auto a, auto b) {
    return std::chrono::duration_cast<std::chrono::microseconds>(b - a).count();
  };
  std::ofstream summary(output_directory / "summary.json");
  if (segment) {
    summary << "{\"schema\":\"pinyon-shift.snr04-segment.v1\","
            << "\"source_frame\":" << scene.frame << ','
            << "\"fixture_sha256\":\"" << scene.sha << "\","
            << "\"first_sequence\":" << segment->first_sequence << ','
            << "\"last_sequence\":" << segment->last_sequence << ','
            << "\"first_id\":" << segment->first_id << ','
            << "\"draws\":" << segment_draws << ','
            << "\"covered_pixels\":" << covered << "}\n";
    summary.close();
    require(bool(summary), "procedural segment summary write failed");
    return covered;
  }
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
    ID3D12Device* borrowed_device, uint32_t samples,
    const Snr04SegmentOptions* segment) {
  require(samples == 1 || samples == 4, "unsupported track sample count");
  if (segment)
    require(segment->first_sequence &&
                segment->first_sequence <= segment->last_sequence &&
                segment->first_id && segment->draw_count &&
                segment->first_id + uint64_t(segment->draw_count) <= 65536,
            "invalid track segment");
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
  desc.SampleDesc.Count = samples;
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
                       D3D12_RESOURCE_STATE_RENDER_TARGET, color_clear, samples);
  auto depth = texture(device.Get(), depth_clear.Format,
                       D3D12_RESOURCE_FLAG_ALLOW_DEPTH_STENCIL,
                       D3D12_RESOURCE_STATE_DEPTH_WRITE, depth_clear, samples);
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
  D3D12_DEPTH_STENCIL_VIEW_DESC depth_view{};
  depth_view.Format = DXGI_FORMAT_D32_FLOAT;
  depth_view.ViewDimension = samples == 4 ? D3D12_DSV_DIMENSION_TEXTURE2DMS
                                          : D3D12_DSV_DIMENSION_TEXTURE2D;
  device->CreateDepthStencilView(depth.Get(), &depth_view,
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
  ComPtr<ID3D12Resource> color_readback, depth_readback;
  SampleCapture sample_capture;
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
    sample_capture = make_sample_capture(device.Get(), color.Get(), depth.Get());
  }
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
  auto prior = initialize_segment_targets(
      device.Get(), commands.Get(), color.Get(), depth.Get(), color_layout,
      depth_layout, rtv_handle, dsv_handle, segment, samples);
  commands->OMSetRenderTargets(1, &rtv_handle, FALSE, &dsv_handle);
  D3D12_VIEWPORT viewport{0, 0, float(width), float(height), 0, 0.5f};
  D3D12_RECT scissor{0, 0, LONG(width), LONG(height)};
  commands->RSSetViewports(1, &viewport);
  commands->RSSetScissorRects(1, &scissor);
  commands->SetGraphicsRootSignature(root.Get());
  commands->IASetPrimitiveTopology(D3D_PRIMITIVE_TOPOLOGY_TRIANGLESTRIP);
  uint32_t segment_draws = 0;
  for (size_t ordinal = 0; ordinal < draws.size(); ++ordinal) {
    const auto& draw = draws[ordinal];
    if (segment && (draw.sequence < segment->first_sequence ||
                    draw.sequence > segment->last_sequence)) continue;
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
    commands->SetGraphicsRoot32BitConstant(
        4, segment ? segment->first_id + segment_draws : UINT(ordinal + 1), 0);
    commands->DrawIndexedInstanced(draw.count, 1, 0, 0, 0);
    ++segment_draws;
  }
  require(!segment || segment_draws == segment->draw_count,
          "track segment draw count mismatch");
  if (samples == 1) {
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
  } else {
    record_sample_capture(commands.Get(), color.Get(), depth.Get(), sample_capture);
  }
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
  uint32_t covered = 0;
  std::vector<uint32_t> draw_pixels(draws.size());
  if (samples == 4) {
    covered = write_sample_capture(
        output_directory, sample_capture,
        segment ? segment->first_id + segment_draws - 1 : uint32_t(draws.size()),
        segment ? nullptr : &draw_pixels);
  } else {
  std::ofstream image(output_directory / "identity.ppm", std::ios::binary);
  std::ofstream rgba(output_directory / "color.rgba", std::ios::binary);
  std::ofstream depth_file(output_directory / "depth.f32", std::ios::binary);
  image << "P6\n" << width << ' ' << height << "\n255\n";
  void *colors = nullptr, *depths = nullptr;
  D3D12_RANGE color_range{0, SIZE_T(color_bytes)}, depth_range{0, SIZE_T(depth_bytes)};
  check(color_readback->Map(0, &color_range, &colors));
  check(depth_readback->Map(0, &depth_range, &depths));
  for (uint32_t y = 0; y < height; ++y) {
    const auto* color_row = static_cast<const uint8_t*>(colors) +
                            y * color_layout.Footprint.RowPitch;
    const auto* depth_row = reinterpret_cast<const float*>(
        static_cast<const uint8_t*>(depths) + y * depth_layout.Footprint.RowPitch);
    rgba.write(reinterpret_cast<const char*>(color_row), width * 4);
    for (uint32_t x = 0; x < width; ++x) {
      const auto* pixel = color_row + x * 4;
      image.write(reinterpret_cast<const char*>(pixel), 3);
      const auto id = uint32_t(pixel[0]) | (uint32_t(pixel[1]) << 8);
      if (id) {
        require((segment || id <= draws.size()) && std::isfinite(depth_row[x]) &&
                    (segment ? depth_row[x] >= 0 : depth_row[x] > 0) &&
                    depth_row[x] <= 1,
                "invalid track identity/depth");
        ++covered;
        if (!segment) ++draw_pixels[id - 1];
      }
    }
    depth_file.write(reinterpret_cast<const char*>(depth_row), width * sizeof(float));
  }
  D3D12_RANGE empty{};
  color_readback->Unmap(0, &empty);
  depth_readback->Unmap(0, &empty);
  image.close();
  rgba.close();
  depth_file.close();
  require(bool(image) && bool(rgba) && bool(depth_file) && covered > 0,
          "empty or unwritable track diagnostic");
  }
  std::ofstream summary(output_directory / "summary.json");
  if (segment) {
    summary << "{\"schema\":\"pinyon-shift.snr04-segment.v1\","
            << "\"source_frame\":" << frame << ','
            << "\"fixture_sha256\":\"" << sha256(source) << "\","
            << "\"first_sequence\":" << segment->first_sequence << ','
            << "\"last_sequence\":" << segment->last_sequence << ','
            << "\"first_id\":" << segment->first_id << ','
            << "\"draws\":" << segment_draws << ','
            << "\"covered_pixels\":" << covered << "}\n";
    summary.close();
    require(bool(summary), "track segment summary write failed");
    return covered;
  }
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
    ID3D12Device* borrowed_device, uint32_t samples,
    const Snr04SegmentOptions* segment) {
  require(samples == 1 || samples == 4, "unsupported manager sample count");
  if (segment)
    require(segment->first_sequence &&
                segment->first_sequence <= segment->last_sequence &&
                segment->first_id && segment->draw_count &&
                segment->first_id + uint64_t(segment->draw_count) <= 65536,
            "invalid manager segment");
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
  desc.SampleDesc.Count = samples;
  ComPtr<ID3D12PipelineState> pipeline;
  check(device->CreateGraphicsPipelineState(&desc, IID_PPV_ARGS(&pipeline)));
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
  D3D12_DEPTH_STENCIL_VIEW_DESC depth_view{};
  depth_view.Format = DXGI_FORMAT_D32_FLOAT;
  depth_view.ViewDimension = samples == 4 ? D3D12_DSV_DIMENSION_TEXTURE2DMS
                                          : D3D12_DSV_DIMENSION_TEXTURE2D;
  device->CreateDepthStencilView(depth.Get(), &depth_view,
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
  ComPtr<ID3D12Resource> color_readback, depth_readback;
  SampleCapture sample_capture;
  if (samples == 1) {
    auto color_desc = color->GetDesc(), depth_desc = depth->GetDesc();
    device->GetCopyableFootprints(&color_desc, 0, 1, 0, &color_layout,
                                  nullptr, nullptr, &color_bytes);
    device->GetCopyableFootprints(&depth_desc, 0, 1, 0, &depth_layout,
                                  nullptr, nullptr, &depth_bytes);
    color_readback = buffer(device.Get(), color_bytes, D3D12_HEAP_TYPE_READBACK,
                            D3D12_RESOURCE_STATE_COPY_DEST);
    depth_readback = buffer(device.Get(), depth_bytes, D3D12_HEAP_TYPE_READBACK,
                            D3D12_RESOURCE_STATE_COPY_DEST);
  } else {
    sample_capture = make_sample_capture(device.Get(), color.Get(), depth.Get());
  }
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
  auto prior = initialize_segment_targets(
      device.Get(), commands.Get(), color.Get(), depth.Get(), color_layout,
      depth_layout, rtv_handle, dsv_handle, segment, samples);
  commands->OMSetRenderTargets(1, &rtv_handle, FALSE, &dsv_handle);
  commands->SetGraphicsRootSignature(root.Get());
  commands->IASetPrimitiveTopology(D3D_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
  uint32_t segment_draws = 0;
  for (size_t ordinal = 0; ordinal < draws.size(); ++ordinal) {
    const auto& draw = draws[ordinal];
    if (segment && (draw.sequence < segment->first_sequence ||
                    draw.sequence > segment->last_sequence)) continue;
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
    commands->SetGraphicsRoot32BitConstant(
        4, segment ? segment->first_id + segment_draws : UINT(ordinal + 1), 0);
    commands->DrawIndexedInstanced(draw.count, 1, 0, 0, 0);
    ++segment_draws;
  }
  require(!segment || segment_draws == segment->draw_count,
          "manager segment draw count mismatch");
  if (samples == 1) {
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
  } else {
    record_sample_capture(commands.Get(), color.Get(), depth.Get(), sample_capture);
  }
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
  uint32_t covered = 0;
  std::vector<uint32_t> draw_pixels(draws.size());
  if (samples == 4) {
    covered = write_sample_capture(
        output_directory, sample_capture,
        segment ? segment->first_id + segment_draws - 1 : uint32_t(draws.size()),
        segment ? nullptr : &draw_pixels);
  } else {
  std::ofstream image(output_directory / "identity.ppm", std::ios::binary);
  std::ofstream rgba(output_directory / "color.rgba", std::ios::binary);
  std::ofstream depth_file(output_directory / "depth.f32", std::ios::binary);
  image << "P6\n" << width << ' ' << height << "\n255\n";
  void *colors = nullptr, *depths = nullptr;
  D3D12_RANGE color_range{0, SIZE_T(color_bytes)}, depth_range{0, SIZE_T(depth_bytes)};
  check(color_readback->Map(0, &color_range, &colors));
  check(depth_readback->Map(0, &depth_range, &depths));
  for (uint32_t y = 0; y < height; ++y) {
    const auto* color_row = static_cast<const uint8_t*>(colors) +
                            y * color_layout.Footprint.RowPitch;
    const auto* depth_row = reinterpret_cast<const float*>(
        static_cast<const uint8_t*>(depths) + y * depth_layout.Footprint.RowPitch);
    rgba.write(reinterpret_cast<const char*>(color_row), width * 4);
    for (uint32_t x = 0; x < width; ++x) {
      const auto* pixel = color_row + x * 4;
      image.write(reinterpret_cast<const char*>(pixel), 3);
      const auto id = uint32_t(pixel[0]) | (uint32_t(pixel[1]) << 8);
      if (id) {
        require((segment || id <= draws.size()) && std::isfinite(depth_row[x]) &&
                    (segment ? depth_row[x] >= 0 : depth_row[x] > 0) &&
                    depth_row[x] <= 1,
                "invalid manager identity/depth");
        ++covered;
        if (!segment) ++draw_pixels[id - 1];
      }
    }
    depth_file.write(reinterpret_cast<const char*>(depth_row), width * sizeof(float));
  }
  D3D12_RANGE empty{};
  color_readback->Unmap(0, &empty);
  depth_readback->Unmap(0, &empty);
  image.close();
  rgba.close();
  depth_file.close();
  require(bool(image) && bool(rgba) && bool(depth_file) && covered > 0,
          "empty or unwritable manager diagnostic");
  }
  std::ofstream summary(output_directory / "summary.json");
  if (segment) {
    summary << "{\"schema\":\"pinyon-shift.snr04-segment.v1\","
            << "\"source_frame\":" << frame << ','
            << "\"fixture_sha256\":\"" << sha256(source) << "\","
            << "\"first_sequence\":" << segment->first_sequence << ','
            << "\"last_sequence\":" << segment->last_sequence << ','
            << "\"first_id\":" << segment->first_id << ','
            << "\"draws\":" << segment_draws << ','
            << "\"covered_pixels\":" << covered << "}\n";
    summary.close();
    require(bool(summary), "manager segment summary write failed");
    return covered;
  }
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

uint32_t pinyon_shift::native_renderer::RunSnr04RemainderDiagnostic(
    const std::filesystem::path& fixture,
    const std::filesystem::path& shader_directory,
    const std::filesystem::path& output_directory,
    ID3D12Device* borrowed_device, uint32_t samples,
    const Snr04SegmentOptions* segment) {
  require(samples == 1 || samples == 4, "unsupported remainder sample count");
  if (segment)
    require(segment->first_sequence &&
                segment->first_sequence <= segment->last_sequence &&
                segment->first_id && segment->draw_count &&
                segment->first_id + uint64_t(segment->draw_count) <= 65536,
            "invalid remainder segment");
  const auto source = read(fixture);
  Reader reader{source};
  require(reader.take<std::array<char, 8>>() ==
              (std::array<char, 8>{'S','N','R','0','3','R','2','\0'}),
          "wrong remainder fixture");
  const auto frame = reader.take<uint64_t>();
  const auto view = reader.take<uint32_t>();
  const auto camera = reader.take<uint32_t>();
  const auto car_count = reader.take<uint32_t>();
  const auto scalar_count = reader.take<uint32_t>();
  const auto draw_count = reader.take<uint32_t>();
  const auto vertex_count = reader.take<uint32_t>();
  const auto index_count = reader.take<uint32_t>();
  require(frame && view && camera && car_count && car_count <= 512 &&
              scalar_count && scalar_count <= 512 && draw_count &&
              draw_count <= 4096 && vertex_count && vertex_count <= 4096 &&
              index_count && index_count <= 4096,
          "unsupported remainder counts");
  reader.take<std::array<uint32_t, 32>>();  // Title camera matrices.
  std::set<uint32_t> car_keys, scalar_keys;
  for (uint32_t i = 0; i < car_count; ++i) {
    auto words = reader.take<std::array<uint32_t, 6>>();
    reader.take<uint64_t>();
    reader.take<std::array<uint32_t, 7>>();
    require(words[0] && car_keys.insert(words[0]).second,
            "duplicate car title record");
  }
  for (uint32_t i = 0; i < scalar_count; ++i) {
    reader.take<std::array<uint64_t, 2>>();
    auto words = reader.take<std::array<uint32_t, 7>>();
    require(words[0] && scalar_keys.insert(words[0]).second,
            "duplicate scalar title record");
  }
  using Range = std::pair<uint32_t, uint32_t>;
  std::map<Range, std::vector<char>> vertices, indices;
  size_t owned_bytes = 0;
  for (auto* ranges : {&vertices, &indices}) {
    const uint32_t count = ranges == &vertices ? vertex_count : index_count;
    for (uint32_t i = 0; i < count; ++i) {
      Range key{reader.take<uint32_t>(), reader.take<uint32_t>()};
      require(key.second && key.second <= (ranges == &vertices ? 3u << 20 : 128u << 10) &&
                  owned_bytes <= (32u << 20) - key.second,
              "unsupported remainder byte range");
      owned_bytes += key.second;
      require(ranges->emplace(key, reader.bytes(key.second)).second,
              "duplicate remainder byte range");
    }
  }
  struct Fetch { uint32_t constant, stride; Range range; };
  struct Draw {
    uint32_t family = 0, title_key = 0, packet = 0, count = 0;
    uint64_t sequence = 0, shader = 0, specialization = 0;
    uint32_t primitive = 0, index_type = 0, format = 0, endian = 0;
    uint32_t shader_endian = 0, restart = 0, reset_index = 0;
    std::vector<Fetch> fetches;
    Range index{};
    std::vector<uint32_t> packed;
    std::array<uint32_t, 64> system{};
    std::array<uint32_t, 192> bound_fetch{};
    uint32_t raster = 0, clip = 0, depth = 0;
    std::array<float, 6> viewport{};
    std::array<int32_t, 4> scissor{};
  };
  std::vector<Draw> draws;
  draws.reserve(draw_count);
  std::set<Range> used_vertices, used_indices;
  std::set<uint32_t> used_car, used_scalar;
  for (uint32_t i = 0; i < draw_count; ++i) {
    Draw draw{};
    draw.family = reader.take<uint32_t>();
    draw.title_key = reader.take<uint32_t>();
    draw.sequence = reader.take<uint64_t>();
    draw.packet = reader.take<uint32_t>();
    draw.shader = reader.take<uint64_t>();
    reader.take<uint64_t>();  // Pixel shader; identity target uses its own.
    draw.specialization = reader.take<uint64_t>();
    reader.take<uint64_t>();  // Dynamic state identity.
    draw.count = reader.take<uint32_t>();
    const auto guest_primitive = reader.take<uint32_t>();
    draw.primitive = reader.take<uint32_t>();
    draw.index_type = reader.take<uint32_t>();
    draw.format = reader.take<uint32_t>();
    draw.endian = reader.take<uint32_t>();
    draw.shader_endian = reader.take<uint32_t>();
    draw.restart = reader.take<uint32_t>();
    draw.reset_index = reader.take<uint32_t>();
    const auto fetch_count = reader.take<uint32_t>();
    require(fetch_count && fetch_count <= 3, "unsupported fetch count");
    for (uint32_t slot = 0; slot < fetch_count; ++slot) {
      Fetch fetch{reader.take<uint32_t>(), reader.take<uint32_t>(),
                  {reader.take<uint32_t>(), reader.take<uint32_t>()}};
      require(fetch.constant < 96 && fetch.stride &&
                  vertices.contains(fetch.range), "missing remainder fetch");
      used_vertices.insert(fetch.range);
      draw.fetches.push_back(fetch);
    }
    draw.index = {reader.take<uint32_t>(), reader.take<uint32_t>()};
    require(indices.contains(draw.index), "missing remainder indices");
    used_indices.insert(draw.index);
    const auto texture_count = reader.take<uint32_t>();
    require(texture_count <= 16, "unsupported texture count");
    for (uint32_t texture = 0; texture < texture_count; ++texture)
      reader.take<std::array<uint32_t, 9>>();  // Identity target does not sample.
    const auto bitmap = reader.take<std::array<uint64_t, 4>>();
    const auto packed_count = reader.take<uint32_t>();
    require(packed_count && packed_count <= 1024 && packed_count % 4 == 0 &&
                packed_count == 4 * (std::popcount(bitmap[0]) +
                    std::popcount(bitmap[1]) + std::popcount(bitmap[2]) +
                    std::popcount(bitmap[3])),
            "invalid remainder constants");
    draw.packed.reserve(packed_count);
    for (uint32_t word = 0; word < packed_count; ++word)
      draw.packed.push_back(reader.take<uint32_t>());
    draw.system = reader.take<std::array<uint32_t, 64>>();
    draw.bound_fetch = reader.take<std::array<uint32_t, 192>>();
    draw.raster = reader.take<uint32_t>();
    draw.clip = reader.take<uint32_t>();
    draw.depth = reader.take<uint32_t>();
    draw.viewport = reader.take<std::array<float, 6>>();
    draw.scissor = reader.take<std::array<int32_t, 4>>();
    require(draw.sequence && (!i || draw.sequence > draws.back().sequence) &&
                draw.packet && draw.shader && draw.count && draw.count <= 32768 &&
                guest_primitive == draw.primitive &&
                (draw.primitive == 4 || draw.primitive == 6) &&
                draw.index_type >= 1 && draw.index_type <= 2 &&
                draw.format <= 1 && draw.endian <= 3 &&
                draw.restart <= 1 &&
                (draw.index_type != 1 ||
                 (draw.format == 0 && draw.endian == 1) ||
                 (draw.format == 1 && draw.endian == 2)) &&
                draw.system[4] == draw.shader_endian &&
                draw.index.second >= draw.count * (draw.format ? 4u : 2u) &&
                ((draw.raster & 7) == 0 || (draw.raster & 7) == 2 ||
                 (draw.raster & 7) == 6) &&
                draw.viewport[0] == 0 && draw.viewport[1] == 0 &&
                draw.viewport[2] == width &&
                std::all_of(draw.viewport.begin(), draw.viewport.end(),
                            [](float value) { return std::isfinite(value); }) &&
                draw.viewport[4] >= 0 && draw.viewport[4] <= 1 &&
                draw.viewport[5] >= 0 && draw.viewport[5] <= 1 &&
                (draw.viewport[3] == 720 || draw.viewport[3] == 464 ||
                 draw.viewport[3] == 208) &&
                draw.scissor[0] == 0 && draw.scissor[1] == 0 &&
                draw.scissor[2] == int32_t(width) &&
                draw.scissor[3] > 0 &&
                draw.scissor[3] <= draw.viewport[3] &&
                draw.scissor[3] + height - draw.viewport[3] <= height,
            "unsupported remainder draw state");
    if (draw.family == 1) {
      require(car_keys.contains(draw.title_key), "unowned car draw");
      used_car.insert(draw.title_key);
    } else {
      require((draw.family == 2 || draw.family == 3) &&
                  scalar_keys.contains(draw.title_key) &&
                  draw.title_key == draw.packet, "unowned scalar draw");
      used_scalar.insert(draw.title_key);
    }
    for (const auto& fetch : draw.fetches) {
      require((draw.bound_fetch[fetch.constant * 2] & 3) == 3 &&
                  (draw.bound_fetch[fetch.constant * 2] & 0x1FFFFFFC) ==
                  fetch.range.first &&
                  (draw.bound_fetch[fetch.constant * 2 + 1] & 0x03FFFFFC) ==
                  fetch.range.second,
              "changed final fetch binding");
    }
    if (draw.index_type == 2) {
      require(draw.format == 1 && draw.endian == 2 &&
                  draw.shader_endian == 2 && draw.restart &&
                  draw.primitive == 6,
              "unsupported converted index mode");
    }
    draws.push_back(std::move(draw));
  }
  require(reader.position == source.size() && used_vertices.size() == vertices.size() &&
              used_indices.size() == indices.size() && used_car == car_keys &&
              used_scalar == scalar_keys,
          "incomplete remainder fixture");

  std::ifstream manifest(shader_directory / "manifest.sha256");
  require(bool(manifest), "missing remainder shader manifest");
  std::string label, fixture_digest;
  require(bool(manifest >> label >> fixture_digest) && label == "fixture" &&
              fixture_digest == sha256(source), "wrong remainder shader fixture");
  std::map<std::string, std::string> shader_digests;
  std::string digest, filename;
  while (manifest >> digest >> filename)
    require(shader_digests.emplace(filename, digest).second,
            "duplicate remainder shader digest");
  require(manifest.eof(), "invalid remainder shader manifest");
  std::map<std::pair<uint64_t, uint64_t>, std::vector<char>> shaders;
  for (const auto& draw : draws) {
    const auto key = std::pair{draw.shader, draw.specialization};
    if (shaders.contains(key)) continue;
    std::ostringstream name;
    name << "vertex_" << std::uppercase << std::hex << std::setfill('0')
         << std::setw(16) << draw.shader << '_' << std::setw(16)
         << draw.specialization << ".dxil";
    auto bytes = read(shader_directory / name.str());
    require(bytes.size() >= 4 && std::memcmp(bytes.data(), "DXBC", 4) == 0 &&
                shader_digests.contains(name.str()) &&
                sha256(bytes) == shader_digests.at(name.str()),
            "missing or changed remainder vertex shader");
    shaders.emplace(key, std::move(bytes));
  }
  require(shaders.size() == shader_digests.size(),
          "remainder shader manifest has unused entries");

  std::map<Range, uint32_t> vertex_offsets;
  std::vector<char> vertex_bytes;
  for (const auto& [range, bytes] : vertices) {
    vertex_bytes.resize((vertex_bytes.size() + 3) & ~size_t(3));
    require(vertex_bytes.size() <= 0x1FFFFFFC - bytes.size(),
            "remainder vertex buffer too large");
    vertex_offsets.emplace(range, uint32_t(vertex_bytes.size()));
    vertex_bytes.insert(vertex_bytes.end(), bytes.begin(), bytes.end());
  }
  for (auto& draw : draws) {
    for (const auto& fetch : draw.fetches) {
      auto& address = draw.bound_fetch[fetch.constant * 2];
      address = (address & 3) | vertex_offsets.at(fetch.range);
    }
  }
  using IndexKey = std::tuple<Range, uint32_t, uint32_t, uint32_t,
                              uint32_t, uint32_t>;
  std::map<IndexKey, std::vector<char>> host_indices;
  for (const auto& draw : draws) {
    IndexKey key{draw.index, draw.count, draw.index_type, draw.format,
                 draw.endian, draw.reset_index};
    if (host_indices.contains(key)) continue;
    const auto& guest = indices.at(draw.index);
    const size_t length = size_t(draw.count) * (draw.format ? 4 : 2);
    require(length <= guest.size(), "truncated remainder index stream");
    auto& host = host_indices[key];
    host.assign(guest.begin(), guest.begin() + length);
    if (draw.index_type == 2) {
      const uint32_t reset = std::byteswap(draw.reset_index);
      require((reset & 0xFF) == 0, "unsupported converted reset index");
      uint32_t resets = 0;
      for (size_t byte = 0; byte < length; byte += 4) {
        uint32_t value;
        std::memcpy(&value, guest.data() + byte, 4);
        value &= 0xFFFFFF00;
        if (value == reset) { value = UINT32_MAX; ++resets; }
        std::memcpy(host.data() + byte, &value, 4);
      }
      require(resets, "converted index stream has no restart index");
    }
  }

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
  desc.BlendState.RenderTarget[0].RenderTargetWriteMask =
      D3D12_COLOR_WRITE_ENABLE_ALL;
  desc.PrimitiveTopologyType = D3D12_PRIMITIVE_TOPOLOGY_TYPE_TRIANGLE;
  desc.NumRenderTargets = 1;
  desc.RTVFormats[0] = DXGI_FORMAT_R8G8B8A8_UNORM;
  desc.DSVFormat = DXGI_FORMAT_D32_FLOAT;
  desc.SampleDesc.Count = samples;
  using PipelineKey = std::tuple<uint64_t, uint64_t, uint32_t, uint32_t,
                                 uint32_t, uint32_t, uint32_t, uint32_t>;
  auto pipeline_key = [](const Draw& draw) -> PipelineKey {
    return {draw.shader, draw.specialization, draw.raster, draw.clip,
            draw.depth, draw.primitive, draw.format, draw.restart};
  };
  std::map<PipelineKey, ComPtr<ID3D12PipelineState>> pipelines;
  for (const auto& draw : draws) {
    auto key = pipeline_key(draw);
    if (pipelines.contains(key)) continue;
    const auto& bytes = shaders.at({draw.shader, draw.specialization});
    desc.VS = {bytes.data(), bytes.size()};
    desc.RasterizerState.CullMode = (draw.raster & 2)
        ? D3D12_CULL_MODE_BACK : D3D12_CULL_MODE_NONE;
    desc.RasterizerState.FrontCounterClockwise = (draw.raster & 4) == 0;
    desc.RasterizerState.DepthClipEnable = (draw.clip & (1u << 16)) == 0;
    desc.DepthStencilState.DepthEnable = (draw.depth & 2) != 0;
    desc.DepthStencilState.DepthWriteMask = (draw.depth & 4)
        ? D3D12_DEPTH_WRITE_MASK_ALL : D3D12_DEPTH_WRITE_MASK_ZERO;
    desc.DepthStencilState.DepthFunc = D3D12_COMPARISON_FUNC(
        uint32_t(D3D12_COMPARISON_FUNC_NEVER) + ((draw.depth >> 4) & 7));
    desc.IBStripCutValue = !draw.restart
        ? D3D12_INDEX_BUFFER_STRIP_CUT_VALUE_DISABLED
        : draw.format ? D3D12_INDEX_BUFFER_STRIP_CUT_VALUE_0xFFFFFFFF
                      : D3D12_INDEX_BUFFER_STRIP_CUT_VALUE_0xFFFF;
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
                       D3D12_RESOURCE_STATE_RENDER_TARGET, color_clear, samples);
  auto depth = texture(device.Get(), depth_clear.Format,
                       D3D12_RESOURCE_FLAG_ALLOW_DEPTH_STENCIL,
                       D3D12_RESOURCE_STATE_DEPTH_WRITE, depth_clear, samples);
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
  D3D12_DEPTH_STENCIL_VIEW_DESC depth_view{};
  depth_view.Format = DXGI_FORMAT_D32_FLOAT;
  depth_view.ViewDimension = samples == 4 ? D3D12_DSV_DIMENSION_TEXTURE2DMS
                                          : D3D12_DSV_DIMENSION_TEXTURE2D;
  device->CreateDepthStencilView(depth.Get(), &depth_view,
                                 dsv->GetCPUDescriptorHandleForHeapStart());
  auto vertex_buffer = upload(device.Get(), vertex_bytes.data(), vertex_bytes.size());
  std::map<IndexKey, ComPtr<ID3D12Resource>> index_buffers;
  for (const auto& [key, bytes] : host_indices)
    index_buffers.emplace(key, upload(device.Get(), bytes.data(), bytes.size()));
  struct Bindings { ComPtr<ID3D12Resource> b0, b1, b3; };
  std::vector<Bindings> bindings;
  bindings.reserve(draws.size());
  for (const auto& draw : draws) {
    std::array<uint32_t, 120> system{};
    std::copy(draw.system.begin(), draw.system.end(), system.begin());
    bindings.push_back({upload(device.Get(), system.data(), sizeof(system)),
                        upload(device.Get(), draw.packed.data(),
                               draw.packed.size() * sizeof(uint32_t)),
                        upload(device.Get(), draw.bound_fetch.data(),
                               sizeof(draw.bound_fetch))});
  }
  D3D12_PLACED_SUBRESOURCE_FOOTPRINT color_layout{}, depth_layout{};
  uint64_t color_bytes = 0, depth_bytes = 0;
  ComPtr<ID3D12Resource> color_readback, depth_readback;
  SampleCapture sample_capture;
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
    sample_capture = make_sample_capture(device.Get(), color.Get(), depth.Get());
  }
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
  auto prior = initialize_segment_targets(
      device.Get(), commands.Get(), color.Get(), depth.Get(), color_layout,
      depth_layout, rtv_handle, dsv_handle, segment, samples);
  commands->OMSetRenderTargets(1, &rtv_handle, FALSE, &dsv_handle);
  commands->SetGraphicsRootSignature(root.Get());
  uint32_t segment_draws = 0;
  for (size_t ordinal = 0; ordinal < draws.size(); ++ordinal) {
    const auto& draw = draws[ordinal];
    if (segment && (draw.sequence < segment->first_sequence ||
                    draw.sequence > segment->last_sequence)) continue;
    const auto& state = bindings[ordinal];
    const float tile_offset = float(height) - draw.viewport[3];
    D3D12_VIEWPORT viewport{draw.viewport[0], tile_offset,
                            draw.viewport[2], draw.viewport[3],
                            draw.viewport[4], draw.viewport[5]};
    D3D12_RECT scissor{draw.scissor[0], draw.scissor[1] + LONG(tile_offset),
                       draw.scissor[2], draw.scissor[3] + LONG(tile_offset)};
    commands->RSSetViewports(1, &viewport);
    commands->RSSetScissorRects(1, &scissor);
    commands->IASetPrimitiveTopology(draw.primitive == 4
        ? D3D_PRIMITIVE_TOPOLOGY_TRIANGLELIST
        : D3D_PRIMITIVE_TOPOLOGY_TRIANGLESTRIP);
    const IndexKey index_key{draw.index, draw.count, draw.index_type,
                             draw.format, draw.endian, draw.reset_index};
    const auto& index = index_buffers.at(index_key);
    D3D12_INDEX_BUFFER_VIEW index_view{
        index->GetGPUVirtualAddress(),
        draw.count * (draw.format ? 4u : 2u),
        draw.format ? DXGI_FORMAT_R32_UINT : DXGI_FORMAT_R16_UINT};
    commands->IASetIndexBuffer(&index_view);
    commands->SetPipelineState(pipelines.at(pipeline_key(draw)).Get());
    commands->SetGraphicsRootConstantBufferView(0, state.b0->GetGPUVirtualAddress());
    commands->SetGraphicsRootConstantBufferView(1, state.b1->GetGPUVirtualAddress());
    commands->SetGraphicsRootConstantBufferView(2, state.b3->GetGPUVirtualAddress());
    commands->SetGraphicsRootShaderResourceView(3, vertex_buffer->GetGPUVirtualAddress());
    commands->SetGraphicsRoot32BitConstant(
        4, segment ? segment->first_id + segment_draws : UINT(ordinal + 1), 0);
    commands->DrawIndexedInstanced(draw.count, 1, 0, 0, 0);
    ++segment_draws;
  }
  require(!segment || segment_draws == segment->draw_count,
          "remainder segment draw count mismatch");
  if (samples == 1) {
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
  } else {
    record_sample_capture(commands.Get(), color.Get(), depth.Get(), sample_capture);
  }
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
  require(waited == WAIT_OBJECT_0, "remainder GPU wait failed");
  check(device->GetDeviceRemovedReason());
  std::filesystem::create_directories(output_directory);
  uint32_t covered = 0;
  uint32_t zero_depth_pixels = 0;
  std::vector<uint32_t> draw_pixels(draws.size());
  if (samples == 4) {
    covered = write_sample_capture(
        output_directory, sample_capture,
        segment ? segment->first_id + segment_draws - 1 : uint32_t(draws.size()),
        segment ? nullptr : &draw_pixels, &zero_depth_pixels);
  } else {
  std::ofstream image(output_directory / "identity.ppm", std::ios::binary);
  std::ofstream rgba(output_directory / "color.rgba", std::ios::binary);
  std::ofstream depth_file(output_directory / "depth.f32", std::ios::binary);
  image << "P6\n" << width << ' ' << height << "\n255\n";
  void *colors = nullptr, *depths = nullptr;
  D3D12_RANGE color_range{0, SIZE_T(color_bytes)}, depth_range{0, SIZE_T(depth_bytes)};
  check(color_readback->Map(0, &color_range, &colors));
  check(depth_readback->Map(0, &depth_range, &depths));
  for (uint32_t y = 0; y < height; ++y) {
    const auto* color_row = static_cast<const uint8_t*>(colors) +
                            y * color_layout.Footprint.RowPitch;
    const auto* depth_row = reinterpret_cast<const float*>(
        static_cast<const uint8_t*>(depths) + y * depth_layout.Footprint.RowPitch);
    rgba.write(reinterpret_cast<const char*>(color_row), width * 4);
    for (uint32_t x = 0; x < width; ++x) {
      const auto* pixel = color_row + x * 4;
      image.write(reinterpret_cast<const char*>(pixel), 3);
      const auto id = uint32_t(pixel[0]) | (uint32_t(pixel[1]) << 8);
      if (id) {
        if ((!segment && id > draws.size()) || !std::isfinite(depth_row[x]) ||
            depth_row[x] < 0 || depth_row[x] > 1)
          throw std::runtime_error("invalid remainder pixel " +
              std::to_string(x) + "," + std::to_string(y) + " id=" +
              std::to_string(id) + " depth=" + std::to_string(depth_row[x]));
        ++covered;
        zero_depth_pixels += depth_row[x] == 0;
        if (!segment) ++draw_pixels[id - 1];
      }
    }
    depth_file.write(reinterpret_cast<const char*>(depth_row), width * sizeof(float));
  }
  D3D12_RANGE empty{};
  color_readback->Unmap(0, &empty);
  depth_readback->Unmap(0, &empty);
  image.close();
  rgba.close();
  depth_file.close();
  require(bool(image) && bool(rgba) && bool(depth_file) && covered > 0,
          "empty or unwritable remainder diagnostic");
  }
  std::ofstream summary(output_directory / "summary.json");
  if (segment) {
    summary << "{\"schema\":\"pinyon-shift.snr04-segment.v1\","
            << "\"source_frame\":" << frame << ','
            << "\"fixture_sha256\":\"" << sha256(source) << "\","
            << "\"first_sequence\":" << segment->first_sequence << ','
            << "\"last_sequence\":" << segment->last_sequence << ','
            << "\"first_id\":" << segment->first_id << ','
            << "\"draws\":" << segment_draws << ','
            << "\"covered_pixels\":" << covered << ','
            << "\"zero_depth_pixels\":" << zero_depth_pixels << "}\n";
    summary.close();
    require(bool(summary), "remainder segment summary write failed");
    return covered;
  }
  summary << "{\"schema\":\"pinyon-shift.snr04-remainder.v1\","
          << "\"source_frame\":" << frame << ','
          << "\"fixture_sha256\":\"" << sha256(source) << "\","
          << "\"width\":" << width << ",\"height\":" << height << ','
          << "\"draws\":" << draws.size() << ','
          << "\"shaders\":" << shaders.size() << ','
          << "\"vertex_bytes\":" << vertex_bytes.size() << ','
          << "\"covered_pixels\":" << covered << ','
          << "\"zero_depth_pixels\":" << zero_depth_pixels << ','
          << "\"visible_draws\":"
          << std::count_if(draw_pixels.begin(), draw_pixels.end(),
                           [](uint32_t value) { return value != 0; }) << ','
          << "\"draw_pixels\":[";
  for (size_t i = 0; i < draws.size(); ++i) {
    if (i) summary << ',';
    summary << "{\"sequence\":" << draws[i].sequence
            << ",\"packet\":" << draws[i].packet
            << ",\"family\":" << draws[i].family
            << ",\"pixels\":" << draw_pixels[i] << '}';
  }
  summary << "]}\n";
  summary.close();
  require(bool(summary), "remainder summary write failed");
  return covered;
}
