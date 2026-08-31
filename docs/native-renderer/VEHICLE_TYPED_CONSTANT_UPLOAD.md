# Vehicle typed constant-upload join

Status: both the whole-range and shader-used-subset joins are rejected. The
next bounded run will partition each fresh candidate as no register overlap,
hash mismatch, or exact subset and report only register envelopes and counts.

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
The v11 qualifier requires complete candidate accounting. That single
partition will distinguish register-space/freshness drift from a payload-
representation mismatch before another join rule is proposed.

The generic writer boundary and caller provenance are proved, but neither
runtime join has yet proved which writes feed the prepared vehicle draws. No
transform or player label may depend on this evidence until the diagnostic
partition selects an exact register-space and payload contract.

## Safety boundary

- The hook is active only with the restart-gated vehicle correlation mode.
- The ledger is fixed-size and retains hashes, not payloads.
- Every authoritative Xenos upload and draw executes unchanged.
- No native publication or draw suppression depends on this evidence.
- Missing, stale, invalid, non-overlapping, or hash-mismatched ranges remain
  unresolved.
