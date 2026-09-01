# FH1 ZPD END policy and regression guard

EPIC-05 is delivered by
`thirdparty/shiftglue-sdk/include/rex/graphics/zpd_policy.h` at migration commit
`079c10ef1fbe3ef418a1c535ac025ab39dda7a2d` plus host schema,
qualification-runner, performance-summary, and sanitized support-report
integration in this project.

## Derivation and scope

Xenia Canary issue [`#1099`](https://github.com/xenia-canary/xenia-canary/issues/1099)
reports a Forza Horizon post-intro black screen after commit
[`8a49c03`](https://github.com/xenia-canary/xenia-canary/commit/8a49c0380f1e4dd47538a8d0e3da9cc454786428),
which relaxed ZPD END detection from a pairwise sentinel to either lane. This
does not prove causation, so the patch exposes the three interpretations needed
for a controlled title-specific qualification instead of hard-coding the
reported workaround.

The supported retail image is title ID `4D5309C9` with executable SHA-256
`DB40DF605ADE49A612B35A7A24C38F6004BCB17A88ED6B48288DE16DF9E3987C`.
The project enforces that hash before generation. ReXGlue's `auto` policy is
scoped to the title ID because the SDK does not receive the project-side image
hash; unsupported titles retain relaxed sentinel detection with no fallback.

## Policy and diagnostics

Configuration schema 7 adds:

```toml
zpd_end_policy = "report_layout"
# report_layout | pairwise_sentinel | relaxed_sentinel

zpd_end_fallback = "pairwise_sentinel"
# none | pairwise_sentinel | relaxed_sentinel
```

`report_layout` classifies the `+0x20` record as BEGIN and the `+0x00` record
as END within each 0x40-byte slot. The optional sentinel fallback is used only
when an address cannot be classified from that layout. `pairwise_sentinel`
requires both lanes of either expected pair; `relaxed_sentinel` accepts either
A lane, preserving the prior ReXGlue interpretation.

Before report memory is cleared, bounded `zpd.event` records expose the
classification, reason, address, slot, logical state, and the four ZPass/ZFail
lanes. Identical observations log for the first two occurrences and then at
powers of two. A `zpd.watchdog` recovery records and replaces any sentinel
still present after handling, preventing unchanged guest polling. Session CSVs
and sanitized support reports add:

```text
zpd_classified_begins
zpd_classified_ends
zpd_classified_orphaned_ends
zpd_policy_fallbacks
zpd_watchdog_recoveries
```

These diagnostics contain counters and scalar classification fields only; they
do not include saves, guest-memory dumps, generated code, or image data.

The qualification gate permits bounded retire-timeout and watchdog fallback
activity only in diagnostic `strict` mode. Shipping and comparison modes must
finish with both counters at zero. Every mode must balance classified BEGIN
and END records without malformed or orphaned reports.

## Qualification and rollback

`tools/qualify-zpd.ps1` provides the six-run legacy/fake/fast/strict policy
matrix and a ten-cold-boot admission run for the selected policy. Each run uses
the installed AppData preview state in place, records intro, controller-layout,
and first-interactive-frame markers, checks the runtime log, and restores the
original host config in a `finally` block.

Shipping remains `occlusion_query = "legacy"` until the matrix and ten-boot
admission gate pass. Immediate rollback is selecting `legacy`; that path does
not consult the new policy. Removing patch `0040` and the schema-7/reporting
integration removes EPIC-05 while retaining the independently qualified
EPIC-04 lifecycle.
