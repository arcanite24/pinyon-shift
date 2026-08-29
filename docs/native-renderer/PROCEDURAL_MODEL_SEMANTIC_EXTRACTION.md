# Procedural-model semantic extraction

This NR-05B slice establishes a bounded, immutable semantic-instance census
at the first proved per-record helper of
`proceduralGeometry::CProceduralModels`. It extracts title records without
rendering them. Every observed instance stays on Xenos replay until mesh,
material, LOD, and streaming semantics are classified.

## Exact title boundary

Virtual slot 40 (`824170D8`) loads the descriptor index from its work node,
stores it at caller stack offset 84, keeps the live `CProceduralModels`
receiver in `r3`, and calls helper `82417418`. The hook at `8241741C` observes
the helper after its link-register save and before it changes the relevant
entry arguments.

The helper's 272-byte stack frame makes its later load at callee offset 356
the same original caller offset 84. Static instructions then derive:

| Semantic input | Exact derivation |
| --- | --- |
| Receiver generation | exact live constructor/destructor join for entry `r3` |
| Record index | guest word at entry `r1 + 84` |
| Descriptor count | guest word at `receiver[124][12]` |
| Descriptor record | `receiver[124][0] + index * 92` |
| Runtime record | `receiver[128] + index * 68` |
| Structural kind | descriptor word at byte offset 36 |
| Transform/constants | receiver byte ranges 320–511 |
| Helper context | entry `r4-r10` |

`tools/discover-native-renderer-dispatch.py` refuses to publish the extraction
contract unless this argument flow and record-address derivation are present
in the supported generated title source.

## Immutable bounded census

The runtime observer first requires an exact live receiver address and
generation. It rejects zero, unaligned, overflowing, or out-of-range record
layouts before reading a record. Each valid observation reads exactly:

- 23 descriptor words (92 bytes);
- 17 runtime words (68 bytes);
- 48 transform/constant words (192 bytes);
- seven helper registers and the structural scalar fields already listed.

The guest payload bound is 380 bytes per live observation, including the
index word and owner/base/count words. A fixed 4,096-entry open-addressed table
is keyed by receiver address, generation, and record index. The first 88
record/transform words are immutable samples. Later observations update only
call/frame counts and hash-variation counters, so a changing runtime record or
transform never rewrites the captured first instance.

The runtime emits one `semantic_instance_entry` per retained key and one
`semantic_instance_summary`. The fail-closed report tool is:

```powershell
python tools/summarize-native-renderer-semantic-instances.py `
  <diagnostic-jsonl> `
  --static <native-renderer-dispatch-static.json> `
  --session <session> `
  --output <semantic-instance-report.json>
```

A complete report requires exact accounting, at least one instance, zero
unknown receivers, invalid layouts, invalid indices, table overflow, and
native admissions. It also requires every live observation to retain
`xenos_replay` and the 380-byte read bound.

## Safety boundary

This is semantic extraction with no rendering. The observer performs bounded
guest reads only. It does not mutate guest memory, upload a native resource,
issue a native draw, change title control flow, or suppress Xenos work. An
unclassified material or state always uses Xenos replay.

The census proves stable record identity and captures the inputs needed for
the next classification batch. It does not yet identify mesh buffers,
materials, textures, visibility bits, LOD policy, or streaming ownership.
Those meanings must be proved before an instance is eligible for native
admission or batching.

## AppData qualification

Release executable SHA-256
`0A69A3D1C1E8DFE4625762F2A4F37B942441FC854BD047EA5BEF240066C751B0`
ran against the installed `0.1.0` preview save in session
`20260829T173833Z-p40812`. The save loaded into the festival world and the
process exited cleanly after 6,636 measured frames (204.704 seconds).

The semantic-instance and command-lineage reports are both `complete`:

- 557,009 live helper observations resolved into 463 immutable instance keys;
- all 557,009 retained Xenos replay, with zero native admissions;
- zero unknown receivers, invalid layouts, invalid indices, or table overflow;
- 211,663,420 bytes reconciled exactly at 380 bounded guest bytes per live
  observation;
- descriptor kinds 0, 4, 1, and 5 appeared across 308, 108, 43, and 4 keys;
- immutable descriptor samples did not vary, while runtime and transform
  hashes recorded 288,017 and 556,475 changes without rewriting first samples;
- 6,367,265 prepared draws retained complete command lineage, with zero
  invalid lineage or overflow.

Performance held a 30.259 FPS median with a 19.294 FPS one-percent low,
50.303 ms p95 frame time, 59.891 Hz presentation cadence, zero present-
deadline misses, and zero XMA stalls. The AppData gameplay frame is
`native-renderer-semantic-extraction-appdata.jpg` (SHA-256
`F4E287C36689A19D7266310C9ADAC720D51D26A1FA60269B8569578E7A06CC62`).
The semantic report SHA-256 is
`1145C68AA778FCEEBDC81793163A8F99A78DEC0E14D9644CAA936CD2CE44BD6B`.
