# ReXGlue XMA cross-buffer packet traversal

EPIC-01 is delivered by
`thirdparty/shiftglue-sdk/src/audio/xma_context.cpp` at migration commit
`079c10ef1fbe3ef418a1c535ac025ab39dda7a2d`.

## Derivation and scope

The packet-handle design is adapted from Xenia Canary PR
[#983](https://github.com/xenia-canary/xenia-canary/pull/983). The Pinyon patch
keeps only the buffer-aware traversal behavior relevant to ReXGlue's existing
decoder and adds deterministic coverage. It does not change FFmpeg behavior,
output padding, or the two-payload frame assembly limit reserved for EPIC-02.

The patch changes:

- `include/rex/audio/xma/context.h`;
- `src/audio/xma_context.cpp`;
- `tests/unit/CMakeLists.txt`;
- `tests/unit/audio/xma_packet_test.cpp`.

It depends on patch `0017`. The new resolver replaces `0017`'s isolated
end-offset guard with the same retirement behavior inside the unified packet
state machine.

## Decoder state transitions

| Resolution result | Decoder transition |
| --- | --- |
| Packet is in the active buffer | Keep the active buffer and use its exact packet index. |
| Packet is in the alternate buffer | Retire the active buffer, switch buffers, and preserve the alternate-buffer packet index. |
| Active buffer is exhausted and the alternate buffer is not valid | Retire the active buffer and enter a clean idle state. |
| Valid buffer has a null address, is too short, or contains no usable continuation packet | Emit one warning per failure class and set XMA error status `4`. |
| Starting buffer or packet-count state is inconsistent | Emit one bounded warning and set XMA error status `4`. |

Full-packet skips and next-frame advancement use the same transition rules.
Read-offset scanning reports the packet handle separately from the bit offset,
so packet `0` at bit offset `32` is not confused with the no-packet sentinel.

## Tests and rollback

The synthetic tests cover current and alternate packet indices, invalid and
undersized buffers, null addresses, exact and beyond-end traversal, full-packet
skip across a buffer boundary, traversal to alternate packet `1`, and repeated
idle `Work()` calls. The complete ReXGlue unit suite is the validation gate.

Rollback is removal of patch `0036`. Because `0017` remains earlier in the
ordered stack, its previous exhausted-input protection becomes active again;
no configuration or persistent data migration is involved.
