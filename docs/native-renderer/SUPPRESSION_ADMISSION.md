# Pass-suppression admission

NR-04D must not infer safety from a correct-looking frame, a recurring draw
signature, or a GPU-time measurement. A pass family becomes eligible for a
suppression implementation only after one local evidence bundle proves every
required gate for one exact build and scene.

`tools/evaluate-native-renderer-suppression.py` validates that bundle and emits
a deterministic admission report. The evaluator cannot enable suppression.
Its output always records `suppression_allowed=false`, Xenos draws preserved,
and both draw and resolve suppression absent. A fully passing report means only
that a separate, default-off implementation PR may begin.

## Required gates

| Gate | Required proof |
| --- | --- |
| `exact_family_identity` | Exact scene-qualified signatures and stable pass boundaries |
| `complete_native_coverage` | Every draw in the selected target phase is reproduced |
| `color_parity` | Complete-pass color comparison passes the documented tolerance |
| `depth_parity` | Complete-pass depth comparison passes or proves no depth effect |
| `later_gpu_consumers` | Every later GPU consumer is replaced or proven absent |
| `guest_cpu_visibility` | CPU reads are preserved/replaced or proven absent |
| `query_side_effects` | Query behavior is preserved or proven unrelated |
| `memexport_side_effects` | Memexport behavior is preserved or proven absent |
| `output_freshness` | Exact-frame publication and stale-frame yield are qualified |
| `fallback_recovery` | Unsupported/error states yield cleanly to Xenos |
| `gpu_timing` | Native and preserved-Xenos GPU buckets are available without drops |
| `rollback_switch` | An independent default-off family switch is specified and tested |

Each gate is `pass`, `fail`, or `unknown` and requires an evidence explanation.
Unknown is a blocker, not an implicit negative result. Local artifacts may be
attached by path and uppercase SHA-256. Passing `--artifact-root` verifies that
every referenced file exists below that root and matches its hash.

Use `--require-ready` in a future suppression implementation workflow; it exits
with code 2 until every gate passes. A malformed or unsafe bundle exits with
code 1.

## Current retained sky/horizon family

The exact pair `747837906D0BF484` / `1D253A52B55C9FB3` has stable boundaries,
one-draw parity, continuous exact-frame output, fallback behavior, and native
GPU timing. It is not admitted for suppression yet:

- the current RenderDoc parity result covers the anchor draw, not the complete
  two-draw retained pass;
- the target's later GPU-consumer graph is not closed;
- guest CPU visibility remains uninstrumented; and
- no independently reversible suppression switch exists.

Consequently the next work is evidence collection and complete-pass comparison,
not draw skipping. The Xenos copy, draw, resolve, query, fence, and memexport
paths remain unchanged.

The complete-pass color gate may use the paired asynchronous readback described
in [VISUAL_COMPARISON.md](VISUAL_COMPARISON.md). It captures private-native and
authoritative-Xenos color after the same follower draw, checks exact active
texel bytes, adds no GPU wait, and preserves the original draw. It does not
prove the independent depth gate.

The 2026-08-28 same-frame qualification passed exact complete-pass color parity
across 41,943,040 active bytes. This promotes `color_parity` to `pass`. The
admission result is now 8/12; `depth_parity`, `later_gpu_consumers`,
`guest_cpu_visibility`, and `rollback_switch` remain `unknown`, so suppression
is still prohibited.
