# ReXGlue XMA stall diagnostics

EPIC-03 is delivered by
`patches/rexglue/0038-m4-xma-stall-diagnostics.patch` plus the host-side
configuration and sanitized-report integration in this project.

## Derivation and scope

The reporting cadence and state fields are adapted from Xenia Canary PR
[`#974`](https://github.com/xenia-canary/xenia-canary/pull/974). That PR was
closed without merge and describes its padding behavior as uncertain, so this
project adopts the diagnostics unconditionally while keeping relaxed padding
admission explicitly opt-in.

The ReXGlue patch changes:

- `include/rex/audio/xma/context.h`;
- `include/rex/perf/counter.h`;
- `src/audio/xma_context.cpp`;
- `src/core/perf/counter.cpp`;
- `tests/unit/audio/xma_packet_test.cpp`.

Each XMA context tracks consecutive and total output-space and no-progress
stalls, recovery count, last successful input offset, and last successful
output read/write offsets. Output-full observations are first treated as
ordinary decoder backpressure. A no-space stall begins only when eight
consecutive work attempts see the same buffer, input offset, output offsets,
admission requirement, and remaining capacity. Any changed state is progress
and primes a new observation instead. Warning summaries are emitted only when
the per-context lifetime total for a stall class reaches 1, 8, 64, and every 256
thereafter. Every recovered stall episode is counted, while a recovery warning
is emitted only when that episode emitted a stall summary. Progress clears only
the consecutive runs.

Context metrics reset on clear, disable, release, and established-stream codec
reinitialization. Process-level performance counters remain independent of
those lifecycle resets so a session CSV retains exact aggregate totals.

## Shipping behavior and support data

Host configuration schema 5 adds:

```toml
xma_relaxed_padding_admission = false
```

With the default `false`, decode admission and padding reservation retain the
qualified strict behavior. When explicitly enabled for an A/B experiment,
padding is removed from the hard admission minimum and reserved only from
remaining writable headroom. The setting is recorded with effective session
configuration.

Sanitized crash/support reports sum the three XMA stall counters from the
session performance CSV into `report.json`. They do not attach the CSV or any
encoded or decoded audio payload.

## Tests, dependencies, and rollback

Deterministic unit coverage forces output-space stalls, verifies the bounded
1/8/64/256 lifetime reporting schedule across transient stall episodes while
preserving exact recovery totals, proves that changing output state is normal
backpressure rather than a stall, forces a no-progress failure with its buffer
and offset preserved, checks lifecycle reset behavior, and proves relaxed
padding changes admission only when the flag is enabled. Project tests cover
schema migration, default-off settings, performance aggregation, and sanitized
support-report totals.

This patch depends on `0036` packet handles and `0037` multi-packet frame
assembly. Rollback is removal of patch `0038` and the associated schema-5,
performance-summary, and support-report integration; EPIC-01 and EPIC-02 remain
independently active.
