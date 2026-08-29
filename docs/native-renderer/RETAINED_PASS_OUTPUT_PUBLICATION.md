# Retained-pass output publication

NR-04D cannot suppress the retained sky/horizon pass while its resolved output
feeds 38 observed Xenos shader families. Replacing those consumers individually
is not the only safe boundary: the native replay can publish its complete color
and depth/stencil result into the same authoritative Xenos render-target
resources, allowing the original resolves and downstream consumers to continue
unchanged.

This milestone implements that publication boundary without suppressing any
guest work. It is diagnostic, startup-only, default-off, and fail-closed.

## Ordering contract

For each exact adjacent anchor/follower occurrence, ReXGlue records work in this
order:

1. seed the private color and depth/stencil targets from the current guest
   targets;
2. replay the anchor and follower into the private targets;
3. restore the guest target bindings;
4. execute both original Xenos draws;
5. queue any requested authoritative parity readbacks;
6. validate the complete private/guest target pair;
7. copy private depth/stencil and color into the guest resources; and
8. continue with the original Xenos resolves, consumers, queries, events,
   fences, and memexport behavior.

Publication never occurs before the original follower. Therefore a failure or
identity mismatch leaves a complete Xenos result in place. The backend validates
both targets before transitioning or copying either resource, preventing a
partial color-only or depth-only publication.

## Exact validation

Publication requires all of the following:

- the host-render-target D3D12 path;
- retained private color and depth/stencil targets from the current exact pass;
- exactly one bound guest color target plus one depth/stencil target;
- identical private and guest render-target keys; and
- matching D3D12 dimensions, array size, mip count, format, sample count, and
  sample quality for both attachments.

Any failed condition returns `unsupported_path`, `unavailable`, or
`target_mismatch`. No copy is recorded, Xenos remains authoritative, and the
runtime diagnostic reports the fallback.

## Qualification launch

Use the AppData save and exact retained-pass signatures:

```powershell
$stateRoot = Join-Path $env:LOCALAPPDATA `
  'PinyonShift\source\0.1.0\.local\preview'
.\tools\capture-native-renderer-census.ps1 `
  -StateRoot $stateRoot `
  -Scene open_world_day `
  -IsolatedDrawSignature '1D253A52B55C9FB3' `
  -PassAnchorSignature '747837906D0BF484' `
  -PublishRetainedPass
```

`PINYON_SHIFT_NATIVE_RENDERER_PUBLISH_RETAINED_PASS=true` is scoped to that
helper invocation and restored afterward. It is rejected unless both exact
pass signatures are configured.

Runtime evidence uses:

- `native_renderer.retained_pass.publication_config`;
- up to 64 `native_renderer.retained_pass.publication` detail events; and
- `native_renderer.retained_pass.publication_summary` at shutdown.

Each detail event names the resulting `guest_target_content` explicitly:
`native_retained_pass` only when both attachments were copied, otherwise
`xenos`. This prevents a failed or partial attempt from being interpreted as
native output authority.

Validate a completed session with:

```powershell
python .\tools\summarize-native-renderer-pass-publication.py `
  "$stateRoot\logs\<session>.jsonl" `
  --output '.local\qualification\retained-pass-publication.json' `
  --require-complete
```

The schema-v1 report rejects signature drift, unsafe suppression fields,
incomplete attachment pairs, and inconsistent bounded-detail or
attempt/success/failure counts.
It always records `suppression_allowed=false` and leaves the downstream-consumer
gate at `qualification_required`.

A qualifying run must report only `published` attempts, both attachments
published, no target mismatch or device-loss event, normal exit, and normal
downstream consumer activity. RenderDoc captures can use the same switch and
must contain `PinyonShift NR-04D native retained-pass publication` after the
authoritative follower marker.

## Open-world-day qualification

The AppData-backed `open_world_day` session
`20260829T082307Z-p39652` qualified the bridge on the 78-patch build:

- 12,018 of 12,018 retained-pass attempts published both color and
  depth/stencil, with zero fallback or target-mismatch results;
- all four downstream-consumer corpus samples completed while the original
  Xenos consumer draws remained enabled, and one sample produced a real
  depth/stencil delta;
- gameplay reached the festival save with visually intact sky, world geometry,
  lighting, crowds, vehicle, and HUD;
- presentation held 59.971 Hz with zero deadline misses, while the measured
  simulation median was 30.491 FPS; and
- the process exited normally with no error-level, fatal, device-loss, or
  device-removed diagnostic.

This is scene-bounded publication evidence. It does not yet promote the
`later_gpu_consumers` gate or authorize suppression.

## Suppression boundary

This bridge does not enable suppression and does not by itself pass the
`later_gpu_consumers` admission gate. Qualification must first prove that the
published native target reaches the original resolves and downstream consumers
with parity across required scenes. Only a later independent, default-off PR
may consider skipping the exact anchor/follower draw pair. Xenos fallback and
all guest side effects remain mandatory.
