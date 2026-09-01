# Direct indexed-draw producers and the live C2 candidate

Status: producer-to-prepared provenance implemented; tested candidate inactive

## Why C2 changed direction

The clean combined session `20260901T011508Z-p39720` proved that the original
`CSimpleModelRenderer` route is dormant in the tested festival/open-world
population. Two renderer instances were constructed, but neither was bound or
dispatched, the `CSimpleModelResource` factory was never reached, and the live
track command graph contained no direct or nested SimpleModel-family identity.

The next C2 boundary therefore starts at a draw-producing edge rather than
adding more assumptions to that dormant object graph.

## Exact producer inventory

`tools/discover-native-renderer-direct-indexed-producers.py` proves every
static direct call to title indexed-draw emitter `82416380`. There are exactly
13 callsites across 11 functions. Their guest return addresses form a small,
closed runtime discriminator; no shader, frequency, or texture heuristic is
needed.

One producer is the exact unified track-presentation mesh helper `82C5ADC0`.
Its direct draw returns to `82C5B038`. Static instruction flow proves that:

- preserved `r26` is the selected mesh passed into the helper;
- the helper binds `r26 + 96`, reads primitive type at `r26 + 36`, and reads
  source element count at `r26 + 100` before the draw;
- preserved `r31` is the live 64-byte transform whose float rows are uploaded
  immediately before the draw; and
- the upstream `82DED198 -> 82436468` route is owned by exact RTTI-proved
  `Presentation_Unified::CTrackPresentation` methods.

The runtime observer at `82416380` and its exact common exit at `824167EC`
are armed only with census plus dispatch
discovery. It counts all 13 exact return-address families and, only for
`82C5B038`, requires `r26` vtable `8200143C` (`CTrackMesh`) before retaining a
bounded 4,096-entry table of mesh address plus 16 numeric transform words. It
does not run during ordinary prototype gameplay.

The balanced scope now attaches that exact mesh and transform to the
synchronously emitted `PM4_DRAW_INDX` packet. Existing physical-packet
provenance then carries it into the prepared backend draw. Entry/exit,
scope-to-packet, and packet-to-prepared counters must all balance; any overlap,
missing packet, unprepared match, read fault, or unknown caller fails closed.

Generate the static report with:

```powershell
python tools/discover-native-renderer-direct-indexed-producers.py `
  .local/generated/default `
  --image .local/analysis/default-image.bin `
  --output .local/qualification/native-renderer-direct-indexed-producers.json
```

## Runtime result

Clean AppData session `20260901T022910Z-p35168` completed normally in the
festival world with Xenos authoritative. All 68,356 direct indexed-draw scopes
balanced, all observations belonged to the closed 13-caller inventory, and no
scope overlap, missing exit, unknown caller, or accounting failure occurred.
The exact `82C5B038` unified-track helper recorded zero calls. The dormant
`82C4DC58` SimpleModel helper also remained at zero.

The active direct families were vector font (50,974), D3D9 device (10,589),
and generic title graphics helpers (6,793). None supplies the RTTI-proved
static-world instance and transform contract required by C2. The exact unified
track edge is therefore retained as safe passive instrumentation, but it is not
the active road or building/prop ingress in this representative saved scene.
No catalog classification was attempted from an empty exact population.

## Deferred recheck gate

Any future scene-specific recheck must establish that `82C5B038` is active,
that every observation has the exact `CTrackMesh` vtable and a finite mapped
transform, and that every exact scope reaches a prepared draw. The existing
offline instance classifier now accepts `--origin unified_track_mesh`; it tests
both plausible matrix conventions against the already-built collision-prop and
gameplay-object catalog without exporting plaintext identity.

The fail-closed runtime qualifier requires a clean process lifecycle, all 13
producer records, zero unknown callers, at least eight distinct transforms,
and complete observation accounting:

```powershell
python tools/summarize-native-renderer-direct-indexed-producers.py `
  .local/preview/logs/<session>.jsonl `
  --session <session> `
  --output .local/qualification/native-renderer-direct-indexed-runtime.json

python tools/summarize-native-renderer-static-world-instance-classification.py `
  .local/preview/logs/<session>.jsonl `
  --catalog .local/qualification/native-renderer-static-world-instance-catalog.json `
  --origin unified_track_mesh `
  --session <session> `
  --output .local/qualification/native-renderer-track-mesh-classification.json
```

Until that evidence exists, this remains an inactive candidate ingress only. It enables no
native admission, guest publication, Xenos suppression, or building/prop
claim; Xenos remains authoritative.
