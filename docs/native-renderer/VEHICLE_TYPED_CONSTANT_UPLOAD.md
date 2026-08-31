# Vehicle typed constant-upload join

Status: implemented as a default-off, payload-free extension of the C4 vehicle
correlation mode; runtime qualification is deferred to the next batched
AppData session.

## Proven title boundary

Title function `82435E78` is the generic float-constant writer. At entry it
receives the destination buffer in `r3`, a register offset in `r4`, the source
vectors in `r5`, and the vector count in `r6`. It copies those vectors into
registers beginning at `r4 + 120` and then marks the destination buffer dirty.

A read-only entry hook now records a bounded recent-upload ledger. Each valid
entry retains only:

- the frame and monotonic observation sequence;
- the exact caller return address supplied by the guest link register;
- destination buffer and source addresses;
- destination register range; and
- a semantic hash of that exact range and payload.

No constant value is logged or written to the offline report. Invalid source
or register ranges are counted and rejected before the source is read. The
fixed 8,192-entry ring covers two representative heavy frames and reports
overwrites explicitly.

## Draw join

Each exact shadow-correlated vehicle color draw tests its observed vertex
constants against uploads no more than one frame old. A match requires every
register in the uploaded range to exist in the prepared draw and the semantic
payload hash to agree exactly. The newest exact upload wins when repeated
writes carry the same range and values.

Per-family accounting records exact matches, misses, caller and register/count
stability, and source/destination address variation. The v9 qualifier
recognizes a stable typed-upload candidate only when every draw in a family
matches and its caller and register range never change. A complete bridge
candidate requires all 30 families to satisfy that rule.

ReXGlue patch `0103-codegen-midasm-link-register-argument.patch` exposes the
guest link register as an optional read-only mid-assembly hook argument. This
avoids 82 duplicated callsite hooks while retaining the exact `bl` return
address for offline title-function resolution.

This proves which typed writes feed the prepared vehicle draws. It does not by
itself convert reference-space constants to a world transform or label a
vehicle as the player. The runtime result will determine which exact register
ranges and title callers should receive the next semantic discriminator.

## Safety boundary

- The hook is active only with the restart-gated vehicle correlation mode.
- The ledger is fixed-size and retains hashes, not payloads.
- Every authoritative Xenos upload and draw executes unchanged.
- No native publication or draw suppression depends on this evidence.
- Missing, stale, invalid, or incomplete ranges remain unresolved.
