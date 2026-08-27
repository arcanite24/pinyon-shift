# FH1 resolve-readback presets and telemetry

EPIC-06 combines ReXGlue's existing resolve-readback modes with schema-8 host
presets, launcher controls, renderer A/B evidence, and the bounded D3D12
telemetry in `patches/rexglue/0041-fh1-resolve-readback-counters.patch`.

## Evidence and scope

The FH1 compatibility tracker and community settings identify two distinct
correctness cases: delayed `fast` readback for scaled-render artifacts and
synchronous `full` readback for garage, autoshow, thumbnail, and livery
accuracy. `full` is intentionally opt-in because it serializes GPU and CPU
work. The project does not detect scenes or modify game assets.

Sources:

- <https://github.com/xenia-canary/game-compatibility/issues/30>
- <https://github.com/xenia-manager/optimized-settings/blob/main/settings/4D5309C9.toml>

## Presets

| Preset | Resolution | Resolve readback | Half-pixel sample | Intended use |
| --- | ---: | --- | --- | --- |
| Shipping 1× | 1× | `none` | off | Normal driving and release default |
| Experimental 2× | 2× | `fast` | on | Scaled rendering without colored-car artifacts |
| Experimental 3× | 3× | `fast` | on | 4K-class output on high-end GPUs; qualification required |
| Accurate showroom | 1× | `full` | off | Garage, autoshow, thumbnails, and liveries |

All presets keep `clear_memory_page_state`, `readback_memexport`,
`readback_memexport_fast`, and `vsync` enabled. The launcher exposes
`none`, `fast`, `some`, and `full` for controlled experiments, labels full
readback as expensive, and preserves backup/reset/restore behavior.
The 3× preset maps the game's 1280×720 internal target to 3840×2160; it is
explicitly experimental and is included in the qualification plan rather than
being presented as part of the existing 2026-08-27 evidence below.

## Metrics

Patch `0041` adds per-frame CSV counters at the D3D12 resolve path:

```text
resolve_readback_requests
resolve_readback_bytes
resolve_readback_fast_copies
resolve_readback_cache_misses
resolve_readback_full_waits
resolve_readback_wait_time_ns
```

Requests count non-empty resolve ranges entering readback. Bytes count only
copies committed to guest memory. Cache misses identify delayed modes that
must synchronize because no prior slot is usable. Full waits count every
synchronous resolve wait, including a delayed-mode miss, and wait time records
the measured wall-clock duration of those waits.

The performance summarizer and sanitized crash report aggregate these scalar
counters. Renderer A/B sessions require them for `readback_resolve` and accept
`fast`, `some`, or `full` as the candidate against a `none` control. The visual
baseline covers front end, garage, autoshow, livery, day, night, race, and
rewind scenes on an exact build fingerprint.

## AppData qualification

The 2026-08-27 qualification used the installed `0.1.0` AppData save and the
release candidate with executable SHA-256
`C075F20F40BCCB29E9EACFB1E1B392508B6F50726BAFBBDF8BC55DAE9FC78160`.
All three profiles completed without a matching fatal, error, exception,
assert, or device-removed signature.

| Profile | Median FPS | 1% low FPS | Resolve requests | Bytes copied | Full waits |
| --- | ---: | ---: | ---: | ---: | ---: |
| Shipping 1× | 56.836 | 20.300 | 0 | 0 | 0 |
| Experimental 2× | 55.777 | 19.866 | 73,767 | 61,139,881,984 | 143 |
| Accurate showroom | 53.785 | 12.267 | 78,458 | 71,649,955,840 | 78,458 |

Experimental 2× kept the live car body free of the documented random colored
artifacts. Accurate showroom displayed a clean representative Mustang photo
and car asset. A previously generated Audi thumbnail in the existing save
remained corrupted; the qualification did not alter or regenerate save data,
and the clean representative asset was used for the acceptance check.

## Rollback

Selecting Shipping 1× immediately returns to `readback_resolve = "none"`.
Reset writes the same conservative preset after backing up the prior file;
restore recovers the newest backup. Removing patch `0041` removes telemetry
only—the existing readback implementation and schema-8 host controls remain
independently reversible.
