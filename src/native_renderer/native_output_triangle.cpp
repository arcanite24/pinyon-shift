#include "native_renderer/native_output_triangle.h"

#include <d3d12.h>
#include <d3dcompiler.h>
#include <wrl/client.h>

#include <deque>
#include <utility>

#include <rex/graphics/d3d12/deferred_command_list.h>
#include <rex/system/interfaces/graphics.h>

#include "native_renderer/snr04_owned_scene_diagnostic.h"

namespace pinyon_shift::native_renderer {
namespace {
using Microsoft::WRL::ComPtr;

struct TrianglePipeline {
  ComPtr<ID3D12Device> device;
  ComPtr<ID3D12RootSignature> root;
  ComPtr<ID3D12PipelineState> pipeline;
  std::deque<std::pair<uint64_t, ComPtr<ID3D12DescriptorHeap>>> rtvs;

  bool Ready(ID3D12Device* current) {
    if (device.Get() != current) {
      rtvs.clear();
      root.Reset();
      pipeline.Reset();
      device = current;
    }
    if (pipeline) return true;
    constexpr char shader[] = R"(
      cbuffer Params : register(b0) { float4 color; };
      struct Vertex { float4 position : SV_Position; float4 color : COLOR0; };
      Vertex vs_main(uint id : SV_VertexID) {
        float2 points[3] = {
          float2(-0.72, -0.62), float2(0.72, -0.62), float2(0, 0.72)
        };
        Vertex result;
        result.position = float4(points[id], 0, 1);
        result.color = color;
        return result;
      }
      float4 ps_main(Vertex input) : SV_Target0 { return input.color; }
    )";
    ComPtr<ID3DBlob> vertex, pixel, errors, serialized;
    if (FAILED(D3DCompile(shader, sizeof(shader) - 1, nullptr, nullptr,
                          nullptr, "vs_main", "vs_5_0", 0, 0, &vertex,
                          &errors)) ||
        FAILED(D3DCompile(shader, sizeof(shader) - 1, nullptr, nullptr,
                          nullptr, "ps_main", "ps_5_0", 0, 0, &pixel,
                          &errors)))
      return false;
    D3D12_ROOT_PARAMETER parameter{};
    parameter.ParameterType = D3D12_ROOT_PARAMETER_TYPE_32BIT_CONSTANTS;
    parameter.Constants.ShaderRegister = 0;
    parameter.Constants.Num32BitValues = 4;
    parameter.ShaderVisibility = D3D12_SHADER_VISIBILITY_ALL;
    D3D12_ROOT_SIGNATURE_DESC root_desc{};
    root_desc.NumParameters = 1;
    root_desc.pParameters = &parameter;
    root_desc.Flags = D3D12_ROOT_SIGNATURE_FLAG_ALLOW_INPUT_ASSEMBLER_INPUT_LAYOUT;
    if (!root &&
        (FAILED(D3D12SerializeRootSignature(&root_desc,
                                            D3D_ROOT_SIGNATURE_VERSION_1,
                                            &serialized, &errors)) ||
         FAILED(device->CreateRootSignature(
             0, serialized->GetBufferPointer(), serialized->GetBufferSize(),
             IID_PPV_ARGS(&root)))))
      return false;
    D3D12_GRAPHICS_PIPELINE_STATE_DESC desc{};
    desc.pRootSignature = root.Get();
    desc.VS = {vertex->GetBufferPointer(), vertex->GetBufferSize()};
    desc.PS = {pixel->GetBufferPointer(), pixel->GetBufferSize()};
    desc.BlendState.RenderTarget[0].RenderTargetWriteMask = D3D12_COLOR_WRITE_ENABLE_ALL;
    desc.SampleMask = UINT_MAX;
    desc.RasterizerState.FillMode = D3D12_FILL_MODE_SOLID;
    desc.RasterizerState.CullMode = D3D12_CULL_MODE_NONE;
    desc.RasterizerState.DepthClipEnable = TRUE;
    desc.PrimitiveTopologyType = D3D12_PRIMITIVE_TOPOLOGY_TYPE_TRIANGLE;
    desc.NumRenderTargets = 1;
    desc.RTVFormats[0] = DXGI_FORMAT_R10G10B10A2_UNORM;
    desc.SampleDesc.Count = 1;
    return SUCCEEDED(device->CreateGraphicsPipelineState(
        &desc, IID_PPV_ARGS(&pipeline)));
  }
};
}  // namespace

bool DrawNativeOutputTriangle(
    const rex::system::NativeGuestOutputRenderContext& context,
    const Snr04LiveScene& scene) {
  auto* device = static_cast<ID3D12Device*>(context.device);
  auto* output = static_cast<ID3D12Resource*>(context.guest_output);
  auto* list = static_cast<rex::graphics::d3d12::DeferredCommandList*>(
      context.deferred_command_list);
  if (!device || !output || !list || !scene.core_draws) return false;
  static thread_local TrianglePipeline graphics;
  if (!graphics.Ready(device)) return false;
  D3D12_DESCRIPTOR_HEAP_DESC heap_desc{};
  heap_desc.Type = D3D12_DESCRIPTOR_HEAP_TYPE_RTV;
  heap_desc.NumDescriptors = 1;
  ComPtr<ID3D12DescriptorHeap> heap;
  if (FAILED(device->CreateDescriptorHeap(&heap_desc, IID_PPV_ARGS(&heap))))
    return false;
  const auto rtv = heap->GetCPUDescriptorHandleForHeapStart();
  device->CreateRenderTargetView(output, nullptr, rtv);
  while (!graphics.rtvs.empty() &&
         graphics.rtvs.front().first <= context.completed_submission)
    graphics.rtvs.pop_front();
  graphics.rtvs.emplace_back(context.submission, std::move(heap));

  D3D12_RESOURCE_BARRIER barrier{};
  barrier.Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
  barrier.Transition.pResource = output;
  barrier.Transition.Subresource = D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
  barrier.Transition.StateBefore =
      D3D12_RESOURCE_STATES(context.guest_output_state);
  barrier.Transition.StateAfter = D3D12_RESOURCE_STATE_RENDER_TARGET;
  list->D3DResourceBarrier(1, &barrier);
  const float sky[]{0.11f, 0.22f, 0.43f, 1.f};
  list->D3DClearRenderTargetView(rtv, sky, 0, nullptr);
  list->D3DOMSetRenderTargets(1, &rtv, FALSE, nullptr);
  list->RSSetViewport({0, 0, float(context.guest_output_width),
                       float(context.guest_output_height), 0, 1});
  list->RSSetScissorRect({0, 0, LONG(context.guest_output_width),
                          LONG(context.guest_output_height)});
  list->D3DSetGraphicsRootSignature(graphics.root.Get());
  list->D3DSetPipelineState(graphics.pipeline.Get());
  list->D3DIASetPrimitiveTopology(D3D_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
  const float color[]{float(scene.core_draws) / 4096.f, 0.8f,
                      (scene.source_frame & 1) ? 0.8f : 0.2f, 1.f};
  list->D3DSetGraphicsRoot32BitConstants(0, 4, color, 0);
  list->D3DDrawInstanced(3, 1, 0, 0);
  std::swap(barrier.Transition.StateBefore, barrier.Transition.StateAfter);
  list->D3DResourceBarrier(1, &barrier);
  return true;
}
}  // namespace pinyon_shift::native_renderer
