# Native draw-state contract

NR-02C captures the immutable shader inputs needed to describe one authentic
draw without changing the displayed frame. Patch
`0054-graphics-draw-state-observer.patch` extends the existing synchronous draw
observer immediately before `IssueDraw`. Xenos remains the only draw authority.

## Captured state

The observer copies only registers referenced by the active shaders:

- up to 64 used vertex float4 constants and 64 used pixel float4 constants,
  each tagged with its shader-bank index;
- the used-bit maps and packed values for 256 bool constants;
- the used loop constants from the 32-register loop bank;
- up to 16 texture-fetch instruction instances, including stage, fetch index,
  the raw six-word Xenos texture fetch constant, instruction dimension, filter
  overrides, LOD bias, half-texel offsets, predication flags, and result
  swizzle; and
- an exact hash of the captured state for cross-capture stability reporting.

The bounds are explicit. Any constant or texture instruction overflow makes a
candidate ineligible. Texture bytes, vertex bytes, index bytes, shader bytecode,
and render targets are not read by this observer.

## Decoder

`tools/build-native-draw-state-contract.py` accepts an exact candidate-selection
inventory. The initial contract requires one selected candidate and one through
four texture resources, while preserving every observed instruction that
references them. It validates constant counts and indices, decodes all 64 Xenos
texture format identities, dimensions stored with minus-one sizing, physical
base and mip addresses, pitch, tiling, endianness, signs, component swizzle,
number format, exponent adjustment, clamp modes, effective filtering,
anisotropy, mip range, fetch and instruction LOD bias, instruction offsets, and
result routing.

The generated document reports whether the sampled draw-state hash is stable
across captures. A changing hash is valid for an authentic snapshot, but blocks
claims that the state is static and must be accounted for by later replay.

## NR-02C qualification

Two post-`0054` AppData-backed `open_world_day` captures selected exactly one
repeatable candidate:

| Session | Draws | Candidate records | Median FPS | 1% low FPS |
| --- | ---: | ---: | ---: | ---: |
| `20260828T055422Z-p40612` | 120,863 | 36 | 60.015 | 28.900 |
| `20260828T055517Z-p39584` | 129,284 | 39 | 59.948 | 28.370 |

Candidate `08810649442C4213` has the same draw-state hash,
`6038AE2E348D3441`, in both captures. Its bounded snapshot contains two vertex
float constants, no pixel float, bool, or loop constants, and one pixel texture
instruction. The texture is a tiled 1280 by 720
`2_10_10_10_AS_16_16_16_16` resource with a 1,280-pixel pitch, point base-map
sampling, and the observed `[2, 1, 0, 5]` component selectors. The geometry
planner also validates the draw's 24 vertices against its complete 384-byte
binding.

Both runs exited normally with zero observer overflow and no memexport, XMA, or
ZPD fallback activity. This qualifies the capture and decode implementation,
but not this candidate: its texture base `0x1C149000` is also an observed
resolve destination. The corrected selector rejects it as a dynamic
render-target consumer. NR-02C therefore needs a new static-source candidate
before its output can advance to PSO construction or isolated comparison.

## Safety boundary

This contract deliberately stops before resource payload access. Its safety
record fixes the following values:

- guest resource payload read: false;
- native upload: false;
- native draw: false;
- suppression allowed: false; and
- Xenos authority: true.

The next milestone may copy the selected snapshot's bounded resources into an
isolated native target. It must preserve these gates until visual and dependency
comparison is complete.
