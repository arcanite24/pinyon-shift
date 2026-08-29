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
Each wrapper opens with `mflr r12`; the hook on the following instruction
observes the caller `LR` through `r12` plus unchanged entry `r3`, `r4`, and
`r5`. A fixed 256-entry atomic table aggregates caller frequency; it does not read guest
resource payloads or write guest state. The original wrapper, PM4 packet,
Xenos draw, arguments, registers, and control flow are preserved. Discovery
records are never suppression evidence.

## Proved draw wrappers

The generated AOT instruction inventory establishes these two runtime wrapper
families:

| Entry | Packet construction | Reviewed identity | Runtime observation |
| --- | --- | --- | --- |
| `0x8240F4D8` | At `0x82410320`, combines a dynamic Type-3 count with opcode `0x36` and stores the resulting `PM4_DRAW_INDX_2` header | Indexed draw wrapper | Hook `0x8240F4DC`: entry `LR` in `r12`, plus `r3-r5` |
| `0x829F7C70` | At `0x829F7CA8`, stores fixed Type-3 count-one header `0xC0003600`, followed by embedded index/draw metadata | Immediate/embedded-index draw wrapper | Hook `0x829F7C74`: entry `LR` in `r12`, plus `r3-r5` |

Three additional opcode-`0x36` constructors at `0x829E82D0`, `0x829E8428`,
and `0x829EDB68` build initialization templates. They are inventoried but are
not runtime draw hooks.

No `PM4_DRAW_INDX` (`0x22`) title constructor has yet passed the same stored-
header proof. The scanner reports only proved stored opcode-`0x36` headers and
explicitly rejects a matching numeric operation in `sub_83051E48` because its
result is not stored as a command packet.

## Static direct callers

`tools/discover-native-renderer-dispatch.py` scans all generated AOT C++ files,
reconstructs instruction addresses from function entries and labels, and
produces a deterministic payload-free JSON inventory. At the current baseline
it finds 11 direct call sites:

| Wrapper | Caller function | Call site | Entry `LR` |
| --- | --- | --- | --- |
| `0x8240F4D8` | `sub_824079B8` | `0x824079F8` | `0x824079FC` |
| `0x8240F4D8` | `sub_82B2B180` | `0x82B2BD74` | `0x82B2BD78` |
| `0x8240F4D8` | `sub_82B40E60` | `0x82B42294` | `0x82B42298` |
| `0x8240F4D8` | `sub_82B425B0` | `0x82B4386C` | `0x82B43870` |
| `0x8240F4D8` | `sub_82B425B0` | `0x82B44420` | `0x82B44424` |
| `0x8240F4D8` | `sub_82B425B0` | `0x82B44740` | `0x82B44744` |
| `0x8240F4D8` | `sub_82B425B0` | `0x82B4478C` | `0x82B44790` |
| `0x8240F4D8` | `sub_82B425B0` | `0x82B449C0` | `0x82B449C4` |
| `0x8240F4D8` | `sub_82B425B0` | `0x82B44A00` | `0x82B44A04` |
| `0x829F7C70` | `sub_829F8D88` | `0x829F93F0` | `0x829F93F4` |
| `0x829F7C70` | `sub_829F9540` | `0x829F9980` | `0x829F9984` |

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

## AppData qualification — 2026-08-29

Clean Release executable
`67794B647E91049F9B818EFFC21053527520DFCB78F48A0E28B7182A9CF3FCFA`
ran against the installed `0.1.0` AppData save through menu, save load, and
live festival gameplay. Session `20260829T102356Z-p41836` exited normally.

The 5,302-frame capture observed 110,057 indexed-wrapper calls, all from entry
`LR` `0x824079FC`. Static correlation resolves that address to the sole call at
`0x824079F8` in `sub_824079B8`. The caller table had zero overflow, the immediate
wrapper was not observed, and the summary proves no guest payload read, guest
state mutation, control-flow change, or suppression. This promotes
`sub_824079B8` to the next wrapper-layer discovery seed, not to a semantic
render-family identity.

Performance telemetry covered 152.765 seconds: median derived FPS was 30.755,
simulation cadence was 29.621 Hz, presentation cadence was 59.988 Hz, and
texture/pipeline cache hit rates were 99.978%/100%. No crash, fatal error,
device loss, or unexpected shutdown appeared. The local visual evidence is
`native-renderer-dispatch-appdata-20260829.png`, SHA-256
`F0368B13C31951126D6B87ECA24A904CD718B79C59AEB20D0B11C83E42777E79`.

## Next promotion gate

A direct caller becomes a semantic hook candidate only after independent scene
captures show a stable association and the relevant object, instance,
material, transform, visibility, LOD, streaming, and destruction ownership is
understood. Required coverage remains world, vehicle, road, HUD, garage,
mirror, shadow, exposure, livery, thumbnail, and rewind.

Resolve, query, tiled-rendering, resource-lifetime, and dirty-state-clear
wrappers remain open title-side inventory work. Until those gates are met,
all work stays on Xenos and no new draw family may be suppressed.
