# Native render-target bridge

NR-03E introduces the backend-neutral ownership and provenance contract for
native render targets. It does not suppress an Xenos draw or change the
default renderer. A later backend integration must translate the opaque
handles to retained host resources and bind a neutral fallback whenever a
lookup returns `kBridgeRequired`.

## Exact pool identity

`NativeRenderTargetKey` includes the host format, dimensions, sample count,
and complete usage mask. A checked-in allocation is reusable only when its
key matches exactly, no resolve mapping pins it, and the completed submission
has reached every submission that referenced it. Candidate allocations are
consumed only on a miss; the backend keeps ownership of an unused candidate
on a hit.

Color and depth attachment identity is mutually exclusive. Resolve producers
must be single-sampled and shader-readable. The resolve record keeps the
canonical guest destination, source rectangle, row pitch, mip level, and
array slice so later backend work does not need to infer subresource identity.

## Producer provenance

Publishing a resolve associates its canonical guest destination with the
native producer and pins that target against pool reuse. A newer overlapping
resolve supersedes and unpins the older mapping. A compatible texture request
returns the producer handle directly; a format, extent, or lifetime mismatch
returns `kBridgeRequired`.

Known GPU-produced ranges remain recorded after their producer is retired.
They therefore cannot silently fall through to guest-memory decoding. The
consumer must bind its neutral fallback until a valid producer is published.
An overlapping guest write invalidates the old mapping and provenance, after
which the rewritten resource may follow the normal bounded decode path.
Physical-heap aliases are canonicalized by `PhysicalRange` before either
operation.

## Lifetime and telemetry

Targets retired by invalidation, replacement, or shutdown enter the same
deferred queue. `Collect` returns them to the backend only after the completed
submission reaches their final-use stamp. The bridge reports pool hits and
misses, producer hits and refusals, resolve publications, guest invalidations,
and live and retired allocation counts and bytes.

The standalone semantic test covers exact keys, physical aliases, pinned
producer non-reuse, superseding resolves, guest-write invalidation, stale
producer refusal, pool reuse, and fence-safe retirement. This PR establishes
the resource contract required before the command processor can publish real
D3D12 render targets into continuous native composition.

## D3D12 producer handoff

The NR-03E milestone installs a dedicated passive resolve
observer alongside the existing diagnostic copy observer. Successful copies
carry their current and completed submission IDs and immediately mark the
canonical destination as GPU-produced, invalidating any older overlapping
producer. This ensures that a consumer cannot decode stale guest memory while
the concrete host allocation is still being discovered.

Later texture bindings expose the backend-owned D3D12 resource, exact guest
row pitch, host format, dimensions, and allocation size. A bounded correlation
table matches only a texture whose complete base range is covered by a known
resolve. The title retains that COM resource on the bridge's first import,
publishes the exact mip-zero producer region, and releases it only after the
backend's completed submission reaches the retirement fence. Re-observing the
same handle is continued use, not pool alias reuse, and an incompatible key is
refused.

Resolve correlation is capped at 4,096 records. Old correlation metadata may
be evicted, but GPU provenance is independently retained by the bridge. If the
provenance table itself reaches its bound, it enters a conservative overflow
state where unmatched requests return `kBridgeRequired` rather than falling
through to guest decode. All observers are default-off, preserve the original
Xenos copies and draws, and expose no suppression operation.

Repeated draw bindings of the same resource and resolve submission are
deduplicated before bridge checkout. Imported backend allocations are limited
to 64 live resources and 128 MiB, with least-recently-observed and 600-
submission-stale producers retired through the submission fence. A resource
that cannot fit those limits remains Xenos-backed; the bridge never weakens
its GPU-provenance refusal to make room.

## Qualification

Clean build and AppData-backed runtime qualification on 2026-08-28 used
session `20260828T211430Z-p39104`. The saved game reached the festival scene
with the default `xenos` renderer and exited normally. The 165.03-second
capture contained 5,788 samples, 30.715 median FPS, 19.597 one-percent-low
FPS, 59.993 Hz presentation, 29.654 Hz simulation, and no presentation
deadline misses. Texture and pipeline hit rates were 99.976 and 100 percent.
The event stream ended with `process.shutdown` and reported no failure events,
failed resolve copies, census target overflow, or census page overflow.

The concrete D3D12 producer handoff was qualified with the same AppData save
in session `20260828T215636Z-p11712`. The 276.83-second capture contained
8,986 samples, 30.346 median FPS, 19.464 one-percent-low FPS, 59.993 Hz
presentation, 29.801 Hz simulation, and no presentation deadline misses.
During 321,521 successful resolve observations, repeated bindings were
deduplicated 3,863,185 times. The producer pool remained at or below 64 live
targets and 108,003,328 bytes in the final steady-state sample, below both
configured limits, with zero budget refusals and zero bridge refusals. The
event stream reported no renderer failure, fatal, crash, or device-loss event,
released every retained reference, preserved Xenos draws, and ended with
`process.shutdown` after a normal exit.

After hardening handle reuse across different guest destinations, the exact
final binary was regression-tested in session `20260828T221140Z-p38016`.
The saved game again reached the festival scene, presented at 59.974 Hz with
no deadline misses, kept 64 live producers to 74,776,576 bytes, recorded zero
budget or bridge refusals and zero failure events, released all retained
references, and exited through `process.shutdown`.
