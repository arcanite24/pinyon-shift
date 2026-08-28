# Native renderer resource identity

NR-03 uses one identity for every guest graphics resource: a half-open byte
range in the 512 MiB Xenon physical aperture. Physical-heap window bits are
removed at the capture boundary, so values such as `0xA1234000` and
`0x01234000` cannot create separate cache entries for the same memory.

`PhysicalRange` rejects empty and aperture-crossing resources and performs
overflow-safe overlap checks. Buffer keys add the buffer class and descriptor
signature. Texture keys add the complete fetch signature and optional mip
range. Both key types carry a content fingerprint from
`PhysicalResourceTracker`.

The tracker assigns monotonically increasing generations to physical pages
touched by a guest write. A capture over any touched range therefore produces
a new key even when the guest object pointer and descriptor are reused. Its
overlap index reports each affected buffer or texture exactly once.

Invalidation only marks identity stale; it never destroys a host object. The
buffer and texture caches introduced by later NR-03 pull requests own those
objects and must retire them behind their final GPU submission. At that point,
the tracker will be connected to ReXGlue's one-shot physical-memory
invalidation callback and each cached range will re-arm the callback after a
successful upload.

The standalone native test covers physical-heap aliases, exact half-open range
boundaries, aperture bounds, page generations, multi-range textures, resource
class separation, deduplicated overlap reporting, and unregistration.

## Buffer cache lifetime

`NativeBufferCache` attaches opaque backend allocations to exact buffer keys.
Hits advance the last-use frame and submission. A physical invalidation removes
the entry from lookup immediately, but moves its allocation to a retired queue
stamped with the later of its last use and the current submission. Only
`Collect(completed_submission)` returns handles that the backend may destroy.
This makes early invalidation and shutdown use the same fence-safe path.

## Texture streaming state

`NativeTextureCache` uses the same physical content identity for asynchronous
texture decode and upload work. An incomplete guest payload schedules bounded
exponential backoff. While a refreshed generation is pending, the cache serves
the previous complete texture; when no complete generation exists, handle zero
selects the backend's neutral fallback. Exhausting the configured attempt limit
stops decode churn until the content identity changes.

The first measured upload contract is taken directly from retained-pass anchor
`747837906D0BF484`. Its two fetches are tiled 256 by 64 `DXN` (BC5-like)
resources with 256-pixel pitch and 8-in-16 endianness. The native semantic test
decodes the captured six-word fetch constant and fixes those values as the
input contract for the upcoming D3D12 upload bridge.
