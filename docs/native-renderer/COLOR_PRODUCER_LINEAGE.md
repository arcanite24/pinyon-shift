# Live color-producer lineage

Status: predicated color tile and exact padded full-frame resolve assembly
proved; runtime workset tracker, row planner, and private D3D12 accumulator
backend implemented

## Why this is the next ingress

The complete unified track-presentation inventory closes the only live exact
slots in the representative festival as depth-only shadow work. The broader
command-buffer lineage already resolves title packet construction through
constructor, owner, producer, and context functions, including exact
`proceduralGeometry::CProceduralModels` receiver lifetime and preparation
identity at context `82417BC0`.

The clean `20260901T065854Z-p37928` AppData session closes that cross-session
gap. It records 688 opaque, bounded color-plus-depth draws under the exact
`CProceduralModels` receiver lineage. The first exact prepared signature is
`751139AF66FBCCF4`, with vertex shader `D3EE3BD1E086935B` and pixel shader
`CE7C54664D18A4E3`; the same session's candidate census independently records
that exact mechanically eligible signature.

That is an exact semantic + mechanical color-ingress join, but not yet a
main-view assembly join. Its sampled scissor is `00000000:01000500`, or
1280x256. The same session contains no 1280x720 draw scissor at all, while the
title has proved bin-mask/select wrappers and a tiled 1280x720 presentation
resource. The 1280x256 region may therefore be one predicated EDRAM tile of the
main view, rather than an offscreen pass. Replaying it as a complete frame is
still invalid and explains the earlier wrong-view prototype symptom.

## Bounded target-shape census

Every existing command-lineage aggregate now partitions its prepared draws
into exact attachment shapes:

- depth only;
- first color only;
- first color plus depth; and
- any other target shape.

Color activity is further counted as opaque, bounded, or sampling a resolved
input. The first color sample retains only prepared signature, shader hashes,
attachment formats, pipeline flags, target registers, and scissor state. A
variation bit records whether later color draws differ from that sample. No
guest payload, shader bytecode, texture data, or camera data is exported, and
the existing 4,096-entry lineage capacity is unchanged.

`tools/summarize-native-renderer-color-producer-lineage.py` requires one armed
target-shape config, one final lineage summary, a clean shutdown, zero lineage
faults or overflow, complete per-entry target accounting, and exact samples for
every color-bearing aggregate. It ranks exact semantic receivers first, then
opaque, bounded, and total color activity. Ranking is investigation evidence;
it cannot enable native admission or suppression.

The follow-up exact target-role profiler partitions every color draw under the
live `82417BC0` semantic receiver by prepared signature, shaders, attachments,
viewport, scissor, target registers, and exact backend bin-select/mask state.
It emits decoded scissor extents and separates monolithic 1280x720 profiles,
predicated 1280-wide EDRAM tiles, unpredicated reduced targets, and other
targets. Receiver addresses are samples only; a variation bit proves when a
target profile spans multiple live receiver instances. The bounded table has
1,024 entries and fails closed on overflow or incomplete accounting.

The clean AppData-backed festival session `20260901T073926Z-p40856` completes
that target-role checkpoint. All 382 exact procedural color draws are bounded,
opaque, predicated, and use the same 1280x256 scissor, target state
`14020500:00030000:00000000:00000000:00000000:00010400`, and bin intersection
`0000000080000003`. There is no monolithic 1280x720 profile. The same final
resolve census exposes three contiguous source-zero ranges on surface
`14020500`, with byte lengths `1310720`, `1310720`, and `1146880`. Their
destination pitch declares 1280x720, format 7 is four bytes per pixel, and the
combined storage is 1280x736: the logical 720 rows plus 16 rows of alignment.
This is strong resolve-topology evidence that the 1280x256 draw extent is one
piece of the padded full-frame assembly, not an independently publishable
camera view.

The resolve census now exports the exact selected source index, selected
source target state, and all bound source targets. The offline
`summarize-native-renderer-procedural-resolve-assembly.py` join requires that
source state to match the procedural target, requires the resolves to fall in
the procedural profile frame window, and proves address contiguity, copy
format, bytes per pixel, logical extent, and bounded row padding.

The follow-up clean AppData session `20260901T080735Z-p36580` removes the last
inference from that gate. The exact selected source state is
`14020500:00030000`, matching the procedural target, and the qualifier proves
the contiguous ranges `1C4E1000`, `1C621000`, and `1C761000` with lengths
`1310720`, `1310720`, and `1146880`. Destination state
`003E0382:02D00500` decodes to four-byte pixels, logical 1280x720, padded
1280x736, and exactly 16 alignment rows. The session exited normally with
complete target and assembly accounting.

The same fail-closed join now exists as a small runtime workset tracker. It
retains at most 64 copies per frame, matches only the exact source target,
requires one destination state and address-contiguous chunks, decodes format
and pitch, and exposes an exact result only for the complete logical frame with
bounded padding. It retains the latest qualified workset while capping detailed
events at 64 and reporting any omitted details in its final summary. Its events
are diagnostic only and are deliberately batched into the next substantial
AppData validation.

The next implementation checkpoint converts each qualified copy into an exact
backend-neutral private-accumulator operation. The plan begins at row 0,
appends only same-state address-contiguous chunks, and commits only after more
than one chunk covers all 720 logical rows with fewer than 64 padding rows. For
the proved workset its row operations are `0+256`, `256+256`, and `512+224`;
the final operation exposes 208 logical rows and preserves the trailing 16
storage rows. Frame advance, target conflict, destination mismatch, malformed
row geometry, or chunk overflow cancels the plan and poisons the remainder of
that frame.

The D3D12 backend now implements the corresponding private padded-frame
resource contract. It accepts operations only after the authoritative Xenos
resolve succeeds, requires contiguous rows and one exact 1280x736 resource,
resolves multisampled private tiles before copying, and re-seeds the private
replay target from authoritative guest EDRAM between component tiles. Only an
exact committed frame may enter the existing swap-time preview; an incomplete,
conflicting, malformed, or allocation-failed frame remains unavailable so the
guest output falls back to Xenos. The title-side planner is now registered only
when the default-off
`pinyon_shift_native_renderer_procedural_frame_accumulator` switch is enabled.
It forwards the exact 1280x720 logical / 1280x736 storage contract after each
successful Xenos resolve and records bounded backend outcomes. Disabled runs
retain the passive planning census; enabled runs let the callback consume each
transition exactly once. Neither mode can publish guest memory or suppress a
draw.

`summarize-native-renderer-procedural-frame-accumulator.py` is the fail-closed
runtime gate for the combined slice. It requires one armed backend config, one
clean shutdown, complete result accounting, zero backend hard failures, and at
least one frame whose plan is exactly `0+256`, `256+256`, and `512+224` and
whose private results advance to rows 256, 512, and committed 736. It also
locks the 1280x720 logical / 1280x736 storage extents, private-resource scope,
completed-first Xenos resolve, zero guest-memory publication, and zero draw
suppression.

Run it after the combined AppData session closes:

```powershell
python tools/summarize-native-renderer-procedural-frame-accumulator.py `
  <session-jsonl> --session <session-id> `
  --output .local/qualification/native-renderer-procedural-frame-accumulator.json
```

Run the deferred qualifier after the next combined AppData capture:

```powershell
python tools/summarize-native-renderer-color-producer-lineage.py `
  <session-log.jsonl> `
  --session <session> `
  --output .local/qualification/native-renderer-color-producer-lineage.json
```

Then classify the exact target profiles from the same session:

```powershell
python tools/summarize-native-renderer-procedural-color-targets.py `
  <session-log.jsonl> `
  --session <session> `
  --output .local/qualification/native-renderer-procedural-color-targets.json
```

Finally, prove the exact resolve assembly:

```powershell
python tools/summarize-native-renderer-procedural-resolve-assembly.py `
  <session-log.jsonl> `
  --session <session> `
  --output .local/qualification/native-renderer-procedural-resolve-assembly.json
```

## Promotion gate

The exact contiguous 1280x720 logical resolve assembly is now proved. The next
C1 implementation may use the runtime tracker and accumulator plan as its
private capture gate only after their event contracts pass the next batched
validation. The private target must use the complete assembly dimensions and
preserve its 16 alignment rows; no 1280x256 component may be published alone.
Other reduced targets remain excluded. Xenos remains authoritative and this
checkpoint changes no rendering or control flow.
