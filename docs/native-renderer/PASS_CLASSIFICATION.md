# Native-renderer pass classification

This is the NR-00E classifier contract for the supported USA retail MS-2505
executable. It classifies census identities from evidence; it does not infer
semantic roles from resolution, pitch, shader hashes, or timing alone.

## Safety model

The tracked manifest at `config/native-renderer/pass-classifier.json` matches
an exact draw signature only within an operator-selected scene. Each rule has a
family, confidence, and evidence string. A signature with no exact rule is
`retained_unknown`, remains on Xenos, and is never suppression-eligible.

Classification is report-only. It cannot skip a draw, redirect a resolve, read
guest payloads, or submit native graphics work. Gate B remains closed.

## Scene markers

The capture wrapper accepts one of these bounded operator markers:

- `front_end`
- `garage`
- `open_world_day`
- `open_world_night`
- `traffic`
- `race`
- `rewind`
- `pause`
- `save_reload`
- `unmarked`

For example:

```powershell
.\tools\capture-native-renderer-census.ps1 `
  -StateRoot "$env:LOCALAPPDATA\PinyonShift\source\0.1.0\.local\preview" `
  -Scene front_end
```

The marker is passed only to the child process and recorded as
`native_renderer.census.scene_marker`. Invalid or missing runtime values become
`invalid` or `unmarked`; they cannot accidentally match another scene.

## Drift and reports

`summarize-native-renderer-census.py` joins the marker, draw census, dependency
graph, and tracked classifier. Its deterministic output contains:

- classified and observed draw counts plus coverage percentage;
- draw totals by pass family;
- the evidence and confidence attached to every matched signature;
- at most 32 unmatched drift records, ordered by draw count;
- an explicit drift-overflow count; and
- the `retained_on_xenos` unknown policy.

The manifest currently recognizes only the 11 exact signatures from qualified
front-end session `20260828T002134Z-p41584`. They are named
`front_end_observed` at medium confidence: the scene and identity are proven,
but their finer UI, composite, clear, and presentation roles are not. No rule
exists yet for garage, world, traffic, race, rewind, pause, or save/reload.

## Promotion rule

A drift signature may enter the manifest only after a reproducible marked
capture identifies it, the associated targets and dependencies are reviewed,
and its evidence is recorded. A semantic family requires stronger hook or
visual evidence than recurrence alone. Changing classification never changes
rendering behavior; suppression has separate gates and remains forbidden in
NR-00.
