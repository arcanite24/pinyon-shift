# Guest-visible render dependencies

This is the evidence ledger for NR-00D on the supported USA retail MS-2505
executable. It describes what the renderer census proves, what remains unknown,
and which unknowns block future draw or resolve suppression.

## Safety conclusion

No render target is suppression-eligible yet. The census can prove that a
successful D3D12 resolve destination is sampled by a later vertex or pixel
shader texture fetch. It does not yet prove that an unsampled target is
presentation-only, that the guest CPU never reads it, or that it has no query,
memexport, livery, thumbnail, mirror, exposure, shadow, or rewind role.

Those missing facts keep Gate B closed. Xenos executes every draw and resolve,
and all observer APIs are read-only and default-off.

## Observation boundary

ReXGlue patch `0045-graphics-resolve-dependency-observer.patch` extends the
existing optional draw observer with texture-fetch addresses, conditional-draw
state, and visibility-query state. It also adds a D3D12 copy observer after the
existing resolve path returns. A copy record contains success, destination
address and length, frame/copy sequence, and bounded register metadata.

The observer does not contain shader code, texture bytes, constants, render
target contents, vertex/index data, or any other guest payload. When no
observer is registered, draw submission and resolve behavior are unchanged.

## Bounded dependency graph

The title-side census keeps two fixed-capacity tables for the lifetime of the
process:

- 4,096 resolve destinations keyed by guest physical base address.
- 32,768 guest 4 KiB pages mapped to the most recently resolved destination.

Each resolve range is page-indexed. Each later used base or mip texture fetch
looks up its page and is accepted only when its exact address remains inside
the destination's latest byte range. A draw is counted once per matched target,
even when multiple fetch constants refer to it. Page, target, failed-copy, and
zero-length overflow conditions are reported explicitly.

The graph emits one `native_renderer.census.resolve_dependency` transition the
first time each tracked target is sampled. This stream is bounded by the 4,096
target capacity. Every 300 emulated frames it also emits one aggregate
`resolve_window` record and at most 32 ranked `resolve_target` summaries. The
graph remains persistent across windows so a later scene can still link to an
earlier resolve.

## Current classification matrix

| Dependency question | Evidence available now | Current classification |
| --- | --- | --- |
| Later draw samples output | Resolve byte range matched against a used vertex/pixel base or mip fetch | `true` when observed; otherwise `unobserved`, not false |
| Final presentation only | No native presentation-source observer yet | `unknown_uninstrumented` |
| Guest CPU reads output | No bounded shared-memory read observer yet | `unknown_uninstrumented` |
| Query depends on output | Conditional and active visibility-query state are correlated with sampling draws, but causality is not established | `related_draw_observed` or `unknown_uninstrumented` |
| Memexport interaction | Sampling draws record whether the vertex shader has memexport | Correlation only; never proof of independence |
| Livery / thumbnail / mirror / exposure / shadow / rewind | No pass classifier has assigned semantic roles yet | `unknown_unclassified` |
| Safe to suppress | Requires all relevant dependencies to be replaced or proven unnecessary | `false` |

An address absent from the dependency stream is not proof that it is
presentation-only. Capacity overflow, an unobserved CPU read, a non-texture
consumer, or an unclassified scene role may still exist.

## Capture and inventory workflow

Run the default-off census through the normal preview launcher. With the
installed save, the explicit command is:

```powershell
.\tools\capture-native-renderer-census.ps1 `
  -StateRoot "$env:LOCALAPPDATA\PinyonShift\source\0.1.0\.local\preview"
```

The wrapper verifies that the selected state root contains a `ForzaProfile`,
refuses to launch over an existing process, sets only the census cvar for that
child run, and delegates to `tools/launch-preview.ps1`. If `-StateRoot` is
omitted, it selects the newest installed preview profile without copying or
changing the save.

Convert the diagnostic JSONL to a deterministic inventory with:

```powershell
$eventLog = Get-ChildItem "$stateRoot\logs\*.jsonl" |
  Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
python .\tools\summarize-native-renderer-census.py `
  $eventLog.FullName `
  --output ".artifacts\native-renderer-census.json"
```

The summarizer selects the latest census-enabled session unless `--session` is
provided. Its output includes aggregated draw signatures, every emitted
resolve target, every observed resolve-to-texture dependency, overflow totals,
and an explicit safety object that keeps suppression disabled. Retaining the
target inventory lets later candidate selection reject a texture address even
when the draw-window dependency bit did not observe the transition.

## Qualification status

The NR-00D implementation was qualified with AppData-backed session
`20260828T002134Z-p41584` on clean commit `d9a0d60`. The run reached 1,500
emulated frames and exited normally. Its deterministic inventory reported:

- 83,401 observed draws across 11 signatures.
- 2,802 successful resolves totaling 10,558,832,640 bytes.
- 1,397 later draws sampling a resolved target.
- Two distinct resolve-to-texture dependency transitions.
- Zero draw, target, and page-capacity overflows.
- Zero crash, GPU-loss, and fatal diagnostic events.

The clean executable SHA-256 was
`D4A415992CF893553CF6AD6CF4821B8169EC8B741607D553BEE6E78162414662`.
The machine-readable inventory remains a local evidence artifact because its
source log contains machine-specific paths and session identifiers.

Gate B remains closed after this capture. CPU-read observation, presentation
provenance, and semantic classification are separate evidence tasks, not facts
that may be inferred from the absence of a texture-fetch match.
