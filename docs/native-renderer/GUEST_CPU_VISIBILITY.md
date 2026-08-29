# Exact pass-family guest CPU visibility

NR-00D requires evidence for guest CPU reads of render-target output before a
pass family can be considered for suppression. The retained sky/horizon family
now has a bounded, default-off observer for that question. Xenos remains the
only authoritative renderer and no draw, resolve, query, or guest-memory side
effect is suppressed.

## Observation boundary

ReXGlue patch `0074-physical-memory-read-observer.patch` adds one-shot access
notifications to explicitly armed physical-memory pages. A real guest CPU read
or write faults the protected alias, reports the physical page range and access
kind, retires that page's access watch, and restores the least-permissive
protection still required by existing write-invalidation watches.

Host-side explicit invalidations do not dispatch the access observer. The
observer never reads or serializes guest payload bytes, and the existing write
invalidation contract remains active independently.

The title arms only successful resolve destinations produced by the exact pair:

- anchor `747837906D0BF484`;
- follower `1D253A52B55C9FB3`.

The process-scoped table is limited to 64 distinct physical base addresses.
Each entry records resolve generations, page-level read and write events, and
the number of distinct resolve generations touched by each access kind. A CPU
write before a read is retained as overwrite evidence, not misclassified as a
read dependency.

## Admission interpretation

The summarizer emits `guest_cpu_visibility` as:

- `fail` when at least one armed resolve generation is read by the guest CPU;
- `pass` when every exact-family resolve was armed, the table did not overflow,
  and no guest CPU read was observed in the selected qualification session;
- `unknown` when arming or bounded coverage is incomplete.

A `pass` is evidence for the selected scene and route only. It does not override
the independent later-GPU-consumer gate, which currently fails, or authorize
suppression by itself.

## Capture workflow

Use the AppData-backed census launcher with the exact pair:

```powershell
.\tools\capture-native-renderer-census.ps1 `
  -StateRoot "$env:LOCALAPPDATA\PinyonShift\source\0.1.0\.local\preview" `
  -Scene open_world_day `
  -PassAnchorSignature 747837906D0BF484 `
  -IsolatedDrawSignature 1D253A52B55C9FB3
```

After a normal exit, summarize the emitted JSONL with:

```powershell
python .\tools\summarize-native-renderer-pass-consumers.py `
  "$stateRoot\logs\<session>.jsonl" `
  --output .artifacts\native-renderer-pass-consumers.json
```

## Qualified open-world result

The 2026-08-29 batched AppData-backed `open_world_day` run used executable
SHA-256 `F3E8DEF38B0AF876D1AD053067E33E7C63A255BA0237562162C061E01EBA14D4`
and session `20260829T053639Z-p40004`. The clean replacement build recorded
all 74 ReXGlue patches. The run reached the saved festival scene, rendered for
an additional 30-second observation window, and exited normally with no error,
fatal, crash, exception, or device-loss event.

The schema-v3 deterministic inventory reported:

- 348 exact-family resolves totaling 91,226,112 bytes;
- six rotating 262,144-byte guest physical destinations;
- all 348 resolve generations armed, with zero target-table overflow;
- zero guest CPU read page events and zero read generations; and
- zero guest CPU write page events and zero write generations.

This promotes `guest_cpu_visibility` to `pass` for this exact build, saved
scene, and observation route: `0 of 348 armed resolve generations were read by
the guest CPU`. It is not a global proof that no other scene reads the output.
The independent `later_gpu_consumers` gate still fails, so suppression remains
prohibited and every Xenos draw and resolve remains authoritative.

The local deterministic inventory SHA-256 is
`B58B6D100EE3BBD83B6DD4EA04CC079D2BC93211F4CABC3E6CD09CE12FDD5B80`.
It remains local because its source field contains a machine-specific path.
Performance telemetry from the same 153.13-second process contained 5,143
samples with median 30.606 FPS, 18.802 FPS one-percent low, zero present
deadline misses, and zero native GPU timing drops.
