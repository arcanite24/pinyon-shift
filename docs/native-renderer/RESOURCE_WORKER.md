# Native resource worker and prewarm queue

NR-03G begins with a backend-neutral two-stage worker contract. CPU-only
preparation runs on a fixed set of `std::jthread` workers. Backend resource,
view, descriptor, and pipeline creation remains exclusively in the bounded
`DrainCommits` call made by the renderer thread.

## Scheduling

Work is ordered by four explicit priorities:

1. visible draw misses;
2. loading-screen prewarm;
3. streaming-registration prewarm;
4. speculative preparation.

FIFO order is preserved within a priority. A full pending or prepared queue
may evict only work with strictly lower priority; equal- or higher-priority
work is never displaced. Default limits are 256 pending requests and 16 MiB,
128 prepared results and 16 MiB, two workers, and 4,096 remembered logical
resources. Completed idle state is retired by least-recently-used order.

Each request carries a resource class, stable identity, and generation. A
newer generation makes queued, prepared, or in-flight older results stale.
Stale results are discarded before renderer-thread commit. Repeated requests
for an outstanding or completed generation are deduplicated. Stop tokens and
explicit shutdown prevent a worker from outliving the owning renderer bridge.

## Initial texture signal

The default-off D3D12 texture bridge now exercises the worker contract with
real texture observations. The physical base range and complete fetch
signature form the metadata identity. Workers validate the copied six-word
fetch descriptor without accessing guest memory or backend objects. The
render thread drains at most four results and 64 KiB per observation.

This first integration deliberately prepares metadata rather than performing
the eventual untile/decode/upload pipeline. It validates scheduling,
deduplication, stale rejection, and render-thread commit under authentic game
load while Xenos remains fully authoritative. Later prewarm observers may
submit the same work before first visibility without changing the queue's
lifetime contract.

## Qualification

The AppData-backed run `20260828T222703Z-p43172` reached the festival scene
and ran for 108.45 seconds. It prepared and renderer-committed all 1,151 unique
texture metadata requests, deduplicated 12,631,781 repeated observations, and
ended with zero stale results, capacity refusals, pending work, prepared work,
or retained references. The capture reported 31.057 median FPS, 17.893
one-percent-low FPS, 59.972 Hz presentation, no presentation deadline misses,
no renderer failure, fatal, crash, or device-loss event, and a normal
`process.shutdown`. Xenos draws and resolves remained preserved throughout.
