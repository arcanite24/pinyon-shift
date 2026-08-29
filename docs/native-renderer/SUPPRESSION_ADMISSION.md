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
| `later_gpu_consumers` | Every later GPU consumer is replaced, proven absent, or preserved behind a bit-exact native publication boundary |
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
complete-pass color/depth parity, continuous exact-frame output, fallback
behavior, and native GPU timing. It is admitted only for the fail-closed,
operator-requested follower boundary because:

- the exact publication boundary preserves the observed later-GPU-consumer
  graph behind bit-exact guest color and depth/stencil targets;
- guest CPU visibility passes for one bounded exact-family AppData
  qualification route, with zero reads across 348 fully armed resolve
  generations; and
- an independent default-off, fail-closed follower suppression implementation
  passed its same-build enabled/disabled rollback qualification.

Consequently the only permitted draw skipping is the experimental exact
follower boundary in
[EXACT_FAMILY_SUPPRESSION.md](EXACT_FAMILY_SUPPRESSION.md). The Xenos anchor,
copy, resolve, query, fence, memexport, and later-consumer paths remain
unchanged, and failed replay/publication executes the original follower.
The additional warm-up, frame-gap yield, and failure cooldown contract is
documented in [STATE_BASED_YIELD.md](STATE_BASED_YIELD.md); it must receive its
own enabled AppData runtime qualification before the safety manifest admits
the hardened route.

That qualification passed on executable
`0D35FDBA928E4A1315A9B3C508272E6796010D033796108264CA6063D2F2334A`:
enabled session `20260829T095155Z-p3564` yielded 48 warm-up publications and
suppressed 12,223 of 12,223 active followers with zero failures, while disabled
session `20260829T095601Z-p32088` suppressed zero draws. Both shut down
normally, promoting the state-based-yield and rollback gates for this exact
family only.

The complete-pass color and depth gates use the paired asynchronous readback
described in [VISUAL_COMPARISON.md](VISUAL_COMPARISON.md). It captures
private-native and authoritative-Xenos attachments after the same follower
draw, checks exact active bytes, adds no GPU wait, and preserves the original
draw. Two-sample depth/stencil targets are extracted as raw per-sample tuples
so both depth and stencil participate in the comparison.

The 2026-08-29 same-frame qualification passed exact complete-pass color parity
across 41,943,040 active bytes and exact two-sample depth/stencil parity across
83,886,080 bytes. This promotes both `color_parity` and `depth_parity` to
`pass`.

The combined bounded census linked 348 family resolves to 63 distinct prepared
later-draw signatures across 38 shader families, with zero signature overflow
and complete prepared metadata. That initially kept `later_gpu_consumers` at
`fail`: consumers were proven present but had no preservation boundary.

[RETAINED_PASS_OUTPUT_PUBLICATION.md](RETAINED_PASS_OUTPUT_PUBLICATION.md)
defines the next preservation boundary. A default-off diagnostic path copies
the parity-qualified native color and depth/stencil result back into the exact
guest targets only after both original Xenos draws. This is intended to let the
existing resolves and all 38 consumer families continue unchanged. Its
implementation alone does not promote the gate. The deterministic evidence
combination in [PUBLICATION_QUALIFICATION.md](PUBLICATION_QUALIFICATION.md)
proves that exact published outputs reach the unchanged resolve and consumer
chain and promotes the gate for the qualified scene.

The same session armed every one of those 348 resolve generations and observed
zero guest CPU read or write events. This promotes `guest_cpu_visibility` from
`unknown` to scene-bounded `pass`, as documented in
[GUEST_CPU_VISIBILITY.md](GUEST_CPU_VISIBILITY.md). The admission result is now
12/12 passing gates for the exact, scene-bounded sky/horizon family. Enabled
AppData session `20260829T092338Z-p31960` suppressed 5,442 followers after
5,442 complete publications with zero fallbacks. Disabled session
`20260829T092551Z-p25116` used the same executable, suppressed zero draws, and
both sessions shut down normally. The exact 38-family identity classifier and
fail-closed switch control are documented in
[CONSUMER_FAMILY_CLASSIFICATION.md](CONSUMER_FAMILY_CLASSIFICATION.md). See
[PASS_CONSUMER_GRAPH.md](PASS_CONSUMER_GRAPH.md).
