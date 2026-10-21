// NA-2.4 pilot (docs/NEAR_NATIVE_RESEARCH.md, issue #753): the command
// buffers the procedural models run are drawn from owned draw programs
// (rex/system/d3d_program.h, gpu_d3d_program). These hooks mark their
// buffers as they are run: the owner's two calls into the list runner set a
// thread-local flag around the call, and the runner's entry marks the
// buffers of the list it runs while the flag is set. See the "display-list
// owners" record in site/findings/rendering.toml.

#include <atomic>
#include <cstdint>

#include <rex/ppc/context.h>
#include <rex/system/d3d_program.h>
#include <rex/system/kernel_state.h>
#include <rex/system/xmemory.h>
#include <rex/types.h>

namespace pinyon_shift::native_renderer {
namespace {

namespace program = rex::system::d3d_program;

// A command buffer: +116 its chain of buffer nodes. A node: +0 the next
// node, +4 its entry count, then (size and flags, physical address) pairs
// from +8 (the same reading as the D3D census).
constexpr uint32_t kListChain = 116;

thread_local uint32_t t_owner_depth = 0;

bool GuestPointer(uint32_t address) { return address >= 0x10000u && address < 0xFFFF0000u; }

uint32_t Load32(uint32_t address) {
  return rex::byte_swap(
      *rex::system::kernel_state()->memory()->TranslateVirtual<uint32_t*>(address));
}

void MarkListBuffers(uint32_t list) {
  if (!GuestPointer(list)) return;
  // An asynchronous call record, not a command buffer.
  if ((Load32(list) & 0xF) == 10) return;
  uint32_t node = Load32(list + kListChain);
  for (uint32_t nodes = 0; GuestPointer(node) && nodes < 64; ++nodes) {
    const uint32_t entries = Load32(node + 4);
    for (uint32_t i = 0; i < entries && i < 4096; ++i) {
      program::MarkList(Load32(node + 12 + 8 * i));
    }
    node = Load32(node);
  }
}

}  // namespace

// Called from the list runner's entry hook (base: the D3D census hook at
// 0x82416A00; v4: PinyonShiftD3dProgramRunCommandBuffer).
void D3dProgramOnRun(uint32_t list) {
  if (t_owner_depth && program::Mode()) MarkListBuffers(list);
}

}  // namespace pinyon_shift::native_renderer

// The procedural models' calls into their list runner (base 0x82418A24 and
// 0x82418EC8, v4 0x824489D4 and 0x82448E78) and the instructions after them.
void PinyonShiftD3dProgramOwnerEnter0() { ++pinyon_shift::native_renderer::t_owner_depth; }
void PinyonShiftD3dProgramOwnerLeave0() {
  if (pinyon_shift::native_renderer::t_owner_depth) --pinyon_shift::native_renderer::t_owner_depth;
}
void PinyonShiftD3dProgramOwnerEnter1() { ++pinyon_shift::native_renderer::t_owner_depth; }
void PinyonShiftD3dProgramOwnerLeave1() {
  if (pinyon_shift::native_renderer::t_owner_depth) --pinyon_shift::native_renderer::t_owner_depth;
}

// v4 0x824469B0, D3DDevice_RunCommandBuffer: r4 the command buffer.
void PinyonShiftD3dProgramRunCommandBuffer(PPCRegister& r4) {
  pinyon_shift::native_renderer::D3dProgramOnRun(r4.u32);
}
