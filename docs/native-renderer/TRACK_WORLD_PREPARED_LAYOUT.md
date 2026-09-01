# Track-world prepared-layout census

Status: implemented; capacity correction awaits one batched AppData rerun

## Why this is the next C1 boundary

The clean festival-world census proved that the direct unified-track mesh edge
is dormant in the tested scene. The live path is instead the exact indirect
track command lineage: 485 balanced scopes and packets reached 732 prepared
draws in session `20260901T022910Z-p35168`.

Those prepared draws already contain the shader-decoded vertex layout,
resources, render state, and numeric constants required to look for a concrete
world-transform contract. Capturing that bounded metadata is more useful than
adding semantic guesses to the two active generic direct-draw helpers.

## Runtime boundary

For every prepared draw reached while the exact track command context is
active, the observer records one of three outcomes:

- bounded geometry and parameter layout;
- unbounded geometry; or
- float-constant, texture-layout, or texture-state overflow.

At most 1,024 distinct layout families are retained. A family key includes the
exact track root, child, descriptor, and descriptor payload plus the prepared
pipeline, geometry-layout, texture-layout, and render-state hashes. Each entry
keeps one bounded metadata sample, its frame/call coverage, and parameter-hash
variation. It never copies vertex, index, texture, or guest object payloads.

Detailed entries are emitted only in the final clean-shutdown path. Periodic
track checkpoints contain cumulative counters but no entry dump, keeping long
sessions bounded and avoiding repeated log volume.

## Offline report

After the next batched AppData run:

```powershell
python tools/summarize-native-renderer-track-prepared-layout.py `
  <session.jsonl> `
  --output .local/qualification/native-renderer-track-prepared-layout.json
```

The report verifies process lifecycle, safety fields, exact command/prepared
accounting, boundedness, table capacity, and per-entry call totals. It also
lists vertex/pixel float-constant register frequency and maximal runs of at
least four consecutive finite vertex registers.

The checked-in catalog classifier then evaluates every four-register window
under both plausible title matrix conventions:

```powershell
python tools/classify-native-renderer-track-prepared-transforms.py `
  --prepared .local/qualification/native-renderer-track-prepared-layout.json `
  --catalog .local/qualification/native-renderer-static-world-instance-catalog.json `
  --output .local/qualification/native-renderer-track-prepared-transforms.json
```

Candidates are grouped by exact vertex shader, starting constant register, and
matrix convention. A group passes only when every observed layout maps to one
unambiguous catalog position, at least eight distinct catalog instances match,
at least one is a collision prop, and exactly one group satisfies the whole
contract. Shader similarity, frequency, near misses, and duplicate catalog
positions cannot qualify it.

These runs are candidates, not transforms. C1 advances only after recurring
runs are compared across changed camera/vehicle poses and matched to the static
world transform catalog without ambiguity. Until then, terrain/road identity,
native admission, publication, and suppression remain unproved and disabled.

## First runtime result

Clean AppData session `20260901T030124Z-p12228` reached the saved festival
world, retained 512 exact families from 732 prepared draws, and reported 54
additional observations after the original table filled. Geometry and
parameter metadata stayed bounded: there were zero unbounded-geometry and zero
parameter-overflow observations. The 512-entry assumption, rather than the
exact join, was therefore too small for this scene.

The census capacity is now 1,024 entries. This remains a fixed startup
allocation and comfortably covers the first run's worst case of 566 distinct
families while preserving fail-closed overflow accounting. A new clean run is
required before transform classification can qualify, because the classifier
correctly rejects any incomplete source census.

An immediately preceding identical launch, session
`20260901T025802Z-p39560`, hit the existing intermittent guest null dereference
at RVA `0x48844D8` while loading the world, before any track prepared-layout
observation was recorded. The controlled retry reached gameplay and exited
normally, so that fault is not attributed to this observer.

## Safety

- Xenos draws and output remain authoritative.
- No guest state or control flow is changed.
- No native draw is admitted from this census.
- No suppression path is armed.
- The capture uses the existing AppData save in place.
