#include "native_renderer/native_output_track.h"

#include <d3d12.h>
#include <d3dcompiler.h>
#include <wrl/client.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <deque>
#include <map>
#include <stdexcept>
#include <tuple>
#include <utility>
#include <vector>

#include <rex/graphics/d3d12/deferred_command_list.h>
#include <rex/system/interfaces/graphics.h>

#include "native_renderer/snr04_owned_scene_diagnostic.h"

namespace pinyon_shift::native_renderer {
namespace {
using Microsoft::WRL::ComPtr;
using PipelineKey = std::tuple<uint64_t, uint64_t, uint32_t, uint32_t, uint32_t>;

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
  ComPtr<ID3D12Resource> upload, depth;
  ComPtr<ID3D12DescriptorHeap> rtv, dsv;
};

struct TrackDrawBinding {
  PipelineKey pipeline;
  uint64_t vertex = 0, index = 0, b0 = 0, b1 = 0, b3 = 0;
  D3D12_VIEWPORT viewport{};
  D3D12_RECT scissor{};
};

struct TrackGraphics {
  ComPtr<ID3D12Device> device;
  ComPtr<ID3D12RootSignature> root;
  ComPtr<ID3DBlob> pixel;
  std::map<PipelineKey, ComPtr<ID3D12PipelineState>> pipelines;
  std::deque<std::pair<uint64_t, TrackFrame>> submitted;

  bool Ready(ID3D12Device* current) {
    if (device.Get() != current) {
      submitted.clear();
      pipelines.clear();
      root.Reset();
      pixel.Reset();
      device = current;
    }
    if (root && pixel) return true;
    constexpr char shader[] =
        "cbuffer Color : register(b2) { float4 flat; };"
        "float4 main() : SV_Target0 { return flat; }";
    ComPtr<ID3DBlob> errors, serialized;
    if (FAILED(D3DCompile(shader, sizeof(shader) - 1, nullptr, nullptr,
                          nullptr, "main", "ps_5_1", 0, 0, &pixel, &errors)))
      return false;
    D3D12_ROOT_PARAMETER parameters[6]{};
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
    D3D12_ROOT_SIGNATURE_DESC description{
        6, parameters, 0, nullptr,
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
    const PipelineKey key{draw.shader, draw.specialization, draw.raster_mode,
                          draw.clip_control, draw.depth_control};
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
    description.PS = {pixel->GetBufferPointer(), pixel->GetBufferSize()};
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
    if (FAILED(device->CreateGraphicsPipelineState(
            &description, IID_PPV_ARGS(&pipeline))))
      return false;
    pipelines.emplace(key, std::move(pipeline));
    return true;
  }
};

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
  heap_desc.NumDescriptors = 1;
  heap_desc.Type = D3D12_DESCRIPTOR_HEAP_TYPE_RTV;
  if (FAILED(device->CreateDescriptorHeap(&heap_desc,
                                          IID_PPV_ARGS(&frame.rtv))))
    return false;
  device->CreateRenderTargetView(
      output, nullptr, frame.rtv->GetCPUDescriptorHandleForHeapStart());
  heap_desc.Type = D3D12_DESCRIPTOR_HEAP_TYPE_DSV;
  if (FAILED(device->CreateDescriptorHeap(&heap_desc,
                                          IID_PPV_ARGS(&frame.dsv))))
    return false;
  device->CreateDepthStencilView(
      frame.depth.Get(), nullptr,
      frame.dsv->GetCPUDescriptorHandleForHeapStart());
  return true;
}

bool DrawTrack(const rex::system::NativeGuestOutputRenderContext& context,
               const Snr04LiveScene& live, TrackGraphics& graphics) {
  auto* device = static_cast<ID3D12Device*>(context.device);
  auto* output = static_cast<ID3D12Resource*>(context.guest_output);
  auto* list = static_cast<rex::graphics::d3d12::DeferredCommandList*>(
      context.deferred_command_list);
  if (!device || !output || !list || !live.track ||
      output->GetDesc().Format != DXGI_FORMAT_R10G10B10A2_UNORM ||
      !graphics.Ready(device))
    return false;
  auto scene = ParseSnr04TrackScene(*live.track);
  if (scene.source_frame != live.source_frame || !scene.raster_captured ||
      scene.draws.empty())
    return false;
  while (!graphics.submitted.empty() &&
         graphics.submitted.front().first <= context.completed_submission)
    graphics.submitted.pop_front();
  if (graphics.submitted.size() >= 8) return false;

  UploadArena arena;
  std::map<Snr04TrackRange, uint64_t> vertices, indices;
  for (const auto& [range, bytes] : scene.vertices)
    vertices.emplace(range, arena.Add(bytes.data(), bytes.size()));
  for (const auto& [range, bytes] : scene.indices)
    indices.emplace(range, arena.Add(bytes.data(), bytes.size()));
  std::vector<TrackDrawBinding> bindings;
  bindings.reserve(scene.draws.size());
  for (const auto& draw : scene.draws) {
    if (!graphics.Pipeline(context, draw)) return false;
    const float tile_offset = 720.f - draw.viewport[3];
    if (tile_offset < 0 || tile_offset != std::floor(tile_offset) ||
        draw.viewport[0] != 0 || draw.viewport[1] != 0 ||
        draw.viewport[2] != 1280 || draw.scissor[0] != 0 ||
        draw.scissor[1] != 0 || draw.scissor[2] != 1280 ||
        draw.scissor[3] > draw.viewport[3] ||
        tile_offset + draw.scissor[3] > 720)
      return false;
    TrackDrawBinding binding;
    binding.pipeline = {draw.shader, draw.specialization, draw.raster_mode,
                        draw.clip_control, draw.depth_control};
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
  TrackFrame frame;
  if (!CreateFrame(device, output, arena, frame)) return false;
  list->ReserveAdditionalBytes(scene.draws.size() * 512 + 4096);
  const auto base = frame.upload->GetGPUVirtualAddress();
  const auto rtv = frame.rtv->GetCPUDescriptorHandleForHeapStart();
  const auto dsv = frame.dsv->GetCPUDescriptorHandleForHeapStart();
  graphics.submitted.emplace_back(context.submission, std::move(frame));

  D3D12_RESOURCE_BARRIER barrier{};
  barrier.Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
  barrier.Transition.pResource = output;
  barrier.Transition.Subresource = D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
  barrier.Transition.StateBefore = D3D12_RESOURCE_STATES(
      context.guest_output_state);
  barrier.Transition.StateAfter = D3D12_RESOURCE_STATE_RENDER_TARGET;
  list->D3DResourceBarrier(1, &barrier);
  const float sky[]{0.11f, 0.22f, 0.43f, 1.f};
  list->D3DClearRenderTargetView(rtv, sky, 0, nullptr);
  list->D3DClearDepthStencilView(dsv, D3D12_CLEAR_FLAG_DEPTH, 0, 0, 0,
                                 nullptr);
  list->D3DOMSetRenderTargets(1, &rtv, FALSE, &dsv);
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
    const uint64_t hash = draw.pixel_shader;
    const float color[]{0.19f + float(hash & 255) / 1024.f,
                        0.23f + float((hash >> 8) & 255) / 1024.f,
                        0.17f + float((hash >> 16) & 255) / 1024.f, 1.f};
    list->D3DSetGraphicsRoot32BitConstants(4, 4, color, 0);
    list->D3DDrawIndexedInstanced(draw.count, 1, 0, 0, 0);
  }
  std::swap(barrier.Transition.StateBefore, barrier.Transition.StateAfter);
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
  } catch (const std::exception&) {
    return false;
  }
}
}  // namespace pinyon_shift::native_renderer
