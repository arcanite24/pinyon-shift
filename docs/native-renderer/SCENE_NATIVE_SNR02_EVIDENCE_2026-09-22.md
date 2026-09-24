# SNR-02 title submodel and resource evidence

Status: in progress. This evidence identifies selected local-car submodels and
their prepared GPU resource census. It does not qualify a native scene, material
mapping, resource lifetime or draw suppression.

## Exact local-car GPU census

The [SNR-00/01 evidence log](SCENE_NATIVE_SNR00_01_EVIDENCE_2026-09-22.md#local-car-title-buffers-join-exactly-to-prepared-draws-and-fetches)
establishes the profile-bearing player → `CCar` → `CCarPresentation` →
`CCarModel` chain. Its 49 view-8 title buffers join by exact packet header and
target to 108 backend executions and 268 prepared draws. The draw set contains
104 index-range/primitive tuples, 48 vertex-buffer layout tuples and 25 texture
payload tuples. The verifier command is:

```powershell
python tools/verify-snr01-player-presentation.py `
  .local/native-renderer/snr01/local-car-selection-run-a-full.log `
  --require-owner-calls --require-backend-join
```

These tuples are a bounded starting set. GPU fetch state does not identify
title material roles or distinguish allocation and payload generations.

## Selected `CCarSubModel` records

Generated `sub_82439960` calls `sub_824385D8` with its third entry argument as
the selector. The returned record has a pointer at offset 356 that the title
reads before building draw state. A read-only hook at return `0x82439990`
records that pointer and 32 bytes of its inline data. The verified base image
SHA-256 is
`6014727FA7B0B79727FD5F32A2E2377533DC8E29679E8D2462BD764D331FA305`.
For observed record vtable `0x8223FDD0`, it resolves complete-object locator
`0x8235E00C` and type descriptor `0x832B40F0` to `CCarSubModel`.

The saved sustained-race replay exited normally with seven captures. Executable
SHA-256 was
`CFA582FE0A77D185A4ED5CAE5630CCE9537DB5B7C96A6690DF01E710E977B0BD`.
The isolated source-frame-6000 log at
`.local/native-renderer/snr02/local-car-model-tags-run-a.log` has SHA-256
`4856D898A8B6850F8380C17E03DCF7BDDD85453C037B28D3060043A31D21E279`.
`tools/verify-snr01-player-presentation.py --require-model-records` passes on
that log.

| Selector | Title inline name | Direct model calls | Selected records |
| ---: | --- | ---: | ---: |
| 0 | `winga` | 2 | 1 |
| 7 | `exhaustRa` | 2 | 1 |
| 10 | `bumperRa` | 7 | 1 |
| 17 | `mirrorR` | 3 | 1 |
| 18 | `mirrorL` | 3 | 1 |
| 33 | `headlightL` | 6 | 1 |
| 34 | `headlightR` | 6 | 1 |

All 29 direct model calls selected one of these seven stable record and inline
name pointers. The other two local model calls entered `sub_82419A30` and
emitted four scene buffers each; they do not pass through this record lookup.
The names identify title submodel slots, not draw material roles. Some selectors
share shader pairs while using disjoint index ranges; shader identity cannot
replace the title record. The selected record goes into `sub_824399F8` for
transform preparation; geometry and material ownership still need a separate
join before SNR-02 can close.

## Submodel to prepared-draw partition

The same replay's full timestamp-ordered diagnostic log is at
`.local/native-renderer/snr02/local-car-model-tags-run-a-full.log` (SHA-256
`ECE23DC261192D72BD55CE768A2B112B61AD2AC907205CD730A75586C072EFCB`).
Run the verifier with both `--require-model-records` and
`--require-backend-join` to check the selected record, scene packet, backend
execution and prepared-draw chain in one capture.

| Title path | Scene buffers | Backend executions | Prepared draws | Distinct index tuples |
| --- | ---: | ---: | ---: | ---: |
| `winga` | 2 | 4 | 4 | 2 |
| `exhaustRa` | 2 | 4 | 4 | 2 |
| `bumperRa` | 7 | 14 | 14 | 7 |
| `mirrorR` | 3 | 6 | 6 | 3 |
| `mirrorL` | 3 | 6 | 6 | 3 |
| `headlightL` | 6 | 17 | 19 | 6 |
| `headlightR` | 6 | 17 | 19 | 6 |
| Separate `sub_82419A30` list path | 8 | 16 | 40 | 5 |

These 112 model draws partition by exact caller and selector: 72 arise from
the seven named `CCarSubModel` records and 40 from the separate list path.
The latter reuses selector value 0, so grouping by selector alone would
incorrectly label those 40 draws as `winga`. The local presentation accounts
for the other 156 draws in the 268-draw car census. This is draw provenance,
not proof that each backend execution is a distinct visible car part.

## Static path after submodel selection

The generated title code makes a useful boundary explicit. `sub_824399F8`
reads the selected record's byte at +352 and its binding pointer at +356. It
copies a 64-byte matrix from either the model at +800 or the binding at +176,
optionally composes the record's matrix at +288, and calls `sub_82435F50` to
publish transform state. It does not read a mesh or material pointer from the
record. Back in `sub_82439960`, the title loads the model field at +32860
and passes it as argument 5 to `sub_824167F8`. The latter emits the child
scene-list packets, which already join exactly to the 72 prepared draws above.

The separate `sub_82419A30` path instead iterates four model slots at
`model + (3188 + slot) * 4`; it reaches the same scene-list flush but never
selects a `CCarSubModel` record. A record name alone cannot serve as resource
provenance.

An instrumented replay exited normally with seven captures (executable SHA-256
`F27A3F0A5DA31A1F0B81A789ED90E21CE4A2F1D1D1427C3EC4AC0E48CA5C8195`).
Its full bounded log at `.local/native-renderer/snr02/model-inputs-run-a-full.log`
has SHA-256
`B263A4D20A830FC29533B3B32305C230449A6919C61A9DA901E403562FCA1753`.
All 31 local model calls read **1** at `model + 32860`, and all 37 scene-list
flushes received that same value as argument 5. It is not a geometry-list
pointer. All four sampled model slots held the same nonzero source pointer in
every call. The 37 flushes emitted 37 distinct transient list objects.
`tools/verify-snr01-player-presentation.py --require-model-records
--require-backend-join` checks these joins along with the 268-draw census.
Next, follow the renderer state queues used by `sub_824167F8` and relate
their entries to each packet's final geometry and material resources.

## Command-buffer node ownership

`sub_82416A00` reads its command-list object's linked-node head at +116.
For each node it reads a count at +4 and packet pairs from the node's
8-byte entries before writing a child indirect packet at `0x82416F18`.
An extended read-only packet hook captured the node and entry index during
another normal-exit, seven-capture saved-race replay (executable SHA-256
`8736F0EF656CE9594A41EA8FBAF3EA5EF6BD14B319B2E38990F9B69E3E168E06`).
The bounded log is `.local/native-renderer/snr02/model-node-run-a-full.log`
(SHA-256 `442B86F2E2BA2CEDFC651E92380F39DE665CC033E4F4ECE2105C93953B2EB72A`).

Every one of the local car's 49 packets used a distinct node exactly
184 bytes after its distinct command-list object; every node had count 1
and emitted entry 1. That partitions into 37 model and 12 presentation
packets. The same verifier command above checks this capture and its
268 prepared draws. These nodes are transient per-submission containers,
not a reusable mesh identity or resource lifetime key. The resource owner
must be found before this command-list packaging step.

## Title model descriptor to draw provenance

The two direct-model call sites in `sub_82437600` and the third in
`sub_8245AA98` read the model selector and command-list pointer from a
12-byte entry in a vector rooted at `CCarPresentation + 6044`. Both paths
pass those fields directly to `sub_82439960`. Read-only hooks immediately
before the three calls captured the vector header, entry and fields. The
normal-exit, seven-capture replay used executable SHA-256
`13DE77BC8E502F7687CA5F89FC3727CD05BA30B25DFD77E43B377C66438F8F4A`;
`.local/native-renderer/snr02/model-descriptor-run-a-full.log` has SHA-256
`2C328AA8D5EED843BF161356632E97C8282A6239794CB9C301A90794E0F38050`.

All 29 local direct-model calls joined one-to-one to distinct live title
descriptor entries. Twenty-seven entries came from table header 1799 and
two from header 1913; every entry lay within its header's begin/end range
on the 12-byte stride. Its selector matched the selected `CCarSubModel`, and
its command-list pointer matched the corresponding title packet's list
object. The existing packet-to-backend join then accounts for all 72 draws
from these descriptors. The separate two-call, 40-draw model path does not
use this descriptor loop. `--require-model-records --require-backend-join`
now verifies the full descriptor-to-draw chain when these records are present.

These descriptors provide an exact title submission identity for the direct
model path. They still do not identify the mesh/material allocation or
freshness behind each prepared draw. The next ownership trace must follow
who populates the command-list descriptor and its child PM4 buffer, while
keeping the separate path distinct.

## Presentation table owner

A further read-only replay dereferenced the first word at the presentation
table root and the first word of each selected command list. The seven-capture
saved-race route exited normally with executable SHA-256
`E64184AD9AF538A89B88D620227ECFB562F7183A290C3FF37E3D849D0A1F461F`;
`.local/native-renderer/snr02/table-owner-run-a-full.log` has SHA-256
`53D301CF1D89729E3B09ED8EDECCD470E9E85444984E391DB94D67BF40279A7C`.
The existing verifier passed its model-record and backend-join requirements.

For all 29 local direct-model descriptors, the table root's first word points
to a live object whose first word is vtable `0x8200373C`. The image's RTTI
locator `0x8235A9DC` resolves through type descriptor `0x832B036C` to
`TRefCountedObjectThreadSafe<CPresentation>`. The selected command lists begin
with scalar `0x00500009`, not a vtable. This identifies a presentation
reference holder at the table root and confirms that the lists are submission
containers. Neither word identifies a persistent mesh or material owner.

The title lookup `sub_8243CCF0` indexes the table by its three selection
arguments (with the third clamped to 0..5) and returns a list pointer or null;
`sub_8243CDC0` flushes a non-null result. This explains why a direct-model
selector can have no packet, but it does not establish who creates the list
or its geometry payload. The next trace must follow that producer and join
its resource lifetime to the prepared draw.

## Static car asset and material binding lead

`tools/discover-native-renderer-vehicle-asset-material.py` passed against
`.local/derived-source/generated/default` and the verified base image. Its
local output at `.local/native-renderer/snr02/vehicle-asset-material-static.json`
has SHA-256
`199FE0E219BBED156DF7B8FE4A6E7F2C1C520DF7EA130B0488EA383F1326B426`.
The image RTTI distinguishes `CCarMaterialSettingsResourceType`,
`CCarModelResourceType`, `CCarMaterialSettingsResource` and
`CCarModelResource`; the audit checks their vtables against generated functions.

The title's path builder `sub_82543558` uses the `Tire` shader-settings paths,
including UI, normal and SLOD variants, and a `Wheels` asset path. Car resource
construction in `sub_824D11B0` calls material binding `sub_82549670` twice
with its embedded binding object at offset 1056. This proves a title-owned
tire/wheel material *family* and supplies a precise runtime probe boundary:
record the root, binding object, load-UI/SLOD flags and asset-key identity at
`0x82549670`, then follow later resolution to a selected title draw and
its backend geometry. The static audit alone does not prove which selected
local-car draw uses that binding, any other material role, geometry ownership
or resource freshness. No native admission follows from it.

### Runtime binding observations

A default-off, 512-record-capped hook at `0x82549674` ran the saved sustained
race to normal exit with seven captures. Executable SHA-256 was
`190190F83B5CAD5C85F0ED10234D9AB12ED0F585B2D5FDB998D71DBB387B5307`;
the ordered diagnostic log at
`.local/native-renderer/snr02/material-binding-run-a-full.log` has SHA-256
`FDBE5D7ED1A2AE375D5670A22C7F94A2A162C24544C5A52D170A1BD2B0CE4E48`.
The local-car model/backend verifier and camera/view verifier both pass on
this replay; the former again finds 49 buffers and 268 prepared draws.

The hook observed 32 calls between source frames 1449 and 4092. Every call
returned to `0x824D2EE0` within the car-resource construction path, used
binding offset 1056, and passed zero for both load-UI and SLOD flags. The
root address is sometimes reused, while its first word changes; it must not
be treated as a stable resource identity or vtable. Generated
`sub_82543558` reads the asset-key string at root offset 1712 and its capacity
at offset 1732 before appending that key to the tire settings path. Further
inspection of generated `sub_82549670` shows that it passes the resulting
temporary string to `sub_82480FC0`, which moves/copies it into the binding
object. This hook therefore proves path setup, not material-object creation
or resource generation. A later trace must follow resolution from the binding
string to the selected draw. These 32 loading-time records do not yet
establish that any specific local-player draw uses this family.

## Selected car transform input

Generated `sub_824399F8` starts with the `CCarSubModel` record in `r6`.
It copies a 64-byte matrix from either model offset 800 or binding offset
176, depending on the binding flag at offset 28. When record byte 352 is
set, it composes the record matrix at offset 288 into that copy. The call at
`0x82439B54` passes the resulting stack matrix to `sub_82435F50`, which
continues writing title render state. Thus this is an authoritative *input*
to title preparation, not a proved final GPU transform.

A default-off, 512-record-capped read-only pair of hooks at `0x824399F8`
and `0x82439B54` records the selected record, title owner call, 16 exact
matrix words, render-state pointer and flag. The corrected preview executable
SHA-256 was `B037815627439E43AB1A76F98EBF34D3BAB84AEBDB50AE3170D666897C2E646F`.
The seven-capture saved-race replay exited normally; its ordered diagnostic
log at `.local/native-renderer/snr02/matrix-input-run-a-full.log` has SHA-256
`FC087E0B911EC77535DB17710BFFA5C1AA6167BE26D03900295990BFC57B32C2`.
The verifier's model-record, matrix-input and backend-join requirements pass
for source frame 6000.

All 29 selected direct-model calls still join their title descriptors and
records. Twelve call the later matrix-consuming routine and each captured
matrix matches its selected record. Seventeen do not make that call; static
control flow skips it when both the binding and record composition flags are
clear. This replay has 49 local-car command buffers and 268 prepared draws,
including calls without a new matrix input. The trace therefore does not
yet explain the carried render state for those calls or identify the final
matrix at draw time. The number of view-8 presentations also varied from
the earlier capture (four here); the verifier now requires the local
presentation's view-8 ownership rather than assuming all eight car
presentations share it.

The next bounded trace must observe title state after `sub_82435F50` and
associate its matrix with each draw, including calls that reuse state. This
still leaves actual mesh/material identity and resource generations open
before an immutable scene can be admitted.

## Selected track-model instance version

The shared-state draw join in the [SNR-01 evidence](SCENE_NATIVE_SNR00_01_EVIDENCE_2026-09-22.md#both-shared-state-callers-reach-selected-track-model-resources)
identifies a `CTrackRenderModelInstance_Unified` at each selected resource
pointer. Generated `sub_82DEB718` compares the instance's cached low 16 bits
at offset 12 with the parent `CTrackRenderModel_Unified` high 16 bits at
offset 12. Generated `sub_82DEB748` copies that parent version into the
instance; `sub_82DEB7B0` also sets the instance's `0x800` flag while copying
the version. These fields give a bounded readiness/version check, not an
allocation generation.

A default-off probe of both selected shared-state callers captured the
instance, its parent at offset 4, the cached and parent version words, and
the runtime pointer at offset 16. The RelWithDebInfo executable SHA-256 was
`B7AAE85D030B1F0B601EB7A979937ACFAEF7E5BE00C5F692EE342FE2AE49FD48`.
The saved sustained-race route exited normally with seven compatibility
captures. The process-filtered log at
`.local/native-renderer/snr02/track-version-run-a-filtered.log` has SHA-256
`03647848A6B9CF3EB39BEDB3D75D7A74C4101BD09FC59A344EA8E0C75FDBB86E`;
its source-frame-6000 census ledger has SHA-256
`4D445AB3332B5E8DE01D6848C2C03B272116A2B99EB1C7FFACC5063C2BF3B8B7`.
The strict frame-wide census and state/resource/draw verifier passed.

The verifier joins all 164 selected view-8 shared-state packets to all 758
candidate draws. The procedural-model caller contributes 45 packets, three
resource pointers and 128 draws, all with cached version 1. The track-model
caller contributes 119 packets, 113 resource pointers and 630 draws: 606
with cached version 1 and 24 with version 9. Across the complete probe
records for the source frame, all 283 calls have instance vtable
`0x820019CC`, parent vtable `0x82001D74`, nonzero parent and runtime pointers,
ready result 1, and cached version equal to the parent's current version.
The instance flag's high 16 bits are `0x800` in those records.

This proves version parity at the selected call boundaries in this replay.
The next SNR-02 trace must identify the parent/runtime object's mesh and
material choice at the resulting draw, and establish a true generation or
allocation lifetime across release and reload. Until then, pointer plus
cached version is a diagnostic identity only, not an immutable-scene key.

## Track-model descriptor selection reaches selected draws

Generated `sub_824365B0` reads the selected instance's parent at offset 4,
then the parent's model root at offset 48. Its container is model root +128.
After a nonzero halfword check at container +8, it calculates the table index
as `selector_a * 3 + selector_b`, reads the descriptor pointer from the table
at container +40, and passes that pointer to `sub_82439868`. The latter
writes it to the render-state object at offset 1200. The halfword is only a
nonzero gate: it was 1 on all 312 observed calls while indices reached 18,
so it is not the table length.

A default-off hook at `0x8243669C`, immediately after that state write, logs
the parent, model root, table, selectors, index, descriptor and state field
for the selected source frame. The first RelWithDebInfo capture used executable
SHA-256 `819DBE39AF136AC0556DBD87A5126048E2B3AC292172FA66CDE98B9AB893A05E`
and the saved sustained-race route exited normally with seven compatibility
captures. The process-filtered log at
`.local/native-renderer/snr02/track-descriptor-run-a-filtered.log` has SHA-256
`71566B1A275D67BCB93D2482960ED1D74CC0C1B9D780762A38D9D04C49C3F801`;
its strict frame-wide ledger has SHA-256
`CBE3AAAE40E50EA5642D37E29B770CF507FAE7BFF34E4ECDE3B96B751205C729`.
The log calls the nonzero gate `count`; the hook now names it `gate_word8`
after the observed indices disproved the count interpretation. The verifier
accepts both field names and the corrected source builds with executable
SHA-256 `A1B775FAF18FD64D7BDDB3077315BF4DDA1C5FA96996A70478FF2D9D3DE3ACAF`.

For source frame 6000, the strict frame-wide census and the
`--require-track-descriptor` resource join pass. All 312 track-descriptor
events match the parent at the ready check, the calculated selector index,
the parent-root/container relationship and the state field. The 119 selected
track packets carry 86 distinct descriptor pointers and join all 580 track
candidate draws (550 on color `00030000`, 30 on `000C0000`). The other 46
shared-state packets and 138 candidate draws use the procedural-model caller;
this descriptor hook does not cover that caller.

This establishes a title-owned selected descriptor *pointer* for this track
caller and its exact packet/draw join. It does not yet identify the
descriptor's mesh ranges, material/texture roles, transform or resource
generation. The next trace must follow the descriptor through its submission
routine to authoritative geometry and material objects, and independently
resolve the procedural-model caller.

### Descriptor is a command-list container

The static consumer corrects the next-hop interpretation. At flush,
`sub_82417060` reads state offset 1200, loads word 0 from that selected
record and passes it to `sub_824167F8`. A source-frame-only extension of the
descriptor probe captured its first eight words. The RelWithDebInfo executable
SHA-256 was `0E794DA8594509CE045A9EA134141307C4BCD7208C921C43AD9A5046BFD31DE2`.
The saved sustained-race route exited normally with seven compatibility
captures. The process-filtered log at
`.local/native-renderer/snr02/track-descriptor-words-run-a-filtered.log`
has SHA-256
`3D9AA9DBBCF927B3E95D636588CE83496B9BD2F92B8C6C0D02AA708075DCFCC3`;
its strict source-frame-6000 ledger has SHA-256
`D766EEC4098D06C3BDA1FE08BC84066F3E563B39C4AD66276E4B011C0F2E66C8`.

The frame-wide census and
`verify-snr01-state-resource-join.py --require-track-descriptor-words`
pass. All 120 selected track packets have `descriptor.word4 & 0x1fffffff`
equal to the packet's physical command-buffer target; those packets join all
595 track candidate draws. They use 87 distinct selected descriptor pointers
from 114 resource pointers. Across all 258 observed track-descriptor calls,
word 0 equals word 3, words 1 and 5 are zero, and words 0, 2 and 4 are
nonzero. These are observed layout facts, not field type declarations.

The selected pointer is therefore a command-list container in this path,
not an authoritative mesh/material identity. The next SNR-02 step must trace
the nested traversal's geometry/material objects and command-list producer
to the backend fetches and shaders. Treating this descriptor address as a
mesh key would confuse submission storage with the underlying resource.

### Cached track command list and nested rebuild path

Generated `sub_824365B0` turns the selected index into a bit mask and checks
it against flags at the parent object +56. A set bit skips the nested
`CTrackModel` traversal. A sparse default-off gate probe found cache misses
in 21 pre-target 128-frame buckets on the saved sustained race. At source
frame 6000, all 324 observed gates were set. At source frame 6001, two of
324 calls missed; those two calls reached four selected 56-byte records and
one selected view-8 scene packet. Both used the same track-model instance.

The source-frame-6001 runtime vtables are `0x820016B4`, `0x82001474` and
`0x8200143C`, which the verified title-image RTTI identifies as
`CTrackModel`, `CTrackSubModel` and `CTrackMesh`. The generated virtual
dispatches support that traversal: `CTrackModel` slot 2 returns its count
and slot 4 selects a submodel; `CTrackSubModel` slot 3 returns its pointer
range count and slot 5 selects a mesh; `CTrackMesh` slot 5 runs the
selection check at `sub_82437058`. For all four observed record events,
`record = record_base + 56 * CTrackMesh.entry_index`. The bounded
`verify-snr02-track-rebuild.py` checks the earlier parent/flag address,
runtime types, nested call order, record formula and packet scope.
For the rebuilding call that emitted a packet, it also checks that the
selected descriptor's word-4 command target is that packet's target.

The scout used RelWithDebInfo executable SHA-256
`02E048746B6EB647120F33E16E1C8EBE2609E49EBC8199D1C1CE64F248307496`
and exited normally with seven compatibility captures. Its process-filtered
log at `.local/native-renderer/snr02/track-gate-scout-run-a-filtered.log`
has SHA-256
`E1C81034F1ED74FFCF1D6E1BC2BF2CA413323CE9132592D9A6F11ACAF48FFA21`.
The first log labeled the later `r30` value `instance`; generated code has
already changed that register to `parent + 56`, so the hook now calls it
`flags_address` and the verifier accepts both labels while checking the
actual relationship.

A second normal saved-race replay traced frame 6001 as the primary frame,
but all 369 track gates there were cached and the nested traversal did not
run. Its process-filtered log has SHA-256
`C9DB68E9471C0CFA308F891D11DB41EE7ECF1F98B80D48EE06EB8B09CBD64335`;
its strict frame-wide ledger has SHA-256
`6A42A22208047B09B3EAD0A4B418552EEEE7D9FB62ABFAF97ED49775B89A91E0`.
The frame-wide census and command-target join passed for source frame 6001:
164 shared-state packets joined 762 candidate draws, including 119 track
packets and 627 track draws. This replay does not join a rebuilding record
to backend draws, because no rebuild occurred in its traced frame.

The title-side graph now reaches a selected `CTrackMesh` and its 56-byte
record, but the record's geometry/material fields and allocation lifetime
remain unresolved. Rebuild timing varies across replays; the next capture
must trigger on an actual cache miss and retain that source frame through
backend consumption, rather than relying on a fixed source-frame number.

### Event-triggered rebuild reaches backend execution

The default-off `--pinyon_shift_snr02_trace_first_rebuild_after_frame=4800`
probe captures the first track cache miss after that source frame, preserving
its selected descriptor and physical command target. It records selected
`CTrackMesh` records, the title's flush of that exact target and the backend
indirect execution, indexed draws and fetches in the following frame. The
bounded verifier is:

```powershell
python tools/verify-snr02-rebuild-execution.py `
  .local/native-renderer/snr02/track-event-trigger-run-b-filtered.log
```

Two saved sustained-race replays exited normally with seven compatibility
captures each. Run A's process-filtered log has SHA-256
`8209277A7C555DEE29D1D23EF00180C02E2DAA0D4F6A7FD82F6EA079B6921554`.
Its source frame 5017 had a cache miss, four selected record visits and one
flush of command target `0x172593C0`. Backend frame 5018 executed that target
once, preparing two indexed draws with one vertex fetch each. The second
replay used executable SHA-256
`253B1B16E75810ECAFDCE43E9B2B094AFC7C1D5443674E1986D35B248D036970`;
its filtered log has SHA-256
`A83E67AFB988A14BC229BE19FEB7610AF527C99B404075F05510A6BB9B7EEAFB`.
Its source frame 4919 had 18 selected record visits and six flushes of
`0x17499CA0`; backend frame 4920 executed that target six times, preparing
36 indexed draws, 36 vertex fetches and six texture fetches. The records
include repeated visits to the same mesh records within the source frame,
not 18 distinct meshes. Every prepared draw had normalized color mask zero;
the six textured draws had a pixel shader, but still wrote no color. This
captured command list is a depth-only submission, so it does not yet prove a
main-view scene-color material or complete the selected slice.

This establishes a reproducible title `CTrackMesh` record → command-list
flush → backend geometry/fetch chain despite variable rebuild timing. It also
shows why the next capture must select a color-writing view-8 submission.

### View-8 color-writing track contribution

The event probe can now track the presentation view-call ordinal and restrict
capture with `--pinyon_shift_snr02_trace_view_call=8`. A saved sustained-race
replay with the frame threshold at 4800 exited normally with seven compatibility
captures. The RelWithDebInfo executable SHA-256 was
`177182D1F7CC4F2A2F78C990DF9A7FF940A192945088150DA87B104C990621A0`;
the process-filtered log at
`.local/native-renderer/snr02/track-view8-event-run-a-filtered.log` has
SHA-256
`7E17107376F237C11A6032EE4CADCAFB2E59BD612CCB87BCAE2D0D46C53F5347`.
Its title-to-backend chain passes:

```powershell
python tools/verify-snr02-rebuild-execution.py `
  .local/native-renderer/snr02/track-view8-event-run-a-filtered.log `
  --view-call 8 --require-color
```

Source frame 4834 missed the track cache for the selected bit at parent
`0xAAFDF660`, traversed a `CTrackModel` → `CTrackSubModel` → `CTrackMesh`
entry and selected its 56-byte record at `0x2E8F8B80`. The title flushed
descriptor `0x2EB99800` to physical command target `0x17577E60`. Backend
frame 4835 executed that same target and prepared one 2,060-index draw with
one vertex fetch (guest base `0x11C64580`, 39,552 bytes) and three texture
fetches at constants 0, 5 and 13. It has a nonzero pixel shader, normalized
color mask 7 and color attachment `00030000`, one of the two candidate
scene-color groups. The indexed buffer starts at guest `0x11C63560` and is
4,120 bytes. This is a concrete color-writing main-view track contribution,
not a semantic material map: the selected record's fields, texture roles,
transform and allocation/payload generations remain to be established.

### The selected record is a control path, not yet a material key

Generated `sub_824365B0` first tests the selected bit at `parent + 56`.
For a selected 56-byte record, its word 0 can index the table at the traversal
object +16 and pass that entry's field +60 to `sub_82C24168`, but the bit at
`flags_address + 8` can skip the lookup. Independently, record words 10–11
bound a four-byte control range, capped by the title at 20 entries; the bit
at `flags_address + 16` can skip that range. The path passes the selected
`CTrackMesh` to `sub_82450440`, but that callee does not read its mesh
argument; it updates shared command state from the selected descriptor and
control flags. The title then flushes the command list. These are observed
control relationships, not decoded geometry or material roles.

A bounded view-8 replay exited normally with seven compatibility captures.
Its RelWithDebInfo executable SHA-256 was
`A082202D58B7CE16CCD7ECB00C7ACFA3FBF9C91ADBA5CD5CCF16CB01D642B09D`;
the process-filtered log at
`.local/native-renderer/snr02/track-record-flags-view8-run-a-filtered.log`
has SHA-256
`D32FC3CF2D898C5E8FA320C3BA383A6A88FF33AF469F545CBFD41153AB98523E`.
It passes:

```powershell
python tools/verify-snr02-rebuild-execution.py `
  .local/native-renderer/snr02/track-record-flags-view8-run-a-filtered.log `
  --view-call 8 --require-color --require-record-control
```

Source frame 4830 selected one track record with a valid word-0 index, but
`resource_skip_flag=true`: the resource-table lookup did not run in this
call. `range_skip_flag=false`, and its six control words were
`[0, -2, -2, -2, -2, 1]`; the `-2` values take a distinct control branch,
not a resource-pointer dereference. The title flushed `0x17577E60`, and
backend frame 4831 used it for the same color-writing, three-texture-fetch
draw family as the prior replay. The cached resource path means this capture
does **not** establish material ownership or freshness. An exploratory probe
that dereferenced the mesh's raw +140 word crashed; the final probe records
that word without dereferencing it. The next lookup must follow the title's
actual producer and resource-allocation paths, including the earlier point
that populated the cached command list.

### Selected command-list header and backend length

Generated `sub_82439868` stores the selected descriptor pointer at state
offset 1200. `sub_82450440` tests its word 0 but does not consume the
`CTrackMesh` argument. At flush, `sub_82417060` reads descriptor word 0 and
passes it to `sub_824167F8` for submission. A new event-triggered header
capture checks this layout against the same view-8 color draw.

The sustained-race replay exited normally with seven compatibility captures.
Its RelWithDebInfo executable SHA-256 was
`29CBBCDA620CF901206E4BF671B3BBD959B2103C8D425E62308BBECE928EDA0C`;
the process-filtered log at
`.local/native-renderer/snr02/track-descriptor-header-view8-run-a-filtered.log`
has SHA-256
`E683ABF504ABA5B5406178E5F26D5CE8B87894AE61410411160A5D8A75B16910`.
The bounded check is:

```powershell
python tools/verify-snr02-rebuild-execution.py `
  .local/native-renderer/snr02/track-descriptor-header-view8-run-a-filtered.log `
  --view-call 8 --require-color --require-record-control `
  --require-descriptor-header
```

At source frame 4806, the selected descriptor had words
`[0xAC991808, 0, 0xABA251AC, 0xAC991808, 0xB7577E60, 0, 352, 1124]`.
Word 2 equals the selected `CTrackModel` container +44; words 0 and 3 are
equal; word 4 masks to the physical target `0x17577E60`. The next backend
frame executed that target with `command_bytes=1116`, eight fewer than
descriptor word 7, and prepared the same color-writing 2,060-index draw.
This validates a command-list header and owner link for one selected
contribution. It does not identify word 0's allocation owner, establish when
the list was built or map material/texture roles. The next trace should
follow the table entry that supplied this descriptor back to its constructor
and stream/resource generation events.

### Car-presentation scalar resource references

The [frame-wide scalar join](SCENE_NATIVE_SNR00_01_EVIDENCE_2026-09-22.md#car-presentation-scalar-packets-cross-both-candidate-color-groups)
identifies three title packets per `CCarPresentation + 2016` subobject:
two depth-only packets followed by a color-writing packet. Generated
`sub_82443600` reads pointers at subobject offsets `+4` and `+12`. Before
the color packet it checks `+16` and passes that reference to
`sub_824AFB20` when nonzero; otherwise it passes the `+12` reference.
This branch means the `+12` object alone does not prove the selected color
texture in every car.

A default-off scalar trace now snapshots those three pointer fields and
their first words at the three known call sites. The bounded checker
`--require-car-scalar-resources` joins the snapshots to prepared draws,
resolves first-word RTTI against the title image, and requires a stable
three-site packet group per observed subobject. Two saved-race replays with
the final probe exited normally and each produced seven compatibility
captures. Both passed the strict frame-wide census with this additional
check:

| Replay | Prepared draws | Joined car draws | Car subobjects | Filtered log SHA-256 | Ledger SHA-256 |
| --- | ---: | ---: | ---: | --- | --- |
| `car-scalar-field16-run-a` | 3,426 | 9 | 1 | `DF8769C228A36B733C47F8837BD0C43C4AE5E8B10A3264A1E5E46A00A4A5A09A` | `0CF9EC0C53E92183A6D535EBA4085E4F206642C2E23C05250294426C10CAF1B6` |
| `car-scalar-field16-run-b` | 3,352 | 9 | 1 | `332E7F9AB5289A0D3E11C8C67F3EB6469C5D94E0AEDC6C42C4F65051FFFA3EBA` | `BCC9D794A1C338CF1AE844AAAFCA768F3F6BC252CA5688E5C1F7D626AB118394` |

The RelWithDebInfo executable SHA-256 was
`5A25D18068FB59177E1DCA4275486466EDEB2A360E8EB44FC086B6424DFDD583`.
For each observed triple, `+4` resolves to `CFXLShaderResource` and `+12`
to `CTextureResource`; `+16` was zero, so the color path selected `+12`.
The three pointers were stable across repeated prepared executions of each
packet. An earlier probe without `+16` covered six car subobjects and found
the same `+4`/`+12` classes, but cannot establish their color selection.
The selected-reference helper `sub_824AFB20` clears a destination slot,
calls the resource object's virtual slot `+8`, then stores the pointer.
For both observed resource vtables that slot targets `sub_824493C0`, which
atomically increments the object's counter at `+32`; virtual slot `+12`
targets `sub_82448FD8`, which decrements it and destroys on zero. This is
title-side reference ownership, not a proven GPU submission fence or
payload-generation rule.
Object class and pointer identity still do not prove actual GPU payload,
semantic texture role, generation, or submission lifetime. These remain
SNR-02 blockers, and this evidence alone does not admit the car triple to
the native slice.

Rebuild either final ledger from its `.local/native-renderer/snr01` filtered
log, changing `run-a` to `run-b` for the second replay:

```powershell
python tools/summarize-snr01-frame-wide-census.py `
  .local/native-renderer/snr01/car-scalar-field16-run-a-filtered.log `
  --source-frame 6000 --require-direct-family `
  --require-direct-family-record --require-semantic-item-node `
  --require-second-path --require-scalar-draw `
  --require-animated-scalar --require-car-scalar-resources `
  --require-dynamic-quad --title-image .local/ui-verify/default-image.bin `
  --require-candidate-boundary `
  --output .local/native-renderer/snr01/car-scalar-field16-run-a-ledger.json
```

### Car color texture resolves to the prepared fetch descriptor

The observed command-device vtable `0x8200306C` sends virtual slot `+92` to
`sub_82444B18`. Called with the selected resource reference at color-pass
setup, this method follows its `+168` member, calls virtual slot `+20`,
and passes the returned descriptor and texture slot to `sub_82442528`.
That writer reads descriptor words at offsets `+28` through `+48` and
updates the title's fetch state. A default-off hook at `0x82444B68`
records the resource and those already-read words before the state update.

Two sustained-race replays with the final probe exited normally with seven
compatibility captures each. Their RelWithDebInfo executable SHA-256 was
`CC92F85820937887A6F8AF8E7BDD7210F29806E61F0EAC5BEF03EDB8FAB4A0F8`.
Both used `fh1-race-sustained.fh1test` with
`--pinyon_shift_fh1_gpu_corpus=true`,
`--pinyon_shift_fh1_clear_producer_trace=true`,
`--pinyon_shift_snr01_trace_source_frame=6000`, and
`--pinyon_shift_snr01_trace_following_frame=true`; the filtered logs came
from their process-scoped sessions through `extract-snr01-run-log.py`.
The strict frame-wide candidate-boundary census and
`--require-car-texture-descriptor` both passed:

| Replay | Prepared draws | Filtered log SHA-256 | Ledger SHA-256 |
| --- | ---: | --- | --- |
| `car-texture-descriptor-run-a` | 2,794 | `FA30D808CD2299CE5780EC2F426F2B190221B51262CDC310C71AFEA2956D91D4` | `FD79AD7F5B1C815A8437B6A7CB4CE1DAEAD9760869541EB2F750884CF34B77A3` |
| `car-texture-descriptor-run-b` | 3,313 | `26450160D08FCDC1D4BA863EE24BADB09EFCBD324430AC2297C7DB5B2E929F51` | `E98C58AF9DE8AE9F4A018C261092BD72549FC91015B9A3C8800A84BB36E883AA` |

Each replay had one captured car subobject. Its color packet executed three
times, each with exactly one slot-0 texture fetch. The source-frame
resolution event named the exact selected `CTextureResource` pointer and
the next direct packet ordinal. For run A, resource `0x2E09DB40`
resolved to `0x2F1AB0B0`; descriptor word `+32` was `0xB5768086` and the
prepared fetch base was `0x15768000`. For run B, resource `0x2E00B870`
resolved to `0x2EEDB150`; descriptor word `+32` was `0xB5981086` and the
prepared base was `0x15981000`. In both runs, the descriptor's `+32` word
masked by `0x1FFFF000` equals the prepared base,
its low six bits equal format 6, and its `+36` word decodes width and
height as 64 each (`low 13 bits + 1`, `bits 13–25 + 1`). The verifier also
requires an unchanged fetch descriptor across all three executions.

This establishes the bounded title resource → resolved descriptor →
prepared texture-fetch relationship for the observed car color packets.
It does not establish the resource's semantic role, when its texture bytes
were produced, their generation or a lifetime through a native GPU fence.
The depth-only packets have no shader-used texture fetch. A separate
exploratory replay omitted the clear-producer trace and therefore could
not pass the full candidate-boundary check; it was not used for this
boundary claim.

Rebuild either final ledger, changing `run-a` to `run-b` for the repeat:

```powershell
python tools/summarize-snr01-frame-wide-census.py `
  .local/native-renderer/snr02/car-texture-descriptor-run-a-filtered.log `
  --source-frame 6000 --require-direct-family `
  --require-direct-family-record --require-semantic-item-node `
  --require-second-path --require-scalar-draw `
  --require-animated-scalar --require-car-scalar-resources `
  --require-car-texture-descriptor --require-dynamic-quad `
  --title-image .local/ui-verify/default-image.bin `
  --require-candidate-boundary `
  --output .local/native-renderer/snr02/car-texture-descriptor-run-a-ledger.json
```

## Selected procedural descriptor and runtime payloads

The revised Gate A slice includes procedural item/node packets beyond the
vegetation pilot. A bounded, default-off title hook now copies the 92-byte
selected descriptor and 68-byte runtime record at each view-8 procedural
item call in source frames 6000–6001. It records raw words at the title's
selection boundary, before relying on any later pointer. The hook does not
reinterpret those words as a mesh, material or allocation generation.

The AppData-backed sustained-race replay exited normally with seven
compatibility captures. Its process-filtered log is
`.local/native-renderer/snr02/item-payload-run-a-filtered.log` (SHA-256
`59B5AA85CED26C077EF5F78676B50BDB830CC42790AA7A1B426B250B1678322A`).
The strict frame-wide ledger and revised pilot-slice verifier passed all
3,241 prepared draws. The selected slice contains 308 procedural-item
backend draws from 174 exact title calls. `tools/verify-snr02-item-payload.py`
joins **all 174** calls to their selected descriptor and runtime payloads,
validates each descriptor's kind at offset 36, and confirms the already
observed title addresses and submit calls. Selected descriptor kinds are
0:155, 1:6, 4:8 and 5:5; these are raw enums, not material roles.

The probe also observed the same 174 runtime addresses in both source
frames. Four records changed **word 15 (offset 60)** from `0x00000008` to
`0x00000028` while retaining the same address; the 92-byte descriptor
payloads at those selected addresses did not change in this capture. This
is direct evidence that a runtime address is not an immutable per-frame
payload identity. The meaning of the changed word and the upstream
generation rule remain unproved. A later SNR-03 scene must own the selected
words or pin a validated immutable resource through consumption, and SNR-02
must still connect them to mesh ranges, material roles and lifetime.

Reproduce the join with:

```powershell
python tools/verify-snr02-item-payload.py `
  .local/native-renderer/snr02/item-payload-run-a-filtered.log `
  .local/native-renderer/snr02/item-payload-run-a-ledger.json
```

The result is a complete bounded **title record payload join** for one
selected family, not yet its GPU geometry/material map or admission to the
private renderer.

The same process log also contains prepared vertex and texture fetches for
backend frame 6001. The verifier now joins every one of the 308 selected
draws by ordinal, execution and packet to those fetches and to its title
item call. Each draw has one fetch-95 vertex stream, 10 words per vertex,
with a reported length equal to its draw vertex count times 10 words. The
174 calls resolve to 174 distinct guest base/length ranges; repeated draws
of a call use one range. All selected draws have no explicit index buffer
and use guest primitive 13. The observed raw kind-to-prepared-footprint map
is:

| Title kind | Draws | Vertex shader | Pixel shader | Texture fetches (slot, raw format) |
| --- | ---: | --- | --- | --- |
| 0 | 272 | `3BC346726C1C2535` | `9584B309533EF6C9` | (0, 20) |
| 1 | 6 | `BDFD2AD68464101A` | `9584B309533EF6C9` | (0, 20) |
| 4 | 17 | `CB8AC98467C0C283` | `F2A369E97366ADFA` | (0, 20), (13, 6) |
| 5 | 13 | `A715C815EDB8EEE8` | `F2A369E97366ADFA` | (0, 20), (13, 6) |

This is a title call → prepared geometry/fetch relationship, not a semantic
material map. The prepared vertex records have no CPU byte snapshot for
these draws. The existing SDK `geometry_range` helper bounds an owned GPU
geometry import for the kind-0 shader when its layered-root conditions hold,
but this capture does not prove those conditions or immutable bytes for all
four kinds. Texture bytes, source material ownership and resource generations
remain open.

### Prepared procedural vertex bytes at the draw boundary

The SDK's existing prepared-draw snapshot path was extended, default off,
to the four observed procedural shader families when the SNR-02 item probe
and source-frame trace are enabled. It copies the CPU-owned fetch-95 range
at backend draw preparation, with a 256 KiB per-draw and 8 MiB per-frame
budget. A failed CPU snapshot has a distinct status; the hash alone is not
used as an immutable scene payload.

A corrected RelWithDebInfo replay used the staged SDK graphics DLL, the
AppData-backed `fh1-race-sustained.fh1test` route and the existing source
frame 6000 flags plus `--pinyon_shift_snr02_item_payload_probe=true`.
It exited normally with seven compatibility captures. The filtered log is
`.local/native-renderer/snr02/item-snapshot-run-b-filtered.log` (SHA-256
`8276841B1CC68B642F386D29D6923FB87FC072255746C7DAA3771501C10D11CA`);
the strict frame-wide ledger is
`.local/native-renderer/snr02/item-snapshot-run-b-ledger.json` (SHA-256
`E0706C51177F060FAD2ABF088EFE36AAE073AF0A71A5284F48593ED7AFFBE229`).
All 3,406 prepared draws passed the candidate-boundary census. The selected
procedural family had 308 draws from 174 title calls. All 308 vertex
snapshots returned status 1 with a nonzero hash, totaling 1,116,680 copied
bytes including repeated draws. The 174 distinct address/length ranges
total 518,400 bytes; the largest was 54,320 bytes. Every repeated draw of
one title call had the same base, length and snapshot hash in this frame.

Recheck the exact title-to-prepared join and snapshots with:

```powershell
python tools/verify-snr02-item-payload.py `
  .local/native-renderer/snr02/item-snapshot-run-b-filtered.log `
  .local/native-renderer/snr02/item-snapshot-run-b-ledger.json `
  --require-vertex-snapshots
```

The SDK currently discards these copied bytes after the prepared-draw
callback. SNR-03 still needs to publish owned bytes with the exact title
call, transform/constants and resource generation through consumption.
One frame of equal hashes does not prove streaming lifetime, material roles
or private-renderer coverage.

### Owned procedural geometry at the output-frame handoff

The opt-in probe now copies each view-8 title descriptor/runtime record and
its one emitted packet into a source-frame scene. At prepared draw, it owns
the first successful vertex snapshot per packet and compares every repeated
draw byte-for-byte. The scene is bounded to 512 calls and 2 MiB of unique
vertex bytes, rejects missing or unstable packets, and is consumed only by
the immediately following output frame. It writes an `SNR02I1` fixture
containing owned title records, camera matrices and vertex bytes; compatibility
output remains unchanged.

An AppData-backed sustained-race replay exited normally with seven
compatibility captures. Its strict frame-wide ledger has 3,118 draws and
passes the candidate-boundary and Gate A slice partition checks (1,779
selected, 70 retained, 1,269 outside). The procedural family contributed
277 selected draws from 167 title calls. All 277 draw-time snapshots passed;
the output-frame scene retained 500,280 unique vertex bytes across 167
packets. The independent fixture verifier matched every raw title record,
packet, guest range and vertex-byte hash to the source and backend trace.

| Evidence | Local path | SHA-256 |
| --- | --- | --- |
| Fixture | `.local/native-renderer/snr02/item-owned-scene-run-a/snr02-items-6000.bin` | `F55B18FE356694A8AC0B9305DB4BDB42395E63C6F2DAC03F1440642F07573117` |
| Filtered log | `.local/native-renderer/snr02/item-owned-scene-run-a-filtered.log` | `6DDFE76E6E7E614C5191320211BFB32D0DDD18C3C351498F60901B3DE190BC3F` |
| Strict ledger | `.local/native-renderer/snr02/item-owned-scene-run-a-ledger.json` | `0B90E5C7D65E6AD5658BE6E81919378946A6826F4F56B1450ADA8405892C1743` |

```powershell
python tools/verify-snr02-item-scene.py `
  .local/native-renderer/snr02/item-owned-scene-run-a/snr02-items-6000.bin `
  .local/native-renderer/snr02/item-owned-scene-run-a-filtered.log `
  .local/native-renderer/snr02/item-owned-scene-run-a-ledger.json
```

This fixture proves title and geometry ownership through one output-frame
handoff. It does not yet contain final per-draw constants, state variants,
texture contents or generations, so it cannot drive the SNR-04 private
renderer or qualify the full frozen slice.

### Ordered final state for repeated procedural draws

The SDK now provides the same draw sequence to prepared and final-state
observers for the four measured procedural shader families. The owned scene
stores one state per sequence: vertex/pixel shader identities, vertex count,
two bounded texture fetch descriptors, the complete 256-register vertex
float bank, final 64 system words, fetch-47 words and dynamic-state identity.
It requires every prepared draw to receive exactly one matching final
callback before writing the version-2 fixture. These are diagnostic inputs;
they do not replace the compatibility renderer or establish texture lifetime.

The sustained-race replay exited normally with seven compatibility captures.
Its strict candidate-boundary census passed 3,273 prepared draws; the Gate A
partition counted 1,597 selected, 70 retained and 1,606 outside. The
procedural family supplied 300 selected executions from 178 title calls.
The `SNR02I2` fixture retained 485,320 unique vertex bytes and all 300
ordered state variants. The independent verifier checked every title record,
packet, draw sequence, shader identity, texture-fetch descriptor, vertex
register hash and final system/fetch hash against that replay's log and
ledger. The fixture is 1,862,932 bytes.

| Evidence | Local path | SHA-256 |
| --- | --- | --- |
| Version-2 fixture | `.local/native-renderer/snr02/item-final-state-run-a/snr02-items-6000.bin` | `840997E2A3F14D780F128499B6DB8D0F0F99E985DCA5076D26287175DE0038A2` |
| Filtered log | `.local/native-renderer/snr02/item-final-state-run-a-filtered.log` | `4167A05D64DB6D6858C782FBA6FCF899CB3A94D349ACD13055F4D5E4A58494D3` |
| Strict ledger | `.local/native-renderer/snr02/item-final-state-run-a-ledger.json` | `4FDCCB9DA228F604BA46FE4736CF7F6FA617A0E7A6FDBC2E68814200CBB06810` |

```powershell
python tools/verify-snr02-item-scene.py `
  .local/native-renderer/snr02/item-final-state-run-a/snr02-items-6000.bin `
  .local/native-renderer/snr02/item-final-state-run-a-filtered.log `
  .local/native-renderer/snr02/item-final-state-run-a-ledger.json
```

One selected draw inherited its vertex-fetch register from an earlier
backend execution (`3650157` versus draw execution `3650245`). The
draw-time owned bytes and packet/state joins passed. The verifier now
reports this provenance separately instead of assuming that fetch-register
writes always occur in the draw's execution.

The fixture still lacks semantic material ownership, texture byte
generations and a private render of these four vertex shader variants.
SNR-03/04 and the full selected-slice coverage gate remain open.

### Procedural vertex-shader binding map

The version-3 owned fixture adds the SDK shader's exact 256-register vertex
bitmap and packed-vector count to each ordered draw. A sustained-race replay
exited normally with seven compatibility captures; its strict census passed
3,623 draws and the Gate A partition counted 1,771 selected, 70 retained
and 1,782 outside. The fixture owns 174 selected procedural calls, 308
ordered draws and 518,400 unique vertex bytes. The independent verifier
matched all raw title records, geometry, shader identities, draw sequences,
texture fetches, vertex register words/bitmaps and final system/fetch words.
All 308 guest primitive-13 draw counts are divisible by four.

| Evidence | Local path | SHA-256 |
| --- | --- | --- |
| Version-3 fixture | `.local/native-renderer/snr02/item-vertex-abi-run-a/snr02-items-6000.bin` | `8598EC404038F8B117627074E48EA919EB83E66EEB0550F9AEBDDCB4C380880C` |
| Filtered log | `.local/native-renderer/snr02/item-vertex-abi-run-a-filtered.log` | `6B46445DF3B3FF497794A51A286AD2EE87A97C5FCD1A32BC9036807705CCEFA7` |
| Strict ledger | `.local/native-renderer/snr02/item-vertex-abi-run-a-ledger.json` | `43F6934E25E309535B759123D9FF1B2DA546BAEBAECC0297DAF3B8243491575F` |

The four captured vertex bytecodes all bind a raw shared-memory SRV at
`t0`, system constants at `cb0`, packed vertex float constants at `cb1`,
fetch constants at `cb3`, and a declared raw UAV at `u0`. Their captured
hashes and `fxc /dumpbin` float-vector counts agree with the live bitmap:

| Vertex hash | Bytecode SHA-256 | Packed vectors | Guest register map |
| --- | --- | ---: | --- |
| `3BC346726C1C2535` | `113B8C594001B1593FFF3F4861C788342721A8B7E0251BEF9E41688A69AE7C31` | 25 | A |
| `BDFD2AD68464101A` | `42CFD0A51E91B4F00F2F0F40CBC4A9F689316FBD6950ABD9DBD2DA4D3458A347` | 25 | A |
| `CB8AC98467C0C283` | `F759D5DE1BE2B8E4913D86E9C11210CD1EE76F33FF004B88FA4DD533E347B02C` | 23 | B |
| `A715C815EDB8EEE8` | `5C8692DDF2FF735D28B7B5F1FDCE740B6BE443EE942191C8D912D9A22852A269` | 23 | B |

Map A: `128–131, 157–160, 162–163, 198, 213–215, 221, 241–245,
250–251, 253–255`. Map B: `0, 128–131, 157–160, 163, 198, 213–215,
241–245, 250, 253–255`. These are guest register numbers in ascending
shader-pack order, not inferred material fields. The fixture retains all
256 raw guest registers, so a private diagnostic can pack exactly the
shader-used values without mutable guest reads. The captured fetch-47 words
also include the fetch-95 descriptor used by these shaders. Raster winding,
exact post-VS positions, coverage/depth parity and texture generations
still require a private same-frame diagnostic and compatibility comparison.

The subsequent [SNR-04 procedural diagnostic](SCENE_NATIVE_SNR04_PROCEDURAL_EVIDENCE_2026-09-23.md)
renders all 312 ordered draws in a new replay with an immutable owned fixture
at the output-frame handoff. It establishes geometry/ABI coverage for this
family, while compatibility attachment parity and material ownership remain
open.

## Live foliage BC3 source and invalidation join

The opt-in SNR-04 BC3 readback now logs the bound texture cache object,
host resource, guest base/mip addresses, guest byte extents and dirty mask at
the copy point. The source row follows the selected unsigned fetch-0 binding;
the copy is recorded on the guest command stream and read only after its
submission fence. A normal-exit AppData-backed sustained-race run captured
source frame 5000/output frame 5001 with compatibility rendering intact.
Its 7 route screenshots completed, and the process shutdown normally.

All five sampled textures were 256×256 BC3 with 65,536-byte guest base and
mip ranges and `outdated=0` at copy time. The five complete nine-mip
readbacks (87,408 bytes each) match the **five** independently captured
RenderDoc chains byte for byte:

| Live SRV | Guest base / mips | RenderDoc chain |
| ---: | --- | --- |
| 564 | `0F358000` / `0ECBD000` | `ResourceId-7771` |
| 566 | `0F348000` / `0ECB0000` | `ResourceId-7770` |
| 568 | `0F368000` / `0ECCA000` | `ResourceId-7769` |
| 785 | `0FD84000` / `0EFAE000` | `ResourceId-7849` |
| 877 | `1075A000` / `0E4DA000` | `ResourceId-7929` |

The last key was **not immutable throughout the run**: its mip range was
invalidated by CPU writes twice and its base range once, with a matching
reload attempt after each invalidation. The last reload attempt preceded the
frame-5001 sample, whose cache dirty mask was zero. The other four keys had
no observed invalidation or reload attempt in this run. This proves a
bounded descriptor → live cache resource → current GPU payload join at the
sampled frame. It does not identify the title material object, assign an
allocation or payload generation across reuse, prove every reload completed
at a native submission fence, or qualify streaming unload/reload.

The RelWithDebInfo executable SHA-256 was
`A92917CE435D8B7EAD7B8A5E5E2AE1E6DEBD5BEA9356AC7228594EFA5787D63C`;
the staged `rexgpu-fh1rd.dll` SHA-256 was
`945E3C181FCE81BD8F377A7B5D203FFE4224A5A690421D5840CB2DA4C76E2642`.
The local process-filtered log is
`.local/native-renderer/snr02/bc3-source-live-a/evidence.log` (SHA-256
`72882BF5AB7B0FEAA53AD4070DCD1B14D5DD3009E66A653472264BF1F3AFA431`),
and its checked source join is `source-join.json` (SHA-256
`22B049068BB96C3290948B2331E7A7F8D39632F61EA5CCEA01CC214180E59552`
after rechecking with the completion-aware verifier).

Reproduce the process-scoped evidence with `extract-snr01-run-log.py
SESSION OUTPUT --include-bc3-source` using session
`20260924T020223Z-p43916.jsonl`, then run
`verify-snr04-bc3-source-join.py LOG LIVE_DIR REFERENCE_DIR OUTPUT
--frame 5001`. The launch used `fh1-race-sustained.fh1test`,
`--pinyon_shift_snr03_probe_frame=5000`,
`--fh1_texture_reload_probe=true`, and
`PINYON_SHIFT_SNR04_BC3_DIR` pointed at the local run directory. The source
row and readback are diagnostic-only and default off. The next ownership
check must follow the title material object into these guest ranges and
distinguish cache object creation from subsequent payload changes; address
equality alone is insufficient.

### Completed reloads on the sampled cache object

A second normal-exit sustained-race run (`20260924T021813Z-p22028`) made the
existing opt-in texture reload probe log the cache object on invalidation and
reload attempt, plus each completed cache load. It produced seven route
captures and five fenced frame-5001 BC3 mip chains. The completion-aware
source verifier again matched all five chains byte for byte to the independent
RenderDoc reference. The same five guest base/mip pairs appeared with
different run-local SRV indices (524, 528, 531, 600 and 769).

The sampled object for base `1075A000` / mips `0E4DA000` had one CPU mip
invalidation and one CPU base invalidation in this run. Each was followed,
in process-log order, by a reload attempt and a completed load of that part
on the **same cache object** before its `outdated=0` readback copy. The other
four sampled objects had no observed invalidation before their copy. This
closes the earlier uncertainty about whether those observed reload attempts
completed for the second run. It does not establish a title material owner,
guest allocation generation, or an unload/reload lifecycle. A completed
cache load is not itself a native GPU submission fence; the subsequent BC3
readback is fenced for the sampled frame.

The executable SHA-256 was
`0C91E84B8BB6C8ECFEB90E3A24E6F1A42B93A4CB92C4D5F0554458AE39CB2E16`;
the staged graphics DLL SHA-256 was
`F552FB1233CFFC712E111BCC881D0E6C4DAA6A167D0BB9746C88F1EB65F8724D`.
The process-filtered log is
`.local/native-renderer/snr02/bc3-complete-live-b/evidence.log` (SHA-256
`E8E53AE03EA7C286BFD382D10DC490D92B7FC406E30A50FC49F38E0465DD3AA6`),
and its checked `source-join.json` has SHA-256
`BB94BB2AC55195B01B76A633CA0BA021E4349EAEFAF35C403224F1F4579E0A97`.
Reproduce with `extract-snr01-run-log.py SESSION OUTPUT
--include-bc3-source` and `verify-snr04-bc3-source-join.py LOG LIVE_DIR
REFERENCE_DIR OUTPUT --frame 5001`. Both probes default off.

## Title vegetation texture key to sampled BC3 payload

Generated `sub_824136F0` selects a vegetation record and reads an owner-local
control table before submitting it. The table's secondary slot indexes an
eight-byte owner-local entry; its first word is passed as `r4` to
`sub_82415BF8`. That function compares the word against a five-slot cache,
resolves a changed key through `sub_82415AD0` and binds the resulting object
through the graphics context's vtable slot 88. A default-off hook at
`0x824139B8` records the selected record, the global 28-byte graphics-state
entry, the owner-local slot and the candidate key before the draw.

The first AppData-backed source-5000/output-5001 run exited normally with
seven compatibility captures. Its 55 selected title records joined 115
prepared fetch-0 executions and five fenced BC3 sources. All 55 selected
records used **global state index 0 and the same 28-byte entry**. The global
entry therefore cannot distinguish the five foliage textures. The filtered
log is `.local/native-renderer/snr02/foliage-title-state-a/evidence.log`
(SHA-256 `BB2750C72F59AEED6E897D61B2876732FC034BCB7862D35B71F59C9C6F10D57C`);
its checked `state-join.json` has SHA-256
`EA7BC544A8F84817BCAFBE2A30A1CA62D6EDAD4784A4A234DB7C0876F180E70B`.

The expanded hook captured the owner-local lookup in a second normal-exit
run (`20260924T024907Z-p42428`) with seven compatibility captures. Its 60
selected title records from eight owners joined all 120 prepared fetch-0
executions, stable per packet, and five live SRVs. Each selected slot was
within the title's bound. The candidate key partition was one-to-one with
the five sampled guest BC3 ranges:

| Title key | Guest base / mips | Selected items | Live SRV |
| --- | --- | ---: | ---: |
| `0x4C78` | `0FD84000` / `0EFAE000` | 14 | 667 |
| `0x4C79` | `1075A000` / `0E4DA000` | 11 | 866 |
| `0x4C7B` | `0F358000` / `0ECBD000` | 12 | 585 |
| `0x4C7C` | `0F348000` / `0ECB0000` | 11 | 587 |
| `0x4C7D` | `0F368000` / `0ECCA000` | 12 | 589 |

The five same-run fenced nine-mip chains also match the independent
RenderDoc chains byte for byte. `verify-snr02-vegetation-state-entry.py`
checks title record → owner-local key → prepared BC3 fetch → live SRV and
cache source for every selected item; `verify-snr04-bc3-source-join.py`
checks the mip bytes. The filtered log is
`.local/native-renderer/snr02/foliage-owner-candidate-b/evidence.log`
(SHA-256 `6CFC577BD3908EF89101B99BA1CC1007E578085046DE6CC4906016F113187D3C`),
the state join is `state-join.json` (SHA-256
`3E77866476278BED57FC5C6805E84B6DAE3B49AEED4B1BFDFC2D1344AD836524`),
and the payload join is `bc3-source-join.json` (SHA-256
`4F980D4F79D51F0EB524139F53D7B868D86DA2B10CAE17F91E78F847B935F9E6`).
The RelWithDebInfo executable SHA-256 was
`C59DFEF7EC3F3AB0391E41A793D0FC4ABF0B3F83391E7DC2EED34E182BCDAB70`.

A third normal-exit run (`20260924T025739Z-p44980`) added the existing
`sub_82415AD0` resolver-return and vtable-bind boundaries to the bounded
trace. It completed seven compatibility captures. All 65 selected records
joined 135 prepared executions and the five same-frame BC3 sources. For 64
selected records, the resolver returned a nonzero object and the following
bind call received the **same object** in slot 0. Each key resolved to one
distinct title object in this run:

| Title key | Resolved and bound title object |
| --- | --- |
| `0x4C78` | `0xAAEC4BC0` |
| `0x4C79` | `0xAAEC4C20` |
| `0x4C7B` | `0xAAEC4CE0` |
| `0x4C7C` | `0xAAEC4D40` |
| `0x4C7D` | `0xAAEC4DA0` |

One selected record did not take the resolver/bind path; the generated
five-slot key cache can skip it when its key is already current. The verifier
requires exact record/key/object agreement for all 64 observed resolutions,
five distinct objects and a complete five-key prepared-fetch/SRV join for
all 65 selected records. The five fenced nine-mip chains again match the
independent RenderDoc payloads. The filtered log is
`.local/native-renderer/snr02/foliage-resolved-object-c/evidence.log`
(SHA-256 `86AC69C0AE45CC3247F4AB412F1B0DD4529D558F3C0E737DC0305DDA68A5E4CD`),
its `state-join.json` has SHA-256
`51A930246D48CB6E36401D8140E1100DD020F976C6CF8668442876D78146B612`,
and its `bc3-source-join.json` has SHA-256
`DA4CC1792F4B5881D7C24D2D4FD723A0847829F9882471E0296C1E5CAC1856F4`.
The executable SHA-256 was
`1DB22A17FEEE66AA03CB539CDAE46D02828EA8A60F2CA68C8B5024AD054119F0`.
A probe-off replay of that build (`20260924T030139Z-p240`) exited normally
at frame 6920 with all seven compatibility captures; its process session
SHA-256 was
`1DEEF31FA6CD2E810851E2A51D085BB91CB43266590B71C8DDEE95E61E956B7F`.

Reproduce the process-filtered log with `extract-snr01-run-log.py SESSION
OUTPUT --include-scene --include-bc3-source`, then run
`verify-snr02-vegetation-state-entry.py LOG OUTPUT --frame 5000` and
`verify-snr04-bc3-source-join.py LOG LIVE_DIR REFERENCE_DIR OUTPUT --frame
5001`. The hooks are diagnostic-only and default off. The title key and
resolved object identify the bounded foliage texture resource in these
runs, but neither pointer nor key yet proves allocation or payload
generation. The next trace must follow resource creation, upload and unload,
including guest-address reuse and streaming mutation.

### Foliage title manager lookup

The generated `sub_824139B8` path loads the resolver context from its stack
slot at `r1+412` and passes it to `sub_82415BF8`. On a cache miss,
`sub_82415AD0` passes that context to `sub_82410A58`, which indexes the
manager table at `context+2812` by the title key. An initial exploratory
probe incorrectly treated the static resolver cache as this context and
faulted; its capture was discarded. The corrected hook reads the stack slot
only for the opt-in frame-5000 vegetation state entry.

The corrected sustained-race replay (`20260924T032556Z-p44176`) exited
normally with all seven route captures. It selected 52 vegetation records,
emitted 112 prepared executions and resolved/bound 51 records; one selected
record skipped the resolver through the title's current-key cache. All five
keys map one-to-one through the manager table to five distinct manager
objects, then to five distinct returned resource records. The manager
objects share one vtable; each returned record is at manager object +44.
The record's first four words were `3`, `1`, a value varying within the capture,
and `0`; the first word is **not** a vtable. Five live BC3 source chains
again matched the independent RenderDoc nine-mip references byte for byte.

The process-filtered log is
`.local/native-renderer/snr02/foliage-manager-lookup-g/evidence.log`
(SHA-256 `656DD02D033BEBC538EDA2139C5BC949E094B3E1474ED8C5176389213620900D`),
the checked `state-join.json` has SHA-256
`6A840B09E0CF1189E7FB1139BCAB815E3F2CE95DD5B305759ACB50C77A386012`,
and the checked `bc3-source-join.json` has SHA-256
`B554F8275F91DEB86D32DB3977B38A059F2736B74109C2EA4391791186A82DDA`.
The executable SHA-256 was
`4AD497CE384CB20198BE013A8CDAF16800FA038B4B4F46E8ED0D8A62240C2127`.
The updated state verifier also passed the earlier 65-record capture.
A probe-off replay of this build (`20260924T033052Z-p42520`) exited normally
with all seven compatibility captures; its process-session SHA-256 was
`BD262FDFD6610FF244472381499E22225818EFB3FA87645E399E372CA286387E`.
This proves the title lookup and sampled resource identity, but does not
yet establish allocation generation, payload mutation or unload/reload
lifetime. SNR-02 remains open.
