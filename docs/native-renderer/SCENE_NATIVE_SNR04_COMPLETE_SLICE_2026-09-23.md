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
