# Isolated native shadow-depth replay

This NR-05F checkpoint turns the first capture-proven shadow producer into one
native D3D12 replay without changing the game-visible render graph. The replay
writes a private depth/stencil target, the original Xenos draw always executes,
and no private result is published or used to suppress guest work.

## Exact admission contract

The runtime does not select a prepared-signature hash because streamed vertex
and index buffer addresses make that hash vary. Instead it requires the full
stable contract observed for the dominant 2048-square producer:

- vertex shader `4E1DA281CC3D7EDB`, no pixel shader, and zero specialization;
- indexed DMA triangle-list draw with 881 indices and three vertex bindings;
- no texture, query, memexport, overflow, or resolved-input dependency;
- Xenos surface/depth state `10000410` / `000002D0`;
- scissor `00000000:04000400`, zero color mask, depth state `00700736`,
  raster state `00219800`, and vertex state `00000004`;
- exactly one D24S8 depth attachment and no color attachment; and
- a fully prepared host pipeline with rasterization enabled.

Any mismatch yields without requesting native work. It does not fall through
to a broader shader-only or depth-only heuristic.

## Private backend path

ReXGlue's isolated replay request now has an explicit depth-only mode. In that
mode the D3D12 target cache rejects any bound guest color target, clones and
seeds only the current depth/stencil resource plane-by-plane, binds only the
private depth target, records the duplicate draw, and restores the prepared
guest state before the authoritative draw. The one-shot native and Xenos depth
readbacks remain local diagnostics.

The completion gate accepts the evidence as the intended checkpoint only when
the private replay records successfully after the exact 2048 by 2048 logical
draw contract above has matched. The logical dimensions come from the captured
zero-origin `04000400` scissor after the configured 2x draw-resolution scale.
ReXGlue's host depth resource is an EDRAM allocation rather than a tightly
cropped shadow texture, so its diagnostic allocation dimensions are larger
(`2080x5056` in the qualifying run). The result records both logical and
allocation dimensions and never treats the padded allocation as the logical
shadow-map extent.

## Qualification

Launch the installed AppData preview with a new local artifact directory:

```powershell
.\tools\capture-native-renderer-census.ps1 `
  -StateRoot "$env:LOCALAPPDATA\PinyonShift\source\0.1.0\.local\preview" `
  -Scene open_world_day `
  -ShadowDepthIsolated `
  -IsolatedDrawDir .local\qualification\nr05f-shadow-depth-isolated
```

Required evidence is one
`native_renderer.shadow_depth_isolated.result` with
`status=recorded_exact_target`, native and Xenos depth artifacts, and a summary
with one private replay. Every event must retain `native_publication=false`,
`xenos_draw=preserved`, `output_authority=xenos`, and
`suppression_eligible=false`.

The first live qualification recorded the exact draw at frame 8731 / draw 3059
with a `2080x5056` D24S8 allocation. Native and Xenos depth/stencil readbacks
were byte-identical (56,950,304 bytes, hash `02FE4C1D52BD6FC8`), while the
game-visible output remained on Xenos.

This checkpoint is not a native shadow atlas. Atlas ownership, tile/cascade
semantics, multi-draw accumulation, consumer binding, reflections,
publication, and suppression remain closed.
