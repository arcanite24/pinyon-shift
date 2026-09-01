# ReXGlue XMA multi-packet frame assembly

EPIC-02 is delivered by
`thirdparty/shiftglue-sdk/src/audio/xma_context.cpp` at migration commit
`079c10ef1fbe3ef418a1c535ac025ab39dda7a2d`.

## Derivation and scope

The bounded payload-assembly design is adapted from ReXGlue commit
[`51b601a`](https://github.com/xXJSONDeruloXx/rexglue-sdk/commit/51b601ab04caf3f1a9a5fcb1455b3a8bb58f5a2a).
The project patch integrates that behavior with EPIC-01's validated logical
packet handles rather than reading continuation buffers directly.

The patch changes:

- `include/rex/audio/xma/context.h`;
- `src/audio/xma_context.cpp`;
- `tests/unit/audio/xma_packet_test.cpp`.

It expands the scratch buffer from two to four header-free packet payloads.
One reusable assembler calculates the required packet count with 64-bit
intermediate arithmetic, resolves every logical packet through EPIC-01, copies
only validated payload bytes, and zero-fills unused or failed output. Split
frame headers and complete frame extraction both use this path.

## Failure behavior

Zero-bit requests, offsets outside a packet payload, sentinel frame sizes,
scratch-capacity overruns, missing continuation buffers, and undersized
alternate buffers are rejected before decoding. Failures set XMA error status
`4` and emit at most one payload warning per failure class and decoder stream.
EPIC-01 continues to bound the more specific packet-resolution warnings.

Next-frame advancement uses the declared frame size rather than the number of
bits that happened to remain in the first guest packet.

## Tests and rollback

Synthetic coverage exercises one-, two-, three-, and four-packet assembly,
late frame starts, split headers, alternate-buffer packet `0` and later packet
indices, missing and short continuations, over-capacity requests, invalid
offsets, zero-length frames, and the maximum sentinel. Three- and four-packet
decoder cases also verify clean advancement across the guest-buffer boundary.

Rollback is removal of patch `0037`. It contains only the four-payload scratch
capacity, assembler, decoder integration, diagnostics, and their tests. EPIC-01
packet traversal remains independently active.
