# Forza Horizon renderer census

This document is the tracked evidence ledger for NR-00. It records facts about
the supported USA retail MS-2505 executable only. Unknowns stay explicit until
a trace or disassembly proves them.

## Baseline

- Pinyon Shift `dev`: `cafc7233fef9e039f163d11023f40eccb22e8fc1`
- ReXGlue: `v0.10.0` at `f5337cdc947ff6d4c4196737e2c807a48f2a1fc2`
- ReXGlue patch stack: `0001` through `0043`
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

This first change adds no native RHI, guest payload capture, Xenos suppression,
or presentation changes. The only setting is
`pinyon_shift_native_renderer_census`, and it defaults to `false`.

## Verified inventory

| Event | Guest location | Owner / ABI evidence | Mutable state | Status |
| --- | --- | --- | --- | --- |
| System command-buffer request | `0x829EFD80` | `sub_829EFB30` calls `VdGetSystemCommandBuffer`; output pointers are passed in `r3` and `r4` | The returned buffer cursor is subsequently written into the graphics-device object | Verified, not hooked |
| Frame submission | `0x829EFEB8` | `sub_829EFB30` calls the sole `VdSwap` import; continuation is `0x829EFEBC` | Device command-buffer cursor is updated after return | Verified, pass-through hook |
| Xenos swap packet | ReXGlue `CommandProcessor::ExecutePacketType3_XE_SWAP` | Consumes the `VdSwap` packet and calls backend `IssueSwap` | ReXGlue snapshots/reset per-frame counters before decoding the packet payload | Verified runtime boundary |
| Draw packet | ReXGlue `PM4_DRAW_INDX` / `PM4_DRAW_INDX_2` | Generic command processor decodes the packet before backend `IssueDraw` | Register-derived draw state is consumed by the backend | Backend boundary verified; title wrapper unknown |
| Resolve/copy | ReXGlue backend `IssueCopy` | Triggered by the Xenos copy path | Render-target and guest-memory dependencies may be produced | Backend boundary verified; title wrapper unknown |

The frame hook has no register parameters and no conditional jump target. When
the census is enabled it emits only frame 1 and every 300th frame, containing a
sequence number, the fixed hook address, and `pass_through` mode. It does not
read or serialize guest memory.

## Open inventory work

- Prove the FH1 draw-wrapper families and their ABI before adding draw hooks.
- Locate the title-side resolve and query wrapper families.
- Establish where each wrapper consumes or clears dirty graphics state.
- Inventory memexport-producing draws and guest-visible resolve destinations.
- Map high-level world, vehicle, road, HUD, garage, mirror, shadow, exposure,
  livery, thumbnail, and rewind dispatch families.

Bounded draw metadata, resolve dependencies, and pass classification belong to
the subsequent NR-00 pull requests. Unknown work stays on Xenos.
