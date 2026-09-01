# Direct indexed-draw producers and the live C2 candidate

Status: static producer inventory proved; batched runtime qualification pending

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

The runtime observer at `82416380` is armed only with census plus dispatch
discovery. It counts all 13 exact return-address families and, only for
`82C5B038`, requires `r26` vtable `8200143C` (`CTrackMesh`) before retaining a
bounded 4,096-entry table of mesh address plus 16 numeric transform words. It
does not run during ordinary prototype gameplay.

Generate the static report with:

```powershell
python tools/discover-native-renderer-direct-indexed-producers.py `
  .local/generated/default `
  --image .local/analysis/default-image.bin `
  --output .local/qualification/native-renderer-direct-indexed-producers.json
```

## Next batched gate

The next combined AppData session must establish that `82C5B038` is active,
that every observation has the exact `CTrackMesh` vtable and a finite mapped
transform, and that the transform table has no overflow. Those transforms can
then be evaluated against the already-built collision-prop and gameplay-object
catalog to determine whether this live track-owned path supplies C2's concrete
building/prop identity.

The fail-closed runtime qualifier requires a clean process lifecycle, all 13
producer records, zero unknown callers, at least eight distinct transforms,
and complete observation accounting:

```powershell
python tools/summarize-native-renderer-direct-indexed-producers.py `
  .local/preview/logs/<session>.jsonl `
  --session <session> `
  --output .local/qualification/native-renderer-direct-indexed-runtime.json
```

Until that evidence exists, this is a candidate ingress only. It enables no
native admission, guest publication, Xenos suppression, or building/prop
claim; Xenos remains authoritative.
