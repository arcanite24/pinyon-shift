# Exact pass-family consumer graph

This document records the bounded later-GPU-consumer inventory for the retained
sky/horizon family selected by anchor signature `747837906D0BF484` and follower
signature `1D253A52B55C9FB3`. The inventory is diagnostic only: Xenos executes
every draw and resolve, and suppression remains disabled.

## Observation contract

When the exact adjacent family occurs, the census retains its EDRAM surface and
color/depth target identity. A later successful Xenos copy is attributed to the
family only when its selected copy source exactly matches that identity. The
existing guest-physical page map then links each resolve destination to later
used base or mip texture fetches.

Raw fetch observation is provisional. A consumer enters the graph only after
the backend reports its prepared draw, so an async-compilation skip cannot be
misclassified as executed guest GPU work. Provisional matches discarded before
preparation are counted separately in the shutdown summary.

The implementation keeps fixed-capacity state:

- 4,096 resolve destinations and 32,768 guest pages from the dependency census.
- 1,024 exact consumer draw signatures for the selected family.
- 64 resolve/first-consumer detail examples.

Every unique consumer signature receives an aggregate record at shutdown with
its shader hashes, specialization masks, prepared pipeline identity, geometry
shape, pipeline state, and the base/mip fetch slots that consumed the family
output. The shutdown summary independently counts present and missing prepared
metadata. The summarizer groups pipeline variants by exact shader
specialization, assigns a stable family identifier and activity rank, and
leaves semantic role and native coverage fail-closed. A signature-table
overflow makes the deterministic inventory incomplete. Missing prepared
metadata makes classification incomplete. Detail overflow only truncates
examples; it does not discard the aggregate signature graph. An unobserved
consumer is never interpreted as proof of independence.

Convert a completed diagnostic JSONL log with:

```powershell
python .\tools\summarize-native-renderer-pass-consumers.py `
  $eventLog `
  --anchor 747837906D0BF484 `
  --follower 1D253A52B55C9FB3 `
  --output .artifacts\native-renderer-pass-consumers.json
```

The command rejects missing shutdown summaries, signature/count conflicts, and
any event that does not preserve Xenos authority and prohibit suppression.

## Qualified open-world result

The latest 2026-08-29 AppData-backed `open_world_day` run used executable
SHA-256 `F3E8DEF38B0AF876D1AD053067E33E7C63A255BA0237562162C061E01EBA14D4`
and session `20260829T053639Z-p40004`. It exited normally with no error, fatal,
crash, or device-loss event. The deterministic inventory reported:

- 8,892 exact family occurrences.
- 348 matching color-source resolves totaling 91,226,112 bytes.
- Six rotating 262,144-byte guest destinations.
- 342 resolves sampled before replacement by a later resolve.
- 9,229 prepared resolve-to-consumer draws and texture references.
- 63 distinct prepared consumer draw signatures grouped into 38 exact shader
  specialization families, with zero signature overflow and zero missing
  prepared metadata.
- 48 provisional fetch matches discarded because the backend did not reach the
  prepared-draw stage; these are not classified as GPU consumers.
- Zero query-correlated and zero memexport-correlated sample events.
- Six outputs overwritten without a sampled consumer in the observed interval.

The local inventory SHA-256 is
`B58B6D100EE3BBD83B6DD4EA04CC079D2BC93211F4CABC3E6CD09CE12FDD5B80`.
It remains local because it includes a machine-specific diagnostic source path.

The leading shader family used vertex shader `2E5E0A854BE00027` and pixel
shader `BDFFA72B7ED2FBA4`; its two pipeline variants accounted for 1,186
prepared consumer draws. This broad 38-family fan-out proves that the selected
output is not a presentation-only leaf.

Performance telemetry contained 5,143 samples: median 30.606 FPS, 1% low
18.802 FPS, zero present-deadline misses, and zero native GPU timing drops.
The diagnostic table therefore did not disturb the established 30 FPS cadence
in this qualification.

## Suppression consequence

The `later_gpu_consumers` admission gate is now `fail`, not `unknown`: later
GPU consumers are positively observed and have not been replaced. This is
useful closure of the dependency question, but it prohibits suppressing the
producer family. The 38 stable shader families now have exact identity-only
rules in
[CONSUMER_FAMILY_CLASSIFICATION.md](CONSUMER_FAMILY_CLASSIFICATION.md).
They deliberately remain `retained_unknown` with `native_coverage=false` until
reproducible visual or high-level title evidence assigns semantic roles. The
next implementation milestone must produce that evidence and then provide the
native resource publication or native consumer coverage each role requires.

Guest CPU visibility and the independent rollback switch remain separate
gates. The same session fully armed all 348 exact-family resolve generations
and observed zero guest CPU reads or writes, promoting the scene-bounded CPU
gate to `pass`. The bounded observer and interpretation contract are documented
in [GUEST_CPU_VISIBILITY.md](GUEST_CPU_VISIBILITY.md); this does not weaken the
failing later-GPU-consumer gate.
