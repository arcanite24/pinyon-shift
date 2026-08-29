# High-level render hook inventory

This is the NR-00A and NR-05A title-dispatch ledger for the supported USA
retail MS-2505 executable. It separates packet-wrapper identity, which is now
proved, from semantic renderer identity, which remains unknown until runtime
scene evidence supports a family name.

The dispatch extension starts from Pinyon Shift `dev` merge
`38bc3a2239b5c3d1689d0810ab2349e0527cadc6`, ReXGlue `v0.10.0` at
`f5337cdc947ff6d4c4196737e2c807a48f2a1fc2`, and patch stack `0001` through
`0080`. The supported `default.xex` SHA-256 remains
`DB40DF605ADE49A612B35A7A24C38F6004BCB17A88ED6B48288DE16DF9E3987C`.

## Safety boundary

The discovery path is opt-in through
`pinyon_shift_native_renderer_dispatch_discovery` and defaults to `false`.
Each reviewed wrapper opens with `mflr r12`; the hook on the following
instruction observes the caller `LR` through `r12` plus unchanged entry
`r3-r10`. A fixed 256-entry atomic table aggregates caller frequency; it does
not read guest resource payloads or write guest state. The original wrapper,
PM4 packet, Xenos work, arguments, registers, and control flow are preserved.
Discovery records are never suppression evidence.

The NR-05A packet-provenance extension adds exact header-store hooks at
`0x82410328` and `0x829F7CB0`. It correlates title metadata with backend draws
by physical PM4 header address, not by timing or FIFO order. Its fixed
16,384-packet and 4,096-aggregate capacities, failure accounting, and
promotion gate are documented in
[`TITLE_DRAW_PROVENANCE.md`](TITLE_DRAW_PROVENANCE.md).

## Proved wrapper layers

The generated AOT instruction inventory establishes ten runtime wrapper
families:

| Entry | Static evidence | Reviewed identity | Runtime observation |
| --- | --- | --- | --- |
| `0x824079B8` | Directly adapts its entry arguments and calls `0x8240F4D8` at `0x824079F8` | Title draw adapter; semantic family unknown | Hook `0x824079BC`: entry `LR` and `r3-r10` |
| `0x8240F4D8` | Constructs a dynamic-count Type-3 `PM4_DRAW_INDX_2` (`0x36`) header at `0x82410320` and stores it at `0x82410328` | Indexed draw packet wrapper | Entry hook `0x8240F4DC`; exact packet-address hook `0x82410328` |
| `0x824587D8` | Calls `0x82458A88` at `0x82458828` and `0x824589E4` while managing resolve state | Title resolve controller | Hook `0x824587DC`: entry `LR` and `r3-r10` |
| `0x82458A88` | Writes register `0x2208` (`RB_MODECONTROL`) followed by value 6 (`EdramMode::kCopy`) at `0x82458AC0`/`0x82458AD4` | Resolve state-packet setup wrapper | Hook `0x82458A8C`: entry `LR` and `r3-r10` |
| `0x82413AB8` | Stores `PM4_SET_BIN_MASK_LO` and `PM4_SET_BIN_MASK_HI` packet headers | Xenos binning/scissor-state wrapper; semantic tiled-pass role unknown | Hook `0x82413ABC`: entry `LR` and `r3-r10` |
| `0x824736F0` | Stores all four `PM4_SET_BIN_MASK/SELECT_LO/HI` packet headers and calls `0x82413AB8` | Xenos binning-state reset wrapper; semantic tiled-pass role unknown | Hook `0x824736F4`: entry `LR` and `r3-r10` |
| `0x829F21A0` | At `0x829F225C`, stores `0xC0002300`; then marks the query ID active at `0x829F2270` | Visibility-query begin wrapper | Hook `0x829F21A4`: entry `LR` and `r3-r10` |
| `0x829F2280` | At `0x829F22E4`, stores `0xC0002300`; then clears the active query ID at `0x829F2308` | Visibility-query end wrapper | Hook `0x829F2284`: entry `LR` and `r3-r10` |
| `0x82D951E0` | Calls query begin at `0x82D95230`, performs five intervening work calls, then calls query end at `0x82D95378` | Visibility-query lifecycle owner; result semantics unknown | Hook `0x82D951E4`: entry `LR` and `r3-r10` |
| `0x829F7C70` | Constructs fixed Type-3 count-one `PM4_DRAW_INDX_2` (`0x36`) at `0x829F7CA8` and stores it at `0x829F7CB0` | Immediate/embedded-index draw wrapper | Entry hook `0x829F7C74`; exact packet-address hook `0x829F7CB0` |

Three additional opcode-`0x36` constructors at `0x829E82D0`, `0x829E8428`,
and `0x829EDB68` build initialization templates. They are inventoried but are
not runtime draw hooks.

No `PM4_DRAW_INDX` (`0x22`) title constructor has yet passed the same stored-
header proof. The scanner reports 98 proved stored packet constructors across
the draw, query, resolve side-effect, binning-state, and indirect-buffer
opcodes it recognizes. Seven are `PM4_INDIRECT_BUFFER` or
`PM4_INDIRECT_BUFFER_PFD` constructors across six functions. Their exact
backend draw lineage contract is documented in
[`COMMAND_BUFFER_LINEAGE.md`](COMMAND_BUFFER_LINEAGE.md).
It explicitly rejects a matching numeric operation in `sub_83051E48` because
its result is not stored as a command packet.

The adapter ABI exposes `r3-r10` at entry and reads two additional stack words
at entry-stack offsets 92 and 100 before calling the packet wrapper. Those
stack values are documented by the static inventory but are intentionally not
read by the passive runtime hook.

## Dirty-state consumption boundary

The indexed packet wrapper consumes and then clears six dirty-mask slices
before packet emission. Four clears affect the 64-bit word at device offset
16 (`0x8240FAF4`, `0x8240FB2C`, `0x8240FB74`, `0x8240FBB8`); one affects offset
24 (`0x8240FC08`); and one affects offset 32 (`0x8240FC40`). Each clear follows
a state-submission call and a mask operation on the loaded word. The adapter
hook therefore runs before all six clears. This proves the capture boundary;
it does not assign semantic names to any mask bit.

## Resolve boundary

ReXGlue's backend boundary remains proved: a Xenos draw with
`RB_MODECONTROL.edram_mode == kCopy` enters `IssueCopy`. The title side is now
also bounded: `sub_824587D8` controls the lifecycle and calls
`sub_82458A88`, which emits the exact `RB_MODECONTROL = kCopy` state pair.
This proves resolve setup and its controller, not which subsequent draw covers
the copy rectangle or which semantic system owns the destination. The
inventory records `title_resolve_setup_and_backend_copy_proved` without using
timing or dimensions as identity evidence.

The controller also proves the surrounding side-effect order: one
`PM4_EVENT_WRITE`, two `PM4_MEM_WRITE`, two `PM4_WAIT_REG_MEM`, and one
`PM4_EVENT_WRITE_EXT` packet. The setup wrapper proves four bin-mask/select
writes and one `PM4_EVENT_WRITE_ZPD` packet. These are exact command-stream
boundaries, not permission to reproduce, reorder, or suppress their effects.

## Query and binning boundaries

`sub_82D951E0` is the proved owner of one visibility-query lifecycle: it calls
the begin wrapper, performs five intervening work calls, and calls the end
wrapper. Exactly two direct callers reach it, at `0x82D9566C` and
`0x82DA9458`. This locates lifecycle ownership but does not identify how the
result is consumed or what semantic object the query represents.

`sub_82413AB8` and `sub_824736F0` bound Xenos bin-mask/select and scissor-state
submission. They provide a concrete lead for tiled rendering, but packet
identity alone does not prove semantic tiled-pass begin/end ownership.

## Static direct callers

`tools/discover-native-renderer-dispatch.py` scans all generated AOT C++ files,
reconstructs instruction addresses from function entries and labels, and
produces a deterministic payload-free JSON inventory. At the current baseline
it finds 72 direct call sites: 38 into the promoted adapter, nine into the
indexed packet wrapper, two into the immediate wrapper, two into resolve
setup, three into the resolve controller, and one into each visibility-query
wrapper. The remaining 16 sites are ten into binning/scissor state, four into
binning-state reset, and two into the query lifecycle owner. The adapter's 38
sites group into 25 caller functions:

| Caller function | Adapter call sites |
| --- | --- |
| `sub_823E6EF0` | `0x823E6F4C` |
| `sub_823F10C8` | `0x823F117C`, `0x823F11BC`, `0x823F12B0`, `0x823F12E4`, `0x823F13DC`, `0x823F1410` |
| `sub_823F74B0` | `0x823F7590` |
| `sub_823FA990` | `0x823FAD40` |
| `sub_82403C38` | `0x824043A8`, `0x82404970` |
| `sub_824426B8` | `0x82442BF0` |
| `sub_82461108` | `0x82461334` |
| `sub_82463AD8` | `0x82463B34` |
| `sub_82469478` | `0x824695D8`, `0x82469608` |
| `sub_829F0298` | `0x829F0348` |
| `sub_829F8D88` | `0x829F94C0` |
| `sub_82B3FB98` | `0x82B4093C`, `0x82B40BE0`, `0x82B40D70` |
| `sub_82B40E60` | `0x82B41BB4` |
| `sub_82C39E98` | `0x82C39F78` |
| `sub_82C3B7D8` | `0x82C3BCF4` |
| `sub_82C3BD78` | `0x82C3C2CC`, `0x82C3C2E8`, `0x82C3C31C`, `0x82C3C354` |
| `sub_82C3F0E0` | `0x82C3F1F0` |
| `sub_82C8C340` | `0x82C8C62C` |
| `sub_82C8F000` | `0x82C8F828` |
| `sub_82C90178` | `0x82C90CB8` |
| `sub_82C90D88` | `0x82C912F0` |
| `sub_82C97CA8` | `0x82C98134` |
| `sub_82DDF158` | `0x82DDF274` |
| `sub_82E67C48` | `0x82E67FCC` |
| `sub_8314A138` | `0x8314A194`, `0x8314A1AC` |

The exact lower-wrapper and query-wrapper sites, return addresses, wrapper
layers, packet constructors, dirty transitions, and hook ABIs remain in the
versioned JSON rather than a second hand-maintained table.

One additional runtime correlation edge is tail-forwarded: `sub_8246FB90`
calls `sub_829ED510` at `0x8246FC74`, and that function preserves the caller
`LR` while tail-branching to `0x82413AB8`. The static inventory records the
original return address `0x8246FC78`, the forwarder, and its branch separately
from the 72 direct wrapper calls.

The entry `LR` is sufficient to correlate runtime frequency with this table.
It is not sufficient to name a call site terrain, road, vehicle, HUD, or any
other semantic family. Those names remain `unknown`.

## Capture and correlation

Generate static evidence and launch the installed AppData save with discovery
enabled:

```powershell
$stateRoot = Join-Path $env:LOCALAPPDATA `
    'PinyonShift\source\0.1.0\.local\preview'
.\tools\capture-native-renderer-dispatch.ps1 `
    -StateRoot $stateRoot `
    -Scene open_world `
    -StaticOutput .local\qualification\native-dispatch-static.json
```

After a clean exit, correlate the diagnostics JSONL with the static inventory:

```powershell
python .\tools\summarize-native-renderer-dispatch.py `
    <diagnostics.jsonl> `
    --static .local\qualification\native-dispatch-static.json `
    --output .local\qualification\native-dispatch-runtime.json
```

The summarizer requires one read-only session summary, verifies aggregate
caller counts, rejects any session that does not prove the no-mutation safety
boundary, and labels every semantic identity `unknown`. An unmatched `LR` is
retained rather than guessed.

Combine the same diagnostics stream with the static inventory to produce a
bounded side-effect report:

```powershell
python .\tools\summarize-native-renderer-side-effects.py `
    <diagnostics.jsonl> `
    --static .local\qualification\native-dispatch-static.json `
    --output .local\qualification\native-side-effects.json
```

The report aggregates query and memexport draws, resolve counts and bytes,
capacity overflow, wrapper activity, and the static query/resolve/binning
proofs. A zero observation is always `unobserved_not_absent`; it is never
absence evidence. The report preserves Xenos authority and suppression stays
disabled.

Repeat each marked scene at least twice, then build a conservative cross-scene
matrix from the runtime reports:

```powershell
python .\tools\summarize-native-renderer-dispatch-scenes.py `
    .local\qualification\dispatch-*.json `
    --output .local\qualification\native-dispatch-scenes.json
```

The scene summarizer rejects unsafe reports and duplicate sessions. It can
label a caller as a stable single- or multi-scene frequency candidate only
after repeated coverage, but it deliberately leaves `semantic_identity` as
`unknown` and both promotion and suppression disabled. Frequency is a lead for
object/lifetime investigation, not semantic proof.

## AppData qualification — 2026-08-29

Clean Release executable
`7FDD30F7FA8F8BDAFEC710770D55C5D91CE5CE59A62F5D7BD1DD3480B478B9A2`
ran against the installed `0.1.0` AppData save through menu, save load, and
live festival gameplay. Session `20260829T105816Z-p27600` exited normally.

The 7,500-frame capture observed 165,637 title-adapter calls from 14 runtime
callers and the same 165,637 calls through the indexed packet wrapper. All 15
runtime caller records matched the static callsite inventory; there were zero
unknown callers and zero caller-table overflow. Resolve controller/setup,
query begin/end, and immediate-draw wrappers were not observed in this scene.
The summary proves no guest payload read, guest-state mutation, control-flow
change, or suppression. All wrapper and caller identities therefore remain
packet-layer evidence, not semantic render-family identities.

Performance telemetry covered 233.758 seconds: median derived FPS was 30.472,
simulation cadence was 29.740 Hz, presentation cadence was 59.985 Hz, and
texture/pipeline cache hit rates were 99.975%/100%. No crash, fatal error,
device loss, or unexpected shutdown appeared. The local visual evidence is
`native-renderer-wrapper-families-open-world.png`, SHA-256
`93F34AF4AAEB1E75FF58A0E4F726343F70F33C868F6956577B551513D33DBF54`.

## Next promotion gate

A direct caller becomes a semantic hook candidate only after independent scene
captures show a stable association and the relevant object, instance,
material, transform, visibility, LOD, streaming, and destruction ownership is
understood. Required coverage remains world, vehicle, road, HUD, garage,
mirror, shadow, exposure, livery, thumbnail, and rewind.

Query begin/end and lifecycle ownership, resolve setup/controller and its
side-effect packet order, Xenos binning-state submission, and the indexed-
wrapper dirty-state clears are now proved. Resolve-draw ownership, downstream
query-result consumption, semantic tiled-pass ownership, resource lifetime,
and semantic caller identities remain open title-side inventory work. Until
those gates are met, all work stays on Xenos and no new draw family may be
suppressed.

The constructor-provenance qualification identified four immediate caller
functions covering every known-origin prepared draw. Static analysis proves
five constructor edges inside those functions and 32 exact direct callsites
into them. Session `20260829T152644Z-p16152` runtime-qualified the passive
owner bridge with 390,818 balanced owner entries and exits, zero stack faults
or constructor-to-owner mismatches, and 1,669,534 owner-origin draws resolved
to ten live callsites. This is exact operational provenance, not object or
lifetime identity; all semantic identities remain unknown.

The next batched layer selects three producer functions behind 1,420,568 of
those draws (85.1%). Static analysis proves seven direct calls into them and
records bounded local argument leads. `INDIRECT_PRODUCER_PROVENANCE.md`
defines the independent balanced stack, exact owner-to-producer join, and
combined qualification gate. Session `20260829T155036Z-p13876` qualified that
slice with 967,815 balanced producer entries and exits, zero stack faults or
owner-to-producer mismatches, and 4,400,708 producer-origin draws resolved to
five exact live caller edges. Semantic object and lifetime identity remains
unknown.

Those five live edges now have four proved caller scopes and exact producer
root equations. `INDIRECT_CONTEXT_ROOTS.md` specifies the balanced passive
hooks and the fail-closed runtime join: context function, producer return, and
the entry-register-plus-offset root must all match producer `r3`. This narrows
the next object/lifetime investigation without claiming a type, instance,
registration, destruction, or suppression candidate.

That receiver investigation now proves `82417BC0` as virtual slot 41 of
`proceduralGeometry::CProceduralModels`, including its exact constructor,
destructor, scalar-deleting destructor, and runtime address generations. The
semantic receiver is entry `r3`; the command root remains the distinct
`r6 + 59712` value. See `PROCEDURAL_MODEL_RECEIVER_LIFETIME.md`. No mesh,
material, LOD, or streaming field is classified yet. The static proof now also
identifies the 512-byte object extent, slot 14 visibility preparation, slot 40
render-state preparation, 92/68-byte descriptor/runtime record strides, and
three 64-byte transform/constant matrix ranges. Balanced runtime epochs carry
the optional stage history to slot 41 without reading guest payload; the
AppData capture refutes treating both stages as a universal prerequisite.

For all 38 direct adapter callsites, the same static inventory now records
`r3-r10`'s last syntactic definition since the nearest intervening call. Simple
loads retain base register, offset, and width; values crossing a call boundary
remain unknown. The exact runtime provenance report joins these leads with
per-signature argument stability, but neither source alone proves an object
type or lifetime.

The packet-provenance bridge replaces “next draw” inference with an exact
address match. The first consolidated runtime capture proved 232,506 exact
title-to-backend matches, but all matched draws ended before the prepared
callback and 40 live address generations reused an address. The bridge now
retains those generations oldest-first for the same exact address, aggregates
unprepared backend signatures instead of discarding them, and treats clean
shutdown packets as accounted when `recorded = matched + pending` holds. The
next milestone capture must show zero address, forwarding, origin, and capacity
faults before any caller association is accepted; prepared semantic coverage
remains unproved until a prepared outcome is actually observed.

The next ownership bridge validates exact current, parent, and root
command-buffer lineage for each prepared backend draw, then aggregates bounded
ownership classes by nesting depth and exact constructor store. Current-buffer
lengths plus packet and parent/root offsets remain bounded evidence ranges.
Prepared signatures remain samples because they describe draw state, not
buffer ownership. Its
milestone capture must show zero invalid relationships and zero capacity
overflow before any ownership-class association is accepted. Static
constructor identity remains separate until an exact title-to-buffer join is
proved.

That join is now implemented for the six stored indirect-buffer packet sites.
Title hooks record only each store's effective physical address. ReXGlue patch
`0083` brackets synchronous indirect execution with balanced observations, so
the active stack can attach a store address to a prepared draw only through an
exact parent-packet, target-buffer, root, and depth match. Copied templates and
other producers remain unknown; no guest payload is read.
This ownership bridge follows the renderer-census lifecycle directly and does
not depend on the optional title dispatch-discovery toggle.
Its constructor join uses a bounded four-way generational cache: exact backend
addresses consume the oldest retained title generation, while collision
evictions and all unmatched producers remain explicit unknowns.

Session `20260829T143627Z-p19532` runtime-qualified this bridge on the installed
AppData save. It covered 9,016,083 draws and 8,758,586 prepared draws in four
ownership classes, with 1,792,929 exact constructor matches. The run had zero
invalid lineages, aggregation overflow, address failures, table overflow, stack
faults, or draw-stack mismatches. All 2,203,962 enters reconciled with
2,203,961 exits and one buffer open at shutdown. The bounded cache reported
14,438 evictions and retained 411,033 executions as unknown rather than
guessing ownership. Xenos remained authoritative and suppression stayed off.

That follow-up capture, session `20260829T123251Z-p12356`, completed the exact
accounting contract with 107,455 backend matches, 105 shutdown-pending packets,
40 handled live-address reuses, 66 statically joined unprepared aggregates, and
zero attribution faults. This qualifies the exact title-to-backend bridge. It
does not qualify title-to-prepared provenance: every exact match retained the
explicit `not_prepared` outcome.

The follow-up NR-05A bridge adds a one-per-attempt D3D12 outcome observer for
all 21 `IssueDraw` returns. Session `20260829T125853Z-p38524` observed 8,478,174
outcomes with zero missing or mismatched callbacks: 8,216,916 completed,
261,210 EDRAM copies, and 48 no-rasterization/memexport exits. Every one of the
132,568 exact title matches was an EDRAM copy. The bridge therefore explains
the absent prepared callbacks while remaining passive, Xenos-authoritative,
and suppression-ineligible.

## Side-effect-boundary qualification — 2026-08-29

Clean Release executable
`9C0D2318A9B361014457FEBD96802559C694339640287CD3331EC63A92A93CC0`
ran the installed `0.1.0` AppData save through menu, save load, and live
festival gameplay. Session `20260829T112833Z-p40656` exited normally after
6,916 frames.

The ten passive hooks recorded 1,304,743 calls from 26 runtime callers. Static
correlation matched all 26, including the tail-forwarded binning-state edge;
there were zero unknown callers and zero caller-table overflow. The new
binning/scissor wrapper observed 978,620 calls from eight callers, while the
binning-state reset wrapper observed 11,845 calls from three callers. Query
and resolve title wrappers were not exercised in this scene and remain
unclassified.

Twenty-four bounded census windows recorded 263,328 resolves totaling
149,780,066,304 bytes, with zero target/page overflow. Query and memexport
draw counts were zero and are classified `unobserved_not_absent`. Xenos stayed
authoritative, suppression remained disabled, and the report proves no guest
payload read, guest-state mutation, or control-flow change.

Median derived performance was 30.463 FPS over 207.904 seconds; simulation and
presentation cadence were 29.716 Hz and 59.984 Hz. Texture/pipeline cache hit
rates were 99.983%/100%. No crash, fatal error, device loss, or unexpected
shutdown marker appeared.
