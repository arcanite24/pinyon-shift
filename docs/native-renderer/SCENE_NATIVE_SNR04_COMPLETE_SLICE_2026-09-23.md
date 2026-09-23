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
| Event-state report | `640D8E60FCA3A7179383FCD486C75903FFF660404543B2A7C38DDE6891A26D37` |
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
