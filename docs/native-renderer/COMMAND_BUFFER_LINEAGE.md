# Command-buffer lineage

This milestone connects every observed backend draw to the exact command
buffer that contains its PM4 packet. It is an ownership-discovery bridge, not
a native rendering path and not evidence that any draw may be suppressed.

## Why this bridge is needed

The exact title-wrapper provenance bridge proved that the currently reviewed
title draw wrapper feeds EDRAM copies. Prepared world draws therefore enter
the backend through other command streams. ReXGlue already executes those
streams exactly, including nested `PM4_INDIRECT_BUFFER` packets, so the
backend command processor is the strongest passive point from which to recover
their submission lineage.

The static dispatch scanner now recognizes stored `PM4_INDIRECT_BUFFER`
(`0x3F`) and `PM4_INDIRECT_BUFFER_PFD` (`0x37`) headers. The supported title
contains seven such constructors across six functions. This inventory proves
where packet headers are stored, but it does not yet prove the semantic owner
of each constructed buffer.

The title now observes the exact effective address at all six store sites:
`0x824095B4`, `0x82416EFC`, `0x8246FC1C`, `0x8263BD64`, `0x829E8E88`, and
`0x829EC49C`. ReXGlue patch `0083` emits balanced enter/exit observations
around synchronous indirect-buffer execution. The active GPU-thread stack
joins an execution to a store site only when the physical parent-packet
address matches exactly; a prepared draw inherits that constructor only while
the matching target/root/depth context remains active. Copied packet templates
and uninstrumented producers remain explicitly `unknown`.

Title-side packet generations live in a fixed 4,096-bucket, four-way cache.
Each store creates one generation; an exact backend address consumes the oldest
retained matching generation. A full bucket evicts its oldest generation and
counts that eviction explicitly. Eviction can reduce constructor coverage, but
it cannot create a match: evicted, copied, repeated, and uninstrumented packets
remain unknown unless a retained generation matches the exact backend address.

## Exact runtime contract

ReXGlue patch `0082` carries five fields with each draw observation:

- the current command-buffer physical address and length;
- the exact parent indirect-buffer packet address;
- the first indirect-buffer root address; and
- the nesting depth.

Primary or directly executed buffers have depth zero and no parent packet. An
indirect buffer has a nonzero depth and an exact parent packet. Nested buffers
preserve the first indirect root while increasing depth. The draw packet must
fall within the reported current-buffer bounds or the lineage is invalid.

Pinyon validates the exact addresses, current-buffer length, and packet offset
on every draw, then aggregates a stable ownership-class key in a fixed
4,096-entry table: nesting depth, exact constructor store and return address,
plus the exact upstream owner and producer function and return addresses when
those are matched. Balanced entry/exit hooks on all six constructor functions
carry the direct caller return address and bounded `r3-r10` entry metadata into
the exact stored packet generation. A second balanced layer covers the four
immediate constructor callers that produced every known-origin draw in the first
qualification. A third balanced layer covers the three producer functions
responsible for 85.1% of the owner-origin draws in the owner qualification.
Each class retains statically resolved constructor, owner, and producer
callsites when proved, independent argument samples and varying masks, and
minimum and maximum current-buffer lengths, packet
offsets, and parent-packet offsets from the first indirect root, plus a first
prepared-signature sample and whether that signature varied. Absolute current,
parent, and root addresses, buffer lengths, and individual offsets remain
samples or ranges rather than key fields because frame-local command buffers
and their parent packets rotate through guest memory. Prepared signatures are
also excluded because they describe draw state rather than command-buffer
ownership.
Invalid relationships, unbalanced stacks, address failures, replacement
evictions, and table overflow are counted explicitly. Replacement keeps the
cache bounded without treating lost coverage as false ownership evidence.
The report is complete only when draw accounting balances, all prepared calls
are represented, and both invalid and overflow counts are zero. A clean
shutdown may interrupt synchronous indirect execution after its enter callback;
the summary therefore records the number of open buffers and requires
`enters = exits + open_at_shutdown`. Any other result fails closed.

Create the report from the same diagnostics stream used by the renderer census:

```powershell
python .\tools\summarize-native-renderer-command-lineage.py `
    <diagnostics.jsonl> `
    --static .local\qualification\native-dispatch-static-command-lineage.json `
    --output .local\qualification\native-command-buffer-lineage.json
```

## Safety boundary

The bridge observes packet addresses and register-derived draw metadata only.
It reads no guest resource payload, changes no guest state or control flow,
and does not add a renderer or suppression API. Xenos remains authoritative.
Crash reports include only the bounded lineage summary, not individual packet
records.

Command-buffer lineage is armed with the renderer census itself. The broader
title draw-provenance bridge remains independently gated by the optional
dispatch-discovery setting; disabling that setting cannot disable indirect-
buffer enter/exit accounting or the six exact indirect-packet store hooks.

## Runtime qualification — 2026-08-29

Release executable
`167AB428979C2116880667D7888F7EDD3CA2022939A4C0EC2A9585DC0DA46948`
loaded the installed `0.1.0` AppData save through the title and menu into the
live festival scene. Session `20260829T143627Z-p19532` exited normally after a
169.308-second performance capture covering 5,383 samples.

The lineage report completed across 9,016,083 backend draws, including
8,758,586 prepared draws, and collapsed them into four bounded ownership
classes. Invalid lineage and ownership-table overflow were both zero. The six
title hooks recorded 1,813,273 packet generations; 1,792,929 executions matched
an exact retained generation, 14,438 generations were explicitly evicted, and
5,906 remained retained at shutdown. Another 411,033 indirect executions
remained unknown rather than being inferred.

All 2,203,962 indirect enters reconciled with 2,203,961 exits plus one buffer
open at shutdown. Address failures, table overflow, indirect stack faults, and
draw-stack mismatches were zero. Xenos remained authoritative, suppression
remained disabled, and the diagnostics contained no crash, fatal error, device
loss, assertion failure, or unexpected shutdown marker. The visually inspected
festival scene retained the expected car, crowd, structures, HUD, lighting,
and sky. Median derived performance was 30.342 FPS and the 1% low was 19.017
FPS.

## Promotion gate

Runtime qualification demonstrated zero invalid lineages, reconciled
indirect enter/exit/open-at-shutdown accounting, zero stack faults, and zero
overflow, plus exact constructor matches with unmatched producers retained
explicitly. This qualifies dispatch ownership for the matched packet instances.
Semantic identity remains unknown, and suppression remains disabled, until
object and lifetime ownership are independently understood.

The constructor/caller refinement and its additional fail-closed accounting are
documented in `INDIRECT_CONSTRUCTOR_PROVENANCE.md`. Its runtime qualification is
performed as a separate milestone gate; the evidence above remains the baseline
for the original store-and-depth bridge.

The exact owner layer is documented and runtime-qualified in
`INDIRECT_OWNER_PROVENANCE.md`. The next producer layer is documented in
`INDIRECT_PRODUCER_PROVENANCE.md`. Session `20260829T155036Z-p13876`
runtime-qualified its balanced accounting and resolved 4,400,708 producer-
origin draws to five exact live caller edges. Neither refinement changes the
qualified constructor baseline.
