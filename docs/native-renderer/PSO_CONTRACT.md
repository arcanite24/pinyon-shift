# Native PSO contract

NR-02D begins by describing the exact prepared host pipeline. This milestone
does not create a D3D12 pipeline, upload a resource, submit a native draw, or
suppress Xenos work.

## Prepared pipeline observation

ReXGlue patch `0057-d3d12-prepared-pipeline-observer.patch` extends the
existing synchronous prepared-draw callback after `ConfigurePipeline` has
succeeded. In addition to the exact translated shader identities, it reports:

- guest and host primitive types;
- host vertex-shader type and tessellation mode;
- processed index-buffer type, host index format, and primitive restart;
- normalized depth control and color mask;
- the five depth/color render-target format slots and their bound mask; and
- whether host render targets and rasterization are active.

The callback remains default-null and metadata-only. It does not expose a D3D12
object or command list. These fields participate in the candidate signature,
so a change in prepared pipeline shape produces a different candidate rather
than being merged into one aggregate.

The census emits a deterministic prepared-pipeline hash plus every raw field.
Raw values are retained because they are the authoritative cache-key inputs;
later native construction may decode them, but it must never silently ignore
an unknown value.

## Offline contract

`tools/build-native-pso-contract.py` joins one exact candidate selection with
its bounded geometry, decoded draw-state, and texture-provenance contracts:

```powershell
python .\tools\build-native-pso-contract.py `
  .\.local\native-renderer\candidate\selection.json `
  .\.local\native-renderer\candidate\geometry.json `
  .\.local\native-renderer\candidate\draw-state.json `
  .\.local\native-renderer\candidate\texture-provenance.json `
  --signature 0000000000000000 `
  --output .\.local\native-renderer\candidate\pso-contract.json
```

The builder requires matching signatures, false native-upload, native-draw,
and suppression gates, and Xenos authority in every input. The initial
supported shape is a direct
guest indexed draw with no primitive conversion, active tessellation, special
host vertex shader, host primitive restart, or unknown prepared-pipeline flag. It
requires bounded geometry, stable texture content, rasterization, and at least
one bound color output. Every unsupported condition is named explicitly.

ReXGlue defines the tessellation mode as meaningful only when the prepared
host vertex-shader type is not the ordinary `kVertex` path. The contract keeps
the residual register value in the exact key for diagnosis, but does not treat
it as active tessellation while `host_vertex_shader_type` is zero.

The resulting PSO key contains the exact shader specializations, prepared host
topology and index state, normalized depth/color state, target formats, and the
raw guest pipeline-state string. A SHA-256 digest makes the key deterministic
for later cache work.

`ready_for_pso_creation` means only that the metadata is complete and within
the initial supported shape. Visual identity and observed-producer exclusion
remain separate gates, and the contract fixes `native_pso_created`, upload,
draw, and suppression to false with Xenos authority true.

## Signature revision

Adding the prepared-pipeline hash intentionally revises NR-02 candidate
signatures. Pre-`0057` identities and their exact-signature payload scans remain
valid historical evidence, but cannot be reused as post-`0057` scan keys. A
new repeated capture must select the revised identity before PSO construction
or isolated comparison proceeds.

## Local qualification — 2026-08-28

Two consecutive `open_world_day` captures against the installed `0.1.0`
AppData save exited normally. The selector retained 36 recurring candidates.
The previously chosen shader pair (`E35520B6FDEA8C91`, `676B6C2D37982AD9`)
recurred in both sessions as revised signature `747837906D0BF484` with prepared
pipeline hash `464D06471DC459EA`.

| Session | Result |
| --- | --- |
| `20260828T081758Z-p38780` | normal exit |
| `20260828T082430Z-p41780` | normal exit |

The prepared shape was identical in both runs: host primitive 4, ordinary
host vertex shader, direct guest index buffer, host index format 1, primitive
restart disabled, depth/color target bits `00000003`, target formats
`00000001:00000003:00000000:00000000:00000000`, and prepared flags
`00000003`. The observed tessellation mode was the inactive residual value 1.
No native PSO, upload, draw, or Xenos suppression path was enabled.

A clean 57-patch Release build succeeded with executable SHA-256
`8C8556FE675CE6E3A93080A7A420A46A8571AC14B36887F7ED638275B849B6D4`.

## Joined contract qualification — 2026-08-28

Fresh exact-signature scans in sessions `20260828T084949Z-p36548` and
`20260828T085323Z-p43944` reproduced the bounded geometry and texture
contracts under revised signature `747837906D0BF484`. The joined PSO contract
is now `ready_for_pso_creation: true` and has deterministic key SHA-256
`A4E07C14394100E280810B52BDB72D93CAF348AC3A79AE70EDA6F933DDFC4E64`.

The two runs measured 30.560 and 31.032 median FPS over 6,682 and 4,893 frame
samples. Presentation cadence was 59.993 and 59.994 Hz, with zero deadline
misses. Both exited normally and emitted no error, crash, or device-loss event.

The joined result is permission to attempt isolated PSO creation only. Visual
identity remains unconfirmed and observed-producer exclusion is still
required. The contract therefore keeps native PSO creation, native upload,
native drawing, and suppression false, with Xenos authoritative.
