# Historical ReXGlue 0.10.0 patch dispositions

The resulting source is now materialized in ShiftGlue migration commit
`079c10ef1fbe3ef418a1c535ac025ab39dda7a2d`; these numbers are retained only as
historical migration evidence and are no longer replayed during setup.
Later renderer patches 0103–0122 were migrated as normal fork commits through
`01534689ad33442423dc089dd27d08eb984e12eb`.

This record covers every patch in the ReXGlue 0.9.0 series that was present at
project revision `b00fcfe40b544d09cec034fc432fa05cf418d286`. The replacement
series is based on the exact upstream `v0.10.0` commit
`f5337cdc947ff6d4c4196737e2c807a48f2a1fc2`.

| Original | Disposition | 0.10.0 evidence |
| --- | --- | --- |
| `0000` Windows migration-test stabilization | Retire | Both patched files, `migration_scan.cpp` and `template_registry_test.cpp`, were removed by upstream. Current template, output-stamp, codegen-writer, and focused project tests cover the surviving requirements without restoring obsolete test scaffolding. |
| `0001` runtime tracing | Port | Retained project triage events and merged import-reach tracing with upstream's Tracy-started guard. |
| `0002` indirect-dispatch telemetry | Keep unchanged | Applies to the same dispatcher fallback and remains part of crash triage. |
| `0003` first graphics-failure capture | Port | Retained bounded first-failure capture on the reorganized 0.10 graphics path. |
| `0004` input-path telemetry | Port | Adapted to 0.10 `DeviceId`, device enumeration/state APIs, modifier alternatives, and lost-focus/mouse-capture behavior. |
| `0005` context reentry | Keep unchanged | The reentry guard still protects the same guest-context invariant. |
| `0006` owned-chunk control flow | Keep unchanged | The ownership correction remains necessary and its codegen path is unchanged semantically. |
| `0007` configured fallthrough tail calls | Keep unchanged | The configured fallthrough behavior remains distinct from upstream defaults. |
| `0008` XStudio request telemetry | Keep unchanged | Still used for bounded project diagnostics. |
| `0009` module-local thunk reuse | Port | Rebased onto 0.10 dispatcher/module ownership. Unit coverage verifies caller-module routing, reuse, rejection, and unregister cleanup. |
| `0010` reentrant primitive-cache lock | Keep unchanged | Upstream did not replace the nested-lock requirement. |
| `0011` unload recompiled module by name | Keep unchanged | Still required by the project module lifecycle. |
| `0012` retire shared memory watch before callback | Keep unchanged | Ordering remains necessary to prevent callback reentry against a live watch. |
| `0013` direct guest tail calls | Port | Moved the macro to 0.10's generated PCH, taught per-file declaration tracking about tail targets, preserved nonvolatile register publication for SEH funclets, and covered direct branches with a generated-code regression test. |
| `0014` invalid fetch constants | Keep unchanged | The compatibility relaxation remains required and does not overlap a 0.10 replacement. |
| `0015` heap-release failure telemetry | Keep unchanged | Retained bounded diagnostics on the same failure path. |
| `0016` preserve shared XEX heap allocations | Keep unchanged | The shared-allocation lifetime invariant is unchanged. |
| `0017` retire exhausted XMA input | Superseded by `0036` | Its livelock guard is folded into the buffer-aware packet-location state machine, which retires an exhausted active buffer only after its logical read position crosses the buffer boundary. |
| `0018` save lifecycle tracing | Keep unchanged | Retained for save/cache runtime qualification. |
| `0019` save file-I/O tracing | Keep unchanged | Retained for save/cache runtime qualification. |
| `0020` snapshot reentry stack continuations | Keep unchanged | Still supplies the runtime half of restored continuation state. |
| `0021` systemic interior-PC resume | Port | Reconciled dispatch-address handling, register preservation, entry aliases, and current function-dispatcher APIs; focused tests cover nested direct/indirect resumable PCs and invalid dispatcher addresses. |
| `0022` restrict resume aliases | Port | Revalidated as part of the atomic continuation series so aliases remain limited to linked branch/call evidence. |
| `0023` continuation tests | Port | Moved coverage out of deleted upstream test scaffolding into current codegen/output tests and corrected depfile escaping assertions. |
| `0024` entrypoint resume aliases | Port | Adapted the current `init_cpp` template and added focused template coverage. |
| `0025` writable guest cache | Port | Merged with 0.10's filesystem/runtime and Windows link changes; focused cache-mount coverage verifies transient guest writes. |
| `0026` isolate consumer artifacts | Keep unchanged | Source/output separation and version reporting remain required; the prepared SDK retains its own outputs while consumer artifacts stay in the project build tree. |

The replacement series also adds `0027-v0.10-propagate-xxhash-public-headers`.
ReXGlue 0.10.0 exposes `xxhash.h` through public `rex/hash.h`, but kept the
dependency private. Propagating it through `rexcore` and the exported runtime
fixes clean Windows/Clang SDK tests and downstream consumers.

`0028-v0.10-declare-split-fallthrough-tail-targets` closes a declaration gap
found by the first full consumer build. Configured function splits can emit a
synthetic fallthrough tail call after instruction emission; the patch records
that target in the per-file declaration set and extends the full-writer test to
recognize `REX_TAIL_CALL` references.

`0029-v0.10-make-sdk-version-stamping-idempotent` fixes the no-change build
contract. ReXGlue previously replaced the manifest even when `sdk_version`
already matched, leaving it newer than `codegen.build.stamp` and forcing full
analysis on every Ninja invocation. The patch preserves the manifest and its
timestamp when no version edit is needed, with a focused filesystem test.

`0030-v0.10-deduplicate-resume-alias-registrations` resolves a runtime finding
from the first playable 0.10 session. Overlapping/discontinuous function nodes
could expose the same safe return PC and emit duplicate dispatcher mappings.
The patch assigns each alias to one deterministic owner, preserving the
previous last-owner behavior without runtime replacement warnings, and adds a
full-writer regression test for overlapping functions.

`0033-v0.10-match-vmsum-qnan-overflow` replaces the host SSE dot-product
lowering for `vmsum3fp128` and `vmsum4fp128` with the Xenon-compatible
double-precision reduction and final narrowing behavior. Finite dot products
that overflow the guest single-precision result now become canonical QNaN,
while infinite inputs, NaN propagation, reduction order, and signed denormal
flushing are preserved. Focused helper tests cover every edge and PPC fixtures
cover the observed finite-overflow instruction behavior.

`0036-m4-xma-cross-buffer-packet-handles` ports the packet-location model from
Xenia Canary PR `#983` and extends it with explicit failure states, bounded
malformed-buffer warnings, and synthetic ReXGlue tests. All current-packet,
continuation-packet, full-skip, and next-read-offset paths now carry both the
guest buffer index and the packet index within that buffer. This patch depends
on `0017`, whose exhausted-input transition it replaces in place; removing
`0036` restores the independently applicable `0017` behavior.

`0037-m4-xma-multipacket-frame-assembly` adapts the bounded four-payload XMA
frame assembler from ReXGlue commit `51b601a` and routes every source packet
through `0036`'s validated logical packet handles. Split headers and frame data
share one assembly path, invalid sizes and capacity overruns fail with bounded
diagnostics, and synthetic coverage exercises one through four packets across
guest-buffer boundaries. Removing `0037` restores the prior two-payload
decoder without removing `0036`.

`0038-m4-xma-stall-diagnostics` adapts the low-noise diagnostic design from
Xenia Canary PR `#974`, without enabling its uncertain padding change by
default. A no-space event is counted only after the same buffer, input, output,
and admission state persists for eight consecutive work attempts; a changed
observation is normal backpressure and progress. Per-context no-space and
no-progress lifetime
totals log at counts 1, 8, 64, and every 256, with recovery logs only for
episodes that emitted a stall summary. Session performance counters preserve
exact aggregate stall and recovery totals for sanitized support reports. The
optional relaxed-padding admission path is controlled by
`xma_relaxed_padding_admission = false`; removing `0038` restores strict
padding admission and removes only EPIC-03 telemetry and tests.

`0039-gpu-zpd-report-lifecycle-d3d12` adapts the D3D12 portion of Xenia Canary
PR `#1016` at `d35e0b5`. Fixed guest record/slot helpers feed a logical report
map whose lifetimes may span multiple host query segments and submissions.
Per-slot sequence IDs reject stale guest writes, per-index generations protect
the reusable D3D12 heap, fast mode retires asynchronously, and strict mode has
a 2 ms backstop. Sample counts are normalized for internal-resolution scaling,
all EPIC-04 counters are exported, and `occlusion_query = "legacy"` remains the
shipping default and immediate rollback path. Removing `0039` restores the
previous synchronous D3D12 query implementation.

`0040-fh1-zpd-end-policy-and-telemetry` isolates the END-classification signal
reported in Xenia Canary issue `#1099` and commit `8a49c03`. It adds
report-layout, pairwise-sentinel, and relaxed-sentinel policies; an optional
fallback; bounded pre-clear observations; and a final unchanged-sentinel
watchdog. Title-scoped `auto` selects report layout plus pairwise fallback only
for FH1 title ID `4D5309C9`; the project separately gates the supported retail
executable hash. The legacy query path is unchanged and remains the shipping
default until the six-run matrix and ten-cold-boot admission gate pass.
Removing `0040` restores EPIC-04 classification behavior without removing its
logical/physical report lifecycle.

`0041-fh1-resolve-readback-counters` instruments the existing D3D12 resolve
readback path without changing its policy. It counts requests, guest-copy
bytes, fast copies, delayed-slot cache misses, synchronous waits, and measured
wait time. Schema 8 and the launcher use those counters to qualify conservative
Shipping 1×, delayed Experimental 2×, and opt-in Accurate showroom presets.
Removing `0041` removes telemetry only; selecting Shipping 1× remains the
immediate runtime rollback to `readback_resolve = "none"`.

`0042-ppc-partial-vector-store-regression-tests` imports only the semantic
test intent from Xenia Canary commit `30ac9d7`, not its x64 JIT implementation.
Generated native code is checked at offsets 0, 1, 4, 8, 12, and 15 for guest
byte order and preserved destination bytes, with address aliases, unaligned
memcpy head/tail sequences, and 512 seeded randomized differential cases.
The patch changes no runtime lowering; removing it removes test coverage only.

Validation performed on the rebased SDK:

- `unit_tests` and `ppc_tests` build with the pinned Clang 20.1.8 toolchain.
- 1,480/1,480 PPC instruction tests passed with 6,549 assertions.
- The 246-test unit suite passed: 242 tests passed and four pre-existing
  BitStream write cases remain explicitly skipped by upstream.
- No conflict markers, reject files, or binary patch payloads are present.

## Rollback

The last known-good ReXGlue 0.9.0 project revision is
`b00fcfe40b544d09cec034fc432fa05cf418d286`. To roll back before this migration
is merged, use that project revision or abandon this migration branch. After a
merge, revert the migration commit as one unit; do not restore only the version
pin because the 0.10.0 patch series and generated-build contract are atomic.
Then remove the developer-local `.local/rexglue`, `.local/generated`, and
`out/build/win-amd64-release` trees and run the normal setup/build workflow so
the 0.9.0 SDK, generated sources, and consumer binaries are recreated together.
