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
command-line parameter object. This proves a bounded title configuration path.
It does not yet prove which prepared signatures are terrain, road surface,
track props, or an exceptional dependent family.

Generate the payload-free static report with:

```powershell
python tools/discover-native-renderer-track-config.py `
  .local/generated/default `
  --image .local/analysis/default-image.bin `
  --output .local/qualification/native-renderer-track-config.json
```

## Paired runtime census

The census wrapper accepts `-TrackRenderMode baseline` or
`-TrackRenderMode fasttrackrender`. The latter passes only the title argument
`-fasttrackrender`; it does not enable the broader `perfmode` group. Run the
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
