# Terrain and road render-path differential

Phase C1 starts from a title-owned control rather than assigning a semantic
name to a shader or draw-frequency cluster. Static analysis proves that the
retail executable registers `fasttrackrender`, `trackfardistance`,
`renderroaddetailblur`, and `notrackcommandbuffers` on the exact
`CForzaCommandLineParameters` object. The `perfmode` master option fans out to
`fasttrackrender` and eight neighboring fast-family flags, so it is not an
isolated terrain/road experiment.

## Exact configuration bridge

`tools/discover-native-renderer-track-config.py` validates the option strings,
RTTI, registration vtable slot, parser calls, field offsets, and the known
command-line-to-runtime copies. It fails closed if any instruction or image
identity drifts. The relevant title fields are:

| Option | Command-line field | Runtime field | Role |
| --- | ---: | ---: | --- |
| `fasttrackrender` | 4204 | 6297 | isolated title track-family switch |
| `trackfardistance` | 4176 | not yet proved | floating distance control |
| `renderroaddetailblur` | 4181 | 6035 | road-detail effect switch |
| `notrackcommandbuffers` | 2732 | 6230/6232 | inverted command-buffer control |

The runtime copy occurs in `sub_8259C7D8` after the title retrieves the live
command-line parameter object. The retail startup path does not consume
ReXGlue's `ExLoadedCommandLine` bridge for this object. The census therefore
uses an opt-in hook at the exact `fasttrackrender` copy instruction
(`0x8259C834`) to write `false` for the baseline and `true` for the paired
fast-track session. It changes only that title runtime byte and records its
original value. This proves a bounded title configuration path; it does not
yet prove which prepared signatures are terrain, road surface, track props, or
an exceptional dependent family.

Generate the payload-free static report with:

```powershell
python tools/discover-native-renderer-track-config.py `
  .local/generated/default `
  --image .local/analysis/default-image.bin `
  --output .local/qualification/native-renderer-track-config.json
```

## Paired runtime census

The census wrapper accepts `-TrackRenderMode baseline` or
`-TrackRenderMode fasttrackrender`. The exact runtime-copy hook forces only the
isolated `fasttrackrender` byte; it does not enable the broader `perfmode`
group. Explicitly supplying either mode also arms the exact prepared-draw
provenance required by the paired report. Run the
same AppData save and marked scene for both modes, then compare exact prepared
signatures and semantic submission lineage from the two logs.

```powershell
$stateRoot = Join-Path $env:LOCALAPPDATA `
  'PinyonShift\source\0.1.0\.local\preview'
.\tools\capture-native-renderer-census.ps1 `
  -StateRoot $stateRoot -Scene open_world_day -TrackRenderMode baseline
.\tools\capture-native-renderer-census.ps1 `
  -StateRoot $stateRoot -Scene open_world_day `
  -TrackRenderMode fasttrackrender
```

The delta is candidate evidence only. A family becomes a Phase C1 rendering
input only after the changed signature has exact semantic PM4 lineage,
mechanically valid replay, representative visual identification, and stable
coverage across open world and race scenes. Xenos remains authoritative, no
native draw or suppression is enabled by this checkpoint, and the capture
does not require any save-file operation.

After both sessions exit, build the strict normalized delta report:

```powershell
python tools/summarize-native-renderer-track-differential.py `
  --baseline <baseline-jsonl> `
  --fasttrackrender <fasttrackrender-jsonl> `
  --output .local/qualification/native-renderer-track-differential.json
```

The report requires distinct sessions from the same executable and patch set,
one shared marked scene, at least 600 frames per side, zero signature overflow,
normal shutdown, and runtime confirmation that the title accepted the requested
mode. It compares exact prepared procedural-model provenance in calls per 1,000
frames and retains shader, template, receiver-generation, and record identity
for each changed family. A complete report proves a title-owned track delta;
it deliberately leaves terrain/road semantic identity, native admission, and
suppression false.

## Qualified open-world differential

The AppData-backed `open_world_day` pair completed on the same local build:

- baseline session `20260830T233745Z-p15720`: 4,388 frames and 6,325,239
  draws;
- `fasttrackrender` session `20260830T234026Z-p31828`: 4,817 frames and
  7,471,561 draws;
- both runtime controls completed with the original title value `false`, the
  requested runtime value applied exactly, normal shutdown, and Xenos
  authority preserved; and
- the normalized report found 331 material exact-family deltas after removing
  504 low-rate jitter rows.

The paired evidence proves the title-owned track-render differential and gives
the next C1 slice a bounded candidate set. It does not identify all 331 rows as
terrain or roads: menu/loading variance and dependent families are still
present in the session-wide aggregates. Native admission therefore remains
disabled until representative candidates receive visual identification,
isolated replay, and open-world/race stability evidence.
