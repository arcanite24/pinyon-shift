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

## Qualification

Clean build and AppData-backed runtime qualification on 2026-08-28 used
session `20260828T211430Z-p39104`. The saved game reached the festival scene
with the default `xenos` renderer and exited normally. The 165.03-second
capture contained 5,788 samples, 30.715 median FPS, 19.597 one-percent-low
FPS, 59.993 Hz presentation, 29.654 Hz simulation, and no presentation
deadline misses. Texture and pipeline hit rates were 99.976 and 100 percent.
The event stream ended with `process.shutdown` and reported no failure events,
failed resolve copies, census target overflow, or census page overflow.
