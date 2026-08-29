# High-level render hook inventory

This is the NR-00A and NR-05A title-dispatch ledger for the supported USA
retail MS-2505 executable. It separates packet-wrapper identity, which is now
proved, from semantic renderer identity, which remains unknown until runtime
scene evidence supports a family name.

The dispatch extension starts from Pinyon Shift `dev` merge
`38bc3a2239b5c3d1689d0810ab2349e0527cadc6`, ReXGlue `v0.10.0` at
`f5337cdc947ff6d4c4196737e2c807a48f2a1fc2`, and patch stack `0001` through
`0079`. The supported `default.xex` SHA-256 remains
`DB40DF605ADE49A612B35A7A24C38F6004BCB17A88ED6B48288DE16DF9E3987C`.

## Safety boundary

The discovery path is opt-in through
`pinyon_shift_native_renderer_dispatch_discovery` and defaults to `false`.
Each reviewed wrapper opens with `mflr r12`; the hook on the following
instruction observes the caller `LR` through `r12` plus unchanged entry
`r3-r10`. A fixed 256-entry atomic table aggregates caller frequency; it does
not read guest resource payloads or write guest state. The original wrapper,
PM4 packet, Xenos work, arguments, registers, and control flow are preserved.
Discovery records are never suppression evidence.

## Proved wrapper layers

The generated AOT instruction inventory establishes seven runtime wrapper
families:

| Entry | Static evidence | Reviewed identity | Runtime observation |
| --- | --- | --- | --- |
| `0x824079B8` | Directly adapts its entry arguments and calls `0x8240F4D8` at `0x824079F8` | Title draw adapter; semantic family unknown | Hook `0x824079BC`: entry `LR` and `r3-r10` |
| `0x8240F4D8` | At `0x82410320`, stores a dynamic-count Type-3 `PM4_DRAW_INDX_2` (`0x36`) header | Indexed draw packet wrapper | Hook `0x8240F4DC`: entry `LR` and `r3-r10` |
| `0x824587D8` | Calls `0x82458A88` at `0x82458828` and `0x824589E4` while managing resolve state | Title resolve controller | Hook `0x824587DC`: entry `LR` and `r3-r10` |
| `0x82458A88` | Writes register `0x2208` (`RB_MODECONTROL`) followed by value 6 (`EdramMode::kCopy`) at `0x82458AC0`/`0x82458AD4` | Resolve state-packet setup wrapper | Hook `0x82458A8C`: entry `LR` and `r3-r10` |
| `0x829F21A0` | At `0x829F225C`, stores `0xC0002300`; then marks the query ID active at `0x829F2270` | Visibility-query begin wrapper | Hook `0x829F21A4`: entry `LR` and `r3-r10` |
| `0x829F2280` | At `0x829F22E4`, stores `0xC0002300`; then clears the active query ID at `0x829F2308` | Visibility-query end wrapper | Hook `0x829F2284`: entry `LR` and `r3-r10` |
| `0x829F7C70` | At `0x829F7CA8`, stores fixed Type-3 count-one `PM4_DRAW_INDX_2` (`0x36`) header | Immediate/embedded-index draw wrapper | Hook `0x829F7C74`: entry `LR` and `r3-r10` |

Three additional opcode-`0x36` constructors at `0x829E82D0`, `0x829E8428`,
and `0x829EDB68` build initialization templates. They are inventoried but are
not runtime draw hooks.

No `PM4_DRAW_INDX` (`0x22`) title constructor has yet passed the same stored-
header proof. The scanner reports only proved stored opcode-`0x36` and
opcode-`0x23` headers and explicitly rejects a matching numeric operation in
`sub_83051E48` because its result is not stored as a command packet.

The adapter ABI exposes `r3-r10` at entry and reads two additional stack words
at entry-stack offsets 92 and 100 before calling the packet wrapper. Those
stack values are documented by the static inventory but are intentionally not
read by the passive runtime hook.

## Dirty-state consumption boundary

The indexed packet wrapper consumes and then clears six dirty-mask slices
before packet emission. Four clears affect the 64-bit word at device offset
16 (`0x8240FAF4`, `0x8240FB2C`, `0x8240FB74`, `0x8240FBB8`); one affects offset
24 (`0x8240FC08`); and one affects offset 32 (`0x8240FC40`). Each clear follows
a state-submission call and a mask operation on the loaded word. The adapter
hook therefore runs before all six clears. This proves the capture boundary;
it does not assign semantic names to any mask bit.

## Resolve boundary

ReXGlue's backend boundary remains proved: a Xenos draw with
`RB_MODECONTROL.edram_mode == kCopy` enters `IssueCopy`. The title side is now
also bounded: `sub_824587D8` controls the lifecycle and calls
`sub_82458A88`, which emits the exact `RB_MODECONTROL = kCopy` state pair.
This proves resolve setup and its controller, not which subsequent draw covers
the copy rectangle or which semantic system owns the destination. The
inventory records `title_resolve_setup_and_backend_copy_proved` without using
timing or dimensions as identity evidence.

## Static direct callers

`tools/discover-native-renderer-dispatch.py` scans all generated AOT C++ files,
reconstructs instruction addresses from function entries and labels, and
produces a deterministic payload-free JSON inventory. At the current baseline
it finds 56 direct call sites: 38 into the promoted adapter, nine into the
indexed packet wrapper, two into the immediate wrapper, two into resolve
setup, three into the resolve controller, and one into each visibility-query
wrapper. The adapter's 38 sites group into 25 caller functions:

| Caller function | Adapter call sites |
| --- | --- |
| `sub_823E6EF0` | `0x823E6F4C` |
| `sub_823F10C8` | `0x823F117C`, `0x823F11BC`, `0x823F12B0`, `0x823F12E4`, `0x823F13DC`, `0x823F1410` |
| `sub_823F74B0` | `0x823F7590` |
| `sub_823FA990` | `0x823FAD40` |
| `sub_82403C38` | `0x824043A8`, `0x82404970` |
| `sub_824426B8` | `0x82442BF0` |
| `sub_82461108` | `0x82461334` |
| `sub_82463AD8` | `0x82463B34` |
| `sub_82469478` | `0x824695D8`, `0x82469608` |
| `sub_829F0298` | `0x829F0348` |
| `sub_829F8D88` | `0x829F94C0` |
| `sub_82B3FB98` | `0x82B4093C`, `0x82B40BE0`, `0x82B40D70` |
| `sub_82B40E60` | `0x82B41BB4` |
| `sub_82C39E98` | `0x82C39F78` |
| `sub_82C3B7D8` | `0x82C3BCF4` |
| `sub_82C3BD78` | `0x82C3C2CC`, `0x82C3C2E8`, `0x82C3C31C`, `0x82C3C354` |
| `sub_82C3F0E0` | `0x82C3F1F0` |
| `sub_82C8C340` | `0x82C8C62C` |
| `sub_82C8F000` | `0x82C8F828` |
| `sub_82C90178` | `0x82C90CB8` |
| `sub_82C90D88` | `0x82C912F0` |
| `sub_82C97CA8` | `0x82C98134` |
| `sub_82DDF158` | `0x82DDF274` |
| `sub_82E67C48` | `0x82E67FCC` |
| `sub_8314A138` | `0x8314A194`, `0x8314A1AC` |

The exact lower-wrapper and query-wrapper sites, return addresses, wrapper
layers, packet constructors, dirty transitions, and hook ABIs remain in the
versioned JSON rather than a second hand-maintained table.

The entry `LR` is sufficient to correlate runtime frequency with this table.
It is not sufficient to name a call site terrain, road, vehicle, HUD, or any
other semantic family. Those names remain `unknown`.

## Capture and correlation

Generate static evidence and launch the installed AppData save with discovery
enabled:

```powershell
$stateRoot = Join-Path $env:LOCALAPPDATA `
    'PinyonShift\source\0.1.0\.local\preview'
.\tools\capture-native-renderer-dispatch.ps1 `
    -StateRoot $stateRoot `
    -Scene open_world `
    -StaticOutput .local\qualification\native-dispatch-static.json
```

After a clean exit, correlate the diagnostics JSONL with the static inventory:

```powershell
python .\tools\summarize-native-renderer-dispatch.py `
    <diagnostics.jsonl> `
    --static .local\qualification\native-dispatch-static.json `
    --output .local\qualification\native-dispatch-runtime.json
```

The summarizer requires one read-only session summary, verifies aggregate
caller counts, rejects any session that does not prove the no-mutation safety
boundary, and labels every semantic identity `unknown`. An unmatched `LR` is
retained rather than guessed.

Repeat each marked scene at least twice, then build a conservative cross-scene
matrix from the runtime reports:

```powershell
python .\tools\summarize-native-renderer-dispatch-scenes.py `
    .local\qualification\dispatch-*.json `
    --output .local\qualification\native-dispatch-scenes.json
```

The scene summarizer rejects unsafe reports and duplicate sessions. It can
label a caller as a stable single- or multi-scene frequency candidate only
after repeated coverage, but it deliberately leaves `semantic_identity` as
`unknown` and both promotion and suppression disabled. Frequency is a lead for
object/lifetime investigation, not semantic proof.

## AppData qualification — 2026-08-29

Clean Release executable
`7FDD30F7FA8F8BDAFEC710770D55C5D91CE5CE59A62F5D7BD1DD3480B478B9A2`
ran against the installed `0.1.0` AppData save through menu, save load, and
live festival gameplay. Session `20260829T105816Z-p27600` exited normally.

The 7,500-frame capture observed 165,637 title-adapter calls from 14 runtime
callers and the same 165,637 calls through the indexed packet wrapper. All 15
runtime caller records matched the static callsite inventory; there were zero
unknown callers and zero caller-table overflow. Resolve controller/setup,
query begin/end, and immediate-draw wrappers were not observed in this scene.
The summary proves no guest payload read, guest-state mutation, control-flow
change, or suppression. All wrapper and caller identities therefore remain
packet-layer evidence, not semantic render-family identities.

Performance telemetry covered 233.758 seconds: median derived FPS was 30.472,
simulation cadence was 29.740 Hz, presentation cadence was 59.985 Hz, and
texture/pipeline cache hit rates were 99.975%/100%. No crash, fatal error,
device loss, or unexpected shutdown appeared. The local visual evidence is
`native-renderer-wrapper-families-open-world.png`, SHA-256
`93F34AF4AAEB1E75FF58A0E4F726343F70F33C868F6956577B551513D33DBF54`.

## Next promotion gate

A direct caller becomes a semantic hook candidate only after independent scene
captures show a stable association and the relevant object, instance,
material, transform, visibility, LOD, streaming, and destruction ownership is
understood. Required coverage remains world, vehicle, road, HUD, garage,
mirror, shadow, exposure, livery, thumbnail, and rewind.

Query begin/end, resolve setup/controller, and the indexed-wrapper dirty-state
clears are now proved. Resolve-draw ownership, query result ownership,
tiled-rendering, resource lifetime, and semantic caller identities remain open
title-side inventory work. Until those gates are met, all work stays on Xenos
and no new draw family may be suppressed.
