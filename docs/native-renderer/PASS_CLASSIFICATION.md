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

## Qualification snapshot — 2026-08-27

Clean commit `6460ea8` was launched against the installed AppData save with
the `front_end` marker. Session `20260828T002957Z-p39648` reached 1,500 frames,
exited normally, and produced this deterministic report:

- 83,665 observed and classified draws (100% coverage).
- One `front_end_observed` family and zero drift signatures.
- 2,890 resolves and two resolve-to-texture dependencies.
- Zero classifier overflow, census overflow, crash, GPU-loss, or fatal events.

The clean executable SHA-256 was
`67F27E6E3039DB1B79606F18EA62F03DD4F3ED40BFD0B5405DE2A22B2D22F748`.

An equal-duration census-disabled control run used the same build and save.
After discarding 120 warm-up samples, the enabled/control comparison was:

| Mode | Samples | Median frame time | p95 frame time | Median FPS |
| --- | ---: | ---: | ---: | ---: |
| Census disabled | 1,319 | 16,620 us | 18,606 us | 60 |
| Census + classifier capture | 1,421 | 16,630 us | 18,643 us | 60 |

The observed deltas were 10 us at median (0.06%) and 37 us at p95 (0.20%).
This front-end result proves the disabled path has no material overhead in the
captured scene; it does not replace the required open-world and race captures.

## Exact consumer-family extension

The retained sky/horizon producer has a separate exact shader-family classifier
for its later GPU consumers. It is documented in
[CONSUMER_FAMILY_CLASSIFICATION.md](CONSUMER_FAMILY_CLASSIFICATION.md) and does
not change this draw-signature manifest. Its 38 initial rules prove identity
only, retain unknown semantics and false native coverage, emit bounded drift,
and cannot affect rendering or suppression.
