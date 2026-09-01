# Live color-producer lineage

Status: live semantic color producer proved; exact target-role profiler
implemented for the next batched AppData run

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
main-view join. Its sampled scissor is `00000000:01000500`, or 1280x256, rather
than the preview's 1280x720 extent. It may be a reflection, horizon strip, or
other reduced target. It therefore remains ineligible for native publication.

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
viewport, scissor, and target registers. It emits decoded scissor extents and
separates exact 1280x720 profiles from reduced-width and other targets. Receiver
addresses are samples only; a variation bit proves when a target profile spans
multiple live receiver instances. The bounded table has 1,024 entries and
fails closed on overflow or incomplete accounting.

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

## Promotion gate

The next C1 implementation may privately capture one profile only when a clean
session proves complete target-profile accounting and an exact full-preview
1280x720 profile whose calls are all bounded and opaque and never sample a
resolved target. Reduced targets remain excluded even when mechanically
eligible. Until then, Xenos remains authoritative and this census changes no
rendering or control flow.
