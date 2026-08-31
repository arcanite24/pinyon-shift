# Combined C1/C2 qualification gate

Status: implementation complete; first clean AppData batch pending

The combined gate turns one exact runtime session into a single promotion
decision. It joins four independently strict, payload-free reports:

- unified track render-model, generation-safe procedural-receiver handoff, and
  shared world-resource identity;
- complete SimpleModel presentation/resource/mesh lineage;
- runtime transform classification against the title-authored spatial catalog;
  and
- swap-committed continuous output with exact C1 and C2 selection enabled.

Every input must have status `complete`, name the same session, contain no
failures, and preserve its safety boundary. Track, static-world, and continuous
output reports must prove a final shutdown summary; periodic checkpoints are
useful for diagnosis but cannot satisfy this gate.

Launch the combined profile with the installed AppData save:

```powershell
$stateRoot = Join-Path $env:LOCALAPPDATA `
  'PinyonShift\source\0.1.0\.local\preview'
./tools/capture-native-renderer-census.ps1 `
  -StateRoot $stateRoot -PhaseCQualification -Json
```

The profile selects `open_world_day` unless a scene is supplied, enables the
continuous exact track and static-world selectors together, and arms title
draw provenance for the passive C4 player/material joins. It deliberately
does not request the isolated per-resource vehicle readback: shadow-depth
capture and the continuous workset are mutually exclusive, so conflating them
would invalidate both gates.

Run the four component qualifiers first, then join them:

```powershell
python tools/summarize-native-renderer-c1-c2-batch.py `
  --track .local/qualification/track-model-runtime-join.json `
  --static-world .local/qualification/static-world-runtime-join.json `
  --classification .local/qualification/static-world-classification.json `
  --workset .local/qualification/continuous-world-workset.json `
  --output .local/qualification/c1-c2-batch.json
```

A complete report proves exact C1 track-world and classified C2 static-world
draws reached fresh, multi-draw, swap-committed native output in one clean
session while every Xenos draw remained intact. It deliberately does not claim
manual visual acceptance, race coverage, representative high-speed streaming,
family promotion, or suppression. Those remain the next gates.

This report never reads or modifies the AppData save and cannot enable runtime
behavior. It only joins existing payload-free evidence.
