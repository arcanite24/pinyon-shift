# Scene-native baseline and first ownership join

Status: SNR-00 and SNR-01 **in progress**. This records a reproducible
compatibility control and a bounded title/GPU evidence map. It authorizes no
scene admission, draw suppression or claim of native-renderer speedup.

## Qualified local control

The compatibility control used Pinyon
`a9ed5d5cda4cf19cd8bb5c3a9c83e6869c023115` on `dev`, with ShiftGlue
`bf7df82c6322d98b099e19909a8cfc657cfbea36`.
The RelWithDebInfo build completed on 2026-09-22. The SDK build used
`tools/prepare-rexglue.ps1` to materialize `libmspack` symlink targets on
Windows; this leaves only generated vendor-file differences in the nested
checkout. The earlier uncommitted SDK profiling probes remained stashed and
were not part of the binary. The build profile labels the root dirty because
of the materialized nested checkout; hashes below identify the actual binary.

| Input | SHA-256 |
| --- | --- |
| `pinyon_shift.exe` | `F6B01AC3696417A4138288E0212ADF1E7C5412A3189F0F6CD1E869BAB5F82E32` |
| `rexgpu-fh1rd.dll` | `B98AFE02B10B101A10FF78DBF0AACC6403BAE945C61DFEF48D025509A9256DF7` |
| `rexruntimerd.dll` | `C5076E5C1152A31294FD6944BAB20D8F4330A98801C77D1E0A5C97E038CB54D2` |
| Installed native shader catalog v2 | `3C77C669F68F645B5F2B27351D1BB1054B98EE92A3AADE5057D5B2F428CAA5C2` |
| Installed native pipeline catalog v1 | `1FDE4F6EE2D727BA98459560668A1BADAF619B00C0FD49B63D485DFD50141D56` |
| Installed `pinyon_shift.toml` before control | `1684B2F632B04AEAC0DDF76C52E9453F6E9A43EBA0B0D81A356B6A22F2D5E8A4` |
| `fh1-race-sustained.fh1test` | `298C69DCD4A7A10DF05C8084258F61AE67147D1C166313DCF9056B67ACE85D19` |

The installed AppData preview profile is under
`%LOCALAPPDATA%/PinyonShift/source/0.1.0/.local/preview/user` and the verified
guest executable hash is `DB40DF605ADE49A612B35A7A24C38F6004BCB17A88ED6B48288DE16DF9E3987C`.
The installed host settings were D3D12, 1× scale, legacy occlusion queries,
vsync on, variable refresh/tearing off, no host FPS cap, source presentation
on, motion blur and depth of field off, anisotropy 3 and no swap post effect.
The display capture was 1280×720. Hardware: Ryzen 7 5800X, RTX 4080,
NVIDIA driver `32.0.15.8108`. These settings are part of the reference image
quality; changing them creates another baseline.

Launch with the checked AppData save and no existing `pinyon_shift` process:

```powershell
$stateRoot = Join-Path $env:LOCALAPPDATA 'PinyonShift\source\0.1.0\.local\preview'
.\tools\launch-preview.ps1 -Configuration RelWithDebInfo `
  -StateRoot $stateRoot `
  -RenderTestScript config/render-tests/fh1-race-sustained.fh1test `
  -RenderTestOutput .local/native-renderer/snr00/<run-id> `
  -RenderTestTimeoutSeconds 240 -Hidden `
  -GameArgumentsJson '["--pinyon_shift_capture_performance=true"]' -Json
python tools/summarize-drive-window.py `
  .local/native-renderer/snr00/<run-id>/frames.perf.csv `
  .local/native-renderer/snr00/<run-id>/events.jsonl `
  --start race-moving --end race-sustained
```

The first and third controls were uncontended normal exits with seven valid
captures, no error event and 1280×720 output. Raw output images, event logs,
frame CSVs and summaries are local under `.local/native-renderer/snr00/`.
The second control followed the same route, but an unrelated static source
scan overlapped its timing window; it is retained for route evidence and
excluded from the timing-noise estimate.

| Control | Samples / wall | Start X,Z | End X,Z | Travel | Median | p95 | p99 |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| A1 | 1,538 / 29.999 s | −1412.506, 2808.671 | −1747.420, 2644.752 | 372.9 m | 20.066 ms | 26.179 ms | 29.166 ms |
| A2, source scan overlapped | 1,519 / 30.018 s | −1412.961, 2808.890 | −1747.369, 2644.780 | 372.6 m | 20.239 ms | 27.029 ms | 30.146 ms |
| A3 | 1,544 / 30.019 s | −1412.948, 2808.877 | −1747.375, 2644.792 | 372.6 m | 20.060 ms | 25.638 ms | 29.114 ms |

A1 and A3 differ by 0.488 m at the start and 0.060 m at the end. Their
median, p95 and p99 differences are 0.030%, 2.088% and 0.178% of the pair
centres. These are **two pilot controls**, not the final control variation
for Gate B. The older 18.922 ms post-fix trace began around X = −1743 m,
so it is hotspot evidence, not a matched performance baseline for this route.

### Frozen pilot visual reference regions

The A1 control produced four 1280×720, full-resolution PPM images that fix
review locations for the initial compatibility reference. They are local
under `.local/native-renderer/snr00/control-a1/`; rerun the frozen route
above to reproduce them. Hashes identify this exact set, not a claim that
independent race replays produce identical pixels.

| Image | SHA-256 | Review rectangles `(x, y, width, height)` |
| --- | --- | --- |
| `event-entered.ppm` | `55809BC9219B7B0F58B0FAAD6C1FCE76E4330B3FBEA1C6BEB98E464F1C57D3A7` | Festival menu/text `(220, 155, 825, 390)`; car behind UI `(0, 285, 1270, 375)` |
| `race-ready.ppm` | `2627D7B42326DF4E400752B755798BE82EEE44A7E2EE247A93C12E48E44BE184` | Traffic body/glass `(500, 245, 580, 200)`; player body/glass `(470, 375, 335, 325)`; road/shadow `(235, 385, 660, 330)` |
| `race-moving.ppm` | `A9DF949B91428EACB79C45641398C7D38A8A5B11C05DC42F3E28E5296E8CE80D` | Road/terrain boundary `(0, 255, 620, 465)`; grass and fence edges `(810, 265, 390, 260)`; vehicle/shadow `(475, 380, 395, 340)`; sky/exposure `(255, 0, 700, 285)` |
| `race-sustained.ppm` | `FCD747EA54ECAABE4BDB8A57C9C1EDBB05373BAD02E63DAC642A1982A38BE4D1` | Grass/crowd alpha edges `(0, 255, 485, 365)`; player paint/glass `(465, 380, 350, 295)`; lit barriers and shadow `(180, 340, 950, 360)` |

All four show HUD, with the race timer/place in the upper corners and
speedometer at lower right during driving. `race-moving.ppm` captures the
vehicle in motion; the installed settings disable motion blur, so it is not
a blur reference. The menu image is a compatibility-only mode for the
proposed main-view slice. Mirrors, photo mode, and any uncovered reflections
still require explicit whole-frame compatibility behavior. These rectangles
are visual review targets; Gate B still requires same-frame native and
compatibility images and title-proved pass membership before judging parity.

## Predeclared Gate B comparison

- Use the same 1× installed settings and source route, with compatibility
  control A and native candidate B. Run at least two warmed ABBA blocks with
  per-run source-aligned `race-moving` → `race-sustained` summaries. Keep
  diagnostic traces, RenderDoc and screenshot readbacks off in timing runs.
  Run cold startup and 3–5 minute streaming checks separately.
- Reject a pair whose starting pose differs by more than 2 m, ending pose by
  more than 5 m, simulation time by more than 1%, or whose route shows a
  collision/scene transition absent from its partner. Record exclusions rather
  than silently pairing different race positions. Compare one second of
  stationary traffic separately because moving-route car placement can vary.
- Let `A` be the median of the four per-run control medians and `B` the median
  of the four candidate medians. Define control variation as the range of the
  four A run medians divided by `A`. Gate B needs `(A−B)/A ≥ 15%` and greater
  than twice that observed variation. Candidate per-run p95 and p99 medians
  may rise by at most 3% and 5% versus controls, respectively. If control
  variation itself exceeds a tail limit, repeat controls; do not loosen the
  limit after seeing candidate results.
- Require complete scene content and current resource/pose generations. Check
  full-resolution reference crops covering road and grass edges, foliage
  alpha, player/traffic body and glass, shadow boundaries, sky/exposure, HUD
  and menus. Same-frame native and compatibility images are needed before
  judging shader parity; race screenshots from different runs are context,
  not pixel-perfect references. Count admission, unsupported full-frame
  fallback, repeated/dropped presents and simulation time.
- Record host commit and dedicated GPU memory across warm and 3–5 minute
  windows. Provisionally cap incremental committed/resident memory at 512 MiB
  each and steady-state growth after warmup at 64 MiB. Measure the actual
  control footprint before Gate B; a larger need must be justified and frozen
  before the candidate comparison, never after observing its performance.

The proposed first slice remains the full main-view opaque/alpha-tested
contribution and its color/depth interfaces. **SNR-00 is not closed:** exact
title view/pass membership and an image comparison set spanning all required
materials need SNR-01/02. The observed RenderDoc scene target below is a
candidate boundary, not a substitute for that proof.

## SNR-01 title-to-GPU evidence map

The source-frame hook at `0x829EFEB8` observes FH1's sole `VdSwap`. The
read-only title hooks at `0x8240F4D8` and `0x82410328` observe the indexed
emitter and exact PM4 draw-header publication. The current SDK
`GraphicsPreparedDrawObservation` carries frame sequence, shader hashes,
index buffer/range and prepared state, but no title owner/view identity.
The current GPU census is therefore structural and cannot label a material
or connect a RenderDoc event to a title object by itself.

The freshly regenerated static dispatch inventory at
`.local/native-renderer/snr01/dispatch-static-with-image.json` (SHA-256
`640D9B643806F12705DFA5B680663FA1DC9EC0A12D83772263E008899DBDD1EF`)
identifies `proceduralGeometry::CProceduralModels` through RTTI and verifies
the `0x82417418` per-record helper. Candidate read-only boundaries are helper
entry `0x8241741C`, final return `0x82417B80`, render-state entry/return
`0x824170DC`/`0x82417410`, and geometry submission `0x82417B60` leading
through `0x82415CE0` to emitter `0x82415F68`. The inventory explicitly says
mesh/material ownership, LOD meaning, runtime view join and graphics target
join remain unproved. The separate `0x82BC5A3C` vehicle pose hook is shared
by player and traffic and does not identify the player render owner.

The local RenderDoc race frame at
`.local/cpu-profile/traffic-attribution/race-start-capture_frame4709.rdc`
has 5,439 draw actions. Its payload-free trace shows two preceding depth
producer ranges (1,079 draws on D24S8 `ResourceId::8655`, 1,094 on D32S8
`ResourceId::6980`) and a 2,579-draw 4×MSAA scene-color phase on color/depth
`ResourceId::2487/2488`. Both depth resources have later compute/pixel readers;
the color output has ten later pixel readers. These are resource dependencies,
not proof of camera identity or which individual draw is visible. See the
[race-frame attribution](CPU_HOTSPOT_RESULTS_2026-09-21.md#renderdoc-race-frame-producer-and-consumer-join--2026-09-22).

### Bounded source-frame packet probe

The default-off `pinyon_shift_snr01_trace_source_frame` probe observes one
source frame without changing guest state. The saved sustained-race route ran
to normal exit with target frame 6000 and executable SHA-256
`E932A4A6BB0F203CC901CDC8A3ABE2D19682A790262ADDC6D84ECB224EF3F388`.
The raw title packet log is local at
`.local/native-renderer/snr01/semantic-frame-6000/title-packets.log` (SHA-256
`03CCB835A58927FC27CB18724042CB39FE5648F36345AC8E55A6B91D632859A0`).
Its source-frame summary reports 42 generic indexed packets, 392 packets at
the two verified procedural emitter stores, 231 procedural item calls, zero
unmatched returns and zero unfinished scopes. Neither bound was hit (8192
packets, 4096 items). The probe is diagnostic, not a timing baseline.

The generic indexed wrapper produced **zero** packets within item scopes.
The procedural emitter instead produced 197 packets within 197 item calls:
186 at `0x82416260` and 11 at `0x824162F4`, across 36 observed receiver
addresses. Thirty-four calls produced no packet. The remaining 195
procedural-emitter packets occurred outside those item scopes; this may be
other callers or work stages and is not yet classified by view. All 392
packets used one observed command-owner register value, which identifies a
shared command context, not a render owner. Guest packet addresses and
header words are recorded for the later backend join. Counts from this run
are not a draw census for every view or route position.

### Exact packet address to prepared-draw join

The next default-off diagnostic adds the PM4 draw-header physical address,
command-buffer base, capacity and draw-end offset to ShiftGlue's prepared-draw
observation. The saved route again exited normally, using executable SHA-256
`1E165D50D34E4528F1B60C6214874419ACA9A45F8AE4AFAD93AACE93ED6511E8`.
The final SDK GPU DLL SHA-256 was
`1A41505285B1E8172DA5D71424A9D3F2350330C9CA8002FADC61E4FCB453AC09`.
The local combined log at
`.local/native-renderer/snr01/backend-join-final-frame-6000/title-backend-packets.log`
has SHA-256
`3B770AF21DC6780F0710C6E671578C770FA37585BCB9D6273B431042C1C9794E`.
This instrumented run saw 441 distinct procedural-emitter header addresses,
290 inside item scopes. Every one appeared in a prepared-draw callback in
backend frame 6001, while the title hook labelled its source frame 6000.
Every matched callback also satisfied
`(command_buffer + draw_end_offset - packet_physical) % command_bytes == 12`,
the three-word draw packet length. The match used the physical address and
buffer position, not a shader, attachment or image size. Backend frame 6000
preceded the title submissions and is not joined to them.

The 441 headers yielded 593 prepared-draw callbacks: 329 headers appeared
once, 72 twice and 40 three times. This shows repeated execution of packet
addresses; the exact replay/bin cause remains to be proved. Matched callbacks
span 26 shader pairs and render-target bit values 1, 2 and 3, so these
packets cannot be assumed to be one pass. Forty-five generic indexed-wrapper
headers did **not** match a prepared draw in frame 6001, and 4,285 of that
frame's 4,878 prepared draws matched neither observed title header class.
They remain unclassified; some may use other title emitters. The join proves
an exact address/packet-position correlation, not a unique producer
generation: buffers can reuse the same physical address across frames. It
does not prove view, material, resource generation, visibility or complete
coverage. This capture is diagnostic and must not be used as a timing
comparison.

### Receiver phases and emitter callers

An additional default-off source-frame 6000 capture ran to normal exit with
executable SHA-256
`146B63C46CE4936B32F0E018CA898D30647FAFA7D133AD3BEE110316A25F2562`.
The combined title/backend log is
`.local/native-renderer/snr01/emitter-caller-frame-6000/title-backend-emitter.log`
(SHA-256
`E89040F6801C2848DAC756511D5E7B90E790F4BCBC6349C88C72EE26B59644EF`).
The source `runtime.1.log` and `runtime.log` were both required because the
diagnostic output rotated at 5 MiB. Its summary reports 100 balanced
`CProceduralModels` slot-41 dispatch calls, nine balanced slot-40
render-state calls, 296 balanced item calls and 386 balanced emitter calls,
with no unfinished scope or trace cap hit.

The 100 slot-41 calls and 296 item calls share 44 distinct receiver
addresses and one observed graphics-context address, but **no item call or
draw packet is nested inside slot 41**. The nine slot-40 calls use one
aggregate receiver and contain all 296 item calls. The item path emits 235
packets; 61 items emit none. The other 151 procedural packets occur outside
slot 40. This separates two title phases and avoids treating the slot-41
receiver as the direct draw owner. The argument values on either path are
still unlabelled; a value such as 1 or 2 is not yet a view identity.

The original caller return address at `0x82415F6C` partitions all 386
emitter invocations and packet stores. Each packet passed the exact
physical-address and ring-buffer-position join in backend frame 6001:

| Caller LR / static function | Title packets | Prepared-draw callbacks | Item/render-state overlap | Distinct shader pairs | Observed target bits |
| --- | ---: | ---: | --- | ---: | --- |
| `0x82415D1C` / `sub_82415CE0` | 235 | 299 | all 235 | 8 | 1, 3 |
| `0x82412E1C` / `sub_82412DD8` | 129 | 213 | none | 7 | 1, 3 |
| `0x82442B64` / `sub_824426B8` | 22 | 22 | none | 11 | 2 |

The 386 title headers produced 534 backend callbacks because some packet
addresses execute more than once. Of 4,635 prepared draws in backend frame
6001, 4,101 matched none of these headers or the 44 generic-wrapper header
addresses. The generic headers also had no match in that frame. The three
caller functions are proven by the generated title code, but their scene
role, view, material and resource lifetimes remain unproved. A render-target
bit or shader family cannot substitute for those relationships.

### Item record and final submission join

The next saved-route capture exited normally with executable SHA-256
`036EAC24EA4183D1C7DD39A41F1135A757D37F89C8F5FCF16A878D7840397153`.
The local combined log is
`.local/native-renderer/snr01/record-submission-frame-6000/title-backend-records.log`
(SHA-256
`E9C3A6C903B235F303A5FA07FD3ACD1C27D6E76F047F89EB192F1B87ADBA3E34`);
both rotated runtime log files were needed. Read-only hooks observe the
title-selected descriptor at `0x82417684`, runtime record at `0x824176BC`
and final graphics call arguments at `0x82417B7C`. These instructions are
verified in the generated item helper; the trace captures values after the
title computes them and changes no guest state.

For source frame 6000, all 353 item calls observed both records. Across 47
distinct item receiver objects, `descriptor_address - 92 × descriptor_index`
and `runtime_address - 68 × descriptor_index` each yielded one stable base
per receiver. No observed base was shared by two receivers in this frame.
The descriptor kind values were 0 (292 records), 4 (9) and 5 (52). These
are title enum values, **not** proven material roles. The final graphics
call occurred for 292 items and did not occur for 61; every submitted item
emitted exactly one procedural packet, and no non-submitted item did. All
292 packet addresses matched 353 prepared-draw callbacks in backend frame
6001 after repeated packet execution. The other 163 procedural packets came
from the two non-item emitter callers and matched 268 backend callbacks.
The 45 generic-wrapper headers again had no match; 4,341 of 4,962 prepared
draws in backend frame 6001 matched neither observed class.

This proves the observed receiver → selected descriptor/runtime record →
graphics call → PM4 header chain in the title, and an address correlation
to prepared draws in the backend. Cross-frame address reuse prevents a
unique producer-generation claim. It does not prove that the 61
non-submitted items were intentionally
culled, what the descriptor kind means, which view owns the calls, or how
addresses behave across unload/reload and reuse. The final graphics call's
`r5` and `r6` values remain raw arguments until their contract is verified.

### Active higher-level caller paths

The wrapper-caller capture exited normally with executable SHA-256
`4AA263EB5B608EF98EDE091586B2B06E89E0A9343881612EC7AD3C6EDEFBB94F`.
Its combined rotated log is
`.local/native-renderer/snr01/wrapper-caller-frame-6000/title-backend-wrapper.log`
(SHA-256
`D653055235DD21659A5342E04EA4250F4C0754C35AA615022B6417E6BBFC933C`).
Hooks just after the opening `mflr` in `sub_8243D2A0` and `sub_8243BD40`
record their original caller return addresses. Static generated code shows
these wrappers invoke vtable slots 40 and 41, respectively. They can also
invoke other implementations; a wrapper call alone is not a procedural draw.

In source frame 6000, argument equality and immediate call nesting joined
all nine actual `CProceduralModels` slot-40 calls to their wrapper invocation:
eight came from `sub_82439B70` at return `0x8243ABC8`, one from
`sub_8240E7B0` at `0x8240EC80`. The 108 actual slot-41 calls split 94
from `sub_82439B70` at `0x8243AD70` and 14 from `sub_8240E7B0` at
`0x8240ED14`. The third static wrapper caller, `sub_82DEF2B0`, was observed
at wrapper entry but did not invoke these procedural receiver methods in
this frame. The trace reports balanced procedural scopes and 416 emitter
packets. This identifies the live parent functions for the saved route, but
their camera/view and pass semantics still need to be recovered from their
own inputs and title relationships.

The existing `discover-native-renderer-track-ingress.py` static check passes
against the generated title and extracted image. RTTI identifies
`Presentation_Unified::CTrackPresentation` at vtable `0x82243774`; its
derived slots 75 and 79 point to `sub_82439B70` and `sub_8240E7B0`.
`discover-native-renderer-direct-indexed-producers.py` also verifies that
both functions call the unified track presentation helper `0x82436468`.
The local check outputs are
`.local/native-renderer/snr01/track-ingress-static.json` and
`.local/native-renderer/snr01/direct-indexed-static.json`. This makes the
two live parent functions track-presentation paths, but does not establish
which camera/view invoked each slot or that every procedural receiver is a
track mesh.

### Presentation-view scheduling boundary

Two more normal-exit saved-route captures observed source frame 6000 with
read-only hooks at the track-presentation slot-75/79 entries and at their
guarded slot-75 helper. The final capture used executable SHA-256
`F44396CFA02BF4D7DDCE71EE23A1CF62EBA0EC7653BAA6C8BC665C74E0E71494F`.
The logs are local at
`.local/native-renderer/snr01/track-entry-frame-6000/title-track.log`
(SHA-256 `91725B5AAE1F5DB668FEBC78A5F9E4CCB1E89E9F6889C289FBA7A05971066855`)
and `.local/native-renderer/snr01/track-pass-frame-6000/title-track-pass.log`
(SHA-256 `EE22F8C0EEB0D49E6625B060FE879DB077E418331E603AEC36AE9EF612FEA81A`).
The latter reports 19 slot-75 calls, two slot-79 calls, 19 helper calls,
346 procedural items, 441 emitter packets and balanced scopes. The former
reports 19 slot-75 calls, one slot-79 call and balanced scopes. These are
different route replays, so their call counts are not interchangeable.

The regenerated track-ingress static check (local output
`.local/native-renderer/snr01/track-ingress-static.json`, SHA-256
`1FF5BF64E4C8554C5309B00716E7A6925562AF2F6068B42CB7B8A95B30752549`)
verifies RTTI for `CPresentationView` and its refcounted form at vtables
`0x8200265C` and `0x8200255C`. Both slot 13 entries point to
`sub_82444E60`. Its generated code contains six direct calls to guarded
helper `sub_8244CA98`, which obtains the nested track-presentation receiver
from the view object's state and invokes vtable slot 75. In the final
capture, each of the 19 helper entries was immediately followed by one
slot-75 entry with matching outer receiver, context and selected raw
arguments. No helper entry was left unmatched. The 19 helper entries came
from six return sites in `sub_82444E60`:

| Return site | Calls | Raw argument group |
| --- | ---: | --- |
| `0x82445B14` | 8 | `r7=1, r8=0` |
| `0x82445B68` | 1 | `r7=2, r8=2` |
| `0x82445CD0` | 7 | `r7=8, r8=0` |
| `0x82445F18` | 1 | `r7=2, r8=1` |
| `0x82445FE8` | 1 | `r7=16, r8=3` |
| `0x82446008` | 1 | `r7=32768, r8=4` |

The helper can change other arguments before the vtable call; in particular
its `r6` and `r8` must not be equated blindly with the slot-75 entry's
registers. The static view relationship narrows the title scheduling
boundary, but the captured outer receiver's runtime vtable, camera object,
meaning of the raw argument groups and their graphics passes remain
unverified. Neither slot-79 invocation in the final frame is yet joined to
a specific visible-list entry. This is not a complete main-view census.

### Direct indexed packet coverage and remaining gap

The verified direct indexed emitter `sub_82416380` is a third PM4 draw
producer, separate from the generic wrapper and procedural emitter. The
updated static verifier checks its two draw-header stores at `0x824166E4`
and `0x82416774`, common exit `0x824167EC`, and 13 direct caller sites.
Its local output is `.local/native-renderer/snr01/direct-indexed-static.json`
(SHA-256 `8427DB3762EAFF57A0BC8989CCF5114AA04CE1118AE545B487356A272484ABF0`).

A default-off, read-only trace on the sustained race exited normally with
executable SHA-256
`C9CBAE6D1185B963BE29CF7927F352FFCCF17BAF1309C1A7FD5010C9DB37B0F6`.
The combined rotated log is
`.local/native-renderer/snr01/direct-packet-frame-6000/title-backend-direct.log`
(SHA-256 `15C260B49C642C3DB252539042A92C01FF6367B0DF7D94CACF588CD1A6A80920`).
In source frame 6000, two title threads made 552 direct-emitter calls and
published exactly one draw header each: 506 at the primary store and 46 at
the secondary store. The swap thread's summary reports only its own 338
calls; the other thread made 214. Both threads' call scopes balanced, and
neither per-thread packet limit was reached. Direct call ordinals are local
to each thread and must be paired with the thread ID in the log prefix.

The live direct callers were vector font (`0x82412D90`: 162), D3D9 device
helpers (`0x824131F4`: 88; `0x823F59C8`: 9), navigation-map renderer
(`0x8240F020`: 67) and a title graphics helper (`0x8243C8FC`: 226).
The statically verified unified track-mesh caller `0x82C5B038` did not
occur in this frame. These names classify the immediate source functions;
they do not label the visual content of each backend draw.

All 552 direct header physical addresses exactly matched prepared-draw
callbacks in backend frame 6001, accounting for 746 callbacks after some
buffers were executed more than once. The 406 procedural headers matched
586 callbacks; 44 generic-wrapper headers matched none. The three packet
classes had no shared addresses. Of 4,908 prepared callbacks, **3,576**
matched none of these classes. Those unmatched callbacks span 768 observed
command-buffer base addresses; their raw render-target-binding bits were
3 for 2,437 callbacks, 1 for 1,134 and 2 for five. Those bits are binding
shape, not proven view or pass identity. The direct emitter was worth
checking, but it does not close the main scene coverage gap. Next work must
recover how the many other command buffers are produced and pair their
title owner/view with backend packet identity; adding shader or target
heuristics would not establish that join.

### Additional draw-header writers

The updated static check verifies stores in `sub_8240DC70` at
`0x8240E01C`/`0x8240E0B0`, `sub_82408B70` at
`0x82408F7C`/`0x8240900C`, and `sub_829F0928` at `0x829F0A4C`.
Its local output SHA-256 is
`1F42E53D0E5C529FA969BB3ECB2D7A3CF5D3F0B90B554320240EF639DF6F139A`.
The new default-off hooks preserve the title's original code and record
only header address, word, raw command context and producer site.

The sustained-route replay exited normally with executable SHA-256
`8AC5F1386C64021DDB7E7CEEE86CF4FE128261DA652F3FFDDB26050C09EDFCE0`.
Its combined log is
`.local/native-renderer/snr01/extra-packet-frame-6000/title-backend-extra.log`
(SHA-256 `C8164EDE13B5AE520F5224FA7150620F61F4B8F9E9630CEA0175C89CE27356F9`).
Source frame 6000 published 15 headers in `sub_8240DC70` (four primary,
11 secondary), 11 primary headers in `sub_82408B70`, and none at
`0x829F0A4C`. Every one of these 26 header addresses appeared in backend
frame 6001, accounting for 48 prepared callbacks. The prior direct emitter
published 449 headers that matched 690 callbacks; 386 procedural headers
matched 510; 41 generic-wrapper headers matched none. The six address
classes were disjoint in this replay. Of 4,621 prepared callbacks, 3,373
still matched no observed header address. These extra sites therefore do
not close the coverage gap, and their title owner/view roles remain open.

There is direct evidence that physical address alone is not a generation
key: 166 addresses published by the direct emitter in source frame 6000
also appear in backend frame 5999, before this frame's publication hooks
ran. Backend frame 6000 had no address overlap with the source-6000 set;
frame 6001 did. Future joins must include command-buffer submission and
reuse generation or ordering evidence. A bounded earlier-frame capture can
test whether the remaining backend buffers were recorded before source
frame 6000, but an earlier address match by itself would still be
insufficient for native admission.

The next runtime capture must carry a bounded title owner/generation, view,
record and selected LOD through final draw preparation and join the resulting
submissions to RenderDoc phase and resource identity.
Capture helper entry **and post-original state** so transforms/palettes are
not read before the title finishes them. Distinguish main, shadow and
reflection dispatch by owner/view relationships. Record unmatched title
entries and GPU draws on both sides of the join. Until this is demonstrated,
SNR-01 and Gate A stay open and no shader/attachment heuristic authorizes
suppression.

### Backend indirect-buffer execution graph

Prepared-draw observations now carry an indirect-buffer execution ID, parent
execution ID, and the dispatch packet's physical address. The command
processor assigns a fresh ID on each indirect dispatch and restores its
parent context after nested execution. This identifies repeated executions
of the same physical buffer without changing the draw path. The default-off
SNR-01 trace logs these fields alongside the draw packet and command buffer.

The RelWithDebInfo build completed, and the saved sustained-race route exited
normally. The executable SHA-256 was
`C1C5BA1F45DF3DBFD245E3577C5E5B448248AB37558FEC82BEB64088C7C15BBE`.
The combined rotated log is
`.local/native-renderer/snr01/indirect-dispatch-frame-6000/title-backend-dispatch.log`
(SHA-256 `16D84CC90020C59B663826A0D7845661E920552E1D0E98C919589BB654A5C588`).
Backend frames 5999, 6000 and 6001 reported 4,965, 4,759 and 5,122
prepared callbacks across 1,493, 1,458 and 1,572 draw-bearing indirect
executions, respectively. All observed execution IDs and dispatch addresses
were nonzero; no execution ID recurred across these frames. Within each
frame, every execution ID mapped to exactly one parent, dispatch address,
command-buffer address and size.

In backend frame 6001, 3,986 callbacks had a nonzero parent execution ID.
Of the 1,572 draw-bearing executions, 1,122 had a parent that also produced
a prepared draw; every one of those child dispatch packets lay within the
parent's observed command-buffer range. The other parent executions cannot
be checked by this draw-only observation. Across that frame, 833 draw packet
physical addresses occurred under more than one execution ID, with as many
as 85 executions sharing one address. Physical address alone therefore
cannot identify a draw generation.

Comparing the bounded source-frame-6000 header probes with backend frame
6001 produced 1,334 address-matched and 3,788 unmatched callbacks. Only 23
draw-bearing executions had all callback addresses matched; four were mixed
and 1,545 had none matched. These are address correlations, not title-owner
or generation joins. The backend execution graph is established, but title
command-buffer submission, owner/view, record and LOD still need a bounded
join to these executions before SNR-01 or Gate A can close.

### Complete dispatch hierarchy and primary-ring publication

The draw-only observation omits indirect executions that produce no prepared
draw, including some parents of draw-bearing buffers. A separate default-off
observer now records every indirect dispatch. The saved race exited normally
with executable SHA-256
`4D52B0C637EC38CEFF2CF5EA45AEB55FB07CF6BDD4E893E523D5BCB090673658`.
The local combined log is
`.local/native-renderer/snr01/indirect-full-graph-frame-6000/title-backend-full-graph.log`
(SHA-256 `65E3CF22309C06BA7469FEEABD530C9CDC5093F4159D5C51E0E64E4C7D59B9F4`).
Backend frame 6001 contained 1,637 unique indirect executions, 5,397
prepared draws and 133 top-level dispatches. Only 29 roots had prepared
draws; 167 executions had none. Every draw resolved to a root, every parent
ID was present, and every child dispatch packet lay inside its parent's
command-buffer range. Draw ancestry was one or two indirect levels deep.
Neither 8,192-event diagnostic cap was reached. This establishes backend
hierarchy for that bounded frame, not title ownership.

Generated title code identifies `sub_82409398` as the primary-ring indirect
packet writer. Its `0x824095B0` site computes the header address from the
ring base and word cursor, writes `0xC0013F00`, then writes the target and
length. Read-only hooks capture that write site and its caller. Static call
sites at `0x82409838` in `sub_82409668` and `0x829F6308` in
`sub_829F5FF0` are the two observed immediate paths. The caller names are
source functions, not view or scene-owner labels.

The final two-source-frame replay exited normally with executable SHA-256
`3BFCE0CFB1AF4816C894A6063C3366A616A9841D9757F56F4917E769C8E86522`.
Its combined log is
`.local/native-renderer/snr01/primary-caller-frame-6000/title-backend-caller.log`
(SHA-256 `1F41FE50568B3FC3B74084AE94D741FB36936325E7BC7065BCB94ABBFC9239C4`).
Source frames 6000 and 6001 wrote 132 and 133 primary indirect packets.
Across both source frames, 168 calls came from `0x82409838` and 97 from
`0x829F6308`; all used one observed device pointer, and each call submitted
one entry. Backend frame 6001 had 1,620 indirect executions, 133 roots and
5,145 prepared draws. Every root matched exactly one earlier title packet
address, with the same target command-buffer address. Of those roots, 102
were written in source frame 6000 and 31 in source frame 6001; they account
for 1,943 and 3,202 prepared draws respectively. The address, target and
ordering checks passed for every root, with no trace cap hit.

| Source frame / immediate caller | Backend-6001 roots | Roots with draws | Prepared draws |
| --- | ---: | ---: | ---: |
| 6000 / `0x82409838` | 84 | 8 | 1,943 |
| 6000 / `0x829F6308` | 18 | 0 | 0 |
| 6001 / `0x829F6308` | 31 | 21 | 3,202 |

This partitions the observed backend work by immediate title submission
path, but a no-draw root can still contain clears, copies, state or other
effects. The table does not identify scene views or safe replacement cuts.
Reproduce the check with:

```powershell
python tools/verify-snr01-indirect-join.py `
  .local/native-renderer/snr01/primary-caller-frame-6000/title-backend-caller.log `
  --source-frames 6000 6001 --backend-frame 6001
```

Log rotation removed the beginning of backend frame 6000 in this final
capture, so the complete title-to-root claim applies only to backend frame
6001. The exact bounded submission join does not yet identify the upstream
view, visible-list entry, selected LOD, material or allocation generation.
Trace the two immediate callers back to their queue producers and title
owners before using this chain for native scene admission or draw suppression.

### Queue helper caller split

The generated `sub_82409668` queues a target and may submit it directly to
`sub_82409398`. Its common exit is `0x82409838`. A read-only scope records
the helper's caller for each primary-ring packet, including calls that cross
the source-frame boundary. The replay exited normally with executable
SHA-256 `FB8FE05B05EB198582023F908622D1F2F2CC1291BC8F9E5F62160692F66D05BE`.
The local combined log is
`.local/native-renderer/snr01/queued-caller-frame-6000/title-backend-queued.log`
(SHA-256 `99A9B894965B3C05C288A30EB9AC92E6FB15EAA67B7666BF06A33C0939DDE7C0`).
The indirect-join verifier again passed: source frames 6000/6001 each wrote
133 primary packets, and all 133 backend-6001 roots were matched by unique
address, target and order. That backend frame contained 1,621 indirect
executions and 5,133 prepared draws, with no trace cap hit.

| Source frame / title caller path | Backend-6001 roots | Roots with draws | Prepared draws |
| --- | ---: | ---: | ---: |
| 6000 / `sub_8240CF68` → `0x8240CFF8` | 41 | 0 | 0 |
| 6000 / `sub_8240D070` → `0x8240D1B0` | 41 | 8 | 1,860 |
| 6000 / `sub_82469290` → `0x824693E4` / `0x82469434` | 2 | 0 | 0 |
| 6000 / `sub_829F5FF0` → `0x829F6308` | 18 | 0 | 0 |
| 6001 / `sub_829F5FF0` → `0x829F6308` | 31 | 19 | 3,273 |

The static code shows `sub_8240D070` computes a command-buffer length from
the device's command start and write cursor before calling the queued helper.
`sub_829F5FF0` interprets command words and submits an indirect target at
its `0x829F6308` site. Thus these caller sites classify device-level
publication paths, not the scene owner that originally recorded a buffer.
No-draw roots may still perform clears, copies or state changes. The next
join must follow queue/command-buffer production back to the view and its
visible objects; adding more device-flush callers alone cannot prove SNR-01.

### Presentation-view and track-presenter boundary

Static RTTI and the generated call site identify `sub_82444E60` as
`CPresentationView` virtual slot 13. Its `sub_8244CA98` path reads the
view state at `view+4`, loads a nested `CTrackPresentation` pointer from
`state+36`, and passes the outer view to track-presentation slot 75. The
default-off, read-only hooks now record view entry, selection, track link and
common exit. The selected-context pointer and numeric view arguments remain
raw observations; they are not camera, pass or LOD labels.

The saved race exited normally with the RelWithDebInfo executable SHA-256
`CEEEAC33737C238D483554213FF31CBF12D0CF82DCFFDD78CB661750C71568C1`.
The combined local log is
`.local/native-renderer/snr01/view-scope-frame-6000-probed/title-backend-view-scope.log`
(SHA-256 `9B21DE65BB68F8BF2CAFE04D9A1B226DD224173FD785CCF38927685632423521`).
The eight source-frame-6000 view calls had one view pointer, `0x43F84EC0`,
and matched eight exits on one title thread. The entry callers were
`0x823FA398` once, `0x8240A154` six times, and `0x8245032C` once. The
six middle calls used raw argument values `0, 4, 2, 1, 3, 5`. All eight
selection events observed context pointer `0x2E02E000`. All 19 track-link
events resolved the same view through state `0x41BEBCE0` to presenter
`0x41E40120`; 19 slot-75 calls carried the view in argument 9, and two
slot-79 calls carried it in argument 5. These pointers are capture-local.

The entry/exit scopes contained 282 of 374 semantic packets, 366 of 646
direct packet events across all threads, and only 6 of 130 primary indirect
packets in source frame 6000. The per-call semantic/direct/primary counts
were `84/160/4`, `11/1/2`, `10/1/0`, `11/1/0`, `7/1/0`,
`5/1/0`, `11/1/0`, and `143/200/0`. Scope ranges matched every packet
ordinal on the view thread, with no unmatched view entry or exit. The
existing indirect-join verifier also passed: backend frame 6001 had 131
top-level roots, 1,624 indirect executions and 5,180 prepared draws;
all roots joined to source-frame-6000/6001 title packets.

```powershell
python tools/verify-snr01-indirect-join.py `
  .local/native-renderer/snr01/view-scope-frame-6000-probed/title-backend-view-scope.log `
  --source-frames 6000 6001 --backend-frame 6001
```

The scoped calls do not cover most primary-ring publication. Some work may
be deferred, interleaved or performed by another title path; the capture
does not establish which. The next SNR-01 probe must join view/visible-list
entries to the command-buffer production and queue path, then to the exact
primary packets and backend draws. Do not infer main-view completeness or
safe draw suppression from the presenter-pointer relationship alone.

An address-range check supplies a narrower candidate join without another
hook. Every source-frame-6000 semantic and direct packet header lay inside at
least one backend-frame-6001 root command-buffer range. Mapping only the
packets within view scopes gave 15 distinct roots (7 distinct buffer ranges)
and 3,023 descendant prepared draws. Calls 1–7 reached three roots published
in source frame 6000 by the `0x8240D1B0` device path; call 8 reached twelve
roots published in source frame 6001 by the `0x829F6308` interpreter path.
The latter twelve are three executions each of four buffer ranges, so a
packet address alone cannot select one execution. This is a buffer-membership
candidate, not proof that every descendant draw belongs to the view call:
the buffer can contain packets recorded outside that scope, and address reuse
needs lifetime evidence. Capture exact buffer record/submit boundaries and
the visible-list owner before promoting these candidates to an ownership map.

### Track bucket entries to draw packets

`CTrackPresentation` slot 75 (`sub_82439B70`) indexes a pair of pointers at
`presenter + 56808 + 16 * (5 * arg5 + arg6)`. Their difference is divided
by 20, and the loop at `0x8243AB5C` visits that many 20-byte entries. It
first reads a pointer from entry word 0; a second branch reads entry word 1.
This is an authoritative title-side record traversal, but its pointer types,
record ownership and selected LOD remain unknown. Read-only hooks at
`0x8243AB64`, `0x8243AC8C` and `0x8243AD74` bracket each iteration and
record which pointer path it took and the packet ordinals emitted within it.

The final saved race exited normally with executable SHA-256
`F072059784D4689D9E067EC9CF81F0372FAB4B3D7010511E364E0C9EEDFD0C1C`.
Its local combined log is
`.local/native-renderer/snr01/track-bucket-secondary-frame-6000/title-backend-track-bucket-secondary.log`
(SHA-256 `D1FA08572A6E329C9EBC625CD6510CF5784F360978B5E887876E35544B2FBC44`).
Source frame 6000 had 445 logged entries, with no cap hit, unfinished scope
or unmatched exit. All had one view pointer (`0x4311F710`) and one nested
presenter (`0x41B10010`); every entry occurred inside a matching view call.
The bucket offset formula matched the observed slot-75 arguments. The eight
view calls contained `156, 10, 9, 8, 11, 6, 12, 233` entries respectively.

| Pointer path | Entries | Entries with packets | Distinct packet headers | Backend-6001 prepared-draw callbacks |
| --- | ---: | ---: | ---: | ---: |
| First word | 314 | 8 | 209 | 294 |
| Second word | 131 | 36 | 116 | 201 |
| Total | 445 | 44 | 325 | 495 |

The verifier checks that the two paths are exclusive, every scoped packet
ordinal exists exactly once on the same title thread, packet physical
addresses are distinct, and every one has at least one exact backend
prepared-draw packet-address match. The indirect-join verifier separately
matched all 132 backend-frame-6001 roots to title primary-ring packets;
that frame had 1,623 indirect executions and 5,123 prepared draws.

```powershell
python tools/verify-snr01-track-bucket-join.py `
  .local/native-renderer/snr01/track-bucket-secondary-frame-6000/title-backend-track-bucket-secondary.log `
  --source-frame 6000 --backend-frame 6001
python tools/verify-snr01-indirect-join.py `
  .local/native-renderer/snr01/track-bucket-secondary-frame-6000/title-backend-track-bucket-secondary.log `
  --source-frames 6000 6001 --backend-frame 6001
```

The other 401 entries produced no *observed semantic or direct* packet
inside their iteration. That is not yet evidence of intentional culling:
other work may be deferred, emitted by another path, or skipped for a
reason not captured here. Packet-address reuse across frames and record
allocation lifetime also remain unproven. This closes a bounded
view → presenter → raw bucket entry → PM4 header → backend draw chain for
325 packets, but it does not yet name mesh/instance, material, final
transform, LOD or pass, nor account for all draws in the selected view.

### Track bucket model identity and early guards

Static code following the 20-byte entry resolves the first pointer's `+4`
object and calls its vtable slot 13 through `sub_82413240`. The second path
calls `sub_8243F328` on entry word 1, then reads entry word 3 and byte 16
before `sub_8243BD40`. The first path passes its record to `sub_82436468`;
the second passes the resolved object and auxiliary fields to
`sub_8243BD40`. These are two different dispatch paths, not equivalent
fallbacks. The existing RTTI image verifier identifies vtable `0x82001D74`
as `Presentation_Unified::CTrackRenderModel_Unified`, with slot 13 at
`sub_82413228`. The verifier output is local at
`.local/native-renderer/snr01/track-ingress-identity-static.json`.

Read-only hooks at `0x8241325C`, `0x8243AB74`, `0x8243AC9C` and
`0x8243AD40` captured the live model vtable, first-path guard result,
second-path resolved pointer and auxiliary fields within each record scope.
The saved race exited normally with executable SHA-256
`04EE7F4C07A7CD3BC531A87D34984BB3B77D6EAAECA0D12D78447B14261F0932`.
The combined log is
`.local/native-renderer/snr01/track-bucket-identity-frame-6000/title-backend-track-bucket-identity.log`
(SHA-256 `82E21D046BB77926AD641892B1BC241509F9F9FC1BF5A34245EE501D6338F22C`).

This replay had 403 balanced bucket iterations. All 264 first-path entries
had a nonzero model object with vtable `0x82001D74`; all 264 early virtual
guards returned true, but only eight entries emitted observed packets.
All 139 second-path entries resolved a nonzero object and reached the
auxiliary-field read, but only 40 emitted observed packets. Entry word 3
was nonzero for 54 second-path entries. The captured byte-16 values were
`1` (82), `2` (45), `7` (6), `4` (4) and `6` (2); their meanings are not
established. The 48 packet-producing entries emitted 338 distinct headers,
all exactly joined to 509 backend-frame-6001 prepared-draw callbacks. The
indirect-join verifier also passed for all 131 backend roots, 1,581
executions and 4,767 prepared draws in that frame.

```powershell
python tools/verify-snr01-track-bucket-join.py `
  .local/native-renderer/snr01/track-bucket-identity-frame-6000/title-backend-track-bucket-identity.log `
  --source-frame 6000 --backend-frame 6001 `
  --first-model-vtable 0x82001D74
python tools/verify-snr01-indirect-join.py `
  .local/native-renderer/snr01/track-bucket-identity-frame-6000/title-backend-track-bucket-identity.log `
  --source-frames 6000 6001 --backend-frame 6001
```

The two early checks cannot classify the remaining 355 entries as culled:
256 first-path guards passed and 99 second-path objects resolved without
an observed packet inside that iteration. The next ownership join must
follow the selected model/auxiliary records into their concrete geometry,
LOD and material submissions, and separately account for deferred or other
packet producers before assigning an intentional-cull reason.

### Procedural item node to descriptor and packet

The generated `sub_824170D8` loop traverses six linked-list heads. At
`0x824171AC`, it reads node word 1 as an index, word 2 as an argument, and
word 0 as the item receiver. It stores the index at caller stack offset 84,
calls `sub_82417418` at `0x824171D4`, and advances through node word 3 after
the return at `0x824171D8`. The callee uses that index to address 92-byte
descriptor and 68-byte runtime-record arrays. This proves what the index
selects; it does **not** establish that the index means LOD.

Read-only hooks around that call captured node identity, list head,
receiver, index, view and track-bucket scope, and the procedural-item and
semantic-packet ranges. The saved sustained race exited normally with
executable SHA-256
`90695F45ECCB2D9D1F4D4EF90DF9520E6ACA6C9DED5C151D5A7E396C7F75E9C3`.
The combined log is
`.local/native-renderer/snr01/item-node-frame-6000/title-backend-item-node.log`
(SHA-256 `90920A6E4DDA44DA24756995BADAFB7AE1C5A6CEE3911A246F89DE45B3756D95`).

Source frame 6000 had 350 balanced item-node scopes and 350 item calls,
with one-to-one receiver/index matches. Of these, 269 nodes occurred inside
one of eight observed presentation views and a first-path track bucket.
Exactly 208 submitted one semantic packet each; all 208 packets have exact
backend-frame-6001 prepared-draw packet-address matches. The other 61
resolved both descriptor and runtime record but submitted no observed
semantic packet. Their descriptor kind was 0; no culling reason is yet
proven. The remaining 81 nodes submitted packets outside those view scopes.
Three of six static list heads were active in this frame. Per item receiver,
the descriptor and runtime array bases calculated from the index stayed
stable. The second track-bucket path did not produce a procedural-item call
in this capture; its 117 packets need a separate ownership join.

At the helper's final indirect call (`0x82417B7C`), vtable offset 160
receives literal `13` in `r4`, four times runtime-record word 7 in `r5`, and
either runtime-record word 6 or word 8 in `r6` (depending on an earlier
branch). For every submitted first-path item in this capture, the exact
backend draw's `index_count` was `4 × r6`, including packets expanded to
multiple prepared-draw callbacks. The same invariant passed the two earlier
race captures (196 and 209 first-path items). This identifies a bounded
count relationship, not yet the mesh payload, topology or semantic meaning
of literal `13`.

The track-bucket verifier now checks node/item balance, receiver/index and
packet-range equality, bucket and view ancestry, descriptor/runtime base
stability, and exact backend draw joins. The indirect-join verifier also
passed for 133 backend roots, 1,616 indirect executions and 5,242 prepared
draws. Both verifiers are runnable on the log above:

```powershell
python tools/verify-snr01-track-bucket-join.py `
  .local/native-renderer/snr01/item-node-frame-6000/title-backend-item-node.log `
  --source-frame 6000 --backend-frame 6001 `
  --first-model-vtable 0x82001D74
python tools/verify-snr01-indirect-join.py `
  .local/native-renderer/snr01/item-node-frame-6000/title-backend-item-node.log `
  --source-frames 6000 6001 --backend-frame 6001
```

This closes a bounded linked node → descriptor/runtime record → PM4 header
→ backend draw path for the first track-bucket path. The next probe must
identify geometry payload, material, transform and pass at the submit call,
and trace the second bucket path. The 61 non-submitting nodes and other
packet producers remain unclassified; SNR-01 and Gate A stay open.

### Descriptor resource keys and resolver returns

Before the final draw call, `sub_82417418` reads descriptor words 0 and 1
as indices into the receiver's table at `+8`. It passes the selected table
value to `sub_82415BF8` with slot 0 or optional slot 1. That helper caches
the key per slot and, on a change, calls `sub_82415AD0`; its returned object
is passed to a render-context virtual call at vtable offset 88. The object
type and semantic resource role are not yet proven.

Read-only hooks at the two call sites and the resolver return captured a
second saved-race replay. It exited normally with executable SHA-256
`9DC46A97B54155BCB6A9BAC1D5031402C9FD34EE8EB75F085F55A66759E73BD7`.
The combined log is
`.local/native-renderer/snr01/resource-resolution-frame-6000/title-backend-resource-resolution.log`
(SHA-256 `E4C4EE1EE07B9CDAA5070514CB4B02808F7260141F61BE4FAA6983B7E3CA416D`).

Source frame 6000 had 342 balanced item nodes. All 281 submitting items
reached exactly one resource candidate in slot 0; the 61 non-submitting
items reached none. There were 11 distinct keys. The resolver ran 197 times,
for the first candidate and each subsequent key change; 84 repeated-key calls
used its cache. All resolver returns were nonzero, and each key mapped to
one distinct returned object within this frame. These are frame-local
identities, not a lifetime or streaming guarantee. The 189 first-path
submitted items still joined exactly to backend draws; the 130 second-path
packets still lack an item/resource ownership join.

The expanded bucket verifier checks candidate-to-descriptor association,
slot uniqueness, submitted versus non-submitted reachability, cache-change
behavior and one object per key. The indirect verifier passed for 133
backend roots, 1,628 executions and 4,887 prepared draws:

```powershell
python tools/verify-snr01-track-bucket-join.py `
  .local/native-renderer/snr01/resource-resolution-frame-6000/title-backend-resource-resolution.log `
  --source-frame 6000 --backend-frame 6001 `
  --first-model-vtable 0x82001D74
python tools/verify-snr01-indirect-join.py `
  .local/native-renderer/snr01/resource-resolution-frame-6000/title-backend-resource-resolution.log `
  --source-frames 6000 6001 --backend-frame 6001
```

The next relationship to recover is the concrete resource type and the
geometry/index source behind the final draw. Key-to-object stability must
also be retested across unload/reload and address reuse before SNR-02.

### Second bucket path: live virtual targets

The second path calls `sub_8243BD40` with its resolved object, then invokes
that object's vtable slot 41 at `0x8243BEB4`. RTTI in the extracted image
identifies four 42-slot vtables. The static verifier now checks their
decorated names, deleting destructors and slot-40/41 targets; its local
output is `.local/native-renderer/snr01/second-dispatch-static.json`.

| Slot-41 target | RTTI class in `proceduralGeometry` | Vtable |
| --- | --- | --- |
| `0x82417BC0` | `CProceduralModels` | `0x82002B5C` |
| `0x823FDE50` | `CProceduralAnimatedScene` | `0x820029FC` |
| `0x8245AB88` | `CProceduralCharacters` | `0x8200289C` |
| `0x824136F0` | `CProceduralVegetation` | `0x82002AAC` |

A read-only call-site hook captured the object and actual target in a
saved-race replay. It exited normally with executable SHA-256
`4E189BB5ED6C5C29E61F07B15A365BFD7158B023B5543582779CE0EFE735D632`.
The combined log is
`.local/native-renderer/snr01/second-dispatch-frame-6000/title-backend-second-dispatch.log`
(SHA-256 `0EE907D3F79F840BC9FE49CC070DECB26793C6020E3D25E95EC619A26D17EC68`).
All 145 second-path bucket entries invoked exactly one slot-41 target on
the same object returned by their secondary resolver. Their source-frame
6000 packet and backend-frame-6001 draw joins break down as follows:

| Class | Entries | Entries with packets | Distinct packets | Prepared-draw callbacks |
| --- | ---: | ---: | ---: | ---: |
| Procedural models | 97 | 0 | 0 | 0 |
| Animated scene | 12 | 6 | 10 | 17 |
| Characters | 24 | 24 | 24 | 28 |
| Vegetation | 12 | 10 | 88 | 140 |
| Total | 145 | 40 | 122 | 185 |

The 97 model calls with no scoped packet are not proven culled. The
character, vegetation and animated-scene virtual functions are the next
concrete owners to trace into mesh, instance and material submissions.
The expanded track-bucket verifier checks target membership, exact
object equality, one dispatch per second entry, and each target's packet
and backend-draw counts. The indirect verifier passed for 132 backend
roots, 1,578 executions and 4,863 prepared draws:

```powershell
python tools/discover-native-renderer-track-ingress.py `
  .local/generated/default `
  --image .local/ui-verify/default-image.bin `
  --output .local/native-renderer/snr01/second-dispatch-static.json
python tools/verify-snr01-track-bucket-join.py `
  .local/native-renderer/snr01/second-dispatch-frame-6000/title-backend-second-dispatch.log `
  --source-frame 6000 --backend-frame 6001 `
  --first-model-vtable 0x82001D74
python tools/verify-snr01-indirect-join.py `
  .local/native-renderer/snr01/second-dispatch-frame-6000/title-backend-second-dispatch.log `
  --source-frames 6000 6001 --backend-frame 6001
```

SNR-01 remains open: target class identity is stronger than an anonymous
secondary record, but no selected second-path packet has a verified
mesh/instance, transform or material owner yet.

### Second-path child calls and draw counts

The generated slot-41 implementations have different child submission
routes. `CProceduralAnimatedScene` calls `sub_82414A00` at
`0x823FDF94` and `0x823FE08C`; `CProceduralCharacters` reaches its
render-context vtable offset-164 call at `0x8245AE9C`; and
`CProceduralVegetation` reaches the corresponding call at `0x82413A80`
inside a loop. The character count argument comes from object offset 156.
Vegetation reads a per-entry count and can multiply it by three before
the call. These are raw title paths; their mesh and material roles are
still unverified.

Read-only begin/end hooks around those calls captured exact per-child
semantic/direct packet ranges. The saved sustained race exited normally
with executable SHA-256
`062E15D13CFA12F8788046ED9F1D7E56E062416DA74BB13B06371E1974AC8F3A`.
The combined log is
`.local/native-renderer/snr01/second-draw-final-frame-6000/title-backend-second-draw-final.log`
(SHA-256 `71BB10E66CAD38B45C1ECC1BFCDA5FD92DC66D7C872FE88834AC054B43FBD79F`).

In source frame 6000, all 142 second-path packets belonged to exactly
one child call, nested under the matching second bucket entry and its
slot-41 target. Every packet had an exact backend-frame-6001 prepared-draw
address match. No child scope was unfinished or returned under a different
bucket. The 52 continuations reached without a child call are counted as
skipped call sites; they do not establish intentional culling.

| Second-path class | Bucket entries | Child calls | Packets | Backend draw callbacks |
| --- | ---: | ---: | ---: | ---: |
| Procedural models | 91 | 0 | 0 | 0 |
| Animated scene | 12 | 9 | 10 direct | 21 |
| Characters | 24 | 24 | 24 semantic | 29 |
| Vegetation | 12 | 108 | 108 semantic | 200 |
| Total | 139 | 141 | 142 | 250 |

For every character and vegetation child packet, all matching backend
callbacks had `index_count = 4 ×` the title call's `r5` argument. The
animated-scene `r5` does not satisfy that count relation. The expanded
verifier requires exact child/bucket packet-set
equality and checks the count relation by packet address; the separate
indirect verifier passed for 133 backend roots, 1,705 executions and
5,123 prepared draws:

```powershell
python tools/verify-snr01-track-bucket-join.py `
  .local/native-renderer/snr01/second-draw-final-frame-6000/title-backend-second-draw-final.log `
  --source-frame 6000 --backend-frame 6001 `
  --first-model-vtable 0x82001D74
python tools/verify-snr01-indirect-join.py `
  .local/native-renderer/snr01/second-draw-final-frame-6000/title-backend-second-draw-final.log `
  --source-frames 6000 6001 --backend-frame 6001
```

This closes packet ownership at the child-call level for the observed
second path. SNR-01 still needs the selected mesh/instance and final
transform/material identities, view-role classification, and an account
of packetless entries before Gate A can be considered.

### Character and vegetation state-record identity

In the generated character slot-41 function, the render-context
vtable-offset-124 call binds `owner + 132` immediately before its
vtable-offset-164 draw. In the vegetation function, the corresponding
binding argument comes from a loop-derived record pointer:
`record = running_40_byte_offset + *(owner + 108 + group_offset)`.
The same loop walks 12-byte count entries and 8-byte selector entries.
These are state-binding records, not verified mesh or instance objects.

Read-only hooks at `0x8245AE80` and `0x82413A0C` captured the raw binding
argument and carried it into each child draw scope. The saved sustained
race exited normally with executable SHA-256
`7146544F345D68575CFBCCB6B0F8E21577AF73D91EBDBCC2F235F434F1C454A2`.
The combined log is
`.local/native-renderer/snr01/second-bind-frame-6000/title-backend-second-bind.log`
(SHA-256 `1098335F4AC5B1F2EB487C149C4759E1F0B18EBBCEA22606B085D8C83ED0FD18`).

All 22 character child draws used the same render context as their
preceding slot-31 binding and exactly `resolved owner + 132` as the bound
record. They represented 11 distinct record addresses, each submitted
twice with a consistent count argument. All 108 vegetation child draws
used a nonzero bound record on the same context. They represented 54
distinct addresses, again each submitted twice with a consistent count.
The verifier preserves those repeated submissions, checks every bound
record against its child packet and exact backend draw, and still joins
all 140 second-path packets in this capture. The indirect verifier passed
for 133 backend roots, 1,660 executions and 4,940 prepared draws:

```powershell
python tools/verify-snr01-track-bucket-join.py `
  .local/native-renderer/snr01/second-bind-frame-6000/title-backend-second-bind.log `
  --source-frame 6000 --backend-frame 6001 `
  --first-model-vtable 0x82001D74
python tools/verify-snr01-indirect-join.py `
  .local/native-renderer/snr01/second-bind-frame-6000/title-backend-second-bind.log `
  --source-frames 6000 6001 --backend-frame 6001
```

The repeated addresses are frame-local identities only. The target of
both virtual slot-31 calls was not yet included in this capture.

### Slot-31 target identifies a state binding

The next saved sustained-race capture exited normally with executable
SHA-256
`BBA5D68CD973E2892B389D291B17C314952C10C7D53315EF20DEFD4B94318E58`.
Its combined log is
`.local/native-renderer/snr01/binding-target-frame-6000/title-backend-binding-target.log`
(SHA-256 `916F43884B82D20819BBC5DDA2F67A75ED55B30702B56CB0C551DC41CDB1F095`).
The hooks recorded the virtual target at the bind sites. All 26 character
and 108 vegetation child draws reached `0x82415CA8`. The generated
function reads fields at offsets 0 and 7 of the bound record, converts
the slot to a bit mask, and tail-calls `0x82410A70`. Existing
`discover-native-renderer-static-world-mesh-semantics.py` identifies
`0x82410A70` as the material-state binding used by the bounded
`CSimpleSubModel`/`CSimpleMesh` draw route. Its implementation updates
graphics-context state and dirty masks. This classifies the observed
slot-31 record as a **state-binding input**, not a geometry payload.

The character calls used 13 distinct records twice each; vegetation used
54 distinct records twice each. Both verifiers still passed. The
second-path capture contained 144 packets with 254 backend draw callbacks;
the indirect verifier matched 133 roots, 1,623 executions, and 4,643
prepared draws:

```powershell
python tools/verify-snr01-track-bucket-join.py `
  .local/native-renderer/snr01/binding-target-frame-6000/title-backend-binding-target.log `
  --source-frame 6000 --backend-frame 6001 `
  --first-model-vtable 0x82001D74
python tools/verify-snr01-indirect-join.py `
  .local/native-renderer/snr01/binding-target-frame-6000/title-backend-binding-target.log `
  --source-frames 6000 6001 --backend-frame 6001
```

The selected geometry and instance identities, final transforms and
material resources, view role, and packetless entries remain unresolved.
Do not infer geometry from these state-record addresses or publish mutable
guest state after frame publication. SNR-01 remains open.

### Resource-stage and decoded vertex-fetch join

A read-only hook at `0x82415C6C` now records the first-path resource-bind
target, and the prepared-draw callback reports index and vertex-fetch
descriptors without copying guest payloads. The generated render-context
vtable candidates at `0x8200306C` and `0x821451EC` both map offset 88 to
`0x82415C88`, offset 124 to the state bind above, and offset 164 to
`sub_82412DD8`. `0x82415C88` passes the resolved object to
`sub_82442528`, which writes resource fetch-state words. This is a
resource-stage bind, not a geometry-object proof.

The first saved-race replay exited normally with executable SHA-256
`10C991C6942C7FF84334BB6504E0E32EF06515E21DA206B405F985E38DC38204`.
Its combined log is
`.local/native-renderer/snr01/resource-index-frame-6000/title-backend-resource-index.log`
(SHA-256 `550275DA884BB6104C00C763B38653B49B4E861B6EE3910D0B6B690815B1D3E9`).
All 196 successful first-path resolutions reached exactly one
`0x82415C88` bind with the same object, slot and render context. The
decoded first-path, character and vegetation draws used non-indexed
primitive type 13; their index-buffer base and length were zero.
Animated-scene child draws instead used indexed primitive type 4. This
rules out an index-buffer address as the geometry identity for the other
three paths.

The next replay added a borrowed, eight-entry vertex-fetch view to the
ShiftGlue prepared-draw observation (`cf1b680`). It exited normally with
executable
SHA-256
`C77B3827C7F0A61DD9E93EE2C4A8B0E97E5D52F704CDFA0291CCCA17CD3D8320`.
The log is
`.local/native-renderer/snr01/vertex-fetch-frame-6000/title-backend-vertex-fetch.log`
(SHA-256 `387F427686CAE8E4BB662F03EC3A7C3891D3375B2CE13A9B81B3D19ABC748BC0`).
All 5,236 backend-frame-6001 draw callbacks had their declared fetch
lists captured: 8,333 fetch records total, none truncated or unmatched.

| Selected path | Packets | Backend callbacks | Fetch evidence |
| --- | ---: | ---: | --- |
| First | 208 | 256 | One nonzero fetch 95 per packet; 152 distinct signatures |
| Animated scene | 13 | 27 | One or two fetches; six distinct index-buffer bases |
| Characters | 24 | 30 | One fetch 95; 12 state records ↔ 12 fetch signatures |
| Vegetation | 80 | 135 | One fetch 95; 40 state records ↔ 40 fetch signatures |

Each character and vegetation packet had one fetch signature across all
of its backend executions. Within each class, every observed state record
mapped to one signature and each signature to one state record. The
signatures contain the decoded guest base, byte length, stride, fetch
slot and type; the verifier checks nonzero bases and lengths. This is a
frame-local **correlation**, not a proven allocation owner, mesh format,
or resource generation. A different route in this replay had one
animated-scene child call with no packet; the verifier reports it as a
packetless child while requiring exact ownership of every produced packet.
Its reason remains unclassified.

```powershell
python tools/verify-snr01-track-bucket-join.py `
  .local/native-renderer/snr01/vertex-fetch-frame-6000/title-backend-vertex-fetch.log `
  --source-frame 6000 --backend-frame 6001 `
  --first-model-vtable 0x82001D74
python tools/verify-snr01-indirect-join.py `
  .local/native-renderer/snr01/vertex-fetch-frame-6000/title-backend-vertex-fetch.log `
  --source-frames 6000 6001 --backend-frame 6001
```

The next SNR-01 join must trace these fetch bases back to title-owned
vertex allocations and selected instances, then identify final transforms
and the view role. SNR-02 must prove payload freshness before any native
scene uses these addresses.

### Fetch-register packet provenance

The next bounded replay recorded the last GPU packet to write each word of
the prepared vertex-fetch constants. D3D12 bulk register writes bypass the
single-register setter; the first probe therefore produced zero origins and
was not used as evidence. The corrected probe covers both paths. The
successful replay exited normally with 7 valid captures. Its build used root
`f5321c3`, SDK `cf1b680` plus this probe, executable SHA-256
`918DCEE1A611A062C4D13917E29F8BC0933D484605A38609252C09B604F95752`,
and D3D12 DLL SHA-256
`EDC60D88D34CA37E539F9FF39F7B80E7769B333CF227D64DAA96FA899E400659`.
The combined log is
`.local/native-renderer/snr01/fetch-origin-fixed-frame-6000/title-backend-fetch-origin.log`
(SHA-256 `CD59DBC0E8F2327CDFF85D787C38A664CCF61AA72091DDACF9AABA13C00AD592`).

Both SNR-01 verifiers passed for source frame 6000 and backend frame 6001.
Of 7,780 prepared fetch records, all had nonzero origins and both fetch words
pointed to the same setter packet and execution. In 7,620 records the setter
preceded the draw within its indirect-buffer execution; 160 reused fetch
state from a prior execution. Seven fetch records attached to source-frame
packet headers were in that carry-over group. The verifier now checks these
conditions when provenance fields exist, while accepting older captures.
This establishes the GPU register setter's packet, **not** the title object
or allocation that supplied the vertex bytes. Repeated command-buffer
execution and state carry-over remain part of SNR-01's ownership map.

### Character and vegetation title vertex descriptors

The generated `0x82415CA8` state-bind path loads a descriptor pointer from
the bound record's first word, then `0x82410A70` reads descriptor words at
offsets 24 and 28 to set the vertex fetch. A bounded read-only hook captured
those words at the existing character and vegetation bind sites. The saved
race exited normally with seven captures; executable SHA-256 was
`B3F9A03702693C27377503DD7C7993AC2EF2E90F9756BDF28C3F79EAED3A3477`.
The combined log is
`.local/native-renderer/snr01/vertex-descriptor-frame-6000/title-backend-vertex-descriptor.log`
(SHA-256 `097E084920ECE3FE4F4BC6065B99FD28FB52BBDCB9B115964786B9289AB48C01`).

For source frame 6000, 24 character calls produced 24 packets and 30 backend
fetches; 136 vegetation calls produced 136 packets and 230 backend fetches.
Every call's descriptor size word equaled its existing draw argument 6.
For every joined backend fetch 95, the title descriptor decoded exactly:
`guest_base = word24 & 0x1FFFFFFC`, `length = word28 & 0x03FFFFFC`,
and `type = word24 & 3`. The verifier asserts these equalities when the
title descriptor fields are present. This proves the selected draws use
the captured title-side fetch descriptor. It does not yet prove who owns
the referenced allocation, how long it lives, or which final instance
transform belongs to each packet. Other draw paths remain open.

### Vegetation owner-to-record join

The generated vegetation dispatch at `0x824136F0` retains its object in
`r23`, selects one of the pointer words at owner offsets 152, 156 or 160
(`r26` is 44, 48 or 52), and advances `r24` by 40 bytes per selected
record. It passes `r27 = selected pointer + r24` to the state-bind call
at `0x824139F4`. A bounded hook at that call captured those registers and
the pointer word before the original call ran.

The replay exited normally with seven captures, executable SHA-256
`5E764111540FF0216C1117A03D31F6BA2842C5803EEA5C68A860FDB429D3F9A7`.
Its combined log is
`.local/native-renderer/snr01/vegetation-owner-frame-6000/title-backend-vegetation-owner.log`
(SHA-256 `AB895054F1D9DF719DF0AEEF2B420348BC468701CBA15B452FFE9023CC2FE994`).
The route diverged from the earlier pilot controls, so this run supplies
ownership evidence only; it is not a matched performance comparison.

For source frame 6000, all 84 vegetation draw calls belonged to four
dispatch-owner objects. Every owner equaled its enclosing bucket's resolved
object; every selected record equaled the bound record and its captured
stream base plus a multiple-of-40 offset. These calls produced 84 packets
and 152 backend draw callbacks; all 152 fetch descriptors still matched
the title-side words. The verifier checks these joins, while 42 distinct
records each appeared twice in this frame. This proves the selected
vegetation owner-to-record-to-fetch route, but not the vertex allocation's
ownership or lifetime, material semantics, final transform, or whether the
three stream offsets are LODs rather than another title grouping.

### View call to track bucket and backend draw

The title's slot-75 function `0x82439B70` has one common return at
`0x8243BC74`. A default-off scope around those addresses now records the
active `CPresentationView` call and the exact bucket range produced by each
track-presentation call. The saved-race replay exited normally with seven
captures and executable SHA-256
`DCAF5223429357FBE21CFEB898B9220DCDD34ADC97B25359E002E6D79E79B7CC`.
Its combined log is
`.local/native-renderer/snr01/track-call-frame-6000/title-backend-track-call.log`
(SHA-256 `3BD68F330D0355753EF2712056B7CC8D1A7DEA5FF88FA2A1A32F1F3B0FC5A410`).

In source frame 6000, 19 slot-75 calls returned with no unfinished or
unmatched scope. Every one of 392 bucket entries fell within exactly its
recorded parent call. The resulting 324 selected packet headers joined
488 backend-frame-6001 prepared-draw callbacks; both ownership verifiers
passed. The expanded track-bucket verifier checks the view-call existence,
presenter and view identity, bucket range, packet join and target bits.

| View call / title caller return | Track calls | Buckets | Packets | Backend callbacks | Bound targets |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 / `0x823FA398` | 1 | 132 | 74 | 74 | Depth only, bit 0 |
| 2–7 / `0x8240A154` | 12 | 55 | 36 | 36 | Depth + color, bits 0–1 |
| 8 / `0x8245032C` | 6 | 205 | 214 | 378 | Depth + color, bits 0–1 |

The six middle view calls came from one title caller with distinct raw
view arguments 0, 4, 2, 1, 3 and 5, consistent with six face selections;
their camera and target identities are not yet proved. The eighth call
produced the dominant selected color/depth work and is the main-view
candidate, while the first call produced depth-only work. These are
**candidate roles** based on title scheduling and actual bound targets,
not permission to exclude the other views or suppress draws. Fifteen
eighth-view buckets in later track calls had no packet in this frame;
the reason remains to be classified. SNR-00's exact slice and SNR-01's
camera/pass proof remain open.

### View attachments and GPU-copy destinations

The prepared-draw observer now records the raw `RB_SURFACE_INFO`, four
`RB_COLOR_INFO` values and `RB_DEPTH_INFO` alongside the attachment-state
hash. The existing copy observer already had those registers; SNR-01 now
logs bounded copies when its default-off trace flag is enabled. This lets
the view-to-packet verifier's title ownership join continue through the
actual draw target and subsequent GPU copy. A dedicated log path with a
100 MiB rotation limit preserved the complete target-frame window. The
saved-race run exited normally with seven captures. Its executable SHA-256
was `ECF5309B58A4DAD1A594EA38ECBB7E3FE472E333D4936B3B46009744F0D669B5`,
the D3D12 DLL SHA-256 was
`BCE2BF101FF3AE684EE087264587CC032192DA57AF7E27FE195537FBD600A128`,
and the log is `.local/native-renderer/snr01/attachment-copy-full-runtime.log`
(SHA-256 `CDDDFE7C205BFC2CDC73A52A13E831D52CB6E7252B9BB46E96672B60CE8DA33C`).
Both prior SNR-01 ownership verifiers and
`tools/verify-snr01-attachment-copy-join.py` passed on source frame 6000
and backend frame 6001.

| View call | Joined backend draws | Raw attachment pattern | Copy relationship |
| --- | ---: | --- | --- |
| 1 | 74 | Depth only: surface `335545600`, color 0, depth `65536` | Copy 8 resolves 1280×720 |
| 2–7 | 6, 5, 5, 7, 5, 7 | Shared surface `67174720`, color 0 `196608`, depth `65664` | Each call's draws are followed by exactly one successful 256×256 copy, ordinals 11–16, to six distinct guest destinations |
| 8 | 367 | 229 draws on color 0 `196608`; 138 on color 0 `786432`; both surface `335676672`, depth `66560` | Twelve copies, ordinals 65–76, match the first raw target; none matches the second |

The six middle calls come from `sub_82409ED0`, which iterates six resource
slots and selects arguments 0, 4, 2, 1, 3 and 5. The six copy destinations
are `0x1C879000`, `0x1C979000`, `0x1C8F9000`, `0x1C8B9000`, `0x1C939000`
and `0x1C9B9000`: exactly `0x1C879000 + face × 0x40000` for those indices.
Each successful copy writes 256 KiB. This matches the independently recorded
256×256, six-face R10G10B10A2 reflection-cube allocation, base and face order
in [PERF-05](PERFORMANCE_02_05_RESULTS_2026-09-21.md). The title view call,
draw target and copy now establish these as the **reflection face producers**
for this captured allocation. The verifier asserts the ordered offsets and
size without hard-coding the base; this address can be reused or relocated.
The texture-binding join is established below; the generation and semantic
owner remain open.

View 8 remains the main-view candidate. Its two color targets and the
unmatched second target mean the final presentation and retained-pass
dependency cut are not yet established. The trace does not authorize
suppressing any view or pass.

### Reflection-cube consumers and the separate title command path

The prepared-draw observer now exposes the live shader-used texture fetches:
fetch constant, base/mip addresses, format, dimension and dimensions. A
default-off source-frame-6001 saved-race replay with a dedicated log exited
normally with seven captures. Its executable SHA-256 was
`D6CB1AEB4AE4448D72AC7E2AD5A2317697EE373E9B7A7522D647FC11FB2D8DDA`,
the D3D12 DLL SHA-256 was
`D83C0A2792BE79DCE3192442A3D39A7C0C00C380A964712FDE65289CC56F8253`,
and `.local/native-renderer/snr01/texture-consumer-view-runtime.log` has
SHA-256 `0128D11544B3FD27C35A07A0EC517FB8AB401D06EB4C4BBE8411964017CF6879`.
`tools/verify-snr01-cube-consumers.py` passed on source/backend frame 6001;
the indirect and track-bucket verifiers also passed for source frame 6001
and backend frame 6002.

In backend frame 6001, six successful 256×256 face copies (ordinals 8–13)
write `0x1C879000 + face × 0x40000` in order 0, 4, 2, 1, 3, 5. After the
sixth copy, 728 prepared draws each have one live texture fetch from base
`0x1C879000`, mip base `0x1C9F9000`, format 54
(`k_2_10_10_10_AS_16_16_16_16`), cube dimension and 256×256×6 shape.
All 728 render with depth and color to raw target `(surface 335676672,
color 0 786432, depth 66560)`. This is a direct producer-to-consumer address
join in one backend frame, not a shader-hash inference. The verifier checks
that every prepared draw's declared texture-fetch count appears in the log.

Each of those 728 draws descends from a source-frame-6001 primary packet
written at title caller return `0x829F6308`, with no queued caller. None of
their draw packet addresses belongs to a source-frame-6001 tracked view/slot-75
bucket. Static generated code shows `sub_829F5FF0` calls `sub_82409398` at
this return while interpreting a title command stream. This identifies a
separate command path, **not** its semantic scene owner. The consumers use the
same raw target tuple as some view-8 draws in the previous capture, but shared
EDRAM registers do not prove they belong to view 8. SNR-01 must recover this
path's source owner, view/camera and ordering before the proposed main-view
slice can be frozen or suppressed. SNR-05 must preserve the cube production,
mip publication and sampling dependency across that boundary.

### Deferred command worker carrying the cube consumers

Generated title code shows `sub_829F6360` calls the command interpreter
`sub_829F5FF0` at `0x829F6604` with a stream and queue pointer. Default-off
begin/end probes at that call bracket the primary packets written by the
interpreter. The final `fh1-race-sustained.fh1test` replay with
`--pinyon_shift_snr01_trace_source_frame=6000` exited normally with seven
captures. Its executable SHA-256 was
`5C67409D5BE1C242BA5D11CFA0966EFE8D24DF890094BCFE5EC8CDBBF581E7E7`.
The AppData log rotated at 5 MiB; the chronological concatenation of this
run's `runtime.4.log` through `runtime.1.log` and `runtime.log` is saved as
`.local/native-renderer/snr01/deferred-worker-final-sustained-combined.log`
(SHA-256 `3624D932D32D0C45963E27774DD89A8CED45B1AA74B3A65AF1F1E3F21F3B86A9`).
The cube-consumer verifier passed for source/backend frame 6001 with
`--allow-missing-view-trace`, requiring every consumer root to fall within a
matching worker begin/end packet range. The earlier view-trace replay passed
without that flag and found zero tracked-view packet overlap.

This capture has 728 cube-sampling draws from eight primary packet roots. All
roots were written by `sub_829F5FF0` at return `0x829F6308` under queue
`0x401600C8`, using worker streams `0xD3083004` and `0xD308313C`. The smaller
stream covered source-frame-6001 primary packet ordinals 50–55 and the larger
stream covered 56–98. The same worker probes bracketed two earlier
source-frame-6000 streams on that queue. Root count is capture-specific: a
previous worker-trace replay had ten roots and the view-trace replay had nine,
each for the same 728 fetches. Device
`0x4015D580`, entry array `0x7042FDF0`, shader-used fetch descriptor and raw
draw target agreed across the two captures.

The worker boundary identifies **where** deferred commands are interpreted,
not who enqueued them or which scene view owns them. A bounded probe at the
candidate queue-write instruction `0x829F680C` saw no events in source frames
5998–6001 and was removed; this does not rule out earlier or other enqueue
paths. SNR-01 still needs the command-stream producer and semantic camera/view
join. No main-view exclusion or native pass admission follows from this trace.

### Earlier linked-command writes near deferred streams

Static title code in `sub_82409668` has a branch at `0x82409710` that writes
an `0x81` or `0x8F` indirect command at `r29 + 4`, its payload at `r29 + 8`,
then links the block through `sub_823E6568`. A default-off probe at that write
captured the command address, payload, device, title return and active
slot-75 view scope. The first bounded window (source frames 5998–6001) logged
156 writes but no write close to the source-frame-6001 worker streams. A
separate probe of `sub_829EE338`, which copies commands to another buffer,
logged zero calls in source frames 6000–6001 and was removed.

The final probe kept the expensive draw/view trace at source frame 6000 and
extended **only** the linked-write window back to frame 5988. The
`fh1-race-sustained.fh1test` replay exited normally with seven captures. Its
executable SHA-256 was
`0C9617B055C3EB264FD0109F0D7604DF51B947DE04EA2C212A621238B6DD1110`,
and `.local/native-renderer/snr01/linked-indirect-wide-runtime.log` has
SHA-256 `FD39C40756805680017456FEB377138529DDA76799AFE3B2612CCCCB246D6358`.
It recorded 628 linked writes from title returns `0x8240CFF8`,
`0x8240D1B0` and `0x8246946C`. The cube-consumer verifier again found 728
fetches on the same resource,
device and target, this time from eight source-frame-6001 primary roots.

For comparison, subtracting `0x20000000` from the worker's virtual stream
pointer gives the alias used by the linked-write probe. The nearest preceding
recorded writes are:

| Worker source frame / stream | Nearest write source frame / opcode address | Distance before stream | Title return / opcode |
| --- | --- | ---: | --- |
| 6000 / `0xD301C084` | 5999 / `0xB301C030` | 84 bytes | `0x8240CFF8` / `0x8100000B` |
| 6000 / `0xD301C1B4` | 5999 / `0xB301C030` | 388 bytes | `0x8240CFF8` / `0x8100000B` |
| 6001 / `0xD319EA84` | 5997 / `0xB319EA44` | 64 bytes | `0x8240D1B0` / `0x81000010` |
| 6001 / `0xD319EBBC` | 5997 / `0xB319EA44` | 376 bytes | `0x8240D1B0` / `0x81000010` |

These were address and ordering **candidates**, not a command-chain or
view-owner join. The exact-command probe below supersedes this proximity
inference for the cube: these nearby linked writes are not its command words.

### Exact deferred command writer and reader join

The interpreter `sub_829F5FF0` now records the command pointer, opcode and
payload at `0x829F62F0`, immediately after loading the payload and before
calling `sub_82409398`. The primary-packet probe carries that physical
command address to backend draws. The `sub_8240D070` inline writer records
both its cached and stream-write paths with physical destination, opcode,
payload and active presentation-view call. The verifier joins each cube
consumer's primary packet to the preceding read and latest preceding write
at the **same physical command address**, then requires identical opcode and
payload. Physical addresses normalize guest aliases with `& 0x1FFFFFFF`.

The bounded `fh1-race-sustained.fh1test` replay exited normally with seven
captures. The executable SHA-256 was
`8C584AE9B3217EDA17A93BF5B4369982C7C8269C079C6F205E1A2D92F04A3EFD`;
`.local/native-renderer/snr01/exact-payload-runtime.log` SHA-256 was
`D8A692003F2300FD24F3BC6DC2A627704E01D02B699DE7A19D18BD557D61500A`.
Run `python tools/verify-snr01-cube-consumers.py <log> --source-frame 6001
--backend-frame 6001 --allow-missing-view-trace --require-command-writers`
to reproduce the join. It passed for 728 cube-sampling draws from eight
primary roots. In this capture, three distinct command words account for
those roots:

| Physical command | Cube draws | Opcode / payload | Writer |
| --- | ---: | --- | --- |
| `0x13103C04` | 414 | `0x81005739` / `0x130EDBA0` | frame 6000, inline path 1, view call 8 |
| `0x13103C0C` | 124 | `0x81007FD7` / `0x1310AE80` | frame 6000, inline path 1, view call 8 |
| `0x13103C24` | 190 | `0x81007FCB` / `0x1316AD00` | frame 6000, inline path 1, view call 8 |

All three writes occurred with presentation-view pointer `0x423CFA30`
active in call 8 and were read by the deferred worker in source frame 6001.
The track-bucket verifier independently passed for source frame 6000 and
backend frame 6001: 459 visible-list entries yielded 328 packet headers,
with zero unmatched submitted items inside a view. This capture's exact
command join places its three cube command writes inside call 8. The next
replay shows that this is not a universal scope boundary for all cube
commands. SNR-01 and Gate A remain open.

### Presentation-camera RTTI and the post-view command boundary

Read-only hooks after the title loads `view+400` and the selected context's
vtable identify the objects used in each source-frame-6000 presentation call.
The eight `view+400` objects all have vtable `0x82002F64`. The base image
`.local/ui-verify/default-image.bin` has SHA-256
`6014727FA7B0B79727FD5F32A2E2377533DC8E29679E8D2462BD764D331FA305`. Its
RTTI locator at `0x8235FEDC` names this type
`TRefCountedObjectThreadSafe<CPresentationCamera>`. Calls 1 and 8 use the
same camera object `0x2E493200`; calls 2–7 use another,
`0x2E0B0E00`. The six middle calls use the observed face argument sequence
`0, 4, 2, 1, 3, 5`, making their camera a reflection-view candidate, not a
proved semantic label. The selected-context vtable `0x8200306C` resolves
through locator `0x82351880` to
`TRefCountedObjectThreadSafe<CD3D9GraphicsDevice>`, so that pointer is the
graphics device rather than a camera.

The same sustained replay exited normally with seven captures. Executable
SHA-256:
`023ABF6CC94939163456131B7F60B87FCAB7655215FEAD0962AD84921F5FAC6E`.
`.local/native-renderer/snr01/view-object-vtable-runtime.log` SHA-256:
`1D7619A6AAB9FF8268A4F1A6AABB33EB2C7F5C7A9FCC1D59498CA75A58F05360`.
The exact-command verifier passed for all 728 cube-sampling draws from five
primary roots. This run's two cube command words show the scope boundary:

| Physical command | Cube draws | Writer location | Camera join |
| --- | ---: | --- | --- |
| `0x13087484` | 538 | frame 6000, inline path 1, inside view call 8 | `0x2E493200` via view `0x41849E30` |
| `0x130874A4` | 190 | frame 6000, inline path 1, after view call 8 returned | none inside a view scope |

Both writes were on the presentation thread in one sequential inline stream.
The second was logged ten lines after call 8's end, following three other
inline writes inside that call. The verifier still matches its exact address,
opcode and payload to the worker read in source frame 6001, but **does not
assign it to camera `0x2E493200`**. The track-bucket verifier also passed
for source frame 6000/backend frame 6001 with 461 visible-list entries,
324 packet headers and no unmatched submitted items inside a view.

The camera pointer join establishes two distinct camera objects and the
view-8 camera for in-scope command writes. The title's post-view publication
step and camera state/transform semantics remain to be traced before the
entire deferred cube path can be assigned to a view or the main camera.

### Distinct callers for in-view and post-view command refills

`sub_8240CF68` refills the device command stream and calls the inline writer
`sub_8240D070`. A default-off hook now records its immediate title caller on
each inline write. In the next normal-exit sustained replay, seven captures
were produced with executable SHA-256
`82BA4FB095D68F911AB1767E9AC86BE596CDD34CE37ACBA482266CCD23C4393E`.
`.local/native-renderer/snr01/refill-caller-runtime.log` has SHA-256
`B43785363493D146A102A7A27364E4A1010952430E0E242723683EBE1CCB0AAD`.
The cube verifier passed for 728 draws from six primary roots, and the
track-bucket verifier passed for 435 visible-list entries, 322 packet
headers and zero unmatched submitted items inside a view.

| Physical command | Cube draws | View call | Refill caller | Camera |
| --- | ---: | ---: | --- | --- |
| `0x131C6F0C` | 538 | 8 | `0x82467A88` | `0x2E486200` |
| `0x131C6F24` | 20 | 8 | `0x82467A88` | `0x2E486200` |
| `0x131C6F2C` | 170 | outside view scope | `0x824696CC` | unassigned |

Static code places `0x82467A88` in `sub_824679E8` after a buffer copy and
`0x824696CC` in `sub_82469478` after `sub_8243BEE0`. The latter function is
called directly by `sub_823F10C8` at `0x823F1454` after its render-request
loop. These are **different title call paths** to the same refill function;
the post-view command is not merely another write inside the presentation
callback. The immediate parent of `sub_823F10C8`, its relationship to view
call 8, and the command's camera ownership were left open by this capture.

### Render-thread parent of post-view publication

A bounded hook at the entry and common return of `sub_823F10C8` records
its caller on inline writes nested beneath it. The next sustained replay
exited normally with seven captures. Executable SHA-256:
`500BFEB8D546FB13E827B30D1D39ABFB94A30EF1711FAAD33C5EEADFC5148D04`.
`.local/native-renderer/snr01/render-request-caller-runtime.log` SHA-256:
`18701737EEFB870FFC3834AC78A28DF60A2D0B3C983F18E8F6040830D95A6CE1`.
The exact-command verifier passed for 728 cube-sampling draws from nine
primary roots. Its four command words divide as follows:

| Physical command | Cube draws | View call | Refill caller | Render-request caller |
| --- | ---: | ---: | --- | --- |
| `0x13246204` | 419 | 8 | `0x82413CF8` | none |
| `0x1324620C` | 119 | 8 | `0x82467A88` | none |
| `0x13246224` | 121 | 8 | `0x82413CF8` | none |
| `0x1324622C` | 69 | outside view scope | `0x824696CC` | `0x8245B870` |

The three in-view writes join camera `0x2E4B3200` through view
`0x4221FB90`; the post-view write has no active camera scope. Static title
code places `0x8245B870` in `sub_8245AEF8`, calling `sub_823F10C8`.
Base-image RTTI identifies vtable `0x82003284` as `CRenderThread` (locator
`0x822F182C`), with `sub_8245AEF8` in slot 8. Thus the post-view command
comes through the render-thread slot-8 path and then
`sub_823F10C8` → `sub_82469478` → `sub_8240CF68` →
`sub_8240D070`. This is a call-path join, not a camera or view-owner join.
The track-bucket verifier independently passed for source frame 6000 and
backend frame 6001 with 408 visible-list entries, 332 packet headers and
zero unmatched submitted items inside a view. SNR-01 still needs the
render-thread request's source view/camera relationship and a title-level
camera state/transform map before the full deferred path is owned.

### Presentation-camera matrix writers (static)

The same image's `CPresentationCamera` vtable at `0x82002F64` has 65 slots;
the next vtable begins at `0x8200306C`. The generated title functions provide
these exact writes to the camera object (`r3`):

| Vtable slot / function | Proven object writes or reads |
| --- | --- |
| 43 / `sub_82D8C820` | Copies four 16-byte vectors assembled on the stack into `camera+80` |
| 44 / `sub_82DB8190` | Copies four 16-byte vectors assembled on the stack into `camera+144` |
| 11 / `sub_82DBAFC0` | Reads floats at `+208`, `+212`, `+256`, `+260` and byte `+268`; constructs values at `+80`, stores its argument at `+12`, `camera+80` at `+8`, and sets dirty byte `+464` |
| 12 / `sub_82DB7C00` | Reads floats at `+208`, `+212`, `+240`, `+244`, `+248`, `+252` and byte `+268`; writes a 64-byte result at `+80`, stores its argument at `+12`, and sets `+8` and dirty byte `+464` to one |
| 8, 14, 17 | Store an argument at `+8` or floats at `+260` / `+256`, respectively, and set dirty byte `+464` |

Slots 2 and 3 change a refcount at `+496`; slots 62–64 delegate to
`sub_823F8848`, with two of them also calling helpers on `camera+272`.
These are field and call facts, not yet a projection/view/world-transform
semantic map. In particular, slot 12 uses separate branches for its byte
`+268` and argument, so a single assumed matrix convention would be unsafe.
The next bounded runtime probe should record slots 11/12/43/44 and their
camera object pointers around the eight view calls, then join the observed
state to the render-thread request and submitted matrix bindings.

### Live camera-method and view-state join

Default-off hooks at slots 11/12/43/44 and the existing view scope produced
two normal-exit sustained-race replays with seven captures each. The second
build's executable SHA-256 was
`30531EE26E6B40E34BA97D5AF15BF7E73F4225B282AC167E1437A0E408E8565D`;
`.local/native-renderer/snr01/camera-method-run-b.log` SHA-256 was
`1B909F52A1AAB090E7B7B1CD2D962FBDC641358A52FC22B961A0328AE20629A7`.
The new `tools/verify-snr01-camera-view-join.py` passes for source frame 6000.

In that frame, view calls 1 and 8 use camera `0x2E4B6200`; calls 2–7 use
camera `0x2E0B0E00`. Slot 11 runs 14 times on the first camera before the
view calls; slots 12 and 43 have no calls in this frame. Slot 44 runs once
inside every view call on its associated camera. The 64-byte region at
`camera+80` has a stable hash within every call. The `camera+144` hash stays
stable in calls 1 and 8, but changes during each of calls 2–7. Each middle
call's exit hash is the next call's entry hash. Thus the six face calls
successively update one live camera's second matrix region; they are not six
independent camera objects. This does **not** yet identify the matrix's
coordinate convention or prove main-view pass semantics.

The same frame writes one command at `0x130FE12C` after view call 8 returns,
via render-request caller `0x8245B870`, with no active view scope. Its camera
ownership remains unassigned. The track-bucket verifier passed: 441 visible
entries, 353 packet headers and zero unmatched submissions inside a view.
The cube-consumer verifier passed for 728 draws when invoked with primary
packet frame 6001 and backend frame 6001; its three consumer command writers
were in view call 8 in source frame 6000. Using source frame 6000 for that
verifier fails because the observed primary packets in this replay carry
frame 6001. This timing-dependent frame label must not be hidden by claiming
the separate post-view command has a cube consumer or camera join.

The exact post-view command is **consumed**, despite having no view scope.
The extended camera/view verifier joins its single frame-6000 writer at
`0x130FE12C` (opcode `0x810012CD`, payload `0x13186700`) to three deferred
reads and three primary packet roots in frame 6001. Each root produces ten
prepared draw callbacks: 30 callbacks from ten unique draw packet addresses.
Nine of those ten addresses have a frame-6000 direct-packet record with
`direct_call=0`, outside the instrumented direct-call scope. Their output
uses the same observed surface/depth words as other scene draws; 21 callbacks
have color word `0xC0000` and nine have `0x30000`. Neither target similarity
nor temporal adjacency assigns those packets to camera `0x2E4B6200`. SNR-01
must recover the upstream owner of the ten packets or explicitly exclude
them from the frozen slice with a proved pass/dependency boundary.

### Post-view draw writers and variable downstream work

An entry/exit scope around title function `sub_8240DC70` now attaches its
immediate caller to its direct-packet writes. In a normal-exit, seven-capture
replay, executable SHA-256
`26CD009EC6BF928392D1ABF53251FEC99A61A5F45E693B981420E5F1942954C8`,
`.local/native-renderer/snr01/indexed2-caller-run-a.log` SHA-256
`000010C4D4077A715DDEA3CE85C5FB3306CC9AAB69CEE432FCADBD3841BFA153`,
the post-view command `0x130E912C` again has three deferred reads and three
primary roots. This time they produce **231** prepared draw callbacks from
187 unique packet addresses, not the prior run's 30 from ten. Nine of the
187 addresses have a source-frame-6000 `indexed2_secondary` direct-packet
record outside the known direct-call scope. Seven record caller `0x82D07200`,
one records `0x82D0735C`, and one records `0x8244F070`.

The verified base image places `sub_82D06C28`, containing the first two call
sites, in slot 3 of vtable `0x82236214`. Its complete-object locator
`0x823586E4` names `CStandardParticleRenderer`. This proves those eight
packet writes passed through a particle-renderer method; it does not classify
all 231 callbacks under the same deferred root as particle draws.
`0x8244F070` is in `sub_8244E938`; its owner remains unidentified.

A second normal-exit, seven-capture replay after adding two read-only
secondary-object guard bytes used executable SHA-256
`19B959AD6F8E07D5158C82E2E1C7A9E7A6CF1072B609BB96992E9811DAC8524D`.
`.local/native-renderer/snr01/secondary-guard-run-a.log` SHA-256 was
`7246C0747A0185D163D55976F34E90DBA158DD7C1047C811ED1443C57DB3C1CC`.
Its post-view root produced 228 callbacks from 154 packet addresses, with
12 indexed2 direct-packet records: ten from caller `0x82D07200` and one
each from `0x82D0735C` and `0x8244F070`. The generalized camera/view
verifier passes on all three captures, checking the exact command-write,
deferred-read, primary-root and prepared-draw relationships without assuming
a fixed draw count. All observed post-view callbacks still use surface word
`0x14020500`, depth word `0x10400` and color word `0xC0000` or `0x30000`.

The track-bucket verifier passed on the last replay with 442 entries, 342
packet headers and zero unmatched in-view submissions. It failed on the
previous replay because one of 142 secondary entries had no recorded virtual
dispatch and no packet. Static `sub_8243BD40` checks bytes `+52` and `+55`
before dispatch. In the later replay all 141 dispatched secondary entries
had nonzero `+52` and zero `+55`, but the missing entry did not recur, so its
cause is **unproved**. Do not weaken the verifier to count that earlier gap
as intentional culling. SNR-01 still needs the remaining post-view packet
owners and a proven main-view/dependency boundary.

### Title owner of one packet consumed after the view

The title's `sub_82444E60` calls `sub_823E2DE0` at `0x82446160`
(return address `0x82446164`). That wrapper derives subobject and array
pointers from its input and tail-calls `sub_8244E938`, which writes an
`indexed2_secondary` packet at `0x8244F070`. This static path prompted a
default-off, read-only entry probe at `0x8244E93C`; the probe records its
caller, receiver, arguments and active presentation-view call. It does not
interpret the receiver's first word as a vtable or identify a mesh.

The rebuilt executable SHA-256 was
`F2CE5C3D1B2E5CB27EB61113F1D0F3149C0A753DB7442FFBEF528A8F871EE22A`.
The normal-exit sustained race produced seven PPM captures; log
`.local/native-renderer/snr01/indexed2-owner-run-a.log` SHA-256 was
`0533E4AE29C4115E72A523A84FC9387D6DDD76EEEB13B88CD5CCAD34AE2CEAD3`.
At source frame 6000, the probe recorded exactly one matching call:
caller LR `0x82446164`, receiver `0x43061870`, argument 5/view
`0x4248F600`, and active view call 8. The `0x8244F070` direct packet at
physical `0x12ED7F1C` followed on the same thread before view call 8 ended.
The later command at `0x13244F2C` was written **after** that view ended and
read in frame 6001. Its three roots produced 229 prepared draw callbacks
from 185 unique packet addresses; one of those addresses was the title
packet just identified. Thus command publication outside a view does not
imply every packet it consumes was produced outside that view.

`tools/verify-snr01-camera-view-join.py` now asserts this ordered
view → title call → packet → deferred-command consumer join when the new
probe is present, while retaining compatibility with older captures. It
passes this replay and the earlier secondary-guard replay. The track-bucket
verifier passes on this replay (360 entries, 266 packet headers, zero
unmatched in-view submissions), as does the cube-consumer verifier (728
draws, four command writers). The other eight directly observed post-view
packet writes still pass `CStandardParticleRenderer`; most of the 185 packet
addresses under the deferred roots lack an indexed2 direct-packet record.
The selected scene slice and any main-view dependency boundary remain
unproved, so SNR-00, SNR-01 and Gate A remain open.

### Deferred packet address recurrence

The camera/view verifier now compares the post-view root's distinct prepared
draw packet addresses in backend frame 6001 with prepared draws in backend
frames 5999 and 6000, then reports which newly observed addresses have a
source-frame direct, semantic or indexed write. Four earlier captures had an
exact new-address/direct-write match:

| Replay | Post-view addresses | Seen in prior frames | New direct records |
| --- | ---: | ---: | ---: |
| `camera-method-run-b` | 10 | 1 | 9 |
| `indexed2-caller-run-a` | 187 | 178 | 9 |
| `secondary-guard-run-a` | 154 | 142 | 12 |
| `indexed2-owner-run-a` | 185 | 176 | 9 |

In the last replay, all 176 recurring addresses occur in **each** of backend
frames 5999 and 6000. Their captured draw metadata matches frame 6001 at each
address: vertex/pixel shader IDs, index count/type/base/length, primitive type,
and vertex/texture fetch counts. These are recurrent prepared packet addresses,
not 176 source-frame-6000 writes missing from the direct-packet hook. The
addresses are absent from other frame-6001 command roots. Their earlier title
owners and allocation generations remain unknown; stable addresses and draw
metadata do not prove stable buffer contents or a main-view pass boundary.
The next ownership probe should follow the title references to these resident
command buffers, then check their resource generations before any suppression.

A separate normal-exit replay moved the bounded title probe to source frame
5999 without rebuilding (the executable SHA-256 remained
`F2CE5C3D1B2E5CB27EB61113F1D0F3149C0A753DB7442FFBEF528A8F871EE22A`).
It produced seven PPM captures; log
`.local/native-renderer/snr01/resident-origin-5999-run-a.log` SHA-256 was
`E0020B75C476F1B3EF74A32AC6F18353C89FD158D3AFD1B1CD7258C2B5EDD9B5`.
Its post-view command consumed 31 unique packet addresses in backend frame
6000: 23 had already appeared in backend frames 5998/5999 with the same
captured draw metadata, and the other eight exactly matched source-frame-5999
direct writes. The title owner probe again joined one direct packet to view
call 8. The camera/view, track-bucket (351 entries, 281 headers, zero
unmatched in-view submissions) and cube-consumer (728 draws, four writers)
verifiers passed. Moving the probe one frame earlier therefore did not find
the first writes of the recurring packets. The population also varied from
the 185-address source-frame-6000 capture, so addresses must be compared
within each replay, not across launches. A targeted memory-write watch on
known resident command pages is the next way to test mutation; it would not
by itself identify the original title allocator or render owner.

### Full-route survey of known packet writers

A default-off survey now observes the existing semantic and direct PM4 header
writer hooks throughout the replay, independently of the single-frame trace.
It restricts logging to physical ranges `[0x14000000,0x16000000)` and
`[0x17000000,0x18000000)`, with an 8,192-event cap per title thread. The
initial broader `[0x14000000,0x18000000)` attempt hit that cap in the
unrelated `0x16E…` primary-packet pool by source frame about 1830, so it
cannot establish anything about later resident packets. The filter change
excluded that pool. Survey activation is now logged explicitly.

The final filtered build's executable SHA-256 was
`3F346F83C3278B8A01DDEC792D233E391B6084A1051F423FBCA30D79614F06DC`.
Its normal-exit seven-capture log
`.local/native-renderer/snr01/resident-writers-run-c.log` SHA-256 was
`06968CEDCC1CB63EA5FDAE07A34E308F078F3FD440FCF7AA2AA9D589BDD4A28B`.
The activation marker confirms the two ranges and cap. The post-view root
consumed 70 distinct packet addresses, 62 of them also prepared in the two
preceding backend frames. **All 62 recurring addresses lie in the surveyed
ranges, and the complete replay logged zero writes from the hooked semantic
and direct packet producers in those ranges.** The other eight addresses
exactly matched source-frame direct writes. The camera/view verifier passes
and reports the survey coverage. The track-bucket verifier passed with 478
entries, 324 headers and zero unmatched in-view submissions; the cube
consumer verifier passed with 728 draws and four command writers.

Two preceding survey replays also exposed a valid packet mix that the old
camera/view verifier rejected. Their post-view roots had 245 and 248 unique
addresses; 206 in each had appeared in prior backend frames. The newly seen
addresses split into 38/39 direct writes and 1/3 semantic writes, all matched
exactly with no remaining unexplained new address. Of the direct writes,
27/29 occurred within the existing direct-emitter scope, while 11/10 used
the indexed2 path outside it. The semantic writes record emitter caller
`0x82412E1C` in `sub_82412DD8`. The verifier now accepts both known direct
paths, counts semantic/indexed writers, and reports any genuinely uncovered
new address instead of assuming all post-view writes follow indexed2.

The zero-hit resident survey excludes **only** the hooked packet producers
in its ranges during this replay. It does not prove no guest write occurred:
another title writer, a loaded/prebuilt stream, GPU production or earlier
allocation could supply the recurring packets. Stable packet addresses and
draw metadata still do not establish byte freshness or owner identity.
SNR-01/02 need a write/freshness observation on these known pages and a
title reference back to their allocator or scene owner before this portion
of the proposed main-view slice can be claimed or suppressed.

### Sampled bytes of recurring draw packets

The prepared-draw observer now hashes the bounded PM4 draw packet bytes at
the backend callback. It reads from the observed physical packet address to
the draw end, or to the command-buffer end when the draw-end offset is zero;
it rejects out-of-bounds spans and limits the sample to 32 bytes. This is a
diagnostic sample at draw preparation, not a guest-memory write watch or a
resource-generation rule.

The rebuilt executable SHA-256 was
`22D8268E6331BF6BFE5595C7845E1D4AB74079A26F7815DA48A95619FAA6CB7C`.
The sustained race exited normally with seven PPM captures; log
`.local/native-renderer/snr01/packet-byte-hashes-run-a.log` SHA-256 was
`1A7935F6A3E9A3EBDF52ECBD000AFAA04B1058ADA01B7749D2D134106C8FD9DF`.
All 14,912 traced prepared draws had a valid nonzero packet span (8, 12 or
20 bytes), and no frame/packet-address pair had conflicting sampled hashes.
The post-view root consumed 249 unique packet addresses; 206 occurred in
prior backend frames and **all 206 had matching packet byte lengths and
hashes** between those frames and backend frame 6001. The other 43 newly
observed addresses matched 40 source-frame direct writes and three semantic
writes. The generalized camera/view verifier passed with zero uncovered new
addresses. The track-bucket verifier passed with 455 entries, 334 packet
headers and zero unmatched in-view submissions; the cube-consumer verifier
passed for 728 draws and three command writers.

The byte samples make repeated PM4 draw-packet identity stronger than address
and shader-metadata recurrence alone. They do not cover referenced vertex,
index or texture bytes, prove that no write happened between samples, or name
the title owner of the resident stream. SNR-01/02 and Gate A remain open.

### Guest write watch on recurring packet pages

The next default-off probe uses ReXGlue's existing physical-memory access and
invalidation callbacks. On the first prepared draw at backend frame 5999, it
arms the packet header's physical page (only the two surveyed resident ranges,
up to 1,024 pages). It records later guest accesses and write invalidations
through frame 6001. The callback limits unwatching to the faulting range so
another cache's wider invalidation cannot silently disarm neighboring watched
pages. This is a one-shot page observation, not an exact-byte watch.

The replay build's executable SHA-256 was
`EA64056C48AAFA9F4D8E38E7B6F20EBD710049E5782A4429E8DD24264AE891BC`.
Its seven-capture, normal-exit sustained-race log
`.local/native-renderer/snr01/packet-page-watch-run-b.log` SHA-256 was
`5024F5CD23AFAEBF46F544E68CA178BCB2051C3423D79BC39CFC850EB8A2C156`.
The probe armed 730 distinct pages in frame 5999. The frame-6000 post-view
command consumed 192 unique draw packet addresses in backend frame 6001;
183 were recurring. **All 183 recurring addresses lay on 99 armed pages, and
none of those pages generated a guest access or invalidation notification**
between arming and the end of the observed window. All 183 recurring packet
byte hashes matched the preceding frames. The nine newly seen addresses
matched title direct-packet writes. The camera/view verifier reports this
coverage; track-bucket and cube-consumer verifiers also pass with their
documented frame selections.

The first version of the probe, before narrowing the callback unwatch range,
recorded two guest writes to other packet pages, neither used by its 147
recurring post-view addresses. That replay is useful as a callback activation
check but not the strongest no-write claim, since wider cache invalidation
could unwatch adjacent pages. The final replay has no such notifications.

This excludes observed guest CPU writes to those armed physical pages during
this three-frame window. It does not establish when or by whom the resident
streams were originally built, exclude host writes that bypass this callback,
prove referenced geometry and textures stayed unchanged, or extend the result
to other gameplay frames. SNR-01/02 and Gate A remain open. The next title-side
join must identify the owner of these resident command buffers and the
resource generations they reference before the proposed slice can be frozen.

### Render-thread request boundary after the presentation views

The next read-only hook brackets `CRenderThread` slot 8 at
`sub_8245AEF8`, recording the render-thread object, mode argument and
request pointer. Static generated code confirms the common return at
`0x8245BB7C`; the existing post-view path calls `sub_823F10C8` from this
slot at return `0x8245B870`. This tests whether that path shares the same
request scope as the eight presentation-view calls.

The sustained-race replay exited normally with seven captures. Its
executable SHA-256 was
`C93E989478209E3623A9AC7C809E4F53043CE20C7CFB358CB85E73693EE14A79`;
`.local/native-renderer/snr01/render-request-join-run-a.log` SHA-256 was
`4F4A805A6188EECFF177C6AB34975DA0182003564AE80573FBF8179463920C18`.
All eight source-frame-6000 presentation-view calls ended **before** the
observed slot-8 request began. The post-view inline command at physical
`0x1329FAAC` was published within that request on the same title thread.
The request used mode `1`, request pointer `0`, and render-thread object
`0x40159510`; it enclosed no presentation-view call. Later slot-8 calls on
the same object used modes 5, 2 and 4, with null request pointers.

`tools/verify-snr01-camera-view-join.py` now checks this nesting when the
slot-8 trace is present while accepting older captures without it. The
post-view command led to three primary roots and 84 prepared draws from 38
unique packet addresses in this replay; 28 recurred from prior backend
frames and ten matched source-frame direct writes. The track-bucket verifier
again found zero unmatched in-view submissions, and the cube-consumer
verifier passed for 728 draws.

This identifies the post-view publication as a later render-thread mode-1
operation. It does not make that operation a semantic scene owner or carry
the earlier camera into it. SNR-01 must recover the producer and owner of
the resident indirect buffers and the state read by the deferred command
before assigning the post-view draws to the proposed main-view slice.

### Title scene list to child indirect-buffer execution

Static generated code shows `sub_82416A00` retaining its list argument in
`r24` and writing child PM4 indirect packets from that list. The existing
scene-dump hook at `0x82416F18` now records the physical packet header,
target buffer, word count, list object, immediate caller and active view
call in the bounded SNR-01 trace. The backend indirect observer reports the
same header/target pair when executing each child buffer. This join uses
exact addresses and does not infer an owner from a shader or packet range.

The first normal-exit, seven-capture replay used executable SHA-256
`2DFE2783DC1AF1A3F0FA21CD730782354CC0E1365CD1D00091928ACFAF8603A5`;
`.local/native-renderer/snr01/scene-indirect-run-a.log` SHA-256 was
`DFE09ED3A87F40CF5B765FA8B85D67C060958C4C642A5A73F5D44A78F11B014C`.
It recorded 1,069 scene-list child packet pairs in source frame 6000. In
backend frame 6001, 1,395 of 1,410 child indirect executions matched one
of those pairs. The post-view command produced 84 draws: all 54 draws in
child buffers matched list packets emitted inside view call 8, while 30
draws were direct in the later root buffer.

A second normal-exit, seven-capture replay added an entry/exit scope around
`sub_82416A00` to retain its immediate caller. Executable SHA-256 was
`861E592B2EE178164942D56C2C8E14E36E876F210BB37AA1FB29339B370962A1`;
`.local/native-renderer/snr01/scene-indirect-caller-run-a.log` SHA-256 was
`5D016502E10172E7BF754C384D6E42BDBBD594878F11242BC940CC51765F7D17`.
Of 1,490 backend-6001 child executions, 1,475 exactly matched source-frame
scene-list packets. Its post-view command had 38 draws: all five nested
draws matched two list objects emitted inside view call 8, with immediate
caller `0x82416898` (`sub_824167F8`); 33 draws were direct in the root
buffer. Across all scene-list packets, 1,147 used that caller and 49 used
`0x8246E930` (`sub_8246E8F8`). Fifteen child executions did not match this
writer in either capture and remain a separate producer path.

The camera/view verifier now requires the exact scene-list join for every
post-view nested draw when the title scene trace is present and reports the
unmatched child-execution count separately. Track-bucket and cube-consumer
verifiers also pass for the second replay (zero unmatched in-view submitted
items; 728 cube-sampling draws).

This identifies the title **command-list object** that submitted the
resident child buffer in these captures. It is not yet the semantic mesh,
material or view owner of each draw, and it does not classify the direct
root-buffer draws or the 15 other child executions. Follow the callers of
`sub_824167F8` back to the scene object and map each list entry to its
resource generation before SNR-01/02 or Gate A can close.

### Car owner above the scene-list flush

`sub_824167F8` is the immediate caller of most `sub_82416A00` list
emissions. A read-only scope at its entry and common return now carries its
own caller onto the exact scene-indirect packet record. In a normal-exit
seven-capture replay (executable SHA-256
`173D824022FE2DACFDC98E6B4702816555DF69E8CCF46D4D30FEC99061439CBF`;
`.local/native-renderer/snr01/flush-caller-run-a.log` SHA-256
`BB56A6EC986E9E80CA4B56754BB10A14C4D6153114FB0B2980B7F569CE80172F`),
the post-view command had 180 prepared draws: all 156
draws in child buffers matched view-8 scene-list packets; 24 drew directly
in the later root buffer. The 156 nested draws split by flush caller into
`0x8243CE0C` (113), `0x8241A2A4` (28), `0x824399F0` (12), and
`0x824170BC` (3). These return sites belong to `sub_8243CDC0`,
`sub_82419A30`, `sub_82439960`, and `sub_82417060`, respectively.

The next replay captured the object retained by each of those four caller
functions. Static generated code retains entry `r3` in `r31` for the
`0x8243CE0C`, `0x824399F0` and `0x824170BC` paths, and in `r30` for
`0x8241A2A4`; those are the registers observed at the flush call. This
normal-exit replay used executable SHA-256
`79C5FEE10B510B98C8941D3ACE26A14D4CEACD9ADB97AB6A02026A7A14DF052E`;
`.local/native-renderer/snr01/flush-owner-run-a.log` SHA-256 was
`78628A0D0E57F8B2110093C49CB4EDE239BCD4157C42F67D77FE7D918C258B32`.
It produced seven captures. All 132 nested post-view draws joined exactly
to scene-list packets from view call 8; 27 draws were direct in the root
buffer. The nested draws used 54 list objects under nine retained owners.

The first word of the retained owner is `0x82003A54` for 97 draws through
`sub_8243CDC0`, and `0x82001618` for 32 draws through `sub_82439960`
and `sub_82419A30`. The verified base image
(SHA-256 `6014727FA7B0B79727FD5F32A2E2377533DC8E29679E8D2462BD764D331FA305`)
resolves these vtables through RTTI locators `0x823631DC` and
`0x8235E204` to `CCarPresentation` (inside a thread-safe ref-counted
wrapper) and `CCarModel`, respectively. The remaining three draws came
through `sub_82417060`; their owner's first word is `0xBF283F61`, not a
vtable, so that state pointer remains untyped.

The camera/view verifier reports exact scene-list joins, flush callers and
owner first words when these fields are present. It passes this replay;
the track-bucket verifier reports zero unmatched in-view submitted items,
and the cube-consumer verifier passes for 728 draws. These results prove
car-related title owners for the nested post-view packets in this window.
They do not distinguish player from traffic cars, classify the 27 direct
root-buffer draws, map car materials/geometry or prove resource freshness.
Those remaining joins are required before SNR-01/02 and Gate A can close.

### Vehicle-pose object is audio, not the draw owner

A second read-only hook immediately after the existing `0x82BC5A3C`
vehicle-pose hook records its retained `r31` object for source frame 6000.
The saved sustained-race route exited normally with seven captures using
executable SHA-256
`738B094BE4A90EF44F794E9B8D3AEACAF43C1B40F906297D54574A5789C572F3`.
The session log at
`.local/native-renderer/snr01/pose-owner-run-e-full.log` (SHA-256
`915F79C1D0C686689385E1143324C657C5EF01D8D433C2FB2A7FC0D796BA1AF1`)
was reconstructed in time order from that session's `runtime.5.log` through
`runtime.log` rotating-file segments; the initial segment starts at its
`20260922T165454Z-p36708` session marker. The camera/view verifier passes.
The cube-consumer verifier also passes for 728 draws. The track-bucket
verifier's `dispatched == expected` assertion fails in this particular
replay, so it is not used as independent track-coverage evidence.

The pose hook recorded 48 calls on eight distinct `r31` objects. Their
first word was always `0x8213BA54`; the verified base image resolves its
RTTI locator `0x8234F824` and type descriptor `0x832A183C` to a
thread-safe `CCarAudio` wrapper. Generated `sub_82BC5870` retains entry
`r3` in `r31`; its caller `sub_82BC8410` passes that audio object while
passing a stack argument through `r4`, explaining the common `r30` source
pointer. In the same frame, 564 view-8 scene-list packets carried 17
distinct nonzero flush-owner pointers. None equalled any of the eight pose
objects. The post-view command contained 78 prepared draws: all 51 nested
draws joined exactly to view-8 scene lists, with 27 direct root-buffer
draws still unclassified. The 51 nested draws used `CCarPresentation`
(`0x82003A54`, 32 draws), `CCarModel` (`0x82001618`, 16 draws), and the
untyped state pointer (3 draws).

The vehicle-pose hook is therefore a verified car-audio update boundary,
not a direct player/traffic label for rendered car instances. Identifying
the player requires a title relationship from player state to
`CCarPresentation`/`CCarModel`, or a separately proven instance identity;
pointer equality with the pose object is insufficient. The verifier now
checks the audio vtable and reports distinct pose owners and overlap with
view-8 flush owners when the probe is present. SNR-01 and Gate A remain open.

The existing static player-ingress discovery was rerun against the same
verified base image and generated title functions. Its local result at
`.local/native-renderer/snr01/player-ingress-static.json` (SHA-256
`94ABDCA2F8D670CE13EA18B505610A790AFBD790742CD02E96A8E7E1246C67ED`)
verifies `CMapEntityVehiclePlayerLocal` vtable `0x8201D380`, distinct
from the AI/traffic map-entity types, and a vehicle ID getter at
`0x82BBA010` reading receiver offset 12. This is an exact semantic
*ingress* for player identity, but its own contract marks the runtime join
as required. The next probe must carry that map-entity identity into the
car presentation/model instance before any post-view draw can be called
the player's.

### Shared vehicle-ID getter call is a track/procedural path

The apparent nearby bridge at `sub_8243DF70` calls `sub_82BBA010` at
return site `0x8243E548`. A bounded read-only probe recorded the getter
receiver, returned word and enclosing `r31` object from the start of the
saved sustained-race route through source frame 6000. The normal-exit,
seven-capture run used executable SHA-256
`C3E66697DD5C9B50A3345FBCE16BE14FDA3AEAAA7942F1A1C75D5D06E578C609`;
the isolated session log at
`.local/native-renderer/snr01/entity-id-run-b.log` has SHA-256
`02D4AE79C5AF62A2E565DA87FBA6A993B83943CCA1EC8E855812FC975EE8B605`.
The camera/view verifier passes, with all 228 nested post-view draws
joining exactly to view-8 scene lists.

All 25 observed getter receivers, spanning source frames 1588–4086,
had vtable `0x820029FC`, which resolves through base-image RTTI to
`proceduralGeometry::CProceduralAnimatedScene`. Every enclosing object
was the same pointer with vtable `0x82003CCC`, resolved as
`CTrackPresentation`. No receiver had the `CMapEntityVehiclePlayerLocal`
vtable `0x8201D380`, and neither receiver nor enclosing pointer matched
any of the 17 nonzero view-8 car flush owners in frame 6000. The
returned `+12` words were pointer-shaped, not demonstrated vehicle IDs.
`sub_82BBA010` is reused outside the map-entity vtable: a call to it
alone cannot label a car. The temporary probe was removed after this
negative result; the direct map-entity pool path remains the next
semantic ingress to trace.

### Player-local pool remains unassigned in the race

The verified installer store at `0x826291A8` was observed read-only and
its pool pointer retained by the host only while the SNR-01 trace option
is enabled. The pool constructor embeds the sole
`CMapEntityVehiclePlayerLocal` at pool offset 32. Two pools were installed
during the saved route, at source frames 1420 and 3981. Both construction
records had player vtable `0x8201D380` and vehicle ID `0xFFFFFFFF`.

At the end of view call 8 in source frame 6000, the current pool was
`0x41E4FFF0` and the player-local entity was `0x41E50010`, still with
vehicle ID `0xFFFFFFFF`. No call to the verified ID setter `0x82CCF228`
targeted that entity during the run. Its pointer-like fields at offsets
72, 76 and 84 were all null. Neither the pool, player entity nor pool
context `0x2E026A10` equalled any of the 17 nonzero view-8 scene-list
flush owners. The normal-exit run produced seven captures with executable
SHA-256
`1DE67D621A3BD2E99885246DCBF61D75D6F63ACE1B6BC1A0FD21BAF8BE593A0B`;
`.local/native-renderer/snr01/player-links-run-a.log` has SHA-256
`82C4B010BD2A1CBABDAB7DCC6A39148EF5584E89597A138A104B090DCDB677F8`.

`tools/verify-snr01-player-pool.py` locks the two installer observations,
the exact player-local vtable, unassigned ID, absence of setter calls and
null direct links. The cube-consumer verifier passes for 728 draws. The
camera/view verifier reached its direct-packet classification assertion
in this replay, so this run is not used as fresh proof of the already
established full camera join. This proves an authoritative player semantic
object exists in the route, but it is a dormant map-entity slot rather
than the live player render identity. A different player-state boundary
must supply the `CCarPresentation`/`CCarModel` relationship; SNR-01 and
Gate A remain open.

### Live player state identifies the local `CCar`

The `Forza2::CPlayer` constructor at `0x8256D770` was observed while the
existing SNR-01 trace option was enabled. A normal-exit sustained-race replay
at source frame 6000 produced seven captures with executable SHA-256
`876E6F63604ACA4261916EEBEB6FBA76AB992B77C51F0CB4DD3E627D0012845D`.
The isolated session log at
`.local/native-renderer/snr01/local-player-presentation-run-a.log` has
SHA-256
`367D287BF529025752314336EFD5EE9681991B299FADE3D8F74C90E11D41F236`.
`tools/verify-snr01-player-presentation.py` passes on that log.

Eight surviving objects had exact `Forza2::CPlayer` vtable `0x8201EB4C`.
Every player held a `CCar` (`0x8200C29C`) at offset 160. Exactly one player
also held a `Forza2::CForzaProfile` (`0x82014510`) at offset 164. In this
single-player saved route, the profile-bearing player supplies the first
verified semantic local-player identity and its offset-160 field supplies the
corresponding live `CCar`. This corrects the earlier provisional reading of
those two fields; RTTI from the verified base image is authoritative.

The `CCarPresentation` constructor at `0x82DE7638` was observed in the same
run. Eight surviving instances had exact vtable `0x82003A54`, and every one
was also a nonzero view-8 scene-list flush owner. All eight were constructed
from the same argument object with vtable `0x82001BF4`, which RTTI identifies
as the thread-safe `CPresentationType` wrapper. The constructor argument is a
shared type descriptor rather than a vehicle identity.

A bounded diagnostic checked all aligned words in the proven 17,828-byte
local `CCar` layout for exact view-8 flush-owner pointers and all aligned
words in each 6,640-byte `CCarPresentation` for the exact local-car pointer.
Both directions produced zero matches and the temporary scans were removed.
The durable probes retain only player construction, presentation construction
and view-8 owner membership. SNR-01 now has a verified local-player-to-`CCar`
edge and verified car-presentation draw owners, but still needs the title
method or registration boundary that associates that `CCar` with one of the
eight presentations/models before Gate A can close.

### The local `CCar` and its draw-owning presentation share livery identity

A follow-up normal-exit sustained-race replay at source frame 6000 produced
seven captures with executable SHA-256
`1692FAFAAF184DBBA8EC0325864EDDF5EE2409E443B1B9C8DA542FBB93DA9A49`.
The isolated session log at
`.local/native-renderer/snr01/local-car-shared-pointer-run-d.log` has SHA-256
`40A8449ABD295AA74D526823E12A92A2215325398C07C67DA8077F440E5EA289`.
`tools/verify-snr01-player-presentation.py --require-local-presentation`
passes on that log.

The profile-bearing `Forza2::CPlayer` again selected one live `CCar`. A bounded
read-only comparison of aligned fields found that car's offset-12292 pointer in
exactly one of the eight surviving `CCarPresentation` objects, at offset 2800.
The shared object's exact vtable is `0x8222F4A4`; RTTI in the verified base image
identifies it as `CCarLiveryResource`. No approximate address, pose or spatial
catalogue match participates in this association. The durable trace now checks
only these two proved fields and logs the unique match.

The associated presentation had exact vtable `0x82003A54`, was a view-8 flush
owner, and emitted 12 distinct view-8 scene indirect buffers through the same
`0x8243CE0C` presentation flush return site. Those buffers contained 17,070 PM4
words in total and retained the previously proved scene-list-to-prepared-draw
lineage. This closes the missing semantic local-player `CCar` →
`CCarLiveryResource` → `CCarPresentation` → view-8 submission-owner edge. SNR-01
still requires complete selected-slice accounting, mesh/instance ownership and
explicit culling classification before its acceptance condition can be marked
complete.

### The local presentation supplies the exact `CCarModel` owner

Generated `sub_82437218` retains entry `r3` as the `CCarPresentation` in
`r31`. Its model paths load `r3` from offset 5648 before calling
`sub_82439960` or `sub_82419A30`; those functions retain entry `r3` as the
scene-list flush owner. This is the same static path whose runtime owner vtable
was previously resolved to `CCarModel`, so no object scan or address heuristic
is needed.

A normal-exit sustained-race replay at source frame 6000 produced seven
captures with executable SHA-256
`8B7CCCDD3EB383D1E3B0ECB146643A1F51ED0507AD35DCB1A9864961D3E6C43B`.
The isolated session log at
`.local/native-renderer/snr01/local-car-model-run-a.log` has SHA-256
`39ED26AF6B53CF2DF65B7C89994DFB88BC7606EA9A0836D6FE738DF9832F431A`.
`tools/verify-snr01-player-presentation.py --require-local-model` passes.

The unique local `CCarPresentation` held a nonzero object at offset 5648 with
exact `CCarModel` vtable `0x82001618`. That same pointer owned 37 distinct
view-8 scene buffers: 29 returned through `0x824399F0` in `sub_82439960` and
eight through `0x8241A2A4` in `sub_82419A30`, totaling 23,425 PM4 words. The
local presentation separately owned the 12 previously identified buffers.
Together these observations establish the selected player-car chain through
its presentation and model instances into title submission. Remaining SNR-01
work is per-buffer mesh/LOD accounting, final-state timing, unmatched/culling
classification and the 27 direct root-buffer draws; material/resource identity
belongs to SNR-02.

### Every local car owner call is accounted for

Read-only hooks at the entries of `sub_8243CDC0`, `sub_82439960` and
`sub_82419A30` now assign an ordinal to each owner call and retain entry
arguments `r4` through `r10` on every scene-list packet emitted by that call.
The sustained-race replay exited normally with seven captures. Its executable
SHA-256 is
`02997B8A6569C81F565D5EFC99FB4ECB2DD6EF2CE71449FDDF20281F9F316B4D`;
the isolated frame-6000 log at
`.local/native-renderer/snr01/local-car-owner-calls-run-a.log` has SHA-256
`5BF966BDFDE5144951185BC3AE61E54A83F071E132A594CF9737BA6F8C5AD720`.
`tools/verify-snr01-player-presentation.py --require-owner-calls` verifies the
semantic local-player chain and the exact call-to-packet relationships.

The local presentation received 20 owner calls in view 8. Twelve calls each
emitted one scene buffer; their third observed argument selected values 0, 16,
18, 20, 21, 43, 46, 48, 51, 52, 54 and 56. Eight calls emitted no scene
buffer, with selector values 22, 40, 41, 57, 58, 59, 60 and 61. The local
model received 31 owner calls and every call emitted a scene buffer: 29 calls
emitted one and two list calls emitted four, yielding the previously observed
37 model buffers. Every one of the 49 local buffers references a same-owner
call ordinal and carries byte-for-byte identical captured arguments; there are
no missing or mismatched call records.

This proves complete call-to-buffer accounting at the three observed local-car
owner functions for this frame. The eight presentation calls are classified
only as title-side no-submission cases. Their branch or resource reason has not
yet been observed, so they are not claimed as intentional culling. The numeric
selector values are also not yet semantic mesh or LOD labels. SNR-01 remains
open for those meanings, final-state timing, complete selected-slice coverage
including the direct root-buffer draws, and explicit no-submission reasons.

### Null list selections explain the local presentation no-submissions

A follow-up hook records the presentation list lookup result at `0x8243CDE8`,
immediately before `sub_8243CDC0`'s existing null branch. Moving the three
owner-call probes one instruction past their entry `mflr` also records the
original caller without altering arguments. The normal-exit sustained replay
again produced seven captures. Its executable SHA-256 is
`114BDDB983B079DEC29FE3EE597BCA392AF365D260F1DA32862BC7F0830EFABC`;
`.local/native-renderer/snr01/local-car-selection-run-a.log` has SHA-256
`EAAC15D78722EC186DC1E87CB50AB4E85613862B7280346C96CE43FDEE08B50F`.
The owner-call verifier passes with the stricter selection and caller checks.

Every one of the 12 packet-producing local-presentation calls selected a
nonzero list, and the selected pointer exactly equals its emitted packet's
`list_object`. Each of the other eight calls selected null. They are therefore
proved title-side null-list skips rather than missing packet observations.
This classifies the branch outcome; it does not establish whether the empty
slot represents absent geometry, LOD policy, damage state or visibility.

The 20 presentation calls originate from seven sites in `sub_82437218` and 12
calls from `sub_8243CEE0` at return `0x8243D270`. The local model's 31 calls
originate from four sites in `sub_82437218` and two calls from `sub_8245AA98`.
The verifier locks their exact per-site counts. These call sites and the
selector-table formula in
`sub_8243CCF0` provide a bounded next boundary for recovering part/LOD meaning;
numeric selector values remain unnamed until their producer or data schema is
proved.

### Local car title buffers join exactly to prepared draws and fetches

The full timestamp-ordered replay log, including backend frame 6001, is local
at `.local/native-renderer/snr01/local-car-selection-run-a-full.log` with
SHA-256
`2BB523AFC9BDEC60CE7034D720FEBA4D93777F60047F7412FFD2822807FC88BC`.
The player-presentation verifier's `--require-backend-join` mode uses each
scene packet's exact header/target pair to find backend indirect executions,
then uses execution identity to select prepared draws and their fetch records.
It does not use shader or address proximity to infer ownership.

All 49 local-car title buffers matched at least one backend execution. Repeated
execution produced 108 child executions and 268 prepared draws: 156 under the
local presentation and 112 under its model. The immediately preceding replay
had the same 108/268 and 156/112 counts. Every draw used the observed scene
color/depth binding (`surface_info 0x14020500`, color `0xC0000`, depth
`0x10400`, binding bits 3). The draws span 46 shader pairs and 104 distinct
index-buffer range/primitive tuples.

The backend emitted all expected fetch records for those draws: 716 vertex
fetches and 1,238 texture fetches. They resolve to 48 distinct
base/length/stride/type vertex-buffer tuples and 25 distinct texture payload
tuples (base, mip base, format, dimension and extent). Every vertex fetch
names one of the matched local-car executions as a state source. This is the
first exact local-player owner → title list → backend draw → geometry/texture
resource census and supplies an authoritative starting set for SNR-02.

These backend tuples describe prepared state, not semantic material roles or
resource generations. Repeated executions must not be counted as additional
title instances, and shared buffer addresses need allocation/payload lifetime
proof before native admission. Shader pairs remain diagnostics rather than
paint, glass, decal or other role labels.

### Full backend target census for the local-car replay

The later normal-exit SNR-02 table-owner replay (log and executable hashes in
[its evidence](SCENE_NATIVE_SNR02_EVIDENCE_2026-09-22.md#presentation-table-owner))
contains 4,911 prepared draws in backend frame 6001. Of these, 2,884 share
surface word `0x14020500`, depth word `0x10400` and both color/depth binding
bits: 1,577 use color word `0xC0000` and 1,307 use `0x30000`. The local-car
join accounts for 268 draws on the former color word, but the target tuple
alone does not identify the main camera, pass membership or material class.
This bounded census quantifies why the proved local-car chain cannot freeze
the full main-view slice: other title owners and the relationship between
these two color words must be resolved before SNR-00/01 can close.

### Two-source-frame, every-draw ownership census

The existing one-frame title trace omitted the following frame's root
publication, even though backend frame 6001 consumes roots from both source
frames 6000 and 6001. A new default-off
`--pinyon_shift_snr01_trace_following_frame=true` option observes both source
frames and resets view ordinals at their boundary. The saved sustained-race
replay exited normally with seven captures; executable SHA-256 was
`FD24EAAA1ACAAC2C7C55D21FFDC828AF312AC81E2218C750D77EADF61CF2715A`.
The ordered diagnostic log at
`.local/native-renderer/snr01/frame-wide-census-run-a-full.log` has SHA-256
`81195506136F8624B23E6D21755342F3A426130C90FD322FA7DB038678641EED`.
`tools/summarize-snr01-frame-wide-census.py` generated the per-draw ledger
`.local/native-renderer/snr01/frame-wide-census-run-a.json` (SHA-256
`8A1609CE42BB560409E12A383A9011D773B2CC3F3BA43D4D05D6E943A28BAF49`).
It records each draw ordinal, target tuple, execution/root IDs, source frame,
view and observed flush owner, or an explicit unresolved classification.

Both source frames had eight title view calls and 2,534 total scene-list
packets. Backend frame 6001 executed 135 roots and 1,654 indirect buffers,
yielding 5,282 prepared draws. Its roots joined uniquely to title primary
packets: 1,977 draws under roots published in source frame 6000 and 3,305
under roots published in 6001. Of those draws, 3,672 joined exact
scene-list header/target pairs published in source frame 6000; the scene
lists published in 6001 were not consumed in this backend frame. The primary
indirect, camera/view, track-bucket and local-player verifiers pass on this
capture after the camera verifier filters view events by source frame.

| Target group | Draws | View + flush owner | View, no owner | Direct root | Unmatched indirect | Out-of-view scene |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Scene tuple, color `0xC0000` | 1,801 | 1,076 | 24 | 701 | 0 | 0 |
| Scene tuple, color `0x30000` | 1,398 | 1,078 | 0 | 296 | 24 | 0 |
| Other target tuples | 2,083 | 1,126 | 12 | 517 | 72 | 356 |
| **Whole frame** | **5,282** | **3,280** | **36** | **1,514** | **96** | **356** |

All 2,154 candidate-tuple draws with an observed view and flush owner came
from title view call 8 in source frame 6000. The ledger also joins direct-root
draw packet addresses to title `direct` or `semantic` packet writes and
reconstructs their view from same-thread, ordered begin/end records. This
resolves the **view** of 996 of the 997 candidate direct-root draws to view 8;
their title paths include 615 `secondary` direct packets, 30
`indexed2_secondary`, four `primary` direct packets, and 347 semantic packets.
Across the whole frame, 1,496 of 1,514 direct-root draws have such a title
write and view classification. The packet join does not yet identify their
semantic owners.

Thus 3,174 of the 3,199 candidate-tuple draws have proved title view 8:
2,154 with a flush owner, 24 view-8 scene-list draws without one, and 996
direct-root title packets. The remaining 25 are 24 unmatched indirect draws
and one direct-root draw without a matching source write. Their exact draw
ordinals and root packets are in the ledger. The other target tuples include
view-1 depth, views-2–7 cube work and out-of-view work, but their unresolved
direct-root and indirect draws still need owner and pass classification. A
flush-owner pointer is not yet a mesh/material identity. This is a whole-frame
accounting of observed lineage, **not** a frozen cut: SNR-00/01 must resolve
the direct-root semantic owners, the 25 candidate view gaps, retained-pass
dependencies and actual resource owners before admission or suppression.
The 24 indirect gaps are consecutive draw ordinals 5152–5175 under one child
execution (ID 3396208, header `0x12F756D8`, target `0x132C5F00`) whose
root header `0x12EB876C` was published in source frame 6001. The other gap
is direct-root draw ordinal 1977 at packet `0x12EC6368` under root header
`0x12EB8620`. These are
capture-specific addresses, not persistent identities. The next probe can
focus on the missing child-packet producer and the direct-root writer rather
than expanding the already verified local-car pointer chain.

### Exact attachment-write state of the repeated point draws

A further default-off two-source-frame replay logged the prepared draw's
existing normalized depth control, color mask and draw flags. It exited
normally with seven captures using executable SHA-256
`B9729C6876729F7338E24A31D23AC679067C98FD3F267729D10F0FA8990FCF38`.
The ordered log at `.local/native-renderer/snr01/frame-wide-state-run-a-full.log`
has SHA-256
`C8E3CDE57074E21A48693746F8BD85593E10BCA84BFDD070D9653158F92F71AE`;
the per-draw ledger at `.local/native-renderer/snr01/frame-wide-state-run-a.json`
has SHA-256
`7FCAAEC52083F4E1A8E535CAA92907215DE7A95C8B736F9F1EFA8B1224598A5A`.
The route's traffic differed from the prior replay (4,098 versus 5,282
backend draws), so its counts are not substituted into that census.

The same resident 192-byte child buffer produced 24 one-point draws in each
of four target phases, including the candidate scene-color `0x30000` phase.
In all 96 observations the vertex program was `B6C9863F710683EC`, there was
no pixel program, and normalized color mask and depth/stencil control were
both zero. The 24 candidate-phase draws therefore made **no color, depth or
stencil attachment write** in this replay. The earlier RenderDoc race capture
independently shows three 24-draw phases using that vertex program with depth
disabled. This supports keeping these draws outside the diagnostic *image*
slice, while retaining their compatibility execution until any query or other
guest-visible side effect and consumer is proved. It is not permission to
suppress them.

The one direct-root candidate gap recurred as draw ordinal 1635. It used
`1E6883FCCDE1F688`/`A4A965C189287B99`, a three-index rectangle draw,
normalized color mask 15 and depth control 34679, whose low enable/write bits
are nonzero. It was the first draw to either candidate scene-color target in
this backend frame, immediately before the captured view-8 draws. That order
suggests a scene-pass setup draw, but does not establish its title owner or
semantics. It is an image-writing draw with no captured title packet writer
or view, and it still blocks freezing the candidate slice. All 24
attachment-write-free draws and this image-writing draw remain separately
identified in the ledger; attachment words alone must not decide admission.

The SDK already recognizes this vertex/pixel shader pair as an FH1 native
position-color pipeline. Its rectangle-clear replacement additionally checks
the complete pipeline, no query or memory export, CPU-readable vertices,
constant rectangle color and target bounds before `ClearFh1Rectangles`.
The observed shader pair, rectangle primitive and write mask make the direct
draw a **clear candidate**, not an identified clear: this replay did not log
those further checks or the replacement result for draw 1635. The title's
existing read-only `sub_8240E130` clear-producer hook likewise has not been
joined to this packet. A bounded packet-to-producer/clear-result join is the
next useful check. If it proves a retained scene-target clear, classify its
image write as a prerequisite to the view-8 object slice and carry its
resource dependency into SNR-05; otherwise keep it in the unresolved set.

### Title clear producer joins the candidate scene-target packet

A default-off replay paired the existing `sub_8240E130` clear-producer scope
with its device command cursor before and after the call. The saved sustained
race exited normally with seven captures. Executable SHA-256 was
`C9C57BD9B6030F7AAAE5B6C5486703565C0DED512EEE0A78D56F4DBDDB3EDEF5`.
The ordered source-frame-6000/6001 and backend-frame-6001 log at
`.local/native-renderer/snr01/clear-cursor-run-a-full.log` has SHA-256
`2D1A0CFC9B0EB28C8C1F281B164C6632F9C344126F172B272C04BC02C6A6A91C`;
the draw ledger at `.local/native-renderer/snr01/clear-cursor-run-a.json` has
SHA-256
`36D4998312280B14243E8D0BBB1A84931307742848D466698A1C4BB66594D43A`.
The exact primary-root and camera/view verifiers pass. Traffic again varied:
this backend frame had 5,165 prepared draws and 133 roots, so the addresses
and counts below belong to this replay only.

The one candidate direct-root gap was draw ordinal 1971, an 8-byte packet at
physical `0x131A5D08`, in a 592-byte root published in source frame 6000.
Title clear-producer record 62152 was in the same source frame on the title
thread. Its command cursor advanced from guest `0xB31A5B3C` to
`0xB31A5D1C`, physical `0x131A5B3C`–`0x131A5D1C`, with zero refills and no
nested producer. The complete draw packet lies inside that range; no other
clear-producer range contains it. The producer used flags 63 and the draw
targeted the candidate `0x30000` color/depth attachments with writes enabled.
This proves title clear **packet provenance** and pass order, not that the
SDK's optional native rectangle-clear replacement accepted this exact draw
or that the resulting resource contents were validated. Keep the clear and
its target writes on the compatibility path as a prerequisite to the selected
view-8 scene image.

The ledger conservatively labels only direct-root packets wholly contained
in one non-refilled, non-nested clear-producer range as `title_clear`: 12 of
5,165 draws, including this candidate gap. For the two candidate target
tuples together, 3,067 attachment-write-enabled draws have captured view-8
title paths (2,109 scene-list draws with a flush owner, 24 without one,
one, and 934 direct-root title packets). One retained title clear precedes
them; the 24 unmatched indirect point draws have no color/depth/stencil
attachment writes in this replay and remain compatibility work. There are
therefore **zero unattributed attachment-writing candidate draws** in this
capture. This resolves the two candidate view gaps at the image/pass boundary,
but does not freeze the complete object slice: semantic owners for the 934
direct-root packets and 24 ownerless scene-list draws, material/geometry
identity, resource freshness, and retained-pass consumers remain open.

### Direct character-manager pass family

The preceding ledger's largest candidate direct-root call site was
`0x8243C8FC`, inside `sub_8243C050`. That function is called directly from
`CPresentationView` slot 13 (`sub_82444E60`) and receives a context, graphics
device, presentation view and track-presentation object. A default-off
read-only scope at function entry/exit records these arguments and the exact
direct-packet ordinal range. The sustained saved-race replay exited normally
with seven captures. Executable SHA-256 was
`276E881D703D5C8C1DBCE485F8C6A565260B277033DC4ABEEB256E192D926BB5`;
the isolated ordered log at
`.local/native-renderer/snr01/direct-family-run-a-session.log` has SHA-256
`159FE244E1018B60EC1B6B047C7BAD9DB2A295A160AB047472A68D62DA549F0A`.
The per-draw ledger at `.local/native-renderer/snr01/direct-family-run-a.json`
has SHA-256
`C2BF2FF808D7380D35B91E14864AE1972065E8DED5AA8509119CFFA144B7B4C6`.
The frame-wide summarizer with `--require-direct-family`, exact primary-ring
join, and camera/view join all pass for source frame 6000/backend frame 6001.

The two observed `sub_8243C050` calls in source frame 6000 each enclosed
105 direct packet writes. View call 1's packet range yields 105 backend
depth-pass draws; view call 8's range yields 315 draws on candidate scene
color word `0xC0000`. Every backend draw from the title direct caller
`0x8243C8FC` maps to exactly one of those two scopes. The view-8 group
accounts for 315 of 723 attachment-writing candidate direct-root draws in
this replay. Counts differ from the earlier 934-draw candidate sample as
traffic and visibility varied; they are not interchangeable.

The sampled context's first word `0x82243B58` resolves through base-image
RTTI locator `0x82363AD8` and type descriptor `0x832B9D88` to
`proceduralGeometry::CProceduralCharacterManager`. The other first words
resolve to refcounted `CPresentationView` (`0x8200255C`), unified
`CTrackPresentation` (`0x82003CCC`) and `CD3D9GraphicsDevice`
(`0x8200306C`). The verified base image at
`.local/ui-verify/default-image.bin` has SHA-256
`6014727FA7B0B79727FD5F32A2E2377533DC8E29679E8D2462BD764D331FA305`.
This establishes the manager and title pass boundary for this direct family,
not the identity or lifetime of each character mesh/material. The other
candidate direct-root families, ownerless scene-list draws and resource
relationships still block a frozen object slice.

### Character-manager record to backend-draw join

A second default-off probe at the `sub_8243C050` call to `sub_82416380`
captures the manager's selected 128-byte record, its 24-byte source entry and
the direct-draw arguments immediately before packet emission. The saved
sustained-race replay exited normally with seven captures. Executable SHA-256
was `8D5D4220A784847E70C00194DF718AF09E05227EB0F928FDCD7E6999232A3E52`.
The isolated ordered log at
`.local/native-renderer/snr01/direct-family-record-run-a-session.log` has
SHA-256 `BEA74D62B6D9A9237DDDB7DB84B073487006BE6B149A339591B49D664353FAD1`;
the per-draw ledger at `.local/native-renderer/snr01/direct-family-record-run-a.json`
has SHA-256 `1750EDF5170DB63A649B32B6D3FA03B1BDD0DE77022878976CA8FD35C3E13916`.
The ledger's frame-wide, record-to-packet and index-count assertions pass,
as do the camera/view and primary-indirect join verifiers.

This backend frame contains 4,326 prepared draws, including 724
attachment-writing candidate direct-root draws. The source-frame-6000
character-manager depth and view-8 color calls each select the same 126 record
addresses, at an exact 128-byte stride, from 15 source entries at an exact
24-byte stride. All captured record words, source addresses and draw arguments
match across those two calls. Each depth record produces one backend draw;
each color record produces two or three, for 309 color draws total. Every one
of those 309 draws retains the title's `arg7` index count and writes the
candidate scene-color attachment. Thus this family accounts for 309 of the
724 candidate direct-root draws in this replay. Record address reuse across
the two passes supports a same-frame selected-record identity; it does not
prove allocation generation, mesh/material ownership, or resource freshness.

Some title packet physical addresses recur across the two captured source
frames. The ledger no longer assumes global address uniqueness: for each
direct-root backend draw it requires at most one captured title writer at
that physical address. In this replay, 1,205 of 1,221 direct-root draws have
one such writer and 16 have none; none are ambiguous. Of the 724 candidate
attachment-writing direct-root draws, 723 have a unique title writer and one
has none. The earlier clear-producer join identified this kind of candidate
gap in a separate replay; it was not re-established in this record capture.
If a future backend draw matches two source-frame writers, the ledger will
stop instead of choosing one without a buffer-generation proof.

### Existing procedural item and node records close another candidate join

The same capture already contains title `procedural item` and `item node`
records. The updated frame-wide ledger joins each semantic packet's exact
`(source frame, procedural call)` to its selected descriptor/runtime record,
then checks the enclosing node's packet and item-call ranges, receiver and
view. It also requires that the selected descriptor/runtime record reached
the original submit call. No new runtime probe was needed. The resulting
ledger at `.local/native-renderer/snr01/direct-family-record-item-join-run-a.json`
has SHA-256 `6C70E0DF0ECB5E8B1AE8DE65571D0E8F1919E1E01FAAAB6C8DD01399156E29B4`.
Its strict item/node and direct-record checks pass, as does the older
clear-cursor replay without the new strict flags.

Of the 724 attachment-writing candidate direct-root draws in this replay,
171 callbacks come from 114 unique semantic packets at `0x82415D1C`.
Each packet maps to one submitted procedural item, selected descriptor,
runtime record and item node in view call 8. All 171 callbacks share the
observed node render-owner address `0xAC9D3950`; this is a captured pointer,
not a resolved semantic type or lifetime. The selected descriptor-kind values
are raw title enum values (0, 1, 4 and 5), not material labels. Together with
the 309 character-manager callbacks above, exact title item/record identity
now covers 480 of 724 candidate direct-root callbacks in this replay.

The remaining 244 callbacks comprise 141 from 71 semantic packets at
`0x82412E1C` with no active procedural item/node, 102 from other direct
packet callers, and one packet with no captured title writer. They retain
view-8 packet attribution where present, but do not yet have the required
mesh/instance and resource ownership. Nor does this join resolve the 36
ownerless scene-list callbacks elsewhere in the frame. The candidate slice
therefore remains provisional.

### Second context path identifies candidate vegetation records

The generated `sub_82412DD8` is the render-context vtable-offset-164 draw
method reached by the non-item semantic packet writer at `0x82412E1C`.
A default-off entry/exit probe records its original caller, arguments,
active view and exact semantic-packet range. The sustained saved-race replay
exited normally with seven captures. Executable SHA-256 was
`99DD130683EDACB90E8EBE454499A310C485459E90FC5EA4189B5B88A781C7B7`;
the isolated log at `.local/native-renderer/snr01/second-path-run-a-session.log`
has SHA-256 `48E74F8FA95046BC153B15F63AC2B3CD4B0E02A8624027666323DCD0BB838E95`.
The strict frame-wide ledger at `.local/native-renderer/snr01/second-path-run-a.json`
has SHA-256 `C09037DD78600F97ACAE4D5B11086EAA066CE9D3708022C93F569ED4701D14C0`.
The exact primary-root, track-bucket, camera/view and title-item joins pass.
This route has 3,900 backend-frame-6001 draws; counts cannot be combined
with those of the preceding replay.

Of 646 attachment-writing candidate direct-root callbacks, 183 derive from
80 `sub_82412DD8` semantic packets. Their original title callers split into
163 callbacks at `0x82413A84`, 11 at `0x8245AEA0`, and nine across three
other callers. Static code at `0x82413A84` calls the virtual draw from the
vegetation loop. The existing second-draw and track-bucket records join its
163 callbacks to 70 unique selected bound records, eight vegetation owner
objects, and the title-side vertex descriptors. Each joined call has the
same context and draw arguments as the new second-path scope; its bound
record equals the selected vegetation record. The track-bucket verifier
independently checks all 140 vegetation packets and 233 callbacks in this
frame, including those outside the candidate direct-root group. The 11
callbacks at `0x8245AEA0` join seven bound records on the character path.
This establishes title item/record provenance for these observed draws, not
allocation generation, final transform, material semantics or freshness.

This replay also put five directly observed primary-store packets under the
post-view deferred roots. The camera/view verifier previously admitted only
secondary-store direct packets there; it now accepts primary or secondary
when the same verified direct-emitter scope and caller are present. It passes
this and the prior character-record replay. The nine other second-path
callbacks have original call sites but no enclosing second-draw record in
this capture. They and the remaining candidate direct packets still need
semantic ownership before the slice can be frozen.

### The local car model owns the remaining view-8 scene-list flushes

The three previously unowned flush return sites `0x8244CBF4`, `0x8244DD5C`
and `0x8244E2A8` occur in the generated car-model path. The first submits
the list in the entry `r28` object's offset-32860 field; the latter two use
the same field on the entry `r27` object. The bounded hook now records that
object only when its field exactly matches the submitted list argument.

A normal-exit saved-race replay at source frame 6000 produced seven captures.
The executable SHA-256 was
`6D38BD3AC48010B16A7EB361C1FFFA0E30168A822184766E60A6CA037D1796A5`.
Its filtered ordered log is
`.local/native-renderer/snr01/list-owner-run-a-filtered.log` (SHA-256
`D2732D08C9DF9D70C4DAC7BBB950EA7B06E5B50177501E58B93BDC70BD5658DB`)
and the frame-wide ledger is
`.local/native-renderer/snr01/list-owner-run-a-ledger.json` (SHA-256
`5030D731E178A622339722EBFC06C2009DABAC87BD587DA80CA0B0066A3E8EC7`).
The exact local player → car → presentation → model link identifies the
newly joined owner as the local `CCarModel`, with vtable `0x82001618`.
Eight title packets (four, two and two from the respective call sites)
each execute twice, producing 24 candidate scene-color draws. The updated
player-presentation verifier retains its original 37 model-owner packets
and checks these eight additional packets and their 24 draws separately:

```powershell
python tools/verify-snr01-player-presentation.py `
  .local/native-renderer/snr01/list-owner-run-a-filtered.log `
  --frame 6000 --require-local-model --require-list-owner
python tools/summarize-snr01-frame-wide-census.py `
  .local/native-renderer/snr01/list-owner-run-a-filtered.log `
  --source-frame 6000 --require-direct-family `
  --require-direct-family-record --require-semantic-item-node `
  --require-second-path `
  --output .local/native-renderer/snr01/list-owner-run-a-ledger.json
```

The ledger accounts for all 5,109 prepared draws and has zero
`view_unowned` classifications. The two candidate scene-color groups have
3,188 draws: 2,162 scene-list draws with exact view-8 owner, 1,001 direct
draws with a title view-8 packet, 24 unmatched indirect draws with no
attachment writes, and one direct draw with no captured title writer.
This is a stronger boundary census, not a frozen native slice: direct-draw
mesh/material owners, the one writer gap, resource generations, and the
other frame classifications still need resolution.

The follow-up replay enabled the existing clear-producer trace, exited
normally and produced seven captures. Its ordered log is
`.local/native-renderer/snr01/list-owner-clear-run-a-filtered.log` (SHA-256
`5A50358AAC2E8E9B6C5F094C4D34A392E66883D295D7DD3AF9BF5B425E03034D`)
and its ledger is
`.local/native-renderer/snr01/list-owner-clear-run-a-ledger.json` (SHA-256
`E21B4180A8FFF976A6EBB2B7B26741A37CB560D662B2A09B667B93BF7A529C34`).
The local-model verifier above passes on this log as well. The frame-wide
verifier passes with `--require-candidate-boundary`, which rejects any
candidate draw without a view-8 owner, a view-8 direct title packet, an
exact title clear, or a proven no-write state. The ledger
accounts for all 4,350 draws, including ten exact title-clear joins and
zero `view_unowned` draws. The candidate groups contain 2,576 draws:
1,756 view-8 scene-owner draws, 795 direct draws with a title view-8 packet,
one retained title-clear draw and 24 unmatched indirect draws with no
attachment writes. The clear draw's packet lies wholly in producer record
62238's captured command-cursor range. Counts differ between replays, so
the two ledgers are separate observations rather than additive totals.
Recheck the boundary with:

```powershell
python tools/summarize-snr01-frame-wide-census.py `
  .local/native-renderer/snr01/list-owner-clear-run-a-filtered.log `
  --source-frame 6000 --require-direct-family `
  --require-direct-family-record --require-semantic-item-node `
  --require-second-path --require-candidate-boundary `
  --output .local/native-renderer/snr01/list-owner-clear-run-a-ledger.json
```

The same build with all probes off also completed the saved route normally
with seven compatibility captures; this is a smoke check, not a visual or
performance equivalence claim.

Of this clear-trace replay's 795 candidate direct draws, 415 have a joined
direct-family record, 134 a procedural item/node, and 130 a vegetation
second-draw bound record. The remaining 116 have a title view-8 packet but
no instance/record join. Their largest family is 89 draws from return site
`0x824131F4` (84 secondary and five primary packet stores). Generated
`sub_824131B8` owns that return site, computes a draw argument from its
entry `r4`/`r7`, and calls `sub_82416380` to submit. Its entry caller and
input object are the next bounded provenance target. The other gaps are
nine each from `0x823F59C8` and `0x82412E1C`, plus three each from
`0x82401258`, `0x8244F070` and `0x82D0735C`. This partitions the remaining
direct-draw ownership work without guessing their mesh or material roles.

### Scalar draw wrapper joins the car-presentation subobject

A read-only scope around `sub_824131B8` records the entry caller, device,
selector and input count with the exact direct-packet ordinal range emitted
by its original `sub_82416380` call. The frame-wide ledger keys that range
by title thread as well as source frame and ordinal; ordinals repeat on
different title threads. In a normal-exit saved-race replay, all 88 candidate
prepared draws from this wrapper joined a scope, and the strict candidate
boundary check passed across all 4,598 prepared draws.

Seventy-two of the 88 wrapper draws came from the three indirect call sites
`0x82443B98`, `0x82443C40` and `0x82444018` inside generated
`sub_82443600`. That function retains its entry `r3` in nonvolatile `r29`
while passing the graphics device to the draw wrapper. For all eight live
`CCarPresentation` instances, the captured `r29` was exactly the
presentation address plus 2016, with three prepared draws per call site per
presentation. The local-player presentation also appears in this set. This
proves a title presentation-subobject → direct packet → prepared-draw edge;
the subobject's first word is zero, so no separate RTTI type is claimed.
The other 16 wrapper draws in this replay came from `0x82415A28` (ten) and
`0x823FDDFC`/`0x823FDE2C` (three each) and still need semantic ownership.

The final instrumented executable SHA-256 was
`F405E6939C188DBFF1082D3853DEFB5F54A121733314E749E5FFC2624961591F`.
The ordered filtered log is
`.local/native-renderer/snr01/scalar-outer-run-a-filtered.log` (SHA-256
`DBD77567575B30B097EE7C06532B779195808D1AE269983F60BE00128BCDF021`)
and its ledger is
`.local/native-renderer/snr01/scalar-outer-run-a-ledger.json` (SHA-256
`FCF36A1B2ADE91882CA0E9FB49B54E72B43601FB3934E7AFB711EC164EFDDA8F`).
The replay produced seven compatibility captures. Recheck with:

```powershell
python tools/summarize-snr01-frame-wide-census.py `
  .local/native-renderer/snr01/scalar-outer-run-a-filtered.log `
  --source-frame 6000 --require-direct-family `
  --require-direct-family-record --require-semantic-item-node `
  --require-second-path --require-scalar-draw `
  --require-candidate-boundary `
  --output .local/native-renderer/snr01/scalar-outer-run-a-ledger.json
python tools/verify-snr01-player-presentation.py `
  .local/native-renderer/snr01/scalar-outer-run-a-filtered.log `
  --frame 6000 --require-local-model --require-scalar-presentation `
  --census-ledger .local/native-renderer/snr01/scalar-outer-run-a-ledger.json
```

This replay's candidate groups contain 2,595 draws: 2,017 view-8 scene
owners, 553 view-8 direct packets, one retained clear and 24 indirect
draws with no attachment writes. The 72 newly joined draws are a subset of
the 553 direct packets; they do not establish mesh/material generations or
complete the main-view slice.
The same final build with the probes off exited normally with seven
compatibility captures. This is a smoke check, not an image-equivalence or
performance result.

### Dynamic particle packets have a persistent title owner

Read-only hooks bracket the two direct submissions in `sub_82D06C28` and its
caller `sub_82CFDA58`. The caller builds the callee's input record on its
stack, so that input address is not a persistent owner. It retains a separate
object in `r31` and calls the renderer held at its `+36` field. The frame-wide
ledger joins parent input, child input, direct packet and prepared draw by
source frame, title thread and packet ordinal; it also checks four guest
vertices per reported quad.

The verified title image names parent-object vtable `0x82235F94` as
`CParticleSystemNew` and renderer vtable `0x82236214` as
`CStandardParticleRenderer`; slot 3 of the latter is `sub_82D06C28`.
The image SHA-256 was
`6014727FA7B0B79727FD5F32A2E2377533DC8E29679E8D2462BD764D331FA305`.
In the normal-exit saved-race replay, six distinct `CParticleSystemNew`
objects submitted six source-frame-6000 packets in title view 8. They
produced 18 backend-frame-6001 prepared draws, all in the two candidate
scene-color groups: 15 from return site `0x82D07200` and three from
`0x82D0735C`. Every packet used the `indexed2_secondary` path and every
prepared draw joined exactly one parent and child scope. The full ledger
accounts for 3,206 prepared draws; its 1,733 candidate-group draws include
1,062 view-8 scene-owner draws, 646 view-8 direct draws, one title clear and
24 no-write indirect draws. The strict candidate-boundary check passed.

These 18 draws are now identified as **retained particle-renderer work** in
the provisional cut, despite using the candidate scene attachments. The
native opaque/alpha-tested diagnostic must preserve their input/depth
relationship; their presence cannot be used to claim complete selected-scene
coverage or to suppress the particle path. Other candidate direct draws
remain unresolved, so the complete slice is not frozen and SNR-01 stays open.

The instrumented executable SHA-256 was
`0D59CDB19A2FD0B36F5D9B95213208EBAD8042F2A219D98764369562387C612A`.
The ordered filtered log is
`.local/native-renderer/snr01/dynamic-quad-parent-run-a-filtered.log`
(SHA-256 `22D75311C3E766E9D9B1741EB408A6593A02DF8168EA41DF68917BE4B9823CC4`)
and the ledger is
`.local/native-renderer/snr01/dynamic-quad-parent-run-a-ledger.json`
(SHA-256 `5EE9D27B086850A5CF27D2FE4E39C44528484266F9F98A77D10D320EEB260328`).
Recheck the title/command joins, RTTI and boundary with:

```powershell
python tools/summarize-snr01-frame-wide-census.py `
  .local/native-renderer/snr01/dynamic-quad-parent-run-a-filtered.log `
  --source-frame 6000 --require-direct-family `
  --require-direct-family-record --require-semantic-item-node `
  --require-second-path --require-scalar-draw `
  --require-dynamic-quad --title-image .local/ui-verify/default-image.bin `
  --require-candidate-boundary `
  --output .local/native-renderer/snr01/dynamic-quad-parent-run-a-ledger.json
```

The same executable with the probes off also exited the saved route normally
with seven compatibility captures. This is a smoke check, not a visual or
performance equivalence claim. The updated summarizer also rechecked the
earlier 4,598-draw scalar-wrapper ledger with its strict boundary flags.

### Remaining unowned candidate direct packets in the particle replay

Re-reading the full 3,206-draw ledger, 622 of the 646 candidate direct draws
carry at least one of the direct-record, procedural item/node, vegetation
bound-record, scalar-object or particle-parent joins. The remaining **24
prepared draws are eight title view-8 packets**, with three prepared draws per
packet. Their title packet and attachment joins are exact; their semantic
render owner is not yet established:

| Return site | Title packet ordinals | Prepared draws | Submission path | Index counts |
| --- | --- | ---: | --- | --- |
| `0x823F59C8` | 101–103 | 9 | secondary direct | 9300, 8700, 9300 |
| `0x82401258` | 106 | 3 | indexed2 secondary | 220 |
| `0x82412E1C` | 490–492 | 9 | secondary direct | 9096, 4, 512 |
| `0x8244F070` | 116 | 3 | indexed2 secondary | 4 |

Packet 101 writes candidate color word `00030000`; the other seven write
`000C0000`. Generated `sub_823F5980` owns the first return site and retains
its entry object while calling `sub_82416380`. The second-path scope for
`sub_82412DD8` joins packets 490–492; its callers are respectively
`0x823FA8DC`, `0x82447C08` and `0x823FB7D4`. Each caller invokes the
same vtable slot `+164` on its render interface, but the shared command
context alone does not identify the three scene owners. The two indexed2
sites are calls to `sub_8240DC70` inside `sub_82400E70` and
`sub_8244E938`; they issue argument selector 13 with sizes 24 and 16.
These are code-path facts, not material or pass labels. Until the retained
versus selected status of these eight packets and the other direct families
is proved, the exact main-view slice remains provisional.

### Three second-path packets retain distinct caller input records

The existing default-off `sub_82412DD8` scope now reads the enclosing
caller's preserved `r30` and its first word. In a normal-exit saved-race
replay with seven compatibility captures, the three view-8 source-frame-6000
calls each emitted exactly one semantic packet:

| Caller return | Semantic packet | Caller `r30` | First word | Submit arguments `r4`, `r5` |
| --- | ---: | --- | --- | --- |
| `0x823FA8DC` | 389 | `0x40934BE0` | `0x3E800000` | 1, 9096 |
| `0x82447C08` | 390 | `0x40934B60` | `0x3EFF6B07` | 13, 1 |
| `0x823FB7D4` | 391 | `0x40934B00` | `0x3CF30D15` | 13, 128 |

Generated `sub_82D756A8` calls the three functions with `r3` set to its
entry object plus 1408, 1280 and 1184 respectively. Subtracting those
offsets from the observed caller inputs gives the **same parent address,
`0x40934660`**, for all three packets. Their first words are float-like,
not RTTI vtables. This proves a shared title parent → three input records
→ semantic packets; the parent's class was still unknown at this step. The executable
SHA-256 was
`6FF1AD1AD68B635B3306604AF639EE290113A51A0CC90DD8B0E3064E449355F8`;
the ordered filtered log is
`.local/native-renderer/snr01/second-caller-run-b-filtered.log` (SHA-256
`FB25F4D500C05CAF35366AADDC07B97B5119ACE9D75D38D836BBC3342146DF9F`).
The read-only probe can be rechecked with:

```powershell
@'
import json
rows = [json.loads(line.split('FH1 SNR01 second path ')[1])
        for line in open('.local/native-renderer/snr01/second-caller-run-b-filtered.log', encoding='utf-8')
        if 'FH1 SNR01 second path ' in line]
found = [r for r in rows if r['frame'] == 6000 and r['view_call'] == 8
         and r['caller_lr'] in (0x823FA8DC, 0x82447C08, 0x823FB7D4)]
assert len(found) == 3 and len({r['caller_object'] for r in found}) == 3
assert all(r['caller_object_word0'] and r['first_semantic'] == r['last_semantic'] for r in found)
assert {r['caller_object'] - {0x823FA8DC: 1408, 0x82447C08: 1280,
                              0x823FB7D4: 1184}[r['caller_lr']]
        for r in found} == {0x40934660}
'@ | python -
```

The initial broader extraction for this replay did **not** pass: it counted
6,869 prepared draws and reported root `(317456596, 321236480)` without a
title packet. That extraction mistakenly included the previous process's
tail from rotated `runtime.*.log` files. It is invalid as a frame-wide
ledger; the three bounded call records above remain from the stated replay.
The session-bounded extraction and passing full census below supersede the
missing-root claim. Gate A remains open for the separate full-slice coverage
and resource/dependency requirements.

### Shared second-path parent is `CRealtimeSky`

A read-only entry hook on generated `sub_82D756A8` records the parent before
it dispatches the three child calls. A subsequent normal-exit saved-race
replay produced seven compatibility captures and the following exact
source-frame-6000 view-8 relationship:

| Parent | Vtable | Child offset and caller | Semantic packet |
| --- | --- | --- | ---: |
| `0x430FE8B0` | `0x8223A694` | `+1408`, `0x823FA8DC` | 367 |
| same | same | `+1280`, `0x82447C08` | 368 |
| same | same | `+1184`, `0x823FB7D4` | 369 |

The verified title image's RTTI locator for `0x8223A694` names
`.?AVCRealtimeSky@@`. Each observed child address equals the same parent
plus its static call-site offset. This establishes the title
`CRealtimeSky` → three subrecords → second-path semantic packets chain.
The earlier passing backend ledger joined the same return-site family to
**nine candidate-attachment prepared draws** (three each), so these are a
sky producer to retain across the proposed opaque-scene cut. Their actual
color/depth blending and downstream consumers still require SNR-05 proof;
this identification alone does not qualify suppression.
This leaves 15 of that earlier ledger's 24 direct draws without a semantic
owner: nine from `0x823F59C8` and three each from `0x82401258` and
`0x8244F070`.

The executable SHA-256 was
`34E68725CD136C2F3BC838B46462DA369E53C155F67E824073950F10AFFD21EE`.
The four-record filtered trace is
`.local/native-renderer/snr01/shared-parent-run-a-filtered.log` (SHA-256
`586E97EE02FCCC3E1228F13BC4329D7DACD657DFD98F95843589292EA9F6D9EB`);
the title image SHA-256 was
`6014727FA7B0B79727FD5F32A2E2377533DC8E29679E8D2462BD764D331FA305`.
Recheck the pointer/packet relationship and RTTI with:

```powershell
@'
import json, struct
from pathlib import Path
rows = [json.loads(line[line.index('{'):]) for line in Path(
    '.local/native-renderer/snr01/shared-parent-run-a-filtered.log'
).read_text(encoding='utf-8').splitlines()]
parent, = [r for r in rows if 'parent' in r]
children = [r for r in rows if 'caller_object' in r]
offset = {0x823FA8DC: 1408, 0x82447C08: 1280, 0x823FB7D4: 1184}
assert len(children) == 3 and {r['caller_lr'] for r in children} == set(offset)
assert all(r['caller_object'] == parent['parent'] + offset[r['caller_lr']]
           and r['first_semantic'] == r['last_semantic'] for r in children)
image = Path('.local/ui-verify/default-image.bin').read_bytes()
word = lambda address: struct.unpack_from('>I', image, address - 0x82000000)[0]
locator = word(parent['parent_word0'] - 4)
descriptor = word(locator + 12)
start = descriptor + 8 - 0x82000000
assert image[start:image.index(0, start)] == b'.?AVCRealtimeSky@@'
'@ | python -
```

### Indexed2 packet 106 is a race-line presentation call

The verified title image has `sub_823EA098` at vtable slot `+32` of
`CPresentationRaceLine` (`0x8201FF70`). Generated `sub_823EA098` calls
`sub_82400E70`; the latter issues `sub_8240DC70` at return site
`0x82401258`. This is the exact caller site of title packet 106 in the
earlier passing particle ledger, which expanded to three candidate-attachment
prepared draws. Treat this as a **retained race-line presentation producer**
in the provisional cut, subject to SNR-05 color/depth composition proof.
The remaining semantically unowned direct work in that ledger is 12 draws:
nine at graphics-device wrapper return `0x823F59C8` and three at
`0x8244F070`. The wrapper itself is not an owner: title-image vtables for
`CD3D9GraphicsDevice` and its thread-safe ref-counted form contain
`sub_823F5980`; its enclosing caller still needs a title join.

### The graphics-device wrapper packets also belong to `CRealtimeSky`

A bounded entry hook on `sub_823F5980` records its enclosing caller before
the generic device submission. In a normal-exit saved-race replay with seven
compatibility captures, all three view-8 calls that produced the direct
packet family came from `sub_823FADC0`, `sub_82406030` and
`sub_82D71228`. Generated `sub_82D756A8` invokes those functions with
its parent at offsets `+48`, `+736` and `+256`. The observed caller-held
addresses were exactly those offsets from parent `0x4321F020`, whose
`0x8223A694` vtable again resolves to `CRealtimeSky`. The wrapper's
`first_direct` ordinals 193–195 join exact secondary packets 193–195,
all with return site `0x823F59C8`. Their 3100, 2900 and 3100 input
counts match the 9300, 8700 and 9300 prepared index counts in the
earlier passing backend ledger.

Thus **18 of the original 24 unowned candidate direct draws** are now
attributed to retained `CRealtimeSky` submissions (nine through each of
two wrappers), and three to the race-line presentation path. The remaining
three come from indexed2 return site `0x8244F070`. Its entry hook records
caller `0x82446164`; generated `sub_82444E60` calls `sub_823E2DE0`
there, which tail-calls `sub_8244E938`. The observed call's `arg5`
equals the view-8 presentation pointer, proving that it belongs to this
title view. The verified title image places `sub_82444E60` in slot `+52`
of `CPresentationView` and its thread-safe ref-counted form; the indexed2
contribution originates within that presentation-view call. Its lower-level
render-owner class and material role remain unresolved.
The preceding sky and race-line attribution does not make the rest of the
candidate attachment safe to suppress.

The executable SHA-256 was
`D5F0B7968DCA001EA9B55F237BBAA80AC9AAB1841C4D9B7B8B6A81FD060FB1DC`.
The nine-record filtered trace is
`.local/native-renderer/snr01/final-direct-run-a-filtered.log` (SHA-256
`603E5E86FD81BF2576765B504EECCBB25CABB8BD224583B9CD47395757EF3A9B`).
Recheck the exact parent-offset and packet joins with:

```powershell
@'
import json, struct
from pathlib import Path
rows = [json.loads(line[line.index('{'):]) for line in Path(
    '.local/native-renderer/snr01/final-direct-run-a-filtered.log'
).read_text(encoding='utf-8').splitlines()]
view, = [r for r in rows if 'view' in r]
parent, = [r for r in rows if 'parent' in r]
wrappers = [r for r in rows if 'caller_r30' in r]
packets = [r for r in rows if 'direct_caller_lr' in r]
indexed, = [r for r in rows if 'receiver' in r]
offset = {0x823FB260: 48, 0x82406910: 736, 0x82D71D2C: 256}
assert len(wrappers) == len(packets) == 3
assert {r['caller_lr'] for r in wrappers} == set(offset)
assert all(r['caller_r30'] == parent['parent'] + offset[r['caller_lr']]
           for r in wrappers)
assert {r['first_direct'] for r in wrappers} == {r['ordinal'] for r in packets}
assert {r['direct_caller_lr'] for r in packets} == {0x823F59C8}
assert indexed['arg5'] == view['view'] == parent['arg5']
image = Path('.local/ui-verify/default-image.bin').read_bytes()
word = lambda address: struct.unpack_from('>I', image, address - 0x82000000)[0]
assert word(0x8200265C + 52) == 0x82444E60
'@ | python -
```

This replay used a source-frame-only trace, so it establishes bounded
title-packet provenance rather than a new passing full-frame backend census.

### The final indexed2 family is a depth-tested world-space strip

A bounded read at the `sub_8244E938` entry captured the first four 16-byte
vertex records and the dynamic record count. In a normal-exit saved-race
replay with seven captures, the count was three; the first three position
triples were approximately `(-1606.47, 36.57, 2766.76)`,
`(-1773.72, 40.05, 2609.40)` and `(-1806.81, 39.31, 2529.29)`. These are
world-space coordinates, not a screen-space quad. The matching family in
the passing backend ledger had one 128×128 texture fetch and depth control
`0x08700262`: depth test enabled, depth write disabled, by ShiftGlue's
`RB_DEPTHCONTROL` bit layout. The title source is `CPresentationView`, as
proved above. This is a depth-tested, depth-read-only presentation
contribution whose exact lower-level material and composition role remain
open; it must not be silently folded into the native opaque slice.

The single-record trace is
`.local/native-renderer/snr01/indexed2-quad-run-a-filtered.log` (SHA-256
`8C3ABAC2D9788ADC0505760550B600C05B991198FA2C245CA22878CE85FB23F4`).
It used executable SHA-256
`09BA6236BCE3BB4CBAB4D9D96521C18F8EBF7385BC7E411B915B1AFB90DD96AE`.
Recheck the first three positions with:

```powershell
@'
import json, struct
from pathlib import Path
line, = Path('.local/native-renderer/snr01/indexed2-quad-run-a-filtered.log').read_text().splitlines()
row = json.loads(line[line.index('{'):])
assert row['view_call'] == 8 and row['quad_count'] == 3
xyz = [struct.unpack('<f', struct.pack('<I', word))[0]
       for word in row['quad_words'][:12]]
assert all(-2000 < xyz[i] < -1500 and 30 < xyz[i+1] < 50
           and 2500 < xyz[i+2] < 2800 for i in (0, 4, 8))
'@ | python -
```

### Process-bounded replay passes the full candidate boundary census

Rotating `runtime` logs retained records from previous launches; file names
alone are not a run boundary. `tools/extract-snr01-run-log.py` now uses the
process-specific JSONL session's start/end times and restores chronological
rotation order. The unit check includes an old-run tail in a rotated file.
For the normal-exit saved-race replay starting at
`20260923T052728Z-p30692.jsonl`, the extracted log contains only this
process's SNR-01 and clear-producer records. It is
`.local/native-renderer/snr01/clear-complete-run-a-session-filtered.log`
(SHA-256
`9BF6DC293F4D82B18064C6AC5FA3A9F82FCBC71BA0A9580CD17B089FFCC71953`)
with ledger `.local/native-renderer/snr01/clear-complete-run-a-ledger.json`
(SHA-256
`B99E029223DAF72CD1D915760DC7592ED443045CF990E7ECBAFAF1C3D8DC4A03`).
The build is the same SHA-256 as the quad replay above, and this run
produced seven compatibility captures.

The strict verifier accounted for **all 4,605 prepared draws and 131 root
buffers** in backend frame 6001. Both candidate color groups contain 2,705
draws: 1,960 view-8 scene-owner draws, 720 view-8 direct draws, one joined
title clear, and 24 indirect draws with no attachment write. The 24
direct draws without a direct-record, item/node, vegetation bound-record,
scalar-object or particle-parent join again partition as nine plus nine
`CRealtimeSky` draws, three race-line draws, and three view-owned indexed2
draws. No candidate writer lacks a proven title view-8 packet, scene-owner
join or clear. This is a reproducible **view/pass boundary census**, not
proof of complete semantic mesh/material ownership or a suppression cut.

Reproduce the extraction and strict check with:

```powershell
$stateRoot = Join-Path $env:LOCALAPPDATA 'PinyonShift\source\0.1.0\.local\preview'
$session = Join-Path $stateRoot 'logs\20260923T052728Z-p30692.jsonl'
python tools/extract-snr01-run-log.py $session `
  .local/native-renderer/snr01/clear-complete-run-a-session-filtered.log
python tools/summarize-snr01-frame-wide-census.py `
  .local/native-renderer/snr01/clear-complete-run-a-session-filtered.log `
  --source-frame 6000 --require-direct-family `
  --require-direct-family-record --require-semantic-item-node `
  --require-second-path --require-scalar-draw --require-dynamic-quad `
  --title-image .local/ui-verify/default-image.bin `
  --require-candidate-boundary `
  --output .local/native-renderer/snr01/clear-complete-run-a-ledger.json
```

The candidate view/pass boundary is stronger now, but SNR-00/01 remain open:
the complete selected-slice owner → geometry/material/lifetime joins,
retained-pass consumers and full same-frame diagnostic are not yet proved.

### Shared procedural state behind the largest view-8 scene-list family

The same process-bounded replay already contains `second track dispatch`
records. In source frame 6000, 69 calls target `sub_82417BC0`, the verified
slot-41 method of `proceduralGeometry::CProceduralModels`. Every call passes
`0x42030010` in `r6`. The generated method stores entry `r6`, forms
`r24 = r6 + 0xE940`, then calls `sub_82417060` with `r24` at return sites
`0x82418A28` and `0x82418ECC`. The helper's scene-list flush has return
site `0x824170BC`. This is a title-code relationship, not a guessed
offset from nearby allocations.

In the frame-wide ledger, all 893 candidate scene-list draws with that
flush return site have owner `0x4203E950`, exactly
`0x42030010 + 0xE940`. They derive from 226 source-frame-6000 title scene
packets on 95 distinct list objects, each with a one-node indirect list.
The retained owner's first word `0xBF0C2E94` is not a vtable; it varies
in other views.
This identifies the common procedural *state* behind the largest untyped
draw family. It does not assign those 95 lists to model instances or prove
that every state user is a `CProceduralModels` object: other generated
functions also call `sub_82417060`. The next required join is the writer
of each list and its selected model/geometry/material generation.

Recheck the same-frame runtime relationship from the saved log and ledger:

```powershell
@'
import json
from pathlib import Path
log = Path('.local/native-renderer/snr01/clear-complete-run-a-session-filtered.log')
ledger = json.loads(Path('.local/native-renderer/snr01/clear-complete-run-a-ledger.json').read_text())
model = []
packets = []
for line in log.open(encoding='utf8'):
    if 'FH1 SNR01 second track dispatch ' in line:
        row = json.loads(line[line.index('{'):])
        if row['frame'] == 6000 and row['target'] == 0x82417bc0:
            model.append(row)
    elif 'FH1 SNR01 scene indirect packet ' in line:
        row = json.loads(line[line.index('{'):])
        if row['frame'] == 6000 and row['view_call'] == 8 and row['flush_owner'] == 0x4203e950:
            packets.append(row)
draws = [row for row in ledger['draws'] if row['target'].startswith('14020500/')
         and row['classification'] == 'view_owner' and row['flush_caller_lr'] == 0x824170bc]
assert len(model) == 69 and len(packets) == 226 and len(draws) == 893
assert {row['arg6'] for row in model} == {0x42030010}
assert {row['owner'] for row in draws} == {0x4203e950}
assert {row['owner'] for row in draws} == {row['arg6'] + 0xe940 for row in model}
assert len({row['list_object'] for row in packets}) == 95
assert {row['node_count'] for row in packets} == {1}
assert {row['target_physical'] for row in packets} == {
    row['execution_command_buffer'] for row in draws}
'@ | python -
```

### Selected track-model instances reach three bounded scene lists

A default-off read-only hook after the `CProceduralModels` method's
slot-8 resource call captures the selected object and its return state.
The captured vtable `0x820019CC` resolves in the verified title image to
`Presentation_Unified::CTrackRenderModelInstance_Unified`; its slot 8 is
`sub_8243BC80`. The hook remains inactive without the SNR-01 frame probe.

The saved sustained-race replay with the GPU corpus exited normally and
produced seven compatibility captures. Executable SHA-256 was
`18659B4328BF52CAD426971990DC483C3E73E7B3FDDB9A6F9952021317A1A781`.
The process session was `20260923T055609Z-p35848.jsonl` and its extracted
log is `.local/native-renderer/snr01/procedural-resource-corpus-run-a-filtered.log`
(SHA-256 `0B0F8B1C7D83AFB31CB717DB8D3174D17A52757C34CE0021A3CD14EF1CF66C8D`).
The strict frame-wide ledger is
`.local/native-renderer/snr01/procedural-resource-corpus-run-a-ledger.json`
(SHA-256 `EEAC4219B6F989CAC51BBAF607A0CF6F336589C5DAC293A08A44ED4175AECCE2`).
It accounts for 3,778 prepared draws, 127 roots and both candidate color
groups without an unattributed attachment writer.

In source frame 6000, 76 `CProceduralModels` dispatches reached five
ready resource calls on three distinct track-model-instance objects.
Within the exact title-thread dispatch scopes, each selected resource
preceded its own scene-list packets. Three view-8 lists received 49 title
packets; their child-buffer identities joined **147 candidate prepared
draws**, all on color word `00030000`:

| Resource pointer | List object | Prepared draws |
| --- | --- | ---: |
| `AB1C06F8` | `AC04FA3C` | 36 |
| `AB1C070C` | `AC04FE74` | 99 |
| `AB1C0BE4` | `AC0653BC` | 12 |

The shared procedural state produced 652 candidate prepared draws in this
replay, leaving **505 without this per-resource join**. These counts are
from a different replay than the earlier 893-draw state sample; visibility
and traffic vary. The resource-to-list ordering does not yet establish
each resource's mesh, material, transform or allocation generation.
The other state users and producer/consumer bridges remain open.
The later caller-and-resource probe below resolves this shared-state family
in a separate sampled frame.

Reproduce the same-run joins and strict boundary check with:

```powershell
$stateRoot = Join-Path $env:LOCALAPPDATA 'PinyonShift\source\0.1.0\.local\preview'
$session = Join-Path $stateRoot 'logs\20260923T055609Z-p35848.jsonl'
python tools/extract-snr01-run-log.py $session `
  .local/native-renderer/snr01/procedural-resource-corpus-run-a-filtered.log
python tools/summarize-snr01-frame-wide-census.py `
  .local/native-renderer/snr01/procedural-resource-corpus-run-a-filtered.log `
  --source-frame 6000 --require-direct-family `
  --require-direct-family-record --require-semantic-item-node `
  --require-second-path --require-scalar-draw --require-dynamic-quad `
  --title-image .local/ui-verify/default-image.bin `
  --require-candidate-boundary `
  --output .local/native-renderer/snr01/procedural-resource-corpus-run-a-ledger.json
python tools/verify-snr01-model-resource-join.py `
  .local/native-renderer/snr01/procedural-resource-corpus-run-a-filtered.log `
  .local/native-renderer/snr01/procedural-resource-corpus-run-a-ledger.json `
  --source-frame 6000
```

### Both shared-state callers reach selected track-model resources

Read-only probes bracket the existing `sub_82417060` scene-list flush and
its other enclosing path, `sub_824365B0`. The flush brackets capture the
saved title caller LR and exact scene-packet ordinal range. In a normal-exit
saved-race replay with seven compatibility captures, every candidate
draw under the shared procedural state matched a bracketed title packet:
147 draws came through `sub_82417BC0` / return `0x82418ECC`, and 512
through `sub_824365B0` / return `0x82437048`. No state packet had a
mismatched owner or an ambiguous caller in that replay.

The subsequent resource probe on `sub_824365B0` found the selected
`CTrackRenderModelInstance_Unified` at its original slot-8 call. Both
title paths then associate each resource with its scene packet by the
source frame, title thread and enclosing call. The strict backend ledger
joins each packet's **header and child-buffer physical addresses** to its
prepared draws. Matching only the child-buffer/list address would be
wrong: some lists recur under different resource scopes in the same frame.

In this second normal-exit replay, the strict ledger accounts for all
5,160 prepared draws and 127 roots. Its 207 view-8 shared-state packets
join **all 856 candidate prepared draws** under that state, with no
unattributed attachment writer:

| Title resource path | Distinct selected instances | Packets | Prepared draws | Color words |
| --- | ---: | ---: | ---: | --- |
| `CProceduralModels` | 3 | 86 | 258 | `00030000` |
| `sub_824365B0` | 116 | 121 | 598 | 570 `00030000`, 28 `000C0000` |

The captured vtable for every selected resource was `0x820019CC`, whose
verified RTTI names `CTrackRenderModelInstance_Unified`; slot 8 was
`sub_8243BC80` and every observed readiness return was 1. This proves
selected resource **object identity** for the shared-state family in the
sampled frame. It does not prove allocation generations, geometry bytes,
materials, transforms, texture readiness, unload/reload behavior, or the
other candidate draw families. The proposed opaque/alpha-tested slice
therefore remains provisional and Gate A remains open.

The executable SHA-256 was
`064BC41856304E4793811F6A22B4C04FBA737EEF66C09C8DE509DF275E61D63A`.
The process session was `20260923T061319Z-p42596.jsonl`; the extracted
`.local/native-renderer/snr01/track-model-run-a-filtered.log` has SHA-256
`5FEB907DC649ED7B6B08FCA701E36BCE421892CAEB1251E0E027F0A71881B45E`,
and `.local/native-renderer/snr01/track-model-run-a-ledger.json` has
SHA-256 `1ACBEE288C6D41AC42FFF558BFFFEB38E3C354562F837A02EE21BA906C0A1FD4`.
The separate caller-partition replay used executable SHA-256
`985294994B28290C1F237DF8B545F6B564596FF2D973A3E835ED3E1D939511CC`
and process session `20260923T060700Z-p41516.jsonl`.

Reproduce the strict second-run check with the saved-race procedure,
`--pinyon_shift_fh1_gpu_corpus=true`,
`--pinyon_shift_fh1_clear_producer_trace=true`, and the source-frame-6000
SNR-01 trace flags, then run:

```powershell
$stateRoot = Join-Path $env:LOCALAPPDATA 'PinyonShift\source\0.1.0\.local\preview'
$session = Join-Path $stateRoot 'logs\20260923T061319Z-p42596.jsonl'
python tools/extract-snr01-run-log.py $session `
  .local/native-renderer/snr01/track-model-run-a-filtered.log
python tools/summarize-snr01-frame-wide-census.py `
  .local/native-renderer/snr01/track-model-run-a-filtered.log `
  --source-frame 6000 --require-direct-family `
  --require-direct-family-record --require-semantic-item-node `
  --require-second-path --require-scalar-draw --require-dynamic-quad `
  --title-image .local/ui-verify/default-image.bin `
  --require-candidate-boundary `
  --output .local/native-renderer/snr01/track-model-run-a-ledger.json
python tools/verify-snr01-state-resource-join.py `
  .local/native-renderer/snr01/track-model-run-a-filtered.log `
  .local/native-renderer/snr01/track-model-run-a-ledger.json `
  --source-frame 6000
```

The final cleanup removed a misleading exit-register field from the
second path. Its rebuilt executable SHA-256 was
`818F21B3CE113AC322AD8FD2C8EACD83EFC6463E81504FCB90A90A32F3D9240D`.
A second normal-exit saved-race replay produced seven captures. Its session
`20260923T062246Z-p19792.jsonl` yields
`.local/native-renderer/snr01/state-resource-final-run-a-filtered.log`
(SHA-256 `758D83E144646F06EB7CA01139455BB827595963CD2A603487C6C5E8BC43EBEF`)
and `.local/native-renderer/snr01/state-resource-final-run-a-ledger.json`
(SHA-256 `B038180F5853EC67FAD3E75EBA588837068FFDF0B6C4D784C46E54E835A05DC5`).
The strict ledger passes for all 3,639 prepared draws and 138 roots.
The state-resource verifier again joins **every** candidate state draw:
154 packets and 596 prepared draws, split into 72 from two selected
`CProceduralModels` resources and 524 from 125 selected track-path
resources. This repeat confirms the join across different visibility and
resource counts; it does not establish resource generations or a complete
native scene.

### Prior-frame clear producers close the final frame-wide boundary gap

The final strict ledger's 3,639 draws split into 1,919 on the two provisional
candidate targets and 1,720 on other targets. The candidate draws comprise
1,204 view-8 scene-list draws, 690 view-8 direct packets, one joined clear,
and 24 indirect draws with no attachment writes. This rechecks the candidate
view/pass boundary in a different frame; it does not freeze scene membership.

Outside the candidate targets, 583 out-of-view scene-list draws have title
view 0, another 669 have a joined view owner, 404 direct draws have a title
packet in views 0–7, 48 unmatched indirect draws have no attachment writes,
and 16 are joined title clears. The earlier ledger classified six of those
clears as unjoined direct-root draws because their root was published in
source frame 6001 while their command packets were written by clear records
in source frame 6000. The exact root-packet addresses fall uniquely in the
five preceding clear cursor ranges: backend ordinals 3364, 3371, 3374,
3375, 3378 and 3381 join clear records 62440–62444, respectively (62442
produces two draws). All five records precede the root's title primary
packet in the ordered log. The verifier now admits a clear from the root's
source frame or its immediately preceding frame, only when the complete
draw packet lies in one unique, non-refilled clear range written before
root publication. A later write to a reused ring address cannot qualify.

The corrected ledger is
`.local/native-renderer/snr01/state-resource-final-run-a-clear-joined-ledger.json`
(SHA-256 `BFBCD5370B43D55951AD249C01C147AE43D9BFA4B570BA71390E97B128DE0831`).
It accounts for all 3,639 prepared draws with no unjoined attachment
writer on either candidate or noncandidate targets in this backend frame.
This proves a frame-wide title view/pass or clear boundary for this replay,
not complete semantic ownership, retained-pass dependencies or a frozen
native scene slice.
The independent 4,605-draw clear-complete replay also joins six prior-frame
clears and leaves no unjoined attachment writer under the corrected verifier.

The candidate's view-8 direct packets still need semantic work: in this
replay, 220 join character-manager direct records, 211 join procedural
item/node packets, 166 of 175 second-path draws join vegetation bound
records, and all 57 scalar-wrapper draws join an outer object. Nine
second-path draws have no bound-record join. The direct packet and outer
object joins do not establish materials, geometry generations or safe
native admission. The 596 shared-state scene-list draws join selected
track-model resource objects through the state-resource verifier; the
other scene-list families still need equivalent per-item resource joins.

Recheck these counts from the final ledger without another gameplay run:

```powershell
python tools/summarize-snr01-frame-wide-census.py `
  .local/native-renderer/snr01/state-resource-final-run-a-filtered.log `
  --source-frame 6000 --require-direct-family `
  --require-direct-family-record --require-semantic-item-node `
  --require-second-path --require-scalar-draw --require-dynamic-quad `
  --title-image .local/ui-verify/default-image.bin `
  --require-candidate-boundary `
  --output .local/native-renderer/snr01/state-resource-final-run-a-clear-joined-ledger.json
@'
import collections, json
from pathlib import Path
rows = json.loads(Path(
    '.local/native-renderer/snr01/state-resource-final-run-a-ledger.json'
).read_text(encoding='utf8'))['draws']
candidate = [r for r in rows if r['target'].startswith('14020500/')]
other = [r for r in rows if not r['target'].startswith('14020500/')]
assert (len(rows), len(candidate), len(other)) == (3639, 1919, 1720)
assert collections.Counter(r['classification'] for r in candidate) == {
    'view_owner': 1204, 'direct_root': 690,
    'title_clear': 1, 'unmatched_indirect': 24}
assert collections.Counter(r['classification'] for r in other) == {
    'view_owner': 669, 'out_of_view_scene': 583, 'direct_root': 404,
    'unmatched_indirect': 48, 'title_clear': 16}
cross_frame = [r for r in other if r['classification'] == 'title_clear'
               and r['clear_producer_source_frame'] != r['root_source_frame']]
assert [(r['ordinal'], r['clear_producer_record']) for r in cross_frame] == [
    (3364, 62440), (3371, 62441), (3374, 62442), (3375, 62442),
    (3378, 62443), (3381, 62444)]
assert not [r for r in other if r['classification'] == 'direct_root'
            and r['title_packet_view_call'] is None]
'@ | python -
```

### Candidate-target membership is narrower than its attachment tuple

The corrected final replay's 1,919 candidate-target draws partition without
overlap. **1,801** belong to title-linked scene families: 608 car-model or
presentation scene-list draws, 596 selected track-model resource draws,
220 character-manager direct-record draws, 211 procedural item/node draws,
and 166 vegetation bound-record draws. These are *proposed scene members*,
not admitted native items: their complete mesh/material/transform and
generation records are still missing.

The remaining **57** scalar-wrapper draws have exact title packets but
uncertain slice roles. Thirty-six join four `CCarPresentation + 2016`
subobjects; the other 21 have no nonzero outer-object join in this replay
(15 at caller `0x82415A28`, three each at `0x823FDDFC` and `0x823FDE2C`).
The outer join proves presentation ownership for 36, not that their
color/depth work is replaceable by the proposed opaque scene. Static title
code narrows the other 21: `sub_82414A00` emits the 15 at `0x82415A28`
and is called by the `CProceduralAnimatedScene` path documented above;
their specific animated item/record is still unjoined. `sub_823EB600`
calls the scalar wrapper at `0x823FDDFC` and `0x823FDE2C`. The verified
title image places that function at vtable slot `+32` of
`TRefCountedObjectThreadSafe<CPresentationSkid>`, so the other six are
retained skid-presentation work, not an anonymous world-scene family.

The last **61** must remain outside native scene admission here: 18
`CRealtimeSky` draws (nine second-path semantic and nine graphics-device
wrapper), 12 `CParticleSystemNew` draws, three race-line draws, three
depth-tested presentation-strip draws, one title clear and 24 no-attachment-
write indirect draws. In particular, the nine second-path draws without a
vegetation bound record have caller sites `0x823FA8DC`, `0x82447C08` and
`0x823FB7D4`, three executions each. The separately verified
[`CRealtimeSky` parent join](#shared-second-path-parent-is-crealtimesky)
names those exact sites; their missing vegetation record is intentional.
This partition resolves an apparent SNR-01 ownership gap but does not prove
the retained sky/particle composition bridge or freeze the slice. The next
owner work is the 15 animated-scene scalar draws and complete resource/
material/lifetime joins for all proposed scene members. The 36 car-
presentation scalar draws still need a slice-role decision; the six skid
draws belong to the retained presentation dependency check.

Recheck the disjoint accounting from the corrected ledger:

```powershell
@'
import json
from pathlib import Path
rows = json.loads(Path(
    '.local/native-renderer/snr01/state-resource-final-run-a-clear-joined-ledger.json'
).read_text(encoding='utf8'))['draws']
rows = [r for r in rows if r['target'].startswith('14020500/')]
scene = [r for r in rows if r['classification'] == 'view_owner'
         or r['title_direct_record'] or r['title_item_node']
         or r['title_second_draw_bound_record']]
scalar = [r for r in rows if r['title_packet_caller_lr'] == 0x824131F4]
retained = [r for r in rows if r['title_second_path_caller_lr'] in (
    0x823FA8DC, 0x82447C08, 0x823FB7D4)
    or r['title_packet_caller_lr'] in (
        0x823F59C8, 0x82D07200, 0x82D0735C, 0x82401258, 0x8244F070)
    or r['classification'] in ('title_clear', 'unmatched_indirect')]
assert (len(rows), len(scene), len(scalar), len(retained)) == (1919, 1801, 57, 61)
assert len({id(r) for r in scene + scalar + retained}) == len(rows)
assert sum(bool(r['title_scalar_outer_object']) for r in scalar) == 36
assert sum(r['title_second_path_caller_lr'] in (
    0x823FA8DC, 0x82447C08, 0x823FB7D4) for r in retained) == 9
assert sum(r['title_dynamic_quad_parent_first_word'] == 0x82235F94
           for r in retained) == 12
'@ | python -
```

The skid identity is a static title-image check, not an instance-lifetime
claim. Its vtable RTTI is
`.?AV?$TRefCountedObjectThreadSafe@VCPresentationSkid@@@@`; the generated
`sub_823EB600` calls `sub_823FD9F0`, which makes the two observed wrapper
calls. Both caller sites expand to three prepared draws in this replay.
Recheck the image identity and replay counts with:

```powershell
@'
import collections, json, struct
from pathlib import Path
image = Path('.local/ui-verify/default-image.bin').read_bytes()
word = lambda address: struct.unpack_from('>I', image, address - 0x82000000)[0]
vtable = 0x820018F4
assert word(vtable + 32) == 0x823EB600
descriptor = word(word(vtable - 4) + 12)
start = descriptor + 8 - 0x82000000
assert image[start:image.index(0, start)] == (
    b'.?AV?$TRefCountedObjectThreadSafe@VCPresentationSkid@@@@')
rows = json.loads(Path(
    '.local/native-renderer/snr01/state-resource-final-run-a-clear-joined-ledger.json'
).read_text(encoding='utf8'))['draws']
counts = collections.Counter(r['title_scalar_caller_lr'] for r in rows
    if r['target'].startswith('14020500/') and
    r['title_packet_caller_lr'] == 0x824131F4)
assert (counts[0x82415A28], counts[0x823FDDFC], counts[0x823FDE2C]) == (15, 3, 3)
'@ | python -
```

### Animated scalar packets join selected bucket objects and child contexts

The existing title trace already brackets `sub_82414A00`'s direct packets
inside `CProceduralAnimatedScene` slot-41 `second draw call` scopes. The
frame-wide verifier now keys those scopes by source frame, title thread and
direct-packet ordinal, then joins their bucket entry to the selected
`second track dispatch`. It requires both targets to be `0x823FDE50`
and both device arguments to equal the scalar-wrapper input. The verified
title image names slot 41 of vtable `0x820029FC` as
`proceduralGeometry::CProceduralAnimatedScene` with that target.

In the final replay, all 15 candidate-target animated scalar callbacks join
11 exact title packets, six selected dispatch objects and 11 child contexts
across six bucket entries. Repeated backend callbacks keep the same packet,
bucket, dispatch object and child context. The independent 4,605-draw
clear-complete replay joins all 43 candidate animated callbacks through 39
title packets and four bucket entries. Neither replay needs an approximate
spatial or shader match. This establishes the selected animated item/packet
ownership edge, but the child context's mesh, material, transform and
generation fields are not yet decoded; those still block scene admission.

The final ledger is
`.local/native-renderer/snr01/state-resource-final-run-a-animated-joined-ledger.json`
(SHA-256 `15B465656A52D0CEEE0B13E0D7B8C83A06DE116DA4875111BA86D5F479A491D1`).
Rebuild it with the same strict command above, adding
`--require-animated-scalar` and changing `--output`, then check the exact
contribution:

```powershell
@'
import json
from pathlib import Path
rows = json.loads(Path(
    '.local/native-renderer/snr01/state-resource-final-run-a-animated-joined-ledger.json'
).read_text(encoding='utf8'))['draws']
animated = [r for r in rows if r['target'].startswith('14020500/')
            and r['title_scalar_caller_lr'] == 0x82415A28]
assert len(animated) == 15
assert len({r['title_packet_ordinal'] for r in animated}) == 11
assert len({r['title_scalar_bucket_entry'] for r in animated}) == 6
assert len({r['title_scalar_dispatch_object'] for r in animated}) == 6
assert len({r['title_scalar_child_context'] for r in animated}) == 11
assert all(r['title_scalar_dispatch_object'] and
           r['title_scalar_child_context'] for r in animated)
'@ | python -
```

### Car-presentation scalar packets cross both candidate color groups

The remaining 36 scalar draws join four `CCarPresentation + 2016`
subobjects in the same final replay. Generated `CPresentationView` method
`sub_82444E60` calls `sub_823F37D0`, which passes each presentation's
`+2016` subobject to `sub_82443600`. That routine issues the three observed
scalar wrapper calls in title packet order. Each of the four subobjects has
one packet at each caller, and each packet executes three times in backend
frame 6001:

| Title return site | Packet per subobject | Prepared draws | Target color word | Observed write state |
| --- | ---: | ---: | --- | --- |
| `0x82443B98` | First | 12 | `00030000` | color mask 0, no pixel shader, depth control `08714263` |
| `0x82443C40` | Second | 12 | `00030000` | color mask 0, no pixel shader, depth control `0871C263` |
| `0x82444018` | Third | 12 | `000C0000` | color mask 7, pixel shader present, depth control `08700261` |

The first two draw states are depth-only; the third writes color. The title
packet ordinals are 205–216 in four consecutive triples. This is an exact
same-owner relationship across the two candidate color groups, not two
independent passes. Its geometry/material role and depth consumers are not
proved, so Gate A cannot yet decide whether to render this contribution
natively or retain it with an ordered bridge. A shader hash or 12-index
shape is insufficient to call it a decal, shadow or vehicle surface.

Recheck the saved ledger's packet and write-state partition:

```powershell
@'
import collections, json
from pathlib import Path
rows = json.loads(Path(
    '.local/native-renderer/snr01/state-resource-final-run-a-animated-joined-ledger.json'
).read_text(encoding='utf8'))['draws']
rows = [r for r in rows if r['target'].startswith('14020500/')
        and r['title_scalar_outer_object']]
sites = (0x82443B98, 0x82443C40, 0x82444018)
assert len(rows) == 36
assert {r['title_scalar_caller_lr'] for r in rows} == set(sites)
assert len({r['title_scalar_outer_object'] for r in rows}) == 4
assert sorted({r['title_packet_ordinal'] for r in rows}) == list(range(205, 217))
assert collections.Counter(r['title_scalar_caller_lr'] for r in rows) == {
    site: 12 for site in sites}
assert all(r['color_mask'] == 0 and r['pixel_shader'] == 0
           for r in rows if r['title_scalar_caller_lr'] != sites[2])
assert all(r['color_mask'] == 7 and r['pixel_shader']
           for r in rows if r['title_scalar_caller_lr'] == sites[2])
'@ | python -
```

### Revised Gate A diagnostic slice across both candidate targets

`tools/partition-snr00-gate-a-slice.py` applies exact target-tuple and
title-return-site rules to the two independently strict frame-wide ledgers.
It assigns every prepared draw to a required scene family, a retained
candidate-target effect, or an outside target. An unexpected candidate caller
or missing title join fails the check. Outside targets must also have a
title view 0–7, a title clear producer, or a proven no-attachment-write
indirect draw. No shader hash or spatial match admits a draw. The two
replays give:

| Strict replay | All draws | Required diagnostic scene | Retained on candidate targets | Other targets |
| --- | ---: | ---: | ---: | ---: |
| Final resource/animated join | 3,639 | 1,852 | 67 | 1,720 |
| Independent clear-complete/animated join | 4,605 | 2,644 | 61 | 1,900 |
| Procedural payload probe | 3,241 | 1,638 | 70 | 1,533 |

| Required family | 3,639-draw replay | 4,605-draw replay |
| --- | ---: | ---: |
| Car model/presentation scene lists | 608 | 1,067 |
| Shared track/procedural scene lists | 596 | 893 |
| Character-manager direct records | 220 | 261 |
| Procedural item/node packets | 211 | 170 |
| Vegetation bound records (`CProceduralVegetation`) | 155 | 128 |
| Procedural-character bound records (`CProceduralCharacters`) | 11 | 10 |
| Animated-scene scalar packets | 15 | 43 |
| Car-presentation scalar packets | 36 | 72 |

The second-path bound-record test previously grouped procedural characters
with vegetation. Its exact title draw target distinguishes
`CProceduralCharacters` at `0x8245AB88` from `CProceduralVegetation` at
`0x824136F0`; both remain required. The corrected partition checks the
target, bound record and vegetation owner, and passes the two original strict
ledgers plus three later strict ledgers. The later source-frame-5000 combined
replay has 11 procedural-character and 155 vegetation draws; the latter count
matches its 155 vegetation prepared callbacks exactly. The correction changes
family names, not total selected/retained/outside counts. Neither family has
complete native diagnostic admission yet.

The third normal-exit replay independently passed the same fail-closed
partition over both candidate groups and all other targets. Its strict ledger
is `.local/native-renderer/snr02/item-payload-run-a-ledger.json` (SHA-256
`D2F2655F6C846DCBAE83FBF576D7EDE542D004C1C338185E23488FBB327FE5E9`);
its partition is `.local/native-renderer/snr02/item-payload-run-a-slice.json`
(SHA-256 `248205347F6A73FB7890069B57D2E117C8B52BD63D00C12FA806DFC50309761C`).
This frame's 308 procedural-item candidate draws join 174 exact title calls;
the selected descriptor/runtime payload evidence is in the
[SNR-02 log](SCENE_NATIVE_SNR02_EVIDENCE_2026-09-22.md#selected-procedural-descriptor-and-runtime-payloads).

The required set is every view-8 scene-list draw plus exact character-manager,
procedural-character, procedural item/node, vegetation bound-record,
animated-scene scalar and
car-presentation scalar packets. The latter include both depth-only packets
on color word `00030000` and the color-writing packet on `000C0000` for each
owner. They stay required in the diagnostic until the title proves whether
their role belongs to native scene work or needs a retained ordered bridge;
the current owner join alone does not prove that role. Retained effects are
the proven sky, particle, race-line, presentation-strip and skid callers,
the title clear, and no-attachment-write indirect points. They still execute
under compatibility; their composition/depth dependencies remain open.

This is an explicit **pilot slice revision** from attachment membership to
title-proved contribution membership. It does not mean that the 1,852 or
2,644 draws are already admitted to an immutable scene. Geometry, material,
resource generations and complete full-resolution diagnostic coverage are
still missing. Any new candidate target tuple or caller fails the current
rule and requires a documented revision. Other game modes and streaming
transitions need independent qualification before the rule can be treated as
their boundary.

Recheck both frame-wide partitions:

```powershell
python tools/partition-snr00-gate-a-slice.py `
  .local/native-renderer/snr01/state-resource-final-run-a-animated-joined-ledger.json
python tools/partition-snr00-gate-a-slice.py `
  .local/native-renderer/snr01/clear-complete-run-a-animated-joined-ledger.json
```

The saved outputs are `.local/native-renderer/snr01/gate-a-slice-3639.json`
and `gate-a-slice-4605.json` (SHA-256
`7400BAB86AE6EC3F8B289654E9D1F82E417C05C97D2CBCEC18FA5F3A344CF117`
and `412FBBFECDA2B6F9F35135D3411F6E8C86BE1B2E95D3F8F6BEE6491C67C2296F`).
The underlying ledgers have SHA-256
`15B465656A52D0CEEE0B13E0D7B8C83A06DE116DA4875111BA86D5F479A491D1`
and `D2CE9261E25959D706789F71CE803CE78DC6E60995CD7729C1D52D84D5084F6E`.
