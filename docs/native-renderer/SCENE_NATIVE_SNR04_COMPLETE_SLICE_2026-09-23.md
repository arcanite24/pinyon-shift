# SNR-04 complete selected-slice diagnostic — 2026-09-23

The source-frame-5000/output-frame-5001 capture owns all 2,192 selected draws
in six independently verified fixtures. The complete-slice verifier joins
each selected packet to its final backend sequence and rejects missing or
duplicate ownership. It produces a global draw-order manifest.

The offline diagnostic replays that order in 35 contiguous family runs. Each
run reads the previous run's private 1280×720 RGBA and float-depth targets,
draws its assigned range, and writes the targets for the next run. IDs 1–2,192
identify draws in global order. Thus the output has one **logically carried**
color/depth state, with native depth testing across family boundaries. It is
not one uninterrupted GPU target: each boundary has a readback and upload.
The separate family rasters remain useful controls, not additive pixel counts.

Two complete replays and a third after the CLI cleanup produced the same
final result: 659,995 covered pixels, 216 visible draw IDs, zero covered
pixels at depth zero, and byte-identical final color, identity and depth.
All 105 per-run identity/color/depth files also matched between the first
two replays. Each family's one-run and split-run outputs were byte-identical,
which checks the target handoff without requiring cross-family visual parity.

| Output | SHA-256 |
| --- | --- |
| Draw-order manifest | `A747AF07535C4C12FE3D73C5869C5FF744D2AC46DAAD68C8A45EE9E3598BF0D7` |
| Final identity | `0005BBAEF0C33C745212F02C889CD5AF944AEC839978FC88D17611D657A76953` |
| Final RGBA | `5B50546D13B5103662A7E2933378F4E4F3B95360EC5C18C2BA0A29485A700084` |
| Final float depth | `2915BF3282D9B6DC1D612E7E707AA10F0C275D25E9984996F8C8967DBB419904` |

Reproduce from the local capture and validated shader translations:

```powershell
$base = '.local/native-renderer/snr04'
$dxil = '.local/native-renderer/seeded-probe/translation/dxil'
python tools/verify-snr04-complete-slice.py "$base/remainder-index-live-b" "$base/remainder-index-live-b-evidence.log" "$base/remainder-index-live-b-ledger.json" "$base/complete-slice-order-b.json"
python tools/replay-snr04-complete-slice.py "$base/complete-slice-order-b.json" "$base/remainder-index-live-b" "out/build/win-amd64-relwithdebinfo/pinyon_shift_snr04_owned_scene_diagnostic.exe" "$base/remainder-index-shaders-b" "$base/complete-slice-track-shaders-b" "$dxil" "$dxil/vertex_5834939992FFC765_000000000000001F.dxil" "$base/complete-slice-staged-c"
```

This proves ordered geometric coverage and shared private depth for the
selected frame only. The diagnostic still uses identity shading, omits
material alpha and stencil, and uses one sample. It neither compares final
coverage/depth to same-frame compatibility output nor proves resource
generation, unload/reload, moving-frame stability or production performance.
Those are the remaining SNR-02/03/04 Gate A checks before native admission.

## Adjacent moving-view sample

A second AppData-backed run used the same race route with one extra
`capture 5001 track-source-5001` line. It kept compatibility rendering as
default and exited normally with nine screenshots. The source-frame-5000 and
5001 screenshots from **that run** differ in 76.1% of their RGB bytes (mean
absolute byte difference 7.42). The 5001 source scene was consumed at output
frame 5002. Its strict census attributed all 4,682 backend draws, with zero
unknown owners; the unchanged pilot rule selected 2,442 draws and retained
61. All six same-frame fixture verifiers passed:

| Fixture family | Selected draws |
| --- | ---: |
| Shared track | 777 |
| Procedural items | 121 |
| Vegetation | 120 |
| Procedural characters | 10 |
| Character manager | 363 |
| Car scene-list, animated and presentation remainder | 1,051 |

Exact vertex translations were extracted from the same validated shader
pack: 20 track and 69 remainder shader pairs. The global-order replay carried
private color/depth through **36** contiguous family runs and all 2,442
selected draws. It yielded 630,961 covered pixels, 219 visible draw IDs and
no covered pixels at depth zero. Two runs produced byte-identical final
outputs and all 108 intermediate identity/color/depth files.

| Adjacent-frame evidence | SHA-256 |
| --- | --- |
| Filtered runtime log | `B56978230819F9179057E2469114681299286D7DB47EA5D857E07CE163742305` |
| Strict ledger / draw-order manifest | `07D5D63CB1133625A8C33E84BE787175584DF54A0B79E019130C553CB07F6036` / `535F339F2A03C0F37EBB9EF6DD6DAA65A68C046DB8C4837823F89775ECC69475` |
| Final identity / RGBA / depth | `78EFBE5F63217956FF393216D932D5BF24FA74FCDA16380A415A1E845F391F02` / `E5558E95E096F560C9A2851E32DD2037DF91A8D8E9A9D64CAE703C95BC0B9E72` / `2FA2C927E90E633C6432C205464C46B51EB49CBD4D5C2A6C58C3D7CB50569076` |

The optional scene-aware log extraction is reproducible with
`extract-snr01-run-log.py SESSION OUTPUT --include-scene`; the existing
`verify-snr04-complete-slice.py` then validates the six fixtures and writes
the ordered manifest. `replay-snr04-complete-slice.py` accepts that manifest,
the adjacent fixtures, the diagnostic executable and the extracted shaders.
Both `track-source-5001.ppm` and the owned fixtures are in
`.local/native-renderer/snr04/complete-slice-adjacent-live-a`.

The raw identity image appears turned 180° relative to the paired **presented**
screenshot. That comparison crosses the scene-target/presentation boundary;
the RenderDoc check below shows why it must not be counted as a raster
orientation failure. Neither this sample nor frame 5000 qualifies pixel/depth
parity. These are two independently captured source frames, not a continuous
owned scene stream or an unload/reload test.

### Compatibility target-space orientation

A separate race run captured RenderDoc frame 5001. Selected-scene vertex
translations were matched by bytecode hash to the recorded draw actions.
Representative actions bind the same `ResourceId::2504` color attachment,
`R16G16B16A16_FLOAT`, **1280×512**. Its viewports/scissors reuse the target
in three bands: 720-row viewport with 256-row scissor, 464/256 and 208/208.
The live pipeline viewports at events 9991, 14587 and 17209 have heights
720, 464 and 208 respectively. In the exported attachment at event 9991,
the player car is inverted at the **top** of the first tile. That orientation
agrees with the private target's raw image; the presented screenshot has
passed through later resolve/presentation work. Rotating either image for
display is not a geometry fix.

| RenderDoc evidence | SHA-256 |
| --- | --- |
| `renderdoc-frame5001_frame5001.rdc` | `2C8C0267FDD1508749DFF5E7ED0E09BD73133B4A580EB9773A8057EA181A93F2` |
| Event-state report | `25F9003A5748492FAA53DF87A46ABCCE2E946327C2E1AFB21B47F9B25398036F` |
| Event 9991 color attachment | `86F73FB6F4BD0E9AB8EEF0552A7F8A281B179830430DDA1F1C5530FE92F6E7C2` |

Re-export the target states with the checked RenderDoc helper:

```powershell
$env:SNR04_CAPTURE = (Resolve-Path .local/native-renderer/snr04/renderdoc-frame5001_frame5001.rdc).Path
$env:SNR04_OUTPUT = (Join-Path (Get-Location) '.local/native-renderer/snr04/orientation-events-5001.json')
$env:SNR04_EVENTS = '8242,9129,9991,11849,14587,17209,18849,18867'
& .local/tools/renderdoc-1.46/RenderDoc_1.46_64/qrenderdoc.exe --python tools/probe-snr04-renderdoc-target.py
```

This capture was made in a separate run from the complete-slice fixture. It
establishes the compatibility target's coordinate convention and tile reuse,
but it does not join each private draw to the captured attachment or compare
same-run depth/coverage. That remains the SNR-04 parity check.

### Same-run target-space depth diagnostic

An extended AppData-backed race route captured source frame 5001, its six
owned fixtures, the strict runtime census and RenderDoc output frame 5002 in
one normal-exit run. The census attributed all 2,691 backend draws. The
unchanged Gate A partition selected 1,562 draws, retained 61 and placed
1,068 outside. Every selected draw joined an immutable fixture and a final
backend sequence: 668 track, 281 procedural item, 179 vegetation, 17
procedural character, 93 character manager and 324 remainder draws. The
private 1280×720 replay carried identity/color/depth through 35 family runs.
Two complete replays produced identical final files: 904,330 covered pixels,
139 visible draw IDs and no covered pixels at depth zero.

The compatibility scene bound a 1280×512 `R16G16B16A16_FLOAT` color target
and `D32S8_TYPELESS` depth target, both **4× MSAA**. The same resources were
reused with viewport heights 720/464/208 and scissors 256/256/208. The
private complete-slice replay remains **1×**, lacks faithful alpha, stencil
and material behavior, and cannot be judged by final color or exact
per-sample coverage. The checked probe exports the exact sample-0 depth bytes
at selected target-space events. `check-snr04-depth-bands.py` maps the three
scissored tiles to private rows 0/256/512 and reports nonzero-depth overlap.

| Same-run evidence | SHA-256 |
| --- | --- |
| RenderDoc capture | `277C2A371A86038901D845332704574B708F632EAB6F427175827BF93660E955` |
| Strict ledger / draw-order manifest | `FF54BB219D79446A79DBBADA709EA836504B909664A82F4FE5D82CA63446F863` / `28AB880B18EB06AF99A4B479A7DDE50B08AFE3F59DE3347DA9D63632DF72E708` |
| Tile-final event/depth export report | `50904ADB04D01684B8FD25D139AADB3C3568FB75E39B1AE22D680A89A57020B2` |
| Final private identity / color / depth | `E60746286D801482093109768BEBE1983EA674884E3FFCBD17D9F1B7BEADD4E0` / `B6846068D08E6AE323E3A13079DA9F956FB47D661F777D81C9EBB7363ABEF24C` / `4AF265F13E53FDA6BCDF53F5269C9B6F11728AD2DD876F65F4F0F40A485CD15B` |

To repeat the bounded comparison from those local artifacts, set
`SNR04_CAPTURE` to `renderdoc-gatea-full-b_frame5001.rdc`, `SNR04_OUTPUT` to
`renderdoc-gatea-full-b-tile-final.json`, `SNR04_EVENTS` to
`11810,15324,19337` and `SNR04_DEPTH_SAMPLE=0`; run
`qrenderdoc.exe --python tools/probe-snr04-renderdoc-target.py`. Then run:

```powershell
python tools/check-snr04-depth-bands.py .local/native-renderer/snr04/renderdoc-gatea-full-b-tile-final.json .local/native-renderer/snr04/renderdoc-gatea-full-staged-b/step-34/depth.f32
```

Add `--order .local/native-renderer/snr04/renderdoc-gatea-full-b-order.json`
and `--band-colors` followed by the `color.rgba` files from steps 12, 23
and 34, in that order, to attribute pixels to the draw ID at each tile's
end. Using only the final color file misattributes equal-depth redraws in
the first two bands to later tile variants. Their depth bytes do not change
between those tile ends and the final output.

A full action scan identified the final scene-target draw in each band:
events 11810, 15324 and 19337. These are later than the final matched
track shaders at 11779, 15287 and 19300, but their sample-0 depth bytes are
identical. Using nonzero depth as the covered-pixel mask, the tile-final
reference has 902,659 covered pixels and the private replay has 904,330;
901,054 overlap, for **99.46% intersection-over-union**. The first two bands
are fully covered on both sides, so their 100% mask overlap is not a strong
silhouette test. The 208-row band has 98.05% mask overlap. Across overlapping
pixels, median absolute depth difference is `8.32e-5`, but p90 is
`0.00489`; only 466,537 of 901,054 differ by less than `1e-4`.

Of the 85,908 overlapping pixels with absolute depth difference at least
`0.005`, **69,490 (80.9%)** have a vegetation ID at the corresponding tile
end. At 68,823 of those pixels (99.0%), the private reversed-Z depth is
nearer than compatibility sample 0. Car presentation accounts for 10,947
large errors, shared track for 3,467 and other families for 2,004. The five
leading vegetation IDs (290, 824, 285, 280, 819) account for 65,130 large
errors. Their ordered RenderDoc events (11204, 14636, 11188, 11172, 14620)
each bind two pixel textures and use the same translated foliage pixel shader
(`9954AD19FD4584CDF277F954E87005438DAA263094ACA722CF56F49930341D58`).
For all five, RenderDoc's bound vertex-system registers 0/1, 8/9 and 14/15
match the exact same-frame `FH1 SNR03 final draw state` row for that packet
and sequence. This verifies the leading event-to-owned-draw joins beyond an
ordinal count match.

The private vegetation path instead uses an unmasked identity pixel shader.
This points first to foliage alpha/sample-mask behavior, but 1× versus 4×
sampling, later depth ties and retained scene contributions still prevent a
causal parity claim.

The exact-shader RenderDoc scan found **179 foliage actions**, matching the
179 owned vegetation draws and their 45/67/67 tile partition. It counted 126
actions with no pixel SRVs and 53 with two. The latter reference five BC3
resources; all five full nine-mip chains were exported from this same run and
match the independent earlier capture byte for byte. The census report is
`renderdoc-gatea-full-b-vegetation-pixels.json` (SHA-256
`78EAC8AF4D37E0097AE58421C6902D810BECBC40303E42BCBFFDE750A2AE2E157`).
Reproduce the exact-shader event list with
`qrenderdoc.exe --python tools/probe-snr04-vegetation-actions.py`, setting
`SNR04_CAPTURE` to the same RDC and `SNR04_OUTPUT` to
`renderdoc-gatea-full-b-vegetation-actions.json`. Feed that file as
`SNR04_EVENTS_JSON` to `tools/probe-snr04-vegetation-pixel-census.py`, with
`SNR04_BC3_DIR` set to a local output directory. The five `.bc3mips` files
are 87,408 bytes each.

At event 11204 (tile-one draw ID 290), RenderDoc records 133,488 changed
depth samples across 59,649 pixels; sample 0 changes 27,325 texels. The
stage-local private ID overlaps 15,608 of those texels. This is a same-run
per-draw coordinate check, not alpha/depth parity.

The depth comparison is a **coordinate diagnostic**, not SNR-04 acceptance.
It samples only one of four compatibility samples and compares an
identity-shaded selected-only replay with a compatibility target that also
contains retained work. The next bounded check should replay the captured
vegetation BC3 alpha/sample-mask path against preceding scene depth at 4×,
then extend 4× target handoff to the complete ordered slice and compare
matched per-draw events. Stencil and the remaining material states must also
match before parity. Resource generation, continuous moving frames,
unload/reload and production cost are also still open.

### Four-sample vegetation segment handoff

The private diagnostic now accepts `--msaa4 --segment` for an `SNR03F3`
vegetation fixture. A later segment reads the preceding segment's
`identity.u16x4` and `depth.f32x4`, validates the sample count, dimensions,
finite depth and prior ID range, and restores every sample through a private
full-screen D3D12 pass before drawing its own sequence range. The four-sample
standalone mode and all one-sample family segments retain their earlier paths.

The source-5001 same-run fixture has 179 vegetation draws in the same
45/67/67 tile groups as RenderDoc. One 179-draw four-sample segment and a
three-segment replay with those groups produced byte-identical `coverage.u8`,
`identity.u16x4`, `depth.f32x4`, `identity.ppm` and `depth.f32`. The first
segment has 16,959 pixels with differing sample IDs, so this comparison
exercises genuinely distinct per-sample state. The final result covers
431,722 sample-0 pixels. `tools/verify-snr04-msaa-segments.py` checks the
sequence/ID chain and the exact output bytes; the existing
`tools/verify-snr04-msaa.py` now also checks per-sample masks, IDs, depths and
sample-0 files for each segment:

```powershell
python tools/verify-snr04-msaa-segments.py `
  .local/native-renderer/snr04/vegetation-msaa4-segment-single `
  .local/native-renderer/snr04/vegetation-msaa4-segment-first `
  .local/native-renderer/snr04/vegetation-msaa4-segment-middle `
  .local/native-renderer/snr04/vegetation-msaa4-segment-last
```

The final four-sample identity/depth SHA-256 values are
`82740196DD9E22D000A3E6DA6C96D63F6CA4E631C58D6161651921285F8FC00F`
and `D3BDAC0879FA8D83C70997CCD6F32D7345A3BE6448CF73E7BC81CE9D4B60C84D`.
A prior output with IDs from a later segment is rejected. Replaying the
complete 1× selected slice with the rebuilt executable retained its known
identity/color/depth hashes, and the earlier standalone 4× fixture retained
its known coverage hash `BD31714FB1BF59DBF173397BB51D4C3D3164E0C79F5C30138A4E1C64002E5BC5`.

This proves per-sample target state can survive a private process boundary
for vegetation. Preceding compatibility depth and the captured foliage
alpha/sample mask remain necessary for SNR-04 parity.

### Four-sample complete selected-slice replay

The source-5001 same-run fixture now replays all 1,562 selected draws in
35 ordered family stages with a carried 4× private identity/depth target.
The track, procedural, manager and remainder diagnostics use the same
per-sample handoff format as vegetation. The replay driver selects it with
`--msaa4`; the default 1× path retains its existing output and hashes.

Two full 4× replays produced byte-identical coverage, identity and depth
files at **all 35 stage boundaries**. A 668-draw track replay and a 281-draw
procedural-item replay each also matched their two-part split replay byte
for byte. `tools/verify-snr04-msaa.py` validates the final stage's masks,
IDs, depth and sample-0 projections. The final output has 904,375 covered
sample-0 pixels, 905,192 pixels with any covered sample, 3,617,256 covered
samples and 140 visible sample-0 draw IDs.

| Final 4× output | SHA-256 |
| --- | --- |
| Coverage mask | `26327663E4489F8D4A8A67954261DCAA34632D1B2A24BFB28A4AACE2BA3FB5D0` |
| Per-sample identity | `685A356C5601B23BF0438E633CCB3F852B05DAA83E7C2019750ECB762A3CA0F8` |
| Per-sample depth | `27E4EE345B6D12F8C04ACA37CFE7AA9F2EFE609E156250FD26CE48D09DD3EAFA` |

Reproduce using the source-5001 fixtures and verified shader translations:

```powershell
$base = '.local/native-renderer/snr04'
$dxil = '.local/native-renderer/seeded-probe/translation/dxil'
python tools/replay-snr04-complete-slice.py --msaa4 `
  "$base/renderdoc-gatea-full-b-order.json" `
  "$base/renderdoc-gatea-full-live-b" `
  'out/build/win-amd64-relwithdebinfo/pinyon_shift_snr04_owned_scene_diagnostic.exe' `
  "$base/renderdoc-gatea-full-remainder-shaders-b" `
  "$base/renderdoc-gatea-full-track-shaders-b" `
  "$dxil" `
  "$dxil/vertex_5834939992FFC765_000000000000001F.dxil" `
  "$base/renderdoc-gatea-full-msaa4-a"
python tools/verify-snr04-msaa.py "$base/renderdoc-gatea-full-msaa4-a/step-34"
python tools/check-snr04-depth-bands.py `
  "$base/renderdoc-gatea-full-b-tile-final.json" `
  "$base/renderdoc-gatea-full-msaa4-a/step-34/depth.f32"
```

Against the same-run compatibility sample-0 depth, the 4× private sample-0
mask has 99.50% intersection-over-union. The 208-row band has 98.21% mask
overlap. Median absolute depth error is `7.02e-5` but p90 is `0.00488`,
so 4× geometry alone has not fixed depth parity. Repeating the tile-end
draw-ID attribution with the new sample-0 identity files assigns 70,082 of
85,659 depth errors of at least `0.005` (81.8%) to vegetation. At 69,514
of those vegetation pixels the private depth is nearer. The same five
foliage IDs lead the errors as in the 1× diagnostic. Reproduce with
`tools/check-snr04-depth-bands.py`, passing the draw-order manifest as
`--order` and `step-12`, `step-23`, `step-34` `identity.u16x4` files as
`--band-identities`.

The diagnostic still uses identity shading without the captured foliage
alpha/sample mask, stencil or material state. This pattern is consistent
with extra private foliage depth writes, but does not prove their cause.
A matched per-draw target comparison and resource freshness/lifetime
checks remain Gate A work; this output is not a native renderer admission
result.

### Matched foliage draw with compatibility prior depth

The leading foliage draw, global ID 290 at private sequence 10125747,
joins RenderDoc event 11204 in the same source-5001 capture. A bounded
check imports the four RenderDoc **before** depth samples from its 256-row
EDRAM band into a 1280×720 private target, clears private identity, then
replays only this draw at 4×. This removes earlier selected-only private
depth as a variable. The checker validates the reference's recorded
per-sample change counts before comparing the two draw deltas.

| Sample | Compatibility depth writes | Private depth writes | Shared writes |
| --- | ---: | ---: | ---: |
| 0 | 27,325 | 91,039 | 27,323 |
| 1 | 54,472 | 82,522 | 54,443 |
| 2 | 43,233 | 87,275 | 43,225 |
| 3 | 8,458 | 95,448 | 8,458 |

The compatibility draw changes 133,488 samples across 59,649 pixels;
133,449 of those samples and 59,634 of those pixels also change privately.
The private identity shader additionally changes 222,835 samples. The
near-complete containment, paired with sharply different per-sample counts,
isolates a missing coverage/sample-mask behavior in this diagnostic draw.
It does not establish depth-value parity or identify which input to the
captured foliage shader controls every extra write.

```powershell
$base = '.local/native-renderer/snr04'
python tools/check-snr04-matched-vegetation-draw.py `
  "$base/renderdoc-gatea-full-b-vegetation-11204-depth.json" `
  "$base/renderdoc-gatea-full-live-b/snr03-scene-5001.bin" `
  '.local/native-renderer/seeded-probe/translation/dxil/vertex_5834939992FFC765_000000000000001F.dxil' `
  'out/build/win-amd64-relwithdebinfo/pinyon_shift_snr04_owned_scene_diagnostic.exe' `
  "$base/renderdoc-gatea-full-b-vegetation-11204-matched-check" `
  --frame 5001 --sequence 10125747 --draw-id 290 --rows 256
```

The next bounded implementation should bind the event's captured pixel
constants, sampler and BC3 mip chain, execute its alpha/sample-mask path,
and repeat this exact-prior check. Only then should the same change extend
across all 53 textured vegetation actions and the complete selected slice.

### Bounded BC3 alpha and sample-mask replay

`tools/probe-snr04-vegetation-alpha-state.py` exports all four bound pixel
constant blocks, used SRVs and samplers for event 11204. In the same-run
capture, pixel constant block 1 matches the fixture's twelve words exactly.
The captured descriptor indices select BC3 resource 8122 at slot 816 and
sampler 14, which clamps UVs and uses 4× anisotropic filtering. The BC3
nine-mip chain has SHA-256
`812AF0DC0BCFE510207BAB31EB22FF7E55693FBE65F109B3A19A0D7C25D5478E`.
The system/fetch blocks specify a 256×256 texture, unit derivative scale,
alpha-test mode 7, four-sample mask mode and pattern 426.

An opt-in diagnostic uses this verified BC3 chain and sampler with the
captured shader's alpha product and four threshold comparisons. It retains
the translated vertex shader and private identity output. The mode accepts
only matched sequence 10125747, draw ID 290, a 4× target and imported
compatibility prior depth; it does not replace the original pixel shader
or generalize the captured state to other draws.

| Sample | Compatibility writes | Unmasked private | BC3 mask private | BC3 shared |
| --- | ---: | ---: | ---: | ---: |
| 0 | 27,325 | 91,039 | 27,234 | 12,087 |
| 1 | 54,472 | 82,522 | 54,569 | 47,285 |
| 2 | 43,233 | 87,275 | 43,576 | 29,990 |
| 3 | 8,458 | 95,448 | 8,512 | 1,259 |

The per-sample write counts are within 0.8% of the compatibility counts.
The BC3 path changes 60,009 pixels, close to the reference's 59,649, but
only 50,759 pixels overlap (73.67% union overlap). Depth p90 on shared
sample writes is `0.0030`–`0.0047`. The matched-input experiment below
identifies why this nominally same-run fixture drifts spatially.

```powershell
$base = '.local/native-renderer/snr04'
$env:SNR04_CAPTURE = (Resolve-Path "$base/renderdoc-gatea-full-b_frame5001.rdc").Path
$env:SNR04_OUTPUT = (Join-Path (Get-Location) "$base/renderdoc-gatea-full-b-alpha-state-11204.json")
$env:SNR04_EVENT = '11204'
& .local/tools/renderdoc-1.46/RenderDoc_1.46_64/qrenderdoc.exe `
  --python tools/probe-snr04-vegetation-alpha-state.py
python tools/check-snr04-matched-vegetation-draw.py `
  "$base/renderdoc-gatea-full-b-vegetation-11204-depth.json" `
  "$base/renderdoc-gatea-full-live-b/snr03-scene-5001.bin" `
  '.local/native-renderer/seeded-probe/translation/dxil/vertex_5834939992FFC765_000000000000001F.dxil' `
  'out/build/win-amd64-relwithdebinfo/pinyon_shift_snr04_owned_scene_diagnostic.exe' `
  "$base/renderdoc-gatea-full-b-vegetation-11204-alpha-check" `
  --frame 5001 --sequence 10125747 --draw-id 290 --rows 256 `
  --alpha-bc3 "$base/renderdoc-gatea-full-b-bc3/ResourceId-8122.bc3mips"
```

### Matched vertex constants isolate the event-11204 drift

RenderDoc pixel history shows one event-11204 fragment at each of pixels
`(1143,50)`, `(1153,51)` and `(1154,47)`. Its debugger reports UVs
`(0.1279203,0.9302118)`, `(0.0775642,0.9252256)` and
`(0.0693306,0.9369559)`; each fade is approximately one. An opt-in
private pixel readback, `alpha-inputs.f32x4`, records UV, fade and sampled
alpha in that order. The original fixture produces UVs
`(0.1150367,0.9263254)`, `(0.0646334,0.9213268)` and
`(0.0564239,0.9330517)`. Repeating the replay returns the same three
private records.

The vertex bytes for draw 290 are byte-identical across fixture and
RenderDoc (8,864 bytes), and all 64 vertex-system words match. **35 of the
92 bound vertex constant words differ**; four more trailing raw words differ
outside the 23-register shader binding. The first captured VS quad also differs
from the private original-system post-VS quad. This is an input-state
alignment problem in the diagnostic comparison; the BC3 sampler or mask
cannot correct displaced vertices.

`tools/probe-snr04-vegetation-pixel-inputs.py` exports the captured pixel
inputs, first VS quad, full vertex constants and SHA-256 of the fetched
vertex bytes. `tools/match-snr04-vegetation-constants.py` checks the exact
vertex-byte hash, system words, sequence and 39-word raw drift before producing
a local diagnostic fixture with only that item's captured vertex constants
substituted. With that fixture and the same compatibility prior depth and
BC3 chain, the single draw matches **all 133,488 depth-sample writes at
exactly the same pixels and samples**, with zero depth difference on every
write. The three private UVs become bit-identical to RenderDoc. This proves
the translated vertex path and bounded alpha/sample-mask path can reproduce
this draw's depth outcome when the vertex inputs align. It does not prove
the original pixel shader's color or the full scene's material/stencil
parity.

```powershell
$base = '.local/native-renderer/snr04'
$env:SNR04_CAPTURE = (Resolve-Path "$base/renderdoc-gatea-full-b_frame5001.rdc").Path
$env:SNR04_OUTPUT = (Join-Path (Get-Location) "$base/renderdoc-gatea-full-b-pixel-inputs-11204.json")
$env:SNR04_EVENT = '11204'
& .local/tools/renderdoc-1.46/RenderDoc_1.46_64/qrenderdoc.exe `
  --python tools/probe-snr04-vegetation-pixel-inputs.py
# Wait for the asynchronous exporter to write stage=done.
python tools/match-snr04-vegetation-constants.py `
  "$base/renderdoc-gatea-full-live-b/snr03-scene-5001.bin" `
  "$base/renderdoc-gatea-full-b-pixel-inputs-11204.json" `
  "$base/renderdoc-gatea-full-b-11204-constants-matched.bin"
python tools/check-snr04-matched-vegetation-draw.py `
  "$base/renderdoc-gatea-full-b-vegetation-11204-depth.json" `
  "$base/renderdoc-gatea-full-b-11204-constants-matched.bin" `
  '.local/native-renderer/seeded-probe/translation/dxil/vertex_5834939992FFC765_000000000000001F.dxil' `
  'out/build/win-amd64-relwithdebinfo/pinyon_shift_snr04_owned_scene_diagnostic.exe' `
  "$base/renderdoc-gatea-full-b-vegetation-11204-constants-matched-check" `
  --frame 5001 --sequence 10125747 --draw-id 290 --rows 256 `
  --alpha-bc3 "$base/renderdoc-gatea-full-b-bc3/ResourceId-8122.bc3mips"
```

Next, align captured and owned per-draw vertex constants across the frozen
slice before attributing pixel differences to materials. Then test the
original pixel shader, stencil and resource lifetime on the complete
ordered scene. The matching local fixture is an experiment, not a new
source-of-truth scene snapshot or Gate A admission result.

The slice-wide census confirms this is not isolated to draw 290. Ordered
event/sequence joins across the 45/67/67 EDRAM bands have **179/179 exact
fetched vertex ranges**. Every action differs from its owned fixture in
the same 35 of 92 bound vertex constant slots. The first and third bands have
exactly matching 64-word vertex-system blocks (112 draws total); the
middle band differs at system word 44 for its 67 draws. Thus material
comparisons against the current fixture remain confounded throughout the
foliage slice. Capture those vertex constants at the exact render events,
and account for the middle-band system word, before treating the fixture
as a pixel-aligned reference. Captured constants vary across tile draws of
the same vegetation item: 35 items have three distinct constant blocks,
27 have two and five have one. The old `SNR03F3` fixture stores a single
block per item from the prepared source-frame draw. The new `SNR03F4`
fixture preserves that source block for provenance and stores the 92
actually bound words separately for each final draw and tile variant.
The census of the old fixture is stored locally at
`renderdoc-gatea-full-b-vegetation-vertex-alignment.json`.

```powershell
$base = '.local/native-renderer/snr04'
$env:SNR04_CAPTURE = (Resolve-Path "$base/renderdoc-gatea-full-b_frame5001.rdc").Path
$env:SNR04_FIXTURE = (Resolve-Path "$base/renderdoc-gatea-full-live-b/snr03-scene-5001.bin").Path
$env:SNR04_EVENTS_JSON = (Resolve-Path "$base/renderdoc-gatea-full-b-vegetation-actions.json").Path
$env:SNR04_OUTPUT = (Join-Path (Get-Location) "$base/renderdoc-gatea-full-b-vegetation-vertex-alignment.json")
& .local/tools/renderdoc-1.46/RenderDoc_1.46_64/qrenderdoc.exe `
  --python tools/check-snr04-vegetation-vertex-alignment.py
# Wait for the asynchronous exporter to write stage=done.
```

The F4 producer was verified in a normal-exit output-frame-5001 run using
the AppData save: 65 items and 135 final vegetation draws, with each
stored bound-constant hash matching its live final-draw log row. The F4
private diagnostic rendered all 135 draws (70,034 unmasked pixels). A
synthetic F4 fixture made from the earlier RenderDoc capture confirms the
consumer layout: all 179 captured draws have exact fetched vertex bytes
and **zero bound-constant differences**. Event 11204 retains exact
four-sample coverage and depth. The 67 middle-band system-word-44
differences remain in that synthetic fixture, and the live F4 run is a
different race execution. Material, stencil and complete-slice reference
parity remain open.

The same live F4 run also passed the **six-family complete-slice verifier**:
2,307/2,307 selected draws joined immutable fixtures (631 track, 209
procedural items, 135 vegetation, 11 procedural characters, 297 character
manager and 1,024 remainder). The 4× ordered replay finished all 35
family runs with 695,089 covered sample-0 pixels, 697,154 pixels with any
sample covered, 2,778,635 covered samples, 249 visible sample-0 draw IDs
and no covered pixel at depth zero. A second replay made all **220 output
files** across the 35 stages byte-identical. This verifies the F4 change
does not break the full private target handoff; it is still an identity
diagnostic, not a complete compatibility parity check.

| Live F4 evidence | SHA-256 |
| --- | --- |
| Vegetation fixture | `62DCC62C78C4787DBB24CBAD7C00DEAEDB917DD800090835980D1CD8CB1D9095` |
| Complete-slice order | `F1F579748F829FAF3B763DED9A1F9A126A79DF8BF0DA10CAA3F4801980EE2C8F` |
| Final coverage / per-sample depth | `8D0068F98E033BD91A7F52EC5C3EE0569808ED70B0476E38611D290773B469BD` / `C83545B3E58DFF38EE8151016FB7C16F39B91AB8436681AF37D12BBC54C4B9D8` |

Reproduce from `.local/native-renderer/snr04/f4-final-bound-live-c` with
`tools/verify-snr04-complete-slice.py` using its `evidence.log` and
`ledger.json`, then `tools/replay-snr04-complete-slice.py --msaa4` using
its `order.json`, `track-shaders`, `remainder-shaders`, the existing
procedural DXIL directory and the captured vegetation VS DXIL. The route
was `track-frame-reference.fh1test` with
`pinyon_shift_snr03_probe_frame=5000`; compatibility remained authoritative.

### Paired RenderDoc capture: vertex inputs align, frame identity does not

Two further AppData-backed runs captured an `SNR03F4` fixture and RenderDoc
actions in the same process. Both passed the strict six-family draw join:
1,533 selected draws for capture `f4-paired-capture-b_frame5000.rdc` and
1,554 for `f4-paired-capture-c_frame5001.rdc`. The exact vegetation shader
scan found 189 actions in each capture. All 189 fetched vertex ranges and
all 64 vertex-system words per action matched their ordered fixture draws.
The captured vertex-float constants, however, differed from the fixture's
actually bound constants at the same 32 of 92 words in the first run and
30 of 92 words in the second. They also differed from the prepared constants
at those same 30 positions in the second run. Each of its 72 items had one
captured constant variant and one owned variant, so missing tile variants
do not explain this mismatch. The comparison remains an ordered diagnostic,
not a proved same-frame RenderDoc/fixture join or pixel parity result.

Probing source frames 4999 and 4998 while queuing capture 5000 did not
produce an owned scene fixture, although RenderDoc captured a populated
frame. Frame 4999 had preparation activity but no selected main-view call;
the capture filename is therefore insufficient to infer its source-frame
identity. The direct backend capture below tags output-frame identity at the
captured draw boundary and resolves this input-alignment gap. The updated
`check-snr04-vegetation-vertex-alignment.py` accepts the frame's actual
foliage draw count and reports prepared as well as final-bound differences.

### Exact backend-frame RenderDoc capture

The ShiftGlue probe now starts RenderDoc after output frame 5000 submits and
ends it after output frame 5001 submits when
`pinyon_shift_snr03_probe_frame=5000` and RenderDoc is attached. It also
groups each foliage draw under a marker containing the backend output frame
and global draw sequence. This is diagnostic-only; ordinary gameplay does not
start a capture or emit these markers. It avoids assuming that RenderDoc's
presentation-frame filename is a backend frame: three queued captures mapped
to backend output frames 5015, 5008 and 5066 despite filenames 5001, 4987
and 4980 respectively.

The direct capture `f4-direct-capture-a_capture.rdc` and six immutable
fixtures came from the same normal-exit AppData-backed race run. The strict
source-5000/output-5001 census covered all 2,918 prepared draws and joined
all **1,559 selected draws** to their owned fixtures: 667 track, 273
procedural items, 189 vegetation, 17 procedural characters, 93 managers and
320 remainder. RenderDoc exposed 189 foliage markers, every one labeled
`output=5001` with the exact fixture draw sequence. The checked shader hash,
all 189 fetched vertex ranges, all 92 bound and prepared vertex-constant
words, and all 64 system words per action matched. The prior uniform
constant mismatch was a frame-alignment error, not missing final draw state.

Reproduce the paired input check with RenderDoc injection and the extended
race route, passing `--pinyon_shift_snr03_probe_frame=5000` and the matching
source-frame trace flags, without queuing a presentation-frame capture. Run
`probe-snr04-vegetation-actions.py` with `SNR04_CAPTURE`, `SNR04_FRAME=5001`
and `SNR04_OUTPUT`, then run
`check-snr04-vegetation-vertex-alignment.py` with that events JSON, the
`snr03-scene-5000.bin` fixture, capture and output paths. Both scripts write
`stage=done` JSON on success. This proves the foliage geometry input join;
pixel shader/material, stencil, resource lifetime and full selected-slice
image parity remain open.

The same-frame pixel-input census classified all 189 marked foliage draws:
135 use no pixel shader SRVs, and 54 use the same translated alpha-discard
pixel shader with one BC3 texture and one full-view resource. Nine of those
54 list BC3 first; 45 list the full-view resource first. The census now
identifies roles by resource format and checks the two descriptor indices
without assuming binding order. It exported five complete nine-mip BC3
chains (87,408 bytes each); their SHA-256 hashes match all five chains from
the earlier independent RenderDoc capture. The local JSON report is
`f4-direct-vegetation-pixel-census-final.json` (SHA-256
`E2C86691CD600CDF8DC9CE1E3F97DDDC662088CFE61744A03C8A188DBF811B90`).
This owns the captured alpha inputs for this frame but does not yet prove
their source generations, alpha coverage or private-pixel parity.

The same 1,559 draws also completed the carried 4× private replay. Its
sample-0 output has 906,050 covered pixels. A RenderDoc target-state census
located the final compatibility draws for the three reused depth tiles at
events 10715, 14310 and 18468. The sample-0 target-space comparison has
904,117 reference-covered pixels, all overlapping private coverage, and
99.79% coverage intersection-over-union. This overlap is weak for the first
two fully covered tiles; the 208-row tile has 99.23% overlap. Overlap depth
error has median zero but p90 `0.00469`; 74,349 large errors (threshold
`0.005`) fall on private vegetation IDs, and all have the private depth
nearer. A per-draw check of matched foliage event 10089 / private ID 291
found 60,826 reference-changed pixels against 97,903 from the unmasked
private draw, with no reference-only sample changes. The reference's
27,579 changed sample-0 texels all overlap the private draw. This supports
alpha/sample-mask work as the next bounded test, while retained draws,
stencil and material behavior remain confounders. The local depth comparison
is `f4-direct-depth-comparison.json` (SHA-256
`6F17C69FA04830BD89FF0A8ACC608DC52174E3E84164CFD761C1CDC4ED55DC8C`).

The opt-in BC3 alpha probe now accepts any one sequenced foliage draw with
the checked captured system state and a compatibility prior. For the same
source-5000/backend-5001 capture, event 10089 (sequence 10100754, private
ID 291, BC3 resource 7929) reproduced **all** 60,826 reference-changed
pixels. Its four sample write counts were exactly 27,579, 55,674, 44,169
and 8,341 on both sides; there were no reference-only or private-only
writes, and every overlapping depth value was identical. The unmasked
private draw had written 97,903 pixels. Reproduce with
`tools/check-snr04-matched-vegetation-draw.py` using
`f4-direct-vegetation-10089-depth.json`, the F4 scene fixture, the verified
foliage vertex DXIL, `--frame 5000 --sequence 10100754 --draw-id 291
--rows 256`, and `--alpha-bc3
f4-direct-vegetation-bc3/ResourceId-7929.bc3mips`. The local comparison
JSON is `f4-direct-vegetation-10089-alpha/comparison.json` (SHA-256
`692DAAB5FF7559AB96D7968829FD6EE09FD5B45E4987286AFD05814E9FC550E2`).
This isolates the per-draw depth discrepancy to the missing alpha/sample
mask for this draw. The diagnostic still uses an opt-in reconstructed pixel
shader, not the original material path; one exact draw does not establish
full-slice material parity, resource-generation ownership, stencil behavior,
or stability across moving frames and unloads.

A second same-frame draw, event 10084 (sequence 10100753, private ID 290),
uses a different captured BC3 chain (resource 7849). Its 3,582 changed
pixels, all four sample-write counts (1,029, 3,120, 2,388 and 103), and
every written depth also match exactly. The opt-in diagnostic accepts only
the five SHA-256-checked BC3 chains in this capture. The local comparison is
`f4-direct-vegetation-10084-alpha/comparison.json` (SHA-256
`9CB4528396EFF87229E319D697D3083E107E179A4920C2F60997B9229D3FE15A`).
