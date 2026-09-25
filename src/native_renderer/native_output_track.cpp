#include "native_renderer/native_output_track.h"

#include <d3d12.h>
#include <d3dcompiler.h>
#include <wrl/client.h>

#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstring>
#include <deque>
#include <map>
#include <stdexcept>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

#include <rex/graphics/d3d12/deferred_command_list.h>
#include <rex/logging.h>
#include <rex/system/interfaces/graphics.h>

#include "native_renderer/snr04_owned_scene_diagnostic.h"

namespace pinyon_shift::native_renderer {
namespace {
using Microsoft::WRL::ComPtr;
using PipelineKey = std::tuple<uint64_t, uint64_t, uint32_t, uint32_t, uint32_t,
    bool>;
using RemainderPipelineKey = std::tuple<uint64_t, uint64_t, uint32_t,
    uint32_t, uint32_t, uint32_t, uint32_t, uint32_t>;

struct UploadArena {
  std::vector<uint8_t> bytes;

  uint64_t Add(const void* source, size_t size) {
    const size_t offset = (bytes.size() + 255) & ~size_t(255);
    if (offset > 64 * 1024 * 1024 ||
        size > 64 * 1024 * 1024 - offset)
      throw std::runtime_error("native track upload exceeds 64 MiB");
    bytes.resize(offset + size);
    std::memcpy(bytes.data() + offset, source, size);
    return offset;
  }
};

struct TrackFrame {
  ComPtr<ID3D12Resource> upload, depth, color, hud;
  ComPtr<ID3D12DescriptorHeap> rtv, dsv, srv, materials;
  std::vector<ComPtr<ID3D12Resource>> material_resources;
};

struct TrackDrawBinding {
  PipelineKey pipeline;
  uint64_t vertex = 0, index = 0, b0 = 0, b1 = 0, b3 = 0;
  uint32_t material_index = UINT32_MAX;
  D3D12_VIEWPORT viewport{};
  D3D12_RECT scissor{};
};

struct ItemDrawBinding {
  uint64_t sequence = 0, shader = 0, specialization = 0;
  uint32_t count = 0;
  uint64_t vertex = 0, b0 = 0, b1 = 0, b3 = 0;
};

struct RemainderDrawBinding {
  RemainderPipelineKey pipeline;
  uint64_t index = 0, b0 = 0, b1 = 0, b3 = 0;
  uint32_t count = 0, index_bytes = 0, format = 0, primitive = 0;
  uint32_t family = 0;
  D3D12_VIEWPORT viewport{};
  D3D12_RECT scissor{};
};

struct TrackGraphics {
  ComPtr<ID3D12Device> device;
  ComPtr<ID3D12RootSignature> root;
  ComPtr<ID3DBlob> pixel, pixel_textured;
  ComPtr<ID3D12RootSignature> blit_root;
  ComPtr<ID3D12PipelineState> blit_pipeline;
  std::map<PipelineKey, ComPtr<ID3D12PipelineState>> pipelines;
  std::map<std::pair<uint64_t, uint64_t>, ComPtr<ID3D12PipelineState>> item_pipelines;
  std::map<RemainderPipelineKey, ComPtr<ID3D12PipelineState>> remainder_pipelines;
  std::deque<std::pair<uint64_t, TrackFrame>> submitted;

  bool Ready(ID3D12Device* current) {
    if (device.Get() != current) {
      submitted.clear();
      pipelines.clear();
      item_pipelines.clear();
      remainder_pipelines.clear();
      root.Reset();
      pixel.Reset();
      pixel_textured.Reset();
      blit_root.Reset();
      blit_pipeline.Reset();
      device = current;
    }
    if (root && pixel && pixel_textured) return true;
    constexpr char shader[] =
        "cbuffer Color : register(b2) { float4 flat; };"
        "float4 main() : SV_Target0 { return flat; }";
    ComPtr<ID3DBlob> errors, serialized;
    if (FAILED(D3DCompile(shader, sizeof(shader) - 1, nullptr, nullptr,
                          nullptr, "main", "ps_5_1", 0, 0, &pixel, &errors)))
      return false;
    constexpr char textured_shader[] =
        "Texture2D<float4> albedo : register(t1);"
        "SamplerState linear_wrap : register(s0);"
        "float4 main(float4 uv[5] : TEXCOORD0) : SV_Target0 {"
        " return float4(albedo.Sample(linear_wrap, uv[4].xy).rgb, 1); }";
    if (FAILED(D3DCompile(textured_shader, sizeof(textured_shader) - 1,
                          nullptr, nullptr, nullptr, "main", "ps_5_1", 0, 0,
                          &pixel_textured, &errors)))
      return false;
    D3D12_ROOT_PARAMETER parameters[7]{};
    for (uint32_t i = 0; i < 4; ++i) {
      parameters[i].ParameterType = i == 3 ? D3D12_ROOT_PARAMETER_TYPE_SRV
                                           : D3D12_ROOT_PARAMETER_TYPE_CBV;
      parameters[i].Descriptor.ShaderRegister = i == 2 ? 3 : i == 3 ? 0 : i;
      parameters[i].ShaderVisibility = D3D12_SHADER_VISIBILITY_VERTEX;
    }
    parameters[4].ParameterType = D3D12_ROOT_PARAMETER_TYPE_32BIT_CONSTANTS;
    parameters[4].Constants.ShaderRegister = 2;
    parameters[4].Constants.Num32BitValues = 4;
    parameters[4].ShaderVisibility = D3D12_SHADER_VISIBILITY_PIXEL;
    parameters[5].ParameterType = D3D12_ROOT_PARAMETER_TYPE_UAV;
    parameters[5].Descriptor.ShaderRegister = 0;
    parameters[5].ShaderVisibility = D3D12_SHADER_VISIBILITY_VERTEX;
    D3D12_DESCRIPTOR_RANGE material_range{};
    material_range.RangeType = D3D12_DESCRIPTOR_RANGE_TYPE_SRV;
    material_range.NumDescriptors = 1;
    material_range.BaseShaderRegister = 1;
    parameters[6].ParameterType = D3D12_ROOT_PARAMETER_TYPE_DESCRIPTOR_TABLE;
    parameters[6].DescriptorTable = {1, &material_range};
    parameters[6].ShaderVisibility = D3D12_SHADER_VISIBILITY_PIXEL;
    D3D12_STATIC_SAMPLER_DESC sampler{};
    sampler.Filter = D3D12_FILTER_MIN_MAG_MIP_LINEAR;
    sampler.AddressU = D3D12_TEXTURE_ADDRESS_MODE_WRAP;
    sampler.AddressV = D3D12_TEXTURE_ADDRESS_MODE_WRAP;
    sampler.AddressW = D3D12_TEXTURE_ADDRESS_MODE_WRAP;
    sampler.MaxAnisotropy = 1;
    sampler.ComparisonFunc = D3D12_COMPARISON_FUNC_NEVER;
    sampler.MaxLOD = D3D12_FLOAT32_MAX;
    sampler.ShaderVisibility = D3D12_SHADER_VISIBILITY_PIXEL;
    D3D12_ROOT_SIGNATURE_DESC description{
        7, parameters, 1, &sampler,
        D3D12_ROOT_SIGNATURE_FLAG_ALLOW_INPUT_ASSEMBLER_INPUT_LAYOUT};
    if (FAILED(D3D12SerializeRootSignature(
            &description, D3D_ROOT_SIGNATURE_VERSION_1, &serialized,
            &errors)))
      return false;
    return SUCCEEDED(device->CreateRootSignature(
        0, serialized->GetBufferPointer(), serialized->GetBufferSize(),
        IID_PPV_ARGS(&root)));
  }

  bool Pipeline(const rex::system::NativeGuestOutputRenderContext& context,
                const Snr04TrackDraw& draw) {
    const bool textured = draw.pixel_shader == 0x6F7CDE74CDACCB08ull &&
        draw.shader == 0x07425D208E8BD688ull &&
        draw.specialization == 0x7Full;
    const PipelineKey key{draw.shader, draw.specialization, draw.raster_mode,
                          draw.clip_control, draw.depth_control, textured};
    if (pipelines.contains(key)) return true;
    const uint8_t* vertex = nullptr;
    size_t vertex_size = 0;
    if (!context.shader ||
        !context.shader(context, 0, draw.shader, draw.specialization,
                        &vertex, &vertex_size) ||
        !vertex || vertex_size < 4 || std::memcmp(vertex, "DXBC", 4))
      return false;
    D3D12_GRAPHICS_PIPELINE_STATE_DESC description{};
    description.pRootSignature = root.Get();
    description.VS = {vertex, vertex_size};
    ID3DBlob* fragment = textured ? pixel_textured.Get() : pixel.Get();
    description.PS = {fragment->GetBufferPointer(), fragment->GetBufferSize()};
    description.BlendState.RenderTarget[0].RenderTargetWriteMask =
        D3D12_COLOR_WRITE_ENABLE_ALL;
    description.SampleMask = UINT_MAX;
    description.RasterizerState.FillMode = D3D12_FILL_MODE_SOLID;
    description.RasterizerState.CullMode = (draw.raster_mode & 2)
        ? D3D12_CULL_MODE_BACK : D3D12_CULL_MODE_NONE;
    description.RasterizerState.FrontCounterClockwise =
        (draw.raster_mode & 4) == 0;
    description.RasterizerState.DepthClipEnable =
        (draw.clip_control & (1u << 16)) == 0;
    description.DepthStencilState.DepthEnable =
        (draw.depth_control & 2) != 0;
    description.DepthStencilState.DepthWriteMask = (draw.depth_control & 4)
        ? D3D12_DEPTH_WRITE_MASK_ALL : D3D12_DEPTH_WRITE_MASK_ZERO;
    description.DepthStencilState.DepthFunc = D3D12_COMPARISON_FUNC(
        uint32_t(D3D12_COMPARISON_FUNC_NEVER) +
        ((draw.depth_control >> 4) & 7));
    description.PrimitiveTopologyType = D3D12_PRIMITIVE_TOPOLOGY_TYPE_TRIANGLE;
    description.IBStripCutValue = D3D12_INDEX_BUFFER_STRIP_CUT_VALUE_0xFFFF;
    description.NumRenderTargets = 1;
    description.RTVFormats[0] = DXGI_FORMAT_R10G10B10A2_UNORM;
    description.DSVFormat = DXGI_FORMAT_D32_FLOAT;
    description.SampleDesc.Count = 1;
    ComPtr<ID3D12PipelineState> pipeline;
    const HRESULT pipeline_result = device->CreateGraphicsPipelineState(
        &description, IID_PPV_ARGS(&pipeline));
    if (FAILED(pipeline_result)) {
      REXGPU_INFO("FH1 native track pipeline rejected shader={:016X} "
                  "specialization={:X} textured={} hresult={:08X}",
                  draw.shader, draw.specialization, textured,
                  uint32_t(pipeline_result));
      return false;
    }
    pipelines.emplace(key, std::move(pipeline));
    return true;
  }

  bool ItemPipeline(const rex::system::NativeGuestOutputRenderContext& context,
                    uint64_t hash, uint64_t specialization) {
    const auto key = std::pair{hash, specialization};
    if (item_pipelines.contains(key)) return true;
    const uint8_t* vertex = nullptr;
    size_t size = 0;
    if (!context.shader ||
        !context.shader(context, 0, hash, specialization, &vertex, &size) ||
        !vertex || size < 4 || std::memcmp(vertex, "DXBC", 4))
      return false;
    D3D12_GRAPHICS_PIPELINE_STATE_DESC desc{};
    desc.pRootSignature = root.Get();
    desc.VS = {vertex, size};
    desc.PS = {pixel->GetBufferPointer(), pixel->GetBufferSize()};
    desc.BlendState.RenderTarget[0].RenderTargetWriteMask =
        D3D12_COLOR_WRITE_ENABLE_ALL;
    desc.SampleMask = UINT_MAX;
    desc.RasterizerState.FillMode = D3D12_FILL_MODE_SOLID;
    desc.RasterizerState.CullMode = D3D12_CULL_MODE_NONE;
    desc.RasterizerState.DepthClipEnable = TRUE;
    desc.DepthStencilState.DepthEnable = TRUE;
    desc.DepthStencilState.DepthWriteMask = D3D12_DEPTH_WRITE_MASK_ALL;
    desc.DepthStencilState.DepthFunc = D3D12_COMPARISON_FUNC_GREATER_EQUAL;
    desc.PrimitiveTopologyType = D3D12_PRIMITIVE_TOPOLOGY_TYPE_TRIANGLE;
    desc.NumRenderTargets = 1;
    desc.RTVFormats[0] = DXGI_FORMAT_R10G10B10A2_UNORM;
    desc.DSVFormat = DXGI_FORMAT_D32_FLOAT;
    desc.SampleDesc.Count = 1;
    ComPtr<ID3D12PipelineState> pipeline;
    if (FAILED(device->CreateGraphicsPipelineState(&desc,
                                                  IID_PPV_ARGS(&pipeline))))
      return false;
    item_pipelines.emplace(key, std::move(pipeline));
    return true;
  }

  bool RemainderPipeline(
      const rex::system::NativeGuestOutputRenderContext& context,
      const Snr04RemainderDraw& draw) {
    const RemainderPipelineKey key{
        draw.shader, draw.specialization, draw.raster, draw.clip,
        draw.depth, draw.primitive, draw.format, draw.restart};
    if (remainder_pipelines.contains(key)) return true;
    const uint8_t* vertex = nullptr;
    size_t size = 0;
    if (!context.shader ||
        !context.shader(context, 0, draw.shader, draw.specialization,
                        &vertex, &size) ||
        !vertex || size < 4 || std::memcmp(vertex, "DXBC", 4))
      return false;
    D3D12_GRAPHICS_PIPELINE_STATE_DESC desc{};
    desc.pRootSignature = root.Get();
    desc.VS = {vertex, size};
    desc.PS = {pixel->GetBufferPointer(), pixel->GetBufferSize()};
    desc.BlendState.RenderTarget[0].RenderTargetWriteMask =
        D3D12_COLOR_WRITE_ENABLE_ALL;
    desc.SampleMask = UINT_MAX;
    desc.RasterizerState.FillMode = D3D12_FILL_MODE_SOLID;
    desc.RasterizerState.CullMode = (draw.raster & 2)
        ? D3D12_CULL_MODE_BACK : D3D12_CULL_MODE_NONE;
    desc.RasterizerState.FrontCounterClockwise = (draw.raster & 4) == 0;
    desc.RasterizerState.DepthClipEnable =
        (draw.clip & (1u << 16)) == 0;
    desc.DepthStencilState.DepthEnable = (draw.depth & 2) != 0;
    desc.DepthStencilState.DepthWriteMask = (draw.depth & 4)
        ? D3D12_DEPTH_WRITE_MASK_ALL : D3D12_DEPTH_WRITE_MASK_ZERO;
    desc.DepthStencilState.DepthFunc = D3D12_COMPARISON_FUNC(
        uint32_t(D3D12_COMPARISON_FUNC_NEVER) + ((draw.depth >> 4) & 7));
    desc.IBStripCutValue = !draw.restart
        ? D3D12_INDEX_BUFFER_STRIP_CUT_VALUE_DISABLED
        : draw.format ? D3D12_INDEX_BUFFER_STRIP_CUT_VALUE_0xFFFFFFFF
                      : D3D12_INDEX_BUFFER_STRIP_CUT_VALUE_0xFFFF;
    desc.PrimitiveTopologyType = D3D12_PRIMITIVE_TOPOLOGY_TYPE_TRIANGLE;
    desc.NumRenderTargets = 1;
    desc.RTVFormats[0] = DXGI_FORMAT_R10G10B10A2_UNORM;
    desc.DSVFormat = DXGI_FORMAT_D32_FLOAT;
    desc.SampleDesc.Count = 1;
    ComPtr<ID3D12PipelineState> pipeline;
    if (FAILED(device->CreateGraphicsPipelineState(&desc,
                                                  IID_PPV_ARGS(&pipeline))))
      return false;
    remainder_pipelines.emplace(key, std::move(pipeline));
    return true;
  }

  bool BlitReady() {
    if (blit_pipeline) return true;
    constexpr char vertex[] =
        "float4 main(uint id : SV_VertexID) : SV_Position {"
        " float2 p[3] = {float2(-1,-1),float2(-1,3),float2(3,-1)};"
        " return float4(p[id],0,1); }";
    constexpr char fragment[] =
        "Texture2D<float4> scene : register(t0);"
        "Texture2D<float4> guest : register(t1);"
        "float4 main(float4 p : SV_Position) : SV_Target0 {"
        " float2 q=p.xy;"
        " float4 s=scene.Load(int3(1279-int(q.x),719-int(q.y),0));"
        " float4 g=guest.Load(int3(int(q.x),int(q.y),0));"
        " float lo=min(g.r,min(g.g,g.b));"
        " float white=(lo>0.78)?1:0;"
        " float text=(q.x>55 && q.x<255 && q.y>22 && q.y<90)?white:0;"
        " text=max(text,(q.x>1015 && q.x<1240 && q.y>20 && q.y<90)?white:0);"
        " text=max(text,(q.x>1000 && q.y>=105 && q.y<230)?1:0);"
        " text=max(text,(q.x>60 && q.x<225 && q.y>107 && q.y<138)?1:0);"
        " float map=1-smoothstep(68,78,length(q-float2(135,540)));"
        " float speed=1-smoothstep(96,108,length(q-float2(1128,592)));"
        " return lerp(s,g,max(text,max(map,speed))); }";
    ComPtr<ID3DBlob> vs, ps, errors, serialized;
    if (FAILED(D3DCompile(vertex, sizeof(vertex) - 1, nullptr, nullptr,
                          nullptr, "main", "vs_5_1", 0, 0, &vs, &errors)) ||
        FAILED(D3DCompile(fragment, sizeof(fragment) - 1, nullptr, nullptr,
                          nullptr, "main", "ps_5_1", 0, 0, &ps, &errors)))
      return false;
    D3D12_DESCRIPTOR_RANGE range{};
    range.RangeType = D3D12_DESCRIPTOR_RANGE_TYPE_SRV;
    range.NumDescriptors = 2;
    D3D12_ROOT_PARAMETER parameter{};
    parameter.ParameterType = D3D12_ROOT_PARAMETER_TYPE_DESCRIPTOR_TABLE;
    parameter.DescriptorTable = {1, &range};
    parameter.ShaderVisibility = D3D12_SHADER_VISIBILITY_PIXEL;
    D3D12_ROOT_SIGNATURE_DESC root_desc{
        1, &parameter, 0, nullptr,
        D3D12_ROOT_SIGNATURE_FLAG_ALLOW_INPUT_ASSEMBLER_INPUT_LAYOUT};
    if (FAILED(D3D12SerializeRootSignature(
            &root_desc, D3D_ROOT_SIGNATURE_VERSION_1,
            &serialized, &errors)) ||
        FAILED(device->CreateRootSignature(
            0, serialized->GetBufferPointer(), serialized->GetBufferSize(),
            IID_PPV_ARGS(&blit_root))))
      return false;
    D3D12_GRAPHICS_PIPELINE_STATE_DESC desc{};
    desc.pRootSignature = blit_root.Get();
    desc.VS = {vs->GetBufferPointer(), vs->GetBufferSize()};
    desc.PS = {ps->GetBufferPointer(), ps->GetBufferSize()};
    desc.BlendState.RenderTarget[0].RenderTargetWriteMask =
        D3D12_COLOR_WRITE_ENABLE_ALL;
    desc.SampleMask = UINT_MAX;
    desc.RasterizerState.FillMode = D3D12_FILL_MODE_SOLID;
    desc.RasterizerState.CullMode = D3D12_CULL_MODE_NONE;
    desc.PrimitiveTopologyType = D3D12_PRIMITIVE_TOPOLOGY_TYPE_TRIANGLE;
    desc.NumRenderTargets = 1;
    desc.RTVFormats[0] = DXGI_FORMAT_R10G10B10A2_UNORM;
    desc.SampleDesc.Count = 1;
    return SUCCEEDED(device->CreateGraphicsPipelineState(
        &desc, IID_PPV_ARGS(&blit_pipeline)));
  }
};

bool PrepareItems(const rex::system::NativeGuestOutputRenderContext& context,
                  const Snr04ProceduralScene& scene, TrackGraphics& graphics,
                  UploadArena& arena, std::vector<ItemDrawBinding>& bindings,
                  uint64_t& index_offset, uint32_t& index_bytes) {
  if (scene.character || scene.items.empty() || scene.items.size() > 512)
    return false;
  uint32_t max_vertices = 0;
  for (const auto& item : scene.items)
    for (const auto& draw : item.draws)
      max_vertices = (std::max)(max_vertices, draw.vertex_count);
  if (!max_vertices || max_vertices > UINT16_MAX || max_vertices % 4)
    return false;
  std::vector<uint16_t> indices;
  indices.reserve(max_vertices / 4 * 6);
  for (uint32_t first = 0; first < max_vertices; first += 4)
    for (uint32_t corner : {0u, 1u, 3u, 1u, 2u, 3u})
      indices.push_back(uint16_t(first + corner));
  index_bytes = uint32_t(indices.size() * sizeof(uint16_t));
  index_offset = arena.Add(indices.data(), index_bytes);
  for (const auto& item : scene.items) {
    if (item.vertices.empty() || item.constants.empty() ||
        item.draws.empty() || item.fetch[2] > 3)
      return false;
    const auto vertex = arena.Add(item.vertices.data(), item.vertices.size());
    const auto b1 = arena.Add(item.constants.data(),
                              item.constants.size() * sizeof(uint32_t));
    std::array<uint32_t, 192> fetch{};
    std::copy(item.fetch.begin(), item.fetch.end(), fetch.begin() + 188);
    const auto b3 = arena.Add(fetch.data(), sizeof(fetch));
    for (const auto& draw : item.draws) {
      const bool known_shader =
          draw.vertex_shader == 0x3BC346726C1C2535ull ||
          draw.vertex_shader == 0xBDFD2AD68464101Aull ||
          draw.vertex_shader == 0xCB8AC98467C0C283ull ||
          draw.vertex_shader == 0xA715C815EDB8EEE8ull;
      const uint64_t specialization =
          draw.vertex_shader == 0xCB8AC98467C0C283ull ||
          draw.vertex_shader == 0xA715C815EDB8EEE8ull ? 127 : 15;
      if (!known_shader || !draw.sequence || !draw.vertex_count ||
          draw.vertex_count % 4 ||
          draw.vertex_count * 10 != item.vertices.size() ||
          !graphics.ItemPipeline(context, draw.vertex_shader, specialization))
        return false;
      std::array<uint32_t, 120> system{};
      std::copy(draw.system.begin(), draw.system.end(), system.begin());
      system[33] = std::bit_cast<uint32_t>(1.f);
      system[37] = std::bit_cast<uint32_t>(-1.f / 720.f);
      bindings.push_back({draw.sequence, draw.vertex_shader, specialization,
                          draw.vertex_count / 4 * 6, vertex,
                          arena.Add(system.data(), sizeof(system)), b1, b3});
    }
  }
  std::sort(bindings.begin(), bindings.end(),
            [](const auto& a, const auto& b) { return a.sequence < b.sequence; });
  for (size_t i = 1; i < bindings.size(); ++i)
    if (bindings[i - 1].sequence == bindings[i].sequence) return false;
  return !bindings.empty();
}

bool PrepareVegetation(
    const rex::system::NativeGuestOutputRenderContext& context,
    const Snr04VegetationScene& scene, TrackGraphics& graphics,
    UploadArena& arena, std::vector<ItemDrawBinding>& bindings,
    uint64_t& index_offset, uint32_t& index_bytes) {
  constexpr uint64_t shader = 0x5834939992FFC765ull;
  if (!scene.sequenced || scene.items.empty() || scene.items.size() > 512 ||
      !graphics.ItemPipeline(context, shader, 31))
    return false;
  uint32_t max_vertices = 0;
  for (const auto& item : scene.items)
    max_vertices = (std::max)(max_vertices, item.vertex_count);
  if (!max_vertices || max_vertices > UINT16_MAX || max_vertices % 4)
    return false;
  std::vector<uint16_t> indices;
  indices.reserve(max_vertices / 4 * 6);
  for (uint32_t first = 0; first < max_vertices; first += 4)
    for (uint32_t corner : {0u, 1u, 3u, 1u, 2u, 3u})
      indices.push_back(uint16_t(first + corner));
  index_bytes = uint32_t(indices.size() * sizeof(uint16_t));
  index_offset = arena.Add(indices.data(), index_bytes);
  for (const auto& item : scene.items) {
    if (!item.vertex_count || item.vertex_count % 4 ||
        item.vertices.size() != item.vertex_count * 4 ||
        item.variants.empty() || item.fetch[2] > 3)
      return false;
    const auto vertex = arena.Add(item.vertices.data(), item.vertices.size());
    std::array<uint32_t, 192> fetch{};
    std::copy(item.fetch.begin(), item.fetch.end(), fetch.begin() + 188);
    const auto b3 = arena.Add(fetch.data(), sizeof(fetch));
    for (const auto& variant : item.variants) {
      if (!variant.sequence) return false;
      std::array<uint32_t, 120> system{};
      std::copy(variant.system.begin(), variant.system.end(), system.begin());
      bindings.push_back({variant.sequence, shader, 31,
                          item.vertex_count / 4 * 6, vertex,
                          arena.Add(system.data(), sizeof(system)),
                          arena.Add(variant.vertex_constants.data(), 23 * 16),
                          b3});
    }
  }
  std::sort(bindings.begin(), bindings.end(),
            [](const auto& a, const auto& b) { return a.sequence < b.sequence; });
  for (size_t i = 1; i < bindings.size(); ++i)
    if (bindings[i - 1].sequence == bindings[i].sequence) return false;
  return !bindings.empty();
}

bool PrepareRemainder(
    const rex::system::NativeGuestOutputRenderContext& context,
    const Snr04RemainderScene& scene, TrackGraphics& graphics,
    UploadArena& arena, std::vector<RemainderDrawBinding>& bindings,
    uint64_t& vertex_offset) {
  if (scene.vertex_bytes.empty() || scene.draws.empty() ||
      scene.host_indices.empty())
    return false;
  vertex_offset = arena.Add(scene.vertex_bytes.data(), scene.vertex_bytes.size());
  std::map<Snr04RemainderIndexKey, uint64_t> indices;
  for (const auto& [key, bytes] : scene.host_indices)
    indices.emplace(key, arena.Add(bytes.data(), bytes.size()));
  bindings.reserve(scene.draws.size());
  for (const auto& draw : scene.draws) {
    if (!graphics.RemainderPipeline(context, draw))
      throw std::runtime_error("unsupported remainder shader " +
                               std::to_string(draw.shader));
    const float tile_offset = 720.f - draw.viewport[3];
    if (tile_offset < 0 || tile_offset != std::floor(tile_offset) ||
        draw.viewport[0] != 0 || draw.viewport[1] != 0 ||
        draw.viewport[2] != 1280 || draw.scissor[0] != 0 ||
        draw.scissor[1] != 0 || draw.scissor[2] != 1280 ||
        draw.scissor[3] > draw.viewport[3] ||
        tile_offset + draw.scissor[3] > 720)
      return false;
    const Snr04RemainderIndexKey index_key{
        draw.index, draw.count, draw.index_type, draw.format,
        draw.endian, draw.reset_index};
    const auto& bytes = scene.host_indices.at(index_key);
    RemainderDrawBinding binding;
    binding.pipeline = {draw.shader, draw.specialization, draw.raster,
                        draw.clip, draw.depth, draw.primitive, draw.format,
                        draw.restart};
    binding.index = indices.at(index_key);
    binding.index_bytes = uint32_t(bytes.size());
    binding.count = draw.count;
    binding.format = draw.format;
    binding.primitive = draw.primitive;
    binding.family = draw.family;
    std::array<uint32_t, 120> system{};
    std::copy(draw.system.begin(), draw.system.end(), system.begin());
    binding.b0 = arena.Add(system.data(), sizeof(system));
    binding.b1 = arena.Add(draw.packed.data(),
                           draw.packed.size() * sizeof(uint32_t));
    binding.b3 = arena.Add(draw.bound_fetch.data(),
                           sizeof(draw.bound_fetch));
    binding.viewport = {draw.viewport[0], tile_offset, draw.viewport[2],
                        draw.viewport[3], draw.viewport[4], draw.viewport[5]};
    binding.scissor = {draw.scissor[0], LONG(draw.scissor[1] + tile_offset),
                       draw.scissor[2], LONG(draw.scissor[3] + tile_offset)};
    bindings.push_back(binding);
  }
  return true;
}

bool CreateFrame(ID3D12Device* device, ID3D12Resource* output,
                 const UploadArena& arena, TrackFrame& frame) {
  D3D12_HEAP_PROPERTIES upload_heap{};
  upload_heap.Type = D3D12_HEAP_TYPE_UPLOAD;
  D3D12_RESOURCE_DESC upload_desc{};
  upload_desc.Dimension = D3D12_RESOURCE_DIMENSION_BUFFER;
  upload_desc.Width = arena.bytes.size();
  upload_desc.Height = 1;
  upload_desc.DepthOrArraySize = 1;
  upload_desc.MipLevels = 1;
  upload_desc.SampleDesc.Count = 1;
  upload_desc.Layout = D3D12_TEXTURE_LAYOUT_ROW_MAJOR;
  if (FAILED(device->CreateCommittedResource(
          &upload_heap, D3D12_HEAP_FLAG_NONE, &upload_desc,
          D3D12_RESOURCE_STATE_GENERIC_READ, nullptr,
          IID_PPV_ARGS(&frame.upload))))
    return false;
  void* mapped = nullptr;
  if (FAILED(frame.upload->Map(0, nullptr, &mapped))) return false;
  std::memcpy(mapped, arena.bytes.data(), arena.bytes.size());
  frame.upload->Unmap(0, nullptr);

  D3D12_HEAP_PROPERTIES default_heap{};
  default_heap.Type = D3D12_HEAP_TYPE_DEFAULT;
  D3D12_RESOURCE_DESC color_desc{};
  color_desc.Dimension = D3D12_RESOURCE_DIMENSION_TEXTURE2D;
  color_desc.Width = 1280;
  color_desc.Height = 720;
  color_desc.DepthOrArraySize = 1;
  color_desc.MipLevels = 1;
  color_desc.Format = DXGI_FORMAT_R10G10B10A2_UNORM;
  color_desc.SampleDesc.Count = 1;
  color_desc.Flags = D3D12_RESOURCE_FLAG_ALLOW_RENDER_TARGET;
  if (FAILED(device->CreateCommittedResource(
          &default_heap, D3D12_HEAP_FLAG_NONE, &color_desc,
          D3D12_RESOURCE_STATE_RENDER_TARGET, nullptr,
          IID_PPV_ARGS(&frame.color))))
    return false;
  color_desc.Flags = D3D12_RESOURCE_FLAG_NONE;
  if (FAILED(device->CreateCommittedResource(
          &default_heap, D3D12_HEAP_FLAG_NONE, &color_desc,
          D3D12_RESOURCE_STATE_COPY_DEST, nullptr,
          IID_PPV_ARGS(&frame.hud))))
    return false;

  D3D12_HEAP_PROPERTIES depth_heap{};
  depth_heap.Type = D3D12_HEAP_TYPE_DEFAULT;
  D3D12_RESOURCE_DESC depth_desc{};
  depth_desc.Dimension = D3D12_RESOURCE_DIMENSION_TEXTURE2D;
  depth_desc.Width = 1280;
  depth_desc.Height = 720;
  depth_desc.DepthOrArraySize = 1;
  depth_desc.MipLevels = 1;
  depth_desc.Format = DXGI_FORMAT_D32_FLOAT;
  depth_desc.SampleDesc.Count = 1;
  depth_desc.Flags = D3D12_RESOURCE_FLAG_ALLOW_DEPTH_STENCIL;
  D3D12_CLEAR_VALUE clear{};
  clear.Format = DXGI_FORMAT_D32_FLOAT;
  clear.DepthStencil.Depth = 0;
  if (FAILED(device->CreateCommittedResource(
          &depth_heap, D3D12_HEAP_FLAG_NONE, &depth_desc,
          D3D12_RESOURCE_STATE_DEPTH_WRITE, &clear,
          IID_PPV_ARGS(&frame.depth))))
    return false;

  D3D12_DESCRIPTOR_HEAP_DESC heap_desc{};
  heap_desc.NumDescriptors = 2;
  heap_desc.Type = D3D12_DESCRIPTOR_HEAP_TYPE_RTV;
  if (FAILED(device->CreateDescriptorHeap(&heap_desc,
                                          IID_PPV_ARGS(&frame.rtv))))
    return false;
  device->CreateRenderTargetView(
      frame.color.Get(), nullptr,
      frame.rtv->GetCPUDescriptorHandleForHeapStart());
  auto output_rtv = frame.rtv->GetCPUDescriptorHandleForHeapStart();
  output_rtv.ptr += device->GetDescriptorHandleIncrementSize(
      D3D12_DESCRIPTOR_HEAP_TYPE_RTV);
  device->CreateRenderTargetView(output, nullptr, output_rtv);
  heap_desc.NumDescriptors = 1;
  heap_desc.Type = D3D12_DESCRIPTOR_HEAP_TYPE_DSV;
  if (FAILED(device->CreateDescriptorHeap(&heap_desc,
                                          IID_PPV_ARGS(&frame.dsv))))
    return false;
  device->CreateDepthStencilView(
      frame.depth.Get(), nullptr,
      frame.dsv->GetCPUDescriptorHandleForHeapStart());
  heap_desc.Type = D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV;
  heap_desc.Flags = D3D12_DESCRIPTOR_HEAP_FLAG_SHADER_VISIBLE;
  heap_desc.NumDescriptors = 2;
  if (FAILED(device->CreateDescriptorHeap(&heap_desc,
                                          IID_PPV_ARGS(&frame.srv))))
    return false;
  D3D12_SHADER_RESOURCE_VIEW_DESC view{};
  view.Format = DXGI_FORMAT_R10G10B10A2_UNORM;
  view.ViewDimension = D3D12_SRV_DIMENSION_TEXTURE2D;
  view.Shader4ComponentMapping = D3D12_DEFAULT_SHADER_4_COMPONENT_MAPPING;
  view.Texture2D.MipLevels = 1;
  device->CreateShaderResourceView(
      frame.color.Get(), &view,
      frame.srv->GetCPUDescriptorHandleForHeapStart());
  auto hud_view = frame.srv->GetCPUDescriptorHandleForHeapStart();
  hud_view.ptr += device->GetDescriptorHandleIncrementSize(
      D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV);
  device->CreateShaderResourceView(frame.hud.Get(), &view, hud_view);
  return true;
}

bool DrawTrack(const rex::system::NativeGuestOutputRenderContext& context,
               const Snr04LiveScene& live, TrackGraphics& graphics) {
  auto* device = static_cast<ID3D12Device*>(context.device);
  auto* output = static_cast<ID3D12Resource*>(context.guest_output);
  auto* list = static_cast<rex::graphics::d3d12::DeferredCommandList*>(
      context.deferred_command_list);
  if (!device || !output || !list || !live.track || !live.items ||
      !live.vegetation || !live.remainder ||
      output->GetDesc().Format != DXGI_FORMAT_R10G10B10A2_UNORM ||
      !graphics.Ready(device) || !graphics.BlitReady())
    return false;
  auto scene = ParseSnr04TrackScene(*live.track);
  auto remainder = ParseSnr04RemainderScene(*live.remainder);
  if (scene.source_frame != live.source_frame || !scene.raster_captured ||
      scene.draws.empty() || live.items->frame != live.source_frame ||
      live.vegetation->source_frame != live.source_frame ||
      remainder.source_frame != live.source_frame)
    return false;
  while (!graphics.submitted.empty() &&
         graphics.submitted.front().first <= context.completed_submission)
    graphics.submitted.pop_front();
  if (graphics.submitted.size() >= 8) return false;

  UploadArena arena;
  struct Material {
    ComPtr<ID3D12Resource> resource;
    D3D12_SHADER_RESOURCE_VIEW_DESC view{};
  };
  std::vector<Material> materials;
  std::map<std::tuple<std::array<uint32_t, 6>, uint64_t, uint64_t>,
           uint32_t> material_indices;
  std::map<std::pair<uint64_t, uint32_t>,
           const Snr04TrackTextureIdentity*> texture_identities;
  if (live.track_textures) {
    for (const auto& identity : *live.track_textures)
      if (!texture_identities.emplace(
              std::pair{identity.sequence, identity.fetch_constant},
              &identity).second)
        return false;
  }
  std::map<Snr04TrackRange, uint64_t> vertices, indices;
  for (const auto& [range, bytes] : scene.vertices)
    vertices.emplace(range, arena.Add(bytes.data(), bytes.size()));
  for (const auto& [range, bytes] : scene.indices)
    indices.emplace(range, arena.Add(bytes.data(), bytes.size()));
  std::vector<TrackDrawBinding> bindings;
  bindings.reserve(scene.draws.size());
  for (const auto& draw : scene.draws) {
    if (!graphics.Pipeline(context, draw)) {
      REXGPU_INFO("FH1 native track shader unavailable frame={} sequence={} "
                  "shader={:016X}", live.source_frame, draw.sequence,
                  draw.shader);
      return false;
    }
    const float tile_offset = 720.f - draw.viewport[3];
    if (tile_offset < 0 || tile_offset != std::floor(tile_offset) ||
        draw.viewport[0] != 0 || draw.viewport[1] != 0 ||
        draw.viewport[2] != 1280 || draw.scissor[0] != 0 ||
        draw.scissor[1] != 0 || draw.scissor[2] != 1280 ||
        draw.scissor[3] > draw.viewport[3] ||
        tile_offset + draw.scissor[3] > 720)
      return false;
    TrackDrawBinding binding;
    const bool textured = draw.pixel_shader == 0x6F7CDE74CDACCB08ull &&
        draw.shader == 0x07425D208E8BD688ull &&
        draw.specialization == 0x7Full;
    if (textured) {
      const auto found = texture_identities.find({draw.sequence, 0});
      if (found == texture_identities.end() || !context.texture ||
          !found->second->allocation_id ||
          !found->second->payload_generation ||
          found->second->outdated_mask) {
        REXGPU_INFO("FH1 native track texture identity missing frame={} "
                    "sequence={} found={} allocation={} generation={} dirty={}",
                    live.source_frame, draw.sequence,
                    found != texture_identities.end(),
                    found != texture_identities.end()
                        ? found->second->allocation_id : 0,
                    found != texture_identities.end()
                        ? found->second->payload_generation : 0,
                    found != texture_identities.end()
                        ? found->second->outdated_mask : 0);
        return false;
      }
      const auto& identity = *found->second;
      const auto key = std::tuple{identity.fetch_words,
                                  identity.allocation_id,
                                  identity.payload_generation};
      if (auto existing = material_indices.find(key);
          existing != material_indices.end()) {
        binding.material_index = existing->second;
      } else {
        void* resource = nullptr;
        Material material;
        if (!context.texture(context, identity.fetch_words.data(),
                             identity.allocation_id,
                             identity.payload_generation, &resource,
                             &material.view) || !resource) {
          REXGPU_INFO("FH1 native track texture unavailable frame={} "
                      "sequence={} allocation={} generation={}",
                      live.source_frame, draw.sequence,
                      identity.allocation_id, identity.payload_generation);
          return false;
        }
        material.resource = static_cast<ID3D12Resource*>(resource);
        binding.material_index = uint32_t(materials.size());
        material_indices.emplace(key, binding.material_index);
        materials.push_back(std::move(material));
      }
    }
    binding.pipeline = {draw.shader, draw.specialization, draw.raster_mode,
                        draw.clip_control, draw.depth_control, textured};
    binding.vertex = vertices.at(draw.vertex);
    binding.index = indices.at(draw.index);
    std::array<uint32_t, 120> system{};
    std::copy(draw.system.begin(), draw.system.end(), system.begin());
    std::array<uint32_t, 192> fetch{};
    std::copy(draw.fetch.begin(), draw.fetch.end(), fetch.begin() + 188);
    fetch[190] &= 3;
    binding.b0 = arena.Add(system.data(), sizeof(system));
    binding.b1 = arena.Add(draw.packed.data(),
                           draw.packed.size() * sizeof(uint32_t));
    binding.b3 = arena.Add(fetch.data(), sizeof(fetch));
    binding.viewport = {draw.viewport[0], draw.viewport[1] + tile_offset,
                        draw.viewport[2], draw.viewport[3],
                        draw.viewport[4], draw.viewport[5]};
    binding.scissor = {draw.scissor[0],
                       LONG(draw.scissor[1] + tile_offset),
                       draw.scissor[2],
                       LONG(draw.scissor[3] + tile_offset)};
    bindings.push_back(binding);
  }
  std::vector<ItemDrawBinding> item_bindings;
  uint64_t item_index = 0;
  uint32_t item_index_bytes = 0;
  if (!PrepareItems(context, *live.items, graphics, arena, item_bindings,
                    item_index, item_index_bytes))
    return false;
  std::vector<ItemDrawBinding> vegetation_bindings;
  uint64_t vegetation_index = 0;
  uint32_t vegetation_index_bytes = 0;
  if (!PrepareVegetation(context, *live.vegetation, graphics, arena,
                         vegetation_bindings, vegetation_index,
                         vegetation_index_bytes))
    return false;
  std::vector<RemainderDrawBinding> remainder_bindings;
  uint64_t remainder_vertex = 0;
  if (!PrepareRemainder(context, remainder, graphics, arena,
                        remainder_bindings, remainder_vertex))
    return false;
  TrackFrame frame;
  if (!CreateFrame(device, output, arena, frame)) return false;
  if (!materials.empty()) {
    D3D12_DESCRIPTOR_HEAP_DESC heap{};
    heap.Type = D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV;
    heap.NumDescriptors = UINT(materials.size());
    heap.Flags = D3D12_DESCRIPTOR_HEAP_FLAG_SHADER_VISIBLE;
    if (FAILED(device->CreateDescriptorHeap(
            &heap, IID_PPV_ARGS(&frame.materials))))
      return false;
    auto handle = frame.materials->GetCPUDescriptorHandleForHeapStart();
    const auto stride = device->GetDescriptorHandleIncrementSize(heap.Type);
    for (auto& material : materials) {
      device->CreateShaderResourceView(material.resource.Get(),
                                       &material.view, handle);
      frame.material_resources.push_back(std::move(material.resource));
      handle.ptr += stride;
    }
  }
  list->ReserveAdditionalBytes(
      (scene.draws.size() + item_bindings.size() +
       vegetation_bindings.size() + remainder_bindings.size()) * 512 + 8192);
  const auto base = frame.upload->GetGPUVirtualAddress();
  const auto rtv = frame.rtv->GetCPUDescriptorHandleForHeapStart();
  auto output_rtv = rtv;
  output_rtv.ptr += device->GetDescriptorHandleIncrementSize(
      D3D12_DESCRIPTOR_HEAP_TYPE_RTV);
  const auto dsv = frame.dsv->GetCPUDescriptorHandleForHeapStart();
  auto* scene_color = frame.color.Get();
  auto* hud = frame.hud.Get();
  auto* scene_srv = frame.srv.Get();
  auto* material_heap = frame.materials.Get();
  const auto material_gpu_start = material_heap
      ? material_heap->GetGPUDescriptorHandleForHeapStart()
      : D3D12_GPU_DESCRIPTOR_HANDLE{};
  const auto material_stride = device->GetDescriptorHandleIncrementSize(
      D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV);
  const auto scene_srv_gpu = frame.srv->GetGPUDescriptorHandleForHeapStart();
  graphics.submitted.emplace_back(context.submission, std::move(frame));

  D3D12_RESOURCE_BARRIER barrier{};
  barrier.Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
  barrier.Transition.Subresource = D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
  barrier.Transition.pResource = output;
  barrier.Transition.StateBefore = D3D12_RESOURCE_STATES(
      context.guest_output_state);
  barrier.Transition.StateAfter = D3D12_RESOURCE_STATE_COPY_SOURCE;
  list->D3DResourceBarrier(1, &barrier);
  list->D3DCopyResource(hud, output);
  std::swap(barrier.Transition.StateBefore, barrier.Transition.StateAfter);
  list->D3DResourceBarrier(1, &barrier);
  const float sky[]{0.11f, 0.22f, 0.43f, 1.f};
  list->D3DClearRenderTargetView(rtv, sky, 0, nullptr);
  list->D3DClearDepthStencilView(dsv, D3D12_CLEAR_FLAG_DEPTH, 0, 0, 0,
                                 nullptr);
  list->D3DOMSetRenderTargets(1, &rtv, FALSE, &dsv);
  if (material_heap) list->SetDescriptorHeaps(material_heap, nullptr);
  list->D3DSetGraphicsRootSignature(graphics.root.Get());
  for (size_t i = 0; i < scene.draws.size(); ++i) {
    const auto& draw = scene.draws[i];
    const auto& binding = bindings[i];
    list->RSSetViewport(binding.viewport);
    list->RSSetScissorRect(binding.scissor);
    list->D3DIASetPrimitiveTopology(draw.primitive == 4
        ? D3D_PRIMITIVE_TOPOLOGY_TRIANGLELIST
        : D3D_PRIMITIVE_TOPOLOGY_TRIANGLESTRIP);
    D3D12_INDEX_BUFFER_VIEW index{base + binding.index,
                                  draw.index.second, DXGI_FORMAT_R16_UINT};
    list->D3DIASetIndexBuffer(&index);
    list->D3DSetPipelineState(graphics.pipelines.at(binding.pipeline).Get());
    list->D3DSetGraphicsRootConstantBufferView(0, base + binding.b0);
    list->D3DSetGraphicsRootConstantBufferView(1, base + binding.b1);
    list->D3DSetGraphicsRootConstantBufferView(2, base + binding.b3);
    list->D3DSetGraphicsRootShaderResourceView(3, base + binding.vertex);
    if (binding.material_index != UINT32_MAX) {
      auto handle = material_gpu_start;
      handle.ptr += SIZE_T(binding.material_index) * material_stride;
      list->D3DSetGraphicsRootDescriptorTable(6, handle);
    }
    const uint64_t hash = draw.pixel_shader;
    const float color[]{0.19f + float(hash & 255) / 1024.f,
                        0.23f + float((hash >> 8) & 255) / 1024.f,
                        0.17f + float((hash >> 16) & 255) / 1024.f, 1.f};
    list->D3DSetGraphicsRoot32BitConstants(4, 4, color, 0);
    list->D3DDrawIndexedInstanced(draw.count, 1, 0, 0, 0);
  }
  list->RSSetViewport({0, 0, 1280, 720, 0, 0.5f});
  list->RSSetScissorRect({0, 0, 1280, 720});
  list->D3DIASetPrimitiveTopology(D3D_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
  D3D12_INDEX_BUFFER_VIEW item_view{base + item_index, item_index_bytes,
                                     DXGI_FORMAT_R16_UINT};
  list->D3DIASetIndexBuffer(&item_view);
  for (const auto& binding : item_bindings) {
    list->D3DSetPipelineState(graphics.item_pipelines.at(
        {binding.shader, binding.specialization}).Get());
    list->D3DSetGraphicsRootConstantBufferView(0, base + binding.b0);
    list->D3DSetGraphicsRootConstantBufferView(1, base + binding.b1);
    list->D3DSetGraphicsRootConstantBufferView(2, base + binding.b3);
    list->D3DSetGraphicsRootShaderResourceView(3, base + binding.vertex);
    const float color[]{0.47f, 0.40f, 0.31f, 1.f};
    list->D3DSetGraphicsRoot32BitConstants(4, 4, color, 0);
    list->D3DDrawIndexedInstanced(binding.count, 1, 0, 0, 0);
  }
  D3D12_INDEX_BUFFER_VIEW vegetation_view{
      base + vegetation_index, vegetation_index_bytes, DXGI_FORMAT_R16_UINT};
  list->D3DIASetIndexBuffer(&vegetation_view);
  for (const auto& binding : vegetation_bindings) {
    list->D3DSetPipelineState(graphics.item_pipelines.at(
        {binding.shader, binding.specialization}).Get());
    list->D3DSetGraphicsRootConstantBufferView(0, base + binding.b0);
    list->D3DSetGraphicsRootConstantBufferView(1, base + binding.b1);
    list->D3DSetGraphicsRootConstantBufferView(2, base + binding.b3);
    list->D3DSetGraphicsRootShaderResourceView(3, base + binding.vertex);
    const float color[]{0.18f, 0.36f, 0.19f, 1.f};
    list->D3DSetGraphicsRoot32BitConstants(4, 4, color, 0);
    list->D3DDrawIndexedInstanced(binding.count, 1, 0, 0, 0);
  }
  list->D3DSetGraphicsRootShaderResourceView(3, base + remainder_vertex);
  for (const auto& binding : remainder_bindings) {
    list->RSSetViewport(binding.viewport);
    list->RSSetScissorRect(binding.scissor);
    list->D3DIASetPrimitiveTopology(binding.primitive == 4
        ? D3D_PRIMITIVE_TOPOLOGY_TRIANGLELIST
        : D3D_PRIMITIVE_TOPOLOGY_TRIANGLESTRIP);
    D3D12_INDEX_BUFFER_VIEW index{base + binding.index,
                                  binding.index_bytes,
                                  binding.format ? DXGI_FORMAT_R32_UINT
                                                 : DXGI_FORMAT_R16_UINT};
    list->D3DIASetIndexBuffer(&index);
    list->D3DSetPipelineState(graphics.remainder_pipelines.at(
        binding.pipeline).Get());
    list->D3DSetGraphicsRootConstantBufferView(0, base + binding.b0);
    list->D3DSetGraphicsRootConstantBufferView(1, base + binding.b1);
    list->D3DSetGraphicsRootConstantBufferView(2, base + binding.b3);
    const float color[]{binding.family == 1 ? 0.65f : 0.36f,
                        binding.family == 1 ? 0.16f : 0.35f,
                        binding.family == 1 ? 0.12f : 0.34f, 1.f};
    list->D3DSetGraphicsRoot32BitConstants(4, 4, color, 0);
    list->D3DDrawIndexedInstanced(binding.count, 1, 0, 0, 0);
  }
  barrier.Transition.pResource = scene_color;
  barrier.Transition.StateBefore = D3D12_RESOURCE_STATE_RENDER_TARGET;
  barrier.Transition.StateAfter = D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE;
  list->D3DResourceBarrier(1, &barrier);
  barrier.Transition.pResource = output;
  barrier.Transition.StateBefore = D3D12_RESOURCE_STATES(
      context.guest_output_state);
  barrier.Transition.StateAfter = D3D12_RESOURCE_STATE_RENDER_TARGET;
  list->D3DResourceBarrier(1, &barrier);
  barrier.Transition.pResource = hud;
  barrier.Transition.StateBefore = D3D12_RESOURCE_STATE_COPY_DEST;
  barrier.Transition.StateAfter = D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE;
  list->D3DResourceBarrier(1, &barrier);
  list->D3DOMSetRenderTargets(1, &output_rtv, FALSE, nullptr);
  list->RSSetViewport({0, 0, 1280, 720, 0, 1});
  list->RSSetScissorRect({0, 0, 1280, 720});
  list->SetDescriptorHeaps(scene_srv, nullptr);
  list->D3DSetGraphicsRootSignature(graphics.blit_root.Get());
  list->D3DSetPipelineState(graphics.blit_pipeline.Get());
  list->D3DSetGraphicsRootDescriptorTable(0, scene_srv_gpu);
  list->D3DIASetPrimitiveTopology(D3D_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
  list->D3DDrawInstanced(3, 1, 0, 0);
  barrier.Transition.pResource = output;
  barrier.Transition.StateBefore = D3D12_RESOURCE_STATE_RENDER_TARGET;
  barrier.Transition.StateAfter = D3D12_RESOURCE_STATES(
      context.guest_output_state);
  list->D3DResourceBarrier(1, &barrier);
  return true;
}
}  // namespace

bool DrawNativeOutputTrack(
    const rex::system::NativeGuestOutputRenderContext& context,
    const Snr04LiveScene& scene) {
  static thread_local TrackGraphics graphics;
  try {
    return DrawTrack(context, scene, graphics);
  } catch (const std::exception& error) {
    REXGPU_INFO("FH1 native output rejected source_frame={} reason={}",
                scene.source_frame, error.what());
    return false;
  }
}
}  // namespace pinyon_shift::native_renderer
