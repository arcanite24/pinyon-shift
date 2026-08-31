# Vehicle typed constant-upload join

Status: the title-side upload joins are rejected. The v12 per-register run
proved that the generic CPU writer is not the final source of the prepared
vehicle constants. Work continues at the command processor's authoritative
shader-register write boundary.

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
- one semantic hash for each vector in that range.

No constant value is logged or written to the offline report. Invalid source
or register ranges are counted and rejected before the source is read. The
fixed 8,192-entry ring covers two representative heavy frames and reports
overwrites explicitly.

## Draw join

Each exact shadow-correlated vehicle color draw tests its shader-used vertex
constants against uploads no more than one frame old. A match requires at
least one used register to overlap the upload range and every overlapping
vector hash to agree exactly. Unused vectors in the title upload are not
invented as shader inputs. The candidate with the most exact used-vector
matches wins, with newest sequence breaking a tie.

Per-family accounting records exact draw and used-vector matches, misses,
caller, register/range and used-count stability, and source/destination address
variation. The v10 qualifier recognizes a stable candidate only when every
draw in a family matches and its caller, upload range, and consumed subset
size never change. A complete bridge candidate requires all 30 families to
satisfy that rule.

ReXGlue patch `0103-codegen-midasm-link-register-argument.patch` exposes the
guest link register as an optional read-only mid-assembly hook argument. This
avoids 82 duplicated callsite hooks while retaining the exact `bl` return
address for offline title-function resolution.

## First runtime result and correction

The AppData-backed `20260831T181527Z-p45996` run exited normally with no error,
fatal, validation, or device-removal signature. It committed 541 exact vehicle
epochs and 16,230 full-resource matches across all 30 families. The writer
hook strictly accounted 2,419,537 observations: 594,688 valid uploads,
1,824,849 rejected register ranges, and zero invalid source ranges.

The whole-range join produced zero matches across all 16,230 draw scans. That
rejects its admission rule, not the generic writer: ReXGlue reports only
constants actually referenced by the active shader, so requiring every vector
in a broader title upload to appear in the prepared observation was
structurally impossible whenever the shader consumed a subset. The v10 join
therefore compares only the exact shader-used intersection while retaining the
same one-frame freshness, caller provenance, payload-free output, and Xenos
authority.

## Shader-used subset runtime result

The AppData-backed `20260831T184645Z-p11956` run exited normally after the
expanded ledger reset was changed to avoid a multi-megabyte stack temporary.
It committed 525 exact epochs and 15,750 full-resource matches across all 30
families. The writer strictly accounted 2,245,612 observations: 469,815 valid
uploads, 1,775,797 rejected register ranges, and zero invalid source ranges.

The v10 shader-used subset rule also produced zero matches across all 15,750
draw scans. This rejects the second join rule without weakening the proven
writer coverage. A narrow diagnostic now records the observed shader register
envelope and partitions every fresh upload candidate into no-overlap,
hash-mismatch, or exact-subset outcomes. It does not export constant values.
The v11 qualifier requires complete candidate accounting. The short
AppData-backed `20260831T190405Z-p11884` run then reproduced all 30 families
across 11,880 exact geometry matches. It classified 8,331,453 fresh upload
candidates: 7,000,702 had no used-register overlap and 1,330,751 overlapped
but failed the all-vector rule. Every family observed shader registers 0
through 255, proving that freshness and register space are not the blocker.

The v12 join now credits each shader-used register independently when its
index and semantic hash match exactly. Later writes may legitimately replace
other registers from the same broader title upload, so those unrelated
mismatches no longer erase exact provenance. The contributing upload with the
most exact registers wins, with newest sequence as the tie-breaker. Payload
values remain in memory only and Xenos remains authoritative.

## Per-register result and command-stream boundary

The AppData-backed `20260831T191732Z-p39892` run exited normally after 308
qualified vehicle epochs and 9,210 exact color correlations across all 30
families. It strictly accounted 1,363,934 typed-writer observations and
6,111,555 fresh candidates. Of those candidates, 960,532 overlapped a used
register but none matched even one register's exact current value. The v12
last-writer rule therefore also produced zero matches.

This rejects `82435E78` as the semantic provenance boundary for the prepared
draws. It does not invalidate the function's static constant-buffer contract;
it proves that later GPU command construction or register writes replace the
values before the correlated draw reaches the command processor.

ReXGlue now exposes a read-only observer at the final shader-register write.
For each float-constant component it reports the already-endian-correct value,
packet address/header, and complete current/parent/root command-buffer lineage.
The native observer retains only the current 256 vertex-register components and
a bounded 4,096-entry packet-source table. Correlated draws compare their
shader-used values with that authoritative current state and aggregate source
identity by packet header, normalized packet offset, and nesting depth. Dynamic
buffer length and physical addresses remain variation evidence rather than
source identity. No constant payload is exported.

The generic writer boundary and caller provenance remain useful negative
evidence, but no transform or player label may depend on them. The command-
stream census must first prove complete exact component coverage without table
overflow and identify bounded packet-lineage sources for all 30 families.

The corrected command-stream qualification
`20260831T200117Z-p31000` completed normally with 255 exact epochs and 7,650
correlated draws across all 30 vehicle families. Of 122,400 shader-used vertex
vectors, 114,750 (15 per draw) matched the final command-processor register
state exactly, with zero missing or split-component vectors and a maximum age
of zero frames. Exactly one vector per draw remained mismatched. Structural
source aggregation retained 1,620 packet-lineage entries without overflow;
the same producer shapes recur across all families. This proves the final
register-write boundary and narrows the next slice to identifying the single
per-draw mismatch before publishing a semantic constant bridge.

## Safety boundary

- The hook is active only with the restart-gated vehicle correlation mode.
- The ledger is fixed-size and retains hashes, not payloads.
- Every authoritative Xenos upload and draw executes unchanged.
- No native publication or draw suppression depends on this evidence.
- Missing, stale, invalid, non-overlapping, or hash-mismatched ranges remain
  unresolved.
