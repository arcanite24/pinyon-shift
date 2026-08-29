# Forza Horizon renderer census

This document is the tracked evidence ledger for NR-00. It records facts about
the supported USA retail MS-2505 executable only. Unknowns stay explicit until
a trace or disassembly proves them.

## Baseline

- Pinyon Shift `dev`: `cafc7233fef9e039f163d11023f40eccb22e8fc1`
- ReXGlue: `v0.10.0` at `f5337cdc947ff6d4c4196737e2c807a48f2a1fc2`
- ReXGlue patch stack: `0001` through `0049`
- `default.xex` SHA-256:
  `DB40DF605ADE49A612B35A7A24C38F6004BCB17A88ED6B48288DE16DF9E3987C`

This replaces the investigation plan's historical `29b48259` baseline. It is
an inventory update, not a claim that a native renderer exists.

## Hook ownership contract

`src/native_renderer/graphics_hooks.cpp` is the single owner of title-side
graphics hooks. A hook may observe and dispatch, but with every native-renderer
cvar at its default it must preserve the original instruction, registers,
arguments, and control flow. General runtime fixes remain in
`src/pinyon_shift_runtime_hooks.cpp`.

The dispatch-discovery extension adds no native RHI, guest payload capture,
Xenos suppression, or presentation changes. Its setting,
`pinyon_shift_native_renderer_dispatch_discovery`, defaults to `false`.

## Verified inventory

| Event | Guest location | Owner / ABI evidence | Mutable state | Status |
| --- | --- | --- | --- | --- |
| System command-buffer request | `0x829EFD80` | `sub_829EFB30` calls `VdGetSystemCommandBuffer`; output pointers are passed in `r3` and `r4` | The returned buffer cursor is subsequently written into the graphics-device object | Verified, not hooked |
| Frame submission | `0x829EFEB8` | `sub_829EFB30` calls the sole `VdSwap` import; continuation is `0x829EFEBC` | Device command-buffer cursor is updated after return | Verified, pass-through hook |
| Xenos swap packet | ReXGlue `CommandProcessor::ExecutePacketType3_XE_SWAP` | Consumes the `VdSwap` packet and calls backend `IssueSwap` | ReXGlue snapshots/reset per-frame counters before decoding the packet payload | Verified runtime boundary |
| Title draw adapter | `0x824079B8` | Direct call to indexed wrapper at `0x824079F8`; 38 call sites across 25 caller functions | Entry `r3-r10` and caller `LR` are observed only when discovery is enabled; exact packet store is keyed at `0x82410328`; stack arguments remain unread | Verified, bounded pass-through hook; exact backend provenance qualified, prepared provenance not observed |
| Indexed draw wrapper | `0x8240F4D8` | Stored `PM4_DRAW_INDX_2` header at `0x82410320`; dynamic Type-3 count | Entry `r3-r10` and caller `LR` are observed; six consume-then-clear dirty-mask sites are statically proved | Verified, bounded pass-through hook |
| Immediate draw wrapper | `0x829F7C70` | Stored count-one `PM4_DRAW_INDX_2` header at `0x829F7CA8` | Entry `r3-r10` and caller `LR` are observed only when discovery is enabled | Verified, bounded pass-through hook |
| Visibility-query begin | `0x829F21A0` | Stored count-one `PM4_VIZ_QUERY` header at `0x829F225C`; active-query bit set at `0x829F2270` | Entry `r3-r10` and caller `LR` are observed only when discovery is enabled | Verified, bounded pass-through hook |
| Visibility-query end | `0x829F2280` | Stored count-one `PM4_VIZ_QUERY` header at `0x829F22E4`; active-query bit cleared at `0x829F2308` | Entry `r3-r10` and caller `LR` are observed only when discovery is enabled | Verified, bounded pass-through hook |
| Visibility-query owner | `0x82D951E0` | Calls begin at `0x82D95230`, performs five work calls, then calls end at `0x82D95378`; two direct callers | Entry `r3-r10` and caller `LR` are observed only when discovery is enabled | Lifecycle owner verified; result consumer and semantics unknown |
| Draw packet backend | ReXGlue `PM4_DRAW_INDX` / `PM4_DRAW_INDX_2` | Generic command processor decodes the packet before backend `IssueDraw` | Register-derived draw state is consumed by the backend | Verified runtime boundary |
| Draw packet provenance | Title stores `0x82410328` / `0x829F7CB0`; ReXGlue patch `0080` | Both sides normalize the same PM4 header to a physical address | Fixed outstanding table is consumed only on exact address equality; same-address generations are retained oldest-first | Runtime-qualified, passive: 107,455 exact matches and zero attribution faults; no prepared callback observed |
| Draw backend outcome | D3D12 `IssueDraw`; ReXGlue patch `0081` | One callback at every backend return carries frame, draw, and exact packet identity | 18 bounded outcomes separate prepared completion, EDRAM copy, no-effect paths, pending pipelines, and failures | Runtime-qualified, passive: 8,478,174 outcomes, zero callback faults; all 132,568 exact title matches were EDRAM copies |
| Resolve controller | `0x824587D8` | Two direct calls to setup wrapper `0x82458A88`; three direct controller callers | Entry `r3-r10` and caller `LR` are observed only when discovery is enabled | Verified, bounded pass-through hook |
| Resolve setup | `0x82458A88` | Emits `RB_MODECONTROL` register index `0x2208` followed by `EdramMode::kCopy` value 6 | Entry `r3-r10` and caller `LR` are observed only when discovery is enabled | Title setup verified; subsequent resolve draw ownership unknown |
| Binning/scissor state | `0x82413AB8` | Stores `PM4_SET_BIN_MASK_LO/HI` headers; ten direct calls | Entry `r3-r10` and caller `LR` are observed only when discovery is enabled | Xenos state boundary verified; semantic tiled role unknown |
| Binning-state reset | `0x824736F0` | Stores all `PM4_SET_BIN_MASK/SELECT_LO/HI` headers and calls the scissor-state wrapper; four direct callers | Entry `r3-r10` and caller `LR` are observed only when discovery is enabled | Xenos state boundary verified; semantic tiled role unknown |
| Resolve/copy backend | ReXGlue backend `IssueCopy` | Triggered by a Xenos draw while `RB_MODECONTROL.edram_mode == kCopy` | Render-target and guest-memory dependencies may be produced | Verified runtime boundary |

## Bounded draw observation

Patch `0044-graphics-draw-observer.patch` adds an optional, backend-neutral
observer immediately before `IssueDraw`. The observer is not registered unless
`pinyon_shift_native_renderer_census` is enabled before startup. The default-off
path performs one null observer check and leaves draw submission unchanged.

Each observation contains sequence numbers, primitive/index metadata, shader
hashes, render-target/depth/scissor register values, and a memexport flag. It
does not contain shader code, constants, texture data, vertex/index contents,
or any other guest payload.

Pinyon hashes those fields into a fixed 4096-entry table. Element count remains
in each sample but is excluded from the signature so repeated geometry using
the same pipeline and target groups into one pass identity. Every 300 emulated
frames it emits one window record and at most the 16 most frequent signatures.
The window record reports both `unique_signatures` and explicit
`overflow_draws`; saturation never causes an unbounded allocation or per-draw
log stream. This is census evidence only and does not classify or suppress a
draw.

### Local qualification snapshot — 2026-08-27

The census-enabled Release build was launched through `launch-preview.ps1`
against the installed `0.1.0` AppData save and exited normally. Two consecutive
open-world windows produced:

| Frames | Draws | Unique signatures | Overflow draws |
|---:|---:|---:|---:|
| 301–600 | 922,750 | 686 | 0 |
| 601–900 | 1,006,435 | 458 | 0 |

Each window emitted exactly the configured maximum of 16 ranked summaries, no
crash/error/GPU-loss event was recorded, and Xenos remained the only renderer.
An earlier 256-entry prototype that hashed raw draw initiators saturated in the
same route; the recorded result above validates the coarser pass identity and
4096-entry fixed capacity that replaced it.

The frame hook has no register parameters and no conditional jump target. When
the census is enabled it emits only frame 1 and every 300th frame, containing a
sequence number, the fixed hook address, and `pass_through` mode. It does not
read or serialize guest memory.

## Open inventory work

- Prove whether the title has a stored `PM4_DRAW_INDX` (`0x22`) constructor.
- Correlate the proved title resolve controller/setup with the subsequent copy
  draw and its semantic destination owner.
- Locate downstream query-result consumption beyond the proved lifecycle
  owner.
- Correlate the proved bin-mask/select wrappers with semantic tiled-pass
  begin/end ownership.
- Extend dirty-state proof beyond the six indexed-wrapper clear sites.
- Inventory memexport-producing draws and guest-visible resolve destinations.
- Map high-level world, vehicle, road, HUD, garage, mirror, shadow, exposure,
  livery, thumbnail, and rewind dispatch families.
- Use exact title-packet provenance to associate those callers with prepared
  signatures before reading object/lifetime structures.

The ten proved wrapper entries, all 72 static direct calls, one proved tail-
forwarded correlation edge, and explicit semantic unknowns are recorded in
[`HIGH_LEVEL_RENDER_HOOKS.md`](HIGH_LEVEL_RENDER_HOOKS.md).

Resolve-to-texture dependency tracking is documented in
`GUEST_VISIBLE_RENDER_DEPENDENCIES.md`. The evidence-based classifier and scene
capture contract are documented in `PASS_CLASSIFICATION.md`. Scene coverage,
CPU-read observation, and presentation provenance remain subsequent NR-00
work.

Unknown work stays on Xenos.

### Wrapper-family qualification — 2026-08-29

The expanded passive wrapper hooks were qualified in session
`20260829T105816Z-p27600` against the installed `0.1.0` AppData save. The
7,500-frame report recorded 331,274 total calls: 165,637 through the title draw
adapter and the same 165,637 through its indexed packet wrapper. Fourteen
adapter callers and the indexed wrapper's sole caller all matched the static
inventory, with zero unknown callers and zero overflow.

The run exited normally, retained Xenos authority, and confirmed that the
hooks performed no guest payload reads, guest-state writes, control-flow
changes, or suppression. Median derived performance was 30.472 FPS over
233.758 seconds. The other five proved wrappers were not exercised by this
festival scene and remain explicitly unclassified pending repeated marked
scene coverage.

Candidate-specific index, vertex-layout, blend, depth, and raster metadata is
documented in [`CANDIDATE_DRAW_SELECTION.md`](CANDIDATE_DRAW_SELECTION.md).
It is a local NR-02 shortlist only and does not change the NR-00 classifier or
open Gate B.

## NR-02B declaration extension

Patch `0053-graphics-vertex-declaration-observer.patch` adds a 32-attribute
bound, VGT index range, exact result mapping, and explicit overflow reporting.
Title-side candidate aggregation preserves minimum/maximum index counts and
minimum index allocation length across census windows. The deterministic
contract builder independently decodes and validates the captured declaration
without reading guest payloads. Qualification details are in
[`GEOMETRY_CONTRACT.md`](GEOMETRY_CONTRACT.md); Xenos remains authoritative.

## NR-02C draw-state extension

Used shader constants plus texture-fetch and sampler state are captured by the
bounded NR-02C observer and decoded as described in
[`DRAW_STATE_CONTRACT.md`](DRAW_STATE_CONTRACT.md). This state remains
register-only; the census still performs no guest resource payload reads.
The deterministic inventory also retains every emitted resolve target so the
candidate selector can reject any captured base or mip address inside a known
resolve range, independently of draw-window timing.

Candidate records are finalized only by the synchronous D3D12 prepared-draw
callback. Their signature includes the exact effective shader specialization,
preventing a global guest-shader pair with multiple prepared variants from
producing an ambiguous or guessed candidate identity. Draws that never reach a
prepared pipeline are counted and excluded; Xenos remains authoritative.

## Side-effect-boundary qualification — 2026-08-29

Session `20260829T112833Z-p40656` qualified the ten-wrapper dispatch inventory
against the installed AppData save. It reached live festival gameplay and
exited normally after 6,916 frames. All 26 runtime callers matched the 72
direct calls plus one tail-forwarded correlation edge; caller-table overflow
was zero.

The two newly active families were binning/scissor state with 978,620 calls
from eight callers and binning-state reset with 11,845 calls from three
callers. These frequencies prove runtime reachability only; semantic tiled-
pass ownership remains unknown. Xenos performed every draw and resolve, and
suppression stayed disabled.
