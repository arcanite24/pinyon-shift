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

The 2026-08-29 AppData-backed `open_world_day` run used executable SHA-256
`C6DBC2AD3E98C68BE2DEF762C6C309DE70C9DAC2C015306B596DE1C82A450EFE` and
session `20260829T044716Z-p33048`. It exited normally with no error, fatal,
crash, or device-loss event. The deterministic inventory reported:

- 13,650 exact family occurrences.
- 384 matching color-source resolves totaling 100,663,296 bytes.
- Six rotating 262,144-byte guest destinations.
- 378 resolves sampled before replacement by a later resolve.
- 8,552 prepared resolve-to-consumer draws and texture references.
- 51 distinct prepared consumer draw signatures grouped into 26 exact shader
  specialization families, with zero signature overflow and zero missing
  prepared metadata.
- 80 provisional fetch matches discarded because the backend did not reach the
  prepared-draw stage; these are not classified as GPU consumers.
- Zero query-correlated and zero memexport-correlated sample events.
- Six outputs overwritten without a sampled consumer in the observed interval.

The local inventory SHA-256 is
`2913349E4B666AD88B23F0896ADB3F644446CF08EF041319247800695587C3F6`.
It remains local because it includes a machine-specific diagnostic source path.

The leading shader family used vertex shader `2E5E0A854BE00027` and pixel
shader `BDFFA72B7ED2FBA4`; its two pipeline variants accounted for 1,220
prepared consumer draws. This broad 26-family fan-out proves that the selected
output is not a presentation-only leaf.

Performance telemetry contained 5,570 samples: median 30.698 FPS, 1% low
19.287 FPS, one present-deadline miss, and zero native GPU timing drops.
The diagnostic table therefore did not disturb the established 30 FPS cadence
in this qualification.

## Suppression consequence

The `later_gpu_consumers` admission gate is now `fail`, not `unknown`: later
GPU consumers are positively observed and have not been replaced. This is
useful closure of the dependency question, but it prohibits suppressing the
producer family. The next implementation milestone must assign semantic roles
to the 26 stable shader families and provide the native resource publication or
native consumer coverage they require.

Guest CPU visibility and the independent rollback switch remain separate
unknown gates. Neither the absence of query/memexport correlation nor the
visual parity result can substitute for those proofs.
