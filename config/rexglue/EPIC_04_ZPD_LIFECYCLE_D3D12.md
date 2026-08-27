# ReXGlue D3D12 ZPD report lifecycle

EPIC-04 is delivered by
`patches/rexglue/0039-gpu-zpd-report-lifecycle-d3d12.patch` plus host schema,
performance-summary, and sanitized support-report integration in this project.

## Derivation and scope

The guest report layout and logical/physical query split are adapted from Xenia
Canary PR [`#1016`](https://github.com/xenia-canary/xenia-canary/pull/1016),
head commit `d35e0b5359c76d98c758125d529df7af99d8526a`. Pinyon Shift ports only
the Windows/D3D12 report lifecycle. Vulkan, QueryBatch, VIZ, EXT, and the
shader-interlock counter path remain deferred as specified by the epic.

The ReXGlue patch adds:

- fixed 0x20-byte record and 0x40-byte slot helpers;
- logical report handles with per-slot sequence IDs;
- physical D3D12 segments that close and resolve at every submission boundary;
- a generation-protected 8,192-entry host query pool;
- asynchronous fast-mode retirement and late guest result patching;
- bounded strict retirement with a 2 ms backstop;
- conservative fake fallback and the pre-existing legacy path;
- 1x/2x sample-count normalization;
- the complete EPIC-04 performance-counter set;
- deterministic layout, segmentation, scaling, and stale-write tests.

Same-slot reuse increments the guest slot sequence before the new lifetime is
opened. An older result may release its host query index after its fence passes,
but cannot update guest memory or seed the new slot's cached delta. D3D12 query
indices also have independent generations so a late resolve cannot be confused
with a recycled heap entry.

## Configuration and qualification

Host configuration schema 6 adds:

```toml
occlusion_query = "legacy"
# legacy | fake | fast | strict
```

`legacy` remains the shipping default and preserves the previously qualified
synchronous implementation. `fast` writes a conservative visible value or the
last current-slot delta, then patches it when all segments retire. `strict`
closes the containing submission and waits for at most 2 ms; timeout writes a
visible/cached fallback and rejects the eventual stale result. Resource creation
or pool exhaustion also falls back without leaving a guest sentinel pending.

Session CSVs and sanitized support reports expose:

```text
zpd_reports_started
zpd_reports_ended
zpd_report_segments
zpd_same_slot_reuse
zpd_fast_speculative_writes
zpd_async_result_patches
zpd_strict_waits
zpd_strict_wait_time_ns
zpd_retire_timeouts
zpd_fake_fallbacks
zpd_malformed_records
zpd_stale_result_rejections
```

No report contents, guest memory, save data, or image data are included.

## Tests and rollback

The focused lifecycle suite verifies BEGIN/END address classification, a logical
report accumulated across multiple submissions, same-slot stale-result
rejection, and scale-normalized sample counts. The complete ReXGlue unit suite,
D3D12 graphics target, project tests, clean patch replay, release build, and an
AppData-backed runtime qualification are required before merge.

Rollback is selecting `occlusion_query = "legacy"`. Removing patch `0039` and
the schema-6/reporting integration fully removes EPIC-04 without affecting the
audio patches. EPIC-05 owns title-specific END classification and will keep the
modern modes non-shipping until its cold-boot matrix passes.
